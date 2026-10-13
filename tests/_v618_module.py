# -*- coding: utf-8 -*-
"""V618 PHASE 2 — rend le VRAI module `api.routes.abonnement_actuel` disponible dans les bancs
qui remplacent `api.routes` par un faux paquet (extraction AST + faux FastAPI).

Le module est chargé depuis son fichier réel (aucune copie de règle) ; seule la ligne
`from fastapi import …` est neutralisée, car ces bancs posent un faux `fastapi` sans routeur.
"""
import os
import sys
import types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Routeur:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, _nom):
        return lambda *a, **k: (lambda f: f)


def brancher(shared=None):
    """Enregistre le vrai module sous `api.routes.abonnement_actuel` et le renvoie.
    `shared` : le module (réel) qui fournit `_v391_est_expire` si le faux `shared` du banc
    ne l'a pas."""
    src = open(os.path.join(RACINE, "api", "routes", "abonnement_actuel.py"), encoding="utf-8").read()
    src = src.replace("from fastapi import APIRouter, HTTPException, Request", "")
    mod = types.ModuleType("api.routes.abonnement_actuel")
    mod.__file__ = os.path.join(RACINE, "api", "routes", "abonnement_actuel.py")
    _fa = sys.modules.get("fastapi")
    mod.APIRouter = _Routeur
    mod.HTTPException = getattr(_fa, "HTTPException", Exception)
    mod.Request = object
    exec(compile(src, mod.__file__, "exec"), mod.__dict__)
    sys.modules["api.routes.abonnement_actuel"] = mod
    _pk = sys.modules.get("api.routes")
    if _pk is not None:
        setattr(_pk, "abonnement_actuel", mod)
    _sh = sys.modules.get("api.routes.shared")
    if _sh is not None and shared is not None and not hasattr(_sh, "_v391_est_expire"):
        _sh._v391_est_expire = shared._v391_est_expire
    return mod
