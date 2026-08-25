# -*- coding: utf-8 -*-
"""E1B — UNE SEANCE ENCORE AU PLANNING RAPPELLE, MEME SI LE COURS EST ARCHIVE.

CE QUE CE FICHIER PROUVE, ET RIEN D'AUTRE.

`archived = true` cessait a lui seul de faire taire un rappel. C'etait la seule
chose qui separait les deux vraies seances hebdomadaires — archivees pour sortir
de la vitrine, vendues par trois offres, servies par l'agenda public — du dernier
message avant la porte. L'ecran de configuration des rappels les proposait deja
au coach (`rv3_cours_configurables`) ; le moteur les jetait en silence.

CE QUE CE LOT NE FAIT PAS, ET QUE CE FICHIER SURVEILLE : il ne desarchive rien,
ne republie rien, ne rouvre aucune reservation, ne recree aucune occurrence, ne
touche ni au cron, ni a l'idempotence, ni aux drapeaux, ni a E2.

IL N'INVENTE PAS L'ANNULATION D'UNE OCCURRENCE. Le modele ne la porte pas ; ce
lot ne fabrique donc AUCUNE pseudo-logique pour la deviner. Il verifie une chose
verifiable : la seance de cette reservation figure-t-elle ENCORE au planning du
cours. C'est la dette E1C, explicitement hors de ce commit.

Aucun reseau. Aucun Push. Aucun e-mail. Aucune base. Aucune ecriture.

Lancement :  python3 tests/test_e1b_rappel_cours_archive.py
"""

import asyncio
import io
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import test_rv2_rappels_push_email as H   # noqa: E402  (harnais partage)

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()

ZH = H.ZURICH
RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


# --------------------------------------------------------------- jeux de test
R60 = [{"type": "relative", "minutes": 60}]
CODE = "AFR-2287CA"
LIEU = "Bord du Lac, Auvernier, Neuchâtel"


def dans(minutes=60):
    """L'instant que `H.resa(decalage_min=...)` place sur le cours."""
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def horaire_de(instant):
    """(weekday JS, « HH:MM ») du cours qui produirait CET instant."""
    loc = instant.astimezone(ZH)
    return (loc.weekday() + 1) % 7, loc.strftime("%H:%M")


def cours_planifie(cid="c1", instant=None, actif=True, archive=False,
                   decale_jours=0, ponctuel=False, **extra):
    """Un cours dont le planning produit REELLEMENT l'occurrence demandee.

    `decale_jours` deplace le planning sans toucher a la reservation : c'est
    ainsi qu'on represente une seance qui n'est plus au planning, faute de
    pouvoir representer une occurrence annulee (dette E1C).
    """
    quand = instant or dans()
    jour, heure = horaire_de(quand)
    d = H.cours(cid=cid, actif=actif, regles=R60 if actif else None,
                archive=archive)
    d["time"] = heure
    d["locationName"] = LIEU
    if ponctuel:
        loc = (quand + timedelta(days=decale_jours)).astimezone(ZH)
        d["date"] = loc.date().isoformat()
    else:
        d["weekday"] = (jour + decale_jours) % 7
        d["date"] = ""
    d.update(extra)
    return d


def offre(*cours_ids):
    return {"id": "o1", "name": "PULSE x10 cours",
            "linked_course_ids": list(cours_ids)}


async def passage(resas, cours_docs, offres=None, codes=None, **kw):
    b, base = H.bac(resas, cours_docs=cours_docs, offres=offres,
                    codes=codes, **kw)
    r = await b["cron_reservation_reminders"]()
    return b, base, r


def mails():
    return list(H.EMAILS)


# ===================================================== A -> C : la porte E1B
async def porte():
    quand = dans()

    # --- A. cours NON archive : strictement comme avant ---------------------
    await passage([H.resa(instant=quand)], [cours_planifie(instant=quand)])
    verifier("A. cours non archive + resa future valide -> rappel comme avant",
             len(mails()) == 1, "%d mail(s)" % len(mails()))

    # --- A2. le meme, sans planning exploitable : TOUJOURS rappele ----------
    # La preuve de planning est une CONDITION D'OUVERTURE pour les archives,
    # jamais une restriction nouvelle sur le parc vivant.
    c = cours_planifie(instant=quand)
    c.pop("weekday", None)
    c["date"] = ""
    await passage([H.resa(instant=quand)], [c])
    verifier("A2. un cours vivant sans planning calculable rappelle toujours",
             len(mails()) == 1, "%d mail(s)" % len(mails()))

    # --- B. cours ARCHIVE + offre vivante + seance au planning --------------
    await passage([H.resa(instant=quand)],
                  [cours_planifie(instant=quand, archive=True)],
                  offres=[offre("c1")], codes=[{"code": CODE}])
    verifier("B. cours archive + offre vivante + seance au planning -> rappel",
             len(mails()) == 1, "%d mail(s)" % len(mails()))

    # --- B2. cours ARCHIVE + `agenda_abonne`, sans aucune offre -------------
    await passage([H.resa(instant=quand)],
                  [cours_planifie(instant=quand, archive=True,
                                  agenda_abonne=True)])
    verifier("B2. cours archive marque `agenda_abonne` -> rappel",
             len(mails()) == 1, "%d mail(s)" % len(mails()))

    # --- B3. cours ARCHIVE sans offre NI `agenda_abonne` : muet -------------
    await passage([H.resa(instant=quand)],
                  [cours_planifie(instant=quand, archive=True)])
    verifier("B3. cours archive que plus rien ne vend -> muet, comme avant",
             not mails(), repr(mails())[:100])

    # --- B4. l'offre doit designer CE cours, pas un autre -------------------
    await passage([H.resa(instant=quand)],
                  [cours_planifie(instant=quand, archive=True)],
                  offres=[offre("un-autre-cours")])
    verifier("B4. une offre qui ne designe pas ce cours ne prouve rien",
             not mails(), repr(mails())[:100])

    # --- C. cours archive servi, mais AUCUNE reservation --------------------
    b, base, r = await passage([], [cours_planifie(instant=quand, archive=True)],
                               offres=[offre("c1")])
    verifier("C. cours archive + aucune reservation -> rien",
             not mails() and r.get("checked") == 0, repr(r))


# ============================== D -> F : ce qui doit rester definitivement mut
async def refus():
    quand = dans()

    # --- D. reservation annulee : le document n'existe plus -----------------
    # Une annulation est un `delete_one` (`cancel_reservation_from_space`), pas
    # un statut : la reservation annulee est ABSENTE des candidats.
    await passage([], [cours_planifie(instant=quand, archive=True)],
                  offres=[offre("c1")])
    verifier("D. reservation annulee (document supprime) -> aucun rappel",
             not mails())
    verifier("D2. l'annulation reste bien une suppression, pas un statut",
             "await db.reservations.delete_one({\"id\": reservation_id})" in SRC)

    # --- E. occurrence PASSEE ----------------------------------------------
    passe = datetime.now(timezone.utc) - timedelta(minutes=90)
    await passage([H.resa(instant=passe)],
                  [cours_planifie(instant=passe, archive=True)],
                  offres=[offre("c1")])
    verifier("E. occurrence passee -> aucun rappel", not mails(),
             repr(mails())[:100])

    # --- F. occurrence introuvable : le planning ne la produit plus ---------
    await passage([H.resa(instant=quand)],
                  [cours_planifie(instant=quand, archive=True, decale_jours=1)],
                  offres=[offre("c1")])
    verifier("F. seance retiree du planning (jour deplace) -> aucun rappel",
             not mails(), repr(mails())[:100])

    c = cours_planifie(instant=quand, archive=True)
    c.pop("weekday", None)
    c["date"] = ""
    await passage([H.resa(instant=quand)], [c], offres=[offre("c1")])
    verifier("F2. cours archive sans planning calculable -> aucun rappel",
             not mails(), repr(mails())[:100])

    c = cours_planifie(instant=quand, archive=True)
    c["time"] = ""
    await passage([H.resa(instant=quand)], [c], offres=[offre("c1")])
    verifier("F3. horaire illisible -> aucun rappel", not mails(),
             repr(mails())[:100])

    # --- F4. le cours n'existe plus du tout ---------------------------------
    await passage([H.resa(instant=quand)], [], offres=[offre("c1")])
    verifier("F4. cours introuvable -> aucun rappel", not mails())


# ================================ G : la vitrine et la reservation ne bougent
async def vitrine():
    verifier("G. la liste publique filtre toujours les cours archives",
             'base_filter = {"archived": {"$ne": True}}' in SRC)
    verifier("G2. la porte de reservation V426 est intacte",
             'if course.get("archived") and course_id not in _v426_linked:' in SRC
             and 'raise HTTPException(status_code=404, detail="Cours introuvable")' in SRC)
    verifier("G3. E1B ne pose jamais `archived` a False",
             '"archived": False' not in _bloc_cron())
    verifier("G4. E1B n'ecrit RIEN sur les cours",
             "db.courses.update" not in _bloc_cron()
             and "courses.insert" not in _bloc_cron())
    verifier("G5. l'agenda public garde sa propre regle, non touchee",
             '{"visible": {"$ne": False}, "archived": {"$ne": True}},' in SRC
             and '{"agenda_abonne": True},' in SRC)


def _bloc_cron():
    i = SRC.find("async def cron_reservation_reminders")
    return SRC[i:SRC.find("\nasync def send_backup_email", i)]


# ================================== H -> L : idempotence, planning, inertie
async def garanties():
    quand = dans()

    # --- H. deux passages du cron -------------------------------------------
    b, base = H.bac([H.resa(instant=quand)],
                    cours_docs=[cours_planifie(instant=quand, archive=True)],
                    offres=[offre("c1")])
    await b["cron_reservation_reminders"]()
    await b["cron_reservation_reminders"]()
    verifier("H. double passage du cron -> un seul rappel",
             len(H.EMAILS) == 1 and len(H.PUSHS) == 1,
             "%d mail(s), %d push" % (len(H.EMAILS), len(H.PUSHS)))

    # --- I. date unique (cours ponctuel) ------------------------------------
    await passage([H.resa(instant=quand)],
                  [cours_planifie(instant=quand, archive=True, ponctuel=True)],
                  offres=[offre("c1")])
    verifier("I. cours a date unique, seance maintenue -> rappel",
             len(mails()) == 1, "%d mail(s)" % len(mails()))

    await passage([H.resa(instant=quand)],
                  [cours_planifie(instant=quand, archive=True, ponctuel=True,
                                  decale_jours=3)],
                  offres=[offre("c1")])
    verifier("I2. cours a date unique deplacee -> aucun rappel", not mails(),
             repr(mails())[:100])

    # --- J. recurrence ------------------------------------------------------
    sem = datetime.now(timezone.utc) + timedelta(days=7, minutes=60)
    await passage([H.resa(instant=sem)],
                  [cours_planifie(instant=sem, archive=True)],
                  offres=[offre("c1")])
    verifier("J. recurrence hors horizon -> aucun rappel premature",
             not mails(), repr(mails())[:100])

    demain = datetime.now(timezone.utc) + timedelta(days=1)
    c_demain = cours_planifie(instant=demain, archive=True)
    c_demain["reminder_rules"] = [{"type": "relative", "minutes": 1440}]
    await passage([H.resa(instant=demain)], [c_demain], offres=[offre("c1")])
    verifier("J2. recurrence : l'occurrence de demain est bien au planning",
             len(mails()) == 1, "%d mail(s)" % len(mails()))

    # --- K. rappel non active : INERTIE au deploiement -----------------------
    for etat in (None, False):
        await passage([H.resa(instant=quand)],
                      [cours_planifie(instant=quand, archive=True, actif=etat)],
                      offres=[offre("c1")])
        verifier("K. cours archive servi mais rappel %s -> aucun envoi"
                 % ("absent" if etat is None else "coupe"),
                 not mails(), repr(mails())[:100])

    # --- L. l'idempotence est celle d'avant, au caractere pres --------------
    b, base = H.bac([H.resa(instant=quand)],
                    cours_docs=[cours_planifie(instant=quand, archive=True)],
                    offres=[offre("c1")])
    await b["cron_reservation_reminders"]()
    doc = base.reservations.docs[0]
    marq = (doc.get("reminders_sent") or {}).get("defaut") or {}
    verifier("L. le marqueur d'idempotence garde sa forme (canal -> instant)",
             set(marq.keys()) == {"push", "email"}, repr(marq)[:120])
    verifier("L2. le booleen herite est toujours ecrit",
             doc.get("reminder_sent") is True)
    verifier("L3. reserver/liberer un canal n'a pas change",
             "rv2_reserver_canal" in _bloc_cron()
             and "rv2_liberer_canal" in _bloc_cron())


# ==================================================== M : E2 toujours debout
async def e2_intact():
    quand = dans()
    await passage([H.resa(instant=quand, promoCode=CODE)],
                  [cours_planifie(instant=quand, archive=True,
                                  mapsUrl="https://maps.google.com/?q=Auvernier")],
                  offres=[offre("c1")], codes=[{"code": CODE}])
    m = mails()[-1] if mails() else {}
    html = m.get("html") or ""
    txt = m.get("text") or ""
    verifier("M. QUAND : la date et l'heure sont dans le rappel",
             "18:30" in html or ":" in txt, repr(txt)[:90])
    verifier("M2. OU : l'adresse du cours est dans le rappel", LIEU in html)
    verifier("M3. itineraire : le lien de carte est present",
             "maps.google.com" in html)
    verifier("M4. QR : le bouton vers l'espace participant est present",
             "/espace/%s" % CODE in html)
    verifier("M5. le push reste mot pour mot celui d'avant",
             len(H.PUSHS) == 1 and "Danse Afro" in (H.PUSHS[0].get("corps") or ""))


# ============================================ N : non-regression structurelle
def non_regression():
    verifier("N. AUTO-PRESENCE n'est pas touche",
             'AUTO_PRESENCE_TRIAL_ENABLED' in SRC
             and 'AUTO_PRESENCE_TRIAL_ECRITURE_REELLE' in SRC)
    verifier("N2. P1-d n'est pas touche",
             'P1_TRIAL_J3_ENABLED' in SRC and 'P1_TRIAL_J3_ENVOI_REEL' in SRC)
    verifier("N3. la fenetre et l'horizon du moteur sont inchanges",
             "N1B2_DEMI_FENETRE_MIN = 30" in SRC
             and "N1B2_HORIZON_MIN = 2880 + N1B2_DEMI_FENETRE_MIN" in SRC)
    verifier("N4. la regle d'annulation 2 h est intacte",
             "N2_ANNULATION_HEURES" in SRC or "2 h" in SRC)
    verifier("N5. la requete de candidats n'a pas bouge",
             '"datetime": {"$gte": _plancher}' in _bloc_cron())
    verifier("N6. aucun drapeau nouveau dans ce lot",
             "E1B_ENABLED" not in SRC and "E1B_ACTIF" not in SRC)


# ================================ S : ce que le lot promet de ne PAS faire
def structure():
    bloc = _bloc_cron()
    verifier("S1. la regle d'eligibilite n'est ecrite qu'UNE fois",
             SRC.count("def e1b_cours_encore_servi") == 1
             and "e1b_cours_encore_servi" in bloc)
    verifier("S2. l'ecran de configuration utilise LA MEME fonction",
             SRC.count("e1b_cours_encore_servi(") >= 3)
    verifier("S3. le planning est calcule par `_v184_next_occurrences`, pas recopie",
             "_v184_next_occurrences" in SRC[SRC.find("def e1b_seance_encore_au_planning"):
                                             SRC.find("def e1b_seance_encore_au_planning") + 2000])
    verifier("S4. aucune notion d'occurrence annulee n'est inventee",
             "occurrence_annulee" not in SRC and "cancelled_occurrence" not in SRC
             and "occurrences_annulees" not in SRC)
    _entete = SRC[SRC.find("# ============================ E1B"):
                  SRC.find("def e1b_seance_encore_au_planning")]
    verifier("S5. la dette E1C est nommee dans le code, hors de ce lot",
             "E1C" in _entete and "n'invente" in _entete.lower()
             or "E1C" in _entete)
    verifier("S6. les offres sont lues au plus UNE fois par passage",
             bloc.count("db.offers.find") == 1)
    verifier("S7. aucune entree utilisateur ne rentre nue dans une regex",
             "$regex" not in bloc.split("_e1b_cours_vendus")[-1][:800])
    verifier("S8. la projection du cours reste UNE seule lecture par cours",
             bloc.count("db.courses.find_one") == 1)


async def zero_lecture_offres_sans_archive():
    """Un parc sans cours archive ne doit couter AUCUNE lecture d'offres."""
    quand = dans()
    b, base = H.bac([H.resa(instant=quand)],
                    cours_docs=[cours_planifie(instant=quand)],
                    offres=[offre("c1")])
    base.offers.lectures = 0
    _vraie = base.offers.find

    def compte(*a, **k):
        base.offers.lectures += 1
        return _vraie(*a, **k)

    base.offers.find = compte
    await b["cron_reservation_reminders"]()
    verifier("S9. aucun cours archive -> zero lecture d'offres",
             base.offers.lectures == 0, "%d lecture(s)" % base.offers.lectures)

    b, base = H.bac([H.resa(instant=quand, rid="r1"),
                     H.resa(instant=quand, rid="r2", email="b@exemple.com")],
                    cours_docs=[cours_planifie(instant=quand, archive=True)],
                    offres=[offre("c1")])
    base.offers.lectures = 0
    _vraie2 = base.offers.find

    def compte2(*a, **k):
        base.offers.lectures += 1
        return _vraie2(*a, **k)

    base.offers.find = compte2
    await b["cron_reservation_reminders"]()
    verifier("S10. deux reservations archivees -> UNE seule lecture d'offres",
             base.offers.lectures == 1, "%d lecture(s)" % base.offers.lectures)


def main():
    asyncio.get_event_loop().run_until_complete(porte())
    asyncio.get_event_loop().run_until_complete(refus())
    asyncio.get_event_loop().run_until_complete(vitrine())
    asyncio.get_event_loop().run_until_complete(garanties())
    asyncio.get_event_loop().run_until_complete(e2_intact())
    asyncio.get_event_loop().run_until_complete(zero_lecture_offres_sans_archive())
    non_regression()
    structure()

    ok = 0
    for nom, res, detail in RESULTATS:
        print("  %s  %s%s" % ("PASS" if res else "ECHEC", nom,
                              "" if res else "   -> %s" % detail))
        ok += 1 if res else 0
    print("=" * 78)
    print("E-mails REELLEMENT envoyes : 0 — `resend` n'est jamais importe")
    print("Push REELLEMENT envoyes    : 0 — `pywebpush` n'est jamais importe")
    print("Ecritures en production    : 0 — aucune base, aucun reseau")
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())
