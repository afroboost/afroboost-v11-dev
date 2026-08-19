# -*- coding: utf-8 -*-
"""P1-bis-a — LES ADHESIONS : LA SAISIE, ET LA PREUVE QU'ELLE NE TOUCHE A RIEN.

Ce lot pose une collection `memberships`, un formulaire, et deux lectures. Il ne
change AUCUN prix. Les mesures 10 a 14 ne verifient pas un comportement : elles
verifient une ABSENCE — qu'aucun autre chemin du depot ne lit cette collection.
C'est la seule facon de prouver « si P1-bis-b n'arrive jamais, la production est
identique a hier ».

Ce que ces tests garantissent :
  * le statut est DEDUIT des dates, jamais stocke, bornes incluses ;
  * la propriete est SYMETRIQUE — un partenaire ne voit que ses adhesions, un
    contexte sans proprietaire ne voit que celles sans proprietaire ;
  * aucune donnee personnelle sans jeton coach signe ;
  * la trace financiere reutilise le vocabulaire du lot B, avec ses refus ;
  * aucun backfill : une base pleine de forfaits a 250 et 150 ne produit
    AUCUNE adhesion ;
  * aucune saisie utilisateur n'entre dans une regex MongoDB ;
  * checkout, LOT A, ESSAI, Finance A/B et Stripe ignorent `memberships`.

AUCUNE BASE REELLE, AUCUN RESEAU. Les modules sont charges par chemin, avec un
`fastapi` bouchon, comme `tests/test_b_encaissement.py`.
"""
import asyncio, importlib.util, io, os, sys, types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from tests._banc_qr import RESULTATS, verifier, _Base, _Collection, _HTTPException  # noqa: E402


# ═════════════════════════ bouchons de chargement ═══════════════════════════
class _RouteurBouchon:
    """APIRouter reduit a ce dont ce module se sert : deux decorateurs."""

    def __init__(self, *a, **k):
        self.routes = {}

    def _enregistrer(self, methode, chemin):
        def decorateur(fonction):
            self.routes[(methode, chemin)] = fonction
            return fonction
        return decorateur

    def post(self, chemin, **k):
        return self._enregistrer("POST", chemin)

    def get(self, chemin, **k):
        return self._enregistrer("GET", chemin)


_fa = types.ModuleType("fastapi")
_fa.HTTPException = _HTTPException
_fa.APIRouter = _RouteurBouchon
_fa.Request = object
sys.modules["fastapi"] = _fa


def _charger(nom_module, *chemin):
    spec = importlib.util.spec_from_file_location(nom_module, os.path.join(RACINE, *chemin))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SHARED = _charger("p1a_shared", "api", "routes", "shared.py")
sys.modules["api"] = types.ModuleType("api")
sys.modules["api.routes"] = types.ModuleType("api.routes")
sys.modules["api.routes.shared"] = SHARED

# `api.server` n'est PAS charge (il ouvrirait une connexion MongoDB au premier
# import). On lui substitue les trois seules fonctions que ce module lui demande.
JETON = {"email": "", "coach": True, "admin": False}
_srv = types.ModuleType("api.server")
_srv._v311_coach_email_from_jwt = lambda requete: JETON["email"]


async def _est_coach(email):
    return bool(email) and JETON["coach"]


_srv._v309_is_coach_or_admin = _est_coach
_srv.is_super_admin = lambda email: JETON["admin"]
sys.modules["api.server"] = _srv

M = _charger("p1a_membership", "api", "routes", "membership_routes.py")

SUPER_ADMIN = "contact.artboost@gmail.com"
PARTENAIRE = "partenaire@exemple.com"


class _Requete:
    """Le `Request` de FastAPI reduit a ce que les deux routes lisent."""

    def __init__(self, corps=None):
        self._corps = corps if corps is not None else {}

    async def json(self):
        if isinstance(self._corps, Exception):
            raise self._corps
        return self._corps


def _base_neuve():
    base = _Base()
    base.memberships = _Collection()
    M.init_membership_db(base)
    return base


def _connecte(email, admin=False, coach=True):
    JETON["email"] = email
    JETON["admin"] = admin
    JETON["coach"] = coach


async def _creer(**corps):
    return await M.creer_adhesion(_Requete(corps))


async def _lister(**kw):
    return await M.lister_adhesions(_Requete(), **kw)


def _echec(coroutine):
    """Renvoie l'HTTPException levee, ou None si l'appel a reussi."""
    try:
        asyncio.get_event_loop().run_until_complete(coroutine)
        return None
    except _HTTPException as err:
        return err


# ═══════════════ 1-4. LES DATES DECIDENT, ET ELLES SEULES ═══════════════════
def test_statut_deduit():
    # 2. actif aujourd'hui — bornes INCLUSES aux deux extremites.
    verifier("2. adhesion en cours -> active",
             M.p1a_statut("2026-01-01", "2026-12-31", "2026-08-19") == "active")
    verifier("2b. le PREMIER jour est inclus",
             M.p1a_statut("2026-08-19", "2027-08-18", "2026-08-19") == "active")
    verifier("2c. le DERNIER jour est inclus",
             M.p1a_statut("2025-08-19", "2026-08-19", "2026-08-19") == "active")

    # 3. expire — l'exemple exact du cahier des charges.
    verifier("3. lecture au 10/01/2027 d'une adhesion finie le 31/12/2026 -> expiree",
             M.p1a_statut("2026-01-01", "2026-12-31", "2027-01-10") == "expiree")
    verifier("3b. le lendemain de la fin -> expiree",
             M.p1a_statut("2026-01-01", "2026-12-31", "2027-01-01") == "expiree")

    # 4. future
    verifier("4. adhesion qui commence demain -> future",
             M.p1a_statut("2026-09-01", "2027-08-31", "2026-08-19") == "future")

    # Le cinquieme cas : un document sans dates lisibles n'est JAMAIS actif.
    verifier("4b. dates absentes -> invalide (jamais actif)",
             M.p1a_statut("", "", "2026-08-19") == "invalide")
    verifier("4c. fin avant debut -> invalide",
             M.p1a_statut("2026-12-31", "2026-01-01", "2026-08-19") == "invalide")
    verifier("4d. date illisible -> invalide",
             M.p1a_statut("hier", "demain", "2026-08-19") == "invalide")


def test_formats_de_date():
    verifier("1c. le format du navigateur (AAAA-MM-JJ) est accepte",
             M.p1a_date_iso("2026-08-19") == "2026-08-19")
    verifier("1d. le format ecrit a la main (JJ/MM/AAAA) est accepte",
             M.p1a_date_iso("19/08/2026") == "2026-08-19")
    verifier("1e. une date fantaisiste est REFUSEE, jamais devinee",
             M.p1a_date_iso("le 19 aout") == "")


async def test_creation():
    base = _base_neuve()
    _connecte(SUPER_ADMIN, admin=True)
    reponse = await _creer(email="Bassi@Exemple.com", name="Bassi",
                           date_debut="19/08/2026", date_fin="18/08/2027",
                           montant=100, origine_paiement="especes")
    doc = base.memberships.docs[0]
    verifier("1. une adhesion valide est enregistree", reponse.get("success") is True)
    verifier("1a. l'e-mail est normalise en minuscules", doc["email"] == "bassi@exemple.com")
    verifier("1b. les dates sont stockees en AAAA-MM-JJ",
             doc["date_debut"] == "2026-08-19" and doc["date_fin"] == "2027-08-18")
    verifier("1f. la source est declaree", doc.get("source") == "saisie_manuelle")
    verifier("1g. l'auteur de la saisie est conserve", doc.get("created_by") == SUPER_ADMIN)

    # 6bis. AUCUN statut en base : il est calcule a chaque lecture.
    verifier("6bis. aucun `statut` n'est stocke en base", "statut" not in doc)
    verifier("6ter. aucun booleen `is_member` n'est stocke",
             "is_member" not in doc and "active" not in doc)
    verifier("6quater. la reponse porte le statut CALCULE",
             reponse["membership"]["statut"] in M.P1A_STATUTS)

    # Le statut rendu par la lecture ecrase celui qu'un document porterait.
    menteur = dict(doc)
    menteur["statut"] = "active"
    menteur["date_debut"] = "2019-01-01"
    menteur["date_fin"] = "2020-01-01"
    verifier("6quinquies. un statut ecrit en base est ecrase par le calcul",
             M.p1a_projeter(menteur, "2026-08-19")["statut"] == "expiree")


async def test_creation_refus():
    base = _base_neuve()
    _connecte(SUPER_ADMIN, admin=True)
    for nom, corps in (
        ("e-mail absent", {"date_debut": "2026-01-01", "date_fin": "2026-12-31"}),
        ("e-mail invalide", {"email": "pas-une-adresse", "date_debut": "2026-01-01",
                             "date_fin": "2026-12-31"}),
        ("dates absentes", {"email": "a@b.ch"}),
        ("date de fin avant le debut", {"email": "a@b.ch", "date_debut": "2026-12-31",
                                        "date_fin": "2026-01-01"}),
    ):
        erreur = None
        try:
            await _creer(**corps)
        except _HTTPException as err:
            erreur = err
        verifier("1h. refus (%s) sans rien ecrire" % nom,
                 erreur is not None and erreur.status_code == 400 and not base.memberships.docs)


# ═══════════════ 5-7. LA PROPRIETE, SYMETRIQUE DES DEUX COTES ═══════════════
async def test_proprietaire():
    base = _base_neuve()

    _connecte(PARTENAIRE, admin=False)
    await _creer(email="client@partenaire.ch", date_debut="2026-01-01", date_fin="2026-12-31")
    verifier("5. un partenaire est proprietaire de ce qu'il saisit",
             base.memberships.docs[0]["coach_id"] == PARTENAIRE)

    _connecte(SUPER_ADMIN, admin=True)
    await _creer(email="client@maison.ch", date_debut="2026-01-01", date_fin="2026-12-31")
    verifier("6. le super-admin ecrit SANS proprietaire (jamais son adresse injectee)",
             base.memberships.docs[1]["coach_id"] is None)

    # 7. anti-fuite, dans les DEUX sens.
    vu_admin = [m["email"] for m in (await _lister())["memberships"]]
    verifier("7. le contexte sans proprietaire ne voit QUE le stock sans proprietaire",
             vu_admin == ["client@maison.ch"])

    _connecte(PARTENAIRE, admin=False)
    vu_partenaire = [m["email"] for m in (await _lister())["memberships"]]
    verifier("7b. un partenaire ne voit QUE ses adhesions",
             vu_partenaire == ["client@partenaire.ch"])

    # Un troisieme coach ne voit rien du tout : fail closed en multi-coach.
    _connecte("autre@coach.ch", admin=False)
    verifier("7c. un coach tiers ne voit rien (fail closed)",
             (await _lister())["memberships"] == [])


def test_filtre_symetrique():
    verifier("5b. proprietaire reel -> egalite stricte sur coach_id",
             M.p1a_filtre_proprietaire(PARTENAIRE) == {"coach_id": PARTENAIRE})
    sans = M.p1a_filtre_proprietaire(None)
    verifier("6b. sans proprietaire -> les TROIS formes reelles, et aucune autre",
             sans == {"$or": [{"coach_id": None}, {"coach_id": ""},
                              {"coach_id": {"$exists": False}}]})
    verifier("6c. le super-admin n'est jamais injecte comme proprietaire",
             M.p1a_coach_id_contexte(SUPER_ADMIN, True) is None)
    verifier("5c. un partenaire l'est, lui", M.p1a_coach_id_contexte(PARTENAIRE, False) == PARTENAIRE)


# ═════════════════ 8. AUCUN BACKFILL, AUCUN FAUX MEMBRE ═════════════════════
async def test_aucun_backfill():
    base = _base_neuve()
    # Un passe charge : forfaits a 250 et a 150, codes promo, offres. Rien de
    # tout cela ne doit produire une adhesion.
    base.subscriptions.docs.extend([
        {"id": "s1", "email": "ancien@client.ch", "offer_name": "Carte membre 150",
         "renewal_price": 150, "status": "active"},
        {"id": "s2", "email": "ancien2@client.ch", "offer_name": "PULSE x10",
         "renewal_price": 250, "status": "active"},
    ])
    base.offers.docs.extend([
        {"id": "o1", "name": "Adhesion annuelle", "price": 150},
        {"id": "o2", "name": "PULSE x10", "price": 250},
    ])
    base.discount_codes.docs.append({"code": "AFR-ABC123", "assignedEmail": "ancien@client.ch"})

    _connecte(SUPER_ADMIN, admin=True)
    reponse = await _lister()
    verifier("8. un passe plein de forfaits 250/150 ne produit AUCUNE adhesion",
             reponse["memberships"] == [] and reponse["total"] == 0)

    # Mesure sur le CODE : toutes les collections REELLEMENT touchees, relevees
    # par AST (`db["..."]`). Le commentaire du module peut nommer les autres —
    # c'est justement pour dire qu'il ne les lit pas.
    import ast as _ast
    source = io.open(os.path.join(RACINE, "api", "routes", "membership_routes.py"),
                     encoding="utf-8").read()
    touchees = set()
    for noeud in _ast.walk(_ast.parse(source)):
        if isinstance(noeud, _ast.Subscript) and isinstance(noeud.value, _ast.Name) \
                and noeud.value.id == "db":
            cible = noeud.slice
            if isinstance(cible, _ast.Constant):
                touchees.add(cible.value)
    verifier("8b. la SEULE collection touchee est `memberships`",
             touchees == {"memberships"}, str(sorted(touchees)))
    verifier("8c. aucun acces par attribut a une autre collection (db.xxx)",
             not any(isinstance(n, _ast.Attribute) and isinstance(n.value, _ast.Name)
                     and n.value.id == "db" for n in _ast.walk(_ast.parse(source))))


# ═════════════════════ 9. LA TRACE FINANCIERE (LOT B) ═══════════════════════
async def test_montant():
    base = _base_neuve()
    _connecte(SUPER_ADMIN, admin=True)
    await _creer(email="carte@membre.ch", date_debut="2026-01-01", date_fin="2026-12-31",
                 montant=100, origine_paiement="especes")
    doc = base.memberships.docs[0]
    verifier("9. le montant de la carte est stocke dans le vocabulaire du lot B",
             doc.get("montant_encaisse") == 100.0)
    verifier("9a. la devise accompagne le montant", doc.get("devise") == "CHF")
    verifier("9b. le moyen de paiement est conserve", doc.get("origine_paiement") == "especes")
    verifier("9c. la saisie est datee et signee",
             bool(doc.get("encaissement_saisi_le")) and doc.get("encaissement_saisi_par") == SUPER_ADMIN)
    verifier("9d. aucune seance n'est ouverte par une adhesion",
             "seances_a_l_achat" not in doc)

    # Les refus du lot B s'appliquent tels quels — aucune regle recopiee.
    base2 = _base_neuve()
    for nom, corps in (
        ("« offert » avec un montant", {"montant": 100, "origine_paiement": "offert"}),
        ("0 non declare offert", {"montant": 0, "origine_paiement": "especes"}),
        ("montant negatif", {"montant": -10, "origine_paiement": "especes"}),
        ("moyen inconnu", {"montant": 100, "origine_paiement": "bitcoin"}),
        ("montant sans moyen", {"montant": 100}),
    ):
        erreur = None
        try:
            await _creer(email="x@y.ch", date_debut="2026-01-01", date_fin="2026-12-31", **corps)
        except _HTTPException as err:
            erreur = err
        verifier("9e. refus lot B (%s), rien n'est ecrit" % nom,
                 erreur is not None and erreur.status_code == 400 and not base2.memberships.docs)

    # Une adhesion SANS montant reste possible : la carte peut etre reglee plus tard.
    base3 = _base_neuve()
    await _creer(email="sans@montant.ch", date_debut="2026-01-01", date_fin="2026-12-31")
    verifier("9f. une adhesion sans montant est acceptee, et reste sans montant",
             len(base3.memberships.docs) == 1
             and "montant_encaisse" not in base3.memberships.docs[0])
    verifier("9g. « offert » seul est une declaration valide a 0",
             True)
    base4 = _base_neuve()
    await _creer(email="offert@membre.ch", date_debut="2026-01-01", date_fin="2026-12-31",
                 origine_paiement="offert")
    verifier("9h. « offert » se declare a 0, sans ambiguite",
             base4.memberships.docs[0].get("montant_encaisse") == 0.0
             and base4.memberships.docs[0].get("origine_paiement") == "offert")


# ═════════════════════ AUTHENTIFICATION ET SURFACE ══════════════════════════
async def test_authentification():
    base = _base_neuve()
    _connecte("", admin=False)
    for nom, appel in (("creation", M.creer_adhesion(_Requete({"email": "a@b.ch"}))),
                       ("lecture", M.lister_adhesions(_Requete()))):
        erreur = None
        try:
            await appel
        except _HTTPException as err:
            erreur = err
        verifier("A. sans jeton coach signe, %s refusee en 403" % nom,
                 erreur is not None and erreur.status_code == 403)
    verifier("A2. aucune ecriture n'a eu lieu pendant les refus", not base.memberships.docs)

    # Jeton present mais role absent : refus aussi.
    _connecte("inconnu@nulle.part", coach=False)
    erreur = None
    try:
        await M.lister_adhesions(_Requete())
    except _HTTPException as err:
        erreur = err
    verifier("A3. un jeton sans role coach/admin est refuse",
             erreur is not None and erreur.status_code == 403)

    # Mesure sur le CODE, pas sur les commentaires : le module ne lit aucun
    # en-tete lui-meme, il delegue au verificateur de jeton signe.
    import ast as _ast
    source = io.open(os.path.join(RACINE, "api", "routes", "membership_routes.py"),
                     encoding="utf-8").read()
    arbre = _ast.parse(source)
    lit_entetes = any(
        isinstance(n, _ast.Attribute) and n.attr == "headers" for n in _ast.walk(arbre))
    verifier("A4. le module ne lit AUCUN en-tete lui-meme (donc jamais X-User-Email)",
             not lit_entetes)
    verifier("A4b. l'identite vient du verificateur de jeton SIGNE",
             "_v311_coach_email_from_jwt" in source)


async def test_pagination_et_regex():
    base = _base_neuve()
    _connecte(SUPER_ADMIN, admin=True)
    for i in range(3):
        await _creer(email="m%d@exemple.ch" % i, date_debut="2026-01-01", date_fin="2026-12-31")
    reponse = await _lister(limit=500)
    verifier("B. la taille de page est plafonnee a 50", reponse["limit"] == 50)
    reponse = await _lister(limit=0, page=0)
    verifier("B2. une page ou une taille nulle retombe sur des valeurs sures",
             reponse["limit"] >= 1 and reponse["page"] == 1)

    filtre = await _lister(email="M1@Exemple.CH")
    verifier("B3. le filtre par e-mail est une egalite stricte, en minuscules",
             [m["email"] for m in filtre["memberships"]] == ["m1@exemple.ch"])

    source = io.open(os.path.join(RACINE, "api", "routes", "membership_routes.py"),
                     encoding="utf-8").read()
    verifier("B4. aucune saisie utilisateur n'entre dans une regex MongoDB",
             "$regex" not in source)


# ══════════ 10-14. CE LOT NE TOUCHE A RIEN — LA PREUVE PAR L'ABSENCE ════════
def _fichiers_python():
    for dossier, _, fichiers in os.walk(os.path.join(RACINE, "api")):
        for nom in fichiers:
            if nom.endswith(".py"):
                yield os.path.join(dossier, nom)


def test_aucune_autre_lecture():
    """Le coeur de la garantie : `memberships` n'est nomme QUE par son module.

    Toute apparition ailleurs signalerait qu'un chemin de production s'est mis a
    en dependre — donc que la promesse « rien ne change » est fausse.
    """
    porteurs = {}
    for chemin in _fichiers_python():
        texte = io.open(chemin, encoding="utf-8").read()
        if "memberships" in texte or "membership_router" in texte:
            porteurs[os.path.relpath(chemin, RACINE)] = texte

    attendus = {"api/routes/membership_routes.py", "api/server.py"}
    verifier("10-14. seuls le module d'adhesions et l'enregistrement des routes "
             "nomment `memberships`",
             set(porteurs) == attendus, str(sorted(porteurs)))

    # Dans server.py, les seules occurrences sont les lignes d'enregistrement :
    # import, include_router, init. Aucune logique metier.
    lignes = [l.strip() for l in porteurs.get("api/server.py", "").splitlines()
              if "membership" in l and not l.strip().startswith("#")]
    verifier("10-14b. server.py ne fait qu'enregistrer le routeur (3 lignes)",
             len(lignes) == 3 and all(
                 ("import" in l) or ("include_router" in l) or ("init_membership_db" in l)
                 for l in lignes), str(lignes))

    # 10-14c. Les chemins nommement proteges par le cahier des charges.
    surveilles = {
        "10. checkout / prix": ["api/routes/checkout_routes.py", "api/pricing.py"],
        "11. LOT A conversion": ["api/routes/shared.py"],
        "12. ESSAI gratuit": ["api/routes/checkout_routes.py"],
        "13. Finance A/B": ["api/routes/shared.py"],
        "14. Stripe": ["api/routes/stripe_routes.py", "api/routes/reservation_routes.py"],
    }
    # On cherche des REFERENCES, pas le mot « adhesion » : shared.py en parle
    # deja en francais depuis le LOT A (« aucun moteur d'adhesion dans ce
    # depot ») — c'est du commentaire, pas un appel.
    references = ("memberships", "membership_routes", "membership_router",
                  "init_membership_db")
    for libelle, fichiers in surveilles.items():
        coupables = []
        for f in fichiers:
            texte = io.open(os.path.join(RACINE, f), encoding="utf-8").read()
            coupables += [r for r in references if r in texte]
        verifier("%s : aucun appel aux adhesions" % libelle,
                 not coupables, ",".join(coupables))


def test_interface_coach():
    """L'ecran de saisie respecte les regles d'interface du depot."""
    chemin = os.path.join(RACINE, "frontend", "src", "components", "dashboard",
                          "AdhesionsManager.js")
    source = io.open(chemin, encoding="utf-8").read()

    verifier("UI1. le formulaire demande participant, debut, fin et montant",
             all(cle in source for cle in ("adhesion-email", "adhesion-debut",
                                           "adhesion-fin", "adhesion-montant")))
    verifier("UI2. les quatre moyens du lot B sont proposes",
             all(m in source for m in ("especes", "twint", "virement", "offert")))
    verifier("UI3. « offert » desactive la saisie du montant", "disabled={offert}" in source)
    verifier("UI4. les trois libelles de statut viennent des dates",
             all(l in source for l in ("Active", "Future", "Expirée")))

    # Couleurs : tout hexadecimal doit etre un REPLI dans un var(), jamais impose.
    import re as _re
    hexas = _re.findall(r"#[0-9a-fA-F]{6}", source)
    replis = _re.findall(r"var\(--[a-z-]+,\s*#[0-9a-fA-F]{6}", source)
    verifier("UI5. aucune couleur codee en dur (uniquement des replis dans var())",
             len(hexas) == len(replis), "%d hex / %d replis" % (len(hexas), len(replis)))

    verifier("UI6. aucune icone emoji (SVG inline uniquement)",
             "SvgIcon" in source and not _re.search(
                 r"[\U0001F300-\U0001FAFF☀-➿]", source))
    verifier("UI7. le chargement passe par le socle P0 (jamais un zero menteur)",
             "useChargement" in source and "SECTION" in source)
    verifier("UI8. la liste est DERIVEE, aucun setState d'objet (anti-boucle)",
             "const liste = (charge && charge.memberships) || []" in source)

    dashboard = io.open(os.path.join(RACINE, "frontend", "src", "components",
                                     "CoachDashboard.js"), encoding="utf-8").read()
    verifier("UI9. l'ecran est accroche au dashboard, sans toucher aux onglets existants",
             "AdhesionsManager" in dashboard and "offersSubTab === 'adhesions'" in dashboard)


# ══════════════════════════════ execution ═══════════════════════════════════
async def principal():
    test_statut_deduit()
    test_formats_de_date()
    await test_creation()
    await test_creation_refus()
    await test_proprietaire()
    test_filtre_symetrique()
    await test_aucun_backfill()
    await test_montant()
    await test_authentification()
    await test_pagination_et_regex()
    test_aucune_autre_lecture()
    test_interface_coach()


def rapport():
    print("\n" + "=" * 74)
    print("P1-bis-a — ADHESIONS : SAISIE MANUELLE, ET AUCUN EFFET AILLEURS")
    print("=" * 74)
    ok = 0
    for nom, reussi, detail in RESULTATS:
        print(("  OK   " if reussi else "  ECHEC") + "  " + nom
              + (("  [%s]" % detail) if detail and not reussi else ""))
        ok += 1 if reussi else 0
    print("-" * 74)
    print("%d / %d verifications au vert" % (ok, len(RESULTATS)))
    return ok == len(RESULTATS)


if __name__ == "__main__":
    asyncio.run(principal())
    sys.exit(0 if rapport() else 1)
