#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V597 — PROSPECTION → MÉDIAS : SUPPRIMER = CORBEILLE. Ce fichier prouve :

  * supprimer UN média ne touche QUE lui (ni l'original, ni les autres formats) ;
  * supprimer l'original ne supprime PAS ses exports ;
  * le média part dans deleted_items (payload intact) : son URL /api/files y reste
    écrite, donc la purge V425 conserve le fichier ; aucun fichier n'est effacé ;
  * un coach ne peut pas supprimer le média d'un autre (404) ; sans jeton : 403 ;
  * la Corbeille restaure le média ; si sa place est prise, il revient archivé.

    python3 tests/test_v597_suppression_media.py
"""
import asyncio
import io
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ["JWT_SECRET"] = "secret-de-test-v597-sans-rapport-avec-la-production"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v597-inexistant:27017")

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
COACH = "coach.v597@exemple.test"


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



print("\n1. Supprimer UN média")
o = fichier("o1", "video_o1.mp4", "video/mp4")
e1 = fichier("e1", "video_e1.mp4", "video/mp4")
e2 = fichier("e2", "video_e2.mp4", "video/mp4")
im = fichier("m1", "image_m1.jpg", "image/jpeg")
ed = {"debut": 0, "fin": 10, "ratio": "9:16", "position": 0.5, "cadre": {"gauche": 0, "haut": 0, "largeur": 608, "hauteur": 1080}}
orig = lancer(S.v595_ajouter_media(Requete({"niche": "C", "format": "original", "url": o})))["media"]
x916 = lancer(S.v595_ajouter_media(Requete({"niche": "C", "format": "9_16", "url": e1, "origine": "export", "source_id": orig["id"], "edition": ed})))["media"]
x169 = lancer(S.v595_ajouter_media(Requete({"niche": "C", "format": "16_9", "url": e2, "origine": "export", "source_id": orig["id"], "edition": dict(ed, ratio="16:9")})))["media"]
mini = lancer(S.v595_ajouter_media(Requete({"niche": "C", "format": "miniature", "url": im, "source_id": orig["id"]})))["media"]
M = BASE[S.V595_MEDIAS]
ids = lambda: sorted(d["id"] for d in M.docs)
r = lancer(S.v597_supprimer_media(x916["id"], Requete()))
verifier("supprimer le 9:16 : réponse corbeille", r["supprime"] and r["corbeille"])
verifier("supprimer le 9:16 : seuls l'original, le 16:9 et la miniature restent",
         ids() == sorted([orig["id"], x169["id"], mini["id"]]))
corb = BASE.deleted_items.docs
verifier("le 9:16 est dans la corbeille, payload intact", len(corb) == 1 and corb[0]["payload"]["id"] == x916["id"]
         and corb[0]["original_collection"] == "prospection_medias" and corb[0]["coach_id"] == COACH)
verifier("son URL /api/files reste écrite (la purge V425 garde le fichier)", e1 in str(corb[0]))
verifier("aucune fiche uploaded_files touchée", len(BASE.uploaded_files.docs) == 4)
lancer(S.v597_supprimer_media(mini["id"], Requete()))
verifier("supprimer la miniature ne touche aucune vidéo", ids() == sorted([orig["id"], x169["id"]]))

print("\n2. Supprimer l'original ne supprime pas ses exports")
lancer(S.v597_supprimer_media(orig["id"], Requete()))
verifier("le 16:9 reste, avec son source_id", ids() == [x169["id"]] and M.docs[0]["source_id"] == orig["id"])

print("\n3. Cloisonnement")
verifier("le média d'un autre coach -> 404", statut_http(S.v597_supprimer_media(x169["id"], Requete(coach="autre@exemple.test"))) == 404)
verifier("média inexistant -> 404", statut_http(S.v597_supprimer_media("inexistant", Requete())) == 404)
verifier("sans jeton -> 403", statut_http(S.v597_supprimer_media(x169["id"], Requete(coach=None))) == 403)
verifier("après ces refus, le 16:9 est toujours là", ids() == [x169["id"]])

print("\n4. Restauration depuis la Corbeille")
S._v311_coach_email_from_jwt = lambda req: getattr(req, "coach", None)
async def _est_coach(_e):
    return True
S._v309_is_coach_or_admin = _est_coach
S.is_super_admin = lambda e: False
entree = [c for c in corb if c["original_id"] == x916["id"]][0]
lancer(S.restore_trash(entree["id"], Requete()))
restaure = [d for d in M.docs if d["id"] == x916["id"]]
verifier("le 9:16 revient, à l'identique (export à vérifier)", len(restaure) == 1 and restaure[0]["statut"] == "a_verifier")
o2 = fichier("o2", "video_o2.mp4", "video/mp4")
nouvel = lancer(S.v595_ajouter_media(Requete({"niche": "C", "format": "original", "url": o2})))["media"]
entree_o = [c for c in corb if c["original_id"] == orig["id"]][0]
lancer(S.restore_trash(entree_o["id"], Requete()))
ro = [d for d in M.docs if d["id"] == orig["id"]][0]
verifier("ancien original restauré alors qu'un nouveau occupe la place -> archivé", ro["statut"] == "archivee"
         and [d for d in M.docs if d["id"] == nouvel["id"]][0]["statut"] == "en_cours")
verifier("restaurer le média d'un autre coach -> 403", statut_http(S.restore_trash(
    [c for c in corb if c["original_id"] == mini["id"]][0]["id"], Requete(coach="autre@exemple.test"))) == 403)

ok = sum(1 for _, c in RESULTATS if c)
print("\n%d/%d vérifications" % (ok, len(RESULTATS)))
sys.exit(0 if ok == len(RESULTATS) else 1)
