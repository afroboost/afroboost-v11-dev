#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V612 — contraintes d'agenda de Coach Bassi dans « Générer une réponse avec l'IA ».

    python3 -W "error:Flags not at the start:DeprecationWarning" tests/test_v612_agenda_bassi.py

Mercredi / dimanche : intervention extérieure le MATIN seulement, terminée AVANT MIDI, à ≤ 2 h de
trajet depuis Neuchâtel ; trajet jamais deviné. Fonctions pures : aucune base, aucun appel IA, aucun e-mail.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["JWT_SECRET"] = "secret-de-test-v612"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v612:27017")
import api.server as S  # noqa: E402
R = []
def verifier(nom, cond, detail=""):
    R.append(bool(cond)); print("  %-6s %s" % ("OK  " if cond else "ECHEC", nom))
    if detail and not cond: print("           ->", detail)

def ctx(corps, ville, trajet=None, categorie="association", fil=None):
    f = {"city": ville, "category": categorie}
    if trajet is not None:
        f["trajet_depuis_neuchatel_min"] = trajet
    c = S.p3ai_contexte({"id": "inb", "body_text": corps, "from_email": "x@exemple.test"},
                        {"id": "act", "organisations": ["Org"], "message_j0": ""}, [f], [], "")
    c["fil"] = fil or []
    c["contexte_commercial"] = S.v611_contexte_commercial(c, [f])
    return c
def ag(c): return c["contexte_commercial"]["agenda"]
def cr(c): return ag(c)["creneaux"][0] if ag(c)["creneaux"] else {}

print("\nA. Mercredi 9h à Besançon, trajet fiable ≤ 2 h → possible")
a = ctx("Nous pourrions vous accueillir le mercredi 4 mars à 9h, ça vous irait ?", "Besançon", trajet=95)
verifier("mercredi détecté, 9h, avant midi, trajet ≤ 2 h, compatible", cr(a).get("mercredi") and cr(a).get("heure_min") == 540
         and cr(a).get("avant_midi") == "OUI" and cr(a).get("trajet_ok") == "OUI" and cr(a).get("compatible") == "OUI", cr(a))
verifier("le brouillon qui accepte 9h n'est pas signalé", S.v612_controle_brouillon("Le mercredi à 9h me convient très bien.", ag(a)) == [])

print("\nB. Mercredi 14h à Besançon → impossible")
b = ctx("Est-ce que mercredi à 14h vous conviendrait ?", "Besançon", trajet=95)
verifier("après-midi → avant midi NON → incompatible", cr(b).get("avant_midi") == "NON" and cr(b).get("compatible") == "NON", cr(b))
inv = S.p3ai_invite(b)
verifier("l'invite dit d'écarter ce créneau avec la formule prévue", "ce creneau n'est PAS possible" in inv and "regarder une autre date" in inv)
verifier("accepter mercredi 14h dans le brouillon → validation", "créneau incompatible" in S.v612_controle_brouillon("Va pour mercredi à 14h !", ag(b)))

print("\nC. Mercredi matin, ville à plus de 2 h → impossible")
c = ctx("Un mercredi matin serait idéal pour nous.", "Lyon", trajet=180)
verifier("matin mais trajet > 2 h → incompatible", cr(c).get("avant_midi") == "OUI" and cr(c).get("trajet_ok") == "NON" and cr(c).get("compatible") == "NON", cr(c))
verifier("l'invite interdit mercredi et dimanche pour ce lieu", "ne propose ni mercredi ni dimanche" in S.p3ai_invite(c))

print("\nD. Dimanche 10h, ville ≤ 2 h → possible")
d = ctx("Dimanche à 10h, au parc ?", "Bienne", trajet=40)
verifier("10h → fin 11h, avant midi ; compatible", cr(d).get("dimanche") and cr(d).get("avant_midi") == "OUI" and cr(d).get("compatible") == "OUI", cr(d))
d2 = ctx("Dimanche à 11h30 ?", "Bienne", trajet=40)
verifier("dimanche 11h30 → finirait 12h30 → pas avant midi → incompatible", cr(d2).get("avant_midi") == "NON" and cr(d2).get("compatible") == "NON", cr(d2))

print("\nE. Dimanche 15h, ville ≤ 2 h → impossible")
e = ctx("Sonntag um 15 Uhr wäre perfekt.", "Bienne", trajet=40)
verifier("15 Uhr (allemand) détecté, incompatible", cr(e).get("dimanche") and cr(e).get("heure_min") == 900 and cr(e).get("compatible") == "NON", cr(e))

print("\nF. Dimanche matin, trajet inconnu → à vérifier, jamais ferme")
f = ctx("Un dimanche matin chez nous ?", "Besançon")
verifier("trajet inconnu → À VÉRIFIER (rien n'est deviné)", ag(f)["trajet_connu"] is False and ag(f)["trajet_min"] is None and cr(f).get("compatible") == "A VERIFIER", ag(f))
inv = S.p3ai_invite(f)
verifier("l'invite : ne pas confirmer, présenter comme à confirmer", "NE LE CONFIRME PAS" in inv and "Temps de trajet depuis Neuchatel NON CONNU" in inv)
verifier("brouillon ferme « dimanche matin, c'est noté » → validation", "date non vérifiée présentée comme ferme" in S.v612_controle_brouillon(
    "Parfait, dimanche matin c'est noté.", ag(f)))
verifier("brouillon prudent « dimanche matin, à confirmer » → pas signalé", S.v612_controle_brouillon(
    "Le dimanche matin pourrait être possible, à confirmer de mon côté.", ag(f)) == [])
verifier("canton de Neuchâtel → trajet connu (local), jamais « à vérifier »", S.v612_trajet([], "Le Locle")["connu"] is True)

print("\nG. Lundi à samedi (hors mercredi) → aucune restriction inventée")
for jour in ("lundi", "mardi", "jeudi", "vendredi", "samedi"):
    g = ctx("Le %s à 16h ?" % jour, "Besançon")
    verifier("%s 16h, trajet inconnu → compatible (aucune contrainte)" % jour, cr(g).get("compatible") == "OUI", cr(g))
verifier("aucune pénalité dans le brouillon pour « jeudi à 20h »", S.v612_controle_brouillon("Jeudi à 20h, avec plaisir.", ag(ctx("x", "Besançon"))) == [])

print("\nH. Le partenaire propose lui-même mercredi 16h → autre créneau")
h = ctx("Nous vous proposons le mercredi 18 novembre à 16h.", "Yverdon-les-Bains", trajet=35)
verifier("mercredi 16h → incompatible", cr(h).get("compatible") == "NON", cr(h))
verifier("l'invite impose de proposer une autre date", "regarder une autre date ensemble" in S.p3ai_invite(h))
verifier("citer le cours de 18h45 → validation (contrainte interne)", "contrainte interne citée" in S.v612_controle_brouillon(
    "Je dois rentrer pour mon cours de 18h45.", ag(h)))

print("\nI. Séance gratuite pertinente mais créneau incompatible")
i = ctx("Votre projet nous intéresse ! Combien coûterait une venue le mercredi à 15h ?", "Besançon", trajet=95)
cc = i["contexte_commercial"]; inv = S.p3ai_invite(i)
verifier("la séance découverte reste pertinente (V611)", cc["seance_decouverte_pertinente"], cc)
verifier("…mais le créneau est refusé et la séance n'y est jamais proposée",
         "SEANCE DECOUVERTE :" in inv and "ce creneau n'est PAS possible" in inv and "Ne propose jamais une seance (meme offerte) sur un creneau incompatible" in inv)
verifier("brouillon « séance offerte mercredi à 15h » → validation", "créneau incompatible" in S.v612_controle_brouillon(
    "Je vous offre la séance, mercredi à 15h.", ag(i)))

print("\nJ. Garde-fous V611 intacts")
j = ctx("Bonjour, quel serait le prix ?", "Neuchâtel")
verifier("Neuchâtel : toujours pas de séance offerte (V611)", not j["contexte_commercial"]["seance_decouverte_pertinente"])
verifier("l'invite contient toujours la règle V611 et les disponibilités V612", "REGLES COMMERCIALES" in S.p3ai_invite(j) and "DISPONIBILITES DE COACH BASSI" in S.p3ai_invite(j))
verifier("la contrainte interne n'est jamais à expliquer au partenaire", "ne cite jamais ses cours" in S.p3ai_invite(j))

ok = sum(R); print("\n%d/%d vérifications réussies (aucun appel IA réel, aucun e-mail)" % (ok, len(R))); sys.exit(0 if ok == len(R) else 1)
