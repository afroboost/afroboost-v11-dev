#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MT-5 — RÉSERVATIONS MULTI-COACH : identité signée + propriétaire réel.

Ce banc exécute les VRAIES routes de réservation (`api/routes/reservation_routes.py`
et `GET /reservations/ended-for-review` de `api/server.py`) sur le MongoDB EN
MÉMOIRE du banc `test_referral_pass_duo` (importé, jamais recopié), avec de VRAIS
JWT signés par le secret du banc.

Couvert :
  L. liste d'administration `GET /reservations` (paginée ET `all_data`) :
     A voit A / A ne voit pas B / B ne voit pas A / les DEUX super-admins voient
     A + B + plateforme + historique / anonyme 403 / X-User-Email seul 403 (même
     drapeau RESERVATIONS_JWT_STRICT à false) / JWT B + en-tête A -> reste B /
     jeton d'un non-coach 403 / pagination bornée ;
  M. mutations croisées (suivi, casque, validation, staff, absence, suppression,
     scan QR) : l'autre coach reçoit 404, le document est INTACT, aucun nom
     d'un client d'un autre coach ne fuit ; le propriétaire et le super-admin
     gardent la main ; anonyme et en-tête seul -> 403 ;
  E. export CSV des présences : borné au propriétaire, filtres échappés
     (aucune regex fabriquée depuis la requête) ;
  P. parcours publics légitimes : visiteur qui réserve un produit (sans aucune
     identité), abonné qui interroge `ended-for-review` avec SON code, éligibilité
     par code — sans fuite du document de code ni de l'identité d'un tiers.

AUCUN réseau, AUCUN e-mail réel, AUCUNE base réelle.

Lancement :  python3 tests/test_mt5_reservations.py
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)

import test_referral_pass_duo as H  # noqa: E402  (pose l'environnement du banc)

S = H.S
RR = H.RR
from fastapi import HTTPException  # noqa: E402

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


ADMIN = "contact.artboost@gmail.com"
ADMIN2 = "afroboost.bassi@gmail.com"
A = "coach.a@exemple.test"
B = "coach.b@exemple.test"


class Req(H.Requete):
    """La requête du banc, avec `body()` (lu par la route casque)."""

    async def body(self):
        import json as _json
        return _json.dumps(self._corps or {}).encode("utf-8")


def req(jeton_de=None, entete=None, corps=None, params=None):
    e = {}
    if jeton_de:
        e["Authorization"] = "Bearer " + H.jeton_admin(jeton_de)
    if entete:
        e["X-User-Email"] = entete
    return Req(corps if corps is not None else {}, e, params)


async def appel(coro):
    try:
        return 200, await coro
    except HTTPException as e:
        return e.status_code, e.detail


def _aujourdhui_ch():
    return (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%d")


def base_de_depart():
    base = H._Base()
    # Le drapeau historique à FALSE : la liste doit rester fermée à l'en-tête.
    base["feature_flags"].docs.append({"id": "feature_flags", "RESERVATIONS_JWT_STRICT": False})
    base["coaches"].docs += [{"email": A}, {"email": B}]
    base["courses"].docs += [
        {"id": "cours-A", "name": "Cours A", "coach_id": A, "time": "18:30"},
        {"id": "cours-B", "name": "Cours B", "coach_id": B, "time": "18:30"},
    ]
    jour = _aujourdhui_ch() + "T18:30:00"
    il_y_a_1h = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

    def resa(rid, code, nom, coach, **extra):
        d = {"id": rid, "reservationCode": code, "userName": nom,
             "userEmail": nom.lower().replace(" ", ".") + "@exemple.test",
             "userWhatsapp": "+41790000000", "courseName": "Cours", "datetime": jour,
             "offerName": "Offre", "totalPrice": 0, "quantity": 2, "validated": False,
             "createdAt": "2026-09-01T10:00:00+00:00", "isProduct": False}
        if coach is not None:
            d["coach_id"] = coach
        d.update(extra)
        return d

    base["reservations"].docs += [
        resa("rA1", "AFRA0001", "Client A1", A, courseId="cours-A", isProduct=True),
        resa("rA2", "AFRA0002", "Client A2", A, courseId="cours-A", validated=True,
             validatedAt="2026-09-01T18:31:00+00:00"),
        resa("rB1", "AFRB0001", "Client B1", B, courseId="cours-B"),
        resa("rB2", "AFRB0002", "Client B2", B, courseId="cours-B", validated=True,
             validatedAt="2026-09-01T18:32:00+00:00", promoCode="AFR-BBBBBB",
             datetime=il_y_a_1h),
        resa("rP", "AFRP0001", "Client Plateforme", ADMIN),
        resa("rO", "AFRO0001", "Client Historique", None),
    ]
    # Un code d'abonné de A (parcours abonné légitime de ended-for-review).
    base["discount_codes"].docs += [
        {"id": "dc-a", "code": "AFR-AAAAAA", "active": True, "maxUses": 10, "used": 1,
         "assignedEmail": "client.a2@exemple.test", "name": "Client A2", "coach_id": A},
        {"id": "dc-b", "code": "AFR-BBBBBB", "active": True, "maxUses": 10, "used": 1,
         "assignedEmail": "client.b2@exemple.test", "name": "Client B2", "coach_id": B},
        # Code valide SANS séance récente : sonder l'e-mail d'un tiers avec lui.
        {"id": "dc-c", "code": "AFR-CCCCCC", "active": True, "maxUses": 10, "used": 0,
         "assignedEmail": "client.c@exemple.test", "name": "Client C", "coach_id": A},
    ]
    base["reservations"].docs.append(
        resa("rA3", "AFRA0003", "Client A2", A, courseId="cours-A", promoCode="AFR-AAAAAA",
             datetime=il_y_a_1h, validated=True))
    for module in (S, RR):
        module.db = base
    return base


def resa_doc(base, rid):
    return next((r for r in base["reservations"].docs if r.get("id") == rid), None)


def noms(r):
    return sorted(x.get("userName") for x in (r or {}).get("data", []))


TOUS = sorted(["Client A1", "Client A2", "Client A2", "Client B1", "Client B2",
               "Client Plateforme", "Client Historique"])


# ─────────────────────────────────────────────────────────────────────────────
# L. Liste d'administration
# ─────────────────────────────────────────────────────────────────────────────
async def partie_liste():
    base_de_depart()
    for all_data in (False, True):
        m = "all_data" if all_data else "paginée"
        c, r = await appel(RR.get_reservations(req(A), 1, 20, all_data))
        verifier("L1. %s : A voit UNIQUEMENT ses réservations" % m,
                 c == 200 and noms(r) == ["Client A1", "Client A2", "Client A2"], (c, noms(r) if c == 200 else r))
        c, r = await appel(RR.get_reservations(req(B), 1, 20, all_data))
        verifier("L2. %s : B voit UNIQUEMENT les siennes (rien de A)" % m,
                 c == 200 and noms(r) == ["Client B1", "Client B2"], (c, noms(r) if c == 200 else r))
        for adm, n in ((ADMIN, "L3"), (ADMIN2, "L4")):
            c, r = await appel(RR.get_reservations(req(adm), 1, 20, all_data))
            verifier("%s. %s : super-admin %s -> global (A + B + plateforme + historique)" % (n, m, adm),
                     c == 200 and noms(r) == TOUS, (c, noms(r) if c == 200 else r))
        c, r = await appel(RR.get_reservations(req(), 1, 20, all_data))
        verifier("L5. %s : anonyme -> 403" % m, c == 403, (c, r))
        c, r = await appel(RR.get_reservations(req(entete=A), 1, 20, all_data))
        verifier("L6. %s : X-User-Email de A SANS jeton -> 403 (drapeau à false)" % m, c == 403, (c, r))
        c, r = await appel(RR.get_reservations(req(entete=ADMIN), 1, 20, all_data))
        verifier("L7. %s : X-User-Email super-admin SANS jeton -> 403" % m, c == 403, (c, r))
        c, r = await appel(RR.get_reservations(req(B, entete=A), 1, 20, all_data))
        verifier("L8. %s : JWT B + X-User-Email A -> reste B" % m,
                 c == 200 and noms(r) == ["Client B1", "Client B2"], (c, noms(r) if c == 200 else r))
        c, r = await appel(RR.get_reservations(req(B, entete=ADMIN), 1, 20, all_data))
        verifier("L9. %s : JWT B + X-User-Email super-admin -> reste B" % m,
                 c == 200 and noms(r) == ["Client B1", "Client B2"], (c, noms(r) if c == 200 else r))
        c, r = await appel(RR.get_reservations(req("inconnu@exemple.test"), 1, 20, all_data))
        verifier("L10. %s : jeton valide d'un non-coach -> 403" % m, c == 403, (c, r))
    c, r = await appel(RR.get_reservations(req(ADMIN), 1, 100000, False))
    verifier("L11. pagination bornée : limit=100000 ramené à 50 au plus",
             c == 200 and r["pagination"]["limit"] <= 50 and len(r["data"]) <= 50, (c, r if c != 200 else r["pagination"]))
    c, r = await appel(RR.get_reservations(req(ADMIN), 0, 20, False))
    verifier("L12. page=0 ne plante pas (ramenée à 1)", c == 200 and r["pagination"]["page"] == 1, (c, r if c != 200 else r["pagination"]))


# ─────────────────────────────────────────────────────────────────────────────
# M. Mutations croisées
# ─────────────────────────────────────────────────────────────────────────────
async def partie_mutations():
    # Suivi d'expédition
    base = base_de_depart()
    corps = {"trackingNumber": "PIRATE", "shippingStatus": "shipped"}
    c, r = await appel(RR.update_reservation_tracking("rA1", req(corps=corps)))
    verifier("M1. suivi : anonyme -> 403, intact", c == 403 and not resa_doc(base, "rA1").get("trackingNumber"), (c, r))
    c, r = await appel(RR.update_reservation_tracking("rA1", req(entete=A, corps=corps)))
    verifier("M2. suivi : X-User-Email du propriétaire sans jeton -> 403", c == 403, (c, r))
    c, r = await appel(RR.update_reservation_tracking("rA1", req(B, corps=corps)))
    verifier("M3. suivi : B sur la réservation de A -> 404, intact",
             c == 404 and not resa_doc(base, "rA1").get("trackingNumber"), (c, r))
    c, r = await appel(RR.update_reservation_tracking("rA1", req(A, corps={"trackingNumber": "CH123", "shippingStatus": "shipped"})))
    verifier("M4. suivi : propriétaire A -> 200", c == 200 and resa_doc(base, "rA1").get("trackingNumber") == "CH123", (c, r))
    c, r = await appel(RR.update_reservation_tracking("rB1", req(ADMIN2, corps={"trackingNumber": "ADM", "shippingStatus": "shipped"})))
    verifier("M5. suivi : 2e super-admin sur B -> 200", c == 200 and resa_doc(base, "rB1").get("trackingNumber") == "ADM", (c, r))
    c, r = await appel(RR.update_reservation_tracking("rO", req(A, corps=corps)))
    verifier("M6. suivi : réservation historique sans propriétaire -> 404 pour un coach", c == 404, (c, r))

    # Casque
    base = base_de_depart()
    c, r = await appel(RR.update_reservation_headphone_put("rA1", req(corps={"status": "taken"})))
    verifier("M7. casque : anonyme -> 403, intact", c == 403 and not resa_doc(base, "rA1").get("headphone_status"), (c, r))
    c, r = await appel(RR.update_reservation_headphone_post("AFRA0001", req(B, corps={"status": "taken"})))
    verifier("M8. casque : B sur A (par code) -> 404, intact",
             c == 404 and not resa_doc(base, "rA1").get("headphone_status"), (c, r))
    c, r = await appel(RR.update_reservation_headphone_patch("rA1", req(A, corps={"status": "taken"})))
    verifier("M9. casque : propriétaire A -> 200", c == 200 and resa_doc(base, "rA1").get("headphone_status") == "taken", (c, r))

    # Validation par code
    base = base_de_depart()
    c, r = await appel(RR.validate_reservation("AFRA0001", req(B)))
    verifier("M10. validate : B sur A -> 404, non validée", c == 404 and not resa_doc(base, "rA1").get("validated"), (c, r))
    c, r = await appel(RR.validate_reservation("AFRA0002", req(B)))
    verifier("M11. validate : B sur une réservation DÉJÀ validée de A -> 404 (aucun nom rendu)",
             c == 404 and "Client A2" not in str(r), (c, r))
    c, r = await appel(RR.validate_reservation("AFRA0001", req(A)))
    verifier("M12. validate : propriétaire A -> 200", c == 200 and resa_doc(base, "rA1").get("validated") is True, (c, r))

    # Staff
    base = base_de_depart()
    c, r = await appel(RR.staff_validate_reservation(req(B, corps={"code": "AFRA0002"})))
    verifier("M13. staff : B sur une réservation validée de A -> 404 (aucun nom rendu)",
             c == 404 and "Client A2" not in str(r), (c, r))
    c, r = await appel(RR.staff_validate_reservation(req(B, corps={"code": "AFRA0001"})))
    verifier("M14. staff : B sur A -> 404, non validée", c == 404 and not resa_doc(base, "rA1").get("validated"), (c, r))
    c, r = await appel(RR.staff_validate_reservation(req(B, corps={"code": "AFRB0001"})))
    verifier("M15. staff : B sur SA réservation -> 200", c == 200 and resa_doc(base, "rB1").get("validated") is True, (c, r))

    # Absence
    base = base_de_depart()
    c, r = await appel(RR.marquer_absence("rA1", req(B)))
    verifier("M16. absence : B sur A -> 404, rien d'écrit",
             c == 404 and not resa_doc(base, "rA1").get("absence_marked_at"), (c, r))
    c, r = await appel(RR.marquer_absence("rA1", req()))
    verifier("M17. absence : anonyme -> 403", c == 403, (c, r))

    # Suppression
    base = base_de_depart()
    c, r = await appel(RR.delete_reservation("rA1", req(B)))
    verifier("M18. suppression : B sur A -> 404, document présent", c == 404 and resa_doc(base, "rA1") is not None, (c, r))
    c, r = await appel(RR.delete_reservation("rA1", req(entete=A)))
    verifier("M19. suppression : X-User-Email seul -> 403, document présent",
             c == 403 and resa_doc(base, "rA1") is not None, (c, r))

    # Scan QR (CAS A : code de réservation)
    base = base_de_depart()
    c, r = await appel(RR.qr_scan_validate(req(B, corps={"code": "AFRA0002"})))
    verifier("M20. scan : B scanne une réservation DÉJÀ validée de A -> 404 (aucun nom rendu)",
             c == 404 and "Client A2" not in str(r), (c, r))
    c, r = await appel(RR.qr_scan_validate(req(B, corps={"code": "AFRA0001"})))
    verifier("M21. scan : B scanne une réservation de A -> 404, non validée",
             c == 404 and not resa_doc(base, "rA1").get("validated"), (c, r))
    c, r = await appel(RR.qr_scan_validate(req(corps={"code": "AFRA0001"})))
    verifier("M22. scan : anonyme -> 403", c == 403, (c, r))
    c, r = await appel(RR.qr_scan_validate(req(A, corps={"code": "AFRA0001"})))
    verifier("M23. scan : propriétaire A -> 200, validée",
             c == 200 and resa_doc(base, "rA1").get("validated") is True, (c, r))
    c, r = await appel(RR.qr_scan_validate(req(ADMIN2, corps={"code": "AFRB0001"})))
    verifier("M24. scan : 2e super-admin sur B -> 200", c == 200 and resa_doc(base, "rB1").get("validated") is True, (c, r))


# ─────────────────────────────────────────────────────────────────────────────
# E. Export CSV des présences
# ─────────────────────────────────────────────────────────────────────────────
async def _csv(reponse):
    morceaux = []
    async for m in reponse.body_iterator:
        morceaux.append(m if isinstance(m, str) else m.decode("utf-8"))
    return "".join(morceaux)


async def partie_export():
    base_de_depart()
    c, r = await appel(RR.export_attendance(req(A)))
    txt = await _csv(r) if c == 200 else ""
    verifier("E1. export : A n'exporte que ses présences",
             c == 200 and "Client A2" in txt and "Client B2" not in txt, (c, txt[:300]))
    c, r = await appel(RR.export_attendance(req()))
    verifier("E2. export : anonyme -> 403", c == 403, (c, r))
    c, r = await appel(RR.export_attendance(req(entete=ADMIN)))
    verifier("E3. export : X-User-Email super-admin sans jeton -> 403", c == 403, (c, r))
    c, r = await appel(RR.export_attendance(req(ADMIN), "", ".*"))
    txt = await _csv(r) if c == 200 else ""
    verifier("E4. export : filtre `.*` pris LITTÉRALEMENT (aucune regex fabriquée)",
             c == 200 and "Client" not in txt, (c, txt[:300]))
    c, r = await appel(RR.export_attendance(req(ADMIN)))
    txt = await _csv(r) if c == 200 else ""
    verifier("E5. export : super-admin -> global", c == 200 and "Client A2" in txt and "Client B2" in txt, (c, txt[:300]))


# ─────────────────────────────────────────────────────────────────────────────
# P. Parcours publics légitimes
# ─────────────────────────────────────────────────────────────────────────────
async def partie_public():
    base = base_de_depart()
    # ended-for-review
    q = lambda **p: Req({}, {}, p)  # noqa: E731
    c, r = await appel(S.reservations_ended_for_review(q(email="client.a2@exemple.test", code="AFR-AAAAAA")))
    verifier("P1. ended-for-review : abonné avec SON code -> séance détectée",
             c == 200 and r.get("has_ended_session") is True, (c, r))
    c, r = await appel(S.reservations_ended_for_review(q(email="client.b2@exemple.test", code="AFR-CCCCCC")))
    verifier("P2. ended-for-review : SON code valide (sans séance) + e-mail d'un client de B -> neutre",
             c == 200 and r.get("has_ended_session") is False, (c, r))
    _r = Req({}, {"X-User-Email": A}, {"email": "client.b2@exemple.test"})
    c, r = await appel(S.reservations_ended_for_review(_r))
    verifier("P3. ended-for-review : X-User-Email coach SANS jeton -> neutre (plus d'oracle)",
             c == 200 and r.get("has_ended_session") is False, (c, r))
    _r = Req({}, {"Authorization": "Bearer " + H.jeton_admin(A)}, {"email": "client.b2@exemple.test"})
    c, r = await appel(S.reservations_ended_for_review(_r))
    verifier("P4. ended-for-review : JWT A sur un client de B -> neutre",
             c == 200 and r.get("has_ended_session") is False, (c, r))
    _r = Req({}, {"Authorization": "Bearer " + H.jeton_admin(B)}, {"email": "client.b2@exemple.test"})
    c, r = await appel(S.reservations_ended_for_review(_r))
    verifier("P5. ended-for-review : JWT B sur SON client -> séance détectée",
             c == 200 and r.get("has_ended_session") is True, (c, r))

    # éligibilité (appel visiteur/abonné du ChatWidget, sans jeton)
    c, r = await appel(RR.check_reservation_eligibility(Req({"code": "AFR-AAAAAA", "email": "client.a2@exemple.test"}, {})))
    verifier("P6. éligibilité : code valide -> éligible, SANS le document de code (e-mail assigné)",
             c == 200 and r.get("eligible") is True and "client.a2@exemple.test" not in str(r)
             and "discount" not in r, (c, r))
    base["chat_participants"].docs.append({"id": "p1", "email": "abonne@exemple.test", "name": "Abonné Secret",
                                           "isSubscriber": True})
    c, r = await appel(RR.check_reservation_eligibility(Req({"email": "abonne@exemple.test"}, {})))
    verifier("P7. éligibilité : par e-mail -> éligible, SANS nom ni e-mail rendus",
             c == 200 and r.get("eligible") is True and "Abonné Secret" not in str(r), (c, r))

    # visiteur : création d'une réservation produit, sans aucune identité
    avant = len(base["reservations"].docs)
    corps = RR.ReservationCreate(userName="Visiteur", userEmail="visiteur@exemple.test",
                                 offerName="T-shirt", totalPrice=25.0, isProduct=True,
                                 coach_id=A, source="website")
    c, r = await appel(RR.create_reservation(corps, req()))
    cree = base["reservations"].docs[avant:] if len(base["reservations"].docs) > avant else []
    verifier("P8. visiteur : POST /reservations sans identité -> 200, attribuée au coach vérifié",
             c == 200 and cree and cree[0].get("coach_id") == A, (c, str(r)[:200]))


# ─────────────────────────────────────────────────────────────────────────────
# S. Scan d'un CODE (forfait / code collectif) d'un autre coach — MT-5b
# ─────────────────────────────────────────────────────────────────────────────
def _semer_codes(base):
    jour = _aujourdhui_ch() + "T18:30:00"
    fin = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
    for code, coach, email, nom in (("AFR-SUBA01", A, "sa1@exemple.test", "Sabine Abonnee"),
                                    ("AFR-SUBA02", A, "sa2@exemple.test", "Samuel Abonne"),
                                    ("AFR-SUBLEG", None, "sl@exemple.test", "Sylvie Legacy")):
        d = {"id": "sub-" + code, "code": code, "email": email, "name": nom, "status": "active",
             "total_sessions": 10, "used_sessions": 3, "remaining_sessions": 7, "expires_at": fin}
        if coach:
            d["coach_id"] = coach
        base["subscriptions"].docs.append(d)
    # réservations du jour SANS courseId (stock chat/website) : candidates A0
    base["reservations"].docs += [
        {"id": "rS1", "reservationCode": "AFRS0001", "userName": "Sabine Abonnee", "userEmail": "sa1@exemple.test",
         "promoCode": "AFR-SUBA01", "subscriptionId": "sub-AFR-SUBA01", "datetime": jour, "coach_id": A,
         "validated": True, "validatedAt": "2026-09-01T18:31:00+00:00", "createdAt": "2026-09-01T10:00:00+00:00"},
        {"id": "rS2", "reservationCode": "AFRS0002", "userName": "Samuel Abonne", "userEmail": "sa2@exemple.test",
         "promoCode": "AFR-SUBA02", "subscriptionId": "sub-AFR-SUBA02", "datetime": jour, "coach_id": A,
         "validated": False, "createdAt": "2026-09-01T10:00:00+00:00"},
        {"id": "rSL", "reservationCode": "AFRS000L", "userName": "Sylvie Legacy", "userEmail": "sl@exemple.test",
         "promoCode": "AFR-SUBLEG", "subscriptionId": "sub-AFR-SUBLEG", "datetime": jour, "coach_id": A,
         "validated": True, "validatedAt": "2026-09-01T18:31:00+00:00", "createdAt": "2026-09-01T10:00:00+00:00"},
    ]
    base["discount_codes"].docs += [
        {"id": "dc-grp", "code": "AFR-GRPA01", "active": True, "multi_member": True, "maxUses": 20,
         "used": 0, "assignedEmail": "payeur@exemple.test", "name": "Payeur Groupe", "coach_id": A},
        {"id": "dc-solo", "code": "AFR-SOLOA1", "active": True, "maxUses": 5, "used": 0,
         "assignedEmail": "solo@exemple.test", "name": "Solange Solo", "coach_id": A},
    ]
    base["code_members"].docs += [
        {"id": "m1", "code": "AFR-GRPA01", "slug": "mbr001", "name": "Mireille Membre",
         "email": "membre@exemple.test"},
    ]


def _fuite(r, *mots):
    t = str(r)
    return [m for m in mots if m in t]


async def partie_scan_codes():
    base = base_de_depart()
    _semer_codes(base)
    c, r = await appel(RR.qr_scan_validate(req(B, corps={"code": "AFR-SUBA01"})))
    verifier("S1. B scanne l'abonnement de A (réservation du jour VALIDÉE) -> 404 neutre, sans nom ni solde",
             c == 404 and not _fuite(r, "Sabine", "7", "remaining"), (c, r))
    c, r = await appel(RR.qr_scan_validate(req(B, corps={"code": "AFR-SUBA02"})))
    verifier("S2. B scanne l'abonnement de A (réservation NON validée) -> 404 neutre, rien validé",
             c == 404 and not _fuite(r, "Samuel", "remaining") and not resa_doc(base, "rS2").get("validated"), (c, r))
    c, r = await appel(RR.qr_scan_validate(req(B, corps={"code": "AFR-SUBLEG"})))
    verifier("S3. B scanne un forfait SANS coach_id dont la réservation du jour est à A -> jamais le nom/solde",
             c != 200 and not _fuite(r, "Sylvie", "remaining"), (c, r))
    c, r = await appel(RR.qr_scan_validate(req(A, corps={"code": "AFR-SUBA02"})))
    verifier("S4. témoin : A scanne SON abonné -> présence validée",
             c == 200 and resa_doc(base, "rS2").get("validated") is True, (c, r))
    c, r = await appel(RR.qr_scan_validate(req(ADMIN2, corps={"code": "AFR-SUBA01"})))
    verifier("S5. témoin : 2e super-admin -> « Déjà validé » (global)",
             c == 200 and "Déjà validé" in str(r), (c, r))
    # CAS C
    c, r = await appel(RR.qr_scan_validate(req(B, corps={"code": "AFR-GRPA01::mbr001"})))
    verifier("S6. B scanne le code COLLECTIF de A (membre) -> 404 neutre, sans nom de membre",
             c == 404 and not _fuite(r, "Mireille", "Payeur"), (c, r))
    c, r = await appel(RR.qr_scan_validate(req(B, corps={"code": "AFR-SOLOA1"})))
    verifier("S7. B scanne le code individuel de A -> 404 neutre, sans nom",
             c == 404 and not _fuite(r, "Solange"), (c, r))
    c, r = await appel(RR.qr_scan_validate(req(A, corps={"code": "AFR-SOLOA1"})))
    verifier("S8. témoin : A scanne son code sans réservation -> 404 AVEC le nom (il est à lui)",
             c == 404 and "Solange" in str(r), (c, r))

    # ended-for-review : membre d'un code collectif
    il_y_a_1h = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    base["reservations"].docs.append(
        {"id": "rG", "reservationCode": "AFRG0001", "userName": "Mireille Membre",
         "userEmail": "membre@exemple.test", "discountCode": "AFR-GRPA01", "member_slug": "mbr001",
         "courseName": "Cours Groupe", "datetime": il_y_a_1h, "coach_id": A, "validated": True})
    q = lambda **p: Req({}, {}, p)  # noqa: E731
    c, r = await appel(S.reservations_ended_for_review(q(email="membre@exemple.test", code="AFR-GRPA01")))
    verifier("S9. ended-for-review : MEMBRE d'un code collectif (réservation discountCode + e-mail) -> son avis",
             c == 200 and r.get("has_ended_session") is True, (c, r))
    base["reservations"].docs = [x for x in base["reservations"].docs if x.get("id") != "rG"]
    base["reservations"].docs.append(
        {"id": "rX", "reservationCode": "AFRX0001", "userName": "Tiers", "userEmail": "tiers@exemple.test",
         "courseName": "Cours X", "datetime": il_y_a_1h, "coach_id": B, "validated": True})
    c, r = await appel(S.reservations_ended_for_review(q(email="tiers@exemple.test", code="AFR-GRPA01")))
    verifier("S10. ended-for-review : code collectif + e-mail d'un NON-membre -> neutre (pas de sonde)",
             c == 200 and r.get("has_ended_session") is False, (c, r))


def main():
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())
    except Exception:
        pass
    boucle = asyncio.get_event_loop()
    for partie in (partie_liste, partie_mutations, partie_export, partie_public, partie_scan_codes):
        try:
            boucle.run_until_complete(partie())
        except Exception as e:  # une partie qui plante est un échec, pas un arrêt du banc
            import traceback
            traceback.print_exc()
            verifier("%s s'exécute sans exception" % partie.__name__, False, repr(e))
    ok = sum(1 for _, c, _ in RESULTATS if c)
    print("=" * 78)
    print("MT-5 — RÉSERVATIONS MULTI-COACH : %d vérifications" % len(RESULTATS))
    print("=" * 78)
    for nom, cond, detail in RESULTATS:
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom,
                               ("" if cond or not detail else "\n         -> " + str(detail)[:400])))
    print("-" * 78)
    print("%d / %d verifications au vert" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())
