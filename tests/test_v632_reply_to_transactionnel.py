#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V632 — LES E-MAILS TRANSACTIONNELS PORTENT UNE ADRESSE DE REPONSE VIVANTE.

POURQUOI. `notifications@afroboost.com` est l'expediteur de tout le courrier du site, mais
n'a longtemps eu aucun MX : un client qui repondait a « Reservation confirmee » ou « Ton
code Afroboost » parlait dans le vide. Sur les 100 derniers envois, 6 n'avaient AUCUN
`Reply-To` (tous transactionnels) contre 94 pour la prospection.

CE QUE CE FICHIER PROUVE
==============================================================================
  * un e-mail SANS `reply_to` recoit `contact@afroboosteur.com` (absent, nul, vide, liste
    vide) ;
  * un `reply_to` RENSEIGNE n'est JAMAIS modifie : l'adresse a jeton de la prospection
    (`r-<jeton>@reply.afroboosteur.com`) et toute adresse explicite passent a l'octet pres ;
  * le dictionnaire de l'appelant n'est pas modifie (on rend une copie) ;
  * le defaut a la MEME valeur que `AFROBOOST_REPLY_TO_CANONIQUE` du serveur ;
  * l'adresse morte `contact@afroboost.ch` ne revient pas, meme posee par l'environnement ;
  * la valeur passe bien dans la charge utile remise au fournisseur, sur les deux chemins
    (journal actif ou non) ;
  * l'expediteur, le sujet, le corps, les destinataires ne bougent pas d'un caractere ;
  * aucune socket, aucun vrai e-mail.

    python3 tests/test_v632_reply_to_transactionnel.py
"""
import copy
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


# Aucune sortie reseau, coupee AVANT l'import.
_TENTATIVES = []
_GETADDR = socket.getaddrinfo


def _dns(hote, port, *a, **k):
    if str(hote) in ("localhost", "127.0.0.1", "::1", None):
        return _GETADDR(hote, port, *a, **k)
    _TENTATIVES.append(hote)
    raise RuntimeError("sortie reseau interdite : %s" % hote)


socket.getaddrinfo = _dns
os.environ.pop("AFROBOOST_REPLY_TO", None)
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v632-inexistant:27017")
os.environ.setdefault("JWT_SECRET", "secret-de-banc-v632")

import api.resend_central as RC  # noqa: E402

CANON = "contact@afroboosteur.com"
JETON = "r-4bcc1180d1aeeab4da2899419f802687@reply.afroboosteur.com"
BASE = {"from": "Afroboost <notifications@afroboost.com>", "to": ["client@exemple.test"],
        "subject": "Réservation confirmée — AFC33005D5", "html": "<p>Bonjour</p>"}

# ============================================================================
print("\n1. LA FONCTION PURE")
# ============================================================================
for libelle, params in [
    ("absent", dict(BASE)),
    ("None", dict(BASE, reply_to=None)),
    ("chaine vide", dict(BASE, reply_to="")),
    ("espaces", dict(BASE, reply_to="   ")),
    ("liste vide", dict(BASE, reply_to=[])),
    ("liste de vides", dict(BASE, reply_to=["", None])),
]:
    verifier("reply_to %s -> adresse par defaut" % libelle,
             RC._avec_reply_to(params).get("reply_to") == CANON,
             "recu=%r" % RC._avec_reply_to(params).get("reply_to"))

for libelle, params, attendu in [
    ("adresse a jeton (prospection)", dict(BASE, reply_to=JETON), JETON),
    ("liste a jeton", dict(BASE, reply_to=[JETON]), [JETON]),
    ("adresse explicite", dict(BASE, reply_to="coach@club.exemple.test"), "coach@club.exemple.test"),
    ("deux adresses", dict(BASE, reply_to=["a@x.test", "b@x.test"]), ["a@x.test", "b@x.test"]),
]:
    verifier("reply_to %s -> INCHANGE" % libelle,
             RC._avec_reply_to(params).get("reply_to") == attendu)

original = copy.deepcopy(BASE)
sortie = RC._avec_reply_to(BASE)
verifier("le dictionnaire de l'appelant n'est PAS modifie", BASE == original and "reply_to" not in BASE)
verifier("on rend une copie quand on ajoute", sortie is not BASE)
verifier("le reste de la charge utile est identique",
         {k: v for k, v in sortie.items() if k != "reply_to"} == BASE)
_deja = dict(BASE, reply_to=JETON)
verifier("un reply_to renseigne rend le MEME objet (rien n'est copie ni reecrit)",
         RC._avec_reply_to(_deja) is _deja)
verifier("une entree qui n'est pas un dictionnaire ne leve pas", RC._avec_reply_to(None) is None)

# ============================================================================
print("\n2. LA VALEUR : MEME QUE LE SERVEUR, ET L'ADRESSE MORTE NE REVIENT PAS")
# ============================================================================
import api.server as S  # noqa: E402

verifier("parite avec AFROBOOST_REPLY_TO_CANONIQUE du serveur",
         RC.REPLY_TO_DEFAUT == S.AFROBOOST_REPLY_TO_CANONIQUE,
         "central=%s serveur=%s" % (RC.REPLY_TO_DEFAUT, S.AFROBOOST_REPLY_TO_CANONIQUE))
verifier("memes adresses mortes que le serveur",
         tuple(RC.REPLY_TO_MORTES) == tuple(S.AFROBOOST_REPLY_TO_MORTES))
verifier("sans variable d'environnement : la canonique", RC.reply_to_defaut() == CANON)
os.environ["AFROBOOST_REPLY_TO"] = "contact@afroboost.ch"
verifier("l'adresse morte posee par l'environnement est REFUSEE", RC.reply_to_defaut() == CANON)
os.environ["AFROBOOST_REPLY_TO"] = "  CONTACT@AFROBOOST.CH "
verifier("... meme en majuscules et avec des espaces", RC.reply_to_defaut() == CANON)
os.environ["AFROBOOST_REPLY_TO"] = "autre@exemple.test"
verifier("une autre adresse reste possible (on n'a pas fige la valeur)",
         RC.reply_to_defaut() == "autre@exemple.test")
os.environ["AFROBOOST_REPLY_TO"] = ""
verifier("variable vide : la canonique", RC.reply_to_defaut() == CANON)
os.environ.pop("AFROBOOST_REPLY_TO", None)

# ============================================================================
print("\n3. LE PASSAGE REEL PAR LE POINT D'ENVOI")
# ============================================================================
CAPTURE = []


class FauxSDK:
    class Emails:
        @staticmethod
        def send(params, options=None):
            CAPTURE.append(params)
            return {"id": "re_faux"}


# 3a. journal NON actif : comportement « transmis tel quel » d'avant V608, plus l'adresse
RC._actif = False
RC.emails("banc:v632", critique=True, sdk=FauxSDK).send(dict(BASE))
verifier("journal inactif : le fournisseur recoit le reply_to par defaut",
         CAPTURE and CAPTURE[-1].get("reply_to") == CANON)
RC.emails("banc:v632", critique=True, sdk=FauxSDK).send(dict(BASE, reply_to=JETON))
verifier("journal inactif : un reply_to a jeton passe INTACT", CAPTURE[-1].get("reply_to") == JETON)

# 3b. journal actif (un e-mail critique passe meme si la base du quota est illisible)
TRANSPORT = []


def faux_transport(params, options=None):
    TRANSPORT.append(params)
    return {"id": "re_faux_transport"}


RC.configurer(base=object(), transport=faux_transport)
RC.emails("banc:v632", critique=True).send(dict(BASE))
verifier("journal actif : la charge utile soumise porte le reply_to par defaut",
         TRANSPORT and TRANSPORT[-1].get("reply_to") == CANON)
RC.emails("banc:v632", critique=True).send(dict(BASE, reply_to=JETON))
verifier("journal actif : un reply_to a jeton passe INTACT", TRANSPORT[-1].get("reply_to") == JETON)

soumis = TRANSPORT[0]
verifier("expediteur, destinataires, sujet et corps inchanges",
         all(soumis.get(k) == BASE[k] for k in ("from", "to", "subject", "html")))
verifier("aucune cle ajoutee en dehors de reply_to",
         set(soumis) - set(BASE) == {"reply_to"}, "%s" % (set(soumis) - set(BASE)))
RC._actif = False
RC._transport = None

# ============================================================================
print("\n4. LA PROSPECTION N'EST PAS TOUCHEE")
# ============================================================================
SRC = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
verifier("la prospection fixe toujours son propre reply_to a jeton",
         "p3r1_adresse_reponse(a.get(P3R1_CHAMP_TOKEN))" in SRC and SRC.count('"reply_to": p3r1_adresse_reponse') >= 2)
verifier("l'adresse de reponse des campagnes reste celle de V336", 'V336_REPLY_TO = _reply_to_vivant(' in SRC)
verifier("aucun envoi direct ne contourne le point central",
         "resend.Emails.send(" not in SRC.replace("`resend.Emails.send`", ""))

# ============================================================================
print("\n5. AUCUNE SORTIE RESEAU")
# ============================================================================
verifier("aucune socket ouverte", not _TENTATIVES, "%s" % _TENTATIVES[:3])

ok = sum(1 for _, c, _ in RESULTATS if c)
print("\n" + "=" * 78)
print("V632 — Reply-To transactionnel : %d/%d" % (ok, len(RESULTATS)))
print("=" * 78)
for i, c, d in RESULTATS:
    if not c:
        print("  ECHEC : %s%s" % (i, (" -> " + d) if d else ""))
sys.exit(0 if ok == len(RESULTATS) else 1)
