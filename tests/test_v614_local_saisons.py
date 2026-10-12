#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V614 — partenaires locaux (cours réguliers d'abord), autres dates selon l'agenda, saisons.

    python3 -W "error:Flags not at the start:DeprecationWarning" tests/test_v614_local_saisons.py

Fonctions pures : aucune base, aucun appel IA ni réseau, aucun e-mail.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["JWT_SECRET"] = "secret-de-test-v614"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v614:27017")
import api.server as S  # noqa: E402
R = []
def verifier(nom, cond, detail=""):
    R.append(bool(cond)); print("  %-6s %s" % ("OK  " if cond else "ECHEC", nom))
    if detail and not cond: print("           ->", detail)

def ctx(corps, ville, categorie="association", trajet_auto=None):
    f = {"city": ville, "category": categorie}
    c = S.p3ai_contexte({"id": "inb", "body_text": corps, "from_email": "x@exemple.test"},
                        {"id": "act", "organisations": ["Org"], "message_j0": ""}, [f], [], "")
    c["fil"] = []
    if trajet_auto is not None:
        c["trajet_auto"] = trajet_auto
    c["contexte_commercial"] = S.v611_contexte_commercial(c, [f])
    return c, c["contexte_commercial"], c["contexte_commercial"]["situation"], S.p3ai_invite(c)

print("\nA. Partenaire à Neuchâtel intéressé → d'abord un cours régulier")
c, cc, sit, inv = ctx("Bonjour, votre activité nous intéresse beaucoup !", "Neuchâtel")
verifier("local, cours régulier à proposer, pas de séance offerte", sit["local_neuchatel"] and sit["cours_regulier_a_proposer"] and not cc["seance_decouverte_pertinente"], (sit, cc))
verifier("l'invite : venir découvrir un cours mercredi 18h45 / dimanche 18h30, aucune date précise",
         "pendant un cours regulier" in inv and "18h45" in inv and "18h30" in inv and "Ne donne aucune date precise" in inv)
verifier("inviter au cours de mercredi 18h45 n'est PAS signalé (ni créneau, ni contrainte interne)",
         S.v612_controle_brouillon("Venez découvrir un de nos cours, le mercredi à 18h45 ou le dimanche à 18h30.", cc["agenda"]) == [])

print("\nB. Local, séance privée un jeudi → possible selon l'agenda")
c, cc, sit, inv = ctx("Pourriez-vous venir chez nous pour notre équipe, un jeudi à 12h ?", "Neuchâtel")
verifier("séance chez lui + autre date à discuter", sit["veut_seance_chez_lui"] and sit["autre_date_a_discuter"], sit)
verifier("l'invite : possible si l'agenda le permet, jamais « impossible », aucune dispo inventée",
         "POSSIBLE SI L'AGENDA LE PERMET" in inv and "n'invente aucune disponibilite" in inv)
verifier("jeudi : aucune restriction V612", cc["agenda"]["creneaux"][0]["compatible"] == "OUI")

print("\nC. Local, hiver, avec salle → chez lui possible")
c, cc, sit, inv = ctx("En janvier, nous pourrions vous accueillir dans notre salle de gym.", "Neuchâtel")
verifier("saison hiver, salle OUI", sit["saison"] == "hiver" and sit["salle_disponible"] == "OUI", sit)
verifier("l'invite : séance dans sa structure possible", "Hiver : une seance dans sa structure est possible (le partenaire dispose d'une salle)" in inv)

print("\nD. Local, hiver, sans info de salle → demander")
c, cc, sit, inv = ctx("Une séance chez nous en décembre serait top.", "Neuchâtel")
verifier("hiver, salle INCONNU", sit["saison"] == "hiver" and sit["salle_disponible"] == "INCONNU", sit)
verifier("l'invite : demander la salle, ne pas la supposer", "demande-le, ne le suppose pas" in inv)
verifier("brouillon « dans votre salle » sans question → validation (salle supposée)",
         "salle supposée" in S.v614_controle_brouillon("Je viendrai dans votre salle.", c, sit))
verifier("brouillon « si vous disposez d'une salle » → pas signalé",
         "salle supposée" not in S.v614_controle_brouillon("Je peux venir dans votre salle si vous disposez d'une salle adaptée.", c, sit))
verifier("école de danse : la salle n'est pas remise en question", ctx("Chez nous en décembre ?", "Neuchâtel", "ecole_danse")[2]["salle_disponible"] == "OUI")

print("\nE. Local, été → extérieur possible, aucune autorisation affirmée")
c, cc, sit, inv = ctx("Cet été, une séance pour nos membres ?", "Neuchâtel")
verifier("été, extérieur possible", sit["saison"] == "ete" and sit["exterieur_possible"] == "OUI", sit)
verifier("l'invite : extérieur possible, jamais affirmer un lieu autorisé", "EXTERIEUR" in inv and "N'affirme JAMAIS qu'un lieu public est disponible ou autorise" in inv)
verifier("brouillon « le parc est disponible, autorisation obtenue » → validation",
         "lieu ou autorisation non vérifiés" in S.v614_controle_brouillon("Le parc est disponible et l'autorisation obtenue.", c, sit))

print("\nF. Besançon (hors Neuchâtel) → séance offerte + frais de déplacement (V611 intact)")
c, cc, sit, inv = ctx("Votre projet nous plaît, combien coûterait une venue chez nous ?", "Besançon")
verifier("pas local ; séance découverte + frais pertinents", not sit["local_neuchatel"] and cc["seance_decouverte_pertinente"] and cc["frais_deplacement_pertinents"], cc)
verifier("l'invite garde la règle V611 et ne propose pas le cours régulier", "SEANCE DECOUVERTE :" in inv and "pendant un cours regulier" not in inv)

print("\nG / H / I. Mercredi / dimanche (V612 + V613 intacts)")
ok_auto = {"statut": "ok", "minutes": 103, "source": "OSRM", "incertain": False}
c, cc, sit, inv = ctx("Mercredi à 9h chez nous ?", "Besançon", trajet_auto=ok_auto)
verifier("G. mercredi 9h + trajet 103 min → compatible", cc["agenda"]["creneaux"][0]["compatible"] == "OUI", cc["agenda"])
c, cc, sit, inv = ctx("Mercredi à 15h ?", "Besançon", trajet_auto=ok_auto)
verifier("H. mercredi 15h → incompatible", cc["agenda"]["creneaux"][0]["compatible"] == "NON")
c, cc, sit, inv = ctx("Dimanche matin ?", "Besançon")
verifier("I. dimanche matin, trajet inconnu → À VÉRIFIER", cc["agenda"]["creneaux"][0]["compatible"] == "A VERIFIER")

print("\nJ. Autre jour → aucune restriction inventée")
c, cc, sit, inv = ctx("Un samedi à 17h ?", "Besançon")
verifier("samedi 17h → compatible", cc["agenda"]["creneaux"][0]["compatible"] == "OUI")

print("\nK. Mois futur sans disponibilité connue → pas de date inventée")
c, cc, sit, inv = ctx("Avez-vous des disponibilités en mars ?", "Neuchâtel")
verifier("autre date à discuter ; planning en cours mentionnable", sit["autre_date_a_discuter"] and "planifier nos prochaines disponibilites" in inv, sit)
verifier("brouillon « le jeudi 12 mars » inventé → validation (date inventée)",
         "date inventée" in S.v614_controle_brouillon("Je vous propose le jeudi 12 mars.", c, sit))
verifier("brouillon qui reprend la date du partenaire → pas signalé",
         S.v614_controle_brouillon("Le 12 mars me conviendrait.", ctx("Le 12 mars ?", "Neuchâtel")[0], sit) == [])
verifier("saison neutre en mars (pas inventée)", sit["saison"] == "inconnue" and "Saison non precisee" in inv)

print("\nL. Festival → pas tout l'événement offert (V611 intact)")
c, cc, sit, inv = ctx("Oui, intéressés pour notre festival !", "Lausanne", "festival")
verifier("gros événement → vraie proposition", cc["gros_evenement"] and "GROS EVENEMENT : n'offre pas la prestation" in inv)

print("\nM. Refus poli → aucune proposition de lieu / date")
c, cc, sit, inv = ctx("Nous devons faire un tri, merci de votre compréhension.", "Neuchâtel")
verifier("refus : pas de bloc lieu/dates/saison", "LIEU, DATES ET SAISON" not in inv and "n'ajoute AUCUNE offre" in inv)

print("\nN. Rapport interne complet")
champs = ("local_neuchatel", "veut_seance_chez_lui", "date_proposee", "saison", "salle_disponible", "exterieur_possible",
          "cours_regulier_a_proposer", "autre_date_a_discuter")
verifier("les champs V614 sont présents", all(k in sit for k in champs), sit)
verifier("« je dois rentrer pour mon cours » reste signalé (V612)", "contrainte interne citée" in S.v612_controle_brouillon(
    "Je dois rentrer pour mon cours.", cc["agenda"]))

ok = sum(R); print("\n%d/%d vérifications réussies (aucun appel IA ni réseau, aucun e-mail)" % (ok, len(R))); sys.exit(0 if ok == len(R) else 1)
