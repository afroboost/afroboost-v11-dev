# -*- coding: utf-8 -*-
"""V2-0 — tests hors ligne. Aucune base, aucun reseau, aucun envoi.

Deux familles :
  1. les fonctions de perimetre, EXTRAITES du vrai `api/routes/shared.py` ;
  2. un controle de COUVERTURE qui relit `api/server.py`, `campaign_routes.py`
     et `reservation_routes.py` par AST pour verifier qu'aucune des 4 routes
     fermees ne peut redevenir anonyme sans faire echouer ce fichier.

La famille 2 est la plus rentable : elle reste vraie quand quelqu'un modifiera
les routes plus tard, alors qu'un test de comportement seul ne le verrait pas.
"""
import ast, os, sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_SHARED = os.path.join(RACINE, "api", "routes", "shared.py")
SRC_SERVER = os.path.join(RACINE, "api", "server.py")
SRC_CAMPAGNES = os.path.join(RACINE, "api", "routes", "campaign_routes.py")
SRC_RESA = os.path.join(RACINE, "api", "routes", "reservation_routes.py")

A_EXTRAIRE = {"v20_perimetre_contacts", "is_super_admin"}
CLASSES = {"V20AccesRefuse"}
CONSTANTES = {"SUPER_ADMIN_EMAILS"}


def charger(chemin, fonctions, classes=(), constantes=()):
    src = open(chemin, encoding="utf-8").read()
    arbre = ast.parse(src)
    morceaux = []
    for n in arbre.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in fonctions:
            morceaux.append(ast.get_source_segment(src, n))
        elif isinstance(n, ast.ClassDef) and n.name in classes:
            morceaux.append(ast.get_source_segment(src, n))
        elif isinstance(n, ast.Assign):
            for c in n.targets:
                if isinstance(c, ast.Name) and c.id in constantes:
                    morceaux.append(ast.get_source_segment(src, n))
    return morceaux, src


_morceaux, _ = charger(SRC_SHARED, A_EXTRAIRE, CLASSES, CONSTANTES)
NS = {}
exec("\n\n".join(_morceaux), NS)
_manque = [f for f in (A_EXTRAIRE | CLASSES) if f not in NS]
assert not _manque, "extraction incomplete : %s" % _manque

PERIMETRE = NS["v20_perimetre_contacts"]
REFUS = NS["V20AccesRefuse"]
EST_ADMIN = NS["is_super_admin"]
ADMINS = NS["SUPER_ADMIN_EMAILS"]

resultats = []


def verifier(nom, obtenu, attendu):
    resultats.append((obtenu == attendu, nom, obtenu, attendu))


def verifier_vrai(nom, condition, detail=""):
    resultats.append((bool(condition), nom, detail or condition, True))


def leve(fn, *a):
    try:
        fn(*a)
        return False
    except REFUS:
        return True
    except Exception:
        return False


# === 1. LE PIEGE N°1 : refuser n'est pas filtrer ============================
# `get_coach_filter("")` rend `{"coach_id": ""}`, qui SELECTIONNE les 5 fiches a
# coach_id vide. Le perimetre, lui, doit LEVER.
verifier_vrai("identite vide -> LEVE (jamais un dictionnaire)", leve(PERIMETRE, ""))
verifier_vrai("identite None -> LEVE", leve(PERIMETRE, None))
verifier_vrai("identite espaces -> LEVE", leve(PERIMETRE, "   "))
verifier_vrai("identite non-texte -> LEVE", leve(PERIMETRE, 12345))
verifier_vrai("identite liste -> LEVE", leve(PERIMETRE, ["a@b.com"]))
verifier_vrai("identite dict -> LEVE", leve(PERIMETRE, {"email": "a@b.com"}))

# Aucune sortie legitime ne doit jamais contenir un coach_id vide ou nul.
_sorties = [PERIMETRE(ADMINS[0]), PERIMETRE("coach.a@example.com"),
            PERIMETRE("  Coach.B@Example.COM  ")]
verifier("aucune sortie ne porte coach_id vide ou None",
         [s for s in _sorties if s.get("coach_id", "x") in ("", None)], [])

# === 2. Super-admin : la vue globale reste intacte (piege n°4, V310c) =======
for _a in ADMINS:
    verifier("super-admin (%s...) -> {} " % _a[:6], PERIMETRE(_a), {})
verifier("super-admin en MAJUSCULES -> {}", PERIMETRE(ADMINS[0].upper()), {})
verifier("super-admin avec espaces -> {}", PERIMETRE("  " + ADMINS[0] + " "), {})
verifier_vrai("les DEUX super-admins sont reconnus", len(ADMINS) == 2 and all(EST_ADMIN(a) for a in ADMINS))

# === 3. Coach ordinaire : cadre strict ======================================
verifier("coach -> filtre sur son email", PERIMETRE("coach.a@example.com"),
         {"coach_id": "coach.a@example.com"})
verifier("casse et espaces normalises", PERIMETRE("  Coach.A@Example.COM "),
         {"coach_id": "coach.a@example.com"})
verifier("coach B -> son propre filtre", PERIMETRE("coach.b@example.com"),
         {"coach_id": "coach.b@example.com"})
verifier_vrai("coach A et coach B n'ont pas le meme perimetre",
              PERIMETRE("coach.a@example.com") != PERIMETRE("coach.b@example.com"))

# === 4. FAIL-CLOSED sur l'historique sans proprietaire ======================
# Simulation d'une collection reelle : 3 fiches de A, 2 de B, 3 orphelines
# (champ absent, chaine vide, None) — les trois formes rencontrees en base.
BASE = (
    [{"id": "a%d" % i, "coach_id": "coach.a@example.com"} for i in range(3)]
    + [{"id": "b%d" % i, "coach_id": "coach.b@example.com"} for i in range(2)]
    + [{"id": "orphelin_absent"},
       {"id": "orphelin_vide", "coach_id": ""},
       {"id": "orphelin_null", "coach_id": None}]
)


def selection(docs, filtre):
    """Reproduit fidelement la semantique Mongo d'un filtre {"coach_id": v}."""
    if not filtre:
        return list(docs)                       # {} = tout, comme Mongo
    attendu = filtre["coach_id"]
    return [d for d in docs if d.get("coach_id") == attendu]


_vue_a = selection(BASE, PERIMETRE("coach.a@example.com"))
_vue_b = selection(BASE, PERIMETRE("coach.b@example.com"))
_vue_sa = selection(BASE, PERIMETRE(ADMINS[0]))

verifier("coach A voit ses 3 fiches", sorted(d["id"] for d in _vue_a), ["a0", "a1", "a2"])
verifier("coach A ne voit AUCUNE fiche de B", [d for d in _vue_a if d["id"].startswith("b")], [])
verifier("coach B ne voit AUCUNE fiche de A", [d for d in _vue_b if d["id"].startswith("a")], [])
verifier("coach A ne voit AUCUN orphelin (fail-closed)",
         [d["id"] for d in _vue_a if d["id"].startswith("orphelin")], [])
verifier("coach B ne voit AUCUN orphelin (fail-closed)",
         [d["id"] for d in _vue_b if d["id"].startswith("orphelin")], [])
verifier("le super-admin voit TOUT, orphelins compris", len(_vue_sa), len(BASE))
verifier("le super-admin garde les 3 orphelins",
         sorted(d["id"] for d in _vue_sa if d["id"].startswith("orphelin")),
         ["orphelin_absent", "orphelin_null", "orphelin_vide"])

# Le compteur ne doit jamais reveler le volume d'un autre coach (vecteur V4).
verifier("compteur de A = taille de son perimetre", len(_vue_a), 3)
verifier("compteur de B = taille de son perimetre", len(_vue_b), 2)
verifier_vrai("ajouter une fiche a B ne change pas le compteur de A",
              len(selection(BASE + [{"id": "b_new", "coach_id": "coach.b@example.com"}],
                            PERIMETRE("coach.a@example.com"))) == 3)

# === 5. Le filtre ne peut pas etre elargi par l'appelant ====================
# Un filtre applicatif qui porterait deja un coach_id ne doit pas gagner.
def fusion_sure(filtre_applicatif, perimetre):
    q = dict(filtre_applicatif)
    q.update(perimetre)          # le perimetre ecrase TOUJOURS
    return q


verifier("un coach_id fourni par l'appelant est ecrase par le perimetre",
         fusion_sure({"coach_id": "coach.b@example.com", "validated": True},
                     PERIMETRE("coach.a@example.com")),
         {"coach_id": "coach.a@example.com", "validated": True})
verifier("pour le super-admin, la fusion laisse le filtre applicatif intact",
         fusion_sure({"validated": True}, PERIMETRE(ADMINS[0])), {"validated": True})

# === 6. COUVERTURE — les 4 routes ne peuvent plus redevenir anonymes =======
#
# On relit le VRAI code par AST. Pour chaque route fermee : la fonction doit
# recevoir `request` ET appeler une garde. Ce controle survit aux refactorisations.
GARDES = ("v20_exiger_coach_signe", "_v263_authenticated_coach",
          "_v309_require_coach_or_admin", "_v411_exiger_super_admin")

ROUTES_FERMEES = [
    (SRC_SERVER, "get_campaign_errors", "/campaign-errors"),
    (SRC_SERVER, "get_active_conversations_for_messaging", "/conversations/active"),
    (SRC_CAMPAGNES, "get_campaigns_error_logs", "/campaigns/logs"),
    (SRC_RESA, "export_attendance", "/reservations/export/attendance"),
]


def _nom_appele(noeud):
    """Nom de la fonction appelée par un noeud `Call`, sans le module."""
    f = noeud.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def analyser_route(chemin, nom_fn):
    """Analyse une route par ses NOEUDS D'APPEL, jamais par recherche de texte.

    ⚠️ POURQUOI CETTE PRECISION. La premiere version de ce controle cherchait le
    nom de la garde comme SOUS-CHAINE du code source de la fonction. Or
    `ast.get_source_segment` inclut la DOCSTRING — et les docstrings V2-0 citent
    les gardes par leur nom. Consequence demontree en relecture : supprimer les
    5 lignes de garde de `/conversations/active` laissait les 54 tests VERTS. Un
    simple `import` non suivi d'un appel suffisait aussi. Le controle
    « anti-regression » ne controlait rien.

    On marche donc l'AST du CORPS : il faut un vrai `Call` vers une garde, et il
    doit PRECEDER la premiere lecture de base (`.find(`), sinon la garde
    s'executerait apres la fuite.
    """
    src = open(chemin, encoding="utf-8").read()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom_fn:
            args = [a.arg for a in n.args.args]
            corps_noeuds = list(n.body)
            if corps_noeuds and isinstance(corps_noeuds[0], ast.Expr) \
                    and isinstance(corps_noeuds[0].value, ast.Constant):
                corps_noeuds = corps_noeuds[1:]          # on jette la docstring
            appels = []
            for _sous in corps_noeuds:
                for _n in ast.walk(_sous):
                    if isinstance(_n, ast.Call):
                        appels.append((getattr(_n, "lineno", 0), _nom_appele(_n),
                                       [a.id for a in _n.args if isinstance(a, ast.Name)]))
            _gardes = [(l, nom, a) for l, nom, a in appels if nom in GARDES]
            _lectures = [l for l, nom, _ in appels if nom in ("find", "find_one", "aggregate")]
            return {
                "trouvee": True,
                "a_request": "request" in args,
                "gardes": [nom for _, nom, _ in _gardes],
                # la garde recoit-elle bien l'objet `request` ?
                "garde_recoit_request": any("request" in a for _, _, a in _gardes),
                # la garde s'execute-t-elle AVANT toute lecture de base ?
                "garde_avant_lecture": bool(_gardes) and (
                    not _lectures or min(l for l, _, _ in _gardes) < min(_lectures)),
                "corps": ast.get_source_segment(src, n) or "",
                # Code SEUL, docstring retiree : c'est lui qu'il faut inspecter
                # quand on cherche une construction precise.
                "code": "\n".join(filter(None, (ast.get_source_segment(src, _s)
                                                for _s in corps_noeuds))),
            }
    return {"trouvee": False, "a_request": False, "gardes": [], "code": "",
            "garde_recoit_request": False, "garde_avant_lecture": False, "corps": ""}


def analyser_source(src, nom_fn):
    """Même analyse, mais sur une SOURCE fournie — sert à l'auto-test ci-dessous."""
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                     encoding="utf-8") as _f:
        _f.write(src)
        _chemin = _f.name
    try:
        return analyser_route(_chemin, nom_fn)
    finally:
        os.unlink(_chemin)


for _fichier, _fn, _chemin_http in ROUTES_FERMEES:
    _info = analyser_route(_fichier, _fn)
    verifier_vrai("%s : la fonction existe" % _chemin_http, _info["trouvee"])
    verifier_vrai("%s : recoit `request`" % _chemin_http, _info["a_request"],
                  "signature sans request")
    verifier_vrai("%s : APPELLE reellement une garde" % _chemin_http,
                  bool(_info["gardes"]), "aucun appel parmi %s" % (GARDES,))
    verifier_vrai("%s : la garde recoit `request`" % _chemin_http,
                  _info["garde_recoit_request"], _info["gardes"])
    verifier_vrai("%s : la garde s'execute AVANT toute lecture de base" % _chemin_http,
                  _info["garde_avant_lecture"], _info["gardes"])

# Les 3 routes sans usage frontend exigent un jeton SIGNE (pas de repli).
for _fichier, _fn, _chemin_http in ROUTES_FERMEES:
    if _chemin_http == "/conversations/active":
        continue          # transitoire par decision explicite, teste ci-dessous
    _info = analyser_route(_fichier, _fn)
    verifier_vrai("%s : jeton SIGNE exige (aucun repli)" % _chemin_http,
                  "v20_exiger_coach_signe" in _info["gardes"],
                  _info["gardes"])

# `/conversations/active` est volontairement transitoire : le dashboard l'appelle.
# `/conversations/active` est volontairement transitoire : le dashboard l'appelle.
# Toutes les verifications ci-dessous portent sur `code` (docstring RETIREE).
_conv = analyser_route(SRC_SERVER, "get_active_conversations_for_messaging")
verifier_vrai("/conversations/active : garde transitoire (dashboard l'appelle)",
              "_v263_authenticated_coach" in _conv["gardes"])
verifier_vrai("/conversations/active : le role est relu en base",
              "_v309_is_coach_or_admin" in _conv["code"])
verifier_vrai("/conversations/active : les users sont cadres",
              "dict(_v20_portee)" in _conv["code"])
verifier_vrai("/conversations/active : les sessions sont cadrees",
              "_v20_q_sessions.update(_v20_portee)" in _conv["code"])

# L'export nominatif doit cadrer sa requete, pas seulement s'authentifier.
_exp = analyser_route(SRC_RESA, "export_attendance")
verifier_vrai("export attendance : le perimetre entre dans la requete",
              "query.update(_perimetre)" in _exp["code"])

# `/campaign-errors` doit ecarter un coach ordinaire, comme `/campaigns/logs`.
_cerr = analyser_route(SRC_SERVER, "get_campaign_errors")
verifier_vrai("campaign-errors : fail-closed pour un coach ordinaire",
              "v20_perimetre_contacts(_v20_appelant)" in _cerr["code"]
              and "return []" in _cerr["code"])
_clogs = analyser_route(SRC_CAMPAGNES, "get_campaigns_error_logs")
verifier_vrai("campaigns/logs : campaign_errors reserve au super-admin",
              "[] if _perimetre else" in _clogs["code"])
verifier_vrai("campaigns/logs : les campagnes sont cadrees",
              "_q_campagnes.update(_perimetre)" in _clogs["code"])

# === 6bis. AUTO-TEST : ce controle echoue-t-il VRAIMENT si on retire la garde ?
#
# Sans cette preuve, le controle de couverture n'est qu'une declaration. On
# fabrique EN MEMOIRE une version sabotee de chaque route — garde supprimee,
# docstring intacte — et on exige que l'analyse la refuse. C'est le test qui
# teste le test.
def saboter(chemin, nom_fn):
    """Retire du code (pas de la docstring) toute ligne appelant une garde."""
    src = open(chemin, encoding="utf-8").read()
    lignes = src.split("\n")
    arbre = ast.parse(src)
    a_retirer = set()
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom_fn:
            corps = list(n.body)
            if corps and isinstance(corps[0], ast.Expr) and isinstance(corps[0].value, ast.Constant):
                corps = corps[1:]
            for _s in corps:
                for _n in ast.walk(_s):
                    if isinstance(_n, ast.Call) and _nom_appele(_n) in GARDES:
                        for _l in range(getattr(_s, "lineno", 0),
                                        getattr(_s, "end_lineno", 0) + 1):
                            a_retirer.add(_l - 1)
    return "\n".join(l for i, l in enumerate(lignes) if i not in a_retirer)


_sabotages = []
for _fichier, _fn, _chemin_http in ROUTES_FERMEES:
    _sabote = analyser_source(saboter(_fichier, _fn), _fn)
    if _sabote["gardes"]:                       # l'analyse devrait ne RIEN trouver
        _sabotages.append((_chemin_http, _sabote["gardes"]))
verifier("garde retiree -> le controle la voit disparaitre (4 routes)", _sabotages, [])

# ... et la docstring, elle, cite toujours les gardes : c'est la preuve que le
# controle ne se laisse plus abuser par le texte.
_doc_conv = ast.get_docstring(next(
    n for n in ast.walk(ast.parse(open(SRC_SERVER, encoding="utf-8").read()))
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    and n.name == "get_active_conversations_for_messaging")) or ""
verifier_vrai("la docstring cite bien une garde (piege desamorce)",
              "_v263_authenticated_coach" in _doc_conv)

# === 7. Anti-regression : `get_coach_filter` n'est PAS modifiee =============
# On ne touche pas a l'existant ; on ajoute une garde a cote. Ce test le prouve.
_src_shared = open(SRC_SHARED, encoding="utf-8").read()
verifier_vrai("get_coach_filter existe toujours", "def get_coach_filter(" in _src_shared)
verifier_vrai("get_coach_filter rend toujours {} pour un admin",
              "if is_super_admin(email):\n        return {}" in _src_shared)

# === 8. La garde signee ne peut pas etre satisfaite par un en-tete =========
_src_garde = ast.get_source_segment(
    _src_shared,
    next(n for n in ast.parse(_src_shared).body
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
         and n.name == "v20_exiger_coach_signe")) or ""
verifier_vrai("la garde signee lit le JWT, pas l'en-tete",
              "coach_jwt_email(request)" in _src_garde)
verifier_vrai("X-User-Email n'y sert QU'A journaliser le refus",
              _src_garde.count("X-User-Email") == 1
              and "logger.warning" in _src_garde)
verifier_vrai("la garde signee leve 403, elle ne renvoie jamais une chaine vide",
              "raise HTTPException(status_code=403" in _src_garde
              and 'return ""' not in _src_garde)
verifier_vrai("le role est relu dans la collection coaches",
              "database.coaches.find_one" in _src_garde)

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
