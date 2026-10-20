# -*- coding: utf-8 -*-
"""ANALYTICS — LA route unique du cockpit. Lecture seule, JWT strict.

GET /api/analytics/cockpit?periode=aujourdhui|semaine|mois|annee|perso
                          &du=YYYY-MM-DD&au=YYYY-MM-DD
                          &coach_id=...&course_id=...&granularite=jour|semaine|mois

ISOLATION PAR LE SERVEUR. Le coach est tiré du JETON SIGNÉ (jamais de
`X-User-Email`, falsifiable). Un coach ne voit que `coach_id = son e-mail`,
et `coach_id` en paramètre lui est REFUSÉ s'il ne le désigne pas lui-même. Le
super-admin voit tout, ou un coach s'il le demande.

PERFORMANCE. Un nombre FIXE de requêtes (sept), jamais une par participant :
réservations de cours du périmètre (tout l'historique — « nouveau » et
« fidélité » en ont besoin), cours, souscriptions, fiches codes, offres, cartes
membres, transactions de paiement. Puis tout se calcule en mémoire
(`analytics_shared`).

PHASE 2 (revenus, abonnements, essais & conversion) : les souscriptions, fiches
et paiements sont lus sur TOUT le périmètre (pas seulement ceux des
réservations) — un Pulse acheté et jamais consommé est une recette. La DB reste
en LECTURE SEULE : aucune écriture, nulle part.

PHASE 3 (`vue=association`, `GET /api/analytics/export?format=csv|xlsx|pdf`) :
une PROJECTION agrégée du même résultat (période précédente et douze mois
calculés en mémoire sur les mêmes tables, + une lecture de `concept` pour le
nom public d'un coach filtré). Aucune donnée personnelle ne sort :
`verifier_anonymat` refuse la réponse sinon.
"""
import logging
from fastapi import APIRouter, HTTPException, Request

from api.routes.analytics_shared import (
    PERIODES, bornes_periode, calculer_kpi, calculer_kpi_finance, choisir_fiche_code, cle_participant,
    construire_achats, construire_faits, mois_suivant, vers_local, calculer_kpi_sources,
)
from api.routes.analytics_association import (
    PERIMETRE_ENSEMBLE, export_csv, export_pdf, export_xlsx, periode_precedente, projeter_association,
    verifier_anonymat,
)
from api.routes.analytics_cloture import (
    CLOTURE_COLLECTION, RAISON_DEJA_CLOTURE, assoc_depuis_snapshot, cle_cloture, construire_snapshot,
    est_cloturable, meta_snapshot, verifier_integrite,
)
from api.routes.analytics_stats import (
    AVERT_CLOTURE_ALTEREE, PORTEE_FINANCES, PORTEE_FREQUENTATION, RAISON_ERREUR, construire_reponse,
    genere_le as genere_le_stats, reponse_base_indisponible,
)
from api.routes.shared import is_super_admin
from datetime import datetime, timezone
from fastapi.responses import JSONResponse, Response

logger = logging.getLogger(__name__)
analytics_router = APIRouter(prefix="/analytics", tags=["analytics"])
# STATS-1 : la route MACHINE du Cockpit de l'association, dans ce même fichier
# (mêmes lectures, même cœur). Son propre préfixe : `/api/stats/...`.
stats_router = APIRouter(prefix="/stats", tags=["stats"])


async def _coach_analytics(request: Request) -> str:
    """Coach/admin par JWT SIGNÉ uniquement — 401 sans jeton, 403 sans droit."""
    from api.server import _v311_coach_email_from_jwt, _v309_is_coach_or_admin
    email = _v311_coach_email_from_jwt(request)
    if not email:
        raise HTTPException(status_code=401, detail="Jeton signé requis")
    if not await _v309_is_coach_or_admin(email):
        raise HTTPException(status_code=403, detail="Réservé aux coachs")
    return email


def _perimetre(email: str, coach_id: str) -> str:
    """Le coach_id effectif : imposé pour un coach, libre pour le super-admin."""
    _demande = str(coach_id or "").strip().lower()
    if is_super_admin(email):
        return _demande            # "" = tout le site
    if _demande and _demande != email.lower():
        raise HTTPException(status_code=403, detail="Périmètre d'un autre coach")
    return email.lower()


async def _lire_sources(db, perimetre: str) -> dict:
    """Les SEPT lectures du moteur, et rien d'autre. Lecture seule.

    Extraites telles quelles de `_calculer_cockpit` (STATS-1) pour que la route
    machine `/api/stats/association` lise EXACTEMENT les mêmes documents que
    l'écran coach : mêmes requêtes, mêmes projections, mêmes bornes. Un banc
    compare la sortie du cockpit avant / après cette extraction.
    """
    # ── 1. les réservations de cours du périmètre (historique complet) ──────
    _q = {"isProduct": {"$ne": True}}
    if perimetre:
        _q["coach_id"] = perimetre
    # Le filtre COURS s'applique EN MÉMOIRE, après construction des faits : la
    # liste des cours proposée à l'écran (`cours_disponibles`) vient ainsi des
    # mêmes lignes, sans requête supplémentaire, et reste complète quand un
    # cours est sélectionné.
    reservations = await db.reservations.find(_q, {"_id": 0}).to_list(50000)

    codes = {str(r.get("discountCode") or r.get("promoCode") or "").strip().upper()
             for r in reservations}
    codes.discard("")
    sids = {str(r.get("subscriptionId") or "").strip() for r in reservations}
    sids.discard("")
    cids = {str(r.get("courseId") or "").strip() for r in reservations}
    cids.discard("")

    # ── 2..7. les documents liés — le PÉRIMÈTRE entier pour la finance ──────
    # Souscriptions : celles du coach (ou toutes pour l'admin) PLUS celles que
    # les réservations désignent (id ou code) — un forfait ancien sans coach_id
    # reste rattaché à ses réservations. Fiches codes : idem par le code.
    cours = await db.courses.find({"id": {"$in": list(cids)}}, {"_id": 0, "id": 1, "name": 1,
                                  "weekday": 1, "locationName": 1, "location": 1}).to_list(5000) if cids else []
    _q_subs = {}
    if perimetre:
        _q_subs = {"$or": [{"coach_id": perimetre}, {"id": {"$in": list(sids)}}, {"code": {"$in": list(codes)}}]}
    forfaits = await db.subscriptions.find(_q_subs, {"_id": 0}).to_list(20000)
    codes_tous = set(codes) | {str(f.get("code") or "").strip().upper() for f in forfaits}
    codes_tous.discard("")
    _q_codes = {}
    if perimetre:
        _q_codes = {"$or": [{"coach_id": perimetre}, {"code": {"$in": list(codes_tous)}}]}
    fiches = await db.discount_codes.find(_q_codes, {"_id": 0}).to_list(20000)
    # Toutes les offres (catalogue court) : nom, prix, pack — la classification
    # « Pulse / abonnement / autre » en a besoin, pas seulement le prix.
    offres = await db.offers.find({}, {"_id": 0, "id": 1, "name": 1, "price": 1, "pack_sessions": 1}).to_list(1000)
    _q_cartes = {"coach_id": perimetre} if perimetre else {}
    cartes = await db.memberships.find(_q_cartes, {"_id": 0, "email": 1, "date_debut": 1, "date_fin": 1,
                                                    "source": 1, "coach_id": 1, "subscription_id": 1}).to_list(20000)
    _q_pay = {"payment_status": {"$in": ["paid", "pending"]}}
    if perimetre:
        _q_pay["coach_id"] = perimetre
    paiements = await db.payment_transactions.find(_q_pay, {"_id": 0, "id": 1, "session_id": 1, "amount": 1,
                                                            "amount_total": 1, "quantity": 1, "currency": 1,
                                                            "product_name": 1, "customer_email": 1, "metadata": 1,
                                                            "payment_status": 1, "payment_method": 1, "created_at": 1,
                                                            "coach_id": 1}).to_list(20000)
    return {"reservations": reservations, "cours": cours, "forfaits": forfaits, "fiches": fiches,
            "offres": offres, "cartes": cartes, "paiements": paiements}


def _coeur_kpi(sources: dict, perimetre: str, debut, fin, granularite: str, course_id: str,
               maintenant, normaliser_occurrence=None):
    """LE calcul en mémoire, PUR : sources lues -> (kpi, contexte).

    Aucune base, aucun jeton. Le cockpit coach et la route machine
    `/api/stats/association` passent par ici : une seule règle, partout.
    Le contexte (faits filtrés, achats, cartes) sert à la projection
    Association sans aucune lecture de plus.
    """
    reservations = sources["reservations"]
    cours, forfaits, fiches = sources["cours"], sources["forfaits"], sources["fiches"]
    offres, cartes, paiements = sources["offres"], sources["cartes"], sources["paiements"]
    _g = granularite

    cours_par_id = {c["id"]: c for c in cours if c.get("id")}
    forfaits_par_id = {f["id"]: f for f in forfaits if f.get("id")}
    forfaits_par_code = {}
    for f in forfaits:
        k = str(f.get("code") or "").strip().upper()
        if k and k not in forfaits_par_code:
            forfaits_par_code[k] = f
    # La phase 1 prenait la PREMIÈRE fiche d'un code ; la phase 2 choisit la
    # fiche du droit (`choisir_fiche_code`) — même règle pour les deux moteurs.
    _fiches_par_code = {}
    for f in fiches:
        k = str(f.get("code") or "").strip().upper()
        if k:
            _fiches_par_code.setdefault(k, []).append(f)
    codes_par_code = {k: choisir_fiche_code(v) for k, v in _fiches_par_code.items()}
    offres_par_id = {o["id"]: o for o in offres if o.get("id")}
    memberships_par_email = {cle_participant(c.get("email")): c for c in cartes if c.get("email")}

    table = construire_faits(reservations, cours_par_id, forfaits_par_id, forfaits_par_code,
                             codes_par_code, offres_par_id, memberships_par_email,
                             normaliser_occurrence=normaliser_occurrence)
    _cid = str(course_id or "").strip()
    _par_cours = {}
    for f in table["faits"]:
        k = f["course_id"] or f["course_name"]
        if not k:
            continue
        e = _par_cours.setdefault(k, {"id": f["course_id"] or "", "name": f["course_name"] or k, "reservations": 0})
        e["reservations"] += 1
    faits = [f for f in table["faits"] if f["course_id"] == _cid] if _cid else table["faits"]
    kpi = calculer_kpi(faits, debut, fin, _g)
    kpi["perimetre"] = {"coach_id": perimetre or "tous", "course_id": _cid or "tous"}
    kpi["cours_disponibles"] = sorted(_par_cours.values(), key=lambda c: (-c["reservations"], c["name"]))
    kpi["ecartees"] = table["ecartees"]
    kpi["qualite"].update(table["qualite"])

    # ── PHASE 2 : achats (un achat = une fois), abonnements, essais ────────
    # Global période/coach ; le filtre cours ne s'applique qu'à « valeur par
    # cours » (faits filtrés) et chaque section dit son périmètre.
    _subs_perim = [f for f in forfaits if not perimetre or str(f.get("coach_id") or "").strip().lower() == perimetre]
    _fiches_perim = fiches if not perimetre else [
        f for f in fiches if str(f.get("coach_id") or "").strip().lower() == perimetre
        or str(f.get("code") or "").strip().upper() in {str(x.get("code") or "").strip().upper() for x in _subs_perim}]
    _achats = construire_achats(_subs_perim, _fiches_perim, paiements, offres_par_id, maintenant)
    _fin = calculer_kpi_finance(_achats["achats"], _achats["en_attente"], cartes, faits, debut, fin, _g,
                                maintenant, cours_filtre=_cid,
                                encaissements_hors_achats=_achats.get("encaissements_supprimes"))
    kpi.update(_fin)
    kpi["achats"] = {"ecartes": _achats["ecartes"], "qualite": _achats["qualite"], "total": len(_achats["achats"])}
    # TRACKING 2B : ACQUISITION — PAR SOURCE. Même faits, mêmes achats, mêmes
    # moteurs, restreints à chaque source (first-touch de la personne). Aucune
    # lecture de plus. Fail-open : une erreur ici ne prive pas du reste du cockpit.
    try:
        kpi["sources"] = calculer_kpi_sources(faits, _achats["achats"], cartes, debut, fin, maintenant)
    except Exception as _src_e:
        logger.warning("[ANALYTICS] acquisition par source indisponible (%s)", type(_src_e).__name__)
        kpi["sources"] = {"convention": "", "lignes": [], "couverture": {}, "erreur": type(_src_e).__name__}
    kpi["requetes"] = 7
    ctx = {"faits": faits, "achats": _achats, "cartes": cartes, "cours_filtre": _cid}
    return kpi, ctx


def _projection_association(kpi: dict, ctx: dict, debut, fin, libelle: str, maintenant) -> dict:
    """PHASE 3 — la projection Association, en mémoire, depuis le contexte du cœur.

    La période précédente et les douze mois de l'année se calculent EN MÉMOIRE
    sur les faits et les achats déjà chargés (tout l'historique) : le bilan
    coûte 13 passes de plus sur quelques centaines de lignes, pas une requête.
    """
    faits, _achats, cartes, _cid = ctx["faits"], ctx["achats"], ctx["cartes"], ctx["cours_filtre"]

    def _kpi_de(_d, _f):
        _k = calculer_kpi(faits, _d, _f, "mois")
        _k.update(calculer_kpi_finance(_achats["achats"], _achats["en_attente"], cartes, faits, _d, _f,
                                       "mois", maintenant, cours_filtre=_cid,
                                       encaissements_hors_achats=_achats.get("encaissements_supprimes")))
        return _k
    _pd, _pf = periode_precedente(debut, fin)
    _prec = _kpi_de(_pd, _pf)
    _annee = []
    _m = debut.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    for _i in range(12):
        _annee.append((_m, _kpi_de(_m, mois_suivant(_m))))
        _m = mois_suivant(_m)
    return projeter_association(kpi, _prec, _annee, debut, fin, libelle, _cid, maintenant)


async def _calculer_cockpit(request: Request, periode: str = "mois", du: str = "", au: str = "",
                            coach_id: str = "", course_id: str = "", granularite: str = "jour",
                            mois: str = "", vue: str = ""):
    """LE calcul, partagé par le cockpit et les exports : mêmes lectures, mêmes règles."""
    from api.server import db
    from api.routes.reservation_routes import lot1_occurrence_iso

    email = await _coach_analytics(request)
    perimetre = _perimetre(email, coach_id)
    _p = str(periode or "mois").strip().lower()
    if _p not in PERIODES:
        raise HTTPException(status_code=400, detail="periode attendue : " + "|".join(PERIODES))
    _g = str(granularite or "jour").strip().lower()
    if _g not in ("jour", "semaine", "mois"):
        raise HTTPException(status_code=400, detail="granularite attendue : jour|semaine|mois")
    maintenant = vers_local(datetime.now(timezone.utc))
    debut, fin = bornes_periode(_p, maintenant, du, au, mois)
    if debut is None:
        raise HTTPException(status_code=400, detail="perso : du et au (YYYY-MM-DD, du <= au) requis ; mois : YYYY-MM")
    _vue = str(vue or "").strip().lower()

    sources = await _lire_sources(db, perimetre)
    kpi, ctx = _coeur_kpi(sources, perimetre, debut, fin, _g, course_id, maintenant,
                          normaliser_occurrence=lot1_occurrence_iso)
    _cid = ctx["cours_filtre"]

    # ── PHASE 3 : la projection Association — mêmes tables, AUCUNE lecture de plus ──
    if _vue == "association":
        _libelle = PERIMETRE_ENSEMBLE
        if perimetre:
            # Le nom public du coach (concept.appName), jamais son adresse.
            _concept = await db.concept.find_one({"coach_id": perimetre}, {"_id": 0, "appName": 1})
            _nom = str((_concept or {}).get("appName") or "").strip()
            _libelle = "Coach " + (_nom or "(identité masquée)")
        assoc = _projection_association(kpi, ctx, debut, fin, _libelle, maintenant)
        _fuites = verifier_anonymat(assoc)
        if _fuites:
            logger.error("[ANALYTICS] bilan association refusé : donnée personnelle détectée %s", _fuites[:3])
            raise HTTPException(status_code=500, detail="Bilan indisponible : donnée personnelle détectée dans la projection")
        kpi["association"] = assoc
        # ── PHASE 4 : l'état de clôture de cette période (UNE lecture, jamais une écriture) ──
        # Seul le MODE MOIS peut être clôturé : une vue personnalisée reste
        # dynamique même si ses bornes coïncident avec un mois civil.
        _ok, _raison = est_cloturable(debut, fin, maintenant, _cid, _p)
        _existante = None
        if _p == "mois" and not _cid:
            _existante = await db[CLOTURE_COLLECTION].find_one(
                {"cle": cle_cloture(debut.year, debut.month, perimetre)}, {"_id": 0, "bilan": 0})
        kpi["cloture"] = {
            "existante": meta_snapshot(_existante) if _existante else None,
            "cloturable": bool(_ok and not _existante and is_super_admin(email)),
            "raison": (RAISON_DEJA_CLOTURE if _existante else _raison) if not (_ok and not _existante) else "",
            "super_admin": is_super_admin(email),
        }
        kpi["requetes"] = 7 + (1 if perimetre else 0) + (1 if (_p == "mois" and not _cid) else 0)
    return kpi


@analytics_router.get("/cockpit")
async def analytics_cockpit(request: Request, periode: str = "mois", du: str = "", au: str = "",
                            coach_id: str = "", course_id: str = "", granularite: str = "jour",
                            mois: str = "", vue: str = ""):
    return await _calculer_cockpit(request, periode, du, au, coach_id, course_id, granularite, mois, vue)


FORMATS_EXPORT = {
    "csv": ("text/csv; charset=utf-8", "csv", export_csv),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx", export_xlsx),
    "pdf": ("application/pdf", "pdf", export_pdf),
}


@analytics_router.get("/export")
async def analytics_export(request: Request, format: str = "csv", periode: str = "mois", du: str = "", au: str = "",
                           coach_id: str = "", course_id: str = "", mois: str = ""):
    """Le bilan Association en CSV / XLSX / PDF — exactement le résultat de
    `vue=association`, sérialisé. Même garde JWT (401 sans jeton, 403 hors
    périmètre) : un lien direct ne contourne rien, le navigateur passe par
    `fetch` avec le jeton puis enregistre le blob."""
    _f = str(format or "csv").strip().lower()
    if _f not in FORMATS_EXPORT:
        raise HTTPException(status_code=400, detail="format attendu : csv|xlsx|pdf")
    kpi = await _calculer_cockpit(request, periode, du, au, coach_id, course_id, "mois", mois, "association")
    assoc = kpi["association"]
    _type, _ext, _fabrique = FORMATS_EXPORT[_f]
    try:
        contenu = _fabrique(assoc)
    except ImportError as _err:
        logger.error("[ANALYTICS] export %s impossible : %s", _f, _err)
        raise HTTPException(status_code=503, detail="Export %s indisponible sur ce serveur" % _f)
    _nom = "bilan-afroboost-%s.%s" % (assoc["periode"]["debut"][:7] if _f else "", _ext)
    return Response(content=contenu, media_type=_type,
                    headers={"Content-Disposition": 'attachment; filename="%s"' % _nom,
                             "Cache-Control": "no-store"})


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 4 — CLÔTURE MENSUELLE. La seule écriture d'Analytics : `insert_one`
# dans `analytics_monthly_reports`, et rien d'autre.
# ═══════════════════════════════════════════════════════════════════════════

async def _super_admin_analytics(request: Request) -> str:
    """Clôturer est réservé au super-admin : 401 sans jeton, 403 pour un coach."""
    email = await _coach_analytics(request)
    if not is_super_admin(email):
        raise HTTPException(status_code=403, detail="Clôture réservée au super-admin")
    return email


async def _index_clotures(db):
    """Index uniques de la collection des bilans figés — idempotent, posé AVANT
    la première écriture. `cle` (année-mois:périmètre) rend la clôture
    idempotente même sous deux appels simultanés : le second `insert_one`
    tombe en DuplicateKeyError et devient un 409, jamais un second bilan."""
    for _champ, _ in (("cle", "unique"), ("id", "unique")):
        try:
            await db[CLOTURE_COLLECTION].create_index(_champ, unique=True)
        except Exception as _err:  # noqa: BLE001 — l'index existe déjà : rien à faire
            logger.info("[ANALYTICS] index %s.%s : %s", CLOTURE_COLLECTION, _champ, _err)


@analytics_router.post("/cloture")
async def analytics_cloturer(request: Request, mois: str = "", coach_id: str = ""):
    """Figer le bilan Association d'un mois civil terminé. Super-admin seulement.

    Le contenu figé est EXACTEMENT la projection de la phase 3 (mêmes règles,
    même anonymat) ; la clé unique interdit tout second bilan pour la même
    période et le même périmètre (409, jamais un écrasement)."""
    from api.server import db
    from pymongo.errors import DuplicateKeyError

    email = await _super_admin_analytics(request)
    _mois = str(mois or "").strip()
    if len(_mois) != 7:
        raise HTTPException(status_code=400, detail="mois attendu : YYYY-MM")
    # Le serveur est la source de vérité : `du`/`au`/`periode`/`course_id` du
    # client ne sont JAMAIS lus ici — le périmètre mensuel officiel est
    # reconstruit depuis `mois=YYYY-MM` seul, en mode mois, sans filtre cours.
    kpi = await _calculer_cockpit(request, "mois", "", "", coach_id, "", "mois", _mois, "association")
    maintenant = vers_local(datetime.now(timezone.utc))
    debut, fin = bornes_periode("mois", maintenant, "", "", _mois)
    perimetre = _perimetre(email, coach_id)
    _ok, _raison = est_cloturable(debut, fin, maintenant, "", "mois")
    if not _ok:
        raise HTTPException(status_code=409, detail=_raison)
    _cle = cle_cloture(debut.year, debut.month, perimetre)
    _existante = await db[CLOTURE_COLLECTION].find_one({"cle": _cle}, {"_id": 0, "bilan": 0})
    if _existante:
        raise HTTPException(status_code=409, detail=RAISON_DEJA_CLOTURE)
    doc = construire_snapshot(kpi["association"], debut, fin, perimetre, email, maintenant)
    _fuites = verifier_anonymat(doc["bilan"])
    if _fuites:
        raise HTTPException(status_code=500, detail="Clôture refusée : donnée personnelle détectée")
    await _index_clotures(db)
    try:
        await db[CLOTURE_COLLECTION].insert_one(dict(doc))
    except DuplicateKeyError:
        # Deux clics, deux onglets, un retry : le premier a gagné, on le rend.
        raise HTTPException(status_code=409, detail=RAISON_DEJA_CLOTURE)
    logger.info("[ANALYTICS] bilan clôturé %s par %s (empreinte %s)", _cle, email, doc["hash"][:12])
    return {"cloture": meta_snapshot(doc), "message": "Bilan %s clôturé." % doc["periode"]["libelle"]}


@analytics_router.get("/clotures")
async def analytics_clotures(request: Request, coach_id: str = ""):
    """Les archives : les bilans figés du périmètre (coach : les siens ; admin : tout ou un coach)."""
    from api.server import db
    email = await _coach_analytics(request)
    perimetre = _perimetre(email, coach_id)
    _q = {}
    if perimetre:
        _q = {"cle": {"$in": [cle_cloture(a, m, perimetre) for a in range(2024, 2041) for m in range(1, 13)]}}
    docs = await db[CLOTURE_COLLECTION].find(_q, {"_id": 0, "bilan": 0}).to_list(1000)
    docs = sorted(docs, key=lambda d: (str(d.get("annee")), str(d.get("mois")).zfill(2), str(d.get("cle"))), reverse=True)
    return {"clotures": [meta_snapshot(d) for d in docs], "perimetre": perimetre or "tous"}


async def _snapshot_autorise(request: Request, id: str) -> dict:
    """Le bilan figé `id`, si le jeton a le droit de le voir (périmètre imposé au coach)."""
    from api.server import db
    email = await _coach_analytics(request)
    doc = await db[CLOTURE_COLLECTION].find_one({"id": str(id or "").strip()}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Bilan clôturé introuvable")
    _coach = str((doc.get("perimetre") or {}).get("coach_id") or "")
    if not is_super_admin(email) and _coach != email.lower():
        raise HTTPException(status_code=403, detail="Périmètre d'un autre coach")
    return doc


@analytics_router.get("/clotures/{id}")
async def analytics_cloture_lire(request: Request, id: str):
    doc = await _snapshot_autorise(request, id)
    return {"cloture": meta_snapshot(doc), "bilan": assoc_depuis_snapshot(doc)}


@analytics_router.get("/clotures/{id}/export")
async def analytics_cloture_export(request: Request, id: str, format: str = "csv"):
    """CSV / XLSX / PDF OFFICIELS : générés depuis le SNAPSHOT, jamais depuis les
    données courantes — le fichier de dans six mois est celui d'aujourd'hui."""
    _f = str(format or "csv").strip().lower()
    if _f not in FORMATS_EXPORT:
        raise HTTPException(status_code=400, detail="format attendu : csv|xlsx|pdf")
    doc = await _snapshot_autorise(request, id)
    assoc = assoc_depuis_snapshot(doc)
    _type, _ext, _fabrique = FORMATS_EXPORT[_f]
    try:
        contenu = _fabrique(assoc)
    except ImportError as _err:
        logger.error("[ANALYTICS] export officiel %s impossible : %s", _f, _err)
        raise HTTPException(status_code=503, detail="Export %s indisponible sur ce serveur" % _f)
    _nom = "bilan-officiel-afroboost-%04d-%02d-v%s.%s" % (doc["annee"], doc["mois"], doc.get("version", 1), _ext)
    return Response(content=contenu, media_type=_type,
                    headers={"Content-Disposition": 'attachment; filename="%s"' % _nom, "Cache-Control": "no-store"})


# ═══════════════════════════════════════════════════════════════════════════
# STATS-1 — `GET /api/stats/association` : la lecture MACHINE du Cockpit de
# l'association (afroboosteur.com), de serveur à serveur. LECTURE SEULE.
#
# * Périmètre FORCÉ « ensemble » (tout le site, comme le bilan Association du
#   super-admin) : aucun paramètre ne permet de viser un coach ou un cours.
# * Deux clés dédiées, comparées en TEMPS CONSTANT (patron V332) :
#   `AFROBOOST_STATS_KEY_FREQUENTATION` (fréquentation, essais, abonnements)
#   et `AFROBOOST_STATS_KEY_FINANCES` (le même + les revenus). Aucune clé
#   posée -> 503 JSON (inerte) ; clé fausse -> 401 JSON.
# * Débit limité par adresse AVANT tout contrôle de clé : 429 JSON.
# * Cache serveur ~10 min par (portée, période, granularité). Aucune écriture.
# ═══════════════════════════════════════════════════════════════════════════
import os as _os
import re as _re
import time as _time

STATS_ENV_FREQUENTATION = "AFROBOOST_STATS_KEY_FREQUENTATION"
STATS_ENV_FINANCES = "AFROBOOST_STATS_KEY_FINANCES"
STATS_CACHE_TTL = 600.0
STATS_DEBIT_MAX = 30           # appels
STATS_DEBIT_FENETRE = 60.0     # secondes
# PAS de verrou global des échecs (retiré, décision de coordination) : il
# laissait n'importe qui couper la route en continu avec 30 clés fausses.
# La défense est l'ENTROPIE de la clé (≥ 32 caractères exigés, 64 hexa
# recommandés : `openssl rand -hex 32`) ; le débit par adresse n'est qu'un
# frein, l'adresse venant d'en-têtes falsifiables.
STATS_CLE_LONGUEUR_MIN = 32    # une clé plus courte est traitée comme ABSENTE
_STATS_CACHE = {}
_STATS_DEBIT = {}
# ASCII STRICT : `\d` accepterait les chiffres arabes-indiens (« ٢٠٢٦ »), que
# `strptime` refuse ensuite -> 500. `fullmatch` refuse aussi le saut de ligne
# final que `$` tolère.
_RE_MOIS = _re.compile(r"([0-9]{4})-([0-9]{2})", _re.ASCII)
_RE_ANNEE = _re.compile(r"([0-9]{4})", _re.ASCII)
_RE_GRANULARITE = _re.compile(r"[a-z]{1,10}", _re.ASCII)


def _stats_erreur(statut, code, message, entetes=None):
    _h = {"Cache-Control": "no-store"}
    _h.update(entetes or {})
    return JSONResponse(status_code=statut, content={"ok": False, "error": code, "message": message}, headers=_h)


def _stats_ip(request) -> str:
    """L'adresse, lue comme `_live_guest_ip` (server.py) : CF-Connecting-IP, sinon le
    DERNIER saut de X-Forwarded-For (celui posé par le proxy), sinon la socket.
    ⚠️ Falsifiable : ce débit est un simple frein ; la défense est l'entropie de la clé."""
    _h = getattr(request, "headers", {}) or {}
    _ip = (_h.get("cf-connecting-ip") or _h.get("CF-Connecting-IP") or "").strip()
    if not _ip:
        _vals = [v.strip() for v in (_h.get("x-forwarded-for") or _h.get("X-Forwarded-For") or "").split(",") if v.strip()]
        _ip = _vals[-1] if _vals else ""
    if not _ip:
        _c = getattr(request, "client", None)
        _ip = getattr(_c, "host", "") or "inconnu"
    return _ip[:64]


def _stats_cle_configuree(nom: str) -> str:
    """La clé posée, ou "" si absente OU trop courte (< 32 caractères)."""
    _v = (_os.environ.get(nom, "") or "").strip()
    if _v and len(_v) < STATS_CLE_LONGUEUR_MIN:
        logger.error("[STATS] %s trop courte (< %d caractères) : traitée comme absente", nom, STATS_CLE_LONGUEUR_MIN)
        return ""
    return _v


def _stats_debit_ok(cle: str) -> bool:
    """Fenêtre glissante en mémoire (même forme que `_lot3b_debit_ok`)."""
    _now = _time.monotonic()
    _hist = [h for h in _STATS_DEBIT.get(cle, []) if _now - h < STATS_DEBIT_FENETRE]
    if len(_hist) >= STATS_DEBIT_MAX:
        _STATS_DEBIT[cle] = _hist
        return False
    _hist.append(_now)
    _STATS_DEBIT[cle] = _hist
    if len(_STATS_DEBIT) > 5000:      # borne mémoire
        for _k in list(_STATS_DEBIT.keys())[:1000]:
            _STATS_DEBIT.pop(_k, None)
    return True


def _stats_portee(request):
    """(portée, None) si la clé est bonne ; (None, réponse JSON 503/401) sinon."""
    import hmac
    _freq = _stats_cle_configuree(STATS_ENV_FREQUENTATION)
    _fin = _stats_cle_configuree(STATS_ENV_FINANCES)
    if not _freq and not _fin:
        return None, _stats_erreur(503, "stats_non_configurees", "Aucune clé de statistiques n'est posée sur ce serveur.")
    if _freq and _fin and hmac.compare_digest(_freq.encode("utf-8"), _fin.encode("utf-8")):
        # Deux clés IDENTIQUES : la clé « fréquentation » ouvrirait les finances.
        # Configuration refusée, rien n'est servi tant qu'elle n'est pas corrigée.
        logger.error("[STATS] %s et %s sont identiques : configuration refusée", STATS_ENV_FREQUENTATION, STATS_ENV_FINANCES)
        return None, _stats_erreur(503, "configuration_invalide",
                                   "Configuration invalide : les deux clés de statistiques doivent être différentes.")
    _auth = ((getattr(request, "headers", {}) or {}).get("Authorization")
             or (getattr(request, "headers", {}) or {}).get("authorization") or "").strip()
    _fournie = _auth.split(" ", 1)[1].strip() if _auth.lower().startswith("bearer ") else ""
    # Les DEUX comparaisons ont toujours lieu : le temps de réponse ne dit pas
    # laquelle des clés existe.
    _ok_fin = bool(_fin) and bool(_fournie) and hmac.compare_digest(_fournie.encode("utf-8"), _fin.encode("utf-8"))
    _ok_freq = bool(_freq) and bool(_fournie) and hmac.compare_digest(_fournie.encode("utf-8"), _freq.encode("utf-8"))
    if _ok_fin:
        return PORTEE_FINANCES, None
    if _ok_freq:
        return PORTEE_FREQUENTATION, None
    logger.warning("[STATS] accès refusé à /stats/association (clé %s)", "absente" if not _fournie else "invalide")
    return None, _stats_erreur(401, "cle_invalide", "Clé de statistiques absente ou invalide.")


def _stats_periode(mois: str, annee: str, granularite: str, maintenant):
    """(type, debut, fin, granularite, None) ou (None, …, réponse 400)."""
    # Aucun `.strip()` : un paramètre est en ASCII strict ou il est refusé.
    _m, _a = str(mois or ""), str(annee or "")
    if _m and _a:
        return None, None, None, None, _stats_erreur(400, "parametres", "mois=YYYY-MM OU annee=YYYY, pas les deux.")
    if _a:
        _r = _RE_ANNEE.fullmatch(_a)
        if not _r or not (2020 <= int(_a) <= 2100):
            return None, None, None, None, _stats_erreur(400, "parametres", "annee attendue : YYYY.")
        _type, (_d, _f) = "annee", bornes_periode("annee", maintenant, "", "", "%s-01" % _a)
    else:
        if _m:
            _r = _RE_MOIS.fullmatch(_m)
            if not _r or not (1 <= int(_r.group(2)) <= 12) or not (2020 <= int(_r.group(1)) <= 2100):
                return None, None, None, None, _stats_erreur(400, "parametres", "mois attendu : YYYY-MM.")
        _type, (_d, _f) = "mois", bornes_periode("mois", maintenant, "", "", _m)
    if _d is None or _f is None:
        return None, None, None, None, _stats_erreur(400, "parametres", "période illisible.")
    _g = str(granularite or "") or ("mois" if _type == "annee" else "semaine")
    if not _RE_GRANULARITE.fullmatch(_g) or _g not in ("jour", "semaine", "mois"):
        return None, None, None, None, _stats_erreur(400, "parametres", "granularite attendue : jour|semaine|mois.")
    return _type, _d, _f, _g, None


@stats_router.get("/association")
async def stats_association(request: Request, mois: str = "", annee: str = "", granularite: str = ""):
    """Les statistiques AGRÉGÉES de l'ensemble Afroboost, pour le Cockpit de
    l'association. Schéma `stats-association/1`. Lecture seule, aucune donnée
    personnelle (`verifier_anonymat` sur la réponse entière)."""
    from api.server import db
    from api.routes.reservation_routes import lot1_occurrence_iso
    from api.routes import analytics_shared as _A

    # Le débit par adresse : un FREIN (adresse falsifiable), pas une défense.
    if not _stats_debit_ok("ip:" + _stats_ip(request)):
        return _stats_erreur(429, "debit_depasse", "Trop de requêtes : réessayez dans une minute.",
                             {"Retry-After": str(int(STATS_DEBIT_FENETRE))})
    portee, refus = _stats_portee(request)
    if refus is not None:
        return refus
    _instant = datetime.now(timezone.utc)
    maintenant = vers_local(_instant)
    try:
        _type, debut, fin, _g, refus = _stats_periode(mois, annee, granularite, maintenant)
    except Exception:  # noqa: BLE001 — un paramètre hostile donne 400 JSON, jamais 500
        refus = _stats_erreur(400, "parametres", "paramètres illisibles.")
    if refus is not None:
        return refus
    _fuseau_ok = _A.fuseau_zurich_disponible()

    _cle_cache = (portee, _type, debut.strftime("%Y-%m-%d"), _g)
    _c = _STATS_CACHE.get(_cle_cache)
    if _c and _time.monotonic() - _c[0] < STATS_CACHE_TTL:
        return JSONResponse(content=_c[1], headers={"Cache-Control": "no-store", "X-Stats-Cache": "hit"})

    _genere = genere_le_stats(_instant, _A._ZURICH)
    try:
        sources = await _lire_sources(db, "")
    except Exception as _err:  # noqa: BLE001 — la base muette ne devient jamais un zéro
        logger.error("[STATS] base illisible (%s)", type(_err).__name__)
        return JSONResponse(content=reponse_base_indisponible(debut, fin, _type, _g, portee, _genere, _fuseau_ok),
                            headers={"Cache-Control": "no-store"})

    avert = []
    try:
        kpi, ctx = _coeur_kpi(sources, "", debut, fin, _g, "", maintenant, normaliser_occurrence=lot1_occurrence_iso)
        assoc = _projection_association(kpi, ctx, debut, fin, PERIMETRE_ENSEMBLE, maintenant)
    except Exception as _err:  # noqa: BLE001
        logger.error("[STATS] calcul impossible (%s)", type(_err).__name__)
        _r = reponse_base_indisponible(debut, fin, _type, _g, portee, _genere, _fuseau_ok)
        for _b in ("frequentation", "essais", "abonnements", "evolution"):
            _r[_b] = {"disponible": False, "raison": RAISON_ERREUR}
        if portee == PORTEE_FINANCES:
            _r["revenus"] = {"disponible": False, "raison": RAISON_ERREUR}
        _r["qualite"]["avertissements"] = [a for a in _r["qualite"]["avertissements"] if "base" not in a] + \
            ["Le calcul a échoué : aucun chiffre n'est servi."]
        return JSONResponse(content=_r, headers={"Cache-Control": "no-store"})

    # ── les bilans officiels : UNE lecture, jamais une écriture ──
    cloture, clotures_mois = None, {}
    try:
        if _type == "mois" and fin <= maintenant:
            _doc = await db[CLOTURE_COLLECTION].find_one({"cle": cle_cloture(debut.year, debut.month, "")}, {"_id": 0})
            if _doc and verifier_integrite(_doc):
                cloture = assoc_depuis_snapshot(_doc)
            elif _doc:
                avert.append(AVERT_CLOTURE_ALTEREE)
        elif _type == "annee" and _g == "mois":
            _cles = [cle_cloture(debut.year, _mo, "") for _mo in range(1, 13)]
            for _doc in await db[CLOTURE_COLLECTION].find({"cle": {"$in": _cles}}, {"_id": 0}).to_list(12):
                if verifier_integrite(_doc):
                    clotures_mois[(int(_doc.get("annee")), int(_doc.get("mois")))] = _doc.get("bilan") or {}
                else:
                    avert.append(AVERT_CLOTURE_ALTEREE)
    except Exception as _err:  # noqa: BLE001 — sans clôture lisible, on sert le dynamique et on le dit
        avert.append("Bilans clôturés illisibles (%s) : chiffres recalculés." % type(_err).__name__)
        cloture, clotures_mois = None, {}

    # ── le catalogue PUBLIC des cours (le filtre de `GET /api/courses`) : seul
    #    endroit d'où vient un libellé de séance ──
    cours_publics = {}
    try:
        for _c in await db.courses.find({"archived": {"$ne": True}}, {"_id": 0, "id": 1, "name": 1}).to_list(500):
            if _c.get("id") and str(_c.get("name") or "").strip():
                cours_publics[str(_c["id"])] = str(_c["name"]).strip()
    except Exception as _err:  # noqa: BLE001 — sans catalogue, toutes les séances s'appellent « Séance »
        avert.append("Catalogue des cours illisible (%s) : séances non nommées." % type(_err).__name__)
        cours_publics = {}
    reponse = construire_reponse(kpi, ctx, assoc, debut, fin, _type, _g, portee, maintenant, _genere,
                                 cloture=cloture, clotures_mois=clotures_mois, fuseau_ok=_fuseau_ok,
                                 avertissements_amont=avert, cours_publics=cours_publics)
    _fuites = verifier_anonymat(reponse)
    if _fuites:
        logger.error("[STATS] réponse refusée : donnée personnelle détectée %s", _fuites[:3])
        return _stats_erreur(500, "donnee_personnelle_detectee",
                             "Statistiques indisponibles : une donnée personnelle a été détectée et rien n'a été servi.")
    _STATS_CACHE[_cle_cache] = (_time.monotonic(), reponse)
    if len(_STATS_CACHE) > 200:
        for _k in list(_STATS_CACHE.keys())[:50]:
            _STATS_CACHE.pop(_k, None)
    return JSONResponse(content=reponse, headers={"Cache-Control": "no-store", "X-Stats-Cache": "miss"})
