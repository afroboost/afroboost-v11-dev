# -*- coding: utf-8 -*-
"""LOT 2 — L'ADHESION QUI NAIT D'UN ACHAT : CE QU'ELLE FAIT, ET CE QU'ELLE REFUSE.

Les VRAIES fonctions sont chargees depuis les fichiers du depot :
  * `api/routes/shared.py` et `api/routes/membership_routes.py` sont importes
    PAR CHEMIN (avec un `fastapi` et un `api.server` bouchons), de sorte que les
    imports differes de `lot2_creer_adhesion_apres_achat`
    (`from api.routes.membership_routes import ...`) trouvent le VRAI module ;
  * `_lot2_verifier_vendeur` est extraite par AST de `api/routes/checkout_routes.py`
    et executee dans un namespace bouchonne (ce fichier ne s'importe pas seul).

Le faux MongoDB modelise LA SEULE chose dont depend l'idempotence de ce lot :
l'unicite du `_id`. `insert_one` leve une erreur portant `code = 11000` quand un
document de meme `_id` existe deja — exactement ce que `lot2_est_doublon`
reconnait, et exactement ce qu'un webhook rejoue declenche en production.

AUCUNE BASE REELLE, AUCUN RESEAU, AUCUNE ECRITURE, AUCUN PAIEMENT.

Lancement :  python3 tests/test_lot2_adhesion_auto.py
"""

import ast
import asyncio
import importlib.util
import io
import os
import re
import sys
import types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests._banc_qr import RESULTATS, verifier, _Collection, _HTTPException  # noqa: E402

SUPER_ADMIN = "contact.artboost@gmail.com"      # = DEFAULT_COACH_ID depuis V244
PARTENAIRE = "partenaire@exemple.com"


# ═══════════════════════════ lecture des sources ════════════════════════════
class _Source(object):
    """Un fichier du depot, lisible par AST — jamais par grep naif."""

    def __init__(self, *chemin):
        self.chemin = os.path.join(RACINE, *chemin)
        self.relatif = os.path.relpath(self.chemin, RACINE)
        self.texte = io.open(self.chemin, encoding="utf-8").read()
        self.arbre = ast.parse(self.texte)
        self.lignes = self.texte.splitlines(True)

    def noeud(self, nom):
        for n in ast.walk(self.arbre):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
                return n
        raise AssertionError("fonction introuvable dans %s : %s" % (self.relatif, nom))

    def extraire(self, nom):
        n = self.noeud(nom)
        return "".join(self.lignes[n.lineno - 1:n.end_lineno])

    def constante(self, nom):
        for n in ast.walk(self.arbre):
            if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == nom:
                return "".join(self.lignes[n.lineno - 1:n.end_lineno])
        raise AssertionError("constante introuvable dans %s : %s" % (self.relatif, nom))

    def enclosant(self, nom_appele):
        """[(fonction appelante, ligne d'appel)] pour chaque appel a `nom_appele`."""
        trouves = []
        for n in ast.walk(self.arbre):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for c in ast.walk(n):
                if isinstance(c, ast.Call):
                    f = c.func
                    vu = (isinstance(f, ast.Name) and f.id == nom_appele) or \
                         (isinstance(f, ast.Attribute) and f.attr == nom_appele)
                    if vu:
                        trouves.append((n.name, c.lineno))
        return trouves

    def lignes_appel(self, motif):
        """Numeros de ligne des appels `xxx.motif(...)` ou `motif(...)`."""
        out = []
        for n in ast.walk(self.arbre):
            if isinstance(n, ast.Call):
                f = n.func
                if (isinstance(f, ast.Attribute) and f.attr == motif) or \
                        (isinstance(f, ast.Name) and f.id == motif):
                    out.append(n.lineno)
        return sorted(out)


SHARED_SRC = _Source("api", "routes", "shared.py")
CAISSE_SRC = _Source("api", "routes", "checkout_routes.py")
SERVEUR_SRC = _Source("api", "server.py")
MEMBRES_SRC = _Source("api", "routes", "membership_routes.py")

LOT2_FONCTIONS = ("lot2_proprietaire", "lot2_fin_adhesion", "lot2_prolonger_fin",
                  "lot2_est_doublon", "lot2_offre_adherente", "lot2_adhesion_active",
                  "lot2_creer_adhesion_apres_achat", "lot2_prix_de_vente")


def _fonctions_lisant_le_prix():
    """Les fonctions LOT 2 qui mentionnent `price`, quelle qu'en soit la forme.

    LOT 2.1 en autorise UNE SEULE : `lot2_prix_de_vente`. Si une autre se met
    un jour a lire le prix, la frontiere entre « borner » et « decider par le
    montant » s'efface — c'est precisement ce que le depot avait refuse.
    La projection Mongo de `lot2_offre_adherente` est exclue : demander un
    champ a la base n'est pas s'en servir pour decider.
    """
    import ast as _ast
    _trouvees = set()
    for _nom in LOT2_FONCTIONS:
        if _nom == "lot2_offre_adherente":
            continue
        _noeud = SHARED_SRC.noeud(_nom)
        for _n in _ast.walk(_noeud):
            if isinstance(_n, _ast.Constant) and _n.value in ("price", "active_price"):
                _trouvees.add(_nom)
            if isinstance(_n, _ast.Attribute) and _n.attr in ("price", "active_price"):
                _trouvees.add(_nom)
    return _trouvees


# ═══════════════════ chargement des VRAIS modules, hors ligne ═══════════════
class _RouteurBouchon(object):
    """`APIRouter` reduit aux deux decorateurs dont membership_routes se sert."""

    def __init__(self, *a, **k):
        self.routes = {}

    def _enr(self, methode, chemin):
        def deco(f):
            self.routes[(methode, chemin)] = f
            return f
        return deco

    def post(self, chemin, **k):
        return self._enr("POST", chemin)

    def get(self, chemin, **k):
        return self._enr("GET", chemin)


_fa = types.ModuleType("fastapi")
_fa.HTTPException = _HTTPException
_fa.APIRouter = _RouteurBouchon
_fa.Request = object
sys.modules["fastapi"] = _fa

sys.modules["api"] = types.ModuleType("api")
sys.modules["api.routes"] = types.ModuleType("api.routes")

# `api.server` n'est PAS charge : il ouvrirait une connexion MongoDB au premier
# import. Les trois fonctions que membership_routes lui demande sont bouchonnees.
_srv = types.ModuleType("api.server")
_srv._v311_coach_email_from_jwt = lambda requete: ""


async def _est_coach(email):
    return bool(email)


_srv._v309_is_coach_or_admin = _est_coach
_srv.is_super_admin = lambda email: (email or "").strip().lower() == SUPER_ADMIN
sys.modules["api.server"] = _srv


def _charger(nom, *chemin):
    spec = importlib.util.spec_from_file_location(nom, os.path.join(RACINE, *chemin))
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


# LOT 2.1 : `api.pricing` est charge POUR DE VRAI, pas bouchonne. C'est lui qui
# resout le prix de vente d'une offre en tarif progressif, et le laisser absent
# ferait tomber `lot2_prix_de_vente` sur son repli — le test mesurerait alors
# le chemin de secours en croyant mesurer le chemin normal. Le module est pur
# (aucun acces base, aucun import de server.py) : il se charge tel quel.
P = _charger("api.pricing", "api", "pricing.py")

# shared AVANT membership_routes : le second importe le premier au chargement.
S = _charger("api.routes.shared", "api", "routes", "shared.py")
M = _charger("api.routes.membership_routes", "api", "routes", "membership_routes.py")


# ═════════════════════════ faux MongoDB (idempotence) ═══════════════════════
class _DuplicateKeyError(Exception):
    """Le double du pilote : ce que Mongo leve sur un `_id` deja pris."""

    def __init__(self, cle):
        self.code = 11000
        super().__init__("E11000 duplicate key error collection: _id_ dup key: %r" % (cle,))


class _CollectionUnique(_Collection):
    """`_Collection` du banc partage, plus l'UNICITE DU `_id` — le verrou du lot."""

    def __init__(self, docs=None):
        _Collection.__init__(self, docs)
        self.panne_insert = None       # exception a lever a la prochaine ecriture
        self.panne_find = None         # exception a lever a la prochaine lecture

    async def insert_one(self, doc):
        if self.panne_insert is not None:
            raise self.panne_insert
        _id = doc.get("_id")
        if _id is not None and any(d.get("_id") == _id for d in self.docs):
            raise _DuplicateKeyError(_id)
        return await _Collection.insert_one(self, doc)

    def find(self, filtre, projection=None):
        if self.panne_find is not None:
            raise self.panne_find
        return _Collection.find(self, filtre, projection)


class _BaseLot2(object):
    """Toutes les collections du depot, creees a la demande. Chacune garde la
    trace de ses ecritures : c'est ainsi qu'on prouve qu'UNE SEULE est touchee."""

    NOMS = ("memberships", "offers", "subscriptions", "discount_codes", "users",
            "reservations", "courses", "checkout_transactions", "code_members",
            "payment_transactions", "chat_sessions", "free_trial_claims")

    def __init__(self):
        self._c = {}
        for n in self.NOMS:
            self._c[n] = _CollectionUnique()

    def __getitem__(self, nom):
        if nom not in self._c:
            self._c[nom] = _CollectionUnique()
        return self._c[nom]

    def __getattr__(self, nom):
        if nom.startswith("_"):
            raise AttributeError(nom)
        return self[nom]

    def ecritures_hors(self, sauf):
        out = {}
        for nom, col in self._c.items():
            if nom != sauf and col.ecritures:
                out[nom] = list(col.ecritures)
        return out


def _offre(oid="offre-entree", **kw):
    d = {"id": oid, "name": "Carte Membre", "price": 250, "coach_id": None}
    d.update(kw)
    return d


def _adhesion(email, debut, fin, coach_id=None, **kw):
    d = {"_id": "manuelle-" + email + debut, "id": "adh-" + debut, "email": email,
         "coach_id": coach_id, "date_debut": debut, "date_fin": fin,
         "source": "saisie_manuelle"}
    d.update(kw)
    return d


async def _acheter(base, email="marie@test.ch", offre_id="offre-entree",
                   sid="sub-1", nom="Marie", moteur="stripe", montant=250,
                   devise="chf"):
    """Le point d'entree unique, appele comme les deux chemins d'autorite l'appellent."""
    return await S.lot2_creer_adhesion_apres_achat(
        base, email=email, offre_id=offre_id, subscription_id=sid,
        nom=nom, moteur=moteur, montant=montant, devise=devise)


JOUR = M.p1a_jour_suisse()
FIN_ATTENDUE = S.lot2_fin_adhesion(JOUR)


# ═══════ 1. UN PAIEMENT NON CONFIRME NE PEUT PAS ATTEINDRE CETTE FONCTION ═══
def test_1_seuls_les_deux_points_dautorite():
    """Preuve par LECTURE DE SOURCE — la seule possible : cette garantie n'est
    pas dans la fonction, elle est dans le fait que RIEN d'autre ne l'appelle."""
    appelants = {}
    for src in (SHARED_SRC, CAISSE_SRC, SERVEUR_SRC, MEMBRES_SRC):
        for nom, ligne in src.enclosant("lot2_creer_adhesion_apres_achat"):
            appelants.setdefault(src.relatif + ":" + nom, []).append(ligne)
        # l'alias `_lot2` sous lequel les deux chemins l'importent
        for nom, ligne in src.enclosant("_lot2"):
            appelants.setdefault(src.relatif + ":" + nom, []).append(ligne)

    attendus = {"api/server.py:stripe_webhook",
                "api/routes/checkout_routes.py:_process_successful_payment"}
    verifier("1. la fonction n'est appelee QUE depuis les deux points d'autorite",
             set(appelants) == attendus, str(sorted(appelants)))

    # Chemin A : apres la garde d'idempotence V384 ET apres l'ecriture du forfait.
    ligne_appel_a = appelants["api/server.py:stripe_webhook"][0]
    ligne_sub_a = [n for n in SERVEUR_SRC.lignes_appel("insert_one")
                   if "subscriptions.insert_one(subscription_data)" in
                   SERVEUR_SRC.lignes[n - 1]]
    verifier("1a. chemin A : l'adhesion vient APRES l'insertion du forfait",
             bool(ligne_sub_a) and min(ligne_sub_a) < ligne_appel_a
             and ligne_appel_a - min(ligne_sub_a) < 60,
             "forfait=%s appel=%s" % (ligne_sub_a, ligne_appel_a))
    ligne_garde = [i + 1 for i, l in enumerate(SERVEUR_SRC.lignes)
                   if 'return {"status": "already_processed"' in l]
    verifier("1b. chemin A : l'adhesion vient APRES la garde d'idempotence V384",
             bool(ligne_garde) and min(ligne_garde) < ligne_appel_a,
             "garde=%s appel=%s" % (ligne_garde, ligne_appel_a))

    # Chemin B : apres l'ecriture du forfait, dans `_process_successful_payment`.
    ligne_appel_b = appelants["api/routes/checkout_routes.py:_process_successful_payment"][0]
    ligne_sub_b = [n for n in CAISSE_SRC.lignes_appel("insert_one")
                   if 'db["subscriptions"]' in CAISSE_SRC.lignes[n - 1]]
    verifier("1c. chemin B : l'adhesion vient APRES l'insertion du forfait",
             bool(ligne_sub_b) and min(ligne_sub_b) < ligne_appel_b,
             "forfait=%s appel=%s" % (ligne_sub_b, ligne_appel_b))

    # Et ce chemin B n'est lui-meme atteint que par des routes de paiement.
    portes = sorted({n for n, _ in CAISSE_SRC.enclosant("_process_successful_payment")})
    verifier("1d. le chemin B n'est servi que par les webhooks et les caisses",
             portes == ["checkout_cinetpay_webhook", "checkout_paypal_webhook",
                        "checkout_stripe_webhook", "create_checkout_session",
                        "free_checkout"], str(portes))

    # Aucune des fonctions LOT 2 n'est elle-meme une route HTTP.
    decorees = [f.name for f in ast.walk(SHARED_SRC.arbre)
                if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
                and f.name in LOT2_FONCTIONS and f.decorator_list]
    verifier("1e. aucune fonction LOT 2 n'est exposee comme route HTTP",
             not decorees, str(decorees))


# ═══════════════ 2 / 6. UN ACHAT CONFIRME CREE L'ADHESION ═══════════════════
async def test_2_6_achat_reussi():
    base = _BaseLot2()
    base.offers.docs.append(_offre(creates_membership=True))
    r = await _acheter(base)
    docs = base.memberships.docs
    verifier("2. paiement reussi -> une adhesion est creee",
             r["cree"] is True and len(docs) == 1)
    verifier("6. la case `creates_membership: True` est la SEULE condition",
             docs and docs[0]["email"] == "marie@test.ch")
    verifier("2a. l'adhesion court du jour au meme jour l'an prochain, moins un",
             docs[0]["date_debut"] == JOUR and docs[0]["date_fin"] == FIN_ATTENDUE,
             "%s -> %s" % (docs[0]["date_debut"], docs[0]["date_fin"]))
    verifier("2b. la source dit que la machine a decide, pas le coach",
             docs[0]["source"] == "achat" and docs[0]["created_by"] == "achat")
    verifier("2c. la preuve d'achat est conservee (forfait + offre)",
             docs[0]["subscription_id"] == "sub-1"
             and docs[0]["offer_id"] == "offre-entree")
    verifier("2d. le verrou d'idempotence porte l'identifiant du forfait",
             docs[0]["_id"] == S.LOT2_VERROU + "sub-1")
    verifier("2e. la trace financiere reutilise le vocabulaire du lot B",
             docs[0].get("montant_encaisse") == 250.0
             and docs[0].get("devise") == "CHF"
             and docs[0].get("origine_paiement") == "stripe")
    verifier("2f. une adhesion n'ouvre AUCUNE seance",
             "seances_a_l_achat" not in docs[0])
    verifier("2g. le document rendu a l'appelant ne porte pas le verrou interne",
             "_id" not in (r["membership"] or {}))


# ═════════ 3. LE MEME WEBHOOK REJOUE TROIS FOIS -> UNE SEULE ADHESION ═══════
async def test_3_rejeu():
    base = _BaseLot2()
    base.offers.docs.append(_offre(creates_membership=True))
    motifs = []
    for _ in range(3):
        r = await _acheter(base)
        motifs.append((r["cree"], r["motif"]))
    verifier("3. webhook rejoue 3 fois -> UNE seule adhesion",
             len(base.memberships.docs) == 1, str(motifs))
    verifier("3a. les rejeux sont refuses, jamais silencieusement doubles",
             motifs[0] == (True, "") and all(m[0] is False for m in motifs[1:]),
             str(motifs))

    # Le verrou `_id` SEUL, sans l'aide de la garde « deja membre » : on pose
    # une adhesion EXPIREE portant deja le verrou de ce paiement. La garde ne la
    # voit pas (elle ne regarde que les actives) ; seule l'unicite du `_id`
    # arrete le rejeu. C'est le cas qui prouve l'atomicite.
    base2 = _BaseLot2()
    base2.offers.docs.append(_offre(creates_membership=True))
    base2.memberships.docs.append(dict(
        _adhesion("marie@test.ch", "2019-01-01", "2019-12-31"),
        _id=S.LOT2_VERROU + "sub-1"))
    r = await _acheter(base2)
    verifier("3b. le verrou `_id` seul (erreur 11000) suffit a arreter un rejeu",
             r["cree"] is False and r["motif"] == "rejeu"
             and len(base2.memberships.docs) == 1, str(r))

    # La reconnaissance de l'erreur ne depend d'aucun message traduit.
    verifier("3c. `lot2_est_doublon` reconnait le code 11000",
             S.lot2_est_doublon(_DuplicateKeyError("x")) is True)

    class DuplicateKeyError(Exception):
        pass

    verifier("3d. ... et le nom de classe du pilote, sans code",
             S.lot2_est_doublon(DuplicateKeyError("y")) is True)
    verifier("3e. ... et rien d'autre : une panne reseau n'est pas un rejeu",
             S.lot2_est_doublon(RuntimeError("connexion perdue")) is False)


# ═══════════ 4 / 5. CE QUI NE DOIT RIEN CREER : L'IMMENSE MAJORITE ══════════
async def test_4_5_aucune_creation():
    base = _BaseLot2()
    base.offers.docs.append(_offre("offre-entree", creates_membership=True))

    r = await _acheter(base, offre_id="offre-qui-nexiste-pas", sid="sub-x")
    verifier("4. un `offer_id` inconnu ne cree AUCUNE adhesion",
             r["cree"] is False and not base.memberships.docs, str(r))
    verifier("4a. le motif rendu appartient au vocabulaire declare",
             r["motif"] in S.LOT2_MOTIFS, r["motif"])

    # Honnetete : `LOT2_MOTIFS` declare « offre_introuvable », mais le code ne
    # l'emet JAMAIS — introuvable et non-cochee rendent le meme motif. On le
    # mesure au lieu de le supposer.
    motifs_emis = set()
    for n in ast.walk(SHARED_SRC.noeud("lot2_creer_adhesion_apres_achat")):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) \
                and isinstance(n.value.value, str):
            motifs_emis.add(n.value.value)
    verifier("4b. un identifiant inconnu rend `offre_introuvable`, DISTINCT de "
             "« la case n'est pas cochee » (les journaux doivent pouvoir les separer)",
             r["motif"] == "offre_introuvable", r["motif"])

    # 5. Une offre payante ordinaire : rien.
    base.offers.docs.append(_offre("offre-30", price=30))
    r = await _acheter(base, offre_id="offre-30", sid="sub-30", montant=30)
    verifier("5. une offre a 30 CHF sans la case ne cree AUCUNE adhesion",
             r["cree"] is False and r["motif"] == "offre_non_adherente"
             and not base.memberships.docs)

    # `is True` strict : une valeur « presque vraie » ne suffit pas.
    for valeur, libelle in ((None, "absente"), (False, "a false"), ("true", "a la chaine « true »"),
                            (1, "a 1"), ("True", "a la chaine « True »")):
        base.offers.docs.append(_offre("o-" + str(valeur), creates_membership=valeur))
        r = await _acheter(base, offre_id="o-" + str(valeur), sid="s-" + str(valeur))
        verifier("5%s. case %s -> aucune adhesion (comparaison stricte a True)"
                 % ("abcde"[("None", "False", "true", "1", "True").index(str(valeur))], libelle),
                 r["cree"] is False and not base.memberships.docs, str(r))

    # Donnees incompletes : ni e-mail, ni forfait, ni offre -> rien.
    for libelle, kw in (("e-mail absent", {"email": ""}),
                        ("forfait absent", {"sid": ""}),
                        ("offre absente", {"offre_id": ""})):
        r = await _acheter(base, **kw)
        verifier("5f. %s -> motif `donnees_incompletes`, rien d'ecrit" % libelle,
                 r["cree"] is False and r["motif"] == "donnees_incompletes"
                 and not base.memberships.docs)


# ═══════════ 7. LE PRIX N'INTERVIENT NULLE PART DANS LA DECISION ════════════
async def test_7_le_prix_ne_decide_rien():
    base = _BaseLot2()
    base.offers.docs.append(_offre("pulse", price=250, creates_membership=True))
    r1 = await _acheter(base, email="a@test.ch", offre_id="pulse", sid="sub-a", montant=250)

    # Le coach monte son prix. La case n'a pas bouge.
    base.offers.docs[0]["price"] = 260
    r2 = await _acheter(base, email="b@test.ch", offre_id="pulse", sid="sub-b", montant=260)

    verifier("7. prix passe de 250 a 260, case inchangee -> adhesion quand meme",
             r1["cree"] is True and r2["cree"] is True
             and len(base.memberships.docs) == 2)
    verifier("7a. le prix est ENREGISTRE, jamais consulte pour decider",
             base.memberships.docs[0]["montant_encaisse"] == 250.0
             and base.memberships.docs[1]["montant_encaisse"] == 260.0)
    verifier("7b. aucun champ `price` n'est recopie sur l'adhesion",
             "price" not in base.memberships.docs[0])

    # LOT 2.1 — RENVERSEMENT ASSUME DE CE SEUL POINT. Cette verification
    # affirmait l'inverse (« une offre a 0 CHF cochee cree une adhesion »).
    # Elle disait vrai du LOT 2, et c'etait le trou : un coach qui cochait la
    # case sur son essai gratuit offrait un an d'adhesion a chaque visiteur.
    # Ce qui l'entoure n'a PAS change : le prix ne sert toujours pas a
    # identifier une offre (7, 7a, 7e), il ne sert que de borne basse.
    base.offers.docs.append(_offre("gratuite", price=0, creates_membership=True))
    r3 = await _acheter(base, email="c@test.ch", offre_id="gratuite", sid="sub-c",
                        moteur="free", montant=0)
    verifier("7c. LOT 2.1 : une offre a 0 CHF cochee ne cree AUCUNE adhesion",
             r3["cree"] is False and r3["motif"] == "offre_gratuite",
             str(r3))
    verifier("7c1. ... et rien n'est ecrit en base",
             len(base.memberships.docs) == 2)

    # Un achat PAYANT qui n'encaisse rien est refuse LUI AUSSI, mais sous un
    # motif DIFFERENT : « l'offre se donne » est une configuration a corriger,
    # « rien n'a ete encaisse » est un fait comptable sur cet achat-la.
    r4 = await _acheter(base, email="d@test.ch", offre_id="pulse", sid="sub-d",
                        moteur="stripe", montant=0)
    verifier("7c2. offre payante mais 0 encaisse -> refus, motif `montant_nul`",
             r4["cree"] is False and r4["motif"] == "montant_nul", str(r4))

    # LE FAUX REFUS, qui serait pire que le defaut corrige : un montant INCONNU
    # (None) ne doit jamais etre pris pour une gratuite. `None <= 0` leverait
    # d'ailleurs un TypeError, maquille en `echec_ecriture` par le catch-all.
    r5 = await _acheter(base, email="e@test.ch", offre_id="pulse", sid="sub-e",
                        moteur="stripe", montant=None)
    verifier("7c3. montant INCONNU (None) sur offre payante -> adhesion creee",
             r5["cree"] is True, str(r5))

    # Le moteur « free » est un signal INDEPENDANT du montant : il tient meme
    # si un chemin gratuit oubliait un jour de transmettre `total=0`.
    r6 = await _acheter(base, email="f@test.ch", offre_id="pulse", sid="sub-f",
                        moteur="free", montant=250)
    verifier("7c4. moteur `free` sur offre payante -> refus malgre le montant",
             r6["cree"] is False and r6["motif"] == "montant_nul", str(r6))

    # LE PIEGE QUE LA GARDE NE DOIT PAS TOMBER : une offre en tarif progressif
    # porte `price: 0` en base et se vend pourtant. Mesure du 20/08/2026 sur la
    # production : « Afroboost Silent » -> price 0.0, prix reel 15 CHF. Se fier
    # a `price` brut lui refuserait son adhesion.
    _progressive = _offre("progressive", price=0, creates_membership=True)
    _progressive.update({"progressive_pricing": True, "countdown_date": "2099-01-01",
                         "countdown_time": "00:00", "price_early_bird": 15,
                         "price_standard": 20, "price_last_minute": 25})
    base.offers.docs.append(_progressive)
    r7 = await _acheter(base, email="g@test.ch", offre_id="progressive", sid="sub-g",
                        moteur="stripe", montant=15)
    verifier("7c5. offre a `price: 0` mais vendue 15 CHF (tarif progressif) "
             "-> adhesion CREEE, aucun faux refus",
             r7["cree"] is True, str(r7))

    # Mesure sur le CODE : aucune fonction LOT 2 ne lit un prix, ni ne compare
    # a un montant. Les commentaires en parlent — le code, jamais.
    lus, nombres = set(), set()
    for nom in LOT2_FONCTIONS:
        noeud = SHARED_SRC.noeud(nom)
        for n in ast.walk(noeud):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) \
                    and n.value in ("price", "active_price", "amount", "montant_offre"):
                lus.add(n.value)
            if isinstance(n, ast.Attribute) and n.attr in ("price", "active_price"):
                lus.add(n.attr)
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) \
                    and not isinstance(n.value, bool) and n.value in (30, 150, 250, 260):
                nombres.add(n.value)
    # LOT 2.1 : le prix EST desormais lu — mais par UNE seule fonction, celle
    # qui resout le prix de vente. Aucune autre n'y touche : c'est la
    # difference entre « borner » et « decider a partir du montant ».
    verifier("7d. LOT 2.1 : seule `lot2_prix_de_vente` lit le prix, "
             "aucune autre fonction LOT 2 n'y touche",
             lus <= {"price"} and _fonctions_lisant_le_prix() == {"lot2_prix_de_vente"},
             f"champs lus={sorted(lus)} fonctions={sorted(_fonctions_lisant_le_prix())}")
    # CELLE-CI NE CHANGE PAS, et c'est elle qui garantit que le prix ne sert
    # pas d'identite : aucune comparaison a un montant precis.
    verifier("7e. aucun montant en dur (250 / 260 / 150) dans le code LOT 2",
             not nombres, str(sorted(nombres)))
    # LOT 2.1 : la projection demande maintenant le prix ET de quoi resoudre un
    # tarif progressif — sans ces champs, une offre a `price: 0` vendue 15 CHF
    # serait prise pour gratuite (cas reel « Afroboost Silent », 20/08/2026).
    _proj = SHARED_SRC.extraire("lot2_offre_adherente")
    verifier("7f. LOT 2.1 : la lecture d'offre demande le prix ET les champs "
             "de tarif progressif",
             all(c in _proj for c in ('"price"', '"progressive_pricing"',
                                      '"price_early_bird"', '"price_standard"',
                                      '"price_last_minute"', '"countdown_date"')),
             "projection incomplete : un tarif progressif serait lu comme gratuit")


# ═══════════ 8 / 9. LE PROPRIETAIRE VIENT DE L'OFFRE, ET DE LA SEULE ════════
async def test_8_9_proprietaire():
    base = _BaseLot2()
    base.offers.docs.append(_offre("o-part", coach_id="Partenaire@Exemple.com",
                                   creates_membership=True))
    r = await _acheter(base, email="client@part.ch", offre_id="o-part", sid="sub-p")
    verifier("8. offre avec proprietaire -> adhesion a CE proprietaire",
             r["cree"] is True and base.memberships.docs[0]["coach_id"] == PARTENAIRE,
             str(base.memberships.docs[0]["coach_id"]))
    verifier("8a. le proprietaire est normalise (trim + minuscules)",
             S.lot2_proprietaire("  Partenaire@Exemple.COM ") == PARTENAIRE)

    # 9. Les TROIS formes de « sans proprietaire » donnent la MEME : None.
    for libelle, offre in (("null", _offre("o-null", coach_id=None, creates_membership=True)),
                           ("vide", _offre("o-vide", coach_id="", creates_membership=True)),
                           ("espaces", _offre("o-esp", coach_id="   ", creates_membership=True))):
        base.offers.docs.append(offre)
    offre_absente = _offre("o-abs", creates_membership=True)
    offre_absente.pop("coach_id")
    base.offers.docs.append(offre_absente)

    for i, (oid, libelle) in enumerate((("o-null", "null"), ("o-vide", "vide"),
                                        ("o-esp", "espaces"), ("o-abs", "champ absent"))):
        base2 = _BaseLot2()
        base2.offers.docs.extend(base.offers.docs)
        r = await _acheter(base2, email="x%d@test.ch" % i, offre_id=oid, sid="s%d" % i)
        doc = base2.memberships.docs[0]
        verifier("9%s. `coach_id` %s -> adhesion a None, jamais l'adresse super-admin"
                 % ("abcd"[i], libelle),
                 r["cree"] is True and doc["coach_id"] is None
                 and SUPER_ADMIN not in [v for v in doc.values() if isinstance(v, str)],
                 repr(doc["coach_id"]))

    verifier("9e. lot2_proprietaire : tout ce qui n'est pas une chaine utile -> None",
             all(S.lot2_proprietaire(v) is None
                 for v in (None, "", "   ", 0, False, [], {}, 12)))

    # Et le repli interdit : `DEFAULT_COACH_ID` (= l'adresse super-admin depuis
    # V244) n'est nomme nulle part dans le code LOT 2.
    noms = set()
    for nom in LOT2_FONCTIONS:
        for n in ast.walk(SHARED_SRC.noeud(nom)):
            if isinstance(n, ast.Name):
                noms.add(n.id)
    verifier("9f. `DEFAULT_COACH_ID` n'est nomme dans AUCUNE fonction LOT 2",
             "DEFAULT_COACH_ID" not in noms)

    # L'adhesion ecrite est bien VISIBLE par l'ecran Adhesions : meme regle de
    # propriete, importee et non recopiee.
    base3 = _BaseLot2()
    base3.offers.docs.append(_offre("o-null", coach_id=None, creates_membership=True))
    await _acheter(base3, email="visible@test.ch", offre_id="o-null", sid="s-vis")
    doc = base3.memberships.docs[0]
    from tests._banc_qr import _match as _correspond
    verifier("9g. l'adhesion creee est VISIBLE par le filtre de l'ecran Adhesions",
             _correspond(doc, M.p1a_filtre_proprietaire(None)))
    verifier("9h. ... et INVISIBLE pour un partenaire tiers (fail closed)",
             not _correspond(doc, M.p1a_filtre_proprietaire(PARTENAIRE)))


# ═════════ 10. ANTI-FUITE : LE VENDEUR DECLARE DOIT POUVOIR VENDRE ══════════
def _garde_vendeur(base):
    """`_lot2_verifier_vendeur`, extraite du VRAI checkout_routes.py."""
    ns = {"db": base, "HTTPException": _HTTPException,
          "logger": types.SimpleNamespace(warning=lambda *a, **k: None,
                                          info=lambda *a, **k: None,
                                          error=lambda *a, **k: None),
          "is_super_admin": lambda e: (e or "").strip().lower() == SUPER_ADMIN}
    exec(compile(CAISSE_SRC.constante("LOT2_MSG_VENDEUR"), CAISSE_SRC.chemin, "exec"), ns)
    exec(compile(CAISSE_SRC.extraire("_lot2_verifier_vendeur"), CAISSE_SRC.chemin, "exec"), ns)
    return ns["_lot2_verifier_vendeur"]


async def test_10_anti_fuite_vendeur():
    base = _BaseLot2()
    base.offers.docs.extend([
        _offre("o-part", coach_id=PARTENAIRE),
        _offre("o-maison", coach_id=None),
        _offre("o-vide", coach_id=""),
    ])
    garde = _garde_vendeur(base)

    async def refuse(items, vendeur):
        try:
            await garde(items, vendeur)
            return None
        except _HTTPException as err:
            return err

    err = await refuse([{"id": "o-part"}], "voleur@ailleurs.com")
    verifier("10. un vendeur qui n'est pas le proprietaire est refuse en 403",
             err is not None and err.status_code == 403, str(err and err.status_code))

    verifier("10a. le proprietaire reel, lui, passe",
             await refuse([{"id": "o-part"}], PARTENAIRE) is None)
    verifier("10b. le proprietaire reel passe quelle que soit la casse",
             await refuse([{"id": "o-part"}], "  Partenaire@Exemple.COM ") is None)
    verifier("10c. offre sans proprietaire + vendeur vide -> accepte",
             await refuse([{"id": "o-maison"}], "") is None
             and await refuse([{"id": "o-vide"}], "") is None)
    verifier("10d. offre sans proprietaire + super-admin -> accepte",
             await refuse([{"id": "o-maison"}], SUPER_ADMIN) is None)
    verifier("10e. offre sans proprietaire + partenaire tiers -> REFUSE",
             (await refuse([{"id": "o-maison"}], PARTENAIRE)) is not None)
    verifier("10f. offre inconnue -> la garde ne tranche pas, elle laisse passer",
             await refuse([{"id": "offre-libre"}], PARTENAIRE) is None)
    verifier("10g. article sans identifiant -> ignore",
             await refuse([{"name": "article libre"}], PARTENAIRE) is None)
    verifier("10h. un panier mixte est refuse des qu'UN article ne va pas",
             (await refuse([{"id": "o-maison"}, {"id": "o-part"}], SUPER_ADMIN)) is not None)

    # La garde est posee sur LES DEUX portes, et AVANT toute ecriture.
    portes = sorted({n for n, _ in CAISSE_SRC.enclosant("_lot2_verifier_vendeur")
                     if n != "_lot2_verifier_vendeur"})
    verifier("10i. la garde est posee sur LES DEUX portes de la caisse",
             portes == ["create_checkout_session", "free_checkout"], str(portes))
    for porte in portes:
        noeud = CAISSE_SRC.noeud(porte)
        ligne_garde = min(l for n, l in CAISSE_SRC.enclosant("_lot2_verifier_vendeur")
                          if n == porte)
        ecritures = [n.lineno for n in ast.walk(noeud) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Attribute)
                     and n.func.attr in ("insert_one", "update_one", "update_many")]
        verifier("10j. `%s` : la garde precede toute ecriture" % porte,
                 not ecritures or ligne_garde < min(ecritures),
                 "garde=%d ecritures=%s" % (ligne_garde, ecritures))

    # La garde ne touche a rien : elle lit `offers`, et n'ecrit nulle part.
    verifier("10k. la garde n'ecrit dans AUCUNE collection",
             not base.ecritures_hors("memberships") and not base.memberships.ecritures,
             str(base.ecritures_hors("memberships")))


# ══════════ 11 / 12. UNE ADHESION ACTIVE N'EST NI DOUBLEE NI PROLONGEE ══════
async def test_11_12_deja_membre():
    base = _BaseLot2()
    base.offers.docs.append(_offre("o", coach_id=None, creates_membership=True))
    base.memberships.docs.append(_adhesion("marie@test.ch", "2026-01-01", "2099-12-31"))
    avant = [dict(d) for d in base.memberships.docs]

    r = await _acheter(base, email="Marie@Test.CH", offre_id="o", sid="sub-neuf")
    verifier("11. adhesion deja active -> rien de cree, motif `deja_membre`",
             r["cree"] is False and r["motif"] == "deja_membre"
             and len(base.memberships.docs) == 1, str(r["motif"]))
    verifier("11a. l'adhesion existante n'est ni prolongee ni modifiee",
             base.memberships.docs == avant)
    verifier("11b. aucune ecriture du tout n'a eu lieu",
             not base.memberships.ecritures)
    verifier("11c. l'adhesion en cours est rendue a l'appelant, pour les journaux",
             (r["membership"] or {}).get("date_fin") == "2099-12-31")

    # Une adhesion active chez UN AUTRE proprietaire ne bloque pas : la propriete
    # est symetrique des deux cotes.
    base2 = _BaseLot2()
    base2.offers.docs.append(_offre("o", coach_id=None, creates_membership=True))
    base2.memberships.docs.append(_adhesion("marie@test.ch", "2026-01-01", "2099-12-31",
                                            coach_id=PARTENAIRE))
    r = await _acheter(base2, offre_id="o", sid="sub-autre")
    verifier("11d. une adhesion active chez un AUTRE proprietaire ne bloque pas",
             r["cree"] is True and len(base2.memberships.docs) == 2)

    # 12. Expiree : une nouvelle adhesion est bien creee.
    base3 = _BaseLot2()
    base3.offers.docs.append(_offre("o", coach_id=None, creates_membership=True))
    base3.memberships.docs.append(_adhesion("marie@test.ch", "2024-01-01", "2024-12-31"))
    r = await _acheter(base3, offre_id="o", sid="sub-renouv")
    verifier("12. adhesion expiree -> une NOUVELLE adhesion est creee",
             r["cree"] is True and len(base3.memberships.docs) == 2)
    verifier("12a. l'ancienne n'est pas touchee (aucune mise a jour)",
             all(e[0] == "insert" for e in base3.memberships.ecritures),
             str([e[0] for e in base3.memberships.ecritures]))
    verifier("12b. la nouvelle repart d'aujourd'hui, pas de la fin de l'ancienne",
             base3.memberships.docs[1]["date_debut"] == JOUR)

    # Une adhesion FUTURE n'est pas active — mais elle n'est pas non plus une
    # raison de ne rien faire : mesure du comportement reel, pas d'une intention.
    base4 = _BaseLot2()
    base4.offers.docs.append(_offre("o", coach_id=None, creates_membership=True))
    base4.memberships.docs.append(_adhesion("marie@test.ch", "2099-01-01", "2099-12-31"))
    r = await _acheter(base4, offre_id="o", sid="sub-futur")
    verifier("12c. une adhesion FUTURE n'est pas « active » : l'achat en cree une",
             r["cree"] is True and len(base4.memberships.docs) == 2)


# ══════════════ 13. LE STATUT EST CALCULE, JAMAIS STOCKE ════════════════════
async def test_13_statut_jamais_stocke():
    base = _BaseLot2()
    base.offers.docs.append(_offre("o", coach_id=None, creates_membership=True))
    await _acheter(base, offre_id="o", sid="sub-1")
    doc = base.memberships.docs[0]
    verifier("13. aucun champ `statut` n'est ecrit en base", "statut" not in doc)
    verifier("13a. aucun booleen d'appartenance non plus",
             not any(c in doc for c in ("is_member", "active", "est_membre", "membre")))
    verifier("13b. le code retire explicitement tout `statut` avant d'ecrire",
             '_doc.pop("statut", None)' in
             SHARED_SRC.extraire("lot2_creer_adhesion_apres_achat"))
    verifier("13c. la lecture recalcule le statut a partir des dates",
             M.p1a_statut(doc["date_debut"], doc["date_fin"], JOUR) == "active")

    # Et la garde « deja membre » recalcule elle aussi : un document qui MENT
    # avec `statut: active` mais des dates finies ne bloque pas un nouvel achat.
    base2 = _BaseLot2()
    base2.offers.docs.append(_offre("o", coach_id=None, creates_membership=True))
    base2.memberships.docs.append(_adhesion("marie@test.ch", "2019-01-01", "2019-12-31",
                                            statut="active"))
    r = await _acheter(base2, offre_id="o", sid="sub-menteur")
    verifier("13d. un `statut: active` ecrit en base est IGNORE (les dates font foi)",
             r["cree"] is True and len(base2.memberships.docs) == 2)


# ═════════════════ DATES : LES EXEMPLES DU PROPRIETAIRE ═════════════════════
def test_dates():
    verifier("D1. 19/08/2026 -> 18/08/2027",
             S.lot2_fin_adhesion("2026-08-19") == "2027-08-18",
             S.lot2_fin_adhesion("2026-08-19"))
    verifier("D2. 01/01/2026 -> 31/12/2026",
             S.lot2_fin_adhesion("2026-01-01") == "2026-12-31",
             S.lot2_fin_adhesion("2026-01-01"))
    verifier("D3. bornes INCLUSES : active le premier jour",
             M.p1a_statut("2026-08-19", "2027-08-18", "2026-08-19") == "active")
    verifier("D4. bornes INCLUSES : active le dernier jour",
             M.p1a_statut("2026-08-19", "2027-08-18", "2027-08-18") == "active")
    verifier("D5. et expiree le lendemain, pas avant",
             M.p1a_statut("2026-08-19", "2027-08-18", "2027-08-19") == "expiree")
    verifier("D6. une annee bornes incluses fait bien 365 jours",
             (__import__("datetime").date(2027, 8, 18)
              - __import__("datetime").date(2026, 8, 19)).days + 1 == 365)

    # LE 29 FEVRIER — la seule date qui fait lever `replace(year=+1)`.
    verifier("D7. 29/02/2028 -> 28/02/2029 (et non 27/02)",
             S.lot2_fin_adhesion("2028-02-29") == "2029-02-28",
             S.lot2_fin_adhesion("2028-02-29"))
    verifier("D8. le 29 fevrier donne bien une annee pleine (366 jours bornes incluses)",
             (__import__("datetime").date(2029, 2, 28)
              - __import__("datetime").date(2028, 2, 29)).days + 1 == 366)
    verifier("D9. la veille du 29 fevrier suit la regle ordinaire",
             S.lot2_fin_adhesion("2028-02-28") == "2029-02-27")

    # Une date illisible ne produit JAMAIS une adhesion sans fin.
    for mauvaise in ("", None, "hier", "2026-13-45", "19/08/2026", 12345):
        verifier("D10. date de debut illisible (%r) -> \"\", jamais une fin inventee"
                 % (mauvaise,), S.lot2_fin_adhesion(mauvaise) == "")


async def test_date_illisible_ne_cree_rien():
    """La fin incalculable arrete la creation — mesuree, pas supposee."""
    base = _BaseLot2()
    base.offers.docs.append(_offre("o", coach_id=None, creates_membership=True))
    vrai_jour = M.p1a_jour_suisse
    M.p1a_jour_suisse = lambda: "pas-une-date"
    try:
        r = await _acheter(base, offre_id="o", sid="sub-nul")
    finally:
        M.p1a_jour_suisse = vrai_jour
    verifier("D11. une date de fin incalculable n'ecrit RIEN",
             r["cree"] is False and r["motif"] == "donnees_incompletes"
             and not base.memberships.docs, str(r))


# ═══════════ PROLONGATION : ECRITE, TESTEE, ET VOLONTAIREMENT INACTIVE ══════
def test_prolongation_inactive():
    verifier("P1. lot2_prolonger_fin('2026-12-31') -> '2027-12-31'",
             S.lot2_prolonger_fin("2026-12-31") == "2027-12-31",
             S.lot2_prolonger_fin("2026-12-31"))
    verifier("P2. la prolongation DEPLACE la fin d'un an, sans « -1 jour »",
             S.lot2_prolonger_fin("2026-08-18") == "2027-08-18")
    verifier("P3. le 29 fevrier se prolonge au 28/02",
             S.lot2_prolonger_fin("2028-02-29") == "2029-02-28")
    verifier("P4. une date illisible ne prolonge rien",
             S.lot2_prolonger_fin("demain") == "" and S.lot2_prolonger_fin(None) == "")

    # LA PREUVE D'INACTIVITE : personne, dans tout `api/`, ne l'appelle ni ne
    # l'importe. Mesure AST (un appel), plus une mesure textuelle (un import).
    appels, imports = [], []
    for chemin in _fichiers_api():
        texte = io.open(chemin, encoding="utf-8").read()
        if "lot2_prolonger_fin" not in texte:
            continue
        relatif = os.path.relpath(chemin, RACINE)
        arbre = ast.parse(texte)
        for n in ast.walk(arbre):
            if isinstance(n, ast.Call):
                f = n.func
                if (isinstance(f, ast.Name) and f.id == "lot2_prolonger_fin") or \
                        (isinstance(f, ast.Attribute) and f.attr == "lot2_prolonger_fin"):
                    appels.append("%s:%d" % (relatif, n.lineno))
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                for a in n.names:
                    if a.name == "lot2_prolonger_fin":
                        imports.append("%s:%d" % (relatif, n.lineno))
    verifier("P5. AUCUN fichier de api/ n'APPELLE `lot2_prolonger_fin`",
             not appels, str(appels))
    verifier("P6. AUCUN fichier de api/ ne l'IMPORTE non plus",
             not imports, str(imports))
    # Et aucune mise a jour d'adhesion existante nulle part : la prolongation
    # n'est pas non plus faite « a la main » sous un autre nom.
    maj = []
    for nom in LOT2_FONCTIONS:
        for n in ast.walk(SHARED_SRC.noeud(nom)):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                    and n.func.attr in ("update_one", "update_many", "replace_one",
                                        "find_one_and_update", "delete_one", "delete_many"):
                maj.append("%s:%s" % (nom, n.func.attr))
    verifier("P7. aucune fonction LOT 2 ne MODIFIE ni ne SUPPRIME un document",
             not maj, str(maj))


# ════════ LA FONCTION N'ECRIT QUE DANS `memberships`, ET NE LEVE JAMAIS ═════
def test_ecrit_uniquement_memberships():
    """Mesure sur le CODE : chaque ecriture vise `db["memberships"]`."""
    cibles = set()
    for nom in LOT2_FONCTIONS:
        for n in ast.walk(SHARED_SRC.noeud(nom)):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                    and n.func.attr in ("insert_one", "insert_many", "update_one",
                                        "update_many", "delete_one", "delete_many",
                                        "replace_one", "bulk_write"):
                cible = n.func.value
                if isinstance(cible, ast.Subscript) and isinstance(cible.slice, ast.Constant):
                    cibles.add(cible.slice.value)
                elif isinstance(cible, ast.Attribute):
                    cibles.add("db." + cible.attr)
                else:
                    cibles.add("?" + ast.dump(cible)[:40])
    verifier("E1. la SEULE collection ecrite par LOT 2 est `memberships`",
             cibles == {"memberships"}, str(sorted(cibles)))

    lues = set()
    for nom in LOT2_FONCTIONS:
        for n in ast.walk(SHARED_SRC.noeud(nom)):
            if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) \
                    and n.value.id == "db" and isinstance(n.slice, ast.Constant):
                lues.add(n.slice.value)
    verifier("E2. les seules collections LUES sont `offers` et `memberships`",
             lues == {"offers", "memberships"}, str(sorted(lues)))


async def test_ecritures_reelles_et_jamais_de_levee():
    base = _BaseLot2()
    base.offers.docs.append(_offre("o", coach_id=None, creates_membership=True))
    base.subscriptions.docs.append({"id": "sub-1", "email": "marie@test.ch"})
    base.discount_codes.docs.append({"code": "AFR-XXX", "assignedEmail": "marie@test.ch"})
    await _acheter(base, offre_id="o", sid="sub-1")
    verifier("E3. a l'execution, AUCUNE autre collection n'est ecrite",
             not base.ecritures_hors("memberships"),
             str(base.ecritures_hors("memberships")))
    verifier("E4. et `memberships` n'a recu que des insertions",
             [e[0] for e in base.memberships.ecritures] == ["insert"])

    # La base tombe a l'ECRITURE : le paiement ne doit pas en souffrir.
    base2 = _BaseLot2()
    base2.offers.docs.append(_offre("o", coach_id=None, creates_membership=True))
    base2.memberships.panne_insert = RuntimeError("Atlas indisponible")
    r = await _acheter(base2, offre_id="o", sid="sub-2")
    verifier("E5. une panne d'ECRITURE ne leve pas : motif `echec_ecriture`",
             r["cree"] is False and r["motif"] == "echec_ecriture", str(r))

    # La base tombe a la LECTURE des adhesions (la fonction interne, elle, leve).
    base3 = _BaseLot2()
    base3.offers.docs.append(_offre("o", coach_id=None, creates_membership=True))
    base3.memberships.panne_find = RuntimeError("Atlas indisponible")
    r = await _acheter(base3, offre_id="o", sid="sub-3")
    verifier("E6. une panne de LECTURE ne leve pas non plus, et n'ecrit rien",
             r["cree"] is False and r["motif"] == "echec_ecriture"
             and not base3.memberships.docs, str(r))

    # Argument nul, base absente : toujours pas de levee.
    for libelle, appel in (
            ("db = None", S.lot2_creer_adhesion_apres_achat(None, "a@b.ch", "o", "s")),
            ("email non-chaine", S.lot2_creer_adhesion_apres_achat(_BaseLot2(), 42, "o", "s")),
            ("offre non-chaine", S.lot2_creer_adhesion_apres_achat(_BaseLot2(), "a@b.ch",
                                                                  {"x": 1}, "s"))):
        leve = None
        try:
            resultat = await appel
        except Exception as err:                                   # noqa: BLE001
            leve, resultat = err, None
        verifier("E7. (%s) la fonction ne leve JAMAIS, elle rend un dict" % libelle,
                 leve is None and isinstance(resultat, dict)
                 and resultat.get("cree") is False, str(leve))

    # Toute sortie porte un motif du vocabulaire declare (ou "" si creee).
    verifier("E8. le vocabulaire des motifs est ferme et documente",
             set(S.LOT2_MOTIFS) == {"donnees_incompletes", "offre_introuvable",
                                    "offre_non_adherente", "deja_membre", "rejeu",
                                    "echec_ecriture",
                                    # LOT 2.1 : deux refus de plus, volontairement
                                    # DISTINCTS l'un de l'autre — « l'offre se
                                    # donne » se corrige dans le dashboard,
                                    # « rien n'a ete encaisse » est un fait
                                    # comptable sur cet achat-la.
                                    "offre_gratuite", "montant_nul"},
             str(S.LOT2_MOTIFS))


# ═══════════════════ 14. AUCUNE NOUVELLE PAGE, AUCUN ONGLET ═════════════════
def _lire_front(*chemin):
    return io.open(os.path.join(RACINE, "frontend", "src", *chemin), encoding="utf-8").read()


def _bloc_autour(texte, ancre, avant=4, apres=12):
    """Les quelques lignes qui entourent une ancre — le BLOC ajoute par le lot,
    et lui seul. Mesurer le fichier entier melangerait le code deja livre."""
    lignes = texte.splitlines()
    for i, l in enumerate(lignes):
        if ancre in l:
            return "\n".join(lignes[max(0, i - avant):i + apres + 1])
    return ""


def test_14_aucune_nouvelle_page():
    dashboard = _lire_front("components", "CoachDashboard.js")

    # La case vit dans le formulaire d'offre EXISTANT.
    wizard = _lire_front("components", "dashboard", "OfferWizard.js")
    verifier("14. la case vit dans le formulaire d'offre existant",
             'data-testid="offer-creates-membership"' in wizard)

    # CoachDashboard : `creates_membership` n'apparait QUE dans l'enregistrement
    # et la remise a zero d'une offre — jamais dans une entree de navigation.
    # LOT 2 FIX : TROIS lignes, et non deux. La troisieme est le RECHARGEMENT
    # dans `startEditOffer` — son absence etait un bug : rouvrir une offre
    # `creates_membership: true` affichait la case DECOCHEE, et la sauvegarde
    # suivante remettait le champ a `false` en base. Les trois roles, et il n'y
    # en a pas d'autre : (1) relecture a l'ouverture du formulaire,
    # (2) envoi a l'enregistrement, (3) remise a zero pour l'offre suivante.
    # La garde qui compte reste la seconde : jamais dans une entree de
    # navigation.
    lignes = [l.strip() for l in dashboard.splitlines() if "creates_membership" in l]
    verifier("14a. `creates_membership` n'apparait que dans le formulaire d'offre "
             "(3 lignes : relecture, envoi, remise a zero), jamais dans un onglet",
             len(lignes) == 3 and not any(
                 ("id:" in l) or ("label:" in l) or ("icon:" in l) for l in lignes),
             str(lignes))

    # Aucune entree de navigation neuve : les identifiants d'onglets du fichier
    # ne comportent rien de « membre / adhesion » hormis l'onglet `adhesions`
    # livre par P1-bis-a (deja commite, deja teste ailleurs).
    ids = set(re.findall(r"\{\s*id:\s*'([a-z0-9_-]+)'", dashboard))
    neufs = {i for i in ids if ("membre" in i or "member" in i or "lot2" in i)}
    verifier("14b. aucun onglet neuf « membre » n'est ajoute", not neufs, str(sorted(neufs)))
    verifier("14c. le seul onglet d'adhesions reste celui de P1-bis-a",
             "adhesions" in ids and "AdhesionsManager" in dashboard)

    # Aucun composant neuf : les seuls fichiers front qui parlent de LOT 2 sont
    # des ecrans qui existaient DEJA.
    porteurs = set()
    for dossier, _, fichiers in os.walk(os.path.join(RACINE, "frontend", "src")):
        for nom in fichiers:
            if not nom.endswith((".js", ".jsx")):
                continue
            chemin = os.path.join(dossier, nom)
            texte = io.open(chemin, encoding="utf-8").read()
            if "creates_membership" in texte or "LOT 2" in texte:
                porteurs.add(os.path.relpath(chemin, RACINE))
    attendus = {"frontend/src/components/CoachDashboard.js",
                "frontend/src/components/dashboard/OfferWizard.js",
                "frontend/src/components/dashboard/ContactsManager.js",
                "frontend/src/components/dashboard/CarteContact.js",
                "frontend/src/components/dashboard/FicheContact.js"}
    verifier("14d. LOT 2 ne touche que des ecrans EXISTANTS (aucun fichier neuf)",
             porteurs == attendus, str(sorted(porteurs - attendus)))

    # Aucune route neuve dans la vitrine.
    app = _lire_front("App.js")
    verifier("14e. aucune route neuve dans App.js",
             "adhesion" not in app.lower() or "creates_membership" not in app)

    # Le badge « Membre » ne s'affiche que sur une adhesion ACTIVE — les trois
    # ecrans disent la meme chose, ou aucun badge n'apparait.
    contacts = _lire_front("components", "dashboard", "ContactsManager.js")
    carte = _lire_front("components", "dashboard", "CarteContact.js")
    verifier("14f. le badge « Membre » exige un statut `active` (liste ET carte)",
             "c.adhesion.statut === 'active'" in contacts
             and "c.adhesion.statut === 'active'" in carte)
    fiche = _lire_front("components", "dashboard", "FicheContact.js")
    verifier("14g. la fiche affiche le statut du SERVEUR, sans le recalculer",
             "c.adhesion.statut" in fiche and "date_fin" in fiche
             and "p1a_statut" not in fiche)

    # Couleurs : dans le BLOC LOT 2 de chaque ecran (et lui seul — le reste du
    # fichier est du code anterieur, deja livre), tout hexadecimal doit etre un
    # REPLI a l'interieur d'un var(), jamais une couleur imposee.
    for nom, texte, ancre, avant, apres in (
            ("ContactsManager", contacts, 'data-testid="badge-membre"', 4, 12),
            ("CarteContact", carte, "puce('Membre', true)", 4, 2),
            ("OfferWizard", wizard, 'data-testid="offer-creates-membership"', 12, 14),
            ("FicheContact", fiche, "MOTS_ADHESION = {", 2, 10)):
        bloc = _bloc_autour(texte, ancre, avant, apres)
        verifier("14h. %s : le bloc LOT 2 existe bien" % nom, bool(bloc), ancre)
        hexas = re.findall(r"#[0-9a-fA-F]{6}", bloc)
        replis = re.findall(r"var\(--[a-z-]+,\s*#[0-9a-fA-F]{6}", bloc)
        verifier("14i. %s : aucune couleur imposee dans le bloc LOT 2" % nom,
                 len(hexas) == len(replis), "%d hex / %d replis" % (len(hexas), len(replis)))


# ══════ 15-19. NON-REGRESSION : LES AUTRES LOTS IGNORENT CELUI-CI ═══════════
def _fichiers_api():
    for dossier, _, fichiers in os.walk(os.path.join(RACINE, "api")):
        for nom in fichiers:
            if nom.endswith(".py"):
                yield os.path.join(dossier, nom)


def _corps_sans_lot2(src, noms, libelle):
    """Aucune de ces fonctions ne nomme LOT 2 — mesure sur le CODE extrait."""
    coupables = []
    for nom in noms:
        texte = src.extraire(nom)
        for mot in ("lot2", "LOT2", "memberships", "creates_membership",
                    "membership_routes"):
            if mot in texte:
                coupables.append("%s:%s" % (nom, mot))
    verifier("%s : aucune fonction ne connait LOT 2" % libelle,
             not coupables, str(coupables))


def test_15_19_non_regression():
    # Le perimetre TOTAL du lot cote serveur : trois fichiers, pas un de plus.
    porteurs = sorted(os.path.relpath(c, RACINE) for c in _fichiers_api()
                      if re.search(r"lot2|LOT2|creates_membership", io.open(c, encoding="utf-8").read()))
    verifier("15-19. cote serveur, LOT 2 ne vit que dans trois fichiers",
             porteurs == ["api/routes/checkout_routes.py", "api/routes/shared.py",
                          "api/server.py"], str(porteurs))

    # 15. LOT A — l'apres-essai. Ses fonctions decident sans rien savoir du lot 2.
    _corps_sans_lot2(SHARED_SRC,
                     ("conv_presence_reelle", "conv_offres_premier_achat",
                      "conv_offre_autorisee", "conv_etat", "conv_marquer_vue"),
                     "15. LOT A (conversion apres essai)")

    # 16. Finance A/B — la trace d'encaissement. LOT 2 s'en sert ; l'inverse est faux.
    _corps_sans_lot2(SHARED_SRC,
                     ("b_normaliser_origine", "b_valider_encaissement",
                      "b_champs_automatiques", "b_champs_depuis_code"),
                     "16. Finance A/B (trace d'encaissement)")
    verifier("16a. LOT 2 REUTILISE le vocabulaire du lot B (jamais recopie)",
             "b_champs_automatiques(" in
             SHARED_SRC.extraire("lot2_creer_adhesion_apres_achat"))

    # 17. Stripe — le webhook vitrine et le module dedie.
    stripe = io.open(os.path.join(RACINE, "api", "routes", "stripe_routes.py"),
                     encoding="utf-8").read()
    verifier("17. Stripe (`stripe_routes.py`) ignore totalement LOT 2",
             not re.search(r"lot2|LOT2|memberships|creates_membership", stripe))
    _corps_sans_lot2(CAISSE_SRC, ("checkout_stripe_webhook",), "17a. webhook Stripe vitrine")

    # 18. ESSAI — le parcours gratuit et sa garde d'unicite.
    _corps_sans_lot2(SHARED_SRC,
                     ("essai2_codes_essai", "essai2_forfait_essai", "essai2_est_essai",
                      "essai2_presence_essai", "essai2_marquer_conversion",
                      "essai2_tracer_octroi"),
                     "18. ESSAI (essai gratuit et conversion)")
    _corps_sans_lot2(CAISSE_SRC,
                     ("_essai1b_prix_unitaire", "_essai1b_total_autorite",
                      "_essai1b_exiger_gratuit"),
                     "18a. ESSAI-1B (le prix qui fait autorite)")

    # 19. LOT 1 — le rattachement d'une reservation a une occurrence.
    resa = io.open(os.path.join(RACINE, "api", "routes", "reservation_routes.py"),
                   encoding="utf-8").read()
    verifier("19. LOT 1 (`reservation_routes.py`) ignore totalement LOT 2",
             not re.search(r"lot2|LOT2|memberships|creates_membership", resa))

    # P1-bis-a — le module d'adhesions n'a pas ete modifie pour ce lot : c'est
    # LOT 2 qui l'importe, jamais l'inverse.
    membres = MEMBRES_SRC.texte
    verifier("19a. le module d'adhesions n'appelle pas LOT 2 (dependance a sens unique)",
             not re.search(r"lot2|LOT2|creates_membership", membres))
    verifier("19b. LOT 2 importe la regle de propriete au lieu de la recopier",
             "from api.routes.membership_routes import" in
             SHARED_SRC.extraire("lot2_adhesion_active")
             and "P1A_SANS_PROPRIETAIRE" not in
             SHARED_SRC.extraire("lot2_adhesion_active"))

    # Le badge « membre » de `/contacts/all` est un AJOUT tolerant : il n'ecrit
    # rien et ne peut pas vider la liste.
    contacts_all = SERVEUR_SRC.extraire("get_all_contacts_unified")
    _d = contacts_all.find("LOT 2 — L'ETAT MEMBRE")
    _f = contacts_all.find('[LOT2] etat membre ignore', _d)
    bloc = contacts_all[_d:_f] if (_d >= 0 and _f > _d) else ""
    verifier("19c0. le bloc LOT 2 de `/contacts/all` est bien delimite", bool(bloc))
    if bloc:
        verifier("19c. l'enrichissement `/contacts/all` n'ecrit rien",
                 "insert_one" not in bloc and "update_one" not in bloc
                 and "update_many" not in bloc)
        verifier("19d. ... et il est tolerant a l'echec (la liste reste utilisable)",
                 "except" in bloc)
        # Les commentaires du bloc PARLENT de `find_one` pour dire qu'il n'y en
        # a pas : on mesure donc le CODE, lignes de commentaire retirees.
        code = "\n".join(l for l in bloc.splitlines()
                         if not l.strip().startswith("#"))
        verifier("19e. ... et il lit en UNE requete groupee, jamais un find_one par ligne",
                 '"$in"' in code and "find_one" not in code)


# ══════════════════════════════ execution ═══════════════════════════════════
async def principal():
    test_1_seuls_les_deux_points_dautorite()
    await test_2_6_achat_reussi()
    await test_3_rejeu()
    await test_4_5_aucune_creation()
    await test_7_le_prix_ne_decide_rien()
    await test_8_9_proprietaire()
    await test_10_anti_fuite_vendeur()
    await test_11_12_deja_membre()
    await test_13_statut_jamais_stocke()
    test_dates()
    await test_date_illisible_ne_cree_rien()
    test_prolongation_inactive()
    test_ecrit_uniquement_memberships()
    await test_ecritures_reelles_et_jamais_de_levee()
    test_14_aucune_nouvelle_page()
    test_15_19_non_regression()


def rapport():
    print("\n" + "=" * 78)
    print("LOT 2 — L'ADHESION QUI NAIT D'UN ACHAT : CE QU'ELLE FAIT, CE QU'ELLE REFUSE")
    print("=" * 78)
    ok = 0
    for nom, reussi, detail in RESULTATS:
        print(("  OK   " if reussi else "  ECHEC") + "  " + nom
              + (("  [%s]" % detail) if detail and not reussi else ""))
        ok += 1 if reussi else 0
    print("-" * 78)
    print("%d / %d verifications au vert" % (ok, len(RESULTATS)))
    return ok == len(RESULTATS)


if __name__ == "__main__":
    asyncio.run(principal())
    sys.exit(0 if rapport() else 1)
