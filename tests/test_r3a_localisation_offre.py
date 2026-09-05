#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R3a — OU SE PASSE CETTE OFFRE ?

CE BANC N'APPELLE NI LA PRODUCTION NI AUCUN RESEAU. Base en memoire, vraies
fonctions de route : c'est le comportement qui est mesure, pas le texte.

CE QU'IL PROUVE
==============================================================================
  A. un cours a l'unite avec ville + adresse -> stocke tel quel
  B. un evenement aussi
  C. changer la ville -> relue apres rechargement
  D. changer l'adresse -> relue aussi
  E. une offre commerciale SANS lieu -> acceptee (rien n'est force)
  F. U1b n'a pas regresse : la ville sort du meme repli qu'avant
  G. une charge utile malformee -> validation propre, jamais un 500
  H. l'adresse du LIEU n'est pas celle d'une personne
  I. une offre historique sans lieu -> aucune valeur inventee
  J. l'API publique rend la ville et l'adresse, et rien de prive

ET LE PIEGE CENTRAL DU LOT : `region` n'est PAS la ville.
"""
import asyncio
import io
import os
import re
import socket
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
RESULTATS = []


def verifier(intitule, condition, detail=""):
    detail = "" if detail == "" else str(detail)
    RESULTATS.append((intitule, bool(condition), detail))
    print("  %-6s %s" % ("OK  " if condition else "ECHEC", intitule))
    if detail and not condition:
        print("           -> %s" % detail)


_GETADDR = socket.getaddrinfo


def _dns(hote, port, *a, **k):
    if str(hote) in ("localhost", "127.0.0.1", "::1", None):
        return _GETADDR(hote, port, *a, **k)
    raise RuntimeError("sortie reseau interdite : %s" % hote)


socket.getaddrinfo = _dns

os.environ["JWT_SECRET"] = "secret-de-test-r3a"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-r3a-inexistant:27017")
import api.server as S  # noqa: E402
from fastapi import HTTPException  # noqa: E402

# Les outils viennent de `_base_memoire`, PAS du banc R2c : importer un banc
# le RE-EXECUTE, et son rapport se melangeait a celui-ci.
sys.path.insert(0, os.path.join(RACINE, "tests"))
from _base_memoire import _Base, _Requete, _attrape, ADMIN, PARTENAIRE  # noqa: E402

BASE = _Base()
S.db = BASE


def _offre(**kw):
    corps = {"name": "Offre", "price": 30.0, "offer_type": "single_class"}
    corps.update(kw)
    return S.OfferCreate(**corps)


async def _creer(email, **kw):
    return await S.create_offer(_offre(**kw), _Requete(email))


def _lire(oid):
    return asyncio.run(BASE.offers.find_one({"id": oid}))


# ==========================================================================
print("\nLE PIEGE DU LOT — `region` N'EST PAS LA VILLE")
# 12 cours de production sur 23 portent `region=neuchatel` alors qu'ils se
# tiennent a AUVERNIER. Toute migration `region -> city` aurait ete fausse
# une fois sur deux, en silence.
_src = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
_socle = _src[_src.index("# R3a — OU SE PASSE CETTE OFFRE"):_src.index("class Offer(BaseModel):")]
_code = "\n".join(re.sub(r"#.*$", "", l) for l in _socle.splitlines())
_code = re.sub(r'"""[\s\S]*?"""', "", _code)
for indice in ("region", "M1GEO1", "neuchatel", "lausanne", "name", "price"):
    verifier("le socle R3a ne LIT jamais « %s »" % indice, indice not in _code)
verifier("aucune table de villes codee en dur", "Neuch" not in _code and "Auvernier" not in _code)

# ==========================================================================
print("\nA + B — CREER UNE OFFRE SITUEE")

o_a, _c = _attrape(_creer(ADMIN, name="Cours du samedi", offer_type="single_class",
                          location_city="Auvernier",
                          location_address="Bord du Lac, Auvernier",
                          location_lat=46.9765, location_lng=6.8791))
verifier("A. un cours a l'unite se cree avec un lieu", _c is None, _c)
verifier("A-bis. la ville est stockee", o_a and o_a.location_city == "Auvernier",
         o_a and o_a.location_city)
verifier("A-ter. l'adresse aussi",
         o_a and o_a.location_address == "Bord du Lac, Auvernier")
verifier("A-quater. les coordonnees aussi",
         o_a and o_a.location_lat == 46.9765 and o_a.location_lng == 6.8791,
         o_a and (o_a.location_lat, o_a.location_lng))

o_b, _c = _attrape(_creer(ADMIN, name="Silent Lakeside", offer_type="event",
                          location_city="Lausanne",
                          location_address="Esplanade de Montbenon, Lausanne"))
verifier("B. un evenement aussi", _c is None, _c)
verifier("B-bis. ville et adresse stockees",
         o_b and o_b.location_city == "Lausanne"
         and o_b.location_address.startswith("Esplanade"))
verifier("B-ter. sans coordonnees : elles restent NULLES, jamais 0",
         o_b and o_b.location_lat is None and o_b.location_lng is None,
         o_b and (o_b.location_lat, o_b.location_lng))

# ==========================================================================
print("\nC + D — MODIFIER, PUIS RELIRE")

_r, _c = _attrape(S.update_offer(o_a.id, _offre(
    name="Cours du samedi", location_city="Colombier",
    location_address="Bord du Lac, Auvernier"), _Requete(ADMIN)))
verifier("C. la ville se modifie", _c is None, _c)
verifier("C-bis. ... et se RELIT depuis la base",
         _lire(o_a.id).get("location_city") == "Colombier",
         _lire(o_a.id).get("location_city"))

_r, _c = _attrape(S.update_offer(o_a.id, _offre(
    name="Cours du samedi", location_city="Colombier",
    location_address="Place du Port 3, Colombier"), _Requete(ADMIN)))
verifier("D. l'adresse se modifie et se relit",
         _lire(o_a.id).get("location_address") == "Place du Port 3, Colombier",
         _lire(o_a.id).get("location_address"))

# LE PIEGE DE LA SYMETRIE, huitieme edition : un champ absent du modele
# d'ENTREE serait efface par le `$set: offer.model_dump()` a chaque sauvegarde.
for champ in ("location_city", "location_address", "location_lat", "location_lng"):
    verifier("les deux modeles portent « %s » — sinon le PUT l'effacerait" % champ,
             champ in S.Offer.model_fields and champ in S.OfferCreate.model_fields)

# ==========================================================================
print("\nE — RIEN N'EST FORCE : UNE OFFRE PEUT NE PAS AVOIR DE LIEU")

for type_sans_lieu in ("subscription", "pack", "membership", "product", "other"):
    _o, _c = _attrape(_creer(ADMIN, name="X", offer_type=type_sans_lieu))
    verifier("E. « %s » se cree SANS aucun lieu" % type_sans_lieu, _c is None, _c)
    verifier("E-bis. ... et sa ville reste vide, pas inventee" ,
             _o and _o.location_city == "" and _o.location_lat is None,
             _o and (_o.location_city, _o.location_lat))
_o, _c = _attrape(_creer(ADMIN, name="Cours sans adresse", offer_type="single_class"))
verifier("E-ter. meme un cours a l'unite peut rester sans lieu "
         "(l'eligibilite se decidera en R3c, pas ici)", _c is None, _c)

# ==========================================================================
print("\nG — UNE CHARGE UTILE MALFORMEE NE CASSE RIEN")

for mauvais, attendu in (
        ({"location_lat": "pas-un-nombre", "location_lng": 6.0}, None),
        ({"location_lat": 999.0, "location_lng": 6.0}, None),
        ({"location_lat": 46.0, "location_lng": -999.0}, None),
        ({"location_lat": float("nan"), "location_lng": 6.0}, None),
        ({"location_lat": 46.0, "location_lng": None}, None)):
    _o, _c = _attrape(_creer(ADMIN, name="X", **mauvais))
    verifier("G. %s -> accepte, coordonnees ecartees"
             % ", ".join("%s=%r" % kv for kv in mauvais.items()),
             _c is None and _o and _o.location_lat is None and _o.location_lng is None,
             _c or (_o and (_o.location_lat, _o.location_lng)))

_o, _c = _attrape(_creer(ADMIN, name="X", location_city="  Auvernier   ",
                         location_address="Bord   du    Lac"))
verifier("G-bis. les espaces en trop sont ecrases — sans quoi « Vidy,  Lausanne » "
         "et « Vidy, Lausanne » seraient deux lieux",
         _o and _o.location_city == "Auvernier" and _o.location_address == "Bord du Lac",
         _o and (_o.location_city, _o.location_address))
_o, _c = _attrape(_creer(ADMIN, name="X", location_city="V" * 500))
verifier("G-ter. une ville de 500 caracteres est bornee a 200",
         _o and len(_o.location_city) == 200, _o and len(_o.location_city))
verifier("G-quater. une coordonnee valide au bord des bornes passe",
         S.r3a_coordonnee(-90.0, 90.0) == -90.0 and S.r3a_coordonnee(180.0, 180.0) == 180.0)
verifier("G-quinquies. les coordonnees sont SOLIDAIRES : une seule ne situe rien",
         S.r3a_localisation({"location_lat": 46.0})["location_lat"] is None)

# ==========================================================================
print("\nH — LE LIEU N'EST PAS UNE PERSONNE")

verifier("H. aucun champ personnel n'entre dans la localisation",
         set(S.r3a_localisation({}).keys())
         == {"location_city", "location_address", "location_lat", "location_lng"},
         sorted(S.r3a_localisation({})))
for personnel in ("email", "phone", "whatsapp", "coach_id", "customer", "birthday"):
    verifier("H-bis. le socle R3a ne lit jamais « %s »" % personnel, personnel not in _code)
_o, _c = _attrape(_creer(ADMIN, name="X", location_city="Auvernier",
                         location_address="Bord du Lac"))
verifier("H-ter. et rien de ce qui est stocke ne ressemble a une adresse e-mail",
         not re.search(r"[\w.+-]+@[\w-]+\.\w+",
                       str(_o.location_city) + str(_o.location_address)))

# ==========================================================================
print("\nI — LES OFFRES HISTORIQUES : RIEN N'EST INVENTE")

# Telle qu'elle vit VRAIMENT en production : un texte libre, un jeton region
# sur ses cours, et AUCUN champ structure.
BASE.offers.docs.append({
    "id": "legacy-r3a", "name": "PULSE x10 cours", "price": 250.0,
    "coach_id": None, "visible": True,
    "location": "Bord du Lac, Auvernier, Neuchâtel",
    "linked_course_ids": ["c1"]})
BASE.courses.docs.append({"id": "c1", "name": "Silent", "region": "neuchatel",
                          "locationName": "Bord du Lac, Auvernier, Neuchâtel"})
_l = _lire("legacy-r3a")
verifier("I. l'offre historique n'a AUCUN des quatre champs",
         not any(c in _l for c in ("location_city", "location_address",
                                   "location_lat", "location_lng")))
_modele = S.Offer(**_l)
verifier("I-bis. relue par le modele, sa ville est NULLE — pas « Neuchâtel »",
         _modele.location_city is None, _modele.location_city)
verifier("I-ter. ... alors meme que son texte libre CONTIENT « Neuchâtel »",
         "Neuchâtel" in _l["location"])
verifier("I-quater. ... et que son cours lie porte `region=neuchatel`",
         BASE.courses.docs[-1]["region"] == "neuchatel")
verifier("I-5. son texte libre `location` est INTACT",
         _l.get("location") == "Bord du Lac, Auvernier, Neuchâtel")

# La porte de saisie manuelle, reservee a l'administrateur.
_r, _c = _attrape(S.r3a_enregistrer_localisation(
    "legacy-r3a", S.R3ALocalisation(location_city="Auvernier",
                                    location_address="Bord du Lac, Auvernier"),
    _Requete(ADMIN)))
verifier("I-6. l'administrateur situe l'offre a la main", _c is None, _c)
_ap = _lire("legacy-r3a")
verifier("I-7. la ville declaree est AUVERNIER, la vraie commune",
         _ap.get("location_city") == "Auvernier", _ap.get("location_city"))
verifier("I-8. RIEN D'AUTRE n'a bouge (nom, prix, visibilite, texte libre, cours)",
         all(_ap.get(k) == _l.get(k) for k in
             ("name", "price", "visible", "location", "linked_course_ids")))
_r, _c = _attrape(S.r3a_enregistrer_localisation(
    "legacy-r3a", S.R3ALocalisation(location_city="X"), _Requete(PARTENAIRE)))
verifier("I-9. un partenaire ne situe RIEN (403)", _c == 403, _c)
_r, _c = _attrape(S.r3a_enregistrer_localisation(
    "legacy-r3a", S.R3ALocalisation(location_city="X"), _Requete(None)))
verifier("I-10. un anonyme non plus (401)", _c == 401, _c)
_r, _c = _attrape(S.r3a_enregistrer_localisation(
    "fantome", S.R3ALocalisation(location_city="X"), _Requete(ADMIN)))
verifier("I-11. ni une offre inexistante (404)", _c == 404, _c)

# ==========================================================================
print("\nJ — L'API PUBLIQUE : LE LIEU OUI, LE PRIVE NON")

_toutes = asyncio.run(BASE.offers.find({}, {"_id": 0}).to_list(500))
_pub = [S.r2b_offre_publique(o) for o in _toutes]
MAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _emails(v):
    if isinstance(v, dict):
        return [e for x in v.values() for e in _emails(x)]
    if isinstance(v, (list, tuple)):
        return [e for x in v for e in _emails(x)]
    return MAIL.findall(v) if isinstance(v, str) else []


for champ in ("location_city", "location_address", "location_lat", "location_lng"):
    verifier("J. « %s » est publiable" % champ, champ in S.R2B_CLES_OFFRE_PUBLIQUE)
verifier("J-bis. aucune adresse e-mail dans les %d offres publiques" % len(_pub),
         _emails(_pub) == [])
verifier("J-ter. `coach_id` reste hors de la liste blanche",
         "coach_id" not in S.R2B_CLES_OFFRE_PUBLIQUE)
verifier("J-quater. R2c intact : proprietaire et type toujours publiables",
         {"owner_type", "owner_id", "offer_type"} <= set(S.R2B_CLES_OFFRE_PUBLIQUE))
_situee = S.r2b_offre_publique(_lire(o_a.id))
verifier("J-5. une offre situee rend bien sa ville publiquement",
         _situee.get("location_city") == "Colombier", _situee.get("location_city"))

# ==========================================================================
print("\nAUCUN DEBORDEMENT DE LOT")
_routes = _src[_src.index("class R3ALocalisation(BaseModel):"):
               _src.index("# --- Product Categories ---")]
_tout = "\n".join(re.sub(r"#.*$", "", l) for l in (_socle + _routes).splitlines())
_tout = re.sub(r'"""[\s\S]*?"""', "", _tout).lower().replace("afroboost", "")
for hors_sujet in ("boost", "stripe", "wallet", "commission", "discovery",
                   "reservation", "credit", "duo", "eligib"):
    verifier("R3a ne touche pas a « %s »" % hors_sujet,
             not re.search(r"\b%s" % hors_sujet, _tout))

_ok = sum(1 for _i, _c, _d in RESULTATS if _c)
_total = len(RESULTATS)
print("\n" + "=" * 78)
print("R3a : %d / %d verifications" % (_ok, _total))
if _ok != _total:
    print("\nECHECS :")
    for _i, _c, _d in RESULTATS:
        if not _c:
            print("  - %s%s" % (_i, (" -> " + _d) if _d else ""))
print("=" * 78)
sys.exit(0 if _ok == _total else 1)
