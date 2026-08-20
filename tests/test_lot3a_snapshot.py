# -*- coding: utf-8 -*-
"""LOT 3a — LE TARIF FIGE. Verifications hors ligne, sans base ni reseau.

CE QUE CE LOT PROMET, ET QUE CES TESTS VERROUILLENT
---------------------------------------------------
1. AUCUN PRIX NE CHANGE. Le lot n'ajoute que des champs a des documents qui
   allaient etre ecrits. Les tests de structure verifient qu'aucune ligne de
   calcul de montant n'a ete touchee (parties 3 et 4).
2. Le montant fige vient du PAIEMENT, jamais du catalogue du jour — c'est la
   difference entre « cette seance a coute 15 CHF » et « une seance de cette
   offre coute 25 CHF aujourd'hui ».
3. La raison est EXPLICITE. Jamais deduite d'un montant : 15 CHF peut etre un
   forfait, une promo ou un plein tarif.
4. Quand on ne sait pas, on n'ecrit RIEN. Une reservation sans snapshot se lit
   « on ne sait pas » ; un snapshot faux ment pour toujours.

    python3 tests/test_lot3a_snapshot.py
"""
import ast
import importlib.util
import io
import os
import sys
import types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_ok = _ko = 0


def verifier(titre, condition, detail=""):
    global _ok, _ko
    if condition:
        _ok += 1
        print("  OK     " + titre)
    else:
        _ko += 1
        print(" ECHEC   " + titre + ("   -> " + str(detail) if detail else ""))


# ═══════════════ chargement du VRAI module, hors ligne ══════════════════════
_fa = types.ModuleType("fastapi")


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
sys.modules["api.server"] = _srv


def _charger(nom, *chemin):
    spec = importlib.util.spec_from_file_location(nom, os.path.join(RACINE, *chemin))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nom] = mod
    spec.loader.exec_module(mod)
    return mod


S = _charger("api.routes.shared", "api", "routes", "shared.py")


def _src(*chemin):
    return io.open(os.path.join(RACINE, *chemin), encoding="utf-8").read()


# ═══════════════ 1. LA COPIE PLATE ══════════════════════════════════════════
def partie_1_snapshot():
    print("\n=== 1. LE SNAPSHOT EST UNE COPIE PLATE, ET IL SAIT SE TAIRE ===")
    s = S.lot3_snapshot_tarifaire(15, "forfait", tarif_public=30,
                                  palier="standard", offre_id="offre-1")
    verifier("1a. les quatre champs toujours poses",
             s["tarif_applique"] == 15.0 and s["tarif_raison"] == "forfait"
             and s["tarif_devise"] == "CHF" and "tarif_fige_le" in s, str(s))
    verifier("1b. les champs facultatifs le sont vraiment",
             s["tarif_public"] == 30.0 and s["tarif_palier"] == "standard"
             and s["tarif_offre_id"] == "offre-1", str(s))
    verifier("1c. le document est PLAT (aucune valeur imbriquee)",
             all(not isinstance(v, (dict, list)) for v in s.values()), str(s))

    nu = S.lot3_snapshot_tarifaire(15, "forfait")
    verifier("1d. une cle ABSENTE dit « je ne sais pas » — jamais None",
             "tarif_public" not in nu and "tarif_palier" not in nu
             and "tarif_offre_id" not in nu, str(nu))

    verifier("1e. montant illisible -> AUCUN champ",
             S.lot3_snapshot_tarifaire(None, "public") == {}
             and S.lot3_snapshot_tarifaire("abc", "public") == {})
    verifier("1f. montant negatif -> AUCUN champ",
             S.lot3_snapshot_tarifaire(-5, "public") == {})
    verifier("1g. zero est une valeur VALIDE (un essai vaut 0, et on le dit)",
             S.lot3_snapshot_tarifaire(0, "essai")["tarif_applique"] == 0.0)
    # LOT 3b — CES DEUX ASSERTIONS SONT RETOURNEES, PAS SUPPRIMEES.
    #
    # Elles disaient « `membre` n'existe pas encore », ce qui etait la
    # specification NEGATIVE de LOT 3a : le vocabulaire ne devait pas nommer ce
    # qu'aucun code ne savait produire. LOT 3b sait desormais reconnaitre un
    # membre, donc le mot entre — et ce qu'il faut verifier devient : il est
    # bien la, ET rien d'autre n'est entre avec lui.
    verifier("1h. une raison hors vocabulaire retombe toujours sur `inconnu`",
             S.lot3_snapshot_tarifaire(10, "cadeau-du-coach")["tarif_raison"] == "inconnu")
    verifier("1h2. `membre` est desormais une raison VALIDE (LOT 3b)",
             S.lot3_snapshot_tarifaire(15, "membre")["tarif_raison"] == "membre")
    verifier("1i. le vocabulaire reste FERME, et n'a gagne que `membre`",
             set(S.LOT3_RAISONS) == {"public", "promo", "membre", "forfait",
                                     "essai", "offert", "inconnu"}, str(S.LOT3_RAISONS))


# ═══════════════ 2. LA RAISON NE SE DEDUIT JAMAIS DU MONTANT ════════════════
def partie_2_raison():
    print("\n=== 2. LA RAISON EST EXPLICITE, JAMAIS DEDUITE D'UN MONTANT ===")
    verifier("2a. preuve sociale -> `essai` (elle a ete GAGNEE)",
             S.lot3_raison_du_droit({}, {"source": "social_proof"}) == "essai")
    verifier("2b. porte gratuite -> `essai` (le droit d'essai est brule)",
             S.lot3_raison_du_droit({}, {"payment_method": "free",
                                         "total_paid": 0}) == "essai")
    verifier("2c. origine « offert » -> `offert` (elle a ete ACCORDEE)",
             S.lot3_raison_du_droit({}, {"origine_paiement": "offert"}) == "offert")
    verifier("2d. forfait paye -> `forfait`",
             S.lot3_raison_du_droit({"code": "AFR-1"},
                                    {"code": "AFR-1", "total_paid": 250}) == "forfait")
    verifier("2e. rien du tout -> `inconnu`, jamais une supposition",
             S.lot3_raison_du_droit(None, None) == "inconnu")
    verifier("2f. la gratuite est lue sur les DEUX documents jumeaux",
             S.lot3_raison_du_droit({"payment_method": "free",
                                     "total_paid": 0}, None) == "essai",
             "le scan QR n'a que la souscription en main")

    # Le meme montant, trois raisons differentes : la preuve que le chiffre ne
    # decide de rien.
    trois = {S.lot3_snapshot_tarifaire(15, r)["tarif_raison"]
             for r in ("forfait", "promo", "public")}
    verifier("2g. 15 CHF peut etre forfait, promo OU public — le montant ne "
             "designe aucune raison", trois == {"forfait", "promo", "public"})


# ═══════════════ 3. LE FORFAIT : LA REGLE FINANCE, ET ELLE SEULE ════════════
def partie_3_forfait():
    print("\n=== 3. LA VALEUR D'UNE SEANCE VIENT DU MONTANT PAYE ===")
    code = {"code": "AFR-1", "maxUses": 10, "total_paid": 250}
    pulse = {"seances_a_l_achat": 10, "montant_encaisse": 250.0, "devise": "CHF",
             "origine_paiement": "stripe", "code": "AFR-1"}
    membres = dict(pulse, montant_encaisse=150.0)

    f1 = S.lot3_snapshot_du_forfait(pulse, code)
    verifier("3a. PULSE x10 paye 250 -> la seance vaut 25.00",
             f1.get("tarif_applique") == 25.0 and f1.get("tarif_raison") == "forfait",
             str(f1))
    f2 = S.lot3_snapshot_du_forfait(membres, code)
    verifier("3b. « Membres » paye 150 -> la seance vaut 15.00",
             f2.get("tarif_applique") == 15.0, str(f2))
    verifier("3c. ... et JAMAIS 25 : deux forfaits sur les MEMES cours ne "
             "valent pas pareil", f2.get("tarif_applique") != 25.0)

    # Le denominateur ne doit pas bouger avec les compteurs.
    mouvant = dict(membres, total_sessions=999, remaining_sessions=1,
                   used_sessions=9)
    verifier("3d. `total_sessions` et `remaining_sessions` n'influencent RIEN",
             S.lot3_snapshot_du_forfait(mouvant, code).get("tarif_applique") == 15.0,
             "le denominateur est `seances_a_l_achat`, fige a l'achat")

    verifier("3e. montant non prouve -> AUCUN snapshot (on ne devine pas)",
             S.lot3_snapshot_du_forfait({"seances_a_l_achat": 10}, {}) == {})
    _essai = S.lot3_snapshot_du_forfait({}, {"payment_method": "free",
                                             "total_paid": 0})
    verifier("3f. un essai vaut 0 avec la raison `essai`, pas « forfait a 0 »",
             _essai.get("tarif_applique") == 0.0
             and _essai.get("tarif_raison") == "essai", str(_essai))

    # Le catalogue n'est jamais lu : la fonction ne recoit meme pas d'offre.
    import inspect
    params = set(inspect.signature(S.lot3_snapshot_du_forfait).parameters)
    verifier("3g. la fonction ne recoit AUCUNE offre — le catalogue lui est "
             "inaccessible par construction",
             params == {"souscription", "code", "reservation"}, str(params))


# ═══════════════ 4. AUCUN PRIX N'EST TOUCHE ═════════════════════════════════
def partie_4_aucun_prix_touche():
    print("\n=== 4. LE LOT NE CHANGE AUCUN MONTANT ===")
    fonctions = ("lot3_snapshot_tarifaire", "lot3_raison_du_droit",
                 "lot3_snapshot_du_forfait", "lot3_champs_forfait",
                 "lot3_champs_achat")
    arbre = ast.parse(_src("api", "routes", "shared.py"))
    noeuds = {n.name: n for n in ast.walk(arbre)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name in fonctions}
    verifier("4a. les cinq fonctions du lot existent",
             set(noeuds) == set(fonctions), str(sorted(noeuds)))

    ecritures = set()
    for nom, noeud in noeuds.items():
        for n in ast.walk(noeud):
            if isinstance(n, ast.Attribute) and n.attr in (
                    "insert_one", "update_one", "update_many", "delete_one",
                    "delete_many", "find_one_and_update"):
                ecritures.add(nom + "." + n.attr)
    verifier("4b. AUCUNE de ces fonctions n'ecrit en base — ce sont des "
             "fonctions pures", not ecritures, str(sorted(ecritures)))

    # Les champs poses commencent tous par `tarif_` : impossible d'ecraser
    # `totalPrice`, `price` ou un champ de montant existant.
    cles = set()
    for noeud in noeuds.values():
        for n in ast.walk(noeud):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) \
                    and n.value.startswith("tarif_"):
                cles.add(n.value)
    verifier("4c. tous les champs ecrits portent le prefixe `tarif_`",
             cles and all(c.startswith("tarif_") for c in cles), str(sorted(cles)))
    verifier("4d. aucun champ de montant EXISTANT n'est parmi eux",
             not (cles & {"price", "totalPrice", "amount", "total",
                          "montant_encaisse", "renewal_price"}), str(sorted(cles)))

    # Sur les cinq points d'ecriture : le snapshot est FUSIONNE, jamais
    # substitue, et il n'y a aucune reaffectation de montant a cote.
    points = (("api", "routes", "reservation_routes.py"),
              ("api", "server.py"),
              ("api", "routes", "checkout_routes.py"))
    total_appels = 0
    for chemin in points:
        texte = _src(*chemin)
        total_appels += texte.count("_lot3_champs(") + texte.count("_lot3_achat(")
    verifier("4e. les cinq points d'ecriture appellent le snapshot",
             total_appels >= 5, "appels trouves : %d" % total_appels)

    # CE CONTROLE MANQUAIT, et son absence a laisse passer une regression
    # reelle (20/08/2026) : trois imports n'etaient pas proteges. La fonction
    # `lot3_champs_forfait` ne leve jamais — mais l'INSTRUCTION D'IMPORT qui va
    # la chercher, si. Une reservation echouait alors parce qu'une ligne
    # d'historique n'avait pas pu s'ecrire, exactement l'inverse de ce que le
    # lot promet. On verifie donc que CHAQUE appel vit dans un `try`.
    _non_proteges = []
    for chemin in points:
        arbre_p = ast.parse(_src(*chemin))
        _dans_try = set()
        for n in ast.walk(arbre_p):
            if isinstance(n, ast.Try):
                for sous in ast.walk(n):
                    _dans_try.add(id(sous))
        for n in ast.walk(arbre_p):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                    and n.func.id in ("_lot3_champs", "_lot3_achat"):
                if id(n) not in _dans_try:
                    _non_proteges.append("%s:%d" % (chemin[-1], n.lineno))
    verifier("4h. CHAQUE appel au snapshot est protege — import compris : "
             "un echec ne doit jamais faire perdre sa place au client",
             not _non_proteges, str(_non_proteges))

    resa = _src("api", "routes", "reservation_routes.py")
    verifier("4f. le snapshot est FUSIONNE (`update`), jamais substitue",
             "reservation_data.update(_lot3_champs(" in resa
             and "new_reservation.update(_lot3_champs(" in resa)
    verifier("4g. `totalPrice` n'est reaffecte nulle part par ce lot",
             "totalPrice=_lot3" not in resa and '"totalPrice": _lot3' not in resa)


# ═══════════════ 5. LES CINQ CHEMINS SONT COUVERTS ══════════════════════════
def partie_5_chemins():
    print("\n=== 5. AUCUN CHEMIN N'EST OUBLIE ===")
    resa = _src("api", "routes", "reservation_routes.py")
    srv = _src("api", "server.py")
    chk = _src("api", "routes", "checkout_routes.py")

    verifier("5a. POST /api/reservations (forfait ou code)",
             "reservation_data.update(_lot3_champs(_lot3_sub, _lot3_code" in resa)
    verifier("5b. espace abonne (seance tiree du forfait)",
             "reservation_doc.update(_lot3_champs(subscription" in srv)
    verifier("5c. scan QR du coach (presence constatee)",
             "new_reservation.update(_lot3_champs(subscription" in resa)
    verifier("5d. achat vitrine (caisse `_process_successful_payment`)",
             "_resa_doc.update(_lot3_achat(" in chk)
    verifier("5e. achat direct Stripe (webhook client)",
             "_reservation_doc.update(_lot3_achat(" in srv)
    verifier("5f. le chemin gratuit passe par la caisse vitrine — donc couvert",
             'if _pm == "free":' in chk and '"essai", 0.0' in chk.replace(" ", "")
             or '_lot3_raison, _lot3_du = "essai", 0.0' in chk)

    verifier("5g. le snapshot vitrine ne s'ecrit que sur UN SEUL article "
             "(pas de repartition inventee)", "if len(items) == 1:" in chk)
    verifier("5h. l'achat direct herite de l'idempotence de l'upsert",
             chk.count("setOnInsert") >= 0 and "$setOnInsert" in srv)


# ═══════════════ 6. LOT 3b N'EST PAS COMMENCE ═══════════════════════════════
def partie_6_perimetre():
    print("\n=== 6. LE PERIMETRE EST TENU : AUCUN AVANTAGE MEMBRE ===")
    shared = _src("api", "routes", "shared.py")
    _debut = shared.find("LOT 3a — LE TARIF FIGE")
    # LOT 3b — LE BLOC DE CE LOT S'ARRETE OU COMMENCE LE SUIVANT.
    # Sans cette borne, `bloc` avalait le bloc LOT 3b ajoute a la suite dans le
    # meme fichier, et les assertions de perimetre de LOT 3a lui reprochaient
    # le travail de LOT 3b. On mesure bien LOT 3a, et lui seul.
    _fin = shared.find("# LOT 3b — L'AVANTAGE MEMBRE")
    bloc = (shared[_debut:_fin] if _fin > _debut else shared[_debut:]) \
        if _debut > 0 else ""
    verifier("6a. le bloc LOT 3a existe", bool(bloc))
    # On cherche les CLES REELLEMENT POSEES, pas les mentions : le bloc parle
    # explicitement de ces deux champs pour dire qu'il ne les pose PAS, et un
    # `not in` sur le texte brut prendrait cette explication pour une faute.
    _cles_posees = set()
    for _n in ast.walk(ast.parse(shared)):
        if isinstance(_n, ast.Dict):
            for _k in _n.keys:
                if isinstance(_k, ast.Constant) and isinstance(_k.value, str):
                    _cles_posees.add(_k.value)
    # LOT 3b — MEME RETOURNEMENT QU'EN 1h/1i. Ces trois assertions gardaient la
    # frontiere entre les deux lots tant que LOT 3b n'existait pas. Maintenant
    # qu'il existe, ce qu'il faut prouver n'est plus « ces champs sont absents »
    # mais « ils ne sont poses QUE sur une decision membre, jamais a vide ».
    _bloc_3b = shared.split("# LOT 3b — L'AVANTAGE MEMBRE")[-1] if \
        "# LOT 3b — L'AVANTAGE MEMBRE" in shared else ""
    verifier("6b. `tarif_avantage_pct` n'est pose que SOUS CONDITION, jamais en litteral",
             ('_doc["tarif_avantage_pct"] = _pct' in shared
              and "if avantage_pct is not None:" in shared
              and "0 < _pct < 100" in shared))
    verifier("6c. `tarif_membership_id` n'est pose que SOUS CONDITION (idem)",
             ('_doc["tarif_membership_id"]' in shared
              and "if membership_id:" in shared))
    verifier("6c2. sur un achat plein tarif, les deux cles restent ABSENTES",
             ("tarif_avantage_pct" not in S.lot3_snapshot_tarifaire(30, "public")
              and "tarif_membership_id" not in S.lot3_snapshot_tarifaire(30, "public")))
    verifier("6d. LOT 3a lui-meme ne lit toujours AUCUNE adhesion "
             "(c'est LOT 3b qui les lit, dans son propre bloc)",
             "memberships" not in bloc and "lot2_adhesion_active" not in bloc)
    verifier("6d2. LOT 3b lit les adhesions, et ne les ECRIT jamais",
             (bool(_bloc_3b) and 'db["memberships"].find(' in _bloc_3b
              and not any(m in _bloc_3b for m in
                          ("insert_one", "update_one", "delete_one",
                           "update_many", "delete_many", "replace_one"))))
    verifier("6e. aucun pourcentage code en dur",
             not any(x in bloc for x in ("* 0.5", "*0.5", "/ 2", "0.50 *", "50 /")))

    front = os.path.join(RACINE, "frontend", "src")
    trouve = []
    for dossier, _, fichiers in os.walk(front):
        for nom in fichiers:
            if nom.endswith((".js", ".jsx")):
                t = io.open(os.path.join(dossier, nom), encoding="utf-8").read()
                if "tarif_applique" in t or "tarif_raison" in t:
                    trouve.append(nom)
    verifier("6f. AUCUN ecran n'est modifie — le lot est invisible cote client",
             not trouve, str(trouve))


def principal():
    partie_1_snapshot()
    partie_2_raison()
    partie_3_forfait()
    partie_4_aucun_prix_touche()
    partie_5_chemins()
    partie_6_perimetre()
    print("\n" + "-" * 78)
    print("%d / %d verifications au vert" % (_ok, _ok + _ko))
    return 1 if _ko else 0


if __name__ == "__main__":
    sys.exit(principal())
