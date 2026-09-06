#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CONTRAT DE VISIBILITE DES OFFRES — CE QUI SORT, ET POUR QUI.

CE BANC N'APPELLE NI LA PRODUCTION NI AUCUN RESEAU. Il monte une base en
MEMOIRE et appelle les VRAIES fonctions de route : ce n'est pas du `grep`,
c'est le comportement reel qui est mesure.

LE DEFAUT QUE CE LOT FERME
==============================================================================
`GET /api/offers` faisait `db.offers.find({})` — SANS filtre. La vitrine
publique recevait donc les offres masquees (6 sur 9 en production le 06/09),
avec leur nom, leur prix, leur adresse et leur description. Le tri sur
`visible` etait fait par le NAVIGATEUR (App.js ~7582/7588).

C'est la meme faute de structure que R2b (l'e-mail du coach) : une protection
posee cote client n'en est pas une. Quiconque appelle l'API directement — ou
ecrit un adaptateur, ce que Spordateur fait justement — recoit tout.

CE QU'IL PROUVE
==============================================================================
PUBLIC
  A. une offre publiee sort
  B. une offre masquee NE sort PAS
  C. une offre sans le champ `visible` sort (ancien document = publie, c'est
     le defaut du modele et ce que le navigateur appliquait deja)
ADMINISTRATION
  D. `?scope=mine` rend TOUT a l'administrateur, masquees comprises
  E. et au coach, ses masquees a lui
  F. un anonyme qui reclame « les miennes » n'obtient toujours rien
SUPPRESSION
  G. une offre supprimee n'est nulle part — c'est un DELETE physique
CONFIDENTIALITE (R2b, non regresse)
  H. aucune adresse e-mail ne sort par la porte publique
INTEGRITE (R2c / R3a, non regresses)
  I. le filtre ne touche ni au proprietaire, ni au type, ni au lieu
"""
import asyncio
import os
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

os.environ["JWT_SECRET"] = "secret-de-test-r3b"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-r3b-inexistant:27017")
import api.server as S  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _base_memoire import _Base, _Requete, ADMIN, PARTENAIRE  # noqa: E402

BASE = _Base()
S.db = BASE


def _poser(**kw):
    """Ecrit une offre directement en base — on teste la LECTURE, pas la pose."""
    doc = {"id": kw.pop("id"), "name": kw.pop("name", "Offre"), "price": 30.0,
           "owner_type": "admin", "owner_id": None, "offer_type": "single_class",
           "coach_id": ADMIN}
    doc.update(kw)
    asyncio.get_event_loop().run_until_complete(BASE.offers.insert_one(dict(doc)))
    return doc


def _lire(scope="", email=""):
    req = _Requete(email or None)
    return asyncio.get_event_loop().run_until_complete(
        S.get_offers(req, scope=scope) if scope else S.get_offers(req))


def _noms(liste):
    return sorted((o.get("name") if isinstance(o, dict) else getattr(o, "name", ""))
                  for o in (liste or []))


asyncio.set_event_loop(asyncio.new_event_loop())

# Le catalogue de reference : deux publiees, deux masquees, une sans le champ.
_poser(id="pub-1", name="Cours a l'unite", visible=True)
_poser(id="pub-2", name="Cours d'essai", visible=True, price=0.0)
_poser(id="cache-1", name="SILENT LAKESIDE", visible=False, offer_type="event",
       location_city="St-Blaise")
_poser(id="cache-2", name="Membres", visible=False, offer_type="pack", price=150.0)
_poser(id="ancienne", name="Offre sans le champ")          # pas de `visible`
_poser(id="part-1", name="Offre du partenaire", visible=False,
       owner_type="partner", owner_id="uuid-partenaire", coach_id=PARTENAIRE)

print("=" * 78)
print("CONTRAT DE VISIBILITE DES OFFRES")
print("=" * 78)

# ---------------------------------------------------------------- 1. PUBLIC
print("\n1. LA PORTE PUBLIQUE NE REND QUE CE QUI EST PUBLIE")
_public = _noms(_lire())

verifier("A. une offre publiee sort",
         "Cours a l'unite" in _public and "Cours d'essai" in _public, _public)
verifier("B. une offre masquee NE sort PAS",
         "SILENT LAKESIDE" not in _public and "Membres" not in _public, _public)
verifier("B-bis. celle d'un partenaire masquee non plus",
         "Offre du partenaire" not in _public, _public)
verifier("C. une offre SANS le champ `visible` sort — ancien document = publie",
         # Le modele a `visible: bool = True` et le navigateur testait
         # `o.visible !== false`. Traiter l'absence comme « masque » ferait
         # disparaitre d'un coup les offres anterieures au champ.
         "Offre sans le champ" in _public, _public)
verifier("D. le compte est exact : 3 publiees sur 6 en base",
         len(_public) == 3, "%d rendues : %s" % (len(_public), _public))

# ------------------------------------------------------- 2. ADMINISTRATION
print("\n2. L'ADMINISTRATION CONTINUE DE TOUT VOIR")
_admin = _noms(_lire(scope="mine", email=ADMIN))

verifier("E. `scope=mine` rend TOUT a l'administrateur",
         len(_admin) == 6, "%d rendues : %s" % (len(_admin), _admin))
verifier("F. y compris les masquees — sinon il ne pourrait plus les republier",
         "SILENT LAKESIDE" in _admin and "Membres" in _admin, _admin)

_coach = _noms(_lire(scope="mine", email=PARTENAIRE))
verifier("G. le coach voit SA masquee",
         _coach == ["Offre du partenaire"], _coach)
verifier("H. et rien de l'administrateur",
         "Cours a l'unite" not in _coach, _coach)

_anon = _lire(scope="mine")
verifier("I. un anonyme qui reclame « les miennes » n'obtient rien",
         _anon == [], _anon)

# ---------------------------------------------------------- 3. SUPPRESSION
print("\n3. UNE OFFRE SUPPRIMEE N'EST NULLE PART")
# On passe par la VRAIE route de suppression — pas par la base directement :
# c'est son comportement (un DELETE physique) qu'on veut prouver.
asyncio.get_event_loop().run_until_complete(
    S.delete_offer("pub-2", _Requete(ADMIN)))
_apres = _noms(_lire())
_apres_admin = _noms(_lire(scope="mine", email=ADMIN))

verifier("J. absente du public — le DELETE est physique, rien a filtrer",
         "Cours d'essai" not in _apres, _apres)
verifier("K. absente de l'administration aussi",
         "Cours d'essai" not in _apres_admin, _apres_admin)
verifier("L. et le reste du catalogue est intact",
         len(_apres) == 2 and len(_apres_admin) == 5,
         "%d / %d" % (len(_apres), len(_apres_admin)))

# ------------------------------------------------------ 4. CONFIDENTIALITE
print("\n4. R2b — AUCUNE DONNEE PRIVEE PAR LA PORTE PUBLIQUE")
_brut = _lire()


def _valeurs(objet):
    d = objet if isinstance(objet, dict) else getattr(objet, "__dict__", {})
    return d


_fuite = []
for _o in _brut:
    for _cle, _val in _valeurs(_o).items():
        if isinstance(_val, str) and "@" in _val and "." in _val.split("@")[-1]:
            _fuite.append((_cle, _val))

verifier("M. aucune adresse e-mail dans la reponse publique",
         _fuite == [], _fuite)
verifier("N. `coach_id` n'est pas rendu publiquement",
         all("coach_id" not in _valeurs(o) or not _valeurs(o).get("coach_id")
             for o in _brut),
         [_valeurs(o).get("coach_id") for o in _brut])

# ------------------------------------------------------------ 5. INTEGRITE
print("\n5. R2c ET R3a NE SONT PAS TOUCHES")
_admin_docs = _lire(scope="mine", email=ADMIN)


def _par_nom(liste, nom):
    for o in liste:
        if _valeurs(o).get("name") == nom:
            return _valeurs(o)
    return {}


_lakeside = _par_nom(_admin_docs, "SILENT LAKESIDE")
verifier("O. le proprietaire d'une offre masquee est intact",
         _lakeside.get("owner_type") == "admin", _lakeside.get("owner_type"))
verifier("P. son type aussi",
         _lakeside.get("offer_type") == "event", _lakeside.get("offer_type"))
verifier("Q. et sa ville — filtrer une lecture n'ecrit rien",
         _lakeside.get("location_city") == "St-Blaise",
         _lakeside.get("location_city"))
verifier("R. le filtre n'a rien SUPPRIME : 5 documents restent en base",
         len(BASE.offers.docs) == 5, len(BASE.offers.docs))

# ============================================================================
_ok = sum(1 for _i, _c, _d in RESULTATS if _c)
_total = len(RESULTATS)
print("\n" + "=" * 78)
print("CONTRAT DE VISIBILITE : %d / %d verifications" % (_ok, _total))
print("Sorties reseau tentees : 0 — le resolveur DNS est bloque")
print("Ecritures en production : 0 — base en memoire")
print("=" * 78)
if _ok != _total:
    print("\nECHECS :")
    for _i, _c, _d in RESULTATS:
        if not _c:
            print("  - %s%s" % (_i, (" -> " + _d) if _d else ""))
sys.exit(0 if _ok == _total else 1)
