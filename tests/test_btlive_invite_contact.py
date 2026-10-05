"""V572 — l'invité qui rejoint un Live Afroboost entre dans les Contacts EXISTANTS.

Route serveur-à-serveur `POST /api/boosttribe/live-guest` : jeton HS256 signé par BoostTribe
avec le secret partagé EXISTANT, audience RÉSERVÉE (`afroboost-contacts`), jti à usage unique.
Écriture dans `chat_participants` (aucune nouvelle base), anti-doublon `tenant_contacts`
(e-mail ; numéro sous toutes ses écritures), aucun écrasement, aucun consentement marketing,
aucun débit de crédit, registre des refus (`subscribers`) jamais touché.
"""
import asyncio
import copy
import os
import sys
import time
import uuid

import jwt
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_btlive_proprietaire import S, _Coll, COACH_A  # noqa: E402

SECRET = "secret-partage-de-test-assez-long-pour-hs256"
CODE = "LIVE1-AAAA"


class _CollContacts(_Coll):
    """chat_participants en mémoire : find_one avec $and / $or / $in / $regex (insensible casse)."""

    def _ok(self, d, f):
        import re as _re
        for k, v in f.items():
            if k == "$and":
                if not all(self._ok(d, x) for x in v):
                    return False
            elif k == "$or":
                if not any(self._ok(d, x) for x in v):
                    return False
            elif isinstance(v, dict) and "$in" in v:
                if d.get(k) not in v["$in"]:
                    return False
            elif isinstance(v, dict) and "$exists" in v:
                if (k in d) != v["$exists"]:
                    return False
            elif isinstance(v, dict) and "$regex" in v:
                if not _re.search(v["$regex"], str(d.get(k) or ""), _re.I if "i" in v.get("$options", "") else 0):
                    return False
            elif d.get(k) != v:
                return False
        return True

    async def find_one(self, f, proj=None, sort=None):
        docs = [d for d in self.docs.values() if self._ok(d, f)]
        if sort:
            cle, sens = sort[0]
            docs.sort(key=lambda d: str(d.get(cle) or ""), reverse=sens < 0)
        return copy.deepcopy(docs[0]) if docs else None

    async def update_one(self, f, u, upsert=False):
        for d in self.docs.values():
            if self._ok(d, f):
                self._appliquer(d, u)
                return type("R", (), {"matched_count": 1})()
        if upsert:
            d = {k: v for k, v in f.items() if not k.startswith("$")}
            for k, v in u.get("$setOnInsert", {}).items():
                d[k] = v
            self._appliquer(d, u)
            self.docs[d.get("id") or str(uuid.uuid4())] = d
        return type("R", (), {"matched_count": 0})()

    def find(self, f, proj=None):
        docs = [copy.deepcopy(d) for d in self.docs.values() if self._ok(d, f)]

        class C:
            def __aiter__(self):
                self._i = iter(docs)
                return self

            async def __anext__(self):
                try:
                    return next(self._i)
                except StopIteration:
                    raise StopAsyncIteration
        return C()


@pytest.fixture()
def base(monkeypatch):
    monkeypatch.setenv("AFRO_BT_SHARED_SECRET", SECRET)
    monkeypatch.setattr(S, "is_super_admin", lambda e: e == COACH_A)
    import api.routes.tenant_contacts as TC
    monkeypatch.setattr(TC, "is_super_admin", lambda e: e == COACH_A, raising=False)
    fausse = type("DB", (), {})()
    fausse.boosttribe_live = _Coll()
    fausse.boosttribe_live_journal = _CollContacts()
    fausse.chat_participants = _CollContacts()
    fausse.subscribers = _CollContacts()
    fausse.users = _CollContacts()
    fausse.boosttribe_live.docs["actuel"] = {"_id": "actuel", "session_code": CODE, "host": COACH_A, "ended": False,
                                             "started_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()}
    monkeypatch.setattr(S, "db", fausse)
    S._btlive_invite_jti.clear()
    return fausse


class _Req:
    def __init__(self, corps):
        self.corps = corps
        self.headers = {}

    async def json(self):
        return self.corps


def jeton(aud="afroboost-contacts", iss="boosttribe", secret=SECRET, **k):
    p = {"iss": iss, "aud": aud, "jti": str(uuid.uuid4()), "iat": int(time.time()), "exp": int(time.time()) + 300,
         "session_code": CODE, "nom": "Léa", "email": "lea@exemple.ch", "whatsapp": "079 123 45 67",
         "photo_url": "https://x.supabase.co/storage/v1/object/public/session-media/invites/LIVE1-AAAA/a.jpg"}
    p.update(k)
    return jwt.encode(p, secret, algorithm="HS256")


def appel(tok):
    try:
        return 200, asyncio.new_event_loop().run_until_complete(S.boosttribe_live_guest(_Req({"token": tok})))
    except S.HTTPException as e:
        return e.status_code, e.detail


def fiches(base):
    return list(base.chat_participants.docs.values())


def test_G_contact_cree_dans_les_contacts_existants(base):
    st, r = appel(jeton())
    assert st == 200 and r["cree"] is True
    (f,) = fiches(base)
    assert f["name"] == "Léa" and f["email"] == "lea@exemple.ch" and f["whatsapp"] == "+41791234567"
    assert f["source"] == "live_afroboost" and "live_afroboost" in f["sources"]
    assert f["lives"][0]["session_code"] == CODE and f["created_at"]
    assert f["photo_url"].endswith("/invites/LIVE1-AAAA/a.jpg")
    assert f["marketing_consent"] is False                     # entrer au Live ≠ consentement marketing
    assert f["coach_id"] == S.DEFAULT_COACH_ID                 # live du super-admin → espace plateforme


def test_H_meme_email_pas_de_doublon(base):
    appel(jeton())
    st, r = appel(jeton(email="LEA@exemple.ch", whatsapp=""))
    assert st == 200 and r["cree"] is False and len(fiches(base)) == 1


@pytest.mark.parametrize("ecriture", ["0791234567", "+41 79 123 45 67", "0041 79 123 45 67"])
def test_I_meme_numero_autre_ecriture_pas_de_doublon(base, ecriture):
    appel(jeton(email=""))
    st, r = appel(jeton(email="", whatsapp=ecriture))
    assert st == 200 and r["cree"] is False and len(fiches(base)) == 1


def test_J_contact_existant_aucune_donnee_detruite(base):
    base.chat_participants.docs["x"] = {"id": "x", "coach_id": S.DEFAULT_COACH_ID, "name": "Léa Martin",
                                        "email": "lea@exemple.ch", "whatsapp": "+41 79 000 00 00", "source": "manuel",
                                        "marketing_consent": True, "photo_url": "https://ancienne/photo.jpg", "tags": ["vip"]}
    st, r = appel(jeton(nom="pseudo", whatsapp="078 999 88 77"))
    assert st == 200 and r["cree"] is False
    f = base.chat_participants.docs["x"]
    assert f["name"] == "Léa Martin" and f["whatsapp"] == "+41 79 000 00 00" and f["tags"] == ["vip"]
    assert f["photo_url"] == "https://ancienne/photo.jpg" and f["marketing_consent"] is True
    assert f["source"] == "manuel" and set(f["sources"]) == {"manuel", "live_afroboost"}
    assert f["lives"][-1]["session_code"] == CODE


def test_refus_whatsapp_jamais_touche(base):
    base.subscribers.docs["s"] = {"id": "s", "whatsapp": "+41791234567", "status": "opted_out"}
    appel(jeton())
    assert base.subscribers.docs["s"]["status"] == "opted_out" and len(base.subscribers.docs) == 1


@pytest.mark.parametrize("mauvais", [
    jeton(aud="boosttribe"),                       # jeton d'accès BoostTribe : autre usage
    jeton(iss="afroboost"),
    jeton(secret="un-autre-secret-de-test-assez-long-xx"),
    "pas-un-jeton",
])
def test_jeton_invalide_ou_d_un_autre_usage_401(base, mauvais):
    assert appel(mauvais)[0] == 401 and fiches(base) == []


def test_rejeu_refuse(base):
    t = jeton()
    assert appel(t)[0] == 200
    assert appel(t)[0] == 409


def test_session_qui_n_est_pas_un_live_afroboost_404(base):
    assert appel(jeton(session_code="AUTRE-ZZZZ"))[0] == 404 and fiches(base) == []


def test_sans_email_ni_numero_valide_400(base):
    assert appel(jeton(email="", whatsapp="12"))[0] == 400


def test_secret_absent_503(base, monkeypatch):
    monkeypatch.delenv("AFRO_BT_SHARED_SECRET")
    assert appel(jeton())[0] == 503


# ═══ Revue de sécurité du 05/10 : l'origine HTTP n'est pas une authentification ═══
def test_securite_live_ancien_refuse(base):
    """Un code de session d'un live terminé depuis longtemps ne sert plus à injecter des contacts."""
    from datetime import datetime, timedelta, timezone
    base.boosttribe_live.docs["actuel"]["started_at"] = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    assert appel(jeton())[0] == 404 and fiches(base) == []


def test_securite_live_recent_par_le_journal(base):
    from datetime import datetime, timedelta, timezone
    base.boosttribe_live.docs["actuel"] = {"_id": "actuel", "session_code": "AUTRE-ZZZZ", "host": COACH_A,
                                           "started_at": datetime.now(timezone.utc).isoformat()}
    base.boosttribe_live_journal.docs["j"] = {"event": "started", "session_code": CODE, "by": COACH_A,
                                              "at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()}
    assert appel(jeton())[0] == 200
