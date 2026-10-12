# -*- coding: utf-8 -*-
# V607 : SUIVI DES INVITATIONS — un journal honnête, par TYPE d'invitation.
"""V607 — Le funnel des invitations (Essai gratuit, Pass Duo, Événement gratuit,
Événement payant), dans UNE collection : `invitation_events`.

RÈGLE D'HONNÊTETÉ : on n'enregistre que ce que l'on sait. Un clic sur
« Inviter sur WhatsApp » ouvre WhatsApp avec le message prérempli : c'est
`partage_whatsapp_declenche`, JAMAIS « WhatsApp envoyé » (WhatsApp ne nous dit
pas si le message est parti). Aucun libellé de ce module ne parle d'envoi.

DEUX SOURCES :
  - le navigateur (`POST /api/invitation/suivi`, public) — seulement les
    événements de la liste blanche EVENEMENTS_CLIENT, rattachés à un jeton
    RÉEL (invitation du coach, pass de chaîne ou relais d'événement) ; jeton
    inconnu -> rien n'est écrit. Un même visiteur ne compte qu'UNE fois par
    événement et par jeton (clé idempotente) ;
  - le serveur (`enregistrer(...)`) — création, activation, essai débloqué,
    paiement confirmé, nouvelle invitation générée : la preuve est en base.

Chaque ligne porte `type_invitation` (trial | pass_duo | event_free |
event_paid), `generation` (0 = le coach, 1 = l'invité du coach, 2 = l'invité
de l'invité…), `campagne_id` et `coach_id` (clé du propriétaire, "" =
plateforme) : le cockpit filtre par type et par coach. Aucune donnée
personnelle : ni e-mail, ni téléphone, ni jeton en clair (empreinte).
"""
import hashlib
import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
PREFIXE = "[V607-SUIVI]"
COLL = "invitation_events"
TYPES = ("trial", "pass_duo", "event_free", "event_paid")

# Ce que le NAVIGATEUR peut déclarer (il ne prouve rien d'autre).
EVENEMENTS_CLIENT = (
    "lien_ouvert",                  # la page d'invitation est affichée
    "seance_choisie",               # l'invité a choisi SA séance (essai)
    "etape_invitation_atteinte",    # l'écran « invite 1 ami » est affiché
    "partage_whatsapp_declenche",   # WhatsApp ouvert avec le message prérempli
    "partage_autre_declenche",      # partage natif / copie du lien
    "reservation_commencee",        # clic sur le bouton de réservation
)
# Ce que seul le SERVEUR écrit (preuve en base).
EVENEMENTS_SERVEUR = (
    "invitation_creee", "lien_active", "essai_debloque", "inscription_confirmee",
    "reservation_confirmee", "paiement_confirme", "nouvelle_invitation_generee",
)
EVENEMENTS = EVENEMENTS_CLIENT + EVENEMENTS_SERVEUR

# Libellés du cockpit (le mot « envoyé » n'apparaît nulle part).
LIBELLES = {
    "invitation_creee": "Invitation créée",
    "lien_active": "Lien activé",
    "lien_ouvert": "Lien ouvert",
    "seance_choisie": "Séance choisie",
    "etape_invitation_atteinte": "Étape invitation atteinte",
    "partage_whatsapp_declenche": "Partage WhatsApp déclenché",
    "partage_autre_declenche": "Autre partage déclenché",
    "essai_debloque": "Essai débloqué",
    "inscription_confirmee": "Inscription confirmée",
    "reservation_commencee": "Réservation commencée",
    "reservation_confirmee": "Réservation confirmée",
    "paiement_confirme": "Paiement confirmé",
    "nouvelle_invitation_generee": "Nouvelle invitation générée",
}

router = APIRouter(tags=["invitation-suivi"])
db = None
DEBIT_FENETRE_S = 600
DEBIT_MAX = 120                 # événements par IP et par 10 min
_DEBITS = {}


def init_db(database):
    global db
    db = database


def _doublon(err) -> bool:
    """E11000 (index unique), quelle que soit la classe levée."""
    return type(err).__name__ == "DuplicateKeyError" or "e11000" in str(err).lower() or "duplicate" in str(err).lower()


def _iso():
    return datetime.now(timezone.utc).isoformat()


def empreinte(valeur) -> str:
    """16 hexa : jamais un jeton ni un identifiant d'appareil en clair."""
    return hashlib.sha256(str(valeur or "").encode("utf-8")).hexdigest()[:16]


async def assurer_index(database) -> None:
    try:
        await database[COLL].create_index("cle", unique=True, sparse=True)
        await database[COLL].create_index([("coach_id", 1), ("type_invitation", 1), ("evenement", 1)])
        await database[COLL].create_index([("campagne_id", 1), ("evenement", 1)])
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s index non posés (%s)", PREFIXE, type(_err).__name__)


def _generation(v):
    try:
        _g = int(v)
    except (TypeError, ValueError):
        return None
    return _g if 0 <= _g <= 1000 else None


async def enregistrer(database, evenement, *, type_invitation, campagne_id=None, coach_id=None,
                      jeton=None, generation=None, montant=None, cle=None, source="serveur", extra=None):
    """Écrit UNE ligne ; `cle` rend l'écriture idempotente (rejeu = rien).
    FAIL-OPEN : le suivi ne fait jamais échouer le parcours qui l'appelle."""
    _base = database if database is not None else db
    if _base is None or evenement not in EVENEMENTS or type_invitation not in TYPES:
        return False
    _doc = {
        "id": str(uuid.uuid4()), "at": _iso(), "evenement": evenement, "source": source,
        "type_invitation": type_invitation, "campagne_id": campagne_id or None,
        "coach_id": (coach_id or "").strip().lower(), "generation": _generation(generation),
        "jeton": empreinte(jeton) if jeton else None,
    }
    if montant is not None:
        try:
            _doc["montant"] = round(float(montant), 2)
        except (TypeError, ValueError):
            pass
    if cle:
        _doc["cle"] = empreinte(cle) + empreinte("%s|%s" % (evenement, cle))
    if isinstance(extra, dict):
        _doc.update({k: v for k, v in extra.items() if k not in _doc})
    try:
        await _base[COLL].insert_one(dict(_doc))
        return True
    except Exception as _err:  # noqa: BLE001
        if _doublon(_err):
            return False
        logger.warning("%s écriture impossible (%s)", PREFIXE, type(_err).__name__)
        return False


async def resoudre_jeton(database, jeton) -> dict:
    """{type_invitation, campagne_id, coach_id, generation} d'un jeton RÉEL, sinon {}.
    Ordre : invitation du coach (génération 0) > relais d'événement > pass de chaîne."""
    _base = database if database is not None else db
    _t = str(jeton or "").strip()
    if _base is None or not _t or len(_t) > 128 or "$" in _t:
        return {}
    try:
        _c = await _base["referral_campaigns"].find_one({"share_token": _t}, {"_id": 0, "id": 1, "type": 1, "coach_id": 1})
        if _c and _c.get("type") in TYPES:
            return {"type_invitation": _c["type"], "campagne_id": _c.get("id"),
                    "coach_id": _c.get("coach_id") or "", "generation": 0}
        _r = await _base["invitation_relais"].find_one({"jeton": _t}, {"_id": 0})
        if _r:
            return {"type_invitation": _r.get("type_invitation"), "campagne_id": _r.get("campagne_id"),
                    "coach_id": _r.get("coach_id") or "", "generation": _r.get("generation")}
        _p = await _base["referral_passes"].find_one({"share_token": _t}, {"_id": 0})
        if _p:
            from api.routes import referral_engine as E
            _l = E.lignage(_p)
            _cid = _l.get("campaign_id")
            _camp = await _base["referral_campaigns"].find_one({"id": _cid}, {"_id": 0, "type": 1, "coach_id": 1}) \
                if _cid else None
            _type = (_camp or {}).get("type") or "pass_duo"
            return {"type_invitation": _type if _type in TYPES else "pass_duo", "campagne_id": _cid,
                    "coach_id": (_camp or {}).get("coach_id") or "",
                    "generation": (int(_l.get("depth") or 0) + 1) if _cid else int(_l.get("depth") or 0)}
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s jeton illisible (%s)", PREFIXE, type(_err).__name__)
    return {}


def _ip(request) -> str:
    try:
        from api.routes.referral_routes import _ip as _ip_r
        return _ip_r(request)
    except Exception:  # noqa: BLE001
        return "?"


def _debit_ok(ip) -> bool:
    _now = time.time()
    _l = [t for t in _DEBITS.get(ip, []) if _now - t < DEBIT_FENETRE_S]
    if len(_l) >= DEBIT_MAX:
        _DEBITS[ip] = _l
        return False
    _l.append(_now)
    _DEBITS[ip] = _l
    if len(_DEBITS) > 5000:
        _DEBITS.clear()
    return True


@router.post("/api/invitation/suivi")
async def suivi_client(request: Request):
    """Public. `{jeton, evenement, visiteur?}` -> 204. Jeton inconnu, événement
    hors liste ou débit dépassé : 204 aussi (rien n'est révélé, rien n'est écrit)."""
    try:
        _b = await request.json()
    except Exception:  # noqa: BLE001
        _b = {}
    _b = _b if isinstance(_b, dict) else {}
    _ev = str(_b.get("evenement") or "")
    _jeton = str(_b.get("jeton") or "").strip()
    _visiteur = str(_b.get("visiteur") or "").strip()[:64]
    if _ev in EVENEMENTS_CLIENT and _jeton and _debit_ok(_ip(request)):
        _r = await resoudre_jeton(db, _jeton)
        if _r.get("type_invitation"):
            await enregistrer(db, _ev, type_invitation=_r["type_invitation"], campagne_id=_r.get("campagne_id"),
                              coach_id=_r.get("coach_id"), jeton=_jeton, generation=_r.get("generation"),
                              cle=("%s|%s" % (_jeton, _visiteur)) if _visiteur else None, source="client")
    return JSONResponse(status_code=204, content=None)


def agreger(lignes) -> dict:
    """Pur. {evenement: n}, {generation: {evenement: n}}, CA (paiements)."""
    _par_ev, _par_gen, _ca = {}, {}, 0.0
    for _l in lignes or []:
        _e = _l.get("evenement")
        _par_ev[_e] = _par_ev.get(_e, 0) + 1
        _g = _l.get("generation")
        _cle = "inconnue" if _g is None else ("3+" if _g >= 3 else str(_g))
        _par_gen.setdefault(_cle, {})
        _par_gen[_cle][_e] = _par_gen[_cle].get(_e, 0) + 1
        if _e == "paiement_confirme" and isinstance(_l.get("montant"), (int, float)):
            _ca += float(_l["montant"])
    return {"evenements": _par_ev, "par_generation": _par_gen, "ca": round(_ca, 2)}


# Le funnel de l'essai gratuit, dans l'ordre demandé par Bassi.
FUNNEL_ESSAI = ("lien_ouvert", "seance_choisie", "etape_invitation_atteinte",
                "partage_whatsapp_declenche", "essai_debloque", "reservation_confirmee")
FUNNEL_EVENEMENT_PAYANT = ("lien_ouvert", "reservation_commencee", "paiement_confirme",
                           "partage_whatsapp_declenche", "nouvelle_invitation_generee")


@router.get("/api/referral/campaigns-suivi/funnel")
async def suivi_funnel(request: Request, type: str = "", campagne_id: str = ""):
    """Coach (JWT strict). Funnel du coach appelant (super-admin : plateforme ""),
    filtrable par type et par invitation."""
    from api.routes import referral_routes as R
    _c = await R._coach_strict(request)
    _q = {"coach_id": _c["cle"]}
    if type:
        if type not in TYPES:
            raise HTTPException(status_code=422, detail="type : %s" % " | ".join(TYPES))
        _q["type_invitation"] = type
    if campagne_id:
        _q["campagne_id"] = str(campagne_id)[:64]
    _lignes = await db[COLL].find(_q, {"_id": 0, "evenement": 1, "generation": 1, "montant": 1}).to_list(20000)
    _a = agreger(_lignes)
    _ordre = FUNNEL_ESSAI if type == "trial" else (FUNNEL_EVENEMENT_PAYANT if type == "event_paid" else EVENEMENTS)
    _a["funnel"] = [{"evenement": e, "libelle": LIBELLES.get(e, e), "n": _a["evenements"].get(e, 0)} for e in _ordre]
    _g = _a["par_generation"]
    _a["invitations_generation_2"] = sum(v.get("nouvelle_invitation_generee", 0) + v.get("essai_debloque", 0)
                                         for k, v in _g.items() if k == "2")
    _a["invitations_generation_3_plus"] = sum(v.get("nouvelle_invitation_generee", 0) + v.get("essai_debloque", 0)
                                              for k, v in _g.items() if k == "3+")
    _a["libelles"] = LIBELLES
    return _a
