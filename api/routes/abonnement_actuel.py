# -*- coding: utf-8 -*-
# V618 : L'ABONNEMENT ACTUEL D'UNE PERSONNE — UNE SEULE RÈGLE.
"""V618 — `resoudre_abonnement_actuel(db, email)` : la SEULE manière de dire quel abonnement
une PERSONNE possède aujourd'hui.

POURQUOI (audit du 13/10/2026, preuves dans le code) : aucun écran ne résolvait « la personne » ;
chacun partait d'un CODE (adresse /espace/<code>, lien, QR, OTP) ou faisait un
`find_one({email…, active…})` SANS tri ni contrôle d'expiration (e-mail d'accès, lien d'espace
coach, rappel Stripe…). Et les statuts vieillissent : en base, 25 abonnements « active » sont
expirés, 24 codes `active` aussi ; la création manuelle d'un code ne clôturait pas les anciens.
Résultat : un ancien code (expiré mais « active ») pouvait ressortir à la place du nouveau.

LA RÈGLE (explicite, testée) : un abonnement est COURANT s'il
  1. appartient à la personne (e-mail, sans tenir compte de la casse) ;
  2. a le statut `active` (jamais superseded / expired / cancelled / archived / completed) ;
  3. n'est pas expiré (fin de journée suisse, `_v391_est_expire` — la règle V617).
UN courant -> c'est LUI. AUCUN -> état `aucun` (+ le plus récent, pour l'historique seulement).
PLUSIEURS -> `conflit` : on ne choisit PAS (fail closed), on le dit au coach, rien n'est modifié.
Un CODE n'est pas une identité : il sert à retrouver la personne, jamais à imposer son abonnement.
Les compteurs d'un abonnement ne sont jamais mélangés avec ceux d'un autre (lecture seule ici).
"""
import hashlib
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)
PREFIXE = "[V618-ABONNEMENT]"
ETAT_COURANT, ETAT_AUCUN, ETAT_CONFLIT = "courant", "aucun", "conflit"
STATUT_COURANT = "active"
LECTURE_MAX = 100
TYPE_NOTIF = "abonnement_integrite"

router = APIRouter(tags=["abonnement-actuel"])
db = None


def init_db(database):
    global db
    db = database


def _expire(sub, maintenant=None) -> bool:
    from api.routes.shared import _v391_est_expire
    return _v391_est_expire((sub or {}).get("expires_at") or (sub or {}).get("end_date"), maintenant)


def est_courant(sub, maintenant=None) -> bool:
    """PUR. Statut `active` ET non expiré (fin de journée suisse). Rien d'autre."""
    return isinstance(sub, dict) and sub.get("status") == STATUT_COURANT and not _expire(sub, maintenant)


def _cle_tri(sub):
    return (str(sub.get("expires_at") or sub.get("end_date") or ""), str(sub.get("created_at") or ""))


def choisir(subs, maintenant=None) -> dict:
    """PUR. {etat, abonnement, candidats, dernier} à partir des abonnements d'UNE personne."""
    _l = [s for s in (subs or []) if isinstance(s, dict)]
    _c = [s for s in _l if est_courant(s, maintenant)]
    _dernier = sorted(_l, key=_cle_tri, reverse=True)[0] if _l else None
    if len(_c) == 1:
        return {"etat": ETAT_COURANT, "abonnement": _c[0], "candidats": _c, "dernier": _dernier}
    if not _c:
        return {"etat": ETAT_AUCUN, "abonnement": None, "candidats": [], "dernier": _dernier}
    return {"etat": ETAT_CONFLIT, "abonnement": None, "candidats": sorted(_c, key=_cle_tri, reverse=True), "dernier": _dernier}


def _empreinte(email) -> str:
    return hashlib.sha256(("abo|" + str(email or "").strip().lower()).encode("utf-8")).hexdigest()[:12]


async def abonnements_de(database, email) -> list:
    _e = str(email or "").strip().lower()
    if not _e or "@" not in _e:
        return []
    return await database.subscriptions.find(
        {"email": {"$regex": "^%s$" % re.escape(_e), "$options": "i"}},
        {"_id": 0, "id": 1, "code": 1, "email": 1, "status": 1, "expires_at": 1, "end_date": 1, "offer_id": 1,
         "offer_name": 1, "total_sessions": 1, "used_sessions": 1, "remaining_sessions": 1, "created_at": 1,
         "coach_id": 1, "member_slug": 1}).to_list(LECTURE_MAX)


async def resoudre_abonnement_actuel(database, email, maintenant=None, notifier=True) -> dict:
    """LA résolution. Journal sans donnée privée : empreinte de l'e-mail, id choisi, raison."""
    _base = database if database is not None else db
    _r = choisir(await abonnements_de(_base, email), maintenant)
    if _r["etat"] == ETAT_COURANT:
        logger.info("%s subscription_resolution membre=%s chosen_subscription_id=%s reason=current_active",
                    PREFIXE, _empreinte(email), str(_r["abonnement"].get("id"))[:8])
    elif _r["etat"] == ETAT_CONFLIT:
        logger.warning("%s integrity_conflict membre=%s active_count=%d", PREFIXE, _empreinte(email), len(_r["candidats"]))
        if notifier:
            await notifier_conflit(_base, _r["candidats"])
    else:
        logger.info("%s subscription_resolution membre=%s reason=none_current", PREFIXE, _empreinte(email))
    return _r


async def notifier_conflit(database, candidats):
    """Notification INTERNE du coach (une par jeu de codes), idempotente. Codes seulement."""
    if not candidats:
        return
    _codes = sorted({str(c.get("code") or "") for c in candidats if c.get("code")})
    _coach = next((str(c.get("coach_id")) for c in candidats if c.get("coach_id")), "")
    _cle = "integrite_" + hashlib.sha256("|".join(_codes).encode("utf-8")).hexdigest()[:16]
    try:
        await database["notifications"].update_one(
            {"id": _cle}, {"$setOnInsert": {
                "id": _cle, "type": TYPE_NOTIF, "title": "Plusieurs abonnements actifs détectés — à vérifier",
                "message": "Un même client a plusieurs abonnements actifs en même temps (%s). Aucun n'a été choisi "
                           "automatiquement : indique lequel est l'abonnement actuel." % ", ".join(_codes),
                "coach_id": _coach, "read": False, "created_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s notification non écrite (%s)", PREFIXE, type(_err).__name__)


async def code_actuel(database, email):
    """(code | None, resolution) — le CODE de l'abonnement actuel, s'il y en a UN."""
    _r = await resoudre_abonnement_actuel(database, email)
    if _r["etat"] == ETAT_COURANT:
        return str(_r["abonnement"].get("code") or "").strip().upper() or None, _r
    return None, _r


# ── SIMULATION / INTÉGRITÉ (lecture seule) ─────────────────────────────────────
def simuler(subs, codes, maintenant=None) -> dict:
    """PUR. Ce qui, dans les données, peut faire ressortir un ancien abonnement. Rien n'est écrit."""
    from api.routes.shared import _v391_est_expire
    _par = {}
    for s in subs or []:
        _e = str(s.get("email") or "").strip().lower()
        if _e:
            _par.setdefault(_e, []).append(s)
    _conflits, _perimes_clients = [], set()
    for _e, _l in _par.items():
        _r = choisir(_l, maintenant)
        if _r["etat"] == ETAT_CONFLIT:
            _conflits.append({"membre": _empreinte(_e), "codes": [c.get("code") for c in _r["candidats"]]})
        if any(s.get("status") == STATUT_COURANT and not est_courant(s, maintenant) for s in _l):
            _perimes_clients.add(_e)
    _perimes = [s for s in subs or [] if s.get("status") == STATUT_COURANT and not est_courant(s, maintenant)]
    _codes_actifs_expires = [c for c in codes or [] if c.get("active") and _v391_est_expire(c.get("expiresAt"), maintenant)]
    _par_mail = {}
    for c in codes or []:
        if c.get("assignedEmail") and c.get("active"):
            _par_mail.setdefault(str(c["assignedEmail"]).strip().lower(), []).append(c)
    _recover_risque = [e for e, l in _par_mail.items()
                       if any(_v391_est_expire(c.get("expiresAt"), maintenant) for c in l)
                       and any(not _v391_est_expire(c.get("expiresAt"), maintenant) for c in l)]
    return {
        "subscriptions_total": len(subs or []),
        "clients_total": len(_par),
        "clients_conflit_multi_actifs": len(_conflits),
        "conflits": _conflits,
        "subscriptions_statut_active_mais_expirees": len(_perimes),
        "clients_avec_statut_perime": len(_perimes_clients),
        "codes_active_mais_expires": len(_codes_actifs_expires),
        "emails_code_expire_et_code_valide": len(_recover_risque),
        "clients_plusieurs_codes": sum(1 for l in _par.values() if len({s.get("code") for s in l}) > 1),
    }


@router.get("/api/abonnements/integrite")
async def abonnements_integrite(request: Request):
    """Coach (JWT strict, SES clients) : la SIMULATION — ce qui pourrait faire ressortir un ancien
    abonnement. LECTURE SEULE : aucune donnée n'est modifiée."""
    from api.routes import referral_routes as R
    _c = await R._coach_strict(request)
    _f = {} if _c["cle"] == "" else {"coach_id": _c["cle"]}
    _subs = await db.subscriptions.find(_f, {"_id": 0, "email": 1, "code": 1, "status": 1, "expires_at": 1,
                                             "end_date": 1, "created_at": 1}).to_list(5000)
    _codes = await db.discount_codes.find(_f, {"_id": 0, "code": 1, "assignedEmail": 1, "active": 1, "expiresAt": 1}).to_list(5000)
    return dict(simuler(_subs, _codes), lecture_seule=True)


# ── ACCÈS (e-mail « Accède à ton espace ») ─────────────────────────────────────
def _fiche_du_code(fiches, maintenant=None):
    """PUR. La fiche `discount_codes` d'un code : canonique vivante, sinon vivante, sinon la
    plus récente. (Même ordre de confiance que LOT A / V576.)"""
    from api.routes.shared import _v391_est_expire
    _l = [f for f in fiches or [] if isinstance(f, dict)]
    if not _l:
        return None
    _vivantes = [f for f in _l if f.get("active") and not _v391_est_expire(f.get("expiresAt"), maintenant)]
    _can = [f for f in _vivantes if f.get("canonical") is True]
    if len(_can) == 1:
        return _can[0]
    if _vivantes:
        return sorted(_vivantes, key=lambda f: str(f.get("expiresAt") or ""), reverse=True)[0]
    return sorted(_l, key=lambda f: (str(f.get("expiresAt") or ""), str(f.get("created_at") or "")), reverse=True)[0]


async def _fiche(database, code):
    _f = await database.discount_codes.find({"code": {"$regex": "^%s$" % re.escape(str(code or "")), "$options": "i"}},
                                            {"_id": 0}).to_list(20)
    return _fiche_du_code(_f)


async def fiches_pour_acces(database, email, maintenant=None) -> dict:
    """V618 — QUEL(S) code(s) mettre dans l'e-mail d'accès de cette personne.
    courant -> SON code actuel ; conflit -> chacun des abonnements valides (aucun choix
    arbitraire, le coach est prévenu) ; aucun -> repli sur ses fiches de code, la plus récente
    VALIDE d'abord (jamais une fiche expirée devant une fiche valide)."""
    from api.routes.shared import _v391_est_expire
    _r = await resoudre_abonnement_actuel(database, email, maintenant)
    _sortie = []
    if _r["etat"] in (ETAT_COURANT, ETAT_CONFLIT):
        _subs = [_r["abonnement"]] if _r["etat"] == ETAT_COURANT else _r["candidats"]
        for _s in _subs[:3]:
            _f = await _fiche(database, _s.get("code"))
            if _f and all(str(x.get("code")).upper() != str(_f.get("code")).upper() for x in _sortie):
                _sortie.append(_f)
    if not _sortie:
        _e = str(email or "").strip().lower()
        _l = await database.discount_codes.find({"assignedEmail": {"$regex": "^%s$" % re.escape(_e), "$options": "i"},
                                                 "active": True}, {"_id": 0}).to_list(50) if _e else []
        _l.sort(key=lambda f: (not _v391_est_expire(f.get("expiresAt"), maintenant), str(f.get("expiresAt") or "")), reverse=True)
        _sortie = _l[:1]
    return {"etat": _r["etat"], "fiches": _sortie}


async def code_cible_espace(database, email, code_url):
    """V618 — l'espace d'un ANCIEN code est ouvert par une personne PROUVÉE (session d'espace) :
    {code, coach_id} de son espace ACTUEL s'il est différent ; sinon None.
    Garde : le code actuel doit être attribué à la MÊME adresse (celle que la session a prouvée).
    Conflit / aucun abonnement actuel -> None : rien n'est basculé."""
    _e = str(email or "").strip().lower()
    if not _e:
        return None
    _code, _r = await code_actuel(database, _e)
    if not _code or _code == str(code_url or "").strip().upper():
        return None
    _f = await _fiche(database, _code)
    if not _f or str(_f.get("assignedEmail") or "").strip().lower() != _e:
        return None
    return {"code": _code, "coach_id": _f.get("coach_id") or (_r.get("abonnement") or {}).get("coach_id") or ""}
