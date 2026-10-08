# -*- coding: utf-8 -*-
# V534: Centre Parrainage unique — routes du Pass Duo (`/api/referral/*`).
"""V534 — Pass Duo : un abonné invite un ami ; l'ami obtient son premier cours
gratuit (moteur d'essai EXISTANT), et les deux places sont réservées sur la
MÊME occurrence. Ce module ne contient AUCUNE règle métier : elles vivent dans
`referral_engine.py` (pur) et dans les moteurs déjà en place que l'on appelle
sans les modifier (ESSAI-4, ESSAI-1, `_process_successful_payment`, LOT 1,
SEANCES, LOT B2, T1, M2-A, notifications de réservation).

DRAPEAU. `feature_flags.parrainage_duo_enabled` (défaut False, repli ouvert
= False si la base est muette, pattern `v344_jwt_strict_actif`). OFF : `/config`
répond `{enabled:false, courses:[]}` et TOUT le reste répond 404
`parrainage_duo_desactive` — rien n'existe pour le monde.

IDENTITÉ DU PARRAIN. Jamais `X-User-Email`, jamais un code dans le corps :
un jeton d'espace signé (`x-espace-token`, session vivante en base) ou, à
défaut, le jeton abonné V296 (`X-Subscriber-Token`). Sinon 403.

CE QUI N'EST PAS ICI : le scanner (CAS A-E) — les billets Duo sont des
réservations ordinaires, il les valide déjà ; `_process_successful_payment` —
appelé, jamais modifié ; les push existants — appelés, jamais modifiés.

V534b — L'OFFRE DU PASS EST CHOISIE PAR LE PARTICIPANT. Le coach définit par
cours le catalogue autorisé (`courses.duo_offer_ids`, 0 CHF seulement), le
participant choisit (`POST /pass` exige `offer_id`) et peut changer tant que
l'avantage n'est pas consommé (`PATCH /pass/{id|token}/offer`, contrôle de
version optimiste, 409 `conflit_version`). L'octroi du join utilise l'offre
DU PASS ; plus aucun réglage `parrainage_duo_offer_id`. Un changement après
join sans présence neutralise l'ancien octroi puis re-octroie par le MÊME
chemin que le join (`_octroyer_essai` -> `_reserver_ami`).
"""
import asyncio
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from api.routes import referral_engine as E
from api.routes import referral_campaigns_engine as IC   # PAR-1 : règles pures des campagnes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/referral", tags=["referral"])

db = None

PREFIXE = "[V534 DUO]"
FLAG_ID = "feature_flags"
FLAG_CHAMP = "parrainage_duo_enabled"
# V534b : `FLAG_OFFRE` (`parrainage_duo_offer_id`) n'existe plus — l'offre est
# celle du pass, choisie par le participant dans le catalogue du cours.
COLL_PASSES = "referral_passes"
COLL_INVITATIONS = "referral_invitations"
COLL_SESSIONS = "subscriber_sessions"      # = `_B3S1_COLL_SESSIONS` (server.py)
COLL_REGLAGES_PARTAGE = "referral_share_settings"   # V551 : {_id: clé coach, "" = plateforme}
DETAIL_DESACTIVE = "parrainage_duo_desactive"
SOURCE = "pass_duo"                          # `reservations.source` des billets Duo
SOURCE_ATTRIBUTION = "parrainage"            # M2-A (`M2A_SOURCES`)
JOURS_AVANT = 30
OCCURRENCES_MAX = 6
LISTE_MAX = 50
DEBIT_PREFIXE_PASS = "duo_pass:"
DEBIT_PREFIXE_JOIN = "duo_join:"
DEBIT_PREFIXE_OFFRE = "duo_offer:"            # V534b : PATCH public (avant join)
DEBIT_PREFIXE_CHAINE = "duo_chain:"           # V556 : création de l'invitation enfant
DEBIT_PREFIXE_CHAINE_ACTION = "duo_chain_a:"  # V556 : modification / partage (quota séparé)
DEBIT_PREFIXE_CHAINE_LECTURE = "duo_chain_l:" # V556 : contrôle d'aperçu (lecture)
FLAG_CHAINE = "parrainage_chaine_enabled"    # V556 : `true` = actif ; absent / false = parcours V2
# PAR-1 : une campagne `trial` devient la RACINE d'une chaîne V556 (lu `is True`,
# absent / false / base illisible = liens de campagne d'avant, aucune entrée).
FLAG_CHAINE_CAMPAGNE = "invitation_chaine_campagne_enabled"
DEBIT_PREFIXE_CAMPAGNE = "duo_campaign:"      # PAR-1 : POST /campaign/{token}/entry
CAMPAGNE_ENTREES_OUVERTES_MAX = 500           # PAR-1 : P0 ouverts sans invité par campagne
CAMPAGNE_ENTREES_FENETRE_H = 24               # PAR-1 (audit P1-A) : seuls les P0 RÉCENTS comptent au plafond
CAMPAGNE_ENTREES_PAR_IP_HEURE = 5             # PAR-1 (audit P1-A) : P0 créés / heure / IP / campagne
CAMPAGNE_ESSAIS_MAX = 30                      # PAR-1 (audit P1-B) : essais octroyés par campagne (une séance)
_DEBIT_ENTREE_CAMPAGNE = {}                   # PAR-1 : {"<campagne>|<ip>": [instants monotones]}
PREFIXE_PARRAIN_CAMPAGNE = "campagne:"        # PAR-1 : `sponsor.email_norm` d'un P0 (jamais une adresse)


def init_db(database):
    global db
    db = database


# ═══════════════════════════════════════════════════════════════════════════
# Outils
# ═══════════════════════════════════════════════════════════════════════════
def _maintenant():
    return datetime.now(timezone.utc)


def _iso(dt=None):
    return (dt or _maintenant()).isoformat()


def _frontend_url() -> str:
    return (os.environ.get("FRONTEND_URL") or "https://afroboost.com").rstrip("/")


def _est_doublon(err) -> bool:
    """E11000 de MongoDB (index unique), quelle que soit la classe levée."""
    _t = str(err).lower()
    return "duplicate" in _t or "e11000" in _t


async def parrainage_duo_actif(database) -> bool:
    """Le drapeau. Repli OUVERT = False : une base muette ne fait pas apparaître
    une fonctionnalité que le propriétaire n'a pas allumée."""
    if database is None:
        return False
    try:
        _flags = await database[FLAG_ID].find_one({"id": FLAG_ID}, {"_id": 0}) or {}
        return bool(_flags.get(FLAG_CHAMP, False))
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s drapeau %s illisible (%s) — considéré OFF", PREFIXE, FLAG_CHAMP,
                       type(_err).__name__)
        return False


async def _chaine_active() -> bool:
    """V556 — la règle « invite avant de t'inscrire ». Décision de Bassi
    (28/09) : ACTIVE SEULEMENT si `parrainage_chaine_enabled` vaut `true` en
    base. Absent, `false` ou base illisible = parcours V2 (formulaire direct).
    On déploie donc le code éteint, on vérifie, puis on allume — et on
    éteint sans rollback en remettant `false`."""
    try:
        _f = await db[FLAG_ID].find_one({"id": FLAG_ID}, {"_id": 0}) or {}
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s drapeau %s illisible (%s) — règle considérée OFF", PREFIXE, FLAG_CHAINE,
                       type(_err).__name__)
        return False
    return _f.get(FLAG_CHAINE) is True


async def invitation_chaine_campagne_active(database=None) -> bool:
    """PAR-1 — le lien d'une campagne `trial` entre-t-il dans la chaîne ?
    Oui seulement si les TROIS drapeaux le disent, en UNE lecture :
    `parrainage_duo_enabled` (le parrainage existe), `parrainage_chaine_enabled`
    ET `invitation_chaine_campagne_enabled` (`is True`). Base illisible = NON :
    les liens déjà partagés gardent leur cible d'avant."""
    _base = database if database is not None else db
    if _base is None:
        return False
    try:
        _f = await _base[FLAG_ID].find_one({"id": FLAG_ID}, {"_id": 0}) or {}
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s drapeau %s illisible (%s) — considéré OFF", PREFIXE, FLAG_CHAINE_CAMPAGNE,
                       type(_err).__name__)
        return False
    return bool(_f.get(FLAG_CHAMP, False)) and _f.get(FLAG_CHAINE) is True \
        and _f.get(FLAG_CHAINE_CAMPAGNE) is True


async def _exiger_actif() -> None:
    if not await parrainage_duo_actif(db):
        raise HTTPException(status_code=404, detail=DETAIL_DESACTIVE)


def _ip(request) -> str:
    # PAR-1 (audit P1-A, À TRAITER DANS UN LOT INFRA SÉPARÉ — comportement NON
    # modifié ici) : `CF-Connecting-IP` puis `X-Forwarded-For` sont crus SANS
    # vérifier que la requête vient bien de Cloudflare. L'origine Hetzner
    # (178.105.201.62, servie en HTTP par Traefik) répond aussi en direct : un
    # client qui l'appelle en forçant `Host: afroboost.com` choisit librement ces
    # en-têtes, donc SA clé de débit — chaque débit par IP de ce module
    # (`_exiger_debit` : duo_pass, duo_join, duo_offer, duo_chain*, duo_campaign ;
    # `_debit_entree_campagne`) et celui d'ESSAI-7 (checkout_routes
    # `_essai7_exiger_debit`, même lecture) sont alors contournables. Correctif
    # attendu côté infra : n'accepter l'origine que depuis les plages Cloudflare
    # (pare-feu / Traefik), ou ne lire `CF-Connecting-IP` que si `client.host`
    # appartient à ces plages.
    try:
        return (request.headers.get("CF-Connecting-IP")
                or (request.headers.get("X-Forwarded-For", "") or "").split(",")[0].strip()
                or (request.client.host if getattr(request, "client", None) else "")).strip()
    except Exception:  # noqa: BLE001
        return ""


def _debit_entree_campagne(request, campaign_id) -> bool:
    """PAR-1 (audit P1-A) — `CAMPAGNE_ENTREES_PAR_IP_HEURE` P0 créés par heure,
    par IP ET par campagne (compteur mémoire du processus, même mécanique
    qu'ESSAI-7). Faux = refus. Sans IP lisible : accepté (comme `_exiger_debit`)."""
    import time as _t
    _adresse = _ip(request)
    if not _adresse:
        return True
    _cle = "%s|%s" % (str(campaign_id or "")[:64], _adresse[:64])
    _now = _t.monotonic()
    _hist = [h for h in _DEBIT_ENTREE_CAMPAGNE.get(_cle, []) if _now - h < 3600]
    if len(_hist) >= CAMPAGNE_ENTREES_PAR_IP_HEURE:
        _DEBIT_ENTREE_CAMPAGNE[_cle] = _hist
        return False
    _hist.append(_now)
    _DEBIT_ENTREE_CAMPAGNE[_cle] = _hist
    if len(_DEBIT_ENTREE_CAMPAGNE) > 5000:          # borne mémoire
        for _k in list(_DEBIT_ENTREE_CAMPAGNE.keys())[:1000]:
            _DEBIT_ENTREE_CAMPAGNE.pop(_k, None)
    return True


def _exiger_debit(request, prefixe: str) -> None:
    """Même mécanique qu'ESSAI-7 (`_essai7_debit_ok`, compteur mémoire par IP),
    sur une clé PROPRE au parrainage : un pass créé ne consomme pas le quota
    de la porte gratuite, et inversement. Refus = 429, sans rien écrire."""
    _adresse = _ip(request)
    if not _adresse:
        return
    try:
        from api.routes.checkout_routes import _essai7_debit_ok as _ok
    except Exception:  # noqa: BLE001
        return
    if not _ok(prefixe + _adresse):
        logger.warning("%s débit dépassé (%s%s) — 429", PREFIXE, prefixe, _adresse[:24])
        raise HTTPException(status_code=429,
                            detail="Trop de demandes depuis cette connexion. Réessayez dans un moment.")


def _refus(code: int, raison: str, message: str):
    return HTTPException(status_code=code, detail=message, headers={"X-Refus-Raison": raison})


async def _corps(request) -> dict:
    try:
        _b = await request.json()
    except Exception:  # noqa: BLE001
        return {}
    return _b if isinstance(_b, dict) else {}


# ═══════════════════════════════════════════════════════════════════════════
# Identité du parrain
# ═══════════════════════════════════════════════════════════════════════════
async def _parrain_depuis_requete(request) -> dict:
    """`{code, email, coach_id, name, whatsapp}` ou 403.

    1. `x-espace-token` (jeton `subscriber_space`, B3-S1) : signature via
       `lotb3s1_lire_token`, puis session VIVANTE en base (`jti`) via
       `lotb3s1_session_utilisable` — exactement `_b3s13_porteur_autorise`.
    2. Sinon `X-Subscriber-Token` (V296) via `subscriber_from_request`.
    3. Sinon 403. Jamais `X-User-Email`, jamais un code dans le corps.
    """
    from api.routes.shared import (lotb3s1_lire_token, lotb3s1_session_utilisable,
                                   subscriber_from_request, lire_abonnement_par_code)
    _code, _email, _coach = "", "", ""
    try:
        _entete = (request.headers.get("x-espace-token", "") or "").strip()
    except Exception:  # noqa: BLE001
        _entete = ""
    _charge = lotb3s1_lire_token(_entete) if _entete else None
    if _charge:
        try:
            _session = await db[COLL_SESSIONS].find_one({"jti": _charge.get("jti")}, {"_id": 0})
        except Exception as _err:  # noqa: BLE001
            logger.warning("%s session illisible (%s)", PREFIXE, type(_err).__name__)
            _session = None
        _ok, _motif = lotb3s1_session_utilisable(_session, _charge)
        if not _ok:
            logger.info("%s jeton d'espace refusé (%s)", PREFIXE, _motif)
            raise HTTPException(status_code=403, detail="Session abonné invalide — reconnecte-toi.")
        _code = str(_charge.get("code") or "").strip().upper()
        _email = E.normaliser_email(_charge.get("email"))
        _coach = str(_charge.get("coach_id") or "").strip().lower()
    else:
        _sub = subscriber_from_request(request)
        if not _sub or not _sub.get("code"):
            raise HTTPException(status_code=403, detail="Identité abonné requise.")
        _code = _sub["code"]
        _email = E.normaliser_email(_sub.get("email"))
    if not _code:
        raise HTTPException(status_code=403, detail="Identité abonné requise.")

    _forfait = await lire_abonnement_par_code(db, _code, _email or None) or {}
    _fiche = {}
    if not _forfait or not _forfait.get("name"):
        try:
            _fiche = await db["discount_codes"].find_one(
                {"code": {"$regex": "^%s$" % re.escape(_code), "$options": "i"}},
                {"_id": 0, "name": 1, "assignedEmail": 1, "coach_id": 1}) or {}
        except Exception:  # noqa: BLE001
            _fiche = {}
    _email = _email or E.normaliser_email(_forfait.get("email")) or E.normaliser_email(_fiche.get("assignedEmail"))
    _nom = str(_forfait.get("name") or _fiche.get("name") or "").strip()
    if not _nom and _email:
        try:
            _u = await db["users"].find_one({"email": _email}, {"_id": 0, "name": 1}) or {}
            _nom = str(_u.get("name") or "").strip()
        except Exception:  # noqa: BLE001
            pass
    return {
        "code": _code,
        "email": _email,
        "coach_id": _coach or str(_forfait.get("coach_id") or _fiche.get("coach_id") or "").strip().lower(),
        "name": _nom,
        "whatsapp": str(_forfait.get("whatsapp") or "").strip(),
        "subscription": _forfait,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Cours éligibles et occurrences
# ═══════════════════════════════════════════════════════════════════════════
def _occurrences(course) -> list:
    """Les prochaines occurrences (≤ 6, 30 jours) — `_v184_next_occurrences`
    de server.py, normalisées par `lot1_occurrence_iso`. Import différé :
    server.py importe ce module, l'inverse ne peut se faire qu'à l'appel."""
    from api.server import _v184_next_occurrences
    from api.routes.reservation_routes import lot1_occurrence_iso
    _sortie = []
    for _o in (_v184_next_occurrences(course, days_ahead=JOURS_AVANT) or []):
        _iso_occ = lot1_occurrence_iso((_o or {}).get("datetime"))
        if _iso_occ and _iso_occ not in _sortie:
            _sortie.append(_iso_occ)
        if len(_sortie) >= OCCURRENCES_MAX:
            break
    return _sortie


async def _cours_eligibles() -> list:
    """visible + non archivé + `duo_enabled: true` (absent vaut NON)."""
    try:
        return await db["courses"].find(
            {"duo_enabled": True, "visible": {"$ne": False}, "archived": {"$ne": True}},
            {"_id": 0, "id": 1, "name": 1, "weekday": 1, "date": 1, "time": 1,
             "locationName": 1, "location": 1, "mapsUrl": 1, "coach_id": 1,
             "duo_offer_ids": 1, "duo_default_offer_id": 1},
        ).to_list(LISTE_MAX)
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s cours illisibles (%s)", PREFIXE, type(_err).__name__)
        return []


def _dto_config_cours(course, offres_dto, default_offer_id) -> dict:
    return {
        "id": course.get("id"),
        "name": course.get("name") or "",
        "weekday": course.get("weekday"),
        "date": course.get("date"),
        "time": course.get("time") or "",
        "locationName": course.get("locationName") or course.get("location") or "",
        "mapsUrl": course.get("mapsUrl") or "",
        "occurrences": _occurrences(course),
        # V534b : le catalogue autorisé (OffreDTO[]) et la « Recommandée ».
        "offers": list(offres_dto or []),
        "default_offer_id": default_offer_id,
    }


# ═══════════════════════════════════════════════════════════════════════════
# V534b — Le catalogue d'offres d'un cours et l'offre autorisée
# ═══════════════════════════════════════════════════════════════════════════
def _filtre_proprietaire(coach_id) -> dict:
    """LA définition de la propriété du dépôt (`p1a_filtre_proprietaire`) :
    propriétaire -> ses offres ; sans propriétaire -> les offres sans
    propriétaire. Jamais un mélange."""
    from api.routes.membership_routes import p1a_filtre_proprietaire
    return dict(p1a_filtre_proprietaire(coach_id if isinstance(coach_id, str) else None))


async def _offres_du_cours(course) -> tuple:
    """(offres valides RELUES en base dans l'ordre de `duo_offer_ids`,
    default_offer_id|None). Valide = autorisée ∩ visible ∩ non archivée ∩
    prix 0 ∩ du propriétaire du cours. Un cours sans `duo_offer_ids` rend
    ([], None) — absent vaut aucune offre."""
    _ids = [str(i).strip() for i in ((course or {}).get("duo_offer_ids") or []) if str(i or "").strip()]
    if not _ids:
        return [], None
    _q = _filtre_proprietaire((course or {}).get("coach_id"))
    _q["id"] = {"$in": _ids[:LISTE_MAX]}
    try:
        _rows = await db["offers"].find(_q, {"_id": 0}).to_list(LISTE_MAX)
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s offres illisibles (%s)", PREFIXE, type(_err).__name__)
        return [], None
    return E.catalogue_du_cours(course, _rows)


async def _catalogue_dto(course) -> list:
    """Les OffreDTO du catalogue COURANT d'un cours (`recommended` posé)."""
    _valides, _defaut = await _offres_du_cours(course)
    return E.dtos_offres(_valides, _defaut)


async def _catalogue_par_cours(course_id, cache) -> list:
    """Même chose, par identifiant de cours, avec mémo par requête (le /me
    d'un parrain porte plusieurs passes du même cours : une seule lecture)."""
    _cid = str(course_id or "").strip()
    if _cid in cache:
        return cache[_cid]
    _c = None
    if _cid:
        try:
            _c = await db["courses"].find_one({"id": _cid}, {"_id": 0})
        except Exception:  # noqa: BLE001
            _c = None
    cache[_cid] = (await _catalogue_dto(_c)) if _c else []
    return cache[_cid]


async def _offre_autorisee(course, offer_id) -> dict:
    """L'offre RELUE en base si elle est autorisée pour ce cours, sinon 400
    `X-Refus-Raison` ∈ offre_requise | offre_non_autorisee | offre_inactive |
    offre_payante | offre_autre_coach. Le backend valide TOUJOURS : jamais un
    `offer_id` du front accepté tel quel."""
    _oid = str(offer_id or "").strip()
    if not _oid:
        raise _refus(400, E.REFUS_OFFRE_REQUISE, "Choisis l'offre du Pass Duo.")
    _ids = [str(i).strip() for i in ((course or {}).get("duo_offer_ids") or []) if str(i or "").strip()]
    if _oid not in _ids:
        raise _refus(400, E.REFUS_OFFRE_NON_AUTORISEE, "Cette offre n'est pas proposée pour ce cours.")
    _o = await db["offers"].find_one({"id": _oid}, {"_id": 0})
    if not _o:
        raise _refus(400, E.REFUS_OFFRE_INACTIVE, "Cette offre n'est plus disponible.")
    _ok, _raison = E.offre_eligible(_o, (course or {}).get("coach_id"))
    if not _ok:
        raise _refus(400, _raison, {
            E.REFUS_OFFRE_INACTIVE: "Cette offre n'est plus disponible.",
            E.REFUS_OFFRE_PAYANTE: "Pass Duo V1 : offres offertes uniquement (0 CHF).",
            E.REFUS_OFFRE_AUTRE_COACH: "Cette offre n'appartient pas au coach de ce cours.",
        }.get(_raison, "Offre refusée."))
    # La propriété, relue avec le filtre du dépôt (et pas seulement en mémoire).
    _q = _filtre_proprietaire((course or {}).get("coach_id"))
    _q["id"] = _oid
    if not await db["offers"].find_one(_q, {"_id": 0, "id": 1}):
        raise _refus(400, E.REFUS_OFFRE_AUTRE_COACH, "Cette offre n'appartient pas au coach de ce cours.")
    return _o


# ─── PAR-1 : la porte UNIQUE de l'offre d'un pass ──────────────────────────
# Un pass sans `origin.campaign_id` (tous les pass d'avant PAR-1) passe par
# `_offre_autorisee` EXACTEMENT comme avant. Un pass d'une campagne (P0 et ses
# descendants) : l'offre est CELLE de la campagne, revalidée à chaque octroi —
# campagne `active` de type `trial`, même `offer_id`, 0 CHF certain
# (`offre_gratuite`), offre publiée, du propriétaire de la campagne. Archiver
# la campagne ferme donc P0 ET toute sa descendance (coupe-circuit).
async def _campagne_par_id(campaign_id):
    _cid = str(campaign_id or "").strip()
    if not _cid or len(_cid) > 64:
        return None
    try:
        return await db["referral_campaigns"].find_one({"id": _cid}, {"_id": 0})
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s campagne illisible (%s)", PREFIXE, type(_err).__name__)
        return None


async def _offre_de_campagne(campagne, offer_id=None):
    """L'offre RELUE si la campagne peut encore l'octroyer, sinon None."""
    _c = campagne if isinstance(campagne, dict) else None
    if not _c or _c.get("status") != "active" or _c.get("type") != "trial":
        return None
    _oid = str(_c.get("offer_id") or "").strip()
    if not _oid or (offer_id is not None and str(offer_id or "").strip() != _oid):
        return None
    try:
        _o = await db["offers"].find_one({"id": _oid}, {"_id": 0})
    except Exception:  # noqa: BLE001
        _o = None
    if not _o or _o.get("visible") is False or _o.get("archived") is True or _o.get("active") is False:
        return None
    if not IC.offre_gratuite(_o):
        return None
    _cle = str(_c.get("coach_id") or "").strip().lower()
    if _cle and E._proprietaire(_o.get("coach_id")) != _cle:
        return None
    return _o


async def _offre_du_pass(pass_doc, course) -> dict:
    """L'offre que le join octroie. Sans campagne : `_offre_autorisee` (inchangé)."""
    _cid = E.campagne_du_pass(pass_doc)
    if not _cid:
        return await _offre_autorisee(course, (pass_doc or {}).get("offer_id"))
    _o = await _offre_de_campagne(await _campagne_par_id(_cid), (pass_doc or {}).get("offer_id"))
    if not _o:
        raise HTTPException(status_code=410, detail="Cette invitation n'est plus valable.")
    return _o


async def _catalogue_du_pass(pass_doc, cache) -> list:
    """Le catalogue montré avec un pass. Sans campagne : celui du cours
    (inchangé) ; d'une campagne : sa seule offre (« Recommandée »)."""
    if not E.campagne_du_pass(pass_doc):
        return await _catalogue_par_cours((pass_doc or {}).get("course_id"), cache)
    _oid = str((pass_doc or {}).get("offer_id") or "").strip()
    _k = "offre-campagne:" + _oid
    if _k not in cache:
        _o = None
        if _oid:
            try:
                _o = await db["offers"].find_one({"id": _oid}, {"_id": 0})
            except Exception:  # noqa: BLE001
                _o = None
        cache[_k] = [E.dto_offre(_o, True)] if _o else []
    return cache[_k]


async def _proprietaires_campagne(pass_doc) -> list:
    """Les adresses du propriétaire de la campagne racine : la clé du coach, ou
    les super-admins pour une campagne plateforme (clé "")."""
    _c = await _campagne_par_id(E.campagne_du_pass(pass_doc))
    if not _c:
        return []
    _cle = str(_c.get("coach_id") or "").strip().lower()
    if _cle:
        return [_cle]
    try:
        from api.routes.shared import SUPER_ADMIN_EMAILS as _SA
    except Exception:  # noqa: BLE001
        try:
            from api.server import SUPER_ADMIN_EMAILS as _SA
        except Exception:  # noqa: BLE001
            _SA = []
    return [E.normaliser_email(x) for x in (_SA or [])]


def _essais_max(campagne) -> int:
    """PAR-1 (audit P1-B) — plafond d'essais d'une campagne : `essais_max` de la
    campagne s'il est un entier > 0 (réglage futur), sinon `CAMPAGNE_ESSAIS_MAX`."""
    try:
        _n = int((campagne or {}).get("essais_max"))
        if _n > 0:
            return _n
    except (TypeError, ValueError):
        pass
    return CAMPAGNE_ESSAIS_MAX


async def _campagne_complete_essais(campagne) -> bool:
    """Les pass de cette campagne ayant un invité inscrit atteignent-ils le plafond ?"""
    _cid = str((campagne or {}).get("id") or "")
    if not _cid:
        return False
    _n = await db[COLL_PASSES].count_documents(
        {"origin.campaign_id": _cid, "invitee.email_norm": {"$type": "string"}})
    return _n >= _essais_max(campagne)


async def _cours_eligible(course_id: str):
    _cid = str(course_id or "").strip()
    if not _cid:
        return None
    _c = await db["courses"].find_one({"id": _cid}, {"_id": 0})
    if not _c or _c.get("duo_enabled") is not True or _c.get("visible") is False \
            or _c.get("archived") is True:
        return None
    return _c


# ═══════════════════════════════════════════════════════════════════════════
# Lecture / écriture d'un pass
# ═══════════════════════════════════════════════════════════════════════════
async def _reservations_du_pass(pass_doc) -> list:
    _liens = (pass_doc or {}).get("reservations") or {}
    _ids = [i for i in (_liens.get("sponsor_id"), _liens.get("invitee_id")) if i]
    if not _ids:
        return []
    try:
        return await db["reservations"].find({"id": {"$in": _ids}}, {"_id": 0}).to_list(4)
    except Exception:  # noqa: BLE001
        return []


async def _evenement(pass_id: str, type_: str, detail=None, maj=None) -> None:
    """Journalise un événement sur le pass (+ `$set` facultatif).
    V534b : chaque écriture incrémente `version` (contrôle optimiste)."""
    _e = {"at": _iso(), "type": type_, "detail": detail}
    _upd = {"$push": {"events": _e}, "$set": dict(maj or {}, updated_at=_iso()),
            "$inc": {"version": 1}}
    try:
        await db[COLL_PASSES].update_one({"id": pass_id}, _upd)
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s événement %s non journalisé (%s)", PREFIXE, type_, type(_err).__name__)


async def _statut_reel(pass_doc, now=None, reservations=None):
    """Le statut dérivé (`used` / `expired`) — persisté quand il change."""
    _now = now or _maintenant()
    if reservations is None and (pass_doc or {}).get("status") == E.UNLOCKED:
        reservations = await _reservations_du_pass(pass_doc)
    _s, _change = E.statut_derive(pass_doc, _now, reservations)
    if _change:
        await _evenement(pass_doc["id"], _s, None, {"status": _s})
        pass_doc["status"] = _s
    return _s


async def _dto(pass_doc, deja_existant=None, now=None, cache_offres=None):
    _resas = await _reservations_du_pass(pass_doc)
    _s = await _statut_reel(pass_doc, now, _resas)
    _offres = await _catalogue_du_pass(pass_doc, cache_offres if cache_offres is not None else {})
    return E.dto_pass(pass_doc, _s, E.tickets_du_pass(pass_doc, _resas, _frontend_url()),
                      _frontend_url(), deja_existant, offers=_offres)


async def _pass_du_parrain(pass_id: str, parrain: dict):
    _p = await db[COLL_PASSES].find_one({"id": str(pass_id or "").strip()}, {"_id": 0})
    if not _p or E.normaliser_email((_p.get("sponsor") or {}).get("email_norm")) != parrain["email"]:
        raise HTTPException(status_code=404, detail="Pass introuvable")
    return _p


# ═══════════════════════════════════════════════════════════════════════════
# Réservation d'un billet Duo — LE CHEMIN NORMAL, avec trois champs de plus
# ═══════════════════════════════════════════════════════════════════════════
async def _reserver_seance_duo(code, email, name, whatsapp, course, occurrence,
                               pass_doc, role, accepte, session=None) -> dict:
    """Crée (ou rattache) LA réservation de `role` sur l'occurrence du pass.

    Mêmes briques que `reserve_course_from_space` (server.py), dans le même
    ordre : LOT 1 (`lot1_verifier_seance`), T1 (`t1_preuve`), V393
    (`forfait_utilisable`), LOT B2 (`lotb2_refus_canonique`), anti-double
    réservation, SEANCES (`seances_consommer`, clé = id de la réservation),
    décrément conditionnel de `subscriptions`, puis le document — de la même
    forme, avec `source: "pass_duo"`, `pass_id`, `pass_role` en plus.

    Une réservation DÉJÀ existante de la même personne sur la même occurrence
    est RATTACHÉE (aucun second débit) : c'est le cas du parrain qui avait déjà
    réservé sa place avant de créer son pass.
    """
    from api.routes.reservation_routes import lot1_verifier_seance
    from api.server import t1_preuve
    from api.routes.shared import (lire_abonnement_par_code, forfait_utilisable,
                                   lotb2_refus_canonique, seances_consommer,
                                   v531_refus_plafond, m2a_resoudre)
    _cid = str(course.get("id") or "")
    _email = E.normaliser_email(email)
    _l1 = await lot1_verifier_seance(
        {"courseId": _cid, "datetime": occurrence, "courseTime": course.get("time")},
        source=SOURCE)
    _occ = _l1["datetime"]
    _t1 = await t1_preuve(accepte, _cid, "")

    _sub = await lire_abonnement_par_code(db, code, _email or None)
    if not _sub:
        raise HTTPException(status_code=404, detail="Abonnement introuvable")
    # V531 — le CANONIQUE gouverne l'acceptation, comme sur l'espace abonné :
    # quand `lota_droits_du_code` est sans ambiguïté, ce sont ses valeurs que
    # `forfait_utilisable` juge, jamais le compteur dérivé de `subscriptions`.
    _ref = dict(_sub)
    try:
        from api.routes.shared import (v531_actif, v531_valeurs_canoniques, lota_droits_du_code)
        if v531_actif():
            _canon = v531_valeurs_canoniques(await lota_droits_du_code(db, code))
            if _canon:
                _ref["remaining_sessions"] = _canon["remaining_sessions"]
                if _canon.get("expires_at"):
                    _ref["expires_at"] = _canon["expires_at"]
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s canonique illisible pour %s (%s)", PREFIXE, str(code)[:8], type(_err).__name__)
    _ok, _pourquoi = forfait_utilisable(_ref, 1)
    if not _ok:
        raise HTTPException(status_code=400, detail=_pourquoi)
    _b2, _b2_msg = await lotb2_refus_canonique(db, code, 1)
    if _b2:
        raise HTTPException(status_code=400, detail=_b2_msg)

    # V534b : la réservation remplacée par un changement d'offre est SUPPRIMÉE
    # (convention du dépôt, cf. `_annuler_reservation_ami`) ; le filtre sur
    # `status` reste une ceinture si un jour un statut d'annulation apparaît.
    _existante = await db["reservations"].find_one(
        {"userEmail": {"$regex": "^%s$" % re.escape(_email), "$options": "i"},
         "courseId": _cid, "datetime": _occ, "status": {"$ne": "cancelled"}}, {"_id": 0})
    if _existante:
        _autre = _existante.get("pass_id")
        if _autre and _autre != pass_doc.get("id"):
            raise HTTPException(status_code=409, detail="Cette séance est déjà liée à un autre Pass Duo.")
        if not _autre:
            await db["reservations"].update_one(
                {"id": _existante.get("id")},
                {"$set": {"pass_id": pass_doc.get("id"), "pass_role": role}})
            _existante["pass_id"], _existante["pass_role"] = pass_doc.get("id"), role
        _existante["_rattachee"] = True     # jamais persisté : dit « aucune notification neuve »
        logger.info("%s réservation existante rattachée (%s, %s)", PREFIXE, role,
                    str(_existante.get("reservationCode") or "")[:12])
        return _existante

    _rid = str(uuid.uuid4())
    _debit = await seances_consommer(db, code, 1, reservation_id=_rid, source=SOURCE,
                                     session=session)
    _ferme, _msg = v531_refus_plafond(_debit)
    if _ferme:
        raise HTTPException(status_code=409, detail=_msg)

    _now = _iso()
    if _sub.get("id"):
        try:
            _kw = {"session": session} if session is not None else {}
            await db["subscriptions"].update_one(
                {"id": _sub.get("id"), "remaining_sessions": {"$gte": 1}},
                {"$inc": {"remaining_sessions": -1, "used_sessions": 1},
                 "$set": {"updated_at": _now}}, **_kw)
        except Exception as _err:  # noqa: BLE001
            logger.warning("%s compteur subscriptions non décrémenté (%s)", PREFIXE, type(_err).__name__)

    _coach = (_sub.get("coach_id") or course.get("coach_id") or pass_doc.get("coach_id") or "")
    _doc = {
        "id": _rid,
        "reservationCode": "AF%s" % uuid.uuid4().hex[:8].upper(),
        "userName": str(name or "").strip() or "Abonné",
        "userEmail": _email,
        "userWhatsapp": str(whatsapp or ""),
        "courseId": _cid,
        "courseName": course.get("name"),
        "courseTime": course.get("time"),
        "datetime": _occ,
        "offerId": "",
        "offerName": _sub.get("offer_name") or "Abonnement",
        "price": 0.0,
        "quantity": 1,
        "totalPrice": 0.0,
        "discountCode": str(code or "").strip().upper(),
        "promoCode": str(code or "").strip().upper(),
        "source": SOURCE,
        "member_slug": None,
        "type": "ticket",
        "validated": False,
        "validatedAt": None,
        "createdAt": _now,
        "coach_id": _coach,
        "guests": [],
        "guest_headphones": [],
        # V534 : les deux champs additifs du contrat §3.
        "pass_id": pass_doc.get("id"),
        "pass_role": role,
    }
    if _sub.get("id"):
        _doc["subscriptionId"] = _sub.get("id")
    _doc.update(_t1 or {})
    try:
        _m2a = await m2a_resoudre(db, _sub.get("attribution") or _attribution_parrainage(pass_doc), _email)
        if _m2a:
            _doc["attribution"] = _m2a
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s attribution non recopiée (%s)", PREFIXE, type(_err).__name__)
    if session is not None:
        await db["reservations"].insert_one(_doc, session=session)
    else:
        await db["reservations"].insert_one(_doc)
    _doc.pop("_id", None)
    logger.info("%s réservation %s créée (%s)", PREFIXE, _doc["reservationCode"], role)
    return _doc


def _attribution_parrainage(pass_doc, bloc_client=None) -> dict:
    """Le bloc M2-A d'un filleul : `first.source = "parrainage"`."""
    from api.routes.shared import m2a_touche, m2a_bloc_propre
    _touche = m2a_touche(SOURCE_ATTRIBUTION, "duo", "pass_duo",
                         str((pass_doc or {}).get("course_id") or "")[:32], "", "/duo")
    _propre = m2a_bloc_propre(bloc_client) or {}
    return {"first": _touche, "last": _propre.get("last") or _touche}


async def _notifier_reservation(reservation, subscription) -> None:
    """Les notifications EXISTANTES d'une réservation (client, coach in-app,
    push coach, e-mail coach) — même helper que l'espace abonné. Détaché."""
    try:
        from api.routes.shared import notifier_reservation_creee
        from api.routes.reservation_routes import (_send_reservation_email,
                                                   _send_coach_reservation_email)
        from api.server import send_push_by_email

        async def _email_client(_r):
            return bool(await _send_reservation_email(
                _r.get("userEmail"), _r.get("userName"), _r, subscription,
                user_lang=None, user_whatsapp=(subscription or {}).get("whatsapp") or ""))

        asyncio.create_task(notifier_reservation_creee(
            db, reservation, envoyer_email_client=_email_client,
            envoyer_push_coach=send_push_by_email,
            envoyer_email_coach=_send_coach_reservation_email))
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s notifications de réservation non lancées (%s)", PREFIXE, type(_err).__name__)


async def _push_parrain(email, titre, corps, data) -> None:
    if "@" not in str(email or ""):          # V556 : parrain de chaîne pas encore inscrit
        return
    try:
        from api.server import send_push_by_email
        await send_push_by_email(email, titre, corps, data)
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s push parrain non envoyé (%s)", PREFIXE, type(_err).__name__)


async def _email_parrain_debloque(pass_doc) -> bool:
    """E-mail Resend au parrain à l'unlock. Échappement N2 : TOUT ce qui est
    inséré dans le HTML passe par `html.escape`. Non bloquant."""
    from html import escape as _esc
    _key = os.environ.get("RESEND_API_KEY", "")
    if not _key or "@" not in str(((pass_doc or {}).get("sponsor") or {}).get("email_norm") or ""):
        return False
    try:
        import resend
    except ImportError:
        return False
    try:
        from api.routes.shared import get_primary_color
        _sp = pass_doc.get("sponsor") or {}
        _inv = pass_doc.get("invitee") or {}
        _c = E.dto_course(pass_doc)
        _couleur = await get_primary_color(db, pass_doc.get("coach_id") or "")
        _prenom = _esc(E.prenom(_sp.get("name")) or "toi", quote=True)
        _ami = _esc(E.prenom(_inv.get("name")) or "ton ami", quote=True)
        _cours = _esc(str(_c.get("name") or "ton cours")[:120], quote=True)
        _quand = _esc(E.occurrence_lisible(pass_doc.get("occurrence")), quote=True)
        _lieu = _esc(str(_c.get("locationName") or "")[:160], quote=True)
        _lien = _esc(_frontend_url() + "/parrainage", quote=True)
        _html = (
            '<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; '
            'background: #1a1a2e; color: white; padding: 30px; border-radius: 12px;">'
            '<h1 style="color: %s; text-align: center;">Pass Duo débloqué</h1>'
            '<p>Bonjour <strong>%s</strong>,</p>'
            '<p><strong>%s</strong> vient de s&#39;inscrire grâce à ton invitation : vos deux places '
            'pour <strong>%s</strong> le <strong>%s</strong>%s sont réservées.</p>'
            '<div style="text-align: center; margin: 24px 0;">'
            '<a href="%s" style="display: inline-block; background: %s; color: white; padding: 14px 32px; '
            'text-decoration: none; border-radius: 12px; font-weight: bold;">Voir mes billets</a></div>'
            '<p style="text-align: center; color: rgba(255,255,255,0.4); font-size: 12px;">'
            'Afroboost — Centre Parrainage</p></div>'
            % (_esc(_couleur, quote=True), _prenom, _ami, _cours, _quand,
               (" (%s)" % _lieu) if _lieu else "", _lien, _esc(_couleur, quote=True))
        )
        resend.api_key = _key
        await asyncio.to_thread(resend.Emails.send, {
            "from": "Afroboost <notifications@afroboost.com>",
            "to": [_sp.get("email_norm")],
            "subject": "Pass Duo débloqué : vos deux places sont réservées",
            "html": _html,
        })
        return True
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s e-mail parrain non envoyé (%s)", PREFIXE, type(_err).__name__)
        return False


async def _tenter_reservation_parrain(pass_doc, course) -> tuple:
    """(reservation|None, blocked_reason|None) — la place du parrain, sans
    jamais fabriquer un billet ni laisser une réservation orpheline."""
    _sp = pass_doc.get("sponsor") or {}
    # V556 — CHAÎNE : le parrain d'une invitation enfant (A) a DÉJÀ sa place
    # sur cette séance — celle de filleul du pass parent. On la reprend telle
    # quelle : aucun second débit, aucune seconde réservation, et la
    # réservation reste liée au parent (jamais réécrite).
    if E.chaine_du_pass(pass_doc).get("parent_pass_id"):
        if E.parrain_en_attente(pass_doc):
            return None, E.BLOCAGE_PARRAIN_NON_INSCRIT
        _place = await _place_du_parrain_chaine(pass_doc)
        if _place:
            return _place, None
    try:
        _r = await _reserver_seance_duo(
            _sp.get("subscription_code"), _sp.get("email_norm"), _sp.get("name"),
            _sp.get("whatsapp_norm") or "", course, pass_doc.get("occurrence"), pass_doc,
            E.ROLE_SPONSOR, _sp.get("terms_accepted") is True)
        return _r, None
    except HTTPException as _e:
        _raison = (getattr(_e, "headers", None) or {}).get("X-Refus-Raison") or ""
        if _raison == "terms_not_accepted":
            return None, E.BLOCAGE_CONDITIONS
        logger.info("%s place du parrain non confirmée (%s %s)", PREFIXE, _e.status_code,
                    str(_e.detail)[:80])
        return None, E.BLOCAGE_SPONSOR_SANS_SEANCE
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s réservation parrain en erreur (%s)", PREFIXE, type(_err).__name__)
        return None, E.BLOCAGE_SPONSOR_SANS_SEANCE


async def _debloquer_ou_bloquer(pass_doc, course) -> dict:
    """Depuis `friend_registered` : tente la place du parrain. Rend le pass à jour."""
    if E.sans_place_parrain(pass_doc):
        # PAR-1 : racine de campagne — le coach n'a pas de place à réserver :
        # débloqué SANS réservation parrain, sans push ni e-mail (aucune adresse).
        # Même écriture conditionnelle que ci-dessous (`status != unlocked`).
        _now = _iso()
        _cible = E.transition(pass_doc.get("status"), E.UNLOCKED)
        await db[COLL_PASSES].update_one(
            {"id": pass_doc["id"], "status": {"$ne": E.UNLOCKED}},
            {"$set": {"status": _cible, "unlocked_at": _now, "blocked_reason": None, "updated_at": _now},
             "$push": {"events": {"at": _now, "type": "unlocked", "detail": "sans_place_parrain"}},
             "$inc": {"version": 1}})
        return await db[COLL_PASSES].find_one({"id": pass_doc["id"]}, {"_id": 0}) or pass_doc
    _r, _blocage = await _tenter_reservation_parrain(pass_doc, course)
    if _r:
        _now = _iso()
        # V556 : écriture CONDITIONNELLE (`status != unlocked`) — deux déblocages
        # simultanés (join de l'ami + liaison du parrain de chaîne) ne notifient
        # qu'une fois, et le second ne réécrit rien.
        _cible = E.transition(pass_doc.get("status"), E.UNLOCKED)
        _ecrit = await db[COLL_PASSES].update_one(
            {"id": pass_doc["id"], "status": {"$ne": E.UNLOCKED}},
            {"$set": {"status": _cible, "unlocked_at": _now, "blocked_reason": None,
                      "reservations.sponsor_id": _r.get("id"),
                      "reservations.sponsor_code": _r.get("reservationCode"), "updated_at": _now},
             "$push": {"events": {"at": _now, "type": "unlocked", "detail": None}},
             "$inc": {"version": 1}})
        pass_doc = await db[COLL_PASSES].find_one({"id": pass_doc["id"]}, {"_id": 0}) or pass_doc
        if not getattr(_ecrit, "modified_count", 1):
            return pass_doc
        _sub = (await db["subscriptions"].find_one({"id": _r.get("subscriptionId")}, {"_id": 0})
                if _r.get("subscriptionId") else None)
        if not _r.get("_rattachee"):
            await _notifier_reservation(_r, _sub)
        _sp = pass_doc.get("sponsor") or {}
        _cours = E.dto_course(pass_doc)["name"] or "ton cours"
        # V558 : séance choisie pour l'ami ≠ séance du parrain — on ne dit pas « vos deux places ».
        _texte = ("Ton ami est inscrit à la séance que tu lui as offerte (%s)." % _cours
                  if E.seance_choisie(pass_doc) else "Vos deux places pour %s sont réservées." % _cours)
        await _push_parrain(_sp.get("email_norm"), "Pass Duo débloqué" if not E.seance_choisie(pass_doc)
                            else "Invitation réussie", _texte,
                            {"type": "pass_duo_unlocked", "pass_id": pass_doc["id"], "url": "/parrainage"})
        asyncio.create_task(_email_parrain_debloque(pass_doc))
        return pass_doc
    # V556 : jamais par-dessus un `unlocked` écrit entre-temps par un autre chemin.
    _now = _iso()
    await db[COLL_PASSES].update_one(
        {"id": pass_doc["id"], "status": {"$ne": E.UNLOCKED}},
        {"$set": {"blocked_reason": _blocage, "updated_at": _now},
         "$push": {"events": {"at": _now, "type": "sponsor_blocked", "detail": _blocage}},
         "$inc": {"version": 1}})
    pass_doc["blocked_reason"] = _blocage
    return pass_doc


# ═══════════════════════════════════════════════════════════════════════════
# Transaction, octroi de l'essai (chemin UNIQUE du join et du changement d'offre)
# ═══════════════════════════════════════════════════════════════════════════
async def _avec_session(travail):
    """Transaction Mongo (LOT B3) quand le pilote la propose, repli PROPRE
    sinon : `travail(session)` avec `session=None`. Une transaction refusée
    par le serveur (pas de replica set) n'a rien écrit : on rejoue sans."""
    _client = getattr(db, "client", None)
    if _client is None or not hasattr(_client, "start_session"):
        return await travail(None)
    try:
        _cm = await _client.start_session()
    except Exception as _err:  # noqa: BLE001
        logger.info("%s pas de session Mongo (%s) — écritures directes", PREFIXE, type(_err).__name__)
        return await travail(None)
    try:
        async with _cm as _ses:
            _ses.start_transaction()
            try:
                _r = await travail(_ses)
                await _ses.commit_transaction()
                return _r
            except Exception:
                try:
                    await _ses.abort_transaction()
                except Exception:  # noqa: BLE001
                    pass
                raise
    except HTTPException:
        raise
    except Exception as _err:  # noqa: BLE001
        _t = str(_err).lower()
        if "transaction" in _t and ("not supported" in _t or "replica" in _t or "numbers" in _t):
            logger.info("%s transactions indisponibles (%s) — écritures directes", PREFIXE, type(_err).__name__)
            return await travail(None)
        raise


async def _rollback_filleul(pass_doc, email, telephone, access_code, sub_id=None,
                            motif="pass_duo_rollback", rouvrir=True) -> None:
    """La réservation de l'ami a échoué APRÈS l'octroi : on rend son droit à
    l'essai (`_essai1_liberer`), on neutralise le code et le forfait qui
    viennent de naître (marqués, jamais supprimés) et on rouvre le pass.

    V534b : réutilisé par le changement d'offre après join — `motif` =
    `pass_duo_offer_change` (marque `pass_duo_rollback_motif`), `rouvrir=False`
    (l'invité RESTE sur le pass : on remplace son avantage, pas sa place)."""
    try:
        from api.routes.checkout_routes import _essai1_liberer
        await _essai1_liberer(email, telephone=telephone)
    except Exception as _err:  # noqa: BLE001
        logger.error("%s libération de l'essai impossible (%s)", PREFIXE, type(_err).__name__)
    _marque = {"pass_duo_rollback": True, "pass_duo_rollback_at": _iso(),
               "pass_duo_rollback_motif": str(motif or "pass_duo_rollback")[:48]}
    try:
        if access_code:
            await db["discount_codes"].update_one(
                {"code": access_code},
                {"$set": dict(_marque, active=False, maxUses=0)})
            await db["subscriptions"].update_one(
                {"code": access_code},
                {"$set": dict(_marque, status="cancelled", remaining_sessions=0,
                              total_sessions=0)})
    except Exception as _err:  # noqa: BLE001
        logger.error("%s neutralisation du forfait impossible (%s)", PREFIXE, type(_err).__name__)
    if not rouvrir:
        return
    try:
        await db[COLL_PASSES].update_one(
            {"id": pass_doc["id"]},
            {"$set": {"invitee": None, "invitee_access_code": None, "updated_at": _iso()},
             "$inc": {"version": 1}})
    except Exception as _err:  # noqa: BLE001
        logger.error("%s pass non rouvert (%s)", PREFIXE, type(_err).__name__)


async def _octroyer_essai(pass_doc, offre, email, nom, tel_brut, attribution_client=None) -> tuple:
    """LE chemin d'octroi de l'avantage de l'ami — le même pour le join et pour
    un changement d'offre après join : ESSAI-1b (0 CHF confirmé par le
    catalogue) -> T1 -> ESSAI-4 (abonné actif, LIT) -> ESSAI-1 (verrou, ÉCRIT)
    -> `_process_successful_payment(free)` -> marquage pass_duo + M2-A.

    Rend `(access_code, attribution)`. Lève l'HTTPException des gardes telle
    quelle (409 `abonne_actif` / `free_trial_already_*`, 400 gratuit) ; une
    panne de l'octroi libère le verrou et lève 500. NE TOUCHE PAS au pass :
    l'appelant gère `invitee` (rouvrir ou non)."""
    from api.routes.checkout_routes import (
        _essai_porte_garde, _essai1b_exiger_gratuit, _essai1_liberer,
        _process_successful_payment, _t1_preuve_checkout, _r2b_resoudre_vendeur,
        CheckoutItem)
    _item = CheckoutItem(type="offer", id=str(offre.get("id")), name=str(offre.get("name") or "Essai"),
                         price=0.0, quantity=1)
    try:
        await _essai1b_exiger_gratuit([_item])
        _t1_champs = await _t1_preuve_checkout(True, [_item], "")
        # ESSAI-8 (V591) : LA garde commune — téléphone, ESSAI-4, déjà client
        # payant, ESSAI-1 (verrou). Même règle que /checkout/free, jamais une copie.
        await _essai_porte_garde(email, str(offre.get("id")), telephone=tel_brut)
    except HTTPException as _e:
        _raison = (getattr(_e, "headers", None) or {}).get("X-Refus-Raison") or ""
        if _raison == "active_subscription":
            raise _refus(409, E.REFUS_ABONNE_ACTIF,
                         "Tu as déjà un abonnement actif : le Pass Duo est réservé aux nouveaux.")
        raise
    # 409 `free_trial_already_used` | `free_trial_already_granted` | `already_customer`, tel quel

    _vendeur = ""
    try:
        _vendeur = await _r2b_resoudre_vendeur([_item])
    except Exception:  # noqa: BLE001
        _vendeur = ""
    _transaction_id = "duo_%s" % uuid.uuid4().hex[:12]
    try:
        _octroi = await _process_successful_payment(
            transaction_id=_transaction_id, coach_email=_vendeur, customer_name=nom,
            customer_email=email, customer_phone=tel_brut, items=[_item], total=0,
            currency="CHF", payment_method="free", discount_code=None,
            terms_fields=_t1_champs)
    except Exception as _err:  # noqa: BLE001
        await _essai1_liberer(email, telephone=tel_brut)
        logger.error("%s octroi de l'essai en erreur (%s)", PREFIXE, type(_err).__name__)
        raise HTTPException(status_code=500, detail="L'inscription a échoué, rien n'a été enregistré.")
    _access_code = str((_octroi or {}).get("access_code") or "").strip().upper()

    # Source ADDITIVE sur ce que l'octroi vient d'écrire (`source` d'origine
    # intact : ESSAI-1/ESSAI-6 le lisent), + M2-A `parrainage` sur le forfait.
    _attrib = None
    try:
        from api.routes.shared import m2a_resoudre
        _attrib = await m2a_resoudre(db, _attribution_parrainage(pass_doc, attribution_client), email)
    except Exception:  # noqa: BLE001
        _attrib = None
    try:
        _marque = {"pass_duo_id": pass_doc["id"], "pass_duo_role": E.ROLE_INVITEE,
                   "acquisition_source": SOURCE, "pass_duo_offer_id": str(offre.get("id"))}
        await db["discount_codes"].update_one({"code": _access_code}, {"$set": dict(_marque)})
        _maj_sub = dict(_marque)
        if _attrib:
            _maj_sub["attribution"] = _attrib
        await db["subscriptions"].update_one({"code": _access_code}, {"$set": _maj_sub})
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s marquage pass_duo non écrit (%s)", PREFIXE, type(_err).__name__)
    return _access_code, _attrib


async def _reserver_ami(pass_doc, course, access_code, email, nom, tel_brut, maj, push=None) -> dict:
    """La réservation de l'ami + la mise à jour du pass, dans UNE transaction
    quand le pilote la propose (`_avec_session`). `maj` = le `$set` du pass,
    `push` = le `$push` (événements, historique). Rend la réservation."""
    async def _travail(session):
        _r = await _reserver_seance_duo(access_code, email, nom, tel_brut, course,
                                        pass_doc.get("occurrence"), pass_doc, E.ROLE_INVITEE, True,
                                        session=session)
        _set = dict(maj, **{"reservations.invitee_id": _r.get("id"),
                            "reservations.invitee_code": _r.get("reservationCode"),
                            "invitee_access_code": access_code,
                            "updated_at": _iso()})
        _upd = {"$set": _set, "$inc": {"version": 1}}
        if push:
            _upd["$push"] = dict(push)
        _kw = {"session": session} if session is not None else {}
        await db[COLL_PASSES].update_one({"id": pass_doc["id"]}, _upd, **_kw)
        return _r
    return await _avec_session(_travail)


# ═══════════════════════════════════════════════════════════════════════════
# V534b — Changement d'offre
# ═══════════════════════════════════════════════════════════════════════════
def _filtre_version(pass_id, version) -> dict:
    """`{"id", "version"}` — un pass né avant V534b (sans champ) vaut 1."""
    _f = {"id": pass_id}
    if int(version) == 1:
        _f["$or"] = [{"version": 1}, {"version": {"$exists": False}}]
    else:
        _f["version"] = int(version)
    return _f


def _version_du_corps(corps) -> int:
    _v = (corps or {}).get("version")
    if isinstance(_v, bool) or _v is None:
        raise _refus(400, "version_requise", "Version du pass requise (recharge la page).")
    try:
        return int(_v)
    except (TypeError, ValueError):
        raise _refus(400, "version_requise", "Version du pass requise (recharge la page).")


async def _annuler_reservation_ami(reservation_id, code, motif) -> dict:
    """Restitue la séance de CETTE réservation (`seances_restituer`, clé =
    id de la réservation) puis la SUPPRIME — la convention du dépôt : il
    n'existe aucun statut d'annulation sur `reservations` (l'annulation LOT B3
    fait `delete_one`, et ni l'espace, ni le scanner, ni les analytics ne
    lisent un `status`). Une réservation « cancelled » resterait visible dans
    « Mes prochaines séances » et scannable par CAS A : on ne l'invente pas.
    La trace vit dans `referral_passes.events` / `offer_history` (le document
    complet est rendu dans `avant` pour une restauration à l'identique)."""
    from api.routes.shared import seances_restituer
    _avant = await db["reservations"].find_one({"id": reservation_id}, {"_id": 0}) or {}
    _rest = await seances_restituer(db, code, 1, reservation_id=reservation_id, source=motif)
    await db["reservations"].delete_one({"id": reservation_id})
    return {"restitution": _rest, "avant": _avant}


async def _restaurer_ancien_octroi(pass_doc, ancien, email, tel) -> None:
    """(d) de l'avenant §4.5 : le re-octroi a échoué -> on RÉTABLIT l'ancien
    état exactement (code, forfait, réservation, séance, verrou d'essai).
    Chaque étape est indépendante : une panne n'empêche pas les suivantes."""
    from api.routes.shared import SEANCES_COLL
    _code = ancien.get("access_code")
    _rid = ancien.get("reservation_id")
    _unset_marques = {"pass_duo_rollback": "", "pass_duo_rollback_at": "", "pass_duo_rollback_motif": ""}
    try:
        if _code and ancien.get("code_doc") is not None:
            _c = ancien["code_doc"]
            await db["discount_codes"].update_one(
                {"code": _code},
                {"$set": {"active": _c.get("active", True), "maxUses": _c.get("maxUses", 1)},
                 "$unset": _unset_marques})
        if _code and ancien.get("sub_doc") is not None:
            _s = ancien["sub_doc"]
            await db["subscriptions"].update_one(
                {"code": _code},
                {"$set": {"status": _s.get("status", "active"),
                          "remaining_sessions": _s.get("remaining_sessions", 0),
                          "total_sessions": _s.get("total_sessions", 1)},
                 "$unset": _unset_marques})
    except Exception as _err:  # noqa: BLE001
        logger.error("%s restauration du forfait impossible (%s)", PREFIXE, type(_err).__name__)
    try:
        if _rid:
            _av = (ancien.get("annulation") or {}).get("avant") or {}
            # La réservation supprimée en (a) est RÉINSÉRÉE à l'identique (document
            # complet conservé), si elle n'est pas déjà revenue.
            if _av and not await db["reservations"].find_one({"id": _rid}, {"_id": 1}):
                await db["reservations"].insert_one(dict(_av))
            _rest = (ancien.get("annulation") or {}).get("restitution") or {}
            if _rest.get("restitue") and _rest.get("fiche_id"):
                # La séance rendue est REPRISE sur la même fiche, et le mouvement
                # de restitution effacé : une vraie annulation future pourra
                # restituer à son tour (règle « une fois par clé »).
                await db["discount_codes"].update_one(
                    {"id": _rest["fiche_id"]}, {"$inc": {"used": int(_rest.get("quantite") or 1)}})
                await db[SEANCES_COLL].delete_one({"_id": "restitution:%s" % _rid})
    except Exception as _err:  # noqa: BLE001
        logger.error("%s restauration de la réservation impossible (%s)", PREFIXE, type(_err).__name__)
    try:
        from api.routes.checkout_routes import _essai1_reclamer
        await _essai1_reclamer(email, tel)
    except Exception as _err:  # noqa: BLE001
        logger.error("%s verrou d'essai non repris (%s)", PREFIXE, type(_err).__name__)


async def _changer_offre_apres_join(pass_doc, course, nouvelle, entree, changed_by) -> dict:
    """§4.5 friend_registered / unlocked SANS présence : (a) neutraliser
    l'ancien octroi ; (b) re-octroyer par le MÊME chemin que le join ; (c) la
    réservation du parrain n'est pas touchée ; (d) échec en (b) -> rollback de
    (b) + restauration de (a), 500 propre, le pass garde l'ancienne offre.

    ATOMICITÉ RÉELLE : `_process_successful_payment` et le verrou ESSAI-1
    n'acceptent pas de session Mongo (et on ne les modifie pas) — la
    transaction `_avec_session` couvre la réservation de l'ami + le pass
    (comme au join) ; le reste est COMPENSÉ explicitement. Aucune écriture
    n'est faite sur le pass avant que (b) ait réussi : un lecteur concurrent
    voit toujours l'ancienne offre, jamais un entre-deux."""
    _inv = pass_doc.get("invitee") or {}
    _email = E.normaliser_email(_inv.get("email_norm"))
    _tel = str(_inv.get("whatsapp_norm") or "")
    _nom = str(_inv.get("name") or "")
    _ancien_code = str(pass_doc.get("invitee_access_code") or "").strip().upper()
    _ancien_rid = (pass_doc.get("reservations") or {}).get("invitee_id")
    _ancien = {"access_code": _ancien_code, "reservation_id": _ancien_rid,
               "code_doc": None, "sub_doc": None, "annulation": None}
    if _ancien_code:
        _ancien["code_doc"] = await db["discount_codes"].find_one(
            {"code": _ancien_code}, {"_id": 0, "active": 1, "maxUses": 1})
        _ancien["sub_doc"] = await db["subscriptions"].find_one(
            {"code": _ancien_code}, {"_id": 0, "status": 1, "remaining_sessions": 1, "total_sessions": 1})

    # ── (a) neutralisation de l'ancien octroi ──────────────────────────────
    if _ancien_rid:
        _ancien["annulation"] = await _annuler_reservation_ami(_ancien_rid, _ancien_code, E.MOTIF_CHANGEMENT_OFFRE)
    await _rollback_filleul(pass_doc, _email, _tel, _ancien_code, motif=E.MOTIF_CHANGEMENT_OFFRE, rouvrir=False)

    # ── (b) re-octroi, MÊME chemin que le join ─────────────────────────────
    _nouveau_code = ""
    try:
        _nouveau_code, _attrib = await _octroyer_essai(pass_doc, nouvelle, _email, _nom, _tel, None)
        _resa = await _reserver_ami(
            pass_doc, course, _nouveau_code, _email, _nom, _tel,
            {"offer_id": nouvelle.get("id"), "offer_snapshot": E.snapshot_offre(nouvelle),
             "attribution": _attrib or pass_doc.get("attribution"),
             "offer_change": None},
            {"offer_history": entree,
             # La réservation remplacée est SUPPRIMÉE (convention du dépôt) : sa trace
             # — id et reservationCode — reste ici, dans l'événement du pass.
             "events": {"at": _iso(), "type": E.EVENEMENT_OFFRE,
                        "detail": dict(entree, reservation_remplacee={
                            "id": _ancien_rid,
                            "reservationCode": ((_ancien.get("annulation") or {}).get("avant") or {}).get("reservationCode"),
                            "access_code_neutralise": _ancien_code})}})
    except Exception as _err:  # noqa: BLE001
        # ── (d) rollback de (b), puis restauration de (a) ──────────────────
        _detail = getattr(_err, "detail", None) if isinstance(_err, HTTPException) else None
        logger.error("%s re-octroi échoué (%s) — ancienne offre restaurée", PREFIXE,
                     _detail or type(_err).__name__)
        if _nouveau_code:
            _orpheline = await db["reservations"].find_one(
                {"pass_id": pass_doc["id"], "pass_role": E.ROLE_INVITEE, "promoCode": _nouveau_code,
                 "status": {"$ne": "cancelled"}}, {"_id": 0, "id": 1})
            if _orpheline:
                await _annuler_reservation_ami(_orpheline["id"], _nouveau_code, E.MOTIF_CHANGEMENT_OFFRE + "_echec")
            await _rollback_filleul(pass_doc, _email, _tel, _nouveau_code,
                                    motif=E.MOTIF_CHANGEMENT_OFFRE + "_echec", rouvrir=False)
        await _restaurer_ancien_octroi(pass_doc, _ancien, _email, _tel)
        await _evenement(pass_doc["id"], "offer_change_failed",
                         {"to_offer_id": nouvelle.get("id"), "changed_by": changed_by},
                         {"offer_change": None})
        raise HTTPException(status_code=500,
                            detail="Le changement d'offre a échoué : ton Pass Duo garde son offre actuelle.")
    _p = await db[COLL_PASSES].find_one({"id": pass_doc["id"]}, {"_id": 0}) or pass_doc
    _sub = await db["subscriptions"].find_one({"code": _nouveau_code}, {"_id": 0})
    await _notifier_reservation(_resa, _sub)
    await _suivre_place_enfant(pass_doc["id"], _ancien_rid, _resa, _nouveau_code)   # V556
    return _p


async def _changer_offre(pass_doc, offer_id, version, changed_by) -> dict:
    """L'avenant §4, dans l'ordre : 2 pass modifiable ; 3 version ; 4 offre
    autorisée / idempotence ; 5 effet selon l'état ; 6 historique. (1 —
    drapeau, appelant — est fait par la route.) Rend le pass à jour."""
    _resas = await _reservations_du_pass(pass_doc)
    _s = await _statut_reel(pass_doc, None, _resas)
    _ok, _raison = E.pass_modifiable_pour_offre(pass_doc, _resas, _s)
    if not _ok:
        raise _refus(409, E.REFUS_PASS_NON_MODIFIABLE, E.texte_non_modifiable(_raison))
    if int(version) != E.version_pass(pass_doc):
        raise _refus(409, E.REFUS_CONFLIT_VERSION,
                     "Ce pass a été modifié entre-temps : recharge la page et réessaie.")
    _course = await db["courses"].find_one({"id": pass_doc.get("course_id")}, {"_id": 0})
    if not _course or _course.get("archived") is True:
        raise HTTPException(status_code=410, detail="Ce cours n'est plus disponible.")
    _nouvelle = await _offre_autorisee(_course, offer_id)
    if str(_nouvelle.get("id")) == str(pass_doc.get("offer_id") or ""):
        return pass_doc                                  # idempotent, aucune écriture
    _entree = E.entree_historique_offre(pass_doc.get("offer_snapshot") or {"id": pass_doc.get("offer_id")},
                                        E.snapshot_offre(_nouvelle), changed_by, _iso())
    from pymongo import ReturnDocument

    if _s in (E.LOCKED, E.WAITING) or not pass_doc.get("invitee"):
        # Personne n'a rien reçu : UNE écriture, gardée par la version.
        _apres = await db[COLL_PASSES].find_one_and_update(
            _filtre_version(pass_doc["id"], version),
            {"$set": {"offer_id": _nouvelle.get("id"), "offer_snapshot": E.snapshot_offre(_nouvelle),
                      "updated_at": _iso()},
             "$push": {"offer_history": _entree,
                       "events": {"at": _iso(), "type": E.EVENEMENT_OFFRE, "detail": dict(_entree)}},
             "$inc": {"version": 1}},
            projection={"_id": 0}, return_document=ReturnDocument.AFTER)
        if not _apres:
            raise _refus(409, E.REFUS_CONFLIT_VERSION,
                         "Ce pass a été modifié entre-temps : recharge la page et réessaie.")
        logger.info("%s offre du pass %s changée (%s -> %s, %s)", PREFIXE, pass_doc["id"][:8],
                    str(_entree["from_offer_id"])[:8], str(_entree["to_offer_id"])[:8], changed_by)
        return _apres

    # Ami inscrit, aucune présence : le VERROU de version est pris d'abord
    # (le concurrent perd ici, avant toute écriture métier), puis l'effet.
    _verrou = await db[COLL_PASSES].find_one_and_update(
        _filtre_version(pass_doc["id"], version),
        {"$set": {"offer_change": {"to_offer_id": _nouvelle.get("id"), "by": changed_by,
                                   "started_at": _iso()}, "updated_at": _iso()},
         "$inc": {"version": 1}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    if not _verrou:
        raise _refus(409, E.REFUS_CONFLIT_VERSION,
                     "Ce pass a été modifié entre-temps : recharge la page et réessaie.")
    _p = await _changer_offre_apres_join(_verrou, _course, _nouvelle, _entree, changed_by)
    logger.info("%s offre du pass %s changée après join (%s -> %s, %s)", PREFIXE, pass_doc["id"][:8],
                str(_entree["from_offer_id"])[:8], str(_entree["to_offer_id"])[:8], changed_by)
    return _p


# ═══════════════════════════════════════════════════════════════════════════
# Routes — parrain
# ═══════════════════════════════════════════════════════════════════════════
@router.get("/config")
async def referral_config():
    """Public. OFF -> `{enabled:false, courses:[]}` (jamais 404 ici).
    V534b : chaque cours porte `offers[]` (OffreDTO) + `default_offer_id` ;
    un cours `duo_enabled` SANS offre valide est OMIS et journalisé."""
    if not await parrainage_duo_actif(db):
        return {"enabled": False, "courses": []}
    _sortie = []
    for _c in await _cours_eligibles():
        _valides, _defaut = await _offres_du_cours(_c)
        if not _valides:
            logger.info("%s cours %s omis du /config : aucune offre Duo valide (duo_offer_ids=%s)",
                        PREFIXE, str(_c.get("id"))[:12], len(_c.get("duo_offer_ids") or []))
            continue
        _sortie.append(_dto_config_cours(_c, E.dtos_offres(_valides, _defaut), _defaut))
    return {"enabled": True, "courses": _sortie}


@router.get("/me")
async def referral_me(request: Request):
    await _exiger_actif()
    _p = await _parrain_depuis_requete(request)
    _now = _maintenant()
    try:
        _passes = await db[COLL_PASSES].find(
            {"sponsor.email_norm": _p["email"]}, {"_id": 0}
        ).sort("created_at", -1).to_list(LISTE_MAX)
        _invits = await db[COLL_INVITATIONS].find(
            {"sponsor_email_norm": _p["email"]}, {"_id": 0}
        ).sort("created_at", -1).to_list(LISTE_MAX)
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s lecture /me impossible (%s)", PREFIXE, type(_err).__name__)
        raise HTTPException(status_code=503, detail="Parrainage momentanément indisponible")
    _dtos, _statuts, _cache = [], {}, {}
    for _pd in _passes:
        _d = await _dto(_pd, now=_now, cache_offres=_cache)
        _dtos.append(_d)
        _statuts[_pd.get("id")] = _d["status"]
    return {
        "enabled": True,
        # V551 : même filtre que partout ailleurs — jamais la partie locale de l'e-mail
        # (« MON CENTRE · BASSICUSTOMSHOES » vu en production le 28/09).
        "sponsor": {"first_name": E.nom_affichable(_p.get("name"), _p.get("email")), "code": _p["code"]},
        "stats": E.stats_parrain(_passes, _invits, _statuts),
        "passes": _dtos,
        "invitations": [{"id": i.get("id"), "pass_id": i.get("pass_id"),
                         "channel": i.get("channel"), "created_at": i.get("created_at")}
                        for i in _invits],
        "history": E.historique(_passes, LISTE_MAX),
    }


async def _campagne_pass_duo(jeton, course_id=None) -> dict:
    """INV-1 — l'invitation de coach `{id, message}` désignée par son share_token,
    SEULEMENT si elle est `active`, de type `pass_duo` ET porte sur le MÊME cours
    que le pass (audit P2) ; sinon None. Ne lève
    jamais : le parcours du Pass Duo ne change pas quand elle est absente."""
    if not isinstance(jeton, str):
        return None
    _t = jeton.strip()
    _cid = str(course_id or "").strip()
    if not _t or len(_t) > 64 or not _cid:
        return None
    try:
        _c = await db["referral_campaigns"].find_one(
            {"share_token": _t, "status": "active", "type": "pass_duo", "course_id": _cid},
            {"_id": 0, "id": 1, "message": 1})
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s invitation de coach illisible (%s) — ignorée", PREFIXE, type(_err).__name__)
        return None
    if not _c or not _c.get("id"):
        return None
    return {"id": _c["id"], "message": _c.get("message") or None}


@router.post("/pass")
async def referral_creer_pass(request: Request):
    """`{course_id, occurrence, offer_id, terms_accepted?}` -> 201 PassDTO ;
    pass actif déjà existant -> 200 `deja_existant:true` ; cours inéligible /
    occurrence invalide -> 400 ; V534b : `offer_id` OBLIGATOIRE, validé par
    `_offre_autorisee` (400 offre_requise | offre_non_autorisee |
    offre_inactive | offre_payante | offre_autre_coach). Débit par IP AVANT tout."""
    await _exiger_actif()
    _exiger_debit(request, DEBIT_PREFIXE_PASS)
    _parrain = await _parrain_depuis_requete(request)
    _b = await _corps(request)
    _course = await _cours_eligible(_b.get("course_id"))
    if not _course:
        raise HTTPException(status_code=400, detail="Ce cours n'est pas ouvert au Pass Duo.")
    from api.routes.reservation_routes import lot1_occurrence_iso
    _occ = lot1_occurrence_iso(_b.get("occurrence"))
    if not _occ or _occ not in _occurrences(_course):
        raise HTTPException(status_code=400, detail="Occurrence invalide : choisis une date proposée.")
    _offre = await _offre_autorisee(_course, _b.get("offer_id"))
    # V551 : invitation personnalisée facultative, validée AVANT toute écriture.
    _invitation = None
    if _b.get("invitation") is not None:
        try:
            _invitation = E.valider_invitation(_b.get("invitation"))
        except E.InvitationInvalide as _err:
            raise HTTPException(status_code=422, detail=str(_err))
    # INV-1 : invitation de coach facultative (`referral_campaign` = son share_token).
    # Inconnue / inactive / d'un autre type -> ignorée SILENCIEUSEMENT.
    _campagne = await _campagne_pass_duo(_b.get("referral_campaign"), _course.get("id"))

    _now = _maintenant()
    _cle = E.cle_pass(_parrain["email"], _course.get("id"), _occ)
    _existant = await db[COLL_PASSES].find_one(
        {"sponsor.email_norm": _cle[0], "course_id": _cle[1], "occurrence": _cle[2],
         "status": {"$in": list(E.ETATS_ACTIFS)}}, {"_id": 0})
    if _existant:
        return JSONResponse(status_code=200, content=await _dto(_existant, True, _now))

    from api.routes.shared import essai6_normaliser_tel
    _doc = {
        "id": str(uuid.uuid4()),
        "coach_id": (_parrain.get("coach_id") or _course.get("coach_id") or ""),
        "course_id": _course.get("id"),
        "occurrence": _occ,
        "course_snapshot": {
            "name": _course.get("name") or "",
            "time": _course.get("time") or "",
            "locationName": _course.get("locationName") or _course.get("location") or "",
            "mapsUrl": _course.get("mapsUrl") or "",
        },
        "sponsor": {
            "email_norm": _parrain["email"],
            "name": _parrain["name"] or "",
            "whatsapp_norm": essai6_normaliser_tel(_parrain.get("whatsapp")) or None,
            "subscription_code": _parrain["code"],
            "terms_accepted": _b.get("terms_accepted") is True,
        },
        "invitee": None,
        "status": E.LOCKED,
        "share_token": secrets.token_urlsafe(24),
        "opened_at": None,
        "reservations": {"sponsor_id": None, "sponsor_code": None,
                         "invitee_id": None, "invitee_code": None},
        "invitee_access_code": None,
        "blocked_reason": None,
        "attribution": None,
        "spordate_reward": {"status": "none"},
        # V534b : l'offre choisie par le participant, figée + son historique.
        "offer_id": _offre.get("id"),
        "offer_snapshot": E.snapshot_offre(_offre),
        "offer_history": [],
        "version": 1,
        "created_at": _iso(_now),
        "updated_at": _iso(_now),
        "unlocked_at": None,
        "expires_at": _occ,
        "events": [{"at": _iso(_now), "type": "pass_created", "detail": None}],
    }
    if _campagne:
        # INV-1 : le pass garde la trace de l'invitation du coach ; son message
        # préremplit celui du membre s'il n'en a donné aucun.
        _doc["referral_campaign_id"] = _campagne["id"]
        if _campagne.get("message") and not (_invitation or {}).get("message"):
            _invitation = dict(_invitation or {"display_name": None, "photo_url": None},
                               message=_campagne["message"])
    if _invitation is not None:             # V551 : appliquée à la création seulement
        _doc["invitation"] = dict(_invitation, updated_at=_iso(_now))
        _doc["invitation_version"] = 1
    # L0 : QUI invite, figé à la création (photo de l'invitation, sinon du profil du membre).
    _doc["inviter_display"] = E.identite_invitant(
        _doc, await _photo_profil((_doc.get("sponsor") or {}).get("email_norm")))
    try:
        await db[COLL_PASSES].insert_one(dict(_doc))
    except Exception as _err:  # noqa: BLE001
        if _est_doublon(_err):
            _existant = await db[COLL_PASSES].find_one(
                {"sponsor.email_norm": _cle[0], "course_id": _cle[1], "occurrence": _cle[2],
                 "status": {"$in": list(E.ETATS_ACTIFS)}}, {"_id": 0})
            if _existant:
                return JSONResponse(status_code=200, content=await _dto(_existant, True, _now))
        logger.error("%s création du pass impossible (%s)", PREFIXE, type(_err).__name__)
        raise HTTPException(status_code=503, detail="Pass non créé, réessaie dans un instant.")
    logger.info("%s pass créé (%s, cours %s)", PREFIXE, _doc["id"][:8], str(_doc["course_id"])[:8])
    return JSONResponse(status_code=201, content=await _dto(_doc, None, _now))


@router.post("/invitations")
async def referral_invitation(request: Request):
    """`{pass_id, channel}` -> 201 `{id}` ; `locked` -> `waiting`."""
    await _exiger_actif()
    _parrain = await _parrain_depuis_requete(request)
    _b = await _corps(request)
    _canal = str(_b.get("channel") or "").strip().lower()
    if _canal not in E.CANAUX:
        raise HTTPException(status_code=400, detail="Canal inconnu (%s)." % ", ".join(E.CANAUX))
    _p = await _pass_du_parrain(_b.get("pass_id"), _parrain)
    _s = await _statut_reel(_p)
    if _s not in E.ETATS_ACTIFS:
        raise HTTPException(status_code=409, detail="Ce pass n'est plus actif.")
    _inv = {"id": str(uuid.uuid4()), "pass_id": _p["id"], "sponsor_email_norm": _parrain["email"],
            "channel": _canal, "created_at": _iso()}
    await db[COLL_INVITATIONS].insert_one(dict(_inv))
    _maj = {}
    if _s == E.LOCKED:
        _maj["status"] = E.transition(E.LOCKED, E.WAITING)
    await _evenement(_p["id"], "invitation_sent", _canal, _maj)
    # V556 : ce partage a utilisé la share_url courante ; le PROCHAIN aura une
    # URL neuve (même jeton, même parrain, aucun crédit) — WhatsApp refait
    # l'aperçu au lieu de ressortir un envoi sans miniature.
    _apres = await _nouvelle_version_apercu(_p["id"]) or _p
    return JSONResponse(status_code=201, content={
        "id": _inv["id"], "pass_id": _p["id"], "channel": _canal, "created_at": _inv["created_at"],
        "share_url": E.url_partage_versionnee(_frontend_url(), _apres),
        "card_url": E.url_carte(_frontend_url(), _apres) or None})


@router.post("/pass/{pass_id}/cancel")
async def referral_annuler(pass_id: str, request: Request):
    """-> 200 PassDTO `cancelled` ; 409 depuis `unlocked` / `used` (les
    réservations existent : l'annulation passe par elles)."""
    await _exiger_actif()
    _parrain = await _parrain_depuis_requete(request)
    _p = await _pass_du_parrain(pass_id, _parrain)
    _s = await _statut_reel(_p)
    if _s not in E.ETATS_ANNULABLES:
        raise HTTPException(status_code=409, detail="Ce pass ne peut plus être annulé (%s)."
                            % E.LIBELLES.get(_s, _s))
    await _evenement(_p["id"], "cancelled", None, {"status": E.transition(_s, E.CANCELLED)})
    _p = await db[COLL_PASSES].find_one({"id": _p["id"]}, {"_id": 0}) or _p
    return await _dto(_p)


@router.post("/pass/{pass_id}/confirm")
async def referral_confirmer(pass_id: str, request: Request):
    """Retente la place du parrain (`friend_registered` -> `unlocked`) ;
    409 `X-Refus-Raison: sponsor_sans_seance` (ou `conditions_non_acceptees`)."""
    await _exiger_actif()
    _parrain = await _parrain_depuis_requete(request)
    _b = await _corps(request)
    _p = await _pass_du_parrain(pass_id, _parrain)
    await _relier_enfant_si_besoin(_p)          # V556 : l'enfant de CE pass (son filleul inscrit)
    await _relier_enfant_si_besoin(await _parent_de(_p) if E.chaine_du_pass(_p).get("parent_pass_id") else None)  # V556
    _p = await db[COLL_PASSES].find_one({"id": _p["id"]}, {"_id": 0}) or _p
    _s = await _statut_reel(_p)
    if _s == E.UNLOCKED:
        return await _dto(_p)
    if _s != E.FRIEND_REGISTERED:
        raise HTTPException(status_code=409, detail="Ton ami n'est pas encore inscrit.")
    if _b.get("terms_accepted") is True and not (_p.get("sponsor") or {}).get("terms_accepted"):
        await db[COLL_PASSES].update_one({"id": _p["id"]}, {"$set": {"sponsor.terms_accepted": True},
                                                            "$inc": {"version": 1}})
        _p["sponsor"]["terms_accepted"] = True
    _course = await db["courses"].find_one({"id": _p.get("course_id")}, {"_id": 0})
    if not _course:
        raise HTTPException(status_code=404, detail="Cours introuvable")
    _p = await _debloquer_ou_bloquer(_p, _course)
    if _p.get("status") != E.UNLOCKED:
        raise _refus(409, _p.get("blocked_reason") or E.BLOCAGE_SPONSOR_SANS_SEANCE,
                     "Ta place n'a pas pu être confirmée : recharge ton abonnement puis réessaie."
                     if _p.get("blocked_reason") != E.BLOCAGE_CONDITIONS
                     else "Merci d'accepter les conditions de participation pour confirmer ta place.")
    return await _dto(_p)


def _porte_identite_abonne(request) -> bool:
    """Un jeton d'espace ou un jeton abonné est-il présenté ? (Décide quelle
    porte du PATCH offre s'applique — jamais `X-User-Email`.)"""
    try:
        return bool((request.headers.get("x-espace-token", "") or "").strip()
                    or (request.headers.get("X-Subscriber-Token", "") or "").strip())
    except Exception:  # noqa: BLE001
        return False


@router.patch("/pass/{identifiant}/offer")
async def referral_changer_offre(identifiant: str, request: Request):
    """V534b — `{offer_id, version}` -> 200 PassDTO. UNE URL, DEUX PORTES :

    * PARRAIN (`x-espace-token` / `X-Subscriber-Token`) : `identifiant` =
      id du pass (ou son share_token), pass DU parrain sinon 404 ;
      `changed_by: "sponsor"` ; possible dans tout état modifiable.
    * PUBLIC (aucun jeton, débit IP) : `identifiant` = share_token ;
      `changed_by: "invitee"` ; AVANT join uniquement (locked/waiting, sans
      invité) sinon 409 `pass_deja_rejoint`.

    Refus : 400 offre_* / version_requise ; 409 pass_non_modifiable
    (`used` -> texte exact de l'avenant), conflit_version (recharger),
    pass_deja_rejoint ; 500 propre si le re-octroi échoue (ancienne offre
    conservée). `offer_id == offre du pass` -> 200 sans écriture."""
    await _exiger_actif()
    _b = await _corps(request)
    if _porte_identite_abonne(request):
        _parrain = await _parrain_depuis_requete(request)
        _p = await db[COLL_PASSES].find_one(
            {"$or": [{"id": str(identifiant or "").strip()}, {"share_token": str(identifiant or "").strip()}]},
            {"_id": 0})
        if not _p or E.normaliser_email((_p.get("sponsor") or {}).get("email_norm")) != _parrain["email"]:
            raise HTTPException(status_code=404, detail="Pass introuvable")
        _qui = "sponsor"
    else:
        _exiger_debit(request, DEBIT_PREFIXE_OFFRE)
        _p = await _pass_par_token(identifiant)
        _s = await _statut_reel(_p)
        if _p.get("invitee") or _s not in E.ETATS_OUVERTS_AU_JOIN:
            if _s in (E.EXPIRED, E.CANCELLED):
                raise HTTPException(status_code=410, detail="Cette invitation n'est plus valable.")
            raise _refus(409, E.REFUS_PASS_DEJA_REJOINT,
                         "Tu es déjà inscrit : seul le parrain peut encore changer l'offre.")
        _qui = "invitee"
    if E.campagne_du_pass(_p):
        # PAR-1 : l'offre d'une invitation de campagne est celle de la campagne.
        raise _refus(409, E.REFUS_PASS_NON_MODIFIABLE, "L'offre de cette invitation est fixée par le coach.")
    _version = _version_du_corps(_b)
    _p = await _changer_offre(_p, _b.get("offer_id"), _version, _qui)
    return await _dto(_p)


async def _changer_seance(pass_doc, occurrence, version, changed_by) -> dict:
    """V539 — la séance du pass, changée AVANT l'inscription de l'ami.

    MÊME ARMATURE QUE LE CHANGEMENT D'OFFRE, volontairement : version pour la
    concurrence, occurrence relue dans la liste DU SERVEUR, une seule écriture
    gardée, historique et événement. Ce qui change vraiment : la date du pass,
    et sa date d'expiration — un pass ne survit pas à sa séance.

    LE COURS NE CHANGE PAS. L'avantage, l'offre et les règles sont attachés à
    ce cours-là ; déplacer la date d'une séance est une commodité, changer de
    cours serait un autre pass.
    """
    _resas = await _reservations_du_pass(pass_doc)
    _s = await _statut_reel(pass_doc, None, _resas)
    if pass_doc.get("invitee") or _s not in E.ETATS_OUVERTS_AU_JOIN:
        raise _refus(409, E.REFUS_PASS_NON_MODIFIABLE,
                     "La séance ne peut plus être changée : des billets ont déjà été émis.")
    # V556 : l'invitation enfant suit la séance de son parent tant que son ami
    # ne l'a pas rejointe ; ensuite, déplacer le parent séparerait le duo.
    # Toute la DESCENDANCE suit (enfant, petit-enfant...) : un maillon laissé à
    # l'ancienne date ne retrouverait jamais la place de son parrain.
    _descendants = await _descendance(pass_doc)
    # V558 : un maillon qui a CHOISI sa séance ne suit plus son parent — ni lui,
    # ni sa descendance (elle suit la séance de SON parent à lui).
    _suiveurs = []
    for _d in _descendants:
        if E.seance_choisie(_d):
            break
        _suiveurs.append(_d)
    _descendants = _suiveurs
    if any(_d.get("invitee") for _d in _descendants):
        raise _refus(409, E.REFUS_PASS_NON_MODIFIABLE,
                     "Ton ami s'est déjà inscrit à cette séance : elle ne peut plus changer.")
    if int(version) != E.version_pass(pass_doc):
        raise _refus(409, E.REFUS_CONFLIT_VERSION,
                     "Ce pass a été modifié entre-temps : recharge la page et réessaie.")
    _course = await db["courses"].find_one({"id": pass_doc.get("course_id")}, {"_id": 0})
    if not _course or _course.get("archived") is True or _course.get("visible") is False:
        raise HTTPException(status_code=410, detail="Ce cours n'est plus disponible.")
    _dispos = _occurrences(_course)
    _cible, _motif = E.occurrence_choisissable(occurrence, _dispos, _maintenant())
    if not _cible:
        raise _refus(400, _motif, "Cette séance n'est plus proposée : choisis-en une autre.")
    if _cible == str(pass_doc.get("occurrence") or ""):
        return pass_doc                                  # idempotent, aucune écriture

    _entree = E.entree_historique_seance(pass_doc.get("occurrence"), _cible, changed_by, _iso())
    from pymongo import ReturnDocument
    _apres = await db[COLL_PASSES].find_one_and_update(
        _filtre_version(pass_doc["id"], version),
        {"$set": {"occurrence": _cible, "expires_at": _cible, "updated_at": _iso()},
         "$push": {"occurrence_history": _entree,
                   "events": {"at": _iso(), "type": E.EVENEMENT_SEANCE, "detail": dict(_entree)}},
         "$inc": {"version": 1}},
        projection={"_id": 0}, return_document=ReturnDocument.AFTER)
    if not _apres:
        raise _refus(409, E.REFUS_CONFLIT_VERSION,
                     "Ce pass a été modifié entre-temps : recharge la page et réessaie.")
    for _d in _descendants:
        await _synchroniser_seance_enfant(_d, _cible, _entree)
    logger.info("%s seance du pass %s changee (%s -> %s, %s)", PREFIXE, pass_doc["id"][:8],
                str(_entree["from_occurrence"])[:16], str(_entree["to_occurrence"])[:16], changed_by)
    return _apres


@router.patch("/pass/{identifiant}/occurrence")
async def referral_changer_seance(identifiant: str, request: Request):
    """V539 — `{occurrence, version}` -> 200 PassDTO (parrain) ou PassPublicDTO.

    DEUX PORTES, comme pour l'offre : le PARRAIN (jeton d'espace) sur son
    propre pass, l'AMI (public, débit IP) sur le share_token, et lui seulement
    AVANT son inscription. L'occurrence doit figurer dans la liste rendue par
    le serveur pour ce cours : une date tapée à la main est refusée."""
    await _exiger_actif()
    _b = await _corps(request)
    if _porte_identite_abonne(request):
        _parrain = await _parrain_depuis_requete(request)
        _p = await db[COLL_PASSES].find_one(
            {"$or": [{"id": str(identifiant or "").strip()}, {"share_token": str(identifiant or "").strip()}]},
            {"_id": 0})
        if not _p or E.normaliser_email((_p.get("sponsor") or {}).get("email_norm")) != _parrain["email"]:
            raise HTTPException(status_code=404, detail="Pass introuvable")
        if E.chaine_du_pass(_p).get("parent_pass_id"):
            # V556 : sa place est celle de filleul du pass parent, sur CETTE séance.
            raise _refus(409, E.REFUS_PASS_NON_MODIFIABLE,
                         "Cette invitation suit ta séance : change-la depuis ton invitation d'origine.")
        _qui, _public = "sponsor", False
    else:
        _exiger_debit(request, DEBIT_PREFIXE_OFFRE)
        _p = await _pass_par_token(identifiant)
        _s = await _statut_reel(_p)
        if _p.get("invitee") or _s not in E.ETATS_OUVERTS_AU_JOIN:
            if _s in (E.EXPIRED, E.CANCELLED):
                raise HTTPException(status_code=410, detail="Cette invitation n'est plus valable.")
            raise _refus(409, E.REFUS_PASS_DEJA_REJOINT,
                         "Tu es déjà inscrit : seul le parrain peut encore changer la séance.")
        if E.chaine_du_pass(_p).get("parent_pass_id"):
            # V556 : une invitation de la chaîne vaut pour LA séance de son
            # parrain (sa place y est déjà) — la déplacer séparerait le duo.
            raise _refus(409, E.REFUS_PASS_NON_MODIFIABLE,
                         "Cette invitation est liée à la séance de ton parrain.")
        _qui, _public = "invitee", True
    if E.campagne_du_pass(_p):
        # PAR-1 : toute la chaîne d'une campagne vit sur SA séance.
        raise _refus(409, E.REFUS_PASS_NON_MODIFIABLE, "Cette invitation vaut pour la séance choisie par le coach.")
    _p = await _changer_seance(_p, _b.get("occurrence"), _version_du_corps(_b), _qui)
    if _public:
        _now = _maintenant()
        _rep = E.dto_public(_p, await _statut_reel(_p, _now), _now,
                            await _catalogue_du_pass(_p, {}))
        # La même forme que le GET : l'écran garde sa liste de séances après le
        # changement, sans second aller-retour.
        _rep["occurrences"] = await _occurrences_du_pass(_p)
        return _rep
    return await _dto(_p)


# ═══════════════════════════════════════════════════════════════════════════
# V551 — PARRAINAGE V2 : l'invitation personnalisée du membre
# ═══════════════════════════════════════════════════════════════════════════
async def _reglage_partage(cle):
    """Le document de réglages d'une clé (coach en minuscules, "" = plateforme)."""
    try:
        return await db[COLL_REGLAGES_PARTAGE].find_one({"_id": str(cle or "")}) or {}
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s réglages de partage illisibles (%s)", PREFIXE, type(_err).__name__)
        return {}


async def _reglages_effectifs(cle) -> dict:
    """V551 — message et image effectifs : clé coach > plateforme ("") > intégré."""
    _cles = [str(cle or "").strip().lower()]
    if _cles[0]:
        _cles.append("")
    _msg, _img = None, None
    for _c in _cles:
        _r = await _reglage_partage(_c)
        _msg = _msg or (_r.get("default_message") or None)
        _img = _img or (_r.get("share_image_url") if E.url_image_partage_valide(_r.get("share_image_url")) else None)
    return {"message": _msg or E.MESSAGE_INVITATION_DEFAUT, "image_url": _img}


async def _pass_courant(parrain) -> dict:
    """Le pass ouvert le plus récent du membre (statut dérivé actif), ou None."""
    try:
        _passes = await db[COLL_PASSES].find(
            {"sponsor.email_norm": parrain["email"], "status": {"$in": list(E.ETATS_ACTIFS)}},
            {"_id": 0}).sort("created_at", -1).to_list(LISTE_MAX)
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s pass courant illisible (%s)", PREFIXE, type(_err).__name__)
        return None
    _now = _maintenant()
    for _pd in _passes:
        if await _statut_reel(_pd, _now) in E.ETATS_ACTIFS:
            return _pd
    return None


async def _photo_profil(email) -> str:
    """La photo du profil (lecture seule), si c'est une URL admise ; sinon None."""
    if not email:
        return None
    try:
        _u = await db["users"].find_one({"email": email}, {"_id": 0, "photo_url": 1, "photoUrl": 1}) or {}
    except Exception:  # noqa: BLE001
        return None
    try:
        return E.valider_photo_url(_u.get("photo_url") or _u.get("photoUrl"))
    except E.InvitationInvalide:
        return None


@router.get("/invitation")
async def referral_invitation_get(request: Request):
    """V551 — `{identity: {display_name, photo_url}, default_message, pass}`.
    Identité = jeton abonné (jamais un e-mail du corps ni X-User-Email)."""
    await _exiger_actif()
    _parrain = await _parrain_depuis_requete(request)
    _pd = await _pass_courant(_parrain)
    _inv = E.invitation_du_pass(_pd) if _pd else E.invitation_du_pass(None)
    _nom = _inv["display_name"] or E.nom_affichable(_parrain.get("name"), _parrain.get("email"))
    _photo = _inv["photo_url"] or await _photo_profil(_parrain.get("email"))
    _reg = await _reglages_effectifs(_parrain.get("coach_id"))
    return {
        "identity": {"display_name": _nom or "", "photo_url": _photo or None},
        "default_message": _reg["message"],
        # V551 : l'aperçu du membre montre l'image de partage de SON coach (None = le
        # front garde le visuel de l'offre, comme la page de partage).
        "effective": {"image_url": _reg["image_url"]},
        "pass": (await _dto(_pd)) if _pd else None,
    }


@router.put("/pass/{pass_id}/invitation")
async def referral_pass_invitation_put(pass_id: str, request: Request):
    """V551 — personnalise l'invitation d'UN pass (propriétaire seulement).
    Le `share_token` ne change JAMAIS ; seul `invitation_version` s'incrémente
    (-> `share_url?v=N`). Le profil principal n'est jamais touché."""
    await _exiger_actif()
    _parrain = await _parrain_depuis_requete(request)
    _p = await _pass_du_parrain(pass_id, _parrain)
    _s = await _statut_reel(_p)
    if _s in (E.CANCELLED, E.EXPIRED):
        raise HTTPException(status_code=409, detail="Ce pass n'est plus actif (%s)." % E.LIBELLES.get(_s, _s))
    _b = await _corps(request)
    try:
        _inv = E.valider_invitation(_b, _p.get("invitation"))
    except E.InvitationInvalide as _err:
        raise HTTPException(status_code=422, detail=str(_err))
    _now = _iso()
    # L0 : l'identité de l'invitant est re-figée avec l'invitation, dans la MÊME écriture.
    _idt = E.identite_invitant(dict(_p, invitation=_inv),
                               await _photo_profil((_p.get("sponsor") or {}).get("email_norm")))
    await db[COLL_PASSES].update_one(
        {"id": _p["id"], "share_token": _p.get("share_token")},
        {"$set": {"invitation": dict(_inv, updated_at=_now), "inviter_display": _idt,
                  "updated_at": _now},
         "$inc": {"invitation_version": 1}})
    _p = await db[COLL_PASSES].find_one({"id": _p["id"]}, {"_id": 0}) or _p
    logger.info("%s invitation du pass %s personnalisée (v%s)", PREFIXE, _p["id"][:8],
                E.version_invitation(_p))
    return await _dto(_p)


# ═══════════════════════════════════════════════════════════════════════════
# V551 — PARRAINAGE V2 : réglages de partage du coach (JWT signé STRICT)
# ═══════════════════════════════════════════════════════════════════════════
IMAGE_MAX_OCTETS = 3 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
IMAGE_EXTENSIONS = {"jpg": "jpg", "jpeg": "jpg", "png": "png", "webp": "webp"}


def _type_reel_image(octets) -> str:
    """La famille d'après la SIGNATURE binaire (jamais d'après le client)."""
    _b = bytes(octets or b"")
    if _b[:3] == b"\xff\xd8\xff":
        return "jpg"
    if _b[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if len(_b) >= 12 and _b[:4] == b"RIFF" and _b[8:12] == b"WEBP":
        return "webp"
    return ""


async def _coach_strict(request) -> dict:
    """`{email, cle}` — 401 sans jeton Bearer, 403 si le jeton n'est pas celui
    d'un coach/admin. `X-User-Email` n'est JAMAIS lu ici."""
    try:
        _auth = (request.headers.get("Authorization", "") or "").strip()
    except Exception:  # noqa: BLE001
        _auth = ""
    if not _auth.lower().startswith("bearer ") or not _auth.split(" ", 1)[1].strip():
        raise HTTPException(status_code=401, detail="Authentification coach requise — reconnectez-vous")
    _id = await _admin(request)
    return {"email": _id["email"], "cle": "" if _id["admin"] else str(_id["email"] or "").strip().lower()}


async def _reponse_reglages(cle) -> dict:
    _r = await _reglage_partage(cle)
    _eff = await _reglages_effectifs(cle)
    return {
        "default_message": _r.get("default_message") or None,
        "share_image_url": _r.get("share_image_url") or None,
        # `image_url` : l'image du coach, sinon celle de la plateforme, sinon le
        # visuel Afroboost (la page d'aperçu tente encore le média de l'offre avant).
        "effective": {"message": _eff["message"], "image_url": _eff["image_url"] or "/logo512.png"},
        "defaults": {"message": E.MESSAGE_INVITATION_DEFAUT},
        "updated_at": _r.get("updated_at"),
    }


async def _ecrire_reglages(cle, email, maj) -> None:
    await db[COLL_REGLAGES_PARTAGE].update_one(
        {"_id": cle}, {"$set": dict(maj, updated_at=_iso(), updated_by=email)}, upsert=True)


@router.get("/share-settings")
async def referral_share_settings_get(request: Request):
    """V551 — réglages de partage de l'appelant (clé = identité serveur)."""
    _c = await _coach_strict(request)
    return await _reponse_reglages(_c["cle"])


@router.put("/share-settings")
async def referral_share_settings_put(request: Request):
    """V551 — `{default_message?, share_image_url?}` ; tout autre champ ignoré."""
    _c = await _coach_strict(request)
    _b = await _corps(request)
    _maj = {}
    if "default_message" in _b:
        try:
            _maj["default_message"] = E.valider_message(_b.get("default_message"), "default_message")
        except E.InvitationInvalide as _err:
            raise HTTPException(status_code=422, detail=str(_err))
    if "share_image_url" in _b:
        _u = _b.get("share_image_url")
        if _u is not None and not E.url_image_partage_valide(_u):
            raise HTTPException(status_code=400, detail="Image refusée : utilise l'envoi d'image Afroboost.")
        _maj["share_image_url"] = _u
    if _maj:
        await _ecrire_reglages(_c["cle"], _c["email"], _maj)
    return await _reponse_reglages(_c["cle"])


@router.post("/share-settings/image")
async def referral_share_settings_image(request: Request, file: UploadFile = File(...)):
    """V551 — image de partage : JWT strict, JPEG/PNG/WebP (type déclaré +
    signature + extension concordants), <= 3 Mo, nom serveur (uuid). Stockage
    = celui de `/api/files/{id}/{nom}` (`_v413_enregistrer_media`), SANS passer
    par `/coach/upload-asset` (qui croit X-User-Email)."""
    _c = await _coach_strict(request)
    _type = str(getattr(file, "content_type", "") or "").split(";")[0].strip().lower()
    _nom_client = str(getattr(file, "filename", "") or "")
    _ext = _nom_client.rsplit(".", 1)[-1].strip().lower() if "." in _nom_client else ""
    if _type not in IMAGE_TYPES or _ext not in IMAGE_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Formats acceptés : JPG, PNG ou WebP.")
    _octets = await file.read(IMAGE_MAX_OCTETS + 1)
    if len(_octets) > IMAGE_MAX_OCTETS:
        raise HTTPException(status_code=413, detail="Image trop lourde (3 Mo maximum).")
    _reel = _type_reel_image(_octets)
    if not _reel or _reel != IMAGE_TYPES[_type] or _reel != IMAGE_EXTENSIONS[_ext]:
        raise HTTPException(status_code=415, detail="Ce fichier n'est pas une image JPG, PNG ou WebP valide.")
    from api.server import _v413_enregistrer_media
    _file_id = uuid.uuid4().hex[:16]
    _filename = "share_%s.%s" % (uuid.uuid4().hex[:12], _reel)
    _mime = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}[_reel]
    try:
        await _v413_enregistrer_media(_file_id, _filename, _octets, {
            "file_id": _file_id, "filename": _filename, "original_name": _filename,
            "content_type": _mime, "asset_type": "referral_share",
            "coach_email": _c["email"], "created_at": datetime.utcnow(),
        })
    except Exception as _err:  # noqa: BLE001
        logger.error("%s image de partage non enregistrée (%s)", PREFIXE, type(_err).__name__)
        raise HTTPException(status_code=503, detail="Image non enregistrée, réessaie dans un instant.")
    _url = "/api/files/%s/%s" % (_file_id, _filename)
    await _ecrire_reglages(_c["cle"], _c["email"], {"share_image_url": _url})
    logger.info("%s image de partage enregistrée (%s, %d o)", PREFIXE, _file_id, len(_octets))
    return JSONResponse(status_code=201, content=await _reponse_reglages(_c["cle"]))


# ═══════════════════════════════════════════════════════════════════════════
# Routes — publiques (l'ami)
# ═══════════════════════════════════════════════════════════════════════════
async def _occurrences_du_pass(pass_doc) -> list:
    """V539 — les prochaines occurrences du cours du pass (la même liste que
    celle proposée au parrain à la création). Vide si le cours n'est plus
    disponible : l'écran affiche alors la séance actuelle, sans promesse."""
    try:
        _c = await db["courses"].find_one({"id": (pass_doc or {}).get("course_id")}, {"_id": 0})
        if not _c or _c.get("archived") is True or _c.get("visible") is False:
            return []
        return _occurrences(_c)
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s occurrences indisponibles (%s)", PREFIXE, type(_err).__name__)
        return []


async def _pass_par_token(share_token: str):
    _t = str(share_token or "").strip()
    if not _t or len(_t) > 64:
        raise HTTPException(status_code=404, detail="Invitation introuvable")
    _p = await db[COLL_PASSES].find_one({"share_token": _t}, {"_id": 0})
    if not _p:
        raise HTTPException(status_code=404, detail="Invitation introuvable")
    return _p


@router.get("/pass/{share_token}")
async def referral_pass_public(share_token: str):
    """Public, SANS PII. Pose `opened_at` si null (-> `waiting`)."""
    await _exiger_actif()
    _p = await _pass_par_token(share_token)
    _now = _maintenant()
    _s = await _statut_reel(_p, _now)
    if not _p.get("opened_at") and _s in E.ETATS_ACTIFS:
        _maj = {"opened_at": _iso(_now)}
        if _s == E.LOCKED:
            _maj["status"] = E.transition(E.LOCKED, E.WAITING)
            _s = E.WAITING
        await _evenement(_p["id"], "link_opened", None, _maj)
        _p.update(_maj)
        # V534b : la `version` rendue est celle d'APRÈS l'écriture (relue).
        _p = await db[COLL_PASSES].find_one({"id": _p["id"]}, {"_id": 0}) or _p
    # V539 : les autres séances du MÊME cours, pour que l'ami puisse en choisir
    # une autre sans quitter la page. Liste du serveur, jamais une date libre.
    _dto = E.dto_public(_p, _s, _now, await _catalogue_du_pass(_p, {}))
    _dto["occurrences"] = await _occurrences_du_pass(_p)
    if E.chaine_du_pass(_p).get("parent_pass_id") or E.campagne_du_pass(_p):
        # V556 : liée à la séance de son parrain (sa place y est) ;
        # PAR-1 : une campagne vaut pour SA séance (figée par le coach).
        _dto["occurrences"] = []
    # V556 : faut-il inviter avant de s'inscrire ? et où en est ce visiteur ?
    _dto["chain_required"] = E.chaine_requise(_p, _s, await _chaine_active())
    _dto["chain"] = E.dto_chaine_public(_p)
    _dto["invitation_type"] = E.type_invitation(_p)   # UX-P4 : badge « Essai gratuit » / « Pass Duo »
    return _dto


async def _liberer_enfant_refuse(share_token, request, raison, code_http=409) -> bool:
    """PAR-1 (A1) — le visiteur refusé (identité) avait préparé/partagé
    l'UNIQUE invitation enfant du pass : sans libération, le lien resterait
    bloqué pour le vrai ami (« termine sur l'appareil qui a partagé »).

    Conditions, TOUTES requises : l'enfant existe ; la `X-Chain-Key` du join est
    la SIENNE (même appareil) ; son parrain est encore en attente ; ni invité
    ni petit-enfant ; le pass parent n'a pas d'invité. Effet : l'enfant passe
    `cancelled` (motif dans `events`, jamais supprimé ; `chain.parent_pass_id`
    renommé en `chain.released_parent_pass_id` pour libérer l'index unique) et
    le parent perd `child_pass_id / child_created_at / shared_at /
    share_channel` — écritures conditionnelles."""
    _p = await db[COLL_PASSES].find_one({"share_token": str(share_token or "").strip()[:64]}, {"_id": 0})
    if not _p or _p.get("invitee"):
        return False
    _enf = await _enfant_de(_p)
    if not _enf or _enf.get("invitee") or not E.parrain_en_attente(_enf) \
            or E.chaine_du_pass(_enf).get("child_pass_id") or not _cle_chaine_valide(request, _enf):
        return False
    if await _enfant_de(_enf):
        return False
    # V558 : « déjà client » (essai déjà utilisé / détenu, abonné actif) n'est pas
    # un abus — l'invitation DÉJÀ ENVOYÉE à son ami reste valable (la chaîne ne
    # casse pas ; son ami garde SON essai s'il y a droit).
    if not E.refus_libere_enfant(code_http, raison, E.partage_chaine(_enf)["shared"]):
        return False
    _now = _iso()
    _r = await db[COLL_PASSES].update_one(
        {"id": _enf["id"], "invitee": None, "chain.parent_pass_id": _p["id"],
         "chain.child_pass_id": {"$exists": False}, "status": {"$in": list(E.ETATS_OUVERTS_AU_JOIN)}},
        {"$set": {"status": E.CANCELLED, "cancel_reason": "chain_released:%s" % raison,
                  "chain.released_parent_pass_id": _p["id"], "chain.released_at": _now, "updated_at": _now},
         "$unset": {"chain.parent_pass_id": ""},
         "$push": {"events": {"at": _now, "type": "cancelled", "detail": "chain_released:%s" % raison}},
         "$inc": {"version": 1}})
    if not getattr(_r, "modified_count", 1):
        return False
    await db[COLL_PASSES].update_one(
        {"id": _p["id"], "invitee": None, "chain.child_pass_id": _enf["id"]},
        {"$unset": {"chain.child_pass_id": "", "chain.child_created_at": "", "chain.shared_at": "",
                    "chain.share_channel": ""},
         "$set": {"updated_at": _now},
         "$push": {"events": {"at": _now, "type": E.EVENEMENT_CHAINE_LIBEREE, "detail": raison}}})
    logger.info("%s place d'enfant %s libérée sous %s (%s)", PREFIXE, _enf["id"][:8], _p["id"][:8], raison)
    return True


def _liberer_si_refus_identite(fn):
    """PAR-1 (A1) — enveloppe du join : un refus d'IDENTITÉ définitif libère la
    place d'enfant que CET appareil avait prise (`_liberer_enfant_refuse`). Le
    refus d'origine reste la réponse ; le corps du join n'est pas modifié."""
    import functools

    @functools.wraps(fn)
    async def _enveloppe(share_token: str, request: Request):
        try:
            return await fn(share_token, request)
        except HTTPException as _e:
            _raison = (getattr(_e, "headers", None) or {}).get("X-Refus-Raison")
            if E.refus_identite_definitif(_e.status_code, _raison):
                try:
                    await _liberer_enfant_refuse(share_token, request, _raison, _e.status_code)
                except Exception as _err:  # noqa: BLE001
                    logger.warning("%s place d'enfant non libérée (%s)", PREFIXE, type(_err).__name__)
            raise
    return _enveloppe


@router.post("/pass/{share_token}/join")
@_liberer_si_refus_identite
async def referral_join(share_token: str, request: Request):
    """L'ami rejoint — l'ordre du contrat §6, et pas un autre :
    1 drapeau/pass/état/occurrence ; 2 normalisation + auto-parrainage ;
    3 idempotence ; 4 index filleul/occurrence ; 5 ESSAI-4 -> ESSAI-1 ->
    `_process_successful_payment(free)` ; 6 réservation de l'ami (rollback
    sinon) ; 7 place du parrain ; 8 notifications ; 9 M2-A `parrainage`."""
    await _exiger_actif()
    _exiger_debit(request, DEBIT_PREFIXE_JOIN)
    _p = await _pass_par_token(share_token)
    _now = _maintenant()
    _s = await _statut_reel(_p, _now)
    _b = await _corps(request)

    # ── 2. normalisation, auto-parrainage ──────────────────────────────────
    from api.routes.shared import essai6_normaliser_tel
    _email = E.normaliser_email(_b.get("email"))
    _tel_brut = str(_b.get("whatsapp") or "").strip()
    _tel = essai6_normaliser_tel(_tel_brut)
    _nom = str(_b.get("name") or "").strip()[:80]

    # ── 1. état ouvert / occurrence future ─────────────────────────────────
    _code_http, _raison = E.peut_rejoindre(_p, _email, _now)
    if _code_http == 410:
        raise HTTPException(status_code=410, detail="Cette invitation n'est plus valable.")
    if _email and _raison == "idempotent":
        await _relier_enfant_si_besoin(_p)       # V556 : reprise d'une liaison manquée
        return await _reponse_join(_p, _now)
    if _code_http == 409:
        raise _refus(409, E.REFUS_PASS_FERME, "Ce Pass Duo a déjà un invité.")

    if not _email or "@" not in _email or not _nom:
        raise HTTPException(status_code=400, detail="Prénom et e-mail requis.")
    if _b.get("consent_reservation") is not True or _b.get("terms_accepted") is not True:
        raise HTTPException(status_code=400,
                            detail="Merci d'accepter la réservation et les conditions de participation.")
    # V558 — L'ESSAI EST UNE FOIS PAR PERSONNE, À VIE : ESSAI-1 verrouille l'e-mail
    # ET le numéro. Une nouvelle adresse sans numéro contournerait le verrou.
    if not _tel:
        raise _refus(400, "whatsapp_requis", "Indique ton numéro WhatsApp : il sert à réserver ta place.")
    _ok, _motif = E.invite_autorise(_p, _email, _tel)
    if not _ok:
        raise _refus(409, E.REFUS_AUTO_PARRAINAGE, "Tu ne peux pas être ton propre invité.")
    # PAR-1 : le coach d'une campagne ne s'offre pas son propre essai.
    if E.campagne_du_pass(_p) and _email in await _proprietaires_campagne(_p):
        raise _refus(409, E.REFUS_AUTO_PARRAINAGE, "Tu ne peux pas être ton propre invité.")
    # V556 — LA RÈGLE BOULE DE NEIGE : pas d'inscription tant que l'invitation
    # enfant n'a pas été partagée (action déclenchée ; jamais « WhatsApp a
    # confirmé l'envoi », ce qu'un navigateur ne peut pas savoir).
    if await _chaine_active():
        if not E.chaine_partagee(_p):
            raise _refus(409, E.REFUS_INVITATION_REQUISE,
                         "Invite d'abord un ami pour débloquer ton essai gratuit.")
        # V556 : c'est CELUI qui a partagé qui s'inscrit (clé de l'appareil) —
        # un tiers qui a le même lien ne franchit pas la porte à sa place.
        if not _cle_chaine_valide(request, await _enfant_de(_p)):
            raise _refus(403, E.REFUS_AUTRE_APPAREIL,
                         "Termine ton inscription sur l'appareil qui a partagé ton invitation.")
    # V556 — ANTI-BOUCLE : ni un maillon amont (parrains, filleuls), ni l'ami
    # qu'on vient soi-même d'inviter. (Le verrou ESSAI-1 reste la garde de fond.)
    if E.identite_correspond(_email, _tel, await _identites_de_la_chaine(_p)):
        raise _refus(409, E.REFUS_AUTO_PARRAINAGE, "Tu ne peux pas être ton propre invité.")
    # PAR-1 (audit P1-B) : une campagne n'octroie pas plus d'essais que son plafond
    # (une seule séance) — vérifié AVANT la pose de l'invité et l'octroi ESSAI.
    if E.campagne_du_pass(_p):
        _camp = await _campagne_par_id(E.campagne_du_pass(_p))
        if _camp and await _campagne_complete_essais(_camp):
            raise _refus(409, "campagne_complete", "Cette invitation est complète : plus de place d'essai.")

    _course = await db["courses"].find_one({"id": _p.get("course_id")}, {"_id": 0})
    if not _course or _course.get("archived") is True:
        raise HTTPException(status_code=410, detail="Ce cours n'est plus disponible.")

    # ── 3bis. V534b : `offer_id` facultatif = changement INVITEE avant l'octroi
    _oid_demande = str(_b.get("offer_id") or "").strip()
    if _oid_demande and _oid_demande != str(_p.get("offer_id") or ""):
        if E.campagne_du_pass(_p):          # PAR-1 : offre fixée par la campagne
            raise _refus(409, E.REFUS_PASS_NON_MODIFIABLE, "L'offre de cette invitation est fixée par le coach.")
        _p = await _changer_offre(_p, _oid_demande, E.version_pass(_p), "invitee")
    # L'octroi utilise L'OFFRE DU PASS, relue et revalidée (jamais un id du front).
    # PAR-1 : porte unique (`_offre_autorisee` inchangé pour un pass sans campagne).
    _offre = await _offre_du_pass(_p, _course)

    # ── 4. index partiel filleul / occurrence (avant tout octroi) ──────────
    _invitee = {"email_norm": _email, "name": _nom, "whatsapp_norm": _tel or None,
                "consent_reservation_at": _iso(_now),
                "marketing_consent": _b.get("marketing_consent") is True}
    # V534b : la pose de l'invité est gardée par la `version` du pass — un
    # changement d'offre glissé entre la lecture et l'écriture ne peut pas
    # faire octroyer une offre que le pass ne porte plus. Un seul rejeu.
    for _tentative in (1, 2):
        try:
            _r = await db[COLL_PASSES].update_one(
                dict(_filtre_version(_p["id"], E.version_pass(_p)), invitee=None),
                {"$set": {"invitee": _invitee, "updated_at": _iso(_now)}, "$inc": {"version": 1}})
        except Exception as _err:  # noqa: BLE001
            if _est_doublon(_err):
                raise _refus(409, E.REFUS_DEJA_FILLEUL,
                             "Tu es déjà l'invité d'un autre Pass Duo pour cette séance.")
            logger.error("%s pose de l'invité impossible (%s)", PREFIXE, type(_err).__name__)
            raise HTTPException(status_code=503, detail="Inscription impossible pour le moment.")
        if getattr(_r, "modified_count", 1):
            break
        _p = await _pass_par_token(share_token)
        if E.normaliser_email((_p.get("invitee") or {}).get("email_norm")) == _email:
            return await _reponse_join(_p, _now)
        if _p.get("invitee"):
            raise _refus(409, E.REFUS_PASS_FERME, "Ce Pass Duo a déjà un invité.")
        if _tentative == 2:
            raise _refus(409, E.REFUS_CONFLIT_VERSION, "Ce Pass Duo vient d'être modifié : réessaie.")
        _offre = await _offre_du_pass(_p, _course)   # l'offre a pu changer
    _p["invitee"] = _invitee

    async def _rouvrir():
        await db[COLL_PASSES].update_one({"id": _p["id"]}, {"$set": {"invitee": None},
                                                            "$inc": {"version": 1}})

    # ── 5. moteur d'essai EXISTANT : ESSAI-4 -> ESSAI-1 -> octroi ──────────
    # (`_octroyer_essai` = LE chemin, partagé avec le changement d'offre.)
    try:
        _access_code, _attrib = await _octroyer_essai(_p, _offre, _email, _nom, _tel_brut,
                                                      _b.get("attribution"))
    except Exception:
        await _rouvrir()
        raise

    # ── 6. réservation de l'ami (transaction si disponible, rollback sinon) ──
    try:
        _resa_ami = await _reserver_ami(
            _p, _course, _access_code, _email, _nom, _tel_brut,
            {"status": E.transition(_s, E.FRIEND_REGISTERED), "attribution": _attrib},
            {"events": {"at": _iso(), "type": "friend_registered", "detail": None}})
    except Exception as _err:  # noqa: BLE001
        await _rollback_filleul(_p, _email, _tel_brut, _access_code)
        _detail = getattr(_err, "detail", None) if isinstance(_err, HTTPException) else None
        logger.error("%s réservation de l'ami échouée (%s) — octroi annulé", PREFIXE,
                     _detail or type(_err).__name__)
        raise HTTPException(status_code=500,
                            detail="L'inscription a échoué, rien n'a été enregistré. Réessaie dans un instant.")
    _p = await db[COLL_PASSES].find_one({"id": _p["id"]}, {"_id": 0}) or _p
    _sub_ami = await db["subscriptions"].find_one({"code": _access_code}, {"_id": 0})
    await _notifier_reservation(_resa_ami, _sub_ami)

    # ── 7. place du parrain ; 8. notifications ─────────────────────────────
    _p = await _debloquer_ou_bloquer(_p, _course)
    # V556 — le nouvel inscrit devient le parrain de SON invitation enfant.
    try:
        await _lier_enfant(_p, _email, _nom, _tel, _access_code)
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s invitation enfant non liée (%s)", PREFIXE, type(_err).__name__)
    if _p.get("status") == E.FRIEND_REGISTERED and _p.get("blocked_reason") != E.BLOCAGE_PARRAIN_NON_INSCRIT:
        _sp = _p.get("sponsor") or {}
        await _push_parrain(_sp.get("email_norm"), "Ton ami est inscrit",
                            "%s a rejoint ton Pass Duo. Recharge ton abonnement pour confirmer ta place."
                            % (E.prenom(_nom) or "Ton ami"),
                            {"type": "pass_duo_friend_registered", "pass_id": _p["id"], "url": "/parrainage"})
    return await _reponse_join(_p, _now)


async def _reponse_join(pass_doc, now) -> dict:
    _resas = await _reservations_du_pass(pass_doc)
    _s = await _statut_reel(pass_doc, now, _resas)
    return {
        "status": _s,
        "status_label": E.LIBELLES.get(_s, _s),
        "tickets": E.tickets_du_pass(pass_doc, _resas, _frontend_url()),
        "blocked_reason": pass_doc.get("blocked_reason"),
        # V551 : même filtre que la page publique (jamais une partie locale d'e-mail).
        "sponsor_first_name": E.nom_parrain_affichable(pass_doc),
        "course": {k: v for k, v in E.dto_course(pass_doc).items() if k != "id"},
        "occurrence": pass_doc.get("occurrence"),
        # V534b : l'avantage reçu (OffreDTO du pass) et la version courante.
        "offer": E.offre_du_pass(pass_doc),
        "version": E.version_pass(pass_doc),
    }


# ═══════════════════════════════════════════════════════════════════════════
# V556 — PARRAINAGE V3 : LA CHAÎNE « boule de neige »
# ═══════════════════════════════════════════════════════════════════════════
# Règles dans `referral_engine` (section V556). Ici : les lectures/écritures.
# L'invitation enfant est un pass ORDINAIRE (mêmes états, même join, même
# essai unique, mêmes index) : il n'y a pas de second moteur de parrainage.
CHAINE_REMONTEE_MAX = 12        # garde-fou de boucle sur `chain.parent_pass_id`


async def _enfant_de(pass_doc):
    """L'invitation enfant d'un pass (au plus UNE : index unique), ou None."""
    try:
        return await db[COLL_PASSES].find_one(
            {"chain.parent_pass_id": (pass_doc or {}).get("id")}, {"_id": 0})
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s invitation enfant illisible (%s)", PREFIXE, type(_err).__name__)
        return None


async def _descendance(pass_doc) -> list:
    """Les invitations AVAL (enfant, petit-enfant...), une par niveau, bornée."""
    _sortie, _vus, _cur = [], {(pass_doc or {}).get("id")}, pass_doc
    for _ in range(CHAINE_REMONTEE_MAX):
        _cur = await _enfant_de(_cur)
        if not _cur or _cur.get("id") in _vus:
            break
        _vus.add(_cur.get("id"))
        _sortie.append(_cur)
    return _sortie


async def _parent_de(pass_doc):
    _pid = E.chaine_du_pass(pass_doc).get("parent_pass_id")
    if not _pid:
        return None
    try:
        return await db[COLL_PASSES].find_one({"id": _pid}, {"_id": 0})
    except Exception:  # noqa: BLE001
        return None


async def _ancetres(pass_doc) -> list:
    """Les pass AMONT (parent, grand-parent...), du plus proche au plus loin."""
    _sortie, _vus, _cur = [], {(pass_doc or {}).get("id")}, pass_doc
    for _ in range(CHAINE_REMONTEE_MAX):
        _cur = await _parent_de(_cur)
        if not _cur or _cur.get("id") in _vus:
            break
        _vus.add(_cur.get("id"))
        _sortie.append(_cur)
    return _sortie


async def _maillons_en_attente(pass_doc) -> int:
    """Combien de maillons consécutifs, depuis ce pass, ont un parrain PAS
    encore inscrit ? (Borne la chaîne fantôme d'un script qui n'inscrit jamais.)"""
    _n, _cur = 0, pass_doc
    _amont = await _ancetres(pass_doc)
    for _cur in [pass_doc] + _amont:
        if not E.parrain_en_attente(_cur):
            break
        _n += 1
    return _n


async def _identites_de_la_chaine(pass_doc) -> list:
    """[(e-mail, téléphone)] de toutes les personnes de la chaîne AMONT
    (parrains et filleuls) + l'ami déjà inscrit sur l'invitation ENFANT de ce
    pass. Lu côté serveur uniquement : jamais renvoyé au navigateur."""
    _sortie = []
    for _a in await _ancetres(pass_doc):
        for _role in ("sponsor", "invitee"):
            _x = _a.get(_role) or {}
            if _x:
                _sortie.append((_x.get("email_norm"), _x.get("whatsapp_norm")))
    _enf = await _enfant_de(pass_doc)
    if _enf and _enf.get("invitee"):
        _sortie.append((_enf["invitee"].get("email_norm"), _enf["invitee"].get("whatsapp_norm")))
    return _sortie


async def _place_du_parrain_chaine(pass_doc):
    """La réservation de filleul de A sur le pass PARENT, si c'est bien lui et
    bien cette séance ; sinon None (le chemin ordinaire reprend la main)."""
    _parent = await _parent_de(pass_doc)
    if not _parent:
        return None
    _sp = pass_doc.get("sponsor") or {}
    _inv = _parent.get("invitee") or {}
    _rid = (_parent.get("reservations") or {}).get("invitee_id")
    # V558 : quand l'enfant porte SA séance (choisie pour l'ami), la place du
    # parrain reste celle qu'il a déjà sur le parent — jamais une seconde
    # réservation, jamais un second débit, jamais un nouvel essai pour lui.
    _meme_seance = str(_parent.get("occurrence") or "") == str(pass_doc.get("occurrence") or "")
    if (not _rid or not (_meme_seance or E.seance_choisie(pass_doc))
            or E.normaliser_email(_inv.get("email_norm")) != E.normaliser_email(_sp.get("email_norm"))):
        return None
    try:
        _r = await db["reservations"].find_one({"id": _rid, "status": {"$ne": "cancelled"}}, {"_id": 0})
    except Exception:  # noqa: BLE001
        _r = None
    if _r:
        _r["_rattachee"] = True          # jamais persisté : « aucune notification neuve »
    return _r


async def _synchroniser_seance_enfant(enfant, occurrence, entree) -> None:
    """La séance du parent a changé : l'invitation enfant (pas encore
    rejointe) la suit — même jeton, sa carte change d'URL (empreinte)."""
    try:
        await db[COLL_PASSES].update_one(
            {"id": enfant["id"], "invitee": None},
            {"$set": {"occurrence": occurrence, "expires_at": occurrence, "updated_at": _iso()},
             "$push": {"events": {"at": _iso(), "type": E.EVENEMENT_SEANCE, "detail": dict(entree)}},
             "$inc": {"version": 1}})
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s séance de l'invitation enfant non suivie (%s)", PREFIXE, type(_err).__name__)


async def _lier_enfant(parent, email, nom, tel_norm, access_code) -> None:
    """Le filleul du parent vient de s'inscrire : il devient le VRAI parrain
    de son invitation enfant. Si son ami s'y est déjà inscrit, le duo se
    débloque maintenant (sa place = celle qu'il vient d'obtenir)."""
    _enf = await _enfant_de(parent)
    if not _enf or not E.parrain_en_attente(_enf):
        return
    _now = _iso()
    try:
        _r = await db[COLL_PASSES].update_one(
            {"id": _enf["id"], "sponsor.email_norm": E.cle_parrain_en_attente(parent["id"])},
            {"$set": {"sponsor.email_norm": E.normaliser_email(email),
                      "sponsor.name": str(nom or "").strip()[:80],
                      "sponsor.whatsapp_norm": tel_norm or None,
                      "sponsor.subscription_code": access_code,
                      "sponsor.terms_accepted": True,
                      "sponsor.pending": False, "sponsor.bound_at": _now, "updated_at": _now},
             "$push": {"events": {"at": _now, "type": E.EVENEMENT_PARRAIN_LIE, "detail": None}},
             "$inc": {"version": 1}})
    except Exception as _err:  # noqa: BLE001
        # Doublon (A est déjà parrain d'un pass actif sur cette séance) : on
        # laisse l'enfant en attente plutôt que d'écraser un autre pass.
        logger.warning("%s parrain de l'invitation enfant non lié (%s)", PREFIXE, type(_err).__name__)
        return
    if not getattr(_r, "modified_count", 1):
        return
    try:
        await db[COLL_INVITATIONS].update_many(
            {"pass_id": _enf["id"], "sponsor_email_norm": E.cle_parrain_en_attente(parent["id"])},
            {"$set": {"sponsor_email_norm": E.normaliser_email(email)}})
    except Exception:  # noqa: BLE001
        pass
    _enf = await db[COLL_PASSES].find_one({"id": _enf["id"]}, {"_id": 0}) or _enf
    if _enf.get("status") == E.FRIEND_REGISTERED:
        _course = await db["courses"].find_one({"id": _enf.get("course_id")}, {"_id": 0})
        if _course:
            await _debloquer_ou_bloquer(_enf, _course)


async def _nouvelle_version_apercu(pass_id):
    """+1 sur `preview_version` : la PROCHAINE share_url (et la carte) change
    d'adresse. Rien d'autre ne bouge : ni jeton, ni filleul, ni crédit."""
    try:
        await db[COLL_PASSES].update_one({"id": pass_id}, {"$inc": {"preview_version": 1},
                                                          "$set": {"updated_at": _iso()}})
        return await db[COLL_PASSES].find_one({"id": pass_id}, {"_id": 0})
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s version d'aperçu non incrémentée (%s)", PREFIXE, type(_err).__name__)
        return None


async def _bilan_apercu(pass_doc) -> dict:
    """Contrôle d'aperçu du serveur (page OG + carte, cache chauffé)."""
    try:
        from api.server import _v556_bilan_apercu
        return await _v556_bilan_apercu(pass_doc)
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s contrôle d'aperçu indisponible (%s)", PREFIXE, type(_err).__name__)
        return {"ok": False, "fallback": True, "checks": {}}


async def _exiger_campagne_vivante(pass_doc) -> None:
    """PAR-1 (audit P2) — un pass de campagne dont la campagne ne peut plus
    octroyer (archivée, offre retirée...) ne fabrique ni ne partage d'enfant
    voué au 410. Un pass sans campagne : aucune lecture, rien ne change."""
    if not E.campagne_du_pass(pass_doc):
        return
    if not await _offre_de_campagne(await _campagne_par_id(E.campagne_du_pass(pass_doc)),
                                    (pass_doc or {}).get("offer_id")):
        raise HTTPException(status_code=410, detail="Cette invitation n'est plus valable.")


def _cle_chaine_valide(request, enfant) -> bool:
    """`X-Chain-Key` == la clé rendue à la création de l'invitation enfant
    (comparaison à temps constant sur l'empreinte ; jamais stockée en clair)."""
    import hmac
    try:
        _cle = (request.headers.get("x-chain-key", "") or "").strip()
    except Exception:  # noqa: BLE001
        _cle = ""
    _attendu = str(E.chaine_du_pass(enfant).get("edit_key_hash") or "")
    return bool(_cle and _attendu and hmac.compare_digest(_hache_cle(_cle), _attendu))


async def _journal_parent(pass_id, type_, detail, maj) -> None:
    """Événement de chaîne sur le parent SANS toucher à `version` : créer ou
    partager son invitation ne doit pas faire échouer (409) un changement de
    séance ou d'offre que la page tient avec la version qu'elle a lue."""
    _now = _iso()
    try:
        await db[COLL_PASSES].update_one(
            {"id": pass_id},
            {"$set": dict(maj or {}, updated_at=_now),
             "$push": {"events": {"at": _now, "type": type_, "detail": detail}}})
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s événement %s non journalisé (%s)", PREFIXE, type_, type(_err).__name__)


async def _relier_enfant_si_besoin(parent) -> None:
    """Retente la liaison parrain de chaîne (idempotente) pour un parent déjà rejoint."""
    _inv = (parent or {}).get("invitee") or {}
    if not _inv or not parent.get("invitee_access_code"):
        return
    try:
        await _lier_enfant(parent, _inv.get("email_norm"), _inv.get("name"),
                           _inv.get("whatsapp_norm"), parent.get("invitee_access_code"))
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s liaison de chaîne non reprise (%s)", PREFIXE, type(_err).__name__)


async def _suivre_place_enfant(parent_id, ancien_rid, resa, nouveau_code) -> None:
    """Le filleul du parent a changé d'offre après son join : sa réservation et
    son code ont été remplacés. Son invitation enfant pointe vers la nouvelle."""
    if not ancien_rid or not resa:
        return
    try:
        await db[COLL_PASSES].update_one(
            {"chain.parent_pass_id": parent_id, "reservations.sponsor_id": ancien_rid},
            {"$set": {"reservations.sponsor_id": resa.get("id"),
                      "reservations.sponsor_code": resa.get("reservationCode"), "updated_at": _iso()}})
        await db[COLL_PASSES].update_one(
            {"chain.parent_pass_id": parent_id, "sponsor.pending": False},
            {"$set": {"sponsor.subscription_code": nouveau_code}})
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s place de l'invitation enfant non suivie (%s)", PREFIXE, type(_err).__name__)


def _hache_cle(cle) -> str:
    import hashlib
    return hashlib.sha256(str(cle or "").encode("utf-8")).hexdigest()


async def _reponse_chaine(parent, enfant, code=200, edit_key=None, apercu=True):
    _corps_rep = {"child": E.dto_enfant(enfant, _frontend_url()),
                  "shared": E.chaine_partagee(parent)}
    if apercu:
        _corps_rep["preview"] = await _bilan_apercu(enfant)
    if edit_key:
        _corps_rep["edit_key"] = edit_key
    return JSONResponse(status_code=code, content=_corps_rep)


async def _parent_ouvert(share_token):
    """Le pass parent d'une requête de chaîne : 404 inconnu, 410 fermé."""
    _p = await _pass_par_token(share_token)
    _s = await _statut_reel(_p)
    if _s in (E.EXPIRED, E.CANCELLED):
        raise HTTPException(status_code=410, detail="Cette invitation n'est plus valable.")
    return _p, _s


def _champs_invitation_enfant(corps, avec_photo=False) -> dict:
    """Seuls `display_name` et `message` (+ `photo_url` au PATCH, UX-P1, validée
    par `valider_photo_url`) : jamais un e-mail, un id."""
    _cles = ("display_name", "message", "photo_url") if avec_photo else ("display_name", "message")
    _sous = {k: corps.get(k) for k in _cles if k in (corps or {})}
    try:
        return E.valider_invitation(_sous)
    except E.InvitationInvalide as _err:
        raise HTTPException(status_code=422, detail=str(_err))


# ═══════════════════════════════════════════════════════════════════════════
# V558 — WIZARD « INVITATION & PARRAINAGE » : l'offre et LA SÉANCE DE L'AMI
# ═══════════════════════════════════════════════════════════════════════════
# Chaque maillon choisit la séance qu'IL offre au suivant : l'enfant porte son
# propre `course_id` / `occurrence` (`chain.seance_choisie`), le parent garde la
# sienne. Les séances proposées viennent TOUJOURS du serveur (jamais une date ou
# un cours tapés par le navigateur) : futures, cours publics, du MÊME
# propriétaire, compatibles avec l'offre du pass. Le type (`chain.kind`) est
# relu contre `types_offrables` : Parrainage / Affiliation n'existent que si un
# programme réel est configuré (`referral_programs`), sinon ils sont refusés.
COLL_PROGRAMMES = "referral_programs"
DEBIT_PREFIXE_CHAINE_OPTIONS = "duo_chain_o:"   # V558 : lecture des options du Wizard
COURS_CANDIDATS_MAX = 60


async def _proprietaire_chaine(pass_doc) -> str:
    """La clé du propriétaire de la chaîne ("" = plateforme) : celle de la
    campagne racine si le pass en vient, sinon celle du cours du pass."""
    _cid = E.campagne_du_pass(pass_doc)
    if _cid:
        _camp = await _campagne_par_id(_cid)
        return E._proprietaire((_camp or {}).get("coach_id"))
    try:
        _co = await db["courses"].find_one({"id": (pass_doc or {}).get("course_id")}, {"_id": 0, "coach_id": 1})
    except Exception:  # noqa: BLE001
        _co = None
    return E._proprietaire((_co or {}).get("coach_id") if _co else (pass_doc or {}).get("coach_id"))


async def _programmes_actifs(proprietaire) -> list:
    """Les programmes Parrainage / Affiliation ACTIFS de ce propriétaire (lecture
    seule). Aucun document -> [] : les cartes correspondantes n'apparaissent pas."""
    try:
        return await db[COLL_PROGRAMMES].find(
            {"coach_id": str(proprietaire or ""), "status": "active"}, {"_id": 0}).to_list(10)
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s programmes illisibles (%s)", PREFIXE, type(_err).__name__)
        return []


async def _cours_offrables(pass_doc) -> list:
    """Les cours dont une séance peut être offerte au suivant (documents complets)."""
    _p = pass_doc or {}
    _proprio = await _proprietaire_chaine(_p)
    _cid = E.campagne_du_pass(_p)
    if _cid:
        _camp = await _campagne_par_id(_cid)
        _offre = await _offre_de_campagne(_camp, _p.get("offer_id")) if _camp else None
        if not _offre:
            return []
        _ids = IC.cours_lies(_offre) or [str(_p.get("course_id") or "")]
        if str(_p.get("course_id") or "") not in _ids:
            _ids.append(str(_p.get("course_id") or ""))
        _q = {"id": {"$in": [i for i in _ids if i][:COURS_CANDIDATS_MAX]}}
    else:
        _oid = str(_p.get("offer_id") or "").strip()
        if not _oid:
            return []
        # l'offre est filtrée plus bas, en mémoire (bornée à COURS_CANDIDATS_MAX)
        _q = {"duo_enabled": True, "archived": {"$ne": True}}
    try:
        _rows = await db["courses"].find(_q, {"_id": 0}).to_list(COURS_CANDIDATS_MAX)
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s cours offrables illisibles (%s)", PREFIXE, type(_err).__name__)
        return []
    _sortie = []
    for _co in _rows:
        # Coach A ne propose JAMAIS une séance du coach B (propriété du cours).
        # Le cours du pass lui-même reste offrable : c'est déjà celui de la chaîne.
        _sien = _co.get("id") == _p.get("course_id")
        if not IC.cours_public(_co) or (not _sien and E._proprietaire(_co.get("coach_id")) != _proprio):
            continue
        if not _cid and _oid not in [str(i).strip() for i in (_co.get("duo_offer_ids") or [])]:
            continue
        _sortie.append(_co)
    _sortie.sort(key=lambda c: (0 if c.get("id") == _p.get("course_id") else 1, str(c.get("name") or "")))
    return _sortie


async def _seances_offrables(pass_doc) -> list:
    """`[{course_id, name, location, time, occurrences[]}]` — futures uniquement."""
    _sortie = []
    for _co in await _cours_offrables(pass_doc):
        try:
            _occ = [o for o in _occurrences(_co) if not E.est_passee(o, _maintenant())]
        except Exception:  # noqa: BLE001
            _occ = []
        if _occ:
            _sortie.append(E.dto_seance_offrable(_co, _occ))
    return _sortie


async def _valider_seance_enfant(pass_doc, course_id, occurrence) -> tuple:
    """(cours, occurrence) relus côté serveur, sinon 400 `seance_non_autorisee`
    (cours hors liste : autre coach, caché, incompatible) ou `seance_indisponible`
    (date absente de la liste du serveur, passée, pleine au moment du choix)."""
    _cid = str(course_id or "").strip()
    _cours = next((c for c in await _cours_offrables(pass_doc) if c.get("id") == _cid), None)
    if not _cours:
        raise _refus(400, E.REFUS_SEANCE_NON_AUTORISEE, "Cette séance ne peut pas être offerte.")
    _cible, _motif = E.occurrence_choisissable(occurrence, _occurrences(_cours), _maintenant())
    if not _cible:
        raise _refus(400, E.REFUS_SEANCE_INDISPONIBLE, "Cette séance n'est plus disponible.")
    return _cours, _cible


def _instantane_cours(course) -> dict:
    return {"name": course.get("name") or "", "time": course.get("time") or "",
            "locationName": course.get("locationName") or course.get("location") or "",
            "mapsUrl": course.get("mapsUrl") or ""}


async def _choix_enfant(parent, corps) -> dict:
    """Le `$set` du choix Wizard (type et/ou séance) lu dans `corps`, VALIDÉ ; {}
    si le corps n'en porte aucun. Lève 400/422 AVANT toute écriture."""
    _set = {}
    if "kind" in (corps or {}):
        _k = str(corps.get("kind") or "").strip()
        if not E.type_offrable(_k, parent, await _programmes_actifs(await _proprietaire_chaine(parent))):
            raise _refus(400, E.REFUS_TYPE_NON_AUTORISE, "Cette offre n'est pas proposée pour ton invitation.")
        _set["chain.kind"] = _k
    if "course_id" in (corps or {}) or "occurrence" in (corps or {}):
        _cours, _occ = await _valider_seance_enfant(parent, corps.get("course_id"), corps.get("occurrence"))
        _set.update({"course_id": _cours.get("id"), "occurrence": _occ, "expires_at": _occ,
                     "course_snapshot": _instantane_cours(_cours), "chain.seance_choisie": True})
    return _set


async def _appliquer_choix_enfant(enfant, choix):
    """Écrit le choix sur l'enfant ENCORE modifiable (ni rejoint, ni partagé) ;
    le parent n'est jamais touché. Rend l'enfant relu."""
    _change = {k: v for k, v in choix.items()
               if (E.chaine_du_pass(enfant).get(k.split(".", 1)[1]) if k.startswith("chain.") else enfant.get(k)) != v}
    if not _change:
        return enfant
    if enfant.get("invitee"):
        raise _refus(409, E.REFUS_PASS_DEJA_REJOINT, "Ton ami a déjà rejoint cette invitation.")
    if E.partage_chaine(enfant)["shared"] and any(k in _change for k in ("occurrence", "course_id", "chain.kind")):
        # Jamais un changement silencieux de ce qui a DÉJÀ été envoyé.
        raise _refus(409, E.REFUS_INVITATION_DEJA_PARTAGEE,
                     "Ton invitation a déjà été envoyée : sa séance ne peut plus changer.")
    _now = _iso()
    _detail = {"course_id": _change.get("course_id"), "occurrence": _change.get("occurrence"),
               "kind": _change.get("chain.kind")}
    await db[COLL_PASSES].update_one(
        {"id": enfant["id"], "invitee": None},
        {"$set": dict(_change, updated_at=_now),
         "$push": {"events": {"at": _now, "type": E.EVENEMENT_SEANCE_ENFANT, "detail": _detail}},
         "$inc": {"version": 1, "invitation_version": 1}})
    return await db[COLL_PASSES].find_one({"id": enfant["id"]}, {"_id": 0}) or enfant


@router.get("/pass/{share_token}/chain/options")
async def referral_chaine_options(share_token: str, request: Request):
    """V558 — de quoi remplir les étapes « Offre » et « Séance » du Wizard, sans
    aucune donnée personnelle : `{types, seances, seance_parent}`. Public (le jeton
    du parent est la capacité), débit IP."""
    await _exiger_actif()
    _exiger_debit(request, DEBIT_PREFIXE_CHAINE_OPTIONS)
    _p, _s = await _parent_ouvert(share_token)
    _progs = await _programmes_actifs(await _proprietaire_chaine(_p))
    return {"types": E.types_offrables(_p, _progs),
            "seances": await _seances_offrables(_p),
            "seance_parent": {"course_id": _p.get("course_id"), "occurrence": _p.get("occurrence")}}


@router.post("/pass/{share_token}/chain")
async def referral_chaine_creer(share_token: str, request: Request):
    """V556 — crée (201) ou rend (200, idempotent) L'invitation enfant de ce
    pass : `{child, shared, preview, edit_key?}`. Public (le jeton du parent
    est la seule capacité) ; débit par IP ; une seule enfant par pass."""
    await _exiger_actif()
    _exiger_debit(request, DEBIT_PREFIXE_CHAINE)
    _p, _s = await _parent_ouvert(share_token)
    await _exiger_campagne_vivante(_p)          # PAR-1 (audit P2)
    _b = await _corps(request)
    _enf = await _enfant_de(_p)
    if _enf:
        # V558 : l'appareil qui l'a créée peut encore changer type / séance tant
        # que rien n'est envoyé ; un autre appareil relit l'enfant sans rien changer.
        if _cle_chaine_valide(request, _enf):
            _choix = await _choix_enfant(_p, _b)
            if _choix:
                _enf = await _appliquer_choix_enfant(_enf, _choix)
        return await _reponse_chaine(_p, await _apprendre_photo_profil(request, _enf), 200)
    if not await _chaine_active():
        raise HTTPException(status_code=404, detail="parrainage_chaine_desactive")
    if not E.chaine_requise(_p, _s, True):
        # V556 : un lien déjà utilisé ne fabrique pas d'invitation orpheline.
        raise _refus(409, E.REFUS_PASS_FERME, "Cette invitation a déjà été utilisée.")
    if E.attente_trop_longue(await _maillons_en_attente(_p)):
        raise _refus(409, E.REFUS_CHAINE_EN_ATTENTE,
                     "Cette invitation sera active dès que la personne qui te l'a envoyée "
                     "aura terminé son inscription.")
    _inv = _champs_invitation_enfant(_b)
    _inv["message"] = _inv.get("message") or E.MESSAGE_CHAINE_DEFAUT
    _choix = await _choix_enfant(_p, _b)        # V558 : type + séance de l'ami, validés
    _now = _maintenant()
    _cle = secrets.token_urlsafe(18)
    _ch_parent = E.chaine_du_pass(_p)
    try:
        _prof = int(_ch_parent.get("depth") or 0) + 1
    except (TypeError, ValueError):
        _prof = 1
    _doc = {
        "id": str(uuid.uuid4()),
        "coach_id": _p.get("coach_id") or "",
        "course_id": _p.get("course_id"),
        "occurrence": _p.get("occurrence"),
        "course_snapshot": dict(_p.get("course_snapshot") or {}),
        "sponsor": {
            "email_norm": E.cle_parrain_en_attente(_p["id"]),
            "name": _inv.get("display_name") or "",
            "whatsapp_norm": None, "subscription_code": None,
            "terms_accepted": False, "pending": True,
        },
        "invitee": None,
        "status": E.LOCKED,
        "share_token": secrets.token_urlsafe(24),
        "opened_at": None,
        "reservations": {"sponsor_id": None, "sponsor_code": None,
                         "invitee_id": None, "invitee_code": None},
        "invitee_access_code": None,
        "blocked_reason": None,
        "attribution": None,
        "spordate_reward": {"status": "none"},
        "offer_id": _p.get("offer_id"),
        "offer_snapshot": dict(_p.get("offer_snapshot") or {}),
        "offer_history": [],
        "version": 1,
        "invitation": {"display_name": _inv.get("display_name"), "photo_url": None,
                       "message": _inv["message"], "updated_at": _iso(_now)},
        "invitation_version": 1,
        "preview_version": 0,
        "chain": {"parent_pass_id": _p["id"],
                  "root_pass_id": _ch_parent.get("root_pass_id") or _p["id"],
                  "depth": _prof, "edit_key_hash": _hache_cle(_cle), "created_at": _iso(_now)},
        "created_at": _iso(_now),
        "updated_at": _iso(_now),
        "unlocked_at": None,
        "expires_at": _p.get("occurrence"),
        "events": [{"at": _iso(_now), "type": E.EVENEMENT_CHAINE_CREEE, "detail": None}],
    }
    # V558 : la séance (et le type) CHOISIS pour l'ami remplacent ceux hérités du
    # parent — le parent, lui, garde sa séance.
    for _k, _v in _choix.items():
        if _k.startswith("chain."):
            _doc["chain"][_k.split(".", 1)[1]] = _v
        else:
            _doc[_k] = _v
    # PAR-1 : l'enfant d'une chaîne de campagne hérite de la campagne et de la
    # source racine (jamais de `source_type` propre : il est subscriber).
    _org = E.origine_du_pass(_p)
    if _org.get("campaign_id"):
        _racine = "root_source_type" in _org
        _doc["origin"] = {"campaign_id": _org.get("campaign_id"),
                          "root_source_type": _org.get("root_source_type") if _racine else _org.get("source_type"),
                          "root_source_id": _org.get("root_source_id") if _racine else _org.get("source_id")}
    # L0 : l'enfant porte le prénom saisi ; pas de photo (le filleul n'est pas encore inscrit)
    # -> avatar Afroboost, jamais la photo du coach à la place d'un membre.
    # UX-P1 : si le créateur présente une identité abonné, sa photo de PROFIL est
    # proposée (`photo_suggeree`) et sert de repli tant qu'aucune photo n'est choisie.
    _prof_photo = await _photo_profil_requete(request)
    if _prof_photo:
        _doc["inviter_profile_photo"] = _prof_photo
    _doc["inviter_display"] = E.identite_invitant(_doc, _prof_photo)
    try:
        await db[COLL_PASSES].insert_one(dict(_doc))
    except Exception as _err:  # noqa: BLE001
        if _est_doublon(_err):              # deux onglets en même temps : on rend l'existante
            _enf = await _enfant_de(_p)
            if _enf:
                return await _reponse_chaine(_p, _enf, 200)
        logger.error("%s invitation enfant non créée (%s)", PREFIXE, type(_err).__name__)
        raise HTTPException(status_code=503, detail="Invitation non préparée, réessaie dans un instant.")
    await _journal_parent(_p["id"], E.EVENEMENT_CHAINE_CREEE, None,
                          {"chain.child_pass_id": _doc["id"], "chain.child_created_at": _iso(_now)})
    logger.info("%s invitation enfant %s créée sous %s (profondeur %s)", PREFIXE, _doc["id"][:8],
                _p["id"][:8], _prof)
    return await _reponse_chaine(_p, _doc, 201, edit_key=_cle)


@router.patch("/pass/{share_token}/chain")
async def referral_chaine_modifier(share_token: str, request: Request):
    """V556 — prénom / message de la carte, avec la clé rendue à la création
    (`X-Chain-Key`). Même jeton ; nouvelle version d'aperçu.

    UX-P1 — accepte aussi `photo_url` (validée ; null = retirer), `whatsapp`
    (saisie avec indicatif, normalisée E.164 ; invalide -> 422 ; null/"" =
    retirer) et `consent_contact` (booléen). Tout est validé AVANT la moindre
    écriture. Seul un changement VISUEL (prénom, message, photo — ou un corps
    sans champ de contact, comportement V556) incrémente les versions ; le
    numéro ne sort jamais (`whatsapp_renseigne`). Un numéro valide crée /
    complète le contact du COACH PROPRIÉTAIRE (`_contact_coach_chaine`)."""
    await _exiger_actif()
    _exiger_debit(request, DEBIT_PREFIXE_CHAINE_ACTION)
    _p, _s = await _parent_ouvert(share_token)
    _enf = await _enfant_de(_p)
    if not _enf:
        raise HTTPException(status_code=404, detail="Prépare d'abord ton invitation.")
    if not _cle_chaine_valide(request, _enf):
        raise HTTPException(status_code=403, detail="Cette invitation ne peut être modifiée que depuis l'appareil qui l'a créée.")
    if _enf.get("invitee"):
        raise _refus(409, E.REFUS_PASS_DEJA_REJOINT, "Ton ami a déjà rejoint cette invitation.")
    _b = await _corps(request)
    _inv = _champs_invitation_enfant(_b, avec_photo=True)
    _contact = _champs_contact_enfant(_b, E.contact_invitant(_enf))      # 422 avant toute écriture
    _choix = await _choix_enfant(_p, _b)                                 # V558 : 400 avant toute écriture
    if _choix:
        _enf = await _appliquer_choix_enfant(_enf, _choix)
        if not any(k in _b for k in CHAMPS_VISUELS_ENFANT) and _contact is None:
            return await _reponse_chaine(_p, _enf, 200)
    _visuel = any(k in _b for k in CHAMPS_VISUELS_ENFANT) or _contact is None
    _enf = await _apprendre_photo_profil(request, _enf)
    _prof_photo = E.photo_suggeree_enfant(_enf)
    _now = _iso()
    _set, _inc = {"updated_at": _now}, {}
    if _visuel:
        _inv["message"] = _inv.get("message") or E.MESSAGE_CHAINE_DEFAUT
        _existante = E.invitation_du_pass(_enf)
        _fusion = {"display_name": _inv.get("display_name") if "display_name" in _b else _existante["display_name"],
                   "photo_url": _inv.get("photo_url") if "photo_url" in _b else _existante["photo_url"],
                   "message": _inv["message"] if "message" in _b else (_existante["message"] or E.MESSAGE_CHAINE_DEFAUT),
                   "updated_at": _now}
        _set["invitation"] = _fusion
        if E.parrain_en_attente(_enf):
            _set["sponsor.name"] = _fusion["display_name"] or ""
        _apres = dict(_enf, invitation=_fusion)
        if "sponsor.name" in _set:
            _apres["sponsor"] = dict(_enf.get("sponsor") or {}, name=_set["sponsor.name"])
        # L0 : re-figée avec l'invitation ; sans photo -> profil connu -> logo (jamais le coach)
        _set["inviter_display"] = E.identite_invitant(_apres, _prof_photo)
        _inc = {"invitation_version": 1, "version": 1}
    if _contact is not None:
        _set["contact_invitant"] = dict(_contact, updated_at=_now)
    _maj = {"$set": _set}
    if _inc:
        _maj["$inc"] = _inc
    await db[COLL_PASSES].update_one({"id": _enf["id"], "share_token": _enf.get("share_token")}, _maj)
    _enf = await db[COLL_PASSES].find_one({"id": _enf["id"]}, {"_id": 0}) or _enf
    if _contact is not None and _contact.get("whatsapp_e164"):
        await _contact_coach_chaine(_p, _enf, _contact["whatsapp_e164"], _contact.get("consent") is True)
    return await _reponse_chaine(_p, _enf, 200)


# ═══════════════════════════════════════════════════════════════════════════
# UX-P1 (29/09) — photo, numéro et contact du coach sur l'invitation enfant
# ═══════════════════════════════════════════════════════════════════════════
CHAMPS_VISUELS_ENFANT = ("display_name", "message", "photo_url")
DEBIT_PREFIXE_CHAINE_PHOTO = "duo_chain_p:"      # UX-P1 : envoi de photo (quota séparé)
PHOTO_CHAINE_MAX_OCTETS = 5 * 1024 * 1024
SOURCE_CONTACT_PARRAINAGE = "referral"
SOURCE_REGISTRE_SANS_CONSENTEMENT = "referral_no_consent"
MESSAGE_WHATSAPP_INVALIDE = ("Numéro WhatsApp invalide : saisis-le avec l'indicatif du pays "
                             "(ex. +41 79 123 45 67).")


def _champs_contact_enfant(corps, existant) -> dict:
    """`{whatsapp_e164, consent}` fusionné sur l'existant, ou None si le corps
    ne porte aucun champ de contact. 422 (message clair) si invalide."""
    if "whatsapp" not in (corps or {}) and "consent_contact" not in (corps or {}):
        return None
    from api.routes.tenant_contacts import telephone_e164
    _sortie = {"whatsapp_e164": (existant or {}).get("whatsapp_e164") or None,
               "consent": (existant or {}).get("consent") is True}
    if "whatsapp" in corps:
        _v = corps.get("whatsapp")
        if _v is None or (isinstance(_v, str) and not _v.strip()):
            _sortie["whatsapp_e164"] = None
        else:
            _e164 = telephone_e164(_v)
            if not _e164:
                raise HTTPException(status_code=422, detail=MESSAGE_WHATSAPP_INVALIDE)
            _sortie["whatsapp_e164"] = _e164
    if "consent_contact" in corps:
        if not isinstance(corps.get("consent_contact"), bool):
            raise HTTPException(status_code=422, detail="consent_contact : vrai ou faux attendu.")
        _sortie["consent"] = corps["consent_contact"]
    return _sortie


async def _photo_profil_requete(request):
    """La photo de profil de l'abonné qui présente SON identité (`x-espace-token`
    / `X-Subscriber-Token`, jamais X-User-Email) ; None sinon. Jamais bloquant :
    une identité absente ou refusée laisse la route publique telle quelle."""
    if not _porte_identite_abonne(request):
        return None
    try:
        _parrain = await _parrain_depuis_requete(request)
    except HTTPException:
        return None
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s identité abonné illisible (%s)", PREFIXE, type(_err).__name__)
        return None
    return await _photo_profil(_parrain.get("email"))


async def _apprendre_photo_profil(request, enfant):
    """Mémorise la photo de profil proposée sur l'invitation enfant (sans toucher
    aux versions : ce n'est qu'une suggestion). Rend l'enfant à jour."""
    _photo = await _photo_profil_requete(request)
    if not _photo or _photo == (enfant or {}).get("inviter_profile_photo"):
        return enfant
    _maj = {"inviter_profile_photo": _photo}
    if not E.invitation_du_pass(enfant)["photo_url"]:
        _maj["inviter_display"] = E.identite_invitant(enfant, _photo)
    try:
        await db[COLL_PASSES].update_one({"id": enfant["id"]}, {"$set": _maj})
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s photo de profil non mémorisée (%s)", PREFIXE, type(_err).__name__)
        return enfant
    return dict(enfant, **_maj)


async def _proprietaire_contact(enfant):
    """(coach_id propriétaire brut, type de parrainage, campagne) : campagne ->
    son propriétaire ; sinon le `coach_id` du pass ("" = plateforme)."""
    _cid = E.campagne_du_pass(enfant)
    if _cid:
        _camp = await _campagne_par_id(_cid) or {}
        return str(_camp.get("coach_id") or "").strip().lower(), str(_camp.get("type") or "trial"), _cid
    return str((enfant or {}).get("coach_id") or "").strip().lower(), SOURCE, None


async def _registre_consentement(e164, consent) -> bool:
    """Le choix marketing dans le registre EXISTANT `subscribers` (celui que lisent
    `c3_refus_exprimes` / `c3_verdict` avant TOUTE campagne) — aucun second système.

    * consent False -> `status: opted_out` (ligne créée, ou `targeted`/`pending`/
      `confirmed` basculée) : C3 écarte ce numéro de toutes les campagnes.
    * consent True  -> `$setOnInsert` d'une ligne neutre `targeted` (S1 : STOP
      exprimable). Jamais `confirmed` (aucune preuve de possession), et un refus
      existant n'est JAMAIS levé par une route publique (règle DETTE 3 / V332).
    Rend False si le registre est illisible / non écrit."""
    _now = _iso()
    _cle = {"channel": "whatsapp", "value": e164}
    try:
        if consent:
            await db["subscribers"].update_one(
                _cle, {"$setOnInsert": {"id": str(uuid.uuid4()), "created_at": _now, "updated_at": _now,
                                        "status": "targeted", "source": SOURCE_CONTACT_PARRAINAGE, "name": ""}},
                upsert=True)
            return True
        _ex = await db["subscribers"].find_one(_cle, {"_id": 0, "status": 1})
        if _ex and _ex.get("status") == "opted_out":
            return True
        if _ex:
            await db["subscribers"].update_one(
                _cle, {"$set": {"status": "opted_out", "opted_out_at": _now, "updated_at": _now,
                                "opted_out_source": SOURCE_REGISTRE_SANS_CONSENTEMENT,
                                "status_before_opt_out": _ex.get("status")}})
        else:
            await db["subscribers"].update_one(
                _cle, {"$setOnInsert": {"id": str(uuid.uuid4()), "created_at": _now, "name": "",
                                        "source": SOURCE_REGISTRE_SANS_CONSENTEMENT},
                       "$set": {"status": "opted_out", "opted_out_at": _now, "updated_at": _now}},
                upsert=True)
        return True
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s registre de consentement non écrit (%s)", PREFIXE, type(_err).__name__)
        return False


async def _contact_coach_chaine(parent, enfant, e164, consent) -> None:
    """Crée / complète le contact `chat_participants` du COACH PROPRIÉTAIRE.

    Dédoublonnage (coach, téléphone) DANS SA SEULE PORTÉE (`doublon_dans_portee`,
    variantes exactes, aucune regex) ; jamais chez un autre coach. Fiche
    existante : prénom seulement s'il est vide, sources et provenances AJOUTÉES,
    `marketing_consent` = dernier choix ; rien d'autre n'est réécrit.
    Le refus marketing est inscrit AVANT : sans lui, aucun contact n'est créé."""
    from api.routes.tenant_contacts import (portee_proprietaire, doublon_dans_portee,
                                            index_doublons, chercher_doublon)
    if not await _registre_consentement(e164, consent) and not consent:
        logger.warning("%s refus marketing non inscrit : contact NON créé (réessai au prochain PATCH)", PREFIXE)
        return
    _brut, _type, _cid = await _proprietaire_contact(enfant)
    _coach_id, _portee = portee_proprietaire(_brut)
    _lig = E.lignage(enfant)
    _now = _iso()
    _prov = {"campaign_id": _cid or _lig.get("campaign_id"),
             "root_referral_id": _lig.get("root_referral_id"),
             "parent_referral_id": _lig.get("parent_referral_id"),
             "pass_id": enfant.get("id"), "inviter_pass_id": (parent or {}).get("id"),
             "type": _type, "created_at": _now}
    _prenom = E.invitation_du_pass(enfant)["display_name"] or ""
    try:
        # Chemin rapide : variantes exactes. Repli : l'index canonique de la
        # portée (une lecture projetée) — une fiche saisie « 079 123 45 67 »
        # (espaces) n'est pas une variante exacte mais reste le même numéro.
        _ex = await doublon_dans_portee(db, _portee, telephone=e164)
        if not _ex:
            _trouve = chercher_doublon(await index_doublons(db, _portee), telephone=e164)
            if _trouve and _trouve.get("id"):
                _ex = await db["chat_participants"].find_one(
                    {"$and": [_portee, {"id": _trouve["id"]}]}, {"_id": 0})
        if _ex:
            _sources = [x for x in (_ex.get("sources") or []) if isinstance(x, str)]
            if not _sources and _ex.get("source"):
                _sources = [str(_ex["source"])]
            if SOURCE_CONTACT_PARRAINAGE not in _sources:
                _sources.append(SOURCE_CONTACT_PARRAINAGE)
            _provs = [x for x in (_ex.get("referrals") or []) if isinstance(x, dict)]
            if not any(x.get("pass_id") == enfant.get("id") for x in _provs):
                _provs.append(_prov)
            _set = {"sources": _sources, "referrals": _provs[-50:], "marketing_consent": bool(consent),
                    "updated_at": _now}
            if not isinstance(_ex.get("referral"), dict):
                _set["referral"] = _prov
            if not str(_ex.get("name") or "").strip() and _prenom:
                _set["name"] = _prenom
            await db["chat_participants"].update_one(
                {"$and": [_portee, {"id": _ex.get("id")}]}, {"$set": _set})
            return
        await db["chat_participants"].update_one(
            {"coach_id": _coach_id, "whatsapp": e164},
            {"$setOnInsert": {"id": str(uuid.uuid4()), "name": _prenom, "email": "",
                              "source": SOURCE_CONTACT_PARRAINAGE, "sources": [SOURCE_CONTACT_PARRAINAGE],
                              "referral": _prov, "referrals": [_prov], "link_token": None,
                              "created_at": _now, "last_seen_at": None},
             "$set": {"marketing_consent": bool(consent), "updated_at": _now}},
            upsert=True)
        logger.info("%s contact de parrainage créé chez %s", PREFIXE, "la plateforme"
                    if _coach_id != _brut else "le coach propriétaire")
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s contact de parrainage non écrit (%s)", PREFIXE, type(_err).__name__)


@router.post("/pass/{share_token}/chain/photo")
async def referral_chaine_photo(share_token: str, request: Request, file: UploadFile = File(...)):
    """UX-P1 — photo de l'invitation enfant : `X-Chain-Key` obligatoire (403),
    JPEG/PNG/WebP (type déclaré + extension + SIGNATURE binaire concordants,
    415), <= 5 Mo (413), débit par IP. Stockage V413 (`_v413_enregistrer_media`,
    comme l'image de partage V551), nom serveur, AUCUNE donnée personnelle.
    201 `{photo_url: "/api/files/<id>/<nom>"}` — l'appareil l'applique ensuite
    par PATCH /chain (`photo_url`) : elle ne sert qu'à CETTE invitation."""
    await _exiger_actif()
    _exiger_debit(request, DEBIT_PREFIXE_CHAINE_PHOTO)
    _p, _s = await _parent_ouvert(share_token)
    _enf = await _enfant_de(_p)
    if not _enf:
        raise HTTPException(status_code=404, detail="Prépare d'abord ton invitation.")
    if not _cle_chaine_valide(request, _enf):
        raise HTTPException(status_code=403, detail="Cette invitation ne peut être modifiée que depuis l'appareil qui l'a créée.")
    if _enf.get("invitee"):
        raise _refus(409, E.REFUS_PASS_DEJA_REJOINT, "Ton ami a déjà rejoint cette invitation.")
    _type = str(getattr(file, "content_type", "") or "").split(";")[0].strip().lower()
    _nom_client = str(getattr(file, "filename", "") or "")
    _ext = _nom_client.rsplit(".", 1)[-1].strip().lower() if "." in _nom_client else ""
    if _type not in IMAGE_TYPES or _ext not in IMAGE_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Formats acceptés : JPG, PNG ou WebP.")
    _octets = await file.read(PHOTO_CHAINE_MAX_OCTETS + 1)
    if len(_octets) > PHOTO_CHAINE_MAX_OCTETS:
        raise HTTPException(status_code=413, detail="Photo trop lourde (5 Mo maximum).")
    _reel = _type_reel_image(_octets)
    if not _reel or _reel != IMAGE_TYPES[_type] or _reel != IMAGE_EXTENSIONS[_ext]:
        raise HTTPException(status_code=415, detail="Ce fichier n'est pas une image JPG, PNG ou WebP valide.")
    from api.server import _v413_enregistrer_media
    _file_id = uuid.uuid4().hex[:16]
    _filename = "chain_%s.%s" % (uuid.uuid4().hex[:12], _reel)
    _mime = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}[_reel]
    try:
        await _v413_enregistrer_media(_file_id, _filename, _octets, {
            "file_id": _file_id, "filename": _filename, "original_name": _filename,
            "content_type": _mime, "asset_type": "referral_chain_photo",
            "created_at": datetime.utcnow(),
        })
    except Exception as _err:  # noqa: BLE001
        logger.error("%s photo d'invitation non enregistrée (%s)", PREFIXE, type(_err).__name__)
        raise HTTPException(status_code=503, detail="Photo non enregistrée, réessaie dans un instant.")
    logger.info("%s photo d'invitation enfant enregistrée (%s, %d o)", PREFIXE, _file_id, len(_octets))
    return JSONResponse(status_code=201, content={"photo_url": "/api/files/%s/%s" % (_file_id, _filename)})


@router.post("/pass/{share_token}/chain/share")
async def referral_chaine_partager(share_token: str, request: Request):
    """V556 — l'action de partage vient d'être DÉCLENCHÉE (`{channel}`).
    Débloque l'inscription du visiteur (une fois pour toutes) et prépare une
    share_url NEUVE pour un éventuel partage suivant (même jeton)."""
    await _exiger_actif()
    _exiger_debit(request, DEBIT_PREFIXE_CHAINE_ACTION)
    _p, _s = await _parent_ouvert(share_token)
    await _exiger_campagne_vivante(_p)          # PAR-1 (audit P2)
    _b = await _corps(request)
    _canal = str(_b.get("channel") or "").strip().lower()
    if _canal not in E.CANAUX:
        raise HTTPException(status_code=400, detail="Canal inconnu (%s)." % ", ".join(E.CANAUX))
    _enf = await _enfant_de(_p)
    if not _enf:
        raise HTTPException(status_code=404, detail="Prépare d'abord ton invitation.")
    if not _cle_chaine_valide(request, _enf):
        raise _refus(403, E.REFUS_AUTRE_APPAREIL,
                     "Partage ton invitation depuis l'appareil qui l'a préparée.")
    _se = await _statut_reel(_enf)
    if _se in (E.EXPIRED, E.CANCELLED):
        raise HTTPException(status_code=410, detail="Cette invitation n'est plus valable.")
    _now = _iso()
    # V556 : au-delà de PARTAGES_MAX, le partage reste accepté mais n'écrit plus
    # rien (ni journal, ni événement, ni nouvelle carte) — la base ne grossit pas.
    _plafond = E.version_apercu(_enf) >= E.PARTAGES_MAX
    try:
        if _plafond:
            raise StopIteration
        await db[COLL_INVITATIONS].insert_one({
            "id": str(uuid.uuid4()), "pass_id": _enf["id"],
            "sponsor_email_norm": (_enf.get("sponsor") or {}).get("email_norm"),
            "channel": _canal, "created_at": _now, "chain_parent_pass_id": _p["id"]})
    except StopIteration:
        pass
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s partage non journalisé (%s)", PREFIXE, type(_err).__name__)
    if not _plafond:
        await _evenement(_enf["id"], "invitation_sent", _canal,
                         {"status": E.transition(E.LOCKED, E.WAITING)} if _se == E.LOCKED else None)
    if not E.chaine_partagee(_p):
        await _journal_parent(_p["id"], E.EVENEMENT_CHAINE_PARTAGEE, _canal,
                              {"chain.shared_at": _now, "chain.share_channel": _canal})
        _p = await db[COLL_PASSES].find_one({"id": _p["id"]}, {"_id": 0}) or _p
    if not _plafond:
        _enf = await _nouvelle_version_apercu(_enf["id"]) or _enf
    _rep = {"shared": True, "shared_at": E.chaine_du_pass(_p).get("shared_at") or _now,
            "child": E.dto_enfant(_enf, _frontend_url()),
            # la PROCHAINE carte est rendue maintenant (cache chaud pour le robot)
            "preview": await _bilan_apercu(_enf)}
    return JSONResponse(status_code=200, content=_rep)


@router.get("/pass/{share_token}/chain/preview")
async def referral_chaine_apercu(share_token: str, request: Request):
    """V556 — relance le contrôle d'aperçu de l'invitation enfant."""
    await _exiger_actif()
    _exiger_debit(request, DEBIT_PREFIXE_CHAINE_LECTURE)
    _p = await _pass_par_token(share_token)
    _enf = await _enfant_de(_p)
    if not _enf:
        raise HTTPException(status_code=404, detail="Prépare d'abord ton invitation.")
    return await _reponse_chaine(_p, await _apprendre_photo_profil(request, _enf), 200)


# ═══════════════════════════════════════════════════════════════════════════
# PAR-1 — L'ENTRÉE D'UNE CAMPAGNE : un pass racine (P0) par visiteur
# ═══════════════════════════════════════════════════════════════════════════
# Le visiteur d'un lien de campagne `trial` (`/duo/c/<jeton>`) reçoit UN pass
# ORDINAIRE dont le « parrain » est la campagne : ensuite InvitationDuo,
# WizardFilleul et /join font le reste, sans rien changer. Public : la seule
# capacité est le jeton de la campagne ; `X-Entry-Key` (rendue une fois, à la
# création) retrouve le MÊME P0 sur le même appareil. Réponse SANS PII.
DETAIL_ENTREE_INTROUVABLE = "Invitation introuvable"
ENTREE_CLE_MAX = 64


def _jeton_campagne(token) -> str:
    _t = str(token or "").strip()
    if not _t or len(_t) > 128 or any(c.isspace() or c in "/\\?#%$" for c in _t):
        return ""
    return _t


@router.post("/campaign/{token}/entry")
async def referral_campagne_entree(token: str, request: Request):
    """`{attribution?}` (+ `X-Entry-Key` facultatif) -> 201 `{share_token,
    entry_key, target}` (P0 neuf) | 200 `{share_token, target}` (P0 de cette
    clé). 404 neutre (inconnue, brouillon, archivée, autre type, séance ou
    offre invalide) ; 404 `parrainage_chaine_desactive` (drapeaux) ; 410 séance
    passée ; 409 `X-Refus-Raison: campagne_complete` ; 429 débit IP."""
    await _exiger_actif()
    _exiger_debit(request, DEBIT_PREFIXE_CAMPAGNE)
    if not await invitation_chaine_campagne_active(db):
        raise HTTPException(status_code=404, detail="parrainage_chaine_desactive")
    _tok = _jeton_campagne(token)
    _camp = None
    if _tok:
        try:
            _camp = await db["referral_campaigns"].find_one({"share_token": _tok}, {"_id": 0})
        except Exception as _err:  # noqa: BLE001
            logger.warning("%s campagne illisible (%s)", PREFIXE, type(_err).__name__)
            raise HTTPException(status_code=503, detail="Invitation momentanément indisponible")
    if not _camp or _camp.get("status") != "active" or _camp.get("type") != "trial" or not _camp.get("id"):
        raise HTTPException(status_code=404, detail=DETAIL_ENTREE_INTROUVABLE)

    # Le même appareil revient : le MÊME P0, sans rien écrire.
    try:
        _cle_client = (request.headers.get("x-entry-key", "") or "").strip()
    except Exception:  # noqa: BLE001
        _cle_client = ""
    if _cle_client and len(_cle_client) <= ENTREE_CLE_MAX:
        _deja = await db[COLL_PASSES].find_one(
            {"origin.campaign_id": _camp["id"], "origin.entry_key_hash": _hache_cle(_cle_client)}, {"_id": 0})
        if _deja:
            return JSONResponse(status_code=200, content={
                "share_token": _deja.get("share_token"), "target": "/duo/%s" % _deja.get("share_token")})

    from api.routes.reservation_routes import lot1_occurrence_iso
    _occ = lot1_occurrence_iso(_camp.get("occurrence"))
    _course = None
    if _camp.get("course_id"):
        _course = await db["courses"].find_one({"id": str(_camp.get("course_id"))}, {"_id": 0})
    _offre = await _offre_de_campagne(_camp)
    if not _occ or not _course or _course.get("archived") is True or _course.get("visible") is False \
            or not _offre or not IC.seance_du_cours(_course, _occ):
        raise HTTPException(status_code=404, detail=DETAIL_ENTREE_INTROUVABLE)
    _now = _maintenant()
    if E.est_passee(_occ, _now):
        raise HTTPException(status_code=410, detail="La séance de cette invitation est passée.")

    # Plafond : P0 encore ouverts (sans invité) pour cette campagne.
    # Audit P1-A : seuls les P0 RÉCENTS (< 24 h) sans invité comptent — des P0
    # abandonnés ne bloquent plus les vrais visiteurs.
    from datetime import timedelta
    _depuis = _iso(_now - timedelta(hours=CAMPAGNE_ENTREES_FENETRE_H))
    _ouverts = await db[COLL_PASSES].count_documents(
        {"origin.campaign_id": _camp["id"], "origin.source_type": {"$in": list(E.SOURCES_RACINE)},
         "status": {"$in": [E.LOCKED, E.WAITING]}, "invitee": None, "created_at": {"$gte": _depuis}})
    if _ouverts >= CAMPAGNE_ENTREES_OUVERTES_MAX or await _campagne_complete_essais(_camp):
        raise _refus(409, "campagne_complete", "Cette invitation est complète pour le moment.")
    # Audit P1-A : débit PAR IP ET PAR CAMPAGNE, seulement pour un P0 NEUF (une
    # clé X-Entry-Key connue est rendue plus haut sans le consommer).
    if not _debit_entree_campagne(request, _camp["id"]):
        raise HTTPException(status_code=429,
                            detail="Trop de demandes depuis cette connexion. Réessayez dans un moment.")

    _cle_camp = str(_camp.get("coach_id") or "").strip().lower()
    _idt = IC._inviter_public(_camp)
    try:
        _prenom = E.valider_nom_invitation(_idt.get("prenom")) if _idt.get("prenom") else None
    except E.InvitationInvalide:
        _prenom = None
    try:
        _message = E.valider_message(_camp.get("message"))
    except E.InvitationInvalide:
        _message = None
    _attrib = None
    try:
        from api.routes.shared import m2a_bloc_propre
        _attrib = m2a_bloc_propre((await _corps(request)).get("attribution")) or None
    except Exception:  # noqa: BLE001
        _attrib = None
    _pid = str(uuid.uuid4())
    _entry_key = secrets.token_urlsafe(18)
    _doc = {
        "id": _pid,
        "coach_id": str(_course.get("coach_id") or "").strip().lower() or _cle_camp,
        "course_id": _course.get("id"),
        "occurrence": _occ,
        "course_snapshot": {
            "name": _course.get("name") or "",
            "time": _course.get("time") or "",
            "locationName": _course.get("locationName") or _course.get("location") or "",
            "mapsUrl": _course.get("mapsUrl") or "",
        },
        "sponsor": {
            "email_norm": E.cle_parrain_campagne(_camp["id"], _pid),
            "name": _prenom or "",
            "whatsapp_norm": None, "subscription_code": None,
            "terms_accepted": False, "pending": False,
        },
        "invitee": None,
        "status": E.LOCKED,
        "share_token": secrets.token_urlsafe(24),
        "opened_at": None,
        "reservations": {"sponsor_id": None, "sponsor_code": None,
                         "invitee_id": None, "invitee_code": None},
        "invitee_access_code": None,
        "blocked_reason": None,
        "attribution": _attrib,
        "spordate_reward": {"status": "none"},
        "offer_id": _offre.get("id"),
        "offer_snapshot": E.snapshot_offre(_offre),
        "offer_history": [],
        "version": 1,
        "invitation": {"display_name": _prenom, "photo_url": _idt.get("photo_url"),
                       "message": _message, "updated_at": _iso(_now)},
        "invitation_version": 1,
        "inviter_display": {"prenom": _prenom or "", "photo_url": _idt.get("photo_url"), "source": "coach"},
        "chain": {"root_pass_id": _pid, "depth": 0},
        "origin": {"source_type": "partner" if _cle_camp else "super_admin",
                   "source_id": _cle_camp, "campaign_id": _camp["id"],
                   "entry_key_hash": _hache_cle(_entry_key)},
        "created_at": _iso(_now),
        "updated_at": _iso(_now),
        "unlocked_at": None,
        "expires_at": _occ,
        "events": [{"at": _iso(_now), "type": "pass_created", "detail": "campaign"}],
    }
    try:
        await db[COLL_PASSES].insert_one(dict(_doc))
    except Exception as _err:  # noqa: BLE001
        logger.error("%s entrée de campagne non créée (%s)", PREFIXE, type(_err).__name__)
        raise HTTPException(status_code=503, detail="Invitation non préparée, réessaie dans un instant.")
    logger.info("%s P0 %s créé pour la campagne %s", PREFIXE, _pid[:8], str(_camp["id"])[:8])
    return JSONResponse(status_code=201, content={
        "share_token": _doc["share_token"], "entry_key": _entry_key, "target": "/duo/%s" % _doc["share_token"]})


# ═══════════════════════════════════════════════════════════════════════════
# Routes — admin (JWT signé, cloisonnement `get_coach_filter`)
# ═══════════════════════════════════════════════════════════════════════════
async def _admin(request) -> dict:
    from api.server import _v309_require_coach_or_admin
    from api.routes.shared import get_coach_filter, is_super_admin
    _email = await _v309_require_coach_or_admin(request)
    return {"email": _email, "filtre": get_coach_filter(_email), "admin": is_super_admin(_email)}


def _filtre_admin(request, identite) -> dict:
    _q = dict(identite["filtre"])
    _params = getattr(request, "query_params", None) or {}
    _de, _a = str(_params.get("from") or "")[:32], str(_params.get("to") or "")[:32]
    if _de or _a:
        _q["created_at"] = {}
        if _de:
            _q["created_at"]["$gte"] = _de
        if _a:
            _q["created_at"]["$lte"] = _a + ("T23:59:59" if len(_a) == 10 else "")
    _cid = str(_params.get("course_id") or "").strip()
    if _cid:
        _q["course_id"] = _cid
    _coach = str(_params.get("coach") or "").strip().lower()
    if _coach and identite["admin"]:
        _q["coach_id"] = _coach
    _statut = str(_params.get("status") or "").strip()
    if _statut and _statut in E.ETATS:
        _q["status"] = _statut
    return _q


@router.get("/admin/summary")
async def referral_admin_summary(request: Request):
    await _exiger_actif()
    _id = await _admin(request)
    _q = _filtre_admin(request, _id)
    _now = _maintenant()
    _passes = await db[COLL_PASSES].find(_q, {"_id": 0}).sort("created_at", -1).to_list(5000)
    _ids = [p.get("id") for p in _passes]
    _invits = (await db[COLL_INVITATIONS].find({"pass_id": {"$in": _ids}}, {"_id": 0, "channel": 1})
               .to_list(20000)) if _ids else []
    _resas = (await db["reservations"].find({"pass_id": {"$in": _ids}, "validated": True},
                                            {"_id": 0, "id": 1, "pass_id": 1, "validated": 1})
              .to_list(20000)) if _ids else []
    _statuts = {}
    for _pd in _passes:
        _statuts[_pd.get("id")] = (await _statut_reel(_pd, _now, [r for r in _resas if r.get("pass_id") == _pd.get("id")]
                                                       if _pd.get("status") == E.UNLOCKED else None))
    _sortie = E.kpi_parrainage(_passes, _invits, _resas, _statuts)
    _sortie.update(E.kpi_offres(_passes))      # V534b : changements_offre, offre_la_plus_choisie, par_offre
    _sortie["filtres"] = {k: v for k, v in _q.items() if k != "coach_id" or _id["admin"]}
    return _sortie


@router.get("/admin/passes")
async def referral_admin_passes(request: Request):
    await _exiger_actif()
    _id = await _admin(request)
    _q = _filtre_admin(request, _id)
    _params = getattr(request, "query_params", None) or {}
    try:
        _page = max(1, int(_params.get("page") or 1))
    except (TypeError, ValueError):
        _page = 1
    _total = await db[COLL_PASSES].count_documents(_q)
    _rows = await db[COLL_PASSES].find(_q, {"_id": 0}).sort("created_at", -1) \
        .skip((_page - 1) * LISTE_MAX).limit(LISTE_MAX).to_list(LISTE_MAX)
    _now = _maintenant()
    _items, _cache = [], {}
    for _pd in _rows:
        _resas = await _reservations_du_pass(_pd)
        _s = await _statut_reel(_pd, _now, _resas)
        _items.append(E.dto_admin(_pd, _s, E.tickets_du_pass(_pd, _resas, _frontend_url()), _frontend_url(),
                                  offers=await _catalogue_du_pass(_pd, _cache)))
    return {"items": _items, "total": _total, "page": _page, "per_page": LISTE_MAX}
