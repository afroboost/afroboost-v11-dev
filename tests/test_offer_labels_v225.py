"""V225 — Garde-fou sur les libellés de paliers.

Module pur : analyse le source de api/server.py par AST. Aucune dépendance
FastAPI ni MongoDB — ces paquets ne sont pas installés en local.

Invariant protégé : PUT /offers/{id} fait `$set: offer.model_dump()` sur un
OfferCreate en `extra="ignore"`. Tout champ persisté absent d'OfferCreate est
donc effacé en base à chaque sauvegarde d'offre.
"""
import ast
import pathlib

import pytest

SERVER = pathlib.Path(__file__).resolve().parents[1] / "api" / "server.py"

V225_LABELS = {"label_early_bird", "label_standard", "label_last_minute"}


def _class_fields(class_name):
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
def test_les_libelles_v225_sont_declares(model):
    manquants = V225_LABELS - _class_fields(model)
    assert not manquants, f"{model} ne declare pas {sorted(manquants)}"


def test_symetrie_offer_offercreate_sur_les_libelles():
    """Un champ sur Offer mais pas sur OfferCreate est efface au premier PUT."""
    assert V225_LABELS <= _class_fields("Offer") & _class_fields("OfferCreate")


def test_les_prix_des_paliers_restent_declares():
    """Non-regression V223 : les libelles accompagnent les prix, ne les remplacent pas."""
    prix = {"price_early_bird", "price_standard", "price_last_minute"}
    assert prix <= _class_fields("Offer")
    assert prix <= _class_fields("OfferCreate")
