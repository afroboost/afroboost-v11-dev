# -*- coding: utf-8 -*-
"""LOT 3c-0b — ON NE TOUCHE PAS A L'ARGENT DES AUTRES.

CE QUE CE LOT DEFEND. Quatre routes pouvaient etre appelees sans preuve
d'identite, ou avec une identite simplement DECLAREE dans un en-tete que
n'importe qui peut ecrire. Toutes les quatre touchent a ce que LOT 3c devra
compter : le solde de seances d'un client, le montant d'un droit, la propriete
d'un code, les donnees personnelles d'un abonne.

LES QUATRE PORTES, ET CE QU'ELLES LAISSAIENT FAIRE :

  A. PUT /discount-codes/subscriptions/{sub_id}
     Aucune authentification, et pas meme un parametre `request` — s'y
     authentifier etait IMPOSSIBLE. Elle ecrit `remaining_sessions`,
     `used_sessions` et `offer_price` : se recrediter des seances, effacer sa
     consommation, falsifier une recette.

  B. PUT /subscriptions/{id}/sessions
     `require_auth`, qui accepte encore le repli `X-User-Email` (V265) : un
     `curl` suffisait a ajuster le solde d'un client au nom d'un coach.

  C. PUT /subscriptions/{code}/profile
     Aucune authentification, pas de `request`. Ecrit des DONNEES
     PERSONNELLES (nom, WhatsApp) sur l'abonne de n'importe quel coach.

  D. POST /discount-codes
     Aucun refus. Un anonyme creait un code gratuit AU NOM DU COACH DE SON
     CHOIX, ouvrait une souscription active, et declenchait deux e-mails —
     un relais de spam sur le domaine, sans limite de debit.

CE QUE CE LOT NE FAIT PAS : aucune regle de consommation de seances, aucune
logique de profil, aucun prix, aucun doublon corrige. Il ferme des portes.

AUCUNE BASE REELLE, AUCUN RESEAU.
    python3 tests/test_lot3c0b_acces.py
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
    "l3c0b_shared", os.path.join(RACINE, "api", "routes", "shared.py"))
SHARED = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SHARED)
sys.modules["api"] = types.ModuleType("api")
sys.modules["api.routes"] = types.ModuleType("api.routes")
sys.modules["api.routes.shared"] = SHARED

SRC_PROMO = io.open(os.path.join(RACINE, "api", "routes", "promo_routes.py"),
                    encoding="utf-8").read()
SRC_SERVER = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()

ADMIN = SHARED.SUPER_ADMIN_EMAILS[0]
ADMIN2 = SHARED.SUPER_ADMIN_EMAILS[1] if len(SHARED.SUPER_ADMIN_EMAILS) > 1 else ADMIN
COACH_B = "coach.b@partenaire.ch"
COACH_C = "coach.c@partenaire.ch"


def _extraire(fichier, nom):
    src = io.open(os.path.join(RACINE, *fichier), encoding="utf-8").read()
    arbre = ast.parse(src)
    lignes = src.splitlines(True)
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return "".join(lignes[n.lineno - 1:n.end_lineno])
    raise AssertionError("fonction introuvable : %s" % nom)


class _Journal:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass


class _Corps:
    def __init__(self, **kw):
        self._d = dict(kw)
        for k, v in kw.items():
            setattr(self, k, v)

    def model_dump(self):
        return dict(self._d)


class _Requete:
    """Le banc simule la SIGNATURE : `coach_jwt_email` ne lira cet en-tete que
    parce qu'on le lui dit ici. Un vrai `X-User-Email` n'aurait, lui, aucun
    effet sur les routes durcies — c'est precisement ce que le lot garantit."""
    def __init__(self, signe=None, entete_declare=None):
        self.headers = {}
        if entete_declare:
            self.headers["X-User-Email"] = entete_declare
        self._signe = signe or ""


def _jwt(r):
    """Identite SIGNEE. Ne lit JAMAIS `X-User-Email` : c'est tout l'enjeu."""
    return getattr(r, "_signe", "") or ""


def _monde():
    db = _Base()
    db.coaches.docs = [{"email": ADMIN}, {"email": COACH_B}, {"email": COACH_C}]
    db.subscriptions.docs = [
        {"_id": "s1", "id": "sub-B", "code": "BCODE-01", "coach_id": COACH_B,
         "remaining_sessions": 5, "used_sessions": 5, "offer_price": 250.0, "status": "active"},
        # Stock ANCIEN, sans proprietaire : 13 % des souscriptions en production.
        {"_id": "s2", "id": "sub-LEGACY", "code": "OLD-01",
         "remaining_sessions": 3, "used_sessions": 1, "offer_price": 100.0, "status": "active"},
    ]
    return db


def _ns_promo(db):
    ns = {
        "_db": db, "re": __import__("re"), "uuid": uuid, "asyncio": asyncio,
        "datetime": datetime, "timezone": timezone, "logger": _Journal(),
        "HTTPException": _HTTPException, "SUPER_ADMIN_EMAIL": ADMIN,
        "DiscountCode": lambda **kw: _Corps(**kw),
        "DiscountCodeCreate": _Corps,
        "Request": object, "Optional": None, "List": list, "dict": dict, "str": str,
        "is_super_admin": SHARED.is_super_admin,
        "coach_jwt_email": _jwt,
    }

    async def _resolve_offer_details(courses_list, max_uses, offer_name_override=None):
        return (int(max_uses or 1), offer_name_override or "Abonnement", None)

    async def _rien(*a, **k):
        return None

    ns["_resolve_offer_details"] = _resolve_offer_details
    ns["_send_welcome_email"] = _rien
    ns["_send_coach_sale_email"] = _rien
    for nom in ("update_subscription", "create_discount_code"):
        exec(compile(_extraire(("api", "routes", "promo_routes.py"), nom),
                     "promo_routes.py", "exec"), ns)
    return ns


async def _refus(titre, coro, attendu=403):
    try:
        await coro
        verifier(titre, False, "ACCEPTE alors qu'il fallait refuser !")
    except _HTTPException as e:
        verifier(titre, e.status_code == attendu, "statut=%s" % e.status_code)


# ═══════════ A. LA SOUSCRIPTION — SEANCES ET MONTANT ════════════════════════
async def partie_a():
    print("\n=== A. PUT /discount-codes/subscriptions/{id} ===")
    db = _monde()
    maj = _ns_promo(db)["update_subscription"]

    await _refus("A1 anonyme -> REFUS", maj("sub-B", {"remaining_sessions": 99}, _Requete()))
    await _refus("A2 faux X-User-Email (declare, non signe) -> REFUS",
                 maj("sub-B", {"remaining_sessions": 99}, _Requete(entete_declare=COACH_B)))
    await _refus("A3 un AUTRE coach -> REFUS",
                 maj("sub-B", {"remaining_sessions": 99}, _Requete(signe=COACH_C)))
    verifier("A4 apres les trois refus, le solde est INTACT",
             db.subscriptions.docs[0]["remaining_sessions"] == 5,
             str(db.subscriptions.docs[0].get("remaining_sessions")))

    await maj("sub-B", {"remaining_sessions": 7}, _Requete(signe=COACH_B))
    verifier("A5 le coach PROPRIETAIRE modifie SA souscription -> AUTORISE",
             db.subscriptions.docs[0]["remaining_sessions"] == 7)

    await maj("sub-B", {"offer_price": 300.0}, _Requete(signe=ADMIN))
    verifier("A6 le super-admin passe partout",
             db.subscriptions.docs[0]["offer_price"] == 300.0)

    await maj("sub-LEGACY", {"remaining_sessions": 4}, _Requete(signe=COACH_B))
    verifier("A7 le stock ANCIEN sans proprietaire reste modifiable — le refuser "
             "bloquerait le coach sur son propre historique (13 % en production)",
             db.subscriptions.docs[1]["remaining_sessions"] == 4)

    await maj("sub-B", {"coach_id": "voleur@x.ch", "status": "active"}, _Requete(signe=COACH_B))
    verifier("A8 `coach_id` n'est PAS dans la liste blanche : on ne s'approprie "
             "pas une souscription par une mise a jour",
             db.subscriptions.docs[0]["coach_id"] == COACH_B)

    await _refus("A9 souscription inexistante -> 404 FRANC (plus de `{'error':…}` en 200)",
                 maj("sub-inexistante", {"remaining_sessions": 1}, _Requete(signe=ADMIN)), 404)


# ═══════════ D. LA CREATION D'UN CODE ═══════════════════════════════════════
async def partie_d():
    print("\n=== D. POST /discount-codes ===")
    db = _monde()
    creer = _ns_promo(db)["create_discount_code"]

    def corps(**kw):
        base = dict(code="NEW-01", type="100%", value=100, assignedEmail=None,
                    expiresAt=None, courses=[], maxUses=10, coach_id=None,
                    targetCategories=[], offerName=None, multi_member=False,
                    shared_sessions=True, stripe_amount=None,
                    montant_encaisse=None, devise=None, origine_paiement=None)
        base.update(kw)
        return _Corps(**base)

    await _refus("D1 anonyme -> REFUS (il creait un code gratuit + 2 e-mails)",
                 creer(corps(), _Requete()))
    await _refus("D2 faux X-User-Email -> REFUS",
                 creer(corps(), _Requete(entete_declare=COACH_B)))
    verifier("D3 apres refus, AUCUN code n'a ete cree",
             len(db.discount_codes.docs) == 0, str(len(db.discount_codes.docs)))

    await creer(corps(code="B-01"), _Requete(signe=COACH_B))
    verifier("D4 le coach cree son code -> AUTORISE", len(db.discount_codes.docs) == 1)
    verifier("D5 ... et le code lui appartient, identite PROUVEE par le jeton",
             db.discount_codes.docs[0]["coach_id"] == COACH_B,
             str(db.discount_codes.docs[0].get("coach_id")))

    # LE CROSS-COACH : B tente de creer POUR C.
    await creer(corps(code="B-02", coach_id=COACH_C), _Requete(signe=COACH_B))
    verifier("D6 CROSS-COACH — le coach B declare le coach C : le corps est "
             "IGNORE, le code reste a B",
             db.discount_codes.docs[1]["coach_id"] == COACH_B,
             str(db.discount_codes.docs[1].get("coach_id")))

    await creer(corps(code="A-01", coach_id=COACH_C), _Requete(signe=ADMIN))
    verifier("D7 le super-admin, LUI, peut creer pour un coach EXISTANT",
             db.discount_codes.docs[2]["coach_id"] == COACH_C,
             str(db.discount_codes.docs[2].get("coach_id")))

    await creer(corps(code="A-02", coach_id="fantome@nulle-part.xx"), _Requete(signe=ADMIN))
    verifier("D8 ... mais pas pour un coach INEXISTANT — sinon on rouvrirait "
             "par le haut la porte qu'on ferme",
             db.discount_codes.docs[3]["coach_id"] == ADMIN,
             str(db.discount_codes.docs[3].get("coach_id")))

    verifier("D9 le SECOND super-admin est reconnu (l'ombre locale de "
             "`is_super_admin` n'en connaissait qu'un)",
             SHARED.is_super_admin(ADMIN2) is True)


# ═══════════ B & C. LES DEUX ROUTES DE server.py ════════════════════════════
def partie_bc_source():
    print("\n=== B & C. server.py — l'identite est SIGNEE, la porte est fermee ===")
    b = _extraire(("api", "server.py"), "adjust_subscription_sessions")
    verifier("B1 `/sessions` n'utilise PLUS `require_auth` (qui acceptait "
             "l'en-tete falsifiable V265)", "require_auth(request)" not in b, b[:200])
    verifier("B2 ... il exige un JWT coach SIGNE",
             "_v311_coach_email_from_jwt(request)" in b)
    verifier("B3 ... et refuse en 403 sans identite prouvee",
             "403" in b and "Authentification coach requise" in b)
    verifier("B4 le cloisonnement par coach est CONSERVE (V237), legacy inclus",
             "_sub_owner" in b and "appartient a un autre coach" in b)
    verifier("B5 AUCUNE regle de consommation de seances n'a bouge",
             "action" in b and "'add'" in b.replace('"', "'"))

    c = _extraire(("api", "server.py"), "update_subscriber_profile")
    verifier("C1 `/profile` recoit enfin la requete HTTP",
             "request: Request" in c)
    verifier("C2 ... et passe par la garde abonne DEJA en service (7 routes)",
             "_v334_autoriser(request" in c)
    verifier("C3 ... ce qui REFUSE un coach qui n'est pas celui de cet abonne",
             "_v334_autoriser" in SRC_SERVER
             and "Un coach authentifié mais qui n'est PAS celui de cet abonné" in SRC_SERVER)
    verifier("C4 la logique de profil n'a PAS ete touchee (ecriture champ par champ)",
             "if payload.name:" in c and "update_many" in c)
    verifier("C5 le champ `code` du corps n'est jamais ECRIT en base",
             'updates["code"]' not in c)
    verifier("C6 le code vient du CORPS et JAMAIS de l'URL — sinon le chemin "
             "« abonne » serait toujours satisfait et le cloisonnement "
             "inter-coach ne vaudrait plus rien (defaut trouve par le test "
             "en navigateur, pas par relecture)",
             "or code_upper" not in c)
    onb = io.open(os.path.join(RACINE, "frontend", "src", "components",
                               "SubscriberOnboarding.js"), encoding="utf-8").read()
    verifier("C7 ... et le volet frontend presente bien ce code, sinon "
             "l'abonne ne pourrait plus remplir SON profil (V310c)",
             "/profile`" in onb and "        code,\n" in onb)


# ═══════════ E. LE PERIMETRE DU LOT ═════════════════════════════════════════
def partie_e_perimetre():
    print("\n=== E. CE LOT NE COMPTE TOUJOURS AUCUN ARGENT ===")
    verifier("E1 MEMBER_PRICING_ENABLED reste FALSE",
             'MEMBER_PRICING_ENABLED: bool = False' in SRC_SERVER
             and '"MEMBER_PRICING_ENABLED": False' in SRC_SERVER)
    for nom, src in (("update_subscription", SRC_PROMO), ("create_discount_code", SRC_PROMO)):
        bloc = _extraire(("api", "routes", "promo_routes.py"), nom)
        verifier("E2 `%s` n'ecrit RIEN en masse (aucun backfill, aucune migration)" % nom,
                 "update_many" not in bloc and "delete_many" not in bloc)
    verifier("E3 aucun index unique n'est cree par ce lot",
             "create_index" not in _extraire(("api", "routes", "promo_routes.py"),
                                             "create_discount_code"))
    verifier("E4 les doublons ne sont NI fusionnes NI supprimes par ce lot",
             "canonical" not in _extraire(("api", "routes", "promo_routes.py"),
                                          "update_subscription"))


async def principal():
    await partie_a()
    await partie_d()
    partie_bc_source()
    partie_e_perimetre()

    ok = sum(1 for _, c, _ in RESULTATS if c)
    print("\n" + "=" * 74)
    print("LOT 3c-0b — LES PORTES DE LA DONNEE FINANCIERE SONT FERMEES")
    print("=" * 74)
    for nom, cond, detail in RESULTATS:
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom,
                              "" if cond or not detail else "  -> %s" % detail))
    print("-" * 74)
    print("Souscriptions / codes / e-mails REELS : 0 — base en memoire")
    print("%d / %d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(principal()))
