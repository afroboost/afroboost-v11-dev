# -*- coding: utf-8 -*-
"""PREALABLE LOT 3 FINANCE — deux lectures amputees qui rendraient le bilan faux.

POURQUOI CE LOT EXISTE. Le futur bilan financier lira `tarif_applique`, fige a
l'ecriture de la reservation, et le montant du droit derriere chaque presence.
Deux lectures l'en empechent aujourd'hui — et toutes deux echouent EN SILENCE :
elles ne produisent pas un chiffre faux, elles produisent MOINS de chiffres. Un
bilan incomplet qui a l'air complet est pire qu'un bilan qui manque.

CAS A — LA PROJECTION QUI VIDE LE DOCUMENT JUMEAU.
`reserve_course_from_space` lit le code jumeau avec `{"_id": 0,
"shared_sessions": 1}` — il n'en garde qu'UN champ. Or `a_finance_du_droit` a
besoin de `stripe_amount`, `session_id`, `total_paid`, `transaction_id` et
`payment_method`, qui vivent tous sur ce document. LOT 3c-0c a bien remplace le
`None` par ce document, mais le document etait deja vide de ce qui compte : le
correctif etait donc INOPERANT sur ce chemin — celui qui porte 74 des 132
reservations, soit 56 % du trafic reel.

CAS B — LE PREMIER DOCUMENT PLUTOT QUE LE BON.
Quand plusieurs `discount_codes` portent le meme code, l'enrichissement
financier retenait le PREMIER rendu par Mongo (`setdefault`). Or l'argent est
sur l'autre : quatre codes de production portent leur montant sur le document
marque `canonical`, et zero sur le premier. 900 CHF de recettes REELLES etaient
donc invisibles du calcul.

⚠️ CE LOT NE FABRIQUE AUCUN `canonical`. Il LIT celui que la base porte deja.
Aucune fusion, aucun nettoyage, aucune donnee touchee.

AUCUNE BASE REELLE POUR LE CAS B (base en memoire) ; `mongod` JETABLE pour le
cas A, car seul un vrai moteur applique les projections.
    python3 tests/test_lot3_prealable_snapshot.py
"""
import ast, asyncio, importlib.util, io, os, shutil, socket
import subprocess, sys, tempfile, time, types
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from tests._banc_qr import RESULTATS, verifier, _Base, _HTTPException  # noqa: E402

_fa = types.ModuleType("fastapi")
_fa.HTTPException = _HTTPException
_fa.APIRouter = object
_fa.Request = object
sys.modules.setdefault("fastapi", _fa)

_spec = importlib.util.spec_from_file_location(
    "l3p_shared", os.path.join(RACINE, "api", "routes", "shared.py"))
SHARED = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SHARED)
sys.modules["api"] = types.ModuleType("api")
sys.modules["api.routes"] = types.ModuleType("api.routes")
sys.modules["api.routes.shared"] = SHARED

SRC_SERVER = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
SRC_RESA = io.open(os.path.join(RACINE, "api", "routes", "reservation_routes.py"),
                   encoding="utf-8").read()


def _extraire(src, nom):
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


def _iso(j):
    return (datetime.now(timezone.utc) + timedelta(days=j)).isoformat()


# ═══════════════════════════════════════════════════════════════════════════
# CAS A — LA PROJECTION, eprouvee contre un VRAI moteur
# ═══════════════════════════════════════════════════════════════════════════
def _projection_du_jumeau():
    """La projection REELLE passee a la lecture du code jumeau, lue dans le source.

    On n'ecrit pas la projection dans le test : on va chercher CELLE QUI TOURNE.
    Le test reste donc vrai quelle que soit la facon dont elle est corrigee.
    """
    arbre = ast.parse(SRC_SERVER)
    for n in ast.walk(arbre):
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if n.name != "reserve_course_from_space":
            continue
        for interne in ast.walk(n):
            if not isinstance(interne, ast.Assign):
                continue
            cible = getattr(interne.targets[0], "id", "")
            if cible != "discount_for_mode":
                continue
            appel = interne.value
            while isinstance(appel, ast.Await):
                appel = appel.value
            if isinstance(appel, ast.Call) and len(appel.args) >= 2:
                return ast.literal_eval(appel.args[1])
            return None
    raise AssertionError("lecture de `discount_for_mode` introuvable")


class MongoJetable(object):
    def __init__(self):
        self.dbpath = tempfile.mkdtemp(prefix="l3p-mongo-")
        s = socket.socket(); s.bind(("127.0.0.1", 0))
        self.port = s.getsockname()[1]; s.close()
        self.proc = None

    def __enter__(self):
        self.proc = subprocess.Popen(
            ["mongod", "--dbpath", self.dbpath, "--port", str(self.port),
             "--bind_ip", "127.0.0.1", "--nojournal"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        limite = time.time() + 40
        while time.time() < limite:
            try:
                socket.create_connection(("127.0.0.1", self.port), 0.5).close()
                return self
            except OSError:
                if self.proc.poll() is not None:
                    raise AssertionError("mongod s'est arrete au demarrage")
                time.sleep(0.2)
        raise AssertionError("mongod n'a pas demarre")

    def __exit__(self, *_):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        shutil.rmtree(self.dbpath, ignore_errors=True)


async def partie_a_projection():
    from motor.motor_asyncio import AsyncIOMotorClient
    projection = _projection_du_jumeau()

    with MongoJetable() as mongo:
        client = AsyncIOMotorClient("mongodb://127.0.0.1:%d" % mongo.port)
        db = client["l3p_jetable"]

        # Un forfait PAYE ET PROUVE : 150 CHF encaisses par Stripe, 10 seances.
        # C'est le cas metier que le proprietaire cite — 15 CHF la seance, pas 25.
        await db.discount_codes.insert_one({
            "code": "AFR-PREUVE", "stripe_amount": 150.0,
            "session_id": "cs_test_preuve", "maxUses": 10,
            "shared_sessions": True, "offerName": "PULSE x10 cours"})
        sub = {"id": "s1", "code": "AFR-PREUVE", "email": "a@ex.test",
               "status": "active", "total_sessions": 10, "used_sessions": 1,
               "remaining_sessions": 9, "renewal_sessions": 10,
               "offer_name": "PULSE x10 cours", "created_at": _iso(-5)}
        await db.subscriptions.insert_one(dict(sub))

        # On rejoue la lecture EXACTEMENT comme la route la fait.
        jumeau = await db.discount_codes.find_one({"code": "AFR-PREUVE"}, projection)
        snap = SHARED.lot3_champs_forfait(sub, jumeau, None)

        verifier("A1. le document jumeau lu porte la PREUVE du montant "
                 "(`stripe_amount` + `session_id`)",
                 bool((jumeau or {}).get("stripe_amount")) and bool((jumeau or {}).get("session_id")),
                 "champs recus : %r" % sorted((jumeau or {}).keys()))
        verifier("A2. ... et le denominateur (`maxUses`)",
                 bool((jumeau or {}).get("maxUses")),
                 "champs recus : %r" % sorted((jumeau or {}).keys()))
        verifier("A3. le snapshot tarifaire est donc PRODUIT",
                 bool(snap), "snapshot : %r" % (snap,))
        verifier("A4. ... a la bonne valeur : 150 CHF / 10 seances = 15.00, "
                 "et NON une division du prix affiche",
                 (snap or {}).get("tarif_applique") == 15.0,
                 "tarif_applique = %r" % (snap or {}).get("tarif_applique"))
        verifier("A5. ... avec la bonne raison",
                 (snap or {}).get("tarif_raison") == "forfait",
                 "tarif_raison = %r" % (snap or {}).get("tarif_raison"))

        # Contre-epreuve : la gratuite se lit sur le CODE, pas sur la souscription.
        await db.discount_codes.insert_one({
            "code": "AFR-ESSAI", "payment_method": "free", "total_paid": 0,
            "maxUses": 1, "shared_sessions": True})
        sub2 = {"id": "s2", "code": "AFR-ESSAI", "status": "active",
                "total_sessions": 1, "used_sessions": 0, "remaining_sessions": 1}
        j2 = await db.discount_codes.find_one({"code": "AFR-ESSAI"}, projection)
        snap2 = SHARED.lot3_champs_forfait(sub2, j2, None)
        verifier("A6. un essai gratuit est reconnu comme `essai`, pas comme "
                 "`offert` (la preuve est sur le code jumeau)",
                 (snap2 or {}).get("tarif_raison") == "essai",
                 "tarif_raison = %r" % (snap2 or {}).get("tarif_raison"))

        await client.drop_database("l3p_jetable")
        client.close()


# ═══════════════════════════════════════════════════════════════════════════
# CAS B — LE DOCUMENT CANONIQUE, pas le premier rendu par Mongo
# ═══════════════════════════════════════════════════════════════════════════
async def partie_b_canonical():
    db = _Base()
    # Le stock reel : quatre codes de production ont exactement cette forme —
    # un premier document SANS montant, un second `canonical` qui porte l'argent.
    db.discount_codes.docs = [
        {"code": "DUP-01", "stripe_amount": None, "offerName": "PULSE x10"},
        {"code": "DUP-01", "stripe_amount": 250.0, "session_id": "cs_dup",
         "maxUses": 10, "canonical": True, "offerName": "PULSE x10"},
    ]
    db.subscriptions.docs = [
        {"id": "sub-dup", "code": "DUP-01", "email": "m@ex.test", "status": "active",
         "total_sessions": 10, "used_sessions": 2, "remaining_sessions": 8,
         "renewal_sessions": 10, "offer_name": "PULSE x10", "created_at": _iso(-3)},
    ]
    ns = {
        "db": db, "logger": _Journal(), "HTTPException": _HTTPException,
        "_A_COLLATION_INSENSIBLE": None, "isinstance": isinstance, "dict": dict,
        "str": str, "set": set, "sorted": sorted, "bool": bool, "len": len,
    }
    exec(compile(_extraire(SRC_RESA, "_a_enrichir_finance"),
                 "reservation_routes.py", "exec"), ns)

    res = await ns["_a_enrichir_finance"](
        [{"id": "r1", "promoCode": "DUP-01", "userEmail": "m@ex.test"}], {})
    fin = res[0].get("finance") or {}

    verifier("B1. Finance lit le document CANONIQUE, pas le premier rendu "
             "par Mongo (l'argent est sur le canonique)",
             fin.get("montant") == 250.0,
             "montant = %r (250 = canonique, None = premier document)" % fin.get("montant"))
    verifier("B2. ... et le montant est reconnu comme PROUVE "
             "(`stripe_amount` + `session_id`)",
             fin.get("montant_prouve") is True,
             "montant_prouve = %r" % fin.get("montant_prouve"))
    verifier("B3. ... donc la valeur d'UNE seance est calculable : 250/10 = 25 "
             "ICI, parce que le montant est PROUVE et le denominateur connu",
             fin.get("valeur_par_seance") == 25.0,
             "valeur_par_seance = %r" % fin.get("valeur_par_seance"))

    # L'ordre ne doit rien changer : le canonique gagne meme s'il arrive en second,
    # en premier, ou entoure d'autres doublons.
    db2 = _Base()
    db2.discount_codes.docs = [
        {"code": "DUP-01", "stripe_amount": 250.0, "session_id": "cs_dup",
         "maxUses": 10, "canonical": True, "offerName": "PULSE x10"},
        {"code": "DUP-01", "stripe_amount": None, "offerName": "PULSE x10"},
    ]
    db2.subscriptions.docs = [dict(d) for d in db.subscriptions.docs]
    ns2 = dict(ns); ns2["db"] = db2
    exec(compile(_extraire(SRC_RESA, "_a_enrichir_finance"),
                 "reservation_routes.py", "exec"), ns2)
    res2 = await ns2["_a_enrichir_finance"](
        [{"id": "r1", "promoCode": "DUP-01", "userEmail": "m@ex.test"}], {})
    verifier("B4. le resultat ne depend PAS de l'ordre rendu par Mongo",
             (res2[0].get("finance") or {}).get("montant") == 250.0,
             "montant = %r" % (res2[0].get("finance") or {}).get("montant"))

    # Sans canonique, on garde le comportement d'avant : aucun choix arbitraire
    # nouveau n'est introduit.
    db3 = _Base()
    db3.discount_codes.docs = [{"code": "SOLO-01", "stripe_amount": 40.0,
                                "session_id": "cs_solo", "maxUses": 4}]
    db3.subscriptions.docs = [
        {"id": "s3", "code": "SOLO-01", "email": "x@ex.test", "status": "active",
         "total_sessions": 4, "used_sessions": 0, "remaining_sessions": 4,
         "renewal_sessions": 4, "created_at": _iso(-1)}]
    ns3 = dict(ns); ns3["db"] = db3
    exec(compile(_extraire(SRC_RESA, "_a_enrichir_finance"),
                 "reservation_routes.py", "exec"), ns3)
    res3 = await ns3["_a_enrichir_finance"](
        [{"id": "r2", "promoCode": "SOLO-01", "userEmail": "x@ex.test"}], {})
    verifier("B5. un code SANS doublon reste lu exactement comme avant",
             (res3[0].get("finance") or {}).get("montant") == 40.0,
             "montant = %r" % (res3[0].get("finance") or {}).get("montant"))


def partie_c_perimetre():
    """Un prealable de deux lignes. Il ne compte rien, ne migre rien, ne fusionne rien."""
    corps_esp = ast.unparse(ast.parse(_extraire(SRC_SERVER, "reserve_course_from_space")))
    corps_fin = ast.unparse(ast.parse(_extraire(SRC_RESA, "_a_enrichir_finance")))

    # ⚠️ L'espace abonne INCREMENTE legitimement `discount_codes.used` : c'est la
    # consommation d'une seance, elle existe depuis toujours et n'a rien a voir
    # avec ce prealable. Interdire toute ecriture serait faux, et l'assertion
    # serait « assouplie » plus tard pour la mauvaise raison. Ce qu'on garantit
    # ici, c'est qu'AUCUNE FUSION ni suppression de doublon n'est introduite.
    for nom, corps in (("espace abonne", corps_esp), ("enrichissement finance", corps_fin)):
        verifier("C. %s : aucune fusion ni suppression de doublon" % nom,
                 "discount_codes.delete" not in corps
                 and "discount_codes.insert" not in corps
                 and "update_many" not in corps
                 and "subscriptions.insert" not in corps)
    verifier("C1b. l'enrichissement financier reste en LECTURE PURE",
             "update_one" not in corps_fin and "insert_one" not in corps_fin
             and "delete_one" not in corps_fin)
    verifier("C2. aucun `canonical` n'est FABRIQUE — on lit celui de la base",
             '"canonical": True' not in corps_fin and "'canonical': True" not in corps_fin)
    verifier("C3. MEMBER_PRICING_ENABLED reste a false",
             'MEMBER_PRICING_ENABLED: bool = False' in SRC_SERVER)


async def principal():
    await partie_a_projection()
    await partie_b_canonical()
    partie_c_perimetre()

    ok = sum(1 for _, c, _ in RESULTATS if c)
    print("\n" + "=" * 74)
    print("PREALABLE LOT 3 FINANCE — LE BILAN LIRA CE QUI EXISTE DEJA")
    print("=" * 74)
    for nom, cond, detail in RESULTATS:
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom,
                              "" if cond or not detail else "\n          -> %s" % detail))
    print("-" * 74)
    print("mongod jetable detruit, base en memoire. Donnees de production : 0")
    print("%d / %d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(principal()))
