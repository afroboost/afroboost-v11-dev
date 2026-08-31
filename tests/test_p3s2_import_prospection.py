#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3-S2 — L'IMPORT DES PROSPECTS ET L'ÉCRAN QUI LES MONTRE.

CE QUE LE LOT AJOUTE
==============================================================================
  * `tests/import_prospects_cowork.py` — essai à blanc par défaut, `--appliquer`
    pour écrire. Traduit le classeur Cowork vers `partner_prospects`.
  * `offset` et `counts` sur `GET /api/partner-prospects` — sans eux l'écran ne
    peut ni dépasser 50 lignes ni afficher ses tuiles.
  * `frontend/.../ProspectsSection.js` — l'écran, testé à part en Jest.

CE QUE CE FICHIER PROUVE, ET COMMENT
==============================================================================
La traduction est une FONCTION PURE : elle prend des lignes de tableur et rend
des documents, sans base. On peut donc l'éprouver sur des feuilles fabriquées —
catégorie fausse, statut inconnu, « NON TROUVÉ », doublons — sans jamais
approcher la production.

La base reste un BOUCHON qui compte les écritures de CHAQUE collection. Le point
qui compte le plus n'est pas qu'on crée 80 prospects : c'est qu'un SECOND import
n'en crée pas 80 de plus, et qu'aucune autre collection ne bouge.

Le vrai classeur (`~/Downloads/...READY.xlsx`) sert aux vérifications de bout en
bout. S'il est absent, ces contrôles-là sont ANNONCÉS comme non joués — jamais
comptés au vert en silence.

AUCUNE ÉCRITURE EN PRODUCTION.

    python3 tests/test_p3s2_import_prospection.py
"""
import ast
import asyncio
import os
import re
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

RESULTATS = []
NON_JOUES = []


def verifier(intitule, condition, detail=""):
    RESULTATS.append((intitule, bool(condition), detail))
    print("  %-6s %s" % ("OK  " if condition else "ECHEC", intitule))
    if detail and not condition:
        print("           -> %s" % detail)
    return bool(condition)


def non_joue(intitule, raison):
    NON_JOUES.append((intitule, raison))
    print("  %-6s %s   (%s)" % ("SKIP", intitule, raison))


SECRET_FICTIF = "secret-de-test-p3s2-sans-aucun-rapport-avec-la-production"
COACH_A = "coach.a.fictif@exemple.test"
COACH_B = "coach.b.fictif@exemple.test"
os.environ["JWT_SECRET"] = SECRET_FICTIF
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-inexistant:27017")

import jwt as pyjwt  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from pymongo.errors import DuplicateKeyError  # noqa: E402

import api.server as S  # noqa: E402
from tests import import_prospects_cowork as I  # noqa: E402

S.SUPER_ADMIN_EMAILS = ["admin.fictif@exemple.test"]
try:
    asyncio.set_event_loop(asyncio.new_event_loop())
except Exception:
    pass


def lancer(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def jeton(email):
    j = pyjwt.encode({"email": email,
                      "exp": int((datetime.now(timezone.utc) + timedelta(minutes=60)).timestamp())},
                     SECRET_FICTIF, algorithm="HS256")
    return j.decode("utf-8") if isinstance(j, bytes) else j


class RequeteFictive:
    def __init__(self, jeton_=None, params=None, corps=None):
        self.headers = {"Authorization": "Bearer " + jeton_} if jeton_ else {}
        self.query_params = params or {}
        self._corps = corps or {}

    async def json(self):
        return self._corps


class Curseur:
    def __init__(self, docs):
        self._docs = docs
        self._skip = 0
        self._limit = None

    def sort(self, cle, sens=1):
        self._docs = sorted(self._docs, key=lambda d: d.get(cle) or "", reverse=(sens == -1))
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
    def __init__(self, nom, documents=None, uniques=()):
        self.nom = nom
        self.documents = [dict(d) for d in (documents or [])]
        self.uniques = tuple(uniques)
        self.ecritures = 0

    def _ok(self, doc, filtre):
        if not filtre:
            return True
        if "$or" in filtre and not any(self._ok(doc, s) for s in filtre["$or"]):
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

    async def find_one(self, filtre=None, projection=None, **k):
        for d in self.documents:
            if self._ok(d, filtre):
                return dict(d)
        return None

    def find(self, filtre=None, projection=None, **k):
        return Curseur([dict(d) for d in self.documents if self._ok(d, filtre)])

    async def count_documents(self, filtre=None, **k):
        return sum(1 for d in self.documents if self._ok(d, filtre))

    def aggregate(self, etapes, **k):
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

    def _uniques(self, doc, sauf=None):
        for cles in self.uniques:
            cles = (cles,) if isinstance(cles, str) else cles
            if any(doc.get(c) is None for c in cles):
                continue
            for autre in self.documents:
                if autre is sauf:
                    continue
                if all(autre.get(c) == doc.get(c) for c in cles):
                    raise DuplicateKeyError("index unique %s" % (cles,))

    async def insert_one(self, doc, **k):
        self._uniques(doc)
        self.ecritures += 1
        self.documents.append(dict(doc))

    async def update_one(self, filtre, maj, **k):
        for d in self.documents:
            if self._ok(d, filtre):
                candidat = dict(d)
                candidat.update(maj.get("$set") or {})
                self._uniques(candidat, sauf=d)
                d.update(maj.get("$set") or {})
                self.ecritures += 1
                return
        return

    async def delete_one(self, *a, **k):
        self.ecritures += 1

    async def delete_many(self, *a, **k):
        self.ecritures += 1

    async def find_one_and_update(self, *a, **k):
        self.ecritures += 1

    async def create_index(self, *a, **k):
        return "idx"


class BaseBouchon:
    def __init__(self):
        self._cols = {}
        self["partner_prospects"] = CollectionBouchon(
            "partner_prospects", [], uniques=[("coach_id", "ref"), ("id",)])
        self["coaches"] = CollectionBouchon("coaches", [{"email": COACH_A}, {"email": COACH_B}])

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
        return {n: c.ecritures for n, c in self._cols.items() if n not in sauf and c.ecritures}


# ---------------------------------------------------------------------------
# Feuilles FABRIQUÉES : la traduction se teste sans classeur ni base.
# ---------------------------------------------------------------------------
ENTETES = ["ID", "Catégorie", "Nom", "Ville", "Adresse", "Site", "Instagram",
           "Autres réseaux", "E-mail", "Téléphone", "Contact + rôle", "Canal",
           "Score /10", "Priorité", "Idée de collaboration", "Pourquoi Afroboost",
           "Source", "Approche", "Message prêt", "Date contact prévue", "Statut",
           "Relance J+3", "Relance J+7", "Réponse", "Candidature", "Accepté",
           "Lien/QR envoyé", "Réservations", "Présences", "Conversions", "Notes",
           "Source officielle (URL)", "Source secondaire (URL)", "Vérifié le"]


def ligne(**valeurs):
    base = {"ID": "FES-01", "Catégorie": "Festival", "Nom": "Festi Test",
            "Ville": "Neuchâtel", "Statut": "À CONTACTER", "Score /10": "6.5",
            "Priorité": "B", "Canal": "E-mail"}
    base.update(valeurs)
    return [base.get(e, "") for e in ENTETES]


def feuilles(lignes, top20=None, kit=None):
    f = {"Pilotage": [ENTETES] + lignes}
    if top20:
        f["TOP 20 global"] = [["Rang", "ID", "Nom", "Catégorie", "Score /10",
                               "Priorité", "Vague", "Pourquoi"]] + top20
    if kit:
        f["Vague 1 — Kit"] = [["Ordre", "ID", "Nom", "Meilleur canal", "Approche",
                               "Accroche", "Message J0", "Message J+3", "Message J+7",
                               "Message si intéressé", "Source officielle",
                               "Source secondaire", "Vérifié le"]] + kit
    return f


# ===========================================================================
print("\n" + "=" * 78)
print("P3-S2 — IMPORT DES PROSPECTS + ÉCRAN PROSPECTION")
print("=" * 78)

print("\n1. TRADUCTION DU CLASSEUR (fonction pure, aucune base)")

docs = I.traduire(feuilles([ligne()]), COACH_A)
verifier("1a. une ligne valide devient un document",
         len(docs) == 1 and docs[0]["ref"] == "FES-01"
         and docs[0]["category"] == "festival" and docs[0]["status"] == "a_contacter")
verifier("1b. les 8 categories du fichier tombent sur les 8 cles du serveur",
         all(I.traduire(feuilles([ligne(ID=p + "-01", **{"Catégorie": lib})]), COACH_A)[0]["category"] == cle
             for lib, cle, p in (("Festival", "festival", "FES"),
                                 ("École de danse", "ecole_danse", "ECO"),
                                 ("Restaurant", "restaurant", "RES"),
                                 ("Bar", "bar", "BAR"),
                                 ("Commerce", "commerce", "COM"),
                                 ("Organisateur", "organisateur_evenement", "ORG"),
                                 ("Communauté étudiante", "communaute_etudiante", "ETU"),
                                 ("Influenceur", "influenceur", "INF"))))
verifier("1c. toutes les cles produites existent dans P3S1_CATEGORIES",
         set(d["category"] for d in I.traduire(
             feuilles([ligne(ID=p + "-0%d" % i, **{"Catégorie": lib})
                       for i, (lib, p) in enumerate(
                           (("Festival", "FES"), ("Bar", "BAR"), ("Influenceur", "INF")), 1)]),
             COACH_A)) <= set(S.P3S1_CATEGORIES))

d = I.traduire(feuilles([ligne(**{"E-mail": "NON TROUVÉ (formulaire fen.ch)",
                                 "Téléphone": "NON TROUVÉ",
                                 "Instagram": "NON TROUVÉ (FB : sunsports)"})]), COACH_A)[0]
verifier("1d. « NON TROUVÉ » ne devient JAMAIS une coordonnée",
         d["public_email"] == "" and d["public_phone"] == "" and d["instagram"] == "")
verifier("1e. ... mais son texte est conservé en note, l'indice n'est pas perdu",
         "formulaire fen.ch" in d["notes"] and "sunsports" in d["notes"], d["notes"][:120])

d = I.traduire(feuilles([ligne(**{"E-mail": "(masqué sur le site)"})]), COACH_A)[0]
verifier("1f. une valeur qui n'est pas un e-mail est refusée comme e-mail",
         d["public_email"] == "" and "masqué" in d["notes"])

d = I.traduire(feuilles([ligne(**{"E-mail": "contact@akoko.ch"})]), COACH_A)[0]
verifier("1g. un vrai e-mail est conservé", d["public_email"] == "contact@akoko.ch")

d = I.traduire(feuilles([ligne()], top20=[["1", "FES-01", "X", "Festival", "9", "A", "Vague 1", ""]]),
               COACH_A)[0]
verifier("1h. la vague vient de « TOP 20 global », absente de « Pilotage »",
         d["wave"] == "Vague 1")
d = I.traduire(feuilles([ligne()]), COACH_A)[0]
verifier("1i. sans entrée au TOP 20, la vague reste vide — jamais inventée", d["wave"] == "")

d = I.traduire(feuilles([ligne()], kit=[["1", "FES-01", "X", "E-mail (a@b.ch)", "Appro",
                                         "", "Bonjour J0", "J+3", "J+7", "Intéressé",
                                         "https://s1", "https://s2", "31.08.2026"]]),
               COACH_A)[0]
verifier("1j. les messages viennent du Kit, pas du drapeau « Message prêt »",
         d["j0_message"] == "Bonjour J0" and d["j3_message"] == "J+3"
         and d["j7_message"] == "J+7" and d["interested_message"] == "Intéressé")
verifier("1k. le Kit fournit aussi canal, approche, sources et date de vérification",
         d["preferred_channel"] == "E-mail (a@b.ch)" and d["approach"] == "Appro"
         and d["source_url"] == "https://s1" and d["secondary_source_url"] == "https://s2"
         and d["verified_at"] == "31.08.2026")

d = I.traduire(feuilles([ligne(**{"Candidature": "Oui", "Accepté": "Oui",
                                  "Réservations": "12", "Conversions": "3"})]), COACH_A)[0]
verifier("1l. Candidature/Accepté/Réservations/Conversions ne sont PAS importés",
         "partner_id" not in d and "partner_application_id" not in d
         and not any(k in d for k in ("reservations", "conversions")))
verifier("1m. collaboration_type reste nul — le fichier ne le porte pas",
         d["collaboration_type"] is None)

d = I.traduire(feuilles([ligne(ID="ECO-01", **{"Catégorie": "École de danse",
                                               "Nom": "Giant Studio"})]), COACH_A)[0]
verifier("1n. Giant Studio porte sa note « relation chaude » en tête",
         d["notes"].startswith("RELATION CHAUDE"), d["notes"][:80])
verifier("1o. ... et AUCUN partner_id ne lui est fabriqué",
         d.get("partner_id") is None and d.get("partner_application_id") is None)

print("\n2. CE QUI EST REFUSÉ PLUTÔT QUE DEVINÉ")

base = BaseBouchon()
plan = lancer(I.planifier(base, I.traduire(
    feuilles([ligne(**{"Catégorie": "Salle de sport", "ID": "ZZZ-01"})]), COACH_A), COACH_A))
verifier("2a. catégorie inconnue -> invalide, jamais rangée dans « autre »",
         len(plan["invalides"]) == 1 and not plan["nouveaux"])

plan = lancer(I.planifier(base, I.traduire(
    feuilles([ligne(**{"Statut": "VENDU"})]), COACH_A), COACH_A))
verifier("2b. statut inconnu -> invalide", len(plan["invalides"]) == 1 and not plan["nouveaux"])

plan = lancer(I.planifier(base, I.traduire(
    feuilles([ligne(ID="BAR-01", **{"Catégorie": "Festival"})]), COACH_A), COACH_A))
verifier("2c. libellé et préfixe qui se contredisent -> invalide, pas un arbitrage",
         len(plan["invalides"]) == 1, str(plan["invalides"])[:150])

plan = lancer(I.planifier(base, I.traduire(
    feuilles([ligne(), ligne(**{"Nom": "Autre"})]), COACH_A), COACH_A))
verifier("2d. même ref deux fois dans le fichier -> conflit",
         len(plan["conflits"]) == 1 and len(plan["nouveaux"]) == 1)

base = BaseBouchon()
docs = I.traduire(feuilles([ligne()]), COACH_A)
lancer(I.appliquer(base, lancer(I.planifier(base, docs, COACH_A)), COACH_A))
plan = lancer(I.planifier(base, I.traduire(
    feuilles([ligne(ID="FES-99")]), COACH_A), COACH_A))
verifier("2e. même organisation+ville sous une AUTRE ref -> conflit, aucune fusion",
         len(plan["conflits"]) == 1 and not plan["nouveaux"],
         str(plan["conflits"])[:160])
verifier("2f. le conflit dit LAQUELLE, pour que l'humain tranche",
         "FES-01" in str(plan["conflits"][0][1]))

print("\n3. IDEMPOTENCE — LE POINT CENTRAL")

base = BaseBouchon()
lignes80 = [ligne(ID="%s-%02d" % (p, i), **{"Catégorie": lib, "Nom": "Org %s%d" % (p, i)})
            for lib, p in (("Festival", "FES"), ("Bar", "BAR"), ("Commerce", "COM"))
            for i in range(1, 11)]
docs = I.traduire(feuilles(lignes80), COACH_A)
p1 = lancer(I.planifier(base, docs, COACH_A))
verifier("3a. premier essai à blanc : tout est nouveau",
         len(p1["nouveaux"]) == 30 and not p1["identiques"] and not p1["conflits"])
p1bis = lancer(I.planifier(base, I.traduire(feuilles(lignes80), COACH_A), COACH_A))
verifier("3b. un second essai à blanc rend EXACTEMENT le même verdict",
         len(p1bis["nouveaux"]) == len(p1["nouveaux"])
         and len(p1bis["identiques"]) == len(p1["identiques"]))
verifier("3c. l'essai à blanc n'a rien écrit", base["partner_prospects"].ecritures == 0)

res = lancer(I.appliquer(base, p1, COACH_A))
verifier("3d. l'application crée les 30", res["crees"] == 30
         and len(base["partner_prospects"].documents) == 30)

p2 = lancer(I.planifier(base, I.traduire(feuilles(lignes80), COACH_A), COACH_A))
res2 = lancer(I.appliquer(base, p2, COACH_A))
verifier("3e. LE SECOND IMPORT N'EN CRÉE AUCUN DE PLUS — 30, pas 60",
         res2["crees"] == 0 and len(base["partner_prospects"].documents) == 30)
verifier("3f. il les reconnaît tous comme déjà présents", len(p2["identiques"]) == 30)

print("\n4. L'ÉTAT VIVANT N'EST JAMAIS ÉCRASÉ")

vivant = base["partner_prospects"].documents[0]
vivant["status"] = "repondu"
vivant["notes"] = "Rappelé le 12, très intéressé"
vivant["wave"] = "Vague 1"
vivant["replied_at"] = "2026-09-02T10:00:00+00:00"
enrichi = [ligne(ID=vivant["ref"], **{"Catégorie": "Festival", "Nom": vivant["organisation_name"],
                                      "Score /10": "9.5", "Priorité": "A",
                                      "Contact + rôle": "Marie — Responsable"})]
plan = lancer(I.planifier(base, I.traduire(feuilles(enrichi), COACH_A), COACH_A))
lancer(I.appliquer(base, plan, COACH_A))
apres = base["partner_prospects"].documents[0]
verifier("4a. la requalification Cowork est appliquée (score, priorité, contact)",
         apres["score"] == 9.5 and apres["priority"] == "A" and apres["contact_name"] == "Marie")
verifier("4b. le STATUT terrain survit à l'import", apres["status"] == "repondu")
verifier("4c. les NOTES terrain survivent", apres["notes"].startswith("Rappelé le 12"))
verifier("4d. la VAGUE posée à la main survit", apres["wave"] == "Vague 1")
verifier("4e. la date de réponse survit", apres["replied_at"] == "2026-09-02T10:00:00+00:00")
verifier("4f. les champs intouchables sont déclarés et cohérents",
         set(("status", "notes", "wave", "partner_id", "partner_application_id"))
         <= set(I.CHAMPS_INTOUCHABLES)
         and not (set(I.CHAMPS_INTOUCHABLES) & set(I.CHAMPS_REQUALIFIABLES)))

base2 = BaseBouchon()
lancer(I.appliquer(base2, lancer(I.planifier(base2, I.traduire(
    feuilles([ligne(**{"E-mail": "a@b.ch"})]), COACH_A), COACH_A)), COACH_A))
plan = lancer(I.planifier(base2, I.traduire(
    feuilles([ligne(**{"E-mail": "NON TROUVÉ"})]), COACH_A), COACH_A))
verifier("4g. un champ VIDÉ dans le fichier n'efface pas une valeur connue",
         not plan["mises_a_jour"] and len(plan["identiques"]) == 1)

print("\n5. AUCUN EFFET DE BORD")

base = BaseBouchon()
lancer(I.appliquer(base, lancer(I.planifier(base, I.traduire(feuilles(lignes80), COACH_A), COACH_A)), COACH_A))
ailleurs = base.ecritures_hors("partner_prospects")
verifier("5a. l'import n'écrit dans AUCUNE autre collection", ailleurs == {},
         "écritures parasites : %s" % ailleurs)
for intitule, col in (("5b. aucun user", "users"), ("5c. aucun lead", "leads"),
                      ("5d. aucun chat_participant", "chat_participants"),
                      ("5e. aucune chat_session", "chat_sessions"),
                      ("5f. aucun message", "chat_messages"),
                      ("5g. aucune notification", "notifications"),
                      ("5h. aucune réservation", "reservations"),
                      ("5i. aucun abonnement", "subscriptions"),
                      ("5j. aucun partenaire", "partners"),
                      ("5k. aucun code d'accès", "discount_codes")):
    verifier(intitule, base[col].ecritures == 0 and base[col].documents == [])

SOURCE_IMPORT = open(os.path.join(RACINE, "tests", "import_prospects_cowork.py"), encoding="utf-8").read()
INTERDITS = ("resend", "webpush", "send_whatsapp", "send_email", "send_push",
             "graph.facebook.com", "smtplib", "requests.post")
trouves = [i for i in INTERDITS if i in SOURCE_IMPORT.lower()]
verifier("5l. l'importeur ne contient AUCUN canal d'envoi", not trouves, str(trouves))

print("\n6. LA ROUTE DE LISTE ÉTENDUE (offset + compteurs)")

base = BaseBouchon()
lancer(I.appliquer(base, lancer(I.planifier(base, I.traduire(feuilles(lignes80), COACH_A), COACH_A)), COACH_A))
S.db = base
J_A = jeton(COACH_A)

r = lancer(S.p3s1_lister_prospects(RequeteFictive(jeton_=J_A)))
verifier("6a. la liste est plafonnée à 50 mais annonce le total réel",
         r["returned"] == 30 and r["total"] == 30 and r["limit"] == 50)
verifier("6b. la réponse porte offset et counts",
         "offset" in r and "counts" in r)
verifier("6c. les compteurs couvrent les 6 statuts + total + candidature + accepté",
         set(S.P3S1_STATUTS) | {"total", "candidature", "accepte"} <= set(r["counts"]))
verifier("6d. counts.total = 30, counts.a_contacter = 30",
         r["counts"]["total"] == 30 and r["counts"]["a_contacter"] == 30)
verifier("6e. candidature et accepté valent 0 — aucun compteur P2 recopié",
         r["counts"]["candidature"] == 0 and r["counts"]["accepte"] == 0)

page1 = lancer(S.p3s1_lister_prospects(RequeteFictive(jeton_=J_A, params={"limit": "10", "offset": "0"})))
page2 = lancer(S.p3s1_lister_prospects(RequeteFictive(jeton_=J_A, params={"limit": "10", "offset": "10"})))
page3 = lancer(S.p3s1_lister_prospects(RequeteFictive(jeton_=J_A, params={"limit": "10", "offset": "20"})))
ids = [p["id"] for p in page1["prospects"] + page2["prospects"] + page3["prospects"]]
verifier("6f. trois pages de 10 rendent 30 prospects DISTINCTS",
         len(ids) == 30 and len(set(ids)) == 30)
verifier("6g. aucune page ne se recouvre",
         not (set(p["id"] for p in page1["prospects"]) & set(p["id"] for p in page2["prospects"])))
verifier("6h. offset au-delà du total rend une page vide, pas une erreur",
         lancer(S.p3s1_lister_prospects(
             RequeteFictive(jeton_=J_A, params={"offset": "999"})))["returned"] == 0)

r = lancer(S.p3s1_lister_prospects(RequeteFictive(jeton_=J_A, params={"category": "bar"})))
verifier("6i. un filtre restreint la liste MAIS PAS les tuiles",
         r["total"] == 10 and r["counts"]["total"] == 30)

J_B = jeton(COACH_B)
r = lancer(S.p3s1_lister_prospects(RequeteFictive(jeton_=J_B)))
verifier("6j. le coach B ne voit rien du coach A, compteurs inclus",
         r["total"] == 0 and r["counts"]["total"] == 0)

print("\n7. LE CLASSEUR RÉEL")

CHEMIN = I.CHEMIN_DEFAUT
if not os.path.exists(CHEMIN):
    non_joue("7a-7f. bout en bout sur le vrai classeur", "fichier absent : %s" % CHEMIN)
else:
    f = I.lire_classeur(CHEMIN)
    verifier("7a. le classeur porte les 5 feuilles attendues",
             {"Pilotage", "Vague 1 — Kit", "TOP 20 global"} <= set(f), str(list(f)))
    verifier("7b. « Pilotage » contient 80 prospects", len(f["Pilotage"]) - 1 == 80,
             "lignes : %d" % (len(f["Pilotage"]) - 1))
    reels = I.traduire(f, COACH_A)
    verifier("7c. les 80 sont traduits", len(reels) == 80)
    verifier("7d. les 80 tombent sur des catégories connues du serveur",
             all(d["category"] in S.P3S1_CATEGORIES for d in reels))
    verifier("7e. les 80 démarrent en « a_contacter »",
             all(d["status"] == "a_contacter" for d in reels))
    verifier("7f. chacun porte une ref unique",
             len(set(d["ref"] for d in reels)) == 80)
    b = BaseBouchon()
    plan = lancer(I.planifier(b, reels, COACH_A))
    verifier("7g. essai à blanc : 80 nouveaux, 0 conflit, 0 invalide",
             len(plan["nouveaux"]) == 80 and not plan["conflits"] and not plan["invalides"],
             "n=%d c=%d i=%d" % (len(plan["nouveaux"]), len(plan["conflits"]), len(plan["invalides"])))
    lancer(I.appliquer(b, plan, COACH_A))
    verifier("7h. application : 80 créés, aucune autre collection touchée",
             len(b["partner_prospects"].documents) == 80
             and b.ecritures_hors("partner_prospects") == {})
    plan2 = lancer(I.planifier(b, I.traduire(f, COACH_A), COACH_A))
    lancer(I.appliquer(b, plan2, COACH_A))
    verifier("7i. RÉIMPORT DU VRAI FICHIER : toujours 80, jamais 160",
             len(b["partner_prospects"].documents) == 80)

    vague1 = [d for d in reels if d["wave"] == "Vague 1"]
    verifier("7j. la Vague 1 compte 10 lignes (les 9 commerciales + Giant)",
             len(vague1) == 10, "trouvees : %d" % len(vague1))
    giant = [d for d in reels if d["ref"] == "ECO-01"]
    verifier("7k. Giant Studio est dans la Vague 1 et porte sa note distincte",
             giant and giant[0]["wave"] == "Vague 1"
             and giant[0]["notes"].startswith("RELATION CHAUDE"))
    NEUF = ("SUN", "FEN", "ESN", "Akoko", "Okapi", "Ébène", "LAKAY", "Venus", "BDE")
    noms = " | ".join(d["organisation_name"] for d in vague1)
    verifier("7l. les 9 prospects commerciaux annoncés sont bien dans la Vague 1",
             all(n in noms for n in NEUF), noms[:180])
    verifier("7m. les 10 de la Vague 1 ont leurs 4 messages prêts",
             all(d["j0_message"] and d["j3_message"] and d["j7_message"]
                 and d["interested_message"] for d in vague1))
    verifier("7n. aucun prospect ne porte de pointeur P2",
             all(d.get("partner_id") is None and d.get("partner_application_id") is None
                 for d in reels))

print("\n8. L'ÉCRAN — CE QU'IL NE FAIT PAS")

ECRAN = open(os.path.join(RACINE, "frontend", "src", "components", "coach",
                          "ProspectsSection.js"), encoding="utf-8").read()
verifier("8a. l'écran n'appelle QUE les routes partner-prospects",
         set(re.findall(r"\$\{base\}/([a-z-]+)", ECRAN)) == {"partner-prospects"},
         str(set(re.findall(r"\$\{base\}/([a-z-]+)", ECRAN))))
verifier("8b. aucune méthode d'écriture autre que PATCH",
         "axios.post" not in ECRAN and "axios.delete" not in ECRAN
         and "axios.put" not in ECRAN and "axios.patch" in ECRAN)
verifier("8c. AUCUN bouton d'envoi — c'est P3-S3",
         not re.search(r">\s*(Envoyer|Contacter|Relancer)\b", ECRAN))
verifier("8d. aucune couleur imposée : tout hex est un repli de var()",
         all("var(--primary" in ECRAN[max(0, m.start() - 60):m.start()]
             for m in re.finditer(r"#D91CD2", ECRAN)))
verifier("8e. aucune icône emoji — SVG uniquement",
         "SvgIcon" in ECRAN and not re.search(r"[\U0001F300-\U0001FAFF]", ECRAN))
verifier("8f. les liens externes portent rel=noopener",
         'rel="noopener noreferrer"' in ECRAN and 'target="_blank"' in ECRAN)
verifier("8g. les dépendances de chargement sont des chaînes, pas l'objet filtres",
         "deps: [base, signature]" in ECRAN.replace("{ deps: [base, signature] }",
                                                    "deps: [base, signature]"))
verifier("8h. aucun setInterval — rien qui sonde en boucle", "setInterval" not in ECRAN)
verifier("8i. les 8 catégories et 6 statuts de l'écran sont ceux du serveur",
         set(re.findall(r"cle: '([a-z_]+)', libelle", ECRAN)) >=
         set(S.P3S1_CATEGORIES) | set(S.P3S1_STATUTS))

DASH = open(os.path.join(RACINE, "frontend", "src", "components", "CoachDashboard.js"),
            encoding="utf-8").read()
verifier("8j. l'onglet Prospection est branché dans le dashboard existant",
         'id: "prospection"' in DASH and "<ProspectsSection" in DASH)
verifier("8k. aucune application parallèle : un onglet, pas une route",
         DASH.count("<ProspectsSection") == 1)

# ===========================================================================
print("\n" + "=" * 78)
_ok = sum(1 for _, c, _ in RESULTATS if c)
print("RESULTAT : %d/%d" % (_ok, len(RESULTATS)))
if NON_JOUES:
    print("NON JOUES : %d" % len(NON_JOUES))
    for intitule, raison in NON_JOUES:
        print("  - %s  (%s)" % (intitule, raison))
if _ok != len(RESULTATS):
    print("\nECHECS :")
    for intitule, cond, detail in RESULTATS:
        if not cond:
            print("  - %s   %s" % (intitule, detail))
print("=" * 78)
sys.exit(0 if _ok == len(RESULTATS) else 1)
