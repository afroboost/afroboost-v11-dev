# -*- coding: utf-8 -*-
"""LOT 3c-0c — UNE SEULE REGLE POUR CHOISIR LE DOCUMENT A DEBITER.

LE PROBLEME, EN UNE PHRASE. Le TYPE de droit utilise (PULSE, cours a l'unite,
essai, event) est deja correctement determine : c'est le CODE que le client
presente. Ce qui manque, c'est le departage quand PLUSIEURS documents portent
CE MEME code — et la, cinq chemins repondaient de trois facons.

CE QUE CE LOT NE FAIT PAS. Il n'utilise JAMAIS `choisir_abonnement` pour
trancher entre deux OFFRES differentes : l'offre reste designee par le contexte
reel de la reservation (le code presente, ou le `subscriptionId` transmis).
`choisir_abonnement` ne sert qu'au NIVEAU 2 — plusieurs souscriptions de la
MEME offre.

LES SEPT SCENARIOS, tels que le proprietaire les a poses :
  A. PULSE seul                  -> le bon PULSE debite
  B. PULSE + cours a l'unite     -> la reservation unitaire ne touche pas PULSE
  C. PULSE + essai               -> l'essai est consomme, PULSE ne bouge pas
  D. PULSE + event achete        -> PULSE ne bouge pas
  E. deux PULSE actifs           -> affichage, debit et Finance = MEME document
  F. Stripe                      -> un achat reel apparait UNE fois
  G. aucune transaction legitime ne disparait

AUCUNE BASE REELLE, AUCUN RESEAU.
    python3 tests/test_lot3c0c_multi_offres.py
"""
import ast, asyncio, importlib.util, io, os, sys, types, uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from tests._banc_qr import (RESULTATS, verifier, _Base, _HTTPException,  # noqa: E402
                            _Collection)


def _base_avec_paiements():
    """Le banc partage ne porte pas `payment_transactions` — aucune suite ne la
    lisait jusqu'ici. On l'ajoute LOCALEMENT plutot que d'elargir `_banc_qr`,
    qui est partage par huit suites : un ajout la-bas les ferait toutes bouger
    pour le confort d'une seule."""
    db = _Base()
    db.payment_transactions = _Collection()
    return db

_fa = types.ModuleType("fastapi")
_fa.HTTPException = _HTTPException
_fa.APIRouter = object
_fa.Request = object
sys.modules.setdefault("fastapi", _fa)

_spec = importlib.util.spec_from_file_location(
    "l3c0c_shared", os.path.join(RACINE, "api", "routes", "shared.py"))
SHARED = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SHARED)
sys.modules["api"] = types.ModuleType("api")
sys.modules["api.routes"] = types.ModuleType("api.routes")
sys.modules["api.routes.shared"] = SHARED

SRC_SERVER = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
SRC_RESA = io.open(os.path.join(RACINE, "api", "routes", "reservation_routes.py"),
                   encoding="utf-8").read()

ADMIN = SHARED.SUPER_ADMIN_EMAILS[0]
COACH = "coach.b@partenaire.ch"


def _extraire(src, nom):
    arbre = ast.parse(src)
    lignes = src.splitlines(True)
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return "".join(lignes[n.lineno - 1:n.end_lineno])
    raise AssertionError("fonction introuvable : %s" % nom)


def _code_nu(src, nom):
    """Le CODE d'une fonction, sans commentaires ni docstring.

    Un commentaire qui EXPLIQUE pourquoi on n'appelle pas `setdefault` contient
    le mot `setdefault`. On veut savoir ce que la fonction FAIT.
    """
    arbre = ast.parse(_extraire(src, nom))
    f = arbre.body[0]
    corps = list(f.body)
    if corps and isinstance(corps[0], ast.Expr) and isinstance(corps[0].value, ast.Constant) \
            and isinstance(corps[0].value.value, str):
        corps = corps[1:]
    f.body = corps or [ast.Pass()]
    return ast.unparse(arbre)


class _Journal:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass


def _iso(j):
    return (datetime.now(timezone.utc) + timedelta(days=j)).isoformat()


# ═══════════════════════════════════════════════════════════════════════════
# E — LE DEPARTAGE : Finance doit designer le MEME document que le debit
# ═══════════════════════════════════════════════════════════════════════════
def _deux_pulse():
    """Le cas CHRISTOUX10, reproduit : deux documents, MEME code, MEME offre."""
    return [
        {"id": "pulse-vieux", "code": "DUO-01", "email": "m@ex.test",
         "coach_id": COACH, "status": "active", "offer_name": "PULSE x10 cours",
         "offer_price": 250.0, "total_sessions": 10, "used_sessions": 5,
         "remaining_sessions": 5, "expires_at": _iso(30), "created_at": _iso(-10)},
        {"id": "pulse-reel", "code": "DUO-01", "email": "m@ex.test",
         "coach_id": COACH, "status": "active", "offer_name": "PULSE x10 cours",
         "offer_price": 250.0, "total_sessions": 10, "used_sessions": 6,
         "remaining_sessions": 4, "expires_at": _iso(30), "created_at": _iso(-10)},
    ]


async def partie_e_departage():
    docs = _deux_pulse()
    # La regle unique du depot (V391/V394) : c'est elle qui fait foi partout.
    attendu = SHARED.choisir_abonnement(docs)
    verifier("E0. la regle unique designe le document REELLEMENT debite "
             "(used_sessions le plus haut)",
             attendu.get("id") == "pulse-reel",
             "obtenu %r" % attendu.get("id"))

    # Finance : on execute la VRAIE fonction d'enrichissement.
    db = _Base()
    db.subscriptions.docs = [dict(d) for d in docs]
    db.discount_codes.docs = [{"code": "DUO-01", "offerName": "PULSE x10 cours"}]
    ns = {
        "db": db, "logger": _Journal(), "HTTPException": _HTTPException,
        "_A_COLLATION_INSENSIBLE": None, "isinstance": isinstance, "dict": dict,
        "str": str, "set": set, "sorted": sorted, "bool": bool, "len": len,
    }
    exec(compile(_extraire(SRC_RESA, "_a_enrichir_finance"),
                 "reservation_routes.py", "exec"), ns)

    # Une reservation SANS subscriptionId : c'est le stock ancien, et les 74
    # reservations de l'espace abonne d'aujourd'hui. Elle ne peut etre resolue
    # que par son CODE — donc c'est la que le departage doit s'appliquer.
    resas = [{"id": "r1", "promoCode": "DUO-01", "userEmail": "m@ex.test"}]
    enrichies = await ns["_a_enrichir_finance"](resas, {})
    _offre = (enrichies[0].get("finance") or {}).get("offre")
    verifier("E1. Finance resout par le CODE quand `subscriptionId` manque",
             bool(_offre), "finance=%r" % (enrichies[0].get("finance"),))

    # LA verification du lot : Finance ne doit pas prendre « le premier rendu
    # par Mongo » mais LE MEME document que le debit.
    verifier("E2. Finance designe le MEME document que le debit "
             "(pas le premier rendu par Mongo)",
             "choisir_abonnement" in _code_nu(SRC_RESA, "_a_enrichir_finance"),
             "l'enrichissement n'appelle pas la regle unique")
    # E3 — LA VERIFICATION FONCTIONNELLE, celle qui compte vraiment.
    #
    # Les deux documents portent le MEME code et la MEME offre : rien dans le
    # bloc `finance` ne permettrait de les distinguer... sauf le denominateur.
    # On leur donne donc deux `renewal_sessions` differentes, et `finance`
    # revele alors lequel a ete retenu. Avec l'ancien `setdefault`, c'etait le
    # premier document du lot (`pulse-vieux`, 10) ; avec la regle unique, c'est
    # celui que le debit consomme (`pulse-reel`, 8).
    docs2 = _deux_pulse()
    docs2[0]["renewal_sessions"] = 10     # pulse-vieux — le premier rendu par Mongo
    docs2[1]["renewal_sessions"] = 8      # pulse-reel  — celui que le debit choisit
    db2 = _Base()
    db2.subscriptions.docs = [dict(d) for d in docs2]
    db2.discount_codes.docs = [{"code": "DUO-01", "offerName": "PULSE x10 cours"}]
    ns2 = dict(ns)
    ns2["db"] = db2
    exec(compile(_extraire(SRC_RESA, "_a_enrichir_finance"),
                 "reservation_routes.py", "exec"), ns2)
    e2 = await ns2["_a_enrichir_finance"](
        [{"id": "r1", "promoCode": "DUO-01", "userEmail": "m@ex.test"}], {})
    _retenu = (e2[0].get("finance") or {}).get("seances_achetees")
    verifier("E3. FONCTIONNEL — Finance retient le document que le DEBIT "
             "consomme, pas le premier rendu par Mongo",
             _retenu == 8,
             "seances_achetees=%r (8 = pulse-reel, 10 = pulse-vieux)" % (_retenu,))


# ═══════════════════════════════════════════════════════════════════════════
# A a D — LE TYPE DE DROIT RESTE DECIDE PAR LE CONTEXTE, JAMAIS PAR LE TRI
# ═══════════════════════════════════════════════════════════════════════════
def partie_abcd_type_de_droit():
    corps = _code_nu(SRC_RESA, "create_reservation")

    verifier("B. sans identifiant de droit explicite, AUCUNE deduction "
             "(c'est ce qui protege PULSE d'une reservation a l'unite)",
             "is_free_or_single_purchase" in corps)

    # Le NIVEAU 1 ne doit JAMAIS etre tranche par `choisir_abonnement` : ce
    # serait « prendre un abonnement actif », exactement la regle refusee.
    arbre = ast.parse(_extraire(SRC_RESA, "create_reservation"))
    _appels_sans_code = []
    for n in ast.walk(arbre):
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") in (
                "choisir_abonnement", "_v391_choisir"):
            _appels_sans_code.append(getattr(n, "lineno", "?"))
    verifier("A. le TYPE de droit n'est jamais choisi par un tri : "
             "`choisir_abonnement` n'est pas appele a nu sur l'email",
             not _appels_sans_code, "appels en %r" % (_appels_sans_code,))

    verifier("A2. la selection par CODE passe par la regle unique "
             "(`lire_abonnement_par_code`), plus par un find_one brut",
             "lire_abonnement_par_code" in corps or "_l3c0c_lire" in corps)

    # D — un event a billet separe ne doit pas manger une seance de forfait.
    verifier("D. la garde « activite non incluse dans le forfait » protege "
             "aussi POST /reservations",
             "_l3c0c_event_inclus" in corps or "linked_course_ids" in corps)


# ═══════════════════════════════════════════════════════════════════════════
# F et G — TRANSACTIONS : un achat reel compte UNE fois, aucun ne disparait
# ═══════════════════════════════════════════════════════════════════════════
async def partie_fg_transactions():
    db = _base_avec_paiements()
    db.reservations.docs = [
        # Une CONSOMMATION : elle reference la souscription, mais n'est pas la vente.
        {"id": "r1", "coach_id": COACH, "subscriptionId": "sub-1",
         "promoCode": "AFR-VENDU", "userEmail": "m@ex.test", "createdAt": _iso(-1)},
    ]
    db.subscriptions.docs = [
        # LA VENTE : 250 CHF encaisses par Stripe.
        {"id": "sub-1", "code": "AFR-VENDU", "email": "m@ex.test", "coach_id": COACH,
         "status": "active", "offer_name": "PULSE x10", "total_sessions": 10,
         "used_sessions": 1, "remaining_sessions": 9, "created_at": _iso(-3)},
    ]
    db.discount_codes.docs = [
        {"code": "AFR-VENDU", "offerName": "PULSE x10", "maxUses": 10,
         "stripe_amount": 250.0, "session_id": "cs_test_123", "coach_id": COACH},
    ]
    db.payment_transactions.docs = [
        # LE MEME ACHAT, vu du cote paiement : meme session_id.
        {"id": "p1", "session_id": "cs_test_123", "amount": 250.0, "currency": "chf",
         "coach_id": COACH, "created_at": _iso(-3), "payment_status": "paid",
         "metadata": {"customer_email": "m@ex.test", "product_name": "PULSE x10"}},
        # UN AUTRE achat, sans souscription en face : il doit RESTER visible.
        {"id": "p2", "session_id": "cs_test_999", "amount": 40.0, "currency": "chf",
         "coach_id": COACH, "created_at": _iso(-2), "payment_status": "paid",
         "metadata": {"customer_email": "autre@ex.test", "product_name": "Atelier"}},
    ]

    class _Req:
        headers = {}
    ns = {
        "db": db, "logger": _Journal(), "HTTPException": _HTTPException,
        "is_super_admin": SHARED.is_super_admin, "Request": object,
        "int": int, "bool": bool, "len": len, "str": str, "any": any,
        "isinstance": isinstance, "sorted": sorted, "dict": dict, "set": set,
    }

    async def _jwt(r):
        return ADMIN

    async def _est_coach(e):
        return True
    ns["_v311_coach_email_from_jwt"] = lambda r: ADMIN
    ns["_v309_is_coach_or_admin"] = _est_coach
    exec(compile(_extraire(SRC_SERVER, "get_all_transactions"), "server.py", "exec"), ns)

    res = await ns["get_all_transactions"](_Req(), 1, 100)
    items = res.get("transactions") or res.get("items") or res.get("data") or []
    types_par_id = {(i.get("id"), i.get("_tx_type")) for i in items}

    # G — la VENTE ne doit jamais disparaitre parce qu'une reservation la consomme.
    verifier("G. la vente du forfait reste visible meme quand une reservation "
             "la consomme (9 ventes etaient masquees a tort)",
             ("sub-1", "subscription") in types_par_id,
             "types presents : %r" % (sorted(str(t) for t in types_par_id),))

    # F — le paiement Stripe du MEME achat ne doit pas faire une 2e recette.
    verifier("F. un achat reel compte UNE fois : le paiement jumeau "
             "(meme session_id) n'est pas ajoute en double",
             ("p1", "payment") not in types_par_id,
             "types presents : %r" % (sorted(str(t) for t in types_par_id),))

    # G bis — et un paiement SANS souscription en face reste visible.
    verifier("G2. un paiement sans souscription jumelle reste visible "
             "(aucune transaction legitime ne disparait)",
             ("p2", "payment") in types_par_id,
             "types presents : %r" % (sorted(str(t) for t in types_par_id),))

    corps_tx = _code_nu(SRC_SERVER, "get_all_transactions")
    verifier("F2. la deduplication s'appuie sur une preuve STABLE "
             "(session_id / transaction_id), jamais sur le montant ou le nom",
             "session_id" in corps_tx)


# ═══════════════════════════════════════════════════════════════════════════
# PERIMETRE — ce lot ne compte rien, ne migre rien
# ═══════════════════════════════════════════════════════════════════════════
def partie_perimetre():
    # ⚠️ La garde porte sur les donnees FINANCIERES, pas sur toute ecriture de
    # masse : `create_reservation` porte depuis longtemps un `update_many` sur
    # `chat_participants` (l. 1428), sans aucun rapport avec l'argent. Une
    # assertion qui l'interdirait serait fausse — et serait « affaiblie » plus
    # tard pour la mauvaise raison. On nomme donc les collections qui comptent.
    for nom, src in (("get_all_transactions", SRC_SERVER),
                     ("_a_enrichir_finance", SRC_RESA),
                     ("create_reservation", SRC_RESA)):
        corps = _code_nu(src, nom)
        _masse = [c for c in ("subscriptions", "discount_codes")
                  if ("%s.update_many" % c) in corps or ("%s.delete_many" % c) in corps]
        verifier("P. %s : aucune ecriture de masse sur les donnees financieres"
                 % nom, not _masse and "create_index" not in corps,
                 "collections touchees : %r" % (_masse,))
    verifier("P2. MEMBER_PRICING_ENABLED reste a false",
             'MEMBER_PRICING_ENABLED: bool = False' in SRC_SERVER
             and '"MEMBER_PRICING_ENABLED": False' in SRC_SERVER)
    verifier("P3. aucune division naive prix/seances introduite "
             "(la valeur d'une seance vient de `tarif_applique`)",
             "/ 10" not in _code_nu(SRC_SERVER, "get_all_transactions"))


def partie_h_trace():
    """La reservation doit porter le droit qu'elle a debite, pas le laisser deviner."""
    esp = _code_nu(SRC_SERVER, "reserve_course_from_space")

    # Le chemin MAJORITAIRE (74 reservations sur 132) debitait `subscription["id"]`
    # puis construisait un document SANS cet identifiant : l'information etait en
    # main, a dix lignes, et jetee.
    verifier("H1. l'espace abonne ecrit le `subscriptionId` qu'il vient de debiter",
             "subscriptionId" in esp)

    # Le document jumeau (`discount_codes`) porte la PREUVE du montant
    # (`stripe_amount` + `session_id`) et le denominateur (`maxUses`). Deux des
    # trois chemins passaient `None` a sa place : la couverture du snapshot
    # tombait de 20,6 % a 6,3 %. Les deux documents sont pourtant deja lus dans
    # la portee — c'est un argument a passer, pas une requete a ajouter.
    _appels = []
    for src, nom in ((SRC_SERVER, "reserve_course_from_space"),
                     (SRC_RESA, "create_reservation"),
                     (SRC_RESA, "_qr_scan_validate_inner")):
        try:
            corps = _extraire(src, nom)
        except AssertionError:
            continue
        for ligne in corps.splitlines():
            if "_lot3_champs(" in ligne:
                _appels.append((nom, "None" in ligne.split("_lot3_champs(")[1][:40]))
    _sans_jumeau = [n for n, sans in _appels if sans]
    verifier("H2. les chemins de presence passent le document jumeau au "
             "snapshot LOT 3a, plus `None`",
             not _sans_jumeau,
             "encore a None : %r (sur %d appels trouves)" % (_sans_jumeau, len(_appels)))


async def principal():
    await partie_e_departage()
    partie_abcd_type_de_droit()
    partie_h_trace()
    await partie_fg_transactions()
    partie_perimetre()

    ok = sum(1 for _, c, _ in RESULTATS if c)
    print("\n" + "=" * 74)
    print("LOT 3c-0c — UNE SEULE REGLE, DU DEBIT JUSQU'A FINANCE")
    print("=" * 74)
    for nom, cond, detail in RESULTATS:
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom,
                              "" if cond or not detail else "\n          -> %s" % detail))
    print("-" * 74)
    print("Souscriptions / paiements REELS : 0 — base en memoire")
    print("%d / %d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(principal()))
