# -*- coding: utf-8 -*-
"""V585 — sécurité des Liens intelligents et des envois de fichiers.

VRAIES routes (`generate_shareable_link`, `get_all_chat_links`, `update_chat_link`,
`delete_chat_link`) et VRAIE garde d'envoi (`_v585_identite_upload`), avec de VRAIS jetons
signés HS256 et une base en mémoire. Aucun réseau.

Lancer : python3 -m pytest tests/test_v585_securite_liens_uploads.py -q
"""
import asyncio
import os
import sys

os.environ["JWT_SECRET"] = os.environ.get("JWT_SECRET") or ("v585-secret-de-test-" * 3)
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v585-inexistant:27017")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import jwt as pyjwt
import pytest
from fastapi import HTTPException

import api.server as S

ADMIN = S.SUPER_ADMIN_EMAILS[0]
COACH_A = "coach.a@exemple-test.ch"
COACH_B = "coach.b@exemple-test.ch"


def jeton(email, **extra):
    return pyjwt.encode(dict({"email": email}, **extra), os.environ["JWT_SECRET"], algorithm="HS256")


def _match(d, q):
    for k, v in (q or {}).items():
        if k == "$or":
            if not any(_match(d, x) for x in v):
                return False
            continue
        val = d.get(k)
        if isinstance(v, dict) and any(op.startswith("$") for op in v):
            for op, arg in v.items():
                if op == "$ne" and val == arg:
                    return False
                if op == "$exists" and (k in d) != bool(arg):
                    return False
        elif val != v:
            return False
    return True


class _Cur:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, n=None):
        return [dict(x) for x in self.docs]


class _Coll:
    def __init__(self, docs=()):
        self.docs = [dict(x) for x in docs]

    def find(self, q=None, proj=None):
        return _Cur([x for x in self.docs if _match(x, q)])

    async def find_one(self, q=None, proj=None):
        return next((dict(x) for x in self.docs if _match(x, q)), None)

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, q, maj, upsert=False):
        for x in self.docs:
            if _match(x, q):
                x.update(maj.get("$set", {}))
                return type("R", (), {"matched_count": 1, "modified_count": 1})()
        return type("R", (), {"matched_count": 0, "modified_count": 0})()


class _Base:
    def __init__(self, liens=()):
        self.chat_sessions = _Coll(liens)
        self.coaches = _Coll([{"email": COACH_A}, {"email": COACH_B}])
        self.coach_auth = _Coll()


class _Req:
    def __init__(self, headers=None, corps=None):
        self.headers = dict(headers or {})
        self._corps = corps or {}

    async def json(self):
        return self._corps


def auth(email):
    return {"Authorization": "Bearer " + jeton(email)}


def lien(id_, coach_id, titre):
    return {"id": id_, "link_token": "tok" + id_, "title": titre, "coach_id": coach_id,
            "is_smart_link": True, "mode": "ai", "participant_ids": []}


@pytest.fixture()
def base(monkeypatch):
    b = _Base([lien("a1", COACH_A, "Lien A"), lien("b1", COACH_B, "Lien B"),
               lien("s1", S.DEFAULT_COACH_ID, "Lien Bassi")])
    monkeypatch.setattr(S, "db", b)
    etat = {"strict": False}

    async def drapeaux():
        return {"UPLOADS_IDENTITE_STRICTE": etat["strict"]}
    monkeypatch.setattr(S, "get_feature_flags", drapeaux)
    b.etat = etat
    return b


def run(c):
    return asyncio.run(c)


def code(c):
    with pytest.raises(HTTPException) as e:
        run(c)
    return e.value.status_code


# ═══════════ LIENS INTELLIGENTS ═══════════
def test_liste_sans_jeton_refusee(base):
    assert code(S.get_all_chat_links(_Req())) == 403


def test_liste_entete_falsifie_refuse(base):
    assert code(S.get_all_chat_links(_Req({"X-User-Email": ADMIN}))) == 403


def test_coach_ne_voit_que_ses_liens(base):
    assert [l["title"] for l in run(S.get_all_chat_links(_Req(auth(COACH_A))))] == ["Lien A"]


def test_super_admin_voit_tout(base):
    assert len(run(S.get_all_chat_links(_Req(auth(ADMIN))))) == 3


def test_a_ne_modifie_pas_le_lien_de_b(base):
    assert code(S.update_chat_link("b1", _Req(auth(COACH_A), {"title": "pirate"}))) == 404
    assert next(x for x in base.chat_sessions.docs if x["id"] == "b1")["title"] == "Lien B"


def test_a_ne_supprime_pas_le_lien_de_b(base):
    assert code(S.delete_chat_link("b1", _Req(auth(COACH_A)))) == 404
    assert not next(x for x in base.chat_sessions.docs if x["id"] == "b1").get("is_deleted")


def test_modif_et_suppression_sans_jeton_refusees(base):
    assert code(S.update_chat_link("a1", _Req({}, {"title": "x"}))) == 403
    assert code(S.delete_chat_link("a1", _Req())) == 403


def test_proprietaire_modifie_et_supprime(base):
    run(S.update_chat_link("a1", _Req(auth(COACH_A), {"title": "Nouveau"})))
    assert next(x for x in base.chat_sessions.docs if x["id"] == "a1")["title"] == "Nouveau"
    run(S.delete_chat_link("a1", _Req(auth(COACH_A))))
    assert next(x for x in base.chat_sessions.docs if x["id"] == "a1")["is_deleted"] is True


def test_super_admin_conserve_ses_droits(base):
    run(S.update_chat_link("b1", _Req(auth(ADMIN), {"title": "Revu"})))
    run(S.delete_chat_link("s1", _Req(auth(ADMIN))))
    assert next(x for x in base.chat_sessions.docs if x["id"] == "b1")["title"] == "Revu"


def test_creation_identite_du_jeton_pas_de_l_entete(base):
    r = run(S.generate_shareable_link(_Req(dict(auth(COACH_A), **{"X-User-Email": COACH_B}),
                                           {"title": "T"})))
    cree = next(x for x in base.chat_sessions.docs if x["id"] == r["session_id"])
    assert cree["coach_id"] == COACH_A
    assert code(S.generate_shareable_link(_Req({"X-User-Email": COACH_A}, {"title": "T"}))) == 403


def test_lien_public_par_jeton_inchange(base):
    assert run(S.get_chat_link_by_token("toka1"))["title"] == "Lien A"


# ═══════════ ENVOIS DE FICHIERS ═══════════
def test_upload_coach_jwt(base):
    assert run(S._v585_identite_upload(_Req(auth(COACH_A)), "t")) == COACH_A


def test_upload_abonne_jeton(base):
    t = jeton("amina@exemple-reel.ch", type="subscriber", code="AFR-ABC123")
    assert run(S._v585_identite_upload(_Req({"X-Subscriber-Token": t}), "t")) == "amina@exemple-reel.ch"


def test_upload_entete_falsifie_refuse_en_mode_strict(base):
    base.etat["strict"] = True
    assert code(S._v585_identite_upload(_Req({"X-User-Email": ADMIN}), "t")) == 403
    assert code(S._v585_identite_upload(_Req({"Authorization": "Bearer faux.jeton.x"}), "t")) == 403
    assert run(S._v585_identite_upload(_Req(auth(COACH_A)), "t")) == COACH_A      # légitime : OK


def test_upload_jeton_mal_signe_ne_vaut_pas_identite(base):
    faux = pyjwt.encode({"email": ADMIN}, "autre-secret-" * 4, algorithm="HS256")
    base.etat["strict"] = True
    assert code(S._v585_identite_upload(_Req({"Authorization": "Bearer " + faux}), "t")) == 403


def test_upload_repli_journalise_hors_mode_strict(base):
    assert run(S._v585_identite_upload(_Req({"X-User-Email": "visiteur@ex.ch"}), "t")) == "visiteur@ex.ch"
    assert code(S._v585_identite_upload(_Req(), "t")) == 401               # comportement d'avant
    assert run(S._v585_identite_upload(_Req(), "photo", exiger_entete=False)) == ""


# ═══════════ V586 : /chat/generate-strategy (OpenAI) sous JWT coach/admin ═══════════
class _FauxOpenAI:
    appels = 0

    def __init__(self, api_key=None):
        class _C:
            @staticmethod
            def create(**k):
                _FauxOpenAI.appels += 1
                msg = type("M", (), {"content": '{"welcome_message": "Salut", "custom_prompt": "p", '
                                                '"questions": [{"text": "Q1", "type": "text", "options": []}]}'})()
                return type("R", (), {"choices": [type("Ch", (), {"message": msg})()]})()
        self.chat = type("Chat", (), {"completions": _C})()


@pytest.fixture()
def openai_faux(monkeypatch):
    import types
    _FauxOpenAI.appels = 0
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_FauxOpenAI))
    monkeypatch.setenv("OPENAI_API_KEY", "cle-de-test")
    return _FauxOpenAI


CORPS = {"objective": "recruter des partenaires", "lead_type": "partner"}


def test_strategie_sans_jeton_403(base, openai_faux):
    assert code(S.generate_ai_strategy(_Req({}, CORPS))) == 403
    assert openai_faux.appels == 0


def test_strategie_identite_falsifiee_403(base, openai_faux):
    assert code(S.generate_ai_strategy(_Req({"X-User-Email": ADMIN}, CORPS))) == 403
    faux = pyjwt.encode({"email": ADMIN}, "autre-secret-" * 4, algorithm="HS256")
    assert code(S.generate_ai_strategy(_Req({"Authorization": "Bearer " + faux}, CORPS))) == 403
    abonne = jeton("amina@exemple-reel.ch", type="subscriber", code="AFR-X")
    assert code(S.generate_ai_strategy(_Req({"Authorization": "Bearer " + abonne}, CORPS))) == 403
    assert openai_faux.appels == 0


def test_strategie_coach_et_super_admin_200(base, openai_faux):
    r = run(S.generate_ai_strategy(_Req(auth(COACH_A), CORPS)))
    assert r["questions"][0]["text"] == "Q1"
    r = run(S.generate_ai_strategy(_Req(auth(ADMIN), CORPS)))
    assert r["welcome_message"] == "Salut"
    assert openai_faux.appels == 2


def test_strategie_objectif_vide_reste_400(base, openai_faux):
    assert code(S.generate_ai_strategy(_Req(auth(COACH_A), {"objective": ""}))) == 400
