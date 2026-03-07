# v15.0: Unified Checkout Routes - Multi-Vendor Payment Routing
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone
import os
import uuid
import logging
import httpx
import json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/checkout", tags=["checkout"])
db = None

SUPER_ADMIN_EMAILS = ["contact.artboost@gmail.com", "afroboost.bassi@gmail.com"]
FRONTEND_URL = os.environ.get("REACT_APP_FRONTEND_URL", "https://afroboost-v11-dev-pm7l.vercel.app")

def init_db(database):
    global db
    db = database


# ===== MODELS =====

class CheckoutItem(BaseModel):
    type: str = "course"  # "course" | "offer" | "product"
    id: Optional[str] = None
    name: str
    price: float
    currency: str = "CHF"
    quantity: int = 1

class CreateCheckoutRequest(BaseModel):
    coach_email: str  # Vendeur (qui reçoit l'argent)
    payment_method: str  # "card" | "paypal" | "mobile_money"
    items: List[CheckoutItem]
    customer_name: str
    customer_email: str
    customer_phone: str = ""
    discount_code: Optional[str] = None
    discount_amount: Optional[float] = None  # Montant de réduction appliqué
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None

    class Config:
        populate_by_name = True


# ===== HELPERS =====

def is_super_admin(email: str) -> bool:
    return email.lower() in [e.lower() for e in SUPER_ADMIN_EMAILS]


async def get_payment_keys(coach_email: str, method: str):
    """Récupère les clés API pour le vendeur.
    Admin → env vars, Partenaire → collection partner_payment_config"""

    if is_super_admin(coach_email):
        # Admin : utiliser les clés de l'environnement
        if method == "card":
            sk = os.environ.get("STRIPE_SECRET_KEY", "")
            if not sk:
                return None, "Stripe non configuré côté admin"
            return {"stripe_secret_key": sk}, None

        elif method == "paypal":
            cid = os.environ.get("PAYPAL_CLIENT_ID", "")
            cs = os.environ.get("PAYPAL_CLIENT_SECRET", "")
            mode = os.environ.get("PAYPAL_MODE", "sandbox")
            if not cid or not cs:
                return None, "PayPal non configuré côté admin"
            return {"paypal_client_id": cid, "paypal_client_secret": cs, "paypal_mode": mode}, None

        elif method == "mobile_money":
            ak = os.environ.get("CINETPAY_API_KEY", "")
            sid = os.environ.get("CINETPAY_SITE_ID", "")
            sk = os.environ.get("CINETPAY_SECRET_KEY", "")
            if not ak or not sid:
                return None, "CinetPay non configuré côté admin"
            return {"cinetpay_api_key": ak, "cinetpay_site_id": sid, "cinetpay_secret_key": sk}, None

    else:
        # Partenaire : charger depuis la base
        config = await db["partner_payment_config"].find_one({"coach_email": coach_email})
        if not config:
            return None, "Paiements non configurés. Le partenaire doit configurer ses méthodes de paiement."

        if method == "card":
            if not config.get("stripe_enabled") or not config.get("stripe_secret_key"):
                return None, "Paiement par carte non configuré par ce partenaire"
            return {"stripe_secret_key": config["stripe_secret_key"]}, None

        elif method == "paypal":
            if not config.get("paypal_enabled") or not config.get("paypal_client_id"):
                return None, "PayPal non configuré par ce partenaire"
            return {
                "paypal_client_id": config["paypal_client_id"],
                "paypal_client_secret": config["paypal_client_secret"],
                "paypal_mode": config.get("paypal_mode", "sandbox")
            }, None

        elif method == "mobile_money":
            if not config.get("mobile_money_enabled") or not config.get("cinetpay_api_key"):
                return None, "Mobile Money non configuré par ce partenaire"
            return {
                "cinetpay_api_key": config["cinetpay_api_key"],
                "cinetpay_site_id": config["cinetpay_site_id"],
                "cinetpay_secret_key": config.get("cinetpay_secret_key", "")
            }, None

    return None, f"Méthode de paiement inconnue : {method}"


def calculate_total(items: List[CheckoutItem], discount_amount: float = None) -> float:
    """Calcule le total de la commande"""
    total = sum(item.price * item.quantity for item in items)
    if discount_amount and discount_amount > 0:
        total = max(0, total - discount_amount)
    return round(total, 2)


# ===== CHECKOUT ENDPOINT =====

@router.post("/create-session")
async def create_checkout_session(req: CreateCheckoutRequest):
    """Crée une session de paiement routée vers le bon vendeur"""

    total = calculate_total(req.items, req.discount_amount)

    if total <= 0:
        # Gratuit : pas de paiement, créer directement la réservation
        transaction_id = f"free_{uuid.uuid4().hex[:12]}"
        await _process_successful_payment(
            transaction_id=transaction_id,
            coach_email=req.coach_email,
            customer_name=req.customer_name,
            customer_email=req.customer_email,
            customer_phone=req.customer_phone,
            items=req.items,
            total=0,
            currency="CHF",
            payment_method="free",
            discount_code=req.discount_code
        )
        return {
            "success": True,
            "free": True,
            "transaction_id": transaction_id,
            "message": "Réservation confirmée gratuitement !"
        }

    # Récupérer les clés du vendeur
    keys, error = await get_payment_keys(req.coach_email, req.payment_method)
    if error:
        raise HTTPException(status_code=400, detail=error)

    transaction_id = f"txn_{uuid.uuid4().hex[:12]}"
    items_desc = ", ".join([f"{item.name} x{item.quantity}" for item in req.items])

    success_url = req.success_url or f"{FRONTEND_URL}/?payment=success&txn={transaction_id}"
    cancel_url = req.cancel_url or f"{FRONTEND_URL}/?payment=cancelled"

    # ===== STRIPE (Carte + TWINT) =====
    if req.payment_method == "card":
        try:
            import stripe
            stripe.api_key = keys["stripe_secret_key"]

            line_items = []
            for item in req.items:
                amount = int(item.price * 100)  # Stripe utilise les centimes
                if req.discount_amount and len(req.items) == 1:
                    amount = int(max(0, (item.price - (req.discount_amount or 0))) * 100)
                line_items.append({
                    "price_data": {
                        "currency": item.currency.lower(),
                        "product_data": {"name": item.name},
                        "unit_amount": amount
                    },
                    "quantity": item.quantity
                })

            # Déterminer les méthodes de paiement (TWINT si CHF)
            currency = req.items[0].currency.upper() if req.items else "CHF"
            payment_methods = ["card"]
            if currency == "CHF":
                payment_methods.append("twint")

            # Essayer avec TWINT d'abord, fallback card-only si TWINT non activé
            session = None
            methods_to_try = [payment_methods, ["card"]] if len(payment_methods) > 1 else [payment_methods]
            for methods in methods_to_try:
                try:
                    session = stripe.checkout.Session.create(
                        payment_method_types=methods,
                        line_items=line_items,
                        mode="payment",
                        success_url=success_url,
                        cancel_url=cancel_url,
                        customer_email=req.customer_email,
                        metadata={
                            "transaction_id": transaction_id,
                            "coach_email": req.coach_email,
                            "customer_name": req.customer_name,
                            "customer_phone": req.customer_phone,
                            "items": json.dumps([i.dict() for i in req.items]),
                            "discount_code": req.discount_code or "",
                            "type": "vitrine_purchase"
                        }
                    )
                    break  # Succès, sortir de la boucle
                except Exception as twint_err:
                    logger.warning(f"[CHECKOUT] Stripe methods {methods} failed: {twint_err}, trying next...")
                    continue

            if not session:
                raise Exception("Impossible de créer la session Stripe avec les méthodes disponibles")

            # Enregistrer la transaction
            await db["checkout_transactions"].insert_one({
                "transaction_id": transaction_id,
                "stripe_session_id": session.id,
                "coach_email": req.coach_email,
                "customer_email": req.customer_email,
                "customer_name": req.customer_name,
                "customer_phone": req.customer_phone,
                "items": [i.dict() for i in req.items],
                "total": total,
                "currency": currency,
                "payment_method": "card",
                "status": "pending",
                "discount_code": req.discount_code,
                "created_at": datetime.now(timezone.utc).isoformat()
            })

            logger.info(f"[CHECKOUT] Stripe session créée: {session.id} pour {req.coach_email} ({total} {currency})")

            return {
                "success": True,
                "payment_url": session.url,
                "transaction_id": transaction_id,
                "session_id": session.id,
                "method": "card",
                "recipient": req.coach_email
            }

        except Exception as e:
            logger.error(f"[CHECKOUT] Erreur Stripe: {e}")
            raise HTTPException(status_code=500, detail=f"Erreur lors de la création du paiement Stripe: {str(e)[:200]}")

    # ===== PAYPAL =====
    elif req.payment_method == "paypal":
        try:
            base_url = "https://api-m.sandbox.paypal.com" if keys["paypal_mode"] == "sandbox" else "https://api-m.paypal.com"

            # Obtenir un token d'accès
            async with httpx.AsyncClient() as client:
                token_resp = await client.post(
                    f"{base_url}/v1/oauth2/token",
                    data={"grant_type": "client_credentials"},
                    auth=(keys["paypal_client_id"], keys["paypal_client_secret"]),
                    timeout=15
                )

            if token_resp.status_code != 200:
                raise HTTPException(status_code=503, detail="Impossible de se connecter à PayPal")

            access_token = token_resp.json()["access_token"]

            # Créer la commande PayPal
            currency = req.items[0].currency.upper() if req.items else "CHF"

            order_data = {
                "intent": "CAPTURE",
                "purchase_units": [{
                    "reference_id": transaction_id,
                    "description": items_desc[:127],
                    "amount": {
                        "currency_code": currency,
                        "value": f"{total:.2f}"
                    },
                    "custom_id": json.dumps({
                        "coach_email": req.coach_email,
                        "customer_email": req.customer_email,
                        "customer_name": req.customer_name
                    })[:255]
                }],
                "application_context": {
                    "return_url": success_url,
                    "cancel_url": cancel_url,
                    "brand_name": "Afroboost",
                    "user_action": "PAY_NOW"
                }
            }

            async with httpx.AsyncClient() as client:
                order_resp = await client.post(
                    f"{base_url}/v2/checkout/orders",
                    json=order_data,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    },
                    timeout=15
                )

            if order_resp.status_code not in [200, 201]:
                logger.error(f"[CHECKOUT] PayPal order error: {order_resp.text}")
                raise HTTPException(status_code=503, detail="Erreur lors de la création de la commande PayPal")

            order = order_resp.json()
            approve_link = next((l["href"] for l in order.get("links", []) if l["rel"] == "approve"), None)

            if not approve_link:
                raise HTTPException(status_code=500, detail="Lien d'approbation PayPal non trouvé")

            # Enregistrer la transaction
            await db["checkout_transactions"].insert_one({
                "transaction_id": transaction_id,
                "paypal_order_id": order["id"],
                "coach_email": req.coach_email,
                "customer_email": req.customer_email,
                "customer_name": req.customer_name,
                "customer_phone": req.customer_phone,
                "items": [i.dict() for i in req.items],
                "total": total,
                "currency": currency,
                "payment_method": "paypal",
                "status": "pending",
                "discount_code": req.discount_code,
                "created_at": datetime.now(timezone.utc).isoformat()
            })

            logger.info(f"[CHECKOUT] PayPal order créé: {order['id']} pour {req.coach_email} ({total} {currency})")

            return {
                "success": True,
                "payment_url": approve_link,
                "transaction_id": transaction_id,
                "order_id": order["id"],
                "method": "paypal",
                "recipient": req.coach_email
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[CHECKOUT] Erreur PayPal: {e}")
            raise HTTPException(status_code=500, detail=f"Erreur PayPal: {str(e)[:200]}")

    # ===== MOBILE MONEY (CinetPay) =====
    elif req.payment_method == "mobile_money":
        try:
            # Conversion CHF → XOF (approximatif)
            xof_rate = 400  # ~400 XOF = 1 CHF
            total_xof = int(total * xof_rate)
            if total_xof < 100:
                total_xof = 100  # Minimum CinetPay

            notify_url = os.environ.get("CINETPAY_NOTIFY_URL", f"{FRONTEND_URL}/api/checkout/webhook/cinetpay")

            payload = {
                "apikey": keys["cinetpay_api_key"],
                "site_id": keys["cinetpay_site_id"],
                "transaction_id": transaction_id,
                "amount": total_xof,
                "currency": "XOF",
                "description": items_desc[:255],
                "notify_url": notify_url,
                "return_url": success_url,
                "cancel_url": cancel_url,
                "channels": "ALL",
                "customer_name": req.customer_name[:50],
                "customer_email": req.customer_email,
                "customer_phone_number": req.customer_phone or "",
                "customer_city": "Afroboost",
                "customer_country": "CI",
                "metadata": json.dumps({
                    "coach_email": req.coach_email,
                    "items": items_desc,
                    "type": "vitrine_purchase"
                })
            }

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api-checkout.cinetpay.com/v2/payment",
                    json=payload,
                    timeout=30
                )

            data = resp.json()

            if data.get("code") != "201" and resp.status_code not in [200, 201]:
                logger.error(f"[CHECKOUT] CinetPay error: {data}")
                raise HTTPException(status_code=503, detail="Le paiement Mobile Money est temporairement indisponible")

            payment_url = data.get("data", {}).get("payment_url")
            if not payment_url:
                raise HTTPException(status_code=500, detail="URL de paiement CinetPay non générée")

            # Enregistrer la transaction
            await db["checkout_transactions"].insert_one({
                "transaction_id": transaction_id,
                "cinetpay_token": data.get("data", {}).get("payment_token", ""),
                "coach_email": req.coach_email,
                "customer_email": req.customer_email,
                "customer_name": req.customer_name,
                "customer_phone": req.customer_phone,
                "items": [i.dict() for i in req.items],
                "total": total,
                "total_xof": total_xof,
                "currency": "XOF",
                "payment_method": "mobile_money",
                "status": "pending",
                "discount_code": req.discount_code,
                "created_at": datetime.now(timezone.utc).isoformat()
            })

            logger.info(f"[CHECKOUT] CinetPay session créée: {transaction_id} pour {req.coach_email} ({total_xof} XOF)")

            return {
                "success": True,
                "payment_url": payment_url,
                "transaction_id": transaction_id,
                "method": "mobile_money",
                "recipient": req.coach_email
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[CHECKOUT] Erreur CinetPay: {e}")
            raise HTTPException(status_code=500, detail=f"Erreur Mobile Money: {str(e)[:200]}")

    else:
        raise HTTPException(status_code=400, detail=f"Méthode de paiement non supportée : {req.payment_method}")


# ===== WEBHOOKS =====

@router.post("/webhook/stripe")
async def checkout_stripe_webhook(request: Request):
    """Webhook Stripe pour les paiements vitrine (checkout unifié)"""
    import stripe as stripe_lib

    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    # Note: Pour les paiements partenaires, on ne peut pas vérifier la signature
    # car chaque partenaire a sa propre clé webhook.
    # On vérifie plutôt via le metadata.transaction_id en base.

    try:
        event_data = json.loads(payload)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payload")

    if event_data.get("type") == "checkout.session.completed":
        session = event_data["data"]["object"]
        metadata = session.get("metadata", {})

        if metadata.get("type") != "vitrine_purchase":
            # Pas un achat vitrine, ignorer (géré par les autres webhooks)
            return {"status": "ignored"}

        transaction_id = metadata.get("transaction_id")
        if not transaction_id:
            return {"status": "no_transaction_id"}

        # Vérifier que la transaction existe et n'est pas déjà traitée
        txn = await db["checkout_transactions"].find_one({"transaction_id": transaction_id})
        if not txn:
            return {"status": "transaction_not_found"}
        if txn.get("status") == "completed":
            return {"status": "already_processed"}

        # Traiter le paiement
        items_json = metadata.get("items", "[]")
        try:
            items_data = json.loads(items_json)
            items = [CheckoutItem(**i) for i in items_data]
        except:
            items = []

        await _process_successful_payment(
            transaction_id=transaction_id,
            coach_email=metadata.get("coach_email", ""),
            customer_name=metadata.get("customer_name", ""),
            customer_email=session.get("customer_email", ""),
            customer_phone=metadata.get("customer_phone", ""),
            items=items,
            total=session.get("amount_total", 0) / 100,
            currency=session.get("currency", "chf").upper(),
            payment_method="card",
            discount_code=metadata.get("discount_code")
        )

        logger.info(f"[CHECKOUT-WEBHOOK] Paiement Stripe confirmé: {transaction_id}")

    return {"status": "ok"}


@router.post("/webhook/cinetpay")
async def checkout_cinetpay_webhook(request: Request):
    """Webhook CinetPay pour les paiements vitrine Mobile Money"""
    try:
        body = await request.json()
    except:
        body = {}

    cpm_trans_id = body.get("cpm_trans_id") or body.get("transaction_id", "")

    if not cpm_trans_id:
        return {"status": "no_transaction_id"}

    txn = await db["checkout_transactions"].find_one({"transaction_id": cpm_trans_id})
    if not txn:
        return {"status": "transaction_not_found"}
    if txn.get("status") == "completed":
        return {"status": "already_processed"}

    # Vérifier le statut auprès de CinetPay
    keys, error = await get_payment_keys(txn["coach_email"], "mobile_money")
    if error:
        logger.error(f"[CHECKOUT-WEBHOOK] Clés CinetPay introuvables pour {txn['coach_email']}")
        return {"status": "config_error"}

    async with httpx.AsyncClient() as client:
        check_resp = await client.post(
            "https://api-checkout.cinetpay.com/v2/payment/check",
            json={
                "apikey": keys["cinetpay_api_key"],
                "site_id": keys["cinetpay_site_id"],
                "transaction_id": cpm_trans_id
            },
            timeout=15
        )

    check_data = check_resp.json()
    payment_status = check_data.get("data", {}).get("status", "")

    if payment_status == "ACCEPTED":
        items = [CheckoutItem(**i) for i in txn.get("items", [])]

        await _process_successful_payment(
            transaction_id=cpm_trans_id,
            coach_email=txn["coach_email"],
            customer_name=txn.get("customer_name", ""),
            customer_email=txn.get("customer_email", ""),
            customer_phone=txn.get("customer_phone", ""),
            items=items,
            total=txn.get("total", 0),
            currency=txn.get("currency", "XOF"),
            payment_method="mobile_money",
            discount_code=txn.get("discount_code")
        )

        logger.info(f"[CHECKOUT-WEBHOOK] Paiement CinetPay confirmé: {cpm_trans_id}")
    else:
        await db["checkout_transactions"].update_one(
            {"transaction_id": cpm_trans_id},
            {"$set": {"status": "failed", "payment_status": payment_status}}
        )

    return {"status": "ok"}


@router.post("/webhook/paypal")
async def checkout_paypal_webhook(request: Request):
    """Webhook PayPal (capture automatique après retour client)"""
    try:
        body = await request.json()
    except:
        body = {}

    order_id = body.get("orderID") or body.get("order_id", "")
    transaction_id = body.get("transaction_id", "")

    if not transaction_id:
        return {"status": "no_transaction_id"}

    txn = await db["checkout_transactions"].find_one({"transaction_id": transaction_id})
    if not txn:
        return {"status": "transaction_not_found"}
    if txn.get("status") == "completed":
        return {"status": "already_processed"}

    # Capturer le paiement PayPal
    keys, error = await get_payment_keys(txn["coach_email"], "paypal")
    if error:
        return {"status": "config_error"}

    base_url = "https://api-m.sandbox.paypal.com" if keys["paypal_mode"] == "sandbox" else "https://api-m.paypal.com"

    # Obtenir token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            f"{base_url}/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            auth=(keys["paypal_client_id"], keys["paypal_client_secret"]),
            timeout=15
        )

    if token_resp.status_code != 200:
        return {"status": "token_error"}

    access_token = token_resp.json()["access_token"]
    paypal_order_id = txn.get("paypal_order_id", order_id)

    # Capturer
    async with httpx.AsyncClient() as client:
        capture_resp = await client.post(
            f"{base_url}/v2/checkout/orders/{paypal_order_id}/capture",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            timeout=15
        )

    if capture_resp.status_code in [200, 201]:
        capture_data = capture_resp.json()
        if capture_data.get("status") == "COMPLETED":
            items = [CheckoutItem(**i) for i in txn.get("items", [])]

            await _process_successful_payment(
                transaction_id=transaction_id,
                coach_email=txn["coach_email"],
                customer_name=txn.get("customer_name", ""),
                customer_email=txn.get("customer_email", ""),
                customer_phone=txn.get("customer_phone", ""),
                items=items,
                total=txn.get("total", 0),
                currency=txn.get("currency", "CHF"),
                payment_method="paypal",
                discount_code=txn.get("discount_code")
            )

            return {"status": "captured"}

    return {"status": "capture_failed"}


# ===== PAYMENT SUCCESS HANDLER =====

async def _process_successful_payment(
    transaction_id: str,
    coach_email: str,
    customer_name: str,
    customer_email: str,
    customer_phone: str,
    items: list,
    total: float,
    currency: str,
    payment_method: str,
    discount_code: str = None
):
    """Traite un paiement réussi : réservation, code accès, QR, notifications"""

    # 1. Mettre à jour le statut de la transaction
    await db["checkout_transactions"].update_one(
        {"transaction_id": transaction_id},
        {"$set": {
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )

    # 2. Générer un code d'accès unique
    import random
    import string
    access_code = f"AFR-{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}"

    # 3. Stocker le code dans discount_codes (même collection que les codes existants)
    await db["discount_codes"].insert_one({
        "id": str(uuid.uuid4()),
        "code": access_code,
        "coach_id": coach_email,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "customer_phone": customer_phone,
        "type": "access",
        "value": 0,
        "max_uses": 999,
        "current_uses": 0,
        "active": True,
        "source": "checkout_payment",
        "transaction_id": transaction_id,
        "payment_method": payment_method,
        "total_paid": total,
        "currency": currency,
        "items": [i.dict() if hasattr(i, 'dict') else i for i in items],
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    # 4. Créer les réservations pour chaque item de type "course"
    for item in items:
        item_data = item.dict() if hasattr(item, 'dict') else item
        if item_data.get("type") == "course":
            await db["reservations"].insert_one({
                "id": str(uuid.uuid4()),
                "userName": customer_name,
                "userEmail": customer_email,
                "userWhatsapp": customer_phone,
                "courseName": item_data.get("name", ""),
                "coach_id": coach_email,
                "source": "checkout_vitrine",
                "type": "ticket",
                "offerName": item_data.get("name", ""),
                "totalPrice": item_data.get("price", 0),
                "quantity": item_data.get("quantity", 1),
                "promoCode": discount_code or access_code,
                "discountCode": access_code,
                "status": "confirmed",
                "payment_method": payment_method,
                "transaction_id": transaction_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "isProduct": item_data.get("type") == "product"
            })

    # 5. QR Code URL
    qr_url = f"https://afroboost.com/?qr={access_code}"
    qr_image_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={qr_url}"

    # 6. Envoyer les notifications par email
    try:
        import resend
        resend_key = os.environ.get("RESEND_API_KEY", "")
        if resend_key:
            resend.api_key = resend_key

            items_desc = ", ".join([
                f"{(i.dict() if hasattr(i, 'dict') else i).get('name', 'Article')} x{(i.dict() if hasattr(i, 'dict') else i).get('quantity', 1)}"
                for i in items
            ])

            # Email au client
            try:
                resend.Emails.send({
                    "from": "Afroboost <notifications@afroboosteur.com>",
                    "to": [customer_email],
                    "subject": f"✅ Confirmation de votre achat - {access_code}",
                    "html": f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #1a1a2e; color: white; padding: 30px; border-radius: 12px;">
                        <h1 style="color: #D91CD2; text-align: center;">🎉 Merci pour votre achat !</h1>
                        <p>Bonjour <strong>{customer_name}</strong>,</p>
                        <p>Votre paiement de <strong>{total} {currency}</strong> a été confirmé.</p>
                        <div style="background: rgba(217, 28, 210, 0.1); border: 1px solid #D91CD2; border-radius: 8px; padding: 20px; margin: 20px 0; text-align: center;">
                            <p style="color: #D91CD2; font-size: 14px; margin: 0 0 10px 0;">Votre Code d'Accès</p>
                            <p style="font-size: 28px; font-weight: bold; color: white; margin: 0; letter-spacing: 3px;">{access_code}</p>
                        </div>
                        <div style="text-align: center; margin: 20px 0;">
                            <img src="{qr_image_url}" alt="QR Code" style="width: 150px; height: 150px;" />
                            <p style="color: rgba(255,255,255,0.6); font-size: 12px;">Scannez ce QR code pour accéder à vos services</p>
                        </div>
                        <p><strong>Détail :</strong> {items_desc}</p>
                        <p><strong>Méthode :</strong> {payment_method}</p>
                        <hr style="border-color: rgba(255,255,255,0.1);" />
                        <p style="text-align: center; color: rgba(255,255,255,0.4); font-size: 12px;">Afroboost - Votre plateforme de bien-être</p>
                    </div>
                    """
                })
                logger.info(f"[CHECKOUT] Email client envoyé à {customer_email}")
            except Exception as e:
                logger.error(f"[CHECKOUT] Erreur email client: {e}")

            # Email au vendeur
            try:
                coach = await db["coaches"].find_one({"email": coach_email})
                vendor_email = coach_email
                if coach and coach.get("notification_email"):
                    vendor_email = coach["notification_email"]

                resend.Emails.send({
                    "from": "Afroboost <notifications@afroboosteur.com>",
                    "to": [vendor_email],
                    "subject": f"💰 Nouvelle vente ! {total} {currency} - {customer_name}",
                    "html": f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #1a1a2e; color: white; padding: 30px; border-radius: 12px;">
                        <h1 style="color: #22c55e; text-align: center;">💰 Nouvelle vente sur votre vitrine !</h1>
                        <div style="background: rgba(34, 197, 94, 0.1); border: 1px solid #22c55e; border-radius: 8px; padding: 20px; margin: 20px 0;">
                            <p><strong>Client :</strong> {customer_name} ({customer_email})</p>
                            <p><strong>Articles :</strong> {items_desc}</p>
                            <p><strong>Montant :</strong> {total} {currency}</p>
                            <p><strong>Méthode :</strong> {payment_method}</p>
                            <p><strong>Code client :</strong> {access_code}</p>
                        </div>
                        <p style="text-align: center; color: rgba(255,255,255,0.4); font-size: 12px;">Afroboost - Tableau de bord partenaire</p>
                    </div>
                    """
                })
                logger.info(f"[CHECKOUT] Email vendeur envoyé à {vendor_email}")
            except Exception as e:
                logger.error(f"[CHECKOUT] Erreur email vendeur: {e}")
    except ImportError:
        logger.warning("[CHECKOUT] Resend non disponible, emails non envoyés")

    logger.info(f"[CHECKOUT] Paiement traité: {transaction_id}, code={access_code}, vendeur={coach_email}")
