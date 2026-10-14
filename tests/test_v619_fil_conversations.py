#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V619 — LE FIL COMPLET D'UNE CONVERSATION PARTENAIRE.

POURQUOI CE BANC EXISTE
==============================================================================
Audit du 14/10/2026 : les 11 reponses manuelles envoyees ce jour-la sont bien
en base (`prospect_reply_sends.approved_text`, remises par Resend), mais l'ecran
ne montrait que leur date et leur objet. Le TEXTE parti n'etait jamais renvoye
au frontend. Les J0 / relances non plus, et J+14 manquait.

CE QUE CE FICHIER PROUVE (aucune base reelle, aucun reseau, aucun envoi)
==============================================================================
  A. une reponse manuelle apparait avec `approved_text` — jamais le brouillon
     courant, ni `generated_text`, ni `edited_text` ;
  B. deux messages recus du meme partenaire restent DEUX elements, textes complets ;
  C. J0 / J+3 / J+7 / J+14 apparaissent quand ils sont partis ;
  D. un texte historique n'est montre que s'il est PROUVE (instantane, ou
     empreinte d'approbation intacte ET approbation anterieure a l'envoi) ;
     sinon `text` = None et `texte_garanti` = False ;
  E. statut de remise : delivered -> remis, bounced -> rebond, failed -> echec ;
  F. une reservation (envoi non parti) n'est pas un message ;
  G. ordre chronologique, stable d'une lecture a l'autre ;
  H. l'instantane `jX_sent_text` est ecrit A L'ENVOI, une seule fois ;
  I. la route rend `messages_fil` sans rien changer d'autre, et n'ecrit rien.
"""
try:   # V608 : le point d'envoi Resend unique, visible aussi des fonctions EXTRAITES du serveur
    import builtins as _b608, os as _o608, sys as _s608
    _s608.path.insert(0, _o608.path.dirname(_o608.path.dirname(_o608.path.abspath(__file__))))
    import api.resend_central as _rc608
    _b608._rc = _rc608
except Exception:  # noqa: BLE001
    pass
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


_TENTATIVES = []
_GETADDR = socket.getaddrinfo


def _dns(hote, port, *a, **k):
    if str(hote) in ("localhost", "127.0.0.1", "::1", None):
        return _GETADDR(hote, port, *a, **k)
    _TENTATIVES.append(("dns", hote))
    raise OSError("sortie reseau interdite dans ce banc : %s" % hote)


def _conn(self, adresse, *a, **k):
    _TENTATIVES.append(("connect", adresse))
    raise OSError("sortie reseau interdite dans ce banc")


socket.getaddrinfo = _dns
socket.socket.connect = _conn

SECRET = "secret-de-test-v619-sans-aucun-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v619-inexistant:27017")

import jwt as _jwt          # noqa: E402
import api.server as S      # noqa: E402
from fastapi import HTTPException  # noqa: E402

COACH_A = "coach.a.fictif@exemple.test"
COACH_B = "coach.b.fictif@exemple.test"

_BANC = os.path.join(RACINE, "tests", "test_p3s3b_preparation_campagne.py")
_source = io.open(_BANC, encoding="utf-8").read()
_debut = _source.index("def lancer(coroutine):")
_fin = _source.index('# ============================================================================\nprint("\\n1.')
_espace = {"S": S, "asyncio": asyncio, "COACH_A": COACH_A, "COACH_B": COACH_B,
           "INSTANT": "2026-10-11T07:00:00+00:00", "json": json, "os": os, "sys": sys,
           "_jwt": _jwt, "SECRET": SECRET, "HTTPException": HTTPException}
exec(compile(_source[_debut:_fin], _BANC, "exec"), _espace)   # noqa: S102
CollectionBouchon = _espace["CollectionBouchon"]
BaseBouchon = _espace["BaseBouchon"]
RequeteFictive = _espace["RequeteFictive"]
lancer = _espace["lancer"]
jeton = _espace["jeton"]
JA, JB = jeton(COACH_A), jeton(COACH_B)

# ============================================================================
# FIXTURES — fictives, calquees sur la forme REELLE des documents du 14/10.
# Aucun nom, aucune adresse de partenaire reel.
# ============================================================================
CAMP = "camp-v619"
ACT_M = "act-momboye-fictif"     # cas A : un recu + une reponse envoyee
ACT_J = "act-jacquot-fictif"     # cas B : deux recus
ACT_V = "act-vieux-fictif"       # cas D : campagne re-approuvee apres l'envoi

CAMPAGNE = {"id": CAMP, "coach_id": COACH_A, "etat": "approuvee",
            "approved_at": "2026-10-11T07:50:46+00:00",
            "subject_j0": "Afroboost a Paris : cardio-danse afro",
            "subject_j3": "Petite relance", "subject_j7": "Derniere idee",
            "subject_j14": "Je clos mon suivi"}

ACTIONS = [
    {"id": ACT_M, "campaign_id": CAMP, "coach_id": COACH_A, "channel": "email",
     "recipient_key": "TEST-M", "organisations": ["Centre Test Momboye"], "language": "FR",
     "target": "test.momboye@exemple.test", "statut": "envoye",
     "message_j0": "Bonjour,\nJe suis Coach Bassi.", "message_j3": "Je me permets de relancer.",
     "message_j7": "Une derniere idee.", "message_j14": "Je clos mon suivi.",
     "sent_at": "2026-10-11T08:00:00+00:00", "provider_message_id": "res-j0",
     "provider_status": "delivered", "suivi_livraison": True,
     "j3_sent_at": "2026-10-14T07:00:00+00:00", "j3_provider_message_id": "res-j3",
     "j3_provider_status": "delivered",
     "j7_sent_at": "2026-10-18T07:00:00+00:00", "j7_provider_message_id": "res-j7",
     "j7_provider_status": "bounced",
     "j14_sent_at": "2026-10-25T07:00:00+00:00", "j14_provider_message_id": "res-j14",
     "j14_provider_status": "accepted",
     "prospect_ids": ["TEST-M"], "prospect_uuids": ["u-m"]},
    {"id": ACT_J, "campaign_id": CAMP, "coach_id": COACH_A, "channel": "email",
     "recipient_key": "TEST-J", "organisations": ["Ecole Test Jacquot"], "language": "FR",
     "target": "test.jacquot@exemple.test", "statut": "envoye",
     "message_j0": "Objet : Un cours a Belfort\n\nBonjour Carole,\nVoici ma proposition.",
     "sent_at": "2026-10-11T08:01:00+00:00", "provider_status": "delivered",
     "prospect_ids": ["TEST-J"], "prospect_uuids": ["u-j"]},
]
CAMP_V = {"id": "camp-vieille", "coach_id": COACH_A, "etat": "approuvee",
          "approved_at": "2026-10-05T07:00:00+00:00", "subject_j0": "Objet vieux"}
ACTION_V = {"id": ACT_V, "campaign_id": "camp-vieille", "coach_id": COACH_A, "channel": "email",
            "recipient_key": "TEST-V", "organisations": ["Vieux Test"], "language": "FR",
            "target": "test.vieux@exemple.test", "statut": "envoye",
            "message_j0": "Texte reecrit APRES l'envoi", "sent_at": "2026-09-03T12:00:00+00:00",
            "prospect_ids": ["TEST-V"], "prospect_uuids": ["u-v"]}

LONG = "Bonjour,\n" + ("Ligne longue du partenaire. " * 40)


def recu(ident, action, cle, corps, quand, cite=""):
    return {"id": ident, "coach_id": COACH_A, "campaign_id": CAMP, "action_id": action,
            "recipient_key": cle, "from_email": "%s@exemple.test" % cle.lower(),
            "to_email": "r-x@reply.afroboosteur.com", "subject": "Re: Afroboost a Paris",
            "body_text": corps, "body_quoted": cite, "received_at": quand,
            "provider_email_id": "in-" + ident, "statut": "rattache",
            "matching_method": "A0_REPLY_TOKEN", "matching_confidence": 100,
            "contenu_recupere": True}


MESSAGES = [
    recu("in-m1", ACT_M, "TEST-M", "Bonjour BASSI,\nOui tout a fait.", "2026-10-14T12:08:58.912Z",
         cite="Le mer. 14 oct., Afroboost a ecrit :\n> Bonjour"),
    recu("in-j1", ACT_J, "TEST-J", "Oui, vous pouvez m envoyer une video.", "2026-10-14T09:48:14.190Z"),
    recu("in-j2", ACT_J, "TEST-J", LONG, "2026-10-14T14:50:03.176Z"),
]

ENVOI_M = {"id": "in-m1_hash", "inbound_id": "in-m1", "action_id": ACT_M, "coach_id": COACH_A,
           "recipient_key": "TEST-M", "organisation": "Centre Test Momboye",
           "to_email": "test.momboye@exemple.test", "subject": "Re: Afroboost a Paris",
           "generated_text": "TEXTE IA", "edited_text": "TEXTE EDITE",
           "approved_text": "Bonjour Ludivine,\nMerci beaucoup.",
           "send_status": "envoye", "sent_at": "2026-10-14T14:27:36.625674+00:00",
           "provider": "resend", "provider_message_id": "01a13acf-test",
           "provider_status": "delivered", "suivi_livraison": True}
ENVOI_RESERVE = dict(ENVOI_M, id="in-m1_reserve", send_status="reserve",
                     approved_text="NE DOIT PAS APPARAITRE", sent_at=None,
                     provider_status=None, created_at="2026-10-14T15:00:00+00:00")
ENVOI_ECHEC = dict(ENVOI_M, id="in-j1_echec", inbound_id="in-j1", action_id=ACT_J,
                   approved_text="Reponse refusee par le fournisseur", send_status="echec",
                   sent_at=None, provider_status=None, updated_at="2026-10-14T10:00:00+00:00")
BROUILLON_M = {"inbound_id": "in-m1", "reponse_proposee": "BROUILLON COURANT MODIFIE APRES",
               "edite_le": "2026-10-14T16:00:00+00:00"}


def base_neuve(actions=None, campagnes=None, messages=None, envois=None, brouillons=None):
    b = BaseBouchon([])
    b[S.P3S1_COLLECTION] = CollectionBouchon(S.P3S1_COLLECTION, [])
    b[S.P3S3_CAMPAGNES] = CollectionBouchon(S.P3S3_CAMPAGNES,
                                            [CAMPAGNE] if campagnes is None else campagnes)
    b[S.P3S3_ACTIONS] = CollectionBouchon(S.P3S3_ACTIONS, ACTIONS if actions is None else actions,
                                          uniques=[(("id",), None)])
    b[S.P3U2_COLLECTION] = CollectionBouchon(S.P3U2_COLLECTION,
                                             MESSAGES if messages is None else messages,
                                             uniques=[(("id",), None)])
    b[S.P3AI_BROUILLONS] = CollectionBouchon(S.P3AI_BROUILLONS, brouillons or [],
                                             uniques=[(("inbound_id",), None)])
    b[S.P3AI4_COLLECTION] = CollectionBouchon(S.P3AI4_COLLECTION, envois or [],
                                              uniques=[(("id",), None)])
    b[S.P3N_COLLECTION] = CollectionBouchon(S.P3N_COLLECTION, [])
    b["coaches"] = CollectionBouchon("coaches", [{"email": COACH_A}, {"email": COACH_B}])
    b["coach_auth"] = CollectionBouchon("coach_auth", [])
    S.db = b
    S._v619_preuves_cache.clear()
    return b


def campagne_scellee(campagne, actions):
    """La campagne telle qu'approuvee : empreinte calculee sur ses actions."""
    c = dict(campagne)
    c["snapshot_hash"] = S.p3s3_empreinte([a for a in actions if a.get("campaign_id") == c["id"]], c)
    return c


def lister(jeton_=None):
    return lancer(S.p3u2_lister_reponses(RequeteFictive(jeton_=jeton_ or JA, params=None)))


def conv_de(rep, cle):
    return next(c for c in rep["conversations"] if c["cle"] == cle)


# ============================================================================
print("\n1. A — CENTRE MOMBOYE : message recu + reponse envoyee, texte = approved_text")
CAMP_OK = campagne_scellee(CAMPAGNE, ACTIONS)
base_neuve(campagnes=[CAMP_OK], envois=[ENVOI_M, ENVOI_RESERVE, ENVOI_ECHEC],
           brouillons=[BROUILLON_M])
_rep = lister()
_m = conv_de(_rep, ACT_M)
_fil = _m.get("messages_fil") or []
_manuels = [e for e in _fil if e["type"] == "manual_reply"]
_recus = [e for e in _fil if e["direction"] == "incoming"]
verifier("1a. la conversation porte `messages_fil`", isinstance(_m.get("messages_fil"), list))
verifier("1b. le message recu est la, texte complet (body_text)",
         len(_recus) == 1 and _recus[0]["text"] == MESSAGES[0]["body_text"])
verifier("1c. body_quoted est SEPARE (champ `quoted`), jamais colle au texte",
         _recus[0]["quoted"] == MESSAGES[0]["body_quoted"]
         and MESSAGES[0]["body_quoted"] not in _recus[0]["text"])
verifier("1d. la reponse envoyee montre approved_text",
         len(_manuels) == 1 and _manuels[0]["text"] == ENVOI_M["approved_text"])
_tout = json.dumps(_fil, ensure_ascii=False)
verifier("1e. JAMAIS le brouillon courant, ni generated_text, ni edited_text",
         "BROUILLON COURANT" not in _tout and "TEXTE IA" not in _tout and "TEXTE EDITE" not in _tout)
verifier("1f. F — une reservation non partie n'est pas un message",
         "NE DOIT PAS APPARAITRE" not in _tout)
verifier("1g. E — delivered -> remis, avec l'identifiant Resend",
         _manuels[0]["remise"] == "remis" and _manuels[0]["provider_message_id"] == "01a13acf-test")
verifier("1h. objet et date de la reponse = ceux de la trace",
         _manuels[0]["subject"] == ENVOI_M["subject"] and _manuels[0]["date"] == ENVOI_M["sent_at"])
verifier("1i. les champs existants sont INCHANGES (derniere_reponse_afroboost : date/objet seulement)",
         _m["derniere_reponse_afroboost"] == {"sent_at": S.pf_instant(ENVOI_M["sent_at"]),
                                              "to_email": ENVOI_M["to_email"],
                                              "objet": ENVOI_M["subject"]}
         and "approved_text" not in json.dumps(_m["derniere_reponse_afroboost"]))

# ============================================================================
print("\n2. C / D — J0, J+3, J+7, J+14 : visibles, textes PROUVES par l'approbation")
_types = [e["type"] for e in _fil if e["direction"] == "outgoing"]
for _t in ("j0", "j3", "j7", "j14"):
    verifier("2-%s. %s present dans le fil" % (_t, _t.upper()), _t in _types)
_j = {e["type"]: e for e in _fil}
verifier("2a. J0 : texte = message_j0 approuve, objet = objet de campagne, garanti",
         _j["j0"]["text"] == ACTIONS[0]["message_j0"]
         and _j["j0"]["subject"] == CAMPAGNE["subject_j0"] and _j["j0"]["texte_garanti"] is True
         and _j["j0"]["texte_source"] == "approbation_verifiee")
verifier("2b. J+14 : texte et objet propres a l'etape",
         _j["j14"]["text"] == "Je clos mon suivi." and _j["j14"]["subject"] == "Je clos mon suivi")
verifier("2c. E — remises par etape : J0 remis, J+7 rebond, J+14 en attente",
         _j["j0"]["remise"] == "remis" and _j["j3"]["remise"] == "remis"
         and _j["j7"]["remise"] == "rebond" and _j["j14"]["remise"] == "en_attente")
verifier("2f. J0 ancien (accepted SANS suivi_livraison) -> « inconnu », jamais « en attente »",
         S.v619_remise("accepted", suivi=None) == "inconnu"
         and S.v619_remise("accepted", suivi=True) == "en_attente"
         and S.v619_remise("", "envoye", None) == "inconnu"
         and S.v619_remise("delivery_delayed") == "en_attente")
_jac = conv_de(_rep, ACT_J)["messages_fil"]
_j0j = next(e for e in _jac if e["type"] == "j0")
verifier("2d. V602 : une ligne « Objet : » devient l'objet et SORT du texte (comme a l'envoi)",
         _j0j["subject"] == "Un cours a Belfort" and _j0j["text"].startswith("Bonjour Carole")
         and "Objet" not in _j0j["text"])
verifier("2e. un echec d'envoi reste visible comme tel (pas comme remis)",
         any(e["type"] == "manual_reply" and e["remise"] == "echec" for e in _jac))

# ============================================================================
print("\n3. B — deux messages recus : les DEUX textes complets, dans l'ordre")
_rj = [e for e in _jac if e["direction"] == "incoming"]
verifier("3a. deux elements recus, aucun remplace", len(_rj) == 2)
verifier("3b. textes COMPLETS (le long n'est pas tronque cote serveur)",
         _rj[0]["text"] == MESSAGES[1]["body_text"] and _rj[1]["text"] == LONG)
_dates = [S.pf_instant(e["date"]) for e in _jac]
verifier("3c. G — ordre chronologique", _dates == sorted(_dates), str(_dates))
verifier("3d. G — ordre stable d'une lecture a l'autre",
         [e["id"] for e in conv_de(lister(), ACT_J)["messages_fil"]] == [e["id"] for e in _jac])

# ============================================================================
print("\n4. D — un texte NON prouvable n'est jamais affiche comme envoye")
_v_actions = ACTIONS + [ACTION_V]
_cv = campagne_scellee(CAMP_V, _v_actions)   # approuvee le 05/10, envoi le 03/09
base_neuve(actions=_v_actions, campagnes=[CAMP_OK, _cv],
           messages=MESSAGES + [dict(recu("in-v1", ACT_V, "TEST-V", "Merci", "2026-09-04T08:00:00Z"),
                                     campaign_id="camp-vieille")])
_v0 = next(e for e in conv_de(lister(), ACT_V)["messages_fil"] if e["type"] == "j0")
verifier("4a. approbation POSTERIEURE a l'envoi -> texte None, non garanti",
         _v0["text"] is None and _v0["texte_garanti"] is False and _v0["texte_source"] == "non_garanti")
_alteree = [dict(a, message_j0="ALTERE") if a["id"] == ACT_M else a for a in ACTIONS]
base_neuve(actions=_alteree, campagnes=[CAMP_OK])
_a0 = next(e for e in conv_de(lister(), ACT_M)["messages_fil"] if e["type"] == "j0")
verifier("4b. empreinte ALTEREE -> texte None (jamais le texte modifie)",
         _a0["text"] is None and _a0["texte_garanti"] is False)
base_neuve(actions=ACTIONS, campagnes=[dict(CAMPAGNE)])   # jamais scellee
_n0 = next(e for e in conv_de(lister(), ACT_M)["messages_fil"] if e["type"] == "j0")
verifier("4c. campagne sans empreinte -> non garanti", _n0["text"] is None)
_snap = [dict(a, message_j0="ALTERE", j0_sent_text="TEXTE PARTI EXACT",
              j0_sent_subject="OBJET PARTI") if a["id"] == ACT_M else a for a in ACTIONS]
base_neuve(actions=_snap, campagnes=[CAMP_OK])
_s0 = next(e for e in conv_de(lister(), ACT_M)["messages_fil"] if e["type"] == "j0")
verifier("4d. l'INSTANTANE prime, meme si le texte approuve a bouge depuis",
         _s0["text"] == "TEXTE PARTI EXACT" and _s0["subject"] == "OBJET PARTI"
         and _s0["texte_source"] == "instantane_envoi" and _s0["texte_garanti"] is True)

# ============================================================================
print("\n5. H — l'instantane est ecrit A L'ENVOI, une seule fois")
_four = S.P3S3DFournisseurEmail(objet="Objet de campagne")
_c1 = S.v619_contenu_envoye(_four, S.p3s3d_instantane_envoi(ACTIONS[1]), "cle")
verifier("5a. contenu = charge utile reelle (objet V602 extrait, ligne retiree)",
         _c1 == {"subject": "Un cours a Belfort", "text": "Bonjour Carole,\nVoici ma proposition."})
_c2 = S.v619_contenu_envoye(S.P3S3DFournisseurFactice(), {"message": "Texte simple"}, "cle")
verifier("5b. fournisseur factice : meme regle V602", _c2 == {"subject": "", "text": "Texte simple"})
_b = base_neuve(actions=[{k: v for k, v in ACTIONS[1].items()
                          if k not in ("sent_at", "provider_status")}])
lancer(S.p3s3d_appliquer_succes(dict(ACTIONS[1]), {"provider_message_id": "res-1", "provider": "resend"},
                                "2026-10-15T08:00:00+00:00", contenu=_c1))
_doc = _b[S.P3S3_ACTIONS].documents[0]
verifier("5c. J0 : j0_sent_text / j0_sent_subject ecrits avec sent_at",
         _doc.get("j0_sent_text") == _c1["text"] and _doc.get("j0_sent_subject") == _c1["subject"]
         and _doc.get("sent_at") == "2026-10-15T08:00:00+00:00")
lancer(S.p3s3d_appliquer_succes(dict(_doc), {"provider_message_id": "res-2", "provider": "resend"},
                                "2026-10-16T08:00:00+00:00", contenu={"subject": "X", "text": "AUTRE"}))
verifier("5d. J0 : un second passage n'ECRASE pas l'instantane",
         _b[S.P3S3_ACTIONS].documents[0].get("j0_sent_text") == _c1["text"])
_b = base_neuve(actions=[dict(ACTIONS[1])])
lancer(S.p3r2_appliquer_succes(dict(ACTIONS[1]), "j14", {"provider_message_id": "r14"},
                               "2026-10-25T07:00:00+00:00", contenu={"subject": "S14", "text": "T14"}))
lancer(S.p3r2_appliquer_succes(dict(ACTIONS[1]), "j14", {"provider_message_id": "r14b"},
                               "2026-10-26T07:00:00+00:00", contenu={"subject": "NON", "text": "NON"}))
_d14 = _b[S.P3S3_ACTIONS].documents[0]
verifier("5e. relance J+14 : instantane ecrit une fois, jamais ecrase",
         _d14.get("j14_sent_text") == "T14" and _d14.get("j14_sent_subject") == "S14")
lancer(S.p3r2_appliquer_succes(dict(ACTIONS[1]), "j3", {"provider_message_id": "r3"},
                               "2026-10-14T07:00:00+00:00"))
verifier("5f. sans contenu (appel historique) : aucun instantane invente",
         "j3_sent_text" not in _b[S.P3S3_ACTIONS].documents[0])
_src = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
verifier("5g. les DEUX moteurs passent le contenu reel a l'ecriture de succes",
         _src.count("contenu=v619_contenu_envoye(fournisseur, instantane, cle)") == 2)
verifier("5h. aucune route n'ecrit les instantanes en dehors de l'envoi",
         _src.count('"j0_sent_text"') == 1 and _src.count('p3r2_champ(etape, "sent_text")') == 1)
verifier("5i. l'empreinte d'approbation ne lit PAS les instantanes (aucune campagne invalidee)",
         "sent_text" not in _src[_src.index("def p3s3_empreinte"):_src.index("async def p3s3_portee")])

# ============================================================================
print("\n6. I — lecture seule, portee du coach, aucune sortie")
_base = base_neuve(campagnes=[CAMP_OK], envois=[ENVOI_M])
_avant = {n: json.dumps(_base[n].documents, sort_keys=True, default=str)
          for n in (S.P3U2_COLLECTION, S.P3AI4_COLLECTION, S.P3N_COLLECTION, S.P3S3_ACTIONS,
                    S.P3S3_CAMPAGNES, S.P3AI_BROUILLONS)}
_r1 = lister()
_r2 = lister()
verifier("6a. lire le fil n'ecrit RIEN",
         _avant == {n: json.dumps(_base[n].documents, sort_keys=True, default=str) for n in _avant})
verifier("6b. K — deux lectures -> fil identique",
         json.dumps([c.get("messages_fil") for c in _r1["conversations"]], sort_keys=True)
         == json.dumps([c.get("messages_fil") for c in _r2["conversations"]], sort_keys=True))
verifier("6c. la liste `messages` est inchangee (meme nombre, memes ids)",
         sorted(m["id"] for m in _r1["messages"]) == sorted(m["id"] for m in MESSAGES))
_rb = lister(JB)
verifier("6d. un autre coach ne voit AUCUN fil", _rb["conversations"] == [])
S._v619_preuves_cache.clear()
_orig = S.v619_preuves


async def _panne(*a, **k):
    raise RuntimeError("panne simulee")
S.v619_preuves = _panne
_rp = lister()
S.v619_preuves = _orig
verifier("6e. une panne du fil ne vide PAS l'ecran (conversations rendues, fil absent)",
         len(_rp["conversations"]) == 2 and all("messages_fil" not in c for c in _rp["conversations"]))
verifier("6f. aucune sortie reseau tentee", _TENTATIVES == [], str(_TENTATIVES))

# ============================================================================
TOTAL = len(RESULTATS)
ECHECS = [r for r in RESULTATS if not r[1]]
print("\n" + "=" * 78)
print("V619 FIL DES CONVERSATIONS — %d verifications, %d echec(s)" % (TOTAL, len(ECHECS)))
for intitule, _ok, detail in ECHECS:
    print("  ECHEC %s%s" % (intitule, (" -> %s" % detail) if detail else ""))
print("=" * 78)
sys.exit(1 if ECHECS else 0)
