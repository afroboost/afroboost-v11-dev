#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""INV-5 — une invitation active n'emmène que vers ce que le lien profond PEUT ouvrir.

Défaut trouvé en production (29/09) : une invitation « Essai gratuit » a été
activée (1) sur une offre gratuite NON PUBLIQUE — `/?offre=<id>&reserver=1`
ne l'ouvre pas, le front ignore une offre absente de `GET /offers` ; puis
(2) sur une offre publique mais avec un cours ni rattaché à l'offre ni public —
le formulaire annonçait « La séance de ton invitation n'est plus disponible ».

Ce banc exécute les VRAIES routes sur la base en mémoire de
`test_referral_campaigns.py` (importé, jamais recopié). AUCUN réseau.

Lancement :  python3 tests/test_inv5_coherence.py
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_referral_campaigns as T  # noqa: E402

H, E, IC, RC = T.H, T.E, T.IC, T.RC
verifier, appel = H.verifier, H.appel
COACH_A = T.COACH_A

OFFRE_LIEE = "offre-inv5-liee"            # gratuite, publique, rattachée à COURS_A seul
OFFRE_CACHEE = "offre-inv5-cachee"        # gratuite, visible: false (cas 1 de la prod)
OFFRE_ARCHIVEE = "offre-inv5-archivee"    # gratuite, archivée
OFFRE_PRIVEE = "offre-inv5-privee"        # gratuite, link_only : s'ouvre par son lien (V537)
OFFRE_COMPLETE = "offre-inv5-complete"    # gratuite, stock 0 : retirée de la vitrine
OFFRE_PRODUIT = "offre-inv5-produit"      # gratuite mais produit (boutique)
COURS_ARCHIVE = "cours-inv5-archive"
COURS_MASQUE = "cours-inv5-masque"


def depart():
    base, occ = T.depart()
    _wd = [c for c in base["courses"].docs if c["id"] == T.COURS_A][0]["weekday"]
    base["courses"].docs += [
        {"id": COURS_ARCHIVE, "name": "Ancien A", "weekday": _wd, "time": "18:30", "visible": True,
         "archived": True, "coach_id": COACH_A},
        {"id": COURS_MASQUE, "name": "Masqué A", "weekday": _wd, "time": "18:30", "visible": False,
         "archived": False, "coach_id": COACH_A},
    ]
    base["offers"].docs += [
        {"id": OFFRE_LIEE, "name": "Essai lié", "price": 0.0, "visible": True, "coach_id": COACH_A,
         "linked_course_ids": [T.COURS_A]},
        {"id": OFFRE_CACHEE, "name": "Essai caché", "price": 0.0, "visible": False, "coach_id": COACH_A},
        {"id": OFFRE_ARCHIVEE, "name": "Essai archivé", "price": 0.0, "visible": True, "archived": True,
         "coach_id": COACH_A},
        {"id": OFFRE_PRIVEE, "name": "Essai privé", "price": 0.0, "visible": True, "link_only": True,
         "coach_id": COACH_A},
        {"id": OFFRE_COMPLETE, "name": "Essai complet", "price": 0.0, "visible": True, "stock": 0,
         "coach_id": COACH_A},
        {"id": OFFRE_PRODUIT, "name": "Goodies", "price": 0.0, "visible": True, "isProduct": True,
         "coach_id": COACH_A},
    ]
    return base, occ


def essai(offre, cours, occ, statut="active"):
    return {"type": "trial", "status": statut, "course_id": cours, "occurrence": occ, "offer_id": offre}


def decale(occ, jours=0, heure=None):
    _d = datetime.strptime(occ, "%Y-%m-%dT%H:%M:%S") + timedelta(days=jours)
    _s = _d.strftime("%Y-%m-%dT%H:%M:%S")
    return (_s[:11] + heure + ":00") if heure else _s


async def partie_offre():
    base, occ = depart()
    for nom, offre in (("masquée (visible: false)", OFFRE_CACHEE), ("archivée", OFFRE_ARCHIVEE),
                       ("complète (stock épuisé)", OFFRE_COMPLETE), ("produit de boutique", OFFRE_PRODUIT)):
        c, r = await T.creer(COACH_A, essai(offre, T.COURS_A, occ))
        verifier("INV5-O1 trial actif, offre %s -> 422 clair" % nom,
                 c == 422 and "publi" in str(r.get("detail", "")).lower(), (c, r))
        c, r = await T.creer(COACH_A, {"type": "event_free", "status": "active", "offer_id": offre})
        verifier("INV5-O2 event_free actif sans cours, offre %s -> 422" % nom, c == 422, (c, r))
    c, r = await T.creer(COACH_A, essai(OFFRE_PRIVEE, T.COURS_A, occ))
    verifier("INV5-O3 offre privée link_only -> 201 (son lien l'ouvre, V537)", c == 201, (c, r))
    c, r = await T.creer(COACH_A, {"type": "event_free", "status": "active", "offer_id": T.OFFRE_A_ESSAI})
    verifier("INV5-O4 event_free sans cours sur offre publique -> 201", c == 201, (c, r))
    c, r = await T.creer(COACH_A, essai(OFFRE_CACHEE, "cours-inv5-archive", occ, statut="draft"))
    verifier("INV5-O5 brouillon reste permissif (offre cachée + cours archivé) -> 201",
             c == 201 and r.get("status") == "draft", (c, r))
    c, r2 = await T.modifier(COACH_A, r["id"], {"status": "active"})
    verifier("INV5-O6 ... mais son activation -> 422, reste brouillon",
             c == 422 and T.doc(base, r["id"])["status"] == "draft", (c, r2))
    verifier("INV5-O7 aucune écriture dans `campaigns`", not base["campaigns"].docs)


async def partie_cours():
    base, occ = depart()
    c, r = await T.creer(COACH_A, essai(OFFRE_LIEE, T.COURS_A_SANS_DUO, occ))
    verifier("INV5-C1 cours NON rattaché à l'offre (qui liste ses cours) -> 422 clair",
             c == 422 and "rattach" in str(r.get("detail", "")), (c, r))
    c, r = await T.creer(COACH_A, {"type": "event_free", "status": "active", "offer_id": OFFRE_LIEE,
                                   "course_id": T.COURS_A_SANS_DUO, "occurrence": occ})
    verifier("INV5-C1b event_free : même règle -> 422", c == 422, (c, r))
    c, r = await T.creer(COACH_A, essai(OFFRE_LIEE, T.COURS_A, occ))
    verifier("INV5-C2 combinaison valide (offre publique + cours rattaché + vraie séance) -> 201",
             c == 201 and r.get("status") == "active", (c, r))
    for nom, cours in (("archivé", COURS_ARCHIVE), ("masqué", COURS_MASQUE)):
        c, r = await T.creer(COACH_A, essai(T.OFFRE_A_ESSAI, cours, occ))
        verifier("INV5-C3 cours %s (offre sans cours liés) -> 422 clair" % nom,
                 c == 422 and ("masqué" in str(r.get("detail", "")) or "archiv" in str(r.get("detail", ""))),
                 (c, r))
    c, r = await T.creer(COACH_A, essai(T.OFFRE_A_ESSAI, T.COURS_A_SANS_DUO, occ))
    verifier("INV5-C4 offre sans cours liés : tout cours public accepté (règle du front INV-2)", c == 201, (c, r))
    c, r = await T.creer(COACH_A, essai(OFFRE_LIEE, T.COURS_A, decale(occ, jours=1)))
    verifier("INV5-C5 date qui ne tombe pas le jour du cours -> 422", c == 422, (c, r))
    c, r = await T.creer(COACH_A, essai(OFFRE_LIEE, T.COURS_A, decale(occ, heure="19:45")))
    verifier("INV5-C6 heure différente de celle du cours -> 422", c == 422, (c, r))
    c, r = await T.creer(COACH_A, {"type": "pass_duo", "status": "active", "course_id": T.COURS_A,
                                   "occurrence": occ})
    verifier("INV5-C7 pass_duo inchangé -> 201", c == 201, (c, r))

    # PUT d'une invitation ACTIVE : la même porte.
    c, a = await T.creer(COACH_A, essai(OFFRE_LIEE, T.COURS_A, occ))
    c, r = await T.modifier(COACH_A, a["id"], {"course_id": T.COURS_A_SANS_DUO})
    verifier("INV5-C8 PUT active vers un cours non rattaché -> 422, rien changé",
             c == 422 and T.doc(base, a["id"])["course_id"] == T.COURS_A, (c, r))
    c, r = await T.modifier(COACH_A, a["id"], {"offer_id": OFFRE_CACHEE})
    verifier("INV5-C9 PUT active vers une offre cachée -> 422, rien changé",
             c == 422 and T.doc(base, a["id"])["offer_id"] == OFFRE_LIEE, (c, r))
    c, r = await T.modifier(COACH_A, a["id"], {"title": "Nouveau titre"})
    verifier("INV5-C10 PUT active cohérent -> 200", c == 200, (c, r))


async def partie_options():
    base, occ = depart()
    c, o = await appel(RC.invitations_options(T.rq(COACH_A)))
    offres = {x["id"]: x for x in o.get("offers", [])}
    cours = {x["id"]: x for x in o.get("courses", [])}
    verifier("INV5-P1 options 200", c == 200, c)
    verifier("INV5-P2 chaque offre porte `openable` (bool) et `course_ids` (liste)",
             all(isinstance(x.get("openable"), bool) and isinstance(x.get("course_ids"), list)
                 for x in offres.values()), list(offres.values())[:2])
    verifier("INV5-P3 ouvrables : publique, privée par lien, liée",
             offres[T.OFFRE_A_ESSAI]["openable"] and offres[OFFRE_PRIVEE]["openable"]
             and offres[OFFRE_LIEE]["openable"], {k: v.get("openable") for k, v in offres.items()})
    verifier("INV5-P4 NON ouvrables : cachée, complète, produit",
             offres.get(OFFRE_CACHEE, {}).get("openable") is False
             and offres.get(OFFRE_COMPLETE, {}).get("openable") is False
             and offres.get(OFFRE_PRODUIT, {}).get("openable") is False,
             {k: v.get("openable") for k, v in offres.items()})
    verifier("INV5-P5 archivée jamais proposée", OFFRE_ARCHIVEE not in offres, sorted(offres))
    verifier("INV5-P6 course_ids = cours rattachés", offres[OFFRE_LIEE]["course_ids"] == [T.COURS_A]
             and offres[T.OFFRE_A_ESSAI]["course_ids"] == [], offres[OFFRE_LIEE])
    verifier("INV5-P7 chaque cours porte `public`", all(isinstance(x.get("public"), bool) for x in cours.values())
             and cours[T.COURS_A]["public"] is True
             and (COURS_MASQUE not in cours or cours[COURS_MASQUE]["public"] is False)
             and (COURS_ARCHIVE not in cours or cours[COURS_ARCHIVE]["public"] is False),
             {k: v.get("public") for k, v in cours.items()})
    verifier("INV5-P8 aucune PII", T.COACH_A not in json.dumps(o) and not E.contient_pii(o))


async def partie_moteur_pur():
    c = {"id": "c1", "weekday": 3, "time": "18h30", "visible": True}
    verifier("INV5-M1 cours public", IC.cours_public(c) and not IC.cours_public(dict(c, visible=False))
             and not IC.cours_public(dict(c, archived=True)) and not IC.cours_public(None))
    verifier("INV5-M2 rattachement", IC.cours_rattache({"linked_course_ids": ["c1"]}, "c1")
             and not IC.cours_rattache({"linked_course_ids": ["c2"]}, "c1")
             and IC.cours_rattache({"linked_course_ids": []}, "c1") and IC.cours_rattache({}, "c1"))
    # 2026-10-07 est un mercredi (JS 3).
    verifier("INV5-M3 séance du cours (jour + heure)", IC.seance_du_cours(c, "2026-10-07T18:30:00")
             and not IC.seance_du_cours(c, "2026-10-08T18:30:00")
             and not IC.seance_du_cours(c, "2026-10-07T19:30:00"))
    f = {"id": "c2", "date": "2026-10-09", "time": "10:00"}
    verifier("INV5-M4 cours à date fixe", IC.seance_du_cours(f, "2026-10-09T10:00:00")
             and not IC.seance_du_cours(f, "2026-10-16T10:00:00"))


def main():
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())
    except Exception:  # noqa: BLE001
        pass
    boucle = asyncio.get_event_loop()
    for partie in (partie_moteur_pur, partie_offre, partie_cours, partie_options):
        try:
            boucle.run_until_complete(partie())
        except Exception as err:  # noqa: BLE001
            import traceback
            verifier("INV5 PARTIE %s sans exception" % partie.__name__, False,
                     "%s: %s\n%s" % (type(err).__name__, err, traceback.format_exc()[-1500:]))
    res = [r for r in H.RESULTATS if str(r[0]).startswith("INV5")]
    ok = sum(1 for _, c, _ in res if c)
    for nom, cond, detail in res:
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom, ("" if cond or not detail else "\n         -> " + str(detail)[:600])))
    print("%d / %d verifications INV-5 au vert" % (ok, len(res)))
    return 0 if ok == len(res) else 1


if __name__ == "__main__":
    sys.exit(main())
