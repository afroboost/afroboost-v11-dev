# shared.py - Constantes et helpers partagés v9.5.6
from datetime import datetime, timezone, timedelta
import os
import logging

logger = logging.getLogger(__name__)


# === V296 : JETON D'APPAREIL ABONNÉ (« le code est le secret, l'appareil est mémorisé ») ===
#
# But : fermer la faille « email -> code » sans alourdir l'expérience. L'abonné
# entre son code UNE fois par appareil ; le backend délivre un jeton signé
# (même mécanisme JWT que le coach : JWT_SECRET, HS256) qui prouve ensuite qu'il
# détient un code valide. Distinct du JWT coach par `type: "subscriber"` et
# transporté dans l'en-tête `X-Subscriber-Token` (pour NE PAS écraser le
# `Authorization: Bearer` du coach).
#
# GARDE-FOU CAPITAL : si `JWT_SECRET` n'est pas posé, aucun jeton n'est émis et
# rien n'est masqué (comportement d'avant, à l'identique) — comme la transition
# V265. Le durcissement ne s'active donc qu'une fois le secret en place.

def jwt_secret_is_set() -> bool:
    return bool(os.environ.get("JWT_SECRET", ""))


def make_subscriber_token(code: str, email: str, days: int = 90) -> str:
    """Émet un jeton abonné signé { type:"subscriber", code, email }, valide `days` jours.
    Renvoie '' si le secret n'est pas posé (jeton impossible -> chemins existants)."""
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        return ""
    try:
        import jwt as _pyjwt
        now = datetime.now(timezone.utc)
        payload = {
            "type": "subscriber",
            "code": (code or "").strip().upper(),
            "email": (email or "").strip().lower(),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=days)).timestamp()),
        }
        tok = _pyjwt.encode(payload, secret, algorithm="HS256")
        return tok.decode("utf-8") if isinstance(tok, bytes) else tok
    except Exception:
        return ""


def subscriber_from_request(request):
    """Retourne { code, email } si un jeton abonné VALIDE est présent, sinon None.
    Cherche dans l'en-tête X-Subscriber-Token (primaire) puis Authorization Bearer
    (uniquement si le payload est de type "subscriber", pour ne pas confondre avec
    le JWT coach)."""
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        return None
    tok = (request.headers.get("X-Subscriber-Token", "") or "").strip()
    if not tok:
        auth = request.headers.get("Authorization", "") or ""
        if auth.lower().startswith("bearer "):
            tok = auth.split(" ", 1)[1].strip()
    if not tok:
        return None
    try:
        import jwt as _pyjwt
        payload = _pyjwt.decode(tok, secret, algorithms=["HS256"])
        if payload.get("type") != "subscriber":
            return None
        return {
            "code": (payload.get("code") or "").strip().upper(),
            "email": (payload.get("email") or "").strip().lower(),
        }
    except Exception:
        return None


def coach_jwt_email(request) -> str:
    """Email coach depuis un JWT SIGNÉ et vérifié (jamais X-User-Email seul, qui est
    falsifiable). Sert à autoriser un coach/admin à voir les codes en clair. '' sinon."""
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        return ""
    try:
        auth = request.headers.get("Authorization", "") or ""
        if not auth.lower().startswith("bearer "):
            return ""
        tok = auth.split(" ", 1)[1].strip()
        if not tok:
            return ""
        import jwt as _pyjwt
        payload = _pyjwt.decode(tok, secret, algorithms=["HS256"])
        if payload.get("type") == "subscriber":
            return ""  # un jeton abonné n'est pas un coach
        return (payload.get("email") or "").strip().lower()
    except Exception:
        return ""

# v9.5.6: Liste des Super Admins autorisés
SUPER_ADMIN_EMAILS = [
    "contact.artboost@gmail.com",
    "afroboost.bassi@gmail.com"
]
SUPER_ADMIN_EMAIL = "contact.artboost@gmail.com"  # Legacy compatibilité
DEFAULT_COACH_ID = SUPER_ADMIN_EMAILS[0]  # V244: etait "bassi_default" (sentinelle sans compte, invisible a tout coach). Pointe desormais sur l'admin, seul coach reel — les replis coach_id inconnu lui reviennent.
ROLE_SUPER_ADMIN = "super_admin"
ROLE_COACH = "coach"
ROLE_USER = "user"

def is_super_admin(email: str) -> bool:
    """Vérifie si l'email est celui d'un Super Admin"""
    return email and email.lower().strip() in [e.lower() for e in SUPER_ADMIN_EMAILS]


# =====================================================================
# V344 — LES POUVOIRS SUPER-ADMIN SUR UNE IDENTITÉ *SIGNÉE*
# =====================================================================
# Constat V344 : deux privilèges s'obtenaient encore avec un simple en-tête
# `X-User-Email` (repli transitoire V265), c'est-à-dire une valeur écrite par le
# navigateur, donc falsifiable :
#   1. `no_expiry` — publication permanente (Pouvoir A, V343) ;
#   2. la gratuité du Boost vers une autre vitrine (Pouvoir B, V343).
# Les autres écritures réservées (prix du Boost V342, `PUT /feature-flags`, cron
# V330, cockpit V334) exigeaient DÉJÀ un jeton signé — elles ne changent pas.
#
# POURQUOI UN INTERRUPTEUR ET PAS UN VERROU IMMÉDIAT : le propriétaire entre
# aujourd'hui par reconnaissance localStorage, SANS mot de passe, donc SANS jeton
# signé. Fermer le repli d'un coup le mettrait dehors — c'est exactement
# l'incident V310c (dashboard vide, revert 0e12578). On livre donc le verrou
# OFF ; il ne se ferme qu'une fois prouvé que le propriétaire, connecté par
# `/auth/login`, garde ses trois pouvoirs. Même pattern que `REQUIRE_COACH_JWT`
# (V319) : basculable sans redéploiement, et donc utilisable en kill-switch.

V344_FLAG = "SUPERADMIN_JWT_STRICT"


def super_admin_signe(request) -> str:
    """
    V344 — email du super-admin PROUVÉ par un jeton signé, '' sinon.

    Aucun repli : `coach_jwt_email` vérifie la signature HS256 et l'expiration,
    et ne lit jamais `X-User-Email`. C'est le seul helper autorisé à accorder un
    privilège super-admin quand le mode strict est actif.
    """
    email = coach_jwt_email(request)
    return email if (email and is_super_admin(email)) else ""


async def v344_jwt_strict_actif(database) -> bool:
    """
    V344 — le mode strict est-il activé ? Défaut FALSE (comportement V343).

    REPLI VOLONTAIREMENT OUVERT : une base injoignable renvoie False, donc le
    comportement actuel. Échouer « fermé » ici verrouillerait le propriétaire
    dehors sur un simple hoquet de MongoDB Atlas — précisément ce qu'on cherche
    à ne jamais reproduire.
    """
    if database is None:
        return False
    try:
        flags = await database.feature_flags.find_one({"id": "feature_flags"}, {"_id": 0}) or {}
        return bool(flags.get(V344_FLAG, False))
    except Exception as e:
        logger.warning(f"[V344] Drapeau {V344_FLAG} illisible ({e}) — on garde le comportement V343")
        return False

def hex_to_rgb_triplet(hex_color: str) -> str:
    """V259: « r, g, b » d'une couleur #rrggbb, pour les rgba() des emails."""
    try:
        h = (hex_color or "").strip().lstrip("#")
        if len(h) == 3:
            h = h[0] * 2 + h[1] * 2 + h[2] * 2
        if len(h) != 6:
            raise ValueError(h)
        return "%d, %d, %d" % (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except Exception:
        return "217, 28, 210"


async def get_primary_color(db, coach_email: str = "") -> str:
    """V259: couleur de marque a injecter dans les emails HTML.

    Un email ne peut pas lire les variables CSS du site : la couleur doit y
    partir en dur, donc etre relue en base au moment de l'envoi.

    Le concept est MULTI-TENANT (`concept_{email}` par coach, `concept` pour
    l'administration). On lit donc d'abord celui du coach concerne quand on le
    connait — sans quoi l'email d'un partenaire porterait la couleur d'un autre.
    Repli sur le concept global, puis sur le rose historique : une couleur
    illisible ne doit jamais empecher un email de partir.
    """
    try:
        if coach_email:
            doc = await db.concept.find_one(
                {"id": "concept_" + coach_email.lower().strip()},
                {"_id": 0, "primaryColor": 1}
            )
            if doc and doc.get("primaryColor"):
                return doc["primaryColor"]
        doc = await db.concept.find_one({"id": "concept"}, {"_id": 0, "primaryColor": 1})
        if doc and doc.get("primaryColor"):
            return doc["primaryColor"]
    except Exception as e:  # jamais bloquant : l'email prime sur sa couleur
        logger.warning(f"[V259] Couleur de marque non lue, repli sur le defaut: {e}")
    return "#D91CD2"


def get_coach_filter(email: str) -> dict:
    """Retourne le filtre MongoDB pour l'isolation des données coach"""
    if is_super_admin(email):
        return {}
    return {"coach_id": email.lower().strip()}


# === V385 : DURÉE DE VALIDITÉ DES CODES CRÉÉS AUTOMATIQUEMENT ===
#
# Un code créé après paiement doit porter la MÊME durée que ceux créés à la main
# depuis « Code promo / partenaire » : DEUX MOIS. Référence mesurée en base —
# `AFR-53F288` (source `admin_manual`) expire exactement 60 jours après sa
# création.
#
# Avant V385, les deux chemins automatiques (Stripe et Mobile Money) n'écrivaient
# AUCUN `expiresAt`. Le code était donc valable indéfiniment, ce qui n'est ni la
# règle commerciale ni ce que montrent les codes existants.
#
# Constante PARTAGÉE, et c'est le point : Stripe et PawaPay créent leurs codes
# dans deux fichiers différents (`server.py` et `payment_activation.py`). Deux
# valeurs écrites séparément auraient divergé à la première évolution — c'est
# exactement ainsi que les noms de champs des codes avaient divergé (V384).
#
# Les 6 mois du code `AmandaBoost-26` sont une EXCEPTION MANUELLE du 5 août 2026
# (rattrapage d'un paiement perdu) et ne doivent pas servir de référence.
DUREE_VALIDITE_CODE_MOIS = 2


def date_expiration_code(depuis=None) -> str:
    """
    Date d'expiration d'un code créé maintenant, au format `AAAA-MM-JJ` — celui
    qu'utilisent tous les codes existants (`expiresAt`).

    Mois CALENDAIRES et non 60 jours fixes : un achat du 31 décembre expire le
    28 février, pas le 1er mars. `relativedelta` gère les fins de mois et les
    années bissextiles.
    """
    from dateutil.relativedelta import relativedelta
    base = depuis or datetime.now(timezone.utc)
    return (base + relativedelta(months=+DUREE_VALIDITE_CODE_MOIS)).strftime("%Y-%m-%d")


# =====================================================================
# V391 — QUEL ABONNEMENT UN CODE DÉSIGNE-T-IL ?  (cause de fond des doublons)
# =====================================================================
# Un même `code` porte PLUSIEURS documents dans `subscriptions` (renouvellements
# successifs, imports, synchronisations manuelles). Jusqu'ici, six endroits
# différents tranchaient avec `find_one({"code": …, "status": "active"})` — qui
# renvoie le PREMIER document en ordre naturel Mongo, donc en pratique le PLUS
# ANCIEN. Et `/subscriptions/status` déduplicait explicitement en « gardant le
# premier = le plus ancien ».
#
# Conséquence mesurée en production le 7 août 2026 sur BASSBOOSTX-11 : le forfait
# servi était celui expiré le 13/07 avec 1 séance, au lieu du forfait valide
# jusqu'en 2027 avec 45 séances. L'espace abonné affichait un abonnement mort et
# la réservation était refusée, alors que les séances étaient payées.
#
# RÈGLE UNIQUE, appliquée partout : **le plus RÉCENT, NON EXPIRÉ, ayant encore des
# séances**. Les replis successifs garantissent qu'on ne renvoie JAMAIS `None` là
# où l'ancien code renvoyait un document — aucun parcours ne peut donc régresser :
#   1. actif + non expiré + séances restantes   -> le plus récent   (cas nominal)
#   2. actif + non expiré                        -> le plus récent   (forfait épuisé)
#   3. actif                                     -> le plus récent   (tout expiré)
#   4. n'importe quel statut                     -> le plus récent   (dernier repli)


def _v391_est_expire(valeur, maintenant=None) -> bool:
    """`expires_at` est-il dépassé ? Absent/illisible -> JAMAIS expiré.

    Volontairement indulgent : une date au format inattendu ne doit pas couper
    l'accès d'un abonné qui a payé. On préfère servir un forfait douteux que
    d'en refuser un valide (même parti pris que `_v200_parse_expiry`).
    """
    if not valeur:
        return False
    maintenant = maintenant or datetime.now(timezone.utc)
    try:
        if isinstance(valeur, datetime):
            dt = valeur
        else:
            texte = str(valeur).strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(texte)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt < maintenant
    except (ValueError, TypeError):
        return False


def _v391_seances_restantes(sub) -> int:
    """Séances restantes, tolérant aux champs absents ou stockés en texte/flottant."""
    for cle in ("remaining_sessions",):
        brut = (sub or {}).get(cle)
        if brut is not None:
            try:
                return int(float(brut))
            except (TypeError, ValueError):
                pass
    try:
        total = int(float((sub or {}).get("total_sessions") or 0))
        utilisees = int(float((sub or {}).get("used_sessions") or 0))
        return max(0, total - utilisees)
    except (TypeError, ValueError):
        return 0


def _v391_date_creation(sub) -> str:
    """Clé de tri « le plus récent ». Chaîne ISO -> tri lexicographique correct.
    Un document sans date passe en dernier (chaîne vide), jamais en premier.
    """
    return str((sub or {}).get("created_at") or "")


def choisir_abonnement(candidats):
    """Applique la règle V391 à une liste de documents `subscriptions` déjà lus.

    Version SYNCHRONE, pour les appelants qui ont déjà la liste en main.
    Renvoie `None` seulement si `candidats` est vide.
    """
    docs = [d for d in (candidats or []) if d]
    if not docs:
        return None
    maintenant = datetime.now(timezone.utc)
    actifs = [d for d in docs if (d.get("status") or "").lower() == "active"]
    vivants = [d for d in actifs if not _v391_est_expire(d.get("expires_at"), maintenant)]
    avec_seances = [d for d in vivants if _v391_seances_restantes(d) > 0]

    # V394 — DÉPARTAGE PAR LA CONSOMMATION, PLUS PAR LA DATE.
    # V391 départageait sur `created_at` décroissant. Or entre deux doublons créés
    # au même instant (CHRISTOUX10 : 7 MICROSECONDES d'écart, double-clic à la
    # création), « le plus récent » désigne le document VIERGE — le fantôme, celui
    # qui n'a jamais suivi la moindre réservation. Résultat mesuré : l'espace
    # affichait 10 séances restantes au lieu de 6, soit 4 séances non payées
    # offertes.
    # Le document qui fait foi est celui que le système a réellement DÉBITÉ. On
    # départage donc sur `used_sessions` DÉCROISSANT, la date ne servant plus que
    # de second critère à consommation égale.
    # ⚠️ Ce choix suppose qu'un renouvellement FERME l'ancien forfait (V395) :
    # sans cela, un ancien forfait presque épuisé mais encore valide primerait sur
    # un forfait neuf. Aucun code en production n'est dans ce cas aujourd'hui
    # (vérifié), et V395 garantit qu'il n'y en aura pas.
    def _cle(d):
        try:
            consomme = int(float(d.get("used_sessions") or 0))
        except (TypeError, ValueError):
            consomme = 0
        return (consomme, _v391_date_creation(d))

    for lot in (avec_seances, vivants, actifs, docs):
        if lot:
            return sorted(lot, key=_cle, reverse=True)[0]
    return None


async def lire_abonnement_par_code(db, code, email=None, filtre_supplementaire=None):
    """Le BON abonnement pour ce `code` (règle V391), ou `None` si le code n'en a aucun.

    Remplace `find_one({"code": …, "status": "active"})`. Recherche insensible à la
    casse, comme les appels qu'elle remplace.

    `email` — QUAND L'APPELANT SAIT QUI DEMANDE, on ne doit pas lui servir le
    document de quelqu'un d'autre. Certains codes portent des documents à des
    e-mails DIFFÉRENTS (relevé en production : `BASS` et `NADIABOOST-26` en ont 3
    chacun). « Le plus récent » y resterait un choix arbitraire entre plusieurs
    personnes. Si l'e-mail fourni correspond à au moins un document, on choisit
    PARMI CEUX-LÀ ; sinon on retombe sur l'ensemble (l'e-mail n'est alors qu'un
    indice, jamais un filtre bloquant — un abonné dont la fiche porte une adresse
    mal saisie garde son accès).
    """
    import re as _re
    code_norm = (code or "").strip().upper()
    if not code_norm:
        return None
    requete = {"code": {"$regex": f"^{_re.escape(code_norm)}$", "$options": "i"}}
    if filtre_supplementaire:
        requete.update(filtre_supplementaire)
    # Plafond volontaire : un code légitime a une poignée de documents. 50 borne
    # le coût sans jamais tronquer un cas réel (le maximum observé est 3).
    candidats = await db.subscriptions.find(requete, {"_id": 0}).to_list(50)
    if email:
        _e = str(email).strip().lower()
        _miens = [d for d in candidats if (d.get("email") or "").strip().lower() == _e]
        if _miens:
            candidats = _miens
    return choisir_abonnement(candidats)


# =====================================================================
# V393 — UN FORFAIT EXPIRÉ OU ÉPUISÉ NE PERMET JAMAIS DE RÉSERVER
# =====================================================================
# Constat du 7 août 2026 : AUCUN des trois chemins d'écriture ne testait
# `expires_at`. Ils ne regardaient que `remaining <= 0`. Résultat : 22 codes
# expirés — 365 séances, dont 200 chez 16 vrais clients — restaient réservables.
# Ce n'est pas théorique : une cliente a réservé le 05/08 une séance du 05/08
# alors que son forfait expirait le 03/08. Chaque séance ainsi prise est une
# séance non payée.
#
# Le garde vit ICI, en un seul endroit, pour que les trois chemins ne puissent
# plus diverger : espace abonné, vitrine, et scan du QR à l'entrée du cours.

def forfait_utilisable(sub, quantite=1):
    """(ok, message) — ce forfait autorise-t-il `quantite` réservation(s) ?

    Refus EXPLICITE et lisible par le client : il doit comprendre pourquoi, et le
    coach doit pouvoir le lui confirmer sans lire les journaux.
    Un forfait sans `expires_at` n'expire pas (codes à durée libre) — inchangé.
    """
    if not sub:
        return False, "Abonnement introuvable"

    expiration = sub.get("expires_at")
    if _v391_est_expire(expiration):
        try:
            jour = str(expiration)[:10]
            j, m, a = jour.split("-")[2], jour.split("-")[1], jour.split("-")[0]
            lisible = f"{j}.{m}.{a}"
        except (IndexError, ValueError, AttributeError):
            lisible = str(expiration)[:10]
        return False, (
            f"Ton abonnement a expiré le {lisible}. "
            "Contacte le coach pour le renouveler."
        )

    restant = _v391_seances_restantes(sub)
    if restant <= 0:
        return False, (
            "Toutes les séances de ton abonnement ont été utilisées. "
            "Contacte le coach pour le renouveler."
        )
    if restant < quantite:
        return False, f"Séances insuffisantes : {restant} restante(s), {quantite} demandée(s)"

    return True, ""


# =====================================================================
# V397 — UN RENOUVELLEMENT FERME L'ANCIEN FORFAIT
# =====================================================================
# Jusqu'ici, un paiement CRÉAIT un forfait sans jamais fermer le précédent. D'où
# des clients porteurs de plusieurs `subscriptions` actives sur le même e-mail —
# la source même des doublons qui ont fait afficher un forfait mort à une cliente
# alors que son forfait valide existait juste à côté.

async def cloturer_anciens_forfaits(db, email, id_nouveau, log_prefix="V397"):
    """Ferme (`superseded`) les forfaits ACTIFS antérieurs de ce client.

    PORTÉE VOLONTAIREMENT ÉTROITE — on ne ferme QUE ce qui est déjà sans valeur :
    un forfait EXPIRÉ ou ÉPUISÉ. Un forfait encore valide avec des séances au
    compteur n'est JAMAIS touché : le client l'a payé, et certains détiennent
    légitimement deux packs en parallèle. Fermer large ici détruirait de la valeur
    payée — c'est l'erreur exactement inverse de celle qu'on corrige.

    Renvoie la liste des `id` fermés (pour le journal et le rollback).
    """
    if db is None or not email:
        return []
    email_norm = str(email).strip().lower()
    if not email_norm:
        return []
    fermes = []
    try:
        candidats = await db.subscriptions.find(
            {"email": {"$regex": f"^{__import__('re').escape(email_norm)}$", "$options": "i"},
             "status": "active"},
            {"_id": 0},
        ).to_list(50)
    except Exception as e:
        logger.warning(f"[{log_prefix}] Lecture des anciens forfaits impossible: {e}")
        return []

    for anc in candidats:
        if anc.get("id") == id_nouveau:
            continue  # jamais le forfait qu'on vient de créer
        perime = _v391_est_expire(anc.get("expires_at"))
        epuise = _v391_seances_restantes(anc) <= 0
        if not (perime or epuise):
            continue  # encore valide ET avec des séances -> on n'y touche pas
        try:
            r = await db.subscriptions.update_one(
                {"id": anc.get("id"), "status": "active"},
                {"$set": {"status": "superseded",
                          "superseded_at": datetime.now(timezone.utc).isoformat(),
                          "superseded_by": id_nouveau}},
            )
            if r.modified_count == 1:
                fermes.append(anc.get("id"))
                logger.info(
                    f"[{log_prefix}] Ancien forfait ferme: {anc.get('id')} "
                    f"({anc.get('code')}, {'expire' if perime else 'epuise'}) -> superseded"
                )
        except Exception as e:
            logger.warning(f"[{log_prefix}] Fermeture de {anc.get('id')} echouee: {e}")
    return fermes


def expiration_forfait(depuis=None) -> str:
    """`expires_at` d'un forfait créé maintenant : +2 mois, format ISO complet.

    Contrepartie de `date_expiration_code()` (qui produit `AAAA-MM-JJ` pour
    `discount_codes.expiresAt`). Les deux dérivent de la MÊME constante
    `DUREE_VALIDITE_CODE_MOIS`, pour qu'un code et son forfait ne puissent pas
    expirer à deux dates différentes — l'incohérence trouvée chez une cliente dont
    le code expirait le 06.10 et le forfait JAMAIS (`expires_at: null`).
    """
    from dateutil.relativedelta import relativedelta
    base = depuis or datetime.now(timezone.utc)
    fin = (base + relativedelta(months=+DUREE_VALIDITE_CODE_MOIS)).replace(
        hour=23, minute=59, second=59, microsecond=0
    )
    return fin.isoformat()


# === V430 : « un code assigné n'appartient qu'à son propriétaire » ===
#
# Règle unique, écrite ICI et nulle part ailleurs, appelée par les trois routes
# qui ACCORDENT quelque chose contre un code (remise au checkout, validation,
# incrément du compteur à la réservation).
#
# La faille fermée : partout le contrôle s'écrivait
#     if assigne and email_fourni and assigne != email_fourni: refus
# Le `and email_fourni` faisait qu'un e-mail ABSENT ou VIDE désactivait le
# contrôle. Il suffisait donc de retirer `customerEmail` du corps de la requête
# pour utiliser le code de quelqu'un d'autre. C'est un REFUS PAR DÉFAUT ici.
#
# EXCEPTION PROUVÉE — LES CODES DE GROUPE. `assignedEmail` désigne la personne
# qui a PAYÉ, pas la seule qui a le droit de s'en servir. En production, 7
# réservations réelles d'un groupe de 6 ont été posées par 5 membres dont
# l'adresse diffère de `assignedEmail`. L'identité autorisée d'un code
# `multi_member` est donc l'ENSEMBLE {assignedEmail} ∪ {code_members.email}.
# Sans cette exception, ce groupe serait mis dehors.

def normaliser_email(valeur) -> str:
    """Trim + minuscules. Rien d'autre : pas de `contains`, pas de comparaison
    partielle, pas de tolérance floue. Tout ce qui n'est pas une chaîne vaut ''.

    Vérifié sur les 38 documents de `discount_codes` : les 24 valeurs
    `assignedEmail` existantes sont DÉJÀ trim+minuscules et bien formées — cette
    normalisation n'en modifie aucune."""
    if not isinstance(valeur, str):
        return ""
    return valeur.strip().lower()


async def email_autorise_pour_code(db, doc: dict, email_fourni) -> tuple:
    """(autorisé: bool, motif: str) — le porteur de `email_fourni` a-t-il le droit
    d'utiliser ce `discount_code` ?

    - pas d'`assignedEmail`      -> autorisé (« code_non_assigne »), inchangé ;
    - e-mail absent/vide         -> REFUS (« email_absent ») ;
    - égalité normalisée         -> autorisé (« proprietaire ») ;
    - code de groupe + membre    -> autorisé (« membre_du_groupe ») ;
    - sinon                      -> REFUS (« autre_compte »).
    """
    assigne = normaliser_email(doc.get("assignedEmail"))
    if not assigne:
        return True, "code_non_assigne"

    fourni = normaliser_email(email_fourni)
    if not fourni:
        return False, "email_absent"
    if fourni == assigne:
        return True, "proprietaire"

    if doc.get("multi_member"):
        import re as _re
        _code = (doc.get("code") or "").strip()
        if _code:
            try:
                membres = await db.code_members.find(
                    {"code": {"$regex": f"^{_re.escape(_code)}$", "$options": "i"}},
                    {"_id": 0, "email": 1, "blocked": 1},
                ).to_list(300)
            except Exception as e:
                # Base injoignable : on NE relâche PAS le contrôle.
                logger.warning(f"[V430] Lecture code_members impossible pour {_code}: {e}")
                return False, "membres_illisibles"
            for m in membres:
                if normaliser_email(m.get("email")) == fourni:
                    if m.get("blocked"):
                        return False, "membre_bloque"
                    return True, "membre_du_groupe"

    return False, "autre_compte"


# Message unique montré à l'utilisateur. Aucun détail interne : ne dit ni à qui
# le code appartient, ni lequel des motifs a joué.
V430_MESSAGE_REFUS = (
    "Ce code est lié à un compte précis. "
    "Vérifie l'adresse utilisée ou contacte Afroboost."
)


# === V431 : un nettoyage de contacts ne doit pas OUVRIR un code encore valide ===
#
# `assignedEmail` porte DEUX rôles à la fois : une donnée personnelle, et la clé
# de contrôle d'accès lue par V430. Les routes de nettoyage ne voyaient que le
# premier rôle et vidaient le champ — transformant un code personnel en code
# libre, utilisable par n'importe qui.
#
# Constaté en production : `POST /api/sanitize-data` est appelé AUTOMATIQUEMENT
# à chaque chargement du tableau de bord (CoachDashboard.js:2140), et il vide
# `assignedEmail` dès que l'adresse est absente de `db.users`. Or les acheteurs
# Stripe ne sont jamais écrits dans `db.users` (le webhook alimente
# `chat_participants`, 1267 documents, pas `users`, 41 adresses). Deux billets
# ZP1 payés ont ainsi perdu leur protection le jour même de leur achat.
#
# La règle : on ne vide `assignedEmail` que sur un code qui n'ouvre PLUS AUCUN
# droit. Tant qu'il en ouvre un, l'adresse n'est pas une donnée superflue — elle
# EST le droit d'accès. Une fois le code éteint, le nettoyage reprend son cours :
# la minimisation des données est différée, pas abandonnée.

def code_encore_utilisable(doc: dict, aujourdhui: str = "") -> bool:
    """Ce code peut-il encore ouvrir un droit ? actif ET non expiré ET non épuisé.

    Prudence délibérée : tout ce qui n'est pas une expiration ISO clairement
    dépassée est traité comme NON expiré. Une date au format inattendu ne doit
    jamais provoquer l'effacement d'une protection — se tromper dans ce sens
    ouvre un code payé, se tromper dans l'autre ne fait que retarder un ménage.
    """
    if not doc.get("active"):
        return False
    _exp = doc.get("expiresAt")
    if isinstance(_exp, str):
        _exp = _exp.strip()[:10]
        # uniquement AAAA-MM-JJ : une comparaison de chaînes sur « 11.10.2026 »
        # conclurait « expiré » à tort.
        if len(_exp) == 10 and _exp[4] == "-" and _exp[7] == "-" and _exp[:4].isdigit():
            _auj = aujourdhui or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if _exp < _auj:
                return False
    try:
        _max = int(doc.get("maxUses") or 0)
        _used = int(doc.get("used") or 0)
    except (TypeError, ValueError):
        return True                      # compteurs illisibles -> on ne touche à rien
    if _max and _used >= _max:
        return False
    return True


async def purger_assigned_email(db, filtre: dict, motif: str = "") -> dict:
    """Vide `assignedEmail` sur les documents de `filtre`, SAUF ceux encore
    utilisables. Renvoie {vides, proteges}. Met à jour par `id` — jamais par
    `code`, qui porte des doublons en production."""
    vides, proteges = 0, 0
    for _d in await db.discount_codes.find(filtre, {"_id": 0}).to_list(500):
        if code_encore_utilisable(_d):
            proteges += 1
            logger.info(
                f"[V431] {_d.get('code')} : assignedEmail CONSERVE — code encore "
                f"utilisable (actif, non expiré, non épuisé){' — ' + motif if motif else ''}"
            )
            continue
        await db.discount_codes.update_one(
            {"id": _d.get("id")}, {"$set": {"assignedEmail": None}}
        )
        vides += 1
    return {"vides": vides, "proteges": proteges}


# =====================================================================
# C9-A — INSTRUMENTATION POSTHOG, CÔTÉ SERVEUR
# =====================================================================
# POURQUOI CÔTÉ SERVEUR. Le navigateur ne prouve rien : la page de succès
# s'affiche même si le paiement échoue ensuite, et `us.i.posthog.com` est
# bloqué par une part notable des bloqueurs de publicité. Les CONVERSIONS sont
# donc émises depuis le backend, au moment où l'action métier est confirmée en
# base. Les événements d'INTENTION (pageview, clic) restent au frontend.
#
# TROIS RÈGLES ABSOLUES :
#   1. NON BLOQUANT. Aucune exception ne remonte : ni configuration absente, ni
#      timeout, ni panne PostHog ne doit faire échouer une réservation, une
#      présence ou un paiement. Tout est avalé et journalisé.
#   2. ÉTEINT PAR DÉFAUT. `POSTHOG_SERVER_ENABLED` vaut false tant qu'on ne
#      l'allume pas explicitement — même logique que les drapeaux V344.
#   3. AUCUNE DONNÉE PERSONNELLE. Jamais d'e-mail, de téléphone, de nom, de
#      contenu de conversation, de code promo ni d'identifiant Stripe. La
#      personne est désignée par un pseudonyme dérivé, non réversible.

def posthog_actif() -> bool:
    """Lu EN DIRECT à chaque appel : l'interrupteur se change dans Coolify sans
    redéploiement, et sert de coupe-circuit immédiat."""
    return (os.environ.get("POSTHOG_SERVER_ENABLED", "") or "").strip().lower() in ("1", "true", "yes", "on")


def posthog_id(email: str) -> str:
    """Pseudonyme STABLE dérivé de l'e-mail : sha256(sel + e-mail normalisé),
    tronqué à 32 caractères.

    Stable — la même personne produit toujours le même identifiant, donc le
    funnel tient d'un événement à l'autre. Non réversible — PostHog ne reçoit
    jamais l'adresse. Le frontend calculera le MÊME identifiant au moment
    d'appeler `identify()`, ce qui raccrochera la visite anonyme au parcours
    d'achat (lot C9-B).
    """
    import hashlib
    e = (email or "").strip().lower()
    if not e:
        return ""
    sel = os.environ.get("POSTHOG_ID_SALT", "afroboost-c9")
    return hashlib.sha256((sel + "|" + e).encode("utf-8")).hexdigest()[:32]


async def posthog_capture(event: str, email: str = "", props: dict = None,
                          distinct_id: str = "") -> bool:
    """Émet un événement PostHog. Renvoie True si envoyé, False sinon.
    NE LÈVE JAMAIS. L'appelant peut ignorer le retour.

    `email` sert UNIQUEMENT à calculer le pseudonyme : il n'est pas transmis.
    """
    try:
        if not posthog_actif():
            return False
        cle = (os.environ.get("POSTHOG_API_KEY", "") or "").strip()
        if not cle:
            logger.info("[C9] POSTHOG_API_KEY absente — aucun envoi")
            return False
        did = (distinct_id or "").strip() or posthog_id(email)
        if not did:
            logger.info(f"[C9] {event} ignoré — aucun identifiant exploitable")
            return False

        # Filet de sécurité : même si un appelant se trompe, ces clés ne
        # partiront jamais. La minimisation ne dépend pas de la vigilance.
        _INTERDIT = {"email", "phone", "whatsapp", "name", "userName", "userEmail",
                     "customer_email", "promoCode", "promo_code", "code",
                     "session_id", "payment_intent", "stripe_customer_id", "message"}
        charge = {k: v for k, v in (props or {}).items() if k not in _INTERDIT}
        retires = sorted(set(props or {}) & _INTERDIT)
        if retires:
            logger.warning(f"[C9] {event} : propriétés interdites retirées {retires}")

        hote = (os.environ.get("POSTHOG_HOST", "") or "https://us.i.posthog.com").rstrip("/")
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.post(
                hote + "/i/v0/e/",
                json={"api_key": cle, "event": event, "distinct_id": did,
                      "properties": {**charge, "$lib": "afroboost-server"}},
            )
        if r.status_code >= 300:
            logger.warning(f"[C9] {event} refusé par PostHog : HTTP {r.status_code}")
            return False
        logger.info(f"[C9] {event} envoyé (id={did[:8]}…)")
        return True
    except Exception as e:
        # Volontairement muet pour le métier : analytics ne casse jamais rien.
        logger.warning(f"[C9] {event} échoué, ignoré — {type(e).__name__}: {e}")
        return False


# =====================================================================
# C17-B — SOCLE DE NOTIFICATION : RESOUDRE LE BON DESTINATAIRE
# =====================================================================
# Le systeme est destine a etre MULTI-COACH. Or plusieurs notifications
# visaient encore une CONSTANTE GLOBALE (`COACH_EMAIL`, `SUPER_ADMIN_EMAIL`) :
# tant qu'il n'y a qu'un coach cela fonctionne, mais le jour ou un partenaire
# arrive, ses prospects partiraient chez Bassi. On resout donc le proprietaire
# REEL de l'evenement, jamais une constante.
#
# C17-C ne faisait que deux choses : resoudre le coach, et ecrire une trace dans
# `db.notifications` — aucun envoi. C17-D ajoute LE SEUL canal push, et rien
# d'autre : pas d'e-mail, pas de SMS. L'emetteur est INJECTE par l'appelant
# (parametre `envoyer_push`) plutot qu'importe ici : `shared.py` n'importe rien
# de `server.py`, et un import direct creerait un cycle server -> shared -> server.

async def resoudre_coach_du_lead(db, lead: dict) -> str:
    """Coach REELLEMENT proprietaire d'un lead, ou '' si indeterminable.

    Chaine mesuree sur les 133 leads de production :
        lead.coach_id                        -> 59 resolus
        puis chat_sessions[link_token].coach_id -> +32
        puis participant.coach_id               -> +0 (mais garde le jour ou les
                                                   sessions porteront le champ)
        sinon                                   -> 42 restent orphelins

    ⚠️ ON NE DEVINE PAS. Un lead orphelin renvoie '' et ne genere AUCUNE
    notification : mieux vaut ne prevenir personne que prevenir le mauvais coach.
    C'est la regle absolue du multi-coach — evenement du coach A, jamais au B.
    """
    try:
        c = (lead.get("coach_id") or "").strip()
        if c:
            return c
        jeton = (lead.get("link_token") or "").strip()
        if jeton:
            s = await db.chat_sessions.find_one({"link_token": jeton}, {"_id": 0, "coach_id": 1})
            c = ((s or {}).get("coach_id") or "").strip()
            if c:
                return c
        pid = (lead.get("participant_id") or "")
        if pid:
            p = await db.chat_participants.find_one({"id": pid}, {"_id": 0, "coach_id": 1})
            c = ((p or {}).get("coach_id") or "").strip()
            if c:
                return c
    except Exception as e:
        logger.warning(f"[C17-B] resolution coach impossible: {type(e).__name__}")
    return ""


async def notifier_nouveau_prospect(db, lead: dict, envoyer_push=None) -> bool:
    """C17-C — trace « nouveau prospect » pour le coach proprietaire.
    C17-D — et, si `envoyer_push` est fourni, previent ce coach sur son telephone.

    NON BLOQUANTE : ne leve jamais. Une panne de notification ne doit pas
    empecher l'enregistrement d'un prospect — c'est l'inverse qui compte.

    IDEMPOTENTE : l'identifiant derive du lead (`lead_<id>`), et l'ecriture est
    un upsert. Un rejeu ne cree pas de doublon.

    AUCUNE DONNEE SENSIBLE EN JOURNAL : on trace l'identifiant du lead et le
    coach, jamais l'e-mail, le telephone ni les reponses du prospect.
    """
    try:
        lead_id = (lead.get("id") or "").strip()
        if not lead_id:
            return False
        coach = await resoudre_coach_du_lead(db, lead)
        if not coach:
            # Orphelin : on prefere le silence a une notification mal adressee.
            logger.info(f"[C17-C] lead {lead_id[:8]} sans coach resolu — aucune notification")
            return False
        prenom = (lead.get("name") or "").strip().split(" ")[0][:40] or "Un visiteur"
        _res = await db.notifications.update_one(
            {"id": f"lead_{lead_id}"},
            {"$setOnInsert": {
                "id": f"lead_{lead_id}",
                "type": "new_lead",
                "target": "coach",
                "title": "🎯 Nouveau prospect",
                "message": f"{prenom} vient de terminer le tunnel.",
                "coach_id": coach,
                "lead_id": lead_id,
                "link_token": lead.get("link_token"),
                "read": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )
        logger.info(f"[C17-C] notification nouveau prospect creee (lead={lead_id[:8]}, coach={coach[:24]})")
        # C17-D : push vers le coach PROPRIETAIRE resolu ci-dessus — jamais une
        # constante globale, sinon les prospects d'un partenaire sonneraient chez
        # Bassi. Le pid `coach_<email>` est la convention deja utilisee par
        # `push_subscriptions` pour les comptes coach.
        #
        # Trois garanties :
        #   1. NON BLOQUANT — try/except dedie : un push en panne ne doit jamais
        #      empecher l'enregistrement du prospect, qui est le seul enjeu reel.
        #   2. IDEMPOTENT — on n'envoie que si l'upsert a REELLEMENT insere
        #      (`upserted_id`). Un rejeu ne fait pas re-sonner le telephone.
        #   3. PUSH SEUL — aucun e-mail de secours : `send_push_notification`
        #      n'en envoie pas (contrairement a la route /push/send).
        if envoyer_push is not None and getattr(_res, "upserted_id", None) is not None:
            try:
                _ok = await envoyer_push(
                    f"coach_{coach}",
                    "🎯 Nouveau prospect",
                    f"{prenom} vient de terminer le tunnel.",
                )
                logger.info(f"[C17-D] push coach={coach[:24]} envoye={bool(_ok)}")
            except Exception as e:
                logger.warning(f"[C17-D] push ignore, le prospect reste enregistre — {type(e).__name__}: {e}")
        return True
    except Exception as e:
        logger.warning(f"[C17-C] notification ignoree, le prospect reste enregistre — {type(e).__name__}: {e}")
        return False
