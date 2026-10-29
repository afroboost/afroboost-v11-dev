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
import uuid
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


async def _seance_ponctuelle(cours_source, date, heure, coach):
    """V640b : crée un cours ponctuel (date fixe) à partir d'un cours récurrent.
    Le cours est invisible (réservation uniquement via l'invitation)."""
    _id = str(uuid.uuid4())
    _now = datetime.now(timezone.utc).isoformat()
    _copie = {
        "id": _id, "coach_id": coach["cle"],
        "name": cours_source.get("name", "Séance"),
        "date": date, "time": heure,
        "location": cours_source.get("location", ""),
        "locationName": cours_source.get("locationName", ""),
        "duration": cours_source.get("duration"),
        "visible": False, "archived": False,
        "created_at": _now, "copie_de": cours_source.get("id"),
        "_v640b_ponctuel": True,
    }
    await _db()["courses"].insert_one(dict(_copie))
    logger.info("%s V640b séance ponctuelle %s (source=%s, %s %s)",
                PREFIXE, _id, cours_source.get("id"), date, heure)
    return _copie


async def _seance_autonome(date, heure, coach, camp, offre):
    """V640b-fix : crée une séance ponctuelle SANS cours source (invitation sans
    course_id, ex. Hétaïra). Lieu déduit de la campagne ou de l'offre."""
    _id = str(uuid.uuid4())
    _now = datetime.now(timezone.utc).isoformat()
    _lieu = camp.get("lieu") or (offre or {}).get("location") or ""
    _doc = {
        "id": _id, "coach_id": coach["cle"],
        "name": (offre or {}).get("name") or camp.get("title") or "Séance",
        "date": date, "time": heure,
        "location": _lieu, "locationName": _lieu,
        "duration": (offre or {}).get("duration"),
        "visible": False, "archived": False,
        "created_at": _now, "_v640b_ponctuel": True,
    }
    await _db()["courses"].insert_one(dict(_doc))
    logger.info("%s V640b-fix séance autonome %s (%s %s)", PREFIXE, _id, date, heure)
    return _doc


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


# ── V618M — AVANTAGES MEMBRES + URGENCE / PLACES ─────────────────────────────
TEXTE_URGENCE_MAX = 40


def _expiree(o, maintenant=None) -> bool:
    _v = str((o or {}).get("expiration_date") or "").strip()
    if not _v:
        return False
    try:
        _d = datetime.fromisoformat(_v.replace("Z", "+00:00"))
        _d = _d if _d.tzinfo else _d.replace(tzinfo=timezone.utc)
        return _d < (maintenant or datetime.now(timezone.utc))
    except ValueError:
        return False


def offres_choisissables(offres, maintenant=None):
    """PURE — (actives, autres) pour le sélecteur coach. Actives : visibles, non archivées, non
    expirées, ni événement ni produit, sans doublon de nom (la plus récente gardée). « Autres » :
    masquées ou expirées (jamais archivées) — proposées à part, jamais dans la liste principale."""
    _act, _aut, _noms = [], [], {}
    for _o in sorted(offres or [], key=lambda x: str((x or {}).get("created_at") or ""), reverse=True):
        if not _o or not _o.get("id") or _o.get("archived") is True:
            continue
        if str(_o.get("offer_type") or "") == "event" or _o.get("isProduct") is True or str(_o.get("offer_type") or "") == "product":
            continue
        _e = {"id": _o["id"], "nom": str(_o.get("name") or "").strip() or "Offre sans nom"}
        if _o.get("visible") is False or _expiree(_o, maintenant):
            _aut.append(_e)
            continue
        _cle = " ".join(_e["nom"].lower().split())
        if _cle in _noms:
            continue
        _noms[_cle] = True
        _act.append(_e)
    import unicodedata
    _par_nom = lambda e: unicodedata.normalize("NFD", e["nom"].lower()).encode("ascii", "ignore")  # noqa: E731  (É trié comme E)
    return sorted(_act, key=_par_nom), sorted(_aut, key=_par_nom)


async def _offres_du_coach(offre):
    _coach = str((offre or {}).get("coach_id") or "").strip()
    _q = {"coach_id": _coach} if _coach else {"coach_id": {"$in": [None, ""]}}
    return await _db()["offers"].find(_q, {"_id": 0, "id": 1, "name": 1, "offer_type": 1, "visible": 1, "archived": 1,
                                           "expiration_date": 1, "isProduct": 1, "created_at": 1}).to_list(300)


async def _avantages_edition(offre) -> dict:
    from api.routes import evenement_special as EVT
    _toutes = await _offres_du_coach(offre)
    _act, _aut = offres_choisissables(_toutes)
    _noms = {o["id"]: str(o.get("name") or "").strip() for o in _toutes}
    _actives = {o["id"] for o in _act}
    return {
        "actif": (offre or {}).get("gratuit_membres_actif") is not False,
        "regles": [dict(_r, nom=_noms.get(_r["offer_id"]) or "Offre retirée", active=_r["offer_id"] in _actives)
                   for _r in EVT.avantages_configures(offre)],
        "offres": _act, "autres": _aut,
    }


async def _urgence_edition(offre) -> dict:
    from api.routes import evenement_special as EVT
    _o = offre or {}
    return {"texte": str(_o.get("texte_urgence") or ""), "visible": _o.get("texte_urgence_visible") is True,
            "capacite_limitee": EVT.capacite(_o) is not None,
            "capacite_max": EVT.capacite(_o) or (int(_o["capacite_max"]) if isinstance(_o.get("capacite_max"), int) else None),
            "places_prises": await EVT.places_prises(_db(), _o) if _o.get("id") else 0}


def valider_avantages(brut, offres_coach):
    """PURE — la liste enregistrable (sans « aucun »), ou HTTPException 422. Une offre n'est
    acceptée que si elle appartient au coach (ids réels, jamais un titre) et n'est ni un
    événement ni un produit."""
    from api.routes import evenement_special as EVT
    if not isinstance(brut, list) or len(brut) > 50:
        raise HTTPException(status_code=422, detail="Liste d'avantages illisible.")
    _permis = {o["id"]: o for o in offres_coach or [] if o.get("id") and str(o.get("offer_type") or "") != "event"
               and o.get("isProduct") is not True and o.get("archived") is not True}
    _sortie, _vus = [], set()
    for _e in brut:
        _id = str((_e or {}).get("offer_id") or "").strip() if isinstance(_e, dict) else ""
        if not _id or _id not in _permis:
            raise HTTPException(status_code=422, detail="Une offre choisie n'existe pas (ou n'est pas à toi).")
        if _id in _vus:
            raise HTTPException(status_code=422, detail="La même offre apparaît deux fois.")
        _vus.add(_id)
        _t = str((_e or {}).get("type") or "")
        if _t == "reduction" and not (isinstance(_e.get("valeur"), (int, float)) and 1 <= _e["valeur"] <= 100):
            raise HTTPException(status_code=422, detail="La réduction doit être entre 1 et 100 %.")
        if _t == "prix_fixe" and not (isinstance(_e.get("valeur"), (int, float)) and 0 <= _e["valeur"] <= EVT.PRIX_FIXE_MAX):
            raise HTTPException(status_code=422, detail="Le prix membre doit être un montant entre 0 et 10000 CHF.")
        _r = EVT._regle_valide(_e)
        if not _r:
            raise HTTPException(status_code=422, detail="Choisis : Aucun avantage, Gratuit, Réduction % ou Prix fixe.")
        if _r["type"] != "aucun":
            _sortie.append({"offer_id": _id, "type": _r["type"], "valeur": _r["valeur"]})
    return _sortie


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
            # V640b-fix : la date est TOUJOURS modifiable pour un événement.
            # Sans cours : une séance autonome est créée à l'horaire choisi.
            # Cours dédié : le cours et l'offre sont modifiés.
            # Cours récurrent : une séance ponctuelle est créée si besoin.
            "date_modifiable": True,
            "cours_recurrent": bool(cours and not await _cours_dedie(cours, offre)),
            "tarifs": _tarifs(offre) if camp.get("type") == "event_paid" else None,
            "membres": ({"configuree": True, "actif": (offre or {}).get("gratuit_membres_actif") is not False,
                         "libelle": "Avantages membres"}
                        if EVT.regle_membres_configuree(offre) else None),
            # V618M : la configuration par OFFRE (gratuit / réduction / prix fixe / aucun) et les
            # offres que le coach peut choisir ; l'urgence (texte) et la capacité réelle, séparées.
            "avantages": (await _avantages_edition(offre)) if camp.get("type") == "event_paid" else None,
            "urgence": await _urgence_edition(offre),
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
    _v640b_params = None
    _v640b_autonome = None

    # ── Date / heure ────────────────────────────────────────────────────────
    _date = str(_b.get("date") or "").strip() if "date" in _b else None
    _heure = str(_b.get("heure") or "").strip() if "heure" in _b else None
    if _date is not None or _heure is not None:
        # V640 : pour un cours récurrent, les valeurs par défaut viennent de
        # l'occurrence de la campagne, pas de l'offre (qui n'a pas de countdown).
        _occ_existante = str(_camp.get("occurrence") or "")
        _d = _date if _date is not None else (
            str(_o.get("countdown_date") or "")[:10] if _dedie
            else _occ_existante[:10])
        _h = _heure if _heure is not None else (
            str(_o.get("countdown_time") or "")[:5] if _dedie
            else _occ_existante[11:16])
        if not RE_DATE.match(_d) or not RE_HEURE.match(_h):
            raise HTTPException(status_code=422, detail="Date (AAAA-MM-JJ) et heure (HH:MM) de l'événement attendues.")
        _nouvelle_occ = "%sT%s" % (_d, _h)
        _ancienne = str(_camp.get("occurrence") or "")[:16]
        if _nouvelle_occ != _ancienne:
            if _vers_utc(_nouvelle_occ) <= datetime.now(timezone.utc):
                raise HTTPException(status_code=422, detail="La nouvelle date doit être dans le futur.")
            _sensible = True
            if _dedie:
                # Cours dédié → on modifie le cours, l'offre ET l'occurrence
                _o.update(countdown_enabled=True, countdown_date=_d, countdown_time=_h)
                _set_offre.update(countdown_enabled=True, countdown_date=_d, countdown_time=_h)
                _set_cours.update(date=_d, time=_h)
            elif _cours:
                # V640b : cours récurrent — date libre. Si l'horaire ne correspond
                # pas à une séance existante, on PRÉPARE la création d'une séance
                # ponctuelle (différée après les gates simuler/confirmer).
                if not IC.seance_du_cours(_cours, _nouvelle_occ + ":00"):
                    _v640b_params = (_cours, _d, _h, _c, _o)
            # V640b-fix : sans cours lié, créer une séance autonome (différée
            # après les gates simuler/confirmer, comme pour les récurrents).
            if not _dedie and not _cours:
                _v640b_autonome = (_d, _h, _c, _camp, _o)
            _set_camp["occurrence"] = IC.normaliser_occurrence(_nouvelle_occ)

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

    # ── V618M : avantages membres par offre (n'agit que sur les NOUVELLES réservations) ──
    if "avantages_membres" in _b:
        if _camp.get("type") != "event_paid":
            raise HTTPException(status_code=409, detail="Les avantages membres concernent un événement payant.")
        from api.routes import evenement_special as EVT
        _liste = valider_avantages(_b.get("avantages_membres"), await _offres_du_coach(_offre))
        if _liste != [e for e in EVT.avantages_configures(_offre) if e["type"] != "aucun"] \
                or not isinstance(_offre.get("avantages_membres"), list):
            _o["avantages_membres"] = _liste
            _set_offre["avantages_membres"] = _liste
            # Compatibilité (retour arrière possible) : l'ancienne liste « gratuit » suit.
            _set_offre["gratuit_abonnements_offer_ids"] = [e["offer_id"] for e in _liste if e["type"] == "gratuit"]
        # Les paiements et réservations PASSÉS ne sont jamais recalculés : pas de confirmation.

    # ── V618M : urgence (texte marketing) et capacité réelle — deux réglages séparés ──
    if "urgence" in _b:
        from api.routes import evenement_special as EVT
        _u = _b.get("urgence") if isinstance(_b.get("urgence"), dict) else {}
        if "texte" in _u:
            _txt = " ".join(str(_u.get("texte") or "").replace("<", "").replace(">", "").split())
            if len(_txt) > TEXTE_URGENCE_MAX:
                raise HTTPException(status_code=422, detail="Le texte d'urgence fait 40 caractères au plus.")
            _set_offre["texte_urgence"] = _o["texte_urgence"] = _txt
        if "visible" in _u:
            _set_offre["texte_urgence_visible"] = _o["texte_urgence_visible"] = bool(_u.get("visible"))
        if "capacite_limitee" in _u:
            _lim = bool(_u.get("capacite_limitee"))
            if _lim:
                try:
                    _max = int(_u.get("capacite_max"))
                except (TypeError, ValueError):
                    _max = 0
                if not 1 <= _max <= EVT.CAPACITE_MAX:
                    raise HTTPException(status_code=422, detail="Indique une capacité maximum entre 1 et 10000.")
                _pris = await EVT.places_prises(_db(), _offre)
                if _max < _pris:
                    raise HTTPException(status_code=422, detail="%d places sont déjà réservées : la capacité ne peut pas être plus petite." % _pris)
                _set_offre["capacite_max"] = _o["capacite_max"] = _max
            _set_offre["capacite_limitee"] = _o["capacite_limitee"] = _lim
        for _k in ("texte_urgence", "texte_urgence_visible", "capacite_limitee", "capacite_max"):
            if _k in _set_offre and _set_offre[_k] == _offre.get(_k):
                del _set_offre[_k]

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

    # V640b : créer la séance ponctuelle APRÈS les gates (idempotent : même source+date → réutilise).
    if _v640b_params:
        _src, _pd, _ph, _pc, _po = _v640b_params
        _existant = await _db()["courses"].find_one(
            {"_v640b_ponctuel": True, "copie_de": _src.get("id"), "date": _pd, "time": _ph})
        _ponctuel = _existant or await _seance_ponctuelle(_src, _pd, _ph, _pc)
        _set_camp["course_id"] = _ponctuel["id"]
        _ids = list(_po.get("linked_course_ids") or [])
        if _ponctuel["id"] not in _ids:
            _ids.append(_ponctuel["id"])
            _set_offre["linked_course_ids"] = _ids

    # V640b-fix : séance autonome pour invitation sans cours (idempotent sur date+heure+coach).
    if _v640b_autonome:
        _ad, _ah, _ac, _acamp, _ao = _v640b_autonome
        _existant = await _db()["courses"].find_one(
            {"_v640b_ponctuel": True, "copie_de": {"$exists": False},
             "coach_id": _ac["cle"], "date": _ad, "time": _ah})
        _auto = _existant or await _seance_autonome(_ad, _ah, _ac, _acamp, _ao)
        _set_camp["course_id"] = _auto["id"]
        _ids = list(_ao.get("linked_course_ids") or [])
        if _auto["id"] not in _ids:
            _ids.append(_auto["id"])
            _set_offre["linked_course_ids"] = _ids

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
    # V610l — les audios sont stockés AVEC leur contenu (`data`) : un find().sort() triait
    # les documents ENTIERS en mémoire -> « Sort exceeded memory limit » (32 Mo) -> 500,
    # bibliothèque audio inutilisable. Le contenu est retiré AVANT le tri.
    _fichiers = await _db()["uploaded_files"].aggregate([
        {"$match": {"coach_email": _email, "doublon_de": {"$exists": False},
                    "content_type": {"$regex": "^%s" % _GENRES[_genre][0]}}},
        {"$project": {"_id": 0, "data": 0}},
        {"$sort": {"created_at": -1}},
        {"$limit": MEDIAS_MAX},
    ]).to_list(MEDIAS_MAX)
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
