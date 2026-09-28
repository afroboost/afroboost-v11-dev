# -*- coding: utf-8 -*-
"""
V555 — PROPRIÉTAIRE DU LIVE (onglet qui l'a démarré).

Incident : un AUTRE onglet du même coach (même e-mail hôte) fermait le live
en cours par une fin AUTOMATIQUE (croix de l'overlay, démontage de page…).
Règle spécifiée ici (serveur, `POST /boosttribe/live-status`) :
  * le corps peut porter `owner` (`[A-Za-z0-9]{6,32}`, sinon ignoré = absent) ;
  * `started` (nouveau live ET reconnexion V550) enregistre `owner` ; le dernier
    `started` gagne (c'est la reconnexion après rechargement) ;
  * `ended` AUTOMATIQUE (overlay_close, page_unmount, consume_refused, unknown,
    iframe_ended_sans_motif, motif hors liste -> unknown) sur le live courant
    non terminé, document avec owner ET corps avec owner DIFFÉRENT -> 409,
    document inchangé, une ligne `refus` 409 au journal ;
  * `ended` EXPLICITE (host_terminate, host_leave) -> accepté quel que soit l'owner ;
  * owner absent du document OU du corps -> comportement actuel ;
  * `heartbeat` : owner ignoré ; expiration 90 s inchangée.
Base simulée en mémoire, aucune sortie réseau. Même socle que
test_btlive_fin_observabilite.py.
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



OWNER_X, OWNER_Y, OWNER_Z = "ongletX1a2b3", "ongletY4c5d6", "ongletZ7e8f9"
MOTIFS_AUTO = ["overlay_close", "page_unmount", "consume_refused", "unknown",
               "iframe_ended_sans_motif", "motif_hors_liste_xyz"]
MOTIFS_EXPLICITES = ["host_terminate", "host_leave"]


def _o(owner, **extra):
    d = {"owner": owner} if owner is not None else {}
    d.update(extra)
    return d


def actif_public():
    return asyncio.new_event_loop().run_until_complete(S.boosttribe_live_status())["active"]


# ─── enregistrement de l'owner ───────────────────────────────────────────────
def test_started_enregistre_owner(base):
    assert appel(COACH_A, "started", "SESS-AAAA", _o(OWNER_X))[0] == 200
    assert doc(base).get("owner") == OWNER_X


@pytest.mark.parametrize("invalide", ["abc", "x" * 33, "onglet-x1!", "", 123456789, None])
def test_owner_invalide_ignore_comme_absent(base, invalide):
    appel(COACH_A, "started", "SESS-AAAA", {"owner": invalide})
    assert doc(base).get("owner") is None
    # document sans owner -> comportement actuel : une fin automatique passe.
    st, _ = appel(COACH_A, "ended", "SESS-AAAA", _o(OWNER_Y, reason="overlay_close"))
    assert st == 200 and doc(base)["ended"] is True


def test_nouveau_live_sans_owner_n_herite_pas_de_l_owner_precedent(base):
    appel(COACH_A, "started", "SESS-AAAA", _o(OWNER_X))
    appel(COACH_A, "ended", "SESS-AAAA", _o(OWNER_X, reason="host_terminate"))
    appel(COACH_A, "started", "SESS-BBBB")                 # ancien bundle : pas d'owner
    assert doc(base).get("owner") is None
    st, _ = appel(COACH_A, "ended", "SESS-BBBB", _o(OWNER_Z, reason="overlay_close"))
    assert st == 200 and doc(base)["ended"] is True


def test_nouveau_live_remplace_l_owner(base):
    appel(COACH_A, "started", "SESS-AAAA", _o(OWNER_X))
    appel(COACH_A, "ended", "SESS-AAAA", _o(OWNER_X, reason="host_terminate"))
    appel(COACH_A, "started", "SESS-BBBB", _o(OWNER_Y))
    assert doc(base).get("owner") == OWNER_Y


# ─── H : autre onglet, même e-mail hôte, fin automatique -> 409 ────────────────
@pytest.mark.parametrize("motif", MOTIFS_AUTO)
def test_H_autre_onglet_fin_automatique_refusee_409(base, motif):
    appel(COACH_A, "started", "SESS-AAAA", _o(OWNER_X))
    appel(COACH_A, "heartbeat", "SESS-AAAA", _o(OWNER_X))
    avant = dict(doc(base))
    st, _ = appel(COACH_A, "ended", "SESS-AAAA", _o(OWNER_Y, reason=motif))
    assert st == 409
    d = doc(base)
    assert d["ended"] is False
    assert d.get("ended_reason") is None and d.get("ended_by") is None
    assert d.get("ended_at") is None
    assert d.get("owner") == OWNER_X
    assert d == avant                                      # document INCHANGÉ
    assert actif_public() is True                          # le live reste actif
    refus = journal(base, event="ended", outcome="refus")
    assert len(refus) == 1 and refus[0]["status"] == 409 and refus[0]["by"] == COACH_A
    assert journal(base, event="ended", outcome="ok") == []


def test_H_ended_sans_motif_d_un_autre_onglet_refuse(base):
    appel(COACH_A, "started", "SESS-AAAA", _o(OWNER_X))
    st, _ = appel(COACH_A, "ended", "SESS-AAAA", _o(OWNER_Y))     # aucun motif = unknown
    assert st == 409 and doc(base)["ended"] is False


def test_H_le_live_refuse_continue_de_battre(base):
    appel(COACH_A, "started", "SESS-AAAA", _o(OWNER_X))
    appel(COACH_A, "ended", "SESS-AAAA", _o(OWNER_Y, reason="overlay_close"))
    assert appel(COACH_A, "heartbeat", "SESS-AAAA", _o(OWNER_X))[0] == 200
    assert actif_public() is True


def test_H_puis_le_proprietaire_termine_200(base):
    appel(COACH_A, "started", "SESS-AAAA", _o(OWNER_X))
    assert appel(COACH_A, "ended", "SESS-AAAA", _o(OWNER_Y, reason="page_unmount"))[0] == 409
    st, _ = appel(COACH_A, "ended", "SESS-AAAA", _o(OWNER_X, reason="overlay_close"))
    assert st == 200
    d = doc(base)
    assert d["ended"] is True and d["ended_reason"] == "overlay_close"
    assert actif_public() is False
    # ended répété du propriétaire : idempotent, la première trace reste.
    assert appel(COACH_A, "ended", "SESS-AAAA", _o(OWNER_X, reason="host_terminate"))[0] == 200
    assert doc(base)["ended_reason"] == "overlay_close"
    assert [l["transition"] for l in journal(base, event="ended", outcome="ok")] == [True, False]


def test_H_live_deja_termine_fin_automatique_autre_onglet_reste_idempotente(base):
    appel(COACH_A, "started", "SESS-AAAA", _o(OWNER_X))
    appel(COACH_A, "ended", "SESS-AAAA", _o(OWNER_X, reason="host_terminate"))
    st, _ = appel(COACH_A, "ended", "SESS-AAAA", _o(OWNER_Y, reason="overlay_close"))
    assert st == 200                                       # live non courant-ouvert : pas de 409
    assert doc(base)["ended"] is True and doc(base)["ended_reason"] == "host_terminate"


def test_H_ended_tardif_d_une_ancienne_session_inchange(base):
    appel(COACH_A, "started", "SESS-AAAA", _o(OWNER_X))
    st, _ = appel(COACH_A, "ended", "SESS-VIEUX", _o(OWNER_Y, reason="overlay_close"))
    assert st == 200 and doc(base)["ended"] is False       # ne touche pas le live courant


def test_H_autre_super_admin_reste_403_avant_409(base):
    appel(COACH_A, "started", "SESS-AAAA", _o(OWNER_X))
    st, _ = appel(COACH_B, "ended", "SESS-AAAA", _o(OWNER_Y, reason="overlay_close"))
    assert st == 403 and doc(base)["ended"] is False


# ─── I : reconnexion -> le dernier started gagne ─────────────────────────────
def test_I_reconnexion_le_dernier_started_gagne(base):
    appel(COACH_A, "started", "SESS-AAAA", _o(OWNER_X))
    debut = doc(base)["started_at"]
    appel(COACH_A, "started", "SESS-AAAA", _o(OWNER_Y))   # rechargement de la page
    d = doc(base)
    assert d["owner"] == OWNER_Y
    assert d["started_at"] == debut                        # V550 : toujours une reconnexion
    st, _ = appel(COACH_A, "ended", "SESS-AAAA", _o(OWNER_X, reason="overlay_close"))
    assert st == 409 and doc(base)["ended"] is False       # l'ancien onglet ne coupe plus
    st, _ = appel(COACH_A, "ended", "SESS-AAAA", _o(OWNER_Y, reason="overlay_close"))
    assert st == 200 and doc(base)["ended"] is True


# ─── J : grâce 90 s inchangée ────────────────────────────────────────────────
def test_J_grace_90s_inchangee(base):
    appel(COACH_A, "started", "SESS-AAAA", _o(OWNER_X))
    appel(COACH_A, "heartbeat", "SESS-AAAA", _o(OWNER_X))
    maintenant = datetime.now(timezone.utc)
    doc(base)["last_seen"] = (maintenant - timedelta(seconds=60)).isoformat()
    assert actif_public() is True
    doc(base)["last_seen"] = (maintenant - timedelta(seconds=100)).isoformat()
    assert actif_public() is False
    assert doc(base)["ended"] is False
    assert len(journal(base, event="expiration")) == 1


def test_J_btlive_actif_ignore_owner(base):
    m = datetime.now(timezone.utc)
    d = {"session_code": "SESS-AAAA", "ended": False, "started_at": m.isoformat(),
         "owner": OWNER_X}
    assert S.btlive_actif(d, m) is True
    d["last_seen"] = (m - timedelta(seconds=91)).isoformat()
    assert S.btlive_actif(d, m) is False


def test_J_refus_409_ne_rearme_pas_la_grace(base):
    appel(COACH_A, "started", "SESS-AAAA", _o(OWNER_X))
    appel(COACH_A, "heartbeat", "SESS-AAAA", _o(OWNER_X))
    vieux = (datetime.now(timezone.utc) - timedelta(seconds=100)).isoformat()
    doc(base)["last_seen"] = vieux
    appel(COACH_A, "ended", "SESS-AAAA", _o(OWNER_Y, reason="overlay_close"))
    assert doc(base)["last_seen"] == vieux and actif_public() is False


# ─── explicites : acceptés quel que soit l'owner ─────────────────────────────
@pytest.mark.parametrize("motif", MOTIFS_EXPLICITES)
def test_explicite_accepte_meme_autre_owner(base, motif):
    appel(COACH_A, "started", "SESS-AAAA", _o(OWNER_X))
    st, _ = appel(COACH_A, "ended", "SESS-AAAA", _o(OWNER_Y, reason=motif))
    assert st == 200
    d = doc(base)
    assert d["ended"] is True and d["ended_reason"] == motif and d["ended_by"] == COACH_A


# ─── compatibilité ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("motif", MOTIFS_AUTO)
def test_compat_corps_sans_owner_accepte(base, motif):
    appel(COACH_A, "started", "SESS-AAAA", _o(OWNER_X))
    st, _ = appel(COACH_A, "ended", "SESS-AAAA", {"reason": motif})
    assert st == 200 and doc(base)["ended"] is True


@pytest.mark.parametrize("motif", MOTIFS_AUTO)
def test_compat_document_sans_owner_accepte(base, motif):
    appel(COACH_A, "started", "SESS-AAAA")
    st, _ = appel(COACH_A, "ended", "SESS-AAAA", _o(OWNER_Y, reason=motif))
    assert st == 200 and doc(base)["ended"] is True


def test_compat_owner_invalide_dans_le_corps_equivaut_a_absent(base):
    appel(COACH_A, "started", "SESS-AAAA", _o(OWNER_X))
    st, _ = appel(COACH_A, "ended", "SESS-AAAA", {"owner": "x!", "reason": "overlay_close"})
    assert st == 200 and doc(base)["ended"] is True


# ─── même owner : trace V553 complète ────────────────────────────────────────
@pytest.mark.parametrize("motif", MOTIFS_AUTO + MOTIFS_EXPLICITES)
def test_meme_owner_accepte_trace_v553_complete(base, motif):
    appel(COACH_A, "started", "SESS-AAAA", _o(OWNER_X, source="iframe:barre_app:ab12"))
    resp = _Resp()
    st, _ = appel(COACH_A, "ended", "SESS-AAAA",
                  _o(OWNER_X, reason=motif, source="overlay:barre_app:ab12"),
                  headers={"x-request-id": "rid-555"}, resp=resp)
    assert st == 200
    d = doc(base)
    attendu = motif if motif != "motif_hors_liste_xyz" else "unknown"
    assert d["ended"] is True and d["ended_reason"] == attendu
    assert d["ended_by"] == COACH_A
    assert d["ended_source"] == "overlay:barre_app:ab12"
    assert d["ended_request_id"] == "rid-555" and resp.headers["X-Request-ID"] == "rid-555"
    assert len(d["ended_user_agent"]) == 200
    assert d["ended_prev"]["session_code"] == "SESS-AAAA" and d["ended_prev"]["ended"] is False
    lignes = journal(base, event="ended", outcome="ok")
    assert len(lignes) == 1 and lignes[0]["transition"] is True and lignes[0]["reason"] == attendu


# ─── heartbeat : owner ignoré ────────────────────────────────────────────────
def test_heartbeat_autre_owner_meme_hote_accepte(base):
    appel(COACH_A, "started", "SESS-AAAA", _o(OWNER_X))
    avant = len(base.boosttribe_live_journal.lignes)
    st, r = appel(COACH_A, "heartbeat", "SESS-AAAA", _o(OWNER_Y))
    assert st == 200 and r["ok"] is True
    assert doc(base).get("last_seen")
    assert doc(base)["owner"] == OWNER_X                    # un battement ne change pas l'owner
    assert len(base.boosttribe_live_journal.lignes) == avant


def test_heartbeat_autre_super_admin_toujours_403(base):
    appel(COACH_A, "started", "SESS-AAAA", _o(OWNER_X))
    assert appel(COACH_B, "heartbeat", "SESS-AAAA", _o(OWNER_X))[0] == 403
