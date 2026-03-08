# coach_routes.py - Routes coach et admin v9.5.6
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import uuid
import os
import logging
import stripe

logger = logging.getLogger(__name__)

# v9.5.6: Liste des Super Admins autorisés
SUPER_ADMIN_EMAILS = [
    "contact.artboost@gmail.com",
    "afroboost.bassi@gmail.com"
]
SUPER_ADMIN_EMAIL = "contact.artboost@gmail.com"  # Legacy
DEFAULT_COACH_ID = "bassi_default"
ROLE_SUPER_ADMIN = "super_admin"
ROLE_COACH = "coach"
ROLE_USER = "user"

def is_super_admin(email: str) -> bool:
    """Vérifie si l'email est celui d'un Super Admin"""
    return email and email.lower().strip() in [e.lower() for e in SUPER_ADMIN_EMAILS]

# Router
coach_router = APIRouter(tags=["coach"])

# Variable db sera injectée depuis server.py
db = None

def init_db(database):
    global db
    db = database

# === MODÈLES ===
class CoachPackCreate(BaseModel):
    name: str
    price: float
    credits: int
    description: Optional[str] = None
    features: Optional[List[str]] = []
    visible: bool = True

class CoachCreate(BaseModel):
    email: str
    name: str
    phone: Optional[str] = None
    bio: Optional[str] = None
    credits: int = 0
    pack_id: Optional[str] = None

# === ADMIN COACH PACKS ===
@coach_router.get("/admin/coach-packs")
async def get_coach_packs():
    """Liste tous les packs coach (public)"""
    try:
        packs = await db.coach_packs.find({"visible": True}, {"_id": 0}).to_list(100)
        return packs
    except Exception as e:
        logger.error(f"[COACH-PACKS] Erreur: {e}")
        return []

@coach_router.get("/admin/coach-packs/all")
async def get_all_coach_packs(request: Request):
    """Liste tous les packs coach (Super Admin)"""
    caller_email = request.headers.get("X-User-Email", "").lower().strip()
    if not is_super_admin(caller_email):
        raise HTTPException(status_code=403, detail="Super Admin requis")
    packs = await db.coach_packs.find({}, {"_id": 0}).to_list(100)
    return packs

@coach_router.post("/admin/coach-packs")
async def create_coach_pack(pack: CoachPackCreate, request: Request):
    """Crée un pack coach (Super Admin)"""
    caller_email = request.headers.get("X-User-Email", "").lower().strip()
    if not is_super_admin(caller_email):
        raise HTTPException(status_code=403, detail="Super Admin requis")
    pack_data = {
        "id": str(uuid.uuid4()), "name": pack.name, "price": pack.price, "credits": pack.credits,
        "description": pack.description, "features": pack.features, "visible": pack.visible,
        "stripe_price_id": None, "stripe_product_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": None
    }
    if stripe.api_key:
        try:
            prod = stripe.Product.create(name=f"Pack Coach - {pack.name}", description=pack.description or f"{pack.credits} crédits")
            price = stripe.Price.create(unit_amount=int(pack.price * 100), currency="chf", product=prod.id)
            pack_data["stripe_product_id"], pack_data["stripe_price_id"] = prod.id, price.id
        except Exception as e:
            logger.warning(f"[STRIPE] Erreur création produit: {e}")
    await db.coach_packs.insert_one(pack_data)
    pack_data.pop("_id", None)
    return pack_data

@coach_router.put("/admin/coach-packs/{pack_id}")
async def update_coach_pack(pack_id: str, request: Request):
    """Modifie un pack coach (Super Admin)"""
    caller_email = request.headers.get("X-User-Email", "").lower().strip()
    if not is_super_admin(caller_email):
        raise HTTPException(status_code=403, detail="Super Admin requis")
    body = await request.json()
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    for field in ["name", "price", "credits", "description", "features", "visible"]:
        if field in body:
            update_data[field] = body[field]
    result = await db.coach_packs.update_one({"id": pack_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Pack non trouvé")
    updated = await db.coach_packs.find_one({"id": pack_id}, {"_id": 0})
    return updated

@coach_router.delete("/admin/coach-packs/{pack_id}")
async def delete_coach_pack(pack_id: str, request: Request):
    """Supprime un pack coach (Super Admin)"""
    caller_email = request.headers.get("X-User-Email", "").lower().strip()
    if not is_super_admin(caller_email):
        raise HTTPException(status_code=403, detail="Super Admin requis")
    result = await db.coach_packs.delete_one({"id": pack_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Pack non trouvé")
    return {"success": True, "deleted_id": pack_id}

# === ADMIN COACHES ===
@coach_router.get("/admin/coaches")
async def get_coaches(request: Request):
    """Liste tous les coachs (Super Admin)"""
    caller_email = request.headers.get("X-User-Email", "").lower().strip()
    if not is_super_admin(caller_email):
        raise HTTPException(status_code=403, detail="Super Admin requis")
    coaches = await db.coaches.find({}, {"_id": 0}).to_list(100)
    return coaches

@coach_router.post("/admin/coaches/{coach_id}/toggle")
async def toggle_coach_status(coach_id: str, request: Request):
    """Active/Désactive un coach (Super Admin)"""
    caller_email = request.headers.get("X-User-Email", "").lower().strip()
    if not is_super_admin(caller_email):
        raise HTTPException(status_code=403, detail="Super Admin requis")
    coach = await db.coaches.find_one({"id": coach_id})
    if not coach:
        raise HTTPException(status_code=404, detail="Coach non trouvé")
    new_status = not coach.get("is_active", True)
    await db.coaches.update_one({"id": coach_id}, {"$set": {"is_active": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"success": True, "is_active": new_status}

@coach_router.delete("/admin/coaches/{coach_id}")
async def delete_coach(coach_id: str, request: Request):
    """Supprime un coach (Super Admin)"""
    caller_email = request.headers.get("X-User-Email", "").lower().strip()
    if not is_super_admin(caller_email):
        raise HTTPException(status_code=403, detail="Super Admin requis")
    result = await db.coaches.delete_one({"id": coach_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Coach non trouvé")
    return {"success": True, "deleted_id": coach_id}

@coach_router.delete("/admin/partner-cleanup/{email}")
async def cleanup_partner_data(email: str, request: Request):
    """Supprime TOUTES les données d'un partenaire : concept, branding, fichiers, etc. (Super Admin)"""
    caller_email = request.headers.get("X-User-Email", "").lower().strip()
    if not is_super_admin(caller_email):
        raise HTTPException(status_code=403, detail="Super Admin requis")

    email_clean = email.lower().strip()
    email_sanitized = email_clean.replace("@", "_").replace(".", "_")
    deleted = {}

    # 1. Supprimer le concept du partenaire
    r = await db.concept.delete_one({"id": f"concept_{email_clean}"})
    deleted["concept"] = r.deleted_count
    # Aussi essayer avec l'email sanitized
    r2 = await db.concept.delete_one({"id": f"concept_{email_sanitized}"})
    deleted["concept"] += r2.deleted_count

    # 2. Supprimer le coach de la collection coaches
    r = await db.coaches.delete_many({"email": email_clean})
    deleted["coaches"] = r.deleted_count

    # 3. Supprimer le branding
    r = await db.branding.delete_many({"coach_id": email_clean})
    deleted["branding"] = r.deleted_count

    # 4. Supprimer les payment links
    r = await db.payment_links.delete_many({"coach_id": email_clean})
    deleted["payment_links"] = r.deleted_count

    # 5. Supprimer les fichiers uploadés par ce coach
    r = await db.uploaded_files.delete_many({"coach_email": email_clean})
    deleted["uploaded_files"] = r.deleted_count

    # 6. Supprimer les offres du coach
    r = await db.offers.delete_many({"coach_id": email_clean})
    deleted["offers"] = r.deleted_count

    # 7. Supprimer les cours du coach
    r = await db.courses.delete_many({"coach_id": email_clean})
    deleted["courses"] = r.deleted_count

    return {"success": True, "email": email_clean, "deleted": deleted}

# === COACH PROFILE ===
@coach_router.get("/coach/profile")
async def get_coach_profile(request: Request):
    """Profil du coach connecté"""
    caller_email = request.headers.get("X-User-Email", "").lower().strip()
    if not caller_email:
        raise HTTPException(status_code=401, detail="Email requis")
    if is_super_admin(caller_email):
        return {"id": "super_admin", "email": SUPER_ADMIN_EMAIL, "name": "Super Admin", "role": ROLE_SUPER_ADMIN, "credits": -1, "is_super_admin": True}
    coach = await db.coaches.find_one({"email": caller_email.lower()}, {"_id": 0})
    if not coach:
        raise HTTPException(status_code=404, detail="Coach non trouvé")
    return coach

@coach_router.get("/coach/check-credits")
async def api_check_credits(request: Request):
    """Vérifie le solde de crédits"""
    coach_email = request.headers.get("X-User-Email", "").lower().strip()
    if not coach_email:
        raise HTTPException(status_code=401, detail="Email requis")
    if is_super_admin(coach_email):
        return {"has_credits": True, "credits": -1, "unlimited": True}
    coach = await db.coaches.find_one({"email": coach_email.lower()})
    if not coach:
        return {"has_credits": False, "credits": 0, "error": "Coach non trouvé"}
    credits = coach.get("credits", 0)
    return {"has_credits": credits > 0, "credits": credits}

@coach_router.post("/coach/register")
async def register_coach(coach_data: CoachCreate):
    """Inscription d'un nouveau coach"""
    existing = await db.coaches.find_one({"email": coach_data.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email déjà utilisé")
    coach = {
        "id": str(uuid.uuid4()), "email": coach_data.email.lower().strip(), "name": coach_data.name,
        "phone": coach_data.phone, "bio": coach_data.bio, "photo_url": None, "role": ROLE_COACH,
        "credits": coach_data.credits, "pack_id": coach_data.pack_id, "stripe_customer_id": None,
        "stripe_connect_id": None, "is_active": True, "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": None, "last_login": None
    }
    await db.coaches.insert_one(coach)
    coach.pop("_id", None)
    logger.info(f"[COACH] Nouveau: {coach_data.email}")
    return coach

@coach_router.put("/coach/update-profile")
async def update_coach_profile(request: Request):
    """Met à jour le profil du coach (platform_name, bio, etc.) - v9.1.4"""
    body = await request.json()
    caller_email = request.headers.get("X-User-Email", "").lower().strip()
    if not caller_email:
        raise HTTPException(status_code=401, detail="Email requis")
    if is_super_admin(caller_email):
        return {"success": True, "message": "Super Admin - profil non modifiable"}
    coach = await db.coaches.find_one({"email": caller_email})
    if not coach:
        raise HTTPException(status_code=404, detail="Coach non trouvé")
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    for field in ["platform_name", "bio", "logo_url", "phone"]:
        if field in body:
            update_data[field] = body[field]
    await db.coaches.update_one({"email": caller_email}, {"$set": update_data})
    logger.info(f"[COACH] Profil mis à jour: {caller_email} -> {list(update_data.keys())}")
    updated = await db.coaches.find_one({"email": caller_email}, {"_id": 0})
    return updated

@coach_router.post("/coach/deduct-credit")
async def deduct_coach_credit(request: Request):
    """Déduit 1 crédit"""
    body = await request.json()
    coach_email = body.get("email", "").lower().strip()
    action = body.get("action", "unknown")
    if not coach_email:
        raise HTTPException(status_code=400, detail="Email requis")
    if is_super_admin(coach_email):
        return {"success": True, "credits_remaining": -1, "message": "Super Admin illimité"}
    coach = await db.coaches.find_one({"email": coach_email})
    if not coach:
        raise HTTPException(status_code=404, detail="Coach non trouvé")
    if coach.get("credits", 0) <= 0:
        raise HTTPException(status_code=402, detail="Crédits insuffisants")
    new_credits = coach.get("credits", 0) - 1
    await db.coaches.update_one({"email": coach_email}, {"$set": {"credits": new_credits, "updated_at": datetime.now(timezone.utc).isoformat()}})
    logger.info(f"[COACH] Crédit déduit: {coach_email} action={action} reste={new_credits}")
    return {"success": True, "credits_remaining": new_credits, "action": action}

@coach_router.post("/coach/add-credits")
async def add_coach_credits(request: Request):
    """Ajoute des crédits (Super Admin)"""
    body = await request.json()
    caller_email = request.headers.get("X-User-Email", "").lower().strip()
    if not is_super_admin(caller_email):
        raise HTTPException(status_code=403, detail="Super Admin requis")
    coach_email = body.get("coach_email", "").lower().strip()
    credits_to_add = body.get("credits", 0)
    if not coach_email or credits_to_add <= 0:
        raise HTTPException(status_code=400, detail="Email et crédits requis")
    coach = await db.coaches.find_one({"email": coach_email})
    if not coach:
        raise HTTPException(status_code=404, detail="Coach non trouvé")
    new_credits = coach.get("credits", 0) + credits_to_add
    await db.coaches.update_one({"email": coach_email}, {"$set": {"credits": new_credits, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"success": True, "credits_total": new_credits, "coach_email": coach_email}

# === AUTH ROLE ===
@coach_router.get("/auth/role")
async def get_user_role_endpoint(request: Request):
    """Vérifie le rôle de l'utilisateur"""
    caller_email = request.headers.get("X-User-Email", "").lower().strip()
    if not caller_email:
        return {"role": ROLE_USER, "is_super_admin": False, "is_coach": False}
    if is_super_admin(caller_email):
        return {"role": ROLE_SUPER_ADMIN, "is_super_admin": True, "is_coach": True, "email": caller_email}
    coach = await db.coaches.find_one({"email": caller_email, "is_active": True})
    if coach:
        return {"role": ROLE_COACH, "is_super_admin": False, "is_coach": True, "email": caller_email, "coach_id": coach.get("id"), "credits": coach.get("credits", 0)}
    return {"role": ROLE_USER, "is_super_admin": False, "is_coach": False, "email": caller_email}

# === COACH SEARCH (PUBLIC) ===
@coach_router.get("/coaches/search")
async def search_coaches(q: str = ""):
    """Recherche de coachs (public)"""
    if not q or len(q) < 2:
        return []
    query = {"is_active": True, "$or": [{"name": {"$regex": q, "$options": "i"}}, {"email": {"$regex": q, "$options": "i"}}]}
    coaches = await db.coaches.find(query, {"_id": 0, "id": 1, "name": 1, "photo_url": 1, "bio": 1}).to_list(10)
    return coaches

# === v9.4.7: PARTENAIRES ACTIFS AVEC VIDÉOS (CAROUSEL HOME) ===
@coach_router.get("/partners/active")
async def get_active_partners():
    """
    Récupère les partenaires actifs avec leurs vidéos pour le carousel de la home page.
    Inclut le concept (heroImageUrl/video_url) de chaque partenaire.
    v9.6.6: Déduplication des partenaires par email
    """
    try:
        # Récupérer tous les coaches actifs
        coaches = await db.coaches.find(
            {"is_active": True},
            {"_id": 0, "id": 1, "name": 1, "email": 1, "photo_url": 1, "logo_url": 1, "bio": 1, "platform_name": 1}
        ).to_list(20)
        
        partners_with_videos = []
        seen_emails = set()  # v9.6.6: Track des emails pour éviter les doublons
        
        # Ajouter Bassi (Super Admin) en premier s'il a une vidéo configurée
        # v9.4.7: Collection "concept" (singulier) - id "concept" pour le principal
        bassi_concept = await db.concept.find_one({"id": "concept"}, {"_id": 0, "heroImageUrl": 1, "heroVideoUrl": 1})
        if bassi_concept and (bassi_concept.get("heroImageUrl") or bassi_concept.get("heroVideoUrl")):
            bassi_data = {
                "id": "bassi_main",  # v9.6.6: ID unique
                "name": "Bassi - Afroboost",
                "email": SUPER_ADMIN_EMAIL,
                "platform_name": "Afroboost",
                "photo_url": None,
                "logo_url": None,
                "bio": "Coach Afroboost - Fitness & Bien-être",
                "video_url": bassi_concept.get("heroVideoUrl") or bassi_concept.get("heroImageUrl"),
                "heroImageUrl": bassi_concept.get("heroImageUrl")
            }
            partners_with_videos.append(bassi_data)
            seen_emails.add(SUPER_ADMIN_EMAIL.lower())  # v9.6.6: Marquer comme vu
        
        # Pour chaque coach, récupérer son concept (vidéo) - v9.6.6: Skip si déjà vu
        for coach in coaches:
            coach_email = coach.get("email", "").lower()
            
            # v9.6.6: Skip si email déjà dans la liste (évite les doublons)
            if coach_email in seen_emails:
                continue
            seen_emails.add(coach_email)
            
            partner_data = dict(coach)
            partner_data["id"] = partner_data.get("id") or f"coach_{coach_email.replace('@', '_').replace('.', '_')}"  # v9.6.6: ID unique
            
            # Chercher le concept du coach pour avoir la vidéo
            # v9.4.7: Collection "concept" (singulier) pas "concepts"
            concept_id = f"concept_{coach_email.replace('@', '_').replace('.', '_')}"
            concept = await db.concept.find_one(
                {"$or": [{"id": concept_id}, {"coach_id": coach_email}]},
                {"_id": 0, "heroImageUrl": 1, "heroVideoUrl": 1}
            )
            
            if concept:
                partner_data["video_url"] = concept.get("heroVideoUrl") or concept.get("heroImageUrl")
                partner_data["heroImageUrl"] = concept.get("heroImageUrl")
            
            # Inclure même sans vidéo (affichera placeholder)
            partners_with_videos.append(partner_data)
        
        logger.info(f"[PARTNERS-CAROUSEL] {len(partners_with_videos)} partenaires uniques avec vidéos")
        return partners_with_videos
        
    except Exception as e:
        logger.error(f"[PARTNERS-CAROUSEL] Erreur: {e}")
        return []

@coach_router.get("/coaches/public/{coach_id}")
async def get_public_coach_profile(coach_id: str):
    """Profil public d'un coach"""
    coach = await db.coaches.find_one({"id": coach_id, "is_active": True}, {"_id": 0, "id": 1, "name": 1, "photo_url": 1, "bio": 1, "email": 1})
    if not coach:
        raise HTTPException(status_code=404, detail="Coach non trouvé")
    return coach

# === VITRINE COACH ===
@coach_router.get("/coach/vitrine/{username}")
@coach_router.get("/partner/vitrine/{username}")
async def get_coach_vitrine(username: str):
    """Vitrine publique d'un partenaire (coach/vendeur) - v29: inclut concept + heroVideos directement"""
    # v19: Isolation stricte des données par coach_id
    is_admin_vitrine = username.lower() in ["bassi", "afroboost", SUPER_ADMIN_EMAIL.lower()]
    if is_admin_vitrine:
        coach = {"id": "bassi", "name": "Bassi - Afroboost", "email": SUPER_ADMIN_EMAIL, "photo_url": None, "bio": "Coach Afroboost - Fitness & Bien-être", "platform_name": "Afroboost", "logo_url": None, "is_active": True}
        # Super Admin: match son coach_id OU les données legacy sans coach_id
        coach_filter = {"$or": [
            {"coach_id": DEFAULT_COACH_ID},
            {"coach_id": SUPER_ADMIN_EMAIL.lower()},
            {"coach_id": {"$exists": False}},  # Legacy: données créées avant le système multi-coach
            {"coach_id": None},
            {"coach_id": ""}
        ]}
        # v29: Charger le concept admin directement (concept_id="concept")
        concept_id = "concept"
    else:
        coach = await db.coaches.find_one({"$or": [{"name": {"$regex": f"^{username}$", "$options": "i"}}, {"email": username.lower()}, {"id": username}], "is_active": True}, {"_id": 0, "id": 1, "name": 1, "photo_url": 1, "bio": 1, "email": 1, "platform_name": 1, "logo_url": 1})
        if not coach:
            raise HTTPException(status_code=404, detail="Partenaire non trouvé")
        coach_email = coach.get("email", "").lower()
        # Partenaire: match UNIQUEMENT son coach_id — PAS de fallback global
        coach_filter = {"coach_id": coach_email}
        # v29: Concept personnel du partenaire
        concept_id = f"concept_{coach_email}"
    offers = await db.offers.find(coach_filter, {"_id": 0}).to_list(20)
    courses = await db.courses.find(coach_filter, {"_id": 0}).to_list(20)
    # v29: Charger le concept (heroVideos, appName, couleurs, etc.) côté serveur
    concept = await db.concept.find_one({"id": concept_id}, {"_id": 0})
    concept_data = {}
    if concept:
        concept_data = {
            "heroVideos": concept.get("heroVideos", []),
            "heroImageUrl": concept.get("heroImageUrl", ""),
            "appName": concept.get("appName", ""),
            "description": concept.get("description", ""),
            "primaryColor": concept.get("primaryColor", "#D91CD2"),
            "secondaryColor": concept.get("secondaryColor", "#8b5cf6"),
            "backgroundColor": concept.get("backgroundColor", "#000000"),
            "glowColor": concept.get("glowColor", ""),
            "logoUrl": concept.get("logoUrl", ""),
            "eventPosterEnabled": concept.get("eventPosterEnabled", False),
            "eventPosterMediaUrl": concept.get("eventPosterMediaUrl", ""),
            "defaultLandingSection": concept.get("defaultLandingSection", "sessions"),
            "googleReviewsUrl": concept.get("googleReviewsUrl", ""),
            "externalLink1Title": concept.get("externalLink1Title", ""),
            "externalLink1Url": concept.get("externalLink1Url", ""),
            "externalLink2Title": concept.get("externalLink2Title", ""),
            "externalLink2Url": concept.get("externalLink2Url", ""),
        }
    logger.info(f"[VITRINE-V29] {username} → concept_id={concept_id}, heroVideos={len(concept_data.get('heroVideos', []))}, offers={len(offers)}, courses={len(courses)}")
    return {"coach": coach, "offers": offers, "courses": courses, "courses_count": len(courses), "offers_count": len(offers), "concept": concept_data}

# === STRIPE CONNECT ===
@coach_router.post("/coach/stripe-connect/onboard")
async def create_stripe_connect_onboard(request: Request):
    """Crée un lien d'onboarding Stripe Connect"""
    body = await request.json()
    coach_email = body.get("email", "").lower().strip()
    if not coach_email:
        raise HTTPException(status_code=400, detail="Email requis")
    coach = await db.coaches.find_one({"email": coach_email, "is_active": True})
    if not coach:
        raise HTTPException(status_code=404, detail="Coach non trouvé")
    frontend_url = os.environ.get('FRONTEND_URL', 'https://afroboost.com')
    if coach.get("stripe_connect_id"):
        link = stripe.AccountLink.create(account=coach["stripe_connect_id"], type="account_onboarding", refresh_url=f"{frontend_url}/coach/settings", return_url=f"{frontend_url}/coach/settings?stripe=success")
        return {"url": link.url, "account_id": coach["stripe_connect_id"]}
    account = stripe.Account.create(type="express", email=coach_email, capabilities={"card_payments": {"requested": True}, "transfers": {"requested": True}}, metadata={"coach_id": coach.get("id"), "coach_email": coach_email})
    await db.coaches.update_one({"email": coach_email}, {"$set": {"stripe_connect_id": account.id, "updated_at": datetime.now(timezone.utc).isoformat()}})
    account_link = stripe.AccountLink.create(account=account.id, type="account_onboarding", refresh_url=f"{frontend_url}/coach/settings", return_url=f"{frontend_url}/coach/settings?stripe=success")
    logger.info(f"[STRIPE-CONNECT] Compte créé: {coach_email} -> {account.id}")
    return {"url": account_link.url, "account_id": account.id}

@coach_router.get("/coach/stripe-connect/status")
async def get_stripe_connect_status(request: Request):
    """Statut du compte Stripe Connect"""
    coach_email = request.headers.get("X-User-Email", "").lower().strip()
    if not coach_email:
        raise HTTPException(status_code=401, detail="Email requis")
    coach = await db.coaches.find_one({"email": coach_email})
    if not coach:
        return {"connected": False, "status": "not_found"}
    connect_id = coach.get("stripe_connect_id")
    if not connect_id:
        return {"connected": False, "status": "not_started"}
    try:
        account = stripe.Account.retrieve(connect_id)
        return {"connected": True, "status": "active" if account.charges_enabled else "pending", "account_id": connect_id, "charges_enabled": account.charges_enabled, "payouts_enabled": account.payouts_enabled}
    except stripe.error.StripeError:
        return {"connected": False, "status": "error"}

# === MIGRATION DATA ===
@coach_router.post("/admin/migrate-bassi-data")
async def migrate_bassi_data(request: Request):
    """Migre les données vers bassi_default (Super Admin)"""
    caller_email = request.headers.get("X-User-Email", "").lower().strip()
    if not is_super_admin(caller_email):
        raise HTTPException(status_code=403, detail="Super Admin requis")
    results = {}
    r = await db.reservations.update_many({"coach_id": {"$exists": False}}, {"$set": {"coach_id": DEFAULT_COACH_ID}})
    results["reservations"] = r.modified_count
    c = await db.chat_participants.update_many({"coach_id": {"$exists": False}}, {"$set": {"coach_id": DEFAULT_COACH_ID}})
    results["contacts"] = c.modified_count
    p = await db.campaigns.update_many({"coach_id": {"$exists": False}}, {"$set": {"coach_id": DEFAULT_COACH_ID}})
    results["campaigns"] = p.modified_count
    logger.info(f"[MIGRATION] {results}")
    return {"success": True, "migrated": results}

@coach_router.post("/admin/migrate-ownership")
async def migrate_ownership(request: Request):
    """v19: Migre les cours, offres et fichiers orphelins vers le Super Admin"""
    caller_email = request.headers.get("X-User-Email", "").lower().strip()
    if not is_super_admin(caller_email):
        raise HTTPException(status_code=403, detail="Super Admin requis")
    results = {}
    # Cours sans coach_id → Super Admin
    r1 = await db.courses.update_many(
        {"$or": [{"coach_id": {"$exists": False}}, {"coach_id": None}, {"coach_id": ""}]},
        {"$set": {"coach_id": SUPER_ADMIN_EMAIL.lower()}}
    )
    results["courses"] = r1.modified_count
    # Offres sans coach_id → Super Admin
    r2 = await db.offers.update_many(
        {"$or": [{"coach_id": {"$exists": False}}, {"coach_id": None}, {"coach_id": ""}]},
        {"$set": {"coach_id": SUPER_ADMIN_EMAIL.lower()}}
    )
    results["offers"] = r2.modified_count
    # Fichiers uploadés sans coach_email → Super Admin
    r3 = await db.uploaded_files.update_many(
        {"$or": [{"coach_email": {"$exists": False}}, {"coach_email": None}, {"coach_email": ""}]},
        {"$set": {"coach_email": SUPER_ADMIN_EMAIL.lower()}}
    )
    results["uploaded_files"] = r3.modified_count
    logger.info(f"[MIGRATION-OWNERSHIP] {results}")
    return {"success": True, "migrated": results}
