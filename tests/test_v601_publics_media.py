#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V601 — PLUSIEURS VIDÉOS PAR NICHE (une par public) ET LA BONNE VIDÉO POUR CHAQUE PROSPECT.

  * deux vidéos de la même niche et du même format ne s'archivent plus si leurs publics diffèrent ;
  * un export hérite du public de son original ; le public se règle par PATCH, sans nouvel envoi ;
  * salon → Coiffeuse, physio → Physio-Ostéo, sans correspondance → aucune vidéo (jamais au hasard) ;
  * une niche sans vidéo (Entreprises) → aucune vidéo ; restaurer depuis la Corbeille marche encore ;
  * la préparation J0 ne dépend toujours d'aucun média.

    python3 tests/test_v601_publics_media.py
"""
import asyncio
import io
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ["JWT_SECRET"] = "secret-de-test-v601-sans-rapport-avec-la-production"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v601-inexistant:27017")

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
COACH = "coach.v601@exemple.test"


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


S.is_super_admin = lambda e: False
S._v311_coach_email_from_jwt = lambda req: getattr(req, "coach", None)
async def _est_coach(_e):
    return True
S._v309_is_coach_or_admin = _est_coach
P = BASE[S.P3S1_COLLECTION]; M = BASE[S.V595_MEDIAS]
niches = {n["cle"]: n for n in lancer(S.v598_lister_niches(Requete()))["niches"]}
COIF = {"nom": "Salons / coiffure / beauté", "mots_cles": ["coiffure", "tresses", "barbier", "onglerie", "beauté", "perruques", "extensions de cheveux"]}
PHYS = {"nom": "Physio / ostéo / thérapie", "mots_cles": ["physio", "ostéo", "thérapie", "massothérapie", "médecine du sport"]}

print("\n1. Validation du public visé (pure)")
c = S.v601_cible(COIF)
verifier("id stable dérivé du nom", c["id"] == S.v598_slug("Salons / coiffure / beauté"), c)
verifier("mots-clés normalisés sans accent", "beaute" in c["mots_cles"] and "osteo" in S.v601_cible(PHYS)["mots_cles"], c)
try:
    S.v601_cible({"nom": "X y", "mots_cles": []}); refus0 = False
except HTTPException as e:
    refus0 = e.status_code == 400
verifier("sans mot-clé = 400", refus0)
try:
    S.v601_cible({"nom": "Vide", "mots_cles": ["a"]}); refus = False
except HTTPException as e:
    refus = e.status_code == 400
verifier("mots-clés trop courts refusés (400)", refus)

print("\n2. Niche A : deux originaux, deux publics, aucun archivage croisé")
u1 = fichier("c1", "coif.mp4", "video/mp4"); u2 = fichier("p1", "physio.mp4", "video/mp4")
r1 = lancer(S.v595_ajouter_media(Requete({"niche": "A", "format": "original", "url": u1, "cible": COIF})))["media"]
r2 = lancer(S.v595_ajouter_media(Requete({"niche": "A", "format": "original", "url": u2, "cible": PHYS})))["media"]
actifs = [m for m in M.docs if m["niche"] == "A" and m["statut"] != "archivee"]
verifier("les deux originaux restent actifs", len(actifs) == 2, [(m["id"], m["statut"]) for m in M.docs])
u3 = fichier("c2", "coif2.mp4", "video/mp4")
r3 = lancer(S.v595_ajouter_media(Requete({"niche": "A", "format": "original", "url": u3, "cible": COIF})))
verifier("un nouvel original Coiffeuse archive SEULEMENT l'ancien Coiffeuse",
         [m["statut"] for m in M.docs if m["id"] == r1["id"]] == ["archivee"] and
         [m["statut"] for m in M.docs if m["id"] == r2["id"]] != ["archivee"])
coif_id = r3["media"]["id"]
u4 = fichier("c3", "coif_16x9.mp4", "video/mp4")
ex = lancer(S.v595_ajouter_media(Requete({"niche": "A", "format": "16_9", "url": u4, "source_id": coif_id,
                                          "origine": "export", "edition": {"debut": 0, "fin": 10, "ratio": "16:9"}})))["media"]
verifier("un export hérite du public de son original", ex.get("cible_id") == S.v601_cible(COIF)["id"], ex.get("cible_id"))

print("\n3. Routage : la bonne vidéo pour chaque prospect")
def prospect(pid, niche, nom, sous="", cat="commerce"):
    P.docs.append({"id": pid, "coach_id": COACH, "niche_id": niches[niche]["id"], "organisation_name": nom,
                   "subcategory": sous, "category": cat, "status": "a_contacter", "j0_message": "Bonjour"})
prospect("salon", "A", "Akwaba Hair", "coiffure afro / tresses")
prospect("ongle", "A", "Nails Studio", "onglerie")
prospect("physio", "A", "PhysioPod – Institut de physio", "physiothérapie")
prospect("moveo", "A", "MOVEO Thérapies", "physiothérapie / thérapies du mouvement")
prospect("resto", "A", "Chez Mama", "restaurant africain", "restaurant")
prospect("asso", "B", "AGE Uni", "", "association")
prospect("entr", "E", "BCV", "", "commerce")
def choix(pid):
    return lancer(S.v601_media_pour_prospect(pid, Requete()))
verifier("salon → Coiffeuse (le 16:9 de préférence)", (choix("salon")["media"] or {}).get("id") == ex["id"], choix("salon"))
verifier("onglerie → Coiffeuse", (choix("ongle")["media"] or {}).get("public") == "Salons / coiffure / beauté")
verifier("physio → Physio-Ostéo", (choix("physio")["media"] or {}).get("id") == r2["id"], choix("physio"))
verifier("MOVEO Thérapies → Physio-Ostéo", (choix("moveo")["media"] or {}).get("id") == r2["id"], choix("moveo"))
verifier("restaurant de A → AUCUNE vidéo (pas au hasard)", choix("resto")["media"] is None, choix("resto"))
verifier("Entreprises sans vidéo → aucune", choix("entr")["media"] is None and "aucune" in choix("entr")["raison"])
ub = fichier("b1", "asso.mp4", "video/mp4")
mb = lancer(S.v595_ajouter_media(Requete({"niche": "B", "format": "original", "url": ub})))["media"]
verifier("association → vidéo générale de B", (choix("asso")["media"] or {}).get("id") == mb["id"], choix("asso"))
prospect("mixte", "A", "Coiffure & physio", "coiffure / physio")
verifier("deux publics qui correspondent → aucune (ambigu)", choix("mixte")["media"] is None and "ambigu" in choix("mixte")["raison"], choix("mixte"))
verifier("prospect d'un autre coach → 404", statut_http(S.v601_media_pour_prospect("salon", Requete(coach="autre@x.test"))) == 404)
verifier("sans jeton → 403", statut_http(S.v601_media_pour_prospect("salon", Requete(coach=None))) == 403)

print("\n4. Régler le public d'un média existant (PATCH, aucun nouvel envoi)")
ug = fichier("g1", "gen.mp4", "video/mp4")
mg = lancer(S.v595_ajouter_media(Requete({"niche": "F", "format": "original", "url": ug})))["media"]
n_fichiers = len(BASE.uploaded_files.docs)
mp = lancer(S.v595_modifier_media(mg["id"], Requete({"cible": PHYS})))["media"]
verifier("public posé par PATCH", mp.get("cible_id") == S.v601_cible(PHYS)["id"] and mp.get("url") == ug, mp)
verifier("aucun fichier créé", len(BASE.uploaded_files.docs) == n_fichiers)
ug2 = fichier("g2", "gen2.mp4", "video/mp4")
mg2 = lancer(S.v595_ajouter_media(Requete({"niche": "F", "format": "original", "url": ug2})))["media"]
verifier("conflit : même public + même format déjà occupé → 409",
         statut_http(S.v595_modifier_media(mg2["id"], Requete({"cible": PHYS}))) == 409)
verifier("retirer le public alors que « toute la niche » est occupée → 409",
         statut_http(S.v595_modifier_media(mp["id"], Requete({"cible": None}))) == 409)  # g2 occupe déjà « toute la niche »

print("\n5. Corbeille : supprimer puis restaurer un média à public")
lancer(S.v597_supprimer_media(r2["id"], Requete()))
verifier("physio partie à la Corbeille", not [m for m in M.docs if m["id"] == r2["id"]])
item = [d for d in BASE.deleted_items.docs if d.get("original_id") == r2["id"] or (d.get("payload") or {}).get("id") == r2["id"]]
verifier("élément de Corbeille présent", len(item) == 1, BASE.deleted_items.docs[-1:] if BASE.deleted_items.docs else None)
if item:
    st = statut_http(S.restore_trash(item[0]["id"], Requete()))
    verifier("restauration acceptée (aucun autre Physio actif)", st == 200, st)
    verifier("le public est conservé après restauration",
             [m.get("cible_id") for m in M.docs if m["id"] == r2["id"]] == [S.v601_cible(PHYS)["id"]])

print("\n6. J0 indépendant des vidéos")
import inspect
src = inspect.getsource(S.p3s3_preparer_campagne)
verifier("la préparation de campagne ne lit aucun média", "V595_MEDIAS" not in src and "prospection_medias" not in src)

ok = sum(1 for _, v in RESULTATS if v)
print("\n%d/%d vérifications réussies" % (ok, len(RESULTATS)))
sys.exit(0 if ok == len(RESULTATS) else 1)
