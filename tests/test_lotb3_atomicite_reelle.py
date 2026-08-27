# -*- coding: utf-8 -*-
"""LOT B3 — PREUVE D'ATOMICITE, SUR UN VRAI REPLICA SET.

POURQUOI CE FICHIER EXISTE. `tests/test_lotb3_annulation_coherente.py` verifie
la REGLE avec un faux Mongo — il ne peut pas prouver qu'une transaction se
defait vraiment. Ici on execute LE VRAI `delete_reservation`, extrait du vrai
fichier, contre une base JETABLE du cluster reel : commit, abort, concurrence
et rejeu sont observes sur le moteur, pas simules.

IL NE TOURNE PAS TOUT SEUL. Sans `LOTB3_PREUVE_REELLE=1`, il sort au vert sans
rien creer : un banc qui fabrique une base a chaque passage de la suite serait
une nuisance, et un risque.

    LOTB3_PREUVE_REELLE=1 python3 tests/test_lotb3_atomicite_reelle.py

DONNEES 100 % SYNTHETIQUES, base supprimee a la fin, nommee explicitement —
jamais de joker. Aucune donnee reelle n'est lue, copiee ni modifiee.
"""
import ast, asyncio, importlib.util, io, os, re, sys, types, uuid

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

PREFIXE = "afroboost_lotb3_app_test_"

if os.environ.get("LOTB3_PREUVE_REELLE", "") != "1":
    print("LOT B3 — PREUVE REELLE : ignoree (poser LOTB3_PREUVE_REELLE=1 pour l'executer).")
    print("  Ce banc cree une base JETABLE sur le cluster : il ne s'execute jamais par accident.")
    sys.exit(0)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def _env(cle):
    s = io.open(os.path.join(RACINE, ".env.local"), encoding="utf-8").read()
    m = re.search(cle + r'\s*=\s*"?([^"\n]+)"?', s)
    return m.group(1).strip() if m else ""


from motor.motor_asyncio import AsyncIOMotorClient          # noqa: E402
from pymongo.errors import PyMongoError                      # noqa: E402

COACH = "coach-synthetique"


class ErreurInjectee(Exception):
    pass


class CollectionQuiTombe:
    """Enrobe une VRAIE collection et fait echouer `update_one` a la demande.
    La panne est applicative ; c'est le MOTEUR qui doit defaire la transaction."""

    def __init__(self, vraie):
        self._vraie, self.armee = vraie, False

    def __getattr__(self, nom):
        return getattr(self._vraie, nom)

    async def update_one(self, *a, **k):
        if self.armee:
            raise ErreurInjectee("panne applicative injectee")
        return await self._vraie.update_one(*a, **k)


class BaseEnrobee:
    def __init__(self, vraie):
        self._vraie = vraie
        self.subscriptions = CollectionQuiTombe(vraie.subscriptions)
        self.discount_codes = CollectionQuiTombe(vraie.discount_codes)

    def __getattr__(self, nom):
        return getattr(self._vraie, nom)


def espace(db, appelant=COACH):
    """Le VRAI `delete_reservation`, branche sur la base jetable."""
    faux = types.ModuleType("api.server")

    async def _v309_require_coach_or_admin(request):
        if not appelant:
            from fastapi import HTTPException as _H
            raise _H(status_code=403, detail="Authentification coach requise")
        return appelant

    faux._v309_require_coach_or_admin = _v309_require_coach_or_admin
    sys.modules["api.server"] = faux

    from fastapi import HTTPException
    src = io.open(os.path.join(RACINE, "api", "routes", "reservation_routes.py"),
                  encoding="utf-8").read()
    arbre, lignes = ast.parse(src), src.splitlines(True)
    ns = {"db": db, "re": re, "logger": _Journal(), "HTTPException": HTTPException,
          "datetime": __import__("datetime").datetime,
          "timezone": __import__("datetime").timezone,
          "asyncio": asyncio, "uuid": uuid, "Request": object,
          "DEFAULT_COACH_ID": COACH, "_RESEND_OK": False, "_RESEND_KEY": "",
          "SUPER_ADMIN_EMAIL": "admin-synthetique",
          "is_super_admin": lambda e: (e or "") == "admin-synthetique"}
    for n in ast.walk(arbre):
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in (
                "R11_MSG_ANONYME", "R11_MSG_AUTRE_COACH"):
            exec(compile("".join(lignes[n.lineno - 1:n.end_lineno]), "r", "exec"), ns)
    for nom in ("_r11_scanneur", "_r11_verifier_proprietaire", "delete_reservation"):
        for n in ast.walk(arbre):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
                exec(compile("".join(lignes[n.lineno - 1:n.end_lineno]), "r", "exec"), ns)
    return ns


class _Journal:
    def __init__(self):
        self.lignes = []

    def _n(self, niv, m, a):
        try:
            self.lignes.append("%s %s" % (niv, (str(m) % a) if a else m))
        except (TypeError, ValueError):
            self.lignes.append("%s %s" % (niv, m))

    def info(self, m="", *a, **k):
        self._n("INFO", m, a)

    def warning(self, m="", *a, **k):
        self._n("WARN", m, a)

    def error(self, m="", *a, **k):
        self._n("ERROR", m, a)


class _Req:
    async def json(self):
        return {}


async def semer(db, n, source="subscriber_space", quantite=1, used=5):
    await db.reservations.insert_one(
        {"id": "resa-%d" % n, "reservationCode": "SYNTH%04d" % n, "quantity": quantite,
         "userEmail": "membre%d@exemple.invalid" % n, "promoCode": "SYNTHCODE-%d" % n,
         "discountCode": "SYNTHCODE-%d" % n, "subscriptionId": "sub-%d" % n,
         "source": source, "coach_id": COACH, "courseName": "Cours synthetique"})
    await db.subscriptions.insert_one(
        {"id": "sub-%d" % n, "code": "SYNTHCODE-%d" % n, "email": "membre%d@exemple.invalid" % n,
         "used_sessions": used, "remaining_sessions": 10 - used, "total_sessions": 10,
         "status": "active"})
    await db.discount_codes.insert_one(
        {"id": "dc-%d" % n, "code": "SYNTHCODE-%d" % n, "used": used, "maxUses": 10,
         "active": True, "expiresAt": None})


async def etat(db, n):
    r = await db.reservations.find_one({"id": "resa-%d" % n})
    s = await db.subscriptions.find_one({"id": "sub-%d" % n})
    d = await db.discount_codes.find_one({"id": "dc-%d" % n})
    return (r is not None, s["used_sessions"], s["remaining_sessions"], d["used"])


async def principal():
    reelle, base = _env("DB_NAME"), PREFIXE + uuid.uuid4().hex[:12]
    cli = AsyncIOMotorClient(_env("MONGO_URL"), maxPoolSize=8)
    existantes = await cli.list_database_names()
    print("base jetable : %s" % base)
    if base == reelle or base in existantes or not base.startswith(PREFIXE):
        print("STOP — isolation non garantie, aucune ecriture."); sys.exit(1)
    verifier("0. base jetable isolee de la base applicative", True, "")

    db = cli[base]
    for c in ("reservations", "subscriptions", "discount_codes", "notifications"):
        await db.create_collection(c)
    os.environ["LOTB3_ANNULATION_CANONIQUE_ENABLED"] = "true"
    try:
        # ── 1. NOMINAL : les trois effets, sur le vrai moteur ──────────────
        await semer(db, 1)
        ns = espace(BaseEnrobee(db))
        rep = await ns["delete_reservation"]("resa-1", _Req())
        verifier("1. annulation acceptee", rep.get("success") is True, rep)
        verifier("1. les TROIS effets sont presents ensemble",
                 await etat(db, 1) == (False, 4, 6, 4), await etat(db, 1))

        # ── 2. PANNE APRES LA SUPPRESSION -> le moteur defait tout ─────────
        await semer(db, 2)
        enrobee = BaseEnrobee(db)
        enrobee.subscriptions.armee = True
        ns = espace(enrobee)
        try:
            await ns["delete_reservation"]("resa-2", _Req())
            leve = None
        except Exception as e:                                   # noqa: BLE001
            leve = e
        verifier("2. la route refuse proprement", leve is not None and getattr(leve, "status_code", 0) == 500,
                 getattr(leve, "status_code", leve))
        verifier("2. ROLLBACK REEL : la reservation existe toujours",
                 (await etat(db, 2))[0] is True, await etat(db, 2))
        verifier("2. ROLLBACK REEL : aucun compteur n'a bouge",
                 await etat(db, 2) == (True, 5, 5, 5), await etat(db, 2))

        # ── 3. PANNE APRES LE COMPTEUR ABONNEMENT ─────────────────────────
        await semer(db, 3)
        enrobee = BaseEnrobee(db)
        enrobee.discount_codes.armee = True
        ns = espace(enrobee)
        try:
            await ns["delete_reservation"]("resa-3", _Req())
            leve = None
        except Exception as e:                                   # noqa: BLE001
            leve = e
        verifier("3. la route refuse proprement", leve is not None, leve)
        verifier("3. ROLLBACK REEL : aucun effet intermediaire conserve",
                 await etat(db, 3) == (True, 5, 5, 5), await etat(db, 3))

        # ── 4. CONCURRENCE REELLE ─────────────────────────────────────────
        await semer(db, 4)
        ns = espace(BaseEnrobee(db))

        async def tenter():
            try:
                await ns["delete_reservation"]("resa-4", _Req())
                return "ok"
            except Exception as e:                               # noqa: BLE001
                return "refus:%s" % getattr(e, "status_code", type(e).__name__)

        r1, r2 = await asyncio.gather(tenter(), tenter())
        verifier("4. une seule des deux aboutit", [r1, r2].count("ok") == 1, (r1, r2))
        verifier("4. une seule restitution, aucun compteur double",
                 await etat(db, 4) == (False, 4, 6, 4), await etat(db, 4))

        # ── 5. REJEU APRES SUCCES ─────────────────────────────────────────
        avant = await etat(db, 1)
        try:
            await ns["delete_reservation"]("resa-1", _Req())
            code = "accepte"
        except Exception as e:                                   # noqa: BLE001
            code = getattr(e, "status_code", type(e).__name__)
        verifier("5. le rejeu repond 404", code == 404, code)
        verifier("5. AUCUNE seconde restitution", await etat(db, 1) == avant, (avant, await etat(db, 1)))

        # ── 6. DRAPEAU ETEINT : refus, aucune mutation ────────────────────
        await semer(db, 6)
        os.environ["LOTB3_ANNULATION_CANONIQUE_ENABLED"] = "false"
        ns = espace(BaseEnrobee(db))
        try:
            await ns["delete_reservation"]("resa-6", _Req())
            code = "accepte"
        except Exception as e:                                   # noqa: BLE001
            code = getattr(e, "status_code", type(e).__name__)
        verifier("6. drapeau false -> 503", code == 503, code)
        verifier("6. drapeau false -> AUCUNE mutation",
                 await etat(db, 6) == (True, 5, 5, 5), await etat(db, 6))
        os.environ["LOTB3_ANNULATION_CANONIQUE_ENABLED"] = "true"

        n = sum([await db[c].count_documents({}) for c in
                 ("reservations", "subscriptions", "discount_codes")])
        print("documents synthetiques encore presents : %d" % n)
    finally:
        # ── NETTOYAGE : cette base, nommee, et rien d'autre ────────────────
        if base.startswith(PREFIXE) and base != reelle:
            await cli.drop_database(base)
            apres = await cli.list_database_names()
            verifier("7. base jetable supprimee", base not in apres, base)
            verifier("7. aucune base de test residuelle",
                     not any(d.startswith(PREFIXE) for d in apres), "")
        cli.close()


asyncio.get_event_loop().run_until_complete(principal())

echecs = [x for x in RESULTATS if not x[1]]
print("\nLOT B3 — ATOMICITE REELLE (%d verifications)\n" % len(RESULTATS))
for nom, ok, detail in RESULTATS:
    print("  %s %-56s %s" % ("OK  " if ok else "ECHEC", nom, "" if ok else detail))
print("\n%d/%d au vert" % (len(RESULTATS) - len(echecs), len(RESULTATS)))
sys.exit(1 if echecs else 0)
