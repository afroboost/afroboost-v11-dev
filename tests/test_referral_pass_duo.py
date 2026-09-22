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
COURS_SANS_OFFRE = "cours-duo-sans-offre"     # V534b : duo_enabled mais aucun catalogue
OFFRE_ESSAI = "offre-essai-0"                 # = offre A (la « Recommandée »)
OFFRE_A, OFFRE_B, OFFRE_C = OFFRE_ESSAI, "offre-duo-b", "offre-duo-c"
OFFRE_D = "offre-duo-d-non-autorisee"        # gratuite, du coach, PAS dans duo_offer_ids
OFFRE_PAYANTE = "offre-payante-30"           # dans duo_offer_ids, 30 CHF -> jamais
OFFRE_AUTRE_COACH = "offre-autre-coach"      # dans duo_offer_ids, coach_id différent
OFFRE_ARCHIVEE = "offre-archivee"            # dans duo_offer_ids, archivée
OFFRE_INVISIBLE = "offre-invisible"          # dans duo_offer_ids, visible: false
CATALOGUE_AUTORISE = [OFFRE_A, OFFRE_B, OFFRE_C, OFFRE_PAYANTE, OFFRE_AUTRE_COACH,
                      OFFRE_ARCHIVEE, OFFRE_INVISIBLE]

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
         "archived": False, "duo_enabled": True, "coach_id": None,
         # V534b : le coach autorise 3 offres valides (+ 4 pièges que le backend doit écarter).
         "duo_offer_ids": list(CATALOGUE_AUTORISE), "duo_default_offer_id": OFFRE_A},
        {"id": COURS_NON_DUO, "name": "Sans Duo", "weekday": wd, "time": "19:30",
         "locationName": "Salle Sud", "visible": True, "archived": False},
        {"id": COURS_CACHE, "name": "Duo caché", "weekday": wd, "time": "20:30",
         "locationName": "Salle Est", "visible": False, "archived": False, "duo_enabled": True,
         "duo_offer_ids": [OFFRE_A]},
        {"id": "cours-duo-archive", "name": "Duo archivé", "weekday": wd, "time": "21:30",
         "locationName": "Salle Ouest", "visible": True, "archived": True, "duo_enabled": True,
         "duo_offer_ids": [OFFRE_A]},
        {"id": COURS_SANS_OFFRE, "name": "Duo sans offre", "weekday": wd, "time": "17:30",
         "locationName": "Salle Vide", "visible": True, "archived": False, "duo_enabled": True,
         "coach_id": None},
    ]
    base["offers"].docs += [
        {"id": OFFRE_A, "name": "Essai gratuit", "price": 0.0, "visible": True, "coach_id": None,
         "linked_course_ids": [COURS_DUO]},
        {"id": OFFRE_B, "name": "Duo 2 séances", "price": 0, "visible": True, "coach_id": "",
         "pack_sessions": 2, "duree_mois": 1, "description": "Deux séances pour découvrir."},
        {"id": OFFRE_C, "name": "Découverte 14 jours", "price": 0.0, "visible": True,
         "duration_value": 14, "duration_unit": "days", "description": "x" * 260},
        {"id": OFFRE_D, "name": "Gratuite non autorisée", "price": 0.0, "visible": True, "coach_id": None},
        {"id": OFFRE_PAYANTE, "name": "Cours à l'unité", "price": 30.0, "visible": True, "coach_id": None},
        {"id": OFFRE_AUTRE_COACH, "name": "Essai partenaire", "price": 0.0, "visible": True,
         "coach_id": "autre@coach.test"},
        {"id": OFFRE_ARCHIVEE, "name": "Ancien essai", "price": 0.0, "visible": True, "coach_id": None,
         "archived": True},
        {"id": OFFRE_INVISIBLE, "name": "Essai caché", "price": 0.0, "visible": False, "coach_id": None},
    ]
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
    # V534b : le compteur de débit par IP est en mémoire du processus (ESSAI-7,
    # 20/h) ; chaque base de départ repart d'une « heure » neuve. Le test 1i
    # prouve le 429 lui-même sur une IP dédiée.
    C._ESSAI7_DEBIT.clear()
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


async def creer_pass(base, occ, tok=None, offer_id=OFFRE_A, **extra):
    corps = {"course_id": COURS_DUO, "occurrence": occ, "terms_accepted": True}
    if offer_id is not None:
        corps["offer_id"] = offer_id
    corps.update(extra)
    code, dto = await appel(R.referral_creer_pass(req_parrain(base, corps, tok=tok)))
    return code, dto


def entetes_admin():
    return {"Authorization": "Bearer " + jeton_admin()}


async def patch_offre(base, identifiant, offer_id, version, tok=None, public=False, ip=None):
    """PATCH /pass/{identifiant}/offer — porte parrain (jeton) ou publique."""
    corps = {"offer_id": offer_id, "version": version}
    if public:
        return await appel(R.referral_changer_offre(identifiant, Requete(corps, {}, ip=ip)))
    return await appel(R.referral_changer_offre(identifiant, req_parrain(base, corps, tok=tok)))


def resas_ami(base, email=AMI_EMAIL):
    return [r for r in base["reservations"].docs if r.get("pass_role") == "invitee"
            and (r.get("userEmail") or "").lower() == email]


def resas_ami_actives(base, email=AMI_EMAIL):
    return [r for r in resas_ami(base, email) if r.get("status") != "cancelled"]


def codes_ami(base, email=AMI_EMAIL):
    return [d for d in base["discount_codes"].docs if d.get("assignedEmail") == email]


def subs_ami(base, email=AMI_EMAIL):
    return [d for d in base["subscriptions"].docs if d.get("email") == email]


def verrous_actifs(base):
    return [v for v in base["free_trial_claims"].docs if v.get("actif") is True]


def bilan_seances(base, code):
    """(débits appliqués, restitutions appliquées) sur `seance_mouvements` pour ce code."""
    m = [d for d in base["seance_mouvements"].docs if d.get("code") == code and d.get("statut") == "applique"]
    return (sum(1 for d in m if d["type"] == "debit"), sum(1 for d in m if d["type"] == "restitution"))


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
             and dto.get("share_token") and all(ord(ch) < 0x2600 for ch in dto.get("whatsapp_text", "")),
             str({k: dto.get(k) for k in ("status", "invite_url", "whatsapp_text")})[:200])
    # V538 : c'est l'URL de PARTAGE (page d'aperçu) que le message porte, pas la
    # page React — sans quoi WhatsApp affiche un aperçu anonyme.
    verifier("1b-V538. PassDTO : `share_url` = /api/share/duo/<token>, et c'est CE lien qui part dans le message",
             dto.get("share_url", "") == "https://afroboost.com/api/share/duo/%s" % dto.get("share_token")
             and dto["share_url"] in dto.get("whatsapp_text", "")
             and dto["invite_url"] not in dto.get("whatsapp_text", ""),
             str({k: dto.get(k) for k in ("share_url", "whatsapp_text")})[:220])
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
    code, _ = await appel(R.referral_creer_pass(req_parrain(base, {"course_id": COURS_DUO, "occurrence": "2020-01-01T18:30:00", "offer_id": OFFRE_A})))
    verifier("2c. Occurrence hors des dates proposées : 400", code == 400)
    code, _ = await appel(R.referral_creer_pass(Requete({"course_id": COURS_DUO, "occurrence": occ, "offer_id": OFFRE_A},
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
    verifier("5d. AST : dans _octroyer_essai, _essai4_garde < _essai1_garde < _process_successful_payment ; "
             "dans referral_join, _octroyer_essai < _reserver_ami < _debloquer_ou_bloquer ; _reserver_ami appelle "
             "_reserver_seance_duo ; le changement d'offre après join passe par les MÊMES _octroyer_essai / _reserver_ami (V534b)",
             ordre_ast["octroi"]["_essai4_garde"] < ordre_ast["octroi"]["_essai1_garde"]
             < ordre_ast["octroi"]["_process_successful_payment"]
             and ordre_ast["join"]["_octroyer_essai"] < ordre_ast["join"]["_reserver_ami"]
             < ordre_ast["join"]["_debloquer_ou_bloquer"]
             and "_reserver_seance_duo" in ordre_ast["reserver_ami"]
             and ordre_ast["changement"]["_octroyer_essai"] < ordre_ast["changement"]["_reserver_ami"]
             and not any(k in ordre_ast["join"] for k in ("_essai4_garde", "_essai1_garde", "_process_successful_payment"))
             and not any(k in ordre_ast["changement"] for k in ("_essai4_garde", "_essai1_garde", "_process_successful_payment")),
             str(ordre_ast))
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
        "pass": R.referral_creer_pass(req_parrain(base, {"course_id": COURS_DUO, "occurrence": occ, "offer_id": OFFRE_A})),
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
    code, dto = await appel(R.referral_creer_pass(req_parrain(base, {"course_id": COURS_DUO, "occurrence": occ, "offer_id": OFFRE_A})))
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

    await scenarios_offres()


# ═══════════════════════════════════════════════════════════════════════════
# V534b — L'OFFRE DU PASS DUO EST CHOISIE PAR LE PARTICIPANT (avenant §6)
# ═══════════════════════════════════════════════════════════════════════════
CHAMPS_OFFRE_DTO = {"id", "name", "benefit", "price", "sessions", "validity", "conditions", "recommended"}
TECHNIQUES = ("coach_id", "linked_course_ids", "source", "collection", "visible", "archived", "pack_sessions")


def _cours_config(cfg, cid=COURS_DUO):
    return next((c for c in cfg.get("courses", []) if c.get("id") == cid), None)


async def scenarios_offres():
    # ── 1-2. le coach autorise 3 offres ; /config expose EXACTEMENT ces 3 ──
    base, occ = base_de_depart()
    code, cfg = await appel(R.referral_config())
    c = _cours_config(cfg)
    ids = [o["id"] for o in (c or {}).get("offers", [])]
    verifier("O1. Coach : 3 offres valides parmi 7 autorisées (+1 gratuite NON autorisée) — /config expose exactement A, B, C dans l'ordre",
             code == 200 and c is not None and ids == [OFFRE_A, OFFRE_B, OFFRE_C], str(ids))
    verifier("O2. Ni la 4e non autorisée, ni la payante, ni celle d'un autre coach, ni l'archivée, ni l'invisible n'y sont",
             not ({OFFRE_D, OFFRE_PAYANTE, OFFRE_AUTRE_COACH, OFFRE_ARCHIVEE, OFFRE_INVISIBLE} & set(ids)), str(ids))
    verifier("O2b. default_offer_id = A, `recommended` vrai sur A seulement",
             c["default_offer_id"] == OFFRE_A and [o["recommended"] for o in c["offers"]] == [True, False, False],
             str(c.get("default_offer_id")))
    verifier("O2c. OffreDTO : exactement {id,name,benefit,price,sessions,validity,conditions,recommended}, aucun champ technique",
             all(set(o) == CHAMPS_OFFRE_DTO for o in c["offers"])
             and not any(t in json.dumps(c["offers"]) for t in TECHNIQUES), str(c["offers"])[:300])
    oA, oB, oC = c["offers"]
    verifier("O2d. Calculs §2 : A = 1 séance offerte / prix 0 / validity None / conditions None ; B = 2 séances offertes, 1 mois, "
             "conditions ; C = 14 jours, conditions tronquées à 200 caractères",
             oA["benefit"] == "1 séance offerte" and oA["sessions"] == 1 and oA["price"] == 0 and oA["validity"] is None
             and oA["conditions"] is None
             and oB["benefit"] == "2 séances offertes" and oB["sessions"] == 2 and oB["validity"] == "1 mois"
             and oB["conditions"] == "Deux séances pour découvrir."
             and oC["validity"] == "14 jours" and len(oC["conditions"]) == 200 and oC["conditions"].endswith("…"),
             str((oA, oB, oC))[:400])
    verifier("O2e. Un cours duo_enabled SANS duo_offer_ids est OMIS du /config (absent vaut aucune offre)",
             _cours_config(cfg, COURS_SANS_OFFRE) is None and [x["id"] for x in cfg["courses"]] == [COURS_DUO],
             str([x["id"] for x in cfg["courses"]]))
    verifier("O2f. Le modèle Course déclare duo_offer_ids / duo_default_offer_id (Optional, défaut None)",
             {"duo_offer_ids", "duo_default_offer_id"} <= set(S.Course.model_fields)
             and S.Course.model_fields["duo_offer_ids"].default is None
             and S.Course.model_fields["duo_default_offer_id"].default is None)

    # ── 3. choix A à la création ───────────────────────────────────────────
    code, dto = await creer_pass(base, occ, offer_id=OFFRE_A)
    p = base["referral_passes"].docs[0]
    verifier("O3. POST /pass avec offer_id A : 201 ; pass persisté avec offer_id A, offer_snapshot figé, offer_history [], version 1",
             code == 201 and p["offer_id"] == OFFRE_A and p["offer_snapshot"]["name"] == "Essai gratuit"
             and p["offer_snapshot"]["benefit"] == "1 séance offerte" and p["offer_history"] == [] and p["version"] == 1,
             str((code, p.get("offer_id"), p.get("version"))))
    verifier("O3b. PassDTO : offer.id A (recommended), offers = catalogue courant (3), version 1, offer_history []",
             dto["offer"]["id"] == OFFRE_A and dto["offer"]["recommended"] is True and len(dto["offers"]) == 3
             and dto["version"] == 1 and dto["offer_history"] == [] and not E.contient_pii(dto),
             str({k: dto.get(k) for k in ("offer", "version")})[:200])

    # ── 4-6. A -> B (locked) par le parrain ────────────────────────────────
    code, d4 = await patch_offre(base, dto["id"], OFFRE_B, 1)
    p = base["referral_passes"].docs[0]
    verifier("O4. PATCH /pass/{id}/offer {offer_id:B, version:1} (locked) : 200 PassDTO offer.id B, version 2",
             code == 200 and d4["offer"]["id"] == OFFRE_B and d4["version"] == 2, str((code, d4.get("offer"), d4.get("version"))))
    verifier("O5. B est l'offre ACTIVE du pass en base (offer_id + snapshot), version 2",
             p["offer_id"] == OFFRE_B and p["offer_snapshot"]["name"] == "Duo 2 séances" and p["version"] == 2)
    h = p["offer_history"]
    verifier("O6. offer_history : 1 entrée {from A, to B, from_name, to_name, changed_at, changed_by sponsor} + événement offer_changed",
             len(h) == 1 and h[0]["from_offer_id"] == OFFRE_A and h[0]["to_offer_id"] == OFFRE_B
             and h[0]["from_name"] == "Essai gratuit" and h[0]["to_name"] == "Duo 2 séances" and h[0]["changed_by"] == "sponsor"
             and h[0]["changed_at"] and any(e["type"] == "offer_changed" for e in p["events"]), str(h))
    code, d4b = await patch_offre(base, dto["id"], OFFRE_B, 2)
    verifier("O6b. Même offre à nouveau : 200 idempotent, AUCUNE écriture (version reste 2, historique inchangé)",
             code == 200 and d4b["version"] == 2 and len(base["referral_passes"].docs[0]["offer_history"]) == 1)
    code, r = await patch_offre(base, dto["id"], OFFRE_C, 1)
    verifier("O6c. Version périmée (1 alors que 2) : 409 conflit_version, rien n'a changé",
             code == 409 and r["headers"].get("X-Refus-Raison") == "conflit_version"
             and base["referral_passes"].docs[0]["offer_id"] == OFFRE_B, str((code, r)))
    code, r = await appel(R.referral_changer_offre(dto["id"], req_parrain(base, {"offer_id": OFFRE_C})))
    verifier("O6d. Sans `version` dans le corps : 400 version_requise", code == 400 and r["headers"].get("X-Refus-Raison") == "version_requise", str((code, r)))

    # ── 7. /pass/{token} montre B ──────────────────────────────────────────
    tok = dto["share_token"]
    code, pub = await appel(R.referral_pass_public(tok))
    verifier("O7. GET /pass/{token} : offer.id B, offers (3, sans champ technique), version rendue APRÈS link_opened (3), aucune PII",
             code == 200 and pub["offer"]["id"] == OFFRE_B and len(pub["offers"]) == 3 and pub["version"] == 3
             and not E.contient_pii(pub) and not any(t in json.dumps(pub["offers"]) for t in TECHNIQUES),
             str({k: pub.get(k) for k in ("offer", "version")})[:200])

    # ── 8. l'ami change B -> C avant join (public) ─────────────────────────
    code, d8 = await patch_offre(base, tok, OFFRE_C, pub["version"], public=True)
    p = base["referral_passes"].docs[0]
    verifier("O8. PATCH public /pass/{token}/offer {C, version 3} avant join : 200, offre C, changed_by invitee, version 4",
             code == 200 and d8["offer"]["id"] == OFFRE_C and p["offer_id"] == OFFRE_C
             and p["offer_history"][-1]["changed_by"] == "invitee" and p["version"] == 4, str((code, p.get("version"))))
    verifier("O8b. La réponse publique du PATCH ne fuit aucune PII (ni e-mail, ni code du parrain)",
             not E.contient_pii(d8) and PARRAIN_EMAIL not in json.dumps(d8) and PARRAIN_CODE not in json.dumps(d8))
    code, r = await patch_offre(base, tok, OFFRE_B, 3, public=True)
    verifier("O8c. Un second PATCH public avec la version périmée (3) : 409 conflit_version",
             code == 409 and r["headers"].get("X-Refus-Raison") == "conflit_version", str((code, r)))

    # ── 9. /me du parrain montre C + historique ────────────────────────────
    code, me = await appel(R.referral_me(req_parrain(base)))
    lignes = [l for l in me["history"] if l["type"] == "offer_changed"]
    verifier("O9. GET /me : offer.id C, offer_history 2 entrées, history porte 2 lignes « Offre modifiée : A → B / B → C »",
             code == 200 and me["passes"][0]["offer"]["id"] == OFFRE_C and len(me["passes"][0]["offer_history"]) == 2
             and len(lignes) == 2
             and {l["label"] for l in lignes} == {"Offre modifiée : Essai gratuit → Duo 2 séances",
                                                  "Offre modifiée : Duo 2 séances → Découverte 14 jours"},
             str(lignes))

    # ── 10-12. refus 400 : non autorisée / autre coach / inactive ──────────
    v = base["referral_passes"].docs[0]["version"]
    code, r = await patch_offre(base, dto["id"], OFFRE_D, v)
    verifier("O10. Offre gratuite du coach mais NON autorisée sur le cours : 400 offre_non_autorisee",
             code == 400 and r["headers"].get("X-Refus-Raison") == "offre_non_autorisee", str((code, r)))
    code, r = await patch_offre(base, dto["id"], OFFRE_AUTRE_COACH, v)
    verifier("O11. Offre d'un AUTRE coach (pourtant dans duo_offer_ids) : 400 offre_autre_coach",
             code == 400 and r["headers"].get("X-Refus-Raison") == "offre_autre_coach", str((code, r)))
    code, r = await patch_offre(base, dto["id"], OFFRE_ARCHIVEE, v)
    code2, r2 = await patch_offre(base, dto["id"], OFFRE_INVISIBLE, v)
    code3, r3 = await patch_offre(base, dto["id"], "offre-inexistante", v)
    verifier("O12. Offre archivée / invisible / inexistante : 400 offre_inactive (archivée, invisible) — inexistante = non autorisée",
             code == 400 and r["headers"].get("X-Refus-Raison") == "offre_inactive"
             and code2 == 400 and r2["headers"].get("X-Refus-Raison") == "offre_inactive"
             and code3 == 400 and r3["headers"].get("X-Refus-Raison") == "offre_non_autorisee", str((r, r2, r3)))
    verifier("O12b. Aucun de ces refus n'a écrit : offre toujours C, version inchangée, historique intact",
             base["referral_passes"].docs[0]["offer_id"] == OFFRE_C and base["referral_passes"].docs[0]["version"] == v
             and len(base["referral_passes"].docs[0]["offer_history"]) == 2)
    code, r = await patch_offre(base, dto["id"], OFFRE_PAYANTE, v)
    verifier("Obonus-a. Offre PAYANTE (dans duo_offer_ids) : 400 offre_payante au PATCH",
             code == 400 and r["headers"].get("X-Refus-Raison") == "offre_payante", str((code, r)))
    code, r = await creer_pass(base, _prochaine_occurrence(8)[0], offer_id=OFFRE_PAYANTE)
    verifier("Obonus-b. Offre PAYANTE à la création : 400 offre_payante, aucun pass créé",
             code == 400 and r["headers"].get("X-Refus-Raison") == "offre_payante" and len(base["referral_passes"].docs) == 1,
             str((code, r)))
    code, r = await creer_pass(base, _prochaine_occurrence(8)[0], offer_id=None)
    verifier("Obonus-c. `offer_id` manquant à la création : 400 offre_requise, aucun pass créé",
             code == 400 and r["headers"].get("X-Refus-Raison") == "offre_requise" and len(base["referral_passes"].docs) == 1,
             str((code, r)))
    code, r = await creer_pass(base, _prochaine_occurrence(8)[0], offer_id=OFFRE_D)
    verifier("Obonus-d. Offre non autorisée à la création : 400 offre_non_autorisee",
             code == 400 and r["headers"].get("X-Refus-Raison") == "offre_non_autorisee", str((code, r)))

    # ── join : l'octroi utilise L'OFFRE DU PASS (C), plus aucun réglage ────
    code, rep = await appel(R.referral_join(tok, Requete(corps_ami())))
    sub = subs_ami(base)
    verifier("Ojoin. Join : 200 unlocked ; le forfait de l'ami est né de l'offre DU PASS (offer_id C, `_offre_essai` n'existe plus) ; "
             "la réponse porte offer.id C",
             code == 200 and rep["status"] == "unlocked" and len(sub) == 1 and sub[0].get("offer_id") == OFFRE_C
             and rep["offer"]["id"] == OFFRE_C and not hasattr(R, "_offre_essai") and not hasattr(R, "FLAG_OFFRE")
             and MOUCHARDS["paiements"][-1]["items"][0].id == OFFRE_C,
             str((code, rep.get("status"), sub[0].get("offer_id") if sub else None)))
    code, r = await patch_offre(base, tok, OFFRE_A, base["referral_passes"].docs[0]["version"], public=True)
    verifier("Ojoin-b. PATCH public APRÈS join : 409 pass_deja_rejoint (seul le parrain peut encore changer)",
             code == 409 and r["headers"].get("X-Refus-Raison") == "pass_deja_rejoint", str((code, r)))

    # ── 13. changement AVANT déblocage (friend_registered, parrain sans séance) ─
    base, occ = base_de_depart(seances_parrain=0)
    _, dto = await creer_pass(base, occ, offer_id=OFFRE_A)
    code, rep = await appel(R.referral_join(dto["share_token"], Requete(corps_ami())))
    p = base["referral_passes"].docs[0]
    ancien_code, ancien_rid = p["invitee_access_code"], p["reservations"]["invitee_id"]
    code, d13 = await patch_offre(base, dto["id"], OFFRE_B, p["version"])
    p = base["referral_passes"].docs[0]
    verifier("O13. friend_registered (ami inscrit, parrain sans séance) : PATCH A->B = 200, statut inchangé, réservation parrain toujours absente, "
             "ancien code/réservation neutralisés, nouveaux nés de B",
             code == 200 and rep["status"] == "friend_registered" and d13["status"] == "friend_registered"
             and p["reservations"]["sponsor_id"] is None and p["offer_id"] == OFFRE_B
             and p["invitee_access_code"] != ancien_code and p["reservations"]["invitee_id"] != ancien_rid
             and len(resas_ami_actives(base)) == 1 and resas_ami_actives(base)[0]["id"] == p["reservations"]["invitee_id"]
             and not any(r["id"] == ancien_rid for r in resas_ami(base)),
             str((code, d13.get("status"), p.get("offer_id"))))

    # ── 14-17. changement APRÈS déblocage sans présence ────────────────────
    base, occ = base_de_depart(seances_parrain=3)
    _, dto = await creer_pass(base, occ, offer_id=OFFRE_A)
    code, rep = await appel(R.referral_join(dto["share_token"], Requete(corps_ami())))
    p0 = json.loads(json.dumps(base["referral_passes"].docs[0]))
    ancien_code, ancien_rid = p0["invitee_access_code"], p0["reservations"]["invitee_id"]
    resa_parrain_avant = json.loads(json.dumps(next(r for r in base["reservations"].docs if r.get("pass_role") == "sponsor")))
    n_seances_avant = len(MOUCHARDS["seances"])
    code, d14 = await patch_offre(base, dto["id"], OFFRE_B, p0["version"])
    p = base["referral_passes"].docs[0]
    nouveau_code = p["invitee_access_code"]
    ancien_c = next(d for d in base["discount_codes"].docs if d["code"] == ancien_code)
    ancien_s = next(d for d in base["subscriptions"].docs if d["code"] == ancien_code)
    ancienne_r = next((r for r in base["reservations"].docs if r["id"] == ancien_rid), None)
    nouveau_c = next((d for d in base["discount_codes"].docs if d["code"] == nouveau_code), None)
    nouveau_s = next((d for d in base["subscriptions"].docs if d["code"] == nouveau_code), None)
    nouvelle_r = next((r for r in base["reservations"].docs if r["id"] == p["reservations"]["invitee_id"]), None)
    verifier("O14. unlocked sans présence : PATCH A->B = 200, statut unlocked, offre B active, version incrémentée, historique A->B sponsor",
             code == 200 and d14["status"] == "unlocked" and d14["offer"]["id"] == OFFRE_B and p["offer_id"] == OFFRE_B
             and p["version"] > p0["version"] and p["offer_history"][-1]["changed_by"] == "sponsor"
             and p["offer_history"][-1]["from_offer_id"] == OFFRE_A, str((code, d14.get("status"), d14.get("offer"))))
    verifier("O14b. ANCIEN octroi neutralisé : code inactif/maxUses 0, forfait cancelled à 0, marqués pass_duo_offer_change — jamais supprimés",
             ancien_c["active"] is False and ancien_c["maxUses"] == 0 and ancien_c.get("pass_duo_rollback_motif") == "pass_duo_offer_change"
             and ancien_s["status"] == "cancelled" and ancien_s["remaining_sessions"] == 0
             and ancien_s.get("pass_duo_rollback_motif") == "pass_duo_offer_change", str((ancien_c, ancien_s))[:300])
    verifier("O14c. ANCIENNE réservation de l'ami SUPPRIMÉE (convention du dépôt : aucun statut d'annulation sur reservations, "
             "l'annulation LOT B3 fait delete_one) ; sa trace (reservationCode) vit dans les événements du pass",
             ancienne_r is None and any(e.get("type") in ("offer_changed", "reservation_remplacee", "offer_change")
                                        or ancien_rid in str(e) for e in p.get("events", [])),
             str((ancienne_r, [e.get("type") for e in p.get("events", [])][-4:]))[:200])
    verifier("O14d. Séance de l'ancienne réservation RESTITUÉE (fiche ancien code used 1 -> 0, mouvement restitution:<rid> appliqué)",
             ancien_c["used"] == 0 and any(d["_id"] == "restitution:%s" % ancien_rid and d["statut"] == "applique"
                                           for d in base["seance_mouvements"].docs), str(ancien_c.get("used")))
    verifier("O14e. NOUVEAU code/forfait/réservation nés de B : forfait 2 séances (pack) débité à 1, code marqué pass_duo + pass_duo_offer_id B, "
             "réservation active sur la même occurrence, pass.reservations.invitee_* mis à jour",
             nouveau_c is not None and nouveau_c["active"] is not False and nouveau_c.get("pass_duo_offer_id") == OFFRE_B
             and nouveau_c.get("pass_duo_id") == dto["id"] and nouveau_s is not None and nouveau_s.get("offer_id") == OFFRE_B
             and nouveau_s["total_sessions"] == 2 and nouveau_s["remaining_sessions"] == 1
             and nouvelle_r is not None and nouvelle_r.get("status") != "cancelled" and nouvelle_r["datetime"] == occ
             and nouvelle_r["promoCode"] == nouveau_code and p["reservations"]["invitee_code"] == nouvelle_r["reservationCode"],
             str((nouveau_s, nouvelle_r))[:300])
    resa_parrain_apres = next(r for r in base["reservations"].docs if r.get("pass_role") == "sponsor")
    sub_p = next(d for d in base["subscriptions"].docs if d["code"] == PARRAIN_CODE)
    verifier("O14f. La réservation du PARRAIN n'a pas bougé (document identique), son forfait non plus (3 -> 2, une seule fois), pass.reservations.sponsor_* identiques",
             resa_parrain_apres == resa_parrain_avant and sub_p["remaining_sessions"] == 2
             and p["reservations"]["sponsor_id"] == p0["reservations"]["sponsor_id"]
             and p["reservations"]["sponsor_code"] == p0["reservations"]["sponsor_code"])
    verifier("O15. Exactement UNE réservation de l'ami en base (l'ancienne est supprimée), un seul billet invitee dans le DTO",
             len(resas_ami_actives(base)) == 1 and len(resas_ami(base)) == 1
             and [t["role"] for t in d14["tickets"]].count("invitee") == 1
             and next(t for t in d14["tickets"] if t["role"] == "invitee")["reservationCode"] == nouvelle_r["reservationCode"],
             str([(r["id"][:8], r.get("status")) for r in resas_ami(base)]))
    verifier("O16. seances_consommer / seances_restituer ÉQUILIBRÉS : ancien code 1 débit + 1 restitution ; nouveau code 1 débit + 0 ; "
             "parrain 1 débit + 0 ; le mouchard voit exactement 1 débit de plus (le nouveau) — aucune double consommation",
             bilan_seances(base, ancien_code) == (1, 1) and bilan_seances(base, nouveau_code) == (1, 0)
             and bilan_seances(base, PARRAIN_CODE) == (1, 0) and len(MOUCHARDS["seances"]) == n_seances_avant + 1
             and MOUCHARDS["seances"][-1]["code"] == nouveau_code,
             str((bilan_seances(base, ancien_code), bilan_seances(base, nouveau_code), bilan_seances(base, PARRAIN_CODE))))
    verifier("O17. Une SEULE attribution d'essai vivante : free_trial_claims = 2 clés (adresse + numéro), toutes actives, aucun doublon ; "
             "un seul code d'essai vivant pour l'ami (l'ancien est inactif)",
             sorted(d["_id"] for d in base["free_trial_claims"].docs) == sorted(["trial:" + AMI_EMAIL, "trialtel:41765112233"])
             and len(verrous_actifs(base)) == 2 and [d["code"] for d in codes_ami(base) if d["active"] is not False] == [nouveau_code],
             str([(d["_id"], d.get("actif")) for d in base["free_trial_claims"].docs]))
    verifier("O17b. ESSAI-1 ne verrait PAS un second essai à accorder : `_essai1_garde` refuse maintenant (déjà détenu) — l'ancienne offre n'est jamais active en parallèle",
             (await appel(C._essai1_garde(AMI_EMAIL, OFFRE_A, telephone=AMI_TEL)))[0] == 409)
    verifier("O17c. Notifications : la nouvelle réservation de l'ami est notifiée (mouchard), aucun e-mail « débloqué » en double",
             MOUCHARDS["notif_resa"][-1] == nouvelle_r["id"] and MOUCHARDS["email_parrain"].count(dto["id"]) == 1,
             str(MOUCHARDS["notif_resa"]))

    # ── 18. pass `used` -> 409, historique et présence intacts ─────────────
    for r in base["reservations"].docs:
        if r.get("pass_id") and r.get("status") != "cancelled":
            r["validated"] = True
    code, me = await appel(R.referral_me(req_parrain(base)))
    p_avant = json.loads(json.dumps(base["referral_passes"].docs[0]))
    code, r = await patch_offre(base, dto["id"], OFFRE_C, p_avant["version"])
    p_apres = base["referral_passes"].docs[0]
    verifier("O18. Pass `used` : PATCH -> 409 pass_non_modifiable avec le texte EXACT de l'avenant",
             me["passes"][0]["status"] == "used" and code == 409 and r["headers"].get("X-Refus-Raison") == "pass_non_modifiable"
             and r["detail"] == "Cette offre a déjà été utilisée. Tu peux choisir une autre offre pour une prochaine réservation si elle est disponible.",
             str((code, r)))
    verifier("O18b. Historique intact, présences intactes, offre B conservée, version inchangée, rien réécrit",
             p_apres["offer_history"] == p_avant["offer_history"] and p_apres["offer_id"] == OFFRE_B
             and p_apres["version"] == p_avant["version"] and p_apres["events"] == p_avant["events"]
             and all(r["validated"] is True for r in base["reservations"].docs if r.get("pass_id") and r.get("status") != "cancelled"))
    # Présence validée SANS que le pass soit `used` (une seule des deux) : même refus.
    base, occ = base_de_depart(seances_parrain=3)
    _, dto = await creer_pass(base, occ, offer_id=OFFRE_A)
    await appel(R.referral_join(dto["share_token"], Requete(corps_ami())))
    next(r for r in base["reservations"].docs if r.get("pass_role") == "invitee")["validated"] = True
    code, r = await patch_offre(base, dto["id"], OFFRE_B, base["referral_passes"].docs[0]["version"])
    verifier("O18c. UNE présence validée (ami venu, parrain pas encore) : 409 pass_non_modifiable, rien réécrit (ami toujours sur A)",
             code == 409 and r["headers"].get("X-Refus-Raison") == "pass_non_modifiable"
             and base["referral_passes"].docs[0]["offer_id"] == OFFRE_A and len(resas_ami_actives(base)) == 1
             and codes_ami(base)[0]["active"] is not False, str((code, r)))
    # KPI admin sur ce jeu.
    code, kpi = await appel(R.referral_admin_summary(Requete(params={}, entetes=entetes_admin())))
    verifier("Oadmin. /admin/summary : changements_offre, offre_la_plus_choisie {offer_id, name, n}, par_offre",
             code == 200 and kpi["changements_offre"] == 0 and kpi["offre_la_plus_choisie"] == {"offer_id": OFFRE_A, "name": "Essai gratuit", "n": 1}
             and kpi["par_offre"] == {OFFRE_A: 1}, str({k: kpi.get(k) for k in ("changements_offre", "offre_la_plus_choisie", "par_offre")}))

    # ── 19. concurrence : deux PATCH, même version ─────────────────────────
    base, occ = base_de_depart()
    _, dto = await creer_pass(base, occ, offer_id=OFFRE_A)
    r1, r2 = await asyncio.gather(patch_offre(base, dto["id"], OFFRE_B, 1), patch_offre(base, dto["id"], OFFRE_C, 1))
    codes = sorted([r1[0], r2[0]])
    p = base["referral_passes"].docs[0]
    gagnant = r1[1] if r1[0] == 200 else r2[1]
    perdant = r2[1] if r1[0] == 200 else r1[1]
    verifier("O19. Concurrence (locked) : deux PATCH avec version 1 -> exactement un 200 et un 409 conflit_version",
             codes == [200, 409] and perdant["headers"].get("X-Refus-Raison") == "conflit_version", str((r1[0], r2[0])))
    verifier("O19b. État cohérent : l'offre du pass = celle du gagnant, UNE entrée d'historique, version 2",
             p["offer_id"] == gagnant["offer"]["id"] and len(p["offer_history"]) == 1 and p["version"] == 2, str((p["offer_id"], p["version"])))
    # Même course, APRÈS join (chemin avec re-octroi) : le verrou de version tombe avant toute écriture métier.
    base, occ = base_de_depart(seances_parrain=3)
    _, dto = await creer_pass(base, occ, offer_id=OFFRE_A)
    await appel(R.referral_join(dto["share_token"], Requete(corps_ami())))
    v = base["referral_passes"].docs[0]["version"]
    r1, r2 = await asyncio.gather(patch_offre(base, dto["id"], OFFRE_B, v), patch_offre(base, dto["id"], OFFRE_C, v))
    p = base["referral_passes"].docs[0]
    gagnant = r1[1] if r1[0] == 200 else r2[1]
    verifier("O19c. Concurrence (unlocked) : un 200, un 409 conflit_version ; UNE réservation active de l'ami, UN code vivant, "
             "un seul re-octroi, offre = celle du gagnant",
             sorted([r1[0], r2[0]]) == [200, 409] and p["offer_id"] == gagnant["offer"]["id"]
             and len(resas_ami_actives(base)) == 1 and len([d for d in codes_ami(base) if d["active"] is not False]) == 1
             and len(codes_ami(base)) == 2 and len(p["offer_history"]) == 1, str((r1[0], r2[0], p["offer_id"])))

    # ── bonus : panne pendant (b) -> restauration de (a) ───────────────────
    base, occ = base_de_depart(seances_parrain=3)
    _, dto = await creer_pass(base, occ, offer_id=OFFRE_A)
    await appel(R.referral_join(dto["share_token"], Requete(corps_ami())))
    p0 = json.loads(json.dumps(base["referral_passes"].docs[0]))
    ancien_code, ancien_rid = p0["invitee_access_code"], p0["reservations"]["invitee_id"]
    code_avant = json.loads(json.dumps(next(d for d in base["discount_codes"].docs if d["code"] == ancien_code)))
    sub_avant = json.loads(json.dumps(next(d for d in base["subscriptions"].docs if d["code"] == ancien_code)))
    resa_avant = json.loads(json.dumps(next(r for r in base["reservations"].docs if r["id"] == ancien_rid)))
    mouvements_avant = sorted(d["_id"] for d in base["seance_mouvements"].docs)

    async def _seances_en_panne(*a, **k):
        raise RuntimeError("panne simulée pendant le re-octroi")
    SH.seances_consommer = _seances_en_panne
    code, r = await patch_offre(base, dto["id"], OFFRE_B, p0["version"])
    SH.seances_consommer = _mouchard_seances
    p = base["referral_passes"].docs[0]
    code_apres = next(d for d in base["discount_codes"].docs if d["code"] == ancien_code)
    sub_apres = next(d for d in base["subscriptions"].docs if d["code"] == ancien_code)
    resa_apres = next(r for r in base["reservations"].docs if r["id"] == ancien_rid)
    nouveaux = [d for d in codes_ami(base) if d["code"] != ancien_code]
    verifier("Obonus-e. Panne pendant (b) : 500 propre, le pass GARDE l'offre A, invitee_access_code et reservations.invitee_id inchangés, "
             "événement offer_change_failed journalisé, plus de verrou offer_change",
             code == 500 and p["offer_id"] == OFFRE_A and p["invitee_access_code"] == ancien_code
             and p["reservations"]["invitee_id"] == ancien_rid and p["events"][-1]["type"] == "offer_change_failed"
             and not p.get("offer_change") and p["offer_history"] == [], str((code, r, p.get("offer_id"))))
    verifier("Obonus-f. (a) RESTAURÉ : ancien code actif/maxUses/used identiques, forfait identique (status, compteurs), "
             "réservation identique (aucun status cancelled), marques rollback retirées",
             {k: code_apres.get(k) for k in ("active", "maxUses", "used")} == {k: code_avant.get(k) for k in ("active", "maxUses", "used")}
             and {k: sub_apres.get(k) for k in ("status", "remaining_sessions", "total_sessions")}
             == {k: sub_avant.get(k) for k in ("status", "remaining_sessions", "total_sessions")}
             and resa_apres == resa_avant and "pass_duo_rollback" not in code_apres and "pass_duo_rollback" not in sub_apres,
             str((code_apres, sub_apres))[:300])
    verifier("Obonus-g. Mouvements SEANCES revenus à l'identique (restitution effacée), verrou d'essai REPRIS (2 clés actives), "
             "le code né du re-octroi raté est neutralisé (jamais supprimé), aucune réservation orpheline",
             sorted(d["_id"] for d in base["seance_mouvements"].docs) == mouvements_avant and len(verrous_actifs(base)) == 2
             and len(nouveaux) == 1 and nouveaux[0]["active"] is False and nouveaux[0].get("pass_duo_rollback_motif") == "pass_duo_offer_change_echec"
             and len(resas_ami_actives(base)) == 1 and resas_ami_actives(base)[0]["id"] == ancien_rid,
             str((sorted(d["_id"] for d in base["seance_mouvements"].docs), [ (d["code"], d["active"]) for d in codes_ami(base)])))
    code, d = await appel(R.referral_me(req_parrain(base)))
    verifier("Obonus-h. /me après la panne : le pass est toujours unlocked, 2 billets, offre A, la ligne « Changement d'offre annulé » dans l'historique",
             d["passes"][0]["status"] == "unlocked" and len(d["passes"][0]["tickets"]) == 2 and d["passes"][0]["offer"]["id"] == OFFRE_A
             and any(l["type"] == "offer_change_failed" for l in d["history"]), str(d["passes"][0]["status"]))
    code, d = await patch_offre(base, dto["id"], OFFRE_B, base["referral_passes"].docs[0]["version"])
    verifier("Obonus-i. Le même changement, la panne levée : 200, offre B, une réservation active, ancien code neutralisé (l'état restauré était sain)",
             code == 200 and d["offer"]["id"] == OFFRE_B and len(resas_ami_actives(base)) == 1
             and next(c for c in codes_ami(base) if c["code"] == ancien_code)["active"] is False, str((code, d.get("offer"))))

    # ── bonus : join avec offer_id = changement invitee AVANT l'octroi ─────
    base, occ = base_de_depart(seances_parrain=3)
    _, dto = await creer_pass(base, occ, offer_id=OFFRE_A)
    code, rep = await appel(R.referral_join(dto["share_token"], Requete(corps_ami(offer_id=OFFRE_C))))
    p = base["referral_passes"].docs[0]
    verifier("Obonus-j. Join avec `offer_id: C` (≠ A du pass) : changement invitee AVANT l'octroi, forfait né de C, historique A->C invitee, "
             "un seul octroi, aucun rollback",
             code == 200 and rep["status"] == "unlocked" and p["offer_id"] == OFFRE_C and subs_ami(base)[0].get("offer_id") == OFFRE_C
             and p["offer_history"][-1]["changed_by"] == "invitee" and len(MOUCHARDS["paiements"]) == 1
             and len(codes_ami(base)) == 1 and rep["offer"]["id"] == OFFRE_C, str((code, p.get("offer_id"))))
    code, rep = await appel(R.referral_join(dto["share_token"], Requete(corps_ami(offer_id=OFFRE_D))))
    verifier("Obonus-k. Rejeu idempotent du même ami avec une offre NON autorisée : 200 idempotent AVANT toute validation d'offre (rien n'a changé)",
             code == 200 and rep["status"] == "unlocked" and base["referral_passes"].docs[0]["offer_id"] == OFFRE_C, str((code, rep.get("status"))))
    base, occ = base_de_depart(seances_parrain=3)
    _, dto = await creer_pass(base, occ, offer_id=OFFRE_A)
    code, rep = await appel(R.referral_join(dto["share_token"], Requete(corps_ami(offer_id=OFFRE_PAYANTE))))
    verifier("Obonus-l. Join avec une offre PAYANTE : 400 offre_payante, aucun octroi, pass toujours sans invité",
             code == 400 and rep["headers"].get("X-Refus-Raison") == "offre_payante" and not MOUCHARDS["paiements"]
             and base["referral_passes"].docs[0]["invitee"] is None, str((code, rep)))
    # PATCH par un AUTRE abonné : 404, comme cancel.
    autre = jeton_espace(base, "BASS-DUO-02", "marc.parrain@exemple.test")
    code, r = await patch_offre(base, dto["id"], OFFRE_B, 1, tok=autre)
    verifier("Obonus-m. PATCH par un AUTRE abonné (jeton valide, pas le sien) : 404, rien n'a changé",
             code == 404 and base["referral_passes"].docs[0]["offer_id"] == OFFRE_A, str(code))
    code, r = await appel(R.referral_changer_offre(dto["id"], Requete({"offer_id": OFFRE_B, "version": 1}, {"X-User-Email": ADMIN})))
    verifier("Obonus-n. X-User-Email seul = porte PUBLIQUE (l'id n'est pas un share_token) : 404, jamais une identité",
             code == 404 and base["referral_passes"].docs[0]["offer_id"] == OFFRE_A, str(code))
    base, occ = base_de_depart(drapeau=False)
    code, r = await patch_offre(base, "x", OFFRE_B, 1)
    verifier("Obonus-o. Drapeau OFF : PATCH offre -> 404 parrainage_duo_desactive", code == 404 and r.get("detail") == "parrainage_duo_desactive")

    # ── moteur pur ─────────────────────────────────────────────────────────
    verifier("Opur-a. offre_eligible : inactive (None / invisible / archivée), payante, autre coach, OK (sans propriétaire ↔ '' / None / absent)",
             E.offre_eligible(None, None) == (False, "offre_inactive")
             and E.offre_eligible({"id": "x", "price": 0, "visible": False}, None) == (False, "offre_inactive")
             and E.offre_eligible({"id": "x", "price": 0, "archived": True}, None) == (False, "offre_inactive")
             and E.offre_eligible({"id": "x", "price": 15}, None) == (False, "offre_payante")
             and E.offre_eligible({"id": "x", "price": 0, "coach_id": "a@b.c"}, None) == (False, "offre_autre_coach")
             and E.offre_eligible({"id": "x", "price": 0, "coach_id": None}, "a@b.c") == (False, "offre_autre_coach")
             and E.offre_eligible({"id": "x", "price": 0, "coach_id": ""}, None) == (True, None)
             and E.offre_eligible({"id": "x", "price": 0.0, "coach_id": "A@B.C "}, "a@b.c") == (True, None))
    verifier("Opur-b. dto_offre : pack_sessions '10' -> 10 séances offertes ; duration 1 week -> « 1 semaine » ; 3 months -> « 3 mois »",
             E.dto_offre({"id": "x", "name": "P", "price": 0, "pack_sessions": "10"})["benefit"] == "10 séances offertes"
             and E.validity_offre({"duration_value": 1, "duration_unit": "weeks"}) == "1 semaine"
             and E.validity_offre({"duration_value": 3, "duration_unit": "months"}) == "3 mois"
             and E.validity_offre({"duration_value": 3, "duration_unit": "years"}) is None)
    ok_m = (E.pass_modifiable_pour_offre({"status": "locked"}) == (True, None)
            and E.pass_modifiable_pour_offre({"status": "used"}) == (False, "used")
            and E.pass_modifiable_pour_offre({"status": "expired"}) == (False, "expired")
            and E.pass_modifiable_pour_offre({"status": "cancelled"}) == (False, "cancelled")
            and E.pass_modifiable_pour_offre({"status": "unlocked", "reservations": {"sponsor_id": "s", "invitee_id": "i"}},
                                             [{"id": "i", "validated": True}]) == (False, "presence_validee")
            and E.pass_modifiable_pour_offre({"status": "unlocked", "reservations": {"sponsor_id": "s", "invitee_id": "i"}},
                                             [{"id": "zz", "validated": True}]) == (True, None)
            and E.pass_modifiable_pour_offre({"status": "locked"}, None, statut="used") == (False, "used"))
    verifier("Opur-c. pass_modifiable_pour_offre : 7 cas (statut dérivé prioritaire, présence hors pass ignorée) + texte exact pour used",
             ok_m and E.texte_non_modifiable("used") == E.TEXTE_OFFRE_UTILISEE)
    k = E.kpi_offres([{"offer_id": "a", "offer_snapshot": {"name": "A"}, "offer_history": [{}, {}]},
                      {"offer_id": "b", "offer_snapshot": {"name": "B"}, "offer_history": [{}]},
                      {"offer_id": "a", "offer_snapshot": {"name": "A"}}, {"status": "x"}])
    verifier("Opur-d. kpi_offres : changements_offre 3, offre_la_plus_choisie a/A/2, par_offre {a:2, b:1}",
             k == {"changements_offre": 3, "offre_la_plus_choisie": {"offer_id": "a", "name": "A", "n": 2}, "par_offre": {"a": 2, "b": 1}}, str(k))
    verifier("Opur-e. ligne_historique_offre + entree_historique_offre (changed_by inconnu refusé)",
             E.ligne_historique_offre({"from_name": "A", "to_name": "B", "changed_at": "t"}, "p")["label"] == "Offre modifiée : A → B"
             and _leve(lambda: E.entree_historique_offre({}, {}, "pirate", "t")))


def _leve(fn):
    try:
        fn()
    except ValueError:
        return True
    return False


async def _debit_429(base, occ):
    """20 créations tolérées par heure et par IP ; la 21e est refusée SANS écriture."""
    ip = "198.51.100.%d" % (uuid.uuid4().int % 250 + 1)
    n_avant = len(base["referral_passes"].docs)
    codes = []
    for _ in range(21):
        c, _ = await appel(R.referral_creer_pass(Requete({"course_id": COURS_DUO, "occurrence": occ, "offer_id": OFFRE_A},
                                                         {"x-espace-token": jeton_espace(base)}, ip=ip)))
        codes.append(c)
    return codes[:20].count(429) == 0 and codes[20] == 429 and len(base["referral_passes"].docs) == n_avant


def _ordre_ast():
    """Ligne du PREMIER appel de chaque fonction clé, par fonction hôte :
    `octroi` (_octroyer_essai), `join` (referral_join), `reserver_ami`
    (_reserver_ami), `changement` (_changer_offre_apres_join)."""
    src = io.open(os.path.join(RACINE, "api", "routes", "referral_routes.py"), encoding="utf-8").read()
    arbre = ast.parse(src)
    cibles = ("_essai4_garde", "_essai1_garde", "_process_successful_payment", "_reserver_seance_duo",
              "_debloquer_ou_bloquer", "_octroyer_essai", "_reserver_ami")
    hotes = {"octroi": "_octroyer_essai", "join": "referral_join", "reserver_ami": "_reserver_ami",
             "changement": "_changer_offre_apres_join"}
    sortie = {}
    for cle, nom_fn in hotes.items():
        fn = [n for n in ast.walk(arbre) if isinstance(n, ast.AsyncFunctionDef) and n.name == nom_fn][0]
        lignes = {}
        for n in ast.walk(fn):
            if isinstance(n, ast.Call):
                nom = n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
                if nom in cibles and nom not in lignes:
                    lignes[nom] = n.lineno
        sortie[cle] = lignes
    return sortie


# ═══════════════════════════════════════════════════════════════════════════
# V538 — L'APERÇU DU PARTAGE : une invitation, pas un lien anonyme
# ═══════════════════════════════════════════════════════════════════════════
def partie_v538():
    import api.routes.referral_engine as _M
    SRC_SRV = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
    SRC_CENTRE = io.open(os.path.join(RACINE, "frontend", "src", "components",
                                      "parrainage", "CentreParrainage.js"), encoding="utf-8").read()
    FRONT = "https://afroboost.com"

    # ── CAS C : le lien partagé est la page d'aperçu ─────────────────────────
    verifier("V538-C. `partage_url` = /api/share/duo/<token> (et jamais la page React)",
             _M.partage_url(FRONT, "TOK") == "https://afroboost.com/api/share/duo/TOK"
             and _M.invite_url(FRONT, "TOK") == "https://afroboost.com/duo/TOK")

    # ── CAS D/E : les balises et le prénom ───────────────────────────────────
    verifier("V538-D. la route d'aperçu produit og:title / og:description / og:image / og:url / twitter:*",
             all(_b in SRC_SRV for _b in ('@api_router.get("/share/duo/{share_token}")',
                                          'property="og:title"', 'property="og:description"',
                                          'property="og:image"', 'property="og:url"',
                                          'property="og:type"', 'name="twitter:card"',
                                          'name="twitter:title"', 'name="twitter:description"',
                                          'name="twitter:image"')))
    verifier("V538-E. le titre porte le PRÉNOM de l'invitant ; sans prénom, une formule qui reste vraie",
             _M.og_titre_invitation("Bassi") == "Bassi t'invite à Afroboost"
             and _M.og_titre_invitation("") == "Un membre Afroboost t'invite"
             and _M.og_titre_invitation(None) == "Un membre Afroboost t'invite")
    _d = _M.og_description_invitation("Bassi", "Afroboost Dimanche", "2026-09-27T18:30:00", "Cours d'essai GRATUIT")
    verifier("V538-E2. la description dit qui, quoi, quand et ce que l'ami reçoit",
             "Bassi" in _d and "Afroboost Dimanche" in _d and "27" in _d and "essai" in _d.lower(), _d)
    verifier("V538-E3. sans offre nommée, la promesse reste celle du Pass Duo",
             "offert" in _M.og_description_invitation("Bassi", "Cours", None, ""))

    # ── CAS F/G/H/I : la priorité des médias ─────────────────────────────────
    _off_thumb = {"thumbnail": "/api/files/a/img.jpg", "images": ["/api/files/b/autre.jpg"],
                  "videoUrl": "/api/files/c/video_x.mp4"}
    verifier("V538-F. priorité 1 : la miniature (poster) du média de l'offre",
             _M.media_apercu(_off_thumb, {}, {}) == "/api/files/a/img.jpg")
    verifier("V538-F2. une URL de VIDÉO n'est jamais rendue comme image (l'aperçu serait vide)",
             _M.media_apercu({"videoUrl": "/api/files/c/video_x.mp4"}, {}, {}) == ""
             and _M.media_apercu({"thumbnail": "https://res.cloudinary.com/x/video/upload/v1/a.mp4"}, {}, {}) == "")
    verifier("V538-F3. le champ `videoUrl` qui contient en réalité une IMAGE est utilisé (8 offres de prod)",
             _M.media_apercu({"videoUrl": "/api/files/d/image_d53c.jpg"}, {}, {}) == "/api/files/d/image_d53c.jpg")
    verifier("V538-G. priorité 2/3 : images de l'offre, puis image de la séance",
             _M.media_apercu({"images": ["/api/files/b/autre.jpg"]}, {}, {}) == "/api/files/b/autre.jpg"
             and _M.media_apercu({}, {"image": "/api/files/e/cours.jpg"}, {}) == "/api/files/e/cours.jpg")
    verifier("V538-H. priorité 4 : la bannière du concept quand l'offre et la séance n'ont rien",
             _M.media_apercu({}, {}, {"heroImageUrl": "/api/files/f/hero.png"}) == "/api/files/f/hero.png")
    verifier("V538-I. rien nulle part -> chaîne vide, et la route pose le visuel Afroboost",
             _M.media_apercu({}, {}, {}) == "" and _M.media_apercu(None, None, None) == ""
             and 'or f"{FRONT}/logo512.png"' in SRC_SRV)

    # ── CAS J/K/L : un seul lien pour tous les boutons ───────────────────────
    verifier("V538-J/K/L. WhatsApp, Copier, QR et Partager partagent la MÊME URL (`share_url`, repli `invite_url`)",
             "const lienInvite = passLien ? (passLien.share_url || passLien.invite_url) : '';" in SRC_CENTRE
             and "copier(lienInvite)" in SRC_CENTRE and "url: lienInvite" in SRC_CENTRE
             # `passLien.invite_url` ne subsiste QUE comme repli dans la ligne ci-dessus
             and SRC_CENTRE.count("passLien.invite_url") == 1)

    # ── CAS A/B : l'ordre du parcours ────────────────────────────────────────
    verifier("V538-A/B. sans Pass, le CTA « Créer mon Pass Duo » est rendu AVANT le bloc de partage",
             'data-testid="creer-pass-cta"' in SRC_CENTRE
             and "Créer mon Pass Duo" in SRC_CENTRE
             and SRC_CENTRE.index('data-testid="creer-pass-cta"') < SRC_CENTRE.index('data-testid="inviter-un-ami"')
             and "{!lienInvite ? (" in SRC_CENTRE)

    # ── CAS N/O : les compteurs après annulation ─────────────────────────────
    _passes = [{"id": "p1", "invitee": {"name": "A"}, "opened_at": "x", "status": "friend_registered"},
               {"id": "p2", "invitee": {"name": "B"}, "opened_at": "x", "status": "cancelled"}]
    _inv = [{"id": "i1", "pass_id": "p1", "channel": "whatsapp"},
            {"id": "i2", "pass_id": "p2", "channel": "whatsapp"},
            {"id": "i3", "pass_id": "p2", "channel": "copy"}]
    _st = {"p1": "friend_registered", "p2": "cancelled"}
    _s538 = _M.stats_parrain(_passes, _inv, _st)
    verifier("V538-N. un Pass annulé ne gonfle plus « Mes résultats » : 3 invitations dont 2 annulées -> 1",
             _s538["invited"] == 1 and _s538["joined"] == 1 and _s538["opened"] == 1, _s538)
    _st2 = {"p1": "friend_registered", "p2": "expired"}
    verifier("V538-N2. même règle pour un Pass expiré",
             _M.stats_parrain(_passes, _inv, _st2)["invited"] == 1)
    verifier("V538-N3. sans annulation, les compteurs sont inchangés (aucune régression)",
             _M.stats_parrain([_passes[0]], [_inv[0]], {"p1": "friend_registered"})["invited"] == 1
             and _M.stats_parrain(_passes, _inv, {"p1": "waiting", "p2": "waiting"})["invited"] == 3)
    verifier("V538-O. l'historique n'est PAS touché : `kpi_parrainage` continue de tout compter",
             _M.kpi_parrainage(_passes, _inv, None, _st)["kpi"]["invitations"] == 3
             and _M.kpi_parrainage(_passes, _inv, None, _st)["kpi"]["annules"] == 1)
    verifier("V538-N4. l'écran relit `/me` après une annulation (les compteurs ne restent pas figés)",
             "rafraichirResultats()" in SRC_CENTRE
             and "poserPass(r.data); return rafraichirResultats();" in SRC_CENTRE)

    # ── CAS confidentialité + jeton inconnu ──────────────────────────────────
    _bloc = SRC_SRV[SRC_SRV.index('@api_router.get("/share/duo/{share_token}")'):
                    SRC_SRV.index('@api_router.get("/sitemap.xml")')]
    # Le CODE seul (les commentaires, eux, ont le droit de NOMMER ce qu'ils excluent).
    # Le CODE seul : on retire la docstring d'ouverture (elle NOMME ce qu'elle exclut)
    # et les commentaires.
    _sans_doc = _bloc.split('"""', 2)
    _corps = _sans_doc[2] if len(_sans_doc) == 3 else _bloc
    _code = "\n".join(_l for _l in _corps.splitlines() if not _l.strip().startswith("#"))
    verifier("V538-P. l'aperçu n'expose AUCUNE donnée privée (ni e-mail, ni téléphone, ni code d'accès)",
             not any(_m in _code for _m in ("email", "whatsapp", "phone", "access_code",
                                            "invitee_access_code", "subscription_code")),
             [_m for _m in ("email", "whatsapp", "phone", "access_code") if _m in _code])
    verifier("V538-Q. jeton inconnu, vide ou démesuré -> redirection silencieuse, jamais un oracle",
             "if not _tok or len(_tok) > 128:" in _bloc and _bloc.count("RedirectResponse(url=FRONT, status_code=302)") == 2)
    verifier("V538-R. tout ce qui vient de la base est ÉCHAPPÉ avant d'entrer dans le HTML",
             _bloc.count("_html.escape(") == 5 and "quote=True" in _bloc)
    verifier("V538-R2. un vrai navigateur est renvoyé sur la page d'invitation (meta refresh + lien)",
             'http-equiv="refresh" content="0;url={e_cible}"' in _bloc and 'href="{e_cible}"' in _bloc)


# ═══════════════════════════════════════════════════════════════════════════
# V539 — L'AMI CHOISIT SA SÉANCE (règles pures + structure des routes)
# ═══════════════════════════════════════════════════════════════════════════
def partie_v539():
    import api.routes.referral_engine as _M
    from datetime import datetime as _dt, timezone as _tz
    SRC_R = io.open(os.path.join(RACINE, "api", "routes", "referral_routes.py"), encoding="utf-8").read()
    SRC_INV = io.open(os.path.join(RACINE, "frontend", "src", "components",
                                   "parrainage", "InvitationDuo.js"), encoding="utf-8").read()
    SRC_MODAL = io.open(os.path.join(RACINE, "frontend", "src", "components",
                                     "SessionsModal.js"), encoding="utf-8").read()
    SRC_UTIL = io.open(os.path.join(RACINE, "frontend", "src", "utils", "parrainage.js"), encoding="utf-8").read()
    _now = _dt(2026, 9, 22, 12, 0, tzinfo=_tz.utc)
    A, B = "2026-09-27T18:30:00", "2026-10-04T18:30:00"

    # ── La règle : la date vient de la liste du serveur, et n'est pas passée ──
    verifier("V539-1. une occurrence de la liste du serveur, à venir -> acceptée",
             _M.occurrence_choisissable(B, [A, B], _now) == (B, ""))
    verifier("V539-2. une date hors de la liste -> refusée (jamais une date tapée à la main)",
             _M.occurrence_choisissable("2026-12-24T20:00:00", [A, B], _now) == ("", _M.REFUS_OCCURRENCE_INCONNUE))
    verifier("V539-3. une occurrence déjà passée -> refusée",
             _M.occurrence_choisissable("2026-09-01T18:30:00", ["2026-09-01T18:30:00"], _now)
             == ("", _M.REFUS_OCCURRENCE_PASSEE))
    verifier("V539-4. vide, None, liste vide -> refus, jamais une exception",
             _M.occurrence_choisissable("", [A], _now)[1] == _M.REFUS_OCCURRENCE_INCONNUE
             and _M.occurrence_choisissable(None, [A], _now)[1] == _M.REFUS_OCCURRENCE_INCONNUE
             and _M.occurrence_choisissable(A, [], _now)[1] == _M.REFUS_OCCURRENCE_INCONNUE)

    # ── L'historique : même vocabulaire que celui des offres ─────────────────
    _e = _M.entree_historique_seance(A, B, "invitee", "2026-09-22T12:00:00Z")
    verifier("V539-5. l'historique dit d'où vers où, par qui et quand",
             _e == {"from_occurrence": A, "to_occurrence": B,
                    "changed_at": "2026-09-22T12:00:00Z", "changed_by": "invitee"}, _e)
    verifier("V539-6. un auteur inconnu est refusé (même garde que l'historique des offres)",
             _refuse_valueerror(lambda: _M.entree_historique_seance(A, B, "pirate", "x")))
    verifier("V539-7. la ligne lisible : « Séance modifiée : … -> … »",
             _M.ligne_historique_seance(_e) == "Séance modifiée : dimanche 27 septembre à 18:30 -> dimanche 4 octobre à 18:30",
             _M.ligne_historique_seance(_e))

    # ── La route : deux portes, avant inscription seulement ─────────────────
    _bloc = SRC_R[SRC_R.index("async def _changer_seance("):SRC_R.index("# ═══════════════════════════════════════════════════════════════════════════\n# Routes — publiques")]
    verifier("V539-8. la route existe, en PATCH, et rend le DTO public à l'ami",
             '@router.patch("/pass/{identifiant}/occurrence")' in SRC_R
             and "E.dto_public(_p, await _statut_reel(_p, _now), _now," in SRC_R)
    verifier("V539-9. l'ami ne peut changer la séance qu'AVANT son inscription (409 sinon)",
             'if _p.get("invitee") or _s not in E.ETATS_OUVERTS_AU_JOIN:' in _bloc
             and "des billets ont déjà été émis" in _bloc)
    verifier("V539-10. la concurrence est gardée par la `version` (même verrou que l'offre)",
             "if int(version) != E.version_pass(pass_doc):" in _bloc
             and "_filtre_version(pass_doc[\"id\"], version)" in _bloc
             and "REFUS_CONFLIT_VERSION" in _bloc)
    verifier("V539-11. l'occurrence est relue dans la liste DU SERVEUR pour ce cours",
             "_dispos = _occurrences(_course)" in _bloc
             and "E.occurrence_choisissable(occurrence, _dispos, _maintenant())" in _bloc)
    verifier("V539-12. choisir la séance déjà retenue n'écrit rien (idempotent)",
             'if _cible == str(pass_doc.get("occurrence") or ""):' in _bloc and "return pass_doc" in _bloc)
    verifier("V539-13. le pass change de DATE, pas de cours, et son expiration suit",
             '"occurrence": _cible, "expires_at": _cible' in _bloc
             and "course_id" not in _bloc.split("find_one_and_update")[1][:400])
    verifier("V539-14. un cours archivé ou masqué -> 410, jamais un choix impossible",
             'if not _course or _course.get("archived") is True or _course.get("visible") is False:' in _bloc)
    verifier("V539-15. l'historique et l'événement sont écrits dans la même transaction logique",
             '"occurrence_history": _entree' in _bloc and "E.EVENEMENT_SEANCE" in _bloc)
    verifier("V539-16. la page publique rend les séances proposables (liste serveur)",
             '_dto["occurrences"] = await _occurrences_du_pass(_p)' in SRC_R
             and "async def _occurrences_du_pass(pass_doc)" in SRC_R)
    verifier("V539-17. cours indisponible -> liste vide (l'écran montre la séance actuelle, sans promesse)",
             'return []' in SRC_R[SRC_R.index("async def _occurrences_du_pass"):SRC_R.index("async def _pass_par_token")])

    # ── Le navigateur : réutilisation, pas de second calendrier ─────────────
    verifier("V539-18. c'est LE calendrier de la page d'accueil qui est réutilisé (aucun composant neuf)",
             "import SessionsModal from '../SessionsModal';" in SRC_INV
             and not os.path.exists(os.path.join(RACINE, "frontend", "src", "components", "parrainage", "CalendrierDuo.js")))
    verifier("V539-19. il est alimenté par la liste du serveur, sans appeler l'agenda du site",
             "occurrencesFournies={seancesProposables}" in SRC_INV
             and "if (Array.isArray(occurrencesFournies)) {" in SRC_MODAL
             and "setOccurrences(occurrencesFournies);" in SRC_MODAL)
    verifier("V539-20. la page d'accueil n'est PAS modifiée : sans la prop, l'agenda reste la source",
             "const res = await axios.get(`${API}/sessions/agenda`);" in SRC_MODAL
             and "occurrencesFournies = null" in SRC_MODAL
             and "libelleAction = 'Réserver'" in SRC_MODAL)
    verifier("V539-21. la carte dit « Séance choisie » et propose « Choisir une autre séance »",
             ">Séance choisie<" in SRC_INV and "Choisir une autre séance" in SRC_INV
             and 'data-testid="invitation-changer-seance"' in SRC_INV
             and "Cette date ne te convient pas ?" in SRC_INV)
    verifier("V539-22. une seule séance proposée -> aucun bouton (pas de faux choix)",
             "seancesProposables.length > 1" in SRC_INV)
    verifier("V539-23. après inscription, la carte reste en lecture (aucun changement possible)",
             "!dejaRejoint && seancesProposables.length > 1" in SRC_INV)
    verifier("V539-24. le client envoie l'occurrence ET la version, sur la route dédiée",
             "export function changerSeance({ passId, token, occurrence, version, headers })" in SRC_UTIL
             and "/occurrence`," in SRC_UTIL and "version: Number(version) || 1" in SRC_UTIL)
    verifier("V539-25. les dates illisibles sont écartées avant d'atteindre le calendrier",
             "if (!d || Number.isNaN(d.getTime())) return null;" in SRC_UTIL)


def _refuse_valueerror(f):
    try:
        f()
        return False
    except ValueError:
        return True
    except Exception:  # noqa: BLE001
        return False


def main():
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())
    except Exception:
        pass
    asyncio.get_event_loop().run_until_complete(principal())
    partie_v538()
    partie_v539()
    ok = 0
    print("=" * 78)
    print("V534 / V534b — PASS DUO : %d vérifications" % len(RESULTATS))
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
