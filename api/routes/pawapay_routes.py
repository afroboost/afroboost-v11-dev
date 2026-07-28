"""
PawaPay Routes v1.0 (V325)
Routes pour les paiements Mobile Money via PawaPay (agrégateur panafricain).
Couverture : M-Pesa, MTN MoMo, Orange Money, Airtel Money, Vodafone… ~20 pays.

Calqué sur `cinetpay_routes.py` (mêmes endpoints, mêmes rôles, même activation),
adapté à l'API PawaPay v2 « Payment Page » :
  - POST {base}/v2/paymentpage        -> renvoie { redirectUrl }
  - GET  {base}/v2/deposits/{id}      -> statut final du dépôt
Doc : https://docs.pawapay.io/v2/docs/payment_page

DRAPEAU : tout est derrière `PAWAPAY_ENABLED` (collection `feature_flags`), OFF par
défaut, relu à CHAQUE requête (kill-switch sans redéploiement). Quand il est OFF,
tous les endpoints renvoient 404 — sauf `/available`, qui répond `{"enabled": false}`
pour que le frontend sache simplement ne pas afficher l'option.

SÉCURITÉ : aucun jeton n'est écrit dans ce fichier. Le jeton est lu d'abord dans
`partner_payment_config` (tableau de bord admin), sinon dans l'environnement.
"""
import os
import re
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from api.routes.shared import SUPER_ADMIN_EMAILS
from api.routes.payment_activation import activate_after_payment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pawapay", tags=["pawapay"])

# Bases PawaPay — bac à sable par défaut (on ne bascule en production qu'explicitement)
PAWAPAY_SANDBOX_URL = "https://api.sandbox.pawapay.io"
PAWAPAY_PROD_URL = "https://api.pawapay.io"

# Variable db injectée depuis server.py
db = None


def init_db(database):
    global db
    db = database
    logger.info("[PAWAPAY_ROUTES] Base de données initialisée")


# === Pydantic Models (miroir de CinetPay) ===

class PawaPayCheckoutRequest(BaseModel):
    """Requête pour créer un paiement PawaPay"""
    amount: int  # Montant en unité MAJEURE (pas de centimes pour Mobile Money)
    currency: str = "XOF"
    description: str = "Paiement Afroboost"
    customer_name: str = ""
    customer_email: str = ""
    customer_phone: str = ""
    country: str = "CIV"  # ISO 3166-1 alpha-3 (PawaPay), défaut Côte d'Ivoire
    metadata: Optional[dict] = None
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class PawaPayCoachCheckoutRequest(BaseModel):
    """Requête pour inscription partenaire via PawaPay"""
    pack_id: str
    customer_name: str = Field(..., alias="name")
    customer_email: str = Field(..., alias="email")
    customer_phone: str = Field(default="", alias="phone")
    currency: str = "XOF"
    country: str = "CIV"
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None

    class Config:
        # Accepte les deux conventions de nommage (snake_case et alias)
        populate_by_name = True


class PawaPayCreditCheckoutRequest(BaseModel):
    """Requête pour achat de crédits via PawaPay"""
    pack_id: str
    coach_email: str
    currency: str = "XOF"
    country: str = "CIV"
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


# === Helper Functions ===

# PawaPay attend un code pays ISO 3166-1 **alpha-3**. Les autres parties du site
# manipulent parfois de l'alpha-2 (CinetPay envoie "CI") : on convertit plutôt que
# de laisser passer un code que PawaPay refusera.
_ALPHA2_TO_ALPHA3 = {
    "CI": "CIV", "SN": "SEN", "CM": "CMR", "BF": "BFA", "ML": "MLI", "BJ": "BEN",
    "TG": "TGO", "NE": "NER", "GN": "GIN", "CD": "COD", "CG": "COG", "GA": "GAB",
    "KE": "KEN", "TZ": "TZA", "UG": "UGA", "RW": "RWA", "ZM": "ZMB", "MW": "MWI",
    "GH": "GHA", "NG": "NGA", "MZ": "MOZ", "ZW": "ZWE", "SL": "SLE", "BW": "BWA",
}


def normalize_country(country: str) -> str:
    """Renvoie un code pays alpha-3 majuscule (défaut CIV)."""
    c = (country or "").strip().upper()
    if len(c) == 2:
        return _ALPHA2_TO_ALPHA3.get(c, "CIV")
    if len(c) == 3:
        return c
    return "CIV"


def normalize_msisdn(phone: str) -> str:
    """Numéro au format PawaPay : chiffres uniquement, sans '+' ni séparateurs."""
    return re.sub(r"\D", "", phone or "")


async def is_pawapay_flag_on() -> bool:
    """État EN DIRECT du drapeau PAWAPAY_ENABLED (relu à chaque requête)."""
    if db is None:
        return False
    try:
        flags = await db.feature_flags.find_one({"id": "feature_flags"}, {"_id": 0}) or {}
        return bool(flags.get("PAWAPAY_ENABLED", False))
    except Exception as e:
        # Un hoquet de la base ne doit JAMAIS activer un prestataire de paiement.
        logger.error(f"[PAWAPAY] Lecture du drapeau impossible: {e}")
        return False


async def get_pawapay_config():
    """
    Renvoie (token, base_url).
    Ordre de résolution identique à Stripe/CinetPay : `partner_payment_config`
    (tableau de bord admin) d'abord, variables d'environnement ensuite.
    Le parcours des admins est ORDONNÉ (déterministe), comme en V221.
    """
    token = ""
    base_url = ""

    if db is not None:
        for admin_email in SUPER_ADMIN_EMAILS:
            try:
                cfg = await db["partner_payment_config"].find_one({"coach_email": admin_email})
            except Exception:
                cfg = None
            if cfg and cfg.get("pawapay_enabled") and cfg.get("pawapay_api_token"):
                token = cfg["pawapay_api_token"]
                base_url = PAWAPAY_PROD_URL if cfg.get("pawapay_mode") == "live" else PAWAPAY_SANDBOX_URL
                logger.info(f"[PAWAPAY] Jeton lu depuis le tableau de bord ({admin_email})")
                break

    if not token:
        token = os.environ.get("PAWAPAY_API_TOKEN", "")
        base_url = (os.environ.get("PAWAPAY_BASE_URL", "") or PAWAPAY_SANDBOX_URL).rstrip("/")
        if token:
            logger.info("[PAWAPAY] Jeton lu depuis l'environnement PAWAPAY_API_TOKEN")

    return token, (base_url or PAWAPAY_SANDBOX_URL)


async def is_pawapay_configured() -> bool:
    """Configuré = drapeau ON **ET** jeton disponible."""
    if not await is_pawapay_flag_on():
        return False
    token, _ = await get_pawapay_config()
    return bool(token)


async def require_pawapay():
    """
    Garde commune à tous les endpoints métier.
    - Drapeau OFF  -> 404 (l'intégration n'existe pas pour l'extérieur)
    - Drapeau ON mais pas de jeton -> 503 (message identique à CinetPay)
    Renvoie (token, base_url).
    """
    if not await is_pawapay_flag_on():
        raise HTTPException(status_code=404, detail="Not Found")
    token, base_url = await get_pawapay_config()
    if not token:
        raise HTTPException(
            status_code=503,
            detail="Le service de paiement PawaPay n'est pas actuellement disponible. Veuillez réessayer plus tard ou contacter l'administrateur."
        )
    return token, base_url


def frontend_url() -> str:
    return os.environ.get('REACT_APP_FRONTEND_URL', 'https://afroboost.com')


def callback_url() -> str:
    """URL à déclarer côté tableau de bord PawaPay pour recevoir les callbacks."""
    return os.environ.get('PAWAPAY_CALLBACK_URL', f"{frontend_url()}/api/pawapay/webhook")


async def create_pawapay_deposit(
    token: str,
    base_url: str,
    deposit_id: str,
    amount: int,
    country: str,
    reason: str,
    return_url: str,
    msisdn: str = ""
) -> str:
    """
    Ouvre une session « Payment Page » PawaPay et renvoie l'URL de redirection.
    Doc : https://docs.pawapay.io/v2/docs/payment_page

    Le `depositId` est fourni par NOUS et doit être stocké AVANT cet appel : si le
    réseau lâche après l'envoi, c'est la seule référence permettant de retrouver le
    dépôt côté PawaPay.
    """
    payload = {
        "depositId": deposit_id,
        "returnUrl": return_url,
    }
    if reason:
        # Ce texte est affiché au client sur la page PawaPay — on le garde court.
        payload["reason"] = reason[:60]
    if amount and country:
        # Montant en unité MAJEURE, transmis en chaîne (format attendu par PawaPay).
        payload["amount"] = str(int(amount))
        payload["country"] = country
    if msisdn:
        payload["msisdn"] = msisdn

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{base_url}/v2/paymentpage",
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        )

    if response.status_code not in (200, 201):
        logger.error(f"[PAWAPAY] API error: {response.status_code} - {response.text[:300]}")
        raise HTTPException(status_code=502, detail="Erreur PawaPay: service indisponible")

    try:
        data = response.json()
    except Exception:
        logger.error(f"[PAWAPAY] Réponse non-JSON: {response.text[:300]}")
        raise HTTPException(status_code=502, detail="Erreur PawaPay: réponse invalide")

    redirect_url = data.get("redirectUrl") or ""
    if not redirect_url:
        logger.error(f"[PAWAPAY] Pas de redirectUrl dans la réponse: {str(data)[:300]}")
        raise HTTPException(status_code=400, detail="PawaPay n'a pas renvoyé d'URL de paiement")

    return redirect_url


async def verify_pawapay_deposit(token: str, base_url: str, deposit_id: str):
    """
    Vérifie le statut d'un dépôt PawaPay (source de vérité).
    GET {base}/v2/deposits/{depositId}
    Renvoie le dict `data` du dépôt, ou None si introuvable/erreur.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{base_url}/v2/deposits/{deposit_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
    except Exception as e:
        logger.error(f"[PAWAPAY] Erreur réseau lors de la vérification {deposit_id}: {e}")
        return None

    if response.status_code != 200:
        logger.error(f"[PAWAPAY] Check error: {response.status_code} - {response.text[:200]}")
        return None

    try:
        data = response.json()
    except Exception:
        return None

    # v2 : { "status": "FOUND", "data": {...} }
    if isinstance(data, dict):
        if data.get("status") == "NOT_FOUND":
            return None
        inner = data.get("data")
        if isinstance(inner, dict):
            return inner
        # Certaines réponses renvoient directement l'objet dépôt
        if data.get("depositId"):
            return data
    # Repli historique : liste d'un seul élément
    if isinstance(data, list) and data:
        return data[0]
    return None


def deposit_payment_method(deposit: dict) -> str:
    """Libellé lisible de l'opérateur mobile money ayant servi le paiement."""
    try:
        return (deposit.get("payer", {}) or {}).get("accountDetails", {}).get("provider", "") or "MOBILE_MONEY"
    except Exception:
        return "MOBILE_MONEY"


# === Routes ===

@router.get("/available")
async def pawapay_available():
    """
    Seul endpoint joignable quand le drapeau est OFF : il dit au frontend s'il doit
    afficher l'option « Mobile Money (PawaPay) ». Ne divulgue aucune clé.
    """
    enabled = await is_pawapay_configured()
    return {
        "enabled": enabled,
        "flag": await is_pawapay_flag_on(),
        "callback_url": callback_url(),  # à recopier dans le tableau de bord PawaPay
    }


@router.post("/create-checkout")
async def create_pawapay_checkout(request: PawaPayCheckoutRequest):
    """
    Crée une session de paiement PawaPay (Mobile Money, page hébergée).
    """
    token, base_url = await require_pawapay()

    deposit_id = str(uuid.uuid4())
    country = normalize_country(request.country)
    return_url = request.success_url or f"{frontend_url()}/?payment=success&provider=pawapay&tid={deposit_id}"

    # Sauvegarder la transaction en attente AVANT l'appel réseau (recommandation PawaPay)
    await db.pawapay_transactions.insert_one({
        "depositId": deposit_id,
        "amount": request.amount,
        "currency": request.currency,
        "country": country,
        "description": request.description,
        "customer_name": request.customer_name,
        "customer_email": request.customer_email,
        "customer_phone": request.customer_phone,
        "metadata": request.metadata or {},
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    try:
        payment_url = await create_pawapay_deposit(
            token=token,
            base_url=base_url,
            deposit_id=deposit_id,
            amount=request.amount,
            country=country,
            reason=request.description,
            return_url=return_url,
            msisdn=normalize_msisdn(request.customer_phone)
        )

        logger.info(f"[PAWAPAY] Checkout créé: {deposit_id} pour {request.customer_email}")

        return {
            "success": True,
            "transaction_id": deposit_id,
            "deposit_id": deposit_id,
            "payment_url": payment_url
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PAWAPAY] Checkout error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create-coach-checkout")
async def create_pawapay_coach_checkout(request: PawaPayCoachCheckoutRequest):
    """
    Crée un paiement PawaPay pour l'inscription partenaire.
    Équivalent du create-coach-checkout CinetPay, via un autre agrégateur.
    """
    token, base_url = await require_pawapay()

    # Récupérer le pack
    pack = await db.coach_packs.find_one({"id": request.pack_id})
    if not pack:
        raise HTTPException(status_code=404, detail="Pack non trouvé")

    # Prix en unité majeure (conversion depuis CHF si nécessaire) — même règle que CinetPay
    price_major = pack.get("price_xof") or int(pack.get("price", 0) * 400)  # ~400 XOF par CHF
    if price_major <= 0:
        raise HTTPException(status_code=400, detail="Prix invalide pour ce pack")

    deposit_id = str(uuid.uuid4())
    country = normalize_country(request.country)
    return_url = request.success_url or f"{frontend_url()}/?payment=success&provider=pawapay&tid={deposit_id}#partner-dashboard"

    await db.pawapay_transactions.insert_one({
        "depositId": deposit_id,
        "type": "coach_registration",
        "amount": price_major,
        "currency": request.currency,
        "country": country,
        "pack_id": request.pack_id,
        "pack_name": pack.get("name", ""),
        "credits": pack.get("credits", 0),
        "customer_name": request.customer_name,
        "customer_email": request.customer_email,
        "customer_phone": request.customer_phone,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    try:
        payment_url = await create_pawapay_deposit(
            token=token,
            base_url=base_url,
            deposit_id=deposit_id,
            amount=price_major,
            country=country,
            reason=f"Pack Partenaire - {pack.get('name', '')}",
            return_url=return_url,
            msisdn=normalize_msisdn(request.customer_phone)
        )

        logger.info(f"[PAWAPAY] Coach checkout: {deposit_id} pour {request.customer_email}")

        return {
            "success": True,
            "transaction_id": deposit_id,
            "deposit_id": deposit_id,
            "payment_url": payment_url
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PAWAPAY] Coach checkout error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create-credit-checkout")
async def create_pawapay_credit_checkout(request: PawaPayCreditCheckoutRequest):
    """
    Crée un paiement PawaPay pour l'achat de crédits.
    """
    token, base_url = await require_pawapay()

    pack = await db.coach_packs.find_one({"id": request.pack_id})
    if not pack:
        raise HTTPException(status_code=404, detail="Pack non trouvé")

    price_major = pack.get("price_xof") or int(pack.get("price", 0) * 400)
    if price_major <= 0:
        raise HTTPException(status_code=400, detail="Prix invalide")

    deposit_id = str(uuid.uuid4())
    country = normalize_country(request.country)
    return_url = request.success_url or f"{frontend_url()}/dashboard?tab=boutique&payment=success&provider=pawapay"

    await db.pawapay_transactions.insert_one({
        "depositId": deposit_id,
        "type": "credit_purchase",
        "amount": price_major,
        "currency": request.currency,
        "country": country,
        "pack_id": request.pack_id,
        "pack_name": pack.get("name", ""),
        "credits": pack.get("credits", 0),
        "coach_email": request.coach_email,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    try:
        payment_url = await create_pawapay_deposit(
            token=token,
            base_url=base_url,
            deposit_id=deposit_id,
            amount=price_major,
            country=country,
            reason=f"Pack {pack.get('name', 'Credits')}",
            return_url=return_url
        )

        return {
            "success": True,
            "transaction_id": deposit_id,
            "deposit_id": deposit_id,
            "payment_url": payment_url
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PAWAPAY] Credit checkout error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{deposit_id}")
async def get_pawapay_status(deposit_id: str):
    """
    Vérifie le statut d'une transaction PawaPay (local + API PawaPay).
    """
    token, base_url = await require_pawapay()

    local_tx = await db.pawapay_transactions.find_one(
        {"depositId": deposit_id},
        {"_id": 0}
    )

    remote = await verify_pawapay_deposit(token, base_url, deposit_id)

    return {
        "transaction_id": deposit_id,
        "deposit_id": deposit_id,
        "local_status": local_tx.get("status") if local_tx else "not_found",
        "remote_status": remote.get("status") if remote else "unknown",
        "amount": remote.get("amount") if remote else None,
        "currency": remote.get("currency") if remote else None,
        "payment_method": deposit_payment_method(remote) if remote else None
    }


@router.post("/webhook")
async def pawapay_webhook(request: Request):
    """
    Webhook PawaPay — callback de statut final d'un dépôt.

    Le corps du callback n'est JAMAIS cru sur parole : on n'en extrait que le
    `depositId`, puis on RE-INTERROGE l'API PawaPay pour connaître le statut réel
    (même prudence que `verify_cinetpay_payment`).

    Doc : https://docs.pawapay.io/v2/docs/payment_page
    """
    token, base_url = await require_pawapay()

    try:
        body = await request.json()
    except Exception:
        body = {}

    if not isinstance(body, dict):
        body = {}

    # Le callback porte le depositId à la racine ; on tolère aussi la forme imbriquée.
    deposit_id = body.get("depositId") or (body.get("data") or {}).get("depositId") or ""

    if not deposit_id:
        logger.warning("[PAWAPAY_WEBHOOK] Pas de depositId reçu")
        return {"status": "error", "message": "Missing depositId"}

    logger.info(f"[PAWAPAY_WEBHOOK] Notification reçue pour: {deposit_id}")

    # === RE-VÉRIFICATION AUPRÈS DE PAWAPAY (source de vérité) ===
    deposit = await verify_pawapay_deposit(token, base_url, deposit_id)

    if not deposit:
        logger.error(f"[PAWAPAY_WEBHOOK] Impossible de vérifier: {deposit_id}")
        return {"status": "error", "message": "Verification failed"}

    payment_status = deposit.get("status", "")
    amount = deposit.get("amount", 0)
    currency = deposit.get("currency", "")
    payment_method = deposit_payment_method(deposit)

    logger.info(f"[PAWAPAY_WEBHOOK] Status: {payment_status}, Amount: {amount} {currency}, Method: {payment_method}")

    local_tx = await db.pawapay_transactions.find_one({"depositId": deposit_id})

    if not local_tx:
        logger.error(f"[PAWAPAY_WEBHOOK] Transaction inconnue: {deposit_id}")
        return {"status": "error", "message": "Transaction not found"}

    # Garde anti-double traitement
    if local_tx.get("status") == "completed":
        logger.info(f"[PAWAPAY_WEBHOOK] Déjà traitée: {deposit_id}")
        return {"status": "ok", "message": "Already processed"}

    # === PAIEMENT ABOUTI ===
    if payment_status == "COMPLETED":
        await db.pawapay_transactions.update_one(
            {"depositId": deposit_id},
            {"$set": {
                "status": "completed",
                "payment_method": payment_method,
                "provider_transaction_id": deposit.get("providerTransactionId", ""),
                "completed_at": datetime.now(timezone.utc).isoformat()
            }}
        )

        # Activation métier — bloc PARTAGÉ, identique à celui de CinetPay
        await activate_after_payment(
            db,
            local_tx,
            provider="pawapay",
            amount=amount,
            currency=currency,
            payment_method=payment_method,
            transaction_ref=deposit_id,
            log_prefix="PAWAPAY_WEBHOOK",
        )

        return {"status": "ok", "message": "Payment processed"}

    # === PAIEMENT ÉCHOUÉ ===
    elif payment_status == "FAILED":
        failure = deposit.get("failureReason") or {}
        await db.pawapay_transactions.update_one(
            {"depositId": deposit_id},
            {"$set": {
                "status": "failed",
                "failure_reason": failure.get("failureCode") or payment_status,
                "failure_message": failure.get("failureMessage", ""),
                "failed_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        logger.warning(f"[PAWAPAY_WEBHOOK] Paiement FAILED: {deposit_id} ({failure.get('failureCode', '')})")
        return {"status": "ok", "message": "Payment FAILED"}

    # === EN COURS (ACCEPTED / PROCESSING / IN_RECONCILIATION) ===
    else:
        logger.info(f"[PAWAPAY_WEBHOOK] Paiement en attente ({payment_status}): {deposit_id}")
        return {"status": "ok", "message": f"Status: {payment_status}"}
