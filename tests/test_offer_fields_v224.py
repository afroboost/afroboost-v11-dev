"""V224 — Garde-fou sur les champs d'offre.

Module pur : analyse le source de api/server.py par AST. Aucune dépendance
FastAPI ni MongoDB — ces paquets ne sont pas installés en local, ce qui rend
`from api.server import Offer` impossible (cf. les 24 erreurs de collecte de
la suite existante).

Invariant protégé : PUT /offers/{id} fait `$set: offer.model_dump()` sur un
OfferCreate en `extra="ignore"`. Tout champ persisté absent d'OfferCreate est
donc effacé à chaque sauvegarde d'offre.
"""
import ast
import pathlib

import pytest

SERVER = pathlib.Path(__file__).resolve().parents[1] / "api" / "server.py"

# Champs que le formulaire d'offre envoie et qui DOIVENT survivre à un PUT.
V224_FIELDS = {"duration_minutes", "location", "max_participants"}


def _class_fields(class_name):
    """Retourne les noms des champs annotés d'une classe du module server."""
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                stmt.target.id
                for stmt in node.body
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
            }
    raise AssertionError(f"classe {class_name} introuvable dans {SERVER}")


@pytest.mark.parametrize("model", ["Offer", "OfferCreate"])
def test_les_champs_v224_sont_declares(model):
    manquants = V224_FIELDS - _class_fields(model)
    assert not manquants, f"{model} ne declare pas {sorted(manquants)}"


def test_offer_et_offercreate_restent_symetriques_sur_v224():
    """Un champ sur Offer mais pas sur OfferCreate est efface au premier PUT."""
    assert V224_FIELDS <= _class_fields("Offer") & _class_fields("OfferCreate")


def test_videourl_reste_declare_des_deux_cotes():
    """V224 reutilise videoUrl plutot que d'ajouter un champ video concurrent."""
    assert "videoUrl" in _class_fields("Offer")
    assert "videoUrl" in _class_fields("OfferCreate")
