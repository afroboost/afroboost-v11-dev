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
    est_cloturable, meta_snapshot,
)
from api.routes.shared import is_super_admin
from datetime import datetime, timezone
from fastapi.responses import Response

logger = logging.getLogger(__name__)
analytics_router = APIRouter(prefix="/analytics", tags=["analytics"])


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
    emails = {cle_participant(r.get("userEmail")) for r in reservations}
    emails.discard("")

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
                             normaliser_occurrence=lot1_occurrence_iso)
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
                                maintenant, cours_filtre=_cid)
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

    # ── PHASE 3 : la projection Association — mêmes tables, AUCUNE lecture de plus ──
    # La période précédente et les douze mois de l'année se calculent EN MÉMOIRE
    # sur les faits et les achats déjà chargés (tout l'historique) : le bilan
    # coûte 13 passes de plus sur quelques centaines de lignes, pas une requête.
    if _vue == "association":
        def _kpi_de(_d, _f):
            _k = calculer_kpi(faits, _d, _f, "mois")
            _k.update(calculer_kpi_finance(_achats["achats"], _achats["en_attente"], cartes, faits, _d, _f,
                                           "mois", maintenant, cours_filtre=_cid))
            return _k
        _pd, _pf = periode_precedente(debut, fin)
        _prec = _kpi_de(_pd, _pf)
        _annee = []
        _m = debut.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        for _i in range(12):
            _annee.append((_m, _kpi_de(_m, mois_suivant(_m))))
            _m = mois_suivant(_m)
        _libelle = PERIMETRE_ENSEMBLE
        if perimetre:
            # Le nom public du coach (concept.appName), jamais son adresse.
            _concept = await db.concept.find_one({"coach_id": perimetre}, {"_id": 0, "appName": 1})
            _nom = str((_concept or {}).get("appName") or "").strip()
            _libelle = "Coach " + (_nom or "(identité masquée)")
        assoc = projeter_association(kpi, _prec, _annee, debut, fin, _libelle, _cid, maintenant)
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
