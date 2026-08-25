#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BOOT — L'APPLICATION DEMARRE-T-ELLE VRAIMENT ?

POURQUOI CE TEST EXISTE. Le 20 aout 2026, le commit b159717 est passe au vert
sur TOUTE la batterie de tests hors ligne — 214 verifications unitaires, 112 en
navigateur, 15 suites de non-regression — puis a fait PLANTER le backend au
demarrage en production :

    fastapi.exceptions.FastAPIError: Invalid args for response field!
    Hint: check that typing.Optional[starlette.requests.Request] is a valid
    Pydantic field type.

Coolify n'a jamais obtenu de conteneur sain et a bascule sur l'ancien. La
production a ete sauvee par le healthcheck, pas par les tests.

LA FAIBLESSE ETAIT STRUCTURELLE, ET ELLE ETAIT CONNUE : aucun test du depot
n'IMPORTAIT l'application. Ils lisent le source (AST), bouchonnent Mongo,
extraient des fonctions pures — tous d'excellents tests de LOGIQUE, aucun de
DECLARATION. Or une signature de route n'est validee ni par la syntaxe Python,
ni par un test unitaire : elle l'est par FastAPI, au moment ou il construit
l'arbre de dependances de chaque route. C'est-a-dire a l'import, en production,
trop tard.

CE TEST COMBLE EXACTEMENT CE TROU, EN DEUX COUCHES :

  COUCHE 1 — STATIQUE, sans aucune dependance. Tourne partout, y compris sur
  le Python 3.9 de cette machine. Relit le source et refuse les annotations
  que FastAPI ne sait pas interpreter. Elle aurait suffi a attraper le defaut.

  COUCHE 2 — REELLE. Importe `api.server` avec les versions EXACTES de
  production et verifie que les routes se montent. C'est la seule preuve qui
  vaut, parce que c'est litteralement ce que fait uvicorn au demarrage.

Si les dependances manquent, ce test SORT EN ERREUR (code 2) plutot que de
passer : « je ne peux pas prouver » n'est pas « c'est bon ». C'est precisement
la confusion qui a coute ce deploiement.

    python3.13 -m venv /tmp/venv-prod
    /tmp/venv-prod/bin/pip install -r api/requirements.txt
    MONGO_URL="mongodb://127.0.0.1:27017/?serverSelectionTimeoutMS=1" \
      DB_NAME=boot_test /tmp/venv-prod/bin/python tests/test_boot_fastapi.py
"""
import ast
import io
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_OK = 0
_ECHEC = 0


def verifier(libelle, condition, detail=""):
    global _OK, _ECHEC
    if condition:
        _OK += 1
        print("  OK     %s" % libelle)
    else:
        _ECHEC += 1
        print(" ECHEC   %s%s" % (libelle, ("   -> %s" % detail) if detail else ""))


# ═══════════════════════════════════════════════════════════════════════════
# COUCHE 1 — STATIQUE : les annotations que FastAPI REFUSE
# ═══════════════════════════════════════════════════════════════════════════
#
# FastAPI (`dependencies/utils.py:analyze_param`) reconnait ces types par un
# `lenient_issubclass` sur l'annotation NUE. Enveloppee dans un `Optional[...]`
# ou un `Union[...]`, l'annotation devient `typing.Union[...]`, qui n'est
# sous-classe de rien : FastAPI la prend alors pour un champ Pydantic et leve
# `FastAPIError` A L'IMPORT.
#
# La forme CORRECTE pour un parametre facultatif est `x: Request = None` —
# l'annotation reste nue, seul le defaut change. FastAPI injecte la requete et
# ignore le defaut ; un appelant Python interne peut, lui, omettre l'argument.
_TYPES_STARLETTE = (
    "Request", "WebSocket", "Response", "HTTPConnection",
    "BackgroundTasks", "SecurityScopes",
)

_DECORATEURS_ROUTE = ("get", "post", "put", "patch", "delete", "head", "options",
                      "websocket", "api_route")


def _est_decorateur_de_route(dec) -> bool:
    """`@api_router.post(...)`, `@app.get(...)`, `@router.websocket(...)`..."""
    cible = dec.func if isinstance(dec, ast.Call) else dec
    return isinstance(cible, ast.Attribute) and cible.attr in _DECORATEURS_ROUTE


def _annotation_texte(noeud) -> str:
    try:
        return ast.unparse(noeud)
    except Exception:  # Python < 3.9 n'a pas ast.unparse
        return ""


def _annotation_refusee(txt: str):
    """Rend le type Starlette fautif si l'annotation est enveloppee, sinon None."""
    if not txt:
        return None
    enveloppee = txt.startswith("Optional[") or txt.startswith("Union[") \
        or txt.startswith("typing.Optional[") or txt.startswith("typing.Union[") \
        or " | None" in txt or "None | " in txt
    if not enveloppee:
        return None
    for t in _TYPES_STARLETTE:
        if t in txt:
            return t
    return None


def _fichiers_python():
    for dossier, _, fichiers in os.walk(os.path.join(RACINE, "api")):
        if "__pycache__" in dossier:
            continue
        for nom in sorted(fichiers):
            if nom.endswith(".py"):
                yield os.path.join(dossier, nom)


def partie_1_annotations():
    print("\n=== 1. AUCUNE ROUTE NE PORTE UNE ANNOTATION QUE FASTAPI REFUSE ===")
    fautives = []
    routes_vues = 0
    for chemin in _fichiers_python():
        src = io.open(chemin, encoding="utf-8").read()
        try:
            arbre = ast.parse(src)
        except SyntaxError as err:
            fautives.append("%s : SYNTAXE INVALIDE (%s)" % (chemin, err))
            continue
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not any(_est_decorateur_de_route(d) for d in noeud.decorator_list):
                continue
            routes_vues += 1
            args = noeud.args
            tous = list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
            for a in tous:
                if a.annotation is None:
                    continue
                txt = _annotation_texte(a.annotation)
                mauvais = _annotation_refusee(txt)
                if mauvais:
                    fautives.append(
                        "%s:%d  %s(%s: %s)  -> FastAPI prendra `%s` pour un "
                        "champ Pydantic. Ecrire `%s: %s = None`."
                        % (os.path.relpath(chemin, RACINE), a.lineno, noeud.name,
                           a.arg, txt, mauvais, a.arg, mauvais))

    verifier("1a. le balayage a bien trouve des routes (le test n'est pas vide)",
             routes_vues > 100, "routes decorees vues : %d" % routes_vues)
    verifier("1b. aucune annotation `Optional[Request]` / `Union[..., Response]` "
             "sur un parametre de route",
             not fautives, "\n           ".join(fautives))
    return routes_vues


def partie_2_forme_attendue():
    print("\n=== 2. LA FORME CORRECTE EST BIEN EN PLACE LA OU ELLE COMPTE ===")
    src = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
    verifier("2a. `create_checkout_session` recoit la requete HTTP en annotation "
             "NUE, avec un defaut",
             "http_request: Request = None" in src)
    verifier("2b. ... et JAMAIS enveloppee dans un Optional",
             "http_request: Optional[Request]" not in src)
    # Le defaut n'est pas cosmetique : `bot_whatsapp_routes.py` appelle cette
    # fonction directement en Python, avec un seul argument.
    bot = io.open(os.path.join(RACINE, "api", "routes", "bot_whatsapp_routes.py"),
                  encoding="utf-8").read()
    verifier("2c. l'appelant interne du bot WhatsApp appelle toujours la caisse "
             "avec UN seul argument — le defaut lui est indispensable",
             "await create_checkout_session(requete)" in bot)


# ═══════════════════════════════════════════════════════════════════════════
# COUCHE 2 — REELLE : l'application s'importe-t-elle ?
# ═══════════════════════════════════════════════════════════════════════════
def partie_3_import_reel():
    print("\n=== 3. L'APPLICATION S'IMPORTE ET MONTE SES ROUTES (FastAPI reel) ===")
    try:
        import fastapi  # noqa: F401
        from fastapi.routing import APIRoute
    except ImportError:
        print("\n" + "=" * 78)
        print("IMPOSSIBLE DE PROUVER LE DEMARRAGE : fastapi n'est pas installe.")
        print("Ce test SORT EN ERREUR plutot que de passer — « je ne peux pas")
        print("prouver » n'est pas « c'est bon ». C'est cette confusion qui a")
        print("laisse partir un backend qui ne demarrait pas.")
        print("")
        print("  python3.13 -m venv /tmp/venv-prod")
        print("  /tmp/venv-prod/bin/pip install -r api/requirements.txt")
        print("  MONGO_URL='mongodb://127.0.0.1:27017/?serverSelectionTimeoutMS=1' \\")
        print("    DB_NAME=boot_test /tmp/venv-prod/bin/python tests/test_boot_fastapi.py")
        print("=" * 78)
        sys.exit(2)

    os.environ.setdefault("MONGO_URL",
                          "mongodb://127.0.0.1:27017/?serverSelectionTimeoutMS=1")
    os.environ.setdefault("DB_NAME", "boot_test")
    if RACINE not in sys.path:
        sys.path.insert(0, RACINE)

    # C'EST ICI QUE LE DEFAUT SE SERAIT MANIFESTE. FastAPI construit l'arbre de
    # dependances de chaque route au moment ou le decorateur s'execute, donc a
    # l'import du module. Une signature invalide leve `FastAPIError` ici meme.
    try:
        import api.server as S
    except Exception as err:
        verifier("3a. `import api.server` reussit — AUCUNE FastAPIError", False,
                 "%s: %s" % (type(err).__name__, str(err)[:400]))
        return
    verifier("3a. `import api.server` reussit — AUCUNE FastAPIError", True)

    app = getattr(S, "fastapi_app", None)
    verifier("3b. l'objet application existe", app is not None)
    if app is None:
        return

    routes = [r for r in app.routes if isinstance(r, APIRoute)]
    verifier("3c. les routes sont montees en nombre", len(routes) > 300,
             "%d routes" % len(routes))

    chemins = {r.path for r in routes}
    verifier("3d. `/api/create-checkout-session` est declaree",
             "/api/create-checkout-session" in chemins)
    verifier("3e. `/api/tarif/estimation` (LOT 3b) est declaree",
             "/api/tarif/estimation" in chemins)
    verifier("3f. `/api/memberships` (P1-bis-a) est declaree",
             "/api/memberships" in chemins)
    verifier("3g. `/api/reservations` est declaree",
             "/api/reservations" in chemins)
    verifier("3h. `/api/feature-flags` est declaree",
             "/api/feature-flags" in chemins)

    # LA VERIFICATION QUI COMPTE VRAIMENT : FastAPI doit reconnaitre
    # `http_request` comme LA REQUETE, et surtout PAS comme un champ du corps.
    # Une route qui se monte mais attend `http_request` dans le corps JSON
    # renverrait 422 a chaque appel — un demarrage sain, un service casse.
    caisse = next((r for r in routes
                   if r.path == "/api/create-checkout-session"), None)
    verifier("3i. la caisse est bien une APIRoute exploitable", caisse is not None)
    if caisse is not None:
        verifier("3j. FastAPI injecte `http_request` comme REQUETE HTTP",
                 caisse.dependant.request_param_name == "http_request",
                 str(caisse.dependant.request_param_name))
        corps = [p.name for p in caisse.dependant.body_params]
        verifier("3k. ... et NON comme un champ du corps (sinon 422 a chaque appel)",
                 "http_request" not in corps, str(corps))
        verifier("3l. le corps attendu reste le seul modele metier `request`",
                 corps == ["request"], str(corps))

    estim = next((r for r in routes if r.path == "/api/tarif/estimation"), None)
    if estim is not None:
        verifier("3m. l'estimation LOT 3b injecte elle aussi la requete HTTP",
                 estim.dependant.request_param_name == "http_request",
                 str(estim.dependant.request_param_name))

    # ESSAI-7 : la porte gratuite lit desormais l'IP pour limiter le debit. Le
    # meme piege l'attend — `http_request` glisse dans le corps et TOUS les
    # essais gratuits repondent 422.
    gratuit = next((r for r in routes if r.path == "/api/checkout/free"), None)
    verifier("3n. `/api/checkout/free` est declaree", gratuit is not None)
    if gratuit is not None:
        verifier("3o. la porte gratuite injecte la requete HTTP",
                 gratuit.dependant.request_param_name == "http_request",
                 str(gratuit.dependant.request_param_name))
        corps_gratuit = [p.name for p in gratuit.dependant.body_params]
        verifier("3p. ... et le corps reste le seul modele metier `req`",
                 corps_gratuit == ["req"], str(corps_gratuit))


def rapport() -> bool:
    print("\n" + "=" * 78)
    print("BOOT — L'APPLICATION DEMARRE, ET SES ROUTES SE DECLARENT")
    print("=" * 78)
    print("%d / %d verifications au vert" % (_OK, _OK + _ECHEC))
    if _ECHEC:
        print("%d ECHEC(S) — le backend ne demarrerait PAS en production." % _ECHEC)
    return _ECHEC == 0


def principal():
    partie_1_annotations()
    partie_2_forme_attendue()
    partie_3_import_reel()
    return rapport()


if __name__ == "__main__":
    sys.exit(0 if principal() else 1)
