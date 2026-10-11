#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V599 — PROSPECTS ↔ NICHES DYNAMIQUES. Ce fichier prouve :

  * la règle historique Python = la règle JavaScript (nicheDe), cas piégeux compris ;
  * rattachement À BLANC par défaut (rien écrit), puis réel : seul niche_id (+ niche_source)
    change, jamais updated_at ; idempotent ; total conservé ; sans règle = laissé vide ;
  * créer / modifier la niche d'un prospect : niche active exigée, archivée gardée si déjà portée,
    statut et coordonnées intacts ;
  * filtre de liste par niche ; suppression d'une niche refusée dès 1 prospect ;
  * rattachement réservé au super-admin ; 403 sans jeton.

    python3 tests/test_v599_prospects_niches.py
"""
import asyncio
import io
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ["JWT_SECRET"] = "secret-de-test-v599-sans-rapport-avec-la-production"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v599-inexistant:27017")

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
COACH = "coach.v599@exemple.test"


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





import subprocess, json as _json
P = BASE[S.P3S1_COLLECTION]
N = BASE[S.V598_NICHES]
S.is_super_admin = lambda e: e == COACH        # le coach du banc joue le super-admin
print("\n1. La règle Python = la règle JavaScript historique")
CAS = [
    {"wave": "GV 10-2026 — D Écoles de danse France", "category": "commerce"},
    {"wave": "GV 10-2026 — E Entreprises", "category": "association"},
    {"wave": "GV — F Santé", "category": None},
    {"wave": "GV 10-2026 — Dé", "category": "bar"},            # \b JS : D suivi d'un accent
    {"wave": "Festivals été 2027", "category": "ecole_danse"},
    {"wave": "FESTIVAL", "category": "bar"},
    {"wave": "Vague 1", "category": "restaurant"},
    {"wave": "Vague 2", "category": "communaute_etudiante"},
    {"wave": None, "category": "organisateur_evenement"},
    {"wave": "", "category": "inconnue"},
    {"wave": "GVX — A", "category": "fitness"},
    {"wave": "  GV 2 — B  ", "category": "festival"},
]
js = open(os.path.join(RACINE, "frontend", "src", "utils", "prospectionStats.js"), encoding="utf-8").read()
deb = js.index("const CATEGORIE_NICHE"); fin = js.index("const VILLES_FRANCE")
code = js[deb:fin].replace("export function", "function") + "\nconsole.log(JSON.stringify(%s.map(nicheDe)));" % _json.dumps(CAS)
attendu = _json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True).stdout)
obtenu = [S.v599_cle_historique(c)[0] for c in CAS]
verifier("12 cas piégeux : mêmes niches qu'en JavaScript", obtenu == attendu, "%s != %s" % (obtenu, attendu))

print("\n2. Rattachement des fiches existantes")
def fiche(i, **k):
    d = {"id": "p%03d" % i, "coach_id": COACH, "status": "contacte", "updated_at": "2026-09-01T00:00:00+00:00",
         "organisation_name": "Fiche %d" % i, "public_email": "f%d@x.ch" % i}
    d.update(k); P.docs.append(d); return d
for i, c in enumerate(CAS):
    fiche(i, **c)
total = len(P.docs)
avant = [dict(d) for d in P.docs]
r = lancer(S.v599_rattacher_prospects(Requete({})))
verifier("à blanc par défaut : rien écrit", r["a_blanc"] and r["ecrits"] == 0 and all("niche_id" not in d for d in P.docs))
verifier("à blanc : comptes = règle (C, D, E, F, B, A…)", r["controle"] and r["total"] == total
         and r["a_rattacher"] + r["sans_niche"] == total)
verifier("sans règle applicable : listée, pas devinée", r["sans_niche"] == len([x for x in attendu if x is None]) == 1)
r = lancer(S.v599_rattacher_prospects(Requete({"confirmer": True})))
cle_par_id = {n["id"]: n["cle"] for n in N.docs}
verifier("réel : chaque fiche reçoit la niche de la règle",
         [cle_par_id.get(d.get("niche_id")) for d in P.docs] == attendu)
verifier("réel : le total est conservé, aucun doublon", len(P.docs) == total and len({d["id"] for d in P.docs}) == total)
diff = [k for a, b in zip(avant, P.docs) for k in set(a) | set(b) if a.get(k) != b.get(k)]
verifier("réel : SEULS niche_id et niche_source changent (pas updated_at)", set(diff) <= {"niche_id", "niche_source"})
r2 = lancer(S.v599_rattacher_prospects(Requete({"confirmer": True})))
verifier("relancer : idempotent (0 écrit)", r2["ecrits"] == 0 and r2["deja_rattaches"] == r["a_rattacher"])
verifier("rattachement par un non super-admin -> 403", statut_http(S.v599_rattacher_prospects(Requete({"confirmer": True}, coach="autre@x.ch"))) == 403)

print("\n3. Créer / modifier la niche d'un prospect")
g = lancer(S.v598_creer_niche(Requete({"nom": "TEST — Seniors"})))["niche"]
async def _noop(*a, **k):
    return []
S.p3s1_signaux_doublon = _noop
p = lancer(S.p3s1_creer_prospect(Requete({"organisation_name": "TEST — Résidence", "category": "association", "niche_id": g["id"]})))
verifier("créer un prospect dans la nouvelle niche", p["niche_id"] == g["id"])
verifier("créer avec une niche inconnue -> 400", statut_http(S.p3s1_creer_prospect(Requete(
    {"organisation_name": "X", "category": "bar", "niche_id": "00000000-0000-4000-8000-000000000000"}))) == 400)
d = [n for n in N.docs if n["cle"] == "D"][0]
lancer(S.p3s1_modifier_prospect(p["id"], Requete({"status": "repondu"})))
apres = lancer(S.p3s1_modifier_prospect(p["id"], Requete({"niche_id": d["id"]})))
verifier("changer de niche : statut, nom, catégorie intacts", apres["niche_id"] == d["id"] and apres["status"] == "repondu"
         and apres["organisation_name"] == "TEST — Résidence" and apres["category"] == "association")
lancer(S.p3s1_modifier_prospect(p["id"], Requete({"niche_id": g["id"]})))
lancer(S.v598_modifier_niche(g["id"], Requete({"active": False})))
verifier("niche archivée : la fiche la garde", [x for x in P.docs if x["id"] == p["id"]][0]["niche_id"] == g["id"])
verifier("niche archivée : modifier un autre champ reste possible", lancer(S.p3s1_modifier_prospect(p["id"], Requete({"notes": "ok", "niche_id": g["id"]})))["niche_id"] == g["id"])
verifier("niche archivée : refusée pour un AUTRE prospect", statut_http(S.p3s1_modifier_prospect("p000", Requete({"niche_id": g["id"]}))) == 400)
verifier("niche archivée : refusée à la création", statut_http(S.p3s1_creer_prospect(Requete({"organisation_name": "Y", "category": "bar", "niche_id": g["id"]}))) == 400)
lancer(S.v598_modifier_niche(g["id"], Requete({"active": True})))
verifier("réactivée : de nouveau proposable", lancer(S.p3s1_modifier_prospect("p000", Requete({"niche_id": g["id"]})))["niche_id"] == g["id"])
lancer(S.p3s1_modifier_prospect("p000", Requete({"niche_id": attendu and [n for n in N.docs if n["cle"] == attendu[0]][0]["id"]})))
verifier("retirer la niche (null) possible", lancer(S.p3s1_modifier_prospect(p["id"], Requete({"niche_id": None})))["niche_id"] is None)
lancer(S.p3s1_modifier_prospect(p["id"], Requete({"niche_id": g["id"]})))

print("\n4. Filtre, suppression")
class Rq(Requete):
    def __init__(self, params, coach=COACH):
        super().__init__(None, coach); self.query_params = params
r = lancer(S.p3s1_lister_prospects(Rq({"niche_id": g["id"]})))
verifier("filtre par niche : 1 prospect (le TEST)", r["total"] == 1 and r["prospects"][0]["id"] == p["id"])
r = lancer(S.p3s1_lister_prospects(Rq({"niche_id": "sans"})))
verifier("filtre « sans » : le seul sans règle", r["total"] == 1)
verifier("filtre niche invalide -> 400", statut_http(S.p3s1_lister_prospects(Rq({"niche_id": "C"}))) == 400)
verifier("supprimer une niche qui contient 1 prospect -> 409", statut_http(S.v598_supprimer_niche(g["id"], Requete())) == 409)
lancer(S.p3s1_modifier_prospect(p["id"], Requete({"niche_id": d["id"]})))
verifier("vidée de son prospect : la niche TEST se supprime", lancer(S.v598_supprimer_niche(g["id"], Requete()))["corbeille"])
verifier("rattachement sans jeton -> 403", statut_http(S.v599_rattacher_prospects(Requete({}, coach=None))) == 403)

ok = sum(1 for _, c2 in RESULTATS if c2)
print("\n%d/%d vérifications" % (ok, len(RESULTATS)))
sys.exit(0 if ok == len(RESULTATS) else 1)
