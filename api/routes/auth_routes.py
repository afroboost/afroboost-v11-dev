# auth_routes.py - Routes d'authentification v9.1.9 → V133 (JWT)
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
import os
import asyncio
import jwt as pyjwt

# Resend email
try:
    import resend
    RESEND_AVAILABLE = True
except ImportError:
    RESEND_AVAILABLE = False

RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
if RESEND_AVAILABLE and RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

FRONTEND_URL = os.environ.get('FRONTEND_URL', 'https://afroboost-v11-dev-pm7l.vercel.app')

logger = logging.getLogger(__name__)

# Router avec préfixe /auth
auth_router = APIRouter(prefix="/auth", tags=["Authentication"])

# Référence DB (initialisée depuis server.py)
_db = None

# V133: Emails admin depuis variable d'environnement
_admin_emails_env = os.environ.get('ADMIN_EMAILS', 'contact.artboost@gmail.com,afroboost.bassi@gmail.com')
SUPER_ADMIN_EMAILS = [e.strip().lower() for e in _admin_emails_env.split(',') if e.strip()]
AUTHORIZED_COACH_EMAIL = SUPER_ADMIN_EMAILS[0] if SUPER_ADMIN_EMAILS else "contact.artboost@gmail.com"

# V133: JWT configuration
# V311 : NE PAS figer le secret ici. Coolify n'injecte PAS JWT_SECRET ; il est
# résolu au DÉMARRAGE depuis MongoDB (app_secrets) par _v307_resolve_jwt_secret(),
# donc APRÈS l'import de ce module. Une copie prise à l'import resterait vide pour
# toute la vie du processus -> generate_jwt_token renvoyait "" -> /auth/login
# renvoyait un jeton VIDE -> tableau de bord vide. On garde la variable pour la
# rétrocompat, mais tout le code lit désormais _v311_jwt_secret() À CHAQUE APPEL.
JWT_SECRET = os.environ.get('JWT_SECRET', '')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_DAYS = 7

def _v311_jwt_secret() -> str:
    """V311 : lit le secret en direct depuis os.environ à CHAQUE appel (jamais figé
    à l'import) — même comportement que shared.py et server.py côté vérification."""
    return os.environ.get('JWT_SECRET', '')

def generate_jwt_token(email: str, role: str = "user") -> str:
    """Génère un JWT signé."""
    secret = _v311_jwt_secret()
    if not secret:
        # V262: cet echec etait SILENCIEUX — la connexion reussissait, le jeton
        # partait vide, et le frontend retombait sans bruit sur l'en-tete
        # `X-User-Email`, falsifiable. On le trace desormais : c'est le signal
        # qu'il manque JWT_SECRET dans l'environnement.
        logger.warning(
            "[V262] JWT_SECRET absent — jeton vide pour %s. "
            "L'authentification retombe sur X-User-Email (non signee).", email
        )
        return ""
    payload = {
        "email": email.lower().strip(),
        "role": role,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRATION_DAYS),
    }
    return pyjwt.encode(payload, secret, algorithm=JWT_ALGORITHM)

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


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


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
    """V403 — RETIRÉ. Cette route appelait `demobackend.emergentagent.com` pour
    résoudre une session « Google » qui n'en était pas une : c'était l'OAuth de
    la plateforme Emergent, sur laquelle ce projet a été construit. L'utilisateur
    voyait un écran de consentement d'une marque tierce en plein parcours
    Afroboost.

    Le bouton qui l'appelait a été retiré de `CoachLoginModal`. La route est
    conservée mais NEUTRALISÉE plutôt que supprimée : un ancien onglet resté
    ouvert, ou un signet portant `#session_id=…`, la trouverait encore. Un 410
    explicite lui dit quoi faire ; un 404 muet laisserait croire à une panne.

    Vérifié avant retrait : les 11 comptes de `users_auth` sont TOUS en
    `email_password` avec un mot de passe — personne ne se connectait par là.
    """
    raise HTTPException(
        status_code=410,
        detail="La connexion Google a été retirée. Connectez-vous avec votre e-mail et mot de passe.",
    )


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

    # SECURITY-S0 — CETTE ROUTE PROUVAIT UNE IDENTITÉ SANS JAMAIS LA DIRE.
    #
    # Le constat : le propriétaire entrait par le cookie (`CoachLoginModal.js`
    # appelle `/auth/me` au montage), donc SANS jamais passer par `/auth/login`
    # — et `/auth/login` est le seul émetteur de jeton. Résultat mesuré le
    # 29/08/2026 : `afroboost_jwt` absent, `/auth/whoami` -> `valid: false`, et
    # la moitié du tableau de bord en 403 (Utilisateurs, Codes promo, non-lus,
    # Transactions). Comme `JWT_EXPIRATION_DAYS = 7` et qu'aucune route ne
    # renouvelle un jeton, l'état revenait TOUTES LES SEMAINES.
    #
    # Pourquoi c'est sûr, et pourquoi ce n'est pas un second système d'auth :
    # on n'invente aucune preuve, on transcrit celle qui vient d'être vérifiée
    # ci-dessus. Le `session_token` est un UUID4 de `coach_sessions`, contrôlé
    # en base et supprimé s'il est périmé (lignes plus haut). Ses SEULS
    # producteurs sont `/auth/login` (PBKDF2-SHA256, 100 000 itérations, plus
    # le contrôle `pending_validation`), `/auth/register` (auto-inscription
    # refusée en 403) et `/cinetpay/register-free` (adresses super-admin
    # interdites, V2-0d). Détenir ce cookie, c'est donc avoir déjà prouvé
    # exactement ce que `/auth/login` exige.
    #
    # Le rôle est calculé par la MÊME ligne que `/auth/login` — et il reste
    # informatif : l'accès est recalculé en base par `_v309_is_coach_or_admin`,
    # un rôle menti dans un jeton n'ouvre rien.
    #
    # Purement additif : aucun appelant existant ne lit ce champ, aucune garde
    # n'est resserrée. `generate_jwt_token` rend "" (sans lever) quand
    # JWT_SECRET manque — d'où le `if`, pour ne jamais faire stocker un jeton
    # vide au client.
    _s0_email = (user.get("email") or "")
    _s0_role = "super_admin" if is_super_admin_email(_s0_email) else "coach"
    _s0_token = generate_jwt_token(_s0_email, _s0_role) if _s0_email else ""

    _reponse = {
        "user_id": user.get("user_id"),
        "email": user.get("email"),
        "name": user.get("name"),
        "picture": user.get("picture"),
        "is_coach": user.get("is_coach", True)
    }
    if _s0_token:
        _reponse["token"] = _s0_token
    return _reponse


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

        # === V2-0d : MAILLON 1 DE L'ESCALADE SUPER-ADMIN ===
        #
        # Rien n'interdisait de s'inscrire SOUS une adresse de SUPER_ADMIN_EMAILS
        # avec son propre mot de passe. Le compte naissait `pending_validation`,
        # mais `/admin/activate-coach` (en-tête falsifiable) le débloquait, puis
        # `login` accordait `role: "super_admin"` sur le seul e-mail — donc un JWT
        # RÉELLEMENT SIGNÉ, qui franchissait toutes les gardes de V2-0/b/c.
        # Mesuré : `afroboost.bassi@gmail.com` est super-admin dans les trois
        # listes du code et n'a AUCUNE fiche `users_auth`. La place était libre.
        #
        # ⚠️ MÊME RÉPONSE QUE « déjà enregistré », ET C'EST VOULU. Un 403 dédié
        # (« cette adresse est celle du super-admin ») serait un oracle : il
        # confirmerait à un inconnu quelles adresses sont privilégiées. On rend
        # donc le 409 existant, mot pour mot — indiscernable d'un e-mail occupé.
        #
        # La comparaison est celle d'`is_super_admin_email` : `.lower().strip()`
        # contre la liste minusculisée. Casse et espaces sont donc couverts sans
        # écrire de règle nouvelle.
        if is_super_admin_email(email):
            logger.warning("[V2-0d] REFUS inscription sous une adresse réservée")
            raise HTTPException(status_code=409, detail="Cet email est déjà enregistré")

        # Vérifier si l'email existe déjà
        existing_user = await _db.users_auth.find_one({"email": email})
        if existing_user:
            raise HTTPException(status_code=409, detail="Cet email est déjà enregistré")

        # V311d : FERMETURE de l'inscription ouverte. Prouvé : n'importe qui pouvait
        # POST /auth/register et obtenir un compte coach actif. Désormais une
        # auto-inscription est créée EN ATTENTE (pending_validation) et ne peut pas
        # se connecter tant qu'un super-admin ne l'a pas validée. Seul un super-admin
        # (identité JWT ou X-User-Email) peut créer un compte directement actif.
        # V311d.1 : le statut « admin » vient d'un JWT SIGNÉ vérifié, JAMAIS de
        # X-User-Email (falsifiable). Sans jeton valide -> non-admin -> compte en
        # attente. Défaut de sécurité = « en attente » : un X-User-Email usurpé ne
        # peut donc PAS créer un compte directement actif.
        _caller = ""
        _auth = request.headers.get("Authorization", "") or ""
        if _auth.lower().startswith("bearer ") and _v311_jwt_secret():
            try:
                import jwt as _pyjwt
                _p = _pyjwt.decode(_auth.split(" ", 1)[1].strip(), _v311_jwt_secret(), algorithms=["HS256"])
                _caller = (_p.get("email") or "").lower().strip()
            except Exception:
                _caller = ""
        caller_is_admin = is_super_admin_email(_caller)
        pending = not caller_is_admin  # auto-inscription = en attente de validation

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
            "pending_validation": pending,   # V311d : True = connexion bloquée jusqu'à validation
            "picture": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        })

        # Auto-créer un profil coach (inactif tant que non validé)
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
            "is_active": (not pending),      # V311d : actif seulement si créé par un admin
            "platform_name": None,
            "logo_url": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None,
            "last_login": datetime.now(timezone.utc).isoformat()
        })

        logger.info(f"[AUTH] New user registered: {email} (pending={pending})")

        # V311d : auto-inscription -> pas de session, compte en attente de validation.
        if pending:
            raise HTTPException(
                status_code=403,
                detail="Compte créé. Un administrateur doit le valider avant que vous puissiez vous connecter."
            )

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

        # V311d : compte en attente de validation -> connexion refusée. Les comptes
        # existants (sans ce champ) ne sont PAS concernés (get(...) renvoie None != True).
        if user.get("pending_validation") is True:
            raise HTTPException(
                status_code=403,
                detail="Compte en attente de validation par l'administrateur."
            )

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

        # V133: Générer JWT signé
        role = "super_admin" if is_super_admin_email(email) else "coach"
        jwt_token = generate_jwt_token(email, role)

        return {
            "success": True,
            "token": jwt_token,
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


@auth_router.get("/whoami")
async def whoami(request: Request):
    """V311e : outil de PREUVE. Décode le JWT SIGNÉ de l'appelant et renvoie son
    identité VÉRIFIÉE. Ne lit JAMAIS X-User-Email. Sert à prouver qu'une session
    donnée (celle du propriétaire) possède un vrai jeton valide — condition
    obligatoire AVANT de verrouiller quoi que ce soit en JWT-strict."""
    secret = _v311_jwt_secret()
    auth = request.headers.get("Authorization", "") or ""
    if not secret:
        return {"valid": False, "reason": "secret serveur absent"}
    if not auth.lower().startswith("bearer "):
        return {"valid": False, "reason": "aucun jeton envoyé (Authorization absent)"}
    token = auth.split(" ", 1)[1].strip()
    if not token:
        return {"valid": False, "reason": "jeton vide"}
    try:
        import jwt as _pyjwt
        p = _pyjwt.decode(token, secret, algorithms=["HS256"])
        email = (p.get("email") or "").lower().strip()
        return {
            "valid": True,
            "email": email,
            "role": p.get("role"),
            "exp": p.get("exp"),
            "is_super_admin": is_super_admin_email(email),
        }
    except Exception:
        return {"valid": False, "reason": "jeton invalide ou expiré"}


@auth_router.post("/super-admin-setup")
async def super_admin_setup(request: Request):
    """V311f : BOOTSTRAP sécurisé du mot de passe super-admin. Le propriétaire n'avait
    jamais de mot de passe (il entrait par reconnaissance auto, donc sans jeton signé).
    Cet endpoint N'ACCEPTE QUE les emails super-admin CODÉS EN DUR (sinon 403) : un
    inconnu qui l'appelle ne fait qu'envoyer un email au VRAI propriétaire — aucun gain.
    Il crée la fiche de connexion si absente, puis envoie un lien « définir mon mot de
    passe » à cette adresse (que seul le propriétaire reçoit). La preuve d'identité est
    la possession de la boîte email. Ensuite : mot de passe -> connexion -> vrai jeton."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    email = (body.get("email") or "").lower().strip()
    if not is_super_admin_email(email):
        raise HTTPException(status_code=403, detail="Réservé aux comptes super-admin")

    # 1) créer la fiche de connexion si absente (mot de passe aléatoire inutilisable)
    user = await _db.users_auth.find_one({"email": email})
    if not user:
        new_uid = f"coach_{uuid.uuid4().hex[:12]}"
        await _db.users_auth.insert_one({
            "user_id": new_uid,
            "email": email,
            "name": "Administrateur Afroboost",
            "password_hash": hash_password(secrets.token_urlsafe(32)),  # inutilisable tant que non défini
            "auth_method": "email_password",
            "is_coach": True,
            "pending_validation": False,   # super-admin -> jamais en attente
            "picture": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        user = await _db.users_auth.find_one({"email": email})
        logger.warning(f"[V311f] fiche de connexion super-admin créée pour {email}")

    # 2) token de définition de mot de passe (réutilise le mécanisme reset, 1 h)
    setup_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    await _db.password_resets.insert_one({
        "token": setup_token,
        "email": email,
        "user_id": user.get("user_id"),
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "used": False,
    })
    # Lien en dur sur le domaine de production (évite le résidu Vercel de FRONTEND_URL)
    setup_link = f"https://afroboost.com/#reset-password?token={setup_token}"

    sent = False
    if RESEND_AVAILABLE and RESEND_API_KEY:
        try:
            html_content = f"""
            <div style="background: linear-gradient(135deg, #a855f7 0%, #ec4899 100%); padding: 40px 20px; font-family: -apple-system, sans-serif; border-radius: 12px 12px 0 0;">
                <h1 style="color:#fff;margin:0;font-size:24px;">Définir votre mot de passe administrateur</h1>
            </div>
            <div style="background:#1f2937;padding:40px 20px;font-family:-apple-system,sans-serif;color:#fff;">
                <p style="margin:0 0 16px 0;">Bonjour,</p>
                <p style="margin:0 0 24px 0;color:#d1d5db;">Pour sécuriser votre accès administrateur Afroboost, définissez votre mot de passe en cliquant ci-dessous. Vous n'aurez à le faire qu'une fois par appareil.</p>
                <div style="text-align:center;margin:32px 0;">
                    <a href="{setup_link}" style="display:inline-block;background:linear-gradient(135deg,#a855f7 0%,#ec4899 100%);color:#fff;padding:12px 32px;border-radius:6px;text-decoration:none;font-weight:600;">Définir mon mot de passe</a>
                </div>
                <p style="margin:24px 0 8px 0;color:#9ca3af;font-size:13px;">Ou copiez ce lien :</p>
                <p style="margin:0 0 24px 0;word-break:break-all;color:#60a5fa;font-size:12px;">{setup_link}</p>
                <p style="margin:0 0 12px 0;color:#9ca3af;font-size:12px;">Ce lien expire dans 1 heure.</p>
                <p style="margin:0;color:#9ca3af;font-size:12px;">Si vous n'êtes pas à l'origine de cette demande, ignorez cet email : personne d'autre ne peut l'utiliser.</p>
            </div>
            """
            await asyncio.to_thread(resend.Emails.send, {
                "from": "Afroboost <notifications@afroboost.com>",
                "to": [email],
                "subject": "Définir votre mot de passe administrateur Afroboost",
                "html": html_content,
            })
            sent = True
            logger.warning(f"[V311f] email de définition de mot de passe envoyé à {email}")
        except Exception as e:
            logger.warning(f"[V311f] envoi email échoué: {e}")

    return {
        "success": True,
        "email_envoye": sent,
        "message": "Un lien pour définir votre mot de passe a été envoyé à votre adresse email.",
    }


@auth_router.post("/forgot-password")
async def forgot_password(user_data: ForgotPasswordRequest):
    """
    Demande de réinitialisation de mot de passe.
    Génère un token de réinitialisation valide 1 heure.
    Envoie un email avec un lien de réinitialisation.
    Rate limited: max 1 token par email dans les 2 dernières minutes.
    """
    try:
        # Valider l'email
        if not validate_email(user_data.email):
            raise HTTPException(status_code=400, detail="Format email invalide")

        email = user_data.email.lower().strip()

        # RATE LIMITING: Vérifier s'il y a déjà un reset token pour cet email dans les 2 dernières minutes
        two_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=2)
        recent_reset = await _db.password_resets.find_one({
            "email": email,
            "created_at": {"$gte": two_minutes_ago.isoformat()},
            "used": False
        })

        if recent_reset:
            # Retourner succès sans créer un nouveau token (anti-spam)
            logger.info(f"[AUTH] Forgot password rate limited for: {email}")
            return {
                "success": True,
                "message": "Si cet email existe dans notre système, vous recevrez un lien de réinitialisation"
            }

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

        # Envoyer l'email avec lien de réinitialisation
        reset_link = f"{FRONTEND_URL}/#reset-password?token={reset_token}"

        if RESEND_AVAILABLE and RESEND_API_KEY:
            try:
                html_content = f"""
                <div style="background: linear-gradient(135deg, #a855f7 0%, #ec4899 100%); padding: 40px 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; border-radius: 12px 12px 0 0;">
                    <h1 style="color: #fff; margin: 0; font-size: 24px;">Réinitialiser votre mot de passe</h1>
                </div>
                <div style="background: #1f2937; padding: 40px 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #fff;">
                    <p style="margin: 0 0 16px 0;">Bonjour,</p>
                    <p style="margin: 0 0 24px 0; color: #d1d5db;">Vous avez demandé la réinitialisation de votre mot de passe Afroboost. Cliquez sur le bouton ci-dessous pour continuer.</p>
                    <div style="text-align: center; margin: 32px 0;">
                        <a href="{reset_link}" style="display: inline-block; background: linear-gradient(135deg, #a855f7 0%, #ec4899 100%); color: #fff; padding: 12px 32px; border-radius: 6px; text-decoration: none; font-weight: 600;">Réinitialiser mon mot de passe</a>
                    </div>
                    <p style="margin: 24px 0 8px 0; color: #9ca3af; font-size: 13px;">Ou copiez ce lien:</p>
                    <p style="margin: 0 0 24px 0; word-break: break-all; color: #60a5fa; font-size: 12px;">{reset_link}</p>
                    <p style="margin: 0 0 12px 0; color: #9ca3af; font-size: 12px;">Ce lien expire dans 1 heure.</p>
                    <p style="margin: 0; color: #9ca3af; font-size: 12px;">Si vous n'avez pas demandé cette réinitialisation, ignorez cet email.</p>
                </div>
                """

                await asyncio.to_thread(resend.Emails.send, {
                    "from": "Afroboost <notifications@afroboost.com>",
                    "to": [email],
                    "subject": "Réinitialiser votre mot de passe Afroboost",
                    "html": html_content
                })
                logger.info(f"[AUTH] Password reset email sent to: {email}")
            except Exception as e:
                logger.warning(f"[AUTH] Failed to send password reset email to {email}: {e}")
                # Continue even if email fails - token is still valid

        return {
            "success": True,
            "message": "Si cet email existe dans notre système, vous recevrez un lien de réinitialisation"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Forgot password error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@auth_router.post("/reset-password")
async def reset_password(user_data: ResetPasswordRequest):
    """
    Réinitialise le mot de passe avec un token valide.
    Accepte le token généré par /forgot-password et le nouveau mot de passe.
    """
    try:
        token = user_data.token.strip()
        new_password = user_data.new_password

        # Valider le mot de passe
        if not new_password or len(new_password) < 6:
            raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins 6 caractères")

        # Trouver le token
        reset_record = await _db.password_resets.find_one({
            "token": token,
            "used": False
        })

        if not reset_record:
            raise HTTPException(status_code=400, detail="Token invalide ou expiré")

        # Vérifier l'expiration
        expires_at = reset_record.get("expires_at")
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Token expiré")

        # Trouver l'utilisateur
        email = reset_record.get("email")
        user = await _db.users_auth.find_one({"email": email})

        if not user:
            raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

        # Hasher le nouveau mot de passe
        hashed_password = hash_password(new_password)

        # Mettre à jour le mot de passe
        await _db.users_auth.update_one(
            {"email": email},
            {
                "$set": {
                    "password_hash": hashed_password,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )

        # Marquer le token comme utilisé
        await _db.password_resets.update_one(
            {"token": token},
            {
                "$set": {
                    "used": True,
                    "used_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )

        logger.info(f"[AUTH] Password reset successful for: {email}")

        return {
            "success": True,
            "message": "Mot de passe réinitialisé avec succès"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reset password error: {e}")
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
    except Exception:
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
