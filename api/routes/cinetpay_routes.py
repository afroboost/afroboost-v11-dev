"""
CinetPay Routes v1.0
Routes pour les paiements Mobile Money via CinetPay
Supporte: MTN Money, Orange Money, Moov Money, Airtel Money
Couverture: 10 pays francophones d'Afrique
"""
import os
import httpx
import logging
import uuid
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cinetpay", tags=["cinetpay"])

# Configuration CinetPay
CINETPAY_API_KEY = os.environ.get('CINETPAY_API_KEY', '')
CINETPAY_SITE_ID = os.environ.get('CINETPAY_SITE_ID', '')
CINETPAY_SECRET_KEY = os.environ.get('CINETPAY_SECRET_KEY', '')
CINETPAY_BASE_URL = "https://api-checkout.cinetpay.com/v2"

# Variable db sera injectée depuis server.py
db = None

def init_db(database):
    global db
    db = database
    logger.info("[CINETPAY_ROUTES] Base de données initialisée")


# === Pydantic Models ===

class CinetPayCheckoutRequest(BaseModel):
    """Requête pour créer un paiement CinetPay"""
    amount: int  # Montant en unité (pas de centimes pour Mobile Money)
    currency: str = "XOF"  # XOF (FCFA UEMOA), XAF (FCFA CEMAC), EUR
    description: str = "Paiement Afroboost"
    customer_name: str = ""
    customer_email: str = ""
    customer_phone: str = ""
    metadata: Optional[dict] = None
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class CinetPayCoachCheckoutRequest(BaseModel):
    """Requête pour inscription partenaire via Mobile Money"""
    pack_id: str
    customer_name: str = Field(..., alias="name")
    customer_email: str = Field(..., alias="email")
    customer_phone: str = Field(default="", alias="phone")
    currency: str = "XOF"
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None

    class Config:
        # Allow both naming conventions (snake_case and aliases)
        populate_by_name = True


class CinetPayCreditCheckoutRequest(BaseModel):
    """Requête pour achat de crédits via Mobile Money"""
    pack_id: str
    coach_email: str
    currency: str = "XOF"
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class RegisterFreePackRequest(BaseModel):
    """Requête pour inscription gratuite (0 CHF packs)"""
    email: str
    name: str
    phone: str = ""
    pack_id: str
    password: Optional[str] = None  # Optional: only create auth if provided


# === Helper Functions ===

def is_cinetpay_configured():
    """Vérifie que CinetPay est configuré"""
    return bool(CINETPAY_API_KEY and CINETPAY_SITE_ID)


def hash_password(password: str) -> str:
    """Hash password using PBKDF2 with SHA256 (same as auth_routes.py)"""
    salt = secrets.token_hex(16)
    hash_val = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f"{salt}:{hash_val.hex()}"


async def create_cinetpay_payment(
    amount: int,
    currency: str,
    transaction_id: str,
    description: str,
    customer_name: str = "",
    customer_email: str = "",
    customer_phone: str = "",
    notify_url: str = "",
    return_url: str = "",
    metadata: dict = None
):
    """
    Crée un paiement via l'API CinetPay.
    Doc: https://docs.cinetpay.com/api/1.0-fr/checkout/initialisation
    """
    payload = {
        "apikey": CINETPAY_API_KEY,
        "site_id": CINETPAY_SITE_ID,
        "transaction_id": transaction_id,
        "amount": amount,
        "currency": currency.upper(),
        "description": description,
        "customer_name": customer_name or "Client Afroboost",
        "customer_email": customer_email,
        "customer_phone_number": customer_phone,
        "customer_city": "",
        "customer_country": "CI",  # Par défaut Côte d'Ivoire
        "customer_state": "",
        "customer_zip_code": "",
        "notify_url": notify_url,
        "return_url": return_url,
        "channels": "ALL",  # Mobile Money + Carte
        "metadata": str(metadata) if metadata else "",
        "lang": "FR",
        "invoice_data": {
            "Afroboost": description
        }
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{CINETPAY_BASE_URL}/payment",
            json=payload
        )

        if response.status_code != 200:
            logger.error(f"CinetPay API error: {response.status_code} - {response.text}")
            raise HTTPException(status_code=502, detail="Erreur CinetPay: service indisponible")

        data = response.json()

        if data.get("code") != "201":
            logger.error(f"CinetPay payment init failed: {data}")
            raise HTTPException(
                status_code=400,
                detail=data.get("message", "Erreur d'initialisation du paiement")
            )

        return data.get("data", {})


async def verify_cinetpay_payment(transaction_id: str):
    """
    Vérifie le statut d'un paiement CinetPay.
    Doc: https://docs.cinetpay.com/api/1.0-fr/checkout/verification
    """
    payload = {
        "apikey": CINETPAY_API_KEY,
        "site_id": CINETPAY_SITE_ID,
        "transaction_id": transaction_id
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{CINETPAY_BASE_URL}/payment/check",
            json=payload
        )

        if response.status_code != 200:
            logger.error(f"CinetPay check error: {response.status_code}")
            return None

        data = response.json()
        return data.get("data", {})


# === Routes ===

@router.post("/create-checkout")
async def create_cinetpay_checkout(request: CinetPayCheckoutRequest):
    """
    Crée une session de paiement CinetPay (Mobile Money + Carte).
    """
    if not is_cinetpay_configured():
        raise HTTPException(
            status_code=503,
            detail="Le service de paiement CinetPay n'est pas actuellement disponible. Veuillez réessayer plus tard ou contacter l'administrateur."
        )

    transaction_id = f"AFR-{uuid.uuid4().hex[:12]}"
    frontend_url = os.environ.get('REACT_APP_FRONTEND_URL', 'https://afroboost.com')
    notify_url = os.environ.get('CINETPAY_NOTIFY_URL', f"{frontend_url}/api/cinetpay/webhook")
    return_url = request.success_url or f"{frontend_url}/?payment=success&provider=cinetpay&tid={transaction_id}"

    # Sauvegarder la transaction en attente
    await db.cinetpay_transactions.insert_one({
        "transaction_id": transaction_id,
        "amount": request.amount,
        "currency": request.currency,
        "description": request.description,
        "customer_name": request.customer_name,
        "customer_email": request.customer_email,
        "customer_phone": request.customer_phone,
        "metadata": request.metadata or {},
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    try:
        result = await create_cinetpay_payment(
            amount=request.amount,
            currency=request.currency,
            transaction_id=transaction_id,
            description=request.description,
            customer_name=request.customer_name,
            customer_email=request.customer_email,
            customer_phone=request.customer_phone,
            notify_url=notify_url,
            return_url=return_url,
            metadata=request.metadata
        )

        payment_url = result.get("payment_url", "")
        payment_token = result.get("payment_token", "")

        logger.info(f"CinetPay checkout created: {transaction_id} for {request.customer_email}")

        return {
            "success": True,
            "transaction_id": transaction_id,
            "payment_url": payment_url,
            "payment_token": payment_token
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CinetPay checkout error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create-coach-checkout")
async def create_cinetpay_coach_checkout(request: CinetPayCoachCheckoutRequest):
    """
    Crée un paiement CinetPay pour l'inscription partenaire.
    Équivalent du create-coach-checkout Stripe mais via Mobile Money.
    """
    if not is_cinetpay_configured():
        raise HTTPException(
            status_code=503,
            detail="Le service de paiement CinetPay n'est pas actuellement disponible. Veuillez réessayer plus tard ou contacter l'administrateur."
        )

    # Récupérer le pack
    pack = await db.coach_packs.find_one({"id": request.pack_id})
    if not pack:
        raise HTTPException(status_code=404, detail="Pack non trouvé")

    # Prix en FCFA (conversion depuis CHF si nécessaire)
    price_xof = pack.get("price_xof") or int(pack.get("price", 0) * 400)  # ~400 XOF par CHF
    if price_xof <= 0:
        raise HTTPException(status_code=400, detail="Prix invalide pour ce pack")

    transaction_id = f"COACH-{uuid.uuid4().hex[:12]}"
    frontend_url = os.environ.get('REACT_APP_FRONTEND_URL', 'https://afroboost.com')
    notify_url = os.environ.get('CINETPAY_NOTIFY_URL', f"{frontend_url}/api/cinetpay/webhook")
    return_url = request.success_url or f"{frontend_url}/?payment=success&provider=cinetpay&tid={transaction_id}#partner-dashboard"

    # Sauvegarder la transaction
    await db.cinetpay_transactions.insert_one({
        "transaction_id": transaction_id,
        "type": "coach_registration",
        "amount": price_xof,
        "currency": request.currency,
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
        result = await create_cinetpay_payment(
            amount=price_xof,
            currency=request.currency,
            transaction_id=transaction_id,
            description=f"Pack Partenaire Afroboost - {pack.get('name', '')}",
            customer_name=request.customer_name,
            customer_email=request.customer_email,
            customer_phone=request.customer_phone,
            notify_url=notify_url,
            return_url=return_url,
            metadata={
                "type": "coach_registration",
                "pack_id": request.pack_id,
                "credits": pack.get("credits", 0),
                "customer_email": request.customer_email
            }
        )

        logger.info(f"CinetPay coach checkout: {transaction_id} for {request.customer_email}")

        return {
            "success": True,
            "transaction_id": transaction_id,
            "payment_url": result.get("payment_url", ""),
            "payment_token": result.get("payment_token", "")
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CinetPay coach checkout error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create-credit-checkout")
async def create_cinetpay_credit_checkout(request: CinetPayCreditCheckoutRequest):
    """
    Crée un paiement CinetPay pour l'achat de crédits.
    """
    if not is_cinetpay_configured():
        raise HTTPException(
            status_code=503,
            detail="Le service de paiement CinetPay n'est pas actuellement disponible. Veuillez réessayer plus tard ou contacter l'administrateur."
        )

    pack = await db.coach_packs.find_one({"id": request.pack_id})
    if not pack:
        raise HTTPException(status_code=404, detail="Pack non trouvé")

    price_xof = pack.get("price_xof") or int(pack.get("price", 0) * 400)
    if price_xof <= 0:
        raise HTTPException(status_code=400, detail="Prix invalide")

    transaction_id = f"CRED-{uuid.uuid4().hex[:12]}"
    frontend_url = os.environ.get('REACT_APP_FRONTEND_URL', 'https://afroboost.com')
    notify_url = os.environ.get('CINETPAY_NOTIFY_URL', f"{frontend_url}/api/cinetpay/webhook")
    return_url = request.success_url or f"{frontend_url}/dashboard?tab=boutique&payment=success&provider=cinetpay"

    await db.cinetpay_transactions.insert_one({
        "transaction_id": transaction_id,
        "type": "credit_purchase",
        "amount": price_xof,
        "currency": request.currency,
        "pack_id": request.pack_id,
        "pack_name": pack.get("name", ""),
        "credits": pack.get("credits", 0),
        "coach_email": request.coach_email,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    try:
        result = await create_cinetpay_payment(
            amount=price_xof,
            currency=request.currency,
            transaction_id=transaction_id,
            description=f"Pack {pack.get('name', 'Crédits')} - {pack.get('credits', 0)} crédits",
            customer_email=request.coach_email,
            notify_url=notify_url,
            return_url=return_url,
            metadata={
                "type": "credit_purchase",
                "pack_id": request.pack_id,
                "credits": pack.get("credits", 0),
                "coach_email": request.coach_email
            }
        )

        return {
            "success": True,
            "transaction_id": transaction_id,
            "payment_url": result.get("payment_url", ""),
            "payment_token": result.get("payment_token", "")
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"CinetPay credit checkout error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/register-free")
async def register_free_pack(request: RegisterFreePackRequest, response: Response):
    """
    Enregistrement gratuit pour packs à 0 CHF.

    Crée:
    1. Un profil coach dans la collection 'coaches'
    2. Si password est fourni: créer des credentials auth dans 'users_auth' avec PBKDF2-SHA256 (100k iterations)
    3. Une session coach (localStorage-friendly)
    4. Envoie des notifications emails (admin + nouveau partenaire via Resend)

    Retourne: user info + session token
    """
    try:
        email = request.email.lower().strip()
        name = request.name.strip()
        phone = request.phone.strip()
        pack_id = request.pack_id.strip()
        password = request.password

        # === VALIDATION ===
        if not email or '@' not in email:
            raise HTTPException(status_code=400, detail="Email invalide")

        if not name or len(name) < 2:
            raise HTTPException(status_code=400, detail="Le nom doit contenir au moins 2 caractères")

        if password and len(password) < 6:
            raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins 6 caractères")

        # === VÉRIFIER LE PACK ===
        pack = await db.coach_packs.find_one({"id": pack_id})
        if not pack:
            raise HTTPException(status_code=404, detail="Pack non trouvé")

        # Vérifier que c'est un pack gratuit (0 CHF)
        pack_price = pack.get("price", 0)
        if pack_price > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Ce pack ne peut pas être enregistré gratuitement (prix: {pack_price} CHF)"
            )

        # === VÉRIFIER QUE L'EMAIL N'EXISTE PAS ===
        existing_coach = await db.coaches.find_one({"email": email})
        if existing_coach:
            raise HTTPException(status_code=409, detail="Cet email est déjà enregistré comme partenaire")

        existing_user = await db.users_auth.find_one({"email": email})
        if existing_user:
            raise HTTPException(status_code=409, detail="Cet email est déjà enregistré")

        # === CRÉER LE PROFIL COACH ===
        coach_id = str(uuid.uuid4())
        credits = pack.get("credits", 0)

        coach_profile = {
            "id": coach_id,
            "email": email,
            "name": name,
            "phone": phone,
            "bio": "",
            "photo_url": "",
            "role": "coach",
            "credits": credits,
            "pack_id": pack_id,
            "pack_name": pack.get("name", ""),
            "stripe_customer_id": None,
            "stripe_connect_id": None,
            "is_active": True,
            "payment_provider": "free",
            "payment_method": "free_registration",
            "platform_name": None,
            "logo_url": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "last_login": datetime.now(timezone.utc).isoformat()
        }

        await db.coaches.insert_one(coach_profile)
        logger.info(f"[CINETPAY_FREE] Coach créé: {email} avec pack {pack_id}")

        user_id = None
        session_token = None

        # === CRÉER AUTH SI MOT DE PASSE FOURNI ===
        if password:
            user_id = f"coach_{uuid.uuid4().hex[:12]}"
            hashed_password = hash_password(password)

            await db.users_auth.insert_one({
                "user_id": user_id,
                "email": email,
                "name": name,
                "password_hash": hashed_password,
                "auth_method": "email_password",
                "is_coach": True,
                "picture": "",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            })

            logger.info(f"[CINETPAY_FREE] Auth credentials créés pour: {email}")
        else:
            # Sans password, générer un user_id pour la session
            user_id = f"coach_{uuid.uuid4().hex[:12]}"

        # === CRÉER LA SESSION ===
        session_token = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        await db.coach_sessions.insert_one({
            "session_id": str(uuid.uuid4()),
            "user_id": user_id,
            "email": email,
            "name": name,
            "session_token": session_token,
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat()
        })

        # === DÉFINIR LE COOKIE ===
        response.set_cookie(
            key="coach_session_token",
            value=session_token,
            httponly=True,
            secure=True,
            samesite="none",
            max_age=7 * 24 * 60 * 60,
            path="/"
        )

        logger.info(f"[CINETPAY_FREE] Session créée pour: {email}")

        # === ENVOYER LES EMAILS ===
        try:
            import resend
            import asyncio

            resend_api_key = os.environ.get('RESEND_API_KEY', '')
            if resend_api_key:
                resend.api_key = resend_api_key

                # Email au Super Admin
                admin_email = "contact.artboost@gmail.com"
                await asyncio.to_thread(resend.Emails.send, {
                    "from": "Afroboost <notifications@afroboosteur.com>",
                    "to": [admin_email],
                    "subject": f"🎉 Nouveau Partenaire Gratuit ! {name} ({email})",
                    "html": f"""
                    <div style="font-family:Arial,sans-serif;max-width:500px;margin:auto;padding:20px;background:#1a1a2e;color:white;border-radius:12px;">
                        <h2 style="color:#D91CD2;">🎉 Nouveau Partenaire Afroboost (Inscription Gratuite)</h2>
                        <p><strong>Nom:</strong> {name}</p>
                        <p><strong>Email:</strong> {email}</p>
                        <p><strong>Téléphone:</strong> {phone or 'N/A'}</p>
                        <p><strong>Pack:</strong> {pack.get('name', 'N/A')}</p>
                        <p><strong>Crédits:</strong> {credits}</p>
                        <p><strong>Type d'inscription:</strong> Gratuit (0 CHF)</p>
                        <p style="color:#4ade80;font-weight:bold;margin-top:20px;">Inscription confirmée ✅</p>
                    </div>
                    """
                })

                # Email au nouveau partenaire
                await asyncio.to_thread(resend.Emails.send, {
                    "from": "Afroboost <notifications@afroboosteur.com>",
                    "to": [email],
                    "subject": "🎊 Bienvenue Partenaire Afroboost !",
                    "html": f"""
                    <div style="font-family:Arial,sans-serif;max-width:500px;margin:auto;padding:20px;background:#1a1a2e;color:white;border-radius:12px;">
                        <h2 style="color:#D91CD2;">Bienvenue {name} ! 🎊</h2>
                        <p>Votre inscription comme Partenaire Afroboost est confirmée.</p>
                        <p><strong>Pack:</strong> {pack.get('name', '')}</p>
                        <p><strong>Crédits disponibles:</strong> {credits}</p>
                        <p style="margin-top:20px;">
                            <a href="https://afroboost.com/#partner-dashboard"
                               style="display:inline-block;padding:12px 24px;background:linear-gradient(135deg,#D91CD2,#8b5cf6);color:white;text-decoration:none;border-radius:8px;font-weight:bold;">
                                Accéder à mon Dashboard →
                            </a>
                        </p>
                    </div>
                    """
                })

                logger.info(f"[CINETPAY_FREE] Emails envoyés pour: {email}")
        except Exception as email_err:
            logger.error(f"[CINETPAY_FREE] Erreur envoi email: {email_err}")
            # Continue même si l'email échoue

        return {
            "success": True,
            "user": {
                "user_id": user_id,
                "email": email,
                "name": name,
                "picture": "",
                "is_coach": True
            },
            "session_token": session_token,
            "message": "Inscription gratuite réussie",
            "redirect": "/#partner-dashboard"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CINETPAY_FREE] Registration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{transaction_id}")
async def get_cinetpay_status(transaction_id: str):
    """
    Vérifie le statut d'une transaction CinetPay.
    """
    if not is_cinetpay_configured():
        raise HTTPException(
            status_code=503,
            detail="Le service de paiement CinetPay n'est pas actuellement disponible."
        )

    # Vérifier en local d'abord
    local_tx = await db.cinetpay_transactions.find_one(
        {"transaction_id": transaction_id},
        {"_id": 0}
    )

    # Vérifier aussi via l'API CinetPay
    remote_status = await verify_cinetpay_payment(transaction_id)

    return {
        "transaction_id": transaction_id,
        "local_status": local_tx.get("status") if local_tx else "not_found",
        "remote_status": remote_status.get("status") if remote_status else "unknown",
        "amount": remote_status.get("amount") if remote_status else None,
        "currency": remote_status.get("currency") if remote_status else None,
        "payment_method": remote_status.get("payment_method") if remote_status else None
    }


@router.post("/webhook")
async def cinetpay_webhook(request: Request):
    """
    Webhook CinetPay - Notification de paiement.
    CinetPay envoie un POST avec cpm_trans_id quand le paiement est confirmé.

    Doc: https://docs.cinetpay.com/api/1.0-fr/checkout/notification
    """
    try:
        body = await request.json()
    except:
        body = {}

    # CinetPay envoie cpm_trans_id dans le body
    transaction_id = body.get("cpm_trans_id", "")

    if not transaction_id:
        # Essayer aussi les form data
        form = await request.form()
        transaction_id = form.get("cpm_trans_id", "")

    if not transaction_id:
        logger.warning("[CINETPAY_WEBHOOK] Pas de transaction_id reçu")
        return {"status": "error", "message": "Missing transaction_id"}

    logger.info(f"[CINETPAY_WEBHOOK] Notification reçue pour: {transaction_id}")

    # Vérifier le paiement via l'API
    payment_data = await verify_cinetpay_payment(transaction_id)

    if not payment_data:
        logger.error(f"[CINETPAY_WEBHOOK] Impossible de vérifier: {transaction_id}")
        return {"status": "error", "message": "Verification failed"}

    payment_status = payment_data.get("status", "")
    amount = payment_data.get("amount", 0)
    currency = payment_data.get("currency", "")
    payment_method = payment_data.get("payment_method", "")

    logger.info(f"[CINETPAY_WEBHOOK] Status: {payment_status}, Amount: {amount} {currency}, Method: {payment_method}")

    # Récupérer la transaction locale
    local_tx = await db.cinetpay_transactions.find_one({"transaction_id": transaction_id})

    if not local_tx:
        logger.error(f"[CINETPAY_WEBHOOK] Transaction inconnue: {transaction_id}")
        return {"status": "error", "message": "Transaction not found"}

    # Éviter le double traitement
    if local_tx.get("status") == "completed":
        logger.info(f"[CINETPAY_WEBHOOK] Déjà traitée: {transaction_id}")
        return {"status": "ok", "message": "Already processed"}

    # === PAIEMENT ACCEPTÉ ===
    if payment_status == "ACCEPTED":
        await db.cinetpay_transactions.update_one(
            {"transaction_id": transaction_id},
            {"$set": {
                "status": "completed",
                "payment_method": payment_method,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }}
        )

        tx_type = local_tx.get("type", "")

        # --- Inscription Partenaire ---
        if tx_type == "coach_registration":
            coach_email = local_tx.get("customer_email", "").lower()
            credits = local_tx.get("credits", 0)
            pack_id = local_tx.get("pack_id", "")
            customer_name = local_tx.get("customer_name", "")

            # Créer/Mettre à jour le profil coach
            existing_coach = await db.coaches.find_one({"email": coach_email})
            if existing_coach:
                await db.coaches.update_one(
                    {"email": coach_email},
                    {"$set": {
                        "credits": credits,
                        "pack_id": pack_id,
                        "is_active": True,
                        "payment_provider": "cinetpay",
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
            else:
                await db.coaches.insert_one({
                    "id": str(uuid.uuid4()),
                    "email": coach_email,
                    "name": customer_name,
                    "phone": local_tx.get("customer_phone", ""),
                    "credits": credits,
                    "pack_id": pack_id,
                    "is_active": True,
                    "payment_provider": "cinetpay",
                    "created_at": datetime.now(timezone.utc).isoformat()
                })

            logger.info(f"[CINETPAY_WEBHOOK] Coach créé/mis à jour: {coach_email} avec {credits} crédits")

            # === NOTIFICATION EMAIL : Super Admin + Partenaire ===
            try:
                import resend
                resend.api_key = os.environ.get('RESEND_API_KEY', '')
                import asyncio

                # Email au Super Admin
                await asyncio.to_thread(resend.Emails.send, {
                    "from": "Afroboost <notifications@afroboosteur.com>",
                    "to": ["contact.artboost@gmail.com"],
                    "subject": f"🎉 Nouveau Partenaire ! {customer_name} ({coach_email})",
                    "html": f"""
                    <div style="font-family:Arial,sans-serif;max-width:500px;margin:auto;padding:20px;background:#1a1a2e;color:white;border-radius:12px;">
                        <h2 style="color:#D91CD2;">🎉 Nouveau Partenaire Afroboost</h2>
                        <p><strong>Nom:</strong> {customer_name}</p>
                        <p><strong>Email:</strong> {coach_email}</p>
                        <p><strong>Pack:</strong> {local_tx.get('pack_name', 'N/A')}</p>
                        <p><strong>Crédits:</strong> {credits}</p>
                        <p><strong>Montant:</strong> {amount} {currency}</p>
                        <p><strong>Méthode:</strong> Mobile Money ({payment_method})</p>
                        <p><strong>Transaction:</strong> {transaction_id}</p>
                        <p style="color:#4ade80;font-weight:bold;margin-top:20px;">Paiement confirmé ✅</p>
                    </div>
                    """
                })

                # Email au nouveau partenaire
                await asyncio.to_thread(resend.Emails.send, {
                    "from": "Afroboost <notifications@afroboosteur.com>",
                    "to": [coach_email],
                    "subject": "🎊 Bienvenue Partenaire Afroboost !",
                    "html": f"""
                    <div style="font-family:Arial,sans-serif;max-width:500px;margin:auto;padding:20px;background:#1a1a2e;color:white;border-radius:12px;">
                        <h2 style="color:#D91CD2;">Bienvenue {customer_name} ! 🎊</h2>
                        <p>Votre inscription comme Partenaire Afroboost est confirmée.</p>
                        <p><strong>Pack:</strong> {local_tx.get('pack_name', '')}</p>
                        <p><strong>Crédits disponibles:</strong> {credits}</p>
                        <p style="margin-top:20px;">
                            <a href="https://afroboost.com/#partner-dashboard"
                               style="display:inline-block;padding:12px 24px;background:linear-gradient(135deg,#D91CD2,#8b5cf6);color:white;text-decoration:none;border-radius:8px;font-weight:bold;">
                                Accéder à mon Dashboard →
                            </a>
                        </p>
                    </div>
                    """
                })

                logger.info(f"[CINETPAY_WEBHOOK] Emails envoyés pour coach: {coach_email}")
            except Exception as email_err:
                logger.error(f"[CINETPAY_WEBHOOK] Erreur envoi email: {email_err}")

        # --- Achat de crédits ---
        elif tx_type == "credit_purchase":
            coach_email = local_tx.get("coach_email", "").lower()
            credits_to_add = local_tx.get("credits", 0)
            pack_name = local_tx.get("pack_name", "")

            if coach_email and credits_to_add > 0:
                await db.coaches.update_one(
                    {"email": coach_email},
                    {"$inc": {"credits": credits_to_add}}
                )

                await db.credit_transactions.insert_one({
                    "coach_email": coach_email,
                    "credits_added": credits_to_add,
                    "pack_name": pack_name,
                    "amount": amount,
                    "currency": currency,
                    "payment_provider": "cinetpay",
                    "transaction_id": transaction_id,
                    "payment_method": payment_method,
                    "date": datetime.now(timezone.utc)
                })

                logger.info(f"[CINETPAY_WEBHOOK] {credits_to_add} crédits ajoutés à {coach_email}")

        # --- Achat client (séances) ---
        else:
            customer_email = local_tx.get("customer_email", "").lower()
            if customer_email:
                # Générer un code d'accès
                access_code = f"AFR-{uuid.uuid4().hex[:6].upper()}"
                sessions_count = local_tx.get("metadata", {}).get("sessions", 10)

                await db.discount_codes.insert_one({
                    "code": access_code,
                    "type": "100%",
                    "maxUses": sessions_count,
                    "sessions": sessions_count,
                    "usedCount": 0,
                    "assignedTo": customer_email,
                    "assignedName": local_tx.get("customer_name", ""),
                    "source": "cinetpay",
                    "transaction_id": transaction_id,
                    "isActive": True,
                    "created_at": datetime.now(timezone.utc).isoformat()
                })

                # Envoyer email avec QR Code
                try:
                    import resend
                    import asyncio
                    resend.api_key = os.environ.get('RESEND_API_KEY', '')

                    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=https://afroboost.com/?qr={access_code}"

                    await asyncio.to_thread(resend.Emails.send, {
                        "from": "Afroboost <notifications@afroboosteur.com>",
                        "to": [customer_email],
                        "subject": f"Votre accès Afroboost - {access_code}",
                        "html": f"""
                        <div style="font-family:Arial,sans-serif;max-width:500px;margin:auto;padding:20px;background:#1a1a2e;color:white;border-radius:12px;">
                            <h2 style="color:#D91CD2;">Bienvenue chez Afroboost ! 🎉</h2>
                            <p>Merci pour votre achat ! Voici vos accès :</p>
                            <div style="background:rgba(139,92,246,0.2);padding:16px;border-radius:8px;text-align:center;margin:16px 0;">
                                <p style="font-size:12px;color:#c4b5fd;">Votre code d'identification</p>
                                <p style="font-size:28px;font-weight:bold;color:#D91CD2;letter-spacing:4px;">{access_code}</p>
                                <p style="font-size:12px;color:rgba(255,255,255,0.5);">Séances : {sessions_count}</p>
                            </div>
                            <div style="text-align:center;margin:16px 0;">
                                <p style="font-size:12px;color:#c4b5fd;">Votre QR Code (à présenter à l'entrée)</p>
                                <img src="{qr_url}" alt="QR Code" style="width:200px;height:200px;border-radius:8px;"/>
                            </div>
                            <p style="font-size:12px;color:rgba(255,255,255,0.5);margin-top:16px;">
                                Utilisez ce code pour vous connecter sur afroboost.com et suivre votre consommation de séances.
                            </p>
                        </div>
                        """
                    })

                    # Notifier le Super Admin
                    await asyncio.to_thread(resend.Emails.send, {
                        "from": "Afroboost <notifications@afroboosteur.com>",
                        "to": ["contact.artboost@gmail.com"],
                        "subject": f"💰 Nouvelle vente ! {local_tx.get('customer_name', '')} - {amount} {currency}",
                        "html": f"""
                        <div style="font-family:Arial,sans-serif;max-width:500px;margin:auto;padding:20px;background:#1a1a2e;color:white;border-radius:12px;">
                            <h2 style="color:#4ade80;">💰 Nouvelle Vente</h2>
                            <p><strong>Client:</strong> {local_tx.get('customer_name', 'N/A')}</p>
                            <p><strong>Email:</strong> {customer_email}</p>
                            <p><strong>Montant:</strong> {amount} {currency}</p>
                            <p><strong>Méthode:</strong> Mobile Money ({payment_method})</p>
                            <p><strong>Code accès:</strong> {access_code}</p>
                            <p><strong>Séances:</strong> {sessions_count}</p>
                        </div>
                        """
                    })
                except Exception as email_err:
                    logger.error(f"[CINETPAY_WEBHOOK] Erreur email client: {email_err}")

        return {"status": "ok", "message": "Payment processed"}

    # === PAIEMENT REFUSÉ ===
    elif payment_status in ("REFUSED", "CANCELLED"):
        await db.cinetpay_transactions.update_one(
            {"transaction_id": transaction_id},
            {"$set": {
                "status": "failed",
                "failure_reason": payment_status,
                "failed_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        logger.warning(f"[CINETPAY_WEBHOOK] Paiement {payment_status}: {transaction_id}")
        return {"status": "ok", "message": f"Payment {payment_status}"}

    # === EN ATTENTE ===
    else:
        logger.info(f"[CINETPAY_WEBHOOK] Paiement en attente ({payment_status}): {transaction_id}")
        return {"status": "ok", "message": f"Status: {payment_status}"}
