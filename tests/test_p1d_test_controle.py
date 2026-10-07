# -*- coding: utf-8 -*-
"""V580 — J+3 (P1-d) : mode test EXCLUSIF `P1D_TEST_CONTROLE`.

Banc hors ligne sur les VRAIES fonctions `p1d_relance_j3` / `p1d_passage` / `p1d_candidats`.
Prouve : un vrai client n'est JAMAIS ciblé en mode test (pas même en simulation) ; une
plus-adresse du super-admin reçoit un envoi RÉEL même si P1_TRIAL_J3_ENVOI_REEL est faux ;
aucun doublon ; achat converti et absence exclus ; hors mode test, rien ne change.

Lancer : python3 -m pytest tests/test_p1d_test_controle.py -q
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ.setdefault("JWT_SECRET", "secret-de-test-p1d")
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p1d-inexistant:27017")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

import api.server as S
from api.routes import shared as SH
from test_p1e_essai_non_reserve import _Base

# 12/10/2026 10:00 Zurich (08:00 UTC) : dans la fenêtre 09-20 h.
MAINTENANT = datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)
ADMIN = S.SUPER_ADMIN_EMAILS[0]
LOCAL, DOMAINE = ADMIN.split("@")
PLUS = "%s+testj3a@%s" % (LOCAL, DOMAINE)


def presence(rid, email, code, heures=80, **extra):
    r = {"id": rid, "userEmail": email, "userName": "Testeur J3", "promoCode": code,
         "validated": True, "coach_id": ADMIN,
         "validatedAt": (MAINTENANT - timedelta(hours=heures)).isoformat()}
    r.update(extra)
    return r


def forfait(code, email, **extra):
    f = {"id": "sub-" + code, "code": code, "email": email, "offer_id": "offre-essai",
         "status": "active", "created_at": (MAINTENANT - timedelta(hours=100)).isoformat()}
    f.update(extra)
    return f


@pytest.fixture()
def env(monkeypatch):
    etat = {"flags": {"P1_TRIAL_J3_ENABLED": True, "P1_TRIAL_J3_ENVOI_REEL": False,
                      "P1D_TEST_CONTROLE": True},
            "envois": [], "base": _Base()}

    async def drapeaux():
        return dict(etat["flags"])

    async def est_essai(_db, forfait=None, code=""):
        return True

    async def contexte(code):
        _f = await etat["base"].subscriptions.find_one({"code": str(code).upper()})
        return str(code).upper(), _f, ""

    async def conv_etat(_db, f, coach=""):
        return {"state": SH.CONV_TERMINEE if (f or {}).get("converted_at") else SH.CONV_OUVERTE}

    async def faux(*a, **k):
        return False

    async def vrai(*a, **k):
        return True

    async def couleur(_c=""):
        return "#D91CD2"

    async def envoi(email, sujet, html, texte):
        etat["envois"].append((email, sujet, texte))
        return True

    monkeypatch.setattr(S, "get_feature_flags", drapeaux)
    monkeypatch.setattr(SH, "est_un_essai", est_essai)
    monkeypatch.setattr(SH, "conv_etat", conv_etat)
    monkeypatch.setattr(S, "_conv_contexte", contexte)
    monkeypatch.setattr(S, "p1d_conversion_cours", faux)
    monkeypatch.setattr(S, "p1b_destinataire_autorise", vrai)
    monkeypatch.setattr(S, "_v259_primary_color", couleur)
    monkeypatch.setattr(S, "p1b_envoyer_email", envoi)

    def charger(forfaits=(), reservations=()):
        etat["base"] = _Base(forfaits, reservations)
        monkeypatch.setattr(S, "db", etat["base"])
        return etat["base"]

    etat["charger"] = charger
    return etat


def passage():
    return asyncio.run(S.p1d_passage(MAINTENANT))


def test_mode_test_vrai_client_jamais_cible_meme_en_simulation(env):
    env["charger"]([forfait("AFR-VRAI", "client@exemple-reel.ch")],
                   [presence("r-vrai", "client@exemple-reel.ch", "AFR-VRAI")])
    assert passage() == {"hors_test_controle": 1}
    assert env["envois"] == []
    assert "relance_j3" not in (env["base"].reservations.docs[0].get("confirmation") or {})


def test_mode_test_plus_adresse_envoi_reel_puis_aucun_doublon(env):
    env["charger"]([forfait("AFR-T1", PLUS)], [presence("r-t1", PLUS, "AFR-T1")])
    assert passage() == {"envoye": 1}
    assert [e[0] for e in env["envois"]] == [PLUS]
    sujet, texte = env["envois"][0][1], env["envois"][0][2]
    assert sujet == "Envie de continuer l'expérience Afroboost ? 🔥"
    assert "Testeur," in texte and "Voir mes options : https://afroboost.com/espace/AFR-T1" in texte
    assert env["base"].reservations.docs[0]["confirmation"]["relance_j3"]["statut"] == "envoye"
    assert passage() == {}                       # 2e cycle : la trace la retire des candidats
    assert len(env["envois"]) == 1


def test_mode_test_achat_converti_exclu(env):
    env["charger"]([forfait("AFR-T2", PLUS, converted_at="2026-10-11T08:00:00+00:00")],
                   [presence("r-t2", PLUS, "AFR-T2")])
    assert passage() == {"deja_converti": 1}
    assert env["envois"] == []


def test_mode_test_absent_jamais_charge(env):
    absent = presence("r-t3", PLUS, "AFR-T3", validated=False,
                      absence_marked_at="2026-10-08T20:00:00+00:00")
    absent.pop("validatedAt")
    env["charger"]([forfait("AFR-T3", PLUS)], [absent])
    assert passage() == {}
    assert env["envois"] == []


def test_mode_test_delai_intact_pas_encore(env):
    env["charger"]([forfait("AFR-T4", PLUS)], [presence("r-t4", PLUS, "AFR-T4", heures=10)])
    assert passage() == {}                       # pas même chargé avant J+3
    assert env["envois"] == []


def test_hors_mode_test_comportement_inchange_simulation(env):
    env["flags"]["P1D_TEST_CONTROLE"] = False
    env["charger"]([forfait("AFR-V", "client@exemple-reel.ch"), forfait("AFR-T5", PLUS)],
                   [presence("r-v", "client@exemple-reel.ch", "AFR-V"), presence("r-t5", PLUS, "AFR-T5")])
    assert passage() == {"simulation": 2}        # ENVOI_REEL faux : simulation pour tous
    assert env["envois"] == []


def test_drapeau_principal_off_rien(env):
    env["flags"]["P1_TRIAL_J3_ENABLED"] = False
    env["charger"]([forfait("AFR-T6", PLUS)], [presence("r-t6", PLUS, "AFR-T6")])
    assert passage() == {"desactive": 1}
    assert env["envois"] == []
