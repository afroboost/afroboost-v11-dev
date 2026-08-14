# -*- coding: utf-8 -*-
"""V2-0d — tests hors ligne. Aucune base, aucun reseau, aucune inscription.

CHAINE D'ESCALADE FERMEE PAR CE LOT :
  1. POST /api/auth/register              e-mail super-admin -> compte cree
  2. POST /api/admin/activate-coach       en-tete forge      -> compte active
  3. POST /api/auth/login                 role derive du mail -> JWT SIGNE
Le jeton obtenu franchissait ensuite TOUTES les gardes de V2-0, V2-0b et V2-0c.

Et un chemin COURT, trouve pendant l'audit :
  POST /api/cinetpay/register-free        anonyme, sans `pending_validation`
                                          -> compte ACTIF en un seul appel.

⚠️ CE FICHIER NE S'INSCRIT JAMAIS ET N'ACTIVE JAMAIS RIEN. Il n'importe ni
`requests` ni `pymongo`, et ignore le domaine public — trois assertions le
verifient sur lui-meme. Creer un compte super-admin en production serait
exactement l'attaque que ce lot ferme.
"""
import ast, base64, json, os, sys, time

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_AUTH = os.path.join(RACINE, "api", "routes", "auth_routes.py")
SRC_COACH = os.path.join(RACINE, "api", "routes", "coach_routes.py")
SRC_CINET = os.path.join(RACINE, "api", "routes", "cinetpay_routes.py")
SRC_SHARED = os.path.join(RACINE, "api", "routes", "shared.py")
MOI = os.path.abspath(__file__)

SECRET_TEST = "SECRET-DE-TEST-V20D-" + base64.b16encode(os.urandom(16)).decode()
_AVANT = os.environ.get("JWT_SECRET")
os.environ["JWT_SECRET"] = SECRET_TEST

import jwt as pyjwt

resultats = []


def verifier(nom, obtenu, attendu):
    resultats.append((obtenu == attendu, nom, obtenu, attendu))


def verifier_vrai(nom, cond, detail=""):
    resultats.append((bool(cond), nom, detail or cond, True))


def lignes(chemin):
    return open(chemin, encoding="utf-8").read().split("\n")


def extraire(chemin, fonctions, constantes=()):
    lig = lignes(chemin)
    bouts = []
    for n in ast.parse("\n".join(lig)).body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in fonctions:
            bouts.append("\n".join(lig[n.lineno - 1:n.end_lineno]))
        elif isinstance(n, ast.Assign):
            for c in n.targets:
                if isinstance(c, ast.Name) and c.id in constantes:
                    bouts.append("\n".join(lig[n.lineno - 1:n.end_lineno]))
    return bouts


class _J:
    def warning(self, *a, **k): pass
    def info(self, *a, **k): pass
    def error(self, *a, **k): pass


# --- La regle d'exclusion, telle qu'elle est REELLEMENT ecrite dans le code ---
NS_AUTH = {"os": os, "logger": _J()}
exec("\n\n".join(extraire(SRC_AUTH, {"is_super_admin_email"},
                          {"SUPER_ADMIN_EMAILS", "_admin_emails_env"})), NS_AUTH)
EST_ADMIN_AUTH = NS_AUTH["is_super_admin_email"]
ADMINS = NS_AUTH["SUPER_ADMIN_EMAILS"]

NS_SH = {"os": os, "logger": _J(), "jwt": pyjwt}
exec("\n\n".join(extraire(SRC_SHARED, {"is_super_admin", "coach_jwt_email", "super_admin_signe"},
                          {"SUPER_ADMIN_EMAILS"})), NS_SH)
SIGNE = NS_SH["super_admin_signe"]


class FausseRequete:
    def __init__(self, entetes=None):
        self.headers = dict(entetes or {})


def jeton(charge, secret=SECRET_TEST):
    return pyjwt.encode(charge, secret, algorithm="HS256")


T = int(time.time())


# === A/B/C — L'INSCRIPTION ==================================================
# La regle : `is_super_admin_email(email)` apres `email.lower().strip()`.
def inscription_refusee(saisie):
    """Reproduit exactement ce que fait la route : normalisation puis regle."""
    return EST_ADMIN_AUTH(saisie.lower().strip())


verifier("A. inscription normale preservee",
         inscription_refusee("nouveau.coach@example.com"), False)
verifier("A. autre adresse ordinaire preservee",
         inscription_refusee("Jean.Dupont@Example.COM"), False)
verifier("B. inscription sous une adresse super-admin -> refusee",
         [a for a in ADMINS if not inscription_refusee(a)], [])
verifier("C. la meme en MAJUSCULES -> refusee",
         [a for a in ADMINS if not inscription_refusee(a.upper())], [])
verifier("C. la meme avec espaces parasites -> refusee",
         [a for a in ADMINS if not inscription_refusee("  " + a + "  ")], [])
verifier("C. casse melangee + espaces -> refusee",
         inscription_refusee("  CoNtAcT.ArTbOoSt@GmAiL.CoM "), True)
# Cas limites : une adresse VOISINE reste legitime — on ne bloque pas trop large.
for _voisine in ("contact.artboost+x@gmail.com", "contact-artboost@gmail.com",
                 "contact.artboost@gmail.co", "acontact.artboost@gmail.com"):
    verifier("adresse voisine « %s » reste acceptee" % _voisine[:24],
             inscription_refusee(_voisine), False)

# === D/E/F/G — L'ACTIVATION =================================================
verifier("D. activate-coach sans aucun en-tete -> refus",
         SIGNE(FausseRequete()), "")
verifier("E. activate-coach + X-User-Email super-admin FORGE -> refus",
         SIGNE(FausseRequete({"X-User-Email": ADMINS[0]})), "")
verifier("F. activate-coach + JWT d'utilisateur normal -> refus",
         SIGNE(FausseRequete({"Authorization": "Bearer " + jeton(
             {"email": "coach.a@example.com", "exp": T + 600})})), "")
verifier("G. activate-coach + JWT super-admin signe -> AUTORISE",
         SIGNE(FausseRequete({"Authorization": "Bearer " + jeton(
             {"email": ADMINS[0], "exp": T + 600})})), ADMINS[0])
verifier("jeton signe d'un AUTRE secret -> refus",
         SIGNE(FausseRequete({"Authorization": "Bearer " + jeton(
             {"email": ADMINS[0], "exp": T + 600}, "AUTRE-SECRET-DE-TEST-40-CARACTERES")})), "")
verifier("jeton expire -> refus",
         SIGNE(FausseRequete({"Authorization": "Bearer " + jeton(
             {"email": ADMINS[0], "exp": T - 60})})), "")
verifier("jeton ABONNE signe -> refus",
         SIGNE(FausseRequete({"Authorization": "Bearer " + jeton(
             {"type": "subscriber", "email": ADMINS[0], "exp": T + 600})})), "")
_alg_none = (base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
             + "." + base64.urlsafe_b64encode(json.dumps({"email": ADMINS[0]}).encode()).decode().rstrip("=") + ".")
verifier("jeton alg:none -> refus", SIGNE(FausseRequete({"Authorization": "Bearer " + _alg_none})), "")

# === H/I/J — LA CHAINE D'ATTAQUE COMPLETE ==================================
def simuler_attaque(adresse):
    """Rejoue les trois maillons. Renvoie l'etape ou l'attaque casse."""
    if inscription_refusee(adresse):
        return "BLOQUEE a l'etape 1 (inscription)"
    if not SIGNE(FausseRequete({"X-User-Email": ADMINS[0]})):
        return "BLOQUEE a l'etape 2 (activation)"
    return "REUSSIE — JWT super-admin obtenu"


verifier("H. la chaine casse DES la premiere etape",
         simuler_attaque(ADMINS[0]), "BLOQUEE a l'etape 1 (inscription)")
verifier("H. idem pour le second super-admin",
         simuler_attaque(ADMINS[1]), "BLOQUEE a l'etape 1 (inscription)")
verifier("I. compte deja cree -> l'activation reste refusee sans jeton",
         SIGNE(FausseRequete({"X-User-Email": ADMINS[0]})), "")
verifier("J. aucune variante d'adresse ne franchit l'etape 1",
         [v for v in [a.upper() for a in ADMINS] + ["  " + a + " " for a in ADMINS]
          if not inscription_refusee(v)], [])


# === COUVERTURE PAR NOEUDS D'AST ===========================================
GARDES = ("super_admin_signe", "coach_jwt_email", "_v311_coach_email_from_jwt")


def _nom(n):
    f = n.func
    return f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")


def analyser(chemin, nom_fn, lig=None):
    lig = lig or lignes(chemin)
    for n in ast.walk(ast.parse("\n".join(lig))):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom_fn:
            corps = list(n.body)
            if corps and isinstance(corps[0], ast.Expr) and isinstance(corps[0].value, ast.Constant):
                corps = corps[1:]
            gardes, regles, ecr = [], [], []
            for s in corps:
                for x in ast.walk(s):
                    if isinstance(x, ast.Call):
                        nm = _nom(x)
                        if nm in GARDES:
                            gardes.append((x.lineno, nm, [a.id for a in x.args if isinstance(a, ast.Name)]))
                        if nm in ("is_super_admin_email", "is_super_admin", "_v20d_est_admin"):
                            regles.append(x.lineno)
                        if nm in ("insert_one", "update_one", "update_many", "insert_many"):
                            ecr.append(x.lineno)
            return {"trouvee": True, "params": [a.arg for a in n.args.args],
                    "gardes": gardes, "regles": regles, "ecr": ecr,
                    "code": "\n".join("\n".join(lig[s.lineno - 1:s.end_lineno]) for s in corps)}
    return {"trouvee": False, "params": [], "gardes": [], "regles": [], "ecr": [], "code": ""}


R_ACT = analyser(SRC_COACH, "activate_coach")
R_REG = analyser(SRC_AUTH, "register")
R_FREE = analyser(SRC_CINET, "register_free_pack")

verifier_vrai("activate-coach : APPELLE une garde signee", bool(R_ACT["gardes"]), R_ACT["gardes"])
verifier_vrai("activate-coach : la garde recoit `request`",
              any("request" in a for _, _, a in R_ACT["gardes"]))
verifier_vrai("activate-coach : AUCUN `is_super_admin(X-User-Email)` en garde",
              "is_super_admin(caller_email)" not in R_ACT["code"])
verifier_vrai("activate-coach : la garde precede toute ecriture",
              R_ACT["gardes"] and all(min(l for l, _, _ in R_ACT["gardes"]) < e for e in R_ACT["ecr"]),
              (R_ACT["gardes"], R_ACT["ecr"]))

for _nomr, _r in (("register", R_REG), ("register-free", R_FREE)):
    verifier_vrai("%s : la regle d'exclusion est APPELEE" % _nomr, bool(_r["regles"]), _r["regles"])
    verifier_vrai("%s : la regle precede toute ecriture" % _nomr,
                  _r["regles"] and all(min(_r["regles"]) < e for e in _r["ecr"]),
                  (_r["regles"], _r["ecr"]))
    verifier_vrai("%s : le refus est un 409 indiscernable (pas d'oracle)" % _nomr,
                  "déjà enregistré" in _r["code"] and "409" in _r["code"])
    verifier_vrai("%s : le message ne dit PAS « super admin »" % _nomr,
                  "super-admin" not in _r["code"].lower().split("detail=")[-1][:120]
                  if "detail=" in _r["code"] else True)

# === SABOTAGES : le test qui teste le test =================================
def saboter(chemin, nom_fn, quoi):
    lig = lignes(chemin)
    for n in ast.walk(ast.parse("\n".join(lig))):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom_fn:
            corps = list(n.body)
            if corps and isinstance(corps[0], ast.Expr) and isinstance(corps[0].value, ast.Constant):
                corps = corps[1:]
            for s in corps:
                for x in ast.walk(s):
                    if isinstance(x, ast.Call) and _nom(x) in quoi:
                        for i in range(s.lineno, s.end_lineno + 1):
                            lig[i - 1] = ""
    return lig


verifier("sabotage : garde retiree d'activate-coach -> vue",
         analyser(SRC_COACH, "activate_coach", saboter(SRC_COACH, "activate_coach", GARDES))["gardes"], [])
verifier("sabotage : regle retiree de register -> vue",
         analyser(SRC_AUTH, "register", saboter(SRC_AUTH, "register", ("is_super_admin_email",)))["regles"], [])
verifier("sabotage : regle retiree de register-free -> vue",
         analyser(SRC_CINET, "register_free_pack",
                  saboter(SRC_CINET, "register_free_pack", ("_v20d_est_admin",)))["regles"], [])

# === K/L — LES LOTS PRECEDENTS NE SONT PAS TOUCHES =========================
# V2-0b et V2-0c vivent sur d'autres branches. On verifie ici que V2-0d n'a
# laisse AUCUN marqueur dans leurs fichiers — sinon les lots se melangeraient.
_AILLEURS = [os.path.join(RACINE, "api", "server.py"),
             os.path.join(RACINE, "api", "routes", "promo_routes.py"),
             os.path.join(RACINE, "api", "routes", "reservation_routes.py"),
             os.path.join(RACINE, "api", "routes", "shared.py")]
verifier("K/L. aucun marqueur V2-0d hors des 3 fichiers du lot",
         [os.path.basename(f) for f in _AILLEURS
          if os.path.exists(f) and "V2-0d" in open(f, encoding="utf-8").read()], [])
# Et les 3 fichiers du lot portent bien le marqueur.
verifier("les 3 fichiers du lot portent le marqueur V2-0d",
         [os.path.basename(f) for f in (SRC_AUTH, SRC_COACH, SRC_CINET)
          if "V2-0d" not in open(f, encoding="utf-8").read()], [])

# === HYGIENE DU FICHIER DE TEST ============================================
_moi = open(MOI, encoding="utf-8").read()
_imp = [a.name for n in ast.walk(ast.parse(_moi)) if isinstance(n, ast.Import) for a in n.names] \
    + [n.module or "" for n in ast.walk(ast.parse(_moi)) if isinstance(n, ast.ImportFrom)]
verifier("ce test n'importe ni requests ni pymongo",
         [m for m in _imp if m and m.split(".")[0] in ("requests", "pymongo", "motor", "httpx")], [])
_dom = "afroboost" + "." + "com"
verifier("ce test ne connait pas l'URL de production", _moi.count(_dom), 0)
verifier_vrai("le secret de test porte un prefixe reconnaissable",
              SECRET_TEST.startswith("SECRET-DE-TEST-"))

if _AVANT is None:
    os.environ.pop("JWT_SECRET", None)
else:
    os.environ["JWT_SECRET"] = _AVANT

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
