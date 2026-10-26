#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P4-RELAIS — LA PASSERELLE LECTURE SEULE VERS AFROBOOSTEUR.COM.

CE QUE LE LOT AJOUTE
==============================================================================
Trois routes GET (`api/routes/afroboosteur_relais.py`) : prospects, campagnes,
conversations. Gardees par un secret DEDIE (`AFROBOOSTEUR_RELAY_SECRET`),
jamais le secret du webhook Studiio (V331) — deux directions, deux usages,
deux secrets. Portee FERMEE sur un coach precis (`AFROBOOSTEUR_RELAY_COACH_ID`).

REVUE DE SECURITE (avant toute mise en service) — deux defauts trouves et
corriges, tous deux verrouilles par ce banc :

  1. REJOUABILITE. La premiere version signait le CORPS BRUT — vide sur un
     GET, donc une signature CONSTANTE, rejouable indefiniment par quiconque
     l'intercepte une fois. Corrige : la signature couvre desormais
     methode+chemin+requete+horodatage, et l'horodatage doit tomber dans une
     fenetre de 5 minutes. Le repli `Bearer <secret>` brut de V331 a ete
     RETIRE ici : il aurait ete exactement le defaut qu'on vient de corriger.
  2. PORTEE MANQUANTE. La premiere version ne filtrait AUCUNE requete par
     coach — elle s'appuyait sur le fait qu'un seul coach existe AUJOURD'HUI,
     un fait d'exploitation, pas une garantie du schema. Corrige : la portee
     est OBLIGATOIRE (503 si absente), jamais un filtre vide.

CE QUE CE FICHIER PROUVE
==============================================================================
  1. INERTE SANS LE SECRET OU SANS LA PORTEE — meme avec une signature valide.
  2. UNE SIGNATURE VALIDE POUR UNE REQUETE N'EST PAS VALIDE POUR UNE AUTRE
     (chemin different, horodatage different) — preuve directe que la
     rejouabilite du 1er defaut est fermee.
  3. L'HORODATAGE EST VERIFIE : absent, trop vieux ou trop en avance -> refus,
     MEME avec une signature par ailleurs correcte pour cet horodatage-la.
  4. AUCUN REPLI BEARER BRUT N'EXISTE : verifie en lisant le texte du module.
  5. COMPARAISON EN TEMPS CONSTANT (`hmac.compare_digest`).
  6. TOUTE REQUETE EST FILTREE PAR `coach_id` — verifie sur les trois routes,
     avec des documents d'un AUTRE coach present dans le bouchon pour prouver
     l'exclusion, pas seulement l'absence d'erreur.
  7. PROJECTION — AUCUN champ interne (dedupe_key, created_by, website_domain)
     ni secret n'est jamais renvoye.
  8. PAGINATION — plafond 50, meme avec une demande plus grande.
  9. LECTURE SEULE PAR CONSTRUCTION — aucune route POST/PATCH/PUT/DELETE,
     aucun appel d'ecriture Mongo, nulle part dans le fichier.
 10. L'EN-TETE `X-Afroboosteur-Membre` est purement informatif.
 11. AUCUNE SORTIE RESEAU.

AUCUNE ECRITURE EN PRODUCTION. Base entierement bouchonnee, en memoire.

    python3 tests/test_p4_relais_afroboosteur.py
"""
import hashlib
import hmac as hmac_module
import os
import re
import sys
import time

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
COACH_ID = "coach.fictif@exemple.test"
os.environ.pop("AFROBOOSTEUR_RELAY_SECRET", None)  # section 1 depend de son absence
os.environ.pop("AFROBOOSTEUR_RELAY_COACH_ID", None)

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


class URLFictive:
    def __init__(self, chemin, requete=""):
        self.path = chemin
        self.query = requete


class RequeteFictive:
    def __init__(self, chemin="/api/afroboosteur-relais/prospects", requete="",
                 headers=None, params=None):
        self.method = "GET"
        self.url = URLFictive(chemin, requete)
        self.headers = headers or {}
        self.query_params = params or {}


def signer(secret, methode, chemin, requete, horodatage):
    chaine = R._chaine_canonique(methode, chemin, requete, horodatage)
    return hmac_module.new(secret.encode(), chaine.encode(), hashlib.sha256).hexdigest()


def requete_signee(chemin="/api/afroboosteur-relais/prospects", requete="", secret=SECRET,
                    decalage=0, params=None, membre=None):
    horodatage = str(int(time.time()) + decalage)
    sig = signer(secret, "GET", chemin, requete, horodatage)
    h = {"X-Afroboosteur-Signature": sig, "X-Afroboosteur-Timestamp": horodatage}
    if membre:
        h["X-Afroboosteur-Membre"] = membre
    return RequeteFictive(chemin=chemin, requete=requete, headers=h, params=params)


def executer(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ============================================================================
print("\n1. INERTE SANS LE SECRET NI SANS LA PORTEE — meme avec une signature valide")

try:
    executer(R._garde(requete_signee()))
    verifier("1a sans AFROBOOSTEUR_RELAY_SECRET -> 503", False, "aucune exception levee")
except HTTPException as e:
    verifier("1a sans AFROBOOSTEUR_RELAY_SECRET -> 503", e.status_code == 503, str(e.status_code))

os.environ["AFROBOOSTEUR_RELAY_SECRET"] = SECRET
try:
    executer(R._garde(requete_signee()))
    verifier("1b secret pose mais AFROBOOSTEUR_RELAY_COACH_ID absent -> 503 (portee obligatoire)",
              False)
except HTTPException as e:
    verifier("1b secret pose mais AFROBOOSTEUR_RELAY_COACH_ID absent -> 503 (portee obligatoire)",
              e.status_code == 503, str(e.status_code))

os.environ["AFROBOOSTEUR_RELAY_COACH_ID"] = COACH_ID
verifier("1c secret ET portee poses -> la garde seule n'est plus 503",
         executer(R._garde(requete_signee())) == "")

# ============================================================================
print("\n2. UNE SIGNATURE VALIDE POUR UNE REQUETE N'EST PAS VALIDE POUR UNE AUTRE")

req_a = requete_signee(chemin="/api/afroboosteur-relais/prospects")
membre_a = executer(R._garde(req_a))
verifier("2a signature correcte pour SA requete -> acceptee", membre_a == "")

# Meme signature, chemin different : la chaine canonique change, donc la
# signature n'est PLUS valide ailleurs — c'est la preuve que la rejouabilite
# du defaut initial est fermee.
req_b = RequeteFictive(chemin="/api/afroboosteur-relais/campaigns",
                        headers=dict(req_a.headers))
try:
    executer(R._garde(req_b))
    verifier("2b la signature de /prospects echoue sur /campaigns", False)
except HTTPException as e:
    verifier("2b la signature de /prospects echoue sur /campaigns", e.status_code == 403)

# Meme chemin, requete (query string) differente.
req_c = RequeteFictive(chemin="/api/afroboosteur-relais/prospects", requete="limit=1",
                        headers=dict(req_a.headers))
try:
    executer(R._garde(req_c))
    verifier("2c la signature sans parametres echoue avec ?limit=1", False)
except HTTPException as e:
    verifier("2c la signature sans parametres echoue avec ?limit=1", e.status_code == 403)

# ============================================================================
print("\n3. L'HORODATAGE EST VERIFIE, MEME SI LA SIGNATURE LUI CORRESPOND")

req_vieux = requete_signee(decalage=-301)
try:
    executer(R._garde(req_vieux))
    verifier("3a horodatage vieux de 301s (signature pourtant correcte POUR CET horodatage) -> refus",
              False)
except HTTPException as e:
    verifier("3a horodatage vieux de 301s (signature pourtant correcte POUR CET horodatage) -> refus",
              e.status_code == 401, str(e.status_code))

req_futur = requete_signee(decalage=301)
try:
    executer(R._garde(req_futur))
    verifier("3b horodatage 301s dans le futur -> refus", False)
except HTTPException as e:
    verifier("3b horodatage 301s dans le futur -> refus", e.status_code == 401)

req_limite = requete_signee(decalage=-299)
verifier("3c horodatage a 299s (dans la fenetre) -> accepte",
         executer(R._garde(req_limite)) == "")

req_absent = RequeteFictive(headers={"X-Afroboosteur-Signature": "peu importe"})
try:
    executer(R._garde(req_absent))
    verifier("3d aucun horodatage du tout -> refus", False)
except HTTPException as e:
    verifier("3d aucun horodatage du tout -> refus", e.status_code == 401)

# ============================================================================
print("\n4. AUCUN REPLI 'Bearer <secret>' BRUT — verifie par lecture du code")

source = open(os.path.join(RACINE, "api", "routes", "afroboosteur_relais.py"), encoding="utf-8").read()
# On exclut le DOCSTRING du module (qui NOMME le motif V331 pour expliquer
# pourquoi il n'est pas repris ici) : seule compte la presence dans le CODE.
_sans_docstring = re.sub(r'""".*?"""', '', source, count=1, flags=re.S)
verifier("4a aucune lecture de l'en-tete Authorization dans le CODE",
         "headers.get(\"Authorization\"" not in _sans_docstring
         and "headers.get('Authorization'" not in _sans_docstring)
verifier("4b aucun repli bearer brut dans le CODE ('bearer ')",
         "bearer " not in _sans_docstring.lower())

req_avec_authorization = RequeteFictive(headers={"Authorization": "Bearer " + SECRET})
try:
    executer(R._garde(req_avec_authorization))
    verifier("4c un Authorization: Bearer <secret>, meme CORRECT, ne suffit plus -> refus", False)
except HTTPException as e:
    verifier("4c un Authorization: Bearer <secret>, meme CORRECT, ne suffit plus -> refus",
             e.status_code in (401, 403))

# ============================================================================
print("\n5. COMPARAISON EN TEMPS CONSTANT")
appels_reels = re.findall(r'hmac\.compare_digest\(', source)
verifier("5a hmac.compare_digest utilise (jamais ==) pour la signature",
         len(appels_reels) == 1, "trouve %d appel(s)" % len(appels_reels))

# ============================================================================
print("\n6. PORTEE — chaque route FILTRE par coach_id, un autre coach n'apparait jamais")

prospects = [
    {"id": "p1", "coach_id": COACH_ID, "organisation_name": "Studio A", "city": "Geneve",
     "status": "a_contacter", "created_at": "2026-10-01",
     "dedupe_key": "xx", "created_by": "y", "website_domain": "studio-a.ch"},
    {"id": "p2", "coach_id": COACH_ID, "organisation_name": "Studio B", "city": "Lausanne",
     "status": "contacte", "created_at": "2026-10-02", "corbeille": True},
    {"id": "p3", "coach_id": "UN_AUTRE_COACH", "organisation_name": "Ne doit JAMAIS apparaitre",
     "status": "a_contacter", "created_at": "2026-10-03"},
]
campagnes = [
    {"id": "c1", "coach_id": COACH_ID, "nom": "Relance octobre", "etat": "preparee",
     "nb_destinataires": 12, "summary": {"emails_envoyes": 0}, "created_at": "2026-10-05"},
    {"id": "c2", "coach_id": "UN_AUTRE_COACH", "nom": "NE DOIT JAMAIS APPARAITRE",
     "etat": "preparee", "created_at": "2026-10-05"},
]
conversations = [
    {"id": "m1", "coach_id": COACH_ID, "from_email": "partenaire@exemple.test",
     "subject": "RE: proposition", "body_text": "Interesse ?", "received_at": "2026-10-06",
     "statut": "a_repondre"},
    {"id": "m2", "coach_id": "UN_AUTRE_COACH", "from_email": "ne-doit-jamais@apparaitre.test",
     "received_at": "2026-10-06"},
]
R.db = DBBouchon({
    R.P3S1_COLLECTION: CollectionBouchon(prospects),
    R.P3S3_CAMPAGNES: CollectionBouchon(campagnes),
    R.P3U2_COLLECTION: CollectionBouchon(conversations),
})

rep_p = executer(R.relais_lister_prospects(
    requete_signee(chemin="/api/afroboosteur-relais/prospects")))
ids_p = {p["id"] for p in rep_p["prospects"]}
verifier("6a prospects : seul le coach configure, corbeille exclue (p1 seul, pas p2 ni p3)",
         ids_p == {"p1"}, str(ids_p))

rep_c = executer(R.relais_lister_campagnes(
    requete_signee(chemin="/api/afroboosteur-relais/campaigns")))
ids_c = {c["id"] for c in rep_c["campaigns"]}
verifier("6b campagnes : l'autre coach (c2) n'apparait jamais", ids_c == {"c1"}, str(ids_c))

rep_conv = executer(R.relais_lister_conversations(
    requete_signee(chemin="/api/afroboosteur-relais/conversations")))
ids_conv = {m["id"] for m in rep_conv["conversations"]}
verifier("6c conversations : l'autre coach (m2) n'apparait jamais", ids_conv == {"m1"}, str(ids_conv))

# ============================================================================
print("\n7. PROJECTION — aucun champ interne ni secret")

verifier("7a prospects : aucun champ interne (coach_id/dedupe_key/created_by/website_domain)",
         not ({"coach_id", "dedupe_key", "created_by", "website_domain", "city_key"} &
              set(R._PROJECTION_PROSPECT.keys())))
verifier("7b la projection prospects exclut _id", R._PROJECTION_PROSPECT.get("_id") == 0)
verifier("7c campagnes : aucun champ d'execution technique (provider token, idempotency_key)",
         not ({"provider_api_key", "smtp_password", "idempotency_key", "coach_id"} &
              set(R._PROJECTION_CAMPAGNE.keys())))
verifier("7d conversations : aucun coach_id dans la projection renvoyee",
         "coach_id" not in R._PROJECTION_CONVERSATION)

# ============================================================================
print("\n8. PAGINATION — plafond 50, quoi qu'on demande")

req_grosse_page = requete_signee(chemin="/api/afroboosteur-relais/prospects",
                                  requete="limit=9999", params={"limit": "9999"})
rep_grosse = executer(R.relais_lister_prospects(req_grosse_page))
verifier("8a la pagination est PLAFONNEE a 50", rep_grosse["limit"] == R.LIMITE_MAX)

# ============================================================================
print("\n9. LECTURE SEULE PAR CONSTRUCTION — aucune route d'ecriture dans ce fichier")

methodes_ecriture = re.findall(r'@router\.(post|patch|put|delete)\(', source)
verifier("9a aucune route POST/PATCH/PUT/DELETE declaree", methodes_ecriture == [], str(methodes_ecriture))
verifier("9b exactement trois routes GET", len(re.findall(r'@router\.get\(', source)) == 3)
verifier("9c aucun appel a insert_one/update_one/delete_one/replace_one dans tout le fichier",
         not re.search(r'\.(insert_one|insert_many|update_one|update_many|delete_one|delete_many|replace_one)\(', source))

# ============================================================================
print("\n10. L'EN-TETE MEMBRE EST INFORMATIF, JAMAIS AUTORISANT")

req_membre = requete_signee(membre="nimporte.qui@exemple.test")
m = executer(R._garde(req_membre))
verifier("10a la valeur est recopiee pour le journal, sans etre interpretee",
         m == "nimporte.qui@exemple.test")
ligne_membre = [l for l in source.splitlines() if "X-Afroboosteur-Membre" in l and "if" in l]
verifier("10b aucun branchement conditionnel sur X-Afroboosteur-Membre dans la garde",
         ligne_membre == [], str(ligne_membre))

# ============================================================================
print("\n11. AUCUNE SORTIE RESEAU DANS LA GARDE")
verifier("11a aucun import de 'requests' ni 'httpx' dans ce module",
         "import requests" not in source and "import httpx" not in source)

os.environ.pop("AFROBOOSTEUR_RELAY_SECRET", None)
os.environ.pop("AFROBOOSTEUR_RELAY_COACH_ID", None)

# ============================================================================
total = len(RESULTATS)
reussites = sum(1 for _, ok, _ in RESULTATS if ok)
echecs = total - reussites
print("\n=== %d/%d OK (%d echec%s) ===" % (reussites, total, echecs, "" if echecs == 1 else "s"))
if echecs:
    sys.exit(1)
