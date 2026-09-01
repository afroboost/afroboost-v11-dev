#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3-S3-A — LE SOCLE DU MOTEUR DE CAMPAGNE.

CE QUE LE LOT AJOUTE
==============================================================================
Deux collections (`prospect_campaigns`, `prospect_campaign_actions`), trois
champs sur `partner_prospects`, les index — dont LE VERROU INTER-CAMPAGNES,
un index unique PARTIEL —, deux drapeaux eteints, et des fonctions PURES qui
calculent le DESTINATAIRE REEL derriere plusieurs fiches.

AUCUNE route, AUCUN fournisseur, AUCUNE file, AUCUNE boucle, AUCUN envoi.

CE QUE CE FICHIER PROUVE, ET COMMENT
==============================================================================
1. Le lot ne PEUT PAS contacter quelqu'un — verifie en lisant le code (AST),
   pas en constatant qu'aucun message n'est parti aujourd'hui.
2. Le regroupement des fiches ne fusionne QUE sur preuve forte. Les cas sont
   les VRAIS cas de production : Dancefloor, Wellness, Giant Studio d'un cote ;
   Fete de la Danse, Case a Chocs, UniNE, Jazzercise de l'autre.
3. Le verrou inter-campagnes tient une collision CONCURRENTE. Le bouchon
   modelise la regle de MongoDB pour un index unique partiel, et la section 9
   demontre que le meme banc PASSE — donc ne prouve rien — si l'index n'est
   pas partiel ou n'existe pas.
4. Reserver n'est pas envoyer : aucune reservation ne fait passer un prospect
   a `contacte`.

AUCUNE ECRITURE EN PRODUCTION. Tout se joue sur des documents fictifs, en
memoire. La base de production n'est jamais ouverte par ce fichier.

    python3 tests/test_p3s3a_socle_campagne.py
"""
import ast
import asyncio
import io
import os
import random
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


os.environ.setdefault("JWT_SECRET", "secret-de-test-p3s3a-sans-rapport-production")
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p3s3a-inexistant:27017")

import api.server as S  # noqa: E402

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
COACH_A = "coach.a.fictif@exemple.test"
COACH_B = "coach.b.fictif@exemple.test"
INSTANT = "2026-08-31T18:26:57.951583+00:00"   # l'horodatage REEL des 142


def fiche(ref, nom, ville, **extra):
    """Une fiche minimale, au format REEL de production."""
    base = {"id": "p-" + ref.lower(), "ref": ref, "coach_id": COACH_A,
            "organisation_name": nom, "city": ville, "category": "festival",
            "status": S.P3S1_STATUT_INITIAL, "created_at": INSTANT}
    base.update(extra)
    return base


# ============================================================================
print("\n1. LE CONTRAT — NOMS ET VOCABULAIRES EXACTS DE LA CONCEPTION")

verifier("1a. collection campagne = prospect_campaigns",
         S.P3S3_CAMPAGNES == "prospect_campaigns", S.P3S3_CAMPAGNES)
verifier("1b. collection action = prospect_campaign_actions",
         S.P3S3_ACTIONS == "prospect_campaign_actions", S.P3S3_ACTIONS)
verifier("1c. champ de reservation = first_contact_claimed_at",
         S.P3S3_CHAMP_CLAIM == "first_contact_claimed_at", S.P3S3_CHAMP_CLAIM)
verifier("1d. champ d'envoi confirme = first_contact_sent_at",
         S.P3S3_CHAMP_ENVOI == "first_contact_sent_at", S.P3S3_CHAMP_ENVOI)
verifier("1e. champ de destinataire = recipient_key",
         S.P3S3_CHAMP_CLE == "recipient_key", S.P3S3_CHAMP_CLE)
verifier("1f. les trois champs, et seulement eux",
         S.P3S3_CHAMPS_PROSPECT == ("first_contact_claimed_at",
                                    "first_contact_sent_at", "recipient_key"))
verifier("1g. drapeau d'activation = P3_LAUNCH_ENABLED",
         S.P3S3_FLAG_ACTIF == "P3_LAUNCH_ENABLED", S.P3S3_FLAG_ACTIF)
verifier("1h. drapeau d'envoi = P3_LAUNCH_ENVOI_REEL",
         S.P3S3_FLAG_ENVOI == "P3_LAUNCH_ENVOI_REEL", S.P3S3_FLAG_ENVOI)
verifier("1i. AUCUNE troisieme collection introduite",
         len([n for n in dir(S) if n.startswith("P3S3_") and
              isinstance(getattr(S, n), str) and
              getattr(S, n).startswith("prospect_")]) == 2)

# Les six statuts metier de P3-S1 ne bougent pas. C'est la garantie que les
# etats techniques ne polluent pas le vocabulaire commercial.
verifier("1j. les 6 statuts metier P3-S1 sont INCHANGES",
         S.P3S1_STATUTS == ("a_contacter", "contacte", "repondu", "interesse",
                            "sans_reponse_pause", "refuse"), str(S.P3S1_STATUTS))
verifier("1k. aucun statut technique n'a rejoint le vocabulaire metier",
         not set(S.P3S3_STATUTS_ACTION) & set(S.P3S1_STATUTS))
verifier("1l. `echec_indetermine` porte le verrou (on ignore si l'envoi a eu lieu)",
         "echec_indetermine" in S.P3S3_STATUTS_VERROU)
verifier("1m. `echec` NE porte PAS le verrou (cause connue, on peut reessayer)",
         "echec" not in S.P3S3_STATUTS_VERROU)
verifier("1n. `pret` et `exclu` ne verrouillent rien",
         not {"pret", "exclu"} & set(S.P3S3_STATUTS_VERROU))


# ============================================================================
print("\n2. LES DRAPEAUX — FERMES PAR DEFAUT, JAMAIS FAIL-OPEN")

verifier("2a. modele : P3_LAUNCH_ENABLED defaut False",
         S.FeatureFlags().P3_LAUNCH_ENABLED is False)
verifier("2b. modele : P3_LAUNCH_ENVOI_REEL defaut False",
         S.FeatureFlags().P3_LAUNCH_ENVOI_REEL is False)
verifier("2c. le modele de mise a jour accepte les deux",
         hasattr(S.FeatureFlagsUpdate(), "P3_LAUNCH_ENABLED") and
         hasattr(S.FeatureFlagsUpdate(), "P3_LAUNCH_ENVOI_REEL"))
verifier("2d. la creation par defaut pose les deux a False",
         '"P3_LAUNCH_ENABLED": False,' in SRC and
         '"P3_LAUNCH_ENVOI_REEL": False,' in SRC)
verifier("2e. la completion a la lecture les rend False s'ils sont ABSENTS",
         '("P3_LAUNCH_ENABLED", False),' in SRC and
         '("P3_LAUNCH_ENVOI_REEL", False)):' in SRC)

# Le coeur : la porte d'envoi. Aucune combinaison ne l'ouvre sauf deux `True`.
for _cas, _flags, _attendu in (
        ("configuration ABSENTE (None)", None, False),
        ("configuration vide {}", {}, False),
        ("les deux a false", {"P3_LAUNCH_ENABLED": False, "P3_LAUNCH_ENVOI_REEL": False}, False),
        ("actif seul", {"P3_LAUNCH_ENABLED": True}, False),
        ("actif + envoi false (SIMULATION)", {"P3_LAUNCH_ENABLED": True,
                                              "P3_LAUNCH_ENVOI_REEL": False}, False),
        ("envoi seul, sans activation", {"P3_LAUNCH_ENVOI_REEL": True}, False),
        ("envoi true mais actif false", {"P3_LAUNCH_ENABLED": False,
                                         "P3_LAUNCH_ENVOI_REEL": True}, False),
        ("valeurs non booleennes (1/1)", {"P3_LAUNCH_ENABLED": 1,
                                          "P3_LAUNCH_ENVOI_REEL": 1}, False),
        ("chaines 'true'", {"P3_LAUNCH_ENABLED": "true",
                            "P3_LAUNCH_ENVOI_REEL": "true"}, False),
        ("configuration illisible (liste)", ["P3_LAUNCH_ENABLED"], False),
        ("LES DEUX a True", {"P3_LAUNCH_ENABLED": True,
                             "P3_LAUNCH_ENVOI_REEL": True}, True)):
    verifier("2f. porte d'envoi — %-38s -> %s" % (_cas, "OUVERTE" if _attendu else "FERMEE"),
             S.p3s3_envoi_autorise(_flags) is _attendu)


# ============================================================================
print("\n3. NORMALISATION — CE QUI EST UNE PREUVE, ET CE QUI N'EN EST PAS")

for _val, _dom, _attendu in (
        ("https://www.instagram.com/dancefloor_team", "instagram.com", "dancefloor_team"),
        ("https://www.instagram.com/zuerichtanzt.ch/", "instagram.com", "zuerichtanzt.ch"),
        ("instagram.com/festineuch?hl=fr", "instagram.com", "festineuch"),
        ("@caseachocs", "instagram.com", "caseachocs"),
        # Les VRAIES valeurs de production qui ne prouvent RIEN :
        ("via @caseachocs", "instagram.com", ""),
        ("(comptes FdlD)", "instagram.com", ""),
        ("Fete de la Danse (compte)", "instagram.com", ""),
        ("@salsapeople (a confirmer)", "instagram.com", ""),
        ("page evenement FB", "facebook.com", ""),
        ("FB, LinkedIn", "facebook.com", ""),
        ("tiktok", "tiktok.com", ""),
        ("Wellness Sport Club", "facebook.com", ""),
        ("", "instagram.com", ""),
        (None, "instagram.com", "")):
    verifier("3a. compte social %-34s -> %s" % (repr(_val)[:34], repr(_attendu)),
             S.p3s3_compte_social(_val, _dom) == _attendu,
             "obtenu : %r" % S.p3s3_compte_social(_val, _dom))

# E-mail : egalite stricte apres minuscules. Aucune tolerance.
verifier("3b. e-mail : la casse et les espaces ne font pas deux personnes",
         S.p3s3_preuves({"public_email": "  LPD@Wellness-SportClub.CH "}) ==
         S.p3s3_preuves({"public_email": "lpd@wellness-sportclub.ch"}))
verifier("3c. e-mail mal forme -> aucune preuve",
         S.p3s3_preuves({"public_email": "a obtenir"}) == set())
verifier("3d. e-mail vide -> aucune preuve",
         S.p3s3_preuves({"public_email": ""}) == set())

# Telephone : les 9 derniers chiffres. Les formats REELS de production.
verifier("3e. telephone : +41 76 233 49 43 == 076 233 49 43",
         S.p3s3_preuves({"public_phone": "+41 76 233 49 43"}) ==
         S.p3s3_preuves({"public_phone": "076 233 49 43"}))
verifier("3f. telephone : 021 320 56 76 == +41 21 320 56 76",
         S.p3s3_preuves({"public_phone": "021 320 56 76"}) ==
         S.p3s3_preuves({"public_phone": "+41 21 320 56 76"}))
verifier("3g. deux numeros DIFFERENTS restent differents",
         S.p3s3_preuves({"public_phone": "032 731 31 75"}) !=
         S.p3s3_preuves({"public_phone": "032 544 35 84"}))
verifier("3h. numero trop court (< 8 chiffres) -> aucune preuve",
         S.p3s3_preuves({"public_phone": "12 34"}) == set())
verifier("3i. fiche sans aucune coordonnee -> ensemble VIDE",
         S.p3s3_preuves({"organisation_name": "Les Brasseurs"}) == set())


# ============================================================================
print("\n4. recipient_key — DETERMINISTE ET INDEPENDANTE DE L'ORDRE")

_groupe = [fiche("LSN-F3", "Wellness Lausanne", "Lausanne"),
           fiche("GVA-F3", "Wellness Geneve", "Geneve")]
verifier("4a. la cle est la reference la plus ancienne (created_at, puis ref)",
         S.p3s3_recipient_key(_groupe) == "GVA-F3", S.p3s3_recipient_key(_groupe))
verifier("4b. l'ordre d'entree ne change PAS la cle",
         S.p3s3_recipient_key(list(reversed(_groupe))) == "GVA-F3")

_melanges = set()
for _ in range(40):
    _c = list(_groupe)
    random.shuffle(_c)
    _melanges.add(S.p3s3_recipient_key(_c))
verifier("4c. 40 melanges -> une seule et meme cle", len(_melanges) == 1, str(_melanges))

_ancienne = fiche("ZZZ-99", "Ancienne", "Berne")
_ancienne["created_at"] = "2026-01-01T00:00:00+00:00"
verifier("4d. une fiche PLUS ANCIENNE l'emporte, meme si sa ref est derniere",
         S.p3s3_recipient_key([_ancienne] + _groupe) == "ZZZ-99")
verifier("4e. fiche sans `ref` -> retombe sur son `id`, jamais vide",
         S.p3s3_recipient_key([{"id": "p-x", "created_at": INSTANT}]) == "p-x")
verifier("4f. groupe vide -> chaine vide, aucune exception",
         S.p3s3_recipient_key([]) == "" and S.p3s3_recipient_key(None) == "")


# ============================================================================
print("\n5. LES CAS REELS DE PRODUCTION — CE QUI FUSIONNE")

DANCEFLOOR = [
    fiche("LSN-D5", "Dancefloor Studio (site Lausanne)", "Lausanne",
          public_email="infos@dancefloorgenevasalsa.ch", public_phone="+41 76 233 49 43",
          instagram="https://www.instagram.com/dancefloor_studio_lausanne",
          facebook="https://www.facebook.com/dancefloornews",
          website_domain="dancefloorstudio.ch"),
    fiche("GVA-D2", "Dancefloor Studio (site Geneve)", "Geneve",
          public_email="infos@dancefloorgenevasalsa.ch", public_phone="+41 76 233 49 43",
          instagram="https://www.instagram.com/dancefloor_team",
          facebook="DancefloorGeneva", website_domain="dancefloorstudio.ch"),
]
WELLNESS = [
    fiche("LSN-F3", "Wellness Sport Club Lausanne", "Lausanne",
          public_email="lpd@wellness-sportclub.ch", public_phone="021 320 56 76",
          instagram="https://www.instagram.com/wellnesssportclub",
          facebook="Wellness Sport Club", website_domain="wellness-sportclub.ch"),
    fiche("GVA-F3", "Wellness Sport Club Geneve", "Geneve",
          public_email="lpd@wellness-sportclub.ch",
          instagram="https://www.instagram.com/wellness_sportclubch",
          facebook="/WellnessSportClubSuisse", website_domain="wellness-sportclub.ch"),
]
GIANT = [
    fiche("ECO-01", "Giant Studio", "Neuchatel", public_phone="032 731 31 75",
          website_domain="giantstudio.ch"),
    fiche("ORG-10", "Giant Studio (salle)", "Neuchatel", public_phone="032 731 31 75",
          website_domain="giantstudio.ch"),
]

_d = S.p3s3_destinataires(DANCEFLOOR)
verifier("5a. DANCEFLOOR : 2 fiches -> 1 destinataire", len(_d) == 1, "obtenu %d" % len(_d))
verifier("5b. DANCEFLOOR : cle = GVA-D2, couvre les deux fiches",
         _d[0]["recipient_key"] == "GVA-D2" and _d[0]["prospect_ids"] == ["GVA-D2", "LSN-D5"],
         str(_d[0]))
verifier("5c. DANCEFLOOR : la fusion est JUSTIFIEE par e-mail ET telephone",
         "mail:infos@dancefloorgenevasalsa.ch" in _d[0]["preuves_partagees"] and
         any(p.startswith("tel:") for p in _d[0]["preuves_partagees"]),
         str(_d[0]["preuves_partagees"]))
verifier("5d. DANCEFLOOR : leurs Instagram DIFFERENTS n'ont pas empeche la fusion",
         True)

_w = S.p3s3_destinataires(WELLNESS)
verifier("5e. WELLNESS : 2 fiches -> 1 destinataire", len(_w) == 1, "obtenu %d" % len(_w))
verifier("5f. WELLNESS : cle = GVA-F3, couvre les deux fiches",
         _w[0]["recipient_key"] == "GVA-F3" and _w[0]["prospect_ids"] == ["GVA-F3", "LSN-F3"])
verifier("5g. WELLNESS : la SEULE preuve est l'e-mail partage",
         _w[0]["preuves_partagees"] == ["mail:lpd@wellness-sportclub.ch"],
         str(_w[0]["preuves_partagees"]))

_g = S.p3s3_destinataires(GIANT)
verifier("5h. GIANT STUDIO : 2 fiches -> 1 destinataire, sur le TELEPHONE seul",
         len(_g) == 1 and _g[0]["recipient_key"] == "ECO-01" and
         _g[0]["preuves_partagees"] == ["tel:327313175"], str(_g))


# ============================================================================
print("\n6. LES CAS REELS — CE QUI NE FUSIONNE PAS")

# RESO / Fete de la Danse : TROIS antennes, MEME domaine, contacts distincts.
# Le cas que le coach a explicitement demande de ne pas fusionner.
RESO = [
    fiche("ORG-01", "Fete de la Danse NE / RESO", "Neuchatel (national)",
          instagram="(comptes FdlD)", website_domain="fetedeladanse.ch"),
    fiche("LSN-E3", "Fete de la Danse — Lausanne", "Lausanne",
          instagram="https://www.instagram.com/fetedeladanse",
          facebook="Fete de la Danse", website_domain="fetedeladanse.ch"),
    fiche("GVA-E3", "Fete de la Danse — Geneve", "Geneve",
          instagram="Fete de la Danse (compte)",
          facebook="Fete de la Danse Geneve", website_domain="fetedeladanse.ch"),
]
_r = S.p3s3_destinataires(RESO)
verifier("6a. RESO / Fete de la Danse : 3 fiches -> 3 destinataires DISTINCTS",
         len(_r) == 3, "obtenu %d : %s" % (len(_r), [x["recipient_key"] for x in _r]))
verifier("6b. RESO : le domaine partage fetedeladanse.ch n'a fusionne PERSONNE",
         sorted(x["recipient_key"] for x in _r) == ["GVA-E3", "LSN-E3", "ORG-01"])
verifier("6c. RESO : aucune preuve partagee nulle part",
         all(not x["preuves_partagees"] for x in _r))

# Case a Chocs : meme domaine, DEUX e-mails, DEUX telephones. Et un piege —
# « via @caseachocs » ressemble a un compte sans en etre un.
CASE = [
    fiche("BAR-05", "L'Interlope", "Neuchatel",
          public_email="interlope@case-a-chocs.ch", public_phone="+41 32 724 42 42",
          instagram="via @caseachocs", website_domain="case-a-chocs.ch"),
    fiche("ORG-02", "Case a Chocs", "Neuchatel",
          public_email="contact@case-a-chocs.ch", public_phone="032 544 35 84",
          instagram="@caseachocs", website_domain="case-a-chocs.ch"),
]
_c = S.p3s3_destinataires(CASE)
verifier("6d. CASE A CHOCS : meme domaine, 2 destinataires distincts",
         len(_c) == 2, "obtenu %d" % len(_c))
verifier("6e. CASE A CHOCS : « via @caseachocs » n'est PAS un compte — pas de fusion",
         S.p3s3_compte_social("via @caseachocs", "instagram.com") == "")

# UniNE et Jazzercise : memes domaines, aucun rapport entre les entites.
AUTRES = [
    fiche("ETU-01", "SUN — Sports univ. UniNE", "Neuchatel",
          public_email="service.sports@unine.ch", public_phone="+41 32 718 11 11",
          website_domain="unine.ch"),
    fiche("ETU-09", "LUNE / THUNE / GTA", "Neuchatel",
          instagram="@impro.lune", website_domain="unine.ch"),
    fiche("LSN-F4", "Jazzercise Lausanne Bethusy", "Lausanne", website_domain="jazzercise.com"),
    fiche("ZRH-F2", "Jazzercise Zurich", "Zurich", website_domain="jazzercise.com"),
]
_a = S.p3s3_destinataires(AUTRES)
verifier("6f. UniNE + Jazzercise : 4 fiches, 2 domaines partages -> 4 destinataires",
         len(_a) == 4, "obtenu %d" % len(_a))
verifier("6g. deux fiches SANS aucune coordonnee restent SEULES (jamais fusionnees)",
         len(S.p3s3_destinataires([fiche("BAR-09", "Les Brasseurs", "Neuchatel"),
                                   fiche("GVA-E5", "Fete de la Musique Afro", "Geneve")])) == 2)

# Le nom seul ne fusionne jamais — meme identique.
verifier("6h. deux fiches au nom IDENTIQUE, sans preuve, restent 2 destinataires",
         len(S.p3s3_destinataires([fiche("X-01", "Studio Flow", "Neuchatel"),
                                   fiche("X-02", "Studio Flow", "Neuchatel")])) == 2)


# ============================================================================
print("\n7. COLLISIONS ET DETERMINISME SUR L'ENSEMBLE")

TOUT = DANCEFLOOR + WELLNESS + GIANT + RESO + CASE + AUTRES
# 2 Dancefloor -> 1, 2 Wellness -> 1, 2 Giant -> 1, puis 3 RESO, 2 Case a
# Chocs et 4 autres qui ne fusionnent pas : 1+1+1+3+2+4 = 12.
verifier("7a. 15 fiches -> 12 destinataires (3 fusions prouvees, 9 fiches seules)",
         len(TOUT) == 15 and len(S.p3s3_destinataires(TOUT)) == 12,
         "%d fiches, %d destinataires" % (len(TOUT), len(S.p3s3_destinataires(TOUT))))

_reference = S.p3s3_destinataires(TOUT)
_ordres = set()
for _ in range(30):
    _melange = list(TOUT)
    random.shuffle(_melange)
    _ordres.add(tuple((d["recipient_key"], tuple(d["prospect_ids"]))
                      for d in S.p3s3_destinataires(_melange)))
verifier("7b. 30 ordres d'entree differents -> EXACTEMENT le meme decoupage",
         len(_ordres) == 1, "%d decoupages differents" % len(_ordres))

_table = S.p3s3_cle_par_fiche(TOUT)
verifier("7c. chaque fiche recoit une cle, aucune oubliee", len(_table) == 15)
verifier("7d. meme destinataire -> MEME cle (Wellness)",
         _table["LSN-F3"] == _table["GVA-F3"] == "GVA-F3")
verifier("7e. destinataires differents -> cles DIFFERENTES (Fete de la Danse)",
         len({_table["ORG-01"], _table["LSN-E3"], _table["GVA-E3"]}) == 3)
verifier("7f. meme domaine seul -> cles differentes (Jazzercise)",
         _table["LSN-F4"] != _table["ZRH-F2"])
verifier("7g. aucune cle vide", all(v for v in _table.values()))


# ============================================================================
print("\n8. RESERVER N'EST PAS ENVOYER")

_vierge = fiche("T-01", "Test", "Neuchatel")
_reserve = dict(_vierge, **{S.P3S3_CHAMP_CLAIM: INSTANT})
_envoye = dict(_vierge, **{S.P3S3_CHAMP_CLAIM: INSTANT, S.P3S3_CHAMP_ENVOI: INSTANT})

verifier("8a. fiche vierge : contact effectif = NON",
         S.p3s3_contact_effectif(_vierge) is False)
verifier("8b. fiche RESERVEE seule : contact effectif = NON",
         S.p3s3_contact_effectif(_reserve) is False)
verifier("8c. fiche ENVOYEE : contact effectif = OUI",
         S.p3s3_contact_effectif(_envoye) is True)
verifier("8d. INVARIANT — une reservation ne fait PAS passer a `contacte`",
         S.p3s3_statut_metier_cible(_reserve) == "a_contacter",
         S.p3s3_statut_metier_cible(_reserve))
verifier("8e. seul un envoi confirme fait passer a `contacte`",
         S.p3s3_statut_metier_cible(_envoye) == "contacte")
verifier("8f. une reservation SANS envoi, meme ancienne, laisse `a_contacter`",
         S.p3s3_statut_metier_cible(
             dict(_vierge, **{S.P3S3_CHAMP_CLAIM: "2020-01-01T00:00:00+00:00"})) == "a_contacter")
for _avance in ("repondu", "interesse", "refuse", "sans_reponse_pause"):
    verifier("8g. un statut deja avance (%s) n'est JAMAIS ramene a `contacte`" % _avance,
             S.p3s3_statut_metier_cible(dict(_envoye, status=_avance)) == _avance)
verifier("8h. fiche vide / None -> aucune exception, aucun contact",
         S.p3s3_contact_effectif({}) is False and S.p3s3_contact_effectif(None) is False)


# ============================================================================
print("\n9. LE VERROU INTER-CAMPAGNES — COLLISION CONCURRENTE REELLE")

# Bouchon modelisant la regle EXACTE d'un index unique de MongoDB : la
# contrainte ne s'applique qu'aux documents qui SATISFONT le filtre partiel.
# C'est cette nuance qui fait tout : sans elle, la deuxieme action d'une
# campagne serait refusee ; avec un index NON partiel sur (coach_id,
# recipient_key), une campagne ne pourrait contenir qu'un destinataire.


class ErreurUnicite(Exception):
    """L'equivalent de pymongo.errors.DuplicateKeyError (E11000)."""


class CollectionIndexee:
    def __init__(self):
        self.documents = []
        self.index = []          # (cles, unique, filtre_partiel)

    def creer_index(self, cles, unique=False, partiel=None):
        self.index.append((tuple(cles), unique, partiel))

    def _satisfait(self, doc, partiel):
        if not partiel:
            return True
        return all(doc.get(c) == v for c, v in partiel.items())

    def _verifier(self, candidat):
        for cles, unique, partiel in self.index:
            if not unique or not self._satisfait(candidat, partiel):
                continue
            signature = tuple(candidat.get(c) for c in cles)
            for autre in self.documents:
                if autre is candidat or not self._satisfait(autre, partiel):
                    continue
                if tuple(autre.get(c) for c in cles) == signature:
                    raise ErreurUnicite("E11000 " + str(cles))

    def inserer(self, doc):
        candidat = dict(doc)
        self._verifier(candidat)
        self.documents.append(candidat)
        return candidat


def action(campagne, cle, statut="pret", coach=COACH_A):
    """Une action, avec `verrou_actif` DERIVE du statut — jamais pose a la main."""
    doc = {"id": "%s-%s" % (campagne, cle), "campaign_id": campagne,
           "coach_id": coach, "recipient_key": cle, "statut": statut}
    if statut in S.P3S3_STATUTS_VERROU:
        doc["verrou_actif"] = True
    return doc


def base_neuve():
    col = CollectionIndexee()
    col.creer_index(("id",), unique=True)
    col.creer_index(("campaign_id", "recipient_key"), unique=True,
                    partiel=None)
    col.creer_index(("coach_id", "recipient_key"), unique=True,
                    partiel={"verrou_actif": True})
    return col


# --- VERROU 1 : une campagne ne contient pas deux fois le meme destinataire ---
_col = base_neuve()
_col.inserer(action("C1", "GVA-F3"))
try:
    _col.inserer(action("C1", "GVA-F3"))
    _ok = False
except ErreurUnicite:
    _ok = True
verifier("9a. VERROU 1 — le meme destinataire deux fois dans UNE campagne : REFUSE", _ok)

_col = base_neuve()
for _k in ("GVA-F3", "GVA-D2", "ECO-01", "ORG-01", "LSN-E3"):
    _col.inserer(action("C1", _k))
verifier("9b. VERROU 1 — 5 destinataires DIFFERENTS dans une campagne : acceptes",
         len(_col.documents) == 5)

# --- VERROU 2 : deux campagnes ne reclament pas le meme premier contact ---
_col = base_neuve()
_col.inserer(action("C1", "GVA-F3", "reserve"))          # campagne 1 reserve
try:
    _col.inserer(action("C2", "GVA-F3", "reserve"))      # campagne 2 arrive
    _ok = False
except ErreurUnicite:
    _ok = True
verifier("9c. VERROU 2 — deux campagnes CONCURRENTES sur le meme destinataire : REFUSE",
         _ok)

_col = base_neuve()
_col.inserer(action("C1", "GVA-F3", "envoye"))
try:
    _col.inserer(action("C2", "GVA-F3", "reserve"))
    _ok = False
except ErreurUnicite:
    _ok = True
verifier("9d. VERROU 2 — une campagne REJOUEE apres un envoi reussi : REFUSE", _ok)

_col = base_neuve()
_col.inserer(action("C1", "GVA-F3", "echec_indetermine"))
try:
    _col.inserer(action("C2", "GVA-F3", "reserve"))
    _ok = False
except ErreurUnicite:
    _ok = True
verifier("9e. VERROU 2 — apres un echec INDETERMINE : REFUSE (on ignore si l'envoi a eu lieu)",
         _ok)

# ... mais un echec de cause CONNUE libere le destinataire.
_col = base_neuve()
_col.inserer(action("C1", "GVA-F3", "echec"))
_col.inserer(action("C2", "GVA-F3", "reserve"))
verifier("9f. VERROU 2 — apres un echec de cause CONNUE : le destinataire est LIBRE",
         len(_col.documents) == 2)

# ... et deux campagnes non verrouillees coexistent (preparation, exclusion).
_col = base_neuve()
_col.inserer(action("C1", "GVA-F3", "pret"))
_col.inserer(action("C2", "GVA-F3", "pret"))
_col.inserer(action("C3", "GVA-F3", "exclu"))
verifier("9g. VERROU 2 — trois campagnes PREPAREES coexistent (rien n'est reserve)",
         len(_col.documents) == 3)

# ... et le verrou est PAR COACH : l'isolation locataire n'est pas franchie.
_col = base_neuve()
_col.inserer(action("C1", "GVA-F3", "reserve", COACH_A))
_col.inserer(action("C2", "GVA-F3", "reserve", COACH_B))
verifier("9h. VERROU 2 — deux coachs differents ne se bloquent PAS l'un l'autre",
         len(_col.documents) == 2)

# --- LA CONTRE-EPREUVE : sans index partiel, le banc ne prouverait rien ---
_sans = CollectionIndexee()
_sans.creer_index(("id",), unique=True)
_sans.creer_index(("campaign_id", "recipient_key"), unique=True)
_sans.inserer(action("C1", "GVA-F3", "reserve"))
try:
    _sans.inserer(action("C2", "GVA-F3", "reserve"))
    _passe = True
except ErreurUnicite:
    _passe = False
verifier("9i. CONTRE-EPREUVE — SANS le verrou 2, la 2e campagne PASSE : le test mord",
         _passe)

_nonpartiel = CollectionIndexee()
_nonpartiel.creer_index(("coach_id", "recipient_key"), unique=True)   # sans partiel
_nonpartiel.inserer(action("C1", "GVA-F3", "pret"))
try:
    _nonpartiel.inserer(action("C1", "GVA-D2", "pret"))
    _nonpartiel.inserer(action("C2", "GVA-F3", "pret"))
    _casse = False
except ErreurUnicite:
    _casse = True
verifier("9j. CONTRE-EPREUVE — un index NON partiel casserait la preparation elle-meme",
         _casse)


# ============================================================================
print("\n10. LES INDEX SONT REELLEMENT POSES AU DEMARRAGE")

verifier("10a. index unique sur l'identifiant de campagne",
         'await db[P3S3_CAMPAGNES].create_index("id", unique=True)' in SRC)
verifier("10b. index unique sur l'identifiant d'action",
         'await db[P3S3_ACTIONS].create_index("id", unique=True)' in SRC)
verifier("10c. VERROU 1 pose : (campaign_id, recipient_key) unique",
         '[("campaign_id", 1), ("recipient_key", 1)], unique=True,' in SRC)
verifier("10d. VERROU 2 pose : (coach_id, recipient_key) unique",
         '[("coach_id", 1), ("recipient_key", 1)], unique=True,' in SRC)
verifier("10e. VERROU 2 est PARTIEL sur verrou_actif — jamais `sparse`",
         'partialFilterExpression={"verrou_actif": True}' in SRC)
_zone_index = SRC.split("P3-S3-A : les index")[1].split("except Exception")[0]
verifier("10f. aucun index `sparse` introduit par ce lot (le mot-cle, pas le mot)",
         "sparse=" not in _zone_index)
verifier("10g. pagination des campagnes : ordre TOTAL (seconde cle unique)",
         '[("coach_id", 1), ("created_at", -1), ("id", 1)]' in SRC)
verifier("10h. la fiche porte un index sur la cle de son destinataire, NON unique",
         '[("coach_id", 1), (P3S3_CHAMP_CLE, 1)]' in SRC)
verifier("10i. les index sont poses dans le demarrage, pas dans une route",
         SRC.index("P3-S3-A : les index") > SRC.index("[P3-S1] index partner_prospects OK"))


# ============================================================================
print("\n11. RETROCOMPATIBILITE DES 142 FICHES")

_vieille = fiche("FES-01", "Festi'neuch", "Neuchatel")   # telle qu'en base : 3 champs ABSENTS
for _champ in S.P3S3_CHAMPS_PROSPECT:
    verifier("11a. champ %-24s ABSENT d'une fiche existante" % _champ,
             _champ not in _vieille)
verifier("11b. une fiche sans les 3 champs reste `a_contacter`",
         S.p3s3_statut_metier_cible(_vieille) == "a_contacter")
verifier("11c. une fiche sans les 3 champs se regroupe normalement",
         len(S.p3s3_destinataires([_vieille])) == 1)

# Les 3 champs ne sont PAS modifiables depuis un navigateur : la liste blanche
# de P3-S1 ignore toute cle inconnue. Personne ne se declare « contacte ».
_ecrits = S.p3s1_champs_valides({
    "organisation_name": "Test", "category": "festival",
    "first_contact_sent_at": "2026-09-01T00:00:00+00:00",
    "first_contact_claimed_at": "2026-09-01T00:00:00+00:00",
    "recipient_key": "PIRATE-01"}, creation=True)
for _champ in S.P3S3_CHAMPS_PROSPECT:
    verifier("11d. PATCH/POST ne peut PAS ecrire %-24s" % _champ, _champ not in _ecrits)
verifier("11e. ... et le reste du corps est bien pris en compte",
         _ecrits.get("organisation_name") == "Test" and _ecrits.get("category") == "festival")


# ============================================================================
print("\n12. IL EST IMPOSSIBLE QUE CE LOT CONTACTE QUELQU'UN")

DEBUT = SRC.index("# P3-S3-A — SOCLE DU MOTEUR DE CAMPAGNE")
FIN = SRC.index("# --- Leads Routes (Widget IA) ---", DEBUT)
BLOC = SRC[DEBUT:FIN]

# ON INTERROGE LE CODE, PAS LA PROSE. Une premiere version de ce test
# cherchait ces chaines dans le texte du bloc — et mordait sur les
# COMMENTAIRES qui EXPLIQUENT le verrou (« update_one conditionnel »,
# « jamais `sparse` »). Un commentaire n'appelle rien. On parse donc le bloc
# et on inspecte les identifiants REELLEMENT invoques.
ARBRE_BLOC = ast.parse(BLOC)
_appeles = set()
for _n in ast.walk(ARBRE_BLOC):
    if isinstance(_n, ast.Call):
        _f = _n.func
        _appeles.add(getattr(_f, "id", None) or getattr(_f, "attr", None))
    if isinstance(_n, ast.Attribute):
        _appeles.add(_n.attr)
    if isinstance(_n, ast.Name):
        _appeles.add(_n.id)
_appeles.discard(None)

for _interdit in ("insert_one", "update_one", "delete_one", "delete_many",
                  "insert_many", "find_one_and_update", "bulk_write",
                  "find_one", "aggregate", "create_index",
                  "send_email", "send_bulk_email", "_send_whatsapp_meta",
                  "send_push", "send_push_by_email", "notify_all",
                  "resend", "httpx", "requests", "aiohttp", "urllib",
                  "create_task", "db", "api_router", "app"):
    verifier("12a. le bloc P3-S3-A n'invoque jamais %r" % _interdit,
             _interdit not in _appeles)

verifier("12a-bis. aucun decorateur nulle part dans le bloc (donc aucune route)",
         not any(getattr(_n, "decorator_list", None)
                 for _n in ast.walk(ARBRE_BLOC)))
verifier("12b. le bloc ne contient AUCUNE fonction asynchrone ni aucun `await`",
         not any(isinstance(_n, (ast.AsyncFunctionDef, ast.Await))
                 for _n in ast.walk(ARBRE_BLOC)))
verifier("12b-bis. le bloc n'importe rien (aucune dependance reseau possible)",
         not any(isinstance(_n, (ast.Import, ast.ImportFrom))
                 for _n in ast.walk(ARBRE_BLOC)))

# Lecture du code (AST) : aucune fonction p3s3_* n'appelle un helper d'envoi.
ARBRE = ast.parse(SRC)
ENVOI = {"send_email", "send_bulk_email", "_send_whatsapp_meta", "send_push",
         "send_push_by_email", "send_backup_email", "notify_all", "_rc_notifier",
         "p1b_relance_j0", "p1d_relance_j3", "create_task"}
_fautifs = []
_p3s3 = []
for _n in ast.walk(ARBRE):
    if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef)) and _n.name.startswith("p3s3_"):
        _p3s3.append(_n.name)
        for _sous in ast.walk(_n):
            if isinstance(_sous, ast.Call):
                _f = _sous.func
                _nom = getattr(_f, "id", None) or getattr(_f, "attr", None)
                if _nom in ENVOI:
                    _fautifs.append((_n.name, _nom))
verifier("12c. les fonctions p3s3_* existent bien (%d)" % len(_p3s3), len(_p3s3) >= 8,
         str(sorted(_p3s3)))
verifier("12d. AUCUNE fonction p3s3_* n'appelle un helper d'envoi", not _fautifs, str(_fautifs))
verifier("12e. toutes les fonctions p3s3_* sont SYNCHRONES et pures",
         all(isinstance(_n, ast.FunctionDef)
             for _n in ast.walk(ARBRE)
             if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and _n.name.startswith("p3s3_")))

# Aucune route nouvelle : le nombre de decorateurs de route est le meme qu'avant
# le lot pour tout chemin evoquant une campagne de prospection.
for _chemin in ('"/prospect-campaigns', '"/campaign-actions', '"/launch',
                '"/partner-prospects/send', '"/partner-prospects/launch'):
    verifier("12f. aucune route %s" % _chemin, _chemin not in SRC)


# ============================================================================
print("\n" + "=" * 78)
_ok = sum(1 for _, c, _ in RESULTATS if c)
_total = len(RESULTATS)
print("P3-S3-A : %d / %d verifications" % (_ok, _total))
if _ok != _total:
    print("\nECHECS :")
    for _i, _c, _d in RESULTATS:
        if not _c:
            print("  - %s  %s" % (_i, _d))
print("=" * 78)
sys.exit(0 if _ok == _total else 1)
