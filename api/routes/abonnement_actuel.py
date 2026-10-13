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


PLATEFORME = ""
_SANS_LOCATAIRE = ("", "none", "null", "bassi_default", "contact.artboost@gmail.com")


def locataire(coach_id) -> str:
    """PUR. Le PÉRIMÈTRE (coach) d'un document : la plateforme (super-admin, valeurs historiques
    vides / `bassi_default`) = "" ; un coach partenaire = son e-mail. Deux périmètres ne se mélangent
    JAMAIS (V618-b, revue de sécurité) : ni résolution, ni conflit, ni notification croisés."""
    _c = str(coach_id or "").strip().lower()
    return PLATEFORME if _c in _SANS_LOCATAIRE else _c


def _expire(sub, maintenant=None) -> bool:
    from api.routes.shared import _v391_est_expire
    return _v391_est_expire((sub or {}).get("expires_at") or (sub or {}).get("end_date"), maintenant)


def est_courant(sub, maintenant=None) -> bool:
    """PUR. Statut `active` ET non expiré (fin de journée suisse). Rien d'autre."""
    return isinstance(sub, dict) and sub.get("status") == STATUT_COURANT and not _expire(sub, maintenant)


def _cle_tri(sub):
    return (str(sub.get("expires_at") or sub.get("end_date") or ""), str(sub.get("created_at") or ""))


def choisir(subs, maintenant=None) -> dict:
    """PUR. {etat, abonnement, candidats, dernier} à partir des abonnements d'UNE personne.
    V618i : un abonnement supprimé n'existe pas — ni actuel, ni « dernier »."""
    _l = [s for s in (subs or []) if isinstance(s, dict) and not est_supprime(s)]
    _c = [s for s in _l if est_courant(s, maintenant)]
    _dernier = sorted(_l, key=_cle_tri, reverse=True)[0] if _l else None
    if len(_c) == 1:
        return {"etat": ETAT_COURANT, "abonnement": _c[0], "candidats": _c, "dernier": _dernier}
    if not _c:
        return {"etat": ETAT_AUCUN, "abonnement": None, "candidats": [], "dernier": _dernier}
    return {"etat": ETAT_CONFLIT, "abonnement": None, "candidats": sorted(_c, key=_cle_tri, reverse=True), "dernier": _dernier}


def _empreinte(email) -> str:
    return hashlib.sha256(("abo|" + str(email or "").strip().lower()).encode("utf-8")).hexdigest()[:12]


SOURCE_AUTO_SERVICE = "promo_validate"


def est_supprime(sub) -> bool:
    """V618i : abonnement supprimé par le coach (pierre tombale)."""
    return str((sub or {}).get("status") or "").strip().lower() == "deleted"


def de_confiance(sub) -> bool:
    """V618 PHASE 2 (sécurité F3) : un abonnement créé par la route PUBLIQUE /discount-codes/validate
    (aucune preuve d'identité) ne peut ni désigner l'abonnement actuel, ni créer un conflit, ni
    servir de cible de redirection / lien d'accès. Il reste utilisable sur son propre code."""
    return str((sub or {}).get("source") or "") != SOURCE_AUTO_SERVICE


async def abonnements_de(database, email) -> list:
    """Les abonnements d'une adresse, avec leur PÉRIMÈTRE EFFECTIF (`_locataire`) : `coach_id` de
    l'abonnement, sinon celui de la FICHE de son code (V618 phase 2, sécurité F1 : les abonnements
    manuels n'avaient pas de `coach_id` et tombaient tous dans la plateforme)."""
    _e = str(email or "").strip().lower()
    if not _e or "@" not in _e:
        return []
    _l = await database.subscriptions.find(
        {"email": {"$regex": "^%s$" % re.escape(_e), "$options": "i"}},
        {"_id": 0, "id": 1, "code": 1, "email": 1, "status": 1, "expires_at": 1, "end_date": 1, "offer_id": 1,
         "offer_name": 1, "total_sessions": 1, "used_sessions": 1, "remaining_sessions": 1, "created_at": 1,
         "coach_id": 1, "member_slug": 1, "source": 1}).to_list(LECTURE_MAX)
    _sans = sorted({str(x.get("code") or "") for x in _l if not str(x.get("coach_id") or "").strip() and x.get("code")})
    _coach_fiche = {}
    if _sans:
        _vars = sorted(set(_sans) | {c.upper() for c in _sans})
        for _f in await database.discount_codes.find({"code": {"$in": _vars}}, {"_id": 0, "code": 1, "coach_id": 1}).to_list(200):
            _k = str(_f.get("code") or "").upper()
            if str(_f.get("coach_id") or "").strip():
                _coach_fiche.setdefault(_k, _f.get("coach_id"))
    for x in _l:
        x["_locataire"] = locataire(x.get("coach_id") or _coach_fiche.get(str(x.get("code") or "").upper()))
    # V618i : un abonnement SUPPRIMÉ n'existe plus pour le résolveur (ni actuel, ni conflit, ni historique).
    return [x for x in _l if de_confiance(x) and not est_supprime(x)]


async def resoudre_abonnement_actuel(database, email, maintenant=None, notifier=True, perimetre=None) -> dict:
    """LA résolution. `perimetre` (V618-b) : le coach dans lequel on résout (`locataire()`), ou None
    pour toutes ses inscriptions (e-mail d'accès : chaque code proposé reste celui de SON titulaire).
    Journal sans donnée privée : empreinte de l'e-mail, id choisi, raison."""
    _base = database if database is not None else db
    _subs = await abonnements_de(_base, email)
    if perimetre is not None:
        _subs = [x for x in _subs if x.get("_locataire", locataire(x.get("coach_id"))) == perimetre]
    _r = choisir(_subs, maintenant)
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
    """Notification INTERNE, idempotente, PAR COACH : chaque coach ne voit QUE les codes de son
    périmètre, et seulement s'il y a conflit CHEZ LUI (deux coachs différents = pas un conflit)."""
    _par = {}
    for c in candidats or []:
        _par.setdefault(c.get("_locataire", locataire(c.get("coach_id"))), []).append(c)
    for _loc, _l in _par.items():
        if len(_l) >= 2:
            await _notifier_un(database, _loc, _l)


async def _notifier_un(database, coach, candidats):
    _codes = sorted({str(c.get("code") or "") for c in candidats if c.get("code")})
    _coach = coach
    _cle = "integrite_" + hashlib.sha256(("%s|" % coach + "|".join(_codes)).encode("utf-8")).hexdigest()[:16]
    try:
        await database["notifications"].update_one(
            {"id": _cle}, {"$setOnInsert": {
                "id": _cle, "type": TYPE_NOTIF, "title": "Plusieurs abonnements actifs détectés — à vérifier",
                "message": "Un même client a plusieurs abonnements actifs en même temps (%s). Aucun n'a été choisi "
                           "automatiquement : indique lequel est l'abonnement actuel." % ", ".join(_codes),
                "coach_id": _coach, "read": False, "created_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s notification non écrite (%s)", PREFIXE, type(_err).__name__)


async def code_actuel(database, email, perimetre=None):
    """(code | None, resolution) — le CODE de l'abonnement actuel, s'il y en a UN."""
    _r = await resoudre_abonnement_actuel(database, email, perimetre=perimetre)
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
        if _e and de_confiance(s):
            # V618-b : un client = une adresse DANS un périmètre (coach) ; deux coachs ≠ conflit.
            _par.setdefault((_e, s.get("_locataire", locataire(s.get("coach_id")))), []).append(s)
    _conflits, _perimes_clients = [], set()
    for (_e, _loc), _l in _par.items():
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
    _subs = await db.subscriptions.find({}, {"_id": 0, "email": 1, "code": 1, "status": 1, "expires_at": 1,
                                             "end_date": 1, "created_at": 1, "coach_id": 1, "source": 1}).to_list(5000)
    _codes = await db.discount_codes.find({}, {"_id": 0, "code": 1, "assignedEmail": 1, "active": 1, "expiresAt": 1,
                                               "coach_id": 1}).to_list(5000)
    # Périmètre EFFECTIF (sécurité F1) : coach de l'abonnement, sinon celui de la fiche de son code ;
    # un coach partenaire ne voit QUE son périmètre.
    _coach_code = {}
    for _x in _codes:
        if str(_x.get("coach_id") or "").strip():
            _coach_code.setdefault(str(_x.get("code") or "").upper(), _x.get("coach_id"))
    for _x in _subs:
        _x["_locataire"] = locataire(_x.get("coach_id") or _coach_code.get(str(_x.get("code") or "").upper()))
    if _c["cle"] != "":
        _subs = [x for x in _subs if x["_locataire"] == locataire(_c["cle"])]
        _codes = [x for x in _codes if locataire(x.get("coach_id")) == locataire(_c["cle"])]
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


async def _fiche(database, code, perimetre=None):
    """La fiche d'un code ; avec `perimetre`, SEULEMENT parmi celles de ce coach (sécurité F8 :
    une chaîne de code recréée par un autre coach ne mélange jamais les deux)."""
    _f = await database.discount_codes.find({"code": {"$regex": "^%s$" % re.escape(str(code or "")), "$options": "i"}},
                                            {"_id": 0}).to_list(20)
    if perimetre is not None:
        _f = [x for x in _f if locataire(x.get("coach_id")) == perimetre]
    return _fiche_du_code(_f)


async def fiches_pour_acces(database, email, maintenant=None) -> dict:
    """V618 — QUEL(S) code(s) mettre dans l'e-mail d'accès de cette personne.
    courant -> SON code actuel ; conflit -> chacun des abonnements valides (aucun choix
    arbitraire, le coach est prévenu) ; aucun -> repli sur ses fiches de code, la plus récente
    VALIDE d'abord (jamais une fiche expirée devant une fiche valide)."""
    from api.routes.shared import _v391_est_expire
    _r = await resoudre_abonnement_actuel(database, email, maintenant)
    _e_norm = str(email or "").strip().lower()
    _sortie = []
    if _r["etat"] in (ETAT_COURANT, ETAT_CONFLIT):
        _subs = [_r["abonnement"]] if _r["etat"] == ETAT_COURANT else _r["candidats"]
        for _s in _subs[:3]:
            _f = await _fiche(database, _s.get("code"))
            # V618-b (revue de sécurité) : un lien d'accès n'ouvre QUE le code dont CETTE adresse
            # est le TITULAIRE — jamais le code d'une autre personne (11 abonnements en base ont un
            # e-mail différent du titulaire de leur code : club, famille, saisie).
            if not _f or str(_f.get("assignedEmail") or "").strip().lower() != _e_norm:
                continue
            if all(str(x.get("code")).upper() != str(_f.get("code")).upper() for x in _sortie):
                _sortie.append(_f)
    if not _sortie:
        _e = str(email or "").strip().lower()
        _l = await database.discount_codes.find({"assignedEmail": {"$regex": "^%s$" % re.escape(_e), "$options": "i"},
                                                 "active": True}, {"_id": 0}).to_list(50) if _e else []
        _l.sort(key=lambda f: (not _v391_est_expire(f.get("expiresAt"), maintenant), str(f.get("expiresAt") or "")), reverse=True)
        # Sécurité F5 : la fiche RETENUE pour ce code (`_fiche`) doit, elle aussi, avoir cette adresse
        # pour titulaire — jamais une vieille fiche restée active d'un code repris par quelqu'un d'autre.
        for _f in _l:
            _ref = await _fiche(database, _f.get("code"))
            if _ref and str(_ref.get("assignedEmail") or "").strip().lower() == _e:
                _sortie = [_ref]
                break
    return {"etat": _r["etat"], "fiches": _sortie}


async def code_cible_espace(database, email, code_url, coach_session=None):
    """V618 — l'espace d'un ANCIEN code est ouvert par une personne PROUVÉE (session d'espace) :
    {code, coach_id} de son espace ACTUEL s'il est différent ; sinon None.
    Garde : le code actuel doit être attribué à la MÊME adresse (celle que la session a prouvée).
    Conflit / aucun abonnement actuel -> None : rien n'est basculé."""
    _e = str(email or "").strip().lower()
    if not _e:
        return None
    # V618-b : on résout DANS le périmètre (coach) du code de l'adresse — jamais vers l'espace d'un
    # autre coach — et la fiche cible doit avoir CETTE adresse pour titulaire (même preuve que l'OTP).
    _f_url = await _fiche(database, code_url)
    if not _f_url or str(_f_url.get("assignedEmail") or "").strip().lower() != _e:
        return None
    _per = locataire(_f_url.get("coach_id"))
    # Sécurité F7 : la session doit appartenir au MÊME coach que le code de l'adresse.
    if coach_session is not None and locataire(coach_session) != _per:
        return None
    _code, _r = await code_actuel(database, _e, perimetre=_per)
    if not _code or _code == str(code_url or "").strip().upper():
        return None
    _f = await _fiche(database, _code, perimetre=_per)
    if not _f or str(_f.get("assignedEmail") or "").strip().lower() != _e or locataire(_f.get("coach_id")) != _per:
        return None
    return {"code": _code, "coach_id": _f.get("coach_id") or (_r.get("abonnement") or {}).get("coach_id") or ""}


# ── V618 PHASE 2 : RESTITUTION D'UNE SÉANCE (annulation) ───────────────────────
STATUT_SUPPRIME = "deleted"      # V618i : supprimé par le coach — jamais courant, jamais réactivé
STATUTS_HISTORIQUES = ("superseded", "expired", "cancelled", "archived", STATUT_SUPPRIME)


def cible_restitution(reservation, subs_du_code, maintenant=None):
    """PUR. L'abonnement à re-créditer quand CETTE réservation est annulée :
      1. `reservation.subscriptionId` (ou `subscription_id`) s'il existe parmi les abonnements
         du code — exactement lui, même s'il est historique (ses compteurs, pas son statut) ;
      2. sinon l'UNIQUE abonnement actuel du code ;
      3. sinon AUCUN (jamais « le premier trouvé ») : seule la fiche du code est restituée.
    `subscriptionId` présent mais introuvable -> AUCUN (on ne crédite pas un autre abonnement)."""
    _r = reservation or {}
    _l = [s for s in (subs_du_code or []) if isinstance(s, dict)]
    _sid = str(_r.get("subscriptionId") or _r.get("subscription_id") or "").strip()
    if _sid:
        return next((s for s in _l if str(s.get("id") or "") == _sid), None)
    _c = [s for s in _l if est_courant(s, maintenant)]
    return _c[0] if len(_c) == 1 else None


def statut_apres_restitution(sub, maintenant=None):
    """PUR. Le statut à écrire après une restitution, ou None (ne PAS toucher au statut).
    Seul un `completed` (épuisé) encore dans ses dates se rouvre en `active` ; un abonnement
    historique (superseded / expired / cancelled / archived) ou expiré n'est JAMAIS réactivé."""
    _s = sub or {}
    if _s.get("status") == "completed" and not _expire(_s, maintenant):
        return STATUT_COURANT
    return None


async def bascule_scan(database, sub_scanne):
    """V618 PHASE 2 — SCAN À LA PORTE d'un ANCIEN QR. Le code scanné IDENTIFIE la personne ;
    ses droits viennent de son abonnement ACTUEL. (code, abonnement actuel complet) si :
    l'abonnement scanné n'est PAS actuel, la personne est TITULAIRE du code scanné, et elle a UN
    abonnement actuel (même périmètre coach) sur un code dont elle est aussi titulaire.
    Sinon None -> le scan garde le code scanné (et ses refus habituels)."""
    _s = sub_scanne or {}
    if est_courant(_s):
        return None
    _e = str(_s.get("email") or "").strip().lower()
    if not _e:
        return None
    _f = await _fiche(database, _s.get("code"))
    if not _f or str(_f.get("assignedEmail") or "").strip().lower() != _e:
        return None
    _per = locataire(_f.get("coach_id") if _f.get("coach_id") is not None else _s.get("coach_id"))
    _r = await resoudre_abonnement_actuel(database, _e, perimetre=_per)
    if _r["etat"] != ETAT_COURANT:
        return None
    _code = str(_r["abonnement"].get("code") or "").strip().upper()
    if not _code or _code == str(_s.get("code") or "").strip().upper():
        return None
    _f2 = await _fiche(database, _code, perimetre=_per)
    if not _f2 or str(_f2.get("assignedEmail") or "").strip().lower() != _e:
        return None
    _complet = await database.subscriptions.find_one({"id": _r["abonnement"].get("id")}, {"_id": 0})
    return (_code, _complet) if _complet else None


MSG_ANCIEN_CODE = "Ce code n'est plus ton abonnement actuel : utilise le code de ton abonnement en cours."


async def garde_abonnement_actuel(database, sub, email=None):
    """V618 PHASE 2 — GARDE COMMUNE avant d'UTILISER un abonnement (réserver, débiter, valider).
    (ok, motif). Refuse seulement ce qui est prouvé : la personne a un abonnement ACTUEL différent
    (ancien code) ou, en conflit, l'abonnement présenté n'est pas l'un des abonnements actuels.
    Aucun abonnement actuel -> la règle existante (forfait_utilisable) décide seule.
    En conflit, le code présenté par la personne elle-même est accepté s'il est actuel : ce n'est
    pas un choix arbitraire du système."""
    _s = sub or {}
    _e = str(email or _s.get("email") or "").strip().lower()
    if not _e or not _s.get("id") or not de_confiance(_s):
        return True, ""
    _f = await _fiche(database, _s.get("code"))
    _r = await resoudre_abonnement_actuel(database, _e, perimetre=locataire(_s.get("coach_id") or (_f or {}).get("coach_id")))
    if _r["etat"] == ETAT_COURANT and str(_r["abonnement"].get("id")) != str(_s.get("id")):
        return False, MSG_ANCIEN_CODE
    if _r["etat"] == ETAT_CONFLIT and str(_s.get("id")) not in {str(c.get("id")) for c in _r["candidats"]}:
        return False, MSG_ANCIEN_CODE
    return True, ""


# ═══════════════ V618c — SÉCURITÉ : OTP, ANNULATION DEPUIS L'ESPACE ═══════════════

def _norm(adresse) -> str:
    return str(adresse or "").strip().lower()


def contact_otp(fiches, subs, email_demande="", maintenant=None):
    """PUR. (adresse, coach_id) à qui l'OTP d'un code peut être envoyé, ou (None, None).

    Même règle de fiche que V618 (canonique vivante > vivante > plus récente) :
      * une fiche HISTORIQUE n'est jamais retenue quand une fiche vivante existe ;
      * plusieurs fiches candidates avec des TITULAIRES ou des COACHS différents -> l'adresse
        demandée doit désigner exactement l'un d'eux, sinon AUCUN (fail closed) ;
      * fiche sans titulaire -> l'adresse d'un abonnement DE CONFIANCE du code (jamais un
        abonnement créé par la route publique /validate) ; plusieurs adresses -> seule
        l'adresse demandée, si elle en fait partie.
    """
    from api.routes.shared import _v391_est_expire
    _dem = _norm(email_demande)
    _l = [f for f in (fiches or []) if isinstance(f, dict)]
    _viv = [f for f in _l if f.get("active") and not _v391_est_expire(f.get("expiresAt"), maintenant)]
    _cands = _viv or _l
    _cid = None
    if _cands:
        _avec = [f for f in _cands if _norm(f.get("assignedEmail"))]
        _titulaires = {(_norm(f.get("assignedEmail")), locataire(f.get("coach_id"))) for f in _avec}
        if len(_titulaires) > 1:
            _miens = [f for f in _avec if _norm(f.get("assignedEmail")) == _dem]
            if not _miens or len({locataire(f.get("coach_id")) for f in _miens}) > 1:
                return None, None
            _f = _fiche_du_code(_miens, maintenant)
        else:
            _f = _fiche_du_code(_avec or _cands, maintenant)
        _em = _norm((_f or {}).get("assignedEmail"))
        _cid = (_f or {}).get("coach_id")
        if _em:
            return _em, _cid
    _s = [s for s in (subs or []) if isinstance(s, dict) and de_confiance(s) and not est_supprime(s)
          and _norm(s.get("email"))]
    if _cid is not None and str(_cid).strip():
        _s = [s for s in _s if locataire(s.get("coach_id") or _cid) == locataire(_cid)]
    _adresses = {_norm(s.get("email")) for s in _s}
    if _dem and _dem in _adresses:
        _em = _dem
    elif len(_adresses) == 1:
        _em = next(iter(_adresses))
    else:
        return None, None
    _sien = choisir([s for s in _s if _norm(s.get("email")) == _em], maintenant)
    _ref = _sien["abonnement"] or _sien["dernier"] or {}
    return _em, (_cid or _ref.get("coach_id"))


async def reservation_de_la_session(database, reservation, charge) -> bool:
    """V618c — la réservation appartient-elle à la SESSION d'espace qui demande l'annulation ?

    Même définition que la liste « Mes séances » de l'espace :
      * membre de club (slug) : `member_slug` de la réservation = celui de la session, ou
        ancienne réservation sans slug, à SON adresse, sur CE code ;
      * titulaire : réservation à SON adresse (prouvée par OTP), et dont le code est celui de la
        session OU un code dont il est aussi TITULAIRE, chez le MÊME coach (ancien code d'une
        même personne) — jamais le code d'un autre titulaire ni d'un autre coach.
    Une réservation sans code (achat à l'unité) n'est annulable que par son adresse."""
    _r, _c = reservation or {}, charge or {}
    _code = str(_c.get("code") or "").strip().upper()
    _mail = _norm(_c.get("email"))
    _slug = str(_c.get("slug") or "").strip()
    if not _code or not _mail:
        return False
    _rcode = str(_r.get("discountCode") or _r.get("promoCode") or "").strip().upper()
    _rmail = _norm(_r.get("userEmail"))
    _rslug = str(_r.get("member_slug") or "").strip()
    if _slug:
        if _rslug:
            return _rslug == _slug and _rcode == _code
        return _rmail == _mail and _rcode == _code
    if _rmail != _mail:          # même règle que la liste du titulaire : par SON adresse
        return False
    if not _rcode or _rcode == _code:
        return True
    # PARITÉ AVEC LA PORTE D'ENTRÉE (revue de sécurité) : la réservation d'un AUTRE code n'est
    # annulable que si l'OTP de CE code-là reviendrait à la même adresse, chez le MÊME coach que la
    # session — exactement `contact_otp`, la règle qui ouvre l'espace de ce code.
    _rx = {"$regex": "^%s$" % re.escape(_rcode), "$options": "i"}
    _fiches = await database.discount_codes.find(
        {"code": _rx}, {"_id": 0, "code": 1, "assignedEmail": 1, "coach_id": 1, "active": 1, "expiresAt": 1,
                        "canonical": 1, "created_at": 1}).to_list(20)
    _subs = await database.subscriptions.find(
        {"code": _rx}, {"_id": 0, "id": 1, "email": 1, "coach_id": 1, "status": 1, "expires_at": 1, "end_date": 1,
                        "created_at": 1, "source": 1}).to_list(50)
    _em, _cid = contact_otp(_fiches, _subs, _mail)
    return _em == _mail and locataire(_cid) == locataire(_c.get("coach_id"))


# ═══════════════ V618f — TABLEAU DE BORD « CODES » : CLASSEMENT PAR LA RÈGLE CANONIQUE ═══════════════

ETAT_HISTORIQUE = "historique"


def classer_codes(codes, subs, coach_par_code=None, maintenant=None):
    """PUR. Pose `v618` sur chaque fiche de `codes` et corrige l'étiquette `v532` quand le code porte
    des abonnements : c'est l'ABONNEMENT ACTUEL (résolveur, par personne et par coach) qui décide,
    plus la seule date de la fiche.
      * un abonnement du code est l'actuel de son titulaire -> la fiche canonique du code est
        `actuel`, avec la fin et les séances de CET abonnement (ex. fiche à 6/7 au 30/09 mais
        abonnement à 1/32 au 05/06/2027) ; les autres fiches du même code restent historiques ;
      * un abonnement du code est en conflit (plusieurs actuels) -> `conflit` (rien n'est choisi) ;
      * des abonnements, aucun actuel -> `historique` (jamais « actuel » sur la foi de la fiche) ;
      * aucun abonnement (code promo, club…) -> la règle LOT A d'avant, inchangée.
    Lecture seule : ne modifie que les dictionnaires de réponse."""
    _cpc = {str(k).upper(): v for k, v in (coach_par_code or {}).items()}
    _par = {}
    for s in subs or []:
        if not isinstance(s, dict) or not de_confiance(s) or est_supprime(s) or not _norm(s.get("email")):
            continue
        _loc = locataire(s.get("coach_id") or _cpc.get(str(s.get("code") or "").upper()))
        _par.setdefault((_norm(s.get("email")), _loc), []).append(s)
    _etat_sub = {}
    for _l in _par.values():
        _r = choisir(_l, maintenant)
        for s in _l:
            _etat_sub[id(s)] = ("actuel" if _r["etat"] == ETAT_COURANT and s is _r["abonnement"]
                                else "conflit" if _r["etat"] == ETAT_CONFLIT and any(s is c for c in _r["candidats"])
                                else ETAT_HISTORIQUE)
    _subs_code = {}
    for (_m, _loc), _l in _par.items():
        for s in _l:
            _subs_code.setdefault((str(s.get("code") or "").strip().upper(), _loc), []).append(s)
    _fiches_code = {}
    for c in codes or []:
        if isinstance(c, dict) and c.get("code"):
            _fiches_code.setdefault(str(c["code"]).strip().upper(), []).append(c)
    for _k, _fiches in _fiches_code.items():
        # Cloisonnement : les abonnements du MÊME périmètre que les fiches (jamais ceux d'un autre coach).
        _locs = {locataire(f.get("coach_id") or _cpc.get(_k)) for f in _fiches}
        _ss = [s for _l in _locs for s in (_subs_code.get((_k, _l)) or [])]
        if not _ss:
            continue
        _actuels = [s for s in _ss if _etat_sub.get(id(s)) == "actuel"]
        _conflits = [s for s in _ss if _etat_sub.get(id(s)) == "conflit"]
        if _actuels and any((f.get("v532") or {}).get("classement") == "a_verifier" for f in _fiches):
            # Doublons VIVANTS d'un même code (LOT A : À VÉRIFIER) : on ne choisit pas entre eux ;
            # l'information « porte l'abonnement actuel » est ajoutée, l'étiquette reste.
            for f in _fiches:
                f["v618"] = {"etat": "actuel"}
        elif _actuels:
            _sub = _actuels[0]
            _choisie = _fiche_du_code(_fiches, maintenant)
            for f in _fiches:
                f["v618"] = {"etat": "actuel" if f is _choisie else ETAT_HISTORIQUE}
                _e = dict(f.get("v532") or {})
                if f is _choisie:
                    try:
                        _tot = int(float(_sub.get("total_sessions") or 0))
                        _ut = int(float(_sub.get("used_sessions") or 0))
                    except (TypeError, ValueError):
                        _tot, _ut = None, None
                    _e.update(classement="actuel", motif="abonnement_actuel", utilise=_ut, total=_tot,
                              restant=(max(0, _tot - _ut) if _tot else None),
                              expire_le=_sub.get("expires_at") or _sub.get("end_date"))
                elif _e.get("classement") == "actuel":
                    _e.update(classement=ETAT_HISTORIQUE, motif="remplace")
                f["v532"] = _e
        elif _conflits:
            for f in _fiches:
                f["v618"] = {"etat": "conflit"}
        else:
            for f in _fiches:
                f["v618"] = {"etat": ETAT_HISTORIQUE}
                _e = dict(f.get("v532") or {})
                if _e.get("classement") == "actuel":
                    _e.update(classement=ETAT_HISTORIQUE, motif="abonnement_historique")
                    f["v532"] = _e
    return codes


async def enrichir_codes(database, codes, appelant=None, admin=True):
    """V618f — `classer_codes` sur la liste de GET /discount-codes. Deux lectures, ZÉRO écriture ;
    une erreur laisse la liste telle quelle (l'écran d'hier reste l'écran d'hier).

    CLOISONNEMENT (revue de sécurité) : un coach partenaire voit aussi les anciennes fiches sans
    `coach_id` (règle historique de la liste) ; il ne reçoit l'état V618 (dates, séances, conflit
    d'un abonnement) QUE pour les fiches de SON périmètre. Les autres restent exactement telles que
    la liste les rendait avant V618f."""
    try:
        _cible = codes
        if not admin:
            _moi = locataire(appelant)
            _cible = [c for c in codes or [] if isinstance(c, dict) and _moi and locataire(c.get("coach_id")) == _moi]
            if not _cible:
                return codes
        _subs = await database.subscriptions.find(
            {}, {"_id": 0, "id": 1, "code": 1, "email": 1, "status": 1, "expires_at": 1, "end_date": 1,
                 "created_at": 1, "coach_id": 1, "source": 1, "used_sessions": 1, "total_sessions": 1,
                 "remaining_sessions": 1}).to_list(5000)
        _cpc = {}
        for f in await database.discount_codes.find({}, {"_id": 0, "code": 1, "coach_id": 1}).to_list(5000):
            if str(f.get("coach_id") or "").strip():
                _cpc.setdefault(str(f.get("code") or "").upper(), f.get("coach_id"))
        classer_codes(_cible, _subs, _cpc)      # modifie les fiches ciblées sur place
        return codes
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s classement des codes impossible (%s)", PREFIXE, type(_err).__name__)
        return codes


# ═══════════════ V618i — SUPPRESSION FIABLE D'UN ABONNEMENT ═══════════════
#
# Avant : « Supprimer » ne déplaçait que la FICHE du code dans la corbeille ; ses abonnements
# restaient `active` (mesure du 13/10 : 8 abonnements « supprimés » encore courants). Désormais un
# abonnement supprimé devient une PIERRE TOMBALE `status: "deleted"` : conservé pour l'historique
# (paiements, réservations passées, mouvements de séances gardent leur référence), mais exclu à
# jamais du résolveur, de l'espace, du scan, des réservations, de l'événement, du ChatWidget, des
# e-mails d'accès et de l'OTP. Aucune route ne le réactive (seul le super-admin peut restaurer).

COLL_SESSIONS = "subscriber_sessions"


def _rx(code):
    return {"$regex": "^%s$" % re.escape(str(code or "").strip()), "$options": "i"}


async def supprimer_abonnements(database, subs, par, motif):
    """Pierre tombale, PAR id, conditionnelle (le statut lu doit être encore le même) : un abonnement
    modifié entre la lecture et l'écriture n'est pas touché. Compteurs, paiements, dates : intacts."""
    _maintenant = datetime.now(timezone.utc).isoformat()
    _faits = []
    for s in subs or []:
        if not isinstance(s, dict) or not s.get("id") or est_supprime(s):
            continue
        _r = await database.subscriptions.update_one(
            {"id": s.get("id"), "status": s.get("status")},
            {"$set": {"status": STATUT_SUPPRIME, "statut_avant_suppression": s.get("status"),
                      "deleted_at": _maintenant, "deleted_by": par, "deleted_reason": motif}})
        if getattr(_r, "modified_count", 0) == 1:
            _faits.append(s.get("id"))
    if _faits:
        logger.info("%s %d abonnement(s) supprimé(s) (%s)", PREFIXE, len(_faits), motif)
    return _faits


async def revoquer_sessions_du_code(database, code, motif):
    """Les sessions d'espace ouvertes sur ce code sont fermées : un ancien jeton ne rouvre rien."""
    _n = 0
    async for _s in database[COLL_SESSIONS].find({"code": _rx(code), "revoked": {"$ne": True}}, {"_id": 0, "jti": 1}):
        if not _s.get("jti"):
            continue
        _r = await database[COLL_SESSIONS].update_one(
            {"jti": _s.get("jti"), "revoked": {"$ne": True}},
            {"$set": {"revoked": True, "revoked_at": datetime.now(timezone.utc).isoformat(), "revoked_reason": motif}})
        _n += getattr(_r, "modified_count", 0)
    return _n


async def apercu_suppression(database, fiche, maintenant=None):
    """Ce que « Supprimer » va faire pour CETTE fiche — lu, jamais écrit. Les abonnements du code sont
    supprimés SEULEMENT s'il ne reste aucune autre fiche VIVANTE du même code (un doublon expiré
    qu'on retire ne touche jamais l'abonnement porté par la fiche vivante)."""
    from api.routes.shared import _v391_est_expire
    _f = fiche or {}
    _code = str(_f.get("code") or "").strip()
    _now = (maintenant or datetime.now(timezone.utc)).isoformat()
    _autres = [x for x in await database.discount_codes.find({"code": _rx(_code)}, {"_id": 0}).to_list(50)
               if x.get("id") != _f.get("id")]
    _autres_vivantes = [x for x in _autres if x.get("active") and not _v391_est_expire(x.get("expiresAt"))]
    _subs = [x for x in await database.subscriptions.find({"code": _rx(_code)}, {"_id": 0}).to_list(100)
             if not est_supprime(x)]
    _touches = [] if _autres_vivantes else _subs
    _r = choisir(_touches) if _touches else {"abonnement": None, "dernier": None}
    _ref = _r.get("abonnement") or _r.get("dernier") or {}
    try:
        _restantes = (int(float(_ref.get("remaining_sessions"))) if _ref.get("remaining_sessions") is not None
                      else max(0, int(float(_f.get("maxUses") or 0)) - int(float(_f.get("used") or 0))))
    except (TypeError, ValueError):
        _restantes = None
    _resas = await database.reservations.find({"$or": [{"discountCode": _rx(_code)}, {"promoCode": _rx(_code)}]},
                                              {"_id": 0, "datetime": 1}).to_list(1000)
    _passees = sum(1 for r in _resas if str(r.get("datetime") or "") < _now[:16])
    _futures = len(_resas) - _passees
    _mouv = await database["seance_mouvements"].count_documents({"code": _rx(_code)})
    _encaisse = 0.0
    for _x in [_f] + _touches:
        try:
            _encaisse = max(_encaisse, float(_x.get("montant_encaisse") or 0))
        except (TypeError, ValueError):
            pass
    _hist = bool(_passees or _mouv or _encaisse)
    return {
        "code": _code, "client": _f.get("assignedEmail") or _ref.get("email") or "",
        "abonnement": _ref.get("offer_name") or _f.get("offerName") or _code,
        "seances_restantes": _restantes,
        "expiration": str(_ref.get("expires_at") or _f.get("expiresAt") or "")[:10] or None,
        "abonnements_supprimes": len(_touches),
        "abonnement_conserve_par_autre_fiche": bool(_autres_vivantes and _subs),
        "historique": {"paiement_encaisse": _encaisse, "reservations_passees": _passees,
                       "reservations_futures": _futures, "mouvements_seances": _mouv, "conserve": _hist},
        "_subs": _touches,
    }


async def _proprietaire_sub(sub, cle):
    """Périmètre d'un abonnement pour le coach `cle` (vide = super-admin)."""
    if cle == "":
        return True
    _c = locataire(cle)
    return bool(_c) and locataire((sub or {}).get("coach_id")) == _c


@router.get("/api/abonnements/orphelins")
async def abonnements_orphelins(request: Request):
    """V618i — abonnements encore actifs dont le code n'a PLUS AUCUNE fiche (fiche supprimée avant
    V618i, ou jamais créée) : invisibles dans « Codes », ils restaient pourtant utilisables. Liste
    pour que le coach les supprime LUI-MÊME. JWT strict, SON périmètre, lecture seule."""
    from api.routes import referral_routes as R
    _c = await R._coach_strict(request)
    _codes = {str(x.get("code") or "").strip().upper()
              for x in await db.discount_codes.find({}, {"_id": 0, "code": 1}).to_list(10000)}
    _sortie = []
    for s in await db.subscriptions.find({"status": "active"}, {"_id": 0}).to_list(5000):
        if str(s.get("code") or "").strip().upper() in _codes or not await _proprietaire_sub(s, _c["cle"]):
            continue
        _sortie.append({"id": s.get("id"), "code": s.get("code"), "email": s.get("email"),
                        "abonnement": s.get("offer_name") or s.get("code"),
                        "seances_restantes": s.get("remaining_sessions"),
                        "expiration": str(s.get("expires_at") or "")[:10] or None,
                        "courant": est_courant(s)})
    _sortie.sort(key=lambda x: (not x["courant"], str(x.get("code") or "")))
    return {"orphelins": _sortie[:200], "total": len(_sortie)}


@router.delete("/api/abonnements/{subscription_id}")
async def supprimer_abonnement_orphelin(subscription_id: str, request: Request):
    """V618i — supprime UN abonnement dont le code n'a plus de fiche vivante (les autres se suppriment
    depuis la carte du code, qui retire la fiche ET l'abonnement ensemble). JWT strict + propriétaire :
    un coach ne supprime jamais l'abonnement d'un autre coach (403)."""
    from api.routes import referral_routes as R
    from api.routes.shared import _v391_est_expire
    _c = await R._coach_strict(request)
    _s = await db.subscriptions.find_one({"id": str(subscription_id or "")[:64]}, {"_id": 0})
    if not _s or est_supprime(_s):
        raise HTTPException(status_code=404, detail="Abonnement introuvable")
    if not await _proprietaire_sub(_s, _c["cle"]):
        raise HTTPException(status_code=403, detail="Cet abonnement ne vous appartient pas")
    _vivantes = [x for x in await db.discount_codes.find({"code": _rx(_s.get("code"))}, {"_id": 0}).to_list(20)
                 if x.get("active") and not _v391_est_expire(x.get("expiresAt"))]
    if _vivantes:
        raise HTTPException(status_code=409, detail="Ce code existe encore : supprimez-le depuis sa carte (code + abonnement).")
    _faits = await supprimer_abonnements(db, [_s], _c["email"], "suppression_coach")
    if not _faits:
        raise HTTPException(status_code=409, detail="L'abonnement vient d'être modifié. Rechargez et réessayez.")
    _reste = [x for x in await db.subscriptions.find({"code": _rx(_s.get("code"))}, {"_id": 0, "status": 1}).to_list(50)
              if not est_supprime(x)]
    _sessions = 0 if _reste else await revoquer_sessions_du_code(db, _s.get("code"), "abonnement_supprime")
    _apres = await resoudre_abonnement_actuel(db, _s.get("email"), notifier=False,
                                              perimetre=locataire(_s.get("coach_id")))
    return {"success": True, "supprime": _faits[0], "sessions_revoquees": _sessions,
            "abonnement_actuel_apres": (_apres.get("abonnement") or {}).get("code") if _apres["etat"] == ETAT_COURANT else None,
            "etat_apres": _apres["etat"]}


async def peut_gerer_abonnement(database, sub, appelant, admin=False) -> bool:
    """V618i — UNE règle de propriété pour modifier / ajuster / supprimer un abonnement : le
    super-admin gère tout ; un coach partenaire, SEULEMENT son périmètre effectif (coach de
    l'abonnement, sinon celui de la fiche de son code). Un abonnement de la plateforme (sans coach)
    n'appartient à aucun partenaire."""
    if admin:
        return True
    _moi = locataire(appelant)
    if not _moi:
        return False
    _eff = (sub or {}).get("coach_id")
    if not str(_eff or "").strip():
        _f = await _fiche(database, (sub or {}).get("code"))
        _eff = (_f or {}).get("coach_id")
    return locataire(_eff) == _moi


MSG_SUPPRIME = "Cet abonnement a été supprimé : il ne peut plus être modifié ni réactivé."
