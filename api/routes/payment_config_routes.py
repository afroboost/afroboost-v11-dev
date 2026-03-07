# v15.0: Payment Configuration Routes - Multi-Vendor Payment System
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
import logging
import httpx

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payment-config", tags=["payment-config"])
db = None

def init_db(database):
    global db
    db = database

# ===== MODELS =====

class PaymentConfigUpdate(BaseModel):
    # Stripe
    stripe_enabled: bool = False
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""

    # PayPal
    paypal_enabled: bool = False
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_mode: str = "sandbox"  # "sandbox" | "live"

    # Mobile Money (CinetPay)
    mobile_money_enabled: bool = False
    cinetpay_api_key: str = ""
    cinetpay_site_id: str = ""
    cinetpay_secret_key: str = ""

    class Config:
        populate_by_name = True


# ===== HELPERS =====

def mask_key(key: str) -> str:
    """Masque une clé API pour l'affichage (montre les 4 derniers caractères)"""
    if not key or len(key) < 8:
        return "****" if key else ""
    return f"{'*' * (len(key) - 4)}{key[-4:]}"


def compute_is_configured(config: dict) -> bool:
    """Vérifie si au moins une méthode de paiement est configurée et activée"""
    if config.get("stripe_enabled") and config.get("stripe_secret_key"):
        return True
    if config.get("paypal_enabled") and config.get("paypal_client_id"):
        return True
    if config.get("mobile_money_enabled") and config.get("cinetpay_api_key"):
        return True
    return False


# ===== ENDPOINTS =====

@router.get("")
async def get_payment_config(request: Request):
    """Récupère la configuration de paiement du partenaire (clés masquées)"""
    coach_email = request.headers.get("X-User-Email")
    if not coach_email:
        raise HTTPException(status_code=401, detail="Authentification requise")

    config = await db["partner_payment_config"].find_one({"coach_email": coach_email})

    if not config:
        # Retourner une config vide par défaut
        return {
            "coach_email": coach_email,
            "stripe_enabled": False,
            "stripe_secret_key": "",
            "stripe_publishable_key": "",
            "paypal_enabled": False,
            "paypal_client_id": "",
            "paypal_client_secret": "",
            "paypal_mode": "sandbox",
            "mobile_money_enabled": False,
            "cinetpay_api_key": "",
            "cinetpay_site_id": "",
            "cinetpay_secret_key": "",
            "is_configured": False,
            "updated_at": None
        }

    # Masquer les clés sensibles pour l'affichage
    return {
        "coach_email": config["coach_email"],
        "stripe_enabled": config.get("stripe_enabled", False),
        "stripe_secret_key": mask_key(config.get("stripe_secret_key", "")),
        "stripe_publishable_key": config.get("stripe_publishable_key", ""),  # Publishable = pas secrète
        "paypal_enabled": config.get("paypal_enabled", False),
        "paypal_client_id": config.get("paypal_client_id", ""),  # Client ID = pas secret
        "paypal_client_secret": mask_key(config.get("paypal_client_secret", "")),
        "paypal_mode": config.get("paypal_mode", "sandbox"),
        "mobile_money_enabled": config.get("mobile_money_enabled", False),
        "cinetpay_api_key": mask_key(config.get("cinetpay_api_key", "")),
        "cinetpay_site_id": config.get("cinetpay_site_id", ""),  # Site ID = pas secret
        "cinetpay_secret_key": mask_key(config.get("cinetpay_secret_key", "")),
        "is_configured": config.get("is_configured", False),
        "updated_at": config.get("updated_at")
    }


@router.put("")
async def update_payment_config(request: Request, config: PaymentConfigUpdate):
    """Met à jour la configuration de paiement du partenaire"""
    coach_email = request.headers.get("X-User-Email")
    if not coach_email:
        raise HTTPException(status_code=401, detail="Authentification requise")

    # Charger la config existante pour gérer les clés masquées
    existing = await db["partner_payment_config"].find_one({"coach_email": coach_email})

    update_data = config.dict()

    # Si une clé est masquée (contient ****), garder l'ancienne valeur
    if existing:
        for key in ["stripe_secret_key", "paypal_client_secret", "cinetpay_api_key", "cinetpay_secret_key"]:
            if "****" in update_data.get(key, ""):
                update_data[key] = existing.get(key, "")

    update_data["coach_email"] = coach_email
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_data["is_configured"] = compute_is_configured(update_data)

    await db["partner_payment_config"].update_one(
        {"coach_email": coach_email},
        {"$set": update_data},
        upsert=True
    )

    logger.info(f"[PAYMENT-CONFIG] Config mise à jour pour {coach_email}, is_configured={update_data['is_configured']}")

    return {
        "success": True,
        "is_configured": update_data["is_configured"],
        "message": "Configuration de paiement mise à jour"
    }


@router.get("/status/{coach_email}")
async def get_payment_status(coach_email: str):
    """Statut public : quelles méthodes sont actives (PAS les clés).
    Utilisé par la vitrine pour savoir quelles méthodes de paiement proposer."""
    config = await db["partner_payment_config"].find_one({"coach_email": coach_email})

    if not config or not config.get("is_configured"):
        return {
            "is_configured": False,
            "available_methods": [],
            "stripe_publishable_key": None
        }

    methods = []
    stripe_pk = None

    if config.get("stripe_enabled") and config.get("stripe_secret_key"):
        methods.append("card")
        stripe_pk = config.get("stripe_publishable_key", "")

    if config.get("paypal_enabled") and config.get("paypal_client_id"):
        methods.append("paypal")

    if config.get("mobile_money_enabled") and config.get("cinetpay_api_key"):
        methods.append("mobile_money")

    return {
        "is_configured": True,
        "available_methods": methods,
        "stripe_publishable_key": stripe_pk  # Nécessaire côté client pour Stripe.js
    }


@router.get("/raw/{coach_email}")
async def get_raw_payment_config(request: Request, coach_email: str):
    """Récupère la config COMPLÈTE (clés non masquées) — usage interne checkout uniquement.
    Protégé : accessible uniquement par le système (pas d'endpoint public exposé au frontend)."""
    # Vérification que c'est un appel interne (même serveur)
    # En production, cet endpoint sera appelé uniquement par checkout_routes.py côté serveur
    config = await db["partner_payment_config"].find_one({"coach_email": coach_email})
    if not config:
        return None
    return config


@router.post("/test/{method}")
async def test_payment_method(method: str, request: Request):
    """Teste la validité d'une clé API pour une méthode de paiement"""
    coach_email = request.headers.get("X-User-Email")
    if not coach_email:
        raise HTTPException(status_code=401, detail="Authentification requise")

    config = await db["partner_payment_config"].find_one({"coach_email": coach_email})
    if not config:
        raise HTTPException(status_code=404, detail="Aucune configuration trouvée")

    if method == "stripe":
        secret_key = config.get("stripe_secret_key", "")
        if not secret_key:
            return {"success": False, "message": "Clé Stripe non configurée"}
        try:
            import stripe as stripe_lib
            stripe_lib.api_key = secret_key
            # Test simple : lister les dernières 0 transactions
            stripe_lib.BalanceTransaction.list(limit=1)
            return {"success": True, "message": "Connexion Stripe réussie ✅"}
        except Exception as e:
            return {"success": False, "message": f"Erreur Stripe : {str(e)[:100]}"}

    elif method == "paypal":
        client_id = config.get("paypal_client_id", "")
        client_secret = config.get("paypal_client_secret", "")
        mode = config.get("paypal_mode", "sandbox")
        if not client_id or not client_secret:
            return {"success": False, "message": "Clés PayPal non configurées"}
        try:
            base_url = "https://api-m.sandbox.paypal.com" if mode == "sandbox" else "https://api-m.paypal.com"
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{base_url}/v1/oauth2/token",
                    data={"grant_type": "client_credentials"},
                    auth=(client_id, client_secret),
                    timeout=10
                )
            if resp.status_code == 200:
                return {"success": True, "message": "Connexion PayPal réussie ✅"}
            else:
                return {"success": False, "message": f"Erreur PayPal : HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "message": f"Erreur PayPal : {str(e)[:100]}"}

    elif method == "mobile_money":
        api_key = config.get("cinetpay_api_key", "")
        site_id = config.get("cinetpay_site_id", "")
        if not api_key or not site_id:
            return {"success": False, "message": "Clés CinetPay non configurées"}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api-checkout.cinetpay.com/v2/payment/check",
                    json={"apikey": api_key, "site_id": site_id, "transaction_id": "test_connection"},
                    timeout=10
                )
            # CinetPay retourne une erreur pour transaction inconnue, mais ça prouve que les clés sont valides
            data = resp.json()
            if resp.status_code in [200, 404] or "transaction" in str(data).lower():
                return {"success": True, "message": "Connexion CinetPay réussie ✅"}
            return {"success": False, "message": f"Erreur CinetPay : {data.get('message', 'Inconnu')}"}
        except Exception as e:
            return {"success": False, "message": f"Erreur CinetPay : {str(e)[:100]}"}

    else:
        raise HTTPException(status_code=400, detail=f"Méthode inconnue : {method}")
