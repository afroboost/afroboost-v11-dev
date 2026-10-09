#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V595 — PROSPECTION : MÉDIAS ET LIENS. Ce fichier prouve :

  * sans jeton coach : 403 sur les 7 routes ;
  * une vidéo ajoutée entre TOUJOURS « en cours », même si le corps dit « validée » ;
  * remplacer une vidéo ARCHIVE l'ancienne (jamais supprimée) ;
  * aucune vidéo validée -> `defaut_par_niche` vide partout ;
  * un lien d'essai gratuit / QR est forcé « bloqué » et ne peut pas être réactivé (409) ;
  * « Tester le lien » refuse une destination non publique (anti-SSRF) et ne
    change pas le statut ;
  * aucune route DELETE n'existe ; aucun autre code ne lit ces collections.

    python3 tests/test_v595_prospection_medias_liens.py
"""
import asyncio
import io
import json
import os
import re
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ["JWT_SECRET"] = "secret-de-test-v595-sans-rapport-avec-la-production"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v595-inexistant:27017")

import api.server as S  # noqa: E402
from fastapi import HTTPException  # noqa: E402

RESULTATS = []


def verifier(intitule, condition, detail=""):
    RESULTATS.append((intitule, bool(condition)))
    print("  %-6s %s" % ("OK  " if condition else "ECHEC", intitule))
    if detail and not condition:
        print("           -> %s" % detail)


def lancer(c):
    return asyncio.get_event_loop().run_until_complete(c) if False else asyncio.run(c)


# ------------------------------------------------------------- base bouchon
def _ok(doc, filtre):
    for k, v in filtre.items():
        val = doc.get(k)
        if isinstance(v, dict):
            if "$ne" in v and val == v["$ne"]:
                return False
            if "$in" in v and val not in v["$in"]:
                return False
        elif val != v:
            return False
    return True


class Curseur:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *_a, **_k):
        return self

    def skip(self, n):
        self.docs = self.docs[n:]
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    async def to_list(self, _n):
        return [dict(d) for d in self.docs]

    def __aiter__(self):
        self._it = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return dict(next(self._it))
        except StopIteration:
            raise StopAsyncIteration


class Collection:
    def __init__(self):
        self.docs = []
        self.suppressions = 0

    def find(self, filtre, _proj=None):
        return Curseur([d for d in self.docs if _ok(d, filtre)])

    async def find_one(self, filtre, _proj=None):
        for d in self.docs:
            if _ok(d, filtre):
                return dict(d)
        return None

    async def count_documents(self, filtre):
        return len([d for d in self.docs if _ok(d, filtre)])

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, filtre, maj):
        for d in self.docs:
            if _ok(d, filtre):
                d.update(maj["$set"])
                return

    async def update_many(self, filtre, maj):
        for d in self.docs:
            if _ok(d, filtre):
                d.update(maj["$set"])

    async def delete_one(self, *_a):
        self.suppressions += 1

    delete_many = delete_one


class Base(dict):
    def __getitem__(self, nom):
        if nom not in self:
            dict.__setitem__(self, nom, Collection())
        return dict.__getitem__(self, nom)


BASE = Base()
S.db = BASE
COACH = "coach.v595@exemple.test"


class Requete:
    def __init__(self, corps=None, params=None, coach=COACH):
        self._corps = corps
        self.query_params = params or {}
        self.coach = coach

    async def json(self):
        return self._corps


async def _auth(requete):
    if not getattr(requete, "coach", None):
        raise HTTPException(status_code=403, detail="Authentification coach requise")
    return requete.coach


S._v309_require_coach_or_admin = _auth


def statut_http(coroutine):
    try:
        lancer(coroutine)
        return 200
    except HTTPException as e:
        return e.status_code


SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
print("\n1. Sans jeton : 403 partout")
anonyme = Requete(coach=None)
for nom, co in [
        ("GET medias", S.v595_lister_medias(anonyme)),
        ("POST medias", S.v595_ajouter_media(anonyme)),
        ("PATCH media", S.v595_modifier_media("x", anonyme)),
        ("GET liens", S.v595_lister_liens(anonyme)),
        ("POST liens", S.v595_ajouter_lien(anonyme)),
        ("PATCH lien", S.v595_modifier_lien("x", anonyme)),
        ("POST tester", S.v595_tester_lien("x", anonyme))]:
    verifier("%s sans jeton -> 403" % nom, statut_http(co) == 403)

print("\n2. Médias : jamais validés automatiquement, jamais supprimés")
r = lancer(S.v595_lister_medias(Requete()))
verifier("base vide : 0 média, aucune vidéo par défaut",
         r["total"] == 0 and all(v is None for v in r["defaut_par_niche"].values()))
r1 = lancer(S.v595_ajouter_media(Requete({"niche": "D", "format": "16_9", "url": "https://youtu.be/aaa",
                                          "statut": "validee", "version": "V1"})))
verifier("ajout : statut forcé « en_cours » malgré « validee » demandé", r1["media"]["statut"] == "en_cours")
r2 = lancer(S.v595_ajouter_media(Requete({"niche": "D", "format": "16_9", "url": "https://youtu.be/bbb", "version": "V2"})))
docs = BASE[S.V595_MEDIAS].docs
ancien = [d for d in docs if d["id"] == r1["media"]["id"]][0]
verifier("remplacement : l'ancienne passe « archivee »", ancien["statut"] == "archivee" and r2["archives"] == 1)
verifier("remplacement : l'ancienne pointe vers la nouvelle", ancien["remplace_par"] == r2["media"]["id"])
verifier("remplacement : rien n'est supprimé (2 documents)", len(docs) == 2 and BASE[S.V595_MEDIAS].suppressions == 0)
lancer(S.v595_ajouter_media(Requete({"niche": "D", "format": "9_16", "url": "https://youtu.be/ccc"})))
verifier("autre format : n'archive pas le 16:9", [d for d in docs if d["id"] == r2["media"]["id"]][0]["statut"] == "en_cours")
verifier("ressortir l'archive alors que la place est prise -> 409",
         statut_http(S.v595_modifier_media(r1["media"]["id"], Requete({"statut": "en_cours"}))) == 409)
verifier("niche inconnue -> 400",
         statut_http(S.v595_ajouter_media(Requete({"niche": "Z", "format": "16_9", "url": "https://x.ch"}))) == 400)
verifier("lien non web -> 400",
         statut_http(S.v595_ajouter_media(Requete({"niche": "A", "format": "16_9", "url": "javascript:alert(1)"}))) == 400)
r = lancer(S.v595_lister_medias(Requete()))
verifier("toujours aucune vidéo par défaut (aucune validée)", all(v is None for v in r["defaut_par_niche"].values()))
autre = lancer(S.v595_lister_medias(Requete(coach="autre@exemple.test")))
verifier("isolation : un autre coach ne voit rien", autre["total"] == 0)

print("\n3. Liens : essai gratuit / QR bloqués par le serveur")
essai = lancer(S.v595_ajouter_lien(Requete({
    "nom": "Page essai partenaire", "categorie": "reservation", "statut": "actif",
    "url": "https://afroboost.com/cours-essai-gratuit-neuchatel?utm_source=partenaire"})))["lien"]
verifier("lien d'essai enregistré « bloque » même si « actif » demandé", essai["statut"] == "bloque" and essai["verrou"])
verifier("réactiver le lien d'essai -> 409",
         statut_http(S.v595_modifier_lien(essai["id"], Requete({"statut": "actif"}))) == 409)
modif = lancer(S.v595_modifier_lien(essai["id"], Requete({"utilisation": "QR flyer"})))["lien"]
verifier("modifier une note garde « bloque »", modif["statut"] == "bloque")
qr = lancer(S.v595_ajouter_lien(Requete({"nom": "QR invitation", "url": "https://afroboost.com/api/share/invite/abc"})))["lien"]
verifier("invitation d'essai / QR : « bloque »", qr["statut"] == "bloque")
site = lancer(S.v595_ajouter_lien(Requete({"nom": "Site", "categorie": "site", "url": "https://afroboost.com"})))["lien"]
verifier("lien ordinaire : « a_verifier » par défaut", site["statut"] == "a_verifier" and site["verrou"] is None)
verifier("catégorie inconnue -> 400",
         statut_http(S.v595_ajouter_lien(Requete({"nom": "x", "url": "https://x.ch", "categorie": "pub"}))) == 400)

print("\n4. Tester le lien : anti-SSRF, statut inchangé")
verifier("localhost refusé", S.v595_adresse_publique("localhost") is False)
verifier("127.0.0.1 refusé", S.v595_adresse_publique("127.0.0.1") is False)
verifier("169.254.169.254 refusé", S.v595_adresse_publique("169.254.169.254") is False)
verifier("10.0.0.1 refusé", S.v595_adresse_publique("10.0.0.1") is False)
interne = lancer(S.v595_ajouter_lien(Requete({"nom": "Interne", "url": "http://127.0.0.1:8080/healthz"})))["lien"]
t = lancer(S.v595_tester_lien(interne["id"], Requete()))
verifier("test d'une adresse interne : échec sans requête", t["test"]["ok"] is False and t["test"]["http"] is None)
verifier("le test ne change pas le statut", t["lien"]["statut"] == "a_verifier" and t["lien"]["verifie_le"])

bloc_sonde = SRC[SRC.index("async def v595_sonder"):SRC.index('@api_router.post("/prospection-liens/{lien_id}/tester")')]
verifier("anti-rebinding : connexion à l'IP vérifiée (épinglage + SNI)",
         "v595_resoudre_publique" in bloc_sonde and "sni_hostname" in bloc_sonde and "epinglee" in bloc_sonde)
verifier("aucun corps de réponse lu (stream fermé)", "stream=True" in bloc_sonde and ".text" not in bloc_sonde)

print("\n5. Structure : aucune suppression, aucun lecteur caché")
verifier("aucune route DELETE V595", not re.search(r'@api_router\.delete\("/prospection-(medias|liens)', SRC))
lecteurs = [m.start() for m in re.finditer(r"V595_(MEDIAS|LIENS)\]", SRC)]
debut = SRC.index("# V595 — PROSPECTION : MÉDIAS ET LIENS")
fin = SRC.index("# Include router\nfastapi_app.include_router(api_router)")
verifier("seules les routes V595 touchent ces collections", all(debut < x < fin for x in lecteurs))
verifier("les routes sont enregistrées AVANT include_router", debut < fin)

ok = sum(1 for _, b in RESULTATS if b)
print("\n%d/%d vérifications" % (ok, len(RESULTATS)))
sys.exit(0 if ok == len(RESULTATS) else 1)
