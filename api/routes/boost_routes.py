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
Étape 2 : le bouton Boost — destinations possibles et création du paiement.
Étape 3 : confirmation du paiement -> apparition 48 h + encaissement.
"""
import os
import uuid
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from api.routes.shared import (
    coach_jwt_email, is_super_admin, subscriber_from_request,
    SUPER_ADMIN_EMAILS, DEFAULT_COACH_ID,
)

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


# =====================================================================
# ÉTAPE 2 — BOUTON BOOST : DESTINATIONS ET CRÉATION DU PAIEMENT
# =====================================================================

def url_frontend() -> str:
    return os.environ.get("REACT_APP_FRONTEND_URL", "https://afroboost.com").rstrip("/")


async def charger_publication(pub_id: str) -> dict:
    pub = await db.publications.find_one({"id": pub_id}, {"_id": 0})
    if not pub:
        raise HTTPException(status_code=404, detail="Publication non trouvée")
    return pub


def identite_coach(request: Request) -> str:
    """
    Identité coach/admin de l'appelant : JWT signé en priorité, repli `X-User-Email`
    ensuite — EXACTEMENT le mode transitoire V265 utilisé par les autres routes
    publications (`delete_publication`). Durcir ici seulement bloquerait les
    sessions coach légitimes ouvertes avant le JWT (leçon V310c).
    """
    email = coach_jwt_email(request)
    if email:
        return email
    return (request.headers.get("X-User-Email", "") or "").lower().strip()


async def autoriser_auteur(request: Request, pub: dict, subscriber_code: str = "") -> dict:
    """
    Vérifie que l'appelant a le droit de booster CETTE publication, et renvoie
    de quoi tracer le payeur. Trois profils légitimes, les mêmes que pour la
    suppression (V268b) :
      - l'ABONNÉ auteur, prouvé par son code AFR- (fourni, ou porté par son
        jeton d'appareil) ;
      - le COACH auteur (`coach_id` == lui) ;
      - le SUPER-ADMIN, qui modère l'ensemble du mur.
    Un coach ne peut PAS booster la publication d'un autre — le paiement serait
    prélevé sur son compte pour le contenu d'un tiers.
    """
    code_pub = (pub.get("subscriber_code") or "").strip().upper()

    # --- Chemin abonné : le code fourni, ou celui du jeton d'appareil signé.
    code_fourni = (subscriber_code or "").strip().upper()
    if not code_fourni:
        jeton = subscriber_from_request(request)
        if jeton and jeton.get("code"):
            code_fourni = jeton["code"].strip().upper()
    if code_fourni and code_pub and code_fourni == code_pub:
        return {"payer_email": (pub.get("author_id") or "").lower(), "payer_label": "abonné auteur"}

    # --- Chemin coach / admin.
    email = identite_coach(request)
    if not email:
        raise HTTPException(status_code=401, detail="Authentification requise")
    if is_super_admin(email):
        return {"payer_email": email, "payer_label": email}
    possede = ((pub.get("coach_id") or "").lower() == email
               or (pub.get("subscriber_code") or "").lower() == email)
    if not possede:
        raise HTTPException(status_code=403, detail="Seul l'auteur peut booster sa publication")
    return {"payer_email": email, "payer_label": email}


def vitrine_de_la_publication(pub: dict) -> str:
    """
    Vitrine d'ORIGINE d'une publication : celle de son coach. Y « booster » n'aurait
    aucun sens — la publication y est déjà, et gratuitement.
    """
    return (pub.get("coach_id") or DEFAULT_COACH_ID).lower()


def est_auteur_super_admin(request: Request, pub: dict) -> str:
    """
    V343 (POUVOIR B) — l'appelant est-il le super-admin ET l'AUTEUR de cette
    publication ? Renvoie son email si oui, chaîne vide sinon.

    Pourquoi exiger AUSSI d'être l'auteur : `autoriser_auteur` laisse le
    super-admin agir sur n'importe quelle publication (c'est son rôle de
    modération). Sans cette seconde condition, il pourrait placer GRATUITEMENT
    le contenu d'un tiers sur la vitrine d'un coach — ce que le coach n'a pas
    demandé et pour quoi personne n'aurait payé. La gratuité est donc bornée à
    SES propres publications ; s'il boostait celle d'un autre, il repasserait
    par le paiement normal V342.

    Vérification SERVEUR : l'identité vient du JWT (ou du repli X-User-Email du
    mode transitoire V265, comme partout ailleurs sur les publications), jamais
    d'un drapeau « je suis admin » envoyé par le client.

    LIMITE CONNUE, à lever avec le reste du chantier JWT : tant que le repli
    X-User-Email existe (V265), il reste falsifiable. On ne le ferme PAS ici —
    l'entrée coach du tableau de bord s'authentifie précisément par ce repli et
    n'émet aucun JWT ; l'exiger rendrait la fonction inutilisable pour son seul
    utilisateur légitime (c'est l'incident V310c à la lettre). On TRACE donc
    chaque gratuité obtenue sans jeton signé, pour pouvoir mesurer avant de
    durcir — même démarche que le WARNING `[V265] repli X-User-Email`.
    """
    email = identite_coach(request)
    if not email or not is_super_admin(email):
        return ""
    if not coach_jwt_email(request):
        logger.warning(f"[V343] repli X-User-Email — gratuité accordée à {email} SANS jeton signé "
                       f"(publication {pub.get('id', '?')})")
    # Les trois champs où peut vivre l'identité de l'auteur, selon le chemin de
    # publication : coach (`coach_id` / `subscriber_code` = son email) ou
    # résolution d'email a posteriori (`author_id`).
    for champ in ("coach_id", "author_id", "subscriber_code"):
        if (pub.get(champ) or "").strip().lower() == email:
            return email
    return ""


def fin_de_boost(pub: dict) -> str:
    """
    V343 — date de fin d'apparition sur la vitrine de destination.

    48 h par défaut. Si la publication a été créée « sans limite » (POUVOIR A,
    `no_expiry`), son apparition n'a pas de raison d'être plus courte que la
    publication elle-même : on réutilise le mécanisme V331 (date très lointaine),
    exactement comme pour `expires_at`.
    """
    maintenant = datetime.now(timezone.utc)
    if not pub.get("no_expiry"):
        return (maintenant + timedelta(hours=V342_BOOST_HOURS)).isoformat()
    try:
        from api.server import V331_EXPIRATION_LOINTAINE_ANNEES as annees
    except Exception:
        annees = 100  # même valeur que V331 ; repli si l'import n'est pas résoluble
    # `timedelta` plutôt que `replace(year=...)` : ce dernier lève une ValueError
    # un 29 février (le 29/02 de l'année cible n'existe pas une fois sur quatre).
    # Seule compte ici la nature de la date — très lointaine, donc jamais atteinte.
    return (maintenant + timedelta(days=365 * annees)).isoformat()


async def activer_boost_gratuit(pub: dict, cible: str, admin: str) -> dict:
    """
    V343 (POUVOIR B) — apparition GRATUITE, réservée au super-admin auteur.

    Ce chemin ne crée AUCUN paiement (ni Stripe ni PawaPay), n'encaisse rien et
    n'écrit RIEN dans `payment_transactions` : personne ne reçoit d'argent, le
    montant est 0 et il n'y a pas de bénéficiaire. Une trace est tout de même
    conservée dans `boost_transactions`, pour que l'apparition soit auditable
    comme n'importe quelle autre.

    IDEMPOTENCE : si cette publication apparaît DÉJÀ gratuitement sur CETTE même
    vitrine et que l'apparition court encore, on renvoie l'existant sans rien
    réécrire — rappeler l'action ne rallonge donc jamais la durée et n'empile pas
    les entrées. Choisir une AUTRE vitrine remplace la destination, conformément
    au modèle V342 (une publication apparaît sur une vitrine à la fois).
    """
    maintenant_iso = datetime.now(timezone.utc).isoformat()
    pub_id = pub.get("id", "")

    if (pub.get("boost_target_vitrine") == cible
            and pub.get("boost_provider") == "admin_gratuit"
            and (pub.get("boosted_until") or "") > maintenant_iso):
        existant = await db.boost_transactions.find_one(
            {"publication_id": pub_id, "target": cible, "provider": "admin_gratuit",
             "status": "completed"},
            {"_id": 0, "boost_id": 1},
        ) or {}
        logger.info(f"[V343] Boost gratuit déjà actif pour {pub_id} sur « {cible} » — inchangé")
        return {
            "success": True, "gratuit": True, "status": "already_processed",
            "boost_id": existant.get("boost_id", ""), "target": cible,
            "amount_chf": 0, "currency": "CHF",
            "boosted_until": pub.get("boosted_until", ""),
        }

    boost_id = f"boost_{uuid.uuid4().hex[:16]}"
    fin = fin_de_boost(pub)

    await db.boost_transactions.insert_one({
        "boost_id": boost_id,
        "publication_id": pub_id,
        "target": cible,
        "payee": None,                 # personne n'encaisse : c'est gratuit
        "payer_email": admin,
        "payer_label": admin,
        "provider": "admin_gratuit",
        "amount_chf": 0,
        "currency": "CHF",
        "status": "completed",
        "created_at": maintenant_iso,
        "completed_at": maintenant_iso,
        "boosted_until": fin,
    })

    maj = await db.publications.update_one(
        {"id": pub_id},
        {"$set": {
            "boost_target_vitrine": cible,
            "boosted_until": fin,
            "boost_payment_id": boost_id,
            "boost_provider": "admin_gratuit",
            "boost_amount_chf": 0,
            "boost_payer": admin,
            "boost_payee": None,
        }},
    )
    if not getattr(maj, "matched_count", 0):
        raise HTTPException(status_code=404, detail="Publication non trouvée")

    logger.info(f"[V343] Boost GRATUIT super-admin : publication {pub_id} visible sur "
                f"« {cible} » jusqu'au {fin} — aucun paiement, aucun encaissement")
    return {
        "success": True, "gratuit": True, "status": "completed",
        "boost_id": boost_id, "target": cible,
        "amount_chf": 0, "currency": "CHF", "payee": None,
        "boosted_until": fin,
    }


def beneficiaire_de(target: str) -> str:
    """
    Propriétaire de la vitrine de destination = celui qui ENCAISSE.
      - `home` -> la page d'accueil est la vitrine du super-admin ;
      - sinon  -> le coach dont c'est la vitrine.
    """
    cible = (target or "").strip().lower()
    if cible in (V342_CIBLE_ACCUEIL, "", DEFAULT_COACH_ID.lower()):
        return SUPER_ADMIN_EMAILS[0].lower()
    return cible


async def cles_stripe(beneficiaire: str):
    """
    Clé Stripe du BÉNÉFICIAIRE — même routage que le checkout unifié :
    super-admin -> variables d'environnement ; partenaire -> `partner_payment_config`.
    Renvoie (cle, erreur).
    """
    if is_super_admin(beneficiaire):
        cle = os.environ.get("STRIPE_SECRET_KEY", "")
        if not cle:
            return None, "Le paiement par carte n'est pas configuré pour cette vitrine."
        return cle, None

    cfg = await db["partner_payment_config"].find_one({"coach_email": beneficiaire})
    if not cfg or not cfg.get("stripe_enabled") or not cfg.get("stripe_secret_key"):
        return None, "Le propriétaire de cette vitrine n'accepte pas encore le paiement par carte."
    return cfg["stripe_secret_key"], None


async def config_pawapay(beneficiaire: str):
    """
    Configuration PawaPay du BÉNÉFICIAIRE. Renvoie (token, base_url, erreur).

    Le drapeau global `PAWAPAY_ENABLED` reste maître : tant qu'il est OFF, PawaPay
    n'est proposé à personne (même règle que partout ailleurs depuis V325).
    """
    from api.routes.pawapay_routes import (
        is_pawapay_flag_on, get_pawapay_config,
        PAWAPAY_PROD_URL, PAWAPAY_SANDBOX_URL,
    )

    if not await is_pawapay_flag_on():
        return None, None, "Le Mobile Money n'est pas disponible actuellement."

    if is_super_admin(beneficiaire):
        token, base_url = await get_pawapay_config()
        if not token:
            return None, None, "Le Mobile Money n'est pas configuré pour cette vitrine."
        return token, base_url, None

    cfg = await db["partner_payment_config"].find_one({"coach_email": beneficiaire})
    if not cfg or not cfg.get("pawapay_enabled") or not cfg.get("pawapay_api_token"):
        return None, None, "Le propriétaire de cette vitrine n'accepte pas encore le Mobile Money."
    base_url = PAWAPAY_PROD_URL if cfg.get("pawapay_mode") == "live" else PAWAPAY_SANDBOX_URL
    return cfg["pawapay_api_token"], base_url, None


async def moyens_disponibles(beneficiaire: str) -> list:
    """Moyens de paiement réellement utilisables pour encaisser vers ce bénéficiaire."""
    moyens = []
    cle, _ = await cles_stripe(beneficiaire)
    if cle:
        moyens.append("stripe")
    token, _, _ = await config_pawapay(beneficiaire)
    if token:
        moyens.append("pawapay")
    return moyens


@router.get("/publications/{pub_id}/boost/destinations")
async def boost_destinations(pub_id: str, request: Request, subscriber_code: str = ""):
    """
    Vitrines sur lesquelles CETTE publication peut être boostée.

    On exclut la vitrine d'origine : l'auteur y est déjà, gratuitement. Chaque
    destination indique les moyens de paiement réellement disponibles pour elle,
    afin que l'auteur ne choisisse jamais une vitrine qui ne peut pas encaisser.
    """
    pub = await charger_publication(pub_id)
    await autoriser_auteur(request, pub, subscriber_code)

    # V343 (POUVOIR B) : pour le super-admin AUTEUR, l'apparition est gratuite.
    # `gratuit` sert à deux choses côté client : afficher « Publier gratuitement
    # ici » au lieu de « Payer N CHF », et ne pas griser les vitrines dont le
    # paiement n'est pas configuré — sans paiement, cela n'a plus d'importance.
    gratuit = bool(est_auteur_super_admin(request, pub))

    origine = vitrine_de_la_publication(pub)
    admin = SUPER_ADMIN_EMAILS[0].lower()
    destinations = []

    # La page d'accueil — sauf si c'est déjà la vitrine d'origine de la publication.
    if origine != admin:
        destinations.append({
            "target": V342_CIBLE_ACCUEIL,
            "name": "Page d'accueil",
            "kind": "home",
            "providers": await moyens_disponibles(admin),
        })

    # Les vitrines des autres coachs.
    coachs = await db.coaches.find(
        {"is_active": True},
        {"_id": 0, "email": 1, "name": 1, "platform_name": 1},
    ).to_list(50)
    vus = set()
    for c in coachs:
        email = (c.get("email") or "").lower().strip()
        if not email or email == origine or email in vus or is_super_admin(email):
            continue
        vus.add(email)
        destinations.append({
            "target": email,
            "name": c.get("platform_name") or c.get("name") or email,
            "kind": "coach",
            "providers": await moyens_disponibles(email),
        })

    return {
        "destinations": destinations,
        "price_chf": await lire_prix_boost(),
        "currency": "CHF",
        "hours": V342_BOOST_HOURS,
        # V343 : vrai UNIQUEMENT pour le super-admin auteur. Le serveur ne se fie
        # pas à ce qu'en fera le client : la gratuité est re-vérifiée au checkout.
        "gratuit": gratuit,
        # V343 : si la publication est « sans limite » (POUVOIR A), son apparition
        # sur la vitrine de destination l'est aussi.
        "sans_limite": bool(gratuit and pub.get("no_expiry")),
    }


class BoostCheckoutRequest(BaseModel):
    target: str
    # V343 : facultatif — le chemin GRATUIT du super-admin n'utilise aucun
    # prestataire. Le chemin PAYANT continue d'exiger une valeur valide (400 sinon).
    provider: Optional[str] = ""         # "stripe" | "pawapay"
    subscriber_code: Optional[str] = ""
    customer_phone: Optional[str] = ""  # Mobile Money uniquement
    customer_email: Optional[str] = ""
    country: Optional[str] = ""
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


@router.post("/publications/{pub_id}/boost/checkout")
async def boost_checkout(pub_id: str, payload: BoostCheckoutRequest, request: Request):
    """
    Ouvre le paiement d'un Boost. Aucune apparition n'est accordée ici : cet
    endpoint ne fait QUE créer le paiement. L'apparition 48 h est décidée
    exclusivement à la confirmation du prestataire (étape 3).
    """
    pub = await charger_publication(pub_id)
    payeur = await autoriser_auteur(request, pub, payload.subscriber_code or "")

    cible = (payload.target or "").strip().lower()
    origine = vitrine_de_la_publication(pub)
    admin = SUPER_ADMIN_EMAILS[0].lower()

    if cible == V342_CIBLE_ACCUEIL and origine == admin:
        raise HTTPException(status_code=400,
                            detail="Cette publication est déjà sur la page d'accueil — c'est gratuit.")
    if cible not in (V342_CIBLE_ACCUEIL,) and cible == origine:
        raise HTTPException(status_code=400,
                            detail="Publier sur votre propre vitrine est gratuit — le Boost est inutile ici.")

    # La destination doit exister réellement (pas d'email inventé par le client).
    if cible != V342_CIBLE_ACCUEIL:
        connu = await db.coaches.find_one({"email": cible, "is_active": True}, {"_id": 0, "email": 1})
        if not connu:
            raise HTTPException(status_code=404, detail="Vitrine de destination inconnue")

    # =====================================================================
    # V343 (POUVOIR B) — COURT-CIRCUIT GRATUIT DU SUPER-ADMIN
    # =====================================================================
    # Placé APRÈS toutes les validations de destination (elles valent pour lui
    # aussi) et AVANT toute création de paiement : aucun appel Stripe/PawaPay
    # n'est émis, aucun montant n'est calculé, rien n'est encaissé.
    #
    # C'est le SEUL endroit qui accorde une apparition sans paiement, et il est
    # gardé par `est_auteur_super_admin` — une vérification serveur. Pour tout
    # autre appelant, l'exécution continue vers le chemin payant V342, inchangé :
    # un non-admin ne peut donc en aucun cas apparaître ailleurs sans paiement
    # confirmé par le prestataire.
    admin_auteur = est_auteur_super_admin(request, pub)
    if admin_auteur:
        return await activer_boost_gratuit(pub, cible, admin_auteur)

    beneficiaire = beneficiaire_de(cible)

    # MONTANT : lu au serveur, jamais reçu du client.
    prix = await lire_prix_boost()

    provider = (payload.provider or "").strip().lower()
    if provider not in ("stripe", "pawapay"):
        raise HTTPException(status_code=400, detail="Moyen de paiement inconnu")

    boost_id = f"boost_{uuid.uuid4().hex[:16]}"
    retour = payload.success_url or f"{url_frontend()}/?boost=success&bid={boost_id}"
    annule = payload.cancel_url or f"{url_frontend()}/?boost=cancelled&bid={boost_id}"

    # La transaction est écrite AVANT l'appel réseau : si celui-ci échoue à
    # mi-chemin, la référence existe et le paiement reste rattachable.
    transaction = {
        "boost_id": boost_id,
        "publication_id": pub_id,
        "target": cible,
        "payee": beneficiaire,              # qui encaisse = propriétaire de la vitrine cible
        "payer_email": payeur.get("payer_email", ""),
        "payer_label": payeur.get("payer_label", ""),
        "provider": provider,
        "amount_chf": prix,
        "currency": "CHF",
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.boost_transactions.insert_one(dict(transaction))

    # ===== STRIPE (carte + TWINT en CHF) =====
    if provider == "stripe":
        cle, erreur = await cles_stripe(beneficiaire)
        if erreur:
            await db.boost_transactions.update_one(
                {"boost_id": boost_id}, {"$set": {"status": "unavailable", "error": erreur}})
            raise HTTPException(status_code=400, detail=erreur)

        try:
            import stripe
            stripe.api_key = cle

            ligne = {
                "price_data": {
                    "currency": "chf",
                    "product_data": {"name": f"Boost {V342_BOOST_HOURS} h — publication Afroboost"},
                    "unit_amount": int(prix * 100),
                },
                "quantity": 1,
            }
            meta = {
                "type": "publication_boost",
                "boost_id": boost_id,
                "publication_id": pub_id,
                "target": cible,
                "payee": beneficiaire,
            }

            session = None
            # TWINT d'abord (compte suisse), repli carte seule si non activé.
            for moyens in (["card", "twint"], ["card"]):
                try:
                    session = stripe.checkout.Session.create(
                        payment_method_types=moyens,
                        line_items=[ligne],
                        mode="payment",
                        success_url=retour,
                        cancel_url=annule,
                        client_reference_id=boost_id,
                        metadata=meta,
                    )
                    break
                except Exception as err:
                    logger.warning(f"[V342] Stripe {moyens} refusé ({err}), essai suivant…")
                    continue
            if not session:
                raise Exception("Session Stripe impossible à créer")

            await db.boost_transactions.update_one(
                {"boost_id": boost_id}, {"$set": {"stripe_session_id": session.id}})
            logger.info(f"[V342] Boost {boost_id} : paiement Stripe ouvert, {prix} CHF -> {beneficiaire}")
            return {
                "success": True,
                "boost_id": boost_id,
                "provider": "stripe",
                "amount_chf": prix,
                "currency": "CHF",
                "payee": beneficiaire,
                "payment_url": session.url,
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[V342] Boost {boost_id} : échec Stripe — {e}")
            await db.boost_transactions.update_one(
                {"boost_id": boost_id}, {"$set": {"status": "failed", "error": str(e)}})
            raise HTTPException(status_code=502, detail="Le paiement n'a pas pu être ouvert. Réessayez.")

    # ===== PAWAPAY (Mobile Money) =====
    token, base_url, erreur = await config_pawapay(beneficiaire)
    if erreur:
        await db.boost_transactions.update_one(
            {"boost_id": boost_id}, {"$set": {"status": "unavailable", "error": erreur}})
        raise HTTPException(status_code=400, detail=erreur)

    from api.routes.pawapay_routes import (
        resoudre_pays, montant_dans_devise, normalize_msisdn, create_pawapay_deposit,
    )

    try:
        pays, devise = await resoudre_pays(token, base_url, payload.country or "")
        montant = montant_dans_devise(prix, None, devise)

        # Le dépôt PawaPay est identifié par un UUID ; on le relie au Boost.
        deposit_id = str(uuid.uuid4())
        await db.pawapay_transactions.insert_one({
            "depositId": deposit_id,
            "amount": montant,
            "currency": devise,
            "country": pays,
            "description": "Boost publication Afroboost",
            "customer_name": payeur.get("payer_label", ""),
            "customer_email": payload.customer_email or payeur.get("payer_email", ""),
            "customer_phone": payload.customer_phone or "",
            # `type` est ce que lit `activate_after_payment` pour savoir quoi activer.
            "type": "publication_boost",
            "boost_id": boost_id,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        await db.boost_transactions.update_one(
            {"boost_id": boost_id},
            {"$set": {"deposit_id": deposit_id, "amount_local": montant, "currency_local": devise}})

        url_paiement = await create_pawapay_deposit(
            token=token,
            base_url=base_url,
            deposit_id=deposit_id,
            amount=montant,
            country=pays,
            reason="Boost publication Afroboost",
            return_url=retour,
            msisdn=normalize_msisdn(payload.customer_phone or ""),
            currency=devise,
        )
        logger.info(f"[V342] Boost {boost_id} : paiement PawaPay ouvert, {prix} CHF -> {beneficiaire}")
        return {
            "success": True,
            "boost_id": boost_id,
            "provider": "pawapay",
            "amount_chf": prix,
            "currency": "CHF",
            "amount_local": montant,
            "currency_local": devise,
            "payee": beneficiaire,
            "payment_url": url_paiement,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[V342] Boost {boost_id} : échec PawaPay — {e}")
        await db.boost_transactions.update_one(
            {"boost_id": boost_id}, {"$set": {"status": "failed", "error": str(e)}})
        raise HTTPException(status_code=502, detail="Le paiement n'a pas pu être ouvert. Réessayez.")


# =====================================================================
# ÉTAPE 3 — CONFIRMATION DU PAIEMENT : APPARITION 48 H + ENCAISSEMENT
# =====================================================================
#
# RÈGLE CARDINALE : aucune apparition n'est accordée sur la foi d'un clic, ni
# même sur la foi du corps d'un webhook. Le corps reçu ne sert QU'À identifier le
# Boost concerné ; le statut réel est ensuite redemandé au prestataire, qui est la
# seule source de vérité (même prudence que le webhook PawaPay depuis V325).
#
# IDEMPOTENCE : `boost_transactions.status` passe à « completed » une seule fois.
# Un webhook rejoué, ou un retour navigateur rafraîchi, retombe sur cette garde et
# ne rallonge JAMAIS la durée d'affichage.


async def enregistrer_encaissement(tx: dict, reference: str):
    """
    Inscrit la vente au crédit du BÉNÉFICIAIRE, dans la collection que lit déjà
    le tableau des transactions du coach (`/dashboard/all-transactions`). Le Boost
    apparaît donc comme n'importe quelle autre vente, sans toucher à cet endpoint.
    """
    await db.payment_transactions.insert_one({
        "id": str(uuid.uuid4()),
        "session_id": reference or tx.get("boost_id", ""),
        "coach_id": tx.get("payee", ""),          # <- qui encaisse
        "payment_status": "paid",
        "status": "completed",
        "amount_total": int(round(float(tx.get("amount_chf") or 0) * 100)),
        "currency": "chf",
        "provider": tx.get("provider", ""),
        "source": "publication_boost",
        "boost_id": tx.get("boost_id", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "customer_name": tx.get("payer_label", "") or "Auteur",
            "customer_email": tx.get("payer_email", ""),
            "product_name": f"Boost publication ({V342_BOOST_HOURS} h)",
            "publication_id": tx.get("publication_id", ""),
            "target": tx.get("target", ""),
        },
    })


async def activer_boost(boost_id: str, *, provider: str, reference: str = "") -> dict:
    """
    Accorde l'apparition de 48 h sur la vitrine de destination et enregistre
    l'encaissement. À n'appeler QU'APRÈS vérification du paiement auprès du
    prestataire. Idempotent.
    """
    tx = await db.boost_transactions.find_one({"boost_id": boost_id}, {"_id": 0})
    if not tx:
        logger.warning(f"[V342] Boost inconnu à l'activation: {boost_id}")
        return {"status": "unknown"}

    if tx.get("status") == "completed":
        return {"status": "already_processed", "boost_id": boost_id}

    fin = datetime.now(timezone.utc) + timedelta(hours=V342_BOOST_HOURS)

    # La publication d'ORIGINE n'est pas touchée dans sa vitrine : on n'ajoute que
    # les champs d'apparition temporaire ailleurs (ni `coach_id`, ni `expires_at`).
    maj = await db.publications.update_one(
        {"id": tx.get("publication_id", "")},
        {"$set": {
            "boost_target_vitrine": tx.get("target", ""),
            "boosted_until": fin.isoformat(),
            "boost_payment_id": reference or boost_id,
            "boost_provider": provider,
            "boost_amount_chf": tx.get("amount_chf", 0),
            "boost_payer": tx.get("payer_email", "") or tx.get("payer_label", ""),
            "boost_payee": tx.get("payee", ""),
        }},
    )
    if not getattr(maj, "matched_count", 0):
        # La publication a pu être supprimée entre le paiement et la confirmation.
        logger.error(f"[V342] Boost {boost_id} payé mais publication introuvable "
                     f"({tx.get('publication_id')}) — encaissement conservé.")

    await db.boost_transactions.update_one(
        {"boost_id": boost_id},
        {"$set": {
            "status": "completed",
            "boosted_until": fin.isoformat(),
            "provider_reference": reference,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }},
    )

    await enregistrer_encaissement(tx, reference)

    logger.info(f"[V342] Boost {boost_id} confirmé : publication {tx.get('publication_id')} "
                f"visible {V342_BOOST_HOURS} h sur « {tx.get('target')} », "
                f"{tx.get('amount_chf')} CHF encaissés par {tx.get('payee')}")
    return {"status": "ok", "boost_id": boost_id, "boosted_until": fin.isoformat()}


async def verifier_paiement_stripe(tx: dict):
    """
    Redemande à Stripe l'état RÉEL de la session, avec la clé du bénéficiaire.
    Renvoie (paye: bool, reference: str, erreur: str).

    On ne se contente pas de la signature du webhook : chaque partenaire encaisse
    sur SON compte Stripe, avec SON secret de webhook — une signature vérifiable
    par la plateforme n'existe donc que pour les paiements de l'admin. Redemander
    l'état à Stripe protège TOUS les cas, y compris un webhook forgé.
    """
    session_id = tx.get("stripe_session_id", "")
    if not session_id:
        return False, "", "Aucune session Stripe rattachée à ce Boost"

    cle, erreur = await cles_stripe(tx.get("payee", ""))
    if erreur:
        return False, "", erreur

    try:
        import stripe
        stripe.api_key = cle
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        logger.error(f"[V342] Vérification Stripe impossible ({session_id}): {e}")
        return False, "", "Vérification du paiement impossible"

    statut = (getattr(session, "payment_status", "") or "")
    if statut != "paid":
        return False, session_id, f"Paiement non abouti (état Stripe : {statut or 'inconnu'})"
    return True, session_id, ""


@router.post("/boost/webhook/stripe")
async def boost_webhook_stripe(request: Request):
    """
    Webhook Stripe des Boosts (`checkout.session.completed`).

    Le corps ne sert qu'à retrouver le `boost_id`. La signature est vérifiée quand
    `STRIPE_WEBHOOK_SECRET` est disponible ET que le paiement va à l'admin ; dans
    tous les cas, l'état du paiement est redemandé à Stripe avant d'accorder quoi
    que ce soit. Un événement qui ne concerne pas un Boost est ignoré.
    """
    corps = await request.body()

    secret_webhook = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    signature = request.headers.get("stripe-signature", "")
    evenement = None
    if secret_webhook and signature:
        try:
            import stripe
            evenement = stripe.Webhook.construct_event(corps, signature, secret_webhook)
        except Exception:
            # Signature invalide pour NOTRE secret : c'est le cas normal quand le
            # paiement va à un partenaire (autre compte, autre secret). On ne
            # rejette pas — on retombe sur la re-vérification auprès de Stripe.
            evenement = None

    if evenement is None:
        import json
        try:
            evenement = json.loads(corps)
        except Exception:
            raise HTTPException(status_code=400, detail="Corps illisible")

    if (evenement.get("type") if isinstance(evenement, dict) else evenement["type"]) != "checkout.session.completed":
        return {"status": "ignored"}

    session = evenement["data"]["object"]
    meta = session.get("metadata") or {}
    if meta.get("type") != "publication_boost":
        return {"status": "ignored"}

    boost_id = meta.get("boost_id") or session.get("client_reference_id") or ""
    if not boost_id:
        return {"status": "no_boost_id"}

    tx = await db.boost_transactions.find_one({"boost_id": boost_id}, {"_id": 0})
    if not tx:
        return {"status": "unknown_boost"}
    if tx.get("status") == "completed":
        return {"status": "already_processed"}

    paye, reference, erreur = await verifier_paiement_stripe(tx)
    if not paye:
        logger.warning(f"[V342] Webhook Boost {boost_id} ignoré : {erreur}")
        return {"status": "not_paid"}

    return await activer_boost(boost_id, provider="stripe", reference=reference)


@router.get("/publications/boost/confirm/{boost_id}")
async def boost_confirm(boost_id: str):
    """
    Confirmation au RETOUR du paiement (page `?boost=success`).

    Indispensable en place de marché : le compte Stripe d'un partenaire n'envoie
    pas ses webhooks à Afroboost tant qu'il ne les a pas configurés lui-même. Sans
    ce point de contrôle, un Boost payé chez un coach ne s'activerait jamais.
    Ce n'est PAS un raccourci : l'état est redemandé à Stripe exactement comme
    dans le webhook, donc appeler cette route sans avoir payé n'accorde rien.
    """
    tx = await db.boost_transactions.find_one({"boost_id": boost_id}, {"_id": 0})
    if not tx:
        raise HTTPException(status_code=404, detail="Boost inconnu")

    if tx.get("status") == "completed":
        return {"status": "completed", "boosted_until": tx.get("boosted_until", ""),
                "target": tx.get("target", "")}

    if tx.get("provider") == "stripe":
        paye, reference, erreur = await verifier_paiement_stripe(tx)
        if paye:
            resultat = await activer_boost(boost_id, provider="stripe", reference=reference)
            return {"status": "completed", "boosted_until": resultat.get("boosted_until", ""),
                    "target": tx.get("target", "")}
        return {"status": "pending", "message": erreur}

    # PawaPay : c'est son propre webhook qui confirme (il re-vérifie déjà auprès
    # de l'API PawaPay). Ici on ne fait que rapporter l'état courant.
    return {"status": tx.get("status", "pending"), "target": tx.get("target", "")}
