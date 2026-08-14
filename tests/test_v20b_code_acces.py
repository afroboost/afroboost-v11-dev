# -*- coding: utf-8 -*-
"""V2-0b — tests hors ligne. Aucune base, aucun reseau, aucun envoi.

Trois routes rendaient un code d'acces contre un simple e-mail, sans aucune
authentification :
  * GET /api/my-access-code?email=                      -> `users.accessCode`
  * GET /api/subscriber/by-email/{email}/space-link     -> code d'abonnement + URL

Le controle de couverture marche l'AST par NOEUDS D'APPEL, jamais par recherche
de texte : les docstrings de ces routes CITENT les gardes par leur nom, et une
premiere version de ce controle (V2-0) restait verte apres suppression des
gardes. Un auto-test sabote chaque route en memoire et exige que le controle
voie la garde disparaitre.
"""
import ast, os, sys, tempfile

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_SERVER = os.path.join(RACINE, "api", "server.py")
SRC_RESA = os.path.join(RACINE, "api", "routes", "reservation_routes.py")
SRC_SHARED = os.path.join(RACINE, "api", "routes", "shared.py")

# Gardes acceptables. `require_auth` en est VOLONTAIREMENT absente : elle accepte
# encore le repli `X-User-Email` non signe (mode transitoire V265), donc elle ne
# protege pas un secret.
# ⚠️ `_v309_is_coach_or_admin` EST dans cette liste, et c'est important : c'est
# le controle de ROLE, le seul rempart contre un e-mail quelconque. Une premiere
# version l'omettait — on pouvait alors le remplacer par `True` sans qu'aucun
# test ne bronche. Defaut trouve en relecture independante.
GARDES = ("v20_exiger_coach_signe", "_v263_authenticated_coach",
          "_v309_require_coach_or_admin", "_v411_exiger_super_admin",
          "_v309_is_coach_or_admin")

SRC_PROMO = os.path.join(RACINE, "api", "routes", "promo_routes.py")

ROUTES = [
    (SRC_RESA, "get_my_access_code", "/api/my-access-code"),
    (SRC_SERVER, "get_space_link_by_email", "/api/subscriber/by-email/{email}/space-link"),
    (SRC_PROMO, "sync_subscriptions_for_email", "/api/discount-codes/subscriptions/sync"),
]

resultats = []


def verifier(nom, obtenu, attendu):
    resultats.append((obtenu == attendu, nom, obtenu, attendu))


def verifier_vrai(nom, condition, detail=""):
    resultats.append((bool(condition), nom, detail or condition, True))


def _nom_appele(noeud):
    f = noeud.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def analyser_route(chemin, nom_fn):
    """Analyse par NOEUDS D'APPEL. La docstring est retiree avant tout examen."""
    src = open(chemin, encoding="utf-8").read()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom_fn:
            args = [a.arg for a in n.args.args]
            corps = list(n.body)
            if corps and isinstance(corps[0], ast.Expr) and isinstance(corps[0].value, ast.Constant):
                corps = corps[1:]
            appels = []
            for _s in corps:
                for _n in ast.walk(_s):
                    if isinstance(_n, ast.Call):
                        appels.append((getattr(_n, "lineno", 0), _nom_appele(_n),
                                       [a.id for a in _n.args if isinstance(a, ast.Name)]))
            _g = [(l, nom, a) for l, nom, a in appels if nom in GARDES]
            _lect = [l for l, nom, _ in appels if nom in ("find", "find_one", "aggregate")]
            return {
                "trouvee": True, "a_request": "request" in args,
                "gardes": [nom for _, nom, _ in _g],
                "garde_recoit_request": any("request" in a for _, _, a in _g),
                "garde_avant_lecture": bool(_g) and (
                    not _lect or min(l for l, _, _ in _g) < min(_lect)),
                "code": "\n".join(filter(None, (ast.get_source_segment(src, _s) for _s in corps))),
                "docstring": ast.get_docstring(n) or "",
            }
    return {"trouvee": False, "a_request": False, "gardes": [], "code": "",
            "garde_recoit_request": False, "garde_avant_lecture": False, "docstring": ""}


def analyser_source(src, nom_fn):
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(src)
        chemin = f.name
    try:
        return analyser_route(chemin, nom_fn)
    finally:
        os.unlink(chemin)


def saboter(chemin, nom_fn):
    """Retire du CODE (pas de la docstring) toute instruction appelant une garde."""
    src = open(chemin, encoding="utf-8").read()
    lignes = src.split("\n")
    a_retirer = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom_fn:
            corps = list(n.body)
            if corps and isinstance(corps[0], ast.Expr) and isinstance(corps[0].value, ast.Constant):
                corps = corps[1:]
            for _s in corps:
                for _n in ast.walk(_s):
                    if isinstance(_n, ast.Call) and _nom_appele(_n) in GARDES:
                        for _l in range(getattr(_s, "lineno", 0), getattr(_s, "end_lineno", 0) + 1):
                            a_retirer.add(_l - 1)
    return "\n".join(l for i, l in enumerate(lignes) if i not in a_retirer)


# === 1. LES DEUX ROUTES SONT FERMEES ========================================
for _f, _fn, _http in ROUTES:
    _i = analyser_route(_f, _fn)
    verifier_vrai("%s : la fonction existe" % _http, _i["trouvee"])
    verifier_vrai("%s : recoit `request`" % _http, _i["a_request"], "signature sans request")
    verifier_vrai("%s : APPELLE reellement une garde" % _http, bool(_i["gardes"]),
                  "aucun appel parmi %s" % (GARDES,))
    verifier_vrai("%s : la garde recoit `request`" % _http, _i["garde_recoit_request"], _i["gardes"])
    verifier_vrai("%s : la garde s'execute AVANT toute lecture de base" % _http,
                  _i["garde_avant_lecture"], _i["gardes"])

# === 2. LES TROIS ROUTES SONT EN JETON SIGNE, AUCUN REPLI ==================
#
# ⚠️ ASSERTION INVERSEE PAR RAPPORT A LA PREMIERE VERSION DE CE FICHIER.
# Elle verrouillait une garde TRANSITOIRE sur `space-link`, au motif que le
# bouton « Lien » du dashboard l'appelle et qu'un jeton strict rejouerait
# l'incident V310c. Deux mesures ont invalide ce raisonnement :
#   1. `SUPER_ADMIN_EMAILS` est en clair dans le bundle public -> le repli
#      `X-User-Email` ne fermait rien du tout ;
#   2. `GET /api/contacts/all`, qui alimente la liste ou vit le bouton, est DEJA
#      JWT-strict (V311h) — mesure en production : 403 avec `X-User-Email` seul.
#      Un coach qui VOIT le bouton porte donc forcement un jeton signe.
# La garde stricte est donc exactement aussi permissive que l'ecran appelant.
for _f, _fn, _http in ROUTES:
    _i = analyser_route(_f, _fn)
    verifier_vrai("%s : jeton SIGNE exige" % _http,
                  "v20_exiger_coach_signe" in _i["gardes"], _i["gardes"])
    verifier_vrai("%s : AUCUN repli X-User-Email" % _http,
                  "_v263_authenticated_coach" not in _i["gardes"], _i["gardes"])

_mac = analyser_route(SRC_RESA, "get_my_access_code")
_sl = analyser_route(SRC_SERVER, "get_space_link_by_email")
_sync = analyser_route(SRC_PROMO, "sync_subscriptions_for_email")

# La route d'ECRITURE doit refuser AVANT d'ecrire, pas seulement avant de lire.
verifier_vrai("sync : la garde precede l'insert_one",
              _sync["code"].index("v20_exiger_coach_signe") < _sync["code"].index("insert_one")
              if "insert_one" in _sync["code"] else True)

# === 3. ZERO REGRESSION : le 404 « Pas abonne » est CONSERVE ================
# `ContactsManager.js:120` traduit le 404 par l'etat « Pas abonne ». Le changer
# en 403 afficherait « Erreur » au coach : regression silencieuse.
verifier_vrai("space-link : le 404 « Aucun code abonne » est conserve",
              "Aucun code abonné pour cet email" in _sl["code"]
              and "status_code=404" in _sl["code"])
verifier_vrai("space-link : le 400 « Email requis » est conserve",
              "Email requis" in _sl["code"] and "status_code=400" in _sl["code"])
verifier_vrai("my-access-code : le 400 et le 404 sont conserves",
              "Email requis" in _mac["code"] and "Utilisateur non trouvé" in _mac["code"])
# La forme de la reponse ne change pas non plus.
verifier_vrai("space-link : rend toujours code + url", '"url"' in _sl["code"] and '"code"' in _sl["code"])
verifier_vrai("my-access-code : rend toujours accessCode", "accessCode" in _mac["code"])

# === 4. L'ORDRE DES OPERATIONS : refuser AVANT de lire la base ==============
for _f, _fn, _http in ROUTES:
    _i = analyser_route(_f, _fn)
    _c = _i["code"]
    _pos_garde = min((_c.index(g) for g in GARDES if g in _c), default=-1)
    _pos_lecture = _c.index("find_one") if "find_one" in _c else len(_c)
    verifier_vrai("%s : la garde precede le find_one dans le texte" % _http,
                  _pos_garde >= 0 and _pos_garde < _pos_lecture)

# === 5. AUCUN SECRET JOURNALISE EN CLAIR ====================================
# Exigence bloquante : V2-0b ne doit ajouter aucun journal contenant un code.
_interdits = []
for _f, _fn, _http in ROUTES:
    for _l in analyser_route(_f, _fn)["code"].split("\n"):
        if "logger." in _l and any(m in _l for m in ("accessCode", "code)", '"code"', "code}")):
            _interdits.append((_http, _l.strip()[:90]))
verifier("aucun code d'acces journalise en clair", _interdits, [])
# Le journal de refus vit desormais DANS `v20_exiger_coach_signe` (shared.py),
# plus dans les routes : une seule ligne de journal, un seul format, et elle ne
# porte que l'identite revendiquee — jamais un code.
_src_sh = open(SRC_SHARED, encoding="utf-8").read()
_g_txt = ast.get_source_segment(_src_sh, next(
    n for n in ast.parse(_src_sh).body
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    and n.name == "v20_exiger_coach_signe")) or ""
# On n'inspecte que les LIGNES DE JOURNAL : chercher « code » dans tout le corps
# donnerait un faux positif sur `status_code=403`.
_lignes_journal = [l for l in _g_txt.split("\n") if "logger." in l]
verifier_vrai("la garde journalise bien le refus", any("REFUS" in l for l in _lignes_journal))
verifier_vrai("aucune ligne de journal ne porte un code d'acces",
              not any(m in l for l in _lignes_journal
                      for m in ("accessCode", "access_code", "subscriber_code", '"code"')),
              _lignes_journal)
verifier_vrai("aucune route ne journalise le refus elle-meme (une seule source)",
              all("logger.warning" not in analyser_route(f, fn)["code"] for f, fn, _ in ROUTES))

# === 6. AUTO-TEST : le controle echoue-t-il VRAIMENT sans la garde ? ========
_sabotages = []
for _f, _fn, _http in ROUTES:
    _s = analyser_source(saboter(_f, _fn), _fn)
    if _s["gardes"]:
        _sabotages.append((_http, _s["gardes"]))
verifier("garde retiree -> le controle la voit disparaitre (3 routes)", _sabotages, [])
# ... alors que les docstrings, elles, citent toujours les gardes.
verifier_vrai("les docstrings citent les gardes (piege desamorce)",
              "_v263_authenticated_coach" in _sl["docstring"]
              and "SIGNÉ" in _mac["docstring"].upper())

# === 7. LA GARDE SIGNEE RESTE SAINE (heritee de V2-0, non modifiee) ========
_src_shared = open(SRC_SHARED, encoding="utf-8").read()
_garde = ast.get_source_segment(_src_shared, next(
    n for n in ast.parse(_src_shared).body
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    and n.name == "v20_exiger_coach_signe")) or ""
verifier_vrai("la garde signee lit le JWT, jamais l'en-tete", "coach_jwt_email(request)" in _garde)
verifier_vrai("X-User-Email n'y sert qu'a journaliser le refus", _garde.count("X-User-Email") == 1)
verifier_vrai("la garde signee leve 403", "raise HTTPException(status_code=403" in _garde)
verifier_vrai("la garde signee ne renvoie jamais une chaine vide", 'return ""' not in _garde)
verifier_vrai("shared.py n'a pas ete modifie par V2-0b",
              "V2-0 (CONTACTS) : REFUSER N'EST PAS FILTRER" in _src_shared)

# === 8. AUCUNE AUTRE ROUTE NE REND UN CODE CONTRE UN E-MAIL SEUL ===========
# Balayage : toute fonction qui lit `assignedEmail` ou `users.accessCode` et
# renvoie un code doit porter une garde. C'est le controle qui empeche qu'une
# 3e jumelle reapparaisse.
# ⚠️ On DECOUPE les lignes une seule fois et on tranche par `lineno`.
# `ast.get_source_segment` re-parcourt la source a chaque appel : sur les 26 000
# lignes de `server.py` et ses ~900 fonctions, le controle devenait quadratique
# et ne terminait plus. Mesure : > 120 s avant, < 1 s apres.
_lignes_srv = open(SRC_SERVER, encoding="utf-8").read().split("\n")


def _texte(n):
    """Source d'un noeud, par tranche de lignes — O(1) au lieu de O(n)."""
    d = getattr(n, "lineno", 0) - 1
    f = getattr(n, "end_lineno", d + 1)
    return "\n".join(_lignes_srv[d:f])


# Le critere doit etre PRECIS. Une premiere version attrapait 5 faux positifs
# (`get_subscriber_space`, `join_subscriber_space`, `get_subscriber_by_code`…) :
# ce sont des routes indexees par le CODE — modele capability, il faut deja
# detenir le secret pour les appeler. Ce qu'on cherche, c'est l'inverse : une
# route qui prend un E-MAIL en parametre et rend un code. Le critere porte donc
# sur la SIGNATURE, pas sur le corps.
def _est_une_route(n):
    """La fonction est-elle exposee en HTTP ? (decorateur `@…_router.get/post/…`)

    Sans ce filtre, le controle attrapait `_v334_stats_abonne` — un HELPER
    interne, sans decorateur, appele par une fonction qui detient deja le code
    ET l'e-mail. Un helper n'est pas une porte : seule une route en est une.
    """
    for d in getattr(n, "decorator_list", []):
        f = d.func if isinstance(d, ast.Call) else d
        if isinstance(f, ast.Attribute) and f.attr in ("get", "post", "put", "delete", "patch"):
            return True
    return False


_sans_garde = []
for n in ast.walk(ast.parse("\n".join(_lignes_srv))):
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if not _est_une_route(n):
            continue                      # helper interne : pas une porte
        params = [a.arg for a in n.args.args]
        if not any("email" in p.lower() for p in params):
            continue                      # route indexee par le code : hors sujet
        corps = list(n.body)
        if corps and isinstance(corps[0], ast.Expr) and isinstance(corps[0].value, ast.Constant):
            corps = corps[1:]
        if not corps:
            continue
        code = "\n".join(_texte(s) for s in corps)
        rend_code = ('"code": code' in code) or ('"code": subscription' in code)
        if rend_code and not any(g in code for g in GARDES):
            _sans_garde.append(n.name)
verifier("aucune autre route ne rend un code contre un e-mail sans garde",
         [f for f in _sans_garde if f not in ("v389_subscriber_recover",)], [])

print("=" * 74)
_echecs = 0
for ok, nom, obtenu, attendu in resultats:
    print(("  PASS  " if ok else "  FAIL  ") + nom)
    if not ok:
        _echecs += 1
        print("          obtenu  : %r" % (obtenu,))
        print("          attendu : %r" % (attendu,))
print("=" * 74)
print("  %d/%d" % (len(resultats) - _echecs, len(resultats)))
sys.exit(1 if _echecs else 0)
