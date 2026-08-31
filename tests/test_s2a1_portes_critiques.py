#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SECURITY-S2-A1 — LES TROIS PORTES CRITIQUES SONT-ELLES VRAIMENT FERMEES ?

CE QUE CE LOT FERME, ET POURQUOI C'ETAIT GRAVE
==============================================================================
Trois routes n'avaient AUCUNE authentification :

  POST /api/campaigns/send-email       relais de courrier ouvert
  POST /api/campaigns/send-bulk-email  le meme, sans plafond de destinataires
  PUT  /api/whatsapp-config            ecriture des identifiants du numero business

Sur les deux premieres, `X-User-Email` n'etait lu que pour decider d'un DEBIT DE
CREDITS, jamais d'un acces : `if coach_email and not is_super_admin(...)`.
En-tete ABSENT -> condition fausse -> aucun controle, aucun debit, et l'e-mail
part quand meme, vers l'adresse de son choix. Sur la troisieme, la signature ne
recevait meme pas `Request` : authentifier y etait structurellement impossible.

CE QUE CE FICHIER PROUVE, ET COMMENT
==============================================================================
Il ne fait partir AUCUN e-mail, AUCUN WhatsApp, et n'ecrit dans AUCUNE base.

  * le moteur d'envoi (`resend.Emails.send`) est remplace par un ESPION qui
    compte les appels ET retient ce qu'on lui a demande d'envoyer ;
  * la base est un bouchon qui HONORE les filtres et COMPTE les ecritures ;
  * la couche reseau elle-meme est neutralisee : toute tentative de connexion
    TCP est comptee et refusee (section 9). Un envoi reel ne peut pas se cacher.

Deux moities, et il faut les deux — c'est la regle V310c :
  * la porte REFUSE tout ce qui n'est pas un coach (sections 2, 3, 5) ;
  * la porte S'OUVRE pour le coach legitime, et ce qui sort est exactement ce
    qu'on a demande (section 4).

Les jetons sont FABRIQUES ICI, avec un secret FICTIF et des adresses FICTIVES.
Aucune valeur reelle — ni secret Meta, ni jeton Twilio — n'entre dans ce fichier.

LE PIEGE QUI JUSTIFIE UNE PARTIE DES VERIFICATIONS
==============================================================================
`require_auth` decode un JWT SANS tester `payload["type"]`. L'employer ici
aurait transforme un jeton ABONNE en identite coach : une escalade de
privileges installee par le correctif lui-meme. Les gardes retenues
(`_v309_require_coach_or_admin`, `_v411_exiger_super_admin`) passent toutes deux
par `_v311_coach_email_from_jwt`, qui rejette `type == "subscriber"`.

Mais ce test de type NE SUFFIT PAS : un TROISIEME type signe existe et circule
en production, `type: "subscriber_space"` (jeton d'espace abonne emis apres
verification OTP). Il FRANCHIT le test de type et ressort avec l'e-mail du
membre. Seul le controle de ROLE qui suit l'arrete. C'est pourquoi on ne
verifie pas seulement « le jeton abonne est refuse », mais « les DEUX jetons
non-coach sont refuses » — et pourquoi une garde qui se contenterait de
`_v311_coach_email_from_jwt` seul serait un trou.

    python3 tests/test_s2a1_portes_critiques.py
"""
import ast
import asyncio
import os
import re
import socket
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

RESULTATS = []


def verifier(intitule, condition, detail=""):
    RESULTATS.append((intitule, bool(condition), detail))
    marque = "OK  " if condition else "ECHEC"
    ligne = "  %-6s %s" % (marque, intitule)
    if detail and not condition:
        ligne += "\n           -> %s" % detail
    print(ligne)
    return bool(condition)


# ============================================================================
# Bouchons : aucune base, aucun reseau, aucun envoi
# ============================================================================

# Valeurs FICTIVES uniquement. Le secret ne sert qu'a signer les jetons de ce
# fichier ; il n'a aucun rapport avec celui de la production.
SECRET_FICTIF = "secret-de-test-s2a1-sans-aucun-rapport-avec-la-production"
ADMIN_FICTIF = "admin.fictif@exemple.test"
COACH_FICTIF = "coach.fictif@exemple.test"
MEMBRE_FICTIF = "membre.fictif@exemple.test"
INCONNU_FICTIF = "inconnu.fictif@exemple.test"

os.environ["JWT_SECRET"] = SECRET_FICTIF
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-inexistant:27017")

import jwt as pyjwt  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402


def _jeton(payload, minutes=60):
    maintenant = datetime.now(timezone.utc)
    corps = dict(payload)
    corps["iat"] = int(maintenant.timestamp())
    corps["exp"] = int((maintenant + timedelta(minutes=minutes)).timestamp())
    jeton = pyjwt.encode(corps, SECRET_FICTIF, algorithm="HS256")
    return jeton.decode("utf-8") if isinstance(jeton, bytes) else jeton


JETON_ADMIN = _jeton({"email": ADMIN_FICTIF, "role": "super_admin"})
JETON_COACH = _jeton({"email": COACH_FICTIF, "role": "coach"})
JETON_ABONNE = _jeton({"type": "subscriber", "code": "AFR-TEST01", "email": MEMBRE_FICTIF})
JETON_ESPACE = _jeton({
    "type": "subscriber_space", "code": "AFR-TEST01", "email": MEMBRE_FICTIF,
    "coach_id": COACH_FICTIF, "slug": "test", "jti": "test-jti",
})
JETON_MAUVAIS_SECRET = pyjwt.encode(
    {"email": ADMIN_FICTIF, "role": "super_admin",
     "exp": int((datetime.now(timezone.utc) + timedelta(minutes=60)).timestamp())},
    "un-autre-secret-qui-n-est-pas-le-bon", algorithm="HS256")
if isinstance(JETON_MAUVAIS_SECRET, bytes):
    JETON_MAUVAIS_SECRET = JETON_MAUVAIS_SECRET.decode("utf-8")


class RequeteFictive:
    """Le strict minimum dont les gardes et les routes ont besoin."""

    def __init__(self, jeton=None, entete_email=None, corps=None):
        entetes = {}
        if jeton:
            entetes["Authorization"] = "Bearer " + jeton
        if entete_email:
            entetes["X-User-Email"] = entete_email
        self.headers = entetes
        self._corps = corps if corps is not None else {}

    async def json(self):
        return self._corps


class CollectionBouchon:
    """`find_one`/`find` HONORENT le filtre ; `update_one` COMPTE sans ecrire.

    Le bouchon doit respecter le filtre, sinon il ment : une premiere version
    renvoyait le meme document coach quelle que soit la requete, ce qui faisait
    passer pour coach n'importe quelle adresse — et ce fichier annoncait alors
    une faille inexistante sur les jetons d'espace abonne. Un bouchon trop
    complaisant est aussi trompeur qu'un test absent.
    """

    def __init__(self, documents=None):
        self.documents = list(documents or [])
        self.ecritures = 0

    def _correspond(self, doc, filtre):
        for cle, val in (filtre or {}).items():
            if str(cle).startswith("$"):
                continue
            if isinstance(val, dict):
                if "$in" in val and doc.get(cle) not in val["$in"]:
                    return False
                continue
            if doc.get(cle) != val:
                return False
        return True

    async def find_one(self, filtre=None, *a, **k):
        for doc in self.documents:
            if self._correspond(doc, filtre):
                return doc
        return None

    def find(self, filtre=None, *a, **k):
        documents = [d for d in self.documents if self._correspond(d, filtre)]

        class _Curseur:
            def __aiter__(self_inner):
                self_inner._i = iter(documents)
                return self_inner

            async def __anext__(self_inner):
                try:
                    return next(self_inner._i)
                except StopIteration:
                    raise StopAsyncIteration

        return _Curseur()

    async def update_one(self, *a, **k):
        self.ecritures += 1
        return None


class BaseBouchon:
    def __init__(self):
        # COACH_FICTIF est le SEUL coach enregistre. Personne d'autre.
        self.coaches = CollectionBouchon([{"email": COACH_FICTIF, "credits": 0}])
        self.coach_auth = CollectionBouchon([])
        self.whatsapp_config = CollectionBouchon([])
        self.feature_flags = CollectionBouchon([{"id": "feature_flags"}])
        self.subscribers = CollectionBouchon([])   # aucun refus C3
        self.payment_links = CollectionBouchon([])  # rempli au coup par coup

    def __getattr__(self, nom):
        return CollectionBouchon([])


import api.server as S  # noqa: E402

S.db = BaseBouchon()
S.SUPER_ADMIN_EMAILS = [ADMIN_FICTIF]

# ---------------------------------------------------------------------------
# L'ESPION D'ENVOI. Il ne se contente pas de compter : il retient CE QU'ON LUI A
# DEMANDE D'ENVOYER. Compter les appels prouve qu'aucun e-mail ne part quand la
# porte refuse ; retenir le contenu prouve, quand elle s'ouvre, que ce qui sort
# est exactement ce qu'on a demande — et, pour notify-coach, que le
# destinataire n'a pas ete choisi par le client.
# ---------------------------------------------------------------------------
ENVOIS = []


class ResendBouchon:
    class Emails:
        @staticmethod
        def send(params):
            ENVOIS.append(dict(params))
            return {"id": "identifiant-fictif-%d" % len(ENVOIS)}


S.resend = ResendBouchon
S.RESEND_AVAILABLE = True
S.RESEND_API_KEY = "cle-fictive-de-test"

# ---------------------------------------------------------------------------
# NEUTRALISATION DU RESEAU. Un envoi reel passerait forcement par une connexion
# TCP : on la rend impossible et on la compte. C'est la preuve qu'aucun appel
# externe ne s'est cache derriere un bouchon oublie.
# ---------------------------------------------------------------------------
RESEAU = {"tentatives": []}
_connect_reel = socket.socket.connect
_create_reel = socket.create_connection


def _connect_interdit(self, adresse, *a, **k):
    RESEAU["tentatives"].append(str(adresse))
    raise OSError("connexion reseau interdite pendant ce test : %s" % (adresse,))


def _create_interdit(adresse, *a, **k):
    RESEAU["tentatives"].append(str(adresse))
    raise OSError("connexion reseau interdite pendant ce test : %s" % (adresse,))


socket.socket.connect = _connect_interdit
socket.create_connection = _create_interdit

# Les envois passent par `asyncio.to_thread`. On l'execute en direct : plus
# simple a suivre, et surtout aucun fil de discussion ne peut survivre au test.
_to_thread_reel = asyncio.to_thread if hasattr(asyncio, "to_thread") else None


async def _to_thread_direct(fonction, *a, **k):
    return fonction(*a, **k)


asyncio.to_thread = _to_thread_direct
S.asyncio.to_thread = _to_thread_direct

try:
    asyncio.set_event_loop(asyncio.new_event_loop())
except Exception:
    pass


def appeler(coroutine):
    """Execute la route et rend (statut, valeur). 403/400/402 -> le code."""
    try:
        return 200, asyncio.get_event_loop().run_until_complete(coroutine)
    except S.HTTPException as e:
        return e.status_code, getattr(e, "detail", "")


class TachesFictives:
    """Retient la tache de fond au lieu de la lancer — on decide QUAND l'executer."""

    def __init__(self):
        self.taches = []

    def add_task(self, fonction, *a, **k):
        self.taches.append((fonction, a, k))

    def executer_tout(self):
        for fonction, a, k in self.taches:
            resultat = fonction(*a, **k)
            if asyncio.iscoroutine(resultat):
                asyncio.get_event_loop().run_until_complete(resultat)


# ============================================================================
print("=" * 78)
print("SECURITY-S2-A1 — TROIS PORTES CRITIQUES")
print("=" * 78)

print("\n=== 1. LES GARDES REJETTENT LES JETONS QUI NE SONT PAS DES COACHS ===")

verifier("1a. un jeton ABONNE ne produit AUCUNE identite coach",
         S._v311_coach_email_from_jwt(RequeteFictive(JETON_ABONNE)) == "",
         "type == 'subscriber' doit etre rejete par _v311")

verifier("1b. un jeton d'ESPACE ABONNE franchit le test de type — le piege est reel",
         S._v311_coach_email_from_jwt(RequeteFictive(JETON_ESPACE)) == MEMBRE_FICTIF,
         "si ce test casse, le raisonnement du lot doit etre relu")

verifier("1c. ... mais le controle de ROLE l'arrete",
         asyncio.get_event_loop().run_until_complete(
             S._v309_is_coach_or_admin(MEMBRE_FICTIF)) is False)

verifier("1d. un jeton signe d'un AUTRE secret ne vaut rien",
         S._v311_coach_email_from_jwt(RequeteFictive(JETON_MAUVAIS_SECRET)) == "")

verifier("1e. `X-User-Email` seul ne produit AUCUNE identite signee",
         S._v311_coach_email_from_jwt(RequeteFictive(None, ADMIN_FICTIF)) == "")

verifier("1f. un jeton coach legitime, lui, est reconnu",
         S._v311_coach_email_from_jwt(RequeteFictive(JETON_COACH)) == COACH_FICTIF)


print("\n=== 2. POST /campaigns/send-email — LA PORTE REFUSE ===")

CORPS_ATTAQUE = {"to_email": "victime@exemple.test", "to_name": "V",
                 "subject": "sujet", "message": "corps"}

for intitule, requete in [
    ("2a. anonyme -> 403", RequeteFictive(None, None, CORPS_ATTAQUE)),
    ("2b. `X-User-Email` d'un admin, forge, sans jeton -> 403",
     RequeteFictive(None, ADMIN_FICTIF, CORPS_ATTAQUE)),
    ("2c. jeton ABONNE -> 403", RequeteFictive(JETON_ABONNE, None, CORPS_ATTAQUE)),
    ("2d. jeton d'ESPACE ABONNE -> 403", RequeteFictive(JETON_ESPACE, None, CORPS_ATTAQUE)),
    ("2e. jeton signe d'un autre secret -> 403",
     RequeteFictive(JETON_MAUVAIS_SECRET, None, CORPS_ATTAQUE)),
    ("2f. jeton d'un e-mail inconnu de la base -> 403",
     RequeteFictive(_jeton({"email": INCONNU_FICTIF, "role": "coach"}), None, CORPS_ATTAQUE)),
]:
    avant = len(ENVOIS)
    statut, _ = appeler(S.send_campaign_email(requete))
    verifier(intitule, statut == 403 and len(ENVOIS) == avant,
             "statut=%s, envois declenches=%s" % (statut, len(ENVOIS) - avant))

verifier("2g. AUCUN e-mail n'est parti pendant toute la section 2",
         len(ENVOIS) == 0, "compteur=%s" % len(ENVOIS))


print("\n=== 3. POST /campaigns/send-bulk-email — LA PORTE REFUSE, 10 DESTINATAIRES ===")

DIX = [{"email": "cible%02d@exemple.test" % i, "name": "Cible %d" % i} for i in range(1, 11)]
CORPS_MASSE = {"recipients": DIX, "subject": "sujet", "message": "corps"}

for intitule, requete in [
    ("3a. anonyme, 10 destinataires -> 403", RequeteFictive(None, None, CORPS_MASSE)),
    ("3b. `X-User-Email` forge, 10 destinataires -> 403",
     RequeteFictive(None, ADMIN_FICTIF, CORPS_MASSE)),
    ("3c. jeton ABONNE, 10 destinataires -> 403",
     RequeteFictive(JETON_ABONNE, None, CORPS_MASSE)),
    ("3d. jeton d'ESPACE ABONNE, 10 destinataires -> 403",
     RequeteFictive(JETON_ESPACE, None, CORPS_MASSE)),
    ("3e. jeton signe d'un autre secret, 10 destinataires -> 403",
     RequeteFictive(JETON_MAUVAIS_SECRET, None, CORPS_MASSE)),
    ("3f. jeton d'un e-mail inconnu de la base, 10 destinataires -> 403",
     RequeteFictive(_jeton({"email": INCONNU_FICTIF, "role": "coach"}), None, CORPS_MASSE)),
]:
    taches = TachesFictives()
    avant = len(ENVOIS)
    statut, _ = appeler(S.send_bulk_campaign_email(requete, taches))
    verifier(intitule,
             statut == 403 and len(ENVOIS) == avant and not taches.taches,
             "statut=%s envois=%s taches=%s" % (statut, len(ENVOIS) - avant, len(taches.taches)))

verifier("3g. aucun envoi ni aucune tache de fond de tout le fichier jusqu'ici",
         len(ENVOIS) == 0, "compteur=%s" % len(ENVOIS))


print("\n=== 4. LES CHEMINS LEGITIMES PASSENT — ET CE QUI SORT EST EXACT ===")
print("     (moteur d'envoi mocke : rien ne quitte cette machine)")

DEST_FICTIF = "destinataire.fictif@exemple.test"
SUJET_FICTIF = "Sujet fictif S2-A1"
MESSAGE_FICTIF = "Corps de message fictif, ligne unique."

CORPS_VALIDE = {"to_email": DEST_FICTIF, "to_name": "Destinataire Fictif",
                "subject": SUJET_FICTIF, "message": MESSAGE_FICTIF, "media_url": None}

# --- 4.1 send-email avec un jeton COACH legitime -----------------------------
ENVOIS.clear()
credits_avant = S.db.coaches.ecritures
statut, reponse = appeler(S.send_campaign_email(
    RequeteFictive(JETON_COACH, None, dict(CORPS_VALIDE))))

verifier("4a. COACH legitime : la route repond en succes",
         statut == 200 and isinstance(reponse, dict) and reponse.get("success") is True,
         "statut=%s reponse=%s" % (statut, reponse))
verifier("4b. ... exactement UN appel au moteur d'envoi",
         len(ENVOIS) == 1, "appels=%d" % len(ENVOIS))
verifier("4c. ... vers le destinataire fictif EXACT, et lui seul",
         len(ENVOIS) == 1 and ENVOIS[0].get("to") == [DEST_FICTIF],
         "to=%s" % (ENVOIS[0].get("to") if ENVOIS else None))
verifier("4d. ... avec le sujet fictif EXACT",
         len(ENVOIS) == 1 and ENVOIS[0].get("subject") == SUJET_FICTIF,
         "subject=%s" % (ENVOIS[0].get("subject") if ENVOIS else None))
verifier("4e. ... et le message fictif present dans le corps envoye",
         len(ENVOIS) == 1 and MESSAGE_FICTIF in ENVOIS[0].get("html", ""))
verifier("4f. ... et la route renvoie bien ce destinataire",
         reponse.get("to") == DEST_FICTIF if isinstance(reponse, dict) else False)

# --- 4.2 send-email avec un jeton SUPER-ADMIN --------------------------------
ENVOIS.clear()
statut, reponse = appeler(S.send_campaign_email(
    RequeteFictive(JETON_ADMIN, None, dict(CORPS_VALIDE))))
verifier("4g. SUPER-ADMIN : succes, exactement UN envoi, meme destinataire",
         statut == 200 and reponse.get("success") is True
         and len(ENVOIS) == 1 and ENVOIS[0].get("to") == [DEST_FICTIF],
         "statut=%s envois=%d" % (statut, len(ENVOIS)))

# --- 4.3 bulk avec un jeton COACH legitime -----------------------------------
TROIS = [
    {"email": "bulk01@exemple.test", "name": "Bulk Un"},
    {"email": "bulk02@exemple.test", "name": "Bulk Deux"},
    {"email": "bulk03@exemple.test", "name": "Bulk Trois"},
]
ENVOIS.clear()
taches = TachesFictives()
statut, reponse = appeler(S.send_bulk_campaign_email(
    RequeteFictive(JETON_COACH, None,
                   {"recipients": TROIS, "subject": SUJET_FICTIF, "message": MESSAGE_FICTIF}),
    taches))

verifier("4h. BULK, coach legitime : la route accepte",
         statut == 200 and reponse.get("success") is True
         and reponse.get("total_recipients") == 3,
         "statut=%s reponse=%s" % (statut, reponse))
verifier("4i. ... UNE seule tache de fond planifiee, pas davantage",
         len(taches.taches) == 1, "taches=%d" % len(taches.taches))
verifier("4j. ... et AUCUN envoi tant que la tache n'a pas tourne",
         len(ENVOIS) == 0, "envois=%d" % len(ENVOIS))

taches.executer_tout()

verifier("4k. tache executee : EXACTEMENT 3 envois, ni plus ni moins",
         len(ENVOIS) == 3, "envois=%d" % len(ENVOIS))
verifier("4l. ... vers les 3 destinataires fictifs EXACTS",
         [e.get("to") for e in ENVOIS] == [[r["email"]] for r in TROIS],
         "to=%s" % [e.get("to") for e in ENVOIS])
verifier("4m. ... tous avec le sujet fictif",
         all(e.get("subject") == SUJET_FICTIF for e in ENVOIS))

# --- 4.4 bulk avec un jeton SUPER-ADMIN --------------------------------------
ENVOIS.clear()
taches = TachesFictives()
statut, reponse = appeler(S.send_bulk_campaign_email(
    RequeteFictive(JETON_ADMIN, None,
                   {"recipients": TROIS, "subject": SUJET_FICTIF, "message": MESSAGE_FICTIF}),
    taches))
taches.executer_tout()
verifier("4n. BULK, SUPER-ADMIN : autorise, 3 envois exacts",
         statut == 200 and len(ENVOIS) == 3, "statut=%s envois=%d" % (statut, len(ENVOIS)))

# --- 4.5 la facturation n'a pas bouge ----------------------------------------
verifier("4o. AUCUN debit de credits n'a eu lieu — la logique est INCHANGEE",
         S.db.coaches.ecritures == credits_avant,
         "ecritures sur `coaches` = %d (attendu %d). `launch_campaign` debite deja "
         "le cout global : un debit ici serait un DOUBLE debit."
         % (S.db.coaches.ecritures, credits_avant))


print("\n=== 5. PUT /whatsapp-config — SUPER-ADMIN STRICT, ET RIEN N'EST ECRIT ===")

CONFIG_FICTIVE = S.WhatsAppConfigUpdate(
    metaAccessToken="JETON-META-FICTIF-AAA",
    metaPhoneNumberId="000000000000000",
    accountSid="SID-FICTIF",
    authToken="JETON-AUTH-FICTIF",
)

for intitule, requete in [
    ("5a. anonyme -> 403", RequeteFictive()),
    ("5b. `X-User-Email` d'un admin, forge -> 403", RequeteFictive(None, ADMIN_FICTIF)),
    ("5c. jeton ABONNE -> 403", RequeteFictive(JETON_ABONNE)),
    ("5d. jeton d'ESPACE ABONNE -> 403", RequeteFictive(JETON_ESPACE)),
    ("5e. jeton signe d'un autre secret -> 403", RequeteFictive(JETON_MAUVAIS_SECRET)),
    ("5f. jeton COACH normal -> 403 (config de PLATEFORME, pas de coach)",
     RequeteFictive(JETON_COACH)),
]:
    avant = S.db.whatsapp_config.ecritures
    statut, _ = appeler(S.update_whatsapp_config(CONFIG_FICTIVE, requete))
    verifier(intitule,
             statut == 403 and S.db.whatsapp_config.ecritures == avant,
             "statut=%s ecritures=%s" % (statut, S.db.whatsapp_config.ecritures - avant))

avant = S.db.whatsapp_config.ecritures
statut, _ = appeler(S.update_whatsapp_config(CONFIG_FICTIVE, RequeteFictive(JETON_ADMIN)))
verifier("5g. jeton SUPER-ADMIN : la porte s'ouvre, EXACTEMENT une ecriture simulee",
         statut == 200 and S.db.whatsapp_config.ecritures == avant + 1,
         "statut=%s ecritures=%s" % (statut, S.db.whatsapp_config.ecritures - avant))


print("\n=== 6. /notify-coach — LE VISITEUR NE CHOISIT PAS LE DESTINATAIRE ===")
print("     (route volontairement laissee OUVERTE : retour Stripe/TWINT visiteur)")

COACH_EN_BASE = "coach.notification.fictif@exemple.test"
ADRESSE_PIRATE = "pirate.fictif@exemple.test"


def _charge_notify(**extras):
    """Charge utile visiteur, avec tentatives d'injection de destinataire."""
    donnees = {
        "clientName": "Client Fictif",
        "clientEmail": ADRESSE_PIRATE,   # champ LEGITIMEMENT controle par le client
        "clientWhatsapp": "+41000000000",
        "offerName": "Offre fictive",
        "courseName": "Cours fictif",
        "sessionDate": "lundi 1 janvier 2030",
        "amount": 1.0,
        "reservationCode": "AFR-FICTIF",
    }
    donnees.update(extras)
    return S.CoachNotificationPayload(**donnees)


# A. le client tente d'imposer une adresse par tous les noms plausibles
S.db.payment_links = CollectionBouchon(
    [{"id": "payment_links", "coachNotificationEmail": COACH_EN_BASE,
      "coachNotificationPhone": ""}])
ENVOIS.clear()
statut, reponse = appeler(S.notify_coach(_charge_notify(
    to_email=ADRESSE_PIRATE, coachEmail=ADRESSE_PIRATE,
    email=ADRESSE_PIRATE, recipient=ADRESSE_PIRATE)))

verifier("6a. le modele IGNORE `to_email`/`coachEmail`/`email`/`recipient`",
         not any(hasattr(_charge_notify(to_email=ADRESSE_PIRATE), champ)
                 for champ in ("to_email", "coachEmail", "email", "recipient")))
verifier("6b. un e-mail part bien (le coach est notifie)",
         statut == 200 and len(ENVOIS) == 1 and reponse.get("emailSent") is True,
         "statut=%s envois=%d reponse=%s" % (statut, len(ENVOIS), reponse))
verifier("6c. le destinataire est celui de la BASE, jamais celui du client",
         len(ENVOIS) == 1 and ENVOIS[0].get("to") == [COACH_EN_BASE],
         "to=%s" % (ENVOIS[0].get("to") if ENVOIS else None))
verifier("6d. l'adresse arbitraire du client n'est destinataire d'AUCUN envoi",
         all(ADRESSE_PIRATE not in (e.get("to") or []) for e in ENVOIS))

# B. l'adresse du client apparait dans le CORPS (c'est son role : identifier le
#    client au coach), mais echappee — jamais comme destinataire.
verifier("6e. l'adresse du client figure dans le corps, echappee, pas dans `to`",
         ADRESSE_PIRATE in ENVOIS[0].get("html", "") and "<script" not in ENVOIS[0].get("html", ""))

statut, _ = appeler(S.notify_coach(_charge_notify(clientName='<script>alerte()</script>')))
verifier("6f. une balise injectee par le client ressort ECHAPPEE",
         len(ENVOIS) == 2 and "&lt;script&gt;" in ENVOIS[1].get("html", "")
         and "<script>" not in ENVOIS[1].get("html", ""))

# C. aucune destination fiable resolue cote serveur -> aucun envoi
S.db.payment_links = CollectionBouchon(
    [{"id": "payment_links", "coachNotificationEmail": "", "coachNotificationPhone": ""}])
avant = len(ENVOIS)
statut, reponse = appeler(S.notify_coach(_charge_notify()))
verifier("6g. aucune adresse coach en base -> AUCUN e-mail, et la route le dit",
         len(ENVOIS) == avant and reponse.get("success") is False,
         "envois=%d reponse=%s" % (len(ENVOIS) - avant, reponse))

# D. configuration absente -> aucun envoi non plus
S.db.payment_links = CollectionBouchon([])
avant = len(ENVOIS)
statut, reponse = appeler(S.notify_coach(_charge_notify()))
verifier("6h. aucune configuration du tout -> AUCUN e-mail",
         len(ENVOIS) == avant and reponse.get("success") is False,
         "envois=%d" % (len(ENVOIS) - avant))

# E. un telephone seul ne suffit pas a declencher un e-mail
S.db.payment_links = CollectionBouchon(
    [{"id": "payment_links", "coachNotificationEmail": "",
      "coachNotificationPhone": "+41000000000"}])
avant = len(ENVOIS)
statut, reponse = appeler(S.notify_coach(_charge_notify()))
verifier("6i. telephone seul, aucune adresse -> AUCUN e-mail",
         len(ENVOIS) == avant, "envois=%d" % (len(ENVOIS) - avant))

verifier("6j. sur TOUS les envois du fichier, aucune adresse choisie par un client",
         all(ADRESSE_PIRATE not in (e.get("to") or []) for e in ENVOIS))


print("\n=== 7. LE CODE LIVRE DIT BIEN CE QU'ON CROIT (relecture du source) ===")

SRC = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
_ARBRE = ast.parse(SRC)
_LIGNES = SRC.split("\n")


def _corps_de(nom):
    """Isole le corps d'une fonction via `ast`, commentaires compris.

    Surtout PAS par indentation : `notify_coach` contient une f-string
    triple-guillemets dont les lignes commencent en colonne 0 (le message de
    notification). Un decoupage par indentation s'y arrete au milieu et declare
    absent du code qui est bel et bien la — c'est exactement ce qui s'est
    produit a la premiere ecriture de ce fichier.
    """
    for noeud in ast.walk(_ARBRE):
        if isinstance(noeud, (ast.AsyncFunctionDef, ast.FunctionDef)) and noeud.name == nom:
            return "\n".join(_LIGNES[noeud.lineno - 1:noeud.end_lineno])
    raise AssertionError("fonction introuvable : %s" % nom)


CORPS_SEND = _corps_de("send_campaign_email")
CORPS_BULK = _corps_de("send_bulk_campaign_email")
CORPS_WA = _corps_de("update_whatsapp_config")
CORPS_NOTIFY = _corps_de("notify_coach")

verifier("7a. send-email appelle bien `_v309_require_coach_or_admin`",
         "await _v309_require_coach_or_admin(request)" in CORPS_SEND)
verifier("7b. send-bulk-email aussi",
         "await _v309_require_coach_or_admin(request)" in CORPS_BULK)
verifier("7c. whatsapp-config appelle `_v411_exiger_super_admin`",
         "_v411_exiger_super_admin(request," in CORPS_WA)

for nom, corps in [("send-email", CORPS_SEND), ("send-bulk-email", CORPS_BULK),
                   ("whatsapp-config", CORPS_WA)]:
    verifier("7d. %s n'emploie PAS `require_auth` (il accepte les jetons abonne)" % nom,
             not re.search(r"\brequire_auth\s*\(", corps))

verifier("7e. la signature de whatsapp-config recoit bien `Request`",
         "async def update_whatsapp_config(config: WhatsAppConfigUpdate, request: Request)" in SRC)

verifier("7f. notify-coach envoie desormais l'e-mail lui-meme",
         "resend.Emails.send" in CORPS_NOTIFY and '"emailSent"' in CORPS_NOTIFY)

verifier("7g. notify-coach echappe le message avant de l'inserer dans du HTML",
         "_v468_html.escape(notification_message)" in CORPS_NOTIFY)

verifier("7h. la destination de la notification vient de la BASE, jamais du corps",
         'payment_links.get("coachNotificationEmail"' in CORPS_NOTIFY
         and 'payload.coachEmail' not in CORPS_NOTIFY
         and 'payload.to_email' not in CORPS_NOTIFY)

verifier("7i. le debit de credits de send-email n'a PAS ete deplace (pas de double debit)",
         'coach_email = request.headers.get("X-User-Email", "").lower().strip()' in CORPS_SEND)

verifier("7j. le modele de notify-coach n'expose AUCUN champ de destination",
         not any(champ in S.CoachNotificationPayload.model_fields
                 for champ in ("to_email", "coachEmail", "email", "recipient")))


print("\n=== 8. LE FRONT ENVOIE LE JETON — SANS RECOPIER LA LOGIQUE DU JETON ===")

DASH = open(os.path.join(RACINE, "frontend", "src", "components", "CoachDashboard.js"),
            encoding="utf-8").read()
APPJS = open(os.path.join(RACINE, "frontend", "src", "App.js"), encoding="utf-8").read()
WASVC = open(os.path.join(RACINE, "frontend", "src", "services", "whatsappService.js"),
             encoding="utf-8").read()
SW = open(os.path.join(RACINE, "frontend", "public", "sw.js"), encoding="utf-8").read()

verifier("8a. plus AUCUN `fetch` vers send-email dans le dashboard",
         "fetch(`${BACKEND_URL}/api/campaigns/send-email`" not in DASH)

verifier("8b. les DEUX points d'appel sont passes en axios",
         DASH.count("axios.post(`${API}/campaigns/send-email`") == 2,
         "trouve %d" % DASH.count("axios.post(`${API}/campaigns/send-email`"))

verifier("8c. plus AUCUN `fetch` PUT vers whatsapp-config",
         "method: 'PUT'" not in WASVC and "axios.put(`${API}/api/whatsapp-config`" in WASVC)

verifier("8d. whatsappService importe axios",
         "import axios from 'axios'" in WASVC)

verifier("8e. App.js n'APPELLE plus send-email (le chemin visiteur anonyme a disparu)",
         "axios.post(`${API}/campaigns/send-email`" not in APPJS
         and "campaigns/send-email" in APPJS,
         "la route ne doit plus etre APPELEE, mais le commentaire V468 doit "
         "expliquer pourquoi — sinon un futur lecteur la recablera")

verifier("8f. App.js lit `emailSent` renvoye par le serveur",
         "notifyResponse.data.emailSent" in APPJS)

# Version MINIMALE, pas exacte : epingler « v468 » ferait echouer ce fichier a
# chaque bump ulterieur, pour une raison sans aucun rapport avec SECURITY-S2-A1.
# Le seul risque reel est le RETOUR EN ARRIERE — un cache revenu sous v468
# reservirait le bundle dont les envois partent en `fetch`, donc sans jeton.
_sw_version = re.search(r"afroboost-v(\d+)", SW)
verifier("8g. le Service Worker est au moins en v468 (jamais revenu en arriere)",
         bool(_sw_version) and int(_sw_version.group(1)) >= 468,
         "version lue = %s" % (_sw_version.group(0) if _sw_version else "aucune"))


print("\n=== 9. AUCUN APPEL EXTERNE, AUCUNE VALEUR SENSIBLE REELLE ===")

MOI = open(os.path.abspath(__file__), encoding="utf-8").read()

_MOTIFS_INTERDITS = [
    (r"EAA[A-Za-z0-9]{20,}", "jeton Meta"),
    (r"\bAC[0-9a-f]{32}\b", "Account SID Twilio"),
    (r"\bSK[0-9a-f]{32}\b", "cle Twilio"),
    (r"re_[A-Za-z0-9_]{20,}", "cle Resend"),
    (r"sk_live_[A-Za-z0-9]{10,}", "cle Stripe"),
    (r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.", "JWT en dur"),
]
for _motif, _quoi in _MOTIFS_INTERDITS:
    verifier("9a. aucun %s reel n'est ecrit dans ce fichier" % _quoi,
             not re.search(_motif, MOI))

verifier("9b. tous les jetons sont fabriques sur un secret fictif",
         SECRET_FICTIF.startswith("secret-de-test"))

verifier("9c. AUCUNE connexion reseau n'a ete tentee de tout le fichier",
         not RESEAU["tentatives"], "tentatives=%s" % RESEAU["tentatives"])

verifier("9d. tous les destinataires touches sont des adresses fictives `.test`",
         all(str(a).endswith(".test") for e in ENVOIS for a in (e.get("to") or [])),
         "destinataires=%s" % [e.get("to") for e in ENVOIS])

verifier("9e. aucune ecriture simulee ailleurs que sur `whatsapp_config`",
         S.db.coaches.ecritures == 0 and S.db.subscribers.ecritures == 0,
         "coaches=%d subscribers=%d" % (S.db.coaches.ecritures, S.db.subscribers.ecritures))


# Le reseau est rendu a son etat normal : ce fichier ne doit rien laisser derriere lui.
socket.socket.connect = _connect_reel
socket.create_connection = _create_reel
if _to_thread_reel is not None:
    asyncio.to_thread = _to_thread_reel
    S.asyncio.to_thread = _to_thread_reel

print("\n" + "=" * 78)
_ok = sum(1 for _, c, _ in RESULTATS if c)
_total = len(RESULTATS)
print("SECURITY-S2-A1 — %d / %d verifications au vert" % (_ok, _total))
print("=" * 78)
if _ok != _total:
    print("\nECHECS :")
    for intitule, cond, detail in RESULTATS:
        if not cond:
            print("  - %s%s" % (intitule, ("  [%s]" % detail) if detail else ""))
sys.exit(0 if _ok == _total else 1)
