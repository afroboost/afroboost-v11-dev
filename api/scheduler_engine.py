"""
scheduler_engine.py - Moteur de scheduler pour Afroboost
Architecture "POSER-RAMASSER" : DB = seule source de vérité

Date: 6 Février 2026
"""

import pytz
import os
import uuid as uuid_module
import requests
from datetime import datetime, timezone
import logging

logger = logging.getLogger("scheduler_engine")

PARIS_TZ = pytz.timezone('Europe/Paris')

# ==================== PARSING & VALIDATION ====================

def parse_campaign_date(date_str):
    """Parse une date ISO et la convertit en datetime UTC."""
    if not date_str:
        return None
    try:
        if 'Z' in date_str:
            date_str = date_str.replace('Z', '+00:00')
            dt = datetime.fromisoformat(date_str)
        elif '+' in date_str or (len(date_str) > 10 and '-' in date_str[-6:] and ':' in date_str[-3:]):
            dt = datetime.fromisoformat(date_str)
        else:
            dt = datetime.fromisoformat(date_str)
            dt = PARIS_TZ.localize(dt)
        
        if dt.tzinfo is None:
            dt = PARIS_TZ.localize(dt)
        
        return dt.astimezone(pytz.UTC)
    except Exception as e:
        logger.warning(f"[SCHEDULER] Date parsing error '{date_str}': {e}")
        return None


def validate_cta_link(cta_link):
    """Valide et normalise un lien CTA."""
    if not cta_link:
        return None
    validated_link = cta_link.strip()
    if validated_link and not validated_link.startswith(('http://', 'https://', '#')):
        validated_link = 'https://' + validated_link
    return validated_link


# ==================== ARCHITECTURE "POSER-RAMASSER" ====================
# Le scheduler POSE les messages en DB, le frontend les RAMASSE

def store_scheduled_message(scheduler_db, session_id, message_text, mode="community", 
                           media_url=None, cta_type=None, cta_text=None, cta_link=None,
                           campaign_id=None, campaign_name=None):
    """
    POSER: Stocke un message programmé en DB avec status 'stored'.
    C'est la SEULE source de vérité pour les messages.
    
    Returns:
        (success: bool, message_id: str|None, error: str|None)
    """
    try:
        message_id = str(uuid_module.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        # Message à stocker
        message = {
            "id": message_id,
            "session_id": session_id,
            "sender_id": "coach",
            "sender_name": "Coach Bassi",
            "sender_type": "coach",
            "content": message_text,
            "mode": mode,
            "is_deleted": False,
            "notified": False,
            "scheduled": True,
            "status": "stored",
            "created_at": now,
            "stored_at": now
        }
        
        # Champs optionnels
        if media_url:
            message["media_url"] = media_url
        if cta_type:
            message["cta_type"] = cta_type
        if cta_text:
            message["cta_text"] = cta_text
        if cta_link:
            message["cta_link"] = validate_cta_link(cta_link)
        if campaign_id:
            message["campaign_id"] = campaign_id
        if campaign_name:
            message["campaign_name"] = campaign_name
        
        # INSERTION EN DB - POINT DE VÉRITÉ
        result = scheduler_db.chat_messages.insert_one(message)
        
        if result.inserted_id:
            print(f"[POSER] ✅ Message stocké en DB: {message_id[:8]}... -> session {session_id[:8]}...")
            logger.info(f"[POSER] Message {message_id} stocké pour session {session_id}")
            return True, message_id, None
        else:
            return False, None, "Insertion DB échouée"
            
    except Exception as e:
        print(f"[POSER] ❌ Erreur stockage: {e}")
        logger.error(f"[POSER] Erreur: {e}")
        return False, None, str(e)


def emit_socket_signal(message_id, session_id, message_data):
    """
    Émet un signal Socket.IO pour les clients connectés en direct.
    ATTENTION: Ce n'est qu'un signal, pas la source de vérité.
    """
    try:
        socket_payload = {
            "id": message_data.get("id", message_id),
            "type": "coach",
            "text": message_data.get("content", ""),
            "sender": "Coach Bassi",
            "senderId": "coach",
            "sender_type": "coach",
            "scheduled": True,
            "created_at": message_data.get("created_at")
        }
        
        # Ajouter les champs optionnels
        for field in ["media_url", "cta_type", "cta_text", "cta_link"]:
            if message_data.get(field):
                socket_payload[field] = message_data[field]
        
        response = requests.post(
            "http://localhost:8001/api/scheduler/emit-group-message",
            json={"session_id": session_id, "message": socket_payload},
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"[SIGNAL] ✅ Socket.IO émis pour {message_id[:8]}...")
            return True
        else:
            print(f"[SIGNAL] ⚠️ Socket.IO: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"[SIGNAL] ⚠️ Socket.IO exception: {e}")
        return False


def send_internal_message(scheduler_db, conversation_id, message_text, conversation_name="",
                         media_url=None, cta_type=None, cta_text=None, cta_link=None,
                         campaign_id=None, campaign_name=None):
    """
    Architecture "POSER-RAMASSER" pour messages internes.
    1. POSER: Stocke en DB
    2. SIGNAL: Émet Socket.IO (optionnel, pour clients connectés)
    """
    try:
        processed_message = message_text.replace("{prénom}", conversation_name or "ami(e)").replace("{prenom}", conversation_name or "ami(e)")
        
        # Vérifier/créer la session
        session = scheduler_db.chat_sessions.find_one(
            {"id": conversation_id, "is_deleted": {"$ne": True}},
            {"_id": 0, "id": 1, "mode": 1}
        )
        
        if not session:
            if conversation_id in ["community", "vip", "promo"]:
                new_session_id = str(uuid_module.uuid4())
                new_session = {
                    "id": new_session_id,
                    "participant_ids": [],
                    "mode": conversation_id,
                    "is_ai_active": False,
                    "is_deleted": False,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "title": f"💬 Groupe {conversation_id.capitalize()}"
                }
                scheduler_db.chat_sessions.insert_one(new_session)
                session = new_session
                conversation_id = new_session_id
            else:
                return False, f"Session non trouvée: {conversation_id}", None
        else:
            conversation_id = session.get("id")
        
        mode = session.get("mode", "user")
        
        # ÉTAPE 1: POSER en DB
        success, message_id, error = store_scheduled_message(
            scheduler_db=scheduler_db,
            session_id=conversation_id,
            message_text=processed_message,
            mode=mode,
            media_url=media_url,
            cta_type=cta_type,
            cta_text=cta_text,
            cta_link=cta_link,
            campaign_id=campaign_id,
            campaign_name=campaign_name
        )
        
        if not success:
            return False, error, None
        
        # ÉTAPE 2: SIGNAL Socket.IO (optionnel)
        message_data = {
            "id": message_id,
            "content": processed_message,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "media_url": media_url,
            "cta_type": cta_type,
            "cta_text": cta_text,
            "cta_link": validate_cta_link(cta_link) if cta_link else None
        }
        emit_socket_signal(message_id, conversation_id, message_data)
        
        return True, None, conversation_id
        
    except Exception as e:
        print(f"[INTERNAL] ❌ Exception: {e}")
        return False, str(e), None


def send_group_message(scheduler_db, target_group_id, message_text,
                      media_url=None, cta_type=None, cta_text=None, cta_link=None,
                      campaign_id=None, campaign_name=None):
    """
    Architecture "POSER-RAMASSER" pour messages groupe.
    """
    try:
        processed_message = message_text.replace("{prénom}", "Communauté").replace("{prenom}", "Communauté")
        
        # Trouver ou créer la session communautaire
        community_session = scheduler_db.chat_sessions.find_one({
            "mode": "community",
            "is_deleted": {"$ne": True}
        }, {"_id": 0})
        
        if not community_session:
            session_id = str(uuid_module.uuid4())
            new_session = {
                "id": session_id,
                "participant_ids": [],
                "mode": "community",
                "is_ai_active": False,
                "is_deleted": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "title": "💬 Communauté Afroboost"
            }
            scheduler_db.chat_sessions.insert_one(new_session)
        else:
            session_id = community_session.get("id")
        
        # ÉTAPE 1: POSER en DB
        success, message_id, error = store_scheduled_message(
            scheduler_db=scheduler_db,
            session_id=session_id,
            message_text=processed_message,
            mode="community",
            media_url=media_url,
            cta_type=cta_type,
            cta_text=cta_text,
            cta_link=cta_link,
            campaign_id=campaign_id,
            campaign_name=campaign_name
        )
        
        if not success:
            return False, error, None
        
        # ÉTAPE 2: SIGNAL Socket.IO
        message_data = {
            "id": message_id,
            "content": processed_message,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "media_url": media_url,
            "cta_type": cta_type,
            "cta_text": cta_text,
            "cta_link": validate_cta_link(cta_link) if cta_link else None
        }
        emit_socket_signal(message_id, session_id, message_data)
        
        return True, None, session_id
        
    except Exception as e:
        print(f"[GROUP] ❌ Exception: {e}")
        return False, str(e), None


def send_email(to_email, to_name, subject, message, media_url=None):
    """Envoi email via l'API interne."""
    try:
        response = requests.post(
            "http://localhost:8001/api/campaigns/send-email",
            json={
                "to_email": to_email,
                "to_name": to_name,
                "subject": subject,
                "message": message,
                "media_url": media_url
            },
            timeout=30
        )
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                return True, None
            return False, result.get("error", "Unknown error")
        return False, f"HTTP {response.status_code}"
    except Exception as e:
        return False, str(e)


def send_whatsapp(to_phone, message, media_url=None):
    """Envoi WhatsApp via Twilio."""
    try:
        response = requests.post(
            "http://localhost:8001/api/campaigns/send-whatsapp",
            json={
                "to_phone": to_phone,
                "message": message,
                "media_url": media_url
            },
            timeout=30
        )
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                return True, None, result.get("sid")
            return False, result.get("error", "Unknown error"), None
        return False, f"HTTP {response.status_code}", None
    except Exception as e:
        return False, str(e), None


# ==================== JOB PRINCIPAL DU SCHEDULER ====================

def scheduler_job(mongo_client_sync, scheduler_heartbeat_ref):
    """
    Job APScheduler - s'exécute toutes les 60 secondes.
    Architecture "POSER-RAMASSER": DB = seule source de vérité.
    """
    scheduler_db = mongo_client_sync[os.environ.get('DB_NAME', 'test_database')]
    
    try:
        now_utc = datetime.now(timezone.utc)
        now_paris = datetime.now(PARIS_TZ)
        now_str_paris = now_paris.strftime('%H:%M:%S')
        
        # Mettre à jour le heartbeat
        scheduler_heartbeat_ref[0] = now_utc.isoformat()
        
        # Récupérer les campagnes actives
        campaigns = list(scheduler_db.campaigns.find(
            {"status": {"$in": ["scheduled", "sending", "pending_quota"]}},
            {"_id": 0}
        ))
        
        print(f"[SCHEDULER] ⏰ {now_str_paris} Paris | {len(campaigns)} campagne(s)")
        logger.info(f"[SCHEDULER] 📋 {len(campaigns)} campagne(s) à vérifier ({now_str_paris} Paris)")
        
        for campaign in campaigns:
            try:
                campaign_id = campaign.get("id")
                campaign_name = campaign.get("name", "Sans nom")
                
                scheduled_at = campaign.get("scheduledAt")
                scheduled_dates = campaign.get("scheduledDates", [])
                sent_dates = campaign.get("sentDates", [])
                
                if scheduled_at and not scheduled_dates:
                    scheduled_dates = [scheduled_at]
                
                if not scheduled_dates:
                    continue
                
                # Trouver les dates à traiter
                dates_to_process = []
                for date_str in scheduled_dates:
                    parsed_date = parse_campaign_date(date_str)
                    if parsed_date:
                        is_past = parsed_date <= now_utc
                        already_sent = date_str in sent_dates
                        
                        if is_past and not already_sent:
                            dates_to_process.append(date_str)
                            parsed_paris = parsed_date.astimezone(PARIS_TZ)
                            print(f"[DEBUG] ✅ ENVOI! '{campaign_name}' | Prévu: {parsed_paris.strftime('%H:%M')} | Now: {now_str_paris}")
                
                if not dates_to_process:
                    continue
                
                print(f"[SCHEDULER] 🎯 EXÉCUTION: {campaign_name}")
                
                channels = campaign.get("channels", {})
                message = campaign.get("message", "")
                media_url = campaign.get("mediaUrl", "")
                cta_type = campaign.get("ctaType")
                cta_text = campaign.get("ctaText")
                cta_link = campaign.get("ctaLink")
                
                success_count = 0
                fail_count = 0
                results = campaign.get("results", [])
                
                # ========== MESSAGERIE INTERNE ==========
                if channels.get("internal"):
                    target_ids = campaign.get("targetIds", [])
                    target_conv_id = campaign.get("targetConversationId")
                    
                    if not target_ids and target_conv_id:
                        target_ids = [target_conv_id]
                    
                    if target_ids:
                        for idx, tid in enumerate(target_ids):
                            try:
                                success, error, session_id = send_internal_message(
                                    scheduler_db=scheduler_db,
                                    conversation_id=tid,
                                    message_text=message,
                                    conversation_name=campaign.get("targetConversationName", ""),
                                    media_url=media_url if media_url else None,
                                    cta_type=cta_type,
                                    cta_text=cta_text,
                                    cta_link=cta_link,
                                    campaign_id=campaign_id,
                                    campaign_name=campaign_name
                                )
                                
                                results.append({
                                    "contactId": tid,
                                    "channel": "internal",
                                    "status": "sent" if success else "failed",
                                    "error": error if not success else None,
                                    "sentAt": now_utc.isoformat()
                                })
                                
                                if success:
                                    success_count += 1
                                    print(f"[SCHEDULER] ✅ Interne [{idx+1}/{len(target_ids)}]: OK")
                                else:
                                    fail_count += 1
                                    
                            except Exception as e:
                                fail_count += 1
                                continue
                    
                    # Si UNIQUEMENT internal, on termine
                    only_internal = not any([channels.get("whatsapp"), channels.get("email"), channels.get("group")])
                    if only_internal:
                        new_status = "completed" if success_count > 0 else "failed"
                        scheduler_db.campaigns.update_one(
                            {"id": campaign_id},
                            {"$set": {
                                "status": new_status,
                                "results": results,
                                "sentDates": list(set(sent_dates + dates_to_process)),
                                "updatedAt": now_utc.isoformat()
                            }}
                        )
                        print(f"[SCHEDULER] {'🟢' if success_count > 0 else '🔴'} '{campaign_name}' → {new_status}")
                        continue
                
                # ========== GROUPE ==========
                if channels.get("group"):
                    try:
                        success, error, session_id = send_group_message(
                            scheduler_db=scheduler_db,
                            target_group_id=campaign.get("targetGroupId", "community"),
                            message_text=message,
                            media_url=media_url if media_url else None,
                            cta_type=cta_type,
                            cta_text=cta_text,
                            cta_link=cta_link,
                            campaign_id=campaign_id,
                            campaign_name=campaign_name
                        )
                        
                        results.append({
                            "contactId": "group",
                            "channel": "group",
                            "status": "sent" if success else "failed",
                            "error": error if not success else None,
                            "sentAt": now_utc.isoformat()
                        })
                        
                        if success:
                            success_count += 1
                            print(f"[SCHEDULER] ✅ Groupe: OK")
                        else:
                            fail_count += 1
                            
                    except Exception as e:
                        fail_count += 1
                
                # ========== EMAIL & WHATSAPP (contacts) ==========
                target_type = campaign.get("targetType", "all")
                selected_contacts = campaign.get("selectedContacts", [])
                
                if target_type == "all":
                    contacts = list(scheduler_db.users.find({}, {"_id": 0}))
                else:
                    contacts = list(scheduler_db.users.find({"id": {"$in": selected_contacts}}, {"_id": 0}))
                
                for contact in contacts:
                    contact_email = contact.get("email", "")
                    contact_phone = contact.get("whatsapp", "")
                    contact_name = contact.get("name", "")
                    
                    if channels.get("email") and contact_email:
                        try:
                            success, error = send_email(
                                to_email=contact_email,
                                to_name=contact_name,
                                subject=f"📢 {campaign_name}",
                                message=message,
                                media_url=media_url if media_url else None
                            )
                            results.append({
                                "contactEmail": contact_email,
                                "channel": "email",
                                "status": "sent" if success else "failed",
                                "error": error if not success else None,
                                "sentAt": now_utc.isoformat()
                            })
                            if success:
                                success_count += 1
                            else:
                                fail_count += 1
                        except:
                            fail_count += 1
                    
                    if channels.get("whatsapp") and contact_phone:
                        try:
                            success, error, sid = send_whatsapp(
                                to_phone=contact_phone,
                                message=message,
                                media_url=media_url if media_url else None
                            )
                            results.append({
                                "contactPhone": contact_phone,
                                "channel": "whatsapp",
                                "status": "sent" if success else "failed",
                                "error": error if not success else None,
                                "sentAt": now_utc.isoformat()
                            })
                            if success:
                                success_count += 1
                            else:
                                fail_count += 1
                        except:
                            fail_count += 1
                
                # Mise à jour finale
                new_sent_dates = list(set(sent_dates + dates_to_process))
                all_dates_done = set(new_sent_dates) >= set(scheduled_dates)
                
                if fail_count > 0 and success_count == 0:
                    new_status = "failed"
                elif all_dates_done:
                    new_status = "completed"
                else:
                    new_status = "scheduled"
                
                scheduler_db.campaigns.update_one(
                    {"id": campaign_id},
                    {"$set": {
                        "status": new_status,
                        "results": results,
                        "sentDates": new_sent_dates,
                        "updatedAt": now_utc.isoformat()
                    }}
                )
                
                print(f"[SCHEDULER] {'🟢' if new_status == 'completed' else '🔴'} '{campaign_name}' → {new_status} (✓{success_count}/✗{fail_count})")
                
            except Exception as campaign_error:
                logger.error(f"[SCHEDULER] ❌ Erreur campagne: {campaign_error}")
                continue
            
    except Exception as e:
        logger.error(f"[SCHEDULER] ❌ Erreur job: {e}")
