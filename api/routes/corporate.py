# -*- coding: utf-8 -*-
# V657 : AFROBOOST CORPORATE — contrats entreprise, invitation privée, places par édition.
"""V657 — Afroboost Corporate (pilote Neuchâtel, grille « pilote-2026-11»).

CE QUE CE MODULE FAIT
- `corporate_contracts` : un contrat par entreprise (prospect existant), places par édition
  (5/10/20), durée (3/6/12 mois), prix mensuel FIGÉ à la création, statut
  devis -> signe -> (resilie | termine).
- UNE édition par mois : « à planifier » tant qu'elle n'est pas liée à un VRAI événement
  daté (offre `event` à réservation automatique existante). La lier RETIENT les places
  (retenue `corporate` sous verrou, voir `evenement_special`) et crée un code 100 % caché,
  limité à CET événement, `maxUses` = places, expirant le jour de l'événement.
- Un lien privé par entreprise (jeton `secrets.token_urlsafe(24)`), révocable /
  régénérable. Inscription publique à 0 CHF par la machinerie V628 (code + réclamation
  unique par e-mail et par événement + billet `reservationCode` pour le QR d'entrée).
- FACTURATION : aucune facture ici. Le seul système est le générateur existant
  (`POST /api/invoices/generate`, collection `invoices`). Le contrat ne garde que des
  RÉFÉRENCES (numéros) et l'échéancier ; les montants facturés / payés / dus sont
  CALCULÉS depuis les factures liées.

CE QU'IL NE FAIT PAS : aucun envoi (e-mail, WhatsApp), aucun paiement Stripe, aucune
suspension automatique pour impayé, aucune modification des abonnements ni des offres.
"""
import html
import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request

from api.routes import evenement_special as E
from api.routes.shared import (SUPER_ADMIN_EMAIL, b_valider_encaissement, coach_jwt_email,
                               is_super_admin, normaliser_email)

logger = logging.getLogger(__name__)
PREFIXE = "[V657-CORP]"
router = APIRouter(tags=["corporate"])
db = None

COLL = "corporate_contracts"
COLL_FACTURES = "invoices"
COLL_COMPTEURS = "invoice_counters"
COLL_REGLAGES = "invoice_settings"
ID_REGLAGES = "facturation_corporate"

GRILLE_VERSION = "pilote-2026-11"
# CHF par mois, par nombre de places par édition et par durée (mois). Décision du propriétaire.
GRILLE = {
    5: {3: 350, 6: 325, 12: 300},
    10: {3: 650, 6: 600, 12: 550},
    20: {3: 1200, 6: 1100, 12: 1000},
}
STATUTS = ("devis", "signe", "resilie", "termine")
DELAI_MODIF_DEFAUT_H = 48
DELAI_PAIEMENT_DEFAUT_J = 30
VALIDITE_DEVIS_DEFAUT_J = 30
RE_MOIS = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
RE_JOUR = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
RE_JETON = re.compile(r"^[A-Za-z0-9_-]{24,64}$")
LISTE_MAX = 50
MSG_INTROUVABLE = "Invitation introuvable ou désactivée."
MSG_DOUBLON = "Cette adresse e-mail est déjà inscrite à cette édition."
MSG_PLEIN = "Toutes les places de votre entreprise pour cette édition sont prises."
MSG_CLOS = "Les inscriptions et changements pour cette édition sont clos."
MSG_NON_PLANIFIEE = "Cette édition n'est pas encore planifiée."
MSG_COORDONNEES = ("Coordonnées de facturation Afroboost non vérifiées : enregistre-les puis coche "
                   "« vérifiées » (Paiements → Générateur de factures) avant d'émettre un devis ou une facture Entreprise.")


def init_db(database):
    global db
    db = database


async def assurer_index(database) -> None:
    """Index posés au démarrage (collections NEUVES : aucune donnée existante concernée)."""
    try:
        await database[COLL].create_index("id", unique=True)
        await database[COLL].create_index("token", unique=True,
                                          partialFilterExpression={"token": {"$type": "string"}})
        await database[COLL].create_index("entreprise.prospect_id")
        # Une seule facture ACTIVE par contrat et par mois : `cle_unicite` n'existe que sur
        # les factures Entreprise non annulées (aucune facture existante ne la porte).
        await database[COLL_FACTURES].create_index("cle_unicite", unique=True,
                                                   partialFilterExpression={"cle_unicite": {"$type": "string"}})
        await database[COLL_FACTURES].create_index("corporate_contract_id")
        await database[COLL_FACTURES].create_index("invoice_number")
        await database[E.COLL_RETENUES].create_index([("offer_id", 1), ("type", 1), ("statut", 1)])
        await database[E.COLL_PLACES].create_index([("offer_id", 1), ("corporate_contract_id", 1)])
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s index non posés (%s)", PREFIXE, type(_err).__name__)


# ═══════════════════════════ RÈGLES PURES ═══════════════════════════
def prix(places, duree):
    """{"prix_mensuel", "total", "grille_version"} ou None si la combinaison n'existe pas."""
    try:
        _p, _d = int(places), int(duree)
    except (TypeError, ValueError):
        return None
    _m = GRILLE.get(_p, {}).get(_d)
    if _m is None:
        return None
    return {"places": _p, "duree_mois": _d, "prix_mensuel": float(_m), "total": float(_m * _d),
            "grille_version": GRILLE_VERSION}


def mois_suivants(debut, n):
    _m = RE_MOIS.match(str(debut or ""))
    if not _m:
        return []
    _a, _mm = int(_m.group(1)), int(_m.group(2))
    _sortie = []
    for _i in range(int(n)):
        _k = _mm - 1 + _i
        _sortie.append("%04d-%02d" % (_a + _k // 12, _k % 12 + 1))
    return _sortie


def conditions_texte(c) -> str:
    """Les conditions FIGÉES dans le devis / contrat (texte unique, réutilisé partout)."""
    return "\n".join([
        "%d places par édition, %d éditions (une Afroboost Corporate par mois), soit jusqu'à %d participations."
        % (c["places"], c["duree_mois"], c["places"] * c["duree_mois"]),
        "Prix mensuel %.2f CHF, total %.2f CHF (grille %s) : prix et durée figés à la signature."
        % (c["prix_mensuel"], c["total"], c.get("grille_version") or GRILLE_VERSION),
        "Facturation mensuelle, paiement par virement bancaire à %d jours." % int(c.get("delai_paiement_jours") or DELAI_PAIEMENT_DEFAUT_J),
        "Places non utilisées sur une édition : perdues, sans report ni remboursement.",
        "Changement de participant possible jusqu'à %d h avant l'édition." % int(c.get("delai_modif_heures") or DELAI_MODIF_DEFAUT_H),
        "Éditions non encore programmées : « à planifier » ; date et lieu confirmés dès qu'ils sont fixés.",
    ])


def lignes_devis(c) -> list:
    """Prestations incluses + options (sans prix) — reprises telles quelles dans le PDF du devis."""
    return [
        "Prestation incluse : un événement Afroboost Corporate par mois (environ 60 à 90 minutes, format Classic).",
        "Options sur devis uniquement (sans prix ici) : Silent, Live Music, Silent Live Fusion.",
    ]


def _maintenant():
    return datetime.now(timezone.utc)


def _iso():
    return _maintenant().isoformat()


# ═══════════════════════════ ACCÈS ═══════════════════════════
def _ip(request) -> str:
    try:
        return (request.headers.get("CF-Connecting-IP")
                or (request.headers.get("X-Forwarded-For", "") or "").split(",")[0].strip()
                or (request.client.host if request.client else "")).strip()
    except Exception:  # noqa: BLE001
        return ""


async def exiger_super_admin(request) -> str:
    """Jeton SIGNÉ du super-admin unique, sinon 403 (jamais X-User-Email)."""
    _e = (coach_jwt_email(request) or "").strip().lower()
    if not _e or not is_super_admin(_e):
        raise HTTPException(status_code=403, detail="Accès réservé au super-admin")
    return _e


async def _corps(request) -> dict:
    try:
        _b = await request.json()
    except Exception:  # noqa: BLE001
        _b = {}
    return _b if isinstance(_b, dict) else {}


async def _contrat(contrat_id):
    _c = await db[COLL].find_one({"id": str(contrat_id or "")[:64]}, {"_id": 0})
    if not _c:
        raise HTTPException(status_code=404, detail="Contrat introuvable")
    return _c


def _journal(par, action, **k):
    return {"$push": {"journal": {"$each": [dict({"le": _iso(), "par": par, "action": action}, **k)], "$slice": -200}}}


# ═══════════════════════════ FINANCES (calculées, jamais stockées deux fois) ═══════════════════════════
async def factures_du_contrat(contrat_id) -> list:
    return await db[COLL_FACTURES].find({"corporate_contract_id": contrat_id}, {"_id": 0}).sort(
        "created_at", 1).to_list(200)


def etat_financier(contrat, factures) -> dict:
    """Facturé / payé / dû, et l'échéancier dont le statut DÉRIVE des factures liées."""
    _f = [x for x in factures if x.get("type_document") == "facture" and x.get("statut") != "annulee"]
    _par_mois = {x.get("mois"): x for x in _f}
    _facture = round(sum(float(x.get("total") or 0) for x in _f), 2)
    _paye = round(sum(float(x.get("montant_paye") or 0) for x in _f), 2)
    _ech = []
    for _l in (contrat.get("echeancier") or []):
        _x = _par_mois.get(_l.get("mois"))
        _st = "a_emettre" if not _x else ("payee" if _x.get("statut") == "payee" else "emise")
        _ech.append({"mois": _l.get("mois"), "montant": _l.get("montant"), "statut": _st,
                     "facture_numero": (_x or {}).get("invoice_number"),
                     "montant_paye": float((_x or {}).get("montant_paye") or 0),
                     "echeance": (_x or {}).get("echeance")})
    return {"total_contrat": float(contrat.get("total") or 0), "facture": _facture, "paye": _paye,
            "du": round(float(contrat.get("total") or 0) - _paye, 2),
            "facture_impaye": round(_facture - _paye, 2), "echeancier": _ech,
            "devis": [{"numero": x.get("invoice_number"), "date": x.get("date"), "valide_jusquau": x.get("valide_jusquau")}
                      for x in factures if x.get("type_document") == "devis"],
            "factures": [{"numero": x.get("invoice_number"), "mois": x.get("mois"), "statut": x.get("statut"),
                          "total": x.get("total"), "montant_paye": x.get("montant_paye") or 0,
                          "echeance": x.get("echeance"), "date": x.get("date")}
                         for x in factures if x.get("type_document") == "facture"]}


async def dto_contrat(c, avec_finances=True) -> dict:
    _d = {k: v for k, v in c.items() if k not in ("journal",)}
    if avec_finances:
        _d["finances"] = etat_financier(c, await factures_du_contrat(c.get("id")))
    return _d


# ═══════════════════════════ ROUTES ADMIN : CONTRATS ═══════════════════════════
@router.get("/api/corporate/grille")
async def v657_grille(request: Request):
    await exiger_super_admin(request)
    return {"version": GRILLE_VERSION, "grille": {str(k): {str(d): p for d, p in v.items()} for k, v in GRILLE.items()}}


@router.get("/api/corporate/prix")
async def v657_prix(request: Request, places: int = 0, mois: int = 0):
    await exiger_super_admin(request)
    _p = prix(places, mois)
    if not _p:
        raise HTTPException(status_code=400, detail="Combinaison inconnue : 5, 10 ou 20 places ; 3, 6 ou 12 mois.")
    return _p


@router.post("/api/corporate/contrats")
async def v657_creer_devis(request: Request):
    """Crée un contrat au statut DEVIS. Prix et durée lus dans la grille et FIGÉS ici."""
    _admin = await exiger_super_admin(request)
    _b = await _corps(request)
    _p = prix(_b.get("places"), _b.get("mois"))
    if not _p:
        raise HTTPException(status_code=400, detail="Combinaison inconnue : 5, 10 ou 20 places ; 3, 6 ou 12 mois.")
    _debut = str(_b.get("mois_debut") or "").strip()
    if not RE_MOIS.match(_debut):
        raise HTTPException(status_code=400, detail="Mois de début attendu au format AAAA-MM.")
    _pid = str(_b.get("prospect_id") or "").strip()[:64]
    _prospect = await db.partner_prospects.find_one({"id": _pid}, {"_id": 0, "id": 1, "organisation_name": 1, "city": 1}) if _pid else None
    if not _prospect:
        raise HTTPException(status_code=404, detail="Prospect introuvable")
    try:
        _delai = int(_b.get("delai_modif_heures") or DELAI_MODIF_DEFAUT_H)
        _paiement = int(_b.get("delai_paiement_jours") or DELAI_PAIEMENT_DEFAUT_J)
        _validite = int(_b.get("validite_devis_jours") or VALIDITE_DEVIS_DEFAUT_J)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Délais : nombres entiers attendus.")
    if not (0 <= _delai <= 720 and 1 <= _paiement <= 120 and 1 <= _validite <= 180):
        raise HTTPException(status_code=400, detail="Délais hors limites.")
    _mois = mois_suivants(_debut, _p["duree_mois"])
    _c = dict(_p)
    _c.update({
        "id": str(uuid.uuid4()),
        "entreprise": {"prospect_id": _prospect["id"], "nom": _prospect.get("organisation_name") or "",
                       "ville": _prospect.get("city") or ""},
        "facturation": _facturation_valide(_b.get("facturation")),
        "mois_debut": _mois[0], "mois_fin": _mois[-1],
        "statut": "devis", "signe_le": None,
        "token": None, "token_actif": False,
        "delai_modif_heures": _delai, "delai_paiement_jours": _paiement, "validite_devis_jours": _validite,
        "editions": [{"mois": m, "statut": "a_planifier", "offer_id": None, "course_id": None,
                      "code": None, "code_id": None, "date": None, "lieu": None} for m in _mois],
        "echeancier": [{"mois": m, "montant": _p["prix_mensuel"]} for m in _mois],
        "cree_le": _iso(), "cree_par": _admin, "maj_le": _iso(),
        "journal": [{"le": _iso(), "par": _admin, "action": "devis_cree"}],
    })
    _c["conditions"] = conditions_texte(_c)
    await db[COLL].insert_one(dict(_c))
    logger.info("%s devis %s créé (%s places x %s mois)", PREFIXE, _c["id"][:8], _p["places"], _p["duree_mois"])
    return await dto_contrat(_c)


def _facturation_valide(f) -> dict:
    """Coordonnées de facturation de l'ENTREPRISE, saisies par l'admin (jamais devinées)."""
    _f = f if isinstance(f, dict) else {}
    _t = lambda k, n: (str(_f.get(k) or "").strip()[:n] or None)  # noqa: E731
    return {"nom": _t("nom", 160), "adresse": _t("adresse", 200), "ville": _t("ville", 120),
            "contact": _t("contact", 120), "email": (_t("email", 160) or "").lower() or None}


@router.patch("/api/corporate/contrats/{contrat_id}")
async def v657_modifier_contrat(contrat_id: str, request: Request):
    """Seuls la facturation de l'entreprise et les délais se modifient ; jamais prix ni durée."""
    _admin = await exiger_super_admin(request)
    _c = await _contrat(contrat_id)
    _b = await _corps(request)
    _set = {}
    if "facturation" in _b:
        _set["facturation"] = _facturation_valide(_b.get("facturation"))
    for _k, _lo, _hi in (("delai_modif_heures", 0, 720), ("delai_paiement_jours", 1, 120), ("validite_devis_jours", 1, 180)):
        if _k in _b:
            try:
                _v = int(_b.get(_k))
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="%s : entier attendu" % _k)
            if not _lo <= _v <= _hi:
                raise HTTPException(status_code=400, detail="%s hors limites" % _k)
            _set[_k] = _v
    if not _set:
        raise HTTPException(status_code=400, detail="Rien à modifier")
    if _c.get("statut") == "devis":   # les conditions du devis suivent ses délais ; signées, elles sont figées
        _set["conditions"] = conditions_texte(dict(_c, **_set))
    _set["maj_le"] = _iso()
    await db[COLL].update_one({"id": _c["id"]}, dict({"$set": _set}, **_journal(_admin, "modifie", champs=sorted(_set))))
    return await dto_contrat(await _contrat(contrat_id))


@router.get("/api/corporate/contrats")
async def v657_lister(request: Request, page: int = 1, prospect_id: str = ""):
    await exiger_super_admin(request)
    _q = {}
    if prospect_id:
        _q["entreprise.prospect_id"] = str(prospect_id)[:64]
    _page = max(1, int(page or 1))
    _total = await db[COLL].count_documents(_q)
    _liste = await db[COLL].find(_q, {"_id": 0, "journal": 0}).sort("cree_le", -1).skip((_page - 1) * LISTE_MAX).to_list(LISTE_MAX)
    return {"contrats": [await dto_contrat(c) for c in _liste], "total": _total, "page": _page, "par_page": LISTE_MAX}


@router.get("/api/corporate/contrats/{contrat_id}")
async def v657_lire(contrat_id: str, request: Request):
    await exiger_super_admin(request)
    return await dto_contrat(await _contrat(contrat_id))


@router.post("/api/corporate/contrats/{contrat_id}/signer")
async def v657_signer(contrat_id: str, request: Request):
    """Confirmation de signature (acceptation du devis) : le contrat devient la base des places."""
    _admin = await exiger_super_admin(request)
    _c = await _contrat(contrat_id)
    _jeton = _c.get("token") or secrets.token_urlsafe(24)
    _r = await db[COLL].update_one({"id": _c["id"], "statut": "devis"},
                                   dict({"$set": {"statut": "signe", "signe_le": _iso(), "token": _jeton,
                                                  "token_actif": True, "maj_le": _iso()}}, **_journal(_admin, "signe")))
    if not _r.modified_count:
        raise HTTPException(status_code=409, detail="Seul un devis peut être signé.")
    return await dto_contrat(await _contrat(contrat_id))


async def _liberer_editions_futures(c, admin):
    """Résiliation : les retenues des éditions À VENIR sont rendues et leurs codes désactivés.
    Les inscriptions déjà faites restent (elles comptent comme des places ordinaires)."""
    for _e in (c.get("editions") or []):
        if _e.get("statut") != "planifiee":
            continue
        if _e.get("date") and E.evenement_commence(_e.get("date")):
            continue
        await db[E.COLL_RETENUES].update_one({"_id": "corp:%s:%s" % (c["id"], _e["mois"]), "statut": "active"},
                                             {"$set": {"statut": "liberee", "liberee_le": _maintenant()}})
        if _e.get("code_id"):
            await db.discount_codes.update_one({"id": _e["code_id"]}, {"$set": {"active": False}})


@router.post("/api/corporate/contrats/{contrat_id}/statut")
async def v657_statut(contrat_id: str, request: Request):
    """`resilie` (libère les places des éditions à venir) ou `termine`. Aucun effet financier."""
    _admin = await exiger_super_admin(request)
    _c = await _contrat(contrat_id)
    _cible = str((await _corps(request)).get("statut") or "")
    if _cible not in ("resilie", "termine") or _c.get("statut") != "signe":
        raise HTTPException(status_code=409, detail="Transition refusée (seul un contrat signé se résilie ou se termine).")
    if _cible == "resilie":
        await _liberer_editions_futures(_c, _admin)
    await db[COLL].update_one({"id": _c["id"], "statut": "signe"},
                              dict({"$set": {"statut": _cible, "token_actif": False, "maj_le": _iso()}},
                                   **_journal(_admin, _cible)))
    return await dto_contrat(await _contrat(contrat_id))


@router.post("/api/corporate/contrats/{contrat_id}/lien")
async def v657_lien(contrat_id: str, request: Request):
    """{"action": "revoquer" | "regenerer"}. Régénérer invalide l'ancien lien immédiatement."""
    _admin = await exiger_super_admin(request)
    _c = await _contrat(contrat_id)
    _a = str((await _corps(request)).get("action") or "")
    if _c.get("statut") != "signe":
        raise HTTPException(status_code=409, detail="Le lien n'existe que pour un contrat signé.")
    if _a == "revoquer":
        _set = {"token_actif": False}
    elif _a == "regenerer":
        _set = {"token": secrets.token_urlsafe(24), "token_actif": True}
    else:
        raise HTTPException(status_code=400, detail="Action inconnue")
    await db[COLL].update_one({"id": _c["id"]}, dict({"$set": dict(_set, maj_le=_iso())}, **_journal(_admin, "lien_" + _a)))
    return await dto_contrat(await _contrat(contrat_id))


@router.post("/api/corporate/contrats/{contrat_id}/editions/{mois}/lier")
async def v657_lier_edition(contrat_id: str, mois: str, request: Request):
    """Lie l'édition du mois à un événement EXISTANT (offre `event` à réservation automatique,
    cours daté de ce mois). RETIENT les places sous verrou : refus 409 s'il n'en reste pas assez."""
    _admin = await exiger_super_admin(request)
    _c = await _contrat(contrat_id)
    if _c.get("statut") != "signe":
        raise HTTPException(status_code=409, detail="Seul un contrat signé retient des places.")
    _ed = next((e for e in (_c.get("editions") or []) if e.get("mois") == mois), None)
    if not _ed:
        raise HTTPException(status_code=404, detail="Édition inconnue pour ce contrat")
    if _ed.get("statut") != "a_planifier":
        raise HTTPException(status_code=409, detail="Cette édition est déjà planifiée.")
    _oid = str((await _corps(request)).get("offer_id") or "")[:64]
    _offre = await db.offers.find_one({"id": _oid}, {"_id": 0}) if _oid else None
    if not _offre or _offre.get("archived") is True or not E.reservation_auto(_offre):
        raise HTTPException(status_code=404, detail="Événement introuvable (offre « événement » à réservation automatique requise).")
    _cours = await E.cours_de_l_evenement(db, _offre)
    _occ = E.occurrence(_cours)
    if not _occ:
        raise HTTPException(status_code=409, detail="L'événement n'a pas de date fixe.")
    if _occ[:7] != mois:
        raise HTTPException(status_code=409, detail="L'événement n'a pas lieu en %s." % mois)
    if E.evenement_commence(_occ):
        raise HTTPException(status_code=409, detail="L'événement a déjà commencé.")
    _places = int(_c.get("places") or 0)
    _ret_id = "corp:%s:%s" % (_c["id"], mois)
    try:
        async with E.verrou_capacite(db, _offre):
            _reste = await E.places_restantes(db, _offre)
            if _reste is not None and _reste < _places:
                raise HTTPException(status_code=409, detail="Pas assez de places sur cet événement : %d restantes, %d demandées."
                                    % (_reste, _places))
            try:
                await db[E.COLL_RETENUES].insert_one({
                    "_id": _ret_id, "id": _ret_id, "offer_id": _oid, "type": E.RETENUE_CORPORATE, "places": _places,
                    "corporate_contract_id": _c["id"], "mois": mois, "statut": "active", "cree_le": _maintenant()})
            except Exception as _err:  # noqa: BLE001
                if E._doublon(_err):
                    raise HTTPException(status_code=409, detail="Cette édition retient déjà des places.")
                raise
    except E.VerrouIndisponible:
        raise HTTPException(status_code=409, detail=E.MSG_OCCUPE)
    # Code caché, limité à CET événement (offre + cours daté), jamais global.
    _code = "CORP-" + secrets.token_hex(8).upper()
    _code_id = str(uuid.uuid4())
    await db.discount_codes.insert_one({
        "id": _code_id, "code": _code, "type": "100%", "value": 100, "maxUses": _places, "used": 0,
        "active": True, "expiresAt": _occ[:10], "courses": [_oid, (_cours or {}).get("id")],
        "coach_id": E.proprietaire_evenement(_offre, _cours) or SUPER_ADMIN_EMAIL,
        "assignedEmail": None, "multi_member": False, "canonical": True,
        "corporate_contract_id": _c["id"], "corporate_mois": mois, "cache": True,
        "created_at": _iso(), "created_by": _admin})
    _lieu = (_cours or {}).get("locationName") or (_cours or {}).get("location") or _offre.get("location") or ""
    _r = await db[COLL].update_one(
        {"id": _c["id"], "editions": {"$elemMatch": {"mois": mois, "statut": "a_planifier"}}},
        dict({"$set": {"editions.$.statut": "planifiee", "editions.$.offer_id": _oid,
                       "editions.$.course_id": (_cours or {}).get("id"), "editions.$.code": _code,
                       "editions.$.code_id": _code_id, "editions.$.date": _occ, "editions.$.lieu": _lieu,
                       "maj_le": _iso()}}, **_journal(_admin, "edition_liee", mois=mois, offer_id=_oid)))
    if not _r.modified_count:   # course perdue : tout est défait
        await db[E.COLL_RETENUES].delete_one({"_id": _ret_id})
        await db.discount_codes.delete_one({"id": _code_id})
        raise HTTPException(status_code=409, detail="Cette édition vient d'être planifiée.")
    return await dto_contrat(await _contrat(contrat_id))


# ═══════════════════════════ INSCRIPTIONS (admin) ═══════════════════════════
def _delai_depasse(contrat, edition) -> bool:
    _debut = E.debut_utc(edition.get("date"))
    if _debut is None:
        return True
    return _maintenant() >= _debut - timedelta(hours=int(contrat.get("delai_modif_heures") or DELAI_MODIF_DEFAUT_H))


def _dto_inscription(r) -> dict:
    return {k: r.get(k) for k in ("id", "userName", "userEmail", "userWhatsapp", "reservationCode", "datetime",
                                  "courseName", "createdAt", "validated", "corporate_mois")}


@router.get("/api/corporate/contrats/{contrat_id}/editions/{mois}/inscriptions")
async def v657_inscriptions(contrat_id: str, mois: str, request: Request):
    await exiger_super_admin(request)
    _c = await _contrat(contrat_id)
    _liste = await db.reservations.find({"corporate_contract_id": _c["id"], "corporate_mois": str(mois)[:7]},
                                        {"_id": 0}).sort("createdAt", 1).to_list(LISTE_MAX)
    _ed = next((e for e in (_c.get("editions") or []) if e.get("mois") == mois), {}) or {}
    return {"inscriptions": [_dto_inscription(r) for r in _liste], "places": _c.get("places"),
            "places_restantes": max(0, int(_c.get("places") or 0) - len(_liste)),
            "delai_depasse": _delai_depasse(_c, _ed) if _ed.get("date") else False}


async def _inscription(c, reservation_id):
    _r = await db.reservations.find_one({"id": str(reservation_id)[:64], "corporate_contract_id": c["id"]}, {"_id": 0})
    if not _r:
        raise HTTPException(status_code=404, detail="Inscription introuvable")
    _ed = next((e for e in (c.get("editions") or []) if e.get("mois") == _r.get("corporate_mois")), None) or {}
    return _r, _ed


@router.patch("/api/corporate/contrats/{contrat_id}/inscriptions/{reservation_id}")
async def v657_corriger_inscription(contrat_id: str, reservation_id: str, request: Request):
    """Corrige le nom / WhatsApp (toujours), ou REMPLACE la personne (nouvel e-mail) jusqu'au délai."""
    _admin = await exiger_super_admin(request)
    _c = await _contrat(contrat_id)
    _r, _ed = await _inscription(_c, reservation_id)
    _b = await _corps(request)
    _set = {}
    if _b.get("nom"):
        _set["userName"] = str(_b["nom"]).strip()[:80]
    if "whatsapp" in _b:
        _set["userWhatsapp"] = re.sub(r"[^0-9+ ]", "", str(_b.get("whatsapp") or ""))[:30].strip()
    _nouvel = normaliser_email(_b.get("email")) if _b.get("email") else ""
    if _nouvel and _nouvel != _r.get("userEmail"):
        if not RE_EMAIL.match(_nouvel):
            raise HTTPException(status_code=400, detail="Adresse e-mail invalide.")
        if _delai_depasse(_c, _ed):
            raise HTTPException(status_code=409, detail=MSG_CLOS)
        _offre_id = _r.get("offerId")
        if await db.reservations.find_one({"offerId": _offre_id, "userEmail": _nouvel, "status": {"$ne": "cancelled"}}, {"_id": 1}):
            raise HTTPException(status_code=409, detail=MSG_DOUBLON)
        _ancienne = _r.get("evenement_place_cle")
        _place = await db[E.COLL_PLACES].find_one({"_id": _ancienne}) or {}
        _nouvelle = "code:%s:%s" % (_offre_id, _nouvel)
        try:
            await db[E.COLL_PLACES].insert_one(dict({k: v for k, v in _place.items() if k != "_id"}, _id=_nouvelle))
        except Exception as _err:  # noqa: BLE001
            if E._doublon(_err):
                raise HTTPException(status_code=409, detail=MSG_DOUBLON)
            raise
        _set.update({"userEmail": _nouvel, "evenement_place_cle": _nouvelle})
        await db.reservations.update_one({"id": _r["id"]}, {"$set": _set})
        await db[E.COLL_PLACES].delete_one({"_id": _ancienne, "reservation_id": _r["id"]})
    elif _set:
        await db.reservations.update_one({"id": _r["id"]}, {"$set": _set})
    else:
        raise HTTPException(status_code=400, detail="Rien à corriger")
    await db[COLL].update_one({"id": _c["id"]}, _journal(_admin, "inscription_corrigee", reservation_id=_r["id"]))
    return _dto_inscription(await db.reservations.find_one({"id": _r["id"]}, {"_id": 0}))


@router.delete("/api/corporate/contrats/{contrat_id}/inscriptions/{reservation_id}")
async def v657_annuler_inscription(contrat_id: str, reservation_id: str, request: Request):
    """Annule l'inscription jusqu'au délai : la place revient à l'entreprise (code rendu)."""
    _admin = await exiger_super_admin(request)
    _c = await _contrat(contrat_id)
    _r, _ed = await _inscription(_c, reservation_id)
    if _delai_depasse(_c, _ed):
        raise HTTPException(status_code=409, detail=MSG_CLOS + " La place est perdue (aucun report).")
    _sup = await db.reservations.delete_one({"id": _r["id"]})
    if not _sup.deleted_count:
        raise HTTPException(status_code=404, detail="Inscription introuvable")
    await E.liberer_place(db, _r)
    from api.routes.shared import seances_restituer
    await seances_restituer(db, _r.get("promoCode") or "", 1, reservation_id=_r["id"], source="corporate_annulation")
    await db[COLL].update_one({"id": _c["id"]}, _journal(_admin, "inscription_annulee", reservation_id=_r["id"]))
    return {"success": True}


# ═══════════════════════════ INVITATION PUBLIQUE ═══════════════════════════
async def _contrat_par_jeton(token):
    _t = str(token or "")
    if not RE_JETON.match(_t):
        return None
    _c = await db[COLL].find_one({"token": _t}, {"_id": 0})
    if not _c or _c.get("token_actif") is not True or _c.get("statut") != "signe":
        return None
    return _c


@router.get("/api/corporate/invitation/{token}")
async def v657_invitation(token: str):
    """Page publique : entreprise, éditions (date/lieu SEULEMENT si planifiées), places restantes.
    Aucune donnée personnelle, aucun code."""
    _c = await _contrat_par_jeton(token)
    if not _c:
        raise HTTPException(status_code=404, detail=MSG_INTROUVABLE)
    _eds = []
    for _e in (_c.get("editions") or []):
        _d = {"mois": _e.get("mois"), "statut": _e.get("statut")}
        if _e.get("statut") == "planifiee" and _e.get("date"):
            _pris = await E.places_corporate_reclamees(db, _e.get("offer_id"), _c["id"])
            _d.update({"date": _e.get("date"), "lieu": _e.get("lieu") or "",
                       "places_restantes": max(0, int(_c.get("places") or 0) - _pris),
                       "inscriptions_ouvertes": not _delai_depasse(_c, _e) and not E.evenement_commence(_e.get("date"))})
        _eds.append(_d)
    return {"entreprise": (_c.get("entreprise") or {}).get("nom") or "", "places_par_edition": _c.get("places"),
            "delai_modif_heures": _c.get("delai_modif_heures"), "editions": _eds}


@router.post("/api/corporate/invitation/{token}/inscription")
async def v657_inscrire(token: str, request: Request):
    """Inscription d'un·e employé·e à 0 CHF — UNIQUEMENT pour un contrat SIGNÉ, lien actif,
    édition planifiée, avant le délai, dans la limite des places du contrat ; une adresse
    e-mail = une place par édition. Machinerie V628 : débit atomique du code caché du
    contrat (`seances_consommer`), réclamation unique `code:<offre>:<e-mail>`, billet."""
    from api.routes.checkout_routes import _essai7_debit_ok
    _ip_c = _ip(request)
    if _ip_c and not _essai7_debit_ok("corp:" + _ip_c):
        raise HTTPException(status_code=429, detail="Trop de tentatives. Réessaie dans un moment.")
    _b = await _corps(request)
    _email = normaliser_email(str(_b.get("email") or "")[:254])
    # V657b : route publique dont le nom part dans un e-mail : aucun caractère HTML n'y entre.
    _nom = re.sub(r"\s+", " ", re.sub(r"[<>&\"'`]", "", str(_b.get("nom") or ""))).strip()[:80]
    _whatsapp = re.sub(r"[^0-9+ ]", "", str(_b.get("whatsapp") or ""))[:30].strip()
    _mois = str(_b.get("mois") or "")[:7]
    if not RE_EMAIL.match(_email):
        raise HTTPException(status_code=400, detail="Adresse e-mail invalide.")
    if len(_nom) < 2:
        raise HTTPException(status_code=400, detail="Nom et prénom requis.")
    _c = await _contrat_par_jeton(token)
    if not _c:
        raise HTTPException(status_code=404, detail=MSG_INTROUVABLE)
    _ed = next((e for e in (_c.get("editions") or []) if e.get("mois") == _mois), None)
    if not _ed or _ed.get("statut") != "planifiee" or not _ed.get("offer_id"):
        raise HTTPException(status_code=409, detail=MSG_NON_PLANIFIEE)
    _offre = await db.offers.find_one({"id": _ed["offer_id"]}, {"_id": 0})
    if not _offre or not E.reservation_auto(_offre):
        raise HTTPException(status_code=409, detail=MSG_NON_PLANIFIEE)
    _cours = await E.cours_de_l_evenement(db, _offre)
    _occ = E.occurrence(_cours)
    if not _occ or E.evenement_commence(_occ) or _delai_depasse(_c, dict(_ed, date=_occ)):
        raise HTTPException(status_code=409, detail=MSG_CLOS)
    from api.server import t1_preuve
    _t1 = await t1_preuve(_b.get("terms_accepted") is True, (_cours or {}).get("id") or "",
                          (_cours or {}).get("coach_id") or _offre.get("coach_id") or "")
    _fiche = await db.discount_codes.find_one({"id": _ed.get("code_id"), "corporate_contract_id": _c["id"]}, {"_id": 0})
    _refus = E.verifier_code_evenement(_fiche, _offre, cours=_cours)
    if _refus == E.MSG_CODE_UTILISE:
        raise HTTPException(status_code=409, detail=MSG_PLEIN)
    if _refus:
        logger.warning("%s code du contrat %s inutilisable (%s)", PREFIXE, _c["id"][:8], _refus)
        raise HTTPException(status_code=409, detail=MSG_NON_PLANIFIEE)
    _cle = "code:%s:%s" % (_offre.get("id"), _email)
    _deja, _ = await E._deja(db, _cle)
    if _deja or await db.reservations.find_one({"offerId": _offre.get("id"), "userEmail": _email,
                                                "status": {"$ne": "cancelled"}}, {"_id": 1}):
        raise HTTPException(status_code=409, detail=MSG_DOUBLON)
    from api.routes.shared import seances_consommer, seances_restituer
    _code = str(_fiche.get("code") or "").upper()
    _rid = str(uuid.uuid4())
    try:
        async with E.verrou_capacite(db, _offre, force=True):
            _ret = await db[E.COLL_RETENUES].find_one({"_id": "corp:%s:%s" % (_c["id"], _mois), "statut": "active"})
            _pris = await E.places_corporate_reclamees(db, _offre.get("id"), _c["id"])
            if not _ret or _pris >= int(_ret.get("places") or 0):
                raise HTTPException(status_code=409, detail=MSG_PLEIN)
            _debit = await seances_consommer(db, _code, 1, reservation_id=_rid, source="corporate")
            if not _debit.get("debite"):
                raise HTTPException(status_code=409, detail=MSG_PLEIN)
            try:
                _resa, _creee = await E.reserver(
                    db, cle=_cle, offre=_offre, cours=_cours, occ=_occ, email=_email, nom=_nom, prix=0,
                    source=E.SOURCE_CODE, code=_code, whatsapp=_whatsapp, reservation_id=_rid,
                    extra=dict(_t1, paiement="corporate", code_fiche_id=_fiche.get("id"),
                               corporate_contract_id=_c["id"], corporate_mois=_mois,
                               entreprise=(_c.get("entreprise") or {}).get("nom") or ""),
                    place_extra={"corporate_contract_id": _c["id"], "mois": _mois})
            except Exception:
                if not await db.reservations.find_one({"id": _rid}, {"_id": 1}):
                    await seances_restituer(db, _code, 1, reservation_id=_rid, source="corporate_echec")
                raise
            if not _creee:
                await seances_restituer(db, _code, 1, reservation_id=_rid, source="corporate_doublon")
                raise HTTPException(status_code=409, detail=MSG_DOUBLON)
    except E.VerrouIndisponible:
        raise HTTPException(status_code=409, detail=E.MSG_OCCUPE)
    try:   # même confirmation qu'une place par code (V628) : e-mail avec le billet
        from api.routes.shared import notifier_reservation_creee
        from api.routes.reservation_routes import _send_reservation_email, _send_coach_reservation_email
        from api.server import send_push_by_email
        import asyncio

        async def _mail_client(_r):
            return bool(await _send_reservation_email(_email, _nom, _r, None, user_lang=None, user_whatsapp=_whatsapp))

        asyncio.create_task(notifier_reservation_creee(db, _resa, envoyer_email_client=_mail_client,
                                                       envoyer_push_coach=send_push_by_email,
                                                       envoyer_email_coach=_send_coach_reservation_email))
    except Exception as _n:  # noqa: BLE001 — la place est prise, la notification suit ou non
        logger.warning("%s notification non partie (%s)", PREFIXE, type(_n).__name__)
    logger.info("%s inscription %s (contrat %s, %s)", PREFIXE, _resa.get("reservationCode"), _c["id"][:8], _mois)
    return {"success": True, "prix": 0,
            "reservation": {k: _resa.get(k) for k in ("reservationCode", "courseName", "datetime", "offerName")},
            "lieu": _ed.get("lieu") or ""}


# ═══════════════════════════ PROSPECT : SUIVI FINANCIER (lecture) ═══════════════════════════
@router.get("/api/corporate/prospects/{prospect_id}/suivi-financier")
async def v657_suivi_prospect(prospect_id: str, request: Request):
    await exiger_super_admin(request)
    _cs = await db[COLL].find({"entreprise.prospect_id": str(prospect_id)[:64]}, {"_id": 0, "journal": 0}) \
        .sort("cree_le", -1).to_list(20)
    _sortie = []
    for _c in _cs:
        _f = etat_financier(_c, await factures_du_contrat(_c["id"]))
        _sortie.append({"id": _c["id"], "statut": _c.get("statut"), "places": _c.get("places"),
                        "duree_mois": _c.get("duree_mois"), "prix_mensuel": _c.get("prix_mensuel"),
                        "total": _c.get("total"), "mois_debut": _c.get("mois_debut"),
                        "devis": _f["devis"], "factures": _f["factures"], "facture": _f["facture"],
                        "paye": _f["paye"], "du": _f["du"]})
    return {"contrats": _sortie}


# ═══════════════════════════ FACTURATION : extension du générateur existant ═══════════════════════════
# Appelé par `POST /api/invoices/generate` (server.py) — UN SEUL système de factures.
async def reglages_facturation() -> dict:
    return await db[COLL_REGLAGES].find_one({"_id": ID_REGLAGES}, {"_id": 0}) or {}


async def prochain_numero(prefixe: str, annee: int) -> str:
    """Compteur ATOMIQUE par préfixe et par année : AF-CORP-2026-0001, DEVIS-2026-0001."""
    from pymongo import ReturnDocument
    _cle = "%s-%d" % (prefixe, annee)
    _d = await db[COLL_COMPTEURS].find_one_and_update({"_id": _cle}, {"$inc": {"seq": 1}}, upsert=True,
                                                      return_document=ReturnDocument.AFTER)
    return "%s-%04d" % (_cle, int(_d.get("seq") or 1))


def demande_etendue(body) -> bool:
    return bool((body or {}).get("corporate_contract_id")) or str((body or {}).get("type_document") or "") == "devis"


def _jour_ch(d):
    return d.strftime("%d.%m.%Y")


async def preparer_document(body, auteur) -> dict:
    """Le document à rendre et à enregistrer, ou HTTPException. Les montants et lignes d'un
    document Entreprise sont CALCULÉS ici depuis le contrat — jamais repris du navigateur."""
    _type = str(body.get("type_document") or "facture")
    if _type not in ("facture", "devis"):
        raise HTTPException(status_code=400, detail="type_document : « facture » ou « devis ».")
    _cid = str(body.get("corporate_contract_id") or "")[:64]
    _auj = datetime.now(timezone.utc).date()
    if not _cid:   # devis hors Entreprise : numérotation DEVIS, contenu du formulaire (comme avant)
        return {"type_document": "devis", "numero": await prochain_numero("DEVIS", _auj.year), "corporate": None}
    if not is_super_admin(auteur):
        raise HTTPException(status_code=403, detail="Documents Entreprise réservés au super-admin")
    _reg = await reglages_facturation()
    if _reg.get("verifie") is not True or not (_reg.get("nom") and _reg.get("iban")):
        raise HTTPException(status_code=409, detail=MSG_COORDONNEES)
    _c = await _contrat(_cid)
    _fac = _c.get("facturation") or {}
    if not _fac.get("nom"):
        raise HTTPException(status_code=409, detail="Coordonnées de facturation de l'entreprise manquantes (contrat).")
    _emetteur = {"name": _reg.get("nom"), "address": _reg.get("adresse") or "", "city": _reg.get("ville") or "",
                 "iban": _reg.get("iban"), "contact": _reg.get("contact") or "", "ide": _reg.get("ide") or ""}
    _dest = {"name": _fac.get("nom"), "address": _fac.get("adresse") or "",
             "city": _fac.get("ville") or "", "contact": _fac.get("contact") or ""}
    _champs = {"type": "corporate", "corporate_contract_id": _cid, "entreprise": (_c.get("entreprise") or {}).get("nom"),
               "emitter": _emetteur, "recipient": _dest}
    if _type == "devis":
        if _c.get("statut") not in ("devis", "signe"):
            raise HTTPException(status_code=409, detail="Contrat résilié ou terminé : aucun devis.")
        _valid = _auj + timedelta(days=int(_c.get("validite_devis_jours") or VALIDITE_DEVIS_DEFAUT_J))
        _items = [{"description": "Afroboost Corporate — %d places par édition, 1 édition par mois (%s à %s)"
                   % (_c["places"], _c["mois_debut"], _c["mois_fin"]),
                   "quantity": _c["duree_mois"], "unit_price": _c["prix_mensuel"], "total": _c["total"]}]
        _notes = "\n".join(lignes_devis(_c) + (_c.get("conditions") or conditions_texte(_c)).split("\n")
                           + ["Devis valable jusqu'au %s." % _jour_ch(_valid)])
        return dict(_champs, type_document="devis", numero=await prochain_numero("DEVIS", _auj.year),
                    items=_items, notes=_notes, valide_jusquau=_valid.isoformat(), contrat=_c)
    # FACTURE mensuelle
    if _c.get("statut") != "signe":
        raise HTTPException(status_code=409, detail="Une facture mensuelle exige un contrat signé.")
    _mois = str(body.get("mois") or "")[:7]
    _ligne = next((l for l in (_c.get("echeancier") or []) if l.get("mois") == _mois), None)
    if not _ligne:
        raise HTTPException(status_code=400, detail="Mois hors du contrat.")
    if await db[COLL_FACTURES].find_one({"cle_unicite": "%s:%s" % (_cid, _mois)}, {"_id": 1}):
        raise HTTPException(status_code=409, detail="Une facture existe déjà pour %s." % _mois)
    _ech = str(body.get("echeance") or "")[:10]
    if not RE_JOUR.match(_ech):
        _ech = (_auj + timedelta(days=int(_c.get("delai_paiement_jours") or DELAI_PAIEMENT_DEFAUT_J))).isoformat()
    _items = [{"description": "Afroboost Corporate — édition %s — %d places" % (_mois, _c["places"]),
               "quantity": 1, "unit_price": _ligne["montant"], "total": _ligne["montant"]}]
    _numero = await prochain_numero("AF-CORP", _auj.year)
    _notes = "\n".join(["Paiement par virement bancaire au plus tard le %s." % _jour_ch(datetime.fromisoformat(_ech)),
                        "Référence à indiquer : %s." % _numero,
                        "Places non utilisées : perdues, sans report ni remboursement."])
    return dict(_champs, type_document="facture", numero=_numero,
                items=_items, notes=_notes, mois=_mois, echeance=_ech, contrat=_c)


async def enregistrer_document(doc, total, date_txt, auteur) -> None:
    """Insère l'enregistrement (statut, paiements, rappels) puis référence le numéro sur le contrat."""
    _rec = {"invoice_number": doc["numero"], "date": date_txt, "emitter": doc.get("emitter"),
            "recipient": doc.get("recipient"), "items": doc.get("items"), "total": round(float(total), 2),
            "notes": doc.get("notes"), "created_at": datetime.utcnow().isoformat(), "cree_par": auteur,
            "type_document": doc["type_document"], "statut": "emise", "montant_paye": 0.0,
            "paiements": [], "rappels": []}
    if doc.get("corporate_contract_id"):
        _rec.update({"type": "corporate", "corporate_contract_id": doc["corporate_contract_id"],
                     "entreprise": doc.get("entreprise")})
    if doc["type_document"] == "devis":
        _rec.update({"valide_jusquau": doc.get("valide_jusquau"), "statut": "emise"})
    else:
        _rec.update({"mois": doc.get("mois"), "echeance": doc.get("echeance"),
                     "cle_unicite": "%s:%s" % (doc["corporate_contract_id"], doc.get("mois"))})
    try:
        await db[COLL_FACTURES].insert_one(_rec)
    except Exception as _err:  # noqa: BLE001
        if E._doublon(_err):
            raise HTTPException(status_code=409, detail="Une facture existe déjà pour %s." % doc.get("mois"))
        raise
    if doc.get("corporate_contract_id"):
        _champ = "devis_numeros" if doc["type_document"] == "devis" else "factures_numeros"
        await db[COLL].update_one({"id": doc["corporate_contract_id"]},
                                  dict({"$addToSet": {_champ: doc["numero"]}, "$set": {"maj_le": _iso()}},
                                       **_journal(auteur, doc["type_document"] + "_emis", numero=doc["numero"])))


def peut_voir_facture(rec, email) -> bool:
    return is_super_admin(email) or (bool(rec.get("cree_par")) and rec.get("cree_par") == email)


async def enregistrer_paiement(numero, body, auteur) -> dict:
    """Paiement (partiel admis) d'UNE facture Entreprise, validé par `b_valider_encaissement`.
    Concurrence : mise à jour conditionnée au montant déjà payé lu (aucun double comptage)."""
    _rec = await db[COLL_FACTURES].find_one({"invoice_number": str(numero)[:40]}, {"_id": 0})
    if not _rec or not peut_voir_facture(_rec, auteur):
        raise HTTPException(status_code=404, detail="Facture introuvable")
    if _rec.get("type_document") != "facture" or "statut" not in _rec:
        raise HTTPException(status_code=409, detail="Paiement réservé aux factures suivies (Entreprise).")
    if _rec.get("statut") != "emise":
        raise HTTPException(status_code=409, detail="Facture déjà payée ou annulée.")
    _mode = str(body.get("mode") or "virement")
    if _mode == "offert":
        raise HTTPException(status_code=400, detail="Un paiement de facture ne peut pas être « offert ».")
    _v = b_valider_encaissement(body.get("montant"), _mode, saisi_par=auteur)
    _deja = round(float(_rec.get("montant_paye") or 0), 2)
    _reste = round(float(_rec.get("total") or 0) - _deja, 2)
    if _v["montant_encaisse"] > _reste + 0.005:
        raise HTTPException(status_code=400, detail="Montant supérieur au reste dû (%.2f CHF)." % _reste)
    _date = str(body.get("date") or "")[:10]
    if not RE_JOUR.match(_date):
        _date = datetime.now(timezone.utc).date().isoformat()
    _nouveau = round(_deja + _v["montant_encaisse"], 2)
    _p = {"id": str(uuid.uuid4()), "mode": _v["origine_paiement"], "montant": _v["montant_encaisse"],
          "devise": _v["devise"], "date": _date, "reference": str(body.get("reference") or "").strip()[:80] or None,
          "saisi_par": auteur, "saisi_le": _iso()}
    _r = await db[COLL_FACTURES].update_one(
        {"invoice_number": _rec["invoice_number"], "statut": "emise", "montant_paye": _rec.get("montant_paye", 0)},
        {"$set": {"montant_paye": _nouveau,
                  "statut": "payee" if _nouveau >= round(float(_rec.get("total") or 0), 2) - 0.005 else "emise"},
         "$push": {"paiements": _p}})
    if not _r.modified_count:
        raise HTTPException(status_code=409, detail="La facture vient d'être modifiée : recharge et réessaie.")
    return await db[COLL_FACTURES].find_one({"invoice_number": _rec["invoice_number"]}, {"_id": 0})


def texte_rappel(rec, contrat) -> str:
    """Brouillon PROFESSIONNEL de rappel (à copier) — rien n'est envoyé."""
    _reste = round(float(rec.get("total") or 0) - float(rec.get("montant_paye") or 0), 2)
    _ech = rec.get("echeance") or ""
    try:
        _ech_txt = _jour_ch(datetime.fromisoformat(_ech))
    except ValueError:
        _ech_txt = _ech
    _qui = ((rec.get("recipient") or {}).get("contact") or "").strip()
    return "\n".join([
        "Bonjour%s," % ((" " + _qui) if _qui else ""),
        "",
        "Sauf erreur de notre part, la facture %s du %s (Afroboost Corporate, édition %s), d'un montant de "
        "%.2f CHF, arrivée à échéance le %s, présente un solde ouvert de %.2f CHF."
        % (rec.get("invoice_number"), rec.get("date") or "", rec.get("mois") or "", float(rec.get("total") or 0),
           _ech_txt, _reste),
        "",
        "Nous vous remercions de bien vouloir procéder au virement en indiquant la référence %s. "
        "Si le paiement a été effectué entre-temps, merci de ne pas tenir compte de ce message." % rec.get("invoice_number"),
        "",
        "Avec nos meilleures salutations,",
        ((rec.get("emitter") or {}).get("name") or "Afroboost"),
    ])


@router.get("/api/invoices/reglages-facturation")
async def v657_lire_reglages(request: Request):
    await exiger_super_admin(request)
    return await reglages_facturation()


@router.put("/api/invoices/reglages-facturation")
async def v657_ecrire_reglages(request: Request):
    """Coordonnées de l'ÉMETTEUR pour les documents Entreprise. Toute modification remet
    « vérifiées » à faux, sauf si la même requête les déclare vérifiées (super-admin)."""
    _admin = await exiger_super_admin(request)
    _b = await _corps(request)
    _t = lambda k, n: (html.unescape(str(_b.get(k) or "")).strip()[:n] or None)  # noqa: E731
    _doc = {"nom": _t("nom", 160), "adresse": _t("adresse", 200), "ville": _t("ville", 120),
            "iban": _t("iban", 40), "contact": _t("contact", 120), "ide": _t("ide", 40),
            "verifie": _b.get("verifie") is True, "maj_le": _iso(), "maj_par": _admin}
    if _doc["verifie"]:
        if not (_doc["nom"] and _doc["iban"] and _doc["adresse"] and _doc["ville"]):
            raise HTTPException(status_code=400, detail="Nom, adresse, ville et IBAN requis pour déclarer les coordonnées vérifiées.")
        _doc.update({"verifie_par": _admin, "verifie_le": _iso()})
    else:
        _doc.update({"verifie_par": None, "verifie_le": None})
    await db[COLL_REGLAGES].update_one({"_id": ID_REGLAGES}, {"$set": _doc}, upsert=True)
    return await reglages_facturation()
