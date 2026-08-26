#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LOT « VOIR LES COURS » — WhatsApp propose la MÊME vérité que le site.

CE QUI N'ALLAIT PAS. `lire_cours()` lisait `db.courses` en direct et ne filtrait
QUE `archived` / `visible` / « Nouveau cours ». Le champ `date` était projeté puis
JAMAIS utilisé : mesuré le 26/08/2026 en production, 9 des 11 lignes proposées
étaient des événements ponctuels TERMINÉS (Dîner canadien du 09/08, Laff Festival
du 21/08, …). À l'inverse, deux séances bien réelles — archivées mais marquées
`agenda_abonne` — étaient ABSENTES de WhatsApp alors que le site les affiche.

LA RÈGLE. Il existe déjà UNE vérité publique : `GET /api/sessions/agenda`
(« les occurrences qu'un visiteur peut voir et reserver »). WhatsApp doit la
CONSOMMER, jamais en recopier les filtres — sinon les deux listes redivergeront
au premier changement de règle.

DÉCISIONS DU COACH (26/08/2026), verrouillées ici :
  1. une séance archivée reste proposée SI la vérité du site la présente encore
     (c'est le terme `agenda_abonne`) ; une séance seulement conservée en
     historique ne l'est pas ;
  2. le doublon « Cours à l'unité » / « Afroboost Silent – Session Cardio » sur
     le même créneau est ASSUMÉ tant qu'il est identique sur le site — ce lot ne
     touche à AUCUNE donnée ;
  3. affichage : UNE LIGNE PAR OCCURRENCE FUTURE, 10 maximum, tri chronologique.
     Pas « la prochaine par cours » : cela masquerait un créneau réservable.

Test UNITAIRE hors ligne : AUCUNE connexion MongoDB, AUCUN appel réseau,
AUCUN message envoyé, AUCUNE écriture.

    python tests/test_bot_cours_agenda.py
"""
import ast
import asyncio
import os
import re
import sys
from datetime import datetime, timedelta, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_BOT = os.path.join(RACINE, "api", "routes", "bot_whatsapp_routes.py")
SERVEUR = os.path.join(RACINE, "api", "server.py")

NOMS = {"_couper", "_sans_vrai_nom", "JOURS", "SITE", "MAX_LIGNES_LISTE", "MAX_TITRE_LIGNE",
        "MAX_DESCRIPTION_LIGNE", "MAX_TITRE_BOUTON", "BOUTON_COURS", "BOUTON_OFFRES",
        "BOUTON_COACH", "PREFIXE_PAYER", "PREFIXE_OCCURRENCE", "_JOURS_COURT",
        "construire_liste_occurrences", "_libelle_occurrence", "construire_fiche_cours",
        "_prochaine_seance", "_lien_offre", "_bloc_tarifs", "_formater_prix",
        "_prix", "LIEN_BOUTIQUE", "_LIBELLE_PALIER", "construire_repli"}


def _charger_bot():
    """Prélève les fonctions du VRAI module (il importe FastAPI, absent ici)."""
    src = open(MODULE_BOT, encoding="utf-8").read()
    arbre = ast.parse(src)
    gardes = [n for n in arbre.body
              if (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in NOMS)
              or (isinstance(n, ast.Assign)
                  and any(getattr(t, "id", None) in NOMS for t in n.targets))]
    silencieux = type("L", (), {"info": lambda *a, **k: None, "warning": lambda *a, **k: None,
                                "error": lambda *a, **k: None})()
    espace = {"re": re, "datetime": datetime, "timedelta": timedelta,
              "timezone": timezone, "logger": silencieux}
    exec(compile(ast.Module(body=gardes, type_ignores=[]), MODULE_BOT, "exec"), espace)
    return espace


BOT = _charger_bot()
SRC_BOT = open(MODULE_BOT, encoding="utf-8").read()
SRC_SERVEUR = open(SERVEUR, encoding="utf-8").read()

echecs = 0


def verifier(titre, condition, detail=""):
    global echecs
    if condition:
        print("✅ PASS  %s" % titre)
    else:
        echecs += 1
        print("❌ FAIL  %s\n         → %s" % (titre, detail))


def occurrence(course_id, nom, iso, lieu="Bord du Lac, Auvernier", offres=None):
    """Forme EXACTE renvoyée par `_v184_next_occurrences` + `sessions_agenda`."""
    dt = datetime.fromisoformat(iso)
    return {"course_id": course_id, "name": nom, "weekday": dt.weekday(),
            "time": dt.strftime("%H:%M"), "locationName": lieu,
            "datetime": dt.isoformat(), "date": dt.date().isoformat(),
            "offers": offres or [{"id": "o1", "name": "Cours à l'unité"}],
            "recurrent": True}


# ================================================================ 1. UNE LIGNE PAR OCCURRENCE
def test_une_ligne_par_occurrence():
    """Deux occurrences du MÊME cours = DEUX lignes. C'est la décision 3."""
    occs = [occurrence("c1", "Cours à l'unité", "2026-08-26T18:30"),
            occurrence("c1", "Cours à l'unité", "2026-08-30T18:30")]
    payload, reste = BOT["construire_liste_occurrences"](occs)
    lignes = payload["interactive"]["action"]["sections"][0]["rows"]
    verifier("1. deux occurrences du même cours -> DEUX lignes",
             len(lignes) == 2, "obtenu %d ligne(s)" % len(lignes))
    verifier("1. aucune occurrence perdue", reste == 0, "reste=%s" % reste)


# ================================================================ 2. TRI CHRONOLOGIQUE
def test_tri_chronologique():
    occs = [occurrence("c2", "Sunday Vibes", "2026-08-30T18:30"),
            occurrence("c1", "Session Cardio", "2026-08-26T18:30"),
            occurrence("c3", "Événement", "2026-08-28T20:00")]
    payload, _ = BOT["construire_liste_occurrences"](occs)
    lignes = payload["interactive"]["action"]["sections"][0]["rows"]
    ordre = [l["title"] for l in lignes]
    verifier("2. tri chronologique, pas par jour de semaine",
             ordre == ["Session Cardio", "Événement", "Sunday Vibes"], "obtenu %s" % ordre)


# ================================================================ 3. PLAFOND DE 10
def test_plafond_dix_lignes_et_reste_annonce():
    occs = [occurrence("c%d" % i, "Cours %d" % i, "2026-08-%02dT18:30" % (10 + i))
            for i in range(14)]
    payload, reste = BOT["construire_liste_occurrences"](occs)
    lignes = payload["interactive"]["action"]["sections"][0]["rows"]
    verifier("3. jamais plus de 10 lignes (contrainte WhatsApp)",
             len(lignes) == 10, "obtenu %d" % len(lignes))
    verifier("3. le reste est ANNONCÉ, jamais tronqué en silence",
             reste == 4 and "4 autre" in payload["interactive"]["body"]["text"],
             "reste=%s corps=%r" % (reste, payload["interactive"]["body"]["text"]))


# ================================================================ 4. LA DATE EST VISIBLE
def test_la_date_apparait_dans_la_ligne():
    """Sans date affichée, deux occurrences du même cours sont indiscernables."""
    occs = [occurrence("c1", "Cours à l'unité", "2026-08-26T18:30")]
    payload, _ = BOT["construire_liste_occurrences"](occs)
    desc = payload["interactive"]["action"]["sections"][0]["rows"][0]["description"]
    verifier("4. la description porte la DATE (jour + quantième)",
             "26/08" in desc and "mer" in desc.lower(), "description=%r" % desc)
    verifier("4. la description porte l'HEURE", "18:30" in desc, "description=%r" % desc)
    verifier("4. la description porte le LIEU", "Auvernier" in desc, "description=%r" % desc)


# ================================================================ 4bis. GARDE-FOU V367
def test_les_fiches_jamais_renommees_restent_masquees():
    """V367 : l'assistant d'offre cree un cours « Nouveau cours » des le premier
    clic. L'agenda les exclut deja par `visible`, mais cette regle est une donnee,
    pas un verrou : on garde le filtre de nom, sinon un horaire enregistre trop tot
    se retrouverait propose sous ce nom."""
    occs = [occurrence("c9", "Nouveau cours", "2026-08-26T18:30"),
            occurrence("c1", "Cours à l'unité", "2026-08-27T18:30")]
    payload, _ = BOT["construire_liste_occurrences"](occs)
    titres = [l["title"] for l in payload["interactive"]["action"]["sections"][0]["rows"]]
    verifier("4bis. « Nouveau cours » reste masque (V367)",
             titres == ["Cours à l'unité"], "titres=%s" % titres)


# ================================================================ 5. IDENTIFIANTS UNIQUES
def test_identifiants_de_ligne_uniques():
    """WhatsApp REFUSE une liste dont deux lignes portent le même id."""
    occs = [occurrence("c1", "Cours à l'unité", "2026-08-26T18:30"),
            occurrence("c1", "Cours à l'unité", "2026-08-30T18:30")]
    payload, _ = BOT["construire_liste_occurrences"](occs)
    ids = [l["id"] for l in payload["interactive"]["action"]["sections"][0]["rows"]]
    verifier("5. deux occurrences du même cours -> identifiants DIFFÉRENTS",
             len(set(ids)) == len(ids), "ids=%s" % ids)
    verifier("5. l'identifiant porte le préfixe d'occurrence",
             all(i.startswith(BOT["PREFIXE_OCCURRENCE"]) for i in ids), "ids=%s" % ids)
    verifier("5. l'identifiant reste sous la limite WhatsApp (200)",
             all(len(i) <= 200 for i in ids), "ids=%s" % ids)


# ================================================================ 6. LE CLIC RETROUVE LE COURS
def test_le_clic_retrouve_cours_et_instant():
    occs = [occurrence("c1", "Cours à l'unité", "2026-08-26T18:30"),
            occurrence("c1", "Cours à l'unité", "2026-08-30T18:30")]
    payload, _ = BOT["construire_liste_occurrences"](occs)
    ids = [l["id"] for l in payload["interactive"]["action"]["sections"][0]["rows"]]
    brut = ids[1][len(BOT["PREFIXE_OCCURRENCE"]):]
    verifier("6. l'identifiant contient le cours ET l'instant choisis",
             brut.startswith("c1") and "2026-08-30T18:30" in brut, "brut=%r" % brut)


# ================================================================ 7. LA FICHE MONTRE LA BONNE DATE
def test_fiche_cours_affiche_l_occurrence_choisie():
    """Aujourd'hui la fiche d'un cours ponctuel passé affiche « 18:30 » tout court."""
    cours = {"id": "c1", "name": "Cours à l'unité", "weekday": 3, "time": "18:30",
             "locationName": "Bord du Lac, Auvernier"}
    fiche = BOT["construire_fiche_cours"](cours, None, quand_iso="2026-08-30T18:30:00")
    corps = fiche["text"]["body"]
    verifier("7. la fiche affiche la date de l'occurrence CLIQUÉE",
             "30/08" in corps, "corps=%r" % corps[:200])


# ================================================================ 8. AUCUNE RECOPIE DE FILTRE
def _code_sans_docstring(source, nom):
    """Le CODE d'une fonction, sa docstring retirée.

    Chercher les mots interdits dans le texte brut faisait échouer le test sur
    la documentation elle-même : la docstring de `lire_occurrences` EXPLIQUE
    l'ancien filtre `archived`. On veut interdire l'INSTRUCTION, pas le mot.
    """
    for noeud in ast.walk(ast.parse(source)):
        if isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)) and noeud.name == nom:
            corps = list(noeud.body)
            if (corps and isinstance(corps[0], ast.Expr)
                    and isinstance(getattr(corps[0], "value", None), ast.Constant)
                    and isinstance(corps[0].value.value, str)):
                corps = corps[1:]
            return "\n".join(ast.unparse(n) for n in corps)
    return None


def test_le_bot_consomme_l_agenda_et_ne_recopie_rien():
    verifier("8. le bot appelle le helper d'agenda du site",
             "_agenda_occurrences" in SRC_BOT,
             "aucune référence à _agenda_occurrences dans le module bot")
    code = _code_sans_docstring(SRC_BOT, "lire_occurrences")
    verifier("8. `lire_occurrences` existe", code is not None, "fonction absente")
    if code is not None:
        verifier("8. `lire_occurrences` APPELLE le helper du site",
                 "_agenda_occurrences" in code, "code=%r" % code)
        for interdit in ("db.courses", "archived", "agenda_abonne", "visible"):
            verifier("8. `lire_occurrences` ne recopie PAS le filtre `%s`" % interdit,
                     interdit not in code, "code=%r" % code)
    # Le même verrou sur la construction de la liste : aucun filtre métier ne doit
    # y réapparaître non plus (le garde-fou de nom V367 est la seule exception).
    code_liste = _code_sans_docstring(SRC_BOT, "construire_liste_occurrences")
    if code_liste is not None:
        for interdit in ("archived", "agenda_abonne", "linked_course_ids", "datetime.now"):
            verifier("8. `construire_liste_occurrences` ne refiltre pas `%s`" % interdit,
                     interdit not in code_liste, "code=%r" % code_liste[:300])


# ================================================================ 9. LE SITE N'EST PAS TOUCHÉ
def test_la_route_du_site_delegue_au_helper():
    verifier("9. le helper `_agenda_occurrences` existe côté serveur",
             "async def _agenda_occurrences" in SRC_SERVEUR, "helper absent de server.py")
    bloc = SRC_SERVEUR.split('@api_router.get("/sessions/agenda")', 1)
    verifier("9. la route /sessions/agenda existe toujours", len(bloc) == 2, "route absente")
    if len(bloc) == 2:
        corps = bloc[1].split("\n@api_router", 1)[0]
        verifier("9. la route DÉLÈGUE au helper (aucune logique dupliquée)",
                 "_agenda_occurrences" in corps, "corps=%r" % corps[:400])
        verifier("9. la route ne refiltre plus les cours elle-même",
                 "db.courses.find" not in corps, "corps=%r" % corps[:400])


# ================================================================ 10. RIEN D'AUTRE N'EST TOUCHÉ
def test_perimetre_du_lot():
    # On cherche des APPELS, pas des mots : le module contient un commentaire
    # « NI launch_campaign », qui AFFIRME l'absence. Compter la chaîne nue faisait
    # échouer le test sur sa propre documentation.
    for interdit, libelle in (("_v453_signature_refusee(", "V453 / HMAC"),
                              ("META_APP_SECRET", "secret Meta"),
                              ("launch_campaign(", "campagnes"),
                              ("registre_stop", "registre STOP")):
        verifier("10. le bot n'appelle pas %s" % libelle, interdit not in SRC_BOT,
                 "appel détecté : %s" % interdit)
    verifier("10. le bot n'écrit RIEN dans courses",
             "courses.update" not in SRC_BOT and "courses.delete" not in SRC_BOT
             and "courses.insert" not in SRC_BOT, "écriture détectée sur courses")


def principal():
    # Un test qui LÈVE est un test qui ÉCHOUE — jamais un test qui interrompt la
    # série. Sans ce filet, la toute première fonction manquante masquait les neuf
    # verrous suivants et la ligne de base ROUGE était illisible.
    for essai in (test_une_ligne_par_occurrence, test_tri_chronologique,
                  test_plafond_dix_lignes_et_reste_annonce,
                  test_la_date_apparait_dans_la_ligne,
                  test_les_fiches_jamais_renommees_restent_masquees,
                  test_identifiants_de_ligne_uniques,
                  test_le_clic_retrouve_cours_et_instant,
                  test_fiche_cours_affiche_l_occurrence_choisie,
                  test_le_bot_consomme_l_agenda_et_ne_recopie_rien,
                  test_la_route_du_site_delegue_au_helper,
                  test_perimetre_du_lot):
        try:
            essai()
        except Exception as e:
            verifier(essai.__name__, False, "%s: %s" % (type(e).__name__, e))
    print("=" * 78)
    print("Réseau : 0   |   Base : 0   |   Envois WhatsApp : 0   |   Écritures : 0")
    if echecs:
        print("%d ÉCHEC(S)" % echecs)
        sys.exit(1)
    print("TOUT EST VERT")


if __name__ == "__main__":
    principal()
