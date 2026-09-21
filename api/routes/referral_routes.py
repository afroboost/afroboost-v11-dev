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
"""
import asyncio
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from api.routes import referral_engine as E

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/referral", tags=["referral"])

db = None

PREFIXE = "[V534 DUO]"
FLAG_ID = "feature_flags"
FLAG_CHAMP = "parrainage_duo_enabled"
# Réglage facultatif : l'identifiant de l'offre d'essai à octroyer. Absent, la
# première offre gratuite (prix 0) visible du propriétaire du cours est prise,
# de préférence celle qui lie ce cours (`linked_course_ids`).
FLAG_OFFRE = "parrainage_duo_offer_id"
COLL_PASSES = "referral_passes"
COLL_INVITATIONS = "referral_invitations"
COLL_SESSIONS = "subscriber_sessions"      # = `_B3S1_COLL_SESSIONS` (server.py)
DETAIL_DESACTIVE = "parrainage_duo_desactive"
SOURCE = "pass_duo"                          # `reservations.source` des billets Duo
SOURCE_ATTRIBUTION = "parrainage"            # M2-A (`M2A_SOURCES`)
JOURS_AVANT = 30
OCCURRENCES_MAX = 6
LISTE_MAX = 50
DEBIT_PREFIXE_PASS = "duo_pass:"
DEBIT_PREFIXE_JOIN = "duo_join:"


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


async def _exiger_actif() -> None:
    if not await parrainage_duo_actif(db):
        raise HTTPException(status_code=404, detail=DETAIL_DESACTIVE)


def _ip(request) -> str:
    try:
        return (request.headers.get("CF-Connecting-IP")
                or (request.headers.get("X-Forwarded-For", "") or "").split(",")[0].strip()
                or (request.client.host if getattr(request, "client", None) else "")).strip()
    except Exception:  # noqa: BLE001
        return ""


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
             "locationName": 1, "location": 1, "mapsUrl": 1, "coach_id": 1},
        ).to_list(LISTE_MAX)
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s cours illisibles (%s)", PREFIXE, type(_err).__name__)
        return []


def _dto_config_cours(course) -> dict:
    return {
        "id": course.get("id"),
        "name": course.get("name") or "",
        "weekday": course.get("weekday"),
        "date": course.get("date"),
        "time": course.get("time") or "",
        "locationName": course.get("locationName") or course.get("location") or "",
        "mapsUrl": course.get("mapsUrl") or "",
        "occurrences": _occurrences(course),
    }


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
    """Journalise un événement sur le pass (+ `$set` facultatif)."""
    _e = {"at": _iso(), "type": type_, "detail": detail}
    _upd = {"$push": {"events": _e}, "$set": dict(maj or {}, updated_at=_iso())}
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


async def _dto(pass_doc, deja_existant=None, now=None):
    _resas = await _reservations_du_pass(pass_doc)
    _s = await _statut_reel(pass_doc, now, _resas)
    return E.dto_pass(pass_doc, _s, E.tickets_du_pass(pass_doc, _resas, _frontend_url()),
                      _frontend_url(), deja_existant)


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

    _existante = await db["reservations"].find_one(
        {"userEmail": {"$regex": "^%s$" % re.escape(_email), "$options": "i"},
         "courseId": _cid, "datetime": _occ}, {"_id": 0})
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
    if not _key:
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
    _r, _blocage = await _tenter_reservation_parrain(pass_doc, course)
    if _r:
        _now = _iso()
        await _evenement(pass_doc["id"], "unlocked", None, {
            "status": E.transition(pass_doc.get("status"), E.UNLOCKED),
            "unlocked_at": _now, "blocked_reason": None,
            "reservations.sponsor_id": _r.get("id"),
            "reservations.sponsor_code": _r.get("reservationCode")})
        pass_doc = await db[COLL_PASSES].find_one({"id": pass_doc["id"]}, {"_id": 0}) or pass_doc
        _sub = (await db["subscriptions"].find_one({"id": _r.get("subscriptionId")}, {"_id": 0})
                if _r.get("subscriptionId") else None)
        if not _r.get("_rattachee"):
            await _notifier_reservation(_r, _sub)
        _sp = pass_doc.get("sponsor") or {}
        _cours = E.dto_course(pass_doc)["name"] or "ton cours"
        await _push_parrain(_sp.get("email_norm"), "Pass Duo débloqué",
                            "Vos deux places pour %s sont réservées." % _cours,
                            {"type": "pass_duo_unlocked", "pass_id": pass_doc["id"], "url": "/parrainage"})
        asyncio.create_task(_email_parrain_debloque(pass_doc))
        return pass_doc
    await _evenement(pass_doc["id"], "sponsor_blocked", _blocage, {
        "status": pass_doc.get("status"), "blocked_reason": _blocage})
    pass_doc["blocked_reason"] = _blocage
    return pass_doc


# ═══════════════════════════════════════════════════════════════════════════
# Offre d'essai et transaction
# ═══════════════════════════════════════════════════════════════════════════
async def _offre_essai(course) -> dict:
    """L'offre d'essai gratuite RÉELLE (prix 0, relue en base) du propriétaire
    du cours — préférence à celle qui lie ce cours ; réglage possible par
    `feature_flags.parrainage_duo_offer_id`."""
    try:
        _flags = await db[FLAG_ID].find_one({"id": FLAG_ID}, {"_id": 0}) or {}
        _forcee = str(_flags.get(FLAG_OFFRE) or "").strip()
        if _forcee:
            _o = await db["offers"].find_one({"id": _forcee}, {"_id": 0})
            if _o:
                return _o
    except Exception:  # noqa: BLE001
        pass
    try:
        from api.routes.membership_routes import p1a_filtre_proprietaire
        _q = dict(p1a_filtre_proprietaire((course or {}).get("coach_id")))
    except Exception:  # noqa: BLE001
        _q = {}
    _q.update({"price": {"$in": [0, 0.0]}, "archived": {"$ne": True}})
    try:
        _rows = await db["offers"].find(_q, {"_id": 0}).to_list(LISTE_MAX)
    except Exception:  # noqa: BLE001
        _rows = []
    _rows = [o for o in _rows if o.get("visible") is not False]
    _cid = str((course or {}).get("id") or "")
    for _o in _rows:
        if _cid and _cid in (_o.get("linked_course_ids") or []):
            return _o
    return _rows[0] if _rows else None


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


async def _rollback_filleul(pass_doc, email, telephone, access_code, sub_id=None) -> None:
    """La réservation de l'ami a échoué APRÈS l'octroi : on rend son droit à
    l'essai (`_essai1_liberer`), on neutralise le code et le forfait qui
    viennent de naître (marqués, jamais supprimés) et on rouvre le pass."""
    try:
        from api.routes.checkout_routes import _essai1_liberer
        await _essai1_liberer(email, telephone=telephone)
    except Exception as _err:  # noqa: BLE001
        logger.error("%s libération de l'essai impossible (%s)", PREFIXE, type(_err).__name__)
    _marque = {"pass_duo_rollback": True, "pass_duo_rollback_at": _iso()}
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
    try:
        await db[COLL_PASSES].update_one(
            {"id": pass_doc["id"]},
            {"$set": {"invitee": None, "invitee_access_code": None, "updated_at": _iso()}})
    except Exception as _err:  # noqa: BLE001
        logger.error("%s pass non rouvert (%s)", PREFIXE, type(_err).__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Routes — parrain
# ═══════════════════════════════════════════════════════════════════════════
@router.get("/config")
async def referral_config():
    """Public. OFF -> `{enabled:false, courses:[]}` (jamais 404 ici)."""
    if not await parrainage_duo_actif(db):
        return {"enabled": False, "courses": []}
    return {"enabled": True, "courses": [_dto_config_cours(c) for c in await _cours_eligibles()]}


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
    _dtos, _statuts = [], {}
    for _pd in _passes:
        _d = await _dto(_pd, now=_now)
        _dtos.append(_d)
        _statuts[_pd.get("id")] = _d["status"]
    return {
        "enabled": True,
        "sponsor": {"first_name": E.prenom(_p["name"]), "code": _p["code"]},
        "stats": E.stats_parrain(_passes, _invits, _statuts),
        "passes": _dtos,
        "invitations": [{"id": i.get("id"), "pass_id": i.get("pass_id"),
                         "channel": i.get("channel"), "created_at": i.get("created_at")}
                        for i in _invits],
        "history": E.historique(_passes, LISTE_MAX),
    }


@router.post("/pass")
async def referral_creer_pass(request: Request):
    """`{course_id, occurrence, terms_accepted?}` -> 201 PassDTO ; pass actif
    déjà existant -> 200 `deja_existant:true` ; cours inéligible / occurrence
    invalide -> 400. Débit par IP AVANT tout."""
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
        "created_at": _iso(_now),
        "updated_at": _iso(_now),
        "unlocked_at": None,
        "expires_at": _occ,
        "events": [{"at": _iso(_now), "type": "pass_created", "detail": None}],
    }
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
    return JSONResponse(status_code=201, content={"id": _inv["id"], "pass_id": _p["id"],
                                                  "channel": _canal, "created_at": _inv["created_at"]})


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
    _s = await _statut_reel(_p)
    if _s == E.UNLOCKED:
        return await _dto(_p)
    if _s != E.FRIEND_REGISTERED:
        raise HTTPException(status_code=409, detail="Ton ami n'est pas encore inscrit.")
    if _b.get("terms_accepted") is True and not (_p.get("sponsor") or {}).get("terms_accepted"):
        await db[COLL_PASSES].update_one({"id": _p["id"]}, {"$set": {"sponsor.terms_accepted": True}})
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


# ═══════════════════════════════════════════════════════════════════════════
# Routes — publiques (l'ami)
# ═══════════════════════════════════════════════════════════════════════════
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
    return E.dto_public(_p, _s, _now)


@router.post("/pass/{share_token}/join")
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
        return await _reponse_join(_p, _now)
    if _code_http == 409:
        raise _refus(409, E.REFUS_PASS_FERME, "Ce Pass Duo a déjà un invité.")

    if not _email or "@" not in _email or not _nom:
        raise HTTPException(status_code=400, detail="Prénom et e-mail requis.")
    if _b.get("consent_reservation") is not True or _b.get("terms_accepted") is not True:
        raise HTTPException(status_code=400,
                            detail="Merci d'accepter la réservation et les conditions de participation.")
    _ok, _motif = E.invite_autorise(_p, _email, _tel)
    if not _ok:
        raise _refus(409, E.REFUS_AUTO_PARRAINAGE, "Tu ne peux pas être ton propre invité.")

    _course = await db["courses"].find_one({"id": _p.get("course_id")}, {"_id": 0})
    if not _course or _course.get("archived") is True:
        raise HTTPException(status_code=410, detail="Ce cours n'est plus disponible.")
    _offre = await _offre_essai(_course)
    if not _offre:
        logger.error("%s aucune offre d'essai gratuite — join impossible", PREFIXE)
        raise HTTPException(status_code=503, detail="Offre d'essai indisponible pour le moment.")

    # ── 4. index partiel filleul / occurrence (avant tout octroi) ──────────
    _invitee = {"email_norm": _email, "name": _nom, "whatsapp_norm": _tel or None,
                "consent_reservation_at": _iso(_now),
                "marketing_consent": _b.get("marketing_consent") is True}
    try:
        _r = await db[COLL_PASSES].update_one(
            {"id": _p["id"], "invitee": None},
            {"$set": {"invitee": _invitee, "updated_at": _iso(_now)}})
    except Exception as _err:  # noqa: BLE001
        if _est_doublon(_err):
            raise _refus(409, E.REFUS_DEJA_FILLEUL,
                         "Tu es déjà l'invité d'un autre Pass Duo pour cette séance.")
        logger.error("%s pose de l'invité impossible (%s)", PREFIXE, type(_err).__name__)
        raise HTTPException(status_code=503, detail="Inscription impossible pour le moment.")
    if not getattr(_r, "modified_count", 1):
        _p = await _pass_par_token(share_token)
        if E.normaliser_email((_p.get("invitee") or {}).get("email_norm")) == _email:
            return await _reponse_join(_p, _now)
        raise _refus(409, E.REFUS_PASS_FERME, "Ce Pass Duo a déjà un invité.")
    _p["invitee"] = _invitee

    async def _rouvrir():
        await db[COLL_PASSES].update_one({"id": _p["id"]}, {"$set": {"invitee": None}})

    # ── 5. moteur d'essai EXISTANT : ESSAI-4 -> ESSAI-1 -> octroi ──────────
    from api.routes.checkout_routes import (
        _essai4_garde, _essai1_garde, _essai1b_exiger_gratuit, _essai1_liberer,
        _process_successful_payment, _t1_preuve_checkout, _r2b_resoudre_vendeur,
        CheckoutItem)
    _item = CheckoutItem(type="offer", id=str(_offre.get("id")), name=str(_offre.get("name") or "Essai"),
                         price=0.0, quantity=1)
    try:
        await _essai1b_exiger_gratuit([_item])
        _t1_champs = await _t1_preuve_checkout(True, [_item], "")
        await _essai4_garde(_email, str(_offre.get("id")))
    except HTTPException as _e:
        await _rouvrir()
        _raison = (getattr(_e, "headers", None) or {}).get("X-Refus-Raison") or ""
        if _raison == "active_subscription":
            raise _refus(409, E.REFUS_ABONNE_ACTIF,
                         "Tu as déjà un abonnement actif : le Pass Duo est réservé aux nouveaux.")
        raise
    try:
        await _essai1_garde(_email, str(_offre.get("id")), telephone=_tel_brut)
    except HTTPException:
        await _rouvrir()
        raise  # 409 `free_trial_already_used` | `free_trial_already_granted`, tel quel

    _vendeur = ""
    try:
        _vendeur = await _r2b_resoudre_vendeur([_item])
    except Exception:  # noqa: BLE001
        _vendeur = ""
    _transaction_id = "duo_%s" % uuid.uuid4().hex[:12]
    try:
        _octroi = await _process_successful_payment(
            transaction_id=_transaction_id, coach_email=_vendeur, customer_name=_nom,
            customer_email=_email, customer_phone=_tel_brut, items=[_item], total=0,
            currency="CHF", payment_method="free", discount_code=None,
            terms_fields=_t1_champs)
    except Exception as _err:  # noqa: BLE001
        await _essai1_liberer(_email, telephone=_tel_brut)
        await _rouvrir()
        logger.error("%s octroi de l'essai en erreur (%s)", PREFIXE, type(_err).__name__)
        raise HTTPException(status_code=500, detail="L'inscription a échoué, rien n'a été enregistré.")
    _access_code = str((_octroi or {}).get("access_code") or "").strip().upper()

    # Source ADDITIVE sur ce que l'octroi vient d'écrire (`source` d'origine
    # intact : ESSAI-1/ESSAI-6 le lisent), + M2-A `parrainage` sur le forfait.
    _attrib = None
    try:
        from api.routes.shared import m2a_resoudre
        _attrib = await m2a_resoudre(db, _attribution_parrainage(_p, _b.get("attribution")), _email)
    except Exception:  # noqa: BLE001
        _attrib = None
    try:
        _marque = {"pass_duo_id": _p["id"], "pass_duo_role": E.ROLE_INVITEE,
                   "acquisition_source": SOURCE}
        await db["discount_codes"].update_one({"code": _access_code}, {"$set": dict(_marque)})
        _maj_sub = dict(_marque)
        if _attrib:
            _maj_sub["attribution"] = _attrib
        await db["subscriptions"].update_one({"code": _access_code}, {"$set": _maj_sub})
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s marquage pass_duo non écrit (%s)", PREFIXE, type(_err).__name__)

    # ── 6. réservation de l'ami (transaction si disponible, rollback sinon) ──
    async def _travail(session):
        _r = await _reserver_seance_duo(_access_code, _email, _nom, _tel_brut, _course,
                                        _p.get("occurrence"), _p, E.ROLE_INVITEE, True,
                                        session=session)
        _maj = {"status": E.transition(_s, E.FRIEND_REGISTERED),
                "invitee_access_code": _access_code,
                "attribution": _attrib,
                "reservations.invitee_id": _r.get("id"),
                "reservations.invitee_code": _r.get("reservationCode"),
                "updated_at": _iso()}
        _kw = {"session": session} if session is not None else {}
        await db[COLL_PASSES].update_one(
            {"id": _p["id"]},
            {"$set": _maj, "$push": {"events": {"at": _iso(), "type": "friend_registered", "detail": None}}},
            **_kw)
        return _r

    try:
        _resa_ami = await _avec_session(_travail)
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
    if _p.get("status") == E.FRIEND_REGISTERED:
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
        "sponsor_first_name": E.prenom((pass_doc.get("sponsor") or {}).get("name")),
        "course": {k: v for k, v in E.dto_course(pass_doc).items() if k != "id"},
        "occurrence": pass_doc.get("occurrence"),
    }


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
    _items = []
    for _pd in _rows:
        _resas = await _reservations_du_pass(_pd)
        _s = await _statut_reel(_pd, _now, _resas)
        _items.append(E.dto_admin(_pd, _s, E.tickets_du_pass(_pd, _resas, _frontend_url()), _frontend_url()))
    return {"items": _items, "total": _total, "page": _page, "per_page": LISTE_MAX}
