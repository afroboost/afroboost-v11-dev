#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V610l — bibliothèque AUDIO de l'éditeur d'invitation (`GET /api/referral/campaigns-medias`).

Cause du 500 en production (12/10/2026, reproduit en lecture seule sur Atlas) : les
fichiers audio sont stockés AVEC leur contenu (`data`) ; `find(...).sort("created_at")`
triait les documents entiers en mémoire -> « Sort exceeded memory limit of 33554432 bytes ».
Correctif : `aggregate` $match -> $project (sans `data`) -> $sort -> $limit.

La fausse base ci-dessous se comporte comme Atlas : un tri sur des documents qui portent
encore `data` lève l'erreur ; le même tri APRÈS retrait de `data` passe.

Lancement : python3 tests/test_v610l_medias_audio.py
"""
import asyncio
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_referral_campaigns as T  # noqa: E402  (pose l'environnement du banc)
import api.routes.invitation_edition as IE  # noqa: E402

H = T.H
verifier = H.verifier
COACH = T.COACH_A

class TriTropLourd(Exception):
    pass


def _correspond(doc, filtre):
    for cle, cond in filtre.items():
        val = doc.get(cle)
        if isinstance(cond, dict):
            if "$exists" in cond and (cle in doc) != cond["$exists"]:
                return False
            if "$regex" in cond:
                import re
                if not isinstance(val, str) or not re.search(cond["$regex"], val):
                    return False
        elif val != cond:
            return False
    return True


class _Curseur:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *a, **k):
        if any("data" in d for d in self.docs):
            raise TriTropLourd("Sort exceeded memory limit of 33554432 bytes")
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    async def to_list(self, n):
        return self.docs[:n]


class _Fichiers:
    def __init__(self, docs):
        self.docs = docs
        self.pipelines = []

    def find(self, filtre, projection=None):
        return _Curseur([dict(d) for d in self.docs if _correspond(d, filtre)])

    def aggregate(self, pipeline):
        self.pipelines.append(pipeline)
        docs = [dict(d) for d in self.docs]
        for etape in pipeline:
            if "$match" in etape:
                docs = [d for d in docs if _correspond(d, etape["$match"])]
            elif "$project" in etape:
                exclus = [k for k, v in etape["$project"].items() if v == 0]
                docs = [{k: v for k, v in d.items() if k not in exclus} for d in docs]
            elif "$sort" in etape:
                if any("data" in d for d in docs):
                    raise TriTropLourd("Sort exceeded memory limit of 33554432 bytes")
                (champ, sens), = etape["$sort"].items()
                docs.sort(key=lambda d: str(d.get(champ) or ""), reverse=sens < 0)
            elif "$limit" in etape:
                docs = docs[:etape["$limit"]]
        return _Curseur(docs)


class _Vide:
    def find(self, *a, **k):
        return _Curseur([])


class _Base(dict):
    def __getitem__(self, cle):
        return dict.get(self, cle) or _Vide()


def fichier(fid, nom, genre, date, coach=COACH, **extra):
    d = {"file_id": fid, "filename": "%s_%s" % (genre, fid), "original_name": nom, "content_type": genre + "/mpeg",
         "coach_email": coach, "size": 1000, "created_at": date, "data": b"x" * 64}
    d.update(extra)
    return d


async def principal():
    T.depart()
    fichiers = _Fichiers([
        fichier("a1", "musique.mp3", "audio", "2026-03-08T10:00:00"),
        fichier("a2", "deviens_afroboosteur.mp3", "audio", "2026-10-12T12:20:28"),
        fichier("a3", "doublon.mp3", "audio", "2026-10-12T13:00:00", doublon_de="a2"),
        fichier("a4", "autre_coach.mp3", "audio", "2026-10-12T14:00:00", coach=T.COACH_B),
        fichier("v1", "clip.mp4", "video", "2026-10-11T09:00:00"),
    ])
    base = _Base(uploaded_files=fichiers)
    ancien = IE._db
    IE._db = lambda: base
    try:
        c, r = await H.appel(IE.medias_lister(T.rq(COACH), type="audio"))
    finally:
        IE._db = ancien
    verifier("L-1 bibliothèque audio -> 200 (plus de 500 « Sort exceeded memory limit »)", c == 200, (c, r))
    items = (r or {}).get("items") or []
    noms = [i.get("nom") for i in items]
    verifier("L-2 les audios du coach, le plus récent d'abord", noms == ["deviens_afroboosteur.mp3", "musique.mp3"], noms)
    verifier("L-3 ni doublon, ni fichier d'un autre coach, ni vidéo", "doublon.mp3" not in noms
             and "autre_coach.mp3" not in noms and "clip.mp4" not in noms, noms)
    verifier("L-4 adresse du fichier existant (jamais recopié)",
             items and items[0]["url"] == "/api/files/a2/audio_a2", items[:1])
    verifier("L-5 aucun contenu de fichier renvoyé", all("data" not in i for i in items), items)
    p = fichiers.pipelines[0] if fichiers.pipelines else []
    etapes = [list(e.keys())[0] for e in p]
    verifier("L-6 `data` retiré AVANT le tri", etapes[:4] == ["$match", "$project", "$sort", "$limit"]
             and p[1]["$project"].get("data") == 0, etapes)
    # L'ancienne requête échoue bien sur ce banc (le banc reproduit la panne d'Atlas).
    try:
        fichiers.find({"coach_email": COACH}).sort("created_at", -1)
        verifier("L-7 le banc reproduit la panne de l'ancien tri", False)
    except TriTropLourd:
        verifier("L-7 le banc reproduit la panne de l'ancien tri", True)


if __name__ == "__main__":
    asyncio.run(principal())
    _res = [r for r in H.RESULTATS if r[0].startswith("L-")]
    for _nom, _ok, _detail in _res:
        print(("OK   " if _ok else "ÉCHEC ") + _nom + ("" if _ok else "  -> %r" % (_detail,)))
    _n = sum(1 for r in _res if r[1])
    print("\n%d / %d vérifications V610l bibliothèque audio" % (_n, len(_res)))
    sys.exit(0 if _n == len(_res) == 7 else 1)
