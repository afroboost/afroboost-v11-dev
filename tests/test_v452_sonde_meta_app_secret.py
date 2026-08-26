# -*- coding: utf-8 -*-
"""V452 — SONDE : le conteneur reçoit-il META_APP_SECRET ? Un BOOLEEN, rien d'autre.

POURQUOI CE LOT EXISTE SEUL. Le lot suivant (3b) verifiera la signature
`X-Hub-Signature-256` des webhooks Meta. Si le secret n'atteint pas le conteneur,
cette verification refuserait TOUT le trafic entrant legitime : plus aucun message
recu, plus aucun STOP traite, bot muet. Or le projet a deja vecu exactement cela :
`JWT_SECRET` avait ete pose dans Coolify SANS jamais parvenir au conteneur — d'ou
le repli V307 par MongoDB `app_secrets`. Poser une variable ne prouve rien.

On deploie donc d'abord la SEULE sonde, sans aucun changement de comportement, et
on n'ecrit la verification qu'apres l'avoir vue repondre `true` en production.

CE QUI EST GARANTI ICI :
  - la reponse ne contient QUE des booleens — jamais une valeur, jamais une
    longueur, jamais un prefixe, jamais un nom d'hote ;
  - les booleens deja publies sont conserves a l'identique ;
  - aucun comportement du webhook, des campagnes ou de STOP n'est touche.

Aucun reseau. Aucune base. Aucun envoi. Aucune ecriture.

Lancement :  python3 tests/test_v452_sonde_meta_app_secret.py
"""
import ast
import asyncio
import io
import os
import subprocess
import sys
import warnings

warnings.filterwarnings("ignore")

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVEUR = os.path.join(RACINE, "api", "server.py")
SOURCE = io.open(SERVEUR, encoding="utf-8").read()
ARBRE = ast.parse(SOURCE)
LIGNES = SOURCE.splitlines(True)

VARIABLE = "META_APP_SECRET"
CHAMP = "meta_app_secret_set"
# Valeur fictive du bac a sable. Elle ne doit apparaitre dans AUCUNE reponse.
FAUX_SECRET = "SECRET-META-FICTIF-DU-TEST-V452-NE-DOIT-JAMAIS-SORTIR"

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def noeud(nom):
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return n
    raise AssertionError("fonction introuvable : %s" % nom)


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


# ----------------------------------------------------------------------------
# Execution reelle du handler, dans un bac a sable
# ----------------------------------------------------------------------------
class FausseReponseJSON:
    def __init__(self, content=None, **kw):
        self.content = content


def executer_handler(env):
    """Execute `debug_config` avec l'environnement donne et rend le dict publie."""
    anciens = {}
    for cle in (VARIABLE, "STRIPE_SECRET_KEY", "OPENAI_API_KEY", "RESEND_API_KEY", "JWT_SECRET"):
        anciens[cle] = os.environ.get(cle)
        if cle in env:
            os.environ[cle] = env[cle]
        else:
            os.environ.pop(cle, None)
    try:
        bac = {"os": os, "JSONResponse": FausseReponseJSON,
               "fastapi_app": type("a", (), {"get": staticmethod(lambda *a, **k: (lambda f: f))})}
        exec(compile(extraire("debug_config"), "<v452-extrait>", "exec"), bac)
        rep = asyncio.new_event_loop().run_until_complete(bac["debug_config"]())
        return rep.content
    finally:
        for cle, val in anciens.items():
            if val is None:
                os.environ.pop(cle, None)
            else:
                os.environ[cle] = val


def scenarios():
    # --- secret PRESENT ---
    r = executer_handler({VARIABLE: FAUX_SECRET, "JWT_SECRET": "x", "STRIPE_SECRET_KEY": "y",
                          "OPENAI_API_KEY": "z", "RESEND_API_KEY": "w"})
    verifier("1. le champ %s est publie" % CHAMP, CHAMP in (r or {}), str(sorted(r or {})))
    verifier("2. secret pose -> true", (r or {}).get(CHAMP) is True, repr((r or {}).get(CHAMP)))
    verifier("3. c'est un BOOLEEN, pas une chaine",
             isinstance((r or {}).get(CHAMP), bool), type((r or {}).get(CHAMP)).__name__)

    # --- FUITE : la valeur ne doit apparaitre nulle part ---
    texte = repr(r)
    verifier("4. la valeur du secret n'apparait PAS dans la reponse",
             FAUX_SECRET not in texte, "FUITE")
    for morceau in (FAUX_SECRET[:8], FAUX_SECRET[:4], FAUX_SECRET[-8:]):
        verifier("4. aucun MORCEAU du secret (%s...) n'apparait" % morceau[:4],
                 morceau not in texte, "FUITE")
    verifier("5. aucune LONGUEUR de secret n'est publiee",
             not any("length" in str(k).lower() or "len" == str(k).lower() for k in (r or {})),
             str(sorted(r or {})))
    verifier("6. toutes les valeurs publiees sont des booleens",
             all(isinstance(v, bool) for v in (r or {}).values()),
             str({k: type(v).__name__ for k, v in (r or {}).items()}))

    # --- secret ABSENT ---
    r2 = executer_handler({"JWT_SECRET": "x", "STRIPE_SECRET_KEY": "y",
                           "OPENAI_API_KEY": "z", "RESEND_API_KEY": "w"})
    verifier("7. secret absent -> false", (r2 or {}).get(CHAMP) is False, repr((r2 or {}).get(CHAMP)))
    verifier("8. secret VIDE -> false",
             (executer_handler({VARIABLE: ""}) or {}).get(CHAMP) is False, "")

    # --- les booleens historiques sont conserves ---
    for ancien in ("stripe_key_set", "openai_key_set", "resend_key_set", "jwt_secret_set"):
        verifier("9. le booleen historique %s est conserve" % ancien, ancien in (r or {}),
                 str(sorted(r or {})))
    verifier("10. la sonde n'ajoute QU'UN champ",
             len(r or {}) == 5, "%d champs : %s" % (len(r or {}), sorted(r or {})))


def tests_structurels():
    nu = code_nu("debug_config")
    verifier("S1. la sonde lit bien la variable d'environnement %s" % VARIABLE,
             VARIABLE in nu, nu[:200])
    verifier("S2. la valeur est enveloppee dans bool() — jamais rendue telle quelle",
             "bool(os.environ.get('%s'))" % VARIABLE in nu
             or 'bool(os.environ.get("%s"))' % VARIABLE in nu, nu[:300])
    verifier("S3. aucune troncature de secret (pas de [:n], pas de len())",
             "[:2" not in nu and "[:8" not in nu and "len(" not in nu, nu[:300])
    verifier("S4. la route reste publique et sans effet de bord (aucune ecriture)",
             "insert" not in nu and "update" not in nu and "delete" not in nu, nu[:200])


INTOUCHABLES = (
    "handle_meta_whatsapp_webhook",       # webhook entrant + STOP — NON TOUCHE
    "verify_meta_whatsapp_webhook",       # handshake GET Meta — NON TOUCHE
    "_v332_stop_whatsapp",                # traitement STOP entrant
    "launch_campaign",                    # moteur de campagne
    "v451_lancer_campagne_http",          # garde V451
    "test_whatsapp_template",             # gardes V450
    "test_campaign_3steps",
    "whatsapp_diagnostic",
    "whatsapp_app_info",
    "send_whatsapp_direct",
    "_send_whatsapp_meta",
    "_get_whatsapp_config",
)

_CACHE = {}


def _index(rev):
    if rev not in _CACHE:
        try:
            t = subprocess.check_output(["git", "show", "%s:api/server.py" % rev],
                                        cwd=RACINE, stderr=subprocess.DEVNULL).decode("utf-8")
            lg = t.splitlines(True)
            idx = {}
            for x in ast.walk(ast.parse(t)):
                if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    idx.setdefault(x.name, []).append("".join(lg[x.lineno - 1:x.end_lineno]))
            _CACHE[rev] = idx
        except subprocess.CalledProcessError:
            _CACHE[rev] = {}
    return _CACHE[rev]


def _index_travail():
    lg = SOURCE.splitlines(True)
    idx = {}
    for x in ast.walk(ARBRE):
        if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)):
            idx.setdefault(x.name, []).append("".join(lg[x.lineno - 1:x.end_lineno]))
    return idx


def tests_non_regression():
    tete, travail = _index("HEAD"), _index_travail()
    if not tete:
        verifier("N0. la revision HEAD est lisible", False, "git indisponible")
        return
    verifier("N0. la revision HEAD est lisible", True)
    for nom in INTOUCHABLES:
        if nom not in tete:
            continue
        verifier("11. %s INCHANGE par ce lot" % nom, tete[nom] == travail.get(nom),
                 "MODIFIE")
    diff = subprocess.check_output(["git", "diff", "--name-only", "HEAD"],
                                   cwd=RACINE).decode("utf-8").split()
    autorises = {"api/server.py", "tests/test_v452_sonde_meta_app_secret.py"}
    hors = [f for f in diff if f not in autorises]
    verifier("12. le lot ne modifie AUCUN autre fichier", hors == [], " ".join(hors))
    change = [n for n, s in travail.items() if n not in tete or tete[n] != s]
    verifier("13. dans server.py, SEUL debug_config change",
             set(change) <= {"debug_config"}, "aussi : %s" % sorted(set(change) - {"debug_config"}))


def main():
    tests_structurels()
    tests_non_regression()
    try:
        scenarios()
    except AssertionError as e:
        verifier("SCENARIOS non joues : %s" % e, False, "la sonde n'existe pas encore")
    ok = sum(1 for _, r, _ in RESULTATS if r)
    print("=" * 78)
    for nom, r, detail in RESULTATS:
        print(("  OK   " if r else "  ECHEC") + "  " + nom + (("   -> " + detail) if not r else ""))
    print("=" * 78)
    print("Secrets imprimes par cette suite : 0")
    print("Reseau : 0   Base : 0   Envois : 0   Ecritures : 0")
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())
