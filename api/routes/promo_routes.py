# promo_routes.py - Routes de codes promo v9.2.0
# Extrait de server.py pour modularisation
# v9.3.0: Ajout isolation par coach_id
# v96: Email bienvenue + renforcement unicité

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime, timezone
import uuid
import logging
import asyncio
import os

logger = logging.getLogger(__name__)

# === v96: Email infrastructure ===
try:
    import resend
    _RESEND_OK = True
except ImportError:
    _RESEND_OK = False

_RESEND_KEY = os.environ.get('RESEND_API_KEY', '')


async def _send_welcome_email(user_email: str, user_name: str, code_str: str, offer_name: str, total_sessions: int):
    """Envoie un email de bienvenue quand un code est validé pour la première fois"""
    if not _RESEND_OK or not _RESEND_KEY:
        return
    resend.api_key = _RESEND_KEY

    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=https://afroboost.com/?qr={code_str}&format=png"

    html = f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0a0a0a;">
        <div style="background:linear-gradient(135deg,#d91cd2,#8b5cf6);padding:24px;text-align:center;">
            <h1 style="color:white;margin:0;font-size:22px;">Bienvenue chez Afroboost !</h1>
        </div>
        <div style="padding:24px;color:#fff;">
            <p style="color:#a855f7;font-size:16px;line-height:1.6;">
                Hey {user_name} ! Ton code personnel a bien été activé. Voici tes infos :
            </p>
            <div style="background:rgba(217,28,210,0.1);border:1px solid rgba(217,28,210,0.3);border-radius:12px;padding:20px;margin:20px 0;text-align:center;">
                <p style="margin:0 0 8px;color:#888;">Ton code d'accès personnel</p>
                <p style="margin:0;color:#d91cd2;font-size:28px;font-weight:bold;letter-spacing:3px;">{code_str}</p>
                <p style="margin:12px 0 4px;color:#fff;font-size:15px;">{offer_name}</p>
                <p style="margin:0;color:#a855f7;font-size:14px;">{total_sessions} séance{"s" if total_sessions > 1 else ""} disponible{"s" if total_sessions > 1 else ""}</p>
            </div>
            <div style="text-align:center;margin:24px 0;">
                <p style="color:#888;margin-bottom:12px;font-size:13px;">Ton QR Code personnel</p>
                <img src="{qr_url}" alt="QR Code" width="140" height="140" style="background:white;padding:8px;border-radius:8px;display:block;margin:0 auto;"/>
                <p style="color:#a855f7;font-size:12px;margin-top:8px;">Ce code est uniquement réservé à toi.</p>
            </div>
            <div style="background:rgba(147,51,234,0.1);border-radius:8px;padding:14px;margin:16px 0;">
                <p style="margin:0;color:#a855f7;font-size:13px;font-weight:bold;">Comment ça marche ?</p>
                <p style="margin:8px 0 0;color:#ccc;font-size:13px;line-height:1.5;">
                    1. Ouvre le chat sur afroboost.com<br>
                    2. Entre ton code <strong style="color:#d91cd2;">{code_str}</strong> pour t'identifier<br>
                    3. Réserve un cours ou une offre<br>
                    4. Présente ton QR Code à l'entrée
                </p>
            </div>
            <div style="text-align:center;margin:24px 0;">
                <a href="https://afroboost.com" style="display:inline-block;background:#d91cd2;color:white;padding:12px 24px;text-decoration:none;border-radius:8px;font-weight:bold;font-size:14px;">Accéder à mon espace</a>
            </div>
            <p style="color:#666;font-size:11px;text-align:center;margin-top:24px;">Ce code est personnel et ne peut pas être partagé. Conserve cet email précieusement.</p>
        </div>
    </div>"""

    try:
        await asyncio.to_thread(resend.Emails.send, {
            "from": "Afroboost <notifications@afroboosteur.com>",
            "to": [user_email],
            "subject": f"Ton code Afroboost — {code_str}",
            "html": html
        })
        logger.info(f"[EMAIL] Bienvenue envoyé à {user_email} pour code {code_str}")
    except Exception as e:
        logger.warning(f"[EMAIL] Erreur envoi bienvenue: {e}")

# Super Admin email - pas de filtre
SUPER_ADMIN_EMAIL = "contact.artboost@gmail.com"

# Router avec préfixe /discount-codes
promo_router = APIRouter(prefix="/discount-codes", tags=["Promo Codes"])

# Référence DB (initialisée depuis server.py)
_db = None

def init_promo_db(database):
    """Initialise la référence DB"""
    global _db
    _db = database
    logger.info("[PROMO_ROUTES] Base de données initialisée")


# === MODÈLES ===
class DiscountCode(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    code: str
    type: str  # "100%", "%", "CHF"
    value: float
    assignedEmail: Optional[str] = None
    expiresAt: Optional[str] = None
    courses: List[str] = []
    maxUses: Optional[int] = None
    used: int = 0
    active: bool = True
    coach_id: Optional[str] = None  # v9.3.0: Isolation par coach


class DiscountCodeCreate(BaseModel):
    code: str
    type: str
    value: float
    assignedEmail: Optional[str] = None
    expiresAt: Optional[str] = None
    courses: List[str] = []
    maxUses: Optional[int] = None
    coach_id: Optional[str] = None  # v9.3.0: Isolation par coach


# === v104: HELPER — Résoudre les détails de l'offre liée à un code ===
async def _resolve_offer_details(courses_list, max_uses):
    """Détermine le nombre de séances et le nom de l'offre en se basant sur l'article autorisé.
    Règle v104: Plus de défaut 10 séances. Le crédit vient de l'article ou de maxUses."""
    offer_name = "Abonnement"
    offer_price = None
    total_sessions = max_uses  # Utiliser maxUses tel quel (peut être None)

    if courses_list and _db is not None:
        # Chercher la première offre liée
        for course_id in courses_list:
            offer = await _db.offers.find_one({"id": course_id}, {"_id": 0})
            if offer:
                offer_name = offer.get("name", offer_name)
                offer_price = offer.get("price")
                # v104: Déduire les séances du nom de l'offre si maxUses non défini
                if total_sessions is None:
                    name_lower = offer_name.lower()
                    # Patterns: "x10", "x5", "x20", "× 10", etc.
                    import re
                    match = re.search(r'[x×]\s*(\d+)', name_lower)
                    if match:
                        total_sessions = int(match.group(1))
                    elif 'unit' in name_lower or 'à l\'unité' in name_lower or 'unique' in name_lower:
                        total_sessions = 1
                break  # On prend la première offre

    # v104: Si toujours None après résolution, défaut = 1 (pas 10)
    if total_sessions is None:
        total_sessions = 1

    return total_sessions, offer_name, offer_price


# === v106.9: HELPER — Sanitize MongoDB docs for JSON serialization ===
def _sanitize_mongo_doc(doc):
    """Convertit les types non-sérialisables (datetime, ObjectId, bytes) en strings JSON-safe"""
    if not isinstance(doc, dict):
        return doc
    sanitized = {}
    for key, value in doc.items():
        if isinstance(value, datetime):
            sanitized[key] = value.isoformat()
        elif isinstance(value, dict):
            sanitized[key] = _sanitize_mongo_doc(value)
        elif isinstance(value, list):
            sanitized[key] = [_sanitize_mongo_doc(v) if isinstance(v, dict) else (v.isoformat() if isinstance(v, datetime) else str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v) for v in value]
        elif not isinstance(value, (str, int, float, bool, type(None), list)):
            sanitized[key] = str(value)  # ObjectId, bytes, etc.
        else:
            sanitized[key] = value
    return sanitized


# === ROUTES ===
@promo_router.get("")
async def get_discount_codes(request: Request):
    """Récupère les codes promo - filtrés par coach_id sauf Super Admin"""
    user_email = request.headers.get('X-User-Email', '').lower().strip()
    is_super_admin = user_email == SUPER_ADMIN_EMAIL.lower()
    
    # Super Admin voit tous les codes, coach voit seulement les siens
    query = {} if is_super_admin else {"$or": [
        {"coach_id": user_email},
        {"coach_id": None},  # Codes sans coach_id (legacy)
        {"coach_id": {"$exists": False}}
    ]}
    
    codes = await _db.discount_codes.find(query, {"_id": 0}).to_list(1000)
    return codes


@promo_router.post("")
async def create_discount_code(code: DiscountCodeCreate, request: Request):
    """Crée un nouveau code promo avec coach_id — v96: auto-crée la subscription si bénéficiaire assigné"""
    user_email = request.headers.get('X-User-Email', '').lower().strip()
    is_super_admin = user_email == SUPER_ADMIN_EMAIL.lower()

    code_data = code.model_dump()
    # v9.3.0: Assigner le coach_id si pas Super Admin
    if not is_super_admin and user_email:
        code_data["coach_id"] = user_email

    code_obj = DiscountCode(**code_data)
    await _db.discount_codes.insert_one(code_obj.model_dump())

    # v96: Auto-créer la subscription si un bénéficiaire est assigné
    # v104: Résolution dynamique des séances via l'article lié
    assigned_email = (code.assignedEmail or "").lower().strip()
    if assigned_email:
        code_str = code.code.upper().strip()
        total_sessions, offer_name, offer_price = await _resolve_offer_details(code.courses, code.maxUses)

        # Vérifier qu'il n'y a pas déjà un abonnement actif pour ce code + email
        existing = await _db.subscriptions.find_one({
            "email": assigned_email,
            "code": {"$regex": f"^{code_str}$", "$options": "i"},
            "status": "active"
        })
        if not existing:
            expiry = None
            if code.expiresAt:
                try:
                    exp_str = code.expiresAt
                    if 'T' not in exp_str:
                        exp_str = exp_str + "T23:59:59+00:00"
                    expiry = exp_str
                except Exception:
                    expiry = code.expiresAt

            sub_data = {
                "id": str(uuid.uuid4()),
                "email": assigned_email,
                "name": assigned_email.split("@")[0],
                "code": code_str,
                "offer_name": offer_name,
                "offer_price": offer_price,
                "total_sessions": total_sessions,
                "used_sessions": 0,
                "remaining_sessions": total_sessions,
                "expires_at": expiry,
                "status": "active",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "source": "admin_manual"
            }
            await _db.subscriptions.insert_one(sub_data)
            logger.info(f"[PROMO] Subscription auto-créée: {assigned_email} - {code_str} ({total_sessions} séances)")
            # Envoyer email de bienvenue
            asyncio.create_task(_send_welcome_email(
                assigned_email, assigned_email.split("@")[0],
                code_str, offer_name, total_sessions
            ))

    return code_obj


@promo_router.put("/{code_id}")
async def update_discount_code(code_id: str, updates: dict):
    """Met à jour un code promo"""
    await _db.discount_codes.update_one({"id": code_id}, {"$set": updates})
    updated = await _db.discount_codes.find_one({"id": code_id}, {"_id": 0})
    return updated


@promo_router.delete("/{code_id}")
async def delete_discount_code(code_id: str):
    """Supprime un code promo"""
    await _db.discount_codes.delete_one({"id": code_id})
    return {"success": True}


@promo_router.post("/validate")
async def validate_discount_code(data: dict):
    """Valide un code promo et crée/met à jour l'abonnement v11.4 — v106.9: fix JSON serialization"""
    try:
        code_str = data.get("code", "").strip().upper()  # Normalize: trim + uppercase
        user_email = data.get("email", "").strip().lower()
        user_name = data.get("name", "").strip()
        course_id = data.get("courseId", "").strip() if data.get("courseId") else ""

        # Case-insensitive search using regex
        code = await _db.discount_codes.find_one({
            "code": {"$regex": f"^{code_str}$", "$options": "i"},  # Case insensitive match
            "active": True
        }, {"_id": 0})

        if not code:
            return {"valid": False, "message": "Code inconnu ou invalide"}

        # v106.9: Sanitize MongoDB doc — convert datetime/non-serializable to strings
        code = _sanitize_mongo_doc(code)

        # Check expiration date
        expiry_date = None
        if code.get("expiresAt"):
            try:
                expiry = code["expiresAt"]
                if isinstance(expiry, str):
                    # Handle various date formats
                    expiry = expiry.replace('Z', '+00:00')
                    if 'T' not in expiry:
                        expiry = expiry + "T23:59:59+00:00"
                    expiry_date = datetime.fromisoformat(expiry)
                elif isinstance(expiry, datetime):
                    expiry_date = expiry
                # v106.9: Ensure timezone-aware comparison
                now_utc = datetime.now(timezone.utc)
                if expiry_date:
                    if expiry_date.tzinfo is None:
                        expiry_date = expiry_date.replace(tzinfo=timezone.utc)
                    if expiry_date < now_utc:
                        return {"valid": False, "message": "Code promo expiré"}
            except Exception as e:
                logger.warning(f"[VALIDATE] Date parsing error for code {code_str}: {e}")

        # Check max uses (global)
        if code.get("maxUses") and code.get("used", 0) >= code["maxUses"]:
            return {"valid": False, "message": "Code promo épuisé (nombre max d'utilisations atteint)"}

        # Check if course is allowed - SKIP if no courseId provided (identification flow)
        allowed_courses = code.get("courses", [])
        if course_id and allowed_courses and len(allowed_courses) > 0:
            if course_id not in allowed_courses:
                return {"valid": False, "message": "Code non applicable à ce cours"}

        # Check assigned email (only if assignedEmail is set AND email is provided)
        assigned = code.get("assignedEmail") or ""
        if assigned and isinstance(assigned, str):
            assigned = assigned.strip()
            if assigned and user_email:
                if assigned.lower() != user_email.lower():
                    return {"valid": False, "message": "Code réservé à un autre compte"}

        # v96: Si le code n'est assigné à personne, le verrouiller au premier utilisateur
        if (not assigned or (isinstance(assigned, str) and not assigned.strip())) and user_email:
            await _db.discount_codes.update_one(
                {"code": {"$regex": f"^{code_str}$", "$options": "i"}},
                {"$set": {"assignedEmail": user_email}}
            )
            logger.info(f"[PROMO] Code {code_str} verrouillé pour {user_email} (premier utilisateur)")

        # === v104: CRÉER/METTRE À JOUR L'ABONNEMENT — résolution dynamique via article ===
        if user_email:
            # v104: Résolution dynamique — plus de défaut 10 séances
            courses_list = code.get("courses") or []
            raw_max = code.get("maxUses") or code.get("sessions") or None
            total_sessions, offer_name, offer_price = await _resolve_offer_details(courses_list, raw_max)
            # Fallback nom: code name > code string
            if offer_name == "Abonnement":
                offer_name = code.get("name") or code.get("code") or "Abonnement"

            # Vérifier si l'abonné a déjà un abonnement actif avec CE code
            existing_sub = await _db.subscriptions.find_one({
                "email": user_email,
                "code": code_str,
                "status": "active"
            }, {"_id": 0})

            if not existing_sub:
                # Créer un nouvel abonnement
                subscription_data = {
                    "id": str(uuid.uuid4()),
                    "email": user_email,
                    "name": user_name or user_email.split("@")[0],
                    "code": code_str,
                    "offer_name": offer_name,
                    "offer_price": offer_price,
                    "total_sessions": total_sessions,
                    "used_sessions": 0,
                    "remaining_sessions": total_sessions,
                    "expires_at": expiry_date.isoformat() if expiry_date else None,
                    "status": "active",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
                await _db.subscriptions.insert_one(subscription_data)
                logger.info(f"[SUBSCRIPTION] Créé: {user_email} - {offer_name} ({total_sessions} séances)")
                # v96: Email de bienvenue à la première activation
                asyncio.create_task(_send_welcome_email(
                    user_email, user_name or user_email.split("@")[0],
                    code_str, offer_name, total_sessions
                ))
            else:
                logger.info(f"[SUBSCRIPTION] Existant: {user_email} - {existing_sub.get('remaining_sessions')} séances restantes")

            # Sync CRM
            await _db.chat_participants.update_one(
                {"email": user_email},
                {
                    "$set": {
                        "email": user_email,
                        "name": user_name or user_email.split("@")[0],
                        "source": "chat_login",
                        "isSubscriber": True,
                        "subscriptionCode": code_str,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    },
                    "$setOnInsert": {
                        "id": str(uuid.uuid4()),
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                },
                upsert=True
            )

        # Enrichir la réponse avec les infos d'abonnement
        subscription_info = None
        if user_email:
            sub = await _db.subscriptions.find_one({"email": user_email, "code": code_str, "status": "active"}, {"_id": 0})
            if sub:
                sub = _sanitize_mongo_doc(sub)
                subscription_info = {
                    "offer_name": sub.get("offer_name"),
                    "offer_price": sub.get("offer_price"),
                    "total_sessions": sub.get("total_sessions"),
                    "used_sessions": sub.get("used_sessions", 0),
                    "remaining_sessions": sub.get("remaining_sessions"),
                    "expires_at": sub.get("expires_at")
                }

        return {"valid": True, "code": code, "subscription": subscription_info}

    except Exception as e:
        logger.error(f"[VALIDATE] Erreur validation code {data.get('code', '?')}: {type(e).__name__}: {e}")
        return {"valid": False, "message": f"Erreur serveur lors de la validation"}


@promo_router.post("/{code_id}/use")
async def use_discount_code(code_id: str):
    """Marque un code promo comme utilisé (décompte géré par create_reservation)"""
    return {"success": True, "note": "Decompte gere par create_reservation"}


# === v11.4: ENDPOINTS SUBSCRIPTIONS (ABONNEMENTS) ===
@promo_router.get("/subscriptions/status")
async def get_subscription_status(email: str = "", code: str = ""):
    """Récupère le statut d'abonnement d'un utilisateur v11.4 — v95/v151: retourne UNIQUEMENT les abonnements dont le code promo est encore actif et assigné"""
    if not email and not code:
        return {"success": False, "message": "Email ou code requis"}

    query = {"status": "active"}
    if email:
        query["email"] = email.lower().strip()
    if code:
        query["code"] = code.upper().strip()

    # v95: Récupérer TOUS les abonnements actifs (pas juste le premier)
    all_subs = await _db.subscriptions.find(query, {"_id": 0}).to_list(50)

    if not all_subs:
        return {
            "success": False,
            "hasSubscription": False,
            "message": "Aucun abonnement actif"
        }

    # v151: FILTRAGE — ne garder que les abonnements dont le code promo est encore actif
    # ET assigné à cet utilisateur (ou sans restriction d'email)
    verified_subs = []
    seen_codes = set()  # Déduplication par code
    user_email = email.lower().strip() if email else ""

    for sub in all_subs:
        sub_code = sub.get("code", "")
        if not sub_code:
            continue

        # Déduplier par code (garder le premier = le plus ancien)
        code_key = sub_code.upper()
        if code_key in seen_codes:
            continue

        # Vérifier que le discount_code existe et est encore actif
        discount = await _db.discount_codes.find_one({
            "code": {"$regex": f"^{sub_code}$", "$options": "i"},
            "active": True
        }, {"_id": 0, "assignedEmail": 1, "active": 1})

        if not discount:
            # Code promo désactivé ou supprimé → ignorer cette subscription
            logger.info(f"[SUBSCRIPTION v151] Ignoré {sub_code} pour {user_email}: code promo inactif/supprimé")
            continue

        # Vérifier que le code est bien assigné à cet utilisateur (si assignedEmail est défini)
        assigned = (discount.get("assignedEmail") or "").lower().strip()
        if assigned and user_email and assigned != user_email:
            # Code assigné à quelqu'un d'autre → ignorer
            logger.info(f"[SUBSCRIPTION v151] Ignoré {sub_code} pour {user_email}: assigné à {assigned}")
            continue

        seen_codes.add(code_key)
        verified_subs.append(sub)

    if not verified_subs:
        return {
            "success": False,
            "hasSubscription": False,
            "message": "Aucun abonnement actif"
        }

    def format_sub(s):
        return {
            "id": s.get("id"),
            "email": s.get("email"),
            "name": s.get("name"),
            "code": s.get("code"),
            "offer_name": s.get("offer_name"),
            "offer_price": s.get("offer_price"),
            "total_sessions": s.get("total_sessions"),
            "used_sessions": s.get("used_sessions", 0),
            "remaining_sessions": s.get("remaining_sessions"),
            "expires_at": s.get("expires_at"),
            "status": s.get("status")
        }

    # Rétro-compatible : "subscription" = premier résultat
    return {
        "success": True,
        "hasSubscription": True,
        "subscription": format_sub(verified_subs[0]),
        "subscriptions": [format_sub(s) for s in verified_subs]
    }


@promo_router.post("/subscriptions/deduct")
async def deduct_session(data: dict):
    """Déduit une séance de l'abonnement v11.4"""
    email = data.get("email", "").lower().strip()
    code = data.get("code", "").upper().strip()
    
    if not email:
        return {"success": False, "message": "Email requis"}
    
    # Chercher l'abonnement actif
    query = {"email": email, "status": "active"}
    if code:
        query["code"] = code
    
    subscription = await _db.subscriptions.find_one(query, {"_id": 0})
    
    if not subscription:
        return {"success": False, "message": "Aucun abonnement actif", "remaining": 0}
    
    remaining = subscription.get("remaining_sessions", 0)
    if remaining <= 0:
        return {"success": False, "message": "Plus de séances disponibles", "remaining": 0}
    
    # Déduire 1 séance
    new_remaining = remaining - 1
    new_used = subscription.get("used_sessions", 0) + 1
    
    update_data = {
        "remaining_sessions": new_remaining,
        "used_sessions": new_used,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Si plus de séances, marquer comme complété
    if new_remaining <= 0:
        update_data["status"] = "completed"
    
    await _db.subscriptions.update_one(
        {"id": subscription.get("id")},
        {"$set": update_data}
    )
    
    logger.info(f"[SUBSCRIPTION] Déduction: {email} - {new_used}/{subscription.get('total_sessions')} séances utilisées")
    
    return {
        "success": True,
        "message": f"Séance déduite ({new_remaining} restantes)",
        "remaining": new_remaining,
        "used": new_used,
        "total": subscription.get("total_sessions")
    }


# === v95: SYNC — Créer des subscriptions pour les codes promo qui n'en ont pas encore ===
@promo_router.post("/subscriptions/sync")
async def sync_subscriptions_for_email(data: dict):
    """Crée des subscriptions pour tous les codes assignés à un email qui n'en ont pas encore"""
    email = data.get("email", "").lower().strip()
    if not email:
        return {"success": False, "message": "Email requis"}

    # Trouver tous les codes assignés à cet email
    codes = await _db.discount_codes.find(
        {"assignedEmail": {"$regex": f"^{email}$", "$options": "i"}, "active": True},
        {"_id": 0}
    ).to_list(50)

    created = []
    skipped = []
    for code in codes:
        code_str = code.get("code", "").upper().strip()
        # Vérifier si une subscription existe déjà
        existing = await _db.subscriptions.find_one(
            {"email": email, "code": {"$regex": f"^{code_str}$", "$options": "i"}, "status": "active"},
            {"_id": 0}
        )
        if existing:
            skipped.append(code_str)
            continue

        # v104: Résolution dynamique des séances via l'article
        raw_max = code.get("maxUses") or code.get("sessions") or None
        total, resolved_name, resolved_price = await _resolve_offer_details(code.get("courses", []), raw_max)
        final_name = resolved_name if resolved_name != "Abonnement" else (code.get("name") or code_str)
        sub = {
            "id": str(uuid.uuid4()),
            "email": email,
            "name": data.get("name", email.split("@")[0]),
            "code": code_str,
            "offer_name": final_name,
            "offer_price": resolved_price,
            "total_sessions": total,
            "used_sessions": 0,
            "remaining_sessions": total,
            "expires_at": code.get("expiresAt"),
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": "manual_sync"
        }
        await _db.subscriptions.insert_one(sub)
        created.append({"code": code_str, "sessions": total})
        logger.info(f"[SYNC] Subscription créée: {email} - {code_str} ({total} séances)")

    return {
        "success": True,
        "created": created,
        "skipped": skipped,
        "message": f"{len(created)} abonnement(s) créé(s), {len(skipped)} déjà existant(s)"
    }
