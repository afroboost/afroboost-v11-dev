#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MT-6 — /api/subscriber-info/{code} : fin de la fuite e-mail/WhatsApp par code.

CE QUE CE FICHIER PROUVE
==============================================================================
GET  /subscriber-info/{code}
  - abonné porteur du jeton d'appareil DE CE CODE -> fiche complète (l'écran
    ChatWidget pré-remplit et reconnecte comme avant) ;
  - anonyme qui connaît seulement le code -> {exists, name} et RIEN d'autre
    (ni e-mail, ni WhatsApp, ni date de naissance) ;
  - jeton abonné d'un AUTRE code -> traité comme anonyme ;
  - coach : JWT SIGNÉ + propriétaire du code (subscriptions/discount_codes
    .coach_id) -> fiche complète ; autre coach -> 404 IDENTIQUE au code inconnu ;
    super-admin (les DEUX) -> global ; X-User-Email seul -> jamais le chemin
    coach ; JWT B + X-User-Email A -> reste B.
PUT  /subscriber-info/{code}
  - exige le jeton abonné de CE code (JWT_SECRET posé) ; liste blanche
    name/whatsapp/birthday ; l'e-mail écrit est celui du jeton, jamais le corps ;
    un tiers (même code collectif, autre e-mail) ne réécrit pas la fiche.

Banc : base Mongo EN MÉMOIRE, vrais JWT HS256 signés avec un secret de banc,
jetons abonnés émis par `make_subscriber_token` (le vrai émetteur). Aucune
base réelle, aucun réseau.

    python3 tests/test_mt6_subscriber_info.py
"""
import asyncio
import copy
import os
import re
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

SECRET = "secret-de-banc-mt6-sans-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ["MONGO_URL"] = "mongodb://bouchon-inexistant-mt6:27017"

import jwt as pyjwt  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import api.server as S  # noqa: E402
from api.routes.shared import SUPER_ADMIN_EMAILS, make_subscriber_token  # noqa: E402

RESULTATS = []


def verifier(intitule, condition, detail=""):
    RESULTATS.append((intitule, bool(condition), detail))
    print("  %-6s %s" % ("OK  " if condition else "ECHEC", intitule))
    if detail and not condition:
        print("           -> %s" % (str(detail)[:300],))
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
# SA-1 : un seul super-admin ; l'ancien second est vérifié comme NON super-admin.
ANCIEN_SECOND = "afroboost.bassi@gmail.com"
A = "coach.a.mt2@exemple.test"
B = "coach.b.mt2@exemple.test"


ADMIN = SUPER_ADMIN_EMAILS[0]
# SA-1 : un seul super-admin ; l'ancien second est vérifié comme NON super-admin.
ANCIEN_SECOND = "afroboost.bassi@gmail.com"
A = "coach.a.mt6@exemple.test"
B = "coach.b.mt6@exemple.test"


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
    def __init__(self, qui=None, entete=None, corps=None, abonne=None):
        """`abonne` = (code, email) -> jeton d'appareil abonné (X-Subscriber-Token)."""
        h = Entetes()
        if qui:
            h["Authorization"] = "Bearer " + jeton(qui)
        if entete:
            h["X-User-Email"] = entete
        if abonne:
            h["X-Subscriber-Token"] = make_subscriber_token(abonne[0], abonne[1])
        self.headers = h
        self.query_params = {}
        self._corps = corps if corps is not None else {}
        self.cookies = {}

        class _C:
            host = "127.0.0.1"
        self.client = _C()

    async def json(self):
        return self._corps


def appel(fabrique):
    try:
        return asyncio.run(fabrique()), 200
    except HTTPException as e:
        return e.detail, e.status_code
    except TypeError as e:  # ancien code : signature sans `request`
        return "TypeError %s" % e, 500
    except Exception as e:  # noqa: BLE001
        return "500 %s: %s" % (type(e).__name__, e), 500


PII = ("email", "whatsapp", "birthday", "phone", "code", "coach_id", "notes")

# ============================================================================
# JEU DE DONNÉES
# ============================================================================
CODE_A = "AFR-MT6AAA"      # abonné d'Alice, coach A
CODE_B = "AFR-MT6BBB"      # abonné de Bob, coach B
CODE_COLL = "GROUPE-MT6"   # code collectif (sans assignedEmail), coach A


def base_neuve():
    db = BaseFictive()
    db.coaches.docs += [{"email": A}, {"email": B}]
    db.subscriptions.docs += [
        {"id": "sA", "code": CODE_A, "coach_id": A, "status": "active", "name": "Alice",
         "email": "alice@x.test", "remaining": 5},
        {"id": "sB", "code": CODE_B, "coach_id": B, "status": "active", "name": "Bob",
         "email": "bob@x.test", "remaining": 5},
    ]
    db.discount_codes.docs += [
        {"code": CODE_A, "coach_id": A, "active": True, "assignedEmail": "alice@x.test", "maxUses": 10, "used": 1},
        {"code": CODE_B, "coach_id": B, "active": True, "assignedEmail": "bob@x.test", "maxUses": 10, "used": 1},
        {"code": CODE_COLL, "coach_id": A, "active": True, "assignedEmail": "", "maxUses": 50, "used": 1,
         "name": "Groupe"},
    ]
    db.subscriber_infos.docs += [
        {"code": CODE_A, "coach_id": A, "name": "Alice Martin", "whatsapp": "+41765550001",
         "email": "alice@x.test", "birthday": "1990-04-02"},
        {"code": CODE_B, "coach_id": B, "name": "Bob Durand", "whatsapp": "+41765550002",
         "email": "bob@x.test", "birthday": "1985-12-24"},
        {"code": CODE_COLL, "coach_id": A, "name": "Premier Membre", "whatsapp": "+41765550003",
         "email": "premier@x.test", "birthday": "1970-01-01"},
    ]
    S.db = db
    return db


def fiche(db, code):
    for d in db.subscriber_infos.docs:
        if d.get("code") == code:
            return d
    return {}


GET = S.v294_get_subscriber_info
PUT = S.v294_put_subscriber_info


def get(code, req):
    return appel(lambda: GET(code, req))


def put(code, req):
    return appel(lambda: PUT(code, req))


def complet(r, attendu_email, attendu_wa):
    return isinstance(r, dict) and r.get("email") == attendu_email and r.get("whatsapp") == attendu_wa


def sans_pii(r):
    return isinstance(r, dict) and not any(r.get(k) for k in PII)


# ============================================================================
print("\n=== GET : abonné légitime (jeton de CE code) ===")
db = base_neuve()
r, c = get(CODE_A, Req(abonne=(CODE_A, "alice@x.test")))
verifier("abonné A + jeton de son code -> fiche complète (écran pré-rempli)",
         c == 200 and r.get("exists") is True and complet(r, "alice@x.test", "+41765550001")
         and r.get("birthday") == "1990-04-02" and r.get("name") == "Alice Martin", (c, r))
r, c = get(CODE_A.lower(), Req(abonne=(CODE_A, "alice@x.test")))
verifier("code en minuscules + jeton -> même fiche", c == 200 and complet(r, "alice@x.test", "+41765550001"), (c, r))

print("\n=== GET : anonyme qui connaît le code ===")
r, c = get(CODE_A, Req())
verifier("anonyme + code valide -> 200, exactement {exists, name}",
         c == 200 and isinstance(r, dict) and set(r.keys()) == {"exists", "name"}
         and r.get("exists") is True and r.get("name") == "Alice Martin", (c, r))
verifier("anonyme + code valide -> AUCUNE PII (email/whatsapp/birthday)", sans_pii(r), r)
r, c = get("AFR-INCONNU", Req())
verifier("anonyme + code inconnu -> exists False, aucune PII",
         c == 200 and r.get("exists") is False and sans_pii(r) and not r.get("name"), (c, r))
r, c = get(CODE_A, Req(abonne=(CODE_B, "bob@x.test")))
verifier("jeton abonné d'un AUTRE code -> traité comme anonyme (aucune PII)",
         c == 200 and sans_pii(r), (c, r))
r, c = get(CODE_A, Req(entete=A))
verifier("X-User-Email du coach A sans JWT -> jamais le chemin coach (aucune PII)",
         c in (200, 403, 404) and (c != 200 or sans_pii(r)), (c, r))
r, c = get(CODE_A, Req(entete=ADMIN))
verifier("X-User-Email d'un super-admin sans JWT -> aucune PII",
         c in (200, 403, 404) and (c != 200 or sans_pii(r)), (c, r))
r, c = get(CODE_COLL, Req(abonne=(CODE_COLL, "second@x.test")))
verifier("code collectif : jeton d'un AUTRE membre (autre e-mail) -> pas la PII du premier",
         c == 200 and sans_pii(r), (c, r))
r, c = get(CODE_COLL, Req(abonne=(CODE_COLL, "premier@x.test")))
verifier("code collectif : jeton du membre enregistré -> sa fiche",
         c == 200 and complet(r, "premier@x.test", "+41765550003"), (c, r))

print("\n=== GET : coachs (JWT signé + propriété) ===")
r, c = get(CODE_A, Req(A))
verifier("A lit son abonné -> 200 fiche complète", c == 200 and complet(r, "alice@x.test", "+41765550001"), (c, r))
r_ab, c_ab = get(CODE_B, Req(A))
r_in, c_in = get("AFR-INCONNU", Req(A))
verifier("A lit l'abonné de B -> 404", c_ab == 404, (c_ab, r_ab))
verifier("A : abonné de B et code inconnu -> réponses IDENTIQUES (aucun oracle)",
         (c_ab, r_ab) == (c_in, r_in), ((c_ab, r_ab), (c_in, r_in)))
r, c = get(CODE_A, Req(B))
verifier("B lit l'abonné de A -> 404", c == 404, (c, r))
r, c = get(CODE_B, Req(B))
verifier("B lit son abonné -> 200", c == 200 and complet(r, "bob@x.test", "+41765550002"), (c, r))
r, c = get(CODE_A, Req(B, entete=A))
verifier("JWT B + X-User-Email A -> reste B (404 sur l'abonné de A)", c == 404, (c, r))
for adm in (ADMIN,):
    r1, c1 = get(CODE_A, Req(adm))
    r2, c2 = get(CODE_B, Req(adm))
    verifier("super-admin %s -> global (A et B lisibles)" % adm,
             c1 == 200 and complet(r1, "alice@x.test", "+41765550001")
             and c2 == 200 and complet(r2, "bob@x.test", "+41765550002"), ((c1, r1), (c2, r2)))
verifier("SA-1 : un seul super-admin", SUPER_ADMIN_EMAILS == [ADMIN], SUPER_ADMIN_EMAILS)
for _code in (CODE_A, CODE_B):
    r, c = get(_code, Req(ANCIEN_SECOND))
    verifier("SA-1 : ancien second super-admin -> refusé (403/404), aucune PII sur %s" % _code,
             c in (403, 404) and "alice@x.test" not in str(r) and "bob@x.test" not in str(r), (c, r))
r, c = get(CODE_A, Req("inconnu.pas.coach@exemple.test"))
verifier("JWT signé d'un non-coach -> refusé (403/404), aucune PII", c in (403, 404), (c, r))
r, c = get(CODE_A, Req(B, abonne=(CODE_A, "alice@x.test")))
verifier("coach B qui est AUSSI porteur du jeton de CE code -> sa propre fiche (priorité abonné)",
         c == 200 and complet(r, "alice@x.test", "+41765550001"), (c, r))

print("\n=== PUT ===")
db = base_neuve()
r, c = put(CODE_A, Req(corps={"whatsapp": "+41000000000", "email": "pirate@x.test"}))
verifier("PUT anonyme (code seul) -> refusé 403", c == 403, (c, r))
verifier("PUT anonyme : fiche intacte", fiche(db, CODE_A).get("whatsapp") == "+41765550001"
         and fiche(db, CODE_A).get("email") == "alice@x.test", fiche(db, CODE_A))
r, c = put(CODE_A, Req(abonne=(CODE_B, "bob@x.test"), corps={"whatsapp": "+41000000000"}))
verifier("PUT avec jeton d'un AUTRE code -> 403, fiche intacte",
         c == 403 and fiche(db, CODE_A).get("whatsapp") == "+41765550001", (c, r))
r, c = put(CODE_A, Req(A, corps={"whatsapp": "+41000000000"}))
verifier("PUT avec JWT coach seul -> 403 (pas de chemin coach en écriture)",
         c == 403 and fiche(db, CODE_A).get("whatsapp") == "+41765550001", (c, r))
r, c = put(CODE_A, Req(abonne=(CODE_A, "alice@x.test"),
                       corps={"whatsapp": "+41761112233", "email": "autre@x.test", "name": "Alice M.",
                              "birthday": "1990-04-03", "coach_id": B, "code": CODE_B}))
f = fiche(db, CODE_A)
verifier("PUT abonné légitime -> 200", c == 200, (c, r))
verifier("PUT : liste blanche appliquée (whatsapp/name/birthday écrits)",
         f.get("whatsapp") == "+41761112233" and f.get("name") == "Alice M." and f.get("birthday") == "1990-04-03", f)
verifier("PUT : e-mail = celui du jeton, jamais celui du corps", f.get("email") == "alice@x.test", f)
verifier("PUT : coach_id/code du corps ignorés", f.get("coach_id") == A and f.get("code") == CODE_A, f)
r, c = put(CODE_COLL, Req(abonne=(CODE_COLL, "second@x.test"), corps={"whatsapp": "+41000000000"}))
verifier("PUT code collectif par un autre membre -> refusé, fiche du premier intacte",
         c in (403, 409) and fiche(db, CODE_COLL).get("whatsapp") == "+41765550003", (c, r))
r, c = put(CODE_A, Req(abonne=(CODE_A, "alice@x.test"), corps={"whatsapp": {"$ne": 1}, "name": "x" * 5000}))
f = fiche(db, CODE_A)
verifier("PUT : valeurs non-chaîne / trop longues ignorées (pas de 500)",
         c == 200 and f.get("whatsapp") == "+41761112233" and len(f.get("name") or "") <= 200, (c, f))
r, c = put(CODE_A, Req(abonne=(CODE_A, "alice@x.test"), corps={"whatsapp": ""}))
verifier("PUT : champ vide n'écrase jamais", c == 200 and fiche(db, CODE_A).get("whatsapp") == "+41761112233", (c, r))
# Nouvel abonné sans fiche : première écriture (upsert) par le porteur du jeton.
db.discount_codes.docs.append({"code": "AFR-NEUF01", "coach_id": B, "active": True,
                               "assignedEmail": "neuf@x.test", "maxUses": 5, "used": 0})
r, c = put("AFR-NEUF01", Req(abonne=("AFR-NEUF01", "neuf@x.test"),
                              corps={"name": "Neuf", "whatsapp": "+41790000009", "email": "neuf@x.test"}))
f = fiche(db, "AFR-NEUF01")
verifier("PUT : première fiche créée pour le porteur (coach_id du code)",
         c == 200 and f.get("whatsapp") == "+41790000009" and f.get("coach_id") == B and f.get("email") == "neuf@x.test",
         (c, f))

# ============================================================================
ok = sum(1 for _, v, _ in RESULTATS if v)
print("\n%d/%d verifications" % (ok, len(RESULTATS)))
sys.exit(0 if ok == len(RESULTATS) else 1)
