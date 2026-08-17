# -*- coding: utf-8 -*-
"""L'agenda public rend les MEMES horaires que les cartes d'offres.

Le vrai `sessions_agenda` est extrait de `api/server.py` par AST et execute
sur un faux MongoDB, avec les documents REELS de production (les identifiants
et les drapeaux sont ceux observes le 17/08/2026).

Aucun reseau. Aucune base. Aucune ecriture.

Lancement :  python3 tests/test_sessions_agenda.py
"""

import ast
import asyncio
import io
import os
import sys
from datetime import datetime, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVEUR = os.path.join(RACINE, "api", "server.py")
SOURCE = io.open(SERVEUR, encoding="utf-8").read()
ARBRE = ast.parse(SOURCE)
LIGNES = SOURCE.splitlines(True)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def noeud(nom):
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return n
    raise AssertionError("introuvable : %s" % nom)


def extraire(nom):
    n = noeud(nom)
    return "".join(LIGNES[n.lineno - 1:n.end_lineno])


def code_nu(nom):
    n = noeud(nom)
    corps = list(n.body)
    if (corps and isinstance(corps[0], ast.Expr)
            and isinstance(getattr(corps[0], "value", None), ast.Constant)
            and isinstance(corps[0].value.value, str)):
        corps = corps[1:]
    return "\n".join(ast.unparse(x) for x in corps)


# ------------------------------------------------------- faux client MongoDB
MANQUANT = object()


def _val(doc, chemin):
    cur = doc
    for p in chemin.split("."):
        if not isinstance(cur, dict) or p not in cur:
            return MANQUANT
        cur = cur[p]
    return cur


def _match(doc, q):
    for cle, attendu in (q or {}).items():
        if cle == "$or":
            if not any(_match(doc, sous) for sous in attendu):
                return False
            continue
        obtenu = _val(doc, cle)
        if isinstance(attendu, dict):
            for op, v in attendu.items():
                if op == "$ne":
                    if obtenu is not MANQUANT and obtenu == v:
                        return False
                elif op == "$in":
                    if obtenu is MANQUANT or obtenu not in v:
                        return False
                elif op == "$exists":
                    if bool(obtenu is not MANQUANT) != bool(v):
                        return False
                else:
                    raise AssertionError("operateur non simule : %s" % op)
        else:
            if obtenu is MANQUANT or obtenu != attendu:
                return False
    return True


class _Curseur(object):
    def __init__(self, d):
        self.d = d

    async def to_list(self, n):
        await asyncio.sleep(0)
        import copy
        return [copy.deepcopy(x) for x in self.d[:n]]


class _Coll(object):
    def __init__(self, docs):
        self.docs = docs

    def find(self, q=None, p=None):
        return _Curseur([d for d in self.docs if _match(d, q or {})])


class _Base(object):
    def __init__(self, offres, cours):
        self.offers = _Coll(offres)
        self.courses = _Coll(cours)


# ------------------------------------------------------------------ le bac
CONSTANTES = """
_V184_WEEKDAY_LABELS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
"""

A_EXTRAIRE = ["_v184_parse_time_hhmm", "_v184_next_occurrences", "sessions_agenda"]


def bac(offres, cours):
    base = _Base(offres, cours)
    b = {
        "db": base,
        "datetime": datetime, "timedelta": timedelta,
        "logger": type("l", (), {k: staticmethod(lambda *a, **kw: None)
                                 for k in ("info", "warning", "error", "debug")}),
        "api_router": type("r", (), {"get": staticmethod(lambda *a, **k: (lambda f: f))}),
    }
    exec(compile("\n\n".join([CONSTANTES] + [extraire(f) for f in A_EXTRAIRE]),
                 "<agenda>", "exec"), b)
    return b, base


# --------------------------------------------------- documents REELS observes
MERCREDI = {"id": "64b4c975", "name": "Afroboost Silent – Session Cardio",
            "weekday": 3, "time": "18:30", "locationName": "Neuchâtel",
            "visible": True, "archived": True, "agenda_abonne": True}
DIMANCHE = {"id": "23534f7c", "name": "Afroboost Silent – Sunday Vibes",
            "weekday": 0, "time": "18:30", "locationName": "Neuchâtel",
            "visible": True, "archived": True, "agenda_abonne": True}
EVENEMENT = {"id": "laff21", "name": "Laff Festival", "weekday": 5, "date": "2026-08-21",
             "time": "18:30", "locationName": "Lausanne", "visible": True, "archived": False}
RETIRE = {"id": "vieux", "name": "Cours retire", "weekday": 2, "time": "20:00",
          "visible": True, "archived": True}          # archive SANS agenda_abonne
MASQUE = {"id": "brouillon", "name": "Nouveau cours", "weekday": 4, "time": "18:30",
          "visible": False, "archived": False}

PULSE = {"id": "pulse", "name": "PULSE x10 cours", "visible": True,
         "linked_course_ids": ["64b4c975", "23534f7c"]}
MEMBRES = {"id": "membres", "name": "Membres", "visible": True,
           "linked_course_ids": ["64b4c975", "23534f7c"]}
OFFRE_EVT = {"id": "off-evt", "name": "Afroboost Silent", "visible": True,
             "linked_course_ids": ["laff21"]}
OFFRE_RETIREE = {"id": "off-vieux", "name": "Ancienne offre", "visible": True,
                 "linked_course_ids": ["vieux"]}


async def agenda(offres, cours, jours=60):
    b, _ = bac(offres, cours)
    return await b["sessions_agenda"](days=jours)


def jours_de(sortie):
    return sorted({o["datetime"][:10] for o in sortie["occurrences"]})


async def scenarios():
    # --- A. le cas reel : PULSE et Membres, mercredi + dimanche --------------
    s = await agenda([PULSE, MEMBRES], [MERCREDI, DIMANCHE, EVENEMENT], jours=30)
    occ = s["occurrences"]
    verifier("A1. les seances recurrentes du mercredi et du dimanche SORTENT",
             len(occ) > 0, "%d occurrence(s)" % len(occ))

    _mercredis = [o for o in occ if o["course_id"] == "64b4c975"]
    _dimanches = [o for o in occ if o["course_id"] == "23534f7c"]
    verifier("A2. les deux cours archives mais `agenda_abonne` sont presents",
             len(_mercredis) > 0 and len(_dimanches) > 0,
             "mercredi %d / dimanche %d" % (len(_mercredis), len(_dimanches)))

    verifier("A3. tous les mercredis tombent bien un mercredi",
             all(datetime.fromisoformat(o["datetime"]).weekday() == 2 for o in _mercredis))
    verifier("A4. tous les dimanches tombent bien un dimanche",
             all(datetime.fromisoformat(o["datetime"]).weekday() == 6 for o in _dimanches))
    verifier("A5. l'heure annoncee est 18:30 partout",
             all(o["datetime"][11:16] == "18:30" for o in _mercredis + _dimanches),
             str(sorted({o["datetime"][11:16] for o in _mercredis + _dimanches})))

    # --- B. ANTI-DOUBLON : deux offres, un seul cours -----------------------
    _cles = [(o["course_id"], o["datetime"]) for o in occ]
    verifier("B1. PULSE et Membres pointent le meme cours -> UNE occurrence",
             len(_cles) == len(set(_cles)),
             "%d occurrences pour %d cles distinctes" % (len(_cles), len(set(_cles))))
    verifier("B2. mais les DEUX offres sont listees a cote de la seance",
             _mercredis and sorted(x["id"] for x in _mercredis[0]["offers"]) == ["membres", "pulse"],
             str(_mercredis[0]["offers"] if _mercredis else None))

    # --- C. la regle exacte : archive SEUL ne suffit pas --------------------
    s2 = await agenda([PULSE, MEMBRES, OFFRE_RETIREE], [MERCREDI, DIMANCHE, RETIRE], jours=30)
    verifier("C1. un cours archive SANS `agenda_abonne` reste dehors, meme lie a une offre",
             not any(o["course_id"] == "vieux" for o in s2["occurrences"]))
    s3 = await agenda([], [MASQUE], jours=30)
    verifier("C2. un cours `visible: false` non lie reste dehors",
             len(s3["occurrences"]) == 0, str(s3["occurrences"][:1]))
    s4 = await agenda([], [EVENEMENT], jours=60)
    verifier("C3. un cours publie sort meme sans offre liee",
             len(s4["occurrences"]) == 1)

    # --- D. FLEXIBILITE : aucun jour n'est fige -----------------------------
    JEUDI = dict(MERCREDI, id="jeu", name="Atelier", weekday=4, time="19:00")
    OFF_J = {"id": "oj", "name": "Offre jeudi", "visible": True, "linked_course_ids": ["jeu"]}
    sj = await agenda([OFF_J], [JEUDI], jours=30)
    verifier("D1. un cours du jeudi apparait le JEUDI, sans une ligne de code en plus",
             sj["occurrences"] and all(
                 datetime.fromisoformat(o["datetime"]).weekday() == 3 for o in sj["occurrences"]),
             str(jours_de(sj)[:3]))
    verifier("D2. et a 19:00",
             all(o["datetime"][11:16] == "19:00" for o in sj["occurrences"]))

    # le coach deplace le cours : jeudi -> samedi, 19:00 -> 10:30
    SAMEDI = dict(JEUDI, weekday=6, time="10:30")
    ss = await agenda([OFF_J], [SAMEDI], jours=30)
    verifier("D3. deplace au samedi, les futures occurrences suivent",
             ss["occurrences"] and all(
                 datetime.fromisoformat(o["datetime"]).weekday() == 5 for o in ss["occurrences"]),
             str(jours_de(ss)[:3]))
    verifier("D4. et la nouvelle heure suit aussi",
             all(o["datetime"][11:16] == "10:30" for o in ss["occurrences"]))
    verifier("D5. l'identifiant du cours n'a pas bouge — la config tient au cours",
             all(o["course_id"] == "jeu" for o in ss["occurrences"]))

    # les sept jours, sans distinction
    for _j in range(7):
        _c = dict(MERCREDI, id="j%d" % _j, weekday=_j)
        _o = {"id": "o%d" % _j, "name": "o", "visible": True, "linked_course_ids": ["j%d" % _j]}
        _s = await agenda([_o], [_c], jours=14)
        if not _s["occurrences"]:
            verifier("D6. les sept jours de la semaine sont couverts", False, "weekday=%d vide" % _j)
            break
    else:
        verifier("D6. les sept jours de la semaine sont couverts", True)

    # --- E. contenu d'une occurrence ---------------------------------------
    o = _mercredis[0]
    verifier("E1. l'occurrence porte tout ce qu'il faut a l'ecran",
             all(k in o for k in ("course_id", "name", "date", "time", "datetime",
                                  "locationName", "offers", "recurrent")),
             str(sorted(o.keys())))
    verifier("E2. un cours recurrent est marque comme tel",
             o.get("recurrent") is True)
    _evt = [x for x in occ if x["course_id"] == "laff21"]
    verifier("E3. un evenement date est marque comme NON recurrent",
             _evt and _evt[0].get("recurrent") is False, str(_evt[:1]))
    verifier("E4. les occurrences sortent triees",
             [x["datetime"] for x in occ] == sorted(x["datetime"] for x in occ))

    # --- F. bornes ----------------------------------------------------------
    verifier("F1. l'horizon demande est respecte",
             all(datetime.fromisoformat(x["datetime"]) <= datetime.now() + timedelta(days=31)
                 for x in occ))
    _s = await agenda([PULSE], [MERCREDI], jours=10000)
    verifier("F2. un horizon aberrant est borne, pas honore", _s["jours"] == 180, str(_s["jours"]))


def structure():
    nu = code_nu("sessions_agenda")
    verifier("S1. la route reutilise le calcul d'occurrences existant",
             "_v184_next_occurrences" in nu)
    verifier("S2. elle applique la regle V426 `agenda_abonne`",
             "agenda_abonne" in nu)
    verifier("S3. elle dedoublonne par (cours, instant), jamais par offre",
             "course_id" in nu and "datetime" in nu)
    verifier("S4. elle ne code AUCUN jour de la semaine",
             not any(j in nu.lower() for j in
                     ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")))
    verifier("S5. elle n'ecrit rien en base",
             not any(m in nu for m in ("update_one", "insert_one", "delete_one", "$set")))
    verifier("S6. elle ne lit pas les offres masquees",
             "'visible'" in nu.replace('"', "'"))

    moi = io.open(os.path.abspath(__file__), encoding="utf-8").read()
    mods = set()
    for n in ast.walk(ast.parse(moi)):
        if isinstance(n, ast.Import):
            mods.update(x.name.split(".")[0] for x in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    verifier("S7. ce test n'importe que la bibliotheque standard hors reseau",
             mods <= {"ast", "asyncio", "io", "os", "sys", "datetime", "copy"}, str(sorted(mods)))


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
    print("Requetes MongoDB reelles : 0 — la base est un double en memoire")
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())
