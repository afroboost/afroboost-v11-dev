# -*- coding: utf-8 -*-
"""A1 — LE SCAN VALIDE UNE OCCURRENCE REELLE, PAS « UN COURS ».

Trois defauts, un seul invariant : « le scan constate LA seance du jour, et
n'en debite qu'une ».

  A1-1  `courses.weekday` est en convention JAVASCRIPT (Dim=0), le scanner
        l'interrogeait en convention PYTHON (Lun=0) -> un jour de decalage.
  A1-2  un cours a DATE FIXE etait traite comme un cours hebdomadaire : le
        « Diner canadien » du 09/08 restait selectionnable tous les dimanches,
        et le choix manuel acceptait N'IMPORTE QUEL cours du catalogue.
  A1-3  la reservation creee etait datee de l'INSTANT DU SCAN, donc ne
        designait aucune occurrence.

Banc d'essai partage (`_banc_qr`) : Mongo factice, extraction AST du VRAI
fichier de routes. AUCUNE BASE REELLE, AUCUN RESEAU.

L'oracle du jour de la semaine n'est PAS le code teste : c'est `%w` de la
bibliotheque standard, qui vaut Dimanche=0 — exactement la convention
JavaScript. Les deux sont calcules independamment.
"""
import asyncio, sys, os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._banc_qr import (  # noqa: E402
    RESULTATS, TZ_CH, verifier, construire, faux_shared, faux_api_server,
    scanner, resa, forfait, cours, aujourdhui, _Base, COACH_TEST, _HTTPException,
)


def _jour_iso(decalage=0):
    return (datetime.now(TZ_CH) + timedelta(days=decalage)).strftime("%Y-%m-%d")


def _js_aujourdhui():
    """Convention JavaScript du jour courant, via `%w` (Dim=0) — oracle
    independant du code teste."""
    return int(datetime.now(TZ_CH).strftime("%w"))


def _heure(decalage_min=0):
    return (datetime.now(TZ_CH) + timedelta(minutes=decalage_min)).strftime("%H:%M")


def _base(courses_docs, sub=None, resas=None):
    db = _Base()
    db.courses.docs = list(courses_docs)
    db.reservations.docs = list(resas or [])
    if sub:
        db.subscriptions.docs = [sub]
    return db


# ═══════════════════ 1. A1-1 — LA CONVENTION DU JOUR ════════════════════════
def test_convention_jour():
    faux_shared()
    ns = construire(_Base())
    _js = ns["_a1_jour_js"]

    # Preuve par les DATES, pas par le code : sept jours consecutifs compares a
    # `%w`. Si la formule etait celle de Python, les sept echoueraient.
    ok = True
    detail = ""
    for d in range(7):
        _d = datetime(2026, 8, 17) + timedelta(days=d)   # 17/08/2026 = un lundi
        attendu = int(_d.strftime("%w"))
        if _js(_d) != attendu:
            ok = False
            detail += "%s: %d != %d " % (_d.date(), _js(_d), attendu)
    verifier("1. A1-1 convention JS (Dim=0) sur 7 jours consecutifs", ok, detail)

    # Les deux cas qui l'ont fait echouer en production.
    verifier("1b. vendredi 21/08/2026 -> 5 (et non 4, valeur Python)",
             _js(datetime(2026, 8, 21)) == 5, str(_js(datetime(2026, 8, 21))))
    verifier("1c. dimanche 23/08/2026 -> 0 (et non 6, valeur Python)",
             _js(datetime(2026, 8, 23)) == 0, str(_js(datetime(2026, 8, 23))))

    # Inverse EXACT de la conversion V196 (`py = (js - 1) % 7`).
    verifier("1d. reciproque de V196 verifiee sur les 7 jours",
             all(((_js(datetime(2026, 8, 17) + timedelta(days=d)) - 1) % 7)
                 == (datetime(2026, 8, 17) + timedelta(days=d)).weekday()
                 for d in range(7)), "")


# ═══════════════ 2. A1-2 — « A LIEU AUJOURD'HUI » ═══════════════════════════
def test_a_lieu_aujourdhui():
    faux_shared()
    ns = construire(_Base())
    f = ns["_a1_a_lieu_aujourdhui"]
    jour, js = _jour_iso(), _js_aujourdhui()

    verifier("2. recurrent du bon jour : retenu",
             f(cours(weekday=js), jour, js) is True, "")
    verifier("2b. recurrent d'un autre jour : ecarte",
             f(cours(weekday=(js + 3) % 7), jour, js) is False, "")
    verifier("2c. ponctuel date d'aujourd'hui : retenu",
             f(cours(date=jour, weekday=(js + 3) % 7), jour, js) is True,
             "la date fixe prime sur weekday")
    verifier("2d. ponctuel DEJA PASSE : ecarte meme si weekday concorde",
             f(cours(date=_jour_iso(-7), weekday=js), jour, js) is False,
             "c'est le « Diner canadien » du 09/08 qui revenait chaque dimanche")
    verifier("2e. ponctuel a venir : ecarte aujourd'hui",
             f(cours(date=_jour_iso(3), weekday=js), jour, js) is False, "")
    verifier("2f. date horodatee (ISO long) : comparee sur 10 caracteres",
             f(cours(date=jour + "T18:30:00", weekday=(js + 2) % 7), jour, js) is True, "")
    verifier("2g. weekday illisible : ecarte, jamais d'exception",
             f(cours(weekday=None), jour, js) is False, "")
    verifier("2h. weekday texte non numerique : ecarte",
             f(cours(weekday="mercredi"), jour, js) is False, "")


# ═══════════════ 3. A1-1 — L'ETIQUETTE AFFICHEE ═════════════════════════════
def test_etiquette():
    faux_shared()
    ns = construire(_Base())
    e = ns["_a1_etiquette"]

    # Le dimanche 23/08/2026 : le tableau ['Lun'..'Dim'] indexe par weekday=0
    # affichait « Lun ». C'est le bug vu a l'ecran par le coach.
    verifier("3. cours du dimanche etiquete « Dim » (et non « Lun »)",
             e(cours(date="2026-08-23", time="10:30"), "2026-08-23", 0).startswith("Dim"),
             e(cours(date="2026-08-23", time="10:30"), "2026-08-23", 0))
    verifier("3b. cours du vendredi etiquete « Ven » (et non « Sam »)",
             e(cours(date="2026-08-21", time="19:00"), "2026-08-21", 5).startswith("Ven"),
             e(cours(date="2026-08-21", time="19:00"), "2026-08-21", 5))
    verifier("3c. l'heure du cours figure dans l'etiquette",
             "10:30" in e(cours(date="2026-08-23", time="10:30"), "2026-08-23", 0), "")
    verifier("3d. cours sans heure : etiquette quand meme lisible",
             e(cours(date="2026-08-23", time=""), "2026-08-23", 0).strip() == "Dim", "")


# ═══════════════ 4. A1-3 — L'HORODATAGE DE L'OCCURRENCE ═════════════════════
def test_datetime_occurrence():
    faux_shared()
    ns = construire(_Base())
    d = ns["_a1_datetime_occurrence"]
    maintenant = datetime.now(TZ_CH)

    verifier("4. l'occurrence porte la date du jour ET l'heure du COURS",
             d(cours(time="18:30"), "2026-08-19", maintenant) == "2026-08-19T18:30:00",
             d(cours(time="18:30"), "2026-08-19", maintenant))
    verifier("4b. heure a un chiffre normalisee sur deux",
             d(cours(time="9:05"), "2026-08-19", maintenant) == "2026-08-19T09:05:00", "")
    verifier("4c. format NAIF local (aucun fuseau) — convention V196",
             "+" not in d(cours(time="18:30"), "2026-08-19", maintenant), "")
    verifier("4d. heure absente : repli sur l'instant du scan, jamais d'exception",
             d(cours(time=""), "2026-08-19", maintenant).startswith(
                 maintenant.strftime("%Y-%m-%dT")), "")
    verifier("4e. heure aberrante (99:99) : repli, pas de date impossible",
             d(cours(time="99:99"), "2026-08-19", maintenant).startswith(
                 maintenant.strftime("%Y-%m-%dT")), "")


# ═════════ 5. LA ROUTE — LE SELECTEUR NE PROPOSE QUE LE JOUR ════════════════
async def test_route_selecteur():
    js = _js_aujourdhui()
    aujourdhui = cours(id="c-jour", name="Silent du jour", weekday=js, time=_heure(300))
    autre_jour = cours(id="c-autre", name="Silent d'un autre jour", weekday=(js + 3) % 7)
    ponctuel_passe = cours(id="c-passe", name="Diner canadien", weekday=js, date=_jour_iso(-10))
    sub = forfait(remaining_sessions=5, total_sessions=10, used_sessions=5,
                  coach_id=COACH_TEST)

    db = _base([aujourdhui, autre_jour, ponctuel_passe], sub=sub)
    faux_shared(abonnement=sub)
    faux_api_server(COACH_TEST)
    ns = construire(db)

    try:
        await scanner(ns, "AFR-ESSAI1")
        verifier("5. 422 attendu quand aucun cours n'est a l'heure", False, "aucune exception")
    except _HTTPException as e:
        d = e.detail if isinstance(e.detail, dict) else {}
        ids = [c["id"] for c in d.get("courses", [])]
        verifier("5. 422 no_course_now conserve", e.status_code == 422
                 and d.get("error") == "no_course_now", str(e.detail))
        verifier("5b. la liste de secours vient du SERVEUR", "courses" in d, str(d))
        verifier("5c. le cours du jour y figure", "c-jour" in ids, str(ids))
        verifier("5d. le cours d'un AUTRE jour n'y figure pas", "c-autre" not in ids, str(ids))
        verifier("5e. le ponctuel DEJA PASSE n'y figure pas", "c-passe" not in ids, str(ids))
        verifier("5f. chaque entree porte une etiquette prete a afficher",
                 all(c.get("label") for c in d.get("courses", [])), str(d.get("courses")))

    verifier("5g. un 422 n'ecrit RIEN sur les reservations", not db.reservations.ecritures, "")
    verifier("5h. un 422 ne debite AUCUNE seance", not db.subscriptions.ecritures, "")


# ═════════ 6. LA ROUTE — LE CHOIX MANUEL EST BORNE AU JOUR ══════════════════
async def test_route_choix_manuel():
    js = _js_aujourdhui()
    aujourdhui = cours(id="c-jour", weekday=js, time=_heure(300))
    autre_jour = cours(id="c-autre", weekday=(js + 3) % 7)
    ponctuel_passe = cours(id="c-passe", weekday=js, date=_jour_iso(-10))
    sub = forfait(remaining_sessions=5, total_sessions=10, used_sessions=5,
                  coach_id=COACH_TEST)

    # ── un cours d'un AUTRE jour : refus, et surtout aucun debit ────────────
    db = _base([aujourdhui, autre_jour, ponctuel_passe], sub=sub)
    faux_shared(abonnement=sub)
    faux_api_server(COACH_TEST)
    ns = construire(db)
    try:
        await scanner(ns, "AFR-ESSAI1", courseId="c-autre")
        verifier("6. cours d'un autre jour : refus attendu", False, "accepte !")
    except _HTTPException as e:
        verifier("6. cours d'un autre jour force : refuse (400)", e.status_code == 400, str(e.detail))
    verifier("6b. refus : AUCUNE reservation creee", not db.reservations.ecritures,
             str(db.reservations.ecritures))
    verifier("6c. refus : AUCUNE seance debitee", not db.subscriptions.ecritures,
             str(db.subscriptions.ecritures))
    verifier("6d. refus : le solde du forfait est intact",
             db.subscriptions.docs[0]["remaining_sessions"] == 5, "")

    # ── un ponctuel deja passe : meme refus ────────────────────────────────
    db = _base([aujourdhui, autre_jour, ponctuel_passe], sub=sub)
    faux_shared(abonnement=sub)
    ns = construire(db)
    try:
        await scanner(ns, "AFR-ESSAI1", courseId="c-passe")
        verifier("6e. ponctuel passe force : refus attendu", False, "accepte !")
    except _HTTPException as e:
        verifier("6e. ponctuel deja passe force : refuse (400)", e.status_code == 400, str(e.detail))
    verifier("6f. ponctuel passe : aucune seance debitee", not db.subscriptions.ecritures, "")

    # ── un identifiant inexistant : 404, distinct du refus metier ──────────
    db = _base([aujourdhui], sub=sub)
    faux_shared(abonnement=sub)
    ns = construire(db)
    try:
        await scanner(ns, "AFR-ESSAI1", courseId="c-nexiste-pas")
        verifier("6g. cours inconnu : refus attendu", False, "accepte !")
    except _HTTPException as e:
        verifier("6g. cours inconnu : 404 (distinct du 400 metier)", e.status_code == 404, str(e.detail))


# ═════════ 7. LA ROUTE — LE CHEMIN LEGITIME MARCHE ENCORE ═══════════════════
async def test_route_chemin_legitime():
    js = _js_aujourdhui()
    du_jour = cours(id="c-jour", name="Silent du jour", weekday=js, time=_heure(300))
    sub = forfait(remaining_sessions=5, total_sessions=10, used_sessions=5,
                  coach_id=COACH_TEST)
    db = _base([du_jour], sub=sub)
    faux_shared(abonnement=sub)
    faux_api_server(COACH_TEST)
    ns = construire(db)

    r = await scanner(ns, "AFR-ESSAI1", courseId="c-jour")
    verifier("7. cours DU JOUR force : la validation aboutit", r.get("success") is True, str(r))
    verifier("7b. une reservation est creee", len(db.reservations.docs) == 1,
             str(len(db.reservations.docs)))

    creee = db.reservations.docs[0]
    attendu = _jour_iso() + "T" + du_jour["time"] + ":00"
    verifier("7c. A1-3 : la reservation porte L'OCCURRENCE, pas l'heure du scan",
             creee.get("datetime") == attendu, "%s != %s" % (creee.get("datetime"), attendu))
    verifier("7d. elle designe bien LE cours choisi", creee.get("courseId") == "c-jour", "")
    verifier("7e. elle est marquee presente (le scan constate une presence)",
             creee.get("validated") is True, "")
    verifier("7f. EXACTEMENT une seance debitee",
             db.subscriptions.docs[0]["remaining_sessions"] == 4, "")
    verifier("7g. le compteur d'utilisation suit",
             db.subscriptions.docs[0]["used_sessions"] == 6, "")

    # ── second scan : A0 prend le relais, aucun second debit ───────────────
    ns2 = construire(db)
    r2 = await scanner(ns2, "AFR-ESSAI1", courseId="c-jour")
    verifier("7h. second scan : accepte sans erreur", r2.get("success") is True, str(r2))
    verifier("7i. DEBIT UNIQUE : le solde n'a pas rebouge",
             db.subscriptions.docs[0]["remaining_sessions"] == 4,
             str(db.subscriptions.docs[0]["remaining_sessions"]))
    verifier("7j. aucune seconde reservation", len(db.reservations.docs) == 1,
             str(len(db.reservations.docs)))


# ═════════ 8. LA ROUTE — AUTO-DETECTION A L'HEURE DU COURS ══════════════════
async def test_route_auto_detection():
    js = _js_aujourdhui()
    maintenant = cours(id="c-now", name="Cours en cours", weekday=js, time=_heure(0))
    autre_jour = cours(id="c-autre", weekday=(js + 3) % 7, time=_heure(0))
    sub = forfait(remaining_sessions=5, total_sessions=10, used_sessions=5,
                  coach_id=COACH_TEST)
    db = _base([maintenant, autre_jour], sub=sub)
    faux_shared(abonnement=sub)
    faux_api_server(COACH_TEST)
    ns = construire(db)

    r = await scanner(ns, "AFR-ESSAI1")
    verifier("8. auto-detection : le cours de l'heure est retenu", r.get("success") is True, str(r))
    verifier("8b. c'est bien le cours DU JOUR, pas son homonyme d'un autre jour",
             db.reservations.docs and db.reservations.docs[0].get("courseId") == "c-now",
             str(db.reservations.docs))
    verifier("8c. un seul debit", db.subscriptions.docs[0]["remaining_sessions"] == 4, "")


# ═════════ 9. NON-REGRESSION A0 — LA PRESENCE AVANT LE CREDIT ═══════════════
async def test_non_regression_a0():
    js = _js_aujourdhui()
    du_jour = cours(id="c-jour", weekday=js, time=_heure(0))
    sub = forfait(remaining_sessions=5, total_sessions=10, used_sessions=5,
                  coach_id=COACH_TEST)
    deja = resa(code="AF-DEJA", courseId="c-jour",
                datetime=_jour_iso() + "T" + du_jour["time"] + ":00",
                validated=False, promoCode="AFR-ESSAI1", subscriptionId="sub-1")
    db = _base([du_jour], sub=sub, resas=[deja])
    faux_shared(abonnement=sub)
    faux_api_server(COACH_TEST)
    ns = construire(db)

    r = await scanner(ns, "AFR-ESSAI1")
    verifier("9. A0 non regresse : la reservation existante est validee",
             db.reservations.docs[0]["validated"] is True, str(r))
    verifier("9b. A0 non regresse : AUCUN credit debite (deja paye a la reservation)",
             db.subscriptions.docs[0]["remaining_sessions"] == 5,
             str(db.subscriptions.docs[0]["remaining_sessions"]))
    verifier("9c. A0 non regresse : aucune reservation en double",
             len(db.reservations.docs) == 1, str(len(db.reservations.docs)))


# ═════════ 10. LE CODE SOURCE — PLUS AUCUNE CONVENTION LOCALE ═══════════════
def test_source():
    import io
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    routes = io.open(os.path.join(racine, "api", "routes", "reservation_routes.py"),
                     encoding="utf-8").read()
    verifier("10. le scanner n'interroge plus Mongo avec `now_swiss.weekday()`",
             "today_weekday = now_swiss.weekday()" not in routes, "")
    verifier("10b. le choix manuel n'accepte plus n'importe quel cours du catalogue",
             'find_one({"id": forced_course_id, "archived": False}' not in routes, "")

    for nom, chemin in (("CoachDashboard.js", ("frontend", "src", "components", "CoachDashboard.js")),
                        ("ChatWidget.js", ("frontend", "src", "components", "ChatWidget.js"))):
        src = io.open(os.path.join(racine, *chemin), encoding="utf-8").read()
        verifier("10c. %s : plus de tableau de jours local dans le selecteur de scan" % nom,
                 "['Lun','Mar','Mer','Jeu','Ven','Sam','Dim']" not in src
                 and "['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']" not in src, "")
        verifier("10d. %s : le selecteur consomme `detail.courses` du serveur" % nom,
                 "detail.courses" in src, "")

    chat = io.open(os.path.join(racine, "frontend", "src", "components", "ChatWidget.js"),
                   encoding="utf-8").read()
    debut = chat.index("if (status === 422 && typeof detail === 'object' && detail && detail.error === 'no_course_now')")
    bloc = chat[debut:debut + 900]
    verifier("10e. ChatWidget : le bloc modifie reste en ES5 (var / function)",
             " const " not in bloc and " let " not in bloc and "=>" not in bloc, bloc[:120])



# ═════ 11. A1b — UNE RESERVATION HISTORIQUE NE REDEVIENT PAS UNE SEANCE ═════
#
# Constate en production le 19/08/2026 : le scan de BASSBOOSTX-11 repondait
# « Deja valide — Diner canadien », alors que « Diner canadien » est un cours
# PONCTUEL du 09/08. A1 protegeait la CREATION ; l'APPARIEMENT — quelles
# reservations existantes comptent comme presence du jour — n'avait aucune garde.
async def test_a1b_garde_appariement():
    js = _js_aujourdhui()
    du_jour = cours(id="c-jour", name="Silent du jour", weekday=js, time=_heure(0))
    # Le cas reel : un ponctuel du passe, TOUJOURS present, TOUJOURS visible,
    # TOUJOURS non archive — c'est exactement l'etat de « Diner canadien ».
    diner = cours(id="c-diner", name="Dîner canadien", weekday=js,
                  date=_jour_iso(-10), time="12:00", visible=True, archived=False)
    archive = cours(id="c-arch", name="Session Cardio", weekday=js, archived=True)
    masque = cours(id="c-masq", name="Cours masqué", weekday=js, time=_heure(0), visible=False)
    sub = forfait(remaining_sessions=5, total_sessions=10, used_sessions=5, coach_id=COACH_TEST)
    faux_shared(abonnement=sub)
    faux_api_server(COACH_TEST)

    async def filtre(db, resas):
        return await construire(db)["_a1b_occurrences_reelles"](resas)

    # ── le cas terrain, a l'identique ───────────────────────────────────────
    db = _base([du_jour, diner], sub=sub)
    fupq = resa(code="AFRO-FUPQ", courseId="c-diner", courseName="Dîner canadien",
                datetime=aujourdhui("10:16"), validated=True, promoCode="BASSBOOSTX-11")
    verifier("11. AFRO-FUPQ / « Dîner canadien » : ECARTEE du scan du jour",
             await filtre(db, [fupq]) == [], "elle est encore candidate")

    # ── et le scan complet ne la ressort plus ──────────────────────────────
    db = _base([du_jour, diner], sub=sub, resas=[dict(fupq)])
    ns = construire(db)
    r = await scanner(ns, "AFR-ESSAI1")
    verifier("11b. le scan ne repond plus « Déjà validé » sur un cours d'un autre jour",
             r.get("message") != "Déjà validé", str(r.get("message")))
    verifier("11c. il bascule sur le cours qui a REELLEMENT lieu aujourd'hui",
             db.reservations.docs[-1].get("courseId") == "c-jour",
             str(db.reservations.docs[-1].get("courseId")))
    verifier("11d. la reservation historique n'est PAS modifiee",
             db.reservations.docs[0].get("reservationCode") == "AFRO-FUPQ"
             and db.reservations.docs[0].get("validated") is True, "")
    verifier("11e. AUCUNE suppression : elle reste en base pour l'historique",
             any(x.get("reservationCode") == "AFRO-FUPQ" for x in db.reservations.docs), "")

    # ── les autres motifs d'exclusion ──────────────────────────────────────
    db = _base([du_jour, diner, archive], sub=sub)
    verifier("12. cours ARCHIVE : reservation ecartee",
             await filtre(db, [resa(code="AF-ARCH", courseId="c-arch")]) == [], "")
    verifier("12b. cours ABSENT de la collection : reservation ecartee",
             await filtre(db, [resa(code="AF-ABS", courseId="c-supprime-pour-de-bon")]) == [], "")
    # 13 : une occurrence PRECEDENTE du meme cours recurrent. Attention au piege
    # de raisonnement : un cours hebdomadaire A BIEN LIEU il y a 7 jours — ce
    # n'est donc pas la garde d'occurrence qui l'ecarte, mais le filtre du JOUR
    # en amont. On le verifie donc la ou il agit : dans la route complete.
    _vieille = resa(code="AF-VIEUX", courseId="c-jour", validated=False,
                    datetime=_jour_iso(-7) + "T18:30:00")
    _vieille_validee = resa(code="AF-VLD", courseId="c-jour", validated=True,
                            datetime=_jour_iso(-30) + "T18:30:00")
    db13 = _base([du_jour], sub=forfait(remaining_sessions=5, total_sessions=10,
                                        used_sessions=5, coach_id=COACH_TEST),
                 resas=[_vieille, _vieille_validee])
    faux_shared(abonnement=db13.subscriptions.docs[0])
    ns13 = construire(db13)
    await scanner(ns13, "AFR-ESSAI1")
    verifier("13. occurrence PRECEDENTE du meme cours : jamais validee par le scan du jour",
             _vieille["validated"] is False, "")
    verifier("13b. ancienne reservation DEJA VALIDEE : ne ressort pas comme seance actuelle",
             db13.reservations.docs[-1].get("reservationCode") not in ("AF-VIEUX", "AF-VLD"),
             str(db13.reservations.docs[-1].get("reservationCode")))

    # ── ce qui doit PASSER ─────────────────────────────────────────────────
    db = _base([du_jour, masque], sub=sub)
    ok = await filtre(db, [resa(code="AF-OK", courseId="c-jour")])
    verifier("14. cours actif + reservation du jour : conservee",
             len(ok) == 1 and ok[0]["reservationCode"] == "AF-OK", str(ok))
    masquee = await filtre(db, [resa(code="AF-MASQ", courseId="c-masq")])
    verifier("15. DECISION : `visible: false` n'invalide PAS une reservation legitime",
             len(masquee) == 1, "un cours masque a ete traite comme invalide")
    sans_cid = await filtre(db, [resa(code="AF-SANSCID", courseId="")])
    verifier("16. reservation SANS courseId : conservee (repli assume, 58/133 en prod)",
             len(sans_cid) == 1, str(sans_cid))

    # ── ponctuel du jour + recurrent du jour ───────────────────────────────
    ponctuel = cours(id="c-ponct", name="Laff Festival", date=_jour_iso(), time="19:00",
                     weekday=(js + 3) % 7)
    db = _base([du_jour, ponctuel], sub=sub)
    verifier("17. cours PONCTUEL du jour : conservee (la date prime sur weekday)",
             len(await filtre(db, [resa(code="AF-PONCT", courseId="c-ponct",
                                        datetime=aujourdhui("19:00"))])) == 1, "")
    verifier("17b. cours RECURRENT du jour : conservee",
             len(await filtre(db, [resa(code="AF-REC", courseId="c-jour")])) == 1, "")

    # ── aucun repli catalogue, aucun debit sur une seance historique ───────
    db = _base([diner], sub=sub, resas=[dict(fupq)])
    ns = construire(db)
    try:
        await scanner(ns, "AFR-ESSAI1")
        verifier("18. aucun cours du jour : 422 attendu", False, "accepte !")
    except _HTTPException as e:
        d = e.detail if isinstance(e.detail, dict) else {}
        verifier("18. aucun cours reel aujourd'hui : 422, aucun repli catalogue",
                 e.status_code == 422 and d.get("courses") == [], str(e.detail))
    verifier("18b. AUCUN debit sur une seance historique",
             not db.subscriptions.ecritures, str(db.subscriptions.ecritures))
    verifier("18c. AUCUNE reservation creee", len(db.reservations.docs) == 1, "")
    verifier("18d. la reservation historique reste intacte",
             db.reservations.docs[0].get("validated") is True, "")


# ═════ 12. LE CODE SOURCE — LA GARDE EST BIEN AUX DEUX ENDROITS ═════════════
def test_a1b_source():
    import io as _io
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = _io.open(os.path.join(racine, "api", "routes", "reservation_routes.py"),
                   encoding="utf-8").read()
    verifier("19. la garde est appliquee au chemin d'appariement (A0)",
             "return await _a1b_occurrences_reelles(_dujour)" in src, "")
    verifier("19b. ... et au dernier recours (CAS E)",
             "_cas_e = await _a1b_occurrences_reelles(_cas_e)" in src, "")
    # On analyse le CODE EXECUTE, docstring et commentaires exclus : la
    # docstring DECRIT la regle (« `visible` n'est pas une garde ») et
    # contiendrait sinon tous les mots qu'on cherche a ne pas trouver.
    import ast as _ast
    _fn = next(n for n in _ast.walk(_ast.parse(src))
               if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))
               and n.name == "_a1b_occurrences_reelles")
    _lignes = src.splitlines(True)
    _debut = _fn.body[1].lineno - 1 if _ast.get_docstring(_fn) else _fn.body[0].lineno - 1
    corps = "".join(_lignes[_debut:_fn.end_lineno])
    code = "\n".join(l for l in corps.splitlines() if not l.strip().startswith("#"))
    verifier("20. PREUVE : `visible` n'est utilise nulle part comme garde",
             "visible" not in code, [l for l in code.splitlines() if "visible" in l][:1])
    verifier("20b. la garde repose sur `archived` et sur l'occurrence reelle",
             'get("archived")' in code and "_a1_a_lieu_aujourdhui(" in code, "")
    verifier("21. LECTURE SEULE : la garde n'ecrit rien",
             not any(x in code for x in ("insert_one", "update_one", "update_many",
                                         "delete_one", "delete_many")), "")
    verifier("22. une seule requete groupee, jamais un find_one par ligne",
             code.count("db.courses.find(") == 1 and "find_one" not in code, "")
    verifier("23. aucun statut d'annulation invente (le champ n'existe pas en base)",
             "cancelled" not in code and '"status"' not in code, "")


async def principal():
    test_convention_jour()
    test_a_lieu_aujourdhui()
    test_etiquette()
    test_datetime_occurrence()
    await test_route_selecteur()
    await test_route_choix_manuel()
    await test_route_chemin_legitime()
    await test_route_auto_detection()
    await test_non_regression_a0()
    await test_a1b_garde_appariement()
    test_a1b_source()
    test_source()


def rapport():
    print("\n" + "=" * 74)
    print("A1 — SCAN QR / OCCURRENCE REELLE")
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
