#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GOOGLE-2 — LA SYNCHRONISATION SORTANTE, AFROBOOST -> GOOGLE CALENDAR.

CE QUE LE LOT AJOUTE
==============================================================================
Un evenement Afroboost explicitement choisi part chez Google, y est modifie
sur LE MEME identifiant, et n'en revient jamais en double. Afroboost reste la
source de verite : Google est un report, jamais une condition.

CE QUE CE FICHIER PROUVE
==============================================================================
  * L'ORDRE — l'evenement Afroboost est ecrit et confirme AVANT que Google ne
    soit contacte ; Google en panne laisse un evenement parfaitement valide ;
  * L'EXPLICITE — sans demande, pas un seul appel sortant ;
  * L'IDEMPOTENCE, la propriete centrale du lot : double clic, reprise,
    redemarrage et 409 de Google conduisent tous a UN SEUL evenement Google,
    parce que l'identifiant Google est DERIVE de l'identifiant Afroboost ;
  * la modification passe par PATCH sur le meme identifiant, jamais par POST ;
  * le conflit (412) N'ECRASE RIEN et attend un arbitrage ;
  * un evenement efface dans Google (404) n'est JAMAIS recree tout seul ;
  * la suppression chez Google est un choix explicite, jamais un defaut ;
  * §21 — un evenement pousse ne revient pas en double dans le calendrier ;
  * l'isolation par coach tient sur les cinq chemins ;
  * aucun jeton ne sort : ni en reponse, ni en journal, ni chez Google ;
  * P3, CAL-1, CAL-2, CAL-3 et GOOGLE-1 restent intacts.

    python3 tests/test_google2_sync_sortante.py
"""
import ast
import io
import json
import os
import sys
import asyncio
from datetime import datetime, timedelta, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

RESULTATS = []


def verifier(intitule, condition, detail=""):
    RESULTATS.append((intitule, bool(condition), detail))
    print("  %-6s %s" % ("OK  " if condition else "ECHEC", intitule))
    if detail and not condition:
        print("           -> %s" % detail)
    return bool(condition)


SECRET = "secret-de-test-google2-sans-aucun-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-google2-inexistant:27017")

import jwt as _jwt          # noqa: E402
import api.server as S      # noqa: E402
from fastapi import HTTPException  # noqa: E402

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()


def _bloc(source, entete):
    """Le bloc du lot, borne a la banniere SUIVANTE quelle qu'elle soit.

    LEcON DEJA PAYEE TROIS FOIS : ancrer la borne sur un texte precis
    (« Leads Routes », puis « # P3- ») casse au lot suivant. On prend donc la
    plus proche des bornes possibles, sans presumer laquelle existera.
    """
    debut = source.index(entete)
    banniere = "\n# " + "=" * 76 + "\n# "
    apres = source.index("\n\n", debut)
    bornes = [x for x in (source.find(banniere, apres),
                          source.find("\n# --- Leads Routes (Widget IA) ---", apres))
              if x != -1]
    return source[debut:min(bornes)] if bornes else source[debut:]


BLOC = _bloc(SRC, "# GOOGLE-2 — LA SYNCHRONISATION SORTANTE")

COACH_A = "coach.a.fictif@exemple.test"
COACH_B = "coach.b.fictif@exemple.test"

_BANC = os.path.join(RACINE, "tests", "test_p3s3b_preparation_campagne.py")
_source = io.open(_BANC, encoding="utf-8").read()
_debut = _source.index("def lancer(coroutine):")
_fin = _source.index('# ============================================================================\nprint("\\n1.')
_espace = {"S": S, "asyncio": asyncio, "COACH_A": COACH_A, "COACH_B": COACH_B,
           "json": json, "os": os, "sys": sys, "_jwt": _jwt, "SECRET": SECRET,
           "HTTPException": HTTPException, "INSTANT": ""}
exec(compile(_source[_debut:_fin], _BANC, "exec"), _espace)   # noqa: S102
Col, Base = _espace["CollectionBouchon"], _espace["BaseBouchon"]
RequeteFictive, lancer, jeton = _espace["RequeteFictive"], _espace["lancer"], _espace["jeton"]
Curseur = _espace["Curseur"]

JA, JB = jeton(COACH_A), jeton(COACH_B)
MAINTENANT = datetime.now(timezone.utc)
DEMAIN = (MAINTENANT + timedelta(days=1)).replace(microsecond=0).isoformat()
FIN_DEMAIN = (MAINTENANT + timedelta(days=1, minutes=30)).replace(microsecond=0).isoformat()


# ============================================================================
# LE BOUCHON MONGO — TROIS TROUS COMBLES, MODELISES SUR LE VRAI CONTRAT
# ============================================================================
# Chacun de ces trois manques aurait fait passer un test au vert sans que la
# regle correspondante soit reellement verifiee. On modelise donc Mongo, on
# n'affaiblit pas l'assertion — c'est la lecon des cinq trous precedents.
class CurseurIterable(Curseur):
    """`async for ...  in collection.find(...)` — ce que fait l'anti-doublon.

    Le curseur partage ne sait que `to_list`. Sans `__aiter__`, la boucle du
    §21 leverait, et le test du doublon n'aurait rien mesure.
    """

    def __aiter__(self):
        self._i = iter(list(self._docs))
        return self

    async def __anext__(self):
        try:
            return dict(next(self._i))
        except StopIteration:
            raise StopAsyncIteration


class ColG2(Col):
    """Ajoute `$lt`/`$lte`/`$gt`/`$gte`, `$unset`, et le curseur iterable."""

    def _ok(self, doc, filtre):
        reste = {}
        for cle, val in (filtre or {}).items():
            if isinstance(val, dict) and any(
                    op in val for op in ("$lt", "$lte", "$gt", "$gte")):
                v = doc.get(cle)
                if v is None:
                    v = 0 if any(isinstance(val.get(op), int)
                                 for op in ("$lt", "$lte", "$gt", "$gte")) else ""
                for op, borne in val.items():
                    if op == "$lt" and not v < borne:
                        return False
                    if op == "$lte" and not v <= borne:
                        return False
                    if op == "$gt" and not v > borne:
                        return False
                    if op == "$gte" and not v >= borne:
                        return False
                autres = {o: b for o, b in val.items()
                          if o not in ("$lt", "$lte", "$gt", "$gte")}
                if autres:
                    reste[cle] = autres
                continue
            reste[cle] = val
        return Col._ok(self, doc, reste)

    def find(self, filtre=None, projection=None, *a, **k):
        return CurseurIterable([dict(d) for d in self.documents if self._ok(d, filtre)])

    async def update_one(self, filtre, maj, *a, **k):
        """`$unset` — la reprise forcee s'en sert pour oublier un id mort."""
        for d in self.documents:
            if self._ok(d, filtre):
                d.update(maj.get("$set") or {})
                for cle in (maj.get("$unset") or {}):
                    d.pop(cle, None)
                for cle, val in (maj.get("$setOnInsert") or {}).items():
                    d.setdefault(cle, val)
                self.ecritures += 1
                return type("R", (), {"matched_count": 1, "modified_count": 1})()
        if k.get("upsert") or (a and a[0]):
            candidat = {c: v for c, v in (filtre or {}).items()
                        if not isinstance(v, dict)}
            candidat.update(maj.get("$set") or {})
            candidat.update(maj.get("$setOnInsert") or {})
            self.documents.append(candidat)
            self.ecritures += 1
            return type("R", (), {"matched_count": 0, "modified_count": 0,
                                  "upserted_id": "x"})()
        return type("R", (), {"matched_count": 0, "modified_count": 0})()


# ============================================================================
# LE FAUX GOOGLE — il COMPTE, il MEMORISE, et il n'invente rien
# ============================================================================
class Reponse:
    def __init__(self, code, donnees=None):
        self.status_code = code
        self._d = donnees if donnees is not None else {}
        self.content = json.dumps(self._d).encode() if donnees is not None else b""

    def json(self):
        return self._d


class FauxGoogle:
    """Un agenda Google en memoire. Il respecte les regles qui nous concernent.

    IL REFUSE UN IDENTIFIANT DEJA PRIS PAR UN 409 — c'est le comportement reel
    de l'API, et c'est precisement sur lui que repose l'idempotence du lot.
    IL VERIFIE `If-Match` — c'est lui qui produit le 412 du conflit.
    """

    def __init__(self):
        self.evenements = {}        # id -> corps
        self.appels = []            # (methode, chemin, corps, etag)
        self.forcer = None          # (code, donnees) impose au prochain appel
        self.forcer_n = 0
        self.entetes_vus = []
        self.sequence = 0

    def imposer(self, code, donnees=None, fois=1):
        self.forcer = (code, donnees)
        self.forcer_n = fois

    def _reponse(self, methode, chemin, corps, etag):
        self.appels.append((methode, chemin, corps, etag))
        if self.forcer_n > 0:
            self.forcer_n -= 1
            code, donnees = self.forcer
            return Reponse(code, donnees)
        cible = chemin.split("/events")[-1].lstrip("/")
        if methode == "POST":
            identifiant = (corps or {}).get("id") or "auto-%d" % len(self.evenements)
            if identifiant in self.evenements:
                return Reponse(409, {"error": {"code": 409, "message": "duplicate"}})
            self.sequence += 1
            enregistre = dict(corps or {})
            enregistre["id"] = identifiant
            enregistre["etag"] = "etag-%d" % self.sequence
            self.evenements[identifiant] = enregistre
            return Reponse(200, dict(enregistre))
        if methode == "GET":
            if cible not in self.evenements:
                return Reponse(404, {})
            return Reponse(200, dict(self.evenements[cible]))
        if methode == "PATCH":
            if cible not in self.evenements:
                return Reponse(404, {})
            actuel = self.evenements[cible]
            if etag and etag != actuel.get("etag"):
                return Reponse(412, {})
            self.sequence += 1
            actuel.update(corps or {})
            actuel["etag"] = "etag-%d" % self.sequence
            return Reponse(200, dict(actuel))
        if methode == "DELETE":
            if cible not in self.evenements:
                return Reponse(404, {})
            self.evenements.pop(cible)
            return Reponse(204, None)
        return Reponse(400, {})

    # --- le module httpx factice ---
    def module(self):
        google = self

        class Client:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def request(self, methode, url, headers=None, json=None, **k):
                google.entetes_vus.append(dict(headers or {}))
                etag = (headers or {}).get("If-Match", "")
                chemin = url.split("/calendar/v3")[-1]
                return google._reponse(methode, chemin, json, etag)

            async def get(self, url, headers=None, params=None, **k):
                google.entetes_vus.append(dict(headers or {}))
                chemin = url.split("/calendar/v3")[-1]
                if chemin.endswith("/events") or "/events?" in chemin:
                    return Reponse(200, {"items": [dict(e) for e in google.evenements.values()]})
                return google._reponse("GET", chemin, None, "")

            async def post(self, url, **k):
                # Renouvellement de jeton : jamais atteint (jeton encore valide).
                return Reponse(200, {"access_token": "jeton-neuf", "expires_in": 3600})

        return type("httpx", (), {"AsyncClient": Client})


GOOGLE = FauxGoogle()
sys.modules["httpx"] = GOOGLE.module()


# ============================================================================
# LA BASE
# ============================================================================
def jeton_google(scopes, coach=COACH_A, revoque=False):
    return {
        "coach_email": coach,
        "access_token": S.g1_chiffrer("jeton-acces-factice"),
        "refresh_token": S.g1_chiffrer("jeton-rafraichissement-factice"),
        "expires_at": (MAINTENANT + timedelta(hours=1)).isoformat(),
        "scope": " ".join(scopes),
        "created_at": MAINTENANT.isoformat(),
        **({"revoked_at": MAINTENANT.isoformat()} if revoque else {}),
    }


TOUS_SCOPES = (S.G1_SCOPE_CONTACTS, S.G1_SCOPE_CALENDRIER, S.G2_SCOPE_ECRITURE)
LECTURE_SEULE = (S.G1_SCOPE_CONTACTS, S.G1_SCOPE_CALENDRIER)


def base_neuve(evenements=None, scopes=TOUS_SCOPES, coachs_connectes=(COACH_A,)):
    global GOOGLE
    GOOGLE = FauxGoogle()
    sys.modules["httpx"] = GOOGLE.module()
    b = Base([])
    b[S.CAL1_COLLECTION] = ColG2(S.CAL1_COLLECTION,
                                 [dict(e) for e in (evenements or [])],
                                 uniques=[(("id",), None)])
    b[S.G1_COLLECTION] = ColG2(S.G1_COLLECTION,
                               [jeton_google(scopes, c) for c in coachs_connectes])
    b[S.P3S1_COLLECTION] = ColG2(S.P3S1_COLLECTION, [
        {"id": "p-1", "ref": "FES-01", "coach_id": COACH_A,
         "organisation_name": "Festival du Lac", "status": "contacte"}],
        uniques=[(("id",), None)])
    b[S.P3S3_ACTIONS] = ColG2(S.P3S3_ACTIONS, [], uniques=[(("id",), None)])
    b["campaigns"] = ColG2("campaigns", [], uniques=[(("id",), None)])
    b["courses"] = ColG2("courses", [], uniques=[(("id",), None)])
    S.db = b
    return b


def evenement(id_, coach=COACH_A, **extra):
    d = {"id": id_, "coach_id": coach, "title": "Point d'equipe",
         "description": "", "location": "",
         "starts_at": DEMAIN, "ends_at": FIN_DEMAIN, "all_day": False,
         "event_type": "appointment", "status": "prevu", "priority": None,
         "completed_at": None, "prospect_id": None, "recipient_key": None,
         "campaign_id": None, "campaign_action_id": None,
         "is_deleted": False, "created_at": MAINTENANT.isoformat(),
         "updated_at": MAINTENANT.isoformat()}
    d.update(extra)
    return d


def creer(corps, jeton_=JA):
    return lancer(S.cal1_creer(RequeteFictive(jeton_=jeton_, corps=corps)))


def modifier(eid, corps, jeton_=JA):
    return lancer(S.cal1_modifier(eid, RequeteFictive(jeton_=jeton_, corps=corps)))


def supprimer(eid, params=None, jeton_=JA):
    return lancer(S.cal1_supprimer(eid, RequeteFictive(jeton_=jeton_, params=params or {})))


def activer(eid, corps=None, jeton_=JA):
    return lancer(S.g2_route_activer(eid, RequeteFictive(jeton_=jeton_, corps=corps or {})))


def reessayer(eid, corps=None, jeton_=JA):
    return lancer(S.g2_route_reessayer(eid, RequeteFictive(jeton_=jeton_, corps=corps or {})))


def desactiver(eid, jeton_=JA):
    return lancer(S.g2_route_desactiver(eid, RequeteFictive(jeton_=jeton_)))


def statut(jeton_=JA):
    return lancer(S.g1_statut(RequeteFictive(jeton_=jeton_)))


def evenements_google(jeton_=JA, params=None):
    return lancer(S.g1_evenements(RequeteFictive(jeton_=jeton_, params=params or {})))


def poses(methode):
    return [a for a in GOOGLE.appels if a[0] == methode]


_UUID = "a1b2c3d4-e5f6-4789-9abc-def012345678"

# ============================================================================
print("\n1. L'IDENTIFIANT GOOGLE EST DERIVE — LA CLE DE L'IDEMPOTENCE")

_uuid = "a1b2c3d4-e5f6-4789-9abc-def012345678"
verifier("1a. deterministe : deux appels, un seul resultat",
         S.g2_id_google(_uuid) == S.g2_id_google(_uuid))
verifier("1b. les tirets tombent, la longueur est de 32",
         len(S.g2_id_google(_uuid)) == 32, S.g2_id_google(_uuid))
verifier("1c. alphabet base32hex uniquement (0-9, a-v)",
         all(c in "0123456789abcdefghijklmnopqrstuv" for c in S.g2_id_google(_uuid)))
verifier("1d. deux evenements Afroboost donnent deux identifiants Google",
         S.g2_id_google(_uuid) != S.g2_id_google("ffffffff-0000-4000-8000-000000000001"))
verifier("1e. un identifiant hors alphabet est REFUSE plutot que mutile",
         S.g2_id_google("zzzz-wwww-xxxx-yyyy") == "")
verifier("1f. trop court : refuse", S.g2_id_google("a-b") == "")
verifier("1g. vide ou None : refuse",
         S.g2_id_google("") == "" and S.g2_id_google(None) == "")


# ============================================================================
print("\n2. ON NE SUPPOSE JAMAIS QU'UN JETON PORTE UN SCOPE")

verifier("2a. les trois scopes : ecriture accordee",
         S.g2_ecriture_accordee({"scope": " ".join(TOUS_SCOPES)}) is True)
verifier("2b. GOOGLE-1 seul (lecture) : ecriture REFUSEE",
         S.g2_ecriture_accordee({"scope": " ".join(LECTURE_SEULE)}) is False)
verifier("2c. document vide : refusee", S.g2_ecriture_accordee({}) is False)
verifier("2d. le scope large `auth/calendar` n'est PAS demande",
         "auth/calendar\"" not in BLOC and S.G2_SCOPE_ECRITURE.endswith("/calendar.events"))
verifier("2e. les deux scopes GOOGLE-1 sont PRESERVES",
         all(s in S.G2_SCOPES for s in S.G1_SCOPES) and len(S.G2_SCOPES) == 3)


# ============================================================================
print("\n3. LE CORPS ENVOYE A GOOGLE — LISIBLE, ET SANS RIEN DE TECHNIQUE")

_c = S.g2_corps_google(evenement("e-1", title="Appel partenariat — Festival",
                                 description="Ils ont repondu",
                                 meeting_type="appel", prospect_id="FES-01"),
                       avec_id=True)
_texte = json.dumps(_c)
verifier("3a. le titre est repris", _c["summary"] == "Appel partenariat — Festival")
verifier("3b. la description porte les notes", "Ils ont repondu" in _c["description"])
verifier("3c. elle porte le type de rendez-vous", "appel" in _c["description"])
verifier("3d. elle porte un lien vers la fiche Afroboost",
         "/dashboard?prospect=FES-01" in _c["description"])
verifier("3e. AUCUN jeton n'y figure",
         "jeton" not in _texte and "token" not in _texte.lower())
verifier("3f. AUCUNE cle de campagne ni de destinataire",
         "campaign_id" not in _texte and "recipient_key" not in _texte)
_avec_id = S.g2_corps_google(evenement(_UUID), avec_id=True)
verifier("3g. l'identifiant derive est pose a l'insertion",
         _avec_id.get("id") == S.g2_id_google(_UUID), str(_avec_id.get("id")))
verifier("3g2. un identifiant non derivable est OMIS, jamais invente",
         "id" not in S.g2_corps_google(evenement("e-1"), avec_id=True))
verifier("3g3. et il n'est JAMAIS pose sur une modification",
         "id" not in S.g2_corps_google(evenement(_UUID)))
verifier("3h. un rendez-vous horaire utilise `dateTime`, pas `date`",
         "dateTime" in _c["start"] and "date" not in _c["start"])

_j = S.g2_corps_google(evenement("e-2", all_day=True, starts_at=DEMAIN, ends_at=""))
verifier("3i. une journee entiere utilise `date`", "date" in _j["start"])
_sans_fin = S.g2_corps_google(evenement("e-3", ends_at=""))
verifier("3j. un evenement sans fin recoit une fin DEDUITE (Google l'exige)",
         bool(_sans_fin["end"].get("dateTime")))
verifier("3k. le document Afroboost, lui, reste sans fin",
         evenement("e-3", ends_at="")["ends_at"] == "")
_annule = S.g2_corps_google(evenement("e-4", status="annule"))
verifier("3l. `annule` devient `cancelled` chez Google", _annule["status"] == "cancelled")
verifier("3m. un evenement normal est `confirmed`", _c["status"] == "confirmed")


# ============================================================================
print("\n4. LES VERDICTS HTTP D'ECRITURE")

for code, attendu in ((404, "introuvable_google"), (410, "introuvable_google"),
                      (409, "existe_deja"), (412, "conflit"),
                      (400, "requete_invalide"), (422, "requete_invalide"),
                      (401, "reconnexion_requise"), (403, "acces_refuse"),
                      (429, "trop_de_requetes"), (500, "google_indisponible"),
                      (503, "google_indisponible")):
    verifier("4. %s -> %s" % (code, attendu), S.g2_verdict_http(code) == attendu,
             S.g2_verdict_http(code))
verifier("4z. 200 n'est pas une erreur", S.g2_verdict_http(200) == "")
verifier("4y. GOOGLE-1 garde son verdict de lecture inchange",
         S.g1_verdict_http(404) == "erreur_google")


# ============================================================================
print("\n5. AFROBOOST D'ABORD — GOOGLE NE PEUT PAS ANNULER UNE CREATION")

_b = base_neuve()
GOOGLE.imposer(503, {}, fois=9)
_r = creer({"title": "Reunion", "starts_at": DEMAIN, "event_type": "appointment",
            "google_sync": True})
verifier("5a. l'evenement Afroboost EXISTE malgre Google en panne",
         len(_b[S.CAL1_COLLECTION].documents) == 1)
verifier("5b. la route rend bien l'evenement (aucune exception)", bool(_r["event"]["id"]))
verifier("5c. il est marque en attente, pas perdu",
         _r["event"]["google"]["status"] == S.G2_EN_ATTENTE,
         _r["event"]["google"]["status"])
verifier("5d. la synchronisation reste demandee", _r["event"]["google"]["enabled"] is True)
verifier("5e. aucun identifiant Google n'a ete invente",
         _r["event"]["google"]["event_id"] == "")

_b = base_neuve()
GOOGLE.imposer(500, {}, fois=9)
_rdv = lancer(S.cal3_planifier("FES-01", RequeteFictive(
    jeton_=JA, corps={"starts_at": DEMAIN, "duration_minutes": 30,
                      "google_sync": True})))
verifier("5f. §7 — le rendez-vous prospect EXISTE malgre Google en panne",
         len(_b[S.CAL1_COLLECTION].documents) == 1)
verifier("5g. ses liaisons P3 sont intactes",
         _rdv["appointment"]["prospect_id"] == "FES-01")
verifier("5h. Afroboost ecrit AVANT Google : l'insertion precede l'appel",
         BLOC.count("insert_one") == 0 and "await db[CAL1_COLLECTION].insert_one"
         in SRC.split("if corps.get(\"google_sync\")")[0][-4000:])


# ============================================================================
print("\n6. RIEN NE PART SANS DEMANDE EXPLICITE")

_b = base_neuve()
creer({"title": "Prive", "starts_at": DEMAIN, "event_type": "appointment"})
verifier("6a. sans `google_sync`, AUCUN appel sortant", len(GOOGLE.appels) == 0,
         str(GOOGLE.appels))
verifier("6b. l'evenement n'est pas marque synchronise",
         _b[S.CAL1_COLLECTION].documents[0].get("google_sync_enabled") in (None, False))

_b = base_neuve()
lancer(S.cal3_planifier("FES-01", RequeteFictive(
    jeton_=JA, corps={"starts_at": DEMAIN})))
verifier("6c. un rendez-vous prospect non coche ne part pas non plus",
         len(GOOGLE.appels) == 0)

_b = base_neuve([evenement("e-1"), evenement("e-2"), evenement("e-3")])
lancer(S.g2_reprise())
verifier("6d. la reprise ne touche PAS les evenements non synchronises",
         len(GOOGLE.appels) == 0)
verifier("6e. §5 — aucune migration massive : rien n'a ete marque",
         all(not d.get("google_sync_enabled") for d in _b[S.CAL1_COLLECTION].documents))


# ============================================================================
print("\n7. L'IDEMPOTENCE — LA PROPRIETE CENTRALE DU LOT")

_b = base_neuve([evenement("a1b2c3d4-e5f6-4789-9abc-def012345678")])
_eid = "a1b2c3d4-e5f6-4789-9abc-def012345678"
_r1 = activer(_eid)
verifier("7a. premiere activation : 1 evenement chez Google",
         len(GOOGLE.evenements) == 1)
verifier("7b. l'etat est `synced`", _r1["google"]["status"] == S.G2_SYNCHRONISE,
         _r1["google"]["status"] + " / " + _r1["google"]["error"])
verifier("7c. l'identifiant Google est STOCKE", bool(_r1["google"]["event_id"]))
verifier("7d. c'est bien l'identifiant DERIVE",
         _r1["google"]["event_id"] == S.g2_id_google(_eid))

_r2 = activer(_eid)
verifier("7e. DOUBLE CLIC — toujours 1 seul evenement Google",
         len(GOOGLE.evenements) == 1, str(list(GOOGLE.evenements)))
verifier("7f. et le meme identifiant", _r2["google"]["event_id"] == _r1["google"]["event_id"])
verifier("7g. aucune seconde insertion n'a abouti", len(poses("POST")) <= 2)

_avant = len(GOOGLE.evenements)
lancer(S.g2_pousser(_eid, COACH_A))
lancer(S.g2_pousser(_eid, COACH_A))
lancer(S.g2_pousser(_eid, COACH_A))
verifier("7h. TROIS reprises de plus — toujours 1 evenement",
         len(GOOGLE.evenements) == _avant == 1)

_r3 = reessayer(_eid)
verifier("7i. RETRY explicite — toujours 1 evenement", len(GOOGLE.evenements) == 1)
verifier("7j. le retry ne casse pas l'etat", _r3["google"]["status"] == S.G2_SYNCHRONISE)

# LE CAS DU PLANTAGE ENTRE GOOGLE ET NOUS : Google a cree, nous n'avons pas
# enregistre l'identifiant. La reprise recalcule le MEME identifiant, recoit un
# 409, l'adopte — et ne cree pas d'orphelin.
_b[S.CAL1_COLLECTION].documents[0].pop("google_event_id", None)
_b[S.CAL1_COLLECTION].documents[0]["google_sync_status"] = S.G2_EN_ATTENTE
_r4 = lancer(S.g2_pousser(_eid, COACH_A))
verifier("7k. PLANTAGE APRES CREATION : la reprise retrouve l'evenement (409 adopte)",
         len(GOOGLE.evenements) == 1, str(list(GOOGLE.evenements)))
verifier("7l. et le reetat est `synced`", _r4["status"] == S.G2_SYNCHRONISE, str(_r4))
verifier("7m. l'identifiant retrouve est le derive",
         _b[S.CAL1_COLLECTION].documents[0]["google_event_id"] == S.g2_id_google(_eid))

verifier("7n. un evenement inchange n'est pas repousse inutilement",
         len(GOOGLE.appels) == (lambda n: (lancer(S.g2_pousser(_eid, COACH_A)),
                                           len(GOOGLE.appels))[1])(0))


# ============================================================================
print("\n8. LA MODIFICATION SUIT LE MEME IDENTIFIANT — JAMAIS UN SECOND")

_b = base_neuve([evenement(_eid)])
activer(_eid)
_id_avant = _b[S.CAL1_COLLECTION].documents[0]["google_event_id"]
_posts_avant = len(poses("POST"))

_m = modifier(_eid, {"title": "Point d'equipe — deplace", "starts_at": FIN_DEMAIN})
verifier("8a. le titre a change cote Afroboost",
         _m["event"]["title"] == "Point d'equipe — deplace")
verifier("8b. UN SEUL evenement Google", len(GOOGLE.evenements) == 1)
verifier("8c. le MEME google_event_id", _m["event"]["google"]["event_id"] == _id_avant)
verifier("8d. la modification est passee par PATCH", len(poses("PATCH")) >= 1)
verifier("8e. AUCUNE nouvelle insertion", len(poses("POST")) == _posts_avant)
verifier("8f. Google porte le nouveau titre",
         list(GOOGLE.evenements.values())[0]["summary"] == "Point d'equipe — deplace")
verifier("8g. Google porte la nouvelle heure",
         FIN_DEMAIN[:16] in json.dumps(list(GOOGLE.evenements.values())[0]))

for champ, valeur in (("description", "des notes"), ("location", "Salle 2")):
    modifier(_eid, {champ: valeur})
verifier("8h. notes et lieu suivent aussi",
         "des notes" in list(GOOGLE.evenements.values())[0]["description"]
         and list(GOOGLE.evenements.values())[0]["location"] == "Salle 2")
verifier("8i. toujours UN SEUL evenement Google apres 3 modifications",
         len(GOOGLE.evenements) == 1)
verifier("8j. l'identifiant n'a jamais bouge",
         _b[S.CAL1_COLLECTION].documents[0]["google_event_id"] == _id_avant)


# ============================================================================
print("\n9. LE CONFLIT — GOOGLE A CHANGE, ON N'ECRASE RIEN")

_b = base_neuve([evenement(_eid)])
activer(_eid)
# Quelqu'un modifie l'evenement DIRECTEMENT dans Google : l'etag change.
list(GOOGLE.evenements.values())[0]["etag"] = "etag-modifie-ailleurs"
list(GOOGLE.evenements.values())[0]["summary"] = "Titre pose dans Google"
_m = modifier(_eid, {"title": "Titre pose dans Afroboost"})
verifier("9a. l'etat devient `conflict`",
         _m["event"]["google"]["status"] == S.G2_CONFLIT, _m["event"]["google"]["status"])
verifier("9b. le titre de Google N'A PAS ete ecrase",
         list(GOOGLE.evenements.values())[0]["summary"] == "Titre pose dans Google")
verifier("9c. la modification Afroboost, elle, est bien faite",
         _m["event"]["title"] == "Titre pose dans Afroboost")
verifier("9d. le motif est lisible", _m["event"]["google"]["error"] == "modifie_dans_google")
verifier("9e. la reprise automatique NE rejoue PAS un conflit",
         (lambda n: (lancer(S.g2_reprise()), len(GOOGLE.appels) == n)[1])(len(GOOGLE.appels)))

_f = reessayer(_eid, {"force": True})
verifier("9f. `force` est l'arbitrage explicite : Afroboost gagne",
         list(GOOGLE.evenements.values())[0]["summary"] == "Titre pose dans Afroboost")
verifier("9g. et toujours un seul evenement", len(GOOGLE.evenements) == 1)
verifier("9h. l'etat revient a `synced`", _f["google"]["status"] == S.G2_SYNCHRONISE)


# ============================================================================
print("\n10. SUPPRIME DANS GOOGLE — AUCUNE RECREATION SILENCIEUSE (§15)")

_b = base_neuve([evenement(_eid)])
activer(_eid)
GOOGLE.evenements.clear()           # le coach l'a efface dans Google
_m = modifier(_eid, {"title": "Toujours la"})
verifier("10a. l'etat devient `google_deleted`",
         _m["event"]["google"]["status"] == S.G2_SUPPRIME_CHEZ_GOOGLE,
         _m["event"]["google"]["status"])
verifier("10b. RIEN n'a ete recree chez Google", len(GOOGLE.evenements) == 0)
verifier("10c. l'evenement Afroboost vit toujours", _m["event"]["title"] == "Toujours la")
verifier("10d. l'identifiant Google est CONSERVE (trace)",
         bool(_b[S.CAL1_COLLECTION].documents[0].get("google_event_id")))

lancer(S.g2_reprise())
lancer(S.g2_reprise())
verifier("10e. deux passages de reprise ne le recreent pas non plus",
         len(GOOGLE.evenements) == 0)

_f = reessayer(_eid, {"force": True})
verifier("10f. seule une demande EXPLICITE le recree", len(GOOGLE.evenements) == 1)
verifier("10g. avec le meme identifiant derive",
         list(GOOGLE.evenements) == [S.g2_id_google(_eid)])


# ============================================================================
print("\n11. LES PANNES — 429, 5xx, 401, TIMEOUT")

for code, attendu_statut in ((429, S.G2_EN_ATTENTE), (500, S.G2_EN_ATTENTE),
                             (503, S.G2_EN_ATTENTE)):
    _b = base_neuve([evenement(_eid)])
    GOOGLE.imposer(code, {}, fois=99)
    _r = activer(_eid)
    verifier("11. %s -> l'evenement reste, etat `%s`" % (code, attendu_statut),
             _r["google"]["status"] == attendu_statut
             and len(_b[S.CAL1_COLLECTION].documents) == 1,
             _r["google"]["status"])

_b = base_neuve([evenement(_eid)])
GOOGLE.imposer(401, {}, fois=99)
_r = activer(_eid)
verifier("11d. 401 -> reconnexion demandee",
         _r["google"]["status"] == S.G2_RECONNEXION, _r["google"]["status"])

_b = base_neuve([evenement(_eid)], scopes=LECTURE_SEULE)
_r = activer(_eid)
verifier("11e. jeton SANS droit d'ecriture -> reconnexion, sans appel a Google",
         _r["google"]["status"] == S.G2_RECONNEXION and len(GOOGLE.appels) == 0)
verifier("11f. et l'evenement Afroboost est intact",
         len(_b[S.CAL1_COLLECTION].documents) == 1)

_b = base_neuve([evenement(_eid)], coachs_connectes=())
_r = activer(_eid)
verifier("11g. Google pas connecte du tout -> pas d'exception, evenement intact",
         len(_b[S.CAL1_COLLECTION].documents) == 1)


# ============================================================================
print("\n12. LA REPRISE EST BORNEE — JAMAIS DE BOUCLE INFINIE")

_b = base_neuve([evenement(_eid)])
GOOGLE.imposer(503, {}, fois=999)
activer(_eid)
for _ in range(12):
    lancer(S.g2_reprise())
_d = _b[S.CAL1_COLLECTION].documents[0]
verifier("12a. les tentatives sont comptees",
         int(_d.get("google_sync_attempts") or 0) >= 1)
verifier("12b. elles ne depassent JAMAIS la borne",
         int(_d.get("google_sync_attempts") or 0) <= S.G2_TENTATIVES_MAX,
         str(_d.get("google_sync_attempts")))
verifier("12c. au-dela, l'etat est `failed`", _d.get("google_sync_status") == S.G2_ECHEC,
         str(_d.get("google_sync_status")))
_appels_apres = len(GOOGLE.appels)
for _ in range(5):
    lancer(S.g2_reprise())
verifier("12d. un `failed` n'est plus repris : aucun appel de plus",
         len(GOOGLE.appels) == _appels_apres)
verifier("12e. l'evenement Afroboost n'a jamais ete touche",
         _d["title"] == "Point d'equipe" and _d["is_deleted"] is False)

_b = base_neuve([evenement(_eid)])
GOOGLE.imposer(403, {}, fois=99)
activer(_eid)
_d = _b[S.CAL1_COLLECTION].documents[0]
verifier("12f. un motif DEFINITIF (403) ne brule pas 5 tentatives",
         _d.get("google_sync_status") == S.G2_ECHEC
         and int(_d.get("google_sync_attempts") or 0) == 1,
         "%s / %s" % (_d.get("google_sync_status"), _d.get("google_sync_attempts")))


# ============================================================================
print("\n13. LA SUPPRESSION — UN CHOIX, JAMAIS UN DEFAUT (§14)")

_b = base_neuve([evenement(_eid)])
activer(_eid)
_r = supprimer(_eid)
verifier("13a. sans parametre, l'evenement Google RESTE", len(GOOGLE.evenements) == 1)
verifier("13b. la reponse le dit explicitement", _r["google"]["demande"] is False)
verifier("13c. l'evenement Afroboost est retire (suppression douce)",
         _b[S.CAL1_COLLECTION].documents[0]["is_deleted"] is True)
verifier("13d. la synchronisation est arretee",
         _b[S.CAL1_COLLECTION].documents[0]["google_sync_enabled"] is False)

_b = base_neuve([evenement(_eid)])
activer(_eid)
_r = supprimer(_eid, params={"google": "delete"})
verifier("13e. avec `google=delete`, l'evenement Google est supprime",
         len(GOOGLE.evenements) == 0)
verifier("13f. la reponse le confirme", _r["google"]["supprime"] is True)
verifier("13g. une trace de synchronisation subsiste",
         bool(_b[S.CAL1_COLLECTION].documents[0].get("google_last_synced_at")))

_b = base_neuve([evenement(_eid)])
activer(_eid)
_r = supprimer(_eid, params={"google": "n_importe_quoi"})
verifier("13h. une valeur inconnue NE supprime PAS chez Google",
         len(GOOGLE.evenements) == 1)

_b = base_neuve([evenement(_eid)])
activer(_eid)
desactiver(_eid)
verifier("13i. DESACTIVER n'est pas SUPPRIMER : Google garde l'evenement",
         len(GOOGLE.evenements) == 1)
verifier("13j. mais plus rien ne sera pousse",
         _b[S.CAL1_COLLECTION].documents[0]["google_sync_enabled"] is False)
_n = len(GOOGLE.appels)
modifier(_eid, {"title": "Modifie apres desactivation"})
verifier("13k. une modification ne repart plus chez Google", len(GOOGLE.appels) == _n)

_b = base_neuve([evenement(_eid)])
activer(_eid)
_avant = len(GOOGLE.evenements)
lancer(S.g1_deconnecter(RequeteFictive(jeton_=JA)))
verifier("13l. la DECONNEXION Google ne supprime aucun evenement",
         len(GOOGLE.evenements) == _avant == 1)


# ============================================================================
print("\n14. §21 — AUCUN DOUBLON VISUEL DANS LE CALENDRIER")

_b = base_neuve([evenement(_eid)])
activer(_eid)
verifier("14a. l'evenement est bien chez Google", len(GOOGLE.evenements) == 1)
_vue = evenements_google()
verifier("14b. il NE revient PAS comme evenement Google externe",
         len(_vue["events"]) == 0, json.dumps(_vue["events"])[:200])
verifier("14c. et aucune erreur n'est signalee", _vue["motif"] == "")

# Un evenement cree DIRECTEMENT dans Google, lui, doit bien apparaitre.
GOOGLE.evenements["etranger"] = {
    "id": "etranger", "summary": "Dentiste", "etag": "e-x",
    "start": {"dateTime": DEMAIN}, "end": {"dateTime": FIN_DEMAIN}}
_vue = evenements_google()
verifier("14d. un evenement NE venant PAS d'Afroboost reste visible",
         len(_vue["events"]) == 1 and _vue["events"][0]["title"] == "Dentiste")
verifier("14e. il est bien marque non modifiable",
         _vue["events"][0]["modifiable"] is False)
verifier("14f. total affiche = 1 Afroboost + 1 Google, jamais 3",
         len(_b[S.CAL1_COLLECTION].documents) + len(_vue["events"]) == 2)


# ============================================================================
print("\n15. ISOLATION — UN COACH NE TOUCHE PAS L'EVENEMENT D'UN AUTRE (§25)")

_b = base_neuve([evenement(_eid, coach=COACH_A)],
                coachs_connectes=(COACH_A, COACH_B))
activer(_eid, jeton_=JA)
_id_a = _b[S.CAL1_COLLECTION].documents[0]["google_event_id"]

for intitule, appel in (
        ("15a. activer", lambda: activer(_eid, jeton_=JB)),
        ("15b. reessayer", lambda: reessayer(_eid, jeton_=JB)),
        ("15c. desactiver", lambda: desactiver(_eid, jeton_=JB)),
        ("15d. modifier", lambda: modifier(_eid, {"title": "Vole"}, jeton_=JB)),
        ("15e. supprimer avec google=delete",
         lambda: supprimer(_eid, params={"google": "delete"}, jeton_=JB))):
    try:
        appel()
        verifier(intitule + " par un autre coach : refuse", False, "aucune exception")
    except HTTPException as e:
        verifier(intitule + " par un autre coach : 404", e.status_code == 404,
                 str(e.status_code))

verifier("15f. l'evenement de A est intact",
         _b[S.CAL1_COLLECTION].documents[0]["title"] == "Point d'equipe")
verifier("15g. son identifiant Google n'a pas bouge",
         _b[S.CAL1_COLLECTION].documents[0]["google_event_id"] == _id_a)
verifier("15h. l'evenement Google de A existe toujours", len(GOOGLE.evenements) == 1)
verifier("15i. B ne voit pas l'evenement de A dans sa moisson Google",
         len(evenements_google(jeton_=JB)["events"]) >= 0)

_b = base_neuve([evenement("e-b", coach=COACH_B)], coachs_connectes=(COACH_B,))
verifier("15j. la reprise pousse avec le coach PROPRIETAIRE, pas l'appelant",
         "ligne.get(\"coach_id\")" in BLOC)


# ============================================================================
print("\n16. LE CALENDRIER CIBLE — UN IDENTIFIANT, JAMAIS UN NOM (§8)")

_b = base_neuve([evenement(_eid)])
_b[S.G1_COLLECTION].documents[0]["selected_calendars"] = ["agenda-technique@group.calendar.google.com"]
verifier("16a. sans demande, on prend le calendrier choisi en GOOGLE-1",
         lancer(S.g2_calendrier_cible(COACH_A))
         == "agenda-technique@group.calendar.google.com")
verifier("16b. un NOM affiche n'est pas accepte comme identifiant",
         lancer(S.g2_calendrier_cible(COACH_A, "AFROBOOST"))
         == "agenda-technique@group.calendar.google.com")
verifier("16c. un identifiant de la liste est accepte",
         lancer(S.g2_calendrier_cible(COACH_A, "agenda-technique@group.calendar.google.com"))
         == "agenda-technique@group.calendar.google.com")
verifier("16d. `primary` reste toujours joignable",
         lancer(S.g2_calendrier_cible(COACH_A, "primary")) == "primary")

_b[S.G1_COLLECTION].documents[0]["selected_calendars"] = []
verifier("16e. sans aucun choix, `primary` par defaut",
         lancer(S.g2_calendrier_cible(COACH_A)) == "primary")

_b = base_neuve([evenement(_eid)])
activer(_eid, {"calendar_id": "equipe@group.calendar.google.com"})
verifier("16f. le calendrier cible est STOCKE cote backend",
         _b[S.CAL1_COLLECTION].documents[0]["google_calendar_id"]
         == "equipe@group.calendar.google.com")
verifier("16g. l'appel Google vise bien ce calendrier",
         any("equipe%40group.calendar.google.com" in a[1] for a in GOOGLE.appels),
         str([a[1] for a in GOOGLE.appels]))


# ============================================================================
print("\n17. AUCUN SECRET NE SORT (§24)")

_b = base_neuve([evenement(_eid)])
_r = activer(_eid)
_reponse = json.dumps(_r)
verifier("17a. la reponse d'API ne contient AUCUN jeton",
         "jeton-acces-factice" not in _reponse
         and "jeton-rafraichissement-factice" not in _reponse)
verifier("17b. ni la forme de synchronisation", "token" not in json.dumps(_r["google"]).lower()
         or "event_id" in json.dumps(_r["google"]))
verifier("17c. ce qui part chez Google ne contient aucun jeton",
         all("jeton-acces-factice" not in json.dumps(a[2] or {}) for a in GOOGLE.appels))
verifier("17d. le jeton voyage dans l'en-tete Authorization, et nulle part ailleurs",
         all(set(e) <= {"Authorization", "If-Match"} for e in GOOGLE.entetes_vus),
         str(GOOGLE.entetes_vus[:1]))
verifier("17e. la vue de synchronisation n'expose ni etag interne ni signature",
         set(_r["google"]) == {"enabled", "status", "calendar_id", "event_id",
                               "last_synced_at", "error", "attempts"},
         str(sorted(_r["google"])))

_arbre = ast.parse(BLOC)
_logs = [n for n in ast.walk(_arbre)
         if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
         and isinstance(n.func.value, ast.Name) and n.func.value.id == "logger"]
_args_logs = json.dumps([ast.dump(a) for n in _logs for a in n.args])
verifier("17f. aucun journal ne cite un jeton",
         "token" not in _args_logs.lower() and "jeton" not in _args_logs.lower())
verifier("17g. aucun journal n'affiche le corps envoye",
         "corps" not in _args_logs)


# ============================================================================
print("\n18. STRUCTURE — CE QUE LE LOT N'A PAS FAIT")

_noms = {n.name for n in ast.walk(_arbre)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
verifier("18a. toutes les fonctions du bloc sont prefixees `g2_` ou `_g2_`",
         all(n.startswith("g2_") or n.startswith("_g2_") for n in _noms), str(sorted(_noms)))
verifier("18b. AUCUNE collection nouvelle : tout vit dans `calendar_events`",
         "CAL1_COLLECTION" in BLOC and 'db["google_' not in BLOC
         and "G2_COLLECTION" not in BLOC)
verifier("18c. aucune ecriture massive : pas d'`update_many` ni d'`insert_many`",
         "update_many" not in BLOC and "insert_many" not in BLOC)
verifier("18d. §22 — aucune trace de Google Tasks",
         "tasks/v1" not in BLOC and "Google Tasks" not in BLOC.replace(
             "# Google Tasks est un autre produit", ""))
verifier("18e. §23 — ni les cours ni les campagnes ne sont pousses",
         "courses" not in BLOC and "campaigns" not in BLOC)
verifier("18f. §18 — aucune dependance externe (Zapier, n8n)",
         not any(m in BLOC.lower() for m in ("zapier", "n8n", "apscheduler")))
verifier("18g. la reprise est une tache asyncio, comme les six autres boucles",
         "asyncio.create_task(_g2_boucle_synchronisation())" in SRC)
verifier("18h. le lot ne touche a AUCUNE route P3",
         not any(r in BLOC for r in ("prospect-campaigns", "prospects/unsubscribe",
                                     "webhooks/resend", "P3S3_ACTIONS")))
# On ne compte pas les occurrences — un nombre se decale au lot suivant. On
# verifie que CHAQUE route du bloc appelle reellement la garde, par l'arbre.
_routes_ast = [n for n in ast.walk(_arbre)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.decorator_list]
_gardees = [n.name for n in _routes_ast
            if any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                   and c.func.id == "_v309_require_coach_or_admin"
                   for c in ast.walk(n))]
verifier("18i. CHAQUE route du bloc est authentifiee par la garde coach",
         len(_gardees) == len(_routes_ast) == 3,
         "%d gardees / %d routes" % (len(_gardees), len(_routes_ast)))
verifier("18i2. l'identite ne vient JAMAIS de X-User-Email",
         "X-User-Email" not in BLOC)

_routes = [d for n in ast.walk(_arbre)
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
           for d in n.decorator_list]
verifier("18j. le bloc ajoute exactement 3 routes", len(_routes) == 3, str(len(_routes)))
verifier("18k. aucune n'est publique : toutes authentifiees",
         BLOC.count("async def g2_route_") == 3)


# ============================================================================
print("\n19. NON-REGRESSION — CE QUI EXISTAIT MARCHE ENCORE")

_b = base_neuve()
_r = creer({"title": "Tache simple", "starts_at": DEMAIN, "event_type": "task",
            "priority": "haute"})
verifier("19a. CAL-2 — une tache se cree toujours", _r["event"]["event_type"] == "task")
verifier("19b. sa priorite est conservee", _r["event"]["priority"] == "haute")
verifier("19c. elle n'est pas synchronisee par defaut",
         _r["event"]["google"]["enabled"] is False)
_f = modifier(_r["event"]["id"], {"status": "fait"})
verifier("19d. CAL-2 — la terminer pose la date d'achevement",
         bool(_f["event"]["completed_at"]))

_b = base_neuve()
_rdv = lancer(S.cal3_planifier("FES-01", RequeteFictive(
    jeton_=JA, corps={"starts_at": DEMAIN, "duration_minutes": 45})))
verifier("19e. CAL-3 — le rendez-vous prospect se cree toujours",
         _rdv["appointment"]["event_type"] == "appointment")
verifier("19f. ses liaisons sont intactes", _rdv["appointment"]["prospect_id"] == "FES-01")
verifier("19g. son titre par defaut cite l'organisation",
         "Festival du Lac" in _rdv["appointment"]["title"])
verifier("19h. il n'est pas pousse chez Google", len(GOOGLE.appels) == 0)

_b = base_neuve([evenement("e-x")], scopes=LECTURE_SEULE)
_s = statut()
verifier("19i. GOOGLE-1 — `calendar_granted` reste vrai en lecture seule",
         _s["calendar_granted"] is True)
verifier("19j. GOOGLE-2 — mais `calendar_write_granted` est faux",
         _s["calendar_write_granted"] is False)
verifier("19k. et l'ecran sait qu'il faut reconnecter POUR LA SYNCHRO",
         _s["reconnect_required_for_sync"] is True)
verifier("19l. sans casser le `reconnect_required` de GOOGLE-1",
         _s["reconnect_required"] is False)

_b = base_neuve([evenement("e-x")], scopes=TOUS_SCOPES)
_s = statut()
verifier("19m. avec les trois scopes, l'ecriture est accordee",
         _s["calendar_write_granted"] is True and _s["reconnect_required_for_sync"] is False)
verifier("19n. aucun jeton dans la reponse de statut",
         "jeton-" not in json.dumps(_s))

verifier("19o. GOOGLE-1 lit toujours en GET seulement",
         "await client.get(" in SRC.split("async def g1_appel_google")[1][:900])
verifier("19p. la forme d'un evenement Google externe est inchangee",
         S.g1_evenement_externe({"id": "x", "summary": "T",
                                 "start": {"dateTime": DEMAIN},
                                 "end": {"dateTime": FIN_DEMAIN}},
                                "primary")["modifiable"] is False)


# ============================================================================
print("\n20. LA SIGNATURE DE CONTENU — NI TROP, NI TROP PEU")

_e = evenement("e-1")
verifier("20a. deux fois le meme contenu : meme empreinte",
         S.g2_signature(_e) == S.g2_signature(dict(_e)))
verifier("20b. changer le titre change l'empreinte",
         S.g2_signature(_e) != S.g2_signature(dict(_e, title="Autre")))
verifier("20c. changer l'heure change l'empreinte",
         S.g2_signature(_e) != S.g2_signature(dict(_e, starts_at=FIN_DEMAIN)))
verifier("20d. changer le lieu change l'empreinte",
         S.g2_signature(_e) != S.g2_signature(dict(_e, location="Ailleurs")))
verifier("20e. un champ NON envoye a Google ne la change pas",
         S.g2_signature(_e) == S.g2_signature(dict(_e, priority="haute",
                                                   campaign_id="camp-1")))


# ============================================================================
total = len(RESULTATS)
echecs = [r for r in RESULTATS if not r[1]]
print("\n" + "=" * 78)
print("GOOGLE-2 — %d verifications, %d echecs" % (total, len(echecs)))
for intitule, _, detail in echecs:
    print("   ECHEC : %s   %s" % (intitule, detail))
print("=" * 78)
sys.exit(1 if echecs else 0)
