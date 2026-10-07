# -*- coding: utf-8 -*-
"""P1A (07/10/2026) — routes partenaires : plus d'identité prise dans un en-tête ou un corps.

Audit marketing du 07/10 : `POST /session-to-credit` modifiait le compte d'un coach à partir de
la seule adresse du corps ; `GET /check-partner/{email}` révélait nom et crédits à un anonyme ;
14 routes d'administration de `coach_routes.py` (lister / désactiver / supprimer un coach, purger,
migrer, ajouter des crédits…) croyaient l'en-tête `X-User-Email` — or l'adresse du super-admin est
publique. Ce banc prouve, sur les VRAIES fonctions de route et une base en mémoire :

  * non connecté → refusé ;
  * connecté sans droit (autre coach, jeton abonné, en-tête forgé) → refusé ;
  * autorisé → fonctionne ;
  * changer l'e-mail (corps ou en-tête) ne permet JAMAIS d'agir sur le compte d'un autre coach.

Hors ligne : aucune base réelle, aucun réseau, aucun e-mail.
Lancer : python3 -m pytest tests/test_p1a_securite_partenaires.py -q
"""
import asyncio
import os
import sys

os.environ["JWT_SECRET"] = "secret-de-test-p1a"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p1a-inexistant:27017")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import jwt as pyjwt
import pytest
from fastapi import HTTPException

import api.server as S
import api.routes.coach_routes as C

ADMIN = S.SUPER_ADMIN_EMAILS[0]
A = "coach.a@exemple.test"
B = "coach.b@exemple.test"
INCONNU = "personne@exemple.test"


# ───────────────────────── base en mémoire (supporte $set et $inc) ─────────────────────────
def _correspond(doc, requete):
    for cle, attendu in (requete or {}).items():
        if isinstance(attendu, dict):
            if "$exists" in attendu and (cle in doc) != bool(attendu["$exists"]):
                return False
            if "$in" in attendu and doc.get(cle) not in attendu["$in"]:
                return False
        elif doc.get(cle) != attendu:
            return False
    return True


class _Curseur:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, n=None):
        return list(self.docs)[:n] if n else list(self.docs)


class _Coll:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    def find(self, requete=None, proj=None):
        return _Curseur([{k: v for k, v in d.items() if k != "_id"} for d in self.docs if _correspond(d, requete)])

    async def find_one(self, requete=None, proj=None):
        for d in self.docs:
            if _correspond(d, requete):
                return {k: v for k, v in d.items() if k != "_id"}
        return None

    async def update_one(self, requete, maj, upsert=False):
        for d in self.docs:
            if _correspond(d, requete):
                d.update(maj.get("$set", {}))
                for k, v in maj.get("$inc", {}).items():
                    d[k] = d.get(k, 0) + v
                return type("R", (), {"modified_count": 1, "matched_count": 1})()
        return type("R", (), {"modified_count": 0, "matched_count": 0})()

    async def delete_one(self, requete):
        for i, d in enumerate(self.docs):
            if _correspond(d, requete):
                del self.docs[i]
                return type("R", (), {"deleted_count": 1})()
        return type("R", (), {"deleted_count": 0})()

    async def delete_many(self, requete):
        return type("R", (), {"deleted_count": 0})()


class _Base:
    def __init__(self, strict=True):
        self.coaches = _Coll([
            {"id": "id-a", "email": A, "name": "Coach A", "credits": 3, "sessions_available": 2, "is_active": True},
            {"id": "id-b", "email": B, "name": "Coach B", "credits": 5, "sessions_available": 4, "is_active": True},
        ])
        self.users_auth = _Coll([{"email": "en.attente@exemple.test", "pending_validation": True, "name": "X"}])
        self.feature_flags = _Coll([{"id": "feature_flags", "SUPERADMIN_JWT_STRICT": strict, "REQUIRE_COACH_JWT": strict}])
        self.coach_packs = _Coll()

    def __getitem__(self, nom):
        return getattr(self, nom)


class _Req:
    def __init__(self, jeton=None, entete=None, corps=None):
        self.headers = {}
        if jeton:
            self.headers["Authorization"] = "Bearer " + jeton
        if entete:
            self.headers["X-User-Email"] = entete
        self._corps = corps or {}
        self.headers = _H(self.headers)

    async def json(self):
        return dict(self._corps)


class _H(dict):
    def get(self, cle, defaut=""):
        for k, v in self.items():
            if k.lower() == str(cle).lower():
                return v
        return defaut


def jeton(email, type_=None):
    p = {"email": email}
    if type_:
        p["type"] = type_
    return pyjwt.encode(p, os.environ["JWT_SECRET"], algorithm="HS256")


def appel(coro):
    """(résultat, code HTTP ou None) — distingue un refus propre d'un plantage."""
    try:
        r = asyncio.run(coro)
        code = getattr(r, "status_code", None)
        return r, code
    except HTTPException as e:
        return None, e.status_code


@pytest.fixture()
def base(monkeypatch):
    b = _Base(strict=True)
    monkeypatch.setattr(S, "db", b)
    monkeypatch.setattr(C, "db", b)
    return b


def coach(b, email):
    return next(d for d in b.coaches.docs if d["email"] == email)


# ════════════════════ 1. POST /session-to-credit ════════════════════
def test_session_to_credit_anonyme_refuse(base):
    _r, code = appel(S.convert_session_to_credit(_Req(corps={"email": A})))
    assert code in (401, 403)
    assert coach(base, A)["sessions_available"] == 2 and coach(base, A)["credits"] == 3


def test_session_to_credit_entete_forge_refuse(base):
    _r, code = appel(S.convert_session_to_credit(_Req(entete=A, corps={"email": A})))
    assert code in (401, 403)
    assert coach(base, A)["sessions_available"] == 2


def test_session_to_credit_jeton_abonne_refuse(base):
    _r, code = appel(S.convert_session_to_credit(_Req(jeton=jeton(A, "subscriber"), corps={"email": A})))
    assert code in (401, 403)


def test_session_to_credit_autre_coach_refuse(base):
    """Le cœur : un coach connecté ne touche pas au compte d'un autre en changeant l'e-mail."""
    _r, code = appel(S.convert_session_to_credit(_Req(jeton=jeton(A), corps={"email": B})))
    assert code == 403
    assert coach(base, B)["sessions_available"] == 4 and coach(base, B)["credits"] == 5


def test_session_to_credit_autorise(base):
    r, code = appel(S.convert_session_to_credit(_Req(jeton=jeton(A), corps={"email": A})))
    assert code is None and r["success"] is True
    assert coach(base, A)["sessions_available"] == 1 and coach(base, A)["credits"] == 4
    r, code = appel(S.convert_session_to_credit(_Req(jeton=jeton(A))))          # corps sans e-mail : son compte
    assert code is None and coach(base, A)["sessions_available"] == 0


def test_session_to_credit_inconnu_signe_refuse(base):
    _r, code = appel(S.convert_session_to_credit(_Req(jeton=jeton(INCONNU), corps={"email": INCONNU})))
    assert code in (403, 404)


# ════════════════════ 2. GET /check-partner/{email} ════════════════════
def test_check_partner_ne_revele_que_oui_non(base):
    r, code = appel(S.check_if_partner(A))
    assert code is None and r == {"is_partner": True}, "ni nom, ni crédits, ni e-mail renvoyés"
    r, _ = appel(S.check_if_partner(INCONNU))
    assert r == {"is_partner": False}
    r, _ = appel(S.check_if_partner(ADMIN))
    assert r == {"is_partner": True}


# ════════════════════ 3. Routes d'administration (super-admin) ════════════════════
@pytest.mark.parametrize("nom,fabrique", [
    ("add-credits", lambda r: C.add_coach_credits(r)),
    ("pending-coaches", lambda r: C.list_pending_coaches(r)),
    ("admin/coaches", lambda r: C.get_coaches(r)),
    ("toggle", lambda r: C.toggle_coach_status("id-b", r)),
    ("delete", lambda r: C.delete_coach("id-b", r)),
])
def test_admin_entete_forge_refuse(base, nom, fabrique):
    """L'adresse du super-admin est publique : l'écrire dans l'en-tête ne donne plus rien."""
    corps = {"coach_email": B, "credits": 10}
    _r, code = appel(fabrique(_Req(entete=ADMIN, corps=corps)))
    assert code == 403, nom
    _r, code = appel(fabrique(_Req(jeton=jeton(A), corps=corps)))          # coach connecté, pas admin
    assert code == 403, nom
    _r, code = appel(fabrique(_Req(corps=corps)))                          # anonyme
    assert code == 403, nom
    assert coach(base, B)["credits"] == 5 and coach(base, B)["is_active"] is True


def test_admin_jeton_signe_autorise(base):
    r, code = appel(C.add_coach_credits(_Req(jeton=jeton(ADMIN), corps={"coach_email": B, "credits": 10})))
    assert code is None and r["credits_total"] == 15
    r, code = appel(C.list_pending_coaches(_Req(jeton=jeton(ADMIN))))
    assert code is None and r["count"] == 1
    r, code = appel(C.get_coaches(_Req(jeton=jeton(ADMIN))))
    assert code is None and len(r) == 2


def test_admin_mode_strict_eteint_garde_le_comportement_historique(monkeypatch):
    """Interrupteur d'urgence : SUPERADMIN_JWT_STRICT=false → règle d'avant (en-tête), rien d'autre."""
    b = _Base(strict=False)
    monkeypatch.setattr(S, "db", b)
    monkeypatch.setattr(C, "db", b)
    r, code = appel(C.get_coaches(_Req(entete=ADMIN)))
    assert code is None and len(r) == 2


# ════════════════════ 4. Routes coach (identité du coach connecté) ════════════════════
def test_profil_coach_entete_forge_refuse_et_jeton_lit_son_profil(base):
    _r, code = appel(C.get_coach_profile(_Req(entete=B)))
    assert code in (401, 403)
    r, code = appel(C.get_coach_profile(_Req(jeton=jeton(A), entete=B)))   # en-tête B ignoré : le jeton fait foi
    assert code is None and r["email"] == A


def test_update_profil_ne_touche_que_son_compte(base):
    r, code = appel(C.update_coach_profile(_Req(jeton=jeton(A), entete=B, corps={"bio": "piratée"})))
    assert code is None and r["email"] == A
    assert coach(base, A).get("bio") == "piratée" and "bio" not in coach(base, B)
    _r, code = appel(C.update_coach_profile(_Req(entete=B, corps={"bio": "x"})))
    assert code in (401, 403) and "bio" not in coach(base, B)


def test_deduct_credit_ne_touche_que_son_compte(base):
    _r, code = appel(C.deduct_coach_credit(_Req(corps={"email": B})))
    assert code in (401, 403) and coach(base, B)["credits"] == 5
    _r, code = appel(C.deduct_coach_credit(_Req(jeton=jeton(A), corps={"email": B})))
    assert code == 403 and coach(base, B)["credits"] == 5
    r, code = appel(C.deduct_coach_credit(_Req(jeton=jeton(A), corps={"email": A})))
    assert code is None and coach(base, A)["credits"] == 2


def test_stripe_connect_onboard_autre_coach_refuse(base):
    _r, code = appel(C.create_stripe_connect_onboard(_Req(jeton=jeton(A), corps={"email": B})))
    assert code == 403 and "stripe_connect_id" not in coach(base, B)
    _r, code = appel(C.create_stripe_connect_onboard(_Req(corps={"email": B})))
    assert code in (401, 403)


def test_check_credits_et_statut_stripe_exigent_le_jeton(base):
    _r, code = appel(C.api_check_credits(_Req(entete=B)))
    assert code in (401, 403)
    r, code = appel(C.api_check_credits(_Req(jeton=jeton(A))))
    assert code is None and r["credits"] == 3
    _r, code = appel(C.get_stripe_connect_status(_Req(entete=B)))
    assert code in (401, 403)
