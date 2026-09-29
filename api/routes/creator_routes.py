# -*- coding: utf-8 -*-
"""V559 — PROGRAMME CRÉATEUR / AFFILIATION : routes et écritures.

Règles pures : `creator_engine` (C). Identité : les portes EXISTANTES du
parrainage — espace abonné (`_parrain_depuis_requete`, jeton d'espace / jeton
abonné) ou coach / super-admin signé (`_admin`, JWT). `X-User-Email` n'est
JAMAIS lu. Le rôle « créateur rémunéré » n'est décidé QUE par le super-admin.

COLLECTIONS
  creators            une fiche par personne (e-mail normalisé unique) :
                      statut pending / approved / rejected / suspended ;
  referral_programs   (existante, V558) programmes `type: "affiliation"` ;
  referral_commissions une commission par paiement (`cle_paiement` unique) ;
  payout_requests     les demandes de retrait (traitement manuel, lot 1).

ÉCRITURE D'UNE CONVERSION : UNIQUEMENT depuis le webhook de paiement (Stripe
`paid`), jamais depuis le navigateur. FAIL-OPEN : un achat encaissé n'échoue
jamais à cause de l'affiliation.
"""
import html
import logging
import os
import secrets
import uuid
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from api.routes import creator_engine as C
from api.routes import referral_routes as R

logger = logging.getLogger(__name__)
PREFIXE = "[CREATEUR]"

router = APIRouter(prefix="/api/createur", tags=["createur"])
db = None

COLL_CREATEURS = "creators"
COLL_PROGRAMMES = "referral_programs"
COLL_COMMISSIONS = "referral_commissions"
COLL_RETRAITS = "payout_requests"
DEBIT_PREFIXE_DEMANDE = "createur_d:"
DEBIT_PREFIXE_RETRAIT = "createur_r:"
DEBIT_PREFIXE_PARTAGE = "createur_p:"


def init_db(database):
    global db
    db = database


def _db():
    return db if db is not None else R.db


def _front() -> str:
    return (os.environ.get("FRONTEND_URL") or "https://afroboost.com").rstrip("/")


async def assurer_index(database) -> None:
    """Index posés AU DÉMARRAGE, avant toute donnée (leçon P2) : l'unicité de
    `cle_paiement` est ce qui rend un double webhook inoffensif."""
    try:
        await database[COLL_CREATEURS].create_index("id", unique=True)
        await database[COLL_CREATEURS].create_index("email", unique=True)
        await database[COLL_CREATEURS].create_index("share_token", unique=True,
                                                    partialFilterExpression={"share_token": {"$type": "string"}})
        await database[COLL_CREATEURS].create_index([("status", 1), ("created_at", -1)])
        await database[COLL_COMMISSIONS].create_index("id", unique=True)
        await database[COLL_COMMISSIONS].create_index("cle_paiement", unique=True)
        await database[COLL_COMMISSIONS].create_index([("creator_id", 1), ("created_at", -1)])
        await database[COLL_COMMISSIONS].create_index("payment_id")
        await database[COLL_RETRAITS].create_index("id", unique=True)
        await database[COLL_RETRAITS].create_index([("creator_id", 1), ("created_at", -1)])
        logger.info("%s index OK", PREFIXE)
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s index non posés (%s)", PREFIXE, type(_err).__name__)


def _refus(code, message):
    raise HTTPException(status_code=code, detail=message)


async def _corps(request) -> dict:
    try:
        _b = await request.json()
    except Exception:  # noqa: BLE001
        return {}
    return _b if isinstance(_b, dict) else {}


# ─── Identité ────────────────────────────────────────────────────────────────
def _entete(request, nom) -> str:
    try:
        return (request.headers.get(nom, "") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


async def _identite(request) -> dict:
    """`{email, role, nom}` — espace abonné d'abord (jeton d'espace / abonné),
    sinon coach / super-admin signé. 401/403 sinon. Jamais X-User-Email."""
    if _entete(request, "x-espace-token") or _entete(request, "x-subscriber-token"):
        _p = await R._parrain_depuis_requete(request)
        if not _p.get("email"):
            _refus(403, "Identité abonné requise.")
        return {"email": C.normaliser_email(_p["email"]), "role": "subscriber", "nom": _p.get("name") or ""}
    _auth = _entete(request, "authorization")
    if _auth.lower().startswith("bearer ") and _auth.split(" ", 1)[1].strip():
        _a = await R._admin(request)
        return {"email": C.normaliser_email(_a["email"]), "role": "super_admin" if _a["admin"] else "coach",
                "nom": ""}
    _refus(401, "Connecte-toi à ton espace pour continuer.")


async def _super_admin(request) -> str:
    """Le super-admin signé, sinon 401/403."""
    _auth = _entete(request, "authorization")
    if not (_auth.lower().startswith("bearer ") and _auth.split(" ", 1)[1].strip()):
        _refus(401, "Authentification requise — reconnecte-toi.")
    _a = await R._admin(request)
    if not _a["admin"]:
        _refus(403, "Réservé au super-admin.")
    return C.normaliser_email(_a["email"])


# ─── Lectures ────────────────────────────────────────────────────────────────
async def _createur_par_email(email):
    try:
        return await _db()[COLL_CREATEURS].find_one({"email": C.normaliser_email(email)}, {"_id": 0})
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s fiche créateur illisible (%s)", PREFIXE, type(_err).__name__)
        return None


async def _createur_par_jeton(jeton):
    if not C.jeton_valide(jeton):
        return None
    try:
        return await _db()[COLL_CREATEURS].find_one({"share_token": str(jeton)}, {"_id": 0})
    except Exception:  # noqa: BLE001
        return None


async def _programmes_affiliation(actifs=True) -> list:
    _q = {"type": "affiliation", "coach_id": ""}
    if actifs:
        _q["status"] = "active"
    try:
        return await _db()[COLL_PROGRAMMES].find(_q, {"_id": 0}).sort("created_at", 1).to_list(C.LISTE_MAX)
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s programmes illisibles (%s)", PREFIXE, type(_err).__name__)
        return []


async def _confirmer_echues(filtre) -> None:
    """Confirmation PARESSEUSE : une commission `pending` dont le délai est passé
    devient `confirmed` à la lecture (écriture conditionnelle, idempotente)."""
    _now = C.maintenant()
    try:
        await _db()[COLL_COMMISSIONS].update_many(
            dict(filtre, status="pending", confirmable_at={"$lte": C.iso(_now)}),
            {"$set": {"status": "confirmed", "confirmed_at": C.iso(_now)},
             "$push": {"history": {"at": C.iso(_now), "status": "confirmed", "motif": "delai_ecoule"}}})
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s confirmation différée (%s)", PREFIXE, type(_err).__name__)


async def _commissions_du_createur(createur) -> list:
    await _confirmer_echues({"creator_id": createur["id"]})
    try:
        return await _db()[COLL_COMMISSIONS].find({"creator_id": createur["id"]}, {"_id": 0}) \
            .sort("created_at", -1).to_list(500)
    except Exception:  # noqa: BLE001
        return []


async def _filleuls(createur, commissions) -> list:
    """LA MÊME SOURCE que la chaîne : les invités des passes dont le créateur
    est le parrain (`referral_passes`), puis les acheteurs de son lien. Lectures
    groupées ($in), bornées ; prénom / date / origine / statut seulement."""
    _email = C.normaliser_email(createur.get("email"))
    try:
        _passes = await _db()["referral_passes"].find(
            {"sponsor.email_norm": _email, "invitee.email_norm": {"$type": "string"}},
            {"_id": 0, "invitee": 1, "reservations": 1, "created_at": 1}).sort("created_at", -1).to_list(C.LISTE_MAX)
    except Exception:  # noqa: BLE001
        _passes = []
    _achats = {}
    for _c in commissions:
        if C.statut_effectif(_c) in ("pending", "confirmed", "paid"):
            _achats.setdefault(_c.get("buyer_id"), _c)
    _resa_ids = [(_p.get("reservations") or {}).get("invitee_id") for _p in _passes]
    _valides = set()
    if any(_resa_ids):
        try:
            _rows = await _db()["reservations"].find(
                {"id": {"$in": [i for i in _resa_ids if i]}, "validated": True}, {"_id": 0, "id": 1}).to_list(C.LISTE_MAX)
            _valides = {r.get("id") for r in _rows}
        except Exception:  # noqa: BLE001
            _valides = set()
    _emails = [C.normaliser_email((_p.get("invitee") or {}).get("email_norm")) for _p in _passes]
    _clients = set()
    if _emails:
        try:
            _subs = await _db()["subscriptions"].find(
                {"email": {"$in": _emails}, "source": "stripe_auto"}, {"_id": 0, "email": 1}).to_list(C.LISTE_MAX)
            _clients = {C.normaliser_email(s.get("email")) for s in _subs}
        except Exception:  # noqa: BLE001
            _clients = set()
    _sortie, _vus = [], set()
    for _p in _passes:
        _inv = _p.get("invitee") or {}
        _e = C.normaliser_email(_inv.get("email_norm"))
        if _e in _vus:
            continue
        _vus.add(_e)
        if _e in _achats and C.statut_effectif(_achats[_e]) in ("confirmed", "paid"):
            _statut = "Achat confirmé"
        elif _e in _clients or _e in _achats:
            _statut = "Client"
        elif (_p.get("reservations") or {}).get("invitee_id") in _valides:
            _statut = "Premier essai"
        else:
            _statut = "Inscrit"
        _sortie.append(C.dto_filleul(_inv.get("name"), _inv.get("consent_reservation_at") or _p.get("created_at"),
                                     "Invitation", _statut))
    for _e, _c in _achats.items():
        if _e in _vus:
            continue
        _vus.add(_e)
        _statut = "Achat confirmé" if C.statut_effectif(_c) in ("confirmed", "paid") else "Client"
        _sortie.append(C.dto_filleul(_c.get("buyer_prenom"), _c.get("created_at"), "Lien créateur", _statut))
    return _sortie[:C.LISTE_MAX]


async def _dashboard(createur) -> dict:
    _comms = await _commissions_du_createur(createur)
    _liste_filleuls = await _filleuls(createur, _comms)
    _k = C.kpis(_comms, len(_liste_filleuls))
    _progs = await _programmes_affiliation()
    try:
        _retraits = await _db()[COLL_RETRAITS].find({"creator_id": createur["id"]}, {"_id": 0}) \
            .sort("created_at", -1).to_list(20)
    except Exception:  # noqa: BLE001
        _retraits = []
    _en_cours = any(r.get("status") in ("pending", "approved") for r in _retraits)
    _jeton = createur.get("share_token") or ""
    return {
        "kpis": _k,
        "lien": C.lien_createur(_front(), _jeton) if _jeton else "",
        "lien_partage": C.lien_partage(_front(), _jeton) if _jeton else "",
        "carte_url": ("%s/carte.jpg" % C.lien_partage(_front(), _jeton)) if _jeton else "",
        "commissions": [C.libelle_programme(p) for p in _progs],
        "retrait_min": C.RETRAIT_MIN_CHF,
        "retrait_possible": _k["solde"] >= C.RETRAIT_MIN_CHF and not _en_cours,
        "retrait_en_cours": _en_cours,
        "methode": createur.get("payout_method"),
        "methode_detail": C.masquer_detail(createur.get("payout_method"), createur.get("payout_detail")),
        "retraits": [C.dto_retrait(r) for r in _retraits],
        "filleuls": _liste_filleuls,
        "conversions": [C.dto_conversion(c) for c in _comms[:C.LISTE_MAX]],
    }


def _dto_demande(createur) -> dict:
    _c = createur or {}
    return {"prenom": _c.get("prenom"), "nom": _c.get("nom"), "statut": _c.get("status"),
            "cree_le": _c.get("created_at"), "decide_le": _c.get("decided_at"),
            "methode": _c.get("payout_method"),
            "methode_detail": C.masquer_detail(_c.get("payout_method"), _c.get("payout_detail"))}


# ═══════════════════════════════════════════════════════════════════════════
# Créateur : état, demande, tableau de bord, retrait
# ═══════════════════════════════════════════════════════════════════════════
@router.get("/me")
async def createur_moi(request: Request):
    """`{statut, programme_ouvert, demande?, dashboard?}` pour la personne
    identifiée (abonné ou coach). Aucune donnée d'un tiers."""
    _id = await _identite(request)
    _c = await _createur_par_email(_id["email"])
    _progs = await _programmes_affiliation()
    _rep = {"statut": (_c or {}).get("status") or "none", "role": _id["role"],
            "programme_ouvert": bool(_progs),
            "commissions": [C.libelle_programme(p) for p in _progs],
            "delai_confirmation_jours": C.DELAI_CONFIRMATION_JOURS,
            "retrait_min": C.RETRAIT_MIN_CHF}
    if _c:
        _rep["demande"] = _dto_demande(_c)
    if _c and _c.get("status") == "approved":
        _rep["dashboard"] = await _dashboard(_c)
    return _rep


@router.post("/demande")
async def createur_demande(request: Request):
    """« Devenir créateur » : une demande `pending` (jamais une approbation). Une
    demande refusée peut être renvoyée ; approuvée / suspendue / en attente : 409."""
    _id = await _identite(request)
    if _id["role"] == "super_admin":
        _refus(409, "Le super-admin ne peut pas être créateur rémunéré.")
    R._exiger_debit(request, DEBIT_PREFIXE_DEMANDE)
    try:
        _champs = C.valider_demande(await _corps(request))
    except C.DemandeInvalide as _err:
        _refus(422, str(_err))
    if not _champs["reglement_accepte"]:
        _refus(422, "Merci d'accepter le règlement du programme Créateur.")
    _existante = await _createur_par_email(_id["email"])
    _now = C.iso()
    if _existante and _existante.get("status") in ("pending", "approved", "suspended"):
        _refus(409, {"pending": "Ta demande est déjà en cours d'examen.",
                     "approved": "Tu es déjà créateur Afroboost.",
                     "suspended": "Ton compte créateur est suspendu : contacte Afroboost."}[_existante["status"]])
    if _existante:
        await _db()[COLL_CREATEURS].update_one(
            {"id": _existante["id"], "status": "rejected"},
            {"$set": dict(_champs, status="pending", updated_at=_now, decided_at=None),
             "$push": {"history": {"at": _now, "status": "pending", "par": "createur"}}})
    else:
        _doc = dict(_champs, id=str(uuid.uuid4()), email=_id["email"], role_origine=_id["role"],
                    status="pending", share_token=None, created_at=_now, updated_at=_now,
                    history=[{"at": _now, "status": "pending", "par": "createur"}])
        try:
            await _db()[COLL_CREATEURS].insert_one(dict(_doc))
        except Exception as _err:  # noqa: BLE001
            if R._est_doublon(_err):
                _refus(409, "Ta demande est déjà en cours d'examen.")
            raise
    logger.info("%s demande créateur (%s)", PREFIXE, _id["role"])
    return await createur_moi(request)


@router.post("/retrait")
async def createur_retrait(request: Request):
    """Demande de retrait du SOLDE (commissions confirmées, non encore demandées).
    Une seule demande ouverte à la fois ; minimum `RETRAIT_MIN_CHF`. Le paiement
    est fait À LA MAIN par le super-admin (lot 1)."""
    _id = await _identite(request)
    R._exiger_debit(request, DEBIT_PREFIXE_RETRAIT)
    _c = await _createur_par_email(_id["email"])
    if not _c or _c.get("status") != "approved":
        _refus(403, "Réservé aux créateurs approuvés.")
    if await _db()[COLL_RETRAITS].find_one({"creator_id": _c["id"], "status": {"$in": ["pending", "approved"]}},
                                            {"_id": 0, "id": 1}):
        _refus(409, "Une demande de retrait est déjà en cours.")
    await _confirmer_echues({"creator_id": _c["id"]})
    _dispo = await _db()[COLL_COMMISSIONS].find(
        {"creator_id": _c["id"], "status": "confirmed", "payout_request_id": {"$exists": False}},
        {"_id": 0, "id": 1, "commission_amount": 1}).to_list(500)
    _montant = C.arrondi(sum(C.arrondi(x.get("commission_amount")) for x in _dispo))
    if _montant < C.RETRAIT_MIN_CHF:
        _refus(409, "Le montant minimum de retrait est de %.0f CHF." % C.RETRAIT_MIN_CHF)
    _rid = str(uuid.uuid4())
    _ids = [x["id"] for x in _dispo]
    # Réserver les commissions AVANT d'écrire la demande : une commission ne peut
    # appartenir qu'à UNE demande (filtre « pas encore réservée »).
    await _db()[COLL_COMMISSIONS].update_many(
        {"id": {"$in": _ids}, "status": "confirmed", "payout_request_id": {"$exists": False}},
        {"$set": {"payout_request_id": _rid}})
    _reservees = await _db()[COLL_COMMISSIONS].find({"payout_request_id": _rid},
                                                   {"_id": 0, "id": 1, "commission_amount": 1}).to_list(500)
    _montant = C.arrondi(sum(C.arrondi(x.get("commission_amount")) for x in _reservees))
    _now = C.iso()
    await _db()[COLL_RETRAITS].insert_one({
        "id": _rid, "creator_id": _c["id"], "amount": _montant, "currency": "CHF", "status": "pending",
        "payment_method": _c.get("payout_method"), "commission_ids": [x["id"] for x in _reservees],
        "created_at": _now, "processed_at": None, "history": [{"at": _now, "status": "pending"}]})
    logger.info("%s retrait demandé %.2f CHF", PREFIXE, _montant)
    return await createur_moi(request)


# ═══════════════════════════════════════════════════════════════════════════
# Partage : la page d'aperçu (OG + carte) qui renvoie vers le lien créateur
# ═══════════════════════════════════════════════════════════════════════════
@router.get("/partage/{jeton}")
async def createur_partage(jeton: str, request: Request):
    R._exiger_debit(request, DEBIT_PREFIXE_PARTAGE)
    _c = await _createur_par_jeton(jeton)
    if not _c or _c.get("status") != "approved":
        raise HTTPException(status_code=404, detail="Lien introuvable")
    _p = html.escape(C.prenom(_c.get("prenom")) or "Afroboost", quote=True)
    _cible = html.escape(C.lien_createur(_front(), jeton), quote=True)
    _carte = html.escape("%s/carte.jpg" % C.lien_partage(_front(), jeton), quote=True)
    _titre = "%s t'invite à découvrir Afroboost" % _p
    _page = (
        "<!doctype html><html lang=\"fr\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<meta name=\"robots\" content=\"noindex\">"
        "<title>%(t)s</title>"
        "<meta property=\"og:title\" content=\"%(t)s\">"
        "<meta property=\"og:description\" content=\"Cardio · danse afrobeat · casques audio\">"
        "<meta property=\"og:image\" content=\"%(i)s\"><meta property=\"og:image:width\" content=\"1200\">"
        "<meta property=\"og:image:height\" content=\"630\"><meta property=\"og:url\" content=\"%(u)s\">"
        "<meta name=\"twitter:card\" content=\"summary_large_image\">"
        "<meta http-equiv=\"refresh\" content=\"0;url=%(u)s\"></head>"
        "<body><a href=\"%(u)s\">Découvrir Afroboost</a></body></html>") % {"t": _titre, "i": _carte, "u": _cible}
    return HTMLResponse(_page, headers={"Cache-Control": "public, max-age=300"})


@router.get("/partage/{jeton}/carte.jpg")
async def createur_carte(jeton: str, request: Request):
    R._exiger_debit(request, DEBIT_PREFIXE_PARTAGE)
    _c = await _createur_par_jeton(jeton)
    if not _c or _c.get("status") != "approved":
        raise HTTPException(status_code=404, detail="Carte introuvable")
    from api.routes import referral_carte as RC
    _couleur = None
    try:
        _concept = await _db()["concept"].find_one({"id": "concept"}, {"_id": 0, "primaryColor": 1}) or {}
        _couleur = _concept.get("primaryColor")
    except Exception:  # noqa: BLE001
        _couleur = None
    _octets = RC.rendre_carte({"nom": C.prenom(_c.get("prenom")) or "Afroboost", "cours": "", "offre": "",
                               "occurrence": None, "lieu": "", "couleur": _couleur, "photo": None,
                               "type": "Créateur"})
    return Response(content=_octets, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})


# ═══════════════════════════════════════════════════════════════════════════
# CONVERSIONS — appelées par les webhooks de paiement, jamais par le navigateur
# ═══════════════════════════════════════════════════════════════════════════
async def _createur_de_l_invitation(email_acheteur):
    """Le parrain DIRECT de la dernière invitation rejointe par l'acheteur (fenêtre
    `FENETRE_INVITATION_JOURS`), s'il est créateur. Jamais le parrain du parrain."""
    _e = C.normaliser_email(email_acheteur)
    if not _e:
        return None, None
    _depuis = C.iso(C.maintenant() - timedelta(days=C.FENETRE_INVITATION_JOURS))
    try:
        _p = await _db()["referral_passes"].find(
            {"invitee.email_norm": _e, "created_at": {"$gte": _depuis}},
            {"_id": 0, "id": 1, "sponsor": 1, "origin": 1}).sort("created_at", -1).to_list(1)
    except Exception:  # noqa: BLE001
        _p = []
    if not _p:
        return None, None
    _sp = (_p[0].get("sponsor") or {})
    if _sp.get("pending") is True:
        return None, None
    return await _createur_par_email(_sp.get("email_norm")), _p[0]


async def enregistrer_conversion(database, *, email, nom, offer_id, montant, devise, order_id, payment_id,
                                 source, jeton_createur=None):
    """Enregistre AU PLUS UNE commission pour ce paiement. Rend la commission
    (existante ou créée), ou None si rien n'est dû. Ne lève jamais."""
    global db
    if database is not None and db is None:
        db = database
    try:
        if C.arrondi(montant) <= 0 or not order_id or not email:
            return None
        _cle = C.cle_paiement(source, order_id)
        _deja = await _db()[COLL_COMMISSIONS].find_one({"cle_paiement": _cle}, {"_id": 0})
        if _deja:
            return _deja
        _lien = await _createur_par_jeton(jeton_createur) if jeton_createur else None
        _inv, _pass = await _createur_de_l_invitation(email)
        _createur = C.choisir_createur(_lien, _inv, email)
        if not _createur:
            return None
        _origine = "lien" if (_lien and _createur.get("id") == _lien.get("id")) else "invitation"
        _progs = await _programmes_affiliation()
        _montant_c, _prog = C.commission_pour(_progs, offer_id, montant)
        if not _prog:
            return None
        _offre_nom = _prog.get("offer_name") or ""
        if not _offre_nom:
            try:
                _o = await _db()["offers"].find_one({"id": str(offer_id or "")}, {"_id": 0, "name": 1}) or {}
                _offre_nom = _o.get("name") or ""
            except Exception:  # noqa: BLE001
                _offre_nom = ""
        _doc = C.nouvelle_commission(
            createur=_createur, programme=_prog, commission=_montant_c, cle=_cle, email_acheteur=email,
            nom_acheteur=nom, offer_id=offer_id, offer_name=_offre_nom, montant=montant, devise=devise,
            order_id=order_id, payment_id=payment_id, origine=_origine,
            referral_id=(_pass or {}).get("id") if _origine == "invitation" else None,
            campaign_id=((_pass or {}).get("origin") or {}).get("campaign_id") if _origine == "invitation" else None)
        try:
            await _db()[COLL_COMMISSIONS].insert_one(dict(_doc))
        except Exception as _err:  # noqa: BLE001
            if R._est_doublon(_err):              # webhook rejoué en même temps : une seule
                return await _db()[COLL_COMMISSIONS].find_one({"cle_paiement": _cle}, {"_id": 0})
            raise
        logger.info("%s commission %.2f %s (%s, %s)", PREFIXE, _doc["commission_amount"], _doc["currency"],
                    _origine, _cle[:24])
        return _doc
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s conversion non enregistrée (%s)", PREFIXE, type(_err).__name__)
        return None


def _lire(obj, cle, defaut=None):
    try:
        _v = obj.get(cle)
    except Exception:  # noqa: BLE001
        _v = getattr(obj, cle, None)
    return defaut if _v is None else _v


async def creator_conversion_stripe(database, session, metadata=None):
    """`checkout.session.completed` PAYÉ → conversion (clé = id de la session)."""
    _meta = metadata if isinstance(metadata, dict) else dict(_lire(session, "metadata", {}) or {})
    if str(_lire(session, "payment_status", "") or "") != "paid":
        return None
    _details = _lire(session, "customer_details", {}) or {}
    try:
        _email = _details.get("email")
    except Exception:  # noqa: BLE001
        _email = None
    _email = _email or _lire(session, "customer_email") or _meta.get("customer_email") or ""
    _offre = _meta.get("offer_id") or ""
    if not _offre:
        try:
            import json as _json
            _items = _json.loads(_meta.get("items") or "[]")
            _offre = str((_items[0] or {}).get("id") or "") if _items else ""
        except Exception:  # noqa: BLE001
            _offre = ""
    return await enregistrer_conversion(
        database, email=_email, nom=_meta.get("customer_name") or "", offer_id=_offre,
        montant=(float(_lire(session, "amount_total", 0) or 0) / 100.0), devise=_lire(session, "currency", "chf"),
        order_id=_lire(session, "id"), payment_id=_lire(session, "payment_intent"), source="stripe",
        jeton_createur=_meta.get("creator_token"))


async def creator_remboursement(database, payment_id, complet=True, motif="stripe_refund"):
    """Achat remboursé : commission pending / confirmed → `refunded`. Déjà PAYÉE :
    elle reste `paid` (l'argent est parti) et reçoit une RÉGULARISATION tracée.
    Rien n'est supprimé. Rend le nombre de commissions touchées."""
    global db
    if database is not None and db is None:
        db = database
    _pid = str(payment_id or "").strip()
    if not _pid:
        return 0
    _now = C.iso()
    _n = 0
    try:
        _rows = await _db()[COLL_COMMISSIONS].find({"payment_id": _pid}, {"_id": 0}).to_list(5)
        for _c in _rows:
            if not complet:
                await _db()[COLL_COMMISSIONS].update_one(
                    {"id": _c["id"]}, {"$set": {"remboursement_partiel": True},
                                       "$push": {"history": {"at": _now, "status": _c.get("status"),
                                                             "motif": "remboursement_partiel_a_verifier"}}})
                _n += 1
                continue
            if _c.get("status") in ("pending", "confirmed"):
                _r = await _db()[COLL_COMMISSIONS].update_one(
                    {"id": _c["id"], "status": {"$in": ["pending", "confirmed"]}},
                    {"$set": {"status": "refunded", "refunded_at": _now},
                     "$unset": {"payout_request_id": ""},
                     "$push": {"history": {"at": _now, "status": "refunded", "motif": motif}}})
                _touchee = int(getattr(_r, "modified_count", 1) or 0)
                _n += _touchee
                # Réservée dans une demande de retrait encore ouverte : le montant
                # demandé baisse d'autant (jamais de retrait d'un argent remboursé).
                if _touchee and _c.get("payout_request_id"):
                    await _db()[COLL_RETRAITS].update_one(
                        {"id": _c["payout_request_id"], "status": {"$in": ["pending", "approved"]}},
                        {"$inc": {"amount": -C.arrondi(_c.get("commission_amount"))},
                         "$pull": {"commission_ids": _c["id"]},
                         "$push": {"history": {"at": _now, "status": "ajuste", "motif": "remboursement"}}})
            elif _c.get("status") == "paid" and not _c.get("regularisation"):
                await _db()[COLL_COMMISSIONS].update_one(
                    {"id": _c["id"], "regularisation": {"$exists": False}},
                    {"$set": {"regularisation": {"at": _now, "montant": -C.arrondi(_c.get("commission_amount")),
                                                 "motif": motif}},
                     "$push": {"history": {"at": _now, "status": "paid", "motif": "regularisation:" + motif}}})
                _n += 1
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s remboursement non répercuté (%s)", PREFIXE, type(_err).__name__)
    return _n


# ═══════════════════════════════════════════════════════════════════════════
# SUPER-ADMIN : demandes, créateurs, programmes, conversions, retraits
# ═══════════════════════════════════════════════════════════════════════════
def _dto_admin_createur(c) -> dict:
    _c = c or {}
    return {"id": _c.get("id"), "prenom": _c.get("prenom"), "nom": _c.get("nom"), "email": _c.get("email"),
            "telephone": _c.get("telephone"), "reseaux": _c.get("reseaux"), "motivation": _c.get("motivation"),
            "role_origine": _c.get("role_origine"), "statut": _c.get("status"),
            "methode": _c.get("payout_method"),
            "methode_detail": C.masquer_detail(_c.get("payout_method"), _c.get("payout_detail")),
            "cree_le": _c.get("created_at"), "decide_le": _c.get("decided_at"),
            "lien": C.lien_createur(_front(), _c["share_token"]) if _c.get("share_token") else ""}


def _statut_param(request, permis):
    _s = str((getattr(request, "query_params", None) or {}).get("statut") or "").strip()
    return _s if _s in permis else ""


@router.get("/admin/createurs")
async def admin_createurs(request: Request):
    await _super_admin(request)
    _q = {}
    _s = _statut_param(request, C.STATUTS_CREATEUR)
    if _s:
        _q["status"] = _s
    _rows = await _db()[COLL_CREATEURS].find(_q, {"_id": 0}).sort("created_at", -1).to_list(C.LISTE_MAX)
    return {"createurs": [_dto_admin_createur(c) for c in _rows]}


@router.post("/admin/createurs/{createur_id}/decision")
async def admin_decision(createur_id: str, request: Request):
    _admin_email = await _super_admin(request)
    _b = await _corps(request)
    _c = await _db()[COLL_CREATEURS].find_one({"id": str(createur_id or "")[:64]}, {"_id": 0})
    if not _c:
        _refus(404, "Créateur introuvable")
    _decision = str(_b.get("decision") or "")
    _cible = C.decision_autorisee(_c.get("status"), _decision)
    if not _cible:
        _refus(409, "Cette décision n'est pas possible depuis le statut « %s »." % _c.get("status"))
    _now = C.iso()
    _set = {"status": _cible, "decided_at": _now, "decided_by": _admin_email, "updated_at": _now}
    if _cible == "approved" and not _c.get("share_token"):
        _set["share_token"] = secrets.token_urlsafe(12)
    _r = await _db()[COLL_CREATEURS].update_one(
        {"id": _c["id"], "status": _c.get("status")},
        {"$set": _set, "$push": {"history": {"at": _now, "status": _cible, "par": "super_admin"}}})
    if not getattr(_r, "modified_count", 1):
        _refus(409, "Le statut a changé entre-temps : recharge la page.")
    logger.info("%s décision %s -> %s", PREFIXE, _decision, _cible)
    return _dto_admin_createur(await _db()[COLL_CREATEURS].find_one({"id": _c["id"]}, {"_id": 0}))


@router.get("/admin/programmes")
async def admin_programmes(request: Request):
    await _super_admin(request)
    return {"programmes": await _programmes_affiliation(actifs=False)}


async def _programme_depuis_corps(corps) -> dict:
    try:
        _p = C.valider_programme(corps)
    except C.DemandeInvalide as _err:
        _refus(422, str(_err))
    _o = await _db()["offers"].find_one({"id": _p["offer_id"]}, {"_id": 0, "id": 1, "name": 1, "price": 1})
    if not _o:
        _refus(422, "Offre introuvable.")
    _p["offer_name"] = str(_o.get("name") or "")[:120]
    return _p


@router.post("/admin/programmes")
async def admin_programme_creer(request: Request):
    _admin_email = await _super_admin(request)
    _p = await _programme_depuis_corps(await _corps(request))
    _now = C.iso()
    _doc = dict(_p, id=str(uuid.uuid4()), type="affiliation", coach_id="", created_at=_now, updated_at=_now,
                created_by=_admin_email)
    await _db()[COLL_PROGRAMMES].insert_one(dict(_doc))
    _doc.pop("_id", None)
    return _doc


@router.put("/admin/programmes/{programme_id}")
async def admin_programme_modifier(programme_id: str, request: Request):
    await _super_admin(request)
    _p = await _programme_depuis_corps(await _corps(request))
    _r = await _db()[COLL_PROGRAMMES].update_one(
        {"id": str(programme_id or "")[:64], "type": "affiliation"}, {"$set": dict(_p, updated_at=C.iso())})
    if not getattr(_r, "matched_count", 1):
        _refus(404, "Programme introuvable")
    return await _db()[COLL_PROGRAMMES].find_one({"id": str(programme_id)}, {"_id": 0})


@router.get("/admin/commissions")
async def admin_commissions(request: Request):
    await _super_admin(request)
    await _confirmer_echues({})
    _q = {}
    _s = _statut_param(request, C.STATUTS_COMMISSION)
    if _s:
        _q["status"] = _s
    _rows = await _db()[COLL_COMMISSIONS].find(_q, {"_id": 0, "history": 0}).sort("created_at", -1) \
        .to_list(C.LISTE_MAX)
    _ids = list({r.get("creator_id") for r in _rows if r.get("creator_id")})
    _noms = {}
    if _ids:
        for _c in await _db()[COLL_CREATEURS].find({"id": {"$in": _ids}}, {"_id": 0, "id": 1, "prenom": 1, "nom": 1}) \
                .to_list(C.LISTE_MAX):
            _noms[_c["id"]] = ("%s %s" % (_c.get("prenom") or "", _c.get("nom") or "")).strip()
    return {"commissions": [dict(C.dto_conversion(r), createur=_noms.get(r.get("creator_id"), ""),
                                 origine=r.get("origine"), acheteur=r.get("buyer_prenom"),
                                 regularisation=r.get("regularisation"),
                                 remboursement_partiel=r.get("remboursement_partiel") is True) for r in _rows]}


@router.post("/admin/commissions/{commission_id}/annuler")
async def admin_commission_annuler(commission_id: str, request: Request):
    """Remboursement / annulation MANUELS (quand Stripe n'a pas prévenu)."""
    await _super_admin(request)
    _b = await _corps(request)
    _motif = "refunded" if _b.get("motif") == "refunded" else "cancelled"
    _c = await _db()[COLL_COMMISSIONS].find_one({"id": str(commission_id or "")[:64]}, {"_id": 0})
    if not _c:
        _refus(404, "Commission introuvable")
    if _c.get("payment_id") and _motif == "refunded":
        await creator_remboursement(None, _c["payment_id"], True, "admin_refund")
    else:
        _now = C.iso()
        if _c.get("status") == "paid":
            await _db()[COLL_COMMISSIONS].update_one(
                {"id": _c["id"], "regularisation": {"$exists": False}},
                {"$set": {"regularisation": {"at": _now, "montant": -C.arrondi(_c.get("commission_amount")),
                                             "motif": "admin_" + _motif}},
                 "$push": {"history": {"at": _now, "status": "paid", "motif": "regularisation:admin_" + _motif}}})
        else:
            await _db()[COLL_COMMISSIONS].update_one(
                {"id": _c["id"], "status": {"$in": ["pending", "confirmed"]}},
                {"$set": {"status": _motif}, "$unset": {"payout_request_id": ""},
                 "$push": {"history": {"at": _now, "status": _motif, "motif": "admin"}}})
    return C.dto_conversion(await _db()[COLL_COMMISSIONS].find_one({"id": _c["id"]}, {"_id": 0}))


@router.get("/admin/retraits")
async def admin_retraits(request: Request):
    await _super_admin(request)
    _q = {}
    _s = _statut_param(request, C.STATUTS_RETRAIT)
    if _s:
        _q["status"] = _s
    _rows = await _db()[COLL_RETRAITS].find(_q, {"_id": 0}).sort("created_at", -1).to_list(C.LISTE_MAX)
    _ids = list({r.get("creator_id") for r in _rows})
    _crs = {}
    if _ids:
        for _c in await _db()[COLL_CREATEURS].find({"id": {"$in": _ids}}, {"_id": 0}).to_list(C.LISTE_MAX):
            _crs[_c["id"]] = _c
    _sortie = []
    for _r in _rows:
        _c = _crs.get(_r.get("creator_id")) or {}
        # Le super-admin paie À LA MAIN : il voit le moyen de paiement complet.
        _sortie.append(dict(C.dto_retrait(_r), createur=("%s %s" % (_c.get("prenom") or "", _c.get("nom") or "")).strip(),
                            email=_c.get("email"), payout_detail=_c.get("payout_detail")))
    return {"retraits": _sortie}


@router.post("/admin/retraits/{retrait_id}/decision")
async def admin_retrait_decision(retrait_id: str, request: Request):
    _admin_email = await _super_admin(request)
    _b = await _corps(request)
    _decision = str(_b.get("decision") or "")
    _cible = C.DECISIONS_RETRAIT.get(_decision)
    _r = await _db()[COLL_RETRAITS].find_one({"id": str(retrait_id or "")[:64]}, {"_id": 0})
    if not _r:
        _refus(404, "Demande introuvable")
    _permis = {"approve": ("pending",), "pay": ("pending", "approved"), "reject": ("pending", "approved")}
    if not _cible or _r.get("status") not in _permis.get(_decision, ()):
        _refus(409, "Cette décision n'est pas possible depuis « %s »." % _r.get("status"))
    _now = C.iso()
    _maj = await _db()[COLL_RETRAITS].update_one(
        {"id": _r["id"], "status": _r["status"]},
        {"$set": {"status": _cible, "processed_at": _now, "processed_by": _admin_email},
         "$push": {"history": {"at": _now, "status": _cible}}})
    if not getattr(_maj, "modified_count", 1):
        _refus(409, "La demande a changé entre-temps : recharge la page.")
    if _cible == "paid":
        await _db()[COLL_COMMISSIONS].update_many(
            {"payout_request_id": _r["id"], "status": "confirmed"},
            {"$set": {"status": "paid", "paid_at": _now},
             "$push": {"history": {"at": _now, "status": "paid", "motif": "retrait:" + _r["id"][:8]}}})
    elif _cible == "rejected":
        await _db()[COLL_COMMISSIONS].update_many({"payout_request_id": _r["id"]},
                                                  {"$unset": {"payout_request_id": ""}})
    return C.dto_retrait(await _db()[COLL_RETRAITS].find_one({"id": _r["id"]}, {"_id": 0}))
