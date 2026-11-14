# -*- coding: utf-8 -*-
"""V670 — /api/translate : cache des contenus PUBLICS, débit par IP, budget quotidien.

Ce que ces bancs tiennent :
  * un contenu public (`cache: true`) n'est traduit qu'UNE fois : la seconde demande vient
    du cache, sans appel IA ;
  * un message de chat (pas de `cache`) n'est JAMAIS lu ni écrit dans le cache — il est privé ;
  * la clé de cache ne confond pas « 5 € offerts » et « 5 offerts », ni deux langues ;
  * le texte source n'est PAS stocké (seulement son empreinte SHA-256) ;
  * le lexique vérifié reste prioritaire et gratuit ;
  * seul l'appel IA est limité (20/min/IP, 200/jour/IP, budget global) : cache et lexique
    ne le sont jamais ;
  * une panne de base ne casse pas la traduction ; une panne IA ne remplit pas le cache.

AUCUNE BASE RÉELLE, AUCUN RÉSEAU, AUCUN APPEL IA PAYANT : l'IA est un faux qui compte ses appels.
    python3 tests/test_traduction_cache_v670.py
"""
import asyncio
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=300")
os.environ.setdefault("DB_NAME", "test_v670")
os.environ.setdefault("JWT_SECRET", "test_secret_v670")
# Une clé BIDON : elle ne sert qu'à franchir le contrôle de présence. Aucun appel réseau n'est
# possible : `openai.OpenAI` est remplacé plus bas par un faux.
os.environ["OPENAI_API_KEY"] = "cle-de-test-jamais-envoyee"

import logging
logging.disable(logging.CRITICAL)
import api.server as S
from fastapi import HTTPException
import openai

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


# ── Doubles ────────────────────────────────────────────────────────────────
class FauxIA:
    appels = 0
    echec = False
    vide = False

    def __init__(self, *a, **k):
        self.chat = self
        self.completions = self

    def create(self, **kw):
        FauxIA.appels += 1
        if FauxIA.echec:
            raise RuntimeError("panne simulee")
        texte = kw["messages"][-1]["content"]
        sortie = "" if FauxIA.vide else "[traduit] " + texte
        msg = type("M", (), {"content": sortie})()
        return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()


openai.OpenAI = FauxIA


class FausseCollection:
    def __init__(self, base):
        self.base = base
        self.docs = {}
        self.ecritures = 0

    async def find_one(self, requete):
        if self.base.panne_lecture:
            raise RuntimeError("base injoignable")
        return self.docs.get(requete.get("_id"))

    async def update_one(self, requete, maj, upsert=False):
        if self.base.panne_ecriture:
            raise RuntimeError("base en lecture seule")
        self.ecritures += 1
        doc = self.docs.setdefault(requete["_id"], {"_id": requete["_id"]})
        doc.update(maj.get("$set", {}))


class FausseBase:
    def __init__(self):
        self.panne_lecture = False
        self.panne_ecriture = False
        self.cols = {}

    def __getitem__(self, nom):
        return self.cols.setdefault(nom, FausseCollection(self))


class FausseRequete:
    def __init__(self, corps, ip="203.0.113.7"):
        self._corps = corps
        self.headers = {"CF-Connecting-IP": ip}
        self.client = None

    async def json(self):
        return self._corps


def remise_a_zero():
    FauxIA.appels = 0
    FauxIA.echec = False
    FauxIA.vide = False
    S._V670_TRAD_IP.clear()
    S._V670_TRAD_BUDGET.update({"jour": None, "n": 0})
    os.environ.pop("TRANSLATE_AI_DAILY_BUDGET", None)
    base = FausseBase()
    S.db = base
    return base


def appeler(corps, ip="203.0.113.7"):
    try:
        return asyncio.run(S.translate_text(FausseRequete(corps, ip))), None
    except HTTPException as e:
        return None, e.status_code


PUBLIC = {"text": "Cours de danse afrobeat du samedi", "target_lang": "en", "cache": True}

# ── 1. Contenu public : une seule traduction IA, puis le cache ─────────────
base = remise_a_zero()
r1, e1 = appeler(PUBLIC)
r2, e2 = appeler(PUBLIC)
verifier("PUBLIC 1 — 1re demande : traduite par l'IA", r1 and r1["source"] == "ia" and not r1.get("cached"))
verifier("PUBLIC 2 — 2de demande identique : vient du CACHE", r2 and r2["source"] == "cache" and r2["cached"] is True)
verifier("PUBLIC 3 — la même traduction est rendue", r1 and r2 and r1["translation"] == r2["translation"])
verifier("PUBLIC 4 — UN SEUL appel IA pour deux demandes", FauxIA.appels == 1, FauxIA.appels)
for _ in range(5):
    appeler(PUBLIC)
verifier("PUBLIC 5 — sept demandes, toujours UN seul appel IA", FauxIA.appels == 1, FauxIA.appels)

# ── 2. Vie privée : un message de chat n'est jamais en cache ───────────────
base = remise_a_zero()
chat = {"text": "Salut, je serai en retard ce soir", "target_lang": "en"}
appeler(chat); appeler(chat)
col = base["translation_cache"]
verifier("PRIVÉ 1 — sans `cache`, chaque demande appelle l'IA (rien n'est mémorisé)", FauxIA.appels == 2, FauxIA.appels)
verifier("PRIVÉ 2 — aucune écriture dans le cache pour un message de chat", col.ecritures == 0 and not col.docs)
base = remise_a_zero()
appeler({"text": "message", "target_lang": "en", "cache": "true"})
appeler({"text": "message", "target_lang": "en", "cache": 1})
verifier("PRIVÉ 3 — `cache` doit être exactement true (ni « true », ni 1)", base["translation_cache"].ecritures == 0)

# ── 3. La clé de cache ne confond rien ─────────────────────────────────────
base = remise_a_zero()
appeler({"text": "5 € offerts", "target_lang": "en", "cache": True})
appeler({"text": "5 offerts", "target_lang": "en", "cache": True})
verifier("CLÉ 1 — « 5 € offerts » et « 5 offerts » sont deux textes (pas de normalisation agressive)", FauxIA.appels == 2, FauxIA.appels)
appeler({"text": "5 € offerts", "target_lang": "de", "cache": True})
verifier("CLÉ 2 — la langue cible fait partie de la clé", FauxIA.appels == 3, FauxIA.appels)
appeler({"text": "  5 €   offerts  ", "target_lang": "en", "cache": True})
verifier("CLÉ 3 — les espaces superflus ne créent pas un doublon", FauxIA.appels == 3, FauxIA.appels)
verifier("CLÉ 4 — la clé est un SHA-256 hexadécimal de 64 caractères",
         len(S._v670_cle_cache("en", "x")) == 64 and all(c in "0123456789abcdef" for c in S._v670_cle_cache("en", "x")))
verifier("CLÉ 5 — déterministe, et sensible à la casse",
         S._v670_cle_cache("en", "Abc") == S._v670_cle_cache("en", "Abc") != S._v670_cle_cache("en", "abc"))

# ── 4. Le texte source n'est pas stocké ────────────────────────────────────
base = remise_a_zero()
secret = "Offre confidentielle Dupont 0791234567"
appeler({"text": secret, "target_lang": "en", "cache": True})
doc = list(base["translation_cache"].docs.values())[0]
verifier("STOCKAGE 1 — l'empreinte est stockée, le TEXTE SOURCE ne l'est pas",
         secret not in str(doc.get("_id", "")) and all(secret not in str(v) or k == "translation" for k, v in doc.items() if k != "translation"))
verifier("STOCKAGE 2 — champs attendus seulement", set(doc) == {"_id", "lang", "translation", "approximate", "model", "created_at"}, sorted(doc))

# ── 5. Lexique vérifié : prioritaire, gratuit, sans écriture ───────────────
base = remise_a_zero()
r, e = appeler({"text": "bonjour", "target_lang": "bas", "cache": True})
verifier("LEXIQUE 1 — « bonjour » en bàsàa vient du lexique vérifié", r and r["source"] == "lexique" and r["translation"] == "mɛ̀ ǹyega", r)
verifier("LEXIQUE 2 — aucun appel IA, aucune écriture en cache", FauxIA.appels == 0 and base["translation_cache"].ecritures == 0)

# ── 6. Débit par IP : seul l'appel IA est limité ───────────────────────────
base = remise_a_zero()
codes = []
for i in range(S._V670_TRAD_IP_MINUTE + 3):
    _, e = appeler({"text": f"texte numero {i}", "target_lang": "en", "cache": True})
    codes.append(e)
verifier("DÉBIT 1 — 20 appels IA par minute passent", all(c is None for c in codes[:S._V670_TRAD_IP_MINUTE]), codes)
verifier("DÉBIT 2 — le 21e est refusé en 429", codes[S._V670_TRAD_IP_MINUTE] == 429, codes[S._V670_TRAD_IP_MINUTE])
n_ia = FauxIA.appels
_, e = appeler({"text": "autre texte", "target_lang": "en", "cache": True}, ip="198.51.100.9")
verifier("DÉBIT 3 — une AUTRE adresse n'est pas touchée", e is None)
r, e = appeler({"text": "texte numero 0", "target_lang": "en", "cache": True})
verifier("DÉBIT 4 — un texte DÉJÀ en cache reste servi à l'adresse limitée (le cache est gratuit)", e is None and r["source"] == "cache", (r, e))
r, e = appeler({"text": "bonjour", "target_lang": "bas"})
verifier("DÉBIT 5 — le lexique reste servi à l'adresse limitée", e is None and r["source"] == "lexique")
verifier("DÉBIT 6 — les refus n'appellent PAS l'IA", FauxIA.appels == n_ia + 1, (FauxIA.appels, n_ia))

# ── 7. Budget quotidien global ─────────────────────────────────────────────
base = remise_a_zero()
os.environ["TRANSLATE_AI_DAILY_BUDGET"] = "3"
sc = []
for i in range(5):
    _, e = appeler({"text": f"budget {i}", "target_lang": "en", "cache": True}, ip=f"198.51.100.{i + 10}")
    sc.append(e)
verifier("BUDGET 1 — trois appels IA, puis refus 429 pour tout le monde", sc == [None, None, None, 429, 429], sc)
r, e = appeler({"text": "budget 0", "target_lang": "en", "cache": True}, ip="198.51.100.99")
verifier("BUDGET 2 — le cache reste servi budget épuisé", e is None and r["source"] == "cache")
os.environ["TRANSLATE_AI_DAILY_BUDGET"] = "0"
S._V670_TRAD_BUDGET.update({"jour": None, "n": 0})
_, e = appeler({"text": "tout nouveau", "target_lang": "en"})
verifier("BUDGET 3 — budget à 0 : plus aucun appel IA", e == 429 and FauxIA.appels == 3, (e, FauxIA.appels))
os.environ["TRANSLATE_AI_DAILY_BUDGET"] = "pas un nombre"
verifier("BUDGET 4 — une valeur invalide retombe sur 1500 (jamais de plantage)", S._v670_budget_jour() == 1500)

# ── 8. Pannes : la base ne casse pas la traduction, l'IA ne remplit pas le cache ──
base = remise_a_zero()
base.panne_lecture = True
r, e = appeler(PUBLIC)
verifier("PANNE 1 — base illisible : la traduction fonctionne quand même", e is None and r and r["source"] == "ia", (r, e))
base = remise_a_zero()
base.panne_ecriture = True
r, e = appeler(PUBLIC)
verifier("PANNE 2 — base non inscriptible : la traduction est rendue, sans exception", e is None and r and r["translation"], (r, e))
base = remise_a_zero()
FauxIA.echec = True
r, e = appeler(PUBLIC)
verifier("PANNE 3 — l'IA tombe : erreur 502 comme avant", e == 502, e)
verifier("PANNE 4 — rien n'est mis en cache après une panne IA", base["translation_cache"].ecritures == 0)
base = remise_a_zero()
FauxIA.vide = True
r, e = appeler(PUBLIC)
verifier("PANNE 5 — une traduction VIDE n'est jamais mise en cache", base["translation_cache"].ecritures == 0, (r, base["translation_cache"].ecritures))

# ── 9. Contrats inchangés ──────────────────────────────────────────────────
base = remise_a_zero()
r, e = appeler({"text": "", "target_lang": "en"})
verifier("CONTRAT 1 — texte vide : réponse vide, sans appel IA", r == {"translation": ""} and FauxIA.appels == 0)
_, e = appeler({"text": "Bonjour tout le monde", "target_lang": "klingon"})
verifier("CONTRAT 2 — langue inconnue : 400 comme avant", e == 400, e)
r, e = appeler({"text": "Bonjour tout le monde", "target_lang": "wo"})
verifier("CONTRAT 3 — la réponse garde `translation`, `target_lang`, `approximate`, `source`",
         r and {"translation", "target_lang", "approximate", "source"} <= set(r), r)

ok = sum(1 for _, c, _ in RESULTATS if c)
for nom, cond, detail in RESULTATS:
    print("  %s  %s%s" % ("OK  " if cond else "ECHEC", nom, ("  <- " + str(detail)) if (detail and not cond) else ""))
print("\n%d/%d" % (ok, len(RESULTATS)))
sys.exit(0 if ok == len(RESULTATS) else 1)
