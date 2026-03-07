# auth_routes.py - Routes d'authentification v9.1.9
# Extrait de server.py pour modularisation

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta
import uuid
import logging
import httpx
import hashlib
import secrets
import re

logger = logging.getLogger(__name__)

# Router avec préfixe /auth
auth_router = APIRouter(prefix="/auth", tags=["Authentication"])

# Référence DB (initialisée depuis server.py)
_db = None

# Email coach autorisé
AUTHORIZED_COACH_EMAIL = "contact.artboost@gmail.com"

# v9.5.6: Liste des Super Admins autorisés
SUPER_ADMIN_EMAILS = [
    "contact.artboost@gmail.com",
    "afroboost.bassi@gmail.com"
]

def is_super_admin_email(email: str) -> bool:
    """Vérifie si l'email est celui d'un Super Admin"""
    return email and email.lower().strip() in [e.lower() for e in SUPER_ADMIN_EMAILS]

def init_auth_db(database):
    """Initialise la référence DB"""
    global _db
    _db = database
    logger.info("[AUTH_ROUTES] Base de données initialisée")

# === MODÈLES ===
class CoachLogin(BaseModel):
    email: str
    password: Optional[str] = None


class RegisterRequest(BaseModel):
    email: str
    name: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


# === PASSWORD HASHING HELPERS ===
def hash_password(password: str) -> str:
    """Hash password using PBKDF2 with SHA256"""
    salt = secrets.token_hex(16)
    hash_val = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f"{salt}:{hash_val.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verify password against stored hash"""
    try:
        salt, hash_val = stored.split(':')
        new_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
        return new_hash.hex() == hash_val
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False


def validate_email(email: str) -> bool:
    """Validate email format using regex"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


# === ROUTES GOOGLE OAUTH ===
@auth_router.post("/google/session")
async def process_google_session(request: Request, response: Response):
    """
    Traite le session_id reçu après authentification Google.
    Vérifie que l'email est autorisé (coach@afroboost.com).

    REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    """
    try:
        body = await request.json()
        session_id = body.get("session_id")

        if not session_id:
            raise HTTPException(status_code=400, detail="session_id requis")

        # Appeler l'API Emergent pour récupérer les données de session avec retry logic
        max_retries = 3
        retry_delay = 1
        user_data = None

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    emergent_response = await client.get(
                        "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                        headers={"X-Session-ID": session_id}
                    )

                    if emergent_response.status_code == 200:
                        user_data = emergent_response.json()
                        logger.info(f"[AUTH] Google session verified on attempt {attempt + 1}")
                        break
                    else:
                        logger.warning(f"[AUTH] Google session API returned {emergent_response.status_code} on attempt {attempt + 1}")

                        if attempt < max_retries - 1:
                            import asyncio
                            await asyncio.sleep(retry_delay)
                        else:
                            raise HTTPException(status_code=401, detail="Session invalide ou expirée")
            except httpx.TimeoutException:
                logger.warning(f"[AUTH] Google session API timeout on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    import asyncio
                    await asyncio.sleep(retry_delay)
                else:
                    raise HTTPException(status_code=408, detail="Délai d'attente dépassé avec l'API d'authentification")
            except httpx.RequestError as e:
                logger.warning(f"[AUTH] Google session API request error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    import asyncio
                    await asyncio.sleep(retry_delay)
                else:
                    raise HTTPException(status_code=503, detail="Service d'authentification indisponible")

        if not user_data:
            raise HTTPException(status_code=401, detail="Session invalide ou expirée")
        
        email = user_data.get("email", "").lower()
        name = user_data.get("name", "")
        picture = user_data.get("picture", "")
        session_token = user_data.get("session_token", "")
        
        # v9.2.2: Permettre l'accès à tous les emails (Super Admin + Partenaires)
        # Le Super Admin (contact.artboost@gmail.com ou afroboost.bassi@gmail.com) a des privilèges spéciaux
        is_super_admin = is_super_admin_email(email)
        
        # Créer ou mettre à jour l'utilisateur Google
        user_id = f"coach_{uuid.uuid4().hex[:12]}"
        existing_user = await _db.google_users.find_one({"email": email}, {"_id": 0})
        
        if existing_user:
            user_id = existing_user.get("user_id", user_id)
            await _db.google_users.update_one(
                {"email": email},
                {"$set": {
                    "name": name,
                    "picture": picture,
                    "last_login": datetime.now(timezone.utc).isoformat()
                }}
            )
        else:
            await _db.google_users.insert_one({
                "user_id": user_id,
                "email": email,
                "name": name,
                "picture": picture,
                "is_coach": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_login": datetime.now(timezone.utc).isoformat()
            })
        
        # v9.2.2: Créer automatiquement un profil coach si inexistant (sauf Super Admin)
        if not is_super_admin:
            existing_coach = await _db.coaches.find_one({"email": email})
            if not existing_coach:
                # Créer un profil coach minimal avec 0 crédits
                new_coach = {
                    "id": str(uuid.uuid4()),
                    "email": email,
                    "name": name,
                    "phone": "",
                    "bio": "",
                    "photo_url": picture,
                    "role": "coach",
                    "credits": 0,  # Crédits initiaux à 0, doit acheter un pack
                    "pack_id": None,
                    "stripe_customer_id": None,
                    "stripe_connect_id": None,
                    "is_active": True,
                    "platform_name": None,
                    "logo_url": None,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": None,
                    "last_login": datetime.now(timezone.utc).isoformat()
                }
                await _db.coaches.insert_one(new_coach)
                logger.info(f"[AUTH] Nouveau coach créé automatiquement: {email}")
            else:
                # Mettre à jour last_login pour les coachs existants
                await _db.coaches.update_one(
                    {"email": email},
                    {"$set": {"last_login": datetime.now(timezone.utc).isoformat()}}
                )
        
        # Créer la session
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        await _db.coach_sessions.delete_many({"user_id": user_id})  # Supprimer les anciennes sessions
        await _db.coach_sessions.insert_one({
            "session_id": str(uuid.uuid4()),
            "user_id": user_id,
            "email": email,
            "name": name,
            "session_token": session_token,
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        
        # Définir le cookie httpOnly
        response.set_cookie(
            key="coach_session_token",
            value=session_token,
            httponly=True,
            secure=True,
            samesite="none",
            max_age=7 * 24 * 60 * 60,  # 7 jours
            path="/"
        )
        
        return {
            "success": True,
            "user": {
                "user_id": user_id,
                "email": email,
                "name": name,
                "picture": picture,
                "is_coach": True
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Google auth error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@auth_router.get("/me")
async def get_current_user(request: Request, response: Response):
    """
    Vérifie la session actuelle et retourne les infos utilisateur.
    Utilisé pour vérifier si l'utilisateur est connecté.
    Auto-renouvelle la session si elle expire dans moins de 3 jours.
    """
    # Récupérer le token depuis le cookie ou le header Authorization
    session_token = request.cookies.get("coach_session_token")

    if not session_token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            session_token = auth_header[7:]

    if not session_token:
        raise HTTPException(status_code=401, detail="Non authentifié")

    # Vérifier la session
    session = await _db.coach_sessions.find_one(
        {"session_token": session_token},
        {"_id": 0}
    )

    if not session:
        raise HTTPException(status_code=401, detail="Session invalide")

    # Vérifier l'expiration
    expires_at = session.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    if expires_at < now:
        await _db.coach_sessions.delete_one({"session_token": session_token})
        raise HTTPException(status_code=401, detail="Session expirée")

    # Auto-renewal: if session expires in less than 3 days, extend to 7 days
    time_until_expiry = expires_at - now
    three_days = timedelta(days=3)

    if time_until_expiry < three_days:
        new_expires_at = now + timedelta(days=7)
        await _db.coach_sessions.update_one(
            {"session_token": session_token},
            {"$set": {"expires_at": new_expires_at.isoformat()}}
        )

        # Refresh the cookie with new expiration
        response.set_cookie(
            key="coach_session_token",
            value=session_token,
            httponly=True,
            secure=True,
            samesite="none",
            max_age=7 * 24 * 60 * 60,  # 7 jours
            path="/"
        )

        logger.info(f"[AUTH] Session auto-renewed for user {session.get('user_id')}")

    # Récupérer l'utilisateur depuis google_users ou users_auth
    user = await _db.google_users.find_one(
        {"user_id": session.get("user_id")},
        {"_id": 0}
    )

    # Si l'utilisateur n'est pas trouvé dans google_users, chercher dans users_auth
    if not user:
        user = await _db.users_auth.find_one(
            {"user_id": session.get("user_id")},
            {"_id": 0}
        )

    if not user:
        raise HTTPException(status_code=401, detail="Utilisateur non trouvé")

    return {
        "user_id": user.get("user_id"),
        "email": user.get("email"),
        "name": user.get("name"),
        "picture": user.get("picture"),
        "is_coach": user.get("is_coach", True)
    }


@auth_router.post("/logout")
async def logout(request: Request, response: Response):
    """
    Déconnexion: supprime la session et le cookie.
    """
    session_token = request.cookies.get("coach_session_token")

    if session_token:
        await _db.coach_sessions.delete_many({"session_token": session_token})

    response.delete_cookie(
        key="coach_session_token",
        path="/",
        secure=True,
        samesite="none"
    )

    return {"success": True, "message": "Déconnexion réussie"}


# === EMAIL/PASSWORD AUTHENTICATION ===
@auth_router.post("/register")
async def register(request: Request, response: Response, user_data: RegisterRequest):
    """
    Enregistrement avec email et mot de passe.
    Crée un compte utilisateur et un profil coach automatiquement.
    """
    try:
        # Valider l'email
        if not validate_email(user_data.email):
            raise HTTPException(status_code=400, detail="Format email invalide")

        email = user_data.email.lower().strip()

        # Valider le nom
        if not user_data.name or len(user_data.name.strip()) == 0:
            raise HTTPException(status_code=400, detail="Le nom ne peut pas être vide")

        # Valider le mot de passe
        if not user_data.password or len(user_data.password) < 6:
            raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins 6 caractères")

        # Vérifier si l'email existe déjà
        existing_user = await _db.users_auth.find_one({"email": email})
        if existing_user:
            raise HTTPException(status_code=409, detail="Cet email est déjà enregistré")

        # Créer l'utilisateur
        user_id = f"coach_{uuid.uuid4().hex[:12]}"
        hashed_password = hash_password(user_data.password)

        await _db.users_auth.insert_one({
            "user_id": user_id,
            "email": email,
            "name": user_data.name.strip(),
            "password_hash": hashed_password,
            "auth_method": "email_password",
            "is_coach": True,
            "picture": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        })

        # Auto-créer un profil coach
        coach_id = str(uuid.uuid4())
        await _db.coaches.insert_one({
            "id": coach_id,
            "email": email,
            "name": user_data.name.strip(),
            "phone": "",
            "bio": "",
            "photo_url": "",
            "role": "coach",
            "credits": 0,
            "pack_id": None,
            "stripe_customer_id": None,
            "stripe_connect_id": None,
            "is_active": True,
            "platform_name": None,
            "logo_url": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
            "last_login": datetime.now(timezone.utc).isoformat()
        })

        logger.info(f"[AUTH] New user registered: {email}")

        # Créer la session
        session_token = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        await _db.coach_sessions.insert_one({
            "session_id": str(uuid.uuid4()),
            "user_id": user_id,
            "email": email,
            "name": user_data.name.strip(),
            "session_token": session_token,
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat()
        })

        # Définir le cookie
        response.set_cookie(
            key="coach_session_token",
            value=session_token,
            httponly=True,
            secure=True,
            samesite="none",
            max_age=7 * 24 * 60 * 60,
            path="/"
        )

        return {
            "success": True,
            "user": {
                "user_id": user_id,
                "email": email,
                "name": user_data.name.strip(),
                "picture": "",
                "is_coach": True
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@auth_router.post("/login")
async def login(request: Request, response: Response, user_data: LoginRequest):
    """
    Connexion avec email et mot de passe.
    """
    try:
        # Valider l'email
        if not validate_email(user_data.email):
            raise HTTPException(status_code=400, detail="Format email invalide")

        email = user_data.email.lower().strip()

        # Trouver l'utilisateur
        user = await _db.users_auth.find_one({"email": email})

        if not user:
            raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")

        # Vérifier le mot de passe
        if not verify_password(user_data.password, user.get("password_hash", "")):
            raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")

        user_id = user.get("user_id")
        name = user.get("name", "")

        # Supprimer les anciennes sessions
        await _db.coach_sessions.delete_many({"user_id": user_id})

        # Créer la nouvelle session
        session_token = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        await _db.coach_sessions.insert_one({
            "session_id": str(uuid.uuid4()),
            "user_id": user_id,
            "email": email,
            "name": name,
            "session_token": session_token,
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat()
        })

        # Mettre à jour last_login du coach
        await _db.coaches.update_one(
            {"email": email},
            {"$set": {"last_login": datetime.now(timezone.utc).isoformat()}}
        )

        # Définir le cookie
        response.set_cookie(
            key="coach_session_token",
            value=session_token,
            httponly=True,
            secure=True,
            samesite="none",
            max_age=7 * 24 * 60 * 60,
            path="/"
        )

        logger.info(f"[AUTH] User logged in: {email}")

        return {
            "success": True,
            "user": {
                "user_id": user_id,
                "email": email,
                "name": name,
                "picture": user.get("picture", ""),
                "is_coach": True
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@auth_router.post("/forgot-password")
async def forgot_password(user_data: ForgotPasswordRequest):
    """
    Demande de réinitialisation de mot de passe.
    Génère un token de réinitialisation valide 1 heure.
    """
    try:
        # Valider l'email
        if not validate_email(user_data.email):
            raise HTTPException(status_code=400, detail="Format email invalide")

        email = user_data.email.lower().strip()

        # Trouver l'utilisateur
        user = await _db.users_auth.find_one({"email": email})

        if not user:
            # Pour la sécurité, on retourne succès même si l'utilisateur n'existe pas
            logger.info(f"[AUTH] Forgot password request for non-existent user: {email}")
            return {
                "success": True,
                "message": "Si cet email existe dans notre système, vous recevrez un lien de réinitialisation"
            }

        # Générer un token de réinitialisation
        reset_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        await _db.password_resets.insert_one({
            "token": reset_token,
            "email": email,
            "user_id": user.get("user_id"),
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "used": False
        })

        logger.info(f"[AUTH] Password reset token generated for: {email}")

        # Note: Email sending can be implemented later
        return {
            "success": True,
            "message": "Si cet email existe dans notre système, vous recevrez un lien de réinitialisation"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Forgot password error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === LEGACY COACH AUTH (conservé pour compatibilité) ===
legacy_auth_router = APIRouter(prefix="/coach-auth", tags=["Legacy Auth"])

@legacy_auth_router.get("")
async def get_coach_auth():
    """DÉPRÉCIÉ: Utilisez /auth/me à la place"""
    return {"email": AUTHORIZED_COACH_EMAIL, "auth_method": "google_oauth"}

@legacy_auth_router.post("/login")
async def coach_login(login: CoachLogin):
    """DÉPRÉCIÉ: Utilisez l'authentification Google OAuth"""
    return {
        "success": False, 
        "message": "L'authentification par mot de passe a été désactivée. Veuillez utiliser 'Se connecter avec Google'."
    }


# === v9.5.6: ROUTE RÔLE UTILISATEUR ===
@auth_router.get("/role")
async def get_user_role(request: Request):
    """
    Retourne le rôle de l'utilisateur basé sur son email.
    Utilisé pour déterminer si l'utilisateur est Super Admin ou Coach.
    """
    user_email = request.headers.get('X-User-Email', '').lower().strip()
    
    if not user_email:
        return {
            "role": "user",
            "is_super_admin": False,
            "email": None
        }
    
    is_admin = is_super_admin_email(user_email)
    
    return {
        "role": "super_admin" if is_admin else "coach",
        "is_super_admin": is_admin,
        "email": user_email
    }


# === v9.5.6: CHECK PARTNER STATUS ===
@auth_router.post("/check-partner-status")
async def check_partner_status(request: Request):
    """
    Vérifie le statut partenaire d'un utilisateur connecté.
    Retourne is_partner et has_credits.
    """
    try:
        body = await request.json()
        email = body.get("email", "").lower().strip()
    except:
        email = request.headers.get('X-User-Email', '').lower().strip()
    
    if not email:
        return {
            "is_partner": False,
            "has_credits": False,
            "error": "Email non fourni"
        }
    
    # Super Admin a toujours accès
    if is_super_admin_email(email):
        return {
            "is_partner": True,
            "has_credits": True,
            "is_super_admin": True,
            "credits": -1,
            "unlimited": True
        }
    
    # Vérifier le profil coach
    coach = await _db.coaches.find_one({"email": email})
    
    if not coach:
        return {
            "is_partner": False,
            "has_credits": False,
            "credits": 0
        }
    
    credits = coach.get("credits", 0)
    
    return {
        "is_partner": True,
        "has_credits": credits > 0,
        "credits": credits
    }
