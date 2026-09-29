#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MT-2 — CONTACTS / USERS / CATÉGORIES : cloisonnement multi-coach.

CE QUE CE FICHIER PROUVE
==============================================================================
Pour chaque route Contacts corrigée par MT-2, la matrice :
  A lit A 200 · A lit B 404/403 · B lit A 404/403 · A modifie A OK ·
  A modifie B 404/403 · A supprime B 404/403 · anonyme 401/403 ·
  X-User-Email A sans JWT 401/403 · JWT B + X-User-Email A -> reste B ·
  super-admin global (LES DEUX super-admins) · chemins visiteurs toujours OK ·
  regex (caractères spéciaux) · dédoublonnage par coach · users globaux
  visibles seulement si relation prouvée · space-link inter-coach 404.

COMMENT
==============================================================================
Une base Mongo EN MÉMOIRE (`BaseFictive`), assez riche pour les opérateurs que
ces routes emploient ($or/$and/$in/$regex/$exists/$ne/$all/$size, $set/$unset/
$addToSet/$pull/$pullAll/$inc, skip/limit/sort). Les requêtes portent un VRAI
JWT HS256 signé avec un secret de banc. Les fonctions de route sont appelées
directement (ce sont des coroutines FastAPI ordinaires).

AUCUNE base réelle, AUCUN réseau : `MONGO_URL` pointe vers un hôte inexistant
et n'est jamais ouvert (toutes les collections sont remplacées).

    python3 tests/test_mt2_contacts.py
"""
import asyncio
import copy
import os
import re
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

SECRET = "secret-de-banc-mt2-sans-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ["MONGO_URL"] = "mongodb://bouchon-inexistant-mt2:27017"

import jwt as pyjwt  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import api.server as S  # noqa: E402
from api.routes import contact_categories_routes as CAT  # noqa: E402
from api.routes import contact_segments_routes as SEG  # noqa: E402
from api.routes import tenant_contacts as TC  # noqa: E402
from api.routes.shared import SUPER_ADMIN_EMAILS  # noqa: E402

RESULTATS = []


def verifier(intitule, condition, detail=""):
    RESULTATS.append((intitule, bool(condition), detail))
    print("  %-6s %s" % ("OK  " if condition else "ECHEC", intitule))
    if detail and not condition:
        print("           -> %s" % (detail,))
    return bool(condition)


# ============================================================================
# 1. BASE MONGO EN MÉMOIRE
# ============================================================================
_ABSENT = object()


def _valeur(doc, cle):
    cur = doc
    for p in cle.split("."):
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return _ABSENT
    return cur


def _egal(v, attendu):
    if v is _ABSENT:
        return attendu is None
    if isinstance(v, list) and not isinstance(attendu, list):
        return attendu in v
    return v == attendu


def _op(v, op, arg):
    if op == "$in":
        return any(_egal(v, a) for a in arg)
    if op == "$nin":
        return not any(_egal(v, a) for a in arg)
    if op == "$ne":
        return not _egal(v, arg)
    if op == "$eq":
        return _egal(v, arg)
    if op == "$exists":
        return (v is not _ABSENT) == bool(arg)
    if op == "$all":
        return isinstance(v, list) and all(a in v for a in arg)
    if op == "$size":
        return isinstance(v, list) and len(v) == arg
    if op in ("$gt", "$gte", "$lt", "$lte"):
        if v is _ABSENT or v is None:
            return False
        try:
            return {"$gt": v > arg, "$gte": v >= arg, "$lt": v < arg, "$lte": v <= arg}[op]
        except TypeError:
            return False
    raise AssertionError("opérateur non géré par le banc : %s" % op)


def correspond(doc, filtre):
    for cle, attendu in (filtre or {}).items():
        if cle == "$or":
            if not any(correspond(doc, f) for f in attendu):
                return False
            continue
        if cle == "$and":
            if not all(correspond(doc, f) for f in attendu):
                return False
            continue
        if cle == "$nor":
            if any(correspond(doc, f) for f in attendu):
                return False
            continue
        v = _valeur(doc, cle)
        if isinstance(attendu, dict) and any(k.startswith("$") for k in attendu):
            if "$regex" in attendu:
                flags = re.I if "i" in (attendu.get("$options") or "") else 0
                motif = re.compile(attendu["$regex"], flags)  # lève comme Mongo sur motif invalide
                vals = v if isinstance(v, list) else [v]
                if not any(isinstance(x, str) and motif.search(x) for x in vals):
                    return False
            for op, arg in attendu.items():
                if op in ("$regex", "$options"):
                    continue
                if not _op(v, op, arg):
                    return False
        elif not _egal(v, attendu):
            return False
    return True


def projeter(doc, proj):
    d = copy.deepcopy(doc)
    d.pop("_id", None)
    if not proj:
        return d
    inclus = [k for k, v in proj.items() if v and k != "_id"]
    if inclus:
        return {k: d[k] for k in inclus if k in d}
    return {k: v for k, v in d.items() if proj.get(k, 1)}


class Resultat:
    def __init__(self, matched=0, modified=0, deleted=0, upserted_id=None):
        self.matched_count = matched
        self.modified_count = modified
        self.deleted_count = deleted
        self.upserted_id = upserted_id
        self.inserted_id = upserted_id


class Curseur:
    def __init__(self, docs):
        self._docs = list(docs)
        self._skip = 0
        self._limit = None

    def sort(self, cle, sens=1):
        specs = cle if isinstance(cle, list) else [(cle, sens)]
        for champ, s in reversed(specs):
            self._docs.sort(key=lambda d: str(d.get(champ) or ""), reverse=(s == -1))
        return self

    def skip(self, n):
        self._skip = n
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _tranche(self):
        d = self._docs[self._skip:]
        return d[:self._limit] if self._limit else d

    async def to_list(self, n=None):
        t = self._tranche()
        return t[:n] if n else t

    def __aiter__(self):
        self._it = iter(self._tranche())
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class Collection:
    def __init__(self, nom):
        self.nom = nom
        self.docs = []

    def find(self, filtre=None, proj=None, *a, **k):
        return Curseur([projeter(d, proj) for d in self.docs if correspond(d, filtre)])

    async def find_one(self, filtre=None, proj=None, *a, **k):
        for d in self.docs:
            if correspond(d, filtre):
                return projeter(d, proj)
        return None

    async def insert_one(self, doc):
        doc["_id"] = "oid-%d" % (len(self.docs) + 1)
        self.docs.append(copy.deepcopy(doc))
        return Resultat(upserted_id=doc["_id"])

    async def count_documents(self, filtre=None, *a, **k):
        return sum(1 for d in self.docs if correspond(d, filtre))

    def _appliquer(self, d, maj, insertion=False):
        avant = copy.deepcopy(d)
        for op, champs in maj.items():
            if op == "$set" or (op == "$setOnInsert" and insertion):
                for k, v in champs.items():
                    d[k] = copy.deepcopy(v)
            elif op == "$setOnInsert":
                continue
            elif op == "$unset":
                for k in champs:
                    d.pop(k, None)
            elif op == "$inc":
                for k, v in champs.items():
                    d[k] = (d.get(k) or 0) + v
            elif op == "$addToSet":
                for k, v in champs.items():
                    vals = v["$each"] if isinstance(v, dict) and "$each" in v else [v]
                    lst = list(d.get(k) or [])
                    for x in vals:
                        if x not in lst:
                            lst.append(x)
                    d[k] = lst
            elif op == "$push":
                for k, v in champs.items():
                    d.setdefault(k, []).append(v)
            elif op == "$pull":
                for k, v in champs.items():
                    d[k] = [x for x in (d.get(k) or []) if x != v]
            elif op == "$pullAll":
                for k, v in champs.items():
                    d[k] = [x for x in (d.get(k) or []) if x not in v]
            else:
                raise AssertionError("mise à jour non gérée par le banc : %s" % op)
        return d != avant

    async def update_one(self, filtre, maj, upsert=False, **k):
        for d in self.docs:
            if correspond(d, filtre):
                return Resultat(1, int(self._appliquer(d, maj)))
        if upsert:
            neuf = {k2: v for k2, v in (filtre or {}).items() if not k2.startswith("$")}
            self._appliquer(neuf, maj, insertion=True)
            await self.insert_one(neuf)
            return Resultat(0, 0, upserted_id=neuf["_id"])
        return Resultat(0, 0)

    async def update_many(self, filtre, maj, **k):
        m = n = 0
        for d in self.docs:
            if correspond(d, filtre):
                m += 1
                n += int(self._appliquer(d, maj))
        return Resultat(m, n)

    async def delete_one(self, filtre, **k):
        for i, d in enumerate(self.docs):
            if correspond(d, filtre):
                del self.docs[i]
                return Resultat(deleted=1)
        return Resultat(deleted=0)

    async def delete_many(self, filtre, **k):
        avant = len(self.docs)
        self.docs = [d for d in self.docs if not correspond(d, filtre)]
        return Resultat(deleted=avant - len(self.docs))

    def aggregate(self, *a, **k):
        return Curseur([])


class BaseFictive:
    def __init__(self):
        self._c = {}

    def __getitem__(self, nom):
        return self._c.setdefault(nom, Collection(nom))

    def __getattr__(self, nom):
        if nom.startswith("_"):
            raise AttributeError(nom)
        return self[nom]


# ============================================================================
# 2. IDENTITÉS ET REQUÊTES
# ============================================================================
ADMIN = SUPER_ADMIN_EMAILS[0]
# SA-1 : il n'existe plus qu'UN super-admin. L'ancien second compte
# (afroboost.bassi@gmail.com) est désormais vérifié comme NON super-admin :
# aucune vue globale, refus sur les routes réservées.
ANCIEN_SECOND = "afroboost.bassi@gmail.com"
assert SUPER_ADMIN_EMAILS == [ADMIN], SUPER_ADMIN_EMAILS
A = "coach.a.mt2@exemple.test"
B = "coach.b.mt2@exemple.test"


def jeton(email, type_=None):
    charge = {"email": email,
              "exp": int((datetime.now(timezone.utc) + timedelta(minutes=30)).timestamp())}
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
    def __init__(self, qui=None, entete=None, corps=None, type_=None, params=None):
        h = Entetes()
        if qui:
            h["Authorization"] = "Bearer " + jeton(qui, type_)
        if entete:
            h["X-User-Email"] = entete
        self.headers = h
        self.query_params = params or {}
        self._corps = corps if corps is not None else {}
        self.cookies = {}

        class _C:
            host = "127.0.0.1"
        self.client = _C()

    async def json(self):
        return self._corps


class Souple(dict):
    """Dictionnaire de RÉPONSE tolérant : une clé absente vaut None au lieu de
    lever. Sert la phase ROUGE (ancien code, réponses d'une autre forme) : la
    vérification échoue proprement au lieu d'arrêter le banc."""
    def __missing__(self, cle):
        return None


def _souple(o):
    if isinstance(o, dict):
        return Souple({k: _souple(v) for k, v in o.items()})
    if isinstance(o, list):
        return [_souple(x) for x in o]
    return o


def appel(fabrique):
    """(résultat, code HTTP). Une exception NON HTTP = une 500 (elle est
    comptée comme telle, pas masquée : aucun test n'accepte 500)."""
    try:
        return _souple(asyncio.run(fabrique())), 200
    except HTTPException as e:
        return e.detail, e.status_code
    except Exception as e:  # noqa: BLE001
        return "500 %s: %s" % (type(e).__name__, e), 500


def sur(fn, defaut=None):
    """Évalue `fn()` ; une exception (ancien code, signature absente) rend
    `defaut` — la vérification correspondante échoue au lieu d'arrêter le banc."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        print("           (exception : %s: %s)" % (type(e).__name__, e))
        return defaut


def refuse(code):
    return code in (401, 403)


def cache(code):
    return code in (403, 404)


# ============================================================================
# 3. JEU DE DONNÉES
# ============================================================================
def base_neuve():
    db = BaseFictive()
    db.coaches.docs += [{"email": A, "credits": 100}, {"email": B, "credits": 100}]
    db.chat_participants.docs += [
        {"id": "pA1", "coach_id": A, "name": "Alice chez A", "email": "alice@x.test",
         "whatsapp": "+41765112233", "tags": [], "created_at": "2026-01-01"},
        {"id": "pB1", "coach_id": B, "name": "Bob chez B", "email": "bob@x.test",
         "whatsapp": "0791234567", "tags": [], "created_at": "2026-01-01"},
        {"id": "pB2", "coach_id": B, "name": "Alice chez B", "email": "alice@x.test",
         "whatsapp": "", "tags": [], "created_at": "2026-01-02"},
        {"id": "pPlat", "coach_id": ADMIN, "name": "Plateforme", "email": "plat@x.test",
         "whatsapp": "+41780000001", "created_at": "2026-01-01"},
        {"id": "pLegacy", "name": "Historique", "email": "legacy@x.test", "created_at": "2025-01-01"},
    ]
    db.users.docs += [
        {"id": "uA", "coach_id": A, "name": "User de A", "email": "ua@x.test", "whatsapp": ""},
        {"id": "uRelA", "name": "Relié à A", "email": "rel@x.test", "whatsapp": ""},
        {"id": "uNone", "name": "Personne", "email": "none@x.test", "whatsapp": ""},
        {"id": "uRelB", "name": "Relié à B", "email": "relb@x.test", "whatsapp": ""},
        {"id": "uDcA", "name": "Code de A", "email": "dca@x.test", "whatsapp": ""},
    ]
    db.reservations.docs += [{"id": "r1", "coach_id": A, "userEmail": "rel@x.test"}]
    # MT-2b : preuves FORTES (nées d'un paiement de la personne) :
    #   rel@  -> adhésion ACHETÉE chez A ; relb@ -> abonnement Stripe chez B.
    db.memberships.docs += [{"id": "mA", "coach_id": A, "email": "rel@x.test", "source": "achat"}]
    db.subscriptions.docs += [
        {"id": "sB", "coach_id": B, "email": "relb@x.test", "status": "active", "code": "AFR-BBB111",
         "source": "stripe_auto"},
        {"id": "sA", "coach_id": A, "email": "suba@x.test", "status": "active", "code": "AFR-AAA111"},
    ]
    db.discount_codes.docs += [
        {"id": "dA", "coach_id": A, "assignedEmail": "dca@x.test", "active": True, "code": "AFR-DCA111"},
    ]
    db.chat_sessions.docs += [
        {"id": "sessA", "coach_id": A, "title": "Groupe de A", "mode": "group", "participant_ids": ["pA1"]},
        {"id": "sessB", "coach_id": B, "title": "Groupe de B", "mode": "group", "participant_ids": ["pB1"]},
    ]
    db.leads.docs += [
        {"id": "lA", "coach_id": A, "firstName": "LeadA", "email": "la@x.test", "whatsapp": "+41761110001"},
        {"id": "lB", "coach_id": B, "firstName": "LeadB", "email": "lb@x.test", "whatsapp": "+41761110002"},
        {"id": "lSansMail", "coach_id": ADMIN, "firstName": "SansMail", "email": "", "whatsapp": "+41761110003"},
    ]
    db.contact_categories.docs += [
        {"id": "cA", "coach_id": A, "name": "Cat A", "color": "#111111", "icon": "x", "order": 1},
        {"id": "cB", "coach_id": B, "name": "Cat B", "color": "#222222", "icon": "x", "order": 1},
        {"id": "cPlat", "coach_id": CAT.SUPER_ADMIN_EMAIL, "name": "Cat Plateforme",
         "color": "#333333", "icon": "x", "order": 1},
    ]
    S.db = db
    CAT.db = db
    SEG.db = db
    return db


def par(db, coll, champ, val):
    """Premier document de `coll` où `champ == val`, ou {} (jamais d'IndexError)."""
    for d in db[coll].docs:
        if d.get(champ) == val:
            return d
    return {}


def doc(db, coll, id_):
    for d in db[coll].docs:
        if d.get("id") == id_:
            return Souple(d)
    return None


# ============================================================================
# 4. LES TESTS
# ============================================================================
print("\n== 1. GET /chat/participants (liste) ==")
db = base_neuve()
r, c = appel(lambda: S.get_chat_participants(Req(A)))
verifier("A lit sa liste : 200", c == 200)
ids = {p["id"] for p in r} if c == 200 else set()
verifier("A ne voit que ses fiches", ids == {"pA1"}, ids)
r, c = appel(lambda: S.get_chat_participants(Req(B)))
verifier("B ne voit pas les fiches de A", c == 200 and "pA1" not in {p["id"] for p in r})
r, c = appel(lambda: S.get_chat_participants(Req()))
verifier("anonyme -> 401/403", refuse(c), c)
r, c = appel(lambda: S.get_chat_participants(Req(entete=ADMIN)))
verifier("X-User-Email super-admin SANS JWT -> 403 (P0 fermé)", refuse(c), c)
r, c = appel(lambda: S.get_chat_participants(Req(entete=A)))
verifier("X-User-Email A sans JWT -> 403", refuse(c), c)
r, c = appel(lambda: S.get_chat_participants(Req(B, entete=A)))
verifier("JWT B + X-User-Email A -> reste B", c == 200 and {p["id"] for p in r} == {"pB1", "pB2"},
         [p["id"] for p in r] if c == 200 else c)
r, c = appel(lambda: S.get_chat_participants(Req(ADMIN)))
verifier("super-admin : vue globale (5 fiches)", c == 200 and len(r) == 5, len(r) if c == 200 else c)
r, c = appel(lambda: S.get_chat_participants(Req(ANCIEN_SECOND)))
verifier("SA-1 : ancien second super-admin -> PAS de vue globale (refus)", refuse(c), c)
r, c = appel(lambda: S.get_chat_participants(Req(ADMIN), limit=2, skip=1))
verifier("pagination optionnelle limit/skip", c == 200 and len(r) == 2)
r, c = appel(lambda: S.get_chat_participants(Req(A, type_="subscriber")))
verifier("jeton ABONNÉ -> 403 (pas un coach)", refuse(c), c)
r, c = appel(lambda: S.get_chat_participants(Req("inconnu@x.test")))
verifier("JWT signé d'un non-coach -> 403", refuse(c), c)

print("\n== 2. GET /chat/participants/{id} ==")
r, c = appel(lambda: S.get_chat_participant("pA1", Req(A)))
verifier("A lit A : 200", c == 200 and r.get("id") == "pA1")
r, c = appel(lambda: S.get_chat_participant("pB1", Req(A)))
verifier("A lit B : 404", c == 404, c)
r, c = appel(lambda: S.get_chat_participant("pA1", Req(B)))
verifier("B lit A : 404", c == 404, c)
r, c = appel(lambda: S.get_chat_participant("pA1", Req()))
verifier("anonyme : 401/403", refuse(c), c)
r, c = appel(lambda: S.get_chat_participant("pA1", Req(entete=A)))
verifier("X-User-Email A sans JWT : 403", refuse(c), c)
r, c = appel(lambda: S.get_chat_participant("pA1", Req(B, entete=A)))
verifier("JWT B + X-User-Email A -> 404 (reste B)", c == 404, c)
r, c = appel(lambda: S.get_chat_participant("pB1", Req(ADMIN)))
verifier("super-admin lit B : 200", c == 200)
r, c = appel(lambda: S.get_chat_participant("pLegacy", Req(A)))
verifier("fiche historique sans propriétaire : invisible pour A", c == 404, c)

print("\n== 3. PUT /chat/participants/{id} (liste blanche) ==")
db = base_neuve()
r, c = appel(lambda: S.update_chat_participant("pA1", {"name": "Alice modifiée", "coach_id": B,
                                               "isSubscriber": True, "id": "vol"}, Req(A)))
verifier("champ hors liste blanche -> 400 (jamais un 200 sans effet)", c == 400, c)
r, c = appel(lambda: S.update_chat_participant("pA1", {"name": "Alice modifiée", "email": {"$ne": ""}}, Req(A)))
verifier("A modifie A : 200", c == 200, c)
d = doc(db, "chat_participants", "pA1")
verifier("le nom est modifié", d and d.get("name") == "Alice modifiée")
verifier("coach_id NON modifiable", d and d.get("coach_id") == A, d and d.get("coach_id"))
verifier("isSubscriber / id NON modifiables", d and "isSubscriber" not in d and d.get("id") == "pA1")
verifier("un objet (opérateur) n'entre pas comme valeur", d and d.get("email") == "alice@x.test", d and d.get("email"))
r, c = appel(lambda: S.update_chat_participant("pB1", {"name": "Piraté"}, Req(A)))
verifier("A modifie B : 404", c == 404, c)
verifier("... et la fiche de B est intacte", (doc(db, "chat_participants", "pB1") or {}).get("name") == "Bob chez B")
r, c = appel(lambda: S.update_chat_participant("pB1", {"coach_id": A}, Req()))
verifier("anonyme : 403 (avant : $set libre sans auth)", refuse(c), c)
r, c = appel(lambda: S.update_chat_participant("pB1", {"name": "x"}, Req(entete=B)))
verifier("X-User-Email B sans JWT : 403", refuse(c), c)
r, c = appel(lambda: S.update_chat_participant("pB1", {"name": "Par l'ancien second"}, Req(ANCIEN_SECOND)))
verifier("SA-1 : ancien second modifie B -> refus, fiche intacte",
         refuse(c) and (doc(db, "chat_participants", "pB1") or {}).get("name") != "Par l'ancien second", c)
r, c = appel(lambda: S.update_chat_participant("pB1", {"name": "Par admin"}, Req(ADMIN)))
verifier("super-admin modifie B : 200", c == 200 and (doc(db, "chat_participants", "pB1") or {}).get("name") == "Par admin")

print("\n== 4. DELETE /chat/participants/{id} ==")
db = base_neuve()
r, c = appel(lambda: S.delete_chat_participant("pB1", Req(A)))
verifier("A supprime B : 404 (plus d'oracle 403)", c == 404, c)
verifier("... la fiche de B existe toujours", doc(db, "chat_participants", "pB1") is not None)
r, c = appel(lambda: S.delete_chat_participant("pB1", Req(entete=B)))
verifier("X-User-Email B sans JWT : 403", refuse(c), c)

print("\n== 5. POST /chat/participants — regex & dédoublonnage par coach ==")
db = base_neuve()
noms_avant = {d.get("id"): d.get("name") for d in db.chat_participants.docs}
ids_avant = set(noms_avant)
SPECIAUX = ["+", ".", "*", "[", "(", ")", "\\", "?", "|", "^", "$", "{", "", ".*", "[0-9]+", "(.*)"]
for ch in SPECIAUX:
    r, c = appel(lambda: S.create_chat_participant(S.ChatParticipantCreate(name="Intrus", whatsapp=ch), Req(A)))
    verifier("whatsapp=%r : pas d'erreur 500, pas de fiche existante renvoyée" % ch,
             c == 200 and isinstance(r, dict) and r.get("id") not in ids_avant, (c, r if c != 200 else r.get("id")))
verifier("aucune fiche existante n'a été renommée",
         all(doc(db, "chat_participants", i)["name"] == n for i, n in noms_avant.items()))
# Numéro de B saisi par A (sous une autre écriture) : A obtient SA fiche neuve.
r, c = appel(lambda: S.create_chat_participant(S.ChatParticipantCreate(name="Tentative", whatsapp="+41 79 123 45 67"), Req(A)))
verifier("numéro d'un contact de B saisi par A -> nouvelle fiche de A (pas celle de B)",
         c == 200 and r["id"] != "pB1" and r["coach_id"] == A, r)
verifier("... la réponse de création ne ré-émet aucune coordonnée", c == 200 and r["whatsapp"] is None and r["email"] is None, r)
verifier("... la fiche de B n'est ni renvoyée ni renommée", (doc(db, "chat_participants", "pB1") or {}).get("name") == "Bob chez B")
# Même e-mail chez A (existe) : A retrouve SA fiche, pas celle de B.
r, c = appel(lambda: S.create_chat_participant(S.ChatParticipantCreate(name="Alice bis", email="ALICE@x.test"), Req(A)))
verifier("e-mail existant chez A (casse différente) -> fiche de A mise à jour", c == 200 and r["id"] == "pA1", r)
verifier("... la fiche homonyme de B est intacte", (doc(db, "chat_participants", "pB2") or {}).get("name") == "Alice chez B")
# Numéro canonique : 0765112233 == +41765112233
r, c = appel(lambda: S.create_chat_participant(S.ChatParticipantCreate(name="Alice tel", whatsapp="076 511 22 33"), Req(A)))
verifier("numéro sous une autre écriture (0765…) -> doublon canonique de A", c == 200 and r["id"] == "pA1", r)
# Même personne chez deux coachs = deux fiches distinctes
r1, c1 = appel(lambda: S.create_chat_participant(S.ChatParticipantCreate(name="Carole", email="carole@x.test"), Req(A)))
r2, c2 = appel(lambda: S.create_chat_participant(S.ChatParticipantCreate(name="Carole", email="carole@x.test"), Req(B)))
verifier("même e-mail chez A et B -> deux fiches distinctes",
         c1 == 200 and c2 == 200 and r1["id"] != r2["id"] and r1["coach_id"] == A and r2["coach_id"] == B)
r, c = appel(lambda: S.create_chat_participant(S.ChatParticipantCreate(name="Anon", email="z@x.test"), Req()))
verifier("anonyme : 403", refuse(c), c)
r, c = appel(lambda: S.create_chat_participant(S.ChatParticipantCreate(name="Faux", email="bob@x.test"), Req(entete=B)))
verifier("X-User-Email B sans JWT : 403", refuse(c), c)
# Super-admin : ne retrouve PAS la fiche d'un partenaire
r, c = appel(lambda: S.create_chat_participant(S.ChatParticipantCreate(name="Admin crée", email="bob@x.test"), Req(ADMIN)))
verifier("super-admin crée bob@ : fiche PLATEFORME neuve, pas celle de B",
         c == 200 and r["id"] != "pB1" and r["coach_id"] == S.DEFAULT_COACH_ID, r)
r, c = appel(lambda: S.create_chat_participant(S.ChatParticipantCreate(name="Admin legacy", email="legacy@x.test"), Req(ADMIN)))
verifier("super-admin retrouve le stock plateforme sans propriétaire", c == 200 and r["id"] == "pLegacy", r)

print("\n== 6. /chat/participants/find (route masquée, fermée quand même) ==")
r, c = appel(lambda: S.find_participant(Req(), name=".*"))
verifier("anonyme : 403", refuse(c), c)
r, c = appel(lambda: S.find_participant(Req(A), name=".*"))
verifier("name='.*' est un LITTÉRAL (aucune fiche)", c == 200 and r is None, r)
r, c = appel(lambda: S.find_participant(Req(A), whatsapp="+"))
verifier("whatsapp='+' : pas de 500", c == 200, c)
r, c = appel(lambda: S.find_participant(Req(A), email="bob@x.test"))
verifier("A ne trouve pas la fiche de B", c == 200 and r is None, r)

print("\n== 7. /users/{id} (GET/PUT/DELETE) + relations prouvées ==")
db = base_neuve()
r, c = appel(lambda: S.get_user("uA", Req(A)))
verifier("A lit son user : 200", c == 200)
r, c = appel(lambda: S.get_user("uRelA", Req(A)))
verifier("user GLOBAL relié à A par adhésion ACHETÉE : visible", c == 200)
r, c = appel(lambda: S.get_user("uDcA", Req(A)))
verifier("user GLOBAL relié seulement par un code saisi par A : 404 (preuve fabricable)", c == 404, c)
# MT-2b — P1 audit : le coach importe l'adresse d'un inscrit global, lui crée
# réservation, code, fiche abonné et abonnement MANUEL : rien de cela n'ouvre le user.
db.users.docs.append({"id": "uCible", "name": "Cible", "email": "cible@x.test", "whatsapp": "+41790000099"})
db.chat_participants.docs.append({"id": "pFab", "coach_id": A, "name": "Importée", "email": "cible@x.test"})
db.reservations.docs.append({"id": "rFab", "coach_id": A, "userEmail": "cible@x.test"})
db.discount_codes.docs.append({"id": "dFab", "coach_id": A, "assignedEmail": "cible@x.test", "active": True, "code": "AFR-FAB111"})
db.subscriber_infos.docs.append({"code": "AFR-FAB111", "coach_id": A, "email": "cible@x.test"})
db.subscriptions.docs.append({"id": "sFab", "coach_id": A, "email": "cible@x.test", "status": "active",
                              "code": "AFR-FAB111", "source": "admin_manual", "stripe_customer_id": None})
db.memberships.docs.append({"id": "mFab", "coach_id": A, "email": "cible@x.test", "source": "saisie_manuelle"})
r, c = appel(lambda: S.get_user("uCible", Req(A)))
verifier("preuves FABRICABLES (CRM, résa, code, fiche abonné, abo manuel, adhésion saisie) : 404", c == 404, c)
r, c = appel(lambda: S.get_all_contacts_unified(Req(A)))
_mt2b_ids = {x["id"] for x in r["contacts"]} if c == 200 else set()
verifier("... /contacts/all : le user global n'apparaît pas (seule SA fiche CRM)",
         c == 200 and "uCible" not in _mt2b_ids and "pFab" in _mt2b_ids, _mt2b_ids)
verifier("... et le WhatsApp du user global n'est nulle part", c == 200 and "+41790000099" not in str(r), "")
db.subscriptions.docs.append({"id": "sPaye", "coach_id": A, "email": "cible@x.test", "status": "active",
                              "code": "AFR-PAY111", "source": "stripe_auto"})
r, c = appel(lambda: S.get_user("uCible", Req(A)))
verifier("abonnement PAYÉ (stripe_auto) chez A : user visible", c == 200, c)
r, c = appel(lambda: S.get_user("uNone", Req(A)))
verifier("user GLOBAL sans relation : 404", c == 404, c)
r, c = appel(lambda: S.get_user("uRelB", Req(A)))
verifier("user relié à B : 404 pour A", c == 404, c)
r, c = appel(lambda: S.get_user("uRelB", Req(B)))
verifier("user relié à B (abonnement) : visible par B", c == 200)
r, c = appel(lambda: S.get_user("uA", Req(B)))
verifier("B lit le user de A : 404", c == 404, c)
r, c = appel(lambda: S.get_user("uA", Req()))
verifier("anonyme : 403 (était PUBLIC)", refuse(c), c)
r, c = appel(lambda: S.get_user("uA", Req(entete=A)))
verifier("X-User-Email A sans JWT : 403", refuse(c), c)
r, c = appel(lambda: S.get_user("uNone", Req(ADMIN)))
verifier("super-admin : global", c == 200)
r, c = appel(lambda: S.get_user("uNone", Req(ANCIEN_SECOND)))
verifier("SA-1 : ancien second -> refus", refuse(c) or c == 404, c)
r, c = appel(lambda: S.update_user("uA", S.UserCreate(name="Nouveau", email="ua@x.test"), Req(A)))
verifier("A modifie son user : 200", c == 200 and (doc(db, "users", "uA") or {}).get("name") == "Nouveau")
verifier("... coach_id conservé", (doc(db, "users", "uA") or {}).get("coach_id") == A)
r, c = appel(lambda: S.update_user("uA", S.UserCreate(name="Pirate", email="x@x.test"), Req(B)))
verifier("B modifie le user de A : 404", c == 404, c)
r, c = appel(lambda: S.update_user("uA", S.UserCreate(name="Pirate", email="x@x.test"), Req()))
verifier("PUT anonyme : 403 (était SANS auth)", refuse(c), c)
r, c = appel(lambda: S.update_user("uRelA", S.UserCreate(name="Pirate", email="x@x.test"), Req(A)))
verifier("user GLOBAL partagé : A ne le modifie pas (403)", c == 403, c)
r, c = appel(lambda: S.delete_user("uA", Req(B)))
verifier("B supprime le user de A : 404", c == 404, c)
r, c = appel(lambda: S.delete_user("uA", Req(entete=A)))
verifier("DELETE X-User-Email A sans JWT : 403 (repli retiré)", refuse(c), c)
r, c = appel(lambda: S.delete_user("uRelA", Req(A)))
verifier("DELETE d'un user GLOBAL par un coach relié : 403", c == 403, c)
verifier("... toujours présent", doc(db, "users", "uRelA") is not None)
db.discount_codes.docs.append({"id": "dB-ua", "coach_id": B, "assignedEmail": "ua@x.test",
                               "active": False, "code": "AFR-BUA000"})
r, c = appel(lambda: S.delete_user("uA", Req(A)))
verifier("A supprime son user : 200", c == 200 and doc(db, "users", "uA") is None, (c, r))
verifier("... sans libérer le code d'un AUTRE coach", (doc(db, "discount_codes", "dB-ua") or {}).get("assignedEmail") == "ua@x.test")

print("\n== 8. POST /users (inscription PUBLIQUE conservée) ==")
db = base_neuve()
r, c = appel(lambda: S.create_user(S.UserCreate(name="Visiteur", email="v@x.test"), Req()))
verifier("visiteur anonyme : inscription OK", c == 200)
verifier("... sans propriétaire", "coach_id" not in par(db, "users", "email", "v@x.test"))
r, c = appel(lambda: S.create_user(S.UserCreate(name="Contact", email="c@x.test"), Req(A)))
verifier("coach A (JWT) : fiche rattachée à A", c == 200 and
         par(db, "users", "email", "c@x.test").get("coach_id") == A)
r, c = appel(lambda: S.create_user(S.UserCreate(name="Faux", email="f@x.test"), Req(entete=A)))
verifier("X-User-Email A seul : AUCUN rattachement", c == 200 and
         "coach_id" not in par(db, "users", "email", "f@x.test"))

print("\n== 9. GET /users/{id}/profile (mini-fiche publique, sans e-mail) ==")
db = base_neuve()
r, c = appel(lambda: S.get_user_profile("uNone", Req()))
verifier("anonyme : 200, nom présent", c == 200 and r.get("name") == "Personne")
verifier("anonyme : PAS d'e-mail", c == 200 and "email" not in r, r.get("email") if c == 200 else c)
r, c = appel(lambda: S.get_user_profile("none@x.test", Req()))
verifier("id = l'adresse elle-même : e-mail rendu (n'apprend rien)", c == 200 and r.get("email") == "none@x.test")
r, c = appel(lambda: S.get_user_profile("uRelA", Req(A)))
verifier("coach relié : e-mail rendu", c == 200 and r.get("email") == "rel@x.test", r)
r, c = appel(lambda: S.get_user_profile("uRelB", Req(A)))
verifier("coach NON relié : pas d'e-mail", c == 200 and "email" not in r)
r, c = appel(lambda: S.get_user_profile("uNone", Req(ADMIN)))
verifier("super-admin : e-mail rendu", c == 200 and r.get("email") == "none@x.test")
r, c = appel(lambda: S.get_user_profile("pB1", Req(entete=ADMIN)))
verifier("X-User-Email admin sans JWT : pas d'e-mail", c == 200 and "email" not in r)

print("\n== 10. PUT /chat/participants/{id}/birthday (chemin VISITEUR conservé) ==")
db = base_neuve()
r, c = appel(lambda: S.save_participant_birthday("pA1", Req(corps={"birthday": "03-14"})))
verifier("visiteur (id = capacité) : 200", c == 200 and (doc(db, "chat_participants", "pA1") or {}).get("birthday") == "03-14")
r, c = appel(lambda: S.save_participant_birthday("pA1", Req(corps={"birthday": "03-14", "coach_id": B, "name": "x"})))
verifier("liste blanche : coach_id / name ignorés", (doc(db, "chat_participants", "pA1") or {}).get("coach_id") == A
         and (doc(db, "chat_participants", "pA1") or {}).get("name") == "Alice chez A")
r, c = appel(lambda: S.save_participant_birthday("pA1", Req(corps={"birthday": "ab-cd"})))
verifier("date non numérique : 400", c == 400, c)
r, c = appel(lambda: S.save_participant_birthday("pA1", Req(corps=["x"])))
verifier("corps non-objet : 400 (plus de 500)", c == 400, c)

print("\n== 11. /contacts/all : users & sessions filtrés ==")
db = base_neuve()
r, c = appel(lambda: S.get_all_contacts_unified(Req(A)))
ok = c == 200 and r.get("success")
verifier("A : 200", ok, r if not ok else "")
ids = {x["id"] for x in r["contacts"]} if ok else set()
verifier("A voit son user et les users RELIÉS (preuve forte)", {"uA", "uRelA"} <= ids and "uDcA" not in ids, ids)
verifier("A ne voit PAS les users sans relation ni ceux de B", not ({"uNone", "uRelB"} & ids), ids & {"uNone", "uRelB"})
verifier("A voit SON groupe, pas celui de B", "sessA" in ids and "sessB" not in ids)
verifier("A ne voit pas les fiches CRM de B", not ({"pB1", "pB2"} & ids))
r, c = appel(lambda: S.get_all_contacts_unified(Req(B)))
ids = {x["id"] for x in r["contacts"]} if c == 200 else set()
verifier("B voit uRelB, pas uRelA", "uRelB" in ids and "uRelA" not in ids, ids)
r, c = appel(lambda: S.get_all_contacts_unified(Req(ADMIN)))
ids = {x["id"] for x in r["contacts"]} if c == 200 else set()
verifier("super-admin : global (tous users + tous groupes)",
         {"uA", "uRelA", "uNone", "uRelB", "sessA", "sessB"} <= ids, ids)
r, c = appel(lambda: S.get_all_contacts_unified(Req(entete=ADMIN)))
verifier("X-User-Email admin sans JWT : 403", refuse(c), c)

print("\n== 12. Segments /contacts/segments & /contacts/segment/{cle} ==")
db = base_neuve()
pers_a, _ = sur(lambda: asyncio.run(SEG._calcule_personnes(A)), ([], None))
ids_a = {p["id"] for p in pers_a}
verifier("portefeuille A : ses fiches et users reliés seulement",
         "pA1" in ids_a and not ({"pB1", "pB2", "uNone", "uRelB", "pPlat", "pLegacy"} & ids_a), ids_a)
pers_g, _ = sur(lambda: asyncio.run(SEG._calcule_personnes()), ([], None))
verifier("appel interne sans coach : vue plateforme (compatibilité moteur campagnes)",
         {"pB1", "pA1"} <= {p["id"] for p in pers_g})
r, c = appel(lambda: SEG.compter_segments(Req(A)))
verifier("A : /contacts/segments 200, personnes = son portefeuille", c == 200 and r["personnes"] == len(pers_a), r if c != 200 else r["personnes"])
r, c = appel(lambda: SEG.compter_segments(Req(ADMIN)))
verifier("super-admin : /contacts/segments 200", c == 200, c)
verifier("... vue globale", c == 200 and r["personnes"] == len(pers_g))
r, c = appel(lambda: SEG.compter_segments(Req(ANCIEN_SECOND)))
verifier("SA-1 : ancien second : /contacts/segments -> refus (plus de vue globale)", refuse(c), c)
r, c = appel(lambda: SEG.lister_segment("whatsapp", Req(A)))
verifier("A : segment whatsapp sans fiche de B", c == 200 and "pB1" not in {x["id"] for x in r["contacts"]}, r)
r, c = appel(lambda: SEG.compter_segments(Req(entete=A)))
verifier("X-User-Email seul : 403 « reconnectez-vous »", c == 403 and "reconnectez-vous" in str(r), r)
verifier("`_autorise` garde sa signature (campagnes AGENT 1)",
         sur(lambda: asyncio.run(SEG._est_coach_ou_admin(ADMIN)) is True
             and asyncio.run(SEG._est_coach_ou_admin(ANCIEN_SECOND)) is False
             and asyncio.run(SEG._est_coach_ou_admin("")) is False, False))

print("\n== 13. space-link : propriété de l'abonnement ==")
db = base_neuve()
r, c = appel(lambda: S.get_space_link_by_email("suba@x.test", Req(A)))
verifier("A : son abonné -> 200 + code", c == 200 and r["code"] == "AFR-AAA111")
r, c = appel(lambda: S.get_space_link_by_email("dca@x.test", Req(A)))
verifier("A : code d'accès qu'il a émis -> 200", c == 200 and r["code"] == "AFR-DCA111")
r, c = appel(lambda: S.get_space_link_by_email("relb@x.test", Req(A)))
verifier("A : abonné de B -> 404", c == 404, (c, r))
r404, c404 = appel(lambda: S.get_space_link_by_email("inconnu@x.test", Req(A)))
verifier("... réponse IDENTIQUE à une adresse inconnue", (c, r) == (c404, r404), (r, r404))
r, c = appel(lambda: S.get_space_link_by_email("suba@x.test", Req(B)))
verifier("B : abonné de A -> 404", c == 404, c)
r, c = appel(lambda: S.get_space_link_by_email("relb@x.test", Req(ADMIN)))
verifier("super-admin : global", c == 200 and r["code"] == "AFR-BBB111")
r, c = appel(lambda: S.get_space_link_by_email("relb@x.test", Req(ANCIEN_SECOND)))
verifier("SA-1 : ancien second : pas de lien d'espace d'autrui", c != 200, c)
r, c = appel(lambda: S.get_space_link_by_email("suba@x.test", Req(entete=A)))
verifier("X-User-Email A sans JWT : 403", refuse(c), c)
r, c = appel(lambda: S.get_space_link_by_email("suba@x.test", Req(B, entete=A)))
verifier("JWT B + X-User-Email A : reste B -> 404", c == 404, c)

print("\n== 14. Catégories ==")
db = base_neuve()
r, c = appel(lambda: CAT.get_contact_categories(Req(A)))
verifier("A lit ses catégories", c == 200 and {x["id"] for x in r["categories"]} == {"cA"}, r)
r, c = appel(lambda: CAT.get_contact_categories(Req(ADMIN)))
verifier("super-admin -> catégories de la PLATEFORME", c == 200 and {x["id"] for x in r["categories"]} == {"cPlat"}, r)
r, c = appel(lambda: CAT.get_contact_categories(Req(ANCIEN_SECOND)))
verifier("SA-1 : ancien second -> jamais les catégories de la PLATEFORME",
         c != 200 or "cPlat" not in {x["id"] for x in r.get("categories", [])}, (c, r))
r, c = appel(lambda: CAT.get_contact_categories(Req(entete=A)))
verifier("X-User-Email A sans JWT : 403", refuse(c), c)
r, c = appel(lambda: CAT.get_contact_categories(Req()))
verifier("anonyme : 403", refuse(c), c)
r, c = appel(lambda: CAT.update_contact_category("cA", Req(A, corps={"name": "Cat A2"})))
verifier("A modifie sa catégorie", c == 200 and (doc(db, "contact_categories", "cA") or {}).get("name") == "Cat A2")
r, c = appel(lambda: CAT.update_contact_category("cB", Req(A, corps={"name": "Piratée"})))
verifier("A modifie la catégorie de B : 404", c == 404 and (doc(db, "contact_categories", "cB") or {}).get("name") == "Cat B", c)
r, c = appel(lambda: CAT.update_contact_category("cA", Req(B, corps={"name": "Piratée"})))
verifier("B modifie la catégorie de A : 404", c == 404, c)
r, c = appel(lambda: CAT.delete_contact_category("cB", Req(A)))
verifier("A supprime la catégorie de B : 404", c == 404 and doc(db, "contact_categories", "cB") is not None, c)
r, c = appel(lambda: CAT.update_contact_category("cB", Req(ADMIN, corps={"name": "Admin"})))
verifier("super-admin : modifie la catégorie de B (global)", c == 200 and doc(db, "contact_categories", "cB")["name"] == "Admin", c)
# set-categories
r, c = appel(lambda: CAT.set_contact_categories(Req(A, corps={"contact_ids": ["pA1"], "category_ids": ["cA", "cB"]})))
verifier("A catégorise sa fiche : 1 mise à jour", c == 200 and r["updated"] == 1)
verifier("... la catégorie de B est filtrée", (doc(db, "chat_participants", "pA1") or {}).get("categories") == ["cA"],
         doc(db, "chat_participants", "pA1").get("categories"))
r, c = appel(lambda: CAT.set_contact_categories(Req(A, corps={"contact_ids": ["pB1"], "category_ids": ["cA"]})))
verifier("A catégorise la fiche de B : 404 et fiche intacte",
         c == 404 and "categories" not in doc(db, "chat_participants", "pB1"), c)
r, c = appel(lambda: CAT.set_contact_categories(Req(A, corps={"contact_ids": ["pA1", "pB1"], "category_ids": ["cA"], "mode": "set"})))
verifier("lot mixte A+B : 404 et RIEN écrit (même pas la fiche de A)", c == 404
         and doc(db, "chat_participants", "pA1").get("categories") == ["cA"], c)
db.chat_participants.docs.append({"id": "pA3", "coach_id": A, "name": "A3"})
r, c = appel(lambda: CAT.set_contact_categories(Req(ANCIEN_SECOND, corps={"contact_ids": ["pB1", "pA3"], "category_ids": ["cB", "cA"]})))
verifier("SA-1 : ancien second ne catégorise pas les fiches d'autrui",
         c != 200 and doc(db, "chat_participants", "pB1").get("categories") != ["cB", "cA"], (c, r))
r, c = appel(lambda: CAT.set_contact_categories(Req(ADMIN, corps={"contact_ids": ["pB1", "pA3"], "category_ids": ["cB", "cA"]})))
verifier("super-admin : catégorise toute fiche avec toute catégorie (global)", c == 200 and r["updated"] == 2
         and doc(db, "chat_participants", "pB1").get("categories") == ["cB", "cA"], (c, r))
n_avant = len(db.chat_participants.docs)
r, c = appel(lambda: CAT.set_contact_categories(Req(A, corps={"contact_ids": ["uNone"], "category_ids": ["cA"]})))
verifier("user SANS relation : 404, pas copié dans le CRM de A", c == 404 and len(db.chat_participants.docs) == n_avant, c)
r, c = appel(lambda: CAT.set_contact_categories(Req(A, corps={"contact_ids": ["uRelA"], "category_ids": ["cA"]})))
cp = doc(db, "chat_participants", "uRelA")
verifier("user RELIÉ : copié chez A et catégorisé", c == 200 and cp and cp["coach_id"] == A and cp["categories"] == ["cA"], cp)
r, c = appel(lambda: CAT.set_contact_categories(Req(B, corps={"contact_ids": ["uRelA"], "category_ids": ["cB"]})))
verifier("id déjà copié chez A : B reçoit 404, pas de doublon d'id",
         c == 404 and sum(1 for d in db.chat_participants.docs if d.get("id") == "uRelA") == 1)
r, c = appel(lambda: CAT.filter_contacts_by_categories(Req(A, corps={"category_ids": ["cA"]})))
verifier("filter-by-categories : portefeuille de A, paginé", c == 200 and r["limit"] == 50 and
         {"pA1", "uRelA"} <= {x["id"] for x in r["contacts"]} and "pB1" not in {x["id"] for x in r["contacts"]}, r)
r, c = appel(lambda: CAT.filter_contacts_by_categories(Req(entete=A, corps={"category_ids": ["cA"]})))
verifier("filter-by-categories X-User-Email seul : 403", refuse(c), c)
r, c = appel(lambda: CAT.get_category_stats(Req(entete=A)))
verifier("stats X-User-Email seul : 403", refuse(c), c)

print("\n== 15. Leads ==")
db = base_neuve()
r, c = appel(lambda: S.get_leads(Req(A)))
verifier("A lit ses leads", c == 200 and {x["id"] for x in r} == {"lA"})
r, c = appel(lambda: S.get_leads(Req(entete=ADMIN)))
verifier("X-User-Email admin sans JWT : 403 (P0 fermé)", refuse(c), c)
r, c = appel(lambda: S.get_leads(Req(ADMIN)))
verifier("super-admin : global, paginé (<= 50)", c == 200 and len(r) == 3)
r, c = appel(lambda: S.get_leads(Req(ANCIEN_SECOND)))
verifier("SA-1 : ancien second : pas la liste globale des leads", refuse(c) or (c == 200 and len(r) == 0), (c, r))
r, c = appel(lambda: S.delete_lead("lB", Req(A)))
verifier("A supprime le lead de B : 404", c == 404 and doc(db, "leads", "lB") is not None, c)
r, c = appel(lambda: S.delete_lead("lB", Req(entete=B)))
verifier("X-User-Email B sans JWT : 403", refuse(c), c)
r, c = appel(lambda: S.delete_lead("lA", Req(A)))
verifier("A supprime son lead", c == 200 and doc(db, "leads", "lA") is None)
# POST public
r, c = appel(lambda: S.create_lead(Req(), S.Lead(firstName="Visiteur", whatsapp="+41761110009", email="vis@x.test")))
verifier("POST /leads visiteur anonyme : OK (chemin public)", c == 200)
verifier("... rattaché à la plateforme", par(db, "leads", "email", "vis@x.test")["coach_id"] == S.DEFAULT_COACH_ID)
r, c = appel(lambda: S.create_lead(Req(entete=B), S.Lead(firstName="Planté", whatsapp="+41761110010", email="pl@x.test")))
verifier("X-User-Email B ne choisit PAS le propriétaire", par(db, "leads", "email", "pl@x.test")["coach_id"] == S.DEFAULT_COACH_ID)
r, c = appel(lambda: S.create_lead(Req(), S.Lead(firstName="Curieux", whatsapp="+41761110003", email="")))
verifier("lead existant retrouvé par numéro : la réponse NE contient PAS ses données",
         c == 200 and r.get("firstName") == "Curieux" and "coach_id" not in r, r)
r, c = appel(lambda: S.create_lead(Req(), S.Lead(firstName="Vide", whatsapp=".", email="")))
verifier("e-mail vide + numéro « . » : nouveau lead, aucun lead existant renommé",
         c == 200 and (doc(db, "leads", "lSansMail") or {}).get("firstName") == "Curieux")

print("\n== 16. check-duplicates / bulk-import / add-tags / deduplicate ==")
db = base_neuve()
r, c = appel(lambda: S.check_duplicate_contacts(Req(A, corps={"emails": ["bob@x.test", "alice@x.test"],
                                                      "phones": ["0765112233", "0791234567", "+", "."]})))
verifier("check-duplicates A : ses doublons seulement (e-mail)", c == 200 and r["existing_emails"] == ["alice@x.test"], r)
verifier("check-duplicates A : numéro canonique de A trouvé, celui de B non",
         c == 200 and r["existing_phones"] == ["0765112233"], r)
r, c = appel(lambda: S.check_duplicate_contacts(Req(ADMIN, corps={"emails": ["bob@x.test", "alice@x.test"]})))
verifier("check-duplicates super-admin : vue GLOBALE", c == 200 and r["existing_emails"] == ["alice@x.test", "bob@x.test"], r)
r, c = appel(lambda: S.check_duplicate_contacts(Req(entete=A, corps={"emails": ["bob@x.test"]})))
verifier("check-duplicates X-User-Email seul : 403", refuse(c), c)
r, c = appel(lambda: S.bulk_import_contacts(Req(A, corps={"contacts": [
    {"name": "Bob import", "email": "bob@x.test"},
    {"name": "Num B", "phone": "+41791234567"},
    {"name": "Court", "phone": "079"},
    {"name": "Point", "phone": "."},
    {"name": "Alice", "email": "alice@x.test"},
    {"name": "Dup lot", "email": "lot@x.test"},
    {"name": "Dup lot 2", "email": "LOT@x.test"},
]})))
verifier("bulk-import A : e-mail/numéro de B NE sont PAS des doublons",
         c == 200 and r["imported"] == 5 and r["duplicates"] == 2, r)
verifier("... la fiche de B n'est pas renommée", (doc(db, "chat_participants", "pB1") or {}).get("name") == "Bob chez B")
verifier("... fiches créées chez A", sum(1 for d in db.chat_participants.docs
                                          if d.get("coach_id") == A and d.get("source") == "import") == 5)
r, c = appel(lambda: S.bulk_import_contacts(Req(entete=A, corps={"contacts": [{"email": "q@x.test"}]})))
verifier("bulk-import X-User-Email seul : 403", refuse(c), c)
r, c = appel(lambda: S.add_tags_to_contacts(Req(A, corps={"contact_ids": ["pA1", "pB1"], "tags": ["vip"]})))
verifier("add-tags lot mixte A+B : 404, rien n'est tagué", c == 404
         and "vip" not in (doc(db, "chat_participants", "pB1").get("tags") or [])
         and "vip" not in (doc(db, "chat_participants", "pA1").get("tags") or []), c)
r, c = appel(lambda: S.add_tags_to_contacts(Req(A, corps={"contact_ids": ["pA1"], "tags": ["vip"]})))
verifier("add-tags A sur SA fiche : 1", c == 200 and r["updated"] == 1)
r, c = appel(lambda: S.add_tags_to_contacts(Req(corps={"contact_ids": ["pB1"], "tags": ["x"]})))
verifier("add-tags anonyme : 403 (était SANS auth)", refuse(c), c)
# deduplicate
db = base_neuve()
db.chat_participants.docs += [
    {"id": "dA1", "coach_id": A, "name": "Dup", "email": "dup@x.test", "created_at": "2026-01-01"},
    {"id": "dA2", "coach_id": A, "name": "Dup", "email": "dup@x.test", "created_at": "2026-02-01"},
    {"id": "dB1", "coach_id": B, "name": "Dup", "email": "dup@x.test", "created_at": "2025-01-01"},
]
r, c = appel(lambda: S.deduplicate_contacts(Req(A)))
verifier("deduplicate A : fusionne SES doublons", c == 200 and r["merged"] == 1 and doc(db, "chat_participants", "dA2") is None, r)
verifier("... la fiche de B (plus ancienne) n'est PAS touchée", doc(db, "chat_participants", "dB1") is not None)
db.chat_participants.docs.append({"id": "dB2", "coach_id": B, "name": "Dup", "email": "dup@x.test", "created_at": "2026-03-01"})
r, c = appel(lambda: S.deduplicate_contacts(Req(ADMIN)))
verifier("deduplicate super-admin SANS paramètre : portée PLATEFORME (fiches de B intactes)",
         c == 200 and doc(db, "chat_participants", "dB2") is not None, r)
r, c = appel(lambda: S.deduplicate_contacts(Req(ADMIN), scope="global"))
verifier("deduplicate super-admin : par propriétaire (A et B gardent chacun une fiche)",
         c == 200 and doc(db, "chat_participants", "dA1") and doc(db, "chat_participants", "dB1")
         and doc(db, "chat_participants", "dB2") is None, r)
verifier("... pA1 (alice chez A) et pB2 (alice chez B) coexistent",
         doc(db, "chat_participants", "pA1") is not None and doc(db, "chat_participants", "pB2") is not None)
r, c = appel(lambda: S.deduplicate_contacts(Req(entete=A)))
verifier("deduplicate X-User-Email seul : 403", refuse(c), c)

print("\n== 17. Types, suggestions, dry-run, notes, suivi abonnés ==")
db = base_neuve()
r, c = appel(lambda: S.t3_classer_contact("pA1", Req(A, corps={"contact_type": "participant"})))
verifier("A classe sa fiche", c == 200)
r, c = appel(lambda: S.t3_classer_contact("pB1", Req(A, corps={"contact_type": "participant"})))
verifier("A classe la fiche de B : 404", c == 404, c)
r, c = appel(lambda: S.t3_classer_contact("pA1", Req(entete=A, corps={"contact_type": "participant"})))
verifier("type : X-User-Email seul -> 403", refuse(c), c)
r, c = appel(lambda: S.t3_dry_run_participant(Req(entete=A)))
verifier("dry-run : X-User-Email seul -> 403", refuse(c), c)
db.reservations.docs.append({"id": "r2", "coach_id": A, "userEmail": "bob@x.test", "validated": True})
r, c = appel(lambda: S.t3_suggestions_participant(Req(A)))
verifier("suggestions : jamais la fiche d'un autre coach",
         c == 200 and "pB1" not in {s["contact_id"] for s in r["suggestions"]}, r)
# notes
r, c = appel(lambda: S.v338_lire_note("subscriber", "AFR-BBB111", Req(entete=B)))
verifier("note : X-User-Email du coach sans JWT -> 403 (repli retiré)", refuse(c), c)
r, c = appel(lambda: S.v338_lire_note("subscriber", "AFR-BBB111", Req(A)))
verifier("note : A lit la note d'un abonné de B -> 403", refuse(c), c)
r, c = appel(lambda: S.v338_lire_note("subscriber", "AFR-BBB111", Req(B)))
verifier("note : B (JWT) lit la note de SON abonné -> 200", c == 200, (c, r))
r, c = appel(lambda: S.v338_lire_note("subscriber", "AFR-BBB111", Req(), code="AFR-BBB111"))
verifier("note : l'ABONNÉ lui-même (par son code) -> 200 (chemin conservé)", c == 200, (c, r))
r, c = appel(lambda: S.v338_ecrire_note(Req(entete=B, corps={"target_type": "subscriber",
                                                     "target_id": "AFR-BBB111", "text": "x"})))
verifier("note : écriture X-User-Email seul -> 403", refuse(c), c)
# suivi abonnés
r, c = appel(lambda: S.v334_suivi_abonnes_coach(Req(entete=ADMIN)))
verifier("suivi abonnés : X-User-Email admin sans JWT -> 403", refuse(c), c)
r, c = appel(lambda: S.v334_suivi_abonnes_coach(Req(A)))
verifier("suivi abonnés : A (JWT) -> 200", c == 200, (c, r))

print("\n== 18. Module commun : preuves de relation & contrat AGENT 1 ==")
db = base_neuve()
rel = sur(lambda: asyncio.run(TC.emails_relies(db, A)), set())
verifier("emails_relies(A) = preuves FORTES seulement (adhésion achetée)",
         rel == {"rel@x.test"}, rel)
verifier("... sans aucune adresse de B", not ({"bob@x.test", "relb@x.test"} & rel), rel)
db.leads.docs.append({"id": "lX", "coach_id": A, "email": "none@x.test"})
verifier("un LEAD (public, fabricable) n'est PAS une preuve",
         sur(lambda: "none@x.test" not in asyncio.run(TC.emails_relies(db, A)), False))
verifier("filtrer_ids users : relation prouvée seulement",
         sur(lambda: asyncio.run(TC.filtrer_ids(db, A, "users", ["uNone", "uRelA", "uA", "uRelA", "uRelB"]))) == ["uRelA", "uA"])
verifier("filtrer_ids chat_participants : portefeuille",
         sur(lambda: asyncio.run(TC.filtrer_ids(db, A, "chat_participants", ["pB1", "pA1", {"$ne": 1}]))) == ["pA1"])
try:
    TC.filtre_proprietaire("")
    verifier("identité vide -> PerimetreRefuse", False)
except TC.PerimetreRefuse:
    verifier("identité vide -> PerimetreRefuse", True)
verifier("variantes_telephone('.') = [] (pas une identité)", sur(lambda: TC.variantes_telephone(".") == [], False))
verifier("variantes_telephone canonise 0041/0/+41",
         sur(lambda: "0765112233" in TC.variantes_telephone("+41 76 511 22 33")
             and "+41765112233" in TC.variantes_telephone("0041765112233"), False))

print("\n== 19. MT-2b : replis X-User-Email restants, rôle coach_auth, entrées invalides ==")
db = base_neuve()
db.users.docs.append({"id": "uProf", "name": "Profil", "email": "prof@x.test"})
r, c = appel(lambda: S.update_user_mini_profile("uProf", Req(entete="prof@x.test", corps={"bio": "piraté"})))
verifier("PATCH /users/{id}/profile : X-User-Email de la personne sans jeton -> 403", c == 403
         and "bio" not in doc(db, "users", "uProf"), c)
r, c = appel(lambda: S.update_user_mini_profile("uProf", Req(entete=ADMIN, corps={"bio": "piraté"})))
verifier("PATCH profile : X-User-Email super-admin sans JWT -> 403", c == 403, c)
r, c = appel(lambda: S.update_user_mini_profile("uProf", Req("prof@x.test", type_="subscriber", corps={"bio": "ok"})))
verifier("PATCH profile : jeton ABONNÉ de la personne -> 200", c == 200, (c, r))
r, c = appel(lambda: S.update_user_mini_profile("uProf", Req(ADMIN, corps={"bio": "admin"})))
verifier("PATCH profile : JWT super-admin -> 200", c == 200, (c, r))
db.users.docs.append({"id": "fantome"})
r, c = appel(lambda: S.cleanup_ghost_users(Req(entete=ADMIN)))
verifier("cleanup-ghost-users : X-User-Email super-admin sans JWT -> 403 (plus de delete_many)",
         c == 403 and doc(db, "users", "fantome") is not None, c)
r, c = appel(lambda: S.cleanup_ghost_users(Req(A)))
verifier("cleanup-ghost-users : JWT coach -> 403", c == 403, c)
r, c = appel(lambda: S.cleanup_ghost_users(Req(ANCIEN_SECOND)))
verifier("SA-1 : cleanup-ghost-users : JWT de l'ancien second -> 403, rien supprimé",
         c == 403 and doc(db, "users", "fantome") is not None, c)
r, c = appel(lambda: S.cleanup_ghost_users(Req(ADMIN)))
verifier("cleanup-ghost-users : JWT super-admin -> 200", c == 200 and doc(db, "users", "fantome") is None, (c, r))
r, c = appel(lambda: S._v334_autoriser(Req(entete=A), "AFR-AAA111"))
verifier("_v334_autoriser : X-User-Email du coach sans JWT -> 403", c == 403, c)
r, c = appel(lambda: S._v334_autoriser(Req(A), "AFR-AAA111"))
verifier("_v334_autoriser : JWT du coach propriétaire -> coach", c == 200 and r[0] == "coach", r)
r, c = appel(lambda: S._v334_autoriser(Req(B), "AFR-AAA111"))
verifier("_v334_autoriser : JWT d'un autre coach -> 403", c == 403, c)
r, c = appel(lambda: S._v334_autoriser(Req(), "AFR-AAA111", "AFR-AAA111"))
verifier("_v334_autoriser : chemin ABONNÉ par code AFR conservé", c == 200 and r[0] == "subscriber", r)
C_AUTH = "coach.auth.seul@exemple.test"
db.coach_auth.docs.append({"email": C_AUTH})
from api.routes.shared import v20_exiger_coach_signe as _v20
r, c = appel(lambda: _v20(Req(C_AUTH), db, "banc"))
verifier("v20_exiger_coach_signe : coach présent seulement dans coach_auth -> accepté (comme _v309)",
         c == 200 and r == C_AUTH, (c, r))
r, c = appel(lambda: CAT.create_contact_category(Req(A, corps={"name": 123})))
verifier("POST /contact-categories name non-chaîne -> 400 (pas 500)", c == 400, (c, r))
r, c = appel(lambda: CAT.create_contact_category(Req(A, corps={"name": {"$ne": 1}})))
verifier("POST /contact-categories name objet -> 400", c == 400, (c, r))
r, c = appel(lambda: CAT.create_contact_category(Req(A, corps={"name": "Nouvelle", "color": 5})))
verifier("POST /contact-categories valide (couleur invalide -> défaut) -> 200", c == 200 and r["category"]["color"] == "#6B7280", (c, r))
# set-categories : lectures groupées
_compteur = {"find_one": 0}
_orig = Collection.find_one
async def _fo(self, *a, **k):
    if self.nom in ("chat_participants", "users"):
        _compteur["find_one"] += 1
    return await _orig(self, *a, **k)
Collection.find_one = _fo
try:
    r, c = appel(lambda: CAT.set_contact_categories(Req(A, corps={"contact_ids": ["pA1", "uRelA"], "category_ids": ["cA"]})))
finally:
    Collection.find_one = _orig
verifier("set-categories : 0 find_one par contact (lectures $in groupées)", c == 200 and _compteur["find_one"] == 0,
         (c, _compteur))

# ============================================================================
ok = sum(1 for _, v, _ in RESULTATS if v)
print("\n%d/%d verifications" % (ok, len(RESULTATS)))
sys.exit(0 if ok == len(RESULTATS) else 1)
