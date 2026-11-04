#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V646 — BANNIÈRE DE LA PAGE /boutique : données séparées de celle de l'accueil.

CE BANC N'ÉCRIT RIEN : logique pure et modèles Pydantic, sans base ni réseau.

La régression visée a déjà coûté cher (V645.4j) : `ConceptUpdate` ignore en
silence un champ non déclaré, et le front croit avoir enregistré.
"""
import os
import re
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
CLES_BANNIERE = {"home_shop_banner_url", "home_shop_banner_type", "home_shop_banner_trim_start",
                 "home_shop_banner_trim_end", "home_shop_banner_thumbnail", "home_shop_banner_crop"}
CLES = CLES_BANNIERE | {"home_shop_banner_repli"}


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


def test_repli_fourni_seulement_quand_le_partenaire_a_sa_banniere():
    avec = v646_banniere_vitrine(PARTENAIRE, PLATEFORME)["home_shop_banner_repli"]
    assert avec["home_shop_banner_url"] == "/api/files/plateforme.jpg"
    assert avec["home_shop_banner_crop"] == {"x": 0.1, "y": 0.2, "zoom": 2}
    assert set(avec) == CLES_BANNIERE, "liste blanche : rien d'autre du concept de la plateforme"
    assert v646_banniere_vitrine(None, PLATEFORME)["home_shop_banner_repli"] is None
    assert v646_banniere_vitrine(PARTENAIRE, {"home_shop_banner_url": ""})["home_shop_banner_repli"] is None


# -------------------------------------------- QUEL PARTENAIRE POUR QUELLE URL
from api.routes.coach_routes import v646_choisir_coach as choisir, _v646_motifs_prefixe as motifs  # noqa: E402

VIEUX = "2026-01-01T00:00:00+00:00"
NEUF = "2026-11-10T00:00:00+00:00"


def c(ident, name, email, actif=True, cree=VIEUX):
    return {"id": ident, "name": name, "email": email, "is_active": actif, "created_at": cree}


JEAN_A = c("c1", "Jean Martin", "jean@a.com")
JEAN_B = c("c2", "Jean Durand", "jean@b.com")
JEANNE = c("c3", "Jeanne", "jeanne@a.com")
DOUBLE = c("c4", "Marie Dupont", "marie.dupont@a.com")
TOUS = [JEAN_A, JEAN_B, JEANNE, DOUBLE]


def test_les_url_qui_designent_un_seul_coach_ne_changent_pas():
    assert choisir(TOUS, "jean@a.com") is JEAN_A
    assert choisir(TOUS, "JEAN@B.COM") is JEAN_B
    assert choisir(TOUS, "c2") is JEAN_B
    assert choisir(TOUS, "Jean Martin") is JEAN_A
    assert choisir(TOUS, "jean-durand") is JEAN_B
    assert choisir(TOUS, "jeanne") is JEANNE
    assert choisir(TOUS, "marie.dupont") is DOUBLE
    assert choisir(TOUS, "marie-dupont") is DOUBLE


def test_separateurs_autorises_et_rien_d_autre():
    for email in ("paul.dupont@a.com", "paul_dupont@a.com", "paul-dupont@a.com"):
        coach = c("x", "X", email)
        assert choisir([coach], "paul-dupont") is coach, email
    for email in ("paulxdupont@a.com", "paul dupont@a.com", "paul+dupont@a.com", "paul..dupont@a.com"):
        assert choisir([c("x", "X", email)], "paul-dupont") is None, email


def test_url_approximatives_refusees():
    jb = c("x", "X", "jean.banc@a.com")
    court = c("y", "Y", "ab@a.com")
    for u in ("jean-b-nc", "j-an-banc", "je-n.banc", "jean", "jean-", "-banc", "jean--banc"):
        assert choisir([jb], u) is None, u
    for u in ("a-", "-b", "--", "-", "a", "ab-"):
        assert choisir([court], u) is None, u


def test_segment_vide_jamais_de_motif_souple():
    assert motifs("a-") == ["^a\\-@"]
    assert motifs("--") == ["^\\-\\-@"]


def test_injection_de_motif_neutralisee():
    for u in (".*", "^", ".*@a.com", "(a+)+$", "je.n", "[a-z]+", "jean|marie"):
        assert choisir(TOUS, u) is None, u
    for m in motifs(".*") + motifs("(a+)+$"):
        assert re.match(m, "jean@a.com") is None


def test_ambiguite_entre_comptes_existants():
    assert choisir(TOUS, "jean") is None
    assert choisir([JEAN_A, {**JEAN_B, "name": "Jean Martin"}], "jean-martin") is None


def test_fiche_en_double_du_meme_coach_n_est_pas_une_ambiguite():
    assert choisir([JEAN_A, dict(JEAN_A)], "jean-martin") is JEAN_A


def test_email_inconnu_ne_retombe_jamais_sur_son_prefixe():
    assert choisir(TOUS, "jean@z.com") is None
    assert choisir([JEANNE], "jeanne@z.com") is None


def test_nouveau_compte_ne_recupere_ni_ne_bloque():
    victime = c("v", "Victime Banc", "victime@a.com")
    assert choisir([victime, c("p", "Victime Banc", "p@x.org", cree=NEUF)], "victime-banc") is victime
    assert choisir([victime, c("p", "victime", "p@x.org", cree=NEUF)], "victime") is victime
    assert choisir([victime, c("p", "P", "victime@x.org", cree=NEUF)], "victime") is victime
    assert choisir([victime, c("p", "v", "p@x.org", cree=NEUF)], "v") is victime
    assert choisir([victime, c("p", "victime@a.com", "p@x.org", cree=NEUF)], "victime@a.com") is victime


def test_compte_non_valide_sans_effet():
    victime = c("v", "Victime Banc", "victime@a.com")
    attente = c("p", "Victime Banc", "p@x.org", actif=False, cree=NEUF)
    assert choisir([victime, attente], "victime-banc") is victime
    assert choisir([attente], "victime-banc") is None


def test_url_d_un_compte_desactive_jamais_reattribuee():
    ancien = c("v", "Victime Banc", "victime@a.com", actif=False)
    assert choisir([ancien, c("p", "Victime Banc", "p@x.org", cree=NEUF)], "victime-banc") is None


def test_deux_comptes_recents_premier_arrive():
    premier = c("a", "Nom Neuf", "a@x.org", cree="2026-11-10T00:00:00+00:00")
    second = c("b", "Nom Neuf", "b@x.org", cree="2026-11-11T00:00:00+00:00")
    assert choisir([second, premier], "nom-neuf") is premier
    assert choisir([second, premier], "b") is second


def test_plus_de_20_correspondances():
    victime = c("v", "Foule", "foule@a.com")
    foule = [c(f"n{i}", "Foule", f"n{i}@x.org", cree=NEUF) for i in range(60)]
    assert choisir([victime] + foule, "foule") is victime
    assert choisir(foule + [victime], "foule") is victime
    assert choisir([c(f"o{i}", "Foule", f"o{i}@x.org") for i in range(25)], "foule") is None


def test_date_illisible_compte_ancien():
    assert choisir([c("v", "Nom", "v@a.com", cree="pas une date"), c("p", "Nom", "p@x.org", cree=NEUF)], "nom")["id"] == "v"


def test_inconnu():
    assert choisir(TOUS, "personne") is None
    assert choisir([], "jean") is None
    assert choisir(TOUS, "") is None
