# -*- coding: utf-8 -*-
"""LOT 3b — L'AVANTAGE MEMBRE. Verifications hors ligne, sans base ni reseau.

CE QUE CE LOT PROMET, ET QUE CES TESTS VERROUILLENT
---------------------------------------------------
1. UN MEMBRE PAIE MOINS, MAIS SEULEMENT S'IL EST MEMBRE **A LA DATE DE LA
   SEANCE**. Pas « aujourd'hui » : la seance du 10/01/2027 est jugee au
   10/01/2027 (partie 2). Une adhesion expiree ou pas encore commencee ne
   donne RIEN — plein tarif, jamais une erreur.
2. UNE SEULE REMISE S'APPLIQUE, la plus avantageuse pour le client, et en cas
   d'EGALITE c'est le membre qui gagne (partie 3, scenarios A a J du
   proprietaire).
3. ON N'ACHETE PAS SON ADHESION AU TARIF MEMBRE. `creates_membership: True`
   -> aucun avantage (partie 1). C'est la regle bloquante : un PULSE 250
   brade passerait sous la borne de LOT 2.1 et l'adhesion disparaitrait en
   silence.
4. LE POURCENTAGE APPLIQUE EST FIGE dans la reservation (partie 4). Le coach
   peut passer de 50 % a 30 % demain : cette reservation-ci gardera 50.
5. LE LOT N'ECRIT JAMAIS UNE ADHESION et ne touche a aucun moteur de prix
   existant (partie 5). Il lit `memberships`, il ne l'ecrit pas.
6. AUCUN ORACLE : la route d'estimation n'accepte AUCUN e-mail, le checkout
   exige un jeton d'appareil signe QUI DESIGNE L'ACHETEUR (partie 6).
7. LE NAVIGATEUR PROPOSE, LE SERVEUR DISPOSE. Une date qui ne correspond a
   aucune occurrence REELLE du cours interroge est rejetee — date falsifiee
   (H) comme occurrence empruntee a un autre cours (I) (partie 7).
8. L'ADHESION DU COACH B NE PAIE JAMAIS CHEZ LE COACH A (partie 8, scenario
   J). Le filtre vient de `p1a_filtre_proprietaire`, importe et jamais recopie.
9. LE FORFAIT N'EST PAS DOUBLEMENT FACTURE (partie 9, scenario K) : un membre
   qui consomme une seance de son PULSE x10 ne paie RIEN de plus.
10. LE DRAPEAU ETEINT REND LE SITE D'AVANT, au pixel et au centime — serveur
   ET navigateur, panne de lecture comprise (partie 10).
11. LA REOUVERTURE DU CHOIX DE DATE EST UNE BRECHE, PAS UNE PORTE : quatre
   conditions cumulatives, les deux verrous conserves (partie 11).

    python3 tests/test_lot3b_avantage_membre.py
"""
import ast
import asyncio
import importlib.util
import io
import os
import sys
import types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

_ok = _ko = 0


def verifier(titre, condition, detail=""):
    global _ok, _ko
    if condition:
        _ok += 1
        print("  OK     " + titre)
    else:
        _ko += 1
        print(" ECHEC   " + titre + ("   -> " + str(detail) if detail else ""))


# ═══════════════ chargement du VRAI code, hors ligne ════════════════════════
# Meme technique que `tests/test_lot3a_snapshot.py` : `fastapi` et `api.server`
# sont des bouchons, les modules sont charges PAR CHEMIN. Aucun import de
# `api.server` (il ouvrirait une connexion MongoDB), aucun reseau.
class _Routeur(object):
    def __init__(self, *a, **k):
        pass

    def _deco(self, *a, **k):
        return lambda f: f
    get = post = put = delete = _deco


class _HTTPException(Exception):
    def __init__(self, status_code=400, detail=""):
        self.status_code = status_code
        self.detail = detail


_fa = types.ModuleType("fastapi")
_fa.APIRouter = _Routeur
_fa.HTTPException = _HTTPException
_fa.Request = object
_fa.Header = _fa.Query = _fa.Depends = lambda *a, **k: None
sys.modules["fastapi"] = _fa
sys.modules["api"] = types.ModuleType("api")
sys.modules["api.routes"] = types.ModuleType("api.routes")
_srv = types.ModuleType("api.server")
_srv.db = None
_srv.DEFAULT_COACH_ID = "coach@defaut"
_srv.is_super_admin = lambda e: False
_srv._v311_coach_email_from_jwt = lambda r: ""
sys.modules["api.server"] = _srv


def _charger(nom, *chemin):
    spec = importlib.util.spec_from_file_location(nom, os.path.join(RACINE, *chemin))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nom] = mod
    spec.loader.exec_module(mod)
    return mod


S = _charger("api.routes.shared", "api", "routes", "shared.py")
# `lot3b_couverture` importe `p1a_statut` DEPUIS ce module : la regle de dates
# de P1-bis-a est reutilisee, jamais recopiee. On charge donc le VRAI module.
M = _charger("api.routes.membership_routes", "api", "routes", "membership_routes.py")

# Faux Mongo asynchrone du depot (`tests/_banc_qr.py`), pour les deux seules
# fonctions `async` touchees ici.
from tests._banc_qr import _Base, _Collection  # noqa: E402
import tests._banc_qr as BQ  # noqa: E402


def _src(*chemin):
    return io.open(os.path.join(RACINE, *chemin), encoding="utf-8").read()


SHARED_SRC = _src("api", "routes", "shared.py")
SERVER_SRC = _src("api", "server.py")
SHARED_ARBRE = ast.parse(SHARED_SRC)
SERVER_ARBRE = ast.parse(SERVER_SRC)


def _fonction(arbre, source, nom):
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return ast.get_source_segment(source, n) or ""
    return ""


def _corps_sans_docstring(arbre, source, nom):
    """Le CODE d'une fonction, docstring exclue. Une docstring qui EXPLIQUE une
    convention n'est pas une seconde lecture de cette convention."""
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            _corps = n.body
            if _corps and isinstance(_corps[0], ast.Expr) \
                    and isinstance(getattr(_corps[0], "value", None), ast.Constant) \
                    and isinstance(_corps[0].value.value, str):
                _corps = _corps[1:]
            return "\n".join(ast.get_source_segment(source, s) or "" for s in _corps)
    return ""


def _classe(arbre, nom):
    for n in ast.walk(arbre):
        if isinstance(n, ast.ClassDef) and n.name == nom:
            return n
    return None


def _champs_de_classe(arbre, nom):
    noeud = _classe(arbre, nom)
    if noeud is None:
        return None
    champs = set()
    for n in noeud.body:
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            champs.add(n.target.id)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    champs.add(t.id)
    return champs


# Le bloc LOT 3b de shared.py : du titre de section jusqu'a la fin du fichier.
_DEBUT_3B = SHARED_SRC.find("LOT 3b — L'AVANTAGE MEMBRE")
BLOC_3B = SHARED_SRC[_DEBUT_3B:] if _DEBUT_3B > 0 else ""


# `lot3b_occurrences_prouvees` importe TROIS garanties de LOT 1 depuis
# `api/routes/reservation_routes.py`. Ce fichier ne s'importe pas hors ligne
# (il exige `pydantic`), on rejoue donc la technique de `tests/_banc_qr.py` :
# les fonctions REELLES sont extraites du VRAI source et exécutées dans un
# module minimal. Rien n'est recopie — si LOT 1 change, ce test change avec.
class _Silence(object):
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass


def _module_reservation_routes():
    from datetime import datetime as _dt
    mod = types.ModuleType("api.routes.reservation_routes")
    ns = mod.__dict__
    ns.update({"datetime": _dt, "logger": _Silence(), "dict": dict,
               "str": str, "int": int})
    # les constantes de module dont dependent les fonctions extraites
    for n in ast.walk(BQ.ARBRE):
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in (
                "LOT1_PREFIXE", "LOT1_NON_VALEURS", "A1_JOURS_JS"):
            exec(compile("".join(BQ.LIGNES[n.lineno - 1:n.end_lineno]),
                         BQ.FICHIER, "exec"), ns)
    for nom in ("lot1_occurrence_iso", "_a1_jour_js", "_a1_a_lieu_aujourdhui"):
        exec(compile(BQ.extraire(nom), BQ.FICHIER, "exec"), ns)
    sys.modules["api.routes.reservation_routes"] = mod
    return mod


RR = _module_reservation_routes()

APP_SRC = _src("frontend", "src", "App.js")
RESA_SRC = _src("api", "routes", "reservation_routes.py")
CHECKOUT_SRC = _src("api", "routes", "checkout_routes.py")

# Le predicat de reouverture, decoupe du VRAI App.js.
_I_PRED = APP_SRC.find("const lot3bChoixDateRequis")
_F_PRED = APP_SRC.find("\n  };", _I_PRED) if _I_PRED > 0 else -1
PREDICAT_JS = APP_SRC[_I_PRED:_F_PRED] if _I_PRED > 0 and _F_PRED > 0 else ""


def _si_drapeau_checkout():
    """Le `if _l3b_on:` de `create_checkout_session`, en tant que NOEUD."""
    for n in ast.walk(SERVER_ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and n.name == "create_checkout_session":
            for m in ast.walk(n):
                if isinstance(m, ast.If) and isinstance(m.test, ast.Name) \
                        and m.test.id == "_l3b_on":
                    return ast.get_source_segment(SERVER_SRC, m) or ""
    return ""


# ═══════════════ 1. L'AVANTAGE DE L'OFFRE ═══════════════════════════════════
def partie_1_avantage_de_l_offre():
    print("\n=== 1. L'AVANTAGE SE LIT SUR L'OFFRE, ET DANS LE DOUTE IL VAUT 0 ===")
    A = S.lot3b_avantage_de_l_offre

    verifier("1a. champ ABSENT -> 0.0 (aucune migration, aucun backfill)",
             A({"id": "offre-1", "name": "Silent"}) == 0.0)
    verifier("1b. 50 -> 50.0", A({"member_discount_pct": 50}) == 50.0)
    verifier("1c. 30.5 -> 30.5 (les demi-pourcents sont acceptes)",
             A({"member_discount_pct": 30.5}) == 30.5)

    for valeur, libelle in ((0, "zero"), (-10, "negatif"), (100, "cent"),
                            (120, "au-dela de cent"), ("abc", "illisible"),
                            (None, "None")):
        verifier("1d. %s -> 0.0 (bornes STRICTES ]0, 100[)" % libelle,
                 A({"member_discount_pct": valeur}) == 0.0,
                 str(A({"member_discount_pct": valeur})))

    verifier("1e. offre vide / None / liste -> 0.0",
             A({}) == 0.0 and A(None) == 0.0 and A([1, 2]) == 0.0)

    # LA REGLE BLOQUANTE DU PROPRIETAIRE.
    verifier("1f. `creates_membership: True` -> 0.0 : ON N'ACHETE PAS SON "
             "ADHESION AU TARIF MEMBRE (PULSE 250 protege)",
             A({"member_discount_pct": 50, "creates_membership": True}) == 0.0,
             "un prix brade passerait sous la borne LOT 2.1 -> adhesion "
             "supprimee en silence")
    verifier("1g. ... et la garde porte sur True STRICT, pas sur une chaine",
             A({"member_discount_pct": 50, "creates_membership": False}) == 50.0)

    verifier("1h. `isProduct: True` -> 0.0 (boutique hors perimetre V1)",
             A({"member_discount_pct": 50, "isProduct": True}) == 0.0)
    verifier("1i. `isPhysicalProduct: True` -> 0.0 (TVA et port composent le "
             "prix ailleurs que dans `price`)",
             A({"member_discount_pct": 50, "isPhysicalProduct": True}) == 0.0)

    verifier("1j. le nom du champ est celui declare par le lot",
             S.LOT3B_CHAMP_AVANTAGE == "member_discount_pct")


# ═══════════════ 2. LA COUVERTURE PAR LES DATES ═════════════════════════════
ADH = {"id": "adh-1", "email": "marie@test.ch", "date_debut": "2026-01-01",
       "date_fin": "2026-12-31", "coach_id": None}


def partie_2_couverture():
    print("\n=== 2. C'EST LA DATE DE LA SEANCE QUI DECIDE, PAS LA DATE DU JOUR ===")
    C = S.lot3b_couverture
    liste = [ADH]

    verifier("2a. seance du 19/08/2026 -> COUVERTE",
             (C(liste, "2026-08-19") or {}).get("id") == "adh-1")
    verifier("2b. seance du 10/01/2027 -> NON couverte (membre expire)",
             C(liste, "2027-01-10") is None,
             "l'exemple exact du cahier des charges")
    verifier("2c. seance du 31/12/2025 -> NON couverte (membre pas encore "
             "commence)", C(liste, "2025-12-31") is None)

    verifier("2d. le PREMIER jour est INCLUS",
             (C(liste, "2026-01-01") or {}).get("id") == "adh-1")
    verifier("2e. le DERNIER jour est INCLUS — « valable jusqu'au 31 decembre » "
             "veut dire le 31 aussi",
             (C(liste, "2026-12-31") or {}).get("id") == "adh-1")

    verifier("2f. un horodatage complet est accepte (troncature a [:10])",
             (C(liste, "2026-08-19T18:30:00") or {}).get("id") == "adh-1")
    verifier("2g. ... et le lendemain de la fin, horodate, reste NON couvert",
             C(liste, "2027-01-01T09:00:00") is None)

    for valeur, libelle in (("hier", "date illisible"), ("", "vide"),
                            (None, "None"), ("2026-08", "tronquee"),
                            (12345, "non-chaine")):
        verifier("2h. %s -> None (jamais un rabais devine)" % libelle,
                 C(liste, valeur) is None, str(C(liste, valeur)))

    # Plusieurs adhesions : c'est CELLE QUI COUVRE qui est rendue, pas la
    # premiere de la liste — sinon le `membership_id` fige serait faux.
    trois = [
        {"id": "vieille", "date_debut": "2024-01-01", "date_fin": "2024-12-31"},
        {"id": "future", "date_debut": "2027-01-01", "date_fin": "2027-12-31"},
        {"id": "bonne", "date_debut": "2026-06-01", "date_fin": "2026-09-30"},
    ]
    verifier("2i. parmi trois adhesions, c'est CELLE QUI COUVRE qui est rendue",
             (C(trois, "2026-08-19") or {}).get("id") == "bonne",
             str(C(trois, "2026-08-19")))
    verifier("2j. aucune ne couvre -> None",
             C(trois, "2025-03-01") is None)
    verifier("2k. une liste vide, None, ou des elements non-dict -> None "
             "(ne leve jamais)",
             C([], "2026-08-19") is None and C(None, "2026-08-19") is None
             and C(["texte", None], "2026-08-19") is None)

    # La fonction est PURE : aucune base ne lui est passee.
    import inspect
    params = list(inspect.signature(C).parameters)
    verifier("2l. la fonction est PURE — elle ne recoit aucune base",
             params == ["adhesions", "occurrence_iso"], str(params))


async def partie_2bis_lecture():
    print("\n=== 2bis. LA LECTURE D'ADHESION NE LEVE JAMAIS, ET RESTE SYMETRIQUE ===")
    base = _Base()
    base.memberships = _Collection([
        dict(ADH, email="marie@test.ch", coach_id=None),
        dict(ADH, id="adh-partenaire", email="marie@test.ch",
             coach_id="partenaire@exemple.com"),
    ])

    sans = await S.lot3b_adhesions(base, "Marie@Test.CH", None)
    verifier("2m. l'e-mail est normalise, et un contexte SANS proprietaire ne "
             "voit que le stock sans proprietaire",
             [a["id"] for a in sans] == ["adh-1"], str([a["id"] for a in sans]))

    chez_lui = await S.lot3b_adhesions(base, "marie@test.ch",
                                       "partenaire@exemple.com")
    verifier("2n. un partenaire ne voit QUE ses adhesions (regle 2c8a831, "
             "importee et jamais recopiee)",
             [a["id"] for a in chez_lui] == ["adh-partenaire"],
             str([a["id"] for a in chez_lui]))

    tiers = await S.lot3b_adhesions(base, "marie@test.ch", "autre@coach.ch")
    verifier("2o. un coach tiers ne voit rien (fail closed)", tiers == [])

    verifier("2p. sans e-mail -> aucune adhesion, aucune requete",
             await S.lot3b_adhesions(base, "", None) == []
             and await S.lot3b_adhesions(base, None, None) == [])

    class _BasePanne(object):
        def __getitem__(self, nom):
            raise RuntimeError("Atlas injoignable")

    verifier("2q. base illisible -> [] et AUCUNE exception : une panne donne le "
             "PLEIN TARIF, jamais une erreur au moment de payer",
             await S.lot3b_adhesions(_BasePanne(), "marie@test.ch", None) == [])

    verifier("2r. `lot3b_adhesion_a_la_date` compose les deux, et juge A LA DATE",
             (await S.lot3b_adhesion_a_la_date(base, "marie@test.ch", None,
                                               "2026-08-19") or {}).get("id") == "adh-1"
             and await S.lot3b_adhesion_a_la_date(base, "marie@test.ch", None,
                                                  "2027-01-10") is None)


# ═══════════════ 3. L'ARBITRAGE — LES SCENARIOS DU PROPRIETAIRE ═════════════
def _membre(base_unitaire, quantite, couvertes, pct):
    """Le total membre, calcule comme l'appelant le calcule (checkout et
    estimation partagent la MEME formule) : les dates non couvertes restent au
    plein tarif."""
    return (base_unitaire * (quantite - couvertes)
            + base_unitaire * (1 - pct / 100.0) * couvertes)


def partie_3_arbitrage():
    print("\n=== 3. UNE SEULE REMISE S'APPLIQUE : LA MEILLEURE POUR LE CLIENT ===")
    R = S.lot3b_arbitrer

    a = R(30, 30, total_membre=None, pct_membre=0, promo_type=None)
    verifier("3A. non-membre, offre a 30 -> 30, raison `public`",
             a["total"] == 30 and a["raison"] == "public"
             and a["avantage_pct"] is None, str(a))

    b = R(30, 30, total_membre=15, pct_membre=50, promo_type=None)
    verifier("3B. membre 50 % -> 15, raison `membre`, avantage 50 fige",
             b["total"] == 15 and b["raison"] == "membre"
             and b["avantage_pct"] == 50.0, str(b))

    # C et D : l'adhesion ne couvre pas la date -> l'appelant passe None.
    c = R(30, 30, total_membre=None, pct_membre=50, promo_type=None)
    verifier("3C. adhesion EXPIREE a la date -> 30, plein tarif",
             c["total"] == 30 and c["raison"] == "public"
             and c["avantage_pct"] is None, str(c))
    d = R(30, 30, total_membre=None, pct_membre=50, promo_type=None)
    verifier("3D. adhesion pas encore COMMENCEE -> 30, plein tarif",
             d["total"] == 30 and d["raison"] == "public", str(d))

    e = R(30, 30, total_membre=21, pct_membre=30, promo_type=None)
    verifier("3E. membre 30 % -> 21", e["total"] == 21
             and e["raison"] == "membre" and e["avantage_pct"] == 30.0, str(e))

    f = R(30, 24, total_membre=15, pct_membre=50, promo_type="%")
    verifier("3F. membre 50 % CONTRE promo 20 % -> le MEMBRE gagne (15)",
             f["total"] == 15 and f["raison"] == "membre", str(f))

    g = R(30, 9, total_membre=15, pct_membre=50, promo_type="%")
    verifier("3G. membre 50 % CONTRE promo 70 % -> la PROMO gagne (9), et "
             "aucun `avantage_pct` n'est fige",
             g["total"] == 9 and g["raison"] == "promo"
             and g["avantage_pct"] is None, str(g))

    h = R(30, 15, total_membre=15, pct_membre=50, promo_type="%")
    verifier("3H. EGALITE 50/50 -> LE MEMBRE gagne (regle du proprietaire)",
             h["total"] == 15 and h["raison"] == "membre"
             and h["avantage_pct"] == 50.0, str(h))

    # ---- GARDE C1 : un code `100%` est un FORFAIT PAYE, jamais une promo ----
    i1 = R(30, 0.0, total_membre=None, pct_membre=0, promo_type="100%")
    verifier("3I. GARDE C1 — `promo_type=\"100%\"` -> raison `forfait`, "
             "JAMAIS `promo`",
             i1["raison"] == "forfait" and i1["total"] == 0.0, str(i1))
    i2 = R(30, 0.0, total_membre=15, pct_membre=50, promo_type="100%")
    verifier("3I2. ... meme quand un avantage membre existe et perd "
             "l'arbitrage", i2["raison"] == "forfait", str(i2))
    i3 = R(30, 24, total_membre=None, pct_membre=0, promo_type="CHF")
    verifier("3I3. une remise en CHF reellement appliquee reste `promo`",
             i3["raison"] == "promo" and i3["total"] == 24, str(i3))
    i4 = R(30, 30, total_membre=None, pct_membre=0, promo_type="%")
    verifier("3I4. un code qui ne baisse RIEN n'est pas une promo -> `public`",
             i4["raison"] == "public", str(i4))
    i5 = R(30, 24, total_membre=None, pct_membre=0, promo_type="parrainage")
    verifier("3I5. un type de remise hors vocabulaire n'est pas comparable "
             "-> `public`", i5["raison"] == "public", str(i5))
    verifier("3I6. le vocabulaire des remises comparables est FERME, sans "
             "`100%`", tuple(S.LOT3B_PROMOS_COMPARABLES) == ("%", "CHF"),
             str(S.LOT3B_PROMOS_COMPARABLES))

    # ---- GARDE C2 : un avantage ne rend jamais gratuit, ni ne majore ----
    j1 = R(0.004, 0.004, total_membre=0.002, pct_membre=50, promo_type=None)
    verifier("3J. GARDE C2 — un total membre qui s'arrondit a 0 est REFUSE : "
             "retour au plein tarif (sinon le droit d'essai brule et LOT 2.1 "
             "refuse l'adhesion)",
             j1["raison"] == "public" and j1["total"] == 0.004
             and j1["avantage_pct"] is None, str(j1))
    j2 = R(30, 30, total_membre=35, pct_membre=50, promo_type=None)
    verifier("3J2. GARDE C2 — un total membre SUPERIEUR au plein tarif est "
             "refuse : un avantage qui majore n'est pas un avantage",
             j2["raison"] == "public" and j2["total"] == 30, str(j2))
    j3 = R(30, 30, total_membre=15, pct_membre=100, promo_type=None)
    verifier("3J3. un pourcentage a 100 n'ouvre aucun avantage",
             j3["raison"] == "public", str(j3))
    j4 = R(30, 30, total_membre=15, pct_membre=0, promo_type=None)
    verifier("3J4. un pourcentage a 0 non plus", j4["raison"] == "public", str(j4))
    j5 = R(0, 0, total_membre=0, pct_membre=50, promo_type=None)
    verifier("3J5. une base a 0 (offre gratuite) n'est jamais « remisee »",
             j5["raison"] == "public", str(j5))
    j6 = R("abc", 30, total_membre=15, pct_membre=50)
    verifier("3J6. une base illisible -> `inconnu` et AUCUN total invente",
             j6["total"] is None and j6["raison"] == "inconnu", str(j6))
    j7 = R(30, 30, total_membre="abc", pct_membre=50)
    verifier("3J7. un total membre illisible -> plein tarif, pas d'exception",
             j7["raison"] == "public" and j7["total"] == 30, str(j7))

    # ---- LE PANIER MULTI-DATES : la seule lecture honnete de la validite ----
    base_unitaire, qte, couvertes, pct = 30.0, 3, 1, 50
    total = _membre(base_unitaire, qte, couvertes, pct)
    verdict = R(base_unitaire * qte, base_unitaire * qte,
                total_membre=total, pct_membre=pct, promo_type=None)
    verifier("3K. PANIER — 3 seances dont UNE SEULE couverte : 2 pleins tarifs "
             "+ 1 tarif membre = 75, et non 45",
             verdict["total"] == 75.0 and verdict["raison"] == "membre"
             and total == 30 + 30 + 15, str(verdict))
    verdict3 = R(90, 90, total_membre=_membre(30.0, 3, 3, 50), pct_membre=50)
    verifier("3K2. les TROIS couvertes -> 45", verdict3["total"] == 45.0)
    verdict0 = R(90, 90, total_membre=None, pct_membre=50)
    verifier("3K3. AUCUNE couverte -> 90, plein tarif",
             verdict0["total"] == 90 and verdict0["raison"] == "public")

    # La fonction est PURE : aucune base, aucun e-mail, aucune offre.
    import inspect
    params = list(inspect.signature(R).parameters)
    verifier("3L. l'arbitre est PUR — ni base, ni offre, ni identite",
             params == ["base", "total_promo", "total_membre", "pct_membre",
                        "promo_type"], str(params))


# ═══════════════ 4. LE SNAPSHOT LOT 3a, ETENDU ══════════════════════════════
def partie_4_snapshot():
    print("\n=== 4. LE POURCENTAGE APPLIQUE EST FIGE, COMME LE MONTANT ===")
    verifier("4a. `membre` appartient desormais au vocabulaire FERME",
             "membre" in S.LOT3_RAISONS, str(S.LOT3_RAISONS))
    verifier("4b. ... et le vocabulaire n'a gagne QUE ce mot",
             set(S.LOT3_RAISONS) == {"public", "promo", "membre", "forfait",
                                     "essai", "offert", "inconnu"},
             str(S.LOT3_RAISONS))

    s = S.lot3_snapshot_tarifaire(15, "membre", tarif_public=30,
                                  avantage_pct=50, membership_id="x")
    verifier("4c. le snapshot membre pose les SEPT champs attendus",
             s.get("tarif_applique") == 15.0 and s.get("tarif_raison") == "membre"
             and s.get("tarif_public") == 30.0
             and s.get("tarif_avantage_pct") == 50.0
             and s.get("tarif_membership_id") == "x"
             and s.get("tarif_devise") == "CHF" and "tarif_fige_le" in s, str(s))
    verifier("4d. le document reste PLAT (aucune valeur imbriquee)",
             all(not isinstance(v, (dict, list)) for v in s.values()), str(s))

    plein = S.lot3_snapshot_tarifaire(30, "public", tarif_public=30)
    verifier("4e. sur un achat PLEIN TARIF, les deux cles membre sont ABSENTES "
             "— pas a None, ABSENTES",
             "tarif_avantage_pct" not in plein
             and "tarif_membership_id" not in plein, str(plein))

    for valeur, libelle in ((0, "zero"), (100, "cent"), (120, "au-dela"),
                            (-5, "negatif"), ("abc", "illisible")):
        _s = S.lot3_snapshot_tarifaire(15, "membre", avantage_pct=valeur)
        verifier("4f. un avantage %s n'est PAS ecrit (bornes ]0, 100[)" % libelle,
                 "tarif_avantage_pct" not in _s, str(_s))

    _s = S.lot3_snapshot_tarifaire(15, "membre", membership_id="")
    verifier("4g. un `membership_id` vide n'est pas ecrit non plus",
             "tarif_membership_id" not in _s, str(_s))
    _s = S.lot3_snapshot_tarifaire(15, "membre", membership_id="i" * 200)
    verifier("4h. le `membership_id` est borne a 64 caracteres",
             len(_s["tarif_membership_id"]) == 64)

    verifier("4i. le vocabulaire reste FERME : une raison inconnue retombe sur "
             "`inconnu`",
             S.lot3_snapshot_tarifaire(15, "cadeau")["tarif_raison"] == "inconnu"
             and S.lot3_snapshot_tarifaire(15, "MEMBRE")["tarif_raison"] == "membre")

    # L'enveloppe qui ne leve jamais transmet bien les deux nouveaux arguments.
    e = S.lot3_champs_achat(15, "membre", tarif_public=30, avantage_pct=50,
                            membership_id="adh-1")
    verifier("4j. `lot3_champs_achat` (l'enveloppe des points d'ecriture) "
             "transmet les deux nouvelles cles",
             e.get("tarif_avantage_pct") == 50.0
             and e.get("tarif_membership_id") == "adh-1", str(e))

    # Le pourcentage FIGE est celui de l'achat, pas celui de l'offre du jour :
    # la preuve, deux snapshots successifs avec deux pourcentages differents.
    hier = S.lot3_snapshot_tarifaire(15, "membre", tarif_public=30, avantage_pct=50)
    demain = S.lot3_snapshot_tarifaire(21, "membre", tarif_public=30, avantage_pct=30)
    verifier("4k. le coach passe de 50 % a 30 % : l'achat d'hier garde 50",
             hier["tarif_avantage_pct"] == 50.0
             and demain["tarif_avantage_pct"] == 30.0)


# ═══════════════ 5. PERIMETRE ET NON-REGRESSION ═════════════════════════════
def partie_5_perimetre():
    print("\n=== 5. LE LOT LIT LES ADHESIONS, IL N'EN ECRIT AUCUNE ===")
    verifier("5a. le bloc LOT 3b de shared.py existe", bool(BLOC_3B))

    ecritures = []
    for n in ast.walk(SHARED_ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and n.name.startswith("lot3b_"):
            corps = ast.get_source_segment(SHARED_SRC, n) or ""
            for op in ("insert_one", "update_one", "update_many", "delete_one",
                       "delete_many", "replace_one", "find_one_and_update"):
                if op in corps:
                    ecritures.append("%s -> %s" % (n.name, op))
    verifier("5b. AUCUNE fonction `lot3b_` n'ecrit en base — LOT 2 / 2.1 "
             "restent seuls maitres de l'adhesion",
             not ecritures, str(ecritures))
    verifier("5c. le bloc entier ne contient aucune ecriture Mongo",
             not any(op in BLOC_3B for op in
                     ("insert_one", "update_one", "delete_one", "delete_many",
                      "replace_one")))
    verifier("5d. il LIT bien `memberships` (sinon le lot ne servirait a rien)",
             'db["memberships"]' in BLOC_3B)

    # Aucun pourcentage code en dur : le pourcentage vient TOUJOURS de l'offre.
    motifs = ("* 0.5", "*0.5", "/ 2 ", "0.50", "50 /", "* 50", "/ 100", "0.7 *")
    trouves = [m for m in motifs if m in BLOC_3B]
    constantes = set()
    for n in ast.walk(SHARED_ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and n.name.startswith("lot3b_"):
            for m in ast.walk(n):
                if isinstance(m, ast.BinOp) and isinstance(m.op, (ast.Mult, ast.Div)):
                    for cote in (m.left, m.right):
                        if isinstance(cote, ast.Constant) and \
                                isinstance(cote.value, (int, float)):
                            constantes.add(float(cote.value))
    verifier("5e. aucun pourcentage code en dur dans le bloc LOT 3b "
             "(la seule constante multiplicative est le passage en centimes "
             "de la garde C2)",
             not trouves and constantes <= {100.0},
             "motifs=%s constantes=%s" % (trouves, sorted(constantes)))

    # `api/pricing.py` : le module a risque financier direct, intact.
    pricing = _src("api", "pricing.py")
    arbre_p = ast.parse(pricing)
    sig = None
    for n in ast.walk(arbre_p):
        if isinstance(n, ast.FunctionDef) and n.name == "compute_active_price":
            sig = [a.arg for a in n.args.args]
    verifier("5f. `compute_active_price` garde sa signature `(offer, now=None)` "
             "— il ne connait ni l'acheteur ni la base",
             sig == ["offer", "now"], str(sig))
    verifier("5g. `api/pricing.py` ne nomme ni adhesion, ni e-mail, ni base, "
             "ni LOT 3b",
             not any(mot in pricing for mot in
                     ("memberships", "lot3b", "member_discount", "email", "db.")),
             "le rabais membre y ferait passer des offres sous la borne LOT 2.1")

    # LOT 2 / LOT 2.1 : la creation d'adhesion et sa borne de prix, intactes.
    for nom in ("lot2_creer_adhesion_apres_achat", "lot2_prix_de_vente"):
        corps = _fonction(SHARED_ARBRE, SHARED_SRC, nom)
        verifier("5h. `%s` existe et ignore totalement LOT 3b" % nom,
                 bool(corps) and not any(mot in corps for mot in
                                         ("lot3b", "LOT3B", "member_discount",
                                          "avantage")),
                 "un rabais applique ici supprimerait des adhesions en silence")

    # La symetrie Offer / OfferCreate — le piege repete six fois du depot.
    offre = _champs_de_classe(SERVER_ARBRE, "Offer") or set()
    offre_create = _champs_de_classe(SERVER_ARBRE, "OfferCreate") or set()
    verifier("5i. `member_discount_pct` est declare dans `Offer` ET dans "
             "`OfferCreate` (sinon efface a chaque PUT /offers)",
             "member_discount_pct" in offre and "member_discount_pct" in offre_create,
             "Offer=%s OfferCreate=%s" % ("member_discount_pct" in offre,
                                          "member_discount_pct" in offre_create))
    verifier("5j. ses deux voisins soumis a la meme symetrie y sont toujours",
             {"creates_membership", "first_purchase_eligible"} <= offre
             and {"creates_membership", "first_purchase_eligible"} <= offre_create)

    # Le coupe-circuit, aux QUATRE endroits.
    flags = _champs_de_classe(SERVER_ARBRE, "FeatureFlags") or set()
    flags_maj = _champs_de_classe(SERVER_ARBRE, "FeatureFlagsUpdate") or set()
    lecture = _fonction(SERVER_ARBRE, SERVER_SRC, "get_feature_flags")
    verifier("5k. `MEMBER_PRICING_ENABLED` est declare dans `FeatureFlags`",
             "MEMBER_PRICING_ENABLED" in flags)
    verifier("5l. ... et dans `FeatureFlagsUpdate` (sinon impossible a basculer)",
             "MEMBER_PRICING_ENABLED" in flags_maj)
    verifier("5m. ... et dans le dict de creation par defaut",
             '"MEMBER_PRICING_ENABLED": False' in lecture)
    verifier("5n. ... et dans le tuple de completion a la lecture (sinon "
             "absent de la reponse, donc invisible par curl)",
             '("MEMBER_PRICING_ENABLED", False)' in lecture)
    verifier("5o. le defaut est FALSE aux quatre endroits : le lot est "
             "invisible tant que le proprietaire ne l'allume pas",
             lecture.count("MEMBER_PRICING_ENABLED") == 2
             and "MEMBER_PRICING_ENABLED: bool = False" in SERVER_SRC)

    # Option A du proprietaire : la route de reservation n'est PAS touchee.
    resa = _src("api", "routes", "reservation_routes.py")
    verifier("5p. `POST /api/reservations` n'a PAS ete touchee : aucun symbole "
             "`lot3b_` dans reservation_routes.py",
             "lot3b" not in resa and "LOT3B" not in resa,
             "option A du proprietaire")

    # Le front n'affiche encore rien de ce lot cote reservation directe.
    verifier("5q. LOT 3a n'a pas ete casse : ses cinq fonctions existent "
             "toujours",
             all(hasattr(S, f) for f in
                 ("lot3_snapshot_tarifaire", "lot3_raison_du_droit",
                  "lot3_snapshot_du_forfait", "lot3_champs_forfait",
                  "lot3_champs_achat")))
    verifier("5r. et un snapshot de forfait sans avantage reste identique "
             "a LOT 3a",
             S.lot3_snapshot_du_forfait(
                 {"seances_a_l_achat": 10, "montant_encaisse": 250.0,
                  "origine_paiement": "stripe", "code": "AFR-1"},
                 {"code": "AFR-1", "maxUses": 10, "total_paid": 250}
             ).get("tarif_applique") == 25.0)


# ═══════════════ 6. SECURITE ════════════════════════════════════════════════
def partie_6_securite():
    print("\n=== 6. AUCUN ORACLE, AUCUN TARIF MEMBRE SANS JETON SIGNE ===")
    champs = _champs_de_classe(SERVER_ARBRE, "Lot3bEstimationRequest")
    verifier("6a. le modele d'estimation existe", champs is not None, str(champs))
    # LOT 3b — L'ASSERTION EST RETOURNEE, ET RENFORCEE.
    #
    # Elle exigeait « aucun e-mail en entree », pour qu'on ne puisse pas
    # demander « est-ce que telle adresse est membre ? ». Le champ
    # `customerEmail` a ete ajoute depuis — mais il ne SERT QU'A UNE EGALITE
    # avec l'e-mail du jeton que l'appelant detient deja. La reponse ne lui
    # apprend donc rien : il connait sa propre adresse. Ce qu'il faut prouver
    # n'est plus « aucun e-mail », c'est « cet e-mail n'interroge RIEN ».
    #
    # Il est necessaire : sans lui, un membre connecte qui reserve pour un
    # tiers voyait le tarif membre et etait debite du plein tarif — l'ecran
    # promettait ce que la caisse n'aurait pas tenu.
    verifier("6b. le SEUL e-mail accepte est celui de l'acheteur, et il ne "
             "sert qu'a une egalite (aucun oracle)",
             champs is not None
             and sorted(c for c in champs
                        if "mail" in c.lower()) == ["customerEmail"],
             str(sorted(champs or [])))
    verifier("6c. il n'accepte pas davantage un code d'abonnement ni un "
             "membership_id",
             champs is not None and not any(
                 c.lower() in ("code", "subscribercode", "membershipid",
                               "membership_id") for c in champs),
             str(sorted(champs or [])))

    route = _fonction(SERVER_ARBRE, SERVER_SRC, "lot3b_estimation_tarifaire")
    verifier("6b2. ... il est compare a l'e-mail du JETON, jamais utilise "
             "pour interroger la base",
             "_acheteur != _email" in route
             and "corps.customerEmail" in route
             and not any(
                 f"{_r}(corps.customerEmail" in route
                 for _r in ("find_one", "find", "lot3b_adhesions")))
    verifier("6b3. ... et sans jeton valide il est purement IGNORE : la "
             "reponse reste le prix public",
             route.find("identification_requise")
             < route.find("_acheteur"))
    verifier("6b4. la meme regle qu'a la caisse : on n'achete pas au tarif "
             "membre pour quelqu'un d'autre",
             "_l3b_achete_pour_soi" in SERVER_SRC
             and "acheteur_different" in route)
    verifier("6d. l'identite de la route vient du JETON D'APPAREIL SIGNE, et "
             "de lui seul",
             "subscriber_from_request as _jeton" in route
             and '(_tok or {}).get("email")' in route, "")
    verifier("6e. sans jeton, la reponse est le PRIX PUBLIC — jamais une "
             "erreur, qui serait deja une information",
             '_reponse["identification_requise"] = True' in route
             and "return _reponse" in route)
    verifier("6f. le drapeau eteint court-circuite la route",
             'get("MEMBER_PRICING_ENABLED")' in route)
    verifier("6g. la charge est bornee (429), sur une cle qui ne designe que "
             "l'appelant lui-meme",
             "_lot3b_debit_ok" in route and "429" in route)
    verifier("6h. aucune regex MongoDB construite depuis une entree "
             "utilisateur dans la route", "$regex" not in route)

    checkout = _fonction(SERVER_ARBRE, SERVER_SRC, "create_checkout_session")
    verifier("6i. le checkout exige `subscriber_from_request` (jeton signe "
             "V296), jamais `customerEmail` seul",
             "subscriber_from_request as _l3b_jeton" in checkout)
    verifier("6j. ... et le jeton doit DESIGNER L'ACHETEUR : l'e-mail du jeton "
             "est compare a `customerEmail`",
             "_l3b_email == _l3b_mail(request.customerEmail)" in checkout,
             "un membre ne paie pas les seances d'un tiers a son tarif")
    verifier("6k. l'avantage n'est evalue QUE si les deux conditions sont "
             "reunies",
             "if _l3b_pct_offre > 0 and _l3b_achete_pour_soi:" in checkout)
    verifier("6l. tout le bloc est sous `try` : un avantage qui echoue rend le "
             "PLEIN TARIF, jamais une erreur de paiement",
             "[LOT3b] avantage membre non evalue" in checkout
             and "except Exception as _l3b_err" in checkout)
    verifier("6m. le drapeau eteint neutralise le bloc du checkout",
             "_l3b_on = bool((await get_feature_flags())" in checkout
             and "if _l3b_on:" in checkout)
    verifier("6n. les dates du navigateur sont REVALIDEES par le serveur",
             "_l3b_occurrences(" in checkout,
             "sinon il suffirait d'envoyer une date situee dans son adhesion")
    verifier("6o. le pourcentage applique est FIGE dans le snapshot de l'achat",
             "avantage_pct=_lot3b_pct" in checkout
             and "membership_id=_lot3b_membership_id" in checkout)

    verifier("6p. aucune regex MongoDB construite depuis une entree "
             "utilisateur dans le bloc LOT 3b de shared.py",
             "$regex" not in BLOC_3B)
    verifier("6q. la lecture d'adhesion filtre par EGALITE STRICTE sur "
             "l'e-mail normalise",
             '_requete["email"] = _email' in BLOC_3B
             and "normaliser_email(email)" in BLOC_3B)



# ═══════════════ 7. LA SECURITE DE L'OCCURRENCE ════════════════════
# Le navigateur PROPOSE une date, le serveur DISPOSE. Sans cette revalidation,
# il suffirait d'envoyer une date situee a l'interieur de son adhesion pour
# obtenir le tarif membre sur une seance qui n'a pas lieu ce jour-la.
#
# 2026-08-26, 09-02, 09-09, 09-16, 09-23 et 09-30 sont des MERCREDIS ;
# 2026-08-27 est un JEUDI ; 2026-09-15 est un MARDI.
MER = ("2026-08-26", "2026-09-02", "2026-09-09", "2026-09-16", "2026-09-23",
       "2026-09-30")
JEU = "2026-08-27"


def _base_cours():
    base = _Base()
    base.courses = _Collection([
        # recurrent, MERCREDI (convention JavaScript : Dim=0 -> Mer=3)
        {"id": "cours-mer", "name": "Silent Mercredi", "weekday": 3,
         "time": "18:30", "visible": True, "archived": False},
        # recurrent, JEUDI
        {"id": "cours-jeu", "name": "Silent Jeudi", "weekday": 4,
         "time": "19:00", "visible": True, "archived": False},
        # PONCTUEL : `date` est prioritaire sur `weekday` (regle A1)
        {"id": "cours-ponctuel", "name": "Masterclass", "date": "2026-09-15",
         "weekday": 3, "time": "19:00", "visible": True, "archived": False},
        # archive : il ne doit plus prouver aucune date
        {"id": "cours-archive", "name": "Ancien", "weekday": 3,
         "time": "18:30", "visible": True, "archived": True},
    ])
    return base


async def partie_7_occurrence():
    print("\n=== 7. LE NAVIGATEUR PROPOSE, LE SERVEUR DISPOSE (dates H et I) ===")
    O = S.lot3b_occurrences_prouvees
    base = _base_cours()

    verifier("7a. une date REELLE du cours est prouvee",
             await O(base, "cours-mer", [MER[0] + "T18:30:00"])
             == [MER[0] + "T18:30:00"],
             str(await O(base, "cours-mer", [MER[0] + "T18:30:00"])))

    # ---- H. LA DATE FALSIFIEE ----
    h1 = await O(base, "cours-mer", [JEU + "T18:30:00"])
    verifier("7H1. DATE FALSIFIEE — un JEUDI envoye sur un cours du MERCREDI "
             "est REJETE (sinon il suffisait de viser une date interieure a "
             "son adhesion)", h1 == [], str(h1))
    h2 = await O(base, "cours-ponctuel", ["2026-09-16T19:00:00"])
    verifier("7H2. DATE FALSIFIEE — un cours PONCTUEL du 15/09 ne prouve pas "
             "le 16/09", h2 == [], str(h2))
    h3 = await O(base, "cours-ponctuel", ["2026-09-15T19:00:00"])
    verifier("7H3. ... et il prouve bien SA date a lui",
             h3 == ["2026-09-15T19:00:00"], str(h3))
    h4 = await O(base, "cours-ponctuel", [MER[1] + "T19:00:00"])
    verifier("7H4. ... meme si ce jour-la tombe un mercredi : `date` est "
             "PRIORITAIRE sur `weekday`, un ponctuel n'a pas lieu chaque "
             "semaine", h4 == [], str(h4))
    h5 = await O(base, "cours-mer", [JEU + "T18:30:00", MER[0] + "T18:30:00"])
    verifier("7H5. dans un panier mixte, SEULE la date reelle survit",
             h5 == [MER[0] + "T18:30:00"], str(h5))

    # ---- I. L'OCCURRENCE D'UN AUTRE COURS ----
    i1 = await O(base, "cours-mer", [JEU + "T19:00:00"])
    verifier("7I1. OCCURRENCE D'UN AUTRE COURS — la date est valide pour le "
             "cours B (jeudi), on interroge le cours A (mercredi) : REJETEE",
             i1 == [], str(i1))
    i2 = await O(base, "cours-jeu", [JEU + "T19:00:00"])
    verifier("7I2. ... et la MEME date, posee sur SON cours, est acceptee",
             i2 == [JEU + "T19:00:00"], str(i2))
    i3 = await O(base, "cours-jeu", [MER[0] + "T18:30:00"])
    verifier("7I3. ... symetriquement, la date du cours A sur le cours B est "
             "rejetee", i3 == [], str(i3))

    # ---- LE COURS LUI-MEME ----
    verifier("7b. `courseId` inexistant -> liste vide (donc PLEIN TARIF)",
             await O(base, "cours-fantome", [MER[0] + "T18:30:00"]) == [])
    verifier("7c. `courseId` vide / None -> liste vide, aucune requete",
             await O(base, "", [MER[0] + "T18:30:00"]) == []
             and await O(base, None, [MER[0] + "T18:30:00"]) == [])
    verifier("7d. cours ARCHIVE -> liste vide : on ne brade pas une seance "
             "qui n'existe plus",
             await O(base, "cours-archive", [MER[0] + "T18:30:00"]) == [])

    # ---- LES GARANTIES DE LOT 1, REUTILISEES ET NON RECOPIEES ----
    d1 = await O(base, "cours-mer", [MER[0]])
    verifier("7e. une DATE SEULE (\u00ab 2026-08-26 \u00bb, sans heure) est REJETEE — "
             "LOT 1 refuse de RECONSTRUIRE une heure", d1 == [], str(d1))
    d2 = await O(base, "cours-mer", [MER[0] + "T18"])
    verifier("7f. une date tronquee (\u00ab ...T18 \u00bb) est rejetee de meme",
             d2 == [], str(d2))
    for valeur, libelle in (("hier", "illisible"), ("", "vide"), (None, "None"),
                            (12345, "non-chaine"), ("2026-13-45T18:30:00",
                                                    "mois/jour impossibles")):
        r = await O(base, "cours-mer", [valeur])
        verifier("7g. date %s -> aucune date prouvee (jamais un rabais devine)"
                 % libelle, r == [], str(r))
    verifier("7h. une liste de dates vide / None -> liste vide",
             await O(base, "cours-mer", []) == []
             and await O(base, "cours-mer", None) == [])

    # ---- LE PLAFOND ET LES DOUBLONS ----
    six = [j + "T18:30:00" for j in MER]          # six mercredis REELS
    p = await O(base, "cours-mer", six)
    verifier("7i. PLAFOND — six dates envoyees, cinq au plus retenues "
             "(meme borne que `safe_quantity`, V225)",
             len(p) == 5 and p == six[:5], str(p))
    d = await O(base, "cours-mer", [six[0], six[0], six[1], six[0]])
    verifier("7j. DOUBLONS — la meme date envoyee trois fois n'est comptee "
             "qu'une fois (sinon le panier paierait un tarif membre trois "
             "fois sur une seule seance)",
             d == [six[0], six[1]], str(d))
    mix = await O(base, "cours-mer", [six[0], JEU + "T18:30:00", six[0],
                                      "", None, six[1]])
    verifier("7k. plafond, doublons et rejets se composent sans lever",
             mix == [six[0], six[1]], str(mix))

    # ---- LA CONVENTION `weekday` JAVASCRIPT, LE PIEGE HISTORIQUE (A1) ----
    verifier("7l. CONVENTION JS (Dim=0) — `weekday: 3` accepte un MERCREDI",
             await O(base, "cours-mer", [MER[3] + "T18:30:00"])
             == [MER[3] + "T18:30:00"])
    verifier("7m. ... et REFUSE un JEUDI. En convention Python (Lun=0), 3 "
             "vaudrait jeudi : c'est exactement le decalage d'un cran que A1 "
             "a supprime", await O(base, "cours-mer", [JEU + "T19:00:00"]) == [])
    verifier("7n. ... `weekday: 4` accepte le JEUDI, et refuse le mercredi",
             await O(base, "cours-jeu", [JEU + "T19:00:00"]) == [JEU + "T19:00:00"]
             and await O(base, "cours-jeu", [MER[0] + "T18:30:00"]) == [])

    # ---- LA PANNE ----
    class _BasePanne(object):
        def __getitem__(self, nom):
            raise RuntimeError("Atlas injoignable")

    verifier("7o. PANNE DE BASE -> liste vide et AUCUNE exception : le client "
             "paie le PLEIN TARIF, il ne voit pas une erreur au moment de payer",
             await O(_BasePanne(), "cours-mer", [MER[0] + "T18:30:00"]) == [])

    class _CoursIllisible(object):
        def __getitem__(self, nom):
            class _C(object):
                async def find_one(self, *a, **k):
                    raise RuntimeError("curseur casse")
            return _C()

    verifier("7p. ... idem si c'est la LECTURE du cours qui echoue",
             await O(_CoursIllisible(), "cours-mer", [MER[0] + "T18:30:00"]) == [])

    # ---- LA PREUVE QUE LOT 1 EST IMPORTE, PAS RECOPIE ----
    corps = _fonction(SHARED_ARBRE, SHARED_SRC, "lot3b_occurrences_prouvees")
    verifier("7q. la revalidation IMPORTE les garanties de LOT 1 / A1 au lieu "
             "de les reecrire",
             "from api.routes.reservation_routes import" in corps
             and "lot1_occurrence_iso" in corps
             and "_a1_a_lieu_aujourdhui" in corps and "_a1_jour_js" in corps)
    verifier("7r. ... et n'interprete JAMAIS `weekday` elle-meme (la "
             "docstring l'EXPLIQUE, le code ne le LIT pas)",
             "weekday" not in _corps_sans_docstring(
                 SHARED_ARBRE, SHARED_SRC, "lot3b_occurrences_prouvees"),
             "une seconde lecture de la convention JS ferait renaitre le "
             "decalage d'un cran")
    verifier("7s. elle ne lit que `courses`, et n'ecrit rien",
             'db["courses"]' in corps
             and not any(op in corps for op in
                         ("insert_one", "update_one", "delete_one")))


# ═══════════════ 8. CROSS-COACH (scenario J) ══════════════════════
def _base_adhesions():
    base = _Base()
    base.memberships = _Collection([
        {"id": "sans-none", "email": "marie@test.ch", "coach_id": None,
         "date_debut": "2026-01-01", "date_fin": "2026-12-31"},
        {"id": "sans-vide", "email": "marie@test.ch", "coach_id": "",
         "date_debut": "2026-01-01", "date_fin": "2026-12-31"},
        {"id": "sans-absent", "email": "marie@test.ch",
         "date_debut": "2026-01-01", "date_fin": "2026-12-31"},
        {"id": "chez-a", "email": "marie@test.ch", "coach_id": "coach-a@x.ch",
         "date_debut": "2026-01-01", "date_fin": "2026-12-31"},
        {"id": "chez-b", "email": "marie@test.ch", "coach_id": "coach-b@x.ch",
         "date_debut": "2026-01-01", "date_fin": "2026-12-31"},
        {"id": "autre-personne", "email": "jean@test.ch",
         "coach_id": "coach-a@x.ch",
         "date_debut": "2026-01-01", "date_fin": "2026-12-31"},
    ])
    return base


async def partie_8_cross_coach():
    print("\n=== 8. L'ADHESION DU COACH B NE PAIE JAMAIS CHEZ LE COACH A ===")
    base = _base_adhesions()

    async def _ids(coach_id, email="marie@test.ch"):
        return sorted(a["id"] for a in await S.lot3b_adhesions(base, email, coach_id))

    a = await _ids("coach-a@x.ch")
    verifier("8J1. CROSS-COACH — chez le coach A, l'adhesion ouverte chez le "
             "coach B est INVISIBLE",
             a == ["chez-a"] and "chez-b" not in a, str(a))
    b = await _ids("coach-b@x.ch")
    verifier("8J2. ... et symetriquement chez le coach B",
             b == ["chez-b"], str(b))
    verifier("8J3. ... aucun des deux ne voit le stock SANS proprietaire",
             not any(i.startswith("sans-") for i in a + b), str(a + b))

    sans = await _ids(None)
    verifier("8a. le contexte SANS proprietaire voit les TROIS formes de "
             "\u00ab sans proprietaire \u00bb : None, chaine vide, champ absent",
             sans == ["sans-absent", "sans-none", "sans-vide"], str(sans))
    verifier("8b. ... et JAMAIS le catalogue d'un partenaire",
             "chez-a" not in sans and "chez-b" not in sans, str(sans))
    verifier("8c. `\"\"` et `None` designent le meme contexte sans proprietaire",
             await _ids("") == sans and await _ids("   ") == sans)

    verifier("8d. le proprietaire est normalise (casse, espaces) : "
             "\u00ab Coach-A@X.ch \u00bb reste le coach A",
             await _ids("  Coach-A@X.ch  ") == ["chez-a"])
    verifier("8e. un coach TIERS ne voit rien du tout (fail closed)",
             await _ids("coach-c@x.ch") == [])
    verifier("8f. l'adhesion d'une AUTRE personne ne remonte jamais, meme "
             "chez le bon coach",
             "autre-personne" not in a
             and await _ids("coach-a@x.ch", "jean@test.ch") == ["autre-personne"])

    # LA PREUVE QUE LE FILTRE EST IMPORTE, ET NON RECOPIE : on remplace la
    # vraie fonction par un espion et on verifie qu'elle est REELLEMENT appelee.
    _appels = []
    _vrai = M.p1a_filtre_proprietaire

    def _espion(coach_id):
        _appels.append(coach_id)
        return _vrai(coach_id)

    M.p1a_filtre_proprietaire = _espion
    try:
        await S.lot3b_adhesions(base, "marie@test.ch", "coach-a@x.ch")
    finally:
        M.p1a_filtre_proprietaire = _vrai
    verifier("8g. PREUVE VIVANTE — la regle de propriete vient de "
             "`p1a_filtre_proprietaire`, appele a l'execution",
             _appels == ["coach-a@x.ch"], str(_appels))

    verifier("8h. ... et le source l'IMPORTE explicitement",
             "from api.routes.membership_routes import p1a_filtre_proprietaire"
             in BLOC_3B)
    verifier("8i. ... sans jamais reconstruire le filtre a la main : ni `$or`, "
             "ni liste de \u00ab sans proprietaire \u00bb dans le bloc LOT 3b",
             "$or" not in BLOC_3B and "P1A_SANS_PROPRIETAIRE" not in BLOC_3B
             and '{"coach_id"' not in BLOC_3B)

    verifier("8j. la regle indisponible -> aucune adhesion, donc PLEIN TARIF "
             "(fail closed, jamais un rabais par defaut)",
             "regle de propriete indisponible" in BLOC_3B
             and "return []" in BLOC_3B)

    # Le coach de l'offre est resolu par `lot2_proprietaire`, aux DEUX
    # appelants : c'est ce qui garantit la symetrie du filtre cote serveur.
    for nom in ("lot3b_estimation_tarifaire", "create_checkout_session"):
        corps = _fonction(SERVER_ARBRE, SERVER_SRC, nom)
        verifier("8k. `%s` resout le proprietaire de l'OFFRE (`lot2_proprietaire`), "
                 "jamais celui de l'acheteur" % nom,
                 "lot2_proprietaire" in corps
                 and ('_offer.get("coach_id")' in corps
                      or '_offre.get("coach_id")' in corps), nom)


# ══════════ 9. LE FORFAIT N'EST PAS DOUBLEMENT FACTURE (K) ══════════
def partie_9_forfait():
    print("\n=== 9. UN MEMBRE QUI CONSOMME UNE SEANCE DE SON PULSE x10 NE "
          "PAIE RIEN DE PLUS ===")
    espace = _fonction(SERVER_ARBRE, SERVER_SRC, "reserve_course_from_space")
    verifier("9a. le chemin \u00ab espace abonne \u00bb existe et ecrit bien "
             "`source: subscriber_space`",
             bool(espace) and '"source": "subscriber_space"' in espace)
    verifier("9K1. il ecrit `price: 0.0` ET `totalPrice: 0.0` — consommer une "
             "seance de son forfait ne declenche AUCUN encaissement",
             '"price": 0.0' in espace and '"totalPrice": 0.0' in espace)
    verifier("9K2. LOT 3b n'y a pas mis les pieds : aucun symbole `lot3b_`, "
             "`LOT3B` ni `MEMBER_PRICING` dans ce chemin",
             not any(mot in espace for mot in
                     ("lot3b", "LOT3B", "MEMBER_PRICING", "member_discount")),
             "un avantage membre applique ici facturerait une seance DEJA payee")
    verifier("9K3. la trace tarifaire y est celle du FORFAIT "
             "(`lot3_champs_forfait`), jamais celle d'un achat",
             "lot3_champs_forfait" in espace
             and "lot3_champs_achat" not in espace)

    verifier("9K4. `reservation_routes.py` (POST /reservations, scan QR) "
             "ignore totalement LOT 3b",
             not any(mot in RESA_SRC for mot in
                     ("lot3b", "LOT3B", "MEMBER_PRICING")))
    verifier("9K5. `checkout_routes.py` aussi",
             not any(mot in CHECKOUT_SRC for mot in
                     ("lot3b", "LOT3B", "MEMBER_PRICING")))

    # LA RAISON TARIFAIRE D'UNE SEANCE DE FORFAIT, VERIFIEE EN L'APPELANT.
    # Le PULSE x10 du proprietaire : 250 CHF encaisses pour 10 seances.
    # `seances_a_l_achat` est le denominateur fige a l'achat (lot B), jamais
    # `total_sessions` que la reconduction incremente.
    sub = {"id": "sub-1", "code": "AFR-PULSE", "email": "marie@test.ch",
           "seances_a_l_achat": 10, "montant_encaisse": 250.0,
           "origine_paiement": "stripe",
           "total_sessions": 10, "remaining_sessions": 7}
    code = {"code": "AFR-PULSE", "maxUses": 10, "total_paid": 250.0,
            "origine_paiement": "stripe"}
    raison = S.lot3_raison_du_droit(sub, code)
    verifier("9K6. une souscription PAYEE donne la raison `forfait`",
             raison == "forfait", str(raison))
    verifier("9K7. ... et JAMAIS `membre` : l'avantage membre porte sur "
             "l'ACHAT du forfait, pas sur chacune de ses seances",
             raison != "membre"
             and S.lot3_raison_du_droit(sub, None) != "membre"
             and S.lot3_raison_du_droit(None, code) != "membre")
    verifier("9K8. le mot `membre` n'apparait meme pas dans la fonction",
             "membre" not in _fonction(SHARED_ARBRE, SHARED_SRC,
                                       "lot3_raison_du_droit"))

    # Le snapshot ecrit sur cette seance porte le prix REELLEMENT paye a
    # l'achat (250 / 10 = 25), et aucune cle d'avantage membre.
    snap = S.lot3_champs_forfait(sub, code, None)
    verifier("9K9. la seance vaut 250/10 = 25 CHF (le prix D'ACHAT du pack), "
             "et le document ne porte AUCUNE cle d'avantage membre",
             snap.get("tarif_applique") == 25.0
             and snap.get("tarif_raison") == "forfait"
             and "tarif_avantage_pct" not in snap
             and "tarif_membership_id" not in snap, str(snap))
    verifier("9K10. CONCLUSION — un membre qui consomme une seance de son "
             "PULSE x10 ne paie RIEN de plus : prix 0, raison `forfait`, "
             "aucun tarif membre applique une seconde fois",
             snap.get("tarif_raison") == "forfait"
             and '"totalPrice": 0.0' in espace
             and "lot3b" not in espace)


# ══════════════ 10. LE DRAPEAU, DANS LES DEUX POSITIONS ═════════════
def partie_10_drapeau():
    print("\n=== 10. DRAPEAU ETEINT = LE SITE D'AVANT, AU PIXEL ET AU CENTIME ===")
    # --- le defaut, dans le modele ---
    noeud = _classe(SERVER_ARBRE, "FeatureFlags")
    defaut = None
    for n in (noeud.body if noeud else []):
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) \
                and n.target.id == "MEMBER_PRICING_ENABLED":
            defaut = getattr(n.value, "value", "absent")
    verifier("10a. `MEMBER_PRICING_ENABLED` vaut FALSE par defaut dans "
             "`FeatureFlags` — le lot naît eteint", defaut is False, str(defaut))

    # --- le checkout : TOUT le bloc est sous `if _l3b_on:` ---
    checkout = _fonction(SERVER_ARBRE, SERVER_SRC, "create_checkout_session")
    dedans = _si_drapeau_checkout()
    verifier("10b. le `if _l3b_on:` du checkout existe et n'est pas vide",
             len(dedans) > 500, str(len(dedans)))
    verifier("10c. TOUTE lecture d'adhesion est DEDANS : hors du `if`, il ne "
             "reste que les deux affectations du drapeau lui-meme",
             checkout.count("_l3b_") - dedans.count("_l3b_") == 2,
             "hors du if : %d occurrences"
             % (checkout.count("_l3b_") - dedans.count("_l3b_")))
    for symbole in ("_l3b_lire_adhesions", "_l3b_occurrences", "_l3b_arbitrer",
                    "_l3b_jeton", "_l3b_avantage"):
        verifier("10d. `%s` n'existe QUE sous le drapeau allume" % symbole,
                 symbole in dedans
                 and checkout.count(symbole) == dedans.count(symbole))
    verifier("10e. DRAPEAU ETEINT = `_v429_total` INCHANGE : sa seule "
             "reaffectation LOT 3b est a l'interieur du `if`",
             '_v429_total = float(_l3b_verdict["total"])' in dedans
             and checkout.count('_v429_total = float(_l3b_verdict')
             == dedans.count('_v429_total = float(_l3b_verdict') == 1)
    verifier("10f. ... et les trois variables de trace naissent a None AVANT "
             "le bloc : eteint, la reservation n'ecrit aucune cle membre",
             "_lot3b_raison = None" in checkout
             and "_lot3b_pct = None" in checkout
             and "_lot3b_membership_id = None" in checkout)

    # --- la route d'estimation : reponse publique AVANT toute lecture ---
    route = _fonction(SERVER_ARBRE, SERVER_SRC, "lot3b_estimation_tarifaire")
    i_court = route.find("if not _actif:")
    i_lire = route.find("lot3b_adhesions as _lire_adhesions")
    i_appel = route.find("await _lire_adhesions(")
    verifier("10g. la route d'estimation REND la reponse publique avant toute "
             "lecture d'adhesion quand le drapeau est eteint",
             0 < i_court < i_lire and i_court < i_appel,
             "court-circuit=%d import=%d appel=%d" % (i_court, i_lire, i_appel))
    verifier("10h. ... et ce qu'elle rend alors est bien le PRIX PUBLIC, pas "
             "une erreur",
             "return _reponse" in route[i_court:i_court + 120]
             and '"votre_tarif": round(_base, 2)' in route[:i_court])

    # --- la panne de lecture du drapeau vaut ETEINT, aux DEUX endroits ---
    verifier("10i. PANNE — dans le checkout, un drapeau illisible vaut ETEINT "
             "(`except` -> `_l3b_on = False`)",
             "except Exception:" in checkout and "_l3b_on = False" in checkout
             and checkout.find("except Exception:") < checkout.find("_l3b_on = False"))
    verifier("10j. PANNE — dans l'estimation, idem (`_actif = False`)",
             "_actif = False" in route
             and route.find("except Exception:") < route.find("_actif = False"))
    verifier("10k. ... la panne n'est JAMAIS une decision tarifaire "
             "(lecon V310c, commentee dans le code)",
             "la panne ne doit pas devenir une decision" in checkout)

    # --- cote navigateur ---
    verifier("10l. NAVIGATEUR — `lot3bChoixDateRequis` commence par le "
             "drapeau : eteint, le parcours d'achat ne bouge pas d'un pixel",
             PREDICAT_JS.split("\n")[1].strip()
             == "if (!memberPricingEnabled || !offer) return false;",
             PREDICAT_JS.split("\n")[1].strip())
    verifier("10m. NAVIGATEUR — l'etat naît a `false`",
             "useState(false);" in APP_SRC[
                 APP_SRC.find("const [memberPricingEnabled"):
                 APP_SRC.find("const [memberPricingEnabled") + 160])
    verifier("10n. NAVIGATEUR — le drapeau est lu sur la requete "
             "`/feature-flags` DEJA existante (aucun appel reseau ajoute)",
             "setMemberPricingEnabled(response.data?.MEMBER_PRICING_ENABLED || false)"
             in APP_SRC and APP_SRC.count("axios.get(`${API}/feature-flags`)") == 1)
    verifier("10o. NAVIGATEUR — l'ECHEC de lecture des drapeaux pose "
             "`setMemberPricingEnabled(false)`",
             "setMemberPricingEnabled(false);" in APP_SRC)
    _bloc_catch = APP_SRC[APP_SRC.find("Feature flags not available"):
                          APP_SRC.find("Feature flags not available") + 400]
    verifier("10p. ... et c'est bien dans le `catch`, pas ailleurs",
             "setMemberPricingEnabled(false);" in _bloc_catch, _bloc_catch[:80])


# ═══════════ 11. LE PREDICAT DE REOUVERTURE EST ETROIT ════════════
def partie_11_predicat():
    print("\n=== 11. LA REOUVERTURE DU CHOIX DE DATE EST UNE BRECHE, PAS UNE "
          "PORTE ===")
    verifier("11a. le predicat existe dans App.js", bool(PREDICAT_JS))

    conditions = (
        ("1. le drapeau est allume", "!memberPricingEnabled"),
        ("2. l'offre est PAYANTE", "v223UnitPrice(offer) > 0"),
        ("3. elle porte un AVANTAGE membre",
         "parseFloat(offer.member_discount_pct)"),
        ("4. elle est LIEE a des cours", "offer.linked_course_ids"),
    )
    for libelle, motif in conditions:
        verifier("11b. condition cumulative %s -> presente" % libelle,
                 motif in PREDICAT_JS, motif)
    verifier("11c. les QUATRE conditions sortent chacune par `return false;` "
             "— elles sont CUMULATIVES, pas alternatives",
             PREDICAT_JS.count("return false;") == 4,
             str(PREDICAT_JS.count("return false;")))
    verifier("11d. la condition 4 exige une liste NON VIDE",
             "linked_course_ids.length === 0" in PREDICAT_JS
             and "Array.isArray(offer.linked_course_ids)" in PREDICAT_JS)
    verifier("11e. une CINQUIEME garde ferme la breche d'une grille VIDE : au "
             "moins un cours lie doit etre reellement affichable",
             "courses.some(" in PREDICAT_JS
             and "c.visible !== false" in PREDICAT_JS
             and "c.archived !== true" in PREDICAT_JS,
             "sinon le visiteur devrait choisir une date inexistante et ne "
             "pourrait PLUS acheter du tout")

    # --- VERROU 1 : l'achat direct est CONSERVE pour tout le reste ---
    #
    # IL Y A DEUX AIGUILLAGES, PAS UN. Le test navigateur l'a prouve a nos
    # depens : `handleSelectOffer` avait ete corrige, mais le bouton
    # « Réserver » de la carte testait encore `v225IsDirectCheckout` SEUL et
    # court-circuitait le formulaire. L'ecran etait donc juste et inatteignable
    # par le CTA principal. On exige desormais la condition AUX DEUX endroits.
    verrou = "if (v225IsDirectCheckout(offer) && !lot3bChoixDateRequis(offer)) {"
    verifier("11f. VERROU 1 — l'achat direct est CONDITIONNE, jamais supprime",
             verrou in APP_SRC, "la condition doit etre `&& !lot3bChoixDateRequis`")
    verifier("11f2. ... et la condition est posee sur LES DEUX aiguillages "
             "(le bouton « Réserver » ET handleSelectOffer)",
             APP_SRC.count(verrou) == 2, str(APP_SRC.count(verrou)))
    _apres = APP_SRC[APP_SRC.rfind(verrou):APP_SRC.rfind(verrou) + 220]
    verifier("11g. ... et handleSelectOffer appelle toujours "
             "`startProgressiveCheckout` puis sort : toutes les autres offres "
             "gardent le parcours d'avant",
             "startProgressiveCheckout(offer, 1);" in _apres
             and "return;" in _apres, _apres[:120])
    _bouton = APP_SRC[APP_SRC.find(verrou):APP_SRC.find(verrou) + 220]
    verifier("11g2. ... et le bouton de la carte passe par `v226BuyDirect`, "
             "le point d'entree unique de l'achat direct",
             "v226BuyDirect();" in _bouton, _bouton[:120])
    verifier("11g3. ... lequel se garde LUI AUSSI, pour qu'aucun appelant ne "
             "puisse contourner la regle par inadvertance",
             "if (lot3bChoixDateRequis(offer)) return;" in APP_SRC)
    verifier("11h. `startProgressiveCheckout` n'a pas ete supprime du fichier",
             APP_SRC.count("startProgressiveCheckout") >= 3,
             str(APP_SRC.count("startProgressiveCheckout")))
    verifier("11i. le point de decision historique `v225IsDirectCheckout` est "
             "toujours le premier terme du verrou (aucune redérivation a la "
             "main)", verrou.startswith("if (v225IsDirectCheckout(offer)"))

    # --- VERROU 2 : showSessions derive du predicat ---
    verifier("11j. VERROU 2 — `showSessions` n'est plus `false` EN DUR",
             "const showSessions = false" not in APP_SRC)
    verifier("11k. ... il derive du MEME predicat, applique a l'offre active",
             "const showSessions = lot3bChoixDateRequis(activeOffer);" in APP_SRC)
    verifier("11l. ... et il n'existe qu'UNE seule definition de `showSessions`",
             APP_SRC.count("const showSessions =") == 1,
             str(APP_SRC.count("const showSessions =")))

    # --- LE CALCUL HISTORIQUE V225, TOUJOURS LA ET TOUJOURS NON CONSOMME ---
    verifier("11m. le calcul historique `showSessionsLegacy` (V225) est "
             "TOUJOURS present — aucune suppression de code",
             "const showSessionsLegacy =" in APP_SRC)
    verifier("11n. ... et TOUJOURS non consomme : il n'apparait qu'une fois, "
             "a sa declaration (aucune regression de lisibilite, aucune "
             "seconde autorite sur l'affichage)",
             APP_SRC.count("showSessionsLegacy") == 1,
             str(APP_SRC.count("showSessionsLegacy")))
    verifier("11o. ... et il reste explicitement marque comme non utilise",
             "eslint-disable-next-line no-unused-vars" in APP_SRC[
                 APP_SRC.find("const showSessionsLegacy") - 200:
                 APP_SRC.find("const showSessionsLegacy")])

    # --- LE PREDICAT EST APPELE AUX DEUX VERROUS, ET NULLE PART AILLEURS ---
    # Le predicat est RELAYE (prop) jusqu'au bouton, jamais REDERIVE. Compter
    # les occurrences serait fragile ; ce qui compte est qu'il n'existe qu'UNE
    # definition, et qu'aucun autre endroit ne recalcule la regle a la main.
    verifier("11p. le predicat n'a qu'UNE definition",
             APP_SRC.count("const lot3bChoixDateRequis = (offer) =>") == 1,
             str(APP_SRC.count("const lot3bChoixDateRequis = (offer) =>")))
    verifier("11p2. il est RELAYE en prop, avec un defaut qui preserve "
             "l'existant pour tout appelant qui ne le passe pas",
             APP_SRC.count("lot3bChoixDateRequis = () => false") == 2,
             str(APP_SRC.count("lot3bChoixDateRequis = () => false")))
    verifier("11p3. la regle n'est REDERIVEE nulle part : `member_discount_pct` "
             "n'est compare qu'a l'interieur du predicat",
             APP_SRC.count("member_discount_pct") == 1
             and "member_discount_pct" in PREDICAT_JS,
             str(APP_SRC.count("member_discount_pct")))

# ══════════════════════════════ execution ═══════════════════════════════════
def principal():
    partie_1_avantage_de_l_offre()
    partie_2_couverture()
    asyncio.get_event_loop().run_until_complete(partie_2bis_lecture())
    partie_3_arbitrage()
    partie_4_snapshot()
    partie_5_perimetre()
    partie_6_securite()
    _boucle = asyncio.get_event_loop()
    _boucle.run_until_complete(partie_7_occurrence())
    _boucle.run_until_complete(partie_8_cross_coach())
    partie_9_forfait()
    partie_10_drapeau()
    partie_11_predicat()


def rapport():
    print("\n" + "=" * 74)
    print("LOT 3b — L'AVANTAGE MEMBRE : LA DATE DECIDE, LE MEILLEUR TARIF GAGNE")
    print("=" * 74)
    print("%d / %d verifications au vert" % (_ok, _ok + _ko))
    return _ko == 0


if __name__ == "__main__":
    principal()
    sys.exit(0 if rapport() else 1)
