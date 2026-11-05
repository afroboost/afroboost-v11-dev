#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V647 — une carte par cours physique : l'identité métier, jamais la seule heure et adresse.

Fonctions pures de `api/routes/shared.py`, aucune base, aucun réseau.
"""
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
sys.path.insert(0, RACINE)
from api.routes.shared import (v647_adresse_normalisee as adr,  # noqa: E402
                               v647_groupes_seance_physique as groupes,
                               v647_inscrits_du_groupe as inscrits)

echecs = []


def v(nom, cond, detail=""):
    print(("OK   " if cond else "FAIL ") + nom + (f"  -> {detail}" if not cond else ""))
    if not cond:
        echecs.append(nom)


COACH = "coach@example.test"
ICI = "Chem. des Valangines 97, 2000 Neuchâtel"


def fiche(i, **k):
    d = {"id": i, "coach_id": COACH, "weekday": 3, "time": "18:45", "locationName": "Chemin des Valangines 97, 2000 Neuchâtel", "date": ""}
    d.update(k)
    return d


FORFAIT = fiche("forfait", archived=True, agenda_abonne=True, locationName=ICI)
PUBLIEE = fiche("publiee", visible=True, archived=False)
OFFRES = {"forfait": {"o1", "o2"}, "publiee": {"o2", "o3"}}

print("── Adresses")
v("Chem. et Chemin sont la même rue", adr(ICI) == adr("Chemin des Valangines 97, 2000 Neuchâtel"))
v("une parenthèse parasite ne compte pas", adr(ICI + ")") == adr(ICI))
v("les accents ne comptent pas", adr("Neuchatel") == adr("Neuchâtel"))
v("un autre numéro est une autre adresse", adr("Chemin des Valangines 98") != adr("Chemin des Valangines 97"))

print("── Regroupés : le vrai cas")
g = groupes([FORFAIT, PUBLIEE], OFFRES)
v("les deux fiches sont réunies", g.get("forfait") and g.get("forfait") == g.get("publiee"), g)
v("la fiche forfait est la principale", g["forfait"]["principale"] == "forfait")
v("l'identifiant est stable quel que soit l'ordre", groupes([PUBLIEE, FORFAIT], OFFRES)["forfait"]["id"] == g["forfait"]["id"])

print("── Jamais regroupés : même heure et même adresse ne suffisent pas")
CAS = [
    ("un événement daté", [FORFAIT, fiche("x", date="2026-10-28")], {"forfait": {"o2"}, "x": {"o2"}}),
    ("un événement V610", [FORFAIT, fiche("x", v610_evenement=True)], {"forfait": {"o2"}, "x": {"o2"}}),
    ("une séance qui en remplace une autre", [FORFAIT, fiche("x", remplace_cours_id="y")], {"forfait": {"o2"}, "x": {"o2"}}),
    ("une séance ponctuelle de campagne", [FORFAIT, fiche("x", _v640b_ponctuel=True)], {"forfait": {"o2"}, "x": {"o2"}}),
    ("aucune offre commune", [FORFAIT, PUBLIEE], {"forfait": {"o1"}, "publiee": {"o3"}}),
    ("une fiche sans offre", [FORFAIT, PUBLIEE], {"forfait": {"o1"}}),
    ("deux fiches publiées (deux salles)", [fiche("a"), fiche("b")], {"a": {"o2"}, "b": {"o2"}}),
    ("deux fiches forfait", [fiche("a", agenda_abonne=True), fiche("b", agenda_abonne=True)], {"a": {"o2"}, "b": {"o2"}}),
    ("trois fiches : ambigu", [FORFAIT, PUBLIEE, fiche("c")], {"forfait": {"o2"}, "publiee": {"o2"}, "c": {"o2"}}),
    ("un autre coach", [FORFAIT, fiche("x", coach_id="autre@example.test")], {"forfait": {"o2"}, "x": {"o2"}}),
    ("un autre jour", [FORFAIT, fiche("x", weekday=0)], {"forfait": {"o2"}, "x": {"o2"}}),
    ("une autre heure", [FORFAIT, fiche("x", time="19:00")], {"forfait": {"o2"}, "x": {"o2"}}),
    ("une autre adresse", [FORFAIT, fiche("x", locationName="Rue du Lac 1, Neuchâtel")], {"forfait": {"o2"}, "x": {"o2"}}),
    ("une adresse absente", [fiche("a", agenda_abonne=True, locationName=""), fiche("b", locationName="")], {"a": {"o2"}, "b": {"o2"}}),
    ("une fiche publiée masquée", [FORFAIT, fiche("x", visible=False)], {"forfait": {"o2"}, "x": {"o2"}}),
]
for nom, cours, offres in CAS:
    v(nom, groupes(cours, offres) == {}, groupes(cours, offres))

print("── Inscrits, sans doublon")
P = lambda r: r.get("quantity", 1)  # noqa: E731
v("personnes différentes : on additionne", inscrits([{"userEmail": "a@x", "courseId": "f"}, {"userEmail": "b@x", "courseId": "p"}], P) == 2)
v("la même personne sur les deux fiches : une fois", inscrits([{"userEmail": "a@x", "courseId": "f"}, {"userEmail": "A@X ", "courseId": "p"}], P) == 1)
v("plusieurs places : le plus grand total", inscrits([{"userEmail": "a@x", "courseId": "f", "quantity": 3}, {"userEmail": "a@x", "courseId": "p"}], P) == 3)
v("deux réservations sur UNE fiche : toutes comptent", inscrits([{"userEmail": "a@x", "courseId": "f"}, {"userEmail": "a@x", "courseId": "f"}], P) == 2)
v("sans e-mail : aucune fusion", inscrits([{"courseId": "f"}, {"courseId": "p"}], P) == 2)

print(f"\n{'ÉCHECS : ' + str(len(echecs)) if echecs else 'TOUT EST VERT'}")
sys.exit(1 if echecs else 0)
