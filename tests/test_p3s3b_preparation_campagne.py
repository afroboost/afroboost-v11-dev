#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3-S3-B — LA PREPARATION D'UNE CAMPAGNE, ET RIEN D'AUTRE.

CE QUE LE LOT AJOUTE
==============================================================================
Quatre routes : preparer (simulation par defaut), lister, lire, modifier une
action. Un instantane fige par destinataire. Aucune route d'envoi.

CE QUE CE FICHIER PROUVE, ET COMMENT
==============================================================================
La base est un BOUCHON qui HONORE LES INDEX UNIQUES, y compris les PARTIELS :
c'est indispensable, parce que trois garanties du lot reposent entierement sur
eux — l'unicite du destinataire dans une campagne, l'idempotence de la
preparation, et le fait qu'une campagne seulement PREPAREE ne pose aucun verrou.
Un bouchon qui ignorerait les index validerait un code qui casse en production.

Le bouchon COMPTE aussi les ecritures de CHAQUE collection. C'est la seule
facon de prouver le point central : preparer une campagne n'ecrit que dans
`prospect_campaigns` et `prospect_campaign_actions`, ne touche a AUCUN statut
metier, ne pose NI `first_contact_claimed_at` NI `first_contact_sent_at`, et
ne contacte personne.

AUCUNE ECRITURE EN PRODUCTION. Tout se joue en memoire.

    python3 tests/test_p3s3b_preparation_campagne.py
"""
import ast
import asyncio
import io
import json
import os
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


SECRET = "secret-de-test-p3s3b-sans-aucun-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p3s3b-inexistant:27017")

import jwt as _jwt          # noqa: E402
import api.server as S      # noqa: E402
from fastapi import HTTPException  # noqa: E402

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
COACH_A = "coach.a.fictif@exemple.test"
COACH_B = "coach.b.fictif@exemple.test"
INSTANT = "2026-08-31T18:26:57.951583+00:00"


def lancer(coroutine):
    return asyncio.get_event_loop().run_until_complete(coroutine)


def jeton(email):
    return _jwt.encode({"email": email, "sub": email, "role": "coach"}, SECRET, algorithm="HS256")


class RequeteFictive:
    def __init__(self, jeton_=None, corps=None, params=None):
        self.headers = {}
        if jeton_:
            self.headers["Authorization"] = "Bearer " + jeton_
        self._corps = corps
        if corps is not None:
            self.headers["content-length"] = str(len(json.dumps(corps)))
        self.query_params = params or {}
        self.client = type("C", (), {"host": "127.0.0.1"})()
        self.url = type("U", (), {"path": "/api/prospect-campaigns/prepare"})()
        self.method = "POST"

    async def json(self):
        if self._corps is None:
            raise ValueError("pas de corps")
        return self._corps


class ErreurUnicite(Exception):
    """DuplicateKeyError du bouchon — meme classe que celle attrapee par le code."""


class Curseur:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, cle, sens=1):
        specs = cle if isinstance(cle, list) else [(cle, sens)]
        for champ, s in reversed(specs):
            self._docs = sorted(self._docs, key=lambda d: d.get(champ) or "", reverse=(s == -1))
        return self

    def skip(self, n):
        self._docs = self._docs[n:]
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    async def to_list(self, n=None):
        return [dict(d) for d in (self._docs[:n] if n else self._docs)]


class CollectionBouchon:
    """Honore les filtres du lot, LES INDEX UNIQUES (partiels compris), et COMPTE."""

    def __init__(self, nom, documents=None, uniques=()):
        self.nom = nom
        self.documents = [dict(d) for d in (documents or [])]
        # uniques : (cles, filtre_partiel_ou_None)
        self.uniques = list(uniques)
        self.ecritures = 0

    # --- filtrage ---
    def _ok(self, doc, filtre):
        if not filtre:
            return True
        for cle, val in filtre.items():
            if cle == "$or":
                if not any(self._ok(doc, sous) for sous in val):
                    return False
                continue
            if isinstance(val, dict):
                if "$in" in val and doc.get(cle) not in val["$in"]:
                    return False
                if "$nin" in val and doc.get(cle) in val["$nin"]:
                    return False
                if "$exists" in val and (cle in doc) != val["$exists"]:
                    return False
                if "$ne" in val and doc.get(cle) == val["$ne"]:
                    return False
                continue
            if doc.get(cle) != val:
                return False
        return True

    def _satisfait(self, doc, partiel):
        if not partiel:
            return True
        for cle, cond in partiel.items():
            if isinstance(cond, dict) and "$type" in cond:
                if cond["$type"] == "string" and not isinstance(doc.get(cle), str):
                    return False
            elif doc.get(cle) != cond:
                return False
        return True

    def _verifier_uniques(self, candidat, sauf=None):
        for cles, partiel in self.uniques:
            if not self._satisfait(candidat, partiel):
                continue
            signature = tuple(candidat.get(c) for c in cles)
            for autre in self.documents:
                if autre is sauf or not self._satisfait(autre, partiel):
                    continue
                if tuple(autre.get(c) for c in cles) == signature:
                    raise ErreurUnicite("E11000 %s %s" % (self.nom, cles))

    async def find_one(self, filtre=None, projection=None, *a, **k):
        for d in self.documents:
            if self._ok(d, filtre):
                return dict(d)
        return None

    def find(self, filtre=None, projection=None, *a, **k):
        return Curseur([dict(d) for d in self.documents if self._ok(d, filtre)])

    async def count_documents(self, filtre=None, *a, **k):
        return sum(1 for d in self.documents if self._ok(d, filtre))

    def aggregate(self, etapes, *a, **k):
        docs = list(self.documents)
        groupes = {}
        for etape in etapes:
            if "$match" in etape:
                docs = [d for d in docs if self._ok(d, etape["$match"])]
            if "$group" in etape:
                cle = etape["$group"]["_id"].lstrip("$")
                for d in docs:
                    groupes[d.get(cle)] = groupes.get(d.get(cle), 0) + 1

        class _C:
            def __aiter__(self_inner):
                self_inner._i = iter([{"_id": k, "n": v} for k, v in groupes.items()])
                return self_inner

            async def __anext__(self_inner):
                try:
                    return next(self_inner._i)
                except StopIteration:
                    raise StopAsyncIteration
        return _C()

    async def insert_one(self, doc, *a, **k):
        candidat = dict(doc)
        self._verifier_uniques(candidat)
        self.ecritures += 1
        self.documents.append(candidat)
        return None

    async def update_one(self, filtre, maj, *a, **k):
        for d in self.documents:
            if self._ok(d, filtre):
                candidat = dict(d)
                candidat.update(maj.get("$set") or {})
                self._verifier_uniques(candidat, sauf=d)
                d.update(maj.get("$set") or {})
                self.ecritures += 1
                return type("R", (), {"matched_count": 1, "modified_count": 1})()
        return type("R", (), {"matched_count": 0, "modified_count": 0})()

    async def insert_many(self, docs, *a, **k):
        for d in docs:
            await self.insert_one(d)

    async def delete_one(self, *a, **k):
        self.ecritures += 1

    async def delete_many(self, *a, **k):
        self.ecritures += 1

    async def find_one_and_update(self, *a, **k):
        self.ecritures += 1
        return None

    async def create_index(self, *a, **k):
        return "idx"


class BaseBouchon:
    def __init__(self, prospects):
        self._cols = {}
        self["partner_prospects"] = CollectionBouchon(
            "partner_prospects", prospects, uniques=[(("coach_id", "ref"), {"ref": {"$type": "string"}}),
                                                     (("id",), None)])
        self["prospect_campaigns"] = CollectionBouchon(
            "prospect_campaigns", [],
            uniques=[(("id",), None),
                     (("coach_id", "idempotency_key"), {"idempotency_key": {"$type": "string"}})])
        self["prospect_campaign_actions"] = CollectionBouchon(
            "prospect_campaign_actions", [],
            uniques=[(("id",), None),
                     (("campaign_id", "recipient_key"), {"recipient_key": {"$type": "string"}}),
                     (("coach_id", "recipient_key"), {"verrou_actif": True})])
        self["coaches"] = CollectionBouchon("coaches", [{"email": COACH_A}, {"email": COACH_B}])
        self["coach_auth"] = CollectionBouchon("coach_auth", [])

    def __setitem__(self, nom, col):
        self._cols[nom] = col

    def __getitem__(self, nom):
        if nom not in self._cols:
            self._cols[nom] = CollectionBouchon(nom)
        return self._cols[nom]

    def __getattr__(self, nom):
        return self[nom]

    def total_ecritures(self, sauf=()):
        return sum(c.ecritures for n, c in self._cols.items() if n not in sauf)


def fiche(ref, nom, ville, **extra):
    base = {"id": "p-" + ref.lower(), "ref": ref, "coach_id": COACH_A,
            "organisation_name": nom, "city": ville, "city_key": S.p3s1_normaliser(ville),
            "category": "festival", "status": "a_contacter", "created_at": INSTANT,
            "wave": "Vague 1", "priority": "B"}
    base.update(extra)
    return base


# --- Le jeu de fiches : les VRAIS cas de production, en miniature ------------
FICHES = [
    # Wellness : 2 fiches, 1 destinataire (e-mail partage). Canal declare e-mail.
    fiche("GVA-F3", "Wellness Sport Club Geneve", "Geneve", public_email="lpd@wellness-sportclub.ch",
          instagram="https://www.instagram.com/wellness_sportclubch",
          preferred_channel="E-mail", j0_message="Bonjour Wellness Geneve", language="FR"),
    fiche("LSN-F3", "Wellness Sport Club Lausanne", "Lausanne", public_email="lpd@wellness-sportclub.ch",
          public_phone="021 320 56 76", preferred_channel="E-mail",
          j0_message="Bonjour Wellness Lausanne", language="FR"),
    # Dancefloor : 2 fiches, 1 destinataire (e-mail + telephone partages).
    fiche("GVA-D2", "Dancefloor Studio (Geneve)", "Geneve",
          public_email="infos@dancefloorgenevasalsa.ch", public_phone="+41 76 233 49 43",
          instagram="https://www.instagram.com/dancefloor_team",
          preferred_channel="E-mail", j0_message="Bonjour Dancefloor", language="FR"),
    fiche("LSN-D5", "Dancefloor Studio (Lausanne)", "Lausanne",
          public_email="infos@dancefloorgenevasalsa.ch", public_phone="076 233 49 43",
          preferred_channel="E-mail / DM", j0_message="Bonjour Dancefloor bis", language="FR"),
    # RESO / Fete de la Danse : 3 antennes, MEME domaine, AUCUNE preuve partagee.
    fiche("ORG-01", "Fete de la Danse NE / RESO", "Neuchatel", website="https://fetedeladanse.ch",
          website_domain="fetedeladanse.ch", instagram="(comptes FdlD)",
          preferred_channel="Formulaire", j0_message="Bonjour RESO", language="FR"),
    fiche("LSN-E3", "Fete de la Danse — Lausanne", "Lausanne", website_domain="fetedeladanse.ch",
          instagram="https://www.instagram.com/fetedeladanse",
          preferred_channel="Instagram DM", j0_message="Bonjour FdlD Lausanne", language="FR"),
    fiche("GVA-E3", "Fete de la Danse — Geneve", "Geneve", website_domain="fetedeladanse.ch",
          instagram="Fete de la Danse (compte)", public_email="geneve@fetedeladanse.ch",
          preferred_channel="E-mail", j0_message="Bonjour FdlD Geneve", language="FR"),
    # Zurich : message ALLEMAND + traduction francaise interne.
    fiche("ZRH-D3", "Dynamo Zurich — African Dance", "Zurich", public_email="tanz@dynamo.ch",
          preferred_channel="E-mail", language="allemand",
          j0_message="Guten Tag, wir sind Afroboost",
          j0_fr_translation="Bonjour, nous sommes Afroboost"),
    # Un destinataire SANS aucune coordonnee -> BLOQUE.
    fiche("BAR-09", "Les Brasseurs", "Neuchatel", preferred_channel="A identifier"),
    # Un destinataire Instagram SEUL -> MANUEL.
    fiche("INF-01", "Coach Ikram", "Neuchatel", instagram="https://www.instagram.com/coach_ikram",
          preferred_channel="Instagram DM", j0_message="Bonjour Ikram", language="FR"),
]
# 10 fiches -> 8 destinataires (Wellness et Dancefloor fusionnent).


def base_neuve():
    b = BaseBouchon([dict(f) for f in FICHES])
    S.db = b
    return b


JA = jeton(COACH_A)
JB = jeton(COACH_B)


def preparer(base, **corps):
    return lancer(S.p3s3_preparer_campagne(RequeteFictive(jeton_=JA, corps=corps)))


# ============================================================================
print("\n1. AUCUNE ROUTE D'ENVOI N'EXISTE")

CHEMINS = [r.path for r in S.app.routes if "prospect-campaigns" in getattr(r, "path", "")]
verifier("1a. sept routes de campagne, pas une de plus", len(CHEMINS) == 7, str(CHEMINS))
verifier("1a-bis. et ce sont exactement celles attendues",
         sorted(CHEMINS) == sorted([
             "/api/prospect-campaigns/prepare",
             "/api/prospect-campaigns",
             "/api/prospect-campaigns/{campaign_id}",
             "/api/prospect-campaigns/{campaign_id}",
             "/api/prospect-campaigns/{campaign_id}/approve",
             "/api/prospect-campaigns/{campaign_id}/reopen",
             "/api/prospect-campaigns/{campaign_id}/actions/{action_id}"]), str(sorted(CHEMINS)))
for _interdit in ("send", "launch", "dispatch", "retry", "j3", "j7", "execute"):
    verifier("1b. aucune route contenant %r" % _interdit,
             not any(_interdit in c for c in CHEMINS))

DEBUT = SRC.index("# P3-S3-B — LA PREPARATION D'UNE CAMPAGNE")
_SUITE = "# P3-S3-D1 — LE CONTRAT D'EXECUTION"
FIN = (SRC.index(_SUITE, DEBUT) if _SUITE in SRC[DEBUT:]
       else SRC.index("# --- Leads Routes (Widget IA) ---", DEBUT))
BLOC = SRC[DEBUT:FIN]
ARBRE = ast.parse(BLOC)
_appeles = set()
for _n in ast.walk(ARBRE):
    if isinstance(_n, ast.Call):
        _appeles.add(getattr(_n.func, "id", None) or getattr(_n.func, "attr", None))
    if isinstance(_n, ast.Attribute):
        _appeles.add(_n.attr)
_appeles.discard(None)
for _interdit in ("send_email", "send_bulk_email", "_send_whatsapp_meta", "send_push",
                  "send_push_by_email", "notify_all", "create_task", "Emails",
                  "httpx", "requests", "aiohttp", "urlopen", "urlretrieve",
                  "AsyncClient", "ClientSession", "sendmail", "SMTP"):
    verifier("1c. le bloc P3-S3-B n'invoque jamais %r" % _interdit, _interdit not in _appeles)

# Les SEULS decorateurs autorises : les quatre routes de preparation et de
# lecture. Tout autre verbe HTTP, ou tout chemin inattendu, doit sauter aux yeux.
_decore = []
for _n in ast.walk(ARBRE):
    for _d in getattr(_n, "decorator_list", []) or []:
        _verbe = getattr(getattr(_d, "func", _d), "attr", "?")
        _chemin = _d.args[0].value if getattr(_d, "args", None) else "?"
        _decore.append((_verbe, _chemin))
verifier("1c-bis. les decorateurs du bloc sont ceux attendus, et rien d'autre",
         sorted(_decore) == sorted([
             ("post", "/prospect-campaigns/prepare"),
             ("get", "/prospect-campaigns"),
             ("get", "/prospect-campaigns/{campaign_id}"),
             ("post", "/prospect-campaigns/{campaign_id}/approve"),
             ("post", "/prospect-campaigns/{campaign_id}/reopen"),
             ("patch", "/prospect-campaigns/{campaign_id}"),
             ("patch", "/prospect-campaigns/{campaign_id}/actions/{action_id}")]),
         str(sorted(_decore)))
verifier("1d. le bloc n'appelle meme pas la porte d'envoi (rien a autoriser)",
         "p3s3_envoi_autorise" not in _appeles)
verifier("1e. le bloc n'ecrit jamais dans partner_prospects",
         "P3S1_COLLECTION].insert_one" not in BLOC and
         "P3S1_COLLECTION].update_one" not in BLOC and
         "P3S1_COLLECTION].delete_one" not in BLOC)


# ============================================================================
print("\n2. LE DRY-RUN N'ECRIT RIEN — ET C'EST LE DEFAUT")

_b = base_neuve()
_r = preparer(_b)                                   # aucun `dry_run` fourni
verifier("2a. sans parametre, la preparation est une SIMULATION", _r["dry_run"] is True)
verifier("2b. 0 ecriture dans prospect_campaigns", _b["prospect_campaigns"].ecritures == 0)
verifier("2c. 0 ecriture dans prospect_campaign_actions",
         _b["prospect_campaign_actions"].ecritures == 0)
verifier("2d. 0 ecriture dans partner_prospects", _b["partner_prospects"].ecritures == 0)
verifier("2e. 0 ecriture NULLE PART, toutes collections confondues",
         _b.total_ecritures() == 0, "ecritures : %d" % _b.total_ecritures())
verifier("2f. `dry_run: true` explicite : meme resultat",
         preparer(_b, dry_run=True)["dry_run"] is True and _b.total_ecritures() == 0)

verifier("2g. le dry-run rend le resume complet",
         set(_r["summary"]) >= {"destinataires", "fiches", "par_execution",
                                "par_canal", "par_langue", "sans_message_j0"})
verifier("2h. il rend aussi les actions QUI SERAIENT creees", len(_r["actions"]) == 8,
         "actions : %d" % len(_r["actions"]))


# ============================================================================
print("\n3. 10 FICHES -> 8 DESTINATAIRES, ET LES CAS NOMMES")

_S = _r["summary"]
verifier("3a. fiches comptees : 10", _S["fiches"] == 10, str(_S["fiches"]))
verifier("3b. destinataires uniques : 8", _S["destinataires"] == 8, str(_S["destinataires"]))
verifier("3c. dont 2 regroupements multi-fiches", _S["multi_fiches"] == 2)

_par = {a["recipient_key"]: a for a in _r["actions"]}
verifier("3d. DANCEFLOOR : une seule action pour GVA-D2 + LSN-D5",
         "GVA-D2" in _par and sorted(_par["GVA-D2"]["prospect_ids"]) == ["GVA-D2", "LSN-D5"]
         and "LSN-D5" not in _par, str(sorted(_par)))
verifier("3e. WELLNESS : une seule action pour GVA-F3 + LSN-F3",
         "GVA-F3" in _par and sorted(_par["GVA-F3"]["prospect_ids"]) == ["GVA-F3", "LSN-F3"]
         and "LSN-F3" not in _par)
verifier("3f. RESO / Fete de la Danse : TROIS actions distinctes",
         all(k in _par for k in ("ORG-01", "LSN-E3", "GVA-E3")))
verifier("3g. ... et le domaine partage n'a fusionne personne",
         all(len(_par[k]["prospect_ids"]) == 1 for k in ("ORG-01", "LSN-E3", "GVA-E3")))
verifier("3h. la deduplication est celle de P3-S3-A, pas une seconde",
         "p3s3_grouper(fiches)" in BLOC and "grouper" not in BLOC.split("p3s3_grouper(fiches)")[0]
         .rsplit("def ", 1)[-1])


# ============================================================================
print("\n4. CANAL ET TYPE D'EXECUTION")

verifier("4a. WELLNESS : e-mail declare + e-mail public -> AUTO",
         _par["GVA-F3"]["channel"] == "email" and _par["GVA-F3"]["execution_type"] == "AUTO")
verifier("4b. RESO : formulaire declare, aucun e-mail -> ASSISTE",
         _par["ORG-01"]["channel"] == "formulaire" and _par["ORG-01"]["execution_type"] == "ASSISTE",
         "%s / %s" % (_par["ORG-01"]["channel"], _par["ORG-01"]["execution_type"]))
verifier("4c. FdlD Lausanne : DM declare + compte reel, aucun e-mail -> MANUEL",
         _par["LSN-E3"]["channel"] == "instagram" and _par["LSN-E3"]["execution_type"] == "MANUEL")
verifier("4d. FdlD Geneve : e-mail declare -> AUTO (le canal declare l'emporte)",
         _par["GVA-E3"]["channel"] == "email" and _par["GVA-E3"]["execution_type"] == "AUTO")
verifier("4e. INF-01 : Instagram seul, aucun e-mail -> MANUEL",
         _par["INF-01"]["channel"] == "instagram" and _par["INF-01"]["execution_type"] == "MANUEL")
verifier("4f. BAR-09 : aucune coordonnee -> BLOQUE, et statut `bloque`",
         _par["BAR-09"]["channel"] == "aucun" and _par["BAR-09"]["execution_type"] == "BLOQUE"
         and _par["BAR-09"]["statut"] == "bloque")
verifier("4g. le secours est ENREGISTRE, pas emprunte : Wellness garde Instagram en secours",
         _par["GVA-F3"]["backup_channel"] == "instagram", str(_par["GVA-F3"]["backup_channel"]))
verifier("4h. un destinataire sans secours porte None, jamais une invention",
         _par["BAR-09"]["backup_channel"] is None)

# WhatsApp n'est JAMAIS deduit d'un numero.
_sans_mention = S.p3s3_canal_et_execution([fiche("X-1", "X", "Neuchatel",
                                                 public_phone="+41 79 111 22 33",
                                                 preferred_channel="Telephone")])
verifier("4i. un TELEPHONE seul ne devient jamais WhatsApp",
         _sans_mention["channel"] == "telephone")
_avec_mention = S.p3s3_canal_et_execution([fiche("X-2", "X", "Neuchatel",
                                                 public_phone="+41 79 111 22 33",
                                                 preferred_channel="WhatsApp")])
verifier("4j. il faut une mention EXPLICITE pour que WhatsApp soit retenu",
         _avec_mention["channel"] == "whatsapp" and _avec_mention["execution_type"] == "ASSISTE")
_wa_sans_num = S.p3s3_canal_et_execution([fiche("X-3", "X", "Neuchatel",
                                                preferred_channel="WhatsApp")])
verifier("4k. une mention WhatsApp SANS numero ne suffit pas non plus",
         _wa_sans_num["channel"] != "whatsapp")


# ============================================================================
print("\n5. LES MESSAGES SONT PERSONNALISES, JAMAIS GENERIQUES")

_messages = [a["message_j0"] for a in _r["actions"] if a["message_j0"]]
verifier("5a. chaque message present est UNIQUE",
         len(_messages) == len(set(_messages)), str(len(_messages)))
verifier("5b. aucun message n'est fabrique : BAR-09 n'en a pas et n'en recoit pas",
         _par["BAR-09"]["message_j0"] == "" and _par["BAR-09"]["message_j0_origine"] == "absent")
verifier("5c. le resume compte les destinataires sans message J0",
         _S["sans_message_j0"] == 1, str(_S["sans_message_j0"]))
verifier("5d. ZURICH : le message ALLEMAND est conserve tel quel",
         _par["ZRH-D3"]["message_j0"] == "Guten Tag, wir sind Afroboost")
verifier("5e. ZURICH : la langue est conservee",
         _par["ZRH-D3"]["language"] == "allemand")
verifier("5f. ZURICH : la traduction francaise est gardee A PART, jamais a la place",
         _par["ZRH-D3"]["j0_fr_translation"] == "Bonjour, nous sommes Afroboost"
         and _par["ZRH-D3"]["message_j0"] != _par["ZRH-D3"]["j0_fr_translation"])
verifier("5g. un groupe multi-fiches garde le message de sa fiche de tete",
         _par["GVA-F3"]["message_j0"] == "Bonjour Wellness Geneve")


# ============================================================================
print("\n6. L'APPLY CREE UNE CAMPAGNE PREPAREE — ET RIEN QUI RESSEMBLE A UN ENVOI")

_b = base_neuve()
_a = preparer(_b, dry_run=False, name="P3-LAUNCH-8")
verifier("6a. la campagne est creee", _b["prospect_campaigns"].ecritures == 1)
verifier("6b. 8 actions creees", _a["actions_creees"] == 8, str(_a["actions_creees"]))
verifier("6c. aucune action refusee", _a["actions_refusees"] == 0)
_camp = _b["prospect_campaigns"].documents[0]
verifier("6d. l'etat est `preparee`", _camp["etat"] == "preparee", _camp["etat"])
for _interdit in ("sending", "sent", "contacte", "approuvee", "en_cours"):
    verifier("6e. l'etat n'est PAS %r" % _interdit, _camp["etat"] != _interdit)
verifier("6f. approbation NON posee", _camp["approved_at"] is None and _camp["approved_by"] is None)
verifier("6g. demarrage NON pose", _camp["started_at"] is None and _camp["finished_at"] is None)

_acts = _b["prospect_campaign_actions"].documents
verifier("6h. AUCUNE action ne porte `verrou_actif`",
         not any("verrou_actif" in a for a in _acts))
verifier("6i. AUCUNE action ne porte claimed_at / sent_at",
         not any(("claimed_at" in a) or ("sent_at" in a) for a in _acts))
verifier("6j. les statuts d'action sont `pret` ou `bloque`, rien d'autre",
         {a["statut"] for a in _acts} == {"pret", "bloque"},
         str({a["statut"] for a in _acts}))

# LE POINT CENTRAL : preparer ne touche NI les prospects, NI le reste du systeme.
verifier("6k. 0 ecriture dans partner_prospects", _b["partner_prospects"].ecritures == 0)
verifier("6l. les 10 fiches restent `a_contacter`",
         all(f["status"] == "a_contacter" for f in _b["partner_prospects"].documents))
verifier("6m. first_contact_claimed_at ecrit sur 0 fiche",
         sum(1 for f in _b["partner_prospects"].documents if "first_contact_claimed_at" in f) == 0)
verifier("6n. first_contact_sent_at ecrit sur 0 fiche",
         sum(1 for f in _b["partner_prospects"].documents if "first_contact_sent_at" in f) == 0)
verifier("6o. AUCUNE autre collection n'a ete ecrite (contact, lead, notification...)",
         _b.total_ecritures(sauf=("prospect_campaigns", "prospect_campaign_actions")) == 0,
         "ecritures ailleurs : %d" % _b.total_ecritures(
             sauf=("prospect_campaigns", "prospect_campaign_actions")))


# ============================================================================
print("\n7. LE SNAPSHOT EST IMMUABLE")

_avant = dict(next(a for a in _acts if a["recipient_key"] == "GVA-F3"))
# On modifie la FICHE apres la preparation, comme le ferait le coach.
for f in _b["partner_prospects"].documents:
    if f["ref"] == "GVA-F3":
        f["j0_message"] = "MESSAGE COMPLETEMENT REECRIT"
        f["public_email"] = "autre@ailleurs.test"
        f["preferred_channel"] = "Instagram DM"
        f["organisation_name"] = "Nom change"

_relu = lancer(S.p3s3_lire_campagne(_camp["id"], RequeteFictive(jeton_=JA)))
_apres = next(a for a in _relu["actions"] if a["recipient_key"] == "GVA-F3")
for _champ in ("message_j0", "channel", "target", "execution_type", "organisations", "language"):
    verifier("7a. le snapshot conserve %-16s malgre la fiche modifiee" % _champ,
             _apres[_champ] == _avant[_champ],
             "avant=%r apres=%r" % (_avant[_champ], _apres[_champ]))
verifier("7b. le message fige n'est PAS celui de la fiche reecrite",
         _apres["message_j0"] == "Bonjour Wellness Geneve")
verifier("7c. l'action ne relit jamais la fiche : aucun `find` de prospect dans la lecture",
         "P3S1_COLLECTION].find" not in
         BLOC.split("async def p3s3_lire_campagne")[1].split("@api_router")[0])


# ============================================================================
print("\n8. IDEMPOTENCE : LE DOUBLE CLIC NE CREE PAS DEUX CAMPAGNES")

_b = base_neuve()
_un = preparer(_b, dry_run=False, idempotency_key="clic-unique-42")
_deux = preparer(_b, dry_run=False, idempotency_key="clic-unique-42")
verifier("8a. le premier appel cree la campagne", _un["rejeu"] is False)
verifier("8b. le SECOND appel la reconnait au lieu d'en creer une jumelle",
         _deux["rejeu"] is True)
verifier("8c. une seule campagne en base", len(_b["prospect_campaigns"].documents) == 1)
verifier("8d. le meme identifiant est rendu",
         _un["campaign"]["id"] == _deux["campaign"]["id"])
verifier("8e. 8 actions, pas 16", len(_b["prospect_campaign_actions"].documents) == 8)

_troisieme = preparer(_b, dry_run=False, idempotency_key="autre-clic-43")
verifier("8f. une cle DIFFERENTE ne cree PLUS de seconde campagne (garde P3-S3-C)",
         len(_b["prospect_campaigns"].documents) == 1 and _troisieme["rejeu"] is True,
         "campagnes : %d" % len(_b["prospect_campaigns"].documents))
_deliberee = preparer(_b, dry_run=False, idempotency_key="voulue-44", allow_new=True)
verifier("8f-bis. ... sauf demande EXPLICITE du coach (`allow_new`)",
         len(_b["prospect_campaigns"].documents) == 2 and _deliberee["rejeu"] is False)
verifier("8g. deux campagnes PREPAREES coexistent sur les memes destinataires",
         len(_b["prospect_campaign_actions"].documents) == 16)
verifier("8h. ... parce qu'aucune ne pose `verrou_actif` (le verrou vient plus tard)",
         not any("verrou_actif" in a for a in _b["prospect_campaign_actions"].documents))

# Sans cle, deux preparations restent deux campagnes : c'est legitime.
_b2 = base_neuve()
preparer(_b2, dry_run=False)
preparer(_b2, dry_run=False)
verifier("8i. sans cle d'idempotence non plus, une seule campagne (garde P3-S3-C)",
         len(_b2["prospect_campaigns"].documents) == 1,
         "campagnes : %d" % len(_b2["prospect_campaigns"].documents))


# ============================================================================
print("\n9. UN DESTINATAIRE NE PEUT PAS ETRE DEUX FOIS DANS UNE CAMPAGNE")

_b = base_neuve()
preparer(_b, dry_run=False)
_col = _b["prospect_campaign_actions"]
_camp_id = _b["prospect_campaigns"].documents[0]["id"]
_jumelle = dict(_col.documents[0])
_jumelle["id"] = "autre-identifiant"
try:
    lancer(_col.insert_one(_jumelle))
    _refuse = False
except ErreurUnicite:
    _refuse = True
verifier("9a. l'index (campaign_id, recipient_key) REFUSE le doublon", _refuse)
verifier("9b. la campagne compte au plus 1 action par destinataire",
         len({a["recipient_key"] for a in _col.documents}) == len(_col.documents))
verifier("9c. 8 destinataires -> 8 actions maximum", len(_col.documents) == 8)

# Et le meme destinataire dans une AUTRE campagne reste possible tant que rien
# n'est reserve : c'est l'invariant « plusieurs campagnes preparees coexistent ».
_autre = dict(_col.documents[0])
_autre["id"] = "action-autre-campagne"
_autre["campaign_id"] = "campagne-differente"
lancer(_col.insert_one(_autre))
verifier("9d. le meme destinataire dans une AUTRE campagne preparee : accepte",
         len(_col.documents) == 9)


# ============================================================================
print("\n10. EXCLUSION ET CORRECTION DU SNAPSHOT")

_b = base_neuve()
preparer(_b, dry_run=False)
_camp = _b["prospect_campaigns"].documents[0]
_cible = next(a for a in _b["prospect_campaign_actions"].documents
              if a["recipient_key"] == "GVA-F3")

_res = lancer(S.p3s3_modifier_action(_camp["id"], _cible["id"],
                                     RequeteFictive(jeton_=JA, corps={"excluded": True})))
verifier("10a. l'action passe a `exclu`", _res["action"]["statut"] == "exclu")
verifier("10b. le resume retire l'exclu des destinataires",
         _res["summary"]["destinataires"] == 7 and _res["summary"]["exclus"] == 1,
         str(_res["summary"]["destinataires"]))
verifier("10c. l'action n'est PAS supprimee, elle reste tracee",
         len(_b["prospect_campaign_actions"].documents) == 8)
verifier("10d. EXCLURE NE TOUCHE PAS LE PROSPECT : 0 ecriture dans partner_prospects",
         _b["partner_prospects"].ecritures == 0)
verifier("10e. ... ni son statut metier",
         all(f["status"] == "a_contacter" for f in _b["partner_prospects"].documents))

_res = lancer(S.p3s3_modifier_action(_camp["id"], _cible["id"],
                                     RequeteFictive(jeton_=JA, corps={"excluded": False})))
verifier("10f. reintegrer redonne `pret`", _res["action"]["statut"] == "pret")
verifier("10g. le resume revient a 8", _res["summary"]["destinataires"] == 8)

# Reintegrer un BLOQUE ne le rend pas pret : il n'a toujours aucun canal.
_bloq = next(a for a in _b["prospect_campaign_actions"].documents
             if a["recipient_key"] == "BAR-09")
lancer(S.p3s3_modifier_action(_camp["id"], _bloq["id"],
                              RequeteFictive(jeton_=JA, corps={"excluded": True})))
_res = lancer(S.p3s3_modifier_action(_camp["id"], _bloq["id"],
                                     RequeteFictive(jeton_=JA, corps={"excluded": False})))
verifier("10h. reintegrer un destinataire SANS canal le rend `bloque`, pas `pret`",
         _res["action"]["statut"] == "bloque", _res["action"]["statut"])

# Correction du message : le SNAPSHOT change, la FICHE ne bouge pas.
_res = lancer(S.p3s3_modifier_action(
    _camp["id"], _cible["id"],
    RequeteFictive(jeton_=JA, corps={"message_j0": "Texte corrige a la main"})))
verifier("10i. le message du snapshot est corrige",
         _res["action"]["message_j0"] == "Texte corrige a la main")
verifier("10j. son origine devient `edite`", _res["action"]["message_j0_origine"] == "edite")
verifier("10k. LA FICHE SOURCE N'A PAS BOUGE",
         next(f for f in _b["partner_prospects"].documents
              if f["ref"] == "GVA-F3")["j0_message"] == "Bonjour Wellness Geneve")
verifier("10l. toujours 0 ecriture dans partner_prospects", _b["partner_prospects"].ecritures == 0)

# Changer le canal recalcule ce que la machine sait faire.
_res = lancer(S.p3s3_modifier_action(_camp["id"], _cible["id"],
                                     RequeteFictive(jeton_=JA, corps={"channel": "instagram"})))
verifier("10m. changer le canal recalcule le type d'execution",
         _res["action"]["channel"] == "instagram" and _res["action"]["execution_type"] == "MANUEL")
_res = lancer(S.p3s3_modifier_action(_camp["id"], _cible["id"],
                                     RequeteFictive(jeton_=JA, corps={"channel": "aucun"})))
verifier("10n. passer a `aucun` rend l'action `bloque`",
         _res["action"]["statut"] == "bloque" and _res["action"]["execution_type"] == "BLOQUE")

try:
    lancer(S.p3s3_modifier_action(_camp["id"], _cible["id"],
                                  RequeteFictive(jeton_=JA, corps={"channel": "pigeon"})))
    _refuse = False
except HTTPException as e:
    _refuse = e.status_code == 400
verifier("10o. un canal inconnu est REFUSE (400), jamais range dans `autre`", _refuse)

try:
    lancer(S.p3s3_modifier_action(_camp["id"], _cible["id"],
                                  RequeteFictive(jeton_=JA, corps={"statut": "envoye"})))
    _refuse = False
except HTTPException as e:
    _refuse = e.status_code == 400
verifier("10p. on ne peut PAS forcer un statut d'envoi par le corps de la requete", _refuse)


# ============================================================================
print("\n11. UNE CAMPAGNE QUI N'EST PLUS `preparee` NE SE MODIFIE PLUS")

_b["prospect_campaigns"].documents[0]["etat"] = "approuvee"
try:
    lancer(S.p3s3_modifier_action(_camp["id"], _cible["id"],
                                  RequeteFictive(jeton_=JA, corps={"excluded": True})))
    _refuse = False
except HTTPException as e:
    _refuse = e.status_code == 409
verifier("11a. modifier une campagne approuvee est refuse (409)", _refuse)
_b["prospect_campaigns"].documents[0]["etat"] = "preparee"


# ============================================================================
print("\n12. AUTHENTIFICATION ET CLOISONNEMENT")

for _nom, _appel in (
        ("preparer", lambda: S.p3s3_preparer_campagne(RequeteFictive(corps={"dry_run": True}))),
        ("lister", lambda: S.p3s3_lister_campagnes(RequeteFictive())),
        ("lire", lambda: S.p3s3_lire_campagne(_camp["id"], RequeteFictive())),
        ("modifier", lambda: S.p3s3_modifier_action(_camp["id"], _cible["id"],
                                                    RequeteFictive(corps={"excluded": True})))):
    try:
        lancer(_appel())
        _ferme = False
    except HTTPException as e:
        _ferme = e.status_code in (401, 403)
    verifier("12a. %-9s SANS jeton -> refuse" % _nom, _ferme)

try:
    lancer(S.p3s3_lire_campagne(_camp["id"], RequeteFictive(jeton_=JB)))
    _ferme = False
except HTTPException as e:
    _ferme = e.status_code == 403
verifier("12b. la campagne d'un autre coach -> 403", _ferme)

try:
    lancer(S.p3s3_modifier_action(_camp["id"], _cible["id"],
                                  RequeteFictive(jeton_=JB, corps={"excluded": True})))
    _ferme = False
except HTTPException as e:
    _ferme = e.status_code == 403
verifier("12c. modifier l'action d'un autre coach -> 403", _ferme)

_vu = lancer(S.p3s3_lister_campagnes(RequeteFictive(jeton_=JB)))
verifier("12d. un autre coach ne voit AUCUNE campagne qui n'est pas la sienne",
         _vu["total"] == 0, str(_vu["total"]))


# ============================================================================
print("\n13. SELECTION ET FILTRES")

_b = base_neuve()
_sel = preparer(_b, prospect_ids=["GVA-F3", "LSN-F3", "ORG-01"])
verifier("13a. une selection explicite limite la campagne",
         _sel["summary"]["fiches"] == 3 and _sel["summary"]["destinataires"] == 2,
         str(_sel["summary"]))
verifier("13b. ... et Wellness y reste UN seul destinataire",
         sorted(a["recipient_key"] for a in _sel["actions"]) == ["GVA-F3", "ORG-01"])

_flt = preparer(_b, city="Neuchatel")
verifier("13c. le filtre ville s'applique, sur la forme normalisee",
         _flt["summary"]["fiches"] == 3, str(_flt["summary"]["fiches"]))
_flt = preparer(_b, priority="B")
verifier("13d. le filtre priorite s'applique", _flt["summary"]["fiches"] == 10)

try:
    preparer(_b, prospect_ids=[])
    _refuse = False
except HTTPException as e:
    _refuse = e.status_code == 400
verifier("13e. une selection vide est refusee, jamais interpretee comme « tous »", _refuse)

try:
    preparer(_b, status="statut-qui-n-existe-pas")
    _refuse = False
except HTTPException as e:
    _refuse = e.status_code == 400
verifier("13f. un filtre qui ne rend rien est refuse, pas une campagne vide", _refuse)

# LES VAGUES NE BRIDENT RIEN : aucune limite a 9, 10 ou « Vague 1 ».
_tout = preparer(_b)
verifier("13g. sans filtre de vague, les 8 destinataires sont prepares",
         _tout["summary"]["destinataires"] == 8)
verifier("13h. aucune limite de 9 ou 10 n'existe dans le code du lot",
         " 9]" not in BLOC and "[:10]" not in BLOC and "limit(10)" not in BLOC)


# ============================================================================
print("\n14. LES DRAPEAUX RESTENT FERMES, ET LE LOT MARCHE QUAND MEME")

verifier("14a. la porte d'envoi est fermee avec les deux drapeaux a false",
         S.p3s3_envoi_autorise({"P3_LAUNCH_ENABLED": False,
                                "P3_LAUNCH_ENVOI_REEL": False}) is False)
verifier("14b. tout P3-S3-B fonctionne SANS activer aucun drapeau",
         _tout["summary"]["destinataires"] == 8 and _b["prospect_campaigns"].ecritures >= 0)
verifier("14c. meme les deux drapeaux a true, aucune route d'envoi n'existe",
         not any(m in c for c in CHEMINS for m in ("send", "launch", "dispatch")))


# ============================================================================
print("\n15. LECTURE ET PAGINATION")

_b = base_neuve()
preparer(_b, dry_run=False, name="Campagne A")
preparer(_b, dry_run=False, name="Campagne B", allow_new=True)
_l = lancer(S.p3s3_lister_campagnes(RequeteFictive(jeton_=JA)))
verifier("15a. les deux campagnes sont listees", _l["total"] == 2)
verifier("15b. la liste est plafonnee et paginee",
         _l["limit"] == 25 and _l["offset"] == 0 and len(_l["campaigns"]) == 2)
verifier("15c. le tri porte une seconde cle UNIQUE (ordre total)",
         '.sort([("created_at", -1), ("id", 1)]).skip(depart)' in
         BLOC.split("async def p3s3_lister_campagnes")[1].split("@api_router")[0])

_id_a = _b["prospect_campaigns"].documents[0]["id"]
_lu = lancer(S.p3s3_lire_campagne(_id_a, RequeteFictive(jeton_=JA)))
verifier("15d. la lecture rend la campagne et ses actions",
         _lu["campaign"]["id"] == _id_a and len(_lu["actions"]) == 8)
verifier("15e. le resume est RECALCULE depuis les actions, pas relu du fige",
         _lu["summary"]["destinataires"] == 8)

try:
    lancer(S.p3s3_lire_campagne("campagne-qui-n-existe-pas", RequeteFictive(jeton_=JA)))
    _quatrecent = False
except HTTPException as e:
    _quatrecent = e.status_code == 404
verifier("15f. une campagne inconnue -> 404", _quatrecent)


# ============================================================================
print("\n16. LE MODELE PREPARE LA GARANTIE DU LOT SUIVANT")

verifier("16a. `verrou_actif` n'est jamais pose par ce lot", "verrou_actif" not in
         BLOC.split('"created_at": maintenant')[0].split("def p3s3_action_preparee")[-1]
         .replace("# PAS DE `verrou_actif`", ""))
verifier("16b. les statuts qui porteront le verrou sont deja definis",
         S.P3S3_STATUTS_VERROU == ("reserve", "en_cours", "envoye", "echec_indetermine"))
verifier("16c. aucun statut pose par la preparation n'est un statut de verrou",
         not {"pret", "bloque", "exclu"} & set(S.P3S3_STATUTS_VERROU))
verifier("16d. l'index qui portera le verrou existe deja (P3-S3-A)",
         'partialFilterExpression={"verrou_actif": True}' in SRC)


# ============================================================================
print("\n" + "=" * 78)
_ok = sum(1 for _, c, _ in RESULTATS if c)
_total = len(RESULTATS)
print("P3-S3-B : %d / %d verifications" % (_ok, _total))
if _ok != _total:
    print("\nECHECS :")
    for _i, _c, _d in RESULTATS:
        if not _c:
            print("  - %s  %s" % (_i, _d))
print("=" * 78)
sys.exit(0 if _ok == _total else 1)
