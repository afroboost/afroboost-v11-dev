#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V363 — règles de segmentation des contacts.

Test UNITAIRE, hors ligne : faux contacts fabriqués, aucune connexion à MongoDB,
aucun appel réseau, aucun message envoyé. Il vérifie les trois arbitrages validés
par le coach le 1er août 2026 :

    (1) statut « active » mais date d'expiration passée  -> EXPIRÉ
    (2) statut « active » sans aucune date               -> ACTIF, signalé à vérifier
    (3) 0 séance restante, date encore valable           -> EXPIRÉ (épuisé)
    (4) essai gratuit                                    -> uniquement source free_checkout

ainsi que le garde-fou du lot « interne / test » : le critère est le numéro
RÉELLEMENT porté par la fiche, jamais l'e-mail — marquer par e-mail excluait
3 personnes bien réelles des campagnes.

MODE D'EMPLOI
    python tests/test_segments_contacts.py
    pytest tests/test_segments_contacts.py
"""
import ast
import os
import sys
import types
from datetime import datetime, timedelta, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _charge(chemin, noms):
    """Extrait des objets d'un fichier source et les exécute isolément.

    Les routes vivent dans un module qui importe FastAPI ; l'importer ici
    exigerait toute la pile de production. On ne prélève donc que les fonctions
    de règles, qui sont pures — le test porte ainsi sur le VRAI code livré, sans
    dépendance et sans jamais ouvrir de connexion à la base.
    """
    src = open(chemin, encoding="utf-8").read()
    arbre = ast.parse(src)
    gardes = [n for n in arbre.body
              if (isinstance(n, ast.FunctionDef) and n.name in noms)
              or (isinstance(n, ast.Assign)
                  and any(getattr(c, "id", None) in noms for c in n.targets))]
    # Les fonctions prélevées utilisent les imports du module d'origine : on les
    # fournit explicitement, puisqu'on n'exécute pas l'en-tête du fichier.
    import re as _re
    espace = {"re": _re, "os": os, "datetime": datetime,
              "timezone": timezone, "timedelta": timedelta}
    exec(compile(ast.Module(body=gardes, type_ignores=[]), chemin, "exec"), espace)
    return espace


# La vraie normalisation E.164 du chemin d'envoi, exposée sous le nom qu'attend
# l'import différé de contact_segments_routes.
_srv = _charge(os.path.join(RACINE, "api", "server.py"), {"format_phone_e164"})
_faux = types.ModuleType("api.server")
_faux.format_phone_e164 = _srv["format_phone_e164"]
sys.modules.setdefault("api", types.ModuleType("api"))
sys.modules["api.server"] = _faux

_seg = _charge(os.path.join(RACINE, "api", "routes", "contact_segments_routes.py"),
               {"CONFIG_DEFAUT", "SEGMENTS_CONNUS", "_etat_abonnement",
                "_normalise_email", "_normalise_tel"})
CONFIG_DEFAUT = _seg["CONFIG_DEFAUT"]
SEGMENTS_CONNUS = _seg["SEGMENTS_CONNUS"]
_etat_abonnement = _seg["_etat_abonnement"]
_normalise_email = _seg["_normalise_email"]
_normalise_tel = _seg["_normalise_tel"]

CFG = CONFIG_DEFAUT
DEMAIN = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
HIER = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()


def test_numero_normalise():
    """Un numéro exploitable donne une clé de 9 chiffres ; sinon None."""
    assert _normalise_tel("+41 76 000 00 01", CFG) == "760000001"
    assert _normalise_tel("0760000001", CFG) == "760000001"      # forme suisse locale
    assert _normalise_tel("", CFG) is None
    assert _normalise_tel(None, CFG) is None
    assert _normalise_tel("12345", CFG) is None                  # trop court
    assert _normalise_tel("000000000000", CFG) is None           # que des zéros


def test_email_valide():
    assert _normalise_email("Ana@Ex.COM", CFG) == "ana@ex.com"
    assert _normalise_email("pas-un-email", CFG) is None
    assert _normalise_email(None, CFG) is None


def test_arbitrage_1_date_prime_sur_statut():
    etat, _ = _etat_abonnement(
        [{"status": "active", "expires_at": HIER, "remaining_sessions": 5}], CFG)
    assert etat == "expire", "un abonnement périmé ne doit jamais compter comme actif"


def test_arbitrage_2_sans_date_reste_actif_mais_signale():
    etat, sans_date = _etat_abonnement(
        [{"status": "active", "remaining_sessions": 3}], CFG)
    assert etat == "actif"
    assert sans_date is True, "l'absence de date doit être signalée pour vérification"


def test_arbitrage_3_zero_seance_vaut_expire():
    etat, _ = _etat_abonnement(
        [{"status": "active", "expires_at": DEMAIN, "remaining_sessions": 0}], CFG)
    assert etat == "expire"


def test_abonnement_normal_actif():
    etat, sans_date = _etat_abonnement(
        [{"status": "active", "expires_at": DEMAIN, "remaining_sessions": 4}], CFG)
    assert etat == "actif" and sans_date is False


def test_aucun_abonnement_donne_visiteur():
    etat, _ = _etat_abonnement([], CFG)
    assert etat is None, "sans abonnement connu, la personne est un visiteur"


def test_le_meilleur_abonnement_gagne():
    """Historique conservé : un actif l'emporte sur un ancien expiré."""
    etat, _ = _etat_abonnement([
        {"status": "completed", "expires_at": HIER, "remaining_sessions": 0},
        {"status": "active", "expires_at": DEMAIN, "remaining_sessions": 2},
    ], CFG)
    assert etat == "actif"


def test_numero_interne_reconnu_par_le_numero_seul():
    """« interne / test » se décide sur le numéro, jamais sur l'e-mail."""
    interne = set(CFG["numeros_internes"])
    assert _normalise_tel("+41 76 520 33 63", CFG) in interne
    assert _normalise_tel("+41 76 000 00 01", CFG) not in interne


def test_essai_gratuit_seule_source_reconnue():
    sources = set(CFG["regles"]["essai_gratuit"]["sources"])
    assert sources == {"free_checkout"}, "aucune extrapolation depuis un prix à 0"


def test_segments_connus_stables():
    """Les clés servent d'URL (/contacts/segment/{clé}) : elles ne doivent pas bouger."""
    attendus = {"whatsapp", "email", "abonne_actif", "essai_gratuit", "abonnement_expire",
                "visiteur", "demarchable_whatsapp", "comptes_app", "a_completer",
                "interne_test"}
    assert set(SEGMENTS_CONNUS) == attendus


if __name__ == "__main__":
    echecs = 0
    for nom, fonction in sorted(globals().items()):
        if nom.startswith("test_") and callable(fonction):
            try:
                fonction()
                print(f"✅ PASS  {nom}")
            except Exception as erreur:
                echecs += 1
                print(f"❌ FAIL  {nom}\n         → {type(erreur).__name__}: {erreur}")
    print("\nV363 :", "tous les tests passent" if not echecs else f"{echecs} échec(s)")
    sys.exit(1 if echecs else 0)
