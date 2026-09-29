"""
MT-0 — PORTEFEUILLE DE CONTACTS D'UN COACH (multi-coach, 29/09/2026).

Une seule réponse, pour tout le serveur, à la question « ce contact appartient-il
au coach X ? ». Les routes Contacts ET le moteur de campagnes (destinataires
« tous », `targetIds`, segments, groupes) s'appuient sur ces fonctions : deux
règles différentes finiraient par diverger.

RÈGLE :
- super-admin (identité issue d'un JWT SIGNÉ, jamais d'un en-tête) -> portée globale ;
- coach -> uniquement ce qu'une relation SERVEUR rattache à lui :
  * `chat_participants` dont `coach_id` == son e-mail ;
  * `users` globaux SEULEMENT si une relation est prouvée (voir `emails_relies`) ;
  * `chat_sessions` / groupes dont `coach_id` == son e-mail.
- aucune identité -> refus (jamais un dictionnaire « vide = tout »).

FAIL-CLOSED : un document sans propriétaire n'appartient à aucun coach ordinaire ;
seul le super-admin le voit. On n'invente de propriétaire à personne.

Aucune dépendance FastAPI : testable hors ligne. Les routes convertissent
`PerimetreRefuse` en 403.
"""
import re
from typing import Optional

from api.routes.shared import is_super_admin


class PerimetreRefuse(Exception):
    """Aucune identité exploitable : l'appelant doit répondre 403."""


def normaliser_email(e) -> str:
    return (e or "").strip().lower() if isinstance(e, str) else ""


def est_global(coach_email: str) -> bool:
    """Portée plateforme : réservée aux super-admins (identité déjà prouvée par JWT)."""
    _e = normaliser_email(coach_email)
    if not _e:
        raise PerimetreRefuse("identité requise")
    return is_super_admin(_e)


def filtre_proprietaire(coach_email: str) -> dict:
    """`{}` pour un super-admin, `{"coach_id": email}` pour un coach ; lève sinon."""
    _e = normaliser_email(coach_email)
    if est_global(_e):
        return {}
    return {"coach_id": _e}


# ---------------------------------------------------------------------------
# MT-2 : LES PREUVES DE RELATION SERVEUR (un `user` global n'a pas de coach).
#
# Un document `users` est créé par l'inscription publique (POST /users) SANS
# propriétaire. L'exposer à un coach (nom, e-mail, WhatsApp via /contacts/all
# et GET /users/{id}) exige une PREUVE FORTE : un fait né d'une action de la
# PERSONNE ELLE-MÊME, que le coach ne peut PAS fabriquer seul.
#
# MT-2b (audit AGENT 5) — chaque source a été passée au crible « le coach
# peut-il créer ce document tout seul, avec l'adresse de son choix ? » :
#
#   source              fabricable par le coach ?                 retenue
#   chat_participants   OUI (POST /chat/participants, import CSV,  NON
#                       synchro Google : adresse saisie par lui)
#   discount_codes      OUI (POST /discount-codes, assignedEmail   NON
#                       saisi par le coach)
#   reservations        OUI (POST /reservations est PUBLIC : n'importe qui
#                       réserve le cours du coach au nom de n'importe quelle
#                       adresse ; le cours tranche le coach_id)       NON
#   subscriber_infos    OUI (PUT /subscriber-info/{code} : porteur du jeton
#                       abonné du code depuis MT-6 — le coach connaît ses codes
#                       manuels ET leur assignedEmail, il peut l'obtenir) NON
#   subscriptions       OUI pour source admin_manual / manual_sync /
#                       social_proof (création à la main) ;
#                       NON pour `source: "stripe_auto"` (webhook Stripe
#                       après PAIEMENT de la personne) ou un `stripe_customer_id`
#                       (client Stripe réel). `source` et `stripe_customer_id`
#                       ne sont PAS modifiables par PUT /subscriptions (liste
#                       blanche promo_routes).                      OUI (payé)
#   memberships         OUI pour `saisie_manuelle` (POST coach) ;
#                       NON pour `source: "achat"` (LOT 2 : adhésion créée
#                       par le paiement). `source` n'est pas modifiable.  OUI (achat)
#
# La FICHE CRM du coach (`chat_participants`, coach_id = lui) reste visible
# pour lui : c'est la sienne, il l'a saisie. Ce qui change : elle n'ouvre plus
# le `user` GLOBAL homonyme ni ses coordonnées.
#
# Écartés aussi : `leads` (POST public), `payment_transactions` (aucun
# propriétaire), tout document sans `coach_id` (fail-closed).
#
# Forme : (collection, champ e-mail, filtre supplémentaire de preuve forte).
# ---------------------------------------------------------------------------
MT2_PREUVES_RELATION = (
    ("subscriptions", "email",
     {"$or": [{"source": "stripe_auto"},
              {"stripe_customer_id": {"$nin": [None, ""]}}]}),
    ("memberships", "email", {"source": "achat"}),
)


def _mt2_emails_du_champ(valeur) -> list:
    """`assignedEmail` peut être une chaîne OU une liste selon l'âge du code."""
    if isinstance(valeur, (list, tuple)):
        return [normaliser_email(v) for v in valeur if normaliser_email(v)]
    _m = normaliser_email(valeur)
    return [_m] if _m else []


async def emails_relies(db, coach_email: str) -> set:
    """E-mails (normalisés) que le SERVEUR rattache au coach — preuve de relation.

    MT-2b : union des preuves FORTES de `MT2_PREUVES_RELATION` (faits nés d'un
    paiement de la personne), chacune filtrée sur `coach_id == <e-mail du
    coach>` (égalité stricte, jamais une regex). Une
    collection illisible prive de SA preuve sans faire tomber les autres : on
    rend moins, jamais plus.
    """
    _e = normaliser_email(coach_email)
    if not _e:
        raise PerimetreRefuse("identité requise")
    _out = set()
    for _coll, _champ, _preuve in MT2_PREUVES_RELATION:
        try:
            async for _d in db[_coll].find({"coach_id": _e, **_preuve}, {"_id": 0, _champ: 1}):
                _out.update(_mt2_emails_du_champ(_d.get(_champ)))
        except Exception:  # noqa: BLE001 — fail-closed : la preuve manque, rien de plus
            continue
    return _out


async def email_relie(db, coach_email: str, email: str) -> bool:
    """MT-2 : version ciblée de `emails_relies` pour UNE adresse (une lecture
    `find_one` par preuve au lieu de charger tout le portefeuille)."""
    _e = normaliser_email(coach_email)
    if not _e:
        raise PerimetreRefuse("identité requise")
    _m = normaliser_email(email)
    if not _m:
        return False
    for _coll, _champ, _preuve in MT2_PREUVES_RELATION:
        try:
            if await db[_coll].find_one({"coach_id": _e, _champ: _m, **_preuve}, {"_id": 1}):
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


async def contact_appartient(db, coach_email: str, collection: str, doc_id: str) -> bool:
    """Le document `doc_id` de `collection` fait-il partie du portefeuille du coach ?

    Super-admin : vrai si le document existe. Coach : relation serveur exigée.
    Collections gérées : chat_participants, users, chat_sessions.
    """
    if not isinstance(doc_id, str) or not doc_id or "$" in doc_id or len(doc_id) > 128:
        return False
    _e = normaliser_email(coach_email)
    _global = est_global(_e)
    if collection in ("chat_participants", "chat_sessions"):
        _f = {"id": doc_id}
        if not _global:
            _f["coach_id"] = _e
        return bool(await db[collection].find_one(_f, {"_id": 1}))
    if collection == "users":
        _u = await db.users.find_one({"id": doc_id}, {"_id": 0, "email": 1, "coach_id": 1})
        if not _u:
            return False
        if _global:
            return True
        if normaliser_email(_u.get("coach_id")) == _e:
            return True
        return await email_relie(db, _e, _u.get("email"))
    return False


async def filtrer_ids(db, coach_email: str, collection: str, ids) -> list:
    """Ne garde que les ids appartenant au coach (ordre conservé, doublons retirés).

    MT-2 : même réponse que `contact_appartient` appelé id par id, mais en
    lectures GROUPÉES (`$in`) — jamais une requête par identifiant (règle du
    dépôt : les gros groupes saturaient le serveur)."""
    _vus, _cands = set(), []
    for _i in ids or []:
        if (isinstance(_i, str) and _i and _i not in _vus and "$" not in _i
                and len(_i) <= 128):
            _vus.add(_i)
            _cands.append(_i)
    if not _cands:
        return []
    _e = normaliser_email(coach_email)
    _global = est_global(_e)
    if collection in ("chat_participants", "chat_sessions"):
        _f = {"id": {"$in": _cands}}
        if not _global:
            _f["coach_id"] = _e
        _ok = {d.get("id") async for d in db[collection].find(_f, {"_id": 0, "id": 1})}
        return [i for i in _cands if i in _ok]
    if collection == "users":
        _docs = [d async for d in db.users.find({"id": {"$in": _cands}},
                                               {"_id": 0, "id": 1, "email": 1, "coach_id": 1})]
        if _global:
            _ok = {d.get("id") for d in _docs}
        else:
            _rel = await emails_relies(db, _e)
            _ok = {d.get("id") for d in _docs
                   if normaliser_email(d.get("coach_id")) == _e
                   or normaliser_email(d.get("email")) in _rel}
        return [i for i in _cands if i in _ok]
    return []


async def filtre_users_du_coach(db, coach_email: str) -> Optional[dict]:
    """Filtre Mongo des `users` visibles par le coach : `{}` (super-admin) ou
    `{"$or": [coach_id == e-mail, email ∈ relation prouvée]}`."""
    _e = normaliser_email(coach_email)
    if est_global(_e):
        return {}
    _emails = sorted(await emails_relies(db, _e))
    return {"$or": [{"coach_id": _e}, {"email": {"$in": _emails}}]}


# ===========================================================================
# MT-2 — DÉDOUBLONNAGE À LA PORTÉE DU COACH, SANS AUCUNE REGEX.
#
# AVANT : POST /chat/participants, /contacts/bulk-import et la synchro Google
# cherchaient un doublon dans TOUTE la collection, avec le numéro saisi injecté
# tel quel dans `$regex` (`whatsapp: "."` renvoyait une fiche au hasard — d'un
# autre coach — et écrasait son nom ; `+` levait une 500).
#
# APRÈS :
#   1. la recherche est BORNÉE à la portée d'écriture du coach (`portee_ecriture`) ;
#   2. l'e-mail se compare comme un LITTÉRAL (re.escape + ancrage, casse ignorée) ;
#   3. le téléphone se compare sur sa forme CANONIQUE (`normaliser_telephone`,
#      qui réutilise la convention du dépôt `essai6_normaliser_tel` /
#      `normaliser_numero` : chiffres seuls, « 00 » puis « 0 » national -> 41).
#      Plancher de 8 chiffres : « . », « + », « 12 » ne sont PAS des identités.
# Aucune entrée utilisateur n'entre jamais dans une regex Mongo.
# ===========================================================================

# Les valeurs de `coach_id` qui désignent la PLATEFORME (le super-admin) : le
# défaut actuel, l'ancienne sentinelle V244 et le stock sans propriétaire.
MT2_COACH_IDS_PLATEFORME = ("bassi_default", "", None)


def normaliser_telephone(valeur) -> str:
    """Forme canonique comparable d'un numéro, ou '' si inexploitable."""
    try:
        from api.routes.shared import essai6_normaliser_tel
        return essai6_normaliser_tel(valeur) if isinstance(valeur, str) else ""
    except Exception:  # noqa: BLE001
        return ""


def variantes_telephone(valeur) -> list:
    """Formes EXACTES sous lesquelles un même numéro est stocké en base
    (saisie brute sans espaces, +41…, 0041…, 41…, 0…). Sert aux requêtes
    `$in` à égalité stricte — jamais une regex."""
    _canon = normaliser_telephone(valeur)
    if not _canon:
        return []
    _v = {_canon, "+" + _canon, "00" + _canon}
    if _canon.startswith("41"):
        _v.add("0" + _canon[2:])
    _brut = "".join(ch for ch in str(valeur) if ch not in " -.()\t")
    if _brut:
        _v.add(_brut)
    return sorted(_v)


def portee_ecriture(coach_email: str):
    """(coach_id à écrire, filtre de la portée de dédoublonnage).

    Coach    -> (son e-mail, {"coach_id": son e-mail}).
    Super-admin -> (DEFAULT_COACH_ID, fiches de la PLATEFORME : défaut, ancienne
    sentinelle, stock sans propriétaire). Jamais la collection entière : le
    super-admin ne doit pas « retrouver » la fiche d'un partenaire en créant la
    sienne.
    """
    _e = normaliser_email(coach_email)
    if not est_global(_e):
        return _e, {"coach_id": _e}
    from api.routes.shared import DEFAULT_COACH_ID
    return DEFAULT_COACH_ID, {"$or": [
        {"coach_id": {"$in": [DEFAULT_COACH_ID] + list(MT2_COACH_IDS_PLATEFORME)}},
        {"coach_id": {"$exists": False}},
    ]}


async def index_doublons(db, filtre_portee: dict) -> dict:
    """Index e-mail / téléphone canonique des fiches `chat_participants` de la
    portée. UNE lecture projetée, puis comparaisons en mémoire."""
    _idx = {}
    async for _d in db.chat_participants.find(
            filtre_portee, {"_id": 0, "id": 1, "name": 1, "email": 1,
                            "whatsapp": 1, "phone": 1, "coach_id": 1}):
        indexer_fiche(_idx, _d)
    return _idx


def indexer_fiche(index: dict, doc: dict) -> None:
    _m = normaliser_email(doc.get("email"))
    if _m:
        index.setdefault("m:" + _m, doc)
    for _champ in ("whatsapp", "phone"):
        _t = normaliser_telephone(doc.get(_champ))
        if _t:
            index.setdefault("t:" + _t, doc)


def chercher_doublon(index: dict, email=None, telephone=None):
    _m = normaliser_email(email)
    if _m and ("m:" + _m) in index:
        return index["m:" + _m]
    _t = normaliser_telephone(telephone)
    if _t and ("t:" + _t) in index:
        return index["t:" + _t]
    return None


async def doublon_dans_portee(db, filtre_portee: dict, email=None, telephone=None):
    """Recherche CIBLÉE d'un doublon (une seule fiche) : égalité stricte sur
    l'e-mail normalisé (littéral échappé, insensible à la casse) et sur les variantes exactes du numéro, dans la portée.
    Aucune regex. Renvoie le document (sans `_id`) ou None."""
    _ou = []
    _m = normaliser_email(email)
    if _m:
        # Casse historique : des fiches anciennes portent l'e-mail tel que saisi.
        # `re.escape` + ancrage : l'adresse est un LITTÉRAL, jamais un motif.
        _ou.append({"email": {"$regex": "^" + re.escape(_m) + "$", "$options": "i"}})
    _vars = variantes_telephone(telephone)
    if _vars:
        _ou.append({"whatsapp": {"$in": _vars}})
        _ou.append({"phone": {"$in": _vars}})
    if not _ou:
        return None
    return await db.chat_participants.find_one(
        {"$and": [filtre_portee, {"$or": _ou}]}, {"_id": 0})
