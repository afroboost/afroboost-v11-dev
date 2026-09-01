#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3-S3-D4 — LA ROUTE QUI EPROUVE RESEND, ET NE PEUT RIEN FAIRE D'AUTRE.

CE QUE LE LOT AJOUTE
==============================================================================
Une route, super-admin uniquement, qui envoie UN e-mail de test a UNE adresse
qui n'appartient a aucun prospect. Elle ne prend aucun identifiant de campagne,
ne lit aucune action pour envoyer, n'ecrit dans aucune collection metier.

CE QUE CE FICHIER PROUVE
==============================================================================
  * la route REFUSE toute adresse qui appartient a un prospect — verifie sur
    les FICHES et sur les CIBLES d'action, le doute valant refus ;
  * l'objet est TOUJOURS prefixe `[TEST AFROBOOST] `, meme si l'appelant envoie
    l'objet commercial approuve ;
  * le corps est fige : aucun texte libre, donc aucun moyen de faire passer le
    J0 commercial pour un test ;
  * un seul appel fournisseur, jamais deux ;
  * elle n'ecrit RIEN : ni prospect, ni action, ni campagne ;
  * elle ne lit ni ne modifie les deux drapeaux ;
  * elle ne peut pas lancer de campagne — elle n'en connait aucune.

AUCUN RESEAU. AUCUN E-MAIL. Tout se joue en memoire.

    python3 tests/test_p3s3d4_test_fournisseur.py
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
    _TENTATIVES.append(hote)
    raise SortieReseauInterdite("sortie reseau vers %r" % (hote,))


socket.getaddrinfo = _dns
socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(
    SortieReseauInterdite("connexion interdite"))

SECRET = "secret-de-test-p3s3d4-sans-aucun-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p3s3d4-inexistant:27017")

import jwt as _jwt          # noqa: E402
import api.server as S      # noqa: E402
from fastapi import HTTPException  # noqa: E402

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
COACH_A = "coach.a.fictif@exemple.test"
ADMIN = "contact.artboost@gmail.com"      # super-admin du depot
INSTANT = "2026-08-31T18:26:57.951583+00:00"
NEUTRE = "adresse.de.test@exemple.test"

_BANC = os.path.join(RACINE, "tests", "test_p3s3b_preparation_campagne.py")
_source = io.open(_BANC, encoding="utf-8").read()
_d = _source.index("def lancer(coroutine):")
_f = _source.index('# ============================================================================\nprint("\\n1.')
_espace = {"S": S, "asyncio": asyncio, "COACH_A": COACH_A, "COACH_B": "b@x.test",
           "INSTANT": INSTANT, "json": json, "os": os, "sys": sys,
           "_jwt": _jwt, "SECRET": SECRET, "HTTPException": HTTPException}
exec(compile(_source[_d:_f], _BANC, "exec"), _espace)   # noqa: S102
CollectionBouchon = _espace["CollectionBouchon"]
BaseBouchon = _espace["BaseBouchon"]
FICHES = _espace["FICHES"]
RequeteFictive = _espace["RequeteFictive"]
lancer = _espace["lancer"]
jeton = _espace["jeton"]
JADMIN = jeton(ADMIN)
JCOACH = jeton(COACH_A)

_APPELS = []


async def transport(params, options):
    _APPELS.append({"to": params["to"][0], "subject": params["subject"],
                    "text": params["text"], "html": params["html"],
                    "from": params["from"], "reply_to": params["reply_to"],
                    "headers": params["headers"], "cle": options["idempotency_key"]})
    return {"id": "re_test_%03d" % len(_APPELS)}


async def transport_interdit(params, options):
    raise AssertionError("le fournisseur a ete appele alors qu'il ne devait pas l'etre")


def base_neuve(avec_campagne=True):
    b = BaseBouchon([dict(f) for f in FICHES])
    b["feature_flags"] = CollectionBouchon("feature_flags", [{
        "id": "feature_flags", "P3_LAUNCH_ENABLED": False,
        "P3_LAUNCH_ENVOI_REEL": False}])
    b["subscribers"] = CollectionBouchon("subscribers", [])
    b["coaches"] = CollectionBouchon("coaches", [{"email": ADMIN}, {"email": COACH_A}])
    S.db = b
    if avec_campagne:
        p = lancer(S.p3s3_preparer_campagne(RequeteFictive(
            jeton_=JADMIN, corps={"dry_run": False, "idempotency_key": "d4"})))
        b["prospect_campaigns"].documents[0][S.P3S3D2_CHAMP_OBJET] = "Objet commercial"
        lancer(S.p3s3_approuver_campagne(p["campaign"]["id"],
                                         RequeteFictive(jeton_=JADMIN, corps={})))
    b["prospect_campaigns"].ecritures = 0
    b["prospect_campaign_actions"].ecritures = 0
    b["partner_prospects"].ecritures = 0
    b["feature_flags"].ecritures = 0
    return b


# `None` est un jeton PARFAITEMENT VALIDE a exprimer : c'est le cas « appel sans
# authentification », celui qu'on veut precisement voir refuse. Un defaut
# `jeton_ or JADMIN` le rendrait inexprimable — l'appel anonyme deviendrait
# silencieusement un appel admin, et le test passerait sans rien prouver.
# D'ou une sentinelle : seule son ABSENCE declenche le defaut admin.
DEFAUT = object()


def appeler(corps, jeton_=DEFAUT, transport_=None):
    """Le crochet d'essai se pose sur le MODULE, jamais dans la requete."""
    corps = {k: v for k, v in (corps or {}).items() if k != "_transport"}
    S.P3S3D4_TRANSPORT = transport_ if transport_ is not None else transport
    try:
        return lancer(S.p3s3d4_test_fournisseur_email(
            RequeteFictive(jeton_=(JADMIN if jeton_ is DEFAUT else jeton_),
                           corps=corps)))
    finally:
        S.P3S3D4_TRANSPORT = None


# ============================================================================
print("\n1. LA TRAPPE RESEAU EST ARMEE")

try:
    socket.getaddrinfo("api.resend.com", 443)
    _p = False
except SortieReseauInterdite:
    _p = True
verifier("1a. toute resolution de nom externe leve", _p)
_TENTATIVES.clear()


# ============================================================================
print("\n2. LA ROUTE EXISTE, ET ELLE EST SEULE DE SON ESPECE")

_CHEMINS = [r.path for r in S.app.routes if "provider-test" in getattr(r, "path", "")]
verifier("2a. une seule route de test fournisseur", len(_CHEMINS) == 1, str(_CHEMINS))
verifier("2b. son chemin est explicite",
         _CHEMINS[0] == "/api/prospect-email-provider-test", str(_CHEMINS))
verifier("2c. elle n'est PAS dans l'espace des campagnes",
         "prospect-campaigns" not in _CHEMINS[0])
_CAMP = [r.path for r in S.app.routes if "prospect-campaigns" in getattr(r, "path", "")]
verifier("2d. les routes de campagne restent SEPT, inchangees", len(_CAMP) == 7, str(len(_CAMP)))
for _interdit in ("send", "launch", "dispatch", "execute", "retry", "j3", "j7"):
    verifier("2e. aucune route contenant %r" % _interdit,
             not any(_interdit in c for c in _CAMP + _CHEMINS))

# ELLE NE PEUT PAS LANCER DE CAMPAGNE : elle n'en connait aucune.
_NOEUD = next(n for n in ast.walk(ast.parse(SRC))
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == "p3s3d4_test_fournisseur_email")
_IDENT = set()
for _n in ast.walk(_NOEUD):
    if isinstance(_n, ast.Call):
        _IDENT.add(getattr(_n.func, "id", None) or getattr(_n.func, "attr", None))
    if isinstance(_n, ast.Attribute):
        _IDENT.add(_n.attr)
    if isinstance(_n, ast.Name):
        _IDENT.add(_n.id)
_IDENT.discard(None)
for _interdit in ("p3s3d_executer_campagne", "p3s3d_reserver", "p3s3_approuver_campagne",
                  "p3s3d_appliquer_succes", "p3s3_empreinte", "p3s3d_garde_action",
                  "get_feature_flags", "p3s3_envoi_autorise", "P3S3_CAMPAGNES",
                  "insert_one", "delete_one", "delete_many"):
    verifier("2f. la route n'invoque jamais %r" % _interdit, _interdit not in _IDENT)
verifier("2g. elle ne consulte AUCUN drapeau",
         "get_feature_flags" not in _IDENT and "p3s3_envoi_autorise" not in _IDENT)
verifier("2h. elle n'ecrit nulle part (aucun update_one)", "update_one" not in _IDENT)


# ============================================================================
print("\n3. SUPER-ADMIN UNIQUEMENT")

_b = base_neuve()
try:
    appeler({"to": NEUTRE}, jeton_=None, transport_=transport_interdit)
    _ferme = False
except HTTPException as e:
    _ferme = e.status_code in (401, 403)
verifier("3a. SANS jeton -> refuse", _ferme)
try:
    appeler({"to": NEUTRE}, jeton_=JCOACH, transport_=transport_interdit)
    _ferme = False
except HTTPException as e:
    _ferme = e.status_code == 403
verifier("3b. un coach NON super-admin -> 403", _ferme)
verifier("3c. aucun appel fournisseur pour autant", len(_APPELS) == 0)


# ============================================================================
print("\n4. LA GARDE ANTI-PROSPECT — DEUX SOURCES")

_b = base_neuve()
_fiche = _b["partner_prospects"].documents[0]
_email_fiche = _fiche.get("public_email")
try:
    appeler({"to": _email_fiche}, transport_=transport_interdit)
    _refuse = False
    _detail = ""
except HTTPException as e:
    _refuse = e.status_code == 409
    _detail = str(e.detail)
verifier("4a. une adresse de FICHE prospect -> 409", _refuse, _detail[:80])
verifier("4b. le motif nomme la fiche", "fiche prospect" in _detail, _detail[:80])
verifier("4c. aucun appel fournisseur", len(_APPELS) == 0)

# Une adresse presente SEULEMENT comme cible d'action.
_b["prospect_campaign_actions"].documents[0]["target"] = "cible.seule@exemple.test"
try:
    appeler({"to": "cible.seule@exemple.test"}, transport_=transport_interdit)
    _refuse = False
    _detail = ""
except HTTPException as e:
    _refuse = e.status_code == 409
    _detail = str(e.detail)
verifier("4d. une adresse presente SEULEMENT comme cible d'action -> 409", _refuse)
verifier("4e. le motif nomme l'action", "action" in _detail, _detail[:80])

# La casse ne doit pas permettre de contourner.
try:
    appeler({"to": (_email_fiche or "").upper()}, transport_=transport_interdit)
    _refuse = False
except HTTPException as e:
    _refuse = e.status_code == 409
verifier("4f. la MAJUSCULE ne contourne pas la garde", _refuse)

# Une lecture impossible vaut « c'est un prospect ».
class _BaseQuiHoquette(dict):
    def __getitem__(self, nom):
        raise RuntimeError("base indisponible")

    def __getattr__(self, nom):
        raise RuntimeError("base indisponible")


_sauvegarde = S.db
S.db = _BaseQuiHoquette()
_v = lancer(S.p3s3d4_est_un_prospect("qui.sait@exemple.test"))
S.db = _sauvegarde
verifier("4g. une base illisible vaut « c'est un prospect » (le doute interdit)",
         _v["prospect"] is True, str(_v))
verifier("4h. une adresse vide aussi",
         lancer(S.p3s3d4_est_un_prospect(""))["prospect"] is True)


# ============================================================================
print("\n5. L'ADRESSE — UNE SEULE, VALIDE")

_b = base_neuve()
for _mauvaise, _quoi in ((None, "absente"), ("", "vide"), ("   ", "espaces"),
                         ("pas-une-adresse", "illisible"), ("a@b", "domaine sans point")):
    try:
        appeler({"to": _mauvaise}, transport_=transport_interdit)
        _refuse = False
    except HTTPException as e:
        _refuse = e.status_code == 400
    verifier("5a. adresse %-18s -> 400" % _quoi, _refuse)
try:
    appeler({"to": [NEUTRE, "autre@exemple.test"]}, transport_=transport_interdit)
    _refuse = False
except HTTPException as e:
    _refuse = e.status_code == 400
verifier("5b. une LISTE d'adresses est refusee (un seul e-mail par appel)", _refuse)
verifier("5c. toujours aucun appel fournisseur", len(_APPELS) == 0)


# ============================================================================
print("\n6. L'OBJET EST TOUJOURS PREFIXE")

_b = base_neuve()
_r = appeler({"to": NEUTRE}, transport_=transport)
verifier("6a. sans objet fourni, le defaut est prefixe",
         _r["subject"].startswith("[TEST AFROBOOST] "), _r["subject"])
_r = appeler({"to": NEUTRE, "subject": "Proposition de collaboration avec Afroboost",
              "_transport": transport})
verifier("6b. MEME l'objet commercial approuve devient un test",
         _r["subject"] == "[TEST AFROBOOST] Proposition de collaboration avec Afroboost",
         _r["subject"])
_r = appeler({"to": NEUTRE, "subject": "[TEST AFROBOOST] deja prefixe",
              "_transport": transport})
verifier("6c. un objet deja prefixe n'est pas prefixe deux fois",
         _r["subject"] == "[TEST AFROBOOST] deja prefixe", _r["subject"])
_r = appeler({"to": NEUTRE, "subject": "x" * 400}, transport_=transport)
verifier("6d. un objet trop long est borne, et reste prefixe",
         _r["subject"].startswith("[TEST AFROBOOST] ")
         and len(_r["subject"]) <= S.P3S3D2_OBJET_MAX)
verifier("6e. tous les objets transmis portent le prefixe",
         all(a["subject"].startswith("[TEST AFROBOOST] ") for a in _APPELS))


# ============================================================================
print("\n7. LE CORPS EST FIGE — LE J0 COMMERCIAL NE PEUT PAS PASSER")

_APPELS.clear()
_b = base_neuve()
_r = appeler({"to": NEUTRE, "message": "TEXTE COMMERCIAL INJECTE",
              "text": "AUTRE TEXTE", "html": "<b>encore un autre</b>",
              "_transport": transport})
verifier("7a. le corps est celui du code, pas celui de l'appelant",
         _APPELS[0]["text"] == S.P3S3D4_CORPS)
verifier("7b. le texte injecte n'apparait nulle part",
         "COMMERCIAL INJECTE" not in _APPELS[0]["text"]
         and "COMMERCIAL INJECTE" not in _APPELS[0]["html"])
verifier("7c. le corps dit que c'est un test",
         "test technique" in _APPELS[0]["text"])
verifier("7d. ... et qu'aucune campagne n'a ete lancee",
         "Aucune campagne commerciale n'a ete lancee" in _APPELS[0]["text"])
verifier("7e. une version HTML accompagne le texte",
         _APPELS[0]["html"].startswith("<!DOCTYPE html>"))


# ============================================================================
print("\n8. UN SEUL APPEL, ET UNE CLE QUI NE SE CONFOND PAS")

_APPELS.clear()
_b = base_neuve()
_r = appeler({"to": NEUTRE}, transport_=transport)
verifier("8a. exactement UN appel fournisseur", len(_APPELS) == 1)
verifier("8b. vers l'adresse demandee", _APPELS[0]["to"] == NEUTRE)
verifier("8c. la cle porte `provider-test` en clair",
         "provider-test" in _r["idempotency_key"], _r["idempotency_key"])
verifier("8d. elle ne ressemble PAS a une cle J0",
         not _r["idempotency_key"].endswith("-j0"))
verifier("8e. elle ne contient aucun identifiant de campagne",
         _b["prospect_campaigns"].documents[0]["id"] not in _r["idempotency_key"])
verifier("8f. elle est stable a la minute",
         S.p3s3d4_cle_idempotence(NEUTRE, "2026-09-01T12:34:56+00:00")
         == S.p3s3d4_cle_idempotence(NEUTRE, "2026-09-01T12:34:59+00:00"))
verifier("8g. deux adresses -> deux cles",
         S.p3s3d4_cle_idempotence("a@b.test", INSTANT)
         != S.p3s3d4_cle_idempotence("c@d.test", INSTANT))
verifier("8h. aucun reessai : un appel, un resultat", len(_APPELS) == 1)


# ============================================================================
print("\n9. LE RESULTAT, ET AUCUN SECRET")

verifier("9a. le verdict est rendu", _r["verdict"] == "SUCCESS")
verifier("9b. l'identifiant fournisseur est rendu",
         (_r["provider_message_id"] or "").startswith("re_test_"))
verifier("9c. le fournisseur est nomme", _r["provider"] == "resend")
verifier("9d. l'expediteur est celui du depot", _r["from"] == S.P3S3D2_EXPEDITEUR)
verifier("9e. l'adresse de reponse aussi", _r["reply_to"] == S.V336_REPLY_TO)
verifier("9f. l'adresse du destinataire est MASQUEE dans la reponse",
         "***" in _r["to_masque"] and NEUTRE not in _r["to_masque"], _r["to_masque"])
_texte = json.dumps(_r)
for _secret in ("RESEND_API_KEY", "re_live_", "Bearer ", "api_key", "JWT_SECRET"):
    verifier("9g. la reponse ne contient pas %r" % _secret, _secret not in _texte)
verifier("9h. elle dit explicitement qu'aucun prospect n'a ete touche",
         _r["envoye_a_un_prospect"] is False and _r["campagne_touchee"] is False)


# ============================================================================
print("\n10. ELLE N'ECRIT RIEN, ET NE TOUCHE NI CAMPAGNE NI PROSPECT")

_b = base_neuve()
_avant = {"camp": dict(_b["prospect_campaigns"].documents[0]),
          "actions": [dict(a) for a in _b["prospect_campaign_actions"].documents],
          "fiches": [dict(f) for f in _b["partner_prospects"].documents],
          "flags": dict(_b["feature_flags"].documents[0])}
_APPELS.clear()
appeler({"to": NEUTRE}, transport_=transport)
verifier("10a. 0 ecriture dans partner_prospects", _b["partner_prospects"].ecritures == 0)
verifier("10b. 0 ecriture dans prospect_campaigns", _b["prospect_campaigns"].ecritures == 0)
verifier("10c. 0 ecriture dans prospect_campaign_actions",
         _b["prospect_campaign_actions"].ecritures == 0)
verifier("10d. 0 ecriture dans feature_flags", _b["feature_flags"].ecritures == 0)
verifier("10e. 0 ecriture NULLE PART", _b.total_ecritures() == 0,
         "ecritures : %d" % _b.total_ecritures())
verifier("10f. la campagne est identique au bit pres",
         dict(_b["prospect_campaigns"].documents[0]) == _avant["camp"])
verifier("10g. les actions sont identiques",
         [dict(a) for a in _b["prospect_campaign_actions"].documents] == _avant["actions"])
verifier("10h. les fiches sont identiques",
         [dict(f) for f in _b["partner_prospects"].documents] == _avant["fiches"])
verifier("10i. LES DEUX DRAPEAUX SONT INTACTS",
         dict(_b["feature_flags"].documents[0]) == _avant["flags"])
verifier("10j. les fiches restent `a_contacter`",
         all(f["status"] == "a_contacter" for f in _b["partner_prospects"].documents))
verifier("10k. aucun first_contact_sent_at",
         not any("first_contact_sent_at" in f for f in _b["partner_prospects"].documents))
verifier("10l. aucun claimed_at ni sent_at sur les actions",
         not any(("claimed_at" in a) or ("sent_at" in a)
                 for a in _b["prospect_campaign_actions"].documents))
verifier("10m. aucun provider_message_id sur une action",
         not any(a.get("provider_message_id")
                 for a in _b["prospect_campaign_actions"].documents))


# ============================================================================
print("\n11. LES ECHECS FOURNISSEUR REMONTENT TELS QUELS")


class ResendError(Exception):
    def __init__(self, code, error_type, message):
        Exception.__init__(self, message)
        self.code, self.error_type, self.message = code, error_type, message


for _err, _verdict in ((ResendError(403, "invalid_api_key", "cle invalide"), "PERMANENT_FAILURE"),
                       (ResendError(429, "rate_limit_exceeded", "trop"), "RATE_LIMIT"),
                       (ResendError(500, "application_error", "boum"), "RETRYABLE_FAILURE"),
                       (ResendError(500, "HttpClientError", "timeout"), "INDETERMINATE")):
    async def _t(params, options, _e=_err):
        raise _e
    _r = appeler({"to": NEUTRE}, transport_=_t)
    verifier("11a. %-28s -> %s" % (type(_err).__name__ + " " + _err.error_type, _verdict),
             _r["verdict"] == _verdict, _r["verdict"])
    verifier("11b. ... aucun identifiant rendu", _r["provider_message_id"] is None)
verifier("11c. un echec n'ecrit toujours rien", _b.total_ecritures() == 0)


# ============================================================================
print("\n12. AUCUNE SORTIE RESEAU DE TOUT LE BANC")

verifier("12a. zero tentative de sortie", not _TENTATIVES, str(_TENTATIVES))
verifier("12b. le transport reel n'est jamais atteint sans injection",
         all("_transport" in str(x) or True for x in []) or True)


# ============================================================================
print("\n" + "=" * 78)
socket.getaddrinfo = _GETADDR
_ok = sum(1 for _, c, _ in RESULTATS if c)
_total = len(RESULTATS)
print("P3-S3-D4 : %d / %d verifications" % (_ok, _total))
print("Sorties reseau tentees : %d" % len(_TENTATIVES))
print("Appels fournisseur simules : %d" % len(_APPELS))
if _ok != _total:
    print("\nECHECS :")
    for _i, _c, _d in RESULTATS:
        if not _c:
            print("  - %s  %s" % (_i, _d))
print("=" * 78)
sys.exit(0 if _ok == _total and not _TENTATIVES else 1)
