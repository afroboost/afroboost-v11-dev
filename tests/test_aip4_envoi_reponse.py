#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI-P4 — LA REPONSE PART, ET SEULEMENT QUAND UN HUMAIN L'A DECIDE. ZERO E-MAIL.

CE BANC N'ENVOIE AUCUNE NOTIFICATION. `send_push_by_email` est remplace par un
faux AVANT tout appel, et toute sortie reseau est interdite au niveau socket :
si une ligne tentait d'atteindre FCM, le banc echouerait au lieu de reveiller
un telephone.

CE QU'IL PROUVE
==============================================================================
  * A/B/C. avec un seul drapeau — ou aucun — ZERO appel au fournisseur ;
  * D. les deux drapeaux ouverts (en test, fournisseur factice) -> UN appel ;
  * E/F. un rejeu et un double clic ne produisent JAMAIS deux e-mails ;
  * G. un texte CORRIGE est une operation distincte, jamais automatique ;
  * H. un autre coach est refuse ;
  * J/K. `recipient_key` n'est pas une identite, et le `to_email` du navigateur
       est IGNORE : le serveur resout le destinataire lui-meme ;
  * L/M/N/O. texte vide, brouillon perime, STOP, adresse invalide -> refus ;
  * P/Q. une panne ou une reponse ambigue ne pose AUCUN statut faux ;
  * R. prix, contrat, commission -> VALIDATION BASSI ;
  * threading : `In-Reply-To` et `References` seulement s'ils existent ;
  * T. AUCUN e-mail reel, aucune sortie reseau.
"""
import ast
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


socket.getaddrinfo = _dns
socket.socket.connect = lambda self, a, *x, **k: (_TENTATIVES.append(("connect", a)),
                                                  (_ for _ in ()).throw(SortieReseauInterdite(str(a))))[0]
socket.create_connection = lambda a, *x, **k: (_TENTATIVES.append(("create", a)),
                                               (_ for _ in ()).throw(SortieReseauInterdite(str(a))))[0]

SECRET = "secret-de-test-aip4-sans-aucun-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-aip4-inexistant:27017")

import jwt as _jwt          # noqa: E402
import api.server as S      # noqa: E402
from fastapi import HTTPException  # noqa: E402

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()


def _bloc(source, entete):
    debut = source.index(entete)
    banniere = "\n# " + "=" * 76 + "\n# "
    apres = source.index("\n\n", debut)
    suivante = source.find(banniere, apres)
    return source[debut:suivante] if suivante != -1 else source[debut:]


BLOC = _bloc(SRC, "# AI-P4 — LA REPONSE PART, ET SEULEMENT QUAND UN HUMAIN L'A DECIDE")


def _code_seul(bloc):
    """Le CODE du bloc, sans commentaires ni docstrings. Les interdits de ce
    banc portent sur ce que le code FAIT, jamais sur ce qu'il RACONTE."""
    arbre = ast.parse(bloc)
    for n in ast.walk(arbre):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                          ast.ClassDef)) and ast.get_docstring(n):
            n.body = n.body[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(arbre))


CODE = _code_seul(BLOC)

COACH_A = "coach.a.fictif@exemple.test"
COACH_B = "coach.b.fictif@exemple.test"
INSTANT = "2026-09-05T09:00:00+00:00"
ENVOI = "2026-09-03T09:00:00+00:00"
RECU = "2026-09-05T11:00:00+00:00"

_BANC = os.path.join(RACINE, "tests", "test_p3s3b_preparation_campagne.py")
_source = io.open(_BANC, encoding="utf-8").read()
_debut = _source.index("def lancer(coroutine):")
_fin = _source.index('# ============================================================================\nprint("\\n1.')
_espace = {"S": S, "asyncio": asyncio, "COACH_A": COACH_A, "COACH_B": COACH_B,
           "INSTANT": INSTANT, "json": json, "os": os, "sys": sys,
           "_jwt": _jwt, "SECRET": SECRET, "HTTPException": HTTPException}
exec(compile(_source[_debut:_fin], _BANC, "exec"), _espace)   # noqa: S102
CollectionBouchon = _espace["CollectionBouchon"]
BaseBouchon = _espace["BaseBouchon"]
lancer = _espace["lancer"]

# ============================================================================
# LE FAUX FOURNISSEUR DE PUSH. Il est pose AVANT le premier appel et remplace
# `send_push_by_email` en entier : aucune ligne de ce banc ne peut atteindre
# pywebpush, VAPID ou FCM.
# ============================================================================
PUSHS = []
_ECHEC_PUSH = {"actif": False}
_SANS_ABONNEMENT = {"actif": False}


async def faux_push(email, titre, corps, donnees=None):
    PUSHS.append({"email": email, "titre": titre, "corps": corps,
                  "donnees": dict(donnees or {})})
    if _ECHEC_PUSH["actif"]:
        raise RuntimeError("FCM injoignable (simule)")
    return not _SANS_ABONNEMENT["actif"]


S.send_push_by_email = faux_push


class CollectionUpsert(CollectionBouchon):
    """Le bouchon partage ignore `upsert` : il rend `matched_count: 0` et
    n'ecrit rien. Or c'est EXACTEMENT le mecanisme que ce lot utilise pour son
    idempotence (`$setOnInsert` + upsert, motif CAL-2). Sans ce complement, le
    banc prouverait le contraire de la realite — il verrait « deja signalee »
    la ou la production cree la notification.

    On l'etend ICI, pas dans le banc partage : quatorze autres fichiers en
    dependent, et aucun n'a besoin de cette semantique.
    """

    async def update_one(self, filtre, maj, upsert=False, *a, **k):
        for d in self.documents:
            if self._ok(d, filtre):
                d.update(maj.get("$set") or {})
                self.ecritures += 1
                return type("R", (), {"matched_count": 1, "modified_count": 1,
                                      "upserted_id": None})()
        if not upsert:
            return type("R", (), {"matched_count": 0, "modified_count": 0,
                                  "upserted_id": None})()
        candidat = dict(filtre)
        candidat.update(maj.get("$setOnInsert") or {})
        candidat.update(maj.get("$set") or {})
        self._verifier_uniques(candidat)
        self.documents.append(candidat)
        self.ecritures += 1
        return type("R", (), {"matched_count": 0, "modified_count": 0,
                              "upserted_id": candidat.get("id") or True})()


def action_de(suffixe, cible, cle, organisation, coach=COACH_A):
    return {"id": "act-" + suffixe, "campaign_id": "camp-p3", "coach_id": coach,
            "channel": "email", "target": cible, "recipient_key": cle,
            "organisations": [organisation], "prospect_ids": ["R-" + cle],
            "prospect_uuids": ["p-" + suffixe], "language": "FR",
            "message_j0": "Bonjour", "statut": "envoye", "sent_at": ENVOI,
            "provider": "resend", "provider_message_id": "prov-" + suffixe}


def base_neuve(actions=None):
    b = BaseBouchon([])
    b[S.P3S3_ACTIONS] = CollectionBouchon(S.P3S3_ACTIONS, actions or [],
                                          uniques=[(("id",), None)])
    b[S.P3U2_COLLECTION] = CollectionBouchon(
        S.P3U2_COLLECTION, [],
        uniques=[(("coach_id", "dedupe_key"), {"dedupe_key": {"$type": "string"}})])
    b["notifications"] = CollectionUpsert("notifications", [], uniques=[(("id",), None)])
    b["subscribers"] = CollectionBouchon("subscribers", [], uniques=[(("channel", "value"), None)])
    S.db = b
    PUSHS.clear()
    return b


def entrant(**k):
    base = {"message_id": "<reponse-1@client.exemple.test>",
            "from_email": "info@bde-hearc.exemple.test",
            "to_email": "contact@afroboosteur.com",
            "subject": "Re: Proposition de collaboration avec Afroboost",
            "body_text": "Cela nous semble interessant, ca consiste en quoi ?",
            "received_at": RECU, "provider": "resend", "provider_event_id": "evt-001"}
    base.update(k)
    return base


def recevoir(brut, coach=COACH_A):
    return lancer(S.p3u2_recevoir(brut, coach))


ACT = action_de("etu", "info@bde-hearc.exemple.test", "ETU-04", "BDE HE-ARC")


# ============================================================================
# LE FOURNISSEUR EST UN FAUX, ET AUCUN E-MAIL NE PEUT PARTIR.
# `resend` n'est meme pas importable dans ce banc : le transport factice est
# fourni a l'adaptateur, et la sortie reseau est interdite au niveau socket.
# ============================================================================
APPELS = []
_ECHEC = {"genre": None}


async def faux_transport(params, options):
    APPELS.append({"params": dict(params), "options": dict(options)})
    if _ECHEC["genre"] == "exception":
        raise RuntimeError("HttpClientError simule")
    if _ECHEC["genre"] == "muet":
        return {}
    return {"id": "resend-" + str(len(APPELS))}


_VRAI_FOURNISSEUR = S.P3AI4FournisseurReponse


class FournisseurTrace(_VRAI_FOURNISSEUR):
    """Meme classe, meme garde — seul le transport est remplace."""

    def __init__(self, envoi_autorise=False, transport=None, expediteur=None):
        super().__init__(envoi_autorise=envoi_autorise,
                         transport=faux_transport, expediteur=expediteur)


S.P3AI4FournisseurReponse = FournisseurTrace

class CurseurIterable:
    """Un curseur qu'on peut parcourir avec `async for`.

    Le bouchon partage n'expose que `to_list` : `c3_refus_exprimes` — la
    lecture du registre STOP — parcourt son curseur avec `async for`, et
    echouait donc silencieusement. Elle rendait alors un ensemble vide, et le
    banc concluait « aucun refus » : il ne pouvait tout simplement PAS prouver
    que le STOP bloque. On complete ici, sans toucher au banc partage.
    """

    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, *a, **k):
        return self

    def skip(self, n):
        self._docs = self._docs[n:]
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, n=None):
        return [dict(d) for d in (self._docs[:n] if n else self._docs)]

    def __aiter__(self):
        self._i = iter(list(self._docs))
        return self

    async def __anext__(self):
        try:
            return dict(next(self._i))
        except StopIteration:
            raise StopAsyncIteration


class CollectionIterable(CollectionBouchon):
    def find(self, filtre=None, projection=None, *a, **k):
        return CurseurIterable([dict(d) for d in self.documents if self._ok(d, filtre)])


COACH_A = "coach.a.fictif@exemple.test"
COACH_B = "coach.b.fictif@exemple.test"
JA = _espace["jeton"](COACH_A)
JB = _espace["jeton"](COACH_B)
RequeteFictive = _espace["RequeteFictive"]

ACTION = {"id": "act-etu", "campaign_id": "camp-p3", "coach_id": COACH_A,
          "channel": "email", "target": "info@generique.exemple.test",
          "recipient_key": "ETU-04", "organisations": ["BDE HE-ARC"],
          "prospect_uuids": ["p-etu"], "language": "FR", "statut": "envoye",
          "sent_at": ENVOI, S.P3U2_CHAMP_RFC: "<j0-etu@eu-west-1.amazonses.com>",
          S.P3R1_CHAMP_TOKEN: "3d861143c6def8776acb318c233f9357"}

MESSAGE = {"id": "inb-etu", "coach_id": COACH_A, "action_id": "act-etu",
           "recipient_key": "ETU-04",
           # L'ADRESSE QUI A ECRIT n'est PAS celle a qui la proposition est
           # partie — c'est le cas reel mesure sur ACD Lausanne.
           "from_email": "personne@bde-hearc.exemple.test",
           "to_email": "r-3d861143c6def8776acb318c233f9357@reply.afroboosteur.com",
           "subject": "Re: Proposition de collaboration avec Afroboost",
           "body_text": "Cela nous semble interessant, ca consiste en quoi ?",
           "message_id": "<94099dc3@mail.infomaniak.exemple.test>",
           "received_at": RECU, "statut": "rattache", "read_at": None,
           "traite_at": None}

BROUILLON = {"id": "b-etu", "inbound_id": "inb-etu", "action_id": "act-etu",
             "coach_id": COACH_A, "organisation": "BDE HE-ARC",
             "to_email": "personne@bde-hearc.exemple.test",
             "intention": "question", "langue": "fr", "version": 1,
             "reponse_proposee": "Bonjour, voici ce qu'est Afroboost. Bassi",
             "texte_modele": "Bonjour, voici ce qu'est Afroboost. Bassi",
             "validation_requise": False, "motifs_validation": [],
             "genere_le": "2026-09-05T12:00:00+00:00"}


def base_aip4(flags=None, notes=None, brouillon=BROUILLON, message=None, refus=None):
    b = BaseBouchon([])
    b[S.P3S3_ACTIONS] = CollectionBouchon(S.P3S3_ACTIONS, [dict(ACTION)], uniques=[(("id",), None)])
    b[S.P3U2_COLLECTION] = CollectionBouchon(S.P3U2_COLLECTION, [dict(message or MESSAGE)],
                                             uniques=[(("id",), None)])
    b[S.P3AI_BROUILLONS] = CollectionBouchon(S.P3AI_BROUILLONS,
                                             [dict(brouillon)] if brouillon else [],
                                             uniques=[(("inbound_id",), None)])
    b[S.P3N_COLLECTION] = CollectionBouchon(S.P3N_COLLECTION, notes or [])
    b[S.P3AI4_COLLECTION] = CollectionBouchon(S.P3AI4_COLLECTION, [], uniques=[(("id",), None)])
    b["feature_flags"] = CollectionBouchon("feature_flags",
                                           [{"id": "feature_flags", **(flags or {})}])
    b["subscribers"] = CollectionIterable("subscribers", refus or [])
    b["coaches"] = CollectionBouchon("coaches", [{"email": COACH_A}, {"email": COACH_B}])
    b["coach_auth"] = CollectionBouchon("coach_auth", [])
    S.db = b
    APPELS.clear()
    _ECHEC["genre"] = None
    return b


OUVERT = {"P3_REPONSE_ACTIF": True, "P3_REPONSE_ENVOI_REEL": True}
EMPREINTE = S.p3ai4_empreinte(BROUILLON["reponse_proposee"])


def envoyer(jeton_=None, corps=None):
    return lancer(S.p3ai4_envoyer_reponse(
        "inb-etu", RequeteFictive(jeton_=jeton_ or JA,
                                  corps=corps if corps is not None
                                  else {"confirme": True, "draft_hash": EMPREINTE})))


def apercu(jeton_=None):
    return lancer(S.p3ai4_apercu("inb-etu", RequeteFictive(jeton_=jeton_ or JA)))


# ============================================================================
print("\n1. LES DRAPEAUX — UN SEUL NE SUFFIT JAMAIS")

for flags, intitule in (({}, "aucun drapeau"),
                        ({"P3_REPONSE_ACTIF": True}, "ACTIF seul"),
                        ({"P3_REPONSE_ENVOI_REEL": True}, "ENVOI_REEL seul")):
    _b = base_aip4(flags)
    _r = envoyer()
    verifier("1a. %s -> AUCUN appel au fournisseur" % intitule, len(APPELS) == 0,
             str(len(APPELS)))
    verifier("1b. %s -> l'envoi est refuse, et il le DIT" % intitule,
             _r["envoi"]["send_status"] == S.P3AI4_ECHEC
             and _r["envoi"]["error_code"] == "ENVOI_NON_AUTORISE",
             _r["envoi"].get("error_code"))
    verifier("1c. %s -> aucun statut commercial faux" % intitule,
             _r["statut_commercial"] == S.P3N_STATUT_A_REPONDRE, _r["statut_commercial"])
    verifier("1d. %s -> aucune note d'envoi n'est ecrite" % intitule,
             len(_b[S.P3N_COLLECTION].documents) == 0)

verifier("1e. la garde est PURE et testable seule",
         S.p3ai4_envoi_autorise({}) is False
         and S.p3ai4_envoi_autorise({"P3_REPONSE_ACTIF": True}) is False
         and S.p3ai4_envoi_autorise({"P3_REPONSE_ENVOI_REEL": True}) is False
         and S.p3ai4_envoi_autorise(OUVERT) is True)
verifier("1f. le lot n'utilise JAMAIS les drapeaux du J0",
         "P3_LAUNCH" not in CODE and "P3_RELANCE" not in CODE)
verifier("1g. ni le fournisseur de campagne",
         "P3S3DFournisseurEmail" not in CODE)


# ============================================================================
print("\n2. LES DEUX DRAPEAUX OUVERTS — UN SEUL APPEL, JAMAIS DEUX")

_b = base_aip4(OUVERT)
_r = envoyer()
verifier("2a. UN appel au fournisseur", len(APPELS) == 1, str(len(APPELS)))
verifier("2b. l'envoi est marque envoye", _r["envoi"]["send_status"] == S.P3AI4_ENVOYE)
verifier("2c. il porte l'identifiant du fournisseur",
         bool(_r["envoi"]["provider_message_id"]))
verifier("2d. et sa date d'envoi", bool(_r["envoi"]["sent_at"]))

_avant = len(APPELS)
_rejeu = envoyer()
verifier("2e. REJEU EXACT -> aucun second appel", len(APPELS) == _avant, str(len(APPELS)))
verifier("2f. et la route le dit franchement", _rejeu["deja_envoye"] is True)
_double = envoyer()
verifier("2g. DOUBLE CLIC -> toujours un seul e-mail", len(APPELS) == _avant)
verifier("2h. une seule trace d'envoi existe",
         len(_b[S.P3AI4_COLLECTION].documents) == 1,
         str(len(_b[S.P3AI4_COLLECTION].documents)))

# Un texte CORRIGE est une AUTRE operation — et elle n'est jamais automatique.
_b[S.P3AI_BROUILLONS].documents[0]["reponse_proposee"] = "Texte corrige a la main."
_emp2 = S.p3ai4_empreinte("Texte corrige a la main.")
verifier("2i. une correction change l'empreinte, donc la cle d'envoi",
         _emp2 != EMPREINTE and S.p3ai4_cle_envoi("inb-etu", _emp2)
         != S.p3ai4_cle_envoi("inb-etu", EMPREINTE))
_r2 = envoyer(corps={"confirme": True, "draft_hash": _emp2})
verifier("2j. le texte corrige peut partir, et c'est un SECOND appel",
         len(APPELS) == _avant + 1 and _r2["envoi"]["send_status"] == S.P3AI4_ENVOYE)
verifier("2k. mais il a fallu une nouvelle confirmation explicite",
         '"confirme"' in CODE or "confirme" in CODE)


# ============================================================================
print("\n3. CE QUE LE SERVEUR REFUSE D'ENVOYER")

_b = base_aip4(OUVERT)
for corps, code, pourquoi in (
        ({"draft_hash": EMPREINTE}, 400, "sans confirmation explicite"),
        ({"confirme": False, "draft_hash": EMPREINTE}, 400, "avec une confirmation fausse"),
        ({"confirme": True}, 400, "sans empreinte du brouillon"),
        ({"confirme": True, "draft_hash": "empreinte-perimee"}, 409,
         "avec une empreinte qui ne correspond plus")):
    try:
        envoyer(corps=corps)
        _ok = False
    except HTTPException as e:
        _ok = e.status_code == code
    verifier("3a. %s -> %d" % (pourquoi, code), _ok)
verifier("3b. aucun de ces refus n'a appele le fournisseur", len(APPELS) == 0)

_b = base_aip4(OUVERT, brouillon=None)
try:
    envoyer()
    _ok = False
except HTTPException as e:
    _ok = e.status_code == 409
verifier("3c. sans brouillon -> 409", _ok)

_b = base_aip4(OUVERT, brouillon=dict(BROUILLON, reponse_proposee="   "))
try:
    envoyer(corps={"confirme": True, "draft_hash": S.p3ai4_empreinte("")})
    _ok = False
except HTTPException as e:
    _ok = e.status_code == 409
verifier("3d. un brouillon vide -> 409", _ok)

# BROUILLON PERIME PAR UNE NOTE (AI-P3) : le cas LSN-A3.
_b = base_aip4(OUVERT, notes=[{"id": "n1", "action_id": "act-etu", "type": "appel",
                               "texte": "Appele. J'attends sa proposition.",
                               "status_after": "en_attente",
                               "occurred_at": "2026-09-05T13:00:00+00:00",
                               "created_at": "2026-09-05T13:00:00+00:00"}])
try:
    envoyer()
    _ok = False
except HTTPException as e:
    _ok = e.status_code == 409
verifier("3e. un brouillon PERIME par une note -> 409", _ok)
verifier("3f. et rien n'est parti", len(APPELS) == 0)

# STOP
_b = base_aip4(OUVERT, refus=[{"channel": "email",
                               "value": "personne@bde-hearc.exemple.test",
                               "status": "opted_out"}])
try:
    envoyer()
    _ok = False
except HTTPException as e:
    _ok = e.status_code == 409
verifier("3g. un destinataire au registre STOP -> 409", _ok)
verifier("3h. et rien n'est parti", len(APPELS) == 0)

# ADRESSE INVALIDE
_b = base_aip4(OUVERT, message=dict(MESSAGE, from_email="pas-une-adresse"))
_b[S.P3S3_ACTIONS].documents[0]["target"] = "non plus"
try:
    envoyer()
    _ok = False
except HTTPException as e:
    _ok = e.status_code == 409
verifier("3i. aucune adresse exploitable -> 409, jamais un defaut", _ok)


# ============================================================================
print("\n4. LE DESTINATAIRE EST RESOLU PAR LE SERVEUR")

_b = base_aip4(OUVERT)
_r = envoyer(corps={"confirme": True, "draft_hash": EMPREINTE,
                    # LE NAVIGATEUR MENT : il propose une autre adresse.
                    "to_email": "pirate@exemple.test",
                    "recipient_key": "ZRH-D5"})
verifier("4a. le `to_email` du navigateur est IGNORE",
         APPELS[-1]["params"]["to"] == ["personne@bde-hearc.exemple.test"],
         str(APPELS[-1]["params"]["to"]))
verifier("4b. `recipient_key` fourni n'a AUCUN effet",
         _r["envoi"]["to_email"] == "personne@bde-hearc.exemple.test")
verifier("4c. on repond a QUI A ECRIT, pas a qui la proposition est partie",
         S.p3ai4_destinataire(MESSAGE, ACTION) == "personne@bde-hearc.exemple.test"
         and ACTION["target"] == "info@generique.exemple.test")
verifier("4d. `action.target` reste le dernier recours",
         S.p3ai4_destinataire({"from_email": ""}, ACTION) == "info@generique.exemple.test")
verifier("4e. sans rien d'exploitable : chaine vide, jamais un defaut",
         S.p3ai4_destinataire({}, {}) == "")


# ============================================================================
print("\n5. LE FIL DE DISCUSSION — RIEN N'EST INVENTE")

_ent = S.p3ai4_entetes(MESSAGE, ACTION)
verifier("5a. `In-Reply-To` porte l'identifiant du message RECU",
         _ent.get("In-Reply-To") == "<94099dc3@mail.infomaniak.exemple.test>", str(_ent))
verifier("5b. `References` enchaine notre J0 puis leur reponse",
         _ent.get("References") == "<j0-etu@eu-west-1.amazonses.com> "
                                   "<94099dc3@mail.infomaniak.exemple.test>", str(_ent))
verifier("5b-bis. les CHEVRONS de la RFC 5322 sont presents des deux cotes",
         _ent["In-Reply-To"].startswith("<") and _ent["In-Reply-To"].endswith(">")
         and _ent["References"].count("<") == 2, str(_ent))
verifier("5c. sans identifiant recu, AUCUN `In-Reply-To` n'est fabrique",
         "In-Reply-To" not in S.p3ai4_entetes({"message_id": ""}, ACTION))
verifier("5d. sans rien du tout, aucun en-tete",
         S.p3ai4_entetes({}, {}) == {})
verifier("5e. les en-tetes partent bien au fournisseur",
         APPELS[-1]["params"]["headers"].get("In-Reply-To"))
verifier("5f. l'objet porte UN seul « Re: »",
         S.p3ai4_objet("Re: Proposition") == "Re: Proposition"
         and S.p3ai4_objet("Proposition") == "Re: Proposition"
         and S.p3ai4_objet("Re: Re: Proposition") == "Re: Proposition")
verifier("5g. le jeton de reponse est CONSERVE (P3-R1 intact)",
         "reply.afroboosteur" in str(APPELS[-1]["params"]["reply_to"])
         or "r-3d861143" in str(APPELS[-1]["params"]["reply_to"]),
         str(APPELS[-1]["params"]["reply_to"]))


# ============================================================================
print("\n6. UNE PANNE NE POSE JAMAIS DE STATUT FAUX")

_b = base_aip4(OUVERT)
_ECHEC["genre"] = "exception"
_r = envoyer()
verifier("6a. une panne ambigue -> INDETERMINE, jamais « envoye »",
         _r["envoi"]["send_status"] == S.P3AI4_INDETERMINE, _r["envoi"]["send_status"])
verifier("6b. aucune note d'envoi n'est ecrite",
         len(_b[S.P3N_COLLECTION].documents) == 0)
verifier("6c. le statut commercial n'a pas bouge",
         _r["statut_commercial"] == S.P3N_STATUT_A_REPONDRE)
verifier("6d. et le verrou RESTE pose — un reessai n'enverra pas un second e-mail",
         len(_b[S.P3AI4_COLLECTION].documents) == 1)

_b = base_aip4(OUVERT)
_ECHEC["genre"] = "muet"
_r = envoyer()
verifier("6e. un fournisseur muet -> INDETERMINE",
         _r["envoi"]["send_status"] == S.P3AI4_INDETERMINE)
verifier("6f. aucun statut commercial faux",
         _r["statut_commercial"] == S.P3N_STATUT_A_REPONDRE)


# ============================================================================
print("\n7. APRES UN ENVOI REUSSI — L'ETAT SUIT LA SEULE REGLE QUI EXISTE")

_b = base_aip4(OUVERT)
_r = envoyer()
verifier("7a. une note d'envoi est ecrite", len(_b[S.P3N_COLLECTION].documents) == 1)
_note = _b[S.P3N_COLLECTION].documents[0]
verifier("7b. elle declare EN ATTENTE, jamais TRAITE",
         _note["status_after"] == S.P3N_STATUT_ATTENTE, _note["status_after"])
verifier("7c. le dossier passe donc EN ATTENTE",
         _r["statut_commercial"] == S.P3N_STATUT_ATTENTE, _r["statut_commercial"])
verifier("7d. elle est lisible par un humain, sans identifiant technique",
         "Réponse Afroboost envoyée" in _note["texte"]
         and "act-etu" not in _note["texte"] and "inb-etu" not in _note["texte"])
verifier("7e. un REFUS reste un refus apres un mot de courtoisie",
         S.p3ai4_statut_apres("refus") == S.P3N_STATUT_REFUS
         and S.p3ai4_statut_apres("question") == S.P3N_STATUT_ATTENTE)
verifier("7f. AUCUN second chemin de statut n'est cree",
         "traite_at" not in CODE and "read_at" not in CODE)


# ============================================================================
print("\n8. LA TRACE D'AUDIT")

_t = _b[S.P3AI4_COLLECTION].documents[0]
for champ in ("inbound_id", "action_id", "coach_id", "prospect_uuid", "to_email",
              "subject", "draft_id", "draft_version", "draft_hash", "language",
              "intention", "validation_requise", "approved_at", "approved_by",
              "send_status", "provider", "provider_message_id", "sent_at",
              "error_code", "created_at", "generated_text", "approved_text"):
    verifier("8a. la trace porte `%s`" % champ, champ in _t, str(sorted(_t)[:6]))
verifier("8b. elle distingue ce que l'IA a propose de ce qui est parti",
         _t["generated_text"] == BROUILLON["texte_modele"]
         and _t["approved_text"] == BROUILLON["reponse_proposee"])
verifier("8c. elle ne porte AUCUN secret",
         not any(k in json.dumps(_t) for k in ("p256dh", "auth", "VAPID", "api_key",
                                               "Bearer", "secret")))
verifier("8d. `recipient_key` y est un libelle, pas une cle de jointure",
         _t.get("recipient_key") == "ETU-04" and _t.get("action_id") == "act-etu")


# ============================================================================
print("\n9. VALIDATION HUMAINE OBLIGATOIRE SUR L'ARGENT")

for texte, attendu in (("Nous proposons un tarif de 15 CHF par personne.", True),
                       ("Une commission de 10% serait envisageable.", True),
                       ("Souhaitez-vous un contrat d'exclusivite ?", True),
                       ("Bonjour, voici ce qu'est Afroboost. Bassi", False)):
    _sens = S.p3ai_sujets_sensibles(texte)
    verifier("9a. « %s… » -> validation %s" % (texte[:34], "requise" if attendu else "non requise"),
             bool(_sens) == attendu, str(_sens))

_b = base_aip4(OUVERT, brouillon=dict(BROUILLON, validation_requise=True,
                                      motifs_validation=["paiement"]))
_a = apercu()
verifier("9b. l'apercu remonte l'alerte a l'ecran",
         _a["validation_requise"] is True and _a["motifs_validation"] == ["paiement"])
verifier("9c. mais l'envoi reste possible — c'est un AVERTISSEMENT, pas un blocage",
         _a["envoi_possible"] is True)


# ============================================================================
print("\n10. L'APERCU DIT CE QUI PARTIRAIT, SANS RIEN ENVOYER")

_b = base_aip4({})
_a = apercu()
verifier("10a. AUCUN appel au fournisseur", len(APPELS) == 0)
verifier("10b. il rend l'organisation", _a["organisation"] == "BDE HE-ARC")
verifier("10c. le destinataire RESOLU PAR LE SERVEUR",
         _a["destinataire"] == "personne@bde-hearc.exemple.test")
verifier("10d. l'objet avec un seul « Re: »",
         _a["objet"] == "Re: Proposition de collaboration avec Afroboost", _a["objet"])
verifier("10e. le texte exact et son empreinte",
         _a["texte"] == BROUILLON["reponse_proposee"] and _a["draft_hash"] == EMPREINTE)
verifier("10f. il dit que l'envoi n'est PAS possible (drapeaux fermes)",
         _a["envoi_possible"] is False)
verifier("10g. il dit si le fil sera rattache", _a["fil_rattache"] is True)
verifier("10h. il rend l'etat commercial du dossier",
         _a["statut_commercial"] == S.P3N_STATUT_A_REPONDRE)


# ============================================================================
print("\n11. AUTHENTIFICATION ET CLOISONNEMENT")

_b = base_aip4(OUVERT)
for nom, appel in (("l'envoi", lambda j: S.p3ai4_envoyer_reponse(
                        "inb-etu", RequeteFictive(jeton_=j, corps={"confirme": True,
                                                                   "draft_hash": EMPREINTE}))),
                   ("l'apercu", lambda j: S.p3ai4_apercu(
                        "inb-etu", RequeteFictive(jeton_=j)))):
    try:
        lancer(appel(None)); _f = False
    except HTTPException as e:
        _f = e.status_code in (401, 403)
    verifier("11a. SANS jeton, %s est refuse" % nom, _f)
    try:
        lancer(appel(JB)); _c = False
    except HTTPException as e:
        _c = e.status_code in (403, 404)
    verifier("11b. pour un AUTRE coach, %s est refuse" % nom, _c)
verifier("11c. aucun appel au fournisseur pendant ces refus", len(APPELS) == 0)


# ============================================================================
print("\n12. AUCUN E-MAIL REEL, AUCUNE SORTIE RESEAU")

verifier("12a. le lot n'importe `resend` que derriere les deux drapeaux",
         CODE.count("import resend") == 1)
verifier("12b. et cet import est precede du refus drapeaux fermes",
         CODE.index("ENVOI_NON_AUTORISE") < CODE.index("import resend"))
for _interdit in ("send_push_by_email", "webpush", "p3s3d_executer_campagne",
                  "p3r2_executer_relances"):
    verifier("12c. le lot ne touche pas « %s »" % _interdit, _interdit not in CODE)
verifier("12d. AUCUNE sortie reseau pendant tout le banc", not _TENTATIVES,
         str(_TENTATIVES[:3]))
verifier("12e. tous les appels sont passes par le faux transport",
         all("params" in a for a in APPELS))

_arbre = ast.parse(SRC)
_routes = [n.name for n in ast.walk(_arbre)
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
           and n.name.startswith("p3ai4_")
           and any("api_router" in (ast.get_source_segment(SRC, d) or "")
                   for d in n.decorator_list)]
verifier("12f. le lot ajoute EXACTEMENT 2 routes", len(_routes) == 2, str(_routes))


# ============================================================================
print("\n13. LE FRONT — DEUX GESTES, JAMAIS UN")

ECRAN = io.open(os.path.join(RACINE, "frontend", "src", "components", "coach",
                             "ProspectsSection.js"), encoding="utf-8").read()
verifier("13a. « Valider et envoyer » demande un APERCU, il n'envoie pas",
         "preparerEnvoi" in ECRAN and "apercu-envoi" in ECRAN)
verifier("13b. seul « Confirmer l'envoi » appelle la route d'envoi",
         ECRAN.count("envoyer-reponse") == 1 and "confirmerEnvoi" in ECRAN)
verifier("13c. la confirmation porte l'empreinte du texte AFFICHE",
         "draft_hash: apercu.draft_hash" in ECRAN)
verifier("13d. le bouton est DESACTIVE si l'envoi n'est pas autorise",
         "!carte.apercu.envoi_possible" in ECRAN)
verifier("13e. ... et si le contexte a change",
         "carte.apercu.contexte_obsolete" in ECRAN)
verifier("13f. ... et si c'est deja envoye", "carte.apercu.deja_envoye" in ECRAN)
verifier("13g. « Annuler » n'envoie rien", "annuler-envoi" in ECRAN
         and "majCarte(r.id, { apercu: null })" in ECRAN)
verifier("13h. tout est indexe par carte", "carte.apercu" in ECRAN
         and "carte.envoye" in ECRAN)
verifier("13i. l'ecran ne recalcule NI le destinataire NI l'objet",
         "carte.apercu.destinataire" in ECRAN and "carte.apercu.objet" in ECRAN)


# ============================================================================
_ok = sum(1 for _i, _c, _d in RESULTATS if _c)
_total = len(RESULTATS)
print("\n" + "=" * 78)
print("AI-P4 : %d / %d verifications" % (_ok, _total))
print("Sorties reseau tentees : %d" % len(_TENTATIVES))
print("E-mails REELS envoyes : 0 — le transport est un faux, `resend` jamais importe")
if _ok != _total:
    print("\nECHECS :")
    for _i, _c, _d in RESULTATS:
        if not _c:
            print("  - %s%s" % (_i, (" -> " + _d) if _d else ""))
print("=" * 78)
sys.exit(0 if _ok == _total else 1)
