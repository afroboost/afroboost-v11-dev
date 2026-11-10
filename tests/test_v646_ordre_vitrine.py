# -*- coding: utf-8 -*-
"""V646 — l'ordre d'une vitrine. HORS LIGNE : fonction pure, aucune base.

    MONGO_URL=mongodb://127.0.0.1:27017 DB_NAME=test python3 -m pytest tests/test_v646_ordre_vitrine.py -q

CE QUE CES TESTS PROTEGENT. Une vitrine affiche ses propres publications ET
celles qu'un auteur extérieur y a BOOSTEES (V342). Le Boost se paie pour une
PRESENCE de 48 h, jamais pour une priorité. Une publication boostée ne doit
donc JAMAIS pouvoir prendre la première place d'une vitrine qui n'est pas la
sienne en se marquant elle-même « à la une ».
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "test")

from api.server import v646_ordonner_vitrine  # noqa: E402


def pub(pid, date, a_la_une=False, boosted=False):
    return {"id": pid, "created_at": date, "a_la_une": a_la_une, "boosted": boosted}


def ids(pubs):
    return [p["id"] for p in v646_ordonner_vitrine(pubs)]


def test_sans_mise_en_avant_lordre_reste_la_date_decroissante():
    """Le comportement d'avant V646, à l'identique."""
    assert ids([pub("vieux", "2026-11-01T10:00:00+00:00"),
                pub("recent", "2026-11-09T10:00:00+00:00"),
                pub("moyen", "2026-11-05T10:00:00+00:00")]) == ["recent", "moyen", "vieux"]


def test_une_publication_de_la_vitrine_marquee_a_la_une_passe_devant():
    assert ids([pub("recent", "2026-11-09T10:00:00+00:00"),
                pub("vieux_a_la_une", "2026-11-01T10:00:00+00:00", a_la_une=True)]) \
        == ["vieux_a_la_une", "recent"]


def test_UNE_PUBLICATION_BOOSTEE_NE_PREND_PAS_LA_PREMIERE_PLACE():
    """LE DEFAUT QUE CE LOT FERME (revue de sécurité).

    Un coach partenaire marque SA publication « à la une » — son droit — puis
    achète un Boost vers la vitrine d'un autre coach, ou vers l'accueil. Son
    `a_la_une` doit y être sans effet.
    """
    liste = [pub("hote_recent", "2026-11-09T10:00:00+00:00"),
             pub("etranger_boost", "2026-11-08T10:00:00+00:00", a_la_une=True, boosted=True),
             pub("hote_vieux", "2026-11-01T10:00:00+00:00")]
    assert ids(liste) == ["hote_recent", "etranger_boost", "hote_vieux"]
    assert ids(liste)[0] != "etranger_boost"


def test_le_proprietaire_garde_la_main_sur_sa_propre_vitrine():
    """Même scène, mais c'est l'hôte qui s'est mis en avant : il passe devant
    la publication boostée, même plus récente."""
    assert ids([pub("etranger_boost", "2026-11-09T10:00:00+00:00", a_la_une=True, boosted=True),
                pub("hote_a_la_une", "2026-11-02T10:00:00+00:00", a_la_une=True)]) \
        == ["hote_a_la_une", "etranger_boost"]


def test_plusieurs_mises_en_avant_restent_entre_elles_par_date():
    assert ids([pub("une_vieille", "2026-11-01T10:00:00+00:00", a_la_une=True),
                pub("ordinaire", "2026-11-08T10:00:00+00:00"),
                pub("une_recente", "2026-11-05T10:00:00+00:00", a_la_une=True)]) \
        == ["une_recente", "une_vieille", "ordinaire"]


def test_lhistorique_sans_le_champ_ne_change_pas_dordre():
    """Toutes les publications déjà en base n'ont ni `a_la_une` ni `boosted`."""
    historique = [{"id": "a", "created_at": "2026-11-09T10:00:00+00:00"},
                  {"id": "b", "created_at": "2026-11-08T10:00:00+00:00"},
                  {"id": "c", "created_at": "2026-11-07T10:00:00+00:00"}]
    assert ids(historique) == ["a", "b", "c"]


def test_robustesse_liste_vide_date_absente_valeurs_etranges():
    assert v646_ordonner_vitrine([]) == []
    assert v646_ordonner_vitrine(None) == []
    # Une date manquante ne lève pas : elle part en fin de groupe.
    assert ids([{"id": "sans_date"}, pub("date", "2026-11-09T10:00:00+00:00")]) == ["date", "sans_date"]
    # `a_la_une` non booléen : la véracité Python décide, aucune exception.
    assert ids([pub("faux", "2026-11-09T10:00:00+00:00"),
                {"id": "vrai", "created_at": "2026-11-01T10:00:00+00:00", "a_la_une": 1}]) == ["vrai", "faux"]


def test_la_fonction_ne_modifie_pas_la_liste_recue():
    """PURE : l'appelant garde sa liste intacte."""
    origine = [pub("a", "2026-11-01T10:00:00+00:00"), pub("b", "2026-11-09T10:00:00+00:00", a_la_une=True)]
    copie = list(origine)
    v646_ordonner_vitrine(origine)
    assert origine == copie
