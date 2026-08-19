# -*- coding: utf-8 -*-
"""A0 — le scan a l'entree dit la verite sur la presence.

Banc d'essai partage (`tests/_banc_qr.py`, introduit par R11) : Mongo factice,
extraction AST du VRAI fichier `api/routes/reservation_routes.py`.
AUCUNE BASE REELLE, AUCUN RESEAU, AUCUNE DONNEE DE PRODUCTION.

Le coach est authentifie pour toute la suite : A0 mesure le COMPORTEMENT du
scan, la securite est mesuree par `test_r11_scan_auth.py`.

Lancement :  python3 tests/test_a0_qr_presence.py
"""
import asyncio, os, sys
from datetime import datetime, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RACINE, "tests"))
import _banc_qr as B

TZ_CH = B.TZ_CH
_HTTPException = B._HTTPException
PRESENCES = B.PRESENCES
construire = B.construire
faux_shared = B.faux_shared
faux_api_server = B.faux_api_server
_a0_jour = B._a0_jour
aujourdhui = B.aujourdhui
resa = B.resa
forfait = B.forfait
scanner = B.scanner
extraire_source = B.extraire
_Base = B._Base
_Requete = B._Requete
_a0_horodatage_inutile = None

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


# ═════════════════════════════ LES TESTS ═════════════════════════════════════
async def principal():
    faux_api_server()          # coach authentifie pour toute la suite A0
    # ── 1. QR valide sur seance ponctuelle (essai gratuit, credit deja a 0) ──
    PRESENCES.clear()
    db = _Base()
    r = resa()
    db.reservations.docs.append(r)
    sub = forfait()
    faux_shared(abonnement=sub)
    ns = construire(db)
    rep = await scanner(ns, "AFR-ESSAI1")
    verifier("1. essai a 0 credit : presence validee au lieu d'un refus",
             rep.get("success") and db.reservations.docs[0]["validated"] is True,
             rep.get("message", ""))
    verifier("1b. aucun credit consomme",
             sub["remaining_sessions"] == 0 and not db.subscriptions.ecritures,
             "restant=%s" % sub["remaining_sessions"])
    verifier("1c. aucune seconde reservation creee",
             len(db.reservations.docs) == 1, "%d resa" % len(db.reservations.docs))
    verifier("1d. presence emise une fois dans le funnel",
             PRESENCES == [("AF0000001", False)], str(PRESENCES))

    # ── 2 & 3. cours recurrent : SEULE l'occurrence du jour est validee ──────
    PRESENCES.clear()
    db = _Base()
    occ_jour = resa("AF-SEM1", datetime=aujourdhui())
    occ_suivante = resa("AF-SEM2", datetime=_a0_jour(7) + "T18:30:00")
    db.reservations.docs += [occ_jour, occ_suivante]
    faux_shared(abonnement=forfait(remaining_sessions=0))
    ns = construire(db)
    rep = await scanner(ns, "AFR-ESSAI1")
    verifier("2. occurrence recurrente du jour validee",
             occ_jour["validated"] is True, rep.get("message", ""))
    verifier("3. l'occurrence de la semaine suivante reste INTACTE",
             occ_suivante["validated"] is False, str(occ_suivante["validated"]))

    # ── 4. mauvais QR -> refus net ──────────────────────────────────────────
    db = _Base()
    faux_shared(abonnement=None)
    ns = construire(db)
    try:
        await scanner(ns, "CODE-QUI-N-EXISTE-PAS")
        verifier("4. mauvais QR refuse", False, "aucune exception")
    except _HTTPException as e:
        verifier("4. mauvais QR refuse", e.status_code == 404, "HTTP %s" % e.status_code)

    # ── 5. double scan : idempotent, aucun second effet ─────────────────────
    PRESENCES.clear()
    db = _Base()
    r = resa()
    db.reservations.docs.append(r)
    faux_shared(abonnement=forfait())
    ns = construire(db)
    r1 = await scanner(ns, "AFR-ESSAI1")
    horodatage_1 = r["validatedAt"]
    r2 = await scanner(ns, "AFR-ESSAI1")
    verifier("5. 2e scan : reponse « Déjà validé »",
             "Déjà validé" in r2.get("message", ""), r2.get("message", ""))
    verifier("5b. 2e scan : validatedAt inchange",
             r["validatedAt"] == horodatage_1, "%s" % r["validatedAt"])
    verifier("5c. 2e scan : AUCUN second evenement de presence",
             PRESENCES == [("AF0000001", False)], str(PRESENCES))

    # ── 5bis. deux scans SIMULTANES : une seule presence ─────────────────────
    PRESENCES.clear()
    db = _Base()
    r = resa()
    db.reservations.docs.append(r)
    faux_shared(abonnement=forfait())
    ns = construire(db)
    a, b = await asyncio.gather(scanner(ns, "AFR-ESSAI1"), scanner(ns, "AFR-ESSAI1"))
    verifier("5d. scans concurrents : une seule presence emise",
             len(PRESENCES) == 1, str(PRESENCES))

    # ── 6. abonnement sans reservation du jour -> chemin historique ──────────
    db = _Base()
    faux_shared(abonnement=forfait(remaining_sessions=0),
                forfait_ok=(False, "Toutes les séances de ton abonnement ont été utilisées."))
    ns = construire(db)
    try:
        await scanner(ns, "AFR-ESSAI1")
        verifier("6. sans reservation ET sans credit : refus conserve", False, "pas d'exception")
    except _HTTPException as e:
        verifier("6. sans reservation ET sans credit : refus V393 conserve",
                 e.status_code == 400 and "séances" in str(e.detail), str(e.detail))

    # ── 7. essai gratuit : la presence est ce qui le consomme ───────────────
    PRESENCES.clear()
    db = _Base()
    r = resa(discountCode="AFR-ESSAI1", validated=False)
    db.reservations.docs.append(r)
    faux_shared(abonnement=forfait(total_sessions=1, remaining_sessions=0))
    ns = construire(db)
    await scanner(ns, "AFR-ESSAI1")
    verifier("7. essai : validated=True pose (etat « done » atteignable)",
             r.get("validated") is True and bool(r.get("validatedAt")), str(r.get("validatedAt")))

    # ── 8. forfait payant entame : comportement existant intact ─────────────
    PRESENCES.clear()
    db = _Base()
    r = resa("AF-PACK9", discountCode="PULSE10")
    db.reservations.docs.append(r)
    sub = forfait(code="PULSE10", remaining_sessions=9, total_sessions=10, used_sessions=1)
    faux_shared(abonnement=sub)
    ns = construire(db)
    rep = await scanner(ns, "PULSE10")
    verifier("8. pack entame : presence validee, message inchange pour le staff",
             rep.get("success") and rep.get("type") == "subscription", rep.get("message", ""))
    verifier("9. pack entame : credit NON debite une seconde fois",
             sub["remaining_sessions"] == 9 and not db.subscriptions.ecritures,
             "restant=%s" % sub["remaining_sessions"])
    verifier("10. presence enregistree une seule fois",
             len([e for e in db.reservations.ecritures if e[0] == "update"]) == 1,
             str(len(db.reservations.ecritures)))
    verifier("11. historique coherent : la reservation d'origine est conservee",
             db.reservations.docs[0]["reservationCode"] == "AF-PACK9"
             and len(db.reservations.docs) == 1, "")

    # ── A0-2 : le QR de l'e-mail de confirmation ────────────────────────────
    ns_url = construire(_Base())
    extraire_code = ns_url["_a0_code_depuis_qr"]
    cas = [
        ("https://afroboost.com/chat?code=AFR-EB04A1&res=AF1368C426", "AF1368C426",
         "URL de l'e-mail -> code de RESERVATION (occurrence exacte)"),
        ("https://afroboost.com/?qr=AFR-EB04A1", "AFR-EB04A1", "URL ?qr= (V156) inchangee"),
        ("AFR-EB04A1", "AFR-EB04A1", "code brut inchange"),
        ("AFR-EB04A1::marie", "AFR-EB04A1::marie", "code groupe inchange"),
        ("AF1368C426", "AF1368C426", "code de reservation brut inchange"),
    ]
    for entree, attendu, libelle in cas:
        obtenu = extraire_code(entree)
        verifier("A0-2 : %s" % libelle, obtenu == attendu, "%r -> %r" % (entree, obtenu))
    verifier("A0-2 : « AFROBOOST » n'est plus jamais extrait d'une URL",
             "AFROBOOST" not in extraire_code(cas[0][0]).upper(), "")

    # ── A0-2 : CAS A, garde d'occurrence ────────────────────────────────────
    PRESENCES.clear()
    db = _Base()
    vieille = resa("AF-VIEILLE", datetime=_a0_jour(-7) + "T18:30:00")
    db.reservations.docs.append(vieille)
    faux_shared(abonnement=None)
    ns = construire(db)
    try:
        await scanner(ns, "https://afroboost.com/chat?code=X&res=AF-VIEILLE")
        verifier("A0-2 : e-mail d'une AUTRE occurrence refuse", False, "pas d'exception")
    except _HTTPException as e:
        verifier("A0-2 : e-mail d'une AUTRE occurrence refuse",
                 e.status_code == 400 and vieille["validated"] is False, str(e.detail))

    # code BRUT d'une autre date : comportement d'AVANT conserve (aucune
    # regression pour le coach qui saisit un code a la main).
    PRESENCES.clear()
    db = _Base()
    tardive = resa("AF-TARDIVE", datetime=_a0_jour(-1) + "T18:30:00")
    db.reservations.docs.append(tardive)
    faux_shared(abonnement=None)
    ns = construire(db)
    rep = await scanner(ns, "AF-TARDIVE")
    verifier("A0-2 : code BRUT d'hier -> validation tardive toujours possible",
             rep.get("success") and tardive["validated"] is True, rep.get("message", ""))

    PRESENCES.clear()
    db = _Base()
    dujour = resa("AF-DUJOUR")
    db.reservations.docs.append(dujour)
    faux_shared(abonnement=None)
    ns = construire(db)
    rep = await scanner(ns, "https://afroboost.com/chat?code=X&res=AF-DUJOUR")
    verifier("A0-2 : e-mail de l'occurrence du JOUR valide la presence",
             rep.get("success") and dujour["validated"] is True, rep.get("message", ""))
    verifier("A0-3 : la presence du CAS A entre dans le funnel",
             PRESENCES == [("AF-DUJOUR", False)], str(PRESENCES))

    # ── deux seances le meme jour : la plus proche, jamais l'autre ──────────
    PRESENCES.clear()
    db = _Base()
    maintenant = datetime.now(TZ_CH)
    proche = resa("AF-PROCHE", datetime=maintenant.strftime("%Y-%m-%dT%H:%M:00"))
    lointaine = resa("AF-LOIN",
                     datetime=(maintenant - timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:00"))
    db.reservations.docs += [lointaine, proche]
    faux_shared(abonnement=forfait())
    ns = construire(db)
    await scanner(ns, "AFR-ESSAI1")
    verifier("12. deux seances le meme jour : la seance en cours est validee",
             proche["validated"] is True, "")
    verifier("12b. deux seances le meme jour : l'autre reste intacte",
             lointaine["validated"] is False, "")

    # ── aucune ecriture hors reservations ───────────────────────────────────
    verifier("13. ESSAI non regresse : aucune ecriture sur subscriptions",
             not db.subscriptions.ecritures, str(db.subscriptions.ecritures))
    verifier("14. aucune ecriture sur discount_codes (credits intacts)",
             not db.discount_codes.ecritures, str(db.discount_codes.ecritures))


def rapport():
    print("\n" + "=" * 74)
    print("A0 — SCAN QR / PRESENCE")
    print("=" * 74)
    ok = 0
    for nom, reussi, detail in RESULTATS:
        print(("  OK   " if reussi else "  ECHEC") + "  " + nom + (("  [%s]" % detail) if detail and not reussi else ""))
        ok += 1 if reussi else 0
    print("-" * 74)
    print("%d / %d verifications au vert" % (ok, len(RESULTATS)))
    return ok == len(RESULTATS)


if __name__ == "__main__":
    asyncio.run(principal())
    sys.exit(0 if rapport() else 1)
