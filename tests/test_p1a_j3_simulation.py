# -*- coding: utf-8 -*-
"""P1A (07/10/2026) — J+3 après essai : vérification EN SIMULATION, sans rien activer.

En production, `P1_TRIAL_J3_ENABLED=true` et `P1_TRIAL_J3_ENVOI_REEL=false` : la boucle horaire
`_p1d_boucle_relance_j3` évalue chaque candidat mais n'écrit rien et n'envoie rien. Ce banc rejoue
la VRAIE fonction `p1d_relance_j3` sur des cas datés, avec l'écran de conversion simulé, et prouve :
  * présence d'essai à J+4, 10h00 Zurich, écran ouvert → « simulation », aucun envoi, aucune écriture ;
  * achat depuis l'essai → « deja_converti » ; écran fermé → « ecran_ferme » ;
  * avant J+3 → « pas_encore » ; après J+10 → « trop_tard » ; la nuit → « hors_fenetre » ;
  * présence payante → « pas_un_essai » ; déjà relancé → « deja_traitee » (en réel).

Aucun e-mail : l'expéditeur est un compteur. Lancer : python3 -m pytest tests/test_p1a_j3_simulation.py -q
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ.setdefault("JWT_SECRET", "secret-de-test-p1a-j3")
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p1a-inexistant:27017")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import api.server as S
from api.routes import shared as SH

# 07/10/2026 08:00 UTC = 10:00 à Zurich (heure d'été) : dans la fenêtre 09:00-20:00.
MAINTENANT = datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)


def presence(jours_avant, code="AFR-ESSAI1", **extra):
    r = {"id": "resa-%s-%s" % (code, jours_avant), "promoCode": code, "userEmail": "invitee@exemple.test",
         "userName": "Amina", "validated": True,
         "validatedAt": (MAINTENANT - timedelta(days=jours_avant)).isoformat()}
    r.update(extra)
    return r


@pytest.fixture()
def env(monkeypatch):
    etat = {"envois": [], "reel": False, "conv": SH.CONV_OUVERTE, "achat": False, "jetons": set()}

    async def drapeaux():
        return {"P1_TRIAL_J3_ENABLED": True, "P1_TRIAL_J3_ENVOI_REEL": etat["reel"]}

    async def est_essai(_db, forfait=None, code=""):
        return code == "AFR-ESSAI1"

    async def contexte(code):
        return None, {"id": "forfait-essai", "code": code}, ""

    async def conv_etat(_db, _forfait, _coach):
        return {"state": etat["conv"]}

    async def conversion(_forfait):
        return etat["achat"]

    async def autorise(_e):
        return True

    async def couleur(_c):
        return "#D91CD2"

    async def faux_envoi(email, sujet, html, texte):
        etat["envois"].append((email, sujet))
        return True

    async def reserver(_db, rid, canal, quand):
        if (rid, canal) in etat["jetons"]:
            return False
        etat["jetons"].add((rid, canal))
        return True

    async def cloturer(*a, **k):
        return None

    monkeypatch.setattr(S, "get_feature_flags", drapeaux)
    monkeypatch.setattr(SH, "est_un_essai", est_essai)
    monkeypatch.setattr(S, "_conv_contexte", contexte)
    monkeypatch.setattr(SH, "conv_etat", conv_etat)
    monkeypatch.setattr(S, "p1d_conversion_cours", conversion)
    monkeypatch.setattr(S, "p1b_destinataire_autorise", autorise)
    monkeypatch.setattr(S, "_v259_primary_color", couleur)
    monkeypatch.setattr(S, "p1b_envoyer_email", faux_envoi)
    monkeypatch.setattr(SH, "_rc_reserver_jeton", reserver)
    monkeypatch.setattr(SH, "_rc_cloturer_jeton", cloturer)
    return etat


def j3(r, quand=MAINTENANT):
    return asyncio.run(S.p1d_relance_j3(r, maintenant=quand))


def test_simulation_rien_ne_part(env):
    assert j3(presence(4)) == "simulation"
    assert env["envois"] == [] and env["jetons"] == set(), "simulation : ni envoi, ni jeton écrit"


def test_arret_si_achete(env):
    env["achat"] = True
    assert j3(presence(4)) == "deja_converti"
    env["achat"] = False
    env["conv"] = SH.CONV_TERMINEE
    assert j3(presence(4)) == "deja_converti"


def test_ecran_ferme_rien_a_proposer(env):
    env["conv"] = "fermee"
    assert j3(presence(4)) == "ecran_ferme"


def test_bornes_de_temps(env):
    assert j3(presence(2)) == "pas_encore"
    assert j3(presence(11)) == "trop_tard"
    nuit = MAINTENANT.replace(hour=21)            # 23:00 à Zurich
    assert j3(presence(4), quand=nuit) == "hors_fenetre"


def test_jamais_une_presence_payante(env):
    assert j3(presence(4, code="AFR-PULSE1")) == "pas_un_essai"


def test_absent_jamais_candidat():
    """Le J+3 ne lit que des présences : `p1d_candidats` exige `validated: True` en base."""
    import inspect
    src = inspect.getsource(S.p1d_candidats)
    assert '"validated": True' in src


def test_en_reel_une_seule_fois(env):
    env["reel"] = True
    r = presence(4)
    assert j3(r) == "envoye"
    assert j3(r) == "deja_traitee"
    assert len(env["envois"]) == 1
    assert "continuer" in env["envois"][0][1].lower()
