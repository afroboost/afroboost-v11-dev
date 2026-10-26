#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P4-RELAIS — LA PASSERELLE LECTURE SEULE VERS AFROBOOSTEUR.COM.

CE QUE LE LOT AJOUTE
==============================================================================
Trois routes GET (`api/routes/afroboosteur_relais.py`) : prospects, campagnes,
conversations. Gardees par un secret DEDIE (`AFROBOOSTEUR_RELAY_SECRET`),
jamais le secret du webhook Studiio (V331) — deux directions, deux usages,
deux secrets.

CE QUE CE FICHIER PROUVE
==============================================================================
  1. INERTE SANS LE SECRET — aucune route ne repond tant qu'il n'est pas pose
     (503, meme avec une signature presente).
  2. LE SECRET CORRECT OUVRE, un mauvais secret ou aucun REFUSE (403).
  3. LES DEUX VOIES fonctionnent : signature HMAC ET jeton `Bearer`.
  4. COMPARAISON EN TEMPS CONSTANT (`hmac.compare_digest`), pas `==`.
  5. PROJECTION — AUCUN champ interne (dedupe_key, created_by, website_domain,
     coach_id…) ni secret n'est jamais renvoye.
  6. PAGINATION — plafond 50, meme avec une demande plus grande.
  7. LECTURE SEULE PAR CONSTRUCTION — le fichier ne declare AUCUNE route
     POST/PATCH/PUT/DELETE : verifie en lisant le texte du module, pas en
     esperant qu'aucun test ne la declenche.
  8. L'EN-TETE `X-Afroboosteur-Membre` est purement informatif : une valeur
     falsifiee n'elargit RIEN, elle est seulement journalisee.
  9. AUCUNE SORTIE RESEAU : la garde ne fait aucun appel externe.

AUCUNE ECRITURE EN PRODUCTION. Base entierement bouchonnee, en memoire.

    python3 tests/test_p4_relais_afroboosteur.py
"""
import hashlib
import hmac as hmac_module
import os
import re
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


import asyncio  # noqa: E402

SECRET = "secret-relais-fictif-sans-aucun-rapport-avec-la-production"
os.environ.pop("AFROBOOSTEUR_RELAY_SECRET", None)  # section 1 depend de son absence

from fastapi import HTTPException  # noqa: E402
import api.routes.afroboosteur_relais as R  # noqa: E402


# ============================================================================
print("\n0. OUTILLAGE — bouchon minimal (lecture seule, aucun reseau)")


class Curseur:
    def __init__(self, docs):
        self._docs = docs
        self._skip = 0
        self._limit = None

    def sort(self, cle, sens=1):
        specs = cle if isinstance(cle, list) else [(cle, sens)]
        for champ, s in reversed(specs):
            self._docs = sorted(self._docs, key=lambda d: d.get(champ) or "", reverse=(s == -1))
        return self

    def skip(self, n):
        self._skip = n
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _tranche(self):
        d = self._docs[self._skip:]
        return d[:self._limit] if self._limit is not None else d

    async def to_list(self, n):
        return list(self._tranche())[:n]


class CollectionBouchon:
    def __init__(self, documents=None):
        self.documents = [dict(d) for d in (documents or [])]

    def _ok(self, doc, filtre):
        if not filtre:
            return True
        for cle, val in filtre.items():
            if isinstance(val, dict) and "$ne" in val:
                if doc.get(cle) == val["$ne"]:
                    return False
                continue
            if doc.get(cle) != val:
                return False
        return True

    def find(self, filtre=None, projection=None, *a, **k):
        return Curseur([dict(d) for d in self.documents if self._ok(d, filtre)])

    async def count_documents(self, filtre=None, *a, **k):
        return sum(1 for d in self.documents if self._ok(d, filtre))


class DBBouchon:
    def __init__(self, collections):
        self._c = collections

    def __getitem__(self, nom):
        return self._c[nom]


class RequeteFictive:
    def __init__(self, headers=None, params=None, corps=b""):
        self.headers = headers or {}
        self.query_params = params or {}
        self._corps = corps

    async def body(self):
        return self._corps


def signer(secret, corps=b""):
    return hmac_module.new(secret.encode(), corps, hashlib.sha256).hexdigest()


def executer(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ============================================================================
print("\n1. INERTE SANS LE SECRET — meme avec une signature presente")

req_avec_bearer = RequeteFictive(headers={"Authorization": "Bearer " + SECRET})
try:
    executer(R._garde(req_avec_bearer))
    verifier("1a sans AFROBOOSTEUR_RELAY_SECRET -> 503", False, "aucune exception levee")
except HTTPException as e:
    verifier("1a sans AFROBOOSTEUR_RELAY_SECRET -> 503", e.status_code == 503, str(e.status_code))

try:
    executer(R.relais_lister_prospects(req_avec_bearer))
    verifier("1b la route elle-meme est inerte -> 503", False)
except HTTPException as e:
    verifier("1b la route elle-meme est inerte -> 503", e.status_code == 503, str(e.status_code))

# ============================================================================
print("\n2. LE SECRET POSE : signature et jeton, les deux voies")
os.environ["AFROBOOSTEUR_RELAY_SECRET"] = SECRET

req_sans_rien = RequeteFictive()
try:
    executer(R._garde(req_sans_rien))
    verifier("2a aucun en-tete -> 403", False)
except HTTPException as e:
    verifier("2a aucun en-tete -> 403", e.status_code == 403, str(e.status_code))

req_mauvais_secret = RequeteFictive(headers={"Authorization": "Bearer mauvais-secret"})
try:
    executer(R._garde(req_mauvais_secret))
    verifier("2b mauvais secret -> 403", False)
except HTTPException as e:
    verifier("2b mauvais secret -> 403", e.status_code == 403, str(e.status_code))

req_bearer_correct = RequeteFictive(headers={"Authorization": "Bearer " + SECRET})
membre = executer(R._garde(req_bearer_correct))
verifier("2c secret correct via Bearer -> accepte", membre == "")

req_signature_correcte = RequeteFictive(
    headers={"X-Afroboosteur-Signature": signer(SECRET, b"")},
    corps=b"",
)
membre2 = executer(R._garde(req_signature_correcte))
verifier("2d secret correct via signature HMAC -> accepte", membre2 == "")

req_signature_prefixee = RequeteFictive(
    headers={"X-Afroboosteur-Signature": "sha256=" + signer(SECRET, b"")},
)
verifier("2e le prefixe 'sha256=' est tolere",
         executer(R._garde(req_signature_prefixee)) == "")

req_signature_fausse = RequeteFictive(headers={"X-Afroboosteur-Signature": "0" * 64})
try:
    executer(R._garde(req_signature_fausse))
    verifier("2f signature incorrecte -> 403", False)
except HTTPException as e:
    verifier("2f signature incorrecte -> 403", e.status_code == 403)

# ============================================================================
print("\n3. COMPARAISON EN TEMPS CONSTANT")
source = open(os.path.join(RACINE, "api", "routes", "afroboosteur_relais.py"), encoding="utf-8").read()
# Deux comparaisons REELLES dans le code (signature + jeton) ; l'en-tete du
# fichier en cite une troisieme, en prose — on compte les appels, pas le mot.
appels_reels = re.findall(r'hmac\.compare_digest\(', source)
verifier("3a hmac.compare_digest utilise (jamais ==) pour comparer le secret, aux DEUX endroits",
         len(appels_reels) == 2, "trouve %d appel(s)" % len(appels_reels))

# ============================================================================
print("\n4. L'EN-TETE MEMBRE EST INFORMATIF, JAMAIS AUTORISANT")
req_membre_quelconque = RequeteFictive(
    headers={"Authorization": "Bearer " + SECRET, "X-Afroboosteur-Membre": "nimporte.qui@exemple.test"})
m = executer(R._garde(req_membre_quelconque))
verifier("4a la valeur est recopiee pour le journal, sans etre interpretee", m == "nimporte.qui@exemple.test")
verifier("4b aucun branchement conditionnel sur X-Afroboosteur-Membre dans la garde",
         "if" not in [l for l in source.splitlines() if "X-Afroboosteur-Membre" in l][0])

# ============================================================================
print("\n5. PROSPECTS — projection reduite, filtre corbeille, pagination")

prospects = [
    {"id": "p1", "organisation_name": "Studio A", "city": "Geneve", "status": "a_contacter",
     "created_at": "2026-10-01", "coach_id": "secret-interne", "dedupe_key": "xx", "created_by": "y"},
    {"id": "p2", "organisation_name": "Studio B", "city": "Lausanne", "status": "contacte",
     "created_at": "2026-10-02", "corbeille": True},
    {"id": "p3", "organisation_name": "Studio C", "city": "Sion", "status": "a_contacter",
     "created_at": "2026-10-03"},
]
R.db = DBBouchon({R.P3S1_COLLECTION: CollectionBouchon(prospects)})

reponse = executer(R.relais_lister_prospects(RequeteFictive(
    headers={"Authorization": "Bearer " + SECRET})))
verifier("5a la fiche en corbeille (p2) est exclue", {p["id"] for p in reponse["prospects"]} == {"p1", "p3"})
verifier("5b total reflete le meme filtre", reponse["total"] == 2)
verifier("5c AUCUN champ interne (coach_id/dedupe_key/created_by) n'est demande par la projection",
         not ({"coach_id", "dedupe_key", "created_by", "website_domain", "city_key"} &
              set(R._PROJECTION_PROSPECT.keys())))
verifier("5d la projection exclut _id", R._PROJECTION_PROSPECT.get("_id") == 0)

req_grosse_page = RequeteFictive(headers={"Authorization": "Bearer " + SECRET}, params={"limit": "9999"})
reponse2 = executer(R.relais_lister_prospects(req_grosse_page))
verifier("5e la pagination est PLAFONNEE a 50, quoi qu'on demande", reponse2["limit"] == R.LIMITE_MAX)

# ============================================================================
print("\n6. CAMPAGNES — etat et compteurs, jamais de secret")

campagnes = [
    {"id": "c1", "nom": "Relance octobre", "etat": "preparee", "nb_destinataires": 12,
     "summary": {"emails_envoyes": 0}, "created_at": "2026-10-05"},
]
R.db = DBBouchon({R.P3S3_CAMPAGNES: CollectionBouchon(campagnes)})
rep_camp = executer(R.relais_lister_campagnes(RequeteFictive(headers={"Authorization": "Bearer " + SECRET})))
verifier("6a une campagne renvoyee, avec son etat", rep_camp["campaigns"][0]["etat"] == "preparee")
verifier("6b aucun champ liè a l'execution technique (provider token, etc.) dans la projection",
         not ({"provider_api_key", "smtp_password", "idempotency_key"} & set(R._PROJECTION_CAMPAGNE.keys())))

# ============================================================================
print("\n7. CONVERSATIONS — lecture des reponses partenaires")

conversations = [
    {"id": "m1", "from_email": "partenaire@exemple.test", "subject": "RE: proposition",
     "body_text": "Interesse, on en discute ?", "received_at": "2026-10-06", "statut": "a_repondre"},
]
R.db = DBBouchon({R.P3U2_COLLECTION: CollectionBouchon(conversations)})
rep_conv = executer(R.relais_lister_conversations(RequeteFictive(headers={"Authorization": "Bearer " + SECRET})))
verifier("7a un message renvoye", rep_conv["conversations"][0]["from_email"] == "partenaire@exemple.test")

# ============================================================================
print("\n8. LECTURE SEULE PAR CONSTRUCTION — aucune route d'ecriture dans ce fichier")

methodes_ecriture = re.findall(r'@router\.(post|patch|put|delete)\(', source)
verifier("8a aucune route POST/PATCH/PUT/DELETE declaree", methodes_ecriture == [], str(methodes_ecriture))
verifier("8b exactement trois routes GET", len(re.findall(r'@router\.get\(', source)) == 3)
verifier("8c aucun appel a insert_one/update_one/delete_one/replace_one dans tout le fichier",
         not re.search(r'\.(insert_one|insert_many|update_one|update_many|delete_one|delete_many|replace_one)\(', source))

# ============================================================================
print("\n9. AUCUNE SORTIE RESEAU DANS LA GARDE")
verifier("9a aucun import de 'requests' ni 'httpx' dans ce module",
         "import requests" not in source and "import httpx" not in source)

os.environ.pop("AFROBOOSTEUR_RELAY_SECRET", None)

# ============================================================================
total = len(RESULTATS)
reussites = sum(1 for _, ok, _ in RESULTATS if ok)
echecs = total - reussites
print("\n=== %d/%d OK (%d echec%s) ===" % (reussites, total, echecs, "" if echecs == 1 else "s"))
if echecs:
    sys.exit(1)
