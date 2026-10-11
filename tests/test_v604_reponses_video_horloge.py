#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V604 — réponse humaine / automatique / à vérifier, « plus tard », vidéo sur demande, horloge.

    python3 tests/test_v604_reponses_video_horloge.py
"""
import asyncio, os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["JWT_SECRET"] = "secret-de-test-v604"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v604-inexistant:27017")
import api.server as S  # noqa: E402

R = []
def verifier(nom, cond, detail=""):
    R.append(bool(cond)); print("  %-6s %s" % ("OK  " if cond else "ECHEC", nom))
    if detail and not cond: print("           ->", detail)
A = S.v604_analyser_reponse

print("\n1. Nature des réponses")
for sujet, texte, h, de, attendu in [
    ("Buskers Bern – thx for your mail", "", {}, "info@b.ch", "automatique"),
    ("Réponse automatique : absent", "Je suis absent jusqu'au 20 octobre.", {}, "", "automatique"),
    ("Abwesenheitsnotiz", "Ich bin derzeit abwesend.", {}, "", "automatique"),
    ("Re: Afroboost", "", {"Auto-Submitted": "auto-replied"}, "", "automatique"),
    ("Re: Afroboost", "Je suis absent", {"Precedence": "auto_reply"}, "", "automatique"),
    ("Re: Afroboost", "Bonjour, oui volontiers, envoyez-moi la vidéo !", {}, "", "humaine"),
    ("Re: Proposition", "Merci, mais nous ne sommes pas intéressés.", {}, "", "humaine"),
    ("Re: Proposition", "STOP", {}, "", "humaine"),
    ("Re: Proposition", "Quel est votre tarif ?", {}, "", "humaine"),
    ("Accusé de réception", "Merci, bien reçu.", {}, "", "a_verifier"),
    ("Re: Afroboost", "Merci", {}, "noreply@x.ch", "a_verifier"),
    ("Re: Afroboost", "Ceci est une réponse automatique. Concernant votre proposition de cours, je vous rappelle.", {}, "", "humaine"),
]:
    r = A(sujet, texte, h, de)
    verifier("%-11s ← %s / %s" % (attendu, sujet[:28], texte[:30]), r["nature_reponse"] == attendu, r)

print("\n2. Vidéo demandée (texte nouveau seulement)")
verifier("« envoyez-moi la vidéo » → demande_video", A("Re: x", "Oui, envoyez-moi la vidéo", {}, "")["demande_video"])
verifier("« schicken Sie mir das Video » → demande_video", A("AW: x", "Gerne, schicken Sie mir das Video.", {}, "")["demande_video"])
verifier("pas de mot vidéo → non", not A("Re: x", "Intéressé, appelez-moi", {}, "")["demande_video"])
verifier("réponse automatique → jamais demande_video", not A("Out of office", "video", {"Auto-Submitted": "auto-replied"}, "")["demande_video"])

print("\n3. « Contactez-moi plus tard »")
ref = datetime(2026, 10, 11, tzinfo=timezone.utc)
d = lambda t: S.v604_date_suivi(t, ref)[0]
verifier("« revenez vers moi en janvier » → 2027-01-01", (d("Revenez vers moi en janvier svp") or "").startswith("2027-01-01"))
verifier("« recontactez-nous en novembre » → 2026-11-01", (d("Recontactez-nous en novembre") or "").startswith("2026-11-01"))
verifier("« l'année prochaine » → 2027-01-01", (d("Contactez-moi l'année prochaine") or "").startswith("2027-01-01"))
verifier("« plus tard » sans mois → suivi sans date", d("Revenez vers moi plus tard") is None and S.v604_date_suivi("Revenez vers moi plus tard", ref)[1])
verifier("aucun report → rien", S.v604_date_suivi("Merci beaucoup", ref) == (None, None))

print("\n4. Routage vidéo — 8 cas")
def media(n, nom, cible=None):
    return {"id": nom, "niche": n, "format": "16_9", "statut": "a_verifier", "url": "/api/files/x/%s.mp4" % nom,
            "fichier": {"nom": nom}, "cible": cible, "cible_id": (cible or {}).get("id")}
COIF = S.v601_cible({"nom": "Salons / coiffure / beauté", "mots_cles": ["coiff", "tress", "onglerie", "barber", "nail", "beauté"]})
PHYS = S.v601_cible({"nom": "Physio / ostéo / thérapie", "mots_cles": ["physio", "ostéo", "thérap"]})
ASSO = S.v601_cible({"nom": "Associations", "categories": ["association"]})
M = [media("A", "COIFFEUSE", COIF), media("A", "PHYSIO", PHYS), media("B", "ASSOCIATION", ASSO), media("C", "FESTIVAL"),
     media("D", "ECOLE"), media("E", "ENTREPRISE"), media("F", "SAGE-FEMME"), media("G", "ETUDIANTS")]
for niche, p, attendu in [
    ("A", {"organisation_name": "Afrique Tresses", "subcategory": "coiffure afro / tresses", "category": "commerce"}, "COIFFEUSE"),
    ("A", {"organisation_name": "PhysioPod", "subcategory": "physiothérapie", "category": "commerce"}, "PHYSIO"),
    ("B", {"organisation_name": "Mosaïk", "subcategory": "association antiraciste", "category": "association"}, "ASSOCIATION"),
    ("C", {"organisation_name": "Lakelive Festival", "category": "festival"}, "FESTIVAL"),
    ("D", {"organisation_name": "Galerie de la Danse", "category": "ecole_danse"}, "ECOLE"),
    ("E", {"organisation_name": "BCV", "category": "commerce"}, "ENTREPRISE"),
    ("F", {"organisation_name": "SuperMamans", "category": "sante"}, "SAGE-FEMME"),
    ("G", {"organisation_name": "AGE — Association générale des étudiant·es", "category": "communaute_etudiante"}, "ETUDIANTS"),
]:
    ch = S.v601_choisir_media(p, niche, [m for m in M if m["niche"] == niche])
    verifier("%s %-28s → %s" % (niche, p["organisation_name"][:28], attendu), (ch["media"] or {}).get("id") == attendu, ch)
ch = S.v601_choisir_media({"organisation_name": "Chez Mama", "category": "restaurant"}, "A", [m for m in M if m["niche"] == "A"])
verifier("A restaurant → AUCUNE (jamais au hasard)", ch["media"] is None)
ch = S.v601_choisir_media({"organisation_name": "AGE étudiants", "category": "communaute_etudiante"}, "B", [m for m in M if m["niche"] == "B"])
verifier("étudiant resté en B → AUCUNE (pas la vidéo Association)", ch["media"] is None)
ch = S.v601_choisir_media({"organisation_name": "Coiffure & physio", "subcategory": "coiffure / physio"}, "A", [m for m in M if m["niche"] == "A"])
verifier("ambigu → AUCUNE", ch["media"] is None and "ambigu" in ch["raison"])

print("\n5. Horloge des relances")
verifier("samedi 10:00 Zurich → hors heures d'envoi", not S.v604_heure_ouvree(datetime(2026, 10, 17, 8, tzinfo=timezone.utc)))
verifier("lundi 10:00 Zurich → heures d'envoi", S.v604_heure_ouvree(datetime(2026, 10, 12, 8, tzinfo=timezone.utc)))
verifier("lundi 19:00 Zurich → hors heures", not S.v604_heure_ouvree(datetime(2026, 10, 12, 17, tzinfo=timezone.utc)))
async def drapeaux_fermes():
    return {"P3_RELANCE_ENABLED": False}
S.get_feature_flags = drapeaux_fermes
verifier("drapeau P3_RELANCE_ENABLED fermé → passage inactif, aucune lecture", asyncio.run(S.v604_passage_relances()) == {"actif": False})

ok = sum(R); print("\n%d/%d vérifications réussies" % (ok, len(R))); sys.exit(0 if ok == len(R) else 1)
