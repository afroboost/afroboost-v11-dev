# -*- coding: utf-8 -*-
# V607 : LA BOULE DE NEIGE DES ÉVÉNEMENTS — chaque participant reçoit SON lien.
"""V607 — Relais d'invitation pour les ÉVÉNEMENTS (payant, gratuit).

L'essai gratuit et le Pass Duo ont DÉJÀ leur chaîne (`referral_passes`, V556 :
parent / racine / profondeur). Ce module ne les touche PAS. Il donne aux
événements la même capacité, sans obligation : après un paiement confirmé
(événement payant) ou une inscription confirmée (événement gratuit), le
participant reçoit un lien PERSONNEL (`/i/<jeton>`) qu'il peut partager s'il le
veut. Rien n'est bloqué s'il ne partage pas.

COLLECTION `invitation_relais` — un document = un participant d'un événement :
  jeton (unique), campagne_id + racine_jeton (l'invitation du coach), coach_id,
  type_invitation, parent_jeton + parent_relais_id (qui l'a invité ; None =
  l'invitation du coach), generation (1 = invité du coach, 2 = invité de
  l'invité…), inviteur_prenom (SON prénom, affiché à ceux qu'il invite),
  email_empreinte (jamais l'adresse), preuve {nature: stripe|reservation, cle},
  reservation_id, paiement {montant, devise, payment_intent}, created_at.

ANTI-FRAUDE :
  - jeton inventé -> aucun relais (le parent doit exister et être actif) ;
  - même paiement / même réservation -> un seul relais (`preuve_cle` unique) ;
  - une personne = UN relais par invitation : si elle en a déjà un, on le lui
    REND (jamais un 2e) -> une boucle A -> B -> A ne crée rien, l'inviteur
    déjà enregistré ne change JAMAIS ;
  - s'inviter soi-même (même e-mail que le parent) -> relais sans attribution
    (rattaché à la racine, génération 1), compté une seule fois.
"""
import hashlib
import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)
PREFIXE = "[V607-RELAIS]"
COLL = "invitation_relais"
TYPES_RELAIS = ("event_paid", "event_free")
RE_JETON = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
FENETRE_RESERVATION = timedelta(hours=48)

router = APIRouter(tags=["invitation-relais"])
db = None

# Débit des routes PUBLIQUES de relais : elles répondent 200 / 404 selon qu'une
# preuve (session, réservation, accès) existe — sans plafond, ce serait un oracle pour
# deviner des codes. TROIS compteurs, car l'IP seule se falsifie (`CF-Connecting-IP` /
# `X-Forwarded-For` crus sans contrôle de l'origine — dette infra P1-A) :
#   - par IP : 20 essais / 10 min ;
#   - par JETON d'invitation : 30 / 10 min (un attaquant doit viser UNE invitation
#     réelle : changer d'IP ne lui rend pas d'essais) ;
#   - par ROUTE, toutes IP confondues : 300 / 10 min (plafond absolu).
# Les entrées expirées sont retirées une à une ; jamais de remise à zéro globale.
DEBIT_FENETRE_S = 600
DEBIT_MAX = 20
DEBIT_MAX_JETON = 30
DEBIT_MAX_ROUTE = 300
_DEBITS = {}


def _ip(request) -> str:
    try:
        from api.routes.referral_routes import _ip as _ip_r
        return _ip_r(request)
    except Exception:  # noqa: BLE001
        return "?"


def _consommer(cle, maximum, maintenant) -> bool:
    _l = [x for x in _DEBITS.get(cle, []) if maintenant - x < DEBIT_FENETRE_S]
    if len(_l) >= maximum:
        _DEBITS[cle] = _l
        return False
    _l.append(maintenant)
    _DEBITS[cle] = _l
    return True


def _purger(maintenant) -> None:
    if len(_DEBITS) <= 5000:
        return
    for _k in [k for k, v in _DEBITS.items() if not v or maintenant - v[-1] >= DEBIT_FENETRE_S]:
        _DEBITS.pop(_k, None)


def exiger_debit(request, route="relais", jeton=None) -> None:
    """429 dès qu'UN des trois plafonds (IP, jeton, route) est atteint."""
    import time as _t
    _now = _t.time()
    _purger(_now)
    _ok = _consommer("route:" + route, DEBIT_MAX_ROUTE, _now)
    _ok = _consommer("ip:%s:%s" % (route, _ip(request)), DEBIT_MAX, _now) and _ok
    if jeton:
        _ok = _consommer("jeton:%s:%s" % (route, jeton), DEBIT_MAX_JETON, _now) and _ok
    if not _ok:
        raise HTTPException(status_code=429, detail="Trop de tentatives. Réessaie plus tard.")


def init_db(database):
    global db
    db = database


async def assurer_index(database) -> None:
    try:
        await database[COLL].create_index("jeton", unique=True)
        await database[COLL].create_index("preuve_cle", unique=True)
        await database[COLL].create_index([("campagne_id", 1), ("email_empreinte", 1)])
        await database[COLL].create_index([("campagne_id", 1), ("generation", 1)])
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s index non posés (%s)", PREFIXE, type(_err).__name__)


def _doublon(err) -> bool:
    """E11000 (index unique), quelle que soit la classe levée."""
    return type(err).__name__ == "DuplicateKeyError" or "e11000" in str(err).lower() or "duplicate" in str(err).lower()


def _iso():
    return datetime.now(timezone.utc).isoformat()


def empreinte_email(email) -> str:
    _e = str(email or "").strip().lower()
    return hashlib.sha256(("relais|" + _e).encode("utf-8")).hexdigest()[:24] if _e else ""


def prenom(nom) -> str:
    """Le prénom affichable : 1er mot, jamais une adresse."""
    _n = str(nom or "").strip()
    if not _n or "@" in _n:
        return ""
    return re.sub(r"[<>\"']", "", _n.split()[0])[:40]


def jeton_valide(t) -> str:
    _t = str(t or "").strip()
    return _t if RE_JETON.match(_t) else ""


async def resoudre_parent(database, jeton):
    """(campagne, relais_parent|None) d'un jeton : l'invitation ACTIVE du coach
    (événement) ou un relais dont l'invitation racine est encore active."""
    _t = jeton_valide(jeton)
    if not _t:
        return None, None
    _camp = await database["referral_campaigns"].find_one({"share_token": _t}, {"_id": 0})
    if _camp:
        return (_camp, None) if (_camp.get("status") == "active" and _camp.get("type") in TYPES_RELAIS) else (None, None)
    _rel = await database[COLL].find_one({"jeton": _t}, {"_id": 0})
    if not _rel:
        return None, None
    _camp = await database["referral_campaigns"].find_one({"id": _rel.get("campagne_id")}, {"_id": 0})
    if not _camp or _camp.get("status") != "active":
        return None, None
    return _camp, _rel


def _doc_relais(camp, parent, email, nom, preuve_nature, preuve_cle, auto_invitation=False) -> dict:
    _attribue = parent is not None and not auto_invitation
    return {
        "id": str(uuid.uuid4()),
        "jeton": secrets.token_urlsafe(24),
        "campagne_id": camp.get("id"),
        "racine_jeton": camp.get("share_token"),
        "coach_id": camp.get("coach_id") or "",
        "type_invitation": camp.get("type"),
        "parent_jeton": (parent or {}).get("jeton") if _attribue else camp.get("share_token"),
        "parent_relais_id": (parent or {}).get("id") if _attribue else None,
        "generation": (int((parent or {}).get("generation") or 1) + 1) if _attribue else 1,
        "inviteur_prenom": prenom(nom),
        "email_empreinte": empreinte_email(email),
        "auto_invitation": bool(auto_invitation),
        "preuve_nature": preuve_nature,
        "preuve_cle": "%s:%s" % (preuve_nature, preuve_cle),
        "created_at": _iso(),
        "attribue_le": _iso(),
    }


async def creer_relais(database, *, jeton_parent, email, nom, preuve_nature, preuve_cle,
                       reservation_id=None, paiement=None):
    """Le relais du participant (idempotent), ou None si le jeton ne mène à rien."""
    _base = database if database is not None else db
    _camp, _parent = await resoudre_parent(_base, jeton_parent)
    if not _camp or not preuve_cle:
        return None
    _cle = "%s:%s" % (preuve_nature, preuve_cle)
    _deja = await _base[COLL].find_one({"preuve_cle": _cle}, {"_id": 0})
    if _deja:
        return _deja                                    # même paiement / réservation : rien de neuf
    _emp = empreinte_email(email)
    if _emp:
        _existant = await _base[COLL].find_one({"campagne_id": _camp.get("id"), "email_empreinte": _emp}, {"_id": 0})
        if _existant:
            return _existant                            # une personne = un relais ; inviteur figé
    _auto = bool(_emp) and _parent is not None and _parent.get("email_empreinte") == _emp
    _doc = _doc_relais(_camp, _parent, email, nom, preuve_nature, preuve_cle, auto_invitation=_auto)
    if reservation_id:
        _doc["reservation_id"] = str(reservation_id)[:80]
    if isinstance(paiement, dict):
        _doc["paiement"] = {k: paiement.get(k) for k in ("montant", "devise", "payment_intent") if k in paiement}
    try:
        await _base[COLL].insert_one(dict(_doc))
    except Exception as _err:  # noqa: BLE001
        if _doublon(_err):
            return await _base[COLL].find_one({"preuve_cle": _cle}, {"_id": 0})
        raise
    logger.info("%s relais %s créé (campagne %s, génération %s)", PREFIXE, _doc["id"][:8],
                str(_camp.get("id"))[:8], _doc["generation"])
    try:
        from api.routes import invitation_suivi as SV
        _ev = "paiement_confirme" if preuve_nature == "stripe" else "inscription_confirmee"
        await SV.enregistrer(_base, _ev, type_invitation=_doc["type_invitation"], campagne_id=_doc["campagne_id"],
                             coach_id=_doc["coach_id"], jeton=_doc["parent_jeton"], generation=_doc["generation"],
                             montant=(paiement or {}).get("montant"), cle=_cle)
        await SV.enregistrer(_base, "nouvelle_invitation_generee", type_invitation=_doc["type_invitation"],
                             campagne_id=_doc["campagne_id"], coach_id=_doc["coach_id"], jeton=_doc["jeton"],
                             generation=_doc["generation"], cle=_doc["id"])
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s suivi non écrit (%s)", PREFIXE, type(_err).__name__)
    return _doc


def _lire(obj, cle, defaut=None):
    try:
        _v = obj.get(cle)
    except Exception:  # noqa: BLE001
        _v = getattr(obj, cle, None)
    return defaut if _v is None else _v


async def relais_depuis_paiement_stripe(database, session, metadata=None):
    """Webhook `checkout.session.completed` PAYÉ avec `invitation_token` -> relais.
    FAIL-OPEN : l'achat encaissé ne dépend jamais de la boule de neige."""
    try:
        _meta = metadata if isinstance(metadata, dict) else dict(_lire(session, "metadata", {}) or {})
        _jeton = jeton_valide(_meta.get("invitation_token"))
        if not _jeton or str(_lire(session, "payment_status", "") or "") != "paid":
            return None
        _details = _lire(session, "customer_details", {}) or {}
        try:
            _email = _details.get("email")
            _nom = _details.get("name")
        except Exception:  # noqa: BLE001
            _email, _nom = None, None
        _email = _email or _lire(session, "customer_email") or _meta.get("customer_email") or ""
        _nom = _meta.get("customer_name") or _nom or ""
        # L'offre payée doit être CELLE de l'invitation (un jeton ne s'achète pas ailleurs).
        _camp, _ = await resoudre_parent(database, _jeton)
        _offre = str(_meta.get("offer_id") or "")
        # FAIL-CLOSED : l'offre payée doit être PRÉSENTE et identique à celle de l'invitation.
        if not _camp or not _camp.get("offer_id") or _offre != str(_camp.get("offer_id")):
            return None
        return await creer_relais(database, jeton_parent=_jeton, email=_email, nom=_nom, preuve_nature="stripe",
                                  preuve_cle=str(_lire(session, "id") or ""),
                                  paiement={"montant": float(_lire(session, "amount_total", 0) or 0) / 100.0,
                                            "devise": str(_lire(session, "currency", "chf") or "chf"),
                                            "payment_intent": _lire(session, "payment_intent")})
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s relais non créé après paiement (%s)", PREFIXE, type(_err).__name__)
        return None


def dto_relais(rel, camp=None, base_url="https://afroboost.com") -> dict:
    """Ce que voit le PARTICIPANT : son lien et son prénom. Aucune autre donnée."""
    _b = str(base_url or "https://afroboost.com").rstrip("/")
    return {"jeton": rel.get("jeton"), "share_url": "%s/i/%s" % (_b, rel.get("jeton")),
            "prenom": rel.get("inviteur_prenom") or "", "generation": rel.get("generation"),
            "type": rel.get("type_invitation"), "titre": (camp or {}).get("title") or None}


def _front():
    try:
        from api.routes.referral_routes import _frontend_url
        return _frontend_url()
    except Exception:  # noqa: BLE001
        return "https://afroboost.com"


@router.get("/api/invitation/relais/session/{session_id}")
async def relais_par_session(session_id: str, request: Request = None):
    """Après le paiement : le lien personnel de l'acheteur. L'identifiant de session
    Stripe (non devinable) est la seule clé ; 404 tant que le webhook n'est pas passé.
    Débit large (le navigateur réessaie quelques fois pendant le webhook)."""
    if request is not None:
        exiger_debit(request, route="session")
    _s = str(session_id or "").strip()
    if not re.match(r"^cs_[A-Za-z0-9_]{6,200}$", _s):
        raise HTTPException(status_code=404, detail="Introuvable")
    _r = await db[COLL].find_one({"preuve_cle": "stripe:" + _s}, {"_id": 0})
    if not _r:
        raise HTTPException(status_code=404, detail="Introuvable")
    _c = await db["referral_campaigns"].find_one({"id": _r.get("campagne_id")}, {"_id": 0, "title": 1})
    return dto_relais(_r, _c, _front())


@router.post("/api/invitation/relais/reservation")
async def relais_par_reservation(request: Request):
    """ÉVÉNEMENT GRATUIT : `{jeton, reservation_code}` après l'inscription. La
    réservation doit exister, être RÉCENTE (48 h) et porter l'offre de l'invitation."""
    try:
        _b = await request.json()
    except Exception:  # noqa: BLE001
        _b = {}
    _b = _b if isinstance(_b, dict) else {}
    _jeton = jeton_valide(_b.get("jeton"))
    exiger_debit(request, route="reservation", jeton=_jeton or "?")
    _code = str(_b.get("reservation_code") or "").strip()
    if not _jeton or not re.match(r"^[A-Za-z0-9_-]{4,40}$", _code):
        raise HTTPException(status_code=404, detail="Introuvable")
    _camp, _ = await resoudre_parent(db, _jeton)
    if not _camp or _camp.get("type") != "event_free":
        raise HTTPException(status_code=404, detail="Introuvable")
    _res = await db["reservations"].find_one({"reservationCode": _code}, {"_id": 0})
    if not _res or not _camp.get("offer_id") or str(_res.get("offerId") or "") != str(_camp.get("offer_id")):
        raise HTTPException(status_code=404, detail="Introuvable")
    try:
        _cree = datetime.fromisoformat(str(_res.get("createdAt") or _res.get("created_at") or "").replace("Z", "+00:00"))
        if _cree.tzinfo is None:
            _cree = _cree.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - _cree > FENETRE_RESERVATION:
            raise HTTPException(status_code=404, detail="Introuvable")
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=404, detail="Introuvable")
    _r = await creer_relais(db, jeton_parent=_jeton, email=_res.get("userEmail"), nom=_res.get("userName"),
                            preuve_nature="reservation", preuve_cle=str(_res.get("id") or _code),
                            reservation_id=_res.get("id"))
    if not _r:
        raise HTTPException(status_code=404, detail="Introuvable")
    return dto_relais(_r, _camp, _front())


def _recent(valeur) -> bool:
    try:
        _d = valeur if isinstance(valeur, datetime) else datetime.fromisoformat(str(valeur or "").replace("Z", "+00:00"))
        if _d.tzinfo is None:
            _d = _d.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - _d <= FENETRE_RESERVATION
    except Exception:  # noqa: BLE001
        return False


@router.post("/api/invitation/relais/inscription")
async def relais_par_inscription(request: Request):
    """ÉVÉNEMENT GRATUIT, parcours de la vitrine : l'inscription gratuite ouvre un
    accès (code AFR) puis l'espace. `{jeton, code}` : l'accès doit exister, être
    RÉCENT (48 h) et porter l'offre de l'invitation. Le lien est facultatif."""
    try:
        _b = await request.json()
    except Exception:  # noqa: BLE001
        _b = {}
    _b = _b if isinstance(_b, dict) else {}
    _jeton = jeton_valide(_b.get("jeton"))
    exiger_debit(request, route="inscription", jeton=_jeton or "?")
    _code = str(_b.get("code") or "").strip().upper()
    if not _jeton or not re.match(r"^[A-Z0-9-]{4,40}$", _code):
        raise HTTPException(status_code=404, detail="Introuvable")
    _camp, _ = await resoudre_parent(db, _jeton)
    if not _camp or _camp.get("type") != "event_free":
        raise HTTPException(status_code=404, detail="Introuvable")
    _sub = await db["subscriptions"].find_one({"code": _code}, {"_id": 0, "code": 1, "offer_id": 1, "created_at": 1,
                                                                "email": 1, "name": 1})
    if not _sub or not _recent(_sub.get("created_at")) \
            or not _camp.get("offer_id") or str(_sub.get("offer_id") or "") != str(_camp.get("offer_id")):
        raise HTTPException(status_code=404, detail="Introuvable")
    _r = await creer_relais(db, jeton_parent=_jeton, email=_sub.get("email"), nom=_sub.get("name"),
                            preuve_nature="inscription", preuve_cle=_code)
    if not _r:
        raise HTTPException(status_code=404, detail="Introuvable")
    return dto_relais(_r, _camp, _front())


@router.get("/api/referral/campaigns-relais/{campagne_id}/chaine")
async def chaine_campagne(campagne_id: str, request: Request):
    """Coach (JWT strict, ses invitations seulement) : la chaîne RECONSTRUITE —
    qui a invité qui, génération par génération. Prénoms seulement, 500 au plus."""
    from api.routes import referral_routes as R
    _c = await R._coach_strict(request)
    _camp = await db["referral_campaigns"].find_one({"id": str(campagne_id)[:64], "coach_id": _c["cle"]}, {"_id": 0})
    if not _camp:
        raise HTTPException(status_code=404, detail="Invitation introuvable")
    _rows = await db[COLL].find({"campagne_id": _camp["id"]}, {"_id": 0}).sort("created_at", 1).to_list(500)
    _par_id = {r["id"]: r for r in _rows}
    _noeuds = [{"id": r["id"], "prenom": r.get("inviteur_prenom") or "", "generation": r.get("generation"),
                "invite_par": (_par_id.get(r.get("parent_relais_id")) or {}).get("inviteur_prenom")
                if r.get("parent_relais_id") else "coach",
                "parent_relais_id": r.get("parent_relais_id"), "preuve": r.get("preuve_nature"),
                "montant": (r.get("paiement") or {}).get("montant"), "created_at": r.get("created_at")}
               for r in _rows]
    return {"campagne_id": _camp["id"], "type": _camp.get("type"), "total": len(_noeuds), "noeuds": _noeuds}
