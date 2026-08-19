# -*- coding: utf-8 -*-
"""R11 — valider une presence exige une identite prouvee.

Banc d'essai partage (`tests/_banc_qr.py`) : Mongo factice, extraction AST du
VRAI fichier `api/routes/reservation_routes.py`.
AUCUNE BASE REELLE, AUCUN RESEAU, AUCUNE DONNEE DE PRODUCTION.

Cette suite ne depend PAS du lot A0 : elle tourne telle quelle sur le commit
R11 seul comme sur R11 + A0.

Lancement :  python3 tests/test_r11_scan_auth.py
"""
import asyncio, io, os, sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RACINE, "tests"))
import _banc_qr as B

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def cours_du_moment(coach_id="coach.a@test", cid="cours-1"):
    """Le cours que la detection horaire du scan trouvera (fenetre +/-90 min).

    Necessaire sur le commit R11 SEUL : sans A0, le scan passe par la detection
    de cours avant d'atteindre la reservation du jour. Le rendre explicite ici
    fait que cette suite vaut sur les DEUX commits.
    """
    _m = B.datetime.now(B.TZ_CH)
    # A1/A1b : `courses.weekday` est en convention JAVASCRIPT (Dim=0), comme en
    # base. Cette fixture posait `_m.weekday()`, convention PYTHON (Lun=0) —
    # elle portait donc le decalage d'un jour que le lot A1 corrige. `%w` de la
    # bibliotheque standard donne exactement la convention JS, sans passer par
    # le code teste.
    return {"id": cid, "name": "Silent Mercredi", "time": _m.strftime("%H:%M"),
            "weekday": int(_m.strftime("%w")), "visible": True, "archived": False,
            "coach_id": coach_id}


async def principal():
    # ═══ 1. APPEL ANONYME REFUSE — sur les trois portes ═══════════════════
    for route, appel in (
        ("/qr/scan-validate", lambda ns: ns["_qr_scan_validate_inner"](B._Requete({"code": "AF0000001"}))),
        ("/reservations/{code}/validate", lambda ns: ns["validate_reservation"]("AF0000001", B._Requete({}))),
        ("/staff/validate", lambda ns: ns["staff_validate_reservation"](B._Requete({"code": "AF0000001"}))),
    ):
        db = B._Base()
        r = B.resa()
        db.reservations.docs.append(r)
        B.faux_shared(abonnement=B.forfait(remaining_sessions=5))
        ns = B.construire_routes(db, coach="")            # anonyme
        try:
            await appel(ns)
            verifier("1. %s : anonyme refuse" % route, False, "aucune exception")
        except B._HTTPException as e:
            verifier("1. %s : anonyme refuse (403)" % route, e.status_code == 403, "HTTP %s" % e.status_code)
        verifier("1b. %s : rien n'a ete ecrit" % route,
                 r["validated"] is False and not db.reservations.ecritures, "")

    # ═══ 2. COACH AUTHENTIFIE ET PROPRIETAIRE -> OK ═══════════════════════
    B.PRESENCES.clear()
    db = B._Base()
    r = B.resa(coach_id="coach.a@test")
    db.reservations.docs.append(r)
    db.courses.docs.append(cours_du_moment(r.get("coach_id", "")))
    B.faux_shared(abonnement=B.forfait(remaining_sessions=5))
    ns = B.construire_routes(db, coach="coach.a@test", admins=())
    rep = await ns["_qr_scan_validate_inner"](B._Requete({"code": "AFR-ESSAI1"}))
    verifier("2. coach authentifie ET proprietaire : presence validee",
             rep.get("success") and r["validated"] is True, rep.get("message", ""))

    # ═══ 3. QR d'une reservation payee : aucun debit ══════════════════════
    verifier("3. QR d'une reservation payee : aucun debit de seance",
             bool(r.get("validatedAt")) and not db.subscriptions.ecritures, "")

    # ═══ 4. QR invalide -> refus ══════════════════════════════════════════
    db = B._Base()
    B.faux_shared(abonnement=None)
    ns = B.construire_routes(db, coach="coach.a@test", admins=())
    try:
        await ns["_qr_scan_validate_inner"](B._Requete({"code": "CODE-INEXISTANT"}))
        verifier("4. QR invalide refuse", False, "aucune exception")
    except B._HTTPException as e:
        verifier("4. QR invalide refuse (404, pas 403)", e.status_code == 404, "HTTP %s" % e.status_code)

    # ═══ 5. double scan -> pas de second effet ════════════════════════════
    B.PRESENCES.clear()
    db = B._Base()
    r = B.resa(coach_id="coach.a@test")
    db.reservations.docs.append(r)
    db.courses.docs.append(cours_du_moment(r.get("coach_id", "")))
    B.faux_shared(abonnement=B.forfait(remaining_sessions=5))
    ns = B.construire_routes(db, coach="coach.a@test", admins=())
    await ns["_qr_scan_validate_inner"](B._Requete({"code": "AFR-ESSAI1"}))
    quand = r["validatedAt"]
    rep2 = await ns["_qr_scan_validate_inner"](B._Requete({"code": "AFR-ESSAI1"}))
    verifier("5. double scan : horodatage inchange, une seule presence",
             r["validatedAt"] == quand and len(B.PRESENCES) <= 1, str(B.PRESENCES))

    # ═══ 6. COACH AUTHENTIFIE MAIS NON PROPRIETAIRE -> REFUS ══════════════
    B.PRESENCES.clear()
    db = B._Base()
    r = B.resa(coach_id="coach.a@test")
    db.reservations.docs.append(r)
    db.courses.docs.append(cours_du_moment(r.get("coach_id", "")))
    B.faux_shared(abonnement=B.forfait(remaining_sessions=5))
    ns = B.construire_routes(db, coach="coach.b@test", admins=())
    try:
        await ns["_qr_scan_validate_inner"](B._Requete({"code": "AFR-ESSAI1"}))
        verifier("6. coach NON proprietaire refuse", False, "aucune exception")
    except B._HTTPException as e:
        verifier("6. coach NON proprietaire refuse (403)", e.status_code == 403, "HTTP %s" % e.status_code)
    verifier("6b. coach NON proprietaire : AUCUNE ecriture",
             r["validated"] is False and not B.PRESENCES, "")

    # ═══ 6c. super-admin : valide partout ═════════════════════════════════
    db = B._Base()
    r = B.resa(coach_id="coach.a@test")
    db.reservations.docs.append(r)
    db.courses.docs.append(cours_du_moment(r.get("coach_id", "")))
    B.faux_shared(abonnement=B.forfait(remaining_sessions=5))
    ns = B.construire_routes(db, coach="admin@test", admins=("admin@test",))
    rep = await ns["_qr_scan_validate_inner"](B._Requete({"code": "AFR-ESSAI1"}))
    verifier("6c. super-admin : valide le cours d'un autre coach",
             rep.get("success") and r["validated"] is True, "")

    # ═══ 6d. donnee orpheline (coach_id vide) : repli documente ═══════════
    db = B._Base()
    r = B.resa(coach_id="")
    db.reservations.docs.append(r)
    db.courses.docs.append(cours_du_moment(r.get("coach_id", "")))
    B.faux_shared(abonnement=B.forfait(remaining_sessions=5))
    ns = B.construire_routes(db, coach="coach.b@test", admins=())
    rep = await ns["_qr_scan_validate_inner"](B._Requete({"code": "AFR-ESSAI1"}))
    verifier("6d. reservation sans coach_id : validation possible (repli documente)",
             rep.get("success") and r["validated"] is True, "")

    # ═══ 7. occurrence recurrente : la bonne, et elle seule ═══════════════
    db = B._Base()
    jour = B.resa("AF-SEM1", coach_id="coach.a@test")
    suivante = B.resa("AF-SEM2", coach_id="coach.a@test",
                      datetime=B._a0_jour(7) + "T18:30:00")
    db.reservations.docs += [jour, suivante]
    db.courses.docs.append(cours_du_moment("coach.a@test"))
    B.faux_shared(abonnement=B.forfait(remaining_sessions=5))
    ns = B.construire_routes(db, coach="coach.a@test", admins=())
    await ns["_qr_scan_validate_inner"](B._Requete({"code": "AFR-ESSAI1"}))
    verifier("7. occurrence recurrente : celle du jour validee",
             jour["validated"] is True, "")
    verifier("7b. occurrence recurrente : celle de la semaine suivante JAMAIS touchee",
             suivante["validated"] is False, "")

    # ═══ 8. seance ponctuelle ═════════════════════════════════════════════
    db = B._Base()
    p = B.resa("AF-PONCT", coach_id="coach.a@test", courseName="Laff Festival")
    db.reservations.docs.append(p)
    B.faux_shared(abonnement=B.forfait(remaining_sessions=5))
    ns = B.construire_routes(db, coach="coach.a@test", admins=())
    rep = await ns["_qr_scan_validate_inner"](B._Requete({"code": "AF-PONCT"}))
    verifier("8. seance ponctuelle : presence validee par son code de reservation",
             p["validated"] is True, rep.get("message", ""))

    # ═══ 9. ESSAI / credit : aucune ecriture sur les forfaits ═════════════
    verifier("9. ESSAI et credits : aucune ecriture sur subscriptions",
             not db.subscriptions.ecritures, str(db.subscriptions.ecritures))
    verifier("9b. aucune ecriture sur discount_codes",
             not db.discount_codes.ecritures, str(db.discount_codes.ecritures))

    # ═══ 10. forfait a 0 credit NON falsifiable anonymement ═══════════════
    db = B._Base()
    r = B.resa(coach_id="coach.a@test")
    db.reservations.docs.append(r)
    B.faux_shared(abonnement=B.forfait(remaining_sessions=0))
    ns = B.construire_routes(db, coach="")               # anonyme
    try:
        await ns["_qr_scan_validate_inner"](B._Requete({"code": "AFR-ESSAI1"}))
        verifier("10. forfait a 0 credit : falsification anonyme refusee", False, "validee !")
    except B._HTTPException as e:
        verifier("10. forfait a 0 credit : falsification anonyme refusee (403)",
                 e.status_code == 403 and r["validated"] is False, "HTTP %s" % e.status_code)

    # ═══ 11. le frontend transmet bien l'auth existante ═══════════════════
    app = io.open(os.path.join(RACINE, "frontend", "src", "App.js"), encoding="utf-8").read()
    verifier("11a. intercepteur axios : Authorization Bearer <afroboost_jwt>",
             "localStorage.getItem('afroboost_jwt')" in app
             and "config.headers['Authorization'] = 'Bearer ' + jwt" in app, "")
    for f in ("components/CoachDashboard.js", "components/ChatWidget.js"):
        t = io.open(os.path.join(RACINE, "frontend", "src", f), encoding="utf-8").read()
        verifier("11b. %s : scan via l'axios global (donc intercepte)" % os.path.basename(f),
                 "qr/scan-validate" in t and "import axios" in t, "")
    verifier("11c. aucun ecran n'appelle les deux routes soeurs (rien a casser)",
             not any("staff/validate" in io.open(os.path.join(dp, fn), encoding="utf-8",
                                                 errors="ignore").read()
                     for dp, _, fns in os.walk(os.path.join(RACINE, "frontend", "src"))
                     for fn in fns if fn.endswith(".js")), "")

    # ═══ 12. la garde est bien AVANT toute lecture du corps ═══════════════
    corps = B.extraire("_qr_scan_validate_inner")
    verifier("12. garde R11 placee avant `await request.json()`",
             corps.index("_r11_scanneur(request)") < corps.index("await request.json()"), "")


def rapport():
    print("\n" + "=" * 74)
    print("R11 — AUTHENTIFICATION DU SCAN DE PRESENCE")
    print("=" * 74)
    ok = 0
    for nom, reussi, detail in RESULTATS:
        print(("  OK   " if reussi else "  ECHEC") + "  " + nom
              + (("  [%s]" % detail) if detail and not reussi else ""))
        ok += 1 if reussi else 0
    print("-" * 74)
    print("%d / %d verifications au vert" % (ok, len(RESULTATS)))
    return ok == len(RESULTATS)


if __name__ == "__main__":
    asyncio.run(principal())
    sys.exit(0 if rapport() else 1)
