# -*- coding: utf-8 -*-
# V610e : L'ÉDITEUR COMPLET D'INVITATION DU COACH (événement, tarifs, médias).
"""V610e — ce que le coach modifie SANS Claude Code, depuis son tableau de bord.

Les textes et médias de l'invitation passent par la route EXISTANTE
`PUT /api/referral/campaigns/{id}` (liste blanche, version, share_token intact).
Ce module ajoute ce qui ne vit PAS dans `referral_campaigns` :

* L'ÉVÉNEMENT — date, heure, lieu : l'offre (compte à rebours), le cours de
  l'événement (s'il lui est DÉDIÉ : date fixe, rattaché à cette seule offre) et
  l'occurrence / le lieu de l'invitation, écrits ensemble.
* LES TARIFS — prévente / standard / dernière minute et les DEUX bascules
  (heure suisse) : écrits sur l'OFFRE, la seule source de vérité des prix. Le
  serveur recalcule le montant au moment de chaque paiement ; rien de passé
  (transaction, réservation, reçu) n'est jamais réécrit.
* LA RÈGLE « OFFERT AUX MEMBRES 8 MOIS » — un interrupteur qui la suspend ou la
  rétablit ; les offres d'abonnement concernées ne sont jamais exposées.
* LES MÉDIAS DU COACH — ses fichiers importés (+ ses vidéos de la bibliothèque) et
  l'enregistrement d'un nouvel import avec empreinte SHA-256 calculée PAR LE
  SERVEUR : un fichier identique déjà importé est réutilisé (pas de doublon).

AUCUNE CAPACITÉ n'est créée ou modifiée ici. AUCUN participant n'est contacté.
Propriété : la même porte que les invitations (JWT coach strict, 404 neutre).
"""
import hashlib
import logging
import os
import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)
PREFIXE = "[V610e-EDITION]"
router = APIRouter(tags=["invitation-edition"])
db = None

RE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_HEURE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
RE_LOCAL = re.compile(r"^\d{4}-\d{2}-\d{2}T([01]\d|2[0-3]):[0-5]\d$")
RE_FICHIER = re.compile(r"^/api/files/([A-Za-z0-9_-]{1,64})/([A-Za-z0-9._-]{1,200})$")
PRIX_MAX = 10000.0
LIEU_MAX = 160
TYPES_EVENEMENT = ("event_free", "event_paid")
MEDIAS_MAX = 50
MSG_CONFIRMATION = ("Des participants ont déjà réservé cet événement. Cette modification affectera "
                    "les prochaines réservations. Aucun participant ne sera prévenu automatiquement. Continuer ?")


def init_db(database):
    global db
    db = database


def _db():
    if db is not None:
        return db
    from api.routes import referral_campaigns_routes as RC
    return RC._db()


try:
    from zoneinfo import ZoneInfo
    _ZURICH = ZoneInfo("Europe/Zurich")
except Exception:  # noqa: BLE001
    _ZURICH = timezone.utc


def _local(dt_utc) -> str:
    """UTC -> « AAAA-MM-JJTHH:MM » à l'heure de Zurich."""
    return dt_utc.astimezone(_ZURICH).strftime("%Y-%m-%dT%H:%M") if dt_utc else ""


def _vers_utc(local) -> datetime:
    return datetime.strptime(local, "%Y-%m-%dT%H:%M").replace(tzinfo=_ZURICH).astimezone(timezone.utc)


def _prix(valeur, champ):
    try:
        _p = round(float(valeur), 2)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="%s : montant en CHF attendu." % champ)
    if not (0 < _p <= PRIX_MAX):
        raise HTTPException(status_code=422, detail="%s : montant positif attendu (CHF)." % champ)
    return _p


async def _contexte(request, inv_id):
    """(coach, invitation, offre|None, cours|None) — tout DU coach, sinon 404."""
    from api.routes import referral_campaigns_routes as RC
    _c = await RC._coach(request)
    _camp = await RC._invitation(_c, inv_id)
    _offre = await RC._objet_du_coach(_c, "offers", _camp.get("offer_id")) if _camp.get("offer_id") else None
    _cours = await RC._objet_du_coach(_c, "courses", _camp.get("course_id")) if _camp.get("course_id") else None
    return _c, _camp, _offre, _cours


async def _cours_dedie(cours, offre) -> bool:
    """Le cours n'appartient QU'À cet événement : date fixe, rattaché à cette seule offre.
    Sinon (cours récurrent / partagé), sa date ne se modifie pas depuis une invitation."""
    if not cours or not offre or not RE_DATE.match(str(cours.get("date") or "")[:10]):
        return False
    _n = await _db()["offers"].count_documents({"linked_course_ids": cours.get("id")})
    return _n <= 1 and cours.get("id") in (offre.get("linked_course_ids") or [])


async def _participants(offre) -> dict:
    if not offre:
        return {"reservations": 0, "paiements": 0}
    _r = await _db()["reservations"].count_documents({"offerId": offre.get("id")})
    _p = await _db()["payment_transactions"].count_documents(
        {"metadata.offer_id": offre.get("id"), "payment_status": "paid"})
    return {"reservations": int(_r), "paiements": int(_p)}


def _tarifs(offre):
    """La grille telle que le coach la lit (heure suisse), ou None (pas de paliers)."""
    from api.pricing import tier_boundaries
    from api.routes import referral_campaigns_engine as IC
    if not offre or offre.get("progressive_pricing") is not True:
        return None
    _b = tier_boundaries(offre) or {}
    _pa = IC.prix_actif(offre)
    return {
        "prevente": offre.get("price_early_bird"), "standard": offre.get("price_standard"),
        "derniere_minute": offre.get("price_last_minute"),
        "libelles": {"prevente": offre.get("label_early_bird") or "Prévente",
                     "standard": offre.get("label_standard") or "Standard",
                     "derniere_minute": offre.get("label_last_minute") or "Dernière minute"},
        "fin_prevente": _local(_b.get("early_bird_end")), "fin_standard": _local(_b.get("standard_end")),
        "debut_evenement": _local(_b.get("reference")),
        "prix_actif": (_pa or {}).get("prix"), "palier_actif": (_pa or {}).get("palier"),
        "libelle_actif": (_pa or {}).get("libelle"),
    }


async def _edition(_c, camp, offre, cours) -> dict:
    from api.routes import referral_campaigns_routes as RC
    from api.routes import evenement_special as EVT
    _evt = None
    if camp.get("type") in TYPES_EVENEMENT:
        _occ = str(camp.get("occurrence") or "")
        _evt = {
            "date": (str((cours or {}).get("date") or "")[:10] if await _cours_dedie(cours, offre) else "") or _occ[:10],
            "heure": str((cours or {}).get("time") or "")[:5] if await _cours_dedie(cours, offre) else _occ[11:16],
            "lieu": camp.get("lieu") or (cours or {}).get("locationName") or (cours or {}).get("location")
            or (offre or {}).get("location") or "",
            "date_modifiable": await _cours_dedie(cours, offre),
            "tarifs": _tarifs(offre) if camp.get("type") == "event_paid" else None,
            "membres": ({"configuree": True, "actif": bool(EVT.offres_gratuite(offre)),
                         "libelle": "Offert aux membres 8 mois actifs"}
                        if EVT.regle_membres_configuree(offre) else None),
            "offre_nom": (offre or {}).get("name"),
            "description_offre": ((offre or {}).get("description") or "")[:1500],
            "participants": await _participants(offre),
            "reservation_auto": EVT.reservation_auto(offre),
        }
    return {"invitation": await RC._dto(camp, cours, offre, charger=False), "evenement": _evt}


@router.get("/api/referral/campaigns-edition/{inv_id}")
async def edition_lire(inv_id: str, request: Request):
    """Tout ce que l'éditeur affiche : l'invitation (DTO coach) + l'événement (date,
    heure, lieu, grille tarifaire en heure suisse, règle membres, participants)."""
    _c, _camp, _offre, _cours = await _contexte(request, inv_id)
    return await _edition(_c, _camp, _offre, _cours)


@router.put("/api/referral/campaigns-edition/{inv_id}/evenement")
async def edition_evenement(inv_id: str, request: Request):
    """Date / heure / lieu / tarifs / règle membres. `simuler: true` : valide et rend
    l'aperçu (tarif actif) SANS rien écrire. Modification sensible avec des
    participants déjà inscrits -> 409 `confirmation_requise` tant que `confirmer` n'est
    pas vrai. Rien de passé n'est réécrit ; personne n'est contacté."""
    from api.routes import referral_campaigns_engine as IC
    from api.routes import referral_campaigns_routes as RC
    _c, _camp, _offre, _cours = await _contexte(request, inv_id)
    if _camp.get("status") == "archived":
        raise HTTPException(status_code=409, detail="Invitation archivée : elle n'est plus modifiable.")
    if _camp.get("type") not in TYPES_EVENEMENT or not _offre:
        raise HTTPException(status_code=409, detail="Cette invitation n'est pas un événement avec une offre.")
    try:
        _b = await request.json()
    except Exception:  # noqa: BLE001
        _b = {}
    _b = _b if isinstance(_b, dict) else {}
    _dedie = await _cours_dedie(_cours, _offre)
    _o = dict(_offre)            # l'offre CANDIDATE (rien n'est écrit avant validation complète)
    _set_offre, _set_cours, _set_camp = {}, {}, {}
    _sensible = False

    # ── Date / heure ────────────────────────────────────────────────────────
    _date = str(_b.get("date") or "").strip() if "date" in _b else None
    _heure = str(_b.get("heure") or "").strip() if "heure" in _b else None
    if _date is not None or _heure is not None:
        _d = _date if _date is not None else str(_o.get("countdown_date") or "")
        _h = _heure if _heure is not None else str(_o.get("countdown_time") or "")[:5]
        if not RE_DATE.match(_d) or not RE_HEURE.match(_h):
            raise HTTPException(status_code=422, detail="Date (AAAA-MM-JJ) et heure (HH:MM) de l'événement attendues.")
        if (_d, _h) != (str(_offre.get("countdown_date") or ""), str(_offre.get("countdown_time") or "")[:5]):
            if not _dedie:
                raise HTTPException(status_code=409, detail=(
                    "La date de ce cours ne se change pas ici : il n'est pas propre à cet événement."))
            if _vers_utc("%sT%s" % (_d, _h)) <= datetime.now(timezone.utc):
                raise HTTPException(status_code=422, detail="La nouvelle date doit être dans le futur.")
            _sensible = True
            _o.update(countdown_enabled=True, countdown_date=_d, countdown_time=_h)
            _set_offre.update(countdown_enabled=True, countdown_date=_d, countdown_time=_h)
            _set_cours.update(date=_d, time=_h)
            _set_camp["occurrence"] = IC.normaliser_occurrence("%sT%s" % (_d, _h))

    # ── Lieu ────────────────────────────────────────────────────────────────
    if "lieu" in _b:
        _l = " ".join(str(_b.get("lieu") or "").replace("<", "").replace(">", "").split())[:LIEU_MAX]
        if not _l:
            raise HTTPException(status_code=422, detail="Le lieu de l'événement est obligatoire.")
        _actuel = _camp.get("lieu") or (_cours or {}).get("locationName") or (_cours or {}).get("location") or ""
        if _l != _actuel:
            _sensible = True
            _set_camp["lieu"] = _l
            if _dedie:
                _set_cours.update(location=_l, locationName=_l)

    # ── Tarifs (événement payant à paliers) ─────────────────────────────────
    _cles_prix = ("prevente", "standard", "derniere_minute", "fin_prevente", "fin_standard")
    if any(k in _b for k in _cles_prix):
        if _camp.get("type") != "event_paid" or _o.get("progressive_pricing") is not True:
            raise HTTPException(status_code=409, detail="Cet événement n'a pas de tarifs à paliers.")
        for _k, _champ, _lib in (("prevente", "price_early_bird", "Prévente"), ("standard", "price_standard", "Standard"),
                                 ("derniere_minute", "price_last_minute", "Dernière minute")):
            if _k in _b:
                _p = _prix(_b.get(_k), _lib)
                if _p != _o.get(_champ):
                    _o[_champ] = _p
                    _set_offre[_champ] = _p
                    _sensible = True
        for _k, _champ in (("fin_prevente", "palier_fin_prevente"), ("fin_standard", "palier_fin_standard")):
            if _k in _b:
                _v = str(_b.get(_k) or "").strip()[:16]
                if not RE_LOCAL.match(_v):
                    raise HTTPException(status_code=422, detail="Bascule : date et heure (AAAA-MM-JJ HH:MM) attendues.")
                if _v != str(_o.get(_champ) or ""):
                    _o[_champ] = _v
                    _set_offre[_champ] = _v
                    _sensible = True
        if "price_early_bird" in _set_offre:
            _o["price"] = _set_offre["price"] = _set_offre["price_early_bird"]   # prix de base = prévente
    if _o.get("progressive_pricing") is True and _camp.get("type") == "event_paid":
        from api.pricing import tier_boundaries, _bascule_locale
        # Les bascules SAISIES sont jugées telles quelles (le calcul des prix, lui, ignore
        # une bascule incohérente — ici on la REFUSE au lieu de l'enregistrer en silence).
        _sans = {k: v for k, v in _o.items() if k not in ("palier_fin_prevente", "palier_fin_standard")}
        _defaut = tier_boundaries(_sans)
        if not _defaut:
            raise HTTPException(status_code=422, detail="Date de l'événement manquante : les paliers en dépendent.")
        _bornes = {"reference": _defaut["reference"],
                   "early_bird_end": _bascule_locale(_o.get("palier_fin_prevente")) or _defaut["early_bird_end"],
                   "standard_end": _bascule_locale(_o.get("palier_fin_standard")) or _defaut["standard_end"]}
        if not (_bornes["early_bird_end"] <= _bornes["standard_end"] <= _bornes["reference"]):
            raise HTTPException(status_code=422, detail=(
                "Chronologie des tarifs incohérente : la prévente finit avant le standard, "
                "qui finit au plus tard au début de l'événement."))
        if _bornes["early_bird_end"] == _bornes["standard_end"] == _bornes["reference"]:
            raise HTTPException(status_code=422, detail="Aucune période de vente : vérifie les bascules.")
        for _champ in ("price_early_bird", "price_standard", "price_last_minute"):
            if not isinstance(_o.get(_champ), (int, float)) or _o.get(_champ) <= 0:
                raise HTTPException(status_code=422, detail="Les trois tarifs doivent être des montants positifs.")

    # ── Règle « offert aux membres 8 mois » (interrupteur protégé) ──────────
    if "gratuit_membres_actif" in _b:
        from api.routes import evenement_special as EVT
        if not EVT.regle_membres_configuree(_offre):
            raise HTTPException(status_code=409, detail="Aucune règle « membres » n'est configurée pour cet événement.")
        _actif = bool(_b.get("gratuit_membres_actif"))
        if _actif != bool(EVT.offres_gratuite(_offre)):
            _o["gratuit_membres_actif"] = _actif
            _set_offre["gratuit_membres_actif"] = _actif
            _sensible = True          # des membres comptaient peut-être sur leur place offerte

    if _b.get("simuler") is True:
        _pa = IC.prix_actif(_o) if _camp.get("type") == "event_paid" else None
        return {"simulation": True, "tarifs": _tarifs(_o) if _camp.get("type") == "event_paid" else None,
                "prix_actif": (_pa or {}).get("prix"), "palier_actif": (_pa or {}).get("palier")}

    if not (_set_offre or _set_cours or _set_camp):
        return dict(await _edition(_c, _camp, _offre, _cours), inchange=True)
    _part = await _participants(_offre)
    if _sensible and (_part["reservations"] or _part["paiements"]) and _b.get("confirmer") is not True:
        raise HTTPException(status_code=409, detail={"code": "confirmation_requise", "message": MSG_CONFIRMATION,
                                                     "participants": _part})

    _maintenant = datetime.now(timezone.utc).isoformat()
    if _set_offre:
        _set_offre["updated_at"] = _maintenant
        await _db()["offers"].update_one({"id": _offre["id"]}, {"$set": _set_offre})
    if _set_cours and _cours:
        await _db()["courses"].update_one({"id": _cours["id"]}, {"$set": _set_cours})
    # La carte, l'aperçu WhatsApp et la page lisent le prix / la date : version +1
    # (jamais un nouveau share_token — les liens déjà partagés restent valides).
    _set_camp["updated_at"] = _maintenant
    await _db()[RC.COLL].update_one({"id": _camp["id"], "coach_id": _c["cle"], "status": {"$ne": "archived"}},
                                    {"$set": _set_camp, "$inc": {"version": 1}})
    logger.info("%s invitation %s : événement modifié (%s)", PREFIXE, str(_camp["id"])[:8],
                ",".join(sorted(list(_set_offre) + list(_set_cours) + list(_set_camp))))
    _c2, _camp2, _offre2, _cours2 = await _contexte(request, inv_id)
    return await _edition(_c2, _camp2, _offre2, _cours2)


# ── MÉDIAS DU COACH ─────────────────────────────────────────────────────────
_GENRES = {"video": ("video/",), "audio": ("audio/",), "image": ("image/",)}


@router.get("/api/referral/campaigns-medias")
async def medias_lister(request: Request, type: str = "video"):
    """Les médias de CE coach pour l'éditeur : ses fichiers importés (sans doublons)
    et, pour la vidéo, sa bibliothèque Médias. 50 au plus, les plus récents d'abord."""
    from api.routes import referral_campaigns_routes as RC
    _c = await RC._coach(request)
    _genre = type if type in _GENRES else "video"
    _email = str(_c.get("email") or "").strip().lower()
    _cle = _c.get("cle")
    _items, _vus = [], set()
    _fichiers = await _db()["uploaded_files"].find(
        {"coach_email": _email, "doublon_de": {"$exists": False},
         "content_type": {"$regex": "^%s" % _GENRES[_genre][0]}},
        {"_id": 0, "data": 0}).sort("created_at", -1).limit(MEDIAS_MAX).to_list(MEDIAS_MAX)
    for _f in _fichiers:
        _url = "/api/files/%s/%s" % (_f.get("file_id"), _f.get("filename"))
        if _url in _vus:
            continue
        _vus.add(_url)
        _items.append({"url": _url, "nom": _f.get("original_name") or _f.get("filename"), "type": _genre,
                       "taille": _f.get("size"), "date": str(_f.get("created_at") or "")[:19], "source": "import"})
    if _genre == "video":
        for _m in await _db()["prospection_medias"].find(
                {"coach_id": _email, "statut": {"$ne": "archivee"}}, {"_id": 0}).sort("updated_at", -1) \
                .limit(MEDIAS_MAX).to_list(MEDIAS_MAX):
            _url = str(_m.get("url") or "")
            if not _url or _url in _vus:
                continue
            _vus.add(_url)
            _items.append({"url": _url, "nom": (_m.get("fichier") or {}).get("nom") if isinstance(_m.get("fichier"), dict)
                           else (_m.get("version") or "Vidéo de la bibliothèque"), "type": "video",
                           "taille": None, "date": str(_m.get("updated_at") or "")[:19], "source": "bibliotheque"})
    if _genre == "image":
        # V610g : les miniatures déjà utilisées par CE coach (bibliothèque Médias « miniature »,
        # et images de ses invitations) — choisir sans réimporter.
        for _m in await _db()["prospection_medias"].find(
                {"coach_id": _email, "format": "miniature", "statut": {"$ne": "archivee"}}, {"_id": 0, "url": 1, "updated_at": 1, "fichier": 1}) \
                .sort("updated_at", -1).limit(MEDIAS_MAX).to_list(MEDIAS_MAX):
            _url = str(_m.get("url") or "")
            if _url and _url not in _vus:
                _vus.add(_url)
                _items.append({"url": _url, "nom": ((_m.get("fichier") or {}).get("nom") if isinstance(_m.get("fichier"), dict) else None)
                               or "Miniature", "type": "image", "taille": None, "date": str(_m.get("updated_at") or "")[:19],
                               "source": "bibliotheque"})
        for _inv in await _db()["referral_campaigns"].find(
                {"coach_id": _cle, "image_source": "upload", "image_url": {"$type": "string"}},
                {"_id": 0, "image_url": 1, "title": 1, "updated_at": 1}).sort("updated_at", -1).limit(MEDIAS_MAX).to_list(MEDIAS_MAX):
            _url = str(_inv.get("image_url") or "")
            if _url and _url not in _vus:
                _vus.add(_url)
                _items.append({"url": _url, "nom": "Miniature — %s" % (_inv.get("title") or "invitation"), "type": "image",
                               "taille": None, "date": str(_inv.get("updated_at") or "")[:19], "source": "invitation"})
    return {"type": _genre, "items": _items[:MEDIAS_MAX]}


def _octets(fichier_doc, file_id, filename):
    try:
        from api.server import _v413_chemin
        _chemin = _v413_chemin(file_id, filename)
        if _chemin and os.path.isfile(_chemin):
            with open(_chemin, "rb") as _f:
                return _f.read()
    except Exception:  # noqa: BLE001
        pass
    _d = (fichier_doc or {}).get("data")
    return bytes(_d) if _d else None


@router.post("/api/referral/campaigns-medias/enregistrer")
async def medias_enregistrer(request: Request):
    """Après un import (`/api/coach/upload-chunk`) : l'empreinte SHA-256 est calculée
    par le SERVEUR. Un fichier identique déjà importé par ce coach -> on rend SON
    adresse (le nouveau est marqué `doublon_de`, jamais supprimé)."""
    from api.routes import referral_campaigns_routes as RC
    _c = await RC._coach(request)
    try:
        _b = await request.json()
    except Exception:  # noqa: BLE001
        _b = {}
    _m = RE_FICHIER.match(str((_b or {}).get("url") or "").strip())
    if not _m:
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    _email = str(_c.get("email") or "").strip().lower()
    _doc = await _db()["uploaded_files"].find_one({"file_id": _m.group(1), "coach_email": _email})
    if not _doc:
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    _sha = _doc.get("sha256")
    if not _sha:
        _data = _octets(_doc, _m.group(1), _m.group(2))
        if not _data:
            raise HTTPException(status_code=404, detail="Fichier introuvable")
        _sha = hashlib.sha256(_data).hexdigest()
    _autre = await _db()["uploaded_files"].find_one(
        {"coach_email": _email, "sha256": _sha, "file_id": {"$ne": _m.group(1)}, "doublon_de": {"$exists": False}},
        {"_id": 0, "file_id": 1, "filename": 1})
    if _autre:
        await _db()["uploaded_files"].update_one({"file_id": _m.group(1)}, {"$set": {"sha256": _sha,
                                                                                    "doublon_de": _autre["file_id"]}})
        return {"url": "/api/files/%s/%s" % (_autre["file_id"], _autre["filename"]), "doublon": True}
    await _db()["uploaded_files"].update_one({"file_id": _m.group(1)}, {"$set": {"sha256": _sha}})
    return {"url": "/api/files/%s/%s" % (_m.group(1), _m.group(2)), "doublon": False}
