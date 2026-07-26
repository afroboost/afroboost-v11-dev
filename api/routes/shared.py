# shared.py - Constantes et helpers partagés v9.5.6
from datetime import datetime, timezone, timedelta
import os
import logging

logger = logging.getLogger(__name__)


# === V296 : JETON D'APPAREIL ABONNÉ (« le code est le secret, l'appareil est mémorisé ») ===
#
# But : fermer la faille « email -> code » sans alourdir l'expérience. L'abonné
# entre son code UNE fois par appareil ; le backend délivre un jeton signé
# (même mécanisme JWT que le coach : JWT_SECRET, HS256) qui prouve ensuite qu'il
# détient un code valide. Distinct du JWT coach par `type: "subscriber"` et
# transporté dans l'en-tête `X-Subscriber-Token` (pour NE PAS écraser le
# `Authorization: Bearer` du coach).
#
# GARDE-FOU CAPITAL : si `JWT_SECRET` n'est pas posé, aucun jeton n'est émis et
# rien n'est masqué (comportement d'avant, à l'identique) — comme la transition
# V265. Le durcissement ne s'active donc qu'une fois le secret en place.

def jwt_secret_is_set() -> bool:
    return bool(os.environ.get("JWT_SECRET", ""))


def make_subscriber_token(code: str, email: str, days: int = 90) -> str:
    """Émet un jeton abonné signé { type:"subscriber", code, email }, valide `days` jours.
    Renvoie '' si le secret n'est pas posé (jeton impossible -> chemins existants)."""
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        return ""
    try:
        import jwt as _pyjwt
        now = datetime.now(timezone.utc)
        payload = {
            "type": "subscriber",
            "code": (code or "").strip().upper(),
            "email": (email or "").strip().lower(),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=days)).timestamp()),
        }
        tok = _pyjwt.encode(payload, secret, algorithm="HS256")
        return tok.decode("utf-8") if isinstance(tok, bytes) else tok
    except Exception:
        return ""


def subscriber_from_request(request):
    """Retourne { code, email } si un jeton abonné VALIDE est présent, sinon None.
    Cherche dans l'en-tête X-Subscriber-Token (primaire) puis Authorization Bearer
    (uniquement si le payload est de type "subscriber", pour ne pas confondre avec
    le JWT coach)."""
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        return None
    tok = (request.headers.get("X-Subscriber-Token", "") or "").strip()
    if not tok:
        auth = request.headers.get("Authorization", "") or ""
        if auth.lower().startswith("bearer "):
            tok = auth.split(" ", 1)[1].strip()
    if not tok:
        return None
    try:
        import jwt as _pyjwt
        payload = _pyjwt.decode(tok, secret, algorithms=["HS256"])
        if payload.get("type") != "subscriber":
            return None
        return {
            "code": (payload.get("code") or "").strip().upper(),
            "email": (payload.get("email") or "").strip().lower(),
        }
    except Exception:
        return None


def coach_jwt_email(request) -> str:
    """Email coach depuis un JWT SIGNÉ et vérifié (jamais X-User-Email seul, qui est
    falsifiable). Sert à autoriser un coach/admin à voir les codes en clair. '' sinon."""
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        return ""
    try:
        auth = request.headers.get("Authorization", "") or ""
        if not auth.lower().startswith("bearer "):
            return ""
        tok = auth.split(" ", 1)[1].strip()
        if not tok:
            return ""
        import jwt as _pyjwt
        payload = _pyjwt.decode(tok, secret, algorithms=["HS256"])
        if payload.get("type") == "subscriber":
            return ""  # un jeton abonné n'est pas un coach
        return (payload.get("email") or "").strip().lower()
    except Exception:
        return ""

# v9.5.6: Liste des Super Admins autorisés
SUPER_ADMIN_EMAILS = [
    "contact.artboost@gmail.com",
    "afroboost.bassi@gmail.com"
]
SUPER_ADMIN_EMAIL = "contact.artboost@gmail.com"  # Legacy compatibilité
DEFAULT_COACH_ID = SUPER_ADMIN_EMAILS[0]  # V244: etait "bassi_default" (sentinelle sans compte, invisible a tout coach). Pointe desormais sur l'admin, seul coach reel — les replis coach_id inconnu lui reviennent.
ROLE_SUPER_ADMIN = "super_admin"
ROLE_COACH = "coach"
ROLE_USER = "user"

def is_super_admin(email: str) -> bool:
    """Vérifie si l'email est celui d'un Super Admin"""
    return email and email.lower().strip() in [e.lower() for e in SUPER_ADMIN_EMAILS]

def hex_to_rgb_triplet(hex_color: str) -> str:
    """V259: « r, g, b » d'une couleur #rrggbb, pour les rgba() des emails."""
    try:
        h = (hex_color or "").strip().lstrip("#")
        if len(h) == 3:
            h = h[0] * 2 + h[1] * 2 + h[2] * 2
        if len(h) != 6:
            raise ValueError(h)
        return "%d, %d, %d" % (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except Exception:
        return "217, 28, 210"


async def get_primary_color(db, coach_email: str = "") -> str:
    """V259: couleur de marque a injecter dans les emails HTML.

    Un email ne peut pas lire les variables CSS du site : la couleur doit y
    partir en dur, donc etre relue en base au moment de l'envoi.

    Le concept est MULTI-TENANT (`concept_{email}` par coach, `concept` pour
    l'administration). On lit donc d'abord celui du coach concerne quand on le
    connait — sans quoi l'email d'un partenaire porterait la couleur d'un autre.
    Repli sur le concept global, puis sur le rose historique : une couleur
    illisible ne doit jamais empecher un email de partir.
    """
    try:
        if coach_email:
            doc = await db.concept.find_one(
                {"id": "concept_" + coach_email.lower().strip()},
                {"_id": 0, "primaryColor": 1}
            )
            if doc and doc.get("primaryColor"):
                return doc["primaryColor"]
        doc = await db.concept.find_one({"id": "concept"}, {"_id": 0, "primaryColor": 1})
        if doc and doc.get("primaryColor"):
            return doc["primaryColor"]
    except Exception as e:  # jamais bloquant : l'email prime sur sa couleur
        logger.warning(f"[V259] Couleur de marque non lue, repli sur le defaut: {e}")
    return "#D91CD2"


def get_coach_filter(email: str) -> dict:
    """Retourne le filtre MongoDB pour l'isolation des données coach"""
    if is_super_admin(email):
        return {}
    return {"coach_id": email.lower().strip()}
