# -*- coding: utf-8 -*-
"""ESSAI-5a-1D — l'ecran dit-il la verite sur un essai ?

Regle metier : reserver ne consomme pas l'essai, seule la presence le consomme.
Le compteur, lui, est decremente des la reservation — et il DOIT l'etre, c'est
lui qui empeche une deuxieme reservation gratuite. On ne le change pas : on
l'interprete.

`t2_etat_essai` est EXTRAITE de `api/server.py` par AST. Aucune base, aucun
reseau, aucune ecriture.
"""
import ast
import asyncio
import io
import os
import sys
import types
from datetime import datetime, timezone, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVEUR = os.path.join(RACINE, "api", "server.py")
RESULTATS = []


def verifier(nom, ok, detail=""):
    RESULTATS.append((nom, bool(ok), str(detail)))


_ARBRE = ast.parse(io.open(SERVEUR, encoding="utf-8").read())
_VOULUS = ("T2_ESSAI_DISPONIBLE", "T2_ESSAI_RESERVE", "T2_ESSAI_EFFECTUE",
           "t2_etat_essai")
_NOEUDS = {}
for _n in _ARBRE.body:
    if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef)) and _n.name in _VOULUS:
        _n.decorator_list = []
        _NOEUDS[_n.name] = _n
    elif isinstance(_n, ast.Assign):
        for _c in _n.targets:
            if isinstance(_c, ast.Name) and _c.id in _VOULUS:
                _NOEUDS[_c.id] = _n
_MANQUE = [v for v in _VOULUS if v not in _NOEUDS]
if _MANQUE:
    print("EXTRACTION IMPOSSIBLE : %s" % _MANQUE)
    sys.exit(1)
SOURCE = "\n".join(ast.unparse(_NOEUDS[v]) for v in _VOULUS)


def code_nu(nom):
    _n = ast.parse(ast.unparse(_NOEUDS[nom])).body[0]
    if getattr(_n, "body", None) and isinstance(_n.body[0], ast.Expr) \
       and isinstance(getattr(_n.body[0], "value", None), ast.Constant) \
       and isinstance(_n.body[0].value.value, str):
        _n.body = _n.body[1:]
    return ast.unparse(_n)


# Le vrai filtre d'ESSAI-2, lu par AST : on ne recopie pas la regle.
_PARTAGE = os.path.join(RACINE, "api", "routes", "shared.py")
_FILTRE = None
for _n in ast.parse(io.open(_PARTAGE, encoding="utf-8").read()).body:
    if isinstance(_n, ast.Assign) and any(
            isinstance(c, ast.Name) and c.id == "ESSAI2_FILTRE_GRATUIT" for c in _n.targets):
        _FILTRE = ast.literal_eval(_n.value)
for _nom in ("api", "api.routes", "api.routes.shared"):
    sys.modules.setdefault(_nom, types.ModuleType(_nom))
sys.modules["api.routes.shared"].ESSAI2_FILTRE_GRATUIT = _FILTRE


class _Journal:
    def __init__(self): self.lignes = []
    def _n(self, m, *a): self.lignes.append(str(m))
    info = warning = error = _n


def _match(doc, f):
    for k, v in (f or {}).items():
        if k == "$or":
            if not any(_match(doc, c) for c in v): return False
            continue
        if doc.get(k) != v: return False
    return True


class _Coll:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]
        self.ecritures = 0

    async def find_one(self, f=None, p=None, **k):
        await asyncio.sleep(0)
        for d in self.docs:
            if _match(d, f): return dict(d)
        return None

    async def update_one(self, *a, **k):
        self.ecritures += 1
        raise AssertionError("ESSAI-5a-1D ne doit RIEN ecrire")

    async def insert_one(self, *a, **k):
        self.ecritures += 1
        raise AssertionError("ESSAI-5a-1D ne doit RIEN ecrire")


class _Base:
    def __init__(self, codes=None):
        self.discount_codes = _Coll(codes)
        self.reservations = _Coll()
        self.subscriptions = _Coll()


BAC = {}
CODE_ESSAI = [{"code": "AFR-ESSAI", "payment_method": "free", "total_paid": 0}]
CODE_PAYE = [{"code": "AFR-PULSE", "source": "stripe_payment"}]


def bac(codes=None):
    base = _Base(codes)
    journal = _Journal()
    g = {"__builtins__": __builtins__, "datetime": datetime, "timezone": timezone,
         "timedelta": timedelta, "db": base, "logger": journal}
    exec(compile(SOURCE, "<t2>", "exec"), g)
    BAC.clear(); BAC.update(g)
    return g, base, journal


def iso(h):
    return (datetime.now(timezone.utc) + timedelta(hours=h)).isoformat()


def resa(h=+48, validee=False, nom="Afroboost Silent", heure="18:30"):
    return {"id": "r1", "courseName": nom, "courseTime": heure,
            "datetime": iso(h), "validated": validee}


async def scenarios():
    # A — ESSAI DISPONIBLE
    g, _, _ = bac(CODE_ESSAI)
    e = await g["t2_etat_essai"]("AFR-ESSAI", [], 1)
    verifier("A1. aucun essai reserve -> etat « disponible »",
             e["is_trial"] is True and e["state"] == "available", str(e))
    verifier("A2. et aucune seance n'est annoncee", e["next_session"] is None)

    # B — ESSAI RESERVE : le point de depart de ce lot
    g, _, _ = bac(CODE_ESSAI)
    e = await g["t2_etat_essai"]("AFR-ESSAI", [resa()], 0)
    verifier("B1. reservation a venir -> etat « reserve », PAS « consomme »",
             e["state"] == "booked", str(e))
    verifier("B2. le compteur brut vaut 0 — mais il est expose A COTE de "
             "l'etat, il ne le remplace pas",
             e["remaining_raw"] == 0 and e["state"] == "booked")
    verifier("B3. la seance concernee est annoncee, sans nouvelle architecture",
             e["next_session"]["courseName"] == "Afroboost Silent"
             and e["next_session"]["courseTime"] == "18:30", str(e["next_session"]))
    verifier("B4. l'etat n'est JAMAIS « done » sur une simple reservation",
             e["state"] != "done")

    # C — REDEVENU DISPONIBLE (annulation : la reservation disparait)
    g, _, _ = bac(CODE_ESSAI)
    e = await g["t2_etat_essai"]("AFR-ESSAI", [], 1)
    verifier("C1. apres annulation -> « disponible »", e["state"] == "available")

    # C bis — no-show cloture : la reservation reste, mais elle est PASSEE
    g, _, _ = bac(CODE_ESSAI)
    e = await g["t2_etat_essai"]("AFR-ESSAI", [resa(h=-72)], 1)
    verifier("C2. seance passee sans validation -> « disponible », "
             "l'essai n'a pas ete consomme", e["state"] == "available", str(e))

    # D — PRESENCE CONFIRMEE
    g, _, _ = bac(CODE_ESSAI)
    e = await g["t2_etat_essai"]("AFR-ESSAI", [resa(h=-24, validee=True)], 0)
    verifier("D1. presence confirmee -> « effectue »", e["state"] == "done", str(e))
    verifier("D2. une presence l'emporte sur une reservation a venir",
             (await g["t2_etat_essai"]("AFR-ESSAI",
                                       [resa(h=+48), resa(h=-24, validee=True)], 0))["state"] == "done")

    # FORFAIT PAYANT — l'ecran ne change pas d'un pixel
    g, _, _ = bac(CODE_PAYE)
    for _r, _rest in (([], 7), ([resa()], 6), ([resa(h=-24, validee=True)], 6)):
        e = await g["t2_etat_essai"]("AFR-PULSE", _r, _rest)
        verifier("P1. forfait payant -> is_trial False, aucun etat impose",
                 e == {"is_trial": False}, str(e))
    g, _, _ = bac(CODE_PAYE)
    verifier("P2. code inconnu -> is_trial False",
             await g["t2_etat_essai"]("AFR-INCONNU", [], 3) == {"is_trial": False})
    verifier("P3. code vide -> is_trial False",
             await g["t2_etat_essai"]("", [], 3) == {"is_trial": False})

    # AUCUNE ECRITURE
    g, base, _ = bac(CODE_ESSAI)
    await g["t2_etat_essai"]("AFR-ESSAI", [resa()], 0)
    verifier("W1. aucune ecriture : l'etat est DERIVE, jamais stocke",
             base.discount_codes.ecritures == 0
             and base.reservations.ecritures == 0
             and base.subscriptions.ecritures == 0)


def structure():
    nu = code_nu("t2_etat_essai")
    verifier("S1. aucune nouvelle source de verite : ni ecriture, ni compteur",
             not any(m in nu for m in ("insert_one", "update_one", "$set", "$inc")))
    verifier("S2. la nature d'essai vient d'ESSAI-2, elle n'est pas redefinie",
             "ESSAI2_FILTRE_GRATUIT" in nu)
    verifier("S3. l'etat se derive des reservations recues, sans les relire",
             "db.reservations" not in nu)
    verifier("S4. le compteur brut est conserve, pas efface",
             "remaining_raw" in nu)

    serv = io.open(SERVEUR, encoding="utf-8").read()
    verifier("S5. le decrement a la reservation est INTACT",
             '"used_sessions": new_used' in serv and "new_remaining = remaining - quantity" in serv)
    verifier("S6. la garde d'unicite (forfait_utilisable) est INTACTE",
             "forfait_utilisable" in serv)
    verifier("S7. la restitution des essais non honores est INTACTE",
             "t1_restituer_essais_non_honores" in serv
             and "trial_credit_restored" in serv)
    verifier("S8. `validated` est desormais projete vers l'espace abonne — "
             "c'etait le seul champ manquant",
             '"validated": 1,' in serv)

    moi = io.open(os.path.abspath(__file__), encoding="utf-8").read()
    mods = set()
    for n in ast.walk(ast.parse(moi)):
        if isinstance(n, ast.Import):
            mods.update(x.name.split(".")[0] for x in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    verifier("S9. ce test n'importe que la bibliotheque standard, hors reseau",
             mods <= {"ast", "asyncio", "io", "os", "sys", "types", "datetime"},
             str(sorted(mods)))


def main():
    structure()
    b = asyncio.new_event_loop()
    try:
        b.run_until_complete(scenarios())
    finally:
        b.close()
    ok = sum(1 for _, r, _ in RESULTATS if r)
    print("=" * 78)
    for nom, r, detail in RESULTATS:
        print(("  PASS  " if r else "  FAIL  ") + nom + (("   -> " + detail) if not r else ""))
    print("=" * 78)
    print("Ecritures en base : 0 — l'etat est derive, jamais stocke")
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())
