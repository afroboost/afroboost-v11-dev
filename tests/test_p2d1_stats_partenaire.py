#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2-D1 — CE QU'UN PARTENAIRE A REELLEMENT APPORTE.

`GET /api/partners/{partner_slug}/stats`. Agregats seuls : des entiers et deux
taux. Aucune liste, aucune adresse, aucun code — la route existe precisement
pour que le navigateur n'ait jamais a recevoir les reservations des gens.

LES TROIS DEFINITIONS QUI FONT TOUT LE LOT, ET D'OU ELLES VIENNENT
==============================================================================

1. L'ATTRIBUTION EST `first`, avec les QUATRE criteres SIMULTANEMENT.
   La logique deployee (`utils/attribution.js`) fige `first` et ne remplace
   `last` que par une origine EXTERNE. Cas qui tranche : partenaire A ->
   Instagram -> reservation donne `first = A`, `last = instagram`. La question
   metier est « qui a AMENE cette personne », donc `first`.

2. LA PRESENCE EST `validated is True`, SEUL.
   C'est la convention de TOUT le depot (`server.py:28745`, `28812`,
   `shared.py:1271`, `1869`, `reservation_routes.py:1701`). `validatedAt` y sert
   de filtre de DATE (relances P1-d), jamais de preuve. Exiger les deux aurait
   cree ici une definition de la presence differente du reste du produit, pour
   aucun gain : en production les deux coincident (15 et 15).

3. PULSE ET MEMBRE SE LISENT SUR LES BOOLEENS DE L'OFFRE.
   `creates_membership` (l'offre qui fait ENTRER) et `requires_active_membership`
   (celle qui fait CONTINUER) — la regle deja ecrite dans `shared.py:2564`,
   `2599` : « jamais sur un nom, jamais sur un montant ». La production contient
   « PULSE x10 cours (Membres) » et « Cours a l'unite (copie) » : un filtre par
   libelle s'y briserait.

LE PIEGE QUE CE FICHIER SURVEILLE
==============================================================================
L'ESSAI GRATUIT CREE LUI-MEME UN ABONNEMENT — `🎁 Cours d'essai GRATUIT`
apparait 9 fois dans `subscriptions` en production. Compter naivement les
abonnements d'une personne venue par un partenaire donnerait 100 % de
conversion pour tout le monde, et le tableau serait faux des le premier
partenaire. La section 5 verifie que l'abonnement portant le code de la
reservation attribuee est bien ECARTE.

AUCUNE ECRITURE. La base est un bouchon qui COMPTE les ecritures ; le compteur
doit rester a zero. Aucune donnee de production n'est touchee.

    python3 tests/test_p2d1_stats_partenaire.py
"""
import ast
import asyncio
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
SECRET_FICTIF = "secret-de-test-p2d1-sans-aucun-rapport-avec-la-production"
ADMIN_FICTIF = "admin.fictif@exemple.test"
COACH_FICTIF = "coach.fictif@exemple.test"
AUTRE_COACH = "autre.coach.fictif@exemple.test"
MEMBRE_FICTIF = "membre.fictif@exemple.test"

os.environ["JWT_SECRET"] = SECRET_FICTIF
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-inexistant:27017")

import jwt as pyjwt  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402


def _jeton(payload, minutes=60):
    m = datetime.now(timezone.utc)
    c = dict(payload)
    c["iat"] = int(m.timestamp())
    c["exp"] = int((m + timedelta(minutes=minutes)).timestamp())
    j = pyjwt.encode(c, SECRET_FICTIF, algorithm="HS256")
    return j.decode("utf-8") if isinstance(j, bytes) else j


JETON_ADMIN = _jeton({"email": ADMIN_FICTIF, "role": "super_admin"})
JETON_COACH = _jeton({"email": COACH_FICTIF, "role": "coach"})
JETON_AUTRE = _jeton({"email": AUTRE_COACH, "role": "coach"})
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
    def __init__(self, jeton=None, entete=None):
        e = {}
        if jeton:
            e["Authorization"] = "Bearer " + jeton
        if entete:
            e["X-User-Email"] = entete
        self.headers = e


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
    """Honore les filtres imbriques (`a.b.c`), `$in` et `$or`. COMPTE les ecritures."""

    def __init__(self, documents=None):
        self.documents = [dict(d) for d in (documents or [])]
        self.ecritures = 0

    @staticmethod
    def _lire(doc, chemin):
        cour = doc
        for bout in chemin.split("."):
            if not isinstance(cour, dict):
                return None
            cour = cour.get(bout)
        return cour

    def _ok(self, doc, filtre):
        for cle, val in (filtre or {}).items():
            if cle == "$or":
                if not any(self._ok(doc, f) for f in val):
                    return False
                continue
            reel = self._lire(doc, cle)
            if isinstance(val, dict):
                if "$in" in val and reel not in val["$in"]:
                    return False
                if "$nin" in val and reel in val["$nin"]:
                    return False
                if "$exists" in val and (reel is not None) != val["$exists"]:
                    return False
                continue
            if reel != val:
                return False
        return True

    async def find_one(self, filtre=None, projection=None, *a, **k):
        for d in self.documents:
            if self._ok(d, filtre):
                return dict(d)
        return None

    def find(self, filtre=None, projection=None, *a, **k):
        return Curseur([dict(d) for d in self.documents if self._ok(d, filtre)])

    async def insert_one(self, *a, **k):
        self.ecritures += 1

    async def update_one(self, *a, **k):
        self.ecritures += 1

    async def delete_one(self, *a, **k):
        self.ecritures += 1

    async def find_one_and_update(self, *a, **k):
        self.ecritures += 1
        return None


# --- Le decor ---------------------------------------------------------------
SLUG = "akoko_tresses"
AUTRE_SLUG = "recif_neuchatel"

OFFRE_PULSE = "offre-pulse-fictive"
OFFRE_MEMBRE = "offre-membre-fictive"
OFFRE_ESSAI = "offre-essai-fictive"

OFFRES = [
    # Les DEUX booleens du depot, sur des offres dont le NOM ne dit rien d'utile :
    # si le code filtrait par libelle, ces tests le prendraient en flagrant delit.
    {"id": OFFRE_PULSE, "name": "Formule A (copie)", "creates_membership": True},
    {"id": OFFRE_MEMBRE, "name": "Formule B (copie)", "requires_active_membership": True},
    {"id": OFFRE_ESSAI, "name": "Essai fictif", "creates_membership": False},
]

PARTNERS = [
    {"id": "p1", "partner_slug": SLUG, "coach_id": COACH_FICTIF,
     "partner_status": "decouverte", "lead_id": "lead-a"},
    {"id": "p2", "partner_slug": AUTRE_SLUG, "coach_id": AUTRE_COACH,
     "partner_status": "decouverte", "lead_id": "lead-b"},
]


def attr(source=None, medium=None, campagne=None, contenu=None):
    return {"first": {"source": source, "medium": medium,
                      "campaign": campagne, "content": contenu}}


def res(rid, code=None, mail=None, valide=False, offre=None, attribution=None, **extra):
    d = {"id": rid, "reservationCode": "AFR-" + rid.upper(),
         "createdAt": "2026-08-20T10:00:00+00:00",
         "userEmail": mail, "discountCode": code, "validated": valide,
         "offerId": offre}
    if attribution is not None:
        d["attribution"] = attribution
    d.update(extra)
    return d


BON = attr("partenaire", "referral", "essai_neuchatel", SLUG)


def decor(reservations=None, subscriptions=None):
    class Base:
        def __init__(self):
            self.partners = CollectionBouchon(PARTNERS)
            self.offers = CollectionBouchon(OFFRES)
            self.reservations = CollectionBouchon(reservations or [])
            self.subscriptions = CollectionBouchon(subscriptions or [])
            self.coaches = CollectionBouchon([{"email": COACH_FICTIF}, {"email": AUTRE_COACH}])
            self.coach_auth = CollectionBouchon([])

        def __getattr__(self, n):
            return CollectionBouchon([])

        def ecritures(self):
            return sum(c.ecritures for c in (self.partners, self.offers, self.reservations,
                                             self.subscriptions, self.coaches, self.coach_auth))
    import api.server as S
    S.db = Base()
    return S.db


import api.server as S  # noqa: E402

S.SUPER_ADMIN_EMAILS = [ADMIN_FICTIF]

try:
    asyncio.set_event_loop(asyncio.new_event_loop())
except Exception:
    pass


def stats(jeton=JETON_COACH, entete=None, slug=SLUG):
    coro = S.p2d_stats_partenaire(slug, RequeteFictive(jeton, entete))
    try:
        return 200, asyncio.get_event_loop().run_until_complete(coro)
    except S.HTTPException as e:
        return e.status_code, getattr(e, "detail", "")


# ============================================================================
print("=" * 78)
print("P2-D1 — STATISTIQUES PARTENAIRE")
print("=" * 78)

print("\n=== 1. LA PORTE ===")

decor()
for intitule, jeton, entete in [
    ("1a. anonyme -> 403", None, None),
    ("1b. `X-User-Email` d'un admin, forge -> 403", None, ADMIN_FICTIF),
    ("1c. `X-User-Email` du proprietaire, forge -> 403", None, COACH_FICTIF),
    ("1d. JWT d'un autre secret -> 403", JETON_MAUVAIS, None),
    ("1e. jeton ABONNE -> 403", JETON_ABONNE, None),
    ("1f. jeton d'ESPACE ABONNE -> 403", JETON_ESPACE, None),
]:
    statut, _ = stats(jeton, entete)
    verifier(intitule, statut == 403, "statut=%s" % statut)

statut, _ = stats(JETON_AUTRE)
verifier("1g. un AUTRE coach ne lit pas les stats du partenaire -> 403",
         statut == 403, "statut=%s" % statut)
statut, _ = stats(JETON_COACH, slug=AUTRE_SLUG)
verifier("1h. ... et la reciproque est vraie -> 403", statut == 403, "statut=%s" % statut)
statut, _ = stats(JETON_COACH, slug="slug_inconnu")
verifier("1i. slug inconnu -> 404", statut == 404, "statut=%s" % statut)
statut, _ = stats(JETON_COACH, slug="x" * 200)
verifier("1j. slug absurdement long -> 404", statut == 404, "statut=%s" % statut)
statut, r = stats(JETON_COACH)
verifier("1k. le PROPRIETAIRE est autorise", statut == 200, "statut=%s" % statut)
statut, r = stats(JETON_ADMIN)
verifier("1l. le SUPER-ADMIN est autorise", statut == 200, "statut=%s" % statut)
verifier("1m. un partenaire n'est JAMAIS fabrique depuis un lead",
         'db.leads' not in ast.unparse(
             [n for n in ast.walk(ast.parse(open(os.path.join(RACINE, "api", "server.py"),
              encoding="utf-8").read()))
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "p2d_stats_partenaire"][0]))


print("\n=== 2. SEULES LES BONNES ATTRIBUTIONS COMPTENT ===")

decor([
    res("ok1", code="AFR-001", mail="a@exemple.test", attribution=BON),
    # Chacune de ces quatre casse UN critere, et un seul.
    res("ko-source", code="AFR-002", mail="b@exemple.test",
        attribution=attr("instagram", "referral", "essai_neuchatel", SLUG)),
    res("ko-medium", code="AFR-003", mail="c@exemple.test",
        attribution=attr("partenaire", "social", "essai_neuchatel", SLUG)),
    res("ko-campagne", code="AFR-004", mail="d@exemple.test",
        attribution=attr("partenaire", "referral", "autre_campagne", SLUG)),
    res("ko-contenu", code="AFR-005", mail="e@exemple.test",
        attribution=attr("partenaire", "referral", "essai_neuchatel", AUTRE_SLUG)),
    res("ko-aucune", code="AFR-006", mail="f@exemple.test"),
])
statut, r = stats()
verifier("2a. seules les reservations aux QUATRE criteres comptent",
         r["reservations"] == 1, "reservations=%s" % r.get("reservations"))

# `last` partenaire mais `first` autre : NE COMPTE PAS.
decor([
    res("last-seul", code="AFR-010", mail="g@exemple.test",
        attribution={"first": {"source": "instagram", "medium": "social",
                               "campaign": "essai_neuchatel", "content": SLUG},
                     "last": {"source": "partenaire", "medium": "referral",
                              "campaign": "essai_neuchatel", "content": SLUG}}),
])
statut, r = stats()
verifier("2b. `last` partenaire ne suffit PAS — seul `first` credite",
         r["reservations"] == 0, "reservations=%s" % r.get("reservations"))

# `first` partenaire et `last` Instagram : COMPTE (le cas qui a tranche la regle).
decor([
    res("first-part", code="AFR-011", mail="h@exemple.test",
        attribution={"first": {"source": "partenaire", "medium": "referral",
                               "campaign": "essai_neuchatel", "content": SLUG},
                     "last": {"source": "instagram", "medium": "social",
                              "campaign": "", "content": ""}}),
])
statut, r = stats()
verifier("2c. partenaire PUIS Instagram : le partenaire garde le credit",
         r["reservations"] == 1, "reservations=%s" % r.get("reservations"))

decor([res("autre", code="AFR-020", mail="i@exemple.test",
           attribution=attr("partenaire", "referral", "essai_neuchatel", AUTRE_SLUG))])
statut, r = stats()
verifier("2d. les donnees d'un AUTRE partenaire sont exclues",
         r["reservations"] == 0 and r["unique_people"] == 0)


print("\n=== 3. VRAIES RESERVATIONS ET PERSONNES UNIQUES ===")

# Le document parasite de production : une reponse d'API entiere, sans `id`,
# sans `reservationCode`, sans `createdAt`.
PARASITE = {"data": [], "pagination": {"page": 1}, "attribution": BON}

decor([
    res("r1", code="AFR-100", mail="mm@exemple.test", attribution=BON),
    res("r2", code="AFR-100", mail="mm@exemple.test", attribution=BON),
    res("r3", code="AFR-100", mail="MM@Exemple.Test ", attribution=BON),
    PARASITE,
])
statut, r = stats()
verifier("3a. le document parasite est EXCLU du comptage",
         r["reservations"] == 3, "reservations=%s" % r.get("reservations"))
verifier("3b. 3 reservations de la MEME personne = 1 personne unique",
         r["unique_people"] == 1, "unique_people=%s" % r.get("unique_people"))

decor([
    res("d1", code="AFR-200", mail="x@exemple.test", attribution=BON),
    res("d2", code="AFR-201", mail="x@exemple.test", attribution=BON),
])
statut, r = stats()
verifier("3c. `discountCode` est PRIORITAIRE : deux codes = deux personnes",
         r["unique_people"] == 2, "unique_people=%s" % r.get("unique_people"))

decor([
    res("e1", code=None, mail="  Y@Exemple.Test  ", attribution=BON),
    res("e2", code=None, mail="y@exemple.test", attribution=BON),
])
statut, r = stats()
verifier("3d. sans code, le repli est l'e-mail NORMALISE (casse et espaces)",
         r["unique_people"] == 1, "unique_people=%s" % r.get("unique_people"))

decor([
    res("u1", code="AFR-300", mail="z@exemple.test", attribution=BON, userId="uid-1"),
    res("u2", code="AFR-301", mail="z@exemple.test", attribution=BON, userId="uid-1"),
])
statut, r = stats()
verifier("3e. `userId` n'est JAMAIS requis (0/145 en production)",
         r["unique_people"] == 2 and "userId" not in str(r))
verifier("3f. la methode de deduplication est annoncee, sans valeur personnelle",
         r["unique_people_method"] == "discount_code_then_normalized_email")


print("\n=== 4. LA PRESENCE ===")

decor([
    res("p1", code="AFR-400", mail="p1@exemple.test", valide=True, attribution=BON,
        validatedAt="2026-08-21T10:00:00+00:00"),
    res("p2", code="AFR-401", mail="p2@exemple.test", valide=True, attribution=BON),
    res("p3", code="AFR-402", mail="p3@exemple.test", valide=False, attribution=BON,
        validatedAt="2026-08-21T10:00:00+00:00"),
    res("p4", code="AFR-403", mail="p4@exemple.test", valide=False, attribution=BON),
])
statut, r = stats()
verifier("4a. `validated: True` compte — la convention de TOUT le depot",
         r["attendances"] == 2, "attendances=%s" % r.get("attendances"))
verifier("4b. `validatedAt` SEUL, sans `validated`, ne compte PAS",
         r["attendances"] == 2)
verifier("4c. la definition employee est annoncee",
         r["attendance_definition"] == "validated_true")
verifier("4d. une reservation n'est PAS une presence par defaut",
         r["reservations"] == 4 and r["attendances"] == 2)


print("\n=== 5. LES CONVERSIONS, ET LE PIEGE DE L'ESSAI ===")

# La personne est venue par le partenaire (essai, code AFR-500), puis a achete
# un Pulse. L'abonnement de l'ESSAI porte le meme code que la reservation
# attribuee : il ne doit PAS compter.
decor(
    reservations=[
        res("es1", code="AFR-500", mail="conv@exemple.test", offre=OFFRE_ESSAI, attribution=BON),
        # L'achat qui suit, sur l'offre d'ENTREE (creates_membership).
        res("ac1", code="AFR-501", mail="conv@exemple.test", offre=OFFRE_PULSE),
    ],
    subscriptions=[
        {"code": "AFR-500", "email": "conv@exemple.test", "status": "active"},   # l'essai
        {"code": "AFR-501", "email": "conv@exemple.test", "status": "active"},   # l'achat
    ])
statut, r = stats()
verifier("5a. l'abonnement de l'ESSAI est ECARTE — sinon 100 % de conversion "
         "pour tout le monde",
         r["conversions"]["subscription"] == 1,
         "subscription=%s" % r["conversions"]["subscription"])
verifier("5b. Pulse est reconnu par `creates_membership`, jamais par le nom",
         r["conversions"]["pulse"] == 1, "pulse=%s" % r["conversions"]["pulse"])
verifier("5c. le TOTAL compte des PERSONNES, pas des lignes",
         r["conversions"]["total"] == 1, "total=%s" % r["conversions"]["total"])

# Membre : `requires_active_membership`.
decor(
    reservations=[
        res("es2", code="AFR-600", mail="m@exemple.test", offre=OFFRE_ESSAI, attribution=BON),
        res("ac2", code="AFR-601", mail="m@exemple.test", offre=OFFRE_MEMBRE),
    ],
    subscriptions=[{"code": "AFR-601", "email": "m@exemple.test", "status": "completed"}])
statut, r = stats()
verifier("5d. Membre est reconnu par `requires_active_membership`",
         r["conversions"]["member"] == 1, "member=%s" % r["conversions"]["member"])

# LE SCENARIO DU BRIEF : 3 reservations, 1 abonnement, 1 adhesion, meme personne.
decor(
    reservations=[
        res("t1", code="AFR-700", mail="tri@exemple.test", offre=OFFRE_ESSAI, attribution=BON),
        res("t2", code="AFR-700", mail="tri@exemple.test", offre=OFFRE_ESSAI, attribution=BON),
        res("t3", code="AFR-700", mail="tri@exemple.test", offre=OFFRE_ESSAI, attribution=BON),
        res("t4", code="AFR-701", mail="tri@exemple.test", offre=OFFRE_PULSE),
        res("t5", code="AFR-702", mail="tri@exemple.test", offre=OFFRE_MEMBRE),
    ],
    subscriptions=[
        {"code": "AFR-700", "email": "tri@exemple.test", "status": "active"},
        {"code": "AFR-701", "email": "tri@exemple.test", "status": "active"},
        {"code": "AFR-702", "email": "tri@exemple.test", "status": "superseded"},
    ])
statut, r = stats()
verifier("5e. 3 reservations, 1 personne", r["reservations"] == 3 and r["unique_people"] == 1,
         "res=%s pers=%s" % (r["reservations"], r["unique_people"]))
verifier("5f. presente dans TROIS categories, elle ne compte qu'UNE conversion",
         r["conversions"]["total"] == 1,
         "pulse=%s member=%s sub=%s total=%s" % (
             r["conversions"]["pulse"], r["conversions"]["member"],
             r["conversions"]["subscription"], r["conversions"]["total"]))
# LE DETAIL COMPTE DES PERSONNES, LUI AUSSI. Cette personne a DEUX abonnements
# post-essai (AFR-701 et AFR-702) : `subscription` vaut 1, pas 2. Faire compter
# des achats au detail et des personnes au total donnerait un tableau ou « 2
# abonnements » surplomberait « 1 conversion » — illisible.
verifier("5g. le detail par categorie compte des PERSONNES, comme le total",
         r["conversions"]["pulse"] == 1 and r["conversions"]["member"] == 1
         and r["conversions"]["subscription"] == 1,
         "pulse=%s member=%s sub=%s" % (r["conversions"]["pulse"],
                                        r["conversions"]["member"],
                                        r["conversions"]["subscription"]))
verifier("5g-bis. l'unite est annoncee dans la reponse",
         r.get("conversions_unit") == "people")

# Statuts : liste BLANCHE.
# UNE PERSONNE PAR STATUT — puisque le compteur denombre des personnes, il faut
# six personnes distinctes pour eprouver six statuts.
STATUTS = ["active", "completed", "superseded", "expired", "cancelled", "refunded"]
decor(
    reservations=[res("s%d" % i, code="AFR-8%02d" % i, mail="st%d@exemple.test" % i,
                      offre=OFFRE_ESSAI, attribution=BON)
                  for i in range(len(STATUTS))],
    subscriptions=[{"code": "AFR-9%02d" % i, "email": "st%d@exemple.test" % i,
                    "status": st} for i, st in enumerate(STATUTS)])
statut, r = stats()
verifier("5h. les 4 statuts d'ACHAT comptent, `cancelled`/`refunded` NON "
         "(liste blanche, pas liste noire)",
         r["conversions"]["subscription"] == 4,
         "subscription=%s" % r["conversions"]["subscription"])
verifier("5h-bis. ... et le total suit : 4 personnes converties sur 6",
         r["unique_people"] == 6 and r["conversions"]["total"] == 4,
         "pers=%s total=%s" % (r["unique_people"], r["conversions"]["total"]))


print("\n=== 6. LES TAUX ===")

decor([
    res("x1", code="AFR-900", mail="t1@exemple.test", valide=True, attribution=BON),
    res("x2", code="AFR-901", mail="t2@exemple.test", valide=True, attribution=BON),
    res("x3", code="AFR-902", mail="t3@exemple.test", valide=False, attribution=BON),
    res("x4", code="AFR-903", mail="t4@exemple.test", valide=False, attribution=BON),
])
statut, r = stats()
verifier("6a. taux de presence = presences / reservations",
         r["attendance_rate"] == 0.5, "taux=%s" % r["attendance_rate"])
verifier("6b. taux de conversion = conversions / PERSONNES uniques",
         r["conversion_rate"] == 0.0, "taux=%s" % r["conversion_rate"])

decor()
statut, r = stats()
verifier("6c. aucune reservation : les taux valent `null`, JAMAIS 0 %",
         r["attendance_rate"] is None and r["conversion_rate"] is None,
         "presence=%s conversion=%s" % (r["attendance_rate"], r["conversion_rate"]))
verifier("6d. ... et les compteurs valent bien 0",
         r["reservations"] == 0 and r["unique_people"] == 0
         and r["conversions"]["total"] == 0)


print("\n=== 7. LA REPONSE : AUCUNE PII, AUCUN CLIC, AUCUNE ECRITURE ===")

base = decor([
    res("z1", code="AFR-950", mail="secret@exemple.test", valide=True, attribution=BON,
        userName="Nom Secret", userWhatsapp="+41000000000"),
])
statut, r = stats()
texte = str(r)
for interdit, quoi in [("secret@exemple.test", "e-mail"), ("Nom Secret", "nom"),
                       ("+41000000000", "telephone"), ("AFR-950", "code d'acces"),
                       ("z1", "identifiant de reservation")]:
    verifier("7a. la reponse ne contient AUCUN %s" % quoi, interdit not in texte)

verifier("7b. la reponse ne contient AUCUNE liste",
         not any(isinstance(v, list) for v in r.values()))
verifier("7c. AUCUN compteur de clics — l'audit a montre qu'ils ne sont pas mesurables",
         "click" not in texte.lower() and "clic" not in texte.lower())
verifier("7d. AUCUNE ECRITURE de toute la suite",
         base.ecritures() == 0, "ecritures=%d" % base.ecritures())
verifier("7e. la base d'attribution est annoncee dans la reponse",
         r["attribution"] == {"basis": "first", "source": "partenaire",
                              "medium": "referral", "campaign": "essai_neuchatel"})
verifier("7f. le statut operationnel est rendu tel quel, jamais recalcule",
         r["partner_status"] == "decouverte")


print("\n=== 8. LE CODE LIVRE DIT BIEN CE QU'ON CROIT ===")

SRC = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
ARBRE = ast.parse(SRC)


def _code(nom):
    """Le CODE EXECUTE seul — docstring et commentaires retires, guillemets
    normalises. Sans ce nettoyage, ce fichier se piegerait lui-meme : la
    docstring cite `require_auth` et `last` pour dire qu'ils ne sont PAS
    employes."""
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == nom:
            corps = list(n.body)
            if (corps and isinstance(corps[0], ast.Expr)
                    and isinstance(getattr(corps[0], "value", None), ast.Constant)
                    and isinstance(corps[0].value.value, str)):
                corps = corps[1:]
            return "\n".join(ast.unparse(x) for x in corps).replace("'", '"')
    raise AssertionError(nom)


CODE = _code("p2d_stats_partenaire")

verifier("8a. la garde est `_v309_require_coach_or_admin`",
         "await _v309_require_coach_or_admin(request)" in CODE)
verifier("8b. ... et c'est la PREMIERE instruction executee",
         CODE.strip().split("\n")[0].strip() == "appelant = await _v309_require_coach_or_admin(request)",
         CODE.strip().split("\n")[0].strip())
verifier("8c. `require_auth` n'est PAS employe", not re.search(r"\brequire_auth\s*\(", CODE))
verifier("8d. aucune decision d'acces ne vient de `X-User-Email`", "X-User-Email" not in CODE)
verifier("8e. AUCUNE ecriture dans le corps de la route",
         not re.search(r"\b(insert_one|insert_many|update_one|update_many|delete_one|"
                       r"delete_many|find_one_and_update|find_one_and_delete)\b", CODE))
verifier("8f. l'attribution employee est `first`, jamais `last`",
         "attribution.first.source" in CODE and "attribution.last" not in CODE)
verifier("8g. les QUATRE criteres sont exiges ensemble",
         all(c in CODE for c in ("attribution.first.source", "attribution.first.medium",
                                 "attribution.first.campaign", "attribution.first.content")))
verifier("8h. Pulse/Membre se lisent sur les BOOLEENS de l'offre, jamais sur un nom",
         '"creates_membership": True' in CODE and '"requires_active_membership": True' in CODE
         and "offer_name" not in CODE and "PULSE" not in CODE)
verifier("8i. la presence est `validated is True`",
         'r.get("validated") is True' in CODE)
verifier("8j. la propriete est verifiee sur `partners.coach_id`",
         'partenaire.get("coach_id")' in CODE)
verifier("8k. aucune regex Mongo sur une entree utilisateur", "$regex" not in CODE)
verifier("8l. les statuts d'achat sont une liste BLANCHE",
         "P2D_STATUTS_ACHAT" in CODE and "cancelled" not in SRC.split("P2D_STATUTS_ACHAT = ")[1][:120])
verifier("8m. le total des conversions est une UNION d'ensembles de personnes",
         "pulse | membre | abonnement" in CODE)
verifier("8n. aucun index n'est cree par ce lot",
         "create_index" not in CODE)

verifier("8o. les quatre UTM du serveur sont les jumelles de celles du navigateur",
         all(v in open(os.path.join(RACINE, "frontend", "src", "utils",
                                    "partnerLink.js"), encoding="utf-8").read()
             for v in ("partenaire", "referral", "essai_neuchatel"))
         and 'P2D_SOURCE = "partenaire"' in SRC
         and 'P2D_MEDIUM = "referral"' in SRC
         and 'P2D_CAMPAGNE = "essai_neuchatel"' in SRC)

verifier("8p. P2-A, P2-B et P2-C ne sont pas touches par ce lot",
         'd.get("application_decision") or "pending"' in SRC
         and "await _v309_require_coach_or_admin(request)" in _code("p2b_decider_candidature"))


print("\n" + "=" * 78)
_ok = sum(1 for _, c, _ in RESULTATS if c)
_total = len(RESULTATS)
print("P2-D1 — %d / %d verifications au vert" % (_ok, _total))
print("=" * 78)
if _ok != _total:
    print("\nECHECS :")
    for i, c, d in RESULTATS:
        if not c:
            print("  - %s%s" % (i, ("  [%s]" % d) if d else ""))
sys.exit(0 if _ok == _total else 1)
