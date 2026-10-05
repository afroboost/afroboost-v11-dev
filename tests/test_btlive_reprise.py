"""V571 — LIEN D'INVITATION PERSISTANT : fermer la fenêtre ≠ terminer le Live.

Mesuré en production (journal `boosttribe_live_journal`, 01/10) : 15 fois, une fin par la
croix (`overlay_close`) suivie en moins de 60 s d'un `started` sous un NOUVEAU code. Le lien
déjà envoyé pointait alors vers une salle que l'hôte ne rejoindrait plus.

Règle : « reprenable par l'hôte » (aucune fin EXPLICITE, < 3 h) est séparé de « en direct »
(battement < 90 s, badge public). Seuls Terminer / Quitter rendent le code définitivement mort.
"""
import asyncio
import inspect
from datetime import datetime, timedelta, timezone

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_btlive_proprietaire import (S, base, appel, doc, journal, COACH_A, COACH_B, CODE,  # noqa: F401
                                      MOTIFS_AUTO, MOTIFS_EXPLICITES)

T0 = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def _doc(**k):
    d = {"session_code": CODE, "host": COACH_A, "started_at": T0.isoformat(), "ended": False}
    d.update(k)
    return d


def run(c):
    return asyncio.new_event_loop().run_until_complete(c)


# ── la règle pure ──────────────────────────────────────────────────────────────
def test_reprenable_tant_que_rien_n_est_termine():
    assert S.btlive_reprenable(_doc(), T0 + timedelta(minutes=5)) is True


@pytest.mark.parametrize("motif", ["overlay_close", "page_unmount", "server_expiration", "unknown", None])
def test_une_fin_automatique_laisse_le_live_reprenable(motif):
    assert S.btlive_reprenable(_doc(ended=True, ended_reason=motif), T0 + timedelta(minutes=5)) is True


def test_seul_terminer_rend_le_live_definitivement_fini():
    assert S.btlive_reprenable(_doc(ended=True, ended_reason="host_terminate"), T0 + timedelta(minutes=5)) is False


def test_quitter_hote_est_un_depart_TEMPORAIRE():
    """V571b (décision Bassi 05/10) : « Quitter le live » de l'hôte ne termine rien."""
    assert S.btlive_reprenable(_doc(ended=True, ended_reason="host_leave"), T0 + timedelta(minutes=5)) is True


def test_battement_perdu_depuis_longtemps_reste_reprenable_mais_plus_en_direct():
    d = _doc(last_seen=(T0 + timedelta(minutes=1)).isoformat())
    maintenant = T0 + timedelta(minutes=10)
    assert S.btlive_actif(d, maintenant) is False          # badge public : plus « EN DIRECT »
    assert S.btlive_reprenable(d, maintenant) is True      # l'hôte retrouve SON live


def test_plus_de_3_h_n_est_plus_reprenable():
    assert S.btlive_reprenable(_doc(), T0 + timedelta(hours=3, minutes=1)) is False


def test_document_vide_ou_sans_code():
    assert S.btlive_reprenable(None, T0) is False
    assert S.btlive_reprenable(_doc(session_code=""), T0) is False


# ── retour de l'hôte : le même code, pour l'hôte seulement ─────────────────────
def test_reprise_hote_rend_le_meme_code_apres_la_croix(base):
    appel(COACH_A, "started", CODE)
    appel(COACH_A, "ended", CODE, {"reason": "overlay_close"})
    assert run(S._btlive_etat()) == {"active": False}                # plus « en direct »…
    assert run(S._btlive_reprise_hote(COACH_A)) == CODE               # …mais reprenable par SON hôte
    assert run(S._btlive_reprise_hote(COACH_B)) is None              # jamais par quelqu'un d'autre


def test_apres_terminer_aucun_code_n_est_rendu(base):
    appel(COACH_A, "started", CODE)
    appel(COACH_A, "ended", CODE, {"reason": "host_terminate"})
    assert run(S._btlive_reprise_hote(COACH_A)) is None


def test_apres_quitter_l_hote_reprend_le_meme_code(base):
    appel(COACH_A, "started", CODE)
    appel(COACH_A, "ended", CODE, {"reason": "host_leave"})
    assert run(S._btlive_etat()) == {"active": False}            # badge éteint tout de suite
    assert run(S._btlive_reprise_hote(COACH_A)) == CODE           # même code au retour
    appel(COACH_A, "started", CODE)
    assert journal(base, event="started", reconnexion=True)       # le même live reprend


def test_started_sur_le_meme_code_apres_la_croix_est_une_REPRISE(base):
    appel(COACH_A, "started", CODE)
    debut = doc(base)["started_at"]
    appel(COACH_A, "ended", CODE, {"reason": "overlay_close"})
    st, _ = appel(COACH_A, "started", CODE)
    assert st == 200
    d = doc(base)
    assert d["ended"] is False and d["session_code"] == CODE
    assert d["started_at"] == debut                                   # le garde-fou des 3 h ne glisse pas
    assert journal(base, event="started", reconnexion=True), "journalisé comme une reconnexion"
    assert run(S._btlive_etat())["active"] is True


def test_started_apres_terminer_reste_un_nouveau_live(base):
    appel(COACH_A, "started", CODE)
    appel(COACH_A, "ended", CODE, {"reason": "host_terminate"})
    appel(COACH_A, "started", CODE)
    assert journal(base, event="started", reconnexion=True) == []


def test_access_donne_bt_session_a_l_hote_qui_revient():
    src = inspect.getsource(S.boosttribe_access)
    assert "_btlive_reprise_hote(" in src
    assert 'usage.get("kind") == "admin"' in src
