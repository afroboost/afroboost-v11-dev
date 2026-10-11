#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V600 — SUPPRIMER UNE NICHE = CORBEILLE, JAMAIS DE CASCADE. Ce fichier prouve :

  * toute niche se supprime (d'origine, créée, vide, avec prospects / médias / liens) ;
  * RIEN d'autre ne bouge : prospects (niche_id compris), médias, liens restent intacts ;
  * une niche supprimée ne reçoit plus rien (média, lien, prospect, renommage) ;
  * l'inscription automatique ne recrée PAS une « C » neuve ; restaurer rend tout ;
  * une campagne écarte les fiches d'une niche supprimée OU archivée ;
  * comptes réels exposés pour la confirmation ; cloisonnement ; 403 sans jeton.

    python3 tests/test_v600_suppression_niche.py
"""
import asyncio
import io
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ["JWT_SECRET"] = "secret-de-test-v600-sans-rapport-avec-la-production"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v600-inexistant:27017")

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

    async def find_one(self, filtre, _proj=None, **_k):
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
        n = 0
        for d in self.docs:
            if _ok(d, filtre):
                d.update(maj["$set"])
                n += 1
        return type("R", (), {"modified_count": n})()


class Base(dict):
    def __getattr__(self, nom):
        return self[nom]

    def __getitem__(self, nom):
        if nom not in self:
            dict.__setitem__(self, nom, Collection())
        return dict.__getitem__(self, nom)


BASE = Base()
S.db = BASE
COACH = "coach.v600@exemple.test"


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






import copy
P = BASE[S.P3S1_COLLECTION]; N = BASE[S.V598_NICHES]
S.is_super_admin = lambda e: False
S._v311_coach_email_from_jwt = lambda req: getattr(req, "coach", None)
async def _est_coach(_e):
    return True
S._v309_is_coach_or_admin = _est_coach
niches = lancer(S.v598_lister_niches(Requete()))["niches"]
C = [n for n in niches if n["cle"] == "C"][0]
D = [n for n in niches if n["cle"] == "D"][0]
for i in range(3):
    P.docs.append({"id": "p%d" % i, "ref": "C-%d" % i, "coach_id": COACH, "niche_id": C["id"], "status": "a_contacter",
                   "organisation_name": "Festival %d" % i, "category": "festival", "public_email": "f%d@x.ch" % i,
                   "j0_message": "Bonjour", "created_at": "2026-09-0%dT00:00:00+00:00" % (i + 1)})
P.docs.append({"id": "d0", "ref": "D-0", "coach_id": COACH, "niche_id": D["id"], "status": "a_contacter",
               "organisation_name": "Ecole", "category": "ecole_danse", "public_email": "e@x.ch", "j0_message": "Bonjour",
               "created_at": "2026-09-05T00:00:00+00:00"})
url = fichier("v1", "video_v1.mp4", "video/mp4")
lancer(S.v595_ajouter_media(Requete({"niche": "C", "format": "original", "url": url})))
lancer(S.v595_ajouter_lien(Requete({"nom": "Page", "url": "https://afroboost.com", "niche": "C"})))
avant = {k: copy.deepcopy(BASE[k].docs) for k in (S.P3S1_COLLECTION, S.V595_MEDIAS, S.V595_LIENS)}

print("\n1. Supprimer une niche d'origine qui contient tout")
r = lancer(S.v600_contenu_niche(C["id"], Requete()))
verifier("comptes réels pour la confirmation : 3 prospects, 1 média, 1 lien", r["contenu"] == {"prospects": 3, "medias": 1, "liens": 1})
r = lancer(S.v598_supprimer_niche(C["id"], Requete()))
verifier("supprimée vers la Corbeille, contenu annoncé conservé", r["corbeille"] and r["contenu_conserve"]["prospects"] == 3)
verifier("RIEN d'autre n'a bougé (prospects, médias, liens à l'identique)", all(BASE[k].docs == v for k, v in avant.items()))
verifier("la fiche niche est marquée supprimée, pas effacée", [n for n in N.docs if n["id"] == C["id"]][0]["supprimee"] is True)
verifier("une entrée de Corbeille, avec les comptes",
         [x for x in BASE.deleted_items.docs if x["original_id"] == C["id"]][0]["payload"]["contenu"]["prospects"] == 3)
lancer(S.v598_lister_niches(Requete()))
verifier("relire n'inscrit PAS une « C » neuve", len([n for n in N.docs if n["cle"] == "C"]) == 1)
verifier("supprimer deux fois -> 409", statut_http(S.v598_supprimer_niche(C["id"], Requete())) == 409)

print("\n2. Une niche supprimée ne reçoit plus rien")
verifier("nouveau média -> 400", statut_http(S.v595_ajouter_media(Requete({"niche": "C", "format": "16_9", "url": "https://youtu.be/z"}))) == 400)
verifier("nouveau lien -> 400", statut_http(S.v595_ajouter_lien(Requete({"nom": "x", "url": "https://afroboost.com", "niche": "C"}))) == 400)
async def _noop(*a, **k):
    return []
S.p3s1_signaux_doublon = _noop
verifier("nouveau prospect -> 400", statut_http(S.p3s1_creer_prospect(Requete({"organisation_name": "X", "category": "bar", "niche_id": C["id"]}))) == 400)
verifier("déplacer un prospect d'une autre niche dedans -> 400", statut_http(S.p3s1_modifier_prospect("d0", Requete({"niche_id": C["id"]}))) == 400)
verifier("une fiche qui la porte reste modifiable", lancer(S.p3s1_modifier_prospect("p0", Requete({"notes": "ok", "niche_id": C["id"]})))["niche_id"] == C["id"])
verifier("renommer une niche supprimée -> 409", statut_http(S.v598_modifier_niche(C["id"], Requete({"nom": "Festivals 2"}))) == 409)

print("\n3. Campagne : jamais une niche supprimée ou archivée")
class RqCampagne(Requete):
    def __init__(self, corps):
        super().__init__(corps)
        self.headers = {"content-length": "1"}
async def _portee(a):
    return {"coach_id": a}
S.p3s3_portee = _portee
r = lancer(S.p3s3_preparer_campagne(RqCampagne({"dry_run": True, "status": "a_contacter"})))
verifier("simulation : seule la fiche de D (niche active) est retenue", r["summary"]["fiches"] == 1)
lancer(S.v598_modifier_niche(D["id"], Requete({"active": False})))
verifier("D archivée : plus aucune fiche sélectionnable (400)", statut_http(S.p3s3_preparer_campagne(RqCampagne({"dry_run": True, "status": "a_contacter"}))) == 400)
lancer(S.v598_modifier_niche(D["id"], Requete({"active": True})))

print("\n4. Restaurer depuis la Corbeille")
entree = [x for x in BASE.deleted_items.docs if x["original_id"] == C["id"]][0]
lancer(S.restore_trash(entree["id"], Requete()))
c2 = [n for n in N.docs if n["id"] == C["id"]][0]
verifier("restaurée : même id, même clé, même nom, même ordre", c2["supprimee"] is False and c2["cle"] == "C"
         and c2["nom"] == C["nom"] and c2["ordre"] == C["ordre"])
verifier("la Corbeille ne la garde plus", not [x for x in BASE.deleted_items.docs if x["original_id"] == C["id"]])
verifier("ses 3 prospects la référencent toujours", len([p for p in P.docs if p.get("niche_id") == C["id"]]) == 3)
verifier("elle reçoit de nouveau des médias", lancer(S.v595_ajouter_media(Requete({"niche": "C", "format": "16_9", "url": "https://youtu.be/ok"})))["media"]["niche"] == "C")
r = lancer(S.p3s3_preparer_campagne(RqCampagne({"dry_run": True, "status": "a_contacter"})))
verifier("ses fiches redeviennent sélectionnables", r["summary"]["fiches"] == 4)

print("\n5. Une niche créée, vide, aussi ; cloisonnement")
g = lancer(S.v598_creer_niche(Requete({"nom": "TEST — vide"})))["niche"]
verifier("niche créée vide : supprimée", lancer(S.v598_supprimer_niche(g["id"], Requete()))["corbeille"])
verifier("son nom redevient disponible", lancer(S.v598_creer_niche(Requete({"nom": "TEST — vide"})))["niche"]["nom"] == "TEST — vide")
verifier("un autre coach ne peut pas supprimer -> 404", statut_http(S.v598_supprimer_niche(D["id"], Requete(coach="autre@x.ch"))) == 404)
verifier("un autre coach ne lit pas les comptes -> 404", statut_http(S.v600_contenu_niche(D["id"], Requete(coach="autre@x.ch"))) == 404)
verifier("comptes sans jeton -> 403", statut_http(S.v600_contenu_niche(D["id"], Requete(coach=None))) == 403)
verifier("suppression sans jeton -> 403", statut_http(S.v598_supprimer_niche(D["id"], Requete(coach=None))) == 403)

ok = sum(1 for _, c3 in RESULTATS if c3)
print("\n%d/%d vérifications" % (ok, len(RESULTATS)))
sys.exit(0 if ok == len(RESULTATS) else 1)
