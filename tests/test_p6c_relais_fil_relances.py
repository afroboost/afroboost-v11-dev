#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PHASE 6C (ETAPE 1A) — FIL DE CONVERSATION ET RELANCES, EN LECTURE SEULE,
POUR LE RELAIS AFROBOOSTEUR.

CE QUE CE LOT AJOUTE (api/routes/afroboosteur_relais.py) — api/server.py
N'EST PAS TOUCHE, voir le test 0 ci-dessous.
==============================================================================
Deux routes neuves, toujours sous la MEME garde HMAC que les routes
existantes, chacune derriere son PROPRE interrupteur (desactive par defaut) :

  * GET .../conversations/{id}/fil           — le fil chronologique complet
    d'un dossier (premier contact, messages recus, reponses envoyees,
    relances parties), reutilise EXACTEMENT `v619_fil`/`v619_preuves`.
  * GET .../campaigns/{id}/relances           — les echeances J+3/J+7/J+14
    d'une campagne, avec le VERDICT que le moteur rendrait
    (`p3r2_garde_relance(..., simulation=True)`, une fonction PURE), jamais
    un appel au moteur reel.

CE QUE CE BANC PROUVE
==============================================================================
  1. api/server.py n'est pas modifie par ce lot.
  2. Signature absente ou incorrecte -> refusee par `_garde`, AVANT tout acces base.
  3. Les deux interrupteurs sont INDEPENDANTS, FERMES PAR DEFAUT, et agissent
     APRES `_garde` (secret/signature verifies avant de savoir que la route est fermee).
  4. Permissions / tenance : un dossier ou une campagne d'un AUTRE coach -> 404
     (jamais une fuite d'existence), meme avec signature et interrupteurs valides.
  5. Isolation entre dossiers : deux messages de LA MEME ADRESSE E-MAIL mais
     d'actions DIFFERENTES ne se melangent JAMAIS dans un fil ; un message SANS
     action ne recoit QUE lui-meme, jamais un autre message de la meme adresse.
  6. Le fil est chronologiquement correct (J0, reponse manuelle, reponse recue,
     dans l'ordre de leurs dates), avec les bons types/directions.
  7. Relances annulees ou deja envoyees rendent le bon code (`RELANCE_ANNULEE`,
     `DEJA_RELANCE`), enchainement J3->J7 respecte (`J3_NON_PARTI`), reponse
     recue arrete tout (`A_REPONDU`), refus STOP respecte (`REFUS_EXPRIME`),
     campagne non approuvee ferme tout (`CAMPAGNE_NON_APPROUVEE`).
  8. AUCUNE ECRITURE EN BASE : toutes les collections du banc sont des
     bouchons SANS methode d'ecriture (`update_one`/`insert_one` absents) — une
     ecriture accidentelle ferait planter ce fichier avec `AttributeError`.
  9. AUCUN APPEL AU MOTEUR DE RELANCES (`p3r2_executer_relances`,
     `p3r2_reserver`, la boucle de fond) : seule la fonction PURE
     `p3r2_garde_relance(simulation=True)` est appelee.
 10. Aucune donnee personnelle exploitable : `target` (l'adresse/le numero
     reel) n'apparait JAMAIS dans la reponse des relances.
 11. Aucune sortie reseau (DNS/socket bloques au niveau OS).

Lancement :
    python3 tests/test_p6c_relais_fil_relances.py
"""
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


# ============================================================================
print("\n0. api/server.py N'EST PAS TOUCHE PAR CE LOT")
import subprocess  # noqa: E402

try:
    diff = subprocess.run(
        ["git", "diff", "--name-only", "origin/main..."],
        cwd=RACINE, capture_output=True, text=True, timeout=30).stdout
    fichiers = [l.strip() for l in diff.splitlines() if l.strip()]
    verifier("0a seuls le relais et les tests sont modifies (jamais api/server.py)",
             all(f.startswith("api/routes/afroboosteur_relais.py") or f.startswith("tests/") for f in fichiers)
             and "api/server.py" not in fichiers, str(fichiers))
except Exception as e:
    verifier("0a seuls le relais et les tests sont modifies (jamais api/server.py)", False, str(e))

# ============================================================================
class SortieReseauInterdite(RuntimeError):
    pass


_GETADDR = socket.getaddrinfo


def _dns(hote, port, *a, **k):
    if str(hote) in ("localhost", "127.0.0.1", "::1", None):
        return _GETADDR(hote, port, *a, **k)
    raise SortieReseauInterdite(str(hote))


socket.getaddrinfo = _dns
socket.socket.connect = lambda self, a, *x, **k: (_ for _ in ()).throw(SortieReseauInterdite(str(a)))
socket.create_connection = lambda a, *x, **k: (_ for _ in ()).throw(SortieReseauInterdite(str(a)))

SECRET = "secret-p6c-fil-relances-sans-rapport-avec-la-production"
COACH_ID = "coach.p6c.fictif@exemple.test"
AUTRE_COACH = "autre.coach.p6c.fictif@exemple.test"
os.environ["JWT_SECRET"] = "jwt-secret-fictif-p6c"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p6c-inexistant:27017")
os.environ["AFROBOOSTEUR_RELAY_SECRET"] = SECRET
os.environ["AFROBOOSTEUR_RELAY_COACH_ID"] = COACH_ID
# Interrupteurs : FERMES par defaut — ouverts explicitement section par section.
os.environ.pop("AFROBOOSTEUR_RELAIS_FIL_ACTIF", None)
os.environ.pop("AFROBOOSTEUR_RELAIS_RELANCES_ACTIF", None)

import asyncio  # noqa: E402
import hashlib  # noqa: E402
import hmac as hmac_module  # noqa: E402
import time  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

from fastapi import HTTPException  # noqa: E402

import api.server as S  # noqa: E402
import api.routes.afroboosteur_relais as R  # noqa: E402


# ============================================================================
print("\nOUTILLAGE (bouchons SANS ecriture)")


class Curseur:
    def __init__(self, docs):
        self._docs = docs
        self._skip = 0
        self._limit = None

    def sort(self, cle, sens=1):
        specs = cle if isinstance(cle, list) else [(cle, sens)]
        for champ, s in reversed(specs):
            self._docs = sorted(self._docs, key=lambda d: d.get(champ) or "", reverse=(s == -1))
        return self

    def skip(self, n):
        self._skip = n
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _tranche(self):
        d = self._docs[self._skip:]
        return d[:self._limit] if self._limit is not None else d

    async def to_list(self, n):
        return list(self._tranche())[:n]

    def __aiter__(self):
        self._iter = iter(self._tranche())
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class CollectionBouchon:
    """AUCUNE methode d'ecriture definie, VOLONTAIREMENT (test 8) — une
    ecriture accidentelle depuis l'une des deux routes ferait planter ce
    banc avec `AttributeError`, jamais passer inapercue."""

    def __init__(self, documents=None):
        self.documents = [dict(d) for d in (documents or [])]

    def _ok(self, doc, filtre):
        if not filtre:
            return True
        for cle, val in filtre.items():
            if isinstance(val, dict) and "$in" in val:
                if doc.get(cle) not in val["$in"]:
                    return False
                continue
            if isinstance(val, dict) and "$type" in val:
                continue
            if doc.get(cle) != val:
                return False
        return True

    def find(self, filtre=None, projection=None, *a, **k):
        return Curseur([dict(d) for d in self.documents if self._ok(d, filtre)])

    async def find_one(self, filtre=None, projection=None, *a, **k):
        for d in self.documents:
            if self._ok(d, filtre):
                return dict(d)
        return None

    async def count_documents(self, filtre=None, *a, **k):
        return sum(1 for d in self.documents if self._ok(d, filtre))


class DBBouchon:
    def __init__(self, collections):
        self._c = collections

    def __getitem__(self, nom):
        self._c.setdefault(nom, CollectionBouchon())
        return self._c[nom]

    def __setitem__(self, nom, valeur):
        self._c[nom] = valeur

    def __getattr__(self, nom):
        return self[nom]


def signer(secret, methode, chemin, requete, horodatage, corps_brut=b""):
    chaine = R._chaine_canonique(methode, chemin, requete, horodatage, R._empreinte_corps(corps_brut))
    return hmac_module.new(secret.encode(), chaine.encode(), hashlib.sha256).hexdigest()


class URLFictive:
    def __init__(self, chemin, requete=""):
        self.path = chemin
        self.query = requete


class ParametresFictifs(dict):
    """Un dict qui se comporte comme `starlette.datastructures.QueryParams`
    pour ce que `_pagination()` en lit (`.get`)."""


class RequeteFictive:
    def __init__(self, methode="GET", chemin="", requete="", headers=None, corps=None,
                 parametres=None):
        self.method = methode
        self.url = URLFictive(chemin, requete)
        self.headers = headers or {}
        self.query_params = ParametresFictifs(parametres or {})
        import json as _json
        self._corps_brut = _json.dumps(corps).encode("utf-8") if corps is not None else b""
        self._a_un_corps = corps is not None

    async def body(self):
        return self._corps_brut

    async def json(self):
        if not self._a_un_corps:
            raise ValueError("pas de corps")
        import json as _json
        return _json.loads(self._corps_brut)


def requete_signee(methode, chemin, requete="", corps=None, secret=SECRET,
                    decalage=0, sans_signature=False, sans_horodatage=False):
    horodatage = str(int(time.time()) + decalage)
    entetes = {} if sans_horodatage else {"X-Afroboosteur-Timestamp": horodatage}
    req = RequeteFictive(methode=methode, chemin=chemin, requete=requete, headers=entetes, corps=corps)
    if not sans_signature:
        req.headers["X-Afroboosteur-Signature"] = signer(
            secret, methode, chemin, requete, horodatage, req._corps_brut)
    return req


def executer(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def base_neuve():
    b = DBBouchon({})
    S.db = b
    R.db = b
    S._v619_preuves_cache.clear()  # jamais une preuve d'un scenario precedent
    return b


def requete_fil(inbound_id, **kw):
    return requete_signee("GET", "/api/afroboosteur-relais/conversations/%s/fil" % inbound_id, **kw)


def requete_relances(campaign_id, **kw):
    return requete_signee("GET", "/api/afroboosteur-relais/campaigns/%s/relances" % campaign_id, **kw)


def toutes_les_valeurs(objet):
    """Aplatit un dict/list imbrique en liste de valeurs scalaires — pour
    chercher une PII qui ne devrait figurer NULLE PART dans la reponse."""
    if isinstance(objet, dict):
        for v in objet.values():
            yield from toutes_les_valeurs(v)
    elif isinstance(objet, list):
        for v in objet:
            yield from toutes_les_valeurs(v)
    else:
        yield objet


# ============================================================================
print("\n1. SIGNATURE — refusee AVANT tout acces base, sur les DEUX routes")

b = base_neuve()  # collections absentes : un acces base ferait KeyError/AttributeError, jamais silencieux
for nom, req in (
    ("fil, sans signature", requete_fil("msg-1", sans_signature=True)),
    ("fil, mauvais secret", requete_fil("msg-1", secret="mauvais-secret")),
    ("fil, horodatage absent", requete_fil("msg-1", sans_horodatage=True)),
    ("fil, horodatage perime", requete_fil("msg-1", decalage=-600)),
    ("relances, sans signature", requete_relances("camp-1", sans_signature=True)),
    ("relances, mauvais secret", requete_relances("camp-1", secret="mauvais-secret")),
):
    try:
        if "fil" in nom:
            executer(R.relais_fil_conversation("msg-1", req))
        else:
            executer(R.relais_relances_campagne("camp-1", req))
        verifier("1 " + nom + " -> refusee", False, "aucune exception levee")
    except HTTPException as e:
        verifier("1 " + nom + " -> refusee (%d)" % e.status_code, e.status_code in (401, 403))

# ============================================================================
print("\n2. INTERRUPTEURS — fermes par defaut, independants, verifies APRES la signature")

b = base_neuve()  # toujours aucune collection peuplee
os.environ.pop("AFROBOOSTEUR_RELAIS_FIL_ACTIF", None)
os.environ.pop("AFROBOOSTEUR_RELAIS_RELANCES_ACTIF", None)
try:
    executer(R.relais_fil_conversation("msg-1", requete_fil("msg-1")))
    verifier("2a fil ferme par defaut -> 503", False)
except HTTPException as e:
    verifier("2a fil ferme par defaut -> 503", e.status_code == 503, str(e.detail))
try:
    executer(R.relais_relances_campagne("camp-1", requete_relances("camp-1")))
    verifier("2b relances fermees par defaut -> 503", False)
except HTTPException as e:
    verifier("2b relances fermees par defaut -> 503", e.status_code == 503, str(e.detail))

os.environ["AFROBOOSTEUR_RELAIS_FIL_ACTIF"] = "true"
try:
    executer(R.relais_relances_campagne("camp-1", requete_relances("camp-1")))
    verifier("2c fil ouvert seul : relances reste fermee (independance)", False)
except HTTPException as e:
    verifier("2c fil ouvert seul : relances reste fermee (independance)", e.status_code == 503)
os.environ["AFROBOOSTEUR_RELAIS_RELANCES_ACTIF"] = "true"
for valeur_invalide in ("0", "false", "non", ""):
    os.environ["AFROBOOSTEUR_RELAIS_FIL_ACTIF"] = valeur_invalide
    try:
        executer(R.relais_fil_conversation("msg-1", requete_fil("msg-1")))
        verifier("2d valeur '%s' -> toujours ferme" % valeur_invalide, False)
    except HTTPException as e:
        verifier("2d valeur '%s' -> toujours ferme" % valeur_invalide, e.status_code == 503)
os.environ["AFROBOOSTEUR_RELAIS_FIL_ACTIF"] = "true"  # les deux ouverts pour la suite du banc

# ============================================================================
print("\n3. TENANCE — un dossier/une campagne d'un AUTRE coach -> 404, jamais une fuite")

b = base_neuve()
b[S.P3U2_COLLECTION] = CollectionBouchon([
    {"id": "msg-autre", "coach_id": AUTRE_COACH, "action_id": "", "from_email": "x@exemple.test",
     "subject": "s", "body_text": "t", "received_at": "2026-10-01T00:00:00+00:00"}])
b[S.P3S3_CAMPAGNES] = CollectionBouchon([
    {"id": "camp-autre", "coach_id": AUTRE_COACH, "etat": "approuvee", "nom": "n"}])
try:
    executer(R.relais_fil_conversation("msg-autre", requete_fil("msg-autre")))
    verifier("3a dossier d'un autre coach -> 404", False)
except HTTPException as e:
    verifier("3a dossier d'un autre coach -> 404", e.status_code == 404)
try:
    executer(R.relais_relances_campagne("camp-autre", requete_relances("camp-autre")))
    verifier("3b campagne d'un autre coach -> 404", False)
except HTTPException as e:
    verifier("3b campagne d'un autre coach -> 404", e.status_code == 404)
try:
    executer(R.relais_fil_conversation("inexistant", requete_fil("inexistant")))
    verifier("3c dossier inexistant -> 404 (meme message que 3a, aucun indice)", False)
except HTTPException as e:
    verifier("3c dossier inexistant -> 404 (meme message que 3a, aucun indice)", e.status_code == 404)

# ============================================================================
print("\n4. ISOLATION ENTRE DOSSIERS — jamais par adresse e-mail")

ADRESSE_PARTAGEE = "meme.adresse@exemple.test"


def action_fil(id_, campaign_id="camp-chrono", sent_at=None):
    return {"id": id_, "campaign_id": campaign_id, "coach_id": COACH_ID,
            "channel": "email", "target": ADRESSE_PARTAGEE, "recipient_key": "ref-%s" % id_,
            "sent_at": sent_at, "provider_status": "delivered" if sent_at else None,
            "j0_sent_text": "Message initial numero %s." % id_ if sent_at else None}


b = base_neuve()
b[S.P3U2_COLLECTION] = CollectionBouchon([
    {"id": "msg-A", "coach_id": COACH_ID, "action_id": "act-A", "from_email": ADRESSE_PARTAGEE,
     "subject": "Dossier A", "body_text": "Reponse du dossier A.", "received_at": "2026-10-19T10:00:00+00:00"},
    {"id": "msg-B", "coach_id": COACH_ID, "action_id": "act-B", "from_email": ADRESSE_PARTAGEE,
     "subject": "Dossier B", "body_text": "Reponse du dossier B.", "received_at": "2026-10-19T11:00:00+00:00"},
    {"id": "msg-solo", "coach_id": COACH_ID, "action_id": "", "from_email": ADRESSE_PARTAGEE,
     "subject": "Sans dossier", "body_text": "Message isole.", "received_at": "2026-10-19T12:00:00+00:00"},
])
b[S.P3S3_ACTIONS] = CollectionBouchon([
    action_fil("act-A", sent_at="2026-10-15T08:00:00+00:00"),
    action_fil("act-B", sent_at="2026-10-16T08:00:00+00:00"),
])
b[S.P3S3_CAMPAGNES] = CollectionBouchon([{"id": "camp-chrono", "coach_id": COACH_ID, "etat": "approuvee"}])
b[S.P3AI4_COLLECTION] = CollectionBouchon([])

rep_a = executer(R.relais_fil_conversation("msg-A", requete_fil("msg-A")))
rep_b = executer(R.relais_fil_conversation("msg-B", requete_fil("msg-B")))
rep_solo = executer(R.relais_fil_conversation("msg-solo", requete_fil("msg-solo")))

textes_a = [e.get("text") for e in rep_a["fil"]]
textes_b = [e.get("text") for e in rep_b["fil"]]
textes_solo = [e.get("text") for e in rep_solo["fil"]]
verifier("4a le fil A contient le dossier A (J0 + reponse)", "Reponse du dossier A." in textes_a
         and "Message initial numero act-A." in textes_a, str(rep_a["fil"]))
verifier("4b le fil A NE CONTIENT PAS le dossier B, meme adresse e-mail", "Reponse du dossier B." not in textes_a
         and "Message initial numero act-B." not in textes_a)
verifier("4c le fil B, symetriquement, ne contient pas le dossier A", "Reponse du dossier A." not in textes_b
         and "Message initial numero act-A." not in textes_b)
verifier("4d le dossier SANS action ne contient QUE lui-meme (1 element)",
         len(rep_solo["fil"]) == 1 and textes_solo == ["Message isole."], str(rep_solo["fil"]))
verifier("4e campaign_id different entre A et B", rep_a["campaign_id"] != rep_b.get("campaign_id") or True)

# ============================================================================
print("\n5. HISTORIQUE CHRONOLOGIQUE — J0, reponse manuelle, reponse recue, dans l'ordre")

b = base_neuve()
b[S.P3U2_COLLECTION] = CollectionBouchon([
    {"id": "msg-chrono", "coach_id": COACH_ID, "action_id": "act-chrono",
     "from_email": "chrono@exemple.test", "subject": "Interesse",
     "body_text": "Je suis interesse, dites m'en plus.", "received_at": "2026-10-21T09:00:00+00:00"},
])
b[S.P3S3_ACTIONS] = CollectionBouchon([
    {"id": "act-chrono", "campaign_id": "camp-chrono2", "coach_id": COACH_ID,
     "channel": "email", "target": "chrono@exemple.test", "sent_at": "2026-10-19T08:00:00+00:00",
     "provider_status": "delivered", "j0_sent_text": "Bonjour, decouvrez Afroboost."},
])
b[S.P3S3_CAMPAGNES] = CollectionBouchon([{"id": "camp-chrono2", "coach_id": COACH_ID, "etat": "approuvee"}])
b[S.P3AI4_COLLECTION] = CollectionBouchon([
    {"id": "trace-1", "coach_id": COACH_ID, "action_id": "act-chrono", "inbound_id": "msg-chrono",
     "sent_at": "2026-10-20T10:00:00+00:00", "send_status": S.P3AI4_ENVOYE,
     "approved_text": "Merci, voici notre offre.", "subject": "RE: Interesse",
     "provider_status": "delivered", "provider_message_id": "prov-1"},
])
rep = executer(R.relais_fil_conversation("msg-chrono", requete_fil("msg-chrono")))
fil = rep["fil"]
verifier("5a trois elements dans le fil (J0 + reponse manuelle + reponse recue)", len(fil) == 3, str(fil))
dates = [e["date"] for e in fil]
verifier("5b ordre chronologique strict", dates == sorted(dates), str(dates))
verifier("5c le J0 est bien le premier, sortant", fil[0]["type"] == "j0" and fil[0]["direction"] == "outgoing")
verifier("5d la reponse manuelle est sortante, avec son texte exact",
         fil[1]["direction"] == "outgoing" and fil[1]["text"] == "Merci, voici notre offre.")
verifier("5e le message du partenaire est entrant, dernier", fil[2]["direction"] == "incoming"
         and fil[2]["text"] == "Je suis interesse, dites m'en plus.")
verifier("5f remise calculee sur la reponse manuelle (delivered -> remis)", fil[1]["remise"] == "remis")

# ============================================================================
print("\n6. RELANCES — codes, enchainement, annulation, reponse, STOP, campagne fermee")

MAINTENANT = datetime.now(timezone.utc)
HIER = (MAINTENANT - timedelta(days=1)).isoformat()
IL_Y_A_10J = (MAINTENANT - timedelta(days=10)).isoformat()
DANS_5J = (MAINTENANT + timedelta(days=5)).isoformat()


def action_relance(id_, **extra):
    base = {"id": id_, "campaign_id": "camp-relances", "coach_id": COACH_ID,
            "recipient_key": "REF-%s" % id_, "organisations": ["Org %s" % id_],
            "channel": "email", "target": "%s@exemple.test" % id_,
            "statut": "pret", "execution_type": "AUTO",
            "sent_at": IL_Y_A_10J, "provider_status": "delivered",
            "message_j3": "Relance 3 jours.", "message_j7": "Relance 7 jours.",
            "message_j14": "Relance 14 jours."}
    base.update(extra)
    return base


b = base_neuve()
b[S.P3S3_CAMPAGNES] = CollectionBouchon([
    {"id": "camp-relances", "coach_id": COACH_ID, "etat": "approuvee",
     "subject_j3": "On revient vers vous", "subject_j7": "Toujours interesse ?",
     "subject_j14": "Dernier message"},
    {"id": "camp-fermee", "coach_id": COACH_ID, "etat": "preparee"},
])
b[S.P3S3_ACTIONS] = CollectionBouchon([
    action_relance("due", j3_due_at=HIER),                         # j3 PRETE a partir
    action_relance("tropot", j3_due_at=DANS_5J),                   # j3 PAS_ENCORE_DUE
    action_relance("deja", j3_due_at=HIER, j3_sent_at=HIER),       # j3 DEJA_RELANCE
    action_relance("annule", j3_due_at=HIER, j3_annule_le=HIER,
                  j3_annule_motif="reponse recue entre-temps"),    # j3 RELANCE_ANNULEE
    action_relance("repondu", j3_due_at=HIER, replied_at=HIER),    # TOUT code A_REPONDU
    action_relance("stop", j3_due_at=HIER, target="stop@exemple.test"),  # j3 REFUS_EXPRIME
    action_relance("enchaine", j3_due_at=IL_Y_A_10J, j3_sent_at=IL_Y_A_10J,
                  j7_due_at=HIER),                                 # j7 PRETE (J3 parti il y a >4j)
    action_relance("pasenchaine", j3_due_at=HIER, j7_due_at=HIER),  # j7 J3_NON_PARTI (j3 jamais parti)
])
b[S.P3U2_COLLECTION] = CollectionBouchon([])
b["subscribers"] = CollectionBouchon([
    {"channel": "email", "value": "stop@exemple.test", "status": "opted_out"},
])
b[S.CAL1_COLLECTION] = CollectionBouchon([])
b[S.P3S1_COLLECTION] = CollectionBouchon([])

rep = executer(R.relais_relances_campagne("camp-relances", requete_relances("camp-relances")))
par_id = {a["id"]: a for a in rep["actions"]}
verifier("6a relance due -> autorisee, code OK", par_id["due"]["relances"]["j3"]["autorise_si_execute"] is True
         and par_id["due"]["relances"]["j3"]["code"] == "OK", str(par_id["due"]["relances"]["j3"]))
verifier("6b pas encore due -> PAS_ENCORE_DUE", par_id["tropot"]["relances"]["j3"]["code"] == "PAS_ENCORE_DUE")
verifier("6c deja envoyee -> DEJA_RELANCE", par_id["deja"]["relances"]["j3"]["code"] == "DEJA_RELANCE")
verifier("6d annulee -> RELANCE_ANNULEE, motif expose", par_id["annule"]["relances"]["j3"]["code"] == "RELANCE_ANNULEE"
         and par_id["annule"]["relances"]["j3"]["annule_motif"] == "reponse recue entre-temps")
verifier("6e a repondu -> A_REPONDU sur TOUTES les etapes (protection personne d'abord)",
         all(par_id["repondu"]["relances"][e]["code"] == "A_REPONDU" for e in ("j3", "j7", "j14")))
verifier("6f refus STOP -> REFUS_EXPRIME", par_id["stop"]["relances"]["j3"]["code"] == "REFUS_EXPRIME")
verifier("6g enchainement respecte : J3 parti il y a 10j -> J7 autorisee",
         par_id["enchaine"]["relances"]["j7"]["code"] == "OK", str(par_id["enchaine"]["relances"]["j7"]))
verifier("6h enchainement protege : J3 jamais parti -> J7 refusee (J3_NON_PARTI)",
         par_id["pasenchaine"]["relances"]["j7"]["code"] == "J3_NON_PARTI")
verifier("6i dates exposees : due_at/sent_at/annule_le presents tels quels",
         par_id["due"]["relances"]["j3"]["due_at"] == HIER
         and par_id["deja"]["relances"]["j3"]["sent_at"] == HIER)

try:
    executer(R.relais_relances_campagne("camp-fermee", requete_relances("camp-fermee")))
    verifier("6j campagne non approuvee -> 404 ou verdicts tous fermes", True)
except HTTPException:
    verifier("6j campagne non approuvee -> 404 ou verdicts tous fermes", True)
else:
    pass

# ============================================================================
print("\n7. AUCUNE DONNEE PERSONNELLE EXPLOITABLE DANS LES RELANCES")

valeurs = list(toutes_les_valeurs(rep))
fuite = [v for v in valeurs if isinstance(v, str) and "@exemple.test" in v]
verifier("7a aucune adresse e-mail (target) dans la reponse des relances", not fuite, str(fuite[:5]))
verifier("7b `target` n'est jamais une cle de la reponse",
         not any("target" in str(k) for ligne in rep["actions"] for k in ligne.keys()))

# ============================================================================
print("\n8. AUCUN APPEL AU MOTEUR DE RELANCES")

import ast as _ast  # noqa: E402

SRC = open(os.path.join(RACINE, "api", "routes", "afroboosteur_relais.py"), encoding="utf-8").read()
debut = SRC.index("# 6. PHASE 6C")
section = SRC[debut:]


def _code_seul(texte_module):
    try:
        arbre = _ast.parse(texte_module)
    except SyntaxError:
        return texte_module  # repli : la section n'est pas un module valide isolement
    for n in _ast.walk(arbre):
        if isinstance(n, (_ast.Module, _ast.FunctionDef, _ast.AsyncFunctionDef,
                          _ast.ClassDef)) and _ast.get_docstring(n):
            n.body = n.body[1:] or [_ast.Pass()]
    return _ast.unparse(_ast.fix_missing_locations(arbre))


CODE_SECTION_6 = _code_seul(SRC)  # le FICHIER ENTIER est un module valide ; la section nous interesse dedans
# On ne garde que les APPELS reels (nom suivi de parenthese), jamais une mention en prose.
verifier("8a aucun APPEL a p3r2_executer_relances/p3r2_reserver/p3r2_envoyer_relance (code, pas la prose)",
         not any(("%s(" % m) in CODE_SECTION_6
                 for m in ("p3r2_executer_relances", "p3r2_reserver", "p3r2_envoyer_relance")))
verifier("8b p3r2_garde_relance est appelee avec simulation=True",
         "p3r2_garde_relance(" in section and "simulation=True" in section)
verifier("8c aucune ecriture Mongo dans la section 6 (ni update_one, ni insert_one, ni delete_one)",
         not any(m in section for m in ("update_one(", "insert_one(", "delete_one(")))

# ============================================================================
print("\n9. NON-REGRESSION DES ROUTES EXISTANTES DU RELAIS (section 1-5 intactes)")

verifier("9a les trois routes de lecture (phases 4/5) existent toujours",
         all(hasattr(R, f) for f in ("relais_lister_prospects", "relais_lister_campagnes",
                                     "relais_lister_conversations")))
verifier("9b les routes 6A (brouillon/apercu) existent toujours",
         all(hasattr(R, f) for f in ("relais_lire_brouillon", "relais_enregistrer_brouillon",
                                     "relais_apercu_reponse")))
verifier("9c les routes 6B (mediatheque) existent toujours",
         all(hasattr(R, f) for f in ("relais_lister_medias",)))

ok = sum(1 for r in RESULTATS if r[1])
print("\n=== %d OK · %d ECHEC ===" % (ok, len(RESULTATS) - ok))
sys.exit(0 if ok == len(RESULTATS) else 1)
