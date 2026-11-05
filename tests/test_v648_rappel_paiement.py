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
SANS_NOM = "sans-nom@example.test"
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
v("BASSBOOSTX-11 (case non cochée) : aperçu seulement, vérification exigée, exclu de l'automatique",
  (lambda r: r["ok"] and r["incomplet"] and r["verification_requise"] and "pas une preuve" in r["avertissement"])(
      e(abo(suivi_paiement={"montant_total": 400, "prochaine_echeance": D(0)}))))
v("case cochée : aucune vérification supplémentaire", e(abo())["verification_requise"] is False)
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
v("un partenaire signe de son nom", rp.signature_du_code({"coach_id": PARTENAIRE}, {"name": "Lea"}) == "Lea")
v("le nom professionnel passe avant le nom", rp.signature_du_code({"coach_id": PARTENAIRE}, {"name": "Lea", "platform_name": "Studio Lea"}) == "Studio Lea")
v("« Afroboost » par défaut n'est pas son nom", rp.signature_du_code({"coach_id": PARTENAIRE}, {"name": "Lea", "platform_name": "Afroboost"}) == "Lea")
v("partenaire sans nom : aucune signature inventée", rp.signature_du_code({"coach_id": PARTENAIRE}) == "")

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
v("l'identifiant = abonnement + échéance + palier + rang", rp.cle_envoi("s1", "2026-11-05", 2) == "s1|2026-11-05|manuel|2")
print("── Décision de relance")
_N = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
_il_y_a = lambda **k: (_N - timedelta(**k)).isoformat()  # noqa: E731
_dr = rp.decision_relance
v("aucun envoi : rang 1", _dr([], 7, _N) == {"action": "nouveau", "rang": 1})
v("envoyé il y a 6 j : refus, date de relance donnée",
  (lambda r: r["action"] == "refus" and r["type"] == "deja_envoye" and r["prochaine_le"][:10] == "2026-11-21")(_dr([{"rang": 1, "statut": "envoye", "envoye_le": _il_y_a(days=6)}], 7, _N)))
v("envoyé il y a 7 j : relance, rang 2", _dr([{"rang": 1, "statut": "envoye", "envoye_le": _il_y_a(days=7)}], 7, _N) == {"action": "nouveau", "rang": 2})
v("le délai vient du réglage", _dr([{"rang": 1, "statut": "envoye", "envoye_le": _il_y_a(days=8)}], 14, _N)["type"] == "deja_envoye")
v("le dernier rang décide", _dr([{"rang": 1, "statut": "envoye", "envoye_le": _il_y_a(days=30)}, {"rang": 2, "statut": "envoye", "envoye_le": _il_y_a(days=1)}], 7, _N)["type"] == "deja_envoye")
v("date d'envoi illisible : refus", _dr([{"rang": 1, "statut": "envoye", "envoye_le": "?"}], 7, _N)["action"] == "refus")
_inc = lambda deb, maj: {"rang": 1, "statut": "incertain", "premier_essai_le": deb, "maj_le": maj}  # noqa: E731
v("incertain à l'instant : aucun renvoi immédiat", _dr([_inc(_il_y_a(seconds=5), _il_y_a(seconds=5))], 7, _N)["type"] == "incertain_attente")
v("incertain depuis 14 min : toujours en attente", _dr([_inc(_il_y_a(minutes=14), _il_y_a(minutes=14))], 7, _N)["type"] == "incertain_attente")
v("incertain depuis 2 h : reprise, même clé", _dr([_inc(_il_y_a(hours=2), _il_y_a(hours=2))], 7, _N)["action"] == "reprise")
v("reprise ratée à l'instant : l'attente repart", _dr([_inc(_il_y_a(hours=2), _il_y_a(seconds=5))], 7, _N)["type"] == "incertain_attente")
v("incertain de 24 h : plus aucun essai", _dr([_inc(_il_y_a(hours=24), _il_y_a(hours=24))], 7, _N)["type"] == "incertain_bloque")
v("incertain de 8 j : toujours aucun nouveau message", _dr([_inc(_il_y_a(days=8), _il_y_a(days=8))], 7, _N)["type"] == "incertain_bloque")
v("en cours interrompu : traité comme incertain", _dr([{"rang": 1, "statut": "en_cours", "premier_essai_le": _il_y_a(minutes=30), "maj_le": _il_y_a(minutes=30)}], 7, _N)["action"] == "reprise")
v("incertain sur une AUTRE date : bloque aussi", _dr([dict(_inc(_il_y_a(hours=1), _il_y_a(hours=1)), echeance="A")], 7, _N, "B")["type"] == "incertain_bloque")
v("envoi récent sur une AUTRE date : le délai s'applique", _dr([{"rang": 1, "statut": "envoye", "envoye_le": _il_y_a(days=1), "echeance": "A"}], 7, _N, "B")["type"] == "deja_envoye")
v("envoi ancien sur une AUTRE date : nouveau rappel, rang 1", _dr([{"rang": 1, "statut": "envoye", "envoye_le": _il_y_a(days=8), "echeance": "A"}], 7, _N, "B") == {"action": "nouveau", "rang": 1})
_trois = [{"rang": r, "statut": "envoye", "envoye_le": _il_y_a(days=30)} for r in (1, 2, 3)]
v("3 rappels envoyés : le 4e est refusé, même après 30 j", _dr(_trois, 7, _N)["type"] == "maximum_atteint")
v("le maximum compte par échéance", _dr([dict(x, echeance="A") for x in _trois], 7, _N, "B")["action"] == "nouveau")
v("un refus certain n'use pas un rang", _dr(_trois[:2] + [{"rang": 3, "statut": "echec"}], 7, _N)["action"] == "reessai")
print("── Aperçu à usage unique")
_e0, _c0 = "emp", "coach@example.test"
_j0 = rp.jeton_apercu(_e0, "nouveau|1|0", _c0, _N)
v("jeton valide", rp.jeton_valide(_j0, _e0, "nouveau|1|0", _c0, _N) == "ok")
v("après 31 min : périmé", rp.jeton_valide(_j0, _e0, "nouveau|1|0", _c0, _N + timedelta(minutes=31)) == "expire")
v("autres données : refusé", rp.jeton_valide(_j0, "autre", "nouveau|1|0", _c0, _N) == "different")
v("autre état des envois : refusé", rp.jeton_valide(_j0, _e0, "nouveau|2|0", _c0, _N) == "different")
v("autre coach : refusé", rp.jeton_valide(_j0, _e0, "nouveau|1|0", "x@example.test", _N) == "different")
v("empreinte seule, sans signature : refusée", rp.jeton_valide(_e0, _e0, "nouveau|1|0", _c0, _N) == "different")
v("jeton vide : refusé", rp.jeton_valide("", _e0, "nouveau|1|0", _c0, _N) == "different" and rp.jeton_valide(None, _e0, "nouveau|1|0", _c0, _N) == "different")
print("── Nom professionnel")
for _ok in ("Lea", "Studio Lea", "Coach Tom", "Danse & Co", "Marie-Hélène D'Arc", "St. Gall Fitness", "Sébastien", "A.B. Coaching", "Studio 54", "Zoé Œuvre"):
    v(f"accepté : {_ok}", rp.nom_pro_valide(_ok) is True)
for _no in ("", None, 42, "x" * 61, "https://evil.example", "evil.com", "www.evil", "Paie ici evil.ch", "lea@evil.test", "Lea\nPaie ici", "Lea <b>", "Afroboost", "Afroboost Officiel",
            "AFROBOOST", "Afr0boost", "A f r o b o o s t", "A.f.r-o.boost", "Coach Bassi", "Bässi", "B4ssi", "Сoach Bassi", "Аfroboost", "Support Stripe", "TWINT Paiement", "CH93 00762 01162",
            "Service client", "Ma Banque", "Afrøboost", "Afrœboost", "Bæssi", "Bassl", "BASSL", "8assi", "Afro 8oost", "Bass 1", "evil.com-pay", "evil.com&x", "evil .com", "x.ch-y",
            "CH93 0076 2011 6238 5295 7", "12 34 56", "1 2 3 4 5", "Afr0boost24"):
    v(f"refusé : {_no!r}"[:50], rp.nom_pro_valide(_no) is False)
v("le défaut « Afroboost » cède au nom du coach", rp.nom_professionnel({"platform_name": "Afroboost", "name": "Lea"}) == "Lea")
v("un nom de plateforme refusé ne se rattrape pas en silence", rp.nom_professionnel({"platform_name": "Afroboost Officiel", "name": "Lea"}) == "")
v("signature officielle conservée", rp.signature_du_code({"coach_id": ""}) == "Coach Bassi, d'Afroboost")
v("un partenaire ne peut pas signer Bassi", rp.signature_du_code({"coach_id": PARTENAIRE}, {"name": "Coach Bassi"}) == "")
v("date d'incertain illisible : refus", _dr([{"rang": 1, "statut": "incertain"}], 7, _N)["action"] == "refus")
v("échec : même rang", _dr([{"rang": 3, "statut": "echec"}], 7, _N)["rang"] == 3)
v("étapes lisibles", rp.etape_du_rang(1) == "Rappel" and rp.etape_du_rang(2) == "Relance 1" and rp.etape_du_rang(3) == "Relance 2")
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
    await db.coaches.insert_many([{"email": PARTENAIRE, "name": "Lea", "platform_name": "Studio Lea"}, {"email": AUTRE, "name": "Tom"},
                                  {"email": SANS_NOM}])
    await db.offers.insert_many([{"id": "o-manuel", "billing_mode": "unique"}, {"id": "o-2x", "billing_mode": "saison_2x"}])
    await db.discount_codes.insert_many([
        {"id": "c1", "code": "CODE-1", "coach_id": "", "assignedEmail": "cliente@example.test"},
        {"id": "c2", "code": "CODE-LEA", "coach_id": PARTENAIRE, "assignedEmail": ""},
        {"id": "c3", "code": "CODE-STRIPE", "coach_id": "", "assignedEmail": "stripe@example.test"},
        {"id": "c4", "code": "CODE-OFFRE", "coach_id": "", "assignedEmail": ""},
        {"id": "c5", "code": "CODE-OPT", "coach_id": "", "assignedEmail": "refus@example.test"},
        {"id": "c6", "code": "CODE-CASE", "coach_id": "", "assignedEmail": ""},
        {"id": "c7", "code": "CODE-TOM", "coach_id": AUTRE, "assignedEmail": ""},
        {"id": "c8", "code": "CODE-SANSNOM", "coach_id": SANS_NOM, "assignedEmail": ""},
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
        abo(id="s-tom", code="CODE-TOM", coach_id=AUTRE, email="client-tom@example.test", name="Ana"),
        abo(id="s-sansnom", code="CODE-SANSNOM", coach_id=SANS_NOM, email="client-x@example.test"),
    ])
    await db.subscribers.insert_one({"channel": "email", "value": "refus@example.test", "status": "opted_out"})


async def refus_faux(db, canal, valeur):
    return bool(await db.subscribers.find_one({"channel": canal, "value": valeur, "status": "opted_out"}))


async def principal():
    client = AsyncIOMotorClient(ADRESSE, serverSelectionTimeoutMS=3000)
    assert ADRESSE.startswith("mongodb://127.0.0.1") and BASE == "afroboost_v648_test"
    db = client[BASE]
    rp.init_db(db, refus_email=lambda c, x: refus_faux(db, c, x))
    promo_routes.init_promo_db(db)
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
                          ("GET", "/api/rappels-paiement/simulation"), ("GET", "/api/rappels-paiement/liste"),
                          ("GET", "/api/rappels-paiement/historique"), ("GET", "/api/rappels-paiement/s1/apercu"),
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
        v("il signe de son nom professionnel", r.json()["texte"].endswith("Studio Lea") and "Bassi" not in r.json()["texte"], r.json()["texte"])
        r = await cl.get("/api/rappels-paiement/s-sansnom/apercu", headers=jeton(SANS_NOM))
        v("partenaire sans nom : aucun message possible", r.json()["possible"] is False and r.json()["motif"] == "signature_manquante", r.text)
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
        v("case non cochée : aperçu possible, avertissement, vérification exigée", r.json()["possible"] and r.json()["avertissement"] and r.json()["verification_requise"] is True, r.text)
        emp_case = r.json()["empreinte"]
        avant = await empreinte_base(db)
        r = await cl.post("/api/rappels-paiement/s-case/envoyer", headers=A, json={"confirmation": True, "empreinte": emp_case})
        v("case non cochée, sans montant : envoi bloqué", r.status_code == 409 and r.json()["detail"]["type"] == "verification_requise", r.text)
        r = await cl.post("/api/rappels-paiement/s-case/envoyer", headers=A, json={"confirmation": True, "empreinte": emp_case, "montant_confirme": 150})
        v("montant différent du solde : envoi bloqué", r.status_code == 409 and r.json()["detail"]["type"] == "montant_different", r.text)
        r = await cl.post("/api/rappels-paiement/s-case/envoyer", headers=A, json={"confirmation": True, "empreinte": emp_case, "montant_confirme": "abc"})
        v("montant illisible : envoi bloqué", r.status_code == 409 and r.json()["detail"]["type"] == "verification_requise", r.text)
        v("aucun envoi pendant ces refus", len(faux.Emails.appels) == 0)
        v("l'abonnement n'a pas été corrigé", await empreinte_base(db) == avant)
        r = await cl.post("/api/rappels-paiement/s-case/envoyer", headers=A, json={"confirmation": True, "empreinte": emp_case, "montant_confirme": 200})
        v("montant vérifié : envoi accepté", r.status_code == 200 and r.json()["issue"] == "envoye" and len(faux.Emails.appels) == 1, r.text)
        d = await db[rp.COL_RAPPELS].find_one({"subscription_id": "s-case"})
        v("le montant confirmé est gardé dans l'historique", d["montant_confirme"] == 200, d)
        v("toujours aucune écriture sur l'abonnement", await empreinte_base(db) == avant)
        await db[rp.COL_RAPPELS].delete_many({})
        faux.Emails.__init__()
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
        v("changer la date ne contourne pas les 7 jours", r.status_code == 409 and r.json()["detail"]["type"] == "deja_envoye" and len(faux.Emails.appels) == 1, r.text)
        await db[rp.COL_RAPPELS].update_one({"_id": rp.cle_envoi("s1", D(0), 1)}, {"$set": {"envoye_le": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()}})
        ap2 = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap2["empreinte"]})
        v("après le délai, une NOUVELLE échéance ouvre un nouveau rappel", r.status_code == 200 and len(faux.Emails.appels) == 2, r.text)
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"suivi_paiement.prochaine_echeance": D(0)}})
        v("code de Bassi : l'adresse de réponse reste celle par défaut", faux.Emails.appels[0][0].get("reply_to") == rc.reply_to_defaut(), faux.Emails.appels[0][0].get("reply_to"))
        ap_l = (await cl.get("/api/rappels-paiement/s-lea/apercu", headers=P)).json()
        r = await cl.post("/api/rappels-paiement/s-lea/envoyer", headers=P, json={"confirmation": True, "empreinte": ap_l["empreinte"]})
        v("un partenaire envoie à SON client", r.status_code == 200 and faux.Emails.appels[-1][0]["to"] == ["client-lea@example.test"], r.text)
        v("son client lui répond à lui", faux.Emails.appels[-1][0].get("reply_to") == PARTENAIRE)
        v("aucune mention de Bassi dans son message", "Bassi" not in faux.Emails.appels[-1][0]["text"] and "Bassi" not in faux.Emails.appels[-1][0]["html"])

        print("── Relances : même échéance, sans changer la date")
        await semer(db, flag=True)
        faux.Emails.__init__()
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        v("première étape : Rappel", ap["envoi"]["etape"] == "Rappel" and ap["envoi"]["peut_envoyer"] is True, ap["envoi"])
        corps = {"confirmation": True, "empreinte": ap["empreinte"]}
        await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps)
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        v("aperçu : envoi bloqué, date de relance", ap["envoi"]["peut_envoyer"] is False and ap["envoi"]["prochaine_le"][:10] == D(7), ap["envoi"])
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps)
        v("avant 7 jours : refus, un seul message", r.status_code == 409 and r.json()["detail"]["type"] == "deja_envoye" and len(faux.Emails.appels) == 1, r.text)
        il_y_a_8 = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        await db[rp.COL_RAPPELS].update_one({"_id": rp.cle_envoi("s1", D(0), 1)}, {"$set": {"envoye_le": il_y_a_8, "cree_le": il_y_a_8}})
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"montant_encaisse": 400}})
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps)
        v("dette réglée depuis : aucune relance", r.status_code == 409 and r.json()["detail"]["type"] == "solde_nul" and len(faux.Emails.appels) == 1, r.text)
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"montant_encaisse": 200}})
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        v("après 7 jours : étape Relance 1", ap["envoi"]["peut_envoyer"] is True and ap["envoi"]["etape"] == "Relance 1", ap["envoi"])
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"empreinte": ap["empreinte"]})
        v("la relance exige aussi la confirmation", r.status_code == 400, r.status_code)
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps)
        v("l'ancien aperçu ne sert pas pour la relance", r.status_code == 409 and r.json()["detail"]["type"] == "donnees_changees" and len(faux.Emails.appels) == 1, r.text)
        corps = {"confirmation": True, "empreinte": ap["empreinte"]}
        faux.Emails.delai = 0.2
        rs = await asyncio.gather(*[cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps) for _ in range(8)])
        faux.Emails.delai = 0
        v("relance, 8 demandes simultanées : un seul message de plus", len(faux.Emails.appels) == 2, len(faux.Emails.appels))
        v("relance, une seule réussite", sorted(x.status_code for x in rs) == [200] + [409] * 7, [x.status_code for x in rs])
        v("clé d'idempotence différente de celle du rappel", faux.Emails.appels[0][1]["idempotency_key"] != faux.Emails.appels[1][1]["idempotency_key"])
        s1 = await db.subscriptions.find_one({"id": "s1"})
        v("la date d'échéance n'a pas bougé", s1["suivi_paiement"]["prochaine_echeance"] == D(0))
        hist = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()["historique"]
        v("historique : 2 lignes, la plus récente d'abord", [h["etape"] for h in hist] == ["Relance 1", "Rappel"], hist)
        h = hist[0]
        v("historique : date, destinataire, étape, résultat et coach", h["envoye_le"] and h["destinataire"] == "cliente@example.test" and h["statut"] == "envoye" and h["envoye_par"] == ADMIN, h)
        await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "MANUEL", "delai_relance_jours": 30})
        await db[rp.COL_RAPPELS].update_one({"_id": rp.cle_envoi("s1", D(0), 2)}, {"$set": {"envoye_le": il_y_a_8}})
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps)
        v("le délai réglé par le coach s'applique (30 j)", r.status_code == 409 and r.json()["detail"]["type"] == "deja_envoye", r.text)
        r = await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "MANUEL", "delai_relance_jours": 1})
        v("impossible de descendre sous 7 jours", r.status_code == 400, r.status_code)
        await db[rp.COL_REGLAGES].update_one({"_id": ADMIN}, {"$set": {"delai_relance_jours": 1}})
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        v("une valeur sous 7 jours en base ne vaut rien", ap["envoi"]["delai_jours"] == 7, ap["envoi"])
        await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "MANUEL", "delai_relance_jours": 7})
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        corps = {"confirmation": True, "empreinte": ap["empreinte"]}
        rs = await asyncio.gather(*[cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps) for _ in range(5)])
        v("3e rappel, 5 demandes simultanées : un seul message", len(faux.Emails.appels) == 3 and sorted(x.status_code for x in rs) == [200] + [409] * 4, [x.status_code for x in rs])
        print("── Quatrième rappel")
        await db[rp.COL_RAPPELS].update_one({"_id": rp.cle_envoi("s1", D(0), 3)}, {"$set": {"envoye_le": il_y_a_8}})
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        v("aperçu : maximum annoncé, envoi fermé", ap["envoi"]["peut_envoyer"] is False and ap["envoi"]["type"] == "maximum_atteint", ap["envoi"])
        rs = await asyncio.gather(*[cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]}) for _ in range(5)])
        v("4e rappel : refus, même simultané", all(x.status_code == 409 and x.json()["detail"]["type"] == "maximum_atteint" for x in rs), [x.text for x in rs][:1])
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"], "reprise_incertain": True})
        v("4e rappel : la « reprise » n'ouvre rien", r.status_code == 409 and len(faux.Emails.appels) == 3, r.text)
        v("exactement 3 rappels pour cette échéance", await db[rp.COL_RAPPELS].count_documents({"subscription_id": "s1", "echeance": D(0), "statut": "envoye"}) == 3)
        print("── Le délai suit le coach propriétaire")
        await cl.put("/api/rappels-paiement/reglages", headers=P, json={"mode": "MANUEL", "delai_relance_jours": 30})
        ap_l = (await cl.get("/api/rappels-paiement/s-lea/apercu", headers=A)).json()
        v("le super-admin voit le client du partenaire signé par lui", ap_l["texte"].endswith("Studio Lea"))
        r = await cl.post("/api/rappels-paiement/s-lea/envoyer", headers=A, json={"confirmation": True, "empreinte": ap_l["empreinte"]})
        v("les réponses vont au coach propriétaire", r.status_code == 200 and faux.Emails.appels[-1][0].get("reply_to") == PARTENAIRE, r.text)
        d = await db[rp.COL_RAPPELS].find_one({"_id": rp.cle_envoi("s-lea", D(0), 1)})
        await db[rp.COL_RAPPELS].update_one({"_id": d["_id"]}, {"$set": {"envoye_le": il_y_a_8}})
        r = await cl.get("/api/rappels-paiement/s-lea/apercu", headers=A)
        v("le délai de 30 j du partenaire s'applique au super-admin", r.json()["envoi"]["peut_envoyer"] is False, r.json()["envoi"])

        print("── Cloisonnement de l'historique et de la liste")
        h_p = (await cl.get("/api/rappels-paiement/historique", headers=P)).json()["historique"]
        v("le partenaire voit son historique, et lui seul", len(h_p) == 1 and h_p[0]["code"] == "CODE-LEA", h_p)
        h_o = (await cl.get("/api/rappels-paiement/historique", headers=O)).json()["historique"]
        v("un autre partenaire n'y voit rien", h_o == [], h_o)
        h_a = (await cl.get("/api/rappels-paiement/historique", headers=A)).json()["historique"]
        v("le super-admin voit tout", {x["code"] for x in h_a} == {"CODE-1", "CODE-LEA"}, h_a)
        r = await cl.get("/api/rappels-paiement/s-lea/apercu", headers=O)
        v("un autre partenaire ne lit pas l'aperçu ni son historique : 404", r.status_code == 404)
        l_o = (await cl.get("/api/rappels-paiement/liste", headers=O)).json()["lignes"]
        v("liste d'un autre partenaire : ses seuls clients", [x["code"] for x in l_o] == ["CODE-TOM"], l_o)
        r = await cl.get("/api/rappels-paiement/reglages", headers=O)
        v("son réglage reste le sien", r.json()["delai_relance_jours"] == 7, r.text)

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
        v("après un refus, l'ancien aperçu ne sert plus", r.status_code == 409 and r.json()["detail"]["type"] == "donnees_changees" and len(faux.Emails.appels) == 1, r.text)
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]})
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
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        v("aperçu : envoi fermé juste après l'incertitude", ap["envoi"]["peut_envoyer"] is False and ap["envoi"]["type"] == "incertain_attente", ap["envoi"])
        for j in (False, True):
            r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"], "reprise_incertain": j})
            v(f"aucun renvoi immédiat (reprise demandée : {j})", r.status_code == 409 and r.json()["detail"]["type"] == "incertain_attente" and len(faux.Emails.appels) == 1, r.text)
        il_y_a_20 = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        await db[rp.COL_RAPPELS].update_one({"_id": rp.cle_envoi("s1", D(0))}, {"$set": {"maj_le": il_y_a_20}})
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]})
        v("clic simple : refus, aucun appel", r.status_code == 409 and r.json()["detail"]["type"] == "incertain" and len(faux.Emails.appels) == 1, r.text)
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"montant_encaisse": 250}})
        ap3 = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap3["empreinte"], "reprise_incertain": True})
        v("reprise avec un AUTRE montant : refusée (même clé = même message)", r.status_code == 409 and r.json()["detail"]["type"] == "incertain_attente" and len(faux.Emails.appels) == 1, r.text)
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"montant_encaisse": 200}})
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        v("aperçu : reprise proposée, avec demande explicite", ap["envoi"]["confirmation_incertain"] is True, ap["envoi"])
        rs = await asyncio.gather(*[cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"], "reprise_incertain": True}) for _ in range(5)])
        v("reprise, 5 demandes simultanées : une seule passe", sorted(x.status_code for x in rs) == [200] + [409] * 4 and len(faux.Emails.appels) == 2, [x.status_code for x in rs])
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
        v("après 24 h : plus aucune reprise (Resend a oublié la clé)", r.status_code == 409 and r.json()["detail"]["type"] == "incertain_bloque" and len(faux.Emails.appels) == n, r.text)
        vieux = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        await db[rp.COL_RAPPELS].update_one({"_id": rp.cle_envoi("s1", D(0))}, {"$set": {"premier_essai_le": vieux, "maj_le": vieux}})
        for j in (False, True):
            r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=dict(corps, reprise_incertain=j))
            v(f"après 8 j, sans résolution fiable : toujours aucun envoi (demande : {j})", r.status_code == 409 and r.json()["detail"]["type"] == "incertain_bloque" and len(faux.Emails.appels) == n, r.text)
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"suivi_paiement.prochaine_echeance": D(1)}})
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"], "reprise_incertain": True})
        v("changer la date ne contourne pas l'incertitude", r.status_code == 409 and r.json()["detail"]["type"] == "incertain_bloque" and len(faux.Emails.appels) == n, r.text)
        d = await db[rp.COL_RAPPELS].find_one({"_id": rp.cle_envoi("s1", D(0), 1)})
        v("la ligne incertaine reste dans l'historique", d["statut"] == "incertain", d)

        print("── Le problème signalé : un refus ancien, puis une incertitude")
        await semer(db, flag=True)
        faux.Emails.__init__()
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        faux.Emails.reponse = ErreurResend(422)
        await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]})
        cle1 = rp.cle_envoi("s1", D(0))
        vieux = (datetime.now(timezone.utc) - timedelta(days=9)).isoformat()
        await db[rp.COL_RAPPELS].update_one({"_id": cle1}, {"$set": {"premier_essai_le": vieux, "maj_le": vieux}})
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        faux.Emails.reponse = TimeoutError()
        avant_essai = datetime.now(timezone.utc).isoformat()
        await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]})
        d = await db[rp.COL_RAPPELS].find_one({"_id": cle1})
        v("nouvel essai : nouvelle clé ET nouvelle date de référence", d["statut"] == "incertain" and d["premier_essai_le"] >= avant_essai and faux.Emails.appels[0][1] != faux.Emails.appels[1][1], d)
        faux.Emails.reponse = None
        n = len(faux.Emails.appels)
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        v("le vieux refus n'ouvre aucun renvoi", ap["envoi"]["peut_envoyer"] is False and ap["envoi"]["type"] == "incertain_attente", ap["envoi"])
        for j in (False, True):
            r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"], "reprise_incertain": j})
            v(f"aucun message de plus (demande : {j})", r.status_code == 409 and len(faux.Emails.appels) == n, r.text)

        print("── Réponses tardives du fournisseur")
        _orig_appel = rp._appel_fournisseur

        async def _avec(pendant, reponse):
            async def _f(cle, params, options):
                await pendant(cle)
                if isinstance(reponse, Exception):
                    raise reponse
                return reponse
            rp._appel_fournisseur = _f

        async def _vu_incertain(cle):        # l'appel traîne : un autre passage l'a déjà déclaré incertain
            await db[rp.COL_RAPPELS].update_one({"_id": cle}, {"$set": {"statut": "incertain", "erreur": "interrompu"}})

        async def _deja_envoye(cle):
            await db[rp.COL_RAPPELS].update_one({"_id": cle}, {"$set": {"statut": "envoye", "envoye_le": "2026-01-01T00:00:00+00:00", "resend_id": "em_1"}})

        async def _preparer():
            await semer(db, flag=True)
            return (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()["empreinte"]

        jt = await _preparer()
        await _avec(_vu_incertain, ErreurResend(422))
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": jt})
        d = await db[rp.COL_RAPPELS].find_one({"_id": cle1})
        v("refus tardif : l'état prudent reste, jamais « échec »", d["statut"] == "incertain" and r.json()["detail"]["type"] == "incertain", d)
        jt = await _preparer()
        await _avec(_vu_incertain, {"id": "em_tardif"})
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": jt})
        d = await db[rp.COL_RAPPELS].find_one({"_id": cle1})
        v("succès tardif : résolution fiable, l'envoi est confirmé", d["statut"] == "envoye" and d["resend_id"] == "em_tardif" and "erreur" not in d, d)
        jt = await _preparer()
        await _avec(_deja_envoye, ErreurResend(500))
        await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": jt})
        d = await db[rp.COL_RAPPELS].find_one({"_id": cle1})
        v("erreur tardive : un envoi confirmé ne recule jamais", d["statut"] == "envoye", d)
        jt = await _preparer()
        await _avec(_deja_envoye, {"id": "em_2"})
        await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": jt})
        d = await db[rp.COL_RAPPELS].find_one({"_id": cle1})
        v("second succès : la date du premier est conservée", d["envoye_le"] == "2026-01-01T00:00:00+00:00" and d["resend_id"] == "em_1", d)
        rp._appel_fournisseur = _orig_appel

        print("── Aperçu : falsification, expiration, autre coach")
        await semer(db, flag=True)
        faux.Emails.__init__()
        v_s = rp.empreinte("s1", rp.eligibilite(await db.subscriptions.find_one({"id": "s1"}, {"_id": 0})))
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": v_s})
        v("sans aperçu demandé (empreinte calculée) : refus", r.status_code == 409 and len(faux.Emails.appels) == 0, r.text)
        vieux_j = rp.jeton_apercu(v_s, "nouveau|1|0", ADMIN, datetime.now(timezone.utc) - timedelta(minutes=31))
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": vieux_j})
        v("aperçu de plus de 30 min : refus", r.status_code == 409 and r.json()["detail"]["type"] == "apercu_expire" and len(faux.Emails.appels) == 0, r.text)
        ap_a = (await cl.get("/api/rappels-paiement/s-lea/apercu", headers=A)).json()
        r = await cl.post("/api/rappels-paiement/s-lea/envoyer", headers=P, json={"confirmation": True, "empreinte": ap_a["empreinte"]})
        v("l'aperçu d'un autre coach ne sert pas", r.status_code == 409 and r.json()["detail"]["type"] == "donnees_changees" and len(faux.Emails.appels) == 0, r.text)

        print("── Signature partenaire, par la route")
        for mauvais in ("Afroboost Officiel", "Coach Bassi", "https://evil.example", "paie@evil.test", "x" * 61):
            await db.coaches.update_one({"email": PARTENAIRE}, {"$set": {"platform_name": mauvais}})
            r = await cl.get("/api/rappels-paiement/s-lea/apercu", headers=P)
            v(f"nom {mauvais[:24]!r} : aucun aperçu", r.json()["possible"] is False and r.json()["motif"] == "signature_manquante" and "texte" not in r.json(), r.text)
            r = await cl.post("/api/rappels-paiement/s-lea/envoyer", headers=P, json={"confirmation": True, "empreinte": ap_a["empreinte"]})
            v(f"nom {mauvais[:24]!r} : aucun envoi", r.status_code == 409 and r.json()["detail"]["type"] == "signature_manquante" and len(faux.Emails.appels) == 0, r.text)
        await db.coaches.update_one({"email": PARTENAIRE}, {"$set": {"platform_name": "Studio Lea"}})
        r = await cl.get("/api/rappels-paiement/s-lea/apercu", headers=O)
        v("isolation : un autre coach ne voit toujours rien", r.status_code == 404)
        v("rappel Afroboost : signature officielle", (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()["texte"].endswith("Coach Bassi, d'Afroboost"))

        print("── Une reprise qui échoue reste incertaine")
        for nom, err in (("quota", rc.QuotaResendAtteint(95, 95, False)), ("refus 422", ErreurResend(422))):
            await semer(db, flag=True)
            faux.Emails.__init__()
            faux.Emails.reponse = TimeoutError()
            await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps)
            k1 = faux.Emails.appels[0][1]["idempotency_key"]
            await db[rp.COL_RAPPELS].update_one({"_id": rp.cle_envoi("s1", D(0))}, {"$set": {"maj_le": (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()}})
            faux.Emails.reponse = err
            ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
            await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"], "reprise_incertain": True})
            d = await db[rp.COL_RAPPELS].find_one({"_id": rp.cle_envoi("s1", D(0))})
            v(f"reprise + {nom} : toujours incertain, jamais une nouvelle clé", d["statut"] == "incertain" and d["idempotency_key"] == k1, d)

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
        await db[rp.COL_RAPPELS].insert_one({"_id": cle, "rang": 1, "statut": "en_cours", "maj_le": recent, "premier_essai_le": recent, "subscription_id": "s1", "echeance": D(0), "palier": rp.PALIER_MANUEL, "cree_le": recent})
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps)
        v("un envoi en cours bloque le suivant", r.status_code == 409 and r.json()["detail"]["type"] == "en_cours" and len(faux.Emails.appels) == 0, r.text)
        vieux = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        await db[rp.COL_RAPPELS].update_one({"_id": cle}, {"$set": {"maj_le": vieux}})
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps)
        v("processus disparu : traité comme incertain, attente imposée, aucun appel", r.status_code == 409 and r.json()["detail"]["type"] == "incertain_attente" and len(faux.Emails.appels) == 0, r.text)
        d = await db[rp.COL_RAPPELS].find_one({"_id": cle})
        v("et l'historique le dit", d["statut"] == "incertain" and d["erreur"] == "interrompu", d)

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
        v("délai de relance : 7 jours par défaut", (await cl.get("/api/rappels-paiement/reglages", headers=P)).json()["delai_relance_jours"] == 7)
        for mauvais in (0, 1, 6, 61, "7", True, 7.5, None):
            r = await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "MANUEL", "delai_relance_jours": mauvais})
            v(f"délai de relance {mauvais!r} : 400", r.status_code == 400, r.status_code)
        r = await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "MANUEL", "delai_relance_jours": 14})
        v("délai de relance 14 : rangé", r.json()["delai_relance_jours"] == 14, r.text)
        r = await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "MANUEL"})
        v("un autre réglage ne l'efface pas", r.json()["delai_relance_jours"] == 14, r.text)
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
        v("partenaire sans nom : n'enverrait pas", L["CODE-SANSNOM"]["enverrait"] is False)

        print("── Section « Rappels de paiement »")
        await semer(db)
        r = await cl.get("/api/rappels-paiement/liste", headers=A)
        v("la liste répond", r.status_code == 200, r.text)
        L = {x["code"]: x for x in r.json()["lignes"]}
        v("envoi réel signalé comme coupé", r.json()["envoi_reel"] is False)
        v("montant et échéance", L["CODE-1"]["reste_a_payer"] == 200 and L["CODE-1"]["prochaine_echeance"] == D(0))
        v("rappel possible sur le cas normal", L["CODE-1"]["possible"] is True and L["CODE-1"]["envoi"]["peut_envoyer"] is True)
        v("case non cochée : vérification annoncée", L["CODE-CASE"]["verification_requise"] is True)
        v("saison_2x : listé, sans envoi possible", L["CODE-STRIPE"]["possible"] is False and L["CODE-STRIPE"]["motif"] == "stripe_recurrent")
        v("abonnement remplacé : absent", all(x["subscription_id"] != "s-ancien" for x in L.values()))
        await db.subscriptions.update_one({"id": "s-case"}, {"$set": {"montant_encaisse": 400}})
        r = await cl.get("/api/rappels-paiement/liste", headers=A)
        v("solde réglé : retiré de la liste", all(x["code"] != "CODE-CASE" for x in r.json()["lignes"]))
        await db.subscriptions.update_one({"id": "s-case"}, {"$set": {"suivi_paiement.prochaine_echeance": D(40), "montant_encaisse": 200}})
        L = {x["code"]: x for x in (await cl.get("/api/rappels-paiement/liste", headers=A)).json()["lignes"]}
        v("échéance lointaine : listée, sans envoi", L["CODE-CASE"]["possible"] is False and L["CODE-CASE"]["motif"] == "hors_fenetre")
        v("liste bornée à 50 lignes", rp.SIMULATION_MAX == 50)
        v("aucune écriture par la liste", await db[rp.COL_RAPPELS].count_documents({}) == 0)

        print("── L'encadré « Paiements à encaisser » reste celui de la production")
        r = await cl.get("/api/discount-codes/echeances", headers=A)
        v("la route répond", r.status_code == 200 and len(r.json()["rappels"]) >= 1, r.text)
        v("aucun champ V648 ajouté", all("rappel_envoi" not in x for x in r.json()["rappels"]))
        v("les champs d'origine sont intacts", {x["code"]: x for x in r.json()["rappels"]}["CODE-1"]["reste_a_payer"] == 200)
        r = await cl.get("/api/discount-codes/echeances")
        v("sans jeton : toujours 403", r.status_code == 403)

    await client.drop_database(BASE)
    client.close()


asyncio.run(principal())
print(f"\n{'ÉCHECS : ' + str(len(echecs)) + ' ' + str(echecs) if echecs else 'TOUT EST VERT'}")
sys.exit(1 if echecs else 0)
