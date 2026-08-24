# -*- coding: utf-8 -*-
"""P0 — L'ESPACE ABONNE NE RENDAIT AUCUNE RESERVATION.

MESURE DE PRODUCTION, 24/08/2026 :

    GET /api/subscriber/space/AFR-S4QYXD
      reservations : []
      trial        : {"is_trial": true, "state": "available"}

alors que la reservation existe, qu'elle est `validated: true` et que l'essai a
bel et bien ete consomme le jour meme.

LA CAUSE. `V310` (protection anti-injection) a pose `re.escape` sur 84 regex
Mongo. A deux endroits, la variable etait DEJA echappee :

    user_email_escaped = _re_mod.escape(user_email)        # l. 13011
    {"$regex": f"^{re.escape(user_email_escaped)}$"}       # l. 13048  <- deux fois

Un double echappement transforme `ex\\.test` en `ex\\\\\\.test` : le motif ne
cherche plus un point, il cherche un ANTISLASH suivi d'un point. Comme tout
domaine d'e-mail contient un point, la recherche ne pouvait matcher PERSONNE.

CE QUE CELA CASSAIT, ET QUI EST LE PLUS GRAVE :
  * « Mes seances » restait vide pour tout le monde ;
  * `t2_etat_essai` lit CETTE liste pour dire si l'essai est effectue. Vide, il
    repondait `available` au lieu de `done` ;
  * l'ecran de conversion LOT A est monte sous `etatEssai === "done"`. Il n'a
    donc JAMAIS pu s'afficher depuis sa mise en ligne du 19/08/2026.

Aucun reseau. Aucune base.

Lancement :  python3 tests/test_p0_espace_reservations.py
"""

import ast
import io
import os
import re
import sys

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


ESPACE = extraire("get_subscriber_space")

# --- le comportement, avant la structure ------------------------------------
ADRESSES = ["bassi@afroboost.com", "moyikad204@kolsea.com",
            "jean-luc.martin+test@sous.domaine.co.uk", "a_b@c.io"]


def motif_simple(mail):
    """Ce que le code DOIT construire : une seule couche d'echappement."""
    return "^%s$" % re.escape(mail)


def motif_double(mail):
    """Ce qu'il construisait : deux couches."""
    return "^%s$" % re.escape(re.escape(mail))


def comportement():
    for _m in ADRESSES:
        verifier("C. un seul echappement retrouve « %s »" % _m[:28],
                 re.match(motif_simple(_m), _m, re.I) is not None)
    _casses = [_m for _m in ADRESSES if re.match(motif_double(_m), _m, re.I) is None]
    verifier("C2. le DOUBLE echappement ne retrouve AUCUNE de ces adresses "
             "— c'est bien la cause, pas une coincidence",
             len(_casses) == len(ADRESSES), "retrouvees : %s" %
             [m for m in ADRESSES if m not in _casses])
    # L'injection reste refusee : c'est ce que V310 protegeait, et on n'y touche pas.
    _mechant = "a@b.c$|^.*"
    verifier("C3. l'echappement SIMPLE protege toujours de l'injection regex",
             re.match(motif_simple(_mechant), "autre@victime.com", re.I) is None)


def structure():
    _lignes_regex = [l.strip() for l in ESPACE.splitlines()
                     if "$regex" in l and "userEmail" in l]
    verifier("S1. les deux recherches par adresse existent toujours",
             len(_lignes_regex) == 2, _lignes_regex)
    verifier("S2. AUCUNE ne ré-échappe une variable déjà échappée",
             not any(re.search(r"escape\(\w*_escaped\)", l) for l in _lignes_regex),
             [l for l in _lignes_regex if re.search(r"escape\(\w*_escaped\)", l)])
    verifier("S3. ... et elles utilisent bien la variable ECHAPPEE, "
             "jamais l'adresse brute",
             all("_escaped" in l for l in _lignes_regex), _lignes_regex)
    verifier("S4. l'echappement a lieu UNE fois, en amont",
             "user_email_escaped = _re_mod.escape(user_email)" in ESPACE)
    verifier("S5. les deux recherches restent ancrees ^...$ "
             "(une adresse partielle ne doit pas matcher)",
             all(l.count("^") == 1 and "$\"" in l or "$'" in l or "}$" in l
                 for l in _lignes_regex), _lignes_regex)
    verifier("S6. `t2_etat_essai` lit toujours CETTE liste — c'est ce qui "
             "faisait tomber l'ecran de conversion",
             "t2_etat_essai(code_upper, reservations_raw" in ESPACE)


def main():
    comportement(); structure()
    print("=" * 78)
    for nom, ok, detail in RESULTATS:
        print("  %-6s %s" % ("OK" if ok else "ECHEC", nom))
        if not ok and detail != "":
            print("         -> %s" % (detail,))
    _ok = sum(1 for _n, o, _d in RESULTATS if o)
    print("-" * 78)
    print("%d / %d verifications" % (_ok, len(RESULTATS)))
    return 0 if _ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())
