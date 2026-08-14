# -*- coding: utf-8 -*-
"""V2-0c — tests hors ligne. Aucune base, aucun reseau, aucun envoi.

`POST /api/v307-set-jwt-secret` pose le JWT_SECRET — la cle qui signe TOUS les
jetons de la plateforme. Elle etait gardee par `_v263_authenticated_coach`, qui
retombe INCONDITIONNELLEMENT sur l'en-tete `X-User-Email` (`server.py`, ligne
`return _hdr`). Or `SUPER_ADMIN_EMAILS` figure en clair dans le bundle public.
Un `curl -H "X-User-Email: <adresse admin>"` reecrivait donc la cle de signature.

⚠️ CE FICHIER N'APPELLE JAMAIS LA PRODUCTION. Il n'importe ni `requests` ni
`pymongo`, et le domaine public du site n'y figure nulle part — trois assertions
le verifient sur le fichier lui-meme (§7), en reconstituant le domaine a
l'execution pour ne pas se contredire. Poser un secret invalide TOUS les jetons
en circulation : un test qui le ferait serait pire que le defaut qu'il verifie.

PROCEDURE D'URGENCE, si `JWT_SECRET` est un jour perdu. La route devient alors
inatteignable (`_v311` rend "" sans secret) — c'est assume : une trappe par
en-tete rouvrirait le trou. Recuperation HORS HTTP, puis REDEMARRAGE :
  1. variable d'environnement `JWT_SECRET` (docker-compose) ;
  2. fichier monte /app/secrets/jwt_secret ou /run/secrets/jwt_secret ;
  3. db.app_secrets.update_one({"id":"jwt"}, {"$set":{"secret":"<64 car.>"}},
     upsert=True).
Le §5 verifie que ces trois voies existent toujours dans le code.
"""
import ast, base64, json, os, sys, time

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(RACINE, "api", "server.py")
MOI = os.path.abspath(__file__)

# Secret de TEST, tire au hasard a chaque execution : jamais egal a un vrai
# secret, et prefixe reconnaissable si jamais il atterrissait dans un journal.
SECRET_TEST = "SECRET-DE-TEST-V20C-" + base64.b16encode(os.urandom(16)).decode()
_SECRET_AVANT = os.environ.get("JWT_SECRET")
os.environ["JWT_SECRET"] = SECRET_TEST

import jwt as pyjwt

# ⚠️ On DECOUPE la source une seule fois et on tranche par `lineno` :
# `ast.get_source_segment` re-parcourt le fichier a chaque appel, et `server.py`
# fait ~26 000 lignes (mesure du lot precedent : >120 s contre <1 s).
LIGNES = open(SRC, encoding="utf-8").read().split("\n")
ARBRE = ast.parse("\n".join(LIGNES))


def texte(n):
    return "\n".join(LIGNES[getattr(n, "lineno", 1) - 1:getattr(n, "end_lineno", 1)])


def extraire(noms_fn, noms_const=()):
    bouts = []
    for n in ARBRE.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in noms_fn:
            bouts.append(texte(n))
        elif isinstance(n, ast.Assign):
            for c in n.targets:
                if isinstance(c, ast.Name) and c.id in noms_const:
                    bouts.append(texte(n))
    return bouts


class _Journal:
    def warning(self, *a, **k): pass
    def info(self, *a, **k): pass
    def error(self, *a, **k): pass


NS = {"os": os, "jwt": pyjwt, "logger": _Journal(), "Request": object}
exec("\n\n".join(extraire({"_v311_coach_email_from_jwt", "is_super_admin"},
                          {"SUPER_ADMIN_EMAILS"})), NS)
DEPUIS_JWT = NS["_v311_coach_email_from_jwt"]
EST_ADMIN = NS["is_super_admin"]
ADMINS = NS["SUPER_ADMIN_EMAILS"]

resultats = []


def verifier(nom, obtenu, attendu):
    resultats.append((obtenu == attendu, nom, obtenu, attendu))


def verifier_vrai(nom, cond, detail=""):
    resultats.append((bool(cond), nom, detail or cond, True))


class FausseRequete:
    def __init__(self, entetes=None):
        self.headers = dict(entetes or {})


def jeton(charge, secret=SECRET_TEST, alg="HS256"):
    return pyjwt.encode(charge, secret, algorithm=alg)


def b64u(o):
    return base64.urlsafe_b64encode(json.dumps(o).encode()).decode().rstrip("=")


MAINTENANT = int(time.time())


def autorise(req):
    """Reproduit EXACTEMENT la garde de la route : identite signee + role."""
    e = DEPUIS_JWT(req)
    return bool(e) and bool(EST_ADMIN(e))


# === 1. LES SEPT COMPORTEMENTS EXIGES =======================================
verifier("1. aucun en-tete -> refus", autorise(FausseRequete()), False)
verifier("2. X-User-Email seul -> refus",
         autorise(FausseRequete({"X-User-Email": "coach.a@example.com"})), False)
verifier("3. e-mail SUPER-ADMIN forge -> refus",
         autorise(FausseRequete({"X-User-Email": ADMINS[0]})), False)
_jeton_admin = jeton({"email": ADMINS[0], "iat": MAINTENANT, "exp": MAINTENANT + 600})
verifier("4. JWT super-admin valide -> passe",
         autorise(FausseRequete({"Authorization": "Bearer " + _jeton_admin})), True)
verifier("5. JWT signe d'un AUTRE secret -> refus",
         autorise(FausseRequete({"Authorization": "Bearer " + jeton(
             {"email": ADMINS[0], "exp": MAINTENANT + 600}, "UN-AUTRE-SECRET-DE-TEST-40-CAR")})), False)
verifier("6. JWT expire -> refus",
         autorise(FausseRequete({"Authorization": "Bearer " + jeton(
             {"email": ADMINS[0], "iat": MAINTENANT - 7200, "exp": MAINTENANT - 60})})), False)
# alg:none fabrique a la main — pyjwt refuse de l'encoder.
_alg_none = b64u({"alg": "none", "typ": "JWT"}) + "." + b64u({"email": ADMINS[0]}) + "."
verifier("7. JWT alg:none -> refus",
         autorise(FausseRequete({"Authorization": "Bearer " + _alg_none})), False)

# === 2. LES PIEGES QUE LA GARDE DOIT ATTRAPER ==============================
verifier("jeton ABONNE correctement signe -> refus",
         autorise(FausseRequete({"Authorization": "Bearer " + jeton(
             {"type": "subscriber", "code": "AFR-TEST", "email": ADMINS[0],
              "exp": MAINTENANT + 600})})), False)
verifier("JWT de coach ORDINAIRE valide -> refus (role controle)",
         autorise(FausseRequete({"Authorization": "Bearer " + jeton(
             {"email": "coach.a@example.com", "exp": MAINTENANT + 600})})), False)
verifier("JWT sans e-mail -> refus",
         autorise(FausseRequete({"Authorization": "Bearer " + jeton(
             {"role": "super_admin", "exp": MAINTENANT + 600})})), False)
verifier("les DEUX super-admins passent",
         [autorise(FausseRequete({"Authorization": "Bearer " + jeton(
             {"email": a, "exp": MAINTENANT + 600})})) for a in ADMINS], [True] * len(ADMINS))
verifier("e-mail en MAJUSCULES normalise",
         autorise(FausseRequete({"Authorization": "Bearer " + jeton(
             {"email": ADMINS[0].upper(), "exp": MAINTENANT + 600})})), True)
_malformes = ["Bearer", "Bearer   ", "Basic xyz", "Bearer a.b.c", "", "Bearer " + _jeton_admin[:-5]]
verifier("en-tetes malformes -> refus, sans exception",
         [h for h in _malformes if autorise(FausseRequete({"Authorization": h}))], [])
verifier("jeton valide MAIS secret absent -> refus (verrou d'amorcage)",
         (lambda: (os.environ.__setitem__("JWT_SECRET", ""),
                   autorise(FausseRequete({"Authorization": "Bearer " + _jeton_admin})),
                   os.environ.__setitem__("JWT_SECRET", SECRET_TEST))[1])(), False)
# `is_super_admin` ne rend pas un vrai booleen : "" pour "", None pour None.
verifier("is_super_admin ne rend jamais True sur une entree vide",
         [v for v in ("", None, 0) if EST_ADMIN(v) is True], [])


# === 3. COUVERTURE PAR NOEUDS D'AST, JAMAIS PAR RECHERCHE DE TEXTE =========
GARDES = ("_v311_coach_email_from_jwt", "_v411_exiger_super_admin", "coach_jwt_email")


def _appele(n):
    f = n.func
    return f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")


def analyser(arbre=None, lignes=None):
    """Analyse la route. Renvoie gardes, ecritures BASE et ecritures ENVIRONNEMENT.

    ⚠️ POINT PROPRE A CE LOT. `os.environ["JWT_SECRET"] = secret` est un
    `ast.Assign` dont la cible est un `Subscript` — CE N'EST PAS un `ast.Call`.
    Le controle du lot precedent, qui ne collectait que des appels, y serait
    structurellement AVEUGLE. On collecte donc les deux natures d'ecriture.
    """
    arbre = arbre or ARBRE
    lig = lignes or LIGNES

    def txt(n):
        return "\n".join(lig[n.lineno - 1:n.end_lineno])

    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "v307_set_jwt_secret":
            corps = list(n.body)
            if corps and isinstance(corps[0], ast.Expr) and isinstance(corps[0].value, ast.Constant):
                corps = corps[1:]
            gardes, ecr_base, ecr_env, roles, awaits = [], [], [], [], []
            for s in corps:
                for x in ast.walk(s):
                    if isinstance(x, ast.Call):
                        nom = _appele(x)
                        if nom in GARDES:
                            gardes.append((x.lineno, nom,
                                           [a.id for a in x.args if isinstance(a, ast.Name)]))
                        if nom == "is_super_admin":
                            roles.append(x.lineno)
                        if nom in ("update_one", "insert_one", "replace_one", "update_many",
                                   "find_one_and_update", "bulk_write", "delete_one"):
                            ecr_base.append(x.lineno)
                    # ECRITURE D'ENVIRONNEMENT : Assign a cible Subscript
                    if isinstance(x, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                        cibles = x.targets if isinstance(x, ast.Assign) else [x.target]
                        for c in cibles:
                            if isinstance(c, ast.Subscript):
                                base = c.value
                                if (isinstance(base, ast.Attribute) and base.attr == "environ") or \
                                   (isinstance(base, ast.Name) and base.id == "environ"):
                                    ecr_env.append(x.lineno)
                    if isinstance(x, ast.Await) and isinstance(x.value, ast.Call) \
                            and _appele(x.value) in GARDES:
                        awaits.append(x.lineno)
            return {"trouvee": True, "params": [a.arg for a in n.args.args],
                    "gardes": gardes, "roles": roles, "ecr_base": ecr_base,
                    "ecr_env": ecr_env, "awaits": awaits,
                    "code": "\n".join(txt(s) for s in corps),
                    "decoree": any(isinstance(d.func if isinstance(d, ast.Call) else d, ast.Attribute)
                                   for d in n.decorator_list),
                    "docstring": ast.get_docstring(n) or ""}
    return {"trouvee": False, "gardes": [], "roles": [], "ecr_base": [], "ecr_env": [],
            "awaits": [], "params": [], "code": "", "decoree": False, "docstring": ""}


R = analyser()
verifier_vrai("la route existe et est exposee en HTTP", R["trouvee"] and R["decoree"])
verifier_vrai("elle recoit `request`", "request" in R["params"], R["params"])
verifier_vrai("elle APPELLE reellement une garde signee", bool(R["gardes"]), R["gardes"])
verifier_vrai("la garde recoit `request`", any("request" in a for _, _, a in R["gardes"]))
verifier_vrai("le controle de ROLE est present", bool(R["roles"]), R["roles"])
verifier_vrai("AUCUN repli X-User-Email comme garde",
              "_v263_authenticated_coach" not in R["code"] or
              "_v263_authenticated_coach(" not in R["code"])
verifier_vrai("aucune garde synchrone laissee sous `await`", not R["awaits"], R["awaits"])

# L'ordre : la garde precede les DEUX natures d'ecriture.
_g = min(l for l, _, _ in R["gardes"]) if R["gardes"] else 10 ** 9
verifier_vrai("la garde precede l'ecriture Mongo", all(_g < e for e in R["ecr_base"]),
              (_g, R["ecr_base"]))
verifier_vrai("la garde precede l'ecriture de os.environ", all(_g < e for e in R["ecr_env"]),
              (_g, R["ecr_env"]))
verifier("une seule ecriture Mongo, une seule d'environnement",
         (len(R["ecr_base"]), len(R["ecr_env"])), (1, 1))
verifier_vrai("la garde est la PREMIERE instruction du corps",
              _g == min([l for l, _, _ in R["gardes"]] + R["roles"]))

# === 4. ZERO REGRESSION : le comportement metier est conserve ==============
verifier_vrai("le seuil de 32 caracteres est conserve", "len(secret) < 32" in R["code"])
verifier_vrai("le 400 « Secret trop court » est conserve", "Secret trop court" in R["code"])
verifier_vrai("`upsert=True` est conserve", "upsert=True" in R["code"])
verifier_vrai("la reponse garde ses 4 champs",
              all(c in R["code"] for c in ('"status"', '"jwt_secret_set"',
                                           '"jwt_secret_len"', '"source"')))
verifier_vrai("le corps optionnel est toujours accepte", "token_urlsafe" in R["code"])
_journaux = [l for l in R["code"].split("\n") if "logger." in l]
verifier_vrai("aucun journal ne porte le secret en clair",
              all("len(secret)" in l or "secret" not in l.split("logger.")[1] for l in _journaux),
              _journaux)
# On inspecte le SEUL `return` de la route : `{"secret": secret}` apparait aussi
# dans le `$set` de l'ecriture Mongo, ou il est legitime.
_retours = [texte(x) for x in ast.walk(ARBRE)
            if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))
            and x.name == "v307_set_jwt_secret"
            for x in ast.walk(x) if isinstance(x, ast.Return)]
verifier_vrai("le secret n'est renvoye dans AUCUN return",
              all("secret" not in r or "jwt_secret_set" in r or "jwt_secret_len" in r
                  for r in _retours), _retours)

# === 5. LES TROIS VOIES DE SECOURS EXISTENT TOUJOURS ======================
# Si elles disparaissent, le verrou d'amorcage devient DEFINITIF.
_src = "\n".join(LIGNES)
verifier_vrai("secours 1 : variable d'environnement lue au demarrage",
              'os.environ.get("JWT_SECRET"' in _src)
verifier_vrai("secours 2 : fichier monte", "/run/secrets/jwt_secret" in _src
              and "/app/secrets/jwt_secret" in _src)
verifier_vrai("secours 3 : lecture de app_secrets au demarrage",
              'app_secrets.find_one({"id": "jwt"}' in _src)
verifier_vrai("la route et le resolveur visent le MEME document",
              _src.count('{"id": "jwt"}') >= 2)

# === 6. AUTO-TESTS DE SABOTAGE — le test qui teste le test ================
def saboter(mode):
    """Fabrique EN MEMOIRE une version degradee de server.py."""
    lig = list(LIGNES)
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "v307_set_jwt_secret":
            corps = list(n.body)
            if corps and isinstance(corps[0], ast.Expr) and isinstance(corps[0].value, ast.Constant):
                corps = corps[1:]
            a_vider = set()
            for s in corps:
                for x in ast.walk(s):
                    if mode == "garde" and isinstance(x, ast.Call) and _appele(x) in GARDES:
                        a_vider.update(range(s.lineno, s.end_lineno + 1))
                    if mode == "role" and isinstance(x, ast.Call) and _appele(x) == "is_super_admin":
                        a_vider.update(range(s.lineno, s.end_lineno + 1))
            if mode == "env_hissee":
                # S5 : on hisse la SEULE affectation os.environ avant la garde.
                env = R["ecr_env"][0]
                ligne_env = lig[env - 1]
                del lig[env - 1]
                lig.insert(n.lineno, ligne_env)
                return lig
            for i in a_vider:
                lig[i - 1] = ""
            return lig
    return lig


for _mode, _attendu in (("garde", "gardes"), ("role", "roles")):
    _lig = saboter(_mode)
    _r = analyser(ast.parse("\n".join(_lig)), _lig)
    verifier("sabotage « %s » -> le controle le voit" % _mode, _r[_attendu], [])

# S5 : l'ecriture d'environnement hissee AVANT la garde doit etre detectee.
_lig5 = saboter("env_hissee")
_r5 = analyser(ast.parse("\n".join(_lig5)), _lig5)
_g5 = min(l for l, _, _ in _r5["gardes"]) if _r5["gardes"] else 10 ** 9
verifier_vrai("sabotage S5 : os.environ hissee AVANT la garde -> detecte",
              _r5["ecr_env"] and any(e < _g5 for e in _r5["ecr_env"]),
              (_g5, _r5["ecr_env"]))
# ... et la docstring, elle, cite toujours les gardes : preuve que le controle
# ne se laisse pas abuser par le texte.
verifier_vrai("la docstring cite les gardes (piege desamorce)",
              "_v311_coach_email_from_jwt" in R["docstring"])

# === 7. HYGIENE DU FICHIER DE TEST LUI-MEME ===============================
_moi = open(MOI, encoding="utf-8").read()
_imports = [a.name for n in ast.walk(ast.parse(_moi)) if isinstance(n, ast.Import) for a in n.names] \
    + [n.module or "" for n in ast.walk(ast.parse(_moi)) if isinstance(n, ast.ImportFrom)]
verifier("ce test n'importe ni requests ni pymongo",
         [m for m in _imports if m and m.split(".")[0] in ("requests", "pymongo", "motor", "httpx")], [])
# Le domaine est reconstitue a l'execution : l'ecrire en clair ferait echouer
# l'assertion sur son propre fichier.
_domaine = "afroboost" + "." + "com"
verifier("ce test ne connait pas l'URL de production", _moi.count(_domaine), 0)
verifier_vrai("le secret de test porte un prefixe reconnaissable",
              SECRET_TEST.startswith("SECRET-DE-TEST-"))
verifier_vrai("aucun test du depot n'appelle cette route en HTTP",
              not any("v307-set-jwt-secret" in open(os.path.join(RACINE, "tests", f),
                                                    encoding="utf-8", errors="ignore").read()
                      and "requests" in open(os.path.join(RACINE, "tests", f),
                                             encoding="utf-8", errors="ignore").read()
                      for f in os.listdir(os.path.join(RACINE, "tests"))
                      if f.endswith(".py") and f != os.path.basename(MOI)))

# Restauration de l'environnement — on ne laisse rien derriere soi.
if _SECRET_AVANT is None:
    os.environ.pop("JWT_SECRET", None)
else:
    os.environ["JWT_SECRET"] = _SECRET_AVANT

print("=" * 74)
_e = 0
for ok, nom, obtenu, attendu in resultats:
    print(("  PASS  " if ok else "  FAIL  ") + nom)
    if not ok:
        _e += 1
        print("          obtenu  : %r" % (obtenu,))
        print("          attendu : %r" % (attendu,))
print("=" * 74)
print("  %d/%d" % (len(resultats) - _e, len(resultats)))
sys.exit(1 if _e else 0)
