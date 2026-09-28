# -*- coding: utf-8 -*-
"""V554 — disposition du Hero (`concept.heroLayout`), cote serveur.

CE QUE CE BANC TIENT :
  * `v554_normaliser_hero_layout` : whitelist des cles, bornes x/y [0,1] et
    size [0.6,1.8], align dans la liste, bool / NaN / inf refuses, non-dict ->
    None, sortie toujours `v: 1`, payload geant ramene au schema ;
  * remise a zero : {"v":1,"desktop":null,"mobile":null} -> None, ECRIT en
    base (null), et le reste de la mise a jour passe ;
  * compatibilite : un concept sans heroLayout -> None ;
  * isolation : un coach ecrit dans `concept_{email}`, jamais dans `concept`,
    et n'a PAS besoin d'etre super-admin (contrairement aux textes V547).

Meme methode que tests/test_v547_hero_textes.py : on extrait les noeuds de
server.py par l'AST et on les execute avec une base simulee.
AUCUNE BASE REELLE, AUCUN RESEAU.
    python3 -m pytest tests/test_v554_hero_layout.py -q
"""
import ast, asyncio, io, os, types
from typing import List, Optional

import pytest
from pydantic import BaseModel, ConfigDict

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
ARBRE = ast.parse(SRC)
ADMIN = "admin@exemple.invalid"
COACH = "coach@exemple.invalid"


def _noeud(nom):
    for n in ARBRE.body:
        if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            n.decorator_list = []
            return ast.unparse(n)
        if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == nom for t in n.targets):
            return ast.unparse(n)
    raise AssertionError("introuvable : " + nom)


class Coll:
    def __init__(self):
        self.docs = {}

    async def find_one(self, f, p=None):
        d = self.docs.get(f.get("id"))
        return dict(d) if d else None

    async def update_one(self, f, u, upsert=False):
        d = self.docs.setdefault(f["id"], {"id": f["id"]})
        d.update(u.get("$set", {}))
        return types.SimpleNamespace(matched_count=1)


class HTTPException(Exception):
    def __init__(self, status_code=500, detail=""):
        super().__init__(detail)
        self.status_code = status_code


@pytest.fixture
def ns():
    ns = {
        "BaseModel": BaseModel, "ConfigDict": ConfigDict, "Optional": Optional,
        "List": List, "HTTPException": HTTPException, "Request": object,
        "logger": types.SimpleNamespace(error=lambda *a, **k: None),
        "is_super_admin": lambda e: e == ADMIN,
        "require_auth": lambda req: req.email,
        "db": types.SimpleNamespace(concept=Coll()),
    }
    for nom in ("Concept", "ConceptUpdate", "V547_HERO_LIMITES", "v547_filtrer_textes_hero",
                "V554_HERO_APPAREILS", "V554_HERO_ELEMENTS", "V554_HERO_ALIGNS",
                "V554_HERO_TAILLE_MIN", "V554_HERO_TAILLE_MAX",
                "_v554_nombre", "_v554_element", "v554_normaliser_hero_layout",
                "update_concept"):
        exec(_noeud(nom), ns)
    return ns


def run(c):
    return asyncio.new_event_loop().run_until_complete(c)


def req(email):
    return types.SimpleNamespace(email=email)


# ---------------------------------------------------------------- normalisation

def test_non_dict_donne_none(ns):
    n = ns["v554_normaliser_hero_layout"]
    for brut in (None, "x", 3, 1.5, True, [], [{"desktop": {}}], ("a",)):
        assert n(brut) is None, brut


def test_disposition_complete_intacte(ns):
    n = ns["v554_normaliser_hero_layout"]
    brut = {"v": 1,
            "desktop": {"title": {"x": 0.5, "y": 0.4, "size": 1.2, "align": "left"},
                        "subtitle": {"x": 0.5, "y": 0.6, "size": 1, "align": "right"},
                        "cta": {"x": 0.5, "y": 0.8, "size": 0.9}},
            "mobile": None}
    assert n(brut) == {"v": 1,
                       "desktop": {"title": {"x": 0.5, "y": 0.4, "size": 1.2, "align": "left"},
                                   "subtitle": {"x": 0.5, "y": 0.6, "size": 1.0, "align": "right"},
                                   "cta": {"x": 0.5, "y": 0.8, "size": 0.9}},
                       "mobile": None}


def test_bornes(ns):
    n = ns["v554_normaliser_hero_layout"]
    r = n({"mobile": {"title": {"x": -3, "y": 7, "size": 99},
                      "cta": {"x": 2, "y": -0.1, "size": 0.01}}})
    assert r["mobile"]["title"] == {"x": 0.0, "y": 1.0, "size": 1.8, "align": "center"}
    assert r["mobile"]["cta"] == {"x": 1.0, "y": 0.0, "size": 0.6}
    assert r["mobile"]["subtitle"] is None
    assert r["desktop"] is None and r["v"] == 1


def test_types_invalides(ns):
    n = ns["v554_normaliser_hero_layout"]
    # x ou y invalide -> element retire ; size invalide -> 1 ; align invalide -> center
    r = n({"desktop": {"title": {"x": "0.5", "y": 0.5},
                       "subtitle": {"x": 0.2, "y": 0.3, "size": "grand", "align": "justify"},
                       "cta": {"x": 0.5, "y": None}}})
    assert r["desktop"] == {"title": None,
                            "subtitle": {"x": 0.2, "y": 0.3, "size": 1.0, "align": "center"},
                            "cta": None}
    # element non-dict, disposition non-dict
    r = n({"desktop": {"title": [0.5, 0.5], "cta": {"x": 0.1, "y": 0.1}}, "mobile": "oui"})
    assert r["desktop"]["title"] is None and r["mobile"] is None


def test_bool_refuse_comme_nombre(ns):
    n = ns["v554_normaliser_hero_layout"]
    assert n({"desktop": {"title": {"x": True, "y": 0.5}}}) is None
    r = n({"desktop": {"cta": {"x": 0.5, "y": 0.5, "size": True}}})
    assert r["desktop"]["cta"]["size"] == 1.0  # True n'est pas 1.0 : defaut


def test_nan_inf_et_entier_geant(ns):
    n = ns["v554_normaliser_hero_layout"]
    for mauvais in (float("nan"), float("inf"), float("-inf"), 10 ** 400):
        assert n({"mobile": {"title": {"x": mauvais, "y": 0.5}}}) is None, mauvais
        r = n({"mobile": {"title": {"x": 0.5, "y": 0.5, "size": mauvais}}})
        assert r["mobile"]["title"]["size"] == 1.0, mauvais


def test_cles_inconnues_retirees_et_v_force(ns):
    n = ns["v554_normaliser_hero_layout"]
    r = n({"v": 99, "pirate": "<script>", "tablet": {"title": {"x": 0, "y": 0}},
           "desktop": {"title": {"x": 0.5, "y": 0.5, "align": "left", "color": "#f00", "html": "x"},
                       "logo": {"x": 0.5, "y": 0.5},
                       "cta": {"x": 0.5, "y": 0.5, "align": "left", "href": "javascript:"}}})
    assert set(r) == {"v", "desktop", "mobile"} and r["v"] == 1
    assert set(r["desktop"]) == {"title", "subtitle", "cta"}
    assert set(r["desktop"]["title"]) == {"x", "y", "size", "align"}
    assert set(r["desktop"]["cta"]) == {"x", "y", "size"}  # pas d'align sur le CTA


def test_payload_geant_ramene_au_schema(ns):
    n = ns["v554_normaliser_hero_layout"]
    brut = {"k%d" % i: "x" * 1000 for i in range(5000)}
    brut["desktop"] = {"title": {"x": 0.5, "y": 0.5, "bourre": list(range(100000))}}
    brut["desktop"].update({"e%d" % i: {"x": 0, "y": 0} for i in range(5000)})
    r = n(brut)
    assert len(repr(r)) < 400
    assert r["desktop"]["title"] == {"x": 0.5, "y": 0.5, "size": 1.0, "align": "center"}


def test_appareil_vide_donne_none(ns):
    n = ns["v554_normaliser_hero_layout"]
    r = n({"desktop": {}, "mobile": {"cta": {"x": 0.5, "y": 0.9}}})
    assert r["desktop"] is None and r["mobile"]["cta"]["y"] == 0.9


def test_remise_a_zero_complete(ns):
    n = ns["v554_normaliser_hero_layout"]
    assert n({"v": 1, "desktop": None, "mobile": None}) is None
    assert n({}) is None


# ---------------------------------------------------------------- modele

def test_compatibilite_concept_sans_heroLayout(ns):
    ancien = ns["Concept"](**{"id": "concept", "appName": "Afroboost"})
    assert ancien.heroLayout is None
    assert "heroLayout" in ancien.model_dump()  # la cle est presente (null) en GET
    assert ns["ConceptUpdate"]().heroLayout is None


# ---------------------------------------------------------------- PUT /concept

def test_put_coach_ecrit_dans_son_document(ns):
    upd, Upd = ns["update_concept"], ns["ConceptUpdate"]
    brut = {"v": 1, "desktop": {"title": {"x": 5, "y": 0.2, "size": 3, "align": "left", "z": 1}},
            "mobile": None}
    doc = run(upd(Upd(appName="Club", heroLayout=brut), req(COACH)))
    assert doc["id"] == "concept_" + COACH
    assert doc["appName"] == "Club"
    assert doc["heroLayout"]["desktop"]["title"] == {"x": 1.0, "y": 0.2, "size": 1.8, "align": "left"}
    docs = ns["db"].concept.docs
    assert "concept" not in docs  # le concept global n'est pas touche
    assert set(docs) == {"concept_" + COACH}


def test_put_admin_ecrit_le_global_et_coachs_isoles(ns):
    upd, Upd = ns["update_concept"], ns["ConceptUpdate"]
    lay_admin = {"v": 1, "desktop": {"cta": {"x": 0.1, "y": 0.1}}, "mobile": None}
    lay_coach = {"v": 1, "desktop": None, "mobile": {"cta": {"x": 0.9, "y": 0.9}}}
    run(upd(Upd(heroLayout=lay_admin), req(ADMIN)))
    run(upd(Upd(heroLayout=lay_coach), req(COACH)))
    docs = ns["db"].concept.docs
    assert docs["concept"]["heroLayout"]["desktop"]["cta"]["x"] == 0.1
    assert docs["concept"]["heroLayout"]["mobile"] is None
    assert docs["concept_" + COACH]["heroLayout"]["desktop"] is None
    assert docs["concept_" + COACH]["heroLayout"]["mobile"]["cta"]["x"] == 0.9


def test_put_remise_a_zero_ecrit_null(ns):
    upd, Upd = ns["update_concept"], ns["ConceptUpdate"]
    run(upd(Upd(heroLayout={"desktop": {"title": {"x": 0.3, "y": 0.3}}}), req(COACH)))
    assert ns["db"].concept.docs["concept_" + COACH]["heroLayout"] is not None
    doc = run(upd(Upd(heroLayout={"v": 1, "desktop": None, "mobile": None}), req(COACH)))
    assert "heroLayout" in doc and doc["heroLayout"] is None
    # relu par le modele de GET : null pour les deux appareils
    assert ns["Concept"](**doc).heroLayout is None


def test_put_sans_heroLayout_ne_touche_pas_la_disposition(ns):
    upd, Upd = ns["update_concept"], ns["ConceptUpdate"]
    run(upd(Upd(heroLayout={"mobile": {"cta": {"x": 0.5, "y": 0.5}}}), req(COACH)))
    doc = run(upd(Upd(appName="Autre nom"), req(COACH)))
    assert doc["heroLayout"]["mobile"]["cta"] == {"x": 0.5, "y": 0.5, "size": 1.0}


def test_textes_v547_toujours_reserves_au_super_admin(ns):
    upd, Upd = ns["update_concept"], ns["ConceptUpdate"]
    doc = run(upd(Upd(heroTitle="PIRATE", heroLayout={"desktop": {"cta": {"x": 0, "y": 0}}}), req(COACH)))
    assert "heroTitle" not in doc
    assert doc["heroLayout"]["desktop"]["cta"]["x"] == 0.0
