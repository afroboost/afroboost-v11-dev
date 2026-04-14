# reservation_routes.py - Routes réservations v9.5.8 → v96: Email confirmation → v158: AFRO-XXXX + WhatsApp + i18n
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
        'guide_step3': '3. Écris "Je veux réserver une séance" à ton coach',
        'guide_step4': '4. Choisis ton horaire — au minimum 24h à l\'avance',
        'cta_chat': 'Aller au chat',
        'cta_space': 'Mon espace',
        'footer': 'Conserve cet email. À très vite chez Afroboost !',
        'credit_label': 'Ton crédit restant',
        'credit_unit': 'séances',
        'whatsapp_msg': ('✨ Afroboost — Réservation confirmée ✨\n\n'
                         'Merci {name} ! Référence : {res_code}\n'
                         '🎟️ Code d\'accès permanent : {access_code}\n'
                         '📅 {dates}\n\n'
                         'Pour tes prochaines séances, va sur le chat Afroboost et entre ton code.\n'
                         '⚠️ Réserve au moins 24h à l\'avance sinon la séance est perdue.\n\n'
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
        'guide_step3': '3. Tell your coach "I want to book a session"',
        'guide_step4': '4. Pick your slot — at least 24h in advance',
        'cta_chat': 'Go to chat',
        'cta_space': 'My space',
        'footer': 'Keep this email safe. See you soon at Afroboost!',
        'credit_label': 'Your remaining credit',
        'credit_unit': 'sessions',
        'whatsapp_msg': ('✨ Afroboost — Booking confirmed ✨\n\n'
                         'Thanks {name}! Reference: {res_code}\n'
                         '🎟️ Permanent access code: {access_code}\n'
                         '📅 {dates}\n\n'
                         'For your next sessions, go to the Afroboost chat and enter your code.\n'
                         '⚠️ Book at least 24h in advance or the session is lost.\n\n'
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
        'guide_step3': '3. Schreibe deinem Coach "Ich möchte eine Session buchen"',
        'guide_step4': '4. Wähle einen Slot — mindestens 24h im Voraus',
        'cta_chat': 'Zum Chat',
        'cta_space': 'Mein Bereich',
        'footer': 'Bewahre diese E-Mail auf. Bis bald bei Afroboost!',
        'credit_label': 'Dein verbleibendes Guthaben',
        'credit_unit': 'Sessions',
        'whatsapp_msg': ('✨ Afroboost — Buchung bestätigt ✨\n\n'
                         'Danke {name}! Referenz: {res_code}\n'
                         '🎟️ Dauerhafter Zugangscode: {access_code}\n'
                         '📅 {dates}\n\n'
                         'Für deine nächsten Sessions, gehe in den Afroboost-Chat und gib deinen Code ein.\n'
                         '⚠️ Buche mindestens 24h im Voraus, sonst ist die Session verloren.\n\n'
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
        return
    resend.api_key = _RESEND_KEY

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
        code = subscription_info.get("code", promo)
        sub_html = f"""
        <div style="background:rgba(147,51,234,0.15);border:1px solid rgba(147,51,234,0.3);border-radius:8px;padding:14px;margin:16px 0;">
            <p style="margin:0;color:#a855f7;font-size:13px;">{t['credit_label']}</p>
            <p style="margin:4px 0 0;color:#fff;font-size:18px;font-weight:bold;">{remaining}/{total} {t['credit_unit']}</p>
            <p style="margin:4px 0 0;color:#888;font-size:12px;">Code : {code}</p>
        </div>"""

    # v158: Le QR code pointe vers la page chat avec le code d'accès pré-rempli
    # Sert de (1) billet d'entrée scannable par le coach ET (2) raccourci vers le chat
    chat_deeplink = f"https://afroboost.com/chat?code={quote(access_code)}&res={quote(res_code)}"
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=220x220&data={quote(chat_deeplink)}&format=png"

    html = f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0a0a0a;">
        <div style="background:linear-gradient(135deg,#d91cd2,#8b5cf6);padding:24px;text-align:center;">
            <h1 style="color:white;margin:0;font-size:22px;">{t['hero_title']}</h1>
        </div>
        <div style="padding:24px;color:#fff;">
            <p style="color:#a855f7;font-size:16px;line-height:1.6;">
                {t['thanks'].format(name=user_name or '')}
            </p>
            <div style="background:rgba(217,28,210,0.1);border:1px solid rgba(217,28,210,0.3);border-radius:12px;padding:20px;margin:20px 0;">
                <table style="width:100%;color:#fff;font-size:14px;">
                    <tr><td style="color:#888;padding:6px 0;">{t['reference']}</td><td style="font-weight:bold;color:#d91cd2;">{res_code}</td></tr>
                    <tr><td style="color:#888;padding:6px 0;">{t['offer']}</td><td>{offer}</td></tr>
                    {"<tr><td style='color:#888;padding:6px 0;'>" + t['course'] + "</td><td>" + course + "</td></tr>" if course else ""}
                    {"<tr><td style='color:#888;padding:6px 0;'>" + t['dates'] + "</td><td>" + dates_text + "</td></tr>" if dates_text else ""}
                    {"<tr><td style='color:#888;padding:6px 0;'>" + t['promo'] + "</td><td style='color:#a855f7;'>" + promo + "</td></tr>" if promo else ""}
                    <tr><td style="color:#888;padding:6px 0;">{t['price']}</td><td style="font-weight:bold;">{price} CHF</td></tr>
                </table>
            </div>
            {sub_html}
            <!-- Code d'accès permanent -->
            <div style="background:linear-gradient(135deg,rgba(217,28,210,0.2),rgba(139,92,246,0.2));border:2px solid #d91cd2;border-radius:12px;padding:20px;margin:20px 0;text-align:center;">
                <p style="color:#fff;font-size:15px;font-weight:bold;margin:0 0 10px;">{t['access_title']}</p>
                <p style="color:#d91cd2;font-size:26px;font-weight:bold;letter-spacing:2px;margin:10px 0;font-family:monospace;">{access_code}</p>
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
            <!-- CTAs -->
            <div style="text-align:center;margin:28px 0;">
                <a href="{chat_deeplink}" style="display:inline-block;background:#d91cd2;color:white;padding:14px 28px;text-decoration:none;border-radius:8px;font-weight:bold;font-size:14px;margin:4px;">{t['cta_chat']}</a>
                <a href="https://afroboost.com" style="display:inline-block;background:rgba(139,92,246,0.3);color:white;padding:14px 28px;text-decoration:none;border-radius:8px;font-weight:bold;font-size:14px;margin:4px;border:1px solid rgba(139,92,246,0.5);">{t['cta_space']}</a>
            </div>
            <p style="color:#666;font-size:11px;text-align:center;margin-top:24px;">{t['footer']}</p>
        </div>
    </div>"""

    try:
        await asyncio.to_thread(resend.Emails.send, {
            "from": "Afroboost <notifications@afroboosteur.com>",
            "to": [user_email],
            "subject": f"{t['subject']} — {res_code}",
            "html": html
        })
        logger.info(f"[EMAIL] Confirmation envoyée à {user_email} pour {res_code} (code {access_code}, lang {lang})")
    except Exception as e:
        logger.warning(f"[EMAIL] Erreur envoi confirmation: {e}")

# v9.5.8: Liste des Super Admins
SUPER_ADMIN_EMAILS = [
    "contact.artboost@gmail.com",
    "afroboost.bassi@gmail.com"
]
SUPER_ADMIN_EMAIL = "contact.artboost@gmail.com"  # Legacy

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
db = None

def init_reservation_db(database):
    global db
    db = database

# === MODÈLES ===
class ReservationBase(BaseModel):
    userName: str
    userEmail: str
    userWhatsapp: Optional[str] = None
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
@reservation_router.get("/reservations")
async def get_reservations(request: Request, page: int = 1, limit: int = 20, all_data: bool = False):
    """Get reservations with pagination - Filtré par coach_id"""
    caller_email = request.headers.get("X-User-Email", "").lower().strip()
    base_query = {} if is_super_admin(caller_email) else {"coach_id": caller_email} if caller_email else {"coach_id": "__no_access__"}
    projection = {
        "_id": 0, "id": 1, "reservationCode": 1, "userName": 1, "userEmail": 1,
        "userWhatsapp": 1, "courseName": 1, "courseTime": 1, "datetime": 1,
        "offerName": 1, "totalPrice": 1, "quantity": 1, "validated": 1,
        "validatedAt": 1, "createdAt": 1, "selectedDates": 1, "selectedDatesText": 1,
        "selectedVariants": 1, "variantsText": 1, "isProduct": 1, "shippingStatus": 1,
        "trackingNumber": 1, "promoCode": 1, "source": 1, "type": 1
    }
    if all_data:
        reservations = await db.reservations.find(base_query, {"_id": 0}).sort("createdAt", -1).to_list(10000)
    else:
        skip = (page - 1) * limit
        reservations = await db.reservations.find(base_query, projection).sort("createdAt", -1).skip(skip).limit(limit).to_list(limit)
    total_count = await db.reservations.count_documents(base_query)
    for res in reservations:
        if isinstance(res.get('createdAt'), str):
            res['createdAt'] = datetime.fromisoformat(res['createdAt'].replace('Z', '+00:00'))
    return {"data": reservations, "pagination": {"page": page, "limit": limit, "total": total_count, "pages": (total_count + limit - 1) // limit}}

@reservation_router.post("/reservations", response_model=Reservation)
async def create_reservation(reservation: ReservationCreate, request: Request):
    """Créer une réservation - Vérifie la validité du code et déduit 1 séance v11.4"""
    promo_code = reservation.promoCode or reservation.discountCode
    user_email = reservation.userEmail.lower().strip() if reservation.userEmail else ""

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

    # === v95: VÉRIFIER ET DÉDUIRE UNE SÉANCE — support subscriptionId pour choix multi-abo ===
    subscription_id = getattr(reservation, 'subscriptionId', None)
    if user_email:
        # v95: Si subscriptionId fourni, cibler cet abonnement spécifique
        if subscription_id:
            query = {"id": subscription_id, "email": user_email, "status": "active"}
        else:
            query = {"email": user_email, "status": "active"}
            if promo_code:
                query["code"] = promo_code.upper().strip()

        subscription = await db.subscriptions.find_one(query, {"_id": 0})
        
        if subscription:
            remaining = subscription.get("remaining_sessions", 0)
            if remaining <= 0:
                logger.warning(f"[RESERVATION] {user_email} - Plus de séances disponibles")
                raise HTTPException(status_code=400, detail="Plus de séances disponibles dans votre abonnement")
            
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

    if promo_code:
        discount = await db.discount_codes.find_one({"code": {"$regex": f"^{promo_code}$", "$options": "i"}, "active": True}, {"_id": 0})
        if discount:
            # v95: Incrémenter le compteur d'utilisation du code promo
            await db.discount_codes.update_one(
                {"id": discount.get("id")},
                {"$inc": {"used": 1}}
            )
            logger.info(f"[RESERVATION] Code promo {promo_code} utilisé (compteur incrémenté)")
        else:
            logger.info(f"[RESERVATION] Code promo invalide: {promo_code}")

    # Créer la réservation avec coach_id par défaut
    caller_email = request.headers.get("X-User-Email", "").lower().strip() if request else None
    reservation_data = Reservation(
        userName=reservation.userName, userEmail=reservation.userEmail, userWhatsapp=reservation.userWhatsapp,
        userLanguage=reservation.userLanguage,
        courseName=reservation.courseName, courseTime=reservation.courseTime, datetime=reservation.datetime,
        offerName=reservation.offerName, totalPrice=reservation.totalPrice, quantity=reservation.quantity,
        selectedDates=reservation.selectedDates, selectedDatesText=reservation.selectedDatesText,
        selectedVariants=reservation.selectedVariants, variantsText=reservation.variantsText,
        isProduct=reservation.isProduct, promoCode=promo_code, subscriptionId=subscription_id,
        source=reservation.source, type=reservation.type,
        coach_id=caller_email if caller_email and not is_super_admin(caller_email) else "bassi_default"
    ).model_dump()
    await db.reservations.insert_one(reservation_data)
    reservation_data.pop("_id", None)
    logger.info(f"[RESERVATION] Créée: {reservation_data.get('reservationCode')} pour {user_email}")

    # v96/v158: Envoyer email + WhatsApp de confirmation avec code AFRO-XXXX
    if user_email:
        sub_info = None
        if subscription_id:
            sub_info = await db.subscriptions.find_one({"id": subscription_id}, {"_id": 0})
        asyncio.create_task(_send_reservation_email(
            user_email, reservation.userName, reservation_data, sub_info,
            user_lang=reservation.userLanguage,
            user_whatsapp=reservation.userWhatsapp
        ))

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

@reservation_router.post("/reservations/{reservation_code}/validate")
async def validate_reservation(reservation_code: str):
    """Validate a reservation by QR code scan"""
    reservation = await db.reservations.find_one({"reservationCode": reservation_code}, {"_id": 0})
    if not reservation:
        raise HTTPException(status_code=404, detail="Réservation non trouvée")
    await db.reservations.update_one(
        {"reservationCode": reservation_code},
        {"$set": {"validated": True, "validatedAt": datetime.now(timezone.utc).isoformat()}}
    )
    return {"success": True, "message": "Réservation validée", "reservation": reservation}

@reservation_router.delete("/reservations/{reservation_id}")
async def delete_reservation(reservation_id: str):
    """Supprime une réservation"""
    await db.reservations.delete_one({"id": reservation_id})
    return {"success": True}

# === STAFF ACCESS: Validation QR uniquement (pas d'accès chat/réglages) ===
@reservation_router.post("/staff/validate")
async def staff_validate_reservation(request: Request):
    """Endpoint simplifié pour le staff — valide une réservation par code QR.
    Le staff n'a accès qu'à ce endpoint, pas aux conversations ni aux réglages."""
    body = await request.json()
    code = body.get("code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="Code requis")
    reservation = await db.reservations.find_one({"reservationCode": code}, {"_id": 0})
    if not reservation:
        raise HTTPException(status_code=404, detail="Réservation non trouvée")
    if reservation.get("validated"):
        return {"success": False, "message": "Déjà validé", "userName": reservation.get("userName", ""), "validatedAt": reservation.get("validatedAt", "")}
    await db.reservations.update_one(
        {"reservationCode": code},
        {"$set": {"validated": True, "validatedAt": datetime.now(timezone.utc).isoformat()}}
    )
    return {"success": True, "message": "Réservation validée", "userName": reservation.get("userName", ""), "courseName": reservation.get("courseName", "")}


# === EXPORT PRÉSENCES (CSV) ===
@reservation_router.get("/reservations/export/attendance")
async def export_attendance(request: Request, date: str = "", course: str = ""):
    """Exporte la liste des présences (réservations validées) au format CSV.
    Paramètres optionnels: date (YYYY-MM-DD), course (nom du cours).
    Le frontend peut convertir en Excel ou PDF."""
    query = {"validated": True}
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
async def get_my_access_code(email: str = ""):
    """v158: Retourne le code AFRO-XXXX permanent d'un utilisateur par email."""
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
        discount = await db.discount_codes.find_one({"code": {"$regex": f"^{code}$", "$options": "i"}, "active": True}, {"_id": 0})
        if discount:
            return {"eligible": True, "discount": discount, "type": "discount_code"}
    # Chercher par email (abonné actif)
    if email:
        subscriber = await db.chat_participants.find_one({"email": {"$regex": f"^{email}$", "$options": "i"}}, {"_id": 0})
        if subscriber and subscriber.get("isSubscriber"):
            return {"eligible": True, "subscriber": {"name": subscriber.get("name"), "email": subscriber.get("email")}, "type": "subscriber"}
    return {"eligible": False, "reason": "Aucun abonnement ou code valide trouvé"}
