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

def get_coach_filter(email: str) -> dict:
    """Retourne le filtre MongoDB pour l'isolation des données coach"""
    if is_super_admin(email):
        return {}
    return {"coach_id": email.lower().strip()}
