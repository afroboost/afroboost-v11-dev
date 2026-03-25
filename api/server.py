# VERSION 7.0 - PRODUCTION READY - NE PAS MODIFIER login/tri/sync
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Union
import uuid
from datetime import datetime, timezone, timedelta
import stripe
import asyncio
import json
import jwt as pyjwt

# V134: JWT Secret for token signing â WARNING logged at startup if missing
JWT_SECRET = os.environ.get('JWT_SECRET', '')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_DAYS = 7
JWT_STRICT_MODE = bool(JWT_SECRET)  # V134: Si JWT_SECRET est dÃ©fini, fallback X-User-Email dÃ©sactivÃ©

if not JWT_SECRET:
    import logging as _startup_logging
    _startup_logging.getLogger(__name__).warning(
        "â ï¸  [V134] JWT_SECRET non dÃ©fini ! L'authentification JWT est INACTIVE. "
        "Configurez JWT_SECRET dans les variables d'environnement Vercel pour sÃ©curiser l'API."
    )

# Web Push imports
try:
    from pywebpush import webpush, WebPushException
    WEBPUSH_AVAILABLE = True
except ImportError:
    WEBPUSH_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("pywebpush not installed - push notifications disabled")

# Resend import
try:
    import resend
    RESEND_AVAILABLE = True
except ImportError:
    RESEND_AVAILABLE = False

# v9.1.1: Import routes modulaires
from api.routes.coach_routes import coach_router, init_db as init_coach_db
from api.routes.campaign_routes import campaign_router, init_campaign_db
from api.routes.reservation_routes import reservation_router, init_reservation_db
# v9.1.9: Import routes auth
from api.routes.auth_routes import auth_router, legacy_auth_router, init_auth_db
# v9.2.0: Import routes promo codes
from api.routes.promo_routes import promo_router, init_promo_db
# v13.4: Import routes stripe
from api.routes.stripe_routes import router as stripe_router, init_db as init_stripe_db
from api.routes.cinetpay_routes import router as cinetpay_router, init_db as init_cinetpay_db
# v15.0: Import routes paiement multi-vendeurs
from api.routes.payment_config_routes import router as payment_config_router, init_db as init_payment_config_db
from api.routes.checkout_routes import router as checkout_router, init_db as init_checkout_db
# V154: Import routes catÃ©gories contacts
from api.routes.contact_categories_routes import category_router, init_category_db

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Stripe configuration - utilise la variable d'environnement existante
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

# VAPID configuration for Web Push
VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '')
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')
VAPID_CLAIMS_EMAIL = os.environ.get('VAPID_CLAIMS_EMAIL', 'contact@afroboost.ch')

# Resend configuration
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
if RESEND_AVAILABLE and RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

# TWILIO CONFIGURATION
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
TWILIO_FROM_NUMBER = os.environ.get('TWILIO_FROM_NUMBER', '')
TWILIO_SANDBOX_NUMBER = "+14155238886"
TWILIO_PRODUCTION_NUMBER = "+41765203363"

# V118: Meta Cloud API WhatsApp â prioritÃ© sur Twilio quand configurÃ©
META_ACCESS_TOKEN = os.environ.get('META_ACCESS_TOKEN', '')
META_PHONE_NUMBER_ID = os.environ.get('META_PHONE_NUMBER_ID', '')

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL')
if not mongo_url:
    raise RuntimeError("MONGO_URL required")

# v162: Limiter les connexions pour M0 Atlas (max 500 connexions)
client = AsyncIOMotorClient(
    mongo_url,
    maxPoolSize=1,
    minPoolSize=0,
    maxIdleTimeMS=45000,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    socketTimeoutMS=10000,
    retryWrites=True,
    retryReads=True
)
db = client[os.environ.get('DB_NAME', 'afroboost_db')]

# v9.1.1: Initialiser la db pour les routes modulaires
init_coach_db(db)
init_campaign_db(db)
init_reservation_db(db)
# v9.1.9: Initialiser la db pour auth routes
init_auth_db(db)
# v9.2.0: Initialiser la db pour promo routes
init_promo_db(db)
# v13.4: Initialiser la db pour stripe routes
init_stripe_db(db)
# v14.0: Initialiser la db pour CinetPay routes
init_cinetpay_db(db)

# Configure logging FIRST (needed for socketio)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ââ HELPER SÃCURITÃ : vÃ©rification authentification ââââââââââ
# V134: JWT STRICT â si JWT_SECRET est dÃ©fini, le fallback X-User-Email est DÃSACTIVÃ
def require_auth(request: Request) -> str:
    """
    V134 â Authentification sÃ©curisÃ©e:
    - Si JWT_SECRET est configurÃ© (JWT_STRICT_MODE=True):
      Seul le Bearer JWT est acceptÃ©. Le header X-User-Email est IGNORÃ.
    - Si JWT_SECRET est absent (JWT_STRICT_MODE=False):
      Le header X-User-Email est acceptÃ© (mode legacy/dev).
    Retourne l'email (en minuscule, sans espaces) si valide.
    LÃ¨ve HTTP 401 si aucune authentification valide.
    """
    # 1. Essayer JWT d'abord (mÃ©thode sÃ©curisÃ©e)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer ") and JWT_SECRET:
        token = auth_header[7:]
        try:
            payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            email = payload.get("email", "").lower().strip()
            if email:
                return email
        except pyjwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token JWT expirÃ© â reconnectez-vous")
        except pyjwt.InvalidTokenError:
            if JWT_STRICT_MODE:
                raise HTTPException(status_code=401, detail="Token JWT invalide")
            # En mode non-strict, on essaie le fallback

    # 2. Mode STRICT: JWT obligatoire, pas de fallback
    if JWT_STRICT_MODE:
        raise HTTPException(
            status_code=401,
            detail="Authentification JWT requise"
        )

    # 3. Mode LEGACY (dev/sans JWT_SECRET): fallback X-User-Email
    email = request.headers.get("X-User-Email", "").lower().strip()
    if not email:
        raise HTTPException(
            status_code=401,
            detail="Authentification requise"
        )
    return email


def require_auth_email(request: Request) -> str:
    """
    V134: Extraction sÃ©curisÃ©e de l'email authentifiÃ©.
    Utilise require_auth() puis retourne l'email.
    Remplace les appels directs Ã  request.headers.get('X-User-Email').
    """
    return require_auth(request)


def generate_jwt(email: str, role: str = "user") -> str:
    """GÃ©nÃ¨re un JWT signÃ© contenant l'email et le rÃ´le de l'utilisateur."""
    if not JWT_SECRET:
        return ""
    payload = {
        "email": email.lower().strip(),
        "role": role,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRATION_DAYS),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


# CrÃ©er l'application FastAPI (interne)
fastapi_app = FastAPI(title="Afroboost API")
api_router = APIRouter(prefix="/api")

# Socket.IO dÃ©sactivÃ© en mode Vercel Serverless

async def emit_new_message(session_id: str, message_data: dict):
    """
    Ãmet un Ã©vÃ©nement 'message_received' Ã  tous les clients d'une session.
    AppelÃ© par les endpoints de chat quand un message est envoyÃ©.
    Socket.IO dÃ©sactivÃ© en mode Vercel Serverless.
    """
    # No-op: Socket.IO dÃ©sactivÃ© en mode Vercel Serverless
    pass

# Socket.IO private messages and typing indicators dÃ©sactivÃ©s en mode Vercel Serverless

# === CONSTANTE EMAIL COACH ===
COACH_EMAIL = "contact.artboost@gmail.com"

# === SYSTÃME MULTI-COACH v8.9 ===
# V133: Super Admin emails chargÃ©s depuis variable d'environnement
# Format: "email1@example.com,email2@example.com"
_admin_emails_env = os.environ.get('ADMIN_EMAILS', 'contact.artboost@gmail.com,afroboost.bassi@gmail.com')
SUPER_ADMIN_EMAILS = [e.strip().lower() for e in _admin_emails_env.split(',') if e.strip()]
SUPER_ADMIN_EMAIL = SUPER_ADMIN_EMAILS[0] if SUPER_ADMIN_EMAILS else ""  # Legacy - compatibilitÃ©
DEFAULT_COACH_ID = "bassi_default"  # ID par dÃ©faut pour les donnÃ©es existantes

# RÃ´les disponibles
ROLE_SUPER_ADMIN = "super_admin"
ROLE_COACH = "coach"
ROLE_USER = "user"
ROLE_PARTNER = "partner"

def get_user_role(email: str) -> str:
    """DÃ©termine le rÃ´le d'un utilisateur basÃ© sur son email"""
    if email and email.lower().strip() in [e.lower() for e in SUPER_ADMIN_EMAILS]:
        return ROLE_SUPER_ADMIN
    return ROLE_USER

def is_super_admin(email: str) -> bool:
    """VÃ©rifie si l'email est celui d'un Super Admin"""
    return email and email.lower().strip() in [e.lower() for e in SUPER_ADMIN_EMAILS]

def get_coach_filter(email: str) -> dict:
    """Retourne le filtre MongoDB pour l'isolation des donnÃ©es coach"""
    if is_super_admin(email):
        return {}
    return {"coach_id": email.lower().strip()}

# v9.0.2: Helper pour dÃ©duire les crÃ©dits
# v12.1: Support des prix variables par service
async def deduct_credit(coach_email: str, action: str = "action", amount: int = 1) -> dict:
    """DÃ©duit des crÃ©dits du compte coach. Retourne {success, credits_remaining, error}"""
    if is_super_admin(coach_email):
        return {"success": True, "credits_remaining": -1, "bypassed": True}
    coach = await db.coaches.find_one({"email": coach_email.lower()})
    if not coach:
        return {"success": False, "error": "Coach non trouvÃ©", "credits_remaining": 0}
    current_credits = coach.get("credits", 0)
    if current_credits < amount:
        return {"success": False, "error": f"CrÃ©dits insuffisants ({current_credits}/{amount})", "credits_remaining": current_credits}
    await db.coaches.update_one({"email": coach_email.lower()}, {"$inc": {"credits": -amount}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}})
    logger.info(f"[CREDITS] {coach_email} -{amount} crÃ©dit(s) ({action}) -> {current_credits - amount} restants")
    return {"success": True, "credits_remaining": current_credits - amount, "deducted": amount}

async def check_credits(coach_email: str, required: int = 1) -> dict:
    """VÃ©rifie le solde de crÃ©dits sans dÃ©duire"""
    if is_super_admin(coach_email):
        return {"has_credits": True, "credits": -1, "unlimited": True}
    coach = await db.coaches.find_one({"email": coach_email.lower()})
    if not coach:
        return {"has_credits": False, "credits": 0, "error": "Coach non trouvÃ©"}
    credits = coach.get("credits", 0)
    return {"has_credits": credits >= required, "credits": credits, "required": required}

# v12.1: Helper pour rÃ©cupÃ©rer le prix d'un service
async def get_service_price(service_name: str) -> int:
    """RÃ©cupÃ¨re le prix d'un service depuis platform_settings"""
    settings = await db.platform_settings.find_one({"_id": "global"})
    if settings and settings.get("service_prices"):
        return settings["service_prices"].get(service_name, 1)
    return 1  # Prix par dÃ©faut

# ASGI app - Socket.IO dÃ©sactivÃ© en mode Vercel Serverless
# app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)  # Removed for Vercel Serverless

# HEALTH CHECK
@fastapi_app.get("/health")
async def health_check():
    """Health check Kubernetes"""
    try:
        await client.admin.command('ping')
        return JSONResponse(status_code=200, content={"status": "healthy", "database": "connected"})
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "database": "disconnected", "error": str(e)}
        )

@fastapi_app.get("/api/health")
async def api_health_check():
    """Health check endpoint via /api prefix for Kubernetes"""
    return await health_check()

@fastapi_app.get("/api/debug/config")
async def debug_config(request: Request):
    """Debug endpoint â V133: protÃ©gÃ© par auth admin"""
    email = require_auth(request)
    if not is_super_admin(email):
        raise HTTPException(status_code=403, detail="AccÃ¨s rÃ©servÃ© aux administrateurs")
    mongo = os.environ.get('MONGO_URL', '')
    import re
    masked_mongo = re.sub(r'://([^:]+):([^@]+)@', r'://\1:****@', mongo) if mongo else 'NOT SET'

    return JSONResponse(content={
        "mongo_url_masked": masked_mongo,
        "db_name": os.environ.get('DB_NAME', 'NOT SET'),
        "frontend_url": os.environ.get('FRONTEND_URL', 'NOT SET'),
        "cors_origins": os.environ.get('CORS_ORIGINS', 'NOT SET'),
        "stripe_key_set": bool(os.environ.get('STRIPE_SECRET_KEY')),
        "openai_key_set": bool(os.environ.get('OPENAI_API_KEY')),
        "resend_key_set": bool(os.environ.get('RESEND_API_KEY')),
    })

@fastapi_app.get("/api/debug/network")
async def debug_network(request: Request):
    """Debug endpoint â V133: protÃ©gÃ© par auth admin"""
    email = require_auth(request)
    if not is_super_admin(email):
        raise HTTPException(status_code=403, detail="AccÃ¨s rÃ©servÃ© aux administrateurs")
    import socket
    import time
    results = {"dns_srv": [], "tcp_tests": [], "dns_txt": []}

    # Test DNS SRV resolution
    try:
        import dns.resolver
        srv_answers = dns.resolver.resolve('_mongodb._tcp.customer-apps.drejrt.mongodb.net', 'SRV')
        for rdata in srv_answers:
            host = str(rdata.target).rstrip('.')
            results["dns_srv"].append({"host": host, "port": rdata.port})
    except Exception as e:
        results["dns_srv_error"] = str(e)

    # Test DNS TXT (for replicaSet info)
    try:
        import dns.resolver
        txt_answers = dns.resolver.resolve('customer-apps.drejrt.mongodb.net', 'TXT')
        for rdata in txt_answers:
            results["dns_txt"].append(str(rdata))
    except Exception as e:
        results["dns_txt_error"] = str(e)

    # Test raw TCP connectivity to each shard
    hosts_to_test = [
        ("customer-apps-shard-00-00.drejrt.mongodb.net", 27017),
        ("customer-apps-shard-00-01.drejrt.mongodb.net", 27017),
        ("customer-apps-shard-00-02.drejrt.mongodb.net", 27017),
    ]
    for host, port in hosts_to_test:
        try:
            start = time.time()
            sock = socket.create_connection((host, port), timeout=5)
            elapsed = time.time() - start
            sock.close()
            results["tcp_tests"].append({"host": host, "port": port, "status": "OK", "time_ms": round(elapsed * 1000)})
        except Exception as e:
            results["tcp_tests"].append({"host": host, "port": port, "status": "FAILED", "error": str(e)})

    return JSONResponse(content=results)

# Favicon endpoint to prevent 404 errors
@fastapi_app.get("/api/favicon.ico")
async def favicon():
    """Return empty response for favicon requests to prevent 404 errors"""
    from starlette.responses import Response
    return Response(status_code=204)

@api_router.get("/favicon.ico")
async def api_favicon():
    """Return empty response for favicon requests via API router"""
    from starlette.responses import Response
    return Response(status_code=204)

# === FICHIERS STATIQUES EMOJIS ===
# StaticFiles mounts removed for Vercel Serverless - use CDN or external storage
# EMOJIS_DIR = ROOT_DIR / "uploads" / "emojis"
# UPLOADS_DIR = "/app/backend/uploads/profiles"
# COACHES_UPLOADS_DIR = "/app/backend/uploads/coaches"
EMOJIS_DIR = ROOT_DIR / "uploads" / "emojis"  # Keep for file operations reference
UPLOADS_DIR = "/app/backend/uploads/profiles"
COACHES_UPLOADS_DIR = "/app/backend/uploads/coaches"

# === MODELS ===

class AudioTrack(BaseModel):
    """v17.5: Piste audio enrichie pour le Studio Audio"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    url: str  # URL du fichier audio
    title: str = "Sans titre"
    cover_url: Optional[str] = None  # Pochette
    description: Optional[str] = ""
    price: float = 0.0  # 0 = gratuit
    preview_duration: int = 30  # DurÃ©e preview en secondes
    duration: Optional[float] = None  # DurÃ©e totale en secondes
    order: int = 0
    visible: bool = True  # En vente sur la vitrine

class Course(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    weekday: int
    time: str
    locationName: str
    location: Optional[str] = None  # Alias de locationName pour le frontend
    mapsUrl: Optional[str] = ""
    visible: bool = True
    archived: bool = False  # Archive au lieu de supprimer
    playlist: Optional[List[str]] = None  # Legacy: URLs simples
    audio_tracks: Optional[List[dict]] = None  # v17.5: Pistes audio enrichies (AudioTrack)
    coach_id: Optional[str] = None  # v19: Ownership â email du coach propriÃ©taire

class CourseCreate(BaseModel):
    name: str
    weekday: int
    time: str
    locationName: str
    mapsUrl: Optional[str] = ""
    visible: bool = True
    archived: bool = False
    playlist: Optional[List[str]] = None  # Legacy
    audio_tracks: Optional[List[dict]] = None  # v17.5: Pistes audio enrichies
    coach_id: Optional[str] = None  # v19: Ownership

class Offer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    price: float
    thumbnail: Optional[str] = ""
    videoUrl: Optional[str] = ""
    description: Optional[str] = ""
    keywords: Optional[str] = ""  # Mots-clÃ©s pour la recherche (invisible)
    visible: bool = True
    images: List[str] = []  # Support multi-images (max 5)
    # E-commerce fields
    category: Optional[str] = ""  # Ex: "service", "tshirt", "shoes", "supplement"
    isProduct: bool = False  # True = physical product, False = service/course
    variants: Optional[dict] = None  # { sizes: ["S","M","L"], colors: ["Noir","Blanc"], weights: ["0.5kg","1kg"] }
    tva: float = 0.0  # TVA percentage
    shippingCost: float = 0.0  # Frais de port
    stock: int = -1  # -1 = unlimited
    coach_id: Optional[str] = None  # v19: Ownership â email du coach propriÃ©taire
    # v59: DurÃ©e de validitÃ© & prolongation automatique
    duration_value: Optional[int] = None  # ex: 2 (nombre)
    duration_unit: Optional[str] = None   # "days", "weeks", "months"
    is_auto_prolong: bool = True          # prolongation automatique Ã  l'expiration
    created_at: Optional[str] = None      # ISO datetime de crÃ©ation
    expiration_date: Optional[str] = None # ISO datetime d'expiration calculÃ©e
    last_reminded_date: Optional[str] = None   # date dernier rappel J-7
    last_prolonged_date: Optional[str] = None  # date derniÃ¨re prolongation
    # V159: Compte Ã  rebours
    countdown_enabled: bool = False
    countdown_text: Optional[str] = ""
    countdown_date: Optional[str] = ""
    countdown_time: Optional[str] = "23:59"

class OfferCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    price: float
    thumbnail: Optional[str] = ""
    videoUrl: Optional[str] = ""
    description: Optional[str] = ""
    keywords: Optional[str] = ""  # Mots-clÃ©s pour la recherche
    visible: bool = True
    images: List[str] = []  # Support multi-images (max 5)
    # E-commerce fields
    category: Optional[str] = ""
    isProduct: bool = False
    variants: Optional[dict] = None
    tva: float = 0.0
    shippingCost: float = 0.0
    stock: int = -1
    coach_id: Optional[str] = None  # v19: Ownership
    # v61: DurÃ©e de validitÃ© â accepte int ou string pour tolÃ©rance frontend
    duration_value: Optional[Union[int, str]] = None
    duration_unit: Optional[str] = None
    is_auto_prolong: Union[bool, str] = True
    # V159: Compte Ã  rebours
    countdown_enabled: bool = False
    countdown_text: Optional[str] = ""
    countdown_date: Optional[str] = ""
    countdown_time: Optional[str] = "23:59"

class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    email: str
    whatsapp: Optional[str] = ""
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UserCreate(BaseModel):
    name: str
    email: str
    whatsapp: Optional[str] = ""

class Reservation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    reservationCode: str
    userId: str
    userName: str
    userEmail: str
    userWhatsapp: Optional[str] = ""
    courseId: str
    courseName: str
    courseTime: str
    datetime: str
    offerId: str
    offerName: str
    price: float
    quantity: int = 1
    totalPrice: float
    discountCode: Optional[str] = None
    discountType: Optional[str] = None
    discountValue: Optional[float] = None
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # E-commerce / Shipping fields
    validated: bool = False
    validatedAt: Optional[str] = None
    selectedVariants: Optional[dict] = None  # { size: "M", color: "Noir" }
    variantsText: Optional[str] = None  # "Taille: M, Couleur: Noir"
    shippingAddress: Optional[str] = None  # Adresse de livraison
    isProduct: bool = False  # True si produit physique
    tva: float = 0.0
    shippingCost: float = 0.0
    trackingNumber: Optional[str] = None  # NumÃ©ro de suivi colis
    shippingStatus: str = "pending"  # pending, shipped, delivered
    # Multi-date selection support
    selectedDates: Optional[List[str]] = None  # Array of ISO date strings
    selectedDatesText: Optional[str] = None  # Formatted text of selected dates
    # === NOUVEAUX CHAMPS: Origine et type abonnÃ© ===
    promoCode: Optional[str] = None  # Code promo utilisÃ© par l'abonnÃ©
    source: Optional[str] = None  # chat_widget, web, manual
    type: Optional[str] = None  # abonnÃ©, achat_direct

class ReservationCreate(BaseModel):
    userId: str
    userName: str
    userEmail: str
    userWhatsapp: Optional[str] = ""
    courseId: str
    courseName: str
    courseTime: str
    datetime: str
    offerId: str
    offerName: str
    price: float
    quantity: int = 1
    totalPrice: float
    discountCode: Optional[str] = None
    discountType: Optional[str] = None
    discountValue: Optional[float] = None
    selectedVariants: Optional[dict] = None
    variantsText: Optional[str] = None
    shippingAddress: Optional[str] = None
    isProduct: bool = False
    # Multi-date selection support
    selectedDates: Optional[List[str]] = None  # Array of ISO date strings
    selectedDatesText: Optional[str] = None  # Formatted text of selected dates
    # === NOUVEAUX CHAMPS: Origine et type abonnÃ© ===
    promoCode: Optional[str] = None  # Code promo utilisÃ© par l'abonnÃ©
    source: Optional[str] = None  # chat_widget, web, manual
    type: Optional[str] = None  # abonnÃ©, achat_direct

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

class DiscountCodeCreate(BaseModel):
    code: str
    type: str
    value: float
    assignedEmail: Optional[str] = None
    expiresAt: Optional[str] = None
    courses: List[str] = []
    maxUses: Optional[int] = None

class PaymentLinks(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = "payment_links"
    stripe: str = ""
    paypal: str = ""
    twint: str = ""
    coachWhatsapp: str = ""
    # Notifications automatiques pour le coach
    coachNotificationEmail: str = ""  # Email pour recevoir les alertes
    coachNotificationPhone: str = ""  # TÃ©lÃ©phone pour recevoir les alertes WhatsApp

class PaymentLinksUpdate(BaseModel):
    stripe: Optional[str] = ""
    paypal: Optional[str] = ""
    twint: Optional[str] = ""
    coachWhatsapp: Optional[str] = ""
    coachNotificationEmail: Optional[str] = ""
    coachNotificationPhone: Optional[str] = ""

# Campaign Models for Marketing Module
class CampaignResult(BaseModel):
    contactId: str
    contactName: str
    contactEmail: Optional[str] = ""
    contactPhone: Optional[str] = ""
    channel: str  # "whatsapp", "email", "instagram"
    status: str = "pending"  # "pending", "sent", "failed"
    sentAt: Optional[str] = None

class Campaign(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    message: str
    mediaUrl: Optional[str] = ""
    mediaFormat: str = "16:9"  # "9:16" or "16:9"
    mediaType: Optional[str] = None  # v11: 'upload', 'youtube', 'drive', 'image', 'link'
    targetType: str = "all"  # "all" or "selected"
    selectedContacts: List[str] = []
    channels: dict = Field(default_factory=lambda: {"whatsapp": True, "email": False, "instagram": False, "group": False, "internal": False})
    targetGroupId: Optional[str] = "community"  # ID du groupe cible pour le canal "group"
    targetIds: Optional[List[str]] = []  # Tableau des IDs du panier (nouveau systÃ¨me)
    targetConversationId: Optional[str] = None  # ID de la conversation interne (legacy - premier du panier)
    targetConversationName: Optional[str] = None  # Nom de la conversation pour affichage
    scheduledAt: Optional[str] = None  # ISO date or null for immediate
    status: str = "draft"  # "draft", "scheduled", "sending", "completed"
    # Champs CTA pour boutons d'action
    ctaType: Optional[str] = None  # "reserver", "offre", "personnalise"
    ctaText: Optional[str] = None  # Texte du bouton
    ctaLink: Optional[str] = None  # URL du bouton
    # v11: Prompts indÃ©pendants par campagne
    systemPrompt: Optional[str] = None  # Instructions systÃ¨me IA pour cette campagne
    descriptionPrompt: Optional[str] = None  # Prompt de description/objectif spÃ©cifique
    # V115: Choix de l'expÃ©diteur WhatsApp â "business" (prod +41765203363) par dÃ©faut
    senderType: Optional[str] = "business"  # "business" = +41 76 520 33 63 (prod), "custom" = numÃ©ro partenaire perso
    coach_id: Optional[str] = None  # v11: Email du coach propriÃ©taire
    results: List[dict] = []
    createdAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updatedAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class CampaignCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    message: str
    mediaUrl: Optional[str] = ""
    mediaFormat: str = "16:9"
    mediaType: Optional[str] = None  # v11: 'upload', 'youtube', 'drive', 'image', 'link'
    targetType: str = "all"
    selectedContacts: List[str] = []
    channels: dict = Field(default_factory=lambda: {"whatsapp": True, "email": False, "instagram": False, "group": False, "internal": False})
    targetGroupId: Optional[str] = "community"
    targetIds: Optional[List[str]] = []
    targetConversationId: Optional[str] = None
    targetConversationName: Optional[str] = None
    scheduledAt: Optional[str] = None
    ctaType: Optional[str] = None
    ctaText: Optional[str] = None
    ctaLink: Optional[str] = None
    # v11: Prompts indÃ©pendants par campagne
    systemPrompt: Optional[str] = None
    descriptionPrompt: Optional[str] = None
    # V115: Choix de l'expÃ©diteur WhatsApp â "business" (prod +41765203363) par dÃ©faut
    senderType: Optional[str] = "business"  # "business" = +41 76 520 33 63 (prod), "custom" = numÃ©ro partenaire perso

class Concept(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = "concept"
    appName: str = "Afroboost"  # Nom de l'application (titre principal)
    description: str = "Le concept Afroboost : cardio + danse afrobeat + casques audio immersifs. Un entraÃ®nement fun, Ã©nergÃ©tique et accessible Ã  tous."
    heroImageUrl: str = ""
    heroVideoUrl: str = ""
    heroVideos: List[dict] = []  # v18: Multi-vidÃ©os [{url, type: 'youtube'|'upload', title}] max 3
    logoUrl: str = ""
    faviconUrl: str = ""
    termsText: str = ""  # CGV - Conditions GÃ©nÃ©rales de Vente
    termsTextPartners: str = ""  # V93.6: CGP - Conditions GÃ©nÃ©rales Partenaires
    googleReviewsUrl: str = ""  # Lien avis Google
    defaultLandingSection: str = "sessions"  # Section d'atterrissage par dÃ©faut: "sessions", "offers", "shop"
    vitrineSectionOrder: str = "sessions-first"  # V119: Ordre des sections vitrine: "sessions-first" ou "offers-first"
    # Liens externes
    externalLink1Title: str = ""
    externalLink1Url: str = ""
    externalLink2Title: str = ""
    externalLink2Url: str = ""
    # Modes de paiement acceptÃ©s
    paymentTwint: bool = False
    paymentPaypal: bool = False
    paymentCreditCard: bool = False
    # Affiche ÃvÃ©nement (popup)
    eventPosterEnabled: bool = False
    eventPosterMediaUrl: str = ""  # URL image ou vidÃ©o
    # Personnalisation des couleurs
    primaryColor: str = "#D91CD2"  # Couleur principale (glow)
    secondaryColor: str = "#8b5cf6"  # Couleur secondaire
    # v9.4.4: Couleurs avancÃ©es
    backgroundColor: str = "#000000"  # Couleur de fond du site
    glowColor: str = ""  # Couleur du glow (auto si vide = primaryColor)

class ConceptUpdate(BaseModel):
    appName: Optional[str] = None  # Nom de l'application
    description: Optional[str] = None
    heroImageUrl: Optional[str] = None
    heroVideoUrl: Optional[str] = None
    heroVideos: Optional[List[dict]] = None  # v18: Multi-vidÃ©os max 3
    logoUrl: Optional[str] = None
    faviconUrl: Optional[str] = None
    termsText: Optional[str] = None  # CGV - Conditions GÃ©nÃ©rales de Vente
    termsTextPartners: Optional[str] = None  # V93.6: CGP - Conditions GÃ©nÃ©rales Partenaires
    googleReviewsUrl: Optional[str] = None  # Lien avis Google
    defaultLandingSection: Optional[str] = None  # Section d'atterrissage par dÃ©faut
    vitrineSectionOrder: Optional[str] = None  # V119: Ordre des sections vitrine
    # Liens externes
    externalLink1Title: Optional[str] = None
    externalLink1Url: Optional[str] = None
    externalLink2Title: Optional[str] = None
    externalLink2Url: Optional[str] = None
    # Modes de paiement acceptÃ©s
    paymentTwint: Optional[bool] = None
    paymentPaypal: Optional[bool] = None
    paymentCreditCard: Optional[bool] = None
    # Affiche ÃvÃ©nement (popup)
    eventPosterEnabled: Optional[bool] = None
    eventPosterMediaUrl: Optional[str] = None
    # Personnalisation des couleurs
    primaryColor: Optional[str] = None
    secondaryColor: Optional[str] = None
    # v9.4.4: Couleurs avancÃ©es
    backgroundColor: Optional[str] = None
    glowColor: Optional[str] = None

class AppConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = "app_config"
    background_color: str = "#020617"
    gradient_color: str = "#3b0764"
    primary_color: str = "#d91cd2"
    secondary_color: str = "#8b5cf6"
    text_color: str = "#ffffff"
    font_family: str = "system-ui"
    font_size: int = 16
    app_title: str = "Afroboost"
    app_subtitle: str = "RÃ©servation de casque"
    concept_description: str = "Le concept Afroboost : cardio + danse afrobeat + casques audio immersifs."
    choose_session_text: str = "Choisissez votre session"
    choose_offer_text: str = "Choisissez votre offre"
    user_info_text: str = "Vos informations"
    button_text: str = "RÃ©server maintenant"

# FEATURE FLAGS
class FeatureFlags(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = "feature_flags"
    AUDIO_SERVICE_ENABLED: bool = False
    VIDEO_SERVICE_ENABLED: bool = False
    STREAMING_SERVICE_ENABLED: bool = False
    updatedAt: Optional[str] = None
    updatedBy: Optional[str] = None

class FeatureFlagsUpdate(BaseModel):
    AUDIO_SERVICE_ENABLED: Optional[bool] = None
    VIDEO_SERVICE_ENABLED: Optional[bool] = None
    STREAMING_SERVICE_ENABLED: Optional[bool] = None

# === SYSTÃME MULTI-COACH v8.9 - MODÃLES ===

class CoachPack(BaseModel):
    """Pack d'abonnement pour les coachs partenaires"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str  # Ex: "Pack Starter", "Pack Pro"
    price: float  # Prix en CHF
    credits: int  # Nombre de crÃ©dits inclus
    description: str = ""
    stripe_price_id: Optional[str] = None  # ID du prix Stripe
    stripe_product_id: Optional[str] = None  # ID du produit Stripe
    features: List[str] = []  # Liste des fonctionnalitÃ©s
    visible: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: Optional[str] = None

class CoachPackCreate(BaseModel):
    name: str
    price: float
    credits: int
    description: str = ""
    features: List[str] = []
    visible: bool = True

class CoachPackUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None
    credits: Optional[int] = None
    description: Optional[str] = None
    features: Optional[List[str]] = None
    visible: Optional[bool] = None

class Coach(BaseModel):
    """Profil d'un coach partenaire"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str  # Email unique du coach
    name: str
    phone: Optional[str] = None
    photo_url: Optional[str] = None
    bio: Optional[str] = None
    platform_name: Optional[str] = None  # v9.0.1 Nom personnalisÃ© de la plateforme
    logo_url: Optional[str] = None  # v9.0.1 Logo personnalisÃ©
    role: str = "coach"  # "coach" ou "super_admin"
    credits: int = 0  # Solde de crÃ©dits actuel
    stripe_customer_id: Optional[str] = None
    stripe_connect_id: Optional[str] = None
    pack_id: Optional[str] = None
    is_active: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: Optional[str] = None
    last_login: Optional[str] = None

class CoachCreate(BaseModel):
    email: str
    name: str
    phone: Optional[str] = None
    bio: Optional[str] = None
    pack_id: Optional[str] = None
    credits: int = 0

# COACH SUBSCRIPTION
class CoachSubscription(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    coachEmail: str
    hasAudioService: bool = False
    hasVideoService: bool = False
    hasStreamingService: bool = False
    subscriptionPlan: str = "free"
    subscriptionStartDate: Optional[str] = None
    subscriptionEndDate: Optional[str] = None
    isActive: bool = True
    createdAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updatedAt: Optional[str] = None

class CoachSubscriptionUpdate(BaseModel):
    hasAudioService: Optional[bool] = None
    hasVideoService: Optional[bool] = None
    hasStreamingService: Optional[bool] = None
    subscriptionPlan: Optional[str] = None
    subscriptionEndDate: Optional[str] = None
    isActive: Optional[bool] = None

class CoachAuth(BaseModel):
    email: str
    password: str

class CoachLogin(BaseModel):
    email: str
    password: str

# --- Lead Model (Widget IA) ---
class Lead(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = ""
    firstName: str
    whatsapp: str
    email: str
    createdAt: str = ""
    source: str = "widget_ia"

class ChatMessage(BaseModel):
    message: str
    leadId: str = ""
    firstName: str = ""
    email: str = ""  # Email pour CRM auto-save
    whatsapp: str = ""  # WhatsApp pour CRM auto-save
    source: str = "chat_ia"  # Source du contact (lien chat IA)
    link_token: str = ""  # Token du lien pour rÃ©cupÃ©rer le custom_prompt

# CHAT SYSTEM
class ChatParticipant(BaseModel):
    """Participant au chat"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    whatsapp: Optional[str] = ""
    email: Optional[str] = ""
    source: str = "chat_afroboost"  # Source par dÃ©faut, peut identifier un lien spÃ©cifique
    link_token: Optional[str] = None  # Token du lien via lequel l'utilisateur est arrivÃ©
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_seen_at: Optional[str] = None
    birthday: Optional[str] = None  # V160: Date de naissance (format MM-DD)

class ChatParticipantCreate(BaseModel):
    name: str
    whatsapp: Optional[str] = ""
    email: Optional[str] = ""
    source: str = "chat_afroboost"
    link_token: Optional[str] = None
    birthday: Optional[str] = None  # V160: Date de naissance (format MM-DD)

class ChatSession(BaseModel):
    """Session de chat avec gestion des modes et participants"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    participant_ids: List[str] = []  # Liste des IDs de participants
    mode: str = "ai"  # "ai", "human", "community"
    is_ai_active: bool = True  # Interrupteur pour dÃ©sactiver l'IA
    is_deleted: bool = False  # Suppression logique
    link_token: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])  # Token unique pour partage
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: Optional[str] = None
    deleted_at: Optional[str] = None
    # MÃ©tadonnÃ©es pour le coach
    title: Optional[str] = None  # Titre optionnel pour identifier la session
    notes: Optional[str] = None  # Notes du coach sur cette session
    # Prompt spÃ©cifique au lien (PRIORITAIRE sur campaignPrompt)
    custom_prompt: Optional[str] = None  # Nullable - si vide, utilise campaignPrompt global

class ChatSessionCreate(BaseModel):
    mode: str = "ai"
    is_ai_active: bool = True
    title: Optional[str] = None

class ChatSessionUpdate(BaseModel):
    mode: Optional[str] = None
    is_ai_active: Optional[bool] = None
    is_deleted: Optional[bool] = None
    title: Optional[str] = None
    notes: Optional[str] = None
    custom_prompt: Optional[str] = None  # Prompt spÃ©cifique au lien

class EnhancedChatMessage(BaseModel):
    """Message de chat ameliore avec session, sender et suppression logique"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    sender_id: str
    sender_name: str
    sender_type: str = "user"
    content: str
    mode: str = "ai"
    is_deleted: bool = False
    is_group: bool = False  # v8.6: True si message de groupe
    notified: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    deleted_at: Optional[str] = None

class EnhancedChatMessageCreate(BaseModel):
    session_id: str
    sender_id: str
    sender_name: str
    sender_type: str = "user"
    content: str

class ChatLinkResponse(BaseModel):
    """RÃ©ponse pour la gÃ©nÃ©ration de lien partageable"""
    link_token: str
    share_url: str
    session_id: str

# === MESSAGERIE PRIVÃE (MP) - Isolation totale de l'IA ===
class PrivateMessage(BaseModel):
    """Message privÃ© entre deux participants - INVISIBLE pour l'IA"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str  # ID unique de la conversation MP
    sender_id: str
    sender_name: str
    recipient_id: str
    recipient_name: str
    content: str
    is_read: bool = False
    is_deleted: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class PrivateConversation(BaseModel):
    """Conversation privÃ©e entre deux participants"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    participant_1_id: str
    participant_1_name: str
    participant_2_id: str
    participant_2_name: str
    last_message: Optional[str] = None
    last_message_at: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

# === FONCTION UTILITAIRE: Formatage unifie des messages ===
def format_message_for_frontend(m: dict) -> dict:
    """Convertit un message MongoDB vers le format attendu par le frontend."""
    return {
        "id": m.get("id"), "type": "user" if m.get("sender_type") == "user" else ("coach" if m.get("sender_type") == "coach" else "ai"),
        "text": m.get("content", "") or m.get("text", ""), "sender": (m.get("sender_name") or m.get("sender", "")).replace("ðª ", ""),
        "senderId": m.get("sender_id") or m.get("senderId", ""), "sender_type": m.get("sender_type", "ai"),
        "created_at": m.get("created_at"), "media_url": m.get("media_url"), "media_type": m.get("media_type"),
        "cta_type": m.get("cta_type"), "cta_text": m.get("cta_text"), "cta_link": m.get("cta_link"),
        "broadcast": m.get("broadcast", False), "scheduled": m.get("scheduled", False)
    }

# ROUTES

# V109.2: Endpoint MediaViewer â retourne les donnÃ©es d'un media_link par slug
@api_router.get("/media/{slug}")
async def get_media_by_slug(slug: str):
    """RÃ©cupÃ¨re un media_link par son slug pour le MediaViewer frontend."""
    media = await db.media_links.find_one({"slug": slug.lower()}, {"_id": 0})
    if not media:
        raise HTTPException(status_code=404, detail="MÃ©dia non trouvÃ©")
    # Enrichir avec youtube_id si c'est une URL YouTube
    video_url = media.get("video_url", "")
    if video_url and ("youtube.com" in video_url or "youtu.be" in video_url):
        import re as re_mv
        yt_match = re_mv.search(r'(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})', video_url)
        if yt_match:
            media["youtube_id"] = yt_match.group(1)
    return media

# V109.2: Endpoint PUT pour modifier un media_link
@api_router.put("/media/{slug}")
async def update_media_by_slug(slug: str, request: Request):
    """Met Ã  jour un media_link existant (description, cta_text, cta_link, etc.)."""
    body = await request.json()
    allowed_fields = ["title", "description", "cta_text", "cta_link", "thumbnail", "custom_thumbnail", "video_url"]
    update_data = {k: v for k, v in body.items() if k in allowed_fields}
    if not update_data:
        raise HTTPException(status_code=400, detail="Aucun champ valide Ã  mettre Ã  jour")
    result = await db.media_links.update_one({"slug": slug.lower()}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="MÃ©dia non trouvÃ©")
    return {"success": True, "updated_fields": list(update_data.keys())}

# V109.2: Endpoint POST pour crÃ©er un media_link
@api_router.post("/media")
async def create_media_link(request: Request):
    """CrÃ©e un nouveau media_link pour le MediaViewer."""
    body = await request.json()
    slug = body.get("slug", "").strip().lower()
    video_url = body.get("video_url", "").strip()
    if not slug or not video_url:
        raise HTTPException(status_code=400, detail="slug et video_url requis")
    # VÃ©rifier si le slug existe dÃ©jÃ 
    existing = await db.media_links.find_one({"slug": slug}, {"_id": 0, "slug": 1})
    if existing:
        raise HTTPException(status_code=409, detail="Ce slug existe dÃ©jÃ ")
    doc = {
        "slug": slug,
        "video_url": video_url,
        "thumbnail": body.get("thumbnail"),
        "custom_thumbnail": body.get("custom_thumbnail"),
        "title": body.get("title", "VidÃ©o Afroboost"),
        "description": body.get("description", ""),
        "cta_text": body.get("cta_text"),
        "cta_link": body.get("cta_link"),
        "created_at": datetime.utcnow().isoformat()
    }
    await db.media_links.insert_one(doc)
    doc.pop("_id", None)
    return doc

@api_router.get("/")
async def root():
    return {"message": "Afroboost API"}

@api_router.get("/courses", response_model=List[Course])
async def get_courses():
    courses_raw = await db.courses.find({"archived": {"$ne": True}}, {"_id": 0}).to_list(100)
    if not courses_raw:
        default_courses = [
            {"id": str(uuid.uuid4()), "name": "Afroboost Silent â Session Cardio", "weekday": 3, "time": "18:30", "locationName": "Rue des Vallangines 97, NeuchÃ¢tel", "mapsUrl": ""},
            {"id": str(uuid.uuid4()), "name": "Afroboost Silent â Sunday Vibes", "weekday": 0, "time": "18:30", "locationName": "Rue des Vallangines 97, NeuchÃ¢tel", "mapsUrl": ""}
        ]
        await db.courses.insert_many(default_courses)
        courses_raw = default_courses
    
    # === FIX: Ajouter "location" comme alias de "locationName" pour le frontend ===
    # CrÃ©er une copie des cours pour ajouter le champ location
    courses = []
    for course in courses_raw:
        course_copy = dict(course)
        if "locationName" in course_copy:
            course_copy["location"] = course_copy["locationName"]
        courses.append(course_copy)
    
    return courses

@api_router.post("/courses", response_model=Course)
async def create_course(course: CourseCreate, request: Request):
    # SÃ©curitÃ© : vÃ©rifier que l'utilisateur est authentifiÃ©
    # v19: Auto-set coach_id depuis le header d'authentification
    user_email = require_auth(request)
    course_data = course.model_dump()
    if user_email and not course_data.get("coach_id"):
        course_data["coach_id"] = user_email
    course_obj = Course(**course_data)
    await db.courses.insert_one(course_obj.model_dump())
    return course_obj

@api_router.put("/courses/{course_id}")
async def update_course(course_id: str, course_update: dict, request: Request):
    """Update a course - supports partial updates including playlist and audio_tracks"""
    # SÃ©curitÃ© : vÃ©rifier que l'utilisateur est authentifiÃ©
    require_auth(request)
    # RÃ©cupÃ©rer le cours existant
    existing = await db.courses.find_one({"id": course_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Cours non trouvÃ©")
    
    # Fusionner les donnÃ©es (mise Ã  jour partielle)
    update_data = {k: v for k, v in course_update.items() if v is not None}
    
    await db.courses.update_one({"id": course_id}, {"$set": update_data})
    updated = await db.courses.find_one({"id": course_id}, {"_id": 0})
    return updated

@api_router.put("/courses/{course_id}/archive")
async def archive_course(course_id: str, request: Request):
    """Archive a course instead of deleting it"""
    # SÃ©curitÃ© : vÃ©rifier que l'utilisateur est authentifiÃ©
    require_auth(request)
    await db.courses.update_one({"id": course_id}, {"$set": {"archived": True}})
    updated = await db.courses.find_one({"id": course_id}, {"_id": 0})
    return {"success": True, "course": updated}

@api_router.delete("/courses/{course_id}")
async def delete_course(course_id: str, request: Request):
    """
    HARD DELETE - Supprime PHYSIQUEMENT un cours de toutes les tables.
    Aucune trace ne doit rester dans la base de donnÃ©es.
    """
    # SÃ©curitÃ© : vÃ©rifier que l'utilisateur est authentifiÃ©
    require_auth(request)
    deleted_counts = {
        "course": 0,
        "reservations": 0,
        "sessions": 0
    }
    
    # 1. Supprimer le cours (y compris les archivÃ©s)
    result = await db.courses.delete_one({"id": course_id})
    deleted_counts["course"] = result.deleted_count
    
    # 2. Supprimer TOUTES les rÃ©servations liÃ©es Ã  ce cours
    result = await db.reservations.delete_many({"courseId": course_id})
    deleted_counts["reservations"] = result.deleted_count
    
    # 3. Supprimer les sessions/rÃ©fÃ©rences potentielles liÃ©es au cours
    # (au cas oÃ¹ des sessions de chat sont liÃ©es Ã  un cours spÃ©cifique)
    result = await db.chat_sessions.delete_many({"courseId": course_id})
    deleted_counts["sessions"] = result.deleted_count
    
    total_deleted = sum(deleted_counts.values())
    logger.info(f"[HARD DELETE] Cours {course_id} - SupprimÃ©: cours={deleted_counts['course']}, rÃ©servations={deleted_counts['reservations']}, sessions={deleted_counts['sessions']}")
    
    # 4. ÃMETTRE UN ÃVÃNEMENT SOCKET.IO pour synchronisation temps rÃ©el
    # Socket.IO dÃ©sactivÃ© en mode Vercel Serverless
    logger.debug(f"[SOCKET.IO] ÃvÃ©nement course_deleted (disabled in Vercel Serverless) pour {course_id}")
    
    return {
        "success": True, 
        "hardDelete": True,
        "deleted": deleted_counts,
        "total": total_deleted
    }

@api_router.delete("/courses/purge/archived")
async def purge_archived_courses(request: Request):
    """
    PURGE TOTAL - Supprime tous les cours archivÃ©s et leurs donnÃ©es liÃ©es.
    UtilisÃ© pour nettoyer la base de donnÃ©es des cours obsolÃ¨tes.
    """
    # SÃ©curitÃ© : vÃ©rifier que l'utilisateur est authentifiÃ©
    require_auth(request)
    # Trouver tous les cours archivÃ©s
    archived_courses = await db.courses.find({"archived": True}, {"id": 1}).to_list(1000)
    archived_ids = [c["id"] for c in archived_courses]
    
    if not archived_ids:
        return {"success": True, "message": "Aucun cours archivÃ© Ã  purger", "purged": 0}
    
    # Supprimer les cours archivÃ©s
    deleted_courses = await db.courses.delete_many({"archived": True})
    
    # Supprimer les rÃ©servations liÃ©es
    deleted_reservations = await db.reservations.delete_many({"courseId": {"$in": archived_ids}})
    
    logger.info(f"[PURGE] SupprimÃ© {deleted_courses.deleted_count} cours archivÃ©s et {deleted_reservations.deleted_count} rÃ©servations")
    
    # Ãmettre un Ã©vÃ©nement pour rafraÃ®chir tous les clients
    # Socket.IO dÃ©sactivÃ© en mode Vercel Serverless
    logger.debug(f"[SOCKET.IO] ÃvÃ©nement courses_purged (disabled in Vercel Serverless)")
    
    return {
        "success": True,
        "purgedCourses": deleted_courses.deleted_count,
        "purgedReservations": deleted_reservations.deleted_count,
        "purgedIds": archived_ids
    }

# --- v59: Helper calcul date expiration ---
def calculate_expiration_date(from_date_str: str, duration_value: int, duration_unit: str) -> str:
    """Calcule la date d'expiration Ã  partir d'une date + durÃ©e"""
    from_date = datetime.fromisoformat(from_date_str.replace('Z', '+00:00')) if isinstance(from_date_str, str) else from_date_str
    if duration_unit == "months":
        delta = timedelta(days=duration_value * 30)
    elif duration_unit == "weeks":
        delta = timedelta(weeks=duration_value)
    elif duration_unit == "days":
        delta = timedelta(days=duration_value)
    else:
        return None
    return (from_date + delta).isoformat()

# --- Offers ---
@api_router.get("/offers", response_model=List[Offer])
async def get_offers():
    offers = await db.offers.find({}).to_list(100)
    if not offers:
        default_offers = [
            {"id": str(uuid.uuid4()), "name": "Cours Ã  l'unitÃ©", "price": 30, "thumbnail": "", "videoUrl": "", "description": "", "visible": True},
            {"id": str(uuid.uuid4()), "name": "Carte 10 cours", "price": 150, "thumbnail": "", "videoUrl": "", "description": "", "visible": True},
            {"id": str(uuid.uuid4()), "name": "Abonnement 1 mois", "price": 109, "thumbnail": "", "videoUrl": "", "description": "", "visible": True}
        ]
        await db.offers.insert_many(default_offers)
        return default_offers
    # v152: Migration â ajouter un champ 'id' persistant si absent
    result = []
    for o in offers:
        if "id" not in o or not o["id"]:
            new_id = str(uuid.uuid4())
            await db.offers.update_one({"_id": o["_id"]}, {"$set": {"id": new_id}})
            o["id"] = new_id
            print(f"[V152] Migrated offer '{o.get('name')}' â id={new_id}")
        o.pop("_id", None)
        result.append(o)
    return result

@api_router.post("/offers", response_model=Offer)
async def create_offer(offer: OfferCreate, request: Request):
    user_email = require_auth(request)
    offer_data = offer.model_dump()
    # v61: Blindage conversion durÃ©e â accepte string, int, vide, null
    raw_dv = offer_data.get("duration_value")
    if raw_dv is not None and raw_dv != "" and raw_dv is not False:
        try:
            offer_data["duration_value"] = int(raw_dv)
        except (ValueError, TypeError):
            offer_data["duration_value"] = None
    else:
        offer_data["duration_value"] = None
    if not offer_data.get("duration_unit") or offer_data["duration_unit"] == "":
        offer_data["duration_unit"] = None
    # Normaliser is_auto_prolong
    iap = offer_data.get("is_auto_prolong")
    offer_data["is_auto_prolong"] = iap not in (False, "false", "0", 0, None)
    print(f"[V61 DEBUG] POST /offers duration_value={offer_data.get('duration_value')} duration_unit={offer_data.get('duration_unit')} is_auto_prolong={offer_data.get('is_auto_prolong')}")
    if user_email and not offer_data.get("coach_id"):
        offer_data["coach_id"] = user_email
    # v59: Calculer expiration si durÃ©e dÃ©finie
    now_iso = datetime.utcnow().isoformat()
    offer_data["created_at"] = now_iso
    if offer_data.get("duration_value") and offer_data.get("duration_unit"):
        offer_data["expiration_date"] = calculate_expiration_date(now_iso, offer_data["duration_value"], offer_data["duration_unit"])
    offer_obj = Offer(**offer_data)
    await db.offers.insert_one(offer_obj.model_dump())
    return offer_obj

@api_router.put("/offers/{offer_id}", response_model=Offer)
async def update_offer(offer_id: str, offer: OfferCreate, request: Request):
    try:
        require_auth(request)
        update_data = offer.model_dump()
        # v61: Blindage conversion durÃ©e
        raw_dv = update_data.get("duration_value")
        if raw_dv is not None and raw_dv != "" and raw_dv is not False:
            try:
                update_data["duration_value"] = int(raw_dv)
            except (ValueError, TypeError):
                update_data["duration_value"] = None
        else:
            update_data["duration_value"] = None
        if not update_data.get("duration_unit") or update_data["duration_unit"] == "":
            update_data["duration_unit"] = None
        iap = update_data.get("is_auto_prolong")
        update_data["is_auto_prolong"] = iap not in (False, "false", "0", 0, None)
        # v152: Trouver l'offre existante (par id)
        existing = await db.offers.find_one({"id": offer_id})
        if not existing:
            raise HTTPException(status_code=404, detail=f"Offre {offer_id} introuvable")
        # v152: PrÃ©server coach_id existant (le frontend ne l'envoie pas)
        if not update_data.get("coach_id") and existing.get("coach_id"):
            update_data["coach_id"] = existing["coach_id"]
        # v59: Recalculer expiration si durÃ©e modifiÃ©e
        if update_data.get("duration_value") and update_data.get("duration_unit"):
            created_at = existing.get("created_at") or datetime.utcnow().isoformat()
            update_data["created_at"] = created_at
            update_data["expiration_date"] = calculate_expiration_date(created_at, update_data["duration_value"], update_data["duration_unit"])
            if existing.get("duration_value") != update_data["duration_value"] or existing.get("duration_unit") != update_data["duration_unit"]:
                update_data["last_reminded_date"] = None
                update_data["last_prolonged_date"] = None
        else:
            update_data["expiration_date"] = None
        await db.offers.update_one({"_id": existing["_id"]}, {"$set": update_data})
        updated = await db.offers.find_one({"_id": existing["_id"]}, {"_id": 0})
        return updated
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[V152 ERROR] PUT /offers/{offer_id}: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Erreur update offre: {str(e)}")

@api_router.delete("/offers/{offer_id}")
async def delete_offer(offer_id: str, request: Request):
    """v20: Supprime une offre avec vÃ©rification d'ownership + nettoyage codes promo"""
    user_email = require_auth(request)

    # v152: VÃ©rifier que l'offre existe (par id)
    offer = await db.offers.find_one({"id": offer_id})
    if not offer:
        raise HTTPException(status_code=404, detail="Offre non trouvÃ©e")

    # v20: VÃ©rifier l'ownership â Super Admin peut tout supprimer, sinon uniquement ses propres offres
    if not is_super_admin(user_email):
        offer_owner = (offer.get("coach_id") or "").lower()
        if offer_owner and offer_owner != user_email:
            raise HTTPException(status_code=403, detail="Vous ne pouvez supprimer que vos propres offres")

    # 1. Supprimer l'offre (utiliser _id MongoDB pour fiabilitÃ©)
    result = await db.offers.delete_one({"_id": offer["_id"]})
    logger.info(f"[DELETE-OFFER] {offer_id} supprimÃ©e par {user_email}, deleted_count={result.deleted_count}")

    # 2. Nettoyer les rÃ©fÃ©rences dans les codes promo
    await db.discount_codes.update_many(
        {"courses": offer_id},
        {"$pull": {"courses": offer_id}}
    )

    return {"success": True, "message": "Offre supprimÃ©e et rÃ©fÃ©rences nettoyÃ©es"}

# --- Product Categories ---
@api_router.get("/categories")
async def get_categories():
    categories = await db.categories.find({}, {"_id": 0}).to_list(100)
    return categories if categories else [
        {"id": "service", "name": "Services & Cours", "icon": "ð§"},
        {"id": "tshirt", "name": "T-shirts", "icon": "ð"},
        {"id": "shoes", "name": "Chaussures", "icon": "ð"},
        {"id": "supplement", "name": "ComplÃ©ments", "icon": "ð"},
        {"id": "accessory", "name": "Accessoires", "icon": "ð"}
    ]

@api_router.post("/categories")
async def create_category(category: dict):
    category["id"] = category.get("id") or str(uuid.uuid4())[:8]
    await db.categories.insert_one(category)
    return category

# --- Users ---
@api_router.get("/users", response_model=List[User])
async def get_users(request: Request):
    # Filtrage par coach_id si un coach est connectÃ© (super_admin voit tout)
    try:
        coach_email = require_auth(request)
    except HTTPException:
        coach_email = ""
    query = {}
    if coach_email and not is_super_admin(coach_email):
        # Un coach ne voit que ses propres utilisateurs (inscrits via son lien)
        query = {"$or": [
            {"coach_id": coach_email},
            {"coach_id": {"$exists": False}}  # Utilisateurs sans coach assignÃ© (legacy)
        ]}
    users = await db.users.find(query, {"_id": 0}).to_list(1000)
    for user in users:
        if isinstance(user.get('createdAt'), str):
            user['createdAt'] = datetime.fromisoformat(user['createdAt'].replace('Z', '+00:00'))
    return users

@api_router.post("/users", response_model=User)
async def create_user(user: UserCreate):
    user_obj = User(**user.model_dump())
    doc = user_obj.model_dump()
    doc['createdAt'] = doc['createdAt'].isoformat()
    await db.users.insert_one(doc)
    return user_obj

@api_router.get("/users/{user_id}", response_model=User)
async def get_user(user_id: str):
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if isinstance(user.get('createdAt'), str):
        user['createdAt'] = datetime.fromisoformat(user['createdAt'].replace('Z', '+00:00'))
    return user

@api_router.put("/users/{user_id}", response_model=User)
async def update_user(user_id: str, user: UserCreate):
    """Update an existing user/contact"""
    existing = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")
    
    update_data = user.model_dump()
    await db.users.update_one({"id": user_id}, {"$set": update_data})
    updated = await db.users.find_one({"id": user_id}, {"_id": 0})
    if isinstance(updated.get('createdAt'), str):
        updated['createdAt'] = datetime.fromisoformat(updated['createdAt'].replace('Z', '+00:00'))
    return updated

@api_router.delete("/users/{user_id}")
async def delete_user(user_id: str):
    """Supprime un utilisateur/contact et nettoie les rÃ©fÃ©rences dans les codes promo"""
    # 1. RÃ©cupÃ©rer l'email de l'utilisateur avant suppression
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_email = user.get("email")
    
    # 2. Supprimer l'utilisateur
    await db.users.delete_one({"id": user_id})
    
    # 3. Nettoyer les rÃ©fÃ©rences dans les codes promo (retirer l'email des assignedEmail)
    if user_email:
        await db.discount_codes.update_many(
            {"assignedEmail": user_email},
            {"$set": {"assignedEmail": None}}
        )
    
    return {"success": True, "message": "Contact supprimÃ© et rÃ©fÃ©rences nettoyÃ©es"}

# --- Photo de profil (MOTEUR D'UPLOAD RÃEL) ---
@api_router.post("/users/upload-photo")
async def upload_user_photo(file: UploadFile = File(...), participant_id: str = Form(...)):
    """
    v75: MOTEUR D'UPLOAD PHOTO PROFIL â Stockage MongoDB (compatible Vercel)
    1. ReÃ§oit l'image via UploadFile
    2. Redimensionne Ã  200x200 max
    3. Sauvegarde dans MongoDB collection 'uploaded_files' (pas le filesystem Ã©phÃ©mÃ¨re)
    4. Met Ã  jour photo_url dans 'users' ET 'chat_participants'
    5. Retourne l'URL /api/files/{file_id}/{filename} pour synchronisation
    """
    from PIL import Image
    import io
    import uuid
    from bson.binary import Binary

    # Validation du type MIME
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Type de fichier non supportÃ©. Envoyez une image.")

    # Lire le contenu du fichier
    contents = await file.read()

    # VÃ©rifier la taille (max 2MB)
    if len(contents) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Fichier trop volumineux (max 2MB)")

    try:
        # Ouvrir et traiter l'image
        img = Image.open(io.BytesIO(contents))

        # Convertir en RGB si nÃ©cessaire (RGBA, P modes)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')

        # Redimensionner Ã  max 200x200 en conservant les proportions
        img.thumbnail((200, 200), Image.LANCZOS)

        # Sauvegarder en mÃ©moire (pas sur le filesystem Vercel Ã©phÃ©mÃ¨re)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
        file_bytes = buf.getvalue()

        # GÃ©nÃ©rer un identifiant unique pour MongoDB
        file_id = uuid.uuid4().hex[:16]
        filename = f"profile_{participant_id}_{file_id}.jpg"

        # Stocker dans MongoDB (comme coach/upload-asset)
        file_doc = {
            "file_id": file_id,
            "filename": filename,
            "original_name": file.filename or "profile.jpg",
            "content_type": "image/jpeg",
            "asset_type": "profile_photo",
            "participant_id": participant_id,
            "data": Binary(file_bytes),
            "size": len(file_bytes),
            "created_at": datetime.utcnow()
        }
        await db.uploaded_files.insert_one(file_doc)

        # URL publique via le endpoint /api/files/ existant
        photo_url = f"/api/files/{file_id}/{filename}"

        # === MISE Ã JOUR BASE DE DONNÃES ===
        # 1. Mettre Ã  jour dans la collection 'users' (par participant_id OU email)
        update_result_users = await db.users.update_one(
            {"$or": [{"id": participant_id}, {"participant_id": participant_id}]},
            {"$set": {"photo_url": photo_url, "photoUrl": photo_url}},
            upsert=False
        )

        # 2. Mettre Ã  jour dans 'chat_participants' si existe
        update_result_participants = await db.chat_participants.update_one(
            {"id": participant_id},
            {"$set": {"photo_url": photo_url, "photoUrl": photo_url}},
            upsert=False
        )

        logger.info(f"[UPLOAD] â v75 Photo profil MongoDB: {filename} ({len(file_bytes)} bytes) | users={update_result_users.modified_count}, participants={update_result_participants.modified_count}")

        return {
            "success": True,
            "url": photo_url,
            "filename": filename,
            "participant_id": participant_id,
            "db_updated": {
                "users": update_result_users.modified_count,
                "participants": update_result_participants.modified_count
            }
        }

    except Exception as e:
        logger.error(f"[UPLOAD] â Erreur traitement image: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur traitement image: {str(e)}")

# === v17.5: UPLOAD ISOLÃ PAR COACH â MONGODB STORAGE (Vercel-compatible) ===
@api_router.post("/coach/upload-asset")
async def upload_coach_asset(
    request: Request,
    file: UploadFile = File(...),
    asset_type: str = Form("image")  # "image", "video", "logo", "audio"
):
    """
    Upload d'assets pour les coaches - Stockage MongoDB (compatible Vercel read-only FS)
    v17.5: Stocke les fichiers binaires dans MongoDB collection 'uploaded_files'
    """
    import io
    import uuid
    import base64

    coach_email = require_auth(request)

    # Validation du type MIME
    allowed_types = {
        "image": ["image/jpeg", "image/png", "image/webp", "image/gif"],
        "video": ["video/mp4", "video/webm", "video/quicktime"],
        "logo": ["image/jpeg", "image/png", "image/webp", "image/svg+xml"],
        "audio": ["audio/mpeg", "audio/mp3", "audio/wav", "audio/ogg", "audio/aac", "audio/mp4"]
    }

    if asset_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Type d'asset invalide: {asset_type}")

    if file.content_type not in allowed_types[asset_type]:
        raise HTTPException(status_code=400, detail=f"Type MIME non autorisÃ© pour {asset_type}: {file.content_type}")

    contents = await file.read()

    # Limite de taille: 15MB max pour MongoDB document storage
    max_sizes = {"image": 5*1024*1024, "video": 15*1024*1024, "logo": 2*1024*1024, "audio": 15*1024*1024}
    if len(contents) > max_sizes.get(asset_type, 5*1024*1024):
        raise HTTPException(status_code=400, detail=f"Fichier trop volumineux (max {max_sizes[asset_type]//1024//1024}MB)")

    try:
        # Extension basÃ©e sur le type MIME
        ext_map = {
            "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif",
            "video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov",
            "image/svg+xml": ".svg",
            "audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/wav": ".wav",
            "audio/ogg": ".ogg", "audio/aac": ".aac", "audio/mp4": ".m4a"
        }
        ext = ext_map.get(file.content_type, ".bin")

        file_id = uuid.uuid4().hex[:16]
        filename = f"{asset_type}_{file_id}{ext}"

        # Pour les images, optimiser en mÃ©moire
        file_bytes = contents
        if asset_type in ["image", "logo"] and file.content_type.startswith("image/") and file.content_type != "image/svg+xml":
            from PIL import Image
            img = Image.open(io.BytesIO(contents))
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            max_dim = 1920 if asset_type == "image" else 400
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, "JPEG" if ext == ".jpg" else "PNG", quality=85)
            file_bytes = buf.getvalue()

        # Stocker dans MongoDB
        from bson.binary import Binary
        file_doc = {
            "file_id": file_id,
            "filename": filename,
            "original_name": file.filename,
            "content_type": file.content_type,
            "asset_type": asset_type,
            "coach_email": coach_email,
            "data": Binary(file_bytes),
            "size": len(file_bytes),
            "created_at": datetime.utcnow()
        }

        await db.uploaded_files.insert_one(file_doc)

        # URL publique via API endpoint
        asset_url = f"/api/files/{file_id}/{filename}"

        logger.info(f"[COACH-UPLOAD] â Asset stockÃ© MongoDB pour {coach_email}: {filename} ({asset_type}, {len(file_bytes)} bytes)")

        return {
            "success": True,
            "url": asset_url,
            "filename": filename,
            "asset_type": asset_type,
            "coach_id": coach_email
        }

    except Exception as e:
        logger.error(f"[COACH-UPLOAD] â Erreur: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur upload: {str(e)}")

# === v58: Upload en chunks pour fichiers > 4MB (contourne limite Vercel 4.5MB body) ===
@api_router.post("/coach/upload-chunk")
async def upload_chunk(
    request: Request,
    file: UploadFile = File(...),
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    original_name: str = Form("audio.mp3"),
    content_type: str = Form("audio/mpeg"),
    asset_type: str = Form("audio")
):
    """Upload un chunk de fichier. Quand tous les chunks sont reÃ§us, assemble et stocke."""
    import uuid
    from bson.binary import Binary

    coach_email = require_auth(request)

    contents = await file.read()
    logger.info(f"[CHUNK-UPLOAD] Chunk {chunk_index + 1}/{total_chunks} pour {upload_id} ({len(contents)} bytes)")

    # Stocker le chunk
    await db.upload_chunks.update_one(
        {"upload_id": upload_id, "chunk_index": chunk_index},
        {"$set": {
            "upload_id": upload_id,
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "data": Binary(contents),
            "coach_email": coach_email,
            "original_name": original_name,
            "content_type": content_type,
            "asset_type": asset_type,
            "created_at": datetime.utcnow()
        }},
        upsert=True
    )

    # VÃ©rifier si tous les chunks sont arrivÃ©s
    received = await db.upload_chunks.count_documents({"upload_id": upload_id})
    if received < total_chunks:
        return {"success": True, "status": "chunk_received", "received": received, "total": total_chunks}

    # Tous les chunks reÃ§us â assembler le fichier
    chunks = await db.upload_chunks.find(
        {"upload_id": upload_id}
    ).sort("chunk_index", 1).to_list(length=total_chunks)

    file_bytes = b""
    for chunk in chunks:
        file_bytes += bytes(chunk["data"])

    # Nettoyer les chunks
    await db.upload_chunks.delete_many({"upload_id": upload_id})

    # Stocker le fichier assemblÃ© (mÃªme logique que upload-asset)
    ext_map = {
        "audio/mpeg": ".mp3", "audio/mp3": ".mp3", "audio/wav": ".wav",
        "audio/ogg": ".ogg", "audio/aac": ".aac", "audio/mp4": ".m4a",
        "image/jpeg": ".jpg", "image/png": ".png", "video/mp4": ".mp4"
    }
    ext = ext_map.get(content_type, ".bin")
    file_id = uuid.uuid4().hex[:16]
    filename = f"{asset_type}_{file_id}{ext}"

    file_doc = {
        "file_id": file_id,
        "filename": filename,
        "original_name": original_name,
        "content_type": content_type,
        "asset_type": asset_type,
        "coach_email": coach_email,
        "data": Binary(file_bytes),
        "size": len(file_bytes),
        "created_at": datetime.utcnow()
    }
    await db.uploaded_files.insert_one(file_doc)

    asset_url = f"/api/files/{file_id}/{filename}"
    logger.info(f"[CHUNK-UPLOAD] â Fichier assemblÃ©: {filename} ({len(file_bytes)} bytes, {total_chunks} chunks)")

    return {
        "success": True,
        "status": "complete",
        "url": asset_url,
        "filename": filename,
        "asset_type": asset_type,
        "size": len(file_bytes)
    }

# === v44: CRUD PISTES AUDIO AUTONOMES (indÃ©pendant des cours) ===
# Collection MongoDB: audio_tracks â chaque piste est un document indÃ©pendant

@api_router.get("/audio-tracks")
async def list_audio_tracks(request: Request):
    """Liste toutes les pistes audio d'un coach"""
    email = require_auth(request)
    tracks = await db.audio_tracks.find(
        {"coach_email": email},
        {"_id": 0}
    ).sort("order", 1).to_list(500)
    return {"tracks": tracks, "count": len(tracks)}

@api_router.post("/audio-tracks")
async def create_audio_track(request: Request):
    """CrÃ©e une nouvelle piste audio"""
    email = require_auth(request)
    body = await request.json()

    track_id = f"track-{uuid.uuid4().hex[:12]}"
    # Compter les pistes existantes pour l'ordre
    count = await db.audio_tracks.count_documents({"coach_email": email})

    track_doc = {
        "id": track_id,
        "coach_email": email,
        "url": body.get("url", ""),
        "title": body.get("title", "Sans titre"),
        "cover_url": body.get("cover_url"),
        "description": body.get("description", ""),
        "price": float(body.get("price", 0)),
        "preview_duration": int(body.get("preview_duration", 30)),
        "duration": body.get("duration"),
        "order": body.get("order", count),
        "visible": body.get("visible", True),
        "created_at": datetime.utcnow().isoformat()
    }

    await db.audio_tracks.insert_one(track_doc)
    del track_doc["_id"]  # Remove MongoDB _id before returning
    logger.info(f"[AUDIO] â Piste crÃ©Ã©e: {track_doc['title']} pour {email}")
    return {"success": True, "track": track_doc}

class ReorderRequest(BaseModel):
    """v48: SchÃ©ma Pydantic strict pour le reorder â empÃªche les erreurs de type"""
    model_config = ConfigDict(extra="ignore")
    track_ids: List[str] = Field(..., min_length=0, description="Liste ordonnÃ©e des IDs de pistes")

@api_router.put("/audio-tracks/reorder")
async def reorder_audio_tracks(request: Request):
    """v48: RÃ©ordonne les pistes audio â DOIT Ãªtre AVANT {track_id} pour Ã©viter conflit de route"""
    email = require_auth(request)
    try:
        body = await request.json()
        reorder_data = ReorderRequest(**body)
    except Exception as e:
        logger.error(f"[AUDIO-REORDER] â Validation error: {str(e)}")
        raise HTTPException(status_code=422, detail=f"Format invalide: {str(e)}")

    track_ids = reorder_data.track_ids
    updated = 0
    for i, tid in enumerate(track_ids):
        result = await db.audio_tracks.update_one(
            {"id": tid, "coach_email": email},
            {"$set": {"order": i}}
        )
        if result.modified_count > 0:
            updated += 1

    logger.info(f"[AUDIO-REORDER] â {email} â {updated}/{len(track_ids)} pistes rÃ©ordonnÃ©es")
    return {"success": True, "reordered": len(track_ids), "updated": updated}

@api_router.put("/audio-tracks/{track_id}")
async def update_audio_track(track_id: str, request: Request):
    """Met Ã  jour une piste audio (titre, prix, visible, etc.)"""
    email = require_auth(request)
    body = await request.json()

    existing = await db.audio_tracks.find_one({"id": track_id, "coach_email": email})
    if not existing:
        raise HTTPException(status_code=404, detail="Piste non trouvÃ©e")

    update_data = {k: v for k, v in body.items() if v is not None and k not in ("id", "coach_email", "_id")}
    if "price" in update_data:
        update_data["price"] = float(update_data["price"])

    await db.audio_tracks.update_one({"id": track_id}, {"$set": update_data})
    updated = await db.audio_tracks.find_one({"id": track_id}, {"_id": 0})
    logger.info(f"[AUDIO] âï¸ Piste modifiÃ©e: {track_id} â champs: {list(update_data.keys())}")
    return {"success": True, "track": updated}

@api_router.delete("/audio-tracks/{track_id}")
async def delete_audio_track(track_id: str, request: Request):
    """Supprime une piste audio"""
    email = require_auth(request)
    result = await db.audio_tracks.delete_one({"id": track_id, "coach_email": email})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Piste non trouvÃ©e")
    logger.info(f"[AUDIO] ðï¸ Piste supprimÃ©e: {track_id} par {email}")
    return {"success": True, "deleted": track_id}

# === v44: PISTES AUDIO PUBLIQUES (pour la vitrine) ===
@api_router.get("/public/audio-tracks/{coach_email}")
async def get_public_audio_tracks(coach_email: str):
    """Liste les pistes audio visibles d'un coach (pour la vitrine publique)"""
    tracks = await db.audio_tracks.find(
        {"coach_email": coach_email.lower().strip(), "visible": True},
        {"_id": 0, "coach_email": 0}
    ).sort("order", 1).to_list(100)
    return {"tracks": tracks, "count": len(tracks)}

# === v18.1: DIAGNOSTIC FICHIERS UPLOADÃS (doit Ãªtre AVANT la route dynamique) ===
@api_router.get("/files/check/{file_id}")
async def check_uploaded_file(file_id: str):
    """Diagnostic: vÃ©rifie si un fichier existe dans MongoDB sans le charger"""
    try:
        file_doc = await db.uploaded_files.find_one(
            {"file_id": file_id},
            {"file_id": 1, "filename": 1, "content_type": 1, "size": 1, "original_name": 1, "asset_type": 1, "created_at": 1, "coach_email": 1}
        )
        if not file_doc:
            return {"exists": False, "file_id": file_id}

        return {
            "exists": True,
            "file_id": file_doc.get("file_id"),
            "filename": file_doc.get("filename"),
            "original_name": file_doc.get("original_name"),
            "content_type": file_doc.get("content_type"),
            "size": file_doc.get("size"),
            "asset_type": file_doc.get("asset_type"),
            "created_at": str(file_doc.get("created_at", "")),
            "coach_email": file_doc.get("coach_email")
        }
    except Exception as e:
        return {"exists": False, "error": str(e)}

# === v18.3: FASTSTART MP4 â dÃ©place moov avant mdat pour streaming instantanÃ© ===
def mp4_faststart(data: bytes) -> bytes:
    """
    RÃ©organise un MP4 pour placer l'atome moov AVANT mdat (faststart).
    Permet au navigateur de commencer la lecture sans attendre le tÃ©lÃ©chargement complet.
    Retourne les donnÃ©es originales si dÃ©jÃ  faststart ou si le format n'est pas MP4.
    """
    import struct
    try:
        # Parse les atomes top-level
        atoms = []
        pos = 0
        while pos < len(data) - 8:
            size = struct.unpack('>I', data[pos:pos+4])[0]
            atom_type = data[pos+4:pos+8].decode('ascii', errors='replace')
            if size < 8:
                break
            if size == 1 and pos + 16 <= len(data):
                size = struct.unpack('>Q', data[pos+8:pos+16])[0]
            atoms.append({'type': atom_type, 'offset': pos, 'size': size})
            pos += size
            if pos > len(data):
                break

        # Trouver moov et mdat
        moov = next((a for a in atoms if a['type'] == 'moov'), None)
        mdat = next((a for a in atoms if a['type'] == 'mdat'), None)

        if not moov or not mdat:
            return data  # Pas un MP4 standard

        # DÃ©jÃ  faststart ? (moov avant mdat)
        if moov['offset'] < mdat['offset']:
            logger.info("[FASTSTART] â DÃ©jÃ  faststart")
            return data

        logger.info(f"[FASTSTART] ð RÃ©organisation: moov@{moov['offset']} â avant mdat@{mdat['offset']}")

        # Calculer le dÃ©calage: moov va Ãªtre insÃ©rÃ© avant mdat
        moov_data = bytearray(data[moov['offset']:moov['offset'] + moov['size']])
        moov_size = moov['size']

        # Ajuster les offsets stco et co64 dans moov
        # Les chunk offsets pointent dans mdat â ils doivent Ãªtre dÃ©calÃ©s de +moov_size
        def adjust_offsets(box_data, box_offset, parent_end):
            """Parcourt rÃ©cursivement moov pour ajuster stco/co64"""
            pos = box_offset + 8  # Skip size + type
            while pos < parent_end - 8:
                child_size = struct.unpack('>I', box_data[pos:pos+4])[0]
                child_type = box_data[pos+4:pos+8].decode('ascii', errors='replace')
                if child_size < 8 or pos + child_size > parent_end:
                    break

                if child_type == 'stco':
                    # stco: 4 bytes version/flags + 4 bytes count + 4 bytes per entry
                    entry_count = struct.unpack('>I', box_data[pos+12:pos+16])[0]
                    for i in range(entry_count):
                        off = pos + 16 + i * 4
                        if off + 4 <= parent_end:
                            old_val = struct.unpack('>I', box_data[off:off+4])[0]
                            struct.pack_into('>I', box_data, off, old_val + moov_size)

                elif child_type == 'co64':
                    entry_count = struct.unpack('>I', box_data[pos+12:pos+16])[0]
                    for i in range(entry_count):
                        off = pos + 16 + i * 8
                        if off + 8 <= parent_end:
                            old_val = struct.unpack('>Q', box_data[off:off+8])[0]
                            struct.pack_into('>Q', box_data, off, old_val + moov_size)

                elif child_type in ('trak', 'mdia', 'minf', 'stbl', 'edts', 'dinf'):
                    adjust_offsets(box_data, pos, pos + child_size)

                pos += child_size

        adjust_offsets(moov_data, 0, moov_size)

        # Reconstruire: [atoms avant mdat] + [moov ajustÃ©] + [mdat] + [atoms aprÃ¨s moov]
        result = bytearray()
        for a in atoms:
            if a['type'] == 'mdat':
                result.extend(moov_data)  # InsÃ©rer moov avant mdat
                result.extend(data[a['offset']:a['offset'] + a['size']])
            elif a['type'] == 'moov':
                pass  # Skip â dÃ©jÃ  insÃ©rÃ© avant mdat
            else:
                result.extend(data[a['offset']:a['offset'] + a['size']])

        logger.info(f"[FASTSTART] â RÃ©organisÃ©: {len(data)} â {len(result)} bytes")
        return bytes(result)

    except Exception as e:
        logger.warning(f"[FASTSTART] â ï¸ Erreur faststart, retour original: {e}")
        return data

# === V148: OPTIMIZED IMAGE ENDPOINT â sert des images compressÃ©es JPEG pour le hero ===
@api_router.get("/files/{file_id}/optimized")
async def serve_optimized_image(file_id: str, w: int = 1200, q: int = 80, fmt: str = "auto", request: Request = None):
    """
    V148+V157: Sert une version optimisÃ©e d'une image uploadÃ©e.
    ParamÃ¨tres: w=largeur max (dÃ©faut 1200px), q=qualitÃ© (dÃ©faut 80), fmt=format (auto/webp/jpeg).
    V157: Support WebP (~30% plus lÃ©ger que JPEG) avec dÃ©tection Accept header.
    """
    from fastapi.responses import Response
    import io

    try:
        file_doc = await db.uploaded_files.find_one({"file_id": file_id})
        if not file_doc:
            raise HTTPException(status_code=404, detail="Fichier non trouvÃ©")

        raw_data = file_doc.get("data")
        if raw_data is None:
            raise HTTPException(status_code=404, detail="DonnÃ©es manquantes")

        if hasattr(raw_data, 'read'):
            file_bytes = raw_data.read()
        elif isinstance(raw_data, bytes):
            file_bytes = raw_data
        else:
            file_bytes = bytes(raw_data)

        content_type = file_doc.get("content_type", "")

        # Seulement pour les images
        if not content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Ce endpoint est rÃ©servÃ© aux images")

        from PIL import Image

        img = Image.open(io.BytesIO(file_bytes))

        # Convertir RGBA â RGB si nÃ©cessaire (pour JPEG)
        if img.mode in ('RGBA', 'P', 'LA'):
            background = Image.new('RGB', img.size, (0, 0, 0))
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode in ('RGBA', 'LA'):
                background.paste(img, mask=img.split()[-1])
            img = background

        # Redimensionner si plus large que w
        if img.width > w:
            ratio = w / img.width
            new_h = int(img.height * ratio)
            img = img.resize((w, new_h), Image.LANCZOS)

        # V157: DÃ©terminer le format de sortie (WebP si supportÃ©, sinon JPEG)
        use_webp = False
        if fmt == "webp":
            use_webp = True
        elif fmt == "auto" and request:
            accept = request.headers.get("accept", "")
            if "image/webp" in accept:
                use_webp = True

        buf = io.BytesIO()
        if use_webp:
            img.save(buf, format='WEBP', quality=q, method=4)
            out_media = "image/webp"
            out_fmt = "webp"
        else:
            img.save(buf, format='JPEG', quality=q, optimize=True)
            out_media = "image/jpeg"
            out_fmt = "jpeg"
        optimized_bytes = buf.getvalue()

        logger.info(f"[V157-OPTIM] {file_id}: {len(file_bytes)} â {len(optimized_bytes)} bytes ({int(len(optimized_bytes)/1024)}KB, {w}px, q={q}, fmt={out_fmt})")

        return Response(
            content=optimized_bytes,
            media_type=out_media,
            headers={
                "Cache-Control": "public, max-age=31536000, immutable",
                "Content-Length": str(len(optimized_bytes)),
                "X-Original-Size": str(len(file_bytes)),
                "X-Optimized-Size": str(len(optimized_bytes)),
                "Vary": "Accept",
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[V157-OPTIM] Erreur: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur optimisation: {str(e)}")

# === v17.5: SERVING FICHIERS DEPUIS MONGODB ===
@api_router.get("/files/{file_id}/{filename}")
async def serve_uploaded_file(file_id: str, filename: str, request: Request = None):
    """
    Sert un fichier uploadÃ© depuis MongoDB.
    v18.3: Faststart MP4 automatique + StreamingResponse pour gros fichiers
    V148: Support Range requests pour streaming vidÃ©o instantanÃ©
    Cache-Control: 1 an (les fichiers sont immutables via leur ID unique)
    """
    from fastapi.responses import Response, StreamingResponse
    import io

    try:
        logger.info(f"[FILE-SERVE] RequÃªte fichier: file_id={file_id}, filename={filename}")

        file_doc = await db.uploaded_files.find_one({"file_id": file_id})

        if not file_doc:
            logger.warning(f"[FILE-SERVE] â Fichier non trouvÃ©: {file_id}")
            raise HTTPException(status_code=404, detail="Fichier non trouvÃ©")

        # Extraire les donnÃ©es binaires
        raw_data = file_doc.get("data")
        if raw_data is None:
            logger.error(f"[FILE-SERVE] â Champ 'data' manquant pour {file_id}")
            raise HTTPException(status_code=500, detail="DonnÃ©es fichier manquantes")

        # Convertir BSON Binary en bytes de maniÃ¨re sÃ»re
        if hasattr(raw_data, 'read'):
            file_bytes = raw_data.read()
        elif isinstance(raw_data, bytes):
            file_bytes = raw_data
        else:
            file_bytes = bytes(raw_data)

        content_type = file_doc.get("content_type", "application/octet-stream")

        # Sanitize filename pour header HTTP (latin-1 safe)
        raw_name = file_doc.get("original_name", filename)
        original_name = raw_name.encode('ascii', 'replace').decode('ascii').replace('?', '_')
        file_size = len(file_bytes)

        logger.info(f"[FILE-SERVE] â Servant {original_name}: {file_size} bytes, type={content_type}")

        # V151: Smart video serving â ALWAYS use 206 partial responses for videos
        # Vercel serverless has a 4.5MB response body limit. Large videos MUST be
        # served in chunks via Range requests. Even without Range header, we send
        # the first chunk as 206 to trigger the browser's range request mode.
        CHUNK_SIZE = 2 * 1024 * 1024  # 2MB per chunk â well under 4.5MB limit
        range_header = request.headers.get("range") if request else None

        if content_type.startswith("video/"):
            start = 0
            end = min(CHUNK_SIZE - 1, file_size - 1)

            if range_header:
                try:
                    range_spec = range_header.replace("bytes=", "").strip()
                    parts = range_spec.split("-")
                    start = int(parts[0]) if parts[0] else 0
                    end = int(parts[1]) if len(parts) > 1 and parts[1] else min(start + CHUNK_SIZE - 1, file_size - 1)
                    end = min(end, file_size - 1)
                except Exception as range_err:
                    logger.warning(f"[FILE-SERVE] â ï¸ Range parse error: {range_err}")
                    start = 0
                    end = min(CHUNK_SIZE - 1, file_size - 1)
            else:
                logger.info(f"[FILE-SERVE] ð¬ Video {file_size} bytes â no Range header, forcing 206 with first {CHUNK_SIZE} bytes")

            chunk = file_bytes[start:end + 1]
            logger.info(f"[FILE-SERVE] ð¡ Video range {start}-{end}/{file_size} ({len(chunk)} bytes)")
            return Response(
                content=chunk,
                status_code=206,
                media_type=content_type,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(len(chunk)),
                    "Cache-Control": "public, max-age=31536000, immutable",
                }
            )

        # Pour les fichiers non-vidÃ©o > 3MB, utiliser StreamingResponse
        if file_size > 3 * 1024 * 1024:
            return StreamingResponse(
                io.BytesIO(file_bytes),
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=31536000, immutable",
                    "Content-Disposition": f'inline; filename="{original_name}"',
                    "Content-Length": str(file_size),
                    "Accept-Ranges": "bytes"
                }
            )

        return Response(
            content=file_bytes,
            media_type=content_type,
            headers={
                "Cache-Control": "public, max-age=31536000, immutable",
                "Content-Disposition": f'inline; filename="{original_name}"',
                "Content-Length": str(file_size),
                "Accept-Ranges": "bytes"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FILE-SERVE] â Erreur servant {file_id}: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erreur lecture fichier: {type(e).__name__}: {str(e)}")

# === V153: Video chunk endpoints for CDN-cached parallel loading ===
# Problem: Vercel serverless reads ENTIRE MongoDB document (~10MB) per range request â ~40s for video
# Solution: Return individual 2MB chunks as 200 responses (reliably cached by Vercel edge CDN via s-maxage).
# Frontend fetches all chunks in parallel â first visitor ~5-8s, subsequent visitors <1s (edge cache).
CHUNK_SIZE_V153 = 2 * 1024 * 1024  # 2MB chunks

@api_router.get("/video-chunks/{file_id}/info")
async def video_chunks_info(file_id: str):
    """V153: Return video metadata for chunk-based parallel loading"""
    from fastapi.responses import JSONResponse
    try:
        file_doc = await db.uploaded_files.find_one({"file_id": file_id})
        if not file_doc:
            raise HTTPException(status_code=404, detail="File not found")
        raw_data = file_doc.get("data")
        if raw_data is None:
            raise HTTPException(status_code=500, detail="No data field")
        if hasattr(raw_data, 'read'):
            file_bytes = raw_data.read()
        elif isinstance(raw_data, bytes):
            file_bytes = raw_data
        else:
            file_bytes = bytes(raw_data)
        file_size = len(file_bytes)
        total_chunks = (file_size + CHUNK_SIZE_V153 - 1) // CHUNK_SIZE_V153
        content_type = file_doc.get("content_type", "video/mp4")
        logger.info(f"[V153] Video info: {file_id} = {file_size} bytes, {total_chunks} chunks")
        return JSONResponse(
            content={"file_size": file_size, "total_chunks": total_chunks, "chunk_size": CHUNK_SIZE_V153, "content_type": content_type},
            headers={"Cache-Control": "public, s-maxage=31536000, max-age=31536000, immutable"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[V153] Error getting video info {file_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/video-chunks/{file_id}/{chunk_idx}")
async def serve_video_chunk(file_id: str, chunk_idx: int):
    """V153: Serve individual 2MB video chunk with 200 status for reliable Vercel edge CDN caching"""
    from fastapi.responses import Response
    try:
        file_doc = await db.uploaded_files.find_one({"file_id": file_id})
        if not file_doc:
            raise HTTPException(status_code=404, detail="File not found")
        raw_data = file_doc.get("data")
        if raw_data is None:
            raise HTTPException(status_code=500, detail="No data field")
        if hasattr(raw_data, 'read'):
            file_bytes = raw_data.read()
        elif isinstance(raw_data, bytes):
            file_bytes = raw_data
        else:
            file_bytes = bytes(raw_data)
        file_size = len(file_bytes)
        start = chunk_idx * CHUNK_SIZE_V153
        if start >= file_size:
            raise HTTPException(status_code=404, detail=f"Chunk {chunk_idx} out of range")
        end = min(start + CHUNK_SIZE_V153, file_size)
        chunk = file_bytes[start:end]
        total_chunks = (file_size + CHUNK_SIZE_V153 - 1) // CHUNK_SIZE_V153
        content_type = file_doc.get("content_type", "video/mp4")
        logger.info(f"[V153] Chunk {chunk_idx}/{total_chunks} of {file_id}: {len(chunk)} bytes")
        return Response(
            content=chunk,
            status_code=200,
            media_type=content_type,
            headers={
                "Cache-Control": "public, s-maxage=31536000, max-age=31536000, immutable",
                "Content-Length": str(len(chunk)),
                "X-Chunk-Index": str(chunk_idx),
                "X-Total-Chunks": str(total_chunks),
                "X-File-Size": str(file_size),
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[V153] Error serving chunk {chunk_idx} of {file_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# === v9.3.1: VÃRIFICATION PARTENAIRE (CÃTÃ SERVEUR) ===
@api_router.get("/check-partner/{email}")
async def check_if_partner(email: str):
    """
    VÃ©rifie si un utilisateur est un partenaire inscrit (a un profil coach)
    UtilisÃ© par le frontend pour afficher le bon bouton dans le chat
    v9.5.6: Super Admin a toujours accÃ¨s
    """
    email = email.lower().strip()
    
    # v9.5.6: Super Admin a toujours accÃ¨s illimitÃ©
    if is_super_admin(email):
        return {
            "is_partner": True,
            "email": email,
            "name": "Super Admin",
            "has_credits": True,
            "credits": -1,
            "unlimited": True,
            "is_super_admin": True
        }
    
    # VÃ©rifier si l'email a un profil coach
    coach = await db.coaches.find_one({"email": email}, {"_id": 0, "email": 1, "name": 1, "credits": 1})
    
    if coach:
        return {
            "is_partner": True,
            "email": coach.get("email"),
            "name": coach.get("name"),
            "has_credits": (coach.get("credits", 0) or 0) > 0
        }
    
    return {"is_partner": False, "email": email}


# === V90: ENDPOINT CONVERSION SEANCE -> CREDIT SERVICE ===
@api_router.post("/session-to-credit")
async def convert_session_to_credit(request: Request):
    """
    V90: Convertit 1 seance payee (15 CHF) en 1 credit service.
    Le partenaire echange ses seances achetees contre des credits utilisables pour les services.
    """
    try:
        body = await request.json()
        email = body.get("email", "").lower().strip()
        
        if not email:
            return JSONResponse(status_code=400, content={"error": "Email requis"})
        
        # Super Admin bypass
        if is_super_admin(email):
            return {"success": True, "message": "Super Admin - credits illimites", "credits": -1}
        
        # Verifier que le coach/partenaire existe
        coach = await db.coaches.find_one({"email": email})
        if not coach:
            return JSONResponse(status_code=404, content={"error": "Partenaire non trouve"})
        
        # Verifier qu il a au moins 1 seance disponible
        sessions_available = coach.get("sessions_available", 0)
        if sessions_available < 1:
            return JSONResponse(status_code=400, content={
                "error": "Aucune seance disponible a convertir",
                "sessions_available": sessions_available
            })
        
        # Convertir: -1 seance, +1 credit
        result = await db.coaches.update_one(
            {"email": email},
            {
                "$inc": {"sessions_available": -1, "credits": 1},
                "$set": {"role": "partner", "updated_at": datetime.utcnow().isoformat()}
            }
        )
        
        updated = await db.coaches.find_one({"email": email})
        logger.info(f"[V90] Session->Credit conversion for {email}: sessions={updated.get('sessions_available', 0)}, credits={updated.get('credits', 0)}")
        
        return {
            "success": True,
            "sessions_remaining": updated.get("sessions_available", 0),
            "credits": updated.get("credits", 0),
            "message": "1 seance convertie en 1 credit service"
        }
    except Exception as e:
        logger.error(f"[V90] Error session-to-credit: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

# === v9.5.8: ENDPOINT DÃDUCTION CRÃDITS ===
@api_router.post("/credits/deduct")
async def api_deduct_credit(request: Request):
    """
    DÃ©duit 1 crÃ©dit du compte partenaire.
    UtilisÃ© par le frontend pour les actions consommant des crÃ©dits.
    Super Admin (afroboost.bassi@gmail.com) ne consomme jamais de crÃ©dits.
    """
    # V134: Auth obligatoire pour dÃ©duire des crÃ©dits
    user_email = require_auth(request)

    try:
        body = await request.json()
        action = body.get("action", "action")
    except Exception as e:
        logger.warning(f"[V133] Erreur parsing body action: {e}")
        action = "action"

    result = await deduct_credit(user_email, action)

    if not result.get("success"):
        raise HTTPException(status_code=402, detail=result.get("error", "CrÃ©dits insuffisants"))

    return result

@api_router.get("/credits/check")
async def api_check_credits(request: Request):
    """
    VÃ©rifie le solde de crÃ©dits d'un partenaire.
    V134: Auth obligatoire.
    """
    user_email = require_auth(request)

    return await check_credits(user_email)

@api_router.get("/users/{participant_id}/profile")
async def get_user_profile(participant_id: str):
    """
    RÃ©cupÃ¨re le profil utilisateur depuis la DB (PAS localStorage).
    Cherche dans 'users' puis 'chat_participants'.
    """
    # 1. Chercher dans la collection 'users'
    user = await db.users.find_one(
        {"$or": [{"id": participant_id}, {"participant_id": participant_id}]},
        {"_id": 0}
    )
    
    if user:
        photo_url = user.get("photo_url") or user.get("photoUrl")
        return {
            "success": True,
            "source": "users",
            "participant_id": participant_id,
            "name": user.get("name") or user.get("username"),
            "email": user.get("email"),
            "photo_url": photo_url
        }
    
    # 2. Fallback: chercher dans 'chat_participants'
    participant = await db.chat_participants.find_one(
        {"id": participant_id},
        {"_id": 0}
    )
    
    if participant:
        photo_url = participant.get("photo_url") or participant.get("photoUrl")
        return {
            "success": True,
            "source": "chat_participants",
            "participant_id": participant_id,
            "name": participant.get("name") or participant.get("username"),
            "email": participant.get("email"),
            "photo_url": photo_url
        }
    
    # 3. Aucun profil trouvÃ©
    return {
        "success": False,
        "participant_id": participant_id,
        "photo_url": None,
        "message": "Profil non trouvÃ©"
    }

# === COACH NOTIFICATIONS ===

class CoachNotificationPayload(BaseModel):
    """Payload for coach notification"""
    clientName: str
    clientEmail: str
    clientWhatsapp: str
    offerName: str
    courseName: str
    sessionDate: str
    amount: float
    reservationCode: str

@api_router.post("/notify-coach")
async def notify_coach(payload: CoachNotificationPayload):
    """
    Endpoint to trigger coach notification.
    Returns the notification config so frontend can send via EmailJS/WhatsApp.
    """
    try:
        # Get payment links config which contains coach notification settings
        payment_links = await db.payment_links.find_one({"id": "payment_links"}, {"_id": 0})
        if not payment_links:
            return {"success": False, "message": "Configuration non trouvÃ©e"}
        
        coach_email = payment_links.get("coachNotificationEmail", "")
        coach_phone = payment_links.get("coachNotificationPhone", "")
        
        if not coach_email and not coach_phone:
            return {"success": False, "message": "Aucune adresse de notification configurÃ©e"}
        
        # Format notification message
        notification_message = f"""ð NOUVELLE RÃSERVATION !

ð¤ Client: {payload.clientName}
ð§ Email: {payload.clientEmail}
ð± WhatsApp: {payload.clientWhatsapp}

ð¯ Offre: {payload.offerName}
ð Cours: {payload.courseName}
ð Date: {payload.sessionDate}
ð° Montant: {payload.amount} CHF

ð Code: {payload.reservationCode}

---
Notification automatique Afroboost"""

        return {
            "success": True,
            "coachEmail": coach_email,
            "coachPhone": coach_phone,
            "message": notification_message,
            "subject": f"ð Nouvelle rÃ©servation - {payload.clientName}"
        }
    except Exception as e:
        logger.error(f"Error in notify-coach: {e}")
        return {"success": False, "message": str(e)}

# === v9.2.0: Routes discount-codes dÃ©placÃ©es vers routes/promo_routes.py ===
# Les routes suivantes ont Ã©tÃ© extraites pour modularisation :
# - GET /discount-codes
# - POST /discount-codes
# - PUT /discount-codes/{code_id}
# - DELETE /discount-codes/{code_id}
# - POST /discount-codes/validate
# - POST /discount-codes/{code_id}/use

# === SANITIZE DATA (Nettoyage des donnÃ©es fantÃ´mes) ===

@api_router.post("/sanitize-data")
async def sanitize_data():
    """
    Nettoie automatiquement les donnÃ©es fantÃ´mes:
    - Retire des codes promo les IDs d'offres/cours qui n'existent plus
    - Retire des codes promo les emails de bÃ©nÃ©ficiaires qui n'existent plus
    """
    # 1. RÃ©cupÃ©rer tous les IDs valides
    valid_offer_ids = set()
    valid_course_ids = set()
    valid_user_emails = set()
    
    offers = await db.offers.find({}, {"id": 1, "_id": 0}).to_list(1000)
    for o in offers:
        if o.get("id"):
            valid_offer_ids.add(o["id"])
    
    courses = await db.courses.find({}, {"id": 1, "_id": 0}).to_list(1000)
    for c in courses:
        if c.get("id"):
            valid_course_ids.add(c["id"])
    
    users = await db.users.find({}, {"email": 1, "_id": 0}).to_list(1000)
    for u in users:
        if u.get("email"):
            valid_user_emails.add(u["email"])
    
    all_valid_ids = valid_offer_ids | valid_course_ids
    
    # Nettoyer les codes promo
    discount_codes = await db.discount_codes.find({}, {"_id": 0}).to_list(1000)
    cleaned_count = 0
    
    for code in discount_codes:
        updates = {}
        if code.get("courses"):
            valid = [c for c in code["courses"] if c in all_valid_ids]
            if len(valid) != len(code["courses"]):
                updates["courses"] = valid
        if code.get("assignedEmail") and code["assignedEmail"] not in valid_user_emails:
            updates["assignedEmail"] = None
        if updates:
            await db.discount_codes.update_one({"id": code["id"]}, {"$set": updates})
            cleaned_count += 1
    
    return {"success": True, "codes_cleaned": cleaned_count}

@api_router.post("/campaigns")
async def create_campaign(campaign: CampaignCreate, request: Request = None):
    # V134: Authentification obligatoire via require_auth (JWT strict si activÃ©)
    coach_email = ""
    if request:
        coach_email = require_auth(request)

    # v13: VÃ©rification crÃ©dits AVANT crÃ©ation (0 crÃ©dits = pas d'envoi)
    if coach_email and not is_super_admin(coach_email):
        campaign_cost = await get_service_price("campaign")
        target_count = max(1, len(campaign.targetIds or []))
        total_cost = campaign_cost * target_count
        credit_check = await check_credits(coach_email, total_cost)
        if not credit_check.get("has_credits"):
            raise HTTPException(
                status_code=402,
                detail=f"CrÃ©dits insuffisants: {credit_check.get('credits', 0)}/{total_cost} requis. Rechargez votre pack."
            )

    campaign_data = Campaign(
        name=campaign.name,
        message=campaign.message,
        mediaUrl=campaign.mediaUrl,
        mediaFormat=campaign.mediaFormat,
        mediaType=campaign.mediaType,
        targetType=campaign.targetType,
        selectedContacts=campaign.selectedContacts,
        channels=campaign.channels,
        targetGroupId=campaign.targetGroupId,
        targetIds=campaign.targetIds or [],
        targetConversationId=campaign.targetConversationId,
        targetConversationName=campaign.targetConversationName,
        scheduledAt=campaign.scheduledAt,
        status="scheduled" if campaign.scheduledAt else "draft",
        ctaType=campaign.ctaType,
        ctaText=campaign.ctaText,
        ctaLink=campaign.ctaLink,
        systemPrompt=campaign.systemPrompt,
        descriptionPrompt=campaign.descriptionPrompt,
        coach_id=coach_email or None
    ).model_dump()
    await db.campaigns.insert_one(campaign_data)
    campaign_data.pop("_id", None)
    return campaign_data


@api_router.put("/campaigns/{campaign_id}")
async def update_campaign(campaign_id: str, request: Request):
    """
    Met Ã  jour une campagne existante (nom, message, horaire, canaux, etc.)
    Seules les campagnes draft/scheduled peuvent Ãªtre modifiÃ©es.
    V134: VÃ©rifie que l'utilisateur JWT est bien le crÃ©ateur de la campagne.
    """
    # V134: Auth obligatoire
    caller_email = require_auth(request)
    body = await request.json()

    existing = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # V134: VÃ©rification propriÃ©taire â seul le crÃ©ateur ou un super admin peut modifier
    campaign_owner = (existing.get("coach_id") or "").lower().strip()
    if campaign_owner and caller_email != campaign_owner and not is_super_admin(caller_email):
        raise HTTPException(status_code=403, detail="Vous ne pouvez modifier que vos propres campagnes")

    # EmpÃªcher la modification d'une campagne en cours d'envoi uniquement
    if existing.get("status") == "sending":
        raise HTTPException(status_code=400, detail="Cannot edit a campaign while it is being sent")

    # Champs modifiables
    allowed_fields = [
        "name", "message", "mediaUrl", "mediaFormat", "mediaType",
        "targetType", "selectedContacts", "channels", "targetGroupId",
        "targetIds", "targetConversationId", "targetConversationName",
        "scheduledAt", "ctaType", "ctaText", "ctaLink",
        "systemPrompt", "descriptionPrompt"
    ]

    update_data = {}
    for field in allowed_fields:
        if field in body:
            update_data[field] = body[field]

    # Mettre Ã  jour le statut en fonction de scheduledAt
    if "scheduledAt" in update_data:
        if update_data["scheduledAt"]:
            update_data["status"] = "scheduled"
            # Nettoyer les anciens rÃ©sultats pour permettre un relancement propre
            update_data["results"] = []
            update_data["launchedAt"] = None
        else:
            update_data["status"] = "draft"

    update_data["updatedAt"] = datetime.now(timezone.utc).isoformat()

    await db.campaigns.update_one(
        {"id": campaign_id},
        {"$set": update_data}
    )

    updated = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    logger.info(f"[CAMPAIGN-UPDATE] âï¸ Campagne '{updated.get('name')}' modifiÃ©e (champs: {list(update_data.keys())})")
    return updated


# ââ HELPER OMNICANALITÃ : Ã©crire les messages campagne dans chat_messages ââ
async def _save_campaign_chat_message(
    contact_id: str,
    content: str,
    media_url: str = None,
    channel: str = "email",
    campaign_id: str = None,
    campaign_name: str = None,
    cta_type: str = None,
    cta_text: str = None,
    cta_link: str = None
):
    """
    Ãcrit le message de campagne dans la collection chat_messages
    pour qu'il apparaisse dans l'UI client (omnicanalitÃ©).
    CrÃ©e la session si elle n'existe pas encore pour ce contact.
    Inclut les mÃ©dias et boutons CTA pour l'affichage dans le chat.
    Fallback silencieux : ne lÃ¨ve jamais d'exception bloquante.
    """
    # Chercher ou crÃ©er la session chat du contact
    session = await db.chat_sessions.find_one(
        {"participant_ids": contact_id},
        {"_id": 0, "id": 1}
    )
    if session:
        session_id = session["id"]
    else:
        session_id = str(uuid.uuid4())
        await db.chat_sessions.insert_one({
            "id": session_id,
            "mode": "user",
            "participant_ids": [contact_id],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        })
        logger.info(f"[CAMPAIGN-CHAT] Session crÃ©Ã©e pour contact {contact_id}: {session_id}")

    msg_id = str(uuid.uuid4())
    msg_timestamp = datetime.now(timezone.utc).isoformat()

    msg_doc = {
        "id": msg_id,
        "session_id": session_id,
        "content": content,
        "media_url": media_url or None,
        "sender_type": "coach",
        "sender_name": "Coach Bassi",
        "sender_id": f"coach-campaign-{channel}",
        "channel": channel,
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "timestamp": msg_timestamp,
        "created_at": msg_timestamp
    }
    # Ajouter les champs CTA s'ils existent
    if cta_type:
        msg_doc["cta_type"] = cta_type
    if cta_text:
        msg_doc["cta_text"] = cta_text
    if cta_link:
        msg_doc["cta_link"] = cta_link

    await db.chat_messages.insert_one(msg_doc)

    # Mettre Ã  jour le timestamp de la session
    await db.chat_sessions.update_one(
        {"id": session_id},
        {"$set": {"last_message_at": msg_timestamp, "updated_at": msg_timestamp}}
    )
    logger.info(f"[CAMPAIGN-CHAT] Message {channel} enregistrÃ© dans chat_messages pour {contact_id}")


def substitute_campaign_variables(message: str, contact: dict) -> str:
    """
    Remplace les variables {prÃ©nom}, {nom}, {email}, {prenom}, {name} dans le message.
    Insensible Ã  la casse et aux accents.
    """
    if not message or not contact:
        return message

    name = contact.get("name", "")
    first_name = name.split()[0] if name else ""
    email = contact.get("email", "")
    phone = contact.get("whatsapp", "") or contact.get("phone", "")

    # Remplacements (insensible Ã  la casse)
    import re
    replacements = {
        r'\{prÃ©nom\}': first_name,
        r'\{prenom\}': first_name,
        r'\{name\}': name,
        r'\{nom\}': name,
        r'\{email\}': email,
        r'\{phone\}': phone,
        r'\{tel\}': phone,
        # Patterns courants avec contenu entre accolades (ex: {pascal}, {jean})
        # Si c'est un mot simple entre accolades qui ressemble Ã  un prÃ©nom, remplacer aussi
    }

    result = message
    for pattern, value in replacements.items():
        result = re.sub(pattern, value, result, flags=re.IGNORECASE)

    return result


def format_phone_e164(phone: str, default_country: str = "+41") -> str:
    """
    V112: Convertit un numÃ©ro de tÃ©lÃ©phone au format E.164 pour Twilio.
    DÃ©faut: Suisse (+41) au lieu de France (+33).
    Ex: 0765203363 â +41765203363
    Ex: +41765203363 â +41765203363
    """
    if not phone:
        return ""
    phone = phone.strip().replace(" ", "").replace("-", "").replace(".", "")
    if phone.startswith("+"):
        return phone
    if phone.startswith("00"):
        return "+" + phone[2:]
    if phone.startswith("0"):
        return default_country + phone[1:]
    return default_country + phone


@api_router.post("/campaigns/{campaign_id}/launch")
async def launch_campaign(campaign_id: str, request: Request = None):
    """
    Lance une campagne immÃ©diatement.
    - Internal: Envoi dans les conversations chat (groupes/utilisateurs)
    - WhatsApp: Envoi DIRECT via Twilio
    - Email: Envoi DIRECT via Resend
    - Instagram: Non supportÃ© (manuel)

    V134: VÃ©rifie que le caller est le propriÃ©taire de la campagne.
    Chaque canal est indÃ©pendant: l'Ã©chec d'un envoi ne bloque pas les suivants.
    """
    # V134: Auth obligatoire pour lancer
    caller_email = ""
    if request:
        caller_email = require_auth(request)

    campaign = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # V134: VÃ©rification propriÃ©taire â seul le crÃ©ateur ou un super admin peut lancer
    campaign_owner = (campaign.get("coach_id") or "").lower().strip()
    if caller_email and campaign_owner and caller_email != campaign_owner and not is_super_admin(caller_email):
        raise HTTPException(status_code=403, detail="Vous ne pouvez lancer que vos propres campagnes")

    # v11: VÃ©rification et dÃ©duction de crÃ©dits (coÃ»t Ã nombre de contacts)
    coach_email = campaign.get("coach_id", "")
    if coach_email and not is_super_admin(coach_email):
        campaign_cost = await get_service_price("campaign")
        target_count = max(1, len(campaign.get("targetIds", [])))
        total_cost = campaign_cost * target_count
        credit_check = await check_credits(coach_email, total_cost)
        if not credit_check.get("has_credits"):
            raise HTTPException(
                status_code=402,
                detail=f"CrÃ©dits insuffisants: {credit_check.get('credits', 0)}/{total_cost} requis ({target_count} contact(s) Ã {campaign_cost} crÃ©dit(s))"
            )
        deduct_result = await deduct_credit(coach_email, f"campagne {campaign.get('name', '')}", total_cost)
        if not deduct_result.get("success"):
            raise HTTPException(status_code=402, detail=deduct_result.get("error", "Erreur dÃ©duction crÃ©dits"))
        logger.info(f"[CAMPAIGN-LAUNCH] ð° {total_cost} crÃ©dits dÃ©duits pour {coach_email} ({target_count} contacts)")

    # V112: Marquer immÃ©diatement "sending" pour le suivi temps rÃ©el cÃ´tÃ© frontend
    await db.campaigns.update_one(
        {"id": campaign_id},
        {"$set": {"status": "sending", "updatedAt": datetime.now(timezone.utc).isoformat()}}
    )
    logger.info(f"[CAMPAIGN-LAUNCH] ð Statut 'sending' appliquÃ© pour {campaign_id}")

    # Prepare results and tracking
    results = []
    channels = campaign.get("channels", {})
    message_content = campaign.get("message", "")
    media_url = campaign.get("mediaUrl", "")
    campaign_name = campaign.get("name", "Campagne")
    target_ids = campaign.get("targetIds", [])
    cta_type = campaign.get("ctaType", "")
    cta_text = campaign.get("ctaText", "")
    cta_link = campaign.get("ctaLink", "")

    # V118: DÃ©terminer le moteur WhatsApp â Meta Cloud API > Twilio production > Twilio sandbox
    sender_type = campaign.get("senderType", "business")
    business_from_number, wa_mode = await _get_whatsapp_sender()
    if sender_type == "custom" and campaign.get("customFromNumber"):
        business_from_number = campaign.get("customFromNumber")
        wa_mode = "twilio_custom"
    logger.info(f"[CAMPAIGN-LAUNCH-V118] ð¤ Mode {wa_mode}: envoi depuis {business_from_number}")
    
    success_count = 0
    fail_count = 0
    
    logger.info(f"[CAMPAIGN-LAUNCH] ð Lancement campagne '{campaign_name}' - targetIds: {len(target_ids)}, channels: {channels}")
    
    # ==================== ENVOI INTERNE (Chat) ====================
    # Filtrer les targetIds vides/null
    valid_target_ids = [tid for tid in target_ids if tid and tid.strip()]
    if channels.get("internal") and valid_target_ids:
        for target_id in valid_target_ids:
            internal_result = {
                "targetId": target_id,
                "channel": "internal",
                "status": "pending",
                "sentAt": None
            }

            try:
                # === DÃTECTION GROUPE OU UTILISATEUR ===
                # Chercher d'abord si le targetId est une session de groupe
                group_session = await db.chat_sessions.find_one(
                    {"id": target_id, "$or": [
                        {"title": {"$exists": True, "$ne": ""}},
                        {"mode": {"$in": ["community", "vip", "promo", "group"]}}
                    ]},
                    {"_id": 0, "id": 1, "mode": 1, "title": 1, "participant_ids": 1}
                )

                is_group = group_session is not None

                if is_group:
                    # === ENVOI GROUPE : message dans la session de groupe directement ===
                    session_id = group_session.get("id")
                    group_name = group_session.get("title", "Groupe")
                    logger.info(f"[CAMPAIGN-LAUNCH] ð¥ Groupe dÃ©tectÃ©: {group_name} ({session_id})")
                    contact_doc = {"name": group_name, "email": ""}
                else:
                    # === ENVOI INDIVIDUEL : rÃ©soudre l'utilisateur ===
                    contact_doc = await db.users.find_one({"id": target_id}, {"_id": 0, "email": 1, "name": 1})
                    contact_email = contact_doc.get("email", "") if contact_doc else ""
                    contact_name_internal = contact_doc.get("name", "") if contact_doc else ""

                    # StratÃ©gie de recherche: email (fiable) > participant_ids > id direct
                    session = None
                    if contact_email:
                        session = await db.chat_sessions.find_one(
                            {"participantEmail": contact_email},
                            {"_id": 0, "id": 1, "mode": 1, "title": 1, "participant_ids": 1}
                        )
                        if session:
                            logger.info(f"[CAMPAIGN-LAUNCH] ð Session trouvÃ©e par email {contact_email}: {session.get('id')}")

                    if not session:
                        session = await db.chat_sessions.find_one(
                            {"$or": [{"id": target_id}, {"participant_ids": target_id}]},
                            {"_id": 0, "id": 1, "mode": 1, "title": 1}
                        )

                    if session:
                        session_id = session.get("id")
                    else:
                        # CrÃ©er une session pour cet utilisateur s'il n'en a pas
                        session_id = str(uuid.uuid4())
                        await db.chat_sessions.insert_one({
                            "id": session_id,
                            "mode": "user",
                            "participant_ids": [target_id],
                            "participantEmail": contact_email,
                            "participantName": contact_name_internal,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        })
                        logger.info(f"[CAMPAIGN-LAUNCH] ð Session crÃ©Ã©e pour {target_id} ({contact_email}): {session_id}")
                
                # Substituer les variables {prÃ©nom} etc. avec les infos du contact
                personalized_message = substitute_campaign_variables(
                    message_content,
                    contact_doc or {"name": "", "email": contact_email}
                )

                # InsÃ©rer le message dans la conversation
                msg_id = str(uuid.uuid4())
                msg_timestamp = datetime.now(timezone.utc).isoformat()

                internal_msg_doc = {
                    "id": msg_id,
                    "session_id": session_id,
                    "content": personalized_message,
                    "media_url": media_url or None,
                    "sender_type": "coach",
                    "sender_name": "Coach Bassi",
                    "sender_id": "coach-campaign",
                    "is_group": is_group,
                    "timestamp": msg_timestamp,
                    "created_at": msg_timestamp
                }
                # Ajouter CTA si prÃ©sent
                if cta_type:
                    internal_msg_doc["cta_type"] = cta_type
                if cta_text:
                    internal_msg_doc["cta_text"] = cta_text
                if cta_link:
                    internal_msg_doc["cta_link"] = cta_link

                await db.chat_messages.insert_one(internal_msg_doc)
                
                # Mettre Ã  jour la session
                await db.chat_sessions.update_one(
                    {"id": session_id},
                    {"$set": {"last_message_at": msg_timestamp, "updated_at": msg_timestamp}}
                )
                
                internal_result["status"] = "sent"
                internal_result["sentAt"] = msg_timestamp
                internal_result["messageId"] = msg_id
                internal_result["sessionId"] = session_id
                success_count += 1
                logger.info(f"[CAMPAIGN-LAUNCH] â Message interne envoyÃ© Ã  {target_id}")
                
            except Exception as e:
                internal_result["status"] = "failed"
                internal_result["error"] = str(e)
                fail_count += 1
                logger.error(f"[CAMPAIGN-LAUNCH] â Erreur envoi interne Ã  {target_id}: {str(e)}")
            
            results.append(internal_result)
    
    # ==================== ENVOI WHATSAPP/EMAIL (via contacts CRM) ====================
    # RÃ©soudre les contacts pour email/WhatsApp
    # Les targetIds peuvent Ãªtre des IDs utilisateur OU des IDs de conversation/session
    # On essaie d'abord par ID utilisateur, puis par email via chat_sessions
    contacts = []
    if channels.get("whatsapp") or channels.get("email"):
        # V159-FIX: Si des targetIds spÃ©cifiques sont fournis, les utiliser MÃME si targetType=="all"
        # Cela Ã©vite d'envoyer Ã  tous les contacts quand l'utilisateur a sÃ©lectionnÃ© des destinataires prÃ©cis
        if campaign.get("targetType") == "all" and not valid_target_ids and not campaign.get("selectedContacts"):
            contacts = await db.users.find({}, {"_id": 0}).to_list(1000)
        else:
            contact_ids = valid_target_ids if valid_target_ids else campaign.get("selectedContacts", [])
            if contact_ids:
                # 1) Essayer de trouver directement par ID utilisateur
                contacts = await db.users.find({"id": {"$in": contact_ids}}, {"_id": 0}).to_list(1000)

                # 2) Si rien trouvÃ©, les IDs sont peut-Ãªtre des conversation/session IDs
                #    â rÃ©soudre via participantEmail des chat_sessions
                if not contacts:
                    for cid in contact_ids:
                        # Chercher le user par ID direct
                        user_doc = await db.users.find_one({"id": cid}, {"_id": 0})
                        if user_doc:
                            contacts.append(user_doc)
                            continue
                        # Chercher la session chat pour trouver l'email du participant
                        session_doc = await db.chat_sessions.find_one(
                            {"$or": [{"id": cid}, {"participant_ids": cid}]},
                            {"_id": 0, "participantEmail": 1, "participantName": 1}
                        )
                        if session_doc and session_doc.get("participantEmail"):
                            pemail = session_doc["participantEmail"]
                            user_by_email = await db.users.find_one({"email": pemail}, {"_id": 0})
                            if user_by_email:
                                contacts.append(user_by_email)
                            else:
                                # CrÃ©er un contact virtuel avec les infos de la session
                                contacts.append({
                                    "id": cid,
                                    "name": session_doc.get("participantName", ""),
                                    "email": pemail,
                                    "whatsapp": ""
                                })

                logger.info(f"[CAMPAIGN-LAUNCH] ð§ {len(contacts)} contacts rÃ©solus pour email/WhatsApp")
    
    for contact in contacts:
        contact_id = contact.get("id", "")
        contact_name = contact.get("name", "")
        contact_email = contact.get("email", "")
        # v107: RÃ©solution robuste du tÃ©lÃ©phone â essayer plusieurs champs
        contact_phone = (
            contact.get("whatsapp", "") or
            contact.get("phone", "") or
            contact.get("telephone", "") or
            contact.get("userWhatsapp", "") or
            ""
        ).strip()

        # Substituer les variables pour chaque contact
        personalized_msg = substitute_campaign_variables(message_content, contact)

        # ==================== ENVOI WHATSAPP (INDÃPENDANT) ====================
        if channels.get("whatsapp") and not contact_phone:
            # v107: Contact sans numÃ©ro â enregistrer l'Ã©chec explicitement
            results.append({
                "contactId": contact_id,
                "contactName": contact_name,
                "contactEmail": contact_email,
                "contactPhone": "",
                "channel": "whatsapp",
                "status": "failed",
                "error": f"Aucun numÃ©ro de tÃ©lÃ©phone trouvÃ© pour {contact_name or contact_email}",
                "sentAt": None
            })
            fail_count += 1
            logger.warning(f"[CAMPAIGN-LAUNCH] â ï¸ WhatsApp impossible: pas de tÃ©lÃ©phone pour {contact_name} ({contact_id})")
        if channels.get("whatsapp") and contact_phone:
            whatsapp_result = {
                "contactId": contact_id,
                "contactName": contact_name,
                "contactEmail": contact_email,
                "contactPhone": contact_phone,
                "channel": "whatsapp",
                "status": "pending",
                "sentAt": None,
                "deliveredAt": None,  # v11: tracking
                "readAt": None        # v11: tracking
            }
            
            try:
                # V118: Router vers Meta Cloud API ou Twilio selon le mode dÃ©tectÃ©
                phone_e164 = format_phone_e164(contact_phone)
                if wa_mode == "meta":
                    wa_response = await send_whatsapp_meta(
                        to_phone=phone_e164,
                        message=personalized_msg,
                        media_url=media_url if media_url else None,
                        campaign_id=campaign_id,
                        campaign_name=campaign_name
                    )
                else:
                    wa_response = await send_whatsapp_direct(
                        to_phone=phone_e164,
                        message=personalized_msg,
                        media_url=media_url if media_url else None,
                        campaign_id=campaign_id,
                        campaign_name=campaign_name,
                        from_number_override=business_from_number
                    )

                if wa_response.get("status") == "success":
                    whatsapp_result["status"] = "sent"
                    whatsapp_result["sentAt"] = datetime.now(timezone.utc).isoformat()
                    whatsapp_result["sid"] = wa_response.get("sid")
                    success_count += 1
                    logger.info(f"[CAMPAIGN-LAUNCH] â WhatsApp envoyÃ© Ã  {contact_name} ({contact_phone})")
                    # OmnicanalitÃ© : Ã©crire le message dans chat_messages pour l'UI client
                    try:
                        await _save_campaign_chat_message(
                            contact_id=contact_id,
                            content=personalized_msg,
                            media_url=media_url,
                            channel="whatsapp",
                            campaign_id=campaign_id,
                            campaign_name=campaign_name,
                            cta_type=cta_type,
                            cta_text=cta_text,
                            cta_link=cta_link
                        )
                    except Exception as chat_err:
                        logger.warning(f"[CAMPAIGN-CHAT] Ãcriture chat_messages Ã©chouÃ©e (WhatsApp, {contact_id}): {chat_err}")
                elif wa_response.get("status") == "simulated":
                    # v107: Simulated = Twilio non configurÃ© â compter comme ÃCHEC
                    whatsapp_result["status"] = "failed"
                    whatsapp_result["error"] = "Configuration Twilio manquante (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER non dÃ©finis)"
                    fail_count += 1
                    logger.error(f"[CAMPAIGN-LAUNCH] â WhatsApp NON ENVOYÃ (Twilio non configurÃ©) pour {contact_name} ({contact_phone})")
                else:
                    whatsapp_result["status"] = "failed"
                    whatsapp_result["error"] = wa_response.get("error", "Unknown error")
                    whatsapp_result["error_code"] = wa_response.get("error_code", "")
                    fail_count += 1
                    logger.error(f"[CAMPAIGN-LAUNCH] â WhatsApp Ã©chouÃ© pour {contact_name}: {wa_response.get('error')}")
            except Exception as e:
                whatsapp_result["status"] = "failed"
                whatsapp_result["error"] = str(e)
                fail_count += 1
                logger.error(f"[CAMPAIGN-LAUNCH] â Exception WhatsApp pour {contact_name}: {str(e)}")
            
            results.append(whatsapp_result)
        
        # ==================== ENVOI EMAIL (INDÃPENDANT) ====================
        if channels.get("email") and contact_email:
            email_result = {
                "contactId": contact_id,
                "contactName": contact_name,
                "contactEmail": contact_email,
                "contactPhone": contact_phone,
                "channel": "email",
                "status": "pending",
                "sentAt": None,
                "deliveredAt": None,  # v11: tracking
                "readAt": None        # v11: tracking
            }
            
            try:
                # Envoi via l'endpoint interne (Resend)
                if RESEND_AVAILABLE and RESEND_API_KEY:
                    # PrÃ©parer le template email
                    subject = f"ð¢ {campaign_name}"
                    first_name = contact_name.split()[0] if contact_name else "ami(e)"
                    
                    # v16.3: Construire le bloc CTA HTML pour l'email
                    cta_html = ""
                    if cta_text and cta_link:
                        cta_color = "#D91CD2" if cta_type == "conversation" else "#9333EA" if cta_type == "reserver" else "#6366f1"
                        cta_html = f"""
<div style="padding:16px 20px;text-align:center;">
<a href="{cta_link}" style="display:inline-block;padding:14px 32px;background:{cta_color};color:#fff;font-size:15px;font-weight:bold;text-decoration:none;border-radius:8px;">{cta_text}</a>
</div>"""
                    elif cta_text and cta_type == "reserver":
                        site_url = "https://afroboost.com"
                        cta_html = f"""
<div style="padding:16px 20px;text-align:center;">
<a href="{site_url}/#devenir-coach" style="display:inline-block;padding:14px 32px;background:#9333EA;color:#fff;font-size:15px;font-weight:bold;text-decoration:none;border-radius:8px;">{cta_text or 'RÃ©server'}</a>
</div>"""

                    # V159+V162: Google Drive URL handling â images â lh3, videos â clickable preview
                    import re as re_gd
                    _gd_file = re_gd.search(r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)', media_url or "")
                    _gd_open = re_gd.search(r'drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)', media_url or "")
                    _gd_id = (_gd_file.group(1) if _gd_file else _gd_open.group(1) if _gd_open else None)
                    _is_google_drive = bool(_gd_id)
                    _original_drive_url = media_url if _is_google_drive else None
                    # For Google Drive: create lh3 thumbnail URL (works for images, can serve as video thumbnail)
                    if _gd_id:
                        _gd_thumbnail = f"https://lh3.googleusercontent.com/d/{_gd_id}=w1000"
                        # V162: Keep original Drive URL for video playback link
                        _gd_preview_url = f"https://drive.google.com/file/d/{_gd_id}/preview"
                        _gd_view_url = f"https://drive.google.com/file/d/{_gd_id}/view"
                        # Only convert to lh3 for non-video (pure image) display
                        # We'll handle this in the media HTML block below
                        media_url = _gd_thumbnail  # default to lh3 for image display

                    # V108.5: Construire le bloc mÃ©dia HTML â avec preview vidÃ©o amÃ©liorÃ©e
                    media_html = ""
                    app_url = "https://www.afroboost.com"
                    if media_url:
                        # V162: Google Drive files â clickable thumbnail with play button + Drive link
                        # Since we can't detect video vs image from Drive URL alone,
                        # show a clickable image that links to Drive preview (works for both)
                        if _is_google_drive:
                            # V150: Gmail-compatible play button overlay using background-image on <td>
                            # Gmail strips position:absolute/relative, so we use table bg technique
                            media_html = f'''<div style="padding:0;text-align:center;">
<table cellpadding="0" cellspacing="0" border="0" width="100%" style="max-width:440px;margin:0 auto;">
<tr>
<td background="{_gd_thumbnail}" bgcolor="#1a1a2e" width="440" height="248" valign="middle" align="center" style="background-image:url({_gd_thumbnail});background-size:cover;background-position:center center;background-repeat:no-repeat;border-radius:8px;">
<a href="{_gd_view_url}" target="_blank" style="display:block;text-decoration:none;">
<table cellpadding="0" cellspacing="0" border="0" width="100%" height="248"><tr><td align="center" valign="middle" height="248">
<table cellpadding="0" cellspacing="0" border="0"><tr><td width="64" height="64" align="center" valign="middle" bgcolor="#D91CD2" style="border-radius:50%;background-color:rgba(217,28,210,0.9);color:#ffffff;font-size:28px;font-family:Arial,sans-serif;">&#9658;</td></tr></table>
</td></tr></table>
</a>
</td>
</tr>
</table>
<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-top:12px;">
<tr><td align="center">
<a href="{_gd_view_url}" target="_blank" style="display:inline-block;padding:12px 28px;background:linear-gradient(135deg,#D91CD2,#8b5cf6);color:#ffffff;text-decoration:none;border-radius:8px;font-family:Arial,sans-serif;font-size:14px;font-weight:bold;">&#9658; Voir le mÃ©dia</a>
</td></tr>
</table>
</div>'''
                            logger.info(f"[CAMPAIGN-EMAIL] Google Drive media detected, ID={_gd_id}, view_url={_gd_view_url}")
                        elif any(media_url.lower().endswith(ext) for ext in ['.mp4', '.webm', '.mov']):
                            # V108.5: Pour MP4, chercher thumbnail dans media_links + afficher preview cliquable
                            video_thumbnail = None
                            video_click_url = media_url
                            try:
                                # Chercher un media_link qui pointe vers cette vidÃ©o
                                media_link = await db.media_links.find_one(
                                    {"$or": [{"video_url": media_url}, {"video_url": {"$regex": media_url.split("/")[-1]}}]},
                                    {"_id": 0, "slug": 1, "thumbnail": 1, "custom_thumbnail": 1}
                                )
                                if media_link:
                                    video_thumbnail = media_link.get("custom_thumbnail") or media_link.get("thumbnail")
                                    slug = media_link.get("slug")
                                    if slug:
                                        video_click_url = f"{app_url}/?_mv=1#/v/{slug}"
                                        logger.info(f"[CAMPAIGN-EMAIL] Media link trouvÃ©: slug={slug}, thumbnail={video_thumbnail}")
                            except Exception as ml_err:
                                logger.warning(f"[CAMPAIGN-EMAIL] Erreur lookup media_link: {ml_err}")

                            if video_thumbnail:
                                # V150: Gmail-compatible thumbnail + play button using background-image on <td>
                                media_html = f'''<div style="padding:0;text-align:center;">
<table cellpadding="0" cellspacing="0" border="0" width="100%" style="max-width:440px;margin:0 auto;">
<tr>
<td background="{video_thumbnail}" bgcolor="#1a1a2e" width="440" height="248" valign="middle" align="center" style="background-image:url({video_thumbnail});background-size:cover;background-position:center center;background-repeat:no-repeat;border-radius:8px;">
<a href="{video_click_url}" style="display:block;text-decoration:none;">
<table cellpadding="0" cellspacing="0" border="0" width="100%" height="248"><tr><td align="center" valign="middle" height="248">
<table cellpadding="0" cellspacing="0" border="0"><tr><td width="64" height="64" align="center" valign="middle" bgcolor="#D91CD2" style="border-radius:50%;background-color:rgba(217,28,210,0.9);color:#ffffff;font-size:28px;font-family:Arial,sans-serif;">&#9658;</td></tr></table>
</td></tr></table>
</a>
</td>
</tr>
</table>
<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-top:12px;">
<tr><td align="center">
<a href="{video_click_url}" style="display:inline-block;padding:12px 28px;background:linear-gradient(135deg,#D91CD2,#8b5cf6);color:#ffffff;text-decoration:none;border-radius:8px;font-family:Arial,sans-serif;font-size:14px;font-weight:bold;">&#9658; Voir la vidÃ©o</a>
</td></tr>
</table>
</div>'''
                            else:
                                # V149: Pas de thumbnail â bouton play violet centrÃ© sur fond sombre
                                media_html = f'''<div style="padding:20px;text-align:center;background:#1a1a2e;border-radius:8px;margin:10px;">
<table cellpadding="0" cellspacing="0" border="0" width="100%">
<tr><td align="center" style="padding:20px 0;">
<a href="{video_click_url}" style="text-decoration:none;">
<div style="width:64px;height:64px;border-radius:50%;background:#D91CD2;display:inline-block;text-align:center;">
<table cellpadding="0" cellspacing="0" border="0" width="64" height="64"><tr><td align="center" valign="middle" style="color:#ffffff;font-size:28px;font-family:Arial,sans-serif;">&#9658;</td></tr></table>
</div>
</a>
</td></tr>
<tr><td align="center">
<a href="{video_click_url}" style="display:inline-block;padding:12px 28px;background:linear-gradient(135deg,#D91CD2,#8b5cf6);color:#ffffff;text-decoration:none;border-radius:8px;font-family:Arial,sans-serif;font-size:14px;font-weight:bold;">&#9658; Voir la vidÃ©o</a>
</td></tr>
</table>
</div>'''
                        elif any(media_url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']) or 'lh3.googleusercontent.com' in media_url:
                            media_html = f'<div style="padding:0;"><img src="{media_url}" alt="MÃ©dia" style="width:100%;max-height:300px;object-fit:cover;border-radius:0;" /></div>'
                        elif 'youtube.com' in media_url or 'youtu.be' in media_url:
                            # V109: YouTube â chercher/crÃ©er slug dans media_links â ouvrir MediaViewer
                            import re as re_yt
                            import uuid as uuid_yt
                            yt_match = re_yt.search(r'(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})', media_url)
                            yt_id = yt_match.group(1) if yt_match else None
                            yt_click_url = app_url  # fallback
                            yt_thumbnail = f"https://img.youtube.com/vi/{yt_id}/hqdefault.jpg" if yt_id else None
                            if yt_id:
                                try:
                                    # Chercher un media_link existant pour cette vidÃ©o YouTube
                                    yt_media_link = await db.media_links.find_one(
                                        {"$or": [
                                            {"video_url": media_url},
                                            {"video_url": {"$regex": yt_id}},
                                            {"video_url": f"https://www.youtube.com/watch?v={yt_id}"},
                                            {"video_url": f"https://youtu.be/{yt_id}"}
                                        ]},
                                        {"_id": 0, "slug": 1, "thumbnail": 1, "custom_thumbnail": 1}
                                    )
                                    if yt_media_link and yt_media_link.get("slug"):
                                        slug = yt_media_link["slug"]
                                        yt_click_url = f"{app_url}/?_mv=1#/v/{slug}"
                                        yt_thumbnail = yt_media_link.get("custom_thumbnail") or yt_media_link.get("thumbnail") or yt_thumbnail
                                        logger.info(f"[CAMPAIGN-EMAIL] YouTube media_link trouvÃ©: slug={slug}")
                                    else:
                                        # Auto-crÃ©er un media_link pour cette vidÃ©o YouTube
                                        auto_slug = f"yt-{yt_id}".lower()
                                        await db.media_links.update_one(
                                            {"slug": auto_slug},
                                            {"$setOnInsert": {
                                                "slug": auto_slug,
                                                "video_url": media_url,
                                                "thumbnail": yt_thumbnail,
                                                "title": campaign.get("subject", "VidÃ©o Afroboost"),
                                                "created_at": datetime.utcnow().isoformat()
                                            }},
                                            upsert=True
                                        )
                                        yt_click_url = f"{app_url}/?_mv=1#/v/{auto_slug}"
                                        logger.info(f"[CAMPAIGN-EMAIL] YouTube media_link auto-crÃ©Ã©: slug={auto_slug}")
                                except Exception as yt_err:
                                    logger.warning(f"[CAMPAIGN-EMAIL] Erreur lookup YouTube media_link: {yt_err}")
                                    yt_click_url = media_url  # fallback vers YouTube direct

                            if yt_thumbnail:
                                # V150: Gmail-compatible YouTube thumbnail + play button using background-image on <td>
                                media_html = f'''<div style="padding:0;text-align:center;">
<table cellpadding="0" cellspacing="0" border="0" width="100%" style="max-width:440px;margin:0 auto;">
<tr>
<td background="{yt_thumbnail}" bgcolor="#1a1a2e" width="440" height="248" valign="middle" align="center" style="background-image:url({yt_thumbnail});background-size:cover;background-position:center center;background-repeat:no-repeat;border-radius:8px;">
<a href="{yt_click_url}" style="display:block;text-decoration:none;">
<table cellpadding="0" cellspacing="0" border="0" width="100%" height="248"><tr><td align="center" valign="middle" height="248">
<table cellpadding="0" cellspacing="0" border="0"><tr><td width="64" height="64" align="center" valign="middle" bgcolor="#D91CD2" style="border-radius:50%;background-color:rgba(217,28,210,0.9);color:#ffffff;font-size:28px;font-family:Arial,sans-serif;">&#9658;</td></tr></table>
</td></tr></table>
</a>
</td>
</tr>
</table>
<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-top:12px;">
<tr><td align="center">
<a href="{yt_click_url}" style="display:inline-block;padding:12px 28px;background:linear-gradient(135deg,#D91CD2,#8b5cf6);color:#ffffff;text-decoration:none;border-radius:8px;font-family:Arial,sans-serif;font-size:14px;font-weight:bold;">&#9658; Voir la vidÃ©o</a>
</td></tr>
</table>
</div>'''
                            else:
                                media_html = f'<div style="padding:10px 20px;text-align:center;"><a href="{yt_click_url}" style="display:inline-block;padding:12px 28px;background:linear-gradient(135deg,#D91CD2,#8b5cf6);color:#ffffff;text-decoration:none;border-radius:8px;font-family:Arial,sans-serif;font-size:14px;font-weight:bold;">&#9658; Voir la vidÃ©o</a></div>'
                        else:
                            # V108.5: Lien mÃ©dia gÃ©nÃ©rique (ni vidÃ©o, ni image, ni YouTube)
                            media_html = f'''<div style="padding:16px;text-align:center;">
<a href="{media_url}" style="display:inline-block;padding:12px 28px;background:#9333EA;color:#ffffff;text-decoration:none;border-radius:8px;font-family:Arial,sans-serif;font-size:14px;font-weight:bold;">&#9658; Voir le contenu</a>
</div>'''

                    html_content = f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="utf-8"><title>Message Afroboost</title></head>
<body style="margin:0;padding:20px;background:#f5f5f5;font-family:Arial,sans-serif;">
<div style="max-width:480px;margin:0 auto;background:#111;border-radius:10px;overflow:hidden;">
<div style="background:#9333EA;padding:16px 20px;text-align:center;">
<span style="color:#fff;font-size:22px;font-weight:bold;">Afroboost</span>
</div>
{media_html}
<div style="padding:20px;color:#fff;font-size:14px;line-height:1.6;">
<p>Salut {first_name},</p>
{personalized_msg.replace(chr(10), '<br>')}
</div>
{cta_html}
<div style="padding:15px 20px;border-top:1px solid #333;text-align:center;">
<a href="https://afroboost.com" style="color:#9333EA;text-decoration:none;font-size:11px;">afroboost.com</a>
</div>
</div>
</body>
</html>"""
                    
                    params = {
                        "from": "Afroboost <notifications@afroboosteur.com>",
                        "to": [contact_email],
                        "subject": subject,
                        "html": html_content
                    }
                    
                    email_response = await asyncio.to_thread(resend.Emails.send, params)
                    email_result["status"] = "sent"
                    email_result["sentAt"] = datetime.now(timezone.utc).isoformat()
                    email_result["email_id"] = email_response.get("id")
                    success_count += 1
                    logger.info(f"[CAMPAIGN-LAUNCH] â Email envoyÃ© Ã  {contact_name} ({contact_email})")
                    # OmnicanalitÃ© : Ã©crire le message dans chat_messages pour l'UI client
                    try:
                        await _save_campaign_chat_message(
                            contact_id=contact_id,
                            content=personalized_msg,
                            media_url=media_url,
                            channel="email",
                            campaign_id=campaign_id,
                            campaign_name=campaign_name,
                            cta_type=cta_type,
                            cta_text=cta_text,
                            cta_link=cta_link
                        )
                    except Exception as chat_err:
                        logger.warning(f"[CAMPAIGN-CHAT] Ãcriture chat_messages Ã©chouÃ©e (email, {contact_id}): {chat_err}")
                else:
                    email_result["status"] = "simulated"
                    email_result["sentAt"] = datetime.now(timezone.utc).isoformat()
                    logger.info(f"[CAMPAIGN-LAUNCH] ð§ª Email simulÃ© pour {contact_name} ({contact_email})")
            except Exception as e:
                email_result["status"] = "failed"
                email_result["error"] = str(e)
                fail_count += 1
                logger.error(f"[CAMPAIGN-LAUNCH] â Email Ã©chouÃ© pour {contact_name}: {str(e)}")
            
            results.append(email_result)
        
        # ==================== INSTAGRAM (NON SUPPORTÃ - MANUEL) ====================
        if channels.get("instagram"):
            results.append({
                "contactId": contact_id,
                "contactName": contact_name,
                "contactEmail": contact_email,
                "contactPhone": contact_phone,
                "channel": "instagram",
                "status": "manual",
                "sentAt": None,
                "note": "Envoi manuel requis"
            })
    
    # v107: DÃ©terminer le statut final avec prÃ©cision
    if not results:
        final_status = "failed"  # Aucun contact rÃ©solu â Ã©chec
        logger.warning(f"[CAMPAIGN-LAUNCH] â ï¸ Aucun rÃ©sultat - 0 contacts rÃ©solus pour la campagne")
    elif fail_count > 0 and success_count == 0:
        final_status = "failed"  # 100% Ã©chouÃ©
    elif fail_count > 0 and success_count > 0:
        final_status = "partial"  # Partiellement rÃ©ussi
    else:
        final_status = "completed"  # 100% envoyÃ©
    
    # v107: Update campaign avec compteurs dÃ©taillÃ©s
    await db.campaigns.update_one(
        {"id": campaign_id},
        {"$set": {
            "status": final_status,
            "results": results,
            "successCount": success_count,
            "failCount": fail_count,
            "totalCount": success_count + fail_count,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "launchedAt": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    logger.info(f"[CAMPAIGN-LAUNCH] ð Campagne '{campaign_name}' terminÃ©e - â{success_count} / â{fail_count}")
    
    return await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})

# === v11 + V114: WEBHOOK TWILIO STATUS (delivered, read, failed, undelivered) ===
@api_router.post("/webhooks/twilio/status")
async def twilio_status_webhook(request: Request):
    """
    Webhook Twilio pour les mises Ã  jour de statut WhatsApp.
    Twilio envoie: queued, sent, delivered, read, failed, undelivered
    V114+V115: GÃ¨re les Ã©checs asynchrones et recalcule le statut campagne (production).
    """
    try:
        form_data = await request.form()
        message_sid = form_data.get("MessageSid", "")
        message_status = form_data.get("MessageStatus", "")
        error_code = form_data.get("ErrorCode", "")
        to_phone = form_data.get("To", "").replace("whatsapp:", "")
        from_phone = form_data.get("From", "").replace("whatsapp:", "")

        if not message_sid or not message_status:
            return {"ok": True}

        logger.info(f"[TWILIO-WEBHOOK-V114] ð¬ SID={message_sid} Status={message_status} ErrorCode={error_code} To={to_phone}")

        now_iso = datetime.now(timezone.utc).isoformat()

        # Chercher la campagne contenant ce SID dans ses rÃ©sultats
        update_fields = {}
        if message_status == "delivered":
            update_fields = {"results.$.deliveredAt": now_iso}
        elif message_status == "read":
            update_fields = {"results.$.readAt": now_iso, "results.$.deliveredAt": now_iso}
        elif message_status in ("failed", "undelivered"):
            # V115: Mapper les codes d'erreur Twilio vers des messages lisibles en franÃ§ais
            error_messages = {
                "63007": "NumÃ©ro WhatsApp non valide ou non enregistrÃ©",
                "63015": "NumÃ©ro non enregistrÃ© ou session WhatsApp expirÃ©e",
                "63016": "FenÃªtre de conversation expirÃ©e (>24h) â le contact doit rÃ©pondre d'abord",
                "21610": "Destinataire a bloquÃ© les messages",
                "21408": "CrÃ©dits Twilio insuffisants",
                "21211": "NumÃ©ro 'To' invalide",
                "21614": "NumÃ©ro non compatible WhatsApp",
                "63032": "Template de message non approuvÃ© par WhatsApp",
            }
            error_msg = error_messages.get(str(error_code), f"Twilio erreur {error_code}: {message_status}")
            update_fields = {
                "results.$.status": "failed",
                "results.$.error": error_msg,
                "results.$.error_code": str(error_code),
                "results.$.failedAt": now_iso
            }

        if update_fields:
            result = await db.campaigns.update_one(
                {"results.sid": message_sid},
                {"$set": update_fields}
            )
            if result.modified_count > 0:
                logger.info(f"[TWILIO-WEBHOOK-V114] â RÃ©sultat mis Ã  jour pour SID={message_sid}: {message_status}")

                # V114: Si Ã©chec, recalculer le statut global de la campagne
                if message_status in ("failed", "undelivered"):
                    campaign = await db.campaigns.find_one(
                        {"results.sid": message_sid},
                        {"_id": 0, "id": 1, "results": 1, "name": 1}
                    )
                    if campaign:
                        campaign_id = campaign["id"]
                        campaign_name = campaign.get("name", "")
                        all_results = campaign.get("results", [])
                        success_count = sum(1 for r in all_results if r.get("status") == "sent")
                        fail_count = sum(1 for r in all_results if r.get("status") == "failed")

                        if fail_count > 0 and success_count == 0:
                            new_status = "failed"
                        elif fail_count > 0 and success_count > 0:
                            new_status = "partial"
                        else:
                            new_status = "completed"

                        await db.campaigns.update_one(
                            {"id": campaign_id},
                            {"$set": {
                                "status": new_status,
                                "successCount": success_count,
                                "failCount": fail_count,
                                "updatedAt": now_iso
                            }}
                        )
                        logger.info(f"[TWILIO-WEBHOOK-V114] ð Campagne '{campaign_name}' â statut: {new_status} (â{success_count} â{fail_count})")

                        # Enregistrer l'erreur dans campaign_errors
                        await db.campaign_errors.insert_one({
                            "campaign_id": campaign_id,
                            "campaign_name": campaign_name,
                            "error_type": "twilio_async_failure",
                            "error_code": str(error_code),
                            "error_message": error_msg,
                            "message_sid": message_sid,
                            "channel": "whatsapp",
                            "to_phone": to_phone,
                            "from_phone": from_phone,
                            "twilio_status": message_status,
                            "created_at": now_iso
                        })
            else:
                logger.debug(f"[TWILIO-WEBHOOK-V114] Aucune campagne trouvÃ©e pour SID={message_sid}")

        return {"ok": True}
    except Exception as e:
        logger.error(f"[TWILIO-WEBHOOK-V114] Erreur: {e}")
        return {"ok": True}  # Toujours retourner 200 Ã  Twilio

# V112: Endpoint polling temps rÃ©el â rÃ©cupÃ©rer le statut d'une campagne
@api_router.get("/campaigns/{campaign_id}/status")
async def get_campaign_status(campaign_id: str):
    """
    V112: Retourne le statut actuel d'une campagne pour le polling temps rÃ©el.
    UtilisÃ© par le frontend pour mettre Ã  jour l'UI sans recharger la page.
    """
    campaign = await db.campaigns.find_one(
        {"id": campaign_id},
        {"_id": 0, "id": 1, "status": 1, "results": 1, "successCount": 1, "failCount": 1, "totalCount": 1, "updatedAt": 1}
    )
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign

@api_router.post("/campaigns/{campaign_id}/mark-sent")
async def mark_campaign_sent(campaign_id: str, data: dict):
    """Mark specific result as sent"""
    contact_id = data.get("contactId")
    channel = data.get("channel")
    
    await db.campaigns.update_one(
        {"id": campaign_id, "results.contactId": contact_id, "results.channel": channel},
        {"$set": {
            "results.$.status": "sent",
            "results.$.sentAt": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    # Check if all results are sent
    campaign = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if campaign:
        all_sent = all(r.get("status") == "sent" for r in campaign.get("results", []))
        if all_sent:
            await db.campaigns.update_one(
                {"id": campaign_id},
                {"$set": {"status": "completed", "updatedAt": datetime.now(timezone.utc).isoformat()}}
            )
    
    return {"success": True}

# --- Payment Links ---
# v9.3.0: Isolation par coach_id
@api_router.get("/payment-links")
async def get_payment_links(request: Request):
    try:
        user_email = require_auth(request)
    except HTTPException:
        user_email = ""
    is_admin = is_super_admin(user_email)  # v9.5.6

    # Si pas d'email (visiteur sur la vitrine App.js), charger les liens admin
    if not user_email:
        is_admin = True

    # ID de lien selon le coach
    link_id = "payment_links" if is_admin else f"payment_links_{user_email}"
    
    links = await db.payment_links.find_one({"id": link_id}, {"_id": 0})
    if not links:
        default_links = PaymentLinks().model_dump()
        default_links["id"] = link_id
        default_links["coach_id"] = user_email if not is_admin else None
        await db.payment_links.insert_one(default_links)
        return default_links
    return links

@api_router.put("/payment-links")
async def update_payment_links(links: PaymentLinksUpdate, request: Request):
    # V134: Auth obligatoire pour modifier les payment links
    user_email = require_auth(request)
    is_admin = is_super_admin(user_email)  # v9.5.6
    
    # ID de lien selon le coach
    link_id = "payment_links" if is_admin else f"payment_links_{user_email}"
    
    link_data = links.model_dump()
    link_data["coach_id"] = user_email if not is_admin else None
    
    await db.payment_links.update_one(
        {"id": link_id}, 
        {"$set": link_data}, 
        upsert=True
    )
    return await db.payment_links.find_one({"id": link_id}, {"_id": 0})

# v9.3.0: Endpoint public pour rÃ©cupÃ©rer les payment links d'un coach (vitrine)
@api_router.get("/payment-links/{coach_email}")
async def get_coach_payment_links(coach_email: str):
    """RÃ©cupÃ¨re les liens de paiement d'un coach spÃ©cifique (pour la vitrine publique)"""
    coach_email = coach_email.lower().strip()
    is_admin = is_super_admin(coach_email)  # v9.5.6
    
    link_id = "payment_links" if is_admin else f"payment_links_{coach_email}"
    
    links = await db.payment_links.find_one({"id": link_id}, {"_id": 0})
    if not links:
        return {"stripe": "", "paypal": "", "twint": "", "coachWhatsapp": ""}
    
    # Retourner seulement les liens publics
    return {
        "stripe": links.get("stripe", ""),
        "paypal": links.get("paypal", ""),
        "twint": links.get("twint", ""),
        "coachWhatsapp": links.get("coachWhatsapp", "")
    }

# --- Stripe Checkout avec TWINT ---

class CreateCheckoutRequest(BaseModel):
    """RequÃªte pour crÃ©er une session de paiement Stripe"""
    productName: str
    amount: float  # Montant en CHF (decimal, ex: 25.00)
    customerEmail: Optional[str] = None
    originUrl: str  # URL d'origine du frontend pour construire success/cancel URLs
    reservationData: Optional[dict] = None  # DonnÃ©es de rÃ©servation pour metadata

@api_router.post("/create-checkout-session")
async def create_checkout_session(request: CreateCheckoutRequest):
    """
    CrÃ©e une session Stripe Checkout avec support pour cartes et TWINT.
    TWINT nÃ©cessite la devise CHF.
    """
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe API key not configured")
    
    # Construire les URLs dynamiquement basÃ©es sur l'origine frontend
    # {CHECKOUT_SESSION_ID} est remplacÃ© automatiquement par Stripe
    success_url = f"{request.originUrl}?status=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{request.originUrl}?status=canceled"
    
    # Montant en centimes (Stripe utilise les plus petites unitÃ©s)
    amount_cents = int(request.amount * 100)
    
    # PrÃ©parer les metadata
    metadata = {
        "product_name": request.productName,
        "customer_email": request.customerEmail or "",
        "source": "afroboost_checkout"
    }
    if request.reservationData:
        metadata["reservation_id"] = request.reservationData.get("id", "")
        metadata["course_name"] = request.reservationData.get("courseName", "")
    
    # MÃ©thodes de paiement: card + twint (devise CHF obligatoire pour TWINT)
    payment_methods = ['card', 'twint']
    
    try:
        # CrÃ©er la session Stripe avec card + twint
        session = stripe.checkout.Session.create(
            payment_method_types=payment_methods,
            line_items=[{
                'price_data': {
                    'currency': 'chf',  # CHF obligatoire pour TWINT
                    'product_data': {
                        'name': request.productName,
                    },
                    'unit_amount': amount_cents,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=request.customerEmail,
            metadata=metadata,
        )
        
        # CrÃ©er l'entrÃ©e dans payment_transactions
        transaction = {
            "id": str(uuid.uuid4()),
            "session_id": session.id,
            "amount": request.amount,
            "currency": "chf",
            "product_name": request.productName,
            "customer_email": request.customerEmail,
            "metadata": metadata,
            "payment_status": "pending",
            "payment_methods": payment_methods,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.payment_transactions.insert_one(transaction)
        
        logger.info(f"Stripe session created with payment methods: {payment_methods}, session_id: {session.id}")
        
        return {
            "sessionId": session.id,
            "url": session.url,
            "paymentMethods": payment_methods
        }
        
    except stripe.error.InvalidRequestError as e:
        # Si TWINT cause une erreur (non activÃ© sur le compte), fallback sur card seul
        logger.warning(f"TWINT not available, falling back to card only: {str(e)}")
        
        try:
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'chf',
                        'product_data': {
                            'name': request.productName,
                        },
                        'unit_amount': amount_cents,
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url=success_url,
                cancel_url=cancel_url,
                customer_email=request.customerEmail,
                metadata=metadata,
            )
            
            # CrÃ©er l'entrÃ©e dans payment_transactions
            transaction = {
                "id": str(uuid.uuid4()),
                "session_id": session.id,
                "amount": request.amount,
                "currency": "chf",
                "product_name": request.productName,
                "customer_email": request.customerEmail,
                "metadata": metadata,
                "payment_status": "pending",
                "payment_methods": ['card'],
                "warning": "TWINT not available",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.payment_transactions.insert_one(transaction)
            
            logger.info(f"Stripe session created with card only (TWINT fallback), session_id: {session.id}")
            
            return {
                "sessionId": session.id,
                "url": session.url,
                "paymentMethods": ['card'],
                "warning": "TWINT not available on this Stripe account"
            }
            
        except stripe.error.StripeError as fallback_error:
            logger.error(f"Stripe fallback error: {str(fallback_error)}")
            raise HTTPException(status_code=500, detail=f"Payment error: {str(fallback_error)}")
            
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Payment error: {str(e)}")

@api_router.get("/checkout-status/{session_id}")
async def get_checkout_status(session_id: str):
    """
    VÃ©rifie le statut d'une session de paiement Stripe.
    """
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe API key not configured")
    
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        
        # Mettre Ã  jour le statut dans la base de donnÃ©es
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {
                "payment_status": session.payment_status,
                "status": session.status,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        return {
            "status": session.status,
            "paymentStatus": session.payment_status,
            "amountTotal": session.amount_total,
            "currency": session.currency,
            "metadata": session.metadata
        }
        
    except stripe.error.StripeError as e:
        logger.error(f"Error checking checkout status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error checking status: {str(e)}")

@api_router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """Webhook Stripe - GÃ¨re les paiements coach, crÃ©dits et clients."""
    try:
        body = await request.body()
        event = stripe.Event.construct_from(stripe.util.json.loads(body), stripe.api_key)
        if event.type == 'checkout.session.completed':
            session = event.data.object
            metadata = session.metadata or {}
            payment_type = metadata.get("type", "client_payment")
            
            # v13.0: Achat de crÃ©dits par partenaire existant
            if payment_type == "credit_purchase":
                coach_email = metadata.get("customer_email", "").lower().strip()
                credits = int(metadata.get("credits", 0))
                pack_name = metadata.get("pack_name", "Pack CrÃ©dits")
                price_chf = metadata.get("price_chf", "0")
                
                if coach_email and credits > 0:
                    # Ajouter les crÃ©dits au compte du coach
                    result = await db.coaches.update_one(
                        {"email": coach_email},
                        {"$inc": {"credits": credits}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
                    )
                    
                    # RÃ©cupÃ©rer le nouveau solde
                    coach = await db.coaches.find_one({"email": coach_email})
                    new_balance = coach.get("credits", 0) if coach else credits
                    
                    # v13.0: Logger la transaction dans credit_transactions
                    transaction_doc = {
                        "id": str(uuid.uuid4()),
                        "type": "credit_purchase",
                        "coach_email": coach_email,
                        "coach_name": metadata.get("customer_name", ""),
                        "pack_id": metadata.get("pack_id", ""),
                        "pack_name": pack_name,
                        "credits_added": credits,
                        "balance_after": new_balance,
                        "amount_chf": float(price_chf),
                        "stripe_session_id": session.id,
                        "stripe_customer_id": session.get("customer"),
                        "payment_status": "completed",
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    await db.credit_transactions.insert_one(transaction_doc)
                    
                    logger.info(f"[WEBHOOK-CREDITS] {coach_email} +{credits} crÃ©dits (Pack: {pack_name}) -> Solde: {new_balance}")
                    
                    # Notification email au coach
                    if RESEND_AVAILABLE and coach_email:
                        try:
                            html = f"""<div style="font-family:Arial;max-width:600px;margin:0 auto;background:#0a0a0a;">
                            <div style="background:linear-gradient(135deg,#d91cd2,#8b5cf6);padding:24px;text-align:center;">
                            <h1 style="color:white;margin:0;">CrÃ©dits ajoutÃ©s ! ð</h1></div>
                            <div style="padding:24px;color:#fff;">
                            <p>Bonjour {metadata.get('customer_name', 'Coach')},</p>
                            <p>Votre achat de <strong>{pack_name}</strong> a Ã©tÃ© confirmÃ©.</p>
                            <div style="background:rgba(217,28,210,0.15);border:1px solid rgba(217,28,210,0.3);padding:20px;border-radius:8px;margin:20px 0;text-align:center;">
                            <p style="margin:0;color:#22c55e;font-size:32px;font-weight:bold;">+{credits} crÃ©dits</p>
                            <p style="margin:12px 0 0;color:#888;">Nouveau solde: <strong style="color:#d91cd2;">{new_balance} crÃ©dits</strong></p>
                            </div>
                            <p style="color:#888;font-size:12px;">Utilisez vos crÃ©dits pour les campagnes, conversations IA et codes promo.</p>
                            </div></div>"""
                            await asyncio.to_thread(resend.Emails.send, {
                                "from": "Afroboost <notifications@afroboosteur.com>",
                                "to": [coach_email],
                                "subject": f"â +{credits} crÃ©dits ajoutÃ©s Ã  votre compte",
                                "html": html
                            })
                        except Exception as mail_err:
                            logger.warning(f"[WEBHOOK-CREDITS] Email error: {mail_err}")
                    
                    # Notification Bassi
                    if RESEND_AVAILABLE:
                        try:
                            bassi_html = f"""<div style="font-family:Arial;max-width:600px;margin:0 auto;background:#1a1a2e;padding:24px;">
                            <h2 style="color:#22c55e;margin:0 0 16px;">ð° Vente de Pack CrÃ©dits !</h2>
                            <div style="background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.3);padding:16px;border-radius:8px;">
                            <p style="margin:0;color:#fff;"><strong>Coach:</strong> {coach_email}</p>
                            <p style="margin:8px 0 0;color:#fff;"><strong>Pack:</strong> {pack_name}</p>
                            <p style="margin:8px 0 0;color:#22c55e;"><strong>Montant:</strong> {price_chf} CHF</p>
                            <p style="margin:8px 0 0;color:#d91cd2;"><strong>CrÃ©dits:</strong> +{credits}</p>
                            </div></div>"""
                            await asyncio.to_thread(resend.Emails.send, {
                                "from": "Afroboost System <notifications@afroboosteur.com>",
                                "to": [SUPER_ADMIN_EMAIL],
                                "subject": f"ð° Vente: {pack_name} Ã  {metadata.get('customer_name', coach_email)}",
                                "html": bassi_html
                            })
                        except Exception as notify_err:
                            logger.warning(f"[WEBHOOK-CREDITS] Notification Bassi error: {notify_err}")
            
            # v8.9: Paiement coach (inscription)
            elif payment_type == "coach_registration":
                # Paiement Coach - CrÃ©er le compte coach
                coach_email = metadata.get("customer_email", "").lower().strip()
                coach_name = metadata.get("customer_name", "")
                pack_id = metadata.get("pack_id", "")
                credits = int(metadata.get("credits", 0))
                
                # CrÃ©er ou mettre Ã  jour le coach
                coach_doc = {
                    "id": str(uuid.uuid4()),
                    "email": coach_email,
                    "name": coach_name,
                    "phone": metadata.get("customer_phone", ""),
                    "role": "partner",
                    "credits": credits,
                    "pack_id": pack_id,
                    "stripe_customer_id": session.get("customer"),
                    "is_active": True,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                await db.coaches.update_one(
                    {"email": coach_email},
                    {"$setOnInsert": coach_doc},
                    upsert=True
                )
                logger.info(f"[WEBHOOK] Coach crÃ©Ã©: {coach_email} avec {credits} crÃ©dits")
                
                # v9.0.2: Notifier Bassi de l'achat de pack
                if RESEND_AVAILABLE:
                    try:
                        pack_name = metadata.get("pack_name", "Pack Coach")
                        bassi_html = f"""<div style="font-family:Arial;max-width:600px;margin:0 auto;background:#1a1a2e;padding:24px;">
                        <h2 style="color:#d91cd2;margin:0 0 16px;">ð Nouveau Coach inscrit !</h2>
                        <div style="background:rgba(217,28,210,0.1);border:1px solid rgba(217,28,210,0.3);padding:16px;border-radius:8px;margin-bottom:16px;">
                        <p style="margin:0;color:#fff;"><strong>Email:</strong> {coach_email}</p>
                        <p style="margin:8px 0 0;color:#fff;"><strong>Nom:</strong> {coach_name}</p>
                        <p style="margin:8px 0 0;color:#fff;"><strong>Pack:</strong> {pack_name}</p>
                        <p style="margin:8px 0 0;color:#22c55e;"><strong>CrÃ©dits:</strong> {credits}</p>
                        </div>
                        <p style="color:#888;font-size:12px;">AccÃ©dez au Panel Admin pour gÃ©rer ce coach.</p>
                        </div>"""
                        await asyncio.to_thread(resend.Emails.send, {"from": "Afroboost System <notifications@afroboosteur.com>", "to": [SUPER_ADMIN_EMAIL], "subject": f"ð Nouveau Coach: {coach_name}", "html": bassi_html})
                        logger.info(f"[WEBHOOK] Notification Bassi envoyÃ©e pour {coach_email}")
                    except Exception as notify_err:
                        logger.warning(f"[WEBHOOK] Notification Bassi error: {notify_err}")
                
                # Envoyer email de bienvenue au coach
                if RESEND_AVAILABLE and coach_email:
                    try:
                        html = f"""<div style="font-family:Arial;max-width:600px;margin:0 auto;background:#0a0a0a;">
                        <div style="background:linear-gradient(135deg,#d91cd2,#8b5cf6);padding:24px;text-align:center;">
                        <h1 style="color:white;margin:0;">Bienvenue Coach !</h1></div>
                        <div style="padding:24px;color:#fff;">
                        <p>FÃ©licitations {coach_name} !</p>
                        <p>Ton compte Coach Afroboost est maintenant actif avec <strong>{credits} crÃ©dits</strong>.</p>
                        <p style="color:#a855f7;">Connecte-toi via le bouton "S'identifier" sur afroboost.com pour accÃ©der Ã  ton Dashboard personnel.</p>
                        </div></div>"""
                        await asyncio.to_thread(resend.Emails.send, {
                            "from": "Afroboost <notifications@afroboosteur.com>",
                            "to": [coach_email],
                            "subject": "Bienvenue Coach Afroboost !",
                            "html": html
                        })
                    except Exception as mail_err:
                        logger.warning(f"[WEBHOOK] Email coach error: {mail_err}")
            else:
                # Paiement Client standard
                await db.payment_transactions.update_one({"session_id": session.id}, {"$set": {"payment_status": session.payment_status, "status": "completed", "webhook_received_at": datetime.now(timezone.utc).isoformat()}})
                # v8.1: CREATION AUTOMATIQUE CODE D'ACCES
                customer_email = session.get("customer_email") or metadata.get("customer_email", "")
                product_name = metadata.get("product_name", "Abonnement Afroboost")
                sessions_count = 10 if "10" in product_name else (5 if "5" in product_name else 1)
                new_code = f"AFR-{str(uuid.uuid4())[:6].upper()}"
                discount_doc = {"id": str(uuid.uuid4()), "code": new_code, "type": "100%", "value": 100, "assignedEmail": customer_email, "maxUses": sessions_count, "used": 0, "active": True, "courses": [], "created_at": datetime.now(timezone.utc).isoformat(), "source": "stripe_payment", "session_id": session.id}
                await db.discount_codes.insert_one(discount_doc)
                logger.info(f"[PAYMENT] Code {new_code} cree pour {customer_email} ({sessions_count} seances)")
                # v95.2: Auto-crÃ©er la subscription aprÃ¨s paiement Stripe
                subscription_data = {
                    "id": str(uuid.uuid4()),
                    "email": customer_email.lower().strip(),
                    "name": metadata.get("customer_name", customer_email.split("@")[0]),
                    "code": new_code,
                    "offer_name": product_name,
                    "total_sessions": sessions_count,
                    "used_sessions": 0,
                    "remaining_sessions": sessions_count,
                    "expires_at": None,
                    "status": "active",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "source": "stripe_auto"
                }
                await db.subscriptions.insert_one(subscription_data)
                logger.info(f"[PAYMENT] Subscription auto-creee: {customer_email} - {product_name} ({sessions_count} seances)")
                # v8.1: EMAIL AVEC QR CODE + CODE TEXTE
                if RESEND_AVAILABLE and RESEND_API_KEY and customer_email:
                    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=https://afroboost.com/?qr={new_code}&format=png"
                    html = f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0a0a0a;"><div style="background:linear-gradient(135deg,#d91cd2,#8b5cf6);padding:24px;text-align:center;"><h1 style="color:white;margin:0;font-size:22px;">Bienvenue chez Afroboost</h1></div><div style="padding:24px;color:#fff;"><p style="color:#a855f7;font-size:16px;line-height:1.6;">Merci pour ton achat et bienvenue dans la communaute Afroboost ! <span style="font-size:18px;">&#9889;</span><br><br>Ton energie va faire la difference. Tu trouveras ci-dessous ton code personnel et ton QR Code pour acceder a tes seances.</p><div style="background:rgba(147,51,234,0.15);border:1px solid rgba(147,51,234,0.3);border-radius:12px;padding:20px;margin:20px 0;text-align:center;"><p style="margin:0 0 8px;color:#888;">Ton code d'acces personnel</p><p style="margin:0;color:#d91cd2;font-size:28px;font-weight:bold;letter-spacing:3px;">{new_code}</p><p style="margin:12px 0 0;color:#888;">{sessions_count} seances incluses</p></div><div style="text-align:center;margin:30px 0;"><p style="color:#888;margin-bottom:16px;">Ton QR Code d'acces</p><img src="{qr_url}" alt="QR Code Afroboost" width="150" height="150" style="background:white;padding:10px;border-radius:8px;display:block;margin:0 auto;"/><p style="color:#a855f7;font-size:13px;margin-top:12px;">Presente ce QR Code a l'entree de ton cours.</p></div><div style="text-align:center;margin:30px 0;"><a href="https://afroboost.com" style="display:inline-block;background:#d91cd2;color:white;padding:14px 28px;text-decoration:none;border-radius:8px;font-weight:bold;font-size:14px;">Acceder a mon espace Afroboost</a></div><p style="color:#666;font-size:12px;text-align:center;margin-top:30px;">Conserve ce mail precieusement. A tres vite !</p></div></div>"""
                    try:
                        await asyncio.to_thread(resend.Emails.send, {"from": "Afroboost <notifications@afroboosteur.com>", "to": [customer_email], "subject": f"Votre acces Afroboost - {new_code}", "html": html})
                        logger.info(f"[PAYMENT] Email envoye a {customer_email}")
                    except Exception as mail_err:
                        logger.warning(f"[PAYMENT] Email error: {mail_err}")
                # v8.7: Sync CRM - Creer/MAJ contact (email unique)
                await db.chat_participants.update_one({"email": customer_email}, {"$set": {"email": customer_email, "name": metadata.get("customer_name", customer_email.split("@")[0]), "source": "stripe_payment", "updated_at": datetime.now(timezone.utc).isoformat()}, "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
                # V120: Push notification au coach pour la vente
                try:
                    customer_name = metadata.get("customer_name", customer_email.split("@")[0])
                    await send_push_to_coaches(
                        "ð° Nouvelle vente !",
                        f"{customer_name} â {product_name} ({sessions_count} sÃ©ances)",
                        {"url": "/coach", "type": "new_sale"}
                    )
                except Exception as push_err:
                    logger.warning(f"[PUSH-COACH] Push vente error: {push_err}")
                # v162: Email preuve de vente au coach
                try:
                    coach_sale_html = f"""<div style="font-family:Arial;max-width:600px;margin:0 auto;background:#1a1a2e;color:#fff;padding:24px;border-radius:12px">
                        <div style="text-align:center;padding:16px 0">
                            <h2 style="color:#d91cd2">Nouvelle vente Afroboost</h2>
                        </div>
                        <div style="background:#16213e;border-radius:8px;padding:16px;margin:12px 0">
                            <p><strong>Client:</strong> {metadata.get("customer_name", "N/A")} ({customer_email})</p>
                            <p><strong>Offre:</strong> {product_name}</p>
                            <p><strong>Seances:</strong> {sessions_count}</p>
                            <p><strong>Code:</strong> {new_code}</p>
                            <p><strong>Date:</strong> {datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")}</p>
                        </div>
                    </div>"""
                    await asyncio.to_thread(resend.Emails.send, {"from": "Afroboost <notifications@afroboosteur.com>", "to": [COACH_EMAIL], "subject": f"Vente - {metadata.get('customer_name', 'Client')} - {product_name}", "html": coach_sale_html})
                    logger.info(f"[EMAIL] Preuve de vente envoyee au coach pour {customer_email}")
                except Exception as coach_mail_err:
                    logger.warning(f"[EMAIL] Erreur envoi preuve vente coach: {coach_mail_err}")
        elif event.type == 'checkout.session.expired':
            session = event.data.object
            await db.payment_transactions.update_one({"session_id": session.id}, {"$set": {"status": "expired", "webhook_received_at": datetime.now(timezone.utc).isoformat()}})
        return {"received": True}
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Webhook error: {str(e)}")

# === ESPACE ABONNÃ â Lookup par code AFR-XXXXXX v11.0 ===
@api_router.get("/subscriber/{code}")
async def get_subscriber_by_code(code: str):
    """
    RÃ©cupÃ¨re les infos d'un abonnÃ© via son code AFR-XXXXXX.
    Retourne: sÃ©ances restantes, historique, QR code URL.
    """
    try:
        code_upper = code.upper().strip()
        # Chercher dans discount_codes
        discount = await db.discount_codes.find_one(
            {"code": code_upper},
            {"_id": 0}
        )
        if not discount:
            raise HTTPException(status_code=404, detail="Code abonnÃ© introuvable")

        # Infos de base
        max_uses = discount.get("maxUses", 0)
        used = discount.get("used", 0)
        remaining = max(0, max_uses - used)
        email = discount.get("assignedEmail", "")
        is_active = discount.get("active", False) and remaining > 0

        # QR Code URL
        qr_data = f"https://afroboost.com/?qr={code_upper}"
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={qr_data}&format=png"

        # Historique des validations (si collection existe)
        validations = []
        try:
            validation_docs = await db.qr_validations.find(
                {"code": code_upper},
                {"_id": 0}
            ).sort("validated_at", -1).to_list(50)
            validations = validation_docs
        except Exception:
            pass

        return {
            "code": code_upper,
            "email": email,
            "name": discount.get("name", email.split("@")[0] if email else "AbonnÃ©"),
            "sessions_total": max_uses,
            "sessions_used": used,
            "sessions_remaining": remaining,
            "is_active": is_active,
            "qr_code_url": qr_url,
            "created_at": discount.get("created_at", ""),
            "source": discount.get("source", ""),
            "validations": validations
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[SUBSCRIBER] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === ESPACE ABONNÃ â RÃ©cupÃ©ration d'accÃ¨s par email ou WhatsApp v11.1 ===
@api_router.post("/subscriber/recover")
async def recover_subscriber_access(request: Request):
    """
    Retrouver ses accÃ¨s abonnÃ© par email ou WhatsApp.
    Renvoie le code + QR Code par email.
    Rate limited: 3 requÃªtes max par email/10 minutes.
    """
    try:
        body = await request.json()
        email = body.get("email", "").lower().strip() if body.get("email") else ""
        whatsapp = body.get("whatsapp", "").strip() if body.get("whatsapp") else ""

        # Au moins un paramÃ¨tre requis
        if not email and not whatsapp:
            raise HTTPException(status_code=400, detail="Email ou WhatsApp requis")

        # RATE LIMITING: VÃ©rifier les tentatives de rÃ©cupÃ©ration
        ten_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=10)
        attempt_key = email if email else f"whatsapp_{whatsapp}"

        existing_attempts = await db.recovery_attempts.count_documents({
            "key": attempt_key,
            "created_at": {"$gte": ten_minutes_ago.isoformat()}
        })

        if existing_attempts >= 3:
            raise HTTPException(status_code=429, detail="Trop de tentatives. RÃ©essayez dans 10 minutes.")

        # Enregistrer la tentative
        await db.recovery_attempts.insert_one({
            "key": attempt_key,
            "email": email,
            "whatsapp": whatsapp,
            "created_at": datetime.now(timezone.utc).isoformat()
        })

        # Chercher le code abonnÃ©
        discount = None
        found_email = None

        if email:
            # Recherche directe par assignedEmail
            discount = await db.discount_codes.find_one(
                {"assignedEmail": email, "active": True},
                {"_id": 0}
            )
            if discount:
                found_email = email
        else:
            # Recherche par WhatsApp: trouver d'abord le participant chat
            participant = await db.chat_participants.find_one(
                {"whatsapp": whatsapp},
                {"_id": 0}
            )
            if participant:
                found_email = participant.get("email")
                if found_email:
                    # Chercher le code avec cet email
                    discount = await db.discount_codes.find_one(
                        {"assignedEmail": found_email, "active": True},
                        {"_id": 0}
                    )

        if not discount or not found_email:
            logger.info(f"[SUBSCRIBER-RECOVER] No active code found for email={email}, whatsapp={whatsapp}")
            raise HTTPException(status_code=404, detail="Aucun code abonnÃ© actif trouvÃ©")

        # Infos du code
        code = discount.get("code", "").upper()
        max_uses = discount.get("maxUses", 0)
        used = discount.get("used", 0)
        remaining = max(0, max_uses - used)
        name = discount.get("name", found_email.split("@")[0] if found_email else "AbonnÃ©")

        # QR Code URL
        qr_data = f"https://afroboost.com/?qr={code}"
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={qr_data}"

        # Envoyer l'email avec code et QR code
        if RESEND_AVAILABLE and RESEND_API_KEY:
            try:
                html_content = f"""
                <div style="background: linear-gradient(135deg, #a855f7 0%, #ec4899 100%); padding: 40px 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; border-radius: 12px 12px 0 0;">
                    <h1 style="color: #fff; margin: 0; font-size: 24px;">Vos accÃ¨s Afroboost</h1>
                </div>
                <div style="background: #1f2937; padding: 40px 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #fff;">
                    <p style="margin: 0 0 24px 0;">Bonjour {name},</p>
                    <p style="margin: 0 0 24px 0; color: #d1d5db;">Voici votre code d'accÃ¨s Afroboost et vos informations d'abonnement.</p>

                    <div style="background: #111827; border-radius: 8px; padding: 24px; margin: 24px 0; border-left: 4px solid #a855f7;">
                        <p style="margin: 0 0 12px 0; color: #9ca3af; font-size: 12px;">Votre code:</p>
                        <p style="margin: 0; font-size: 28px; font-weight: bold; color: #60a5fa; font-family: 'Courier New', monospace;">{code}</p>
                        <p style="margin: 16px 0 0 0; color: #9ca3af; font-size: 13px;">SÃ©ances restantes: <span style="color: #22c55e; font-weight: bold;">{remaining}/{max_uses}</span></p>
                    </div>

                    <p style="margin: 24px 0 16px 0; color: #9ca3af; font-size: 13px;">Scannez ce code QR pour accÃ©der:</p>
                    <div style="text-align: center; margin: 24px 0;">
                        <img src="{qr_url}" alt="QR Code {code}" style="max-width: 200px; height: auto; border-radius: 8px; background: #fff; padding: 8px;">
                    </div>

                    <p style="margin: 24px 0 8px 0; color: #9ca3af; font-size: 12px;">Ou accÃ©dez directement en utilisant le lien:</p>
                    <p style="margin: 0 0 24px 0; word-break: break-all; color: #60a5fa; font-size: 12px;">https://afroboost.com/?qr={code}</p>

                    <div style="border-top: 1px solid #374151; padding-top: 16px; margin-top: 24px;">
                        <p style="margin: 0; color: #9ca3af; font-size: 11px;">Questions? Contactez-nous sur WhatsApp ou par email.</p>
                    </div>
                </div>
                """

                await asyncio.to_thread(resend.Emails.send, {
                    "from": "Afroboost <notifications@afroboosteur.com>",
                    "to": [found_email],
                    "subject": f"Votre code d'accÃ¨s Afroboost - {code}",
                    "html": html_content
                })
                logger.info(f"[SUBSCRIBER-RECOVER] Recovery email sent to {found_email}")
            except Exception as e:
                logger.warning(f"[SUBSCRIBER-RECOVER] Email send error: {e}")
                # Continue anyway - code info will be returned

        return {
            "success": True,
            "code": code,
            "email": found_email,
            "name": name,
            "sessions_remaining": remaining,
            "sessions_total": max_uses,
            "qr_code_url": qr_url,
            "sent_to_chat": False
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[SUBSCRIBER-RECOVER] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === STRIPE CHECKOUT POUR COACHS PARTENAIRES v8.9 ===
@api_router.post("/stripe/create-coach-checkout")
async def create_coach_checkout(request: Request):
    """
    CrÃ©e une session Stripe Checkout pour l'inscription d'un nouveau coach.
    AprÃ¨s paiement, le coach recevra ses crÃ©dits et son accÃ¨s.
    """
    try:
        body = await request.json()
        price_id = body.get("price_id")
        pack_id = body.get("pack_id")
        email = body.get("email", "").lower().strip()
        name = body.get("name", "")
        phone = body.get("phone", "")
        promo_code = body.get("promo_code", "")
        
        if not price_id or not email or not name:
            raise HTTPException(status_code=400, detail="price_id, email et name requis")
        
        # RÃ©cupÃ©rer les infos du pack
        pack = await db.coach_packs.find_one({"id": pack_id})
        if not pack:
            raise HTTPException(status_code=404, detail="Pack non trouvÃ©")
        
        # v8.9.7: DÃ©tecter l'URL frontend depuis le Referer ou utiliser l'env
        referer = request.headers.get("Referer", "")
        if referer:
            from urllib.parse import urlparse
            parsed = urlparse(referer)
            frontend_url = f"{parsed.scheme}://{parsed.netloc}"
        else:
            frontend_url = os.environ.get('FRONTEND_URL', 'https://afroboost.com')
        
        # v15.5: URL de redirection dynamique (dev/prod)
        referer = request.headers.get("Referer", "")
        if referer:
            from urllib.parse import urlparse
            parsed = urlparse(referer)
            frontend_url = f"{parsed.scheme}://{parsed.netloc}"
        else:
            frontend_url = os.environ.get('FRONTEND_URL', 'https://afroboost.com')

        COACH_DASHBOARD_URL = f"{frontend_url}/#partner-dashboard"
        CANCEL_URL = f"{frontend_url}/#devenir-coach"

        # v15.5: Essayer avec TWINT d'abord, fallback card-only
        methods_to_try = [["card", "twint"], ["card"]]
        checkout_session = None
        for methods in methods_to_try:
            try:
                checkout_session = stripe.checkout.Session.create(
                    payment_method_types=methods,
                    line_items=[{
                        "price": price_id,
                        "quantity": 1
                    }],
                    mode="payment",
                    success_url=f"{base_url}/#partner-dashboard?success=true&session_id={{CHECKOUT_SESSION_ID}}&auth=success",
                    cancel_url=CANCEL_URL,
                    customer_email=email,
                    metadata={
                        "type": "coach_registration",
                        "pack_id": pack_id,
                        "pack_name": pack.get("name", ""),
                        "credits": str(pack.get("credits", 0)),
                        "customer_name": name,
                        "customer_email": email,
                        "customer_phone": phone,
                        "promo_code": promo_code
                    }
                )
                break
            except Exception as twint_err:
                logger.warning(f"[COACH-CHECKOUT] Methods {methods} failed: {twint_err}, trying next...")
                continue

        if not checkout_session:
            raise Exception("Impossible de crÃ©er la session Stripe")

        logger.info(f"[COACH-CHECKOUT] Session crÃ©Ã©e pour {email}, pack={pack.get('name')}")
        return {"checkout_url": checkout_session.url, "session_id": checkout_session.id}
        
    except HTTPException:
        raise
    except stripe.error.StripeError as e:
        logger.error(f"[COACH-CHECKOUT] Stripe error: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur Stripe: {str(e)}")
    except Exception as e:
        logger.error(f"[COACH-CHECKOUT] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === v13.0: BOUTIQUE CRÃDITS - Achat de packs par partenaires existants ===
@api_router.post("/stripe/create-credit-checkout")
async def create_credit_checkout(request: Request):
    """
    v13.0: CrÃ©e une session Stripe Checkout pour l'achat de crÃ©dits par un partenaire existant.
    L'argent va directement Ã  Bassi (Super Admin).
    """
    try:
        body = await request.json()
        pack_id = body.get("pack_id")
        caller_email = require_auth(request)

        if not pack_id:
            raise HTTPException(status_code=400, detail="pack_id requis")
        
        # Super Admin ne paie jamais
        if is_super_admin(caller_email):
            raise HTTPException(status_code=400, detail="Le Super Admin a des crÃ©dits illimitÃ©s")
        
        # VÃ©rifier que le coach existe
        coach = await db.coaches.find_one({"email": caller_email})
        if not coach:
            raise HTTPException(status_code=404, detail="Coach non trouvÃ©")
        
        # RÃ©cupÃ©rer les infos du pack
        pack = await db.coach_packs.find_one({"id": pack_id})
        if not pack:
            raise HTTPException(status_code=404, detail="Pack non trouvÃ©")
        
        # Si pas de price_id Stripe, crÃ©er un prix Ã  la volÃ©e
        price_id = pack.get("stripe_price_id")
        if not price_id:
            # CrÃ©er le produit et le prix Stripe
            product = stripe.Product.create(
                name=pack.get("name", "Pack CrÃ©dits"),
                description=f"{pack.get('credits', 0)} crÃ©dits Afroboost"
            )
            price = stripe.Price.create(
                product=product.id,
                unit_amount=int(float(pack.get("price", 0)) * 100),  # Convertir CHF en centimes
                currency="chf"
            )
            price_id = price.id
            # Sauvegarder les IDs Stripe dans le pack
            await db.coach_packs.update_one(
                {"id": pack_id},
                {"$set": {"stripe_product_id": product.id, "stripe_price_id": price_id}}
            )
            logger.info(f"[CREDIT-CHECKOUT] Prix Stripe crÃ©Ã©: {price_id} pour pack {pack_id}")
        
        # URL de redirection
        referer = request.headers.get("Referer", "")
        if referer:
            from urllib.parse import urlparse
            parsed = urlparse(referer)
            frontend_url = f"{parsed.scheme}://{parsed.netloc}"
        else:
            frontend_url = "https://afroboost.com"
        
        # CrÃ©er la session Stripe Checkout
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price": price_id,
                "quantity": 1
            }],
            mode="payment",
            success_url=f"{frontend_url}?credit_success=true&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{frontend_url}?credit_cancelled=true",
            customer_email=caller_email,
            metadata={
                "type": "credit_purchase",  # v13.0: Type pour le webhook
                "pack_id": pack_id,
                "pack_name": pack.get("name", ""),
                "credits": str(pack.get("credits", 0)),
                "price_chf": str(pack.get("price", 0)),
                "customer_email": caller_email,
                "customer_name": coach.get("name", "")
            }
        )
        
        logger.info(f"[CREDIT-CHECKOUT] Session crÃ©Ã©e pour {caller_email}, pack={pack.get('name')}, crÃ©dits={pack.get('credits')}")
        return {"checkout_url": checkout_session.url, "session_id": checkout_session.id}
        
    except HTTPException:
        raise
    except stripe.error.StripeError as e:
        logger.error(f"[CREDIT-CHECKOUT] Stripe error: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur Stripe: {str(e)}")
    except Exception as e:
        logger.error(f"[CREDIT-CHECKOUT] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# v13.0: Liste des packs crÃ©dits disponibles pour la boutique
@api_router.get("/credit-packs")
async def get_credit_packs():
    """Retourne les packs de crÃ©dits visibles pour l'achat"""
    packs = await db.coach_packs.find(
        {"visible": {"$ne": False}},  # Packs visibles uniquement
        {"_id": 0}
    ).sort("price", 1).to_list(20)  # Trier par prix croissant
    return packs

# v13.0: Historique des transactions de crÃ©dits
@api_router.get("/credit-transactions")
async def get_credit_transactions(request: Request):
    """Retourne l'historique des achats de crÃ©dits (Admin: tous, Coach: les siens)"""
    try:
        user_email = require_auth(request)
    except HTTPException:
        user_email = ""
    is_admin = is_super_admin(user_email)
    
    query = {} if is_admin else {"coach_email": user_email}
    transactions = await db.credit_transactions.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    return transactions



# --- Concept ---
# v9.3.0: Isolation par coach_id - chaque coach a sa propre configuration
@api_router.get("/concept", response_model=Concept)
async def get_concept(request: Request):
    try:
        user_email = require_auth(request)
    except HTTPException:
        user_email = ""
    is_admin = is_super_admin(user_email)  # v9.5.6

    # Si pas d'email (visiteur sur la vitrine App.js), charger le concept admin
    if not user_email:
        is_admin = True

    # Super Admin: concept global, Coach: concept personnel
    concept_id = "concept" if is_admin else f"concept_{user_email}"
    
    concept = await db.concept.find_one({"id": concept_id}, {"_id": 0})
    if not concept:
        # CrÃ©er un concept par dÃ©faut pour ce coach
        default_concept = Concept().model_dump()
        default_concept["id"] = concept_id
        default_concept["coach_id"] = user_email if not is_admin else None
        await db.concept.insert_one(default_concept)
        return default_concept
    return concept

@api_router.put("/concept")
async def update_concept(concept: ConceptUpdate, request: Request):
    try:
        user_email = require_auth(request)
    except HTTPException:
        user_email = ""
    is_admin = is_super_admin(user_email)  # v9.5.6
    
    # Super Admin: concept global, Coach: concept personnel
    concept_id = "concept" if is_admin else f"concept_{user_email}"
    
    try:
        updates = {k: v for k, v in concept.model_dump().items() if v is not None}
        updates["coach_id"] = user_email if not is_admin else None
        result = await db.concept.update_one({"id": concept_id}, {"$set": updates}, upsert=True)
        updated = await db.concept.find_one({"id": concept_id}, {"_id": 0})
        return updated
    except Exception as e:
        logger.error(f"Error updating concept: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- v17.0: Branding (couleur accent + logo) ---
@api_router.post("/coach/update-branding")
async def update_coach_branding(request: Request):
    """Met Ã  jour accent_color et logo_url du coach"""
    body = await request.json()
    email = require_auth(request)

    updates = {}
    if "accent_color" in body:
        updates["accent_color"] = body["accent_color"]
    if "logo_url" in body:
        updates["logo_url"] = body["logo_url"]

    if updates:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.coaches.update_one({"email": email}, {"$set": updates}, upsert=True)

    coach = await db.coaches.find_one({"email": email}, {"_id": 0})
    return {"accent_color": coach.get("accent_color", "#D91CD2"), "logo_url": coach.get("logo_url", "")}

@api_router.get("/coach/branding/{coach_email}")
async def get_coach_branding(coach_email: str):
    """RÃ©cupÃ¨re le branding public d'un coach"""
    coach = await db.coaches.find_one({"email": coach_email.lower()}, {"_id": 0, "accent_color": 1, "logo_url": 1})
    if not coach:
        return {"accent_color": "#D91CD2", "logo_url": ""}
    return {"accent_color": coach.get("accent_color", "#D91CD2"), "logo_url": coach.get("logo_url", "")}


# --- v17.1: SEO Dynamique ---
@api_router.post("/coach/update-seo")
async def update_coach_seo(request: Request):
    """Met Ã  jour meta_title, meta_description, keywords du coach"""
    body = await request.json()
    email = require_auth(request)

    updates = {}
    for field in ["meta_title", "meta_description", "seo_keywords"]:
        if field in body:
            updates[field] = body[field]

    if updates:
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.coaches.update_one({"email": email}, {"$set": updates}, upsert=True)

    coach = await db.coaches.find_one({"email": email}, {"_id": 0, "meta_title": 1, "meta_description": 1, "seo_keywords": 1})
    return coach or {}

@api_router.get("/coach/seo/{coach_email}")
async def get_coach_seo(coach_email: str):
    """RÃ©cupÃ¨re les meta SEO d'un coach (public)"""
    coach = await db.coaches.find_one(
        {"email": coach_email.lower()},
        {"_id": 0, "meta_title": 1, "meta_description": 1, "seo_keywords": 1, "name": 1, "platform_name": 1, "accent_color": 1, "logo_url": 1}
    )
    if not coach:
        return {}
    return coach

@api_router.get("/og/{username}")
async def get_og_meta(username: str, request: Request):
    """v17.1: HTML OpenGraph pour crawlers (WhatsApp, Instagram, Facebook)"""
    from starlette.responses import HTMLResponse

    # Trouver le coach â mÃªme logique que coach/vitrine
    SUPER_ADMIN_EMAILS = ['contact.artboost@gmail.com', 'afroboost.bassi@gmail.com']
    # v65: Redirection 301 pour "artboost" â "bassi"
    if username.lower() == "artboost":
        from starlette.responses import RedirectResponse as RR
        return RR(url="/api/og/bassi", status_code=301)
    if username.lower() in ["bassi", "afroboost"]:
        coach = {"name": "Bassi - Afroboost", "email": "contact.artboost@gmail.com", "platform_name": "Afroboost"}
    else:
        coach = await db.coaches.find_one(
            {"$or": [
                {"username": username.lower()},
                {"name": {"$regex": f"^{username}$", "$options": "i"}},
                {"email": username.lower()},
                {"id": username}
            ]},
            {"_id": 0}
        )

    if not coach:
        return HTMLResponse("<html><head><title>Afroboost</title></head><body>Coach not found</body></html>", status_code=404)

    title = coach.get("meta_title") or f"{coach.get('platform_name') or coach.get('name', username)} | Afroboost"
    description = coach.get("meta_description") or f"DÃ©couvrez les cours et services de {coach.get('name', username)} sur Afroboost"
    image = coach.get("logo_url") or "https://afroboost-v11-dev-pm7l.vercel.app/logo192.png"
    url = f"https://afroboost-v11-dev-pm7l.vercel.app/coach/{username}"
    accent = coach.get("accent_color", "#D91CD2")

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8"/>
    <title>{title}</title>
    <meta name="description" content="{description}"/>
    <meta name="theme-color" content="{accent}"/>

    <!-- OpenGraph -->
    <meta property="og:type" content="website"/>
    <meta property="og:title" content="{title}"/>
    <meta property="og:description" content="{description}"/>
    <meta property="og:image" content="{image}"/>
    <meta property="og:url" content="{url}"/>
    <meta property="og:site_name" content="Afroboost"/>

    <!-- Twitter Card -->
    <meta name="twitter:card" content="summary_large_image"/>
    <meta name="twitter:title" content="{title}"/>
    <meta name="twitter:description" content="{description}"/>
    <meta name="twitter:image" content="{image}"/>

    <meta http-equiv="refresh" content="0;url={url}"/>
</head>
<body>
    <h1>{title}</h1>
    <p>{description}</p>
    <a href="{url}">Voir la page</a>
</body>
</html>"""
    return HTMLResponse(html)

@api_router.get("/sitemap.xml")
async def get_sitemap():
    """v17.1: Sitemap XML dynamique"""
    from starlette.responses import Response

    base_url = "https://afroboost-v11-dev-pm7l.vercel.app"
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    urls = [
        f'  <url><loc>{base_url}/</loc><lastmod>{now}</lastmod><priority>1.0</priority></url>',
        f'  <url><loc>{base_url}/devenir-coach</loc><lastmod>{now}</lastmod><priority>0.8</priority></url>'
    ]

    # Ajouter toutes les vitrines de coachs actifs
    coaches = await db.coaches.find(
        {"is_active": {"$ne": False}},
        {"_id": 0, "username": 1, "name": 1}
    ).to_list(200)

    for c in coaches:
        slug = c.get("username") or c.get("name", "").lower().replace(" ", "-")
        if slug:
            urls.append(f'  <url><loc>{base_url}/coach/{slug}</loc><lastmod>{now}</lastmod><priority>0.7</priority></url>')

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>"""

    return Response(content=xml, media_type="application/xml")


# --- v17.2: FAQ Module ---
@api_router.get("/public/faqs/{faq_type}")
async def get_public_faqs(faq_type: str):
    """v102: FAQ publiques (partner, general) â sans auth"""
    faqs = await db.public_faqs.find(
        {"type": faq_type, "is_active": {"$ne": False}},
        {"_id": 0}
    ).sort("order", 1).to_list(50)
    return faqs

@api_router.post("/admin/faqs")
async def admin_create_faq(request: Request):
    """v102: SuperAdmin â creer une FAQ publique"""
    email = require_auth(request)
    if not is_super_admin(email):
        raise HTTPException(status_code=403, detail="SuperAdmin requis")
    body = await request.json()
    faq_doc = {
        "id": str(uuid.uuid4()),
        "type": body.get("type", "partner"),
        "question": body.get("question", ""),
        "answer": body.get("answer", ""),
        "order": body.get("order", 0),
        "is_active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.public_faqs.insert_one(faq_doc)
    return faq_doc

@api_router.put("/admin/faqs/{faq_id}")
async def admin_update_faq(faq_id: str, request: Request):
    """v102: SuperAdmin â modifier une FAQ publique"""
    email = require_auth(request)
    if not is_super_admin(email):
        raise HTTPException(status_code=403, detail="SuperAdmin requis")
    body = await request.json()
    update = {}
    for k in ["question", "answer", "order", "is_active", "type"]:
        if k in body: update[k] = body[k]
    if update:
        await db.public_faqs.update_one({"id": faq_id}, {"$set": update})
    return await db.public_faqs.find_one({"id": faq_id}, {"_id": 0})

@api_router.delete("/admin/faqs/{faq_id}")
async def admin_delete_faq(faq_id: str, request: Request):
    """v102: SuperAdmin â supprimer une FAQ publique"""
    email = require_auth(request)
    if not is_super_admin(email):
        raise HTTPException(status_code=403, detail="SuperAdmin requis")
    await db.public_faqs.delete_one({"id": faq_id})
    return {"success": True}

@api_router.get("/coach/faqs/{coach_email}")
async def get_coach_faqs(coach_email: str):
    """RÃ©cupÃ¨re les FAQs publiques d'un coach"""
    faqs = await db.faqs.find(
        {"coach_email": coach_email.lower()},
        {"_id": 0}
    ).sort("order", 1).to_list(50)
    return faqs

@api_router.post("/coach/faq")
async def create_faq(request: Request):
    """CrÃ©er une FAQ"""
    body = await request.json()
    email = require_auth(request)

    faq = {
        "id": f"faq_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{os.urandom(3).hex()}",
        "coach_email": email,
        "question": body.get("question", "").strip(),
        "answer": body.get("answer", "").strip(),
        "category": body.get("category", "general"),
        "order": body.get("order", 0),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    if not faq["question"]:
        raise HTTPException(status_code=400, detail="La question est requise")

    await db.faqs.insert_one(faq)
    faq.pop("_id", None)
    return faq

@api_router.put("/coach/faq/{faq_id}")
async def update_faq(faq_id: str, request: Request):
    """Modifier une FAQ"""
    body = await request.json()
    email = require_auth(request)

    updates = {}
    for field in ["question", "answer", "category", "order"]:
        if field in body:
            updates[field] = body[field]
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    result = await db.faqs.update_one(
        {"id": faq_id, "coach_email": email},
        {"$set": updates}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="FAQ non trouvÃ©e")

    faq = await db.faqs.find_one({"id": faq_id}, {"_id": 0})
    return faq

@api_router.delete("/coach/faq/{faq_id}")
async def delete_faq(faq_id: str, request: Request):
    """Supprimer une FAQ"""
    email = require_auth(request)

    result = await db.faqs.delete_one({"id": faq_id, "coach_email": email})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="FAQ non trouvÃ©e")

    return {"deleted": True}


# --- v17.3: Import Auto Contacts ---
@api_router.post("/contacts/check-duplicates")
async def check_duplicate_contacts(request: Request):
    """VÃ©rifie les doublons dans la liste de contacts importÃ©s"""
    body = await request.json()
    phones = [p.strip() for p in body.get("phones", []) if p.strip()]
    emails = [e.strip().lower() for e in body.get("emails", []) if e.strip()]
    coach_email = require_auth(request)

    existing_phones = set()
    existing_emails = set()

    # v68: Isolation multi-tenant â ne chercher les doublons que dans les contacts du coach
    coach_filter = {} if is_super_admin(coach_email) else {"coach_id": coach_email}

    if phones:
        phone_query = {**coach_filter, "phone": {"$in": phones}}
        cursor = db.chat_participants.find(phone_query, {"_id": 0, "phone": 1})
        async for doc in cursor:
            if doc.get("phone"):
                existing_phones.add(doc["phone"])

    if emails:
        email_query = {**coach_filter, "email": {"$in": emails}}
        cursor = db.chat_participants.find(email_query, {"_id": 0, "email": 1})
        async for doc in cursor:
            if doc.get("email"):
                existing_emails.add(doc["email"].lower())

    return {
        "existing_phones": list(existing_phones),
        "existing_emails": list(existing_emails),
        "total_checked": len(phones) + len(emails)
    }


# ============================================================
# CONTACTS UNIFIÃS â v18: Merge participants + users + groupes
# ============================================================

@api_router.post("/contacts/deduplicate")
async def deduplicate_contacts(request: Request):
    """v104: Nettoie les doublons existants dans chat_participants.
    Fusionne par email (case-insensitive) ou phone normalisÃ©.
    Garde le contact le plus ancien (created_at), met Ã  jour avec les infos des doublons."""
    caller_email = require_auth(request)

    try:
        # RÃ©cupÃ©rer tous les contacts du coach
        query = {} if is_super_admin(caller_email) else {"coach_id": caller_email}
        all_contacts = await db.chat_participants.find(query, {"_id": 0}).to_list(10000)

        # Grouper par email normalisÃ©
        email_groups = {}
        phone_groups = {}
        for c in all_contacts:
            email = (c.get("email") or "").strip().lower()
            phone = (c.get("whatsapp") or c.get("phone") or "").replace(" ", "").replace("-", "").replace("+", "")
            if email:
                email_groups.setdefault(email, []).append(c)
            elif phone:
                phone_groups.setdefault(phone, []).append(c)

        merged = 0
        deleted_ids = []

        # Fusionner les doublons email
        for email, contacts in email_groups.items():
            if len(contacts) <= 1:
                continue
            # Garder le plus ancien
            contacts.sort(key=lambda x: x.get("created_at", ""))
            keeper = contacts[0]
            for dup in contacts[1:]:
                # TransfÃ©rer les infos manquantes du doublon vers le keeper
                updates = {}
                if not keeper.get("whatsapp") and dup.get("whatsapp"):
                    updates["whatsapp"] = dup["whatsapp"]
                if not keeper.get("phone") and dup.get("phone"):
                    updates["phone"] = dup["phone"]
                if not keeper.get("name") or keeper["name"] == "Sans nom":
                    if dup.get("name") and dup["name"] != "Sans nom":
                        updates["name"] = dup["name"]
                # Fusionner tags
                keeper_tags = set(keeper.get("tags", []))
                dup_tags = set(dup.get("tags", []))
                if dup_tags - keeper_tags:
                    updates["tags"] = list(keeper_tags | dup_tags)
                if updates:
                    await db.chat_participants.update_one({"id": keeper["id"]}, {"$set": updates})
                    keeper.update(updates)
                # Supprimer le doublon
                await db.chat_participants.delete_one({"id": dup["id"]})
                deleted_ids.append(dup["id"])
                merged += 1

        # Fusionner les doublons phone (ceux sans email)
        for phone, contacts in phone_groups.items():
            if len(contacts) <= 1:
                continue
            contacts.sort(key=lambda x: x.get("created_at", ""))
            keeper = contacts[0]
            for dup in contacts[1:]:
                updates = {}
                if not keeper.get("email") and dup.get("email"):
                    updates["email"] = dup["email"]
                if not keeper.get("name") or keeper["name"] == "Sans nom":
                    if dup.get("name") and dup["name"] != "Sans nom":
                        updates["name"] = dup["name"]
                keeper_tags = set(keeper.get("tags", []))
                dup_tags = set(dup.get("tags", []))
                if dup_tags - keeper_tags:
                    updates["tags"] = list(keeper_tags | dup_tags)
                if updates:
                    await db.chat_participants.update_one({"id": keeper["id"]}, {"$set": updates})
                    keeper.update(updates)
                await db.chat_participants.delete_one({"id": dup["id"]})
                deleted_ids.append(dup["id"])
                merged += 1

        # Mettre Ã  jour les sessions qui rÃ©fÃ©rencent les contacts supprimÃ©s
        if deleted_ids:
            logger.info(f"[DEDUP] {merged} doublons fusionnÃ©s, IDs supprimÃ©s: {deleted_ids[:10]}...")

        return {
            "success": True,
            "merged": merged,
            "deleted_ids": deleted_ids,
            "total_before": len(all_contacts),
            "total_after": len(all_contacts) - merged
        }
    except Exception as e:
        logger.error(f"[DEDUP] Erreur: {e}")
        return {"success": False, "error": str(e)}

@api_router.get("/contacts/all")
async def get_all_contacts_unified(request: Request):
    """
    Endpoint unifiÃ© qui fusionne chat_participants, users, et groupes
    pour la sÃ©lection de destinataires dans les campagnes.
    DÃ©dupliquÃ© par email/phone. Retourne groupes + contacts individuels.
    """
    caller_email = require_auth(request)

    try:
        contacts = []
        seen_emails = set()
        seen_phones = set()

        # 1. GROUPES â Sessions avec titre ou mode groupe
        sessions = await db.chat_sessions.find(
            {"is_deleted": {"$ne": True}},
            {"_id": 0, "id": 1, "mode": 1, "title": 1, "participant_ids": 1, "updated_at": 1}
        ).sort("updated_at", -1).to_list(500)

        for session in sessions:
            title = (session.get("title") or "").strip()
            mode = session.get("mode", "user")
            if title or mode in ["community", "vip", "promo", "group"]:
                mode_names = {"community": "Communauté", "vip": "VIP", "promo": "Offres Spéciales", "group": "Groupe"}
                contacts.append({
                    "id": session.get("id", ""),
                    "name": title or mode_names.get(mode, f"Groupe {mode}"),
                    "type": "group",
                    "category": mode,
                    "phone": None,
                    "email": None,
                    "source": "session",
                    "member_count": len(session.get("participant_ids", []))
                })

        # Groupes standards si manquants
        existing_ids = set(c["id"] for c in contacts)
        for gid, gname in [("community", "Communauté Générale"), ("vip", "Groupe VIP"), ("promo", "Offres Spéciales")]:
            if gid not in existing_ids:
                contacts.append({
                    "id": gid, "name": gname, "type": "group",
                    "category": gid, "phone": None, "email": None,
                    "source": "default", "member_count": 0
                })

        # v108: Construction d'un index IDâemail pour dÃ©duplication cohÃ©rente
        # chat_participants est la source PRIORITAIRE (CRM du coach)
        seen_ids = set()

        # 2. CHAT_PARTICIPANTS â Contacts CRM (imports, stripe, chat) â SOURCE PRIORITAIRE
        if is_super_admin(caller_email):
            participants = await db.chat_participants.find({}, {"_id": 0}).to_list(5000)
        else:
            participants = await db.chat_participants.find(
                {"coach_id": caller_email}, {"_id": 0}
            ).to_list(5000)

        for p in participants:
            pid = p.get("id", "")
            email = (p.get("email") or "").strip().lower()
            phone = (p.get("whatsapp") or p.get("phone") or "").strip()
            # Dedup par ID d'abord, puis email/phone
            if pid and pid in seen_ids:
                continue
            if email and email in seen_emails:
                continue
            if phone and phone in seen_phones:
                continue
            if pid:
                seen_ids.add(pid)
            if email:
                seen_emails.add(email)
            if phone:
                seen_phones.add(phone)

            contacts.append({
                "id": pid,
                "name": p.get("name") or email or phone or "Sans nom",
                "type": "user",
                "category": p.get("source", "import"),
                "phone": phone or None,
                "email": email or None,
                "source": p.get("source", "import"),
                "tags": p.get("tags", []),
                "categories": p.get("categories", [])
            })

        # 3. USERS â Utilisateurs de l'app (ceux pas dÃ©jÃ  dans participants)
        # v108: Dedup par ID ET email pour Ã©viter les doublons cross-collections
        all_users = await db.users.find({}, {"_id": 0, "id": 1, "name": 1, "email": 1, "created_at": 1}).to_list(5000)
        for u in all_users:
            uid = u.get("id", "")
            email = (u.get("email") or "").strip().lower()
            if uid and uid in seen_ids:
                continue
            if email and email in seen_emails:
                continue
            if uid:
                seen_ids.add(uid)
            if email:
                seen_emails.add(email)
            contacts.append({
                "id": uid,
                "name": u.get("name") or email or "Sans nom",
                "type": "user",
                "category": "app_user",
                "phone": None,
                "email": email or None,
                "source": "app",
                "tags": []
            })

        # Sort: groupes d'abord, puis contacts par nom
        contacts.sort(key=lambda x: (0 if x["type"] == "group" else 1, (x.get("name") or "").lower()))

        groups_count = len([c for c in contacts if c["type"] == "group"])
        users_count = len([c for c in contacts if c["type"] == "user"])

        return {
            "success": True,
            "contacts": contacts,
            "total": len(contacts),
            "groups_count": groups_count,
            "users_count": users_count
        }
    except Exception as e:
        logger.error(f"[CONTACTS-ALL] Erreur: {e}")
        return {"success": False, "contacts": [], "error": str(e)}


@api_router.post("/contacts/bulk-import")
async def bulk_import_contacts(request: Request):
    """
    Import en masse de contacts dans chat_participants.
    Accepte un tableau de {name, phone, email, source, tags}.
    DÃ©duplique par phone/email. Retourne le nombre importÃ©.
    """
    caller_email = require_auth(request)

    body = await request.json()
    contacts_list = body.get("contacts", [])
    source = body.get("source", "import")

    if not contacts_list:
        return {"imported": 0, "duplicates": 0, "errors": 0}

    imported = 0
    duplicates = 0
    errors = 0

    for c in contacts_list:
        try:
            email = (c.get("email") or "").strip().lower()
            phone = (c.get("phone") or c.get("whatsapp") or "").strip()
            name = (c.get("name") or "").strip()

            if not email and not phone:
                errors += 1
                continue

            # Check duplicate
            dup_query = {"$or": []}
            if email:
                dup_query["$or"].append({"email": {"$regex": f"^{email}$", "$options": "i"}})
            if phone:
                clean = phone.replace(" ", "").replace("-", "")
                dup_query["$or"].append({"whatsapp": {"$regex": clean}})
                dup_query["$or"].append({"phone": {"$regex": clean}})

            if dup_query["$or"]:
                existing = await db.chat_participants.find_one(dup_query, {"_id": 0})
                if existing:
                    # Update name if better
                    if name and not existing.get("name"):
                        await db.chat_participants.update_one(
                            {"id": existing["id"]},
                            {"$set": {"name": name, "last_seen_at": datetime.now(timezone.utc).isoformat()}}
                        )
                    duplicates += 1
                    continue

            # Insert new
            new_participant = {
                "id": str(uuid.uuid4()),
                "name": name or email or phone,
                "email": email or None,
                "whatsapp": phone or None,
                "phone": phone or None,
                "source": source,
                "coach_id": caller_email if not is_super_admin(caller_email) else DEFAULT_COACH_ID,
                "tags": c.get("tags", []),
                "categories": c.get("categories", []),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_seen_at": datetime.now(timezone.utc).isoformat()
            }
            await db.chat_participants.insert_one(new_participant)
            imported += 1

        except Exception as err:
            logger.warning(f"[BULK-IMPORT] Erreur contact: {err}")
            errors += 1

    return {
        "success": True,
        "imported": imported,
        "duplicates": duplicates,
        "errors": errors,
        "total_processed": len(contacts_list)
    }


# V146: Suppression en masse de contacts
@api_router.post("/contacts/bulk-delete")
async def bulk_delete_contacts(request: Request):
    """V146: Supprime une liste de contacts par ID (chat_participants + users)."""
    caller_email = require_auth(request)
    body = await request.json()
    contact_ids = body.get("ids", [])

    if not contact_ids or not isinstance(contact_ids, list):
        raise HTTPException(status_code=400, detail="ids (liste) requis")

    deleted_count = 0
    for cid in contact_ids:
        # Supprimer de chat_participants
        r1 = await db.chat_participants.delete_one({"id": cid})
        if r1.deleted_count > 0:
            deleted_count += r1.deleted_count
            continue
        # Fallback: supprimer de users
        r2 = await db.users.delete_one({"id": cid})
        deleted_count += r2.deleted_count

    logger.info(f"[V146] SupprimÃ© {deleted_count}/{len(contact_ids)} contacts par {caller_email}")
    return {"success": True, "deleted": deleted_count, "requested": len(contact_ids)}


# ============================================================
# GOOGLE CONTACTS SYNC â v18: OAuth2 + People API
# ============================================================

GOOGLE_CONTACTS_CLIENT_ID = os.environ.get("GOOGLE_CONTACTS_CLIENT_ID", "")
GOOGLE_CONTACTS_CLIENT_SECRET = os.environ.get("GOOGLE_CONTACTS_CLIENT_SECRET", "")
GOOGLE_CONTACTS_SCOPES = "https://www.googleapis.com/auth/contacts.readonly"

@api_router.get("/google-contacts/auth-url")
async def get_google_contacts_auth_url(request: Request):
    """GÃ©nÃ¨re l'URL d'autorisation Google pour la sync contacts"""
    caller_email = require_auth(request)

    if not GOOGLE_CONTACTS_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google Contacts non configurÃ© (GOOGLE_CONTACTS_CLIENT_ID manquant)")

    # Redirect URI = notre callback
    base_url = os.environ.get("VERCEL_URL", "afroboost-v11-dev-pm7l.vercel.app")
    redirect_uri = f"https://{base_url}/api/google-contacts/callback"

    import urllib.parse
    params = urllib.parse.urlencode({
        "client_id": GOOGLE_CONTACTS_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_CONTACTS_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": caller_email  # Pour identifier le coach
    })

    return {
        "auth_url": f"https://accounts.google.com/o/oauth2/v2/auth?{params}",
        "configured": True
    }


@api_router.get("/google-contacts/callback")
async def google_contacts_callback(code: str = "", state: str = "", error: str = ""):
    """Callback OAuth2 Google â Ã©change le code contre un token"""
    from fastapi.responses import HTMLResponse
    import httpx

    if error:
        return HTMLResponse(f"<html><body><h2>Erreur: {error}</h2><script>window.close()</script></body></html>")

    if not code or not state:
        return HTMLResponse("<html><body><h2>Code manquant</h2><script>window.close()</script></body></html>")

    coach_email = state.lower().strip()
    base_url = os.environ.get("VERCEL_URL", "afroboost-v11-dev-pm7l.vercel.app")
    redirect_uri = f"https://{base_url}/api/google-contacts/callback"

    try:
        # Exchange code for tokens
        async with httpx.AsyncClient() as client:
            token_resp = await client.post("https://oauth2.googleapis.com/token", data={
                "client_id": GOOGLE_CONTACTS_CLIENT_ID,
                "client_secret": GOOGLE_CONTACTS_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri
            })
            tokens = token_resp.json()

        if "error" in tokens:
            return HTMLResponse(f"<html><body><h2>Erreur token: {tokens.get('error_description', tokens['error'])}</h2><script>setTimeout(()=>window.close(),3000)</script></body></html>")

        # Store refresh token for the coach
        await db.google_tokens.update_one(
            {"coach_email": coach_email},
            {"$set": {
                "coach_email": coach_email,
                "access_token": tokens.get("access_token"),
                "refresh_token": tokens.get("refresh_token"),
                "expires_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )

        return HTMLResponse("""
        <html><body style="background:#1a1025;color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
        <div style="text-align:center">
            <h2 style="color:#22c55e">â Google Contacts connectÃ© !</h2>
            <p>Vous pouvez fermer cette fenÃªtre et cliquer sur "Synchroniser".</p>
            <script>setTimeout(()=>window.close(),2000)</script>
        </div>
        </body></html>
        """)

    except Exception as e:
        logger.error(f"[GOOGLE-CONTACTS] Callback error: {e}")
        return HTMLResponse(f"<html><body><h2>Erreur: {str(e)}</h2><script>setTimeout(()=>window.close(),3000)</script></body></html>")


@api_router.get("/google-contacts/status")
async def google_contacts_status(request: Request):
    """VÃ©rifie si le coach a connectÃ© Google Contacts"""
    try:
        caller_email = require_auth(request)
    except HTTPException:
        caller_email = ""
    token_doc = await db.google_tokens.find_one({"coach_email": caller_email}, {"_id": 0})
    return {
        "connected": bool(token_doc and token_doc.get("refresh_token")),
        "last_sync": token_doc.get("last_sync") if token_doc else None,
        "configured": bool(GOOGLE_CONTACTS_CLIENT_ID)
    }


@api_router.post("/google-contacts/sync")
async def sync_google_contacts(request: Request):
    """
    Synchronise les contacts Google dans chat_participants.
    Utilise le refresh_token stockÃ© pour obtenir un access_token frais.
    """
    caller_email = require_auth(request)

    token_doc = await db.google_tokens.find_one({"coach_email": caller_email}, {"_id": 0})
    if not token_doc or not token_doc.get("refresh_token"):
        raise HTTPException(status_code=400, detail="Google non connectÃ©. Cliquez sur 'Connecter Google' d'abord.")

    import httpx

    try:
        # 1. Refresh the access token
        async with httpx.AsyncClient() as client:
            token_resp = await client.post("https://oauth2.googleapis.com/token", data={
                "client_id": GOOGLE_CONTACTS_CLIENT_ID,
                "client_secret": GOOGLE_CONTACTS_CLIENT_SECRET,
                "refresh_token": token_doc["refresh_token"],
                "grant_type": "refresh_token"
            })
            tokens = token_resp.json()

        if "error" in tokens:
            raise HTTPException(status_code=400, detail=f"Token refresh failed: {tokens.get('error_description', tokens['error'])}")

        access_token = tokens["access_token"]

        # 2. Fetch contacts from Google People API (paginated)
        all_contacts = []
        next_page_token = None
        page_count = 0

        async with httpx.AsyncClient() as client:
            while page_count < 10:  # Max 10 pages (10000 contacts)
                params = {
                    "personFields": "names,emailAddresses,phoneNumbers",
                    "pageSize": 1000,
                    "sources": "READ_SOURCE_TYPE_CONTACT"
                }
                if next_page_token:
                    params["pageToken"] = next_page_token

                resp = await client.get(
                    "https://people.googleapis.com/v1/people/me/connections",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params=params
                )

                if resp.status_code != 200:
                    logger.error(f"[GOOGLE-SYNC] API error: {resp.status_code} {resp.text[:200]}")
                    break

                data = resp.json()
                connections = data.get("connections", [])

                for person in connections:
                    names = person.get("names", [])
                    emails = person.get("emailAddresses", [])
                    phones = person.get("phoneNumbers", [])

                    name = names[0].get("displayName", "") if names else ""
                    email = emails[0].get("value", "") if emails else ""
                    phone = phones[0].get("value", "") if phones else ""

                    if email or phone:
                        all_contacts.append({
                            "name": name,
                            "email": email.lower().strip() if email else None,
                            "phone": phone.strip() if phone else None,
                            "source": "google",
                            "tags": ["google"]
                        })

                next_page_token = data.get("nextPageToken")
                if not next_page_token:
                    break
                page_count += 1

        # 3. Bulk import with dedup
        imported = 0
        duplicates = 0

        for c in all_contacts:
            email = c.get("email")
            phone = c.get("phone")

            dup_query = {"$or": []}
            if email:
                dup_query["$or"].append({"email": {"$regex": f"^{email}$", "$options": "i"}})
            if phone:
                clean = (phone or "").replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
                if clean:
                    dup_query["$or"].append({"whatsapp": {"$regex": clean}})
                    dup_query["$or"].append({"phone": {"$regex": clean}})

            if dup_query["$or"]:
                existing = await db.chat_participants.find_one(dup_query, {"_id": 0, "id": 1})
                if existing:
                    duplicates += 1
                    continue

            await db.chat_participants.insert_one({
                "id": str(uuid.uuid4()),
                "name": c["name"] or c["email"] or c["phone"],
                "email": c.get("email"),
                "whatsapp": c.get("phone"),
                "phone": c.get("phone"),
                "source": "google",
                "coach_id": caller_email if not is_super_admin(caller_email) else DEFAULT_COACH_ID,
                "tags": ["google"],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_seen_at": datetime.now(timezone.utc).isoformat()
            })
            imported += 1

        # Update last sync time
        await db.google_tokens.update_one(
            {"coach_email": caller_email},
            {"$set": {"last_sync": datetime.now(timezone.utc).isoformat()}}
        )

        return {
            "success": True,
            "imported": imported,
            "duplicates": duplicates,
            "total_google": len(all_contacts),
            "message": f"â {imported} nouveaux contacts importÃ©s ({duplicates} doublons ignorÃ©s)"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GOOGLE-SYNC] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/contacts/add-tags")
async def add_tags_to_contacts(request: Request):
    """Ajoute des tags Ã  une liste de contacts (pour grouper/catÃ©goriser)"""
    try:
        caller_email = require_auth(request)
    except HTTPException:
        caller_email = ""
    body = await request.json()
    contact_ids = body.get("contact_ids", [])
    tags = body.get("tags", [])

    if not contact_ids or not tags:
        return {"updated": 0}

    updated = 0
    for cid in contact_ids:
        result = await db.chat_participants.update_one(
            {"id": cid},
            {"$addToSet": {"tags": {"$each": tags}}}
        )
        if result.modified_count:
            updated += 1

    return {"success": True, "updated": updated}


# --- Config ---
@api_router.get("/config", response_model=AppConfig)
async def get_config():
    config = await db.config.find_one({"id": "app_config"}, {"_id": 0})
    if not config:
        default_config = AppConfig().model_dump()
        await db.config.insert_one(default_config)
        return default_config
    return config

@api_router.put("/config")
async def update_config(config_update: dict):
    await db.config.update_one({"id": "app_config"}, {"$set": config_update}, upsert=True)
    return await db.config.find_one({"id": "app_config"}, {"_id": 0})

# === GOOGLE OAUTH AUTHENTICATION ===
# Business: Authentification Google exclusive pour le Super Admin / Coach
# Seul l'email autorisÃ© peut accÃ©der au dashboard

# Email autorisÃ© pour l'accÃ¨s Coach/Super Admin
AUTHORIZED_COACH_EMAIL = os.environ.get("AUTHORIZED_COACH_EMAIL", "contact.artboost@gmail.com")

class GoogleAuthSession(BaseModel):
    """Session d'authentification Google"""
    model_config = ConfigDict(extra="ignore")
    session_id: str
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    session_token: str
    expires_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class GoogleUser(BaseModel):
    """Utilisateur authentifiÃ© via Google"""
    model_config = ConfigDict(extra="ignore")
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    is_coach: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login: Optional[datetime] = None

# === v9.1.9: Routes auth dÃ©placÃ©es vers routes/auth_routes.py ===
# Les routes suivantes ont Ã©tÃ© extraites pour modularisation :
# - POST /auth/google/session
# - GET /auth/me
# - POST /auth/logout
# - GET /coach-auth
# - POST /coach-auth/login

# === FEATURE FLAGS API (Super Admin Only) ===
# Business: Seul le Super Admin peut activer/dÃ©sactiver les services globaux

@api_router.get("/feature-flags")
async def get_feature_flags():
    """
    RÃ©cupÃ¨re la configuration des feature flags
    Par dÃ©faut, tous les services additionnels sont dÃ©sactivÃ©s
    """
    flags = await db.feature_flags.find_one({"id": "feature_flags"}, {"_id": 0})
    if not flags:
        # CrÃ©er la config par dÃ©faut (tout dÃ©sactivÃ©)
        default_flags = {
            "id": "feature_flags",
            "AUDIO_SERVICE_ENABLED": False,
            "VIDEO_SERVICE_ENABLED": False,
            "STREAMING_SERVICE_ENABLED": False,
            "updatedAt": None,
            "updatedBy": None
        }
        await db.feature_flags.insert_one(default_flags.copy())  # .copy() pour Ã©viter mutation
        # Retourner sans _id
        return {k: v for k, v in default_flags.items() if k != "_id"}
    return flags

@api_router.put("/feature-flags")
async def update_feature_flags(update: FeatureFlagsUpdate):
    """
    Met Ã  jour les feature flags (Super Admin only)
    TODO: Ajouter authentification Super Admin
    """
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    update_data["updatedAt"] = datetime.now(timezone.utc).isoformat()
    update_data["updatedBy"] = "super_admin"  # TODO: RÃ©cupÃ©rer depuis le token
    
    await db.feature_flags.update_one(
        {"id": "feature_flags"}, 
        {"$set": update_data}, 
        upsert=True
    )
    return await db.feature_flags.find_one({"id": "feature_flags"}, {"_id": 0})

# === COACH SUBSCRIPTION API ===
# Business: Gestion des abonnements et droits des coachs

@api_router.get("/coach-subscription")
async def get_coach_subscription():
    """
    RÃ©cupÃ¨re l'abonnement du coach actuel
    Utilise l'email de coach_auth pour trouver l'abonnement correspondant
    """
    # RÃ©cupÃ©rer l'email du coach actuel
    coach_auth = await db.coach_auth.find_one({"id": "coach_auth"}, {"_id": 0})
    if not coach_auth:
        return {"error": "Coach auth not found"}
    
    coach_email = coach_auth.get("email", "coach@afroboost.com")
    
    # Chercher l'abonnement correspondant
    subscription = await db.coach_subscriptions.find_one(
        {"coachEmail": coach_email}, 
        {"_id": 0}
    )
    
    if not subscription:
        # CrÃ©er un abonnement par dÃ©faut (free, sans services additionnels)
        default_sub = {
            "id": str(uuid.uuid4()),
            "coachEmail": coach_email,
            "hasAudioService": False,
            "hasVideoService": False,
            "hasStreamingService": False,
            "subscriptionPlan": "free",
            "subscriptionStartDate": datetime.now(timezone.utc).isoformat(),
            "subscriptionEndDate": None,
            "isActive": True,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "updatedAt": None
        }
        await db.coach_subscriptions.insert_one(default_sub.copy())  # .copy() pour Ã©viter mutation
        # Retourner sans _id
        return {k: v for k, v in default_sub.items() if k != "_id"}
    
    return subscription

@api_router.put("/coach-subscription")
async def update_coach_subscription(update: CoachSubscriptionUpdate):
    """
    Met Ã  jour l'abonnement du coach
    TODO: Ajouter vÃ©rification Super Admin pour modifications sensibles
    """
    coach_auth = await db.coach_auth.find_one({"id": "coach_auth"}, {"_id": 0})
    if not coach_auth:
        raise HTTPException(status_code=404, detail="Coach auth not found")
    
    coach_email = coach_auth.get("email", "coach@afroboost.com")
    
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    update_data["updatedAt"] = datetime.now(timezone.utc).isoformat()
    
    await db.coach_subscriptions.update_one(
        {"coachEmail": coach_email},
        {"$set": update_data},
        upsert=True
    )
    
    return await db.coach_subscriptions.find_one({"coachEmail": coach_email}, {"_id": 0})

# === SERVICE ACCESS VERIFICATION ===
# Business: Fonction centrale pour vÃ©rifier l'accÃ¨s aux services

@api_router.get("/verify-service-access/{service_name}")
async def verify_service_access(service_name: str):
    """
    VÃ©rifie si un service est accessible pour le coach actuel.
    
    Logique de vÃ©rification (BOTH conditions must be true):
    1. Feature flag global activÃ© (Super Admin)
    2. Coach a l'abonnement correspondant
    
    Args:
        service_name: "audio", "video", "streaming"
    
    Returns:
        {
            "hasAccess": bool,
            "reason": str,
            "featureFlagEnabled": bool,
            "coachHasSubscription": bool
        }
    """
    # Mapper les noms de service aux champs
    service_map = {
        "audio": ("AUDIO_SERVICE_ENABLED", "hasAudioService"),
        "video": ("VIDEO_SERVICE_ENABLED", "hasVideoService"),
        "streaming": ("STREAMING_SERVICE_ENABLED", "hasStreamingService")
    }
    
    if service_name not in service_map:
        raise HTTPException(status_code=400, detail=f"Service inconnu: {service_name}")
    
    flag_field, sub_field = service_map[service_name]
    
    # 1. VÃ©rifier le feature flag global
    flags = await db.feature_flags.find_one({"id": "feature_flags"}, {"_id": 0})
    feature_enabled = flags.get(flag_field, False) if flags else False
    
    # 2. VÃ©rifier l'abonnement du coach
    coach_auth = await db.coach_auth.find_one({"id": "coach_auth"}, {"_id": 0})
    coach_email = coach_auth.get("email", "coach@afroboost.com") if coach_auth else "coach@afroboost.com"
    
    subscription = await db.coach_subscriptions.find_one({"coachEmail": coach_email}, {"_id": 0})
    coach_has_service = subscription.get(sub_field, False) if subscription else False
    
    # DÃ©terminer l'accÃ¨s et la raison
    has_access = feature_enabled and coach_has_service
    
    if not feature_enabled:
        reason = f"Service {service_name} dÃ©sactivÃ© globalement (contacter l'administrateur)"
    elif not coach_has_service:
        reason = f"Votre abonnement n'inclut pas le service {service_name}"
    else:
        reason = "AccÃ¨s autorisÃ©"
    
    return {
        "hasAccess": has_access,
        "reason": reason,
        "featureFlagEnabled": feature_enabled,
        "coachHasSubscription": coach_has_service,
        "service": service_name
    }

# === EMAILJS CONFIG (MongoDB) ===

class EmailJSConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = "emailjs_config"
    serviceId: str = ""
    templateId: str = ""
    publicKey: str = ""

class EmailJSConfigUpdate(BaseModel):
    serviceId: Optional[str] = None
    templateId: Optional[str] = None
    publicKey: Optional[str] = None

@api_router.get("/emailjs-config")
async def get_emailjs_config():
    config = await db.emailjs_config.find_one({"id": "emailjs_config"}, {"_id": 0})
    if not config:
        return {"id": "emailjs_config", "serviceId": "", "templateId": "", "publicKey": ""}
    return config

@api_router.put("/emailjs-config")
async def update_emailjs_config(config: EmailJSConfigUpdate):
    updates = {k: v for k, v in config.model_dump().items() if v is not None}
    updates["id"] = "emailjs_config"
    await db.emailjs_config.update_one({"id": "emailjs_config"}, {"$set": updates}, upsert=True)
    return await db.emailjs_config.find_one({"id": "emailjs_config"}, {"_id": 0})

# === WHATSAPP CONFIG (MongoDB) ===

class WhatsAppConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = "whatsapp_config"
    accountSid: str = ""
    authToken: str = ""
    fromNumber: str = ""
    apiMode: str = "twilio"

class WhatsAppConfigUpdate(BaseModel):
    accountSid: Optional[str] = None
    authToken: Optional[str] = None
    fromNumber: Optional[str] = None
    apiMode: Optional[str] = None

@api_router.get("/whatsapp-config")
async def get_whatsapp_config():
    config = await db.whatsapp_config.find_one({"id": "whatsapp_config"}, {"_id": 0})
    if not config:
        return {"id": "whatsapp_config", "accountSid": "", "authToken": "", "fromNumber": "", "apiMode": "twilio"}
    return config

# V118: Endpoint pour rÃ©cupÃ©rer le mode WhatsApp actuel
@api_router.get("/whatsapp-mode")
async def get_whatsapp_mode():
    """
    V118: Retourne le mode WhatsApp actuel (meta / production / sandbox).
    """
    sender_number, mode = await _get_whatsapp_sender()
    meta_token, meta_phone_id = await _get_meta_config()
    return {
        "mode": mode,  # "meta" | "production" | "sandbox"
        "engine": "meta" if mode == "meta" else "twilio",
        "senderNumber": sender_number,
        "sandboxNumber": TWILIO_SANDBOX_NUMBER,
        "productionNumber": TWILIO_PRODUCTION_NUMBER,
        "metaConfigured": bool(meta_token and meta_phone_id),
        "sandboxJoinCode": "join everyone-goes" if mode == "sandbox" else None,
        "needsRegistration": mode == "sandbox"
    }

# V115: Endpoint pour enregistrer un sender WhatsApp vÃ©rifiÃ©
@api_router.put("/whatsapp-sender")
async def set_whatsapp_sender(data: dict):
    """
    V115: Enregistre le numÃ©ro WhatsApp sender vÃ©rifiÃ© sur Twilio.
    Une fois enregistrÃ©, le systÃ¨me bascule automatiquement en mode production.
    """
    registered_sender = data.get("registeredSender", "")
    if not registered_sender:
        raise HTTPException(status_code=400, detail="registeredSender requis")

    await db.whatsapp_config.update_one(
        {"id": "whatsapp_config"},
        {"$set": {"registeredSender": registered_sender, "updatedAt": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )
    logger.info(f"[WHATSAPP-V115] â Sender production enregistrÃ©: {registered_sender}")
    return {"status": "ok", "registeredSender": registered_sender, "mode": "production"}

# V118: Configuration Meta Cloud API WhatsApp
@api_router.get("/meta-whatsapp-config")
async def get_meta_whatsapp_config():
    """V118: RÃ©cupÃ¨re la config Meta WhatsApp (sans exposer le token complet)."""
    config = await db.meta_whatsapp_config.find_one({"id": "meta_whatsapp_config"}, {"_id": 0})
    if not config:
        return {"id": "meta_whatsapp_config", "configured": False, "phoneNumberId": "", "displayNumber": "", "tokenSet": False}
    token = config.get("accessToken", "")
    return {
        "id": "meta_whatsapp_config",
        "configured": bool(token and config.get("phoneNumberId")),
        "phoneNumberId": config.get("phoneNumberId", ""),
        "displayNumber": config.get("displayNumber", ""),
        "businessName": config.get("businessName", ""),
        "tokenSet": bool(token),
        "tokenPreview": f"{token[:8]}...{token[-4:]}" if len(token) > 12 else ("***" if token else ""),
        "updatedAt": config.get("updatedAt", "")
    }

@api_router.put("/meta-whatsapp-config")
async def update_meta_whatsapp_config(data: dict):
    """V118: Sauvegarde la config Meta Cloud API WhatsApp du Super Admin."""
    access_token = data.get("accessToken", "")
    phone_number_id = data.get("phoneNumberId", "")
    display_number = data.get("displayNumber", "+41765203363")
    business_name = data.get("businessName", "Afroboost")

    if not access_token or not phone_number_id:
        raise HTTPException(status_code=400, detail="accessToken et phoneNumberId requis")

    await db.meta_whatsapp_config.update_one(
        {"id": "meta_whatsapp_config"},
        {"$set": {
            "id": "meta_whatsapp_config",
            "accessToken": access_token,
            "phoneNumberId": phone_number_id,
            "displayNumber": display_number,
            "businessName": business_name,
            "updatedAt": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )
    logger.info(f"[META-V118] â Config Meta WhatsApp sauvegardÃ©e â phoneNumberId={phone_number_id}")
    return {"status": "ok", "configured": True, "mode": "meta"}

@api_router.post("/meta-whatsapp-test")
async def test_meta_whatsapp():
    """V118: Envoie un message test 'Hello Afroboost' via Meta Cloud API au numÃ©ro du Super Admin."""
    meta_token, meta_phone_id = await _get_meta_config()
    if not meta_token or not meta_phone_id:
        raise HTTPException(status_code=400, detail="Meta Cloud API non configurÃ©e. Renseignez d'abord vos clÃ©s.")

    # RÃ©cupÃ©rer le numÃ©ro du Super Admin
    meta_cfg = await db.meta_whatsapp_config.find_one({"id": "meta_whatsapp_config"}, {"_id": 0})
    test_number = (meta_cfg or {}).get("displayNumber", "+41765203363")

    result = await send_whatsapp_meta(
        to_phone=test_number,
        message="â Hello Afroboost ! Votre configuration WhatsApp Meta Cloud API fonctionne parfaitement. ð",
        campaign_id="meta_test",
        campaign_name="Test Meta Config"
    )

    if result.get("status") == "success":
        return {"status": "ok", "message": f"Message test envoyÃ© Ã  {test_number}", "wamid": result.get("sid")}
    else:
        raise HTTPException(status_code=502, detail=f"Ãchec envoi test: {result.get('error', 'Erreur inconnue')}")

@api_router.delete("/meta-whatsapp-config")
async def delete_meta_whatsapp_config():
    """V118: Supprime la config Meta et rebascule sur Twilio."""
    await db.meta_whatsapp_config.delete_one({"id": "meta_whatsapp_config"})
    logger.info("[META-V118] ðï¸ Config Meta WhatsApp supprimÃ©e â retour Twilio")
    return {"status": "ok", "mode": "twilio"}

@api_router.put("/whatsapp-config")
async def update_whatsapp_config(config: WhatsAppConfigUpdate):
    updates = {k: v for k, v in config.model_dump().items() if v is not None}
    updates["id"] = "whatsapp_config"
    await db.whatsapp_config.update_one({"id": "whatsapp_config"}, {"$set": updates}, upsert=True)
    return await db.whatsapp_config.find_one({"id": "whatsapp_config"}, {"_id": 0})

# === DATA MIGRATION (localStorage -> MongoDB) ===

class MigrationData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    emailJSConfig: Optional[dict] = None
    whatsAppConfig: Optional[dict] = None
    aiConfig: Optional[dict] = None
    reservations: Optional[List[dict]] = None
    coachAuth: Optional[dict] = None

@api_router.post("/migrate-data")
async def migrate_localstorage_to_mongodb(data: MigrationData):
    """
    Endpoint pour migrer les donnÃ©es du localStorage vers MongoDB.
    AppelÃ© une seule fois lors de la premiÃ¨re utilisation aprÃ¨s la migration.
    """
    migrated = {"emailJS": False, "whatsApp": False, "ai": False, "reservations": 0, "coachAuth": False}
    
    # Migration EmailJS Config
    if data.emailJSConfig and data.emailJSConfig.get("serviceId"):
        existing = await db.emailjs_config.find_one({"id": "emailjs_config"})
        if not existing or not existing.get("serviceId"):
            await db.emailjs_config.update_one(
                {"id": "emailjs_config"}, 
                {"$set": {**data.emailJSConfig, "id": "emailjs_config"}}, 
                upsert=True
            )
            migrated["emailJS"] = True
    
    # Migration WhatsApp Config
    if data.whatsAppConfig and data.whatsAppConfig.get("accountSid"):
        existing = await db.whatsapp_config.find_one({"id": "whatsapp_config"})
        if not existing or not existing.get("accountSid"):
            await db.whatsapp_config.update_one(
                {"id": "whatsapp_config"}, 
                {"$set": {**data.whatsAppConfig, "id": "whatsapp_config"}}, 
                upsert=True
            )
            migrated["whatsApp"] = True
    
    # Migration AI Config
    if data.aiConfig and data.aiConfig.get("systemPrompt"):
        existing = await db.ai_config.find_one({"id": "ai_config"})
        if not existing or not existing.get("systemPrompt"):
            await db.ai_config.update_one(
                {"id": "ai_config"}, 
                {"$set": {**data.aiConfig, "id": "ai_config"}}, 
                upsert=True
            )
            migrated["ai"] = True
    
    # Migration Reservations
    if data.reservations:
        for res in data.reservations:
            if res.get("reservationCode"):
                existing = await db.reservations.find_one({"reservationCode": res["reservationCode"]})
                if not existing:
                    await db.reservations.insert_one(res)
                    migrated["reservations"] += 1
    
    # Migration Coach Auth
    if data.coachAuth:
        existing = await db.coach_auth.find_one({"id": "coach_auth"})
        if not existing:
            await db.coach_auth.update_one(
                {"id": "coach_auth"}, 
                {"$set": {**data.coachAuth, "id": "coach_auth"}}, 
                upsert=True
            )
            migrated["coachAuth"] = True
    
    logger.info(f"Migration completed: {migrated}")
    return {"success": True, "migrated": migrated}

@api_router.get("/migration-status")
async def get_migration_status():
    """VÃ©rifie si les donnÃ©es ont Ã©tÃ© migrÃ©es vers MongoDB"""
    emailjs = await db.emailjs_config.find_one({"id": "emailjs_config"}, {"_id": 0})
    whatsapp = await db.whatsapp_config.find_one({"id": "whatsapp_config"}, {"_id": 0})
    ai = await db.ai_config.find_one({"id": "ai_config"}, {"_id": 0})
    reservations_count = await db.reservations.count_documents({})
    
    return {
        "emailJS": bool(emailjs and emailjs.get("serviceId")),
        "whatsApp": bool(whatsapp and whatsapp.get("accountSid")),
        "ai": bool(ai and ai.get("systemPrompt")),
        "reservationsCount": reservations_count,
        "migrationComplete": True
    }

# === AI WHATSAPP AGENT ===

class AIConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = "ai_config"
    enabled: bool = False
    systemPrompt: str = """Tu es l'assistant virtuel d'Afroboost, une expÃ©rience fitness unique combinant cardio, danse afrobeat et casques audio immersifs.

Ton rÃ´le:
- RÃ©pondre aux questions sur les cours, les offres et les rÃ©servations
- Ãtre chaleureux, dynamique et motivant comme un coach fitness
- Utiliser un ton amical et des emojis appropriÃ©s
- Personnaliser les rÃ©ponses avec le prÃ©nom du client quand disponible

Si tu ne connais pas la rÃ©ponse, oriente vers le contact: contact.artboost@gmail.com"""
    model: str = "gpt-4o-mini"
    provider: str = "openai"
    lastMediaUrl: str = ""
    twintPaymentUrl: str = ""  # Lien de paiement Twint direct pour les ventes
    campaignPrompt: str = ""  # Prompt Campagne PRIORITAIRE - AjoutÃ© Ã  la fin du contexte

class AIConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    systemPrompt: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    lastMediaUrl: Optional[str] = None
    twintPaymentUrl: Optional[str] = None  # Lien de paiement Twint direct
    campaignPrompt: Optional[str] = None  # Prompt Campagne PRIORITAIRE

class AILog(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    fromPhone: str
    clientName: Optional[str] = None
    incomingMessage: str
    aiResponse: str
    responseTime: float = 0  # En secondes

class WhatsAppWebhook(BaseModel):
    From: str  # whatsapp:+41XXXXXXXXX
    Body: str
    To: Optional[str] = None
    MediaUrl0: Optional[str] = None

# --- AI Config Routes ---
@api_router.get("/ai-config")
async def get_ai_config():
    config = await db.ai_config.find_one({"id": "ai_config"}, {"_id": 0})
    if not config:
        default_config = AIConfig().model_dump()
        await db.ai_config.insert_one(default_config)
        return default_config
    return config

@api_router.put("/ai-config")
async def update_ai_config(config: AIConfigUpdate):
    updates = {k: v for k, v in config.model_dump().items() if v is not None}
    await db.ai_config.update_one({"id": "ai_config"}, {"$set": updates}, upsert=True)
    return await db.ai_config.find_one({"id": "ai_config"}, {"_id": 0})

# --- V107.5: GÃ©nÃ©ration Prompt MaÃ®tre ---
@api_router.post("/ai/generate-master-prompt")
async def generate_master_prompt(request: Request):
    """
    V107.5: GÃ©nÃ¨re un Prompt MaÃ®tre complet en agrÃ©geant toutes les donnÃ©es de la plateforme:
    - Concept/description du site
    - Cours disponibles (noms, dates, horaires, lieux, prix)
    - Offres et tarifs (abonnements, produits)
    - Promotions actives
    - Articles de blog
    - Page partenaire (si existante)
    Retourne le prompt gÃ©nÃ©rÃ© prÃªt Ã  Ãªtre sauvegardÃ© dans ai_config.systemPrompt
    """
    try:
        try:
            user_email = require_auth(request)
        except HTTPException:
            user_email = ""

        # 1. Concept / Description du site
        concept_text = ""
        try:
            concept = await db.concept.find_one({"id": "concept"}, {"_id": 0})
            if concept and concept.get("description"):
                concept_text = concept["description"][:800]
        except Exception as e:
            logger.warning(f"[V133] Erreur chargement concept: {e}")

        # 2. Cours disponibles
        courses_text = ""
        try:
            courses = await db.courses.find({"archived": {"$ne": True}, "visible": {"$ne": False}}, {"_id": 0}).to_list(30)
            if courses:
                lines = []
                for c in courses:
                    line = f"- {c.get('name', 'Cours')}"
                    if c.get('date'): line += f" | Date: {c['date']}"
                    if c.get('time'): line += f" | Heure: {c['time']}"
                    if c.get('location') or c.get('locationName'): line += f" | Lieu: {c.get('location') or c.get('locationName')}"
                    if c.get('price'): line += f" | Prix: {c['price']} CHF"
                    if c.get('description'): line += f"\n  Description: {c['description'][:150]}"
                    lines.append(line)
                courses_text = "\n".join(lines)
        except Exception as e:
            logger.warning(f"[V133] Erreur chargement courses: {e}")

        # 3. Offres (services + produits)
        offers_text = ""
        try:
            all_offers = await db.offers.find({"visible": {"$ne": False}}, {"_id": 0}).to_list(50)
            if all_offers:
                products = [o for o in all_offers if o.get('isProduct')]
                services = [o for o in all_offers if not o.get('isProduct')]
                lines = []
                if services:
                    lines.append("ABONNEMENTS & SERVICES:")
                    for s in services:
                        l = f"- {s.get('name', 'Offre')} : {s.get('price', 0)} CHF"
                        if s.get('description'): l += f" â {s['description'][:120]}"
                        if s.get('duration_value') and s.get('duration_unit'):
                            l += f" (DurÃ©e: {s['duration_value']} {s['duration_unit']})"
                        lines.append(l)
                if products:
                    lines.append("\nPRODUITS BOUTIQUE:")
                    for p in products:
                        l = f"- {p.get('name', 'Produit')} : {p.get('price', 0)} CHF"
                        if p.get('description'): l += f" â {p['description'][:120]}"
                        if p.get('category'): l += f" [CatÃ©gorie: {p['category']}]"
                        stock = p.get('stock', -1)
                        if stock >= 0: l += f" (Stock: {stock})"
                        lines.append(l)
                offers_text = "\n".join(lines)
        except Exception as e:
            logger.warning(f"[V133] Erreur chargement offres: {e}")

        # 4. Promotions actives (UNIQUEMENT les promos publiques, pas les codes internes)
        promos_text = ""
        try:
            promos = await db.discount_codes.find({"active": True}, {"_id": 0}).to_list(20)
            if promos:
                lines = []
                for p in promos:
                    # Ignorer les codes assignÃ©s Ã  un email spÃ©cifique (codes internes Stripe)
                    if p.get('assignedEmail'):
                        continue
                    # Ignorer les codes Ã  usage unique dÃ©jÃ  utilisÃ©s
                    if p.get('maxUses') and p.get('used', 0) >= p.get('maxUses', 1):
                        continue
                    ptype = p.get('type', '%')
                    pvalue = p.get('value', 0)
                    label = f"{pvalue}%" if ptype == '%' else f"{pvalue} CHF de rÃ©duction"
                    line = f"- {label}"
                    if p.get('expiresAt'):
                        line += f" (expire le {p['expiresAt'][:10]})"
                    lines.append(line)
                if lines:
                    promos_text = "\n".join(lines)
        except Exception as e:
            logger.warning(f"[V133] Erreur chargement promos: {e}")

        # 5. Articles de blog
        articles_text = ""
        try:
            articles = await db.articles.find({"visible": {"$ne": False}}, {"_id": 0}).sort("created_at", -1).to_list(10)
            if articles:
                lines = []
                for a in articles:
                    l = f"- {a.get('title', 'Article')}"
                    if a.get('summary'): l += f": {a['summary'][:100]}"
                    elif a.get('content'): l += f": {a['content'][:100]}"
                    lines.append(l)
                articles_text = "\n".join(lines)
        except Exception as e:
            logger.warning(f"[V133] Erreur chargement articles: {e}")

        # 6. Page partenaire (sales page)
        partner_text = ""
        try:
            partner = await db.partner_pages.find_one({"coach_email": user_email}, {"_id": 0})
            if partner:
                if partner.get('title'): partner_text += f"Titre: {partner['title']}\n"
                if partner.get('subtitle'): partner_text += f"Sous-titre: {partner['subtitle']}\n"
                if partner.get('description'): partner_text += f"Description: {partner['description'][:300]}\n"
                if partner.get('features'):
                    partner_text += "Points forts: " + ", ".join(partner['features'][:5]) + "\n"
        except Exception as e:
            logger.warning(f"[V133] Erreur chargement partner page: {e}")

        # Assembler le Prompt MaÃ®tre
        prompt = f"""Tu es l'assistant virtuel d'Afroboost, une expÃ©rience fitness unique combinant cardio, danse afrobeat et casques audio immersifs.

TON RÃLE:
- RÃ©pondre aux questions sur les cours, les offres, les rÃ©servations et la boutique
- Ãtre chaleureux, dynamique et motivant comme un coach fitness
- Utiliser un ton amical et des emojis appropriÃ©s
- Personnaliser les rÃ©ponses avec le prÃ©nom du client quand disponible
- Encourager la rÃ©servation et l'achat quand c'est pertinent
- Ne JAMAIS inventer d'informations â utilise UNIQUEMENT les donnÃ©es ci-dessous"""

        if concept_text:
            prompt += f"""

Ã PROPOS D'AFROBOOST:
{concept_text}"""

        if courses_text:
            prompt += f"""

COURS DISPONIBLES:
{courses_text}"""
        else:
            prompt += "\n\nCOURS: Aucun cours programmÃ© actuellement. Invite le client Ã  suivre nos rÃ©seaux pour les prochaines dates."

        if offers_text:
            prompt += f"""

OFFRES ET TARIFS:
{offers_text}"""

        if promos_text:
            prompt += f"""

PROMOTIONS EN COURS:
{promos_text}
Note: Ne communique JAMAIS les codes promo directement. Indique seulement qu'une promotion existe."""

        if articles_text:
            prompt += f"""

ARTICLES / BLOG:
{articles_text}"""

        if partner_text:
            prompt += f"""

PAGE PARTENAIRE:
{partner_text}"""

        prompt += f"""

CONTACT: contact.artboost@gmail.com
SITE: https://www.afroboost.com

Si tu ne connais pas la rÃ©ponse Ã  une question, oriente vers le contact email ou WhatsApp."""

        return {"success": True, "prompt": prompt}

    except Exception as e:
        logger.error(f"[V107.5] Erreur gÃ©nÃ©ration Prompt MaÃ®tre: {e}")
        return {"success": False, "error": str(e)}

# --- AI Logs Routes ---
@api_router.get("/ai-logs")
async def get_ai_logs():
    logs = await db.ai_logs.find({}, {"_id": 0}).sort("timestamp", -1).to_list(50)
    return logs

@api_router.delete("/ai-logs")
async def clear_ai_logs():
    await db.ai_logs.delete_many({})
    return {"success": True}

# --- WhatsApp Webhook (Twilio) ---
@api_router.post("/webhook/whatsapp")
async def handle_whatsapp_webhook(webhook: WhatsAppWebhook):
    """
    Webhook pour recevoir les messages WhatsApp entrants via Twilio
    RÃ©pond automatiquement avec l'IA si activÃ©e
    """
    import time
    start_time = time.time()
    
    # RÃ©cupÃ©rer la config IA
    ai_config = await db.ai_config.find_one({"id": "ai_config"}, {"_id": 0})
    if not ai_config or not ai_config.get("enabled"):
        logger.info(f"AI disabled, ignoring message from {webhook.From}")
        return {"status": "ai_disabled"}
    
    # Extraire le numÃ©ro de tÃ©lÃ©phone
    from_phone = webhook.From.replace("whatsapp:", "")
    to_phone = getattr(webhook, 'To', '').replace("whatsapp:", "") if hasattr(webhook, 'To') else ""
    incoming_message = webhook.Body

    logger.info(f"Incoming WhatsApp from {from_phone}: {incoming_message}")

    # V113: Si le message arrive sur le numÃ©ro Business (+41765203363), le stocker dans Conversations
    business_number = "+41765203363"
    is_business_reply = to_phone.replace(" ", "").replace("-", "") == business_number or not to_phone
    if is_business_reply:
        try:
            normalized = from_phone.replace("+", "").replace(" ", "").replace("-", "")
            # Chercher une session de conversation existante pour ce numÃ©ro WhatsApp
            existing_session = await db.chat_sessions.find_one(
                {"whatsappPhone": from_phone},
                {"_id": 0, "id": 1}
            )
            if not existing_session:
                # Chercher par numÃ©ro normalisÃ© dans les users
                wa_user = await db.users.find_one(
                    {"$or": [
                        {"whatsapp": {"$regex": normalized[-9:] + "$"}},
                        {"phone": {"$regex": normalized[-9:] + "$"}}
                    ]},
                    {"_id": 0, "id": 1, "name": 1, "email": 1}
                )
                if wa_user:
                    existing_session = await db.chat_sessions.find_one(
                        {"$or": [
                            {"participantEmail": wa_user.get("email")},
                            {"participant_ids": wa_user.get("id")}
                        ]},
                        {"_id": 0, "id": 1}
                    )

            session_id = existing_session.get("id") if existing_session else None
            if not session_id:
                # CrÃ©er une nouvelle session pour ce numÃ©ro WhatsApp
                session_id = str(uuid.uuid4())
                await db.chat_sessions.insert_one({
                    "id": session_id,
                    "mode": "whatsapp",
                    "whatsappPhone": from_phone,
                    "participantName": from_phone,
                    "participant_ids": [],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                })
                logger.info(f"[V113-WEBHOOK] ð± Nouvelle session WhatsApp crÃ©Ã©e pour {from_phone}: {session_id}")

            # InsÃ©rer le message entrant dans chat_messages
            msg_id = str(uuid.uuid4())
            msg_ts = datetime.now(timezone.utc).isoformat()
            await db.chat_messages.insert_one({
                "id": msg_id,
                "session_id": session_id,
                "content": incoming_message,
                "sender_type": "user",
                "sender_name": from_phone,
                "sender_id": from_phone,
                "channel": "whatsapp",
                "timestamp": msg_ts,
                "created_at": msg_ts
            })
            await db.chat_sessions.update_one(
                {"id": session_id},
                {"$set": {"last_message_at": msg_ts, "updated_at": msg_ts}}
            )
            logger.info(f"[V113-WEBHOOK] ð¬ Message WhatsApp sauvegardÃ© dans Conversations: {session_id}")
        except Exception as conv_err:
            logger.error(f"[V113-WEBHOOK] â Erreur sauvegarde conversation: {conv_err}")

    # Chercher le client dans les rÃ©servations
    client_name = None
    normalized_phone = from_phone.replace("+", "").replace(" ", "")
    reservations = await db.reservations.find({}, {"_id": 0}).to_list(1000)
    
    for res in reservations:
        res_phone = (res.get("whatsapp") or res.get("phone") or "").replace("+", "").replace(" ", "").replace("-", "")
        if res_phone and normalized_phone.endswith(res_phone[-9:]):
            client_name = res.get("userName") or res.get("name")
            break
    
    # Construire le contexte
    context = ""
    if client_name:
        context += f"\n\nLe client qui te parle s'appelle {client_name}. Utilise son prÃ©nom dans ta rÃ©ponse."
    
    last_media = ai_config.get("lastMediaUrl", "")
    if last_media:
        context += f"\n\nNote: Tu as rÃ©cemment envoyÃ© un mÃ©dia Ã  ce client: {last_media}. Tu peux lui demander s'il l'a bien reÃ§u."
    
    full_system_prompt = ai_config.get("systemPrompt", "") + context
    
    # Appeler l'IA
    try:
        from openai import OpenAI

        openai_key = os.environ.get("OPENAI_API_KEY")
        if not openai_key:
            logger.error("OPENAI_API_KEY not configured")
            return {"status": "error", "message": "AI key not configured"}

        client = OpenAI(api_key=openai_key)
        model_name = ai_config.get("model", "gpt-4o-mini")

        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=model_name,
            messages=[
                {"role": "system", "content": full_system_prompt},
                {"role": "user", "content": incoming_message}
            ],
            max_tokens=1000
        )
        ai_response = response.choices[0].message.content
        
        response_time = time.time() - start_time
        
        # Sauvegarder le log
        log_entry = AILog(
            fromPhone=from_phone,
            clientName=client_name,
            incomingMessage=incoming_message,
            aiResponse=ai_response,
            responseTime=response_time
        ).model_dump()
        await db.ai_logs.insert_one(log_entry)
        
        logger.info(f"AI responded to {from_phone} in {response_time:.2f}s")
        
        # Retourner la rÃ©ponse (Twilio attend un TwiML ou un JSON)
        # Pour une rÃ©ponse automatique, Twilio utilise TwiML
        return {
            "status": "success",
            "response": ai_response,
            "clientName": client_name,
            "responseTime": response_time
        }
        
    except Exception as e:
        logger.error(f"AI error: {str(e)}")
        return {"status": "error", "message": str(e)}

# --- Endpoint pour envoyer WhatsApp depuis le frontend (Liaison IA -> Twilio) ---
class SendWhatsAppRequest(BaseModel):
    to: str
    message: str
    mediaUrl: str = None

# === FONCTION UTILITAIRE WHATSAPP ===
async def _get_twilio_config():
    """
    RÃ©cupÃ¨re la configuration Twilio avec PRIORITÃ aux variables .env.
    Ordre de prioritÃ©:
    1. Variables d'environnement (.env) - PRODUCTION
    2. Configuration en base de donnÃ©es - FALLBACK
    
    Retourne: (account_sid, auth_token, from_number) ou (None, None, None) si non configurÃ©
    """
    # PRIORITÃ 1: Variables d'environnement (.env)
    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
        # V115: from_number â prioritÃ© env, sinon sandbox comme fallback sÃ»r
        effective_from = TWILIO_FROM_NUMBER or TWILIO_SANDBOX_NUMBER
        logger.info(f"[WHATSAPP-CONFIG] â Config .env - NumÃ©ro: {effective_from}")
        return TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, effective_from
    
    # PRIORITÃ 2: Configuration en base de donnÃ©es (fallback)
    whatsapp_config = await db.whatsapp_config.find_one({"id": "whatsapp_config"}, {"_id": 0})
    if whatsapp_config:
        account_sid = whatsapp_config.get("accountSid")
        auth_token = whatsapp_config.get("authToken")
        from_number = whatsapp_config.get("fromNumber")
        
        if account_sid and auth_token and from_number:
            logger.info(f"[WHATSAPP-PROD] â ï¸ Utilisation config DB (fallback) - NumÃ©ro: {from_number}")
            return account_sid, auth_token, from_number
    
    return None, None, None

async def _get_meta_config():
    """
    V118: RÃ©cupÃ¨re la config Meta Cloud API WhatsApp.
    PrioritÃ©: 1. Variables .env  2. Config MongoDB (meta_whatsapp_config)
    Retourne: (access_token, phone_number_id) ou (None, None)
    """
    if META_ACCESS_TOKEN and META_PHONE_NUMBER_ID:
        return META_ACCESS_TOKEN, META_PHONE_NUMBER_ID
    meta_cfg = await db.meta_whatsapp_config.find_one({"id": "meta_whatsapp_config"}, {"_id": 0})
    if meta_cfg:
        token = meta_cfg.get("accessToken", "")
        phone_id = meta_cfg.get("phoneNumberId", "")
        if token and phone_id:
            return token, phone_id
    return None, None


async def _get_whatsapp_sender():
    """
    V118: DÃ©termine le moteur WhatsApp et le numÃ©ro expÃ©diteur.
    Ordre de prioritÃ©:
    1. Meta Cloud API (si configurÃ©) â mode "meta"
    2. Twilio sender enregistrÃ© (registeredSender DB) â mode "production"
    3. TWILIO_FROM_NUMBER (env) â mode "production"
    4. TWILIO_SANDBOX_NUMBER â mode "sandbox"

    Retourne: (from_number, mode) â mode = "meta" | "production" | "sandbox"
    """
    # 1. Meta Cloud API configurÃ© ?
    meta_token, meta_phone_id = await _get_meta_config()
    if meta_token and meta_phone_id:
        # RÃ©cupÃ©rer le numÃ©ro affichÃ© depuis la config
        meta_cfg = await db.meta_whatsapp_config.find_one({"id": "meta_whatsapp_config"}, {"_id": 0})
        display_number = (meta_cfg or {}).get("displayNumber", TWILIO_PRODUCTION_NUMBER)
        logger.info(f"[WHATSAPP-SENDER-V118] â Mode Meta Cloud API â numÃ©ro: {display_number}")
        return display_number, "meta"

    # 2. Sender Twilio enregistrÃ© dans la DB
    wa_config = await db.whatsapp_config.find_one({"id": "whatsapp_config"}, {"_id": 0})
    if wa_config and wa_config.get("registeredSender"):
        registered = wa_config["registeredSender"]
        logger.info(f"[WHATSAPP-SENDER] â Sender Twilio production: {registered}")
        return registered, "production"

    # 3. Variable d'environnement Twilio
    if TWILIO_FROM_NUMBER and TWILIO_FROM_NUMBER != TWILIO_SANDBOX_NUMBER:
        return TWILIO_FROM_NUMBER, "production"

    # 4. Fallback sandbox
    logger.info(f"[WHATSAPP-SENDER] â ï¸ Fallback sandbox: {TWILIO_SANDBOX_NUMBER}")
    return TWILIO_SANDBOX_NUMBER, "sandbox"


async def send_whatsapp_meta(to_phone: str, message: str, media_url: str = None, campaign_id: str = None, campaign_name: str = None) -> dict:
    """
    V118: Envoie un message WhatsApp via Meta Cloud API (graph.facebook.com).
    UtilisÃ© quand le Super Admin a configurÃ© ses clÃ©s Meta.
    """
    import httpx

    access_token, phone_number_id = await _get_meta_config()
    if not access_token or not phone_number_id:
        return {"status": "error", "error": "Meta Cloud API non configurÃ©e (META_ACCESS_TOKEN / META_PHONE_NUMBER_ID manquants)", "error_code": "META_NOT_CONFIGURED"}

    # Formater le numÃ©ro destinataire (E.164 sans le +)
    clean_to = to_phone.replace(" ", "").replace("-", "").replace(".", "")
    if clean_to.startswith("+"):
        clean_to = clean_to[1:]
    elif clean_to.startswith("0"):
        clean_to = "41" + clean_to[1:]
    elif not clean_to.startswith("41"):
        clean_to = "41" + clean_to

    meta_url = f"https://graph.facebook.com/v21.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # Construire le payload â message texte simple (pas de template)
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": clean_to,
        "type": "text",
        "text": {"preview_url": False, "body": message}
    }

    # Si un mÃ©dia image est fourni, envoyer comme message image
    if media_url and any(media_url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_to,
            "type": "image",
            "image": {"link": media_url, "caption": message}
        }
    elif media_url and any(media_url.lower().endswith(ext) for ext in ['.mp4', '.mov', '.webm']):
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_to,
            "type": "video",
            "video": {"link": media_url, "caption": message}
        }

    logger.info(f"[META-WHATSAPP-V118] ð¤ Envoi vers {clean_to} via Meta Cloud API")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(meta_url, json=payload, headers=headers)
            result = response.json()

            if response.status_code >= 400:
                error_msg = "Erreur Meta API"
                error_detail = result.get("error", {})
                if isinstance(error_detail, dict):
                    error_msg = error_detail.get("message", error_msg)
                    error_code = error_detail.get("code", response.status_code)
                else:
                    error_code = response.status_code

                logger.error(f"[META-WHATSAPP-V118] â Erreur [{error_code}]: {error_msg}")

                try:
                    await db.campaign_errors.insert_one({
                        "campaign_id": campaign_id or "direct_send",
                        "campaign_name": campaign_name or "Envoi Direct",
                        "error_type": "meta_api_error",
                        "error_code": str(error_code),
                        "error_message": error_msg,
                        "channel": "whatsapp",
                        "to_phone": clean_to,
                        "engine": "meta",
                        "http_status": response.status_code,
                        "created_at": datetime.now(timezone.utc).isoformat()
                    })
                except Exception:
                    pass

                return {"status": "error", "error": error_msg, "error_code": str(error_code)}

            # SuccÃ¨s â extraire le message ID
            messages = result.get("messages", [])
            wa_id = messages[0].get("id", "") if messages else ""
            logger.info(f"[META-WHATSAPP-V118] â EnvoyÃ© â wamid: {wa_id}")

            return {"status": "success", "sid": wa_id, "to": clean_to, "engine": "meta"}

    except Exception as e:
        logger.error(f"[META-WHATSAPP-V118] â Exception: {str(e)}")
        return {"status": "error", "error": str(e), "error_code": "META_EXCEPTION"}


async def send_whatsapp_direct(to_phone: str, message: str, media_url: str = None, campaign_id: str = None, campaign_name: str = None, from_number_override: str = None) -> dict:
    """
    Fonction interne pour envoyer un message WhatsApp via Twilio.
    UtilisÃ©e par l'endpoint /send-whatsapp et par /campaigns/{id}/launch.

    Args:
        to_phone: NumÃ©ro de tÃ©lÃ©phone du destinataire
        message: Corps du message
        media_url: URL d'un mÃ©dia Ã  joindre (optionnel)
        campaign_id: ID de la campagne (pour logs d'erreurs)
        campaign_name: Nom de la campagne (pour logs d'erreurs)
        from_number_override: V113 â NumÃ©ro expÃ©diteur alternatif (ex: +41765203363 pour BYON)

    Returns:
        dict avec status, sid (si succÃ¨s), error (si Ã©chec), error_code (si Twilio)
    """
    import httpx

    # RÃ©cupÃ©rer la config Twilio (prioritÃ© .env)
    account_sid, auth_token, from_number = await _get_twilio_config()

    # V115: Utiliser le numÃ©ro override si fourni (campagnes passent toujours un override)
    if from_number_override:
        from_number = from_number_override
        logger.info(f"[WHATSAPP-V115] ð² Override expÃ©diteur: {from_number_override}")
    elif not from_number:
        # Fallback pour envois directs (hors campagne): dÃ©tection auto
        from_number, _mode = await _get_whatsapp_sender()
        logger.info(f"[WHATSAPP-V115] ð¤ Auto-dÃ©tection sender ({_mode}): {from_number}")

    if not account_sid or not auth_token or not from_number:
        # V112: JAMAIS de mode simulÃ© â erreur explicite si config manquante
        logger.error("[WHATSAPP-V112] â Configuration Twilio manquante â ENVOI IMPOSSIBLE")
        return {
            "status": "error",
            "error": "Configuration Twilio manquante (TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER non dÃ©finis)",
            "error_code": "MISSING_CONFIG"
        }

    # V112: Formater le numÃ©ro destinataire â format international obligatoire (+41 pour la Suisse)
    clean_to = to_phone.replace(" ", "").replace("-", "").replace(".", "")
    if not clean_to.startswith("+"):
        if clean_to.startswith("0"):
            clean_to = "+41" + clean_to[1:]
        elif clean_to.startswith("41"):
            clean_to = "+" + clean_to
        else:
            clean_to = "+41" + clean_to

    # V115: Formater le numÃ©ro expÃ©diteur
    clean_from = from_number if from_number.startswith("+") else "+" + from_number
    
    # Construire la requÃªte Twilio
    twilio_url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    
    data = {
        "From": f"whatsapp:{clean_from}",
        "To": f"whatsapp:{clean_to}",
        "Body": message
    }

    if media_url:
        data["MediaUrl"] = media_url

    # V114: StatusCallback pour recevoir les notifications de statut asynchrones de Twilio
    # (delivered, read, failed, undelivered â mise Ã  jour temps rÃ©el du statut campagne)
    base_url = os.environ.get("VERCEL_URL", "afroboost-v11-dev-pm7l.vercel.app")
    if not base_url.startswith("http"):
        base_url = f"https://{base_url}"
    status_callback_url = f"{base_url}/api/webhooks/twilio/status"
    data["StatusCallback"] = status_callback_url

    logger.info(f"[WHATSAPP-PROD] ð¤ Envoi via {clean_from} vers {clean_to} (callback: {status_callback_url})")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                twilio_url,
                data=data,
                auth=(account_sid, auth_token)
            )
            
            result = response.json()
            
            if response.status_code >= 400:
                error_msg = result.get("message", "Unknown error")
                error_code = result.get("code", response.status_code)
                more_info = result.get("more_info", "")
                
                logger.error(f"[WHATSAPP] â Erreur [{error_code}]: {error_msg}")
                
                # Stockage dans campaign_errors
                try:
                    error_doc = {
                        "campaign_id": campaign_id or "direct_send",
                        "campaign_name": campaign_name or "Envoi Direct",
                        "error_type": "twilio_api_error",
                        "error_code": str(error_code),
                        "error_message": error_msg,
                        "more_info": more_info,
                        "channel": "whatsapp",
                        "to_phone": clean_to,
                        "from_phone": clean_from,
                        "http_status": response.status_code,
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    await db.campaign_errors.insert_one(error_doc)
                except Exception as log_err:
                    logger.error(f"[WHATSAPP] Erreur log: {log_err}")
                
                return {
                    "status": "error", 
                    "error": error_msg, 
                    "error_code": str(error_code),
                    "more_info": more_info
                }
            
            sid = result.get("sid", "")
            logger.info(f"[WHATSAPP] â EnvoyÃ© - SID: {sid}")
            
            return {
                "status": "success",
                "sid": sid,
                "to": clean_to,
                "from": clean_from
            }
            
    except Exception as e:
        logger.error(f"[WHATSAPP] â Exception: {str(e)}")
        
        try:
            error_doc = {
                "campaign_id": campaign_id or "direct_send",
                "campaign_name": campaign_name or "Envoi Direct",
                "error_type": "exception",
                "error_code": "EXCEPTION",
                "error_message": str(e),
                "channel": "whatsapp",
                "to_phone": clean_to,
                "from_phone": clean_from,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.campaign_errors.insert_one(error_doc)
        except Exception as log_err:
            logger.error(f"[WHATSAPP-DIAG] Impossible d'enregistrer l'exception: {log_err}")
        
        return {"status": "error", "error": str(e), "error_code": "EXCEPTION"}
@api_router.post("/send-whatsapp")
async def send_whatsapp_message(request: SendWhatsAppRequest):
    """
    Endpoint pour envoyer un message WhatsApp.
    Utilise la config Twilio avec PRIORITÃ aux variables .env.
    """
    return await send_whatsapp_direct(
        to_phone=request.to,
        message=request.message,
        media_url=request.mediaUrl
    )

# --- Endpoint pour tester l'IA manuellement ---
@api_router.post("/ai-test")
async def test_ai_response(data: dict):
    """Test l'IA avec un message manuel"""
    import time
    start_time = time.time()
    
    message = data.get("message", "")
    client_name = data.get("clientName", "")
    
    if not message:
        raise HTTPException(status_code=400, detail="Message requis")
    
    # RÃ©cupÃ©rer la config IA
    ai_config = await db.ai_config.find_one({"id": "ai_config"}, {"_id": 0})
    if not ai_config:
        ai_config = AIConfig().model_dump()
    
    # Construire le contexte
    context = ""
    if client_name:
        context += f"\n\nLe client qui te parle s'appelle {client_name}. Utilise son prÃ©nom dans ta rÃ©ponse."
    
    last_media = ai_config.get("lastMediaUrl", "")
    if last_media:
        context += f"\n\nNote: Tu as rÃ©cemment envoyÃ© un mÃ©dia Ã  ce client: {last_media}."
    
    full_system_prompt = ai_config.get("systemPrompt", "") + context

    try:
        from openai import OpenAI

        openai_key = os.environ.get("OPENAI_API_KEY")
        if not openai_key:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY non configurÃ©")

        client = OpenAI(api_key=openai_key)
        model_name = ai_config.get("model", "gpt-4o-mini")

        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=model_name,
            messages=[
                {"role": "system", "content": full_system_prompt},
                {"role": "user", "content": message}
            ],
            max_tokens=1000
        )
        ai_response = response.choices[0].message.content
        
        response_time = time.time() - start_time
        
        return {
            "success": True,
            "response": ai_response,
            "responseTime": response_time
        }
        
    except Exception as e:
        logger.error(f"AI test error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Leads Routes (Widget IA) ---
# v68: ISOLATION MULTI-TENANT â chaque lead est liÃ© Ã  un coach_id
@api_router.get("/leads")
async def get_leads(request: Request):
    """RÃ©cupÃ¨re les leads capturÃ©s via le widget IA â filtrÃ© par coach_id"""
    caller_email = require_auth(request)

    # v68: Super Admin voit TOUS les leads, partenaire voit les siens
    if is_super_admin(caller_email):
        leads = await db.leads.find({}, {"_id": 0}).sort("createdAt", -1).to_list(500)
    else:
        leads = await db.leads.find(
            {"coach_id": caller_email}, {"_id": 0}
        ).sort("createdAt", -1).to_list(500)
    return leads

@api_router.post("/leads")
async def create_lead(request: Request, lead: Lead):
    """Enregistre un nouveau lead depuis le widget IA"""
    from datetime import datetime, timezone

    # v68: RÃ©cupÃ©rer le coach_id depuis le header ou le referer
    try:
        caller_email = require_auth(request)
    except HTTPException:
        caller_email = ""
    # Si pas de header (widget public), utiliser DEFAULT_COACH_ID
    coach_id = caller_email if caller_email else DEFAULT_COACH_ID

    lead_data = lead.model_dump()
    lead_data["id"] = f"lead_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{lead.whatsapp[-4:]}"
    lead_data["createdAt"] = datetime.now(timezone.utc).isoformat()
    lead_data["coach_id"] = coach_id  # v68: Association au coach

    # VÃ©rifier si le lead existe dÃ©jÃ  (mÃªme email ou WhatsApp) POUR CE COACH
    dup_filter = {"coach_id": coach_id, "$or": [{"email": lead.email}, {"whatsapp": lead.whatsapp}]}
    existing = await db.leads.find_one(dup_filter)

    if existing:
        await db.leads.update_one(
            {"id": existing["id"]},
            {"$set": {"firstName": lead.firstName, "updatedAt": lead_data["createdAt"]}}
        )
        existing["firstName"] = lead.firstName
        return {**existing, "_id": None}

    await db.leads.insert_one(lead_data)
    return {k: v for k, v in lead_data.items() if k != "_id"}

@api_router.delete("/leads/{lead_id}")
async def delete_lead(lead_id: str, request: Request):
    """Supprime un lead â vÃ©rifie l'ownership"""
    caller_email = require_auth(request)

    # v68: Super Admin peut supprimer n'importe quel lead, partenaire seulement les siens
    if is_super_admin(caller_email):
        result = await db.leads.delete_one({"id": lead_id})
    else:
        result = await db.leads.delete_one({"id": lead_id, "coach_id": caller_email})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {"success": True}

# === v9.4.1: ENDPOINT SUGGESTIONS IA POUR CAMPAGNES ===
@api_router.post("/ai/campaign-suggestions")
async def generate_campaign_suggestions(data: dict):
    """
    GÃ©nÃ¨re 3 variantes de messages de campagne basÃ©es sur l'objectif fourni.
    Types: Promo (ð¥), Relance (ð), Info (ð¢)
    """
    import time
    start_time = time.time()
    
    campaign_goal = data.get("campaign_goal", "")
    campaign_name = data.get("campaign_name", "Campagne")
    recipient_count = data.get("recipient_count", 1)
    # v11: Prompts indÃ©pendants par campagne
    campaign_system_prompt = data.get("system_prompt", "")
    campaign_description_prompt = data.get("description_prompt", "")

    if not campaign_goal and not campaign_description_prompt:
        raise HTTPException(status_code=400, detail="Objectif de campagne requis")

    # RÃ©cupÃ©rer la config IA
    ai_config = await db.ai_config.find_one({"id": "ai_config"}, {"_id": 0})
    if not ai_config:
        ai_config = {}

    # v11: PrioritÃ© â prompt campagne > prompt global
    effective_goal = campaign_description_prompt or campaign_goal
    extra_instructions = campaign_system_prompt or ai_config.get('campaignPrompt', '')

    # SystÃ¨me prompt pour la gÃ©nÃ©ration de suggestions
    system_prompt = f"""Tu es un expert en marketing et copywriting pour une application de fitness/danse appelÃ©e Afroboost.

Tu dois gÃ©nÃ©rer EXACTEMENT 3 variantes de messages WhatsApp/SMS basÃ©es sur l'objectif suivant:
"{effective_goal}"

RÃGLES STRICTES:
1. Chaque message doit Ãªtre COURT (max 200 caractÃ¨res)
2. Chaque message doit contenir la variable {{prÃ©nom}} au dÃ©but
3. Utilise des emojis pertinents (1-2 max)
4. Sois direct et engageant
5. Inclus un call-to-action clair

FORMAT DE RÃPONSE (JSON strict):
{{
  "suggestions": [
    {{"type": "Promo", "text": "ð¥ Salut {{prÃ©nom}}! [message promotionnel avec offre]"}},
    {{"type": "Relance", "text": "ð Hey {{prÃ©nom}}! [message de relance engageant]"}},
    {{"type": "Info", "text": "ð¢ {{prÃ©nom}}, [information importante]"}}
  ]
}}

Contexte:
- Campagne: {campaign_name}
- Nombre de destinataires: {recipient_count}
- Application: Cours de danse Afrobeat, casques silencieux

{extra_instructions}
"""
    
    try:
        from openai import OpenAI

        openai_key = os.environ.get("OPENAI_API_KEY")
        if not openai_key:
            # Fallback: gÃ©nÃ©rer des suggestions statiques
            return {
                "success": True,
                "suggestions": [
                    {"type": "Promo", "text": f"ð¥ Salut {{prÃ©nom}}! {campaign_goal} Profites-en vite!"},
                    {"type": "Relance", "text": f"ð Hey {{prÃ©nom}}! On ne t'a pas vu depuis un moment. {campaign_goal}"},
                    {"type": "Info", "text": f"ð¢ {{prÃ©nom}}, nouvelle info: {campaign_goal}. Ã bientÃ´t!"}
                ],
                "source": "fallback"
            }

        client = OpenAI(api_key=openai_key)
        model_name = ai_config.get("model", "gpt-4o-mini")

        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"GÃ©nÃ¨re 3 variantes de messages pour cette campagne: {campaign_goal}"}
            ],
            max_tokens=1000
        )
        ai_response = response.choices[0].message.content

        # Parser la rÃ©ponse JSON
        import json
        import re

        response_text = ai_response
        
        # Extraire le JSON de la rÃ©ponse
        json_match = re.search(r'\{[\s\S]*"suggestions"[\s\S]*\}', response_text)
        if json_match:
            parsed = json.loads(json_match.group())
            suggestions = parsed.get("suggestions", [])
        else:
            # Fallback si pas de JSON valide
            suggestions = [
                {"type": "Promo", "text": f"ð¥ Salut {{prÃ©nom}}! {campaign_goal} Profites-en maintenant!"},
                {"type": "Relance", "text": f"ð Hey {{prÃ©nom}}! {campaign_goal} On t'attend!"},
                {"type": "Info", "text": f"ð¢ {{prÃ©nom}}, {campaign_goal}. Ã trÃ¨s vite!"}
            ]
        
        response_time = time.time() - start_time
        
        return {
            "success": True,
            "suggestions": suggestions[:3],  # Maximum 3
            "response_time": round(response_time, 2),
            "source": "ai"
        }
        
    except Exception as e:
        logger.error(f"[AI SUGGESTIONS] Error: {str(e)}")
        # Fallback en cas d'erreur
        return {
            "success": True,
            "suggestions": [
                {"type": "Promo", "text": f"ð¥ Salut {{prÃ©nom}}! {campaign_goal} RÃ©serve maintenant!"},
                {"type": "Relance", "text": f"ð Hey {{prÃ©nom}}! {campaign_goal} On t'attend!"},
                {"type": "Info", "text": f"ð¢ {{prÃ©nom}}, {campaign_goal}. Ã bientÃ´t!"}
            ],
            "source": "fallback",
            "error": str(e)
        }

# --- Chat IA Widget ---
@api_router.post("/chat")
async def chat_with_ai(data: ChatMessage):
    """
    Chat avec l'IA depuis le widget client.
    
    FonctionnalitÃ©s:
    1. SYNCHRONISATION IA: RÃ©cupÃ¨re dynamiquement les offres et articles
    2. CRM AUTO-SAVE: Enregistre automatiquement le prospect (anti-doublon)
    3. CONTEXTE DYNAMIQUE: Injecte les infos dans le prompt systÃ¨me
    """
    import time
    start_time = time.time()
    
    message = data.message
    first_name = data.firstName
    email = data.email
    whatsapp = data.whatsapp
    source = data.source or "chat_ia"
    
    if not message:
        raise HTTPException(status_code=400, detail="Message requis")
    
    # === 1. CRM AUTO-SAVE (Anti-doublon) ===
    # Enregistrer le prospect dans chat_participants si email ou whatsapp fourni
    if email or whatsapp:
        try:
            # VÃ©rifier si le contact existe dÃ©jÃ  (par email OU whatsapp)
            existing_contact = None
            if email:
                existing_contact = await db.chat_participants.find_one({"email": email}, {"_id": 0})
            if not existing_contact and whatsapp:
                # Normaliser le numÃ©ro WhatsApp
                clean_whatsapp = whatsapp.replace(" ", "").replace("-", "")
                existing_contact = await db.chat_participants.find_one({
                    "$or": [
                        {"whatsapp": whatsapp},
                        {"whatsapp": clean_whatsapp}
                    ]
                }, {"_id": 0})
            
            if not existing_contact:
                # CrÃ©er le nouveau contact
                new_participant = {
                    "id": str(uuid.uuid4()),
                    "name": first_name or "Visiteur Chat IA",
                    "email": email or "",
                    "whatsapp": whatsapp or "",
                    "source": f"Lien Chat IA ({source})",
                    "link_token": None,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "last_seen_at": datetime.now(timezone.utc).isoformat()
                }
                await db.chat_participants.insert_one(new_participant)
                logger.info(f"[CRM-AUTO] Nouveau contact crÃ©Ã©: {first_name or 'Visiteur'} ({email or whatsapp}) - Source: {source}")
            else:
                # Mettre Ã  jour last_seen_at
                await db.chat_participants.update_one(
                    {"id": existing_contact.get("id")},
                    {"$set": {"last_seen_at": datetime.now(timezone.utc).isoformat()}}
                )
                logger.info(f"[CRM-AUTO] Contact existant mis Ã  jour: {existing_contact.get('name')}")
        except Exception as crm_error:
            logger.warning(f"[CRM-AUTO] Erreur enregistrement CRM (non bloquant): {crm_error}")
    
    # === 2. RÃCUPÃRER LA CONFIG IA ===
    ai_config = await db.ai_config.find_one({"id": "ai_config"}, {"_id": 0})
    if not ai_config:
        ai_config = AIConfig().model_dump()
    
    if not ai_config.get("enabled"):
        return {"response": "L'assistant IA est actuellement dÃ©sactivÃ©. Veuillez contacter le coach directement.", "responseTime": 0}
    
    # === 2.5 DETECTION MODE STRICT (lien avec custom_prompt) ===
    link_token = data.link_token.strip() if data.link_token else ""
    if not link_token and data.source and data.source.startswith("link_"):
        link_token = data.source.replace("link_", "")
    
    use_strict_mode = False
    CUSTOM_PROMPT = ""
    
    if link_token:
        try:
            session_with_prompt = await db.chat_sessions.find_one(
                {"link_token": link_token, "is_deleted": {"$ne": True}},
                {"_id": 0, "custom_prompt": 1}
            )
            if session_with_prompt and session_with_prompt.get("custom_prompt"):
                custom_prompt = session_with_prompt.get("custom_prompt", "").strip()
                if custom_prompt:
                    CUSTOM_PROMPT = custom_prompt
                    use_strict_mode = True
                    logger.info(f"[CHAT-IA] Mode STRICT lien {link_token[:8]}")
        except Exception as e:
            logger.warning(f"[CHAT-IA] Erreur custom_prompt: {e}")
    
    # === 3. CONSTRUIRE LE CONTEXTE DYNAMIQUE ===
    if use_strict_mode:
        # v8.5: ISOLATION TOTALE - UNIQUEMENT le custom_prompt du lien
        context = f"\n\n=== INSTRUCTIONS SPECIFIQUES DU LIEN ===\n{CUSTOM_PROMPT}\n"
        if first_name:
            context += f"\nInterlocuteur: {first_name}\n"
        logger.info("[CHAT-IA] v8.5: Isolation totale activee")
    else:
        # MODE STANDARD: Contexte complet avec cours/tarifs/vente
        context = "\n\n========== CONNAISSANCES DU SITE AFROBOOST ==========\n"
        context += "Utilise EXCLUSIVEMENT ces informations pour rÃ©pondre sur les produits, cours, offres et articles.\n"
        context += "IMPORTANT: VÃ©rifie TOUJOURS l'INVENTAIRE BOUTIQUE avant de dire qu'un produit n'existe pas !\n"
        
        # PrÃ©nom du client
        if first_name:
            context += f"\nð¤ CLIENT: {first_name} - Utilise son prÃ©nom pour Ãªtre chaleureux.\n"
        
        # Concept/Description du site
        try:
            concept = await db.concept.find_one({"id": "concept"}, {"_id": 0})
            if concept and concept.get('description'):
                context += f"\nð Ã PROPOS D'AFROBOOST:\n{concept.get('description', '')[:500]}\n"
        except Exception as e:
            logger.warning(f"[CHAT-IA] Erreur rÃ©cupÃ©ration concept: {e}")
    
    # === SECTIONS VENTE (UNIQUEMENT en mode STANDARD, pas en mode STRICT) ===
    if not use_strict_mode:
        # === SECTION 1: INVENTAIRE BOUTIQUE (PRODUITS PHYSIQUES) ===
        try:
            # RÃ©cupÃ©rer TOUS les Ã©lÃ©ments de la collection offers
            all_offers = await db.offers.find({"visible": {"$ne": False}}, {"_id": 0}).to_list(50)
            
            # SÃ©parer les PRODUITS des SERVICES
            products = [o for o in all_offers if o.get('isProduct') == True]
            services = [o for o in all_offers if not o.get('isProduct')]
            
            # === PRODUITS BOUTIQUE (cafÃ©, vÃªtements, accessoires...) ===
            if products:
                context += "\n\nð INVENTAIRE BOUTIQUE (Produits en vente):\n"
                for p in products[:15]:
                    name = p.get('name', 'Produit')
                    price = p.get('price', 0)
                    desc = p.get('description', '')[:150] if p.get('description') else ''
                    category = p.get('category', '')
                    stock = p.get('stock', -1)
                    
                    context += f"  â {name.upper()} : {price} CHF"
                    if category:
                        context += f" (CatÃ©gorie: {category})"
                    if stock > 0:
                        context += f" - En stock: {stock}"
                    context += "\n"
                    if desc:
                        context += f"    Description: {desc}\n"
                context += "  â Si un client demande un de ces produits, CONFIRME qu'il est disponible !\n"
            else:
                context += "\n\nð INVENTAIRE BOUTIQUE: Aucun produit en vente actuellement.\n"
            
            # === SERVICES ET OFFRES (abonnements, cours Ã  l'unitÃ©...) ===
            if services:
                context += "\n\nð° OFFRES ET TARIFS (Services):\n"
                for s in services[:10]:
                    name = s.get('name', 'Offre')
                    price = s.get('price', 0)
                    desc = s.get('description', '')[:100] if s.get('description') else ''
                    
                    context += f"  â¢ {name} : {price} CHF"
                    if desc:
                        context += f" - {desc}"
                    context += "\n"
            else:
                context += "\n\nð° OFFRES: Aucune offre spÃ©ciale actuellement.\n"
                
        except Exception as e:
            logger.error(f"[CHAT-IA] â Erreur rÃ©cupÃ©ration offres/produits: {e}")
            context += "\n\nð BOUTIQUE: Informations temporairement indisponibles.\n"
    
        # === SECTION 2: COURS DISPONIBLES ===
        try:
            courses = await db.courses.find({"visible": {"$ne": False}}, {"_id": 0}).to_list(20)
            if courses:
                context += "\n\nð¯ COURS DISPONIBLES:\n"
                for c in courses[:10]:  # Max 10 cours
                    name = c.get('name', 'Cours')
                    date = c.get('date', '')
                    time_slot = c.get('time', '')
                    location = c.get('location', '')
                    price = c.get('price', '')
                    description = c.get('description', '')[:80] if c.get('description') else ''
                    
                    context += f"  â¢ {name}"
                    if date:
                        context += f" - {date}"
                    if time_slot:
                        context += f" Ã  {time_slot}"
                    if location:
                        context += f" ({location})"
                    if price:
                        context += f" - {price} CHF"
                    context += "\n"
                    if description:
                        context += f"    â {description}\n"
            else:
                context += "\n\nð¯ COURS: Aucun cours programmÃ© actuellement. Invite le client Ã  suivre nos rÃ©seaux pour les prochaines dates.\n"
        except Exception as e:
            logger.warning(f"[CHAT-IA] Erreur rÃ©cupÃ©ration cours: {e}")
            context += "\n\nð¯ COURS: Informations temporairement indisponibles.\n"
        
        # === SECTION 3: PROMOS SPÃCIALES (avec masquage des codes) ===
        # L'IA peut connaÃ®tre les remises pour calculer les prix, mais JAMAIS les codes
        # PRODUCTION-READY: Try/except individuel pour chaque promo
        try:
            active_promos = await db.discount_codes.find({"active": True}, {"_id": 0}).to_list(20)
            if active_promos:
                context += "\n\nð PROMOTIONS EN COURS:\n"
                promos_injected = 0
                for promo in active_promos[:5]:
                    try:
                        # MASQUAGE TECHNIQUE: Le champ 'code' n'est JAMAIS lu ni transmis
                        # Seuls 'type' et 'value' sont utilisÃ©s pour le calcul
                        promo_type = promo.get('type', '%')
                        promo_value = promo.get('value', 0)
                        
                        # Validation: S'assurer que value est un nombre valide
                        if promo_value is None:
                            promo_value = 0
                        promo_value = float(promo_value)
                        
                        # Construire la description SANS le code rÃ©el
                        # Le placeholder [CODE_APPLIQUÃ_AU_PANIER] est la SEULE chose visible
                        if promo_type == '100%':
                            context += "  â¢ Remise 100% disponible (code: [CODE_APPLIQUÃ_AU_PANIER])\n"
                        elif promo_type == '%':
                            context += "  â¢ Remise de " + str(promo_value) + "% disponible (code: [CODE_APPLIQUÃ_AU_PANIER])\n"
                        elif promo_type == 'CHF':
                            context += "  â¢ Remise de " + str(promo_value) + " CHF disponible (code: [CODE_APPLIQUÃ_AU_PANIER])\n"
                        else:
                            # Type inconnu: afficher quand mÃªme sans rÃ©vÃ©ler le code
                            context += "  â¢ Promotion disponible (code: [CODE_APPLIQUÃ_AU_PANIER])\n"
                        promos_injected += 1
                    except Exception as promo_error:
                        # Log l'erreur mais continue avec les autres promos
                        logger.warning(f"[CHAT-IA] â ï¸ Promo ignorÃ©e (erreur parsing): {promo_error}")
                        continue
                
                if promos_injected > 0:
                    context += "  â Tu peux calculer les prix rÃ©duits avec ces remises.\n"
                    context += "  â Ne dis JAMAIS le code. Dis simplement: 'Le code est appliquÃ© automatiquement au panier.'\n"
                    logger.info(f"[CHAT-IA] â {promos_injected} promos injectÃ©es (codes masquÃ©s)")
        except Exception as e:
            logger.warning(f"[CHAT-IA] Erreur rÃ©cupÃ©ration promos (non bloquant): {e}")
        
        # === SECTION 5: LIEN DE PAIEMENT TWINT ===
        twint_payment_url = ai_config.get("twintPaymentUrl", "")
        if twint_payment_url and twint_payment_url.strip():
            context += f"\n\nð³ LIEN DE PAIEMENT TWINT:\n"
            context += f"  URL: {twint_payment_url}\n"
            context += "  â Quand un client confirme vouloir acheter, propose-lui ce lien de paiement sÃ©curisÃ© Twint.\n"
    # === FIN DES SECTIONS VENTE (uniquement en mode STANDARD) ===
    
    # === RÃGLES STRICTES POUR L'IA ===
    # RÃ©cupÃ©rer le lien de paiement Twint UNIQUEMENT en mode STANDARD
    twint_payment_url = ""
    if not use_strict_mode:
        twint_payment_url = ai_config.get("twintPaymentUrl", "")
    
    # DÃ©tecter intention essai gratuit
    message_lower = message.lower()
    is_trial_intent = any(word in message_lower for word in ['essai', 'gratuit', 'tester', 'essayer', 'test', 'dÃ©couvrir'])
    
    # ARCHITECTURE DE PROMPT - STRICT vs STANDARD
    if use_strict_mode:
        # MODE STRICT : custom_prompt REMPLACE BASE_PROMPT, AUCUNE donnÃ©e de vente
        STRICT_SYSTEM_PROMPT = """
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
â        ððð MODE STRICT - PARTENARIAT / COLLABORATION ððð        â
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

âââ INTERDICTIONS ABSOLUES âââ

Tu as INTERDICTION ABSOLUE de:
- Citer un PRIX, un TARIF, un COÃT ou un MONTANT (CHF, EUR, $)
- Mentionner un LIEN DE PAIEMENT (Twint, Stripe, etc.)
- Parler de COURS, SESSIONS, ABONNEMENTS ou RÃSERVATIONS
- Orienter vers l'ACHAT ou l'INSCRIPTION
- Donner des informations sur la BOUTIQUE ou les PRODUITS Ã  vendre

Si on te demande un prix, un tarif ou "combien Ã§a coÃ»te", TU DOIS rÃ©pondre:
"Je vous invite Ã  en discuter directement lors de notre Ã©change, je m'occupe uniquement de la partie collaboration."

Si on insiste, rÃ©pÃ¨te cette phrase. Ne donne JAMAIS de prix.

ð¯ TON RÃLE UNIQUE:
Tu t'occupes UNIQUEMENT de la COLLABORATION et du PARTENARIAT.
Tu peux parler du CONCEPT Afroboost (cardio + danse afrobeat + casques audio immersifs).
Tu ne connais AUCUN prix, AUCUN tarif, AUCUN lien de paiement.

"""
        STRICT_SYSTEM_PROMPT += "\nð INSTRUCTIONS EXCLUSIVES DU LIEN:\n\n"
        STRICT_SYSTEM_PROMPT += CUSTOM_PROMPT
        
        context += STRICT_SYSTEM_PROMPT
        logger.info("[CHAT-IA] ð Mode STRICT activÃ©")
        
    else:
        # MODE STANDARD : FLUX HABITUEL AVEC DONNÃES DE VENTE
        BASE_PROMPT = """
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
â                BASE_PROMPT - IDENTITÃ COACH BASSI                â
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

ð¯ IDENTITÃ:
Tu es le COACH BASSI, coach Ã©nergique et passionnÃ© d'Afroboost.
Tu reprÃ©sentes la marque Afroboost et tu guides les clients vers leurs objectifs fitness.
Tu ne parles QUE du catalogue Afroboost (produits, cours, offres listÃ©s ci-dessus).

ðª SIGNATURE:
- PrÃ©sente-toi comme "Coach Bassi" si on te demande ton nom
- Utilise un ton motivant, bienveillant et Ã©nergique
- Signe parfois tes messages avec "- Coach Bassi ðª" pour les messages importants

â CONTENU AUTORISÃ (EXCLUSIVEMENT):
- Les PRODUITS de l'INVENTAIRE BOUTIQUE listÃ©s ci-dessus
- Les COURS disponibles listÃ©s ci-dessus
- Les OFFRES et TARIFS listÃ©s ci-dessus
- Le concept Afroboost (cardio + danse afrobeat)

ð¯ TON STYLE:
- Coach motivant et Ã©nergique (TU ES Coach Bassi)
- Utilise le prÃ©nom du client
- Oriente vers l'INSCRIPTION IMMÃDIATE
- Emojis: ð¥ðªð
- RÃ©ponses courtes et percutantes
"""

        # --- 2. SECURITY_PROMPT : RÃ¨gle non nÃ©gociable ---
        SECURITY_PROMPT = """
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
â              SECURITY_PROMPT - RÃGLE NON NÃGOCIABLE              â
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

â RÃGLE NON NÃGOCIABLE:
Si la question ne concerne pas un produit ou un cours Afroboost, rÃ©ponds:
"DÃ©solÃ©, je suis uniquement programmÃ© pour vous assister sur nos offres et formations. ð"

ð« N'invente JAMAIS de codes promo. Si une remise existe, dis: "Le code sera appliquÃ© automatiquement au panier."

ð« INTERDICTIONS ABSOLUES:
- Ne rÃ©ponds JAMAIS aux questions hors-sujet (politique, mÃ©tÃ©o, cuisine, prÃ©sident, etc.)
- Ne rÃ©vÃ¨le JAMAIS un code promo textuel
- N'invente JAMAIS d'offres ou de prix
"""

        # Ajout de rÃ¨gles contextuelles
        if is_trial_intent:
            SECURITY_PROMPT += """

ð FLOW ESSAI GRATUIT:
1. "Super ! ð¥ Les 10 premiers peuvent tester gratuitement !"
2. "Tu prÃ©fÃ¨res Mercredi ou Dimanche ?"
3. Attends sa rÃ©ponse avant de demander ses coordonnÃ©es.
"""
        
        # Lien Twint UNIQUEMENT en mode STANDARD
        if twint_payment_url and twint_payment_url.strip():
            SECURITY_PROMPT += f"""

ð³ PAIEMENT: Propose ce lien Twint: {twint_payment_url}
"""
        else:
            SECURITY_PROMPT += """

ð³ PAIEMENT: Oriente vers le coach WhatsApp ou email pour finaliser.
"""

        # --- 3. CAMPAIGN_PROMPT : RÃ©cupÃ©rÃ© de la config globale ---
        CAMPAIGN_PROMPT = ai_config.get("campaignPrompt", "").strip()
        
        # GARDE-FOU: Limite Ã  2000 caractÃ¨res
        MAX_CAMPAIGN_LENGTH = 2000
        if len(CAMPAIGN_PROMPT) > MAX_CAMPAIGN_LENGTH:
            logger.warning("[CHAT-IA] â ï¸ CAMPAIGN_PROMPT tronquÃ©")
            CAMPAIGN_PROMPT = CAMPAIGN_PROMPT[:MAX_CAMPAIGN_LENGTH] + "... [TRONQUÃ]"
        
        # Injection MODE STANDARD: BASE + SECURITY + CAMPAIGN
        context += BASE_PROMPT
        context += SECURITY_PROMPT
        if CAMPAIGN_PROMPT:
            context += "\n\n--- INSTRUCTIONS PRIORITAIRES DE LA CAMPAGNE ACTUELLE ---\n"
            context += CAMPAIGN_PROMPT
            context += "\n--- FIN DES INSTRUCTIONS ---\n"
            logger.info("[CHAT-IA] â Mode STANDARD - Campaign Prompt injectÃ© (len: " + str(len(CAMPAIGN_PROMPT)) + ")")
        else:
            logger.info("[CHAT-IA] Mode STANDARD - Pas de Campaign Prompt")
    
    # v8.4: Assemblage final - PRIORITE: Prompt Lien > Prompt Campagne > Prompt Systeme
    if use_strict_mode and CUSTOM_PROMPT:
        full_system_prompt = context  # Prompt du lien REMPLACE tout
        logger.info("[CHAT-IA] v8.4: Prompt Lien actif (systemPrompt ignore)")
    else:
        full_system_prompt = ai_config.get("systemPrompt", "Tu es l'assistant IA d'Afroboost.") + context
    
    try:
        from openai import OpenAI

        openai_key = os.environ.get("OPENAI_API_KEY")
        if not openai_key:
            return {"response": "Configuration IA incomplÃ¨te. Contactez l'administrateur.", "responseTime": 0}

        client = OpenAI(api_key=openai_key)
        model_name = ai_config.get("model", "gpt-4o-mini")

        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=model_name,
            messages=[
                {"role": "system", "content": full_system_prompt},
                {"role": "user", "content": message}
            ],
            max_tokens=1000
        )
        ai_response = response.choices[0].message.content
        response_time = round(time.time() - start_time, 2)
        
        # Log la conversation
        await db.ai_logs.insert_one({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "from": f"widget_{first_name or 'anonymous'}",
            "email": email or "",
            "whatsapp": whatsapp or "",
            "source": source,
            "message": message,
            "response": ai_response,
            "responseTime": response_time
        })
        
        return {
            "response": ai_response,
            "responseTime": response_time
        }
        
    except Exception as e:
        logger.error(f"Chat AI error: {str(e)}")
        return {"response": "DÃ©solÃ©, une erreur s'est produite. Veuillez rÃ©essayer.", "responseTime": 0}

# === ENHANCED CHAT SYSTEM API ===
# SystÃ¨me de chat amÃ©liorÃ© avec reconnaissance utilisateur, modes et liens partageables

# --- Chat Participants (CRM) ---
@api_router.get("/chat/participants")
async def get_chat_participants(request: Request):
    """RÃ©cupÃ¨re les participants du chat (CRM) - FiltrÃ© par coach_id v8.9.5"""
    try:
        caller_email = require_auth(request)
    except HTTPException:
        caller_email = ""
    
    # RÃGLE ANTI-CASSE BASSI: Super Admin voit TOUT
    if is_super_admin(caller_email):
        participants = await db.chat_participants.find({}, {"_id": 0}).to_list(1000)
    else:
        # Coach normal: uniquement ses donnÃ©es (coach_id == son email)
        participants = await db.chat_participants.find(
            {"coach_id": caller_email}, {"_id": 0}
        ).to_list(1000) if caller_email else []
    return participants

@api_router.get("/chat/participants/{participant_id}")
async def get_chat_participant(participant_id: str):
    """RÃ©cupÃ¨re un participant par son ID"""
    participant = await db.chat_participants.find_one({"id": participant_id}, {"_id": 0})
    if not participant:
        raise HTTPException(status_code=404, detail="Participant non trouvÃ©")
    return participant
@api_router.post("/chat/participants")
async def create_chat_participant(participant: ChatParticipantCreate, request: Request):
    """v104: Upsert contact â dÃ©duplique par email/phone, met Ã  jour si existant"""
    try:
        coach_email = require_auth(request)
    except HTTPException:
        coach_email = ""
    coach_id = coach_email if (coach_email and not is_super_admin(coach_email)) else DEFAULT_COACH_ID

    p = participant.model_dump()
    email = (p.get("email") or "").strip().lower()
    phone = (p.get("whatsapp") or p.get("phone") or "").replace(" ", "").replace("-", "")

    # v104: Recherche doublon par email ou phone
    dup_query = {"$or": []}
    if email:
        dup_query["$or"].append({"email": {"$regex": f"^{email}$", "$options": "i"}})
    if phone:
        dup_query["$or"].append({"whatsapp": {"$regex": phone}})
        dup_query["$or"].append({"phone": {"$regex": phone}})

    existing = None
    if dup_query["$or"]:
        existing = await db.chat_participants.find_one(dup_query, {"_id": 0})

    if existing:
        # Mettre Ã  jour les champs non vides
        updates = {"last_seen_at": datetime.now(timezone.utc).isoformat()}
        if p.get("name") and p["name"] != existing.get("name"):
            updates["name"] = p["name"]
        if email and not existing.get("email"):
            updates["email"] = email
        if phone and not existing.get("whatsapp"):
            updates["whatsapp"] = phone
        if p.get("source") and p["source"] != existing.get("source"):
            updates["source"] = p["source"]
        # Fusionner les tags
        new_tags = p.get("tags", [])
        if new_tags:
            updates["tags"] = list(set(existing.get("tags", []) + new_tags))
        await db.chat_participants.update_one({"id": existing["id"]}, {"$set": updates})
        updated = await db.chat_participants.find_one({"id": existing["id"]}, {"_id": 0})
        return updated

    # Nouveau contact â vÃ©rifier crÃ©dits
    if coach_email and not is_super_admin(coach_email):
        credit_check = await check_credits(coach_email)
        if not credit_check.get("has_credits"):
            raise HTTPException(status_code=402, detail="CrÃ©dits insuffisants. Achetez un pack pour continuer.")
        await deduct_credit(coach_email, "crÃ©ation contact")

    participant_obj = ChatParticipant(**p)
    participant_data = participant_obj.model_dump()
    participant_data["coach_id"] = coach_id
    await db.chat_participants.insert_one(participant_data)
    participant_data.pop("_id", None)
    return participant_data

@api_router.get("/chat/participants/find")
async def find_participant(
    name: Optional[str] = None,
    email: Optional[str] = None,
    whatsapp: Optional[str] = None
):
    """
    Recherche un participant par nom, email ou WhatsApp.
    UtilisÃ© pour la reconnaissance automatique des utilisateurs.
    """
    query = {"$or": []}
    
    if name:
        query["$or"].append({"name": {"$regex": name, "$options": "i"}})
    if email:
        query["$or"].append({"email": {"$regex": f"^{email}$", "$options": "i"}})
    if whatsapp:
        # Nettoyer le numÃ©ro WhatsApp pour la recherche
        clean_whatsapp = whatsapp.replace(" ", "").replace("-", "").replace("+", "")
        query["$or"].append({"whatsapp": {"$regex": clean_whatsapp}})
    
    if not query["$or"]:
        return None
    
    participant = await db.chat_participants.find_one(query, {"_id": 0})
    return participant

@api_router.put("/chat/participants/{participant_id}")
async def update_chat_participant(participant_id: str, update_data: dict):
    """Met Ã  jour un participant"""
    update_data["last_seen_at"] = datetime.now(timezone.utc).isoformat()
    await db.chat_participants.update_one(
        {"id": participant_id},
        {"$set": update_data}
    )
    updated = await db.chat_participants.find_one({"id": participant_id}, {"_id": 0})
    return updated

# ââââââââââ V160: Anniversaires ââââââââââ

@api_router.get("/birthdays/today")
async def get_todays_birthdays():
    """V160: Retourne les participants dont c'est l'anniversaire aujourd'hui"""
    today = datetime.now(timezone.utc).strftime("%m-%d")
    logger.info(f"[V160] Checking birthdays for {today}")
    
    # Chercher dans chat_participants
    participants = await db.chat_participants.find(
        {"birthday": today},
        {"_id": 0, "id": 1, "name": 1, "birthday": 1}
    ).to_list(100)
    
    return {"date": today, "birthdays": participants, "count": len(participants)}

@api_router.put("/chat/participants/{participant_id}/birthday")
async def update_participant_birthday(participant_id: str, data: dict):
    """V160: Met a jour la date de naissance d'un participant (format MM-DD)"""
    birthday = data.get("birthday")
    if not birthday:
        raise HTTPException(status_code=400, detail="birthday field required (format MM-DD)")
    
    # Valider le format MM-DD
    try:
        month, day = birthday.split("-")
        if not (1 <= int(month) <= 12 and 1 <= int(day) <= 31):
            raise ValueError()
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Format invalide. Utilisez MM-DD (ex: 03-15)")
    
    result = await db.chat_participants.update_one(
        {"id": participant_id},
        {"$set": {"birthday": birthday}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Participant non trouve")
    
    logger.info(f"[V160] Birthday updated for {participant_id}: {birthday}")
    return {"success": True, "participant_id": participant_id, "birthday": birthday}

@api_router.delete("/chat/participants/{participant_id}")
async def delete_chat_participant(participant_id: str):
    """Supprime un participant du CRM avec nettoyage complet des donnees orphelines"""
    logger.info(f"[DELETE] Suppression participant: {participant_id}")
    
    participant = await db.chat_participants.find_one({"id": participant_id}, {"_id": 0})
    if not participant:
        logger.warning(f"[DELETE] Participant non trouve: {participant_id}")
        raise HTTPException(status_code=404, detail="Participant non trouve")
    
    participant_name = participant.get('name', 'inconnu')
    
    # 1. Supprimer tous les messages envoyes par ce participant
    messages_result = await db.chat_messages.delete_many({"sender_id": participant_id})
    logger.info(f"[DELETE] Messages supprimes: {messages_result.deleted_count}")
    
    # 2. Retirer le participant de toutes les sessions
    sessions_update = await db.chat_sessions.update_many(
        {"participant_ids": participant_id},
        {"$pull": {"participant_ids": participant_id}}
    )
    logger.info(f"[DELETE] Sessions mises a jour: {sessions_update.modified_count}")
    
    # 3. Supprimer les sessions privees ou le participant etait seul
    orphan_sessions = await db.chat_sessions.delete_many({
        "mode": "private",
        "participant_ids": {"$size": 0}
    })
    logger.info(f"[DELETE] Sessions orphelines supprimees: {orphan_sessions.deleted_count}")
    
    # 4. Supprimer le participant
    result = await db.chat_participants.delete_one({"id": participant_id})
    logger.info(f"[DELETE] Participant supprime: {result.deleted_count}")
    
    logger.info(f"[DELETE] Participant {participant_name} et donnees associees supprimes")
    return {
        "success": True, 
        "message": f"Contact {participant_name} supprime definitivement",
        "deleted": {
            "participant": result.deleted_count,
            "messages": messages_result.deleted_count,
            "sessions_updated": sessions_update.modified_count,
            "orphan_sessions": orphan_sessions.deleted_count
        }
    }

# --- Active Conversations for Internal Messaging ---
@api_router.get("/conversations/active")
async def get_active_conversations_for_messaging():
    """
    RÃ©cupÃ¨re TOUTES les conversations pour la programmation de messages internes.
    Inclut : 
    - Sessions avec titre (groupes nommÃ©s comme "Les Lionnes")
    - Groupes standards (community, vip, promo)
    - TOUS les utilisateurs de la collection users
    """
    try:
        conversations = []
        seen_user_ids = set()  # Pour Ã©viter les doublons d'utilisateurs
        
        # 1. RÃ©cupÃ©rer TOUTES les sessions de chat avec titre (GROUPES NOMMÃS)
        sessions = await db.chat_sessions.find(
            {"is_deleted": {"$ne": True}},
            {"_id": 0, "id": 1, "mode": 1, "title": 1, "participant_ids": 1, "created_at": 1, "last_message_at": 1, "updated_at": 1}
        ).sort("updated_at", -1).to_list(500)
        
        for session in sessions:
            try:
                session_id = session.get("id", "")
                mode = session.get("mode", "user")
                title = session.get("title", "")
                participant_ids = session.get("participant_ids", [])
                
                # GROUPES : Sessions avec titre OU mode groupe
                if title and title.strip():
                    # Session avec titre = Groupe nommÃ© (comme "Les Lionnes")
                    conversations.append({
                        "conversation_id": session_id,
                        "name": f"ð¥ {title.strip()}",
                        "type": "group",
                        "mode": mode,
                        "title": title.strip(),
                        "last_activity": session.get("updated_at") or session.get("last_message_at") or session.get("created_at", "")
                    })
                elif mode in ["community", "vip", "promo", "group"]:
                    # Mode groupe standard - uniquement si pas encore ajoutÃ©
                    mode_names = {
                        "community": "ð CommunautÃ©",
                        "vip": "â­ Groupe VIP",
                        "promo": "ð Offres SpÃ©ciales",
                        "group": "ð¥ Groupe"
                    }
                    conversations.append({
                        "conversation_id": session_id,
                        "name": mode_names.get(mode, f"ð¥ Groupe {mode}"),
                        "type": "group",
                        "mode": mode,
                        "title": "",
                        "last_activity": session.get("updated_at") or ""
                    })
                else:
                    # Session utilisateur - noter les IDs pour Ã©viter les doublons
                    for pid in participant_ids:
                        seen_user_ids.add(pid)
                        
            except Exception as session_err:
                logger.warning(f"[CONVERSATIONS-ACTIVE] Erreur session {session.get('id', '?')}: {session_err}")
                continue
        
        # 2. Ajouter les groupes standards s'ils n'existent pas
        standard_groups = [
            {"conversation_id": "community", "name": "ð CommunautÃ© GÃ©nÃ©rale", "type": "group", "mode": "community"},
            {"conversation_id": "vip", "name": "â­ Groupe VIP", "type": "group", "mode": "vip"},
            {"conversation_id": "promo", "name": "ð Offres SpÃ©ciales", "type": "group", "mode": "promo"}
        ]
        
        existing_ids = [c["conversation_id"] for c in conversations]
        for group in standard_groups:
            if group["conversation_id"] not in existing_ids:
                conversations.append(group)
        
        # 3. RÃ©cupÃ©rer TOUS les utilisateurs de la collection users
        all_users = await db.users.find(
            {},
            {"_id": 0, "id": 1, "name": 1, "email": 1, "created_at": 1}
        ).sort("name", 1).to_list(500)
        
        # Ãviter les doublons (mÃªme email)
        seen_emails = set()
        for user in all_users:
            try:
                user_id = user.get("id", "")
                user_name = (user.get("name") or "").strip()
                user_email = (user.get("email") or "").strip().lower()
                
                # Ignorer les utilisateurs sans ID
                if not user_id:
                    continue
                
                # NOTE: Plus de dÃ©duplication par email - on inclut TOUS les users
                # Ãviter seulement les doublons par ID
                if user_id in seen_user_ids:
                    continue
                seen_user_ids.add(user_id)
                
                # Construire le nom d'affichage (fallback sur email si pas de nom)
                if user_name:
                    display_name = f"ð¤ {user_name}"
                    if user_email:
                        display_name += f" ({user_email})"
                elif user_email:
                    display_name = f"ð¤ {user_email}"
                else:
                    display_name = f"ð¤ Contact {user_id[:8]}"
                
                conversations.append({
                    "conversation_id": user_id,  # Utilise l'ID utilisateur pour cibler directement
                    "name": display_name,
                    "type": "user",
                    "mode": "user",
                    "title": "",
                    "email": user_email,
                    "last_activity": user.get("created_at", "")
                })
            except Exception as user_err:
                logger.warning(f"[CONVERSATIONS-ACTIVE] Erreur user: {user_err}")
                continue
        
        # 4. Trier: groupes d'abord (par nom), puis utilisateurs (par nom)
        conversations.sort(key=lambda x: (
            0 if x["type"] == "group" else 1,
            x.get("name", "").lower()
        ))
        
        # Compter les rÃ©sultats
        groups_count = len([c for c in conversations if c["type"] == "group"])
        users_count = len([c for c in conversations if c["type"] == "user"])
        logger.info(f"[CONVERSATIONS-ACTIVE] {len(conversations)} conversations trouvÃ©es ({groups_count} groupes, {users_count} utilisateurs)")
        
        return {
            "success": True,
            "conversations": conversations,
            "total": len(conversations),
            "groups_count": groups_count,
            "users_count": users_count
        }
        
    except Exception as e:
        logger.error(f"[CONVERSATIONS-ACTIVE] Erreur: {e}")
        return {
            "success": False,
            "conversations": [],
            "error": str(e)
        }

# --- Rejoindre un groupe automatiquement (adhÃ©sion via lien) ---
class GroupJoinRequest(BaseModel):
    group_id: str
    email: str
    name: str = ""
    user_id: str = None

@api_router.post("/groups/join")
async def join_group_automatically(request: GroupJoinRequest):
    """
    Permet Ã  un utilisateur dÃ©jÃ  connectÃ© de rejoindre un groupe via un lien ?group=ID.
    UtilisÃ© pour l'adhÃ©sion automatique sans re-saisie d'email.
    """
    try:
        group_id = request.group_id
        email = request.email
        name = request.name or email.split('@')[0]
        user_id = request.user_id
        
        logger.info(f"[GROUP-JOIN] ð Tentative adhÃ©sion: {email} -> groupe {group_id}")
        
        # VÃ©rifier si le groupe existe
        # Chercher dans les sessions avec ce ID ou ce mode
        group_session = await db.chat_sessions.find_one(
            {"$or": [
                {"id": group_id},
                {"mode": group_id},
                {"title": {"$regex": group_id, "$options": "i"}}
            ]},
            {"_id": 0}
        )
        
        # Si le groupe n'existe pas, crÃ©er un groupe standard
        if not group_session:
            # VÃ©rifier si c'est un mode standard (community, vip, promo)
            if group_id in ["community", "vip", "promo"]:
                mode_titles = {
                    "community": "Communauté Générale",
                    "vip": "Groupe VIP",
                    "promo": "Offres Spéciales"
                }
                group_session = {
                    "id": f"group_{group_id}_{uuid.uuid4().hex[:8]}",
                    "mode": group_id,
                    "title": mode_titles.get(group_id, f"Groupe {group_id}"),
                    "participant_ids": [],
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                await db.chat_sessions.insert_one(group_session)
                logger.info(f"[GROUP-JOIN] â Nouveau groupe crÃ©Ã©: {group_session['id']}")
            else:
                raise HTTPException(status_code=404, detail=f"Groupe {group_id} non trouvÃ©")
        
        # RÃ©cupÃ©rer ou crÃ©er l'utilisateur
        participant_id = user_id
        if not participant_id:
            # Chercher l'utilisateur par email
            existing_user = await db.users.find_one({"email": email}, {"_id": 0})
            if existing_user:
                participant_id = existing_user.get("id")
            else:
                # CrÃ©er un nouvel utilisateur
                participant_id = str(uuid.uuid4())
                new_user = {
                    "id": participant_id,
                    "name": name,
                    "email": email,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                await db.users.insert_one(new_user)
                logger.info(f"[GROUP-JOIN] â Nouvel utilisateur crÃ©Ã©: {name} ({email})")
        
        # Ajouter l'utilisateur au groupe s'il n'y est pas dÃ©jÃ 
        session_id = group_session.get("id")
        current_participants = group_session.get("participant_ids", [])
        
        if participant_id not in current_participants:
            await db.chat_sessions.update_one(
                {"id": session_id},
                {
                    "$addToSet": {"participant_ids": participant_id},
                    "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
                }
            )
            logger.info(f"[GROUP-JOIN] â {name} ajoutÃ© au groupe {session_id}")
        else:
            logger.info(f"[GROUP-JOIN] â¹ï¸ {name} dÃ©jÃ  membre du groupe {session_id}")
        
        return {
            "success": True,
            "message": f"Bienvenue dans le groupe {group_session.get('title', group_id)} !",
            "conversation_id": session_id,
            "group_name": group_session.get("title", ""),
            "participant_id": participant_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GROUP-JOIN] â Erreur: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Chat Sessions ---
@api_router.get("/chat/sessions")
async def get_chat_sessions(include_deleted: bool = False, request: Request = None):
    """RÃ©cupÃ¨re toutes les sessions de chat (exclut les supprimÃ©es par dÃ©faut)
    v14.0: Enrichit avec participantName et participantEmail pour l'affichage CRM
    v14.7: Filtrage par coach_id pour l'Ã©tanchÃ©itÃ© (Super Admin voit tout)
    """
    # v14.7: RÃ©cupÃ©rer l'email du caller pour le filtrage
    caller_email = ""
    if request:
        try:
            caller_email = require_auth(request)
        except HTTPException:
            caller_email = ""
    
    # Base query
    query = {} if include_deleted else {"is_deleted": {"$ne": True}}
    
    # v14.7: Super Admin voit tout, Coach voit uniquement ses sessions
    if caller_email and not is_super_admin(caller_email):
        query["coach_id"] = caller_email
    
    sessions = await db.chat_sessions.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    
    # v14.0: Enrichir chaque session avec les infos du premier participant
    enriched_sessions = []
    for session in sessions:
        participant_name = ""
        participant_email = ""
        participant_whatsapp = ""

        # v108: Chercher dans participant_ids â fallback users + affichage multi-membres pour groupes
        is_group_session = session.get("mode") == "group" or session.get("group_id")
        all_member_names = []

        for pid in session.get("participant_ids", []):
            p = await db.chat_participants.find_one({"id": pid}, {"_id": 0, "name": 1, "email": 1, "whatsapp": 1})
            if not p:
                # v108: Fallback vers users
                p = await db.users.find_one({"id": pid}, {"_id": 0, "name": 1, "email": 1})
            if p:
                pname = p.get("name", "")
                if not participant_name:
                    participant_name = pname
                    participant_email = p.get("email", "")
                    participant_whatsapp = p.get("whatsapp", "")
                if pname:
                    all_member_names.append(pname)
                if not is_group_session:
                    break  # Pour les conversations privÃ©es, 1 seul nom suffit

        # v108: Pour les groupes, afficher tous les noms des membres
        if is_group_session and all_member_names:
            participant_name = ", ".join(all_member_names[:4])
            if len(all_member_names) > 4:
                participant_name += f" +{len(all_member_names) - 4}"

        # Fallback sur le titre de la session
        if not participant_name and session.get("title"):
            participant_name = session.get("title")
        
        # RÃ©cupÃ©rer le dernier message
        last_message = await db.chat_messages.find_one(
            {"session_id": session.get("id"), "is_deleted": {"$ne": True}},
            {"_id": 0, "content": 1},
            sort=[("created_at", -1)]
        )
        
        # Compter les messages
        message_count = await db.chat_messages.count_documents({
            "session_id": session.get("id"),
            "is_deleted": {"$ne": True}
        })
        
        enriched_sessions.append({
            **session,
            "participantName": participant_name,
            "participantEmail": participant_email,
            "participantWhatsapp": participant_whatsapp,
            "lastMessage": last_message.get("content", "")[:100] if last_message else "Nouvelle conversation",
            "messageCount": message_count
        })
    
    return enriched_sessions

# === CRM AVANCÃ - HISTORIQUE CONVERSATIONS ===
@api_router.get("/conversations")
async def get_conversations_advanced(
    request: Request,
    page: int = 1,
    limit: int = 20,
    query: str = "",
    include_deleted: bool = False
):
    """
    Endpoint CRM avancÃ© pour les conversations avec pagination et recherche.
    v14.7: Filtrage par coach_id pour l'Ã©tanchÃ©itÃ© (Super Admin voit tout)
    
    ParamÃ¨tres:
    - page: NumÃ©ro de page (commence Ã  1)
    - limit: Nombre d'Ã©lÃ©ments par page (max 100)
    - query: Recherche dans les noms de participants, emails, contenus de messages
    - include_deleted: Inclure les sessions supprimÃ©es
    
    Retourne:
    - conversations: Liste des conversations enrichies avec dernier message et date
    - total: Nombre total de conversations
    - page: Page actuelle
    - pages: Nombre total de pages
    - has_more: Indique s'il y a plus de pages
    """
    import re

    # v14.7: RÃ©cupÃ©rer l'email du caller pour le filtrage
    try:
        caller_email = require_auth(request)
    except HTTPException:
        caller_email = ""
    
    # Limiter Ã  100 max
    limit = min(limit, 100)
    skip = (page - 1) * limit
    
    # Query de base pour les sessions
    base_query = {} if include_deleted else {"is_deleted": {"$ne": True}}
    
    # v14.7: Super Admin voit tout, Coach voit uniquement ses sessions
    if caller_email and not is_super_admin(caller_email):
        base_query["coach_id"] = caller_email
    
    # Si recherche, d'abord trouver les participants correspondants
    matching_participant_ids = []
    matching_session_ids = []
    
    if query and query.strip():
        search_regex = {"$regex": re.escape(query), "$options": "i"}
        
        # Rechercher dans les participants
        matching_participants = await db.chat_participants.find({
            "$or": [
                {"name": search_regex},
                {"email": search_regex},
                {"whatsapp": search_regex}
            ]
        }, {"_id": 0, "id": 1}).to_list(500)
        matching_participant_ids = [p["id"] for p in matching_participants]
        
        # Rechercher dans les messages
        matching_messages = await db.chat_messages.find({
            "content": search_regex,
            "is_deleted": {"$ne": True}
        }, {"_id": 0, "session_id": 1}).to_list(500)
        matching_session_ids = list(set([m["session_id"] for m in matching_messages]))
        
        # Rechercher dans les titres de session
        title_sessions = await db.chat_sessions.find({
            "title": search_regex,
            **base_query
        }, {"_id": 0, "id": 1}).to_list(500)
        matching_session_ids.extend([s["id"] for s in title_sessions])
        matching_session_ids = list(set(matching_session_ids))
        
        # Construire la query finale
        if matching_participant_ids or matching_session_ids:
            base_query["$or"] = []
            if matching_participant_ids:
                base_query["$or"].append({"participant_ids": {"$in": matching_participant_ids}})
            if matching_session_ids:
                base_query["$or"].append({"id": {"$in": matching_session_ids}})
        else:
            # Aucun rÃ©sultat
            return {
                "conversations": [],
                "total": 0,
                "page": page,
                "pages": 0,
                "has_more": False
            }
    
    # Compter le total
    total = await db.chat_sessions.count_documents(base_query)
    pages = (total + limit - 1) // limit
    
    # RÃ©cupÃ©rer les sessions paginÃ©es
    sessions = await db.chat_sessions.find(
        base_query, 
        {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    
    # Enrichir chaque session avec le dernier message et les infos participant
    enriched_conversations = []
    
    for session in sessions:
        # RÃ©cupÃ©rer le dernier message
        last_message = await db.chat_messages.find_one(
            {"session_id": session["id"], "is_deleted": {"$ne": True}},
            {"_id": 0},
            sort=[("created_at", -1)]
        )
        
        # v108.2: RÃ©cupÃ©rer les infos des participants â fallback vers users
        participants_info = []
        for pid in session.get("participant_ids", []):
            participant = await db.chat_participants.find_one({"id": pid}, {"_id": 0})
            if not participant:
                # v108.2: Fallback vers la collection users
                participant = await db.users.find_one({"id": pid}, {"_id": 0})
            if participant:
                participants_info.append({
                    "id": participant.get("id", pid),
                    "name": participant.get("name", "Inconnu"),
                    "email": participant.get("email", ""),
                    "whatsapp": participant.get("whatsapp", participant.get("phone", "")),
                    "source": participant.get("source", "")
                })

        # Compter le nombre de messages
        message_count = await db.chat_messages.count_documents({
            "session_id": session["id"],
            "is_deleted": {"$ne": True}
        })

        # v108.2: Pour les groupes, afficher TOUS les noms des membres
        is_group_session = session.get("mode") == "group" or session.get("group_id")
        first_participant_name = ""
        first_participant_email = ""
        first_participant_whatsapp = ""
        if participants_info:
            first_participant_name = participants_info[0].get("name", "")
            first_participant_email = participants_info[0].get("email", "")
            first_participant_whatsapp = participants_info[0].get("whatsapp", "")

        # v108.2: Pour les groupes, concatÃ©ner tous les noms
        if is_group_session and len(participants_info) > 1:
            all_names = [p.get("name", "") for p in participants_info if p.get("name")]
            if all_names:
                first_participant_name = ", ".join(all_names[:4])
                if len(all_names) > 4:
                    first_participant_name += f" +{len(all_names) - 4}"

        # Fallback sur le titre de la session (pour les liens nommÃ©s)
        if not first_participant_name and session.get("title"):
            first_participant_name = session.get("title")

        enriched_conversations.append({
            **session,
            "participants": participants_info,
            "participantName": first_participant_name,  # v14.0: Pour l'affichage CRM
            "participantEmail": first_participant_email,  # v14.0: Pour l'affichage CRM
            "participantWhatsapp": first_participant_whatsapp,  # v16.0: WhatsApp pour CRM
            "lastMessage": last_message.get("content", "")[:100] if last_message else "Nouvelle conversation",
            "last_message": {
                "content": last_message.get("content", "")[:100] if last_message else "",
                "sender_name": last_message.get("sender_name", "") if last_message else "",
                "sender_type": last_message.get("sender_type", "") if last_message else "",
                "created_at": last_message.get("created_at", "") if last_message else ""
            } if last_message else None,
            "message_count": message_count,
            "messageCount": message_count  # v14.0: Alias pour compatibilitÃ© frontend
        })
    
    logger.info(f"[CRM] Conversations: page={page}, limit={limit}, query='{query}', total={total}")
    
    return {
        "conversations": enriched_conversations,
        "total": total,
        "page": page,
        "pages": pages,
        "has_more": page < pages
    }

@api_router.get("/chat/sessions/{session_id}")
async def get_chat_session(session_id: str):
    """RÃ©cupÃ¨re une session par son ID"""
    session = await db.chat_sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvÃ©e")
    return session

@api_router.get("/chat/sessions/by-token/{link_token}")
async def get_chat_session_by_token(link_token: str):
    """
    RÃ©cupÃ¨re une session par son token de partage.
    UtilisÃ© quand un utilisateur arrive via un lien partagÃ©.
    """
    session = await db.chat_sessions.find_one(
        {"link_token": link_token, "is_deleted": {"$ne": True}}, 
        {"_id": 0}
    )
    if not session:
        raise HTTPException(status_code=404, detail="Lien invalide ou session expirÃ©e")
    return session

@api_router.post("/chat/sessions")
async def create_chat_session(session: ChatSessionCreate):
    """CrÃ©e une nouvelle session de chat"""
    session_obj = ChatSession(**session.model_dump())
    await db.chat_sessions.insert_one(session_obj.model_dump())
    return session_obj.model_dump()

@api_router.put("/chat/sessions/{session_id}")
async def update_chat_session(session_id: str, update: ChatSessionUpdate):
    """
    Met Ã  jour une session de chat.
    UtilisÃ© pour changer le mode (IA/Humain/Communautaire) ou supprimer logiquement.
    """
    logger.info(f"[DELETE] Mise Ã  jour session {session_id}: {update.model_dump()}")
    
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    # Si suppression logique, ajouter la date
    if update_data.get("is_deleted"):
        update_data["deleted_at"] = datetime.now(timezone.utc).isoformat()
        logger.info(f"[DELETE] Session {session_id} marquÃ©e comme supprimÃ©e (is_deleted=True)")
    
    result = await db.chat_sessions.update_one(
        {"id": session_id},
        {"$set": update_data}
    )
    logger.info(f"[DELETE] RÃ©sultat update: matched={result.matched_count}, modified={result.modified_count}")
    
    updated = await db.chat_sessions.find_one({"id": session_id}, {"_id": 0})
    return updated

@api_router.post("/chat/sessions/{session_id}/add-participant")
async def add_participant_to_session(session_id: str, participant_id: str):
    """Ajoute un participant Ã  une session existante"""
    session = await db.chat_sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvÃ©e")
    
    # VÃ©rifier que le participant existe
    participant = await db.chat_participants.find_one({"id": participant_id}, {"_id": 0})
    if not participant:
        raise HTTPException(status_code=404, detail="Participant non trouvÃ©")
    
    # Ajouter le participant s'il n'est pas dÃ©jÃ  prÃ©sent
    if participant_id not in session.get("participant_ids", []):
        await db.chat_sessions.update_one(
            {"id": session_id},
            {
                "$push": {"participant_ids": participant_id},
                "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
            }
        )
    
    updated = await db.chat_sessions.find_one({"id": session_id}, {"_id": 0})
    return updated

@api_router.post("/chat/sessions/{session_id}/toggle-ai")
async def toggle_session_ai(session_id: str):
    """
    Bascule l'Ã©tat de l'IA pour une session.
    Si l'IA est active, elle devient inactive et inversement.
    """
    session = await db.chat_sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvÃ©e")
    
    new_state = not session.get("is_ai_active", True)
    new_mode = "ai" if new_state else "human"

    await db.chat_sessions.update_one(
        {"id": session_id},
        {"$set": {
            "is_ai_active": new_state,
            "mode": new_mode,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )

    # v16.0: InsÃ©rer un message systÃ¨me visible pour le visiteur
    system_text = "ð¤ L'assistant IA est de retour" if new_state else "ð¢ Un conseiller humain a pris le relais"
    system_msg = {
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "sender_type": "system",
        "sender_name": "SystÃ¨me",
        "sender_id": "system",
        "content": system_text,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_deleted": False
    }
    await db.chat_messages.insert_one(system_msg)

    updated = await db.chat_sessions.find_one({"id": session_id}, {"_id": 0})
    return updated

# --- Chat Messages ---
@api_router.get("/chat/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, include_deleted: bool = False):
    """Recupere tous les messages d'une session avec format unifie.
    V107.8: Auto-dÃ©tecte et fusionne les sessions dupliquÃ©es cÃ´tÃ© coach.
    """
    # V107.9: VÃ©rifier s'il existe des sessions dupliquÃ©es Ã  fusionner
    # Cross-rÃ©fÃ©rence via chat_participants pour trouver TOUTES les sessions du mÃªme abonnÃ©
    session = await db.chat_sessions.find_one({"id": session_id, "is_deleted": {"$ne": True}}, {"_id": 0})
    if session:
        participant_email = session.get("participantEmail", "")
        participant_ids = list(session.get("participant_ids", []))

        # V107.9: RÃ©soudre TOUS les participant_ids liÃ©s Ã  cet email via chat_participants
        all_pids = set(participant_ids)
        resolved_email = participant_email

        # Si on a un email, chercher le participant_id correspondant
        if participant_email:
            participant = await db.chat_participants.find_one(
                {"email": {"$regex": f"^{participant_email}$", "$options": "i"}},
                {"_id": 0, "id": 1}
            )
            if participant:
                all_pids.add(participant["id"])

        # Si on a des participant_ids, rÃ©soudre leurs emails
        if participant_ids:
            for pid in participant_ids:
                p = await db.chat_participants.find_one({"id": pid}, {"_id": 0, "email": 1})
                if p and p.get("email"):
                    resolved_email = resolved_email or p["email"]
                    # Chercher d'autres participants avec le mÃªme email
                    same_email_ps = await db.chat_participants.find(
                        {"email": {"$regex": f"^{p['email']}$", "$options": "i"}},
                        {"_id": 0, "id": 1}
                    ).to_list(10)
                    for sp in same_email_ps:
                        all_pids.add(sp["id"])

        # Construire les requÃªtes de recherche de sessions dupliquÃ©es
        merge_queries = []
        if resolved_email:
            merge_queries.append({"participantEmail": {"$regex": f"^{resolved_email}$", "$options": "i"}})
        if all_pids:
            merge_queries.append({"participant_ids": {"$in": list(all_pids)}})

        if merge_queries and session.get("mode") not in ("group", "community"):
            other_sessions = await db.chat_sessions.find(
                {
                    "$or": merge_queries,
                    "id": {"$ne": session_id},
                    "is_deleted": {"$ne": True},
                    "mode": {"$nin": ["community", "group"]},
                    "group_id": {"$exists": False},
                },
                {"_id": 0}
            ).to_list(10)

            for other in other_sessions:
                # Double-check: exclure les sessions de groupe
                if other.get("is_group") or other.get("group_id") or other.get("mode") == "group":
                    continue
                # Fusionner: migrer les messages de l'autre session vers celle-ci
                migrated = await db.chat_messages.update_many(
                    {"session_id": other["id"]},
                    {"$set": {"session_id": session_id}}
                )
                # Fusionner les participant_ids
                for pid in other.get("participant_ids", []):
                    if pid not in participant_ids:
                        await db.chat_sessions.update_one(
                            {"id": session_id},
                            {"$push": {"participant_ids": pid}}
                        )
                        participant_ids.append(pid)
                # Copier participantEmail si manquant
                if not participant_email and other.get("participantEmail"):
                    participant_email = other["participantEmail"]
                    await db.chat_sessions.update_one(
                        {"id": session_id},
                        {"$set": {"participantEmail": participant_email}}
                    )
                # Soft-delete l'autre session
                await db.chat_sessions.update_one(
                    {"id": other["id"]},
                    {"$set": {"is_deleted": True, "merged_into": session_id}}
                )
                logger.info(f"[V107.9] FUSION: {other['id'][:8]} â {session_id[:8]} ({migrated.modified_count} msgs, pids={list(all_pids)[:3]})")

    query = {"session_id": session_id}
    if not include_deleted: query["is_deleted"] = {"$ne": True}
    raw = await db.chat_messages.find(query, {"_id": 0}).sort("created_at", 1).to_list(500)
    return [format_message_for_frontend(m) for m in raw]

# V107.10: Restaurer les sessions supprimÃ©es par erreur lors de la fusion
@api_router.post("/chat/sessions/restore-merged")
async def restore_merged_sessions():
    """
    V107.10: Restaure toutes les sessions qui ont Ã©tÃ© merged par erreur
    (sessions de groupe, community, ou sessions avec group_id)
    """
    restored = []
    # Trouver toutes les sessions supprimÃ©es avec merged_into
    deleted_sessions = await db.chat_sessions.find(
        {"merged_into": {"$exists": True}, "is_deleted": True},
        {"_id": 0}
    ).to_list(100)

    for sess in deleted_sessions:
        # Restaurer les sessions de groupe/community supprimÃ©es par erreur
        should_restore = (
            sess.get("mode") in ("group", "community") or
            sess.get("group_id") or
            sess.get("is_group")
        )
        if should_restore:
            merged_into = sess.get("merged_into")
            # Restaurer les messages qui ont Ã©tÃ© migrÃ©s
            if merged_into:
                await db.chat_messages.update_many(
                    {"session_id": merged_into, "original_session_id": sess["id"]},
                    {"$set": {"session_id": sess["id"]}}
                )
            # Restaurer la session
            await db.chat_sessions.update_one(
                {"id": sess["id"]},
                {"$set": {"is_deleted": False}, "$unset": {"merged_into": ""}}
            )
            restored.append(sess["id"])
            logger.info(f"[V107.10] Session restaurÃ©e: {sess['id'][:8]} (mode={sess.get('mode')}, group_id={sess.get('group_id', 'N/A')[:8] if sess.get('group_id') else 'N/A'})")

    # Aussi restaurer les sessions de conversation directe supprimÃ©es par erreur
    # qui ont des modes normaux (ai, human, bot)
    all_merged = await db.chat_sessions.find(
        {"merged_into": {"$exists": True}, "is_deleted": True, "mode": {"$in": ["ai", "human", "bot", None]}},
        {"_id": 0}
    ).to_list(100)
    for sess in all_merged:
        # Restaurer si elle a Ã©tÃ© fusionnÃ©e rÃ©cemment (merged_into existe)
        await db.chat_sessions.update_one(
            {"id": sess["id"]},
            {"$set": {"is_deleted": False}, "$unset": {"merged_into": ""}}
        )
        restored.append(sess["id"])
        logger.info(f"[V107.10] Session directe restaurÃ©e: {sess['id'][:8]}")

    return {"success": True, "restored_count": len(restored), "restored_ids": restored}

# v8.6: Endpoint messages de groupe
@api_router.get("/chat/group/messages")
async def get_group_messages(limit: int = 100):
    """Recupere les messages de groupe (is_group=True ou session_id=group)"""
    query = {"$or": [{"is_group": True}, {"session_id": "group"}], "is_deleted": {"$ne": True}}
    raw = await db.chat_messages.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return [format_message_for_frontend(m) for m in reversed(raw)]
# === ENDPOINT SYNC "RAMASSER" ===
@api_router.get("/messages/sync")
async def sync_messages(session_id: str, since: Optional[str] = None, limit: int = 100):
    """V146: RAMASSER â Messages UNIQUEMENT de la session demandÃ©e. Plus de fuite broadcast/group."""
    # V146: FIX â Ne plus inclure broadcast/group dans les sessions privÃ©es
    # Chaque session ne reÃ§oit QUE ses propres messages (isolation stricte)
    base_query = {"is_deleted": {"$ne": True}, "session_id": session_id}
    if since:
        try:
            if 'Z' in since: since = since.replace('Z', '+00:00')
            parsed = datetime.fromisoformat(since)
            if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=timezone.utc)
            base_query["created_at"] = {"$gt": parsed.astimezone(timezone.utc).isoformat()}
        except Exception:
            base_query["created_at"] = {"$gt": since}
    # Tri deterministe: created_at puis id pour garantir un ordre stable
    raw = await db.chat_messages.find(base_query, {"_id": 0}).sort([("created_at", 1), ("id", 1)]).to_list(limit)
    messages = [format_message_for_frontend(m) for m in raw]
    sync_ts = datetime.now(timezone.utc).isoformat()
    return {"success": True, "session_id": session_id, "count": len(messages), "messages": messages, "synced_at": sync_ts, "server_time_utc": sync_ts}
@api_router.get("/messages/sync/all")
async def sync_all_messages(participant_id: str, since: Optional[str] = None, limit: int = 200):
    """
    RAMASSER TOUT: RÃ©cupÃ¨re tous les messages du participant (toutes sessions).
    Pour synchronisation complÃ¨te au rÃ©veil du mobile.
    """
    # Trouver toutes les sessions du participant
    sessions = await db.chat_sessions.find(
        {"$or": [
            {"participant_ids": participant_id},
            {"mode": "community"}  # Inclure la session communautaire
        ]},
        {"_id": 0, "id": 1}
    ).to_list(100)
    
    session_ids = [s["id"] for s in sessions]
    
    query = {
        "session_id": {"$in": session_ids},
        "is_deleted": {"$ne": True}
    }
    
    if since:
        query["created_at"] = {"$gt": since}
    
    messages = await db.chat_messages.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).to_list(limit)
    
    logger.info(f"[SYNC-ALL] ð± RamassÃ© {len(messages)} message(s) pour {participant_id[:8]}...")
    
    return {
        "success": True,
        "participant_id": participant_id,
        "sessions_count": len(session_ids),
        "messages_count": len(messages),
        "messages": messages,
        "synced_at": datetime.now(timezone.utc).isoformat()
    }
@api_router.post("/chat/messages")
async def create_chat_message(message: EnhancedChatMessageCreate):
    """
    CrÃ©e un nouveau message dans une session.
    Met Ã  jour automatiquement le mode du message selon l'Ã©tat de la session.
    """
    # RÃ©cupÃ©rer la session pour connaÃ®tre le mode actuel
    session = await db.chat_sessions.find_one({"id": message.session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvÃ©e")
    
    message_obj = EnhancedChatMessage(
        **message.model_dump(),
        mode=session.get("mode", "ai")
    )
    await db.chat_messages.insert_one(message_obj.model_dump())
    return message_obj.model_dump()

@api_router.put("/chat/messages/{message_id}/delete")
async def soft_delete_message(message_id: str):
    """Suppression logique d'un message"""
    await db.chat_messages.update_one(
        {"id": message_id},
        {"$set": {
            "is_deleted": True,
            "deleted_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    return {"success": True, "message": "Message marquÃ© comme supprimÃ©"}

# === ROUTES ADMIN SÃCURISÃES ===

@api_router.post("/admin/delete-history")
async def admin_delete_history(request: Request):
    """
    Suppression de l'historique d'une session - ADMIN ONLY.
    VÃ©rifie que l'email de l'appelant est celui du coach.
    """
    body = await request.json()
    session_id = body.get("session_id")
    caller_email = body.get("email", "").lower().strip()
    
    # ===== VÃRIFICATION SÃCURITÃ : EMAIL COACH OBLIGATOIRE =====
    if caller_email != COACH_EMAIL:
        logger.warning(f"[SECURITY] Tentative non autorisÃ©e de suppression d'historique par: {caller_email}")
        raise HTTPException(
            status_code=403, 
            detail="AccÃ¨s refusÃ©. Seul le coach peut supprimer l'historique."
        )
    
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id requis")
    
    # Suppression logique de tous les messages de la session
    result = await db.chat_messages.update_many(
        {"session_id": session_id},
        {"$set": {
            "is_deleted": True,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": caller_email
        }}
    )
    
    logger.info(f"[ADMIN] Historique supprimÃ© pour session {session_id} par {caller_email}. {result.modified_count} messages.")
    
    return {
        "success": True, 
        "message": f"Historique supprimÃ© ({result.modified_count} messages)",
        "deleted_count": result.modified_count
    }

@api_router.post("/admin/change-identity")
async def admin_change_identity(request: Request):
    """
    Changement d'identitÃ© d'un participant - ADMIN ONLY.
    VÃ©rifie que l'email de l'appelant est celui du coach.
    """
    body = await request.json()
    participant_id = body.get("participant_id")
    caller_email = body.get("email", "").lower().strip()
    
    # ===== VÃRIFICATION SÃCURITÃ : EMAIL COACH OBLIGATOIRE =====
    if caller_email != COACH_EMAIL:
        logger.warning(f"[SECURITY] Tentative non autorisÃ©e de changement d'identitÃ© par: {caller_email}")
        raise HTTPException(
            status_code=403, 
            detail="AccÃ¨s refusÃ©. Seul le coach peut changer l'identitÃ©."
        )
    
    if not participant_id:
        raise HTTPException(status_code=400, detail="participant_id requis")
    
    logger.info(f"[ADMIN] Changement d'identitÃ© demandÃ© pour {participant_id} par {caller_email}")
    
    return {
        "success": True, 
        "message": "IdentitÃ© rÃ©initialisÃ©e. L'utilisateur devra se reconnecter."
    }

# === MESSAGERIE PRIVÃE (MP) - ISOLÃE DE L'IA ===

@api_router.post("/private/conversations")
async def create_or_get_private_conversation(request: Request):
    """
    CrÃ©e ou rÃ©cupÃ¨re une conversation privÃ©e entre deux participants.
    Les MP sont stockÃ©es dans une collection sÃ©parÃ©e et INVISIBLES pour l'IA.
    """
    body = await request.json()
    participant_1_id = body.get("participant_1_id")
    participant_1_name = body.get("participant_1_name")
    participant_2_id = body.get("participant_2_id")
    participant_2_name = body.get("participant_2_name")
    
    if not all([participant_1_id, participant_2_id]):
        raise HTTPException(status_code=400, detail="IDs des participants requis")
    
    # VÃ©rifier si une conversation existe dÃ©jÃ  (dans les deux sens)
    existing = await db.private_conversations.find_one({
        "$or": [
            {"participant_1_id": participant_1_id, "participant_2_id": participant_2_id},
            {"participant_1_id": participant_2_id, "participant_2_id": participant_1_id}
        ]
    }, {"_id": 0})
    
    if existing:
        logger.info(f"[MP] Conversation existante trouvÃ©e: {existing.get('id')}")
        return existing
    
    # CrÃ©er une nouvelle conversation
    conversation = PrivateConversation(
        participant_1_id=participant_1_id,
        participant_1_name=participant_1_name or "Membre",
        participant_2_id=participant_2_id,
        participant_2_name=participant_2_name or "Membre"
    )
    await db.private_conversations.insert_one(conversation.model_dump())
    logger.info(f"[MP] Nouvelle conversation crÃ©Ã©e: {conversation.id}")
    return conversation.model_dump()

@api_router.get("/private/conversations/{participant_id}")
async def get_private_conversations(participant_id: str):
    """
    RÃ©cupÃ¨re toutes les conversations privÃ©es d'un participant.
    """
    conversations = await db.private_conversations.find({
        "$or": [
            {"participant_1_id": participant_id},
            {"participant_2_id": participant_id}
        ]
    }, {"_id": 0}).sort("last_message_at", -1).to_list(50)
    return conversations

@api_router.post("/private/messages")
async def send_private_message(request: Request):
    """
    Envoie un message privÃ©. Ces messages sont ISOLÃS de l'IA.
    """
    body = await request.json()
    conversation_id = body.get("conversation_id")
    sender_id = body.get("sender_id")
    sender_name = body.get("sender_name")
    recipient_id = body.get("recipient_id")
    recipient_name = body.get("recipient_name")
    content = body.get("content")
    
    if not all([conversation_id, sender_id, content]):
        raise HTTPException(status_code=400, detail="DonnÃ©es manquantes")
    
    # CrÃ©er le message privÃ©
    message = PrivateMessage(
        conversation_id=conversation_id,
        sender_id=sender_id,
        sender_name=sender_name or "Membre",
        recipient_id=recipient_id or "",
        recipient_name=recipient_name or "Membre",
        content=content
    )
    await db.private_messages.insert_one(message.model_dump())
    
    # Mettre Ã  jour la conversation avec le dernier message
    await db.private_conversations.update_one(
        {"id": conversation_id},
        {"$set": {
            "last_message": content[:100],
            "last_message_at": message.created_at
        }}
    )
    
    # === SOCKET.IO: Ãmettre le message privÃ© en temps rÃ©el ===
    # Socket.IO dÃ©sactivÃ© en mode Vercel Serverless
    logger.debug(f"[SOCKET.IO] Message privÃ© (disabled in Vercel Serverless) envoyÃ© dans {conversation_id}")
    
    logger.info(f"[MP] Message envoyÃ© de {sender_name} dans conversation {conversation_id}")
    return message.model_dump()

@api_router.get("/private/messages/{conversation_id}")
async def get_private_messages(conversation_id: str, limit: int = 100):
    """
    RÃ©cupÃ¨re les messages d'une conversation privÃ©e.
    """
    messages = await db.private_messages.find(
        {"conversation_id": conversation_id, "is_deleted": {"$ne": True}},
        {"_id": 0}
    ).sort("created_at", 1).to_list(limit)
    return messages

@api_router.put("/private/messages/read/{conversation_id}")
async def mark_private_messages_read(conversation_id: str, reader_id: str):
    """
    Marque tous les messages d'une conversation comme lus par un participant.
    """
    result = await db.private_messages.update_many(
        {"conversation_id": conversation_id, "recipient_id": reader_id, "is_read": False},
        {"$set": {"is_read": True}}
    )
    return {"success": True, "marked_read": result.modified_count}

@api_router.get("/private/unread/{participant_id}")
async def get_unread_private_count(participant_id: str):
    """
    Compte les messages privÃ©s non lus pour un participant.
    """
    count = await db.private_messages.count_documents({
        "recipient_id": participant_id,
        "is_read": False,
        "is_deleted": {"$ne": True}
    })
    return {"unread_count": count}

# === UPLOAD PHOTO DE PROFIL (LEGACY REDIRECT) ===
# L'ancien endpoint redirige vers le nouveau moteur /users/upload-photo

@api_router.post("/upload/profile-photo")
async def upload_profile_photo_legacy(file: UploadFile = File(...), participant_id: str = Form("guest")):
    """Endpoint legacy - redirige vers /users/upload-photo"""
    return await upload_user_photo(file=file, participant_id=participant_id)

# === NOTIFICATIONS (SONORES ET VISUELLES) ===

@api_router.get("/notifications/unread")
async def get_unread_notifications(
    target: str = "coach",  # "coach" ou "client"
    session_id: Optional[str] = None,
    include_ai: bool = False  # Inclure les rÃ©ponses IA dans les notifications coach
):
    """
    RÃ©cupÃ¨re les messages non notifiÃ©s pour le coach ou un client.
    OptimisÃ© pour le polling toutes les 10 secondes.
    
    ParamÃ¨tres:
    - target: "coach" pour les messages user, "client" pour les rÃ©ponses AI/coach
    - session_id: Optionnel, filtrer par session
    - include_ai: Si true et target=coach, inclut aussi les rÃ©ponses IA (pour suivi)
    
    Retourne:
    - count: Nombre de messages non notifiÃ©s
    - messages: Liste des messages (max 10, triÃ©s par date dÃ©croissante)
    - target: Target demandÃ©
    """
    query = {
        "is_deleted": {"$ne": True},
        "notified": {"$ne": True}
    }
    
    if target == "coach":
        if include_ai:
            # Messages utilisateurs + rÃ©ponses IA (pour suivi)
            query["sender_type"] = {"$in": ["user", "ai"]}
        else:
            # Seulement messages des utilisateurs
            query["sender_type"] = "user"
    else:
        # Messages de l'IA ou du coach destinÃ©s aux clients
        query["sender_type"] = {"$in": ["ai", "coach"]}
    
    if session_id:
        query["session_id"] = session_id
    
    # Compter le nombre total (limitÃ© pour performance)
    count = await db.chat_messages.count_documents(query)
    
    # RÃ©cupÃ©rer les messages non notifiÃ©s les plus rÃ©cents (max 10 pour performance)
    messages = await db.chat_messages.find(
        query, 
        {"_id": 0, "id": 1, "session_id": 1, "sender_name": 1, "sender_type": 1, "content": 1, "created_at": 1}
    ).sort("created_at", -1).limit(10).to_list(10)
    
    return {
        "count": count,
        "messages": messages,
        "target": target
    }

# === EMOJIS PERSONNALISÃS DU COACH ===
@api_router.get("/custom-emojis/list")
async def list_custom_emojis():
    """
    Liste tous les emojis personnalisÃ©s disponibles dans /uploads/emojis/
    """
    emojis = []
    try:
        emoji_files = list(EMOJIS_DIR.glob("*.*"))
        for f in emoji_files:
            if f.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg']:
                emojis.append({
                    "name": f.stem,
                    "url": f"/api/emojis/{f.name}",
                    "filename": f.name
                })
        logger.info(f"[EMOJIS] {len(emojis)} emojis trouvÃ©s")
    except Exception as e:
        logger.error(f"[EMOJIS] Erreur listing: {e}")
    
    return {"emojis": emojis, "count": len(emojis)}

@api_router.post("/custom-emojis/upload")
async def upload_custom_emoji(request: Request):
    """
    Upload un emoji personnalisÃ© (pour le coach).
    Accepte une image en base64 avec un nom.
    """
    import base64
    
    body = await request.json()
    name = body.get("name", "emoji")
    image_data = body.get("image")  # base64 encoded
    file_extension = body.get("extension", "png")
    
    if not image_data:
        raise HTTPException(status_code=400, detail="Image data required")
    
    try:
        # DÃ©coder le base64
        image_bytes = base64.b64decode(image_data.split(",")[-1] if "," in image_data else image_data)
        
        # Sauvegarder le fichier
        filename = f"{name.replace(' ', '_').lower()}.{file_extension}"
        filepath = EMOJIS_DIR / filename
        
        with open(filepath, "wb") as f:
            f.write(image_bytes)
        
        logger.info(f"[EMOJIS] Emoji uploadÃ©: {filename}")
        
        return {
            "success": True,
            "emoji": {
                "name": name,
                "url": f"/api/emojis/{filename}",
                "filename": filename
            }
        }
    except Exception as e:
        logger.error(f"[EMOJIS] Erreur upload: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.put("/notifications/mark-read")
async def mark_notifications_read(request: Request):
    """
    Marque des messages comme notifiÃ©s.
    
    Body:
    - message_ids: Liste des IDs de messages Ã  marquer comme notifiÃ©s
    - all_for_target: "coach" ou "client" pour marquer tous les messages non lus
    - session_id: Optionnel, pour limiter Ã  une session
    """
    body = await request.json()
    message_ids = body.get("message_ids", [])
    all_for_target = body.get("all_for_target")
    session_id = body.get("session_id")
    
    update_count = 0
    
    if message_ids:
        # Marquer des messages spÃ©cifiques
        result = await db.chat_messages.update_many(
            {"id": {"$in": message_ids}},
            {"$set": {"notified": True}}
        )
        update_count = result.modified_count
    
    elif all_for_target:
        # Marquer tous les messages pour un target
        query = {
            "is_deleted": {"$ne": True},
            "notified": {"$ne": True}
        }
        
        if all_for_target == "coach":
            query["sender_type"] = "user"
        else:
            query["sender_type"] = {"$in": ["ai", "coach"]}
        
        if session_id:
            query["session_id"] = session_id
        
        result = await db.chat_messages.update_many(
            query,
            {"$set": {"notified": True}}
        )
        update_count = result.modified_count
    
    logger.info(f"[NOTIFICATIONS] MarquÃ© {update_count} messages comme lus (target: {all_for_target})")
    
    return {
        "success": True,
        "marked_count": update_count
    }

# --- Shareable Links (Liens Partageables) ---
@api_router.post("/chat/generate-link")
async def generate_shareable_link(request: Request):
    """
    GÃ©nÃ¨re un lien partageable unique pour le chat IA.
    Ce lien peut Ãªtre partagÃ© sur les rÃ©seaux sociaux.
    v14.7: Ajoute coach_id pour l'Ã©tanchÃ©itÃ© des donnÃ©es
    
    Body optionnel:
    {
        "title": "Titre du lien",
        "custom_prompt": "Prompt spÃ©cifique (nullable, prioritaire sur campaignPrompt)"
    }
    """
    body = await request.json()
    title = body.get("title", "").strip() or f"Lien-{str(uuid.uuid4())[:6]}"
    custom_prompt = body.get("custom_prompt")
    if custom_prompt and isinstance(custom_prompt, str):
        custom_prompt = custom_prompt.strip() if custom_prompt.strip() else None

    # v98: Champs Ã©tendus pour les liens intelligents
    lead_type = body.get("lead_type", "participant")
    tunnel_questions = body.get("tunnel_questions", [])
    end_actions = body.get("end_actions", [])
    welcome_message = body.get("welcome_message", "")

    # v14.7: RÃ©cupÃ©rer le coach_id pour l'Ã©tanchÃ©itÃ©
    try:
        coach_email = require_auth(request)
    except HTTPException:
        coach_email = ""

    # CrÃ©er une nouvelle session avec un token unique
    session = ChatSession(
        mode="ai",
        is_ai_active=True,
        title=title,
        custom_prompt=custom_prompt
    )

    # v14.7: Ajouter coach_id pour l'Ã©tanchÃ©itÃ© (Super Admin = DEFAULT_COACH_ID)
    session_data = session.model_dump()
    if coach_email and not is_super_admin(coach_email):
        session_data["coach_id"] = coach_email
    else:
        session_data["coach_id"] = DEFAULT_COACH_ID

    # v98: Stocker les champs du lien intelligent
    session_data["lead_type"] = lead_type
    session_data["tunnel_questions"] = tunnel_questions if isinstance(tunnel_questions, list) else []
    session_data["end_actions"] = end_actions if isinstance(end_actions, list) else []
    session_data["welcome_message"] = welcome_message.strip() if isinstance(welcome_message, str) else ""

    await db.chat_sessions.insert_one(session_data)

    # Construire l'URL de partage
    frontend_url = os.environ.get("FRONTEND_URL", "")
    share_url = f"{frontend_url}/chat/{session.link_token}" if frontend_url else f"/chat/{session.link_token}"

    logger.info(f"[CHAT-LINK] Lien cree: {session.link_token} | titre: {title} | custom_prompt: {'oui' if custom_prompt else 'non'} | tunnel: {len(tunnel_questions)} questions | actions: {len(end_actions)}")

    return {
        "link_token": session.link_token,
        "share_url": share_url,
        "session_id": session.id,
        "title": title,
        "custom_prompt": custom_prompt,
        "has_custom_prompt": custom_prompt is not None,
        "lead_type": lead_type,
        "tunnel_questions": tunnel_questions,
        "end_actions": end_actions,
        "welcome_message": welcome_message
    }

@api_router.get("/chat/links")
async def get_all_chat_links():
    """
    RÃ©cupÃ¨re tous les liens de chat gÃ©nÃ©rÃ©s.
    Utile pour le coach pour gÃ©rer ses liens partagÃ©s.
    """
    sessions = await db.chat_sessions.find(
        {"is_deleted": {"$ne": True}},
        {"_id": 0, "id": 1, "link_token": 1, "title": 1, "mode": 1, "is_ai_active": 1, "created_at": 1, "participant_ids": 1, "custom_prompt": 1, "lead_type": 1, "tunnel_questions": 1, "end_actions": 1, "welcome_message": 1}
    ).sort("created_at", -1).to_list(100)
    
    # Ajouter le nombre de participants pour chaque lien
    for session in sessions:
        session["participant_count"] = len(session.get("participant_ids", []))
    
    return sessions

# v98.2: RÃ©cupÃ©rer un lien spÃ©cifique par token (pour OnboardingTunnel)
@api_router.get("/chat/links/{token}")
async def get_chat_link_by_token(token: str):
    """
    RÃ©cupÃ¨re un lien de chat par son link_token.
    UtilisÃ© par le tunnel d'onboarding pour charger les questions personnalisÃ©es.
    """
    link = await db.chat_sessions.find_one(
        {"$or": [{"link_token": token}, {"id": token}], "is_deleted": {"$ne": True}},
        {"_id": 0, "id": 1, "link_token": 1, "title": 1, "custom_prompt": 1, "lead_type": 1,
         "tunnel_questions": 1, "end_actions": 1, "welcome_message": 1, "is_ai_active": 1}
    )
    if not link:
        raise HTTPException(status_code=404, detail="Lien non trouvÃ©")
    return link

# v98.2: GÃ©nÃ©rer une stratÃ©gie IA pour le tunnel
@api_router.post("/chat/generate-strategy")
async def generate_ai_strategy(request: Request):
    """
    Utilise l'IA pour gÃ©nÃ©rer des questions de tunnel, un message d'accueil
    et un prompt systÃ¨me basÃ©s sur l'objectif du coach.
    """
    body = await request.json()
    objective = body.get("objective", "").strip()
    lead_type = body.get("lead_type", "participant")

    if not objective:
        raise HTTPException(status_code=400, detail="Objectif requis")

    try:
        from openai import OpenAI
        openai_key = os.environ.get("OPENAI_API_KEY")
        if not openai_key:
            raise HTTPException(status_code=500, detail="OpenAI non configurÃ©")

        client = OpenAI(api_key=openai_key)

        system_msg = """Tu es un expert en tunnels de vente et qualification de leads.
L'utilisateur te donne un objectif. Tu dois gÃ©nÃ©rer:
1. Un message d'accueil engageant (2-3 phrases max, avec emoji)
2. 3 Ã  5 questions de qualification pertinentes
3. Un prompt systÃ¨me pour l'IA du chat

RÃ©ponds en JSON strict:
{
  "welcome_message": "...",
  "custom_prompt": "...",
  "questions": [
    {"text": "...", "type": "text|buttons|email|phone|city|number|date", "options": ["opt1","opt2"] }
  ]
}
Pour type "buttons", fournis 2-4 options. Pour les autres types, options = [].
Langue: franÃ§ais. Ton: professionnel mais chaleureux."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": f"Objectif: {objective}\nType de lead: {lead_type}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=800,
        )

        import json
        result = json.loads(response.choices[0].message.content)
        logger.info(f"[AI STRATEGY] GÃ©nÃ©rÃ© {len(result.get('questions', []))} questions pour objectif: {objective[:50]}")
        return result

    except Exception as e:
        logger.error(f"[AI STRATEGY] Erreur: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur IA: {str(e)}")

@api_router.delete("/chat/links/{link_id}")
async def delete_chat_link(link_id: str):
    """
    Supprime un lien de chat (suppression logique).
    Le lien ne sera plus accessible et n'apparaÃ®tra plus dans la liste.
    """
    logger.info(f"[DELETE] Suppression lien: {link_id}")
    
    result = await db.chat_sessions.update_one(
        {"$or": [{"id": link_id}, {"link_token": link_id}]},
        {"$set": {"is_deleted": True, "deleted_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    logger.info(f"[DELETE] RÃ©sultat: matched={result.matched_count}, modified={result.modified_count}")
    
    if result.modified_count == 0:
        logger.warning(f"[DELETE] Lien non trouvÃ©: {link_id}")
        raise HTTPException(status_code=404, detail="Lien non trouvÃ©")
    
    logger.info(f"[DELETE] Lien {link_id} supprimÃ© avec succÃ¨s â")
    return {"success": True, "message": "Lien supprimÃ©"}

# v16.1: Endpoint pour modifier un lien de chat (titre + prompt)
@api_router.put("/chat/links/{link_id}")
async def update_chat_link(link_id: str, request: Request):
    """
    Met Ã  jour le titre et/ou le custom_prompt d'un lien de chat existant.
    Permet de modifier le prompt mÃªme aprÃ¨s la crÃ©ation du lien.

    Body:
    {
        "title": "Nouveau titre",           // Optionnel
        "custom_prompt": "Nouveau prompt"    // Optionnel (null pour supprimer)
    }
    """
    body = await request.json()
    update_fields = {"updated_at": datetime.now(timezone.utc).isoformat()}

    if "title" in body:
        update_fields["title"] = body["title"].strip() if body["title"] else ""

    if "custom_prompt" in body:
        cp = body["custom_prompt"]
        update_fields["custom_prompt"] = cp.strip() if cp and isinstance(cp, str) and cp.strip() else None

    # v98: Champs Ã©tendus pour les liens intelligents
    for field in ["lead_type", "welcome_message"]:
        if field in body:
            val = body[field]
            update_fields[field] = val.strip() if isinstance(val, str) else val

    for field in ["tunnel_questions", "end_actions"]:
        if field in body:
            val = body[field]
            update_fields[field] = val if isinstance(val, list) else []

    if len(update_fields) <= 1:  # Only updated_at
        raise HTTPException(status_code=400, detail="Aucun champ Ã  mettre Ã  jour")

    result = await db.chat_sessions.update_one(
        {"$or": [{"id": link_id}, {"link_token": link_id}], "is_deleted": {"$ne": True}},
        {"$set": update_fields}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Lien non trouvÃ©")

    # RÃ©cupÃ©rer le lien mis Ã  jour
    updated = await db.chat_sessions.find_one(
        {"$or": [{"id": link_id}, {"link_token": link_id}]},
        {"_id": 0}
    )

    logger.info(f"[CHAT-LINK] Lien {link_id} mis Ã  jour: title={update_fields.get('title', 'â')}, custom_prompt={'oui' if update_fields.get('custom_prompt') else 'non'}")

    return {
        "success": True,
        "session": updated,
        "message": "Lien mis Ã  jour"
    }

# v14.3: Endpoint pour amÃ©liorer un prompt avec l'IA
@api_router.post("/chat/enhance-prompt")
async def enhance_prompt_with_ai(request: Request):
    """
    Transforme un texte brut en prompt structurÃ© pour le chat IA.
    Utilise l'IA pour reformuler et structurer le prompt de maniÃ¨re professionnelle.
    """
    body = await request.json()
    raw_prompt = body.get("raw_prompt", "").strip()
    
    if not raw_prompt:
        raise HTTPException(status_code=400, detail="Le prompt brut est requis")
    
    # RÃ©cupÃ©rer la config IA
    ai_config = await db.ai_config.find_one({"id": "ai_config"}, {"_id": 0})
    if not ai_config or not ai_config.get("enabled"):
        raise HTTPException(status_code=503, detail="L'assistant IA est dÃ©sactivÃ©")
    
    try:
        # Utiliser l'IA pour amÃ©liorer le prompt
        from openai import OpenAI

        openai_key = os.environ.get("OPENAI_API_KEY")
        if not openai_key:
            raise ValueError("OPENAI_API_KEY not configured")

        client = OpenAI(api_key=openai_key)
        model_name = ai_config.get("model", "gpt-4o-mini")

        system_prompt = """Tu es un expert en rÃ©daction de prompts pour assistants IA.
Transforme le texte brut suivant en un prompt clair, structurÃ© et professionnel.
Le prompt doit:
- DÃ©finir clairement le rÃ´le de l'assistant
- PrÃ©ciser le ton et le style de communication
- Inclure des instructions spÃ©cifiques si mentionnÃ©es
- Ãtre concis mais complet

RÃ©ponds UNIQUEMENT avec le prompt amÃ©liorÃ©, sans explication."""

        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Texte brut Ã  transformer:\n{raw_prompt}"}
            ],
            max_tokens=500
        )

        enhanced = response.choices[0].message.content.strip()
        logger.info(f"[ENHANCE-PROMPT] Prompt amÃ©liorÃ©: {raw_prompt[:30]}... -> {enhanced[:50]}...")
        
        return {"enhanced_prompt": enhanced, "original": raw_prompt}
        
    except Exception as e:
        logger.error(f"[ENHANCE-PROMPT] Erreur: {str(e)}")
        # Fallback: retourner le prompt original structurÃ© manuellement
        fallback = f"Tu es un assistant virtuel professionnel. {raw_prompt}. Sois courtois et aide l'utilisateur au mieux."
        return {"enhanced_prompt": fallback, "original": raw_prompt, "fallback": True}

@api_router.post("/ai/enhance-text")
async def enhance_text_with_ai(request: Request):
    """
    v17.0 â Assistant rÃ©daction IA gÃ©nÃ©rique.
    Contextes: offer, pack, legal, seo, faq_answer, general
    """
    body = await request.json()
    text = body.get("text", "").strip()
    context = body.get("context") or body.get("style") or "general"
    lang = body.get("lang", "fr")

    if not text:
        raise HTTPException(status_code=400, detail="Le texte est requis")

    try:
        from openai import OpenAI

        openai_key = os.environ.get("OPENAI_API_KEY")
        if not openai_key:
            raise ValueError("OPENAI_API_KEY not configured")

        client = OpenAI(api_key=openai_key)

        prompts = {
            "offer": f"""Tu es un expert en marketing fitness/wellness.
AmÃ©liore cette description d'offre pour la rendre attractive et professionnelle.
- Garde le sens original, rends-la percutante et vendeuse
- Max 150 caractÃ¨res
- Utilise des mots-clÃ©s fitness/bien-Ãªtre
- Langue: {lang}
RÃ©ponds UNIQUEMENT avec le texte amÃ©liorÃ©.""",
            "pack": f"""Tu es un expert en marketing digital pour coaches sportifs.
AmÃ©liore cette description de pack/abonnement pour maximiser les conversions.
- Mets en avant la valeur et les bÃ©nÃ©fices
- CrÃ©e un sentiment d'urgence subtil
- Max 200 caractÃ¨res
- Langue: {lang}
RÃ©ponds UNIQUEMENT avec le texte amÃ©liorÃ©.""",
            "legal": f"""Tu es un juriste spÃ©cialisÃ© en droit suisse du commerce en ligne.
AmÃ©liore et professionnalise ces conditions gÃ©nÃ©rales.
- Assure la conformitÃ© lÃ©gale suisse (CO, LPD)
- Langage clair mais juridiquement prÃ©cis
- Langue: {lang}
RÃ©ponds UNIQUEMENT avec le texte amÃ©liorÃ©.""",
            "seo": f"""Tu es un expert SEO pour sites de coaching fitness.
Optimise ce texte pour le rÃ©fÃ©rencement naturel.
- IntÃ¨gre des mots-clÃ©s pertinents naturellement
- Respecte les bonnes pratiques SEO (meta title < 60 car, meta desc < 160 car)
- Langue: {lang}
RÃ©ponds UNIQUEMENT avec le texte optimisÃ©.""",
            "faq_answer": f"""Tu es un coach sportif professionnel et bienveillant.
RÃ©dige une rÃ©ponse claire et rassurante Ã  cette question de FAQ.
- Ton professionnel mais chaleureux
- RÃ©ponse concise (2-3 phrases max)
- Langue: {lang}
RÃ©ponds UNIQUEMENT avec la rÃ©ponse.""",
            "general": f"""Tu es un assistant rÃ©daction professionnel.
AmÃ©liore ce texte pour le rendre plus clair et impactant.
- Garde le sens original
- Langue: {lang}
RÃ©ponds UNIQUEMENT avec le texte amÃ©liorÃ©.""",
            "afroboost": f"""Tu es le coach Afroboost, expert en fitness et bien-Ãªtre.
RÃ©Ã©cris ce message dans le style Afroboost : motivant, chaleureux, professionnel et Ã©nergique.
- Utilise un ton positif et encourageant
- Ajoute de l'Ã©nergie et de la motivation
- Garde le sens du message original
- Maximum 2-3 phrases percutantes
- Langue: {lang}
RÃ©ponds UNIQUEMENT avec le texte rÃ©Ã©crit.""",
            "expert": f"""Tu es un architecte de systÃ¨mes IA et expert en prompt engineering.
Le texte ci-dessous est une instruction pour crÃ©er un prompt systÃ¨me pour un assistant IA de groupe.
- GÃ©nÃ¨re un prompt systÃ¨me expert, concis et prÃ©cis
- DÃ©finis la personnalitÃ©, le ton et le domaine d'expertise de l'IA
- Style Afroboost : motivant, chaleureux, professionnel
- Maximum 3 phrases
- Langue: {lang}
RÃ©ponds UNIQUEMENT avec le prompt systÃ¨me gÃ©nÃ©rÃ©."""
        }

        system_prompt = prompts.get(context, prompts["general"])

        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            max_tokens=500
        )

        enhanced = response.choices[0].message.content.strip()
        logger.info(f"[ENHANCE-TEXT] ctx={context} | {text[:30]}... -> {enhanced[:50]}...")

        return {"enhanced_text": enhanced, "original": text, "context": context}

    except Exception as e:
        logger.error(f"[ENHANCE-TEXT] Erreur: {str(e)}")
        return {"enhanced_text": text, "original": text, "context": context, "fallback": True, "error": str(e)}


# --- Intelligent Chat Entry Point ---
@api_router.post("/chat/smart-entry")
async def smart_chat_entry(request: Request):
    """
    Point d'entrÃ©e intelligent pour le chat.
    
    1. VÃ©rifie si l'utilisateur existe dÃ©jÃ  (par nom, email ou WhatsApp)
    2. Si oui, rÃ©cupÃ¨re ses sessions prÃ©cÃ©dentes et son historique
    3. Si non, crÃ©e un nouveau participant et une nouvelle session
    4. Retourne les infos du participant et la session active
    
    Body attendu:
    {
        "name": "John",
        "email": "john@example.com",  // Optionnel
        "whatsapp": "+41761234567",   // Optionnel
        "link_token": "abc123"         // Optionnel - si via lien partagÃ©
    }
    """
    body = await request.json()
    name = body.get("name", "").strip()
    email = body.get("email", "").strip()
    whatsapp = body.get("whatsapp", "").strip()
    link_token = body.get("link_token")
    tunnel_answers = body.get("tunnel_answers")  # v100: rÃ©ponses tunnel

    if not name:
        raise HTTPException(status_code=400, detail="Le nom est requis")
    
    # Rechercher un participant existant
    existing_participant = None
    search_query = {"$or": []}
    
    if email:
        search_query["$or"].append({"email": {"$regex": f"^{email}$", "$options": "i"}})
    if whatsapp:
        clean_whatsapp = whatsapp.replace(" ", "").replace("-", "").replace("+", "")
        if clean_whatsapp:
            search_query["$or"].append({"whatsapp": {"$regex": clean_whatsapp}})
    
    # Recherche aussi par nom exact
    search_query["$or"].append({"name": {"$regex": f"^{name}$", "$options": "i"}})
    
    if search_query["$or"]:
        existing_participant = await db.chat_participants.find_one(search_query, {"_id": 0})
    
    # DÃ©terminer la source
    source = f"link_{link_token}" if link_token else "chat_afroboost"
    
    if existing_participant:
        # Participant reconnu - mettre Ã  jour last_seen
        participant_id = existing_participant["id"]
        update_fields = {"last_seen_at": datetime.now(timezone.utc).isoformat()}
        
        # v104: Mettre Ã  jour les infos si nouvelles ou manquantes
        if email and not existing_participant.get("email"):
            update_fields["email"] = email
        if whatsapp and not existing_participant.get("whatsapp"):
            update_fields["whatsapp"] = whatsapp
        if name and name != existing_participant.get("name"):
            update_fields["name"] = name
        if not existing_participant.get("coach_id"):
            update_fields["coach_id"] = DEFAULT_COACH_ID
        
        await db.chat_participants.update_one(
            {"id": participant_id},
            {"$set": update_fields}
        )
        
        participant = await db.chat_participants.find_one({"id": participant_id}, {"_id": 0})
        is_returning = True
    else:
        # Nouveau participant â v104: ajouter coach_id pour unification contacts
        participant_obj = ChatParticipant(
            name=name,
            email=email,
            whatsapp=whatsapp,
            source=source,
            link_token=link_token
        )
        new_doc = participant_obj.model_dump()
        new_doc["coach_id"] = DEFAULT_COACH_ID
        await db.chat_participants.insert_one(new_doc)
        participant = {k: v for k, v in new_doc.items() if k != "_id"}
        participant_id = participant["id"]
        is_returning = False
    
    # Trouver ou crÃ©er la session
    session = None
    
    if link_token:
        # Si via lien partagÃ©, utiliser cette session
        session = await db.chat_sessions.find_one(
            {"link_token": link_token, "is_deleted": {"$ne": True}},
            {"_id": 0}
        )
    
    if not session:
        # Chercher une session active existante pour ce participant
        sessions = await db.chat_sessions.find(
            {
                "participant_ids": participant_id,
                "is_deleted": {"$ne": True}
            },
            {"_id": 0}
        ).sort("created_at", -1).to_list(1)

        if sessions:
            session = sessions[0]

    # V107.6: Chercher aussi par participantEmail (session crÃ©Ã©e par le coach)
    # Cas 1: Pas de session â utiliser celle du coach
    # Cas 2: Session existante MAIS une autre session coach existe aussi â FUSIONNER les messages
    if email:
        email_session = await db.chat_sessions.find_one(
            {
                "participantEmail": {"$regex": f"^{email}$", "$options": "i"},
                "is_deleted": {"$ne": True}
            },
            {"_id": 0}
        )
        if email_session:
            if not session:
                # Cas 1: Pas de session trouvÃ©e par participant_ids â utiliser celle du coach
                if participant_id not in email_session.get("participant_ids", []):
                    await db.chat_sessions.update_one(
                        {"id": email_session["id"]},
                        {
                            "$push": {"participant_ids": participant_id},
                            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
                        }
                    )
                    email_session = await db.chat_sessions.find_one({"id": email_session["id"]}, {"_id": 0})
                session = email_session
                logger.info(f"[SMART-ENTRY] V107.6 Cas1: Session coach trouvÃ©e par email {email} -> {session['id'][:8]}")
            elif session["id"] != email_session["id"]:
                # Cas 2: DEUX sessions diffÃ©rentes existent â FUSIONNER
                # Migrer tous les messages de la session abonnÃ© vers la session coach
                subscriber_session_id = session["id"]
                coach_session_id = email_session["id"]
                migrated = await db.chat_messages.update_many(
                    {"session_id": subscriber_session_id},
                    {"$set": {"session_id": coach_session_id}}
                )
                # Ajouter le participant_id Ã  la session coach
                if participant_id not in email_session.get("participant_ids", []):
                    await db.chat_sessions.update_one(
                        {"id": coach_session_id},
                        {
                            "$push": {"participant_ids": participant_id},
                            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
                        }
                    )
                # Soft-delete l'ancienne session de l'abonnÃ©
                await db.chat_sessions.update_one(
                    {"id": subscriber_session_id},
                    {"$set": {"is_deleted": True, "merged_into": coach_session_id}}
                )
                session = await db.chat_sessions.find_one({"id": coach_session_id}, {"_id": 0})
                logger.info(f"[SMART-ENTRY] V107.6 Cas2: FUSION {subscriber_session_id[:8]} â {coach_session_id[:8]} ({migrated.modified_count} msgs migrÃ©s)")

    if not session:
        # CrÃ©er une nouvelle session
        session_obj = ChatSession(
            mode="ai",
            is_ai_active=True,
            participant_ids=[participant_id]
        )
        await db.chat_sessions.insert_one(session_obj.model_dump())
        session = session_obj.model_dump()
    else:
        # Ajouter le participant Ã  la session s'il n'y est pas
        if participant_id not in session.get("participant_ids", []):
            await db.chat_sessions.update_one(
                {"id": session["id"]},
                {
                    "$push": {"participant_ids": participant_id},
                    "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
                }
            )
            session = await db.chat_sessions.find_one({"id": session["id"]}, {"_id": 0})
    
    # v15.0: Mettre Ã  jour le participantName de la session pour l'affichage CRM
    if session and name:
        await db.chat_sessions.update_one(
            {"id": session["id"]},
            {"$set": {
                "participantName": name,
                "participantEmail": email if email else session.get("participantEmail", ""),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        session = await db.chat_sessions.find_one({"id": session["id"]}, {"_id": 0})
    
    # v100: Sauvegarder les rÃ©ponses tunnel dans la collection leads
    if tunnel_answers and isinstance(tunnel_answers, (list, dict)):
        lead_doc = {
            "id": str(uuid.uuid4()),
            "participant_id": participant_id,
            "session_id": session["id"],
            "link_token": link_token,
            "name": name,
            "email": email,
            "whatsapp": whatsapp,
            "answers": tunnel_answers,
            "source": source,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.leads.insert_one(lead_doc)
        logger.info(f"[V100] ð Lead sauvegardÃ©: {name} ({email}) â {len(tunnel_answers) if isinstance(tunnel_answers, list) else 1} rÃ©ponses")
        # Aussi stocker dans la session pour accÃ¨s rapide cÃ´tÃ© coach
        await db.chat_sessions.update_one(
            {"id": session["id"]},
            {"$set": {"tunnel_answers": tunnel_answers, "lead_id": lead_doc["id"]}}
        )

    # RÃ©cupÃ©rer l'historique des messages si participant existant
    chat_history = []
    if is_returning:
        chat_history = await db.chat_messages.find(
            {"session_id": session["id"], "is_deleted": {"$ne": True}},
            {"_id": 0}
        ).sort("created_at", 1).to_list(50)

    return {
        "participant": participant,
        "session": session,
        "is_returning": is_returning,
        "chat_history": chat_history,
        "message": f"Ravi de te revoir, {name} !" if is_returning else f"Bienvenue, {name} !",
        "lead_saved": bool(tunnel_answers)
    }

# --- AI Chat with Session Context ---
@api_router.post("/chat/ai-response")
async def get_ai_response_with_session(request: Request):
    """
    Envoie un message Ã  l'IA avec le contexte COMPLET de la session.
    Inclut les produits, offres, cours et articles depuis MongoDB.
    
    Body attendu:
    {
        "session_id": "xxx",
        "participant_id": "xxx",
        "message": "Bonjour!"
    }
    """
    import time
    start_time = time.time()
    
    body = await request.json()
    session_id = body.get("session_id")
    participant_id = body.get("participant_id")
    message_text = body.get("message", "").strip()
    
    if not session_id or not participant_id or not message_text:
        raise HTTPException(status_code=400, detail="session_id, participant_id et message sont requis")
    
    # RÃ©cupÃ©rer la session
    session = await db.chat_sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvÃ©e")
    
    # RÃ©cupÃ©rer le participant â chercher dans chat_participants PUIS fallback dans users
    participant = await db.chat_participants.find_one({"id": participant_id}, {"_id": 0})
    if not participant:
        # v108: Fallback vers la collection users (abonnÃ©s qui rejoignent via groupe/lien)
        participant = await db.users.find_one({"id": participant_id}, {"_id": 0})
    if not participant:
        raise HTTPException(status_code=404, detail="Participant non trouvÃ©")

    participant_name = participant.get("name", "Utilisateur")
    
    # V108.3: Log dÃ©taillÃ© pour debug groupe
    session_mode = session.get("mode", "ai")
    is_group = session_mode == "group" or session.get("group_id")
    if is_group:
        logger.info(f"[V108.3-GROUP] Message de {participant_name} ({participant_id}) â session {session_id} (mode={session_mode}, group_id={session.get('group_id', 'N/A')})")

    # Sauvegarder le message de l'utilisateur
    user_message = EnhancedChatMessage(
        session_id=session_id,
        sender_id=participant_id,
        sender_name=participant_name,
        sender_type="user",
        content=message_text,
        mode=session.get("mode", "ai")
    )
    msg_data = user_message.model_dump()
    await db.chat_messages.insert_one(msg_data)

    if is_group:
        logger.info(f"[V108.3-GROUP] Message SAUVÃ: id={user_message.id}, session_id={msg_data.get('session_id')}, content='{message_text[:50]}'")

    # === SOCKET.IO: Ãmettre le message utilisateur en temps rÃ©el ===
    await emit_new_message(session_id, {
        "id": user_message.id,
        "type": "user",
        "text": message_text,
        "sender": participant_name,
        "senderId": participant_id,
        "sender_type": "user",
        "created_at": user_message.created_at
    })
    
    # VÃ©rifier si l'IA est active pour cette session
    # V107.12: Groupes avec IA â si is_ai_active=True ET mode=group, l'IA rÃ©pond aussi
    # session_mode dÃ©jÃ  dÃ©fini plus haut (V108.3)
    ai_enabled_for_session = session.get("is_ai_active", True)
    ai_allowed = ai_enabled_for_session and (session_mode == "ai" or session_mode == "group")

    if not ai_allowed:
        # Mode humain ou groupe sans IA - Notifier le coach par e-mail (non-bloquant)
        asyncio.create_task(
            notify_coach_new_message(
                participant_name=participant_name,
                message_preview=message_text,
                session_id=session_id
            )
        )
        return {
            "response": None,
            "ai_active": False,
            "mode": session_mode,
            "message_saved": True,
            "user_message_id": user_message.id,
            "coach_notified": True
        }
    
    # RÃ©cupÃ©rer la config IA
    ai_config = await db.ai_config.find_one({"id": "ai_config"}, {"_id": 0})
    if not ai_config or not ai_config.get("enabled"):
        return {
            "response": "L'assistant IA est actuellement dÃ©sactivÃ©.",
            "ai_active": False,
            "message_saved": True,
            "user_message_id": user_message.id
        }
    
    # =====================================================================
    # DÃTECTION MODE STRICT (AVANT construction du contexte)
    # Mapper link_token â custom_prompt pour initialiser le bon "caractÃ¨re IA"
    use_strict_mode = False
    CUSTOM_PROMPT = ""

    # 1. VÃ©rifier si la session a un custom_prompt directement
    session_custom_prompt = session.get("custom_prompt") if session else None
    if session_custom_prompt and isinstance(session_custom_prompt, str) and session_custom_prompt.strip():
        CUSTOM_PROMPT = session_custom_prompt.strip()
        use_strict_mode = True
        logger.info("[CHAT-AI-RESPONSE] Mode STRICT via session.custom_prompt")

    # 2. Fallback : si pas de custom_prompt, vÃ©rifier via link_token (URL du client)
    if not use_strict_mode:
        link_token = body.get("link_token", "").strip() if body.get("link_token") else ""
        # Chercher aussi le link_token stockÃ© dans la session
        if not link_token:
            link_token = session.get("link_token", "") if session else ""
        if link_token:
            try:
                # RÃ©cupÃ©rer la session originale du lien pour son custom_prompt
                link_session = await db.chat_sessions.find_one(
                    {"link_token": link_token, "is_deleted": {"$ne": True}},
                    {"_id": 0, "custom_prompt": 1}
                )
                if link_session and link_session.get("custom_prompt"):
                    prompt_from_link = link_session["custom_prompt"].strip()
                    if prompt_from_link:
                        CUSTOM_PROMPT = prompt_from_link
                        use_strict_mode = True
                        logger.info(f"[CHAT-AI-RESPONSE] Mode STRICT via link_token {link_token[:8]}")
            except Exception as e:
                logger.warning(f"[CHAT-AI-RESPONSE] Erreur rÃ©cup custom_prompt via link_token: {e}")
    
    # CONSTRUCTION DU CONTEXTE
    logger.info("[CHAT-AI-RESPONSE] Construction contexte...")
    
    if use_strict_mode:
        # v8.5: ISOLATION TOTALE - UNIQUEMENT le custom_prompt du lien
        context = f"\n\n=== INSTRUCTIONS SPECIFIQUES DU LIEN ===\n{CUSTOM_PROMPT}\n"
        context += f"\nInterlocuteur: {participant_name}\n"
        logger.info("[CHAT-AI-RESPONSE] v8.5: Isolation totale")
    else:
        # MODE STANDARD: Contexte complet avec toutes les donnÃ©es de vente
        context = "\n\n========== CONNAISSANCES DU SITE AFROBOOST ==========\n"
        context += "Utilise EXCLUSIVEMENT ces informations pour rÃ©pondre sur les produits, cours, offres et articles.\n"
        context += "IMPORTANT: VÃ©rifie TOUJOURS l'INVENTAIRE BOUTIQUE avant de dire qu'un produit n'existe pas !\n"
        
        # PrÃ©nom du client
        context += f"\nð¤ CLIENT: {participant_name} - Utilise son prÃ©nom pour Ãªtre chaleureux.\n"
        
        # Concept/Description du site
        try:
            concept = await db.concept.find_one({"id": "concept"}, {"_id": 0})
            if concept and concept.get('description'):
                context += f"\nð Ã PROPOS D'AFROBOOST:\n{concept.get('description', '')[:500]}\n"
        except Exception as e:
            logger.warning(f"[CHAT-AI-RESPONSE] Erreur rÃ©cupÃ©ration concept: {e}")
    
    # === SECTIONS VENTE (UNIQUEMENT en mode STANDARD, pas en mode STRICT) ===
    if not use_strict_mode:
        # === SECTION 1: INVENTAIRE BOUTIQUE (PRODUITS PHYSIQUES) ===
        try:
            # RÃ©cupÃ©rer TOUS les Ã©lÃ©ments de la collection offers
            all_offers = await db.offers.find({"visible": {"$ne": False}}, {"_id": 0}).to_list(50)
            
            # SÃ©parer les PRODUITS des SERVICES
            products = [o for o in all_offers if o.get('isProduct') == True]
            services = [o for o in all_offers if not o.get('isProduct')]
            
            # === PRODUITS BOUTIQUE (cafÃ©, vÃªtements, accessoires...) ===
            if products:
                context += "\n\nð INVENTAIRE BOUTIQUE (Produits en vente):\n"
                for p in products[:15]:
                    name = p.get('name', 'Produit')
                    price = p.get('price', 0)
                    desc = p.get('description', '')[:150] if p.get('description') else ''
                    category = p.get('category', '')
                    stock = p.get('stock', -1)
                    
                    context += f"  â {name.upper()} : {price} CHF"
                    if category:
                        context += f" (CatÃ©gorie: {category})"
                    if stock > 0:
                        context += f" - En stock: {stock}"
                    context += "\n"
                    if desc:
                        context += f"    Description: {desc}\n"
                context += "  â Si un client demande un de ces produits, CONFIRME qu'il est disponible !\n"
            else:
                context += "\n\nð INVENTAIRE BOUTIQUE: Aucun produit en vente actuellement.\n"
            
            # === SERVICES ET OFFRES (abonnements, cours Ã  l'unitÃ©...) ===
            if services:
                context += "\n\nð° OFFRES ET TARIFS (Services):\n"
                for s in services[:10]:
                    name = s.get('name', 'Offre')
                    price = s.get('price', 0)
                    desc = s.get('description', '')[:100] if s.get('description') else ''
                    
                    context += f"  â¢ {name} : {price} CHF"
                    if desc:
                        context += f" - {desc}"
                    context += "\n"
            else:
                context += "\n\nð° OFFRES: Aucune offre spÃ©ciale actuellement.\n"
                
        except Exception as e:
            logger.error(f"[CHAT-AI-RESPONSE] â Erreur rÃ©cupÃ©ration offres/produits: {e}")
            context += "\n\nð BOUTIQUE: Informations temporairement indisponibles.\n"
        
        # === SECTION 2: COURS DISPONIBLES ===
        try:
            courses = await db.courses.find({"visible": {"$ne": False}}, {"_id": 0}).to_list(20)
            if courses:
                context += "\n\nð¯ COURS DISPONIBLES:\n"
                for c in courses[:10]:  # Max 10 cours
                    name = c.get('name', 'Cours')
                    date = c.get('date', '')
                    time_slot = c.get('time', '')
                    location = c.get('locationName', c.get('location', ''))
                    price = c.get('price', '')
                    description = c.get('description', '')[:80] if c.get('description') else ''
                    
                    context += f"  â¢ {name}"
                    if date:
                        context += f" - {date}"
                    if time_slot:
                        context += f" Ã  {time_slot}"
                    if location:
                        context += f" ({location})"
                    if price:
                        context += f" - {price} CHF"
                    context += "\n"
                    if description:
                        context += f"    â {description}\n"
            else:
                context += "\n\nð¯ COURS: Aucun cours programmÃ© actuellement. Invite le client Ã  suivre nos rÃ©seaux pour les prochaines dates.\n"
        except Exception as e:
            logger.warning(f"[CHAT-AI-RESPONSE] Erreur rÃ©cupÃ©ration cours: {e}")
            context += "\n\nð¯ COURS: Informations temporairement indisponibles.\n"
        
        # === SECTION 3: PROMOS SPÃCIALES (avec masquage des codes) ===
        # L'IA peut connaÃ®tre les remises pour calculer les prix, mais JAMAIS les codes
        # PRODUCTION-READY: Try/except individuel pour chaque promo
        try:
            active_promos = await db.discount_codes.find({"active": True}, {"_id": 0}).to_list(20)
            if active_promos:
                context += "\n\nð PROMOTIONS EN COURS:\n"
                promos_injected = 0
                for promo in active_promos[:5]:
                    try:
                        # MASQUAGE TECHNIQUE: Le champ 'code' n'est JAMAIS lu ni transmis
                        # Seuls 'type' et 'value' sont utilisÃ©s pour le calcul
                        promo_type = promo.get('type', '%')
                        promo_value = promo.get('value', 0)
                        
                        # Validation: S'assurer que value est un nombre valide
                        if promo_value is None:
                            promo_value = 0
                        promo_value = float(promo_value)
                        
                        # Construire la description SANS le code rÃ©el
                        # Le placeholder [CODE_APPLIQUÃ_AU_PANIER] est la SEULE chose visible
                        if promo_type == '100%':
                            context += "  â¢ Remise 100% disponible (code: [CODE_APPLIQUÃ_AU_PANIER])\n"
                        elif promo_type == '%':
                            context += "  â¢ Remise de " + str(promo_value) + "% disponible (code: [CODE_APPLIQUÃ_AU_PANIER])\n"
                        elif promo_type == 'CHF':
                            context += "  â¢ Remise de " + str(promo_value) + " CHF disponible (code: [CODE_APPLIQUÃ_AU_PANIER])\n"
                        else:
                            # Type inconnu: afficher quand mÃªme sans rÃ©vÃ©ler le code
                            context += "  â¢ Promotion disponible (code: [CODE_APPLIQUÃ_AU_PANIER])\n"
                        promos_injected += 1
                    except Exception as promo_error:
                        # Log l'erreur mais continue avec les autres promos
                        logger.warning(f"[CHAT-IA] â ï¸ Promo ignorÃ©e (erreur parsing): {promo_error}")
                        continue
                
                if promos_injected > 0:
                    context += "  â Tu peux calculer les prix rÃ©duits avec ces remises.\n"
                    context += "  â Ne dis JAMAIS le code. Dis simplement: 'Le code est appliquÃ© automatiquement au panier.'\n"
                    logger.info(f"[CHAT-IA] â {promos_injected} promos injectÃ©es (codes masquÃ©s)")
        except Exception as e:
            logger.warning(f"[CHAT-IA] Erreur rÃ©cupÃ©ration promos (non bloquant): {e}")
        
        # === SECTION 5: LIEN DE PAIEMENT TWINT ===
        twint_payment_url = ai_config.get("twintPaymentUrl", "")
        if twint_payment_url and twint_payment_url.strip():
            context += f"\n\nð³ LIEN DE PAIEMENT TWINT:\n"
            context += f"  URL: {twint_payment_url}\n"
            context += "  â Quand un client confirme vouloir acheter, propose-lui ce lien de paiement sÃ©curisÃ© Twint.\n"
            logger.info(f"[CHAT-AI-RESPONSE] â Lien Twint injectÃ©: {twint_payment_url[:50]}...")
        else:
            logger.info(f"[CHAT-AI-RESPONSE] â ï¸ Pas de lien Twint configurÃ©")
        
        # === HISTORIQUE DE CONVERSATION ===
        try:
            recent_messages = await db.chat_messages.find(
                {"session_id": session_id, "is_deleted": {"$ne": True}},
                {"_id": 0}
            ).sort("created_at", -1).limit(10).to_list(10)
            
            if recent_messages and len(recent_messages) > 1:
                history = "\n".join([
                    f"{'Client' if m.get('sender_type') == 'user' else 'Assistant'}: {m.get('content', '')}"
                    for m in reversed(recent_messages[1:])  # Exclure le message actuel
                ])
                context += f"\n\nð HISTORIQUE RÃCENT:\n{history}"
        except Exception as e:
            logger.warning(f"[CHAT-AI-RESPONSE] Erreur rÃ©cupÃ©ration historique: {e}")
    # === FIN DES SECTIONS VENTE (uniquement en mode STANDARD) ===
    
    # ARCHITECTURE DE PROMPT
    user_message_lower = message_text.lower() if message_text else ""
    is_trial_intent = any(word in user_message_lower for word in ['essai', 'gratuit', 'tester', 'essayer', 'test', 'dÃ©couvrir'])
    
    if use_strict_mode:
        # MODE STRICT : custom_prompt REMPLACE BASE_PROMPT, aucune donnÃ©e de vente
        STRICT_SYSTEM_PROMPT = """
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
â        ððð MODE STRICT - PARTENARIAT / COLLABORATION ððð        â
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

âââ INTERDICTIONS ABSOLUES âââ

Tu as INTERDICTION ABSOLUE de:
- Citer un PRIX, un TARIF, un COÃT ou un MONTANT (CHF, EUR, $)
- Mentionner un LIEN DE PAIEMENT (Twint, Stripe, etc.)
- Parler de COURS, SESSIONS, ABONNEMENTS ou RÃSERVATIONS
- Orienter vers l'ACHAT ou l'INSCRIPTION
- Donner des informations sur la BOUTIQUE ou les PRODUITS Ã  vendre

Si on te demande un prix, un tarif ou "combien Ã§a coÃ»te", TU DOIS rÃ©pondre:
"Je vous invite Ã  en discuter directement lors de notre Ã©change, je m'occupe uniquement de la partie collaboration."

Si on insiste, rÃ©pÃ¨te cette phrase. Ne donne JAMAIS de prix.

ð¯ TON RÃLE UNIQUE:
Tu t'occupes UNIQUEMENT de la COLLABORATION et du PARTENARIAT.
Tu peux parler du CONCEPT Afroboost (cardio + danse afrobeat + casques audio immersifs).
Tu ne connais AUCUN prix, AUCUN tarif, AUCUN lien de paiement.

"""
        # Ajouter le custom_prompt comme instructions exclusives
        STRICT_SYSTEM_PROMPT += "\nâââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ\n"
        STRICT_SYSTEM_PROMPT += "ð INSTRUCTIONS EXCLUSIVES DU LIEN:\n"
        STRICT_SYSTEM_PROMPT += "âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ\n\n"
        STRICT_SYSTEM_PROMPT += CUSTOM_PROMPT
        STRICT_SYSTEM_PROMPT += "\n\nâââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ\n"
        
        # Injecter le prompt STRICT (remplace tout)
        context += STRICT_SYSTEM_PROMPT
        logger.info("[CHAT-AI-RESPONSE] ð Mode STRICT activÃ© - Aucune donnÃ©e de vente/prix/Twint injectÃ©e")
        
    else:
        # =====================================================================
        # MODE STANDARD : FLUX HABITUEL AVEC TOUTES LES DONNÃES DE VENTE
        # =====================================================================
        
        # --- 1. BASE_PROMPT : Limite l'IA aux produits/cours ---
        BASE_PROMPT = """
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
â                BASE_PROMPT - IDENTITÃ COACH BASSI                â
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

ð¯ IDENTITÃ:
Tu es le COACH BASSI, coach Ã©nergique et passionnÃ© d'Afroboost.
Tu reprÃ©sentes la marque Afroboost et tu guides les clients vers leurs objectifs fitness.
Tu ne parles QUE du catalogue Afroboost (produits, cours, offres listÃ©s ci-dessus).

ðª SIGNATURE:
- PrÃ©sente-toi comme "Coach Bassi" si on te demande ton nom
- Utilise un ton motivant, bienveillant et Ã©nergique
- Signe parfois tes messages avec "- Coach Bassi ðª" pour les messages importants

â CONTENU AUTORISÃ (EXCLUSIVEMENT):
- Les PRODUITS de l'INVENTAIRE BOUTIQUE listÃ©s ci-dessus
- Les COURS disponibles listÃ©s ci-dessus
- Les OFFRES et TARIFS listÃ©s ci-dessus
- Le concept Afroboost (cardio + danse afrobeat)

ð¯ TON STYLE:
- Coach motivant et Ã©nergique (TU ES Coach Bassi)
- Utilise le prÃ©nom du client
- Oriente vers l'INSCRIPTION IMMÃDIATE
- Emojis: ð¥ðªð
- RÃ©ponses courtes et percutantes
"""

        # --- 2. SECURITY_PROMPT : RÃ¨gle non nÃ©gociable ---
        SECURITY_PROMPT = """
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
â              SECURITY_PROMPT - RÃGLE NON NÃGOCIABLE              â
ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

â RÃGLE NON NÃGOCIABLE:
Si la question ne concerne pas un produit ou un cours Afroboost, rÃ©ponds:
"DÃ©solÃ©, je suis uniquement programmÃ© pour vous assister sur nos offres et formations. ð"

ð« N'invente JAMAIS de codes promo. Si une remise existe, dis: "Le code sera appliquÃ© automatiquement au panier."

ð« INTERDICTIONS ABSOLUES:
- Ne rÃ©ponds JAMAIS aux questions hors-sujet (politique, mÃ©tÃ©o, cuisine, prÃ©sident, etc.)
- Ne rÃ©vÃ¨le JAMAIS un code promo textuel
- N'invente JAMAIS d'offres ou de prix
"""

        # Ajout de rÃ¨gles contextuelles
        if is_trial_intent:
            SECURITY_PROMPT += """

ð FLOW ESSAI GRATUIT:
1. "Super ! ð¥ Les 10 premiers peuvent tester gratuitement !"
2. "Tu prÃ©fÃ¨res Mercredi ou Dimanche ?"
3. Attends sa rÃ©ponse avant de demander ses coordonnÃ©es.
"""
        
        # Twint UNIQUEMENT en mode STANDARD
        twint_payment_url = ai_config.get("twintPaymentUrl", "")
        if twint_payment_url and twint_payment_url.strip():
            SECURITY_PROMPT += f"""

ð³ PAIEMENT: Propose ce lien Twint: {twint_payment_url}
"""
        else:
            SECURITY_PROMPT += """

ð³ PAIEMENT: Oriente vers le coach WhatsApp ou email pour finaliser.
"""

        # --- 3. CAMPAIGN_PROMPT : RÃ©cupÃ©rÃ© de la config globale ---
        CAMPAIGN_PROMPT = ai_config.get("campaignPrompt", "").strip()
        
        # GARDE-FOU: Limite Ã  2000 caractÃ¨res
        MAX_CAMPAIGN_LENGTH = 2000
        if len(CAMPAIGN_PROMPT) > MAX_CAMPAIGN_LENGTH:
            logger.warning("[CHAT-AI-RESPONSE] â ï¸ CAMPAIGN_PROMPT tronquÃ©")
            CAMPAIGN_PROMPT = CAMPAIGN_PROMPT[:MAX_CAMPAIGN_LENGTH] + "... [TRONQUÃ]"
        
        # Injection MODE STANDARD: BASE + SECURITY + CAMPAIGN
        context += BASE_PROMPT
        context += SECURITY_PROMPT
        if CAMPAIGN_PROMPT:
            context += "\n\n--- INSTRUCTIONS PRIORITAIRES DE LA CAMPAGNE ACTUELLE ---\n"
            context += CAMPAIGN_PROMPT
            context += "\n--- FIN DES INSTRUCTIONS ---\n"
            logger.info("[CHAT-AI-RESPONSE] â Mode STANDARD - Campaign Prompt injectÃ© (len: " + str(len(CAMPAIGN_PROMPT)) + ")")
        else:
            logger.info("[CHAT-AI-RESPONSE] Mode STANDARD - Pas de Campaign Prompt")
    
    # v8.4: Assemblage final - PRIORITE: Prompt Lien > Prompt Campagne > Prompt Systeme
    if use_strict_mode and CUSTOM_PROMPT:
        full_system_prompt = context  # Prompt du lien REMPLACE tout
        logger.info("[CHAT-AI-RESPONSE] v8.4: Prompt Lien actif")
    else:
        full_system_prompt = ai_config.get("systemPrompt", "Tu es l'assistant IA d'Afroboost.") + context
    
    logger.info("[CHAT-AI-RESPONSE] Contexte construit")
    
    try:
        from openai import OpenAI

        openai_key = os.environ.get("OPENAI_API_KEY")
        if not openai_key:
            return {"response": "Configuration IA incomplÃ¨te.", "ai_active": False}

        client = OpenAI(api_key=openai_key)
        model_name = ai_config.get("model", "gpt-4o-mini")

        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=model_name,
            messages=[
                {"role": "system", "content": full_system_prompt},
                {"role": "user", "content": message_text}
            ],
            max_tokens=1000
        )
        ai_response_text = response.choices[0].message.content
        response_time = round(time.time() - start_time, 2)
        
        logger.info(f"[CHAT-AI-RESPONSE] â RÃ©ponse IA gÃ©nÃ©rÃ©e en {response_time}s")
        
        # Sauvegarder la rÃ©ponse de l'IA
        ai_message = EnhancedChatMessage(
            session_id=session_id,
            sender_id="ai",
            sender_name="Assistant Afroboost",
            sender_type="ai",
            content=ai_response_text,
            mode="ai"
        )
        await db.chat_messages.insert_one(ai_message.model_dump())
        
        # === SOCKET.IO: Ãmettre la rÃ©ponse IA en temps rÃ©el ===
        await emit_new_message(session_id, {
            "id": ai_message.id,
            "type": "ai",
            "text": ai_response_text,
            "sender": "Coach Bassi",
            "senderId": "ai",
            "sender_type": "ai",
            "created_at": ai_message.created_at
        })
        
        # Log
        await db.ai_logs.insert_one({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "from": participant_name,
            "message": message_text,
            "response": ai_response_text,
            "responseTime": response_time
        })
        
        return {
            "response": ai_response_text,
            "ai_active": True,
            "mode": "ai",
            "response_time": response_time,
            "user_message_id": user_message.id,
            "ai_message_id": ai_message.id
        }
        
    except Exception as e:
        logger.error(f"AI Chat error: {str(e)}")
        return {
            "response": "DÃ©solÃ©, une erreur s'est produite. Veuillez rÃ©essayer.",
            "ai_active": True,
            "error": str(e)
        }

# --- Coach Response to Chat ---
@api_router.post("/chat/coach-response")
async def send_coach_response(request: Request):
    """
    Permet au coach d'envoyer un message dans une session.
    UtilisÃ© en mode "human" ou "community".
    """
    body = await request.json()
    session_id = body.get("session_id")
    message_text = body.get("message", "").strip()
    coach_name = body.get("coach_name", "Coach")
    
    if not session_id or not message_text:
        raise HTTPException(status_code=400, detail="session_id et message sont requis")
    
    session = await db.chat_sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvÃ©e")
    
    # CrÃ©er le message du coach
    coach_message = EnhancedChatMessage(
        session_id=session_id,
        sender_id="coach",
        sender_name=coach_name,
        sender_type="coach",
        content=message_text,
        mode=session.get("mode", "human")
    )
    await db.chat_messages.insert_one(coach_message.model_dump())
    
    # === SOCKET.IO: Ãmettre le message coach en temps rÃ©el ===
    await emit_new_message(session_id, {
        "id": coach_message.id,
        "type": "coach",
        "text": message_text,
        "sender": "Coach Bassi",
        "senderId": "coach",
        "sender_type": "coach",
        "created_at": coach_message.created_at
    })
    # === PUSH NOTIFICATION: Alerter l'abonnÃ© si app fermÃ©e (skip si socket actif) ===
    # v7.2: Ajout fallback email si push echoue
    participant_id = session.get("participant_id") or (session.get("participant_ids") or [None])[0]
    if participant_id:
        push_sent = await send_push_notification(participant_id, "Afroboost", f"Nouveau message de {coach_name}", None, session_id)
        # Si push echoue, envoyer un email de backup
        if not push_sent:
            asyncio.create_task(send_backup_email(participant_id, message_text))
    return {"success": True, "message_id": coach_message.id, "mode": session.get("mode")}

# v8.6 / V146: Envoi message de groupe â utilise le session_id du groupe si fourni
@api_router.post("/chat/group-message")
async def send_group_message(request: Request):
    """V146: Envoie un message dans un groupe spÃ©cifique (ou broadcast legacy)."""
    body = await request.json()
    message_text = body.get("message", "").strip()
    coach_name = body.get("coach_name", "Coach Bassi")
    media_url = body.get("media_url")
    group_session_id = body.get("session_id")  # V146: session_id du groupe si disponible

    if not message_text:
        raise HTTPException(status_code=400, detail="message requis")

    # Recuperer tous les participants actifs
    participants = await db.chat_participants.find({}, {"_id": 0, "id": 1, "email": 1, "name": 1}).to_list(500)
    if not participants:
        return {"success": False, "error": "Aucun abonne"}

    # V146: Utiliser le session_id du groupe si fourni, sinon fallback "group" (legacy)
    effective_session_id = group_session_id or "group"

    group_msg = EnhancedChatMessage(
        session_id=effective_session_id, sender_id="coach", sender_name=coach_name,
        sender_type="coach", content=message_text, mode="community", is_group=True
    )
    await db.chat_messages.insert_one(group_msg.model_dump())
    
    # Emettre via Socket.IO a tous
    # Socket.IO dÃ©sactivÃ© en mode Vercel Serverless
    logger.debug(f"[SOCKET.IO] Group message (disabled in Vercel Serverless) emitted")
    
    # Notifications email en arriere-plan (async)
    async def notify_all():
        for p in participants:
            if p.get("email"):
                await send_backup_email(p["id"], f"[Groupe] {message_text[:100]}")
    asyncio.create_task(notify_all())
    
    logger.info(f"[GROUP] Message envoye a {len(participants)} abonnes")
    return {"success": True, "message_id": group_msg.id, "recipients": len(participants)}

# ====== v101: CRUD Groupes de Chat ======
@api_router.post("/chat/groups")
async def create_chat_group(request: Request):
    """v101: CrÃ©er un groupe de chat avec membres sÃ©lectionnÃ©s et prompt IA dÃ©diÃ©"""
    coach_email = require_auth(request)
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Le nom du groupe est requis")
    member_ids = body.get("members", [])
    system_prompt = body.get("system_prompt", "")
    is_ai_active = body.get("is_ai_active", True)

    group_id = str(uuid.uuid4())
    link_token = str(uuid.uuid4())[:8]
    now_iso = datetime.now(timezone.utc).isoformat()

    group_doc = {
        "id": group_id,
        "name": name,
        "coach_id": coach_email,
        "member_ids": member_ids,
        "system_prompt": system_prompt,
        "is_ai_active": is_ai_active,
        "link_token": link_token,
        "mode": "group",
        "created_at": now_iso,
        "updated_at": now_iso,
        "is_deleted": False,
    }
    await db.chat_groups.insert_one(group_doc)

    # CrÃ©er aussi une session de chat liÃ©e au groupe
    session_doc = {
        "id": f"grp_{group_id[:8]}",
        "title": name,
        "mode": "group",
        "is_ai_active": is_ai_active,
        "custom_prompt": system_prompt,
        "participant_ids": member_ids,
        "coach_id": coach_email,
        "group_id": group_id,
        "link_token": link_token,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    await db.chat_sessions.insert_one(session_doc)

    logger.info(f"[V101] â Groupe '{name}' crÃ©Ã© ({len(member_ids)} membres) par {coach_email}")
    return {**group_doc, "_id": None, "session_id": session_doc["id"]}


@api_router.get("/chat/groups")
async def get_chat_groups(request: Request):
    """v108: Liste des groupes du coach â enrichi avec noms des membres"""
    try:
        caller_email = require_auth(request)
    except HTTPException:
        caller_email = ""
    query = {"is_deleted": {"$ne": True}}
    if caller_email and not is_super_admin(caller_email):
        query["coach_id"] = caller_email
    groups = await db.chat_groups.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)

    # v108: Enrichir chaque groupe avec les noms des membres pour l'affichage
    for g in groups:
        member_ids = g.get("member_ids", [])
        members_info = []
        for mid in member_ids:
            p = await db.chat_participants.find_one({"id": mid}, {"_id": 0, "name": 1, "email": 1})
            if not p:
                p = await db.users.find_one({"id": mid}, {"_id": 0, "name": 1, "email": 1})
            if p:
                members_info.append({"id": mid, "name": p.get("name", ""), "email": p.get("email", "")})
            else:
                members_info.append({"id": mid, "name": "Inconnu", "email": ""})
        g["members_info"] = members_info

    return groups


@api_router.put("/chat/groups/{group_id}")
async def update_chat_group(group_id: str, request: Request):
    """v101: Modifier un groupe (nom, membres, prompt IA, switch IA)"""
    require_auth(request)
    body = await request.json()
    update_fields = {"updated_at": datetime.now(timezone.utc).isoformat()}
    for key in ["name", "member_ids", "system_prompt", "is_ai_active"]:
        if key in body:
            update_fields[key] = body[key]
    await db.chat_groups.update_one({"id": group_id}, {"$set": update_fields})
    # Sync session liÃ©e
    session_update = {}
    if "name" in body: session_update["title"] = body["name"]
    if "system_prompt" in body: session_update["custom_prompt"] = body["system_prompt"]
    if "is_ai_active" in body: session_update["is_ai_active"] = body["is_ai_active"]
    if "member_ids" in body: session_update["participant_ids"] = body["member_ids"]
    if session_update:
        session_update["updated_at"] = update_fields["updated_at"]
        await db.chat_sessions.update_one({"group_id": group_id}, {"$set": session_update})
    updated = await db.chat_groups.find_one({"id": group_id}, {"_id": 0})
    return updated


@api_router.delete("/chat/groups/{group_id}")
async def delete_chat_group(group_id: str, request: Request):
    """v101: Supprimer un groupe (soft delete)"""
    require_auth(request)
    now_iso = datetime.now(timezone.utc).isoformat()
    await db.chat_groups.update_one({"id": group_id}, {"$set": {"is_deleted": True, "deleted_at": now_iso}})
    await db.chat_sessions.update_one({"group_id": group_id}, {"$set": {"is_deleted": True}})
    return {"success": True}


# V107.12: Groupes publics â pour les abonnÃ©s
@api_router.get("/chat/groups/public")
async def get_public_groups(request: Request):
    """V107.12: Liste les groupes disponibles pour les abonnÃ©s.
    Retourne tous les groupes actifs avec leur session_id."""
    groups = await db.chat_groups.find(
        {"is_deleted": {"$ne": True}},
        {"_id": 0, "id": 1, "name": 1, "system_prompt": 1, "is_ai_active": 1,
         "member_ids": 1, "link_token": 1, "created_at": 1}
    ).sort("created_at", -1).to_list(50)

    # Enrichir avec session_id
    for g in groups:
        g["session_id"] = f"grp_{g['id'][:8]}"
        g["member_count"] = len(g.get("member_ids", []))

    return groups


@api_router.get("/chat/groups/{group_id}/debug")
async def debug_group_messages(group_id: str):
    """V108.3: Debug endpoint â vÃ©rifie les messages d'un groupe et sa session."""
    session_id = f"grp_{group_id[:8]}"

    # VÃ©rifier la session
    session = await db.chat_sessions.find_one({"id": session_id}, {"_id": 0})

    # VÃ©rifier le groupe
    group = await db.chat_groups.find_one({"id": group_id}, {"_id": 0})

    # Compter les messages
    messages = await db.chat_messages.find(
        {"session_id": session_id, "is_deleted": {"$ne": True}},
        {"_id": 0, "id": 1, "sender_name": 1, "sender_type": 1, "sender_id": 1, "content": 1, "session_id": 1, "created_at": 1}
    ).sort("created_at", 1).to_list(100)

    # Chercher aussi des messages avec un session_id similaire (typo, etc.)
    similar_messages = await db.chat_messages.find(
        {"session_id": {"$regex": f"grp_{group_id[:6]}"}, "is_deleted": {"$ne": True}},
        {"_id": 0, "id": 1, "session_id": 1, "sender_name": 1, "sender_type": 1, "content": 1, "created_at": 1}
    ).sort("created_at", 1).to_list(100)

    return {
        "group_id": group_id,
        "expected_session_id": session_id,
        "session_exists": session is not None,
        "session_data": {
            "id": session.get("id") if session else None,
            "mode": session.get("mode") if session else None,
            "participant_ids": session.get("participant_ids") if session else None,
            "is_deleted": session.get("is_deleted") if session else None,
            "group_id": session.get("group_id") if session else None,
        } if session else None,
        "group_data": {
            "id": group.get("id") if group else None,
            "name": group.get("name") if group else None,
            "member_ids": group.get("member_ids") if group else None,
        } if group else None,
        "messages_count": len(messages),
        "messages": messages,
        "similar_session_messages": similar_messages,
    }


@api_router.post("/chat/groups/{group_id}/join")
async def join_chat_group(group_id: str, request: Request):
    """V108: Un abonnÃ© rejoint un groupe. Assure la cohÃ©rence chat_participants + session."""
    body = await request.json()
    participant_id = body.get("participant_id", "").strip()
    if not participant_id:
        raise HTTPException(status_code=400, detail="participant_id requis")

    # VÃ©rifier que le groupe existe
    group = await db.chat_groups.find_one(
        {"id": group_id, "is_deleted": {"$ne": True}}, {"_id": 0}
    )
    if not group:
        raise HTTPException(status_code=404, detail="Groupe introuvable")

    session_id = f"grp_{group_id[:8]}"

    # v108: S'assurer que le participant existe dans chat_participants
    # Si il est dans users mais pas dans chat_participants, le crÃ©er
    existing_participant = await db.chat_participants.find_one({"id": participant_id}, {"_id": 0})
    if not existing_participant:
        user_record = await db.users.find_one({"id": participant_id}, {"_id": 0})
        if user_record:
            new_participant = {
                "id": participant_id,
                "name": user_record.get("name", "Membre"),
                "email": user_record.get("email", ""),
                "whatsapp": user_record.get("phone", ""),
                "source": "group_join",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_seen_at": datetime.now(timezone.utc).isoformat(),
            }
            # Attribuer le coach_id du groupe
            coach_id = group.get("coach_id", "")
            if coach_id:
                new_participant["coach_id"] = coach_id
            await db.chat_participants.insert_one(new_participant)
            logger.info(f"[V108] Participant {participant_id} migrÃ© usersâchat_participants pour groupe {group_id}")

    # Ajouter le participant au groupe et Ã  la session
    await db.chat_groups.update_one(
        {"id": group_id},
        {"$addToSet": {"member_ids": participant_id}}
    )
    await db.chat_sessions.update_one(
        {"id": session_id},
        {"$addToSet": {"participant_ids": participant_id}}
    )

    logger.info(f"[V108] Participant {participant_id} a rejoint le groupe '{group.get('name', '')}' ({group_id})")
    return {"success": True, "session_id": session_id, "group_name": group.get("name", "")}


# --- Private Chat from Community ---
@api_router.post("/chat/start-private")
async def start_private_chat(request: Request):
    """
    CrÃ©e une session de chat privÃ©e entre deux participants.
    UtilisÃ© quand un utilisateur clique sur un autre dans un chat communautaire.
    
    Body attendu:
    {
        "initiator_id": "xxx",  # ID du participant qui initie
        "target_id": "xxx",     # ID du participant cible
        "community_session_id": "xxx"  # ID de la session communautaire d'origine
    }
    """
    body = await request.json()
    initiator_id = body.get("initiator_id")
    target_id = body.get("target_id")
    community_session_id = body.get("community_session_id")
    
    if not initiator_id or not target_id:
        raise HTTPException(status_code=400, detail="initiator_id et target_id sont requis")
    
    # VÃ©rifier que les deux participants existent
    initiator = await db.chat_participants.find_one({"id": initiator_id}, {"_id": 0})
    target = await db.chat_participants.find_one({"id": target_id}, {"_id": 0})
    
    if not initiator or not target:
        raise HTTPException(status_code=404, detail="Participant non trouvÃ©")
    
    # VÃ©rifier s'il existe dÃ©jÃ  une session privÃ©e entre ces deux personnes
    existing_session = await db.chat_sessions.find_one({
        "participant_ids": {"$all": [initiator_id, target_id], "$size": 2},
        "mode": "human",
        "is_deleted": {"$ne": True}
    }, {"_id": 0})
    
    if existing_session:
        return {
            "session": existing_session,
            "is_new": False,
            "message": f"Reprise de la conversation avec {target.get('name', 'ce participant')}"
        }
    
    # CrÃ©er une nouvelle session privÃ©e
    private_session = ChatSession(
        mode="human",
        is_ai_active=False,
        participant_ids=[initiator_id, target_id],
        title=f"Discussion privÃ©e: {initiator.get('name', '')} & {target.get('name', '')}"
    )
    await db.chat_sessions.insert_one(private_session.model_dump())
    
    # Message d'accueil
    welcome_message = EnhancedChatMessage(
        session_id=private_session.id,
        sender_id="system",
        sender_name="SystÃ¨me",
        sender_type="ai",
        content=f"ð¬ Discussion privÃ©e crÃ©Ã©e entre {initiator.get('name', '')} et {target.get('name', '')}.",
        mode="human"
    )
    await db.chat_messages.insert_one(welcome_message.model_dump())
    
    return {
        "session": private_session.model_dump(),
        "is_new": True,
        "message": f"Nouvelle discussion privÃ©e avec {target.get('name', 'ce participant')}"
    }

# --- Custom Emojis/Stickers ---
@api_router.get("/chat/emojis")
async def get_custom_emojis():
    """RÃ©cupÃ¨re tous les emojis personnalisÃ©s uploadÃ©s par le coach"""
    emojis = await db.custom_emojis.find({"active": True}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return emojis

@api_router.post("/chat/emojis")
async def upload_custom_emoji(request: Request):
    """
    Upload un emoji personnalisÃ© (image base64).
    
    Body attendu:
    {
        "name": "happy",
        "image_data": "data:image/png;base64,...",
        "category": "emotions"  # optionnel
    }
    """
    body = await request.json()
    name = body.get("name", "").strip()
    image_data = body.get("image_data", "")
    category = body.get("category", "custom")
    
    if not name or not image_data:
        raise HTTPException(status_code=400, detail="name et image_data sont requis")
    
    # Valider le format base64
    if not image_data.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="Format d'image invalide. Utilisez base64 (data:image/...)")
    
    emoji_obj = {
        "id": str(uuid.uuid4()),
        "name": name,
        "image_data": image_data,
        "category": category,
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.custom_emojis.insert_one(emoji_obj)
    
    # Retourner sans _id (MongoDB l'ajoute automatiquement)
    emoji_obj.pop("_id", None)
    return emoji_obj

@api_router.delete("/chat/emojis/{emoji_id}")
async def delete_custom_emoji(emoji_id: str):
    """Supprime un emoji personnalisÃ©"""
    result = await db.custom_emojis.delete_one({"id": emoji_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Emoji non trouvÃ©")
    return {"success": True, "message": "Emoji supprimÃ©"}

# --- Get Session Participants (for community chat) ---
@api_router.get("/chat/sessions/{session_id}/participants")
async def get_session_participants(session_id: str):
    """RÃ©cupÃ¨re les dÃ©tails des participants d'une session"""
    session = await db.chat_sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvÃ©e")
    
    participant_ids = session.get("participant_ids", [])
    participants = []
    
    for pid in participant_ids:
        participant = await db.chat_participants.find_one({"id": pid}, {"_id": 0})
        if participant:
            participants.append({
                "id": participant.get("id"),
                "name": participant.get("name"),
                "last_seen_at": participant.get("last_seen_at")
            })
    
    return participants

# === WEB PUSH NOTIFICATIONS ===

@api_router.get("/push/vapid-key")
async def get_vapid_public_key():
    """Retourne la clÃ© publique VAPID pour l'inscription cÃ´tÃ© client"""
    return {"publicKey": VAPID_PUBLIC_KEY}

@api_router.post("/push/subscribe")
async def subscribe_push(request: Request):
    """V120: Enregistre une souscription push. Supporte role=subscriber|coach et email pour les coachs."""
    body = await request.json()
    participant_id = body.get("participant_id")
    subscription = body.get("subscription")
    role = body.get("role", "subscriber")  # V120: subscriber ou coach
    email = body.get("email", "")  # V120: email du coach pour lookup
    if not participant_id or not subscription:
        raise HTTPException(status_code=400, detail="participant_id et subscription requis")
    endpoint = subscription.get("endpoint", "")
    doc = {
        "participant_id": participant_id,
        "subscription": subscription,
        "active": True,
        "role": role,
        "email": email.lower().strip() if email else "",
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    # Securite: si endpoint existe pour AUTRE user, le reassigner au nouveau
    if endpoint:
        await db.push_subscriptions.update_one({"subscription.endpoint": endpoint}, {"$set": doc}, upsert=True)
    else:
        await db.push_subscriptions.update_one({"participant_id": participant_id}, {"$set": doc}, upsert=True)
    logger.debug(f"[PUSH] Subscribe OK: {participant_id[:8]}... role={role}")
    return {"success": True}

@api_router.delete("/push/subscribe/{participant_id}")
async def unsubscribe_push(participant_id: str):
    """Desactive la souscription push d'un participant"""
    await db.push_subscriptions.update_one({"participant_id": participant_id}, {"$set": {"active": False}})
    return {"success": True}

async def send_push_notification(participant_id: str, title: str, body: str, data: dict = None, session_id: str = None):
    """Envoie une notification push a un participant (sauf si socket actif)."""
    if not WEBPUSH_AVAILABLE or not VAPID_PRIVATE_KEY:
        return False
    # Verifier si socket actif (chat ouvert) - evite vibration inutile
    # Socket.IO dÃ©sactivÃ© en mode Vercel Serverless - envoyer toujours la notification
    # if session_id:
    #     try:
    #         room_sids = list(sio.manager.rooms.get('/', {}).get(session_id, set()))
    #         if room_sids:
    #             logger.debug(f"[PUSH] Skip - socket actif")
    #             return False
    #     except Exception:
    #         pass
    # Recuperer la souscription
    sub = await db.push_subscriptions.find_one({"participant_id": participant_id, "active": True}, {"_id": 0})
    if not sub or not sub.get("subscription"):
        return False
    subscription_info = sub["subscription"]
    payload = json.dumps({"title": title, "body": body, "icon": "/logo192.png", "badge": "/logo192.png", "data": data or {}, "timestamp": datetime.now(timezone.utc).isoformat()})
    try:
        webpush(subscription_info=subscription_info, data=payload, vapid_private_key=VAPID_PRIVATE_KEY, vapid_claims={"sub": f"mailto:{VAPID_CLAIMS_EMAIL}"})
        logger.debug(f"[PUSH] Sent OK")
        return True
    except WebPushException as e:
        if e.response and e.response.status_code in [404, 410]:
            await db.push_subscriptions.update_one({"participant_id": participant_id}, {"$set": {"active": False}})
            logger.debug(f"[PUSH] Subscription desactivee (410/404)")
        else:
            logger.error(f"[PUSH] Echec critique: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"[PUSH] Erreur: {str(e)}")
        return False

async def send_push_to_coaches(title: str, body: str, data: dict = None):
    """V120: Envoie une notification push a TOUS les coachs inscrits."""
    if not WEBPUSH_AVAILABLE or not VAPID_PRIVATE_KEY:
        return 0
    sent_count = 0
    try:
        coach_subs = await db.push_subscriptions.find({"role": "coach", "active": True}, {"_id": 0}).to_list(100)
        payload = json.dumps({"title": title, "body": body, "icon": "/logo192.png", "badge": "/logo192.png", "data": data or {"url": "/coach"}, "timestamp": datetime.now(timezone.utc).isoformat()})
        for sub in coach_subs:
            subscription_info = sub.get("subscription")
            if not subscription_info:
                continue
            try:
                webpush(subscription_info=subscription_info, data=payload, vapid_private_key=VAPID_PRIVATE_KEY, vapid_claims={"sub": f"mailto:{VAPID_CLAIMS_EMAIL}"})
                sent_count += 1
            except WebPushException as e:
                if e.response and e.response.status_code in [404, 410]:
                    await db.push_subscriptions.update_one({"participant_id": sub.get("participant_id")}, {"$set": {"active": False}})
                logger.debug(f"[PUSH-COACH] Echec: {str(e)[:80]}")
            except Exception as e:
                logger.error(f"[PUSH-COACH] Erreur: {str(e)[:80]}")
    except Exception as e:
        logger.error(f"[PUSH-COACH] Erreur globale: {str(e)}")
    logger.debug(f"[PUSH-COACH] Envoi OK: {sent_count}/{len(coach_subs) if 'coach_subs' in dir() else '?'}")
    return sent_count

async def send_backup_email(participant_id: str, message_preview: str):
    """Envoie un email de backup si la notification push echoue."""
    participant = await db.chat_participants.find_one({"id": participant_id}, {"_id": 0})
    if not participant or not participant.get("email"):
        return False
    email = participant["email"]
    name = participant.get("name", "")
    if not RESEND_AVAILABLE or not RESEND_API_KEY:
        logger.debug(f"[EMAIL] Simulation -> {email}")
        return True
    
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #d91cd2, #8b5cf6); padding: 20px; border-radius: 12px 12px 0 0; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 24px;">Afroboost</h1>
        </div>
        <div style="background: #1a1a1a; padding: 30px; color: #ffffff; border-radius: 0 0 12px 12px;">
            <p style="font-size: 16px; margin-bottom: 20px;">
                Bonjour {name},
            </p>
            <p style="font-size: 14px; color: #cccccc; margin-bottom: 20px;">
                Vous avez recu une reponse sur Afroboost :
            </p>
            <div style="background: rgba(139, 92, 246, 0.2); padding: 15px; border-radius: 8px; margin-bottom: 20px; border-left: 3px solid #8b5cf6;">
                <p style="margin: 0; font-size: 14px; color: #ffffff;">
                    "{message_preview[:150]}{'...' if len(message_preview) > 150 else ''}"
                </p>
            </div>
            <a href="https://afroboost.com" 
               style="display: inline-block; background: linear-gradient(135deg, #d91cd2, #8b5cf6); color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                Voir la conversation
            </a>
            <p style="font-size: 12px; color: #666666; margin-top: 30px;">
                Cet email a ete envoye car vous avez une notification en attente sur Afroboost.
            </p>
        </div>
    </div>
    """
    
    try:
        params = {
            "from": "Afroboost <notifications@afroboosteur.com>",
            "to": [email],
            "subject": "Nouvelle reponse sur Afroboost",
            "html": html_content
        }
        
        # Appel non-bloquant
        email_result = await asyncio.to_thread(resend.Emails.send, params)
        logger.info(f"Backup email sent to {email}: {email_result}")
        return True
    except Exception as e:
        logger.error(f"Backup email failed: {str(e)}")
        return False

async def notify_coach_new_message(participant_name: str, message_preview: str, session_id: str):
    """
    V120: Notifie le coach par push + e-mail quand un message arrive en mode humain.
    Crucial pour ne pas rater de ventes.
    """
    # V120: Push notification au coach EN PREMIER (instantanÃ©)
    try:
        await send_push_to_coaches(
            f"ð¬ {participant_name}",
            message_preview[:120],
            {"url": "/coach", "type": "new_message", "session_id": session_id}
        )
    except Exception as push_err:
        logger.warning(f"[PUSH-COACH] Erreur push: {push_err}")
    # RÃ©cupÃ©rer l'email du coach depuis coach_auth
    coach_auth = await db.coach_auth.find_one({}, {"_id": 0})
    if not coach_auth or not coach_auth.get("email"):
        logger.warning("Coach email not configured - cannot send notification")
        return False
    
    coach_email = coach_auth.get("email")
    
    # Mode simulation si Resend non configurÃ©
    if not RESEND_AVAILABLE or not RESEND_API_KEY:
        logger.info(f"[SIMULATION COACH EMAIL] To: {coach_email}")
        logger.info(f"[SIMULATION COACH EMAIL] Subject: ð Nouveau message de {participant_name}")
        logger.info(f"[SIMULATION COACH EMAIL] Message: {message_preview[:100]}...")
        logger.info(f"[SIMULATION COACH EMAIL] Session ID: {session_id}")
        logger.info(f"[SIMULATION COACH EMAIL] Email would be sent successfully (Resend not configured)")
        return True
    
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #d91cd2, #8b5cf6); padding: 20px; border-radius: 12px 12px 0 0; text-align: center;">
            <h1 style="color: white; margin: 0; font-size: 24px;">ð Nouveau message !</h1>
        </div>
        <div style="background: #1a1a1a; padding: 30px; color: #ffffff; border-radius: 0 0 12px 12px;">
            <p style="font-size: 16px; margin-bottom: 20px;">
                <strong>{participant_name}</strong> vous a envoyÃ© un message :
            </p>
            <div style="background: rgba(139, 92, 246, 0.2); padding: 15px; border-radius: 8px; margin-bottom: 20px; border-left: 3px solid #8b5cf6;">
                <p style="margin: 0; font-size: 14px; color: #ffffff;">
                    "{message_preview[:200]}{'...' if len(message_preview) > 200 else ''}"
                </p>
            </div>
            <p style="font-size: 12px; color: #aaaaaa; margin-bottom: 20px;">
                Ce message nÃ©cessite votre rÃ©ponse en mode humain.
            </p>
            <a href="https://afroboost.com/coach" 
               style="display: inline-block; background: linear-gradient(135deg, #d91cd2, #8b5cf6); color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                RÃ©pondre maintenant
            </a>
        </div>
    </div>
    """
    
    try:
        params = {
            "from": "Afroboost <notifications@afroboosteur.com>",
            "to": [coach_email],
            "subject": f"ð Nouveau message de {participant_name}",
            "html": html_content
        }
        
        email_result = await asyncio.to_thread(resend.Emails.send, params)
        logger.info(f"Coach notification email sent: {email_result}")
        return True
    except Exception as e:
        logger.error(f"Coach notification email failed: {str(e)}")
        return False

# =============================================
# ENDPOINT CAMPAGNES EMAIL VIA RESEND
# =============================================
@api_router.post("/campaigns/send-email")
async def send_campaign_email(request: Request):
    """Envoie un email de campagne via Resend - v9.0.2: DÃ©duit 1 crÃ©dit"""
    try:
        coach_email = require_auth(request)
    except HTTPException:
        coach_email = ""
    if coach_email and not is_super_admin(coach_email):
        credit_check = await check_credits(coach_email)
        if not credit_check.get("has_credits"):
            raise HTTPException(status_code=402, detail="CrÃ©dits insuffisants. Achetez un pack pour continuer.")
        await deduct_credit(coach_email, "envoi campagne email")
    body = await request.json()
    to_email = body.get("to_email")
    to_name = body.get("to_name", "")
    subject = body.get("subject", "Message d'Afroboost")
    message = body.get("message", "")
    media_url = body.get("media_url", None)
    
    # LOG DEBUG CRITIQUE
    if not to_email:
        raise HTTPException(status_code=400, detail="to_email requis")
    if not message:
        raise HTTPException(status_code=400, detail="message requis")
    if not RESEND_AVAILABLE or not RESEND_API_KEY:
        return {"success": False, "error": "Resend non configurÃ©"}
    
    # === TRAITEMENT DU MEDIA URL ===
    media_html = ""
    if media_url:
        thumbnail_url = None
        click_url = media_url
        
        # DÃ©terminer l'URL de base du frontend (production ou preview)
        # PRIORITÃ: 1. FRONTEND_URL explicite, 2. MÃªme domaine que REACT_APP_BACKEND_URL
        frontend_base = os.environ.get('FRONTEND_URL', '')
        
        # Si pas de FRONTEND_URL ou si c'est afroboost.com, vÃ©rifier si on est en preview
        if not frontend_base or 'afroboost.com' in frontend_base:
            # Utiliser le mÃªme domaine que le backend (pour l'environnement preview)
            # Le backend est appelÃ© via REACT_APP_BACKEND_URL qui contient le domaine preview
            from fastapi import Request
            # Par dÃ©faut, utiliser afroboost.com pour la production
            frontend_base = 'https://www.afroboost.com'
        
        logger.info(f"Frontend base URL: {frontend_base}")
        
        # VÃ©rifier si c'est un lien mÃ©dia interne
        # Formats supportÃ©s: /v/slug, /api/share/slug, afroboost.com/v/slug
        slug = None
        if '/api/share/' in media_url:
            slug = media_url.split('/api/share/')[-1].split('?')[0].split('#')[0].strip('/')
        elif '/v/' in media_url:
            slug = media_url.split('/v/')[-1].split('?')[0].split('#')[0].strip('/')
        
        if slug:
            # RÃ©cupÃ©rer la thumbnail depuis la base de donnÃ©es
            media_link = await db.media_links.find_one({"slug": slug.lower()}, {"_id": 0})
            if media_link:
                thumbnail_url = media_link.get("thumbnail") or media_link.get("custom_thumbnail")
                # HASH ROUTING: Utiliser /#/v/{slug} pour garantir le fonctionnement
                # sans configuration serveur (100% cÃ´tÃ© client)
                click_url = f"{frontend_base}/?_mv=1#/v/{slug}"
                logger.info(f"Media link found for slug {slug}: click_url={click_url}, thumbnail={thumbnail_url}")
            else:
                logger.warning(f"Media link not found for slug: {slug}")
        else:
            # V109: VÃ©rifier si c'est une URL YouTube â auto-crÃ©er slug MediaViewer
            import re as re_yt2
            import uuid as uuid_yt2
            yt_match2 = re_yt2.search(r'(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})', media_url)
            if yt_match2:
                yt_id2 = yt_match2.group(1)
                thumbnail_url = f"https://img.youtube.com/vi/{yt_id2}/hqdefault.jpg"
                try:
                    # Chercher ou crÃ©er un media_link
                    yt_ml = await db.media_links.find_one(
                        {"$or": [{"video_url": media_url}, {"video_url": {"$regex": yt_id2}}]},
                        {"_id": 0, "slug": 1}
                    )
                    if yt_ml and yt_ml.get("slug"):
                        click_url = f"{frontend_base}/?_mv=1#/v/{yt_ml['slug']}"
                    else:
                        auto_slug2 = f"yt-{yt_id2}".lower()
                        await db.media_links.update_one(
                            {"slug": auto_slug2},
                            {"$setOnInsert": {
                                "slug": auto_slug2,
                                "video_url": media_url,
                                "thumbnail": thumbnail_url,
                                "title": subject,
                                "created_at": datetime.utcnow().isoformat()
                            }},
                            upsert=True
                        )
                        click_url = f"{frontend_base}/?_mv=1#/v/{auto_slug2}"
                    logger.info(f"[SEND-EMAIL] YouTube â MediaViewer: {click_url}")
                except Exception as yt_err2:
                    logger.warning(f"[SEND-EMAIL] YouTube media_link error: {yt_err2}")
                    click_url = media_url
            elif any(media_url.lower().endswith(ext) for ext in ['.mp4', '.webm', '.mov']):
                # V109: VidÃ©o MP4 â chercher/crÃ©er slug MediaViewer
                thumbnail_url = None
                try:
                    mp4_ml = await db.media_links.find_one(
                        {"$or": [{"video_url": media_url}, {"video_url": {"$regex": media_url.split("/")[-1]}}]},
                        {"_id": 0, "slug": 1, "thumbnail": 1, "custom_thumbnail": 1}
                    )
                    if mp4_ml and mp4_ml.get("slug"):
                        thumbnail_url = mp4_ml.get("custom_thumbnail") or mp4_ml.get("thumbnail")
                        click_url = f"{frontend_base}/?_mv=1#/v/{mp4_ml['slug']}"
                except Exception:
                    pass
            else:
                # URL externe directe (image)
                thumbnail_url = media_url

        # GÃ©nÃ©rer le HTML de l'image cliquable - V5 FINAL (taille rÃ©duite -20%)
        if thumbnail_url:
            if thumbnail_url.startswith('http://'):
                thumbnail_url = thumbnail_url.replace('http://', 'https://')
            
            # Template V5 : Card RÃDUITE (-20%) avec image + bouton
            # Image: 400px au lieu de 536px
            media_html = f'''<!-- Image cliquable (taille rÃ©duite) -->
<a href="{click_url}" style="display:block;text-decoration:none;">
<img src="{thumbnail_url}" width="400" style="display:block;width:100%;max-width:400px;border-radius:8px;margin:0 auto;" alt="AperÃ§u vidÃ©o">
</a>
<!-- Bouton "Voir la vidÃ©o" -->
<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-top:15px;">
<tr><td align="center">
<a href="{click_url}" style="display:inline-block;padding:12px 28px;background:linear-gradient(135deg,#D91CD2,#8b5cf6);color:#ffffff;text-decoration:none;border-radius:8px;font-family:Arial,sans-serif;font-size:14px;font-weight:bold;">
&#9658; Voir la vidÃ©o
</a>
</td></tr>
</table>'''
    
    # =====================================================
    # Template Email V5 FINAL - Anti-Promotions Maximal
    # =====================================================
    # RÃGLES GMAIL ANTI-PROMOTIONS:
    # 1. TEXTE BRUT en premier (3 lignes minimum AVANT tout design)
    # 2. Salutation personnalisÃ©e
    # 3. Ratio texte > image
    # 4. Pas de gradient CSS (Gmail les ignore parfois)
    # 5. Taille rÃ©duite de 20%
    
    # Extraire le prÃ©nom pour personnalisation
    to_name = body.get("to_name", "")
    first_name = to_name.split()[0] if to_name else "ami(e)"
    preheader_text = f"Salut {first_name}, dÃ©couvre notre nouvelle vidÃ©o exclusive !"
    
    html_content = f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Message Afroboost</title>
</head>
<body style="margin:0;padding:0;background-color:#f5f5f5;font-family:Arial,Helvetica,sans-serif;">

<!-- PREHEADER INVISIBLE -->
<div style="display:none;font-size:1px;color:#f5f5f5;line-height:1px;max-height:0px;max-width:0px;opacity:0;overflow:hidden;">
{preheader_text}
</div>

<!-- WRAPPER -->
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f5f5f5;">
<tr><td align="center" style="padding:20px 10px;">

<!-- ========== TEXTE BRUT ANTI-PROMOTIONS (3 lignes AVANT le design) ========== -->
<table width="480" cellpadding="0" cellspacing="0" border="0" style="max-width:480px;">
<tr><td style="color:#333333;font-size:14px;line-height:1.6;font-family:Arial,sans-serif;padding-bottom:15px;">
Salut {first_name},<br><br>
J'ai une nouvelle vidÃ©o Ã  te partager. Je pense qu'elle va te plaire !<br>
Clique sur le bouton ci-dessous pour la dÃ©couvrir.
</td></tr>
</table>

<!-- ========== CARD PRINCIPALE (taille rÃ©duite 480px) ========== -->
<table width="480" cellpadding="0" cellspacing="0" border="0" style="max-width:480px;background-color:#111111;border-radius:10px;overflow:hidden;">

<!-- HEADER VIOLET -->
<tr><td align="center" style="background-color:#9333EA;padding:16px 20px;">
<a href="https://afroboost.com" style="color:#ffffff;font-size:22px;font-weight:bold;text-decoration:none;font-family:Arial,sans-serif;">Afroboost</a>
</td></tr>

<!-- CONTENU -->
<tr><td style="padding:20px;">

<!-- IMAGE + BOUTON -->
{media_html}

<!-- MESSAGE -->
<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-top:20px;">
<tr><td style="color:#ffffff;font-size:14px;line-height:1.6;font-family:Arial,sans-serif;">
{message.replace(chr(10), '<br>')}
</td></tr>
</table>

</td></tr>

<!-- FOOTER -->
<tr><td align="center" style="padding:15px 20px;border-top:1px solid #333333;">
<p style="color:#888888;font-size:11px;margin:0;font-family:Arial,sans-serif;">
<a href="https://afroboost.com" style="color:#9333EA;text-decoration:none;">afroboost.com</a>
</p>
</td></tr>

</table>

</td></tr>
</table>

</body>
</html>'''
    
    try:
        params = {
            "from": "Afroboost <notifications@afroboosteur.com>",
            "to": [to_email],
            "subject": subject,
            "html": html_content
        }
        
        email_result = await asyncio.to_thread(resend.Emails.send, params)
        logger.info(f"Campaign email sent to {to_email}: {email_result}")
        return {"success": True, "email_id": email_result.get("id"), "to": to_email}
    except Exception as e:
        logger.error(f"Campaign email failed: {str(e)}")
        return {"success": False, "error": str(e)}

# === v9.4.2: ENDPOINT CAMPAGNE MASSE (BACKGROUND TASK) ===
@api_router.post("/campaigns/send-bulk-email")
async def send_bulk_campaign_email(request: Request, background_tasks: BackgroundTasks):
    """
    Envoie des emails de campagne Ã  plusieurs destinataires en tÃ¢che de fond.
    Garantit que l'interface ne soit jamais bloquÃ©e (asynchrone).
    v9.4.2: Chaque email est envoyÃ© de maniÃ¨re indÃ©pendante.
    """
    body = await request.json()
    recipients = body.get("recipients", [])  # [{email, name}, ...]
    subject = body.get("subject", "Message d'Afroboost")
    message = body.get("message", "")
    media_url = body.get("media_url", None)
    try:
        coach_email = require_auth(request)
    except HTTPException:
        coach_email = ""
    
    if not recipients:
        raise HTTPException(status_code=400, detail="Aucun destinataire")
    if not message:
        raise HTTPException(status_code=400, detail="Message requis")
    
    # VÃ©rification des crÃ©dits pour tous les emails
    total_credits_needed = len(recipients)
    if coach_email and not is_super_admin(coach_email):
        credit_check = await check_credits(coach_email)
        current_credits = credit_check.get("credits", 0)
        if current_credits < total_credits_needed:
            raise HTTPException(
                status_code=402, 
                detail=f"CrÃ©dits insuffisants. Requis: {total_credits_needed}, Disponibles: {current_credits}"
            )
    
    # Fonction d'envoi en arriÃ¨re-plan
    async def send_emails_background(recipients_list, subj, msg, media, coach):
        results = {"sent": 0, "failed": 0, "errors": []}
        for recipient in recipients_list:
            try:
                to_email = recipient.get("email")
                to_name = recipient.get("name", "")
                if not to_email:
                    continue
                
                # Personnaliser le message avec le prÃ©nom
                personalized_msg = msg.replace("{prÃ©nom}", to_name).replace("{prenom}", to_name)
                
                # PrÃ©parer l'email
                if not RESEND_AVAILABLE or not RESEND_API_KEY:
                    results["failed"] += 1
                    results["errors"].append(f"{to_email}: Resend non configurÃ©")
                    continue
                
                # Construire le HTML (version simplifiÃ©e)
                html_content = f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0f0f0f;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#0f0f0f;">
<tr><td align="center" style="padding:20px;">
<table width="600" cellpadding="0" cellspacing="0" border="0" style="background:#1a1a1a;border-radius:12px;">
<tr><td style="padding:30px;">
<h1 style="color:#D91CD2;margin:0;font-size:24px;">Afroboost</h1>
<p style="color:#ffffff;margin-top:20px;line-height:1.6;">{personalized_msg.replace(chr(10), '<br>')}</p>
</td></tr>
<tr><td style="padding:15px;border-top:1px solid #333;text-align:center;">
<a href="https://afroboost.com" style="color:#9333EA;font-size:12px;">afroboost.com</a>
</td></tr>
</table>
</td></tr>
</table>
</body></html>'''
                
                params = {
                    "from": "Afroboost <notifications@afroboosteur.com>",
                    "to": [to_email],
                    "subject": subj,
                    "html": html_content
                }
                
                await asyncio.to_thread(resend.Emails.send, params)
                results["sent"] += 1
                
                # DÃ©duire le crÃ©dit
                if coach and not is_super_admin(coach):
                    await deduct_credit(coach, f"email campagne Ã  {to_email}")
                
                # Petit dÃ©lai entre les emails pour Ã©viter le rate limiting
                await asyncio.sleep(0.2)
                
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"{to_email}: {str(e)}")
                logger.error(f"Bulk email failed for {to_email}: {e}")
        
        logger.info(f"[BULK EMAIL] TerminÃ©: {results['sent']} envoyÃ©s, {results['failed']} Ã©chouÃ©s")
        return results
    
    # Lancer en arriÃ¨re-plan
    background_tasks.add_task(send_emails_background, recipients, subject, message, media_url, coach_email)
    
    return {
        "success": True,
        "message": f"Envoi de {len(recipients)} emails lancÃ© en arriÃ¨re-plan",
        "total_recipients": len(recipients),
        "status": "processing"
    }

@api_router.post("/push/send")
async def send_push_to_participant(request: Request):
    """
    Endpoint pour envoyer manuellement une notification push.
    
    Body attendu:
    {
        "participant_id": "xxx",
        "title": "Nouveau message",
        "body": "Vous avez une rÃ©ponse...",
        "send_email_backup": true
    }
    """
    body = await request.json()
    participant_id = body.get("participant_id")
    title = body.get("title", "Afroboost")
    message_body = body.get("body", "Vous avez un nouveau message")
    send_email_backup = body.get("send_email_backup", True)
    
    if not participant_id:
        raise HTTPException(status_code=400, detail="participant_id requis")
    
    # Essayer d'envoyer la notification push
    push_sent = await send_push_notification(participant_id, title, message_body)
    
    email_sent = False
    if not push_sent and send_email_backup:
        # Planifier l'email de backup aprÃ¨s 5 minutes
        # Pour l'instant, on l'envoie directement si push Ã©choue
        email_sent = await send_backup_email(participant_id, message_body)
    
    return {
        "push_sent": push_sent,
        "email_sent": email_sent,
        "participant_id": participant_id
    }
# === v87: CRON ENDPOINT â VÃ©rifie et lance les campagnes programmÃ©es ===
# v87: Helper pour parser scheduledAt (gÃ¨re Z, +00:00, et naÃ¯f)
def _parse_scheduled_at(scheduled_at_str: str) -> datetime:
    """Parse un scheduledAt ISO string vers un datetime UTC aware."""
    if not scheduled_at_str:
        return None
    try:
        s = scheduled_at_str.strip()
        # GÃ©rer le suffix Z (JavaScript toISOString())
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        dt = datetime.fromisoformat(s)
        # Si naÃ¯f (pas de timezone), on assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

@api_router.get("/cron/check-campaigns")
async def cron_check_campaigns(request: Request):
    """
    Vercel Cron job: vÃ©rifie les campagnes 'scheduled' dont scheduledAt <= now.
    Lance automatiquement chaque campagne due.
    ProtÃ©gÃ© par header Vercel CRON_SECRET ou Super Admin.
    v87: Comparaison datetime robuste (gÃ¨re Z et +00:00).
    """
    # VÃ©rification sÃ©curitÃ© (Vercel cron envoie Authorization: Bearer <CRON_SECRET>)
    auth_header = request.headers.get("Authorization", "")
    try:
        user_email = require_auth(request)
    except HTTPException:
        user_email = ""
    cron_secret = os.environ.get("CRON_SECRET", "")

    is_vercel_cron = auth_header == f"Bearer {cron_secret}" if cron_secret else False
    is_admin = is_super_admin(user_email)
    is_local_dev = not cron_secret  # Si pas de secret, on autorise (dev local)

    if not is_vercel_cron and not is_admin and not is_local_dev:
        raise HTTPException(status_code=401, detail="Unauthorized - Cron access only")

    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()

    # v87: RÃ©cupÃ©rer TOUTES les campagnes scheduled, comparer en datetime (pas string)
    all_scheduled = await db.campaigns.find({
        "status": "scheduled",
        "scheduledAt": {"$exists": True, "$ne": None}
    }).to_list(200)

    due_campaigns = []
    for campaign in all_scheduled:
        scheduled_dt = _parse_scheduled_at(campaign.get("scheduledAt", ""))
        if scheduled_dt and scheduled_dt <= now_dt:
            due_campaigns.append(campaign)

    launched = []
    errors = []

    for campaign in due_campaigns:
        campaign_id = campaign.get("id")
        campaign_name = campaign.get("name", "?")
        try:
            # RÃ©utiliser le mÃªme endpoint de lancement
            result = await launch_campaign(campaign_id)
            launched.append({"id": campaign_id, "name": campaign_name, "results_count": len(result.get("results", []))})
            logger.info(f"[CRON] â Campagne '{campaign_name}' lancÃ©e automatiquement")
        except Exception as e:
            errors.append({"id": campaign_id, "name": campaign_name, "error": str(e)})
            logger.error(f"[CRON] â Erreur lancement '{campaign_name}': {e}")
            # Marquer comme Ã©chouÃ©e pour ne pas retenter indÃ©finiment
            await db.campaigns.update_one(
                {"id": campaign_id},
                {"$set": {"status": "failed", "error": str(e)}}
            )

    # Nettoyer les campagnes bloquÃ©es en "sending" depuis plus de 10 minutes
    ten_minutes_ago = now_dt - timedelta(minutes=10)
    all_sending = await db.campaigns.find({"status": "sending"}).to_list(50)
    stuck_campaigns = []
    for sc in all_sending:
        updated_dt = _parse_scheduled_at(sc.get("updatedAt", ""))
        if updated_dt and updated_dt <= ten_minutes_ago:
            stuck_campaigns.append(sc)

    stuck_fixed = 0
    for stuck in stuck_campaigns:
        stuck_results = stuck.get("results", [])
        has_success = any(r.get("status") == "sent" for r in stuck_results)
        await db.campaigns.update_one(
            {"id": stuck.get("id")},
            {"$set": {
                "status": "completed" if has_success else "failed",
                "updatedAt": datetime.now(timezone.utc).isoformat()
            }}
        )
        stuck_fixed += 1
        logger.info(f"[CRON] ð§ Campagne bloquÃ©e '{stuck.get('name')}' corrigÃ©e â {'completed' if has_success else 'failed'}")

    # Mettre Ã  jour le heartbeat scheduler pour le badge UI
    last_run = datetime.now(timezone.utc).isoformat()

    return {
        "success": True,
        "checked_at": last_run,
        "due_campaigns": len(due_campaigns),
        "launched": launched,
        "errors": errors,
        "stuck_fixed": stuck_fixed
    }

# === v70: EMAILS EXPIRATION OFFRES â Design Afroboost Premium ===
def _email_wrapper(header_gradient: str, body_html: str) -> str:
    """V70: Template email Afroboost unifiÃ© avec design premium"""
    return f"""<div style="font-family:'Segoe UI',Arial,sans-serif;max-width:520px;margin:0 auto;background:#0a0a0a;">
<div style="background:#111;border-radius:16px;overflow:hidden;border:1px solid rgba(217,28,210,0.2);">
<div style="background:{header_gradient};padding:24px;text-align:center;">
<div style="font-size:28px;margin-bottom:4px;">ð</div>
<span style="color:#fff;font-size:22px;font-weight:800;letter-spacing:1px;">AFROBOOST</span>
<div style="color:rgba(255,255,255,0.7);font-size:11px;margin-top:4px;letter-spacing:2px;">MOVE â¢ GROOVE â¢ BOOST</div>
</div>
{body_html}
<div style="padding:16px;text-align:center;border-top:1px solid rgba(255,255,255,0.08);">
<div style="color:#666;font-size:11px;">Â© 2026 Afroboost â Tous droits rÃ©servÃ©s</div>
<div style="margin-top:6px;">
<a href="https://afroboost-v11-dev-pm7l.vercel.app" style="color:#D91CD2;font-size:11px;text-decoration:none;">afroboost.com</a>
</div>
</div>
</div></div>"""

async def send_expiry_reminder_email(coach_email: str, offer_name: str, days_remaining: int):
    """V70: Email J-7 rappel expiration â design Afroboost premium"""
    if not RESEND_API_KEY:
        logger.warning(f"[EXPIRY] Resend non configurÃ©, email ignorÃ© pour {coach_email}")
        return
    first_name = coach_email.split('@')[0].capitalize()
    subject = f"â° Plus que {days_remaining} jours â votre offre \"{offer_name}\" arrive Ã  Ã©chÃ©ance"
    urgency_bar = f"""<div style="background:rgba(245,158,11,0.15);border:1px solid rgba(245,158,11,0.4);border-radius:10px;padding:12px 16px;margin:16px 0;text-align:center;">
<span style="color:#f59e0b;font-size:24px;font-weight:800;">{days_remaining}</span>
<span style="color:#f59e0b;font-size:13px;font-weight:600;margin-left:6px;">jour{"s" if days_remaining > 1 else ""} restant{"s" if days_remaining > 1 else ""}</span>
</div>"""
    body = f"""<div style="padding:24px;color:#fff;">
<p style="font-size:16px;margin:0 0 12px;">Salut <strong>{first_name}</strong> ð</p>
<p style="color:rgba(255,255,255,0.8);line-height:1.6;margin:0 0 8px;">Votre offre <strong style="color:#D91CD2;">"{offer_name}"</strong> arrive bientÃ´t Ã  expiration.</p>
{urgency_bar}
<p style="color:rgba(255,255,255,0.7);line-height:1.6;font-size:14px;margin:0 0 8px;">ð Si la <strong style="color:#fff;">prolongation automatique</strong> est activÃ©e, votre offre sera renouvelÃ©e sans action de votre part.</p>
<p style="color:rgba(255,255,255,0.7);line-height:1.6;font-size:14px;margin:0 0 20px;">Sinon, pensez Ã  la renouveler manuellement depuis votre tableau de bord.</p>
<div style="text-align:center;margin:20px 0;">
<a href="https://afroboost-v11-dev-pm7l.vercel.app/#partner-dashboard" style="display:inline-block;padding:14px 32px;background:linear-gradient(135deg,#9333EA,#D91CD2);color:#fff;text-decoration:none;border-radius:10px;font-weight:700;font-size:15px;letter-spacing:0.5px;">GÃ©rer mes offres â</a>
</div>
</div>"""
    html = _email_wrapper("linear-gradient(135deg,#9333EA,#D91CD2)", body)
    try:
        import resend as resend_lib
        resend_lib.api_key = RESEND_API_KEY
        resend_lib.Emails.send({"from": "Afroboost <notifications@afroboosteur.com>", "to": coach_email, "subject": subject, "html": html})
        logger.info(f"[EXPIRY] â Rappel J-{days_remaining} envoyÃ© Ã  {coach_email}")
    except Exception as e:
        logger.error(f"[EXPIRY] â Email J-{days_remaining} Ã©chouÃ©: {e}")

async def send_prolongation_email(coach_email: str, offer_name: str):
    """V70: Email J-0 prolongation automatique â avec mention lÃ©gale non remboursable"""
    if not RESEND_API_KEY:
        return
    first_name = coach_email.split('@')[0].capitalize()
    subject = f"â C'est fait ! Votre offre \"{offer_name}\" a Ã©tÃ© prolongÃ©e"
    body = f"""<div style="padding:24px;color:#fff;">
<p style="font-size:16px;margin:0 0 12px;">Salut <strong>{first_name}</strong> ð</p>
<div style="background:rgba(16,185,129,0.12);border:1px solid rgba(16,185,129,0.4);border-radius:10px;padding:14px 16px;margin:12px 0;text-align:center;">
<span style="font-size:22px;">â</span>
<span style="color:#10b981;font-size:15px;font-weight:700;margin-left:8px;">Prolongation effectuÃ©e avec succÃ¨s</span>
</div>
<p style="color:rgba(255,255,255,0.8);line-height:1.6;margin:12px 0 8px;">Votre offre <strong style="color:#D91CD2;">"{offer_name}"</strong> a Ã©tÃ© automatiquement renouvelÃ©e. Vos clients peuvent continuer Ã  en profiter !</p>
<div style="background:rgba(245,158,11,0.1);border-left:3px solid #f59e0b;padding:10px 14px;margin:16px 0;border-radius:0 8px 8px 0;">
<p style="color:#f59e0b;font-size:12px;font-weight:700;margin:0 0 4px;">âï¸ MENTION LÃGALE</p>
<p style="color:rgba(255,255,255,0.7);font-size:12px;margin:0;line-height:1.5;">ConformÃ©ment aux conditions gÃ©nÃ©rales d'utilisation de la plateforme Afroboost, cette prolongation automatique est <strong style="color:#f59e0b;">dÃ©finitive et non remboursable</strong>. En activant le renouvellement automatique, vous avez acceptÃ© ces conditions. Pour dÃ©sactiver le renouvellement futur, rendez-vous dans votre tableau de bord.</p>
</div>
<div style="text-align:center;margin:20px 0;">
<a href="https://afroboost-v11-dev-pm7l.vercel.app/#partner-dashboard" style="display:inline-block;padding:14px 32px;background:linear-gradient(135deg,#9333EA,#D91CD2);color:#fff;text-decoration:none;border-radius:10px;font-weight:700;font-size:15px;letter-spacing:0.5px;">Voir mes offres â</a>
</div>
</div>"""
    html = _email_wrapper("linear-gradient(135deg,#059669,#10b981)", body)
    try:
        import resend as resend_lib
        resend_lib.api_key = RESEND_API_KEY
        resend_lib.Emails.send({"from": "Afroboost <notifications@afroboosteur.com>", "to": coach_email, "subject": subject, "html": html})
        logger.info(f"[EXPIRY] â Email prolongation envoyÃ© Ã  {coach_email}")
    except Exception as e:
        logger.error(f"[EXPIRY] â Email prolongation Ã©chouÃ©: {e}")

async def send_expired_no_credits_email(coach_email: str, offer_name: str):
    """V70: Email quand offre expire sans crÃ©dits â alerte urgente"""
    if not RESEND_API_KEY:
        return
    first_name = coach_email.split('@')[0].capitalize()
    subject = f"â ï¸ Votre offre \"{offer_name}\" a expirÃ© â Rechargez vos crÃ©dits"
    body = f"""<div style="padding:24px;color:#fff;">
<p style="font-size:16px;margin:0 0 12px;">Salut <strong>{first_name}</strong>,</p>
<div style="background:rgba(239,68,68,0.12);border:1px solid rgba(239,68,68,0.4);border-radius:10px;padding:14px 16px;margin:12px 0;text-align:center;">
<span style="font-size:22px;">â</span>
<span style="color:#ef4444;font-size:15px;font-weight:700;margin-left:8px;">Offre expirÃ©e â renouvellement impossible</span>
</div>
<p style="color:rgba(255,255,255,0.8);line-height:1.6;margin:12px 0 8px;">Votre offre <strong style="color:#ef4444;">"{offer_name}"</strong> a expirÃ© et <strong>n'a pas pu Ãªtre renouvelÃ©e</strong> car votre solde de crÃ©dits est insuffisant.</p>
<p style="color:rgba(255,255,255,0.7);line-height:1.6;font-size:14px;margin:0 0 8px;">Vos clients ne peuvent plus voir cette offre. Rechargez vos crÃ©dits pour la rÃ©activer immÃ©diatement.</p>
<div style="text-align:center;margin:20px 0;">
<a href="https://afroboost-v11-dev-pm7l.vercel.app/#partner-dashboard" style="display:inline-block;padding:14px 32px;background:linear-gradient(135deg,#ef4444,#dc2626);color:#fff;text-decoration:none;border-radius:10px;font-weight:700;font-size:15px;letter-spacing:0.5px;">Recharger mes crÃ©dits â</a>
</div>
</div>"""
    html = _email_wrapper("linear-gradient(135deg,#dc2626,#ef4444)", body)
    try:
        import resend as resend_lib
        resend_lib.api_key = RESEND_API_KEY
        resend_lib.Emails.send({"from": "Afroboost <notifications@afroboosteur.com>", "to": coach_email, "subject": subject, "html": html})
        logger.info(f"[EXPIRY] â Email offre expirÃ©e (pas de crÃ©dits) envoyÃ© Ã  {coach_email}")
    except Exception as e:
        logger.error(f"[EXPIRY] â Email expirÃ©e Ã©chouÃ©: {e}")

# === v70: ENDPOINT DE TEST EMAILS EXPIRATION (Super Admin only) ===
@api_router.post("/admin/test-expiry-email")
async def test_expiry_email(request: Request):
    """V70: Envoie les 3 types d'emails de test au Super Admin. Ne touche PAS aux donnÃ©es rÃ©elles."""
    try:
        user_email = require_auth(request)
    except HTTPException:
        user_email = ""
    if not is_super_admin(user_email):
        raise HTTPException(status_code=403, detail="RÃ©servÃ© au Super Admin")
    test_email = SUPER_ADMIN_EMAIL  # contact.artboost@gmail.com
    test_offer = "Session Afroboost Xtrem (TEST)"
    results = []
    # Email 1: Rappel J-7
    try:
        await send_expiry_reminder_email(test_email, test_offer, 7)
        results.append({"type": "J-7 Rappel", "status": "sent", "to": test_email})
    except Exception as e:
        results.append({"type": "J-7 Rappel", "status": "error", "error": str(e)})
    # Email 2: Prolongation J-0
    try:
        await send_prolongation_email(test_email, test_offer)
        results.append({"type": "J-0 Prolongation", "status": "sent", "to": test_email})
    except Exception as e:
        results.append({"type": "J-0 Prolongation", "status": "error", "error": str(e)})
    # Email 3: ExpirÃ©e sans crÃ©dits
    try:
        await send_expired_no_credits_email(test_email, test_offer)
        results.append({"type": "ExpirÃ©e sans crÃ©dits", "status": "sent", "to": test_email})
    except Exception as e:
        results.append({"type": "ExpirÃ©e sans crÃ©dits", "status": "error", "error": str(e)})
    logger.info(f"[V70-TEST] 3 emails de test envoyÃ©s Ã  {test_email}")
    return {"success": True, "message": f"3 emails de test envoyÃ©s Ã  {test_email}", "results": results}

# =====================================================
# === v71: SOCIAL BOOST â Commentaires & Social Proof ===
# =====================================================

import random as _random

# Banque de commentaires IA Afroboost
_AI_COMMENTS_BANK = [
    {"user_name": "Sarah M.", "text": "Ãnergie incroyable ! Je n'ai jamais autant transpirÃ© en m'amusant ð¥"},
    {"user_name": "Kevin D.", "text": "Le meilleur cours de ma vie, ambiance de folie !"},
    {"user_name": "Aminata K.", "text": "Je suis devenue accro, 3 cours par semaine maintenant ð"},
    {"user_name": "Lucas T.", "text": "Mon cardio a explosÃ© depuis que j'ai commencÃ© Afroboost"},
    {"user_name": "Fatou B.", "text": "L'Ã©nergie du coach est contagieuse, on ne peut pas rester immobile !"},
    {"user_name": "Marie-Claire P.", "text": "J'ai perdu 5kg en 2 mois grÃ¢ce aux sessions Afroboost ð"},
    {"user_name": "Djibril S.", "text": "Cours au casque = zÃ©ro distraction, 100% dans le mood !"},
    {"user_name": "Julie R.", "text": "MÃªme mon mari s'y est mis, c'est dire ! ð"},
    {"user_name": "Oumar N.", "text": "La meilleure dÃ©couverte fitness de 2026, sans hÃ©siter"},
    {"user_name": "ChloÃ© V.", "text": "Ambiance incroyable, on se sent comme en festival ð¶"},
    {"user_name": "IsmaÃ«l G.", "text": "Le concept casque audio change tout, on est dans sa bulle !"},
    {"user_name": "Nadia F.", "text": "Les chorÃ©s sont accessibles mÃªme pour les dÃ©butants ð"},
    {"user_name": "Thomas H.", "text": "600 calories brÃ»lÃ©es par session, c'est validÃ© par ma montre !"},
    {"user_name": "AÃ¯cha L.", "text": "Mon moment prÃ©fÃ©rÃ© de la semaine, je recommande Ã  200% ð"},
    {"user_name": "Pierre-Antoine M.", "text": "Le meilleur investissement santÃ© que j'ai fait cette annÃ©e"},
    {"user_name": "Binta D.", "text": "On transpire, on rigole, on danse... que demander de plus ?"},
    {"user_name": "Romain C.", "text": "J'ai emmenÃ© toute mon Ã©quipe, team building parfait !"},
    {"user_name": "Yasmine E.", "text": "Coach au top, playlist au top, rÃ©sultats au top â­"},
    {"user_name": "Michel B.", "text": "Ã 55 ans je fais Afroboost et j'adore, jamais trop tard !"},
    {"user_name": "Kadiatou T.", "text": "La communautÃ© Afroboost est tellement bienveillante ð¤"},
    {"user_name": "Antoine W.", "text": "Meilleur dÃ©fouloir aprÃ¨s une journÃ©e de bureau"},
    {"user_name": "Mariama S.", "text": "Ma fille de 12 ans adore aussi, c'est familial !"},
    {"user_name": "David L.", "text": "Le son dans le casque, les vibrations, l'Ã©nergie du groupe... magique"},
    {"user_name": "Sophie A.", "text": "J'ai essayÃ© plein de sports, rien ne m'a autant motivÃ©e ðª"},
    {"user_name": "Moussa K.", "text": "Chaque session est diffÃ©rente, on ne s'ennuie jamais !"},
]

@api_router.post("/admin/generate-social-proof")
async def generate_social_proof(request: Request):
    """V71: GÃ©nÃ¨re des commentaires IA (Super Admin uniquement). count=10 par dÃ©faut, max 50."""
    try:
        user_email = require_auth(request)
    except HTTPException:
        user_email = ""
    if not is_super_admin(user_email):
        raise HTTPException(status_code=403, detail="RÃ©servÃ© au Super Admin")

    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    count = min(int(body.get("count", 10)), 50)

    now = datetime.now(timezone.utc)
    generated = []

    # SÃ©lectionne des commentaires alÃ©atoires de la banque
    pool = list(_AI_COMMENTS_BANK)
    _random.shuffle(pool)
    selected = pool[:count] if count <= len(pool) else (pool * (count // len(pool) + 1))[:count]

    for i, tpl in enumerate(selected):
        # v78: GÃ©nÃ¨re un avatar unique via DiceBear API (avatars gratuits)
        avatar_seed = f"{tpl['user_name'].replace(' ', '')}{i}{now.strftime('%H%M%S')}"
        avatar_url = f"https://api.dicebear.com/7.x/avataaars/svg?seed={avatar_seed}&backgroundColor=D91CD2"
        comment = {
            "id": f"ai_{now.strftime('%Y%m%d%H%M%S')}_{i}",
            "user_name": tpl["user_name"],
            "text": tpl["text"],
            "profile_photo": avatar_url,
            "likes": _random.randint(3, 85),
            "is_ai": True,
            "is_visible": True,
            "coach_id": user_email,
            "created_at": (now - timedelta(days=_random.randint(0, 60), hours=_random.randint(0, 23))).isoformat()
        }
        await db.comments.insert_one(comment)
        generated.append(comment)

    logger.info(f"[V71] {count} commentaires IA gÃ©nÃ©rÃ©s par {user_email}")
    return {"success": True, "count": count, "comments": [{k: v for k, v in c.items() if k != "_id"} for c in generated]}

@api_router.get("/comments")
async def get_comments(request: Request):
    """V71: RÃ©cupÃ¨re les commentaires visibles (public)."""
    coach_id = request.query_params.get("coach_id", "").lower().strip()
    query = {"is_visible": True}
    if coach_id:
        query["coach_id"] = coach_id

    # v106.7: Retourner le vrai total + les 100 derniers commentaires
    total_count = await db.comments.count_documents(query)
    comments = await db.comments.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"comments": comments, "total": len(comments), "total_count": total_count}

@api_router.post("/comments/{comment_id}/like")
async def like_comment(comment_id: str):
    """V71: Ajoute un like Ã  un commentaire."""
    result = await db.comments.update_one({"id": comment_id}, {"$inc": {"likes": 1}})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Commentaire non trouvÃ©")
    return {"success": True, "comment_id": comment_id}

@api_router.post("/admin/boost-likes")
async def boost_likes(request: Request):
    """V71: Ajoute des likes en masse (Super Admin uniquement)."""
    try:
        user_email = require_auth(request)
    except HTTPException:
        user_email = ""
    if not is_super_admin(user_email):
        raise HTTPException(status_code=403, detail="RÃ©servÃ© au Super Admin")

    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    boost_amount = min(int(body.get("amount", 100)), 500)

    # Boost tous les commentaires visibles avec un montant alÃ©atoire
    comments = await db.comments.find({"is_visible": True}, {"id": 1}).to_list(500)
    boosted = 0
    for c in comments:
        add = max(1, _random.randint(int(boost_amount * 0.3), boost_amount))
        await db.comments.update_one({"id": c["id"]}, {"$inc": {"likes": add}})
        boosted += 1

    logger.info(f"[V71] Boost +{boost_amount} likes sur {boosted} commentaires par {user_email}")
    return {"success": True, "boosted_comments": boosted, "boost_amount": boost_amount}

@api_router.delete("/admin/comments")
async def clear_comments(request: Request):
    """V71: Supprime tous les commentaires IA (Super Admin uniquement)."""
    try:
        user_email = require_auth(request)
    except HTTPException:
        user_email = ""
    if not is_super_admin(user_email):
        raise HTTPException(status_code=403, detail="RÃ©servÃ© au Super Admin")

    result = await db.comments.delete_many({"is_ai": True})
    logger.info(f"[V71] {result.deleted_count} commentaires IA supprimÃ©s par {user_email}")
    return {"success": True, "deleted": result.deleted_count}

@api_router.delete("/admin/comments/{comment_id}")
async def delete_single_comment(comment_id: str, request: Request):
    """V77: Supprime un commentaire individuel (Super Admin uniquement)."""
    try:
        user_email = require_auth(request)
    except HTTPException:
        user_email = ""
    if not is_super_admin(user_email):
        raise HTTPException(status_code=403, detail="RÃ©servÃ© au Super Admin")
    result = await db.comments.delete_one({"id": comment_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Commentaire non trouvÃ©")
    logger.info(f"[V77] Commentaire {comment_id} supprimÃ© par {user_email}")
    return {"success": True, "comment_id": comment_id}

@api_router.post("/admin/comments/add")
async def add_manual_comment(request: Request):
    """V79: Ajoute un commentaire manuellement (Super Admin uniquement)."""
    try:
        user_email = require_auth(request)
    except HTTPException:
        user_email = ""
    if not is_super_admin(user_email):
        raise HTTPException(status_code=403, detail="RÃ©servÃ© au Super Admin")
    body = await request.json()
    user_name = body.get("user_name", "").strip()
    text = body.get("text", "").strip()
    profile_photo = body.get("profile_photo", "").strip()
    if not user_name or not text:
        raise HTTPException(status_code=400, detail="user_name et text requis")
    # Anti-doublon: vÃ©rifie si un commentaire identique existe dÃ©jÃ  (mÃªme nom + mÃªme texte)
    existing = await db.comments.find_one({"user_name": user_name, "text": text, "is_visible": True})
    if existing:
        raise HTTPException(status_code=409, detail="Ce commentaire existe dÃ©jÃ ")
    now = datetime.utcnow()
    avatar_seed = f"{user_name.replace(' ', '')}{now.strftime('%H%M%S')}"
    comment = {
        "id": f"manual_{now.strftime('%Y%m%d%H%M%S')}_{_random.randint(100,999)}",
        "user_name": user_name,
        "text": text,
        "profile_photo": profile_photo or f"https://api.dicebear.com/7.x/avataaars/svg?seed={avatar_seed}&backgroundColor=D91CD2",
        "likes": _random.randint(1, 20),
        "rating": 5,
        "is_ai": False,
        "is_visible": True,
        "coach_id": body.get("coach_id", user_email),
        "created_at": now.isoformat()
    }
    await db.comments.insert_one(comment)
    comment.pop("_id", None)
    logger.info(f"[V79] Commentaire manuel ajoutÃ© par {user_email}: {user_name}")
    return {"success": True, "comment": comment}

@api_router.post("/admin/comments/{comment_id}/photo")
async def update_comment_photo(comment_id: str, request: Request):
    """V77: Met Ã  jour la photo de profil d'un commentaire (Super Admin uniquement)."""
    try:
        user_email = require_auth(request)
    except HTTPException:
        user_email = ""
    if not is_super_admin(user_email):
        raise HTTPException(status_code=403, detail="RÃ©servÃ© au Super Admin")
    body = await request.json()
    photo_url = body.get("photo_url", "")
    if not photo_url:
        raise HTTPException(status_code=400, detail="photo_url requis")
    result = await db.comments.update_one({"id": comment_id}, {"$set": {"profile_photo": photo_url}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Commentaire non trouvÃ©")
    logger.info(f"[V77] Photo commentaire {comment_id} mise Ã  jour par {user_email}")
    return {"success": True, "comment_id": comment_id, "photo_url": photo_url}

# === v88: POST /api/reviews â Avis post-session soumis par un abonnÃ© identifiÃ© ===
@api_router.post("/reviews")
async def submit_review(request: Request):
    """V88: Un abonnÃ© identifiÃ© soumet un avis. Anti-spam: 1 avis par coach (pas par session vide)."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Body JSON invalide")
    participant_code = (body.get("participant_code", "") or "").strip()
    participant_name = (body.get("participant_name", "") or "").strip()
    text = (body.get("text", "") or "").strip()
    try:
        rating = int(body.get("rating", 5))
    except (ValueError, TypeError):
        rating = 5
    profile_photo = (body.get("profile_photo", "") or "").strip()
    coach_id = (body.get("coach_id", "") or "").strip().lower() or "contact.artboost@gmail.com"
    session_id = (body.get("session_id", "") or "").strip()

    if not participant_code or not text:
        raise HTTPException(status_code=400, detail="participant_code et text requis")
    if rating < 1 or rating > 5:
        rating = 5

    # v88 fix: Anti-spam â 1 avis par abonnÃ© par coach (session_id optionnel)
    # Si session_id fourni â 1 par session. Sinon â 1 par coach.
    spam_query = {"participant_code": participant_code, "is_review": True, "coach_id": coach_id}
    if session_id:
        spam_query["session_id"] = session_id
    existing = await db.comments.find_one(spam_query)
    if existing:
        raise HTTPException(status_code=409, detail="Vous avez dÃ©jÃ  laissÃ© un avis")

    now = datetime.now(timezone.utc)
    # Fallback avatar DiceBear si pas de photo
    if not profile_photo:
        avatar_seed = f"{participant_name.replace(' ', '')}{participant_code}{now.strftime('%H%M%S')}"
        profile_photo = f"https://api.dicebear.com/7.x/avataaars/svg?seed={avatar_seed}&backgroundColor=D91CD2"

    comment = {
        "id": f"review_{now.strftime('%Y%m%d%H%M%S')}_{_random.randint(100,999)}",
        "user_name": participant_name or f"AbonnÃ© {participant_code[:4]}",
        "text": text,
        "profile_photo": profile_photo,
        "rating": rating,
        "likes": 0,
        "is_ai": False,
        "is_review": True,
        "is_verified": True,
        "is_visible": True,
        "participant_code": participant_code,
        "session_id": session_id,
        "coach_id": coach_id,
        "created_at": now.isoformat()
    }
    await db.comments.insert_one(comment)
    comment.pop("_id", None)
    logger.info(f"[V88] Avis soumis par {participant_name} (code: {participant_code}, coach: {coach_id})")
    return {"success": True, "comment": comment}

# === v88: GET /api/reviews/check â VÃ©rifier si un abonnÃ© a dÃ©jÃ  laissÃ© un avis ===
@api_router.get("/reviews/check")
async def check_review(request: Request):
    """V88: VÃ©rifie si un participant a dÃ©jÃ  laissÃ© un avis pour ce coach."""
    participant_code = request.query_params.get("participant_code", "").strip()
    coach_id = request.query_params.get("coach_id", "").strip().lower()
    if not participant_code:
        return {"has_reviewed": False}
    query = {"participant_code": participant_code, "is_review": True}
    if coach_id:
        query["coach_id"] = coach_id
    existing = await db.comments.find_one(query)
    return {"has_reviewed": existing is not None}

# === v88: POST /api/reviews/request â Coach envoie manuellement une demande d'avis ===
@api_router.post("/reviews/request")
async def send_review_request(request: Request):
    """V88: Le coach envoie manuellement une demande d'avis aux participants d'un cours."""
    body = await request.json()
    coach_email = (body.get("coach_email", "") or "").strip().lower()
    course_id = (body.get("course_id", "") or "").strip()
    course_name = (body.get("course_name", "") or "").strip()

    if not coach_email:
        raise HTTPException(status_code=400, detail="coach_email requis")

    # Trouver les abonnÃ©s actifs du coach
    now = datetime.now(timezone.utc)
    subscribers = await db.users.find({
        "coach_id": coach_email,
        "subscription.end_date": {"$gte": now.isoformat()}
    }).to_list(200)

    sent_count = 0
    for sub in subscribers:
        code = sub.get("code", "")
        name = sub.get("name", sub.get("first_name", ""))
        if not code:
            continue
        # Ne pas envoyer si dÃ©jÃ  un avis
        existing = await db.comments.find_one({"participant_code": code, "is_review": True, "coach_id": coach_email})
        if existing:
            continue
        # Envoyer un message review_request dans le chat
        msg = {
            "id": f"review_req_{now.strftime('%Y%m%d%H%M%S')}_{_random.randint(100,999)}_{code}",
            "session_id": f"{coach_email}__{code}",
            "sender": "bot",
            "sender_name": "Afroboost",
            "text": f"ð¥ Bravo pour ta session {course_name or 'Afroboost'} {name} ! Comment as-tu trouvÃ© le cours ?",
            "type": "review_request",
            "timestamp": now.isoformat(),
            "read": False
        }
        await db.messages.insert_one(msg)
        sent_count += 1

    logger.info(f"[V88] Demande d'avis manuelle envoyÃ©e Ã  {sent_count} abonnÃ©s par {coach_email}")
    return {"success": True, "sent_count": sent_count}

# === v80: Page Like â Compteur de likes pour la page coach (visiteurs) ===
@api_router.post("/page-like")
async def page_like(request: Request):
    """V80: IncrÃ©mente le compteur de likes de la page coach. Public (pas besoin d'Ãªtre admin)."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    coach_email = (body.get("coach_email", "") or "").strip().lower()
    if not coach_email:
        coach_email = "contact.artboost@gmail.com"  # Default Super Admin
    # Upsert: incrÃ©menter le compteur de likes
    result = await db.page_likes.find_one_and_update(
        {"coach_email": coach_email},
        {"$inc": {"count": 1}},
        upsert=True,
        return_document=True
    )
    new_count = result.get("count", 1) if result else 1
    return {"success": True, "count": new_count}

@api_router.get("/page-likes")
async def get_page_likes(coach_email: str = "contact.artboost@gmail.com"):
    """V80: RÃ©cupÃ¨re le compteur de likes de la page coach."""
    doc = await db.page_likes.find_one({"coach_email": coach_email.lower().strip()})
    return {"count": doc.get("count", 0) if doc else 0}

# === v71: CRON â Notification chat post-cours (24h aprÃ¨s) ===
@api_router.get("/cron/post-course-feedback")
async def cron_post_course_feedback(request: Request):
    """V71: Envoie un message chat automatique 24h aprÃ¨s un cours rÃ©servÃ© pour demander un avis."""
    auth_header = request.headers.get("Authorization", "")
    cron_secret = os.environ.get("CRON_SECRET", "")
    if cron_secret and auth_header != f"Bearer {cron_secret}":
        raise HTTPException(status_code=401, detail="Non autorisÃ©")

    now = datetime.now(timezone.utc)
    target_time = now - timedelta(hours=24)

    # Cherche les rÃ©servations de cours terminÃ©s il y a ~24h (fenÃªtre de 2h)
    window_start = (target_time - timedelta(hours=1)).isoformat()
    window_end = (target_time + timedelta(hours=1)).isoformat()

    reservations = await db.reservations.find({
        "status": "confirmed",
        "date": {"$gte": window_start, "$lte": window_end},
        "feedback_sent": {"$ne": True}
    }).to_list(100)

    sent = 0
    for res in reservations:
        participant_name = res.get("name", res.get("participant_name", ""))
        coach_id = res.get("coach_id", "")
        session_id = res.get("session_id", "")

        if not participant_name or not coach_id:
            continue

        # v86: Envoie un message dans le chat privÃ© avec type review_request (bouton interactif)
        feedback_msg = {
            "id": f"feedback_{now.strftime('%Y%m%d%H%M%S')}_{sent}",
            "session_id": session_id or coach_id,
            "sender": "system",
            "sender_name": "Afroboost",
            "text": f"ð¥ Bravo pour ta session Afroboost {participant_name} ! Comment as-tu trouvÃ© le cours ?",
            "type": "review_request",
            "reservation_id": str(res.get("_id", "")),
            "timestamp": now.isoformat(),
            "is_system": True
        }
        await db.messages.insert_one(feedback_msg)

        # Marque la rÃ©servation pour ne pas renvoyer
        await db.reservations.update_one({"_id": res["_id"]}, {"$set": {"feedback_sent": True}})
        sent += 1

    logger.info(f"[V71-CRON] {sent} demandes d'avis envoyÃ©es")
    return {"success": True, "feedback_requests_sent": sent}

# === v69: CRON â VÃ©rification expirations offres (avec crÃ©dits) ===
@api_router.get("/admin/check-expirations")
async def check_expirations(request: Request):
    """Cron quotidien : rappels J-7 + prolongation auto J-0 des offres avec durÃ©e."""
    auth_header = request.headers.get("Authorization", "")
    try:
        user_email = require_auth(request)
    except HTTPException:
        user_email = ""
    cron_secret = os.environ.get("CRON_SECRET", "")
    is_vercel_cron = auth_header == f"Bearer {cron_secret}" if cron_secret else False
    is_admin = is_super_admin(user_email)
    if not is_vercel_cron and not is_admin and not cron_secret:
        pass  # dev local OK
    elif not is_vercel_cron and not is_admin:
        raise HTTPException(status_code=401, detail="Unauthorized")

    now = datetime.now(timezone.utc)
    offers = await db.offers.find({"duration_value": {"$exists": True, "$ne": None}}).to_list(500)
    reminded = 0
    prolonged = 0
    expired_no_credits = 0
    errors = []

    for offer in offers:
        try:
            offer_id = offer.get("id")
            offer_name = offer.get("name", "?")
            coach_email = offer.get("coach_id", "")
            exp_str = offer.get("expiration_date")
            if not exp_str or not coach_email:
                continue
            expiry = datetime.fromisoformat(exp_str.replace('Z', '+00:00'))
            if expiry.tzinfo is None:
                from datetime import timezone as tz
                expiry = expiry.replace(tzinfo=tz.utc)
            days_left = (expiry - now).days

            # J-7 : rappel (1 seule fois)
            if 0 < days_left <= 7 and not offer.get("last_reminded_date"):
                await send_expiry_reminder_email(coach_email, offer_name, days_left)
                await db.offers.update_one({"id": offer_id}, {"$set": {"last_reminded_date": now.isoformat()}})
                reminded += 1

            # J-0 : prolongation auto (v69: Super Admin gratuit, partenaires = 1 crÃ©dit)
            elif days_left <= 0 and offer.get("is_auto_prolong", True) and not offer.get("last_prolonged_date"):
                dv = offer.get("duration_value")
                du = offer.get("duration_unit")
                # V69: VÃ©rifier crÃ©dits pour les partenaires (Super Admin = gratuit)
                if is_super_admin(coach_email):
                    can_prolong = True
                else:
                    credit_check = await check_credits(coach_email, 1)
                    can_prolong = credit_check.get("has_credits", False)

                if can_prolong:
                    new_exp = calculate_expiration_date(now.isoformat(), dv, du)
                    await db.offers.update_one({"id": offer_id}, {"$set": {
                        "expiration_date": new_exp,
                        "last_prolonged_date": now.isoformat(),
                        "last_reminded_date": None
                    }})
                    # V69: DÃ©duire 1 crÃ©dit pour les partenaires
                    if not is_super_admin(coach_email):
                        await deduct_credit(coach_email, f"prolongation_offre_{offer_name}", 1)
                    await send_prolongation_email(coach_email, offer_name)
                    prolonged += 1
                else:
                    # V69: Pas de crÃ©dits â offre expire, email d'alerte
                    await db.offers.update_one({"id": offer_id}, {"$set": {
                        "last_prolonged_date": now.isoformat(),
                        "expired_no_credits": True
                    }})
                    await send_expired_no_credits_email(coach_email, offer_name)
                    expired_no_credits += 1
        except Exception as e:
            errors.append({"offer": offer.get("id"), "error": str(e)})
            logger.error(f"[CRON-EXPIRY] â {e}")

    logger.info(f"[CRON-EXPIRY] â {len(offers)} offres vÃ©rifiÃ©es, {reminded} rappels, {prolonged} prolongations, {expired_no_credits} expirÃ©es sans crÃ©dits")
    return {"success": True, "checked": len(offers), "reminded": reminded, "prolonged": prolonged, "expired_no_credits": expired_no_credits, "errors": errors}

# === v69: Endpoint â Prochaine expiration ===
@api_router.get("/offers/next-expiration")
async def get_next_expiration(request: Request):
    """Retourne la prochaine date d'expiration d'offre pour le dashboard."""
    user_email = require_auth(request)
    now = datetime.now(timezone.utc)
    # Super Admin voit toutes les offres, partenaire seulement les siennes
    query = {"expiration_date": {"$exists": True, "$ne": None}}
    if not is_super_admin(user_email):
        query["coach_id"] = user_email
    offers = await db.offers.find(query, {"_id": 0, "id": 1, "name": 1, "expiration_date": 1, "coach_id": 1, "is_auto_prolong": 1}).to_list(200)
    # Trier par date d'expiration la plus proche dans le futur
    upcoming = []
    for o in offers:
        exp_str = o.get("expiration_date")
        if not exp_str:
            continue
        try:
            exp = datetime.fromisoformat(exp_str.replace('Z', '+00:00'))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            days_left = (exp - now).days
            if days_left >= 0:
                upcoming.append({"id": o["id"], "name": o.get("name", "?"), "expiration_date": exp_str, "days_left": days_left, "coach_id": o.get("coach_id", ""), "is_auto_prolong": o.get("is_auto_prolong", True)})
        except Exception as e:
            logger.warning(f"[V133] Erreur parsing expiration offre {o.get('id', '?')}: {e}")
            continue
    upcoming.sort(key=lambda x: x["days_left"])
    return {"next": upcoming[0] if upcoming else None, "total_with_expiration": len(upcoming), "upcoming": upcoming[:5]}

# === SCHEDULER HEALTH ENDPOINTS ===
@api_router.get("/scheduler/status")
async def get_scheduler_status():
    """Scheduler status â uses Vercel Cron."""
    return {
        "scheduler_running": True,
        "scheduler_state": "vercel_cron",
        "mode": "Vercel Cron",
        "message": "Campaigns are auto-launched via Vercel Cron every minute."
    }

@api_router.get("/scheduler/health")
async def get_scheduler_health():
    """Scheduler health check â Vercel Cron mode."""
    return {
        "status": "active",
        "mode": "Vercel Cron",
        "last_run": datetime.now(timezone.utc).isoformat(),
        "message": "Vercel Cron checks scheduled campaigns every minute."
    }

# === SCHEDULER GROUP MESSAGE EMISSION (disabled in Vercel Serverless) ===
@api_router.post("/scheduler/emit-group-message")
async def scheduler_emit_group_message(request: Request):
    """Endpoint disabled - Socket.IO and APScheduler are not available in Vercel Serverless mode."""
    return {
        "success": False,
        "error": "Scheduler message emission is disabled in Vercel Serverless mode",
        "mode": "Vercel Serverless"
    }

# === v9.2.7: PARAMÃTRES GLOBAUX PLATEFORME (Super Admin Only) ===

# v9.5.6: Utilise la fonction is_super_admin() pour la vÃ©rification

@api_router.get("/platform-settings")
async def get_platform_settings(request: Request):
    """RÃ©cupÃ©rer les paramÃ¨tres globaux de la plateforme"""
    try:
        user_email = require_auth(request)
    except HTTPException:
        user_email = ""
    is_admin = is_super_admin(user_email)  # v9.5.6
    
    # RÃ©cupÃ©rer ou crÃ©er les settings
    settings = await db.platform_settings.find_one({"_id": "global"})
    if not settings:
        settings = {
            "_id": "global",
            "partner_access_enabled": True,  # AccÃ¨s partenaires activÃ© par dÃ©faut
            "maintenance_mode": False,       # Mode maintenance dÃ©sactivÃ© par dÃ©faut
            # v12.1: Prix des services en crÃ©dits (configurables par Super Admin)
            "service_prices": {
                "campaign": 1,       # CoÃ»t d'une campagne
                "ai_conversation": 1, # CoÃ»t d'une conversation IA
                "promo_code": 1       # CoÃ»t de gÃ©nÃ©ration d'un code promo
            },
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": user_email
        }
        await db.platform_settings.insert_one(settings)
    
    # v12.1: Assurer que service_prices existe
    service_prices = settings.get("service_prices", {
        "campaign": 1,
        "ai_conversation": 1,
        "promo_code": 1
    })
    
    return {
        "partner_access_enabled": settings.get("partner_access_enabled", True),
        "maintenance_mode": settings.get("maintenance_mode", False),
        "service_prices": service_prices,  # v12.1
        "is_super_admin": is_admin,
        "updated_at": settings.get("updated_at"),
        "updated_by": settings.get("updated_by")
    }

@api_router.put("/platform-settings")
async def update_platform_settings(request: Request):
    """Mettre Ã  jour les paramÃ¨tres globaux (Super Admin uniquement)"""
    try:
        user_email = require_auth(request)
    except HTTPException:
        user_email = ""
    
    # VÃ©rification Super Admin v9.5.6
    if not is_super_admin(user_email):
        raise HTTPException(status_code=403, detail="AccÃ¨s rÃ©servÃ© au Super Admin")
    
    try:
        data = await request.json()
    except Exception as e:
        logger.warning(f"[V133] JSON parse error: {e}")
        raise HTTPException(status_code=400, detail="Format JSON invalide")
    
    update_fields = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": user_email
    }
    
    # Mise Ã  jour des toggles
    if "partner_access_enabled" in data:
        update_fields["partner_access_enabled"] = bool(data["partner_access_enabled"])
    if "maintenance_mode" in data:
        update_fields["maintenance_mode"] = bool(data["maintenance_mode"])
    
    # v12.1: Mise Ã  jour des prix des services
    if "service_prices" in data:
        service_prices = data["service_prices"]
        update_fields["service_prices"] = {
            "campaign": max(0, int(service_prices.get("campaign", 1))),
            "ai_conversation": max(0, int(service_prices.get("ai_conversation", 1))),
            "promo_code": max(0, int(service_prices.get("promo_code", 1)))
        }
        logger.info(f"[PLATFORM-SETTINGS] Service prices updated: {update_fields['service_prices']}")
    
    # Upsert settings
    result = await db.platform_settings.update_one(
        {"_id": "global"},
        {"$set": update_fields},
        upsert=True
    )
    
    # RÃ©cupÃ©rer les settings mis Ã  jour
    settings = await db.platform_settings.find_one({"_id": "global"})
    
    logger.info(f"[PLATFORM-SETTINGS] Updated by {user_email}: {update_fields}")
    
    return {
        "success": True,
        "partner_access_enabled": settings.get("partner_access_enabled", True),
        "maintenance_mode": settings.get("maintenance_mode", False),
        "service_prices": settings.get("service_prices", {"campaign": 1, "ai_conversation": 1, "promo_code": 1}),
        "updated_at": settings.get("updated_at"),
        "message": "ParamÃ¨tres mis Ã  jour"
    }

# Include router
fastapi_app.include_router(api_router)

# v9.1.1: Include coach routes
fastapi_app.include_router(coach_router, prefix="/api")

# v9.1.2: Include campaign routes
fastapi_app.include_router(campaign_router, prefix="/api")

# v9.1.4: Include reservation routes
fastapi_app.include_router(reservation_router, prefix="/api")

# v9.1.9: Include auth routes (modularisation)
fastapi_app.include_router(auth_router, prefix="/api")
fastapi_app.include_router(legacy_auth_router, prefix="/api")

# v9.2.0: Include promo routes (modularisation)
fastapi_app.include_router(promo_router, prefix="/api")

# v13.4: Include Stripe routes (extracted)
fastapi_app.include_router(stripe_router)
init_stripe_db(db)

# v14.0: Include CinetPay routes (Mobile Money)
fastapi_app.include_router(cinetpay_router)
init_cinetpay_db(db)

# v15.0: Include multi-vendor payment routes
fastapi_app.include_router(payment_config_router)
init_payment_config_db(db)
fastapi_app.include_router(checkout_router)
init_checkout_db(db)

# V154: Include contact categories routes
fastapi_app.include_router(category_router, prefix="/api")
init_category_db(db)

# V133: CORS restreint â uniquement les domaines Afroboost autorisÃ©s
_cors_default = "https://www.afroboost.com,https://afroboost.com,https://afroboost-v11-dev.vercel.app,http://localhost:3000"
_cors_origins = os.environ.get('CORS_ORIGINS', _cors_default).split(',')
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-User-Email", "X-Requested-With"],
)

# Dynamic manifest.json endpoint for PWA
@fastapi_app.get("/api/manifest.json")
async def get_dynamic_manifest():
    """Serve dynamic manifest.json with logo and name from coach settings"""
    concept = await db.concept.find_one({})
    
    # Use coach-configured favicon (priority) or logo as fallback
    logo_url = None
    app_name = "Afroboost"  # Default name
    if concept:
        # faviconUrl has priority, then logoUrl (same as frontend)
        logo_url = concept.get("faviconUrl") or concept.get("logoUrl")
        # Use custom appName if configured
        if concept.get("appName"):
            app_name = concept.get("appName")
    
    manifest = {
        "short_name": app_name,
        "name": f"{app_name} - RÃ©servation de casque",
        "description": concept.get("description", "Le concept Afroboost : cardio + danse afrobeat + casques audio immersifs.") if concept else "Le concept Afroboost : cardio + danse afrobeat + casques audio immersifs.",
        "icons": [
            {
                "src": "favicon.ico",
                "sizes": "64x64 32x32 24x24 16x16",
                "type": "image/x-icon"
            }
        ],
        "start_url": ".",
        "display": "standalone",
        "theme_color": "#000000",
        "background_color": "#000000",
        "orientation": "portrait-primary"
    }
    
    # Add dynamic logo icons if configured â V139: separate "any" and "maskable"
    if logo_url:
        manifest["icons"] = [
            {
                "src": logo_url,
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any"
            },
            {
                "src": logo_url,
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "maskable"
            },
            {
                "src": logo_url,
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any"
            },
            {
                "src": logo_url,
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable"
            },
            {
                "src": "favicon.ico",
                "sizes": "64x64 32x32 24x24 16x16",
                "type": "image/x-icon"
            }
        ]
    else:
        # Fallback to default icons
        manifest["icons"] = [
            {
                "src": "favicon.ico",
                "sizes": "64x64 32x32 24x24 16x16",
                "type": "image/x-icon"
            },
            {
                "src": "logo192.png",
                "type": "image/png",
                "sizes": "192x192",
                "purpose": "any maskable"
            },
            {
                "src": "logo512.png",
                "type": "image/png",
                "sizes": "512x512",
                "purpose": "any maskable"
            }
        ]
    
    from fastapi.responses import JSONResponse
    return JSONResponse(content=manifest, media_type="application/manifest+json")

# === SCHEDULER (APScheduler disabled in Vercel Serverless) ===
# APScheduler and background jobs are not supported in Vercel Serverless
# Use Vercel Cron or external scheduler (e.g., Inngest, Temporal, etc.)

SCHEDULER_RUNNING = False
SCHEDULER_LAST_HEARTBEAT = None
SCHEDULER_INTERVAL = 30
@fastapi_app.on_event("startup")
async def startup_db():
    """Initialize database indexes on startup (APScheduler disabled in Vercel Serverless)."""
    logger.info("[SYSTEM] Starting Afroboost API...")

    # Index unique pour push_subscriptions (evite doublons)
    try:
        await db.push_subscriptions.create_index("endpoint", unique=True, sparse=True)
        logger.info("[INDEX] push_subscriptions.endpoint unique OK")
    except Exception:
        pass  # Index existe deja

    logger.info("[SYSTEM] Database indexes initialized")

@fastapi_app.on_event("shutdown")
async def shutdown_db_client():
    """Close database connections on shutdown."""
    client.close()
    logger.info("[SYSTEM] Database connections closed")

# Export for Vercel Serverless
app = fastapi_app
