# -*- coding: utf-8 -*-
"""
V555 — SURFACES D'UN LIVE (plusieurs onglets hôtes du même coach).

Mesuré en prod le 28/09 : un 2e onglet du même coach qui ouvre le Live REJOINT la
session en hôte et émet `started`. Avec « le dernier started possède », sa croix
éteignait le live de l'onglet qui diffusait. Règle spécifiée ici
(`POST /boosttribe/live-status`) :
  * `owner` (chaîne `[A-Za-z0-9]{6,32}`, sinon ignoré = absent) identifie une surface ;
  * le document porte `surfaces: {owner: dernier signe de vie}` : un nouveau live
    repart de `{owner: now}` (ou `{}`), une reconnexion et chaque battement avec
    owner posent `surfaces.<owner> = now` ;
  * une fin AUTOMATIQUE avec owner X est refusée (409, journalisée
    `autre_surface_vivante`, `surfaces.X` retiré, live intact) s'il existe une
    AUTRE surface vue il y a <= BTLIVE_SURFACE_S (35 s) ; sinon acceptée ;
  * `host_terminate` / `host_leave` : toujours acceptés ;
  * sans owner dans le corps : règle d'avant ; battement accepté quel que soit
    l'owner ; grâce 90 s inchangée.
Base simulée en mémoire, aucune sortie réseau.
"""
import asyncio
import copy
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
    """Collection en mémoire : égalité stricte ; `None` dans un filtre = champ absent ou nul
    (comme Mongo) ; `$set` / `$unset` comprennent les chemins pointés (`surfaces.<owner>`)."""

    def __init__(self):
        self.docs = {}
        self.lignes = []

    @staticmethod
    def _ok(d, f):
        return all(d.get(k) == v for k, v in f.items())

    @staticmethod
    def _poser(d, cle, v):
        *chemin, fin = cle.split(".")
        for c in chemin:
            if not isinstance(d.get(c), dict):
                d[c] = {}
            d = d[c]
        d[fin] = v

    @staticmethod
    def _retirer(d, cle):
        *chemin, fin = cle.split(".")
        for c in chemin:
            d = d.get(c)
            if not isinstance(d, dict):
                return
        d.pop(fin, None)

    def _appliquer(self, d, u):
        for k, v in u.get("$set", {}).items():
            self._poser(d, k, v)
        for k in u.get("$unset", {}):
            self._retirer(d, k)

    async def find_one(self, f, proj=None):
        for d in self.docs.values():
            if self._ok(d, f):
                return copy.deepcopy(d)
        return None

    async def update_one(self, f, u, upsert=False):
        for d in self.docs.values():
            if self._ok(d, f):
                self._appliquer(d, u)
                return _Res(1)
        if upsert:
            d = {k: v for k, v in f.items()}
            self._appliquer(d, u)
            self.docs[d["_id"]] = d
        return _Res(0)

    async def insert_one(self, d):
        self.lignes.append(copy.deepcopy(d))


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



A, B, Z = "ongletAaaaa1", "ongletBbbbb2", "ongletZzzzz3"
MOTIFS_AUTO = ["overlay_close", "page_unmount", "consume_refused", "unknown",
               "iframe_ended_sans_motif", "motif_hors_liste_xyz"]
MOTIFS_EXPLICITES = ["host_terminate", "host_leave"]
CODE = "SESS-AAAA"


def _o(owner, **extra):
    d = {"owner": owner} if owner is not None else {}
    d.update(extra)
    return d


def il_y_a(secondes):
    return (datetime.now(timezone.utc) - timedelta(seconds=secondes)).isoformat()


def actif_public():
    return asyncio.new_event_loop().run_until_complete(S.boosttribe_live_status())["active"]


def surfaces(base):
    return doc(base).get("surfaces") or {}


def deux_surfaces(base):
    """A démarre et bat ; B (2e onglet) rejoint (reconnexion V550) et bat."""
    assert appel(COACH_A, "started", CODE, _o(A))[0] == 200
    assert appel(COACH_A, "heartbeat", CODE, _o(A))[0] == 200
    assert appel(COACH_A, "started", CODE, _o(B))[0] == 200
    assert appel(COACH_A, "heartbeat", CODE, _o(B))[0] == 200
    assert set(surfaces(base)) == {A, B}


# ─── surfaces : enregistrement ───────────────────────────────────────────────
def test_started_nouveau_live_pose_une_surface(base):
    appel(COACH_A, "started", CODE, _o(A))
    assert set(surfaces(base)) == {A}
    assert "owner" not in doc(base)


def test_started_sans_owner_surfaces_vides(base):
    appel(COACH_A, "started", CODE)
    assert doc(base).get("surfaces") == {}


def test_reconnexion_ajoute_une_surface_sans_retirer_la_premiere(base):
    appel(COACH_A, "started", CODE, _o(A))
    debut = doc(base)["started_at"]
    appel(COACH_A, "started", CODE, _o(B))
    assert set(surfaces(base)) == {A, B}
    assert doc(base)["started_at"] == debut                 # V550 : reconnexion, pas un nouveau live


def test_nouveau_live_repart_de_zero(base):
    deux_surfaces(base)
    appel(COACH_A, "ended", CODE, _o(A, reason="host_terminate"))
    appel(COACH_A, "started", "SESS-BBBB")
    assert doc(base).get("surfaces") == {}
    appel(COACH_A, "started", "SESS-CCCC", _o(Z))
    assert set(surfaces(base)) == {Z}


@pytest.mark.parametrize("invalide", ["abc", "x" * 33, "onglet-x1!", "", 123456789, ["ongletAaaaa1"],
                                      {"a": 1}, None])
def test_owner_non_conforme_ou_non_chaine_ignore(base, invalide):
    appel(COACH_A, "started", CODE, {"owner": invalide})
    assert doc(base).get("surfaces") == {}
    appel(COACH_A, "heartbeat", CODE, _o(A))               # une vraie surface vivante
    # owner ignoré = absent : règle d'avant, la fin passe malgré la surface A vivante.
    st, _ = appel(COACH_A, "ended", CODE, {"owner": invalide, "reason": "overlay_close"})
    assert st == 200 and doc(base)["ended"] is True


# ─── H-prod : le 2e onglet ferme, le live de l'onglet qui diffuse survit ───────
@pytest.mark.parametrize("motif", MOTIFS_AUTO)
def test_H_prod_2e_onglet_ferme_409_live_intact(base, motif):
    deux_surfaces(base)
    st, _ = appel(COACH_A, "ended", CODE, _o(B, reason=motif, source="overlay:barre_app:bb22"))
    assert st == 409
    d = doc(base)
    assert d["ended"] is False and d.get("ended_reason") is None and d.get("ended_at") is None
    assert actif_public() is True
    assert set(surfaces(base)) == {A}                       # B est parti
    refus = journal(base, event="ended", outcome="refus")
    assert len(refus) == 1 and refus[0]["status"] == 409
    assert refus[0]["refus"] == "autre_surface_vivante" and refus[0]["autres_surfaces"] == [A]
    assert journal(base, event="ended", outcome="ok") == []


def test_H_prod_puis_l_onglet_qui_diffuse_ferme_200_trace_v553(base):
    deux_surfaces(base)
    assert appel(COACH_A, "ended", CODE, _o(B, reason="overlay_close"))[0] == 409
    assert appel(COACH_A, "heartbeat", CODE, _o(A))[0] == 200          # A diffuse toujours
    resp = _Resp()
    st, _ = appel(COACH_A, "ended", CODE, _o(A, reason="overlay_close", source="overlay:barre_app:aa11"),
                  headers={"x-request-id": "rid-555"}, resp=resp)
    assert st == 200
    d = doc(base)
    assert d["ended"] is True and d["ended_reason"] == "overlay_close"
    assert d["ended_by"] == COACH_A and d["ended_source"] == "overlay:barre_app:aa11"
    assert d["ended_request_id"] == "rid-555" and resp.headers["X-Request-ID"] == "rid-555"
    assert len(d["ended_user_agent"]) == 200
    assert d["ended_prev"]["session_code"] == CODE and d["ended_prev"]["ended"] is False
    ok = journal(base, event="ended", outcome="ok")
    assert len(ok) == 1 and ok[0]["transition"] is True
    assert actif_public() is False


def test_A_ferme_pendant_que_B_bat_409_puis_B_ferme_200(base):
    deux_surfaces(base)
    assert appel(COACH_A, "ended", CODE, _o(A, reason="page_unmount"))[0] == 409
    assert set(surfaces(base)) == {B} and actif_public() is True
    assert appel(COACH_A, "ended", CODE, _o(B, reason="overlay_close"))[0] == 200
    assert doc(base)["ended"] is True


def test_autre_surface_vue_il_y_a_40s_fin_acceptee(base):
    deux_surfaces(base)
    doc(base)["surfaces"][A] = il_y_a(40)
    st, _ = appel(COACH_A, "ended", CODE, _o(B, reason="overlay_close"))
    assert st == 200 and doc(base)["ended"] is True


def test_autre_surface_vue_il_y_a_30s_fin_refusee(base):
    deux_surfaces(base)
    doc(base)["surfaces"][A] = il_y_a(30)
    assert appel(COACH_A, "ended", CODE, _o(B, reason="overlay_close"))[0] == 409


def test_owner_inconnu_de_la_map_seul_accepte(base):
    appel(COACH_A, "started", CODE, _o(A))
    doc(base)["surfaces"][A] = il_y_a(60)
    st, _ = appel(COACH_A, "ended", CODE, _o(Z, reason="overlay_close"))
    assert st == 200 and doc(base)["ended"] is True


# ─── I : rechargement de la page (A -> A') ──────────────────────────────────
def test_I_reload_ancienne_surface_muette_plus_de_35s_fermeture_200(base):
    appel(COACH_A, "started", CODE, _o(A))
    appel(COACH_A, "heartbeat", CODE, _o(A))
    appel(COACH_A, "started", CODE, _o(B))                   # A' = même page rechargée
    doc(base)["surfaces"][A] = il_y_a(40)                   # A ne bat plus
    st, _ = appel(COACH_A, "ended", CODE, _o(B, reason="overlay_close"))
    assert st == 200 and doc(base)["ended"] is True


def test_I_reload_fermeture_avant_35s_409_puis_grace_90s_apres_un_battement(base):
    appel(COACH_A, "started", CODE, _o(A))
    appel(COACH_A, "heartbeat", CODE, _o(A))
    appel(COACH_A, "started", CODE, _o(B))
    appel(COACH_A, "heartbeat", CODE, _o(B))
    assert appel(COACH_A, "ended", CODE, _o(B, reason="overlay_close"))[0] == 409
    assert actif_public() is True
    m = datetime.now(timezone.utc)
    d = dict(doc(base))
    d["last_seen"] = (m - timedelta(seconds=100)).isoformat()   # plus personne ne bat
    assert S.btlive_actif(d, m) is False


def test_I_reload_fermeture_avant_35s_sans_battement_grace_90s_eteint_quand_meme(base):
    """Limite annoncée « le live s'éteint par la grâce de 90 s ». Mais la
    reconnexion EFFACE `last_seen` (V549b) : si A' ferme avant son 1er battement,
    le refus 409 laisse un live sans `last_seen`, donc sans grâce -> 3 h."""
    appel(COACH_A, "started", CODE, _o(A))
    appel(COACH_A, "heartbeat", CODE, _o(A))
    appel(COACH_A, "started", CODE, _o(B))                   # A' monte, ne bat pas encore
    assert appel(COACH_A, "ended", CODE, _o(B, reason="overlay_close"))[0] == 409
    m = datetime.now(timezone.utc) + timedelta(seconds=100)  # personne ne bat pendant 100 s
    assert S.btlive_actif(doc(base), m) is False


# ─── J : grâce 90 s inchangée ────────────────────────────────────────────────
def test_J_grace_90s_inchangee(base):
    appel(COACH_A, "started", CODE, _o(A))
    appel(COACH_A, "heartbeat", CODE, _o(A))
    doc(base)["last_seen"] = il_y_a(60)
    assert actif_public() is True
    doc(base)["last_seen"] = il_y_a(100)
    assert actif_public() is False and doc(base)["ended"] is False
    assert len(journal(base, event="expiration")) == 1


def test_J_btlive_actif_ignore_les_surfaces(base):
    m = datetime.now(timezone.utc)
    d = {"session_code": CODE, "ended": False, "started_at": m.isoformat(),
         "surfaces": {A: m.isoformat()}, "last_seen": (m - timedelta(seconds=91)).isoformat()}
    assert S.btlive_actif(d, m) is False                    # une surface fraîche ne prolonge rien
    d["last_seen"] = m.isoformat()
    assert S.btlive_actif(d, m) is True


def test_J_refus_409_rearme_la_grace_puis_expire_sans_battement(base):
    # V555 : le refus pose last_seen (une autre surface est vivante par définition) ;
    # si plus personne ne bat ensuite, la grâce de 90 s éteint le live — jamais 3 h.
    deux_surfaces(base)
    doc(base)["last_seen"] = il_y_a(100)
    st, _ = appel(COACH_A, "ended", CODE, _o(B, reason="overlay_close"))
    assert st == 409
    vu = S._btlive_date(doc(base)["last_seen"])
    assert datetime.now(timezone.utc) - vu < timedelta(seconds=5)
    assert S.btlive_actif(doc(base), datetime.now(timezone.utc))
    assert not S.btlive_actif(doc(base), datetime.now(timezone.utc) + timedelta(seconds=95))


# ─── explicites ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("motif", MOTIFS_EXPLICITES)
def test_explicite_accepte_malgre_une_autre_surface_vivante(base, motif):
    deux_surfaces(base)
    st, _ = appel(COACH_A, "ended", CODE, _o(B, reason=motif))
    assert st == 200
    d = doc(base)
    assert d["ended"] is True and d["ended_reason"] == motif and d["ended_by"] == COACH_A


# ─── compatibilité ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("motif", MOTIFS_AUTO)
def test_compat_corps_sans_owner_regle_d_avant(base, motif):
    deux_surfaces(base)
    st, _ = appel(COACH_A, "ended", CODE, {"reason": motif})
    assert st == 200 and doc(base)["ended"] is True


def test_compat_live_d_avant_v555_sans_champ_surfaces(base):
    appel(COACH_A, "started", CODE)
    doc(base).pop("surfaces", None)                          # document écrit avant V555
    appel(COACH_A, "heartbeat", CODE)
    st, _ = appel(COACH_A, "ended", CODE, _o(B, reason="overlay_close"))
    assert st == 200 and doc(base)["ended"] is True


@pytest.mark.parametrize("motif", MOTIFS_AUTO + MOTIFS_EXPLICITES)
def test_surface_unique_trace_v553_complete(base, motif):
    appel(COACH_A, "started", CODE, _o(A, source="iframe:barre_app:ab12"))
    appel(COACH_A, "heartbeat", CODE, _o(A))
    resp = _Resp()
    st, _ = appel(COACH_A, "ended", CODE, _o(A, reason=motif, source="overlay:barre_app:ab12"),
                  headers={"x-request-id": "rid-123"}, resp=resp)
    assert st == 200
    attendu = "unknown" if motif == "motif_hors_liste_xyz" else motif
    d = doc(base)
    assert d["ended"] is True and d["ended_reason"] == attendu and d["ended_by"] == COACH_A
    assert d["ended_source"] == "overlay:barre_app:ab12" and d["ended_request_id"] == "rid-123"
    assert len(d["ended_user_agent"]) == 200 and d["ended_prev"]["session_code"] == CODE
    assert len(journal(base, event="ended", outcome="ok")) == 1


# ─── battements ──────────────────────────────────────────────────────────────
def test_heartbeat_accepte_pour_tout_owner_et_pose_sa_surface(base):
    appel(COACH_A, "started", CODE, _o(A))
    avant = len(base.boosttribe_live_journal.lignes)
    st, r = appel(COACH_A, "heartbeat", CODE, _o(Z))        # owner jamais annoncé par started
    assert st == 200 and r["ok"] is True
    assert set(surfaces(base)) == {A, Z}
    assert doc(base).get("last_seen")
    assert len(base.boosttribe_live_journal.lignes) == avant  # aucun journal


def test_heartbeat_sans_owner_ne_pose_aucune_surface(base):
    appel(COACH_A, "started", CODE, _o(A))
    assert appel(COACH_A, "heartbeat", CODE)[0] == 200
    assert set(surfaces(base)) == {A}


def test_heartbeat_autre_super_admin_toujours_403(base):
    appel(COACH_A, "started", CODE, _o(A))
    assert appel(COACH_B, "heartbeat", CODE, _o(Z))[0] == 403
    assert set(surfaces(base)) == {A}


# ─── idempotence et priorités ────────────────────────────────────────────────
def test_ended_idempotent_apres_fin(base):
    deux_surfaces(base)
    assert appel(COACH_A, "ended", CODE, _o(A, reason="host_terminate"))[0] == 200
    # une croix tardive de B sur un live déjà terminé : 200, la 1re trace reste.
    assert appel(COACH_A, "ended", CODE, _o(B, reason="overlay_close"))[0] == 200
    assert doc(base)["ended_reason"] == "host_terminate"
    assert [l["transition"] for l in journal(base, event="ended", outcome="ok")] == [True, False]


def test_403_prioritaire_sur_409(base):
    deux_surfaces(base)
    st, _ = appel(COACH_B, "ended", CODE, _o(Z, reason="overlay_close"))
    assert st == 403 and doc(base)["ended"] is False
    assert set(surfaces(base)) == {A, B}                     # un intrus ne retire rien
    assert [l["status"] for l in journal(base, event="ended", outcome="refus")] == [403]


def test_ended_tardif_ancienne_session_ne_touche_pas_le_live(base):
    deux_surfaces(base)
    st, _ = appel(COACH_A, "ended", "SESS-VIEUX", _o(B, reason="overlay_close"))
    assert st == 200 and doc(base)["ended"] is False and set(surfaces(base)) == {A, B}


def test_aucun_jeton_dans_le_refus(base):
    deux_surfaces(base)
    appel(COACH_A, "ended", CODE, _o(B, reason="overlay_close", token=JETON))
    tout = repr(base.boosttribe_live_journal.lignes) + repr(doc(base))
    assert JETON not in tout and "Bearer" not in tout
