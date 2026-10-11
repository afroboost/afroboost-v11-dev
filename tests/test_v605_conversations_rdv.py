#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V605 — Conversations partenaires : langue, traduction protégée, rendez-vous public, rappel.

    python3 tests/test_v605_conversations_rdv.py
"""
import asyncio
import io
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ["JWT_SECRET"] = "secret-de-test-v605-sans-rapport-avec-la-production"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v605-inexistant:27017")

import api.server as S  # noqa: E402
from fastapi import HTTPException  # noqa: E402

RESULTATS = []


def verifier(intitule, condition, detail=""):
    RESULTATS.append((intitule, bool(condition)))
    print("  %-6s %s" % ("OK  " if condition else "ECHEC", intitule))
    if detail and not condition:
        print("           -> %s" % detail)


def _ok(doc, filtre):
    for k, v in filtre.items():
        val = doc.get(k)
        if isinstance(v, dict):
            if "$ne" in v and val == v["$ne"]:
                return False
            if "$in" in v and val not in v["$in"]:
                return False
        elif val != v:
            return False
    return True


class Curseur:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *_a, **_k):
        return self

    def skip(self, n):
        self.docs = self.docs[n:]
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    async def to_list(self, _n):
        return [dict(d) for d in self.docs]

    def __aiter__(self):
        self._it = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return dict(next(self._it))
        except StopIteration:
            raise StopAsyncIteration


class Collection:
    def __init__(self):
        self.docs = []

    def find(self, filtre, _proj=None):
        return Curseur([d for d in self.docs if _ok(d, filtre)])

    async def find_one(self, filtre, _proj=None, **_k):
        for d in self.docs:
            if _ok(d, filtre):
                return dict(d)
        return None

    async def count_documents(self, filtre):
        return len([d for d in self.docs if _ok(d, filtre)])

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, filtre, maj, upsert=False):
        for d in self.docs:
            if _ok(d, filtre):
                d.update(maj.get("$set", {}))
                return
        if upsert:                                   # V598 : inscription idempotente ($setOnInsert)
            self.docs.append(dict(filtre, **maj.get("$setOnInsert", {}), **maj.get("$set", {})))

    async def delete_one(self, filtre):
        avant = len(self.docs)
        self.docs = [d for d in self.docs if not _ok(d, filtre)]
        self.supprimes = getattr(self, "supprimes", 0) + (avant - len(self.docs))

    async def update_many(self, filtre, maj):
        n = 0
        for d in self.docs:
            if _ok(d, filtre):
                d.update(maj["$set"])
                n += 1
        return type("R", (), {"modified_count": n})()


class Base(dict):
    def __getattr__(self, nom):
        return self[nom]

    def __getitem__(self, nom):
        if nom not in self:
            dict.__setitem__(self, nom, Collection())
        return dict.__getitem__(self, nom)


BASE = Base()
S.db = BASE
COACH = "coach.v605@exemple.test"


class Requete:
    def __init__(self, corps=None, coach=COACH):
        self._corps = corps
        self.query_params = {}
        self.coach = coach

    async def json(self):
        return self._corps


async def _auth(requete):
    if not getattr(requete, "coach", None):
        raise HTTPException(status_code=403, detail="Authentification coach requise")
    return requete.coach


S._v309_require_coach_or_admin = _auth


def lancer(c):
    return asyncio.run(c)


def statut_http(coroutine):
    try:
        lancer(coroutine)
        return 200
    except HTTPException as e:
        return e.status_code


def fichier(fid, nom, mime, coach=COACH, taille=1000):
    BASE.uploaded_files.docs.append({"file_id": fid, "filename": nom, "content_type": mime,
                                     "coach_email": coach, "size": taille, "original_name": nom,
                                     "asset_type": "video" if mime.startswith("video/") else "image"})
    return "/api/files/%s/%s" % (fid, nom)

from datetime import datetime, timezone, timedelta
from pymongo.errors import DuplicateKeyError
_ins = Collection.insert_one
async def _insert_unique(self, doc):
    if doc.get("creneau_cle") and any(d.get("creneau_cle") == doc["creneau_cle"] and d.get("coach_id") == doc.get("coach_id") for d in self.docs):
        raise DuplicateKeyError("E11000 creneau")
    await _ins(self, doc)
Collection.insert_one = _insert_unique
S.is_super_admin = lambda e: False

L = S.v605_lecture
H = S.V604_HUMAINE
print("\n1. Langue + intention de rendez-vous (10 cas)")
cas = {
 "1 visio FR": ({"body_text": "Oui, faisons une visio la semaine prochaine, je suis disponible.", "nature_reponse": H}, "fr", True, ""),
 "2 Termin DE": ({"body_text": "Guten Tag, gerne können wir einen Termin vereinbaren und kurz telefonieren. Freundliche Grüsse", "nature_reponse": H}, "de", True, ""),
 "3 call EN": ({"body_text": "Hello, thanks for your email. Let's schedule a call, we would be happy to meet you.", "nature_reponse": H}, "en", True, ""),
 "4 Calendly": ({"body_text": "Bonjour, avec plaisir, prenez rendez-vous ici : https://calendly.com/denis/30min merci", "nature_reponse": H}, "fr", True, "https://calendly.com/denis/30min"),
 "5 Troodi": ({"body_text": "Bonjour\nSuper ! Merci pour votre message.\nJe vous laisse insérer un créneau pour une visio afin d’en\ndiscuter ?\nwww.troodi.ch/agenda\nMerci beaucoup et bon dimanche\nDenis\nwww.troodi.ch [http://www.trOOdi.ch]  079 671 39 55", "nature_reponse": H}, "fr", True, "https://www.troodi.ch/agenda"),
 "6 refus": ({"body_text": "Bonjour, merci mais nous ne sommes pas intéressés. Pas besoin d'un appel.", "nature_reponse": H}, "fr", False, ""),
 "7 automatique": ({"body_text": "Je suis absent, appelez le secrétariat pour un rendez-vous.", "nature_reponse": S.V604_AUTOMATIQUE}, "fr", False, ""),
}
for nom, (m, lang, rdv, agenda) in cas.items():
    r = L(m)
    verifier("%-14s langue=%s rdv=%s agenda=%s" % (nom, lang, rdv, agenda or "-"),
             r["langue"] == lang and r["rdv_souhaite"] == rdv and r["agenda_externe"] == agenda, str(r))
verifier("réel SalsaRica « nicht interssiert » (faute) → négatif, aucun RDV",
         L({"body_text": "Hola Bassi\n\nDanke für deine Anfrage, aber wir sind nicht interssiert\n\nFreundliche Grüsse", "nature_reponse": H})["tonalite"] == "negative")
verifier("réel BDE « on en parlera au sein du comité » → PAS une demande de RDV",
         not L({"body_text": "Bonjour, merci pour les infos, on en parlera au sein du comité, on vous tiendra au courant !", "nature_reponse": H})["rdv_souhaite"])
verifier("réel FAANG « convenir d'un moment d'échange » → RDV souhaité",
         L({"body_text": "Nous prendrons volontiers le temps de discuter. Je reviendrai vers vous pour convenir d'un moment d'échange.", "nature_reponse": H})["rdv_souhaite"])
verifier("Troodi : réponse positive", L(cas["5 Troodi"][0])["tonalite"] == "positive")
verifier("refus : tonalité négative", L(cas["6 refus"][0])["tonalite"] == "negative")
verifier("message trop court : langue indécidable ''", S.v605_langue("Merci") == "")

print("\n2. Protection avant traduction")
txt = "Guten Tag, bitte buchen Sie unter www.troodi.ch/agenda oder rufen Sie 079 671 39 55 an, am 15.11. um 14:30, Preis 250 CHF, BCV — Banque Cantonale Vaudoise, Afroboost."
masque, table = S.v605_proteger(txt, ["BCV — Banque Cantonale Vaudoise"])
verifier("URL, téléphone, date, heure, montant, organisation, Afroboost masqués",
         all(x in table for x in ["www.troodi.ch/agenda", "BCV — Banque Cantonale Vaudoise", "Afroboost", "14:30"]) and "troodi" not in masque, str((masque, table)))
verifier("restauration exacte", S.v605_restaurer(masque, table) == txt)
try:
    S.v605_restaurer(masque.replace("⟦P1⟧", ""), table); perdu = False
except ValueError:
    perdu = True
verifier("une balise perdue → traduction REFUSÉE (jamais rendue cassée)", perdu)

print("\n3. Traduction (IA simulée) : FR→DE, FR→EN, DE→FR, original conservé, aucun envoi")
import types
appels = []
class _Rep:
    def __init__(self, t): self.choices = [types.SimpleNamespace(message=types.SimpleNamespace(content=t))]
class _FakeClient:
    def __init__(self, **k): self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))
    def create(self, model, messages, **k):
        appels.append(messages)
        u = messages[1]["content"]; sysm = messages[0]["content"]
        if "allemand" in sysm: return _Rep("Gerne! Hier ist der Link: " + " ".join(re.findall(r"⟦P\d+⟧", u)))
        if "anglais" in sysm: return _Rep("With pleasure! Here is the link: " + " ".join(re.findall(r"⟦P\d+⟧", u)))
        return _Rep("Bonjour, volontiers, réservez sur " + " ".join(re.findall(r"⟦P\d+⟧", u)))
import re
sys.modules["openai"] = types.SimpleNamespace(OpenAI=_FakeClient)
os.environ["OPENAI_API_KEY"] = "cle-de-test"
I = BASE[S.P3U2_COLLECTION]; A = BASE[S.P3S3_ACTIONS]; C = BASE[S.CAL1_COLLECTION]
A.docs.append({"id": "act1", "coach_id": COACH, "organisations": ["Troodi"], "prospect_ids": ["E-01"], "recipient_key": "rk1",
               "campaign_id": "camp1", "sent_at": "2026-10-11T08:09:00+00:00", "j3_due_at": "2026-10-14T08:09:00+00:00"})
I.docs.append({"id": "in1", "coach_id": COACH, "action_id": "act1",
               "body_text": "Guten Tag, gerne einen Termin unter www.troodi.ch/agenda vereinbaren. Freundliche Grüsse"})
avant = dict(I.docs[0])
r = lancer(S.v605_traduire_message("in1", Requete({})))
verifier("DE → FR traduit, URL exacte", "www.troodi.ch/agenda" in r["traduction"] and r["langue"] == "de", str(r))
verifier("original INCHANGÉ en base", I.docs[0]["body_text"] == avant["body_text"] and I.docs[0]["traduction_fr"] == r["traduction"])
n = len(appels); lancer(S.v605_traduire_message("in1", Requete({})))
verifier("2e clic : traduction en cache, aucun nouvel appel IA", len(appels) == n)
r = lancer(S.v605_traduire_reponse("in1", Requete({"texte": "Avec plaisir, voici le lien https://afroboost.com/rdv/abc", "langue": "de"})))
verifier("FR → DE : brouillon traduit, lien conservé, envoye=False", "https://afroboost.com/rdv/abc" in r["traduction"] and r["envoye"] is False and r["traduction"].startswith("Gerne"), str(r))
r = lancer(S.v605_traduire_reponse("in1", Requete({"texte": "Merci, à bientôt", "langue": "en"})))
verifier("FR → EN : brouillon traduit", r["traduction"].startswith("With pleasure"), str(r))
verifier("aucun e-mail envoyé par la traduction", not BASE["prospect_outbound"].docs if "prospect_outbound" in BASE else True)
verifier("sans jeton → 403", statut_http(S.v605_traduire_reponse("in1", Requete({"texte": "x"}, coach=None))) == 403)
verifier("message d'un autre coach → 404", statut_http(S.v605_traduire_message("in1", Requete({}, coach="autre@x.test"))) == 404)

print("\n4. Lien de rendez-vous + page publique")
lien = lancer(S.v605_lien_rdv("in1", Requete({})))
jeton = A.docs[0]["rdv_token"]
verifier("lien /rdv/<jeton>, jeton aléatoire ≥ 16 car., aucune donnée sensible", lien["lien"].endswith("/rdv/" + jeton) and len(jeton) >= 16 and "@" not in lien["lien"] and lien["envoye"] is False)
verifier("2e demande : MÊME jeton", lancer(S.v605_lien_rdv("in1", Requete({})))["lien"] == lien["lien"])
class Pub:
    def __init__(self, corps=None): self._c = corps; self.headers = {}; self.client = types.SimpleNamespace(host="1.2.3.4")
    async def json(self): return self._c
pub = lancer(S.v605_public_creneaux(jeton, Pub()))
verifier("public : créneaux proposés, aucun e-mail ni identifiant interne", pub["creneaux"] and pub["organisation"] == "Troodi" and "coach_id" not in str(pub) and COACH not in str(pub))
from zoneinfo import ZoneInfo
loc = [datetime.fromisoformat(c).astimezone(ZoneInfo("Europe/Zurich")) for c in pub["creneaux"]]
verifier("créneaux : lun-ven, 09:00-17:30 Zurich, jamais dans moins de 12 h",
         all(d.weekday() < 5 and 9 <= d.hour < 18 for d in loc) and min(loc) >= datetime.now(timezone.utc) + timedelta(hours=11, minutes=59))
verifier("jeton inconnu → 404", statut_http(S.v605_public_creneaux("x" * 20, Pub())) == 404)
creneau = pub["creneaux"][3]
C.docs.append({"id": "occupe", "coach_id": COACH, "event_type": "appointment", "status": "prevu", "starts_at": pub["creneaux"][0],
               "ends_at": (datetime.fromisoformat(pub["creneaux"][0]) + timedelta(minutes=30)).isoformat()})
verifier("un RDV existant retire son créneau", pub["creneaux"][0] not in lancer(S.v605_public_creneaux(jeton, Pub()))["creneaux"])
verifier("créneau occupé → 409", statut_http(S.v605_public_confirmer(jeton, Pub({"starts_at": pub["creneaux"][0], "type": "visio"}))) == 409)

print("\n5. Confirmation, double réservation, relances arrêtées")
A.docs.append({"id": "act2", "coach_id": COACH, "organisations": ["BCV"], "prospect_ids": ["E-02"], "rdv_token": "jetonDeuxiemePartenaire01",
               "sent_at": "2026-10-11T08:09:00+00:00"})
async def deux_en_meme_temps():
    return await asyncio.gather(S.v605_public_confirmer(jeton, Pub({"starts_at": creneau, "type": "visio"})),
                                S.v605_public_confirmer("jetonDeuxiemePartenaire01", Pub({"starts_at": creneau, "type": "appel"})),
                                return_exceptions=True)
res = asyncio.run(deux_en_meme_temps())
ok = [r for r in res if isinstance(r, dict) and r.get("confirme")]
refus = [r for r in res if isinstance(r, HTTPException) and r.status_code == 409]
verifier("même créneau, deux partenaires simultanés → UN confirmé, l'autre 409", len(ok) == 1 and len(refus) == 1, str(res))
ev = [d for d in C.docs if d.get("rdv_token") == jeton]
verifier("RDV dans l'agenda existant : appointment confirmé, prospect, organisation, durée, type, origine",
         len(ev) == 1 and ev[0]["event_type"] == "appointment" and ev[0]["status"] == "confirme" and ev[0]["prospect_id"] == "E-01"
         and ev[0]["duration_minutes"] == 30 and ev[0]["meeting_type"] == "visio" and ev[0]["origine"] == "prospection_partenaire" and "Troodi" in ev[0]["title"], str(ev))
a1 = A.docs[0]
verifier("relances restantes annulées, motif RENDEZ_VOUS_PLANIFIE", all(a1.get(e + "_annule_motif") == "RENDEZ_VOUS_PLANIFIE" for e in ("j3", "j7", "j14")))
verifier("garde de relance : J+3 refusée ensuite", S.p3r2_garde_relance(a1, {"etat": "approuvee"}, "j3", set(), "2026-10-15T00:00:00+00:00")["code"] == "RELANCE_ANNULEE")
again = lancer(S.v605_public_confirmer(jeton, Pub({"starts_at": pub["creneaux"][5], "type": "visio"})))
verifier("2e confirmation avec le même lien → le RDV existant (aucun doublon)", again["deja"] and len([d for d in C.docs if d.get("rdv_token") == jeton]) == 1)
verifier("page publique ensuite : « déjà réservé »", lancer(S.v605_public_creneaux(jeton, Pub()))["deja_reserve"])
conv = [{"action_id": "act1"}]; lancer(S.v605_agenda_des_conversations(conv))
verifier("RDV visible dans la conversation", conv[0]["rendez_vous"] and conv[0]["rendez_vous"]["type"] == "visio")

print("\n6. « Recontactez-moi le mois prochain » → UNE tâche agenda")
ref = datetime(2026, 10, 11, tzinfo=timezone.utc)
verifier("« rappelez-moi le mois prochain » → 2026-11-01", (S.v604_date_suivi("Rappelez-moi le mois prochain", ref)[0] or "").startswith("2026-11-01"))
verifier("« revenez vers moi le 15 novembre » → 2026-11-15", (S.v604_date_suivi("Revenez vers moi le 15 novembre", ref)[0] or "").startswith("2026-11-15"))
verifier("« contactez-moi en janvier » → 2027-01-01 (inchangé)", (S.v604_date_suivi("Contactez-moi en janvier", ref)[0] or "").startswith("2027-01-01"))
A.docs.append({"id": "act3", "coach_id": COACH, "organisations": ["Viteos SA"], "prospect_ids": ["E-03"]})
lancer(S.v605_creer_tache_suivi(A.docs[-1], "2026-11-01T08:00:00+00:00", "rappelez-moi le mois prochain", "in9"))
lancer(S.v605_creer_tache_suivi(A.docs[-1], "2026-11-01T08:00:00+00:00", "rappelez-moi le mois prochain", "in9"))
t = [d for d in C.docs if d.get("campaign_action_id") == "act3"]
verifier("une seule tâche (idempotent), liée au prospect, aucun envoi", len(t) == 1 and t[0]["event_type"] == "task" and t[0]["prospect_id"] == "E-03")

ok = sum(1 for _, v in RESULTATS if v); print("\n%d/%d vérifications réussies" % (ok, len(RESULTATS))); sys.exit(0 if ok == len(RESULTATS) else 1)
