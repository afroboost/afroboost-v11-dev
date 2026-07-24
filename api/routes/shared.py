# shared.py - Constantes et helpers partagés v9.5.6
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

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
