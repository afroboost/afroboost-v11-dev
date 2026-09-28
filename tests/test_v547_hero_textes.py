# -*- coding: utf-8 -*-
"""V547 — textes du Hero modifiables (heroTitle / heroSubtitle / heroCtaLabel).

CE QUE CE BANC TIENT :
  * le modèle `Concept` porte les trois champs avec, pour défaut, le texte
    exact qui était écrit en dur dans App.js (un concept existant rend donc
    la même chose qu'avant) ;
  * `ConceptUpdate` les accepte, optionnels (None par défaut) ;
  * `PUT /concept` : un appelant non super-admin ne peut PAS les écrire (les
    champs sont retirés, le reste de l'enregistrement passe) ;
  * pour le super-admin, les valeurs sont TRONQUÉES (120 / 240 / 60) au lieu
    d'un 422 qui casserait l'auto-save ; la chaîne vide passe (= défaut).

AUCUNE BASE RÉELLE, AUCUN RÉSEAU.
    python3 tests/test_v547_hero_textes.py
"""
import ast, asyncio, io, os, sys, types
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
APP = io.open(os.path.join(RACINE, "frontend", "src", "App.js"), encoding="utf-8").read()
# V554 : les défauts du Hero ont quitté App.js pour utils/heroLayout.js
# (HERO_TEXTES_DEFAUT), rendus par components/HeroTexte.js. La garantie
# « le front porte le texte historique » est vérifiée là où il vit désormais.
APP += io.open(os.path.join(RACINE, "frontend", "src", "utils", "heroLayout.js"), encoding="utf-8").read()
ARBRE = ast.parse(SRC)
RESULTATS = []

TITRE = "Danse. Transpire. Lâche prise."
SOUS_TITRE = "Vis l'expérience Afroboost : danse afrobeat et fitness au casque, même si tu n'as jamais dansé."
CTA = "Réserver mon 1er cours gratuit"


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


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


ADMIN = "admin@exemple.invalid"


def charger():
    ns = {
        "BaseModel": BaseModel, "ConfigDict": ConfigDict, "Optional": Optional,
        "List": List, "HTTPException": HTTPException, "Request": object,
        "logger": types.SimpleNamespace(error=lambda *a, **k: None),
        "is_super_admin": lambda e: e == ADMIN,
        "require_auth": lambda req: req.email,
        "db": types.SimpleNamespace(concept=Coll()),
    }
    for nom in ("Concept", "ConceptUpdate", "V547_HERO_LIMITES",
                "v547_filtrer_textes_hero", "update_concept"):
        exec(_noeud(nom), ns)
    return ns


def run(c):
    return asyncio.new_event_loop().run_until_complete(c)


def main():
    ns = charger()
    Concept, ConceptUpdate = ns["Concept"], ns["ConceptUpdate"]

    # 1. Défauts du modèle = texte historique d'App.js, caractère pour caractère
    c = Concept()
    verifier("defaut heroTitle", c.heroTitle == TITRE, repr(c.heroTitle))
    verifier("defaut heroSubtitle", c.heroSubtitle == SOUS_TITRE, repr(c.heroSubtitle))
    verifier("defaut heroCtaLabel", c.heroCtaLabel == CTA, repr(c.heroCtaLabel))
    verifier("defauts presents dans App.js", all(t in APP for t in (TITRE, SOUS_TITRE, CTA)))
    # un concept stocké AVANT V547 (sans les champs) reçoit les défauts
    ancien = Concept(**{"id": "concept", "appName": "Afroboost"})
    verifier("concept existant -> defauts", ancien.heroTitle == TITRE and ancien.heroCtaLabel == CTA)

    # 2. ConceptUpdate accepte les champs, None par défaut
    u = ConceptUpdate()
    verifier("update None par defaut", u.heroTitle is None and u.heroSubtitle is None and u.heroCtaLabel is None)
    u = ConceptUpdate(heroTitle="A", heroSubtitle="B", heroCtaLabel="C")
    verifier("update accepte les 3", (u.heroTitle, u.heroSubtitle, u.heroCtaLabel) == ("A", "B", "C"))
    long_ok = ConceptUpdate(heroTitle="x" * 500)  # pas de 422
    verifier("update long accepte (pas de 422)", len(long_ok.heroTitle) == 500)

    # 3. Fonction pure : filtre non-admin + troncature admin
    f = ns["v547_filtrer_textes_hero"]
    r = f({"heroTitle": "T", "heroSubtitle": "S", "heroCtaLabel": "C", "appName": "X"}, False)
    verifier("non-admin : champs retires", r == {"appName": "X"}, repr(r))
    r = f({"heroTitle": "t" * 200, "heroSubtitle": "s" * 300, "heroCtaLabel": "c" * 90}, True)
    verifier("admin : troncature 120/240/60",
             (len(r["heroTitle"]), len(r["heroSubtitle"]), len(r["heroCtaLabel"])) == (120, 240, 60))
    r = f({"heroTitle": ""}, True)
    verifier("admin : chaine vide conservee (= defaut)", r == {"heroTitle": ""})
    r = f({"heroTitle": TITRE}, True)
    verifier("admin : texte court intact", r["heroTitle"] == TITRE)

    # 4. Route PUT /concept (base simulée)
    upd = ns["update_concept"]
    corps = ConceptUpdate(appName="Mon club", heroTitle="PIRATE", heroSubtitle="PIRATE", heroCtaLabel="PIRATE")
    doc = run(upd(corps, types.SimpleNamespace(email="coach@exemple.invalid")))
    verifier("PUT coach : ecrit le reste", doc.get("appName") == "Mon club", repr(doc))
    verifier("PUT coach : hero non ecrit",
             not any(k in doc for k in ("heroTitle", "heroSubtitle", "heroCtaLabel")), repr(doc))
    verifier("PUT coach : concept global intact", "concept" not in ns["db"].concept.docs)

    corps = ConceptUpdate(heroTitle="T" * 130, heroSubtitle="Sous", heroCtaLabel="C" * 61)
    doc = run(upd(corps, types.SimpleNamespace(email=ADMIN)))
    verifier("PUT admin : concept global", doc.get("id") == "concept")
    verifier("PUT admin : titre tronque 120", doc.get("heroTitle") == "T" * 120)
    verifier("PUT admin : sous-titre ecrit", doc.get("heroSubtitle") == "Sous")
    verifier("PUT admin : cta tronque 60", doc.get("heroCtaLabel") == "C" * 60)
    doc = run(upd(ConceptUpdate(heroTitle=""), types.SimpleNamespace(email=ADMIN)))
    verifier("PUT admin : remise a vide", doc.get("heroTitle") == "")

    ok = sum(1 for _, b, _ in RESULTATS if b)
    for nom, b, d in RESULTATS:
        print(("OK   " if b else "ECHEC") + " " + nom + ("" if b else "  -> " + d))
    print("\n%d/%d verifications vertes" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())
