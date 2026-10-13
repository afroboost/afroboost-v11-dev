# -*- coding: utf-8 -*-
# V610o : PROGRAMME AMBASSADEUR AFROBOOST — les Boosts, lus sur la chaîne V607.
"""V610o — Boosts, paliers et récompenses des ambassadeurs (événements).

COLLECTIONS (aucune autre n'est créée) :
  ambassadeur_boosts       — _id `boost:<relais du filleul>` : parrain (relais, jeton,
                             prénom, empreinte d'e-mail), filleul (relais, prénom),
                             campagne, coach, preuve, paiement, statut granted|revoked,
                             historique [{at, evenement: BOOST_GRANTED|BOOST_REVOKED, raison}].
  ambassadeur_recompenses  — _id `<coach>|<empreinte>|<palier>` : palier débloqué, état
                             (disponible/utilise, a_remettre/remise, actif), historique,
                             `a_verifier` si les Boosts repassent sous le seuil après coup.
  referral_programs        — UN document `type: "ambassadeur"` par coach : la configuration
                             (paliers, message « 50 PLACES », Pass Ami, avantage filleul inactif).
Notification coach : `notifications` (type `ambassadeur_palier`), interne seulement.

CONFIDENTIALITÉ : le membre ne voit que SES Boosts (session d'espace ou session Stripe
payée, toutes deux non devinables) ; le coach (JWT strict) ne voit que les ambassadeurs de
SES invitations, avec les coordonnées de SES réservations. Jamais d'e-mail en clair stocké
ici (empreinte seulement).
"""
import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from api.routes import ambassadeur_engine as A

logger = logging.getLogger(__name__)
PREFIXE = "[V610o-AMBASSADEUR]"
COLL_BOOSTS = "ambassadeur_boosts"
COLL_RECOMPENSES = "ambassadeur_recompenses"
COLL_PROGRAMMES = "referral_programs"
COLL_RELAIS = "invitation_relais"
TYPE_NOTIF = "ambassadeur_palier"
LISTE_MAX = 200
RECENTS_MAX = 10

router = APIRouter(tags=["ambassadeur"])
db = None


def init_db(database):
    global db
    db = database


def _base(database=None):
    return database if database is not None else db


async def assurer_index(database) -> None:
    try:
        await database[COLL_BOOSTS].create_index([("coach_id", 1), ("parrain_empreinte", 1)])
        await database[COLL_BOOSTS].create_index("payment_intent")
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s index non posés (%s)", PREFIXE, type(_err).__name__)


def _iso():
    return datetime.now(timezone.utc).isoformat()


def _doublon(err) -> bool:
    return type(err).__name__ == "DuplicateKeyError" or "e11000" in str(err).lower() or "duplicate" in str(err).lower()


async def config_du_coach(database, coach_id) -> dict:
    try:
        _d = await _base(database)[COLL_PROGRAMMES].find_one({"type": "ambassadeur", "coach_id": str(coach_id or "")}, {"_id": 0})
    except Exception:  # noqa: BLE001
        _d = None
    return A.config_valide(_d)


async def nombre_boosts(database, coach_id, empreinte) -> int:
    return await _base(database)[COLL_BOOSTS].count_documents(
        {"coach_id": str(coach_id or ""), "parrain_empreinte": empreinte, "statut": A.STATUT_ACCORDE})


async def _notifier_coach(database, coach_id, titre, message, cle):
    """Notification INTERNE du coach (jamais d'e-mail / WhatsApp). Idempotente par `cle`."""
    try:
        await _base(database)["notifications"].update_one(
            {"id": cle}, {"$setOnInsert": {"id": cle, "type": TYPE_NOTIF, "title": titre, "message": message,
                                           "coach_id": str(coach_id or ""), "read": False, "created_at": _iso()}},
            upsert=True)
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s notification coach non écrite (%s)", PREFIXE, type(_err).__name__)


async def _appliquer_paliers(database, coach_id, empreinte, prenom, avant, apres):
    """Paliers franchis -> récompense historisée (idempotente) + notification coach ;
    paliers repassés sous le seuil -> rien d'effacé : `a_verifier` si déjà profitée."""
    _cfg = await config_du_coach(database, coach_id)
    _b = _base(database)
    for _p in A.paliers_franchis(avant, apres, _cfg["paliers"]):
        _id = "%s|%s|%s" % (coach_id, empreinte, _p["cle"])
        try:
            await _b[COLL_RECOMPENSES].update_one(
                {"_id": _id},
                {"$setOnInsert": {"_id": _id, "coach_id": coach_id, "ambassadeur_empreinte": empreinte,
                                  "ambassadeur_prenom": prenom or "", "palier": _p["cle"], "seuil": _p["seuil"],
                                  "libelle": _p["libelle"], "etat": A.ETATS_INITIAUX.get(_p["cle"], "actif"),
                                  "debloque_le": _iso(), "historique": [{"at": _iso(), "evenement": "PALIER_DEBLOQUE", "boosts": apres}]},
                 "$unset": {"a_verifier": ""}},
                upsert=True)
        except Exception as _err:  # noqa: BLE001
            if not _doublon(_err):
                logger.warning("%s palier non historisé (%s)", PREFIXE, type(_err).__name__)
        _phrase = {"pass_ami": "%s débloque son Pass Ami (%d Boosts).",
                   "recompense": "%s débloque sa Récompense Afroboost (%d Boosts).",
                   "vip": "%s devient Ambassadeur VIP (%d Boosts)."}.get(_p["cle"], "%s franchit un palier (%d Boosts).")
        await _notifier_coach(database, coach_id, "Ambassadeur : palier débloqué",
                              _phrase % (prenom or "Un ambassadeur", apres), "amb_%s" % _id.replace("|", "_"))
    for _p in A.paliers_perdus(avant, apres, _cfg["paliers"]):
        _id = "%s|%s|%s" % (coach_id, empreinte, _p["cle"])
        _r = await _b[COLL_RECOMPENSES].find_one({"_id": _id})   # document complet
        if not _r:
            continue
        _donnee = _r.get("etat") in A.ETATS_DONNES
        await _b[COLL_RECOMPENSES].update_one(
            {"_id": _id}, {"$set": {"a_verifier": True, "sous_le_seuil_depuis": _iso()},
                           "$push": {"historique": {"at": _iso(), "evenement": "SOUS_LE_SEUIL", "boosts": apres,
                                                    "deja_profitee": _donnee}}})
        if _donnee:
            await _notifier_coach(database, coach_id, "Ambassadeur : cas à vérifier",
                                  "%s est repassé sous %d Boosts après une annulation, mais « %s » a déjà été %s."
                                  % (prenom or "Un ambassadeur", _p["seuil"], _p["libelle"],
                                     "remise" if _r.get("etat") == "remise" else "utilisé"),
                                  "amb_verif_%s_%s" % (_id.replace("|", "_"), apres))


async def accorder_boost(database, relais_filleul) -> bool:
    """Le relais du filleul VIENT d'être créé (place confirmée) -> +1 Boost au parrain
    DIRECT. Idempotent (clé `boost:<relais>`). FAIL-OPEN pour l'appelant."""
    if not A.peut_accorder(relais_filleul):
        return False
    _b = _base(database)
    _parent = await _b[COLL_RELAIS].find_one({"id": relais_filleul.get("parent_relais_id")}, {"_id": 0})
    if not _parent or not _parent.get("email_empreinte"):
        return False
    if _parent.get("email_empreinte") == relais_filleul.get("email_empreinte"):
        return False                                     # auto-parrainage : jamais de Boost
    _coach = str(relais_filleul.get("coach_id") or _parent.get("coach_id") or "")
    _emp = _parent["email_empreinte"]
    _avant = await nombre_boosts(_b, _coach, _emp)
    _paiement = relais_filleul.get("paiement") if isinstance(relais_filleul.get("paiement"), dict) else {}
    _doc = {
        "_id": A.cle_boost(relais_filleul["id"]), "coach_id": _coach, "campagne_id": relais_filleul.get("campagne_id"),
        "racine_jeton": relais_filleul.get("racine_jeton"),
        "parrain_relais_id": _parent.get("id"), "parrain_jeton": _parent.get("jeton"),
        "parrain_prenom": _parent.get("inviteur_prenom") or "", "parrain_empreinte": _emp,
        "filleul_relais_id": relais_filleul["id"], "filleul_prenom": relais_filleul.get("inviteur_prenom") or "",
        "filleul_generation": relais_filleul.get("generation"),
        "preuve_nature": relais_filleul.get("preuve_nature"), "preuve_cle": relais_filleul.get("preuve_cle"),
        "reservation_id": relais_filleul.get("reservation_id"),
        "montant": _paiement.get("montant"), "payment_intent": _paiement.get("payment_intent"),
        "statut": A.STATUT_ACCORDE, "accorde_le": _iso(),
        "historique": [{"at": _iso(), "evenement": A.EVENEMENT_ACCORDE, "raison": "place_confirmee"}],
    }
    try:
        await _b[COLL_BOOSTS].insert_one(dict(_doc))
    except Exception as _err:  # noqa: BLE001
        if _doublon(_err):
            return False                                 # déjà accordé (rejeu) : rien de neuf
        raise
    logger.info("%s +1 Boost (%s -> parrain %s)", PREFIXE, _doc["_id"][:20], str(_parent.get("id"))[:8])
    await _appliquer_paliers(_b, _coach, _emp, _doc["parrain_prenom"], _avant, _avant + 1)
    return True


async def revoquer_boost(database, cle, raison) -> bool:
    """Boost accordé -> révoqué (une seule fois), historique conservé."""
    _b = _base(database)
    _r = await _b[COLL_BOOSTS].find_one({"_id": cle})
    if not _r or _r.get("statut") != A.STATUT_ACCORDE:
        return False
    _avant = await nombre_boosts(_b, _r.get("coach_id"), _r.get("parrain_empreinte"))
    _maj = await _b[COLL_BOOSTS].update_one(
        {"_id": cle, "statut": A.STATUT_ACCORDE},
        {"$set": {"statut": A.STATUT_REVOQUE, "revoque_le": _iso(), "raison_revocation": raison},
         "$push": {"historique": {"at": _iso(), "evenement": A.EVENEMENT_REVOQUE, "raison": raison}}})
    if not getattr(_maj, "modified_count", 1):
        return False
    logger.info("%s Boost révoqué %s (%s)", PREFIXE, str(cle)[:20], raison)
    await _appliquer_paliers(_b, _r.get("coach_id"), _r.get("parrain_empreinte"), _r.get("parrain_prenom"), _avant, max(0, _avant - 1))
    return True


async def revoquer_par_paiement(database, payment_intent, complet=True) -> int:
    """`charge.refunded` : les Boosts nés de ce paiement sont révoqués (remboursement
    complet seulement ; un remboursement partiel est tracé à vérifier)."""
    _pi = str(payment_intent or "").strip()
    if not _pi:
        return 0
    _b = _base(database)
    _n = 0
    for _r in await _b[COLL_BOOSTS].find({"payment_intent": _pi}).to_list(5):
        if not complet:
            await _b[COLL_BOOSTS].update_one({"_id": _r["_id"]}, {"$set": {"remboursement_partiel": True},
                                                                  "$push": {"historique": {"at": _iso(), "evenement": "REMBOURSEMENT_PARTIEL", "raison": "a_verifier"}}})
            continue
        _n += int(await revoquer_boost(_b, _r["_id"], "remboursement_stripe"))
    return _n


async def _place_annulee(database, boost) -> bool:
    """La place du filleul a-t-elle été ANNULÉE (réservation supprimée) ?
    Faute de preuve (réclamation absente), on ne révoque pas."""
    _b = _base(database)
    _cle = str(boost.get("preuve_cle") or "")
    try:
        if _cle.startswith("stripe:"):
            _pl = await _b["evenement_places"].find_one({"_id": _cle}, {"_id": 1, "reservation_id": 1})
            if not _pl or not _pl.get("reservation_id"):
                return False
            return not await _b["reservations"].find_one({"id": _pl["reservation_id"]}, {"_id": 1})
        if boost.get("reservation_id"):
            return not await _b["reservations"].find_one({"id": boost["reservation_id"]}, {"_id": 1})
    except Exception:  # noqa: BLE001
        return False
    return False


async def reconcilier(database, filtre) -> int:
    """Les Boosts ACCORDÉS dont la place a été annulée -> révoqués (idempotent)."""
    _b = _base(database)
    _n = 0
    for _r in await _b[COLL_BOOSTS].find(dict(filtre, statut=A.STATUT_ACCORDE), {"_id": 0}).to_list(LISTE_MAX):
        _cle = A.cle_boost(_r.get("filleul_relais_id"))
        if await _place_annulee(_b, _r):
            _n += int(await revoquer_boost(_b, _cle, "reservation_annulee"))
    return _n


# ── Le membre : SON impact ───────────────────────────────────────────────────
async def impact(database, coach_id, empreinte) -> dict:
    """Ce que l'ambassadeur voit de lui-même : Boosts cumulés, amis (prénoms), progression,
    récompenses débloquées, Boosts récents. Rien d'un tiers au-delà du prénom de ses filleuls."""
    _b = _base(database)
    await reconcilier(_b, {"coach_id": coach_id, "parrain_empreinte": empreinte})
    _cfg = await config_du_coach(_b, coach_id)
    _acc = await _b[COLL_BOOSTS].find({"coach_id": coach_id, "parrain_empreinte": empreinte, "statut": A.STATUT_ACCORDE}
                                      ).sort("accorde_le", -1).to_list(LISTE_MAX)
    _rec = await _b[COLL_RECOMPENSES].find({"coach_id": coach_id, "ambassadeur_empreinte": empreinte}, {"_id": 0}).to_list(10)
    return {
        "progression": A.progression(len(_acc), _cfg["paliers"]),
        "paliers": _cfg["paliers"],
        "amis": len(_acc),
        "recents": [{"id": str(x["_id"]), "prenom": x.get("filleul_prenom") or "", "at": x.get("accorde_le")} for x in _acc[:RECENTS_MAX]],
        "recompenses": [{"palier": r.get("palier"), "libelle": r.get("libelle"), "etat": r.get("etat"),
                         "etat_libelle": A.libelle_etat(r.get("palier"), r.get("etat")), "debloque_le": r.get("debloque_le")}
                        for r in sorted(_rec, key=lambda r: int(r.get("seuil") or 0))],
        "message_places": _cfg["message_places"],
    }


async def _porteur_espace(request, code, slug):
    from api.routes import invitation_relais as IR
    return await IR._porteur_espace(request, code, slug)


@router.post("/api/ambassadeur/mon-impact")
async def ambassadeur_mon_impact(request: Request):
    """Espace (session d'espace prouvée par le code e-mail) : MON impact, par coach dont je
    suis participant. 403 sans session. `{code, slug?}` + en-tête `x-espace-token`."""
    from api.routes import invitation_relais as IR
    try:
        _b = await request.json()
    except Exception:  # noqa: BLE001
        _b = {}
    _b = _b if isinstance(_b, dict) else {}
    IR.exiger_debit(request)
    _code = str(_b.get("code") or "").strip().upper()
    _charge = await _porteur_espace(request, _code, str(_b.get("slug") or "")) if re.match(r"^[A-Z0-9-]{4,40}$", _code) else None
    if not _charge:
        raise HTTPException(status_code=403, detail="Ouvre ton espace pour voir ton impact.")
    _emp = IR.empreinte_email(_charge.get("email"))
    if not _emp:
        return {"ambassadeur": False}
    _rels = await db[COLL_RELAIS].find({"email_empreinte": _emp, "type_invitation": {"$in": list(IR.TYPES_RELAIS)}},
                                       {"_id": 0}).sort("created_at", -1).to_list(20)
    if not _rels:
        return {"ambassadeur": False}
    _coach = str(_rels[0].get("coach_id") or "")
    _sortie = await impact(db, _coach, _emp)
    # le lien à partager depuis l'espace : celui de l'événement à venir le plus récent
    _lien = None
    for _r in _rels:
        if str(_r.get("coach_id") or "") != _coach:
            continue
        _camp = await db["referral_campaigns"].find_one({"id": _r.get("campagne_id")}, {"_id": 0})
        if _camp and _camp.get("status") == "active" and IR._a_venir(_camp.get("occurrence")):
            _lien = IR.dto_relais(_r, _camp, IR._front())
            break
    _sortie.update({"ambassadeur": True, "lien": _lien})
    return _sortie


@router.get("/api/ambassadeur/impact/session/{session_id}")
async def ambassadeur_impact_session(session_id: str, request: Request = None):
    """Après un paiement : l'impact de l'ACHETEUR (session Stripe payée, non devinable).
    Compteurs seulement (aucun prénom) ; 404 tant que le webhook n'est pas passé."""
    from api.routes import invitation_relais as IR
    if request is not None:
        IR.exiger_debit(request)
    _s = str(session_id or "").strip()
    if not re.match(r"^cs_[A-Za-z0-9_]{6,200}$", _s):
        raise HTTPException(status_code=404, detail="Introuvable")
    _r = await db[COLL_RELAIS].find_one({"preuve_cle": "stripe:" + _s}, {"_id": 0})
    if not _r or not _r.get("email_empreinte"):
        raise HTTPException(status_code=404, detail="Introuvable")
    _i = await impact(db, str(_r.get("coach_id") or ""), _r["email_empreinte"])
    return {"progression": _i["progression"], "amis": _i["amis"], "recompenses": _i["recompenses"],
            "message_places": _i["message_places"]}


# ── Le coach : SES ambassadeurs ──────────────────────────────────────────────
async def _coach(request):
    from api.routes import referral_routes as R
    return await R._coach_strict(request)


async def _reservation_du_relais(database, rel):
    """La réservation PROPRE d'un participant (pour ses coordonnées), ou None."""
    _b = _base(database)
    _cle = str((rel or {}).get("preuve_cle") or "")
    _rid = (rel or {}).get("reservation_id")
    try:
        if not _rid and _cle.startswith("stripe:"):
            _pl = await _b["evenement_places"].find_one({"_id": _cle}, {"reservation_id": 1})
            _rid = (_pl or {}).get("reservation_id")
        if _rid:
            return await _b["reservations"].find_one({"id": _rid}, {"_id": 0, "userName": 1, "userEmail": 1,
                                                                     "userWhatsapp": 1, "coach_id": 1, "datetime": 1,
                                                                     "offerName": 1, "totalPrice": 1})
    except Exception:  # noqa: BLE001
        return None
    return None


async def _ambassadeurs_du_coach(cle_coach):
    """Agrégat par ambassadeur (empreinte) des relais des invitations de CE coach."""
    _rels = await db[COLL_RELAIS].find({"coach_id": cle_coach}, {"_id": 0}).sort("created_at", 1).to_list(2000)
    _par = {}
    for _r in _rels:
        _e = _r.get("email_empreinte")
        if not _e:
            continue
        _a = _par.setdefault(_e, {"empreinte": _e, "prenom": _r.get("inviteur_prenom") or "", "relais": []})
        _a["relais"].append(_r)
    return _par


async def _partages(jetons):
    if not jetons:
        return 0
    try:
        return await db["invitation_events"].count_documents(
            {"jeton": {"$in": list(jetons)}, "evenement": {"$in": ["partage_whatsapp_declenche", "partage_autre_declenche"]}})
    except Exception:  # noqa: BLE001
        return 0


@router.get("/api/ambassadeur/coach")
async def ambassadeur_coach_liste(request: Request, q: str = ""):
    """Coach (JWT strict) : SES ambassadeurs — prénom, contact (de SA réservation),
    partages déclenchés, amis convertis, Boosts, prochain palier, récompenses, VIP."""
    _c = await _coach(request)
    _cle = _c["cle"]
    await reconcilier(db, {"coach_id": _cle})
    _cfg = await config_du_coach(db, _cle)
    _par = await _ambassadeurs_du_coach(_cle)
    _boosts = await db[COLL_BOOSTS].find({"coach_id": _cle}, {"_id": 0, "parrain_empreinte": 1, "statut": 1}).to_list(5000)
    _rec = await db[COLL_RECOMPENSES].find({"coach_id": _cle}).to_list(2000)
    _q = str(q or "").strip().lower()[:60]
    _sortie = []
    for _e, _a in _par.items():
        _acc = sum(1 for b in _boosts if b.get("parrain_empreinte") == _e and b.get("statut") == A.STATUT_ACCORDE)
        _rev = sum(1 for b in _boosts if b.get("parrain_empreinte") == _e and b.get("statut") == A.STATUT_REVOQUE)
        _resa = await _reservation_du_relais(db, _a["relais"][-1])
        _contact = {}
        # coordonnées de SA réservation : celles d'une réservation de CE coach (le super-admin,
        # clé vide, possède les invitations de la plateforme et leurs réservations).
        if _resa and (_cle == "" or str(_resa.get("coach_id") or "").strip().lower() == _cle):
            _contact = {"nom": _resa.get("userName") or "", "email": _resa.get("userEmail") or "",
                        "whatsapp": _resa.get("userWhatsapp") or ""}
        _ligne = {"id": _e[:24], "prenom": _a["prenom"], "contact": _contact,
                  "partages": await _partages([r.get("jeton") for r in _a["relais"]]),
                  "convertis": _acc, "revoques": _rev,
                  "progression": A.progression(_acc, _cfg["paliers"]),
                  "recompenses": [{"id": r.get("_id"), "palier": r.get("palier"), "libelle": r.get("libelle"),
                                   "etat": r.get("etat"), "etat_libelle": A.libelle_etat(r.get("palier"), r.get("etat")),
                                   "a_verifier": bool(r.get("a_verifier"))}
                                  for r in sorted([x for x in _rec if x.get("ambassadeur_empreinte") == _e],
                                                  key=lambda x: int(x.get("seuil") or 0))]}
        if _q and _q not in " ".join([_ligne["prenom"], _contact.get("nom", ""), _contact.get("email", ""),
                                       _contact.get("whatsapp", "")]).lower():
            continue
        _sortie.append(_ligne)
    _sortie.sort(key=lambda l: (-l["convertis"], l["prenom"].lower()))
    return {"ambassadeurs": _sortie[:LISTE_MAX], "total": len(_sortie), "paliers": _cfg["paliers"]}


async def _empreinte_par_id(cle_coach, ident):
    _id = str(ident or "")[:24]
    if not re.match(r"^[a-f0-9]{8,24}$", _id):
        return None
    for _e in (await _ambassadeurs_du_coach(cle_coach)).keys():
        if _e.startswith(_id):
            return _e
    return None


@router.get("/api/ambassadeur/coach/{ident}")
async def ambassadeur_coach_detail(ident: str, request: Request):
    """Coach : le détail d'UN ambassadeur — ses filleuls (événement, date, statut,
    réservation confirmée, montant, Boost oui/non, annulé/remboursé)."""
    _c = await _coach(request)
    _cle = _c["cle"]
    _e = await _empreinte_par_id(_cle, ident)
    if not _e:
        raise HTTPException(status_code=404, detail="Ambassadeur introuvable")
    await reconcilier(db, {"coach_id": _cle, "parrain_empreinte": _e})
    _filleuls = await db[COLL_RELAIS].find({"coach_id": _cle, "parent_relais_id": {"$in": [
        r.get("id") for r in await db[COLL_RELAIS].find({"coach_id": _cle, "email_empreinte": _e}, {"_id": 0, "id": 1}).to_list(50)]}},
        {"_id": 0}).sort("created_at", 1).to_list(LISTE_MAX)
    _boosts = {b.get("filleul_relais_id"): b for b in await db[COLL_BOOSTS].find({"coach_id": _cle, "parrain_empreinte": _e}, {"_id": 0}).to_list(LISTE_MAX)}
    _camps = {}
    _lignes = []
    for _f in _filleuls:
        _cid = _f.get("campagne_id")
        if _cid not in _camps:
            _camps[_cid] = await db["referral_campaigns"].find_one({"id": _cid}, {"_id": 0, "title": 1, "occurrence": 1}) or {}
        _bo = _boosts.get(_f.get("id")) or {}
        _resa = await _reservation_du_relais(db, _f)
        _lignes.append({"prenom": _f.get("inviteur_prenom") or "", "evenement": _camps[_cid].get("title") or "",
                        "date": _camps[_cid].get("occurrence"), "generation": _f.get("generation"),
                        "reservation_confirmee": bool(_resa), "montant": (_f.get("paiement") or {}).get("montant"),
                        "boost": _bo.get("statut") == A.STATUT_ACCORDE,
                        "annule_ou_rembourse": _bo.get("statut") == A.STATUT_REVOQUE,
                        "raison": _bo.get("raison_revocation"), "auto_invitation": bool(_f.get("auto_invitation"))})
    _rec = await db[COLL_RECOMPENSES].find({"coach_id": _cle, "ambassadeur_empreinte": _e}).to_list(10)
    return {"id": _e[:24], "filleuls": _lignes,
            "recompenses": [{"id": r["_id"], "palier": r.get("palier"), "libelle": r.get("libelle"), "etat": r.get("etat"),
                             "etat_libelle": A.libelle_etat(r.get("palier"), r.get("etat")), "a_verifier": bool(r.get("a_verifier"))}
                            for r in sorted(_rec, key=lambda r: int(r.get("seuil") or 0))]}


@router.post("/api/ambassadeur/coach/recompense")
async def ambassadeur_coach_recompense(request: Request):
    """Coach : `{id, etat}` — Pass Ami utilisé / disponible, Récompense remise / à remettre.
    Jamais recrédité automatiquement ; tout changement est historisé."""
    _c = await _coach(request)
    try:
        _b = await request.json()
    except Exception:  # noqa: BLE001
        _b = {}
    _id = str((_b or {}).get("id") or "")
    _r = await db[COLL_RECOMPENSES].find_one({"_id": _id, "coach_id": _c["cle"]})
    if not _r:
        raise HTTPException(status_code=404, detail="Récompense introuvable")
    _nouvel = A.transition_recompense(_r.get("palier"), _r.get("etat"), str((_b or {}).get("etat") or ""))
    if not _nouvel:
        raise HTTPException(status_code=400, detail="Changement impossible pour cette récompense.")
    await db[COLL_RECOMPENSES].update_one({"_id": _id, "coach_id": _c["cle"]},
                                          {"$set": {"etat": _nouvel, "etat_le": _iso()},
                                           "$push": {"historique": {"at": _iso(), "evenement": "ETAT", "etat": _nouvel,
                                                                    "par": _c.get("email")}}})
    return {"id": _id, "etat": _nouvel, "etat_libelle": A.libelle_etat(_r.get("palier"), _nouvel)}


@router.get("/api/ambassadeur/coach-config")
async def ambassadeur_config_lire(request: Request):
    _c = await _coach(request)
    return await config_du_coach(db, _c["cle"])


@router.put("/api/ambassadeur/coach-config")
async def ambassadeur_config_ecrire(request: Request):
    """Coach : paliers (seuils croissants, libellés), message « 50 PLACES », Pass Ami
    (activités compatibles, expiration). L'avantage filleul reste désactivé (préparé)."""
    _c = await _coach(request)
    try:
        _b = await request.json()
    except Exception:  # noqa: BLE001
        _b = {}
    _actuelle = await db[COLL_PROGRAMMES].find_one({"type": "ambassadeur", "coach_id": _c["cle"]}, {"_id": 0})
    try:
        _cfg = A.config_depuis_saisie(_b, _actuelle)
    except A.ConfigInvalide as _err:
        raise HTTPException(status_code=400, detail=str(_err))
    await db[COLL_PROGRAMMES].update_one(
        {"type": "ambassadeur", "coach_id": _c["cle"]},
        {"$set": dict(_cfg, type="ambassadeur", coach_id=_c["cle"], status="active", updated_at=_iso()),
         "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": _iso()}},
        upsert=True)
    return _cfg
