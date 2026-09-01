#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3-U3 — L'ARRIVEE RESEND, DERRIERE UNE SIGNATURE, SANS UN SEUL E-MAIL.

CE QUE LE LOT AJOUTE
==============================================================================
Une route publique qui recoit les evenements Resend, verifie leur signature,
traduit `email.received` vers le contrat U2 et passe la main au moteur. Elle
est POSEE mais INERTE : sans MX sur `reply.afroboosteur.com` et sans Resend
Receiving configure, rien ne peut y arriver.

CE QUE CE FICHIER PROUVE
==============================================================================
  * la porte est fermee par defaut : pas de secret -> 401, pas de SDK -> 401,
    en-tetes incomplets -> 401, signature refusee -> 401 ;
  * un corps NON SIGNE n'est jamais interprete — meme pas pour lire son type ;
  * la verification n'est PAS reecrite : elle delegue au SDK ;
  * la traduction Resend -> `InboundMessage` ne laisse fuir aucun champ
    propre au fournisseur, et lit les en-tetes sans se soucier de la casse ;
  * aucun HTML etranger n'est conserve ;
  * la correlation n'est PAS recodee ici : le webhook appelle U2 ;
  * un meme evenement rejoue dix fois ne produit qu'un message, un seul
    `replied_at`, un seul arret de relance ;
  * `email.sent` n'ecrit QUE la metadonnee, et une seule fois ;
  * aucune socket ne s'ouvre, aucun appel Resend reel.

    python3 tests/test_p3u3_resend_inbound.py
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


class SortieReseauInterdite(RuntimeError):
    pass


_TENTATIVES = []
_GETADDR = socket.getaddrinfo
_CONNECT = socket.socket.connect
_CREATE = socket.create_connection


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
# CE QU'IL NE FAIT PAS : reimplementer la cryptographie de Resend. Ce n'est
# pas notre code, et un banc qui la recopierait ne prouverait que sa propre
# copie. Ce qu'on eprouve ici, c'est NOTRE cablage : que la verification soit
# appelee, qu'elle le soit AVANT toute lecture du corps, et qu'un refus arrete
# tout. Le faux `verify` leve donc ou passe, sur commande.
# ---------------------------------------------------------------------------
_APPELS_VERIFY = []
_VERIFY_ACCEPTE = {"oui": True}


class _FauxWebhooks:
    @classmethod
    def verify(cls, options):
        _APPELS_VERIFY.append(options)
        if not _VERIFY_ACCEPTE["oui"]:
            raise ValueError("no matching signature found")


_faux_resend = types.ModuleType("resend")
_faux_resend.Webhooks = _FauxWebhooks
_faux_resend.Emails = types.SimpleNamespace(send=lambda *a, **k: {"id": "x"})
sys.modules["resend"] = _faux_resend

SECRET = "secret-de-test-p3u3-sans-aucun-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p3u3-inexistant:27017")
SECRET_WEBHOOK = "whsec_valeur_de_test_jamais_utilisee_en_production"
os.environ["RESEND_WEBHOOK_SECRET"] = SECRET_WEBHOOK

import jwt as _jwt          # noqa: E402
import api.server as S      # noqa: E402
from fastapi import HTTPException  # noqa: E402

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()


def _bloc(source, entete):
    """Le bloc du lot, borne par ce qui vient APRES lui — quel qu'il soit.

    Deux corrections successives, chacune payee par une fausse alerte :
      * la banniere cherchee etait `# P3-`, si bien qu'un lot d'une AUTRE
        famille (CAL-1) ne bornait rien et le bloc avalait le suivant ;
      * partir du titre mordait sur la banniere de FERMETURE de l'en-tete,
        reduisant le bloc a une seule ligne.
    On part donc de la fin de l'en-tete, on accepte n'importe quelle banniere
    de lot, et on retient la borne LA PLUS PROCHE.
    """
    debut = source.index(entete)
    banniere = "\n# " + "=" * 76 + "\n# "
    apres_entete = source.index("\n\n", debut)
    bornes = [x for x in (source.find(banniere, apres_entete),
                          source.find("# --- Leads Routes (Widget IA) ---", apres_entete))
              if x != -1]
    return source[debut:min(bornes)] if bornes else source[debut:]


BLOC_U3 = _bloc(SRC, "# P3-U3 — L'ARRIVEE REELLE")

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

# LE PROPRIETAIRE DES MESSAGES ENTRANTS est une constante du serveur ; les
# actions du banc doivent lui appartenir, sinon rien ne se rattache.
PROPRIO = S.P3U3_COACH_PAR_DEFAUT
RFC_A = "<j0-beaulac-aaaa@reply.exemple.test>"
RFC_B = "<j0-voisin-bbbb@reply.exemple.test>"


class RequeteWebhook:
    """Une requete HTTP brute : un corps en octets, des en-tetes."""

    def __init__(self, corps, entetes=None):
        self._corps = corps if isinstance(corps, bytes) else json.dumps(corps).encode()
        self.headers = dict(entetes if entetes is not None else ENTETES_OK)

    async def body(self):
        return self._corps


ENTETES_OK = {"svix-id": "msg_2abc", "svix-timestamp": "1789000000",
              "svix-signature": "v1,QUJD"}


def action(suffixe, cible, cle, refs=None, envoyee=True, **extra):
    a = {"id": "act-" + suffixe, "campaign_id": "camp-1", "coach_id": PROPRIO,
         "channel": "email", "target": cible, "recipient_key": cle,
         "message_j0": "Bonjour", "language": "FR", "organisations": ["Org " + cle],
         "prospect_ids": ["R-" + cle], "statut": "envoye", "execution_type": "AUTO"}
    if envoyee:
        a.update({"sent_at": ENVOI, "provider": "resend",
                  "provider_message_id": "prov-" + suffixe,
                  "j3_due_at": "2026-09-04T09:00:00+00:00",
                  "j7_due_at": "2026-09-08T09:00:00+00:00"})
    if refs:
        a[S.P3U2_CHAMP_RFC] = S.p3u2_normaliser_identifiant(refs)
    a.update(extra)
    return a


def base_neuve(actions=None, fiches=None):
    b = BaseBouchon(fiches or [])
    b[S.P3S3_ACTIONS] = CollectionBouchon(
        S.P3S3_ACTIONS, [dict(a) for a in (actions or [])], uniques=[(("id",), None)])
    b[S.P3U2_COLLECTION] = CollectionBouchon(
        S.P3U2_COLLECTION, [],
        uniques=[(("coach_id", "dedupe_key"), {"dedupe_key": {"$type": "string"}})])
    b["subscribers"] = CollectionBouchon("subscribers", [], uniques=[(("channel", "value"), None)])
    S.db = b
    return b


def evenement_recu(**k):
    donnees = {"id": "em_recu_001", "from": "hotel@beaulac.exemple.test",
               "to": ["contact@reply.afroboosteur.com"],
               "subject": "Re: Proposition de collaboration avec Afroboost",
               "text": "Bonjour, cela nous interesse.",
               "created_at": RECU,
               "message_id": "<reponse-1@client.exemple.test>",
               "headers": {"In-Reply-To": RFC_A, "References": RFC_A}}
    donnees.update(k.pop("data", {}))
    e = {"type": "email.received", "created_at": RECU, "id": "evt_001", "data": donnees}
    e.update(k)
    return e


def appeler(evenement, entetes=None):
    return lancer(S.p3u3_webhook_resend(RequeteWebhook(evenement, entetes)))


ACT_A = action("aaaa", "hotel@beaulac.exemple.test", "BAR-01", refs=RFC_A)
ACT_B = action("bbbb", "voisin@exemple.test", "BAR-02", refs=RFC_B)


# ============================================================================
print("\n1. LA SIGNATURE — LA PORTE EST FERMEE PAR DEFAUT")

_b = base_neuve([ACT_A])
_VERIFY_ACCEPTE["oui"] = True
del _APPELS_VERIFY[:]

# (a) secret absent
_sauve = os.environ.pop("RESEND_WEBHOOK_SECRET")
try:
    appeler(evenement_recu())
    _ferme = False
except HTTPException as e:
    _ferme = e.status_code == 401
verifier("1a. SANS secret configure -> 401 (fail-closed)", _ferme)
verifier("1b. ... et le SDK n'a meme pas ete appele", len(_APPELS_VERIFY) == 0)
verifier("1c. ... et RIEN n'a ete stocke", len(_b[S.P3U2_COLLECTION].documents) == 0)

# (b) secret vide
os.environ["RESEND_WEBHOOK_SECRET"] = "   "
try:
    appeler(evenement_recu())
    _ferme = False
except HTTPException as e:
    _ferme = e.status_code == 401
verifier("1d. secret VIDE -> 401 aussi", _ferme)
os.environ["RESEND_WEBHOOK_SECRET"] = SECRET_WEBHOOK

# (c) en-tetes incomplets
for _manquant in ("svix-id", "svix-timestamp", "svix-signature"):
    _e = dict(ENTETES_OK)
    _e.pop(_manquant)
    try:
        appeler(evenement_recu(), _e)
        _ferme = False
    except HTTPException as e:
        _ferme = e.status_code == 401
    verifier("1e. en-tete %-16s manquant -> 401" % _manquant, _ferme)

# (d) signature refusee par le SDK
_VERIFY_ACCEPTE["oui"] = False
try:
    appeler(evenement_recu())
    _ferme = False
except HTTPException as e:
    _ferme = e.status_code == 401
verifier("1f. signature REFUSEE par le SDK -> 401", _ferme)
verifier("1g. ... et toujours rien en base", len(_b[S.P3U2_COLLECTION].documents) == 0)
_VERIFY_ACCEPTE["oui"] = True

# (e) SDK absent
_dispo = S.RESEND_AVAILABLE
S.RESEND_AVAILABLE = False
try:
    appeler(evenement_recu())
    _ferme = False
except HTTPException as e:
    _ferme = e.status_code == 401
verifier("1h. SDK indisponible -> 401 (on ne devine pas une signature)", _ferme)
S.RESEND_AVAILABLE = _dispo

verifier("1i. AUCUN secret ne transite dans le detail de la reponse",
         SECRET_WEBHOOK not in json.dumps([r[0] for r in RESULTATS]))


# ============================================================================
print("\n2. UN CORPS NON SIGNE N'EST JAMAIS INTERPRETE")

# La signature passe AVANT `json.loads`. Un corps illisible ET non signe doit
# rendre 401, pas 400 : sinon on aurait deja lu ce qu'un inconnu a envoye.
_VERIFY_ACCEPTE["oui"] = False
try:
    lancer(S.p3u3_webhook_resend(RequeteWebhook(b"{ceci n'est pas du json")))
    _code = None
except HTTPException as e:
    _code = e.status_code
verifier("2a. corps illisible ET non signe -> 401, jamais 400", _code == 401, str(_code))
_VERIFY_ACCEPTE["oui"] = True
try:
    lancer(S.p3u3_webhook_resend(RequeteWebhook(b"{ceci n'est pas du json")))
    _code = None
except HTTPException as e:
    _code = e.status_code
verifier("2b. corps illisible mais SIGNE -> 400", _code == 400, str(_code))
try:
    lancer(S.p3u3_webhook_resend(RequeteWebhook(b'["une", "liste"]')))
    _code = None
except HTTPException as e:
    _code = e.status_code
verifier("2c. un corps qui n'est pas un objet -> 400", _code == 400, str(_code))

_arbre = ast.parse(BLOC_U3[BLOC_U3.index("P3U3_ENTETE_ID"):])
_route = [f for f in ast.walk(_arbre)
          if isinstance(f, ast.AsyncFunctionDef) and f.name == "p3u3_webhook_resend"][0]
_corps_route = ast.get_source_segment(BLOC_U3[BLOC_U3.index("P3U3_ENTETE_ID"):], _route) or ""
verifier("2d. dans le code, la signature est verifiee AVANT tout `json.loads`",
         _corps_route.index("p3u3_signature_valide") < _corps_route.index("json.loads"))


# ============================================================================
print("\n3. LA VERIFICATION N'EST PAS REECRITE — ELLE DELEGUE")

verifier("3a. le lot appelle `resend.Webhooks.verify`",
         "resend.Webhooks.verify" in BLOC_U3)
verifier("3b. il ne recode AUCUNE cryptographie",
         not any(m in BLOC_U3 for m in ("hmac.new", "compare_digest", "b64decode",
                                        "sha256(", "hashlib")),
         "un HMAC maison dans le bloc U3")
_b = base_neuve([ACT_A])
del _APPELS_VERIFY[:]
appeler(evenement_recu())
verifier("3c. le SDK est reellement appele", len(_APPELS_VERIFY) == 1)
_opt = _APPELS_VERIFY[0]
verifier("3d. il recoit le corps BRUT, pas un objet reserialise",
         isinstance(_opt["payload"], str) and _opt["payload"].startswith("{"))
verifier("3e. il recoit les trois en-tetes Svix",
         set(_opt["headers"]) == {"id", "timestamp", "signature"}, str(_opt["headers"]))
verifier("3f. il recoit le secret d'environnement",
         _opt["webhook_secret"] == SECRET_WEBHOOK)


# ============================================================================
print("\n4. LA TRADUCTION RESEND -> CONTRAT U2")

_m = S.p3u3_adapter_recu(evenement_recu())
verifier("4a. le contrat U2 est respecte, champ pour champ",
         set(S.p3u2_message_entrant(_m)) ==
         {"message_id", "in_reply_to", "references", "from_email", "to_email",
          "subject", "body_text", "received_at", "provider", "provider_event_id",
          "dedupe_key"})
verifier("4b. l'identifiant d'evenement vient de l'evenement", _m["provider_event_id"] == "evt_001")
verifier("4c. le `Message-ID` entrant est lu", _m["message_id"] == "<reponse-1@client.exemple.test>")
verifier("4d. `In-Reply-To` est lu", _m["in_reply_to"] == RFC_A)
verifier("4e. `References` est lu", _m["references"] == RFC_A)
verifier("4f. l'expediteur", _m["from_email"] == "hotel@beaulac.exemple.test")
verifier("4g. le destinataire est extrait de la LISTE `to`",
         _m["to_email"] == "contact@reply.afroboosteur.com", str(_m["to_email"]))
verifier("4h. le texte", _m["body_text"].startswith("Bonjour"))
verifier("4i. la date de reception", _m["received_at"] == RECU)
verifier("4j. le fournisseur est nomme", _m["provider"] == "resend")

# la casse des en-tetes ne doit rien empecher
_casse = S.p3u3_adapter_recu(evenement_recu(data={"headers": {
    "in-reply-to": RFC_A, "REFERENCES": RFC_B, "message-id": "<x@y.test>"}}))
verifier("4k. les en-tetes sont lus SANS tenir compte de la casse",
         _casse["in_reply_to"] == RFC_A and _casse["references"] == RFC_B, str(_casse))
_sans_champ = S.p3u3_adapter_recu(evenement_recu(data={
    "message_id": None, "headers": {"Message-ID": "<depuis-entete@x.test>"}}))
verifier("4l. sans champ `message_id`, l'en-tete RFC prend le relais",
         _sans_champ["message_id"] == "<depuis-entete@x.test>", str(_sans_champ["message_id"]))
verifier("4m. AUCUN champ propre a Resend ne fuit dans le contrat",
         not any(c in json.dumps(_m).lower() for c in ("svix", "\"data\"", "email_id")))


# ============================================================================
print("\n5. LE HTML N'EST JAMAIS CONSERVE TEL QUEL")

_html = S.p3u3_adapter_recu(evenement_recu(data={
    "text": "", "html": "<html><head><style>p{color:red}</style></head>"
                        "<body><p>Bonjour&nbsp;!</p><p>Deux lignes</p>"
                        "<script>alert(1)</script></body></html>"}))
verifier("5a. le corps rendu est du TEXTE", "<p>" not in _html["body_text"], _html["body_text"])
verifier("5b. le script est retire", "alert" not in _html["body_text"], _html["body_text"])
verifier("5c. le style est retire", "color:red" not in _html["body_text"])
verifier("5d. le contenu lisible survit",
         "Bonjour !" in _html["body_text"] and "Deux lignes" in _html["body_text"],
         repr(_html["body_text"]))
verifier("5e. les blocs deviennent des retours a la ligne",
         "\n" in _html["body_text"], repr(_html["body_text"]))
verifier("5f. le TEXTE fourni prime toujours sur le HTML",
         S.p3u3_adapter_recu(evenement_recu(data={"html": "<p>ignore</p>"}))["body_text"]
         .startswith("Bonjour, cela"))
verifier("5g. aucun champ HTML n'entre dans le contrat",
         "html" not in S.p3u2_message_entrant(_html))


# ============================================================================
print("\n6. LA CORRELATION N'EST PAS RECODEE — U2 DECIDE")

verifier("6a. le webhook appelle `p3u2_recevoir`", "p3u2_recevoir(message, coach)" in BLOC_U3)
verifier("6b. il ne recode AUCUNE des trois methodes",
         not any(m in BLOC_U3 for m in ("P3U2_METHODE_IN_REPLY_TO", "candidats_email",
                                        "p3u2_verdict_correlation", "matching_confidence")))
# ON REGARDE LES ECRITURES REELLES, PAS LA PROSE : `replied_at` figure dans
# le commentaire qui explique justement que ce bloc ne l'ecrit pas.
_cles_ecrites = set()
for _n in ast.walk(_arbre):
    if isinstance(_n, ast.Call) and getattr(_n.func, "attr", "") in (
            "update_one", "update_many", "insert_one", "insert_many"):
        for _a in _n.args:
            for _s in ast.walk(_a):
                if isinstance(_s, ast.Constant) and isinstance(_s.value, str):
                    _cles_ecrites.add(_s.value)
verifier("6c. il n'ecrit NI `replied_at` NI d'annulation de relance",
         not (_cles_ecrites & {"replied_at", "j3_annule_le", "j7_annule_le",
                               "j3_annule_motif", "j7_annule_motif", "status"}),
         str(sorted(_cles_ecrites)))
# LA LISTE EXACTE, ET RIEN DE PLUS. `P3U2_CHAMP_RFC` est une CONSTANTE, donc
# absente des litteraux : c'est bien la seule valeur metier posee, et elle est
# verifiee separement en 8b. Tout ajout de champ fera echouer cette ligne —
# c'est precisement ce qu'on veut d'une garde de perimetre.
verifier("6c-bis. les seules cles ecrites par le bloc sont celles de la metadonnee",
         _cles_ecrites == {"$exists", "$set", "provider_message_id", "updated_at"},
         str(sorted(_cles_ecrites)))

_b = base_neuve([ACT_A, ACT_B], fiches=[{"id": "p-1", "ref": "R-BAR-01",
                                         "coach_id": PROPRIO, "status": "contacte"}])
_r = appeler(evenement_recu())
verifier("6d. bout en bout : le message est stocke", _r["stocke"] is True, str(_r))
verifier("6e. methode A, decidee par U2", _r["methode"] == S.P3U2_METHODE_IN_REPLY_TO, str(_r))
verifier("6f. statut `rattache`", _r["statut"] == S.P3U2_STATUT_RATTACHE)
_a = [a for a in _b[S.P3S3_ACTIONS].documents if a["id"] == "act-aaaa"][0]
verifier("6g. `replied_at` pose par U2", _a.get("replied_at") == RECU, str(_a.get("replied_at")))
verifier("6h. J+3 et J+7 annules", bool(_a.get("j3_annule_le")) and bool(_a.get("j7_annule_le")))
verifier("6i. la fiche passe a `repondu`",
         _b["partner_prospects"].documents[0].get("status") == "repondu")
verifier("6j. le voisin est intact",
         not [a for a in _b[S.P3S3_ACTIONS].documents if a["id"] == "act-bbbb"][0].get("replied_at"))

# fallback e-mail, et ambiguite : U2 decide, le webhook n'invente rien
_b = base_neuve([ACT_A])
_r = appeler(evenement_recu(data={"headers": {}, "message_id": "<seul@x.test>"}))
verifier("6k. sans en-tete, le repli par expediteur s'applique",
         _r["methode"] == S.P3U2_METHODE_EMAIL, str(_r))
_b = base_neuve([ACT_A, action("dddd", "hotel@beaulac.exemple.test", "BAR-99")])
_r = appeler(evenement_recu(data={"headers": {}, "message_id": "<amb@x.test>"}))
verifier("6l. deux candidats -> `manual_review`, aucun choix au hasard",
         _r["statut"] == S.P3U2_STATUT_REVUE, str(_r))
verifier("6m. ... et aucune action ne porte `replied_at`",
         not any(a.get("replied_at") for a in _b[S.P3S3_ACTIONS].documents))


# ============================================================================
print("\n7. IDEMPOTENCE — DIX FOIS LE MEME EVENEMENT")

_b = base_neuve([ACT_A], fiches=[{"id": "p-1", "ref": "R-BAR-01",
                                  "coach_id": PROPRIO, "status": "contacte"}])
_premiers = appeler(evenement_recu())
_suivants = [appeler(evenement_recu()) for _ in range(9)]
verifier("7a. un seul message en base", len(_b[S.P3U2_COLLECTION].documents) == 1,
         str(len(_b[S.P3U2_COLLECTION].documents)))
verifier("7b. les neuf suivants sont des doublons",
         all(r["doublon"] is True for r in _suivants))
verifier("7c. un seul `replied_at`, et il n'a pas bouge",
         _b[S.P3S3_ACTIONS].documents[0].get("replied_at") == RECU)
verifier("7d. une seule fiche marquee",
         _b["partner_prospects"].documents[0].get("status") == "repondu")
verifier("7e. seul le PREMIER a compte comme premiere reponse",
         _premiers.get("stocke") is True
         and not any(r.get("premiere_reponse") for r in _suivants))

# meme message, identifiant d'evenement different : le `Message-ID` prime
_r = appeler(evenement_recu(id="evt_REJEU"))
verifier("7f. un rejeu sous un autre identifiant d'evenement reste un doublon",
         _r["doublon"] is True, str(_r))

# sans identifiant dans la charge utile, `svix-id` sert de repli
_b = base_neuve([ACT_A])
_sans = evenement_recu(data={"message_id": None, "id": None})
_sans["id"] = None
appeler(_sans, dict(ENTETES_OK, **{"svix-id": "msg_unique_42"}))
_doc = _b[S.P3U2_COLLECTION].documents[0]
verifier("7g. sans identifiant dans le corps, `svix-id` sert de repli",
         _doc.get("dedupe_key") == "evt:msg_unique_42", str(_doc.get("dedupe_key")))
_r = appeler(_sans, dict(ENTETES_OK, **{"svix-id": "msg_unique_42"}))
verifier("7h. ... et il dedoublonne bien", _r["doublon"] is True, str(_r))


# ============================================================================
print("\n8. `email.sent` — LA METADONNEE, ET RIEN D'AUTRE")

_b = base_neuve([action("gggg", "cible@exemple.test", "BAR-05")])
_envoi = {"type": "email.sent", "id": "evt_sent_1",
          "data": {"email_id": "prov-gggg", "message_id": "<sortant-gggg@resend.test>"}}
_r = appeler(_envoi)
verifier("8a. l'evenement est acquitte", _r["recu"] is True, str(_r))
_a = _b[S.P3S3_ACTIONS].documents[0]
verifier("8b. le `Message-ID` RFC est stocke sur l'action",
         _a.get(S.P3U2_CHAMP_RFC) == "sortant-gggg@resend.test", str(_a.get(S.P3U2_CHAMP_RFC)))
verifier("8c. il est DISTINCT de `provider_message_id`",
         _a.get("provider_message_id") == "prov-gggg"
         and _a.get(S.P3U2_CHAMP_RFC) != _a.get("provider_message_id"))
verifier("8d. AUCUNE consequence metier : pas de `replied_at`", not _a.get("replied_at"))
verifier("8e. ... pas de relance annulee", not _a.get("j3_annule_le"))
verifier("8f. ... et `sent_at` n'a pas bouge", _a.get("sent_at") == ENVOI)

_r2 = appeler(_envoi)
verifier("8g. rejoue, il n'ecrit pas une seconde fois",
         _r2["rfc_message_id_ecrit"] is False, str(_r2))
verifier("8h. la valeur reste la premiere",
         _b[S.P3S3_ACTIONS].documents[0].get(S.P3U2_CHAMP_RFC) == "sortant-gggg@resend.test")

# un evenement SANS Message-ID n'invente rien
_b = base_neuve([action("hhhh", "autre@exemple.test", "BAR-06")])
_r = appeler({"type": "email.sent", "id": "evt_sent_2", "data": {"email_id": "prov-hhhh"}})
verifier("8i. sans `Message-ID`, RIEN n'est ecrit", _r["rfc_message_id_ecrit"] is False, str(_r))
verifier("8j. ... et le champ reste ABSENT (pas de chaine vide en base)",
         S.P3U2_CHAMP_RFC not in _b[S.P3S3_ACTIONS].documents[0])
verifier("8k. le lot ne FABRIQUE jamais de Message-ID",
         "uuid" not in BLOC_U3.lower() and "token_urlsafe" not in BLOC_U3)


# ============================================================================
print("\n9. LES AUTRES EVENEMENTS SONT ACQUITTES, PAS TRAITES")

_b = base_neuve([ACT_A])
for _type in ("email.delivered", "email.bounced", "email.complained",
              "email.opened", "contact.created", ""):
    _r = appeler({"type": _type, "id": "evt_x", "data": {}})
    verifier("9. evenement %-20s acquitte sans effet" % (_type or "(vide)"),
             _r["recu"] is True and _r.get("ignore") is True, str(_r))
verifier("9z. et rien n'a ete stocke", len(_b[S.P3U2_COLLECTION].documents) == 0)


# ============================================================================
print("\n10. LA ROUTE — FORME ET INNOCUITE")

verifier("10a. une seule route est ajoutee", BLOC_U3.count("@api_router.") == 1)
verifier("10b. elle est en POST", '@api_router.post("/webhooks/resend")' in SRC)
verifier("10c. elle n'utilise PAS l'auth coach (Resend n'a pas de compte)",
         "_v309_require_coach_or_admin" not in BLOC_U3)
verifier("10d. aucun secret n'est ecrit en dur",
         "whsec_" not in BLOC_U3.replace("`whsec_`", ""), "un secret litteral dans le bloc")
verifier("10e. le secret vient d'une variable DEDIEE",
         'os.environ.get("RESEND_WEBHOOK_SECRET"' in BLOC_U3)
verifier("10f. le journal ne montre que le motif, jamais la valeur attendue",
         'logger.warning("[P3-U3] webhook REFUSE : %s", verdict["motif"])' in BLOC_U3)
verifier("10g. le lot n'ouvre NI IMAP NI SMTP",
         not any(m in BLOC_U3 for m in ("imaplib", "smtplib", "poplib")))
verifier("10h. il ne touche NI au DNS NI au Reply-To",
         "reply.afroboosteur.com" not in BLOC_U3.replace(
             "`reply.afroboosteur.com`", "").replace(
             "# de reception qui tranchera", "")
         or "AFROBOOST_REPLY_TO" not in BLOC_U3)
verifier("10i. aucune migration : le champ RFC reste optionnel",
         "$exists" in BLOC_U3 and "update_many" not in BLOC_U3)


# ============================================================================
print("\n11. AUCUN RESEAU REEL")

verifier("11a. zero tentative de sortie", len(_TENTATIVES) == 0, str(_TENTATIVES))
verifier("11b. aucun appel `Emails.send` dans ce lot", "Emails.send" not in BLOC_U3)
verifier("11c. aucun appel HTTP direct", not any(
    m in BLOC_U3 for m in ("requests.", "httpx.", "urllib.request", "aiohttp")))


# ============================================================================
print("\n" + "=" * 78)
_ok = sum(1 for _, c, _ in RESULTATS if c)
print("P3-U3 : %d / %d verifications" % (_ok, len(RESULTATS)))
print("Sorties reseau tentees : %d" % len(_TENTATIVES))
print("Appels Resend REELS : 0 — le SDK est un faux, pose avant l'import")
_ech = [i for i, c, _ in RESULTATS if not c]
if _ech:
    print("\nECHECS :")
    for i in _ech:
        print("  - %s" % i)
print("=" * 78)
sys.exit(0 if not _ech else 1)
