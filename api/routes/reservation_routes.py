# reservation_routes.py - Routes réservations v9.5.8 → v96: Email confirmation → v158: AFRO-XXXX + WhatsApp + i18n
import re  # V310 : disponible au niveau module pour re.escape (anti-injection regex)
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
import uuid
import logging
import asyncio
import os
import secrets
import string
from urllib.parse import quote

logger = logging.getLogger(__name__)

# === v96: Email confirmation après réservation ===
try:
    import resend
    _RESEND_OK = True
except ImportError:
    _RESEND_OK = False

# === v158: WhatsApp via Twilio ===
try:
    from twilio.rest import Client as _TwilioClient
    _TWILIO_OK = True
except ImportError:
    _TWILIO_OK = False

_RESEND_KEY = os.environ.get('RESEND_API_KEY', '')
_TWILIO_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
_TWILIO_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
_TWILIO_WHATSAPP_FROM = os.environ.get('TWILIO_WHATSAPP_FROM', 'whatsapp:+14155238886')  # sandbox par défaut


# V180: Helper pour envoyer notifications push à un user via son email
async def _send_push_to_email(email: str, title: str, body: str, data: dict = None) -> bool:
    """V180: Envoie une notification push à tous les participants liés à un email."""
    if not email or db is None:
        return False
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        return False
    vapid_private = os.environ.get('VAPID_PRIVATE_KEY', '')
    vapid_email = os.environ.get('VAPID_CLAIMS_EMAIL', 'contact@afroboost.ch')
    if not vapid_private:
        return False
    import json as _json
    email_lower = email.lower().strip()
    candidate_pids = set()
    # V206: Chercher directement dans push_subscriptions par email + préfixe coach_
    try:
        async for ps in db.push_subscriptions.find({"email": email_lower}, {"_id": 0, "participant_id": 1}):
            if ps.get("participant_id"):
                candidate_pids.add(ps["participant_id"])
    except Exception:
        pass
    candidate_pids.add(f"coach_{email_lower}")
    # V181: Chercher dans chat_participants ET users (CRM)
    try:
        async for p in db.chat_participants.find({"email": email_lower}, {"_id": 0, "id": 1}):
            if p.get("id"):
                candidate_pids.add(p["id"])
    except Exception:
        pass
    try:
        async for u in db.users.find({"email": email_lower}, {"_id": 0, "id": 1}):
            if u.get("id"):
                candidate_pids.add(u["id"])
    except Exception:
        pass
    sent = 0
    for pid in candidate_pids:
        if not pid:
            continue
        try:
            sub = await db.push_subscriptions.find_one({"participant_id": pid, "active": True}, {"_id": 0})
        except Exception:
            continue
        if not sub or not sub.get("subscription"):
            continue
        payload = _json.dumps({
            "title": title, "body": body,
            "icon": "/logo192.png", "badge": "/notification-badge-96.png",  # V445 : le badge
        # Android n'est qu'un masque alpha — le logo couleur y donnait un carre blanc.
        # (Le Service Worker code ses propres valeurs en dur et ignore celles-ci ;
        #  on les corrige tout de meme pour qu'aucune des deux ne mente.)
            "data": data or {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        try:
            webpush(
                subscription_info=sub["subscription"], data=payload,
                vapid_private_key=vapid_private,
                vapid_claims={"sub": "mailto:" + vapid_email}
            )
            sent += 1
        except WebPushException as e:
            if e.response and e.response.status_code in [404, 410]:
                try:
                    await db.push_subscriptions.update_one({"participant_id": pid}, {"$set": {"active": False}})
                except Exception:
                    pass
        except Exception:
            pass
    if sent > 0:
        logger.info(f"[PUSH-V180] {sent} notif(s) envoyée(s) à {email_lower}: {title}")
    return sent > 0


# === v158: Génération du code d'accès permanent AFRO-XXXX ===
def _generate_afro_code() -> str:
    """Génère un code d'accès permanent au format AFRO-XXXX (alphanumérique)."""
    alphabet = string.ascii_uppercase + string.digits  # exclut 0, O, I, 1 pour lisibilité
    alphabet = alphabet.replace('O', '').replace('0', '').replace('I', '').replace('1', '')
    return 'AFRO-' + ''.join(secrets.choice(alphabet) for _ in range(4))


async def _ensure_user_access_code(user_email: str, user_name: str, user_whatsapp: str = None, lang: str = 'fr') -> str:
    """Retourne le code AFRO-XXXX permanent de l'utilisateur, en le créant au premier usage.
    Le code est stocké dans db.users pour réutilisation."""
    if db is None or not user_email:
        return _generate_afro_code()  # fallback
    user_email = user_email.lower().strip()
    existing = await db.users.find_one({"email": user_email}, {"_id": 0, "accessCode": 1})
    if existing and existing.get("accessCode"):
        return existing["accessCode"]
    # Générer un code unique (on ré-essaye jusqu'à 5 fois en cas de collision)
    for _ in range(5):
        code = _generate_afro_code()
        collision = await db.users.find_one({"accessCode": code}, {"_id": 0})
        if not collision:
            break
    # Upsert dans db.users (compte client auto-créé)
    await db.users.update_one(
        {"email": user_email},
        {"$set": {
            "email": user_email,
            "name": user_name,
            "whatsapp": user_whatsapp,
            "language": lang,
            "updatedAt": datetime.now(timezone.utc).isoformat()
        },
         "$setOnInsert": {
            "id": str(uuid.uuid4()),
            "accessCode": code,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "role": "client"
        }},
        upsert=True
    )
    # Re-lire pour obtenir le code finalement stocké (évite race conditions)
    final = await db.users.find_one({"email": user_email}, {"_id": 0, "accessCode": 1})
    return final.get("accessCode", code) if final else code


# === v158: Traductions multilingues (FR/DE/EN) ===
_I18N = {
    'fr': {
        'subject': 'Réservation confirmée',
        'hero_title': 'Réservation confirmée !',
        'thanks': 'Merci {name} pour ta réservation ! Voici le récapitulatif :',
        'reference': 'Référence',
        'offer': 'Offre',
        'course': 'Cours',
        'dates': 'Dates',
        'promo': 'Code promo',
        'price': 'Prix',
        'qr_label': 'Ton QR Code d\'entrée',
        'qr_note': 'Présente ce QR Code à l\'entrée du cours — il sert aussi de raccourci vers ton chat.',
        'access_title': '🎟️ Ton code d\'accès personnel',
        'access_intro': 'Utilise ce code pour réserver tes prochaines séances depuis le chat :',
        'guide_title': '📖 Comment réserver tes prochaines séances',
        'guide_step1': '1. Clique sur le bouton ci-dessous "Aller au chat"',
        'guide_step2': '2. Entre ton code d\'accès {code}',
        'guide_step3': '3. Clique sur l\'icône calendrier 📅',
        'guide_step4': '4. Choisis ton horaire — au minimum 24h à l\'avance',
        'cta_chat': 'Aller au chat',
        'cta_space': 'Mon espace',
        'footer': 'Conserve cet email. À très vite chez Afroboost !',
        'credit_label': 'Ton crédit restant',
        'credit_unit': 'séances',
        # v158: règles annulation & remboursement
        'cancel_title': '⚠️ Règles d\'annulation',
        'cancel_rule1': 'Annulation possible jusqu\'à 24h avant la séance.',
        'cancel_rule2': 'Passé ce délai : séance non remboursable.',
        # v158: infos pratiques à apporter le jour J
        'practical_title': '🎒 Infos pratiques pour ta séance',
        'practical_rule1': '🕒 Viens 15 minutes en avance',
        'practical_rule2': '👕 Tenue de sport',
        'practical_rule3': '🧻 Serviette',
        'practical_rule4': '💧 Bouteille d\'eau',
        'whatsapp_msg': ('✨ Afroboost — Réservation confirmée ✨\n\n'
                         'Merci {name} ! Référence : {res_code}\n'
                         '🎟️ Code d\'accès permanent : {access_code}\n'
                         '📅 {dates}\n\n'
                         'Pour tes prochaines séances, va sur le chat Afroboost et entre ton code.\n'
                         '⚠️ Réserve au moins 24h à l\'avance sinon la séance est perdue.\n'
                         '⚠️ Annulation uniquement jusqu\'à 24h avant — sinon non remboursable.\n\n'
                         '🎒 À apporter : tenue de sport, serviette, bouteille d\'eau\n'
                         '🕒 Viens 15 minutes en avance\n\n'
                         '💜 La piste t\'attend !'),
    },
    'en': {
        'subject': 'Booking confirmed',
        'hero_title': 'Booking confirmed!',
        'thanks': 'Thanks {name} for your booking! Here is the summary:',
        'reference': 'Reference',
        'offer': 'Offer',
        'course': 'Course',
        'dates': 'Dates',
        'promo': 'Promo code',
        'price': 'Price',
        'qr_label': 'Your entry QR code',
        'qr_note': 'Show this QR code at the door — it also opens your chat.',
        'access_title': '🎟️ Your personal access code',
        'access_intro': 'Use this code to book your next sessions from the chat:',
        'guide_title': '📖 How to book your next sessions',
        'guide_step1': '1. Tap the "Go to chat" button below',
        'guide_step2': '2. Enter your access code {code}',
        'guide_step3': '3. Tap the calendar icon 📅',
        'guide_step4': '4. Pick your slot — at least 24h in advance',
        'cta_chat': 'Go to chat',
        'cta_space': 'My space',
        'footer': 'Keep this email safe. See you soon at Afroboost!',
        'credit_label': 'Your remaining credit',
        'credit_unit': 'sessions',
        'cancel_title': '⚠️ Cancellation policy',
        'cancel_rule1': 'Cancellation is allowed up to 24h before the session.',
        'cancel_rule2': 'After that: the session is non-refundable.',
        'practical_title': '🎒 Practical info for your session',
        'practical_rule1': '🕒 Arrive 15 minutes early',
        'practical_rule2': '👕 Sportswear',
        'practical_rule3': '🧻 Towel',
        'practical_rule4': '💧 Water bottle',
        'whatsapp_msg': ('✨ Afroboost — Booking confirmed ✨\n\n'
                         'Thanks {name}! Reference: {res_code}\n'
                         '🎟️ Permanent access code: {access_code}\n'
                         '📅 {dates}\n\n'
                         'For your next sessions, go to the Afroboost chat and enter your code.\n'
                         '⚠️ Book at least 24h in advance or the session is lost.\n'
                         '⚠️ Cancel at least 24h before — otherwise non-refundable.\n\n'
                         '🎒 Bring: sportswear, towel, water bottle\n'
                         '🕒 Arrive 15 min early\n\n'
                         '💜 The dance floor is waiting!'),
    },
    'de': {
        'subject': 'Buchung bestätigt',
        'hero_title': 'Buchung bestätigt!',
        'thanks': 'Danke {name} für deine Buchung! Hier die Übersicht:',
        'reference': 'Referenz',
        'offer': 'Angebot',
        'course': 'Kurs',
        'dates': 'Termine',
        'promo': 'Rabattcode',
        'price': 'Preis',
        'qr_label': 'Dein Eingangs-QR-Code',
        'qr_note': 'Zeige diesen QR-Code am Eingang — er öffnet auch deinen Chat.',
        'access_title': '🎟️ Dein persönlicher Zugangscode',
        'access_intro': 'Verwende diesen Code, um deine nächsten Sessions im Chat zu buchen:',
        'guide_title': '📖 So buchst du deine nächsten Sessions',
        'guide_step1': '1. Klicke unten auf "Zum Chat"',
        'guide_step2': '2. Gib deinen Zugangscode ein: {code}',
        'guide_step3': '3. Klicke auf das Kalender-Symbol 📅',
        'guide_step4': '4. Wähle einen Slot — mindestens 24h im Voraus',
        'cta_chat': 'Zum Chat',
        'cta_space': 'Mein Bereich',
        'footer': 'Bewahre diese E-Mail auf. Bis bald bei Afroboost!',
        'credit_label': 'Dein verbleibendes Guthaben',
        'credit_unit': 'Sessions',
        'cancel_title': '⚠️ Stornierungsbedingungen',
        'cancel_rule1': 'Stornierung bis 24h vor der Session möglich.',
        'cancel_rule2': 'Danach: Session nicht erstattungsfähig.',
        'practical_title': '🎒 Praktische Infos für deine Session',
        'practical_rule1': '🕒 Komme 15 Minuten früher',
        'practical_rule2': '👕 Sportkleidung',
        'practical_rule3': '🧻 Handtuch',
        'practical_rule4': '💧 Wasserflasche',
        'whatsapp_msg': ('✨ Afroboost — Buchung bestätigt ✨\n\n'
                         'Danke {name}! Referenz: {res_code}\n'
                         '🎟️ Dauerhafter Zugangscode: {access_code}\n'
                         '📅 {dates}\n\n'
                         'Für deine nächsten Sessions, gehe in den Afroboost-Chat und gib deinen Code ein.\n'
                         '⚠️ Buche mindestens 24h im Voraus, sonst ist die Session verloren.\n'
                         '⚠️ Stornierung nur bis 24h vorher — sonst keine Rückerstattung.\n\n'
                         '🎒 Bitte mitbringen: Sportkleidung, Handtuch, Wasserflasche\n'
                         '🕒 Komme 15 Min früher\n\n'
                         '💜 Die Tanzfläche wartet!'),
    },
}


def _detect_lang(user_lang: str = None, user_whatsapp: str = None) -> str:
    """Choisit la langue des messages (FR/EN/DE)."""
    if user_lang:
        ul = user_lang.lower().strip()[:2]
        if ul in _I18N:
            return ul
    # Heuristique par indicatif téléphonique
    if user_whatsapp:
        wa = user_whatsapp.replace(' ', '')
        if wa.startswith('+49'):
            return 'de'
        if wa.startswith('+44') or wa.startswith('+1'):
            return 'en'
    return 'fr'


async def _send_whatsapp_confirmation(to_whatsapp: str, user_name: str, reservation_data: dict, access_code: str, lang: str):
    """v158: Envoie une confirmation WhatsApp via Twilio."""
    if not _TWILIO_OK or not _TWILIO_SID or not _TWILIO_TOKEN:
        logger.info("[WHATSAPP] Twilio non configuré — WhatsApp non envoyé")
        return
    if not to_whatsapp:
        return
    try:
        t = _I18N.get(lang, _I18N['fr'])
        to_number = to_whatsapp.strip()
        if not to_number.startswith('whatsapp:'):
            # Assurer le format +XXX...
            if not to_number.startswith('+'):
                to_number = '+' + to_number.lstrip('0')
            to_number = 'whatsapp:' + to_number
        body = t['whatsapp_msg'].format(
            name=user_name or '',
            res_code=reservation_data.get('reservationCode', 'N/A'),
            access_code=access_code,
            dates=reservation_data.get('selectedDatesText', '') or reservation_data.get('courseName', '')
        )
        client = _TwilioClient(_TWILIO_SID, _TWILIO_TOKEN)
        await asyncio.to_thread(
            client.messages.create,
            from_=_TWILIO_WHATSAPP_FROM,
            to=to_number,
            body=body
        )
        logger.info(f"[WHATSAPP] Confirmation envoyée à {to_number}")
    except Exception as e:
        logger.warning(f"[WHATSAPP] Erreur envoi: {e}")


async def _send_reservation_email(user_email: str, user_name: str, reservation_data: dict, subscription_info: dict = None, user_lang: str = None, user_whatsapp: str = None):
    """v158: Envoie email + WhatsApp + crée/récupère le code AFRO-XXXX."""
    # 1. Récupérer/créer le code d'accès permanent (crée aussi l'utilisateur dans db.users)
    lang = _detect_lang(user_lang, user_whatsapp)
    access_code = await _ensure_user_access_code(user_email, user_name, user_whatsapp, lang)
    t = _I18N.get(lang, _I18N['fr'])

    # 2. Envoyer WhatsApp (en parallèle)
    if user_whatsapp:
        asyncio.create_task(_send_whatsapp_confirmation(user_whatsapp, user_name, reservation_data, access_code, lang))

    # 3. Envoyer email via Resend
    if not _RESEND_OK or not _RESEND_KEY:
        logger.warning("[EMAIL] Resend non disponible — email non envoyé")
        return False
    resend.api_key = _RESEND_KEY

    # V259: couleur de marque relue en base (un email ne lit pas les variables CSS)
    primary_color = await get_primary_color(db)
    primary_rgb = hex_to_rgb_triplet(primary_color)

    res_code = reservation_data.get("reservationCode", "N/A")
    offer = reservation_data.get("offerName", "Réservation")
    course = reservation_data.get("courseName", "")
    price = reservation_data.get("totalPrice", 0)
    promo = reservation_data.get("promoCode", "")
    dates_text = reservation_data.get("selectedDatesText", "")

    # Info abonnement
    sub_html = ""
    if subscription_info:
        remaining = subscription_info.get("remaining_sessions", "?")
        total = subscription_info.get("total_sessions", "?")
        # Option 3 : le code d'abonnement ne part plus par e-mail (identifiant interne).
        sub_html = f"""
        <div style="background:rgba(147,51,234,0.15);border:1px solid rgba(147,51,234,0.3);border-radius:8px;padding:14px;margin:16px 0;">
            <p style="margin:0;color:#a855f7;font-size:13px;">{t['credit_label']}</p>
            <p style="margin:4px 0 0;color:#fff;font-size:18px;font-weight:bold;">{remaining}/{total} {t['credit_unit']}</p>
        </div>"""

    # v158: Le QR code pointe vers la page chat avec le code d'accès pré-rempli
    # Sert de (1) billet d'entrée scannable par le coach ET (2) raccourci vers le chat
    chat_deeplink = f"https://afroboost.com/chat?code={quote(access_code)}&res={quote(res_code)}"
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=220x220&data={quote(chat_deeplink)}&format=png"

    html = f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0a0a0a;">
        <div style="background:linear-gradient(135deg,{primary_color},#8b5cf6);padding:24px;text-align:center;">
            <h1 style="color:white;margin:0;font-size:22px;">{t['hero_title']}</h1>
        </div>
        <div style="padding:24px;color:#fff;">
            <p style="color:#a855f7;font-size:16px;line-height:1.6;">
                {t['thanks'].format(name=user_name or '')}
            </p>
            <div style="background:rgba({primary_rgb}, 0.1);border:1px solid rgba({primary_rgb}, 0.3);border-radius:12px;padding:20px;margin:20px 0;">
                <table style="width:100%;color:#fff;font-size:14px;">
                    <tr><td style="color:#888;padding:6px 0;">{t['reference']}</td><td style="font-weight:bold;color:{primary_color};">{res_code}</td></tr>
                    <tr><td style="color:#888;padding:6px 0;">{t['offer']}</td><td>{offer}</td></tr>
                    {"<tr><td style='color:#888;padding:6px 0;'>" + t['course'] + "</td><td>" + course + "</td></tr>" if course else ""}
                    {"<tr><td style='color:#888;padding:6px 0;'>" + t['dates'] + "</td><td>" + dates_text + "</td></tr>" if dates_text else ""}
                    <tr><td style="color:#888;padding:6px 0;">{t['price']}</td><td style="font-weight:bold;">{price} CHF</td></tr>
                </table>
            </div>
            {sub_html}
            <!-- Code d'accès permanent -->
            <div style="background:linear-gradient(135deg,rgba({primary_rgb}, 0.2),rgba(139,92,246,0.2));border:2px solid {primary_color};border-radius:12px;padding:20px;margin:20px 0;text-align:center;">
                <p style="color:#fff;font-size:15px;font-weight:bold;margin:0 0 10px;">{t['access_title']}</p>
                <p style="color:{primary_color};font-size:26px;font-weight:bold;letter-spacing:2px;margin:10px 0;font-family:monospace;">{access_code}</p>
                <p style="color:rgba(255,255,255,0.7);font-size:12px;margin:8px 0 0;">{t['access_intro']}</p>
            </div>
            <!-- QR Code -->
            <div style="text-align:center;margin:24px 0;">
                <p style="color:#888;margin-bottom:12px;font-size:13px;">{t['qr_label']}</p>
                <img src="{qr_url}" alt="QR Code" width="160" height="160" style="background:white;padding:8px;border-radius:8px;display:block;margin:0 auto;"/>
                <p style="color:#a855f7;font-size:12px;margin-top:8px;">{t['qr_note']}</p>
            </div>
            <!-- Guide chat -->
            <div style="background:rgba(139,92,246,0.08);border:1px solid rgba(139,92,246,0.25);border-radius:12px;padding:18px;margin:20px 0;">
                <p style="color:#a78bfa;font-size:14px;font-weight:bold;margin:0 0 10px;">{t['guide_title']}</p>
                <p style="color:rgba(255,255,255,0.85);font-size:13px;line-height:1.8;margin:0;">
                    {t['guide_step1']}<br>
                    {t['guide_step2'].format(code=access_code)}<br>
                    {t['guide_step3']}<br>
                    {t['guide_step4']}
                </p>
            </div>
            <!-- Infos pratiques à apporter -->
            <div style="background:rgba(16,185,129,0.08);border:1px solid rgba(16,185,129,0.3);border-radius:12px;padding:18px;margin:20px 0;">
                <p style="color:#10b981;font-size:14px;font-weight:bold;margin:0 0 10px;">{t['practical_title']}</p>
                <p style="color:rgba(255,255,255,0.85);font-size:13px;line-height:1.9;margin:0;">
                    {t['practical_rule1']}<br>
                    {t['practical_rule2']}<br>
                    {t['practical_rule3']}<br>
                    {t['practical_rule4']}
                </p>
            </div>
            <!-- Règles d'annulation -->
            <div style="background:rgba(251,146,60,0.08);border:1px solid rgba(251,146,60,0.3);border-radius:12px;padding:18px;margin:20px 0;">
                <p style="color:#fb923c;font-size:14px;font-weight:bold;margin:0 0 10px;">{t['cancel_title']}</p>
                <p style="color:rgba(255,255,255,0.85);font-size:13px;line-height:1.8;margin:0;">
                    • {t['cancel_rule1']}<br>
                    • {t['cancel_rule2']}
                </p>
            </div>
            <!-- CTAs: les 2 boutons redirigent vers la page chat où l'utilisateur se connecte avec son code AFRO -->
            <div style="text-align:center;margin:28px 0;">
                <a href="{chat_deeplink}" style="display:inline-block;background:{primary_color};color:white;padding:14px 28px;text-decoration:none;border-radius:8px;font-weight:bold;font-size:14px;margin:4px;">{t['cta_chat']}</a>
                <a href="{chat_deeplink}" style="display:inline-block;background:rgba(139,92,246,0.3);color:white;padding:14px 28px;text-decoration:none;border-radius:8px;font-weight:bold;font-size:14px;margin:4px;border:1px solid rgba(139,92,246,0.5);">{t['cta_space']}</a>
            </div>
            <p style="color:#666;font-size:11px;text-align:center;margin-top:24px;">{t['footer']}</p>
        </div>
    </div>"""

    try:
        await asyncio.to_thread(resend.Emails.send, {
            "from": "Afroboost <notifications@afroboost.com>",
            "to": [user_email],
            "subject": f"{t['subject']} — {res_code}",
            "html": html
        })
        logger.info(f"[EMAIL] Confirmation envoyée à {user_email} pour {res_code} (code {access_code}, lang {lang})")
        # F1 — CE QUE CE `True` DIT, ET CE QU'IL NE DIT PAS.
        # Il dit : « Resend a ACCEPTE la demande d'envoi ». Il ne dit pas
        # « delivre » — la delivrabilite se lit chez le fournisseur, et ce lot
        # ne construit aucun suivi de delivrabilite. C'est deja infiniment plus
        # que ce qu'on affirmait avant : la fonction ne rendait RIEN, et
        # l'appelant ecrivait « envoye » quoi qu'il arrive, meme apres un echec
        # avale par le `except` ci-dessous.
        return True
    except Exception as e:
        logger.warning(f"[EMAIL] Erreur envoi confirmation: {e}")
        return False


# ===========================================================================
# N2 — L'E-MAIL DU COACH POUR UNE NOUVELLE RESERVATION
# ===========================================================================
#
# Le coach recevait un e-mail pour une souscription et pour une annulation, mais
# AUCUN pour une reservation. Ce n'etait pas une panne de livraison : le canal
# n'existait pas.
#
# ECRITE UNE SEULE FOIS, INJECTEE PAR LES DEUX ROUTES. `POST /reservations` et
# l'espace abonne appellent le meme moteur (`notifier_reservation_creee`) ; ils
# lui passent donc le meme envoyeur. Aucune duplication de gabarit.
#
# LE DESTINATAIRE EST LE COACH RESOLU, PAS UNE CONSTANTE. L'e-mail d'annulation
# (l.1078) envoie a `SUPER_ADMIN_EMAIL` : un coach partenaire ne recoit donc
# jamais les siens. On ne recopie pas ce defaut — le moteur a deja resolu le
# proprietaire via `resoudre_coach_de_reservation`, et c'est lui qu'on sert.
#
# CE QU'IL CONTIENT : participant, cours, date, heure, lieu, offre. Le prenom
# suffit a identifier ; l'e-mail du client est utile au coach pour repondre et
# figure deja dans son CRM. Aucun code d'acces, aucun jeton, aucun QR.
async def _send_coach_reservation_email(coach_email: str, reservation: dict) -> bool:
    """Previent le coach qu'une seance vient d'etre reservee. True si Resend accepte."""
    _dest = (coach_email or "").strip()
    if not _dest or "@" not in _dest:
        logger.warning("[EMAIL-COACH] destinataire invalide — e-mail non envoye")
        return False
    if not _RESEND_OK or not _RESEND_KEY:
        logger.warning("[EMAIL-COACH] Resend non disponible — e-mail non envoye")
        return False
    resend.api_key = _RESEND_KEY

    from html import escape as _esc
    _nom = _esc(str(reservation.get("userName") or "Un client").strip()[:60], quote=True)
    _mail = _esc(str(reservation.get("userEmail") or "").strip()[:120], quote=True)
    _cours = _esc(str(reservation.get("courseName")
                      or reservation.get("offerName") or "une seance")[:120], quote=True)
    _offre = _esc(str(reservation.get("offerName") or "")[:120], quote=True)
    _lieu = _esc(str(reservation.get("locationName")
                     or reservation.get("location") or "")[:160], quote=True)
    _code = _esc(str(reservation.get("reservationCode") or "")[:20], quote=True)
    try:
        _q = max(1, int(reservation.get("quantity") or 1))
    except (TypeError, ValueError):
        _q = 1

    # DATE ET HEURE DE L'OCCURRENCE RESERVEE, jamais celle du cours recurrent.
    # `datetime` porte l'instant exact choisi (ISO naif en heure suisse, cf.
    # V196) : une reservation du mercredi 19 ne doit pas annoncer « chaque
    # mercredi ». Lecture defensive — un format inattendu ne doit pas empecher
    # l'envoi, il se contente de ne pas embellir la date.
    _brut = str(reservation.get("datetime") or "")
    _quand = _brut[:16].replace("T", " a ")
    try:
        from datetime import datetime as _dt
        _JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
        _MOIS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet",
                 "aout", "septembre", "octobre", "novembre", "decembre"]
        _d = _dt.fromisoformat(_brut.replace("Z", "+00:00").split("+")[0])
        _quand = "%s %d %s a %02d:%02d" % (_JOURS[_d.weekday()], _d.day,
                                           _MOIS[_d.month - 1], _d.hour, _d.minute)
    except (ValueError, TypeError, IndexError):
        pass
    _quand = _esc(_quand, quote=True)

    try:
        primary_color = await get_primary_color(db, _dest)
    except Exception:
        primary_color = "#D91CD2"

    _lignes = [("Participant", _nom + (f" ({_mail})" if _mail else "")),
               ("Cours", _cours), ("Quand", _quand)]
    if _lieu:
        _lignes.append(("Lieu", _lieu))
    if _offre and _offre != _cours:
        _lignes.append(("Offre", _offre))
    if _q > 1:
        _lignes.append(("Places", str(_q)))
    if _code:
        _lignes.append(("Code reservation", _code))
    _bloc = "".join(
        f'<p style="color:#a1a1aa;font-size:12px;margin:10px 0 2px;">{_c}</p>'
        f'<p style="color:#fff;font-size:14px;margin:0;">{_v}</p>'
        for _c, _v in _lignes)

    _url = (os.environ.get("FRONTEND_URL") or "https://afroboost.com").rstrip("/")
    try:
        await asyncio.to_thread(resend.Emails.send, {
            "from": "Afroboost <notifications@afroboost.com>",
            "to": [_dest],
            "subject": f"Nouvelle réservation Afroboost — {reservation.get('courseName') or reservation.get('offerName') or 'séance'}",
            "html": f"""<div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;background:#0a0a0a;border-radius:12px;overflow:hidden;">
                <div style="background:{primary_color};padding:18px;text-align:center;">
                    <h2 style="color:#fff;margin:0;font-size:18px;">Nouvelle réservation</h2>
                </div>
                <div style="padding:20px;">{_bloc}
                    <p style="margin:22px 0 0;text-align:center;">
                        <a href="{_url}/" style="display:inline-block;background:{primary_color};color:#fff;padding:12px 26px;text-decoration:none;border-radius:10px;font-weight:bold;font-size:14px;">Voir mes réservations</a>
                    </p>
                </div>
            </div>"""
        })
        logger.info("[EMAIL-COACH] reservation %s annoncee a %s", _code or "?", _dest[:24])
        # Comme pour l'e-mail client : « Resend a ACCEPTE », pas « delivre ».
        return True
    except Exception as e:
        logger.warning("[EMAIL-COACH] envoi echoue: %s", e)
        return False


# v9.5.8: Liste des Super Admins
SUPER_ADMIN_EMAILS = [
    "contact.artboost@gmail.com",
    "afroboost.bassi@gmail.com"
]
SUPER_ADMIN_EMAIL = "contact.artboost@gmail.com"  # Legacy
# V244: etait "bassi_default" (sentinelle sans compte). Pointe desormais sur
# l'admin, coherent avec server.py — les replis coach_id inconnu lui reviennent.
DEFAULT_COACH_ID = SUPER_ADMIN_EMAILS[0]

def is_super_admin(email: str) -> bool:
    """Vérifie si l'email est celui d'un Super Admin"""
    return email and email.lower().strip() in [e.lower() for e in SUPER_ADMIN_EMAILS]

def get_coach_filter(email: str) -> dict:
    """Retourne le filtre MongoDB pour l'isolation des données coach"""
    if is_super_admin(email):
        return {}  # Super Admin voit tout
    return {"coach_id": email.lower().strip()}

# Router
reservation_router = APIRouter(tags=["reservations"])

# Variable db sera injectée depuis server.py
from api.routes.shared import get_primary_color, hex_to_rgb_triplet  # V259

db = None

def init_reservation_db(database):
    global db
    db = database

# === MODÈLES ===
class ReservationBase(BaseModel):
    userName: str
    userEmail: str
    userWhatsapp: Optional[str] = None
    userBirthday: Optional[str] = None  # V285: date de naissance format MM-DD (optionnel côté modèle)
    userLanguage: Optional[str] = None  # v158: langue pour email/WhatsApp (fr/en/de)
    courseName: Optional[str] = None
    courseTime: Optional[str] = None
    datetime: Optional[str] = None
    offerName: str
    totalPrice: float
    quantity: int = 1
    selectedDates: Optional[List[str]] = []
    selectedDatesText: Optional[str] = None
    selectedVariants: Optional[List[dict]] = []
    variantsText: Optional[str] = None
    isProduct: bool = False
    promoCode: Optional[str] = None
    discountCode: Optional[str] = None
    subscriptionId: Optional[str] = None  # v95: ID de l'abonnement utilisé
    source: Optional[str] = "website"
    type: Optional[str] = "ticket"
    coach_id: Optional[str] = None  # V206: accepter coach_id depuis le body (vitrine)
    # ESSAI-5a-1 : la SEULE chose que le client exprime. La version des
    # conditions, l'heure et l'etat filme du cours sont determines par le
    # serveur — le navigateur n'a voix au chapitre sur aucun des trois.
    terms_accepted: Optional[bool] = None
    courseId: Optional[str] = None

class ReservationCreate(ReservationBase):
    pass

class Reservation(ReservationBase):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    reservationCode: str = Field(default_factory=lambda: f"AF{uuid.uuid4().hex[:8].upper()}")
    validated: bool = False
    validatedAt: Optional[str] = None
    createdAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    shippingStatus: Optional[str] = "pending"
    trackingNumber: Optional[str] = None
    coach_id: Optional[str] = None

# === ENDPOINTS RÉSERVATIONS ===
# ═══════════════════════════════════════════════════════════════════════════
# A — L'ORIGINE ECONOMIQUE D'UNE RESERVATION, EN LECTURE SEULE
# ═══════════════════════════════════════════════════════════════════════════
#
# La carte du tableau de bord affichait le client, le cours, le code et le
# statut — mais ni l'offre utilisee, ni le moindre montant. `totalPrice` vaut 0
# sur toute reservation issue d'un forfait (c'est normal : la seance a ete payee
# a l'achat du pack, pas a la reservation), si bien que le prix ne s'affichait
# JAMAIS.
#
# L'argent ne vit pas sur la reservation. Il vit sur les deux documents jumeaux
# qui portent le droit — le forfait (`subscriptions`) et le code
# (`discount_codes`) — relies par `subscriptionId` et par `promoCode`.
#
# DEUX REQUETES POUR TOUTE LA PAGE, jamais une par ligne : la regle « pas de
# find_one dans une boucle » de ce projet vaut ici comme ailleurs. La casse est
# geree par COLLATION Mongo et non par une regex construite depuis une valeur
# stockee — `SHANNON2026` en base est ecrit `Shannon2026` sur son code, les deux
# doivent se rejoindre sans jamais fabriquer de motif.
#
# CE BLOC N'ECRIT RIEN. Il ne lit pas non plus `offers` : le prix du catalogue
# est celui d'AUJOURD'HUI, l'afficher en face d'un achat d'hier reecrirait
# l'histoire.
_A_COLLATION_INSENSIBLE = {"locale": "en", "strength": 2}


async def _a_enrichir_finance(reservations: list) -> list:
    """Ajoute a chaque reservation un objet `finance`. Jamais d'exception."""
    if not reservations:
        return reservations
    try:
        from api.routes.shared import a_finance_du_droit as _a_resoudre

        _ids, _codes = set(), set()
        for r in reservations:
            _sid = (r.get("subscriptionId") or "").strip()
            if _sid:
                _ids.add(_sid)
            for _c in (r.get("promoCode"), r.get("discountCode")):
                _c = (str(_c or "")).strip()
                if _c:
                    _codes.add(_c.upper())

        _subs, _dcs = [], []
        if _ids or _codes:
            _ou = []
            if _ids:
                _ou.append({"id": {"$in": sorted(_ids)}})
            if _codes:
                _ou.append({"code": {"$in": sorted(_codes)}})
            _subs = await db.subscriptions.find(
                {"$or": _ou},
                {"_id": 0, "id": 1, "code": 1, "offer_name": 1, "offer_price": 1,
                 "renewal_price": 1, "renewal_sessions": 1, "total_sessions": 1,
                 "remaining_sessions": 1, "used_sessions": 1, "status": 1,
                 "montant_encaisse": 1, "devise": 1, "origine_paiement": 1,
                 "seances_a_l_achat": 1},
            ).collation(_A_COLLATION_INSENSIBLE).to_list(500)
        if _codes:
            _dcs = await db.discount_codes.find(
                {"code": {"$in": sorted(_codes)}},
                {"_id": 0, "code": 1, "offerName": 1, "maxUses": 1, "stripe_amount": 1,
                 "total_paid": 1, "paid_currency": 1, "currency": 1, "session_id": 1,
                 "transaction_id": 1, "payment_method": 1, "source": 1,
                 "montant_encaisse": 1, "devise": 1, "origine_paiement": 1,
                 "seances_a_l_achat": 1},
            ).collation(_A_COLLATION_INSENSIBLE).to_list(500)

        _par_id = {s.get("id"): s for s in _subs if s.get("id")}
        _par_code = {}
        for s in _subs:
            _k = (str(s.get("code") or "")).strip().upper()
            if _k:
                _par_code.setdefault(_k, s)
        _codes_idx = {}
        for d in _dcs:
            _k = (str(d.get("code") or "")).strip().upper()
            if _k:
                _codes_idx.setdefault(_k, d)

        for r in reservations:
            _sid = (r.get("subscriptionId") or "").strip()
            _cle = (str(r.get("promoCode") or r.get("discountCode") or "")).strip().upper()
            _sub = _par_id.get(_sid) if _sid else None
            if _sub is None and _cle:
                _sub = _par_code.get(_cle)
            if not _cle and _sub:
                _cle = (str(_sub.get("code") or "")).strip().upper()
            r["finance"] = _a_resoudre(_sub, _codes_idx.get(_cle), r)
        return reservations
    except Exception as _err:
        # Une reservation reste lisible sans son bloc financier. Ce qui n'est
        # jamais acceptable, c'est de faire echouer la liste du coach pour ca.
        logger.warning("[A] Enrichissement financier ignore — %s: %s",
                       type(_err).__name__, _err)
        return reservations


@reservation_router.get("/reservations")
async def get_reservations(request: Request, page: int = 1, limit: int = 20, all_data: bool = False):
    """Get reservations with pagination - Filtré par coach_id"""
    caller_email = request.headers.get("X-User-Email", "").lower().strip()

    # V443 — UNE ABSENCE D'IDENTITÉ N'EST PAS UNE LISTE VIDE.
    #
    # Cette route répondait `200 {"data": [], "pagination": {"total": 0}}` quand
    # aucune identité n'était présentée : le sentinelle `{"coach_id":
    # "__no_access__"}` fabriquait une requête qui ne peut rien remonter. Vu du
    # dashboard, un refus d'accès et un carnet de réservations vide étaient donc
    # EXACTEMENT le même écran — sans message, sans erreur, sans rien dans la
    # console. Le coach a vu « aucune réservation » alors que la base en contenait
    # 128, toutes à son nom.
    #
    # Une liste vide est une AFFIRMATION (« il n'y a rien »). On ne la fait plus
    # quand on n'est pas en mesure de la vérifier : on refuse, explicitement.
    # C'est le principe déjà retenu par V2-0 sur quatre autres routes — « refuser
    # au lieu de filtrer ».
    #
    # ⚠️ PÉRIMÈTRE VOLONTAIREMENT ÉTROIT : la STRATÉGIE d'authentification n'est
    # PAS touchée. L'identité reste exactement ce qu'elle était avant — l'en-tête
    # `X-User-Email`, avec les mêmes droits, le même super-admin, le même
    # filtrage par `coach_id`. Aucun JWT n'est exigé ici, aucune garde n'est
    # ajoutée ni retirée : un appelant qui passait AVANT passe encore, à
    # l'identique. Seule change la réponse faite à celui qui ne présentait RIEN,
    # et qui recevait un mensonge poli. Rendre cette route JWT-strict est un lot
    # distinct (P0-AUTH-COHERENCE), qui devra d'abord PROUVER — appel réel à
    # l'appui — que le chemin légitime du propriétaire émet bien un jeton signé
    # (règle V310c : un durcissement non prouvé a déjà vidé ce dashboard une fois).
    if not caller_email:
        raise HTTPException(status_code=403, detail="Authentification coach requise")

    # V206: Super admin voit tout (y compris bassi_default)
    # V244: isolation stricte — le sentinelle bassi_default a ete migre, plus aucun doc ne le porte.
    base_query = {} if is_super_admin(caller_email) else {"coach_id": caller_email}
    projection = {
        "_id": 0, "id": 1, "reservationCode": 1, "userName": 1, "userEmail": 1,
        "userWhatsapp": 1, "courseName": 1, "courseTime": 1, "datetime": 1,
        "offerName": 1, "totalPrice": 1, "quantity": 1, "validated": 1,
        "validatedAt": 1, "createdAt": 1, "selectedDates": 1, "selectedDatesText": 1,
        "selectedVariants": 1, "variantsText": 1, "isProduct": 1, "shippingStatus": 1,
        "trackingNumber": 1, "promoCode": 1, "source": 1, "type": 1,
        # V226: sans shippingAddress dans la projection, la liste paginee de
        # l'onglet Reservations (appel principal du dashboard coach) ne renvoyait
        # jamais l'adresse: le coach ne pouvait pas savoir ou expedier.
        # selectedVariants / variantsText y etaient deja (ligne au-dessus).
        "shippingAddress": 1,
        # V191: Casques Silent Disco + accompagnants (visible dans le dashboard coach)
        "headphone_status": 1, "headphone_updated_at": 1,
        "guests": 1, "guest_headphones": 1,
        # A : sans ces trois champs, la liste paginee — l'appel PRINCIPAL du
        # tableau de bord — ne pouvait meme pas savoir a quel forfait une
        # reservation se rattachait. Le badge « (abo lie) » de la carte, ecrit
        # depuis longtemps, ne s'affichait donc jamais sur cet ecran.
        "subscriptionId": 1, "discountCode": 1, "courseId": 1,
    }
    if all_data:
        reservations = await db.reservations.find(base_query, {"_id": 0}).sort("createdAt", -1).to_list(10000)
    else:
        skip = (page - 1) * limit
        reservations = await db.reservations.find(base_query, projection).sort("createdAt", -1).skip(skip).limit(limit).to_list(limit)
    total_count = await db.reservations.count_documents(base_query)
    # A : l'origine economique de chaque ligne — deux requetes pour toute la
    # page, aucune ecriture, aucune lecture du catalogue.
    await _a_enrichir_finance(reservations)
    for res in reservations:
        if isinstance(res.get('createdAt'), str):
            res['createdAt'] = datetime.fromisoformat(res['createdAt'].replace('Z', '+00:00'))
    return {"data": reservations, "pagination": {"page": page, "limit": limit, "total": total_count, "pages": (total_count + limit - 1) // limit}}

@reservation_router.post("/reservations", response_model=Reservation)
async def create_reservation(reservation: ReservationCreate, request: Request):
    """Créer une réservation - Vérifie la validité du code et déduit 1 séance v11.4"""
    promo_code = reservation.promoCode or reservation.discountCode
    user_email = reservation.userEmail.lower().strip() if reservation.userEmail else ""

    # === V430 : un code assigné n'appartient qu'à son propriétaire ===
    #
    # Ce chemin ne vérifiait RIEN : un inconnu qui connaissait un code assigné
    # faisait grimper son compteur `used` (plus bas) — il brûlait le quota d'un
    # client sans jamais toucher son abonnement, la déduction étant, elle, filtrée
    # par `email`. Les membres d'un code de groupe restent autorisés : 7
    # réservations réelles en production passent par là.
    #
    # ⚠️ PLACÉ ICI, AVANT TOUTE ÉCRITURE. Refuser plus bas — au moment de
    # l'incrément — laisserait la séance DÉJÀ déduite de l'abonnement : le client
    # perdrait une séance sans obtenir de réservation.
    if promo_code:
        _v430_doc = await db.discount_codes.find_one(
            {"code": {"$regex": f"^{re.escape(promo_code)}$", "$options": "i"}, "active": True},
            {"_id": 0, "code": 1, "assignedEmail": 1, "multi_member": 1},
        )
        if _v430_doc:
            from api.routes.shared import (
                email_autorise_pour_code as _v430_autorise,
                V430_MESSAGE_REFUS as _V430_MSG,
            )
            _v430_ok, _v430_motif = await _v430_autorise(db, _v430_doc, user_email)
            if not _v430_ok:
                logger.warning(
                    f"[V430] Reservation refusee : code {promo_code} ({_v430_motif})"
                )
                raise HTTPException(status_code=403, detail=_V430_MSG)

    # === v158: Règle 24h à l'avance pour les séances suivantes d'un pack ===
    # La 1ère séance (achat initial) peut être n'importe quand.
    # Les séances suivantes (via abonnement actif existant) doivent être >= 24h dans le futur.
    subscription_id_early = getattr(reservation, 'subscriptionId', None)
    selected_dates = reservation.selectedDates or []
    if user_email and subscription_id_early and selected_dates:
        existing_sub = await db.subscriptions.find_one(
            {"id": subscription_id_early, "email": user_email, "status": "active"},
            {"_id": 0, "used_sessions": 1}
        )
        if existing_sub and (existing_sub.get("used_sessions", 0) or 0) >= 1:
            # C'est une séance suivante du pack → exiger 24h à l'avance
            try:
                first_date = selected_dates[0]
                # Format attendu : ISO string. On accepte aussi les dates simples
                dt = datetime.fromisoformat(first_date.replace('Z', '+00:00')) if 'T' in first_date else datetime.fromisoformat(first_date + 'T00:00:00+00:00')
                delta_hours = (dt - datetime.now(timezone.utc)).total_seconds() / 3600.0
                if delta_hours < 24:
                    raise HTTPException(
                        status_code=400,
                        detail="Les séances suivantes de votre pack doivent être réservées au moins 24h à l'avance."
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.warning(f"[RESERVATION] Impossible de parser la date {selected_dates}: {e}")
                # Par sécurité, on laisse passer si le format est ambigu

    # === v95/v158.8: VÉRIFIER ET DÉDUIRE UNE SÉANCE ===
    # v158.8: Ne déduire du pack QUE si l'utilisateur utilise EXPLICITEMENT son abonnement
    # (via subscriptionId ou promoCode qui est son code de pack). Pas d'auto-déduction
    # pour les réservations d'essai gratuit, achats à l'unité, etc.
    subscription_id = getattr(reservation, 'subscriptionId', None)
    offer_price = float(getattr(reservation, 'totalPrice', 0) or 0)
    # Une reservation "essai gratuit" ou "achat à l'unité" NE DOIT PAS déduire d'un pack existant
    # V174: Fix déduction séances abonnés - on déduit dès qu'un abonnement OU code promo est fourni (peu importe le prix qui est forcément 0 pour un abonné)
    is_free_or_single_purchase = (not subscription_id and not promo_code)

    if user_email and not is_free_or_single_purchase:
        # Seulement si subscriptionId OU promoCode explicitement fourni
        if subscription_id:
            query = {"id": subscription_id, "email": user_email, "status": "active"}
        else:
            query = {"email": user_email, "status": "active", "code": promo_code.upper().strip()}

        subscription = await db.subscriptions.find_one(query, {"_id": 0})
        
        if subscription:
            remaining = subscription.get("remaining_sessions", 0)
            # V393 — expiré OU épuisé -> refus. Ce chemin ne testait que l'épuisement :
            # un forfait périmé restait réservable depuis la vitrine et le chat.
            from api.routes.shared import forfait_utilisable as _v393_ok
            _ok, _pourquoi = _v393_ok(subscription, 1)
            if not _ok:
                logger.warning(f"[V393] Reservation refusee pour {user_email} : {_pourquoi}")
                raise HTTPException(status_code=400, detail=_pourquoi)
            
            # Déduire 1 séance
            new_remaining = remaining - 1
            new_used = subscription.get("used_sessions", 0) + 1
            
            update_data = {
                "remaining_sessions": new_remaining,
                "used_sessions": new_used,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            if new_remaining <= 0:
                update_data["status"] = "completed"
            
            await db.subscriptions.update_one(
                {"id": subscription.get("id")},
                {"$set": update_data}
            )
            # v95: Mémoriser le subscriptionId utilisé pour la traçabilité
            subscription_id = subscription.get("id")
            logger.info(f"[RESERVATION] Séance déduite: {user_email} - {new_remaining} restantes (sub: {subscription_id})")

            # V180: Notif push si reste 2 séances ou moins
            if new_remaining == 2:
                try:
                    await _send_push_to_email(
                        user_email,
                        "⚠️ Plus que 2 séances Afroboost",
                        "Pense à renouveler ton abonnement pour continuer à danser !",
                        {"type": "low_sessions", "remaining": 2}
                    )
                except Exception as _e:
                    logger.warning(f"[PUSH-V180] notif 2 séances échec: {_e}")
            elif new_remaining == 0:
                try:
                    await _send_push_to_email(
                        user_email,
                        "🎯 Dernière séance utilisée",
                        "Renouvelle ton abonnement pour ne pas manquer le prochain cours !",
                        {"type": "no_sessions", "remaining": 0}
                    )
                except Exception as _e:
                    logger.warning(f"[PUSH-V180] notif 0 séances échec: {_e}")

    if promo_code:
        discount = await db.discount_codes.find_one({"code": {"$regex": f"^{re.escape(promo_code)}$", "$options": "i"}, "active": True}, {"_id": 0})
        if discount:
            # V430 : l'autorisation a été vérifiée EN TÊTE de route, avant toute
            # écriture. Rien à refaire ici.
            # v95: Incrémenter le compteur d'utilisation du code promo
            await db.discount_codes.update_one(
                {"id": discount.get("id")},
                {"$inc": {"used": 1}}
            )
            logger.info(f"[RESERVATION] Code promo {promo_code} utilisé (compteur incrémenté)")
        else:
            logger.info(f"[RESERVATION] Code promo invalide: {promo_code}")

    # V206: Créer la réservation — coach_id depuis header OU body OU défaut
    caller_email = request.headers.get("X-User-Email", "").lower().strip() if request else None
    # Priorité: 1) header X-User-Email, 2) body coach_id, 3) "bassi_default"
    effective_coach_id = caller_email if caller_email and not is_super_admin(caller_email) else None
    if not effective_coach_id and reservation.coach_id:
        effective_coach_id = reservation.coach_id.lower().strip()
    if not effective_coach_id:
        effective_coach_id = DEFAULT_COACH_ID  # V244
    # ESSAI-5a-1 — la preuve d'acceptation, AVANT la moindre ecriture.
    # Sans conditions publiees, `t1_preuve` rend un dict vide et rien n'est exige.
    try:
        from api.server import t1_preuve as _t1_preuve
        _t1_champs = await _t1_preuve(reservation.terms_accepted,
                                      reservation.courseId or "", effective_coach_id)
    except HTTPException:
        raise
    except Exception as _t1err:
        logger.warning("[T1] preuve d'acceptation ignoree : %s", _t1err)
        _t1_champs = {}

    reservation_data = Reservation(
        userName=reservation.userName, userEmail=reservation.userEmail, userWhatsapp=reservation.userWhatsapp,
        userLanguage=reservation.userLanguage,
        courseName=reservation.courseName, courseTime=reservation.courseTime, datetime=reservation.datetime,
        offerName=reservation.offerName, totalPrice=reservation.totalPrice, quantity=reservation.quantity,
        selectedDates=reservation.selectedDates, selectedDatesText=reservation.selectedDatesText,
        selectedVariants=reservation.selectedVariants, variantsText=reservation.variantsText,
        isProduct=reservation.isProduct, promoCode=promo_code, subscriptionId=subscription_id,
        source=reservation.source, type=reservation.type,
        coach_id=effective_coach_id
    ).model_dump()
    reservation_data.update(_t1_champs)
    if reservation.courseId:
        reservation_data["courseId"] = reservation.courseId
    await db.reservations.insert_one(reservation_data)
    reservation_data.pop("_id", None)
    logger.info(f"[RESERVATION] Créée: {reservation_data.get('reservationCode')} pour {user_email}")

    # C9-A : `trial_booked` — émis APRÈS l'insertion réelle, jamais au clic.
    # `posthog_capture` n'échoue jamais ; ce try n'est qu'une ceinture de plus.
    try:
        from api.routes.shared import posthog_capture as _c9
        from api.routes.shared import essai2_est_essai as _e2_est_essai
        # ESSAI-2 : `trial_booked` s'appelle « trial » mais couvre TOUTE
        # reservation. Sans ce drapeau, l'etape « essai reserve » du funnel est
        # indistinguable d'une reservation d'abonne payant. La reponse se lit
        # dans la base — le code d'acces mene-t-il a un octroi gratuit — jamais
        # dans le nom de l'offre.
        _e2_essai = await _e2_est_essai(db, reservation_data)
        await _c9("trial_booked", email=user_email, props={
            "course_id": getattr(reservation, "courseId", None) or reservation_data.get("courseId"),
            "offer_name_present": bool(reservation_data.get("offerName")),
            "total_price": float(reservation_data.get("totalPrice") or 0),
            "quantity": int(reservation_data.get("quantity") or 1),
            "is_product": bool(reservation_data.get("isProduct")),
            "has_promo": bool(promo_code),
            "source": reservation_data.get("source") or "website",
            "is_free_trial": _e2_essai,
        })
    except Exception as _c9e:
        logger.warning(f"[C9] trial_booked ignoré: {_c9e}")

    # V285: enregistrer la date de naissance (MM-DD) dans le profil, pour les
    # anniversaires. Optionnel — n'echoue jamais la reservation.
    try:
        _bday = (reservation.userBirthday or "").strip()
        if user_email and _bday:
            await db.users.update_one(
                {"email": user_email},
                {"$set": {"birthday": _bday, "birthday_updated_at": datetime.now(timezone.utc).isoformat()}},
                upsert=False
            )
            await db.chat_participants.update_many(
                {"email": user_email},
                {"$set": {"birthday": _bday}}
            )
            logger.info(f"[V285] Anniversaire depuis réservation: {user_email} -> {_bday}")
    except Exception as _e:
        logger.warning(f"[V285] Enregistrement anniversaire ignoré: {_e}")

    # v96/v158: Envoyer email + WhatsApp de confirmation avec code AFRO-XXXX
    if user_email:
        sub_info = None
        if subscription_id:
            sub_info = await db.subscriptions.find_one({"id": subscription_id}, {"_id": 0})
        # === reservation_created : evenement UNIQUE, client + coach ===
        # L'envoi ne depend plus du chemin : le meme helper sert ici et dans
        # l'espace abonne. Il est idempotent par canal et NON BLOQUANT.
        from api.routes.shared import notifier_reservation_creee as _rc_notifier

        async def _rc_push_coach(_email, _titre, _msg, _data=None):
            # Import PARESSEUX : `server.py` importe ce module au chargement,
            # un import en tete de fichier creerait un cycle. On prend
            # `send_push_by_email` — celui qui porte V433 (tri des abonnements)
            # et V434 (TTL 3600) — et jamais `_send_push_to_email`.
            from api.server import send_push_by_email as _envoyer
            return await _envoyer(_email, _titre, _msg, _data)

        async def _rc_email_client(_resa):
            # F1 — ON PROPAGE LE VERDICT, ON NE LE FABRIQUE PLUS.
            # Ce `return True` etait EN DUR : `_send_reservation_email` ne
            # rendait rien et avalait ses erreurs, donc le bilan ecrivait
            # « envoye » meme quand Resend etait absent ou refusait. L'indicateur
            # ne valait rien. Il vaut desormais ce que le fournisseur a repondu.
            return bool(await _send_reservation_email(
                user_email, reservation.userName, _resa, sub_info,
                user_lang=reservation.userLanguage,
                user_whatsapp=reservation.userWhatsapp
            ))

        asyncio.create_task(_rc_notifier(
            db, reservation_data,
            envoyer_email_client=_rc_email_client,
            envoyer_push_coach=_rc_push_coach,
            # N2 : le coach est resolu PAR LE MOTEUR et passe en premier
            # argument — on ne devine pas le destinataire ici.
            envoyer_email_coach=_send_coach_reservation_email,
        ))

    # V180: Notification push à l'abonné après réservation réussie
    if user_email:
        try:
            course_name = (reservation.courseName or reservation.offerName or "ton cours")
            course_dt = reservation.datetime or ""
            asyncio.create_task(_send_push_to_email(
                user_email,
                "🎉 Réservation confirmée",
                "Ta place pour " + course_name + " est réservée. À très vite !",
                {"type": "reservation_confirmed", "courseName": course_name, "datetime": course_dt}
            ))
        except Exception as _e:
            logger.warning(f"[PUSH-V180] notif réservation échec: {_e}")

    # V206 RETIRE : ce bloc poussait vers une CONSTANTE EN DUR
    # (`COACH_EMAIL = "contact.artboost@gmail.com"`), ce qui aurait notifie Bassi
    # pour la reservation d'un autre coach — 58 reservations concernees. Il
    # utilisait en plus `_send_push_to_email`, l'implementation SANS V433 (tri)
    # ni V434 (TTL), qui desactive TOUS les abonnements d'un participant sur un
    # seul 404/410. Le helper `notifier_reservation_creee` s'en charge desormais,
    # avec le coach REELLEMENT resolu et `send_push_by_email`.

    return reservation_data

@reservation_router.put("/reservations/{reservation_id}/tracking")
async def update_reservation_tracking(reservation_id: str, request: Request):
    """Met à jour les informations de suivi d'une réservation"""
    body = await request.json()
    tracking_number = body.get("trackingNumber")
    shipping_status = body.get("shippingStatus", "shipped")
    result = await db.reservations.update_one(
        {"id": reservation_id},
        {"$set": {"trackingNumber": tracking_number, "shippingStatus": shipping_status, "updatedAt": datetime.now(timezone.utc).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Réservation non trouvée")
    updated = await db.reservations.find_one({"id": reservation_id}, {"_id": 0})
    return {"success": True, "reservation": updated}

async def _c9_presence(reservation: dict, etait_deja_validee: bool):
    """C9-A — `attendance_checked_in`, et `second_class_attended` le cas échéant.

    APPELÉ PAR LES TROIS CHEMINS DE VALIDATION (scan direct, staff, groupe) : il
    n'y a pas un seul endroit où une présence se confirme, et en oublier un
    rendrait le funnel faux sans que rien ne le signale.

    `etait_deja_validee` porte l'idempotence. `/reservations/{code}/validate`
    n'a AUCUNE garde de re-scan : sans ce drapeau, repasser le même QR gonflerait
    les présences. On n'émet donc que sur la TRANSITION non-validé -> validé.

    La 2e présence est comptée sur les réservations `validated` de la même
    adresse. Fiabilité vérifiée sur les données de production : 9 présences sur
    9 portent un e-mail ET un `validatedAt`, donc le rang est déterminable.
    Aucune présence anonyme n'existe aujourd'hui ; si une apparaissait, elle
    serait simplement ignorée (pas d'identifiant -> pas d'événement).
    """
    try:
        if etait_deja_validee:
            return
        from api.routes.shared import posthog_capture as _c9
        email = (reservation.get("userEmail") or "").strip().lower()
        if not email:
            return
        rang = await db.reservations.count_documents({"userEmail": email, "validated": True})
        # ESSAI-2 : c'est CETTE etape qui fait la valeur du funnel — une
        # presence reelle, confirmee par le coach. Encore faut-il savoir si
        # elle honore un essai gratuit ou une seance deja payee.
        from api.routes.shared import essai2_est_essai as _e2_est_essai
        _e2_essai = await _e2_est_essai(db, reservation)
        await _c9("attendance_checked_in", email=email, props={
            "course_id": reservation.get("courseId"),
            "attendance_rank": rang,
            "is_product": bool(reservation.get("isProduct")),
            "is_free_trial": _e2_essai,
        })
        if rang == 2:
            await _c9("second_class_attended", email=email, props={
                "course_id": reservation.get("courseId"),
            })
    except Exception as _e:
        logger.warning(f"[C9] presence ignoree: {_e}")


@reservation_router.post("/reservations/{reservation_code}/validate")
async def validate_reservation(reservation_code: str, request: Request):
    """Validate a reservation by QR code scan

    R11 — MEME GARDE QUE `/qr/scan-validate`, ET C'EST INDISPENSABLE.
    Fermer le scanner en laissant cette route ouverte n'aurait rien ferme du
    tout : elle produit EXACTEMENT la meme ecriture (`validated` sur une
    reservation) a partir du seul code de reservation. Mesure du 19/08/2026 sur
    la production : `POST /api/reservations/<code>/validate` sans aucun en-tete
    repondait 404 « Réservation non trouvée » — donc la route etait ATTEINTE,
    et un vrai code aurait ete validé.
    Aucun ecran ne l'appelle (verifie sur tout `frontend/src`) : la fermer ne
    retire donc aucun parcours a personne.
    """
    _scanneur = await _r11_scanneur(request)
    reservation = await db.reservations.find_one({"reservationCode": reservation_code}, {"_id": 0})
    if not reservation:
        raise HTTPException(status_code=404, detail="Réservation non trouvée")
    _c9_deja = bool(reservation.get("validated"))   # C9-A : lu AVANT l'écriture
    if _c9_deja:
        # Comportement inchange : on renvoie le meme succes qu'avant, sans
        # reecrire l'horodatage ni reemettre d'evenement.
        return {"success": True, "message": "Réservation validée", "reservation": reservation}
    await _a0_marquer_presente(reservation, _scanneur)
    return {"success": True, "message": "Réservation validée", "reservation": reservation}

@reservation_router.delete("/reservations/{reservation_id}")
async def delete_reservation(reservation_id: str):
    """Supprime une réservation et recrédite la séance à l'abonné si applicable — V216"""
    # Récupérer la réservation avant suppression pour recréditer
    reservation = await db.reservations.find_one(
        {"$or": [{"id": reservation_id}, {"reservationCode": reservation_id}]},
        {"_id": 0}
    )
    if not reservation:
        raise HTTPException(status_code=404, detail="Réservation introuvable")

    # Recréditer la séance si l'abonné avait un code promo / abonnement
    promo_code = (reservation.get("promoCode") or "").strip().upper()
    subscription_id = (reservation.get("subscriptionId") or "").strip()
    user_email = (reservation.get("userEmail") or "").strip().lower()
    recredited = False

    logger.info(f"[CANCEL] Tentative annulation: res={reservation_id} email={user_email} promo={promo_code} subId={subscription_id}")

    if user_email:
        sub = None
        # V216: Recherche par subscriptionId d'abord (plus fiable)
        if subscription_id:
            sub = await db.subscriptions.find_one(
                {"id": subscription_id, "status": {"$in": ["active", "completed"]}},
                {"_id": 0}
            )
            logger.info(f"[CANCEL] Recherche par subscriptionId={subscription_id}: {'trouvé' if sub else 'non trouvé'}")

        # Fallback: recherche par email + code promo
        if not sub and promo_code and promo_code != "N/A":
            sub = await db.subscriptions.find_one(
                {"email": user_email, "code": promo_code, "status": {"$in": ["active", "completed"]}},
                {"_id": 0}
            )
            logger.info(f"[CANCEL] Recherche par email+code: {'trouvé' if sub else 'non trouvé'}")

        # V216: Fallback ultime — chercher par email seul (un seul abonnement actif)
        if not sub and promo_code and promo_code != "N/A":
            sub = await db.subscriptions.find_one(
                {"email": user_email, "status": {"$in": ["active", "completed"]}},
                {"_id": 0}
            )
            if sub:
                logger.info(f"[CANCEL] Trouvé par email seul: code={sub.get('code')} remaining={sub.get('remaining_sessions')}")

        if sub:
            new_remaining = sub.get("remaining_sessions", 0) + 1
            new_used = max(0, sub.get("used_sessions", 0) - 1)
            update_data = {
                "remaining_sessions": new_remaining,
                "used_sessions": new_used,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            # Si le statut était "completed", le remettre à "active"
            if sub.get("status") == "completed":
                update_data["status"] = "active"
            await db.subscriptions.update_one(
                {"id": sub.get("id")},
                {"$set": update_data}
            )
            recredited = True
            logger.info(f"[CANCEL] Séance recréditée: {user_email} - {new_remaining} restantes (sub: {sub.get('id')})")
        else:
            logger.warning(f"[CANCEL] Aucun abonnement trouvé pour {user_email} / {promo_code} — pas de recrédit")

    # Supprimer la réservation
    await db.reservations.delete_one(
        {"$or": [{"id": reservation_id}, {"reservationCode": reservation_id}]}
    )
    logger.info(f"[CANCEL] Réservation {reservation_id} supprimée — recredited={recredited}")

    # V216: Notifier le coach par email + sauvegarder le log d'annulation
    user_name = reservation.get("userName", user_email)
    course_name = reservation.get("courseName") or reservation.get("offerName") or "cours"
    course_date = reservation.get("datetime") or reservation.get("selectedDatesText") or ""
    res_code = reservation.get("reservationCode", reservation_id)

    # Sauvegarder l'annulation dans notifications collection
    try:
        await db.notifications.insert_one({
            "id": f"cancel_{reservation_id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "type": "reservation_cancelled",
            "title": f"❌ Annulation: {user_name}",
            "message": f"{user_name} a annulé sa réservation pour {course_name} ({course_date}). Code: {res_code}. Séance recréditée: {'Oui' if recredited else 'Non'}.",
            "user_email": user_email,
            "reservation_code": res_code,
            "recredited": recredited,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "read": False,
            "coach_id": reservation.get("coach_id", DEFAULT_COACH_ID),  # V244
        })
    except Exception as _e:
        logger.warning(f"[CANCEL] Erreur sauvegarde notification: {_e}")

    # Envoyer email au coach
    try:
        if _RESEND_OK and _RESEND_KEY:
            import resend as _resend_lib
            _resend_lib.api_key = _RESEND_KEY
            await asyncio.to_thread(_resend_lib.Emails.send, {
                "from": "Afroboost <notifications@afroboost.com>",
                "to": [SUPER_ADMIN_EMAIL],
                "subject": f"❌ Annulation: {user_name} - {course_name}",
                "html": f"""<div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto;background:#0a0a0a;color:#fff;border-radius:16px;overflow:hidden;">
                    <div style="background:linear-gradient(135deg,#ef4444,#dc2626);padding:20px;text-align:center;">
                        <h2 style="color:white;margin:0;font-size:18px;">❌ Réservation annulée</h2>
                    </div>
                    <div style="padding:24px;">
                        <p style="color:#e2e8f0;font-size:14px;margin:0 0 12px;">
                            <strong>{user_name}</strong> ({user_email}) a annulé sa réservation.
                        </p>
                        <div style="background:rgba(255,255,255,0.05);border-radius:10px;padding:14px;margin:0 0 12px;">
                            <p style="color:#a78bfa;font-size:12px;margin:0 0 4px;">COURS</p>
                            <p style="color:white;font-size:14px;margin:0 0 10px;">{course_name}</p>
                            <p style="color:#a78bfa;font-size:12px;margin:0 0 4px;">DATE</p>
                            <p style="color:white;font-size:14px;margin:0 0 10px;">{course_date}</p>
                            <p style="color:#a78bfa;font-size:12px;margin:0 0 4px;">CODE RÉSA</p>
                            <p style="color:white;font-size:14px;margin:0;">{res_code}</p>
                        </div>
                        <p style="color:{'#22c55e' if recredited else '#f87171'};font-size:13px;margin:0;">
                            {"✅ Séance recréditée" if recredited else "⚠️ Pas de recrédit (pas d abonnement trouvé)"}
                        </p>
                    </div>
                </div>"""
            })
            logger.info(f"[CANCEL] Email notification envoyé au coach pour {res_code}")
    except Exception as _e:
        logger.warning(f"[CANCEL] Erreur envoi email coach: {_e}")

    return {"success": True, "recredited": recredited}


# V185 F4 + V186 fix + V188: Suivi des casques (Silent Disco)
async def _update_headphone_impl(reservation_id: str, request: Request):
    """V188: Met à jour le statut du casque audio (Silent Disco).
    Valeurs acceptées : null, 'taken', 'returned'.
    - Si body.guest_index est absent/None → met à jour headphone_status (abonné principal)
    - Si body.guest_index est un entier ≥ 0 → met à jour guest_headphones[index]
    V186 : lookup robuste (id OU reservationCode), parsing tolérant du body.
    """
    body = {}
    try:
        raw = await request.body()
        if raw:
            import json as _json
            body = _json.loads(raw.decode("utf-8"))
    except Exception:
        body = {}

    status = body.get("status") if isinstance(body, dict) else None
    if isinstance(status, str):
        status = status.strip().lower() or None
    if status not in (None, "", "taken", "returned"):
        raise HTTPException(status_code=400, detail=f"Statut casque invalide: {status!r}")
    normalized = status if status else None

    # V188: index de l'accompagnant (None = abonné principal)
    raw_index = body.get("guest_index") if isinstance(body, dict) else None
    guest_index = None
    if raw_index is not None:
        try:
            guest_index = int(raw_index)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"guest_index invalide: {raw_index!r}")
        if guest_index < 0 or guest_index > 19:
            raise HTTPException(status_code=400, detail="guest_index hors borne (0-19)")

    # V186: lookup robuste — id de doc OU reservationCode
    filter_doc = {"$or": [{"id": reservation_id}, {"reservationCode": reservation_id}]}
    reservation = await db.reservations.find_one(
        filter_doc,
        {"_id": 0, "id": 1, "reservationCode": 1, "quantity": 1, "guests": 1, "guest_headphones": 1}
    )
    if not reservation:
        raise HTTPException(status_code=404, detail=f"Réservation introuvable: {reservation_id}")

    now_iso = datetime.now(timezone.utc).isoformat()

    if guest_index is None:
        # Abonné principal
        update_payload = {"headphone_status": normalized, "headphone_updated_at": now_iso}
        await db.reservations.update_one(filter_doc, {"$set": update_payload})
        logger.info(f"[V188 HEADPHONE] {reservation_id} principal → {normalized}")
        return {
            "success": True,
            "reservation_id": reservation_id,
            "headphone_status": normalized,
            "guest_index": None,
        }

    # V188: Accompagnant — vérifier qu'il y a bien une place à cet index
    quantity = int(reservation.get("quantity") or 1)
    max_guests = max(0, quantity - 1)
    if guest_index >= max_guests:
        raise HTTPException(
            status_code=400,
            detail=f"guest_index {guest_index} hors borne pour cette réservation ({max_guests} accompagnant(s))"
        )

    # S'assurer que guest_headphones existe et a la bonne longueur, puis mettre à jour l'index
    existing = reservation.get("guest_headphones")
    if not isinstance(existing, list) or len(existing) < max_guests:
        # Initialiser/étendre la liste à max_guests entrées (None par défaut)
        padded = list(existing) if isinstance(existing, list) else []
        while len(padded) < max_guests:
            padded.append(None)
        padded[guest_index] = normalized
        await db.reservations.update_one(
            filter_doc,
            {"$set": {"guest_headphones": padded, "headphone_updated_at": now_iso}}
        )
    else:
        # Mise à jour ciblée de l'index (notation pointée Mongo)
        await db.reservations.update_one(
            filter_doc,
            {"$set": {f"guest_headphones.{guest_index}": normalized, "headphone_updated_at": now_iso}}
        )
    logger.info(f"[V188 HEADPHONE] {reservation_id} guest[{guest_index}] → {normalized}")
    return {
        "success": True,
        "reservation_id": reservation_id,
        "guest_index": guest_index,
        "guest_headphone_status": normalized,
    }


@reservation_router.put("/reservations/{reservation_id}/headphone")
async def update_reservation_headphone_put(reservation_id: str, request: Request):
    return await _update_headphone_impl(reservation_id, request)


# V186: Accept PATCH/POST aliases (certains proxys/clients ne propagent pas PUT correctement)
@reservation_router.patch("/reservations/{reservation_id}/headphone")
async def update_reservation_headphone_patch(reservation_id: str, request: Request):
    return await _update_headphone_impl(reservation_id, request)


@reservation_router.post("/reservations/{reservation_id}/headphone")
async def update_reservation_headphone_post(reservation_id: str, request: Request):
    return await _update_headphone_impl(reservation_id, request)

# === STAFF ACCESS: Validation QR uniquement (pas d'accès chat/réglages) ===
@reservation_router.post("/staff/validate")
async def staff_validate_reservation(request: Request):
    """Endpoint simplifié pour le staff — valide une réservation par code QR.
    Le staff n'a accès qu'à ce endpoint, pas aux conversations ni aux réglages."""
    # R11 — TROISIEME PORTE SUR LA MEME ECRITURE, fermee par la meme garde.
    # Mesure du 19/08/2026 : `POST /api/staff/validate` sans en-tete repondait
    # 404 — la route etait atteinte. Le nom « staff » ne protegeait rien :
    # `/staff/login` n'emet aucun jeton, il ne fait que basculer une session
    # coach DEJA authentifiee en mode restreint cote navigateur. Le staff scanne
    # donc avec le jeton du coach, qui reste valide : aucun parcours ferme.
    # Aucun ecran n'appelle cette route aujourd'hui (verifie sur tout
    # `frontend/src`).
    _scanneur = await _r11_scanneur(request)
    body = await request.json()
    code = body.get("code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="Code requis")
    reservation = await db.reservations.find_one({"reservationCode": code}, {"_id": 0})
    if not reservation:
        raise HTTPException(status_code=404, detail="Réservation non trouvée")
    if reservation.get("validated"):
        return {"success": False, "message": "Déjà validé", "userName": reservation.get("userName", ""), "validatedAt": reservation.get("validatedAt", "")}
    await _a0_marquer_presente(reservation, _scanneur)
    return {"success": True, "message": "Réservation validée", "userName": reservation.get("userName", ""), "courseName": reservation.get("courseName", "")}


async def _validate_discount_code_presence(code: str, discount: dict, member_slug: str = None,
                                           forced_course_id: str = None, scanneur: str = ""):
    """V213: Valider la présence d'un membre via code promo/groupe.
    Cherche une réservation existante pour aujourd'hui et la valide."""
    from datetime import timedelta as _td
    swiss_tz = timezone(_td(hours=2))
    now_swiss = datetime.now(swiss_tz)
    today_str = now_swiss.strftime("%Y-%m-%d")
    is_multi = discount.get("multi_member", False)

    # Identifier le membre
    member_name = "Abonné"
    member_email = ""
    if is_multi and member_slug:
        # V213: slug peut arriver en majuscules depuis le QR → cherche insensible à la casse
        member = await db.code_members.find_one(
            {"slug": {"$regex": f"^{re.escape(member_slug)}$", "$options": "i"}}, {"_id": 0}
        )
        if member:
            member_name = member.get("name", "Membre")
            member_email = member.get("email", "")
        else:
            raise HTTPException(status_code=404, detail="Membre non trouvé dans ce groupe")
    elif is_multi and not member_slug:
        # V213: Groupe multi-membre scanné sans slug — on cherche toutes les réservations du groupe pour aujourd'hui
        from datetime import timedelta as _td2
        swiss_tz2 = timezone(_td2(hours=2))
        today_str2 = datetime.now(swiss_tz2).strftime("%Y-%m-%d")
        today_reservations = await db.reservations.find(
            {"discountCode": {"$regex": f"^{re.escape(code)}$", "$options": "i"}, "datetime": {"$regex": today_str2}, "validated": {"$ne": True}},
            {"_id": 0}
        ).to_list(50)
        if today_reservations:
            # Valider toutes les réservations non-validées du groupe pour aujourd'hui
            names = []
            for r in today_reservations:
                # R11/A0 : meme helper que partout ailleurs — propriete verifiee,
                # transition atomique, evenement de presence emis une seule fois.
                await _a0_marquer_presente(r, scanneur)
                names.append(r.get("userName", "?"))
            logger.info(f"[QR-SCAN-V213] Groupe {code}: {len(today_reservations)} présences validées")
            return {"success": True, "type": "subscription",
                    "message": f"{len(today_reservations)} présence(s) validée(s)",
                    "reservation": {"userName": ", ".join(names), "reservationCode": code, "courseName": today_reservations[0].get("courseName", "")},
                    "subscriber": {"name": f"Groupe {code}", "remaining": discount.get("remaining_sessions", 0), "total": discount.get("total_sessions", 0)}}
        # Vérifier s'il y a des réservations déjà validées
        already_validated = await db.reservations.count_documents(
            {"discountCode": {"$regex": f"^{re.escape(code)}$", "$options": "i"}, "datetime": {"$regex": today_str2}, "validated": True}
        )
        if already_validated > 0:
            return {"success": True, "type": "subscription", "message": f"Déjà validé ({already_validated} présence(s))",
                    "reservation": {"userName": f"Groupe {code}", "reservationCode": code, "courseName": ""},
                    "subscriber": {"name": f"Groupe {code}", "remaining": discount.get("remaining_sessions", 0), "total": discount.get("total_sessions", 0)}}
        raise HTTPException(status_code=404, detail=f"Aucune réservation pour le groupe {code} aujourd'hui.")
    elif not is_multi:
        member_name = discount.get("name") or discount.get("userName") or "Abonné"
        member_email = discount.get("email", "")

    # Chercher une réservation pour aujourd'hui
    res_query = {"discountCode": {"$regex": f"^{re.escape(code)}$", "$options": "i"}, "datetime": {"$regex": today_str}}
    if member_slug:
        res_query["member_slug"] = {"$regex": f"^{re.escape(member_slug)}$", "$options": "i"}
    elif member_email:
        res_query["userEmail"] = {"$regex": f"^{re.escape(member_email)}$", "$options": "i"}

    reservation = await db.reservations.find_one(res_query, {"_id": 0})

    if reservation:
        if reservation.get("validated"):
            return {"success": True, "type": "subscription", "message": "Déjà validé",
                    "reservation": {"userName": reservation.get("userName", member_name),
                                    "reservationCode": reservation.get("reservationCode", code),
                                    "courseName": reservation.get("courseName", "")},
                    "subscriber": {"name": reservation.get("userName", member_name),
                                   "remaining": discount.get("remaining_sessions", 0),
                                   "total": discount.get("total_sessions", 0)}}
        # Valider la réservation
        # R11/A0 : propriete verifiee, transition atomique, funnel alimente —
        # ce chemin n'emettait AUCUN evenement de presence jusqu'ici.
        await _a0_marquer_presente(reservation, scanneur)
        remaining = discount.get("remaining_sessions", 0)
        total = discount.get("total_sessions", 0)
        # Pour les groupes avec sessions individuelles, lire depuis code_members
        if is_multi and member_slug:
            member_doc = await db.code_members.find_one({"slug": member_slug}, {"_id": 0})
            if member_doc:
                remaining = member_doc.get("remaining_sessions", remaining)
                total = member_doc.get("total_sessions", total)
        logger.info(f"[QR-SCAN-V213] Validé: {member_name} ({code}) -> {reservation.get('courseName')}")
        return {"success": True, "type": "subscription", "message": "Présence validée !",
                "reservation": {"userName": reservation.get("userName", member_name),
                                "reservationCode": reservation.get("reservationCode", code),
                                "courseName": reservation.get("courseName", "")},
                "subscriber": {"name": reservation.get("userName", member_name),
                               "remaining": remaining, "total": total}}

    # Pas de réservation pour aujourd'hui
    raise HTTPException(status_code=404,
                        detail=f"{member_name} n'a pas de réservation pour aujourd'hui. Demande-lui de réserver d'abord.")


async def _validate_user_access_code(code: str, user: dict, forced_course_id: str = None,
                                     scanneur: str = ""):
    """V213 CAS D: Valider la présence via code d'accès AFRO-XXXX.
    Cherche une réservation existante pour aujourd'hui et la valide."""
    from datetime import timedelta as _td
    swiss_tz = timezone(_td(hours=2))
    now_swiss = datetime.now(swiss_tz)
    today_str = now_swiss.strftime("%Y-%m-%d")

    user_email = (user.get("email") or "").lower().strip()
    user_name = user.get("name") or "Utilisateur"

    if not user_email:
        raise HTTPException(status_code=400, detail="Pas d'email associé à ce code d'accès")

    # Chercher une réservation pour aujourd'hui
    res_query = {
        "userEmail": {"$regex": f"^{re.escape(user_email)}$", "$options": "i"},
        "datetime": {"$regex": today_str}
    }
    reservation = await db.reservations.find_one(res_query, {"_id": 0})

    if reservation:
        if reservation.get("validated"):
            return {"success": True, "type": "reservation", "message": "Déjà validé",
                    "reservation": {"userName": reservation.get("userName", user_name),
                                    "reservationCode": reservation.get("reservationCode", code),
                                    "courseName": reservation.get("courseName", "")}}
        # R11/A0 : propriete verifiee, transition atomique, funnel alimente —
        # ce chemin n'emettait AUCUN evenement de presence jusqu'ici.
        await _a0_marquer_presente(reservation, scanneur)
        logger.info(f"[QR-SCAN-V213] Validé via AFRO code: {user_name} ({code}) -> {reservation.get('courseName')}")
        return {"success": True, "type": "reservation", "message": "Présence validée !",
                "reservation": {"userName": reservation.get("userName", user_name),
                                "reservationCode": reservation.get("reservationCode", code),
                                "courseName": reservation.get("courseName", "")}}

    # Pas de réservation — chercher un abonnement actif pour déduire une séance
    sub = await db.subscriptions.find_one(
        {"email": {"$regex": f"^{re.escape(user_email)}$", "$options": "i"}, "status": "active"}, {"_id": 0}
    )
    if sub:
        # Rediriger vers le flux CAS B en passant le code subscription
        # Pour éviter la duplication de code, on retourne l'info pour relancer
        remaining = int(sub.get("remaining_sessions", 0))
        total = sub.get("total_sessions", remaining)
        return {"success": True, "type": "subscription",
                "message": f"{user_name} n'a pas réservé aujourd'hui mais a un abonnement actif ({remaining}/{total} séances).",
                "reservation": {"userName": user_name, "reservationCode": code, "courseName": ""},
                "subscriber": {"name": user_name, "remaining": remaining, "total": total}}

    raise HTTPException(status_code=404,
                        detail=f"{user_name} n'a pas de réservation pour aujourd'hui.")


# ═══════════════════════════════════════════════════════════════════════════
# R11 — VALIDER UNE PRESENCE EXIGE UNE IDENTITE PROUVEE
#
# `/qr/scan-validate` n'avait AUCUNE authentification. La route ecrit
# `validated` sur une reservation, et, quand personne n'a reserve, CREE une
# reservation et DEBITE une seance. Connaitre un code suffisait donc a marquer
# quelqu'un present, ou a lui consommer une seance, depuis n'importe ou.
#
# DEUX AUTRES PORTES FONT LA MEME ECRITURE, et elles sont fermees ici aussi —
# sans elles ce lot n'aurait rien ferme du tout. Mesure du 19/08/2026 sur la
# production, sans le moindre en-tete :
#     POST /api/reservations/<code>/validate  -> 404 (route ATTEINTE)
#     POST /api/staff/validate                -> 404 (route ATTEINTE)
# Un vrai code aurait ete valide. Aucun ecran n'appelle ces deux routes
# (verifie sur tout `frontend/src`) : les fermer ne retire aucun parcours.
#
# POURQUOI MAINTENANT. La presence est le declencheur metier du futur ecran de
# conversion apres essai. Falsifiable, elle rendrait faux tout ce qui se
# construira dessus. On ferme donc AVANT de batir.
#
# AUCUN MECANISME NEUF. On reprend `_v309_require_coach_or_admin`, exactement
# la garde qui protege deja `/api/users`, `/api/contacts/all` et
# `/api/coach/notifications` : JWT SIGNE verifie (HS256), jetons abonne rejetes,
# puis verification que l'e-mail correspond a un compte coach ou super-admin
# REEL. `X-User-Email` ne participe pas — il est falsifiable (mode transitoire
# V265) et ne prouve rien.
#
# LE CHEMIN LEGITIME EST PROUVE AVANT DE DURCIR (regle V310c). Mesure du
# 19/08/2026 sur la production :
#     GET /api/users         sans jeton -> 403
#     GET /api/contacts/all  sans jeton -> 403
#     GET /api/coach/notifications      -> 403
# Ces trois routes portent DEJA cette garde et le tableau de bord du
# proprietaire les consomme sans probleme : sa session emet donc bien un jeton
# signe. Le drapeau `REQUIRE_COACH_JWT` est par ailleurs a True en base.
#
# LE SCANNER MOBILE NE CHANGE PAS D'UN GESTE. Les deux scanners
# (CoachDashboard.js:2449 et ChatWidget.js:5671) passent par l'instance axios
# globale, dont l'intercepteur (App.js:14-20) pose deja
# `Authorization: Bearer <afroboost_jwt>` sur CHAQUE requete. Rien a saisir,
# rien a copier, aucun ecran de plus.
#
# LE MODE STAFF RESTE OUVERT. `/staff/login` n'emet aucun jeton : il ne fait que
# basculer une session coach DEJA authentifiee en mode restreint (drapeau
# `afroboost_staff_mode` cote navigateur). Le staff scanne donc avec le jeton du
# coach, qui reste valide. Aucun parcours staff n'est ferme.
# ═══════════════════════════════════════════════════════════════════════════

R11_MSG_ANONYME = "Authentification coach requise pour valider une présence — reconnecte-toi."
R11_MSG_AUTRE_COACH = "Cette réservation ne relève pas de ton compte."


async def _r11_scanneur(request) -> str:
    """L'e-mail du coach/admin qui scanne, PROUVE par un jeton signe. 403 sinon.

    Import PARESSEUX : `server.py` importe ce module au chargement, un import en
    tete de fichier creerait un cycle. Meme motif que `t1_preuve` (l. 884) et
    `send_push_by_email` (l. 968), deja en service ici.
    """
    from api.server import _v309_require_coach_or_admin as _garde
    try:
        return await _garde(request)
    except HTTPException as _e:
        # On reecrit le message pour le staff qui scanne a la porte : il doit
        # comprendre quoi faire sans lire les journaux. Le CODE reste 403.
        if _e.status_code == 403:
            raise HTTPException(status_code=403, detail=R11_MSG_ANONYME)
        raise


def _r11_verifier_proprietaire(scanneur: str, document: dict, quoi: str = "réservation") -> None:
    """Ce coach a-t-il le droit d'agir sur CE document ? 403 sinon.

    LE MODELE, tel qu'il existe — rien n'est invente ici :
      * un super-admin voit et valide tout (`is_super_admin`, deja la regle de
        `/reservations`, l. 697, et de tout le cloisonnement multi-coach) ;
      * sinon, `coach_id` du document doit etre celui de l'appelant.

    DONNEE ORPHELINE (`coach_id` absent ou vide) -> on LAISSE PASSER. C'est un
    choix, pas un oubli : l'appelant est deja un coach authentifie, et refuser
    bloquerait une validation legitime sur une donnee ancienne. Mesure du
    19/08/2026 : 132 reservations sur 132 et 22 cours sur 22 portent un
    `coach_id`, donc ce repli ne s'applique aujourd'hui a rien. Un `coach_id`
    RENSEIGNE ET DIFFERENT, lui, refuse toujours.
    """
    if is_super_admin(scanneur):
        return
    _proprio = ((document or {}).get("coach_id") or "").lower().strip()
    if not _proprio:
        return
    if _proprio != (scanneur or "").lower().strip():
        logger.warning("[R11] REFUS %s : %s n'est pas le proprietaire (%s)",
                       quoi, scanneur, _proprio)
        raise HTTPException(status_code=403, detail=R11_MSG_AUTRE_COACH)


# ═══════════════════════════════════════════════════════════════════════════
# A0 — LE SCAN A L'ENTREE DIT LA VERITE SUR LA PRESENCE
#
# Constat du 19 aout 2026, sur la production : 9 reservations validees sur 132,
# la derniere le 12 avril. Le scan ne marchait plus, et trois defauts distincts
# s'y ajoutaient. A0 repare le CHEMIN, il ne change AUCUNE regle metier :
# ni le prix, ni les credits, ni ESSAI, ni les rappels, ni les notifications.
#
#   A0-1  Une reservation DEJA PAYEE se valide sans redemander un credit.
#         Reserver depuis l'espace debite deja la seance : au moment du scan,
#         un essai (1 seance) est donc a 0 et le portier repondait « Plus de
#         seances disponibles ». La presence etait INVALIDABLE pour tout
#         participant ayant reserve a l'avance — mesure du 19/08 : 3 des 4
#         reservations a venir etaient dans ce cas, toutes payantes.
#
#   A0-2  Le QR de l'e-mail de confirmation devient scannable. Il encode une
#         URL (`https://afroboost.com/chat?code=...&res=...`) ; le scanner du
#         tableau de bord lui appliquait /AF[A-Z0-9]{6,}/i, dont la premiere
#         correspondance est « AFROBOOST » — pris dans le nom de domaine. Tout
#         scan d'un QR d'e-mail partait donc en 404. La normalisation est faite
#         ICI, cote serveur, et non dans les scanners : il y en a DEUX
#         (CoachDashboard et ChatWidget, ce dernier n'analysant rien du tout),
#         plus la saisie manuelle. Un seul endroit, un seul comportement.
#
#   A0-3  La presence entre enfin dans le funnel. `_c9_presence` n'etait appele
#         par AUCUN des deux chemins reellement empruntes par le scanner,
#         contrairement a ce qu'affirmait sa docstring.
#
# HORS PERIMETRE, ASSUME ET CONSIGNE : `/qr/scan-validate` n'a toujours AUCUNE
# AUTHENTIFICATION (dette R11). A0 ne l'aggrave pas — voir la note detaillee
# au-dessus de la route.
# ═══════════════════════════════════════════════════════════════════════════

# Tolerance de rattachement quand une personne a PLUSIEURS reservations le meme
# jour. Reprise a l'identique de la detection de cours deja en service plus bas
# (« diff <= 90 »), pour que le scan ne connaisse qu'une seule tolerance.
A0_TOLERANCE_MIN = 90


def _a0_maintenant_ch():
    """L'instant present a l'heure suisse, meme convention que le reste de ce
    fichier (UTC+2 en dur).

    ⚠️ Cette convention est FAUSSE en heure d'hiver (UTC+1) : elle decale d'une
    heure la frontiere de minuit. Le defaut est ANTERIEUR a A0 et present dans
    quatre autres endroits de ce fichier ; le corriger changerait le jour
    retenu pour des scans nocturnes, ce qui n'est pas le sujet d'A0. On reprend
    donc la convention existante a l'identique plutot que d'en introduire une
    seconde, et le point est consigne comme anomalie.
    """
    from datetime import timedelta as _td
    return datetime.now(timezone(_td(hours=2)))


def _a0_code_depuis_qr(texte: str) -> str:
    """Le code porte par un QR, qu'il soit brut ou enrobe dans une URL.

    Ne touche a RIEN d'autre : un code brut (`AFR-XXXXXX`, `AF1234ABCD`,
    `CODE::slug`) ressort identique. Seul un texte qui commence par http(s) est
    analyse, et uniquement pour y lire un parametre.

    Ordre de preference — du plus precis au plus large :
      `res`  identifiant de LA reservation (donc de L'OCCURRENCE) -> CAS A ;
      `qr`   convention V156 des QR d'abonnement ;
      `code` code d'acces de l'abonne -> CAS B.

    Le repli est le texte d'origine : si l'URL ne porte aucun de ces trois
    parametres, on ne devine pas — le scan echouera avec le message habituel,
    ce qui reste preferable a une validation approximative.
    """
    _t = (texte or "").strip()
    if not _t.lower().startswith(("http://", "https://")):
        return _t
    try:
        from urllib.parse import urlparse, parse_qs
        _params = parse_qs(urlparse(_t).query)
    except Exception as _err:
        logger.warning("[A0] URL de QR illisible : %s", _err)
        return _t
    for _cle in ("res", "qr", "code"):
        _valeurs = _params.get(_cle) or []
        if _valeurs and str(_valeurs[0]).strip():
            _extrait = str(_valeurs[0]).strip()
            logger.info("[A0] QR-URL : parametre '%s' retenu -> '%s'", _cle, _extrait)
            return _extrait
    logger.warning("[A0] QR-URL sans parametre exploitable — texte conserve tel quel")
    return _t


def _a0_horodatage(valeur):
    """La date/heure d'une reservation, en aware UTC, ou None si illisible.

    Les dates de cette base sont tantot des chaines ISO naives
    (« 2026-08-22T18:30:00 », l'heure locale du cours), tantot des chaines avec
    fuseau, tantot des `datetime`. Une valeur naive est lue comme suisse, pour
    rester coherent avec `_a0_maintenant_ch`.
    """
    from datetime import timedelta as _td
    _tz_ch = timezone(_td(hours=2))
    if isinstance(valeur, datetime):
        _d = valeur if valeur.tzinfo else valeur.replace(tzinfo=_tz_ch)
        return _d.astimezone(timezone.utc)
    try:
        _d = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if _d.tzinfo is None:
        _d = _d.replace(tzinfo=_tz_ch)
    return _d.astimezone(timezone.utc)


def _a0_est_aujourdhui(valeur) -> bool:
    """Cette reservation concerne-t-elle la journee suisse en cours ?

    C'est la garde qui protege l'invariant « ne pas valider une autre
    occurrence du meme cours » : un cours recurrent du mercredi produit une
    reservation par occurrence, chacune avec son propre code. Sans cette garde,
    scanner l'e-mail du 19/08 le 26/08 validerait la seance du 19/08.
    """
    _d = _a0_horodatage(valeur)
    if _d is None:
        return False
    from datetime import timedelta as _td
    _tz_ch = timezone(_td(hours=2))
    return _d.astimezone(_tz_ch).date() == _a0_maintenant_ch().date()


async def _a0_marquer_presente(reservation: dict, scanneur: str = "") -> bool:
    """Pose la presence sur UNE reservation. Renvoie True si c'est une
    transition reelle (non-validee -> validee), False si elle l'etait deja.

    PRISE DE DROIT ATOMIQUE, et non « lire puis ecrire ». Le filtre porte la
    condition `validated != True` : deux scans simultanes du meme QR — un
    double-tap, deux telephones a la porte — n'en font gagner qu'un seul. Le
    perdant lit `matched_count == 0` et ne produit AUCUN second effet : pas de
    second `validatedAt`, pas de second evenement de funnel. C'est le motif
    deja en service pour le verrou de renouvellement (V447) et pour
    `launch_campaign`.

    A0-3 : l'evenement de presence est emis ICI, donc exactement une fois par
    transition, et jamais sur un re-scan.
    """
    # R11 : la propriete se verifie AVANT l'ecriture, sur le document reel.
    # `scanneur` vide = appelant interne qui a deja verifie (aucun aujourd'hui).
    if scanneur:
        _r11_verifier_proprietaire(scanneur, reservation, "réservation")
    _id = reservation.get("id")
    _quand = datetime.now(timezone.utc).isoformat()
    if not _id:
        # Donnee ancienne sans `id` : on retombe sur le code de reservation,
        # qui est unique. Meme condition, meme atomicite.
        _filtre = {"reservationCode": reservation.get("reservationCode"),
                   "validated": {"$ne": True}}
    else:
        _filtre = {"id": _id, "validated": {"$ne": True}}
    _res = await db.reservations.update_one(
        _filtre, {"$set": {"validated": True, "validatedAt": _quand}})
    if not getattr(_res, "matched_count", 0):
        return False
    await _c9_presence(reservation, False)
    return True


async def _a1b_occurrences_reelles(reservations: list) -> list:
    """A1b — NE GARDE QUE LES RESERVATIONS QUI DESIGNENT UNE SEANCE REELLE.

    ═══════════════════════════════════════════════════════════════════════
    CE QUE CECI CORRIGE — constate en production le 19/08/2026.
    ═══════════════════════════════════════════════════════════════════════
    Le coach scanne `BASSBOOSTX-11` : le portier repond « Deja valide — Diner
    canadien ». Or « Diner canadien » est un cours PONCTUEL du 2026-08-09 : il
    n'a pas lieu ce jour-la, et n'aura plus jamais lieu.

    La reservation appariee (`AFRO-FUPQ`) est datee du 19/08 parce qu'elle a ete
    creee le matin meme par l'ANCIEN scanner, qui datait la reservation de
    l'instant du scan au lieu de l'occurrence — c'est exactement le defaut A1-3.
    A1 empeche d'en creer une nouvelle, mais ne protegeait que le chemin de
    CREATION. Le chemin d'APPARIEMENT — quelles reservations existantes comptent
    comme la presence du jour — n'avait, lui, aucune garde : il ne regardait que
    le lien au forfait et la date portee par la reservation.

    Consequence generale, independante de ce residu : n'importe quelle
    reservation datee d'aujourd'hui restait candidate meme si son cours avait
    ete archive, ou n'avait pas lieu ce jour-la.

    ═══════════════════════════════════════════════════════════════════════
    LA REGLE
    ═══════════════════════════════════════════════════════════════════════
    Une reservation reste candidate si — ET SEULEMENT SI elle porte un
    `courseId` — le cours designe :
      * existe encore dans la collection ;
      * n'est pas `archived` ;
      * A LIEU le jour de la reservation (`_a1_a_lieu_aujourdhui`, le meme
        helper que le chemin de creation : une seule definition de « ce cours a
        lieu ce jour-la » dans tout le fichier).

    `visible` N'EST PAS UNE GARDE — DECISION EXPLICITE. C'est un drapeau
    d'AFFICHAGE, pas de cycle de vie : masquer un cours de la vitrine ne doit
    pas rendre invalides les reservations deja prises dessus. Mesure du
    19/08/2026 : 7 cours sur 22 sont invisibles, et AUCUNE reservation n'en
    designe un — la garde n'aurait donc rien filtre aujourd'hui, mais elle
    aurait pu invalider demain une seance parfaitement legitime.

    `courseId` ABSENT -> ON GARDE. Repli assume et mesure : 58 reservations sur
    133 n'en portent aucune (`chat_widget_abonne` 39, `website` 18 — ces deux
    parcours ne l'ecrivent pas). Fermer ici retirerait la validation de presence
    a tout ce stock, pour un gain nul : sans identifiant de cours, il n'y a
    aucune occurrence a verifier. C'est le SEUL ecart au « refus par defaut »,
    et il est nomme.

    ═══════════════════════════════════════════════════════════════════════
    CE QUE CECI NE FAIT PAS
    ═══════════════════════════════════════════════════════════════════════
    Aucune ecriture, aucune suppression, aucun nettoyage. Les reservations
    ecartees restent INTACTES en base et continuent d'apparaitre dans
    l'historique, la liste des reservations, les transactions et le suivi de
    l'abonne. Elles cessent seulement d'etre proposees comme SEANCE ACTUELLE.

    Il n'existe aujourd'hui AUCUN statut d'annulation sur `reservations` (ni
    `status`, ni `cancelled`, ni `deleted` — 0 document sur 133 en porte un) :
    la garde « reservation non annulee » est donc impossible a ecrire ici, et
    n'est pas inventee. Manque consigne, hors de ce lot.

    UNE SEULE REQUETE pour toute la liste (`$in` groupe), jamais un `find_one`
    par ligne — meme regle que partout ailleurs dans ce projet.
    """
    if not reservations:
        return reservations
    _ids = sorted({(r.get("courseId") or "").strip()
                   for r in reservations if (r.get("courseId") or "").strip()})
    if not _ids:
        return reservations
    try:
        _docs = await db.courses.find(
            {"id": {"$in": _ids}},
            {"_id": 0, "id": 1, "name": 1, "weekday": 1, "date": 1, "archived": 1},
        ).to_list(200)
    except Exception as _err:
        # Cours illisibles : on ne durcit pas sur une panne de lecture. Le
        # comportement d'avant A1b reprend la main, il n'est pas pire.
        logger.warning("[A1b] Cours illisibles, garde ignoree — %s: %s",
                       type(_err).__name__, _err)
        return reservations
    _par_id = {c.get("id"): c for c in _docs if c.get("id")}

    _gardees = []
    for _r in reservations:
        _cid = (_r.get("courseId") or "").strip()
        if not _cid:
            _gardees.append(_r)                       # repli assume, cf. docstring
            continue
        _c = _par_id.get(_cid)
        if _c is None:
            logger.info("[A1b] %s ecartee : cours %s absent de la collection",
                        _r.get("reservationCode"), _cid)
            continue
        if _c.get("archived"):
            logger.info("[A1b] %s ecartee : cours « %s » archive",
                        _r.get("reservationCode"), _c.get("name"))
            continue
        _d = _a0_horodatage(_r.get("datetime"))
        if _d is None:
            logger.info("[A1b] %s ecartee : date illisible", _r.get("reservationCode"))
            continue
        from datetime import timedelta as _td_a1b
        _jour_local = _d.astimezone(timezone(_td_a1b(hours=2)))
        _jour_iso = _jour_local.strftime("%Y-%m-%d")
        if not _a1_a_lieu_aujourdhui(_c, _jour_iso, _a1_jour_js(_jour_local)):
            logger.info("[A1b] %s ecartee : « %s » n'a pas lieu le %s",
                        _r.get("reservationCode"), _c.get("name"), _jour_iso)
            continue
        _gardees.append(_r)
    return _gardees


async def _a0_reservations_du_jour(subscription: dict, code: str, member_slug: str = None) -> list:
    """Les reservations de CET abonnement pour la journee en cours.

    DEUX PASSES, de la plus precise a la plus large — et jamais l'inverse :
      1. le lien explicite : `subscriptionId`, ou le code porte par la
         reservation (`discountCode` / `promoCode`) ;
      2. a defaut seulement, l'adresse e-mail.
    L'ordre compte : une personne peut detenir DEUX forfaits (un essai et un
    pack). Chercher d'abord par e-mail validerait la reservation rattachee a
    l'autre forfait. La passe 2 n'existe que pour les reservations anciennes,
    qui ne portent ni `subscriptionId` ni code (37 des 132 reservations de
    production portent `subscriptionId`).

    La fenetre de la requete couvre TROIS jours (hier, aujourd'hui, demain) et
    le tri fin est fait en Python par `_a0_est_aujourdhui`. Raison : le champ
    `datetime` existe en DEUX formats en base — « 2026-08-22T18:30:00 » (heure
    locale du cours) et « 2026-03-11T09:21:01.887Z » (UTC). Un simple prefixe
    de date sur le second se trompe de jour pour les seances de fin de soiree.
    """
    from datetime import timedelta as _td
    _maintenant = _a0_maintenant_ch()
    _jours = [(_maintenant + _td(days=_d)).strftime("%Y-%m-%d") for _d in (-1, 0, 1)]
    _fenetre = {"datetime": {"$regex": "^(" + "|".join(re.escape(_j) for _j in _jours) + ")"}}

    _precis = []
    _sid = str(subscription.get("id") or "").strip()
    if _sid:
        _precis.append({"subscriptionId": _sid})
    _code = (code or "").strip()
    if _code:
        _motif = {"$regex": f"^{re.escape(_code)}$", "$options": "i"}
        _precis.append({"discountCode": _motif})
        _precis.append({"promoCode": _motif})

    async def _chercher(criteres):
        _q = dict(_fenetre)
        _q["$or"] = criteres
        if member_slug:
            _q["member_slug"] = {"$regex": f"^{re.escape(member_slug)}$", "$options": "i"}
        _rows = await db.reservations.find(_q, {"_id": 0}).to_list(20)
        _dujour = [r for r in _rows if _a0_est_aujourdhui(r.get("datetime"))]
        # A1b : une reservation du jour ne suffit pas — encore faut-il qu'elle
        # designe une seance qui a REELLEMENT lieu. Filtre ICI, donc sur les
        # DEUX passes : si la passe precise ne laisse que des candidates
        # invalides, la passe e-mail reprend la main, comme si elle n'avait rien
        # trouve. C'est le comportement voulu.
        return await _a1b_occurrences_reelles(_dujour)

    _trouvees = await _chercher(_precis) if _precis else []
    if _trouvees:
        return _trouvees

    _email = (subscription.get("email") or "").lower().strip()
    if not _email:
        return []
    return await _chercher([{"userEmail": {"$regex": f"^{re.escape(_email)}$", "$options": "i"}}])


def _a0_choisir_occurrence(reservations: list):
    """LA reservation que ce scan concerne, ou None si le choix est ambigu.

    Une seule candidate -> c'est elle, sans condition d'heure : le staff scanne
    a la porte, la personne n'a qu'une seance ce jour-la, il n'y a rien a
    departager. Imposer une fenetre ici refuserait une validation faite un peu
    apres la fin du cours — le cas le plus banal.

    Plusieurs candidates (deux cours le meme jour) -> on prend la plus proche
    de l'instant du scan, et seulement si elle tombe dans la tolerance deja en
    service pour la detection de cours. Au-dela, on ne devine pas : on renvoie
    None et le chemin historique reprend la main.
    """
    _valides = [r for r in (reservations or []) if _a0_horodatage(r.get("datetime")) is not None]
    if not _valides:
        return None
    if len(_valides) == 1:
        return _valides[0]
    _maintenant = _a0_maintenant_ch().astimezone(timezone.utc)
    _classees = sorted(
        _valides,
        key=lambda r: abs((_a0_horodatage(r.get("datetime")) - _maintenant).total_seconds()))
    _ecart_min = abs((_a0_horodatage(_classees[0].get("datetime")) - _maintenant).total_seconds()) / 60
    if _ecart_min > A0_TOLERANCE_MIN:
        logger.info("[A0] %d reservations aujourd'hui, la plus proche a %d min — trop loin, "
                    "on laisse le chemin historique decider", len(_valides), int(_ecart_min))
        return None
    return _classees[0]


async def _a0_presence_deja_reservee(subscription: dict, code: str, member_slug: str = None,
                                     scanneur: str = ""):
    """A0-1 — VALIDER UNE PRESENCE DEJA PAYEE, SANS REDEMANDER DE CREDIT.

    Renvoie la reponse du scan, ou None pour laisser le chemin historique
    (detection du cours, creation de la reservation, debit) reprendre la main.

    LE DEFAUT QUE CECI CORRIGE. Reserver depuis l'espace abonne DEBITE la
    seance immediatement. Au moment du scan, un essai gratuit (1 seance) est
    donc a 0, et le portier repondait « Plus de seances disponibles » — la
    presence etait invalidable pour QUICONQUE avait reserve a l'avance. Mesure
    du 19/08/2026 : 3 des 4 reservations a venir, toutes payantes.

    Le credit a deja ete pris a la reservation : constater la presence n'en
    consomme pas un second. Aucune ecriture sur `subscriptions`, aucune
    creation de reservation — uniquement `validated` / `validatedAt` sur la
    reservation qui existe deja.
    """
    _candidates = await _a0_reservations_du_jour(subscription, code, member_slug)
    _resa = _a0_choisir_occurrence(_candidates)
    if not _resa:
        return None

    _nom = _resa.get("userName") or subscription.get("name") or "Abonné"
    _restant = subscription.get("remaining_sessions", 0)
    _total = subscription.get("total_sessions", _restant)
    _corps = {
        "success": True, "type": "subscription",
        "reservation": {"userName": _nom,
                        "reservationCode": _resa.get("reservationCode", code),
                        "courseName": _resa.get("courseName", "")},
        "subscriber": {"name": _nom, "remaining": _restant, "total": _total},
    }
    if _resa.get("validated"):
        # Re-scan du meme QR : aucun second effet metier, aucun evenement.
        _corps["message"] = "Déjà validé"
        return _corps
    await _a0_marquer_presente(_resa, scanneur)
    logger.info("[A0] Presence validee sans debit : %s -> %s (%s)",
                code, _resa.get("courseName"), _resa.get("reservationCode"))
    _corps["message"] = "Présence validée (réservation déjà payée)"
    return _corps


# ═══════════════════════════════════════════════════════════════════════════
# A1 — LE SCAN VALIDE UNE OCCURRENCE REELLE, PAS « UN COURS »
# ═══════════════════════════════════════════════════════════════════════════
#
# Trois defauts distincts violaient le meme invariant : « le scan a l'entree
# constate LA seance du jour, et n'en debite qu'une ».
#
# A1-1  CONVENTION DU JOUR DE LA SEMAINE.
#       `courses.weekday` est stocke en convention JAVASCRIPT (Dim=0..Sam=6) :
#       c'est `Date.getDay()`, cote site, qui l'ecrit. La preuve est en base et
#       ne depend d'aucune lecture de code — les cours A DATE FIXE portent les
#       DEUX informations, et elles ne concordent qu'en convention JS :
#           « Laff Festival » date=2026-08-21 (un VENDREDI)  weekday=5
#               -> JS : 5 = vendredi  ✔      Python : 5 = samedi  ✘
#           « Silent Dance »  date=2026-08-23 (un DIMANCHE)  weekday=0
#               -> JS : 0 = dimanche  ✔      Python : 0 = lundi   ✘
#       Or le scanner interrogeait Mongo avec `datetime.weekday()`, convention
#       PYTHON (Lun=0..Dim=6) : decalage systematique d'un jour. Le mercredi, il
#       cherchait `weekday: 2` quand les cours du mercredi portent `3`.
#       `_v184_next_occurrences` (V196) fait deja la conversion dans l'autre
#       sens ; on reprend sa formule EXACTEMENT inversee pour que les deux
#       endroits ne puissent plus diverger :
#           V196   py = (js - 1) % 7        A1   js = (py + 1) % 7
#
# A1-2  UNE DATE FIXE N'EST PAS UNE RECURRENCE.
#       Un cours ponctuel (`date` renseignee) n'a lieu QU'UNE fois. Filtre sur
#       le seul `weekday`, « Diner canadien » du 2026-08-09 restait proposable
#       tous les dimanches suivants — et un scan pouvait y debiter une seance.
#
# A1-3  L'OCCURRENCE, PAS L'INSTANT DU SCAN.
#       La reservation creee etait datee `now` (l'heure du scan). Elle ne
#       designait donc AUCUNE occurrence : tout rapprochement ulterieur
#       (`_a0_est_aujourdhui`, recherche de doublon, agenda de l'abonne) portait
#       sur une date sans rapport avec la seance. On date desormais la
#       reservation a l'heure REELLE du cours, au format NAIF local — la meme
#       convention que `_v184_next_occurrences` (V196) et que l'espace abonne,
#       pour qu'il n'y en ait qu'une seule dans toute la base.
#
# Ce qui n'est PAS touche : le credit (un seul debit, garde par A0), la
# propriete (R11), l'idempotence, et le CAS A — un code de reservation saisi a
# la main garde exactement le comportement d'avant.

A1_JOURS_JS = ("Dim", "Lun", "Mar", "Mer", "Jeu", "Ven", "Sam")


def _a1_jour_js(maintenant) -> int:
    """Le jour de la semaine en convention JavaScript (Dim=0..Sam=6).

    Inverse EXACT de la conversion V196 de `_v184_next_occurrences`
    (`py = (js - 1) % 7`). Les deux formules sont ecrites l'une en face de
    l'autre volontairement : c'est le seul endroit du fichier ou la convention
    de `courses.weekday` est interpretee.
    """
    return (maintenant.weekday() + 1) % 7


def _a1_a_lieu_aujourdhui(cours: dict, jour_iso: str, jour_js: int) -> bool:
    """Ce cours a-t-il REELLEMENT lieu aujourd'hui ?

    Deux formes coexistent en base, exactement comme dans
    `_v184_next_occurrences` : `date` (ponctuel, prioritaire) et `weekday`
    (recurrent). Une `date` renseignee ferme la question — le cours n'a lieu
    que ce jour-la, et jamais chaque semaine.
    """
    _date = cours.get("date")
    if isinstance(_date, str) and _date.strip():
        return _date.strip()[:10] == jour_iso
    try:
        _w = int(cours.get("weekday"))
    except (TypeError, ValueError):
        return False
    return _w == jour_js


def _a1_datetime_occurrence(cours: dict, jour_iso: str, repli) -> str:
    """L'horodatage de l'occurrence du jour : la date du jour + l'heure du cours.

    Format NAIF local (« 2026-08-19T18:30:00 »), identique a celui de
    `_v184_next_occurrences` et des reservations de l'espace abonne. `_a0_horodatage`
    lit une valeur naive comme suisse : le moment designe est donc le bon.

    `repli` (l'instant du scan) ne sert que si le cours n'a pas d'heure
    exploitable — on prefere une reservation datee de l'instant du scan a une
    reservation sans date du tout.
    """
    _t = (cours.get("time") or "").strip()
    try:
        _h, _m = _t.split(":")[:2]
        _h, _m = int(_h), int(_m)
        if not (0 <= _h <= 23 and 0 <= _m <= 59):
            raise ValueError(_t)
    except (TypeError, ValueError):
        logger.warning("[A1] Cours %s sans heure exploitable (« %s ») — repli sur l'instant du scan",
                       cours.get("id"), _t)
        return repli.strftime("%Y-%m-%dT%H:%M:%S")
    return "%sT%02d:%02d:00" % (jour_iso, _h, _m)


def _a1_etiquette(cours: dict, jour_iso: str, jour_js: int) -> str:
    """Le libelle pret a afficher d'une occurrence — « Mer 18:30 · Silent ».

    Construit COTE SERVEUR, et c'est le point : les deux interfaces de scan
    (CoachDashboard et ChatWidget) indexaient chacune leur propre tableau de
    jours avec `courses.weekday`, en convention Python. Les 22 cours du
    catalogue s'affichaient donc sous un jour FAUX, decale d'un cran. Une seule
    source de verite supprime la classe de bug entiere.
    """
    _date = cours.get("date")
    if isinstance(_date, str) and _date.strip():
        _j = _date.strip()[:10]
    else:
        _j = jour_iso
    try:
        _d = datetime.strptime(_j, "%Y-%m-%d")
        _lib = A1_JOURS_JS[(_d.weekday() + 1) % 7]
    except (TypeError, ValueError):
        _lib = A1_JOURS_JS[jour_js]
    _heure = (cours.get("time") or "").strip()
    return ("%s %s" % (_lib, _heure)).strip()


async def _a1_occurrences_du_jour(coach_id: str, jour_iso: str, jour_js: int) -> list:
    """Les cours qui ont REELLEMENT lieu aujourd'hui, pour ce coach.

    Le filtre `weekday` n'est PAS pousse dans Mongo : les deux formes (`date`
    ponctuelle et `weekday` recurrent) ne se decrivent pas par le meme critere,
    et un `$or` sur des documents heterogenes serait plus fragile que 22
    documents tries en Python. Le repli « tous coachs » d'origine est conserve
    tel quel — le retirer ferait disparaitre les cours anterieurs a V244.
    """
    _base = {"visible": True, "archived": False}
    _tous = await db.courses.find(dict(_base, coach_id=coach_id), {"_id": 0}).to_list(200)
    if not _tous:
        _tous = await db.courses.find(dict(_base), {"_id": 0}).to_list(200)
    return [c for c in _tous if _a1_a_lieu_aujourdhui(c, jour_iso, jour_js)]


@reservation_router.post("/qr/scan-validate")
async def qr_scan_validate(request: Request):
    """V176/V213d: Scan QR coach — gère TOUS les types de codes."""
    try:
        return await _qr_scan_validate_inner(request)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[QR-V213d] ERREUR INTERNE: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur interne scanner: {type(e).__name__}: {str(e)}")


async def _qr_scan_validate_inner(request: Request):
    """V213d: Logique interne du scan QR."""
    # R11 — PREMIERE CHOSE FAITE, AVANT MEME DE LIRE LE CORPS : qui scanne ?
    # Un anonyme n'ecrit rien, ne cree rien, ne debite rien. La garde est unique
    # et couvre donc TOUS les cas de cette route (A a E), presents et futurs.
    _scanneur = await _r11_scanneur(request)

    body = await request.json()
    # A0-2 : le QR peut porter une URL (celui de l'e-mail de confirmation en
    # porte une). On en extrait le code AVANT toute normalisation de casse :
    # `.upper()` d'abord aurait casse les parametres d'URL sensibles a la casse.
    _brut = body.get("code", "") or ""
    _issu_url = str(_brut).strip().lower().startswith(("http://", "https://"))
    code = _a0_code_depuis_qr(_brut).strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Code requis")

    # V177: courseId optionnel pour override l'auto-détection
    forced_course_id = (body.get("courseId") or "").strip() or None

    # V213: Extraire le member_slug si le QR contient CODE::SLUG
    member_slug_from_qr = None
    if "::" in code:
        parts = code.split("::", 1)
        code = parts[0].strip().upper()
        member_slug_from_qr = parts[1].strip()
        logger.info(f"[QR-V213] Code avec slug détecté: code='{code}', slug='{member_slug_from_qr}'")
    else:
        logger.info(f"[QR-V213] Code simple: '{code}'")

    # CAS A : code de réservation existante
    reservation = await db.reservations.find_one({"reservationCode": code}, {"_id": 0})
    if reservation:
        if reservation.get("validated"):
            return {"success": True, "type": "reservation", "message": "Déjà validé",
                    "reservation": {"userName": reservation.get("userName", ""), "reservationCode": code,
                                    "courseName": reservation.get("courseName", ""), "validatedAt": reservation.get("validatedAt", "")}}
        # A0-2 : UNE PRESENCE SCANNEE SE CONSTATE LE JOUR MEME.
        #
        # PORTEE STRICTEMENT LIMITEE AU CHEMIN QU'A0 OUVRE (`_issu_url`), et
        # c'est delibere : un code saisi ou scanne BRUT garde exactement le
        # comportement d'avant, y compris la validation tardive d'une seance
        # d'hier — un geste volontaire du coach, que rien ne doit lui retirer.
        #
        # Ce qui change, c'est le QR de l'e-mail. Tant qu'il etait inexploitable
        # (il partait en « AFROBOOST », cf. l'en-tete A0), le cas ne se posait
        # pas ; le reparer l'ouvre. Or un cours RECURRENT produit une
        # reservation par occurrence, chacune avec SON e-mail et SON code :
        # presenter a la porte l'e-mail du 19/08 le 26/08 marquerait presente la
        # seance du 19/08 — exactement l'invariant « ne pas valider une autre
        # occurrence du meme cours ». Le refus est explicite : le staff doit
        # comprendre sans lire les journaux, et peut toujours saisir le code a
        # la main s'il veut vraiment valider une autre date.
        if _issu_url and not _a0_est_aujourdhui(reservation.get("datetime")):
            _jour = str(reservation.get("datetime") or "")[:10] or "une autre date"
            logger.info("[A0] Scan refuse : reservation %s datee du %s, pas d'aujourd'hui", code, _jour)
            raise HTTPException(
                status_code=400,
                detail=f"Cette réservation concerne le {_jour}, pas aujourd'hui.")
        # A0-3 : transition atomique + evenement de presence, exactement une fois.
        await _a0_marquer_presente(reservation, _scanneur)
        return {"success": True, "type": "reservation", "message": "Réservation validée",
                "reservation": {"userName": reservation.get("userName", ""), "reservationCode": code,
                                "courseName": reservation.get("courseName", "")}}

    # CAS B : code d'abonnement
    # V391 : le scan du QR à l'entrée DÉBITE une séance — il doit donc débiter le
    # BON forfait. Avec un code à doublons, il piochait dans le plus ancien (souvent
    # périmé) et refusait l'entrée d'un abonné à jour.
    from api.routes.shared import lire_abonnement_par_code as _v391_lire
    subscription = await _v391_lire(db, code)
    if subscription:
        # A0-1 — LA PRESENCE D'ABORD, LE CREDIT ENSUITE.
        #
        # Si une reservation existe deja pour aujourd'hui, la seance a ete
        # debitee au moment de la reserver : on constate la presence et on
        # s'arrete la. Aucun credit relu, aucun credit consomme.
        _presence = await _a0_presence_deja_reservee(subscription, code, member_slug_from_qr,
                                                     _scanneur)
        if _presence is not None:
            return _presence

        # V393 — INCHANGE, mais desormais a sa vraie place : on ne l'atteint
        # que si le scan s'apprete a CREER une reservation, donc a DEBITER.
        # C'est la raison d'etre du garde, ecrite dans son commentaire d'origine
        # (« le scan a l'entree DEBITE une seance »). L'appliquer avant la
        # recherche ci-dessus refusait a l'entree des gens dont la seance etait
        # deja payee et deja decomptee.
        from api.routes.shared import forfait_utilisable as _v393_ok
        _ok, _pourquoi = _v393_ok(subscription, 1)
        if not _ok:
            logger.info(f"[V393] Scan refuse sur {code} : {_pourquoi}")
            raise HTTPException(status_code=400, detail=_pourquoi)
    if not subscription:
        any_sub = await db.subscriptions.find_one({"code": code}, {"_id": 0})
        if any_sub:
            raise HTTPException(status_code=400, detail="Abonnement inactif ou expiré")

        # CAS C (V213): Code promo / groupe — cherche dans discount_codes
        logger.info(f"[QR-V213] CAS B échoué, recherche CAS C (discount_codes) pour code='{code}'")
        discount = await db.discount_codes.find_one(
            {"code": {"$regex": f"^{re.escape(code)}$", "$options": "i"}, "active": True}, {"_id": 0}
        )
        if discount:
            logger.info(f"[QR-V213] CAS C trouvé: discount code '{code}', multi_member={discount.get('multi_member')}, slug={member_slug_from_qr}")
            return await _validate_discount_code_presence(code, discount, member_slug_from_qr,
                                                          forced_course_id, _scanneur)

        # CAS C bis: discount_code inactif ?
        discount_any = await db.discount_codes.find_one(
            {"code": {"$regex": f"^{re.escape(code)}$", "$options": "i"}}, {"_id": 0}
        )
        if discount_any:
            logger.warning(f"[QR-V213] Discount code '{code}' trouvé mais inactif (active={discount_any.get('active')})")
            raise HTTPException(status_code=400, detail=f"Le code {code} est désactivé.")

        # CAS C ter (V213c): Si on a un member_slug, chercher directement dans code_members
        # Le code scanné pourrait être le code du groupe sous un nom différent
        if member_slug_from_qr:
            logger.info(f"[QR-V213] Recherche directe par slug '{member_slug_from_qr}' dans code_members")
            member_by_slug = await db.code_members.find_one(
                {"slug": {"$regex": f"^{re.escape(member_slug_from_qr)}$", "$options": "i"}}, {"_id": 0}
            )
            if member_by_slug:
                member_code = (member_by_slug.get("code") or "").upper()
                logger.info(f"[QR-V213] Membre trouvé via slug! code du membre='{member_code}', code scanné='{code}'")
                # Chercher le discount_code avec le vrai code du membre
                if member_code:
                    real_discount = await db.discount_codes.find_one(
                        {"code": {"$regex": f"^{re.escape(member_code)}$", "$options": "i"}, "active": True}, {"_id": 0}
                    )
                    if real_discount:
                        return await _validate_discount_code_presence(member_code, real_discount, member_slug_from_qr,
                                                                     forced_course_id, _scanneur)

        # CAS D (V213): Code d'accès utilisateur AFRO-XXXX — cherche dans users
        logger.info(f"[QR-V213] CAS C échoué, recherche CAS D (users.accessCode) pour code='{code}'")
        user_by_access = await db.users.find_one(
            {"accessCode": {"$regex": f"^{re.escape(code)}$", "$options": "i"}}, {"_id": 0}
        )
        if user_by_access:
            return await _validate_user_access_code(code, user_by_access, forced_course_id, _scanneur)

        # CAS E (V213c): Chercher dans les réservations par discountCode ou promoCode
        # Au cas où le code serait stocké sous un nom de champ différent
        logger.info(f"[QR-V213] Dernière tentative: recherche dans reservations par discountCode/promoCode")
        from datetime import timedelta as _td_e
        _swiss = timezone(_td_e(hours=2))
        _today = datetime.now(_swiss).strftime("%Y-%m-%d")
        # A1b : ce dernier recours cherchait UNE reservation du jour portant ce
        # code, sans rien verifier d'autre — exactement le trou repare plus haut
        # dans le chemin d'appariement. On lit desormais les candidates, on les
        # passe par la meme garde, et on retient la premiere qui designe une
        # seance reelle. `find_one` est devenu `find(...).to_list(20)` : meme
        # requete, meme filtre, seule la garde s'ajoute.
        _cas_e = await db.reservations.find({
            "$or": [
                {"discountCode": {"$regex": f"^{re.escape(code)}$", "$options": "i"}},
                {"promoCode": {"$regex": f"^{re.escape(code)}$", "$options": "i"}}
            ],
            "datetime": {"$regex": _today}
        }, {"_id": 0}).to_list(20)
        _cas_e = await _a1b_occurrences_reelles(_cas_e)
        direct_res = _cas_e[0] if _cas_e else None
        if direct_res:
            if not direct_res.get("validated"):
                # R11/A0 : meme helper — propriete, atomicite, funnel.
                await _a0_marquer_presente(direct_res, _scanneur)
                logger.info(f"[QR-V213] CAS E: Réservation trouvée directement par code '{code}'")
                return {"success": True, "type": "reservation", "message": "Présence validée !",
                        "reservation": {"userName": direct_res.get("userName", ""), "reservationCode": direct_res.get("reservationCode", code),
                                        "courseName": direct_res.get("courseName", "")}}
            return {"success": True, "type": "reservation", "message": "Déjà validé",
                    "reservation": {"userName": direct_res.get("userName", ""), "reservationCode": direct_res.get("reservationCode", code),
                                    "courseName": direct_res.get("courseName", "")}}

        logger.warning(f"[QR-V213d] Aucun CAS ne correspond pour code='{code}' (slug={member_slug_from_qr})")
        raise HTTPException(status_code=404, detail=f"[V213d] Code '{code}' introuvable (slug={member_slug_from_qr}). Aucun résultat dans reservations, subscriptions, discount_codes, users.")

    remaining = int(subscription.get("remaining_sessions", 0))
    if remaining <= 0:
        raise HTTPException(status_code=400, detail="Plus de séances disponibles")

    user_email = (subscription.get("email") or "").lower().strip()
    user_name = subscription.get("name") or subscription.get("userName") or "Abonné"
    sub_id = subscription.get("id")

    from datetime import timedelta as _td
    swiss_tz = timezone(_td(hours=2))
    now_swiss = datetime.now(swiss_tz)
    coach_id = subscription.get("coach_id") or DEFAULT_COACH_ID  # V244

    # A1-1/A1-2 : les cours qui ont REELLEMENT lieu aujourd'hui — bonne
    # convention de jour, et une date fixe passee ne revient plus chaque semaine.
    _a1_jour_iso = now_swiss.strftime("%Y-%m-%d")
    _a1_js = _a1_jour_js(now_swiss)
    courses = await _a1_occurrences_du_jour(coach_id, _a1_jour_iso, _a1_js)

    target_course = None
    # V177: si le coach a forcé un cours via UI, on l'utilise direct
    if forced_course_id:
        # A1-2 : le choix manuel est borne A LA MEME LISTE que l'auto-detection.
        # Il acceptait auparavant N'IMPORTE QUEL cours non archive du catalogue :
        # le coach pouvait, sans le vouloir, creer une reservation et DEBITER une
        # seance sur un cours qui n'avait pas lieu ce jour-la. Le scan constate
        # une presence — il ne peut la constater que sur une seance du jour.
        target_course = next((c for c in courses if c.get("id") == forced_course_id), None)
        if not target_course:
            _a1_existe = await db.courses.find_one({"id": forced_course_id}, {"_id": 0, "name": 1})
            raise HTTPException(
                status_code=400 if _a1_existe else 404,
                detail=("Ce cours n'a pas lieu aujourd'hui — impossible d'y valider une présence."
                        if _a1_existe else "Cours sélectionné introuvable"))
    else:
        best_diff = 9999
        for c in courses:
            ctime = (c.get("time") or "").strip()
            if not ctime:
                continue
            try:
                ch, cm = ctime.split(":")
                ch, cm = int(ch), int(cm)
                cdt = now_swiss.replace(hour=ch, minute=cm, second=0, microsecond=0)
                diff = abs((cdt - now_swiss).total_seconds() / 60)
                if diff <= 90 and diff < best_diff:
                    target_course = c
                    best_diff = diff
            except Exception:
                continue
        if not target_course:
            # A1-1 : la liste de secours est construite ICI, deja filtree sur le
            # jour et deja etiquetee. Les deux interfaces de scan la rendaient
            # chacune de leur cote, en indexant un tableau de jours francais avec
            # `courses.weekday` — donc en convention Python sur une donnee ecrite
            # en convention JavaScript : les 22 cours s'affichaient sous un jour
            # faux. Une seule source de verite supprime la classe de bug.
            raise HTTPException(
                status_code=422,
                detail={"error": "no_course_now",
                        "message": ("Aucun cours en cours actuellement. Sélectionnez un cours du jour."
                                    if courses else
                                    "Aucun cours ne figure à l'agenda d'aujourd'hui."),
                        "courses": [{"id": c.get("id"), "name": c.get("name") or "Cours",
                                     "time": (c.get("time") or "").strip(),
                                     "label": _a1_etiquette(c, _a1_jour_iso, _a1_js)}
                                    for c in courses]}
            )

    # R11 : creer une reservation et DEBITER une seance sur le cours d'un autre
    # coach est le geste le plus lourd de cette route. La propriete se verifie
    # ici sur le COURS (22 cours sur 22 portent un `coach_id` en production).
    _r11_verifier_proprietaire(_scanneur, target_course, "cours")
    course_id = target_course.get("id")
    course_name = target_course.get("name") or "Cours"
    course_time = target_course.get("time") or ""
    # A1 : un seul calcul du jour dans cette route (`_a1_jour_iso`). `today_str`
    # en etait une seconde copie — deux sources pour la meme date, c'est une
    # divergence en attente.
    today_str = _a1_jour_iso

    existing = await db.reservations.find_one({"userEmail": user_email, "courseId": course_id, "datetime": {"$regex": today_str}}, {"_id": 0})

    if existing:
        # A0-1/A0-3 : ce filet reste en place (aucun code retire). Il n'est
        # atteint que si `_a0_presence_deja_reservee` a renonce — deux seances
        # le meme jour et aucune dans la tolerance. La validation passe par le
        # meme helper atomique, pour que l'evenement de presence parte ici aussi
        # et exactement une fois.
        if not existing.get("validated"):
            await _a0_marquer_presente(existing, _scanneur)
        return {"success": True, "type": "subscription", "message": "Présence validée (résa déjà existante)",
                "reservation": {"userName": user_name, "reservationCode": existing.get("reservationCode", code), "courseName": course_name},
                "subscriber": {"name": user_name, "remaining": remaining, "total": subscription.get("total_sessions", remaining)}}

    new_remaining = remaining - 1
    new_used = int(subscription.get("used_sessions", 0)) + 1
    sub_update = {"remaining_sessions": new_remaining, "used_sessions": new_used, "updated_at": datetime.now(timezone.utc).isoformat()}
    if new_remaining <= 0:
        sub_update["status"] = "completed"
    await db.subscriptions.update_one({"id": sub_id}, {"$set": sub_update})

    new_res_code = _generate_afro_code()
    new_reservation = {
        "id": str(uuid.uuid4()), "reservationCode": new_res_code,
        "userId": subscription.get("userId", ""), "userName": user_name, "userEmail": user_email,
        "userWhatsapp": subscription.get("whatsapp", ""), "courseId": course_id, "courseName": course_name,
        # A1-3 : la reservation designe L'OCCURRENCE (date du jour + heure du
        # cours), plus l'instant du scan. Format naif local, comme V196 et comme
        # l'espace abonne — une seule convention dans toute la base.
        "courseTime": course_time,
        "datetime": _a1_datetime_occurrence(target_course, _a1_jour_iso, now_swiss),
        "offerId": course_id, "offerName": course_name, "price": 0, "quantity": 1, "totalPrice": 0,
        "subscriptionId": sub_id, "promoCode": code, "source": "qr_scan_coach", "type": "abonné",
        "validated": True, "validatedAt": datetime.now(timezone.utc).isoformat(),
        "createdAt": datetime.now(timezone.utc).isoformat(), "coach_id": coach_id
    }
    await db.reservations.insert_one(new_reservation)
    logger.info(f"[QR-SCAN-V176] Création résa + déduction: {user_email} -> {course_name} ({new_remaining} restantes)")
    # A0-3 : ce chemin cree une reservation DEJA validee — c'est une presence
    # constatee, elle doit entrer dans le funnel comme les autres. On appelle
    # `_c9_presence` directement (et non `_a0_marquer_presente`) : le document
    # vient d'etre insere avec `validated: True`, il n'y a pas de transition a
    # arbitrer. `_c9_presence` n'echoue jamais et ne bloque rien.
    await _c9_presence(new_reservation, False)

    return {"success": True, "type": "subscription", "message": "Réservation créée + séance déduite",
            "reservation": {"userName": user_name, "reservationCode": new_res_code, "courseName": course_name},
            "subscriber": {"name": user_name, "remaining": new_remaining, "total": subscription.get("total_sessions", new_remaining + new_used)}}


# === EXPORT PRÉSENCES (CSV) ===
@reservation_router.get("/reservations/export/attendance")
async def export_attendance(request: Request, date: str = "", course: str = ""):
    """Exporte la liste des présences (réservations validées) au format CSV.
    Paramètres optionnels: date (YYYY-MM-DD), course (nom du cours).
    Le frontend peut convertir en Excel ou PDF.

    V2-0 : route FERMÉE. Elle répondait 200 à un anonyme et rendait un CSV
    `Nom, Email, WhatsApp, Cours, Date, Code, Validé le` — le fichier le plus
    nominatif du dépôt. Cas particulier : `request` ÉTAIT déjà dans la signature,
    il n'était simplement jamais lu. La garde était à un appel de distance.

    Jeton signé exigé, sans repli : `export/attendance` a 0 occurrence dans
    `frontend/src`, et aucun composant ne télécharge ce CSV.

    ⚠️ CONSÉQUENCE À ASSUMER, PAS À ADOUCIR. `coach_jwt_email` ne lit QUE
    l'en-tête `Authorization: Bearer`. Or le jeton vit dans `localStorage`, pas
    dans un cookie : une URL collée dans la barre d'adresse n'envoie JAMAIS cet
    en-tête, même après reconnexion. Si quelqu'un téléchargeait ce fichier à la
    main, cet usage est donc SUPPRIMÉ, pas sécurisé. C'est un choix : un export
    nominatif (nom, e-mail, WhatsApp) ne peut pas rester ouvert au premier venu.
    Le rétablir demandera un bouton dans le dashboard, qui passera l'en-tête —
    ce sera un autre lot.

    Le périmètre coach entre AUSSI dans la requête : `query` ne portait aucun
    `coach_id`, donc même authentifiée la route aurait laissé un coach exporter
    les présences d'un autre. `{}` pour le super-admin -> export inchangé.
    """
    from api.routes.shared import (v20_exiger_coach_signe, v20_perimetre_contacts,
                                   V20AccesRefuse)
    _appelant = await v20_exiger_coach_signe(request, db, "export des présences")
    try:
        _perimetre = v20_perimetre_contacts(_appelant)
    except V20AccesRefuse:
        raise HTTPException(status_code=403, detail="Authentification coach requise")
    query = {"validated": True}
    query.update(_perimetre)
    if date:
        query["selectedDatesText"] = {"$regex": date, "$options": "i"}
    if course:
        query["courseName"] = {"$regex": course, "$options": "i"}

    reservations = await db.reservations.find(query, {"_id": 0}).sort("validatedAt", -1).to_list(500)

    # Construire le CSV
    import io, csv
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Nom", "Email", "WhatsApp", "Cours", "Date", "Code", "Validé le"])
    for r in reservations:
        writer.writerow([
            r.get("userName", ""),
            r.get("userEmail", ""),
            r.get("userWhatsapp", ""),
            r.get("courseName", r.get("offerName", "")),
            r.get("selectedDatesText", ""),
            r.get("reservationCode", ""),
            r.get("validatedAt", "")
        ])

    from fastapi.responses import StreamingResponse
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=presences.csv"}
    )


@reservation_router.get("/my-access-code")
async def get_my_access_code(request: Request, email: str = ""):
    """v158: Retourne le code AFRO-XXXX permanent d'un utilisateur par email.

    V2-0b : route FERMÉE. Elle rendait `accessCode` + `name` contre un simple
    e-mail, sans aucune authentification ni limitation de débit. Elle n'avait pas
    de paramètre `Request` : l'authentification y était structurellement
    impossible, pas seulement oubliée. Même famille que la faille V389, restée
    ouverte parce qu'elle vise une AUTRE collection (`users`, pas
    `discount_codes`) et qu'elle a échappé au nettoyage.

    CE QUE CE CODE EST VRAIMENT. `users.accessCode` est un `AFRO-XXXX` de 4
    caractères — le code de CONVERSATION, pas le code d'abonnement `AFR-XXXXXX`.
    Il vaut quand même justificatif : le CAS D du scan QR (`_validate_user_access_code`)
    valide une présence avec lui. Le voler, c'est entrer au cours à la place de
    quelqu'un.

    JETON SIGNÉ EXIGÉ, SANS REPLI, et le risque est nul : la route n'a AUCUN
    appelant. Zéro occurrence dans `frontend/src`, zéro dans le bundle déployé
    source-maps comprises, zéro dans les tests, la CI et le crontab VPS, et
    `git log --all -S` côté frontend est vide depuis sa création (v158, avril
    2026). C'est du code mort qui expose un secret vivant — 2 comptes concernés
    sur 110.

    AUCUNE FONCTIONNALITÉ N'EST PERDUE. Le recours d'un client ayant perdu son
    code existe déjà, ailleurs, et il est meilleur : bouton « Code perdu ? »
    (`ChatWidget.js:8804`) -> `POST /subscriber/recover`, qui envoie le code
    PAR E-MAIL à l'adresse enregistrée, avec limitation à 3 tentatives/10 min,
    et ne rend jamais le secret dans la réponse HTTP. C'est le mécanisme V389.
    """
    from api.routes.shared import v20_exiger_coach_signe
    await v20_exiger_coach_signe(request, db, "lecture d'un code d'accès")
    if not email:
        raise HTTPException(status_code=400, detail="Email requis")
    user = await db.users.find_one({"email": email.lower().strip()}, {"_id": 0, "accessCode": 1, "name": 1, "email": 1})
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return {"email": user.get("email"), "name": user.get("name"), "accessCode": user.get("accessCode")}


@reservation_router.post("/check-reservation-eligibility")
async def check_reservation_eligibility(request: Request):
    """Vérifie si un utilisateur peut réserver (abonné actif ou code promo valide)"""
    body = await request.json()
    email = body.get("email", "").lower().strip()
    code = body.get("code", "").strip()
    if not email and not code:
        return {"eligible": False, "reason": "Email ou code requis"}
    # Chercher par code
    if code:
        discount = await db.discount_codes.find_one({"code": {"$regex": f"^{re.escape(code)}$", "$options": "i"}, "active": True}, {"_id": 0})
        if discount:
            return {"eligible": True, "discount": discount, "type": "discount_code"}
    # Chercher par email (abonné actif)
    if email:
        subscriber = await db.chat_participants.find_one({"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}}, {"_id": 0})
        if subscriber and subscriber.get("isSubscriber"):
            return {"eligible": True, "subscriber": {"name": subscriber.get("name"), "email": subscriber.get("email")}, "type": "subscriber"}
    return {"eligible": False, "reason": "Aucun abonnement ou code valide trouvé"}
