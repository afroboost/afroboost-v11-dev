#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PHASE 6A — REPONDRE A UN PARTENAIRE DEPUIS LE RELAIS. ZERO ENVOI REEL.

CE QUE CE LOT AJOUTE (api/routes/afroboosteur_relais.py)
==============================================================================
Trois routes neuves, toujours sous la meme garde HMAC que les trois lectures
existantes (phases 4/5), jamais un acces generique aux routes privees :

  * GET  .../conversations/{id}/brouillon        — lecture du brouillon.
  * POST .../conversations/{id}/brouillon        — ENREGISTRE le texte d'un
                                                     brouillon (jamais le
                                                     media), avec un controle
                                                     de concurrence par
                                                     empreinte : la SEULE
                                                     ecriture Mongo du fichier.
  * POST .../conversations/{id}/apercu-reponse    — VALIDE un envoi possible,
                                                     sans jamais le reserver
                                                     ni l'executer.

CE QUE CE BANC PROUVE
==============================================================================
  1. L'ECRITURE EST STRICTEMENT BORNEE : un bouchon dedie (`CollectionEcrivable`)
     n'est pose QUE sur `P3AI_BROUILLONS` ; toutes les autres collections
     (`P3AI4_COLLECTION` comprise — reservation/envoi) restent sur le bouchon
     de base, qui NE DEFINIT AUCUNE methode d'ecriture. Une ecriture
     accidentelle ailleurs ferait planter le test avec AttributeError plutot
     que de passer inapercue.
  2. JAMAIS D'ECRASEMENT SILENCIEUX : une empreinte perimee refuse
     l'enregistrement (409) et le texte en base reste EXACTEMENT l'original —
     verifie en le relisant APRES le refus, pas seulement en lisant le code
     d'erreur.
  3. LE MEDIA N'EST JAMAIS TOUCHE par une correction de texte depuis ce relais.
  4. La portee par coach est respectee : un message d'un autre coach rend 404,
     jamais une fuite d'existence.
  5. Une signature invalide ou absente refuse AVANT toute lecture en base.
  6. L'apercu reutilise EXACTEMENT les memes refus que l'envoi reel du coach
     (brouillon absent, vide, place-holder non complete, empreinte perimee,
     deja envoye, contexte perime, STOP, destinataire introuvable) — jamais
     une regle reecrite a part qui pourrait diverger.
  7. Un `pret: true` ne se produit QUE quand toutes les conditions sont
     reunies, et porte le texte + destinataire exacts.
  8. Aucune sortie reseau (DNS/socket bloques au niveau OS).

Lancement :
    python3 tests/test_p4_relais_reponse_partenaire.py
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

SECRET = "secret-p6a-reponse-partenaire-sans-rapport-avec-la-production"
COACH_ID = "coach.p6a.fictif@exemple.test"
AUTRE_COACH = "autre.coach.fictif@exemple.test"
os.environ["JWT_SECRET"] = "jwt-secret-fictif-p6a"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p6a-inexistant:27017")
os.environ["AFROBOOSTEUR_RELAY_SECRET"] = SECRET
os.environ["AFROBOOSTEUR_RELAY_COACH_ID"] = COACH_ID

import asyncio  # noqa: E402
import hashlib  # noqa: E402
import hmac as hmac_module  # noqa: E402
import time  # noqa: E402

from fastapi import HTTPException  # noqa: E402

import api.server as S  # noqa: E402
import api.routes.afroboosteur_relais as R  # noqa: E402


# ============================================================================
print("\n0. OUTILLAGE")


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
    """AUCUNE methode d'ecriture definie, VOLONTAIREMENT — voir l'en-tete."""

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


class CollectionEcrivable(CollectionBouchon):
    """SEULE collection du banc a offrir `update_one` — reservee a
    P3AI_BROUILLONS dans `scenario_de_base()`. Toutes les autres collections
    (P3AI4_COLLECTION comprise) restent le bouchon lecture-seule ci-dessus :
    une ecriture accidentelle ailleurs ferait planter le test avec
    AttributeError, exactement comme avant ce lot.
    """

    def __init__(self, documents=None):
        super().__init__(documents)
        self.ecritures = []

    async def update_one(self, filtre, maj, upsert=False, *a, **k):
        self.ecritures.append({"filtre": dict(filtre), "maj": {k: dict(v) for k, v in maj.items()}})
        for d in self.documents:
            if self._ok(d, filtre):
                d.update(maj.get("$set") or {})
                return type("R", (), {"matched_count": 1, "modified_count": 1, "upserted_id": None})()
        if not upsert:
            return type("R", (), {"matched_count": 0, "modified_count": 0, "upserted_id": None})()
        candidat = dict(filtre)
        candidat.update(maj.get("$setOnInsert") or {})
        candidat.update(maj.get("$set") or {})
        self.documents.append(candidat)
        return type("R", (), {"matched_count": 0, "modified_count": 0, "upserted_id": True})()


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


class RequeteFictive:
    def __init__(self, methode="GET", chemin="", requete="", headers=None,
                 corps=None):
        self.method = methode
        self.url = URLFictive(chemin, requete)
        self.headers = headers or {}
        # UNE SEULE SERIALISATION, reutilisee par .body() ET .json() — exactement
        # comme un vrai `Request` Starlette (le flux est lu une fois, mis en
        # cache). Sans cela, l'empreinte signee et le JSON analyse pourraient
        # porter sur deux representations differentes du meme dict Python.
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
                    decalage=0, sans_signature=False):
    horodatage = str(int(time.time()) + decalage)
    req = RequeteFictive(methode=methode, chemin=chemin, requete=requete,
                         headers={"X-Afroboosteur-Timestamp": horodatage}, corps=corps)
    if not sans_signature:
        req.headers["X-Afroboosteur-Signature"] = signer(
            secret, methode, chemin, requete, horodatage, req._corps_brut)
    return req


def executer(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


INSTANT_BROUILLON = "2026-10-20T09:00:00+00:00"
INSTANT_NOTE_RECENTE = "2026-10-25T09:00:00+00:00"


def base_neuve():
    b = DBBouchon({})
    S.db = b
    R.db = b
    return b


def message_valide(id_="msg-1", coach=COACH_ID, action_id="act-1"):
    return {"id": id_, "coach_id": coach, "action_id": action_id,
            "from_email": "partenaire@exemple.test", "subject": "Re: proposition",
            "body_text": "Interesse, quand ?", "received_at": "2026-10-19T10:00:00+00:00",
            "statut": "recu", "provider": "resend", "read_at": None, "traite_at": None}


def action_valide(id_="act-1", coach=COACH_ID):
    return {"id": id_, "campaign_id": "camp-1", "coach_id": coach,
            "channel": "email", "target": "partenaire@exemple.test",
            "recipient_key": "ref-1", "organisations": ["Partenaire SA"],
            "prospect_ids": ["R-1"], "prospect_uuids": ["uuid-1"]}


def fiche_valide(id_="uuid-1"):
    return {"id": id_, "corbeille": False, "refus_contact": False}


def brouillon_valide(reponse="Oui, mardi 10h me convient.", genere_le=INSTANT_BROUILLON):
    texte = reponse
    medias = S.v625_medias({"medias": [], "media": None})
    empreinte = S.v625_empreinte(texte, medias)
    return {"inbound_id": "msg-1", "reponse_proposee": texte, "genere_le": genere_le,
            "intention": "positif", "langue": "fr", "medias": [], "media": None,
            "id": "brouillon-1"}, empreinte


def scenario_de_base():
    b = base_neuve()
    b[S.P3U2_COLLECTION] = CollectionBouchon([message_valide()])
    b[S.P3S3_ACTIONS] = CollectionBouchon([action_valide()])
    b[S.P3S1_COLLECTION] = CollectionBouchon([fiche_valide()])
    brouillon, empreinte = brouillon_valide()
    b[S.P3AI_BROUILLONS] = CollectionEcrivable([brouillon])
    b[S.P3AI4_COLLECTION] = CollectionBouchon([])
    b["subscribers"] = CollectionBouchon([])
    b[S.P3N_COLLECTION] = CollectionBouchon([])
    return b, empreinte


def requete_apercu(empreinte, inbound_id="msg-1", **kw):
    return requete_signee("POST", "/api/afroboosteur-relais/conversations/%s/apercu-reponse" % inbound_id,
                          corps={"draft_hash": empreinte}, **kw)


def requete_brouillon(inbound_id="msg-1", **kw):
    return requete_signee("GET", "/api/afroboosteur-relais/conversations/%s/brouillon" % inbound_id, **kw)


def requete_enregistrer(texte, draft_hash="", inbound_id="msg-1", **kw):
    return requete_signee(
        "POST", "/api/afroboosteur-relais/conversations/%s/brouillon" % inbound_id,
        corps={"texte": texte, "draft_hash": draft_hash}, **kw)


# ============================================================================
print("\n1. SUCCES — toutes les conditions reunies")

b, empreinte = scenario_de_base()
rep = executer(R.relais_apercu_reponse("msg-1", requete_apercu(empreinte)))
verifier("1a pret: true", rep["pret"] is True, str(rep))
verifier("1b le texte exact du brouillon est rendu", rep["texte"] == "Oui, mardi 10h me convient.")
verifier("1c le destinataire est resolu", rep["destinataire"] == "partenaire@exemple.test")
verifier("1d deja_envoye: false", rep["deja_envoye"] is False)
verifier("1e aucune ecriture n'a eu lieu (collection toujours a 0 trace d'envoi)",
         len(b[S.P3AI4_COLLECTION].documents) == 0)

# ============================================================================
print("\n2. BROUILLON LU EN LECTURE SEULE")

b2, empreinte2 = scenario_de_base()
rep_b = executer(R.relais_lire_brouillon("msg-1", requete_brouillon()))
verifier("2a le brouillon est rendu", rep_b["brouillon"] is not None and
         rep_b["brouillon"]["reponse_proposee"] == "Oui, mardi 10h me convient.")
verifier("2b lu/traite refletent le message (aucun des deux ici)",
         rep_b["lu"] is False and rep_b["traite"] is False)
verifier("2c contexte_obsolete: false (rien de plus recent que le brouillon)",
         rep_b["contexte_obsolete"] is False)
verifier("2d draft_hash calcule ICI correspond EXACTEMENT a celui attendu par l'apercu "
         "(afroboosteur.com n'a jamais besoin de connaitre l'algorithme)",
         rep_b["draft_hash"] == empreinte2, "%s != %s" % (rep_b["draft_hash"], empreinte2))

# ============================================================================
print("\n2bis. ENREGISTRER UN BROUILLON — édition libre, jamais d'écrasement silencieux")

# a. Correction d'un brouillon EXISTANT, empreinte a jour -> accepte.
b2b, empreinte2b = scenario_de_base()
rep_ecrit = executer(R.relais_enregistrer_brouillon(
    "msg-1", requete_enregistrer("Finalement mercredi 14h, si possible.", empreinte2b)))
verifier("2bis-a correction acceptee, le nouveau texte est rendu",
         rep_ecrit["brouillon"]["reponse_proposee"] == "Finalement mercredi 14h, si possible.")
verifier("2bis-a' une nouvelle empreinte, differente de l'ancienne, est rendue",
         rep_ecrit["draft_hash"] != empreinte2b and rep_ecrit["draft_hash"])
verifier("2bis-a'' exactement UNE ecriture Mongo, sur P3AI_BROUILLONS",
         len(b2b[S.P3AI_BROUILLONS].ecritures) == 1)

# b. EMPREINTE PERIMEE (le brouillon a change depuis la derniere lecture) ->
#    refus NET, et le texte en base reste EXACTEMENT celui d'avant.
b2c, _ = scenario_de_base()
try:
    executer(R.relais_enregistrer_brouillon(
        "msg-1", requete_enregistrer("Un texte qui ne devrait jamais s'ecrire.", "empreinte-perimee")))
    verifier("2bis-b empreinte perimee -> refus (409)", False)
except HTTPException as e:
    verifier("2bis-b empreinte perimee -> refus (409)", e.status_code == 409, str(e.status_code))
verifier(
    "2bis-b' RIEN N'A ETE ECRASE : le texte en base est encore l'original",
    executer(b2c[S.P3AI_BROUILLONS].find_one({"inbound_id": "msg-1"}))["reponse_proposee"]
    == "Oui, mardi 10h me convient.",
)

# c. PREMIER BROUILLON (aucun n'existe encore) — draft_hash vide accepte.
b2d, _ = scenario_de_base()
b2d[S.P3AI_BROUILLONS] = CollectionEcrivable([])
rep_premier = executer(R.relais_enregistrer_brouillon(
    "msg-1", requete_enregistrer("Bonjour, je reviens vers vous rapidement.", "")))
verifier("2bis-c premier brouillon (empreinte vide, aucun brouillon prealable) -> accepte",
         rep_premier["brouillon"]["reponse_proposee"] == "Bonjour, je reviens vers vous rapidement.")

# d. Un appelant qui CROIT qu'un brouillon existe deja (empreinte non vide)
#    alors qu'il n'y en a AUCUN -> meme refus : sa vue est perimee elle aussi.
b2e, _ = scenario_de_base()
b2e[S.P3AI_BROUILLONS] = CollectionEcrivable([])
try:
    executer(R.relais_enregistrer_brouillon(
        "msg-1", requete_enregistrer("Texte quelconque.", "empreinte-qui-ne-devrait-pas-exister")))
    verifier("2bis-d empreinte non vide sans brouillon existant -> refus (409)", False)
except HTTPException as e:
    verifier("2bis-d empreinte non vide sans brouillon existant -> refus (409)", e.status_code == 409, str(e.status_code))

# e. Texte vide -> refus, AVANT toute ecriture.
b2f, empreinte2f = scenario_de_base()
try:
    executer(R.relais_enregistrer_brouillon("msg-1", requete_enregistrer("   ", empreinte2f)))
    verifier("2bis-e texte vide -> refus (400)", False)
except HTTPException as e:
    verifier("2bis-e texte vide -> refus (400)", e.status_code == 400, str(e.status_code))
verifier("2bis-e' aucune ecriture n'a eu lieu", len(b2f[S.P3AI_BROUILLONS].ecritures) == 0)

# f. LE MEDIA N'EST JAMAIS TOUCHE : un brouillon deja joint d'un fichier le
#    reste strictement apres une correction de TEXTE depuis ce relais.
b2g, _ = scenario_de_base()
brouillon_avec_media = {
    "inbound_id": "msg-1", "reponse_proposee": "Texte initial.",
    "medias": [{"filename": "devis.pdf"}], "media": {"filename": "devis.pdf"},
}
empreinte_media = S.v625_empreinte("Texte initial.", S.v625_medias(brouillon_avec_media))
b2g[S.P3AI_BROUILLONS] = CollectionEcrivable([brouillon_avec_media])
rep_media = executer(R.relais_enregistrer_brouillon(
    "msg-1", requete_enregistrer("Texte corrige, le fichier doit rester joint.", empreinte_media)))
verifier(
    "2bis-f le media reste EXACTEMENT celui d'avant apres une correction de texte",
    rep_media["brouillon"]["medias"] == [{"filename": "devis.pdf"}]
    and rep_media["brouillon"]["media"] == {"filename": "devis.pdf"},
    str(rep_media["brouillon"]),
)

# g. La garde HMAC s'applique AUSSI a l'enregistrement.
b2h, empreinte2h = scenario_de_base()
try:
    executer(R.relais_enregistrer_brouillon(
        "msg-1", requete_enregistrer("Texte quelconque.", empreinte2h, secret="mauvais-secret")))
    verifier("2bis-g mauvais secret -> 403, rien ecrit", False)
except HTTPException as e:
    verifier("2bis-g mauvais secret -> 403, rien ecrit", e.status_code == 403, str(e.status_code))
verifier("2bis-g' aucune ecriture n'a eu lieu (refuse avant la base)",
         len(b2h[S.P3AI_BROUILLONS].ecritures) == 0)

print("\n   -> Chaque refus ci-dessus laisse le brouillon EXISTANT intact :",
      "jamais un echec qui efface silencieusement un travail deja enregistre.")

# ============================================================================
print("\n3. REFUS — mêmes regles que l'envoi reel du coach, aucune ecriture")

b3, empreinte3 = scenario_de_base()
b3[S.P3AI_BROUILLONS] = CollectionBouchon([])
rep3a = executer(R.relais_apercu_reponse("msg-1", requete_apercu(empreinte3)))
verifier("3a aucun brouillon -> pret:false, raison explicite",
         rep3a["pret"] is False and "brouillon" in rep3a["raison"].lower())

b3b, _ = scenario_de_base()
rep3b = executer(R.relais_apercu_reponse("msg-1", requete_apercu("empreinte-qui-ne-correspond-pas")))
verifier("3b empreinte perimee -> refus, texte jamais rendu",
         rep3b["pret"] is False and rep3b["texte"] is None)

b3c, _ = scenario_de_base()
brouillon_c, empreinte_c = brouillon_valide(reponse="Le [À COMPLÉTER : créneau] vous convient ?")
b3c[S.P3AI_BROUILLONS] = CollectionBouchon([brouillon_c])
rep3c = executer(R.relais_apercu_reponse("msg-1", requete_apercu(empreinte_c)))
verifier("3c place-holder non complete -> refus", rep3c["pret"] is False)

b3d, empreinte3d = scenario_de_base()
b3d["subscribers"] = CollectionBouchon([{"channel": "email", "value": "partenaire@exemple.test",
                                         "status": "opted_out"}])
rep3d = executer(R.relais_apercu_reponse("msg-1", requete_apercu(empreinte3d)))
verifier("3d destinataire ayant dit STOP -> refus", rep3d["pret"] is False, str(rep3d))

b3e, empreinte3e = scenario_de_base()
b3e[S.P3N_COLLECTION] = CollectionBouchon([
    {"action_id": "act-1", "occurred_at": INSTANT_NOTE_RECENTE, "created_at": INSTANT_NOTE_RECENTE,
     "texte": "Le partenaire a rappele : change d'avis sur le prix."},
])
rep3e = executer(R.relais_apercu_reponse("msg-1", requete_apercu(empreinte3e)))
verifier("3e contexte perime (note posterieure au brouillon) -> refus",
         rep3e["pret"] is False and "contexte" in rep3e["raison"].lower(), str(rep3e))

b3f, empreinte3f = scenario_de_base()
cle_envoi = S.p3ai4_cle_envoi("msg-1", empreinte3f)
b3f[S.P3AI4_COLLECTION] = CollectionBouchon([{"id": cle_envoi, "send_status": "envoye"}])
rep3f = executer(R.relais_apercu_reponse("msg-1", requete_apercu(empreinte3f)))
verifier("3f deja envoye -> deja_envoye:true, jamais une erreur HTTP",
         rep3f["deja_envoye"] is True and rep3f["pret"] is False)

print("\n   -> AUCUN de ces six refus n'a leve d'exception : chacun est une",
      "   reponse normale, pas une panne.")

# ============================================================================
print("\n4. PORTEE PAR COACH — jamais une fuite d'existence")

b4, empreinte4 = scenario_de_base()
b4[S.P3U2_COLLECTION] = CollectionBouchon([message_valide(coach=AUTRE_COACH)])
try:
    executer(R.relais_apercu_reponse("msg-1", requete_apercu(empreinte4)))
    verifier("4a message d'un AUTRE coach -> 404", False)
except HTTPException as e:
    verifier("4a message d'un AUTRE coach -> 404", e.status_code == 404, str(e.status_code))

try:
    executer(R.relais_lire_brouillon("msg-inexistant", requete_brouillon("msg-inexistant")))
    verifier("4b identifiant inexistant -> 404", False)
except HTTPException as e:
    verifier("4b identifiant inexistant -> 404", e.status_code == 404, str(e.status_code))

# ============================================================================
print("\n5. LA GARDE HMAC S'APPLIQUE AUX TROIS NOUVELLES ROUTES")

b5, empreinte5 = scenario_de_base()
try:
    executer(R.relais_apercu_reponse("msg-1", requete_apercu(empreinte5, sans_signature=True)))
    verifier("5a signature absente -> 403, aucune lecture en base", False)
except HTTPException as e:
    # La garde verifie l'horodatage AVANT la signature (401 = preuve trop
    # vieille ou absente de date) ; une signature manquante, elle, avec un
    # horodatage par ailleurs present, echoue a l'etape suivante -> 403.
    # Meme comportement, meme ordre, que les trois routes de lecture.
    verifier("5a signature absente -> 403, aucune lecture en base", e.status_code == 403, str(e.status_code))

b5b, empreinte5b = scenario_de_base()
try:
    executer(R.relais_apercu_reponse("msg-1", requete_signee(
        "POST", "/api/afroboosteur-relais/conversations/msg-1/apercu-reponse",
        corps={"draft_hash": empreinte5b}, decalage=-900)))
    verifier("5b' horodatage hors fenetre (-900s) -> 401", False)
except HTTPException as e:
    verifier("5b' horodatage hors fenetre (-900s) -> 401", e.status_code == 401, str(e.status_code))

try:
    executer(R.relais_apercu_reponse("msg-1", requete_apercu(empreinte5, secret="mauvais-secret")))
    verifier("5c mauvais secret -> 403", False)
except HTTPException as e:
    verifier("5c mauvais secret -> 403", e.status_code == 403, str(e.status_code))

# 5d. REVUE DE SECURITE (P6A) — LE CORPS EST DESORMAIS LIE A LA SIGNATURE.
# Une signature valide pour UN corps JSON ne doit JAMAIS rester valide pour
# un AUTRE corps sur le meme chemin/horodatage — c'est exactement le defaut
# ferme par `_empreinte_corps()`. Construit a la main (pas via `requete_signee`,
# qui signerait automatiquement le bon corps) pour simuler une substitution.
b5d, empreinte5d = scenario_de_base()
chemin_apercu = "/api/afroboosteur-relais/conversations/msg-1/apercu-reponse"
horodatage5d = str(int(time.time()))
corps_signe = {"draft_hash": empreinte5d}
corps_substitue = {"draft_hash": "nimporte-quoi-d-autre"}
signature_du_premier_corps = signer(
    SECRET, "POST", chemin_apercu, "", horodatage5d,
    __import__("json").dumps(corps_signe).encode("utf-8"))
requete_substituee = RequeteFictive(
    methode="POST", chemin=chemin_apercu, requete="",
    headers={"X-Afroboosteur-Timestamp": horodatage5d,
             "X-Afroboosteur-Signature": signature_du_premier_corps},
    corps=corps_substitue)
try:
    executer(R.relais_apercu_reponse("msg-1", requete_substituee))
    verifier("5d une signature d'UN corps est refusee pour un AUTRE corps (substitution fermee)", False)
except HTTPException as e:
    verifier("5d une signature d'UN corps est refusee pour un AUTRE corps (substitution fermee)",
             e.status_code == 403, str(e.status_code))

# ============================================================================
print("\n6. AUCUNE ECRITURE POSSIBLE — par construction du bouchon, pas par promesse")

b6, empreinte6 = scenario_de_base()
verifier("6a le bouchon n'offre meme pas insert_one",
         not hasattr(b6[S.P3AI4_COLLECTION], "insert_one"))
verifier("6b le bouchon n'offre meme pas update_one",
         not hasattr(b6[S.P3AI4_COLLECTION], "update_one"))
# Le succes du scenario 1, execute SUR CE MEME bouchon minimal, est la preuve
# positive : la route a bien termine son travail sans jamais avoir besoin
# d'une methode d'ecriture.
rep6 = executer(R.relais_apercu_reponse("msg-1", requete_apercu(empreinte6)))
verifier("6c la route reussit quand meme (aucune ecriture n'etait necessaire)",
         rep6["pret"] is True)

# ============================================================================
print("\n7. ENVOI REEL : AUCUNE ROUTE NE LE DECLENCHE (verifie par lecture du code)")

source = open(os.path.join(RACINE, "api/routes/afroboosteur_relais.py"), encoding="utf-8").read()
# Pas une recherche du MOT "fournisseur" (la documentation en parle en
# toutes lettres, a dessein) : une recherche de l'ACTE — importer resend,
# appeler Resend.Emails, ou importer la moindre fonction d'envoi reel.
verifier("7a aucun import ni appel a un fournisseur d'envoi reel (resend, Emails.send)",
         not __import__("re").search(r'import\s+resend|Emails\.send|resend_central', source))
# Redondant AVEC AUCUNE PERTE par rapport a la section 9 de
# test_p4_relais_afroboosteur.py : ce test-ci confirme la MEME garantie
# depuis ce banc-ci, pour qu'un lecteur de CE fichier n'ait pas a en ouvrir
# un second pour la verifier. REEVALUE : une ecriture legitime existe desormais
# (le texte d'un brouillon) ; ce qui reste absolu, c'est qu'elle ne touche
# JAMAIS prospect_reply_sends (P3AI4_COLLECTION) — la reservation d'un envoi.
verifier(
    "7b toute ecriture du fichier porte EXCLUSIVEMENT sur P3AI_BROUILLONS, "
    "jamais sur P3AI4_COLLECTION (reservation/envoi)",
    (lambda lignes: len(lignes) > 0 and all("P3AI_BROUILLONS" in l for l in lignes))(
        [l for l in source.splitlines()
         if __import__("re").search(r'\.(insert_one|insert_many|update_one|update_many)\(', l)]
    )
)
verifier("7c le fichier documente explicitement que l'envoi n'est pas cable",
         "N'EST PAS CÂBLÉ" in source or "deliberement PAS" in source)

os.environ.pop("AFROBOOSTEUR_RELAY_SECRET", None)
os.environ.pop("AFROBOOSTEUR_RELAY_COACH_ID", None)

# ============================================================================
total = len(RESULTATS)
reussites = sum(1 for _, ok, _ in RESULTATS if ok)
echecs = total - reussites
print("\n=== %d/%d OK (%d echec%s) ===" % (reussites, total, echecs, "" if echecs == 1 else "s"))
if echecs:
    sys.exit(1)
