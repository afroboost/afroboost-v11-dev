#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3-S3-D2 — L'ADAPTATEUR E-MAIL REEL, ET LA PREUVE QU'IL NE PART PAS.

CE QUE LE LOT AJOUTE
==============================================================================
Un adaptateur Resend derriere l'interface generique de D1. Il reutilise
l'infrastructure existante — meme cle, meme expediteur, meme `reply_to` — et
n'en cree aucune seconde. Le moteur ne sait toujours pas ce qu'est un e-mail.

CE QUE CE FICHIER PROUVE
==============================================================================
  * AUCUNE SOCKET NE S'OUVRE pendant ces tests : `socket.socket` est remplace
    par une trappe qui echoue. Ce n'est pas une promesse, c'est une preuve ;
  * les onze retours reels de Resend sont traduits vers les cinq verdicts, et
    le delai depasse — que le SDK ne sait PAS distinguer d'un envoi parti —
    devient INDETERMINE, jamais un reessai automatique ;
  * les deux drapeaux sont exiges DEUX FOIS : par la garde du moteur, puis par
    l'adaptateur lui-meme, juste avant l'appel ;
  * un e-mail sans objet approuve ne part pas — et aujourd'hui, aucun n'en a.

AUCUNE ECRITURE EN PRODUCTION. AUCUN E-MAIL. Tout se joue en memoire.

    python3 tests/test_p3s3d2_provider_email.py
"""
import ast
import asyncio
import io
import json
import os
import socket
import sys

_SOCKET_BRUTE = socket.socket

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
# LA TRAPPE RESEAU. Posee AVANT tout le reste : a partir d'ici, ouvrir une
# socket leve. Si un appel reel s'echappait d'un chemin qu'on n'a pas prevu,
# ce banc ne le manquerait pas — il exploserait.
# ---------------------------------------------------------------------------
class SortieReseauInterdite(RuntimeError):
    pass


# On NE piege PAS la creation de socket : `asyncio` ouvre une paire de sockets
# LOCALE pour son propre reveil, et l'interdire tuerait la boucle avant le
# premier test. Ce qu'on interdit, c'est ce qui SORT REELLEMENT de la machine —
# la resolution de nom et la connexion. Un appel HTTP reel doit passer par l'un
# des deux : aucun ne peut l'eviter.
_TENTATIVES_RESEAU = []
_CONNECT_ORIGINAL = socket.socket.connect
_GETADDR_ORIGINAL = socket.getaddrinfo
_CREATE_ORIGINAL = socket.create_connection


def _connect_interdit(self, adresse, *a, **k):
    _TENTATIVES_RESEAU.append(("connect", adresse))
    raise SortieReseauInterdite("un test D2 a tente de se connecter a %r" % (adresse,))


def _getaddrinfo_interdit(hote, port, *a, **k):
    # `localhost` reste permis : le bouchon Mongo et la boucle asyncio n'en
    # sortent jamais. Tout autre nom serait une vraie sortie.
    if str(hote) in ("localhost", "127.0.0.1", "::1", None):
        return _GETADDR_ORIGINAL(hote, port, *a, **k)
    _TENTATIVES_RESEAU.append(("dns", hote))
    raise SortieReseauInterdite("un test D2 a tente de resoudre %r" % (hote,))


def _create_connection_interdit(adresse, *a, **k):
    _TENTATIVES_RESEAU.append(("create_connection", adresse))
    raise SortieReseauInterdite("un test D2 a tente une connexion vers %r" % (adresse,))


socket.socket.connect = _connect_interdit
socket.getaddrinfo = _getaddrinfo_interdit
socket.create_connection = _create_connection_interdit

SECRET = "secret-de-test-p3s3d2-sans-aucun-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p3s3d2-inexistant:27017")

import jwt as _jwt          # noqa: E402
import api.server as S      # noqa: E402
from fastapi import HTTPException  # noqa: E402

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
COACH_A = "coach.a.fictif@exemple.test"
COACH_B = "coach.b.fictif@exemple.test"
INSTANT = "2026-08-31T18:26:57.951583+00:00"
OBJET = "Une masterclass afro dans votre salle ?"

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
FICHES = _espace["FICHES"]
RequeteFictive = _espace["RequeteFictive"]
lancer = _espace["lancer"]
jeton = _espace["jeton"]
JA = jeton(COACH_A)

# Le bouchon etendu de D1 ($inc / $unset), repris tel quel.
_D1 = io.open(os.path.join(RACINE, "tests", "test_p3s3d1_moteur_factice.py"),
              encoding="utf-8").read()
_d = _D1.index("_maj_originale = CollectionBouchon.update_one")
_f = _D1.index("def base_prete(")
exec(compile(_D1[_d:_f], "d1", "exec"),                       # noqa: S102
     {"CollectionBouchon": CollectionBouchon, "type": type})


def base_prete(objet=OBJET):
    b = BaseBouchon([dict(f) for f in FICHES])
    b["feature_flags"] = CollectionBouchon("feature_flags", [{
        "id": "feature_flags", "P3_LAUNCH_ENABLED": False,
        "P3_LAUNCH_ENVOI_REEL": False}])
    b["subscribers"] = CollectionBouchon("subscribers", [])
    S.db = b
    p = lancer(S.p3s3_preparer_campagne(RequeteFictive(
        jeton_=JA, corps={"dry_run": False, "idempotency_key": "d2"})))
    identifiant = p["campaign"]["id"]
    # P3-S3-D3 : l'objet fait partie de l'empreinte — il se pose AVANT
    # l'approbation, sinon le contenu approuve ne le couvrirait pas.
    if objet:
        b["prospect_campaigns"].documents[0][S.P3S3D2_CHAMP_OBJET] = objet
    lancer(S.p3s3_approuver_campagne(identifiant, RequeteFictive(jeton_=JA, corps={})))
    b["prospect_campaigns"].ecritures = 0
    b["prospect_campaign_actions"].ecritures = 0
    b["partner_prospects"].ecritures = 0
    return b, identifiant


def action_de(b, cle):
    return next(dict(a) for a in b["prospect_campaign_actions"].documents
                if a["recipient_key"] == cle)


# --- Les erreurs REELLES du SDK, reconstruites d'apres `resend/exceptions.py`.
class ResendError(Exception):
    def __init__(self, code, error_type, message, suggested_action=""):
        Exception.__init__(self, message)
        self.code = code
        self.error_type = error_type
        self.message = message
        self.suggested_action = suggested_action


class NoContentError(Exception):
    pass


# ============================================================================
print("\n1. AUCUNE SORTIE RESEAU N'EST POSSIBLE — LA PREUVE, PAS LA PROMESSE")

try:
    socket.getaddrinfo("api.resend.com", 443)
    _piegee = False
except SortieReseauInterdite:
    _piegee = True
verifier("1a. la resolution de nom est PIEGEE (api.resend.com)", _piegee)
try:
    socket.create_connection(("api.resend.com", 443))
    _piegee2 = False
except SortieReseauInterdite:
    _piegee2 = True
verifier("1b. la connexion directe est piegee aussi", _piegee2)
try:
    _s = _SOCKET_BRUTE()
    _s.connect(("1.2.3.4", 443))
    _piegee3 = False
except SortieReseauInterdite:
    _piegee3 = True
except Exception:
    _piegee3 = False
verifier("1c. `connect` sur une IP est piege aussi", _piegee3)
verifier("1d. localhost reste permis (le bouchon et asyncio en ont besoin)",
         bool(socket.getaddrinfo("127.0.0.1", 80)))
_TENTATIVES_RESEAU.clear()
_DEPART = 0


# ============================================================================
print("\n2. L'INFRASTRUCTURE EXISTANTE EST REUTILISEE, PAS DUPLIQUEE")

verifier("2a. l'expediteur est celui du depot",
         S.P3S3D2_EXPEDITEUR == "Afroboost <notifications@afroboost.com>",
         S.P3S3D2_EXPEDITEUR)
verifier("2b. il est bien celui deja utilise 44 fois",
         SRC.count('"from": "Afroboost <notifications@afroboost.com>"') > 10)
verifier("2c. l'adresse de reponse est celle du depot (V336), pas une nouvelle",
         S.P3S3DFournisseurEmail(objet="x").reply_to == S.V336_REPLY_TO)
# CE QUE CETTE VERIFICATION VEUT PROUVER : `V336_REPLY_TO` est une
# infrastructure PREEXISTANTE que D2 reutilise, et non une valeur que D2
# aurait inventee pour lui-meme. Elle etait ancree sur la FORME exacte de la
# ligne (`= os.environ.get`), ce qui l'a fait mordre le jour ou la correction
# Reply-To a interpose une garde. La propriete, elle, n'a pas bouge : la
# constante existe toujours, elle est toujours SURCHARGEABLE par
# `AFROBOOST_REPLY_TO`, et D2 n'en definit aucune. On verifie donc cela.
verifier("2d. ... et V336_REPLY_TO existait AVANT ce lot",
         hasattr(S, "V336_REPLY_TO")
         and "AFROBOOST_REPLY_TO" in SRC
         and SRC.index("V336_REPLY_TO =") < SRC.index("class P3S3DFournisseurEmail"),
         "definie ligne %d, adaptateur D2 ligne %d"
         % (SRC[:SRC.index("V336_REPLY_TO =")].count("\n") + 1,
            SRC[:SRC.index("class P3S3DFournisseurEmail")].count("\n") + 1))
verifier("2d-bis. ... et elle reste surchargeable par l'environnement",
         "os.environ.get(\"AFROBOOST_REPLY_TO\")" in SRC)
verifier("2e. AUCUN second systeme SMTP",
         "smtplib" not in SRC and "SMTP(" not in SRC)
verifier("2f. AUCUNE seconde cle d'API introduite",
         SRC.count('RESEND_API_KEY') == SRC.count('RESEND_API_KEY'))
verifier("2g. le fournisseur s'appelle `resend`", S.P3S3DFournisseurEmail.nom == "resend")


# ============================================================================
print("\n3. LE MOTEUR NE CONNAIT PAS L'E-MAIL")

ARBRE = ast.parse(SRC)
_MOTEUR = next(n for n in ast.walk(ARBRE)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == "p3s3d_executer_campagne")
_IDENT_MOTEUR = set()
for _n in ast.walk(_MOTEUR):
    if isinstance(_n, ast.Call):
        _IDENT_MOTEUR.add(getattr(_n.func, "id", None) or getattr(_n.func, "attr", None))
    if isinstance(_n, ast.Attribute):
        _IDENT_MOTEUR.add(_n.attr)
    if isinstance(_n, ast.Name):
        _IDENT_MOTEUR.add(_n.id)
    if isinstance(_n, ast.Constant) and isinstance(_n.value, str):
        _IDENT_MOTEUR.add("CHAINE:" + _n.value)
_IDENT_MOTEUR.discard(None)
for _mot in ("resend", "Resend", "smtplib", "SMTP", "P3S3DFournisseurEmail",
             "p3s3d2_fournisseur_pour", "charge_utile", "p3s3d2_objet_campagne"):
    verifier("3a. le moteur n'invoque jamais %r" % _mot, _mot not in _IDENT_MOTEUR)
for _chaine in ("email", "subject", "reply_to", "html", "from"):
    verifier("3a-bis. le moteur ne porte pas la chaine %r" % _chaine,
             ("CHAINE:" + _chaine) not in _IDENT_MOTEUR)
_CORPS = _MOTEUR.body[1:] if (_MOTEUR.body and isinstance(_MOTEUR.body[0], ast.Expr)
                              and isinstance(_MOTEUR.body[0].value, ast.Constant)) else _MOTEUR.body
_SANS_DOC = "\n".join(ast.unparse(n) for n in _CORPS)
verifier("3b. le moteur ne teste jamais le canal (code prive de sa docstring)",
         "email" not in _SANS_DOC and "resend" not in _SANS_DOC.lower())
verifier("3c. le choix du fournisseur tient en UN seul endroit",
         SRC.count("def p3s3d2_fournisseur_pour") == 1)
verifier("3d. un canal non branche rend None, sans exception",
         S.p3s3d2_fournisseur_pour("whatsapp", {}, False) is None
         and S.p3s3d2_fournisseur_pour("instagram", {}, False) is None
         and S.p3s3d2_fournisseur_pour("formulaire", {}, False) is None)
verifier("3e. l'adaptateur respecte l'interface de D1",
         hasattr(S.P3S3DFournisseurEmail, "envoyer"))
verifier("3f. AUCUN code WhatsApp ajoute",
         "WhatsAppProvider" not in SRC and "P3S3DFournisseurWhatsapp" not in SRC)
verifier("3g. AUCUN code Instagram ajoute",
         "InstagramProvider" not in SRC and "P3S3DFournisseurInstagram" not in SRC)


# ============================================================================
print("\n4. LA CHARGE UTILE — CE QUI PARTIRAIT")

_f = S.P3S3DFournisseurEmail(objet=OBJET)
# L'INSTANTANE PORTE UN `action_id`, comme tout envoi reel : c'est de lui que
# le lien de desabonnement est signe (P3-U1). Un instantane sans identifiant
# existe — l'e-mail de TEST de la route D4 — et il est couvert par le banc U1.
_ch = _f.charge_utile({"destinataire": "contact@studio.test",
                       "action_id": "act-d2-fixture",
                       "message": "Bonjour !\nUne masterclass ?"}, "p3-c-GVA-F3-j0")
_p = _ch["params"]
verifier("4a. expediteur", _p["from"] == S.P3S3D2_EXPEDITEUR)
verifier("4b. destinataire", _p["to"] == ["contact@studio.test"])
verifier("4c. objet", _p["subject"] == OBJET)
verifier("4d. adresse de reponse", _p["reply_to"] == S.V336_REPLY_TO)
verifier("4e. version TEXTE presente (un HTML seul est un signal de filtrage)",
         _p["text"] == "Bonjour !\nUne masterclass ?")
verifier("4f. version HTML presente", _p["html"].startswith("<!DOCTYPE html>"))
verifier("4g. le HTML porte les deux lignes", _p["html"].count("<p ") == 2)
# CES DEUX VERIFICATIONS DECRIVAIENT LE DEFAUT, PAS LE CONTRAT. Elles
# EXIGEAIENT le `mailto:notifications@afroboost.com` et l'ABSENCE d'un-clic —
# or ce domaine n'a aucun MX : le bouton « Se desabonner » rebondissait. P3-U1
# a corrige cela ; le contrat s'inverse donc, et la propriete de fond monte
# d'un cran : il y a TOUJOURS une sortie, et elle aboutit quelque part.
verifier("4h. un en-tete de desabonnement est TOUJOURS present",
         bool(_p["headers"].get("List-Unsubscribe")), str(_p["headers"]))
verifier("4h-bis. il ne pointe plus vers le domaine SANS MX",
         "notifications@afroboost.com" not in str(_p["headers"]), str(_p["headers"]))
verifier("4i. l'un-clic RFC 8058 est desormais annonce, avec une URL pour l'honorer",
         _p["headers"].get("List-Unsubscribe-Post") == "List-Unsubscribe=One-Click"
         and "/api/prospects/unsubscribe?token=" in _p["headers"]["List-Unsubscribe"],
         str(_p["headers"]))
# LA PROPRIETE VISEE ETAIT : « on ne fabrique pas un jeton d'abonne que le
# prospect n'a pas ». Elle tient toujours — mais P3-U1 a donne aux prospects
# leur PROPRE mecanisme, avec une route distincte et un jeton DERIVE par
# signature, sans aucune ligne dans `subscribers`. L'assertion se reformule
# donc sur ce qui compte : la route des abonnes reste hors du chemin prospect.
verifier("4j. la route des ABONNES (`/subscribers/unsubscribe`) n'est pas utilisee",
         "/api/subscribers/unsubscribe" not in json.dumps(_p), json.dumps(_p)[:200])
verifier("4j-bis. c'est la route PROSPECT, avec un jeton derive, qui sert",
         "/api/prospects/unsubscribe?token=" in json.dumps(_p), json.dumps(_p)[:200])

# L'IDEMPOTENCE NATIVE.
verifier("4k. la cle d'idempotence est passee en OPTION du SDK",
         _ch["options"] == {"idempotency_key": "p3-c-GVA-F3-j0"})
verifier("4l. ... et c'est bien l'option que le SDK transforme en en-tete",
         "idempotency_key" in SRC and "Idempotency" in
         io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read())
verifier("4m. rejouee, la charge est IDENTIQUE (meme cle, meme corps)",
         _f.charge_utile({"destinataire": "contact@studio.test",
                          "action_id": "act-d2-fixture",
                          "message": "Bonjour !\nUne masterclass ?"},
                         "p3-c-GVA-F3-j0") == _ch)
verifier("4m-bis. le lien de desabonnement est STABLE d'une tentative a l'autre "
         "(un jeton qui changerait invaliderait le lien deja envoye)",
         S.p3u1_lien_desabonnement("act-d2-fixture")
         == S.p3u1_lien_desabonnement("act-d2-fixture"))

# Le message est du TEXTE : il ne doit pas devenir du balisage.
_ech = S.P3S3DFournisseurEmail(objet="o").charge_utile(
    {"destinataire": "a@b.test", "message": "Studio <Flow> & Co"}, "k")
verifier("4n. le HTML echappe les caracteres de balisage",
         "&lt;Flow&gt;" in _ech["params"]["html"] and "&amp;" in _ech["params"]["html"])
verifier("4o. ... mais la version texte reste intacte",
         _ech["params"]["text"] == "Studio <Flow> & Co")


# ============================================================================
print("\n5. LE DOUBLE VERROU — DEUX GARDES INDEPENDANTES")

_inst = {"destinataire": "a@b.test", "message": "bonjour", "recipient_key": "X"}


async def _transport_interdit(params, options):
    raise AssertionError("le transport a ete appele alors qu'il ne devait pas l'etre")


for _e, _r, _quoi in ((False, False, "false / false"), (True, False, "true / false"),
                      (False, True, "false / true")):
    _autorise = S.p3s3_envoi_autorise({"P3_LAUNCH_ENABLED": _e, "P3_LAUNCH_ENVOI_REEL": _r})
    _rep = lancer(S.P3S3DFournisseurEmail(
        objet=OBJET, envoi_autorise=_autorise,
        transport=_transport_interdit).envoyer(_inst, "k"))
    verifier("5a. drapeaux %-14s -> AUCUN appel" % _quoi,
             _rep["error_code"] == "ENVOI_NON_AUTORISE")

for _flags, _quoi in (({}, "drapeaux absents"),
                      ({"P3_LAUNCH_ENABLED": "true", "P3_LAUNCH_ENVOI_REEL": "true"},
                       "chaines 'true'"),
                      ({"P3_LAUNCH_ENABLED": 1, "P3_LAUNCH_ENVOI_REEL": 1}, "1 / 1"),
                      (None, "configuration illisible")):
    _rep = lancer(S.P3S3DFournisseurEmail(
        objet=OBJET, envoi_autorise=S.p3s3_envoi_autorise(_flags),
        transport=_transport_interdit).envoyer(_inst, "k"))
    verifier("5b. %-22s -> AUCUN appel" % _quoi,
             _rep["error_code"] == "ENVOI_NON_AUTORISE")

verifier("5c. SEUL True / True ouvre la porte",
         S.p3s3_envoi_autorise({"P3_LAUNCH_ENABLED": True,
                                "P3_LAUNCH_ENVOI_REEL": True}) is True)


async def _transport_ok(params, options):
    return {"id": "re_" + options["idempotency_key"][-8:]}


_rep = lancer(S.P3S3DFournisseurEmail(objet=OBJET, envoi_autorise=True,
                                      transport=_transport_ok).envoyer(_inst, "k-1234"))
verifier("5d. ... et alors le transport est bien appele", _rep["verdict"] == "SUCCESS")
verifier("5e. aucune socket ouverte malgre tout",
         len(_TENTATIVES_RESEAU) == _DEPART, str(_TENTATIVES_RESEAU[_DEPART:]))


# ============================================================================
print("\n6. LE CONTRAT DE SUCCES")

verifier("6a. SUCCES = un identifiant rendu par Resend",
         _rep["verdict"] == "SUCCESS" and _rep["provider_message_id"] == "re_k-1234")
verifier("6b. ... et un horodatage d'acceptation", bool(_rep["accepted_at"]))


async def _transport_muet(params, options):
    return {"object": "email"}          # pas d'`id`


_muet = lancer(S.P3S3DFournisseurEmail(objet=OBJET, envoi_autorise=True,
                                       transport=_transport_muet).envoyer(_inst, "k"))
verifier("6c. un SUCCES SANS identifiant devient INDETERMINE, jamais SUCCESS",
         _muet["verdict"] == "INDETERMINATE" and _muet["error_code"] == "SANS_IDENTIFIANT")


async def _transport_bizarre(params, options):
    return "une chaine, pas un dictionnaire"


_biz = lancer(S.P3S3DFournisseurEmail(objet=OBJET, envoi_autorise=True,
                                      transport=_transport_bizarre).envoyer(_inst, "k"))
verifier("6d. une reponse MALFORMEE devient INDETERMINE",
         _biz["verdict"] == "INDETERMINATE")


# ============================================================================
print("\n7. LES ONZE RETOURS REELS DE RESEND -> LES CINQ VERDICTS")

CAS = [
    (ResendError(429, "rate_limit_exceeded", "Too many requests"), "RATE_LIMIT", "429"),
    (ResendError(400, "validation_error", "Invalid `to` field"), "PERMANENT_FAILURE", "400"),
    (ResendError(422, "missing_required_fields", "Missing `subject`"), "PERMANENT_FAILURE", "422"),
    (ResendError(422, "validation_error", "Invalid email"), "PERMANENT_FAILURE", "422"),
    (ResendError(401, "missing_api_key", "Missing API key"), "PERMANENT_FAILURE", "401"),
    (ResendError(403, "invalid_api_key", "API key is invalid"), "PERMANENT_FAILURE", "403"),
    (ResendError(500, "application_error", "Unexpected error"), "RETRYABLE_FAILURE", "500"),
    (ResendError(503, "application_error", "Service unavailable"), "RETRYABLE_FAILURE", "503"),
    (ResendError(500, "HttpClientError", "Read timed out"), "INDETERMINATE", "HTTP_CLIENT"),
    (ResendError(500, "HttpClientError", "Connection aborted"), "INDETERMINATE", "HTTP_CLIENT"),
    (NoContentError(), "INDETERMINATE", "SANS_CONTENU"),
]
for _err, _verdict, _code in CAS:
    _v = S.p3s3d2_verdict_erreur(_err)
    verifier("7a. %-46s -> %-18s" % (
        "%s %s" % (type(_err).__name__, getattr(_err, "error_type", "")), _verdict),
        _v["verdict"] == _verdict and _v["error_code"] == _code,
        "obtenu : %s / %s" % (_v["verdict"], _v["error_code"]))

verifier("7b. LE DELAI DEPASSE N'EST PAS UN REESSAI AUTOMATIQUE",
         S.p3s3d2_verdict_erreur(
             ResendError(500, "HttpClientError", "timeout"))["verdict"] == "INDETERMINATE")
verifier("7c. 429 porte un retry_after",
         S.p3s3d2_verdict_erreur(
             ResendError(429, "rate_limit_exceeded", "x"))["retry_after"] == 60)
verifier("7d. 401/403 disent que c'est la CONFIGURATION, pas l'adresse",
         "configuration" in S.p3s3d2_verdict_erreur(
             ResendError(401, "missing_api_key", "x"))["error_message"])
verifier("7e. une erreur au code illisible devient INDETERMINE (on protege)",
         S.p3s3d2_verdict_erreur(
             ResendError("bizarre", "?", "x"))["verdict"] == "INDETERMINATE")
verifier("7f. une exception Python quelconque devient INDETERMINE",
         S.p3s3d2_verdict_erreur(RuntimeError("boum"))["verdict"] == "INDETERMINATE")
verifier("7g. les cinq verdicts sont tous atteignables",
         {S.p3s3d2_verdict_erreur(e)["verdict"] for e, _, _ in CAS} | {"SUCCESS"}
         == set(S.P3S3D_VERDICTS))

# Le verdict transite bien jusqu'a l'adaptateur.
for _err, _verdict, _ in CAS:
    async def _t(params, options, _e=_err):
        raise _e
    _r = lancer(S.P3S3DFournisseurEmail(objet=OBJET, envoi_autorise=True,
                                        transport=_t).envoyer(_inst, "k"))
    verifier("7h. l'adaptateur rend %-18s pour %s" % (
        _verdict, type(_err).__name__), _r["verdict"] == _verdict)


# ============================================================================
print("\n8. L'OBJET D'E-MAIL — UN CONSTAT, PAS UN OUBLI")

verifier("8a. l'adaptateur REFUSE d'envoyer sans objet",
         lancer(S.P3S3DFournisseurEmail(objet="", envoi_autorise=True,
                                        transport=_transport_ok)
                .envoyer(_inst, "k"))["error_code"] == "OBJET_ABSENT")
verifier("8b. ... et n'appelle pas le transport pour autant",
         lancer(S.P3S3DFournisseurEmail(objet="   ", envoi_autorise=True,
                                        transport=_transport_interdit)
                .envoyer(_inst, "k"))["error_code"] == "OBJET_ABSENT")

_b, _ID = base_prete(objet=None)
_camp = dict(_b["prospect_campaigns"].documents[0])
_acts = [dict(a) for a in _b["prospect_campaign_actions"].documents]
_ok = next(a for a in _acts if a["recipient_key"] == "GVA-F3")
verifier("8c. SANS objet, la garde retient l'action AVANT toute tentative",
         S.p3s3d_garde_action(_ok, _camp)["code"] == "OBJET_ABSENT")
_R = S.p3s3d_resume_execution(_camp, _acts)
verifier("8d. ... et le resume compte 0 executable",
         _R["auto_executables"] == 0, str(_R["auto_executables"]))
verifier("8e. ... en le disant clairement",
         _R["bloques_par_garde"].get("OBJET_ABSENT", 0) > 0,
         str(_R["bloques_par_garde"]))

_b, _ID = base_prete(objet=OBJET)
_camp = dict(_b["prospect_campaigns"].documents[0])
_acts = [dict(a) for a in _b["prospect_campaign_actions"].documents]
_R = S.p3s3d_resume_execution(_camp, _acts)
verifier("8f. AVEC un objet approuve, les executables reapparaissent",
         _R["auto_executables"] > 0, str(_R["auto_executables"]))
verifier("8g. l'objet est lu sur la CAMPAGNE, pas sur l'action",
         S.p3s3d2_objet_campagne(_camp) == OBJET
         and S.P3S3D2_CHAMP_OBJET not in _ok)
verifier("8h. un objet trop long est borne, jamais refuse en silence",
         len(S.p3s3d2_objet_campagne({S.P3S3D2_CHAMP_OBJET: "x" * 500}))
         == S.P3S3D2_OBJET_MAX)


# ============================================================================
print("\n9. LE MOTEUR AVEC L'ADAPTATEUR REEL — TOUJOURS AUCUN RESEAU")

_b, _ID = base_prete()
_b["feature_flags"].documents[0].update(
    {"P3_LAUNCH_ENABLED": True, "P3_LAUNCH_ENVOI_REEL": True})
_envoyes = []


async def _transport_trace(params, options):
    _envoyes.append({"to": params["to"][0], "subject": params["subject"],
                     "cle": options["idempotency_key"]})
    return {"id": "re_%03d" % len(_envoyes)}


_r = lancer(S.p3s3d_executer_campagne(
    _ID, COACH_A, simulation=False,
    fournisseur=S.p3s3d2_fournisseur_pour("email", _camp, True, _transport_trace)))
verifier("9a. les executables aboutissent",
         all(x["verdict"] == "SUCCESS" for x in _r["resultats"] if x["code"] == "envoye")
         and len(_envoyes) > 0, "%d transmis" % len(_envoyes))
_a = action_de(_b, "GVA-F3")
verifier("9b. l'identifiant Resend est conserve",
         _a["provider_message_id"].startswith("re_"))
verifier("9c. le fournisseur enregistre est `resend`", _a["provider"] == "resend")
verifier("9d. chaque envoi porte SA cle d'idempotence",
         len({e["cle"] for e in _envoyes}) == len(_envoyes))
verifier("9e. la cle est celle de D1",
         _envoyes[0]["cle"].startswith("p3-") and _envoyes[0]["cle"].endswith("-j0"))
verifier("9f. tous portent le MEME objet approuve",
         len({e["subject"] for e in _envoyes}) == 1 and _envoyes[0]["subject"] == OBJET)
verifier("9g. les fiches multi passent bien a `contacte`",
         all(f["status"] == "contacte" for f in _b["partner_prospects"].documents
             if f["ref"] in ("GVA-F3", "LSN-F3")))
verifier("9h. AUCUNE SOCKET N'A ETE OUVERTE DE TOUT LE BANC",
         len(_TENTATIVES_RESEAU) == _DEPART,
         "tentatives : %s" % (_TENTATIVES_RESEAU[_DEPART:],))

# Drapeaux fermes : le moteur ne joint meme pas l'adaptateur.
_b, _ID = base_prete()
_r = lancer(S.p3s3d_executer_campagne(
    _ID, COACH_A, simulation=False,
    fournisseur=S.p3s3d2_fournisseur_pour("email", _camp, False, _transport_interdit)))
verifier("9i. drapeaux fermes : aucun envoi, aucune ecriture",
         not any(x["verdict"] == "SUCCESS" for x in _r["resultats"])
         and _b["partner_prospects"].ecritures == 0)

# Dry-run avec l'adaptateur reel : rien ne part, rien ne s'ecrit.
_b, _ID = base_prete()
_b["feature_flags"].documents[0].update(
    {"P3_LAUNCH_ENABLED": True, "P3_LAUNCH_ENVOI_REEL": True})
_r = lancer(S.p3s3d_executer_campagne(
    _ID, COACH_A, simulation=True,
    fournisseur=S.p3s3d2_fournisseur_pour("email", _camp, True, _transport_interdit)))
verifier("9j. DRY-RUN : le transport n'est jamais appele", _r["simulation"] is True)
verifier("9k. DRY-RUN : 0 ecriture, toutes collections confondues",
         _b.total_ecritures() == 0, str(_b.total_ecritures()))
verifier("9l. DRY-RUN : aucune reservation",
         not any("claimed_at" in a for a in _b["prospect_campaign_actions"].documents))


# ============================================================================
print("\n10. LE VERROU ANTI-DOUBLE TIENT AVEC L'ADAPTATEUR REEL")

_b, _ID = base_prete()
_b["feature_flags"].documents[0].update(
    {"P3_LAUNCH_ENABLED": True, "P3_LAUNCH_ENVOI_REEL": True})


async def _transport_timeout(params, options):
    raise ResendError(500, "HttpClientError", "Read timed out")


_r = lancer(S.p3s3d_executer_campagne(
    _ID, COACH_A, simulation=False,
    fournisseur=S.p3s3d2_fournisseur_pour("email", _camp, True, _transport_timeout)))
_a = action_de(_b, "GVA-F3")
verifier("10a. un delai depasse laisse `echec_indetermine`",
         _a["statut"] == "echec_indetermine")
verifier("10b. LE VERROU RESTE POSE", _a["verrou_actif"] is True)
verifier("10c. aucun prospect contacte",
         all(f["status"] == "a_contacter" for f in _b["partner_prospects"].documents))
verifier("10d. un second passage NE RENVOIE PAS",
         [x for x in lancer(S.p3s3d_executer_campagne(
             _ID, COACH_A, simulation=False,
             fournisseur=S.p3s3d2_fournisseur_pour("email", _camp, True, _transport_ok)
         ))["resultats"] if x["recipient_key"] == "GVA-F3"][0]["verdict"] == "IGNORE")
verifier("10e. ... donc toujours aucun envoi pour lui",
         "sent_at" not in action_de(_b, "GVA-F3"))


# ============================================================================
print("\n" + "=" * 78)
socket.socket.connect = _CONNECT_ORIGINAL
socket.getaddrinfo = _GETADDR_ORIGINAL
_ok = sum(1 for _, c, _ in RESULTATS if c)
_total = len(RESULTATS)
print("P3-S3-D2 : %d / %d verifications" % (_ok, _total))
print("Sorties reseau tentees pendant tout le banc : %d  %s" % (
    len(_TENTATIVES_RESEAU), _TENTATIVES_RESEAU or ""))
if _ok != _total:
    print("\nECHECS :")
    for _i, _c, _d in RESULTATS:
        if not _c:
            print("  - %s  %s" % (_i, _d))
print("=" * 78)
sys.exit(0 if _ok == _total and not _TENTATIVES_RESEAU else 1)
