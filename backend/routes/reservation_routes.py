# reservation_routes.py - Routes réservations v9.5.8 → v96: Email confirmation
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
import uuid
import logging
import asyncio
import os

logger = logging.getLogger(__name__)

# === v96: Email confirmation après réservation ===
try:
    import resend
    _RESEND_OK = True
except ImportError:
    _RESEND_OK = False

_RESEND_KEY = os.environ.get('RESEND_API_KEY', '')


async def _send_reservation_email(user_email: str, user_name: str, reservation_data: dict, subscription_info: dict = None):
    """Envoie un email de confirmation après réservation"""
    if not _RESEND_OK or not _RESEND_KEY:
        logger.warning("[EMAIL] Resend non disponible — email non envoyé")
        return
    resend.api_key = _RESEND_KEY

    res_code = reservation_data.get("reservationCode", "N/A")
    offer = reservation_data.get("offerName", "Réservation")
    course = reservation_data.get("courseName", "")
    price = reservation_data.get("totalPrice", 0)
    promo = reservation_data.get("promoCode", "")
    created = reservation_data.get("createdAt", "")
    dates_text = reservation_data.get("selectedDatesText", "")

    # Info abonnement
    sub_html = ""
    if subscription_info:
        remaining = subscription_info.get("remaining_sessions", "?")
        total = subscription_info.get("total_sessions", "?")
        code = subscription_info.get("code", promo)
        sub_html = f"""
        <div style="background:rgba(147,51,234,0.15);border:1px solid rgba(147,51,234,0.3);border-radius:8px;padding:14px;margin:16px 0;">
            <p style="margin:0;color:#a855f7;font-size:13px;">Ton crédit restant</p>
            <p style="margin:4px 0 0;color:#fff;font-size:18px;font-weight:bold;">{remaining}/{total} séances</p>
            <p style="margin:4px 0 0;color:#888;font-size:12px;">Code : {code}</p>
        </div>"""

    # QR Code de la réservation
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=https://afroboost.com/api/reservations/{res_code}/validate&format=png"

    html = f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0a0a0a;">
        <div style="background:linear-gradient(135deg,#d91cd2,#8b5cf6);padding:24px;text-align:center;">
            <h1 style="color:white;margin:0;font-size:22px;">Réservation confirmée !</h1>
        </div>
        <div style="padding:24px;color:#fff;">
            <p style="color:#a855f7;font-size:16px;line-height:1.6;">
                Merci {user_name} pour ta réservation ! Voici le récapitulatif :
            </p>
            <div style="background:rgba(217,28,210,0.1);border:1px solid rgba(217,28,210,0.3);border-radius:12px;padding:20px;margin:20px 0;">
                <table style="width:100%;color:#fff;font-size:14px;">
                    <tr><td style="color:#888;padding:6px 0;">Référence</td><td style="font-weight:bold;color:#d91cd2;">{res_code}</td></tr>
                    <tr><td style="color:#888;padding:6px 0;">Offre</td><td>{offer}</td></tr>
                    {"<tr><td style='color:#888;padding:6px 0;'>Cours</td><td>" + course + "</td></tr>" if course else ""}
                    {"<tr><td style='color:#888;padding:6px 0;'>Dates</td><td>" + dates_text + "</td></tr>" if dates_text else ""}
                    {"<tr><td style='color:#888;padding:6px 0;'>Code promo</td><td style='color:#a855f7;'>" + promo + "</td></tr>" if promo else ""}
                    <tr><td style="color:#888;padding:6px 0;">Prix</td><td style="font-weight:bold;">{price} CHF</td></tr>
                </table>
            </div>
            {sub_html}
            <div style="text-align:center;margin:24px 0;">
                <p style="color:#888;margin-bottom:12px;font-size:13px;">Ton QR Code de réservation</p>
                <img src="{qr_url}" alt="QR Code" width="140" height="140" style="background:white;padding:8px;border-radius:8px;display:block;margin:0 auto;"/>
                <p style="color:#a855f7;font-size:12px;margin-top:8px;">Présente ce QR Code à l'entrée.</p>
            </div>
            <div style="text-align:center;margin:24px 0;">
                <a href="https://afroboost.com" style="display:inline-block;background:#d91cd2;color:white;padding:12px 24px;text-decoration:none;border-radius:8px;font-weight:bold;font-size:14px;">Accéder à mon espace</a>
            </div>
            <p style="color:#666;font-size:11px;text-align:center;margin-top:24px;">Conserve cet email. À très vite chez Afroboost !</p>
        </div>
    </div>"""

    try:
        await asyncio.to_thread(resend.Emails.send, {
            "from": "Afroboost <notifications@afroboosteur.com>",
            "to": [user_email],
            "subject": f"Réservation confirmée — {res_code}",
            "html": html
        })
        logger.info(f"[EMAIL] Confirmation envoyée à {user_email} pour {res_code}")
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

    # v96: Envoyer email de confirmation
    if user_email:
        sub_info = None
        if subscription_id:
            sub_info = await db.subscriptions.find_one({"id": subscription_id}, {"_id": 0})
        asyncio.create_task(_send_reservation_email(
            user_email, reservation.userName, reservation_data, sub_info
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

# === STAFF ACCESS: Validation QR uniquement (pas d'accès chat/péglages) ===
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
