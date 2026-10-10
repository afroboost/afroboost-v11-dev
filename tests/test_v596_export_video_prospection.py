#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V596 — PROSPECTION → MÉDIAS : EXPORT VIDÉO DANS LE NAVIGATEUR. Ce fichier prouve :

  * le serveur ne fait AUCUN calcul vidéo (pas de ffmpeg, pas de subprocess) ;
  * un fichier /api/files n'est accepté que s'il appartient au coach et a le bon type ;
  * un EXPORT entre « à vérifier », jamais « validée », même si le corps le demande ;
  * un export exige son ORIGINAL (même coach, même niche) ; l'original n'est jamais modifié ;
  * réglages d'export bornés (découpe, ratio, cadre) ; adresse arbitraire refusée ;
  * l'URL du fichier est écrite dans prospection_medias (protège de la purge V425).

    python3 tests/test_v596_export_video_prospection.py
"""
import asyncio
import io
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ["JWT_SECRET"] = "secret-de-test-v596-sans-rapport-avec-la-production"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v596-inexistant:27017")

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

    async def update_one(self, filtre, maj):
        for d in self.docs:
            if _ok(d, filtre):
                d.update(maj["$set"])
                return

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
COACH = "coach.v596@exemple.test"


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


SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
debut_v596 = SRC.index("# --- V596 : fichiers /api/files et export navigateur")
fin_v596 = SRC.index('@api_router.patch("/prospection-medias/{media_id}")')
BLOC = SRC[debut_v596:fin_v596]

print("\n1. Aucun calcul vidéo sur le serveur")
verifier("le bloc V596 ne lance ni ffmpeg ni subprocess",
         "ffmpeg" not in BLOC.lower().replace("aucun calcul", "") and "subprocess" not in BLOC
         and "os.system" not in BLOC and "create_subprocess" not in BLOC)
verifier("le bloc V596 n'ouvre aucun fichier disque", "open(" not in BLOC and "os.path" not in BLOC)
verifier("formats : original, 16_9, 9_16, 1_1, miniature",
         S.V595_FORMATS == ("original", "16_9", "9_16", "1_1", "miniature"))

print("\n2. Original : un fichier du coach, « en cours »")
url_orig = fichier("orig01", "video_orig01.mp4", "video/mp4", taille=22538851)
r = lancer(S.v595_ajouter_media(Requete({
    "niche": "C", "format": "original", "url": url_orig, "statut": "validee",
    "fichier": {"nom": "AFROBOOST_6_FESTIVAL_16x9_AVEC-COACH.mp4", "duree": 43.3, "largeur": 1920, "hauteur": 1080}})))
original = r["media"]
verifier("original : statut « en_cours » malgré « validee » demandé", original["statut"] == "en_cours")
verifier("original : origine « fichier »", original["origine"] == "fichier")
verifier("original : taille lue sur la fiche serveur, pas sur le corps", original["fichier"]["taille"] == 22538851)
verifier("original : nom d'origine conservé", original["fichier"]["nom"] == "AFROBOOST_6_FESTIVAL_16x9_AVEC-COACH.mp4")
verifier("original : l'URL /api/files est écrite dans prospection_medias (anti-purge V425)",
         any(url_orig in str(d) for d in BASE[S.V595_MEDIAS].docs))

print("\n3. Fichiers refusés")
url_autre = fichier("autre01", "video_autre01.mp4", "video/mp4", coach="intrus@exemple.test")
verifier("fichier d'un autre coach -> 403", statut_http(S.v595_ajouter_media(Requete(
    {"niche": "C", "format": "original", "url": url_autre}))) == 403)
verifier("fichier inconnu -> 400", statut_http(S.v595_ajouter_media(Requete(
    {"niche": "C", "format": "original", "url": "/api/files/inconnu/x.mp4"}))) == 400)
verifier("chemin arbitraire (../) -> 400", statut_http(S.v595_ajouter_media(Requete(
    {"niche": "C", "format": "original", "url": "/api/files/../../etc/passwd"}))) == 400)
verifier("nom de fichier ne correspondant pas à la fiche -> 400", statut_http(S.v595_ajouter_media(Requete(
    {"niche": "C", "format": "original", "url": "/api/files/orig01/autre.mp4"}))) == 400)
url_img = fichier("img01", "image_img01.jpg", "image/jpeg")
verifier("une image comme vidéo -> 400", statut_http(S.v595_ajouter_media(Requete(
    {"niche": "C", "format": "16_9", "url": url_img}))) == 400)
verifier("une vidéo comme miniature -> 400", statut_http(S.v595_ajouter_media(Requete(
    {"niche": "C", "format": "miniature", "url": url_orig}))) == 400)

print("\n4. Export : « à vérifier », jamais validé, original exigé")
url_exp = fichier("exp916", "video_exp916.mp4", "video/mp4", taille=9000000)
edition = {"debut": 2, "fin": 40, "ratio": "9:16", "position": 0.5,
           "cadre": {"gauche": 656, "haut": 0, "largeur": 608, "hauteur": 1080}}
verifier("export sans original -> 400", statut_http(S.v595_ajouter_media(Requete(
    {"niche": "C", "format": "9_16", "url": url_exp, "origine": "export", "edition": edition}))) == 400)
verifier("export avec l'original d'une AUTRE niche -> 400", statut_http(S.v595_ajouter_media(Requete(
    {"niche": "A", "format": "9_16", "url": url_exp, "origine": "export", "edition": edition,
     "source_id": original["id"]}))) == 400)
verifier("export au format « original » -> 400", statut_http(S.v595_ajouter_media(Requete(
    {"niche": "C", "format": "original", "url": url_exp, "origine": "export", "edition": edition,
     "source_id": original["id"]}))) == 400)
verifier("export sans réglages -> 400", statut_http(S.v595_ajouter_media(Requete(
    {"niche": "C", "format": "9_16", "url": url_exp, "origine": "export", "source_id": original["id"]}))) == 400)
verifier("extrait trop court -> 400", statut_http(S.v595_ajouter_media(Requete(
    {"niche": "C", "format": "9_16", "url": url_exp, "origine": "export", "source_id": original["id"],
     "edition": dict(edition, debut=10, fin=10.2)}))) == 400)
verifier("ratio inconnu -> 400", statut_http(S.v595_ajouter_media(Requete(
    {"niche": "C", "format": "9_16", "url": url_exp, "origine": "export", "source_id": original["id"],
     "edition": dict(edition, ratio="4:3")}))) == 400)
verifier("cadre hors limites -> 400", statut_http(S.v595_ajouter_media(Requete(
    {"niche": "C", "format": "9_16", "url": url_exp, "origine": "export", "source_id": original["id"],
     "edition": dict(edition, cadre={"gauche": 99999})}))) == 400)
r = lancer(S.v595_ajouter_media(Requete(
    {"niche": "C", "format": "9_16", "url": url_exp, "origine": "export", "source_id": original["id"],
     "statut": "validee", "edition": edition,
     "fichier": {"nom": "festival_9x16.mp4", "duree": 38.0, "largeur": 608, "hauteur": 1080}})))
export = r["media"]
verifier("export : statut « a_verifier » malgré « validee » demandé", export["statut"] == "a_verifier")
verifier("export : pointe vers son original", export["source_id"] == original["id"])
verifier("export : réglages conservés (2 s → 40 s, 9:16)",
         export["edition"]["debut"] == 2 and export["edition"]["fin"] == 40 and export["edition"]["ratio"] == "9:16")
verifier("export : dimensions réelles conservées", export["fichier"]["largeur"] == 608 and export["fichier"]["hauteur"] == 1080)
orig_apres = [d for d in BASE[S.V595_MEDIAS].docs if d["id"] == original["id"]][0]
verifier("l'original reste intact (statut, URL)", orig_apres["statut"] == "en_cours" and orig_apres["url"] == url_orig)
url_exp2 = fichier("exp169", "video_exp169.mp4", "video/mp4")
r2 = lancer(S.v595_ajouter_media(Requete(
    {"niche": "C", "format": "16_9", "url": url_exp2, "origine": "export", "source_id": original["id"],
     "edition": dict(edition, ratio="16:9", cadre={"gauche": 0, "haut": 0, "largeur": 1920, "hauteur": 1080})})))
verifier("un export 16:9 n'archive pas le 9:16",
         [d for d in BASE[S.V595_MEDIAS].docs if d["id"] == export["id"]][0]["statut"] == "a_verifier"
         and r2["archives"] == 0)
url_exp3 = fichier("exp916b", "video_exp916b.mp4", "video/mp4")
r3 = lancer(S.v595_ajouter_media(Requete(
    {"niche": "C", "format": "9_16", "url": url_exp3, "origine": "export", "source_id": original["id"],
     "edition": edition})))
verifier("ré-export 9:16 : l'ancien est ARCHIVÉ, pas supprimé",
         [d for d in BASE[S.V595_MEDIAS].docs if d["id"] == export["id"]][0]["statut"] == "archivee"
         and r3["archives"] == 1)

print("\n5. Miniature et liens publics inchangés")
r = lancer(S.v595_ajouter_media(Requete(
    {"niche": "C", "format": "miniature", "url": url_img, "source_id": original["id"]})))
verifier("miniature : vrai fichier image, « en_cours »", r["media"]["statut"] == "en_cours" and r["media"]["origine"] == "fichier")
r = lancer(S.v595_ajouter_media(Requete({"niche": "B", "format": "16_9", "url": "https://youtu.be/zzz"})))
verifier("lien public : toujours accepté, origine « lien », « en_cours »",
         r["media"]["origine"] == "lien" and r["media"]["statut"] == "en_cours")
verifier("export sans jeton -> 403", statut_http(S.v595_ajouter_media(Requete(
    {"niche": "C", "format": "9_16", "url": url_exp}, coach=None))) == 403)

ok = sum(1 for _, c in RESULTATS if c)
print("\n%d/%d vérifications" % (ok, len(RESULTATS)))
sys.exit(0 if ok == len(RESULTATS) else 1)
