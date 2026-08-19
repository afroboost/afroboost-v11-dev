# -*- coding: utf-8 -*-
"""Banc d'essai partage des tests de scan QR (R11 et A0).

Mongo factice, extraction AST du VRAI fichier `api/routes/reservation_routes.py`,
bouchons explicites pour tout ce qui n'est pas teste.

AUCUNE BASE REELLE, AUCUN RESEAU, AUCUNE DONNEE DE PRODUCTION.

Ce module ne contient AUCUNE assertion : il ne fournit que l'outillage. Les
verifications vivent dans `test_r11_scan_auth.py` et `test_a0_qr_presence.py`,
qui peuvent ainsi tourner INDEPENDAMMENT l'un de l'autre — c'est ce qui rend
chaque commit du lot testable seul.

`construire()` n'exec que les fonctions REELLEMENT presentes dans le fichier :
sur le commit R11 seul, les helpers `_a0_*` n'existent pas encore et sont
simplement ignores.
"""
import ast, asyncio, io, os, re, sys, types
from datetime import datetime, timezone, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FICHIER = os.path.join(RACINE, "api", "routes", "reservation_routes.py")
_TZ_INUTILISE = None
SOURCE = io.open(FICHIER, encoding="utf-8").read()
ARBRE = ast.parse(SOURCE)
LIGNES = SOURCE.splitlines(True)

TZ_CH = timezone(timedelta(hours=2))

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def extraire(nom, obligatoire=True):
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return "".join(LIGNES[n.lineno - 1:n.end_lineno])
    if obligatoire:
        raise AssertionError("fonction introuvable : %s" % nom)
    return None


# ═══════════════════════════ Mongo factice ═══════════════════════════════════
def _cmp_regex(valeur, cond):
    motif = cond.get("$regex", "")
    drapeaux = re.I if "i" in (cond.get("$options") or "") else 0
    if not isinstance(valeur, str):
        return False            # Mongo : un $regex ne matche que des chaines
    return re.search(motif, valeur, drapeaux) is not None


def _pli(v, ci):
    """Repli de casse — simule `collation(strength: 2)` de Mongo."""
    return v.upper() if (ci and isinstance(v, str)) else v


def _match(doc, filtre, ci=False):
    for cle, cond in filtre.items():
        if cle == "$or":
            if not any(_match(doc, c, ci) for c in cond):
                return False
            continue
        val = doc.get(cle, KeyError)
        if isinstance(cond, dict):
            if "$regex" in cond:
                if not _cmp_regex(val if val is not KeyError else None, cond):
                    return False
            for op, ref in cond.items():
                if op in ("$regex", "$options"):
                    continue
                if op == "$ne":
                    if val is not KeyError and val == ref:
                        return False
                elif op == "$exists":
                    if (val is not KeyError) != ref:
                        return False
                elif op == "$nin":
                    if val in ref:
                        return False
                elif op == "$in":
                    if _pli(val, ci) not in [_pli(x, ci) for x in ref]:
                        return False
                else:
                    raise AssertionError("operateur non simule : %s" % op)
        else:
            if val is KeyError or _pli(val, ci) != _pli(cond, ci):
                return False
    return True


class _Curseur:
    """Filtrage PARESSEUX : `collation()` peut arriver apres `find()`, comme
    avec Motor. Sans cela, la casse serait deja tranchee au moment du find."""

    def __init__(self, source, filtre=None):
        self._source = source
        self._filtre = filtre
        self._ci = False
        self._sauter = 0

    def sort(self, *a, **k):
        return self

    def collation(self, *a, **k):
        self._ci = True
        return self

    def skip(self, n):
        self._sauter = int(n or 0)
        return self

    def limit(self, *a, **k):
        return self

    def _resolus(self):
        if self._filtre is None:
            return list(self._source)
        return [d for d in self._source if _match(d, self._filtre, self._ci)]

    async def to_list(self, n):
        return [dict(d) for d in self._resolus()[self._sauter:self._sauter + n]]


class _MajResultat:
    def __init__(self, n):
        self.matched_count = n
        self.modified_count = n


class _Collection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.ecritures = []

    async def find_one(self, filtre, projection=None):
        for d in self.docs:
            if _match(d, filtre):
                return dict(d)
        return None

    def find(self, filtre, projection=None):
        return _Curseur(self.docs, filtre)

    async def count_documents(self, filtre):
        return len([d for d in self.docs if _match(d, filtre)])

    async def update_one(self, filtre, maj):
        for d in self.docs:
            if _match(d, filtre):
                d.update(maj.get("$set", {}))
                self.ecritures.append(("update", dict(filtre), maj))
                return _MajResultat(1)
        return _MajResultat(0)

    async def update_many(self, filtre, maj):
        n = 0
        for d in self.docs:
            if _match(d, filtre):
                d.update(maj.get("$set", {}))
                n += 1
        if n:
            self.ecritures.append(("update_many", dict(filtre), maj))
        return _MajResultat(n)

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        self.ecritures.append(("insert", dict(doc), None))
        return types.SimpleNamespace(inserted_id="x")


class _Base:
    def __init__(self):
        self.reservations = _Collection()
        self.subscriptions = _Collection()
        self.discount_codes = _Collection()
        self.courses = _Collection()
        self.code_members = _Collection()
        self.users = _Collection()
        # B : le catalogue. Present pour PROUVER qu'il n'est plus lu comme
        # source de prix historique — le test le remplit et verifie qu'aucun de
        # ses prix ne ressort.
        self.offers = _Collection()

    def __getitem__(self, nom):
        """Certaines routes accedent aux collections par `db["nom"]`."""
        return getattr(self, nom)


# ═══════════════════════ environnement d'execution ═══════════════════════════
class _HTTPException(Exception):
    def __init__(self, status_code=500, detail="", headers=None):
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


PRESENCES = []           # ce que le funnel a recu


async def _c9_presence_faux(reservation, deja):
    PRESENCES.append((reservation.get("reservationCode"), deja))


class _Journal:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass


def construire(db):
    """Namespace d'execution du code extrait. Tout ce qui n'est pas A0 est
    remplace par un bouchon EXPLICITE : ce test ne mesure que le chemin A0."""
    ns = {
        "db": db, "re": re, "datetime": datetime, "timezone": timezone,
        "timedelta": timedelta, "logger": _Journal(), "asyncio": asyncio,
        "HTTPException": _HTTPException, "uuid": __import__("uuid"),
        "_c9_presence": _c9_presence_faux,
        "DEFAULT_COACH_ID": "coach@test",
        "_generate_afro_code": lambda: "AFTESTCODE",
        # annotations des signatures extraites
        "Request": object, "Optional": None, "List": list, "dict": dict,
    }
    ns["is_super_admin"] = lambda e: (e or "").lower().strip() in ("admin@test",)
    for nom in ("_r11_scanneur", "_r11_verifier_proprietaire",
                "_a0_maintenant_ch", "_a0_code_depuis_qr", "_a0_horodatage",
                "_a0_est_aujourdhui", "_a0_marquer_presente",
                "_a0_reservations_du_jour", "_a0_choisir_occurrence",
                "_a0_presence_deja_reservee",
                # A1 — absents des commits anterieurs, donc simplement ignores
                # la (`obligatoire=False`) : R11 et A0 restent testables seuls.
                "_a1_jour_js", "_a1_a_lieu_aujourdhui", "_a1_datetime_occurrence",
                "_a1_etiquette", "_a1_occurrences_du_jour",
                "_qr_scan_validate_inner"):
        _code = extraire(nom, obligatoire=False)
        if _code:
            exec(compile(_code, FICHIER, "exec"), ns)
    # constantes de module (pas des fonctions)
    for n in ast.walk(ARBRE):
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in (
                "A0_TOLERANCE_MIN", "R11_MSG_ANONYME", "R11_MSG_AUTRE_COACH",
                "A1_JOURS_JS"):
            exec(compile("".join(LIGNES[n.lineno - 1:n.end_lineno]), FICHIER, "exec"), ns)
    return ns


COACH_TEST = "admin@test"          # super-admin dans ce banc d'essai


def faux_api_server(email=COACH_TEST):
    """`api.server`, remplace le temps du test. `email=""` simule un anonyme."""
    m = types.ModuleType("api.server")

    async def _v309_require_coach_or_admin(request):
        if not email:
            raise _HTTPException(403, "Authentification coach requise — reconnectez-vous")
        return email

    m._v309_require_coach_or_admin = _v309_require_coach_or_admin
    sys.modules["api.server"] = m


def faux_shared(forfait_ok=(True, ""), abonnement=None):
    """`api.routes.shared`, remplace le temps du test."""
    m = types.ModuleType("api.routes.shared")

    async def lire_abonnement_par_code(db, code, email=None, filtre_supplementaire=None):
        return abonnement

    def forfait_utilisable(sub, q=1):
        return forfait_ok

    m.lire_abonnement_par_code = lire_abonnement_par_code
    m.forfait_utilisable = forfait_utilisable
    sys.modules["api.routes.shared"] = m
    sys.modules.setdefault("api", types.ModuleType("api"))
    sys.modules.setdefault("api.routes", types.ModuleType("api.routes"))
    if "api.server" not in sys.modules:
        faux_api_server()


class _Requete:
    def __init__(self, corps):
        self._corps = corps

    async def json(self):
        return self._corps


def aujourdhui(heure="18:30"):
    return _a0_jour() + "T" + heure + ":00"


def _a0_jour(decalage=0):
    return (datetime.now(TZ_CH) + timedelta(days=decalage)).strftime("%Y-%m-%d")


def resa(code="AF0000001", **kw):
    d = {"id": "id-" + code, "reservationCode": code, "userName": "Marie",
         "userEmail": "marie@test.ch", "courseId": "cours-1",
         "courseName": "Silent Mercredi", "datetime": aujourdhui(),
         "validated": False, "discountCode": "AFR-ESSAI1",
         "coach_id": COACH_TEST}
    d.update(kw)
    return d


def cours(**kw):
    """Un cours du catalogue. `weekday` est en convention JAVASCRIPT (Dim=0),
    comme en base — c'est tout l'objet d'A1."""
    d = {"id": "cours-1", "name": "Silent Mercredi", "weekday": 3, "time": "18:30",
         "visible": True, "archived": False, "coach_id": COACH_TEST}
    d.update(kw)
    return d


def forfait(**kw):
    d = {"id": "sub-1", "code": "AFR-ESSAI1", "email": "marie@test.ch",
         "name": "Marie", "remaining_sessions": 0, "total_sessions": 1,
         "used_sessions": 1, "status": "active"}
    d.update(kw)
    return d


async def scanner(ns, code, **corps):
    c = {"code": code}
    c.update(corps)
    return await ns["_qr_scan_validate_inner"](_Requete(c))




def construire_routes(db, coach="admin@test", admins=("admin@test",)):
    """Namespace incluant les DEUX routes soeurs de validation, extraites elles
    aussi du vrai fichier. `coach=""` simule un appelant anonyme."""
    faux_api_server(coach)
    ns = construire(db)
    ns["is_super_admin"] = lambda e: (e or "").lower().strip() in [a.lower() for a in admins]
    for nom in ("validate_reservation", "staff_validate_reservation"):
        exec(compile(extraire(nom), FICHIER, "exec"), ns)
    return ns
