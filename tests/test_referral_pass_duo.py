#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V534 — PASS DUO (Centre Parrainage unique) : le banc autonome.

Ce que ce banc exécute : les VRAIES routes (`api/routes/referral_routes.py`),
le VRAI moteur pur (`referral_engine.py`), et les VRAIS moteurs qu'elles
appellent — ESSAI-4, ESSAI-1 (verrou `free_trial_claims`),
`_process_successful_payment`, LOT 1, T1, V393, LOT B2, SEANCES
(`seances_consommer`), M2-A, `_a0_code_depuis_qr` — sur un MongoDB EN MÉMOIRE
qui modélise ce dont ces moteurs dépendent : clés primaires `_id`, index
uniques partiels du contrat, `$regex`, `$in`, `$or`, `$expr` du plafond
SEANCES, `find_one_and_update` avec `upsert`.

Ce qui est REMPLACÉ par un mouchard, et pourquoi : les notifications (push,
e-mails Resend, notifier_reservation_creee) — elles parlent au réseau. Rien
d'autre. AUCUN réseau, AUCUN paiement, AUCUN e-mail, AUCUNE donnée réelle.

Lancement :  python3 tests/test_referral_pass_duo.py
"""
import ast
import asyncio
import io
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

SECRET_TEST = "secret-de-banc-v534-jamais-en-prod"
os.environ["JWT_SECRET"] = SECRET_TEST
os.environ.pop("RESEND_API_KEY", None)
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017/?serverSelectionTimeoutMS=1")
os.environ.setdefault("DB_NAME", "banc_v534")
os.environ["FRONTEND_URL"] = "https://afroboost.com"

import jwt as pyjwt  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

import api.server as S  # noqa: E402
import api.routes.checkout_routes as C  # noqa: E402
import api.routes.reservation_routes as RR  # noqa: E402
import api.routes.shared as SH  # noqa: E402
import api.routes.referral_engine as E  # noqa: E402
import api.routes.referral_routes as R  # noqa: E402

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


# ═══════════════════════════════════════════════════════════════════════════
# Faux MongoDB en mémoire
# ═══════════════════════════════════════════════════════════════════════════
class DuplicateKeyError(Exception):
    code = 11000

    def __init__(self, quoi=""):
        Exception.__init__(self, "E11000 duplicate key error %s" % quoi)


_ABSENT = object()


def _lire(doc, cle):
    cur = doc
    for part in str(cle).split("."):
        if not isinstance(cur, dict) or part not in cur:
            return _ABSENT
        cur = cur[part]
    return cur


def _ecrire(doc, cle, valeur):
    parts = str(cle).split(".")
    cur = doc
    for p in parts[:-1]:
        if not isinstance(cur.get(p), dict):
            cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = valeur


def _retirer(doc, cle):
    parts = str(cle).split(".")
    cur = doc
    for p in parts[:-1]:
        cur = cur.get(p) if isinstance(cur, dict) else None
        if cur is None:
            return
    if isinstance(cur, dict):
        cur.pop(parts[-1], None)


def _expr(doc, e):
    if isinstance(e, str) and e.startswith("$"):
        v = _lire(doc, e[1:])
        return None if v is _ABSENT else v
    if isinstance(e, dict):
        (op, args), = e.items()
        if op == "$ifNull":
            v = _expr(doc, args[0])
            return args[1] if v is None else v
        if op == "$add":
            return sum(_expr(doc, a) or 0 for a in args)
        if op == "$lte":
            return _expr(doc, args[0]) <= _expr(doc, args[1])
        if op == "$gte":
            return _expr(doc, args[0]) >= _expr(doc, args[1])
        raise AssertionError("$expr non simulé : %s" % op)
    return e


def _cmp(valeur, op, arg):
    import re as _re
    if op == "$in":
        return valeur is not _ABSENT and valeur in arg
    if op == "$nin":
        return valeur is _ABSENT or valeur not in arg
    if op == "$ne":
        return (valeur is _ABSENT and arg is not None) or (valeur is not _ABSENT and valeur != arg)
    if op == "$exists":
        return (valeur is not _ABSENT) == bool(arg)
    if op == "$type":
        return valeur is not _ABSENT and (arg == "string" and isinstance(valeur, str))
    if op == "$regex":
        return isinstance(valeur, str) and _re.search(arg, valeur, _re.I) is not None
    if op == "$options":
        return True
    if valeur is _ABSENT or valeur is None:
        return False
    if op == "$gte":
        return valeur >= arg
    if op == "$gt":
        return valeur > arg
    if op == "$lte":
        return valeur <= arg
    if op == "$lt":
        return valeur < arg
    raise AssertionError("opérateur non simulé : %s" % op)


def _match(doc, q):
    for cle, attendu in (q or {}).items():
        if cle == "$or":
            if not any(_match(doc, s) for s in attendu):
                return False
            continue
        if cle == "$and":
            if not all(_match(doc, s) for s in attendu):
                return False
            continue
        if cle == "$expr":
            if not _expr(doc, attendu):
                return False
            continue
        valeur = _lire(doc, cle)
        if isinstance(attendu, dict) and any(str(k).startswith("$") for k in attendu):
            if not all(_cmp(valeur, op, arg) for op, arg in attendu.items()):
                return False
        elif attendu is None:
            if valeur is not _ABSENT and valeur is not None:
                return False
        else:
            if valeur is _ABSENT or valeur != attendu:
                return False
    return True


def _projeter(doc, proj):
    if not proj:
        return json.loads(json.dumps(doc, default=str))
    gardees = [k for k, v in proj.items() if v and k != "_id"]
    d = json.loads(json.dumps(doc, default=str))
    if not gardees:
        d.pop("_id", None)
        return d
    return {k: d[k] for k in gardees if k in d}


class _Curseur:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, cle, sens=1):
        if isinstance(cle, list):
            for c, s in reversed(cle):
                self._docs.sort(key=lambda d: str(d.get(c) or ""), reverse=(s == -1))
        else:
            self._docs.sort(key=lambda d: str(d.get(cle) or ""), reverse=(sens == -1))
        return self

    def skip(self, n):
        self._docs = self._docs[n:]
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, n=None):
        await asyncio.sleep(0)
        return self._docs[:n] if n else list(self._docs)

    def __aiter__(self):
        self._it = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _Coll:
    def __init__(self, nom, uniques=None):
        self.nom = nom
        self.docs = []
        # [(cles, filtre_partiel)] — les index uniques modélisés
        self.uniques = list(uniques or [])
        self.ecritures = 0

    def _verifier_uniques(self, doc, sauf=None):
        if "_id" in doc and any(d is not sauf and d.get("_id") == doc["_id"] for d in self.docs):
            raise DuplicateKeyError("_id")
        for cles, partiel in self.uniques:
            if partiel and not _match(doc, partiel):
                continue
            tuple_doc = tuple(_lire(doc, c) for c in cles)
            if any(v is _ABSENT for v in tuple_doc):
                continue
            for autre in self.docs:
                if autre is sauf:
                    continue
                if partiel and not _match(autre, partiel):
                    continue
                if tuple(_lire(autre, c) for c in cles) == tuple_doc:
                    raise DuplicateKeyError("+".join(cles))

    def find(self, q=None, proj=None, **k):
        return _Curseur([_projeter(d, proj) for d in self.docs if _match(d, q)])

    async def find_one(self, q=None, proj=None, **k):
        await asyncio.sleep(0)
        for d in self.docs:
            if _match(d, q):
                return _projeter(d, proj)
        return None

    async def count_documents(self, q=None, **k):
        return sum(1 for d in self.docs if _match(d, q))

    async def insert_one(self, doc, **k):
        await asyncio.sleep(0)
        d = json.loads(json.dumps(doc, default=str))
        self._verifier_uniques(d)
        self.docs.append(d)
        self.ecritures += 1
        return type("R", (), {"inserted_id": d.get("_id") or d.get("id")})()

    async def insert_many(self, docs, **k):
        for d in docs:
            await self.insert_one(d)

    def _appliquer(self, d, maj):
        for cle, v in (maj.get("$set") or {}).items():
            _ecrire(d, cle, json.loads(json.dumps(v, default=str)))
        for cle in (maj.get("$unset") or {}):
            _retirer(d, cle)
        for cle, v in (maj.get("$inc") or {}).items():
            cur = _lire(d, cle)
            _ecrire(d, cle, (0 if cur is _ABSENT or cur is None else cur) + v)
        for cle, v in (maj.get("$push") or {}).items():
            cur = _lire(d, cle)
            lst = list(cur) if isinstance(cur, list) else []
            lst.append(json.loads(json.dumps(v, default=str)))
            _ecrire(d, cle, lst)

    async def update_one(self, q, maj, upsert=False, **k):
        await asyncio.sleep(0)
        for d in self.docs:
            if _match(d, q):
                avant = json.loads(json.dumps(d, default=str))
                self._appliquer(d, maj)
                try:
                    self._verifier_uniques(d, sauf=d)
                except DuplicateKeyError:
                    d.clear()
                    d.update(avant)
                    raise
                self.ecritures += 1
                return type("R", (), {"matched_count": 1, "modified_count": 1})()
        if upsert:
            d = {k_: v for k_, v in q.items() if not str(k_).startswith("$") and not isinstance(v, dict)}
            self._appliquer(d, {"$set": dict(maj.get("$setOnInsert") or {}, **(maj.get("$set") or {})),
                                "$inc": maj.get("$inc") or {}})
            self._verifier_uniques(d)
            self.docs.append(d)
            self.ecritures += 1
            return type("R", (), {"matched_count": 0, "modified_count": 0, "upserted_id": d.get("_id")})()
        return type("R", (), {"matched_count": 0, "modified_count": 0})()

    async def update_many(self, q, maj, **k):
        n = 0
        for d in self.docs:
            if _match(d, q):
                self._appliquer(d, maj)
                n += 1
        return type("R", (), {"modified_count": n})()

    async def find_one_and_update(self, q, maj, projection=None, return_document=None,
                                  upsert=False, **k):
        await asyncio.sleep(0)
        for d in self.docs:
            if _match(d, q):
                avant = _projeter(d, projection)
                self._appliquer(d, maj)
                self.ecritures += 1
                return _projeter(d, projection) if return_document else avant
        if upsert:
            # Comme MongoDB : le document naît des égalités du filtre + $set ;
            # une collision de `_id` est un E11000.
            d = {k_: v for k_, v in q.items() if not isinstance(v, dict)}
            self._appliquer(d, {"$set": maj.get("$set") or {}})
            self._verifier_uniques(d)
            self.docs.append(d)
            self.ecritures += 1
            return None
        return None

    async def delete_one(self, q, **k):
        for i, d in enumerate(self.docs):
            if _match(d, q):
                del self.docs[i]
                return type("R", (), {"deleted_count": 1})()
        return type("R", (), {"deleted_count": 0})()

    async def find_one_and_delete(self, q, **k):
        for i, d in enumerate(self.docs):
            if _match(d, q):
                return self.docs.pop(i)
        return None

    def aggregate(self, *a, **k):
        return _Curseur([])

    async def create_index(self, *a, **k):
        return None


class _Base:
    """`db["x"]` et `db.x` ; PAS de `client` : les transactions sont
    indisponibles, le repli propre de `_avec_session` est donc ce qui tourne."""

    def __init__(self):
        self._c = {}
        self._c["free_trial_claims"] = _Coll("free_trial_claims")
        self._c["seance_mouvements"] = _Coll("seance_mouvements")
        self._c["referral_passes"] = _Coll("referral_passes", uniques=[
            (("id",), None),
            (("share_token",), None),
            (("sponsor.email_norm", "course_id", "occurrence"),
             {"status": {"$in": list(E.ETATS_ACTIFS)}}),
            (("invitee.email_norm", "course_id", "occurrence"),
             {"invitee.email_norm": {"$type": "string"}}),
        ])

    def __getitem__(self, nom):
        return self._c.setdefault(nom, _Coll(nom))

    def __getattr__(self, nom):
        if nom.startswith("_"):
            raise AttributeError(nom)
        return self[nom]


class _Client:
    host = "203.0.113.7"


class _Entetes(dict):
    def get(self, cle, defaut=""):
        for k, v in self.items():
            if k.lower() == str(cle).lower():
                return v
        return defaut


class Requete:
    def __init__(self, corps=None, entetes=None, params=None, ip=None):
        self.headers = _Entetes(entetes or {})
        self.query_params = params or {}
        self._corps = corps if corps is not None else {}
        self.client = _Client()
        if ip:
            self.client.host = ip

    async def json(self):
        return self._corps


# ═══════════════════════════════════════════════════════════════════════════
# Outils du banc
# ═══════════════════════════════════════════════════════════════════════════
ADMIN = S.SUPER_ADMIN_EMAILS[0]
PARRAIN_EMAIL = "lea.parrain@exemple.test"
PARRAIN_CODE = "BASS-DUO-01"
AMI_EMAIL = "noe.ami@exemple.test"
AMI_TEL = "+41 76 511 22 33"
PARRAIN_TEL = "+41 79 200 30 40"
COURS_DUO = "cours-duo-0001"
COURS_NON_DUO = "cours-sans-duo"
COURS_CACHE = "cours-duo-cache"
OFFRE_ESSAI = "offre-essai-0"

MOUCHARDS = {"push": [], "email_parrain": [], "notif_resa": [], "seances": [],
             "ordre": [], "paiements": []}

_ORIG_SEANCES_CONSOMMER = SH.seances_consommer
_ORIG_ESSAI1_GARDE = C._essai1_garde
_ORIG_PSP = C._process_successful_payment


async def _mouchard_push(email, titre, corps, data):
    MOUCHARDS["push"].append({"email": email, "titre": titre, "data": data})


async def _mouchard_email(pass_doc):
    MOUCHARDS["email_parrain"].append(pass_doc.get("id"))
    return True


async def _mouchard_notif(reservation, subscription):
    MOUCHARDS["notif_resa"].append(reservation.get("id"))


async def _mouchard_seances(db, code, quantite, reservation_id=None, source="", session=None):
    MOUCHARDS["seances"].append({"code": code, "q": quantite, "rid": reservation_id, "source": source})
    return await _ORIG_SEANCES_CONSOMMER(db, code, quantite, reservation_id=reservation_id,
                                        source=source, session=session)


async def _mouchard_essai1_garde(*a, **k):
    MOUCHARDS["ordre"].append("_essai1_garde")
    return await _ORIG_ESSAI1_GARDE(*a, **k)


async def _mouchard_psp(**k):
    MOUCHARDS["ordre"].append("_process_successful_payment")
    MOUCHARDS["paiements"].append(k)
    return await _ORIG_PSP(**k)


def poser_mouchards():
    for v in MOUCHARDS.values():
        v[:] = []
    R._push_parrain = _mouchard_push
    R._email_parrain_debloque = _mouchard_email
    R._notifier_reservation = _mouchard_notif
    SH.seances_consommer = _mouchard_seances
    C._essai1_garde = _mouchard_essai1_garde
    C._process_successful_payment = _mouchard_psp


def _prochaine_occurrence(jours=1, heure="18:30"):
    """L'ISO naïf de « dans N jours à HH:MM » (heure suisse), ET le weekday JS."""
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Europe/Zurich")).replace(tzinfo=None)
    except Exception:
        now = datetime.utcnow() + timedelta(hours=2)
    jour = (now + timedelta(days=jours)).date()
    h, m = [int(x) for x in heure.split(":")]
    dt = datetime(jour.year, jour.month, jour.day, h, m)
    return dt.strftime("%Y-%m-%dT%H:%M:%S"), (jour.weekday() + 1) % 7


def base_de_depart(drapeau=True, seances_parrain=3):
    base = _Base()
    occ, wd = _prochaine_occurrence(1)
    base["feature_flags"].docs.append({"id": "feature_flags", "parrainage_duo_enabled": drapeau})
    base["courses"].docs += [
        {"id": COURS_DUO, "name": "Afro Cardio", "weekday": wd, "time": "18:30",
         "locationName": "Salle Nord", "mapsUrl": "https://maps.example/x", "visible": True,
         "archived": False, "duo_enabled": True, "coach_id": None},
        {"id": COURS_NON_DUO, "name": "Sans Duo", "weekday": wd, "time": "19:30",
         "locationName": "Salle Sud", "visible": True, "archived": False},
        {"id": COURS_CACHE, "name": "Duo caché", "weekday": wd, "time": "20:30",
         "locationName": "Salle Est", "visible": False, "archived": False, "duo_enabled": True},
        {"id": "cours-duo-archive", "name": "Duo archivé", "weekday": wd, "time": "21:30",
         "locationName": "Salle Ouest", "visible": True, "archived": True, "duo_enabled": True},
    ]
    base["offers"].docs.append({"id": OFFRE_ESSAI, "name": "Essai gratuit", "price": 0.0,
                                "visible": True, "coach_id": None,
                                "linked_course_ids": [COURS_DUO]})
    # Le parrain : un forfait payant vivant + sa fiche code.
    dans_3_mois = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()
    base["subscriptions"].docs.append({
        "id": "sub-parrain", "code": PARRAIN_CODE, "email": PARRAIN_EMAIL, "name": "Léa Parrain",
        "whatsapp": PARRAIN_TEL, "offer_name": "Pack 10", "offer_id": "pack-10",
        "total_sessions": 10, "used_sessions": 10 - seances_parrain,
        "remaining_sessions": seances_parrain, "expires_at": dans_3_mois, "status": "active",
        "coach_id": "", "payment_method": "card", "total_paid": 250,
    })
    base["discount_codes"].docs.append({
        "id": "code-parrain", "code": PARRAIN_CODE, "name": "Léa Parrain", "assignedEmail": PARRAIN_EMAIL,
        "active": True, "maxUses": 10, "used": 10 - seances_parrain, "coach_id": "",
        "payment_method": "card", "total_paid": 250, "stripe_amount": 250,
    })
    for module in (S, C, RR):
        module.db = base
    R.init_db(base)
    poser_mouchards()
    return base, occ


def jeton_espace(base, code=PARRAIN_CODE, email=PARRAIN_EMAIL, coach_id=""):
    tok, jti = SH.lotb3s1_make_token(code, email, coach_id)
    base["subscriber_sessions"].docs.append({
        "jti": jti, "code": code.upper(), "email": email.lower(), "coach_id": coach_id,
        "slug": None, "revoked": False,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()})
    return tok


def jeton_admin(email=ADMIN):
    now = datetime.now(timezone.utc)
    return pyjwt.encode({"email": email, "type": "coach", "iat": int(now.timestamp()),
                         "exp": int(now.timestamp()) + 3600}, SECRET_TEST, algorithm="HS256")


def req_parrain(base, corps=None, params=None, tok=None):
    return Requete(corps, {"x-espace-token": tok or jeton_espace(base)}, params)


async def appel(coro):
    """(code_http, corps) — une route peut rendre un dict, une JSONResponse ou lever."""
    try:
        r = await coro
    except HTTPException as e:
        return e.status_code, {"detail": e.detail, "headers": dict(e.headers or {})}
    if isinstance(r, JSONResponse):
        return r.status_code, json.loads(r.body.decode("utf-8"))
    return 200, r


def corps_ami(email=AMI_EMAIL, tel=AMI_TEL, nom="Noé Ami", **extra):
    d = {"name": nom, "email": email, "whatsapp": tel, "consent_reservation": True,
         "terms_accepted": True, "marketing_consent": False}
    d.update(extra)
    return d


async def creer_pass(base, occ, tok=None):
    code, dto = await appel(R.referral_creer_pass(
        req_parrain(base, {"course_id": COURS_DUO, "occurrence": occ, "terms_accepted": True}, tok=tok)))
    return code, dto


# ═══════════════════════════════════════════════════════════════════════════
# Les scénarios
# ═══════════════════════════════════════════════════════════════════════════
async def principal():
    # ── 1. création d'un Pass autorisée ────────────────────────────────────
    base, occ = base_de_depart()
    code, dto = await creer_pass(base, occ)
    verifier("1. Création d'un Pass : 201", code == 201, str(dto)[:120])
    verifier("1b. PassDTO : status locked, invite_url /duo/<token>, texte WhatsApp sans emoji",
             dto.get("status") == "locked" and dto.get("invite_url", "").startswith("https://afroboost.com/duo/")
             and dto.get("share_token") and all(ord(ch) < 0x2600 for ch in dto.get("whatsapp_text", ""))
             and dto["invite_url"] in dto.get("whatsapp_text", ""),
             str({k: dto.get(k) for k in ("status", "invite_url", "whatsapp_text")})[:200])
    verifier("1c. Le pass est persisté avec sponsor.email_norm / subscription_code / expires_at = occurrence",
             len(base["referral_passes"].docs) == 1
             and base["referral_passes"].docs[0]["sponsor"]["email_norm"] == PARRAIN_EMAIL
             and base["referral_passes"].docs[0]["sponsor"]["subscription_code"] == PARRAIN_CODE
             and base["referral_passes"].docs[0]["expires_at"] == occ)
    verifier("1d. Le DTO du parrain ne porte ni e-mail ni téléphone de personne",
             not E.contient_pii(dto), str(E.contient_pii(dto)))
    code2, dto2 = await creer_pass(base, occ)
    verifier("1e. Re-création sur la même occurrence : 200 deja_existant, aucun doublon",
             code2 == 200 and dto2.get("deja_existant") is True and dto2["id"] == dto["id"]
             and len(base["referral_passes"].docs) == 1, str((code2, dto2.get("deja_existant"))))
    codei, inv = await appel(R.referral_invitation(req_parrain(base, {"pass_id": dto["id"], "channel": "whatsapp"})))
    verifier("1f. Invitation journalisée : 201, le pass passe en waiting",
             codei == 201 and inv.get("id") and base["referral_passes"].docs[0]["status"] == "waiting"
             and len(base["referral_invitations"].docs) == 1, str((codei, inv)))
    codex, _ = await appel(R.referral_invitation(req_parrain(base, {"pass_id": dto["id"], "channel": "pigeon"})))
    verifier("1g. Canal inconnu refusé (400)", codex == 400)
    code_me, me = await appel(R.referral_me(req_parrain(base)))
    verifier("1h. GET /me : sponsor.first_name, stats.invited=1, 1 pass, 1 invitation, historique",
             code_me == 200 and me["sponsor"]["first_name"] == "Léa" and me["sponsor"]["code"] == PARRAIN_CODE
             and me["stats"]["invited"] == 1 and len(me["passes"]) == 1 and len(me["invitations"]) == 1
             and any(h["type"] == "invitation_sent" for h in me["history"]), str(me.get("stats")))
    verifier("1i. Débit par IP : la 21e création depuis la même adresse répond 429",
             await _debit_429(base, occ))

    # ── 2. cours non duo_enabled -> 400 ────────────────────────────────────
    base, occ = base_de_depart()
    code, dto = await appel(R.referral_creer_pass(req_parrain(base, {"course_id": COURS_NON_DUO, "occurrence": occ})))
    verifier("2. Cours sans duo_enabled : 400, rien d'écrit", code == 400 and not base["referral_passes"].docs, str(code))
    code, _ = await appel(R.referral_creer_pass(req_parrain(base, {"course_id": COURS_CACHE, "occurrence": occ})))
    verifier("2b. Cours duo mais invisible : 400", code == 400)
    code, _ = await appel(R.referral_creer_pass(req_parrain(base, {"course_id": COURS_DUO, "occurrence": "2020-01-01T18:30:00"})))
    verifier("2c. Occurrence hors des dates proposées : 400", code == 400)
    code, _ = await appel(R.referral_creer_pass(Requete({"course_id": COURS_DUO, "occurrence": occ},
                                                        {"X-User-Email": ADMIN})))
    verifier("2d. X-User-Email seul n'identifie PAS un parrain : 403", code == 403, str(code))

    # ── 3. auto-parrainage refusé : e-mail, puis téléphone ─────────────────
    base, occ = base_de_depart()
    _, dto = await creer_pass(base, occ)
    tok = dto["share_token"]
    code, rep = await appel(R.referral_join(tok, Requete(corps_ami(email=PARRAIN_EMAIL.upper(), tel="+41 76 000 00 00"))))
    verifier("3. Auto-parrainage par e-mail (casse différente) : 409 auto_parrainage",
             code == 409 and rep["headers"].get("X-Refus-Raison") == "auto_parrainage", str((code, rep)))
    code, rep = await appel(R.referral_join(tok, Requete(corps_ami(email="autre.adresse@exemple.test", tel="0792003040"))))
    verifier("3b. Auto-parrainage par téléphone (autre e-mail, même numéro) : 409 auto_parrainage",
             code == 409 and rep["headers"].get("X-Refus-Raison") == "auto_parrainage", str((code, rep)))
    verifier("3c. Aucun essai octroyé, aucun verrou posé, pass toujours sans invité",
             not MOUCHARDS["paiements"] and not base["free_trial_claims"].docs
             and base["referral_passes"].docs[0]["invitee"] is None)

    # ── 8/9 (d'abord) : le parcours nominal complet ────────────────────────
    base, occ = base_de_depart(seances_parrain=3)
    _, dto = await creer_pass(base, occ)
    tok = dto["share_token"]
    code_pub, pub = await appel(R.referral_pass_public(tok))
    code, rep = await appel(R.referral_join(tok, Requete(corps_ami())))
    verifier("8. Join nominal : 200, status unlocked, 2 billets (sponsor + invitee)",
             code == 200 and rep.get("status") == "unlocked" and len(rep.get("tickets", [])) == 2
             and {t["role"] for t in rep["tickets"]} == {"sponsor", "invitee"}, str((code, rep))[:300])
    resas = [r for r in base["reservations"].docs if r.get("pass_id")]
    verifier("8b. Deux documents `reservations` portent pass_id / pass_role / source pass_duo / datetime = occurrence",
             len(resas) == 2 and {r["pass_role"] for r in resas} == {"sponsor", "invitee"}
             and all(r["source"] == "pass_duo" and r["datetime"] == occ and r["courseId"] == COURS_DUO for r in resas)
             and all(r["pass_id"] == dto["id"] for r in resas), str([(r.get("pass_role"), r.get("source")) for r in resas]))
    verifier("8c. `seances_consommer` appelé exactement une fois PAR réservation (2), clé = id de la réservation, source pass_duo",
             len(MOUCHARDS["seances"]) == 2 and {m["rid"] for m in MOUCHARDS["seances"]} == {r["id"] for r in resas}
             and all(m["source"] == "pass_duo" and m["q"] == 1 for m in MOUCHARDS["seances"]),
             str(MOUCHARDS["seances"]))
    sub_p = base["subscriptions"].find_one and [d for d in base["subscriptions"].docs if d["code"] == PARRAIN_CODE][0]
    code_p = [d for d in base["discount_codes"].docs if d["code"] == PARRAIN_CODE][0]
    verifier("8d. Le parrain a été débité d'UNE séance, des deux côtés (forfait 3->2, code used 7->8)",
             sub_p["remaining_sessions"] == 2 and sub_p["used_sessions"] == 8 and code_p["used"] == 8,
             str((sub_p["remaining_sessions"], code_p["used"])))
    essais = [d for d in base["discount_codes"].docs if d.get("assignedEmail") == AMI_EMAIL]
    sub_ami = [d for d in base["subscriptions"].docs if d.get("email") == AMI_EMAIL]
    verifier("8e. L'ami a un code AFR- gratuit (payment_method free, total 0) + forfait 1 séance, débité à 0, marqués pass_duo",
             len(essais) == 1 and essais[0]["code"].startswith("AFR-") and essais[0]["payment_method"] == "free"
             and essais[0]["total_paid"] == 0 and essais[0].get("pass_duo_id") == dto["id"]
             and essais[0]["used"] == 1 and len(sub_ami) == 1 and sub_ami[0]["remaining_sessions"] == 0
             and sub_ami[0].get("acquisition_source") == "pass_duo" and sub_ami[0].get("source") == "checkout_vitrine",
             str((essais[0].get("code") if essais else None, sub_ami[0].get("remaining_sessions") if sub_ami else None)))
    verifier("8f. Le forfait de l'ami est bien reconnu comme un ESSAI par la règle unique (essai6_verdict)",
             essais and SH.essai6_verdict(essais[0], sub_ami[0], None))
    verifier("8g. Le verrou ESSAI-1 est posé sur l'adresse ET le numéro de l'ami",
             {d["_id"] for d in base["free_trial_claims"].docs} == {"trial:" + AMI_EMAIL, "trialtel:41765112233"},
             str([d["_id"] for d in base["free_trial_claims"].docs]))
    verifier("8h. M2-A : la source `parrainage` est sur le forfait de l'ami et sur sa réservation",
             sub_ami and (sub_ami[0].get("attribution") or {}).get("first", {}).get("source") == "parrainage"
             and any((r.get("attribution") or {}).get("first", {}).get("source") == "parrainage"
                     for r in resas if r["pass_role"] == "invitee"),
             str((sub_ami[0].get("attribution") if sub_ami else None)))
    verifier("8i. `parrainage` est dans M2A_SOURCES (et attribution.js — banc test_tracking_sources)",
             "parrainage" in SH.M2A_SOURCES)
    p = base["referral_passes"].docs[0]
    verifier("8j. Le pass : unlocked, unlocked_at posé, reservations.{sponsor,invitee}_{id,code} remplis, invitee_access_code = AFR-",
             p["status"] == "unlocked" and p["unlocked_at"] and all(p["reservations"].values())
             and p["invitee_access_code"] == essais[0]["code"] and p["blocked_reason"] is None,
             str(p["reservations"]))
    verifier("8k. Notifications : push parrain « débloqué » + e-mail parrain + notifications de réservation (2, une par billet)",
             any(m["data"].get("type") == "pass_duo_unlocked" and m["email"] == PARRAIN_EMAIL for m in MOUCHARDS["push"])
             and MOUCHARDS["email_parrain"] == [dto["id"]] and len(MOUCHARDS["notif_resa"]) == 2,
             str((MOUCHARDS["push"], MOUCHARDS["email_parrain"], MOUCHARDS["notif_resa"])))
    verifier("8l. Ordre réel des appels : _essai1_garde AVANT _process_successful_payment (mouchard)",
             MOUCHARDS["ordre"] == ["_essai1_garde", "_process_successful_payment"], str(MOUCHARDS["ordre"]))
    verifier("8m. Le join a d'abord ouvert le lien : opened_at posé (waiting) avant l'inscription",
             code_pub == 200 and p.get("opened_at") and pub.get("status") == "waiting", str(pub))

    # ── 9. deux QR réels, distincts, lus par le scanner ────────────────────
    qrs = [t["qr_value"] for t in rep["tickets"]]
    codes_lus = [RR._a0_code_depuis_qr(q) for q in qrs]
    verifier("9. Deux qr_value distincts, au format URL `?res=` (jamais AFROBOOST:, jamais ?code=)",
             len(set(qrs)) == 2 and all(q.startswith("https://afroboost.com/chat?res=AF") for q in qrs)
             and not any("AFROBOOST:" in q or "code=" in q for q in qrs), str(qrs))
    verifier("9b. `_a0_code_depuis_qr` rend les deux reservationCode -> CAS A trouve chaque réservation",
             sorted(codes_lus) == sorted(t["reservationCode"] for t in rep["tickets"])
             and all([await base["reservations"].find_one({"reservationCode": c}) for c in codes_lus]),
             str(codes_lus))
    verifier("9c. Les billets ne portent ni e-mail, ni code d'accès AFR-, ni téléphone",
             not E.contient_pii(rep) and not any("AFR-" in json.dumps(t) for t in rep["tickets"]),
             str(E.contient_pii(rep)))

    # ── 6. double join idempotent ──────────────────────────────────────────
    n_paiements, n_resas = len(MOUCHARDS["paiements"]), len(base["reservations"].docs)
    code, rep2 = await appel(R.referral_join(tok, Requete(corps_ami(email=AMI_EMAIL.upper()))))
    verifier("6. Même filleul une 2e fois : 200, même état, AUCUN nouvel octroi ni réservation",
             code == 200 and rep2.get("status") == "unlocked" and len(rep2["tickets"]) == 2
             and len(MOUCHARDS["paiements"]) == n_paiements and len(base["reservations"].docs) == n_resas,
             str((code, len(MOUCHARDS["paiements"]), len(base["reservations"].docs))))
    code, rep3 = await appel(R.referral_join(tok, Requete(corps_ami(email="tiers@exemple.test", tel="+41 76 999 88 77"))))
    verifier("6b. Un TIERS sur un pass déjà pourvu : 409 pass_ferme", code == 409 and rep3["headers"].get("X-Refus-Raison") == "pass_ferme")

    # ── 11 (partie unlocked) : annulation impossible depuis unlocked ───────
    code, rep = await appel(R.referral_annuler(dto["id"], req_parrain(base)))
    verifier("11b. cancel depuis unlocked : 409, le pass reste unlocked",
             code == 409 and base["referral_passes"].docs[0]["status"] == "unlocked", str(code))

    # ── 12. admin (JWT signé) sur ce jeu de données ────────────────────────
    code, _ = await appel(R.referral_admin_summary(Requete(params={})))
    verifier("12. /admin/summary sans jeton : 403", code == 403, str(code))
    code, _ = await appel(R.referral_admin_summary(Requete(params={}, entetes={"X-User-Email": ADMIN})))
    verifier("12b. /admin/summary avec X-User-Email seul (falsifiable) : 403", code == 403, str(code))
    code, _ = await appel(R.referral_admin_summary(Requete(params={}, entetes={"Authorization": "Bearer " + jeton_espace(base)})))
    verifier("12c. /admin/summary avec un jeton ABONNÉ : 403", code == 403, str(code))
    code, kpi = await appel(R.referral_admin_summary(Requete(params={}, entetes={"Authorization": "Bearer " + jeton_admin()})))
    verifier("12d. /admin/summary avec JWT admin signé : 200, 9 KPI + par_canal",
             code == 200 and set(kpi["kpi"]) == {"passes_crees", "invitations", "ouvertures", "inscriptions", "debloques",
                                                  "utilises", "expires", "annules", "presences_duo"}
             and set(kpi["par_canal"]) == {"whatsapp", "copy", "qr", "share"}
             and kpi["kpi"]["passes_crees"] == 1 and kpi["kpi"]["inscriptions"] == 1 and kpi["kpi"]["debloques"] == 1
             and kpi["kpi"]["ouvertures"] == 1, str(kpi))
    code, page = await appel(R.referral_admin_passes(Requete(params={"page": "1"}, entetes={"Authorization": "Bearer " + jeton_admin()})))
    verifier("12e. /admin/passes : 200, pagination 50, PassAdminDTO avec e-mails (admin seulement)",
             code == 200 and page["per_page"] == 50 and page["total"] == 1
             and page["items"][0]["sponsor"]["email"] == PARRAIN_EMAIL and page["items"][0]["invitee"]["email"] == AMI_EMAIL,
             str(page)[:200])
    code, _ = await appel(R.referral_admin_passes(Requete(params={}, entetes={"Authorization": "Bearer " + jeton_admin("inconnu@exemple.test")})))
    verifier("12f. Un JWT signé d'un NON-coach : 403", code == 403, str(code))

    # ── used : dérivé en lecture quand les deux présences sont validées ────
    for r in base["reservations"].docs:
        if r.get("pass_id"):
            r["validated"] = True
    code, me = await appel(R.referral_me(req_parrain(base)))
    verifier("8n. Deux présences validées -> statut `used` dérivé en lecture ET persisté",
             me["passes"][0]["status"] == "used" and base["referral_passes"].docs[0]["status"] == "used"
             and me["passes"][0]["status_label"] == "Participation validée", str(me["passes"][0]["status"]))
    code, kpi = await appel(R.referral_admin_summary(Requete(params={}, entetes={"Authorization": "Bearer " + jeton_admin()})))
    verifier("12g. KPI : utilises=1, presences_duo=2 après validation", kpi["kpi"]["utilises"] == 1 and kpi["kpi"]["presences_duo"] == 2, str(kpi["kpi"]))

    # ── 5. deuxième essai refusé : garde AVANT octroi (mouchard + AST) ─────
    base, occ = base_de_depart()
    _, dto = await creer_pass(base, occ)
    # L'ami a DÉJÀ consommé un essai : code gratuit + présence validée.
    base["discount_codes"].docs.append({"id": "ancien", "code": "AFR-ANCIEN", "assignedEmail": AMI_EMAIL,
                                        "payment_method": "free", "total_paid": 0, "active": True,
                                        "maxUses": 1, "used": 1, "coach_id": ""})
    base["subscriptions"].docs.append({"id": "sub-ancien", "code": "AFR-ANCIEN", "email": AMI_EMAIL,
                                       "whatsapp": AMI_TEL,   # le numéro, tel que V251 l'écrit sur le forfait
                                       "status": "completed", "remaining_sessions": 0, "used_sessions": 1,
                                       "total_sessions": 1, "coach_id": "", "offer_id": OFFRE_ESSAI})
    base["reservations"].docs.append({"id": "resa-ancienne", "promoCode": "AFR-ANCIEN", "validated": True,
                                      "userEmail": AMI_EMAIL, "validatedAt": "2026-08-01T18:30:00"})
    code, rep = await appel(R.referral_join(dto["share_token"], Requete(corps_ami())))
    verifier("5. Second essai : 409 free_trial_already_used", code == 409 and rep["headers"].get("X-Refus-Raison") == "free_trial_already_used", str((code, rep)))
    verifier("5b. Mouchard : `_essai1_garde` appelée, `_process_successful_payment` JAMAIS",
             MOUCHARDS["ordre"] == ["_essai1_garde"], str(MOUCHARDS["ordre"]))
    verifier("5c. Le pass est rouvert (invitee None), aucune réservation, aucun forfait créé",
             base["referral_passes"].docs[0]["invitee"] is None and not base["reservations"].docs[1:]
             and len(base["subscriptions"].docs) == 2)
    ordre_ast = _ordre_ast()
    verifier("5d. AST de referral_join : _essai4_garde < _essai1_garde < _process_successful_payment < réservation < notifications",
             ordre_ast["_essai4_garde"] < ordre_ast["_essai1_garde"] < ordre_ast["_process_successful_payment"]
             < ordre_ast["_reserver_seance_duo"] < ordre_ast["_debloquer_ou_bloquer"], str(ordre_ast))
    # Même numéro, autre adresse : ESSAI-6 ferme aussi sur le téléphone.
    code, rep = await appel(R.referral_join(dto["share_token"], Requete(corps_ami(email="nouvelle@exemple.test"))))
    verifier("5e. Même téléphone sous une autre adresse : 409 aussi (ESSAI-6)", code == 409 and "free_trial" in rep["headers"].get("X-Refus-Raison", ""), str((code, rep)))
    # Un ABONNÉ ACTIF (forfait payant) ne peut pas être filleul : ESSAI-4, avant ESSAI-1.
    base, occ = base_de_depart()
    _, dto = await creer_pass(base, occ)
    dans_3_mois = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()
    base["subscriptions"].docs.append({"id": "sub-actif", "code": "PACK-ACTIF", "email": "client@exemple.test",
                                       "status": "active", "remaining_sessions": 5, "used_sessions": 0,
                                       "total_sessions": 5, "expires_at": dans_3_mois, "coach_id": ""})
    code, rep = await appel(R.referral_join(dto["share_token"], Requete(corps_ami(email="client@exemple.test", tel="+41 76 100 20 30"))))
    verifier("5f. Abonné actif : 409 abonne_actif, AUCUN verrou d'essai posé (ESSAI-4 lit, ESSAI-1 n'a pas écrit)",
             code == 409 and rep["headers"].get("X-Refus-Raison") == "abonne_actif" and not base["free_trial_claims"].docs
             and MOUCHARDS["ordre"] == [], str((code, rep, MOUCHARDS["ordre"])))

    # ── 4. même ami une deuxième fois sur la même occurrence (autre parrain) ─
    base, occ = base_de_depart()
    _, dto = await creer_pass(base, occ)
    code, rep = await appel(R.referral_join(dto["share_token"], Requete(corps_ami())))
    verifier("4-pré. Premier join OK", code == 200 and rep["status"] == "unlocked", str(code))
    # Un second parrain, même occurrence.
    base["subscriptions"].docs.append(dict(base["subscriptions"].docs[0], id="sub-p2", code="BASS-DUO-02",
                                           email="marc.parrain@exemple.test", name="Marc Parrain", whatsapp=""))
    base["discount_codes"].docs.append(dict(base["discount_codes"].docs[0], id="code-p2", code="BASS-DUO-02",
                                            assignedEmail="marc.parrain@exemple.test", name="Marc Parrain"))
    tok2 = jeton_espace(base, "BASS-DUO-02", "marc.parrain@exemple.test")
    code, dto2 = await creer_pass(base, occ, tok=tok2)
    verifier("4-pré. Le second parrain crée son pass (201)", code == 201, str(code))
    n_paiements = len(MOUCHARDS["paiements"])
    code, rep = await appel(R.referral_join(dto2["share_token"], Requete(corps_ami())))
    verifier("4. Même ami sur la même occurrence via un autre pass : 409 deja_filleul_occurrence (index partiel)",
             code == 409 and rep["headers"].get("X-Refus-Raison") == "deja_filleul_occurrence", str((code, rep)))
    verifier("4b. Refus AVANT le moteur d'essai : aucun nouvel octroi, second pass toujours sans invité",
             len(MOUCHARDS["paiements"]) == n_paiements and base["referral_passes"].docs[1]["invitee"] is None)

    # ── 7. parrain sans séance -> friend_registered, puis /confirm ─────────
    base, occ = base_de_depart(seances_parrain=0)
    _, dto = await creer_pass(base, occ)
    code, rep = await appel(R.referral_join(dto["share_token"], Requete(corps_ami())))
    p = base["referral_passes"].docs[0]
    resas = [r for r in base["reservations"].docs if r.get("pass_id")]
    verifier("7. Parrain sans séance : 200, status friend_registered, blocked_reason sponsor_sans_seance",
             code == 200 and rep["status"] == "friend_registered" and rep["blocked_reason"] == "sponsor_sans_seance"
             and p["status"] == "friend_registered", str((code, rep.get("status"), rep.get("blocked_reason"))))
    verifier("7b. UNE seule réservation (invitee), AUCUNE réservation parrain, un seul billet, 1 seul débit",
             len(resas) == 1 and resas[0]["pass_role"] == "invitee" and len(rep["tickets"]) == 1
             and rep["tickets"][0]["role"] == "invitee" and p["reservations"]["sponsor_id"] is None
             and len(MOUCHARDS["seances"]) == 1, str((len(resas), rep["tickets"])))
    verifier("7c. Le parrain est prévenu (push « ami inscrit »), pas d'e-mail « débloqué »",
             any(m["data"].get("type") == "pass_duo_friend_registered" for m in MOUCHARDS["push"])
             and not MOUCHARDS["email_parrain"], str(MOUCHARDS["push"]))
    code, rep = await appel(R.referral_confirmer(dto["id"], req_parrain(base)))
    verifier("7d. /confirm sans recharge : 409 X-Refus-Raison sponsor_sans_seance",
             code == 409 and rep["headers"].get("X-Refus-Raison") == "sponsor_sans_seance", str((code, rep)))
    # Recharge : une séance revient sur le forfait ET la fiche.
    sub_p = [d for d in base["subscriptions"].docs if d["code"] == PARRAIN_CODE][0]
    sub_p["remaining_sessions"], sub_p["used_sessions"] = 1, 9
    [d for d in base["discount_codes"].docs if d["code"] == PARRAIN_CODE][0]["used"] = 9
    code, rep = await appel(R.referral_confirmer(dto["id"], req_parrain(base)))
    p = base["referral_passes"].docs[0]
    verifier("7e. /confirm après recharge : 200, unlocked, 2 billets, réservation parrain créée",
             code == 200 and rep["status"] == "unlocked" and len(rep["tickets"]) == 2
             and p["status"] == "unlocked" and p["reservations"]["sponsor_id"] and p["blocked_reason"] is None,
             str((code, rep.get("status"), len(rep.get("tickets", [])))))
    verifier("7f. Le parrain a bien été débité à ce moment-là (1 -> 0) et l'e-mail « débloqué » part",
             sub_p["remaining_sessions"] == 0 and MOUCHARDS["email_parrain"] == [dto["id"]], str(sub_p["remaining_sessions"]))

    # ── 10. expiration ────────────────────────────────────────────────────
    base, occ = base_de_depart()
    _, dto = await creer_pass(base, occ)
    hier = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT18:30:00")
    p = base["referral_passes"].docs[0]
    p["occurrence"], p["expires_at"], p["status"] = hier, hier, "waiting"
    code, pub = await appel(R.referral_pass_public(dto["share_token"]))
    verifier("10. Occurrence passée : lecture publique -> status expired, expired:true (persisté)",
             code == 200 and pub["status"] == "expired" and pub["expired"] is True and p["status"] == "expired", str(pub))
    code, rep = await appel(R.referral_join(dto["share_token"], Requete(corps_ami())))
    verifier("10b. Join sur un pass expiré : 410, rien d'écrit", code == 410 and not MOUCHARDS["paiements"], str(code))
    code, me = await appel(R.referral_me(req_parrain(base)))
    verifier("10c. GET /me : le pass est `expired` avec son libellé", me["passes"][0]["status"] == "expired"
             and me["passes"][0]["status_label"] == "Expiré")
    code, dto_bis = await creer_pass(base, occ)
    verifier("10d. Un pass expiré ne bloque pas la création d'un nouveau pass (index partiel sur les actifs)",
             code == 201 and dto_bis["id"] != dto["id"], str(code))

    # ── 11. annulation depuis waiting ──────────────────────────────────────
    base, occ = base_de_depart()
    _, dto = await creer_pass(base, occ)
    await appel(R.referral_invitation(req_parrain(base, {"pass_id": dto["id"], "channel": "copy"})))
    code, rep = await appel(R.referral_annuler(dto["id"], req_parrain(base)))
    verifier("11. cancel depuis waiting : 200, status cancelled, libellé « Annulé »",
             code == 200 and rep["status"] == "cancelled" and rep["status_label"] == "Annulé"
             and base["referral_passes"].docs[0]["status"] == "cancelled", str((code, rep.get("status"))))
    code, rep = await appel(R.referral_join(dto["share_token"], Requete(corps_ami())))
    verifier("11c. Join sur un pass annulé : 410", code == 410)
    autre = jeton_espace(base, "BASS-DUO-02", "marc.parrain@exemple.test")
    base["subscriptions"].docs.append(dict(base["subscriptions"].docs[0], id="sub-p2", code="BASS-DUO-02",
                                           email="marc.parrain@exemple.test"))
    code, _ = await appel(R.referral_annuler(dto["id"], req_parrain(base, tok=autre)))
    verifier("11d. Un AUTRE abonné ne peut pas annuler ce pass : 404 (pas d'oracle)", code == 404, str(code))

    # ── 13. route publique sans fuite PII ──────────────────────────────────
    base, occ = base_de_depart()
    _, dto = await creer_pass(base, occ)
    code, pub = await appel(R.referral_pass_public(dto["share_token"]))
    verifier("13. GET /pass/<token> : 200, sponsor_first_name + course + occurrence, et AUCUNE clé email/whatsapp/email_norm/subscription_code (parcours récursif)",
             code == 200 and pub["sponsor_first_name"] == "Léa" and pub["course"]["name"] == "Afro Cardio"
             and not E.contient_pii(pub) and "Léa Parrain" not in json.dumps(pub, ensure_ascii=False)
             and PARRAIN_CODE not in json.dumps(pub), str(pub))
    verifier("13b. Le JSON public ne contient ni l'adresse ni le code du parrain, sous aucune clé",
             PARRAIN_EMAIL not in json.dumps(pub) and PARRAIN_TEL not in json.dumps(pub))
    code, _ = await appel(R.referral_pass_public("jeton-inconnu"))
    verifier("13c. Jeton inconnu : 404", code == 404)
    await appel(R.referral_join(dto["share_token"], Requete(corps_ami())))
    code, rep = await appel(R.referral_join(dto["share_token"], Requete(corps_ami())))
    verifier("13d. La réponse de join (vue de l'ami) ne fuit aucune PII non plus",
             not E.contient_pii(rep) and AMI_EMAIL not in json.dumps(rep) and PARRAIN_EMAIL not in json.dumps(rep),
             str(E.contient_pii(rep)))

    # ── 14. drapeau OFF -> 404 partout sauf /config ────────────────────────
    base, occ = base_de_depart(drapeau=False)
    code, cfg = await appel(R.referral_config())
    verifier("14. Drapeau OFF : /config -> {enabled:false, courses:[]}", code == 200 and cfg == {"enabled": False, "courses": []}, str(cfg))
    fermees = {
        "me": R.referral_me(req_parrain(base)),
        "pass": R.referral_creer_pass(req_parrain(base, {"course_id": COURS_DUO, "occurrence": occ})),
        "invitations": R.referral_invitation(req_parrain(base, {"pass_id": "x", "channel": "copy"})),
        "cancel": R.referral_annuler("x", req_parrain(base)),
        "confirm": R.referral_confirmer("x", req_parrain(base)),
        "public": R.referral_pass_public("x"),
        "join": R.referral_join("x", Requete(corps_ami())),
        "admin/summary": R.referral_admin_summary(Requete(params={}, entetes={"Authorization": "Bearer " + jeton_admin()})),
        "admin/passes": R.referral_admin_passes(Requete(params={}, entetes={"Authorization": "Bearer " + jeton_admin()})),
    }
    resultats = {}
    for nom, coro in fermees.items():
        c, r = await appel(coro)
        resultats[nom] = (c, r.get("detail"))
    verifier("14b. Les 9 autres routes répondent 404 parrainage_duo_desactive",
             all(v == (404, "parrainage_duo_desactive") for v in resultats.values()), str(resultats))
    base["feature_flags"].docs.clear()
    code, cfg = await appel(R.referral_config())
    verifier("14c. Document feature_flags ABSENT : OFF aussi (défaut False)", cfg == {"enabled": False, "courses": []})
    verifier("14d. Base injoignable : le drapeau vaut False (repli ouvert = OFF)",
             (await R.parrainage_duo_actif(None)) is False)

    # ── 15. /config ne liste que visible + non archivé + duo_enabled ───────
    base, occ = base_de_depart()
    code, cfg = await appel(R.referral_config())
    verifier("15. /config ON : un seul cours (visible + non archivé + duo_enabled), avec ses occurrences (≤ 6) dont la première = celle du banc",
             code == 200 and cfg["enabled"] is True and [c["id"] for c in cfg["courses"]] == [COURS_DUO]
             and 1 <= len(cfg["courses"][0]["occurrences"]) <= 6 and cfg["courses"][0]["occurrences"][0] == occ
             and set(cfg["courses"][0]) >= {"id", "name", "weekday", "date", "time", "locationName", "mapsUrl", "occurrences"},
             str(cfg)[:300])
    verifier("15b. Le modèle Course déclare `duo_enabled` (Optional, défaut None = NON)",
             "duo_enabled" in S.Course.model_fields and S.Course.model_fields["duo_enabled"].default is None)

    # ── 16. rollback : la réservation de l'ami échoue APRÈS l'octroi ───────
    base, occ = base_de_depart()
    _, dto = await creer_pass(base, occ)

    async def _seances_en_panne(*a, **k):
        raise RuntimeError("panne simulée pendant le débit")
    SH.seances_consommer = _seances_en_panne
    code, rep = await appel(R.referral_join(dto["share_token"], Requete(corps_ami())))
    SH.seances_consommer = _mouchard_seances
    p = base["referral_passes"].docs[0]
    essai = [d for d in base["discount_codes"].docs if d.get("assignedEmail") == AMI_EMAIL]
    verrous = base["free_trial_claims"].docs
    verifier("16. Panne après l'octroi : 500 propre, AUCUNE réservation, pass rouvert (invitee None, status inchangé = locked)",
             code == 500 and not [r for r in base["reservations"].docs if r.get("pass_id")]
             and p["invitee"] is None and p["status"] == "locked", str((code, p["status"], p["invitee"])))
    verifier("16b. Le droit à l'essai est RENDU (verrous libérés) et le forfait/code nés de l'octroi sont neutralisés, pas supprimés",
             all(v.get("actif") is False for v in verrous) and len(verrous) == 2
             and essai and essai[0]["active"] is False and essai[0]["maxUses"] == 0 and essai[0].get("pass_duo_rollback") is True,
             str((verrous, essai[0] if essai else None))[:200])
    verifier("16c. Après rollback, ESSAI-6 ne voit plus d'essai « déjà détenu » : l'ami pourra réessayer",
             (await SH.essai6_reutilisable(base, AMI_EMAIL, AMI_TEL)) is None)
    code, rep = await appel(R.referral_join(dto["share_token"], Requete(corps_ami())))
    verifier("16d. Le même ami réessaie : 200 unlocked (le pass et le droit sont bien revenus)",
             code == 200 and rep["status"] == "unlocked", str((code, rep.get("status"))))

    # ── 18. conditions publiées (T1) : la preuve du parrain n'est jamais inventée ─
    base, occ = base_de_depart()
    base["concept"].docs.append({"id": "concept", "termsText": "Conditions de participation v1."})
    code, dto = await appel(R.referral_creer_pass(req_parrain(base, {"course_id": COURS_DUO, "occurrence": occ})))
    verifier("18. Pass créé SANS terms_accepted : 201 (les conditions se jugent à la réservation, pas à la création)", code == 201, str(code))
    code, rep = await appel(R.referral_join(dto["share_token"], Requete(corps_ami())))
    resas = [r for r in base["reservations"].docs if r.get("pass_id")]
    verifier("18b. L'ami (qui a accepté) est inscrit ; le parrain n'a PAS accepté -> friend_registered, blocked_reason conditions_non_acceptees, AUCUNE réservation parrain",
             code == 200 and rep["status"] == "friend_registered" and rep["blocked_reason"] == "conditions_non_acceptees"
             and len(resas) == 1 and resas[0]["pass_role"] == "invitee" and resas[0].get("terms_accepted") is True
             and resas[0].get("terms_version"), str((code, rep.get("status"), rep.get("blocked_reason"))))
    code, rep = await appel(R.referral_confirmer(dto["id"], req_parrain(base, {})))
    verifier("18c. /confirm sans accepter : 409 X-Refus-Raison conditions_non_acceptees",
             code == 409 and rep["headers"].get("X-Refus-Raison") == "conditions_non_acceptees", str((code, rep)))
    code, rep = await appel(R.referral_confirmer(dto["id"], req_parrain(base, {"terms_accepted": True})))
    resas = [r for r in base["reservations"].docs if r.get("pass_id") and r["pass_role"] == "sponsor"]
    verifier("18d. /confirm avec terms_accepted:true : 200 unlocked, la réservation du parrain porte la preuve T1",
             code == 200 and rep["status"] == "unlocked" and len(resas) == 1 and resas[0].get("terms_accepted") is True
             and resas[0].get("terms_version"), str((code, rep.get("status"))))
    base, occ = base_de_depart()
    base["concept"].docs.append({"id": "concept", "termsText": "Conditions de participation v1."})
    _, dto = await creer_pass(base, occ)
    code, rep = await appel(R.referral_join(dto["share_token"], Requete(corps_ami(email="sans.conditions@exemple.test", tel="", terms_accepted=False))))
    verifier("18e. Un ami qui n'accepte pas les conditions : 400, rien d'écrit pour lui",
             code == 400 and not [d for d in base["discount_codes"].docs if d.get("assignedEmail") == "sans.conditions@exemple.test"], str(code))

    # ── 17. moteur pur : machine d'états ──────────────────────────────────
    ok_t = (E.transition("locked", "waiting") == "waiting" and E.transition("friend_registered", "unlocked") == "unlocked"
            and E.transition("unlocked", "used") == "used")
    ko = 0
    for a, b in (("unlocked", "cancelled"), ("used", "cancelled"), ("cancelled", "waiting"), ("expired", "unlocked"),
                 ("locked", "used")):
        try:
            E.transition(a, b)
        except E.TransitionInvalide:
            ko += 1
    verifier("17. Machine d'états : transitions autorisées OK, 5 transitions interdites refusées", ok_t and ko == 5, str(ko))
    verifier("17b. Libellés FR des 7 états", set(E.LIBELLES) == set(E.ETATS) and E.LIBELLES["waiting"] == "En attente de ton ami")
    verifier("17c. cle_pass normalise l'e-mail", E.cle_pass(" Lea@X.CH ", "c", "o") == ("lea@x.ch", "c", "o"))
    txt = E.texte_whatsapp("Léa", "Afro Cardio", occ, "https://afroboost.com/duo/abc")
    verifier("17d. texte_whatsapp : prénom, cours, date lisible, URL, aucun emoji",
             "Léa" in txt and "Afro Cardio" in txt and "https://afroboost.com/duo/abc" in txt and " à " in txt
             and all(ord(ch) < 0x2600 for ch in txt), txt)
    k = E.kpi_parrainage([{"id": "a", "status": "unlocked", "opened_at": "x", "invitee": {"name": "Noé"}},
                          {"id": "b", "status": "expired"}],
                         [{"channel": "whatsapp"}, {"channel": "qr"}, {"channel": "pigeon"}],
                         [{"pass_id": "a", "validated": True}, {"pass_id": "zz", "validated": True}])
    verifier("17e. kpi_parrainage pur : 9 compteurs cohérents, canal inconnu ignoré, présence hors périmètre ignorée",
             k["kpi"] == {"passes_crees": 2, "invitations": 3, "ouvertures": 1, "inscriptions": 1, "debloques": 1,
                          "utilises": 0, "expires": 1, "annules": 0, "presences_duo": 1}
             and k["par_canal"] == {"whatsapp": 1, "copy": 0, "qr": 1, "share": 0}, str(k))


async def _debit_429(base, occ):
    """20 créations tolérées par heure et par IP ; la 21e est refusée SANS écriture."""
    ip = "198.51.100.%d" % (uuid.uuid4().int % 250 + 1)
    n_avant = len(base["referral_passes"].docs)
    codes = []
    for _ in range(21):
        c, _ = await appel(R.referral_creer_pass(Requete({"course_id": COURS_DUO, "occurrence": occ},
                                                         {"x-espace-token": jeton_espace(base)}, ip=ip)))
        codes.append(c)
    return codes[:20].count(429) == 0 and codes[20] == 429 and len(base["referral_passes"].docs) == n_avant


def _ordre_ast():
    """Ligne du PREMIER appel de chaque fonction clé dans `referral_join`."""
    src = io.open(os.path.join(RACINE, "api", "routes", "referral_routes.py"), encoding="utf-8").read()
    arbre = ast.parse(src)
    fn = [n for n in ast.walk(arbre) if isinstance(n, ast.AsyncFunctionDef) and n.name == "referral_join"][0]
    lignes = {}
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            nom = n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
            if nom in ("_essai4_garde", "_essai1_garde", "_process_successful_payment",
                       "_reserver_seance_duo", "_debloquer_ou_bloquer") and nom not in lignes:
                lignes[nom] = n.lineno
    return lignes


def main():
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())
    except Exception:
        pass
    asyncio.get_event_loop().run_until_complete(principal())
    ok = 0
    print("=" * 78)
    print("V534 — PASS DUO : %d vérifications" % len(RESULTATS))
    print("=" * 78)
    for nom, cond, detail in RESULTATS:
        ok += 1 if cond else 0
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom,
                               ("" if cond or not detail else "\n         -> " + str(detail)[:400])))
    print("-" * 78)
    print("%d / %d verifications au vert" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())
