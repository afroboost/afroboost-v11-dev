#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V611 — « Générer une réponse avec l'IA » applique la règle « première séance découverte ».

    python3 -W "error:Flags not at the start:DeprecationWarning" tests/test_v611_seance_decouverte_ia.py

Aucun appel OpenAI (modèle simulé), aucune base réelle, aucun e-mail.
"""
import asyncio, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["JWT_SECRET"] = "secret-de-test-v611"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v611:27017")
import api.server as S  # noqa: E402
R = []
def verifier(nom, cond, detail=""):
    R.append(bool(cond)); print("  %-6s %s" % ("OK  " if cond else "ECHEC", nom))
    if detail and not cond: print("           ->", detail)

def ctx(corps, ville, categorie="ecole_danse", fil=None, notes=None, j0="", **fiche):
    f = dict({"city": ville, "category": categorie}, **fiche)
    c = S.p3ai_contexte({"id": "inb", "body_text": corps, "from_email": "x@exemple.test"},
                        {"id": "act", "organisations": ["Org"], "message_j0": j0}, [f], notes or [], "")
    c["fil"] = fil or []
    c["contexte_commercial"] = S.v611_contexte_commercial(c, [f])
    return c

print("\nA. Partenaire à Neuchâtel → pas de déplacement ni de séance offerte")
a = ctx("Bonjour, votre proposition nous intéresse, combien coûterait une séance ?", "La Chaux-de-Fonds")
cc = a["contexte_commercial"]; inv = S.p3ai_invite(a)
verifier("hors Neuchâtel = NON (canton NE)", cc["hors_neuchatel"] is False, cc)
verifier("séance découverte / frais de déplacement non pertinents", not cc["seance_decouverte_pertinente"] and not cc["frais_deplacement_pertinents"])
verifier("l'invite interdit la séance gratuite et les frais", "Pas de seance decouverte gratuite" in inv and "SEANCE DECOUVERTE :" not in inv)
verifier("un brouillon qui offrirait la séance → validation (gratuite_hors_regle)",
         "gratuité hors règle" in S.v611_controle_brouillon("Je vous offre la séance gratuite.", a, cc))

print("\nB. Partenaire à Besançon intéressé → séance offerte + frais de déplacement")
b = ctx("Bonjour, l'idée nous plaît beaucoup. Combien coûterait une première intervention chez nous ?", "Besançon")
cc = b["contexte_commercial"]; inv = S.p3ai_invite(b)
verifier("hors Neuchâtel, première collaboration, intérêt", cc["hors_neuchatel"] and cc["premiere_collaboration"] and cc["interet"], cc)
verifier("séance découverte + frais de déplacement pertinents", cc["seance_decouverte_pertinente"] and cc["frais_deplacement_pertinents"])
verifier("l'invite porte la règle (offerte, frais de déplacement aller-retour, aucun tarif pour la suite)",
         "SEANCE DECOUVERTE :" in inv and "prise en charge des frais" in inv and "Ne fixe AUCUN tarif" in inv)
bon = ("Pour une première découverte d'Afroboost à Besançon, je peux vous proposer la séance gratuitement. "
       "Je demanderais simplement la prise en charge de mes frais de déplacement aller-retour.")
verifier("le brouillon conforme ne déclenche aucun motif V611", S.v611_controle_brouillon(bon, b, cc) == [],
         S.v611_controle_brouillon(bon, b, cc))
verifier("« payer l'essence » → validation", "formulation déplacement" in S.v611_controle_brouillon("Il faudrait juste payer l'essence.", b, cc))
verifier("montant de déplacement inventé (80 CHF) → validation", "montant inventé" in S.v611_controle_brouillon("Déplacement : 80 CHF.", b, cc))

print("\nC. Festival à Zurich → pas de festival entier gratuit")
c = ctx("hallo bassi, ja gerne den vorschlag, danke und lg roger", "Zürich", "festival")
cc = c["contexte_commercial"]; inv = S.p3ai_invite(c)
verifier("gros événement détecté (catégorie festival)", cc["gros_evenement"], cc)
verifier("l'invite dit : préparer une vraie proposition, pas offrir la prestation", "GROS EVENEMENT : n'offre pas la prestation" in inv)
verifier("« das ganze Festival kostenlos » → validation", "gros événement offert" in S.v611_controle_brouillon(
    "Wir bieten das ganze Festival kostenlos an.", c, cc))
verifier("événement physique → pas de format en ligne", not cc["format_en_ligne_pertinent"] and "Ne propose pas de format en ligne" in inv)

print("\nD. Hors région, prix déjà convenu → ne contredit pas")
d = ctx("Merci, nous confirmons pour le 12 mars.", "Lausanne",
        fil=[{"de": "afroboost", "quand": "2026-10-01", "texte": "La séance serait à 300 CHF, déplacement compris."}])
cc = d["contexte_commercial"]; inv = S.p3ai_invite(d)
verifier("prix déjà donné, proposition existante, plus une première", cc["prix_deja_donne"] and cc["proposition_existante"] and not cc["premiere_collaboration"], cc)
verifier("aucune séance gratuite proposée", not cc["seance_decouverte_pertinente"] and "Pas de seance decouverte gratuite" in inv)
verifier("le fil complet entre dans l'invite (300 CHF visible pour le modèle)", "FIL PRECEDENT" in inv and "300 CHF" in inv)
verifier("rappeler 300 CHF = OK ; inventer 250 CHF → validation",
         "montant inventé" not in S.v611_controle_brouillon("Comme convenu, 300 CHF.", d, cc)
         and "montant inventé" in S.v611_controle_brouillon("Le tarif sera de 250 CHF.", d, cc))
verifier("offrir la séance après un prix → validation", "gratuité hors règle" in S.v611_controle_brouillon("Finalement elle est offerte.", d, cc))

print("\nE. Format en ligne pertinent")
e = ctx("Nos membres sont répartis dans toute la Suisse romande, une intervention sur place est difficile.", "Genève",
        "association", j0="une séance courte de 30 minutes en ligne")
cc = e["contexte_commercial"]; inv = S.p3ai_invite(e)
verifier("format en ligne pertinent", cc["format_en_ligne_pertinent"], cc)
verifier("l'invite autorise le format en ligne, sans promesse de santé", "EN LIGNE peut etre mentionne" in inv and "Aucune promesse de sante" in inv)

print("\nF. Refus poli → aucune offre commerciale forcée")
f = ctx("Comme nous envoyons à nos membres beaucoup de mails, nous sommes obligés de faire un tri. "
        "Je vous conseille de voir avec les sages-femmes indépendantes de votre région.", "Lausanne", "association")
cc = f["contexte_commercial"]; inv = S.p3ai_invite(f)
verifier("refus / tri détecté ; pas de séance découverte", cc["refus"] and not cc["seance_decouverte_pertinente"], cc)
verifier("l'invite dit de respecter la décision, sans offre", "respecte sa decision, n'ajoute AUCUNE offre" in inv)
verifier("une offre dans le brouillon → validation", "gratuité hors règle" in S.v611_controle_brouillon("Je vous offre une séance gratuite !", f, cc))

print("\nG. Le bouton ne fait que GÉNÉRER un brouillon")
class Cur:
    def __init__(s, d): s.d = d
    async def to_list(s, n): return list(s.d)[:n]
class Col:
    def __init__(s, docs=None): s.docs = list(docs or []); s.ecritures = 0
    def _ok(s, d, q):
        for k, v in (q or {}).items():
            if isinstance(v, dict) and "$ne" in v:
                if d.get(k) == v["$ne"]: return False
            elif d.get(k) != v: return False
        return True
    async def find_one(s, q, p=None): return next((dict(d) for d in s.docs if s._ok(d, q)), None)
    def find(s, q, p=None): return Cur([dict(d) for d in s.docs if s._ok(d, q)])
    async def insert_one(s, d): s.ecritures += 1; s.docs.append(d)
    async def update_one(s, q, u, upsert=False): s.ecritures += 1
class Base(dict):
    def __missing__(s, k): self_col = Col(); s[k] = self_col; return self_col
base = Base()
base[S.P3U2_COLLECTION] = Col([{"id": "old", "action_id": "act-b", "body_text": "Bonjour, de quoi s'agit-il ?", "received_at": "2026-10-10"}])
base[S.P3AI4_COLLECTION] = Col([{"action_id": "act-b", "send_status": "envoye", "approved_text": "Voici notre concept.", "sent_at": "2026-10-11"}])
MESSAGE = {"id": "inb-b", "action_id": "act-b", "coach_id": "coach@exemple.test", "body_text": "Combien coûterait une venue chez nous ?",
           "received_at": "2026-10-12", "from_email": "contact@besancon.test", "subject": "Re: Afroboost"}
ACTION = {"id": "act-b", "organisations": ["MJC Besançon"], "prospect_uuids": ["p-b"]}
FICHES = [{"id": "p-b", "city": "Besançon", "category": "association"}]
INVITES = []
async def faux_modele(invite, ton=""):
    INVITES.append(invite)
    return json.dumps({"intention": "positif", "langue": "fr", "resume": "r", "demande": "d", "prochaine_action": "p",
                       "reponse_proposee": "Bonjour, je peux vous proposer une première séance offerte, avec la prise en charge de mes frais de déplacement aller-retour."})
async def faux_auth(request): return "coach@exemple.test"
async def faux_dossier(inbound_id, email): return {"message": dict(MESSAGE), "action": dict(ACTION), "fiches": FICHES}
async def faux_notes(*a, **k): return []
class Req:
    headers = {"content-length": "0"}
    async def json(self): return {}
sauv = (S.db, S.p3ai_appeler_modele, S._v309_require_coach_or_admin, S.p3ai_dossier, S.p3ai_notes_de)
S.db, S.p3ai_appeler_modele, S._v309_require_coach_or_admin, S.p3ai_dossier, S.p3ai_notes_de = base, faux_modele, faux_auth, faux_dossier, faux_notes
envoyes_avant = len(base[S.P3AI4_COLLECTION].docs)
r = asyncio.run(S.p3ai_analyser("inb-b", Req()))
S.db, S.p3ai_appeler_modele, S._v309_require_coach_or_admin, S.p3ai_dossier, S.p3ai_notes_de = sauv
br = r["brouillon"]
verifier("un brouillon est rendu, avec le rapport interne (contexte commercial)", br.get("reponse_proposee") and br.get("contexte_commercial", {}).get("ville_partenaire") == "Besançon", br.get("contexte_commercial"))
verifier("le modèle a reçu le fil complet (ancien message + notre réponse)", "de quoi s'agit-il" in INVITES[0] and "Voici notre concept" in INVITES[0])
verifier("aucun envoi : la collection des envois n'a reçu aucune écriture", base[S.P3AI4_COLLECTION].ecritures == 0 and len(base[S.P3AI4_COLLECTION].docs) == envoyes_avant)
verifier("rapport interne : 10 champs demandés présents", all(k in br["contexte_commercial"] for k in (
    "ville_partenaire", "hors_neuchatel", "premiere_collaboration", "proposition_existante", "prix_deja_donne", "gros_evenement",
    "seance_decouverte_pertinente", "frais_deplacement_pertinents", "format_en_ligne_pertinent", "collaboration_future_a_discuter")))
import inspect
src = inspect.getsource(S.p3ai_analyser)
verifier("la route d'analyse n'appelle aucun envoi", "envoyer" not in src and "Emails" not in src and "_rc.emails" not in src)
verifier("l'invite ne parle plus de « fondateur » et signe Coach Bassi", "fondateur" not in INVITES[0] and "Coach Bassi" in INVITES[0])

ok = sum(R); print("\n%d/%d vérifications réussies (aucun appel IA réel, aucun e-mail)" % (ok, len(R))); sys.exit(0 if ok == len(R) else 1)
