#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V598 — NICHES DE PROSPECTION GÉRABLES. Ce fichier prouve :

  * les six niches d'origine sont inscrites en base avec leurs clés A–F (idempotent,
    jamais écrasées : un renommage survit) — aucun média / lien existant n'est migré ;
  * créer une niche : id UUID stable, clé = id, ordre = en dernier ; RIEN d'autre n'est créé ;
  * renommer garde l'id et la clé ; archiver bloque les nouveaux médias ;
  * supprimer : refusé pour une niche d'origine ou non vide (409), sinon Corbeille restaurable ;
  * médias et liens acceptent la nouvelle clé ; clé inconnue refusée ; cloisonnement ; 403 sans jeton.

    python3 tests/test_v598_niches_prospection.py
"""
import asyncio
import io
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ["JWT_SECRET"] = "secret-de-test-v598-sans-rapport-avec-la-production"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v598-inexistant:27017")

import api.server as S  # noqa: E402
from fastapi import HTTPException  # noqa: E402

RESULTATS = []


def verifier(intitule, condition, detail=""):
    RESULTATS.append((intitule, bool(condition)))
    print("  %-6s %s" % ("OK  " if condition else "ECHEC", intitule))
    if detail and not condition:
        print("           -> %s" % detail)


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

    async def update_one(self, filtre, maj, upsert=False):
        for d in self.docs:
            if _ok(d, filtre):
                d.update(maj.get("$set", {}))
                return
        if upsert:                                   # V598 : inscription idempotente ($setOnInsert)
            self.docs.append(dict(filtre, **maj.get("$setOnInsert", {}), **maj.get("$set", {})))

    async def delete_one(self, filtre):
        avant = len(self.docs)
        self.docs = [d for d in self.docs if not _ok(d, filtre)]
        self.supprimes = getattr(self, "supprimes", 0) + (avant - len(self.docs))

    async def update_many(self, filtre, maj):
        for d in self.docs:
            if _ok(d, filtre):
                d.update(maj["$set"])


class Base(dict):
    def __getattr__(self, nom):
        return self[nom]

    def __getitem__(self, nom):
        if nom not in self:
            dict.__setitem__(self, nom, Collection())
        return dict.__getitem__(self, nom)


BASE = Base()
S.db = BASE
COACH = "coach.v598@exemple.test"


class Requete:
    def __init__(self, corps=None, coach=COACH):
        self._corps = corps
        self.query_params = {}
        self.coach = coach

    async def json(self):
        return self._corps


async def _auth(requete):
    if not getattr(requete, "coach", None):
        raise HTTPException(status_code=403, detail="Authentification coach requise")
    return requete.coach


S._v309_require_coach_or_admin = _auth


def lancer(c):
    return asyncio.run(c)


def statut_http(coroutine):
    try:
        lancer(coroutine)
        return 200
    except HTTPException as e:
        return e.status_code


def fichier(fid, nom, mime, coach=COACH, taille=1000):
    BASE.uploaded_files.docs.append({"file_id": fid, "filename": nom, "content_type": mime,
                                     "coach_email": coach, "size": taille, "original_name": nom,
                                     "asset_type": "video" if mime.startswith("video/") else "image"})
    return "/api/files/%s/%s" % (fid, nom)




N = BASE[S.V598_NICHES]
print("\n1. Les six d'origine, inscrites sans migration")
r = lancer(S.v598_lister_niches(Requete()))
verifier("6 niches d'origine, clés A–F, ordre 1–6",
         [n["cle"] for n in r["niches"]] == list("ABCDEF") and [n["ordre"] for n in r["niches"]] == [1, 2, 3, 4, 5, 6])
verifier("noms d'origine", r["niches"][2]["nom"] == "Festivals" and r["niches"][5]["nom"] == "Santé / mamans")
verifier("chaque niche a un id UUID stable", all(S.V598_UUID.match(n["id"]) for n in r["niches"]))
ids_avant = [n["id"] for n in r["niches"]]
lancer(S.v598_lister_niches(Requete()))
verifier("relire n'inscrit rien de plus (idempotent)", len(N.docs) == 6 and [n["id"] for n in N.docs] == ids_avant)

print("\n2. Créer une niche : elle seule")
avant = {k: len(v.docs) for k, v in BASE.items() if k != S.V598_NICHES}
c = lancer(S.v598_creer_niche(Requete({"nom": "TEST — Seniors"})))["niche"]
verifier("clé = id (UUID), ordre 7, active", c["cle"] == c["id"] and S.V598_UUID.match(c["id"]) and c["ordre"] == 7 and c["active"] is True)
verifier("slug calculé", c["slug"] == "test-seniors")
verifier("RIEN d'autre créé (prospects, médias, liens, campagnes…)", {k: len(v.docs) for k, v in BASE.items() if k != S.V598_NICHES} == avant)
verifier("même nom -> 409", statut_http(S.v598_creer_niche(Requete({"nom": "test — seniors"}))) == 409)
verifier("nom vide -> 400", statut_http(S.v598_creer_niche(Requete({"nom": " "}))) == 400)
verifier("nom trop long -> 400", statut_http(S.v598_creer_niche(Requete({"nom": "x" * 61}))) == 400)

print("\n3. Médias et liens sur la nouvelle niche")
url = fichier("o9", "video_o9.mp4", "video/mp4")
m = lancer(S.v595_ajouter_media(Requete({"niche": c["cle"], "format": "original", "url": url})))["media"]
verifier("un média s'enregistre sur la nouvelle niche", m["niche"] == c["cle"])
verifier("clé UUID inconnue -> 400", statut_http(S.v595_ajouter_media(Requete(
    {"niche": "00000000-0000-4000-8000-000000000000", "format": "16_9", "url": "https://youtu.be/x"}))) == 400)
verifier("lettre G (inexistante) -> 400", statut_http(S.v595_ajouter_media(Requete({"niche": "G", "format": "16_9", "url": "https://youtu.be/x"}))) == 400)
l = lancer(S.v595_ajouter_lien(Requete({"nom": "Page seniors", "url": "https://afroboost.com", "niche": c["cle"]})))["lien"]
verifier("un lien s'enregistre sur la nouvelle niche", l["niche"] == c["cle"])
r = lancer(S.v595_lister_medias(Requete()))
verifier("defaut_par_niche connaît les 7 niches", set(r["defaut_par_niche"]) == set(list("ABCDEF") + [c["cle"]]))

print("\n4. Renommer, archiver")
r = lancer(S.v598_modifier_niche(c["id"], Requete({"nom": "TEST — Seniors / 60+"})))["niche"]
verifier("renommer garde id et clé", r["id"] == c["id"] and r["cle"] == c["cle"] and r["nom"] == "TEST — Seniors / 60+")
verifier("le média reste relié après renommage", [d for d in BASE[S.V595_MEDIAS].docs if d["id"] == m["id"]][0]["niche"] == c["cle"])
fest = [n for n in N.docs if n["cle"] == "C"][0]
lancer(S.v598_modifier_niche(fest["id"], Requete({"nom": "Festivals & événements"})))
lancer(S.v598_lister_niches(Requete()))
verifier("un renommage d'une niche d'origine survit à la relecture", [n for n in N.docs if n["cle"] == "C"][0]["nom"] == "Festivals & événements")
lancer(S.v598_modifier_niche(fest["id"], Requete({"nom": "Festivals"})))
lancer(S.v598_modifier_niche(c["id"], Requete({"active": False})))
verifier("niche archivée : nouveau média refusé", statut_http(S.v595_ajouter_media(Requete({"niche": c["cle"], "format": "16_9", "url": "https://youtu.be/y"}))) == 400)
verifier("archiver ne touche pas au média existant", len([d for d in BASE[S.V595_MEDIAS].docs if d["niche"] == c["cle"]]) == 1)
verifier("active non booléen -> 400", statut_http(S.v598_modifier_niche(c["id"], Requete({"active": "non"}))) == 400)
lancer(S.v598_modifier_niche(c["id"], Requete({"active": True})))

print("\n5. Suppression sécurisée")
verifier("niche d'origine -> 409", statut_http(S.v598_supprimer_niche(fest["id"], Requete())) == 409)
verifier("niche avec média / lien -> 409", statut_http(S.v598_supprimer_niche(c["id"], Requete())) == 409)
vide = lancer(S.v598_creer_niche(Requete({"nom": "TEST — vide"})))["niche"]
verifier("nouvelle niche suivante : ordre 8", vide["ordre"] == 8)
r = lancer(S.v598_supprimer_niche(vide["id"], Requete()))
verifier("niche vide : supprimée vers la corbeille", r["corbeille"] and not [n for n in N.docs if n["id"] == vide["id"]]
         and [x for x in BASE.deleted_items.docs if x["original_id"] == vide["id"]])
S._v311_coach_email_from_jwt = lambda req: getattr(req, "coach", None)
async def _est_coach(_e):
    return True
S._v309_is_coach_or_admin = _est_coach
S.is_super_admin = lambda e: False
entree = [x for x in BASE.deleted_items.docs if x["original_id"] == vide["id"]][0]
lancer(S.restore_trash(entree["id"], Requete()))
verifier("la corbeille la restaure", [n for n in N.docs if n["id"] == vide["id"]])

print("\n6. Cloisonnement et authentification")
verifier("un autre coach ne voit que ses 6 niches", len(lancer(S.v598_lister_niches(Requete(coach="autre@exemple.test")))["niches"]) == 6)
verifier("un autre coach ne peut pas renommer -> 404", statut_http(S.v598_modifier_niche(c["id"], Requete({"nom": "x y"}, coach="autre@exemple.test"))) == 404)
verifier("un autre coach ne peut pas supprimer -> 404", statut_http(S.v598_supprimer_niche(c["id"], Requete(coach="autre@exemple.test"))) == 404)
anonyme = Requete(coach=None)
for nom, co in [("GET", S.v598_lister_niches(anonyme)), ("POST", S.v598_creer_niche(anonyme)),
                ("PATCH", S.v598_modifier_niche("x", anonyme)), ("DELETE", S.v598_supprimer_niche("x", anonyme))]:
    verifier("%s niches sans jeton -> 403" % nom, statut_http(co) == 403)

ok = sum(1 for _, c2 in RESULTATS if c2)
print("\n%d/%d vérifications" % (ok, len(RESULTATS)))
sys.exit(0 if ok == len(RESULTATS) else 1)
