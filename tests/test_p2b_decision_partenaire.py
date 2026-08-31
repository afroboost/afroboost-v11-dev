#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2-B — ACCEPTER OU REFUSER UNE CANDIDATURE PARTENAIRE.

CE QUE LE LOT AJOUTE
==============================================================================
`PATCH /api/partner-applications/{lead_id}/decision`. Bassi tranche a la main.

  REFUS      -> `application_decision = rejected` + `rejected_at`/`rejected_by`.
                AUCUN slug, AUCUNE entite `partners`.
  ACCEPTATION-> `application_decision = accepted` + `accepted_at`/`accepted_by`
                ET exactement UN document `partners`, `partner_status`
                = "decouverte", avec un `partner_slug` unique.

DEUX NOTIONS QUI NE SE MELANGENT JAMAIS : `application_decision` est l'etat d'un
DOSSIER et vit sur le LEAD ; `partner_status` est la vie OPERATIONNELLE d'un
partenaire et vit sur `partners`. Un lead est une soumission — il en existe deja
des doublons en base ; un partenaire est une entite durable.

CE QUE CE FICHIER PROUVE, ET COMMENT
==============================================================================
La base est un BOUCHON TRANSACTIONNEL : `start_transaction` prend un instantane
de chaque collection, `abort_transaction` le restaure. Sans cela, on ne pourrait
pas prouver le point le plus important du lot — QU'IL N'EXISTE AUCUNE ECRITURE
PARTIELLE. Le bouchon simule aussi les INDEX UNIQUES (`partner_slug`,
`lead_id`) en levant `DuplicateKeyError`, parce que c'est l'index, et non le
code Python, qui ferme le cas concurrent.

AUCUNE ECRITURE EN PRODUCTION. Les 6 candidatures reelles ne sont pas touchees :
tout se joue sur des documents fictifs, en memoire.

LE PIEGE QUE CE FICHIER GARDE OUVERT
==============================================================================
`DuplicateKeyError` n'est importe NULLE PART au niveau module de `server.py` —
le seul import existant est local a une autre fonction. Sans import local dans
la route, le `except DuplicateKeyError` leverait un `NameError`, avale par le
`except Exception` general : une collision de slug reviendrait en 500 « rien n'a
ete modifie » au lieu du 409 « ce slug est deja utilise ». Une verification
dediee (section 7) surveille cet import.

    python3 tests/test_p2b_decision_partenaire.py
"""
import ast
import asyncio
import copy
import os
import re
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
SECRET_FICTIF = "secret-de-test-p2b-sans-aucun-rapport-avec-la-production"
ADMIN_FICTIF = "admin.fictif@exemple.test"
COACH_FICTIF = "coach.fictif@exemple.test"
AUTRE_COACH_FICTIF = "autre.coach.fictif@exemple.test"
MEMBRE_FICTIF = "membre.fictif@exemple.test"

os.environ["JWT_SECRET"] = SECRET_FICTIF
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-inexistant:27017")

import jwt as pyjwt  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from pymongo.errors import DuplicateKeyError  # noqa: E402


def _jeton(payload, minutes=60):
    m = datetime.now(timezone.utc)
    c = dict(payload)
    c["iat"] = int(m.timestamp())
    c["exp"] = int((m + timedelta(minutes=minutes)).timestamp())
    j = pyjwt.encode(c, SECRET_FICTIF, algorithm="HS256")
    return j.decode("utf-8") if isinstance(j, bytes) else j


JETON_ADMIN = _jeton({"email": ADMIN_FICTIF, "role": "super_admin"})
JETON_COACH = _jeton({"email": COACH_FICTIF, "role": "coach"})
JETON_AUTRE = _jeton({"email": AUTRE_COACH_FICTIF, "role": "coach"})
JETON_ABONNE = _jeton({"type": "subscriber", "code": "AFR-T", "email": MEMBRE_FICTIF})
JETON_ESPACE = _jeton({"type": "subscriber_space", "code": "AFR-T", "email": MEMBRE_FICTIF,
                       "coach_id": COACH_FICTIF, "slug": "s", "jti": "j"})
JETON_MAUVAIS = pyjwt.encode(
    {"email": ADMIN_FICTIF, "role": "super_admin",
     "exp": int((datetime.now(timezone.utc) + timedelta(minutes=60)).timestamp())},
    "un-autre-secret", algorithm="HS256")
if isinstance(JETON_MAUVAIS, bytes):
    JETON_MAUVAIS = JETON_MAUVAIS.decode("utf-8")


class RequeteFictive:
    def __init__(self, jeton=None, entete=None, corps=None):
        e = {}
        if jeton:
            e["Authorization"] = "Bearer " + jeton
        if entete:
            e["X-User-Email"] = entete
        self.headers = e
        self._corps = corps if corps is not None else {}

    async def json(self):
        return self._corps


class Curseur:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n):
        return list(self._docs)[:n]

    def __aiter__(self):
        self._i = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._i)
        except StopIteration:
            raise StopAsyncIteration


class CollectionBouchon:
    """Honore les filtres, COMPTE les ecritures, simule les INDEX UNIQUES.

    L'index unique n'est pas un detail de confort : c'est LUI qui ferme le cas
    de deux transactions concurrentes inserant le meme slug, que la lecture en
    transaction ne peut pas voir. Le simuler ici est la seule facon de prouver
    que la route traite correctement le `DuplicateKeyError`.
    """

    def __init__(self, documents=None, uniques=()):
        self.documents = [dict(d) for d in (documents or [])]
        self.uniques = tuple(uniques)
        self.ecritures = 0

    def _ok(self, doc, filtre):
        for cle, val in (filtre or {}).items():
            if str(cle).startswith("$"):
                continue
            if isinstance(val, dict):
                if "$nin" in val and doc.get(cle) in val["$nin"]:
                    return False
                if "$in" in val and doc.get(cle) not in val["$in"]:
                    return False
                if "$exists" in val and (cle in doc) != val["$exists"]:
                    return False
                continue
            if doc.get(cle) != val:
                return False
        return True

    async def find_one(self, filtre=None, projection=None, session=None, *a, **k):
        for d in self.documents:
            if self._ok(d, filtre):
                return dict(d)
        return None

    def find(self, filtre=None, projection=None, session=None, *a, **k):
        return Curseur([dict(d) for d in self.documents if self._ok(d, filtre)])

    def _verifier_uniques(self, doc, sauf=None):
        for cle in self.uniques:
            if cle not in doc:
                continue
            for autre in self.documents:
                if autre is sauf:
                    continue
                if autre.get(cle) == doc.get(cle):
                    raise DuplicateKeyError("index unique %s" % cle)

    async def insert_one(self, doc, session=None, *a, **k):
        self._verifier_uniques(doc)
        self.ecritures += 1
        self.documents.append(dict(doc))
        return None

    async def find_one_and_update(self, filtre, maj, session=None, *a, **k):
        """ATOMIQUE, comme en base : le filtre et l'ecriture ne se separent pas."""
        for d in self.documents:
            if self._ok(d, filtre):
                avant = dict(d)
                d.update(maj.get("$set") or {})
                for cle, val in (maj.get("$push") or {}).items():
                    d.setdefault(cle, []).append(val)
                self.ecritures += 1
                return avant
        return None

    async def update_one(self, *a, **k):
        self.ecritures += 1
        return None


class SessionBouchon:
    """Transaction a instantane : `abort` restaure l'etat d'avant."""

    def __init__(self, base):
        self.base = base
        self.instantane = None

    def start_transaction(self):
        self.instantane = self.base.instantane()

    async def commit_transaction(self):
        self.instantane = None

    async def abort_transaction(self):
        if self.instantane is not None:
            self.base.restaurer(self.instantane)
            self.instantane = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class ClientBouchon:
    def __init__(self, base):
        self.base = base

    async def start_session(self):
        return SessionBouchon(self.base)


class BaseBouchon:
    def __init__(self, leads, liens, partners=()):
        self.leads = CollectionBouchon(leads)
        self.chat_sessions = CollectionBouchon(liens)
        # LES DEUX INDEX UNIQUES DU LOT, tels qu'ils devront exister en base.
        self.partners = CollectionBouchon(partners, uniques=("partner_slug", "lead_id"))
        self.coaches = CollectionBouchon([{"email": COACH_FICTIF},
                                          {"email": AUTRE_COACH_FICTIF}])
        self.coach_auth = CollectionBouchon([])
        self.client = ClientBouchon(self)

    def _cols(self):
        return (self.leads, self.chat_sessions, self.partners)

    def instantane(self):
        return [copy.deepcopy(c.documents) for c in self._cols()]

    def restaurer(self, instantane):
        for col, docs in zip(self._cols(), instantane):
            col.documents = copy.deepcopy(docs)

    def __getattr__(self, nom):
        return CollectionBouchon([])


LIENS = [
    {"link_token": "tok_p", "title": "Partenaire (fictif)", "lead_type": "partner",
     "coach_id": COACH_FICTIF},
    {"link_token": "tok_autre", "title": "Autre coach", "lead_type": "partner",
     "coach_id": AUTRE_COACH_FICTIF},
    {"link_token": "tok_part", "title": "Essai (fictif)", "lead_type": "participant",
     "coach_id": COACH_FICTIF},
]


def leads_neufs():
    return [
        {"id": "lead-a", "link_token": "tok_p", "name": "Akoko Tresses",
         "email": "a@exemple.test", "whatsapp": "+41000000001",
         "answers": {"q_0": {"question": "Activite ?", "answer": "Salon"}},
         "created_at": "2026-08-20T10:00:00+00:00"},
        {"id": "lead-b", "link_token": "tok_p", "name": "Récif Neuchâtel",
         "email": "b@exemple.test", "whatsapp": "+41000000002",
         "answers": {"q_0": {"question": "Activite ?", "answer": "Bar"}},
         "created_at": "2026-08-21T10:00:00+00:00"},
        {"id": "lead-voisin", "link_token": "tok_autre", "name": "Voisin",
         "email": "v@exemple.test", "whatsapp": "+41000000009", "answers": {},
         "created_at": "2026-08-22T10:00:00+00:00"},
        {"id": "lead-participant", "link_token": "tok_part", "name": "Participant",
         "email": "p@exemple.test", "whatsapp": "+41000000003", "answers": {},
         "created_at": "2026-08-23T10:00:00+00:00"},
    ]


import api.server as S  # noqa: E402

S.SUPER_ADMIN_EMAILS = [ADMIN_FICTIF]

try:
    asyncio.set_event_loop(asyncio.new_event_loop())
except Exception:
    pass


def neuf(partners=()):
    S.db = BaseBouchon(leads_neufs(), LIENS, partners)
    return S.db


def decider(jeton=None, entete=None, lead="lead-a", decision="accepted", slug=None):
    corps = {"decision": decision}
    if slug is not None:
        corps["partner_slug"] = slug
    coro = S.p2b_decider_candidature(lead, RequeteFictive(jeton, entete, corps))
    try:
        return 200, asyncio.get_event_loop().run_until_complete(coro)
    except S.HTTPException as e:
        return e.status_code, getattr(e, "detail", "")


# ============================================================================
print("=" * 78)
print("P2-B — DECISION SUR UNE CANDIDATURE PARTENAIRE")
print("=" * 78)

print("\n=== 1. LA PORTE REFUSE ===")

for intitule, jeton, entete in [
    ("1a. anonyme -> 403", None, None),
    ("1b. `X-User-Email` d'un admin, forge -> 403", None, ADMIN_FICTIF),
    ("1c. `X-User-Email` du proprietaire, forge -> 403", None, COACH_FICTIF),
    ("1d. JWT d'un autre secret -> 403", JETON_MAUVAIS, None),
    ("1e. jeton ABONNE -> 403", JETON_ABONNE, None),
    ("1f. jeton d'ESPACE ABONNE -> 403", JETON_ESPACE, None),
]:
    neuf()
    statut, _ = decider(jeton, entete, slug="akoko_tresses")
    verifier(intitule, statut == 403 and not S.db.partners.documents,
             "statut=%s partners=%d" % (statut, len(S.db.partners.documents)))

neuf()
statut, _ = decider(JETON_AUTRE, slug="akoko_tresses")
verifier("1g. un AUTRE coach ne decide pas sur le lien du proprietaire -> 403",
         statut == 403 and not S.db.partners.documents, "statut=%s" % statut)

neuf()
statut, _ = decider(JETON_COACH, lead="lead-voisin", slug="voisin_x")
verifier("1h. ... et la reciproque est vraie -> 403", statut == 403, "statut=%s" % statut)

neuf()
statut, _ = decider(JETON_COACH, lead="lead-inconnu", slug="x_y_z")
verifier("1i. lead inconnu -> 404", statut == 404, "statut=%s" % statut)

neuf()
statut, detail = decider(JETON_COACH, lead="lead-participant", slug="participant_x")
verifier("1j. lead d'un lien NON partenaire -> 404 (jamais accepte par cette route)",
         statut == 404 and not S.db.partners.documents,
         "statut=%s partners=%d" % (statut, len(S.db.partners.documents)))

neuf()
statut, _ = decider(JETON_COACH, decision="peut_etre", slug="x_y_z")
verifier("1k. decision inconnue -> 400", statut == 400, "statut=%s" % statut)


print("\n=== 2. LE REFUS ===")

neuf()
statut, rep = decider(JETON_COACH, decision="rejected")
lead = S.db.leads.documents[0]
verifier("2a. refus accepte SANS slug", statut == 200 and rep.get("success"),
         "statut=%s" % statut)
verifier("2b. `application_decision` = rejected", lead.get("application_decision") == "rejected")
verifier("2c. `rejected_at` et `rejected_by` sont ecrits",
         bool(lead.get("rejected_at")) and lead.get("rejected_by") == COACH_FICTIF)
verifier("2d. AUCUN champ d'acceptation n'est pose",
         "accepted_at" not in lead and "accepted_by" not in lead)
verifier("2e. AUCUNE entite partners creee", len(S.db.partners.documents) == 0)
verifier("2f. AUCUN slug rendu", rep.get("partner_slug") is None)
verifier("2g. `decision_history` compte exactement une trace",
         len(lead.get("decision_history") or []) == 1
         and lead["decision_history"][0]["decision"] == "rejected"
         and lead["decision_history"][0]["by"] == COACH_FICTIF)


print("\n=== 3. L'ACCEPTATION ===")

neuf()
statut, rep = decider(JETON_COACH, slug="akoko_tresses")
lead = S.db.leads.documents[0]
verifier("3a. acceptation acceptee", statut == 200 and rep.get("success"), "statut=%s" % statut)
verifier("3b. `application_decision` = accepted", lead.get("application_decision") == "accepted")
verifier("3c. `accepted_at` et `accepted_by` sont ecrits",
         bool(lead.get("accepted_at")) and lead.get("accepted_by") == COACH_FICTIF)
verifier("3d. EXACTEMENT un partenaire cree", len(S.db.partners.documents) == 1)

p = S.db.partners.documents[0]
verifier("3e. `partner_status` initial = decouverte", p.get("partner_status") == "decouverte")
verifier("3f. le partenaire pointe le lead et le coach",
         p.get("lead_id") == "lead-a" and p.get("coach_id") == COACH_FICTIF)
verifier("3g. le slug est celui demande", p.get("partner_slug") == "akoko_tresses")
verifier("3h. le lien d'origine est conserve", p.get("source_link_token") == "tok_p")
verifier("3i. instantane d'identite present, `answers` NON recopie",
         p.get("name") == "Akoko Tresses" and "answers" not in p)
verifier("3j. `created_by` = identite signee", p.get("created_by") == COACH_FICTIF)
verifier("3k. la reponse rend slug et statut",
         rep.get("partner_slug") == "akoko_tresses" and rep.get("partner_status") == "decouverte")

neuf()
statut, rep = decider(JETON_ADMIN, slug="akoko_tresses")
verifier("3l. le SUPER-ADMIN peut decider sans etre proprietaire",
         statut == 200 and len(S.db.partners.documents) == 1, "statut=%s" % statut)


print("\n=== 4. LE SLUG ===")

neuf()
statut, _ = decider(JETON_COACH, slug=None)
verifier("4a. acceptation SANS slug -> 400", statut == 400 and not S.db.partners.documents,
         "statut=%s" % statut)

for mauvais, quoi in [("ab", "trop court"), ("x" * 41, "trop long"),
                      ("akoko tresses", "espace"),
                      ("récif", "accent"), ("akoko-tresses", "tiret"),
                      ("akoko/tresses", "barre oblique"), ("", "vide"),
                      ("../../etc", "traversee de chemin")]:
    neuf()
    statut, _ = decider(JETON_COACH, slug=mauvais)
    verifier("4b. slug refuse (%s) -> 400" % quoi,
             statut == 400 and not S.db.partners.documents, "statut=%s" % statut)

neuf()
statut, rep = decider(JETON_COACH, slug="  AKOKO_Tresses  ")
# Les majuscules et les espaces de BORD sont normalises, jamais refuses : deux
# corrections sans ambiguite, dont le resultat reste reconnaissable par celui
# qui a tape. Un espace INTERNE, lui, est refuse (ci-dessus) — le corriger
# reviendrait a inventer un separateur a la place du coach.
verifier("4c. espaces de bord et majuscules sont NORMALISES, pas refuses",
         statut == 200 and rep.get("partner_slug") == "akoko_tresses",
         "statut=%s slug=%s" % (statut, rep.get("partner_slug")))

verifier("4d. AUCUN suffixe automatique dans le code de normalisation",
         S.p2b_slug_propre("akoko_tresses") == "akoko_tresses"
         and S.p2b_slug_propre("akoko tresses") == "")


print("\n=== 5. COLLISION, DOUBLE CLIC, ET AUCUNE ECRITURE PARTIELLE ===")

# Deux leads differents, MEME slug.
neuf()
statut1, _ = decider(JETON_COACH, lead="lead-a", slug="meme_slug")
statut2, detail2 = decider(JETON_COACH, lead="lead-b", slug="meme_slug")
verifier("5a. deux leads, meme slug : le second est refuse en 409",
         statut1 == 200 and statut2 == 409, "statut1=%s statut2=%s" % (statut1, statut2))
verifier("5b. ... et il n'existe QU'UN partenaire", len(S.db.partners.documents) == 1)
verifier("5c. ... le message est explicite", "déjà utilisé" in str(detail2), str(detail2))
_b = [d for d in S.db.leads.documents if d["id"] == "lead-b"][0]
verifier("5d. AUCUNE ECRITURE PARTIELLE : le lead refuse reste sans decision",
         "application_decision" not in _b and "accepted_at" not in _b
         and not _b.get("decision_history"),
         "lead-b = %s" % {k: v for k, v in _b.items() if k.startswith(("appl", "acce", "deci"))})

# Rejeu de la MEME decision.
neuf()
decider(JETON_COACH, slug="akoko_tresses")
statut, rep = decider(JETON_COACH, slug="akoko_tresses")
lead = S.db.leads.documents[0]
verifier("5e. rejeu de la MEME decision -> 200 idempotent",
         statut == 200 and rep.get("already") is True, "statut=%s rep=%s" % (statut, rep))
verifier("5f. ... toujours UN seul partenaire", len(S.db.partners.documents) == 1)
verifier("5g. ... `decision_history` ne gagne AUCUNE ligne",
         len(lead.get("decision_history") or []) == 1,
         "%d lignes" % len(lead.get("decision_history") or []))
verifier("5h. ... le rejeu rend le slug existant", rep.get("partner_slug") == "akoko_tresses")

# Double clic SIMULTANE sur le meme lead.
neuf()


async def _course():
    return await asyncio.gather(
        S.p2b_decider_candidature("lead-a", RequeteFictive(
            JETON_COACH, None, {"decision": "accepted", "partner_slug": "course_a"})),
        S.p2b_decider_candidature("lead-a", RequeteFictive(
            JETON_COACH, None, {"decision": "accepted", "partner_slug": "course_b"})),
        return_exceptions=True)


resultats = asyncio.get_event_loop().run_until_complete(_course())
_ok = [r for r in resultats if isinstance(r, dict)]
verifier("5i. double clic SIMULTANE : jamais deux partenaires",
         len(S.db.partners.documents) == 1,
         "partners=%d" % len(S.db.partners.documents))
verifier("5j. ... les deux appels aboutissent proprement (l'un cree, l'autre constate)",
         len(_ok) == 2 and sum(1 for r in _ok if r.get("already")) == 1,
         "reponses=%s" % [(r.get("already"), r.get("partner_slug")) for r in _ok])
verifier("5k. ... et une seule trace dans l'historique",
         len(S.db.leads.documents[0].get("decision_history") or []) == 1)


print("\n=== 6. UNE DECISION NE SE RENVERSE PAS ===")

neuf()
decider(JETON_COACH, slug="akoko_tresses")
statut, detail = decider(JETON_COACH, decision="rejected")
verifier("6a. accepted -> rejected refuse en 409", statut == 409, "statut=%s" % statut)
verifier("6b. ... le partenaire reste intact", len(S.db.partners.documents) == 1)
verifier("6c. ... le lead reste accepte",
         S.db.leads.documents[0].get("application_decision") == "accepted")

neuf()
decider(JETON_COACH, decision="rejected")
statut, _ = decider(JETON_COACH, decision="accepted", slug="akoko_tresses")
verifier("6d. rejected -> accepted refuse en 409", statut == 409, "statut=%s" % statut)
verifier("6e. ... AUCUN partenaire cree", len(S.db.partners.documents) == 0)
verifier("6f. ... le lead reste refuse",
         S.db.leads.documents[0].get("application_decision") == "rejected")

neuf()
decider(JETON_COACH, decision="rejected")
statut, rep = decider(JETON_COACH, decision="rejected")
verifier("6g. rejeu d'un refus -> 200 idempotent, historique inchange",
         statut == 200 and rep.get("already") is True
         and len(S.db.leads.documents[0].get("decision_history") or []) == 1,
         "statut=%s" % statut)


print("\n=== 7. LE CODE LIVRE DIT BIEN CE QU'ON CROIT ===")

SRC = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
ARBRE = ast.parse(SRC)
LIGNES = SRC.split("\n")


def _fonction(nom):
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == nom:
            return n
    raise AssertionError(nom)


def _code(nom):
    """Le CODE EXECUTE seul — docstring et commentaires retires, guillemets
    normalises. Sans cela, ce fichier se piegerait lui-meme : la docstring de la
    route cite `require_auth` et `X-User-Email` pour dire qu'elle ne les emploie
    PAS, et une recherche naive les trouverait dans l'explication."""
    f = _fonction(nom)
    corps = list(f.body)
    if (corps and isinstance(corps[0], ast.Expr)
            and isinstance(getattr(corps[0], "value", None), ast.Constant)
            and isinstance(corps[0].value.value, str)):
        corps = corps[1:]
    if not hasattr(ast, "unparse"):
        return "\n".join(l for l in LIGNES[f.lineno - 1:f.end_lineno]
                         if not l.strip().startswith("#")).replace("'", '"')
    return "\n".join(ast.unparse(n) for n in corps).replace("'", '"')


CODE = _code("p2b_decider_candidature")

verifier("7a. la garde est `_v309_require_coach_or_admin`",
         "await _v309_require_coach_or_admin(request)" in CODE)
verifier("7b. `require_auth` n'est PAS employe", not re.search(r"\brequire_auth\s*\(", CODE))
verifier("7c. aucune decision d'acces ne vient de `X-User-Email`", "X-User-Email" not in CODE)
verifier("7d. l'ecriture est TRANSACTIONNELLE",
         "start_session()" in CODE and "start_transaction()" in CODE
         and "commit_transaction()" in CODE and "abort_transaction()" in CODE)
verifier("7e. l'idempotence repose sur `find_one_and_update`, pas sur un `if`",
         "find_one_and_update" in CODE and '"$nin": list(P2B_DECISIONS)' in CODE)
verifier("7f. toutes les ecritures passent par la session transactionnelle",
         CODE.count("session=ses") >= 3, "trouve %d" % CODE.count("session=ses"))
verifier("7g. `DuplicateKeyError` est importe LOCALEMENT — sans quoi une "
         "collision reviendrait en 500 au lieu de 409",
         "from pymongo.errors import DuplicateKeyError" in CODE)
verifier("7h. `partner_status` demarre a « decouverte »", '"partner_status": "decouverte"' in CODE)
verifier("7i. `partner_status` n'est JAMAIS ecrit sur le lead",
         "partner_status" not in _code("p2b_decider_candidature").split("db.partners")[0])
verifier("7j. la propriete est verifiee AVANT le type (helper partage avec P2-A)",
         "_p2b_lien_et_proprietaire" in CODE)
_helper = _code("_p2b_lien_et_proprietaire")
verifier("7k. ... et dans le helper, coach_id vient bien avant lead_type",
         _helper.index('lien.get("coach_id")') < _helper.index('lien.get("lead_type")'))
verifier("7l. aucune regex Mongo sur une entree utilisateur", "$regex" not in CODE)
_slug_helper = _code("p2b_slug_propre")
verifier("7m. le slug est valide par un motif FERME, dans le helper dedie",
         "P2B_SLUG_MOTIF.match(slug)" in _slug_helper
         and "^[a-z0-9_]{3,40}$" in SRC)
verifier("7m-bis. la route delegue au helper, elle ne revalide pas a sa facon",
         "p2b_slug_propre(" in CODE)
verifier("7m-ter. le helper n'ajoute AUCUN suffixe et ne remplace aucun "
         "caractere interdit — il refuse",
         "+" not in _slug_helper.replace("+ ", "") .replace("re.compile", "")
         or "return slug if" in _slug_helper)

LECTURE = _code("p2a_candidatures_partenaire")
verifier("7n. la lecture P2-A JOINT le slug, sans le recopier sur le lead",
         "db.partners.find(" in LECTURE and '"$in": _acceptes' in LECTURE)
verifier("7o. ... par UNE lecture groupee, jamais un find_one par candidature",
         LECTURE.count("db.partners.find_one") == 0)


print("\n=== 8. LE FRONT ===")

APP = open(os.path.join(RACINE, "frontend", "src", "components", "coach",
                        "PartnerApplications.js"), encoding="utf-8").read()
SW = open(os.path.join(RACINE, "frontend", "public", "sw.js"), encoding="utf-8").read()


def _code_js(source):
    sans = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return "\n".join(l for l in sans.split("\n") if not l.strip().startswith("//"))


APPC = _code_js(APP)

verifier("8a. la decision part en axios.patch", "axios.patch(" in APPC)
verifier("8b. l'URL est celle de la route, et l'identifiant est encode",
         "/partner-applications/${encodeURIComponent(item.id)}/decision" in APPC)
verifier("8c. aucun `fetch` nu", "fetch(" not in APPC)
verifier("8d. la logique du jeton n'est pas recopiee",
         "afroboost_jwt" not in APPC and "Authorization" not in APPC)
verifier("8e. les boutons n'existent que pour une candidature EN ATTENTE",
         "enAttente && onDecider" in APPC)
verifier("8f. le slug est PROPOSE puis modifiable",
         "p2bSuggererSlug(item.name)" in APPC and "onChange={(e) => setSlug(e.target.value)}" in APPC)
# P2-C a deplace la regle du slug dans `utils/partnerLink.js`, avec la
# construction du lien : UNE seule regle, un seul endroit, partagee par les deux
# lots. L'assertion suit le code plutot que de figer un emplacement — et elle
# devient plus forte, puisqu'elle prouve la source unique.
LIEN_UTIL = open(os.path.join(RACINE, "frontend", "src", "utils",
                              "partnerLink.js"), encoding="utf-8").read()
verifier("8g. le format du slug est verifie AVANT l'appel, avec la MEME regle "
         "que le serveur",
         "p2bSlugValide(slug)" in APPC
         and "from '../../utils/partnerLink'" in APPC
         and "^[a-z0-9_]{3,40}$" in LIEN_UTIL)
verifier("8g-bis. la regle du slug n'existe QU'A UN endroit cote navigateur",
         "[a-z0-9_]{3,40}" not in APPC,
         "le motif est recopie dans le composant — deux regles finiraient par "
         "diverger")
verifier("8h. l'ecran previent que le slug est definitif",
         "ne pourra plus être modifié après l'acceptation" in APP)
verifier("8i. le refus demande une confirmation", "Confirmer le refus" in APPC)
verifier("8j. un envoi en cours desactive les boutons (double clic sans effet)",
         "disabled={enCours}" in APPC or "disabled: enCours" in APPC)
verifier("8k. apres succes, la liste est RECHARGEE depuis le serveur",
         "await charger();" in APPC.split("axios.patch")[1][:400])
# P2-C ajoute DELIBEREMENT le lien UTM et le QR sur une candidature acceptee.
# Ce qui reste hors perimetre jusqu'a P2-D, ce sont les statistiques.
verifier("8l. AUCUNE statistique dans ce lot (P2-D)",
         not re.search(r"\bclics\b|\bconversions\b|\btaux\b", APPC))
verifier("8m. le Service Worker est au moins en v470",
         bool(re.search(r"afroboost-v(\d+)", SW))
         and int(re.search(r"afroboost-v(\d+)", SW).group(1)) >= 470,
         re.search(r"afroboost-v(\d+)", SW).group(0))


print("\n" + "=" * 78)
_ok = sum(1 for _, c, _ in RESULTATS if c)
_total = len(RESULTATS)
print("P2-B — %d / %d verifications au vert" % (_ok, _total))
print("=" * 78)
if _ok != _total:
    print("\nECHECS :")
    for i, c, d in RESULTATS:
        if not c:
            print("  - %s%s" % (i, ("  [%s]" % d) if d else ""))
sys.exit(0 if _ok == _total else 1)
