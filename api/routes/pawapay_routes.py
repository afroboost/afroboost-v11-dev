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
import time
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
    # V325c : vide par défaut — le pays est décidé par la configuration RÉELLE du
    # compte PawaPay (GET /v2/active-conf), plus par une valeur codée en dur.
    country: str = ""
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
    country: str = ""   # V325c : voir resoudre_pays()
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
    country: str = ""   # V325c : voir resoudre_pays()
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
    """Renvoie un code pays alpha-3 majuscule, ou '' si l'entrée n'est pas exploitable."""
    c = (country or "").strip().upper()
    if len(c) == 2:
        return _ALPHA2_TO_ALPHA3.get(c, "")
    if len(c) == 3:
        return c
    return ""


# === V325c : CONFIGURATION ACTIVE DU COMPTE PAWAPAY ===
#
# Le pays était CODÉ EN DUR (« CIV »). Ce n'était PAS la cause du 400 du premier
# test sandbox (CIV est bien ouvert sur le compte — c'était le format du montant,
# cf. V325e), mais deviner le pays d'un compte reste faux par principe, et la
# devise à mettre dans `amountDetails` ne peut venir que de là. On DEMANDE donc à
# PawaPay quels pays sont ouverts (GET /v2/active-conf) et avec quelle devise.
#
# Petit cache mémoire : cette configuration ne change qu'au rythme des démarches
# commerciales, inutile d'interroger PawaPay à chaque paiement.
_ACTIVE_CONF_CACHE = {"cle": None, "pays": None, "ts": 0.0}
_ACTIVE_CONF_TTL_S = 600  # 10 minutes


async def get_supported_countries(token: str, base_url: str) -> dict:
    """
    Renvoie {code_pays_alpha3: devise} pour les pays réellement activés en DÉPÔT
    sur le compte PawaPay. Renvoie {} si la configuration est illisible.
    """
    cle = f"{base_url}|{token[-6:] if token else ''}"
    maintenant = time.monotonic()
    if (_ACTIVE_CONF_CACHE["cle"] == cle
            and _ACTIVE_CONF_CACHE["pays"] is not None
            and (maintenant - _ACTIVE_CONF_CACHE["ts"]) < _ACTIVE_CONF_TTL_S):
        return _ACTIVE_CONF_CACHE["pays"]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{base_url}/v2/active-conf",
                headers={"Authorization": f"Bearer {token}"}
            )
    except Exception as e:
        logger.error(f"[PAWAPAY] active-conf injoignable: {e}")
        return {}

    if response.status_code != 200:
        logger.error(f"[PAWAPAY] active-conf HTTP {response.status_code} - {response.text[:200]}")
        return {}

    try:
        data = response.json() or {}
    except Exception:
        return {}

    pays = {}
    for entree in (data.get("countries") or []):
        code = (entree.get("country") or "").strip().upper()
        if not code:
            continue
        # La devise se lit sous le premier fournisseur qui en déclare une :
        # tous les fournisseurs d'un même pays partagent la devise locale.
        devise = ""
        for fournisseur in (entree.get("providers") or []):
            for dev in (fournisseur.get("currencies") or []):
                if dev.get("currency"):
                    devise = dev["currency"].strip().upper()
                    break
            if devise:
                break
        pays[code] = devise

    _ACTIVE_CONF_CACHE.update({"cle": cle, "pays": pays, "ts": maintenant})
    logger.info(f"[PAWAPAY] Pays activés sur le compte: {sorted(pays.keys())}")
    return pays


def taux_par_devise() -> dict:
    """
    Taux de conversion depuis le CHF, configurables sans redéploiement via
    PAWAPAY_RATES (ex. « XOF=400,KES=140,GHS=15 »). XOF=400 par défaut, qui est
    le taux déjà utilisé par le site.
    """
    taux = {"XOF": 400.0}
    brut = (os.environ.get("PAWAPAY_RATES", "") or "").strip()
    for morceau in brut.split(","):
        if "=" in morceau:
            dev, _, val = morceau.partition("=")
            try:
                taux[dev.strip().upper()] = float(val)
            except ValueError:
                continue
    return taux


async def resoudre_pays(token: str, base_url: str, demande: str) -> tuple:
    """
    Choisit le pays à envoyer à PawaPay et renvoie (pays, devise).

    Ordre : PAWAPAY_DEFAULT_COUNTRY -> pays demandé -> unique pays activé.
    Si rien ne colle, on lève une 400 EXPLICITE qui nomme les pays disponibles,
    au lieu de laisser PawaPay répondre un « UNSUPPORTED_PARAMETER » opaque.
    """
    pays_ok = await get_supported_countries(token, base_url)
    if not pays_ok:
        raise HTTPException(
            status_code=503,
            detail="Mobile Money indisponible : configuration du compte PawaPay illisible."
        )

    candidats = [
        normalize_country(os.environ.get("PAWAPAY_DEFAULT_COUNTRY", "")),
        normalize_country(demande),
    ]
    for c in candidats:
        if c and c in pays_ok:
            return c, pays_ok[c]

    if len(pays_ok) == 1:
        seul = next(iter(pays_ok))
        return seul, pays_ok[seul]

    raise HTTPException(
        status_code=400,
        detail=("Mobile Money indisponible pour ce pays. Pays ouverts sur le compte : "
                + ", ".join(sorted(pays_ok.keys())))
    )


def montant_dans_devise(prix_chf, prix_xof, devise: str) -> int:
    """
    Convertit un prix en unité MAJEURE de la devise du pays choisi.

    Refuse plutôt que de deviner : facturer un montant faux serait pire qu'un
    échec propre. Le prix `price_xof` du pack n'est utilisé que si la devise
    est bien le XOF.
    """
    if devise == "XOF" and prix_xof:
        return int(prix_xof)
    taux = taux_par_devise()
    if devise not in taux:
        raise HTTPException(
            status_code=400,
            detail=(f"Mobile Money indisponible : aucun taux de conversion configuré pour {devise}. "
                    f"Renseignez PAWAPAY_RATES (ex. « {devise}=140 »).")
        )
    return int(round(float(prix_chf or 0) * taux[devise]))


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
    """
    URL à déclarer côté tableau de bord PawaPay pour recevoir les callbacks.

    V381 : `/api/pawapay/callback` — point d'entrée UNIQUE qui répartit entre ce
    site et Afroboost Live (voir le bloc « répartiteur » en fin de fichier).
    C'est le chemin réglé dans le tableau de bord PawaPay de production.
    `/api/pawapay/webhook` reste servi à l'identique.
    """
    return os.environ.get('PAWAPAY_CALLBACK_URL', f"{frontend_url()}/api/pawapay/callback")


async def create_pawapay_deposit(
    token: str,
    base_url: str,
    deposit_id: str,
    amount: int,
    country: str,
    reason: str,
    return_url: str,
    msisdn: str = "",
    currency: str = ""
) -> str:
    """
    Ouvre une session « Payment Page » PawaPay et renvoie l'URL de redirection.
    Doc : https://docs.pawapay.io/v2/docs/payment_page

    Le `depositId` est fourni par NOUS et doit être stocké AVANT cet appel : si le
    réseau lâche après l'envoi, c'est la seule référence permettant de retrouver le
    dépôt côté PawaPay.
    """
    # V325e : le schéma RÉEL de l'API v2 (« CreateSession ») n'est PAS celui des
    # exemples de la page de présentation de la doc, restés en v1. L'API v2 attend :
    #   - amountDetails: { amount, currency }   (et NON un « amount » en racine :
    #     c'est ce qui provoquait « UNSUPPORTED_PARAMETER: unsupported parameter
    #     'amount' » lors du premier test sandbox)
    #   - phoneNumber                            (et NON « msisdn »)
    #   - reason : 50 caractères maximum
    #   - language : EN ou FR
    payload = {
        "depositId": deposit_id,
        "returnUrl": return_url,
        "language": "FR",
    }
    if reason:
        # Ce texte est affiché au client sur la page PawaPay — 50 caractères max.
        payload["reason"] = reason[:50]
    if country:
        payload["country"] = country
    if amount and currency:
        # Montant en unité MAJEURE, transmis en chaîne (format attendu par PawaPay).
        payload["amountDetails"] = {"amount": str(int(amount)), "currency": currency}
    if msisdn:
        payload["phoneNumber"] = msisdn

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{base_url}/v2/paymentpage",
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        )

    try:
        data = response.json()
    except Exception:
        logger.error(f"[PAWAPAY] Réponse non-JSON ({response.status_code}): {response.text[:300]}")
        raise HTTPException(status_code=502, detail="Erreur PawaPay: réponse invalide")

    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Erreur PawaPay: réponse invalide")

    # V325g : PawaPay signale certains refus avec un code HTTP 200 et un corps ne
    # contenant QUE `failureReason`. Se fier au seul statut HTTP laissait donc passer
    # l'erreur, qui ressortait plus loin en « pas d'URL de paiement » — un symptôme,
    # pas la cause. La présence de `failureReason` fait foi, quel que soit le statut.
    raison = data.get("failureReason") or {}

    # V325h : un numéro mal saisi ne doit pas faire échouer tout le paiement. PawaPay
    # ne connaît pas tous les formats locaux ; si c'est SEULEMENT le téléphone qui
    # coince, on relance sans lui — le client saisira son numéro sur la page PawaPay.
    # Le MONTANT reste fixé (amountDetails est conservé) : aucun risque de payer autre
    # chose que le prix. Une seule relance, pour ne pas boucler.
    if (isinstance(raison, dict)
            and raison.get("failureCode") == "INVALID_PHONE_NUMBER"
            and "phoneNumber" in payload):
        logger.warning(f"[PAWAPAY] Numéro refusé par PawaPay, relance sans téléphone: {deposit_id}")
        payload.pop("phoneNumber", None)
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{base_url}/v2/paymentpage",
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                }
            )
        try:
            data = response.json()
        except Exception:
            raise HTTPException(status_code=502, detail="Erreur PawaPay: réponse invalide")
        if not isinstance(data, dict):
            raise HTTPException(status_code=502, detail="Erreur PawaPay: réponse invalide")
        raison = data.get("failureReason") or {}

    if raison or response.status_code not in (200, 201):
        # V325b/V325d : on remonte le code HTTP, le `failureCode` ET le `failureMessage`
        # (« UNSUPPORTED_PARAMETER » seul ne dit pas QUEL paramètre est refusé). Ce sont
        # des étiquettes techniques du prestataire : ni jeton, ni donnée client.
        failure_code = raison.get("failureCode", "") if isinstance(raison, dict) else ""
        failure_msg = raison.get("failureMessage", "") if isinstance(raison, dict) else ""
        logger.error(f"[PAWAPAY] API error: {response.status_code} - {response.text[:300]}")
        details = " / ".join(x for x in (f"HTTP {response.status_code}",
                                         failure_code, (failure_msg or "")[:200]) if x)
        raise HTTPException(
            status_code=502,
            detail=f"Erreur PawaPay: service indisponible ({details})"
        )

    # V325f : le nom du champ d'URL varie selon les versions de l'API/doc. On accepte
    # les variantes connues plutôt que d'échouer sur un simple écart de nommage, et
    # si rien ne correspond, l'erreur DIT quels champs PawaPay a renvoyés (les noms
    # seulement, jamais les valeurs : une URL de paiement porte un jeton de session).
    redirect_url = ""
    for champ in ("redirectUrl", "paymentPageUrl", "paymentUrl", "url", "sessionUrl"):
        valeur = data.get(champ)
        if isinstance(valeur, str) and valeur.startswith("http"):
            redirect_url = valeur
            break

    if not redirect_url:
        logger.error(f"[PAWAPAY] Pas d'URL de paiement dans la réponse: {str(data)[:300]}")
        champs = ", ".join(sorted(data.keys())) if isinstance(data, dict) else type(data).__name__
        raise HTTPException(
            status_code=502,
            detail=f"PawaPay n'a pas renvoyé d'URL de paiement (HTTP {response.status_code}; champs reçus : {champs})"
        )

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
    reponse = {
        "enabled": enabled,
        "flag": await is_pawapay_flag_on(),
        "callback_url": callback_url(),  # à recopier dans le tableau de bord PawaPay
    }
    # V325c : les pays réellement ouverts sur le compte. Ce n'est pas un secret
    # (c'est la liste des marchés du compte) et c'est ce qui manquait pour
    # diagnostiquer le 400 / UNSUPPORTED_PARAMETER du premier test.
    if enabled:
        token, base_url = await get_pawapay_config()
        pays = await get_supported_countries(token, base_url)
        reponse["countries"] = sorted(pays.keys())
        reponse["currencies"] = pays
    return reponse


@router.post("/create-checkout")
async def create_pawapay_checkout(request: PawaPayCheckoutRequest):
    """
    Crée une session de paiement PawaPay (Mobile Money, page hébergée).
    """
    token, base_url = await require_pawapay()

    deposit_id = str(uuid.uuid4())
    # V325c : pays et devise décidés par la configuration RÉELLE du compte
    country, devise = await resoudre_pays(token, base_url, request.country)
    return_url = request.success_url or f"{frontend_url()}/?payment=success&provider=pawapay&tid={deposit_id}"

    # Sauvegarder la transaction en attente AVANT l'appel réseau (recommandation PawaPay)
    await db.pawapay_transactions.insert_one({
        "depositId": deposit_id,
        "amount": request.amount,
        "currency": devise or request.currency,
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
            msisdn=normalize_msisdn(request.customer_phone),
            currency=devise
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

    # V325c : pays/devise réels du compte, puis conversion dans CETTE devise
    country, devise = await resoudre_pays(token, base_url, request.country)
    price_major = montant_dans_devise(pack.get("price", 0), pack.get("price_xof"), devise)
    if price_major <= 0:
        raise HTTPException(status_code=400, detail="Prix invalide pour ce pack")

    deposit_id = str(uuid.uuid4())
    return_url = request.success_url or f"{frontend_url()}/?payment=success&provider=pawapay&tid={deposit_id}#partner-dashboard"

    await db.pawapay_transactions.insert_one({
        "depositId": deposit_id,
        "type": "coach_registration",
        "amount": price_major,
        "currency": devise,
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
            msisdn=normalize_msisdn(request.customer_phone),
            currency=devise
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

    # V325c : pays/devise réels du compte, puis conversion dans CETTE devise
    country, devise = await resoudre_pays(token, base_url, request.country)
    price_major = montant_dans_devise(pack.get("price", 0), pack.get("price_xof"), devise)
    if price_major <= 0:
        raise HTTPException(status_code=400, detail="Prix invalide")

    deposit_id = str(uuid.uuid4())
    return_url = request.success_url or f"{frontend_url()}/dashboard?tab=boutique&payment=success&provider=pawapay"

    await db.pawapay_transactions.insert_one({
        "depositId": deposit_id,
        "type": "credit_purchase",
        "amount": price_major,
        "currency": devise,
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
            return_url=return_url,
            currency=devise
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


# ============================================================================
# V381 — RÉPARTITEUR : POINT D'ENTRÉE UNIQUE DES CALLBACKS PAWAPAY
# ============================================================================
# PawaPay n'accepte qu'UNE seule URL de callback par compte, alors que DEUX
# applications attendent des notifications : ce site et Afroboost Live
# (api-live.afroboost.com, route `POST /pawapay/callback`). Le tableau de bord
# PawaPay de PRODUCTION est réglé sur https://afroboost.com/api/pawapay/callback
# — tout arrive donc ici, et c'est d'ici qu'on répartit.
#
# Avant V381 ce chemin n'existait pas : il tombait sur le catch-all SPA, qui
# refuse le POST (405). Tout callback de production aurait été PERDU — paiement
# encaissé chez l'opérateur, accès jamais accordé.
#
# Le callback ne porte que le `depositId` : le propriétaire du dépôt se déduit
# donc de la base. Connu ici -> traitement local (logique du webhook, inchangée).
# Inconnu ici -> il appartient au live, on le lui transmet tel quel.
#
# `/api/pawapay/webhook` reste servi à l'identique : aucun dépôt déjà en vol
# n'est orphelin, et rien de ce qui marchait ne change.

PAWAPAY_LIVE_CALLBACK_URL = os.environ.get(
    "PAWAPAY_LIVE_CALLBACK_URL",
    "https://api-live.afroboost.com/pawapay/callback",
)


@router.post("/callback")
async def pawapay_callback(request: Request):
    """Point d'entrée unique des callbacks PawaPay — répartit site / live."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    if not isinstance(body, dict):
        body = {}

    deposit_id = body.get("depositId") or (body.get("data") or {}).get("depositId") or ""

    if not deposit_id:
        logger.warning("[PAWAPAY_CALLBACK] Pas de depositId reçu")
        return {"status": "error", "message": "Missing depositId"}

    # À qui appartient ce dépôt ? La base fait foi.
    local_tx = None
    if db is not None:
        try:
            local_tx = await db.pawapay_transactions.find_one({"depositId": deposit_id})
        except Exception as e:
            # Un hoquet de la base ne doit pas faire disparaître la notification :
            # on la traite localement — le webhook re-vérifie de toute façon le
            # statut auprès de PawaPay avant d'accorder quoi que ce soit.
            logger.error(f"[PAWAPAY_CALLBACK] Lecture base impossible ({deposit_id}): {e}")
            return await pawapay_webhook(request)

    # === DÉPÔT DE CE SITE ===
    # `request.json()` est mis en cache par Starlette : le webhook peut relire le
    # corps sans que le flux soit déjà consommé.
    if local_tx:
        logger.info(f"[PAWAPAY_CALLBACK] Dépôt du site: {deposit_id}")
        return await pawapay_webhook(request)

    # === DÉPÔT INCONNU ICI -> IL APPARTIENT À AFROBOOST LIVE ===
    logger.info(f"[PAWAPAY_CALLBACK] Inconnu du site, transmission au live: {deposit_id}")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            reponse = await client.post(
                PAWAPAY_LIVE_CALLBACK_URL,
                json=body,
                headers={"Content-Type": "application/json"},
            )
        logger.info(
            f"[PAWAPAY_CALLBACK] Live a répondu {reponse.status_code} pour {deposit_id}"
        )
        return {
            "status": "ok",
            "message": "Forwarded to live",
            "live_status": reponse.status_code,
        }
    except Exception as e:
        # Panne de transport vers le live (et NON un refus du live) : on renvoie
        # une erreur pour que PawaPay REJOUE le callback plus tard. Répondre 200
        # ici perdrait définitivement la notification d'un paiement encaissé.
        logger.error(f"[PAWAPAY_CALLBACK] Transmission au live impossible ({deposit_id}): {e}")
        raise HTTPException(status_code=502, detail="Live callback unreachable")
