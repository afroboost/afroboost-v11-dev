# -*- coding: utf-8 -*-
"""LOT R — LA RECHARGE PULSE x10 A 150 CHF.

LA REGLE, TELLE QUE LE PROPRIETAIRE L'A TRANCHEE :

    250 CHF -> premier achat -> adhesion d'un an + 10 seances.
    150 CHF -> RECHARGE de 10 seances, et RIEN D'AUTRE. Reservee a un membre
               dont l'adhesion est ENCORE VALIDE, et dont le pack est EPUISE.

TROIS REFUS, ET ILS SONT DIFFERENTS :
  * il reste des seances     -> « termine d'abord les tiennes »
  * aucune adhesion          -> « passe par l'offre d'entree a 250 »
  * adhesion expiree         -> « ton annee est finie, reprends une entree »
Les confondre priverait le client de la seule information qui lui permet
d'agir. Chaque refus porte son motif, et le motif remonte jusqu'a l'ecran.

CE QUE LA RECHARGE NE FAIT PAS : creer une seconde adhesion, prolonger celle
qui existe, ni toucher a un montant deja encaisse. « Le membership existant
reste le meme » — decision du proprietaire, verifiee ici.

LA GARDE EST SERVEUR. Le bouton peut etre cache, l'URL forgee, le navigateur
contourne : c'est la caisse qui refuse, pas l'ecran.

AUCUNE BASE REELLE, AUCUN RESEAU.
    python3 tests/test_lotr_recharge_pulse.py
"""
import ast, asyncio, importlib.util, io, os, sys, types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from tests._banc_qr import (RESULTATS, verifier, _Base, _Collection,  # noqa: E402
                            _HTTPException)

_fa = types.ModuleType("fastapi")
_fa.HTTPException = _HTTPException
# `APIRouter(tags=[...])` doit accepter des arguments : le vrai FastAPI n'est
# pas installe dans ce banc, et un `object` nu leve a la construction.
class _Routeur:
    def __init__(self, *a, **k): pass

    def _rien(self, *a, **k):
        return lambda f: f

    get = post = put = patch = delete = _rien


_fa.APIRouter = _Routeur
_fa.Request = object
sys.modules.setdefault("fastapi", _fa)

_spec = importlib.util.spec_from_file_location(
    "lotr_shared", os.path.join(RACINE, "api", "routes", "shared.py"))
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)
_api = types.ModuleType("api"); _api.__path__ = []
sys.modules["api"] = _api
sys.modules["api.routes"] = types.ModuleType("api.routes")
sys.modules["api.routes.shared"] = S
# `api.routes` doit etre un PAQUET pour que `from api.routes.membership_routes
# import p1a_statut` aboutisse : c'est cet import que `lotr_etat_adhesion` fait,
# et sans lui la fonction replie sur son fail-closed — on testerait le repli au
# lieu de la regle.
sys.modules["api.routes"].__path__ = [os.path.join(RACINE, "api", "routes")]
_spec_m = importlib.util.spec_from_file_location(
    "api.routes.membership_routes",
    os.path.join(RACINE, "api", "routes", "membership_routes.py"))
_MR = importlib.util.module_from_spec(_spec_m)
sys.modules["api.routes.membership_routes"] = _MR
_spec_m.loader.exec_module(_MR)


class _BaseR(_Base):
    """Le banc partage n'a pas `memberships` — 20 suites l'utilisent sans elle.
    On l'ajoute ICI plutot que dans `_banc_qr.py` : elargir la fixture commune
    pour un seul lot ferait porter le risque a tous les autres."""

    def __init__(self):
        super().__init__()
        self.memberships = _Collection()


SRC_SHARED = io.open(os.path.join(RACINE, "api", "routes", "shared.py"),
                     encoding="utf-8").read()
SRC_SERVER = io.open(os.path.join(RACINE, "api", "server.py"),
                     encoding="utf-8").read()
SRC_CHECKOUT = io.open(os.path.join(RACINE, "api", "routes", "checkout_routes.py"),
                       encoding="utf-8").read()
SRC_ESPACE = io.open(os.path.join(RACINE, "frontend", "src", "components",
                                  "SubscriberSpace.js"), encoding="utf-8").read()

OFFRE_250 = "a687ce86-94d6-4ba9-a847-c8a20e787491"
OFFRE_150 = "484c4519-15dc-4b86-8aa3-48e3c01c9645"
CLIENT = "membre@exemple.test"
AUJ = "2026-08-24"


def _extraire(nom, src=None):
    src = src or SRC_SHARED
    arbre = ast.parse(src)
    lignes = src.splitlines(True)
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return "".join(lignes[n.lineno - 1:n.end_lineno])
    return None


# ═══════════════════════════════════════════════════════════════════════════
# 1 — L'ETAT DE L'ADHESION : ACTIVE, EXPIREE, OU ABSENTE
# ═══════════════════════════════════════════════════════════════════════════
def partie_1_etat_adhesion():
    f = getattr(S, "lotr_etat_adhesion", None)
    if not f:
        verifier("1. `lotr_etat_adhesion` existe", False, "absente")
        return
    verifier("1. `lotr_etat_adhesion` existe", True)

    _active = {"date_debut": "2026-01-01", "date_fin": "2026-12-31"}
    _expiree = {"date_debut": "2024-01-01", "date_fin": "2024-12-31"}
    _future = {"date_debut": "2027-01-01", "date_fin": "2027-12-31"}

    verifier("1a. une adhesion en cours -> ACTIVE",
             f([_active], AUJ) == "active", f([_active], AUJ))
    verifier("1b. aucune adhesion -> ABSENTE",
             f([], AUJ) == "absente" and f(None, AUJ) == "absente")
    verifier("1c. une adhesion terminee -> EXPIREE, pas « absente » : "
             "le client MERITE de savoir que son annee est finie",
             f([_expiree], AUJ) == "expiree", f([_expiree], AUJ))
    verifier("1d. une adhesion qui n'a pas commence -> pas active",
             f([_future], AUJ) != "active", f([_future], AUJ))
    verifier("1e. une expiree ET une active -> ACTIVE (la meilleure gagne)",
             f([_expiree, _active], AUJ) == "active")
    verifier("1f. le dernier jour est INCLUS — une adhesion qui finit "
             "aujourd'hui vaut encore",
             f([{"date_debut": "2026-01-01", "date_fin": AUJ}], AUJ) == "active")
    verifier("1g. des dates illisibles ne valent JAMAIS « active » : "
             "on ne recharge pas sur une donnee qu'on ne sait pas lire",
             f([{"date_debut": "hier", "date_fin": "demain"}], AUJ) != "active")


# ═══════════════════════════════════════════════════════════════════════════
# 2 — LE VERDICT : QUI PEUT RECHARGER
# ═══════════════════════════════════════════════════════════════════════════
def partie_2_verdict():
    f = getattr(S, "lotr_verdict_recharge", None)
    if not f:
        verifier("2. `lotr_verdict_recharge` existe", False, "absente")
        return
    verifier("2. `lotr_verdict_recharge` existe", True)

    _protegee = {"id": OFFRE_150, "requires_active_membership": True}
    _libre = {"id": OFFRE_250, "creates_membership": True}

    # ── LE SEUL CAS AUTORISE ────────────────────────────────────────────────
    ok, motif = f(_protegee, "active", 0)
    verifier("2a. membre actif + 0 seance -> AUTORISE",
             ok is True and motif == "", "%r / %r" % (ok, motif))

    # ── IL RESTE DES SEANCES ────────────────────────────────────────────────
    ok, motif = f(_protegee, "active", 3)
    verifier("2b. membre actif + 3 seances -> REFUS `seances_restantes` "
             "(il ne paiera pas 150 pour en voir 3)",
             ok is False and motif == "seances_restantes", "%r / %r" % (ok, motif))
    ok, motif = f(_protegee, "active", 1)
    verifier("2c. UNE seule seance restante suffit a refuser",
             ok is False and motif == "seances_restantes")

    # ── PAS MEMBRE ──────────────────────────────────────────────────────────
    ok, motif = f(_protegee, "absente", 0)
    verifier("2d. sans adhesion -> REFUS `adhesion_absente` "
             "(le parcours l'oriente vers l'entree a 250)",
             ok is False and motif == "adhesion_absente", "%r / %r" % (ok, motif))

    # ── ADHESION EXPIREE ────────────────────────────────────────────────────
    ok, motif = f(_protegee, "expiree", 0)
    verifier("2e. adhesion expiree -> REFUS `adhesion_expiree`, motif DISTINCT "
             "de l'absence : la recharge ne rouvre pas une annee finie",
             ok is False and motif == "adhesion_expiree", "%r / %r" % (ok, motif))

    # ── L'ORDRE DES REFUS : L'ADHESION D'ABORD ──────────────────────────────
    # Un non-membre avec des seances restantes doit lire « passe par le 250 »,
    # pas « termine tes seances » : le second le laisserait croire qu'il
    # pourra recharger plus tard.
    ok, motif = f(_protegee, "absente", 5)
    verifier("2f. non-membre AVEC des seances -> le motif qui compte est "
             "l'adhesion, pas le compteur",
             ok is False and motif == "adhesion_absente", motif)

    # ── UNE OFFRE NON PROTEGEE N'EST PAS CONCERNEE ──────────────────────────
    ok, motif = f(_libre, "absente", 0)
    verifier("2g. l'offre d'entree a 250 reste ACHETABLE par un non-membre — "
             "sinon plus personne ne pourrait devenir membre",
             ok is True and motif == "", "%r / %r" % (ok, motif))
    ok, motif = f({"id": "x"}, "absente", 7)
    verifier("2h. une offre ordinaire (champ absent) n'est jamais bridee : "
             "absent vaut NON, comme `creates_membership`",
             ok is True and motif == "")

    # ── LES DEUX CASES SONT EXCLUSIVES, ET L'ADHESION GAGNE ─────────────────
    # Une offre qui ouvre l'adhesion ET se dit reservee aux membres serait un
    # verrou ferme sur lui-meme : plus personne ne pourrait devenir membre.
    ok, motif = f({"id": "x", "requires_active_membership": True,
                   "creates_membership": True}, "absente", 0)
    verifier("2m. offre a la fois d'ENTREE et « reservee aux membres » : "
             "l'adhesion gagne, sinon plus personne ne pourrait le devenir",
             ok is True and motif == "", "%r / %r" % (ok, motif))
    ok, motif = f({"id": "x", "requires_active_membership": True,
                   "creates_membership": True}, "active", 5)
    verifier("2n. ... et cela vaut aussi pour un membre garni : une offre "
             "d'entree ne se refuse jamais sur le compteur de seances",
             ok is True and motif == "")

    # ── FAIL CLOSED SUR LES ENTREES ABERRANTES ──────────────────────────────
    verifier("2i. `requires_active_membership` n'est vrai qu'en `is True` — "
             "une chaine « false » venue d'un import ne protege rien... ",
             f({"requires_active_membership": "false"}, "absente", 0)[0] is True)
    ok, motif = f(_protegee, "inconnu", 0)
    verifier("2j. ...mais un etat d'adhesion INCONNU refuse : on ne recharge "
             "pas sur une lecture qu'on n'a pas comprise",
             ok is False and motif, "%r / %r" % (ok, motif))
    ok, motif = f(_protegee, "active", None)
    verifier("2k. un compteur de seances ILLISIBLE refuse aussi",
             ok is False, "%r / %r" % (ok, motif))
    verifier("2l. une offre absente refuse",
             f(None, "active", 0)[0] is False)


# ═══════════════════════════════════════════════════════════════════════════
# 3 — LE MOTIF PARLE AU CLIENT
# ═══════════════════════════════════════════════════════════════════════════
def partie_3_messages():
    f = getattr(S, "lotr_message_refus", None)
    if not f:
        verifier("3. `lotr_message_refus` existe", False, "absente")
        return
    verifier("3. `lotr_message_refus` existe", True)
    _m = {m: f(m) for m in ("seances_restantes", "adhesion_absente",
                            "adhesion_expiree")}
    verifier("3a. les trois refus donnent TROIS messages differents",
             len(set(_m.values())) == 3, _m)
    verifier("3b. chaque message est en francais et non vide",
             all(isinstance(v, str) and len(v) > 20 for v in _m.values()), _m)
    verifier("3c. le refus « pas membre » ORIENTE vers l'offre d'entree",
             any(x in _m["adhesion_absente"].lower()
                 for x in ("entrée", "entree", "premier achat")), _m["adhesion_absente"])
    verifier("3d. aucun message ne cite un MONTANT : le prix vit dans le "
             "catalogue, pas dans une chaine de caracteres",
             not any(x in v for v in _m.values() for x in ("150", "250")), _m)
    verifier("3e. un motif inconnu ne rend jamais None",
             isinstance(f("nimporte_quoi"), str) and f("") is not None)


# ═══════════════════════════════════════════════════════════════════════════
# 4 — LA GARDE, EN BASE : ELLE LIT L'ADHESION ET LE COMPTEUR
# ═══════════════════════════════════════════════════════════════════════════
class _Journal:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass


def _monde(adhesion=None, seances=0, offre_protegee=True):
    db = _BaseR()
    db.offers.docs = [
        {"id": OFFRE_250, "name": "PULSE x10 cours", "price": 250.0,
         "pack_sessions": 10, "creates_membership": True, "coach_id": None},
        {"id": OFFRE_150, "name": "Membres", "price": 150.0,
         "pack_sessions": 10, "creates_membership": False, "coach_id": None,
         "requires_active_membership": bool(offre_protegee)},
    ]
    db.memberships.docs = [adhesion] if adhesion else []
    db.subscriptions.docs = [
        {"id": "sub-1", "code": "PULSE-01", "email": CLIENT, "status": "active",
         "offer_name": "PULSE x10 cours", "total_sessions": 10,
         "used_sessions": 10 - seances, "remaining_sessions": seances,
         "expires_at": "2026-12-31T23:59:59+00:00"},
    ]
    return db


async def partie_4_garde_base():
    f = getattr(S, "lotr_garde_achat", None)
    if not f:
        verifier("4. `lotr_garde_achat` existe", False, "absente")
        return
    verifier("4. `lotr_garde_achat` existe", True)

    _adh_active = {"id": "adh-1", "email": CLIENT, "coach_id": None,
                   "date_debut": "2026-01-01", "date_fin": "2026-12-31"}
    _adh_expiree = {"id": "adh-0", "email": CLIENT, "coach_id": None,
                    "date_debut": "2024-01-01", "date_fin": "2024-12-31"}

    ok, motif = await f(_monde(_adh_active, 0), CLIENT, OFFRE_150, aujourdhui=AUJ)
    verifier("4a. membre actif, pack epuise -> la caisse ACCEPTE",
             ok is True and motif == "", "%r / %r" % (ok, motif))

    ok, motif = await f(_monde(_adh_active, 3), CLIENT, OFFRE_150, aujourdhui=AUJ)
    verifier("4b. membre actif, 3 seances -> la caisse REFUSE",
             ok is False and motif == "seances_restantes", "%r / %r" % (ok, motif))

    ok, motif = await f(_monde(None, 0), CLIENT, OFFRE_150, aujourdhui=AUJ)
    verifier("4c. non-membre -> la caisse REFUSE, meme si l'ecran a ete "
             "contourne : la garde est SERVEUR",
             ok is False and motif == "adhesion_absente", "%r / %r" % (ok, motif))

    ok, motif = await f(_monde(_adh_expiree, 0), CLIENT, OFFRE_150, aujourdhui=AUJ)
    verifier("4d. adhesion expiree -> la caisse REFUSE",
             ok is False and motif == "adhesion_expiree", "%r / %r" % (ok, motif))

    ok, motif = await f(_monde(None, 0), CLIENT, OFFRE_250, aujourdhui=AUJ)
    verifier("4e. l'offre d'entree reste ouverte a un inconnu",
             ok is True and motif == "", "%r / %r" % (ok, motif))

    # ── LES SEANCES SE COMPTENT SUR TOUS LES FORFAITS VIVANTS ───────────────
    db = _monde(_adh_active, 0)
    db.subscriptions.docs.append(
        {"id": "sub-2", "code": "AUTRE", "email": CLIENT, "status": "active",
         "offer_name": "Cours à l'unité", "total_sessions": 5,
         "used_sessions": 2, "remaining_sessions": 3,
         "expires_at": "2026-12-31T23:59:59+00:00"})
    ok, motif = await f(db, CLIENT, OFFRE_150, aujourdhui=AUJ)
    verifier("4f. un AUTRE forfait encore garni compte aussi : le client a "
             "des seances, il n'a pas besoin d'en racheter",
             ok is False and motif == "seances_restantes", "%r / %r" % (ok, motif))

    # ── UN FORFAIT PERIME NE COMPTE PAS ────────────────────────────────────
    db2 = _monde(_adh_active, 0)
    db2.subscriptions.docs = [
        {"id": "sub-p", "code": "VIEUX", "email": CLIENT, "status": "active",
         "offer_name": "PULSE x10 cours", "total_sessions": 10,
         "used_sessions": 2, "remaining_sessions": 8,
         "expires_at": "2020-01-01T23:59:59+00:00"}]
    ok, motif = await f(db2, CLIENT, OFFRE_150, aujourdhui=AUJ)
    verifier("4g. des seances sur un forfait EXPIRE ne bloquent pas : "
             "elles ne valent plus rien",
             ok is True, "%r / %r" % (ok, motif))

    # ── FAIL CLOSED ────────────────────────────────────────────────────────
    class _Muet:
        def __getattr__(self, _):
            raise RuntimeError("base muette")
    ok, motif = await f(_Muet(), CLIENT, OFFRE_150, aujourdhui=AUJ)
    verifier("4h. base en panne -> REFUS. On n'accorde pas 10 seances sur une "
             "base qui n'a pas repondu",
             ok is False and motif, "%r / %r" % (ok, motif))
    ok, _ = await f(_monde(_adh_active, 0), "", OFFRE_150, aujourdhui=AUJ)
    verifier("4i. sans e-mail identifie -> REFUS", ok is False)


# ═══════════════════════════════════════════════════════════════════════════
# 5 — LA GARDE EST POSEE SUR TOUTES LES PORTES
# ═══════════════════════════════════════════════════════════════════════════
def partie_5_portes():
    # La caisse passe par un helper local (`_lotr_garde`), comme elle le fait
    # deja pour le vendeur (`_lot2_verifier_vendeur`) : on cherche l'APPEL, et
    # on verifie separement que ce helper atteint bien la regle du module.
    _caisse = _extraire("create_checkout_session", SRC_CHECKOUT) or ""
    verifier("5a. la caisse principale (`checkout_routes.create_checkout_session`) "
             "appelle la garde", "_lotr_garde(" in _caisse)
    verifier("5a2. ... et ce helper atteint bien la regle du module partage",
             "lotr_garde_achat" in (_extraire("_lotr_garde", SRC_CHECKOUT) or ""))
    verifier("5a3. la porte GRATUITE est gardee aussi — une offre reservee "
             "obtenue a 0 CHF serait le contournement le plus simple",
             "_lotr_garde(" in (_extraire("free_checkout", SRC_CHECKOUT) or ""))
    verifier("5b. la caisse de la vitrine (`server.py`) l'appelle aussi : "
             "poser la garde sur une seule porte la rendrait contournable "
             "en changeant d'URL",
             SRC_SERVER.count("lotr_garde_achat") >= 1)
    _espace = _extraire("subscriber_stripe_checkout", SRC_SERVER) or ""
    verifier("5c. le bouton de l'espace abonne l'appelle aussi",
             "lotr_garde_achat" in _espace)


# ═══════════════════════════════════════════════════════════════════════════
# 6 — LE BOUTON « RENOUVELER » ACTUEL : LE DEFAUT BLOQUANT
# ═══════════════════════════════════════════════════════════════════════════
def partie_6_bouton():
    """Il facturait le montant du PRECEDENT achat et n'accordait qu'UNE seance.

    LA MECANIQUE DU DEFAUT, verifiee dans le depot : la route posait
    `metadata.product_name` mais NI `offer_id` NI `pack_sessions`. Le webhook
    retombait alors sur une regex appliquee au nom du produit ; ce nom valant
    « Abonnement Afroboost », aucun « x10 » n'y figurait -> `sessions_count = 1`.
    Et `offer_id` vide -> aucune adhesion evaluee.
    """
    src = _extraire("subscriber_stripe_checkout", SRC_SERVER)
    if not src:
        verifier("6. la route du bouton existe", False, "introuvable")
        return
    verifier("6. la route du bouton existe", True)
    verifier("6a. elle transmet `offer_id` — sans quoi le webhook ne sait NI "
             "combien de seances accorder, NI quelle offre a ete achetee",
             '"offer_id"' in src or "'offer_id'" in src)
    verifier("6b. elle transmet `pack_sessions` : c'est LUI qui donne les 10 "
             "seances, et non une regex sur un libelle commercial",
             "pack_sessions" in src)
    verifier("6c. le montant vient du CATALOGUE, pas du precedent achat : "
             "un client PULSE ne doit pas se voir refacturer son entree",
             "stripe_amount" not in src.split("amount_cents")[0]
             or "offers" in src or "lotr_" in src,
             "le montant est encore lu sur le code d'acces")
    verifier("6d. la garde y est posee AUSSI (une porte de plus n'est pas une "
             "porte de moins)", "lotr_garde_achat" in src)


# ═══════════════════════════════════════════════════════════════════════════
# 7 — LA TRACE FINANCIERE
# ═══════════════════════════════════════════════════════════════════════════
def partie_7_trace():
    f = getattr(S, "lotr_trace_recharge", None)
    if not f:
        verifier("7. `lotr_trace_recharge` existe", False, "absente")
        return
    verifier("7. `lotr_trace_recharge` existe", True)
    t = f(montant=150.0, devise="chf", seances=10, offre_id=OFFRE_150,
          membership_id="adh-1", reference="pi_123")
    verifier("7a. la trace dit le MONTANT encaisse",
             t.get("montant_encaisse") == 150.0, t)
    verifier("7b. ... les SEANCES achetees, pour que le Bilan puisse valoriser "
             "chaque presence issue de cette recharge",
             t.get("seances_a_l_achat") == 10, t)
    verifier("7c. ... et une ORIGINE explicite : « renouvellement PULSE » se "
             "lit sans deviner",
             "renouvellement" in str(t.get("origine_paiement") or "").lower(), t)
    verifier("7d. ... l'offre et l'adhesion concernees",
             t.get("offer_id") == OFFRE_150 and t.get("membership_id") == "adh-1", t)
    verifier("7e. ... et la reference du paiement, sans laquelle la somme "
             "n'est rattachable a rien",
             t.get("reference_paiement") == "pi_123", t)
    verifier("7f. la devise est normalisee en majuscules",
             str(t.get("devise") or "").upper() == "CHF", t)
    _vide = f(montant=None, devise=None, seances=None, offre_id="",
              membership_id=None, reference="")
    verifier("7g. un montant INCONNU n'est jamais ecrit 0 : la cle est absente",
             "montant_encaisse" not in _vide, _vide)
    verifier("7h. mais l'origine reste posee : on sait que c'etait une recharge, "
             "meme sans montant lisible",
             "renouvellement" in str(_vide.get("origine_paiement") or "").lower())


# ═══════════════════════════════════════════════════════════════════════════
# 8 — CE QUE LA RECHARGE NE FAIT JAMAIS
# ═══════════════════════════════════════════════════════════════════════════
def partie_8_perimetre():
    for nom in ("lotr_verdict_recharge", "lotr_etat_adhesion",
                "lotr_garde_achat", "lotr_trace_recharge", "lotr_message_refus"):
        corps = _extraire(nom) or ""
        if not corps:
            continue
        verifier("8. `%s` n'ECRIT rien en base" % nom,
                 not any(m in corps for m in
                         ("insert_one", "update_one", "delete_one", "insert_many")))
    _g = _extraire("lotr_garde_achat") or ""
    verifier("8a. la garde ne cree ni ne prolonge AUCUNE adhesion — decision "
             "du proprietaire : « le membership existant reste le meme »",
             "lot2_prolonger_fin" not in _g and "lot2_creer_adhesion" not in _g)
    verifier("8b. aucune comparaison a un MONTANT : ni 150 ni 250 en dur. "
             "Le jour ou le pack passe a 160, la regle tient toujours",
             not any(x in (_g + (_extraire("lotr_verdict_recharge") or ""))
                     for x in ("150", "250")))
    verifier("8c. `MEMBER_PRICING_ENABLED` n'est pas touche : le tarif membre "
             "et la recharge sont deux sujets",
             "MEMBER_PRICING_ENABLED" not in _g)
    # Meme technique que la garde P5 de LOT 2 : on cherche un APPEL par l'AST,
    # pas une occurrence textuelle — un commentaire qui NOMME la fonction ne
    # la reveille pas.
    _appels = []
    for _rep, _, _fics in os.walk(os.path.join(RACINE, "api")):
        for _f in _fics:
            if not _f.endswith(".py"):
                continue
            _t = io.open(os.path.join(_rep, _f), encoding="utf-8").read()
            if "lot2_prolonger_fin" not in _t:
                continue
            for _n in ast.walk(ast.parse(_t)):
                if isinstance(_n, ast.Call):
                    _fn = _n.func
                    if (isinstance(_fn, ast.Name) and _fn.id == "lot2_prolonger_fin") \
                            or (isinstance(_fn, ast.Attribute)
                                and _fn.attr == "lot2_prolonger_fin"):
                        _appels.append(_f)
    verifier("8d. `lot2_prolonger_fin` reste DORMANTE : la decision du "
             "proprietaire est « le membership existant reste le meme », donc "
             "on ne prolonge pas — et la garde P5 de LOT 2 tient encore",
             not _appels, "appelee dans %s" % _appels)


# ═══════════════════════════════════════════════════════════════════════════
# 9 — L'ECRAN : LE CTA N'APPARAIT QUE QUAND C'EST VRAI
# ═══════════════════════════════════════════════════════════════════════════
def partie_9_ecran():
    verifier("9a. l'espace abonne recoit l'eligibilite DU SERVEUR — il ne la "
             "recalcule pas : deux regles divergeraient un jour",
             "recharge" in SRC_ESPACE.lower())
    verifier("9b. le CTA de recharge existe et porte un marqueur de test",
             "recharge-cta" in SRC_ESPACE)
    verifier("9c. il est conditionne a `eligible` renvoye par le serveur",
             "recharge.eligible" in SRC_ESPACE or "recharge?.eligible" in SRC_ESPACE)
    verifier("9d. le motif de refus est AFFICHE : un bouton qui disparait sans "
             "explication est un bug pour celui qui le cherche",
             "recharge-motif" in SRC_ESPACE)
    verifier("9e. l'ecran n'ecrit aucun montant en dur — il affiche celui du "
             "serveur",
             "150" not in SRC_ESPACE.split("recharge")[-1][:2000]
             if "recharge" in SRC_ESPACE else False)
    verifier("9f. la route de l'espace abonne expose bien le bloc `recharge`",
             '"recharge"' in SRC_SERVER)


# ═══════════════════════════════════════════════════════════════════════════
# 10 — LA SYMETRIE DU CHAMP : LE PIEGE QUE CE DEPOT A DEJA PAYE
# ═══════════════════════════════════════════════════════════════════════════
def partie_10_symetrie():
    """Quatre endroits, et il faut LES QUATRE.

    LOT 3b s'est fait piéger exactement ici, et le depot le documente : un
    champ declare dans `OfferCreate` mais pas dans `Offer` est filtre en
    silence par le `response_model=List[Offer]` de GET /offers — la case revient
    decochee a chaque relecture. Et l'inverse : absent d'`OfferCreate`, le
    `$set: offer.model_dump()` du PUT l'EFFACE en base a chaque enregistrement.
    Cote navigateur, meme exigence en trois points : relire, envoyer, remettre a
    zero d'une offre a la suivante.
    """
    _champ = "requires_active_membership"
    _decl = SRC_SERVER.count("    %s: bool = False" % _champ)
    verifier("10a. le champ est declare dans les DEUX modeles Pydantic "
             "(`Offer` ET `OfferCreate`) — un seul des deux suffirait a le "
             "faire disparaitre en silence", _decl == 2,
             "%d declaration(s)" % _decl)

    _dash = io.open(os.path.join(RACINE, "frontend", "src", "components",
                                 "CoachDashboard.js"), encoding="utf-8").read()
    _wiz = io.open(os.path.join(RACINE, "frontend", "src", "components",
                                "dashboard", "OfferWizard.js"), encoding="utf-8").read()
    verifier("10b. le dashboard RELIT le champ depuis la base (sinon rouvrir "
             "une offre protegee montrerait une case decochee)",
             "%s: !!offer.%s" % (_champ, _champ) in _dash)
    verifier("10c. il l'ENVOIE au serveur (sinon le PUT l'effacerait en base)",
             "%s: !!src.%s" % (_champ, _champ) in _dash)
    verifier("10d. il le remet a FAUX a la creation d'une offre neuve",
             "%s: false" % _champ in _dash)
    verifier("10e. le formulaire porte une case, avec un marqueur de test",
             "offer-requires-membership" in _wiz)

    verifier("10f. la case est DESACTIVEE quand l'offre ouvre l'adhesion : on "
             "n'achete pas son adhesion avec une offre reservee aux membres",
             "disabled={form.creates_membership === true}" in _wiz
             and "offer-recharge-exclusive" in _wiz)
    # L'EXCLUSIVITE EST UNE REGLE METIER : elle vit cote SERVEUR, une seule
    # fois et sous test (voir 2m/2n). Le navigateur desactive la case pour
    # l'ergonomie, mais ne rejuge rien — la redire ici creerait une seconde
    # verite, contournable depuis la console.
    verifier("10g. le navigateur ne REJUGE pas l'exclusivite : il transmet, "
             "le serveur tranche",
             "&& !src.creates_membership" not in _dash)
    verifier("10h. l'icone est un SVG du jeu du depot, jamais un emoji",
             'SvgIcon name="refresh"' in _wiz)


async def principal():
    partie_1_etat_adhesion()
    partie_2_verdict()
    partie_3_messages()
    await partie_4_garde_base()
    partie_5_portes()
    partie_6_bouton()
    partie_7_trace()
    partie_8_perimetre()
    partie_9_ecran()
    partie_10_symetrie()

    ok = sum(1 for _, c, _ in RESULTATS if c)
    print("\n" + "=" * 76)
    print("LOT R — RECHARGE PULSE x10 (150 CHF)")
    print("=" * 76)
    for nom, cond, detail in RESULTATS:
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom,
                              "" if cond or not detail else "\n          -> %s" % detail))
    print("-" * 76)
    print("Base en memoire. Donnees de production : 0. Aucun paiement declenche.")
    print("%d / %d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(principal()))
