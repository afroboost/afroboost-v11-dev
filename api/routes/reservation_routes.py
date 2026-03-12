# reservation_routes.py - Routes réservations v9.5.8
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
import uuid
import logging

logger = logging.getLogger(__name__)

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
