# -*- coding: utf-8 -*-
"""
V553 — OBSERVABILITÉ DES FINS DE LIVE (instrumentation seule).

Incident du 28/09 12:06 : un `ended` est arrivé sans que l'iframe ait émis
`bt:session-ended`, et les battements ont continué (puis 409). On ne pouvait pas
dire QUI avait terminé le live. Ce banc tient la trace, sans toucher la décision :
  * chaque fin écrit ended_reason / ended_by / ended_source / ended_request_id /
    ended_user_agent / ended_prev, et UNE ligne dans `boosttribe_live_journal` ;
  * une expiration calculée (grâce 90 s / 3 h) est journalisée UNE seule fois,
    sans écrire `ended` ;
  * aucun battement réussi ne journalise ; un battement refusé, au plus 1×/min ;
  * aucun jeton, aucun en-tête Authorization, aucun corps complet dans les traces.
Base simulée en mémoire, aucune sortie réseau.
"""
import asyncio
import logging
import os
import socket
import sys
from datetime import datetime, timedelta, timezone

import pytest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

_GETADDR = socket.getaddrinfo


def _dns(hote, port, *a, **k):
    if str(hote) in ("localhost", "127.0.0.1", "::1", None):
        return _GETADDR(hote, port, *a, **k)
    raise RuntimeError("sortie reseau interdite : %s" % hote)


socket.getaddrinfo = _dns
os.environ.setdefault("JWT_SECRET", "secret-de-test-btlive-sans-rapport-avec-la-production")
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-btlive-inexistant:27017")

import api.server as S      # noqa: E402

COACH_A, COACH_B = "coach-a@exemple.invalid", "coach-b@exemple.invalid"
JETON = "eyJhbGciOiJIUzI1NiJ9.JETON-SECRET-A-NE-JAMAIS-JOURNALISER.sig"


class _Res:
    def __init__(self, n):
        self.matched_count = n


class _Coll:
    """Collection en mémoire : égalité stricte ; `None` dans un filtre = champ absent ou nul (comme Mongo)."""

    def __init__(self):
        self.docs = {}
        self.lignes = []

    @staticmethod
    def _ok(d, f):
        return all(d.get(k) == v for k, v in f.items())

    async def find_one(self, f, proj=None):
        for d in self.docs.values():
            if self._ok(d, f):
                return dict(d)
        return None

    async def update_one(self, f, u, upsert=False):
        for d in self.docs.values():
            if self._ok(d, f):
                d.update(u.get("$set", {}))
                for k in u.get("$unset", {}):
                    d.pop(k, None)
                return _Res(1)
        if upsert:
            d = {k: v for k, v in f.items()}
            d.update(u.get("$set", {}))
            self.docs[d["_id"]] = d
        return _Res(0)

    async def insert_one(self, d):
        self.lignes.append(dict(d))


class _Req:
    def __init__(self, email, corps, headers=None):
        self.email, self.corps = email, corps
        self.headers = headers if headers is not None else {}

    async def json(self):
        return self.corps


class _Resp:
    def __init__(self):
        self.headers = {}


def _auth(req):
    if not req.email:
        raise S.HTTPException(status_code=401, detail="Authentification requise")
    return req.email


@pytest.fixture(autouse=True)
def base(monkeypatch):
    monkeypatch.setattr(S, "require_auth", _auth)
    monkeypatch.setattr(S, "is_super_admin", lambda e: e in (COACH_A, COACH_B))
    fausse = type("DB", (), {})()
    fausse.boosttribe_live = _Coll()
    fausse.boosttribe_live_journal = _Coll()
    monkeypatch.setattr(S, "db", fausse)
    S._btlive_refus_vus.clear()
    return fausse


def appel(email, event, code, extra=None, headers=None, resp=None):
    corps = {"event": event, "session_code": code}
    corps.update(extra or {})
    h = {"user-agent": "Mozilla/5.0 (banc V553) " + "x" * 400,
         "authorization": "Bearer " + JETON}
    h.update(headers or {})
    try:
        r = asyncio.new_event_loop().run_until_complete(
            S.boosttribe_live_status_set(_Req(email, corps, h), resp))
        return 200, r
    except S.HTTPException as e:
        return e.status_code, e.detail


def doc(base):
    return base.boosttribe_live.docs.get("actuel") or {}


def journal(base, **filtre):
    return [l for l in base.boosttribe_live_journal.lignes
            if all(l.get(k) == v for k, v in filtre.items())]


# ─── les motifs ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("motif", ["host_terminate", "host_leave", "overlay_close",
                                   "page_unmount", "consume_refused", "iframe_ended_sans_motif"])
def test_fin_trace_le_motif(base, motif):
    assert appel(COACH_A, "started", "SESS-AAAA", {"source": "iframe:barre_app:ab12"})[0] == 200
    resp = _Resp()
    st, _ = appel(COACH_A, "ended", "SESS-AAAA", {"reason": motif, "source": "overlay:barre_app:ab12"},
                  headers={"x-request-id": "rid-123"}, resp=resp)
    d = doc(base)
    assert st == 200 and d["ended"] is True
    assert d["ended_reason"] == motif
    assert d["ended_by"] == COACH_A
    assert d["ended_source"] == "overlay:barre_app:ab12"
    assert d["ended_request_id"] == "rid-123"
    assert resp.headers["X-Request-ID"] == "rid-123"
    assert len(d["ended_user_agent"]) == 200
    assert d["ended_prev"]["session_code"] == "SESS-AAAA" and d["ended_prev"]["ended"] is False
    lignes = journal(base, event="ended")
    assert len(lignes) == 1 and lignes[0]["reason"] == motif and lignes[0]["transition"] is True


def test_motif_inconnu_ou_absent_devient_unknown(base):
    appel(COACH_A, "started", "SESS-AAAA")
    appel(COACH_A, "ended", "SESS-AAAA", {"reason": "<script>alert(1)</script>"})
    assert doc(base)["ended_reason"] == "unknown"
    appel(COACH_A, "started", "SESS-BBBB")
    appel(COACH_A, "ended", "SESS-BBBB")          # ancien client : aucun motif
    assert doc(base)["ended_reason"] == "unknown"


def test_request_id_genere_si_absent(base):
    appel(COACH_A, "started", "SESS-AAAA")
    resp = _Resp()
    appel(COACH_A, "ended", "SESS-AAAA", {"reason": "host_leave"}, resp=resp)
    rid = doc(base)["ended_request_id"]
    assert rid and len(rid) <= 64 and resp.headers["X-Request-ID"] == rid


def test_ended_repete_n_ecrase_pas_la_premiere_trace(base):
    appel(COACH_A, "started", "SESS-AAAA")
    appel(COACH_A, "ended", "SESS-AAAA", {"reason": "overlay_close"})
    appel(COACH_A, "ended", "SESS-AAAA", {"reason": "host_terminate"})
    assert doc(base)["ended_reason"] == "overlay_close"
    lignes = journal(base, event="ended")
    assert [l["transition"] for l in lignes] == [True, False]


# ─── les refus : aucune fin, mais une trace ─────────────────────────────────────
def test_sans_auth_401_et_aucune_fin(base):
    appel(COACH_A, "started", "SESS-AAAA")
    st, _ = appel("", "ended", "SESS-AAAA", {"reason": "host_terminate"})
    assert st == 401
    assert doc(base)["ended"] is False
    assert doc(base).get("ended_reason") is None
    assert journal(base, event="ended") == []


def test_non_super_admin_403_et_aucune_fin(base):
    appel(COACH_A, "started", "SESS-AAAA")
    st, _ = appel("intrus@exemple.invalid", "ended", "SESS-AAAA", {"reason": "host_terminate"})
    assert st == 403 and doc(base)["ended"] is False


def test_autre_super_admin_non_hote_403_aucune_fin_mais_refus_journalise(base):
    appel(COACH_A, "started", "SESS-AAAA")
    st, _ = appel(COACH_B, "ended", "SESS-AAAA", {"reason": "overlay_close"})
    assert st == 403
    assert doc(base)["ended"] is False and doc(base).get("ended_reason") is None
    refus = journal(base, event="ended", outcome="refus")
    assert len(refus) == 1 and refus[0]["status"] == 403 and refus[0]["by"] == COACH_B


# ─── battements ──────────────────────────────────────────────────────────────
def test_battement_reussi_ne_journalise_rien(base):
    appel(COACH_A, "started", "SESS-AAAA")
    avant = len(base.boosttribe_live_journal.lignes)
    for _ in range(5):
        assert appel(COACH_A, "heartbeat", "SESS-AAAA")[0] == 200
    assert len(base.boosttribe_live_journal.lignes) == avant


def test_battement_refuse_journalise_dedup_une_fois_par_minute(base):
    appel(COACH_A, "started", "SESS-AAAA")
    appel(COACH_A, "ended", "SESS-AAAA", {"reason": "overlay_close"})
    for _ in range(4):
        assert appel(COACH_A, "heartbeat", "SESS-AAAA")[0] == 409
    refus = journal(base, event="heartbeat", outcome="refus")
    assert len(refus) == 1 and refus[0]["status"] == 409
    # 404 et 403 sont des refus distincts, eux aussi dédupliqués.
    for _ in range(3):
        assert appel(COACH_A, "heartbeat", "SESS-ZZZZ")[0] == 404
    appel(COACH_A, "started", "SESS-CCCC")
    for _ in range(3):
        assert appel(COACH_B, "heartbeat", "SESS-CCCC")[0] == 403
    statuts = sorted(l["status"] for l in journal(base, event="heartbeat", outcome="refus"))
    assert statuts == [403, 404, 409]


# ─── expiration calculée ─────────────────────────────────────────────────────
def test_expiration_journalisee_une_seule_fois_sans_ecrire_ended(base):
    appel(COACH_A, "started", "SESS-AAAA")
    appel(COACH_A, "heartbeat", "SESS-AAAA")
    maintenant = datetime.now(timezone.utc)
    doc(base)["last_seen"] = (maintenant - timedelta(seconds=300)).isoformat()   # 5 min de silence
    lire = lambda: asyncio.new_event_loop().run_until_complete(S.boosttribe_live_status())  # noqa: E731
    assert lire()["active"] is False
    assert lire()["active"] is False
    appel(COACH_A, "heartbeat", "SESS-AAAA")          # un battement tardif arrive aussi
    lignes = journal(base, event="expiration")
    assert len(lignes) == 1
    assert lignes[0]["reason"] == "server_expiration" and lignes[0]["cause"] == "grace_90s"
    assert lignes[0]["silence_s"] >= 299
    assert doc(base)["ended"] is False              # l'expiration n'ÉCRIT PAS `ended`


def test_expiration_3h_sans_battement(base):
    appel(COACH_A, "started", "SESS-AAAA")
    doc(base)["started_at"] = (datetime.now(timezone.utc) - timedelta(hours=3, minutes=5)).isoformat()
    asyncio.new_event_loop().run_until_complete(S.boosttribe_live_status())
    lignes = journal(base, event="expiration")
    assert len(lignes) == 1 and lignes[0]["cause"] == "max_3h"


def test_nouveau_live_rearme_la_journalisation_d_expiration(base):
    appel(COACH_A, "started", "SESS-AAAA")
    appel(COACH_A, "heartbeat", "SESS-AAAA")
    doc(base)["last_seen"] = (datetime.now(timezone.utc) - timedelta(seconds=300)).isoformat()
    asyncio.new_event_loop().run_until_complete(S.boosttribe_live_status())
    appel(COACH_A, "started", "SESS-BBBB")
    appel(COACH_A, "heartbeat", "SESS-BBBB")
    doc(base)["last_seen"] = (datetime.now(timezone.utc) - timedelta(seconds=300)).isoformat()
    asyncio.new_event_loop().run_until_complete(S.boosttribe_live_status())
    assert [l["session_code"] for l in journal(base, event="expiration")] == ["SESS-AAAA", "SESS-BBBB"]


# ─── aucun secret ne fuit ────────────────────────────────────────────────────
def test_aucun_jeton_dans_les_journaux(base, caplog):
    caplog.set_level(logging.DEBUG)
    appel(COACH_A, "started", "SESS-AAAA", {"token": JETON})
    appel(COACH_B, "ended", "SESS-AAAA", {"reason": "host_terminate", "token": JETON})
    appel(COACH_A, "ended", "SESS-AAAA", {"reason": "host_terminate", "token": JETON,
                                          "source": "Bearer " + JETON})
    assert "[BT-LIVE-FIN]" in caplog.text
    tout = caplog.text + repr(base.boosttribe_live_journal.lignes) + repr(doc(base))
    assert JETON not in tout
    assert "JETON-SECRET" not in tout
    assert "Bearer" not in tout
    assert "authorization" not in tout.lower()
    assert doc(base)["ended_source"] == "non_conforme"   # un libellé libre n'est jamais recopié


def test_journal_indisponible_ne_casse_pas_le_live(base):
    class _Casse:
        async def insert_one(self, d):
            raise RuntimeError("atlas indisponible")
    base.boosttribe_live_journal = _Casse()
    assert appel(COACH_A, "started", "SESS-AAAA")[0] == 200
    assert appel(COACH_A, "ended", "SESS-AAAA", {"reason": "host_leave"})[0] == 200
    assert doc(base)["ended"] is True
