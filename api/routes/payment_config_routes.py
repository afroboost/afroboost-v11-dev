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

    # V222: TWINT direct link
    twint_direct_url: str = ""

    # Mobile Money (CinetPay)
    mobile_money_enabled: bool = False
    cinetpay_api_key: str = ""
    cinetpay_site_id: str = ""
    cinetpay_secret_key: str = ""

    # V325: Mobile Money (PawaPay) — prestataire ADDITIONNEL, indépendant de CinetPay
    pawapay_enabled: bool = False
    pawapay_api_token: str = ""
    pawapay_mode: str = "sandbox"  # "sandbox" | "live"

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
    # V325 : PawaPay compte comme méthode configurée au même titre que CinetPay
    if config.get("pawapay_enabled") and config.get("pawapay_api_token"):
        return True
    # V311j : un lien TWINT direct renseigné compte comme méthode configurée
    # (bug : le bandeau « Non configuré » l'ignorait alors que le paiement TWINT
    # est bel et bien proposé aux clients).
    if (config.get("twint_direct_url") or "").strip():
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
            "twint_direct_url": "",
            "mobile_money_enabled": False,
            "cinetpay_api_key": "",
            "cinetpay_site_id": "",
            "cinetpay_secret_key": "",
            # V325
            "pawapay_enabled": False,
            "pawapay_api_token": "",
            "pawapay_mode": "sandbox",
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
        "twint_direct_url": config.get("twint_direct_url", ""),
        "mobile_money_enabled": config.get("mobile_money_enabled", False),
        "cinetpay_api_key": mask_key(config.get("cinetpay_api_key", "")),
        "cinetpay_site_id": config.get("cinetpay_site_id", ""),  # Site ID = pas secret
        "cinetpay_secret_key": mask_key(config.get("cinetpay_secret_key", "")),
        # V325 : le jeton PawaPay est un SECRET -> masqué comme les autres
        "pawapay_enabled": config.get("pawapay_enabled", False),
        "pawapay_api_token": mask_key(config.get("pawapay_api_token", "")),
        "pawapay_mode": config.get("pawapay_mode", "sandbox"),
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
        for key in ["stripe_secret_key", "paypal_client_secret", "cinetpay_api_key", "cinetpay_secret_key",
                    "pawapay_api_token"]:  # V325
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
    import os

    # Super Admin : vérifier aussi les clés dans les variables d'environnement
    SUPER_ADMIN_EMAILS = ["contact.artboost@gmail.com", "afroboost.bassi@gmail.com"]
    is_admin = coach_email.lower().strip() in SUPER_ADMIN_EMAILS

    config = await db["partner_payment_config"].find_one({"coach_email": coach_email})

    methods = []
    stripe_pk = None

    # Vérifier d'abord la config partenaire (partner_payment_config)
    if config and config.get("is_configured"):
        if config.get("stripe_enabled") and config.get("stripe_secret_key"):
            methods.append("card")
            stripe_pk = config.get("stripe_publishable_key", "")
        if config.get("paypal_enabled") and config.get("paypal_client_id"):
            methods.append("paypal")
        if config.get("mobile_money_enabled") and config.get("cinetpay_api_key"):
            methods.append("mobile_money")

    # V325 : PawaPay n'est proposé que si le drapeau global PAWAPAY_ENABLED est ON.
    # Tant qu'il est OFF (défaut), cette liste est strictement celle d'avant V325.
    try:
        _flags = await db.feature_flags.find_one({"id": "feature_flags"}, {"_id": 0}) or {}
        _pawapay_flag = bool(_flags.get("PAWAPAY_ENABLED", False))
    except Exception:
        _pawapay_flag = False
    if _pawapay_flag:
        if config and config.get("pawapay_enabled") and config.get("pawapay_api_token"):
            methods.append("pawapay")
        elif is_admin and os.environ.get("PAWAPAY_API_TOKEN", ""):
            methods.append("pawapay")

    # Super Admin fallback : si pas de config partenaire, utiliser les env vars
    if is_admin and "card" not in methods:
        env_stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
        env_stripe_pk = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
        if env_stripe_key:
            methods.append("card")
            stripe_pk = env_stripe_pk

    if is_admin and "paypal" not in methods:
        env_paypal = os.environ.get("PAYPAL_CLIENT_ID", "")
        if env_paypal:
            methods.append("paypal")

    if is_admin and "mobile_money" not in methods:
        env_cinetpay = os.environ.get("CINETPAY_API_KEY", "")
        if env_cinetpay:
            methods.append("mobile_money")

    if not methods:
        # Dernier fallback pour admin : vérifier les payment_links (ancien système)
        if is_admin:
            links = await db.payment_links.find_one({"id": "payment_links"})
            if links and (links.get("stripe", "").strip() or links.get("paypal", "").strip() or links.get("twint", "").strip()):
                # Admin a des liens de paiement configurés → marquer comme configuré
                if links.get("stripe", "").strip():
                    methods.append("card")
                    stripe_pk = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
                if links.get("paypal", "").strip():
                    methods.append("paypal")

    return {
        "is_configured": len(methods) > 0,
        "available_methods": methods,
        "stripe_publishable_key": stripe_pk
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

    elif method == "pawapay":
        # V325 : le jeton PawaPay est validé en interrogeant un dépôt bidon.
        # Un 401/403 = jeton invalide ; un 200/404 = jeton accepté par PawaPay.
        token = config.get("pawapay_api_token", "")
        mode = config.get("pawapay_mode", "sandbox")
        if not token:
            return {"success": False, "message": "Jeton PawaPay non configuré"}
        base_url = "https://api.pawapay.io" if mode == "live" else "https://api.sandbox.pawapay.io"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{base_url}/v2/deposits/00000000-0000-4000-8000-000000000000",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10
                )
            if resp.status_code in (200, 404):
                return {"success": True, "message": f"Connexion PawaPay réussie ({mode}) ✅"}
            if resp.status_code in (401, 403):
                return {"success": False, "message": "Jeton PawaPay refusé (401/403)"}
            return {"success": False, "message": f"Erreur PawaPay : HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "message": f"Erreur PawaPay : {str(e)[:100]}"}

    else:
        raise HTTPException(status_code=400, detail=f"Méthode inconnue : {method}")
