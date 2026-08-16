# -*- coding: utf-8 -*-
"""V441 — le correctif de `launch_campaign` (exclusion du numéro business).

Le bloc fautif est EXTRAIT du fichier réel (version production `706fd17` d'un
côté, version corrigée de l'autre) puis exécuté tel quel. On ne réécrit rien :
le test prouve que l'ancien texte lève, et que le nouveau ne lève plus.

Aucun réseau, aucune base, aucun WhatsApp, aucune campagne.
Lancement :  python3 tests/test_v441_campagne_skipped.py
"""
import ast, io, os, subprocess, sys, textwrap

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHEMIN = os.path.join("api", "server.py")

RESULTATS = []
def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def bloc_exclusion(source):
    """Extrait, dans `launch_campaign`, le corps du `if normalized_contact ==
    business_phone_number:` — c'est-à-dire les lignes qui se sont exécutées le
    15/08/2026 à 10:02:22 quand la campagne LAFF est morte."""
    arbre = ast.parse(source)
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "launch_campaign":
            for c in ast.walk(n):
                if (isinstance(c, ast.If) and isinstance(c.test, ast.Compare)
                        and "business_phone_number" in ast.unparse(c.test)
                        and "normalized_contact" in ast.unparse(c.test)):
                    return "\n".join(ast.unparse(x) for x in c.body)
    raise AssertionError("bloc d'exclusion introuvable")


def executer(bloc, results):
    """Rejoue le bloc dans les conditions EXACTES du 15/08 : `results` est la
    liste initialisée en début de `launch_campaign`, et on arrive ici parce qu'un
    destinataire porte le numéro business."""
    bac = {
        "results": results, "skipped_count": 0,
        "contact_name": "Info Afroboost", "contact_phone": "+41767639928",
        "logger": type("l", (), {"warning": staticmethod(lambda *a, **k: None)}),
    }
    # `continue` est illégal hors boucle : on enveloppe dans une boucle d'un tour,
    # ce qui reproduit fidèlement le contexte (`for contact in contacts:`).
    code = "for _ in range(1):\n" + textwrap.indent(bloc, "    ")
    exec(compile(code, "<bloc-exclusion>", "exec"), bac)
    return bac


def source_production():
    return subprocess.check_output(
        ["git", "show", "706fd17:%s" % CHEMIN], cwd=RACINE).decode("utf-8")


def main():
    # --- 1. L'ANCIEN code (celui qui tourne en production) DOIT lever.
    ancien = bloc_exclusion(source_production())
    verifier("A1. le bloc de prod contient bien results[\"skipped\"]",
             'results[\'skipped\']' in ancien or 'results["skipped"]' in ancien, ancien)
    try:
        executer(ancien, [])
        verifier("A2. prod 706fd17 : le bloc leve AttributeError", False,
                 "aucune exception — le bug aurait disparu tout seul ?")
    except AttributeError as e:
        verifier("A2. prod 706fd17 : le bloc leve AttributeError",
                 "'list' object has no attribute 'get'" in str(e), str(e))
        verifier("A3. le message est EXACTEMENT celui stocke en base le 15/08",
                 str(e) == "'list' object has no attribute 'get'", str(e))

    # --- 2. Le NOUVEAU code ne doit plus lever, et doit compter l'exclusion.
    nouveau = bloc_exclusion(io.open(os.path.join(RACINE, CHEMIN), encoding="utf-8").read())
    try:
        bac = executer(nouveau, [])
        verifier("B1. corrige : aucune exception", True)
        verifier("B2. corrige : l'exclusion est comptee", bac["skipped_count"] == 1,
                 "skipped_count=%r" % bac["skipped_count"])
        verifier("B3. corrige : `results` reste une LISTE intacte",
                 bac["results"] == [] and isinstance(bac["results"], list), repr(bac["results"]))
    except Exception as e:
        verifier("B1. corrige : aucune exception", False, "%s: %s" % (type(e).__name__, e))

    # --- 3. Le comportement metier de V165 est PRESERVE : on saute le contact.
    verifier("C1. le contact business est toujours ignore (continue present)",
             "continue" in nouveau, nouveau)
    verifier("C2. l'avertissement en journal est conserve",
             "logger.warning" in nouveau, nouveau)

    # --- 4. Une campagne SANS le numero business n'est pas affectee.
    #     (le bloc n'est simplement jamais atteint : rien a executer)
    verifier("D1. correctif limite au seul chemin d'exclusion",
             nouveau.count("skipped_count") == 1, nouveau)

    ok = sum(1 for _, r, _ in RESULTATS if r)
    print("=" * 72)
    for nom, r, detail in RESULTATS:
        print(("  OK   " if r else "  ECHEC") + "  " + nom + (("   -> " + detail) if not r else ""))
    print("=" * 72)
    print("%d/%d tests passes" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())
