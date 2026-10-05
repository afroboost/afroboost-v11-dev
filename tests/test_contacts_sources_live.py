"""V573 — Contacts : la source « Afroboost Live » visible, aucune fiche enrichie masquée.

Test réel du 05/10 : le Live avait bien COMPLÉTÉ une fiche existante (sources
chat_login + live_afroboost), mais `/api/contacts/all` (1) ne renvoyait que `source`,
(2) écartait cette fiche parce qu'une fiche plus ancienne portait le même WhatsApp,
(3) laissait alors une inscription `users` de même identifiant prendre sa place.
Aucune fusion en base : seul l'assemblage de la liste change.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("JWT_SECRET", "secret-de-test-contacts-sans-rapport-avec-la-production")
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-contacts-inexistant:27017")
import api.server as S  # noqa: E402


def assembler(participants, users=()):
    return S.assembler_contacts_individuels(list(participants), list(users), set(), set(), set())


def par_id(liste, i):
    return next(c for c in liste if c["id"] == i)


def test_A_nouveau_contact_live_fiche_complete_et_sources():
    l = assembler([{"id": "n1", "name": "Bass", "email": "bass@ex.ch", "whatsapp": "+41791112233",
                    "source": "live_afroboost", "sources": ["live_afroboost"]}])
    c = par_id(l, "n1")
    assert c["email"] == "bass@ex.ch" and c["phone"] == "+41791112233"
    assert c["source"] == "live_afroboost" and c["sources"] == ["live_afroboost"]


def test_B_contact_chat_login_rejoint_un_live_les_deux_sources():
    l = assembler([{"id": "b1", "name": "bas", "email": "bas@ex.ch", "whatsapp": "0764444444",
                    "source": "chat_login", "sources": ["chat_login", "live_afroboost"]}])
    assert len(l) == 1 and l[0]["sources"] == ["chat_login", "live_afroboost"]


def test_sans_sources_en_base_la_source_principale_suffit():
    l = assembler([{"id": "x", "email": "x@ex.ch", "source": "chat_login"}])
    assert l[0]["sources"] == ["chat_login"]


def test_C_meme_numero_a_l_identique_une_seule_ligne_sources_cumulees():
    """C (même WhatsApp sous formats différents → même fiche) est garanti à l'ÉCRITURE
    (test_btlive_invite_contact::test_I_*). À l'AFFICHAGE, la règle d'avant est gardée : seul
    un numéro identique regroupe — deux personnes partageant un numéro écrit autrement
    restent visibles toutes les deux (mesuré sur la base réelle : sinon des personnes
    différentes disparaissaient)."""
    l = assembler([{"id": "c1", "email": "", "whatsapp": "0791234567", "source": "chat_login"},
                   {"id": "c2", "email": "", "whatsapp": "0791234567", "source": "live_afroboost"}])
    assert len(l) == 1 and l[0]["sources"] == ["chat_login", "live_afroboost"]


def test_personnes_differentes_numero_ecrit_autrement_restent_visibles():
    l = assembler([{"id": "a", "name": "Sarah", "email": "", "whatsapp": "079 123 45 67", "source": "whatsapp-import"},
                   {"id": "b", "name": "Amanda", "email": "", "whatsapp": "+41791234567", "source": "whatsapp-import"}])
    assert {c["name"] for c in l} == {"Sarah", "Amanda"}


def test_fiche_regroupee_son_inscription_ne_reapparait_pas():
    l = assembler([{"id": "k1", "name": "Kim", "email": "kim@ex.ch", "whatsapp": "0790000001", "source": "manual_promo"},
                   {"id": "k2", "name": "Kim B", "email": "kim2@ex.ch", "whatsapp": "0790000001", "source": "chat_login"}],
                  [{"id": "u-k2", "name": "Kim B", "email": "kim2@ex.ch"}])
    assert [c["id"] for c in l] == ["k1"]


def test_D_deux_anciennes_fiches_meme_whatsapp_aucune_source_perdue():
    """Cas réel : 42c37f39 (plus ancienne) et la fiche enrichie par le Live, même numéro."""
    l = assembler([{"id": "42c3", "name": "Bassi", "email": "coach@ex.ch", "whatsapp": "0760000063",
                    "source": "chat_login", "sources": ["chat_login", "referral"]},
                   {"id": "52b9", "name": "Bassi", "email": "bassi@ex.ch", "whatsapp": "0760000063",
                    "source": "chat_login", "sources": ["chat_login", "live_afroboost"]}],
                  [{"id": "52b9", "name": "bassicustomshoes", "email": "bassi@ex.ch"}])
    assert [c["id"] for c in l] == ["42c3"]                     # une fiche visible, son identifiant gardé
    assert l[0]["sources"] == ["chat_login", "referral", "live_afroboost"]


def test_E_inscription_users_ne_remplace_pas_une_fiche_ecartee():
    l = assembler([{"id": "42c3", "email": "a@ex.ch", "whatsapp": "0760000063", "source": "chat_login"},
                   {"id": "52b9", "email": "b@ex.ch", "whatsapp": "0760000063", "source": "chat_login"}],
                  [{"id": "52b9", "name": "bassicustomshoes", "email": "b@ex.ch"}])
    assert all(c.get("name") != "bassicustomshoes" for c in l)


def test_E_profil_sans_identite_jamais_affiche_comme_contact():
    l = assembler([], [{"name": "Coach Bassi"}, {"id": "", "name": "Sans rien", "email": ""},
                       {"id": "u9", "name": "Sans moyen de contact"}])
    assert l == []


def test_inscription_normale_toujours_affichee():
    l = assembler([], [{"id": "u1", "name": "Ana", "email": "ana@ex.ch"}])
    assert l[0]["source"] == "app" and l[0]["sources"] == ["app"]
