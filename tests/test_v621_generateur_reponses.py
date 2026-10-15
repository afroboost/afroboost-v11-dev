#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V621 — GENERATEUR DE REPONSES PARTENAIRES : REPONDRE AVANT DE VENDRE. AUCUN APPEL IA REEL, AUCUN E-MAIL.

  A. le fil du generateur = J0 + relances + reponses de Bassi (+ media) + messages recus ;
  B. le dernier message est lu EN ENTIER, sans l'en-tete de citation ;
  C. questions explicites extraites par le CODE ;
  D. « deja dit » : video envoyee / proposee, echange propose, deja repondu ;
  E. l'invite : regles « repondre avant vendre », aucune repetition, rien inventer, 3-8 phrases,
     ton, garde-fous V611-V614 en limites, champ a completer dans la langue du message ;
  F. AI_REPLY_CHECK : controles CODE ; une reecriture n'est gardee que si elle n'ajoute rien de faux ;
  G. un champ « [À COMPLÉTER : …] » ne part jamais (409) ;
  H. la route d'analyse rend analyse + controle, n'ecrit aucun envoi.
"""
try:
    import builtins as _b, os as _o, sys as _s
    _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
    import api.resend_central as _rc
    _b._rc = _rc
except Exception:  # noqa: BLE001
    pass
import asyncio
import json
import os
import socket
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ.pop("OPENAI_API_KEY", None)
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v621-inexistant:27017")
_TENT = []
_GA = socket.getaddrinfo


def _dns(h, p, *a, **k):
    if str(h) in ("localhost", "127.0.0.1", "::1", None):
        return _GA(h, p, *a, **k)
    _TENT.append(h)
    raise OSError("reseau interdit")


socket.getaddrinfo = _dns
import api.server as S  # noqa: E402
from fastapi import HTTPException  # noqa: E402

R = []


def verifier(nom, ok, detail=""):
    R.append(bool(ok))
    print("  %-6s %s%s" % ("OK" if ok else "ECHEC", nom, "" if ok or not detail else "  -> %s" % detail))


# ---------------------------------------------------------------- fixtures (formes reelles du 15/10)
COOL = ("Bonjour, \n\nNous avons un local à Noiraigue que vous pouvez louer si vous le\nsouhaitez pour organiser "
        "des sessions pour le Val de Travers. \n\nExcellente journée \nArthur\n\nLe 2026-10-12T08:43:21.000+02:00, "
        "Afroboost\n<notifications@afroboost.com> a écrit :")
MOMBOYE = ("Bonjour BASSI,\nOui tout à fait, votre proposition entre parfaitement dans notre\nprogrammation.\n"
           "Peut - on échanger de vive voix pour plus de simplicité ?\nJe suis disponible demain après - midi à partir "
           "de 14H 30 au 06 76 51 00 24\ntel ou whatsapp.\n\nBien Cordialement,\nLudivine\n\n\nOn Wed, Oct 14, 2026 at "
           "11:34 AM Afroboost <notifications@afroboost.com>\nwrote:")
CALIENTE = "guten tag bassi, gerne können wir uns in zürich oder regensdorf treffen anfangs november, wann hättest du zeit? danke und gruss  roger\n\n\n￼"
J0 = "Objet : Cardio-danse afro\n\nBonjour,\n\nJe suis Coach Bassi d'Afroboost. Je peux vous envoyer une courte vidéo.\n\nEst-ce que je peux vous présenter l'idée en 10 minutes ?"
ACTION = {"id": "act-c", "campaign_id": "camp-c", "organisations": ["Cool-Ness"], "message_j0": J0,
          "sent_at": "2026-10-12T06:43:08+00:00", "message_j3": "Je peux vous envoyer une courte vidéo de présentation.",
          "j3_sent_at": "2026-10-15T07:36:44+00:00"}
MSG_COOL = {"id": "inb-c", "action_id": "act-c", "body_text": COOL, "received_at": "2026-10-15T12:39:58Z",
            "from_email": "contact@cool-ness.test", "subject": "Re: Cardio-danse"}

print("\nA. LE FIL DU GENERATEUR")
elements = S.v619_fil([dict(MSG_COOL)], dict(ACTION), {}, {}, [])
fil = S.v621_fil_depuis(elements, MSG_COOL, ACTION)
verifier("A1. J0 + relance J+3 presents (le modele sait ce qu'Afroboost a dit)",
         [x["type"] for x in fil] == ["j0", "j3"], [x["type"] for x in fil])
verifier("A2. J0 non prouve : texte approuve, marque « non garanti », sans la ligne Objet",
         fil[0]["garanti"] is False and "Objet" not in fil[0]["texte"] and "10 minutes" in fil[0]["texte"])
verifier("A3. le message auquel on repond n'est pas dans le fil (il est dans DERNIER MESSAGE)",
         all(x["type"] != "partner_reply" for x in fil))
trace = {"id": "t1", "send_status": "envoye", "provider_status": "delivered", "approved_text": "Voici la vidéo.",
         "sent_at": "2026-10-15T14:00:00+00:00",
         "media": {"type": "video", "titre": "Démo", "url": "/api/files/abc/video_abc"}}
fil2 = S.v621_fil_depuis(S.v619_fil([dict(MSG_COOL)], dict(ACTION), {}, {}, [trace]), MSG_COOL, ACTION)
rep = [x for x in fil2 if x["type"] == "manual_reply"][0]
verifier("A4. une reponse de Bassi porte son media envoye (V620) et « apres le message »",
         rep["media"] == {"type": "video", "titre": "Démo"} and rep["apres_message"] is True)

print("\nB. LE DERNIER MESSAGE, EN ENTIER, SANS EN-TETE DE CITATION")
verifier("B1. « Le … a écrit : » retire (Cool-Ness)", S.v621_sans_citation(COOL).endswith("Arthur"))
verifier("B2. « On … wrote: » sur deux lignes retire (Momboye)", S.v621_sans_citation(MOMBOYE).endswith("Ludivine"))
verifier("B3. le corps utile est intact", "local à Noiraigue" in S.v621_sans_citation(COOL)
         and "14H 30" in S.v621_sans_citation(MOMBOYE))
verifier("B4. le caractere ￼ disparait", "￼" not in S.v621_sans_citation(CALIENTE))

print("\nC. QUESTIONS EXPLICITES (CODE)")
verifier("C1. Cool-Ness : aucune question", S.v621_questions(COOL) == [])
verifier("C2. Momboye : la question d'echange", any("vive voix" in q for q in S.v621_questions(MOMBOYE)))
verifier("C3. Caliente : « wann hättest du zeit? »", any("zeit?" in q for q in S.v621_questions(CALIENTE)))
verifier("C4. « Merci de nous envoyer des liens » compte comme demande",
         S.v621_questions("Bonjour,\nMerci de nous envoyer des liens sur ce que vous faites.") != [])

print("\nD. DEJA DIT")
d = S.v621_deja_dit(fil)
verifier("D1. concept presente, video PROPOSEE (pas envoyee), echange propose",
         d["concept_presente"] and d["video_proposee"] and not d["video_envoyee"] and d["echange_propose"], d)
d2 = S.v621_deja_dit(fil2)
verifier("D2. media video envoye -> video_envoyee", d2["video_envoyee"])
verifier("D3. reponse de Bassi APRES le message -> deja_repondu_le", d2["deja_repondu_le"] == ["2026-10-15"])
verifier("D4. lien /api/files dans un texte -> video_envoyee",
         S.v621_deja_dit([{"de": "afroboost", "texte": "https://afroboost.com/api/files/x/video_x.mp4"}])["video_envoyee"])

print("\nE. L'INVITE")
c = S.p3ai_contexte(MSG_COOL, ACTION, [{"city": "Val-de-Travers (NE)", "category": "commerce"}], [], "a_repondre")
c["fil"], c["deja_dit"] = fil, d
c["contexte_commercial"] = S.v611_contexte_commercial(c, [{"city": "Val-de-Travers (NE)", "category": "commerce"}])
inv = S.p3ai_invite(c)
verifier("E1. le J0 et la relance entrent dans l'invite", "10 minutes" in inv and "relance J+3" in inv)
verifier("E2. dernier message en entier, sans citation", "local à Noiraigue" in inv and "a écrit" not in inv)
verifier("E3. « repondre avant de vendre »", "REPONDRE AVANT DE VENDRE" in inv)
verifier("E4. aucune repetition + deja dit (video proposee, echange propose)",
         "AUCUNE REPETITION" in inv and "video a deja ete PROPOSE" in inv and "echange / appel a deja ete propose" in inv)
verifier("E5. rien inventer (liste)", "ni nombre de participants" in inv and "ni duree de trajet" in inv)
verifier("E6. 3 a 8 phrases ; formules interdites", "3 a 8 phrases" in inv and "Excellente opportunite" in inv)
verifier("E7. garde-fous = limites, jamais obligation", "ils ne t'obligent a RIEN" in inv)
verifier("E8. V614 local : cours regulier seulement s'il veut decouvrir",
         "SEULEMENT s'il veut voir ou decouvrir" in inv and "Propose D'ABORD" not in inv)
verifier("E9. methode A-E + analyse dans le JSON", "METHODE" in inv and '"analyse"' in inv)
verifier("E10. champ a completer dans la langue du message (fr)", "[À COMPLÉTER : jour et heure]" in inv
         and "ZU ERGÄNZEN" not in inv)
cde = dict(c, body_text=CALIENTE)
verifier("E11. message allemand -> champ allemand seulement, et la demande de dispo est signalee",
         "[ZU ERGÄNZEN: Tag und Uhrzeit]" in S.p3ai_invite(cde) and "À COMPLÉTER" not in S.p3ai_invite(cde)
         and "IL TE DEMANDE TES DISPONIBILITES" in S.p3ai_invite(cde))
verifier("E12. V612 : contraintes = intervention SUR PLACE, pas un appel", "jamais un appel ou une visio" in inv)

print("\nF. AI_REPLY_CHECK — CONTROLES DU CODE")
ancien = ("Bonjour Arthur,\n\nMerci pour votre proposition concernant le local à Noiraigue. J’aimerais vous inviter à "
          "découvrir Afroboost lors d’un de mes cours réguliers à Neuchâtel, le mercredi à 18h45 ou le dimanche à 18h30."
          "\n\nCoach Bassi\nAfroboost")
verifier("F1. brouillon du 15/10 (Cool-Ness) : cours reguliers non demandes",
         "cours_reguliers_non_demandes" in S.v621_controle_deterministe(ancien, c))
bon = ("Bonjour Arthur,\n\nMerci pour l'information sur votre local à Noiraigue. Pourriez-vous m'indiquer sa capacité "
       "et les conditions de location ?\n\nBelle journée,\nCoach Bassi\nAfroboost")
verifier("F2. une reponse precise et courte : aucun probleme", S.v621_controle_deterministe(bon, c) == [],
         S.v621_controle_deterministe(bon, c))
verifier("F3. « voici une courte vidéo » alors que la video est deja proposee -> repetee",
         "video_repetee" in S.v621_controle_deterministe("Bonjour, voici une courte vidéo : https://x.test/v", c))
verifier("F4. formule convenue", "formule_convenue" in S.v621_controle_deterministe("Je suis ravi de votre retour.", c))
verifier("F5. heure inventee", "heure_inventee" in S.v621_controle_deterministe("Je passe à 16h15.", c))
verifier("F6. heure presente dans le fil -> pas inventee",
         "heure_inventee" not in S.v621_controle_deterministe("Je vous appelle à 14h30.", dict(c, body_text=MOMBOYE)))
verifier("F7. mois absent de la conversation -> date inventee",
         "date_inventee" in S.v621_controle_deterministe("Rendez-vous en janvier.", c))
verifier("F8. disponibilite affirmee -> inventee",
         "disponibilite_inventee" in S.v621_controle_deterministe("Je suis disponible jeudi.", c))
verifier("F9. creneau demande sans champ -> creneau_non_fourni ; avec champ -> rien",
         "creneau_non_fourni" in S.v621_controle_deterministe("Hallo Roger, sag mir wann.", cde)
         and "creneau_non_fourni" not in S.v621_controle_deterministe("Ich könnte am [ZU ERGÄNZEN: Tag und Uhrzeit].", cde))
verifier("F10. champ a completer sans demande de creneau -> inutile",
         "a_completer_inutile" in S.v621_controle_deterministe("Je propose [À COMPLÉTER : jour et heure].", c))
long_txt = "Bonjour,\n\n" + " ".join("Phrase numéro %d ici." % i for i in range(12)) + "\n\nCoach Bassi\nAfroboost"
verifier("F11. plus de 8 phrases -> trop long", "trop_long" in S.v621_controle_deterministe(long_txt, c))
cm = dict(c, body_text=MOMBOYE, fil=[{"de": "afroboost", "type": "manual_reply", "texte": "Je vous appelle demain à 14h30.",
                                       "apres_message": True, "quand": "2026-10-14T14:27:00"}])
cm["deja_dit"] = S.v621_deja_dit(cm["fil"])
p = S.v621_controle_deterministe("Je vous appelle demain à 14h30 comme convenu.", cm)
verifier("F12. deja repondu + reprise de l'heure -> deja_repondu + reponse_reprise",
         "deja_repondu" in p and "reponse_reprise" in p, p)


def relecture(sortie):
    async def _f(invite):
        APPELS_CTRL.append(invite)
        return json.dumps(sortie) if sortie is not None else ""
    return _f


APPELS_CTRL = []
_vrai = S.v621_appeler_controle
S.v621_appeler_controle = relecture({"verifications": {"rien_invente": True}, "problemes": ["cours non demandés"],
                                     "reponse_finale": bon})
txt, rap = asyncio.run(S.v621_ai_reply_check(c, ancien))
verifier("F13. relecture : reecriture retenue quand elle corrige", txt == bon and rap["reecrit"]
         and "cours_reguliers_non_demandes" in rap["controle_avant"] and rap["controle_apres"] == [], rap)
S.v621_appeler_controle = relecture({"reponse_finale": "Bonjour, je suis disponible jeudi à 16h15."})
txt, rap = asyncio.run(S.v621_ai_reply_check(c, bon))
verifier("F14. une reecriture qui AJOUTE une invention est rejetee", txt == bon and not rap["reecrit"], rap)
S.v621_appeler_controle = relecture({"reponse_finale": "Hallo Roger, sag mir wann."})
garde = "Hallo Roger,\nIch könnte am [ZU ERGÄNZEN: Tag und Uhrzeit].\nCoach Bassi\nAfroboost"
txt, rap = asyncio.run(S.v621_ai_reply_check(cde, garde))
verifier("F15. une reecriture qui retire le champ a completer est rejetee", txt == garde)
APPELS_CTRL.clear()
S.v621_appeler_controle = relecture({"reponse_finale": ancien})
txt, rap = asyncio.run(S.v621_ai_reply_check(c, ancien))
verifier("F16. problemes certains + relecture qui recopie : une 2e relecture, pas plus", len(APPELS_CTRL) == 2)
S.v621_appeler_controle = relecture(None)
txt, rap = asyncio.run(S.v621_ai_reply_check(c, ancien))
verifier("F17. relecture indisponible : le brouillon reste, ses problemes sont nommes",
         txt == ancien and rap["relecture_modele"] is False and "cours_reguliers_non_demandes" in rap["controle_apres"])
S.v621_appeler_controle = _vrai
verifier("F18. sans cle OpenAI, la relecture ne sort pas (rend '')", asyncio.run(_vrai("x")) == "" and not _TENT)

print("\nG. UN CHAMP A COMPLETER NE PART JAMAIS")
verifier("G1. detection fr / de / en", S.v621_a_completer("[À COMPLÉTER : x]") and S.v621_a_completer("[ZU ERGÄNZEN: y]")
         and S.v621_a_completer("[TO COMPLETE: z]") and not S.v621_a_completer("Bonjour [Arthur]"))
src = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
i = src.index("async def p3ai4_envoyer_reponse")
verifier("G2. la route d'envoi refuse (409) un texte avec champ a completer, AVANT le verrou",
         src.index("if v621_a_completer(texte)", i) < src.index("insert_one(dict(trace))", i))
b = S.p3ai_brouillon_depuis(cde, {"reponse_proposee": garde, "intention": "positif", "analyse": {
    "intentions": ["demande_date", "inconnue"], "questions": ["wann?"], "action": "repondre"}}, "x", "t")
verifier("G3. le brouillon porte « créneau à compléter » en validation", "créneau à compléter" in b["motifs_validation"])
verifier("G4. analyse bornee (intention inconnue retiree, action fermee)",
         b["analyse"]["intentions"] == ["demande_date"] and b["analyse"]["action"] == "repondre")
verifier("G5. questions explicites du code jointes au brouillon", b["questions_explicites"] and b["modele"] == "gpt-4.1")

print("\nH. LA ROUTE D'ANALYSE (modele et relecture simules)")


class Curseur:
    def __init__(s, d): s.d = d
    async def to_list(s, n=None): return list(s.d)


class Col:
    def __init__(s, d=None): s.docs, s.ecritures = list(d or []), 0
    def find(s, q=None, p=None, *a, **k):
        def ok(doc):
            for kk, v in (q or {}).items():
                if isinstance(v, dict):
                    if "$in" in v and doc.get(kk) not in v["$in"]: return False
                    if "$ne" in v and doc.get(kk) == v["$ne"]: return False
                elif doc.get(kk) != v: return False
            return True
        return Curseur([x for x in s.docs if ok(x)])
    async def find_one(s, q=None, p=None, *a, **k):
        r = await s.find(q).to_list()
        return r[0] if r else None
    async def insert_one(s, d): s.ecritures += 1; s.docs.append(d)
    async def update_one(s, q, u, upsert=False): s.ecritures += 1


class Base(dict):
    def __missing__(s, k): s[k] = Col(); return s[k]


base = Base()
base[S.P3U2_COLLECTION] = Col([dict(MSG_COOL)])
INV = []


async def faux_modele(invite, ton=""):
    INV.append(invite)
    return json.dumps({"analyse": {"intentions": ["proposition"], "questions": [], "infos_nouvelles": ["local à Noiraigue"],
                                   "action": "demander_precision"}, "intention": "positif", "langue": "fr",
                       "resume": "r", "demande": "d", "prochaine_action": "p", "reponse_proposee": ancien})


async def faux_auth(r): return "coach@exemple.test"
async def faux_dossier(i, e): return {"message": dict(MSG_COOL), "action": dict(ACTION), "fiches": [{"city": "Val-de-Travers (NE)"}]}
async def faux_notes(*a, **k): return []


class Req:
    headers = {"content-length": "0"}
    async def json(self): return {}


sauv = (S.db, S.p3ai_appeler_modele, S._v309_require_coach_or_admin, S.p3ai_dossier, S.p3ai_notes_de, S.v621_appeler_controle)
S.db, S.p3ai_appeler_modele, S._v309_require_coach_or_admin, S.p3ai_dossier, S.p3ai_notes_de = \
    base, faux_modele, faux_auth, faux_dossier, faux_notes
S.v621_appeler_controle = relecture({"verifications": {"rien_de_non_demande": False}, "problemes": ["cours"],
                                     "reponse_finale": bon})
r = asyncio.run(S.p3ai_analyser("inb-c", Req()))
S.db, S.p3ai_appeler_modele, S._v309_require_coach_or_admin, S.p3ai_dossier, S.p3ai_notes_de, S.v621_appeler_controle = sauv
br = r["brouillon"]
verifier("H1. le modele a recu le J0 et la relance", "10 minutes" in INV[0] and "relance J+3" in INV[0])
verifier("H2. le brouillon affiche est la version RELUE", br["reponse_proposee"] == bon and br["texte_modele"] == bon)
verifier("H3. analyse + rapport AI_REPLY_CHECK ranges", br["analyse"]["action"] == "demander_precision"
         and br["controle_ia"]["reecrit"] and "cours_reguliers_non_demandes" in br["controle_ia"]["controle_avant"])
verifier("H4. aucun envoi ecrit", base[S.P3AI4_COLLECTION].ecritures == 0)
verifier("H5. aucune sortie reseau", not _TENT, _TENT)

ok = sum(R)
print("\nV621 GENERATEUR — %d/%d verifications (aucun appel IA reel, aucun e-mail)" % (ok, len(R)))
sys.exit(0 if ok == len(R) else 1)
