#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V636 — ENVOYER UNE REPONSE, AVEC SES MEDIAS, DEPUIS AFROBOOSTEUR.COM
=============================================================================

CE QUE CE LOT AJOUTE, ET CE QU'IL NE REFAIT PAS. Un membre autorise de
l'association pouvait deja, depuis afroboosteur.com : lire une conversation,
ecrire un brouillon, voir la mediatheque du coach. Il ne pouvait PAS joindre un
media a sa reponse, ni l'envoyer. Deux manques, une seule cause : la route
d'enregistrement du brouillon ignorait deliberement les champs media, et
l'envoi n'etait pas cable du tout.

Ce lot comble ces deux manques SANS ecrire un second moteur d'envoi :
`p3ai4_envoyer_reponse_pour` est la fonction du coach, EXTRAITE de sa route
sans qu'une seule de ses regles ne change, et le relais l'appelle.

-----------------------------------------------------------------------------
AUCUN E-MAIL REEL NE PEUT PARTIR DE CE BANC — TROIS FREINS, PAS UN
-----------------------------------------------------------------------------
1. Le DNS et les sockets sont coupes au niveau du systeme (comme dans tous les
   bancs de ce depot) : une sortie reseau leve, elle ne part pas.
2. `S.P3AI4FournisseurReponse` est remplacee par une sous-classe dont le
   transport est un FAUX qui enregistre l'appel et ne contacte rien. C'est le
   meme montage que `tests/test_aip4_envoi_reponse.py`.
3. Les deux drapeaux en base (`P3_REPONSE_ACTIF`, `P3_REPONSE_ENVOI_REEL`)
   sont a False par defaut dans chaque scenario : le code court-circuite alors
   le transport AVANT de l'appeler (`ENVOI_NON_AUTORISE`). Ils ne sont mis a
   True que dans les scenarios qui doivent prouver le chemin complet — et le
   transport est deja un faux a ce moment-la.

Le compteur imprime a la fin verifie le frein 2 : si une seule ligne de code
appelait le vrai `resend`, le module serait importe et le banc le dirait.

-----------------------------------------------------------------------------
CE QUI EST MESURE
-----------------------------------------------------------------------------
1. Les medias sur le brouillon : qui est accepte, qui est refuse, et pourquoi.
2. La route d'envoi, fermee par defaut : trois verrous independants.
3. L'envoi lui-meme : trace, identite du membre, media en LIEN.
4. Les doublons : un rejeu ne renvoie rien deux fois.
5. L'historique commun : il se CALCULE depuis la trace, aucune seconde ecriture.
6. Le code : la route du coach ne garde aucun controle en propre.
"""

import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RESULTATS = []


def verifier(nom, condition, detail=""):
    ok = bool(condition)
    RESULTATS.append((nom, ok, detail))
    print("  %-6s %s%s" % ("OK" if ok else "ECHEC", nom,
                           ("\n           -> %s" % detail) if (detail and not ok) else ""))
    return ok


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

SECRET = "secret-relais-v636"
COACH_ID = "coach@afroboost.test"
AUTRE_COACH = "autre@afroboost.test"
MEMBRE = "membre.autorise@afroboosteur.test"

os.environ["JWT_SECRET"] = "jwt-secret-fictif-v636"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v636-inexistant:27017")
os.environ["AFROBOOSTEUR_RELAY_SECRET"] = SECRET
os.environ["AFROBOOSTEUR_RELAY_COACH_ID"] = COACH_ID

import asyncio  # noqa: E402
import hashlib  # noqa: E402
import hmac as hmac_module  # noqa: E402
import json as _json  # noqa: E402
import time  # noqa: E402

from fastapi import HTTPException  # noqa: E402

import api.server as S  # noqa: E402
import api.routes.afroboosteur_relais as R  # noqa: E402


# ============================================================================
print("\n0. OUTILLAGE — UN FAUX TRANSPORT, DES COLLECTIONS SANS ECRITURE INUTILE")

APPELS_TRANSPORT = []


async def faux_transport(params, options=None):
    """Ne contacte RIEN. Enregistre ce qu'on lui a demande d'envoyer."""
    APPELS_TRANSPORT.append({"params": dict(params), "options": dict(options or {})})
    return {"id": "resend-faux-%d" % len(APPELS_TRANSPORT)}


class FournisseurFaux(S.P3AI4FournisseurReponse):
    """Meme classe, meme garde `envoi_autorise` — seul le transport change."""

    def __init__(self, envoi_autorise=False, transport=None, expediteur=None):
        super().__init__(envoi_autorise=envoi_autorise, transport=faux_transport,
                         expediteur=expediteur)


S.P3AI4FournisseurReponse = FournisseurFaux
verifier("0a le fournisseur d'envoi est remplace par un faux transport",
         S.P3AI4FournisseurReponse is FournisseurFaux)

# `api.server` importe `resend` tout en haut, pour TOUT le fichier : constater
# sa presence dans sys.modules ne prouverait donc RIEN sur ce lot. Ce qu'il
# faut verrouiller, c'est que la fonction d'envoi reelle n'est jamais
# ATTEINTE. On la remplace par un piege : si une seule ligne de ce lot
# l'appelait, le banc s'arreterait net au lieu d'envoyer un e-mail.
import resend  # noqa: E402

APPELS_RESEND_REEL = []


def _piege_resend(*a, **k):
    APPELS_RESEND_REEL.append(True)
    raise SortieReseauInterdite("resend.Emails.send appele depuis le banc V636")


resend.Emails.send = _piege_resend
verifier("0b le VRAI `resend.Emails.send` est remplace par un piege qui leve",
         resend.Emails.send is _piege_resend)


class Curseur:
    def __init__(self, docs):
        self._docs, self._skip, self._limit = docs, 0, None

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


class CollectionLecture:
    """AUCUNE methode d'ecriture, VOLONTAIREMENT : une ecriture imprevue leve
    AttributeError et le banc s'arrete, au lieu de passer inapercue."""

    def __init__(self, documents=None):
        self.documents = [dict(d) for d in (documents or [])]

    def _ok(self, doc, filtre):
        if not filtre:
            return True
        for cle, val in filtre.items():
            if isinstance(val, dict):
                if "$in" in val and doc.get(cle) not in val["$in"]:
                    return False
                if "$ne" in val and doc.get(cle) == val["$ne"]:
                    return False
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


class CollectionEcrivable(CollectionLecture):
    """`update_one` + `insert_one`, avec un index UNIQUE sur `id` quand il est
    demande — c'est lui qui rend le verrou anti-doublon mesurable."""

    def __init__(self, documents=None, unique_sur=None):
        super().__init__(documents)
        self.unique_sur = unique_sur
        self.ecritures = []

    async def insert_one(self, doc):
        if self.unique_sur:
            cle = doc.get(self.unique_sur)
            if any(d.get(self.unique_sur) == cle for d in self.documents):
                raise Exception("E11000 duplicate key error")
        self.documents.append(dict(doc))
        self.ecritures.append({"genre": "insert", "doc": dict(doc)})
        return type("R", (), {"inserted_id": True})()

    async def update_one(self, filtre, maj, upsert=False, *a, **k):
        self.ecritures.append({"genre": "update", "filtre": dict(filtre),
                               "maj": {k: dict(v) for k, v in maj.items()}})
        for d in self.documents:
            if self._ok(d, filtre):
                d.update(maj.get("$set") or {})
                for champ, valeur in (maj.get("$push") or {}).items():
                    d.setdefault(champ, []).append(valeur)
                return type("R", (), {"matched_count": 1, "modified_count": 1})()
        if not upsert:
            return type("R", (), {"matched_count": 0, "modified_count": 0})()
        candidat = dict(filtre)
        candidat.update(maj.get("$setOnInsert") or {})
        candidat.update(maj.get("$set") or {})
        self.documents.append(candidat)
        return type("R", (), {"matched_count": 0, "modified_count": 0})()


class DBBouchon:
    def __init__(self):
        self._c = {}

    def __getitem__(self, nom):
        self._c.setdefault(nom, CollectionLecture())
        return self._c[nom]

    def __setitem__(self, nom, valeur):
        self._c[nom] = valeur

    def __getattr__(self, nom):
        return self[nom]


class URLFictive:
    def __init__(self, chemin, requete=""):
        self.path, self.query = chemin, requete


class RequeteFictive:
    def __init__(self, methode="GET", chemin="", requete="", headers=None, corps=None):
        self.method = methode
        self.url = URLFictive(chemin, requete)
        self.headers = headers or {}
        self._corps_brut = _json.dumps(corps).encode("utf-8") if corps is not None else b""
        self._a_un_corps = corps is not None

    async def body(self):
        return self._corps_brut

    async def json(self):
        if not self._a_un_corps:
            raise ValueError("pas de corps")
        return _json.loads(self._corps_brut)


def requete_signee(methode, chemin, requete="", corps=None, membre=MEMBRE,
                   secret=SECRET, sans_signature=False):
    horodatage = str(int(time.time()))
    req = RequeteFictive(methode=methode, chemin=chemin, requete=requete,
                         headers={"X-Afroboosteur-Timestamp": horodatage}, corps=corps)
    if membre:
        req.headers["X-Afroboosteur-Membre"] = membre
    if not sans_signature:
        chaine = R._chaine_canonique(methode, chemin, requete, horodatage,
                                     R._empreinte_corps(req._corps_brut))
        req.headers["X-Afroboosteur-Signature"] = hmac_module.new(
            secret.encode(), chaine.encode(), hashlib.sha256).hexdigest()
    return req


def executer(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def media(id_, statut="validee", coach=COACH_ID, fmt="miniature"):
    return {"id": id_, "coach_id": coach, "statut": statut, "format": fmt,
            "niche": "n1", "version": "v1", "source_id": id_,
            "url": "/api/files/f-%s/%s.jpg" % (id_, id_),
            "fichier": {"nom": "%s.jpg" % id_, "type": "image/jpeg", "taille": 1234},
            "cible": {"nom": "Public test"}}


def scenario(medias_bibliotheque=None, brouillon_medias=None, flags_ouverts=False,
             coach_du_dossier=COACH_ID):
    """Une base neuve a chaque fois. Les drapeaux d'envoi sont FERMES sauf
    demande explicite — c'est l'etat de la production au moment de ce lot."""
    b = DBBouchon()
    S.db = b
    R.db = b
    b[S.P3U2_COLLECTION] = CollectionLecture([{
        "id": "msg-1", "coach_id": coach_du_dossier, "action_id": "act-1",
        "from_email": "partenaire@exemple.test", "subject": "Re: proposition",
        "body_text": "Interesse, quand ?", "received_at": "2026-10-19T10:00:00+00:00",
        "statut": "recu", "provider": "resend", "recipient_key": "ref-1",
        "read_at": None, "traite_at": None}])
    b[S.P3S3_ACTIONS] = CollectionLecture([{
        "id": "act-1", "campaign_id": "camp-1", "coach_id": coach_du_dossier,
        "channel": "email", "target": "partenaire@exemple.test",
        "recipient_key": "ref-1", "organisations": ["Partenaire SA"],
        "prospect_ids": ["R-1"], "prospect_uuids": ["uuid-1"]}])
    b[S.P3S1_COLLECTION] = CollectionLecture([
        {"id": "uuid-1", "corbeille": False, "refus_contact": False}])
    texte = "Oui, mardi 10h me convient."
    b[S.P3AI_BROUILLONS] = CollectionEcrivable([{
        "inbound_id": "msg-1", "id": "brouillon-1", "reponse_proposee": texte,
        "genere_le": "2026-10-20T09:00:00+00:00", "intention": "positif",
        "langue": "fr", "medias": list(brouillon_medias or []),
        "media": (brouillon_medias or [None])[0] if brouillon_medias else None}])
    b[S.P3AI4_COLLECTION] = CollectionEcrivable([], unique_sur="id")
    b[S.P3N_COLLECTION] = CollectionEcrivable([])
    b["subscribers"] = CollectionLecture([])
    b[S.V595_MEDIAS] = CollectionLecture(medias_bibliotheque or [])
    b[S.V598_NICHES] = CollectionLecture([
        {"coach_id": COACH_ID, "cle": "n1", "nom": "Niche test"}])
    b["feature_flags"] = CollectionLecture([{
        "id": "feature_flags",
        S.P3AI4_DRAPEAU_ACTIF: flags_ouverts,
        S.P3AI4_DRAPEAU_REEL: flags_ouverts}])
    b["coaches"] = CollectionLecture([{"email": COACH_ID}])
    return b


def empreinte_du_brouillon(b):
    doc = b[S.P3AI_BROUILLONS].documents[0]
    return S.v625_empreinte(str(doc.get("reponse_proposee") or ""), S.v625_medias(doc))


CHEMIN_BROUILLON = "/api/afroboosteur-relais/conversations/msg-1/brouillon"
CHEMIN_ENVOI = "/api/afroboosteur-relais/conversations/msg-1/envoyer"


def enregistrer(b, medias=None, texte="Oui, mardi 10h me convient."):
    corps = {"texte": texte, "draft_hash": empreinte_du_brouillon(b)}
    if medias is not None:
        corps["medias"] = medias
    return executer(R.relais_enregistrer_brouillon(
        "msg-1", requete_signee("POST", CHEMIN_BROUILLON, corps=corps)))


def envoyer(b, empreinte=None, membre=MEMBRE):
    corps = {"confirme": True, "draft_hash": empreinte or empreinte_du_brouillon(b)}
    return executer(R.relais_envoyer_reponse(
        "msg-1", requete_signee("POST", CHEMIN_ENVOI, corps=corps, membre=membre)))


# ============================================================================
print("\n1. LES MEDIAS SUR LE BROUILLON — QUI PASSE, QUI NE PASSE PAS")

b = scenario(medias_bibliotheque=[media("m-ok")])
res = enregistrer(b, medias=[{"media_id": "m-ok"}])
doc = b[S.P3AI_BROUILLONS].documents[0]
verifier("1a un media VALIDE de la bibliotheque du coach est joint au brouillon",
         len(doc.get("medias") or []) == 1
         and (doc["medias"][0] or {}).get("media_id") == "m-ok",
         str(doc.get("medias")))
verifier("1b `media` (singulier) est ecrit en meme temps, pour les lecteurs V620",
         (doc.get("media") or {}).get("media_id") == "m-ok")
verifier("1c l'empreinte rendue tient compte du media joint "
         "(sinon l'envoi suivant serait refuse pour empreinte discordante)",
         res.get("draft_hash") == empreinte_du_brouillon(b)
         and res.get("draft_hash") != S.v625_empreinte(doc["reponse_proposee"], []))

for statut in ("en_cours", "a_verifier", "archivee"):
    b = scenario(medias_bibliotheque=[media("m-x", statut=statut)])
    avant = _json.dumps(b[S.P3AI_BROUILLONS].documents[0], sort_keys=True)
    try:
        enregistrer(b, medias=[{"media_id": "m-x"}])
        refuse = False
    except HTTPException as e:
        refuse = e.status_code == 400
    verifier("1d un media `%s` est REFUSE — seul `validee` peut partir par ce canal" % statut,
             refuse)
    verifier("1d-bis ... et le brouillon n'a pas bouge d'un octet (`%s`)" % statut,
             _json.dumps(b[S.P3AI_BROUILLONS].documents[0], sort_keys=True) == avant)

b = scenario(medias_bibliotheque=[media("m-autre", coach=AUTRE_COACH)])
try:
    enregistrer(b, medias=[{"media_id": "m-autre"}])
    refuse_autre = False
except HTTPException as e:
    refuse_autre = e.status_code == 400
verifier("1e le media d'un AUTRE coach est refuse — la portee est celle du coach configure",
         refuse_autre)

b = scenario(medias_bibliotheque=[media("m-ok")])
try:
    enregistrer(b, medias=[{"fichier_url": "/api/files/f-1/x.jpg"}])
    refuse_url = False
except HTTPException as e:
    refuse_url = e.status_code == 400 and "media_id" in (e.detail or "")
verifier("1f `fichier_url` est refuse NOMMEMENT : un membre afroboosteur ne designe "
         "jamais un fichier d'afroboost.com directement", refuse_url)

b = scenario(medias_bibliotheque=[media("m-%d" % i) for i in range(8)])
try:
    enregistrer(b, medias=[{"media_id": "m-%d" % i} for i in range(7)])
    refuse_trop = False
except HTTPException as e:
    refuse_trop = e.status_code == 400 and str(S.V625_MEDIAS_MAX) in (e.detail or "")
verifier("1g au-dela de V625_MEDIAS_MAX (%d) c'est refuse, avec LA MEME borne que le coach"
         % S.V625_MEDIAS_MAX, refuse_trop)

b = scenario(medias_bibliotheque=[media("m-ok")])
enregistrer(b, medias=[{"media_id": "m-ok"}])
enregistrer(b, texte="Texte corrige, medias non mentionnes.")   # cle `medias` ABSENTE
doc = b[S.P3AI_BROUILLONS].documents[0]
verifier("1h cle `medias` ABSENTE = medias inchanges (meme semantique que la route du coach)",
         len(doc.get("medias") or []) == 1 and doc["reponse_proposee"].startswith("Texte corrige"))
enregistrer(b, medias=[])
doc = b[S.P3AI_BROUILLONS].documents[0]
verifier("1i `medias: []` RETIRE les medias — et `media` repasse a None",
         (doc.get("medias") or []) == [] and doc.get("media") is None)


# ============================================================================
print("\n2. LA ROUTE D'ENVOI — FERMEE PAR DEFAUT, TROIS VERROUS INDEPENDANTS")

os.environ.pop("AFROBOOSTEUR_RELAIS_ENVOI_ACTIF", None)
b = scenario()
APPELS_TRANSPORT.clear()
try:
    envoyer(b)
    code_ferme = None
except HTTPException as e:
    code_ferme = e.status_code
verifier("2a interrupteur ABSENT -> 503, l'envoi ne part pas", code_ferme == 503)
verifier("2a-bis ... et RIEN n'a ete reserve ni appele",
         len(b[S.P3AI4_COLLECTION].documents) == 0 and len(APPELS_TRANSPORT) == 0)

for valeur in ("false", "0", "", "non"):
    os.environ["AFROBOOSTEUR_RELAIS_ENVOI_ACTIF"] = valeur
    verifier("2b `AFROBOOSTEUR_RELAIS_ENVOI_ACTIF=%r` ne l'ouvre pas" % valeur,
             R._envoi_actif() is False)
os.environ["AFROBOOSTEUR_RELAIS_ENVOI_ACTIF"] = "true"
verifier("2c seul `true` l'ouvre", R._envoi_actif() is True)

os.environ.pop("AFROBOOSTEUR_RELAIS_FIL_ACTIF", None)
os.environ.pop("AFROBOOSTEUR_RELAIS_RELANCES_ACTIF", None)
verifier("2d les interrupteurs sont INDEPENDANTS : ouvrir l'envoi n'ouvre ni le fil "
         "ni les relances",
         R._envoi_actif() is True and R._fil_actif() is False and R._relances_actif() is False)

b = scenario()
try:
    executer(R.relais_envoyer_reponse(
        "msg-1", requete_signee("POST", CHEMIN_ENVOI, corps={"confirme": True},
                                sans_signature=True)))
    code_sign = None
except HTTPException as e:
    code_sign = e.status_code
verifier("2e sans signature HMAC c'est REFUSE, meme interrupteur ouvert",
         code_sign in (401, 403), "code=%r" % code_sign)

b = scenario(coach_du_dossier=AUTRE_COACH)
try:
    envoyer(b)
    code_portee = None
except HTTPException as e:
    code_portee = e.status_code
verifier("2f un dossier HORS du coach configure -> 404, avant tout envoi", code_portee == 404)

# ⚠️ LE CAS DE LA PRODUCTION, ET LE PIEGE QU'IL CONTIENT. Sur cette
# plateforme, le coach configure EST le super-admin (`DEFAULT_COACH_ID =
# SUPER_ADMIN_EMAILS[0]`, V244). Pour un super-admin, `p3ai_est_proprietaire`
# — le controle de propriete que `p3ai4_envoyer_reponse_pour` applique —
# devient PERMISSIF : il accepterait le dossier d'un autre coach. Ce qui
# cloisonne reellement est donc `_message_de_la_portee`, en amont, qui impose
# `{"coach_id": <coach configure>}` sans jamais rendre un filtre vide. Si
# quelqu'un retirait cet appel de la route d'envoi, CE test tomberait — et lui
# seul : le test 2f ci-dessus passerait toujours, puisqu'il utilise un coach
# ordinaire.
_vrai_super = S.SUPER_ADMIN_EMAILS
try:
    S.SUPER_ADMIN_EMAILS = [COACH_ID]
    b = scenario(coach_du_dossier=AUTRE_COACH)
    APPELS_TRANSPORT.clear()
    try:
        envoyer(b)
        code_super = None
    except HTTPException as e:
        code_super = e.status_code
    verifier("2g MEME si le coach configure est le SUPER-ADMIN, un dossier d'un autre "
             "coach reste un 404 — la portee du relais ne devient jamais vide",
             code_super == 404, "code=%r" % code_super)
    verifier("2g-bis ... et rien n'a ete reserve ni envoye dans ce cas",
             len(b[S.P3AI4_COLLECTION].documents) == 0 and len(APPELS_TRANSPORT) == 0)
finally:
    S.SUPER_ADMIN_EMAILS = _vrai_super


# ============================================================================
print("\n3. L'ENVOI — TRACE, IDENTITE DU MEMBRE, MEDIA EN LIEN")

b = scenario(medias_bibliotheque=[media("m-ok")], flags_ouverts=False)
enregistrer(b, medias=[{"media_id": "m-ok"}])
APPELS_TRANSPORT.clear()
res = envoyer(b)
trace = b[S.P3AI4_COLLECTION].documents[0]
verifier("3a drapeaux EN BASE fermes : la trace est posee, mais le transport n'est JAMAIS appele",
         len(APPELS_TRANSPORT) == 0 and trace.get("error_code") == "ENVOI_NON_AUTORISE",
         "%d appel(s), error_code=%r" % (len(APPELS_TRANSPORT), trace.get("error_code")))
verifier("3a-bis aucune note commerciale n'est posee quand rien n'est parti",
         len(b[S.P3N_COLLECTION].documents) == 0)

b = scenario(medias_bibliotheque=[media("m-ok")], flags_ouverts=True)
enregistrer(b, medias=[{"media_id": "m-ok"}])
APPELS_TRANSPORT.clear()
res = envoyer(b)
trace = b[S.P3AI4_COLLECTION].documents[0]
verifier("3b les trois verrous ouverts : UN seul appel au (faux) transport",
         len(APPELS_TRANSPORT) == 1, str(len(APPELS_TRANSPORT)))
verifier("3c `send_status` = envoye, et la reponse le dit",
         trace.get("send_status") == S.P3AI4_ENVOYE
         and (res.get("envoi") or {}).get("send_status") == S.P3AI4_ENVOYE)
verifier("3d `approved_by` reste LE COACH proprietaire — c'est sa tenance qui est engagee",
         trace.get("approved_by") == COACH_ID, str(trace.get("approved_by")))
verifier("3e `approved_by_membre` porte le MEMBRE afroboosteur — qui a clique est trace",
         trace.get("approved_by_membre") == MEMBRE, str(trace.get("approved_by_membre")))
verifier("3f le prospect destinataire est trace avec la reponse",
         trace.get("recipient_key") == "ref-1" and trace.get("prospect_uuid") == "uuid-1")
verifier("3g le media parti est fige dans la trace (instantane, independant de la bibliotheque)",
         len(trace.get("medias") or []) == 1
         and (trace["medias"][0] or {}).get("media_id") == "m-ok")

params = APPELS_TRANSPORT[0]["params"]
verifier("3h le media part en LIEN, jamais en piece jointe",
         "attachments" not in params, str(sorted(params.keys())))
verifier("3h-bis ... et son adresse figure bien dans le message",
         any("m-ok" in str(params.get(c) or "") for c in ("html", "text")))

rendu = _json.dumps(res)
verifier("3i la reponse du relais ne divulgue NI l'adresse du prospect NI le coach",
         "partenaire@exemple.test" not in rendu and COACH_ID not in rendu, rendu[:200])

# ─────────────────────────────────────────────────────────────────────────────
# LE DESTINATAIRE DOIT POUVOIR OUVRIR LE LIEN — sinon la fonction est
# cosmetique. Le media part en LIEN `/api/files/{id}/{nom}` (3h ci-dessus), et
# la route qui sert ce chemin n'a AUCUNE garde d'authentification : un prospect
# qui recoit l'e-mail peut donc l'ouvrir. C'est le fonctionnement DEJA en place
# pour les reponses du coach, ce lot ne le change pas.
#
# ⚠️ COROLLAIRE A CONNAITRE, PAS A CORRIGER ICI : ce lien est donc ouvert a
#    QUICONQUE le possede. L'identifiant est imprevisible, mais ce n'est pas un
#    controle d'acces. Le durcir changerait le comportement des reponses du
#    coach, hors du perimetre de ce lot — c'est une decision a prendre a part.
# ─────────────────────────────────────────────────────────────────────────────
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "api", "server.py"), encoding="utf-8").read()
_i = _src.index('@api_router.get("/files/{file_id}/{filename}")')
_bloc_fichiers = _src[_i:_src.index("\n@api_router", _i + 10)]
verifier("3n le media part sous la forme `/api/files/...`, servie par une route EXISTANTE",
         '@api_router.get("/files/{file_id}/{filename}")' in _src
         and str(params.get("html") or "").find("/api/files/") >= 0)
verifier("3o cette route n'exige AUCUNE authentification — le destinataire peut donc "
         "ouvrir le lien (fonctionnement deja en place pour le coach)",
         not __import__("re").search(
             r'_v309_require_coach_or_admin|require_auth|_v263_authenticated_coach',
             _bloc_fichiers))


# ─────────────────────────────────────────────────────────────────────────────
print("\n3bis. LA BORNE `validee` TIENT A L'ENVOI, PAS SEULEMENT A L'ECRITURE")
#
# EXIGER `validee` A L'ECRITURE NE SUFFIT PAS, et la section 1 ne pouvait pas
# le voir. Le brouillon est PARTAGE : le coach attache ses medias depuis son
# propre tableau de bord, dont la route accepte tout sauf `archivee`. Un
# membre cliquant « Envoyer » expediait alors un media que ce canal avait
# justement refuse. Deuxieme cas, independant : un media archive APRES avoir
# ete attache reste dans l'instantane du brouillon — voulu pour le coach, mais
# pas pour un tiers qui envoie en son nom.
# ─────────────────────────────────────────────────────────────────────────────

snapshot = {"media_id": "m-pose", "origine": "bibliotheque", "type": "image",
            "url": "/api/files/f-1/m-pose.jpg", "miniature_url": None,
            "titre": "m-pose.jpg", "format": "miniature", "duree": None,
            "niche_nom": "Niche test", "public": "Public test",
            "choisi_at": "2026-10-20T09:00:00+00:00"}

for statut, libelle in (("en_cours", "attache par le COACH alors qu'il etait `en_cours`"),
                        ("archivee", "ARCHIVE apres avoir ete attache")):
    b = scenario(medias_bibliotheque=[media("m-pose", statut=statut)],
                 brouillon_medias=[dict(snapshot)], flags_ouverts=True)
    APPELS_TRANSPORT.clear()
    try:
        envoyer(b)
        code = None
    except HTTPException as e:
        code = e.status_code
    verifier("3j un media %s est REFUSE a l'envoi (409)" % libelle, code == 409,
             "code=%r" % code)
    verifier("3j-bis ... et rien n'a ete reserve ni envoye (%s)" % statut,
             len(b[S.P3AI4_COLLECTION].documents) == 0 and len(APPELS_TRANSPORT) == 0)

b = scenario(medias_bibliotheque=[],
             brouillon_medias=[dict(snapshot)], flags_ouverts=True)
APPELS_TRANSPORT.clear()
try:
    envoyer(b)
    code = None
except HTTPException as e:
    code = e.status_code
verifier("3k un media DISPARU de la mediatheque est refuse a l'envoi", code == 409)

# LIMITE ASSUMEE, mesuree pour qu'elle ne soit pas decouverte en production :
# un fichier televerse par le coach (hors mediatheque) ne peut pas partir par
# ce canal — rien ne permet de verifier qu'il est valide.
b = scenario(medias_bibliotheque=[media("m-ok")], flags_ouverts=True,
             brouillon_medias=[{"origine": "fichier", "type": "image",
                                "url": "/api/files/f-9/photo.jpg", "titre": "photo.jpg"}])
APPELS_TRANSPORT.clear()
try:
    envoyer(b)
    code, detail = None, ""
except HTTPException as e:
    code, detail = e.status_code, e.detail or ""
verifier("3l LIMITE ASSUMEE : un fichier televerse hors mediatheque fait refuser l'envoi, "
         "avec un motif qui dit quoi faire", code == 409 and "médiathèque" in detail,
         "code=%r detail=%r" % (code, detail[:90]))

b = scenario(medias_bibliotheque=[media("m-pose", statut="validee")],
             brouillon_medias=[dict(snapshot)], flags_ouverts=True)
APPELS_TRANSPORT.clear()
res_ok = envoyer(b)
verifier("3m DISCRIMINANCE : le MEME brouillon dont le media est bien `validee` part "
         "normalement — la borne refuse ce qu'il faut, pas tout",
         res_ok.get("deja_envoye") is False and len(APPELS_TRANSPORT) == 1,
         "%d appel(s)" % len(APPELS_TRANSPORT))


# ============================================================================
print("\n4. LES DOUBLONS — UN REJEU NE REENVOIE RIEN")

b = scenario(medias_bibliotheque=[media("m-ok")], flags_ouverts=True)
enregistrer(b, medias=[{"media_id": "m-ok"}])
APPELS_TRANSPORT.clear()
empreinte = empreinte_du_brouillon(b)
premier = envoyer(b, empreinte)
second = envoyer(b, empreinte)
verifier("4a le premier envoi part", premier.get("deja_envoye") is False)
verifier("4b le second s'entend repondre « deja envoye » — un 200, pas une erreur",
         second.get("deja_envoye") is True)
verifier("4c le transport n'a ete appele QU'UNE fois", len(APPELS_TRANSPORT) == 1,
         str(len(APPELS_TRANSPORT)))
verifier("4d une SEULE ligne de reservation existe",
         len(b[S.P3AI4_COLLECTION].documents) == 1,
         str(len(b[S.P3AI4_COLLECTION].documents)))

# ─────────────────────────────────────────────────────────────────────────────
# IL Y A DEUX VERROUS, PAS UN — ET MA PREMIERE VERSION DE CE TEST NE MESURAIT
# QUE LE SECOND. Retirer l'unicite de `id` ne changeait RIEN au resultat, et
# le test « discriminant » passait sans rien prouver. La raison :
#
#   1. LE DOUBLE CLIC ORDINAIRE est arrete par la RELECTURE prealable
#      (`find_one({"id": cle})`), bien avant l'insertion. C'est ce verrou-la
#      que le test 4c mesure.
#   2. LA COURSE REELLE — deux requetes en vol en meme temps, dont aucune ne
#      voit encore la reservation de l'autre — n'est arretee que par
#      l'insertion unique et le rattrapage du doublon (`E11000`). La relecture
#      est aveugle dans ce cas.
#
# On mesure donc les deux SEPAREMENT, en aveuglant la relecture pour isoler le
# second. C'est la seule facon de savoir lequel protege quoi.
# ─────────────────────────────────────────────────────────────────────────────


class ReservationAveugle(CollectionEcrivable):
    """La relecture ne voit RIEN (comme une requete concurrente encore en vol),
    mais l'unicite de `id` reste. Seul le rattrapage `E11000` peut arreter."""

    async def find_one(self, filtre=None, projection=None, *a, **k):
        if self._aveugle:
            return None
        return await super().find_one(filtre, projection, *a, **k)


b = scenario(medias_bibliotheque=[media("m-ok")], flags_ouverts=True)
reservation = ReservationAveugle([], unique_sur="id")
reservation._aveugle = True
b[S.P3AI4_COLLECTION] = reservation
enregistrer(b, medias=[{"media_id": "m-ok"}])
APPELS_TRANSPORT.clear()
empreinte = empreinte_du_brouillon(b)
envoyer(b, empreinte)
reponse_course = envoyer(b, empreinte)
verifier("4e COURSE : relecture aveugle, l'insertion unique rattrape le doublon — "
         "le transport n'est appele qu'UNE fois",
         len(APPELS_TRANSPORT) == 1, "%d appel(s)" % len(APPELS_TRANSPORT))
verifier("4e-bis ... et le second appel rend bien « deja envoye »",
         reponse_course.get("deja_envoye") is True)

# DISCRIMINANCE : les deux verrous retires, le rejeu DOIT passer. Si ce test
# echouait, c'est que le banc empeche les doublons par un hasard de montage et
# que 4c/4e ne prouvent rien.
b = scenario(medias_bibliotheque=[media("m-ok")], flags_ouverts=True)
sans_verrou = ReservationAveugle([], unique_sur=None)
sans_verrou._aveugle = True
b[S.P3AI4_COLLECTION] = sans_verrou
enregistrer(b, medias=[{"media_id": "m-ok"}])
APPELS_TRANSPORT.clear()
empreinte = empreinte_du_brouillon(b)
envoyer(b, empreinte)
try:
    envoyer(b, empreinte)
except Exception:
    pass
verifier("4f DISCRIMINANCE : les DEUX verrous retires, le rejeu passe — 4c et 4e "
         "mesurent donc bien les verrous, chacun le sien",
         len(APPELS_TRANSPORT) == 2,
         "%d appel(s), %d ligne(s)" % (len(APPELS_TRANSPORT), len(sans_verrou.documents)))


# ============================================================================
print("\n5. L'HISTORIQUE COMMUN — IL SE CALCULE, IL NE SE RECOPIE PAS")

b = scenario(medias_bibliotheque=[media("m-ok")], flags_ouverts=True)
enregistrer(b, medias=[{"media_id": "m-ok"}])
APPELS_TRANSPORT.clear()
envoyer(b)
traces = b[S.P3AI4_COLLECTION].documents
messages = b[S.P3U2_COLLECTION].documents
action = b[S.P3S3_ACTIONS].documents[0]
fil = S.v619_fil(messages, action, {"id": "camp-1"}, None, traces)
sortants = [e for e in fil if e.get("direction") == "outgoing"]
verifier("5a la reponse envoyee apparait dans le fil, cote sortant",
         len(sortants) == 1, str([e.get("direction") for e in fil]))
verifier("5b elle y apparait AVEC son media",
         len((sortants[0].get("medias") or [])) == 1 if sortants else False,
         str(sortants[0].get("medias")) if sortants else "aucun sortant")
verifier("5c le texte du fil est bien celui qui est parti",
         sortants[0].get("text") == "Oui, mardi 10h me convient." if sortants else False)
verifier("5d AUCUNE seconde collection d'historique n'a ete ecrite : le fil derive de la "
         "trace, donc les deux sites lisent la MEME source",
         len(b[S.P3AI_BROUILLONS].documents) == 1 and len(traces) == 1)
verifier("5e une seule note commerciale, posee par le chemin AI-P3 existant",
         len(b[S.P3N_COLLECTION].documents) == 1,
         str(len(b[S.P3N_COLLECTION].documents)))


# ============================================================================
print("\n6. LE CODE — UNE SEULE REGLE, DEUX APPELANTS")

source_serveur = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "..", "api", "server.py"), encoding="utf-8").read()
source_relais = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "api", "routes", "afroboosteur_relais.py"),
                     encoding="utf-8").read()

import re  # noqa: E402

bloc_route = source_serveur[
    source_serveur.index('@api_router.post("/prospect-inbound/{inbound_id}/envoyer-reponse")'):]
bloc_route = bloc_route[:bloc_route.index("\n@") if "\n@" in bloc_route[10:] else len(bloc_route)]
verifier("6a la route du coach ne garde AUCUN controle en propre — elle delegue",
         "p3ai4_envoyer_reponse_pour(" in bloc_route
         and not re.search(r'p3ai_est_proprietaire|p3ai4_destinataire|P3AI4FournisseurReponse',
                           bloc_route),
         bloc_route[:160])
verifier("6b la route du coach garde SA garde JWT (rien n'a ete affaibli)",
         "_v309_require_coach_or_admin(request)" in bloc_route)
verifier("6c le relais n'ecrit AUCUNE reservation lui-meme",
         not re.search(r'P3AI4_COLLECTION\]\.(insert_one|update_one)', source_relais))
verifier("6d `approved_by` n'est JAMAIS remplace par le membre externe",
         '"approved_by": email' in source_serveur
         and not re.search(r'"approved_by":\s*(membre|membre_externe)', source_serveur))
verifier("6e aucun client HTTP dans le relais",
         not re.search(r'^\s*import\s+(requests|httpx)', source_relais, re.M))
verifier("6f le relais ne contacte jamais `resend` lui-meme",
         not re.search(r'import\s+resend|Emails\.send', source_relais))

os.environ.pop("AFROBOOSTEUR_RELAIS_ENVOI_ACTIF", None)
os.environ.pop("AFROBOOSTEUR_RELAY_SECRET", None)
os.environ.pop("AFROBOOSTEUR_RELAY_COACH_ID", None)

# ============================================================================
total = len(RESULTATS)
reussites = sum(1 for _, ok, _ in RESULTATS if ok)
echecs = total - reussites
print("\n" + "=" * 78)
print("V636 ENVOI + MEDIAS DEPUIS AFROBOOSTEUR : %d / %d verifications" % (reussites, total))
print("Appels au (faux) transport : %d — aucun n'est sorti de la machine" % len(APPELS_TRANSPORT))
print("Appels au VRAI `resend.Emails.send` : %d%s" % (
    len(APPELS_RESEND_REEL), "  ⚠️ A CORRIGER" if APPELS_RESEND_REEL else ""))
print("E-mails REELS envoyes : 0")
print("=" * 78)
if echecs:
    print("\nECHECS :")
    for nom, ok, detail in RESULTATS:
        if not ok:
            print("  - %s%s" % (nom, ("\n      %s" % detail) if detail else ""))
    sys.exit(1)
