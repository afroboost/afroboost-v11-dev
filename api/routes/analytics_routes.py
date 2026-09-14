# -*- coding: utf-8 -*-
"""ANALYTICS — LA route unique du cockpit. Lecture seule, JWT strict.

GET /api/analytics/cockpit?periode=aujourdhui|semaine|mois|annee|perso
                          &du=YYYY-MM-DD&au=YYYY-MM-DD
                          &coach_id=...&course_id=...&granularite=jour|semaine|mois

ISOLATION PAR LE SERVEUR. Le coach est tiré du JETON SIGNÉ (jamais de
`X-User-Email`, falsifiable). Un coach ne voit que `coach_id = son e-mail`,
et `coach_id` en paramètre lui est REFUSÉ s'il ne le désigne pas lui-même. Le
super-admin voit tout, ou un coach s'il le demande.

PERFORMANCE. Un nombre FIXE de requêtes (six), jamais une par participant :
réservations de cours du périmètre (tout l'historique — « nouveau » et
« fidélité » en ont besoin), cours, forfaits, codes, offres, cartes membres,
tous en `$in` sur les identifiants collectés. Puis tout se calcule en mémoire
(`analytics_shared`).
"""
import logging
from fastapi import APIRouter, HTTPException, Request

from api.routes.analytics_shared import (
    PERIODES, bornes_periode, calculer_kpi, cle_participant, construire_faits, vers_local,
)
from api.routes.shared import is_super_admin
from datetime import datetime, timezone

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


@analytics_router.get("/cockpit")
async def analytics_cockpit(request: Request, periode: str = "mois", du: str = "", au: str = "",
                            coach_id: str = "", course_id: str = "", granularite: str = "jour"):
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
    debut, fin = bornes_periode(_p, maintenant, du, au)
    if debut is None:
        raise HTTPException(status_code=400, detail="perso : du et au (YYYY-MM-DD, du <= au) requis")

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

    # ── 2..6. les documents liés, en $in ────────────────────────────────────
    cours = await db.courses.find({"id": {"$in": list(cids)}}, {"_id": 0, "id": 1, "name": 1,
                                  "weekday": 1, "locationName": 1, "location": 1}).to_list(5000) if cids else []
    forfaits = await db.subscriptions.find(
        {"$or": [{"id": {"$in": list(sids)}}, {"code": {"$in": list(codes)}}]},
        {"_id": 0}).to_list(20000) if (sids or codes) else []
    fiches = await db.discount_codes.find({"code": {"$in": list(codes)}}, {"_id": 0}).to_list(20000) if codes else []
    oids = {str(f.get("offer_id") or "").strip() for f in forfaits}
    oids.discard("")
    offres = await db.offers.find({"id": {"$in": list(oids)}}, {"_id": 0, "id": 1, "price": 1}).to_list(1000) if oids else []
    cartes = await db.memberships.find({"email": {"$in": list(emails)}}, {"_id": 0, "email": 1, "date_fin": 1}).to_list(20000) if emails else []

    cours_par_id = {c["id"]: c for c in cours if c.get("id")}
    forfaits_par_id = {f["id"]: f for f in forfaits if f.get("id")}
    forfaits_par_code = {}
    for f in forfaits:
        k = str(f.get("code") or "").strip().upper()
        if k and k not in forfaits_par_code:
            forfaits_par_code[k] = f
    codes_par_code = {}
    for f in fiches:
        k = str(f.get("code") or "").strip().upper()
        if k and k not in codes_par_code:
            codes_par_code[k] = f
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
    kpi["requetes"] = 6
    return kpi
