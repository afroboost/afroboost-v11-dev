# -*- coding: utf-8 -*-
"""STATS-1 — NON-RÉGRESSION de l'extraction du cœur de calcul.

`_calculer_cockpit` a été découpé en `_lire_sources` (les 7 lectures),
`_coeur_kpi` (le calcul pur) et `_projection_association`. L'écran coach ne
doit pas bouger d'UNE valeur : ce banc exécute, sur la même fausse base et à la
même horloge, la route TELLE QU'AU COMMIT 8baf9b13 (relue depuis git) et la
route actuelle, puis compare les deux réponses JSON en entier, pour une série
de paramètres (mois, année, semaine, perso, granularités, filtre cours, coach,
vue association avec clôture).

Discriminance : toute modification d'un chiffre du cœur (essayez de changer
`kpi["requetes"] = 7` ou un filtre de `_coeur_kpi`) fait échouer ce banc.

    python3 tests/test_stats_coeur_nonregression.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stats_fixtures as F  # noqa: E402

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


F.installer_serveur(F.Base(F.jeu_de_base()), F.ADMIN)
from fastapi import HTTPException  # noqa: E402
import api.routes.analytics_routes as NOUVEAU  # noqa: E402
F.poser_admin()
REF = F.charger_reference()
verifier("la version de référence %s est relue depuis git" % F.COMMIT_REFERENCE, REF is not None)

PARAMS = [
    dict(periode="mois", mois="2026-09"),
    dict(periode="mois", mois="2026-09", granularite="semaine"),
    dict(periode="mois", mois="2026-08", granularite="mois"),
    dict(periode="annee", mois="2026-01", granularite="mois"),
    dict(periode="semaine", mois="2026-09"),
    dict(periode="perso", du="2026-09-01", au="2026-09-30", granularite="jour"),
    dict(periode="mois", mois="2026-09", course_id="c-dim"),
    dict(periode="mois", mois="2026-09", coach_id=F.COACH),
    dict(periode="mois", mois="2026-09", vue="association"),
    dict(periode="mois", mois="2026-09", vue="association", coach_id=F.COACH),
    dict(periode="annee", mois="2026-01", vue="association"),
    dict(periode="mois", mois="2026-10", vue="association"),
    dict(periode="aujourdhui"),
]


def _appel(module, jwt, params, jeu=None):
    base = F.Base(jeu or F.jeu_de_base())
    F.installer_serveur(base, jwt)
    F.horloge_figee(module)
    try:
        r = F.run(module._calculer_cockpit(F.Req(), **params))
        return 200, json.loads(json.dumps(r, sort_keys=True, default=str)), base
    except HTTPException as e:
        return e.status_code, None, base


if REF:
    for p in PARAMS:
        for jwt in (F.ADMIN, F.COACH):
            if jwt == F.COACH and p.get("coach_id") not in (None, F.COACH):
                continue
            s_ref, r_ref, b_ref = _appel(REF["analytics_routes"], jwt, p)
            s_new, r_new, b_new = _appel(NOUVEAU, jwt, p)
            nom = "%s %s" % ("admin" if jwt == F.ADMIN else "coach", p)
            verifier("même statut — " + nom, s_ref == s_new == 200, (s_ref, s_new))
            verifier("même réponse JSON, valeur pour valeur — " + nom, r_ref == r_new,
                     [k for k in (r_ref or {}) if (r_ref or {}).get(k) != (r_new or {}).get(k)][:5])
            verifier("mêmes lectures, dans le même ordre — " + nom, b_ref.lectures == b_new.lectures,
                     (b_ref.lectures, b_new.lectures))
            verifier("aucune écriture — " + nom, not b_new.ecritures, b_new.ecritures)
    # Les refus restent identiques.
    for p, attendu in ((dict(periode="n_importe_quoi"), 400), (dict(periode="perso"), 400),
                       (dict(periode="mois", granularite="heure"), 400)):
        s_ref, _, _ = _appel(REF["analytics_routes"], F.ADMIN, p)
        s_new, _, _ = _appel(NOUVEAU, F.ADMIN, p)
        verifier("même refus %s -> %d" % (p, attendu), s_ref == s_new == attendu, (s_ref, s_new))
    s_new, _, _ = _appel(NOUVEAU, "", dict(periode="mois"))
    verifier("toujours 401 sans jeton", s_new == 401, s_new)

ok = sum(1 for _, c, _ in RESULTATS if c)
for nom, cond, detail in RESULTATS:
    print("  %s  %s%s" % ("OK  " if cond else "ECHEC", nom, ("  <- " + str(detail)) if (detail and not cond) else ""))
print("\n%d/%d" % (ok, len(RESULTATS)))
sys.exit(0 if ok == len(RESULTATS) else 1)
