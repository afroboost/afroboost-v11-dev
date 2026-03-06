"""
Stripe Routes v13.4
Routes pour les paiements Stripe - Checkout, Connect, Webhooks
Extrait de server.py - Updated to use async Motor client
"""
import os
import stripe
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stripe", tags=["stripe"])

# Configure Stripe
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

# Variable db sera injectée depuis server.py
db = None

def init_db(database):
    global db
    db = database


# === Pydantic Models ===

class StripeCheckoutRequest(BaseModel):
    """Requête pour créer une session de paiement Stripe"""
    amount: float
    currency: str = "chf"
    description: str = ""
    customer_email: Optional[str] = None
    metadata: Optional[dict] = None
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class CreditCheckoutRequest(BaseModel):
    """Requête pour acheter des crédits"""
    pack_id: str
    coach_email: str
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


# === Stripe Checkout Routes ===

@router.post("/create-checkout-session")
async def create_stripe_checkout(request: StripeCheckoutRequest):
    """
    Crée une session Stripe Checkout avec support pour cartes et TWINT.
    """
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe API key not configured")
    
    # URLs par défaut
    frontend_url = os.environ.get('REACT_APP_FRONTEND_URL', 'https://afroboost.ch')
    success_url = request.success_url or f"{frontend_url}/payment/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = request.cancel_url or f"{frontend_url}/payment/cancel"
    
    # Montant en centimes
    amount_cents = int(request.amount * 100)
    
    try:
        # Liste des méthodes de paiement
        payment_methods = ["card"]
        
        # Ajouter TWINT si disponible et devise CHF
        if request.currency.lower() == "chf":
            payment_methods.append("twint")
        
        # Créer la session Stripe
        session = stripe.checkout.Session.create(
            payment_method_types=payment_methods,
            line_items=[{
                "price_data": {
                    "currency": request.currency.lower(),
                    "unit_amount": amount_cents,
                    "product_data": {
                        "name": request.description or "Paiement Afroboost",
                    },
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=request.customer_email,
            metadata=request.metadata or {},
        )
        
        logger.info(f"Stripe session created: {session.id}")
        
        return {
            "url": session.url,
            "session_id": session.id,
            "payment_methods": payment_methods
        }
        
    except stripe.error.InvalidRequestError as e:
        logger.error(f"Stripe InvalidRequestError: {str(e)}")
        
        # Fallback sans TWINT
        try:
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{
                    "price_data": {
                        "currency": request.currency.lower(),
                        "unit_amount": amount_cents,
                        "product_data": {
                            "name": request.description or "Paiement Afroboost",
                        },
                    },
                    "quantity": 1,
                }],
                mode="payment",
                success_url=success_url,
                cancel_url=cancel_url,
                customer_email=request.customer_email,
                metadata=request.metadata or {},
            )
            
            return {
                "url": session.url,
                "session_id": session.id,
                "payment_methods": ["card"],
                "warning": "TWINT not available"
            }
            
        except stripe.error.StripeError as fallback_error:
            logger.error(f"Stripe fallback error: {str(fallback_error)}")
            raise HTTPException(status_code=500, detail=str(fallback_error))
            
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}")
async def check_stripe_session(session_id: str):
    """
    Vérifie le statut d'une session de paiement Stripe.
    """
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe API key not configured")
    
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        return {
            "status": session.payment_status,
            "amount_total": session.amount_total / 100 if session.amount_total else 0,
            "currency": session.currency,
            "customer_email": session.customer_email,
            "metadata": session.metadata
        }
    except stripe.error.StripeError as e:
        logger.error(f"Error checking session: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


# === Credit Packs Purchase ===

@router.post("/create-credit-checkout-session")
async def create_credit_checkout_session(request: CreditCheckoutRequest):
    """
    Crée une session Stripe pour acheter des crédits.
    v13.0: Vente de packs de crédits aux partenaires.
    """
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe API key not configured")
    
    # Récupérer le pack - ASYNC
    pack = await db.coach_packs.find_one({"id": request.pack_id})
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")
    
    if not pack.get("isActive", True):
        raise HTTPException(status_code=400, detail="Pack not available")
    
    frontend_url = os.environ.get('REACT_APP_FRONTEND_URL', 'https://afroboost.ch')
    success_url = request.success_url or f"{frontend_url}/dashboard?tab=boutique&payment=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = request.cancel_url or f"{frontend_url}/dashboard?tab=boutique&payment=cancel"
    
    amount_cents = int(pack.get("price", 0) * 100)
    
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card", "twint"] if amount_cents >= 100 else ["card"],
            line_items=[{
                "price_data": {
                    "currency": "chf",
                    "unit_amount": amount_cents,
                    "product_data": {
                        "name": f"Pack {pack.get('name', 'Crédits')} - {pack.get('credits', 0)} crédits",
                        "description": pack.get("description", "Pack de crédits Afroboost"),
                    },
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=request.coach_email,
            metadata={
                "type": "credit_purchase",
                "pack_id": request.pack_id,
                "pack_name": pack.get("name", ""),
                "credits": str(pack.get("credits", 0)),
                "coach_email": request.coach_email
            },
        )
        
        logger.info(f"Credit checkout session created: {session.id} for {request.coach_email}")
        
        return {
            "url": session.url,
            "session_id": session.id
        }
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating credit checkout: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# === Stripe Connect Routes ===

@router.post("/connect/create-account")
async def create_stripe_connect_account(
    x_user_email: str = Header(None, alias="X-User-Email")
):
    """
    Crée un compte Stripe Connect pour un partenaire.
    """
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe API key not configured")
    
    if not x_user_email:
        raise HTTPException(status_code=401, detail="Missing X-User-Email header")
    
    # Vérifier si le coach existe - ASYNC
    coach = await db.coaches.find_one({"email": x_user_email})
    if not coach:
        raise HTTPException(status_code=404, detail="Coach not found")
    
    # Si déjà un compte Connect, retourner l'ID
    if coach.get("stripe_connect_id"):
        return {"account_id": coach.get("stripe_connect_id"), "existing": True}
    
    try:
        # Créer le compte Connect Express
        account = stripe.Account.create(
            type="express",
            country="CH",
            email=x_user_email,
            capabilities={
                "card_payments": {"requested": True},
                "transfers": {"requested": True},
            },
            business_type="individual",
            metadata={
                "coach_email": x_user_email,
                "platform": "afroboost"
            }
        )
        
        # Sauvegarder l'ID du compte Connect - ASYNC
        await db.coaches.update_one(
            {"email": x_user_email},
            {"$set": {"stripe_connect_id": account.id, "updated_at": datetime.now(timezone.utc)}}
        )
        
        logger.info(f"Stripe Connect account created: {account.id} for {x_user_email}")
        
        return {"account_id": account.id, "existing": False}
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe Connect error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/connect/account-link")
async def create_account_link(
    x_user_email: str = Header(None, alias="X-User-Email")
):
    """
    Crée un lien d'onboarding Stripe Connect.
    """
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe API key not configured")
    
    if not x_user_email:
        raise HTTPException(status_code=401, detail="Missing X-User-Email header")
    
    # ASYNC
    coach = await db.coaches.find_one({"email": x_user_email})
    if not coach:
        raise HTTPException(status_code=404, detail="Coach not found")
    
    account_id = coach.get("stripe_connect_id")
    if not account_id:
        raise HTTPException(status_code=400, detail="No Stripe Connect account. Create one first.")
    
    frontend_url = os.environ.get('REACT_APP_FRONTEND_URL', 'https://afroboost.ch')
    
    try:
        account_link = stripe.AccountLink.create(
            account=account_id,
            refresh_url=f"{frontend_url}/dashboard?tab=stripe&refresh=true",
            return_url=f"{frontend_url}/dashboard?tab=stripe&onboarding=complete",
            type="account_onboarding",
        )
        
        return {"url": account_link.url}
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe AccountLink error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/connect/status")
async def get_stripe_connect_status(
    x_user_email: str = Header(None, alias="X-User-Email")
):
    """
    Vérifie le statut d'un compte Stripe Connect.
    """
    if not stripe.api_key:
        return {"connected": False, "error": "Stripe not configured"}
    
    if not x_user_email:
        return {"connected": False, "error": "Missing email"}
    
    # ASYNC
    coach = await db.coaches.find_one({"email": x_user_email})
    if not coach or not coach.get("stripe_connect_id"):
        return {"connected": False, "account_id": None}
    
    account_id = coach.get("stripe_connect_id")
    
    try:
        account = stripe.Account.retrieve(account_id)
        return {
            "connected": True,
            "account_id": account_id,
            "charges_enabled": account.charges_enabled,
            "payouts_enabled": account.payouts_enabled,
            "details_submitted": account.details_submitted,
            "email": account.email
        }
    except stripe.error.StripeError as e:
        logger.error(f"Error retrieving Stripe account: {str(e)}")
        return {"connected": False, "error": str(e)}


# === Webhook Handler ===

@router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Gère les webhooks Stripe (paiements, Connect, etc.)
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')
    
    event = None
    
    try:
        if webhook_secret:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
        else:
            # Mode développement sans signature
            import json
            event = json.loads(payload)
            logger.warning("Webhook processed without signature verification")
    except ValueError as e:
        logger.error(f"Invalid payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid signature: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    event_type = event.get("type", "")
    
    # === Paiement complété (achat de crédits) ===
    if event_type == "checkout.session.completed":
        session = event.get("data", {}).get("object", {})
        metadata = session.get("metadata", {})
        
        # Vérifier si c'est un achat de crédits
        if metadata.get("type") == "credit_purchase":
            coach_email = metadata.get("coach_email")
            credits_to_add = int(metadata.get("credits", 0))
            pack_name = metadata.get("pack_name", "Unknown")
            
            if coach_email and credits_to_add > 0:
                # Ajouter les crédits au coach - ASYNC
                result = await db.coaches.update_one(
                    {"email": coach_email},
                    {"$inc": {"credits": credits_to_add}}
                )
                
                if result.modified_count > 0:
                    # Enregistrer la transaction - ASYNC
                    await db.credit_transactions.insert_one({
                        "coach_email": coach_email,
                        "credits_added": credits_to_add,
                        "pack_name": pack_name,
                        "amount": session.get("amount_total", 0) / 100,
                        "currency": session.get("currency", "chf"),
                        "stripe_session_id": session.get("id"),
                        "stripe_payment_intent": session.get("payment_intent"),
                        "date": datetime.now(timezone.utc)
                    })
                    
                    logger.info(f"Added {credits_to_add} credits to {coach_email} (pack: {pack_name})")
                else:
                    logger.error(f"Failed to add credits to {coach_email}")
    
    # === Événements Stripe Connect ===
    elif event_type == "account.updated":
        account = event.get("data", {}).get("object", {})
        account_id = account.get("id")
        
        # Mettre à jour le statut du coach - ASYNC
        if account_id:
            await db.coaches.update_one(
                {"stripe_connect_id": account_id},
                {"$set": {
                    "stripe_connect_charges_enabled": account.get("charges_enabled", False),
                    "stripe_connect_payouts_enabled": account.get("payouts_enabled", False),
                    "updated_at": datetime.now(timezone.utc)
                }}
            )
            logger.info(f"Stripe Connect account updated: {account_id}")
    
    return {"received": True}
