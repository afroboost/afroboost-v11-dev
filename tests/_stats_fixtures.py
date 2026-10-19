# -*- coding: utf-8 -*-
"""STATS-1 — outils des bancs `/api/stats/association`. NE FAIT RIEN À L'IMPORT.

Données SYNTHÉTIQUES (adresses en `.invalid`), fausse base Mongo en mémoire,
horloge figée, et chargement de la VERSION DE RÉFÉRENCE du moteur (commit
8baf9b13, avant l'extraction du cœur) directement depuis git — pour comparer
la sortie de l'écran coach avant / après, valeur pour valeur.

AUCUNE BASE RÉELLE, AUCUN RÉSEAU.
"""
import asyncio
import importlib.util
import os
import subprocess
import sys
import types
from datetime import datetime, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)

COMMIT_REFERENCE = "8baf9b13"
COACH = "coach@exemple.invalid"
AUTRE = "autre@exemple.invalid"
ADMIN = "admin@exemple.invalid"

# 15 octobre 2026, 12:00 UTC = 14:00 à Zurich (heure d'été jusqu'au 25/10).
MAINTENANT_UTC = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)


def horloge_figee(module, instant=MAINTENANT_UTC):
    """Remplace `datetime` du module par une sous-classe dont `now()` est figé."""
    class _DT(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant if tz is not None else instant.replace(tzinfo=None)
    module.datetime = _DT


# ─────────────────────────────── jeu de données ────────────────────────────

def resa(id_, email, occ, cree, course_id="c-mer", course_name="Silent", coach=COACH, **kw):
    d = {"id": id_, "userEmail": email, "userName": "P " + id_, "courseId": course_id,
         "courseName": course_name, "datetime": occ, "createdAt": cree, "coach_id": coach,
         "validated": False, "isProduct": False, "quantity": 1, "price": 30.0,
         "promoCode": None, "discountCode": None, "source": "subscriber_space"}
    d.update(kw)
    return d


def jeu_de_base():
    """Un mois de septembre et d'août « ordinaires » — AUCUN piège (ni tarif
    progressif, ni abonnement supprimé) : la référence et le code extrait
    doivent y rendre exactement la même chose."""
    reservations = [
        resa("r1", "anna@mail.invalid", "2026-09-09T18:30:00", "2026-09-09T10:00:00+00:00", quantity=2),
        resa("r2", "anna@mail.invalid", "2026-09-13T18:30:00", "2026-09-12T20:00:00+00:00", "c-dim", "Sunday"),
        resa("r3", "bob@mail.invalid", "2026-09-13T18:30:00", "2026-09-10T08:00:00+00:00", "c-dim", "Sunday",
             validated=True, discountCode="AFR-PUL001"),
        resa("r4", "carl@mail.invalid", "2026-09-09T18:30:00", "2026-09-03T08:00:00+00:00", absence_marked_at="x"),
        resa("r5", "dora@mail.invalid", "2026-09-16T18:30:00", "2026-08-30T08:00:00+00:00", quantity=3),
        resa("r6", "anna@mail.invalid", "2026-08-05T18:30:00", "2026-08-01T08:00:00+00:00"),
        resa("r7", "eve@mail.invalid", "2026-09-09T18:30:00", "2026-09-08T08:00:00+00:00",
             discountCode="AFR-ESS001", validated=True),
        resa("r8", "", "2026-09-16T18:30:00", "2026-09-08T08:00:00+00:00"),
        resa("p1", "shop@mail.invalid", "2026-09-10T00:00:00", "2026-09-10T08:00:00+00:00", "", "", isProduct=True),
        resa("x1", "autre@mail.invalid", "2026-09-09T18:30:00", "2026-09-08T08:00:00+00:00", coach=AUTRE),
        resa("r9", "fred@mail.invalid", "2026-10-07T18:30:00", "2026-10-01T08:00:00+00:00"),
    ]
    cours = [{"id": "c-mer", "name": "Silent", "weekday": 3, "locationName": "Lac"},
             {"id": "c-dim", "name": "Sunday", "weekday": 0, "locationName": "Lac"}]
    offres = [
        {"id": "o-pulse", "name": "PULSE x10 cours", "price": 250, "pack_sessions": 10},
        {"id": "o-essai", "name": "Cours d'essai GRATUIT", "price": 0},
        {"id": "o-unite", "name": "Cours à l'unité", "price": 30},
    ]
    souscriptions = [
        {"id": "s1", "code": "AFR-PUL001", "email": "bob@mail.invalid", "coach_id": COACH, "offer_id": "o-pulse",
         "offer_name": "PULSE x10 cours", "status": "active", "created_at": "2026-09-02T09:00:00+00:00",
         "expires_at": "2027-03-01T00:00:00+00:00", "origine_paiement": "twint", "montant_encaisse": 250,
         "total_sessions": 10, "remaining_sessions": 9},
        {"id": "s2", "code": "AFR-ESS001", "email": "eve@mail.invalid", "coach_id": COACH, "offer_id": "o-essai",
         "offer_name": "Cours d'essai GRATUIT", "status": "completed", "created_at": "2026-09-05T09:00:00+00:00",
         "expires_at": "2026-10-05T00:00:00+00:00", "total_sessions": 1, "remaining_sessions": 0},
        {"id": "s3", "code": "AFR-UNI001", "email": "gina@mail.invalid", "coach_id": COACH, "offer_id": "o-unite",
         "offer_name": "Cours à l'unité", "status": "active", "created_at": "2026-08-20T09:00:00+00:00",
         "expires_at": "2026-12-01T00:00:00+00:00", "origine_paiement": "especes", "montant_encaisse": 30,
         "total_sessions": 1, "remaining_sessions": 1},
    ]
    fiches = [
        {"code": "AFR-ESS001", "payment_method": "free", "total_paid": 0, "coach_id": COACH, "active": False},
        {"code": "AFR-PUL001", "coach_id": COACH, "active": True},
    ]
    cartes = [{"email": "bob@mail.invalid", "date_debut": "2026-09-02T00:00:00+00:00",
               "date_fin": "2027-09-02T00:00:00+00:00", "source": "achat", "coach_id": COACH}]
    paiements = [
        {"id": "t1", "session_id": "cs_test_aaa", "amount_total": 4500, "payment_status": "paid",
         "product_name": "Billet", "customer_email": "hugo@mail.invalid", "created_at": "2026-09-20T10:00:00+00:00",
         "coach_id": COACH, "payment_method": "card"},
        {"id": "t2", "session_id": "cs_test_bbb", "amount_total": 3000, "payment_status": "pending",
         "created_at": "2026-09-21T10:00:00+00:00", "coach_id": COACH},
    ]
    return {"reservations": reservations, "courses": cours, "offers": offres, "subscriptions": souscriptions,
            "discount_codes": fiches, "memberships": cartes, "payment_transactions": paiements,
            "concept": [{"coach_id": COACH, "appName": "Studio Test"}], "analytics_monthly_reports": []}


# ─────────────────────────────── fausse base ───────────────────────────────

def correspond(doc, filtre):
    for k, v in (filtre or {}).items():
        if k == "$or":
            if not any(correspond(doc, alt) for alt in v):
                return False
            continue
        val = doc.get(k)
        if isinstance(v, dict) and any(str(op).startswith("$") for op in v):
            for op, arg in v.items():
                if op == "$in" and val not in arg:
                    return False
                if op == "$nin" and val in arg:
                    return False
                if op == "$ne" and val == arg:
                    return False
                if op == "$exists" and (k in doc) != bool(arg):
                    return False
        elif val != v:
            return False
    return True


def projeter(doc, proj):
    if not proj:
        return dict(doc)
    _inc = {k for k, v in proj.items() if v and k != "_id"}
    _exc = {k for k, v in proj.items() if not v}
    if _inc:
        return {k: v for k, v in doc.items() if k in _inc}
    return {k: v for k, v in doc.items() if k not in _exc}


class Curseur:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, n):
        return [dict(d) for d in self.docs[:n]]


class Collection:
    def __init__(self, nom, docs, base):
        self.nom, self.docs, self.base = nom, docs, base

    def find(self, filtre=None, proj=None):
        self.base.lectures.append(self.nom)
        if self.base.panne:
            raise RuntimeError("base injoignable (simulée)")
        return Curseur([projeter(d, proj) for d in self.docs if correspond(d, filtre)])

    async def find_one(self, filtre=None, proj=None):
        self.base.lectures.append(self.nom)
        if self.base.panne:
            raise RuntimeError("base injoignable (simulée)")
        for d in self.docs:
            if correspond(d, filtre):
                return projeter(d, proj)
        return None

    def __getattr__(self, nom):
        # Toute méthode d'écriture est un DÉFAUT : la route est en lecture seule.
        if nom in ("insert_one", "insert_many", "update_one", "update_many", "replace_one",
                   "delete_one", "delete_many", "find_one_and_update", "create_index", "bulk_write"):
            def _interdit(*a, **k):
                self.base.ecritures.append((self.nom, nom))
                raise AssertionError("écriture interdite : %s.%s" % (self.nom, nom))
            return _interdit
        raise AttributeError(nom)


class Base:
    def __init__(self, jeu):
        self.lectures, self.ecritures, self.panne = [], [], False
        self._c = {k: Collection(k, list(v), self) for k, v in jeu.items()}

    def __getattr__(self, nom):
        if nom.startswith("_"):
            raise AttributeError(nom)
        return self._c.setdefault(nom, Collection(nom, [], self))

    def __getitem__(self, nom):
        return getattr(self, nom)


def occurrence_iso(v):
    from api.routes import analytics_shared as A
    _d = A.parser_local(v)
    return _d.strftime("%Y-%m-%dT%H:%M:%S") if _d else ""


def installer_serveur(base, jwt_email=""):
    """`api.server` de substitution : db + gardes JWT ; `reservation_routes` minimal."""
    m = types.ModuleType("api.server")
    m.db = base
    m._v311_coach_email_from_jwt = lambda request: jwt_email
    async def _est_coach(email):
        return email in (COACH, AUTRE, ADMIN)
    m._v309_is_coach_or_admin = _est_coach
    sys.modules["api.server"] = m
    rr = types.ModuleType("api.routes.reservation_routes")
    rr.lot1_occurrence_iso = occurrence_iso
    sys.modules["api.routes.reservation_routes"] = rr


def poser_admin():
    import api.routes.shared as _shared
    _shared.is_super_admin = lambda e: (e or "").lower() == ADMIN
    import api.routes.analytics_routes as _ar
    _ar.is_super_admin = _shared.is_super_admin


# ─────────────────────── la version de référence (git) ─────────────────────

def charger_reference():
    """Les modules `shared`, `analytics_shared`, `analytics_routes` TELS QU'AU
    commit de référence, chargés sous d'autres noms. None si git est muet."""
    noms = {"shared": "api.routes._ref_shared",
            "analytics_shared": "api.routes._ref_analytics_shared",
            "analytics_routes": "api.routes._ref_analytics_routes"}
    mods = {}
    for court in ("shared", "analytics_shared", "analytics_routes"):
        try:
            src = subprocess.check_output(["git", "-C", RACINE, "show", "%s:api/routes/%s.py" % (COMMIT_REFERENCE, court)],
                                          stderr=subprocess.DEVNULL).decode("utf-8")
        except Exception:
            return None
        for a, b in noms.items():
            src = src.replace("from api.routes.%s import" % a, "from %s import" % b)
        mod = types.ModuleType(noms[court])
        mod.__file__ = "<%s@%s>" % (court, COMMIT_REFERENCE)
        sys.modules[noms[court]] = mod
        exec(compile(src, mod.__file__, "exec"), mod.__dict__)
        mods[court] = mod
    mods["shared"].is_super_admin = lambda e: (e or "").lower() == ADMIN
    mods["analytics_routes"].is_super_admin = mods["shared"].is_super_admin
    return mods


class Req:
    def __init__(self, headers=None, ip="203.0.113.7"):
        self.headers = headers or {}
        self.client = types.SimpleNamespace(host=ip)


def run(coro):
    return asyncio.run(coro)
