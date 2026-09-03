#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3-R4 — LE CONTENU REEL DES REPONSES ENTRANTES, SANS UN SEUL E-MAIL.

POURQUOI CE BANC EXISTE
==============================================================================
La correlation marchait deja : la premiere vraie reponse de la campagne P3
(SalsaRica, 03/09) a retrouve son action seule, avec une confiance de 100, et a
annule ses deux relances. Mais son `body_text` etait VIDE. On savait qu'un
prospect avait repondu ; on ne savait pas QUOI. Le webhook `email.received` de
Resend ne porte pas le corps — par conception.

CE QUE CE FICHIER PROUVE
==============================================================================
  * A. un `email.received` avec `text` -> le corps est conserve ;
  * B. un `email.received` avec `html` seulement -> un texte lisible est extrait
       et le HTML source est garde ;
  * C. le fournisseur en panne NE CASSE PAS la correlation : message stocke,
       `replied_at` ecrit, J+3/J+7 annules, et seul le CONTENU porte l'echec ;
  * D. un rejeu du meme webhook ne cree qu'UN message et ne rejoue pas le metier ;
  * E. un rejeu COMPLETE un corps precedemment manquant ;
  * F. un contenu deja correct n'est JAMAIS ecrase ;
  * G. AUCUN champ redige par Afroboost (`j0_message`, `message_j3`,
       `message_j7`, `interested_message`) ne peut devenir un corps entrant ;
  * H. un `email_id` absent est un cas normal, pas une panne ;
  * I. une reponse arrivee ENTRE J+3 et J+7 garde le comportement existant ;
  * J. le rattrapage simule n'ecrit rien, et le rattrapage reel est idempotent ;
  * l'historique cite est SEPARE de la nouvelle reponse ;
  * aucune socket, aucun e-mail, aucune route ajoutee.
"""
import ast
import asyncio
import io
import json
import os
import socket
import sys
import types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

RESULTATS = []


def verifier(intitule, condition, detail=""):
    RESULTATS.append((intitule, bool(condition), detail))
    print("  %-6s %s" % ("OK  " if condition else "ECHEC", intitule))
    if detail and not condition:
        print("           -> %s" % detail)
    return bool(condition)


# ---------------------------------------------------------------------------
# AUCUNE SORTIE RESEAU. Ce lot appelle un fournisseur : c'est precisement pour
# cela qu'on coupe le reseau AVANT l'import. Un banc qui joindrait la vraie API
# de Resend ne prouverait pas notre cablage, il testerait Resend.
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# LE FAUX SDK RESEND, pose AVANT l'import du serveur.
#
# `Emails.Receiving.get` est pilote par `_RECU` : il rend un objet, ou il leve.
# On ne recopie NI la crypto de Resend, NI son transport — on eprouve ce que
# NOTRE code fait de ce qu'il recoit, et de ce qu'il ne recoit pas.
# ---------------------------------------------------------------------------
_APPELS_GET = []
_APPELS_LISTE = []
_RECU = {"reponse": None, "leve": None}
_LISTE = {"donnees": [], "leve": None}


class _FauxReceiving:
    @classmethod
    def get(cls, email_id):
        _APPELS_GET.append(email_id)
        if _RECU["leve"]:
            raise _RECU["leve"]
        return _RECU["reponse"]

    @classmethod
    def list(cls, params=None):
        _APPELS_LISTE.append(params)
        if _LISTE["leve"]:
            raise _LISTE["leve"]
        return {"object": "list", "has_more": False, "data": list(_LISTE["donnees"])}


_ENVOIS = []


class _FauxWebhooks:
    @classmethod
    def verify(cls, options):
        return None


_faux_resend = types.ModuleType("resend")
_faux_resend.Webhooks = _FauxWebhooks
_faux_resend.Emails = types.SimpleNamespace(
    send=lambda *a, **k: _ENVOIS.append((a, k)) or {"id": "jamais"},
    Receiving=_FauxReceiving)
sys.modules["resend"] = _faux_resend

SECRET = "secret-de-banc-p3r4-sans-aucun-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ["RESEND_API_KEY"] = "re_faux_de_banc_p3r4"
os.environ["RESEND_WEBHOOK_SECRET"] = "whsec_valeur_de_banc_jamais_en_production"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p3r4-inexistant:27017")

import jwt as _jwt          # noqa: E402
import api.server as S      # noqa: E402
from fastapi import HTTPException  # noqa: E402

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
BLOC_R4 = SRC[SRC.index("# P3-R4 — LE CONTENU REEL DES REPONSES ENTRANTES"):
              SRC.index("# CAL-1 — UN SEUL CALENDRIER")]
# LE CODE SEUL, SANS LES COMMENTAIRES. L'en-tete du lot NOMME les quatre champs
# Afroboost pour dire qu'ils sont interdits : c'est de la prose, et l'interdire
# obligerait a documenter la regle sans pouvoir l'ecrire. Ce qui doit rester
# introuvable, c'est un USAGE — `a.get("message_j3")` dans une instruction.
CODE_R4 = "\n".join(l for l in BLOC_R4.splitlines() if not l.lstrip().startswith("#"))

COACH_A = "coach.a.fictif@exemple.test"
COACH_B = "coach.b.fictif@exemple.test"
INSTANT = "2026-08-31T18:26:57.951583+00:00"
ENVOI = "2026-09-01T09:00:00+00:00"
RECU = "2026-09-01T11:00:00+00:00"

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

PROPRIO = S.P3U3_COACH_PAR_DEFAUT
JETON = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
ADRESSE_REPONSE = "r-%s@reply.afroboosteur.com" % JETON
ID_RECU = "88268b21-13be-4b73-9ee6-437fe86396e4"
ID_RECU_2 = "12345678-90ab-4cde-8f01-234567890abc"

# LES QUATRE FAUX TEXTES. Ce sont des champs REDIGES PAR AFROBOOST : ils ne
# doivent JAMAIS ressortir comme corps d'un message entrant. Si un jour
# quelqu'un rajoute un repli « si le corps manque, prends le message prepare »,
# c'est ce banc qui doit hurler.
FAUX = {"j0": "FAUX TEXTE J0", "j3": "FAUX TEXTE J3",
        "j7": "FAUX TEXTE J7", "interet": "FAUX TEXTE INTERESSE"}
VRAI = "VRAIE REPONSE PROSPECT"

ENTETES_OK = {"svix-id": "msg_2abc", "svix-timestamp": "1789000000",
              "svix-signature": "v1,QUJD"}


class RequeteWebhook:
    def __init__(self, corps, entetes=None):
        self._corps = corps if isinstance(corps, bytes) else json.dumps(corps).encode()
        self.headers = dict(entetes if entetes is not None else ENTETES_OK)

    async def body(self):
        return self._corps


def action(**extra):
    a = {"id": "act-zrh-d5", "campaign_id": "camp-1", "coach_id": PROPRIO,
         "channel": "email", "target": "info@ecole.exemple.test",
         "recipient_key": "ZRH-D5", "language": "DE",
         "organisations": ["Ecole de danse fictive"], "prospect_ids": ["ZRH-D5"],
         "statut": "envoye", "execution_type": "AUTO",
         "sent_at": ENVOI, "provider": "resend",
         "provider_message_id": "prov-zrh-d5",
         S.P3R1_CHAMP_TOKEN: JETON,
         "j3_due_at": "2026-09-04T09:00:00+00:00",
         "j7_due_at": "2026-09-08T09:00:00+00:00",
         # Les champs Afroboost, bien remplis : le piege est arme.
         "message_j0": FAUX["j0"], "message_j3": FAUX["j3"], "message_j7": FAUX["j7"]}
    a.update(extra)
    return a


def fiche(**extra):
    f = {"id": "fiche-zrh-d5", "coach_id": PROPRIO, "ref": "ZRH-D5",
         "organisation_name": "Ecole de danse fictive", "status": "contacte",
         "j0_message": FAUX["j0"], "j3_message": FAUX["j3"],
         "j7_message": FAUX["j7"], "interested_message": FAUX["interet"]}
    f.update(extra)
    return f


def base_neuve(actions=None, fiches=None, entrants=None):
    b = BaseBouchon([dict(f) for f in (fiches or [])])
    b[S.P3S3_ACTIONS] = CollectionBouchon(
        S.P3S3_ACTIONS, [dict(a) for a in (actions or [])], uniques=[(("id",), None)])
    b[S.P3U2_COLLECTION] = CollectionBouchon(
        S.P3U2_COLLECTION, [dict(d) for d in (entrants or [])],
        uniques=[(("coach_id", "dedupe_key"), {"dedupe_key": {"$type": "string"}})])
    b["subscribers"] = CollectionBouchon("subscribers", [], uniques=[(("channel", "value")
                                                                      , None)])
    S.db = b
    return b


def evenement(email_id=ID_RECU, message_id="<reponse-salsa@ecole.exemple.test>",
              **donnees):
    d = {"email_id": email_id, "from": "info@ecole.exemple.test",
         "to": [ADRESSE_REPONSE], "subject": "Re: Proposition de collaboration",
         "created_at": RECU, "message_id": message_id,
         "headers": {}}
    d.update(donnees)
    return {"type": "email.received", "id": "evt_r4_001", "data": d}


def recu(text=None, html=None):
    """Ce que l'API Receiving rendrait. Un dictionnaire, comme le vrai."""
    return {"id": ID_RECU, "from": "info@ecole.exemple.test",
            "to": [ADRESSE_REPONSE], "subject": "Re: Proposition de collaboration",
            "created_at": RECU, "text": text, "html": html,
            "message_id": "<reponse-salsa@ecole.exemple.test>", "headers": {}}


def poser_recu(text=None, html=None, leve=None):
    _RECU["reponse"] = recu(text=text, html=html)
    _RECU["leve"] = leve
    del _APPELS_GET[:]


# Le texte de reference, avec sa citation : c'est la forme REELLE d'une reponse
# Apple Mail — la nouvelle reponse, puis notre propre J0 recopie dessous.
TEXTE_AVEC_CITATION = (
    "Hola Bassi\n\nDanke fuer deine Anfrage, aber wir sind nicht interessiert\n\n"
    "Freundliche Gruesse\nSonja\n\n"
    "> Am 03.09.2026 um 12:57 schrieb Afroboost <notifications@afroboost.com>:\n"
    "> \n> " + FAUX["j0"] + "\n")


# ============================================================================
print("\n1. LA COUPE DE CITATION — la reponse d'un cote, notre J0 de l'autre")

_c = S.p3r4_couper_citation(TEXTE_AVEC_CITATION)
verifier("1a. la nouvelle reponse est isolee", _c["nouveau"].startswith("Hola Bassi"))
verifier("1b. la signature du prospect RESTE dans la reponse",
         "Sonja" in _c["nouveau"])
verifier("1c. notre J0 recopie part dans l'historique cite",
         FAUX["j0"] in _c["cite"] and FAUX["j0"] not in _c["nouveau"])
verifier("1d. l'historique n'est pas jete", _c["cite"].strip() != "")
for etiquette, entete in (
        ("anglais", "On Sep 3, 2026, at 12:57, Afroboost wrote:"),
        ("francais", "Le 3 sept. 2026 a 12:57, Afroboost a ecrit :"),
        ("Outlook", "-----Original Message-----"),
        ("en-tete De:", "De: Afroboost <notifications@afroboost.com>"),
        ("separateur", "_" * 30)):
    _d = S.p3r4_couper_citation("Reponse courte.\n\n%s\n%s" % (entete, FAUX["j0"]))
    verifier("1e. marqueur %s reconnu" % etiquette,
             _d["nouveau"] == "Reponse courte." and FAUX["j0"] in _d["cite"],
             repr(_d["nouveau"]))
_e = S.p3r4_couper_citation("")
verifier("1f. un texte vide ne casse rien", _e == {"nouveau": "", "cite": ""})
_f = S.p3r4_couper_citation("Aucune citation ici.")
verifier("1g. sans marqueur, tout est nouveau",
         _f["nouveau"] == "Aucune citation ici." and _f["cite"] == "")


# ============================================================================
print("\n2. L'IDENTIFIANT DU MESSAGE RECU — un UUID, jamais autre chose")

verifier("2a. `data.email_id` est lu",
         S.p3r4_identifiant_recu(evenement()) == ID_RECU)
verifier("2b. l'identifiant d'EVENEMENT `msg_…` est REFUSE",
         S.p3r4_identifiant_recu({"type": "email.received",
                                  "data": {"id": "msg_3IoederPGUp3VAYEYTLAUsztIn1"}}) == "",
         "c'est le 422 « must be a valid UUID » deja paye")
verifier("2c. `data.id` est accepte s'il a la bonne forme",
         S.p3r4_identifiant_recu({"data": {"id": ID_RECU_2}}) == ID_RECU_2)
verifier("2d. un identifiant absent rend une chaine vide, pas une erreur",
         S.p3r4_identifiant_recu({"data": {}}) == ""
         and S.p3r4_identifiant_recu(None) == "")
verifier("2e. la validation refuse les formes voisines",
         not S.p3r4_identifiant_valide(ID_RECU + "x")
         and not S.p3r4_identifiant_valide("88268b2113be4b739ee6437fe86396e4")
         and S.p3r4_identifiant_valide(ID_RECU.upper()))


# ============================================================================
print("\n3. A — UN `email.received` AVEC `text`")

base_neuve(actions=[action()], fiches=[fiche()])
poser_recu(text=TEXTE_AVEC_CITATION)
_r = lancer(S.p3u3_webhook_resend(RequeteWebhook(evenement())))
_doc = lancer(S.db[S.P3U2_COLLECTION].find_one({}))
_act = lancer(S.db[S.P3S3_ACTIONS].find_one({"id": "act-zrh-d5"}))
verifier("3a. le message est stocke", _r.get("stocke") is True)
verifier("3b. le corps REEL est conserve",
         _doc["body_text"].startswith("Hola Bassi"), repr(_doc["body_text"])[:120])
verifier("3c. l'historique cite est conserve A PART",
         FAUX["j0"] in _doc["body_quoted"] and FAUX["j0"] not in _doc["body_text"])
verifier("3d. la source est `text`", _doc["contenu_source"] == "text")
verifier("3e. le contenu est marque recupere", _doc["contenu_recupere"] is True)
verifier("3f. aucune erreur n'est notee", _doc["contenu_erreur"] == "")
verifier("3g. l'`email_id` du fournisseur est enfin GARDE",
         _doc["provider_email_id"] == ID_RECU)
verifier("3h. le HTML n'est pas stocke quand `text` suffit", _doc["body_html"] == "")
verifier("3i. la correlation est intacte (jeton, confiance 100)",
         _doc["matching_method"] == S.P3U2_METHODE_TOKEN
         and _doc["matching_confidence"] == 100
         and _doc["statut"] == S.P3U2_STATUT_RATTACHE)
verifier("3j. `replied_at` est ecrit sur l'action", _act.get("replied_at") == RECU)
verifier("3k. les deux relances sont annulees",
         _act.get("j3_annule_motif") == "reponse recue"
         and _act.get("j7_annule_motif") == "reponse recue")
verifier("3l. la fiche passe a `repondu`",
         lancer(S.db[S.P3S1_COLLECTION].find_one({"ref": "ZRH-D5"}))["status"] == "repondu")
verifier("3m. l'API Receiving a ete appelee AVEC l'UUID", _APPELS_GET == [ID_RECU])


# ============================================================================
print("\n4. B — UN `email.received` AVEC `html` SEULEMENT")

base_neuve(actions=[action()], fiches=[fiche()])
poser_recu(text=None,
           html="<html><body><div>Gruezi Bassi</div><div>Wir sind dabei!</div>"
                "<blockquote>Am 03.09.2026 schrieb Afroboost:<br>"
                + FAUX["j0"] + "</blockquote></body></html>")
lancer(S.p3u3_webhook_resend(RequeteWebhook(evenement())))
_doc = lancer(S.db[S.P3U2_COLLECTION].find_one({}))
verifier("4a. un texte lisible est extrait du HTML",
         _doc["body_text"].startswith("Gruezi Bassi"), repr(_doc["body_text"])[:120])
verifier("4b. la source est `html`", _doc["contenu_source"] == "html")
verifier("4c. le HTML source est conserve pour re-extraction",
         _doc["body_html"].startswith("<html"))
verifier("4d. la citation est coupee AUSSI dans le HTML converti",
         FAUX["j0"] not in _doc["body_text"], repr(_doc["body_text"])[:160])
verifier("4e. le contenu est marque recupere", _doc["contenu_recupere"] is True)
verifier("4f. aucune balise ne subsiste dans le texte", "<" not in _doc["body_text"])


# ============================================================================
print("\n5. C — LE FOURNISSEUR EN PANNE NE CASSE PAS LA CORRELATION")

base_neuve(actions=[action()], fiches=[fiche()])
poser_recu(leve=RuntimeError("503 Service Unavailable"))
_r = lancer(S.p3u3_webhook_resend(RequeteWebhook(evenement())))
_doc = lancer(S.db[S.P3U2_COLLECTION].find_one({}))
_act = lancer(S.db[S.P3S3_ACTIONS].find_one({"id": "act-zrh-d5"}))
_fic = lancer(S.db[S.P3S1_COLLECTION].find_one({"ref": "ZRH-D5"}))
verifier("5a. le message est stocke QUAND MEME", _r.get("stocke") is True)
verifier("5b. la correlation tient (jeton, confiance 100)",
         _doc["matching_method"] == S.P3U2_METHODE_TOKEN
         and _doc["matching_confidence"] == 100)
verifier("5c. `replied_at` est ecrit QUAND MEME", _act.get("replied_at") == RECU)
verifier("5d. les relances sont annulees QUAND MEME",
         _act.get("j3_annule_le") and _act.get("j7_annule_le"))
verifier("5e. la fiche est `repondu` QUAND MEME", _fic["status"] == "repondu")
verifier("5f. SEUL le contenu porte l'echec", _doc["contenu_recupere"] is False)
verifier("5g. le motif nomme la panne du fournisseur",
         _doc["contenu_erreur"].startswith(S.P3R4_ERREUR_FOURNISSEUR),
         _doc["contenu_erreur"])
verifier("5h. le corps est vide, PAS rempli d'un texte Afroboost",
         _doc["body_text"] == ""
         and not any(v in json.dumps(_doc) for v in FAUX.values()))
verifier("5i. la route repond 200, sans exception",
         _r.get("recu") is True and _r.get("type") == "email.received")

# Le corps vide chez le fournisseur : un `text` et un `html` tous deux absents.
base_neuve(actions=[action()], fiches=[fiche()])
poser_recu(text="", html="")
lancer(S.p3u3_webhook_resend(RequeteWebhook(evenement())))
_doc = lancer(S.db[S.P3U2_COLLECTION].find_one({}))
verifier("5j. un corps vide chez le fournisseur est dit tel quel",
         _doc["contenu_recupere"] is False
         and _doc["contenu_erreur"] == S.P3R4_CORPS_VIDE, _doc["contenu_erreur"])


# ============================================================================
print("\n6. D — LE REJEU DU MEME WEBHOOK")

base_neuve(actions=[action()], fiches=[fiche()])
poser_recu(text=TEXTE_AVEC_CITATION)
lancer(S.p3u3_webhook_resend(RequeteWebhook(evenement())))
_premier = lancer(S.db[S.P3S3_ACTIONS].find_one({"id": "act-zrh-d5"}))
_annule_j3 = _premier.get("j3_annule_le")
_r2 = lancer(S.p3u3_webhook_resend(RequeteWebhook(evenement())))
_r3 = lancer(S.p3u3_webhook_resend(RequeteWebhook(evenement())))
_tous = lancer(S.db[S.P3U2_COLLECTION].find({}).to_list(50))
_act = lancer(S.db[S.P3S3_ACTIONS].find_one({"id": "act-zrh-d5"}))
verifier("6a. trois passages, UN SEUL message logique", len(_tous) == 1, str(len(_tous)))
verifier("6b. les rejeux sont annonces comme doublons",
         _r2.get("doublon") is True and _r3.get("doublon") is True)
verifier("6c. `replied_at` reste ecrit UNE FOIS", _act.get("replied_at") == RECU)
verifier("6d. les annulations ne sont pas rejouees",
         _act.get("j3_annule_le") == _annule_j3)
verifier("6e. le contenu deja recupere n'est pas duplique",
         _tous[0]["body_text"].count("Hola Bassi") == 1)
verifier("6f. rien a completer sur un message deja complet",
         _r2.get("contenu_complete") is False)


# ============================================================================
print("\n7. E — UN REJEU COMPLETE UN CORPS PRECEDEMMENT MANQUANT")

base_neuve(actions=[action()], fiches=[fiche()])
poser_recu(leve=RuntimeError("timeout"))
lancer(S.p3u3_webhook_resend(RequeteWebhook(evenement())))
_avant = lancer(S.db[S.P3U2_COLLECTION].find_one({}))
_act_avant = lancer(S.db[S.P3S3_ACTIONS].find_one({"id": "act-zrh-d5"}))
poser_recu(text=TEXTE_AVEC_CITATION)          # le fournisseur revient
_r2 = lancer(S.p3u3_webhook_resend(RequeteWebhook(evenement())))
_apres = lancer(S.db[S.P3U2_COLLECTION].find_one({}))
_act_apres = lancer(S.db[S.P3S3_ACTIONS].find_one({"id": "act-zrh-d5"}))
_tous = lancer(S.db[S.P3U2_COLLECTION].find({}).to_list(50))
verifier("7a. le premier passage laisse le corps vide", _avant["body_text"] == "")
verifier("7b. le rejeu est bien vu comme un doublon", _r2.get("doublon") is True)
verifier("7c. le rejeu COMPLETE le corps", _r2.get("contenu_complete") is True)
verifier("7d. le corps reel est desormais en base",
         _apres["body_text"].startswith("Hola Bassi"))
verifier("7e. l'historique cite est pose aussi", FAUX["j0"] in _apres["body_quoted"])
verifier("7f. le contenu est marque recupere", _apres["contenu_recupere"] is True)
verifier("7g. l'erreur precedente est effacee", _apres["contenu_erreur"] == "")
verifier("7h. la date de completion est notee", bool(_apres.get("contenu_complete_le")))
verifier("7i. aucun second message n'est cree", len(_tous) == 1)
verifier("7j. l'identite du message ne change pas", _apres["id"] == _avant["id"])
verifier("7k. `replied_at` n'est PAS reecrit",
         _act_apres.get("replied_at") == _act_avant.get("replied_at"))
verifier("7l. les annulations ne sont PAS rejouees",
         _act_apres.get("j3_annule_le") == _act_avant.get("j3_annule_le"))


# ============================================================================
print("\n8. F — UN CONTENU DEJA CORRECT N'EST JAMAIS ECRASE")

base_neuve(actions=[action()], fiches=[fiche()])
poser_recu(text="Premiere lecture, la bonne.")
lancer(S.p3u3_webhook_resend(RequeteWebhook(evenement())))
_doc = lancer(S.db[S.P3U2_COLLECTION].find_one({}))
_id_doc = _doc["id"]
verifier("8a. le premier corps lisible est pose",
         _doc["body_text"] == "Premiere lecture, la bonne.")
_ecrit = lancer(S.p3r4_completer(_id_doc, {"contenu_recupere": True,
                                           "body_text": "Deuxieme lecture, moins bonne.",
                                           "contenu_source": "html"}))
_doc = lancer(S.db[S.P3U2_COLLECTION].find_one({"id": _id_doc}))
verifier("8b. une seconde lecture n'ecrit RIEN", _ecrit is False)
verifier("8c. le corps d'origine est intact",
         _doc["body_text"] == "Premiere lecture, la bonne.")
_ecrit_vide = lancer(S.p3r4_completer(_id_doc, {"contenu_recupere": False,
                                                "body_text": ""}))
verifier("8d. un contenu NON recupere n'ecrase jamais", _ecrit_vide is False)
_doc = lancer(S.db[S.P3U2_COLLECTION].find_one({"id": _id_doc}))
verifier("8e. le corps est toujours la apres une tentative vide",
         _doc["body_text"] == "Premiere lecture, la bonne."
         and _doc["contenu_recupere"] is True)


# ============================================================================
print("\n9. G — AUCUN TEXTE AFROBOOST NE PEUT DEVENIR UN CORPS ENTRANT")
# LE BANC ANTI-CONFUSION. L'action porte les quatre faux textes, la fiche
# aussi, et le fournisseur dit une seule chose : VRAI. Si demain quelqu'un
# ajoute « si le corps manque, prends le message prepare », ces trois
# verifications tombent.

base_neuve(actions=[action()], fiches=[fiche()])
poser_recu(text=VRAI)
lancer(S.p3u3_webhook_resend(RequeteWebhook(evenement())))
_doc = lancer(S.db[S.P3U2_COLLECTION].find_one({}))
_json = json.dumps(_doc, ensure_ascii=False)
verifier("9a. le corps est EXACTEMENT ce que le fournisseur a dit",
         _doc["body_text"] == VRAI, repr(_doc["body_text"]))
verifier("9b. aucun des quatre faux textes n'entre dans le message",
         not any(v in _json for v in FAUX.values()), _json[:200])
for cle, valeur in FAUX.items():
    verifier("9c. `%s` reste hors du message entrant" % cle, valeur not in _json)

# Meme piege, mais fournisseur MUET : c'est le cas dangereux.
base_neuve(actions=[action()], fiches=[fiche()])
poser_recu(leve=RuntimeError("panne"))
lancer(S.p3u3_webhook_resend(RequeteWebhook(evenement())))
_doc = lancer(S.db[S.P3U2_COLLECTION].find_one({}))
_json = json.dumps(_doc, ensure_ascii=False)
verifier("9d. fournisseur muet : le corps reste VIDE", _doc["body_text"] == "")
verifier("9e. fournisseur muet : AUCUN repli sur un texte Afroboost",
         not any(v in _json for v in FAUX.values()), _json[:200])
verifier("9f. le CODE du lot ne lit AUCUN champ commercial Afroboost",
         not any(c in CODE_R4 for c in ("message_j0", "message_j3", "message_j7",
                                        "interested_message", "j0_message",
                                        "j3_message", "j7_message")),
         "un usage, pas une mention en commentaire")
verifier("9g. et l'interdiction est bien ECRITE dans le lot",
         all(c in BLOC_R4 for c in ("message_j3", "interested_message")),
         "la regle doit rester documentee la ou elle s'applique")


# ============================================================================
print("\n10. H — UN `email_id` ABSENT EST UN CAS NORMAL")

base_neuve(actions=[action()], fiches=[fiche()])
poser_recu(text="jamais lu")
_r = lancer(S.p3u3_webhook_resend(RequeteWebhook(evenement(email_id=None))))
_doc = lancer(S.db[S.P3U2_COLLECTION].find_one({}))
_act = lancer(S.db[S.P3S3_ACTIONS].find_one({"id": "act-zrh-d5"}))
verifier("10a. le message est stocke", _r.get("stocke") is True)
verifier("10b. la correlation tient", _act.get("replied_at") == RECU)
verifier("10c. le motif dit que l'identifiant manque",
         _doc["contenu_erreur"] == S.P3R4_SANS_IDENTIFIANT, _doc["contenu_erreur"])
verifier("10d. le fournisseur n'est meme pas appele", _APPELS_GET == [], str(_APPELS_GET))
verifier("10e. `provider_email_id` est nul, jamais inventé",
         _doc["provider_email_id"] is None)

# L'identifiant d'evenement `msg_…` ne doit pas etre pris pour un `email_id`.
base_neuve(actions=[action()], fiches=[fiche()])
poser_recu(text="jamais lu")
_ev = evenement(email_id=None)
_ev["data"]["id"] = "msg_3IoederPGUp3VAYEYTLAUsztIn1"
lancer(S.p3u3_webhook_resend(RequeteWebhook(_ev)))
verifier("10f. l'identifiant d'EVENEMENT n'est jamais envoye a l'API",
         _APPELS_GET == [], str(_APPELS_GET))


# ============================================================================
print("\n11. I — UNE REPONSE ENTRE J+3 ET J+7")
# Le J+3 est DEJA parti ; seul le J+7 reste a annuler. Ce comportement vient
# de U2 et ne doit pas changer d'un iota parce qu'on lit maintenant le corps.

base_neuve(actions=[action(j3_sent_at="2026-09-04T09:05:00+00:00")], fiches=[fiche()])
poser_recu(text=VRAI)
lancer(S.p3u3_webhook_resend(RequeteWebhook(evenement())))
_act = lancer(S.db[S.P3S3_ACTIONS].find_one({"id": "act-zrh-d5"}))
_doc = lancer(S.db[S.P3U2_COLLECTION].find_one({}))
verifier("11a. le J+3 deja parti reste parti",
         _act.get("j3_sent_at") == "2026-09-04T09:05:00+00:00")
verifier("11b. `replied_at` est ecrit", _act.get("replied_at") == RECU)
verifier("11c. le J+7 est annule", _act.get("j7_annule_motif") == "reponse recue")
verifier("11d. le corps reel est la aussi", _doc["body_text"] == VRAI)
_verdict = S.p3r2_garde_relance(_act, {"etat": "approuvee"}, "j7",
                                maintenant="2026-09-08T09:00:00+00:00")
verifier("11e. la garde de relance refuse desormais le J+7",
         _verdict["autorise"] is False, _verdict["code"])


# ============================================================================
print("\n12. J — LE RATTRAPAGE : simule d'abord, idempotent ensuite")

HISTORIQUE = {"id": "msg-historique-1", "coach_id": PROPRIO,
              "campaign_id": "camp-1", "action_id": "act-zrh-d5",
              "recipient_key": "ZRH-D5", "from_email": "info@ecole.exemple.test",
              "to_email": ADRESSE_REPONSE, "subject": "Re: Proposition",
              "body_text": "", "received_at": RECU,
              "message_id": "<reponse-salsa@ecole.exemple.test>",
              "dedupe_key": "mid:reponse-salsa@ecole.exemple.test",
              "matching_method": S.P3U2_METHODE_TOKEN, "matching_confidence": 100,
              "statut": S.P3U2_STATUT_RATTACHE, "processed_at": RECU}
COMPLET = dict(HISTORIQUE, id="msg-deja-complet", dedupe_key="mid:autre@ecole.test",
               body_text="Deja lisible", contenu_recupere=True,
               contenu_source="text", provider_email_id=ID_RECU_2)

base_neuve(actions=[action(replied_at=RECU)], fiches=[fiche(status="repondu")],
           entrants=[dict(HISTORIQUE), dict(COMPLET)])
_cands = lancer(S.p3r4_candidats_rattrapage())
verifier("12a. un seul candidat : celui dont le corps manque",
         len(_cands) == 1 and _cands[0]["id"] == "msg-historique-1",
         str([c["id"] for c in _cands]))
verifier("12b. le candidat dit que son `email_id` manque",
         _cands[0]["identifiant_present"] is False)
verifier("12c. un message deja lisible n'est PAS candidat",
         "msg-deja-complet" not in [c["id"] for c in _cands])

# Le fournisseur retrouve l'identifiant par correspondance stricte.
_LISTE["donnees"] = [{"id": ID_RECU, "from": "info@ecole.exemple.test",
                      "to": [ADRESSE_REPONSE], "created_at": RECU,
                      "subject": "Re: Proposition"},
                     {"id": ID_RECU_2, "from": "autre@ailleurs.exemple.test",
                      "to": ["r-inconnu@reply.afroboosteur.com"],
                      "created_at": "2026-09-02T10:00:00+00:00", "subject": "x"}]
_LISTE["leve"] = None
poser_recu(text=TEXTE_AVEC_CITATION)

_ecritures_avant = S.db[S.P3U2_COLLECTION].ecritures
_sim = lancer(S.p3r4_rattraper(simulation=True))
verifier("12d. la simulation voit 1 candidat et 1 traitement",
         _sim["candidats"] == 1 and _sim["traites"] == 1, json.dumps(_sim["resultats"]))
verifier("12e. la simulation N'ECRIT RIEN",
         S.db[S.P3U2_COLLECTION].ecritures == _ecritures_avant)
verifier("12f. la simulation montre un apercu du vrai texte",
         _sim["resultats"][0]["apercu"].startswith("Hola Bassi"))
verifier("12g. la simulation a retrouve l'identifiant unique",
         _sim["resultats"][0]["provider_email_id"] == ID_RECU)
verifier("12h. le corps est toujours vide en base",
         lancer(S.db[S.P3U2_COLLECTION].find_one({"id": "msg-historique-1"}))["body_text"] == "")

_reel = lancer(S.p3r4_rattraper(simulation=False))
_doc = lancer(S.db[S.P3U2_COLLECTION].find_one({"id": "msg-historique-1"}))
_act = lancer(S.db[S.P3S3_ACTIONS].find_one({"id": "act-zrh-d5"}))
verifier("12i. le rattrapage reel complete le corps",
         _doc["body_text"].startswith("Hola Bassi"))
verifier("12j. l'historique cite est pose", FAUX["j0"] in _doc["body_quoted"])
verifier("12k. l'`email_id` retrouve est enregistre",
         _doc["provider_email_id"] == ID_RECU)
verifier("12l. `replied_at` de l'action n'est PAS touche", _act.get("replied_at") == RECU)
verifier("12m. aucune relance n'est touchee",
         _act.get("j3_sent_at") is None and _act.get("j7_sent_at") is None)
verifier("12n. la fiche n'est pas retouchee",
         lancer(S.db[S.P3S1_COLLECTION].find_one({"ref": "ZRH-D5"}))["status"] == "repondu")

_second = lancer(S.p3r4_rattraper(simulation=False))
verifier("12o. le second passage reel ne trouve plus rien a faire",
         _second["candidats"] == 0 and _second["traites"] == 0,
         json.dumps(_second["resultats"]))
verifier("12p. aucun message n'a ete cree par le rattrapage",
         len(lancer(S.db[S.P3U2_COLLECTION].find({}).to_list(50))) == 2)

# Deux candidats identiques chez le fournisseur : on ne devine pas.
base_neuve(actions=[action(replied_at=RECU)], fiches=[fiche(status="repondu")],
           entrants=[dict(HISTORIQUE)])
_LISTE["donnees"] = [{"id": ID_RECU, "from": "info@ecole.exemple.test",
                      "to": [ADRESSE_REPONSE], "created_at": RECU},
                     {"id": ID_RECU_2, "from": "info@ecole.exemple.test",
                      "to": [ADRESSE_REPONSE], "created_at": RECU}]
_amb = lancer(S.p3r4_rattraper(simulation=False))
_doc = lancer(S.db[S.P3U2_COLLECTION].find_one({"id": "msg-historique-1"}))
verifier("12q. deux correspondances -> AUCUNE ecriture",
         _amb["traites"] == 0 and _doc["body_text"] == "")
verifier("12r. le motif est l'ambiguite, pas une panne",
         _amb["resultats"][0]["motif"] == S.P3R4_AMBIGU,
         _amb["resultats"][0]["motif"])

# Le plafond est respecte.
base_neuve(actions=[action(replied_at=RECU)], fiches=[fiche(status="repondu")],
           entrants=[dict(HISTORIQUE),
                     dict(HISTORIQUE, id="msg-historique-2",
                          dedupe_key="mid:deux@ecole.test")])
_LISTE["donnees"] = [{"id": ID_RECU, "from": "info@ecole.exemple.test",
                      "to": [ADRESSE_REPONSE], "created_at": RECU}]
_plaf = lancer(S.p3r4_rattraper(simulation=True, plafond=1))
verifier("12s. le plafond arrete le passage",
         _plaf["traites"] == 1
         and any(r["verdict"] == "REPORTE" for r in _plaf["resultats"]),
         json.dumps([r["verdict"] for r in _plaf["resultats"]]))


# ============================================================================
print("\n13. CE QUE LE LOT N'A PAS FAIT")

verifier("13a. aucune route n'est ajoutee", BLOC_R4.count("@api_router.") == 0)
verifier("13b. aucun envoi d'e-mail dans le lot",
         "Emails.send" not in BLOC_R4 and _ENVOIS == [], str(len(_ENVOIS)))
verifier("13c. aucun drapeau d'envoi n'est lu ni ecrit",
         not any(d in BLOC_R4 for d in ("P3_LAUNCH_ENABLED", "P3_LAUNCH_ENVOI_REEL",
                                        "P3_RELANCE_ENABLED", "P3_RELANCE_ENVOI_REEL",
                                        "get_feature_flags")))
verifier("13d. le lot n'ecrit jamais `replied_at` ni une annulation de relance",
         not any(c in BLOC_R4 for c in ('"replied_at"', "j3_annule", "j7_annule",
                                        "p3u2_marquer_reponse")))
verifier("13e. le lot ne touche NI action NI fiche",
         "P3S3_ACTIONS" not in BLOC_R4 and "P3S1_COLLECTION" not in BLOC_R4)
verifier("13f. le lot ne touche pas au registre STOP",
         not any(c in BLOC_R4 for c in ("p3u1_enregistrer_refus", "c3_refus_exprimes",
                                        "subscribers")))
verifier("13g. aucune regex n'entre dans une requete Mongo", "$regex" not in BLOC_R4)
verifier("13h. l'ecriture du contenu est CONDITIONNELLE",
         '"contenu_recupere": {"$ne": True}' in BLOC_R4)
verifier("13i. une seule collection est ecrite : les messages entrants",
         BLOC_R4.count("update_one(") == 1 and "insert_one" not in BLOC_R4
         and "delete" not in BLOC_R4 and "update_many" not in BLOC_R4)
verifier("13j. la liste blanche des champs est fermee",
         set(S.P3R4_CHAMPS_CONTENU) == {"provider_email_id", "body_html",
                                        "body_quoted", "contenu_recupere",
                                        "contenu_source", "contenu_erreur"})
_hors = S.p3r4_champs_contenu({"provider_email_id": "x", "body_text": "PAS ICI",
                               "statut": "PAS ICI", "coach_id": "PAS ICI"})
verifier("13k. un champ hors liste blanche est IGNORE",
         set(_hors) == {"provider_email_id"}, str(sorted(_hors)))
verifier("13l. la coupe de citation reutilise le nettoyage HTML existant",
         "p3u3_texte_depuis_html" in BLOC_R4)
_arbre = ast.parse(BLOC_R4[BLOC_R4.index("P3R4_PREFIXE"):])
_defs = [n.name for n in ast.walk(_arbre)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
verifier("13m. toutes les fonctions du lot sont prefixees `p3r4_`",
         all(n.startswith("p3r4_") for n in _defs), str(_defs))


# ============================================================================
print("\n" + "=" * 78)
_ok = sum(1 for _, c, _ in RESULTATS if c)
print("P3-R4 : %d / %d verifications" % (_ok, len(RESULTATS)))
print("Sorties reseau tentees : %d" % len(_TENTATIVES))
print("E-mails envoyes : %d" % len(_ENVOIS))
print("=" * 78)
if _ok != len(RESULTATS):
    print("\nECHECS :")
    for intitule, cond, detail in RESULTATS:
        if not cond:
            print("  - %s%s" % (intitule, ("  [%s]" % detail) if detail else ""))
    sys.exit(1)
