#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V645.3c — BANNIÈRE BOUTIQUE : découpe (début/fin) + miniature persistées.

CE BANC N'ÉCRIT RIEN : il teste la LOGIQUE PURE de validation
(`_v645c_normaliser_banniere`) et les modèles Pydantic `Concept` / `ConceptUpdate`,
sans base de données ni réseau.

CE QU'IL PROUVE
==============================================================================
  * les 3 champs facultatifs existent, avec des défauts rétrocompatibles ;
  * un concept SANS ces champs (ancienne bannière) parse quand même ;
  * `ConceptUpdate` accepte et transmet les 3 champs ;
  * la validation : extrait valide conservé, fin<=début remis à 0/0 (=effacé),
    bornage [0, 86400] s, miniature non interne/http(s) vidée (garde XSS) ;
  * la découpe/miniature NE CONCERNENT QUE la bannière : aucun champ d'offre.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_v645c")

from api import server  # noqa: E402

norm = server._v645c_normaliser_banniere


# ---------------------------------------------------------------- MODÈLES

def test_concept_champs_et_defauts_retrocompatibles():
    c = server.Concept()
    assert c.home_shop_banner_trim_start == 0.0
    assert c.home_shop_banner_trim_end == 0.0
    assert c.home_shop_banner_thumbnail == ""


def test_ancienne_banniere_sans_nouveaux_champs_parse():
    # Une bannière d'avant ce lot (seulement url + type) doit continuer de parser,
    # et retomber sur les défauts (= aucune découpe, pas de poster).
    old = server.Concept(home_shop_banner_url="/api/files/v/video.mp4", home_shop_banner_type="video")
    assert old.home_shop_banner_trim_start == 0.0
    assert old.home_shop_banner_trim_end == 0.0
    assert old.home_shop_banner_thumbnail == ""


def test_conceptupdate_accepte_les_trois_champs():
    cu = server.ConceptUpdate(
        home_shop_banner_trim_start=2.1,
        home_shop_banner_trim_end=16.0,
        home_shop_banner_thumbnail="/api/files/x/t.jpg",
    )
    dump = {k: v for k, v in cu.model_dump().items() if v is not None}
    assert dump["home_shop_banner_trim_start"] == 2.1
    assert dump["home_shop_banner_trim_end"] == 16.0
    assert dump["home_shop_banner_thumbnail"] == "/api/files/x/t.jpg"


# ------------------------------------------------------------- VALIDATION

def test_extrait_valide_conserve():
    u = {"home_shop_banner_trim_start": 2.1, "home_shop_banner_trim_end": 16.0,
         "home_shop_banner_thumbnail": "/api/files/x/t.jpg"}
    norm(u)
    assert u["home_shop_banner_trim_start"] == 2.1
    assert u["home_shop_banner_trim_end"] == 16.0
    assert u["home_shop_banner_thumbnail"] == "/api/files/x/t.jpg"


def test_debut_zero_fin_positive_est_un_extrait_valide():
    u = {"home_shop_banner_trim_start": 0, "home_shop_banner_trim_end": 16}
    norm(u)
    assert u["home_shop_banner_trim_start"] == 0.0
    assert u["home_shop_banner_trim_end"] == 16.0


def test_fin_avant_ou_egale_debut_efface_la_decoupe():
    for s, e in ((5, 3), (4, 4), (0, 0)):
        u = {"home_shop_banner_trim_start": s, "home_shop_banner_trim_end": e}
        norm(u)
        assert u["home_shop_banner_trim_start"] == 0.0
        assert u["home_shop_banner_trim_end"] == 0.0


def test_bornage_negatif_et_plafond():
    u = {"home_shop_banner_trim_start": -4, "home_shop_banner_trim_end": 999999}
    norm(u)
    assert u["home_shop_banner_trim_start"] == 0.0
    assert u["home_shop_banner_trim_end"] == 86400.0


def test_valeur_non_numerique_tombe_a_zero():
    u = {"home_shop_banner_trim_start": "abc", "home_shop_banner_trim_end": 10}
    norm(u)
    # start illisible -> 0 ; fin 10 > 0 -> extrait [0, 10] conservé
    assert u["home_shop_banner_trim_start"] == 0.0
    assert u["home_shop_banner_trim_end"] == 10.0


def test_miniature_interne_et_http_acceptees():
    for v in ("/api/files/x/t.jpg", "https://cdn/x.jpg", "http://cdn/x.jpg", ""):
        u = {"home_shop_banner_thumbnail": v}
        norm(u)
        assert u["home_shop_banner_thumbnail"] == v


def test_miniature_invalide_videe_garde_xss():
    for v in ("javascript:alert(1)", "data:text/html,x", "ftp://x/y.jpg", "pas-une-url"):
        u = {"home_shop_banner_thumbnail": v}
        norm(u)
        assert u["home_shop_banner_thumbnail"] == ""


def test_sans_champ_banniere_rien_nest_touche():
    u = {"primaryColor": "#fff", "appName": "X"}
    norm(u)
    assert u == {"primaryColor": "#fff", "appName": "X"}


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
