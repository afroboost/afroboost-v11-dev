#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UNE BASE MONGO EN MEMOIRE, juste assez pour les bancs de routes.

EXTRAIT DU BANC R2c, ET VOICI POURQUOI. Le banc R3a avait besoin des memes
outils ; il a commence par `import test_r2c_proprietaire_et_type`, ce qui
RE-EXECUTAIT tout le banc R2c au passage — 78 verifications rejouees, et un
echec R2c signale au milieu du rapport R3a. Un module de test n'est pas une
bibliotheque : il fait des choses en s'important.

Ce fichier, lui, ne fait RIEN a l'import. Il ne definit que des outils.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import api.server as S
from fastapi import HTTPException

# Les identites de test. `ADMIN` est le VRAI super-admin du depot : c'est le
# seul moyen de tester la regle telle qu'elle s'appliquera en production.
ADMIN = S.SUPER_ADMIN_EMAILS[0]
PARTENAIRE = "partenaire.un@exemple.test"
AUTRE = "partenaire.deux@exemple.test"
UUID_UN = "11111111-2222-3333-4444-555555555555"
UUID_DEUX = "99999999-8888-7777-6666-555555555555"


def _attrape(coro):
    """Execute et renvoie (resultat, code_http_ou_None).

    Un banc qui laisse remonter l'exception ne peut pas distinguer « refuse
    proprement en 403 » de « plante en 500 » — or c'est exactement la
    difference qui compte sur une route de securite.
    """
    try:
        return asyncio.run(coro), None
    except HTTPException as e:
        return None, e.status_code


def _correspond(doc, requete):
    for cle, attendu in (requete or {}).items():
        if cle == "$or":
            if not any(_correspond(doc, sous) for sous in attendu):
                return False
            continue
        valeur = doc.get(cle)
        if isinstance(attendu, dict):
            for op, arg in attendu.items():
                if op == "$in" and valeur not in arg:
                    return False
                if op == "$exists" and (cle in doc) != bool(arg):
                    return False
                if op == "$ne" and valeur == arg:
                    return False
        elif valeur != attendu:
            return False
    return True


def _projeter(doc, proj):
    if not proj:
        return dict(doc)
    gardees = [k for k, v in proj.items() if v and k != "_id"]
    if not gardees:
        return {k: v for k, v in doc.items() if k != "_id"}
    return {k: doc[k] for k in gardees if k in doc}


class _Curseur:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n=None):
        return list(self._docs)[:n] if n else list(self._docs)

    def sort(self, *a, **k):
        return self


class _Collection:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    def find(self, requete=None, proj=None):
        return _Curseur([_projeter(d, proj) for d in self.docs
                         if _correspond(d, requete)])

    async def find_one(self, requete=None, proj=None):
        for d in self.docs:
            if _correspond(d, requete):
                return _projeter(d, proj)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return type("R", (), {"inserted_id": doc.get("id")})()

    async def insert_many(self, docs):
        self.docs += [dict(d) for d in docs]

    async def update_one(self, requete, maj):
        for d in self.docs:
            if _correspond(d, requete):
                d.update(maj.get("$set", {}))
                return type("R", (), {"modified_count": 1})()
        return type("R", (), {"modified_count": 0})()

    async def update_many(self, requete, maj):
        return type("R", (), {"modified_count": 0})()

    async def delete_one(self, requete):
        # Le vrai driver SUPPRIME. Ce bouchon renvoyait 0 sans rien retirer :
        # un banc qui verifiait « l'offre a disparu » se serait cru vert en
        # mesurant le bouchon, jamais le code. Aucun banc n'en dependait.
        for i, d in enumerate(self.docs):
            if _correspond(d, requete):
                del self.docs[i]
                return type("R", (), {"deleted_count": 1})()
        return type("R", (), {"deleted_count": 0})()


class _Base:
    def __init__(self):
        self.offers = _Collection()
        self.courses = _Collection()
        self.coaches = _Collection([
            {"id": UUID_UN, "email": PARTENAIRE, "name": "Partenaire Un", "is_active": True},
            {"id": UUID_DEUX, "email": AUTRE, "name": "Partenaire Deux", "is_active": True},
        ])
        self.discount_codes = _Collection()

    def __getitem__(self, nom):
        return getattr(self, nom)


class _Requete:
    """Le strict minimum d'un `fastapi.Request` pour ces routes."""
    def __init__(self, email=None):
        self.headers = {} if email is None else {"X-User-Email": email}
        self.headers = _Entetes(self.headers)


class _Entetes(dict):
    def get(self, cle, defaut=""):
        for k, v in self.items():
            if k.lower() == str(cle).lower():
                return v
        return defaut


