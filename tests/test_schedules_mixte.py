# -*- coding: utf-8 -*-
"""UNE OFFRE MELANGE RECURRENCES ET DATES UNIQUES — CE QUE LE SERVEUR EN FAIT.

Ce banc execute le VRAI `_v184_next_occurrences` (extrait de `api/server.py`
par AST) et la VRAIE regle de deduplication V250 (recopiee depuis
`get_subscriber_space`, et verifiee identique par un test de structure).

CE QU'IL ETABLIT, ET QUI DECIDE DU PERIMETRE DU LOT : le moteur d'occurrences
SAIT DEJA melanger les deux types depuis V246, et le parcours visiteur
dedoublonne DEJA depuis V250. Aucune migration, aucun backfill, aucun champ
nouveau ne sont necessaires — le defaut etait entierement dans l'ecran.

Aucun reseau. Aucune base. Aucune ecriture.

Lancement :  python3 tests/test_schedules_mixte.py
"""

import ast
import io
import os
import sys
from datetime import datetime, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
ARBRE = ast.parse(SOURCE)
LIGNES = SOURCE.splitlines(True)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def extraire(nom):
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return "".join(LIGNES[n.lineno - 1:n.end_lineno])
    raise AssertionError("introuvable : %s" % nom)


def constante(nom):
    for n in ARBRE.body:
        if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == nom for t in n.targets):
            return "".join(LIGNES[n.lineno - 1:n.end_lineno])
    raise AssertionError("constante introuvable : %s" % nom)


ESP = {"__builtins__": __builtins__, "datetime": datetime, "timedelta": timedelta}
for _c in ("_V184_WEEKDAY_LABELS_FR",):
    exec(compile(constante(_c), "<cst>", "exec"), ESP)
for _f in ("_v184_parse_time_hhmm", "_v184_next_occurrences"):
    exec(compile(extraire(_f), "<srv>", "exec"), ESP)
occurrences_de = ESP["_v184_next_occurrences"]


# --- LA REGLE V250, telle que `get_subscriber_space` l'applique -------------
def dedup_v250(occurrences):
    def _norm(s):
        return (s or "").strip().lower()
    vus, sortie = set(), []
    for o in occurrences:
        k = (o.get("datetime"), _norm(o.get("name")), _norm(o.get("locationName")))
        if k in vus:
            continue
        vus.add(k)
        sortie.append(o)
    return sortie


def agenda_de_loffre(cours, jours=60):
    """Ce que voit le visiteur : toutes les occurrences des cours lies."""
    occ = []
    for c in cours:
        occ.extend(occurrences_de(c, days_ahead=jours))
    occ = dedup_v250(occ)
    occ.sort(key=lambda o: o.get("datetime", ""))
    return occ


# --- decor : des dates calculees, jamais ecrites en dur ---------------------
AUJ = datetime.now()


def prochain(jour_js, jours_min=1):
    """La prochaine date tombant un `jour_js` (convention JS, dim = 0)."""
    d = AUJ.date() + timedelta(days=jours_min)
    while ((d.weekday() + 1) % 7) != jour_js:
        d += timedelta(days=1)
    return d.isoformat()


def hebdo(cid, jour_js, heure="18:30", nom="Silent", lieu="Neuchatel"):
    return {"id": cid, "name": nom, "weekday": jour_js, "date": "",
            "time": heure, "locationName": lieu}


def unique(cid, date, heure="14:30", nom="Silent", lieu="Neuchatel"):
    return {"id": cid, "name": nom, "weekday": None, "date": date,
            "time": heure, "locationName": lieu}


LUNDI, MERCREDI, SAMEDI = 1, 3, 6


def cas():
    # --- A. une seule recurrence ------------------------------------------
    a = agenda_de_loffre([hebdo("a", LUNDI)], jours=21)
    verifier("A. 1 recurrence -> des occurrences, toutes un lundi",
             len(a) >= 2 and all(o["datetime"][11:16] == "18:30" for o in a)
             and all(datetime.fromisoformat(o["datetime"]).weekday() == 0 for o in a),
             [o["datetime"] for o in a][:4])

    # --- B. deux recurrences ----------------------------------------------
    b = agenda_de_loffre([hebdo("a", LUNDI), hebdo("b", MERCREDI, nom="Silent B")], jours=21)
    _jours = {datetime.fromisoformat(o["datetime"]).weekday() for o in b}
    verifier("B. 2 recurrences -> les DEUX jours sont proposes", _jours == {0, 2}, _jours)
    verifier("B2. l'ordre est chronologique",
             [o["datetime"] for o in b] == sorted(o["datetime"] for o in b))

    # --- C. une date unique -----------------------------------------------
    d_sam = prochain(SAMEDI, 3)
    c = agenda_de_loffre([unique("c", d_sam)], jours=60)
    verifier("C. 1 date unique -> UNE seule occurrence, a cette date",
             len(c) == 1 and c[0]["date"] == d_sam, [o["date"] for o in c])
    verifier("C2. elle est marquee comme date fixe (le front l'affiche autrement)",
             c[0].get("is_fixed_date") is True)

    # --- D. LE CAS DU PROPRIETAIRE : 2 recurrences + 1 date unique --------
    offre = [hebdo("a", LUNDI, "18:30", "Silent lundi"),
             hebdo("b", MERCREDI, "18:30", "Silent mercredi"),
             unique("c", d_sam, "14:30", "Silent samedi")]
    d = agenda_de_loffre(offre, jours=60)
    _uniques = [o for o in d if o.get("is_fixed_date")]
    _recur = [o for o in d if not o.get("is_fixed_date")]
    verifier("D. 2 recurrences + 1 date unique COHABITENT dans la meme offre",
             len(_uniques) == 1 and len(_recur) >= 4,
             "uniques=%d recurrentes=%d" % (len(_uniques), len(_recur)))
    verifier("D2. la date unique n'apparait QU'UNE fois",
             len([o for o in d if o["date"] == d_sam and o["time"] == "14:30"]) == 1)
    verifier("D3. chaque bloc garde SON type — aucun n'est converti",
             {o["course_id"] for o in _uniques} == {"c"}
             and {o["course_id"] for o in _recur} == {"a", "b"})
    verifier("D4. les 3 blocs sont tous representes",
             {o["course_id"] for o in d} == {"a", "b", "c"})

    # --- E. 1 recurrence + PLUSIEURS dates uniques ------------------------
    d1, d2 = prochain(SAMEDI, 3), prochain(SAMEDI, 10)
    e = agenda_de_loffre([hebdo("a", LUNDI),
                          unique("c", d1, nom="Expo 1"),
                          unique("d", d2, nom="Expo 2")], jours=60)
    verifier("E. 1 recurrence + 2 dates uniques -> les deux uniques sont la",
             {o["date"] for o in e if o.get("is_fixed_date")} == {d1, d2},
             {o["date"] for o in e if o.get("is_fixed_date")})

    # --- F. modifier une date unique --------------------------------------
    avant = agenda_de_loffre([unique("c", d1)], jours=60)
    apres = agenda_de_loffre([unique("c", d2)], jours=60)
    verifier("F. modifier la date d'un bloc unique deplace l'occurrence, sans en creer",
             len(avant) == 1 and len(apres) == 1 and avant[0]["date"] != apres[0]["date"])

    # --- G. date unique PASSEE --------------------------------------------
    vieille = (AUJ - timedelta(days=30)).date().isoformat()
    g = agenda_de_loffre([hebdo("a", LUNDI), unique("c", vieille)], jours=60)
    verifier("G. une date unique passee ne propose plus rien",
             not any(o.get("is_fixed_date") for o in g),
             [o["date"] for o in g if o.get("is_fixed_date")])
    verifier("G2. mais elle ne fait pas disparaitre les recurrences de l'offre",
             len(g) >= 2)

    # --- H. supprimer UN horaire ------------------------------------------
    h = agenda_de_loffre([offre[0], offre[2]], jours=60)
    verifier("H. retirer le bloc mercredi ne touche ni au lundi ni a la date unique",
             {o["course_id"] for o in h} == {"a", "c"}, {o["course_id"] for o in h})

    # --- I / J. sauvegarde sans modification, plusieurs fois ---------------
    j1 = agenda_de_loffre(offre, jours=60)
    j2 = agenda_de_loffre([dict(c) for c in offre], jours=60)
    j3 = agenda_de_loffre([dict(c) for c in offre], jours=60)
    verifier("I. reenregistrer sans rien changer rend EXACTEMENT le meme agenda",
             [o["datetime"] for o in j1] == [o["datetime"] for o in j2])
    verifier("J. trois passages -> aucune duplication",
             len(j1) == len(j2) == len(j3)
             and len({(o["course_id"], o["datetime"]) for o in j3}) == len(j3))

    # --- K. collision recurrent / unique ----------------------------------
    # Un samedi recurrent 14:30 ET une date unique le meme samedi 14:30, meme
    # nom, meme lieu : le visiteur ne doit voir QU'UNE ligne.
    collision = prochain(SAMEDI, 1)
    k = agenda_de_loffre([hebdo("a", SAMEDI, "14:30", "Silent", "Neuchatel"),
                          unique("c", collision, "14:30", "Silent", "Neuchatel")], jours=60)
    _ce_jour = [o for o in k if o["date"] == collision and o["time"] == "14:30"]
    verifier("K. collision exacte (meme instant, meme nom, meme lieu) -> UNE seule ligne",
             len(_ce_jour) == 1, _ce_jour)
    verifier("K2. les autres samedis recurrents restent proposes",
             len([o for o in k if o["date"] != collision]) >= 1)

    # --- K3. deux VRAIS cours au meme instant restent DEUX lignes ---------
    k3 = agenda_de_loffre([hebdo("a", SAMEDI, "14:30", "Silent", "Neuchatel"),
                           unique("c", collision, "14:30", "Danse", "Lausanne")], jours=60)
    verifier("K3. deux seances reellement differentes au meme instant restent deux lignes",
             len([o for o in k3 if o["date"] == collision]) == 2)


def structure():
    """Ce que le code du serveur doit continuer a dire de lui-meme."""
    nu = extraire("_v184_next_occurrences")
    verifier("S1. le type est decide par `date`, jamais par l'absence de weekday",
             '_fixed_date = course.get("date")' in nu and "_fixed_date.strip()" in nu)
    verifier("S2. un cours ponctuel rend AU PLUS une occurrence",
             nu.count("return [{") == 1)
    verifier("S3. le format recurrent (weekday) est intact",
             "py_weekday = (js_weekday - 1) % 7" in nu)

    espace = extraire("get_subscriber_space")
    verifier("S4. la deduplication visiteur V250 est toujours en place, "
             "et sa cle reste (instant, nom, lieu)",
             'k = (o.get("datetime"), _norm(o.get("name")), _norm(o.get("locationName")))'
             in espace)

    # AUCUNE MIGRATION : ce lot ne touche pas le serveur. On le PROUVE.
    import subprocess
    _diff = subprocess.check_output(
        ["git", "diff", "--name-only", "HEAD"], cwd=RACINE).decode().split()
    verifier("S5. ce lot ne modifie AUCUN fichier du serveur",
             not any(f.startswith("api/") for f in _diff),
             "modifies : %s" % [f for f in _diff if f.startswith("api/")])


def main():
    cas()
    structure()
    print("=" * 78)
    for nom, ok, detail in RESULTATS:
        print("  %-6s %s" % ("OK" if ok else "ECHEC", nom))
        if not ok and detail != "":
            print("         -> %s" % (detail,))
    _ok = sum(1 for _n, o, _d in RESULTATS if o)
    print("-" * 78)
    print("%d / %d verifications" % (_ok, len(RESULTATS)))
    print("Aucune base, aucun reseau, aucune ecriture.")
    return 0 if _ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())
