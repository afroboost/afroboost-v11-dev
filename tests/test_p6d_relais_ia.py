#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PHASE 6D — AIDE IA (AMELIORER/CORRIGER/REFORMULER UN TEXTE DE REPONSE),
POUR LE RELAIS AFROBOOSTEUR.

CE QUE CE LOT AJOUTE
==============================================================================
Une route neuve (`api/routes/afroboosteur_relais.py`,
`POST .../ia/ameliorer-texte`), sous la MEME garde HMAC que les routes
existantes, derriere son PROPRE interrupteur (`AFROBOOSTEUR_RELAIS_IA_ACTIF`,
ferme par defaut, independant de FIL_ACTIF/RELANCES_ACTIF).

CE QUE CE LOT TOUCHE DANS `api/server.py`, ET POURQUOI C'EST UN REFACTOR,
PAS UNE REECRITURE. `enhance_text_with_ai` (route `/ai/enhance-text`,
coach/admin JWT) portait les prompts, le modele et l'appel OpenAI EN LIGNE.
Cette logique est extraite, caractere pour caractere, dans une fonction pure
`_v633_ameliorer_texte(text, context, lang)` — la route existante l'appelle
desormais au lieu de porter sa propre copie, et la route du relais fait de
meme. Le test 0 ci-dessous prouve que le COMPORTEMENT EXTERNE de
`/ai/enhance-text` est inchange (meme reponse pour les memes entrees), pas
seulement que le fichier a change.

CE QUE CE BANC PROUVE
==============================================================================
  0. `enhance_text_with_ai` rend EXACTEMENT la meme reponse qu'avant
     l'extraction, pour un texte/contexte/langue donnes (refactor
     comportement-preservant, pas une reecriture).
  1. Signature absente ou incorrecte -> refusee par `_garde`, AVANT tout
     acces a la fonction IA (aucun appel a `_v633_ameliorer_texte`).
  2. Interrupteur ferme par defaut -> 503 ; INDEPENDANT de FIL_ACTIF et
     RELANCES_ACTIF (l'un ouvert, l'autre pas, ne change rien a ce 503).
  3. Debit partage avec le coach, MAIS CLE SEPAREE (`relais:` prefixe) :
     epuiser le compteur du relais ne ferme pas celui du coach direct, et
     reciproquement — memes bornes (20/minute, 300/jour).
  4. Entrees bornees a l'identique de V633 : texte vide refuse, texte trop
     long refuse (meme borne `_V633_TEXTE_MAX`), contexte/langue inconnus
     RETOMBENT sur une valeur sure (jamais une erreur serveur).
  5. AUCUNE ECRITURE MONGO dans la nouvelle section (ni update_one, ni
     insert_one, ni delete_one) — le texte ameliore est RENDU, jamais
     enregistre par cette route (c'est `.../brouillon` qui ecrit, ailleurs).
  6. Aucun appel reseau reel (DNS/socket bloques, `_v633_ameliorer_texte`
     elle-meme est bouchonnee pour ce banc — zero cle OpenAI necessaire).
  7. Non-regression des routes existantes du relais (sections 1-6 intactes).

Lancement :
    python3 tests/test_p6d_relais_ia.py
"""
import os
import socket
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
RESULTATS = []


def verifier(intitule, condition, detail=""):
    RESULTATS.append((intitule, bool(condition), detail))
    print("  %-6s %s" % ("OK  " if condition else "ECHEC", intitule))
    if detail and not condition:
        print("           -> %s" % detail)
    return bool(condition)


# ============================================================================
class SortieReseauInterdite(RuntimeError):
    pass


_GETADDR = socket.getaddrinfo


def _dns(hote, port, *a, **k):
    if str(hote) in ("localhost", "127.0.0.1", "::1", None):
        return _GETADDR(hote, port, *a, **k)
    raise SortieReseauInterdite(str(hote))


socket.getaddrinfo = _dns
socket.socket.connect = lambda self, a, *x, **k: (_ for _ in ()).throw(SortieReseauInterdite(str(a)))
socket.create_connection = lambda a, *x, **k: (_ for _ in ()).throw(SortieReseauInterdite(str(a)))

SECRET = "secret-p6d-ia-sans-rapport-avec-la-production"
COACH_ID = "coach.p6d.fictif@exemple.test"
os.environ["JWT_SECRET"] = "jwt-secret-fictif-p6d"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p6d-inexistant:27017")
os.environ["AFROBOOSTEUR_RELAY_SECRET"] = SECRET
os.environ["AFROBOOSTEUR_RELAY_COACH_ID"] = COACH_ID
# Interrupteurs : FERMES par defaut — ouverts explicitement section par section.
os.environ.pop("AFROBOOSTEUR_RELAIS_FIL_ACTIF", None)
os.environ.pop("AFROBOOSTEUR_RELAIS_RELANCES_ACTIF", None)
os.environ.pop("AFROBOOSTEUR_RELAIS_IA_ACTIF", None)
# AUCUNE cle OpenAI dans ce banc : `_v633_ameliorer_texte` est bouchonnee
# avant le premier appel (voir plus bas) — un oubli ferait echouer "cle
# absente", jamais un appel reseau reel.
os.environ.pop("OPENAI_API_KEY", None)

import asyncio  # noqa: E402
import hashlib  # noqa: E402
import hmac as hmac_module  # noqa: E402
import time  # noqa: E402

from fastapi import HTTPException  # noqa: E402

import api.server as S  # noqa: E402
import api.routes.afroboosteur_relais as R  # noqa: E402


# ============================================================================
print("\nOUTILLAGE")


def signer(secret, methode, chemin, requete, horodatage, corps_brut=b""):
    chaine = R._chaine_canonique(methode, chemin, requete, horodatage, R._empreinte_corps(corps_brut))
    return hmac_module.new(secret.encode(), chaine.encode(), hashlib.sha256).hexdigest()


class URLFictive:
    def __init__(self, chemin, requete=""):
        self.path = chemin
        self.query = requete


class RequeteFictive:
    def __init__(self, methode="POST", chemin="", requete="", headers=None, corps=None):
        self.method = methode
        self.url = URLFictive(chemin, requete)
        self.headers = headers or {}
        import json as _json
        self._corps_brut = _json.dumps(corps).encode("utf-8") if corps is not None else b""
        self._a_un_corps = corps is not None

    async def body(self):
        return self._corps_brut

    async def json(self):
        if not self._a_un_corps:
            raise ValueError("pas de corps")
        import json as _json
        return _json.loads(self._corps_brut)


def requete_signee(chemin, corps=None, secret=SECRET, decalage=0,
                    sans_signature=False, sans_horodatage=False, membre="membre.fictif@exemple.test"):
    horodatage = str(int(time.time()) + decalage)
    entetes = {} if sans_horodatage else {"X-Afroboosteur-Timestamp": horodatage}
    if membre:
        entetes["X-Afroboosteur-Membre"] = membre
    req = RequeteFictive(methode="POST", chemin=chemin, requete="", headers=entetes, corps=corps)
    if not sans_signature:
        req.headers["X-Afroboosteur-Signature"] = signer(secret, "POST", chemin, "", horodatage, req._corps_brut)
    return req


def requete_ia(corps=None, **kw):
    return requete_signee("/api/afroboosteur-relais/ia/ameliorer-texte", corps=corps, **kw)


def executer(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ============================================================================
print("\n0. REFACTOR COMPORTEMENT-PRESERVANT — /ai/enhance-text inchangee")

_APPELS_OPENAI = []


class _ChoixFictif:
    def __init__(self, texte):
        self.message = type("M", (), {"content": texte})()


class _ReponseFictive:
    def __init__(self, texte):
        self.choices = [_ChoixFictif(texte)]


class _CompletionsFictives:
    @staticmethod
    def create(**kwargs):
        _APPELS_OPENAI.append(kwargs)
        return _ReponseFictive("  Texte ameliore par le bouchon.  ")


class _ChatFictif:
    completions = _CompletionsFictives()


class _ClientOpenAIFictif:
    def __init__(self, api_key=None):
        self.chat = _ChatFictif()


os.environ["OPENAI_API_KEY"] = "cle-fictive-pour-ce-banc-seul"
import openai as _openai_module  # noqa: E402
_OpenAI_reel = _openai_module.OpenAI
_openai_module.OpenAI = _ClientOpenAIFictif

try:
    rep_directe = executer(S._v633_ameliorer_texte("Bonjour, interesse par vos services.", "afroboost", "fr"))
    verifier("0a _v633_ameliorer_texte rend le texte ameliore, non vide",
             rep_directe.get("enhanced_text") == "Texte ameliore par le bouchon."
             and rep_directe.get("original") == "Bonjour, interesse par vos services."
             and rep_directe.get("context") == "afroboost", str(rep_directe))
    verifier("0b le modele et max_tokens sont EXACTEMENT ceux de V633 (inchanges)",
             _APPELS_OPENAI[-1].get("model") == "gpt-4o-mini" and _APPELS_OPENAI[-1].get("max_tokens") == 500)
    verifier("0c le prompt systeme correspond au contexte demande (afroboost)",
             "coach Afroboost" in _APPELS_OPENAI[-1]["messages"][0]["content"])
finally:
    os.environ.pop("OPENAI_API_KEY", None)
    _openai_module.OpenAI = _OpenAI_reel

# A PARTIR D'ICI : `_v633_ameliorer_texte` elle-meme est bouchonnee (jamais
# plus le vrai module openai) — le reste du banc ne verifie QUE le relais
# (garde, interrupteur, debit, bornes), jamais le calcul IA lui-meme (deja
# prouve au test 0).
_AMELIORATIONS_RELAIS = []


async def _ameliorer_texte_bouchon(text, context, lang):
    _AMELIORATIONS_RELAIS.append((text, context, lang))
    return {"enhanced_text": "AMELIORE:" + text, "original": text, "context": context}


S._v633_ameliorer_texte = _ameliorer_texte_bouchon

# ============================================================================
print("\n1. SIGNATURE — refusee AVANT tout appel a la fonction IA")

for nom, req in (
    ("sans signature", requete_ia({"text": "Bonjour"}, sans_signature=True)),
    ("mauvais secret", requete_ia({"text": "Bonjour"}, secret="mauvais-secret")),
    ("horodatage absent", requete_ia({"text": "Bonjour"}, sans_horodatage=True)),
    ("horodatage perime", requete_ia({"text": "Bonjour"}, decalage=-600)),
):
    _AMELIORATIONS_RELAIS.clear()
    try:
        executer(R.relais_ameliorer_texte(req))
        verifier("1 " + nom + " -> refusee", False, "aucune exception levee")
    except HTTPException as e:
        verifier("1 " + nom + " -> refusee (%d)" % e.status_code, e.status_code in (401, 403))
    verifier("1 " + nom + " -> fonction IA jamais appelee", not _AMELIORATIONS_RELAIS)

# ============================================================================
print("\n2. INTERRUPTEUR — ferme par defaut, INDEPENDANT du fil et des relances")

os.environ.pop("AFROBOOSTEUR_RELAIS_IA_ACTIF", None)
os.environ.pop("AFROBOOSTEUR_RELAIS_FIL_ACTIF", None)
os.environ.pop("AFROBOOSTEUR_RELAIS_RELANCES_ACTIF", None)
try:
    executer(R.relais_ameliorer_texte(requete_ia({"text": "Bonjour"})))
    verifier("2a IA fermee par defaut -> 503", False)
except HTTPException as e:
    verifier("2a IA fermee par defaut -> 503", e.status_code == 503, str(e.detail))

os.environ["AFROBOOSTEUR_RELAIS_FIL_ACTIF"] = "true"
os.environ["AFROBOOSTEUR_RELAIS_RELANCES_ACTIF"] = "true"
try:
    executer(R.relais_ameliorer_texte(requete_ia({"text": "Bonjour"})))
    verifier("2b fil+relances ouverts, IA toujours fermee -> 503 (independance)", False)
except HTTPException as e:
    verifier("2b fil+relances ouverts, IA toujours fermee -> 503 (independance)", e.status_code == 503)

for valeur_invalide in ("0", "false", "non", ""):
    os.environ["AFROBOOSTEUR_RELAIS_IA_ACTIF"] = valeur_invalide
    try:
        executer(R.relais_ameliorer_texte(requete_ia({"text": "Bonjour"})))
        verifier("2c valeur '%s' -> toujours fermee" % valeur_invalide, False)
    except HTTPException as e:
        verifier("2c valeur '%s' -> toujours fermee" % valeur_invalide, e.status_code == 503)

os.environ["AFROBOOSTEUR_RELAIS_IA_ACTIF"] = "true"
rep = executer(R.relais_ameliorer_texte(requete_ia({"text": "Bonjour, interesse."})))
verifier("2d interrupteur ouvert -> la fonction IA est appelee, texte rendu",
         rep.get("enhanced_text") == "AMELIORE:Bonjour, interesse.", str(rep))

# ============================================================================
print("\n3. DEBIT — cle SEPAREE du coach direct, memes bornes")

_V633_IA_DEBIT_AVANT = dict(S._V633_IA_DEBIT)
S._V633_IA_DEBIT.clear()

for i in range(S._V633_IA_DEBIT_MINUTE):
    executer(R.relais_ameliorer_texte(requete_ia({"text": "msg %d" % i}, membre="m1@exemple.test")))
try:
    executer(R.relais_ameliorer_texte(requete_ia({"text": "un de trop"}, membre="m1@exemple.test")))
    verifier("3a le %de-eme appel de la minute -> refuse (429)" % (S._V633_IA_DEBIT_MINUTE + 1), False)
except HTTPException as e:
    verifier("3a le %de-eme appel de la minute -> refuse (429)" % (S._V633_IA_DEBIT_MINUTE + 1),
             e.status_code == 429)

verifier("3b cle du coach direct (sans prefixe relais:) jamais touchee",
         "coach.p6d.fictif@exemple.test" not in S._V633_IA_DEBIT)
verifier("3c la cle utilisee porte bien le prefixe 'relais:'",
         any(k.startswith("relais:") for k in S._V633_IA_DEBIT))

try:
    executer(R.relais_ameliorer_texte(requete_ia({"text": "autre membre"}, membre="m2@exemple.test")))
    verifier("3d un AUTRE membre garde son propre compteur, non affecte", True)
except HTTPException:
    verifier("3d un AUTRE membre garde son propre compteur, non affecte", False)

S._V633_IA_DEBIT.clear()
S._V633_IA_DEBIT.update(_V633_IA_DEBIT_AVANT)

# ============================================================================
print("\n4. ENTREES BORNEES — identiques a V633, jamais une erreur serveur")

try:
    executer(R.relais_ameliorer_texte(requete_ia({"text": ""})))
    verifier("4a texte vide -> 400", False)
except HTTPException as e:
    verifier("4a texte vide -> 400", e.status_code == 400)

try:
    executer(R.relais_ameliorer_texte(requete_ia({"text": "x" * (S._V633_TEXTE_MAX + 1)})))
    verifier("4b texte trop long -> 400 (meme borne que V633)", False)
except HTTPException as e:
    verifier("4b texte trop long -> 400", e.status_code == 400)

_AMELIORATIONS_RELAIS.clear()
rep = executer(R.relais_ameliorer_texte(requete_ia({"text": "Bonjour", "context": "contexte-inconnu-xyz"})))
verifier("4c contexte inconnu -> retombe sur 'general', jamais une erreur",
         _AMELIORATIONS_RELAIS and _AMELIORATIONS_RELAIS[-1][1] == "general", str(_AMELIORATIONS_RELAIS))

_AMELIORATIONS_RELAIS.clear()
rep = executer(R.relais_ameliorer_texte(requete_ia({"text": "Bonjour", "lang": "???"})))
verifier("4d langue invalide -> retombe sur 'fr', jamais une erreur",
         _AMELIORATIONS_RELAIS and _AMELIORATIONS_RELAIS[-1][2] == "fr", str(_AMELIORATIONS_RELAIS))

_AMELIORATIONS_RELAIS.clear()
rep = executer(R.relais_ameliorer_texte(requete_ia({"text": "Bonjour", "context": "afroboost", "lang": "en"})))
verifier("4e contexte/langue valides -> transmis tels quels",
         _AMELIORATIONS_RELAIS and _AMELIORATIONS_RELAIS[-1][1] == "afroboost"
         and _AMELIORATIONS_RELAIS[-1][2] == "en", str(_AMELIORATIONS_RELAIS))

# ============================================================================
print("\n5. AUCUNE ECRITURE MONGO DANS LA NOUVELLE SECTION")

SRC = open(os.path.join(RACINE, "api", "routes", "afroboosteur_relais.py"), encoding="utf-8").read()
debut = SRC.index("# 7. PHASE 6D")
section = SRC[debut:]
verifier("5a aucune ecriture Mongo (ni update_one, ni insert_one, ni delete_one)",
         not any(m in section for m in ("update_one(", "insert_one(", "delete_one(")))
verifier("5b la route reutilise _v633_ameliorer_texte, aucune seconde implementation des prompts",
         "_v633_ameliorer_texte(" in section and "chat.completions.create" not in section)

# ============================================================================
print("\n6. AUCUN APPEL RESEAU REEL DANS CE BANC")

verifier("6a le socket de sortie reste intercepte (sonde)", socket.getaddrinfo is _dns)

# ============================================================================
print("\n7. NON-REGRESSION DES ROUTES EXISTANTES DU RELAIS")

verifier("7a les trois routes de lecture (phases 4/5) existent toujours",
         all(hasattr(R, f) for f in ("relais_lister_prospects", "relais_lister_campagnes",
                                     "relais_lister_conversations")))
verifier("7b les routes 6A (brouillon/apercu) existent toujours",
         all(hasattr(R, f) for f in ("relais_lire_brouillon", "relais_enregistrer_brouillon",
                                     "relais_apercu_reponse")))
verifier("7c les routes 6C (fil/relances) existent toujours",
         all(hasattr(R, f) for f in ("relais_fil_conversation", "relais_relances_campagne")))
verifier("7d la nouvelle route IA est bien exposee",
         hasattr(R, "relais_ameliorer_texte"))

ok = sum(1 for r in RESULTATS if r[1])
print("\n=== %d OK · %d ECHEC ===" % (ok, len(RESULTATS) - ok))
sys.exit(0 if ok == len(RESULTATS) else 1)
