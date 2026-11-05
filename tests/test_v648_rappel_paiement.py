#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V648 — rappel du deuxième paiement. FOURNISSEUR SIMULÉ, base locale jetable.

Aucun réseau, aucun e-mail : `rappels_paiement.resend` est remplacé par un faux, et la base
est `afroboost_v648_test` sur 127.0.0.1 (le script refuse toute autre adresse).
"""
import asyncio
import hashlib
import inspect
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
ADRESSE = "mongodb://127.0.0.1:27017"
BASE = "afroboost_v648_test"
os.environ["MONGO_URL"] = ADRESSE
os.environ["DB_NAME"] = BASE
os.environ["JWT_SECRET"] = "v648-secret-local"
os.environ["RESEND_API_KEY"] = "re_faux_local_jamais_reel"

import httpx  # noqa: E402
import jwt  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from api import resend_central as rc  # noqa: E402
from api.routes import promo_routes  # noqa: E402
from api.routes import rappels_paiement as rp  # noqa: E402

echecs = []


def v(nom, cond, detail=""):
    print(("OK   " if cond else "FAIL ") + nom + (f"  -> {detail}" if not cond else ""))
    if not cond:
        echecs.append(nom)


ADMIN = "contact.artboost@gmail.com"
PARTENAIRE = "partenaire@example.test"
AUTRE = "autre-coach@example.test"
AUJ = datetime.now(timezone.utc).date()
D = lambda n: (AUJ + timedelta(days=n)).strftime("%Y-%m-%d")  # noqa: E731


def jeton(email):
    return {"Authorization": "Bearer " + jwt.encode({"email": email, "sub": email}, os.environ["JWT_SECRET"], algorithm="HS256")}


def abo(**k):
    d = {"id": "s1", "code": "CODE-1", "status": "active", "email": "cliente@example.test", "name": "Marie Dupont",
         "montant_encaisse": 200, "devise": "CHF",
         "suivi_paiement": {"montant_total": 400, "plusieurs_fois": True, "nb_paiements": 2, "paiement_actuel": 1,
                            "prochaine_echeance": D(0)}}
    d.update(k)
    return d


def suivi(**k):
    s = {"montant_total": 400, "plusieurs_fois": True, "nb_paiements": 2, "paiement_actuel": 1, "prochaine_echeance": D(0)}
    s.update(k)
    return {kk: vv for kk, vv in s.items() if vv is not None}


# ══════════════════════ FAUX FOURNISSEUR ══════════════════════
class ErreurResend(Exception):
    def __init__(self, code):
        super().__init__("faux")
        self.code = code


class FauxEmails:
    def __init__(self):
        self.appels, self.reponse, self.delai = [], None, 0

    def send(self, params, options=None):
        self.appels.append((params, options))
        if self.delai:
            import time
            time.sleep(self.delai)
        r = self.reponse
        if isinstance(r, Exception):
            raise r
        return r if r is not None else {"id": "em_%d" % len(self.appels)}


class FauxResend:
    def __init__(self):
        self.Emails = FauxEmails()


# ══════════════════════ RÈGLES PURES ══════════════════════
print("── Règles pures")
e = rp.eligibilite
v("cas normal : éligible, 200 restants", e(abo())["ok"] and e(abo())["reste"] == 200)
v("BASSBOOSTX-11 (case non cochée) : possible, avec avertissement, exclu de l'automatique",
  (lambda r: r["ok"] and r["incomplet"] and "plusieurs fois" in r["avertissement"])(
      e(abo(suivi_paiement={"montant_total": 400, "prochaine_echeance": D(0)}))))
v("AFR-B12426 (saison_2x + total saisi) : exclu",
  e(abo(billing_mode="saison_2x", stripe_subscription_id="sub_x", montant_encaisse=199.99))["motif"] == "stripe_recurrent")
v("Stripe : exclu par le seul identifiant d'abonnement", e(abo(stripe_subscription_id="sub_x"))["motif"] == "stripe_recurrent")
v("Stripe : exclu par le seul billing_mode", e(abo(billing_mode="mensuel_auto"))["motif"] == "stripe_recurrent")
v("Stripe : exclu par la seule offre", e(abo(), None, {"billing_mode": "saison_2x"})["motif"] == "stripe_recurrent")
v("CHRISTOUX10 (retard, code sans e-mail) : éligible, e-mail de l'abonnement",
  (lambda r: r["ok"] and r["destinataire"] == "cliente@example.test")(
      e(abo(suivi_paiement=suivi(prochaine_echeance=D(-2))), {"assignedEmail": ""})))
v("solde réglé : refusé", e(abo(montant_encaisse=400))["motif"] == "solde_nul")
v("encaissé inconnu : refusé, jamais « reste = total »", e(abo(montant_encaisse=None))["motif"] == "solde_inconnu")
v("total inconnu : refusé", e(abo(suivi_paiement={"prochaine_echeance": D(0)}))["motif"] == "solde_inconnu")
v("encaissé > total : incohérent", e(abo(montant_encaisse=500))["motif"] == "suivi_incoherent")
v("encaissé = 0 : incohérent (aucun premier paiement)", e(abo(montant_encaisse=0))["motif"] == "suivi_incoherent")
v("reste de 0.01 : un arrondi, pas une dette", e(abo(montant_encaisse=399.99))["motif"] == "suivi_incoherent")
v("dernier paiement fait + solde : incohérent", e(abo(suivi_paiement=suivi(paiement_actuel=2)))["motif"] == "suivi_incoherent")
v("sans échéance : refusé", e(abo(suivi_paiement=suivi(prochaine_echeance=None)))["motif"] == "sans_echeance")
v("échéance illisible : incohérent", e(abo(suivi_paiement=suivi(prochaine_echeance="2026-13-45")))["ok"] is False)
v("échéance à +30 j : hors fenêtre", e(abo(suivi_paiement=suivi(prochaine_echeance=D(30))))["motif"] == "hors_fenetre")
v("sans e-mail : refusé", e(abo(email=""))["motif"] == "sans_email")
v("e-mail illisible : refusé", e(abo(email="pas-une-adresse"))["motif"] == "sans_email")
v("adresses code ≠ abonnement : refusé", e(abo(), {"assignedEmail": "autre@example.test"})["motif"] == "destinataire_ambigu")
v("abonnement remplacé : refusé", e(abo(status="superseded"))["motif"] == "aucun_abonnement_actuel")
v("plusieurs abonnements actifs : refusé", e(abo(), None, None, "plusieurs")["motif"] == "plusieurs_abonnements")

print("── Message")
m = rp.construire_message("Marie", 200, "CHF", "2026-11-05", "Coach Bassi, d'Afroboost")
ATTENDU = ("Bonjour Marie,\n\nPetit rappel amical : il reste 200 CHF à régler pour ton abonnement Afroboost, prévu le 05.11.2026.\n\n"
           "Si tu as déjà payé, ne tiens pas compte de ce message. Pour toute question, réponds simplement à cet e-mail.\n\n"
           "À très vite en cours !\nCoach Bassi, d'Afroboost")
v("texte validé, au caractère près", m["texte"] == ATTENDU, m["texte"])
v("objet validé", m["sujet"] == "Rappel : ton deuxième paiement Afroboost")
v("sans prénom : « Bonjour, »", rp.construire_message("", 200, "CHF", "2026-11-05", "x")["texte"].startswith("Bonjour,\n"))
v("montant avec centimes", "200.50 CHF" in rp.construire_message("", 200.5, "CHF", "2026-11-05", "x")["texte"])
v("3e paiement : « prochain », pas « deuxième »", "prochain" in rp.construire_message("", 100, "CHF", "2026-11-05", "x", 2)["sujet"])
x = rp.construire_message("<script>alert(1)</script>", 200, "CHF", "2026-11-05", "x")
v("prénom échappé dans le HTML", "<script>" not in x["html"] and "&lt;script&gt;" in x["html"])
v("aucun lien dans le message", "http" not in m["html"] and "http" not in m["texte"])
v("signature de Bassi sur un code sans propriétaire", rp.signature_du_code({"coach_id": ""}) == "Coach Bassi, d'Afroboost")
v("signature de Bassi sur son code", rp.signature_du_code({"coach_id": ADMIN}) == "Coach Bassi, d'Afroboost")
v("un partenaire ne signe jamais Bassi", rp.signature_du_code({"coach_id": PARTENAIRE}, {"name": "Lea"}) == "Coach Lea, d'Afroboost")
v("partenaire sans nom : neutre", rp.signature_du_code({"coach_id": PARTENAIRE}) == "Ton coach, d'Afroboost")

print("── Erreurs du fournisseur")
c = rp.classer_erreur
v("adresse refusée (422) : échec certain", c(ErreurResend(422)) == "echec")
v("trop de requêtes (429) : échec certain", c(ErreurResend(429)) == "echec")
v("quota local : échec certain", c(rc.QuotaResendAtteint(95, 95, False)) == "echec")
v("erreur serveur (500) : incertain", c(ErreurResend(500)) == "incertain")
v("délai (408) : incertain", c(ErreurResend(408)) == "incertain")
v("clé en cours (409) : incertain", c(ErreurResend(409)) == "incertain")
v("coupure réseau : incertain", c(TimeoutError()) == "incertain")
v("erreur sans code : incertain", c(ValueError("x")) == "incertain")

print("── Automatique : simulation seulement")
v("automatisation fermée dans le code", rp.AUTOMATISATION_DISPONIBLE is False)
j = rp.jalons_simulation(D(0), ["J-3", "J0", "J+3"])
v("J-3 passé, J0 aujourd'hui, J+3 à venir", [x["etat"] for x in j] == ["passe", "aujourdhui", "a_venir"], j)
v("seuls les délais choisis", [x["palier"] for x in rp.jalons_simulation(D(0), ["J0"])] == ["J0"])
_src = inspect.getsource(rp)
v("le module ne lance aucune tâche de fond", "create_task" not in _src and "while True" not in _src)
_srv = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
v("le serveur ne démarre aucune boucle de rappel de paiement", not re.search(r"create_task\([^)]*rappel[^)]*paiement", _srv))
v("aucune mention de prélèvement ou de Stripe dans les appels du module",
  "stripe." not in _src and "Subscription.modify" not in _src)
v("le module n'écrit jamais sur subscriptions ni discount_codes",
  not re.search(r"db\.(subscriptions|discount_codes)\.(update|insert|delete|find_one_and|replace)", _src))
v("l'identifiant = abonnement + échéance + palier", rp.cle_envoi("s1", "2026-11-05") == "s1|2026-11-05|manuel")
v("clé d'idempotence stable", rp.cle_idempotence("a", 1) == rp.cle_idempotence("a", 1) != rp.cle_idempotence("a", 2))


# ══════════════════════ ROUTES RÉELLES, BASE LOCALE ══════════════════════
async def empreinte_base(db):
    """Une photo des collections qui ne doivent JAMAIS bouger."""
    h = hashlib.sha256()
    for col in ("subscriptions", "discount_codes", "offers", "reservations", "campaigns"):
        docs = await db[col].find({}).sort("_id", 1).to_list(1000)
        h.update(json.dumps(docs, default=str, sort_keys=True).encode())
    return h.hexdigest()


async def semer(db, flag=False):
    for col in await db.list_collection_names():
        await db[col].drop()
    await db.feature_flags.insert_one({"id": "feature_flags", **({rp.DRAPEAU_ENVOI_REEL: True} if flag else {})})
    await db.coaches.insert_many([{"email": PARTENAIRE, "name": "Lea"}, {"email": AUTRE, "name": "Tom"}])
    await db.offers.insert_many([{"id": "o-manuel", "billing_mode": "unique"}, {"id": "o-2x", "billing_mode": "saison_2x"}])
    await db.discount_codes.insert_many([
        {"id": "c1", "code": "CODE-1", "coach_id": "", "assignedEmail": "cliente@example.test"},
        {"id": "c2", "code": "CODE-LEA", "coach_id": PARTENAIRE, "assignedEmail": ""},
        {"id": "c3", "code": "CODE-STRIPE", "coach_id": "", "assignedEmail": "stripe@example.test"},
        {"id": "c4", "code": "CODE-OFFRE", "coach_id": "", "assignedEmail": ""},
        {"id": "c5", "code": "CODE-OPT", "coach_id": "", "assignedEmail": "refus@example.test"},
        {"id": "c6", "code": "CODE-CASE", "coach_id": "", "assignedEmail": ""},
    ])
    await db.subscriptions.insert_many([
        abo(),
        abo(id="s-ancien", status="superseded", montant_encaisse=100, email="cliente@example.test"),
        abo(id="s-lea", code="CODE-LEA", coach_id=PARTENAIRE, email="client-lea@example.test", name="Paul"),
        abo(id="s-stripe", code="CODE-STRIPE", billing_mode="saison_2x", stripe_subscription_id="sub_x", email="stripe@example.test"),
        abo(id="s-offre", code="CODE-OFFRE", offer_id="o-2x", email="offre@example.test"),
        abo(id="s-opt", code="CODE-OPT", email="refus@example.test"),
        abo(id="s-case", code="CODE-CASE", email="case@example.test",
            suivi_paiement={"montant_total": 400, "prochaine_echeance": D(0)}),
    ])
    await db.subscribers.insert_one({"channel": "email", "value": "refus@example.test", "status": "opted_out"})


async def refus_faux(db, canal, valeur):
    return bool(await db.subscribers.find_one({"channel": canal, "value": valeur, "status": "opted_out"}))


async def principal():
    client = AsyncIOMotorClient(ADRESSE, serverSelectionTimeoutMS=3000)
    assert ADRESSE.startswith("mongodb://127.0.0.1") and BASE == "afroboost_v648_test"
    db = client[BASE]
    rp.init_db(db, refus_email=lambda c, x: refus_faux(db, c, x))
    promo_routes.init_db(db) if hasattr(promo_routes, "init_db") else None
    promo_routes._db = db
    app = FastAPI()
    app.include_router(rp.router)
    app.include_router(promo_routes.promo_router, prefix="/api")
    faux = FauxResend()
    rp.resend = faux
    T = httpx.ASGITransport(app=app)
    A, P, O = jeton(ADMIN), jeton(PARTENAIRE), jeton(AUTRE)

    async with httpx.AsyncClient(transport=T, base_url="http://test", timeout=30) as cl:
        await semer(db)

        print("── Accès")
        for meth, url in (("GET", "/api/rappels-paiement/reglages"), ("PUT", "/api/rappels-paiement/reglages"),
                          ("GET", "/api/rappels-paiement/simulation"), ("GET", "/api/rappels-paiement/s1/apercu"),
                          ("POST", "/api/rappels-paiement/s1/envoyer")):
            kw = {"json": {}} if meth != "GET" else {}
            r = await cl.request(meth, url, **kw)
            v(f"{meth} {url} sans jeton : 403", r.status_code == 403, r.status_code)
            r = await cl.request(meth, url, headers={"X-User-Email": ADMIN}, **kw)
            v(f"{meth} {url} avec le seul en-tête X-User-Email : 403", r.status_code == 403, r.status_code)
        r = await cl.get("/api/rappels-paiement/s1/apercu", headers=jeton("inconnu@example.test"))
        v("un jeton d'un non-coach : 403", r.status_code == 403, r.status_code)
        r = await cl.get("/api/rappels-paiement/s1/apercu", headers=A)
        v("le propriétaire avec son jeton : 200 (preuve V310c)", r.status_code == 200, r.status_code)
        r = await cl.get("/api/rappels-paiement/s-lea/apercu", headers=P)
        v("un partenaire voit SON client", r.status_code == 200 and r.json()["possible"], r.text)
        v("il signe de son nom", "Coach Lea, d'Afroboost" in r.json()["texte"] and "Bassi" not in r.json()["texte"])
        r = await cl.get("/api/rappels-paiement/s1/apercu", headers=P)
        v("un partenaire ne voit pas un code du super-admin : 404", r.status_code == 404, r.status_code)
        r = await cl.get("/api/rappels-paiement/s-lea/apercu", headers=O)
        v("un autre coach ne voit pas ce client : 404", r.status_code == 404, r.status_code)
        r = await cl.post("/api/rappels-paiement/s-lea/envoyer", headers=O, json={"confirmation": True, "empreinte": "x"})
        v("un autre coach ne peut pas envoyer : 404", r.status_code == 404, r.status_code)

        print("── Drapeau éteint : RIEN ne part, RIEN n'est écrit")
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        v("aperçu complet", ap["possible"] and ap["reste"] == 200 and ap["destinataire"] == "cliente@example.test" and ap["envoi_reel"] is False, ap)
        v("aperçu signé Coach Bassi", ap["texte"].endswith("Coach Bassi, d'Afroboost"))
        avant = await empreinte_base(db)
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]})
        v("réponse : simulation", r.status_code == 200 and r.json()["issue"] == "simulation", r.text)
        v("aucun appel au fournisseur", len(faux.Emails.appels) == 0)
        v("aucun historique écrit", await db[rp.COL_RAPPELS].count_documents({}) == 0)
        v("aucune donnée métier modifiée", await empreinte_base(db) == avant)

        print("── Confirmation et revérifications serveur")
        await db.feature_flags.update_one({"id": "feature_flags"}, {"$set": {rp.DRAPEAU_ENVOI_REEL: True}})
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"empreinte": ap["empreinte"]})
        v("sans confirmation : 400", r.status_code == 400, r.status_code)
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": "fausse"})
        v("empreinte fausse : 409", r.status_code == 409 and r.json()["detail"]["type"] == "donnees_changees", r.text)
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"montant_encaisse": 300}})
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]})
        v("un acompte saisi après l'aperçu : 409", r.status_code == 409, r.status_code)
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"montant_encaisse": 400}})
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]})
        v("payé après l'aperçu : 409 solde_nul", r.status_code == 409 and r.json()["detail"]["type"] == "solde_nul", r.text)
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"montant_encaisse": 200}})
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"email": "changee@example.test"}})
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]})
        v("destinataire changé après l'aperçu : 409", r.status_code == 409, r.status_code)
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"email": "cliente@example.test"}})
        v("toujours aucun appel au fournisseur", len(faux.Emails.appels) == 0)

        print("── Exclusions, par la route")
        for sid, motif in (("s-stripe", "stripe_recurrent"), ("s-offre", "stripe_recurrent"), ("s-opt", "refus_email"),
                           ("s-ancien", "aucun_abonnement_actuel")):
            r = await cl.get(f"/api/rappels-paiement/{sid}/apercu", headers=A)
            v(f"{sid} : aperçu sans message, motif {motif}", r.status_code == 200 and r.json()["possible"] is False and r.json()["motif"] == motif and "texte" not in r.json(), r.text)
            r = await cl.post(f"/api/rappels-paiement/{sid}/envoyer", headers=A, json={"confirmation": True, "empreinte": "x"})
            v(f"{sid} : envoi refusé 409", r.status_code == 409 and r.json()["detail"]["type"] == motif, r.text)
        r = await cl.get("/api/rappels-paiement/s-case/apercu", headers=A)
        v("case non cochée : aperçu possible, avertissement", r.json()["possible"] and r.json()["avertissement"], r.text)
        await db.subscriptions.update_one({"id": "s-case"}, {"$unset": {"email": ""}})
        r = await cl.get("/api/rappels-paiement/s-case/apercu", headers=A)
        v("sans e-mail : aucun message possible", r.json()["possible"] is False and r.json()["motif"] == "sans_email", r.text)
        await db.discount_codes.insert_one({"id": "c1bis", "code": "code-1", "coach_id": "", "assignedEmail": ""})
        r = await cl.get("/api/rappels-paiement/s1/apercu", headers=A)
        v("code en double : refusé", r.json()["motif"] == "code_ambigu", r.text)
        await db.discount_codes.delete_one({"id": "c1bis"})
        v("aucun appel après les exclusions", len(faux.Emails.appels) == 0)

        print("── Envoi réel simulé : un seul message")
        avant = await empreinte_base(db)
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]})
        v("envoi accepté", r.status_code == 200 and r.json()["issue"] == "envoye", r.text)
        v("un seul appel", len(faux.Emails.appels) == 1)
        params, opts = faux.Emails.appels[0]
        v("destinataire relu en base", params["to"] == ["cliente@example.test"])
        v("expéditeur Afroboost", params["from"] == "Afroboost <notifications@afroboost.com>")
        v("clé d'idempotence transmise", bool(opts.get("idempotency_key")))
        v("message construit par le serveur", params["subject"] == ap["sujet"] and params["text"] == ap["texte"])
        d = await db[rp.COL_RAPPELS].find_one({"_id": rp.cle_envoi("s1", D(0))})
        v("historique : envoyé, identifiant Resend, auteur", d["statut"] == "envoye" and d["resend_id"] and d["envoye_par"] == ADMIN, d)
        v("abonnements et codes inchangés", await empreinte_base(db) == avant)
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]})
        v("deuxième clic : 409 deja_envoye", r.status_code == 409 and r.json()["detail"]["type"] == "deja_envoye", r.text)
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"], "reprise_incertain": True})
        v("même une « reprise » ne double pas un envoi confirmé", r.status_code == 409 and r.json()["detail"]["type"] == "deja_envoye", r.text)
        v("toujours un seul appel", len(faux.Emails.appels) == 1)
        hist = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()["historique"]
        v("l'historique apparaît dans l'aperçu", len(hist) == 1 and hist[0]["statut"] == "envoye", hist)
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"suivi_paiement.prochaine_echeance": D(1)}})
        ap2 = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap2["empreinte"]})
        v("une NOUVELLE échéance ouvre un nouveau rappel", r.status_code == 200 and len(faux.Emails.appels) == 2, r.text)
        v("code de Bassi : l'adresse de réponse reste celle par défaut", faux.Emails.appels[0][0].get("reply_to") == rc.reply_to_defaut(), faux.Emails.appels[0][0].get("reply_to"))
        ap_l = (await cl.get("/api/rappels-paiement/s-lea/apercu", headers=P)).json()
        r = await cl.post("/api/rappels-paiement/s-lea/envoyer", headers=P, json={"confirmation": True, "empreinte": ap_l["empreinte"]})
        v("un partenaire envoie à SON client", r.status_code == 200 and faux.Emails.appels[-1][0]["to"] == ["client-lea@example.test"], r.text)
        v("son client lui répond à lui", faux.Emails.appels[-1][0].get("reply_to") == PARTENAIRE)
        v("aucune mention de Bassi dans son message", "Bassi" not in faux.Emails.appels[-1][0]["text"] and "Bassi" not in faux.Emails.appels[-1][0]["html"])

        print("── Double envoi simultané")
        await semer(db, flag=True)
        faux.Emails.__init__()
        faux.Emails.delai = 0.2
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        corps = {"confirmation": True, "empreinte": ap["empreinte"]}
        rs = await asyncio.gather(*[cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps) for _ in range(8)])
        v("8 requêtes simultanées : UN seul appel", len(faux.Emails.appels) == 1, len(faux.Emails.appels))
        v("une seule réussite, 7 refus 409", sorted(x.status_code for x in rs) == [200] + [409] * 7, [x.status_code for x in rs])
        faux.Emails.delai = 0

        print("── Refus certain : on peut réessayer")
        await semer(db, flag=True)
        faux.Emails.__init__()
        faux.Emails.reponse = ErreurResend(422)
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        corps = {"confirmation": True, "empreinte": ap["empreinte"]}
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps)
        v("422 : échec annoncé", r.status_code == 502 and r.json()["detail"]["type"] == "echec", r.text)
        d = await db[rp.COL_RAPPELS].find_one({"_id": rp.cle_envoi("s1", D(0))})
        v("historique : échec", d["statut"] == "echec")
        k1 = faux.Emails.appels[0][1]["idempotency_key"]
        faux.Emails.reponse = None
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps)
        v("nouvel essai réussi", r.status_code == 200, r.text)
        v("nouvelle clé (la précédente garde le refus chez Resend)", faux.Emails.appels[1][1]["idempotency_key"] != k1)
        d = await db[rp.COL_RAPPELS].find_one({"_id": rp.cle_envoi("s1", D(0))})
        v("historique : envoyé, 2 tentatives, erreur effacée", d["statut"] == "envoye" and d["tentatives"] == 2 and "erreur" not in d, d)

        print("── Quota atteint")
        await semer(db, flag=True)
        faux.Emails.__init__()
        faux.Emails.reponse = rc.QuotaResendAtteint(95, 95, False)
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps)
        v("quota : échec certain, réessai possible", r.status_code == 502 and r.json()["detail"]["type"] == "echec", r.text)

        print("── Réponse incertaine : jamais de nouvel essai automatique")
        await semer(db, flag=True)
        faux.Emails.__init__()
        faux.Emails.reponse = TimeoutError()
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps)
        v("coupure : annoncée incertaine", r.status_code == 502 and r.json()["detail"]["type"] == "incertain", r.text)
        d = await db[rp.COL_RAPPELS].find_one({"_id": rp.cle_envoi("s1", D(0))})
        v("historique : incertain", d["statut"] == "incertain")
        k1 = faux.Emails.appels[0][1]["idempotency_key"]
        faux.Emails.reponse = None
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps)
        v("clic simple : refus, aucun appel", r.status_code == 409 and r.json()["detail"]["type"] == "incertain" and len(faux.Emails.appels) == 1, r.text)
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"montant_encaisse": 250}})
        ap3 = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap3["empreinte"], "reprise_incertain": True})
        v("reprise avec un AUTRE montant : refusée (même clé = même message)", r.status_code == 409 and r.json()["detail"]["type"] == "incertain_definitif" and len(faux.Emails.appels) == 1, r.text)
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"montant_encaisse": 200}})
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=dict(corps, reprise_incertain=True))
        v("reprise voulue par le coach : réussie", r.status_code == 200, r.text)
        v("MÊME clé d'idempotence (Resend ne délivre pas deux fois)", faux.Emails.appels[1][1]["idempotency_key"] == k1)

        await semer(db, flag=True)
        faux.Emails.__init__()
        faux.Emails.reponse = ErreurResend(500)
        await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps)
        vieux = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        await db[rp.COL_RAPPELS].update_one({"_id": rp.cle_envoi("s1", D(0))}, {"$set": {"premier_essai_le": vieux}})
        faux.Emails.reponse = None
        n = len(faux.Emails.appels)
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=dict(corps, reprise_incertain=True))
        v("après 24 h : plus aucune reprise (Resend a oublié la clé)", r.status_code == 409 and r.json()["detail"]["type"] == "incertain_definitif" and len(faux.Emails.appels) == n, r.text)

        await semer(db, flag=True)
        faux.Emails.__init__()
        faux.Emails.reponse = {"pas_d_identifiant": True}
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps)
        v("réponse sans identifiant : incertain", r.status_code == 502 and r.json()["detail"]["type"] == "incertain", r.text)

        await semer(db, flag=True)
        faux.Emails.__init__()
        faux.Emails.reponse = None
        cle = rp.cle_envoi("s1", D(0))
        recent = datetime.now(timezone.utc).isoformat()
        await db[rp.COL_RAPPELS].insert_one({"_id": cle, "statut": "en_cours", "maj_le": recent, "premier_essai_le": recent, "subscription_id": "s1", "cree_le": recent})
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps)
        v("un envoi en cours bloque le suivant", r.status_code == 409 and r.json()["detail"]["type"] == "en_cours" and len(faux.Emails.appels) == 0, r.text)
        vieux = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        await db[rp.COL_RAPPELS].update_one({"_id": cle}, {"$set": {"maj_le": vieux}})
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps)
        v("processus disparu : traité comme incertain, aucun appel", r.status_code == 409 and r.json()["detail"]["type"] == "incertain" and len(faux.Emails.appels) == 0, r.text)

        print("── Paiement saisi PENDANT la réservation")
        await semer(db, flag=True)
        faux.Emails.__init__()
        _orig = rp._reserver

        async def _reserver_puis_paiement(*a, **k):
            d = await _orig(*a, **k)
            await db.subscriptions.update_one({"id": "s1"}, {"$set": {"montant_encaisse": 400}})
            return d
        rp._reserver = _reserver_puis_paiement
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps)
        rp._reserver = _orig
        v("arrêt avant le fournisseur", r.status_code == 409 and len(faux.Emails.appels) == 0, r.text)

        print("── Réglages")
        await semer(db)
        r = await cl.get("/api/rappels-paiement/reglages", headers=A)
        v("MANUEL par défaut, automatisation fermée, envoi réel fermé",
          r.json()["mode"] == "MANUEL" and r.json()["automatisation_disponible"] is False and r.json()["envoi_reel"] is False, r.text)
        v("les trois délais proposés", r.json()["delais"] == ["J-3", "J0", "J+3"])
        r = await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "AUTOMATIQUE", "delais": ["J0", "J+3"]})
        v("choix AUTOMATIQUE rangé", r.status_code == 200 and r.json()["mode"] == "AUTOMATIQUE" and r.json()["automatisation_disponible"] is False, r.text)
        v("lecture après écriture", (await cl.get("/api/rappels-paiement/reglages", headers=A)).json()["delais"] == ["J0", "J+3"])
        v("le réglage d'un coach ne touche pas l'autre", (await cl.get("/api/rappels-paiement/reglages", headers=P)).json()["mode"] == "MANUEL")
        r = await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "AUTRE"})
        v("mode inconnu : 400", r.status_code == 400)
        r = await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "MANUEL", "delais": ["J+99"]})
        v("délai inconnu : 400", r.status_code == 400)
        r = await cl.put("/api/rappels-paiement/reglages", headers=A, content="[1,2]")
        v("corps illisible : 400", r.status_code == 400)

        print("── Simulation : lecture seule, automatique choisi ou non")
        await db.feature_flags.update_one({"id": "feature_flags"}, {"$set": {rp.DRAPEAU_ENVOI_REEL: True}})
        faux.Emails.__init__()
        await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "AUTOMATIQUE", "delais": ["J-3", "J0", "J+3"]})
        avant, avant_n = await empreinte_base(db), await db[rp.COL_RAPPELS].count_documents({})
        r = await cl.get("/api/rappels-paiement/simulation", headers=A)
        s = r.json()
        v("réponse marquée simulation", s["simulation"] is True and s["aucun_envoi"] is True, s)
        v("AUCUN e-mail, même drapeau allumé et mode automatique", len(faux.Emails.appels) == 0)
        v("aucune écriture", await empreinte_base(db) == avant and await db[rp.COL_RAPPELS].count_documents({}) == avant_n)
        L = {x["code"]: x for x in s["lignes"]}
        v("cas normal : enverrait", L["CODE-1"]["enverrait"] is True and len(L["CODE-1"]["jalons"]) == 3, L.get("CODE-1"))
        v("saison_2x : n'enverrait pas", L["CODE-STRIPE"]["enverrait"] is False and L["CODE-STRIPE"]["motif_exclusion"] == "stripe_recurrent")
        v("offre saison_2x : n'enverrait pas", L["CODE-OFFRE"]["enverrait"] is False)
        v("case non cochée : n'enverrait pas tout seul", L["CODE-CASE"]["motif_exclusion"] == "suivi_incomplet")
        v("refus d'e-mails : n'enverrait pas", L["CODE-OPT"]["enverrait"] is False)
        r = await cl.get("/api/rappels-paiement/simulation", headers=P)
        v("un partenaire ne simule que ses clients", [x["code"] for x in r.json()["lignes"]] == ["CODE-LEA"], r.text)

        print("── Encadré « Paiements à encaisser »")
        await semer(db)
        r = await cl.get("/api/discount-codes/echeances", headers=A)
        v("la route répond toujours", r.status_code == 200, r.text)
        L = {x["code"]: x for x in r.json()["rappels"]}
        v("les champs d'origine sont intacts", L["CODE-1"]["reste_a_payer"] == 200 and L["CODE-1"]["prochaine_echeance"] == D(0))
        v("rappel possible sur le cas normal", L["CODE-1"]["rappel_envoi"]["possible"] is True)
        v("saison_2x reste affiché, sans rappel possible", L["CODE-STRIPE"]["rappel_envoi"]["possible"] is False and L["CODE-STRIPE"]["rappel_envoi"]["motif"] == "stripe_recurrent")
        r = await cl.get("/api/discount-codes/echeances")
        v("sans jeton : toujours 403", r.status_code == 403)
        r = await cl.get("/api/discount-codes/echeances", headers=P)
        v("partenaire : ses seules lignes", [x["code"] for x in r.json()["rappels"]] == ["CODE-LEA"], r.text)
        _o = rp._contexte

        async def _panne(*a, **k):
            raise RuntimeError("panne")
        rp._contexte = _panne
        r = await cl.get("/api/discount-codes/echeances", headers=A)
        rp._contexte = _o
        v("panne du module : la liste reste affichée", r.status_code == 200 and len(r.json()["rappels"]) >= 1 and "rappel_envoi" not in r.json()["rappels"][0], r.text)

    await client.drop_database(BASE)
    client.close()


asyncio.run(principal())
print(f"\n{'ÉCHECS : ' + str(len(echecs)) + ' ' + str(echecs) if echecs else 'TOUT EST VERT'}")
sys.exit(1 if echecs else 0)
