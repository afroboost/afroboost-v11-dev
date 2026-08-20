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
    verifier("6b. il n'accepte AUCUN e-mail : personne ne peut demander "
             "« est-ce que telle adresse est membre ? »",
             champs is not None and not any(
                 "email" in c.lower() or "mail" in c.lower() for c in champs),
             str(sorted(champs or [])))
    verifier("6c. il n'accepte pas davantage un code d'abonnement ni un "
             "membership_id",
             champs is not None and not any(
                 c.lower() in ("code", "subscribercode", "membershipid",
                               "membership_id") for c in champs),
             str(sorted(champs or [])))

    route = _fonction(SERVER_ARBRE, SERVER_SRC, "lot3b_estimation_tarifaire")
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


# ══════════════════════════════ execution ═══════════════════════════════════
def principal():
    partie_1_avantage_de_l_offre()
    partie_2_couverture()
    asyncio.get_event_loop().run_until_complete(partie_2bis_lecture())
    partie_3_arbitrage()
    partie_4_snapshot()
    partie_5_perimetre()
    partie_6_securite()


def rapport():
    print("\n" + "=" * 74)
    print("LOT 3b — L'AVANTAGE MEMBRE : LA DATE DECIDE, LE MEILLEUR TARIF GAGNE")
    print("=" * 74)
    print("%d / %d verifications au vert" % (_ok, _ok + _ko))
    return _ko == 0


if __name__ == "__main__":
    principal()
    sys.exit(0 if rapport() else 1)
