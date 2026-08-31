#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2-UX SIMPLE — AMELIORER L'EXISTANT, SANS RIEN RECONSTRUIRE.

CE QUE CE LOT FAIT, ET SURTOUT CE QU'IL NE FAIT PAS
==============================================================================
Trois changements de PRESENTATION, zero changement de mecanique :

  1. la landing d'essai montre 3 seances au lieu de 12 ; les 9 autres restent
     dans le document, repliees ;
  2. une reservation confirmee affiche enfin un panneau qui dit quand et ou ;
  3. la fiche partenaire dit qui reserve.

CE QUI N'EST PAS TOUCHE — et c'est le coeur du lot. ESSAI-7 reste intact : la
redirection vers `/espace/AFR-XXXXXX` apres `POST /checkout/free` demeure, parce
qu'elle corrige un defaut MESURE le 25/08/2026 (« le code etait accorde, la
seance ne l'etait pas »). Aucune route backend n'est creee ni modifiee, aucun
contrat n'evolue, aucune reservation n'est automatisee.

LE PIEGE QUE CE FICHIER SURVEILLE
==============================================================================
Les 12 `Event` JSON-LD de la landing sont l'actif SEO le plus concret de la
page — ils la rendent eligible aux resultats enrichis. Ils derivent de
`_m1_seances()`, INDEPENDAMMENT du bloc qui dessine les cartes. Reduire
l'affichage a 3 seances ne doit donc RIEN retirer aux moteurs : les 12
occurrences restent dans le document et dans les donnees structurees. La
section 2 le verifie des deux cotes.

    python3 tests/test_p2ux_simple.py
"""
import ast
import os
import re
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

RESULTATS = []


def verifier(intitule, condition, detail=""):
    RESULTATS.append((intitule, bool(condition), detail))
    print("  %-6s %s" % ("OK  " if condition else "ECHEC", intitule))
    if detail and not condition:
        print("           -> %s" % detail)
    return bool(condition)


SRC = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
ARBRE = ast.parse(SRC)


def _code(nom):
    """Le CODE EXECUTE seul — docstring et commentaires retires."""
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == nom:
            corps = list(n.body)
            if (corps and isinstance(corps[0], ast.Expr)
                    and isinstance(getattr(corps[0], "value", None), ast.Constant)
                    and isinstance(corps[0].value.value, str)):
                corps = corps[1:]
            return "\n".join(ast.unparse(x) for x in corps).replace("'", '"')
    raise AssertionError(nom)


def _code_js(source):
    sans = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    sans = re.sub(r"\{/\*.*?\*/\}", "", sans, flags=re.S)
    return "\n".join(l for l in sans.split("\n") if not l.strip().startswith("//"))


ESPACE = open(os.path.join(RACINE, "frontend", "src", "components",
                           "SubscriberSpace.js"), encoding="utf-8").read()
FICHE = open(os.path.join(RACINE, "frontend", "src", "components", "coach",
                          "PartnerApplications.js"), encoding="utf-8").read()
APPJS = open(os.path.join(RACINE, "frontend", "src", "App.js"), encoding="utf-8").read()
SW = open(os.path.join(RACINE, "frontend", "public", "sw.js"), encoding="utf-8").read()
ESPACE_C, FICHE_C, APP_C = _code_js(ESPACE), _code_js(FICHE), _code_js(APPJS)


print("=" * 78)
print("P2-UX SIMPLE — PRESENTATION SEULE")
print("=" * 78)

print("\n=== 1. LA MECANIQUE N'A PAS BOUGE D'UN OCTET ===")

# ESSAI-7 : la redirection vers l'espace reste, et reste conditionnee a la
# preuve d'octroi par le serveur.
verifier("1a. ESSAI-7 : la redirection vers /espace est toujours la",
         "cibleRedirectionEssai(freeRes.data)" in APP_C
         and "window.location.href = cibleEssai" in APP_C)
verifier("1b. ... et elle reste conditionnee a un octroi PROUVE par le serveur",
         "if (cibleEssai) {" in APP_C)
verifier("1c. le contrat de POST /checkout/free est inchange",
         "class FreeCheckoutRequest" in open(
             os.path.join(RACINE, "api", "routes", "checkout_routes.py"),
             encoding="utf-8").read()
         and "course_id" not in open(
             os.path.join(RACINE, "api", "routes", "checkout_routes.py"),
             encoding="utf-8").read().split("class FreeCheckoutRequest")[1][:600])
verifier("1d. AUCUNE reservation automatique n'est ajoutee apres le checkout",
         "space/${encodeURIComponent" not in APP_C
         and "/reserve/" not in APP_C)
verifier("1e. la route de reservation de l'espace n'est pas modifiee",
         "@api_router.post(\"/subscriber/space/{access_code}/reserve/{course_id}\")" in SRC)
verifier("1f. aucune route backend nouvelle dans ce lot",
         SRC.count("@api_router.get(\"/partners/{partner_slug}/stats\")") == 1
         and SRC.count("@api_router.get(\"/sessions/agenda\")") == 1)
verifier("1g. l'anti-doublon V185 F3 est intact", "dup_query = " in SRC)
verifier("1h. l'attribution n'est touchee nulle part",
         "m2a_bloc_propre" in open(os.path.join(RACINE, "api", "routes",
                                                "checkout_routes.py"),
                                   encoding="utf-8").read())


print("\n=== 2. LA LANDING : PLUS COURTE, MAIS RIEN N'EST RETIRE ===")

PAGE = _code("_m1_page")if any(
    isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == "_m1_page"
    for n in ast.walk(ARBRE)) else None

verifier("2a. la constante d'affichage existe et vaut 3",
         "_M1_SEANCES_VISIBLES = 3" in SRC)
verifier("2b. le plafond de DONNEES reste a 12 — on n'a pas coupe la source",
         "_M1_MAX_SEANCES = 12" in SRC)
verifier("2c. `_m1_seances()` n'est PAS modifiee (elle alimente le JSON-LD)",
         "for occ in occurrences[:_M1_MAX_SEANCES]" in SRC)
verifier("2d. l'apercu prend les N premieres seances, toutes dates confondues",
         "_toutes[:_M1_SEANCES_VISIBLES]" in SRC)
verifier("2e. le RESTE est rendu, dans un <details> replie",
         "_toutes[_M1_SEANCES_VISIBLES:]" in SRC
         and "<details><summary>Voir tout le planning" in SRC)
verifier("2f. le <details> est FERME par defaut (pas de ` open`)",
         "<details><summary>Voir tout le planning" in SRC
         and "<details open><summary>Voir tout le planning" not in SRC)
verifier("2g. les 12 Event JSON-LD viennent de `_evenements`, hors du bloc visuel",
         "] + _evenements)" in SRC)
verifier("2h. aucun JavaScript ajoute a la landing — <details> est natif",
         "_M1_SEANCES_VISIBLES" in SRC and "addEventListener" not in
         SRC.split("_M1_SEANCES_VISIBLES")[1][:4000])
verifier("2i. AUCUN calendrier n'a ete construit sur la landing",
         "calendrier" not in SRC.split("_M1_SEANCES_VISIBLES")[1][:4000].lower()
         or "grille" in SRC)
verifier("2j. SessionsModal n'est PAS duplique",
         "SessionsModal" not in SRC)

for balise, quoi in [("<title>%(titre)s</title>", "title"),
                     ('rel="canonical"', "canonical"),
                     ("<h1>", "H1"),
                     ("Prochaines séances à Neuchâtel", "H2 des seances"),
                     ('"@type": "Event"', "type Event")]:
    verifier("2k. le SEO conserve son %s" % quoi,
             balise in SRC or balise.replace('"', "'") in SRC,
             "introuvable : %s" % balise)

verifier("2l. la microcopy client dit QUAND on choisit sa seance",
         "Inscris-toi" in SRC and "choisis la séance qui te convient" in SRC)
verifier("2m. ... et elle ne promet PAS de choisir sur la landing",
         "Choisis ta séance ci-dessous" not in SRC)


print("\n=== 3. LA CONFIRMATION APRES RESERVATION ===")

verifier("3a. un etat porte la seance qu'on vient de reserver",
         "const [seanceConfirmee, setSeanceConfirmee] = useState(null);" in ESPACE_C)
verifier("3b. il est pose APRES la reponse du serveur, pas au clic",
         "setSeanceConfirmee({" in ESPACE_C
         and ESPACE_C.index("const res = await axios.post(")
         < ESPACE_C.index("setSeanceConfirmee({"))
# Bornee au `try` de CETTE reservation : le fichier contient plusieurs
# `} catch (err) {`, et comparer a la premiere occurrence du fichier ne prouvait
# rien. On decoupe a partir de l'appel reseau lui-meme.
# Le fichier contient SIX `const res = await axios.post(` — OTP, join,
# stripe-checkout, recharge… Se decouper sur le premier ne prouvait rien : on
# vise l'appel de reservation par son URL.
_bloc_reserve = ESPACE_C.split("/reserve/${encodeURIComponent", 1)[1]
_try_reserve = _bloc_reserve.split("} catch", 1)[0]
verifier("3c. ... dans le bloc de SUCCES du try de la reservation, jamais "
         "dans son catch",
         "setSeanceConfirmee({" in _try_reserve,
         "la pose n'est pas dans le try de la reservation")
verifier("3d. le panneau ne s'affiche que s'il y a une seance confirmee",
         "{seanceConfirmee && (" in ESPACE_C)
verifier("3e. le titre attendu est affiche",
         "Ta réservation est confirmée" in ESPACE)

for champ, quoi in [("seanceConfirmee.date", "date"), ("seanceConfirmee.time", "heure"),
                    ("seanceConfirmee.lieu", "lieu"), ("seanceConfirmee.nom", "nom du cours")]:
    verifier("3f. le %s vient de l'occurrence REELLE" % quoi, champ in ESPACE_C)

verifier("3g. la date passe par `formatOccurrence`, deja utilise ailleurs",
         "formatOccurrence(" in ESPACE_C
         and "formatOccurrence(\n                seanceConfirmee.date" in ESPACE)
verifier("3h. AUCUNE valeur en dur : ni date, ni heure, ni lieu",
         not re.search(r"seanceConfirmee[\s\S]{0,600}?(18:30|Auvernier|septembre)", ESPACE_C))
verifier("3i. le badge « Reserve » de chaque date est CONSERVE",
         "Réservé" in ESPACE)
verifier("3j. aucune redirection apres la confirmation",
         "window.location" not in ESPACE_C.split("setSeanceConfirmee({")[1][:1500])
verifier("3k. aucune vente poussee dans le panneau",
         not re.search(r"seanceConfirmee[\s\S]{0,1200}?(Acheter|PULSE|Offre|checkout)", ESPACE))
verifier("3l. le panneau passe DEVANT le bloc ESSAI-7 (order -2 contre -1)",
         "order: -2" in ESPACE and "order: -1" in ESPACE)


print("\n=== 4. IDEMPOTENCE : RIEN N'A ETE REECRIT ===")

verifier("4a. le verrou de double clic existant est intact",
         "if (!occurrence?.course_id || reservingKey) return;" in ESPACE_C)
verifier("4b. aucune requete n'est ajoutee au montage de l'espace",
         ESPACE_C.count("axios.post(") == ESPACE.count("axios.post("))
verifier("4c. la confirmation est un ETAT d'ecran, pas une URL — donc rien a "
         "rejouer au rafraichissement",
         "seanceConfirmee" in ESPACE_C and "/reservation-confirmee" not in ESPACE_C)
verifier("4d. aucun nouvel appel reseau n'est introduit par ce lot",
         "setSeanceConfirmee" in ESPACE_C
         and "await axios" not in ESPACE_C.split("setSeanceConfirmee({")[1][:800])


print("\n=== 5. LES ROLES, DITS EN UNE PHRASE ===")

verifier("5a. la fiche partenaire dit ce que le partenaire a a faire",
         "Partagez votre invitation Afroboost" in FICHE
         and "réserve directement sa séance" in FICHE)
# Borne au TEXTE AFFICHE, pas aux identifiants : une recherche large tombait
# sur `p2cNomFichierQr`, le nom de la fonction du fichier QR — un faux positif
# qui n'a rien a voir avec des donnees clients.
_microcopy = FICHE.split("Partagez votre invitation Afroboost", 1)[1].split("</p>", 1)[0]
_microcopy = "Partagez votre invitation Afroboost" + _microcopy
verifier("5a-bis. la phrase affichee reste sobre : ni fichier, ni contacts, ni "
         "donnees clients, ni transfert",
         not re.search(r"fichier|contact|donnée|base client|transfert|import",
                       _microcopy, re.I),
         _microcopy.strip()[:110])
verifier("5a-ter. ... et elle tient en une phrase courte",
         len(" ".join(_microcopy.split())) < 120,
         "%d caracteres" % len(" ".join(_microcopy.split())))
verifier("5b. la phrase est placee avec le lien et le QR",
         FICHE.index("Partagez votre invitation Afroboost")
         < FICHE.index("Télécharger le QR"))
verifier("5c. AUCUN formulaire de reservation cote partenaire",
         not re.search(r"<input[^>]*(nom|email|téléphone|whatsapp)", FICHE, re.I)
         or "Identifiant du partenaire" in FICHE)
verifier("5d. aucune route de reservation appelee depuis la fiche partenaire",
         "/reserve/" not in FICHE_C and "checkout" not in FICHE_C.lower())
verifier("5e. la fiche n'appelle que la lecture et la decision",
         set(re.findall(r"axios\.(\w+)\(", FICHE_C)) <= {"get", "patch"},
         "%s" % set(re.findall(r"axios\.(\w+)\(", FICHE_C)))


print("\n=== 6. PERIMETRE ET CACHE ===")

verifier("6a. le Service Worker est au moins en v472",
         bool(re.search(r"afroboost-v(\d+)", SW))
         and int(re.search(r"afroboost-v(\d+)", SW).group(1)) >= 472,
         re.search(r"afroboost-v(\d+)", SW).group(0))
verifier("6b. App.js n'est PAS modifie par ce lot",
         "seanceConfirmee" not in APP_C and "_M1_SEANCES_VISIBLES" not in APP_C)
verifier("6c. aucun nouveau composant, aucune nouvelle dependance",
         "qrcode.react" in FICHE and "SessionsModal" not in ESPACE_C)


print("\n" + "=" * 78)
_ok = sum(1 for _, c, _ in RESULTATS if c)
_total = len(RESULTATS)
print("P2-UX SIMPLE — %d / %d verifications au vert" % (_ok, _total))
print("=" * 78)
if _ok != _total:
    print("\nECHECS :")
    for i, c, d in RESULTATS:
        if not c:
            print("  - %s%s" % (i, ("  [%s]" % d) if d else ""))
sys.exit(0 if _ok == _total else 1)
