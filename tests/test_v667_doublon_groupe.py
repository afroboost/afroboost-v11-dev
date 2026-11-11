# -*- coding: utf-8 -*-
"""V667 — « LA MÊME SÉANCE », C'EST LE GROUPE, PAS LA FICHE.

CE QUE J'AI DÉCOUVERT EN VÉRIFIANT (11/11/2026). Il n'y a PAS de doublon à
corriger : depuis V647, une séance physique est portée par DEUX fiches
groupées — la fiche « forfait » (`agenda_abonne: true`) et la fiche publiée —
et le groupement FONCTIONNE déjà sur les données réelles. Le calendrier montre
UNE carte, et les inscrits sont DÉJÀ sommés sur les deux fiches.

LE VRAI TROU, LUI, ÉTAIT AILLEURS : l'anti-doublon de réservation comparait
`courseId` à UNE SEULE fiche. Un même membre pouvait donc réserver la même
séance deux fois — une par fiche — et occuper deux places. Mesuré : 0 cas sur
151 réservations, mais la porte était ouverte.

Ce banc est HORS LIGNE : il éprouve la règle de groupement sur les FORMES
RÉELLES de la base, puis vérifie que les trois chemins d'anti-doublon
s'appuient bien sur le groupe.
"""
import io, os, re, sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from api.routes.shared import (v647_adresse_normalisee,                # noqa: E402
                               v647_groupes_seance_physique)

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()

_ok = _ko = 0


def v(nom, cond, detail=""):
    global _ok, _ko
    if cond:
        _ok += 1
        print("  PASS  %s" % nom)
    else:
        _ko += 1
        print("  RATE  %s  -> %s" % (nom, str(detail)[:160]))


# Les quatre fiches RÉELLES, telles qu'elles sont en base (types compris :
# `weekday` est un int, et les adresses sont écrites différemment).
FORFAIT_MER = {"id": "64b4c975", "name": "Afroboost Silent – Session Cardio",
               "coach_id": "contact.artboost@gmail.com", "weekday": 3, "time": "18:45",
               "locationName": "Chem. des Valangines 97, 2000 Neuchâtel",
               "agenda_abonne": True, "archived": True, "visible": True}
PUBLIEE_MER = {"id": "62fcac27", "name": "Cours à l'unité",
               "coach_id": "contact.artboost@gmail.com", "weekday": 3, "time": "18:45",
               "locationName": "Chemin des Valangines 97, 2000 Neuchâtel",
               "archived": False, "visible": True}
FORFAIT_DIM = {**FORFAIT_MER, "id": "23534f7c", "weekday": 0, "time": "18:30",
               "name": "Afroboost Silent – Sunday Vibes"}
PUBLIEE_DIM = {**PUBLIEE_MER, "id": "01f3b303", "weekday": 0, "time": "18:30"}

OFFRES = {"64b4c975": {"o1", "o2"}, "62fcac27": {"o1"},
          "23534f7c": {"o1", "o2"}, "01f3b303": {"o1"}}

print("== V647 — LE GROUPEMENT EXISTANT, SUR LES FORMES RÉELLES ==")
_g = v647_groupes_seance_physique([FORFAIT_MER, PUBLIEE_MER, FORFAIT_DIM, PUBLIEE_DIM], OFFRES)
v("les 4 fiches forment 2 séances physiques", len(_g) == 4, len(_g))
v("mercredi : les deux fiches sont dans LE MÊME groupe",
  _g.get("64b4c975", {}).get("id") == _g.get("62fcac27", {}).get("id"), _g)
v("dimanche aussi", _g.get("23534f7c", {}).get("id") == _g.get("01f3b303", {}).get("id"), _g)
v("mercredi et dimanche restent DEUX séances distinctes",
  _g.get("64b4c975", {}).get("id") != _g.get("23534f7c", {}).get("id"))
# C'est la fiche FORFAIT qui donne son nom à la carte : c'est donc elle que le
# renommage doit viser.
v("la fiche PRINCIPALE est la fiche forfait (celle dont le nom s'affiche)",
  _g.get("64b4c975", {}).get("principale") == "64b4c975", _g.get("64b4c975"))
v("« Chem. » et « Chemin » sont bien la même adresse",
  v647_adresse_normalisee("Chem. des Valangines 97, 2000 Neuchâtel")
  == v647_adresse_normalisee("Chemin des Valangines 97, 2000 Neuchâtel"))

print()
print("== CE QUI CASSERAIT CE GROUPEMENT — ET QUE LA MIGRATION NE DOIT PAS FAIRE ==")
# MASQUER la fiche publiée : `_publiees` exige `visible is not False`.
_masquee = {**PUBLIEE_MER, "visible": False}
_g2 = v647_groupes_seance_physique([FORFAIT_MER, _masquee], OFFRES)
v("masquer la fiche publiée DÉTRUIT le groupe", len(_g2) == 0, _g2)
# L'ARCHIVER aussi.
_arch = {**PUBLIEE_MER, "archived": True}
v("l'archiver aussi", len(v647_groupes_seance_physique([FORFAIT_MER, _arch], OFFRES)) == 0)
# Sans offre commune, pas de groupe : deux cours qui n'ont rien à voir.
v("sans offre commune, aucun groupe",
  len(v647_groupes_seance_physique([FORFAIT_MER, PUBLIEE_MER],
                                   {"64b4c975": {"o2"}, "62fcac27": {"o1"}})) == 0)
# Deux fiches forfait, ou deux publiées : on ne devine pas laquelle mène.
v("il faut EXACTEMENT une fiche forfait et une publiée",
  len(v647_groupes_seance_physique([FORFAIT_MER, {**FORFAIT_MER, "id": "autre"}],
                                   {"64b4c975": {"o1"}, "autre": {"o1"}})) == 0)

print()
print("== RENOMMER NE CASSE RIEN ==")
_renomme = {**FORFAIT_MER, "name": "Afroboost",
            "description": "Cours collectif de cardio-danse afrobeat, sans casque audio."}
_g3 = v647_groupes_seance_physique([_renomme, PUBLIEE_MER], OFFRES)
v("le groupe tient après renommage", len(_g3) == 2, _g3)
v("et la fiche renommée reste la principale",
  _g3.get("64b4c975", {}).get("principale") == "64b4c975")
# Le nom n'entre PAS dans la clé de groupement : c'est ce qui rend le
# renommage sans danger.
v("le nom n'entre pas dans la règle de groupement",
  "name" not in io.open(os.path.join(RACINE, "api", "routes", "shared.py"),
                        encoding="utf-8").read()
  .split("def v647_groupes_seance_physique")[1].split("def ")[0])

print()
print("== V667 — L'ANTI-DOUBLON REGARDE TOUT LE GROUPE ==")
_bloc = SRC.split("V667 — « LA MÊME SÉANCE »")[1].split("# V186/V202")[0]
v("le filtre de groupe est construit", "_v667_filtre_cours" in _bloc)
v("il réutilise le groupement EXISTANT (pas un second mécanisme)",
  "v647_groupes_depuis_base" in _bloc)
v("il interroge TOUTES les fiches du groupe", '"$in": _v667_ids' in _bloc)
# Les trois chemins d'anti-doublon doivent l'utiliser : groupe, repli
# « anciennes réservations », et individuel.
v("les trois chemins d'anti-doublon l'utilisent",
  _bloc.count("_v667_filtre_cours") >= 4, _bloc.count("_v667_filtre_cours"))
v("plus aucun chemin ne compare la seule fiche",
  '"courseId": course_id,\n            }' not in _bloc)
# UN ÉCHEC DE GROUPEMENT NE DOIT JAMAIS REFUSER UNE RÉSERVATION LÉGITIME.
v("si le groupement échoue, on retombe sur la fiche seule",
  "on s'en tient à la fiche" in _bloc and "_v667_ids = [course_id]" in _bloc)
v("et la date de l'occurrence reste dans la comparaison",
  'dup_query["datetime"] = occurrence_iso' in SRC)

print()
print("  %d/%d" % (_ok, _ok + _ko))
sys.exit(0 if _ko == 0 else 1)
