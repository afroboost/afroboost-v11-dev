#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V646 — BANNIÈRE DE LA PAGE /boutique : données séparées de celle de l'accueil.

CE BANC N'ÉCRIT RIEN : logique pure et modèles Pydantic, sans base ni réseau.

La régression visée a déjà coûté cher (V645.4j) : `ConceptUpdate` ignore en
silence un champ non déclaré, et le front croit avoir enregistré.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_v646")

from api import server  # noqa: E402

CHAMPS = ("url", "type", "trim_start", "trim_end", "thumbnail", "crop")
norm = server._v645c_normaliser_banniere


def test_les_six_champs_existent_avec_des_defauts_vides():
    c = server.Concept()
    assert c.boutique_page_banner_url == ""
    assert c.boutique_page_banner_type == ""
    assert c.boutique_page_banner_trim_start == 0.0
    assert c.boutique_page_banner_trim_end == 0.0
    assert c.boutique_page_banner_thumbnail == ""
    assert c.boutique_page_banner_crop is None


def test_un_concept_existant_sans_ces_champs_reste_lisible():
    c = server.Concept(home_shop_banner_url="/api/files/a.jpg", home_shop_banner_type="image")
    assert c.home_shop_banner_url == "/api/files/a.jpg"
    assert c.boutique_page_banner_url == ""


def test_concept_update_transmet_les_champs():
    corps = {f"boutique_page_banner_{k}": v for k, v in {
        "url": "/api/files/p.jpg", "type": "video", "trim_start": 1.5, "trim_end": 6.0,
        "thumbnail": "/api/files/t.jpg", "crop": {"x": 0.2, "y": 0.3, "zoom": 2},
    }.items()}
    dump = server.ConceptUpdate(**corps).model_dump()
    for cle, val in corps.items():
        assert dump[cle] == val


def test_ecrire_une_banniere_ne_touche_pas_l_autre():
    """Les champs non envoyés restent `None`, donc filtrés avant l'écriture en base."""
    filtre = lambda d: {k: v for k, v in d.items() if v is not None}  # noqa: E731
    page = filtre(server.ConceptUpdate(boutique_page_banner_url="/api/files/p.jpg").model_dump())
    assert not [k for k in page if k.startswith("home_shop_banner")]
    accueil = filtre(server.ConceptUpdate(home_shop_banner_url="/api/files/a.jpg").model_dump())
    assert not [k for k in accueil if k.startswith("boutique_page_banner")]


def test_validation_identique_sur_la_banniere_de_page():
    u = {
        "boutique_page_banner_thumbnail": "javascript:alert(1)",
        "boutique_page_banner_trim_start": 5,
        "boutique_page_banner_trim_end": 3,
        "boutique_page_banner_crop": {"x": 9, "y": -1, "zoom": 50, "pirate": 1},
    }
    norm(u)
    assert u["boutique_page_banner_thumbnail"] == ""
    assert u["boutique_page_banner_trim_start"] == 0.0
    assert u["boutique_page_banner_trim_end"] == 0.0
    assert u["boutique_page_banner_crop"] == {"x": 1.0, "y": 0.0, "zoom": 3.0}


def test_normaliser_l_une_n_invente_rien_sur_l_autre():
    u = {"boutique_page_banner_trim_start": 1, "boutique_page_banner_trim_end": 2}
    norm(u)
    assert set(u) == {"boutique_page_banner_trim_start", "boutique_page_banner_trim_end"}
    v = {"home_shop_banner_trim_start": 1, "home_shop_banner_trim_end": 2}
    norm(v)
    assert set(v) == {"home_shop_banner_trim_start", "home_shop_banner_trim_end"}


# ---------------------------------------------------- VITRINE D'UN PARTENAIRE
from api.routes.coach_routes import v646_banniere_vitrine  # noqa: E402

PLATEFORME = {
    "home_shop_banner_url": "/api/files/plateforme.jpg", "home_shop_banner_type": "image",
    "home_shop_banner_trim_start": 0.0, "home_shop_banner_trim_end": 0.0,
    "home_shop_banner_thumbnail": "", "home_shop_banner_crop": {"x": 0.1, "y": 0.2, "zoom": 2},
    "boutique_page_banner_url": "/api/files/page.jpg", "termsText": "prive", "coach_id": "x@example.com",
}
PARTENAIRE = {
    "home_shop_banner_url": "/api/files/lui.webm", "home_shop_banner_type": "video",
    "home_shop_banner_trim_start": 1.0, "home_shop_banner_trim_end": 6.0,
    "home_shop_banner_thumbnail": "/api/files/mini.jpg", "home_shop_banner_crop": {"x": 0.9, "y": 0.8, "zoom": 1.5},
    "coach_id": "lui@example.com", "boutique_page_banner_url": "/api/files/autre.jpg",
}
CLES = {"home_shop_banner_url", "home_shop_banner_type", "home_shop_banner_trim_start",
        "home_shop_banner_trim_end", "home_shop_banner_thumbnail", "home_shop_banner_crop"}


def test_partenaire_configure_sa_banniere_complete():
    b = v646_banniere_vitrine(PARTENAIRE, PLATEFORME)
    assert b["home_shop_banner_url"] == "/api/files/lui.webm"
    assert b["home_shop_banner_type"] == "video"
    assert (b["home_shop_banner_trim_start"], b["home_shop_banner_trim_end"]) == (1.0, 6.0)
    assert b["home_shop_banner_thumbnail"] == "/api/files/mini.jpg"
    assert b["home_shop_banner_crop"] == {"x": 0.9, "y": 0.8, "zoom": 1.5}


def test_partenaire_sans_banniere_ou_retiree_garde_celle_de_la_plateforme():
    for lui in (None, {}, {"home_shop_banner_url": ""}, {"home_shop_banner_url": "", "home_shop_banner_trim_end": 9.0}):
        b = v646_banniere_vitrine(lui, PLATEFORME)
        assert b["home_shop_banner_url"] == "/api/files/plateforme.jpg"
        assert b["home_shop_banner_trim_end"] == 0.0, "aucun réglage du partenaire ne s'applique au média de la plateforme"


def test_liste_blanche_stricte():
    for lui in (PARTENAIRE, None):
        assert set(v646_banniere_vitrine(lui, PLATEFORME)) == CLES


def test_aucune_banniere_nulle_part():
    b = v646_banniere_vitrine(None, None)
    assert set(b) == CLES and b["home_shop_banner_url"] == "" and b["home_shop_banner_crop"] is None

