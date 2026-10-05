#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V575 — CONTACTS : « Supprimer » renvoyait « Method Not Allowed » (405).

CAUSE
==============================================================================
Le bouton « Supprimer » de Contacts (`ContactsManager.deleteSelected`) envoie
`POST /api/contacts/bulk-delete`. Cette route (V146b) a été RETIRÉE par
`c245cd08` (v162) sans que l'écran soit modifié. Le seul `/{full_path:path}`
encore capable de « reconnaître » ce chemin est le catch-all SPA, déclaré en
GET : Starlette répond donc 405 au POST (chemin trouvé, méthode refusée).

CE QUE CE FICHIER PROUVE
==============================================================================
  R. La route POST existe dans l'application réelle (plus de 405).
  1. Anonyme / X-User-Email seul / jeton abonné -> 403, rien n'est touché.
  2. Coach A supprime SA fiche -> corbeille (restaurable), fiche retirée.
  3. Coach A ne supprime JAMAIS une fiche de B, ni une fiche sans propriétaire
     (ignorées, sans révéler leur existence).
  4. Suppression MULTIPLE : seules les fiches de A partent.
  5. Les inscriptions `users` (comptes plateforme) ne sont jamais effacées,
     même par le super-admin (la corbeille ne sait pas les restaurer).
  6. Profil système (adresse super-admin, propre fiche de l'appelant) protégé.
  7. Aucune donnée d'abonnement touchée (discount_codes, subscriptions,
     memberships, reservations), messages conservés, aucun accès Google.
  8. Super-admin : portée globale sur les fiches CRM.
  9. Entrées invalides -> 400 ; restauration depuis la corbeille OK.

Base Mongo EN MÉMOIRE, VRAI JWT HS256 de banc, aucun réseau.

    python3 tests/test_v575_contacts_bulk_delete.py
"""
import asyncio
import copy
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

SECRET = "secret-de-banc-v575-sans-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ["MONGO_URL"] = "mongodb://bouchon-inexistant-v575:27017"

import jwt as pyjwt  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from starlette.routing import Match  # noqa: E402

import api.server as S  # noqa: E402
from api.routes.shared import SUPER_ADMIN_EMAILS  # noqa: E402

RESULTATS = []


def verifier(intitule, condition, detail=""):
    RESULTATS.append((intitule, bool(condition)))
    print("  %-6s %s" % ("OK  " if condition else "ECHEC", intitule))
    if detail and not condition:
        print("           -> %s" % (detail,))


# ============================================================================
# BASE EN MÉMOIRE (sous-ensemble des opérateurs employés par ces routes)
# ============================================================================
_ABSENT = object()


def _val(doc, cle):
    cur = doc
    for p in cle.split("."):
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return _ABSENT
    return cur


def _egal(v, a):
    if v is _ABSENT:
        return a is None
    if isinstance(v, list) and not isinstance(a, list):
        return a in v
    return v == a


def correspond(doc, filtre):
    for cle, att in (filtre or {}).items():
        if cle == "$or":
            if not any(correspond(doc, f) for f in att):
                return False
            continue
        v = _val(doc, cle)
        if isinstance(att, dict) and any(k.startswith("$") for k in att):
            for op, arg in att.items():
                if op == "$in" and not any(_egal(v, x) for x in arg):
                    return False
                if op == "$nin" and any(_egal(v, x) for x in arg):
                    return False
                if op == "$ne" and _egal(v, arg):
                    return False
                if op not in ("$in", "$nin", "$ne"):
                    raise AssertionError("opérateur non géré : %s" % op)
        elif not _egal(v, att):
            return False
    return True


def projeter(doc, proj):
    d = copy.deepcopy(doc)
    d.pop("_id", None)
    inclus = [k for k, v in (proj or {}).items() if v and k != "_id"]
    return {k: d[k] for k in inclus if k in d} if inclus else d


class Res:
    def __init__(self, matched=0, modified=0, deleted=0):
        self.matched_count, self.modified_count, self.deleted_count = matched, modified, deleted
        self.inserted_id = None


class Curseur:
    def __init__(self, docs):
        self._d = list(docs)

    def sort(self, *a, **k):
        return self

    async def to_list(self, n=None):
        return self._d[:n] if n else self._d

    def __aiter__(self):
        self._it = iter(self._d)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class Coll:
    def __init__(self):
        self.docs = []

    def find(self, f=None, proj=None, *a, **k):
        return Curseur([projeter(d, proj) for d in self.docs if correspond(d, f)])

    async def find_one(self, f=None, proj=None, *a, **k):
        for d in self.docs:
            if correspond(d, f):
                return projeter(d, proj)
        return None

    async def insert_one(self, doc, **k):
        doc["_id"] = "oid-%d" % (len(self.docs) + 1)
        self.docs.append(copy.deepcopy(doc))
        return Res()

    async def count_documents(self, f=None, **k):
        return sum(1 for d in self.docs if correspond(d, f))

    async def update_many(self, f, maj, **k):
        m = n = 0
        for d in self.docs:
            if correspond(d, f):
                m += 1
                for champ, v in (maj.get("$pull") or {}).items():
                    avant = list(d.get(champ) or [])
                    if isinstance(v, dict) and "$in" in v:
                        d[champ] = [x for x in avant if x not in v["$in"]]
                    else:
                        d[champ] = [x for x in avant if x != v]
                    n += int(d[champ] != avant)
                for champ, v in (maj.get("$addToSet") or {}).items():
                    if v not in (d.get(champ) or []):
                        d.setdefault(champ, []).append(v)
                        n += 1
        return Res(m, n)

    async def update_one(self, f, maj, **k):
        for d in self.docs:
            if correspond(d, f):
                tmp = Coll()
                tmp.docs = [d]
                await tmp.update_many({}, maj)
                return Res(1, 1)
        return Res()

    async def delete_one(self, f, **k):
        for i, d in enumerate(self.docs):
            if correspond(d, f):
                del self.docs[i]
                return Res(deleted=1)
        return Res()

    async def delete_many(self, f, **k):
        avant = len(self.docs)
        self.docs = [d for d in self.docs if not correspond(d, f)]
        return Res(deleted=avant - len(self.docs))


class Base:
    def __init__(self):
        self._c = {}

    def __getitem__(self, nom):
        return self._c.setdefault(nom, Coll())

    def __getattr__(self, nom):
        if nom.startswith("_"):
            raise AttributeError(nom)
        return self[nom]


# ============================================================================
# IDENTITÉS / REQUÊTES
# ============================================================================
ADMIN = SUPER_ADMIN_EMAILS[0]
A = "coach.a.v575@exemple.test"
B = "coach.b.v575@exemple.test"


def jeton(email, type_=None):
    charge = {"email": email, "exp": int((datetime.now(timezone.utc) + timedelta(minutes=30)).timestamp())}
    if type_:
        charge["type"] = type_
    j = pyjwt.encode(charge, SECRET, algorithm="HS256")
    return j.decode("utf-8") if isinstance(j, bytes) else j


class Entetes(dict):
    def get(self, k, d=None):
        for kk, v in self.items():
            if kk.lower() == k.lower():
                return v
        return d


class Req:
    def __init__(self, qui=None, entete=None, corps=None, type_=None):
        self.headers = Entetes()
        if qui:
            self.headers["Authorization"] = "Bearer " + jeton(qui, type_)
        if entete:
            self.headers["X-User-Email"] = entete
        self._corps = corps if corps is not None else {}
        self.query_params = {}
        self.cookies = {}

    async def json(self):
        if isinstance(self._corps, Exception):
            raise self._corps
        return self._corps


def appel(coro_fn):
    try:
        return asyncio.run(coro_fn()), 200
    except HTTPException as e:
        return e.detail, e.status_code
    except Exception as e:  # noqa: BLE001
        return "500 %s: %s" % (type(e).__name__, e), 500


def base_neuve():
    db = Base()
    db.coaches.docs += [{"email": A}, {"email": B}]
    db.chat_participants.docs += [
        {"id": "pA1", "coach_id": A, "name": "Alice chez A", "email": "alice@x.test", "source": "google_contacts"},
        {"id": "pA2", "coach_id": A, "name": "Arnaud chez A", "email": "arnaud@x.test", "source": "chat"},
        {"id": "pAself", "coach_id": A, "name": "Moi-même", "email": A},
        {"id": "pAadmin", "coach_id": A, "name": "Bassi", "email": ADMIN},
        {"id": "pB1", "coach_id": B, "name": "Bob chez B", "email": "bob@x.test"},
        {"id": "pLegacy", "name": "Historique", "email": "legacy@x.test"},
    ]
    db.users.docs += [{"id": "uA", "coach_id": A, "name": "Inscrit", "email": "alice@x.test"}]
    db.chat_sessions.docs += [{"id": "s1", "coach_id": A, "participant_ids": ["pA1", "pA2", "pB1"]}]
    db.chat_messages.docs += [{"id": "m1", "session_id": "s1", "sender_id": "pA1", "content": "Bonjour"}]
    db.discount_codes.docs += [{"id": "dc1", "code": "ALICE-1", "assignedEmail": "alice@x.test", "maxUses": 10, "used": 3}]
    db.subscriptions.docs += [{"id": "sub1", "code": "ALICE-1", "email": "alice@x.test", "total_sessions": 10}]
    db.memberships.docs += [{"id": "mb1", "email": "alice@x.test", "source": "achat"}]
    db.reservations.docs += [{"id": "r1", "userEmail": "alice@x.test", "promoCode": "ALICE-1"}]
    db.google_tokens.docs += [{"coach_email": A, "access_token": "x"}]
    S.db = db
    return db


def ids(coll):
    return sorted(d.get("id") for d in coll.docs)


def supprimer(req):
    fn = getattr(S, "bulk_delete_contacts", None)
    if fn is None:
        return {"erreur": "route absente"}, 405
    return appel(lambda: fn(req))


# ============================================================================
# R. LA ROUTE EXISTE (reproduction exacte du 405)
# ============================================================================
print("\nR. Reproduction du 405")
scope = {"type": "http", "path": "/api/contacts/bulk-delete", "method": "POST",
         "root_path": "", "query_string": b"", "headers": []}
matchs = [r.matches(scope)[0] for r in S.fastapi_app.router.routes if hasattr(r, "matches")]
verifier("R1. POST /api/contacts/bulk-delete trouve une route POST (pas de 405)",
         Match.FULL in matchs,
         "aucune route POST : seul un catch-all GET correspond -> 405 Method Not Allowed")

# ============================================================================
# 1. AUTHENTIFICATION
# ============================================================================
print("\n1. Authentification")
for nom, req in [("anonyme", Req(corps={"ids": ["pA1"]})),
                 ("X-User-Email A sans JWT", Req(entete=A, corps={"ids": ["pA1"]})),
                 ("jeton abonné", Req(qui=A, type_="subscriber", corps={"ids": ["pA1"]})),
                 ("JWT d'un inconnu (non coach)", Req(qui="inconnu@x.test", corps={"ids": ["pA1"]}))]:
    db = base_neuve()
    _, c = supprimer(req)
    verifier("1. %s -> 403, rien supprimé" % nom, c == 403 and "pA1" in ids(db.chat_participants), c)

# ============================================================================
# 2-4. SUPPRESSION UNIQUE / ISOLATION / MULTIPLE
# ============================================================================
print("\n2. Suppression unique par le coach propriétaire")
db = base_neuve()
r, c = supprimer(Req(qui=A, corps={"ids": ["pA1"]}))
verifier("2a. 200 + deleted == 1", c == 200 and isinstance(r, dict) and r.get("deleted") == 1, (c, r))
verifier("2b. fiche retirée de chat_participants", "pA1" not in ids(db.chat_participants))
_corb = [d for d in db.deleted_items.docs if d.get("original_id") == "pA1"]
verifier("2c. fiche placée en CORBEILLE (payload complet, coach_id, deleted_by)",
         len(_corb) == 1 and _corb[0]["payload"].get("name") == "Alice chez A"
         and _corb[0].get("coach_id") == A and _corb[0].get("deleted_by") == A
         and _corb[0].get("original_collection") == "chat_participants", _corb)
verifier("2d. session : participant retiré, les autres conservés",
         db.chat_sessions.docs[0]["participant_ids"] == ["pA2", "pB1"], db.chat_sessions.docs[0])
verifier("2e. messages CONSERVÉS", ids(db.chat_messages) == ["m1"])

print("\n3. Isolation coach")
db = base_neuve()
r, c = supprimer(Req(qui=A, corps={"ids": ["pB1"]}))
verifier("3a. A -> fiche de B : rien supprimé", c == 200 and r.get("deleted") == 0
         and "pB1" in ids(db.chat_participants), (c, r))
verifier("3b. réponse identique à un id inexistant (aucun oracle d'existence)",
         r.get("ignored") == supprimer(Req(qui=A, corps={"ids": ["n-existe-pas"]}))[0].get("ignored"))
db = base_neuve()
r, c = supprimer(Req(qui=A, corps={"ids": ["pLegacy"]}))
verifier("3c. A -> fiche sans propriétaire : refusée", r.get("deleted") == 0 and "pLegacy" in ids(db.chat_participants), r)
db = base_neuve()
r, c = supprimer(Req(qui=B, entete=A, corps={"ids": ["pA1"]}))
verifier("3d. JWT B + X-User-Email A : agit comme B (fiche de A intacte)",
         r.get("deleted") == 0 and "pA1" in ids(db.chat_participants), r)

print("\n4. Suppression multiple")
db = base_neuve()
r, c = supprimer(Req(qui=A, corps={"ids": ["pA1", "pA2", "pB1", "pLegacy", "uA", "community", "pA1"]}))
verifier("4a. seules pA1 + pA2 supprimées (doublon d'id compté une fois)",
         c == 200 and r.get("deleted") == 2 and ids(db.chat_participants) == ["pAadmin", "pAself", "pB1", "pLegacy"], (c, r))
verifier("4b. requested / ignored cohérents", r.get("requested") == 6 and r.get("ignored") == 4, r)
verifier("4c. deux entrées de corbeille", len(db.deleted_items.docs) == 2)

# ============================================================================
# 5-7. CE QUI N'EST JAMAIS TOUCHÉ
# ============================================================================
print("\n5. Inscriptions `users`")
for qui in (A, ADMIN):
    db = base_neuve()
    r, c = supprimer(Req(qui=qui, corps={"ids": ["uA"]}))
    verifier("5. %s -> inscription users jamais effacée" % ("coach" if qui == A else "super-admin"),
             c == 200 and r.get("deleted") == 0 and ids(db.users) == ["uA"], (c, r))

print("\n6. Profils système")
db = base_neuve()
r, c = supprimer(Req(qui=A, corps={"ids": ["pAself", "pAadmin"]}))
verifier("6. propre fiche + fiche à l'adresse super-admin protégées",
         r.get("deleted") == 0 and {"pAself", "pAadmin"} <= set(ids(db.chat_participants)), r)

print("\n7. Abonnements, réservations, Google")
db = base_neuve()
avant = {k: copy.deepcopy(db[k].docs) for k in ("discount_codes", "subscriptions", "memberships",
                                                 "reservations", "google_tokens", "chat_messages", "users")}
supprimer(Req(qui=A, corps={"ids": ["pA1", "pA2"]}))
for k, v in avant.items():
    verifier("7. %s strictement inchangé" % k, db[k].docs == v)

# ============================================================================
# 8-9. SUPER-ADMIN, ENTRÉES, RESTAURATION
# ============================================================================
print("\n8. Super-admin")
db = base_neuve()
r, c = supprimer(Req(qui=ADMIN, corps={"ids": ["pB1", "pLegacy"]}))
verifier("8. super-admin : fiche de B + fiche historique supprimées (corbeille)",
         r.get("deleted") == 2 and "pB1" not in ids(db.chat_participants)
         and len(db.deleted_items.docs) == 2, r)

print("\n9. Entrées invalides et restauration")
for nom, corps in [("ids absent", {}), ("ids non-liste", {"ids": "pA1"}), ("liste vide", {"ids": []}),
                   ("plus de 200 ids", {"ids": ["x%d" % i for i in range(201)]}),
                   ("corps illisible", ValueError("json"))]:
    db = base_neuve()
    _, c = supprimer(Req(qui=A, corps=corps))
    verifier("9. %s -> 400" % nom, c == 400 and len(ids(db.chat_participants)) == 6, c)
db = base_neuve()
r, c = supprimer(Req(qui=A, corps={"ids": [{"$ne": None}, "pA1$"]}))
verifier("9. opérateurs Mongo / '$' dans un id : ignorés", c == 200 and r.get("deleted") == 0
         and len(ids(db.chat_participants)) == 6, (c, r))
db = base_neuve()
supprimer(Req(qui=A, corps={"ids": ["pA1"]}))
_tid = db.deleted_items.docs[0]["id"]
r, c = appel(lambda: S.restore_trash(_tid, Req(qui=A)))
verifier("9. restauration depuis la corbeille : fiche et session rétablies",
         c == 200 and "pA1" in ids(db.chat_participants)
         and "pA1" in db.chat_sessions.docs[0]["participant_ids"], (c, r))

# ============================================================================
ok = sum(1 for _, b in RESULTATS if b)
print("\n%d / %d vérifications V575 au vert" % (ok, len(RESULTATS)))
sys.exit(0 if ok == len(RESULTATS) else 1)
