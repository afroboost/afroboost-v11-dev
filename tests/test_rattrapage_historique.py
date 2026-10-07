# -*- coding: utf-8 -*-
"""V583 — rattrapage historique des essais honorés : liste figée, une fois à vie, mode test exclusif.

Banc hors ligne sur les VRAIES fonctions (`rh_evaluer`, `rh_envoyer`, `rh_passage`, `rh_contenu`)
avec une base en mémoire. Aucun e-mail : l'expéditeur est un compteur.

Lancer : python3 -m pytest tests/test_rattrapage_historique.py -q
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

os.environ.setdefault("JWT_SECRET", "secret-de-test-rh")
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-rh-inexistant:27017")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest
from pymongo.errors import DuplicateKeyError

import api.server as S
from api.routes import shared as SH
from test_p1e_essai_non_reserve import _Coll, _ok

MAINTENANT = datetime(2026, 10, 8, 8, 0, tzinfo=timezone.utc)   # 10:00 Zurich
ADMIN = S.SUPER_ADMIN_EMAILS[0]
LOCAL, DOMAINE = ADMIN.split("@")


class _CollRH(_Coll):
    async def insert_one(self, doc):
        if "_id" in doc and any(d.get("_id") == doc["_id"] for d in self.docs):
            raise DuplicateKeyError("doublon")
        self.docs.append(dict(doc))

    async def count_documents(self, req=None):
        return len([d for d in self.docs if _ok(d, req)])


class _BaseRH:
    def __init__(self, reservations=(), liste=()):
        self.reservations = _CollRH(reservations)
        self.subscriptions = _CollRH()
        self._c = {S.RH_COLL_LISTE: _CollRH(liste), S.RH_COLL_TRACE: _CollRH()}

    def __getitem__(self, nom):
        return self._c[nom]


def presence(code, email, nom="Camille Martin", **extra):
    r = {"id": "r-" + code, "promoCode": code, "userEmail": email, "userName": nom,
         "validated": True, "validatedAt": "2026-09-20T16:26:00+00:00", "userWhatsapp": "+41790000000"}
    r.update(extra)
    return r


def entree(code, email, prenom="Camille"):
    return {"_id": code, "email": email, "prenom": prenom, "presence_at": "2026-09-20T16:26:00+00:00"}


@pytest.fixture()
def env(monkeypatch):
    etat = {"flags": {"RATTRAPAGE_HIST_ENVOI_REEL": True, "RATTRAPAGE_HIST_MODE_TEST": False},
            "envois": [], "converti": set(), "achat": {}, "refus": set(), "stop": set(), "essai": True}

    async def drapeaux():
        return dict(etat["flags"])

    async def est_essai(_db, forfait=None, code=""):
        return etat["essai"]

    async def contexte(code):
        return code, {"id": "sub-" + code, "code": code, "coach_id": ADMIN,
                      "converted_at": "2026-10-01" if code in etat["converti"] else None}, ""

    async def conv_etat(_db, f, coach=""):
        return {"state": SH.CONV_OUVERTE}

    async def conversion(f):
        return etat["achat"].get(f["code"], False)

    async def autorise(e):
        return e not in etat["refus"]

    async def refus_canal(canal, val):
        return val in etat["stop"]

    async def couleur(_c=""):
        return "#D91CD2"

    async def envoi(dest, sujet, html, texte):
        etat["envois"].append((dest, sujet, texte))
        return True

    monkeypatch.setattr(S, "get_feature_flags", drapeaux)
    monkeypatch.setattr(SH, "est_un_essai", est_essai)
    monkeypatch.setattr(SH, "conv_etat", conv_etat)
    monkeypatch.setattr(S, "_conv_contexte", contexte)
    monkeypatch.setattr(S, "p1d_conversion_cours", conversion)
    monkeypatch.setattr(S, "p1b_destinataire_autorise", autorise)
    monkeypatch.setattr(S, "c3_refus_exprime", refus_canal)
    monkeypatch.setattr(S, "_v259_primary_color", couleur)
    monkeypatch.setattr(S, "p1b_envoyer_email", envoi)
    monkeypatch.setattr(S, "p1d_dans_la_fenetre", lambda _n: True)

    def charger(reservations=(), liste=()):
        b = _BaseRH(reservations, liste)
        monkeypatch.setattr(S, "db", b)
        etat["base"] = b
        return b

    etat["charger"] = charger
    return etat


def passage(code="", limite=7):
    return asyncio.run(S.rh_passage(code, limite))


CAM = "camille.client@exemple-reel.ch"


def test_personne_valide_envoyee_une_fois_avec_lien_personnel(env):
    env["charger"]([presence("AFR-CAM1", CAM)], [entree("AFR-CAM1", CAM)])
    assert passage() == {"envoye_reel": 1}
    dest, sujet, texte = env["envois"][0]
    assert dest == CAM and sujet == "Des nouvelles d'Afroboost 💜"
    assert texte.startswith("Salut Camille 👋")
    assert "Tu avais testé Afroboost avec nous il y a quelque temps 💜" in texte
    assert "Continuer avec Afroboost : https://afroboost.com/espace/AFR-CAM1" in texte
    assert "CHF" not in texte and "vient de" not in texte


def test_double_lancement_un_seul_envoi(env):
    env["charger"]([presence("AFR-CAM1", CAM)], [entree("AFR-CAM1", CAM)])
    assert passage() == {"envoye_reel": 1}
    assert passage() == {"deja_envoye": 1}
    assert len(env["envois"]) == 1


def test_trace_atomique_meme_si_le_precontrole_est_contourne(env):
    b = env["charger"]([presence("AFR-CAM1", CAM)], [entree("AFR-CAM1", CAM)])
    b[S.RH_COLL_TRACE].docs.append({"_id": CAM, "statut": "en_cours"})
    assert asyncio.run(S.rh_envoyer({"email": CAM, "code": "AFR-CAM1", "prenom": "Camille"})) == "deja_envoye"
    assert env["envois"] == []


def test_achat_depuis_essai_exclu(env):
    env["charger"]([presence("AFR-CAM1", CAM)], [entree("AFR-CAM1", CAM)])
    env["achat"]["AFR-CAM1"] = True
    assert passage() == {"deja_converti": 1}
    env["achat"]["AFR-CAM1"] = None
    assert passage() == {"conversion_indeterminee": 1}
    env["achat"].clear()
    env["converti"].add("AFR-CAM1")
    assert passage() == {"deja_converti": 1}
    assert env["envois"] == []


def test_j3_deja_recu_exclu(env):
    env["charger"]([presence("AFR-CAM1", CAM, confirmation={"relance_j3": {"statut": "envoye"}})],
                   [entree("AFR-CAM1", CAM)])
    assert passage() == {"j3_deja_recu": 1}
    assert env["envois"] == []


def test_refus_email_et_stop_whatsapp_exclus(env):
    env["charger"]([presence("AFR-CAM1", CAM)], [entree("AFR-CAM1", CAM)])
    env["refus"].add(CAM)
    assert passage() == {"refuse": 1}
    env["refus"].clear()
    env["stop"].add("+41790000000")
    assert passage() == {"stop_whatsapp": 1}
    assert env["envois"] == []


def test_sans_presence_ou_pas_un_essai_exclu(env):
    env["charger"]([presence("AFR-CAM1", CAM, validated=False)], [entree("AFR-CAM1", CAM)])
    assert passage() == {"sans_presence": 1}
    env["charger"]([presence("AFR-CAM1", CAM)], [entree("AFR-CAM1", CAM)])
    env["essai"] = False
    assert passage() == {"pas_un_essai": 1}


def test_donnee_test_exclue_hors_mode_test(env):
    t = "%s+testj3a@%s" % (LOCAL, DOMAINE)
    env["charger"]([presence("AFR-T1", t)], [entree("AFR-T1", t)])
    assert passage() == {"donnee_test": 1}
    assert env["envois"] == []


def test_hors_liste_figee_impossible(env):
    env["charger"]([presence("AFR-CAM1", CAM), presence("AFR-AUTRE", "autre@exemple-reel.ch")],
                   [entree("AFR-CAM1", CAM)])
    assert passage("AFR-AUTRE") == {"hors_liste": 1}
    assert env["envois"] == []


def test_mode_test_exclusif_et_dedup(env):
    env["flags"]["RATTRAPAGE_HIST_MODE_TEST"] = True          # même si ENVOI_REEL est vrai
    env["charger"]([presence("AFR-CAM1", CAM)], [entree("AFR-CAM1", CAM)])
    assert passage("AFR-CAM1", 1) == {"envoye_test": 1}
    assert [e[0] for e in env["envois"]] == [S.rh_destinataire_test()]
    assert S.rh_destinataire_test() == "%s+testrattrapage@%s" % (LOCAL, DOMAINE)
    assert "Salut Camille 👋" in env["envois"][0][2]
    assert passage("AFR-CAM1", 1) == {"deja_envoye": 1}
    assert len(env["envois"]) == 1
    # le test ne consomme PAS le droit réel
    assert env["base"][S.RH_COLL_TRACE].docs[0]["_id"] == "test:AFR-CAM1"


def test_drapeaux_off_simulation_sans_trace(env):
    env["flags"]["RATTRAPAGE_HIST_ENVOI_REEL"] = False
    b = env["charger"]([presence("AFR-CAM1", CAM)], [entree("AFR-CAM1", CAM)])
    assert passage() == {"simulation": 1}
    assert env["envois"] == [] and b[S.RH_COLL_TRACE].docs == []


def test_limite_respectee(env):
    env["charger"]([presence("AFR-A", "a@exemple-reel.ch"), presence("AFR-B", "b@exemple-reel.ch")],
                   [entree("AFR-A", "a@exemple-reel.ch"), entree("AFR-B", "b@exemple-reel.ch")])
    assert passage(limite=1) == {"envoye_reel": 1}
    assert len(env["envois"]) == 1


def test_contenu_sans_prenom():
    sujet, html, texte = S.rh_contenu("", "https://afroboost.com/espace/AFR-X", "#D91CD2")
    assert texte.startswith("Salut 👋") and "Salut ," not in texte
