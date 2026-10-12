# -*- coding: utf-8 -*-
# INV-1 : « Invitation » de la page Campagnes du coach — les routes (`/api/referral/campaigns`).
"""INV-1 — CRUD des invitations du coach (collection `referral_campaigns`).

CE QUE CE N'EST PAS : une campagne d'envoi. Rien ici n'écrit dans `campaigns`,
rien n'a de destinataires, de canal ou de date d'envoi, et aucun statut
« scheduled » n'existe : une invitation ne peut PAS entrer dans le moteur
d'envoi massif. Elle produit un LIEN (page publique + carte OG, servies par
`share_invite_routes.py`).

AUTH — réutilisée, jamais réinventée : `_coach_strict` de `referral_routes`
(JWT Bearer signé ; 401 sans jeton, 403 si pas coach/admin ; `X-User-Email`
JAMAIS lu). `coach_id` = `cle` (e-mail coach en minuscules, "" = espace
plateforme / super-admin — la même clé que les réglages de partage V551).
JAMAIS un `coach_id` venant du corps. Un coach ne voit/modifie QUE ses
invitations : filtre `{coach_id: cle}` partout, 404 sinon (pas 403 : on ne
révèle pas l'existence).

PROPRIÉTÉ DES COURS / OFFRES — la règle du dashboard (`get_coach_filter`) :
super-admin -> tout ; coach -> `coach_id == e-mail`. Un cours / une offre hors
de ce périmètre -> 422.

OFFRE D'ESSAI (type `trial`). Le dépôt n'a pas de drapeau « essai » sur une
offre : un essai EST une offre à 0 CHF (ESSAI-6 `essai6_offres_gratuites`,
preuve P3 de `essai6_verdict` ; ESSAI-1B `_essai1b_exiger_gratuit`). On exige
donc une offre du coach dont le prix est CERTAINEMENT nul
(`offre_gratuite` : `active_price` sinon `price`, et les trois paliers à 0
pour un prix progressif — sentinelle `price = 0` de V223).

DRAPEAU `invitation_event_paid_enabled` (document `feature_flags`, lu
`is True` comme `parrainage_chaine_enabled`) : absent / false / base
illisible = l'activation d'un `event_paid` est REFUSÉE (409). Aucune route
pour le basculer dans ce lot.
"""
import logging
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from api.routes import referral_campaigns_engine as IC
from api.routes import referral_engine as E
from api.routes import referral_routes as R

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/referral/campaigns", tags=["referral-campaigns"])

db = None

PREFIXE = "[INV-1]"
COLL = "referral_campaigns"
FLAG_ID = "feature_flags"
FLAG_EVENT_PAYANT = "invitation_event_paid_enabled"
LISTE_MAX = 50
ESSAIS_JETON = 5
PLAFOND_PAR_COACH = 200      # INV-1 (audit P2) : invitations NON archivées par coach


def init_db(database):
    global db
    db = database


def _db():
    """La base de ce module, sinon celle du parrainage (même process, même base)."""
    return db if db is not None else R.db


async def assurer_index(database) -> None:
    """INV-1 : index posés AU DÉMARRAGE, idempotents (même pratique que V534).
    À appeler depuis le démarrage de server.py (coordinateur)."""
    try:
        await database[COLL].create_index("id", unique=True)
        await database[COLL].create_index("share_token", unique=True)
        await database[COLL].create_index([("coach_id", 1), ("status", 1), ("updated_at", -1)])
        logger.info("%s index referral_campaigns OK", PREFIXE)
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s index referral_campaigns non posés (%s)", PREFIXE, type(_err).__name__)


def _iso():
    return datetime.now(timezone.utc).isoformat()


async def _suivre(doc, evenement) -> None:
    """V607 — journal honnête (invitation_events), génération 0 = le coach. FAIL-OPEN."""
    try:
        from api.routes import invitation_suivi as SV
        await SV.enregistrer(_db(), evenement, type_invitation=doc.get("type"), campagne_id=doc.get("id"),
                             coach_id=doc.get("coach_id") or "", jeton=doc.get("share_token"), generation=0,
                             cle="%s|%s" % (doc.get("id"), evenement))
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s suivi non écrit (%s)", PREFIXE, type(_err).__name__)


async def event_payant_actif() -> bool:
    """`invitation_event_paid_enabled` vaut-il `true` ? Absent / illisible = NON."""
    try:
        _f = await _db()[FLAG_ID].find_one({"id": FLAG_ID}, {"_id": 0}) or {}
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s drapeau %s illisible (%s) — considéré OFF", PREFIXE, FLAG_EVENT_PAYANT,
                       type(_err).__name__)
        return False
    return _f.get(FLAG_EVENT_PAYANT) is True


# ═══════════════════════════════════════════════════════════════════════════
# Identité et propriété
# ═══════════════════════════════════════════════════════════════════════════
async def _coach(request) -> dict:
    """`{email, cle, filtre}` — `_coach_strict` (401/403), + le filtre de propriété
    des cours/offres du dashboard (`get_coach_filter`)."""
    _c = await R._coach_strict(request)
    from api.routes.shared import get_coach_filter
    return {"email": _c["email"], "cle": _c["cle"], "filtre": dict(get_coach_filter(_c["email"]))}


async def _invitation(coach, inv_id) -> dict:
    """L'invitation DU coach, sinon 404 (jamais 403)."""
    _id = str(inv_id or "").strip()
    if not _id or len(_id) > 64:
        raise HTTPException(status_code=404, detail="Invitation introuvable")
    _d = await _db()[COLL].find_one({"id": _id, "coach_id": coach["cle"]}, {"_id": 0})
    if not _d:
        raise HTTPException(status_code=404, detail="Invitation introuvable")
    return _d


async def _objet_du_coach(coach, collection, obj_id):
    if not obj_id:
        return None
    _q = dict(coach["filtre"])
    _q["id"] = obj_id           # égalité stricte : jamais de regex sur une entrée
    return await _db()[collection].find_one(_q, {"_id": 0})


async def _profil_coach(email) -> dict:
    """Prénom + photo du coach : coach_profiles, puis coaches, puis users (égalité
    stricte sur l'e-mail). Lecture seule."""
    _e = E.normaliser_email(email)
    _profil = {"email": _e}
    if not _e:
        return _profil
    for _coll, _proj in (("coach_profiles", {"_id": 0, "display_name": 1, "name": 1, "photo_url": 1, "photoUrl": 1}),
                         ("coaches", {"_id": 0, "name": 1, "photo_url": 1, "photoUrl": 1}),
                         ("users", {"_id": 0, "name": 1, "photo_url": 1, "photoUrl": 1})):
        try:
            _d = await _db()[_coll].find_one({"email": _e}, _proj) or {}
        except Exception:  # noqa: BLE001
            _d = {}
        for _k in ("display_name", "name", "photo_url", "photoUrl"):
            if _d.get(_k) and not _profil.get(_k):
                _profil[_k] = _d.get(_k)
    return _profil


async def _identite(coach) -> dict:
    return IC.identite_coach(await _profil_coach(coach["email"]))


# ═══════════════════════════════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════════════════════════════
def _valider(corps, existant=None) -> dict:
    try:
        return IC.valider_entree(corps, existant)
    except IC.InvitationCampagneInvalide as _err:
        raise HTTPException(status_code=422, detail=str(_err))


async def _ouvrables(offres) -> set:
    """INV-5 — les ids des offres que le lien profond ouvre réellement
    (`inv5_offres_ouvrables_par_lien`, server.py : la même porte que `GET /offers`)."""
    _liste = [o for o in (offres or []) if isinstance(o, dict)]
    if not _liste:
        return set()
    from api.server import inv5_offres_ouvrables_par_lien
    return {o.get("id") for o in await inv5_offres_ouvrables_par_lien(_liste)}


MSG_OFFRE_NON_PUBLIEE = ("Cette offre n'est pas publiée (masquée, archivée, hors saison, complète ou close) : "
                         "le lien de l'invitation ne pourrait pas l'ouvrir. Choisis une offre visible sur la vitrine.")
MSG_COURS_NON_PUBLIC = ("Ce cours est masqué ou archivé : la vitrine ne pourrait pas annoncer cette séance. "
                        "Choisis un cours publié.")
MSG_COURS_NON_RATTACHE = "Ce cours n'est pas rattaché à cette offre : choisis un des cours de l'offre."
MSG_SEANCE_HORS_COURS = ("Cette date ne correspond pas à une séance de ce cours (jour ou heure différents) : "
                         "choisis une date où le cours a lieu.")


def _verifier_lien_ouvrable(champs, cours, offre, ouvrables) -> None:
    """INV-5 — trial / event_free en `active` : ce que la vitrine refuserait
    (lien profond d'App.js, `verdictSeanceInvitation` d'INV-2) est refusé ICI,
    avant que le lien parte. 422 avec un message clair."""
    if not offre or offre.get("id") not in ouvrables:
        raise HTTPException(status_code=422, detail=MSG_OFFRE_NON_PUBLIEE)
    if not champs.get("course_id"):
        return                              # event_free sans séance : l'offre suffit
    if not IC.cours_public(cours):
        raise HTTPException(status_code=422, detail=MSG_COURS_NON_PUBLIC)
    if not IC.cours_rattache(offre, cours.get("id")):
        raise HTTPException(status_code=422, detail=MSG_COURS_NON_RATTACHE)
    if champs.get("occurrence") and not IC.seance_du_cours(cours, champs["occurrence"]):
        raise HTTPException(status_code=422, detail=MSG_SEANCE_HORS_COURS)


MSG_LIEU_REQUIS = "Pour activer, il manque : le lieu. Indique où a lieu l'événement."


def _verifier_billet_evenement(champs, cours, offre) -> None:
    """V607 — ÉVÉNEMENT PAYANT seulement : un BILLET (pas un abonnement, ni une
    offre privée / masquée), un LIEU connu, et — si l'offre a des paliers — la
    date de l'invitation = la date de l'événement de l'offre (les paliers se
    calculent sur elle : sinon la carte et le checkout ne diraient pas le même prix)."""
    _raison = IC.raison_offre_non_billet(offre)
    if _raison:
        raise HTTPException(status_code=422, detail=(
            "Cette offre ne peut pas servir de billet d'événement (%s). "
            "Choisis une offre « Événement » ou « Cours à l'unité » publiée." % _raison))
    _lieu = (champs.get("lieu") or (cours or {}).get("locationName") or (cours or {}).get("location")
             or (offre or {}).get("location") or "")
    if not str(_lieu).strip():
        raise HTTPException(status_code=422, detail=MSG_LIEU_REQUIS)
    if IC.prix_actif(offre) is None:
        # Offre à paliers SANS date d'événement : `compute_active_price` retombe sur
        # `price` (sentinelle 0) — le billet serait vendu 0 CHF. Refusé.
        raise HTTPException(status_code=422, detail=(
            "Cette offre n'a pas de prix encaissable maintenant : renseigne la date de l'événement "
            "(compte à rebours) dans l'offre, ses 3 paliers en dépendent."))
    _cd = str((offre or {}).get("countdown_date") or "").strip()
    if (offre or {}).get("progressive_pricing") is True and _cd and champs.get("occurrence"):
        _occ = str(champs["occurrence"])
        _ct = str((offre or {}).get("countdown_time") or "").strip()
        if _occ[:10] != _cd or (_ct and _occ[11:16] != _ct[:5]):
            raise HTTPException(status_code=422, detail=(
                "La date et l'heure doivent être celles de l'événement de l'offre (%s%s) : "
                "les 3 paliers de prix se calculent sur elles." % (_cd, (" à " + _ct[:5]) if _ct else "")))


async def _controler(coach, champs, publication_dediee=False) -> tuple:
    """Propriété (toujours) + règles d'activation (en `active`). Rend (cours, offre).
    V610h : `publication_dediee` = l'offre DÉDIÉE est contrôlée telle qu'elle sera une
    fois publiée (visible) — toutes les autres règles du billet restent appliquées."""
    _cours = _offre = None
    if champs.get("course_id"):
        _cours = await _objet_du_coach(coach, "courses", champs["course_id"])
        if not _cours:
            raise HTTPException(status_code=422, detail="Ce cours n'appartient pas à votre espace.")
    if champs.get("offer_id"):
        _offre = await _objet_du_coach(coach, "offers", champs["offer_id"])
        if not _offre:
            raise HTTPException(status_code=422, detail="Cette offre n'appartient pas à votre espace.")
    if champs.get("status") != "active":
        return _cours, _offre

    _type = champs.get("type")
    # V607 : plus de 409 « fuseau horaire des paliers » — la cause est corrigée dans
    # api/pricing.py (heure suisse). Le drapeau `invitation_event_paid_enabled` n'est
    # plus lu pour l'activation.
    _manque = IC.champs_manquants(champs)
    if _manque:
        raise HTTPException(status_code=422, detail="Pour activer, il manque : %s." % ", ".join(
            IC.LIBELLES_CHAMPS.get(c, c) for c in _manque))
    if champs.get("occurrence") and E.est_passee(champs["occurrence"], datetime.now(timezone.utc)):
        raise HTTPException(status_code=422, detail="Cette séance est déjà passée : choisis une date à venir.")
    if _type in ("trial", "event_free") and not IC.offre_gratuite(_offre):
        raise HTTPException(status_code=422, detail="Choisis une offre gratuite (0 CHF).")
    if _type == "event_paid" and not IC.offre_payante(_offre):
        raise HTTPException(status_code=422, detail="Choisis une offre payante.")
    if _type == "event_paid":
        _verifier_billet_evenement(champs, _cours, dict(_offre, visible=True) if (publication_dediee and _offre) else _offre)
    if _type in ("trial", "event_free"):
        _verifier_lien_ouvrable(champs, _cours, _offre, await _ouvrables([_offre]))
    if _type == "pass_duo" and (_cours or {}).get("duo_enabled") is not True:
        # INV-1 : sans `duo_enabled`, le Centre Parrainage refuserait le pass (400) :
        # l'invitation serait une impasse pour le membre.
        raise HTTPException(status_code=422, detail="Active d'abord le Pass Duo sur ce cours.")
    return _cours, _offre


async def _dto(doc, cours=None, offre=None, charger=True) -> dict:
    if charger:
        try:
            if cours is None and doc.get("course_id"):
                cours = await _db()["courses"].find_one({"id": doc["course_id"]}, {"_id": 0})
            if offre is None and doc.get("offer_id"):
                offre = await _db()["offers"].find_one({"id": doc["offer_id"]}, {"_id": 0})
        except Exception:  # noqa: BLE001
            pass
    # PAR-1 : `target_url` = la cible RÉELLE du lien (chaîne si les drapeaux sont allumés).
    return IC.dto_coach(doc, cours, offre, R._frontend_url(),
                        chaine=await R.invitation_chaine_campagne_active(_db()))


# ═══════════════════════════════════════════════════════════════════════════
# V610h — PUBLIER un événement créé avec son offre + son cours DÉDIÉS (masqués)
# ═══════════════════════════════════════════════════════════════════════════
MSG_RESERVATIONS_REGULIER = ("Le cours régulier « %s » a déjà %d réservation(s) le %s : l'événement ne peut pas "
                             "le remplacer ce jour-là sans les traiter d'abord. Rien n'a été publié.")
STATUTS_RESA_ANNULEE = ("cancelled", "canceled", "annulee", "annulée", "refunded")


async def _plan_publication_dediee(coach, avant, champs):
    """None si la règle générale s'applique ; sinon le plan de publication (rien n'est
    écrit ici). Conditions CUMULATIVES : brouillon -> actif, événement payant, l'offre et
    le cours de l'invitation forment une paire dédiée DU coach (IC.paire_evenement_dediee),
    et au moins l'un des deux est encore masqué."""
    if avant.get("status") == "active" or champs.get("status") != "active" or champs.get("type") != "event_paid":
        return None
    _offre = await _objet_du_coach(coach, "offers", champs.get("offer_id"))
    _cours = await _objet_du_coach(coach, "courses", champs.get("course_id"))
    if not IC.paire_evenement_dediee(_offre, _cours, coach["email"]):
        return None
    if _offre.get("visible") is not False and _cours.get("visible") is not False:
        return None
    _plan = {"offre": _offre, "cours": _cours, "regulier": None}
    _reg_id, _jour = _cours.get("remplace_cours_id"), str(_cours.get("date") or "")[:10]
    if _reg_id and _jour:
        _reg = await _objet_du_coach(coach, "courses", _reg_id)
        if not _reg or E.normaliser_email(_reg.get("coach_id")) != E.normaliser_email(coach["email"]):
            raise HTTPException(status_code=422, detail="Le cours remplacé par l'événement est introuvable dans votre espace.")
        _q = {"$and": [{"$or": [{"courseId": _reg_id}, {"course_id": _reg_id}]},
                       {"$or": [{"datetime": {"$regex": "^" + _jour}}, {"date": {"$regex": "^" + _jour}}]},
                       {"status": {"$nin": list(STATUTS_RESA_ANNULEE)}}]}
        _n = await _db()["reservations"].count_documents(_q)
        if _n:
            raise HTTPException(status_code=409, detail=MSG_RESERVATIONS_REGULIER % (_reg.get("name") or "", _n, _jour))
        _plan["regulier"] = {"id": _reg_id, "jour": _jour,
                             "deja_exclu": _jour in (_reg.get("dates_annulees") or [])}
    return _plan


async def _appliquer_plan(plan) -> list:
    """Écrit offre + cours visibles et l'exclusion du jour sur le cours régulier.
    Rend les annulations à rejouer en cas d'échec (ordre inverse)."""
    _defaire = []
    _o, _c, _r = plan["offre"], plan["cours"], plan["regulier"]
    if _o.get("visible") is False:
        await _db()["offers"].update_one({"id": _o["id"]}, {"$set": {"visible": True}})
        _defaire.append(("offers", {"id": _o["id"]}, {"$set": {"visible": False}}))
    if _c.get("visible") is False:
        await _db()["courses"].update_one({"id": _c["id"]}, {"$set": {"visible": True}})
        _defaire.append(("courses", {"id": _c["id"]}, {"$set": {"visible": False}}))
    if _r and not _r["deja_exclu"]:
        await _db()["courses"].update_one({"id": _r["id"]}, {"$addToSet": {"dates_annulees": _r["jour"]}})
        _defaire.append(("courses", {"id": _r["id"]}, {"$pull": {"dates_annulees": _r["jour"]}}))
    return _defaire


async def _defaire_plan(defaire) -> None:
    for _coll, _filtre, _maj in reversed(defaire or []):
        try:
            await _db()[_coll].update_one(_filtre, _maj)
        except Exception as _e:  # noqa: BLE001
            logger.error("%s V610h retour arrière incomplet (%s %s) : %s", PREFIXE, _coll, _filtre, type(_e).__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Routes (toutes JWT coach strict)
# ═══════════════════════════════════════════════════════════════════════════
@router.get("")
async def invitations_lister(request: Request):
    """`?limit=&skip=&include_archived=1` -> {items, total} ; 50 max ; updated_at desc."""
    _c = await _coach(request)
    _p = getattr(request, "query_params", None) or {}
    try:
        _limit = max(1, min(LISTE_MAX, int(_p.get("limit") or LISTE_MAX)))
    except (TypeError, ValueError):
        _limit = LISTE_MAX
    try:
        _skip = max(0, int(_p.get("skip") or 0))
    except (TypeError, ValueError):
        _skip = 0
    _q = {"coach_id": _c["cle"]}
    if str(_p.get("include_archived") or "") not in ("1", "true"):
        _q["status"] = {"$ne": "archived"}
    _total = await _db()[COLL].count_documents(_q)
    _rows = await _db()[COLL].find(_q, {"_id": 0}).sort("updated_at", -1) \
        .skip(_skip).limit(_limit).to_list(_limit)
    _cids = list({r.get("course_id") for r in _rows if r.get("course_id")})
    _oids = list({r.get("offer_id") for r in _rows if r.get("offer_id")})
    _cours = {c.get("id"): c for c in (await _db()["courses"].find({"id": {"$in": _cids}}, {"_id": 0})
                                        .to_list(LISTE_MAX) if _cids else [])}
    _offres = {o.get("id"): o for o in (await _db()["offers"].find({"id": {"$in": _oids}}, {"_id": 0})
                                         .to_list(LISTE_MAX) if _oids else [])}
    _items = [await _dto(r, _cours.get(r.get("course_id")), _offres.get(r.get("offer_id")), charger=False)
              for r in _rows]
    return {"items": _items, "total": _total}


@router.get("/options")
async def invitations_options(request: Request):
    """De quoi remplir la modale : les cours et offres DU coach, sans aucune
    donnée personnelle. Cours = règle RV3/E1B (`e1b_cours_encore_servi` : non
    archivé OU rattaché à une offre OU `agenda_abonne`)."""
    _c = await _coach(request)
    _offres = await _db()["offers"].find(dict(_c["filtre"]), {"_id": 0}).to_list(300)
    _offres = [o for o in _offres if o.get("archived") is not True]
    _par_cours = {}
    for _o in _offres:
        for _cid in (_o.get("linked_course_ids") or []):
            if _cid:
                _par_cours.setdefault(_cid, []).append(_o.get("id"))
    try:
        from api.server import e1b_cours_encore_servi as _servi
    except Exception:  # noqa: BLE001
        def _servi(cours, _vendus):
            return cours.get("archived") is not True
    _cours = await _db()["courses"].find(dict(_c["filtre"]), {"_id": 0}).to_list(300)
    _sortie_cours = []
    for _co in _cours:
        if not _servi(_co, _par_cours):
            continue
        try:
            _occ = R._occurrences(_co)
        except Exception:  # noqa: BLE001
            _occ = []
        _sortie_cours.append({
            "id": _co.get("id"), "name": _co.get("name") or "",
            "location": _co.get("locationName") or _co.get("location") or "",
            "time": _co.get("time") or "", "weekday": _co.get("weekday"),
            "date": _co.get("date"), "duo_enabled": _co.get("duo_enabled") is True,
            "occurrences": _occ,
            # INV-5 : la vitrine peut-elle annoncer ce cours ? (visible, non archivé)
            "public": IC.cours_public(_co),
        })
        if len(_sortie_cours) >= LISTE_MAX:
            break
    _sortie_offres = []
    # INV-5 : UNE lecture de la porte publique pour toutes les offres (jamais une par offre).
    _ids_ouvrables = await _ouvrables(_offres[:LISTE_MAX])
    for _o in _offres[:LISTE_MAX]:
        _pal = IC.paliers_offre(_o)
        _sortie_offres.append({
            "id": _o.get("id"), "name": str(_o.get("name") or "")[:120],
            # INV-5 : le lien `/?offre=<id>&reserver=1` l'ouvre-t-il ? + ses cours rattachés.
            "openable": _o.get("id") in _ids_ouvrables,
            "course_ids": IC.cours_lies(_o),
            "price": IC._nombre(_o.get("price")),
            "is_free": IC.offre_gratuite(_o),
            "has_progressive_pricing": _o.get("progressive_pricing") is True,
            "price_early_bird": _pal["early_bird"] if _o.get("progressive_pricing") is True else None,
            "price_standard": _pal["standard"] if _o.get("progressive_pricing") is True else None,
            "price_last_minute": _pal["last_minute"] if _o.get("progressive_pricing") is True else None,
            # V607 — événement payant : billet ? prix encaissé maintenant ? date / lieu de l'événement.
            "billet": IC.offre_billet_evenement(_o),
            "raison_non_billet": IC.raison_offre_non_billet(_o),
            "prix_actif": IC.prix_actif(_o),
            "location": str(_o.get("location") or "").strip()[:160] or None,
            "countdown_date": _o.get("countdown_date") or None,
            "countdown_time": _o.get("countdown_time") or None,
            "offer_type": _o.get("offer_type") or None,
        })
    # INV-1 : la miniature par défaut = l'image de partage du coach (V551), sinon celle
    # de la plateforme — la même que la carte utilise quand l'invitation n'en a pas.
    try:
        _defaut = (await R._reglages_effectifs(_c["cle"])).get("image_url") or None
    except Exception:  # noqa: BLE001
        _defaut = None
    return {"courses": _sortie_cours, "offers": _sortie_offres,
            "event_paid_enabled": True,   # V607 : blocage du fuseau levé
            "inviter_display": await _identite(_c),   # V607 : l'aperçu en direct montre qui invite
            "default_image_url": _defaut or "/logo512.png"}


@router.post("")
async def invitations_creer(request: Request):
    """-> 201 DTO coach. `status` d'entrée ∈ draft | active (défaut draft)."""
    _c = await _coach(request)
    _b = await R._corps(request)
    _champs = _valider(_b, None)
    _cours, _offre = await _controler(_c, _champs)
    # INV-1 (audit P2) : plafond par coach, compté AVANT toute écriture.
    if await _db()[COLL].count_documents({"coach_id": _c["cle"], "status": {"$ne": "archived"}}) \
            >= PLAFOND_PAR_COACH:
        raise HTTPException(status_code=409, detail=(
            "Limite atteinte : %d invitations en cours au maximum. "
            "Archive celles qui ne servent plus pour en créer une nouvelle." % PLAFOND_PAR_COACH))
    _now = _iso()
    _doc = dict(_champs)
    _doc.update({
        "id": str(uuid.uuid4()),
        "coach_id": _c["cle"],
        "version": 1,
        "inviter_display": await _identite(_c),
        "created_at": _now,
        "updated_at": _now,
    })
    for _essai in range(ESSAIS_JETON):
        _doc["share_token"] = secrets.token_urlsafe(24)
        _ecrit = {k: _doc.get(k) for k in IC.CHAMPS_DOCUMENT}    # schéma fermé
        try:
            await _db()[COLL].insert_one(dict(_ecrit))
            break
        except Exception as _err:  # noqa: BLE001
            if R._est_doublon(_err) and _essai < ESSAIS_JETON - 1:
                logger.info("%s collision de jeton, nouvel essai", PREFIXE)
                continue
            logger.error("%s création impossible (%s)", PREFIXE, type(_err).__name__)
            raise HTTPException(status_code=503, detail="Invitation non créée, réessaie dans un instant.")
    logger.info("%s invitation %s créée (%s, %s)", PREFIXE, _doc["id"][:8], _doc["type"], _doc["status"])
    await _suivre(_ecrit, "invitation_creee")
    if _ecrit.get("status") == "active":
        await _suivre(_ecrit, "lien_active")
    return JSONResponse(status_code=201, content=await _dto(_ecrit, _cours, _offre, charger=False))


@router.get("/{inv_id}")
async def invitations_lire(inv_id: str, request: Request):
    _c = await _coach(request)
    return await _dto(await _invitation(_c, inv_id))


@router.put("/{inv_id}")
async def invitations_modifier(inv_id: str, request: Request):
    """Champs partiels (liste blanche). `share_token` JAMAIS modifié ; `version`
    +1 seulement si un champ VISUEL change réellement."""
    _c = await _coach(request)
    _avant = await _invitation(_c, inv_id)
    if _avant.get("status") == "archived":
        raise HTTPException(status_code=409, detail="Invitation archivée : elle n'est plus modifiable.")
    return await _modifier_invitation(_c, _avant, await R._corps(request))


async def _modifier_invitation(_c, _avant, _b):
    """Le cœur du PUT (V610h : partagé avec « Réactiver »)."""
    # V607 : le TYPE se change tant que l'invitation est un BROUILLON (rien n'a été
    # partagé : aucun lien public n'existe). Activée = type figé (409).
    if isinstance(_b, dict) and "type" in _b and _b.get("type") != _avant.get("type") \
            and _avant.get("status") != "draft":
        raise HTTPException(status_code=409, detail="Le type ne change plus une fois le lien activé.")
    _champs = _valider(_b, _avant)
    # V610h : brouillon -> actif d'un événement à offre + cours DÉDIÉS encore masqués :
    # TOUT est validé d'abord (billet contrôlé tel que publié), puis publié ensemble ;
    # le moindre échec défait ce qui a été écrit (jamais un état à moitié publié).
    _plan = await _plan_publication_dediee(_c, _avant, _champs)
    _cours, _offre = await _controler(_c, _champs, publication_dediee=_plan is not None)
    _now = _iso()
    _set = dict(_champs, inviter_display=await _identite(_c), updated_at=_now)
    _maj = {"$set": _set}
    if IC.version_incrementee(_avant, _champs):
        _maj["$inc"] = {"version": 1}
    _defaire = []
    try:
        if _plan:
            _defaire = await _appliquer_plan(_plan)
        # INV-1 (audit P2) : `status != archived` DANS le filtre — un archivage survenu entre
        # la lecture et l'écriture n'est jamais annulé par ce PUT (course PUT / archive).
        _ecrit = await _db()[COLL].update_one(
            {"id": _avant["id"], "coach_id": _c["cle"], "share_token": _avant.get("share_token"),
             "status": {"$ne": "archived"}}, _maj)
        if not getattr(_ecrit, "matched_count", 1):
            raise HTTPException(status_code=409, detail="Invitation archivée entre-temps : elle n'est plus modifiable.")
    except Exception:
        await _defaire_plan(_defaire)
        raise
    if _plan:
        logger.info("%s V610h événement publié : offre %s, cours %s, jour exclu %s", PREFIXE,
                    _plan["offre"]["id"], _plan["cours"]["id"], (_plan["regulier"] or {}).get("jour"))
        _offre = dict(_offre or {}, visible=True)
        _cours = dict(_cours or {}, visible=True)
    _apres = await _invitation(_c, _avant["id"])
    if _avant.get("status") != "active" and _apres.get("status") == "active":
        await _suivre(_apres, "lien_active")
    return await _dto(_apres, _cours, _offre, charger=False)


async def _paire_dediee_de(coach, doc):
    """(offre, cours) si l'invitation porte la paire DÉDIÉE du coach, sinon (None, None)."""
    _o = await _objet_du_coach(coach, "offers", doc.get("offer_id"))
    _k = await _objet_du_coach(coach, "courses", doc.get("course_id"))
    return (_o, _k) if IC.paire_evenement_dediee(_o, _k, coach["email"]) else (None, None)


async def _hors_ligne(coach, doc, statut) -> dict:
    """V610h — met l'invitation hors ligne (`hidden` ou `archived`) et, si elle porte
    la paire DÉDIÉE, masque son offre et son cours (plus de vente, plus de place offerte).
    Rien n'est supprimé : réservations, paiements, liens personnels, chaîne, médias,
    tarifs restent. Le cours régulier remplacé N'EST PAS touché (son jour reste exclu :
    jamais deux séances au même horaire, jamais de réactivation implicite).
    Échec de l'écriture de l'invitation -> offre et cours remis comme avant."""
    _o, _k = await _paire_dediee_de(coach, doc)
    _defaire = []
    try:
        for _coll, _obj in (("offers", _o), ("courses", _k)):
            if _obj and _obj.get("visible") is not False:
                await _db()[_coll].update_one({"id": _obj["id"]}, {"$set": {"visible": False}})
                _defaire.append((_coll, {"id": _obj["id"]}, {"$set": {"visible": _obj.get("visible", True)}}))
        _ecrit = await _db()[COLL].update_one(
            {"id": doc["id"], "coach_id": coach["cle"], "status": doc.get("status")},
            {"$set": {"status": statut, "updated_at": _iso(), ("masquee_le" if statut == "hidden" else "archivee_le"): _iso()}})
        if not getattr(_ecrit, "matched_count", 1):
            raise HTTPException(status_code=409, detail="L'invitation a changé entre-temps : recharge la page.")
    except Exception:
        await _defaire_plan(_defaire)
        raise
    return await _invitation(coach, doc["id"])


@router.post("/{inv_id}/masquer")
async def invitations_masquer(inv_id: str, request: Request):
    """V610h — ACTIVE -> MASQUÉE (hors ligne, réactivable, aucune suppression)."""
    _c = await _coach(request)
    _d = await _invitation(_c, inv_id)
    if _d.get("status") == "hidden":
        return await _dto(_d)
    if _d.get("status") != "active":
        raise HTTPException(status_code=409, detail="Seule une invitation publiée peut être masquée.")
    return await _dto(await _hors_ligne(_c, _d, "hidden"))


@router.post("/{inv_id}/reactiver")
async def invitations_reactiver(inv_id: str, request: Request):
    """V610h — MASQUÉE -> ACTIVE : exactement la publication (mêmes contrôles, mêmes
    ids, même jeton, aucun doublon). Événement passé : refus, jamais de réactivation aveugle."""
    _c = await _coach(request)
    _d = await _invitation(_c, inv_id)
    if _d.get("status") == "active":
        return await _dto(_d)
    if _d.get("status") != "hidden":
        raise HTTPException(status_code=409, detail="Seule une invitation masquée peut être réactivée.")
    if _d.get("occurrence") and E.est_passee(_d["occurrence"], datetime.now(timezone.utc)):
        raise HTTPException(status_code=409, detail=MSG_EVENEMENT_PASSE)
    return await _modifier_invitation(_c, _d, {"status": "active"})


MSG_EVENEMENT_PASSE = ("Cet événement est déjà passé : il ne peut pas être réactivé tel quel. "
                       "Modifie sa date ou crée une nouvelle invitation.")


# ═══════════════════════════════════════════════════════════════════════════
# V610k — DUPLIQUER / SUPPRIMER (logique, réversible) / RESTAURER
# ═══════════════════════════════════════════════════════════════════════════
SUFFIXE_COPIE = " — Copie"
# Une offre / un cours DÉDIÉS sont recopiés SANS ce qui appartient à l'événement d'origine.
CHAMPS_OFFRE_NON_COPIES = ("_id", "id", "created_at", "updated_at", "visible", "linked_course_ids", IC.MARQUE_EVENEMENT,
                           "sold", "sold_count", "ventes", "participants_count", "stripe_product_id", "stripe_price_id")
CHAMPS_COURS_NON_COPIES = ("_id", "id", "created_at", "updated_at", "visible", "dates_annulees", IC.MARQUE_EVENEMENT,
                           "participants", "inscrits", "reservations_count")


def titre_copie(titre, maxi=IC.TITRE_MAX) -> str:
    _t = str(titre or "").strip() or "Invitation"
    if _t.endswith(SUFFIXE_COPIE.strip()):
        return _t[:maxi]
    return (_t[:max(1, maxi - len(SUFFIXE_COPIE))].rstrip() + SUFFIXE_COPIE)[:maxi]


async def _copier_paire_dediee(coach, offre, cours, titre):
    """Événement payant à paire DÉDIÉE : une NOUVELLE paire, masquée (brouillon), avec sa
    propre marque — jamais l'offre / le cours réels de l'événement d'origine (ni leurs ventes,
    ni leurs jours exclus). Elle ne devient vendable qu'à la publication (V610h)."""
    _marque = "copie-%s" % uuid.uuid4().hex[:12]
    _now = _iso()
    _c = {k: v for k, v in cours.items() if k not in CHAMPS_COURS_NON_COPIES}
    _c.update({"id": str(uuid.uuid4()), "visible": False, "archived": False, IC.MARQUE_EVENEMENT: _marque,
               "name": titre, "created_at": _now, "copie_de": cours.get("id")})
    _o = {k: v for k, v in offre.items() if k not in CHAMPS_OFFRE_NON_COPIES}
    _o.update({"id": str(uuid.uuid4()), "visible": False, "archived": False, IC.MARQUE_EVENEMENT: _marque,
               "linked_course_ids": [_c["id"]], "name": titre, "created_at": _now, "copie_de": offre.get("id")})
    await _db()["courses"].insert_one(dict(_c))
    try:
        await _db()["offers"].insert_one(dict(_o))
    except Exception:
        await _db()["courses"].delete_one({"id": _c["id"], IC.MARQUE_EVENEMENT: _marque})   # rien d'orphelin
        raise
    return _o, _c


@router.post("/{inv_id}/dupliquer")
async def invitations_dupliquer(inv_id: str, request: Request):
    """V610k — une NOUVELLE invitation en BROUILLON : nouvel id, nouveau jeton, version 1.
    Copiés : type, textes, médias (mêmes fichiers, simplement référencés), lieu, date.
    JAMAIS copiés : liens personnels, réservations, paiements, statistiques, chaîne, statut."""
    _c = await _coach(request)
    _src = await _invitation(_c, inv_id)
    if await _db()[COLL].count_documents({"coach_id": _c["cle"], "status": {"$ne": "archived"}}) >= PLAFOND_PAR_COACH:
        raise HTTPException(status_code=409, detail=(
            "Limite atteinte : %d invitations en cours au maximum. Supprime celles qui ne servent plus." % PLAFOND_PAR_COACH))
    _titre = titre_copie(_src.get("title"))
    _doc = {k: _src.get(k) for k in IC.CHAMPS_DOCUMENT
            if k not in ("id", "share_token", "version", "status", "created_at", "updated_at", "inviter_display")}
    _doc["title"] = _titre
    _paire = (None, None)
    if _src.get("type") == "event_paid":
        _o, _k = await _paire_dediee_de(_c, _src)
        if _o and _k:
            _paire = await _copier_paire_dediee(_c, _o, _k, _titre)
            _doc["offer_id"], _doc["course_id"] = _paire[0]["id"], _paire[1]["id"]
    _now = _iso()
    _doc.update({"id": str(uuid.uuid4()), "coach_id": _c["cle"], "status": "draft", "version": 1,
                 "inviter_display": await _identite(_c), "created_at": _now, "updated_at": _now})
    for _essai in range(ESSAIS_JETON):
        _doc["share_token"] = secrets.token_urlsafe(24)
        _ecrit = {k: _doc.get(k) for k in IC.CHAMPS_DOCUMENT}    # schéma fermé
        _ecrit["copie_de"] = _src["id"]
        try:
            await _db()[COLL].insert_one(dict(_ecrit))
            break
        except Exception as _err:  # noqa: BLE001
            if R._est_doublon(_err) and _essai < ESSAIS_JETON - 1:
                continue
            if _paire[0]:
                await _db()["offers"].delete_one({"id": _paire[0]["id"], "copie_de": {"$exists": True}, "visible": False})
                await _db()["courses"].delete_one({"id": _paire[1]["id"], "copie_de": {"$exists": True}, "visible": False})
            logger.error("%s duplication impossible (%s)", PREFIXE, type(_err).__name__)
            raise HTTPException(status_code=503, detail="Copie non créée, réessaie dans un instant.")
    logger.info("%s invitation %s dupliquée -> %s (%s, paire dédiée copiée : %s)", PREFIXE, _src["id"][:8],
                _ecrit["id"][:8], _ecrit.get("type"), bool(_paire[0]))
    await _suivre(_ecrit, "invitation_creee")
    return JSONResponse(status_code=201, content=await _dto(_ecrit))


async def _donnees_liees(doc) -> dict:
    """Ce qui rattache une invitation à de l'historique RÉEL (rien n'est modifié)."""
    _id = doc.get("id")
    _n = {"liens_personnels": 0, "statistiques": 0, "reservations": 0}
    try:
        _n["liens_personnels"] = await _db()["invitation_relais"].count_documents({"campagne_id": _id})
        _n["statistiques"] = await _db()["invitation_events"].count_documents(
            {"campagne_id": _id, "evenement": {"$nin": ["invitation_creee", "lien_active"]}})   # gestes du coach exclus
        if doc.get("course_id"):
            _n["reservations"] = await _db()["reservations"].count_documents(
                {"$or": [{"courseId": doc["course_id"]}, {"course_id": doc["course_id"]}],
                 "source": {"$in": ["paid_event_auto", "member_free_event"]}}) if doc.get("type") == "event_paid" else 0
    except Exception as _e:  # noqa: BLE001
        logger.warning("%s données liées illisibles (%s)", PREFIXE, type(_e).__name__)
    _n["a_des_donnees"] = any(_n[k] for k in ("liens_personnels", "statistiques", "reservations")) or doc.get("status") != "draft"
    return _n


@router.get("/{inv_id}/donnees-liees")
async def invitations_donnees_liees(inv_id: str, request: Request):
    _c = await _coach(request)
    return await _donnees_liees(await _invitation(_c, inv_id))


@router.post("/{inv_id}/supprimer")
async def invitations_supprimer(inv_id: str, request: Request):
    """V610k — SUPPRESSION LOGIQUE, toujours (jamais d'effacement) : l'invitation est
    archivée (hors de la liste, lien public « plus disponible », offre / cours dédiés
    masqués) et marquée `supprimee_le` ; réservations, paiements, liens personnels, chaîne
    et statistiques restent intacts. Restaurable (en brouillon) depuis la corbeille."""
    _c = await _coach(request)
    _d = await _invitation(_c, inv_id)
    _donnees = await _donnees_liees(_d)
    if _d.get("status") != "archived":
        _d = await _hors_ligne(_c, _d, "archived")
    await _db()[COLL].update_one({"id": _d["id"], "coach_id": _c["cle"]}, {"$set": {"supprimee_le": _iso()}})
    logger.info("%s invitation %s supprimée (logique) — données conservées : %s", PREFIXE, _d["id"][:8], _donnees)
    return {"supprimee": True, "definitive": False, "donnees_conservees": _donnees}


@router.post("/{inv_id}/restaurer")
async def invitations_restaurer(inv_id: str, request: Request):
    """V610k — corbeille -> BROUILLON (jamais republiée automatiquement)."""
    _c = await _coach(request)
    _d = await _invitation(_c, inv_id)
    if _d.get("status") != "archived":
        return await _dto(_d)
    if await _db()[COLL].count_documents({"coach_id": _c["cle"], "status": {"$ne": "archived"}}) >= PLAFOND_PAR_COACH:
        raise HTTPException(status_code=409, detail="Limite atteinte : supprime d'abord une invitation en cours.")
    await _db()[COLL].update_one({"id": _d["id"], "coach_id": _c["cle"], "status": "archived"},
                                 {"$set": {"status": "draft", "updated_at": _iso()}, "$unset": {"supprimee_le": ""}})
    return await _dto(await _invitation(_c, _d["id"]))


@router.post("/{inv_id}/archive")
async def invitations_archiver(inv_id: str, request: Request):
    _c = await _coach(request)
    _d = await _invitation(_c, inv_id)
    if _d.get("status") != "archived":
        # V610h : une invitation archivée ne laisse pas son offre / son cours DÉDIÉS en vente.
        _d = await _hors_ligne(_c, _d, "archived")
    return await _dto(_d)
