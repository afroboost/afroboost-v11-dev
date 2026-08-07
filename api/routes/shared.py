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

    for lot in (avec_seances, vivants, actifs, docs):
        if lot:
            return sorted(lot, key=_v391_date_creation, reverse=True)[0]
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
