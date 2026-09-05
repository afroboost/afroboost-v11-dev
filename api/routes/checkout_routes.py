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
    # R2b — FACULTATIF DESORMAIS, ET C'EST UN DURCISSEMENT, pas un
    # relachement. Le navigateur n'a plus l'e-mail du coach (retire de la
    # sortie publique de `/offers`), et il n'a jamais eu a etre l'autorite sur
    # le destinataire d'un paiement : le serveur le lit dans le catalogue
    # (`_r2b_vendeur_si_absent`). Une valeur encore fournie reste verifiee a
    # l'identique par `_lot2_verifier_vendeur`.
    coach_email: str = ""  # Vendeur (qui reçoit l'argent) — resolu si absent
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

    # LOT 2 : le vendeur declare a-t-il le droit de vendre ces articles ? Pose
    # AVANT le calcul du total et avant la branche gratuite — donc avant la
    # premiere ecriture, quelle que soit la suite du parcours.
    # R2b — SI LE CLIENT NE DIT PLUS QUI VEND, LE SERVEUR LE LIT.
    await _r2b_vendeur_si_absent(req)
    await _lot2_verifier_vendeur(req.items, req.coach_email)

    # LOT R : une offre reservee aux membres se refuse ici aussi. Meme
    # placement que la garde du vendeur — avant le total, avant la branche
    # gratuite, donc avant la premiere ecriture. Poser cette garde sur une
    # seule des portes la rendrait contournable en changeant d'URL : c'est
    # exactement le raisonnement qui a place ESSAI-1 et ESSAI-4 ici.
    await _lotr_garde(req.items, req.customer_email)

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
        # ESSAI-4 : meme garde sur la seconde porte gratuite. La poser sur une
        # seule des deux la rendrait contournable en changeant d'URL — le meme
        # raisonnement qui a place ESSAI-1 ici.
        await _essai4_garde(req.customer_email,
                            str((req.items[0].id if req.items else "") or ""))
        # ESSAI-6 : le numero est le SECOND critere d'identite. `customer_phone`
        # existe deja sur cette requete — aucun champ nouveau. Absent, la garde
        # retombe exactement sur son comportement e-mail d'avant.
        await _essai1_garde(req.customer_email,
                            str((req.items[0].id if req.items else "") or ""),
                            telephone=req.customer_phone)
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
            await _essai1_liberer(req.customer_email,
                                  telephone=req.customer_phone)
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
    # R2b : meme raison que sur `CreateCheckoutRequest` — resolu cote serveur.
    coach_email: str = ""
    items: List[CheckoutItem]
    customer_name: str
    customer_email: str
    customer_phone: str = ""
    discount_code: Optional[str] = None
    # ESSAI-5a-1 : la seule chose que le client exprime.
    terms_accepted: Optional[bool] = None
    # M2-A : l'origine marketing, telle que le navigateur l'a memorisee.
    # OPTIONNELLE et NON FIABLE : elle est re-validee cote serveur contre une
    # liste fermee (`m2a_bloc_propre`) avant la moindre ecriture. Son absence
    # n'empeche jamais un essai — c'est du suivi, pas une condition.
    attribution: Optional[dict] = None


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


# ============================================================================
# LOT 2 — LE VENDEUR DECLARE DOIT ETRE CELUI DE L'OFFRE
# ============================================================================
#
# LA FAILLE FERMEE ICI. `coach_email` est un champ libre du corps de requete.
# Il n'etait confronte a RIEN : ni au proprietaire de l'offre achetee, ni a une
# identite serveur. ESSAI-1B avait bien retire le PRIX au navigateur en le
# relisant en base — mais sa projection ne demande que `price` et
# `active_price`, jamais `coach_id`. Aucune ligne de ce fichier ne comparait le
# vendeur declare au proprietaire reel.
#
# Consequence, avant ce lot : un POST sur `/checkout/free` declarant
# `coach_email: "<coach B>"` avec l'identifiant d'une offre du coach A creait un
# code d'acces, un forfait, une reservation, une transaction et un contact CRM
# ATTRIBUES AU COACH B. Le coach B voyait apparaitre un client qu'il n'a jamais
# vendu ; le coach A ne le voyait pas. Et demain, une adhesion.
#
# IMPACT REEL A CE JOUR : NUL — il n'y a qu'un seul compte coach en base. C'est
# precisement pour cela qu'on la ferme maintenant, pendant qu'elle ne coute
# rien, et non le jour ou un partenaire arrive.
#
# LA REGLE, FAIL CLOSED :
#   * l'offre a un proprietaire reel -> le vendeur declare doit etre LUI ;
#   * l'offre n'a pas de proprietaire (les 8 offres de production sont dans ce
#     cas) -> le vendeur declare doit etre vide, ou un super-admin. Ces deux
#     valeurs sont exactement celles que les deux ecrans de l'application
#     envoient aujourd'hui (`App.js` -> "", `CoachVitrine.js` -> l'adresse de
#     l'admin) : la garde ferme la faille SANS casser un parcours existant.
#     Ce qu'elle refuse desormais, c'est un partenaire qui revendiquerait une
#     offre qui n'est pas la sienne.
#   * l'offre est introuvable -> on ne tranche pas, on laisse passer : le
#     panier peut contenir un article libre, et ce n'est pas le role de cette
#     garde d'en decider. Le prix, lui, est deja traite par ESSAI-1B.
#
# CE QU'ELLE NE FAIT PAS. Elle ne change AUCUN `coach_id` ecrit en base et ne
# touche pas au routage de l'argent : `coach_email` continue de choisir le
# compte de paiement via `get_payment_keys`. Elle verifie seulement qu'il a le
# DROIT d'etre celui-la.

LOT2_MSG_VENDEUR = ("Cette offre n'appartient pas au vendeur indiqué. "
                    "Rechargez la page et réessayez.")


async def _r2b_resoudre_vendeur(items) -> str:
    """LE VENDEUR SE LIT DANS LE CATALOGUE, PAS DANS LA REQUETE. R2b.

    POURQUOI CETTE FONCTION EXISTE. `coach_id` etant l'adresse e-mail du coach,
    R2b l'a retiree de la sortie publique de `/offers`. Or le navigateur la
    renvoyait au serveur pour dire QUI RECOIT L'ARGENT — ce qui etait deja une
    mauvaise idee : le client n'a pas a etre l'autorite sur le destinataire
    d'un paiement. Le serveur sait le lire lui-meme, et `_lot2_verifier_vendeur`
    faisait deja exactement cette lecture pour la CONTROLER.

    ELLE NE DEVINE RIEN. Elle lit `offers.coach_id` sur le premier article qui
    en porte un. Aucun article vendeur -> chaine vide, et le comportement
    d'avant (proprietaire absent = super-admin) s'applique tel quel plus bas.
    """
    for _it in (items or []):
        _d = _it.dict() if hasattr(_it, "dict") else dict(_it)
        _oid = str(_d.get("id") or "").strip()
        if not _oid:
            continue
        try:
            _o = await db["offers"].find_one({"id": _oid}, {"_id": 0, "coach_id": 1})
        except Exception as _err:  # noqa: BLE001
            logger.warning(f"[R2b] proprietaire de l'offre {_oid[:32]} illisible: {_err}")
            continue
        _reel = str((_o or {}).get("coach_id") or "").strip().lower()
        if _reel:
            return _reel
    return ""


async def _r2b_vendeur_si_absent(req) -> None:
    """Repose le vendeur sur la requete quand le client ne l'a pas dit. R2b.

    ELLE EST POSEE SUR LES DEUX PORTES DE PAIEMENT. N'en couvrir qu'une la
    rendrait contournable en changeant d'URL — c'est le raisonnement qui a deja
    place ESSAI-1, ESSAI-4 et la garde du vendeur aux deux endroits.

    ELLE N'OUVRE RIEN. Un client qui declare encore un vendeur n'est pas touche
    et reste verifie a l'identique par `_lot2_verifier_vendeur`.
    """
    if str(getattr(req, "coach_email", "") or "").strip():
        return
    _vendeur = await _r2b_resoudre_vendeur(getattr(req, "items", None))
    if _vendeur:
        req.coach_email = _vendeur
        logger.info("[R2b] vendeur resolu depuis le catalogue (%d article(s))",
                    len(getattr(req, "items", None) or []))


async def _lot2_verifier_vendeur(items, coach_email: str):
    """Refuse (403) si le vendeur declare ne peut pas vendre l'un des articles."""
    _declare = str(coach_email or "").strip().lower()
    for _it in (items or []):
        _d = _it.dict() if hasattr(_it, "dict") else dict(_it)
        _oid = str(_d.get("id") or "").strip()
        if not _oid:
            continue
        try:
            _o = await db["offers"].find_one({"id": _oid}, {"_id": 0, "coach_id": 1})
        except Exception as _err:
            logger.warning(f"[LOT2] proprietaire de l'offre {_oid[:32]} illisible: {_err}")
            continue
        if not _o:
            continue
        _reel = str(_o.get("coach_id") or "").strip().lower()
        if _reel:
            _ok = (_declare == _reel)
        else:
            _ok = (not _declare) or is_super_admin(_declare)
        if not _ok:
            logger.warning("[LOT2] REFUS vendeur — offre=%s proprietaire=%r declare=%r",
                           _oid[:32], _reel or "(aucun)", _declare or "(vide)")
            raise HTTPException(status_code=403, detail=LOT2_MSG_VENDEUR)


async def _lotr_garde(items, customer_email: str) -> None:
    """LOT R — refuse un panier qui contient une offre reservee aux membres.

    LEVE 403 AVEC LE MOTIF, jamais un refus muet : le client doit savoir s'il
    doit terminer ses seances, ouvrir son adhesion, ou la renouveler. Trois
    situations, trois phrases — c'est la decision du proprietaire.

    CHAQUE ARTICLE EST EXAMINE. Un panier melange (une offre libre + la
    recharge) ne doit pas passer parce que le premier article etait innocent.

    LA GARDE ELLE-MEME EST FAIL-CLOSED (`lotr_garde_achat` refuse sur toute
    panne de base). Seul l'echec de son IMPORT laisse passer : casser la caisse
    entiere pour un module absent serait pire que le trou qu'on ferme, et
    l'immense majorite des offres ne sont pas protegees.
    """
    try:
        from api.routes.shared import (lotr_garde_achat as _garde,
                                       lotr_message_refus as _msg)
    except Exception as _err:  # noqa: BLE001
        logger.error("[LOT R] garde indisponible, achat poursuivi: %s", _err)
        return
    for _it in (items or []):
        _oid = str(getattr(_it, "id", "") or "").strip()
        if not _oid:
            continue
        _ok, _motif = await _garde(db, customer_email or "", _oid)
        if not _ok:
            logger.info("[LOT R] panier refuse — offre=%s motif=%s",
                        _oid[:32], _motif)
            raise HTTPException(status_code=403, detail=_msg(_motif))


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


async def _essai1_motif_refus(email: str, telephone: str = "", coach_id=None):
    """`(raison, message)` si le droit a l'essai est ferme, `(None, None)` sinon.

    LES DEUX FERMETURES NE SE VALENT PAS, et les confondre priverait le client
    de la seule information qui lui permet d'agir :
      * CONSOMME   — il est venu. Il n'y aura pas d'autre essai.
      * DEJA DETENU — il en a un qui l'attend. Ce n'est pas un refus d'abus,
        c'est un renvoi vers son propre droit.
    L'ordre compte : « consomme » est le fait le plus definitif, il passe en
    premier. Quelqu'un qui est venu ET qui detiendrait encore un credit doit
    lire « deja utilise », pas « va l'utiliser ».
    """
    from api.routes.shared import (essai6_consomme as _consomme,
                                   essai6_reutilisable as _reutilisable,
                                   ESSAI6_REFUS_CONSOMME as _R_CONSOMME,
                                   ESSAI6_REFUS_DEJA_DETENU as _R_DETENU,
                                   ESSAI6_MESSAGE_CONSOMME as _M_CONSOMME,
                                   ESSAI6_MESSAGE_DEJA_DETENU as _M_DETENU)
    if await _consomme(db, email, telephone, coach_id):
        return _R_CONSOMME, _M_CONSOMME
    if await _reutilisable(db, email, telephone, coach_id):
        return _R_DETENU, _M_DETENU
    return None, None


async def _essai1_essai_deja_accorde(email: str, telephone: str = "",
                                     coach_id=None) -> bool:
    """Le droit a l'essai est-il ferme pour cette personne ?

    CONSERVEE, ET PAS PAR NOSTALGIE : c'est la formulation de l'INVARIANT du
    lot G1/G2 — « deposer ou se faire refuser une demande de preuve sociale ne
    consomme JAMAIS le droit a l'essai ». Cet invariant se verifie en posant
    exactement cette question, et il reste vrai apres ESSAI-6. Seule sa
    composition a change : elle vaut desormais « consomme OU deja detenu »,
    et elle connait le telephone.

    En cas de base muette, `essai6_consomme` rend None : on repond donc False —
    le tunnel ne se ferme pas sur un hoquet, et le verrou atomique reste, lui,
    en place.
    """
    _raison, _ = await _essai1_motif_refus(email, telephone, coach_id)
    return _raison is not None


def _essai1_cles(email: str, telephone: str = "", coach_id=None) -> list:
    """Les cles de verrou de cette personne : l'adresse, et le numero s'il existe.

    LA PORTEE EST LE PROPRIETAIRE, PAS LA PLANETE. Sans proprietaire — le cas de
    TOUTE la production aujourd'hui, les huit offres portant `coach_id: null` —
    la cle reste `trial:{email}`, MOT POUR MOT celle des six verrous deja poses
    le 18/08. Aucun d'eux ne devient orphelin, et il n'y a donc rien a migrer.
    Un partenaire identifie, lui, obtient son propre espace de cles : son essai
    ne ferme pas le droit chez un autre coach.
    """
    from api.routes.shared import (normaliser_email as _norm_mail,
                                   essai6_normaliser_tel as _norm_tel)
    _prefixe = ""
    if isinstance(coach_id, str) and coach_id.strip():
        _prefixe = coach_id.strip().lower() + ":"
    _cles = []
    _mail = _norm_mail(email)
    if _mail:
        _cles.append("trial:" + _prefixe + _mail)
    _tel = _norm_tel(telephone)
    if _tel:
        _cles.append("trialtel:" + _prefixe + _tel)
    return _cles


async def _essai1_reclamer(email: str, telephone: str = "", coach_id=None) -> bool:
    """Reserve l'essai de cette personne, de facon ATOMIQUE. Sur TOUTES ses cles.

    POURQUOI PAS UN SIMPLE `insert_one`. C'etait le motif d'avant, et il ne
    tient plus : depuis ce lot, un verrou peut exister alors que la personne a
    de nouveau droit a un essai (son precedent n'a jamais ete consomme et n'est
    plus utilisable — code supprime, forfait expire). Un `insert_one` lui
    repondrait « doublon » et la banniraient a vie pour un droit qu'elle n'a
    jamais exerce.

    LE MOTIF RETENU garde l'atomicite SANS ce defaut : un `find_one_and_update`
    filtre sur `actif != True`, en `upsert`. Sur un verrou absent, il insere ;
    sur un verrou libere, il le reprend ; sur un verrou ACTIF, le filtre ne
    correspond plus, l'`upsert` tente donc une insertion et MongoDB rend un
    doublon de cle primaire. C'est exactement la barriere qu'on veut, et c'est
    la base qui la tient — pas une lecture suivie d'une ecriture, qui laisserait
    passer deux requetes nees a la meme milliseconde (`shared.py:425`).

    TOUT OU RIEN : si la seconde cle echoue, la premiere est rendue. Sinon un
    numero deja pris laisserait derriere lui un verrou d'adresse fantome.
    """
    _cles = _essai1_cles(email, telephone, coach_id)
    if not _cles:
        return True
    _maintenant = datetime.now(timezone.utc).isoformat()
    _prises = []
    for _cle in _cles:
        try:
            await db["free_trial_claims"].find_one_and_update(
                {"_id": _cle, "actif": {"$ne": True}},
                {"$set": {"actif": True, "created_at": _maintenant},
                 "$unset": {"libere_le": "", "libere_motif": ""}},
                upsert=True,
            )
            _prises.append(_cle)
        except Exception as _err:
            if "duplicate" in str(_err).lower() or "E11000" in str(_err):
                for _rendue in _prises:
                    await _essai1_liberer_cle(_rendue, "reclamation_partielle")
                return False
            # Toute autre panne : on ne bloque pas le tunnel sur une base
            # capricieuse. La garde metier ci-dessus a deja fait son travail.
            logger.warning(f"[ESSAI-1] reservation d'essai impossible: {_err}")
            return True
    return True


async def _essai1_liberer_cle(cle: str, motif: str = "") -> None:
    """Rend UNE cle. Le document reste, marque `actif: False`.

    ON NE SUPPRIME PLUS LE DOCUMENT : la trace de qui a demande un essai, et
    quand, est la seule chose qui permettra un jour de comprendre un litige.
    C'est `actif` qui porte le verrou, pas l'existence de la ligne.
    """
    try:
        await db["free_trial_claims"].update_one(
            {"_id": cle},
            {"$set": {"actif": False,
                      "libere_le": datetime.now(timezone.utc).isoformat(),
                      "libere_motif": str(motif or "")[:64]}},
        )
    except Exception as _err:
        logger.error(f"[ESSAI-1] reservation non liberee ({cle[:24]}): {_err}")


async def _essai1_liberer(email: str, telephone: str = "", coach_id=None) -> None:
    """Rend la reservation si la creation a echoue : sans cela, une panne au
    milieu du tunnel priverait la personne de son essai pour toujours."""
    for _cle in _essai1_cles(email, telephone, coach_id):
        await _essai1_liberer_cle(_cle, "octroi_echoue")


async def _essai1_garde(email: str, offer_id: str = "", telephone: str = "",
                        coach_id=None) -> None:
    """Refuse un second essai. A appeler AVANT la moindre ecriture.

    TROIS ISSUES, ET DEUX REFUS QUI NE DISENT PAS LA MEME CHOSE :

      1. l'essai a ete CONSOMME — une presence validee, sous cette adresse OU
         sous ce numero -> 409 `free_trial_already_used`. C'est le refus qui
         ferme l'abus mesure en production : trois essais sur le seul numero
         +41765203363, sous trois adresses differentes.

      2. la personne DETIENT DEJA un essai encore utilisable -> 409
         `free_trial_already_granted`. Ce n'est pas une punition, c'est un
         renvoi vers son propre droit : on ne fabrique pas un second cours
         gratuit a quelqu'un qui en a un qui l'attend.

      3. sinon -> l'essai est ACCORDE. Y compris a un absent dont le credit a
         ete rendu puis le forfait expire, et y compris a quelqu'un dont le
         code a ete supprime : ni l'un ni l'autre n'est jamais venu.

    LA DIFFERENCE ENTRE 1 ET 2 EST LA DECISION DU PROPRIETAIRE, prise le
    24/08/2026 : « reserver ne consomme pas, seule une presence validee
    consomme ». C'est aussi, mot pour mot, ce que `t1_restituer_essais_non_honores`
    applique deja depuis T1 — on ne change pas ce mecanisme, on s'aligne dessus.

    Le motif machine part dans un en-tete pour que l'ecran puisse orienter sans
    analyser du francais ; le `detail` reste la phrase montree au client.
    """
    _raison, _message = await _essai1_motif_refus(email, telephone, coach_id)
    if _raison:
        await _essai1_tracer_refus(offer_id)
        raise HTTPException(
            status_code=409,
            detail=_message,
            headers={"X-Refus-Raison": _raison},
        )

    if not await _essai1_reclamer(email, telephone, coach_id):
        # Perdu la course : quelqu'un vient d'obtenir l'essai de cette identite
        # a la milliseconde pres. Le message « deja detenu » est le vrai.
        from api.routes.shared import (ESSAI6_REFUS_DEJA_DETENU as _R_DETENU,
                                       ESSAI6_MESSAGE_DEJA_DETENU as _M_DETENU)
        await _essai1_tracer_refus(offer_id)
        raise HTTPException(
            status_code=409,
            detail=_M_DETENU,
            headers={"X-Refus-Raison": _R_DETENU},
        )


# === ESSAI-4 : UN ABONNE ACTIF N'EST PAS UNE ACQUISITION ===
#
# LA REGLE PRODUIT. Le premier cours gratuit sert a faire venir quelqu'un qui
# n'est pas encore client. Une personne qui detient DEJA un droit d'acces
# utilisable n'entre pas dans cette cible : elle a une seance a prendre, pas un
# essai a decouvrir.
#
# CE QUI COMPTE COMME « ABONNEMENT ACTIF ». La verite est celle que le projet
# utilise deja partout ailleurs pour autoriser une reservation :
# `forfait_utilisable` (shared.py) — NON EXPIRE et AU MOINS UNE SEANCE
# RESTANTE. On ne reinvente pas un predicat : un second aurait derive du
# premier, et deux definitions d'« actif » dans le meme produit, c'est la
# garantie qu'un jour l'ecran et le serveur se contrediront.
#
# CE QUI N'EN EST PAS UN — et c'est la moitie de la regle :
#   - un forfait EXPIRE : la personne a ete cliente, elle ne l'est plus ;
#   - un forfait EPUISE (0 seance) : idem ;
#   - un forfait d'ESSAI : sinon la personne qui vient d'obtenir son essai
#     s'entendrait dire « vous avez deja un abonnement actif », ce qui est
#     litteralement vrai et parfaitement trompeur. Les essais sont donc RETIRES
#     de l'examen, et c'est ESSAI-1 — la garde suivante — qui repond pour eux,
#     avec le bon message.
#
# L'ANCIEN ABONNE N'EST PAS EXCLU. Aucune exclusion historique n'est creee ici :
# on ne regarde que ce qui est utilisable AUJOURD'HUI. Quelqu'un dont le pack
# est termine redevient eligible, si ESSAI-1 le laisse passer.
#
# CE QU'ON NE RENVOIE PAS. Le message ne contient NI le code d'acces, NI le lien
# `/espace/{code}`. Le code EST le mot de passe de l'abonne (modele capability,
# V389) : le rendre sur une route publique, contre une simple adresse e-mail,
# rouvrirait exactement la chaine d'attaque fermee en aout. On oriente vers la
# recuperation par e-mail, qui prouve la possession de la boite.

ESSAI4_RAISON = "active_subscription"
# Le message dit QUOI FAIRE, et s'appuie sur un écran QUI EXISTE :
# « Retrouver mes accès » (ChatWidget), qui renvoie le lien par e-mail apres
# avoir prouve la possession de la boite. On ne renvoie donc jamais le code ici.
ESSAI4_MESSAGE = ("Vous avez déjà un abonnement Afroboost actif : réservez votre "
                  "prochaine séance depuis votre espace abonné. Code égaré ? "
                  "Utilisez « Retrouver mes accès » dans le chat.")


async def _essai4_abonnement_actif(email: str) -> bool:
    """Cette adresse detient-elle un forfait PAYANT encore utilisable ?

    En cas d'erreur de lecture : False. Mieux vaut laisser passer un essai de
    trop que fermer l'acquisition parce que la base a hoquete — et ESSAI-1
    reste derriere, lui, pour empecher le doublon.
    """
    _e = (email or "").strip().lower()
    if not _e:
        return False
    # `re` n'est PAS importe au niveau module dans ce fichier (verifie : une seule
    # occurrence, locale, l.1464). Import local, comme la convention du fichier.
    import re as _re_e4
    try:
        from api.routes.shared import (essai2_codes_essai as _codes_essai,
                                       forfait_utilisable as _utilisable)
        _essais = {str(c or "").strip().upper() for c in (await _codes_essai(db, _e) or [])}
        _forfaits = await db["subscriptions"].find(
            {"email": {"$regex": f"^{_re_e4.escape(_e)}$", "$options": "i"},
             "status": "active"},
            {"_id": 0, "code": 1, "expires_at": 1, "remaining_sessions": 1,
             "total_sessions": 1, "used_sessions": 1},
        ).to_list(50)
    except Exception as _err:
        logger.warning(f"[ESSAI-4] lecture des forfaits impossible: {_err}")
        return False

    for _f in _forfaits:
        if str(_f.get("code") or "").strip().upper() in _essais:
            continue          # un essai n'est pas un abonnement : ESSAI-1 s'en charge
        _ok, _ = _utilisable(_f, 1)
        if _ok:
            return True
    return False


async def _essai4_garde(email: str, offer_id: str = "") -> None:
    """Refuse le premier cours gratuit a un client deja actif.

    A appeler AVANT `_essai1_garde` : cette garde-ci ne fait que LIRE, alors que
    la suivante ECRIT (elle reserve l'essai). Dans l'autre ordre, un abonne
    actif consommerait son droit a l'essai pour se faire refuser juste apres.
    """
    if not await _essai4_abonnement_actif(email):
        return
    try:
        from api.routes.shared import posthog_capture as _ph
        await _ph("trial_refused", email="", props={
            "reason": "active_subscription",
            "offer_id": (offer_id or "")[:64],
        })
    except Exception:
        pass
    raise HTTPException(
        status_code=409,
        detail=ESSAI4_MESSAGE,
        headers={"X-Refus-Raison": ESSAI4_RAISON},
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


# ═══ ESSAI-7 — LE CODE NE REPART QUE S'IL N'OUVRE RIEN QUI NE SOIT A NOUS ═══
#
# LE DELTA A FERMER. Rendre `access_code` sur une route SANS authentification
# ajoute une capacite qui n'existait pas : un appelant anonyme qui saisit
# l'adresse d'un tiers repart avec un code utilisable. Bruler l'essai d'autrui
# etait deja possible avant ce lot (trou pre-existant, inchange) ; APPRENDRE le
# code ne l'etait pas.
#
# POURQUOI C'EST GRAVE. `GET /subscriber/space/{code}` resout les reservations
# PAR ADRESSE E-MAIL, pas par code (server.py, « V208c »). Un code neuf frappe
# sur une adresse DEJA CONNUE ouvre donc l'historique complet de cette
# personne : noms de cours, dates, invites, presences validees.
#
# LA REGLE. Le code ne repart QUE si l'espace qu'il ouvre ne peut rien contenir
# d'autre que ce que CETTE requete vient de fournir : aucune reservation,
# aucun forfait, aucun code d'acces anterieur sur cette adresse. Sinon la
# reponse redevient EXACTEMENT celle d'avant le lot, et l'e-mail — qui prouve
# la possession de la boite — reste le seul canal. Le delta retombe a zero.
#
# CE QUI NE COMPTE PAS : un simple contact CRM (`chat_participants`). L'espace
# n'en montre rien, et le tunnel Chat en cree un AVANT le checkout : l'inclure
# aurait ferme Option B pour l'entree principale du funnel.
#
# CE QUE CETTE REGLE NE FERME PAS, et il faut le dire : elle n'empeche pas de
# bruler l'essai d'un tiers (trou anterieur), ni d'obtenir un code sur une
# adresse encore INCONNUE — dont l'espace ne contiendra jamais que ce que
# l'appelant a lui-meme saisi ce jour-la, mais qui suivrait cette adresse si
# elle devenait active plus tard. Fermer CELA demande de prouver la possession
# de l'adresse, donc une etape de verification : c'est un lot en soi.
async def _essai7_espace_vierge(email: str) -> bool:
    """L'espace de cette adresse est-il VIERGE de tout passe ?

    FAIL-CLOSED : en cas de base muette, on repond False. Perdre la redirection
    coute une commodite ; rendre un code a tort coute un acces.
    """
    import re as _re_e7
    _mail = (email or "").strip().lower()
    if not _mail:
        return False
    _motif = {"$regex": f"^{_re_e7.escape(_mail)}$", "$options": "i"}
    try:
        # L'historique que l'espace afficherait. Les deux orthographes du champ
        # sont interrogees : `userEmail` est celle de la production, `user_email`
        # traine dans des documents anciens — et ici, un doublon de prudence ne
        # coute qu'une redirection perdue.
        if await db["reservations"].find_one(
                {"$or": [{"userEmail": _motif}, {"user_email": _motif}]}, {"_id": 1}):
            return False
        if await db["subscriptions"].find_one({"email": _motif}, {"_id": 1}):
            return False
        if await db["discount_codes"].find_one({"assignedEmail": _motif}, {"_id": 1}):
            return False
        # LOT R : l'espace affiche l'etat de recharge, derive des adhesions
        # (`memberships`). Six d'entre elles ont ete regularisees a la main, sans
        # forfait en face : les deduire des trois lectures ci-dessus serait faux.
        if await db["memberships"].find_one({"email": _motif}, {"_id": 1}):
            return False
    except Exception as _err:  # noqa: BLE001
        logger.warning("[ESSAI-7] passe de l'adresse illisible (%s) — code non rendu",
                       type(_err).__name__)
        return False
    return True


# ═══ ESSAI-7 — LIMITATION DE DEBIT SUR LA PORTE GRATUITE ════════════════════
#
# Meme mecanique que `_lot3b_debit_ok` (server.py) : un compteur en memoire du
# processus, sans collection ni ecriture. Le depot n'a pas de limiteur global
# (`slowapi` n'est pas installe), et en ajouter un pour une seule route serait
# disproportionne.
#
# CE QU'ELLE FERME : l'appel FABRIQUE en serie — enumeration d'adresses,
# brulage d'essais en masse. Elle ne pretend pas remplacer une preuve
# d'identite : un seuil ne distingue pas un visiteur d'un attaquant patient.
#
# LE SEUIL EST GENEREUX A DESSEIN. Un essai gratuit est unique par personne :
# 20 par heure et par IP ne gene aucun usage reel, pas meme une salle entiere
# derriere le meme wifi, alors qu'une enumeration en veut des milliers.
_ESSAI7_DEBIT = {}
_ESSAI7_DEBIT_MAX = 20          # octrois tentes
_ESSAI7_DEBIT_FENETRE = 3600.0  # secondes


def _essai7_debit_ok(cle: str) -> bool:
    import time as _t
    _now = _t.monotonic()
    _hist = [h for h in _ESSAI7_DEBIT.get(cle, []) if _now - h < _ESSAI7_DEBIT_FENETRE]
    if len(_hist) >= _ESSAI7_DEBIT_MAX:
        _ESSAI7_DEBIT[cle] = _hist
        return False
    _hist.append(_now)
    _ESSAI7_DEBIT[cle] = _hist
    if len(_ESSAI7_DEBIT) > 5000:      # borne memoire, jamais une fuite
        for _k in list(_ESSAI7_DEBIT.keys())[:1000]:
            _ESSAI7_DEBIT.pop(_k, None)
    return True


def _essai7_exiger_debit(http_request) -> None:
    """Leve 429 au-dela du seuil. A appeler AVANT toute autre garde : un refus
    de debit ne doit RIEN consommer, surtout pas le droit a l'essai.

    L'IP reelle passe par Cloudflare puis Traefik — `request.client.host` est le
    proxy. Meme resolution qu'ailleurs dans le depot (server.py, « IP reelle »).
    """
    try:
        _ip = (http_request.headers.get("CF-Connecting-IP")
               or (http_request.headers.get("X-Forwarded-For", "") or "").split(",")[0].strip()
               or (http_request.client.host if http_request.client else "")).strip()
    except Exception:  # noqa: BLE001
        # Pas d'IP lisible : on ne bloque pas un parcours legitime pour un
        # en-tete manquant. La regle du code vierge, elle, tient toujours.
        return
    if not _ip:
        return
    if not _essai7_debit_ok("free:" + _ip):
        logger.warning("[ESSAI-7] debit depasse pour %s — refus 429", _ip[:24])
        raise HTTPException(
            status_code=429,
            detail="Trop de demandes depuis cette connexion. Réessayez dans un moment.",
        )


@router.post("/free")
async def free_checkout(req: FreeCheckoutRequest, http_request: Request):
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
    # ESSAI-7 : le debit d'abord. Un refus ici ne coute rien a personne — ni
    # lecture, ni ecriture, ni droit consomme.
    _essai7_exiger_debit(http_request)

    # garde-fou : on refuse un item non gratuit ici, ce chemin est reserve au
    # 0 CHF. ESSAI-1B : le prix est relu EN BASE — additionner les `price` du
    # client laissait passer une offre a 250 CHF annoncee a 0.
    # ESSAI-5a-1 — les conditions d'abord, avant meme la verification de
    # gratuite : un refus ici ne laisse rien derriere lui.
    _t1_champs = await _t1_preuve_checkout(req.terms_accepted, req.items,
                                           req.coach_email)

    # LOT 2 : meme garde que sur `/create-session`. Elle doit exister sur LES
    # DEUX portes — la poser sur une seule la rendrait contournable en changeant
    # d'URL, exactement comme ESSAI-1 l'a appris.
    # R2b — SI LE CLIENT NE DIT PLUS QUI VEND, LE SERVEUR LE LIT.
    await _r2b_vendeur_si_absent(req)
    await _lot2_verifier_vendeur(req.items, req.coach_email)

    await _essai1b_exiger_gratuit(req.items)
    if not req.customer_email or "@" not in req.customer_email:
        raise HTTPException(status_code=400, detail="Email client requis.")

    # ESSAI-4 AVANT ESSAI-1 : celle-ci LIT, celle-la ECRIT. Un abonne actif ne
    # doit pas bruler son droit a l'essai pour s'entendre refuser juste apres.
    await _essai4_garde(req.customer_email,
                        str((req.items[0].id if req.items else "") or ""))

    # LOT R : la porte GRATUITE aussi. Une offre reservee aux membres obtenue
    # a 0 CHF serait le contournement le plus simple de tous.
    await _lotr_garde(req.items, req.customer_email)

    # ESSAI-1 : ici, et pas ailleurs. `_process_successful_payment` cree le code
    # AFR- et le forfait des ses premieres lignes ; toute verification posee
    # apres arriverait devant un essai deja accorde.
    # ESSAI-6 : meme second critere sur la seconde porte gratuite. Le poser sur
    # une seule des deux le rendrait contournable en changeant d'URL — c'est le
    # raisonnement qui a place ESSAI-1 et ESSAI-4 ici.
    await _essai1_garde(req.customer_email,
                        str((req.items[0].id if req.items else "") or ""),
                        telephone=req.customer_phone)

    # ESSAI-7 : constate MAINTENANT, avant que le moteur n'ecrive. Apres lui,
    # le forfait et le code qu'il vient de creer rendraient la reponse toujours
    # fausse, et plus aucun code ne repartirait jamais.
    espace_vierge = await _essai7_espace_vierge(req.customer_email)

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
        await _essai1_liberer(req.customer_email,
                              telephone=req.customer_phone)
        raise
    product_name = (result or {}).get("product_name", "Offre gratuite")
    # ESSAI-7 : le code que le serveur VIENT DE CREER, et lui seul.
    # `_process_successful_payment` en fabrique un neuf a chaque appel
    # (`AFR-` + 6 caracteres tires au hasard) : cette valeur n'a jamais
    # appartenu a personne avant cette requete. Voir le commentaire de la
    # reponse, plus bas, pour la difference avec ESSAI-1A.
    # ESSAI-7 : le code ne quitte le serveur que si l'espace qu'il ouvre ne
    # contient rien d'autre que ce que cette requete vient de fournir. Sinon,
    # la reponse est mot pour mot celle d'avant ce lot.
    code_octroye = str((result or {}).get("access_code") or "") if espace_vierge else ""

    # ═══ M2-A — L'ORIGINE SURVIT AU CHANGEMENT D'APPAREIL ═══
    # Le parcours d'essai se termine des jours plus tard, depuis le lien recu
    # par e-mail, souvent sur un autre telephone : le `localStorage` d'origine
    # n'existe plus. On pose donc l'origine ICI, sur la souscription du code —
    # `reserve_course_from_space` la recopiera le jour venu.
    # FAIL-OPEN : toute panne de ce bloc laisse l'essai intact.
    try:
        from api.routes.shared import m2a_bloc_propre as _m2a_propre
        _m2a_attribution = _m2a_propre(getattr(req, "attribution", None))
        _m2a_code = str((result or {}).get("access_code") or "").strip().upper()
        if _m2a_attribution and _m2a_code:
            await db["subscriptions"].update_one(
                {"code": _m2a_code}, {"$set": {"attribution": _m2a_attribution}})
            logger.info("[M2-A] origine enregistree pour un essai (first=%s last=%s)",
                        (_m2a_attribution.get("first") or {}).get("source", "-"),
                        (_m2a_attribution.get("last") or {}).get("source", "-"))
    except Exception as _m2ae:
        logger.warning("[M2-A] origine non enregistree (%s)", type(_m2ae).__name__)

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

    # ESSAI-7 — LE CODE REPART DANS LA REPONSE, ET CE N'EST PAS UN RETOUR EN
    # ARRIERE SUR ESSAI-1A.
    #
    # Ce qu'ESSAI-1A refermait, a juste titre : cette route n'a AUCUNE
    # authentification, l'adresse est celle que le visiteur ecrit lui-meme, et
    # rendre le code d'un TIERS revenait a le remettre a quiconque saisit son
    # adresse. C'est exactement pour cela que le refus ESSAI-4 (« vous avez
    # deja un abonnement actif ») ne dit toujours NI le code, NI le lien
    # `/espace/{code}` : la, il s'agirait d'un code PRE-EXISTANT.
    #
    # Ce qui repart ici est autre chose : un code que ce meme appel VIENT de
    # fabriquer. Les deux chemins qui exposeraient le code de quelqu'un
    # d'autre — essai deja consomme (ESSAI-1) et abonnement actif (ESSAI-4) —
    # LEVENT avant `_process_successful_payment` et ne renvoient rien du tout.
    #
    # POURQUOI IL LE FAUT. Sans ce champ, la fin du tunnel etait un cul-de-sac :
    # le code n'existait pour le visiteur que dans un e-mail — donc dans une
    # boite de reception, un dossier « promotions », un delai. La mesure du
    # 25/08/2026 l'a montre : l'essai etait accorde, la seance ne l'etait pas.
    # Avec lui, la vitrine peut emmener la personne sur `/espace/<CODE>` pour
    # qu'elle CHOISISSE sa seance, tout de suite.
    #
    # Le champ est ADDITIF : tous les autres sont conserves a l'identique.
    return {
        "success": True,
        "free": True,
        "transaction_id": transaction_id,
        "access_code": code_octroye,
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

async def _essai2_convertir_si_paye(email: str, total, payment_method: str,
                                    offer_id: str = "", sub_id: str = "",
                                    items=None) -> bool:
    """LOT A — LE CHAINON MANQUANT : cet achat convertit-il un essai honore ?

    LE TROU QUE CECI BOUCHE. `converted_at` n'etait pose que par le webhook de
    `api/server.py`. Or l'URL reellement declaree chez Stripe est
    `/api/checkout/webhook/stripe`, qui traite LUI-MEME les achats vitrine
    (`type: vitrine_purchase`) via `_process_successful_payment` et ne delegue
    au gestionnaire client que le RESTE. Un achat de la vitrine — donc tout
    achat issu de l'ecran d'apres-essai — n'a jamais converti personne : le
    funnel d'ESSAI-3 affichait 0, et l'ecran aurait continue a vendre a
    quelqu'un qui venait d'acheter.

    UNIQUEMENT SUR UN PAIEMENT REEL. ESSAI-2 definit la conversion comme « le
    premier achat PAYANT qui suit une presence d'essai ». `_process_successful_payment`
    sert aussi les parcours GRATUITS (`/free`, et la branche a 0 CHF de
    `create-session`) : sans cette garde, obtenir un second acces offert apres
    un essai honore serait compte comme une conversion, et le taux du tableau de
    bord deviendrait faux dans le sens flatteur.

    AUCUNE NOUVELLE REGLE DE CONVERSION : c'est `essai2_marquer_conversion` qui
    juge, avec son ecriture atomique. Deux webhooks qui arriveraient tous les
    deux n'en produiraient qu'une. Non bloquant : le paiement est deja encaisse,
    une mesure ratee ne doit rien faire echouer.
    """
    # R1 — LES DEUX GARDES VIVENT DESORMAIS DANS `shared.py`, une seule fois,
    # pour les DEUX chemins d'autorite. Ce helper ne fait plus que rassembler
    # les identifiants d'offre du panier ; il ne juge plus rien lui-meme.
    #
    # R1-c : TOUTES LES LIGNES, PAS LA PREMIERE. `offer_id` valait
    # `items_offer_id`, fige sur le PREMIER article — « t-shirt + PULSE » se
    # classait donc sur le t-shirt. `items` est desormais transmis par
    # l'appelant ; `offer_id` reste le repli exact d'avant pour les appelants
    # qui n'ont qu'un identifiant sous la main (webhook a metadonnee unique).
    _ids = []
    for _it in (items or []):
        _d = _it.dict() if hasattr(_it, "dict") else dict(_it or {})
        _oid = str(_d.get("id") or "").strip()
        if _oid:
            _ids.append(_oid)
    if not _ids and str(offer_id or "").strip():
        _ids = [str(offer_id).strip()]
    try:
        from api.routes.shared import essai2_convertir_si_achat_de_cours as _e2_porte
        return await _e2_porte(db, email, total, payment_method, _ids, str(sub_id or ""))
    except Exception as _err:
        logger.warning(f"[ESSAI-2] conversion non evaluee (caisse vitrine): {_err}")
        return False


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
    _lot3_public = None      # LOT 3a : prix public du jour de l'achat
    _lot3_palier = None      # LOT 3a : palier progressif actif ce jour-la
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
                # LOT 3a : projection ELARGIE aux champs de tarif. C'est la
                # meme requete — aucun cout supplementaire — et elle donne le
                # prix public du jour de l'achat, seul moment ou lire le
                # catalogue est legitime (apres, ce serait le prix d'aujourd'hui,
                # ce que LOT A interdit).
                _offer_doc = await db["offers"].find_one(
                    {"id": item_id},
                    {"_id": 0, "pack_sessions": 1, "price": 1,
                     "progressive_pricing": 1, "countdown_date": 1,
                     "countdown_time": 1, "early_bird_days_before": 1,
                     "standard_hours_before": 1, "price_early_bird": 1,
                     "price_standard": 1, "price_last_minute": 1}
                )
                # `if _offer_doc` : sur une offre INTROUVABLE,
                # `compute_active_price({})` rend 0.0 — et ecrire
                # `tarif_public: 0.0` se lirait « le prix public etait nul »
                # la ou la regle du lot veut qu'une cle absente dise « on ne
                # sait pas ». Les deux ne se ressemblent que de loin.
                if _lot3_public is None and _offer_doc:
                    try:
                        from api.pricing import compute_active_price as _cap
                        _r = _cap(_offer_doc or {}) or {}
                        _lot3_public = float(_r.get("price") or 0)
                        _lot3_palier = _r.get("tier")
                    except Exception:
                        _lot3_public, _lot3_palier = None, None
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

    # B : la trace financiere, dans la meme forme que pour un encaissement saisi
    # a la main. Import local, comme les autres imports de ce helper.
    from api.routes.shared import b_champs_automatiques as _b_auto

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
        "created_at": datetime.now(timezone.utc).isoformat(),
        # B : meme vocabulaire que les codes crees a la main. `payment_method`
        # et `total_paid` existaient deja ici et ne bougent pas ; ces champs-ci
        # les redisent dans la forme UNIQUE que la lecture financiere attend,
        # pour qu'un achat en ligne et un encaissement en especes se lisent
        # exactement de la meme facon.
        **_b_auto(payment_method, total, currency, sessions_count)
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
        # B : la souscription porte la meme trace que son code.
        **_b_auto(payment_method, total, currency, sessions_count),
    })
    logger.info(f"[CHECKOUT] Code {access_code} + subscription crees pour {customer_email} ({sessions_count} seances)")

    # === LOT 2 — CHEMIN D'AUTORITE B : L'ADHESION QUI NAIT DE CET ACHAT ===
    #
    # POURQUOI DEUX BRANCHEMENTS DANS LE DEPOT. Ce fichier reconnait un paiement
    # reussi pour QUATRE webhooks (Stripe vitrine, CinetPay, PayPal, PawaPay) et
    # deux chemins gratuits, tous convergeant ici ; le webhook Stripe « client »
    # de server.py est, lui, un second moteur, avec ses propres champs. Un achat
    # depuis la vitrine ou depuis l'ecran d'apres-essai passe par ICI. N'en
    # brancher qu'un aurait manque la moitie des achats — d'ou le MEME helper
    # appele aux deux endroits, et une seule definition de la regle.
    #
    # LE PROPRIETAIRE N'EST PAS `coach_email`. Cette variable vient du corps de
    # la requete, donc du navigateur : deux ecrans de cette application y
    # mettent aujourd'hui des valeurs differentes pour le meme achat. Le helper
    # relit `offers.coach_id` en base et n'utilise QUE cela. `coach_email`
    # continue de servir a ce a quoi il sert vraiment ici — le routage de
    # l'argent (`get_payment_keys`) — et a rien d'autre pour l'adhesion.
    #
    # NON BLOQUANT, et place APRES l'ecriture du forfait : l'argent est encaisse,
    # le code d'acces est emis. Une adhesion manquee se rattrape a la main.
    try:
        from api.routes.shared import lot2_creer_adhesion_apres_achat as _lot2
        await _lot2(
            db,
            email=customer_email,
            offre_id=items_offer_id,
            subscription_id=subscription_id,
            nom=customer_name or "",
            moteur=payment_method,
            montant=total,
            devise=currency,
        )
    except Exception as _lot2e:
        logger.error(f"[LOT2] adhesion ignoree (chemin checkout): {_lot2e}")

    # V397 : ferme l'ancien forfait (expiré ou épuisé) du même client. Non bloquant :
    # le paiement est déjà encaissé, une erreur ici ne doit rien faire échouer.
    try:
        _fermes = await _v397_cloturer(db, customer_email, subscription_id, log_prefix="V397-VITRINE")
        if _fermes:
            logger.info(f"[V397-VITRINE] {len(_fermes)} ancien(s) forfait(s) ferme(s) pour {customer_email}")
    except Exception as _e397:
        logger.warning(f"[V397-VITRINE] Cloture ignoree: {_e397}")

    # ESSAI-2 / LOT A : le forfait achete existe, la conversion peut etre jugee.
    # Placee ICI et pas plus haut : `essai2_marquer_conversion` renseigne
    # `converted_by_subscription_id`, qui n'a de sens qu'une fois l'identifiant
    # du nouveau forfait connu.
    # R1-c : `items` en plus — le panier ENTIER, pas seulement son premier
    # article. `items_offer_id` reste passe : il sert de repli si aucune ligne
    # ne porte d'identifiant (paniers anciens).
    if await _essai2_convertir_si_paye(customer_email, total, payment_method,
                                       items_offer_id, subscription_id,
                                       items=items):
        logger.info(f"[ESSAI-2] Conversion actee pour {customer_email} "
                    f"(achat vitrine {items_product_name or ''})")

    # 4. Créer les réservations pour chaque item de type "course"
    #
    # LOT 1 — CE CHEMIN N'ECRIVAIT NI `courseId` NI `datetime`. Il ne posait que
    # `courseName`, une chaine libre : la reservation etait structurellement
    # irrattachable a une seance. Zero document en production a ce jour (mesure
    # du 19/08/2026 : 0 reservation `checkout_vitrine` sur 137), donc rien a
    # reparer — mais la premiere vente aurait cree le defaut.
    #
    # POURQUOI ON NE REFUSE PAS ICI, alors que le meme defaut vaut un 400 sur
    # `POST /reservations`. On est APRES l'encaissement : le paiement est
    # accepte, le forfait cree, le code d'acces emis. Refuser maintenant ferait
    # perdre au client la trace de son achat sans lui rendre son argent. La
    # garde `fail closed` protege ce qui n'est pas encore ecrit ; elle n'a pas
    # a punir ce qui est deja paye.
    #
    # CE QU'ON FAIT A LA PLACE — resoudre ce qui est PROUVABLE, omettre le reste :
    #   * `courseId` : verifie cote SERVEUR contre la collection `courses`.
    #     L'identifiant vient du panier, mais son existence n'est jamais prise
    #     pour argent comptant.
    #   * `datetime` : ecrit UNIQUEMENT pour un cours PONCTUEL, dont la date est
    #     portee par le cours lui-meme — la seule occurrence possible, donc rien
    #     n'est devine. Pour un cours RECURRENT, la caisse ne demande aucune
    #     date : il n'y a rien a ecrire, et inventer « la prochaine fois »
    #     fabriquerait une seance a laquelle personne n'a dit vouloir venir.
    #     Le champ reste ABSENT — c'est deja le mot que le lecteur du bilan
    #     comprend comme « seance non rattachee », et cela n'exige aucun champ
    #     nouveau.
    from api.routes.reservation_routes import (
        lot1_identifiant as _l1_id,
        LOT1_PREFIXE as _L1P,
    )
    for item in items:
        item_data = item.dict() if hasattr(item, 'dict') else item
        if item_data.get("type") == "course":
            _l1_course_id = _l1_id(item_data.get("id"))
            _l1_cours = None
            if _l1_course_id:
                _l1_cours = await db["courses"].find_one(
                    {"id": _l1_course_id},
                    {"_id": 0, "id": 1, "date": 1, "time": 1, "archived": 1})
            if not _l1_cours or _l1_cours.get("archived") is True:
                if _l1_course_id:
                    logger.warning("%s checkout_vitrine : cours %r introuvable ou archive, "
                                   "reservation ecrite sans rattachement", _L1P, _l1_course_id[:48])
                _l1_course_id = ""
            _l1_occurrence = ""
            if _l1_cours:
                _l1_date = str(_l1_cours.get("date") or "").strip()[:10]
                _l1_heure = str(_l1_cours.get("time") or "").strip()
                if len(_l1_date) == 10 and ":" in _l1_heure:
                    # Cours PONCTUEL : une seule occurrence possible, portee par
                    # le cours. Meme format naif local que partout ailleurs.
                    _l1_occurrence = "%sT%s:00" % (_l1_date, _l1_heure[:5])
                else:
                    logger.info("%s checkout_vitrine : cours %r recurrent, aucune date choisie "
                                "en caisse — `datetime` volontairement absent",
                                _L1P, _l1_course_id[:48])
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
            # LOT 1 : les deux moities de l'identite de seance, quand elles sont
            # PROUVEES. Posees par `if` plutot qu'en litteral : une cle absente
            # dit « je ne sais pas », une cle a `None` dit « je sais que c'est
            # vide » — et ce n'est pas la meme chose pour qui lira le bilan.
            if _l1_course_id:
                _resa_doc["courseId"] = _l1_course_id
            if _l1_occurrence:
                _resa_doc["datetime"] = _l1_occurrence
            # ESSAI-5a-1 : la preuve suit la reservation qu'elle couvre.
            _resa_doc.update(terms_fields or {})
            # LOT 3a : le tarif fige de cet achat.
            #
            # LE MONTANT VIENT DU PAIEMENT, PAS DU PANIER. `item_data["price"]`
            # est la valeur envoyee par le NAVIGATEUR (elle est d'ailleurs deja
            # recopiee telle quelle dans `totalPrice`, dette connue) ; `total`
            # est ce que la caisse a reellement encaisse. On fige le second.
            #
            # UN SEUL ARTICLE, sinon RIEN. Repartir un total entre plusieurs
            # lignes demanderait une cle de repartition qui n'existe pas : on
            # inventerait. Mieux vaut pas de snapshot qu'un montant fabrique.
            try:
                from api.routes.shared import lot3_champs_achat as _lot3_achat
                if len(items) == 1:
                    _q = max(1, int(item_data.get("quantity", 1) or 1))
                    _pm = str(payment_method or "").strip().lower()
                    if _pm == "free":
                        # Les deux portes gratuites brulent le droit d'essai
                        # (`_essai1_garde`) : c'en est un, pas un « public a 0 ».
                        _lot3_raison, _lot3_du = "essai", 0.0
                    else:
                        _lot3_raison = "promo" if discount_code else "public"
                        _lot3_du = round(float(total or 0) / _q, 2)
                    _resa_doc.update(_lot3_achat(
                        _lot3_du, _lot3_raison,
                        tarif_public=_lot3_public, devise=currency,
                        palier=_lot3_palier, offre_id=items_offer_id or None))
            except Exception as _l3:
                logger.warning("[LOT3a] snapshot vitrine ignore (%s)", type(_l3).__name__)
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
