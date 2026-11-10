# -*- coding: utf-8 -*-
"""V648 — tri et dates de l'onglet « Prospects ». HORS LIGNE.

    MONGO_URL=mongodb://127.0.0.1:27017 DB_NAME=test python3 -m pytest tests/test_v648_tri_prospects.py -q

CE QUE CES TESTS PROTEGENT : le vocabulaire des tris (une valeur inventée est
refusée, pas devinée), la correspondance tri -> champ de date, et le fait qu'un
instant de période ne peut pas être n'importe quelle chaîne.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "test")

from api.server import V648_TRIS, _V648_RE_ISO  # noqa: E402


def test_les_cinq_tris_et_leur_champ_de_date():
    assert sorted(V648_TRIS) == ["ancien", "envoi_ancien", "envoi_recent", "modif_recent", "recent"]
    # L'ajout au CRM.
    assert V648_TRIS["recent"] == ("created_at", -1)
    assert V648_TRIS["ancien"] == ("created_at", 1)
    # L'ENVOI RÉEL, confirmé par le fournisseur — jamais `updated_at`.
    assert V648_TRIS["envoi_recent"] == ("first_contact_sent_at", -1)
    assert V648_TRIS["envoi_ancien"] == ("first_contact_sent_at", 1)
    # La retouche : ce n'est pas un envoi, et le champ le dit.
    assert V648_TRIS["modif_recent"] == ("updated_at", -1)


def test_aucun_tri_ne_confond_modification_et_envoi():
    for cle, (champ, _) in V648_TRIS.items():
        if "envoi" in cle:
            assert champ == "first_contact_sent_at"
        else:
            assert champ != "first_contact_sent_at"


def test_le_defaut_reste_celui_d_avant_v648():
    """Sans `tri`, la route garde `created_at` décroissant : l'écran ne bouge pas."""
    assert V648_TRIS["recent"] == ("created_at", -1)


def test_un_instant_de_periode_doit_etre_un_iso():
    for bon in ("2026-11-10T00:00:00", "2026-11-09T23:00:00.000Z",
                "2026-11-09T23:00:00+00:00", "2026-07-09T22:00:00.123456Z"):
        assert _V648_RE_ISO.match(bon), bon
    for mauvais in ("2026-11-10", "hier", "", "2026-11-10 00:00:00",
                    "' OR 1=1", "2026-13-99T00:00:00Z extra", "{\"$gt\": \"\"}"):
        assert not _V648_RE_ISO.match(mauvais), mauvais


def test_l_ordre_lexicographique_d_un_iso_est_son_ordre_chronologique():
    """C'est ce qui permet au filtre d'être une simple comparaison de chaînes."""
    instants = ["2026-10-11T22:00:00.000Z", "2026-11-09T23:00:00.000Z", "2026-11-10T23:00:00.000Z"]
    assert sorted(instants) == instants
    # Une borne « minuit du lendemain » exclut bien toute la journée précédente,
    # quel que soit le nombre de décimales stocké.
    for stocke in ("2026-11-10T06:21:02", "2026-11-10T23:59:59.999999+00:00"):
        assert stocke < "2026-11-11T00:00:00"
