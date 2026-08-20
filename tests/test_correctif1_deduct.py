# -*- coding: utf-8 -*-
"""CORRECTIF 1 — LA CINQUIEME PORTE : `POST /discount-codes/subscriptions/deduct`.

LOT 3c-0b a ferme quatre portes de ce fichier. Celle-ci est restee ouverte, et
c'est la seule du fichier dont la signature n'a MEME PAS de parametre
`request` : s'y authentifier etait materiellement impossible — le defaut de
naissance des portes A et C.

CE QU'ELLE LAISSAIT FAIRE. Un anonyme, muni de la seule adresse e-mail d'un
abonne, detruisait ses seances payees une par une (`remaining_sessions - 1`,
`used_sessions + 1`), jusqu'a clore le forfait (`status: "completed"`). Le
`code` etant FACULTATIF, un corps reduit a `{"email": ...}` suffisait a bruler
une seance du PREMIER forfait actif trouve. Et le journal ne nommait que la
victime, jamais l'appelant.

POURQUOI LE DURCISSEMENT EST SUR (regle V310c). La route est ORPHELINE, prouve
par deux mesures independantes : `git log --all -S "subscriptions/deduct"` sur
`frontend/` rend ZERO commit — le navigateur ne l'a JAMAIS appelee dans toute
l'histoire du depot — et la chaine est ABSENTE du bundle servi en production.
Les deux seuls appelants sont dans `backend/tests/`, dossier mort et non
deploye, avec un `BASE_URL` vide qui les rend deja inoperants. Aucun parcours
legitime a preserver : c'est la configuration de la porte A.

CE QUE CE LOT NE FAIT PAS. La SELECTION DE CIBLE n'est pas touchee : `find_one`
sans tri reste indetermine quand la personne detient plusieurs forfaits actifs.
C'est un defaut connu, documente, et il appartient a LOT 3c-0c — le corriger
supposerait de passer par `choisir_abonnement` et de rendre le debit atomique,
deux changements de comportement. La verification H8 le PROUVE : elle echouerait
si ce lot y touchait.

AUCUNE BASE REELLE, AUCUN RESEAU.
    python3 tests/test_correctif1_deduct.py
"""
import ast, asyncio, importlib.util, io, os, sys, types, uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from tests._banc_qr import RESULTATS, verifier, _Base, _HTTPException  # noqa: E402

_fa = types.ModuleType("fastapi")
_fa.HTTPException = _HTTPException
_fa.APIRouter = object
_fa.Request = object
sys.modules.setdefault("fastapi", _fa)

_spec = importlib.util.spec_from_file_location(
    "c1_shared", os.path.join(RACINE, "api", "routes", "shared.py"))
SHARED = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SHARED)
sys.modules["api"] = types.ModuleType("api")
sys.modules["api.routes"] = types.ModuleType("api.routes")
sys.modules["api.routes.shared"] = SHARED

SRC_PROMO = io.open(os.path.join(RACINE, "api", "routes", "promo_routes.py"),
                    encoding="utf-8").read()

ADMIN = SHARED.SUPER_ADMIN_EMAILS[0]
ADMIN2 = SHARED.SUPER_ADMIN_EMAILS[1] if len(SHARED.SUPER_ADMIN_EMAILS) > 1 else ADMIN
COACH_B = "coach.b@partenaire.ch"
COACH_C = "coach.c@partenaire.ch"
ABONNE_B = "eleve.b@client.ch"
ABONNE_LEGACY = "eleve.legacy@client.ch"


def _extraire(nom):
    arbre = ast.parse(SRC_PROMO)
    lignes = SRC_PROMO.splitlines(True)
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return "".join(lignes[n.lineno - 1:n.end_lineno])
    raise AssertionError("fonction introuvable : %s" % nom)


class _Journal:
    def __init__(self): self.lignes = []
    def info(self, *a, **k): self.lignes.append(("info", a))
    def warning(self, *a, **k): self.lignes.append(("warning", a))
    def error(self, *a, **k): self.lignes.append(("error", a))


class _Requete:
    """Identite SIGNEE d'un cote, en-tete DECLARE de l'autre — jamais melangees."""
    def __init__(self, signe=None, entete_declare=None):
        self.headers = {}
        if entete_declare:
            self.headers["X-User-Email"] = entete_declare
        self._signe = signe or ""


def _jwt(r):
    """Lit UNIQUEMENT l'identite signee. Ne regarde JAMAIS `X-User-Email` :
    c'est tout l'enjeu du lot. Si la garde retombait sur l'en-tete, H2 casserait."""
    return getattr(r, "_signe", "") or ""


def _monde():
    db = _Base()
    db.coaches.docs = [{"email": ADMIN}, {"email": COACH_B}, {"email": COACH_C}]
    db.coach_auth.docs = []
    db.subscriptions.docs = [
        {"_id": "s1", "id": "sub-B", "code": "BCODE-01", "email": ABONNE_B,
         "coach_id": COACH_B, "status": "active",
         "total_sessions": 10, "used_sessions": 5, "remaining_sessions": 5},
        # Stock ANCIEN sans proprietaire : 13 % des souscriptions en production.
        {"_id": "s2", "id": "sub-LEGACY", "code": "OLD-01", "email": ABONNE_LEGACY,
         "status": "active",
         "total_sessions": 4, "used_sessions": 1, "remaining_sessions": 3},
    ]
    return db


def _ns(db, journal):
    ns = {
        "_db": db, "re": __import__("re"), "uuid": uuid, "asyncio": asyncio,
        "datetime": datetime, "timezone": timezone, "logger": journal,
        "HTTPException": _HTTPException, "SUPER_ADMIN_EMAIL": ADMIN,
        "Request": object, "dict": dict, "str": str,
        "is_super_admin": SHARED.is_super_admin,
        "coach_jwt_email": _jwt,
    }
    exec(compile(_extraire("deduct_session"), "promo_routes.py", "exec"), ns)
    return ns


async def _appeler(ns, corps, requete):
    """Appelle la route sous sa forme CIBLE : `(data, request)`.

    Si la signature ne prend pas encore de requete, on le dit franchement au
    lieu de laisser un `TypeError` brut — c'est precisement le defaut a corriger.
    """
    try:
        return await ns["deduct_session"](corps, requete)
    except TypeError as e:
        if "positional argument" in str(e) or "argument" in str(e):
            raise AssertionError(
                "la route n'accepte pas de `request` — s'y authentifier est "
                "IMPOSSIBLE (%s)" % e)
        raise


async def _refus(titre, corps, requete, ns):
    try:
        await _appeler(ns, corps, requete)
        verifier(titre, False, "ACCEPTE alors qu'il fallait refuser !")
    except _HTTPException as e:
        verifier(titre, e.status_code == 403,
                 "attendu 403, obtenu %s" % e.status_code)
    except AssertionError as e:
        verifier(titre, False, str(e))


def _solde(db, sid):
    for d in db.subscriptions.docs:
        if d.get("id") == sid:
            return (d.get("remaining_sessions"), d.get("used_sessions"))
    return None


async def partie_h_portes():
    db = _monde()
    journal = _Journal()
    ns = _ns(db, journal)
    avant = _solde(db, "sub-B")

    await _refus("H1. anonyme (aucune identite) : refus",
                 {"email": ABONNE_B, "code": "BCODE-01"}, _Requete(), ns)
    await _refus("H2. X-User-Email FORGE valant un vrai coach : refus "
                 "(c'est ce qui distingue un jeton signe d'un en-tete)",
                 {"email": ABONNE_B, "code": "BCODE-01"},
                 _Requete(entete_declare=COACH_B), ns)
    await _refus("H2b. X-User-Email FORGE valant le super-admin : refus",
                 {"email": ABONNE_B, "code": "BCODE-01"},
                 _Requete(entete_declare=ADMIN), ns)
    await _refus("H3. coach signe mais NON proprietaire : refus",
                 {"email": ABONNE_B, "code": "BCODE-01"},
                 _Requete(signe=COACH_C), ns)

    # LA verification qui compte : un refus qui aurait deja decremente ne
    # serait pas un refus.
    verifier("H4. apres les QUATRE refus, le solde est INTACT",
             _solde(db, "sub-B") == avant,
             "avant=%r apres=%r" % (avant, _solde(db, "sub-B")))


async def partie_i_parcours_legitime():
    db = _monde()
    ns = _ns(db, _Journal())

    try:
        await _appeler(ns, {"email": ABONNE_B, "code": "BCODE-01"},
                       _Requete(signe=COACH_B))
        verifier("H5. coach PROPRIETAIRE signe : autorise", True)
        verifier("H5b. ... et le solde baisse d'EXACTEMENT une seance",
                 _solde(db, "sub-B") == (4, 6),
                 "obtenu %r, attendu (4, 6)" % (_solde(db, "sub-B"),))
    except (_HTTPException, AssertionError) as e:
        verifier("H5. coach PROPRIETAIRE signe : autorise", False, str(e))
        verifier("H5b. ... et le solde baisse d'EXACTEMENT une seance", False, "non atteint")

    # Les DEUX adresses de super-admin, pas seulement la premiere : LOT 3c-0b a
    # corrige une ombre locale qui n'en reconnaissait qu'une.
    for i, adr in enumerate((ADMIN, ADMIN2)):
        db2 = _monde()
        ns2 = _ns(db2, _Journal())
        try:
            await _appeler(ns2, {"email": ABONNE_B, "code": "BCODE-01"},
                           _Requete(signe=adr))
            verifier("H6.%d super-admin <%s> : autorise" % (i + 1, adr), True)
        except (_HTTPException, AssertionError) as e:
            verifier("H6.%d super-admin <%s> : autorise" % (i + 1, adr), False, str(e))

    # Le stock ancien reste deductible : le refuser bloquerait le coach sur son
    # PROPRE historique (13 % des souscriptions en production).
    db3 = _monde()
    ns3 = _ns(db3, _Journal())
    try:
        await _appeler(ns3, {"email": ABONNE_LEGACY, "code": "OLD-01"},
                       _Requete(signe=COACH_B))
        verifier("H7. souscription LEGACY sans coach_id : reste deductible "
                 "par un coach signe", _solde(db3, "sub-LEGACY") == (2, 2),
                 "obtenu %r" % (_solde(db3, "sub-LEGACY"),))
    except (_HTTPException, AssertionError) as e:
        verifier("H7. souscription LEGACY sans coach_id : reste deductible "
                 "par un coach signe", False, str(e))


def _code_nu(nom):
    """Le CODE de la fonction, sans commentaires ni docstring.

    Chercher une sous-chaine dans le source BRUT donne des faux negatifs : un
    commentaire qui EXPLIQUE pourquoi on n'utilise pas `choisir_abonnement`
    contient le mot `choisir_abonnement`. On veut savoir ce que la fonction
    FAIT, pas ce qu'elle raconte. `ast.unparse` jette les commentaires ; on
    retire la docstring a la main.
    """
    arbre = ast.parse(_extraire(nom))
    fonction = arbre.body[0]
    corps = list(fonction.body)
    if corps and isinstance(corps[0], ast.Expr) \
            and isinstance(corps[0].value, ast.Constant) \
            and isinstance(corps[0].value.value, str):
        corps = corps[1:]
    fonction.body = corps or [ast.Pass()]
    return ast.unparse(arbre)


def partie_j_perimetre():
    """Le lot ferme une porte. Il ne recompte rien, il ne migre rien."""
    corps = _code_nu("deduct_session")
    prose = _extraire("deduct_session")

    verifier("H8. la regle de SELECTION n'a pas bouge : ni tri, ni "
             "choisir_abonnement, ni $inc introduits (c'est LOT 3c-0c)",
             ".sort(" not in corps and "choisir_abonnement" not in corps
             and "$inc" not in corps)
    verifier("H8b. aucune ecriture de masse ni migration : ni update_many, "
             "ni delete_many, ni create_index",
             "update_many" not in corps and "delete_many" not in corps
             and "create_index" not in corps)
    verifier("H8c. aucun montant touche : `offer_price` absent",
             "offer_price" not in corps)
    verifier("H9. la garde lit un jeton SIGNE (`coach_jwt_email`)",
             "coach_jwt_email" in corps)
    verifier("H9b. ... et JAMAIS l'en-tete declare ni le repli transitoire",
             "X-User-Email" not in corps and "require_auth" not in corps)
    verifier("H10. la signature accepte enfin une requete HTTP — sans elle, "
             "s'authentifier etait impossible",
             "request: Request" in prose)
    verifier("H11. le journal nomme desormais l'APPELANT, pas seulement la "
             "victime", "par {caller}" in corps)


async def principal():
    await partie_h_portes()
    await partie_i_parcours_legitime()
    partie_j_perimetre()

    ok = sum(1 for _, c, _ in RESULTATS if c)
    print("\n" + "=" * 74)
    print("CORRECTIF 1 — LA CINQUIEME PORTE EST FERMEE")
    print("=" * 74)
    for nom, cond, detail in RESULTATS:
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom,
                              "" if cond or not detail else "\n          -> %s" % detail))
    print("-" * 74)
    print("Souscriptions / seances REELLES : 0 — base en memoire")
    print("%d / %d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(principal()))
