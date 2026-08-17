# v15.0: Unified Checkout Routes - Multi-Vendor Payment Routing
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone
import os
import uuid
import logging
from api.routes.shared import (
    expiration_forfait as _v397_expiration,
    cloturer_anciens_forfaits as _v397_cloturer,
)
import httpx
import json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/checkout", tags=["checkout"])
from api.routes.shared import get_primary_color, hex_to_rgb_triplet  # V259

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


async def _t1_preuve_checkout(accepte, items, coach_email: str = "",
                              exiger: bool = True) -> dict:
    """La preuve d'acceptation pour un passage en caisse.

    Le cours concerne est celui du premier article de type « course » : c'est
    lui qui porte, ou non, l'annonce de captation. Un panier sans cours (un
    forfait, un produit) n'a pas de captation a annoncer — les conditions, elles,
    s'appliquent quand meme.

    Import differe de `api.server`, comme partout ailleurs dans ce module :
    server.py importe ce fichier, l'inverse ne peut se faire qu'a l'appel.
    """
    _cid = ""
    for _it in (items or []):
        _t = getattr(_it, "type", None) or (_it.get("type") if isinstance(_it, dict) else "")
        _i = getattr(_it, "id", None) or (_it.get("id") if isinstance(_it, dict) else "")
        if str(_t or "") == "course" and _i:
            _cid = str(_i)
            break
    try:
        from api.server import t1_preuve as _t1
        return await _t1(accepte, _cid, coach_email)
    except HTTPException:
        # `exiger=False` : on etablit la preuve si elle existe, sans bloquer.
        # C'est le cas de la creation d'une session de paiement, qui ne cree
        # AUCUNE reservation par elle-meme — et que le bot WhatsApp appelle
        # cote serveur, sans case a cocher a lui offrir. Le refus est porte
        # la ou une reservation nait vraiment.
        if exiger:
            raise
        return {}
    except Exception as _err:
        logger.warning(f"[T1] preuve d'acceptation ignoree: {_err}")
        return {}


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
    # V401 : pays du Mobile Money pawaPay (« CIV », « SEN »…). Optionnel et
    # ignoré par tous les autres moyens : aucun appelant existant ne le passe,
    # donc aucun parcours actuel ne change. Absent, `resoudre_pays` retombe sur
    # la configuration du compte pawaPay comme partout ailleurs.
    country: Optional[str] = None
    # ESSAI-5a-1 : la seule chose que le client exprime.
    terms_accepted: Optional[bool] = None

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

    # ESSAI-5a-1 — les conditions AVANT tout le reste : avant le calcul du
    # total, avant la garde d'essai, avant la moindre ecriture. Un refus ici
    # ne laisse aucune trace derriere lui.
    _t1_champs = await _t1_preuve_checkout(req.terms_accepted, req.items,
                                           req.coach_email, exiger=False)

    # ESSAI-1B : le total qui DECIDE vient du catalogue. `discount_amount`,
    # fourni par le navigateur, n'est plus une autorite metier.
    total, _prix_resolus = await _essai1b_total_autorite(req.items)

    if total <= 0 and _prix_resolus:
        # Gratuit : pas de paiement, créer directement la réservation
        #
        # ESSAI-1 : cette branche mene EXACTEMENT aux memes ecritures que
        # `/free` — meme helper, meme forfait, meme code AFR-. Garder la garde
        # sur la seule route `/free` la rendrait contournable en changeant
        # d'URL. Elle est donc posee ici aussi, avant la premiere ecriture.
        # Cette branche cree une reservation : les conditions y sont EXIGEES,
        # contrairement a la creation d'une session de paiement au-dessus.
        _t1_champs = await _t1_preuve_checkout(req.terms_accepted, req.items,
                                               req.coach_email, exiger=True)
        await _essai1_garde(req.customer_email,
                            str((req.items[0].id if req.items else "") or ""))
        transaction_id = f"free_{uuid.uuid4().hex[:12]}"
        try:
            await _process_successful_payment(
                terms_fields=_t1_champs,
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
        except Exception:
            # La creation a echoue : on rend la reservation, sinon la personne
            # perdrait son essai sans jamais l'avoir recu.
            await _essai1_liberer(req.customer_email)
            raise
        # ESSAI-2 : meme mesure sur la seconde porte gratuite.
        try:
            from api.routes.shared import essai2_tracer_octroi as _e2_octroi
            await _e2_octroi(db, req.customer_email,
                             str((req.items[0].id if req.items else "") or ""), 0)
        except Exception as _e2err:
            logger.warning(f"[ESSAI-2] octroi non mesure: {_e2err}")

        # V248: notification push au coach — le flux gratuit ne passe pas par le
        # webhook Stripe, il n'avait donc AUCUNE notif (l'email, lui, part deja
        # depuis _process_successful_payment). Import LAZY pour eviter le cycle :
        # server.py importe deja ce module au chargement.
        try:
            from api.server import send_push_by_email as _v248_push
            _v248_offer = (req.items[0].name if req.items else "") or "une offre gratuite"
            await _v248_push(
                req.coach_email,
                "Nouvelle souscription",
                f"{req.customer_name or 'Un client'} s'est inscrit à {_v248_offer} (gratuit)"
            )
        except Exception as _v248_err:
            logger.warning(f"[V248] Push gratuit non-bloquant: {_v248_err}")
        return {
            "success": True,
            "free": True,
            "transaction_id": transaction_id,
            "message": "Réservation confirmée gratuitement !"
        }

    # Récupérer les clés du vendeur.
    #
    # V401 : pawaPay est SAUTÉ ici, et c'est délibéré. `get_payment_keys` résout
    # des clés PAR VENDEUR (Stripe, PayPal, CinetPay du partenaire) ; l'intégration
    # pawaPay est GLOBALE — un seul compte, un seul jeton, une seule URL de
    # callback déjà déclarée chez pawaPay. La faire passer par ce résolveur
    # obligerait chaque partenaire à saisir des clés qu'il n'a pas, et ferait
    # échouer le moyen pour tout le monde sauf l'admin.
    keys = {}
    if req.payment_method != "pawapay":
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
                # ESSAI-1B : le montant DEBITE vient du catalogue, pas du
                # navigateur. Il etait calcule `item.price - discount_amount`,
                # deux valeurs fournies par le client : n'importe qui pouvait
                # ramener une offre a 250 CHF a zero. `discount_amount` n'est
                # plus consulte ; une remise reelle doit venir d'un code valide
                # par le serveur, mecanisme qui existe deja ailleurs.
                _prix_reel, _atteste = await _essai1b_prix_unitaire(item)
                if not _atteste:
                    logger.warning(
                        "[ESSAI-1B] article hors catalogue au paiement : prix non atteste")
                amount = int(round(max(0.0, _prix_reel) * 100))  # centimes
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
                # ESSAI-5a-1 : la preuve est etablie MAINTENANT, au moment ou la
                # personne coche. Elle attend ici que le webhook cree la
                # reservation, pour ne pas etre refabriquee avec une fausse heure.
                "terms_fields": _t1_champs,
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

    # ===== MOBILE MONEY (pawaPay) — V401 =====
    #
    # Le panier de la vitrine n'avait qu'un Mobile Money : CinetPay, inerte en
    # production. pawaPay, lui, est configuré et ouvert sur 12 pays — mais n'était
    # branché QUE sur les offres à l'unité, les packs partenaire et le Boost.
    # Cette branche l'ajoute au panier, À CÔTÉ des trois moyens existants, sans en
    # modifier aucun.
    #
    # ⚠️ L'ACTIVATION RESTE CELLE DE LA VITRINE. On ne réutilise pas l'activation
    # générique de pawaPay : le panier a la sienne (`_process_successful_payment`),
    # qui crée le code, l'abonnement, les RÉSERVATIONS des articles de type
    # « course » et envoie les deux e-mails. Le webhook pawaPay reconnaît le type
    # `vitrine_purchase` et rebranche dessus (voir `payment_activation.py`).
    elif req.payment_method == "pawapay":
        try:
            # Imports TARDIFS : `pawapay_routes` importe déjà ce module au
            # chargement (chaîne checkout -> pawapay), un import en tête créerait
            # un cycle. Même motif que `payment_activation` avec `boost_routes`.
            from api.routes.pawapay_routes import (
                require_pawapay, resoudre_pays, montant_dans_devise,
                create_pawapay_deposit, normalize_msisdn,
            )

            token, base_url = await require_pawapay()
            pays, devise = await resoudre_pays(token, base_url, req.country)
            # Le prix en CHF fait foi : la conversion se fait ICI, jamais dans le
            # navigateur — même règle que `create-checkout` (V382).
            montant = montant_dans_devise(total, None, devise)
            if not montant or montant <= 0:
                raise HTTPException(status_code=400, detail="Montant de paiement invalide.")

            # ⚠️ LE `depositId` DOIT ÊTRE UN UUID. pawaPay le valide et refuse
            # tout autre format : réutiliser le `txn_xxxxx` du panier renvoyait
            # « INVALID_PARAMETER / Value for parameter 'depositId' is invalid »
            # (constaté en production sur la première sonde). Le lien entre les
            # deux mondes passe donc par `metadata.checkout_transaction_id`, et
            # par `deposit_id` recopié dans la transaction du panier ci-dessous.
            deposit_id = str(uuid.uuid4())

            # Tout ce dont l'activation aura besoin est figé MAINTENANT, côté
            # serveur. Le webhook ne recevra que le `depositId` : sans cela, il
            # n'aurait aucun moyen de savoir quoi délivrer.
            await db["pawapay_transactions"].insert_one({
                "depositId": deposit_id,
                "amount": montant,
                "amount_chf": total,
                "currency": devise,
                "country": pays,
                "description": items_desc[:255],
                "customer_name": req.customer_name,
                "customer_email": req.customer_email,
                "customer_phone": req.customer_phone,
                "type": "vitrine_purchase",
                "metadata": {
                    "type": "vitrine_purchase",
                    "checkout_transaction_id": transaction_id,
                    "coach_email": req.coach_email,
                    "items": [i.dict() for i in req.items],
                    "total_chf": total,
                    "discount_code": req.discount_code,
                },
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

            await db["checkout_transactions"].insert_one({
                "transaction_id": transaction_id,
                # Le pont vers `pawapay_transactions`, dans les deux sens.
                "deposit_id": deposit_id,
                "coach_email": req.coach_email,
                "customer_email": req.customer_email,
                "customer_name": req.customer_name,
                "customer_phone": req.customer_phone,
                "items": [i.dict() for i in req.items],
                "total": total,
                "total_local": montant,
                "currency": devise,
                "country": pays,
                "payment_method": "pawapay",
                "status": "pending",
                "discount_code": req.discount_code,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

            payment_url = await create_pawapay_deposit(
                token=token, base_url=base_url, deposit_id=deposit_id,
                amount=montant, country=pays, reason=items_desc[:255],
                return_url=success_url,
                msisdn=normalize_msisdn(req.customer_phone), currency=devise,
            )

            logger.info(
                f"[CHECKOUT] V401 pawaPay session creee: {transaction_id} "
                f"pour {req.coach_email} ({montant} {devise}, {pays})"
            )
            return {
                "success": True,
                "payment_url": payment_url,
                "transaction_id": transaction_id,
                "method": "pawapay",
                "currency": devise,
                "amount_local": montant,
                "country": pays,
                "recipient": req.coach_email,
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[CHECKOUT] V401 erreur pawaPay: {e}")
            raise HTTPException(status_code=500, detail=f"Erreur Mobile Money: {str(e)[:200]}")

    else:
        raise HTTPException(status_code=400, detail=f"Méthode de paiement non supportée : {req.payment_method}")


class FreeCheckoutRequest(BaseModel):
    coach_email: str
    items: List[CheckoutItem]
    customer_name: str
    customer_email: str
    customer_phone: str = ""
    discount_code: Optional[str] = None
    # ESSAI-5a-1 : la seule chose que le client exprime.
    terms_accepted: Optional[bool] = None


# === ESSAI-1B : LE PRIX VIENT DU CATALOGUE, JAMAIS DU NAVIGATEUR ===
#
# `calculate_total` additionne les `price` envoyes par le client, puis soustrait
# un `discount_amount` lui aussi envoye par le client. Deux autorites metier
# confiees au navigateur : `price: 250` accompagne de `discount_amount: 250`
# donne un total nul, donc un checkout GRATUIT sur une offre payante. Et sur
# `/free`, un simple `price: 0` suffit a franchir la garde « ce chemin ne traite
# que le 0 CHF ».
#
# On relit donc le prix en base. Et si un article ne se rattache a AUCUNE offre
# du catalogue, on ne peut pas AFFIRMER qu'il est gratuit : le doute ne profite
# pas au client, la commande part du cote payant.
#
# `discount_amount` n'est plus consulte. Une remise reelle doit venir d'un code
# valide par le serveur — le mecanisme existe deja ailleurs et n'est pas
# reecrit ici.


async def _essai1b_prix_unitaire(item):
    """Rend (prix unitaire faisant autorite, a-t-il ete resolu en base ?).

    Non resolu = le catalogue ne connait pas cet article. On retombe alors sur
    le prix annonce, faute de mieux — mais l'appelant SAIT que la valeur n'est
    pas attestee, et refuse notamment de la declarer gratuite.
    """
    _d = item.dict() if hasattr(item, "dict") else dict(item)
    _oid = str(_d.get("id") or "").strip()
    if _oid:
        try:
            _o = await db["offers"].find_one(
                {"id": _oid}, {"_id": 0, "price": 1, "active_price": 1})
            if _o:
                _p = _o.get("active_price")
                if _p is None:
                    _p = _o.get("price")
                return float(_p or 0), True
        except Exception as _err:
            logger.warning(f"[ESSAI-1B] prix de l'offre {_oid} illisible: {_err}")
    return float(_d.get("price") or 0), False


async def _essai1b_total_autorite(items):
    """Rend (total calcule en base, tous les articles ont-ils ete resolus)."""
    _total = 0.0
    _tout_resolu = True
    for _it in (items or []):
        _d = _it.dict() if hasattr(_it, "dict") else dict(_it)
        _qte = max(1, int(_d.get("quantity") or 1))
        _prix, _resolu = await _essai1b_prix_unitaire(_it)
        if not _resolu:
            _tout_resolu = False
        _total += _prix * _qte
    return round(_total, 2), _tout_resolu


async def _essai1b_exiger_gratuit(items) -> None:
    """Refuse un chemin gratuit que le catalogue ne confirme pas."""
    _total, _resolu = await _essai1b_total_autorite(items)
    if not _resolu or _total > 0:
        raise HTTPException(
            status_code=400,
            detail="Cet endpoint ne traite que les offres gratuites (0 CHF).",
        )


# === ESSAI-1 : UN SEUL ESSAI GRATUIT PAR PERSONNE ===
#
# Le probleme n'est pas theorique. Rien, aujourd'hui, n'empeche de repasser dix
# fois dans le tunnel gratuit : ni index unique (la collection `subscriptions`
# n'en a aucun), ni garde applicative, ni idempotence. Chaque passage cree un
# forfait actif et un code AFR- de plus.
#
# CE QUI COMPTE COMME « ESSAI DEJA ACCORDE ». On ne se fie ni a `offer_name`
# (chaine libre, qui a deja derive en production), ni a `subscriptions.source`
# (« checkout_vitrine » aussi bien pour un essai que pour un pack a 250 CHF),
# ni au seul `offer_id` (ESSAI-0 ne l'ecrit que depuis peu, et les
# souscriptions anterieures n'en ont pas — il n'y a pas eu de backfill).
#
# On retient les DEUX marqueurs ecrits par du code, jamais par un humain :
#
#   1. `discount_codes.payment_method == "free"` ET `total_paid == 0`
#      — pose par `_process_successful_payment`, donc present sur TOUS les
#        essais de la vitrine, y compris les anciens, et sur les DEUX chemins
#        gratuits (`/free` et `/create-session` a total nul) ;
#   2. `discount_codes.source == "social_proof"`
#      — l'essai obtenu contre une preuve sociale en est un aussi.
#
# Un code offert par le coach (`source: "admin_manual"`) n'entre PAS dans le
# compte : c'est un geste commercial delibere, il ne doit pas bruler l'essai.
# Ces deux chemins n'ecrivent d'ailleurs ni `payment_method` ni `total_paid`,
# le filtre les ecarte donc naturellement.
#
# CE QU'ON NE PROMET PAS. L'identite est un e-mail que le visiteur saisit
# lui-meme : la route n'a aucune authentification. Cette garde arrete les
# doublons de bonne foi, les rejeux et les doubles clics. Elle n'arrete pas
# quelqu'un qui change d'adresse — et pretendre le contraire serait mentir.

ESSAI1_RAISON = "free_trial_already_used"
ESSAI1_MESSAGE = "Votre essai gratuit a déjà été utilisé."


async def _essai1_essai_deja_accorde(email: str) -> bool:
    """Cette adresse a-t-elle DEJA recu un essai gratuit ?

    En cas d'erreur de lecture on renvoie False : mieux vaut un second essai
    accorde par accident qu'un tunnel casse pour tout le monde parce que la
    base a hoquete. Le verrou d'unicite (voir plus bas) reste, lui, en place.
    """
    _e = (email or "").strip().lower()
    if not _e:
        return False
    try:
        _doc = await db["discount_codes"].find_one(
            {"assignedEmail": _e,
             "$or": [
                 {"payment_method": "free", "total_paid": 0},
                 {"source": "social_proof"},
             ]},
            {"_id": 1})
        return _doc is not None
    except Exception as _err:
        logger.warning(f"[ESSAI-1] lecture anti-double-essai impossible: {_err}")
        return False


async def _essai1_reclamer(email: str) -> bool:
    """Reserve l'essai de cette adresse, de facon ATOMIQUE.

    Deux requetes lancees a la meme milliseconde passeraient toutes deux une
    simple lecture — c'est arrive dans ce depot, documente a `shared.py:425`
    (« 7 MICROSECONDES d'ecart, double-clic a la creation »). On s'appuie donc
    sur la seule unicite garantie par MongoDB sans declarer d'index : la cle
    primaire. `_id` porte l'adresse normalisee ; le second inserteur se prend
    un doublon et repart les mains vides.

    Meme motif que le jeton BoostTribe (`server.py:10631`), qui utilise le
    `jti` du JWT comme `_id`.
    """
    _e = (email or "").strip().lower()
    if not _e:
        return True
    try:
        await db["free_trial_claims"].insert_one({
            "_id": "trial:" + _e,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return True
    except Exception as _err:
        if "duplicate" in str(_err).lower() or "E11000" in str(_err):
            return False
        # Toute autre panne : on ne bloque pas le tunnel sur une base capricieuse.
        logger.warning(f"[ESSAI-1] reservation d'essai impossible: {_err}")
        return True


async def _essai1_liberer(email: str) -> None:
    """Rend la reservation si la creation a echoue : sans cela, une panne au
    milieu du tunnel priverait la personne de son essai pour toujours."""
    _e = (email or "").strip().lower()
    if not _e:
        return
    try:
        await db["free_trial_claims"].delete_one({"_id": "trial:" + _e})
    except Exception as _err:
        logger.error(f"[ESSAI-1] reservation non liberee pour un essai echoue: {_err}")


async def _essai1_garde(email: str, offer_id: str = "") -> None:
    """Refuse un second essai. A appeler AVANT la moindre ecriture.

    Leve 409 avec un message lisible par un humain dans `detail` — le frontend
    l'affiche deja tel quel — et le motif machine dans un en-tete, pour qu'il
    puisse orienter vers les offres payantes sans analyser du francais.
    """
    if await _essai1_essai_deja_accorde(email):
        await _essai1_tracer_refus(offer_id)
        raise HTTPException(
            status_code=409,
            detail=ESSAI1_MESSAGE,
            headers={"X-Refus-Raison": ESSAI1_RAISON},
        )
    if not await _essai1_reclamer(email):
        await _essai1_tracer_refus(offer_id)
        raise HTTPException(
            status_code=409,
            detail=ESSAI1_MESSAGE,
            headers={"X-Refus-Raison": ESSAI1_RAISON},
        )


async def _essai1_tracer_refus(offer_id: str = "") -> None:
    """Un refus est un evenement de funnel, pas un incident.

    Aucune donnee personnelle : ni e-mail, ni nom, ni code. `offer_id` est un
    identifiant de catalogue, deja envoye par `pulse_purchased`. Non bloquant :
    la mesure ne doit jamais empecher une reponse.
    """
    try:
        from api.routes.shared import posthog_capture as _ph
        await _ph("trial_refused", email="", props={
            "reason": "already_used",
            "offer_id": (offer_id or "")[:64],
        })
    except Exception:
        pass


@router.post("/free")
async def free_checkout(req: FreeCheckoutRequest):
    """V249 — checkout d'une offre GRATUITE (0 CHF), de bout en bout.

    Aligne le flux gratuit sur le flux payant : jusqu'ici la vitrine (App.js)
    faisait un simple POST /reservations qui ne creait NI souscription NI code
    d'acces — le client recevait un message promettant un « code AFR- » qui
    n'existait pas et restait bloque sur /chat.

    Cet endpoint reutilise `_process_successful_payment` (souscription + code
    AFR- + email avec lien de reservation) puis complete par la
    payment_transaction, la notif push au coach et le contact — exactement ce
    que produit le webhook Stripe pour un achat payant.
    """
    # garde-fou : on refuse un item non gratuit ici, ce chemin est reserve au
    # 0 CHF. ESSAI-1B : le prix est relu EN BASE — additionner les `price` du
    # client laissait passer une offre a 250 CHF annoncee a 0.
    # ESSAI-5a-1 — les conditions d'abord, avant meme la verification de
    # gratuite : un refus ici ne laisse rien derriere lui.
    _t1_champs = await _t1_preuve_checkout(req.terms_accepted, req.items,
                                           req.coach_email)
    await _essai1b_exiger_gratuit(req.items)
    if not req.customer_email or "@" not in req.customer_email:
        raise HTTPException(status_code=400, detail="Email client requis.")

    # ESSAI-1 : ici, et pas ailleurs. `_process_successful_payment` cree le code
    # AFR- et le forfait des ses premieres lignes ; toute verification posee
    # apres arriverait devant un essai deja accorde.
    await _essai1_garde(req.customer_email,
                        str((req.items[0].id if req.items else "") or ""))

    transaction_id = f"free_{uuid.uuid4().hex[:12]}"
    try:
        result = await _process_successful_payment(
            terms_fields=_t1_champs,
            transaction_id=transaction_id,
            coach_email=req.coach_email,
            customer_name=req.customer_name,
            customer_email=req.customer_email,
            customer_phone=req.customer_phone,
            items=req.items,
            total=0,
            currency="CHF",
            payment_method="free",
            discount_code=req.discount_code,
        )
    except Exception:
        # Idem : une panne au milieu du tunnel ne doit pas confisquer l'essai.
        await _essai1_liberer(req.customer_email)
        raise
    # ESSAI-1A : `access_code` n'est volontairement PAS relu ici — il ne doit
    # plus quitter le serveur par HTTP, seulement par l'e-mail du titulaire.
    product_name = (result or {}).get("product_name", "Offre gratuite")

    now_iso = datetime.now(timezone.utc).isoformat()

    # payment_transaction (montant 0, deja payee) — pour que la vente gratuite
    # apparaisse dans l'onglet Transactions au meme titre qu'une vente payante.
    try:
        await db["payment_transactions"].insert_one({
            "id": str(uuid.uuid4()),
            "session_id": transaction_id,
            "amount": 0,
            "currency": "chf",
            "product_name": product_name,
            "customer_email": req.customer_email.lower().strip(),
            "coach_id": req.coach_email,
            "payment_status": "paid",
            "status": "completed",
            "payment_method": "free",
            "metadata": {"customer_name": req.customer_name,
                         "customer_email": req.customer_email,
                         "product_name": product_name},
            "created_at": now_iso,
            "webhook_received_at": now_iso,
        })
    except Exception as _pt_err:
        logger.warning(f"[V249] payment_transaction gratuite non-bloquant: {_pt_err}")

    # notif push au coach (non bloquant) — import lazy, comme V248.
    try:
        from api.server import send_push_by_email as _push
        await _push(req.coach_email, "Nouvelle souscription",
                    f"{req.customer_name or 'Un client'} s'est inscrit à {product_name} (gratuit)")
    except Exception as _push_err:
        logger.warning(f"[V249] push gratuit non-bloquant: {_push_err}")

    # contact CRM (non bloquant) — coach_id en $setOnInsert pour ne pas
    # reattribuer un contact existant.
    try:
        _cset = {"email": req.customer_email.lower().strip(),
                 "name": req.customer_name or req.customer_email.split("@")[0],
                 "source": "free_checkout", "updated_at": now_iso}
        if req.customer_phone:
            _cset["phone"] = req.customer_phone
        await db["chat_participants"].update_one(
            {"email": req.customer_email.lower().strip()},
            {"$set": _cset,
             "$setOnInsert": {"id": str(uuid.uuid4()), "coach_id": req.coach_email, "created_at": now_iso}},
            upsert=True,
        )
    except Exception as _c_err:
        logger.warning(f"[V249] contact gratuit non-bloquant: {_c_err}")

    # ESSAI-2 : l'entree du funnel. Elle n'etait pas mesuree : on savait
    # combien de gens cliquaient et combien reservaient, jamais combien
    # obtenaient reellement un acces.
    try:
        from api.routes.shared import essai2_tracer_octroi as _e2_octroi
        await _e2_octroi(db, req.customer_email,
                         str((req.items[0].id if req.items else "") or ""),
                         int((result or {}).get("sessions_count") or 0))
    except Exception as _e2err:
        logger.warning(f"[ESSAI-2] octroi non mesure: {_e2err}")

    # ESSAI-1A : le code AFR- ne repart PLUS dans la reponse HTTP.
    #
    # Cette route n'a aucune authentification : l'adresse est celle que le
    # visiteur ecrit lui-meme. Renvoyer le code revenait donc a le remettre a
    # QUICONQUE saisit l'adresse d'un tiers. Il part desormais par le seul
    # canal qui atteste de la possession de l'adresse : l'e-mail.
    #
    # Le parcours legitime ne change pas d'un pixel — la vitrine ne lisait pas
    # ce champ, et son message dit deja « Consultez votre email pour recevoir
    # votre QR code et code d'acces AFR ».
    return {
        "success": True,
        "free": True,
        "transaction_id": transaction_id,
        "message": "Réservation confirmée gratuitement !",
    }


# ===== WEBHOOKS =====

@router.post("/webhook/stripe")
async def checkout_stripe_webhook(request: Request):
    """Webhook Stripe pour les paiements vitrine (checkout unifié)"""
    import stripe as stripe_lib

    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    # V428B — VERIFICATION DE SIGNATURE, EN FAIL-CLOSED.
    #
    # Cette URL est la SEULE declaree chez Stripe (endpoint dont le signing
    # secret se termine par « XmuY »). Elle acceptait jusqu'ici n'importe quel
    # POST anonyme : `sig` etait lue puis JAMAIS utilisee. Un evenement forge
    # etait relaye au gestionnaire client via `request.state` — chemin qui saute
    # volontairement la verification (server.py:5481) — donc code AFR-*, e-mail
    # et abonnement crees SANS aucun paiement.
    #
    # `STRIPE_WEBHOOK_SECRET_CHECKOUT` est bien le secret de CET endpoint :
    # suffixe `XmuY`, verifie au tableau de bord Stripe ET dans l'environnement
    # du conteneur de production. Le commentaire de server.py:5492, qui pretend
    # qu'elle porte le secret de /api/webhook/stripe, est FAUX.
    #
    # FAIL-CLOSED assume : un webhook de paiement ne doit jamais devenir anonyme
    # parce qu'une variable manque. 503 et non 500, car Stripe reessaie les 5xx
    # pendant plusieurs jours : une mauvaise configuration se rattrape, une
    # faille silencieuse non.
    #
    # Ce bloc est un PORTILLON : `event_data` reste produit par `json.loads`
    # ci-dessous, donc aucune ligne en aval ne change — ni la branche vitrine,
    # ni le relais, ni `invoice.upcoming`.
    _wh_secret = os.environ.get("STRIPE_WEBHOOK_SECRET_CHECKOUT")
    if not _wh_secret:
        logger.error(
            "[CHECKOUT-WEBHOOK] V428B REFUS : STRIPE_WEBHOOK_SECRET_CHECKOUT "
            "absent du runtime. Aucun evenement traite. Poser le signing secret "
            "de l'endpoint /api/checkout/webhook/stripe (Stripe > Webhooks)."
        )
        raise HTTPException(status_code=503, detail="Webhook non configuré")
    try:
        _evt = stripe_lib.Webhook.construct_event(payload, sig, _wh_secret)
        logger.info(
            f"[CHECKOUT-WEBHOOK] V428B signature valide "
            f"(id={getattr(_evt, 'id', '?')}, type={getattr(_evt, 'type', '?')})"
        )
    except Exception as _sig_err:
        # On journalise le TYPE de l'exception, jamais son message : celui-ci
        # peut contenir la signature recue.
        logger.warning(
            f"[CHECKOUT-WEBHOOK] V428B signature INVALIDE, rejet — "
            f"{type(_sig_err).__name__} (corps : {len(payload)} o)"
        )
        raise HTTPException(status_code=400, detail="Signature invalide")

    try:
        event_data = json.loads(payload)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payload")

    # V404 — RAPPEL AVANT DEBIT : `invoice.upcoming` est transmis au gestionnaire
    # client, qui porte le texte valide (V400) et la seule brique d'envoi du parc
    # (Resend). Le LIVE, lui, n'a ni Resend ni SMTP ni push : c'est donc afroboost
    # qui porte le rappel pour les deux — option (b) retenue par le proprietaire.
    #
    # ⚠️ SANS CE BLOC, RIEN N'ARRIVE. Cette URL est la seule declaree chez Stripe
    # pour afroboost, et elle ne deleguait QUE `checkout.session.completed` : un
    # `invoice.upcoming` y serait tombe dans le vide avec un 200, exactement le
    # piege du paiement perdu de V384.
    if event_data.get("type") == "invoice.upcoming":
        from api.server import stripe_webhook as _webhook_client
        request.state.afroboost_event_verifie = event_data
        resultat = await _webhook_client(request)
        logger.info("[CHECKOUT-WEBHOOK] V404 invoice.upcoming transmis au rappel")
        return resultat

    if event_data.get("type") == "checkout.session.completed":
        session = event_data["data"]["object"]
        metadata = session.get("metadata", {})

        if metadata.get("type") != "vitrine_purchase":
            # ================= V384 — CAUSE RACINE D'UN PAIEMENT PERDU =================
            # C'est CETTE URL qui est déclarée dans le tableau de bord Stripe
            # (https://afroboost.com/api/checkout/webhook/stripe), et elle ne sait
            # traiter QUE les achats vitrine. Pour tout le reste — les achats
            # clients, l'immense majorité — elle répondait « ignored » avec un
            # HTTP **200**. Stripe considérait donc la livraison RÉUSSIE, ne
            # réessayait pas, et le paiement n'était jamais honoré : aucun code,
            # aucune souscription, aucun e-mail, aucune notification. Silencieux
            # des deux côtés. C'est ce qui est arrivé le 5 août 2026 à un
            # paiement client de 150 CHF (113 transactions en base, 7 seulement
            # avec `webhook_received_at`, et ces 7 rattrapées à la main).
            #
            # Le vrai gestionnaire existe et fonctionne : `/api/webhook/stripe`
            # (api/server.py). Il n'est simplement PAS déclaré chez Stripe. On lui
            # transmet donc l'événement ici, plutôt que de dépendre d'une
            # configuration externe qu'un déploiement ne peut ni vérifier ni
            # corriger.
            #
            # Import TARDIF : `api.server` importe déjà ce module, un import en
            # tête de fichier créerait un cycle. Même motif que `payment_activation`
            # avec `boost_routes`.
            #
            # `request` est relisible : Starlette met le corps en cache après le
            # premier `await request.body()` — le gestionnaire principal le relit
            # sans que le flux soit consommé.
            # L'événement est transmis PAR L'ÉTAT de la requête, et non relu :
            # Stripe l'a signé avec le secret de CET endpoint, pas avec celui
            # qu'attend le gestionnaire client. Le lui faire re-vérifier
            # renverrait 400 sur chaque paiement (voir V384 dans server.py).
            from api.server import stripe_webhook as _webhook_client
            request.state.afroboost_event_verifie = event_data
            resultat = await _webhook_client(request)
            logger.info(
                f"[CHECKOUT-WEBHOOK] Evenement non-vitrine transmis au "
                f"gestionnaire client: {metadata.get('product_name', '')}"
            )
            return resultat

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
            terms_fields=(txn or {}).get("terms_fields") or {},
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
    discount_code: str = None,
    terms_fields: dict = None
):
    """Traite un paiement réussi : réservation, code accès, QR, notifications

    ESSAI-5a-1 — `terms_fields` porte la preuve d'acceptation deja etablie par
    l'appelant. Elle est recopiee sur les reservations creees ici, sans etre
    re-jugee : la decision a ete prise en amont, avant toute ecriture.
    """

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

    # V216: Calculer le nombre de séances depuis les items
    # V260c — LE PACK DE L'OFFRE FAIT DESORMAIS FOI.
    # Ce calcul ne connaissait que la regex « x10 » sur le NOM de l'article :
    # elle date de la V216, avant l'existence du champ `pack_sessions` (V223).
    # Un pack de 10 seances nomme « Abonnement Decouverte » n'y correspondait
    # pas et le client repartait avec UNE seance. Le webhook Stripe, lui, avait
    # bien ete mis a jour en V223 — les deux chemins de paiement divergeaient
    # donc sur le meme achat.
    # L'article porte un `id` (CheckoutItem.id) : quand il resout une offre
    # declarant `pack_sessions`, cette valeur prime. La regex reste le repli
    # EXACT d'avant pour les articles sans id ou sans pack declare : rien ne
    # change pour eux.
    import re as _re_checkout
    sessions_count = 0
    items_product_name = ""
    # ESSAI-0 : on RETIENT aussi l'identifiant de l'article, pas seulement son nom.
    # `db.subscriptions` ne portait jusqu'ici que `offer_name` — une chaine libre,
    # qui a DEJA derive en production : les deux libelles des essais historiques
    # (« Essai gratuit! », « Cours gratuit! ») ne correspondent plus a aucune offre
    # du catalogue. Toute regle metier batie dessus se desarmerait en silence au
    # prochain renommage. On persiste donc l'identifiant stable.
    #
    # PORTEE : la souscription n'est creee qu'ICI, dans ce helper partage. Y ajouter
    # le champ est donc la seule facon d'en doter les achats gratuits ; le restreindre
    # a un appelant demanderait un `if` artificiel, pour aucun gain. Le champ est
    # purement ADDITIF et n'est lu par personne aujourd'hui : aucun appelant ne
    # change de comportement.
    #
    # AUCUN BACKFILL : les 54 souscriptions existantes restent sans `offer_id`. Ce
    # n'est pas un manque — la future garde anti-double-essai ne bloque que sur un
    # essai VALIDE, et il n'en existe aucun. Toute preuve qu'elle lira sera creee
    # a partir de maintenant.
    items_offer_id = ""
    for item in items:
        item_data = item.dict() if hasattr(item, 'dict') else item
        item_name = item_data.get("name", "")
        item_qty = int(item_data.get("quantity", 1))
        if not items_product_name:
            items_product_name = item_name
            # Meme article que le nom retenu : les deux decrivent la meme ligne.
            items_offer_id = str(item_data.get("id") or "").strip()

        item_pack = None
        item_id = item_data.get("id")
        if item_id:
            try:
                _offer_doc = await db["offers"].find_one(
                    {"id": item_id}, {"_id": 0, "pack_sessions": 1}
                )
                _ps = (_offer_doc or {}).get("pack_sessions")
                # `int(...)` et non `isinstance` : une valeur stockee en 10.0 ou
                # "10" doit compter comme un pack de 10, pas etre ignoree.
                if _ps is not None and int(float(_ps)) > 0:
                    item_pack = int(float(_ps))
            except (TypeError, ValueError):
                item_pack = None
            except Exception as _pack_err:
                # Lecture impossible : on retombe sur la regex plutot que de
                # faire echouer un paiement deja encaisse.
                logger.warning(f"[V260c] Lecture pack_sessions de l'offre {item_id} echouee: {_pack_err}")
                item_pack = None

        if item_pack:
            sessions_count += item_pack * item_qty
        else:
            # Chercher "x10", "x5", etc. dans le nom
            x_match = _re_checkout.search(r'x\s*(\d+)', item_name, _re_checkout.IGNORECASE)
            if x_match:
                sessions_count += int(x_match.group(1)) * item_qty
            else:
                sessions_count += item_qty
    if sessions_count <= 0:
        sessions_count = 1

    # 3. Stocker le code dans discount_codes (champs compatibles avec subscriber check)
    await db["discount_codes"].insert_one({
        "id": str(uuid.uuid4()),
        "code": access_code,
        "name": customer_name,
        "coach_id": coach_email,
        "assignedEmail": customer_email.lower().strip(),
        "type": "100%",
        "value": 100,
        "maxUses": sessions_count,
        "used": 0,
        "active": True,
        "courses": [],
        "source": "checkout_payment",
        "transaction_id": transaction_id,
        "payment_method": payment_method,
        "total_paid": total,
        "currency": currency,
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    # V216: Créer la subscription (suivi séances restantes)
    subscription_id = str(uuid.uuid4())
    await db["subscriptions"].insert_one({
        "id": subscription_id,
        "email": customer_email.lower().strip(),
        "name": customer_name,
        "whatsapp": customer_phone or "",  # V251: evite de redemander le numero dans l'espace abonne
        "code": access_code,
        "offer_name": items_product_name or "Achat Afroboost",
        # ESSAI-0 : identifiant STABLE de l'offre, a cote du nom (qui, lui, derive).
        "offer_id": items_offer_id,
        "total_sessions": sessions_count,
        "used_sessions": 0,
        "remaining_sessions": sessions_count,
        # V397 : +2 mois, JAMAIS nul — même règle que Stripe et Mobile Money.
        "expires_at": _v397_expiration(),
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "checkout_vitrine",
        "coach_id": coach_email,
        "auto_renew": False,
        "renewal_price": total,
        "renewal_sessions": sessions_count,
        "renewal_warnings_sent": [],
    })
    logger.info(f"[CHECKOUT] Code {access_code} + subscription crees pour {customer_email} ({sessions_count} seances)")

    # V397 : ferme l'ancien forfait (expiré ou épuisé) du même client. Non bloquant :
    # le paiement est déjà encaissé, une erreur ici ne doit rien faire échouer.
    try:
        _fermes = await _v397_cloturer(db, customer_email, subscription_id, log_prefix="V397-VITRINE")
        if _fermes:
            logger.info(f"[V397-VITRINE] {len(_fermes)} ancien(s) forfait(s) ferme(s) pour {customer_email}")
    except Exception as _e397:
        logger.warning(f"[V397-VITRINE] Cloture ignoree: {_e397}")

    # 4. Créer les réservations pour chaque item de type "course"
    for item in items:
        item_data = item.dict() if hasattr(item, 'dict') else item
        if item_data.get("type") == "course":
            _resa_doc = {
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
                "promoCode": access_code,
                "discountCode": access_code,
                "subscriptionId": subscription_id,
                "status": "confirmed",
                "payment_method": payment_method,
                "transaction_id": transaction_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "isProduct": item_data.get("type") == "product"
            }
            # ESSAI-5a-1 : la preuve suit la reservation qu'elle couvre.
            _resa_doc.update(terms_fields or {})
            await db["reservations"].insert_one(_resa_doc)

    # 5. QR Code URL
    qr_url = f"https://afroboost.com/?qr={access_code}"
    qr_image_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={qr_url}"

    # 6. Envoyer les notifications par email
    try:
        import resend
        resend_key = os.environ.get("RESEND_API_KEY", "")
        if resend_key:
            resend.api_key = resend_key

            # V259: couleur de marque relue en base (un email ne lit pas les variables CSS)
            primary_color = await get_primary_color(db)
            primary_rgb = hex_to_rgb_triplet(primary_color)

            items_desc = ", ".join([
                f"{(i.dict() if hasattr(i, 'dict') else i).get('name', 'Article')} x{(i.dict() if hasattr(i, 'dict') else i).get('quantity', 1)}"
                for i in items
            ])

            # Email au client
            try:
                resend.Emails.send({
                    "from": "Afroboost <notifications@afroboost.com>",
                    "to": [customer_email],
                    "subject": f"✅ Confirmation de votre achat - {access_code}",
                    "html": f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #1a1a2e; color: white; padding: 30px; border-radius: 12px;">
                        <h1 style="color: {primary_color}; text-align: center;">🎉 Merci pour votre achat !</h1>
                        <p>Bonjour <strong>{customer_name}</strong>,</p>
                        <p>Votre paiement de <strong>{total} {currency}</strong> a été confirmé.</p>
                        <div style="background: rgba({primary_rgb}, 0.1); border: 1px solid {primary_color}; border-radius: 8px; padding: 20px; margin: 20px 0; text-align: center;">
                            <p style="color: {primary_color}; font-size: 14px; margin: 0 0 10px 0;">Votre Code d'Accès</p>
                            <p style="font-size: 28px; font-weight: bold; color: white; margin: 0; letter-spacing: 3px;">{access_code}</p>
                        </div>
                        <div style="text-align: center; margin: 20px 0;">
                            <img src="{qr_image_url}" alt="QR Code" style="width: 150px; height: 150px;" />
                            <p style="color: rgba(255,255,255,0.6); font-size: 12px;">Scannez ce QR code pour accéder à vos services</p>
                        </div>
                        <!-- V248: bouton de reservation MANQUANT — le client recevait un
                             code mais aucun lien pour reserver sa seance, et devait
                             recopier le code a la main (source d'erreurs de saisie).
                             Meme espace que le flow Stripe : /espace/{{code}}. -->
                        <div style="text-align: center; margin: 24px 0;">
                            <a href="https://afroboost.com/espace/{access_code}" style="display: inline-block; background: {primary_color}; color: white; padding: 16px 36px; text-decoration: none; border-radius: 12px; font-weight: bold; font-size: 16px;">&#128197; Réserver ma séance</a>
                            <p style="color: rgba(255,255,255,0.5); font-size: 12px; margin: 10px 0 0;">Ton espace personnel : choisis ta date et confirme en un clic.</p>
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
                    "from": "Afroboost <notifications@afroboost.com>",
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
    # V249: on renvoie le code + les infos utiles pour que l'appelant (endpoint
    # /free) puisse creer la payment_transaction, notifier le coach et rattacher
    # le contact — sans dupliquer la generation du code.
    return {"access_code": access_code, "sessions_count": sessions_count,
            "product_name": items_product_name or "Achat Afroboost"}
