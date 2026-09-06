#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PROSPECTION FOCUS — UN PARTENAIRE, UNE CONVERSATION.

POURQUOI CE BANC EXISTE
==============================================================================
Mesure du 06/09/2026 en production : QUATRE reponses recues, mais TROIS
interlocuteurs. `info@bde-hearc.ch` a ecrit deux fois (04/09 a 05:25, puis
05/09 a 14:45) sur la MEME action de campagne (`a0e02bd1`). L'ecran affichait
donc deux grosses cartes pour un seul partenaire — l'une intitulee
« BDE HE-Arc » (le nom lu dans le brouillon), l'autre « ETU-04 » (la cle
d'affichage) — sans que rien ne dise que c'etait le meme fil.

Et une reponse Afroboost etait DEJA partie sur ce fil (05/09 a 13:05), donc
AVANT le dernier message recu. Le dossier etait « en attente » : Bassi lisait
ce statut en croyant « j'ai repondu », alors qu'un message attendait toujours.

CE QUE CE FICHIER PROUVE
==============================================================================
  * A. les DEUX messages du BDE forment UNE conversation ;
  * B. « ETU-04 » n'est pas un second interlocuteur : c'est la meme cle ;
  * C+D. ACD Lausanne et SalsaRica restent INDEPENDANTS — deux actions
       differentes ne fusionnent jamais ;
  * E. deux messages qu'aucune action ne reclame restent DEUX conversations :
       on ne rassemble pas deux inconnus ;
  * F. `recipient_key` n'est JAMAIS la cle de regroupement — deux organisations
       peuvent la partager, et grouper dessus melangerait deux dossiers ;
  * G. la reponse Afroboost vient de la TRACE reelle (`prospect_reply_sends`),
       jamais d'un statut : sans trace, la conversation dit qu'aucune reponse
       n'est partie ;
  * H. un envoi ANTERIEUR au dernier message ne compte pas comme une reponse a
       ce message (le cas exact du BDE) ;
  * I. un envoi RESERVE mais non abouti n'est pas une reponse partie ;
  * J. les compteurs comptent des CONVERSATIONS, pas des messages ;
  * K. l'ordre de travail : non lues d'abord, puis a repondre, puis a
       qualifier, puis en attente, puis clos — et il ne change AUCUN statut ;
  * L. les dates se comparent normalisees (« Z » contre « +00:00 ») ;
  * M. la route rend `conversations` SANS toucher a `messages` ;
  * N. la portee est celle du coach : un autre coach ne voit rien ;
  * O. la chronologie du dossier porte les DEUX messages du fil ;
  * P. AUCUN e-mail, aucune sortie reseau, aucune ecriture.
"""
import asyncio
import io
import json
import os
import socket
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


class SortieReseauInterdite(RuntimeError):
    pass


_TENTATIVES = []
_GETADDR = socket.getaddrinfo


def _dns(hote, port, *a, **k):
    if str(hote) in ("localhost", "127.0.0.1", "::1", None):
        return _GETADDR(hote, port, *a, **k)
    _TENTATIVES.append(("dns", hote))
    raise SortieReseauInterdite(str(hote))


def _conn(self, adresse, *a, **k):
    _TENTATIVES.append(("connect", adresse))
    raise SortieReseauInterdite(str(adresse))


def _crea(adresse, *a, **k):
    _TENTATIVES.append(("create_connection", adresse))
    raise SortieReseauInterdite(str(adresse))


socket.getaddrinfo = _dns
socket.socket.connect = _conn
socket.create_connection = _crea

SECRET = "secret-de-test-pf-sans-aucun-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-pf-inexistant:27017")

import jwt as _jwt          # noqa: E402
import api.server as S      # noqa: E402
from fastapi import HTTPException  # noqa: E402

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()

COACH_A = "coach.a.fictif@exemple.test"
COACH_B = "coach.b.fictif@exemple.test"

# Le banc de P3-S3-B fournit deja la base bouchon, la requete fictive et le
# jeton. On les reutilise plutot que d'en ecrire une seconde version : deux
# bouchons pour une meme base finiraient par diverger.
_BANC = os.path.join(RACINE, "tests", "test_p3s3b_preparation_campagne.py")
_source = io.open(_BANC, encoding="utf-8").read()
_debut = _source.index("def lancer(coroutine):")
_fin = _source.index('# ============================================================================\nprint("\\n1.')
_espace = {"S": S, "asyncio": asyncio, "COACH_A": COACH_A, "COACH_B": COACH_B,
           "INSTANT": "2026-09-03T10:57:00+00:00", "json": json, "os": os, "sys": sys,
           "_jwt": _jwt, "SECRET": SECRET, "HTTPException": HTTPException}
exec(compile(_source[_debut:_fin], _BANC, "exec"), _espace)   # noqa: S102
CollectionBouchon = _espace["CollectionBouchon"]
BaseBouchon = _espace["BaseBouchon"]
RequeteFictive = _espace["RequeteFictive"]
lancer = _espace["lancer"]
jeton = _espace["jeton"]

JA, JB = jeton(COACH_A), jeton(COACH_B)

# ============================================================================
# LES QUATRE MESSAGES REELS, RECOPIES DE LA PRODUCTION (mesure du 06/09/2026).
# Les identifiants sont ceux de la base ; les corps, ceux qui y sont vraiment.
# C'est sur eux que le regroupement doit tenir, pas sur des cas de laboratoire.
# ============================================================================
ACT_BDE = "a0e02bd1-5599-4419-af53-577cc863eb8b"
ACT_ACD = "61a24e82-a1a6-4074-9c01-949db28f3a6a"
ACT_SALSA = "4a5e8950-44c7-4039-ae4b-99584426f3c4"

ACTIONS = [
    {"id": ACT_BDE, "campaign_id": "camp-p3", "coach_id": COACH_A, "channel": "email",
     "recipient_key": "ETU-04", "organisations": ["BDE HE-Arc"],
     "prospect_ids": ["ETU-04"], "prospect_uuids": ["p-bde"], "language": "FR",
     "statut": "envoye", "sent_at": "2026-09-03T10:57:23+00:00"},
    {"id": ACT_ACD, "campaign_id": "camp-p3", "coach_id": COACH_A, "channel": "email",
     "recipient_key": "LSN-A3",
     "organisations": ["Association Art et Culture pour le Developpement (ACD)"],
     "prospect_ids": ["LSN-A3"], "prospect_uuids": ["p-acd"], "language": "FR",
     "statut": "envoye", "sent_at": "2026-09-03T10:57:36+00:00"},
    {"id": ACT_SALSA, "campaign_id": "camp-p3", "coach_id": COACH_A, "channel": "email",
     "recipient_key": "ZRH-D5", "organisations": ["SalsaRica Dance School"],
     "prospect_ids": ["ZRH-D5"], "prospect_uuids": ["p-salsa"], "language": "DE",
     "statut": "envoye", "sent_at": "2026-09-03T10:57:52+00:00"},
]


def message(identifiant, action, cle, adresse, corps, recu, **extra):
    doc = {"id": identifiant, "coach_id": COACH_A, "campaign_id": "camp-p3",
           "action_id": action, "recipient_key": cle, "from_email": adresse,
           "to_email": "r-jeton@reply.afroboosteur.com",
           "subject": "Re: Proposition de collaboration avec Afroboost",
           "body_text": corps, "received_at": recu, "statut": "rattache",
           "matching_method": "A0_REPLY_TOKEN", "matching_confidence": 100,
           "motif": "", "processed_at": recu, "created_at": recu}
    doc.update(extra)
    return doc


# Le premier message du BDE porte volontairement un « Z » et le second un
# « +00:00 » : c'est le melange reel des deux plumes (moteur d'entree contre
# AI-P4), et c'est lui qui piegeait la comparaison de chaines.
MESSAGES = [
    message("5068f64c", ACT_BDE, "ETU-04", "info@bde-hearc.ch",
            "Cela nous semble une proposition interessante, ca consiste en quoi?",
            "2026-09-04T05:25:19Z"),
    message("427bb698", ACT_BDE, "ETU-04", "info@bde-hearc.ch",
            "Merci pour votre retour. Une derniere question avant de decider.",
            "2026-09-05T14:45:26+00:00"),
    message("391a2f91", ACT_ACD, "LSN-A3", "eveline.sautaux@assoacd.org",
            "Bonjour oui, cela peut se faire, Ndongo Beye est joignable au 076.",
            "2026-09-03T13:35:35+00:00"),
    message("de819aad", ACT_SALSA, "ZRH-D5", "info@salsarica.ch",
            "Danke fuer deine Anfrage, aber wir sind nicht interessiert.",
            "2026-09-03T11:37:15+00:00"),
]

# L'ENVOI REEL : la reponse partie au BDE le 05/09 a 13:05 — donc AVANT le
# message de 14:45. C'est le coeur du cas H.
ENVOI_BDE = {
    "id": "5068f64c_abcdef0123456789", "inbound_id": "5068f64c", "action_id": ACT_BDE,
    "coach_id": COACH_A, "recipient_key": "ETU-04", "organisation": "BDE HE-Arc",
    "to_email": "info@bde-hearc.ch", "subject": "Re: Proposition de collaboration",
    "send_status": "envoye", "sent_at": "2026-09-05T13:05:42.297565+00:00",
    "provider": "resend", "approved_by": COACH_A,
}


def base_neuve(messages=None, actions=None, envois=None, notes=None, brouillons=None):
    b = BaseBouchon([])
    b[S.P3S1_COLLECTION] = CollectionBouchon(S.P3S1_COLLECTION, [])
    b[S.P3S3_ACTIONS] = CollectionBouchon(S.P3S3_ACTIONS,
                                          ACTIONS if actions is None else actions,
                                          uniques=[(("id",), None)])
    b[S.P3U2_COLLECTION] = CollectionBouchon(
        S.P3U2_COLLECTION, MESSAGES if messages is None else messages,
        uniques=[(("id",), None)])
    b[S.P3AI_BROUILLONS] = CollectionBouchon(S.P3AI_BROUILLONS, brouillons or [],
                                             uniques=[(("inbound_id",), None)])
    b[S.P3AI4_COLLECTION] = CollectionBouchon(S.P3AI4_COLLECTION, envois or [],
                                              uniques=[(("id",), None)])
    b[S.P3N_COLLECTION] = CollectionBouchon(S.P3N_COLLECTION, notes or [])
    b["coaches"] = CollectionBouchon("coaches", [{"email": COACH_A}, {"email": COACH_B}])
    b["coach_auth"] = CollectionBouchon("coach_auth", [])
    S.db = b
    return b


def lister(jeton_=None, params=None):
    return lancer(S.p3u2_lister_reponses(RequeteFictive(jeton_=jeton_ or JA,
                                                        params=params)))


def par_cle(conversations):
    return {c["cle"]: c for c in conversations}


# ============================================================================
print("\n1. UN PARTENAIRE, UNE CONVERSATION — LE CAS QUI A DECLENCHE CE LOT")

base_neuve(envois=[ENVOI_BDE])
_rep = lister()
_convs = _rep["conversations"]
_index = par_cle(_convs)

verifier("1a. 4 messages recus, 3 conversations rendues",
         len(_rep["messages"]) == 4 and len(_convs) == 3,
         "messages=%d conversations=%d" % (len(_rep["messages"]), len(_convs)))
verifier("1b. A. les DEUX messages du BDE sont dans la MEME conversation",
         _index[ACT_BDE]["nb_messages"] == 2
         and set(_index[ACT_BDE]["message_ids"]) == {"5068f64c", "427bb698"},
         str(_index.get(ACT_BDE, {}).get("message_ids")))
verifier("1c. B. « ETU-04 » n'est pas une seconde conversation",
         all(c["cle"] != "ETU-04" for c in _convs)
         and len([c for c in _convs if c["recipient_key"] == "ETU-04"]) == 1)
verifier("1d. la conversation porte le NOM de l'organisation, pas la cle",
         _index[ACT_BDE]["organisation"] == "BDE HE-Arc",
         _index[ACT_BDE]["organisation"])
verifier("1e. C+D. ACD et SalsaRica restent independants",
         ACT_ACD in _index and ACT_SALSA in _index
         and _index[ACT_ACD]["nb_messages"] == 1
         and _index[ACT_SALSA]["nb_messages"] == 1)
verifier("1f. aucune organisation n'apparait dans la conversation d'une autre",
         "Ndongo" not in json.dumps(_index[ACT_BDE], ensure_ascii=False)
         and "BDE" not in json.dumps(_index[ACT_ACD], ensure_ascii=False))
verifier("1g. le dernier message du fil BDE est bien celui du 05/09 a 14:45",
         _index[ACT_BDE]["dernier_message"]["id"] == "427bb698",
         _index[ACT_BDE]["dernier_message"]["id"])

# ============================================================================
print("\n2. LA CLE EST `action_id`, JAMAIS `recipient_key`")

# DEUX ORGANISATIONS PARTAGENT LA MEME `recipient_key`. C'est possible :
# `p3s3_recipient_key` rend la `ref` de la fiche la PLUS ANCIENNE d'un groupe
# fusionne. Grouper dessus melangerait deux dossiers.
_collision = [
    message("m-x", "act-x", "MEME-CLE", "un@exemple.test", "Message X",
            "2026-09-01T10:00:00+00:00"),
    message("m-y", "act-y", "MEME-CLE", "deux@exemple.test", "Message Y",
            "2026-09-01T11:00:00+00:00"),
]
base_neuve(messages=_collision, actions=[
    {"id": "act-x", "coach_id": COACH_A, "recipient_key": "MEME-CLE",
     "organisations": ["Organisation X"], "prospect_uuids": []},
    {"id": "act-y", "coach_id": COACH_A, "recipient_key": "MEME-CLE",
     "organisations": ["Organisation Y"], "prospect_uuids": []},
])
_c = lister()["conversations"]
verifier("2a. F. deux actions partageant une cle restent DEUX conversations",
         len(_c) == 2 and {x["cle"] for x in _c} == {"act-x", "act-y"},
         str([x["cle"] for x in _c]))
verifier("2b. chacune porte SON organisation",
         {x["organisation"] for x in _c} == {"Organisation X", "Organisation Y"})

# DEUX MESSAGES QU'AUCUNE ACTION NE RECLAME.
_orphelins = [
    message("orph-1", None, None, "inconnu1@exemple.test", "Qui etes-vous ?",
            "2026-09-01T10:00:00+00:00", statut="manual_review", motif="ambigu"),
    message("orph-2", None, None, "inconnu2@exemple.test", "Bonjour ?",
            "2026-09-01T11:00:00+00:00", statut="manual_review", motif="ambigu"),
]
base_neuve(messages=_orphelins, actions=[])
_c = lister()["conversations"]
verifier("2c. E. deux inconnus ne sont pas « le meme partenaire »",
         len(_c) == 2 and all(x["cle"].startswith("inbound:") for x in _c),
         str([x["cle"] for x in _c]))
verifier("2d. un orphelin n'a ni organisation inventee ni action",
         all(x["organisation"] == "" and x["action_id"] is None for x in _c))

verifier("2e. la fonction de cle est PURE et ne lit que `action_id`/`id`",
         S.pf_cle_conversation({"action_id": "a-1", "id": "m-1"}) == "a-1"
         and S.pf_cle_conversation({"action_id": "", "id": "m-1"}) == "inbound:m-1"
         and S.pf_cle_conversation({"action_id": "  ", "id": "m-1"}) == "inbound:m-1")

# ============================================================================
print("\n3. « REPONSE ENVOYEE » VIENT DE LA TRACE, JAMAIS D'UN STATUT")

base_neuve(envois=[ENVOI_BDE])
_index = par_cle(lister()["conversations"])

verifier("3a. G. la conversation BDE porte la trace reelle de l'envoi",
         (_index[ACT_BDE]["derniere_reponse_afroboost"] or {}).get("to_email")
         == "info@bde-hearc.ch")
verifier("3b. H. l'envoi du 05/09 13:05 est ANTERIEUR au message de 14:45",
         _index[ACT_BDE]["reponse_apres_dernier_message"] is False,
         "sent=%s recu=%s" % (
             (_index[ACT_BDE]["derniere_reponse_afroboost"] or {}).get("sent_at"),
             _index[ACT_BDE]["dernier_message_at"]))
verifier("3c. G. sans trace, ACD n'annonce AUCUNE reponse envoyee",
         _index[ACT_ACD]["derniere_reponse_afroboost"] is None
         and _index[ACT_ACD]["reponse_apres_dernier_message"] is False)

# UN ENVOI POSTERIEUR AU DERNIER MESSAGE, LUI, COMPTE.
_apres = dict(ENVOI_BDE, id="autre", inbound_id="427bb698",
              sent_at="2026-09-06T08:00:00+00:00")
base_neuve(envois=[_apres])
verifier("3d. un envoi POSTERIEUR au dernier message compte comme reponse",
         par_cle(lister()["conversations"])[ACT_BDE]["reponse_apres_dernier_message"]
         is True)

# UN ENVOI RESERVE MAIS NON ABOUTI N'EST PAS UNE REPONSE PARTIE.
_reserve = dict(ENVOI_BDE, id="reserve", send_status="reserve", sent_at=None)
base_neuve(envois=[_reserve])
verifier("3e. I. un envoi RESERVE (non abouti) n'est pas une reponse partie",
         par_cle(lister()["conversations"])[ACT_BDE]["derniere_reponse_afroboost"] is None)

_echoue = dict(ENVOI_BDE, id="echoue", send_status="echec",
               sent_at=None, error_code="bounced")
base_neuve(envois=[_echoue])
verifier("3f. I. un envoi en ECHEC non plus",
         par_cle(lister()["conversations"])[ACT_BDE]["derniere_reponse_afroboost"] is None)

# LE PLUS RECENT DES ENVOIS REUSSIS GAGNE.
base_neuve(envois=[ENVOI_BDE, dict(ENVOI_BDE, id="plus-recent",
                                   sent_at="2026-09-06T09:30:00+00:00")])
verifier("3g. de deux envois reussis, c'est le PLUS RECENT qui est rendu",
         (par_cle(lister()["conversations"])[ACT_BDE]["derniere_reponse_afroboost"]
          or {}).get("sent_at", "").startswith("2026-09-06T09:30"))

# L. LA COMPARAISON DES DATES EST NORMALISEE.
verifier("3h. L. « Z » et « +00:00 » se comparent apres normalisation",
         S.pf_instant("2026-09-05T13:05:42Z")
         == S.pf_instant("2026-09-05T13:05:42+00:00"))
verifier("3i. L. une date illisible rend \"\", jamais une date d'aujourd'hui",
         S.pf_instant("pas une date") == "" and S.pf_instant(None) == ""
         and S.pf_instant("") == "")
verifier("3j. L. une date sans fuseau est lue comme UTC, pas rejetee",
         S.pf_instant("2026-09-05T13:05:42")
         == S.pf_instant("2026-09-05T13:05:42+00:00"))
# LA COMPARAISON BRUTE ETAIT FAUSSE : « Z » (0x5A) passe apres « + » (0x2B).
verifier("3k. L. la comparaison BRUTE aurait donne un resultat FAUX",
         "2026-09-05T13:05:42+00:00" < "2026-09-05T13:05:42Z",
         "le piege qu'evite la normalisation n'existe plus — a revoir")

# ============================================================================
print("\n4. LES COMPTEURS COMPTENT DES CONVERSATIONS")

base_neuve(envois=[ENVOI_BDE])
_rep = lister()
_cpt = _rep["conversations_counts"]
verifier("4a. J. total = 3 conversations, pas 4 messages",
         _cpt["total"] == 3, str(_cpt))
verifier("4b. J. `total` (messages) reste a 4 — il n'est PAS ecrase",
         _rep["total"] == 4, str(_rep["total"]))
verifier("4c. les non lues se comptent par conversation, pas par message",
         _cpt["non_lues"] == 3, str(_cpt["non_lues"]))
verifier("4d. les cinq etats commerciaux ont chacun leur compteur",
         all(k in _cpt for k in S.P3N_STATUTS))
verifier("4e. `a_traiter` ne compte que ce qui attend un geste",
         _cpt["a_traiter"] == 3, str(_cpt["a_traiter"]))

# UNE CONVERSATION TRAITEE SORT DE `a_traiter`.
_traites = [dict(m, traite_at="2026-09-05T18:00:00+00:00") for m in MESSAGES]
base_neuve(messages=_traites)
_cpt = lister()["conversations_counts"]
verifier("4f. trois dossiers clos : `a_traiter` tombe a 0, `traite` monte a 3",
         _cpt["a_traiter"] == 0 and _cpt["traite"] == 3, str(_cpt))

# ============================================================================
print("\n5. L'ORDRE DE TRAVAIL — ET IL NE CHANGE AUCUN STATUT")

verifier("5a. K. une non lue qui attend un geste passe en tete",
         S.pf_rang(S.P3N_STATUT_A_REPONDRE, True, "question") == S.PF_RANG_NOUVEAU)
verifier("5b. K. une demande identifiee passe avant un dossier a qualifier",
         S.pf_rang(S.P3N_STATUT_A_REPONDRE, False, "question")
         < S.pf_rang(S.P3N_STATUT_A_REPONDRE, False, "autre"))
verifier("5c. K. sans analyse, le dossier est « a qualifier »",
         S.pf_rang(S.P3N_STATUT_A_REPONDRE, False, "") == S.PF_RANG_A_QUALIFIER)
verifier("5d. K. « en attente » passe apres tout ce qui attend un geste",
         S.pf_rang(S.P3N_STATUT_ATTENTE, False, "question") == S.PF_RANG_ATTENTE
         and S.PF_RANG_ATTENTE > S.PF_RANG_A_QUALIFIER)
verifier("5e. K. refus et traite ferment la file",
         S.pf_rang(S.P3N_STATUT_REFUS, True, "refus") == S.PF_RANG_CLOS
         and S.pf_rang(S.P3N_STATUT_TRAITE, True, "positif") == S.PF_RANG_CLOS)
verifier("5f. K. un dossier CLOS non lu ne remonte pas en tete",
         S.pf_rang(S.P3N_STATUT_REFUS, True, "refus") == S.PF_RANG_CLOS)

# A RANG EGAL, LE PLUS RECENT D'ABORD.
base_neuve()
_ordre = [c["cle"] for c in lister()["conversations"]]
verifier("5g. a rang egal, le plus recent d'abord",
         _ordre[0] == ACT_BDE, str(_ordre))
verifier("5h. K. trier n'a REQUALIFIE personne — les statuts sont inchanges",
         all(c["statut_commercial"] == S.P3N_STATUT_A_REPONDRE
             for c in lister()["conversations"]))

# ============================================================================
print("\n6. LA ROUTE : ADDITIVE, ET SUR LA SEULE PORTEE DU COACH")

base_neuve(envois=[ENVOI_BDE])
_rep = lister()
verifier("6a. M. `messages` est rendu a l'identique, aucun champ retire",
         len(_rep["messages"]) == 4
         and all({"id", "body_text", "from_email", "received_at", "subject",
                  "statut_commercial"} <= set(m) for m in _rep["messages"]))
verifier("6b. M. les compteurs de READ-P1 et AI-P3 sont toujours la",
         all(k in _rep for k in ("non_lues", "a_repondre", "en_attente",
                                 "refus", "traite", "a_rattacher", "total")))
verifier("6c. M. les trois nouvelles cles sont presentes",
         all(k in _rep for k in ("conversations", "conversations_total",
                                 "conversations_counts")))

_autre = lister(jeton_=JB)
verifier("6d. N. un AUTRE coach ne voit aucune conversation",
         _autre["conversations"] == [] and _autre["conversations_counts"]["total"] == 0,
         str(_autre["conversations_counts"]))

_refus = False
try:
    lancer(S.p3u2_lister_reponses(RequeteFictive(jeton_=None)))
except HTTPException as e:
    _refus = e.status_code in (401, 403)
verifier("6e. N. sans jeton, la route refuse — comme avant ce lot", _refus)

# LE FILTRE COMMERCIAL PORTE AUSSI SUR LES CONVERSATIONS.
base_neuve(messages=[dict(MESSAGES[0]), dict(MESSAGES[1]),
                     dict(MESSAGES[2], traite_at="2026-09-05T18:00:00+00:00"),
                     dict(MESSAGES[3])])
_filtre = lister(params={"statut_commercial": "traite"})
verifier("6f. le filtre commercial reduit les conversations rendues",
         len(_filtre["conversations"]) == 1
         and _filtre["conversations"][0]["cle"] == ACT_ACD,
         str([c["cle"] for c in _filtre["conversations"]]))
verifier("6g. mais les COMPTEURS, eux, restent ceux de toute la portee",
         _filtre["conversations_counts"]["total"] == 3,
         str(_filtre["conversations_counts"]))

# ============================================================================
print("\n7. LA CHRONOLOGIE DU DOSSIER PORTE TOUT LE FIL")

base_neuve(envois=[ENVOI_BDE])
_dossier = lancer(S.p3n_lire_dossier("5068f64c", RequeteFictive(jeton_=JA)))
_recues = [e for e in _dossier["timeline"] if e.get("genre") == "reponse"]
verifier("7a. O. les DEUX messages du fil BDE sont dans la chronologie",
         len(_recues) == 2, str(_recues))
verifier("7b. O. elles sont datees des vrais instants, dans l'ordre",
         [e["quand"] for e in _recues]
         == ["2026-09-04T05:25:19Z", "2026-09-05T14:45:26+00:00"],
         str([e["quand"] for e in _recues]))
verifier("7c. O. la proposition J0 ouvre toujours la chronologie",
         _dossier["timeline"][0]["titre"] == "Proposition Afroboost envoyée",
         _dossier["timeline"][0]["titre"])
verifier("7d. O. l'etat courant ferme toujours la chronologie",
         _dossier["timeline"][-1]["genre"] == "statut")

_solo = lancer(S.p3n_lire_dossier("391a2f91", RequeteFictive(jeton_=JA)))
verifier("7e. O. un fil a un seul message n'en invente pas un second",
         len([e for e in _solo["timeline"] if e.get("genre") == "reponse"]) == 1)

verifier("7f. O. la chronologie reste PURE : sans `messages_du_fil`, un seul recu",
         len([e for e in S.p3n_timeline(ACTIONS[0], MESSAGES[0], [], "a_repondre")
              if e.get("genre") == "reponse"]) == 1)

# ============================================================================
print("\n8. AUCUN ENVOI, AUCUNE ECRITURE, AUCUNE SORTIE RESEAU")

_base = base_neuve(envois=[ENVOI_BDE])
_avant = {nom: json.dumps(_base[nom].documents, sort_keys=True, default=str)
          for nom in (S.P3U2_COLLECTION, S.P3AI4_COLLECTION, S.P3N_COLLECTION,
                      S.P3AI_BROUILLONS, S.P3S3_ACTIONS)}
lister()
lister(params={"statut_commercial": "a_repondre"})
lancer(S.p3n_lire_dossier("5068f64c", RequeteFictive(jeton_=JA)))
_apres_lectures = {nom: json.dumps(_base[nom].documents, sort_keys=True, default=str)
                   for nom in _avant}
verifier("8a. P. lire les conversations n'ecrit RIEN, dans aucune collection",
         _avant == _apres_lectures,
         str([n for n in _avant if _avant[n] != _apres_lectures[n]]))
verifier("8b. P. aucune migration : les 4 messages sont intacts et separes",
         len(_base[S.P3U2_COLLECTION].documents) == 4
         and {d["id"] for d in _base[S.P3U2_COLLECTION].documents}
         == {"5068f64c", "427bb698", "391a2f91", "de819aad"})
verifier("8c. P. aucune sortie reseau n'a ete tentee",
         _TENTATIVES == [], str(_TENTATIVES))

_bloc = SRC[SRC.index("# PROSPECTION FOCUS (PF) — UN PARTENAIRE, UNE CONVERSATION"):]
_bloc = _bloc[:_bloc.index("\n# ====")] if "\n# ====" in _bloc else _bloc
verifier("8d. P. le bloc PF ne connait AUCUNE route d'envoi",
         not any(mot in _bloc for mot in ("resend", "envoyer", "/send", "smtp",
                                          "insert_one", "update_one", "delete_one")),
         "un verbe d'ecriture ou d'envoi est apparu dans le bloc PF")

# ============================================================================
TOTAL = len(RESULTATS)
ECHECS = [r for r in RESULTATS if not r[1]]
print("\n" + "=" * 78)
print("PROSPECTION FOCUS — %d verifications, %d echec(s)" % (TOTAL, len(ECHECS)))
for intitule, _ok, detail in ECHECS:
    print("  ECHEC %s%s" % (intitule, (" -> %s" % detail) if detail else ""))
print("=" * 78)
sys.exit(1 if ECHECS else 0)
