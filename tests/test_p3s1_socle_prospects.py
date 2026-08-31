#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3-S1 — LE SOCLE DES PROSPECTS PARTENAIRES.

CE QUE LE LOT AJOUTE
==============================================================================
Une collection `partner_prospects`, un modele valide, quatre routes :

  GET    /api/partner-prospects              liste + 5 filtres, plafond 50
  GET    /api/partner-prospects/{id}         une fiche
  POST   /api/partner-prospects              creation
  PATCH  /api/partner-prospects/{id}         modification partielle

AUCUN envoi, AUCUNE relance, AUCUNE echeance calculee, AUCUN import, AUCUN
ecran. Les messages J0/J+3/J+7 ne sont que du TEXTE stocke.

CE QUE CE FICHIER PROUVE, ET COMMENT
==============================================================================
La base est un BOUCHON qui compte les ecritures de CHAQUE collection — pas
seulement de celles auxquelles on pense. C'est la seule facon de prouver le
point le plus important du lot : creer un prospect commercial ne fabrique NI
contact, NI conversation, NI lead, NI utilisateur, NI reservation, NI
abonnement, NI notification. Un prospect n'a rien demande ; lui inventer une
identite dans le systeme client fausserait tous les compteurs metier.

La section 5 va plus loin que le comptage : elle LIT LE CODE (AST) des
fonctions `p3s1_*` et verifie qu'aucune n'appelle un helper d'envoi ou de
notification. Un compteur prouve qu'on n'a pas envoye AUJOURD'HUI ; l'AST
prouve qu'on ne PEUT pas envoyer.

AUCUNE ECRITURE EN PRODUCTION. Tout se joue sur des documents fictifs, en
memoire. La base de production n'est jamais ouverte.

    python3 tests/test_p3s1_socle_prospects.py
"""
import ast
import asyncio
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


# ============================================================================
SECRET_FICTIF = "secret-de-test-p3s1-sans-aucun-rapport-avec-la-production"
ADMIN_FICTIF = "admin.fictif@exemple.test"
COACH_A = "coach.a.fictif@exemple.test"
COACH_B = "coach.b.fictif@exemple.test"

os.environ["JWT_SECRET"] = SECRET_FICTIF
# Adresse VOLONTAIREMENT injoignable : le module s'importe, mais aucune
# connexion n'est jamais ouverte. La production n'est pas touchee.
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-inexistant:27017")

import jwt as pyjwt  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from pymongo.errors import DuplicateKeyError  # noqa: E402


def jeton(email, type_=None):
    charge = {"email": email,
              "exp": int((datetime.now(timezone.utc) + timedelta(minutes=60)).timestamp())}
    if type_:
        charge["type"] = type_
    j = pyjwt.encode(charge, SECRET_FICTIF, algorithm="HS256")
    return j.decode("utf-8") if isinstance(j, bytes) else j


JETON_A = jeton(COACH_A)
JETON_B = jeton(COACH_B)
JETON_ABONNE = jeton(COACH_A, type_="subscriber")


class RequeteFictive:
    def __init__(self, jeton_=None, entete=None, corps=None, params=None):
        e = {}
        if jeton_:
            e["Authorization"] = "Bearer " + jeton_
        if entete:
            e["X-User-Email"] = entete
        self.headers = e
        self.query_params = params or {}
        self._corps = corps if corps is not None else {}

    async def json(self):
        return self._corps


class Curseur:
    """P3-S2 : le curseur sait desormais trier, sauter et borner.

    La route de liste a cesse de trier en Python pour trier EN BASE — sans quoi
    la pagination rendrait un echantillon arbitraire. Le bouchon doit donc
    honorer `sort/skip/limit`. C'est de l'OUTILLAGE : aucune assertion de ce
    fichier n'a change.
    """

    def __init__(self, docs):
        self._docs = docs
        self._skip = 0
        self._limit = None

    def sort(self, cle, sens=1):
        self._docs = sorted(self._docs, key=lambda d: d.get(cle) or "",
                            reverse=(sens == -1))
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
        self._i = iter(self._tranche())
        return self

    async def __anext__(self):
        try:
            return next(self._i)
        except StopIteration:
            raise StopAsyncIteration


class CollectionBouchon:
    """Honore les filtres utilises par le lot, COMPTE toute ecriture.

    Le compteur `ecritures` est le coeur des sections 3 et 4 : il est lu sur
    CHAQUE collection, y compris celles que le lot n'est pas cense connaitre.
    """

    def __init__(self, nom, documents=None, uniques=()):
        self.nom = nom
        self.documents = [dict(d) for d in (documents or [])]
        self.uniques = tuple(uniques)
        self.ecritures = 0
        self.index = []

    # --- filtrage ---
    def _ok(self, doc, filtre):
        if not filtre:
            return True
        if "$or" in filtre:
            if not any(self._ok(doc, sous) for sous in filtre["$or"]):
                return False
        for cle, val in filtre.items():
            if cle == "$or":
                continue
            if isinstance(val, dict):
                if "$in" in val and doc.get(cle) not in val["$in"]:
                    return False
                if "$nin" in val and doc.get(cle) in val["$nin"]:
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

    async def count_documents(self, filtre=None, *a, **k):
        return sum(1 for d in self.documents if self._ok(d, filtre))

    def aggregate(self, etapes, *a, **k):
        """P3-S2 : outillage. `$match` puis `$group` par une seule cle."""
        docs = list(self.documents)
        groupes = {}
        for etape in etapes:
            if "$match" in etape:
                docs = [d for d in docs if self._ok(d, etape["$match"])]
            if "$group" in etape:
                cle = etape["$group"]["_id"].lstrip("$")
                for d in docs:
                    groupes[d.get(cle)] = groupes.get(d.get(cle), 0) + 1
        return Curseur([{"_id": k2, "n": v} for k2, v in groupes.items()])

    # --- index uniques, simules comme en base ---
    def _verifier_uniques(self, doc, sauf=None):
        for cles in self.uniques:
            cles = (cles,) if isinstance(cles, str) else cles
            # Index PARTIEL : ignore si l'une des cles vaut None (motif
            # partialFilterExpression {"ref": {"$type": "string"}}).
            if any(doc.get(c) is None for c in cles):
                continue
            for autre in self.documents:
                if autre is sauf:
                    continue
                if all(autre.get(c) == doc.get(c) for c in cles):
                    raise DuplicateKeyError("index unique %s" % (cles,))

    async def insert_one(self, doc, session=None, *a, **k):
        self._verifier_uniques(doc)
        self.ecritures += 1
        self.documents.append(dict(doc))
        return None

    async def update_one(self, filtre, maj, session=None, *a, **k):
        for d in self.documents:
            if self._ok(d, filtre):
                candidat = dict(d)
                candidat.update(maj.get("$set") or {})
                self._verifier_uniques(candidat, sauf=d)
                d.update(maj.get("$set") or {})
                self.ecritures += 1
                return None
        return None

    async def insert_many(self, docs, *a, **k):
        for d in docs:
            await self.insert_one(d)

    async def delete_one(self, *a, **k):
        self.ecritures += 1
        return None

    async def delete_many(self, *a, **k):
        self.ecritures += 1
        return None

    async def find_one_and_update(self, *a, **k):
        self.ecritures += 1
        return None

    async def create_index(self, cles, **k):
        self.index.append((cles, k))
        return "idx"


class BaseBouchon:
    """Registre unique : `db.users` et `db["users"]` sont le MEME objet.

    Indispensable — le lot accede a sa collection par `db[P3S1_COLLECTION]`,
    alors que le reste du serveur utilise l'attribut. Sans registre commun, le
    comptage des ecritures serait aveugle.
    """

    def __init__(self):
        self._cols = {}
        self["partner_prospects"] = CollectionBouchon(
            "partner_prospects", [], uniques=[("coach_id", "ref"), ("id",)])
        self["coaches"] = CollectionBouchon(
            "coaches", [{"email": COACH_A}, {"email": COACH_B}])
        self["coach_auth"] = CollectionBouchon("coach_auth", [])

    def __setitem__(self, nom, col):
        self._cols[nom] = col

    def __getitem__(self, nom):
        if nom not in self._cols:
            self._cols[nom] = CollectionBouchon(nom)
        return self._cols[nom]

    def __getattr__(self, nom):
        if nom.startswith("_"):
            raise AttributeError(nom)
        return self[nom]

    def ecritures_hors(self, *sauf):
        """Toute ecriture faite ailleurs que dans les collections citees."""
        return {n: c.ecritures for n, c in self._cols.items()
                if n not in sauf and c.ecritures}


import api.server as S  # noqa: E402

S.SUPER_ADMIN_EMAILS = [ADMIN_FICTIF]

try:
    asyncio.set_event_loop(asyncio.new_event_loop())
except Exception:
    pass


def lancer(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def poser_base():
    base = BaseBouchon()
    S.db = base
    return base


def statut_http(coro):
    """Le code HTTP leve, ou 200 si la coroutine a rendu sans lever."""
    try:
        lancer(coro)
        return 200
    except HTTPException as e:
        return e.status_code


PROSPECT = {
    "ref": "FES-01",
    "organisation_name": "Festi'neuch",
    "category": "festival",
    "city": "Neuchâtel",
    "website": "https://www.festineuch.ch/programme",
    "instagram": "@festineuch",
    "public_email": "Partenariats@Festineuch.CH",
    "score": 6.5,
    "priority": "B",
    "wave": "Vague 2",
    "preferred_channel": "Formulaire / DM",
    "collaboration_type": "event_programming",
    "j0_message": "Bonjour, c'est Bassi d'Afroboost...",
}


def creer(base, jeton_, **surcharges):
    corps = dict(PROSPECT)
    corps.update(surcharges)
    return lancer(S.p3s1_creer_prospect(RequeteFictive(jeton_=jeton_, corps=corps)))


# ============================================================================
print("\n" + "=" * 78)
print("P3-S1 — SOCLE DES PROSPECTS PARTENAIRES")
print("=" * 78)

print("\n1. AUTHENTIFICATION ET CLOISONNEMENT")

base = poser_base()
cree = creer(base, JETON_A)
verifier("A. un coach authentifie cree un prospect",
         cree.get("id") and cree.get("organisation_name") == "Festi'neuch",
         str(cree)[:120])

base = poser_base()
verifier("B. anonyme refuse (403)",
         statut_http(S.p3s1_creer_prospect(RequeteFictive(corps=dict(PROSPECT)))) == 403)
verifier("B-bis. X-User-Email seul refuse (403) — en-tete falsifiable",
         statut_http(S.p3s1_creer_prospect(
             RequeteFictive(entete=ADMIN_FICTIF, corps=dict(PROSPECT)))) == 403)
verifier("B-ter. jeton d'ABONNE refuse (403)",
         statut_http(S.p3s1_creer_prospect(
             RequeteFictive(jeton_=JETON_ABONNE, corps=dict(PROSPECT)))) == 403)
verifier("B-quater. les 4 routes exigent la meme garde",
         all(statut_http(r) == 403 for r in (
             S.p3s1_lister_prospects(RequeteFictive()),
             S.p3s1_lire_prospect("x", RequeteFictive()),
             S.p3s1_creer_prospect(RequeteFictive(corps=dict(PROSPECT))),
             S.p3s1_modifier_prospect("x", RequeteFictive(corps={"status": "contacte"})))))

base = poser_base()
a = creer(base, JETON_A)
verifier("C. le coach B ne LIT pas le prospect du coach A (403)",
         statut_http(S.p3s1_lire_prospect(a["id"], RequeteFictive(jeton_=JETON_B))) == 403)
verifier("C-bis. le coach B ne MODIFIE pas le prospect du coach A (403)",
         statut_http(S.p3s1_modifier_prospect(
             a["id"], RequeteFictive(jeton_=JETON_B, corps={"status": "refuse"}))) == 403)
liste_b = lancer(S.p3s1_lister_prospects(RequeteFictive(jeton_=JETON_B)))
verifier("C-ter. la LISTE du coach B ne montre rien du coach A",
         liste_b["total"] == 0 and liste_b["prospects"] == [])
verifier("C-quater. le coach_id vient du jeton, jamais du corps",
         creer(poser_base(), JETON_A, coach_id=COACH_B)["coach_id"] == COACH_A)

print("\n2. VALIDATION DU MODELE")

base = poser_base()
verifier("D. categorie valide acceptee (les 8)",
         all(creer(poser_base(), JETON_A, category=c, ref=None)["category"] == c
             for c in S.P3S1_CATEGORIES))
verifier("E. categorie inconnue refusee (400)",
         statut_http(S.p3s1_creer_prospect(RequeteFictive(
             jeton_=JETON_A, corps=dict(PROSPECT, category="salle_de_sport")))) == 400)
verifier("E-bis. categorie absente refusee (400)",
         statut_http(S.p3s1_creer_prospect(RequeteFictive(
             jeton_=JETON_A, corps={"organisation_name": "X"}))) == 400)
verifier("F. statut valide accepte (les 6 amont)",
         all(creer(poser_base(), JETON_A, status=s, ref=None)["status"] == s
             for s in S.P3S1_STATUTS))
verifier("G. statut inconnu refuse (400)",
         statut_http(S.p3s1_creer_prospect(RequeteFictive(
             jeton_=JETON_A, corps=dict(PROSPECT, status="vendu")))) == 400)
verifier("G-bis. les statuts PARTENAIRE sont refuses ici — pas de duplication",
         all(statut_http(S.p3s1_creer_prospect(RequeteFictive(
             jeton_=JETON_A, corps=dict(PROSPECT, status=s)))) == 400
             for s in ("decouverte", "actif", "ambassadeur")))
verifier("G-ter. sans statut fourni, le prospect naît « a_contacter »",
         creer(poser_base(), JETON_A)["status"] == "a_contacter")
verifier("G-ter-bis. un statut explicitement nul est REFUSE (400) — un prospect "
         "a toujours un etat",
         statut_http(S.p3s1_creer_prospect(RequeteFictive(
             jeton_=JETON_A, corps=dict(PROSPECT, status=None)))) == 400)
verifier("G-quater. nom d'organisation vide refuse (400)",
         statut_http(S.p3s1_creer_prospect(RequeteFictive(
             jeton_=JETON_A, corps=dict(PROSPECT, organisation_name="   ")))) == 400)
verifier("G-5. score hors bornes refuse (400)",
         statut_http(S.p3s1_creer_prospect(RequeteFictive(
             jeton_=JETON_A, corps=dict(PROSPECT, score=42)))) == 400)
verifier("G-6. priorite inconnue refusee (400)",
         statut_http(S.p3s1_creer_prospect(RequeteFictive(
             jeton_=JETON_A, corps=dict(PROSPECT, priority="Z")))) == 400)
verifier("G-7. type de collaboration inconnu refuse (400)",
         statut_http(S.p3s1_creer_prospect(RequeteFictive(
             jeton_=JETON_A, corps=dict(PROSPECT, collaboration_type="sponsoring")))) == 400)

c = creer(poser_base(), JETON_A, public_phone=None, contact_name="")
verifier("G-8. une coordonnee absente vaut None, jamais une chaine vide",
         c["public_phone"] is None and c["contact_name"] is None)
verifier("G-9. les deux pointeurs P2 naissent a None",
         c["partner_application_id"] is None and c["partner_id"] is None)
verifier("G-10. les 8 dates commerciales existent et valent None",
         all(c.get(d) is None for d in S.P3S1_DATES))
verifier("G-11. l'e-mail public est normalise en minuscules",
         c["public_email"] == "partenariats@festineuch.ch")

print("\n3. AUCUN EFFET DE BORD — LE POINT CRITIQUE DU LOT")

base = poser_base()
creer(base, JETON_A)
ailleurs = base.ecritures_hors("partner_prospects")
verifier("H a L. creer un prospect n'ecrit dans AUCUNE autre collection",
         ailleurs == {}, "ecritures parasites : %s" % ailleurs)
for intitule, col in (("H. aucun user cree", "users"),
                      ("I. aucun lead cree", "leads"),
                      ("J. aucun chat_participant cree", "chat_participants"),
                      ("J-bis. aucune chat_session creee", "chat_sessions"),
                      ("J-ter. aucun chat_message cree", "chat_messages"),
                      ("J-4. aucune notification creee", "notifications"),
                      ("K. aucune reservation creee", "reservations"),
                      ("L. aucun abonnement cree", "subscriptions"),
                      ("L-bis. aucun code d'acces cree", "discount_codes"),
                      ("L-ter. aucun partenaire cree", "partners")):
    verifier(intitule, base[col].ecritures == 0 and base[col].documents == [])

base = poser_base()
p = creer(base, JETON_A)
lancer(S.p3s1_modifier_prospect(p["id"], RequeteFictive(jeton_=JETON_A, corps={"status": "contacte"})))
lancer(S.p3s1_lister_prospects(RequeteFictive(jeton_=JETON_A)))
lancer(S.p3s1_lire_prospect(p["id"], RequeteFictive(jeton_=JETON_A)))
ailleurs = base.ecritures_hors("partner_prospects")
verifier("H-bis. les QUATRE routes n'ecrivent que dans partner_prospects",
         ailleurs == {}, "ecritures parasites : %s" % ailleurs)

print("\n4. AUCUN ENVOI")

SOURCE = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
ARBRE = ast.parse(SOURCE)
FONCTIONS_P3 = [n for n in ast.walk(ARBRE)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name.startswith("p3s1_")]
verifier("M-0. les fonctions du lot sont bien presentes", len(FONCTIONS_P3) >= 9,
         "trouvees : %d" % len(FONCTIONS_P3))

INTERDITS = ("send_email", "send_whatsapp", "send_push", "send_push_by_email",
             "resend", "Emails", "webpush", "notifier_nouveau_prospect",
             "send_backup_email", "envoyer", "notify")
appels = set()
for f in FONCTIONS_P3:
    for n in ast.walk(f):
        if isinstance(n, ast.Call):
            cible = n.func
            nom = getattr(cible, "id", None) or getattr(cible, "attr", None) or ""
            if any(i.lower() in nom.lower() for i in INTERDITS):
                appels.add("%s -> %s" % (f.name, nom))
verifier("M. aucune fonction p3s1_ n'appelle un helper d'envoi ou de notification",
         not appels, "appels trouves : %s" % sorted(appels))

textuel = set()
for f in FONCTIONS_P3:
    seg = ast.get_source_segment(SOURCE, f) or ""
    for i in ("resend.Emails", "webpush(", "send_whatsapp(", "send_push_by_email(",
              "graph.facebook.com", "notifications.insert"):
        if i in seg:
            textuel.add("%s -> %s" % (f.name, i))
verifier("M-bis. aucune trace textuelle d'un canal d'envoi dans le lot",
         not textuel, str(sorted(textuel)))

base = poser_base()
creer(base, JETON_A, j0_message="Bonjour", j3_message="Je reviens", j7_message="Dernier mot")
verifier("M-ter. les messages J0/J+3/J+7 sont stockes, pas envoyes",
         base["partner_prospects"].documents[0]["j0_message"] == "Bonjour"
         and base.ecritures_hors("partner_prospects") == {})

print("\n5. FILTRES DE LISTE")

base = poser_base()
for i, (cat, st, vg, vl, pr) in enumerate((
        ("festival", "a_contacter", "Vague 1", "Neuchâtel", "A"),
        ("bar", "contacte", "Vague 1", "Neuchatel", "B"),
        ("commerce", "repondu", "Vague 2", "Lausanne", "A"),
        ("influenceur", "a_contacter", "Vague 2", "Neuchâtel", "C"))):
    # E-mails distincts : sinon le signal anti-doublon (§7) refuserait a juste
    # titre la deuxieme fixture. C'est lui qui fonctionne, pas le test qui rate.
    creer(base, JETON_A, ref="R-%02d" % i, organisation_name="Org %d" % i,
          public_email="org%d@exemple.test" % i, public_phone=None,
          category=cat, status=st, wave=vg, city=vl, priority=pr)


def liste(**params):
    return lancer(S.p3s1_lister_prospects(RequeteFictive(jeton_=JETON_A, params=params)))


verifier("N. filtre status", liste(status="a_contacter")["total"] == 2)
verifier("O. filtre category", liste(category="bar")["total"] == 1)
verifier("P. filtre wave", liste(wave="Vague 1")["total"] == 2)
verifier("P-bis. filtre priority", liste(priority="A")["total"] == 2)
verifier("P-ter. filtre city insensible aux accents (Neuchatel == Neuchâtel)",
         liste(city="Neuchatel")["total"] == 3)
verifier("P-4. filtres combines", liste(status="a_contacter", wave="Vague 2")["total"] == 1)
verifier("P-5. filtre a valeur inconnue refuse (400)",
         statut_http(S.p3s1_lister_prospects(
             RequeteFictive(jeton_=JETON_A, params={"status": "vendu"}))) == 400)
verifier("P-6. la liste est plafonnee a 50",
         liste(limit="9999")["limit"] == S.P3S1_LISTE_MAX == 50)
verifier("P-7. la liste rend le total NON borne, pour savoir qu'il en reste",
         set(liste().keys()) >= {"total", "returned", "limit", "prospects"})

print("\n6. MODIFICATION")

base = poser_base()
p = creer(base, JETON_A)
avant = p["updated_at"]
apres = lancer(S.p3s1_modifier_prospect(
    p["id"], RequeteFictive(jeton_=JETON_A, corps={"status": "contacte"})))
verifier("Q. PATCH statut", apres["status"] == "contacte")
verifier("Q-bis. PATCH ne touche QUE les champs fournis",
         apres["organisation_name"] == p["organisation_name"]
         and apres["category"] == p["category"] and apres["wave"] == p["wave"])
verifier("Q-ter. updated_at bouge, created_at ne bouge pas",
         apres["created_at"] == p["created_at"] and apres["updated_at"] >= avant)
verifier("Q-4. PATCH d'un statut inconnu refuse (400)",
         statut_http(S.p3s1_modifier_prospect(
             p["id"], RequeteFictive(jeton_=JETON_A, corps={"status": "vendu"}))) == 400)
verifier("Q-5. PATCH ne peut pas reecrire coach_id ni id",
         lancer(S.p3s1_modifier_prospect(p["id"], RequeteFictive(
             jeton_=JETON_A, corps={"coach_id": COACH_B, "id": "pirate",
                                    "status": "repondu"})))["coach_id"] == COACH_A
         and base["partner_prospects"].documents[0]["id"] == p["id"])
verifier("Q-6. PATCH vide refuse (400)",
         statut_http(S.p3s1_modifier_prospect(
             p["id"], RequeteFictive(jeton_=JETON_A, corps={}))) == 400)
verifier("Q-7. PATCH sur un prospect inexistant -> 404",
         statut_http(S.p3s1_modifier_prospect(
             "inexistant", RequeteFictive(jeton_=JETON_A, corps={"status": "refuse"}))) == 404)
recalc = lancer(S.p3s1_modifier_prospect(
    p["id"], RequeteFictive(jeton_=JETON_A, corps={"city": "Lausanne"})))
verifier("Q-8. changer la ville RECALCULE la cle de doublon",
         recalc["dedupe_key"] == S.p3s1_cle_doublon(p["organisation_name"], "Lausanne")
         and recalc["city_key"] == "lausanne")

print("\n7. ANTI-DOUBLON ET IDEMPOTENCE")

verifier("R-0. la cle de doublon ignore casse, accents et ponctuation",
         S.p3s1_cle_doublon("Festi'neuch", "Neuchâtel")
         == S.p3s1_cle_doublon("  FESTI NEUCH  ", "neuchatel"))
verifier("R-0bis. elle ne RAPPROCHE PAS deux noms qui se ressemblent",
         S.p3s1_cle_doublon("Akoko Tresses", "Neuchâtel")
         != S.p3s1_cle_doublon("Akoko Tresse", "Neuchâtel"))

base = poser_base()
creer(base, JETON_A)
verifier("R. un second prospect nom+ville identique est SIGNALE (409), pas fusionne",
         statut_http(S.p3s1_creer_prospect(RequeteFictive(
             jeton_=JETON_A, corps=dict(PROSPECT, ref="FES-99")))) == 409)
verifier("R-bis. le 409 n'a RIEN ecrit", len(base["partner_prospects"].documents) == 1)
try:
    lancer(S.p3s1_creer_prospect(RequeteFictive(jeton_=JETON_A, corps=dict(PROSPECT, ref="FES-99"))))
    detail = None
except HTTPException as e:
    detail = e.detail
verifier("R-ter. le 409 dit LEQUEL ressemble, pour que l'humain tranche",
         isinstance(detail, dict) and detail.get("possible_duplicates")
         and detail["possible_duplicates"][0]["matched_on"], str(detail)[:160])
verifier("R-4. avec allow_duplicate, les deux fiches coexistent (deux bars homonymes)",
         creer(base, JETON_A, ref="FES-99", allow_duplicate=True).get("id")
         and len(base["partner_prospects"].documents) == 2)

base = poser_base()
creer(base, JETON_A)
verifier("R-5. la MEME ref est refusee par l'INDEX UNIQUE, meme avec allow_duplicate",
         statut_http(S.p3s1_creer_prospect(RequeteFictive(
             jeton_=JETON_A, corps=dict(PROSPECT, organisation_name="Tout autre nom",
                                        city="Bienne", allow_duplicate=True)))) == 409)
verifier("R-6. ce 409-la n'a rien ecrit non plus",
         len(base["partner_prospects"].documents) == 1)
verifier("R-7. la ref est unique PAR COACH, pas globalement",
         lancer(S.p3s1_creer_prospect(RequeteFictive(
             jeton_=JETON_B, corps=dict(PROSPECT))))["ref"] == "FES-01")

base = poser_base()
verifier("R-8. deux prospects SANS ref coexistent (l'index unique est PARTIEL)",
         creer(base, JETON_A, ref=None, organisation_name="Bar A",
               public_email="bar.a@exemple.test", public_phone=None).get("id")
         and creer(base, JETON_A, ref=None, organisation_name="Bar B",
                   public_email="bar.b@exemple.test", public_phone=None).get("id"))
verifier("R-9. un e-mail public identique est signale (409) meme si nom et ville different",
         statut_http(S.p3s1_creer_prospect(RequeteFictive(
             jeton_=JETON_A, corps=dict(PROSPECT, ref=None, organisation_name="Bar C",
                                        city="Bienne", public_phone=None,
                                        public_email="bar.a@exemple.test")))) == 409)
verifier("R-10. un telephone public identique est signale (409)",
         statut_http(S.p3s1_creer_prospect(RequeteFictive(
             jeton_=JETON_A, corps=dict(PROSPECT, ref=None, organisation_name="Bar D",
                                        city="Bienne", public_email=None,
                                        public_phone="+41 32 000 00 00")))) == 200
         and statut_http(S.p3s1_creer_prospect(RequeteFictive(
             jeton_=JETON_A, corps=dict(PROSPECT, ref=None, organisation_name="Bar E",
                                        city="Bienne", public_email=None,
                                        public_phone="+41 32 000 00 00")))) == 409)
verifier("R-11. un prospect SANS aucune coordonnee ne declenche aucun faux signal",
         statut_http(S.p3s1_creer_prospect(RequeteFictive(
             jeton_=JETON_A, corps=dict(PROSPECT, ref=None, organisation_name="Sans coordonnees",
                                        city="Bienne", public_email=None,
                                        public_phone=None)))) == 200)

print("\n8. INDEX ET CONVENTIONS")

DEMARRAGE = ""
for n in ast.walk(ARBRE):
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "startup_db":
        DEMARRAGE = ast.get_source_segment(SOURCE, n) or ""
verifier("S-1. les index sont poses au demarrage", "P3S1_COLLECTION" in DEMARRAGE)
verifier("S-2. (coach_id, ref) est UNIQUE et PARTIEL",
         'partialFilterExpression={"ref": {"$type": "string"}}' in DEMARRAGE
         and '[("coach_id", 1), ("ref", 1)], unique=True' in DEMARRAGE)
verifier("S-3. dedupe_key n'est PAS unique — deux homonymes restent exprimables",
         '[("coach_id", 1), ("dedupe_key", 1)])' in DEMARRAGE)
verifier("S-4. un index par filtre annonce (status, category, wave, priority)",
         all('[("coach_id", 1), ("%s", 1)]' % f in DEMARRAGE
             for f in ("status", "category", "wave", "priority")))

CORPS_P3 = "\n".join(ast.get_source_segment(SOURCE, f) or "" for f in FONCTIONS_P3)
# On cherche la forme REELLE d'une cle Mongo — `"$regex"` entre guillemets —
# et non le mot nu : celui-ci apparait dans un commentaire du lot qui dit
# justement de ne jamais s'en servir. Un test qui echoue sur sa propre
# documentation ne prouve rien.
verifier("S-5. aucune entree utilisateur n'entre dans une regex Mongo",
         '"$regex"' not in CORPS_P3 and "'$regex'" not in CORPS_P3,
         "occurrences : %d" % CORPS_P3.count('"$regex"'))
verifier("S-6. DuplicateKeyError a son import LOCAL dans les deux routes d'ecriture",
         all(any(isinstance(x, ast.ImportFrom) and x.module == "pymongo.errors"
                 for x in ast.walk(f))
             for f in FONCTIONS_P3
             if "DuplicateKeyError" in (ast.get_source_segment(SOURCE, f) or "")))
verifier("S-7. les statuts partenaire P2 ne sont PAS redefinis par ce lot",
         not ({"decouverte", "actif", "ambassadeur"} & set(S.P3S1_STATUTS)))
# P3-S2B a AJOUTE deux categories (`association`, `fitness`). L'assertion
# d'origine figeait l'egalite a huit : elle est ELARGIE, pas retiree — les huit
# du socle restent exigees, et les deux nouvelles sont verifiees a part. Une
# categorie supprimee ferait donc toujours echouer ce test.
verifier("S-8. les 8 categories du socle sont TOUJOURS couvertes",
         set(S.P3S1_CATEGORIES) >= {"festival", "ecole_danse", "restaurant", "bar",
                                    "commerce", "organisateur_evenement",
                                    "communaute_etudiante", "influenceur"})
verifier("S-8-bis. P3-S2B a ajoute « association » et « fitness », et rien d'autre",
         set(S.P3S1_CATEGORIES) == {"festival", "ecole_danse", "restaurant", "bar",
                                    "commerce", "organisateur_evenement",
                                    "communaute_etudiante", "influenceur",
                                    "association", "fitness"})
verifier("S-9. aucune route DELETE — hors lot, comme convenu",
         "p3s1_supprimer" not in SOURCE and 'delete("/partner-prospects' not in SOURCE)
verifier("S-10. la collection est distincte des sept collections metier",
         S.P3S1_COLLECTION == "partner_prospects"
         and S.P3S1_COLLECTION not in ("users", "leads", "chat_participants",
                                       "subscriptions", "reservations", "partners",
                                       "contacts"))

# ============================================================================
print("\n" + "=" * 78)
_ok = sum(1 for _, c, _ in RESULTATS if c)
print("RESULTAT : %d/%d" % (_ok, len(RESULTATS)))
if _ok != len(RESULTATS):
    print("\nECHECS :")
    for intitule, cond, detail in RESULTATS:
        if not cond:
            print("  - %s   %s" % (intitule, detail))
print("=" * 78)
sys.exit(0 if _ok == len(RESULTATS) else 1)
