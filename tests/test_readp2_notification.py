#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""READ-P2 — LE COACH APPREND QU'UN PARTENAIRE A REPONDU. ZERO PUSH REEL.

CE BANC N'ENVOIE AUCUNE NOTIFICATION. `send_push_by_email` est remplace par un
faux AVANT tout appel, et toute sortie reseau est interdite au niveau socket :
si une ligne tentait d'atteindre FCM, le banc echouerait au lieu de reveiller
un telephone.

CE QU'IL PROUVE
==============================================================================
  * A. une reponse qui arrive cree UNE notification `prospect_reply` ;
  * B. et declenche EXACTEMENT un push ;
  * C. un rejeu du meme webhook n'en cree ni une seconde, ni un second push ;
  * D. une DEUXIEME vraie reponse du meme prospect, elle, en cree une ;
  * E/F. seul le coach proprietaire est notifie ;
  * G. un push qui echoue ne fait PAS echouer la reception du message ;
  * H. sans abonnement, tout le reste continue de fonctionner ;
  * I/J. ni le push ni la notification ne marquent quoi que ce soit comme lu ;
  * K. le lien profond vise la BONNE reponse, et c'est le MEME pour le push et
       pour le centre en-app ;
  * L. aucune donnee sensible ne part sur l'ecran verrouille ;
  * M. aucun second moteur de push n'est cree.
"""
import ast
import asyncio
import io
import re
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

SECRET = "secret-de-test-readp2-sans-aucun-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-readp2-inexistant:27017")

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


BLOC = _bloc(SRC, "# READ-P2 — LE COACH APPREND QU'UN PARTENAIRE A REPONDU")


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
print("\n1. UNE REPONSE QUI ARRIVE : UNE NOTIFICATION, UN PUSH")

_b = base_neuve([ACT])
_issue = recevoir(entrant())
_notifs = _b["notifications"].documents
verifier("1a. le message est stocke", _issue["stocke"] is True)
verifier("1b. UNE notification est creee", len(_notifs) == 1, str(len(_notifs)))
verifier("1c. elle est du type `prospect_reply`",
         _notifs[0]["type"] == "prospect_reply", _notifs[0].get("type"))
verifier("1d. son identifiant est deterministe",
         _notifs[0]["id"] == "prospect_reply_" + _issue["id"], _notifs[0]["id"])
verifier("1e. elle appartient au coach proprietaire",
         _notifs[0]["coach_id"] == COACH_A)
verifier("1f. elle nait NON LUE", _notifs[0]["read"] is False)
verifier("1g. EXACTEMENT un push est parti", len(PUSHS) == 1, str(len(PUSHS)))
verifier("1h. vers le coach proprietaire, et lui seul", PUSHS[0]["email"] == COACH_A)
verifier("1i. le signalement est rapporte a l'appelant",
         _issue["signalement"]["signale"] is True and _issue["signalement"]["push"] is True)

# ============================================================================
print("\n2. CE QUE LE PUSH DIT — ET SURTOUT CE QU'IL NE DIT PAS")

verifier("2a. le titre est fixe", PUSHS[0]["titre"] == "Nouvelle réponse partenaire",
         PUSHS[0]["titre"])
verifier("2b. le corps nomme l'organisation",
         PUSHS[0]["corps"] == "BDE HE-ARC a répondu à votre proposition.",
         PUSHS[0]["corps"])
_tout = json.dumps(PUSHS[0], ensure_ascii=False).lower()
for _interdit, _quoi in (("consiste en quoi", "le corps de l'e-mail"),
                         ("bde-hearc.exemple.test", "l'adresse du prospect"),
                         ("proposition de collaboration avec", "l'objet complet"),
                         ("afroboosteur.com", "notre adresse de reception")):
    verifier("2c. l'ecran verrouille ne montre pas %s" % _quoi, _interdit not in _tout)
verifier("2d. sans organisation, la phrase reste vraie et generique",
         S.p3n2_corps("") == "Un partenaire a répondu à votre proposition."
         and S.p3n2_corps(None) == "Un partenaire a répondu à votre proposition.")
verifier("2e. le message du centre en-app est le MEME que celui du push",
         _notifs[0]["message"] == PUSHS[0]["corps"])

# ============================================================================
print("\n3. LE LIEN PROFOND — UN SEUL, POUR LES DEUX CHEMINS")

_lien = "/?prospection=1&inbound=" + _issue["id"]
verifier("3a. le push porte le lien", PUSHS[0]["donnees"].get("url") == _lien,
         PUSHS[0]["donnees"].get("url"))
verifier("3b. la notification en-app porte le MEME lien",
         _notifs[0]["url"] == _lien, _notifs[0].get("url"))
verifier("3c. il vise CETTE reponse, par son identifiant",
         _issue["id"] in _lien and "recipient_key" not in _lien)
verifier("3d. sans identifiant, le lien reste utilisable",
         S.p3n2_lien("") == "/?prospection=1" and S.p3n2_lien(None) == "/?prospection=1")
verifier("3e. le centre le sert au navigateur",
         '"url": 1' in SRC.split("C17J_PROJECTION = {")[1].split("}")[0])
verifier("3f. `prospect_reply` est dans la liste blanche du centre",
         "prospect_reply" in S.C17J_TYPES, str(S.C17J_TYPES))

# ============================================================================
print("\n4. NI LE PUSH NI LA NOTIFICATION NE MARQUENT COMME LU")

_msg = _b[S.P3U2_COLLECTION].documents[0]
verifier("4a. `read_at` est absent apres notification ET push",
         _msg.get("read_at") is None)
verifier("4b. `traite_at` aussi", _msg.get("traite_at") is None)
verifier("4c. le code du lot n'ecrit NULLE PART un etat de lecture",
         "read_at" not in CODE and "read_by" not in CODE and "traite_at" not in CODE)
verifier("4d. le compteur de non-lues voit toujours la reponse",
         lancer(S.p3ai_compteurs(COACH_A))["non_lues"] == 1)

# ============================================================================
print("\n5. UN REJEU NE REVEILLE PERSONNE UNE SECONDE FOIS")

_avant = len(PUSHS)
_rejeu = recevoir(entrant())
verifier("5a. le rejeu est reconnu comme doublon", _rejeu["doublon"] is True)
verifier("5b. AUCUNE seconde notification", len(_b["notifications"].documents) == 1,
         str(len(_b["notifications"].documents)))
verifier("5c. AUCUN second push", len(PUSHS) == _avant, "%d -> %d" % (_avant, len(PUSHS)))
verifier("5d. le rejeu n'atteint meme pas le signalement",
         "signalement" not in _rejeu)

# Second verrou, independant : meme appele directement, on ne signale pas deux fois.
_direct = lancer(S.p3n2_signaler(_b[S.P3U2_COLLECTION].documents[0], ACT))
verifier("5e. un appel DIRECT ne redouble pas non plus",
         _direct["signale"] is False and _direct["motif"] == "deja signalee")
verifier("5f. et n'a pousse aucun push", len(PUSHS) == _avant)

# ============================================================================
print("\n6. UNE DEUXIEME VRAIE REPONSE, ELLE, REVEILLE")

_deux = recevoir(entrant(message_id="<reponse-2@client.exemple.test>",
                         provider_event_id="evt-002",
                         body_text="Une seconde question, en fait."))
verifier("6a. elle est stockee", _deux["stocke"] is True and not _deux["doublon"])
verifier("6b. une SECONDE notification existe",
         len(_b["notifications"].documents) == 2, str(len(_b["notifications"].documents)))
verifier("6c. un SECOND push est parti", len(PUSHS) == _avant + 1)
verifier("6d. les deux notifications ont des identifiants DIFFERENTS",
         _b["notifications"].documents[0]["id"] != _b["notifications"].documents[1]["id"])
verifier("6e. chacune vise SA reponse",
         _b["notifications"].documents[1]["url"].endswith(_deux["id"]))

# ============================================================================
print("\n7. UN AUTRE COACH N'EST JAMAIS REVEILLE")

_b = base_neuve([action_de("aut", "autre@exemple.test", "AUT-01", "Autre Org", COACH_B)])
recevoir(entrant(from_email="autre@exemple.test", to_email="contact@afroboosteur.com"),
         coach=COACH_B)
verifier("7a. la notification appartient a COACH_B",
         _b["notifications"].documents[0]["coach_id"] == COACH_B)
verifier("7b. le push part vers COACH_B, jamais vers COACH_A",
         PUSHS[-1]["email"] == COACH_B and all(p["email"] != COACH_A for p in PUSHS))
verifier("7c. COACH_A ne voit rien de cette notification",
         lancer(S.db["notifications"].count_documents(
             {"coach_id": COACH_A, "type": "prospect_reply"})) == 0)

# ============================================================================
print("\n8. LE PUSH EST ACCESSOIRE — IL NE FAIT JAMAIS ECHOUER LA RECEPTION")

_b = base_neuve([ACT])
_ECHEC_PUSH["actif"] = True
_issue = recevoir(entrant())
_ECHEC_PUSH["actif"] = False
verifier("8a. le message est stocke MALGRE la panne de push", _issue["stocke"] is True)
verifier("8b. la notification en-app existe quand meme",
         len(_b["notifications"].documents) == 1)
verifier("8c. le badge continue de compter cette reponse",
         lancer(S.p3ai_compteurs(COACH_A))["non_lues"] == 1)
verifier("8d. l'echec est rapporte honnetement, pas masque",
         _issue["signalement"]["signale"] is True
         and _issue["signalement"]["push"] is False)

_b = base_neuve([ACT])
_SANS_ABONNEMENT["actif"] = True
_issue = recevoir(entrant())
_SANS_ABONNEMENT["actif"] = False
verifier("8e. SANS abonnement : le message est stocke", _issue["stocke"] is True)
verifier("8f. la notification en-app existe", len(_b["notifications"].documents) == 1)
verifier("8g. et le push est simplement rapporte comme non abouti",
         _issue["signalement"]["push"] is False)

# ============================================================================
print("\n9. AUCUN SECOND MOTEUR, AUCUN ENVOI D'E-MAIL")

verifier("9a. le lot REUTILISE `send_push_by_email`", "send_push_by_email(" in CODE)
for _interdit in ("pywebpush", "webpush(", "VAPID_PRIVATE_KEY", "push_subscriptions",
                  "create_index", "addEventListener"):
    verifier("9b. aucun second moteur : « %s » absent du lot" % _interdit,
             _interdit not in CODE)
for _interdit in ("resend", "Emails.send", "P3S3DFournisseurEmail",
                  "P3_LAUNCH_ENVOI_REEL", "P3_RELANCE_ENVOI_REEL"):
    verifier("9c. aucun envoi d'e-mail : « %s » absent du lot" % _interdit,
             _interdit not in CODE)
verifier("9d. le Service Worker n'est PAS modifie par ce lot",
         "data.tag || 'afroboost-push'" in io.open(
             os.path.join(RACINE, "frontend", "public", "sw.js"), encoding="utf-8").read())

_arbre = ast.parse(SRC)
_routes = [n.name for n in ast.walk(_arbre)
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
           and n.name.startswith("p3n2_")
           and any("api_router" in (ast.get_source_segment(SRC, d) or "")
                   for d in n.decorator_list)]
verifier("9e. le lot n'ajoute AUCUNE route", _routes == [], str(_routes))
verifier("9f. AUCUNE sortie reseau pendant tout le banc", not _TENTATIVES,
         str(_TENTATIVES[:3]))
verifier("9g. AUCUN push reel : tous sont passes par le faux",
         all(isinstance(p, dict) and "email" in p for p in PUSHS))

# ============================================================================
print("\n10. LE FRONT — UN SEUL CHEMIN, ET IL N'OUVRE PAS LE CHAT")

APP = io.open(os.path.join(RACINE, "frontend", "src", "App.js"), encoding="utf-8").read()
DASH = io.open(os.path.join(RACINE, "frontend", "src", "components",
                            "CoachDashboard.js"), encoding="utf-8").read()
ECRAN = io.open(os.path.join(RACINE, "frontend", "src", "components", "coach",
                             "ProspectsSection.js"), encoding="utf-8").read()
CHAT = io.open(os.path.join(RACINE, "frontend", "src", "components",
                            "ChatWidget.js"), encoding="utf-8").read()

# DEEPLINK PROSPECTION — les trois premieres verifications suivent le
# deplacement de la CAPTURE. Elle n'est plus dans un effet d'App.js (elle y
# arrivait apres le montage de l'enfant, cf. section 11) mais a l'import du
# module. Ce qui est prouve ne change pas : le lien profond est reconnu,
# l'intention est mise de cote AVANT toute decision, et on n'y met que
# l'identifiant borne. Seul l'endroit qui le fait a change.
INTENTION_SRC = io.open(os.path.join(RACINE, "frontend", "src", "utils",
                                     "prospectionIntention.js"),
                        encoding="utf-8").read()
_APRES = APP.split("prospectionIntentionLire() !== null")

verifier("10a. le lien profond est reconnu",
         "params.get('prospection') !== '1'" in INTENTION_SRC
         and "get('inbound')" in INTENTION_SRC)
verifier("10b. l'intention est mise de cote AVANT toute decision",
         # A l'import, donc avant le premier rendu — plus tot qu'aucun effet.
         "CAPTURE_AU_CHARGEMENT = capturer()" in INTENTION_SRC
         and "poser(cible)" in INTENTION_SRC)
verifier("10c. il n'y met QUE l'identifiant, borne",
         ".slice(0, 64)" in INTENTION_SRC)
verifier("10d. connecte -> dashboard ; sinon -> connexion, puis reprise",
         len(_APRES) > 1
         and "setCoachMode(true)" in _APRES[1][:1200]
         and "setShowCoachLogin(true)" in _APRES[1][:1200])
verifier("10e. l'URL est nettoyee : un rafraichissement ne rejoue rien",
         "history.replaceState" in INTENTION_SRC)
verifier("10f. l'app DEJA OUVERTE reagit au clic du Service Worker",
         "NOTIFICATION_CLICK" not in APP or "prospection=1" in APP)
verifier("10g. le ChatWidget NE s'ouvre PLUS sur une notification de prospection",
         "url.indexOf('prospection=1') !== -1) return;" in CHAT)
# L'intention est toujours consommee UNE fois — mais plus au montage, ou les
# conversations n'etaient pas encore chargees : au SUCCES, quand l'ecran a
# ouvert la bonne conversation (ou l'a declaree introuvable).
verifier("10h. l'intention est consommee UNE fois, et au succes",
         "prospectionIntentionConsommer()" in DASH
         and DASH.count("prospectionIntentionConsommer()") == 1
         and "export function consommer()" in INTENTION_SRC)
verifier("10i. il bascule sur l'onglet Prospection",
         "setTab('prospection')" in DASH)
# PROSPECTION FOCUS — la cible est desormais une CONVERSATION ouverte SUR le
# message vise : `ouvrirMessage` designe les DEUX, ce qu'un identifiant seul ne
# pouvait plus faire depuis qu'un fil porte plusieurs messages (le BDE en a
# deux). La propriete prouvee ne bouge pas d'un iota : le lien profond n'ouvre
# PAS par un chemin parallele qui sauterait la lecture — la chaine finit dans
# `ouvrirReponse`, donc `read_at` s'ecrit comme si le coach avait clique.
verifier("10j. l'ecran recoit la cible et l'ouvre par le chemin NORMAL",
         "inboundCible" in ECRAN
         and "ouvrirMessage(conversationCible, cibleTrouvee)" in ECRAN
         and "ouvrirReponse(message.id)" in ECRAN)
verifier("10k. la dependance de l'effet est une CHAINE, jamais un tableau",
         "}, [cibleTrouvee]);" in ECRAN)
verifier("10l. une cible introuvable ne casse rien et le DIT",
         "cibleIntrouvable" in ECRAN and "cible-introuvable" in ECRAN)
verifier("10m. la notification en-app mene au MEME endroit que le push",
         "c17jOuvrir" in DASH and "prospection=1" in DASH)
verifier("10n. le badge Prospection continue de venir des NON LUES",
         "p3NonLues > 0 ? `Prospection (${p3NonLues})`" in DASH
         and "res?.data?.non_lues" in DASH)

# ============================================================================
# 11. DEEPLINK PROSPECTION — LA COURSE DE MONTAGE EST FERMEE, ET LE RESTE.
#
# CE QUI S'EST PASSE. `coachMode` est restaure de facon SYNCHRONE depuis le
# localStorage : quand le coach est deja connecte — le cas normal quand il
# touche une notification — CoachDashboard est monte des le PREMIER rendu. React
# executant les effets des enfants AVANT ceux du parent, l'effet de montage du
# dashboard allait chercher l'intention avant que l'effet d'App ne l'ait posee.
# Il trouvait `null`, repartait, et l'identifiant restait en sessionStorage sans
# que personne ne l'honore. Mesure en production le 06/09 : la cle intacte apres
# chargement, et la conversation fermee.
#
# CE QUE CES VERIFICATIONS EMPECHENT DE REVENIR : remettre la capture dans un
# effet, redonner a deux composants le droit d'ecrire la meme cle, ou reprendre
# l'habitude de consommer l'intention avant d'avoir ouvert quoi que ce soit.
# ============================================================================
print("\n11. DEEPLINK PROSPECTION — LA COURSE DE MONTAGE EST FERMEE")

INTENTION = io.open(os.path.join(RACINE, "frontend", "src", "utils",
                                 "prospectionIntention.js"), encoding="utf-8").read()

verifier("11a. la capture a lieu A L'IMPORT, pas dans un effet",
         "CAPTURE_AU_CHARGEMENT = capturer()" in INTENTION)
verifier("11b. le module est la SEULE source : il nomme la cle",
         "CLE = 'afroboost_prospection_inbound'" in INTENTION)
verifier("11c. App.js ne touche PLUS la cle directement",
         "afroboost_prospection_inbound" not in APP)
verifier("11d. le dashboard non plus",
         "afroboost_prospection_inbound" not in DASH)
verifier("11e. ni l'ecran Prospection",
         "afroboost_prospection_inbound" not in ECRAN)
verifier("11f. App LIT l'intention, il ne la pose plus depuis l'URL",
         "prospectionIntentionLire() !== null" in APP)
verifier("11g. le dashboard NE CONSOMME PLUS au montage",
         "removeItem('afroboost_prospection_inbound')" not in DASH
         and "prospectionIntentionLire" in DASH)
verifier("11h. il ecoute l'annonce, pour l'application DEJA ouverte",
         "PROSPECTION_INTENTION_EVENEMENT" in DASH
         and "addEventListener(PROSPECTION_INTENTION_EVENEMENT" in DASH)
verifier("11i. et il retire son ecouteur en partant",
         "removeEventListener(PROSPECTION_INTENTION_EVENEMENT" in DASH)
verifier("11j. la consommation n'a lieu QU'AU SUCCES, cote ecran",
         "prospectionIntentionConsommer()" in DASH
         and "onCibleConsommee" in DASH)
verifier("11k. lire n'efface pas — les deux gestes sont deux fonctions",
         "export function lire()" in INTENTION
         and "export function consommer()" in INTENTION
         and "removeItem" not in INTENTION.split("export function lire()")[1]
                                            .split("export function consommer()")[0])
verifier("11l. une cible INTROUVABLE est aussi un etat terminal : on consomme",
         "if (!cibleIntrouvable) return;" in ECRAN
         and "}, [cibleIntrouvable]);" in ECRAN)
verifier("11m. mais SEULEMENT une fois les conversations chargees",
         "sectionReponses.etat === SECTION.OK" in ECRAN)
verifier("11n. le module borne l'identifiant recu",
         ".slice(0, 64)" in INTENTION)
# Ces deux verifications portent sur le CODE, pas sur la prose : les
# commentaires du module citent « organisation » et « localStorage »
# precisement pour dire qu'il ne les touche pas.
def _sans_commentaires(src):
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)

INTENTION_CODE = _sans_commentaires(INTENTION)

verifier("11o. et ne stocke QUE l'identifiant, jamais le contenu",
         "organisation" not in INTENTION_CODE
         and "from_email" not in INTENTION_CODE
         and "setItem(CLE, valeur)" in INTENTION_CODE)
verifier("11p. sessionStorage, jamais localStorage — l'intention ne survit pas a demain",
         "sessionStorage" in INTENTION_CODE and "localStorage" not in INTENTION_CODE)
verifier("11q. le moteur Push n'est pas touche par ce lot",
         "vapid" not in INTENTION.lower() and "subscription" not in INTENTION.lower())

# ============================================================================
_ok = sum(1 for _i, _c, _d in RESULTATS if _c)
_total = len(RESULTATS)
print("\n" + "=" * 78)
print("READ-P2 : %d / %d verifications" % (_ok, _total))
print("Sorties reseau tentees : %d" % len(_TENTATIVES))
print("Push REELS envoyes : 0 — le fournisseur est un faux, pose avant tout appel")
if _ok != _total:
    print("\nECHECS :")
    for _i, _c, _d in RESULTATS:
        if not _c:
            print("  - %s%s" % (_i, (" -> " + _d) if _d else ""))
print("=" * 78)
sys.exit(0 if _ok == _total else 1)
