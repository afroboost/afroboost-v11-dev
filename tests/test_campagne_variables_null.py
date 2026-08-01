#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V362 — Un contact incomplet ne doit plus faire tomber TOUTE la campagne.

CONTEXTE (incident du 31 juillet 2026)
    Deux campagnes WhatsApp vers « Contacts WhatsApp » se sont soldées par
    « Échoué (0) ». L'erreur enregistrée en base n'était PAS une erreur Meta :

        error: "decoding to str: need a bytes-like object, NoneType found"

    `substitute_campaign_variables()` lit les champs du contact avec
    `contact.get("name", "")` — or ce défaut ne s'applique QUE si la clé est
    absente. Un champ PRÉSENT valant `null` en base traverse donc en `None` et
    arrive tel quel dans `re.sub(pattern, None, ...)`, qui lève un TypeError.
    L'appel se trouvant HORS try/except dans la boucle des contacts de
    `launch_campaign()`, un seul contact incomplet interrompait la fonction
    avant l'écriture de `results` : statut « failed », `results: []` (d'où le
    « (0) » de l'historique) et `launchedAt: null`.

CE QUE VÉRIFIE CE TEST
    1. name / email / téléphone à null -> aucune exception, message rendu.
    2. Le contact complet garde une substitution correcte (pas de régression).
    3. Une boucle de campagne mêlant contacts sains et contacts incomplets va
       jusqu'au BOUT (tous les destinataires traités), ce qui est le vrai
       symptôme corrigé.

MODE D'EMPLOI
    python tests/test_campagne_variables_null.py     # autonome, sans réseau
    pytest tests/test_campagne_variables_null.py

La fonction est extraite du VRAI fichier de production (`api/server.py`) par
analyse syntaxique puis exécutée isolément : aucune dépendance (motor, fastapi…)
n'est nécessaire, et le test ne peut pas passer sur une copie périmée du code.
"""
import ast
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVEUR = os.path.join(RACINE, "api", "server.py")
NOM_FONCTION = "substitute_campaign_variables"


def charger_fonction():
    """Extrait `substitute_campaign_variables` de api/server.py et l'exécute isolément."""
    source = open(SERVEUR, encoding="utf-8").read()
    arbre = ast.parse(source)
    for noeud in arbre.body:
        if isinstance(noeud, ast.FunctionDef) and noeud.name == NOM_FONCTION:
            espace = {}
            exec(compile(ast.Module(body=[noeud], type_ignores=[]), SERVEUR, "exec"), espace)
            return espace[NOM_FONCTION]
    raise AssertionError(f"{NOM_FONCTION} introuvable dans {SERVEUR}")


substituer = charger_fonction()

MESSAGE = "Bonjour {prénom} 👋 — écris-nous sur {tel} ou {email}. À bientôt {nom} !"


def test_contact_avec_champs_null_ne_leve_pas():
    """Les trois formes de champ à null passent sans exception."""
    for etiquette, contact in [
        ("name null", {"name": None, "email": "a@b.c", "whatsapp": "+41760000000"}),
        ("email null", {"name": "Ana", "email": None, "whatsapp": "+41760000000"}),
        ("whatsapp+phone null", {"name": "Ana", "email": "a@b.c", "whatsapp": None, "phone": None}),
        ("tout null", {"name": None, "email": None, "whatsapp": None, "phone": None}),
    ]:
        rendu = substituer(MESSAGE, contact)
        assert isinstance(rendu, str), etiquette
        # Un champ manquant devient vide, jamais le texte "None"
        assert "None" not in rendu, f"{etiquette} : 'None' injecté dans le message"


def test_contact_complet_inchange():
    """Non-régression : la substitution normale continue de fonctionner."""
    rendu = substituer(MESSAGE, {"name": "Ana Silva", "email": "ana@ex.com",
                                 "whatsapp": "+41760000000"})
    assert "Bonjour Ana " in rendu          # {prénom} -> premier mot du nom
    assert "+41760000000" in rendu          # {tel}
    assert "ana@ex.com" in rendu            # {email}
    assert "Ana Silva" in rendu             # {nom}


def test_la_campagne_va_jusquau_bout():
    """Le vrai symptôme : un contact incomplet au milieu ne coupe plus la boucle."""
    destinataires = [
        {"name": "Ana Silva", "email": "ana@ex.com", "whatsapp": "+41760000001"},
        {"name": None, "email": "bob@ex.com", "whatsapp": "+41760000002"},   # le fautif
        {"name": "Chris", "email": None, "whatsapp": None, "phone": None},   # le fautif bis
        {"name": "Dina", "email": "dina@ex.com", "whatsapp": "+41760000004"},
    ]
    traites = []
    for contact in destinataires:
        # Reproduit l'appel de launch_campaign, qui n'est PAS protégé par un try/except
        traites.append(substituer(MESSAGE, contact))
    assert len(traites) == len(destinataires), (
        "la boucle de campagne s'est arrêtée avant le dernier destinataire")


def test_message_vide_ou_contact_vide():
    """Garde-fous d'entrée : rien à substituer, rien ne casse."""
    assert substituer("", {"name": None}) == ""
    assert substituer(MESSAGE, {}) == MESSAGE
    assert substituer(MESSAGE, None) == MESSAGE


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
    print("\nV362 :", "tous les tests passent" if not echecs else f"{echecs} échec(s)")
    sys.exit(1 if echecs else 0)
