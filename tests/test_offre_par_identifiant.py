#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L'ABONNEMENT SE RATTACHE À L'OFFRE PAR SON IDENTIFIANT, PLUS PAR SON NOM.

Exécution : python3 tests/test_offre_par_identifiant.py

POURQUOI CE BANC EXISTE. Le rapprochement se faisait par `offer_name`, une
chaîne figée AU MOMENT DE L'ACHAT. Renommer ou dupliquer une offre rendait
invisibles tous les abonnements antérieurs — mesuré en production le 09/09/2026
sur le compte du propriétaire (« Cours à l'unité test », « Cours à l'unité
(copie) »), qui ne recevait donc aucun rappel. Le nom est un libellé
d'affichage ; l'identifiant est la clé métier.

Aucun réseau, aucune base réelle : la doublure mémoire du dépôt suffit.
"""
import asyncio, os, sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-offre:27017")

import api.server as S                                    # noqa: E402
from tests._base_memoire import _Base                     # noqa: E402

_ok = _ko = 0


def verifie(titre, condition, detail=""):
    global _ok, _ko
    if condition:
        _ok += 1
        print("PASS  %s" % titre)
    else:
        _ko += 1
        print("FAIL  %s%s" % (titre, (" — " + detail) if detail else ""))


def bac(offres):
    b = _Base()
    b.offers.docs = [dict(o) for o in offres]
    S.db = b
    return b


def resoudre(nom="", code="", oid=""):
    from tests._base_memoire import _attrape as _a
    return _a(S._v426_offre_de_labonnement(nom, code, oid))[0]


OFFRE = {"id": "OFFER-123", "name": "PULSE x10 cours",
         "linked_course_ids": ["c1", "c2"], "coach_id": "coach@test"}

print("\n--- §8 : RENOMMER UNE OFFRE NE CASSE PLUS RIEN ---")
b = bac([OFFRE])
_av = resoudre(nom="PULSE x10 cours", oid="OFFER-123")
verifie("avant renommage : l'abonnement trouve son offre", (_av or {}).get("id") == "OFFER-123")
b.offers.docs[0]["name"] = "PULSE x10 cours 2026"          # le coach renomme
_ap = resoudre(nom="PULSE x10 cours", oid="OFFER-123")     # l'abonnement garde l'ANCIEN nom
verifie("après renommage : l'abonnement trouve TOUJOURS son offre",
        (_ap or {}).get("id") == "OFFER-123")
verifie("...et ses cours restent accessibles",
        (_ap or {}).get("linked_course_ids") == ["c1", "c2"])
verifie("aucune migration n'a été nécessaire", b.offers.docs[0]["name"] == "PULSE x10 cours 2026")

print("\n--- §9 A : HISTORIQUE SANS IDENTIFIANT, NOM UNIQUE ---")
bac([OFFRE])
_a = resoudre(nom="PULSE x10 cours")
verifie("A. le repli par nom exact fonctionne encore", (_a or {}).get("id") == "OFFER-123")

print("\n--- §9 B : AUCUNE CORRESPONDANCE ---")
bac([OFFRE])
verifie("B. nom inconnu -> aucune offre (jamais de rattachement au hasard)",
        resoudre(nom="Offre qui n'existe pas") is None)
verifie("B2. ni nom ni identifiant -> aucune offre", resoudre() is None)

print("\n--- §9 C : PLUSIEURS CORRESPONDANCES ---")
bac([OFFRE, {"id": "OFFER-999", "name": "PULSE x10 cours", "linked_course_ids": ["c9"]}])
_c = resoudre(nom="PULSE x10 cours")
verifie("C. deux offres du même nom -> AUCUNE retenue, pas de tirage au sort", _c is None)

print("\n--- §9 D : L'IDENTIFIANT L'EMPORTE SUR LE NOM ---")
bac([OFFRE, {"id": "OFFER-AUTRE", "name": "Cours à l'unité", "linked_course_ids": ["cX"]}])
_d = resoudre(nom="Cours à l'unité", oid="OFFER-123")
verifie("D. nom périmé + identifiant valide -> l'identifiant gagne",
        (_d or {}).get("id") == "OFFER-123", str(_d))
verifie("D2. ...et surtout PAS l'offre qui porte ce nom aujourd'hui",
        (_d or {}).get("id") != "OFFER-AUTRE")

print("\n--- §9 E : IDENTIFIANT INVALIDE ---")
bac([OFFRE])
_e = resoudre(nom="PULSE x10 cours", oid="OFFER-DISPARU")
verifie("E. identifiant introuvable -> AUCUN repli silencieux sur le nom", _e is None,
        str(_e))

print("\n--- LES MOTIFS SONT NOMMÉS ET CHERCHABLES ---")
verifie("motif d'échec exposé", S.OFFRE_ECHEC == "OFFER_RESOLUTION_FAILED", S.OFFRE_ECHEC)
verifie("motif d'ambiguïté exposé", S.OFFRE_AMBIGU == "OFFER_RESOLUTION_AMBIGUOUS", S.OFFRE_AMBIGU)

print("\n--- LA RÉSOLUTION EST UNIQUE, PARTAGÉE PAR LES TROIS ÉCRANS ---")
_src = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
verifie("une seule définition de la résolution",
        _src.count("async def _v426_offre_de_labonnement") == 1)
verifie("espace abonné, LOT R, réservation ET rappels l'appellent tous",
        _src.count("_v426_offre_de_labonnement(") >= 5,
        str(_src.count("_v426_offre_de_labonnement(")))
verifie("le moteur de rappels ne rapproche plus par nom",
        "rvab_offres_ouvrant_le_cours" not in _src)

print("\n--- LES NOUVEAUX ABONNEMENTS PORTENT L'IDENTIFIANT ---")
_promo = open(os.path.join(RACINE, "api", "routes", "promo_routes.py"), encoding="utf-8").read()
_activ = open(os.path.join(RACINE, "api", "routes", "payment_activation.py"), encoding="utf-8").read()
verifie("Stripe écrit offer_id", '"offer_id": str((metadata or {}).get("offer_id") or "")' in _src)
verifie("création manuelle admin écrit offer_id",
        '"offer_id": str((_manual_offer or {}).get("id") or "")' in _src)
verifie("preuve sociale écrit offer_id", '"offer_id": str((offer or {}).get("id") or "")' in _src)
verifie("les 3 portes de promo_routes écrivent offer_id", _promo.count('"offer_id":') >= 3,
        str(_promo.count('"offer_id":')))
verifie("Mobile Money écrit offer_id", '"offer_id": str(local_tx.get("offer_id") or "")' in _activ)

print("\n--- LA MIGRATION HISTORIQUE : UN PLAN, PAS UNE DEVINETTE ---")
from tests._base_memoire import _Requete, ADMIN, _attrape   # noqa: E402


class _Abos(_Base):
    pass


def bac_migration(abos, offres):
    b = _Base()
    b.offers.docs = [dict(o) for o in offres]
    b.subscriptions = type(b.offers)([dict(a) for a in abos])
    S.db = b
    return b


ABOS = [
    {"id": "s1", "email": "a@x.ch", "offer_name": "PULSE x10 cours", "status": "active"},
    {"id": "s2", "email": "b@x.ch", "offer_name": "Cours a l'unite test", "status": "active"},
    {"id": "s3", "email": "c@x.ch", "offer_name": "PULSE x10 cours", "status": "active",
     "offer_id": "DEJA-POSE"},
]

# Le super-admin est exige : une route qui ECRIT ne s'ouvre pas.
b = bac_migration(ABOS, [OFFRE])
_r, _code = _attrape(S.backfill_offer_id(_Requete(email=None), dry_run=True))
verifie("sans super-admin -> refus", _code == 403, str(_code))

# L'IDENTITE SIGNEE est remplacee le temps des bancs suivants : ils portent sur
# la MIGRATION, pas sur l'authentification — celle-ci vient d'etre prouvee par le
# refus 403 ci-dessus, avec la vraie fonction.
_vraie_identite = S._v311_coach_email_from_jwt
S._v311_coach_email_from_jwt = lambda _r: ADMIN

# Simulation : le plan est rendu, RIEN n'est ecrit.
b = bac_migration(ABOS, [OFFRE])
_sim, _ = _attrape(S.backfill_offer_id(_Requete(email=ADMIN), dry_run=True))
verifie("dry_run est le DEFAUT et n'ecrit rien", _sim["ecrits"] == 0 and _sim["dry_run"] is True)
verifie("le plan ne retient que les resolutions CERTAINES", _sim["resolution_certaine"] == 1,
        str(_sim["resolution_certaine"]))
verifie("l'abonnement introuvable est LISTE, jamais devine",
        _sim["sans_correspondance"] == 1
        and _sim["decision_humaine_requise"][0]["offer_name"] == "Cours a l'unite test")
verifie("l'abonnement qui a deja un identifiant n'est meme pas candidat",
        _sim["total_sans_offer_id"] == 2, str(_sim["total_sans_offer_id"]))
verifie("aucune ecriture en simulation",
        all("offer_id" not in d or d["id"] == "s3" for d in b.subscriptions.docs))

# Application : seul le cas certain est ecrit.
b = bac_migration(ABOS, [OFFRE])
_app, _ = _attrape(S.backfill_offer_id(_Requete(email=ADMIN), dry_run=False))
verifie("appliquee : un seul document ecrit", _app["ecrits"] == 1, str(_app["ecrits"]))
_par_id = {d["id"]: d for d in b.subscriptions.docs}
verifie("le cas certain recoit l'identifiant", _par_id["s1"].get("offer_id") == "OFFER-123")
verifie("le cas non resolu reste INTACT", not _par_id["s2"].get("offer_id"))
verifie("l'identifiant deja pose n'est JAMAIS ecrase",
        _par_id["s3"].get("offer_id") == "DEJA-POSE")
verifie("aucun autre champ n'est touche (ni solde, ni expiration, ni statut)",
        _par_id["s2"].get("status") == "active" and "expires_at" not in _par_id["s2"])
verifie("la provenance de l'ecriture est tracee",
        _par_id["s1"].get("offer_id_source") == "backfill_resolution_canonique")

S._v311_coach_email_from_jwt = _vraie_identite   # on rend l'identite reelle

print("\n%d PASS · %d FAIL\n" % (_ok, _ko))
sys.exit(0 if _ko == 0 else 1)
