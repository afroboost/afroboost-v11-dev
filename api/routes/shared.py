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


# =====================================================================
# === V2-0 (CONTACTS) : REFUSER N'EST PAS FILTRER =====================
# =====================================================================
#
# CE QUE CE BLOC CORRIGE. `get_coach_filter("")` ci-dessus renvoie
# `{"coach_id": ""}`. Ce n'est PAS un refus : c'est un filtre qui SÉLECTIONNE
# les documents dont `coach_id` vaut la chaîne vide — il y en a 5 dans
# `chat_participants`, mesurés le 14/08/2026. Et sa variante `None` matcherait
# en plus les champs ABSENTS, soit 891 documents (1 contact, 102 `users`,
# 620 `chat_sessions`, 74 `leads`, 94 `campaign_errors`). Une garde qui rend un
# dictionnaire ne sait pas dire « non ». Celle-ci lève.
#
# Le code s'en protège aujourd'hui par des `if caller_email else []` dispersés —
# une protection accidentelle, qu'une réécriture supprime sans bruit.
#
# ⚠️ MONO-COACH ASSUMÉ, ET DIT. Mesure du 14/08/2026 : `coaches` contient UN
# document, `coach_auth` n'existe pas, et `chat_participants.coach_id` n'a
# qu'UNE valeur distincte sur 1331 documents. Ce périmètre ne SÉPARE donc
# personne aujourd'hui — il pose la structure pour que l'arrivée d'un partenaire
# ne l'expose pas. Ne pas le présenter comme un cloisonnement actif.
#
# FAIL-CLOSED SUR L'HISTORIQUE, VOLONTAIREMENT. Un document sans `coach_id` ne
# correspond à aucun `{"coach_id": <email>}` : il reste invisible pour un coach
# ordinaire et visible du seul super-admin (`{}`). On n'invente à personne un
# propriétaire qu'il n'a pas — l'attribution de l'historique est une décision
# séparée et réversible, pas un effet de bord d'une garde de sécurité.

class V20AccesRefuse(Exception):
    """Levée quand aucune identité exploitable n'accompagne la requête."""


def v20_perimetre_contacts(email: str) -> dict:
    """Filtre Mongo d'une identité DÉJÀ authentifiée — ou refus explicite.

    - identité vide / absente -> LÈVE `V20AccesRefuse` (jamais un dictionnaire) ;
    - super-admin             -> `{}` (vue globale intacte, cf. incident V310c) ;
    - coach                   -> `{"coach_id": <email normalisé>}`.

    L'appelant convertit `V20AccesRefuse` en 403. La séparation est voulue : ce
    module ne dépend pas de FastAPI, ce qui le rend testable hors ligne.
    """
    _e = (email or "").strip().lower() if isinstance(email, str) else ""
    if not _e:
        raise V20AccesRefuse("identité requise")
    if is_super_admin(_e):
        return {}
    return {"coach_id": _e}


async def v20_exiger_coach_signe(request, database, quoi: str = ""):
    """Identité coach/admin portée par un JWT SIGNÉ, sinon 403. Aucun repli.

    Réservée aux routes dont il est PROUVÉ qu'aucun frontend ne les appelle —
    exiger un jeton signé sur une route du dashboard reproduirait l'incident
    V310c (403 -> écran vide), car le dashboard n'émet un JWT que sur le chemin
    « e-mail + mot de passe » et pas sur ses trois entrées automatiques.

    Le rôle n'est jamais décidé par le navigateur : il est relu dans `coaches`.
    """
    from fastapi import HTTPException
    email = coach_jwt_email(request)
    if not email:
        _revendique = ""
        try:
            _revendique = (request.headers.get("X-User-Email", "") or "").strip().lower()
        except Exception:
            pass
        logger.warning("[V2-0] REFUS %s — « %s » sans jeton signé",
                       quoi or "accès", _revendique or "anonyme")
        raise HTTPException(status_code=403,
                            detail="Authentification coach requise — reconnectez-vous")
    if is_super_admin(email):
        return email
    try:
        if database is not None and await database.coaches.find_one({"email": email}, {"_id": 1}):
            return email
    except Exception as _e:
        logger.warning("[V2-0] vérification du rôle impossible pour %s : %s", email, _e)
    logger.warning("[V2-0] REFUS %s — « %s » n'est pas un coach enregistré",
                   quoi or "accès", email)
    raise HTTPException(status_code=403,
                        detail="Authentification coach requise — reconnectez-vous")


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


# =====================================================================
# RESERVATION-CREATED — evenement metier UNIQUE
# =====================================================================
# Jusqu'ici la confirmation dependait du CHEMIN utilise : `create_reservation`
# envoyait un e-mail, l'espace abonne dependait de V436 (casse), et le scan QR
# n'envoyait rien. Deux moteurs concurrents, des comportements differents pour
# un meme evenement metier.
#
# Ce helper est le point unique. La source (`chat_widget_abonne`,
# `subscriber_space`, …) reste une METADONNEE : elle ne decide jamais si les
# notifications partent.
#
# NON BLOQUANT — ne leve JAMAIS. Une reservation reussie ne doit pas etre
# annulee, ni meme perturbee, parce qu'un e-mail ou un push echoue.
#
# IDEMPOTENT PAR CANAL — chaque canal a son propre jeton sous `confirmation`.
# Le jeton est RESERVE par une ecriture conditionnelle atomique AVANT l'envoi :
# deux executions simultanees (rejeu du frontend, retry, double appel) ne
# peuvent pas produire deux envois. Un `find` puis un `send` laisserait une
# fenetre entre les deux ; pas cette forme.
#
# MULTI-COACH STRICT — le coach est resolu depuis la reservation, puis depuis le
# cours. Aucun repli vers une constante globale ni vers le super-admin : mieux
# vaut ne prevenir personne que prevenir le mauvais coach.

async def _rc_reserver_jeton(db, reservation_id: str, canal: str, quand: str) -> bool:
    """Reserve le droit d'envoyer sur CE canal. True si on l'obtient."""
    try:
        res = await db.reservations.update_one(
            {"id": reservation_id, f"confirmation.{canal}": {"$exists": False}},
            {"$set": {f"confirmation.{canal}": {"statut": "en_cours", "at": quand}}},
        )
        return bool(getattr(res, "matched_count", 0))
    except Exception as e:
        logger.warning("[RESA] jeton %s impossible: %s", canal, type(e).__name__)
        return False


async def _rc_cloturer_jeton(db, reservation_id: str, canal: str, ok: bool) -> None:
    try:
        await db.reservations.update_one(
            {"id": reservation_id},
            {"$set": {f"confirmation.{canal}.statut": "envoye" if ok else "echec"}},
        )
    except Exception:
        pass


async def resoudre_coach_de_reservation(db, reservation: dict) -> str:
    """Coach REELLEMENT proprietaire, ou '' — jamais de constante globale."""
    try:
        c = (reservation.get("coach_id") or "").strip()
        if c:
            return c
        cid = (reservation.get("courseId") or "").strip()
        if cid:
            cours = await db.courses.find_one({"id": cid}, {"_id": 0, "coach_id": 1})
            return ((cours or {}).get("coach_id") or "").strip()
    except Exception as e:
        logger.warning("[RESA] resolution coach impossible: %s", type(e).__name__)
    return ""


async def notifier_reservation_creee(
    db, reservation: dict, envoyer_email_client=None, envoyer_push_coach=None,
    envoyer_email_coach=None
) -> dict:
    """`reservation_created` : confirme le client ET previent le coach proprietaire.

    N2 — QUATRIEME CANAL, `coach_email`. Le coach recevait un e-mail pour une
    souscription et pour une annulation, mais AUCUN pour une reservation : le
    canal n'existait pas. Il suit exactement le motif des trois autres — jeton
    d'idempotence, envoyeur injecte par l'appelant, non bloquant. L'envoyeur est
    injecte et non code ici pour la meme raison que les autres : ce module ne
    connait ni Resend, ni les couleurs du coach, ni les gabarits.

    Retro-compatible : un appelant qui ne passe pas `envoyer_email_coach` obtient
    EXACTEMENT le comportement d'avant, `coach_email` restant a None.
    """
    bilan = {"client_email": None, "coach_inapp": None, "coach_push": None,
             "coach_email": None}
    try:
        rid = (reservation.get("id") or "").strip()
        if not rid:
            logger.warning("[RESA] reservation sans id — aucune notification")
            return bilan
        maintenant = datetime.now(timezone.utc).isoformat()

        # --- 1. CLIENT : confirmation par e-mail ---
        client = normaliser_email(reservation.get("userEmail"))
        if client and envoyer_email_client is not None:
            if await _rc_reserver_jeton(db, rid, "client_email", maintenant):
                ok = False
                try:
                    ok = bool(await envoyer_email_client(reservation))
                except Exception as e:
                    logger.warning("[RESA] e-mail client echoue: %s", type(e).__name__)
                await _rc_cloturer_jeton(db, rid, "client_email", ok)
                bilan["client_email"] = "envoye" if ok else "echec"
            else:
                bilan["client_email"] = "deja_traite"

        # --- 2. COACH : resolution stricte ---
        coach = await resoudre_coach_de_reservation(db, reservation)
        if not coach:
            # Anomalie tracee, reservation intacte. On ne devine pas.
            logger.warning("[RESA] coach non resolu (resa %s) — aucune notification coach", rid[:8])
            return bilan

        prenom = (reservation.get("userName") or "").strip().split(" ")[0][:40] or "Un client"
        cours = (reservation.get("courseName") or reservation.get("offerName") or "une seance")
        quand_txt = (reservation.get("selectedDatesText")
                     or str(reservation.get("datetime") or "")[:10])
        titre = "Nouvelle reservation"
        message = f"{prenom} vient de reserver {cours}" + (f" — {quand_txt}" if quand_txt else "")

        # --- 3. COACH : notification in-app ---
        # AUCUNE donnee personnelle : ni e-mail client, ni telephone, ni code.
        # (L'affichage dans le centre C17-J fera l'objet d'un lot separe : il
        #  filtre aujourd'hui `type: "new_lead"` uniquement.)
        if await _rc_reserver_jeton(db, rid, "coach_inapp", maintenant):
            ok = False
            try:
                await db.notifications.update_one(
                    {"id": f"resa_{rid}"},
                    {"$setOnInsert": {
                        "id": f"resa_{rid}", "type": "new_reservation", "target": "coach",
                        "title": titre, "message": message, "coach_id": coach,
                        "reservation_id": rid, "read": False, "created_at": maintenant,
                    }},
                    upsert=True,
                )
                ok = True
            except Exception as e:
                logger.warning("[RESA] notification coach echouee: %s", type(e).__name__)
            await _rc_cloturer_jeton(db, rid, "coach_inapp", ok)
            bilan["coach_inapp"] = "envoye" if ok else "echec"
        else:
            bilan["coach_inapp"] = "deja_traite"

        # --- 4. COACH : push ---
        if envoyer_push_coach is not None:
            if await _rc_reserver_jeton(db, rid, "coach_push", maintenant):
                # P2 — « ECHEC » NE DOIT PLUS COUVRIR DEUX CHOSES DIFFERENTES.
                #
                # Un coach sans aucun appareil inscrit et un coach dont tous les
                # appareils refusent produisaient le MEME mot. On lit donc
                # d'abord s'il existe au moins un abonnement actif : sans
                # abonnement, il n'y a rien a tenter, et ce n'est pas une panne.
                #
                # LIMITE ASSUMEE : cette lecture couvre l'inscription du
                # dashboard (`coach_<email>`) et celles portant `email`. Elle ne
                # reconstitue PAS les 25 identifiants candidats que
                # `send_push_by_email` explore — les dupliquer ici les ferait
                # diverger au premier changement. Elle sert a distinguer un cas
                # franc, pas a predire l'envoi.
                _a_un_appareil = True
                try:
                    _c = (coach or "").strip().lower()
                    _a_un_appareil = bool(await db.push_subscriptions.find_one(
                        {"active": True,
                         "$or": [{"participant_id": "coach_" + _c}, {"email": _c}]},
                        {"_id": 1}))
                except Exception as _err:
                    logger.warning("[RESA] abonnements push illisibles: %s", type(_err).__name__)

                if not _a_un_appareil:
                    await _rc_cloturer_jeton(db, rid, "coach_push", False)
                    bilan["coach_push"] = "aucun_abonnement"
                else:
                    ok = False
                    try:
                        ok = bool(await envoyer_push_coach(coach, titre, message,
                                                           {"type": "new_reservation", "reservation_id": rid}))
                    except Exception as e:
                        logger.warning("[RESA] push coach echoue: %s", type(e).__name__)
                    await _rc_cloturer_jeton(db, rid, "coach_push", ok)
                    bilan["coach_push"] = "envoye" if ok else "echec"
            else:
                bilan["coach_push"] = "deja_traite"

        # --- 5. COACH : e-mail (N2) ---
        # Le jeton est pose comme pour les trois autres : une reservation reelle
        # donne UN e-mail, un rejeu technique donne « deja_traite » et n'envoie
        # rien. Une panne d'envoi laisse la reservation intacte — on est deja
        # dans une tache detachee, et le garde-fou global est plus bas.
        if envoyer_email_coach is not None:
            if await _rc_reserver_jeton(db, rid, "coach_email", maintenant):
                ok = False
                try:
                    ok = bool(await envoyer_email_coach(coach, reservation))
                except Exception as e:
                    logger.warning("[RESA] e-mail coach echoue: %s", type(e).__name__)
                await _rc_cloturer_jeton(db, rid, "coach_email", ok)
                bilan["coach_email"] = "envoye" if ok else "echec"
            else:
                bilan["coach_email"] = "deja_traite"

        logger.info("[RESA] reservation_created %s -> %s", rid[:8], bilan)
    except Exception as e:
        # Garde-fou ultime : la reservation reste valide quoi qu'il arrive.
        logger.warning("[RESA] notification ignoree — %s: %s", type(e).__name__, e)
    return bilan


# ============================================================================
# ESSAI-2 — LES ETAPES DU FUNNEL D'ESSAI, ADOSSEES A LA BASE
# ============================================================================
#
# PostHog analyse, il ne decide de rien. Chaque etape est une verite lisible
# dans les collections, et l'idempotence de la conversion est portee par Mongo.
#
# Ce qui identifie un essai est le signal d'ESSAI-1, et rien d'autre :
# `discount_codes.payment_method == "free"` avec `total_paid == 0`, ecrit par
# `_process_successful_payment` sur tous les essais de la vitrine y compris les
# anciens, ou `source == "social_proof"`. On ne se fie ni a `offer_name`, chaine
# libre qui a deja derive, ni a `subscriptions.source`, qui vaut
# « checkout_vitrine » pour un essai comme pour un pack a 250 CHF.

ESSAI2_FILTRE_GRATUIT = {
    "$or": [
        {"payment_method": "free", "total_paid": 0},
        {"source": "social_proof"},
    ]
}


async def essai2_codes_essai(db, email: str) -> list:
    """Les codes d'acces obtenus GRATUITEMENT par cette adresse."""
    _e = (email or "").strip().lower()
    if not _e:
        return []
    try:
        _q = {"assignedEmail": _e}
        _q.update(ESSAI2_FILTRE_GRATUIT)
        _rows = await db["discount_codes"].find(
            _q, {"_id": 0, "code": 1}).to_list(20)
        return [r.get("code") for r in _rows if r.get("code")]
    except Exception as _e2:
        logger.warning(f"[ESSAI-2] codes d'essai illisibles: {_e2}")
        return []


async def essai2_forfait_essai(db, email: str):
    """Le forfait d'essai de cette adresse, ou None.

    Le PREMIER dans l'ordre de creation : c'est celui qui a ouvert le funnel.
    """
    _codes = await essai2_codes_essai(db, email)
    if not _codes:
        return None
    try:
        _rows = await db["subscriptions"].find(
            {"code": {"$in": _codes}}, {"_id": 0}).to_list(20)
        if not _rows:
            return None
        _rows.sort(key=lambda x: str(x.get("created_at") or ""))
        return _rows[0]
    except Exception as _e2:
        logger.warning(f"[ESSAI-2] forfait d'essai illisible: {_e2}")
        return None


async def essai2_est_essai(db, reservation: dict) -> bool:
    """Cette reservation consomme-t-elle un essai gratuit ?

    On remonte par le lien le PLUS SUR d'abord — `subscriptionId`, pose par le
    moteur — puis par le code, qui voyage sur `promoCode`/`discountCode`.
    """
    if not isinstance(reservation, dict):
        return False
    try:
        _sid = (reservation.get("subscriptionId") or "").strip()
        _code = (reservation.get("promoCode") or reservation.get("discountCode") or "").strip().upper()
        if not _sid and not _code:
            return False
        if not _code and _sid:
            _sub = await db["subscriptions"].find_one({"id": _sid}, {"_id": 0, "code": 1})
            _code = ((_sub or {}).get("code") or "").strip().upper()
        if not _code:
            return False
        _q = {"code": _code}
        _q.update(ESSAI2_FILTRE_GRATUIT)
        return await db["discount_codes"].find_one(_q, {"_id": 1}) is not None
    except Exception as _e2:
        logger.warning(f"[ESSAI-2] nature de la reservation indeterminee: {_e2}")
        return False


async def essai2_presence_essai(db, forfait: dict):
    """La reservation d'essai REELLEMENT honoree, ou None.

    « Presente » veut dire `validated: true`, pose par le coach au scan. Une
    date passee ne prouve rien : on ne la regarde pas.
    """
    if not forfait:
        return None
    _sid = (forfait.get("id") or "").strip()
    _code = (forfait.get("code") or "").strip().upper()
    _ou = []
    if _sid:
        _ou.append({"subscriptionId": _sid})
    if _code:
        _ou.append({"promoCode": _code})
        _ou.append({"discountCode": _code})
    if not _ou:
        return None
    try:
        _rows = await db["reservations"].find(
            {"validated": True, "$or": _ou}, {"_id": 0}).to_list(20)
        if not _rows:
            return None
        _rows.sort(key=lambda x: str(x.get("validatedAt") or ""))
        return _rows[0]
    except Exception as _e2:
        logger.warning(f"[ESSAI-2] presence d'essai illisible: {_e2}")
        return None


async def essai2_marquer_conversion(db, email: str, purchased_offer_id: str = "",
                                    purchased_sub_id: str = "") -> bool:
    """Le premier achat payant qui SUIT une presence d'essai. Rend True si
    cet appel est celui qui a converti.

    TROIS CONDITIONS, dans cet ordre :
      1. un forfait d'essai existe pour cette adresse ;
      2. une reservation rattachee a ce forfait est `validated` — la presence
         est confirmee par le coach, jamais deduite d'une date passee ;
      3. l'ecriture atomique de `converted_at` reussit pour la PREMIERE fois.

    L'ACHAT ANTERIEUR A LA PRESENCE se regle tout seul : on evalue au moment de
    l'achat, donc si la presence n'a pas encore eu lieu, la condition 2 echoue
    et rien n'est emis. Aucune date a comparer, aucune fenetre a choisir.

    LE DEUXIEME ACHAT ne convertit pas : le filtre exige l'ABSENCE de
    `converted_at`, et MongoDB ne l'accorde qu'a un seul ecrivain. C'est le
    motif deja employe cinq fois dans ce depot.

    LA FENETRE MONGO -> POSTHOG, ecrite noir sur blanc. Le marqueur est pose
    AVANT l'envoi analytique, et c'est voulu : deplacer l'ecriture apres
    l'envoi ferait qu'un echec reseau autoriserait une seconde conversion — on
    troquerait une metrique perdue contre une verite metier fausse.
    La consequence assumee est qu'un echec de PostHog perd l'evenement, sans
    aucun rattrapage automatique.
    Pour que ce ne soit pas definitif, la charge analytique est PERSISTEE a
    cote du marqueur et `converted_event_sent` reste faux tant que l'envoi n'a
    pas abouti. Un rejeu ulterieur n'a donc qu'a relire
    `{converted_at: {$exists: true}, converted_event_sent: false}` : il
    reconstitue l'evenement sans jamais rejuger la conversion.
    """
    _e = (email or "").strip().lower()
    if not _e:
        return False
    try:
        _forfait = await essai2_forfait_essai(db, _e)
        if not _forfait:
            return False
        if _forfait.get("converted_at"):
            return False
        _presence = await essai2_presence_essai(db, _forfait)
        if not _presence:
            return False

        _quand = datetime.now(timezone.utc)
        _delai = None
        try:
            _v = str(_presence.get("validatedAt") or "").replace("Z", "+00:00")
            _dt = datetime.fromisoformat(_v)
            if _dt.tzinfo is None:
                _dt = _dt.replace(tzinfo=timezone.utc)
            _delai = max(0, int((_quand - _dt).total_seconds() // 86400))
        except Exception:
            _delai = None

        _props = {
            "trial_offer_id": str(_forfait.get("offer_id") or "")[:64],
            "purchased_offer_id": str(purchased_offer_id or "")[:64],
            "course_id": str(_presence.get("courseId") or "")[:64],
        }
        if _delai is not None:
            _props["days_since_attendance"] = _delai

        _res = await db["subscriptions"].update_one(
            {"id": _forfait.get("id"), "converted_at": {"$exists": False}},
            {"$set": {
                "converted_at": _quand.isoformat(),
                "converted_by_subscription_id": str(purchased_sub_id or ""),
                "converted_props": _props,
                "converted_event_sent": False,
            }},
        )
        if not getattr(_res, "matched_count", 0):
            return False            # un autre appel a converti avant nous
    except Exception as _err:
        logger.warning(f"[ESSAI-2] conversion non evaluee: {_err}")
        return False

    # A partir d'ici la conversion EST actee en base. L'analytique ne peut plus
    # la remettre en cause, seulement la manquer.
    try:
        await posthog_capture("free_trial_converted", email=_e, props=_props)
        await db["subscriptions"].update_one(
            {"id": _forfait.get("id")}, {"$set": {"converted_event_sent": True}})
    except Exception as _err:
        logger.warning(f"[ESSAI-2] free_trial_converted non emis (rejouable): {_err}")
    return True


async def essai2_tracer_octroi(db, email: str, offer_id: str = "",
                               sessions: int = 0) -> None:
    """`free_trial_granted` — l'entree du funnel, qui n'etait pas mesuree.

    Non bloquant : un octroi reussi ne doit jamais echouer sur sa mesure.
    """
    try:
        await posthog_capture("free_trial_granted", email=email, props={
            "offer_id": str(offer_id or "")[:64],
            "sessions": int(sessions or 0),
        })
    except Exception as _err:
        logger.warning(f"[ESSAI-2] free_trial_granted ignore: {_err}")


# ============================================================================
# LOT B — LA TRACE FINANCIERE D'UN DROIT ACCORDE A LA MAIN
# ============================================================================
#
# CE QUE CE LOT REPARE. Mesure du 19/08/2026 sur la production : sur 59
# souscriptions, 41 ne portent AUCUN montant, et 28 d'entre elles ont ete
# creees a la main par le coach. Le formulaire de creation d'un code ne
# demandait nulle part ce qui avait ete encaisse, ni comment. Resultat, sur les
# 133 reservations : 41 % « droit connu, montant inconnu ». On ne pouvait pas
# dire si une souscription avait ete payee, offerte, ou reglee ailleurs.
#
# CE LOT NE REPARE PAS LE PASSE, ET C'EST VOULU. Aucun backfill, aucune
# migration. Les documents anterieurs restent sans montant, et se lisent
# « Montant non enregistre » — jamais « CHF 0 », qui est un montant REEL.
# `B_ORIGINE_INCONNUE` sert a cette lecture seule ; il n'est JAMAIS ecrit.
#
# POURQUOI SUR LE CODE, ET PAS SUR LA SOUSCRIPTION. Le code est cree UNE fois,
# par le coach, au moment ou l'argent change de main. La souscription, elle,
# nait a trois endroits differents de `promo_routes` — a la creation du code, a
# la premiere utilisation du code, et via la synchronisation manuelle. Poser la
# declaration sur le code et la RECOPIER sur chaque souscription qui en decoule
# (`b_champs_depuis_code`) donne une seule saisie et trois documents coherents.
#
# POURQUOI PAS `stripe_amount`. Ce champ existe deja, mais il melange deux
# choses incomparables : 8 montants adosses a une session Stripe reelle, et 11
# poses a la main ou retro-calcules — dont certains par le repli « prix du
# catalogue » de `/admin/fix-all-stripe`, neutralise dans ce meme lot. Un
# montant sans provenance ne peut pas etre distingue d'un montant invente.
# `stripe_amount` continue d'etre ecrit a l'identique (aucun ecran ne regresse),
# mais la verite est desormais dans les champs ci-dessous, qui portent leur
# provenance avec eux.

B_DEVISE_DEFAUT = "CHF"

# Les origines REELLEMENT supportees. Les quatre premieres sont saisissables
# par le coach ; les deux suivantes sont posees par les moteurs de paiement.
B_ORIGINES_MANUELLES = ("especes", "twint", "virement", "offert")
B_ORIGINES_AUTOMATIQUES = ("stripe", "mobile_money")
B_ORIGINES_PAIEMENT = B_ORIGINES_MANUELLES + B_ORIGINES_AUTOMATIQUES

# LECTURE SEULE. Valeur rendue pour un document anterieur a ce lot. Ecrire cette
# valeur reviendrait a fabriquer une declaration qui n'a jamais eu lieu.
B_ORIGINE_INCONNUE = "inconnu"

B_LIBELLES_ORIGINE = {
    "especes": "espèces",
    "twint": "TWINT",
    "virement": "virement",
    "offert": "offert",
    "stripe": "carte / TWINT (Stripe)",
    "mobile_money": "Mobile Money",
    B_ORIGINE_INCONNUE: "origine non enregistrée",
}

B_MSG_MONTANT_REQUIS = (
    "Montant encaissé requis. Indique ce qui a été encaissé et comment "
    "(espèces, TWINT, virement), ou coche « offert » si l'accès est gratuit."
)
B_MSG_ORIGINE_REQUISE = (
    "Moyen de paiement requis : espèces, TWINT, virement, ou « offert »."
)
B_MSG_OFFERT_PAYANT = (
    "Un accès déclaré « offert » ne peut pas porter de montant encaissé."
)
B_MSG_ZERO_NON_OFFERT = (
    "Un montant de 0 doit être déclaré « offert » — sinon on ne sait pas si "
    "l'accès a été payé ailleurs."
)


def b_normaliser_origine(valeur) -> str:
    """L'origine telle qu'elle sera stockee, ou "" si elle n'est pas reconnue.

    Tolerante a la saisie (casse, espaces, accents usuels) mais ferme sur le
    vocabulaire : ce qui n'est pas dans `B_ORIGINES_PAIEMENT` ne rentre pas.
    """
    _v = (str(valeur or "")).strip().lower()
    _v = (_v.replace("è", "e").replace("é", "e").replace("ê", "e")
            .replace(" ", "_").replace("-", "_"))
    _alias = {"cash": "especes", "espece": "especes", "liquide": "especes",
              "bank": "virement", "banque": "virement", "iban": "virement",
              "gratuit": "offert", "free": "offert", "cadeau": "offert",
              "carte": "stripe", "card": "stripe"}
    _v = _alias.get(_v, _v)
    return _v if _v in B_ORIGINES_PAIEMENT else ""


def b_valider_encaissement(montant, origine, devise=None, saisi_par: str = "",
                           seances=None, exiger: bool = True) -> dict:
    """Valide une declaration d'encaissement et renvoie les champs a stocker.

    `exiger=False` : la declaration reste FACULTATIVE (code promo sans
    beneficiaire — aucun droit nominatif n'est accorde, aucune souscription
    n'est creee, donc aucun argent n'est cense changer de main). Rien n'est
    exige, mais tout ce qui est fourni est valide de la meme facon : on ne
    stocke jamais une declaration a moitie vraie.

    Leve `HTTPException(400)` sur toute incoherence — jamais de correction
    silencieuse : si le coach se trompe, il doit le voir.
    """
    # Import local : meme convention que le reste de ce module, qui ne depend
    # pas de FastAPI au chargement (il est importe par des scripts hors serveur).
    from fastapi import HTTPException

    _origine = b_normaliser_origine(origine)
    _brute = str(origine or "").strip()
    if _brute and not _origine:
        raise HTTPException(
            status_code=400,
            detail="Moyen de paiement inconnu : « %s ». Valeurs acceptées : %s."
                   % (_brute[:40], ", ".join(B_ORIGINES_MANUELLES)))

    _montant = None
    if montant is not None and str(montant).strip() != "":
        try:
            _montant = round(float(montant), 2)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=B_MSG_MONTANT_REQUIS)
        if _montant < 0:
            raise HTTPException(status_code=400, detail="Le montant encaissé ne peut pas être négatif.")

    if _montant is None and not _origine:
        if exiger:
            raise HTTPException(status_code=400, detail=B_MSG_MONTANT_REQUIS)
        return {}

    if not _origine:
        raise HTTPException(status_code=400, detail=B_MSG_ORIGINE_REQUISE)

    if _origine == "offert":
        # Un geste commercial se declare a 0, sans ambiguite. Un montant non nul
        # est REFUSE plutot que force a 0 : forcer effacerait une vraie recette.
        if _montant:
            raise HTTPException(status_code=400, detail=B_MSG_OFFERT_PAYANT)
        _montant = 0.0
    else:
        if _montant is None:
            raise HTTPException(status_code=400, detail=B_MSG_MONTANT_REQUIS)
        if _montant == 0:
            raise HTTPException(status_code=400, detail=B_MSG_ZERO_NON_OFFERT)

    _champs = {
        "montant_encaisse": _montant,
        "devise": (str(devise or "").strip().upper() or B_DEVISE_DEFAUT)[:8],
        "origine_paiement": _origine,
        "encaissement_saisi_par": (saisi_par or "").strip().lower()[:120],
        "encaissement_saisi_le": datetime.now(timezone.utc).isoformat(),
    }
    # DENOMINATEUR FIGE. `total_sessions` ne peut pas jouer ce role : la
    # reconduction automatique (V195) l'incremente (`$inc`), si bien qu'apres un
    # renouvellement il ne decrit plus l'achat mais leur cumul. Cette valeur-ci
    # n'est ecrite qu'ici, a la creation, et n'est jamais reecrite.
    try:
        _n = int(seances) if seances is not None else 0
        if _n > 0:
            _champs["seances_a_l_achat"] = _n
    except (TypeError, ValueError):
        pass
    return _champs


# Correspondance entre le vocabulaire des moteurs de paiement et `origine_paiement`.
# `card` et `paypal` passent tous deux par Stripe/checkout dans ce code ; seul
# `mobile_money` a son propre moteur (pawaPay).
B_ORIGINE_PAR_MOTEUR = {
    "free": "offert",
    "card": "stripe",
    "paypal": "stripe",
    "stripe": "stripe",
    "mobile_money": "mobile_money",
}


def b_champs_automatiques(moteur: str, montant, devise=None, seances=None) -> dict:
    """La meme trace, posee AUTOMATIQUEMENT par un moteur de paiement.

    Pas de validation ici : le montant vient de Stripe ou de pawaPay, pas d'une
    saisie. On refuse seulement d'inventer une origine pour un moteur inconnu —
    mieux vaut un champ absent qu'une provenance fausse.
    """
    _origine = B_ORIGINE_PAR_MOTEUR.get((str(moteur or "")).strip().lower(), "")
    if not _origine:
        return {}
    try:
        _montant = round(float(montant or 0), 2)
    except (TypeError, ValueError):
        return {}
    _champs = {
        "montant_encaisse": _montant,
        "devise": (str(devise or "").strip().upper() or B_DEVISE_DEFAUT)[:8],
        "origine_paiement": _origine,
        "encaissement_saisi_par": "",          # personne : c'est le moteur
        "encaissement_saisi_le": datetime.now(timezone.utc).isoformat(),
    }
    try:
        _n = int(seances or 0)
        if _n > 0:
            _champs["seances_a_l_achat"] = _n
    except (TypeError, ValueError):
        pass
    return _champs


def b_champs_depuis_code(code_doc: dict, seances=None) -> dict:
    """Les champs financiers a RECOPIER d'un code vers la souscription qu'il ouvre.

    Recopie, et non recalcul : la declaration a ete faite une fois, au moment ou
    l'argent a change de main. Un document anterieur au lot B n'en porte aucun —
    on renvoie alors {} et la souscription reste sans montant, ce qui est la
    verite.
    """
    if not isinstance(code_doc, dict):
        return {}
    _origine = b_normaliser_origine(code_doc.get("origine_paiement"))
    if not _origine:
        return {}
    _champs = {
        "montant_encaisse": code_doc.get("montant_encaisse"),
        "devise": code_doc.get("devise") or B_DEVISE_DEFAUT,
        "origine_paiement": _origine,
        "encaissement_saisi_par": code_doc.get("encaissement_saisi_par") or "",
        "encaissement_saisi_le": code_doc.get("encaissement_saisi_le") or "",
    }
    _n = code_doc.get("seances_a_l_achat")
    if _n is None:
        _n = seances
    try:
        _n = int(_n) if _n is not None else 0
        if _n > 0:
            _champs["seances_a_l_achat"] = _n
    except (TypeError, ValueError):
        pass
    return _champs


# ============================================================================
# LOT A — LIRE L'ARGENT SANS JAMAIS L'INVENTER
# ============================================================================
#
# Ce lot n'ecrit RIEN. Il repond a une seule question, pour une reservation, une
# transaction ou une souscription : « combien, et comment le sait-on ? »
#
# TROIS REPONSES POSSIBLES, ET TROIS SEULEMENT :
#   * un montant PROUVE   — adosse a une session Stripe, une transaction de
#                           checkout, ou une declaration d'encaissement (lot B) ;
#   * un montant DECLARE  — saisi a la main autrefois, ou tarif fige a la
#                           creation du code : plausible, mais rien ne prouve
#                           qu'il a ete encaisse. Il est affiche AVEC sa reserve ;
#   * RIEN                — et alors on ecrit « Montant non enregistre ».
#
# « CHF 0 » N'EST JAMAIS UNE REPONSE PAR DEFAUT. Zero est un montant REEL : il
# veut dire offert ou essai gratuit, et n'est rendu que lorsque la gratuite est
# etablie. Un trou se dit, il ne s'arrondit pas.
#
# AUCUNE LECTURE DU CATALOGUE. `offers.price` est le prix D'AUJOURD'HUI ; le
# faire apparaitre en face d'un achat d'hier reecrirait l'histoire. Le catalogue
# n'est jamais consulte ici — c'est la garantie du point G de l'audit.

# ── CHF ou centimes : la table, etablie par les DONNEES, pas par l'intuition ──
#
# Mesure du 19/08/2026 sur `payment_transactions` (11 documents portant les deux
# champs) : amount=150.0 / amount_total=15000, amount=2.0 / amount_total=200,
# amount=10.0 / amount_total=4000 (4 unites a 10 CHF).
# On en tire DEUX faits, et on n'extrapole pas au-dela :
#   `amount`       — CHF, et c'est le prix UNITAIRE (V225) ;
#   `amount_total` — CENTIMES, et c'est le total REELLEMENT encaisse par Stripe.
# Tous les autres champs monetaires de la base sont en CHF :
#   discount_codes.stripe_amount / total_paid, subscriptions.renewal_price /
#   offer_price, reservations.totalPrice, et `montant_encaisse` (lot B).
# Aucune conversion n'est appliquee « au cas ou » : seul `amount_total` est
# divise par 100, parce que lui seul est en centimes.
A_CHAMPS_EN_CENTIMES = ("amount_total",)


def a_nombre(valeur):
    """Un float, ou None. Ne confond jamais 0 et « absent »."""
    if valeur is None or valeur is True or valeur is False:
        return None
    if isinstance(valeur, str) and not valeur.strip():
        return None
    try:
        return round(float(valeur), 2)
    except (TypeError, ValueError):
        return None


def a_montant_transaction(tx: dict) -> tuple:
    """Le montant d'une `payment_transactions`, en CHF, et sa fiabilite.

    Renvoie `(montant, prouve)`. `amount_total` vient du webhook Stripe : c'est
    ce que Stripe a REELLEMENT encaisse, donc une preuve. `amount` est le prix
    unitaire annonce AU MOMENT du checkout — il faut le multiplier par la
    quantite, et il ne prouve pas l'encaissement (165 transactions sur 182 sont
    restees `pending`, donc jamais payees).
    """
    if not isinstance(tx, dict):
        return (None, False)
    _cts = a_nombre(tx.get("amount_total"))
    if _cts is not None:
        return (round(_cts / 100.0, 2), True)
    _unit = a_nombre(tx.get("amount"))
    if _unit is None:
        return (None, False)
    try:
        _q = int(tx.get("quantity") or 1)
    except (TypeError, ValueError):
        _q = 1
    return (round(_unit * max(1, _q), 2), False)


# ── Le denominateur d'une valeur par seance ─────────────────────────────────
#
# Il doit etre le nombre de seances ACHETEES, fige au moment de la transaction.
# `total_sessions` est EXCLU : la reconduction automatique (V195) l'incremente
# (`$inc`), si bien qu'apres un renouvellement il decrit un cumul, pas un achat.
# `remaining_sessions` est exclu pour la meme raison, en pire : les boutons +/-
# du tableau de bord (V236) le modifient a la main.
# Restent, par ordre de fiabilite decroissante :
#   `seances_a_l_achat`  (lot B) — ecrit une seule fois, jamais reecrit ;
#   `renewal_sessions`            — pose a l'achat par les moteurs de paiement,
#                                   jamais reecrit (verifie : la reconduction ne
#                                   touche que `total_sessions`) ;
#   `maxUses` du code             — pose a la creation, mais MODIFIABLE ensuite
#                                   par le formulaire d'edition. D'ou le « ≈ »
#                                   systematique sur la valeur par seance.
def a_seances_achetees(souscription: dict, code: dict):
    for _src, _cle in ((souscription, "seances_a_l_achat"),
                       (souscription, "renewal_sessions"),
                       (code, "seances_a_l_achat"),
                       (code, "maxUses")):
        try:
            _n = int((_src or {}).get(_cle) or 0)
        except (TypeError, ValueError):
            _n = 0
        if _n > 0:
            return _n
    return None


def a_est_gratuit_prouve(code: dict) -> bool:
    """La gratuite est-elle ETABLIE ? Meme signal qu'ESSAI-1/ESSAI-2.

    On ne se fie ni au nom de l'offre (« Essai gratuit! » a deja derive) ni a
    l'absence de montant, qui ne prouve rien.
    """
    if not isinstance(code, dict):
        return False
    if b_normaliser_origine(code.get("origine_paiement")) == "offert":
        return True
    if code.get("source") == "social_proof":
        return True
    return code.get("payment_method") == "free" and code.get("total_paid") == 0


# Les sources de montant, de la plus sure a la moins sure. `prouve` dit si un
# encaissement est ADOSSE a une trace (session Stripe, transaction, declaration
# explicite) — c'est lui qui autorise le calcul d'une valeur par seance.
A_LIBELLES_SOURCE = {
    "encaissement": "encaissement déclaré",
    "stripe": "paiement Stripe",
    "checkout": "paiement en ligne",
    "saisie_ancienne": "montant saisi à la main",
    "tarif_creation": "tarif de l'offre à la création — pas une preuve de paiement",
    "reservation": "montant porté par la réservation",
}


def a_finance_du_droit(souscription: dict, code: dict, reservation: dict = None) -> dict:
    """Ce qu'on sait de l'argent derriere UN droit d'acces. Lecture pure.

    `souscription` et `code` sont les deux documents jumeaux qui portent le
    droit ; `reservation` n'est utilisee qu'en dernier recours, pour les achats
    directs qui ne creent ni l'un ni l'autre.
    """
    _sub = souscription if isinstance(souscription, dict) else {}
    _code = code if isinstance(code, dict) else {}
    _resa = reservation if isinstance(reservation, dict) else {}

    _res = {
        "offre": (_sub.get("offer_name") or _code.get("offerName")
                  or _resa.get("offerName") or ""),
        "code": (_sub.get("code") or _code.get("code") or _resa.get("promoCode")
                 or _resa.get("discountCode") or ""),
        "montant": None,
        "devise": (_sub.get("devise") or _code.get("devise")
                   or _code.get("paid_currency") or _code.get("currency")
                   or B_DEVISE_DEFAUT),
        "montant_source": "",
        "montant_prouve": False,
        "origine_paiement": "",
        "gratuit": False,
        "seances_achetees": a_seances_achetees(_sub, _code),
        "valeur_par_seance": None,
    }

    # 1. La declaration du lot B — la seule qui porte sa provenance avec elle.
    for _doc in (_sub, _code):
        _origine = b_normaliser_origine(_doc.get("origine_paiement"))
        _montant = a_nombre(_doc.get("montant_encaisse"))
        if _origine and _montant is not None:
            _res.update(montant=_montant, montant_source="encaissement",
                        montant_prouve=True, origine_paiement=_origine,
                        gratuit=(_montant == 0))
            _res["devise"] = _doc.get("devise") or _res["devise"]
            break

    # 2. Un paiement en ligne ADOSSE a sa session / sa transaction.
    if not _res["montant_source"]:
        _stripe = a_nombre(_code.get("stripe_amount"))
        _paid = a_nombre(_code.get("total_paid"))
        if _stripe is not None and _code.get("session_id"):
            _res.update(montant=_stripe, montant_source="stripe",
                        montant_prouve=True, origine_paiement="stripe")
        elif _paid is not None and _code.get("transaction_id"):
            _res.update(montant=_paid, montant_source="checkout", montant_prouve=True,
                        origine_paiement=b_normaliser_origine(_code.get("payment_method")))
            _res["gratuit"] = (_paid == 0)

    # 3. La gratuite etablie autrement (essai de la vitrine, preuve sociale).
    if not _res["montant_source"] and a_est_gratuit_prouve(_code):
        _res.update(montant=0.0, montant_source="encaissement", montant_prouve=True,
                    origine_paiement="offert", gratuit=True)

    # 4. Montants DECLARES : plausibles, mais rien ne prouve l'encaissement.
    #    Ils sont rendus avec `montant_prouve=False` — l'interface le dit, et
    #    aucune valeur par seance n'en est tiree.
    if not _res["montant_source"]:
        _renouv = a_nombre(_sub.get("renewal_price"))
        _stripe = a_nombre(_code.get("stripe_amount"))
        _tarif = a_nombre(_sub.get("offer_price"))
        _resa_prix = a_nombre(_resa.get("totalPrice"))
        if _renouv:                      # 0 exclu : ce n'est pas une gratuite prouvee
            _res.update(montant=_renouv, montant_source="saisie_ancienne")
        elif _stripe:
            _res.update(montant=_stripe, montant_source="saisie_ancienne")
        elif _tarif:
            _res.update(montant=_tarif, montant_source="tarif_creation")
        elif _resa_prix:
            _res.update(montant=_resa_prix, montant_source="reservation")

    # 5. La valeur indicative par seance — jamais sur un montant non prouve, et
    #    jamais sur un pack d'une seule seance (elle n'apprendrait rien).
    if (_res["montant_prouve"] and _res["montant"] and _res["seances_achetees"]
            and _res["seances_achetees"] > 1):
        _res["valeur_par_seance"] = round(_res["montant"] / _res["seances_achetees"], 2)

    _res["libelle"] = a_libelle_montant(_res)
    return _res


def a_libelle_montant(fin: dict) -> str:
    """La phrase que le coach lit. Une seule ecriture pour les deux interfaces."""
    if not isinstance(fin, dict) or fin.get("montant") is None:
        return "Montant non enregistré"
    _dev = fin.get("devise") or B_DEVISE_DEFAUT
    if fin.get("gratuit"):
        _quoi = B_LIBELLES_ORIGINE.get(fin.get("origine_paiement"), "")
        return "GRATUIT — %s" % (_quoi or "offert")
    _txt = "%s %.2f" % (_dev, fin["montant"])
    if not fin.get("montant_prouve"):
        _txt += (" — tarif à la création, non confirmé"
                 if fin.get("montant_source") == "tarif_creation"
                 else " — saisi à la main")
    return _txt


# ============================================================================
# LOT A — L'APRES-ESSAI : CE QU'ON PROPOSE, ET CE QU'ON REFUSE
# ============================================================================
#
# CE QUE CE LOT AJOUTE. Quelqu'un vient de faire sa seance decouverte. Jusqu'ici
# son espace lui disait « Essai effectue » et s'arretait la : aucune suite, aucun
# tarif, aucun bouton. Ce lot rend l'ecran qui manquait, et RIEN d'autre.
#
# CE QUE CE LOT N'EST PAS. Il n'y a AUCUN moteur d'adhesion dans ce depot :
# ni statut de membre, ni duree d'adhesion, ni renouvellement, ni reduction
# events. Tant qu'il n'existe pas, l'offre « Membres / renouvellement » ne peut
# etre ni promise ni vendue par ce parcours — non pas parce qu'elle coute 150,
# mais parce que RIEN ne sait dire qui est membre.
#
# ═══════════════════════════════════════════════════════════════════════════
# POURQUOI UN CHAMP EXPLICITE, ET PAS UNE DEDUCTION
# ═══════════════════════════════════════════════════════════════════════════
# Audit des champs existants de `offers` (server.py, classe `Offer`) : `price`,
# `name`, `description`, `pack_sessions`, `category`, `isProduct`, `visible`,
# `position`. AUCUN ne porte la distinction « premier achat » / « reserve a un
# membre ». `category` est une chaine libre remplie a la main (« service »,
# « tshirt »…), `visible` est un drapeau d'AFFICHAGE vitrine, et le prix n'est
# pas une identite metier : le jour ou le pack passe a 260 ou l'adhesion a 140,
# une regle ecrite sur les montants vendrait la mauvaise offre en silence.
#
# On ajoute donc UN booleen explicite, `first_purchase_eligible`, pose par le
# coach depuis le formulaire d'offre. Par defaut FAUX : tant que personne n'a
# rien declare, cet ecran ne propose RIEN. C'est le sens de « fail closed » —
# une offre oubliee ne se vend pas, au lieu de se vendre par accident.
#
# QUAND LE LOT ADHESION ARRIVERA, il posera sa propre dimension (« reserve aux
# membres actifs ») et decidera lui-meme du renouvellement. Ce booleen n'aura
# pas a etre defait : il continuera de dire ce qu'il dit — « cette offre est
# proposable a quelqu'un qui n'a encore rien achete ».

CONV_INELIGIBLE = "not_eligible"
CONV_OUVERTE = "open"
CONV_TERMINEE = "purchased"


async def conv_presence_reelle(db, forfait: dict):
    """La presence d'essai qui OUVRE le droit a la conversion, ou None.

    Plus stricte que `essai2_presence_essai`, et volontairement : celle-ci se
    contente de `validated: True`. Ici on exige EN PLUS que la reservation
    designe une seance qui a REELLEMENT eu lieu — meme garde A1/A1b que le
    portier d'entree (`_a1b_occurrences_reelles`), donc :
      * le cours existe encore dans la collection ;
      * il n'est pas archive ;
      * il a bien lieu le jour porte par la reservation.

    C'est ce qui empeche un cours HISTORIQUE — un ponctuel passe, un cours
    supprime — d'ouvrir une conversion. Le defaut existe : c'est exactement le
    residu « Diner canadien » constate le 19/08/2026, ou une reservation datee
    du jour designait un cours qui n'avait pas lieu.

    UNE SEULE DEFINITION de « cette reservation designe une vraie seance » dans
    tout le depot : on importe celle du portier au lieu de la recopier. L'import
    est differe (`reservation_routes` importe deja ce module).

    ECHEC D'IMPORT -> AUCUNE CONVERSION. C'est le seul comportement acceptable
    ici : une conversion manquee coute une vente, une conversion accordee a
    tort encaisse de l'argent sur un droit qui n'existe pas.
    """
    if not forfait:
        return None
    _sid = (forfait.get("id") or "").strip()
    _code = (forfait.get("code") or "").strip().upper()
    _ou = []
    if _sid:
        _ou.append({"subscriptionId": _sid})
    if _code:
        _ou.append({"promoCode": _code})
        _ou.append({"discountCode": _code})
    if not _ou:
        return None
    try:
        _rows = await db["reservations"].find(
            {"validated": True, "$or": _ou}, {"_id": 0}).to_list(20)
    except Exception as _err:
        logger.warning(f"[LOT-A] presences illisibles: {_err}")
        return None
    if not _rows:
        return None
    try:
        from api.routes.reservation_routes import _a1b_occurrences_reelles as _a1b
        _rows = await _a1b(_rows)
    except Exception as _err:
        logger.error("[LOT-A] garde A1b indisponible, conversion refusee: %s", _err)
        return None
    if not _rows:
        return None
    _rows.sort(key=lambda x: str(x.get("validatedAt") or ""))
    return _rows[0]


async def conv_offres_premier_achat(db, coach_id: str = "") -> list:
    """Les offres proposables APRES un essai, dans l'ordre d'affichage.

    QUATRE FILTRES, tous explicites :
      1. `first_purchase_eligible: True` — la declaration du coach, et la seule
         chose qui autorise. Absent ou faux -> l'offre n'existe pas pour cet
         ecran. C'est ce qui exclut l'offre « Membres / renouvellement » sans
         jamais nommer son prix ni son libelle.
      2. le coach proprietaire, SYMETRIQUEMENT — et c'est tout le sujet du
         repli ci-dessous. Un essai qui declare un coach ne voit QUE les offres
         de ce coach. Un essai qui n'en declare AUCUN — cas de tout le stock
         historique — ne voit que les offres qui n'en declarent aucun non plus.
         Jamais celles d'un partenaire identifie : une offre explicitement
         possedee n'est pas « sans proprietaire », et la projeter serait une
         fuite entre catalogues.
      3. un prix STRICTEMENT positif. Un ecran de conversion propose un ACHAT ;
         une offre a 0 CHF y serait un second essai gratuit, que les gardes
         ESSAI-1 / ESSAI-4 refuseraient de toute facon au passage en caisse.
         Ce n'est pas une regle sur les montants : c'est la definition meme de
         « convertir ».
      4. rien d'autre. `visible` N'EST PAS consulte — decision explicite, meme
         raisonnement qu'A1b : c'est un drapeau de vitrine, pas de cycle de vie.
         Une offre que le coach a explicitement declaree « apres essai » ne doit
         pas disparaitre de cet ecran parce qu'il l'a masquee de sa page
         d'accueil. Pour la retirer d'ici, on decoche la case d'ici.

    L'ORDRE vient de `position` (le champ de tri deja utilise par la vitrine et
    le glisser-deposer du dashboard), les offres sans position passant en
    dernier, puis du nom pour que deux positions egales ne s'inversent pas d'un
    chargement a l'autre. La PREMIERE porte `recommended` : cette regle vit ici
    et nulle part ailleurs, pour que l'ecran n'ait rien a decider.

    LE PRIX RENDU EST CELUI QUE LA CAISSE DEBITERA — `offers.price`, la valeur
    que `_essai1b_prix_unitaire` retient. Surtout pas le prix progressif calcule
    a la lecture : l'ecran et la caisse diraient alors deux montants differents.
    """
    _q = {"first_purchase_eligible": True}
    _cid = (coach_id or "").strip()
    if _cid:
        _q["coach_id"] = _cid
    else:
        # PROPRIETAIRE INCONNU -> CATALOGUE SANS PROPRIETAIRE, ET RIEN D'AUTRE.
        #
        # Mesure du 19/08/2026 : les 8 offres de production portent `coach_id`
        # nul, et le forfait d'essai comme son code portent la chaine vide. Le
        # repli precedent — se rabattre sur le compte proprietaire de la
        # plateforme — cherchait donc un `coach_id` que RIEN ne porte : la
        # projection etait vide quoi que le coach coche.
        #
        # La regle est desormais SYMETRIQUE : sans proprietaire d'un cote, on ne
        # regarde que ce qui n'a pas de proprietaire de l'autre. Un partenaire
        # identifie garde son catalogue pour lui — c'est le sens du `$or`
        # ci-dessous, qui enumere les trois formes reelles de « sans
        # proprietaire » et AUCUNE autre. Fail closed conserve : l'offre doit de
        # toute facon etre cochee.
        _q["$or"] = [{"coach_id": None}, {"coach_id": ""},
                     {"coach_id": {"$exists": False}}]
    try:
        _rows = await db["offers"].find(_q, {"_id": 0}).to_list(50)
    except Exception as _err:
        logger.warning(f"[LOT-A] catalogue de conversion illisible: {_err}")
        return []

    _utiles = []
    for _o in _rows:
        try:
            _prix = float(_o.get("price") or 0)
        except (TypeError, ValueError):
            continue
        if _prix <= 0:
            continue
        _utiles.append((_o, _prix))

    def _rang(couple):
        _o = couple[0]
        _p = _o.get("position")
        try:
            _p = int(_p)
        except (TypeError, ValueError):
            _p = 10 ** 6
        return (_p, str(_o.get("name") or ""))

    _utiles.sort(key=_rang)

    _sortie = []
    for _i, (_o, _prix) in enumerate(_utiles):
        try:
            _seances = int(_o.get("pack_sessions") or 0)
        except (TypeError, ValueError):
            _seances = 0
        _sortie.append({
            "id": _o.get("id"),
            "name": _o.get("name") or "",
            "price": _prix,
            "currency": B_DEVISE_DEFAUT,
            "sessions": _seances or None,
            "description": (_o.get("description") or "")[:280],
            "thumbnail": _o.get("thumbnail") or "",
            "recommended": _i == 0,
        })
    return _sortie


async def conv_offre_autorisee(db, offer_id: str, coach_id: str = ""):
    """L'offre demandee SI elle est proposable apres un essai, sinon None.

    LA GARDE DE NIVEAU 2. Le niveau 1 (ce que l'ecran montre) n'est pas une
    barriere : n'importe qui peut poster l'identifiant d'une autre offre. Cette
    fonction relit la MEME regle que `conv_offres_premier_achat`, sur la base,
    au moment de l'achat. Un identifiant d'offre non declaree — celle du
    renouvellement a 150 comme n'importe quelle autre — ressort None, et
    l'appelant refuse.

    Elle est CONTEXTUELLE : elle n'est appelee que par le passage en caisse de
    la conversion. Les parcours existants (vitrine, boutique, renouvellement)
    ne la traversent jamais et ne changent pas d'un octet.
    """
    _oid = (offer_id or "").strip()
    if not _oid:
        return None
    _autorisees = await conv_offres_premier_achat(db, coach_id)
    for _o in _autorisees:
        if _o.get("id") == _oid:
            return _o
    return None


async def conv_etat(db, forfait: dict, coach_id: str = "") -> dict:
    """L'etat de conversion d'un forfait. LECTURE PURE — aucune ecriture.

    LA REGLE D'ELIGIBILITE, en entier et dans cet ordre :
      1. le forfait existe ;
      2. son code est un code d'ESSAI (`ESSAI2_FILTRE_GRATUIT`, la meme
         definition qu'ESSAI-2 et que l'ecran d'etat d'essai — un forfait payant
         n'est jamais un prospect a convertir) ;
      3. une reservation rattachee a ce forfait est `validated` ET designe une
         seance reelle (A1/A1b) ;
      4. si `converted_at` est deja pose, la conversion est TERMINEE : l'ecran
         cesse de traiter la personne comme un prospect.

    Ce qui NE declenche RIEN, et c'est l'essentiel : une reservation seule, un
    compteur tombe a zero, une date passee, un cours archive ou supprime, une
    vieille reservation, l'ouverture de l'espace. Aucun de ces signaux n'entre
    dans la regle ci-dessus.
    """
    _vide = {"eligible": False, "state": CONV_INELIGIBLE, "offers": [],
             "reason": "no_subscription"}
    if not forfait:
        return _vide

    _code = (forfait.get("code") or "").strip().upper()
    if not _code:
        return dict(_vide, reason="no_code")
    try:
        _q = {"code": _code}
        _q.update(ESSAI2_FILTRE_GRATUIT)
        if not await db["discount_codes"].find_one(_q, {"_id": 1}):
            return dict(_vide, reason="not_a_trial")
    except Exception as _err:
        logger.warning("[LOT-A] nature du code indeterminee: %s", _err)
        return dict(_vide, reason="unreadable")

    _presence = await conv_presence_reelle(db, forfait)
    if not _presence:
        return dict(_vide, reason="not_attended")

    if forfait.get("converted_at"):
        return {"eligible": True, "state": CONV_TERMINEE, "offers": [],
                "reason": "already_converted",
                "attended_at": _presence.get("validatedAt") or ""}

    return {
        "eligible": True,
        "state": CONV_OUVERTE,
        "reason": "",
        "attended_at": _presence.get("validatedAt") or "",
        "offers": await conv_offres_premier_achat(db, coach_id),
    }


async def conv_marquer_vue(db, forfait: dict, offres: int = 0) -> bool:
    """`conversion_viewed`, UNE SEULE FOIS. Rend True si c'est cet appel qui a
    marque.

    L'IDEMPOTENCE EST PORTEE PAR MONGO, pas par le navigateur ni par un compteur
    applicatif : le filtre exige l'ABSENCE de `conversion_first_viewed_at`, et
    la base ne l'accorde qu'a un seul ecrivain. Dix rafraichissements, deux
    onglets simultanes, deux scans du meme QR : un evenement metier, et un seul.
    C'est le meme motif que `converted_at` (ESSAI-2) et que le verrou de
    renouvellement (V447).

    LE GET N'ECRIT PAS A CHAQUE LECTURE. L'appelant ne passe ici que lorsque la
    date est ABSENTE du document deja charge ; une fois posee, il n'y a plus
    aucune tentative d'ecriture — zero write par rafraichissement ensuite.

    DEUX DATES, POSEES ENSEMBLE. `conversion_eligible_at` dit « le droit s'est
    ouvert », `conversion_first_viewed_at` dit « l'ecran a ete montre ». Elles
    sont egales aujourd'hui parce que la SEULE chose qui constate l'eligibilite
    est l'ecran lui-meme. Le jour ou un autre chemin la constatera — un rappel
    post-cours, par exemple — la date de vue ne mentira pas pour autant.

    `trial_attended` N'EST PAS EMIS ICI, et ce n'est pas un oubli : il existe
    deja sous le nom `attendance_checked_in` avec `is_free_trial: true` (C9-A,
    reservation_routes), emis exactement une fois par transition de presence, au
    scan — c'est-a-dire au moment ou la presence a REELLEMENT lieu. Le reemettre
    ici le ferait dependre de l'ouverture de l'espace : la mesure serait fausse
    pour quiconque vient au cours sans ouvrir son telephone apres.
    """
    if not forfait or not forfait.get("id"):
        return False
    _quand = datetime.now(timezone.utc).isoformat()
    try:
        _res = await db["subscriptions"].update_one(
            {"id": forfait.get("id"),
             "conversion_first_viewed_at": {"$exists": False}},
            {"$set": {"conversion_eligible_at": _quand,
                      "conversion_first_viewed_at": _quand}},
        )
        if not getattr(_res, "matched_count", 0):
            return False            # deja vu : rien a mesurer une seconde fois
    except Exception as _err:
        logger.warning(f"[LOT-A] premiere vue non marquee: {_err}")
        return False

    try:
        await posthog_capture("conversion_viewed",
                              email=(forfait.get("email") or ""),
                              props={"offers_shown": int(offres or 0),
                                     "trial_offer_id": str(forfait.get("offer_id") or "")[:64]})
    except Exception as _err:
        logger.warning(f"[LOT-A] conversion_viewed non emis: {_err}")
    return True


# ============================================================================
# LOT 2 — L'ADHESION QUI NAIT D'UN ACHAT
# ============================================================================
#
# CE QUE CE LOT AJOUTE. Jusqu'ici une adhesion ne pouvait exister que par la
# main du coach (`POST /memberships`, source « saisie_manuelle ») — et il y en
# avait ZERO en production, la collection n'etant meme pas creee. Desormais un
# achat de l'offre d'entree en cree une, seul, une fois, pour un an.
#
# ═══════════════════════════════════════════════════════════════════════════
# QUATRE DECISIONS, ET CE QU'ELLES REFUSENT
# ═══════════════════════════════════════════════════════════════════════════
#
# 1. AUCUNE DEDUCTION PAR LE PRIX. Pas de `if price == 250`. Le prix bouge, la
#    regle non. C'est un booleen EXPLICITE pose a la main par le coach sur
#    l'offre (`creates_membership`), faux par defaut — meme patron que
#    `first_purchase_eligible` (LOT A), et pour la meme raison : le jour ou
#    l'offre passe a 260, rien ne doit changer. Le depot avait deja tranche ce
#    point deux fois (server.py « le prix n'est pas une identite metier »,
#    membership_routes.py « aucune adhesion n'est creee a partir d'un nom ou
#    d'un montant »). On ne le retranche pas ici.
#
#    LOT 2.1 — PRECISION, ET NON RENVERSEMENT. Le prix est desormais LU, mais
#    jamais pour IDENTIFIER une offre : aucune comparaison a 250, ni a aucun
#    autre palier, n'existe dans ce fichier (le test 7e le verifie par AST).
#    Il sert uniquement de BORNE BASSE : ce qui est donne n'ouvre pas un droit
#    d'un an. Identifier et borner sont deux usages differents. La regle « le
#    prix bouge, la regle non » reste donc entiere : le jour ou PULSE passe a
#    260, la garde ne bronche pas — elle ne se declenche qu'a zero.
#
#    A NE PAS CONFONDRE avec `_C9_PULSE = ("a687ce86", "484c4519")`
#    (server.py) : deux identifiants d'offre codes en dur, qui servent
#    UNIQUEMENT a etiqueter un evenement d'analytique. Aucune decision metier
#    n'en depend, et ce lot n'en ajoute pas.
#
# 2. UN SEUL POINT D'ENTREE POUR DEUX CHEMINS D'AUTORITE. Le depot reconnait un
#    paiement reussi a DEUX endroits : le webhook Stripe « client »
#    (server.py, branche `checkout.session.completed`) et
#    `_process_successful_payment` (checkout_routes.py), lui-meme servi par
#    QUATRE webhooks (Stripe vitrine, CinetPay, PayPal, PawaPay) et deux
#    chemins gratuits. Un achat depuis la vitrine ou depuis l'ecran
#    d'apres-essai passe par le SECOND. Brancher l'adhesion sur un seul aurait
#    manque la moitie des achats — d'ou cette fonction unique, appelee des
#    deux. Une seule definition de « cet achat ouvre une adhesion ».
#
# 3. LE PROPRIETAIRE VIENT DE L'OFFRE EN BASE, JAMAIS DU NAVIGATEUR, JAMAIS
#    D'UN REPLI. `req.coach_email` est une chaine libre du corps de requete :
#    deux ecrans de cette meme application y mettent aujourd'hui des valeurs
#    DIFFERENTES pour le meme achat (mesure du 19/08/2026 : 7 souscriptions
#    `checkout_vitrine` a `coach_id: ""` contre 1 a l'adresse de l'admin). On
#    ne s'en sert donc pas. Et surtout on n'emprunte PAS `DEFAULT_COACH_ID` :
#    depuis V244 cette constante ne vaut plus la sentinelle « bassi_default »
#    mais L'ADRESSE REELLE DU SUPER-ADMIN. Une adhesion ecrite avec cette
#    adresse serait INVISIBLE dans l'ecran Adhesions, dont le filtre « sans
#    proprietaire » ne cherche que None / "" / champ absent : les deux
#    vocabulaires sont mutuellement aveugles. Offre sans proprietaire ->
#    adhesion sans proprietaire. Strictement symetrique, comme `2c8a831`.
#
# 4. UNE ADHESION ACTIVE N'EST NI DOUBLEE NI PROLONGEE. L'offre d'entree est
#    l'offre d'un NOUVEAU membre. Prolonger serait du renouvellement, et le
#    renouvellement appartient a l'offre suivante — qui n'existe pas encore
#    comme parcours. Creer un second document ferait deux adhesions qui se
#    chevauchent, ce que le proprietaire a explicitement refuse : il veut UNE
#    continuite. Donc : rien, et on le dit dans les journaux.

LOT2_PREFIXE = "[LOT2]"

# `source` du document. La saisie a la main garde « saisie_manuelle » : on doit
# pouvoir distinguer d'un coup d'oeil ce que le systeme a decide de ce que le
# coach a declare.
LOT2_SOURCE = "achat"

# Prefixe du VERROU (voir `lot2_creer_adhesion_apres_achat`). Lisible a l'oeil
# dans la base, et impossible a confondre avec un uuid.
LOT2_VERROU = "adh:"

# Motifs de non-creation. Codes STABLES, pensés pour etre cherches dans les
# journaux (`grep "motif=deja_membre"`). Ne jamais les traduire.
LOT2_MOTIFS = (
    "donnees_incompletes",     # il manque l'e-mail, l'offre ou le forfait
    "offre_introuvable",       # l'identifiant ne designe aucune offre
    "offre_non_adherente",     # la case n'est pas cochee — LE CAS NORMAL
    "deja_membre",             # une adhesion est encore valide : on ne touche a rien
    "rejeu",                   # le meme paiement, une seconde fois
    "echec_ecriture",          # la base a refuse, pour une autre raison
    # LOT 2.1 — DEUX motifs distincts, et ce n'est pas de la coquetterie :
    # « l'offre se donne » est une CONFIGURATION a corriger dans le dashboard,
    # « rien n'a ete encaisse » est un fait comptable sur CET achat-la. Les
    # confondre rendrait le premier introuvable dans les journaux.
    "offre_gratuite",          # LOT 2.1 : prix de vente resolu a 0 -> jamais d'adhesion
    "montant_nul",             # LOT 2.1 : offre payante, mais 0 reellement encaisse
)


def lot2_proprietaire(coach_id_de_loffre):
    """Le proprietaire a inscrire sur l'adhesion : celui de l'offre, ou personne.

    Traduit les TROIS formes de « sans proprietaire » reellement presentes en
    base (None, "", champ absent) vers la SEULE que le module adhesions
    reconnait : None. Sans cette traduction, une offre portant `coach_id: ""`
    produirait une adhesion a `""` que `p1a_filtre_proprietaire` retrouverait
    — mais une offre a `coach_id` absent produirait `None`, et les deux
    coexisteraient pour la meme realite. Une seule forme, decidee ici.

    JAMAIS `DEFAULT_COACH_ID` : voir la decision 3 en tete de section.
    """
    if not isinstance(coach_id_de_loffre, str):
        return None
    _c = coach_id_de_loffre.strip().lower()
    return _c or None


def lot2_fin_adhesion(date_debut_iso: str) -> str:
    """La fin d'une adhesion d'un an : « debut + 1 an - 1 jour », AAAA-MM-JJ.

    POURQUOI MOINS UN JOUR. `p1a_statut` inclut les DEUX bornes : une adhesion
    du 01/01 au 31/12 est active le 01/01 comme le 31/12. « Un an » se termine
    donc la veille du meme jour l'annee suivante — 365 jours bornes incluses.
    C'est la convention du proprietaire, et elle reproduit ses trois exemples :
        19/08/2026 -> 18/08/2027       01/01/2026 -> 31/12/2026
        et, pour une prolongation, 31/12/2026 -> 31/12/2027 (voir plus bas).

    LE 29 FEVRIER. `date.replace(year=+1)` leve sur une annee non bissextile.
    Le proprietaire a tranche : la fin est le 28/02 de l'annee suivante — soit
    une annee pleine (29/02/2028 -> 28/02/2029 = 365 jours bornes incluses),
    et non le 27/02 qu'un « -1 jour » applique apres un repli au 28 donnerait.

    Une date illisible rend "" : l'appelant refuse alors de creer, plutot que
    de poser une adhesion dont personne ne saurait dire quand elle finit.
    """
    from datetime import date as _date
    _v = str(date_debut_iso or "").strip()[:10]
    try:
        _d = _date.fromisoformat(_v)
    except (TypeError, ValueError):
        return ""
    try:
        return (_d.replace(year=_d.year + 1) - timedelta(days=1)).isoformat()
    except ValueError:
        # Seul cas possible : le 29 fevrier. Decision du proprietaire.
        return _date(_d.year + 1, 2, 28).isoformat()


def lot2_prolonger_fin(date_fin_iso: str) -> str:
    """CAS A — prolonger une adhesion ENCORE VALIDE : date_fin + 1 an.

    ⚠️ ECRITE ET TESTEE, MAIS VOLONTAIREMENT INACTIVE DANS CE LOT.
    AUCUN chemin de production ne l'appelle, et un test le PROUVE. Elle existe
    pour que le lot du renouvellement (l'offre suivante) n'ait pas a
    reinventer la regle sous pression, et pour qu'elle soit deja eprouvee le
    jour ou on la branchera.

    La regle, validee par le proprietaire : `date_debut` NE BOUGE PAS, seule
    `date_fin` avance d'un an. Une seule continuite d'adhesion, jamais deux
    periodes qui se chevauchent. Exemple : une adhesion 01/01/2026 -> 31/12/2026
    renouvelee le 15/12/2026 devient 01/01/2026 -> 31/12/2027.

    Pas de « -1 jour » ici, a la difference de `lot2_fin_adhesion` : on ne
    calcule pas une duree depuis un debut, on DEPLACE une fin d'exactement un
    an. Le 31/12 reste le 31/12.
    """
    from datetime import date as _date
    _v = str(date_fin_iso or "").strip()[:10]
    try:
        _f = _date.fromisoformat(_v)
    except (TypeError, ValueError):
        return ""
    try:
        return _f.replace(year=_f.year + 1).isoformat()
    except ValueError:
        return _date(_f.year + 1, 2, 28).isoformat()


def lot2_est_doublon(erreur) -> bool:
    """Cette erreur d'ecriture est-elle « ce document existe deja » ?

    Reconnue par le code MongoDB 11000 ET par le nom de la classe : le premier
    couvre le vrai pilote, le second les doubles de test. Aucun des deux ne
    depend d'un message traduit.
    """
    if getattr(erreur, "code", None) == 11000:
        return True
    return "duplicatekey" in type(erreur).__name__.replace("_", "").lower()


async def lot2_offre_adherente(db, offre_id: str):
    """Rend `(offre, "")` si elle ouvre une adhesion, sinon `(None, motif)`.

    DEUX MOTIFS DISTINCTS, et ce n'est pas de la coquetterie : « l'offre
    n'existe pas » est une anomalie a corriger, « la case n'est pas cochee »
    est le cas NORMAL de la quasi-totalite des achats. Les confondre rendrait
    le premier introuvable dans les journaux, noye sous le second.

    `creates_membership is True` — comparaison stricte, jamais `truthy` : une
    chaine « false » venue d'un import maladroit ne doit pas ouvrir une
    adhesion d'un an.

    Offre ILLISIBLE (panne de lecture) -> `offre_introuvable`, donc AUCUNE
    adhesion. Fail closed : on ne cree pas un droit d'un an sur une base qui
    n'a pas repondu.
    """
    _oid = str(offre_id or "").strip()
    if not _oid:
        return None, "offre_introuvable"
    try:
        # LOT 2.1 : la projection ramene aussi de quoi RESOUDRE LE PRIX DE
        # VENTE. Surtout pas le seul `price` : l'offre « Afroboost Silent »
        # porte `price: 0.0` en base et se vend pourtant 15 CHF aujourd'hui,
        # 25 CHF une fois son compte a rebours passe (tarif progressif V223).
        # Se fier a `price` brut refuserait l'adhesion d'un client qui a paye
        # — le faux refus exactement inverse du defaut qu'on ferme ici.
        # Ces champs sont ceux, et seulement ceux, que lit `compute_active_price`.
        _o = await db["offers"].find_one(
            {"id": _oid},
            {"_id": 0, "id": 1, "name": 1, "coach_id": 1, "creates_membership": 1,
             "price": 1, "progressive_pricing": 1, "countdown_date": 1,
             "countdown_time": 1, "early_bird_days_before": 1,
             "standard_hours_before": 1, "price_early_bird": 1,
             "price_standard": 1, "price_last_minute": 1})
    except Exception as _err:
        logger.warning("%s offre %s illisible: %s", LOT2_PREFIXE, _oid[:32], _err)
        return None, "offre_introuvable"
    if not _o:
        return None, "offre_introuvable"
    if _o.get("creates_membership") is not True:
        return None, "offre_non_adherente"
    return _o, ""


def lot2_prix_de_vente(offre) -> float:
    """LOT 2.1 — Le prix REELLEMENT DEMANDE pour cette offre, aujourd'hui.

    POURQUOI PAS `offre["price"]`. Parce que ce champ n'est PAS le prix de
    vente des qu'une offre est en tarif progressif (V223) : mesure du
    20/08/2026 sur la production, l'offre « Afroboost Silent » porte
    `price: 0.0` et se vend 15 CHF (palier `standard`), 25 CHF une fois son
    compte a rebours passe. Une garde posee sur `price` brut lui refuserait
    son adhesion alors que le client a paye — le faux refus symetrique, et
    plus grave, du defaut qu'on ferme ici.

    `compute_active_price` est le SEUL endroit du depot qui sache repondre a
    la question « combien coute cette offre maintenant », et c'est un module
    PUR : aucun acces base, aucun import de `server.py`. L'importer ici ne
    cree donc aucun cycle. Import LOCAL malgre tout, par symetrie avec les
    autres emprunts de ce fichier.

    Ne leve jamais. EN CAS D'ECHEC, ON REPLIE SUR `offre["price"]`, PAS SUR 0.
    C'est un choix delibere, et la premiere version faisait l'inverse : rendre
    0.0 quand le module ne se charge pas transforme TOUTES les offres en
    gratuites d'un coup — plus destructeur que le trou qu'on ferme. Le repli
    sur le prix brut se trompe au pire sur une offre en tarif progressif
    (refus au lieu de creation), jamais dans le sens dangereux. Un prix
    illisible jusqu'au bout rend 0.0, et la refuser est correct.

    ATTENTION, ce n'est PAS un retour en arriere sur « le prix n'est pas une
    identite metier » (server.py, membership_routes.py). Cette regle-la
    interdit d'IDENTIFIER une offre par son montant (`if price == 250`), et
    elle reste entiere : rien ici ne compare a 250, ni a aucun autre palier.
    On ne pose qu'une BORNE : ce qui est donne ne peut pas ouvrir un droit
    d'un an. Identifier et borner sont deux usages differents du meme champ.
    """
    try:
        from api.pricing import compute_active_price as _prix_actif
        return float((_prix_actif(offre or {}) or {}).get("price") or 0)
    except Exception as _err:  # noqa: BLE001
        try:
            _brut = float((offre or {}).get("price") or 0)
        except (TypeError, ValueError):
            _brut = 0.0
        logger.warning("%s tarif progressif illisible (%s) — repli sur le prix "
                       "brut %s", LOT2_PREFIXE, type(_err).__name__, _brut)
        return _brut


async def lot2_adhesion_active(db, email: str, coach_id):
    """L'adhesion ACTIVE de cette personne chez ce proprietaire, ou None.

    Le statut est RECALCULE ici a partir des dates (`p1a_statut`), jamais lu
    depuis un champ : c'est la lecon V393, et c'est aussi ce qui rend cette
    lecture juste sur un document ecrit hier comme sur un document ecrit il y
    a un an.

    Le filtre de propriete est celui du module adhesions, importe et non
    recopie : si les deux divergeaient un jour, une adhesion pourrait etre
    invisible ici et visible la — donc creee en double.
    """
    _email = normaliser_email(email)
    if not _email:
        return None
    try:
        from api.routes.membership_routes import (
            p1a_filtre_proprietaire as _filtre, p1a_statut as _statut)
    except Exception as _err:
        # Fail closed : sans la regle de propriete, on ne peut pas affirmer
        # qu'il n'existe pas d'adhesion — donc on n'en cree pas.
        logger.error("%s regle de propriete indisponible: %s", LOT2_PREFIXE, _err)
        raise
    _requete = dict(_filtre(coach_id))
    _requete["email"] = _email
    try:
        _lignes = await db["memberships"].find(_requete, {"_id": 0}).to_list(50)
    except Exception as _err:
        logger.error("%s adhesions illisibles pour ce contexte: %s", LOT2_PREFIXE, _err)
        raise
    for _l in (_lignes or []):
        if _statut(_l.get("date_debut"), _l.get("date_fin")) == "active":
            return _l
    return None


async def lot2_creer_adhesion_apres_achat(db, email, offre_id, subscription_id,
                                          nom="", moteur="", montant=None,
                                          devise=None):
    """LE POINT D'ENTREE UNIQUE. Rend toujours un dict, ne leve jamais.

    Appele depuis les DEUX points d'autorite du paiement, et depuis eux seuls.
    Il n'est jamais atteint depuis un clic, un retour de navigateur ni une
    requete non authentifiee : quand il s'execute, l'argent a change de main
    et le forfait existe deja en base.

    ═══════════════════════════════════════════════════════════════════════
    L'IDEMPOTENCE, ET POURQUOI ELLE EST ATOMIQUE
    ═══════════════════════════════════════════════════════════════════════
    `_id = "adh:" + subscription_id`. Le forfait est cree UNE fois par paiement
    reussi, sur les deux chemins ; son identifiant est donc la cle naturelle de
    « cet achat-la ». L'unicite du `_id` est garantie par MongoDB lui-meme :
    un webhook rejoue trois fois leve deux fois `DuplicateKeyError`, sans
    aucune lecture prealable et sans fenetre de course.

    C'est le motif de `free_trial_claims` — le SEUL mecanisme reellement
    atomique du domaine paiement de ce depot. Tout le reste (la garde
    `session_id` du webhook client, la garde `transaction_id` du checkout) est
    un `find_one` suivi d'un `insert_one` : fiable contre un rejeu sequentiel,
    faillible en concurrence, et sans aucun index unique pour le rattraper —
    mesure du 19/08/2026 : AUCUNE collection de ce depot ne porte d'index en
    dehors de `_id_`. On ne reproduit pas ce defaut sur une brique neuve.

    ═══════════════════════════════════════════════════════════════════════
    CE QU'IL NE FAIT JAMAIS
    ═══════════════════════════════════════════════════════════════════════
    Aucune ecriture hors de `memberships`. Aucune modification d'un document
    existant — pas meme d'une adhesion : `insert_one` seulement, jamais
    `update_one`. Aucun retro-remplissage. Une erreur ici ne fait echouer NI le
    paiement, NI le forfait, NI le code d'acces : l'appelant encaisse d'abord,
    l'adhesion est un effet, pas une condition.
    """
    _resultat = {"cree": False, "motif": "", "membership": None}
    try:
        _email = normaliser_email(email)
        _sid = str(subscription_id or "").strip()
        _oid = str(offre_id or "").strip()
        if not _email or not _sid or not _oid:
            _resultat["motif"] = "donnees_incompletes"
            return _resultat

        _offre, _pourquoi_pas = await lot2_offre_adherente(db, _oid)
        if not _offre:
            # `offre_non_adherente` est LE CAS NORMAL, et de loin le plus
            # frequent : cette offre ne cree pas d'adhesion, il n'y a rien a
            # signaler. `offre_introuvable`, lui, est une anomalie — on le dit.
            if _pourquoi_pas == "offre_introuvable":
                logger.warning("%s adhesion NON creee — motif=offre_introuvable offre=%s",
                               LOT2_PREFIXE, _oid[:32])
            _resultat["motif"] = _pourquoi_pas
            return _resultat

        # ═══ LOT 2.1 — CE QUI EST DONNE N'OUVRE PAS UN DROIT D'UN AN ═══════
        #
        # Trois signaux, evalues AVANT toute autre lecture : inutile
        # d'interroger la base pour une adhesion qu'on ne creera pas.
        #
        # 1. LE PRIX DE VENTE RESOLU. C'est le fail-safe demande : meme si une
        #    offre porte deja `creates_membership: true` avec un prix a 0 —
        #    par erreur de saisie, ou parce qu'elle date d'avant cette garde —
        #    aucune adhesion ne naitra. Aucune migration, aucun nettoyage de
        #    donnees n'est necessaire : la regle vit dans le code, pas dans la
        #    base. Resolu par `lot2_prix_de_vente`, JAMAIS `offre["price"]`
        #    brut (voir la docstring : une offre a `price: 0` peut se vendre
        #    15 CHF).
        #
        # 2. LE MOTEUR. Les deux portes gratuites du depot
        #    (`POST /checkout/free` et la branche gratuite de
        #    `/checkout/create-session`) passent `payment_method="free"`. Le
        #    signal est independant du montant : il tient meme le jour ou l'un
        #    de ces chemins oublierait de transmettre `total=0`.
        #
        # 3. LE MONTANT REELLEMENT ENCAISSE, et lui seul quand il est CONNU.
        #    `montant is not None` d'abord, et ce n'est pas une precaution de
        #    style : le defaut de la signature est `None`, et `None <= 0`
        #    leverait un TypeError que le catch-all du bas transformerait en
        #    `echec_ecriture` — un faux refus maquille en panne de base.
        #    Mesure du 20/08/2026 : aucun chemin reellement paye n'arrive a
        #    zero. Cote Stripe, `montant = amount_chf or _montant_paye`
        #    (server.py:6749) ou `_montant_paye` est calcule depuis l'objet de
        #    L'EVENEMENT, sans appel reseau (server.py:6611-6615) : une panne
        #    du `Session.retrieve` laisse `amount_chf` a 0.0 et le `or`
        #    bascule sur le montant de l'evenement. Un achat a 250 CHF ne peut
        #    donc pas se presenter ici comme gratuit.
        _prix_vente = lot2_prix_de_vente(_offre)
        _moteur_gratuit = str(moteur or "").strip().lower() == "free"
        _montant_nul = montant is not None and float(montant) <= 0
        if _prix_vente <= 0 or _moteur_gratuit or _montant_nul:
            # WARNING et non INFO : contrairement a `offre_non_adherente`, ce
            # n'est PAS un cas de routine. Soit une offre est mal configuree
            # (case cochee sur une gratuite), soit un achat cense etre payant
            # n'a rien encaisse. Les deux meritent d'etre vus dans les journaux.
            _motif = "offre_gratuite" if _prix_vente <= 0 else "montant_nul"
            logger.warning(
                "%s adhesion NON creee — motif=%s offre=%s prix_vente=%s "
                "moteur=%s montant=%s",
                LOT2_PREFIXE, _motif, _oid[:32], _prix_vente,
                str(moteur or "(aucun)")[:24], montant)
            _resultat["motif"] = _motif
            return _resultat
        # ═══════════════════════════════════════════════════════════════════

        _coach = lot2_proprietaire(_offre.get("coach_id"))

        _actif = await lot2_adhesion_active(db, _email, _coach)
        if _actif:
            # DECISION DU PROPRIETAIRE : ni second document, ni prolongation.
            # L'offre d'entree est celle d'un NOUVEAU membre ; le renouvellement
            # viendra de l'offre suivante, avec sa propre regle.
            logger.info("%s adhesion NON creee — motif=deja_membre offre=%s "
                        "proprietaire=%s fin_en_cours=%s",
                        LOT2_PREFIXE, _oid[:32], _coach or "(aucun)",
                        _actif.get("date_fin"))
            _resultat["motif"] = "deja_membre"
            _resultat["membership"] = _actif
            return _resultat

        from api.routes.membership_routes import p1a_jour_suisse as _jour
        _debut = _jour()
        _fin = lot2_fin_adhesion(_debut)
        if not _fin:
            logger.error("%s date de fin incalculable depuis %r", LOT2_PREFIXE, _debut)
            _resultat["motif"] = "donnees_incompletes"
            return _resultat

        _maintenant = datetime.now(timezone.utc).isoformat()
        _doc = {
            # LE VERROU. Voir le bloc d'idempotence ci-dessus.
            "_id": LOT2_VERROU + _sid,
            "id": str(__import__("uuid").uuid4()),
            "email": _email,
            "name": str(nom or "").strip()[:120],
            "coach_id": _coach,
            "date_debut": _debut,
            "date_fin": _fin,
            "source": LOT2_SOURCE,
            # LA PREUVE D'ACHAT : le forfait ne par le meme paiement, et
            # l'offre qui l'a declenchee. On ne recopie pas le montant depuis
            # l'offre — il vient du moteur de paiement, ci-dessous.
            "subscription_id": _sid,
            "offer_id": _oid,
            "created_by": LOT2_SOURCE,
            "created_at": _maintenant,
            "updated_at": _maintenant,
        }
        # `seances=None` : une adhesion n'ouvre AUCUNE seance — c'est
        # precisement ce qui la distingue d'un forfait. Meme argument que
        # `membership_routes.creer_adhesion`.
        _doc.update(b_champs_automatiques(moteur, montant, devise, seances=None))
        # AUCUN `statut` en base : il est deduit des dates a chaque lecture.
        _doc.pop("statut", None)

        try:
            await db["memberships"].insert_one(_doc)
        except Exception as _err:
            if lot2_est_doublon(_err):
                logger.info("%s adhesion NON creee — motif=rejeu forfait=%s",
                            LOT2_PREFIXE, _sid[:32])
                _resultat["motif"] = "rejeu"
                return _resultat
            raise

        logger.info("%s adhesion CREEE %s -> %s au %s (offre=%s proprietaire=%s)",
                    LOT2_PREFIXE, _doc["id"][:8], _debut, _fin,
                    _oid[:32], _coach or "(aucun)")
        _doc.pop("_id", None)
        _resultat["cree"] = True
        _resultat["membership"] = _doc
        return _resultat

    except Exception as _err:
        # Un achat encaisse ne doit JAMAIS echouer parce que l'adhesion n'a pas
        # pu s'ecrire. On trace fort, et on rend la main.
        logger.error("%s adhesion NON creee — motif=echec_ecriture : %s",
                     LOT2_PREFIXE, _err)
        _resultat["motif"] = "echec_ecriture"
        return _resultat


# ═══════════════════════════════════════════════════════════════════════════
# LOT 3a — LE TARIF FIGE : CE QUI A ETE DEMANDE, ET POURQUOI
# ═══════════════════════════════════════════════════════════════════════════
#
# CE QUE CE BLOC NE FAIT PAS, ET C'EST L'ESSENTIEL : il ne change AUCUN prix.
# Pas un montant affiche, pas un centime debite. Il n'ajoute que des champs a
# des documents qui allaient etre ecrits de toute facon. Un client qui reserve
# avant et apres ce lot paie exactement la meme chose.
#
# LE PROBLEME QU'IL FERME. Aujourd'hui, le prix d'une seance passee n'est
# stocke nulle part : il est RECONSTITUE a chaque affichage par
# `a_finance_du_droit`, en remontant au forfait et au code. Cette
# reconstitution lit des documents qui BOUGENT — le coach change un prix, edite
# un `maxUses`, archive une offre — et l'historique change avec eux. Une
# presence de mars peut donc valoir 25 CHF aujourd'hui et 30 demain, sans que
# rien ne se soit passe en mars.
#
# LE PATRON EST CELUI DU DEPOT, PAS UN NOUVEAU. Quatre precedents disent la
# meme chose : `seances_a_l_achat` (« DENOMINATEUR FIGE »), `b_champs_depuis_code`
# (« recopie, et non recalcul »), `t1_preuve` (« fige l'etat annonce AU MOMENT
# de la reservation ») et le document d'adhesion de LOT 2. Tous suivent cinq
# regles, reprises ici sans en inventer une sixieme :
#   1. une fonction PURE, qui rend un dict PLAT (jamais imbrique) ;
#   2. appelee AVANT la premiere ecriture, fusionnee par `.update()` ;
#   3. qui rend `{}` plutot que d'inventer quand elle ne sait pas ;
#   4. dont les champs ne sont JAMAIS reecrits ensuite ;
#   5. et dont le lecteur DIT SA CONFIANCE au lieu de retomber sur le catalogue.
#
# `tarif_avantage_pct` ET `tarif_membership_id` SONT ARRIVES AVEC LOT 3b, et la
# regle d'attente qui les retenait ici reste vraie apres coup : ils ne sont
# poses QUE lorsqu'un avantage membre a reellement gagne l'arbitrage. Une cle
# absente dit « aucune evaluation d'avantage n'a eu lieu » ; une cle a `None`
# dirait « la question a ete posee et la reponse est non ». Ce n'est pas la
# meme chose, et c'est exactement la distinction que LOT 1 a deja tranchee
# pour `courseId` / `datetime`. Sur un achat plein tarif, les deux cles restent
# donc ABSENTES — jamais posees a 0.

LOT3_PREFIXE = "[LOT3a]"

# Vocabulaire FERME. Codes stables, cherchables dans les journaux
# (`grep "tarif_raison.*forfait"`), jamais traduits.
#
# LOT 3b ajoute `membre`, comme LOT 3a l'avait annonce. Il n'y figurait pas
# tant qu'aucun code ne savait reconnaitre un membre : un vocabulaire qui
# nomme ce que le programme ne sait pas produire est un mensonge en attente.
LOT3_RAISONS = (
    "public",     # plein tarif du catalogue, paye
    "promo",      # un code de reduction a reellement joue
    "membre",     # LOT 3b : l'avantage membre a gagne l'arbitrage
    "forfait",    # seance consommee sur un pack deja paye
    "essai",      # droit d'essai gratuit consomme (ESSAI-1)
    "offert",     # accorde par le coach, rien encaisse
    "inconnu",    # le montant est la, sa raison ne se prouve pas
)


def lot3_raison_du_droit(souscription, code) -> str:
    """La raison tarifaire d'une seance consommee sur un forfait.

    Aucune deduction depuis le MONTANT : 15 CHF peut etre un forfait, une
    promo ou un plein tarif. La raison se lit sur des signaux explicites, ou
    elle vaut `inconnu`. C'est la regle que le proprietaire a posee, et c'est
    aussi celle que `a_est_gratuit_prouve` applique deja (« on ne se fie ni au
    nom de l'offre ni a l'absence de montant, qui ne prouve rien »).
    """
    _sub = souscription if isinstance(souscription, dict) else {}
    _code = code if isinstance(code, dict) else {}

    # La gratuite ETABLIE d'abord — sinon un essai passerait pour un forfait a
    # 0, ce que le proprietaire a explicitement refuse.
    #
    # Interrogee sur LES DEUX documents jumeaux, et pas seulement sur le code :
    # le lot B ecrit `origine_paiement` sur la souscription ET sur le code, et
    # certains points d'ecriture n'ont que l'un des deux en main (le scan QR
    # n'a que la souscription — son cas « code promo » sort par un `return`
    # separe). Ne regarder que le code y ferait passer un essai pour un forfait.
    _gratuit = a_est_gratuit_prouve(_code) or a_est_gratuit_prouve(_sub)
    if _gratuit:
        if _sub.get("source") == "social_proof":
            return "essai"
        if _sub.get("payment_method") == "free":
            return "essai"
        if b_normaliser_origine(_sub.get("origine_paiement")) == "offert" and not _code:
            return "offert"
        # `social_proof` et `free` sont deux gratuites differentes : la
        # premiere a ete GAGNEE (partage, Instagram, motivation), la seconde
        # ACCORDEE. Les confondre effacerait le travail du participant.
        if _code.get("source") == "social_proof":
            return "essai"
        if _code.get("payment_method") == "free":
            return "essai"      # les deux portes gratuites brulent le droit
                                # d'essai (`_essai1_garde`) : c'en est un.
        return "offert"

    # Un forfait paye : la seance est tiree d'un pack, quel que soit son prix.
    if _sub or _code:
        return "forfait"
    return "inconnu"


def lot3_snapshot_tarifaire(tarif_applique, raison, tarif_public=None,
                            devise=None, palier=None, offre_id=None,
                            avantage_pct=None, membership_id=None) -> dict:
    """La decision tarifaire, a plat, telle qu'elle etait CE JOUR-LA.

    Rend `{}` — donc n'ecrit rien — si le montant applique est inconnu ou si
    la raison n'appartient pas au vocabulaire. Mieux vaut une reservation sans
    snapshot qu'un snapshot faux : le premier se lit « on ne sait pas », le
    second ment pour toujours.

    `tarif_public` n'est pose que s'il est REELLEMENT connu. Le reconstituer
    depuis le catalogue serait exactement ce que LOT A interdit (« AUCUNE
    LECTURE DU CATALOGUE : `offers.price` est le prix D'AUJOURD'HUI ») — et
    ce que ce lot existe pour empecher.
    """
    try:
        _applique = float(tarif_applique)
    except (TypeError, ValueError):
        return {}
    if _applique < 0:
        return {}
    _raison = str(raison or "").strip().lower()
    if _raison not in LOT3_RAISONS:
        _raison = "inconnu"

    _doc = {
        "tarif_applique": round(_applique, 2),
        "tarif_raison": _raison,
        "tarif_devise": (str(devise or "").strip().upper() or B_DEVISE_DEFAUT)[:8],
        "tarif_fige_le": datetime.now(timezone.utc).isoformat(),
    }

    # Les trois champs FACULTATIFS. Poses par `if`, jamais en litteral : une
    # cle absente dit « je ne sais pas », une cle a `None` dirait « je sais que
    # c'est vide ». Meme convention que LOT 1 pour `courseId` / `datetime`.
    if tarif_public is not None:
        try:
            _doc["tarif_public"] = round(float(tarif_public), 2)
        except (TypeError, ValueError):
            pass
    if palier:
        _doc["tarif_palier"] = str(palier).strip()[:32]
    if offre_id:
        _doc["tarif_offre_id"] = str(offre_id).strip()[:64]

    # LOT 3b — les deux cles de l'avantage membre. Memes regles que les trois
    # au-dessus : posees par `if`, jamais en litteral, jamais a 0.
    #
    # `tarif_avantage_pct` est le pourcentage REELLEMENT APPLIQUE a cet achat,
    # pas celui que porte l'offre aujourd'hui. C'est toute la raison d'etre du
    # lot : le coach peut passer de 50 % a 30 % demain, cette reservation-ci
    # gardera 50 — exactement comme `tarif_applique` garde son montant.
    if avantage_pct is not None:
        try:
            _pct = round(float(avantage_pct), 2)
        except (TypeError, ValueError):
            _pct = None
        # Un avantage hors de ]0, 100[ n'est pas un avantage : on n'ecrit rien
        # plutot que d'inscrire une valeur qui ne s'est pas appliquee.
        if _pct is not None and 0 < _pct < 100:
            _doc["tarif_avantage_pct"] = _pct
    if membership_id:
        _doc["tarif_membership_id"] = str(membership_id).strip()[:64]
    return _doc


def lot3_snapshot_du_forfait(souscription, code, reservation=None) -> dict:
    """Le snapshot d'une seance tiree d'un forfait deja paye.

    LE MONTANT VIENT DE `a_finance_du_droit`, ET DE NULLE PART AILLEURS. Cette
    fonction est deja l'autorite du depot sur « ce qu'on sait de l'argent
    derriere un droit d'acces » : elle classe sa source (`montant_source`),
    dit si elle est prouvee (`montant_prouve`), et ne divise par le nombre de
    seances QUE sur un montant prouve et un pack de plus d'une seance
    (`valeur_par_seance`). Recalculer ici en parallele creerait une seconde
    verite financiere — le defaut que le lot B a precisement supprime.

    En particulier : `total_sessions` et `remaining_sessions` ne sont jamais
    touches. Le premier est incremente par la reconduction, le second est
    modifiable a la main par les boutons +/-. Le denominateur est
    `seances_a_l_achat`, fige a l'achat (`a_seances_achetees`).
    """
    _fin = a_finance_du_droit(souscription, code, reservation)
    _raison = lot3_raison_du_droit(souscription, code)

    # Une gratuite etablie vaut 0, et on le dit. Sans cette branche, un essai
    # tomberait dans la valeur par seance et vaudrait `None` faute de montant.
    if _raison in ("essai", "offert"):
        return lot3_snapshot_tarifaire(0, _raison, devise=_fin.get("devise"))

    # Un pack : la valeur d'UNE seance, jamais le montant du pack entier.
    _valeur = _fin.get("valeur_par_seance")
    if _valeur is None and _fin.get("montant_prouve") and _fin.get("montant") is not None \
            and (_fin.get("seances_achetees") or 0) == 1:
        # Pack d'une seule seance : `a_finance_du_droit` ne divise pas (la
        # division n'apprendrait rien), mais la valeur de la seance EST le
        # montant. Ne pas le poser perdrait le cas le plus simple.
        _valeur = _fin.get("montant")
    if _valeur is None:
        # Montant non prouve, ou denominateur inconnu. On ne devine pas : pas
        # de snapshot. La lecture retombera sur `a_finance_du_droit`, comme
        # avant ce lot, et l'ecran dira « tarif historique incomplet ».
        return {}
    return lot3_snapshot_tarifaire(_valeur, _raison, devise=_fin.get("devise"))


def lot3_champs_forfait(souscription=None, code=None, reservation=None) -> dict:
    """Enveloppe qui NE LEVE JAMAIS, pour les points d'ecriture.

    Un snapshot est une trace, pas une condition : s'il echoue, la reservation
    doit se creer quand meme. Le lot A a pris la meme precaution sur son
    enrichissement (`/contacts/all` : « tolerant a l'echec, la liste reste
    utilisable ») et LOT 2 sur son adhesion. Un client ne perd pas sa place
    parce qu'une ligne d'historique n'a pas pu s'ecrire.
    """
    try:
        return lot3_snapshot_du_forfait(souscription, code, reservation)
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s snapshot ignore (%s)", LOT3_PREFIXE, type(_err).__name__)
        return {}


def lot3_champs_achat(tarif_applique, raison, tarif_public=None, devise=None,
                      palier=None, offre_id=None, avantage_pct=None,
                      membership_id=None) -> dict:
    """Meme enveloppe, pour un achat : le montant est connu, il vient d'etre paye."""
    try:
        return lot3_snapshot_tarifaire(tarif_applique, raison,
                                       tarif_public=tarif_public, devise=devise,
                                       palier=palier, offre_id=offre_id,
                                       avantage_pct=avantage_pct,
                                       membership_id=membership_id)
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s snapshot ignore (%s)", LOT3_PREFIXE, type(_err).__name__)
        return {}


# =============================================================================
# LOT 3b — L'AVANTAGE MEMBRE
# =============================================================================
#
# CE QUE FAIT CE LOT, EN UNE PHRASE : un membre dont l'adhesion couvre LA DATE
# DE LA SEANCE paie le pourcentage que le coach a pose sur CETTE offre-la.
#
# CINQ REGLES, reprises de LOT 3a sans en inventer une sixieme :
#   1. les fonctions de decision sont PURES et rendent un dict PLAT ;
#   2. la lecture d'adhesion NE LEVE JAMAIS — un tarif qui plante vaut
#      moins qu'un plein tarif ;
#   3. quand la preuve manque, on rend le PLEIN TARIF, jamais un rabais ;
#   4. le pourcentage applique est FIGE dans la reservation, jamais relu ;
#   5. le vocabulaire reste ferme (`LOT3_RAISONS`).
#
# CE QUE CE LOT NE FAIT PAS, ET C'EST VOLONTAIRE :
#   * il n'ECRIT JAMAIS dans `memberships`. Ni creation, ni prolongation, ni
#     correction. LOT 2 / LOT 2.1 restent seuls maitres de l'adhesion.
#   * il ne touche pas a `compute_active_price`. Ce module PUR nourrit
#     `lot2_prix_de_vente`, qui BORNE la creation d'adhesion (LOT 2.1) : y
#     injecter un rabais membre ferait passer des offres sous la borne et
#     supprimerait des adhesions en silence. C'est le pire endroit du depot.
#   * il ne touche pas a `_essai1b_prix_unitaire`, qui decide GRATUIT vs
#     PAYANT : un total tombe a 0 y bascule dans la branche gratuite, brule
#     le droit d'essai et fait refuser l'adhesion par LOT 2.1.

LOT3B_PREFIXE = "[LOT3b]"

# Le champ porte par l'offre. Nomme en anglais comme ses deux voisins
# (`creates_membership`, `first_purchase_eligible`), pour rester coherent avec
# le reste du modele `Offer`.
LOT3B_CHAMP_AVANTAGE = "member_discount_pct"

# GARDE C1 — les seuls types de remise COMPARABLES a un avantage membre.
#
# `"100%"` en est EXCLU, et ce n'est pas un oubli : dans cette base, un code
# `type: "100%"` n'est presque jamais une promo. C'est le code d'acces AFR-
# d'un forfait DEJA PAYE (`maxUses` y porte le nombre de seances). Le compter
# comme une promo ferait ecrire `tarif_raison: "promo"` sur une seance de
# pack — le mensonge permanent que LOT 3a existe pour empecher.
LOT3B_PROMOS_COMPARABLES = ("%", "CHF")


def lot3b_avantage_de_l_offre(offre) -> float:
    """Le pourcentage d'avantage membre de cette offre, ou 0.0.

    Rend 0.0 — donc « aucun avantage » — dans TOUS les cas douteux. Une offre
    qui n'a jamais ete configuree n'a pas de champ : elle vaut 0, sans
    migration et sans backfill. C'est la convention `filmed` (ESSAI-5a-1) et
    `creates_membership` (LOT 2) : absent vaut NON.
    """
    _o = offre if isinstance(offre, dict) else {}
    if not _o:
        return 0.0

    # REGLE BLOQUANTE — ON N'ACHETE PAS SON ADHESION AU TARIF MEMBRE.
    #
    # PULSE 250 et le renouvellement portent `creates_membership: True`. Leur
    # accorder un avantage serait un cercle vicieux (il faut etre membre pour
    # payer moins cher ce qui vous rend membre), et surtout : un prix reduit
    # peut passer sous la borne de LOT 2.1 et faire DISPARAITRE la creation
    # d'adhesion. Le proprietaire a pose cette regle comme bloquante.
    if _o.get("creates_membership") is True:
        return 0.0

    # Hors perimetre V1 : la boutique physique. TVA, frais de port et
    # variantes composent le prix ailleurs que dans `price` — un pourcentage
    # pose ici ne s'appliquerait pas a ce que le client paie vraiment.
    if _o.get("isProduct") is True or _o.get("isPhysicalProduct") is True:
        return 0.0

    try:
        _pct = float(_o.get(LOT3B_CHAMP_AVANTAGE) or 0)
    except (TypeError, ValueError):
        return 0.0

    # GARDE C2 — bornes STRICTES. 0 exclu (rien a faire), 100 exclu (un total
    # a 0 basculerait l'achat dans la branche gratuite : code offert, droit
    # d'essai brule, adhesion refusee par LOT 2.1). Une valeur negative ou
    # aberrante vaut « pas d'avantage », jamais une majoration.
    if not (0 < _pct < 100):
        return 0.0
    return round(_pct, 2)


async def lot3b_adhesions(db, email, coach_id) -> list:
    """Les adhesions de cette personne chez ce proprietaire. NE LEVE JAMAIS.

    UNE SEULE REQUETE, volontairement separee du jugement de date : un panier
    de cinq seances demande cinq verdicts, pas cinq allers-retours en base.
    C'est la regle du depot sur les gros groupes (« batch `$in`, jamais des
    `find_one` en boucle »), appliquee ici a l'echelle d'un panier.
    """
    _email = normaliser_email(email)
    if not _email:
        return []
    try:
        from api.routes.membership_routes import p1a_filtre_proprietaire as _filtre
    except Exception as _err:  # noqa: BLE001
        logger.error("%s regle de propriete indisponible (%s) — plein tarif",
                     LOT3B_PREFIXE, type(_err).__name__)
        return []

    # La REGLE SYMETRIQUE de `2c8a831`, importee et jamais recopiee : un
    # proprietaire reel ne voit que ses adhesions, un contexte sans
    # proprietaire ne voit que les adhesions sans proprietaire. C'est ce qui
    # empeche le coach A d'appliquer l'adhesion ouverte chez le coach B.
    _requete = dict(_filtre(coach_id))
    _requete["email"] = _email
    try:
        return await db["memberships"].find(_requete, {"_id": 0}).to_list(50) or []
    except Exception as _err:  # noqa: BLE001
        logger.error("%s adhesions illisibles (%s) — plein tarif",
                     LOT3B_PREFIXE, type(_err).__name__)
        return []


def lot3b_couverture(adhesions, occurrence_iso):
    """L'adhesion qui couvre CETTE date-la, ou None. Fonction PURE.

    LA DATE EST UN JOUR CALENDAIRE SUISSE. `p1a_statut` accepte deja un
    horodatage complet — `p1a_date_iso` tronque a `[:10]`. On tronque quand
    meme explicitement : compter sur l'effet de bord d'une autre fonction est
    la facon dont les fuseaux finissent par se decaler d'un jour.

    Bornes INCLUSES aux deux extremites (`debut <= jour <= fin`), parce que
    c'est ce que `p1a_statut` garantit depuis P1-bis-a et qu'un membre dont
    l'adhesion s'acheve le jour du cours est encore membre ce jour-la.
    """
    _jour = str(occurrence_iso or "").strip()[:10]
    if len(_jour) != 10:
        return None
    try:
        from api.routes.membership_routes import p1a_statut as _statut
    except Exception as _err:  # noqa: BLE001
        logger.error("%s statut d'adhesion indisponible (%s) — plein tarif",
                     LOT3B_PREFIXE, type(_err).__name__)
        return None
    for _l in (adhesions or []):
        if not isinstance(_l, dict):
            continue
        if _statut(_l.get("date_debut"), _l.get("date_fin"), aujourdhui=_jour) == "active":
            return _l
    return None


async def lot3b_adhesion_a_la_date(db, email, coach_id, occurrence_iso):
    """L'adhesion qui couvre CETTE date-la, ou None. NE LEVE JAMAIS.

    POURQUOI PAS `lot2_adhesion_active`. Cette voisine repond a « cette
    personne est-elle membre AUJOURD'HUI » et LEVE en cas de panne (fail
    closed volontaire : mieux vaut refuser une adhesion que d'en creer une
    fausse). Les deux comportements sont faux ici. Une seance du 10/01/2027
    doit etre jugee au 10/01/2027, et une base momentanement illisible doit
    donner le PLEIN TARIF, pas une erreur 500 au moment de payer.

    LA DATE EST UN JOUR CALENDAIRE SUISSE. `p1a_statut` accepte deja un
    horodatage complet — `p1a_date_iso` tronque a `[:10]`. On tronque quand
    meme explicitement : compter sur l'effet de bord d'une autre fonction est
    la facon dont les fuseaux finissent par se decaler d'un jour.
    """
    return lot3b_couverture(await lot3b_adhesions(db, email, coach_id),
                            occurrence_iso)


async def lot3b_occurrences_prouvees(db, course_id, dates) -> list:
    """Les dates qui correspondent REELLEMENT a une occurrence de ce cours.

    LE NAVIGATEUR PROPOSE, LE SERVEUR DISPOSE. Sans cette revalidation, il
    suffirait d'envoyer une date situee a l'interieur de son adhesion pour
    obtenir le tarif membre sur une seance qui n'a pas lieu ce jour-la.

    Reutilise les garanties de LOT 1, sans les reecrire :
      * `lot1_occurrence_iso` normalise en naif local Europe/Zurich et REFUSE
        une date seule ou une valeur illisible ;
      * `_a1_a_lieu_aujourdhui` tranche entre cours ponctuel (`date`,
        prioritaire) et cours recurrent (`weekday`, convention JS Dim=0).

    Rend une liste — possiblement vide. Une liste vide vaut « aucune date
    prouvee », donc plein tarif : c'est le sens sur lequel il faut se tromper.
    """
    _cid = str(course_id or "").strip()
    _brutes = [d for d in (dates or []) if str(d or "").strip()]
    if not _cid or not _brutes:
        return []
    try:
        from api.routes.reservation_routes import (
            lot1_occurrence_iso as _iso, _a1_a_lieu_aujourdhui as _a_lieu,
            _a1_jour_js as _jour_js)
    except Exception as _err:  # noqa: BLE001
        logger.error("%s garanties LOT 1 indisponibles (%s) — aucune date prouvee",
                     LOT3B_PREFIXE, type(_err).__name__)
        return []
    try:
        _cours = await db["courses"].find_one({"id": _cid}, {"_id": 0})
    except Exception as _err:  # noqa: BLE001
        logger.error("%s cours illisible (%s) — aucune date prouvee",
                     LOT3B_PREFIXE, type(_err).__name__)
        return []
    if not _cours or _cours.get("archived") is True:
        return []

    _prouvees = []
    for _d in _brutes[:5]:  # meme plafond que `safe_quantity` (V225)
        _norm = _iso(_d)
        if not _norm:
            continue
        try:
            _dt = datetime.fromisoformat(_norm)
        except (TypeError, ValueError):
            continue
        if not _a_lieu(_cours, _norm[:10], _jour_js(_dt)):
            continue
        if _norm not in _prouvees:
            _prouvees.append(_norm)
    return _prouvees


def lot3b_arbitrer(base, total_promo, total_membre=None, pct_membre=None,
                   promo_type=None) -> dict:
    """UNE seule remise s'applique : la plus avantageuse pour le client.

    Fonction PURE — elle se teste sans base, comme `api/pricing.py`, « le seul
    [module] a porter un risque financier direct ».

    `total_promo` est le total DEJA calcule par le moteur promo existant
    (V429), passe tel quel. On ne le recalcule pas : reproduire sa formule ici
    creerait une seconde autorite sur le prix, exactement ce que V429 a
    supprime. Sans promo, l'appelant passe `total_promo == base`.

    `total_membre` est calcule par l'APPELANT, et non ici, parce que lui seul
    sait combien de dates sont REELLEMENT couvertes par l'adhesion. Un panier
    de trois seances dont une seule tombe dans la periode de validite paie
    deux pleins tarifs et un tarif membre — c'est la seule lecture honnete de
    « validite a la date de l'occurrence ». `None` = aucun avantage.

    EGALITE : le membre gagne (`<=`). C'est la regle du proprietaire, et elle
    est aussi la plus lisible pour le client — « votre avantage membre a bien
    ete applique » vaut mieux qu'un code promo qui donne le meme montant.

    Rend {"total", "raison", "avantage_pct"}. `avantage_pct` n'est renseigne
    QUE si le membre a gagne : LOT 3a ne pose jamais une cle a 0.
    """
    try:
        _base = float(base)
        _promo = float(total_promo)
    except (TypeError, ValueError):
        return {"total": None, "raison": "inconnu", "avantage_pct": None}
    _t = str(promo_type or "").strip()

    def _sans_membre():
        # GARDE C1 — un `"100%"` n'est pas une promo, c'est un forfait paye.
        if _t == "100%":
            return {"total": _promo, "raison": "forfait", "avantage_pct": None}
        if _t in LOT3B_PROMOS_COMPARABLES and _promo < _base:
            return {"total": _promo, "raison": "promo", "avantage_pct": None}
        return {"total": _promo, "raison": "public", "avantage_pct": None}

    try:
        _pct = float(pct_membre or 0)
    except (TypeError, ValueError):
        _pct = 0.0
    if total_membre is None or not (0 < _pct < 100) or _base <= 0:
        return _sans_membre()
    try:
        _membre = float(total_membre)
    except (TypeError, ValueError):
        return _sans_membre()

    # GARDE C2 — un avantage membre ne rend JAMAIS un achat gratuit. Si
    # l'arrondi au centime tombe a zero (prix public deja minuscule), on
    # renonce a l'avantage plutot que de basculer l'achat dans la branche
    # gratuite, qui brulerait le droit d'essai et ferait refuser l'adhesion.
    #
    # Meme garde contre une valeur negative ou superieure au plein tarif :
    # un avantage qui MAJORE n'est pas un avantage.
    if round(_membre * 100) <= 0 or _membre > _base:
        return _sans_membre()

    if _membre <= _promo:
        return {"total": _membre, "raison": "membre",
                "avantage_pct": round(_pct, 2)}
    return _sans_membre()


# =============================================================================
# LOT 3c-0 — LA PROPRIETE DE LA CHAINE FINANCIERE
# =============================================================================
#
# CE LOT NE CALCULE RIEN. Il ne change ni un prix, ni une presence, ni un
# snapshot tarifaire. Il repond a une seule question, partout de la meme
# facon : A QUI APPARTIENT CE DOCUMENT, et QUI a le droit de le lire.
#
# POURQUOI IL PASSE AVANT LE BILAN. Le futur partage partenaire calculera de
# l'argent. Une somme exacte dont on ne sait pas a qui elle revient ne vaut
# rien — pire, elle donne une fausse assurance. On ferme donc la chaine
# AVANT de la faire compter.
#
# CE QUE LE DEPOT AVAIT DEJA, ET QUI ETAIT LE PROBLEME : SIX regles de
# propriete qui se contredisent (`p1a_filtre_proprietaire`,
# `v20_perimetre_contacts`, le filtre local de `/contacts/all`, celui de
# `GET /reservations`, le « legacy_or » de `/dashboard/all-transactions`, et
# `conv_offres_premier_achat`). Elles ne donnent pas la meme reponse a
# « que voit le super-admin ? » ni a « qui voit les orphelins ? ».
# On n'en ajoute PAS une septieme : les deux fonctions ci-dessous sont
# IMPORTEES par leurs appelants, jamais recopiees, et un test l'exige.

LOT3C0_PREFIXE = "[LOT3c-0]"


def lot3c0_proprietaire_canonique(coach_id=None) -> str:
    """Le proprietaire a ECRIRE. Jamais `None`, jamais la chaine vide.

    DECISION DU PROPRIETAIRE : `None` cesse d'etre une facon normale de
    designer un proprietaire. `None` veut dire « on ne sait pas » ; ce lot
    veut pouvoir dire « cette donnee appartient reellement a la plateforme ».
    C'est indispensable avant l'arrivee de partenaires : le jour ou deux
    coachs se partagent une recette, un document sans proprietaire n'est pas
    une donnee neutre, c'est une donnee litigieuse.

    Ne s'applique QU'AUX NOUVELLES ECRITURES. Le stock ancien n'est pas
    touche — voir `lot3c0_perimetre` pour la facon dont il reste lisible.
    """
    _c = coach_id.strip().lower() if isinstance(coach_id, str) else ""
    return _c or DEFAULT_COACH_ID


def lot3c0_perimetre(appelant, est_admin: bool) -> dict:
    """Le filtre Mongo de LECTURE. LEVE plutot que de rendre un filtre vide.

    Trois comportements, et trois seulement :

      * PAS D'IDENTITE  -> `V20AccesRefuse`. On ne rend JAMAIS un filtre qui
        ne remonte rien : une liste vide est une AFFIRMATION (« il n'y a
        rien »), et la faire sans pouvoir la verifier est le defaut que V443 a
        deja paye une fois sur cette meme route — le coach a lu « aucune
        reservation » alors que la base en contenait 128, toutes a son nom.

      * PROPRIETAIRE / SUPER-ADMIN -> `{}`. Il voit TOUT, y compris le stock
        historique sans proprietaire. C'est la reponse a la compatibilite des
        anciennes donnees : elle est obtenue SANS BACKFILL et sans reecrire
        une seule ligne. Les documents a `coach_id` absent, `None` ou vides
        restent tels quels et restent lisibles par lui.

      * COACH PARTENAIRE -> `{"coach_id": <son email>}`, strictement. Ni les
        orphelins, ni le stock d'un autre. C'est volontairement plus etroit
        que le « legacy_or » de `/dashboard/all-transactions`, qui offre les
        orphelins a tout coach : sur une chaine d'argent, cette generosite-la
        s'appelle une fuite.

    L'identite qu'on lui passe doit venir d'un JWT SIGNE. Cette fonction ne
    verifie rien : elle ne sait pas d'ou vient l'e-mail qu'on lui donne. C'est
    a l'appelant d'exiger la preuve — d'ou `_v309_require_coach_or_admin`.
    """
    _e = appelant.strip().lower() if isinstance(appelant, str) else ""
    if not _e:
        raise V20AccesRefuse("identité requise")
    if est_admin:
        return {}
    return {"coach_id": _e}


async def lot3c0_coach_enregistre(db, email) -> bool:
    """Cet e-mail designe-t-il un coach REELLEMENT enregistre ?

    Meme regle que `_v309_is_coach_or_admin` (api/server.py) : super-admin, ou
    presence dans `coaches` ou `coach_auth`. Elle est REECRITE ici et non
    importee parce que `shared.py` est volontairement en dessous de
    `api.server` — il ne l'importe nulle part, et lui faire remonter la
    dependance creerait un cycle a l'import. C'est la seule duplication du lot,
    elle est assumee, et un test verifie que les deux versions repondent
    pareil.

    Ne leve jamais : une base illisible rend `False`, c'est-a-dire « je ne peux
    pas le prouver », jamais « c'est bon ».
    """
    _e = str(email or "").strip().lower()
    if not _e:
        return False
    if is_super_admin(_e):
        return True
    try:
        if await db["coaches"].find_one({"email": _e}, {"_id": 1}):
            return True
        if await db["coach_auth"].find_one({"email": _e}, {"_id": 1}):
            return True
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s annuaire coach illisible (%s) — non prouve",
                       LOT3C0_PREFIXE, type(_err).__name__)
    return False


async def lot3c0_proprietaire_de_la_seance(db, course_id=None, coach_id_declare=None) -> str:
    """A QUI APPARTIENT CETTE RESERVATION ? La reponse est LUE EN BASE.

    LE DEFAUT D'ORIGINE. `POST /api/reservations` resolvait le proprietaire
    ainsi : en-tete `X-User-Email`, sinon le CORPS de la requete, sinon le
    defaut. Or cette route n'a aucune authentification — et ne peut pas en
    avoir, c'est elle qui enregistre la reservation d'un VISITEUR apres son
    paiement. N'importe qui pouvait donc s'attribuer la reservation d'un autre,
    l'adresse a inscrire etant publiee sans authentification par
    `GET /api/courses`.

    L'ORDRE DE CONFIANCE, du plus sur au moins sur :

      1. LE COURS. `courseId` -> `courses.coach_id`. C'est la seule source
         AUTORITAIRE : elle est en base, le navigateur ne peut pas la
         reecrire. Un menteur qui reserve le cours de A en se declarant B est
         donc enregistre chez A — le cours tranche, pas la declaration.

      2. LE COACH DECLARE, MAIS SEULEMENT S'IL EST VERIFIE. `coach_id` du
         corps n'est retenu QUE s'il designe un coach reellement enregistre
         (`lot3c0_coach_enregistre`). C'est la compatibilite dont les
         parcours SANS cours ont besoin — produit physique, offre libre —
         et ou le cours ne peut, par construction, rien trancher. Un
         `coach_id` invente ne passe pas : il est journalise et ecarte.

      3. LA PLATEFORME, ET SEULEMENT QUAND RIEN N'A ETE DECLARE. Aucune
         designation de cours, aucune designation de coach : la reservation
         a bien ete prise sur la vitrine principale, elle appartient
         reellement a la plateforme.

    CE QUI A DISPARU, ET POURQUOI. La branche « offre » a ete RETIREE. Elle ne
    pouvait pas s'executer : `offerId` n'est pas un champ de `ReservationBase`,
    Pydantic l'ecarte en silence, et le seul appelant qui en envoie un
    (`ChatWidget`) y met en realite un identifiant de COURS. Une regle
    documentee « cours -> offre -> defaut » alors que le maillon du milieu est
    inatteignable est une regle qui ment ; on decrit desormais ce qui tourne.

    « INCONNU » N'EST JAMAIS « LA PLATEFORME », ET N'EST JAMAIS SILENCIEUX.
    Quand une designation existe mais ne se resout pas — cours introuvable,
    cours sans proprietaire, coach declare inconnu — on retombe sur la
    plateforme MAIS on le journalise en ERREUR, avec un motif stable et
    cherchable (`grep "motif=cours_sans_proprietaire"`). C'est la difference
    entre une attribution par defaut et une attribution silencieuse : la
    premiere se voit dans les journaux et se corrige, la seconde se decouvre
    six mois plus tard dans un bilan faux.

    NE LEVE JAMAIS. Une lecture d'appoint ratee ne doit pas faire echouer un
    parcours qui PAIE.
    """
    _motif = ""

    # ── 1. LE COURS — la seule source autoritaire ───────────────────────────
    _cid = str(course_id or "").strip()
    if _cid:
        try:
            _c = await db["courses"].find_one({"id": _cid}, {"_id": 0, "coach_id": 1})
            if _c is None:
                _motif = "cours_introuvable"
            elif str(_c.get("coach_id") or "").strip():
                return lot3c0_proprietaire_canonique(_c.get("coach_id"))
            else:
                # Le cours existe mais n'a pas de proprietaire (stock ancien,
                # ou cours cree sans en-tete d'identite). On NE consulte PAS la
                # declaration du navigateur ici : ce serait rouvrir le vol,
                # puisqu'un cours orphelin est designable par n'importe qui.
                _motif = "cours_sans_proprietaire"
        except Exception as _err:  # noqa: BLE001
            _motif = "cours_illisible_%s" % type(_err).__name__

    # ── 2. LE COACH DECLARE, VERIFIE EN BASE ────────────────────────────────
    # Uniquement quand le cours n'a rien tranche. Si le cours a designe un
    # proprietaire, on est deja sorti ; s'il a ete designe mais reste muet, on
    # ne laisse pas la declaration prendre sa place (voir ci-dessus).
    if not _motif:
        _declare = str(coach_id_declare or "").strip().lower()
        if _declare:
            if await lot3c0_coach_enregistre(db, _declare):
                return lot3c0_proprietaire_canonique(_declare)
            _motif = "coach_declare_inconnu"

    # ── 3. LA PLATEFORME ────────────────────────────────────────────────────
    if _motif:
        # Une designation existait et ne s'est pas resolue : ce n'est PAS un
        # cas normal, et cela ne doit pas passer inapercu.
        logger.error("%s proprietaire NON PROUVE — motif=%s courseId=%r coach_declare=%r "
                     "-> repli plateforme", LOT3C0_PREFIXE, _motif, _cid,
                     str(coach_id_declare or "")[:120])
    return lot3c0_proprietaire_canonique(None)
