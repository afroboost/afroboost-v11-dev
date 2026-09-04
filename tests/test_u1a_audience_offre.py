#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""U1a — L'AUDIENCE D'UNE OFFRE, SANS TOUCHER A CE QUI EXISTE.

POURQUOI CE BANC EXISTE
==============================================================================
Une offre peut desormais dire a qui elle s'adresse. C'est un champ de plus sur
une collection VIVANTE : 8 offres reelles, rattachees a des reservations, des
paiements, des forfaits et des essais. Le risque n'est pas que le champ marche
— c'est qu'il abime les offres d'avant.

LE PIEGE QUE CE BANC SURVEILLE EN PREMIER. `PUT /offers` fait
`$set: offer.model_dump()` sur `OfferCreate`, en `extra="ignore"` : tout champ
absent de CE modele est EFFACE en base a chaque sauvegarde d'offre. Le fichier
`server.py` le dit lui-meme en commentaire (V224). Un champ ajoute a `Offer`
mais oublie dans `OfferCreate` disparaitrait donc au premier enregistrement.

CE QUE CE FICHIER PROUVE
==============================================================================
  * les deux modeles portent le champ — la symetrie est verifiee, pas supposee ;
  * une offre SANS audience vaut « all » : le passe est inchange ;
  * les trois valeurs sont acceptees, et elles seules ;
  * une valeur inconnue redevient « all » au lieu de faire echouer la lecture ;
  * « mixte priorite femmes » de Spordate est REFUSEE — le comportement qu'elle
    promet n'existe pas ici ;
  * aucun champ existant n'a disparu des modeles.

Aucun reseau, aucune base, aucune ecriture.
    python3 tests/test_u1a_audience_offre.py
"""
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

os.environ.setdefault("MONGO_URL", "mongodb://bouchon-u1a-inexistant:27017")
os.environ.setdefault("JWT_SECRET", "secret-de-banc-u1a")

import api.server as S  # noqa: E402

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))
    print("  %-6s %s" % ("OK  " if cond else "ECHEC", nom))
    if detail and not cond:
        print("           -> %s" % detail)


# ============================================================================
print("\n1. LA SYMETRIE DES MODELES — le piege V224")

verifier("1a. `Offer` porte le champ", "audience" in S.Offer.model_fields)
verifier("1b. `OfferCreate` le porte AUSSI — sinon il serait efface a chaque PUT",
         "audience" in S.OfferCreate.model_fields)
_champs_offer = set(S.Offer.model_fields)
_champs_create = set(S.OfferCreate.model_fields)
verifier("1c. tout champ de `OfferCreate` existe dans `Offer`",
         _champs_create.issubset(_champs_offer),
         str(sorted(_champs_create - _champs_offer)))

# ============================================================================
print("\n2. LE PASSE EST INCHANGE")

_vide = S.Offer(name="Cours a l'unite", price=30.0)
verifier("2a. une offre sans audience vaut « all »", _vide.audience == "all", _vide.audience)
_vide_c = S.OfferCreate(name="Cours a l'unite", price=30.0)
verifier("2b. idem a la creation", _vide_c.audience == "all", _vide_c.audience)
verifier("2c. le champ part bien dans le `model_dump` envoye a Mongo",
         S.OfferCreate(name="x", price=0.0).model_dump().get("audience") == "all")

# Les champs metier deja en place sont toujours la : ce lot n'en retire aucun.
for _c in ("name", "price", "images", "videoUrl", "thumbnail", "visible",
           "linked_course_ids", "isProduct", "variants", "tva", "stock",
           "progressive_pricing", "price_early_bird", "price_standard",
           "price_last_minute", "duration_minutes", "location",
           "max_participants", "position", "category"):
    verifier("2d. `%s` est toujours dans OfferCreate" % _c, _c in _champs_create)

# ============================================================================
print("\n3. LES TROIS VALEURS, ET ELLES SEULES")

verifier("3a. la liste est exactement celle attendue",
         S.U1A_AUDIENCES == ("all", "women-only", "men-only"), str(S.U1A_AUDIENCES))
for _v in S.U1A_AUDIENCES:
    verifier("3b. « %s » est acceptee" % _v, S.u1a_audience(_v) == _v)
verifier("3c. la casse et les espaces sont tolérés",
         S.u1a_audience("  Women-Only ") == "women-only")

# ============================================================================
print("\n4. CE QUI N'EST PAS RECONNU REDEVIENT « all »")

for _v, _pourquoi in (
        (None, "absent"),
        ("", "chaine vide"),
        ("nimportequoi", "valeur libre"),
        (42, "pas une chaine"),
        ({"a": 1}, "un objet"),
        ("mixed-priority-women", "la 4e valeur de Spordate")):
    verifier("4a. %s -> « all »" % _pourquoi, S.u1a_audience(_v) == "all", repr(_v))

verifier("4b. « mixte priorite femmes » n'est PAS dans la liste — elle promet "
         "une visibilite que rien n'applique ici",
         "mixed-priority-women" not in S.U1A_AUDIENCES)

# ============================================================================
print("\n5. CE LOT NE FILTRE RIEN")
# L'audience est stockee et affichee. Aucun moteur ne la consulte : si un jour
# une reservation, une recherche ou la vitrine s'y refere, ce banc doit rougir
# pour qu'on en discute AVANT.
_src = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
_usages = _src.count('"audience"') + _src.count("'audience'") + _src.count("audience=")
verifier("5a. le champ n'est lu que par sa normalisation et les deux routes",
         _usages <= 6, "%d occurrences — verifier qu'aucun filtre ne s'en sert" % _usages)
verifier("5b. aucune requete Mongo ne filtre sur l'audience",
         '{"audience"' not in _src and "'audience':" not in _src.replace('"audience":', ''))

# ============================================================================
print("\n6. LA LISTE BLANCHE DU FRONTEND — le piege qui a fait echouer U1a")
# Le champ etait declare dans les deux modeles ET saisi dans le wizard, et
# pourtant il ne persistait pas : `addOffer` (CoachDashboard.js) construit le
# corps de la requete comme une LISTE BLANCHE explicite. Un champ absent de cet
# objet ne PART JAMAIS — le backend le recoit donc vide et le ramene a « all ».
# Le fichier avertissait deja de ce piege trois fois (V223, V224, V256) ; il
# manquait une verification qui le rende impossible a oublier.
import re  # noqa: E402

_DASH = os.path.join(RACINE, "frontend", "src", "components", "CoachDashboard.js")
_src_dash = open(_DASH, encoding="utf-8").read()
_i = _src_dash.index("const offerData = {")
_bloc = _src_dash[_i:_src_dash.index("\n      };", _i)]
_cles_envoyees = set(re.findall(r"^\s{8}([a-zA-Z_][a-zA-Z0-9_]*):", _bloc, re.M))

verifier("6a. `audience` part bien dans la requete", "audience" in _cles_envoyees,
         "sans cette ligne, le choix du coach n'atteint jamais le serveur")

# `coach_id` est la SEULE exception legitime : la propriete est posee par le
# serveur a partir de l'identite de l'appelant, jamais envoyee par le client.
_ATTENDU_ABSENT = {"coach_id"}
_manquants = _champs_create - _cles_envoyees - _ATTENDU_ABSENT
verifier("6b. tout champ du modele traverse la liste blanche",
         not _manquants,
         "champs saisissables mais jamais envoyes : %s" % sorted(_manquants))

# ============================================================================
print("\n7. L'ALLER-RETOUR COMPLET")
# create -> normalisation serveur -> document -> relecture -> hydratation.
# On rejoue la chaine REELLE : le modele, puis la normalisation appelee par les
# deux routes, puis la regle d'affichage du wizard.


def _hydrater(document):
    """La regle du wizard : `form.audience || 'all'`. Copie fidele."""
    return document.get("audience") or "all"


for _choix, _attendu in (("all", "all"),
                         ("women-only", "women-only"),
                         ("men-only", "men-only")):
    _corps = S.OfferCreate(name="TEST AUDIENCE", price=0.0, audience=_choix).model_dump()
    _corps["audience"] = S.u1a_audience(_corps.get("audience"))   # ce que font POST et PUT
    _relu = dict(_corps)                                          # ce que rend le GET
    verifier("7a. aller-retour « %s » : ecrit en base" % _choix,
             _relu.get("audience") == _attendu, repr(_relu.get("audience")))
    verifier("7b. aller-retour « %s » : bouton actif a la reouverture" % _choix,
             _hydrater(_relu) == _attendu, repr(_hydrater(_relu)))

# Une offre d'AVANT ce lot : aucun champ, et le wizard doit afficher « all ».
verifier("7c. offre historique sans le champ -> « Tout le monde »",
         _hydrater({"name": "PULSE x10 cours", "price": 250.0}) == "all")

# Et le wizard lit bien cette regle-la, pas une autre.
_WIZ = os.path.join(RACINE, "frontend", "src", "components", "dashboard", "OfferWizard.js")
_src_wiz = open(_WIZ, encoding="utf-8").read()
verifier("7d. le wizard hydrate avec le meme repli",
         "form.audience || 'all'" in _src_wiz)

# ============================================================================
print("\n" + "=" * 78)
_ok = sum(1 for _, c, _ in RESULTATS if c)
print("U1a : %d / %d verifications" % (_ok, len(RESULTATS)))
print("=" * 78)
if _ok != len(RESULTATS):
    print("\nECHECS :")
    for nom, cond, detail in RESULTATS:
        if not cond:
            print("  - %s%s" % (nom, ("  [%s]" % detail) if detail else ""))
    sys.exit(1)
