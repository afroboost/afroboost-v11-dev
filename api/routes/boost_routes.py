"""
V342 — Boost payant des publications (place de marché des vitrines).

PRINCIPE
--------
Publier sur SA PROPRE vitrine (coach) ou sur celle de SON coach (abonné) reste
GRATUIT — ce fichier n'y touche pas. Le Boost sert uniquement à faire apparaître
une publication existante sur une AUTRE vitrine (celle d'un autre coach) ou sur la
page d'accueil (la vitrine du super-admin), pendant 48 h.

PLACE DE MARCHÉ
---------------
L'argent d'un Boost va au PROPRIÉTAIRE DE LA VITRINE DE DESTINATION, jamais à
l'auteur ni à la plateforme :
  - Boost vers la vitrine du coach D  -> le coach D encaisse (ses propres clés) ;
  - Boost vers la page d'accueil      -> le super-admin encaisse (clés d'environnement).
C'est exactement le mécanisme déjà utilisé par le checkout unifié
(`checkout_routes.get_payment_keys`) : admin -> variables d'environnement,
partenaire -> collection `partner_payment_config`.

SÉCURITÉ
--------
  - Le montant vient TOUJOURS du serveur (`boost_price_chf`), jamais du client.
  - Seul l'AUTEUR d'une publication (ou le super-admin) peut la booster.
  - Le prix n'est modifiable que par un super-admin porteur d'un JWT SIGNÉ.
  - Aucun boost n'est accordé sans paiement confirmé auprès du prestataire.

Étape 1 : le prix (lecture publique, écriture super-admin).
"""
import os
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from api.routes.shared import coach_jwt_email, is_super_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["boost"])

db = None


def init_db(database):
    global db
    db = database


# ===== CONSTANTES =====

# Durée d'apparition sur la vitrine de destination, en heures.
V342_BOOST_HOURS = 48

# Prix par défaut, en CHF, si le super-admin n'a jamais rien réglé.
V342_PRIX_DEFAUT_CHF = 15

# Identifiant du document de réglages dans `platform_settings`.
V342_SETTINGS_ID = "boost_settings"

# Destination « page d'accueil » : la vitrine du super-admin.
V342_CIBLE_ACCUEIL = "home"


# ===== HELPERS =====

async def lire_prix_boost() -> int:
    """
    Prix du Boost en CHF, lu EN BASE à chaque appel (le super-admin peut le changer
    sans redéploiement). Un hoquet de la base retombe sur le défaut plutôt que de
    faire échouer un paiement en cours.
    """
    if db is None:
        return V342_PRIX_DEFAUT_CHF
    try:
        doc = await db.platform_settings.find_one({"id": V342_SETTINGS_ID}, {"_id": 0})
    except Exception as e:
        logger.error(f"[V342] Lecture du prix impossible, repli sur le défaut: {e}")
        return V342_PRIX_DEFAUT_CHF
    if not doc:
        return V342_PRIX_DEFAUT_CHF
    try:
        prix = int(doc.get("boost_price_chf", V342_PRIX_DEFAUT_CHF))
    except (TypeError, ValueError):
        return V342_PRIX_DEFAUT_CHF
    return prix if prix > 0 else V342_PRIX_DEFAUT_CHF


def exiger_super_admin(request: Request) -> str:
    """
    Renvoie l'email du super-admin appelant, ou lève un 403.

    JWT SIGNÉ uniquement : `X-User-Email` est falsifiable et ne doit jamais
    permettre de changer un prix de vente (même règle que `PUT /feature-flags`).
    """
    appelant = coach_jwt_email(request)
    if not appelant or not is_super_admin(appelant):
        raise HTTPException(status_code=403, detail="Super-admin requis")
    return appelant


# ===== MODÈLES =====

class BoostPriceUpdate(BaseModel):
    price_chf: int


# ===== ÉTAPE 1 — PRIX DU BOOST =====

@router.get("/settings/boost-price")
async def get_boost_price():
    """
    Prix du Boost — lecture PUBLIQUE.

    Public à dessein : le montant doit s'afficher dans l'info-bulle du bouton Boost
    avant toute authentification. Ce n'est pas une donnée sensible, et c'est cette
    même valeur que le serveur facturera (le client ne fait que l'afficher).
    """
    return {"price_chf": await lire_prix_boost(), "currency": "CHF"}


@router.put("/settings/boost-price")
async def update_boost_price(payload: BoostPriceUpdate, request: Request):
    """Change le prix du Boost — SUPER-ADMIN uniquement (JWT signé)."""
    appelant = exiger_super_admin(request)

    prix = int(payload.price_chf)
    if prix < 1 or prix > 10000:
        raise HTTPException(status_code=400, detail="Le prix doit être compris entre 1 et 10000 CHF")

    await db.platform_settings.update_one(
        {"id": V342_SETTINGS_ID},
        {"$set": {
            "boost_price_chf": prix,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": appelant,
        }},
        upsert=True,
    )
    logger.info(f"[V342] Prix du Boost réglé à {prix} CHF par {appelant}")
    return {"price_chf": prix, "currency": "CHF"}
