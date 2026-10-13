# -*- coding: utf-8 -*-
# V607 : LA BOULE DE NEIGE DES ÉVÉNEMENTS — chaque participant reçoit SON lien.
"""V607 — Relais d'invitation pour les ÉVÉNEMENTS (payant, gratuit).

L'essai gratuit et le Pass Duo ont DÉJÀ leur chaîne (`referral_passes`, V556 :
parent / racine / profondeur). Ce module ne les touche PAS. Il donne aux
événements la même capacité, sans obligation : après un paiement confirmé
(événement payant) ou une inscription confirmée dans l'espace (événement gratuit), le
participant reçoit un lien PERSONNEL (`/i/<jeton>`) qu'il peut partager s'il le
veut. Rien n'est bloqué s'il ne partage pas.

COLLECTION `invitation_relais` — un document = un participant d'un événement :
  jeton (unique), campagne_id + racine_jeton (l'invitation du coach), coach_id,
  type_invitation, parent_jeton + parent_relais_id (qui l'a invité ; None =
  l'invitation du coach), generation (1 = invité du coach, 2 = invité de
  l'invité…), inviteur_prenom (SON prénom, affiché à ceux qu'il invite),
  email_empreinte (jamais l'adresse), preuve {nature: stripe|inscription, cle},
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

# Débit des routes publiques de relais. AUCUNE n'est un oracle : la session Stripe
# n'est pas devinable et l'inscription exige la session d'espace (code e-mail prouvé).
# Ce débit ne protège donc que la charge : par IP seulement (jamais par invitation ni
# global, ce qui permettrait de BLOQUER les vrais participants), mémoire BORNÉE
# (au-delà de DEBIT_CLES_MAX clés, les plus anciennes sont évincées).
DEBIT_FENETRE_S = 600
DEBIT_MAX = 60
DEBIT_CLES_MAX = 5000
_DEBITS = {}


def _ip(request) -> str:
    try:
        from api.routes.referral_routes import _ip as _ip_r
        return _ip_r(request)
    except Exception:  # noqa: BLE001
        return "?"


def exiger_debit(request) -> None:
    import time as _t
    _now = _t.time()
    _cle = str(_ip(request))[:64]
    _l = [x for x in _DEBITS.pop(_cle, []) if _now - x < DEBIT_FENETRE_S]
    if len(_l) >= DEBIT_MAX:
        _DEBITS[_cle] = _l
        raise HTTPException(status_code=429, detail="Trop de tentatives. Réessaie plus tard.")
    _l.append(_now)
    _DEBITS[_cle] = _l[-DEBIT_MAX:]                 # réinsérée = la plus récente
    while len(_DEBITS) > DEBIT_CLES_MAX:            # mémoire bornée : on évince la plus ancienne
        _DEBITS.pop(next(iter(_DEBITS)), None)


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
    # V610o — PROGRAMME AMBASSADEUR : la place de ce filleul est confirmée (ce relais n'existe
    # qu'après) -> +1 Boost au parrain DIRECT, une seule fois (clé `boost:<relais>`). FAIL-OPEN.
    try:
        from api.routes import ambassadeur_routes as AMB
        await AMB.accorder_boost(_base, _doc)
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s Boost non accordé (%s)", PREFIXE, type(_err).__name__)
    return _doc


async def jeton_parent_evenement(database, offre_id, jeton=None):
    """V610 — Le parent d'un participant d'ÉVÉNEMENT : l'invitation par laquelle il
    est arrivé (si elle porte BIEN cette offre), sinon l'invitation ACTIVE du coach
    pour cette offre (génération 1). Ainsi chaque participant reçoit son lien, même
    venu sans `?inv=`. None si l'offre n'a aucune invitation active."""
    _offre = str(offre_id or "")
    if not _offre:
        return None
    _t = jeton_valide(jeton)
    if _t:
        _camp, _ = await resoudre_parent(database, _t)
        if _camp and str(_camp.get("offer_id") or "") == _offre:
            return _t
    _camp = await database["referral_campaigns"].find_one(
        {"offer_id": _offre, "status": "active", "type": {"$in": list(TYPES_RELAIS)}},
        {"_id": 0, "share_token": 1}, sort=[("created_at", -1)])
    return jeton_valide((_camp or {}).get("share_token")) or None


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
        if not _jeton and _meta.get("offer_id"):
            # V610 : événement à réservation automatique acheté SANS invitation -> son
            # lien quand même, rattaché à l'invitation active du coach (génération 1).
            _o = await database["offers"].find_one({"id": str(_meta.get("offer_id"))},
                                                   {"_id": 0, "offer_type": 1, "evenement_reservation_auto": 1})
            from api.routes.evenement_special import reservation_auto as _v610_auto
            if _v610_auto(_o):
                _jeton = await jeton_parent_evenement(database, _meta.get("offer_id"))
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
            "type": rel.get("type_invitation"), "titre": (camp or {}).get("title") or None,
            # V610o : « membre » (place offerte) / « stripe » (billet payé) / « inscription » —
            # choisit le message de partage (« ma place est offerte » = la SIENNE, jamais l'ami).
            "nature": rel.get("preuve_nature") or None}


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
        exiger_debit(request)
    _s = str(session_id or "").strip()
    if not re.match(r"^cs_[A-Za-z0-9_]{6,200}$", _s):
        raise HTTPException(status_code=404, detail="Introuvable")
    _r = await db[COLL].find_one({"preuve_cle": "stripe:" + _s}, {"_id": 0})
    if not _r:
        raise HTTPException(status_code=404, detail="Introuvable")
    _c = await db["referral_campaigns"].find_one({"id": _r.get("campagne_id")}, {"_id": 0, "title": 1})
    _sortie = dto_relais(_r, _c, _front())
    # V610i : la PLACE elle-même (réclamation `stripe:<session>` posée par le webhook avec la
    # réservation) — la page de retour n'annonce « Ta place est réservée » qu'à ce moment.
    try:
        _sortie["place_confirmee"] = bool(await db["evenement_places"].find_one({"_id": "stripe:" + _s}, {"_id": 1}))
    except Exception:  # noqa: BLE001
        _sortie["place_confirmee"] = False
    return _sortie


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
    exiger_debit(request)
    _jeton = jeton_valide(_b.get("jeton"))
    _code = str(_b.get("code") or "").strip().upper()
    if not _jeton or not re.match(r"^[A-Z0-9-]{4,40}$", _code):
        raise HTTPException(status_code=404, detail="Introuvable")
    # Pas d'oracle sur les codes d'accès : il faut la SESSION D'ESPACE de ce code
    # (en-tête `x-espace-token`, délivré après le code e-mail — même porte que l'espace).
    try:
        from api.server import _b3s13_porteur_autorise
        _charge, _ = await _b3s13_porteur_autorise(request, _code, str(_b.get("slug") or ""))
    except Exception:  # noqa: BLE001
        _charge = None
    if not _charge:
        raise HTTPException(status_code=403, detail="Ouvre ton espace pour obtenir ton lien.")
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


async def _porteur_espace(request, code, slug):
    """La charge de la session d'ESPACE (code e-mail prouvé) qui ouvre CE code, sinon None."""
    try:
        from api.server import _b3s13_porteur_autorise
        _charge, _ = await _b3s13_porteur_autorise(request, code, slug)
        return _charge
    except Exception:  # noqa: BLE001
        return None


MES_EVENEMENTS_MAX = 20


def _a_venir(occurrence, maintenant=None) -> bool:
    """L'événement (heure de Zurich, sans fuseau) n'est pas encore passé — marge de 6 h :
    le soir même, le lien reste à portée."""
    _o = str(occurrence or "")[:19]
    if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", _o):
        return False
    if maintenant is None:
        try:
            from zoneinfo import ZoneInfo
            maintenant = datetime.now(ZoneInfo("Europe/Zurich")).replace(tzinfo=None)
        except Exception:  # noqa: BLE001
            maintenant = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
    return _o >= (maintenant - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%S")[:len(_o)]


@router.post("/api/invitation/relais/mes-evenements")
async def relais_mes_evenements(request: Request):
    """V610m — ESPACE : les événements À VENIR de la personne CONNECTÉE (session d'espace,
    code e-mail prouvé) et SON lien personnel pour chacun — pour retrouver « Inviter mes
    amis » sur sa réservation. `{code, slug?}` + en-tête `x-espace-token`. 403 sans session.
    Rendu : titre, date, lieu, offre, lien personnel — aucune donnée d'un tiers.
    Un relais n'existe qu'après un paiement CONFIRMÉ (webhook), une place offerte ou une
    inscription confirmée : il vaut preuve de participation."""
    try:
        _b = await request.json()
    except Exception:  # noqa: BLE001
        _b = {}
    _b = _b if isinstance(_b, dict) else {}
    exiger_debit(request)
    _code = str(_b.get("code") or "").strip().upper()
    _charge = await _porteur_espace(request, _code, str(_b.get("slug") or "")) \
        if re.match(r"^[A-Z0-9-]{4,40}$", _code) else None
    if not _charge:
        raise HTTPException(status_code=403, detail="Ouvre ton espace pour retrouver tes événements.")
    _emp = empreinte_email(_charge.get("email"))
    if not _emp:
        return {"evenements": []}
    _rels = await db[COLL].find({"email_empreinte": _emp, "type_invitation": {"$in": list(TYPES_RELAIS)}},
                                {"_id": 0}).sort("created_at", -1).limit(MES_EVENEMENTS_MAX).to_list(MES_EVENEMENTS_MAX)
    _sortie, _vues = [], set()
    for _r in _rels:
        _cid = _r.get("campagne_id")
        if not _cid or _cid in _vues:
            continue
        _vues.add(_cid)
        _camp = await db["referral_campaigns"].find_one({"id": _cid}, {"_id": 0})
        if not _camp or _camp.get("status") != "active" or not _a_venir(_camp.get("occurrence")):
            continue
        _sortie.append({"offer_id": _camp.get("offer_id"), "titre": _camp.get("title") or "Événement Afroboost",
                        "occurrence": _camp.get("occurrence"), "lieu": _camp.get("lieu") or "",
                        "relais": dto_relais(_r, _camp, _front())})
    return {"evenements": _sortie}


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
