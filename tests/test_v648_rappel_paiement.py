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
         "montant_encaisse": 200, "devise": "CHF", "origine_paiement": "twint",
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
        self.lectures, self.fiche = [], ErreurResend(404)
        self.listes, self.pages = [], []

    def send(self, params, options=None):
        self.appels.append((params, options))
        if self.delai:
            import time
            time.sleep(self.delai)
        r = self.reponse
        if isinstance(r, Exception):
            raise r
        return r if r is not None else {"id": "em_%d" % len(self.appels)}


    def get(self, identifiant):
        self.lectures.append(identifiant)
        if isinstance(self.fiche, Exception):
            raise self.fiche
        return self.fiche


    def list(self, params=None):
        self.listes.append(params)
        if isinstance(self.pages, Exception):
            raise self.pages
        return self.pages[len(self.listes) - 1] if len(self.listes) <= len(self.pages) else {"data": [], "has_more": False}


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
  e(abo(billing_mode="saison_2x", stripe_subscription_id="sub_x", montant_encaisse=199.99, origine_paiement="renouvellement_pulse"))["motif"] == "stripe_recurrent")
v("Stripe : exclu par un vrai abonnement Stripe", e(abo(stripe_subscription_id="sub_x", origine_paiement="stripe"))["motif"] == "stripe_recurrent")
print("── V649 : le mode de paiement réel")
_cm = lambda **k: rp.classer_mode_paiement(k)  # noqa: E731
v("CHRISTOUX10 : TWINT, offre saison_2x sans abonnement Stripe : manuel", _cm(origine_paiement="twint", offer_id="o-2x") == {"classe": "manuel", "libelle": "TWINT"})
v("BASSBOOSTX-11 : espèces, offre saison_2x sans abonnement Stripe : manuel", _cm(origine_paiement="especes", offer_id="o-2x") == {"classe": "manuel", "libelle": "Espèces"})
v("AFR-B12426 : vrai abonnement Stripe : prélèvement automatique", _cm(origine_paiement="renouvellement_pulse", billing_mode="saison_2x", stripe_subscription_id="sub_x")["classe"] == "stripe_auto")
v("virement : manuel", _cm(origine_paiement="virement")["libelle"] == "Virement")
v("carte en paiement unique : aucun prélèvement", _cm(origine_paiement="stripe") == {"classe": "manuel", "libelle": "Carte, paiement unique"})
v("saison_2x payée en une fois : aucun prélèvement", _cm(origine_paiement="stripe", billing_mode="saison_2x", payment_mode="full")["classe"] == "manuel")
for _nom, _k in (("abonnement Stripe ET TWINT", dict(stripe_subscription_id="sub_x", origine_paiement="twint")), ("abonnement Stripe ET espèces", dict(stripe_subscription_id="sub_x", origine_paiement="especes")),
                 ("abonnement Stripe ET offert", dict(stripe_subscription_id="sub_x", origine_paiement="offert")), ("facturation automatique sans abonnement Stripe", dict(billing_mode="mensuel_auto", origine_paiement="stripe")),
                 ("saison_2x sans abonnement, en TWINT", dict(billing_mode="saison_2x", origine_paiement="twint")), ("mode absent", {}), ("mode inconnu", dict(origine_paiement="xyz")),
                 ("recharge sans abonnement Stripe", dict(origine_paiement="renouvellement_pulse")), ("offert avec un solde", dict(origine_paiement="offert"))):
    v(f"{_nom} : à vérifier", _cm(**_k) == {"classe": "a_verifier", "libelle": "Paiement à vérifier"}, _cm(**_k))
    v(f"{_nom} : aucun rappel, sans parler de Stripe", (lambda r: r["motif"] == "paiement_a_verifier" and "Stripe" not in r["message"])(e(abo(**dict({"origine_paiement": None}, **_k)))))
v("l'ancien texte ambigu a disparu", all("aucun rappel à envoyer" not in m.lower() for m in rp.MOTIFS.values()))
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
v("plusieurs abonnements actifs : refusé", e(abo(), None, "plusieurs")["motif"] == "plusieurs_abonnements")

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
v("un partenaire signe de son nom, formule fixe", rp.signature_du_code({"coach_id": PARTENAIRE}, {"nom": "Lea Martin"}) == "Lea Martin\nCoach partenaire d'Afroboost")
v("avec son activité", rp.signature_du_code({"coach_id": PARTENAIRE}, {"nom": "Lea Martin", "activite": "Studio Lea"}) == "Lea Martin, Studio Lea\nCoach partenaire d'Afroboost")
v("activité refusée : aucune signature", rp.signature_du_code({"coach_id": PARTENAIRE}, {"nom": "Lea Martin", "activite": "Paie sur evil.com"}) == "")
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
j = rp.jalons_simulation(D(0), ["J-3", "J0", "J+3"])
_pal = lambda *a, **k: [x["palier"] for x in rp.jalons_simulation(*a, **k)]  # noqa: E731
v("J-3 dépassé : le premier part aujourd'hui, jamais de date passée", [x["palier"] for x in j] == ["J0", "J+7", "J+14"] and j[0]["etat"] == "aujourdhui", j)
v("politique complète : J-3, puis tous les 7 jours", _pal(D(3), ["J-3", "J0", "J+3"]) == ["J-3", "J+4", "J+11"])
v("délai de 14 jours respecté", _pal(D(3), ["J-3"], delai_jours=14) == ["J-3", "J+11", "J+25"])
v("seul J+3 coché", _pal(D(0), ["J+3"]) == ["J+3", "J+10", "J+17"])
v("échéance dépassée : à partir d'aujourd'hui", _pal(D(-2), ["J-3"]) == ["J+2", "J+9", "J+16"])
v("2 rappels partis : il en reste un", len(_pal(D(0), ["J0"], envoyes=2)) == 1)
v("3 rappels partis : plus rien", _pal(D(0), ["J0"], envoyes=3) == [])
v("attente du délai respectée", rp.jalons_simulation(D(0), ["J0"], envoyes=1, prochaine=D(5) + "T10:00:00+00:00")[0]["date"] == D(5))
v("rien après J+30", _pal(D(-28), ["J0"]) == ["J+28"])
v("aucun délai coché : aucun jalon", rp.jalons_simulation(D(0), []) == [])
_src = inspect.getsource(rp)
v("une seule boucle, et aucune tâche lancée par le module lui-même", "create_task" not in _src and _src.count("while True") == 1)
_srv = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
v("le serveur ne démarre aucune boucle de rappel de paiement", not re.search(r"create_task\([^)]*rappel[^)]*paiement", _srv))
v("aucune mention de prélèvement ou de Stripe dans les appels du module",
  "stripe." not in _src and "Subscription.modify" not in _src)
v("le module n'écrit jamais sur subscriptions ni discount_codes",
  not re.search(r"db\.(subscriptions|discount_codes)\.(update|insert|delete|find_one_and|replace)", _src))
v("l'identifiant = abonnement + échéance + palier + rang", rp.cle_envoi("s1", 2) == "s1|manuel|2")
print("── Décision de relance")
_N = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
_il_y_a = lambda **k: (_N - timedelta(**k)).isoformat()  # noqa: E731
_dr = rp.decision_relance
v("aucun envoi : rang 1, rappel 1", _dr([], 7, _N) == {"action": "nouveau", "rang": 1, "numero": 1})
v("envoyé il y a 6 j : refus, date de relance donnée",
  (lambda r: r["action"] == "refus" and r["type"] == "deja_envoye" and r["prochaine_le"][:10] == "2026-11-21")(_dr([{"rang": 1, "statut": "envoye", "envoye_le": _il_y_a(days=6)}], 7, _N)))
v("envoyé il y a 7 j : relance, rang 2", _dr([{"rang": 1, "statut": "envoye", "envoye_le": _il_y_a(days=7)}], 7, _N) == {"action": "nouveau", "rang": 2, "numero": 2})
v("le délai vient du réglage", _dr([{"rang": 1, "statut": "envoye", "envoye_le": _il_y_a(days=8)}], 14, _N)["type"] == "deja_envoye")
v("le dernier envoi décide", _dr([{"rang": 1, "statut": "envoye", "envoye_le": _il_y_a(days=30)}, {"rang": 2, "statut": "envoye", "envoye_le": _il_y_a(days=1)}], 7, _N)["type"] == "deja_envoye")
v("date d'envoi illisible : refus", _dr([{"rang": 1, "statut": "envoye", "envoye_le": "?"}], 7, _N)["action"] == "refus")
_inc = lambda deb: {"rang": 1, "statut": "incertain", "premier_essai_le": deb, "maj_le": deb}  # noqa: E731
for _nom, _k in (("à l'instant", {"seconds": 5}), ("20 min", {"minutes": 20}), ("2 h", {"hours": 2}), ("24 h", {"hours": 24}), ("8 j", {"days": 8}), ("1 an", {"days": 365})):
    v(f"incertain depuis {_nom} : bloqué, aucun délai ne débloque", _dr([_inc(_il_y_a(**_k))], 7, _N)["type"] == "incertain_bloque")
v("en cours interrompu : traité comme incertain", _dr([{"rang": 1, "statut": "en_cours", "premier_essai_le": _il_y_a(minutes=30), "maj_le": _il_y_a(minutes=30)}], 7, _N)["type"] == "incertain_bloque")
v("incertain sur un autre abonnement de la personne : bloque aussi", _dr([dict(_inc(_il_y_a(hours=1)), subscription_id="A")], 7, _N, {"sub": "B", "encaisse": 200, "total": 400, "numero": 2})["type"] == "incertain_bloque")
_trois = [{"rang": r, "statut": "envoye", "envoye_le": _il_y_a(days=30)} for r in (1, 2, 3)]
v("3 rappels envoyés : le 4e est refusé, même après 30 j", _dr(_trois, 7, _N)["type"] == "maximum_atteint")
v("un refus certain n'use pas un rappel", (lambda r: r["action"] == "reessai" and r["numero"] == 3)(_dr(_trois[:2] + [{"rang": 3, "statut": "echec"}], 7, _N)))
v("une absence prouvée n'use pas un rappel, mais un nouveau rang", _dr(_trois[:1] + [{"rang": 2, "statut": "non_parti"}], 7, _N) == {"action": "nouveau", "rang": 3, "numero": 2})
print("── Identité du paiement")
_p = lambda **k: dict({"sub": "S", "numero": 2, "encaisse": 200.0, "total": 400.0}, **k)  # noqa: E731
_d = lambda **k: dict({"subscription_id": "S", "paiement_numero": 2, "nb_au_rappel": 3, "encaisse_au_rappel": 200, "total_au_rappel": 400}, **k)  # noqa: E731
_cp = rp.classer_paiement
v("rien n'a changé : même paiement", _cp(_d(), _p()) == "meme")
v("total corrigé : même paiement", _cp(_d(), _p(total=450.0)) == "meme")
v("encaissé corrigé à la baisse : même paiement", _cp(_d(), _p(encaisse=150.0)) == "meme")
v("acompte, même rang : même paiement", _cp(_d(), _p(encaisse=250.0)) == "meme")
v("case décochée, rien d'encaissé : même paiement", _cp(_d(), _p(numero=None)) == "meme")
v("case cochée, rien d'encaissé : même paiement", _cp(_d(paiement_numero=None), _p()) == "meme")
v("rang suivant ET encaissement : paiement distinct", _cp(_d(), _p(numero=3, encaisse=300.0)) == "distinct")
v("rang suivant sans encaissement : incertain", _cp(_d(), _p(numero=3)) == "ambigu")
v("rang précédent : incertain", _cp(_d(), _p(numero=1, encaisse=300.0)) == "ambigu")
v("sans rang, encaissement : incertain", _cp(_d(paiement_numero=None), _p(numero=None, encaisse=300.0)) == "ambigu")
v("case changée ET encaissement : incertain", _cp(_d(), _p(numero=None, encaisse=300.0)) == "ambigu" and _cp(_d(paiement_numero=None), _p(encaisse=300.0)) == "ambigu")
v("montant encaissé illisible : incertain", _cp(_d(encaisse_au_rappel=None), _p()) == "ambigu" and _cp(_d(), _p(encaisse=None)) == "ambigu")
v("autre abonnement, même dette : même paiement", _cp(_d(subscription_id="X"), _p()) == "meme")
v("autre abonnement, autres montants : incertain", _cp(_d(subscription_id="X"), _p(total=600.0)) == "ambigu")
v("autre abonnement, 1 centime d'écart : incertain", _cp(_d(subscription_id="X"), _p(total=400.01)) == "ambigu" and _cp(_d(subscription_id="X"), _p(encaisse=200.01)) == "ambigu")
v("ancien abonnement clos et soldé : distinct", _cp(_d(subscription_id="X", _abonnement_solde=True), _p(total=600.0)) == "distinct" and _cp(_d(subscription_id="X", _abonnement_solde=True), _p()) == "distinct")
v("rang +1 et 1 centime : incertain", _cp(_d(), _p(numero=3, encaisse=200.01)) == "ambigu")
v("rang +1, total et encaissé montés d'autant : incertain", _cp(_d(), _p(numero=3, encaisse=250.0, total=450.0)) == "ambigu")
v("rang +2, une seule part encaissée : incertain", _cp(_d(nb_au_rappel=5), _p(numero=4, encaisse=250.0)) == "ambigu")
v("rang +2, deux parts encaissées : distinct", _cp(_d(nb_au_rappel=5), _p(numero=4, encaisse=300.0)) == "distinct")
v("total baissé et 1 centime : incertain", _cp(_d(total_au_rappel=600), _p(numero=3, encaisse=200.01, total=400.0)) == "ambigu")
v("rang au-delà du nombre de paiements : incertain", _cp(_d(nb_au_rappel=3), _p(numero=4, encaisse=400.0)) == "ambigu")
v("nombre de paiements extrême : incertain", _cp(_d(nb_au_rappel=10 ** 6), _p(numero=3, encaisse=200.3)) == "ambigu")
v("sans nombre de paiements : incertain", _cp(_d(nb_au_rappel=None), _p(numero=3, encaisse=300.0)) == "ambigu")
_cycle, _enc, _tot, _rang, _ouverts = _d(), 200.0, 400.0, 2, 0
for _ in range(33):
    _enc, _tot, _rang = _enc + 0.01, _tot + 0.01, _rang + 1
    _ouverts += _cp(dict(_cycle, paiement_numero=_rang - 1, encaisse_au_rappel=_enc - 0.01, total_au_rappel=_tot - 0.01, nb_au_rappel=99), _p(numero=_rang, encaisse=_enc, total=_tot)) == "distinct"
v("33 cycles au centime : aucun nouveau compteur", _ouverts == 0, _ouverts)
print("── Fiches du fournisseur illisibles")
for _nom, _f in (("sans destinataire", {}), ("destinataire vide", {"to": []}), ("destinataire objet", {"to": [{"email": "a@example.test"}]})):
    v(f"{_nom} : illisible", rp.adresses_fiche(_f) is None)
v("adresse avec un nom : lue", rp.adresses_fiche({"to": ["Anne <A@Example.test>"]}) == ["a@example.test"])
v("objet avec espace : lu", rp.objet_fiche({"subject": " x "}) == "x" and rp.objet_fiche({}) is None)
v("identité incertaine : bloque, ne remet pas à zéro", _dr([dict(_d(), rang=1, statut="envoye", envoye_le=_il_y_a(days=30))], 7, _N, _p(numero=3))["type"] == "paiement_ambigu")
v("un paiement distinct repart au rappel 1", (lambda r: r["action"] == "nouveau" and r["numero"] == 1 and r["rang"] == 4)(_dr([dict(_d(), rang=i, statut="envoye", envoye_le=_il_y_a(days=30)) for i in (1, 2, 3)], 7, _N, _p(numero=3, encaisse=300.0))))
v("le délai vaut aussi pour un paiement distinct", _dr([dict(_d(), rang=1, statut="envoye", envoye_le=_il_y_a(days=1))], 7, _N, _p(numero=3, encaisse=300.0))["type"] == "deja_envoye")
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
for _ok in ("Lea", "Studio Lea", "Coach Tom", "Danse & Co", "Marie-Hélène D'Arc", "St. Gall Fitness", "Sébastien", "A.B. Coaching", "Studio 54", "Zoé Œuvre",
            "Fit24", "Club 360", "Bassirou", "Bassirou Diop", "Jean Bassi", "Bassi Diop", "Müller", "Åsa Lind", "Ngọc Anh", "李小龙", "Дмитрий Иванов", "Νίκος", "محمد علي", "Ñandú",
            "Christ Ripert", "Lien Nguyen", "Thomas Paye", "Jean Carte", "Thomas Payet", "Łukasz Nowak", "Aydın Kaya", "Đặng Hoa", "Þór", "فرزانه\u200cها", "മന്ദാകിനി\u200d", "Hélène", "He\u0301le\u0300ne"):
    v(f"accepté : {_ok}", rp.motif_nom_refuse(_ok) == "", rp.motif_nom_refuse(_ok))
for _no in ("", None, 42, "x" * 61, "https://evil.example", "evil.com", "www.evil", "Paie ici evil.ch", "lea@evil.test", "Lea\nPaie ici", "Lea <b>", "Afroboost", "Afroboost Officiel",
            "AFROBOOST", "Afr0boost", "A f r o b o o s t", "A.f.r-o.boost", "Coach Bassi", "Bassi", "Bässi", "B4ssi", "Сoach Bassi", "Аfroboost", "Support Stripe", "TWINT Paiement", "CH93 00762 01162",
            "Service client", "Ma Banque", "Afrøboost", "Afrœboost", "Bæssi", "Bassl", "BASSL", "8assi", "Afro 8oost", "Bass 1", "evil.com-pay", "evil.com&x", "evil .com", "x.ch-y",
            "CH93 0076 2011 6238 5295 7", "12 34 56", "1 2 3 4 5", "Afr0boost24", "evil point com", "evil dot ch", "Paie ici", "Virement Lea", "Cliquez ici", "IBAN Lea",
            "\U0001d400\U0001d405\U0001d411\U0001d40e\U0001d401\U0001d40e\U0001d40e\U0001d412\U0001d413", "\U0001d402oach \U0001d401assi", "Afr\u0585b\u0585\u0585st", "\u1d00\ua730\u0280\u1d0f\u0299\u1d0f\u1d0f\ua731\u1d1b",
            "Coach Bass\u0131", "Coach Bass\u026a", "Coach \u0180assi", "evil.c\ufe0fom", "pa\ufe0fiement", "I\u034fBAN", "w\u034fww", "site.\u092d\u093e\u0930\u0924", "1.1.1.1", "evil dot shop", "evil. com",
            "Payez \u00e0 Jean", "Bank Transfer", "Envoyez CHF \u00e0 Jean", "Zahlung Konto", "Monsieur Bassi", "Dr Bassi", "Team Bassi", "Equipe Bassi", "T W I N T", "S t r i p e", "Lea\u200dMartin",
            "Lea\u200bMartin", "Lea\u202eMartin", "Bοss Аdmin", "Сoach Lea", "Coach B.a.s.s.i", "Le Coach Bassi"):
    v(f"refusé : {_no!r}"[:50], rp.motif_nom_refuse(_no) != "")
v("un refus s'explique en français", "lien" in rp.motif_nom_refuse("evil.com").lower())
v("activité limitée à 40 caractères", rp.motif_nom_refuse("x" * 41, rp.ACTIVITE_MAX) != "" and rp.motif_nom_refuse("x" * 40, rp.ACTIVITE_MAX) == "")
v("signature officielle conservée", rp.signature_du_code({"coach_id": ""}) == "Coach Bassi, d'Afroboost")
v("un partenaire ne peut pas signer Bassi", rp.signature_du_code({"coach_id": PARTENAIRE}, {"nom": "Coach Bassi"}) == "")
v("chiffres : le total des deux champs compte", rp.signature_du_code({"coach_id": PARTENAIRE}, {"nom": "Jean 0791", "activite": "Club 234"}) == "")
v("prénom client douteux : « Bonjour, »", rp._prenom("https://evil.example/x") == "" and rp._prenom("Marie Dupont") == "Marie" and rp._prenom("Paiement urgent") == "")
v("devise libre refusée", e(abo(devise="CHF sur IBAN CH93"))["motif"] == "suivi_incoherent" and e(abo(devise="EVIL.CH"))["motif"] == "suivi_incoherent" and e(abo(devise="EUR"))["ok"] is True)
v("montant infini refusé", e(abo(montant_encaisse="inf"))["motif"] == "solde_inconnu" and e(abo(suivi_paiement=suivi(montant_total="inf")))["ok"] is False and rp._nombre(10 ** 400) is None)
v("jeton non ASCII : refusé sans erreur", rp.jeton_valide("123.\u00e9", "e", "x", "c", datetime.now(timezone.utc)) == "different")
print("── Preuve du fournisseur")
_d0 = {"destinataire": "a@example.test", "premier_essai_le": "2026-11-05T10:00:00+00:00"}
_f0 = {"to": ["A@example.test"], "subject": rp.OBJETS_RAPPEL[0], "created_at": "2026-11-05 10:00:03.5+00", "from": "Afroboost <notifications@afroboost.com>"}
v("fiche conforme", rp.preuve_conforme(_f0, _d0) == "", rp.preuve_conforme(_f0, _d0))
v("autre destinataire : refus", rp.preuve_conforme(dict(_f0, to=["b@example.test"]), _d0) != "")
v("autre objet : refus", rp.preuve_conforme(dict(_f0, subject="Bienvenue"), _d0) != "")
v("autre expéditeur : refus", rp.preuve_conforme(dict(_f0, **{"from": "x@evil.test"}), _d0) != "")
v("trop ancien : refus", rp.preuve_conforme(dict(_f0, created_at="2026-11-01 10:00:00+00"), _d0) != "")
v("trop tardif : refus", rp.preuve_conforme(dict(_f0, created_at="2026-11-07 10:00:00+00"), _d0) != "")
v("date illisible : refus", rp.preuve_conforme(dict(_f0, created_at="?"), _d0) != "")
v("réponse vide : refus", rp.preuve_conforme(None, _d0) != "")
for _f in ("2026-11-05 10:00:03.5+00", "2026-11-05T10:00:03Z", "2026-11-05T10:00:03.123456789+00:00", "2026-11-05T10:00:03+00:00"):
    v(f"format de date accepté : {_f}", rp.preuve_conforme(dict(_f0, created_at=_f), _d0) == "", rp.preuve_conforme(dict(_f0, created_at=_f), _d0))
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
    await db[rp.COL_REGLAGES].insert_many([{"_id": PARTENAIRE, "signature": {"nom": "Lea Martin", "activite": "Studio Lea"}},
                                            {"_id": AUTRE, "signature": {"nom": "Tom Roche"}}])
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
        abo(id="s-stripe", code="CODE-STRIPE", billing_mode="saison_2x", stripe_subscription_id="sub_x", email="stripe@example.test", origine_paiement="stripe"),
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


async def _vieillir(db, sub_id, jours=8):
    _h = (datetime.now(timezone.utc) - timedelta(days=jours)).isoformat()
    await db[rp.COL_RAPPELS].update_many({"subscription_id": sub_id, "statut": "envoye"}, {"$set": {"envoye_le": _h, "cree_le": _h, "maj_le": _h}})


async def _drapeaux(db, **k):
    await db.feature_flags.update_one({"id": "feature_flags"}, {"$set": {getattr(rp, n): val for n, val in k.items()}})


async def tests_v650(db, cl, faux, A, P):
    print("── V650 : le texte du coach")
    m = rp.motif_modele_refuse
    C = "{bonjour} il reste {montant} pour le {echeance}."
    v("texte correct accepté", m("Petit rappel", C) == "")
    v("texte d'origine accepté", m(rp.sujet_defaut(), rp.CORPS_DEFAUT) == "")
    v("phrases normales acceptées", m("Petit rappel", C + " Merci. De ton côté, tout va bien. Merci. Me voici. À bientôt !") == "", m("Petit rappel", C + " Merci. De ton côté, tout va bien. Merci. Me voici. À bientôt !"))
    v("accents et émojis acceptés", m("Été à bientôt", C + " À très vite \u2764\ufe0f !") == "")
    v("modèle sain relu tel quel", rp.modele_enregistre({"sujet": "", "corps": C}) == {"sujet": "", "corps": C})
    v("modèle devenu invalide : texte d'origine", rp.modele_enregistre({"sujet": "Coucou", "corps": C + " evil.com"}) is None)
    v("modèle illisible : texte d'origine", rp.modele_enregistre({"sujet": "Coucou"}) is None and rp.modele_enregistre("x") is None)
    v("délais jamais réglés : les trois", rp.delais_du_reglage({}) == ["J-3", "J0", "J+3"])
    v("délais tout décochés : aucun", rp.delais_du_reglage({"delais": []}) == [])
    for nom, s_, c_ in (("montant écrit", "Petit rappel", C + " Soit 150 CHF."), ("chiffre dans l'objet", "Rappel 150", C), ("date écrite", "Petit rappel", C + " Le 12.11."),
                        ("mois écrit", "Rappel de mars", C), ("devise écrite", "Petit rappel", C + " En francs."), ("lien", "Petit rappel", C + " Va sur https://evil.example"),
                        ("domaine", "Petit rappel", C + " www.evil.test"), ("domaine sans www", "Petit rappel", C + " Paie sur evil.com merci"),
                        ("domaine avec espaces", "Petit rappel", C + " evil . com"), ("domaine en toutes lettres", "Petit rappel", C + " evil point com"),
                        ("point pleine largeur", "Petit rappel", C + " evil\uff0ecom"), ("caractère invisible", "Petit rappel", C + " evil\u200b.com"),
                        ("arobase pleine largeur", "Petit rappel", C + " paie\uff20evil"), ("domaine dans l'objet", "evil.shop", C), ("iban", "Petit rappel", C + " Mon IBAN suit."),
                        ("extension non latine", "Petit rappel", C + " evil.рф"), ("extension io avec espaces", "Petit rappel", C + " evil . io"),
                        ("extension-mot avec espaces", "Petit rappel", C + " evil . de"), ("point idéographique", "Petit rappel", C + " evil\u3002com"),
                        ("remplisseur hangul", "Petit rappel", C + " evil\u3164.com"), ("blanc braille", "Petit rappel", C + " evil.\u2800com"),
                        ("sélecteur de variante", "Petit rappel", C + " evil\ufe0f.com"), ("joint de graphèmes", "Petit rappel", C + " evil\u034f.com"), ("adresse", "Petit rappel", C + " paie@evil.test"), ("sans {montant}", "Petit rappel", "{echeance}"),
                        ("sans {echeance}", "Petit rappel", "{montant}"), ("variable inconnue", "Petit rappel", C + " {iban}"), ("accolade seule", "Petit rappel", C + " }"),
                        ("objet sur deux lignes", "a\nBcc: x", C), ("objet trop long", "x" * 121, C), ("corps trop long", "Petit rappel", C + "x" * 2000),
                        ("objet vide", "", C), ("corps vide", "Petit rappel", ""), ("objet non texte", 5, C), ("variable dans l'objet", "{montant}", C)):
        v(f"refusé : {nom}", m(s_, c_) != "", (s_, c_))

    print("── V650 : envoi manuel d'un texte modifié")
    await semer(db, flag=True)
    faux.Emails.__init__()
    T = {"sujet": "Un petit mot", "corps": "{bonjour}\n\nIl reste {montant}, prévu le {echeance}. <b>Merci</b>"}
    r = await cl.post("/api/rappels-paiement/s1/apercu", headers=A, json=T)
    ap = r.json()
    v("aperçu du texte modifié", r.status_code == 200 and ap["sujet"] == "Un petit mot" and "200" in ap["texte"] and "CHF" in ap["texte"], r.text)
    v("mention « déjà payé » toujours présente", "Si tu as déjà payé" in ap["texte"])
    v("aperçu : rien n'est écrit ni envoyé", await db[rp.COL_RAPPELS].count_documents({}) == 0 and not faux.Emails.appels)
    r = await cl.post("/api/rappels-paiement/s1/apercu", headers=A, json={"sujet": "Un petit mot", "corps": "Payez 500 CHF"})
    v("montant inventé refusé à l'aperçu", r.status_code == 400 and r.json()["detail"]["type"] == "modele_refuse", r.text)
    r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]})
    v("jeton du texte modifié, sans le texte : refus", r.status_code == 409 and not faux.Emails.appels, r.text)
    r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=dict(T, confirmation=True, empreinte=ap["empreinte"], corps=T["corps"] + " Encore"))
    v("texte changé après l'aperçu : refus", r.status_code == 409 and not faux.Emails.appels, r.text)
    r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=dict(T, confirmation=True, empreinte=ap["empreinte"]))
    v("le texte vu part", r.status_code == 200 and r.json()["envoye"] is True and r.json()["message"] == "E-mail envoyé.", r.text)
    p = faux.Emails.appels[0][0]
    v("objet et corps du coach", p["subject"] == "Un petit mot" and "prévu le" in p["text"])
    v("HTML échappé", "&lt;b&gt;Merci" in p["html"] and "<b>Merci" not in p["html"])
    d = await db[rp.COL_RAPPELS].find_one({"subscription_id": "s1"})
    v("historique : manuel, statut, identifiant, objet", d["statut"] == "envoye" and d["mode_envoi"] == "manuel" and d["resend_id"] and d["sujet"] == "Un petit mot", d)
    v("preuve : l'objet modifié n'est pas pris pour un autre e-mail", rp.objet_fiche({"subject": "Un petit mot"}) in rp.OBJETS_RAPPEL + (d["sujet"],))
    faux.Emails.__init__()
    faux.Emails.reponse = {}
    ap = (await cl.post("/api/rappels-paiement/s-offre/apercu", headers=A, json=T)).json()
    r = await cl.post("/api/rappels-paiement/s-offre/envoyer", headers=A, json=dict(T, confirmation=True, empreinte=ap["empreinte"]))
    v("sans identifiant du fournisseur : jamais « envoyé »", r.status_code == 502 and r.json()["detail"]["type"] == "incertain", r.text)
    v("et à vérifier", (await db[rp.COL_RAPPELS].find_one({"subscription_id": "s-offre"}))["statut"] == "incertain")

    print("── V650 : modèle, isolation")
    await semer(db, flag=True)
    faux.Emails.__init__()
    r = await cl.put("/api/rappels-paiement/modele", headers=A, json=T)
    v("modèle enregistré", r.status_code == 200, r.text)
    v("relu dans les réglages", (await cl.get("/api/rappels-paiement/reglages", headers=A)).json()["modele"]["sujet"] == "Un petit mot")
    v("appliqué aux clients de la plateforme", (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()["sujet"] == "Un petit mot")
    v("pas à ceux d'un partenaire", (await cl.get("/api/rappels-paiement/s-lea/apercu", headers=P)).json()["sujet"] != "Un petit mot")
    r = await cl.put("/api/rappels-paiement/modele", headers=A, json={"sujet": rp.OBJETS_RAPPEL[0], "corps": T["corps"]})
    v("objet d'origine : reste calculé, jamais figé", r.json()["modele"]["sujet"] == "", r.text)
    r = await cl.put("/api/rappels-paiement/modele", headers=A, json={"sujet": "Un petit mot", "corps": "Payez 500 CHF"})
    v("modèle invalide : 400", r.status_code == 400)
    await db[rp.COL_REGLAGES].update_one({"_id": rp.SUPER_ADMIN_EMAIL.lower()}, {"$set": {"modele": {"sujet": "Coucou", "corps": "{montant} {echeance} evil.com"}}})
    _a = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
    v("modèle rangé invalide : il ne part pas", "evil.com" not in _a["texte"] and _a["sujet"] != "Coucou", _a["sujet"])
    r = await cl.delete("/api/rappels-paiement/modele", headers=A)
    v("réinitialisation", r.status_code == 200 and (await cl.get("/api/rappels-paiement/reglages", headers=A)).json()["modele"] is None, r.text)
    for meth, url in (("put", "modele"), ("delete", "modele"), ("post", "aide-ia"), ("post", "s1/apercu")):
        r = await cl.request(meth.upper(), "/api/rappels-paiement/" + url, json=T if meth != "delete" else None)
        v(f"sans jeton : {meth} {url} = 403", r.status_code == 403, r.status_code)
    r = await cl.post("/api/rappels-paiement/s1/apercu", headers=P, json=T)
    v("aperçu du client d'un autre : 404", r.status_code == 404, r.status_code)

    print("── V650 : aide IA")
    _orig_ia, recus = rp.appeler_ia, []
    _prop = {"sujet": "Coucou", "corps": "{bonjour} reste {montant} pour le {echeance}."}

    async def _ia(sys_, txt):
        recus.append(sys_ + txt)
        return json.dumps(_prop)
    rp.appeler_ia = _ia
    os.environ.pop("OPENAI_API_KEY", None)
    r = await cl.post("/api/rappels-paiement/aide-ia", headers=A, json=dict(T, ton="direct"))
    v("sans clé : 503 clair", r.status_code == 503 and not recus, r.text)
    os.environ["OPENAI_API_KEY"] = "cle-factice"
    avant = await db[rp.COL_REGLAGES].count_documents({})
    r = await cl.post("/api/rappels-paiement/aide-ia", headers=A, json=dict(T, ton="direct"))
    v("une proposition", r.status_code == 200 and r.json()["proposition"]["sujet"] == "Coucou", r.text)
    v("le ton est transmis", "direct" in recus[0])
    v("aucune donnée client ne part chez l'IA", not any(x in recus[0] for x in ("example.test", "CODE-1", "200")), recus[0])
    v("rien n'est enregistré", await db[rp.COL_REGLAGES].count_documents({}) == avant and (await db[rp.COL_REGLAGES].find_one({"_id": rp.SUPER_ADMIN_EMAIL.lower()}) or {}).get("modele") is None)
    r = await cl.post("/api/rappels-paiement/aide-ia", headers=A, json=dict(T, ton="agressif"))
    v("ton inconnu : 400", r.status_code == 400)
    _prop["corps"] = "Payez 500 CHF tout de suite {montant} {echeance}"
    r = await cl.post("/api/rappels-paiement/aide-ia", headers=A, json=dict(T, ton="direct"))
    v("une proposition avec un montant inventé est écartée", r.status_code == 502 and r.json()["detail"]["type"] == "ia_refusee", r.text)
    async def _panne(*_):
        raise TimeoutError()
    rp.appeler_ia = _panne
    r = await cl.post("/api/rappels-paiement/aide-ia", headers=A, json=dict(T, ton="direct"))
    v("IA en panne : 502 clair", r.status_code == 502 and r.json()["detail"]["type"] == "ia_erreur", r.text)
    rp._appels_ia.clear()
    rp._appels_ia[rp.SUPER_ADMIN_EMAIL.lower()] = [datetime.now(timezone.utc).timestamp()] * rp.IA_LIMITE_HEURE
    r = await cl.post("/api/rappels-paiement/aide-ia", headers=A, json=dict(T, ton="direct"))
    v("limite par heure : 429", r.status_code == 429, r.status_code)
    rp._appels_ia.clear()
    rp.appeler_ia = _orig_ia

    print("── V650 : calculs de l'automatique")
    Z = datetime(2026, 11, 9, 11, 0, tzinfo=timezone.utc)   # un lundi, midi à Zurich
    v("lundi midi : ouvert", rp.auto_heure_ouvree(Z) is True)
    v("lundi 6 h : fermé", rp.auto_heure_ouvree(Z.replace(hour=5)) is False)
    v("samedi : fermé", rp.auto_heure_ouvree(Z + timedelta(days=5)) is False)
    A3 = ["J-3", "J0", "J+3"]
    v("J-4 : trop tôt", rp.auto_doit_envoyer("2026-11-10", A3, "2026-11-06") is False)
    v("J-3 : ouvert", rp.auto_doit_envoyer("2026-11-10", A3, "2026-11-07") is True)
    v("seul J+3 coché : J0 fermé", rp.auto_doit_envoyer("2026-11-10", ["J+3"], "2026-11-10") is False)
    v("aucun délai : fermé", rp.auto_doit_envoyer("2026-11-10", [], "2026-11-10") is False)
    v("après J+30 : fermé", rp.auto_doit_envoyer("2026-11-10", A3, "2026-12-11") is False)
    v("date illisible : fermé", rp.auto_doit_envoyer("x", A3, "2026-11-10") is False)
    T1 = "testeur@example.test"
    v("adresse exacte : acceptée", rp.adresse_de_test(T1, T1) is True)
    v("casse et espaces sans effet", rp.adresse_de_test(" Testeur@Example.test ", T1) is True)
    for mauvais, aut in (("testeur+x@example.test", T1), ("autre@example.test", T1), ("", T1), (None, T1), (T1, ""), (T1, None), ("", ""), ("x", "x")):
        v(f"refusé : {mauvais} / {aut}", rp.adresse_de_test(mauvais, aut) is False)

    print("── V650 : passage automatique")
    _ouvert = rp.auto_heure_ouvree
    rp.auto_heure_ouvree = lambda m=None: True
    await semer(db, flag=True)
    faux.Emails.__init__()
    await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "AUTOMATIQUE", "delais": A3, "confirmation_auto": True})
    b = await rp.passage_automatique()
    v("drapeau éteint : rien", b["actif"] is False and not faux.Emails.appels, b)
    await _drapeaux(db, DRAPEAU_AUTO=True, DRAPEAU_ENVOI_REEL=False)
    b = await rp.passage_automatique()
    v("automatique ouvert, envoi réel fermé : rien", b["envoyes"] == 0 and not faux.Emails.appels, b)
    plus = T1
    await db.subscriptions.update_one({"id": "s1"}, {"$set": {"email": plus}})
    await db.discount_codes.update_one({"id": "c1"}, {"$set": {"assignedEmail": plus}})
    await _drapeaux(db, DRAPEAU_TEST=True)
    b = await rp.passage_automatique()
    v("mode test sans adresse rangée : personne", b["envoyes"] == 0 and not faux.Emails.appels, b)
    await db[rp.COL_REGLAGES].insert_one({"_id": rp.ID_TEST_ADRESSE, "adresse": "autre@example.test"})
    b = await rp.passage_automatique()
    v("mode test, autre adresse rangée : personne", b["envoyes"] == 0 and not faux.Emails.appels, b)
    _a = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
    r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": _a["empreinte"]})
    v("mode test, envoi manuel vers une autre adresse : simulation", r.json().get("issue") == "simulation" and not faux.Emails.appels, r.text)
    await db[rp.COL_REGLAGES].update_one({"_id": rp.ID_TEST_ADRESSE}, {"$set": {"adresse": T1}})
    v("l'adresse de test n'apparaît pas dans les drapeaux publics", T1 not in json.dumps(await db.feature_flags.find_one({"id": "feature_flags"}, {"_id": 0})))
    b = await rp.passage_automatique()
    v("mode test : seule l'adresse rangée reçoit", b["envoyes"] == 1 and [x[0]["to"] for x in faux.Emails.appels] == [[plus]], faux.Emails.appels)
    b = await rp.passage_automatique()
    v("mode test, second passage : aucun doublon", b["envoyes"] == 0 and len(faux.Emails.appels) == 1, b)

    await semer(db, flag=True)
    faux.Emails.__init__()
    await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "AUTOMATIQUE", "delais": [], "confirmation_auto": True})
    await _drapeaux(db, DRAPEAU_AUTO=True)
    b = await rp.passage_automatique()
    v("tous les délais décochés : aucun envoi", b["envoyes"] == 0 and not faux.Emails.appels, b)
    v("relu vide, pas remplacé par les trois", (await cl.get("/api/rappels-paiement/reglages", headers=A)).json()["delais"] == [])
    v("simulation : aucune date annoncée", all(x["jalons"] == [] for x in (await cl.get("/api/rappels-paiement/simulation", headers=A)).json()["lignes"]))

    await semer(db, flag=True)
    faux.Emails.__init__()
    await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "AUTOMATIQUE", "delais": A3, "confirmation_auto": True})
    await db[rp.COL_REGLAGES].update_one({"_id": PARTENAIRE}, {"$set": {"mode": "AUTOMATIQUE", "delais": A3, "auto_actif_depuis": D(0)}})
    await db.subscriptions.update_one({"id": "s1"}, {"$set": {"coach_id": AUTRE}})
    await db.subscriptions.update_one({"id": "s-lea"}, {"$set": {"coach_id": AUTRE}})
    await _drapeaux(db, DRAPEAU_AUTO=True)
    await rp.passage_automatique()
    dest = [x[0]["to"][0] for x in faux.Emails.appels]
    v("code de la plateforme, abonnement marqué d'un autre coach : rien", "cliente@example.test" not in dest, dest)
    v("code du partenaire, abonnement marqué d'un autre coach : rien", "client-lea@example.test" not in dest, dest)
    v("les autres clients partent toujours", "offre@example.test" in dest, dest)

    await semer(db, flag=True)
    faux.Emails.__init__()
    await db.subscriptions.update_one({"id": "s-tom"}, {"$set": {"suivi_paiement.prochaine_echeance": D(-5)}})
    await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "AUTOMATIQUE", "delais": A3, "confirmation_auto": True})
    await db[rp.COL_REGLAGES].update_one({"_id": AUTRE}, {"$set": {"mode": "AUTOMATIQUE", "delais": A3, "auto_actif_depuis": D(0)}})
    await _drapeaux(db, DRAPEAU_AUTO=True)
    b = await rp.passage_automatique()
    dest = sorted(x[0]["to"][0] for x in faux.Emails.appels)
    v("les bons clients, et eux seuls", dest == ["cliente@example.test", "offre@example.test"], dest)
    for exclu, nom in (("stripe@example.test", "Stripe réel"), ("refus@example.test", "refus d'e-mails"), ("case@example.test", "suivi incomplet"),
                       ("client-lea@example.test", "partenaire resté en manuel"), ("client-tom@example.test", "échéance antérieure à l'activation")):
        v(f"exclu : {nom}", exclu not in dest, dest)
    d = await db[rp.COL_RAPPELS].find_one({"subscription_id": "s1"})
    v("historique automatique", d["statut"] == "envoye" and d["mode_envoi"] == "automatique" and d["envoye_par"] == "automatique" and d["palier_auto"] == "J0", d)
    n = len(faux.Emails.appels)
    b = await rp.passage_automatique()
    v("second passage du jour : aucun doublon", b["envoyes"] == 0 and len(faux.Emails.appels) == n, b)
    await _vieillir(db, "s1", 6)
    await rp.passage_automatique()
    v("6 jours : toujours rien", len(faux.Emails.appels) == n)
    await _vieillir(db, "s1", 8)
    await rp.passage_automatique()
    d2 = [x for x in faux.Emails.appels[n:] if x[0]["to"] == ["cliente@example.test"]]
    v("8 jours : le 2e", len(d2) == 1, faux.Emails.appels[n:])
    await _vieillir(db, "s1", 8)
    await rp.passage_automatique()
    await _vieillir(db, "s1", 8)
    await db.subscriptions.update_one({"id": "s1"}, {"$set": {"suivi_paiement.prochaine_echeance": D(1)}})
    await rp.passage_automatique()
    await _vieillir(db, "s1", 8)
    await rp.passage_automatique()
    v("3 rappels au plus, même si la date change", await db[rp.COL_RAPPELS].count_documents({"subscription_id": "s1", "statut": "envoye"}) == 3,
      await db[rp.COL_RAPPELS].count_documents({"subscription_id": "s1"}))

    await semer(db, flag=True)
    faux.Emails.__init__()
    await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "AUTOMATIQUE", "delais": A3, "confirmation_auto": True})
    await _drapeaux(db, DRAPEAU_AUTO=True)
    await cl.put("/api/rappels-paiement/modele", headers=A, json=T)
    _p, rp.PLAFOND_PASSAGE = rp.PLAFOND_PASSAGE, 1
    b = await rp.passage_automatique()
    rp.PLAFOND_PASSAGE = _p
    v("plafond par passage", len(faux.Emails.appels) == 1, b)
    v("le modèle du coach sert à l'automatique", faux.Emails.appels[0][0]["subject"] == "Un petit mot")
    await db[rp.COL_RAPPELS].delete_many({})
    faux.Emails.__init__()
    faux.Emails.reponse = TimeoutError()
    b = await rp.passage_automatique()
    v("panne : le passage s'arrête au premier", b.get("arret") is True and len(faux.Emails.appels) == 1, b)
    faux.Emails.reponse = None
    _sid = (await db[rp.COL_RAPPELS].find_one({"statut": "incertain"}))["subscription_id"]
    _mail = (await db.subscriptions.find_one({"id": _sid}))["email"]
    n = len(faux.Emails.appels)
    await rp.passage_automatique()
    v("résultat incertain : plus aucun envoi pour ce client", len(faux.Emails.appels) > n and not any(x[0]["to"] == [_mail] for x in faux.Emails.appels[n:]), faux.Emails.appels[n:])

    await semer(db, flag=True)
    faux.Emails.__init__()
    await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "AUTOMATIQUE", "delais": A3, "confirmation_auto": True})
    await _drapeaux(db, DRAPEAU_AUTO=True)
    _vrai = faux.Emails.send
    def _refuse_une(params, options=None):
        if params["to"] == ["cliente@example.test"]:
            faux.Emails.appels.append((params, options))
            raise ErreurResend(422)
        return _vrai(params, options)
    faux.Emails.send = _refuse_une
    b = await rp.passage_automatique()
    v("une adresse refusée n'arrête pas les suivants", "arret" not in b and any(x[0]["to"] == ["offre@example.test"] for x in faux.Emails.appels), b)
    n = len([x for x in faux.Emails.appels if x[0]["to"] == ["cliente@example.test"]])
    await rp.passage_automatique()
    v("refus du fournisseur : un seul essai par jour", n == 1 and len([x for x in faux.Emails.appels if x[0]["to"] == ["cliente@example.test"]]) == 1, n)
    v("refus : historique « echec », jamais « envoyé »", (await db[rp.COL_RAPPELS].find_one({"subscription_id": "s1"}))["statut"] == "echec")
    del faux.Emails.send
    await db[rp.COL_RAPPELS].delete_many({})
    faux.Emails.__init__()
    faux.Emails.reponse = ErreurResend(429)
    b = await rp.passage_automatique()
    v("trop de demandes : le passage s'arrête au premier", b.get("arret") is True and len(faux.Emails.appels) == 1, b)
    faux.Emails.__init__()
    await db[rp.COL_RAPPELS].delete_many({})
    r = await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "MANUEL", "delais": A3})
    v("désactivation : date effacée", r.json()["auto_actif_depuis"] is None, r.text)
    b = await rp.passage_automatique()
    v("coach revenu en manuel : rien", b["envoyes"] == 0 and not faux.Emails.appels, b)
    await db.subscriptions.update_one({"id": "s1"}, {"$set": {"suivi_paiement.prochaine_echeance": D(-2)}})
    r = await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "AUTOMATIQUE", "delais": A3, "confirmation_auto": True})
    b = await rp.passage_automatique()
    v("réactivation : l'ancienne échéance reste à l'écart", not any(x[0]["to"] == ["cliente@example.test"] for x in faux.Emails.appels), faux.Emails.appels)
    rp.auto_heure_ouvree = lambda m=None: False
    faux.Emails.__init__()
    await db[rp.COL_RAPPELS].delete_many({})
    b = await rp.passage_automatique()
    v("hors horaire : rien", b.get("hors_horaire") is True and not faux.Emails.appels, b)
    rp.auto_heure_ouvree = _ouvert
    await db.feature_flags.update_one({"id": "feature_flags"}, {"$set": {rp.DRAPEAU_AUTO: False}})
    r = await cl.get("/api/rappels-paiement/simulation", headers=A)
    v("simulation : aucun envoi", r.status_code == 200 and r.json()["aucun_envoi"] is True)
    await semer(db, flag=True)
    await db[rp.COL_RAPPELS].insert_one({"_id": "s1|manuel|1", "subscription_id": "s1", "palier": "manuel", "rang": 1, "statut": "incertain", "echeance": D(0), "premier_essai_le": datetime.now(timezone.utc).isoformat(), "maj_le": datetime.now(timezone.utc).isoformat()})
    L = {x["code"]: x for x in (await cl.get("/api/rappels-paiement/simulation", headers=A)).json()["lignes"]}
    v("simulation : un envoi à vérifier n'annonce aucune date", L["CODE-1"]["enverrait"] is False and L["CODE-1"]["jalons"] == [], L["CODE-1"])
    faux.Emails.__init__()


async def _ligne_de(cl, h, code):
    return next((x for x in (await cl.get("/api/rappels-paiement/liste", headers=h)).json()["lignes"] if x["code"] == code), None)


async def _envoi_ui(cl, h, sid):
    _a = (await cl.get("/api/rappels-paiement/%s/apercu" % sid, headers=h)).json()
    return await cl.post("/api/rappels-paiement/%s/envoyer" % sid, headers=h, json={"confirmation": True, "empreinte": _a.get("empreinte", "x")})


async def _empreinte_finance(db):
    return [await db.subscriptions.find({}, {"_id": 0}).sort("id", 1).to_list(100), await db.discount_codes.find({}, {"_id": 0}).sort("id", 1).to_list(100)]


async def tests_v652(db, cl, faux, A, P):
    _ouvert = rp.auto_heure_ouvree
    rp.auto_heure_ouvree = lambda m=None: True
    URL = "/api/rappels-paiement/%s/%s"

    print("── V652 : statuts, fonctions pures")
    v("exclu", rp.statut_affiche({"motif": "membre_exclu"}, None)["code"] == "exclu")
    v("suspendu", rp.statut_affiche({"motif": "abonnement_suspendu"}, None)["code"] == "suspendu")
    v("annulé (tous)", rp.statut_affiche({"ok": True}, {"type": "annule_tous"})["code"] == "annule")
    v("annulé (un)", rp.statut_affiche({"ok": True}, {"type": "deja_envoye", "doc": {"statut": "annule"}})["code"] == "annule")
    v("envoyé", rp.statut_affiche({"ok": True}, {"type": "deja_envoye", "doc": {"statut": "envoye"}})["code"] == "envoye")
    v("programmé", rp.statut_affiche({"ok": True}, {"action": "nouveau"}, D(1)) == {"code": "programme", "libelle": "Programmé", "date": D(1)})
    v("rien sinon", rp.statut_affiche({"ok": True}, {"action": "nouveau"}) is None)
    for st, att in (("active", False), ("superseded", False), ("archived", False), ("cancelled", True), ("expired", True), ("completed", True), ("inactive", True), ("resilie", True)):
        v(f"statut {st} : suspendu={att}", rp.abonnement_suspendu({"status": st}) is att)
    v("clés : adresse, en minuscules", rp.cle_membre("", {"email": "A@X.test"}, {"assignedEmail": "a@x.test"}) == ["%s|a@x.test" % rp.SUPER_ADMIN_EMAIL.lower()])
    v("clés : sans adresse, le code", rp.cle_membre("c@x.test", {"code": "abc"}) == ["c@x.test|code:ABC"])

    print("── V652 : permissions")
    await semer(db, flag=True)
    faux.Emails.__init__()
    for route in ("annuler", "exclure", "reactiver", "reprendre", "supprimer"):
        r = await cl.post(URL % ("s1", route), json={"confirmation": True, "portee": "tous"})
        v(f"{route} sans jeton : 403", r.status_code == 403, r.status_code)
        r = await cl.post(URL % ("s1", route), headers={"X-User-Email": rp.SUPER_ADMIN_EMAIL}, json={"confirmation": True, "portee": "tous"})
        v(f"{route} en-tête seul : 403", r.status_code == 403, r.status_code)
        r = await cl.post(URL % ("s1", route), headers=P, json={"confirmation": True, "portee": "tous"})
        v(f"{route} sur le client d'un autre coach : 404", r.status_code == 404, r.status_code)
        r = await cl.post(URL % ("s-lea", route), headers=A, json={"portee": "tous"})
        v(f"{route} sans confirmation : 400", r.status_code == 400, r.status_code)
    r = await cl.post(URL % ("s1", "annuler"), headers=A, json={"confirmation": True, "portee": "autre"})
    v("portée inconnue : 400", r.status_code == 400)
    r = await cl.post(URL % ("s1", "exclure"), headers=A, json={"confirmation": True, "motif": "x" * 201})
    v("motif trop long : 400", r.status_code == 400)
    r = await cl.post(URL % ("s1", "exclure"), headers=A, json={"confirmation": True, "motif": 5})
    v("motif non texte : 400", r.status_code == 400)
    v("aucune écriture après ces refus", await db[rp.COL_EXCLUSIONS].count_documents({}) == 0 and await db[rp.COL_RAPPELS].count_documents({}) == 0)

    print("── V652 : annuler ce rappel")
    avant = await _empreinte_finance(db)
    L = await _ligne_de(cl, A, "CODE-1")
    v("menu : les trois actions d'une ligne ordinaire", L["actions"] == {"annuler_un": True, "annuler_tous": True, "reprendre": False, "exclure": True, "reactiver": False, "supprimer": True}, L["actions"])
    r = await cl.post(URL % ("s1", "annuler"), headers=A, json={"confirmation": True, "portee": "un", "numero": 2})
    v("numéro périmé : refus, rien d'annulé", r.status_code == 409 and r.json()["detail"]["type"] == "etat_change" and await db[rp.COL_RAPPELS].count_documents({}) == 0, r.text)
    r = await cl.post(URL % ("s1", "annuler"), headers=A, json={"confirmation": True, "portee": "un", "numero": 1, "motif": "Payé en espèces"})
    v("annulation enregistrée", r.status_code == 200 and r.json()["annule"] is True, r.text)
    d = await db[rp.COL_RAPPELS].find_one({"subscription_id": "s1"})
    v("trace : statut, date, coach, motif", d["statut"] == "annule" and d["annule_le"] and d["envoye_par"] == rp.SUPER_ADMIN_EMAIL.lower() and d["motif_action"] == "Payé en espèces", d)
    v("aucun identifiant d'envoi : rien n'est parti", not d.get("resend_id") and not faux.Emails.appels)
    v("abonnement et code intacts", await _empreinte_finance(db) == avant)
    L = await _ligne_de(cl, A, "CODE-1")
    v("statut Annulé après rechargement", L["statut_rappel"]["code"] == "annule", L["statut_rappel"])
    v("prochain rappel après le délai", L["envoi"]["peut_envoyer"] is False and L["envoi"]["prochaine_le"][:10] == (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d"), L["envoi"])
    v("il n'y a pas d'aller-retour : le suivant est le numéro 2", L["envoi"]["numero"] == 2, L["envoi"])
    r = await _envoi_ui(cl, A, "s1")
    v("clic sur Envoyer : refus, aucun e-mail", r.status_code == 409 and not faux.Emails.appels, r.text)
    h = (await cl.get("/api/rappels-paiement/historique", headers=A)).json()["historique"]
    v("historique : l'annulation et son motif", any(x["statut"] == "annule" and x["motif_action"] == "Payé en espèces" for x in h), h)
    await _vieillir(db, "s1")
    await db[rp.COL_RAPPELS].update_many({"subscription_id": "s1", "statut": "annule"}, {"$set": {"effet_le": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()}})
    r = await _envoi_ui(cl, A, "s1")
    v("après le délai : le suivant part, en rang 2", r.status_code == 200 and (await db[rp.COL_RAPPELS].find_one({"subscription_id": "s1", "statut": "envoye"}))["rang"] == 2, r.text)
    r = await cl.post(URL % ("s1", "annuler"), headers=A, json={"confirmation": True, "portee": "un", "numero": 3})
    v("annuler le suivant pendant l'attente : possible", r.status_code == 200, r.text)
    d = await db[rp.COL_RAPPELS].find_one({"subscription_id": "s1", "rang": 3})
    v("sa date d'effet suit l'attente : pas d'envoi juste après", d["effet_le"][:10] == (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d"), d)
    L = await _ligne_de(cl, A, "CODE-1")
    v("3 places consommées : plus rien à annuler", L["envoi"]["type"] == "maximum_atteint" and L["actions"]["annuler_un"] is False, L["envoi"])
    v("preuve du rappel envoyé conservée", await db[rp.COL_RAPPELS].count_documents({"subscription_id": "s1", "statut": "envoye", "resend_id": {"$ne": None}}) == 1)

    print("── V652 : annuler après un refus du fournisseur")
    await semer(db, flag=True)
    faux.Emails.__init__()
    faux.Emails.reponse = ErreurResend(422)
    await _envoi_ui(cl, A, "s1")
    faux.Emails.__init__()
    r = await cl.post(URL % ("s1", "annuler"), headers=A, json={"confirmation": True, "portee": "un", "numero": 1})
    v("un refus remplacé par l'annulation", r.status_code == 200 and (await db[rp.COL_RAPPELS].find_one({"subscription_id": "s1"}))["statut"] == "annule", r.text)
    v("pas de seconde ligne", await db[rp.COL_RAPPELS].count_documents({"subscription_id": "s1"}) == 1)

    print("── V652 : annuler les rappels futurs")
    await semer(db, flag=True)
    faux.Emails.__init__()
    await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "AUTOMATIQUE", "delais": ["J-3", "J0", "J+3"], "confirmation_auto": True})
    await _drapeaux(db, DRAPEAU_AUTO=True)
    avant = await _empreinte_finance(db)
    L = await _ligne_de(cl, A, "CODE-1")
    v("Programmé, avec sa date", L["statut_rappel"]["code"] == "programme" and L["statut_rappel"]["date"] == D(0), L["statut_rappel"])
    r = await cl.post(URL % ("s1", "annuler"), headers=A, json={"confirmation": True, "portee": "tous", "motif": "Arrangement"})
    v("annulation de tous les rappels", r.status_code == 200 and r.json()["annule"] is True, r.text)
    r = await cl.post(URL % ("s1", "annuler"), headers=A, json={"confirmation": True, "portee": "tous"})
    v("double clic : une seule trace", r.status_code == 200 and r.json()["deja"] is True and await db[rp.COL_RAPPELS].count_documents({"subscription_id": "s1"}) == 1, r.text)
    b = await rp.passage_automatique()
    v("le planificateur ne recrée rien", not any(x[0]["to"] == ["cliente@example.test"] for x in faux.Emails.appels), faux.Emails.appels)
    r = await _envoi_ui(cl, A, "s1")
    v("clic sur Envoyer : refus", r.status_code == 409 and not any(x[0]["to"] == ["cliente@example.test"] for x in faux.Emails.appels), r.text)
    await db.subscriptions.update_one({"id": "s1"}, {"$set": {"suivi_paiement.prochaine_echeance": D(2), "suivi_paiement.note": "x"}})
    await rp.passage_automatique()
    v("changer la date ne recrée rien", not any(x[0]["to"] == ["cliente@example.test"] for x in faux.Emails.appels))
    await db.subscriptions.update_one({"id": "s1"}, {"$set": {"suivi_paiement.prochaine_echeance": D(0)}})
    L = await _ligne_de(cl, A, "CODE-1")
    v("statut Annulé, après rechargement", L["statut_rappel"]["code"] == "annule" and L["actions"]["annuler_tous"] is False and L["reste_a_payer"] == 200, L)
    v("le solde reste affiché, abonnement intact", (await db.subscriptions.find_one({"id": "s1"}, {"_id": 0}))["montant_encaisse"] == 200)
    await db.subscriptions.update_one({"id": "s1"}, {"$set": {"montant_encaisse": 250}})
    r = await _envoi_ui(cl, A, "s1")
    v("un acompte sur le même paiement ne recrée rien", r.status_code == 409 and not any(x[0]["to"] == ["cliente@example.test"] for x in faux.Emails.appels), r.text)
    await db[rp.COL_RAPPELS].delete_many({"subscription_id": "s1"})
    await db.subscriptions.update_one({"id": "s1"}, {"$set": {"montant_encaisse": 200, "suivi_paiement.montant_total": 600, "suivi_paiement.nb_paiements": 3, "suivi_paiement.paiement_actuel": 1}})
    r = await cl.post(URL % ("s1", "annuler"), headers=A, json={"confirmation": True, "portee": "tous"})
    v("paiement 2 sur 3 : ses rappels annulés", r.status_code == 200 and r.json()["annule"] is True, r.text)
    await db.subscriptions.update_one({"id": "s1"}, {"$set": {"montant_encaisse": 400, "suivi_paiement.paiement_actuel": 2}})
    L = await _ligne_de(cl, A, "CODE-1")
    v("paiement 3 sur 3, le 2 réellement encaissé : les rappels reprennent pour lui seul", L["possible"] is True and L["envoi"]["peut_envoyer"] is True and L["statut_rappel"]["code"] != "annule", L)

    print("── V652 : reprendre les rappels futurs")
    await semer(db, flag=True)
    faux.Emails.__init__()
    await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "AUTOMATIQUE", "delais": ["J-3", "J0", "J+3"], "confirmation_auto": True})
    await _drapeaux(db, DRAPEAU_AUTO=True)
    await db.subscriptions.update_one({"id": "s1"}, {"$set": {"suivi_paiement.prochaine_echeance": D(-2)}})
    r = await cl.post(URL % ("s1", "reprendre"), headers=A, json={"confirmation": True})
    v("rien à reprendre : refus", r.status_code == 409 and r.json()["detail"]["type"] == "pas_annule", r.text)
    await cl.post(URL % ("s1", "annuler"), headers=A, json={"confirmation": True, "portee": "tous", "motif": "Arrangement"})
    L = await _ligne_de(cl, A, "CODE-1")
    v("le menu propose de reprendre, plus d'annuler", L["actions"]["reprendre"] is True and L["actions"]["annuler_tous"] is False, L["actions"])
    avant = await _empreinte_finance(db)
    n = len(faux.Emails.appels)
    res = await asyncio.gather(cl.post(URL % ("s1", "reprendre"), headers=A, json={"confirmation": True, "motif": "Le membre a demandé"}),
                               cl.post(URL % ("s1", "reprendre"), headers=A, json={"confirmation": True}))
    v("double clic simultané : une seule reprise", sorted(x.status_code for x in res) == [200, 409], [x.text for x in res])
    v("la reprise n'envoie rien", len(faux.Emails.appels) == n)
    v("abonnement et code intacts", await _empreinte_finance(db) == avant)
    h = {x["statut"]: x for x in (await cl.get("/api/rappels-paiement/historique", headers=A)).json()["historique"]}
    v("historique : l'annulation reste, la reprise s'ajoute", set(h) >= {"annule_tous_leve", "reprise"} and h["annule_tous_leve"]["motif_action"] == "Arrangement", h)
    v("reprise : date et coach", h["reprise"]["annule_le"] and h["reprise"]["envoye_par"] == rp.SUPER_ADMIN_EMAIL.lower())
    L = await _ligne_de(cl, A, "CODE-1")
    v("éligibilité recalculée : rappel manuel de nouveau possible", L["possible"] is True and L["envoi"]["peut_envoyer"] is True and L["statut_rappel"] is None, L)
    await rp.passage_automatique()
    v("l'automatique ne revient pas sur l'échéance passée", not any(x[0]["to"] == ["cliente@example.test"] for x in faux.Emails.appels), faux.Emails.appels)
    s_ = {x["code"]: x for x in (await cl.get("/api/rappels-paiement/simulation", headers=A)).json()["lignes"]}
    v("simulation : même réponse", s_["CODE-1"]["motif_exclusion"] == "echeance_ancienne", s_["CODE-1"])
    await db.subscriptions.update_one({"id": "s1"}, {"$set": {"suivi_paiement.prochaine_echeance": D(0)}})
    await rp.passage_automatique()
    v("une échéance non passée repart, une fois", len([x for x in faux.Emails.appels if x[0]["to"] == ["cliente@example.test"]]) == 1, faux.Emails.appels)
    await rp.passage_automatique()
    v("aucun doublon au passage suivant", len([x for x in faux.Emails.appels if x[0]["to"] == ["cliente@example.test"]]) == 1)
    r = await cl.post(URL % ("s1", "annuler"), headers=A, json={"confirmation": True, "portee": "tous"})
    v("annuler de nouveau : possible", r.status_code == 200 and r.json().get("deja") is None, r.text)
    r = await cl.post(URL % ("s1", "reprendre"), headers=A, json={"confirmation": True})
    v("reprendre après un envoi : le délai est rappelé", r.status_code == 200 and "Relance possible" in r.json()["message"], r.text)
    r = await _envoi_ui(cl, A, "s1")
    v("la reprise ne contourne pas les 7 jours", r.status_code == 409, r.text)

    await semer(db, flag=True)
    faux.Emails.__init__()
    await cl.post(URL % ("s1", "annuler"), headers=A, json={"confirmation": True, "portee": "un", "numero": 1})
    await cl.post(URL % ("s1", "annuler"), headers=A, json={"confirmation": True, "portee": "tous"})
    await cl.post(URL % ("s1", "reprendre"), headers=A, json={"confirmation": True})
    v("un rappel annulé garde sa place après la reprise", await db[rp.COL_RAPPELS].count_documents({"subscription_id": "s1", "statut": "annule"}) == 1
      and (await _ligne_de(cl, A, "CODE-1"))["envoi"]["numero"] == 2, await _ligne_de(cl, A, "CODE-1"))
    await db[rp.COL_RAPPELS].delete_many({"subscription_id": "s1"})
    await cl.post(URL % ("s1", "annuler"), headers=A, json={"confirmation": True, "portee": "tous"})
    r = await cl.post(URL % ("s1", "reprendre"), headers=P, json={"confirmation": True})
    v("un autre coach ne reprend pas : 404", r.status_code == 404, r.status_code)
    await cl.post(URL % ("s1", "exclure"), headers=A, json={"confirmation": True})
    r = await cl.post(URL % ("s1", "reprendre"), headers=A, json={"confirmation": True})
    v("membre exclu : la reprise est refusée, l'annulation reste", r.status_code == 409 and r.json()["detail"]["type"] == "membre_exclu"
      and await db[rp.COL_RAPPELS].count_documents({"subscription_id": "s1", "statut": "annule_tous"}) == 1, r.text)
    await semer(db, flag=True)
    await cl.post(URL % ("s-lea", "annuler"), headers=P, json={"confirmation": True, "portee": "tous"})
    r = await cl.post(URL % ("s-lea", "reprendre"), headers=P, json={"confirmation": True})
    v("un partenaire reprend pour son propre client", r.status_code == 200, r.text)

    print("── V652 : exclure et réactiver")
    await semer(db, flag=True)
    faux.Emails.__init__()
    await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "AUTOMATIQUE", "delais": ["J-3", "J0", "J+3"], "confirmation_auto": True})
    await _drapeaux(db, DRAPEAU_AUTO=True)
    avant = await _empreinte_finance(db)
    _a_vieux = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
    r = await cl.post(URL % ("s1", "exclure"), headers=A, json={"confirmation": True, "motif": "Demande du membre"})
    v("exclusion enregistrée", r.status_code == 200 and r.json()["exclu"] is True, r.text)
    d = await db[rp.COL_EXCLUSIONS].find_one({})
    v("trace : date, coach, motif, journal", d["actif"] is True and d["par"] == rp.SUPER_ADMIN_EMAIL.lower() and d["motif"] == "Demande du membre" and d["le"] and d["journal"][0]["action"] == "exclu", d)
    v("abonnement et code intacts", await _empreinte_finance(db) == avant)
    r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": _a_vieux["empreinte"]})
    v("Envoyer malgré l'aperçu déjà ouvert : refus", r.status_code == 409 and r.json()["detail"]["type"] == "membre_exclu" and not faux.Emails.appels, r.text)
    L = await _ligne_de(cl, A, "CODE-1")
    v("statut Exclu, solde affiché, seule action : réactiver", L["statut_rappel"]["code"] == "exclu" and L["reste_a_payer"] == 200 and L["actions"] == {"annuler_un": False, "annuler_tous": False, "reprendre": False, "exclure": False, "reactiver": True, "supprimer": True}, L)
    a = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
    v("aperçu : impossible, avec le motif", a["possible"] is False and a["motif"] == "membre_exclu")
    await rp.passage_automatique()
    v("le planificateur respecte l'exclusion", not any(x[0]["to"] == ["cliente@example.test"] for x in faux.Emails.appels), faux.Emails.appels)
    v("les autres membres partent toujours", any(x[0]["to"] == ["offre@example.test"] for x in faux.Emails.appels), faux.Emails.appels)
    await db.subscriptions.insert_one(abo(id="s-bis", code="CODE-1B", email="CLIENTE@example.test"))
    await db.discount_codes.insert_one({"id": "c1b", "code": "CODE-1B", "coach_id": "", "assignedEmail": ""})
    v("même personne sur un autre code : exclue aussi, casse ignorée", (await _ligne_de(cl, A, "CODE-1B"))["motif"] == "membre_exclu")
    await db[rp.COL_REGLAGES].update_one({"_id": PARTENAIRE}, {"$set": {"x": 1}})
    await db.subscriptions.insert_one(abo(id="s-lea2", code="CODE-LEA2", coach_id=PARTENAIRE, email="cliente@example.test"))
    await db.discount_codes.insert_one({"id": "c-lea2", "code": "CODE-LEA2", "coach_id": PARTENAIRE, "assignedEmail": ""})
    v("l'exclusion d'un coach ne s'impose pas à un autre", (await _ligne_de(cl, P, "CODE-LEA2"))["motif"] != "membre_exclu", await _ligne_de(cl, P, "CODE-LEA2"))
    r = await cl.post(URL % ("s-lea", "exclure"), headers=P, json={"confirmation": True})
    v("un partenaire exclut son propre client", r.status_code == 200 and await db[rp.COL_EXCLUSIONS].count_documents({"coach_id": PARTENAIRE}) == 1, r.text)
    await db.subscriptions.delete_many({"id": {"$in": ["s-bis", "s-lea2"]}})
    await db.discount_codes.delete_many({"id": {"$in": ["c1b", "c-lea2"]}})

    n = len(faux.Emails.appels)
    await db[rp.COL_RAPPELS].delete_many({"subscription_id": "s1"})
    await db.subscriptions.update_one({"id": "s1"}, {"$set": {"suivi_paiement.prochaine_echeance": D(-2)}})
    r = await cl.post(URL % ("s1", "reactiver"), headers=A, json={"confirmation": True})
    v("réactivation enregistrée", r.status_code == 200 and r.json()["reactive"] is True and r.json()["eligible"] is True, r.text)
    d = await db[rp.COL_EXCLUSIONS].find_one({"_id": rp.cle_membre("", {"email": "cliente@example.test"})[0]})
    v("la trace reste : rien n'est supprimé", d["actif"] is False and d["reactive_par"] and [j["action"] for j in d["journal"]] == ["exclu", "reactive"] and d["reprise_jour"] == D(0), d)
    r = await cl.post(URL % ("s1", "reactiver"), headers=A, json={"confirmation": True})
    v("réactiver deux fois : refus", r.status_code == 409 and r.json()["detail"]["type"] == "pas_exclu", r.text)
    v("rien n'est renvoyé par la réactivation", len(faux.Emails.appels) == n)
    await rp.passage_automatique()
    v("l'automatique ne réexpédie pas l'ancienne échéance", not any(x[0]["to"] == ["cliente@example.test"] for x in faux.Emails.appels[n:]), faux.Emails.appels[n:])
    s_ = {x["code"]: x for x in (await cl.get("/api/rappels-paiement/simulation", headers=A)).json()["lignes"]}
    v("simulation : l'ancienne échéance reste à l'écart", s_["CODE-1"]["motif_exclusion"] == "echeance_ancienne", s_["CODE-1"])
    await db.subscriptions.update_one({"id": "s1"}, {"$set": {"suivi_paiement.prochaine_echeance": D(1)}})
    await rp.passage_automatique()
    v("l'échéance suivante repart", any(x[0]["to"] == ["cliente@example.test"] for x in faux.Emails.appels[n:]), faux.Emails.appels[n:])

    print("── V652 : abonnement inactif")
    await semer(db, flag=True)
    faux.Emails.__init__()
    await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "AUTOMATIQUE", "delais": ["J-3", "J0", "J+3"], "confirmation_auto": True})
    await _drapeaux(db, DRAPEAU_AUTO=True)
    await db.subscriptions.update_one({"id": "s1"}, {"$set": {"status": "cancelled"}})
    L = await _ligne_de(cl, A, "CODE-1")
    v("ligne gardée, statut Suspendu, solde affiché", L["statut_rappel"]["code"] == "suspendu" and L["reste_a_payer"] == 200 and L["possible"] is False, L)
    v("exclure reste possible, pas annuler", L["actions"] == {"annuler_un": False, "annuler_tous": False, "reprendre": False, "exclure": True, "reactiver": False, "supprimer": True}, L["actions"])
    await rp.passage_automatique()
    v("aucun rappel automatique", not any(x[0]["to"] == ["cliente@example.test"] for x in faux.Emails.appels))
    r = await _envoi_ui(cl, A, "s1")
    v("aucun rappel manuel non plus", r.status_code == 409 and not any(x[0]["to"] == ["cliente@example.test"] for x in faux.Emails.appels), r.text)
    await db.subscriptions.update_one({"id": "s1"}, {"$set": {"status": "cancelled", "montant_encaisse": 200}})
    v("le solde n'est pas effacé", (await db.subscriptions.find_one({"id": "s1"}))["suivi_paiement"]["montant_total"] == 400)
    await db.subscriptions.insert_one(abo(id="s1-neuf", code="CODE-1", email="cliente@example.test"))
    v("un abonnement actif sur le même code : pas de doublon de ligne", len([x for x in (await cl.get("/api/rappels-paiement/liste", headers=A)).json()["lignes"] if x["code"] == "CODE-1"]) == 1)
    await db.subscriptions.delete_one({"id": "s1-neuf"})
    await db.subscriptions.update_one({"id": "s1"}, {"$set": {"status": "superseded"}})
    v("abonnement remplacé : pas de ligne", await _ligne_de(cl, A, "CODE-1") is None)
    await db.subscriptions.update_one({"id": "s1"}, {"$set": {"status": "active"}})
    v("réactivé : la ligne redevient normale", (await _ligne_de(cl, A, "CODE-1"))["possible"] is True)

    print("── V652 : concurrence avec un envoi en cours")
    await semer(db, flag=True)
    faux.Emails.__init__()
    # L'annulation arrive pendant la réservation : la dernière vérification doit tout arrêter, sans appeler le fournisseur.
    _vrai_reserver = rp._reserver
    async def _reserver_puis_annuler(sub_id, *a, **k):
        doc = await _vrai_reserver(sub_id, *a, **k)
        r_ = await cl.post(URL % (sub_id, "annuler"), headers=A, json={"confirmation": True, "portee": "tous"})
        v("annulation pendant l'envoi : enregistrée et signalée", r_.status_code == 200 and r_.json()["envoi_en_cours"] is True, r_.text)
        return doc
    rp._reserver = _reserver_puis_annuler
    r = await _envoi_ui(cl, A, "s1")
    rp._reserver = _vrai_reserver
    v("annuler tout pendant la réservation : rien n'est parti", r.status_code == 409 and not faux.Emails.appels, r.text)
    await semer(db, flag=True)
    async def _reserver_puis_exclure(sub_id, *a, **k):
        doc = await _vrai_reserver(sub_id, *a, **k)
        await cl.post(URL % (sub_id, "exclure"), headers=A, json={"confirmation": True})
        return doc
    rp._reserver = _reserver_puis_exclure
    r = await _envoi_ui(cl, A, "s1")
    rp._reserver = _vrai_reserver
    v("exclure pendant la réservation : rien n'est parti", r.status_code == 409 and not faux.Emails.appels, r.text)
    await semer(db, flag=True)
    faux.Emails.__init__()
    await db[rp.COL_RAPPELS].insert_one({"_id": rp.cle_envoi("s1", 1), "subscription_id": "s1", "palier": rp.PALIER_MANUEL, "rang": 1, "statut": "en_cours", "maj_le": datetime.now(timezone.utc).isoformat()})
    r = await cl.post(URL % ("s1", "annuler"), headers=A, json={"confirmation": True, "portee": "un", "numero": 1})
    v("annuler ce rappel pendant son envoi : refus clair", r.status_code == 409 and r.json()["detail"]["type"] == "en_cours", r.text)
    await semer(db, flag=True)
    faux.Emails.__init__()
    _a = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
    res = await asyncio.gather(cl.post(URL % ("s1", "annuler"), headers=A, json={"confirmation": True, "portee": "un", "numero": 1}),
                               cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": _a["empreinte"]}))
    _sts = sorted(d_["statut"] for d_ in await db[rp.COL_RAPPELS].find({"subscription_id": "s1"}).to_list(5))
    v("annulation et envoi simultanés : un seul gagnant sur ce rang", (await db[rp.COL_RAPPELS].count_documents({"subscription_id": "s1", "rang": 1})) == 1, _sts)
    v("et l'état dit la vérité", (_sts == ["annule"] and not faux.Emails.appels) or ("envoye" in _sts and len(faux.Emails.appels) == 1) or _sts == ["echec"], (_sts, len(faux.Emails.appels), [x.status_code for x in res]))

    print("── V654 : supprimer définitivement")
    await semer(db, flag=True)
    faux.Emails.__init__()
    await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "AUTOMATIQUE", "delais": ["J-3", "J0", "J+3"], "confirmation_auto": True})
    await _drapeaux(db, DRAPEAU_AUTO=True)
    await db.subscriptions.insert_one(abo(id="s1-autre", code="CODE-1B", email="cliente@example.test"))
    await db.discount_codes.insert_one({"id": "c1b", "code": "CODE-1B", "coach_id": "", "assignedEmail": "cliente@example.test"})
    avant = await _empreinte_finance(db)
    _a_vieux = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
    r = await cl.post(URL % ("s1", "supprimer"), headers=P, json={"confirmation": True})
    v("un autre coach ne supprime pas : 404", r.status_code == 404 and await db[rp.COL_RAPPELS].count_documents({}) == 0, r.status_code)
    r = await cl.post(URL % ("s1", "supprimer"), headers=A, json={})
    v("sans confirmation : 400", r.status_code == 400)
    res = await asyncio.gather(cl.post(URL % ("s1", "supprimer"), headers=A, json={"confirmation": True, "motif": "Doublon"}),
                               cl.post(URL % ("s1", "supprimer"), headers=A, json={"confirmation": True, "motif": "Doublon"}))
    v("double clic simultané : une seule trace", all(x.status_code == 200 for x in res) and await db[rp.COL_RAPPELS].count_documents({"statut": "supprime"}) == 1, [x.text for x in res])
    v("abonnements et codes intacts", await _empreinte_finance(db) == avant)
    d = await db[rp.COL_RAPPELS].find_one({"statut": "supprime"})
    v("trace d'audit : date, coach, motif", d["annule_le"] and d["envoye_par"] == rp.SUPER_ADMIN_EMAIL.lower() and d["motif_action"] == "Doublon", d)
    v("disparu de la liste", await _ligne_de(cl, A, "CODE-1") is None)
    v("l'autre rappel du même membre reste", (await _ligne_de(cl, A, "CODE-1B"))["possible"] is True)
    s_ = [x["code"] for x in (await cl.get("/api/rappels-paiement/simulation", headers=A)).json()["lignes"]]
    v("disparu de la simulation", "CODE-1" not in s_ and "CODE-1B" in s_, s_)
    r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": _a_vieux["empreinte"]})
    v("aperçu déjà ouvert puis Envoyer : refus, aucun e-mail", r.status_code == 409 and r.json()["detail"]["type"] == "rappel_supprime" and not faux.Emails.appels, r.text)
    a = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
    v("aperçu impossible", a["possible"] is False and a["motif"] == "rappel_supprime")
    b = await rp.passage_automatique()
    _vers_s1 = [x for x in faux.Emails.appels if x[0]["to"] == ["cliente@example.test"]]
    v("le planificateur envoie l'autre rappel, pas celui-ci", len(_vers_s1) == 1 and await db[rp.COL_RAPPELS].count_documents({"subscription_id": "s1", "statut": {"$in": ["envoye", "en_cours"]}}) == 0, _vers_s1)
    await db.subscriptions.update_one({"id": "s1"}, {"$set": {"suivi_paiement.prochaine_echeance": D(2), "suivi_paiement.note": "x", "suivi_paiement.montant_total": 410}})
    v("changer la date ou le total ne le recrée pas", await _ligne_de(cl, A, "CODE-1") is None)
    await db.subscriptions.update_one({"id": "s1"}, {"$set": {"suivi_paiement.prochaine_echeance": D(0), "suivi_paiement.montant_total": 400}})
    await db.subscriptions.insert_one(abo(id="s1-renouv", code="CODE-1", email="cliente@example.test", status="superseded"))
    await db.subscriptions.delete_one({"id": "s1-renouv"})
    await db.subscriptions.update_one({"id": "s1"}, {"$set": {"status": "superseded"}})
    await db.subscriptions.insert_one(abo(id="s1-neuf", code="CODE-1", email="cliente@example.test"))
    v("même dette sur un abonnement renouvelé : pas recréé", await _ligne_de(cl, A, "CODE-1") is None)
    await db.subscriptions.delete_one({"id": "s1-neuf"})
    await db.subscriptions.update_one({"id": "s1"}, {"$set": {"status": "active"}})
    r = await cl.post(URL % ("s1", "supprimer"), headers=A, json={"confirmation": True})
    v("supprimer de nouveau : déjà fait, pas d'erreur", r.status_code == 200 and r.json()["deja"] is True, r.text)
    h = (await cl.get("/api/rappels-paiement/historique", headers=A)).json()["historique"]
    v("la décision reste à l'historique", any(x["statut"] == "supprime" and x["motif_action"] == "Doublon" for x in h), h)
    v("la preuve de l'envoi de l'autre rappel reste", any(x["statut"] == "envoye" for x in h), h)

    await semer(db, flag=True)
    faux.Emails.__init__()
    await cl.post(URL % ("s1", "exclure"), headers=A, json={"confirmation": True})
    await cl.post(URL % ("s1", "supprimer"), headers=A, json={"confirmation": True})
    v("une ligne exclue peut être supprimée, et disparaît", await _ligne_de(cl, A, "CODE-1") is None)
    await cl.post(URL % ("s1", "reactiver"), headers=A, json={"confirmation": True})
    v("réactiver le membre ne ressuscite pas le rappel supprimé", await _ligne_de(cl, A, "CODE-1") is None)
    v("supprimer n'a pas exclu le membre", await db[rp.COL_EXCLUSIONS].count_documents({"actif": True}) == 0)

    await semer(db, flag=True)
    await db.subscriptions.update_one({"id": "s1"}, {"$set": {"montant_encaisse": 200, "suivi_paiement.montant_total": 600, "suivi_paiement.nb_paiements": 3, "suivi_paiement.paiement_actuel": 1}})
    await cl.post(URL % ("s1", "supprimer"), headers=A, json={"confirmation": True})
    v("paiement 2 sur 3 supprimé : absent", await _ligne_de(cl, A, "CODE-1") is None)
    await db.subscriptions.update_one({"id": "s1"}, {"$set": {"montant_encaisse": 400, "suivi_paiement.paiement_actuel": 2}})
    v("paiement suivant, le 2 réellement encaissé : sa propre ligne existe", (await _ligne_de(cl, A, "CODE-1")) is not None)

    await semer(db, flag=True)
    faux.Emails.__init__()
    r = await cl.post(URL % ("s-lea", "supprimer"), headers=P, json={"confirmation": True})
    v("un partenaire supprime pour son propre client", r.status_code == 200 and await _ligne_de(cl, P, "CODE-LEA") is None, r.text)

    await semer(db, flag=True)
    faux.Emails.__init__()
    async def _reserver_puis_supprimer(sub_id, *a, **k):
        doc = await _vrai_reserver(sub_id, *a, **k)
        r_ = await cl.post(URL % (sub_id, "supprimer"), headers=A, json={"confirmation": True})
        v("suppression pendant un envoi : l'écran annonce l'envoi engagé", r_.status_code == 200 and r_.json()["envoi_engage"] is True and "a pu partir" in r_.json()["message"], r_.text)
        return doc
    rp._reserver = _reserver_puis_supprimer
    r = await _envoi_ui(cl, A, "s1")
    rp._reserver = _vrai_reserver
    v("suppression pendant la réservation : rien n'est parti", r.status_code == 409 and not faux.Emails.appels, r.text)
    v("et l'essai reste un échec, jamais un envoi", (await db[rp.COL_RAPPELS].find_one({"subscription_id": "s1", "rang": 1}))["statut"] == "echec")

    print("── V652 : rappels ordinaires")
    await semer(db, flag=True)
    faux.Emails.__init__()
    r = await _envoi_ui(cl, A, "s1")
    v("un rappel ordinaire part", r.status_code == 200 and len(faux.Emails.appels) == 1, r.text)
    L = await _ligne_de(cl, A, "CODE-1")
    v("statut Envoyé", L["statut_rappel"]["code"] == "envoye", L["statut_rappel"])
    rp.auto_heure_ouvree = _ouvert
    faux.Emails.__init__()


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
        v("il signe de son nom professionnel", r.json()["texte"].endswith("Lea Martin, Studio Lea\nCoach partenaire d'Afroboost") and "Bassi" not in r.json()["texte"], r.json()["texte"])
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
        for sid, motif in (("s-stripe", "stripe_recurrent"), ("s-opt", "refus_email"),
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
        d = await db[rp.COL_RAPPELS].find_one({"_id": rp.cle_envoi("s1")})
        v("historique : envoyé, identifiant Resend, auteur", d["statut"] == "envoye" and d["resend_id"] and d["envoye_par"] == ADMIN, d)
        v("abonnements et codes inchangés", await empreinte_base(db) == avant)
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]})
        v("deuxième clic : 409 deja_envoye", r.status_code == 409 and r.json()["detail"]["type"] == "deja_envoye", r.text)
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"], "reprise_incertain": True})
        v("un ancien champ « reprise » ne change rien", r.status_code == 409 and r.json()["detail"]["type"] == "deja_envoye", r.text)
        v("toujours un seul appel", len(faux.Emails.appels) == 1)
        hist = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()["historique"]
        v("l'historique apparaît dans l'aperçu", len(hist) == 1 and hist[0]["statut"] == "envoye", hist)
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"suivi_paiement.prochaine_echeance": D(1)}})
        ap2 = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap2["empreinte"]})
        v("changer la date ne contourne pas les 7 jours", r.status_code == 409 and r.json()["detail"]["type"] == "deja_envoye" and len(faux.Emails.appels) == 1, r.text)
        await db[rp.COL_RAPPELS].update_one({"_id": rp.cle_envoi("s1", 1)}, {"$set": {"envoye_le": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()}})
        ap2 = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap2["empreinte"]})
        v("après le délai, ce rappel compte comme le 2e du même paiement", r.status_code == 200 and len(faux.Emails.appels) == 2 and (await db[rp.COL_RAPPELS].find_one({"_id": rp.cle_envoi("s1", 2)}))["numero"] == 2, r.text)
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
        await db[rp.COL_RAPPELS].update_one({"_id": rp.cle_envoi("s1", 1)}, {"$set": {"envoye_le": il_y_a_8, "cree_le": il_y_a_8}})
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
        await db[rp.COL_RAPPELS].update_one({"_id": rp.cle_envoi("s1", 2)}, {"$set": {"envoye_le": il_y_a_8}})
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
        await db[rp.COL_RAPPELS].update_one({"_id": rp.cle_envoi("s1", 3)}, {"$set": {"envoye_le": il_y_a_8}})
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
        v("le super-admin voit le client du partenaire signé par lui", "Lea Martin, Studio Lea" in ap_l["texte"])
        r = await cl.post("/api/rappels-paiement/s-lea/envoyer", headers=A, json={"confirmation": True, "empreinte": ap_l["empreinte"]})
        v("les réponses vont au coach propriétaire", r.status_code == 200 and faux.Emails.appels[-1][0].get("reply_to") == PARTENAIRE, r.text)
        d = await db[rp.COL_RAPPELS].find_one({"_id": rp.cle_envoi("s-lea", 1)})
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
        d = await db[rp.COL_RAPPELS].find_one({"_id": rp.cle_envoi("s1")})
        v("historique : échec", d["statut"] == "echec")
        k1 = faux.Emails.appels[0][1]["idempotency_key"]
        faux.Emails.reponse = None
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps)
        v("après un refus, l'ancien aperçu ne sert plus", r.status_code == 409 and r.json()["detail"]["type"] == "donnees_changees" and len(faux.Emails.appels) == 1, r.text)
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]})
        v("nouvel essai réussi", r.status_code == 200, r.text)
        v("nouvelle clé (la précédente garde le refus chez Resend)", faux.Emails.appels[1][1]["idempotency_key"] != k1)
        d = await db[rp.COL_RAPPELS].find_one({"_id": rp.cle_envoi("s1")})
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
        d = await db[rp.COL_RAPPELS].find_one({"_id": rp.cle_envoi("s1")})
        v("historique : incertain", d["statut"] == "incertain")
        faux.Emails.reponse = None
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        v("aperçu : envoi fermé juste après l'incertitude", ap["envoi"]["peut_envoyer"] is False and ap["envoi"]["type"] == "incertain_bloque", ap["envoi"])
        rs = await asyncio.gather(*[cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]}) for _ in range(5)])
        v("double clic sur un envoi à vérifier : aucun appel", all(x.status_code == 409 for x in rs) and len(faux.Emails.appels) == 1, [x.status_code for x in rs])

        await semer(db, flag=True)
        faux.Emails.__init__()
        faux.Emails.reponse = ErreurResend(500)
        await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps)
        vieux = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        await db[rp.COL_RAPPELS].update_one({"_id": rp.cle_envoi("s1")}, {"$set": {"premier_essai_le": vieux}})
        faux.Emails.reponse = None
        n = len(faux.Emails.appels)
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=dict(corps, reprise_incertain=True))
        v("après 24 h : plus aucune reprise (Resend a oublié la clé)", r.status_code == 409 and r.json()["detail"]["type"] == "incertain_bloque" and len(faux.Emails.appels) == n, r.text)
        vieux = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        await db[rp.COL_RAPPELS].update_one({"_id": rp.cle_envoi("s1")}, {"$set": {"premier_essai_le": vieux, "maj_le": vieux}})
        for j in (False, True):
            r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=dict(corps, reprise_incertain=j))
            v(f"après 8 j, sans résolution fiable : toujours aucun envoi (demande : {j})", r.status_code == 409 and r.json()["detail"]["type"] == "incertain_bloque" and len(faux.Emails.appels) == n, r.text)
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"suivi_paiement.prochaine_echeance": D(1)}})
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"], "reprise_incertain": True})
        v("changer la date ne contourne pas l'incertitude", r.status_code == 409 and r.json()["detail"]["type"] == "incertain_bloque" and len(faux.Emails.appels) == n, r.text)
        d = await db[rp.COL_RAPPELS].find_one({"_id": rp.cle_envoi("s1", 1)})
        v("la ligne incertaine reste dans l'historique", d["statut"] == "incertain", d)

        print("── Le problème signalé : un refus ancien, puis une incertitude")
        await semer(db, flag=True)
        faux.Emails.__init__()
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        faux.Emails.reponse = ErreurResend(422)
        await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]})
        cle1 = rp.cle_envoi("s1")
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
        v("le vieux refus n'ouvre aucun renvoi", ap["envoi"]["peut_envoyer"] is False and ap["envoi"]["type"] == "incertain_bloque", ap["envoi"])
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
        _t0 = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        _e_vraie = rp.empreinte("s1", rp.eligibilite(await db.subscriptions.find_one({"id": "s1"}, {"_id": 0})), _t0["sujet"] + "\n" + _t0["texte"])
        vieux_j = rp.jeton_apercu(_e_vraie, "nouveau|1|0", ADMIN, datetime.now(timezone.utc) - timedelta(minutes=31))
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": vieux_j})
        v("aperçu de plus de 30 min : refus", r.status_code == 409 and r.json()["detail"]["type"] == "apercu_expire" and len(faux.Emails.appels) == 0, r.text)
        ap_a = (await cl.get("/api/rappels-paiement/s-lea/apercu", headers=A)).json()
        r = await cl.post("/api/rappels-paiement/s-lea/envoyer", headers=P, json={"confirmation": True, "empreinte": ap_a["empreinte"]})
        v("l'aperçu d'un autre coach ne sert pas", r.status_code == 409 and r.json()["detail"]["type"] == "donnees_changees" and len(faux.Emails.appels) == 0, r.text)

        print("── Signature partenaire, par la route")
        for mauvais in ("Afroboost Officiel", "Coach Bassi", "https://evil.example", "paie@evil.test", "x" * 61):
            r = await cl.put("/api/rappels-paiement/signature", headers=P, json={"nom": mauvais})
            v(f"saisie {mauvais[:24]!r} : refus expliqué", r.status_code == 400 and r.json()["detail"]["type"] == "nom_refuse" and r.json()["detail"]["message"].startswith("Nom :"), r.text)
            # Même si la base est modifiée à la main, le contrôle se refait à chaque aperçu et envoi.
            await db[rp.COL_REGLAGES].update_one({"_id": PARTENAIRE}, {"$set": {"signature.nom": mauvais}})
            r = await cl.get("/api/rappels-paiement/s-lea/apercu", headers=P)
            v(f"nom {mauvais[:24]!r} : aucun aperçu", r.json()["possible"] is False and r.json()["motif"] == "signature_manquante" and "texte" not in r.json(), r.text)
            r = await cl.post("/api/rappels-paiement/s-lea/envoyer", headers=P, json={"confirmation": True, "empreinte": ap_a["empreinte"]})
            v(f"nom {mauvais[:24]!r} : aucun envoi", r.status_code == 409 and r.json()["detail"]["type"] == "signature_manquante" and len(faux.Emails.appels) == 0, r.text)
        await db[rp.COL_REGLAGES].update_one({"_id": PARTENAIRE}, {"$set": {"signature.nom": "Lea Martin"}})
        r = await cl.put("/api/rappels-paiement/signature", headers=P, json={"nom": "Lea Martin", "activite": "Paie sur evil.com"})
        v("activité refusée, explication par champ", r.status_code == 400 and r.json()["detail"]["champ"] == "activite", r.text)
        r = await cl.put("/api/rappels-paiement/signature", headers=P, json={"nom": "Fit24"})
        v("nom légitime avec chiffres : accepté", r.status_code == 200 and r.json()["apercu"] == "Fit24\nCoach partenaire d'Afroboost", r.text)
        r = await cl.put("/api/rappels-paiement/signature", headers=P, json={"nom": "Bassirou Diop", "activite": "Danse"})
        v("Bassirou : accepté", r.status_code == 200, r.text)
        r = await cl.put("/api/rappels-paiement/signature", headers=A, json={"nom": "Autre"})
        v("la signature officielle ne se modifie pas", r.status_code == 400 and r.json()["detail"]["type"] == "signature_officielle", r.text)
        r = await cl.put("/api/rappels-paiement/signature", json={"nom": "Lea"})
        v("sans jeton : 403", r.status_code == 403)
        r = await cl.put("/api/rappels-paiement/signature", headers={"X-User-Email": PARTENAIRE}, json={"nom": "Lea"})
        v("avec le seul en-tête X-User-Email : 403", r.status_code == 403)
        v("un partenaire n'écrit que sa signature", (await db[rp.COL_REGLAGES].find_one({"_id": AUTRE}))["signature"]["nom"] == "Tom Roche")
        await db[rp.COL_REGLAGES].update_one({"_id": PARTENAIRE}, {"$set": {"signature": {"nom": "Lea Martin", "activite": "Studio Lea"}}})
        v("réglages : partenaire = champs ; Afroboost = signature officielle",
          (await cl.get("/api/rappels-paiement/reglages", headers=P)).json()["signature_officielle"] is False and (await cl.get("/api/rappels-paiement/reglages", headers=A)).json()["signature_officielle"] is True)

        print("── Envoi à vérifier : résolution sur preuve seulement")
        await semer(db, flag=True)
        faux.Emails.__init__()
        faux.Emails.reponse = TimeoutError()
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]})
        faux.Emails.reponse = None
        cle1 = rp.cle_envoi("s1")
        deb = datetime.now(timezone.utc) - timedelta(hours=24)
        await db[rp.COL_RAPPELS].update_one({"_id": cle1}, {"$set": {"premier_essai_le": deb.isoformat(), "maj_le": deb.isoformat()}})
        cle_avant = (await db[rp.COL_RAPPELS].find_one({"_id": cle1}))["idempotency_key"]
        n_envois = len(faux.Emails.appels)
        URL_V = "/api/rappels-paiement/s1/verifier-envoi"
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        v("statut visible : à vérifier, envoi fermé, action admin", ap["envoi"]["a_verifier"] is True and ap["envoi"]["verification_admin"] is True and ap["envoi"]["peut_envoyer"] is False and "Envoi à vérifier" in ap["envoi"]["message"], ap["envoi"])
        L = {x["code"]: x for x in (await cl.get("/api/rappels-paiement/liste", headers=A)).json()["lignes"]}
        v("la liste le montre aussi", L["CODE-1"]["envoi"]["a_verifier"] is True)
        for nom, h in (("sans jeton", {}), ("en-tête seul", {"X-User-Email": ADMIN}), ("partenaire", P), ("autre coach", O)):
            r = await cl.post(URL_V, headers=h, json={"resend_id": "abcd-1234"})
            v(f"vérifier, {nom} : 403", r.status_code == 403, r.status_code)
        r = await cl.post(URL_V, headers=A, json={})
        v("sans preuve : blocage maintenu, contact manuel proposé", r.status_code == 200 and r.json()["resolu"] is False and r.json()["motif"] == "aucune_preuve" and "hors du système" in r.json()["message"], r.text)
        r = await cl.post(URL_V, headers=A, json={"resend_id": "../../domains"})
        v("identifiant illisible : 400, le fournisseur n'est pas appelé", r.status_code == 400 and faux.Emails.lectures == [], r.text)
        r = await cl.post(URL_V, headers=A, json={"resend_id": "abcd-1234"})
        v("le fournisseur ne connaît pas cet e-mail : blocage maintenu", r.json()["resolu"] is False and r.json()["motif"] == "fournisseur_indisponible", r.text)
        cree = (deb + timedelta(seconds=3)).isoformat()
        bonne = {"to": ["cliente@example.test"], "subject": rp.OBJETS_RAPPEL[0], "created_at": cree, "last_event": "delivered", "from": "Afroboost <notifications@afroboost.com>"}
        for nom, mauvaise in (("autre destinataire", dict(bonne, to=["x@example.test"])), ("autre objet", dict(bonne, subject="Bienvenue")),
                              ("autre période", dict(bonne, created_at=(deb - timedelta(days=3)).isoformat()))):
            faux.Emails.fiche = mauvaise
            r = await cl.post(URL_V, headers=A, json={"resend_id": "abcd-1234"})
            v(f"preuve non conforme ({nom}) : blocage maintenu", r.json()["resolu"] is False and r.json()["motif"] == "preuve_non_conforme", r.text)
        d = await db[rp.COL_RAPPELS].find_one({"_id": cle1})
        v("rien n'a bougé après ces refus", d["statut"] == "incertain" and d["idempotency_key"] == cle_avant)
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        for j in (False, True):
            r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"], "reprise_incertain": j})
            v(f"sans preuve, jamais d'envoi (demande : {j})", r.status_code == 409 and r.json()["detail"]["type"] == "incertain_bloque" and len(faux.Emails.appels) == n_envois, r.text)
        faux.Emails.fiche = bonne
        avant = await empreinte_base(db)
        rs = await asyncio.gather(*[cl.post(URL_V, headers=A, json={"resend_id": "abcd-1234"}) for _ in range(5)])
        v("preuve conforme, 5 demandes : une seule résolution", sum(1 for x in rs if x.status_code == 200 and x.json().get("resolu") is True) == 1, [x.text for x in rs][:2])
        d = await db[rp.COL_RAPPELS].find_one({"_id": cle1})
        v("preuve conforme : confirmé, avec sa date réelle et sa trace", d["statut"] == "envoye" and d["resend_id"] == "abcd-1234" and d["envoye_le"][:19] == cree[:19] and d["resolution"]["par"] == ADMIN and d["resolution"]["source"] == "identifiant" and "erreur" not in d, d)
        v("la résolution N'ENVOIE RIEN", len(faux.Emails.appels) == n_envois)
        v("aucune clé réutilisée ni créée", d["idempotency_key"] == cle_avant and d["tentatives"] == 1, d)
        v("aucune donnée métier modifiée", await empreinte_base(db) == avant)
        r = await cl.post(URL_V, headers=A, json={"resend_id": "abcd-1234"})
        v("plus rien à vérifier : 409", r.status_code == 409 and r.json()["detail"]["type"] == "rien_a_verifier", r.text)
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        v("le délai de 7 jours part de l'envoi réel", ap["envoi"]["peut_envoyer"] is False and ap["envoi"]["type"] == "deja_envoye", ap["envoi"])
        print("── Preuve : journal central, preuve déjà utilisée")
        await db[rp.COL_RAPPELS].insert_one({"_id": rp.cle_envoi("s-case"), "subscription_id": "s-case", "palier": rp.PALIER_MANUEL, "echeance": D(0), "rang": 1, "statut": "incertain",
                                             "destinataire": "cliente@example.test", "premier_essai_le": deb.isoformat(), "maj_le": deb.isoformat(), "cree_le": deb.isoformat(), "tentatives": 1})
        r = await cl.post("/api/rappels-paiement/s-case/verifier-envoi", headers=A, json={"resend_id": "abcd-1234"})
        v("une preuve ne sert qu'à un rappel", r.json()["resolu"] is False and r.json()["motif"] == "preuve_deja_utilisee", r.text)
        await db[rc.COL_JOURNAL].insert_one({"reference": rp.cle_envoi("s-case"), "resend_id": "journal-5678"})
        faux.Emails.lectures = []
        r = await cl.post("/api/rappels-paiement/s-case/verifier-envoi", headers=A, json={})
        d = await db[rp.COL_RAPPELS].find_one({"_id": rp.cle_envoi("s-case")})
        v("le journal central fournit la preuve, le fournisseur la confirme", r.json()["resolu"] is True and faux.Emails.lectures == ["journal-5678"] and d["resolution"]["source"] == "journal", r.text)
        await db[rp.COL_RAPPELS].insert_one({"_id": rp.cle_envoi("s-lea"), "subscription_id": "s-lea", "coach_id": PARTENAIRE, "palier": rp.PALIER_MANUEL, "echeance": D(0), "rang": 1, "statut": "incertain",
                                             "destinataire": "client-lea@example.test", "premier_essai_le": deb.isoformat(), "maj_le": deb.isoformat(), "cree_le": deb.isoformat(), "tentatives": 1})
        ap = (await cl.get("/api/rappels-paiement/s-lea/apercu", headers=P)).json()
        v("partenaire : statut visible, aucune action de résolution", ap["envoi"]["a_verifier"] is True and ap["envoi"]["verification_admin"] is False, ap["envoi"])
        r = await cl.get("/api/rappels-paiement/s-lea/apercu", headers=O)
        v("isolation : un autre coach ne voit toujours rien", r.status_code == 404)
        v("rappel Afroboost : signature officielle", (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()["texte"].endswith("Coach Bassi, d'Afroboost"))

        await semer(db, flag=True)
        faux.Emails.__init__()
        faux.Emails.reponse = {"pas_d_identifiant": True}
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps)
        v("réponse sans identifiant : incertain", r.status_code == 502 and r.json()["detail"]["type"] == "incertain", r.text)

        await semer(db, flag=True)
        faux.Emails.__init__()
        faux.Emails.reponse = None
        cle = rp.cle_envoi("s1")
        recent = datetime.now(timezone.utc).isoformat()
        await db[rp.COL_RAPPELS].insert_one({"_id": cle, "rang": 1, "statut": "en_cours", "maj_le": recent, "premier_essai_le": recent, "subscription_id": "s1", "echeance": D(0), "palier": rp.PALIER_MANUEL, "cree_le": recent})
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps)
        v("un envoi en cours bloque le suivant", r.status_code == 409 and r.json()["detail"]["type"] == "en_cours" and len(faux.Emails.appels) == 0, r.text)
        vieux = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        await db[rp.COL_RAPPELS].update_one({"_id": cle}, {"$set": {"maj_le": vieux}})
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json=corps)
        v("processus disparu : envoi à vérifier, aucun appel", r.status_code == 409 and r.json()["detail"]["type"] == "incertain_bloque" and len(faux.Emails.appels) == 0, r.text)
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
        v("automatique sans confirmation explicite : 400", r.status_code == 400, r.text)
        r = await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "AUTOMATIQUE", "delais": ["J0", "J+3"], "confirmation_auto": True})
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
        await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "AUTOMATIQUE", "delais": ["J-3", "J0", "J+3"], "confirmation_auto": True})
        avant, avant_n = await empreinte_base(db), await db[rp.COL_RAPPELS].count_documents({})
        r = await cl.get("/api/rappels-paiement/simulation", headers=A)
        s = r.json()
        v("réponse marquée simulation", s["simulation"] is True and s["aucun_envoi"] is True, s)
        v("AUCUN e-mail, même drapeau allumé et mode automatique", len(faux.Emails.appels) == 0)
        v("aucune écriture", await empreinte_base(db) == avant and await db[rp.COL_RAPPELS].count_documents({}) == avant_n)
        L = {x["code"]: x for x in s["lignes"]}
        v("cas normal : enverrait", L["CODE-1"]["enverrait"] is True and len(L["CODE-1"]["jalons"]) == 3, L.get("CODE-1"))
        v("saison_2x : n'enverrait pas", L["CODE-STRIPE"]["enverrait"] is False and L["CODE-STRIPE"]["motif_exclusion"] == "stripe_recurrent")
        v("offre saison_2x sans abonnement Stripe : un paiement manuel, il enverrait", L["CODE-OFFRE"]["enverrait"] is True, L["CODE-OFFRE"])
        v("case non cochée : n'enverrait pas tout seul", L["CODE-CASE"]["motif_exclusion"] == "suivi_incomplet")
        v("refus d'e-mails : n'enverrait pas", L["CODE-OPT"]["enverrait"] is False)
        r = await cl.get("/api/rappels-paiement/simulation", headers=P)
        v("un partenaire ne simule que ses clients", [x["code"] for x in r.json()["lignes"]] == ["CODE-LEA"], r.text)
        v("partenaire sans nom : n'enverrait pas", L["CODE-SANSNOM"]["enverrait"] is False)

        print("── Revue indépendante : remplacer l'abonnement ne vide rien")
        await semer(db, flag=True)
        faux.Emails.__init__()
        faux.Emails.reponse = TimeoutError()
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]})
        faux.Emails.reponse = None
        n_envois = len(faux.Emails.appels)
        await db[rp.COL_RAPPELS].update_one({"subscription_id": "s1"}, {"$set": {"coach_id": ""}})
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"status": "superseded"}})
        await db.subscriptions.insert_one(abo(id="s1-nouveau"))
        ap = (await cl.get("/api/rappels-paiement/s1-nouveau/apercu", headers=A)).json()
        v("nouvel abonnement, même personne : envoi fermé", ap["envoi"]["peut_envoyer"] is False, ap["envoi"])
        r = await cl.post("/api/rappels-paiement/s1-nouveau/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"], "reprise_incertain": True})
        v("nouvel abonnement : aucun message", r.status_code == 409 and len(faux.Emails.appels) == n_envois, r.text)
        print("── Revue indépendante : personne ne bloque le client d'un autre coach")
        await semer(db, flag=True)
        faux.Emails.__init__()
        await db.subscriptions.update_one({"id": "s-tom"}, {"$set": {"email": "client-lea@example.test"}})
        ap = (await cl.get("/api/rappels-paiement/s-lea/apercu", headers=P)).json()
        await cl.post("/api/rappels-paiement/s-lea/envoyer", headers=P, json={"confirmation": True, "empreinte": ap["empreinte"]})
        ap = (await cl.get("/api/rappels-paiement/s-tom/apercu", headers=O)).json()
        v("même personne chez un autre coach : indépendant, aucune fuite", ap["envoi"]["peut_envoyer"] is True and ap["historique"] == [], ap["envoi"])
        print("── Revue indépendante : code en double, coach désactivé")
        await semer(db, flag=True)
        await db.discount_codes.insert_one({"id": "c2bis", "code": "code-lea", "coach_id": AUTRE, "assignedEmail": ""})
        r = await cl.get("/api/rappels-paiement/s-lea/apercu", headers=O)
        v("doublon de code chez un autre coach : aucun accès", r.status_code == 404, r.status_code)
        r = await cl.get("/api/rappels-paiement/s-lea/apercu", headers=P)
        v("doublon : le propriétaire non plus, à vérifier d'abord", r.status_code == 404, r.status_code)
        _codes_vus = []
        for h in (P, O):
            _codes_vus += [x["code"].upper() for x in (await cl.get("/api/rappels-paiement/liste", headers=h)).json()["lignes"]]
        v("doublon : absent des listes des deux coachs", "CODE-LEA" not in _codes_vus, _codes_vus)
        r = await cl.get("/api/rappels-paiement/s-lea/apercu", headers=A)
        v("le super-admin voit le motif", r.status_code == 200 and r.json()["motif"] == "code_ambigu", r.text)
        await semer(db, flag=True)
        await db.coaches.update_one({"email": PARTENAIRE}, {"$set": {"is_active": False}})
        r = await cl.get("/api/rappels-paiement/liste", headers=P)
        v("coach désactivé : 403", r.status_code == 403, r.status_code)
        print("── Revue indépendante : l'aperçu couvre le texte, la simulation n'écrit rien")
        await semer(db, flag=True)
        faux.Emails.__init__()
        ap = (await cl.get("/api/rappels-paiement/s-lea/apercu", headers=P)).json()
        await db[rp.COL_REGLAGES].update_one({"_id": PARTENAIRE}, {"$set": {"signature.nom": "Autre Nom"}})
        r = await cl.post("/api/rappels-paiement/s-lea/envoyer", headers=P, json={"confirmation": True, "empreinte": ap["empreinte"]})
        v("signature changée après l'aperçu : refus", r.status_code == 409 and len(faux.Emails.appels) == 0, r.text)
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"name": "https://evil.example/x"}})
        v("nom client douteux : « Bonjour, »", (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()["texte"].startswith("Bonjour,\n"))
        await semer(db)
        vieux = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        await db[rp.COL_RAPPELS].insert_one({"_id": rp.cle_envoi("s1"), "subscription_id": "s1", "coach_id": "", "destinataire": "x@example.test", "palier": rp.PALIER_MANUEL, "echeance": D(-1), "rang": 1, "statut": "en_cours", "maj_le": vieux, "premier_essai_le": vieux, "cree_le": vieux})
        ap = (await cl.get("/api/rappels-paiement/s-case/apercu", headers=A)).json()
        await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": "x"})
        v("drapeau éteint : un état interrompu n'est même pas écrit", (await db[rp.COL_RAPPELS].find_one({"_id": rp.cle_envoi("s1")}))["statut"] == "en_cours")
        r = await cl.put("/api/rappels-paiement/reglages", headers=A, json={"mode": "MANUEL", "delais": [[]]})
        v("délais illisibles : 400", r.status_code == 400, r.status_code)

        print("── DÉCISION 1 : un envoi incertain n'est plus jamais repris")
        await semer(db, flag=True)
        faux.Emails.__init__()
        faux.Emails.reponse = TimeoutError()
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]})
        faux.Emails.reponse = None
        n = len(faux.Emails.appels)
        for nom, age in (("20 min", timedelta(minutes=20)), ("2 h", timedelta(hours=2)), ("24 h", timedelta(hours=24)), ("30 j", timedelta(days=30))):
            quand = (datetime.now(timezone.utc) - age).isoformat()
            await db[rp.COL_RAPPELS].update_many({"subscription_id": "s1"}, {"$set": {"maj_le": quand, "premier_essai_le": quand}})
            ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
            v(f"après {nom} : « Envoi à vérifier », envoi fermé", ap["envoi"]["a_verifier"] is True and ap["envoi"]["peut_envoyer"] is False and "Envoi à vérifier" in ap["envoi"]["message"], ap["envoi"])
            for j in (False, True):
                r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"], "reprise_incertain": j})
                v(f"après {nom}, reprise demandée {j} : aucun appel au fournisseur", r.status_code == 409 and len(faux.Emails.appels) == n, r.text)

        print("── DÉCISION 1 : résolution par le super-admin seulement")
        URL_V = "/api/rappels-paiement/s1/verifier-envoi"
        deb = datetime.now(timezone.utc) - timedelta(hours=30)

        async def _incertain_ancien(heures=30):
            await semer(db, flag=True)
            faux.Emails.__init__()
            faux.Emails.reponse = TimeoutError()
            ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
            await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]})
            faux.Emails.reponse = None
            q = (datetime.now(timezone.utc) - timedelta(hours=heures)).isoformat()
            await db[rp.COL_RAPPELS].update_one({"_id": rp.cle_envoi("s1")}, {"$set": {"premier_essai_le": q, "maj_le": q}})
            return ap["empreinte"]

        def _mail(heures, a="autre@example.test", objet="Autre sujet", i="m-000001"):
            return {"id": i, "to": [a], "subject": objet, "created_at": (datetime.now(timezone.utc) - timedelta(hours=heures)).isoformat(), "from": "Afroboost <notifications@afroboost.com>"}
        await _incertain_ancien(2)
        r = await cl.post(URL_V, headers=A, json={"verifier_absence": True})
        v("moins de 24 h : trop tôt, blocage maintenu", r.json()["resolu"] is False and r.json()["motif"] == "trop_tot" and faux.Emails.listes == [], r.text)
        jeton_ancien = await _incertain_ancien()
        n = len(faux.Emails.appels)
        for nom, pages in (("fournisseur en panne", ErreurResend(500)), ("liste vide", [{"data": [], "has_more": False}]),
                           ("liste qui s'arrête avant la période", [{"data": [_mail(29)], "has_more": False}]),
                           ("date illisible", [{"data": [dict(_mail(29), created_at="?"), _mail(40)], "has_more": False}]),
                           ("ordre inattendu", [{"data": [_mail(40), _mail(29), _mail(50)], "has_more": False}]),
                           ("réponse illisible", ["n'importe quoi"]),
                           ("fiche sans destinataire", [{"data": [{k: x for k, x in _mail(29).items() if k != "to"}, _mail(40)], "has_more": False}]),
                           ("destinataire en objet", [{"data": [dict(_mail(29), to=[{"email": "cliente@example.test"}]), _mail(40)], "has_more": False}]),
                           ("fiche sans objet", [{"data": [{k: x for k, x in _mail(29).items() if k != "subject"}, _mail(40)], "has_more": False}]),
                           ("objet ressemblant pour cette personne", [{"data": [_mail(29, a="cliente@example.test", objet="Rappel : ton paiement"), _mail(40)], "has_more": False}]),
                           ("objet « Re: Rappel »", [{"data": [_mail(29, a="cliente@example.test", objet="Re: Rappel : ton deuxième"), _mail(40)], "has_more": False}]),
                           ("objet encodé", [{"data": [_mail(29, a="cliente@example.test", objet="=?UTF-8?Q?xx?="), _mail(40)], "has_more": False}]),
                           ("objet « ton paiement »", [{"data": [_mail(29, a="cliente@example.test", objet="Ton paiement Afroboost"), _mail(40)], "has_more": False}])):
            faux.Emails.listes, faux.Emails.pages = [], pages
            r = await cl.post(URL_V, headers=A, json={"verifier_absence": True})
            d = await db[rp.COL_RAPPELS].find_one({"_id": rp.cle_envoi("s1")})
            v(f"{nom} : preuve insuffisante, blocage maintenu", r.json()["resolu"] is False and r.json()["motif"] == "preuve_insuffisante" and "hors du système" in r.json()["message"] and d["statut"] == "incertain", r.text)
        faux.Emails.listes = []
        faux.Emails.pages = [{"data": [_mail(29, a="cliente@example.test", objet=rp.OBJETS_RAPPEL[0], i="m-111111"), _mail(29.5, a="CLIENTE@example.test", objet=rp.OBJETS_RAPPEL[1], i="m-222222"), _mail(40)], "has_more": False}]
        r = await cl.post(URL_V, headers=A, json={"verifier_absence": True})
        v("deux e-mails possibles : impossible de trancher, blocage maintenu", r.json()["resolu"] is False and r.json()["motif"] == "preuve_insuffisante", r.text)
        for nom, h in (("sans jeton", {}), ("partenaire", P), ("autre coach", O)):
            r = await cl.post(URL_V, headers=h, json={"verifier_absence": True})
            v(f"absence, {nom} : 403", r.status_code == 403, r.status_code)
        print("── Absence prouvée : tentative distincte, règles normales")
        faux.Emails.listes = []
        faux.Emails.pages = [{"data": [_mail(5), _mail(29)], "has_more": True}, {"data": [_mail(29.5, a="autre@example.test", objet=rp.OBJETS_RAPPEL[0]), _mail(40)], "has_more": True}]
        avant = await empreinte_base(db)
        r = await cl.post(URL_V, headers=A, json={"verifier_absence": True})
        d = await db[rp.COL_RAPPELS].find_one({"_id": rp.cle_envoi("s1")})
        v("toute la période lue, aucun e-mail pour cette personne : absence prouvée", r.json()["resolu"] is True and r.json()["non_parti"] is True and d["statut"] == "non_parti" and d["resolution"]["source"] == "historique_fournisseur" and d["resolution"]["par"] == ADMIN, r.text)
        v("les pages ont été suivies", faux.Emails.listes[1].get("after") == "m-000001", faux.Emails.listes)
        v("la vérification n'envoie rien", len(faux.Emails.appels) == n)
        v("aucune donnée métier modifiée", await empreinte_base(db) == avant)
        ancienne_cle = d["idempotency_key"]
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": jeton_ancien})
        v("l'ancienne confirmation ne sert plus", r.status_code == 409 and r.json()["detail"]["type"] == "donnees_changees" and len(faux.Emails.appels) == n, r.text)
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        v("aperçu : nouvelle tentative possible, toujours le 1er rappel", ap["envoi"]["peut_envoyer"] is True and ap["envoi"]["etape"] == "Rappel" and ap["envoi"]["a_verifier"] is False, ap["envoi"])
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]})
        d2 = await db[rp.COL_RAPPELS].find_one({"_id": rp.cle_envoi("s1", 2)})
        v("tentative distincte : nouveau rang, nouvelle clé", r.status_code == 200 and d2["statut"] == "envoye" and d2["numero"] == 1 and d2["idempotency_key"] != ancienne_cle and faux.Emails.appels[-1][1]["idempotency_key"] != ancienne_cle, d2)
        hist = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()["historique"]
        v("l'historique garde les deux lignes", sorted(h["statut"] for h in hist) == ["envoye", "non_parti"], hist)
        print("── Envoi prouvé par l'historique : il compte")
        await _incertain_ancien()
        faux.Emails.listes = []
        faux.Emails.pages = [{"data": [_mail(29, a="cliente@example.test", objet=rp.OBJETS_RAPPEL[0], i="m-333333"), _mail(40)], "has_more": False}]
        faux.Emails.fiche = _mail(29, a="cliente@example.test", objet=rp.OBJETS_RAPPEL[0], i="m-333333")
        r = await cl.post(URL_V, headers=A, json={"verifier_absence": True})
        d = await db[rp.COL_RAPPELS].find_one({"_id": rp.cle_envoi("s1")})
        v("l'e-mail existait : l'envoi est confirmé et compté, jamais « non parti »", r.json()["resolu"] is True and not r.json().get("non_parti") and d["statut"] == "envoye" and d["numero"] == 1 and d["resend_id"] == "m-333333", r.text)
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        v("il compte : relance 1 à venir, délai en cours selon sa date réelle", ap["envoi"]["peut_envoyer"] is False and ap["envoi"]["type"] == "deja_envoye", ap["envoi"])
        await _incertain_ancien()
        await db[rc.COL_JOURNAL].insert_one({"reference": rp.cle_envoi("s1"), "resend_id": "journal-9999"})
        faux.Emails.listes = []
        faux.Emails.fiche = ErreurResend(404)
        r = await cl.post(URL_V, headers=A, json={"verifier_absence": True})
        d = await db[rp.COL_RAPPELS].find_one({"_id": rp.cle_envoi("s1")})
        v("le journal connaît un identifiant : aucune absence possible", r.json()["resolu"] is False and d["statut"] == "incertain" and faux.Emails.listes == [], r.text)

        print("── DÉCISION 2 : trois rappels par paiement attendu, quoi que fasse le coach")
        await semer(db, flag=True)
        faux.Emails.__init__()
        vieux = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()

        async def _un_rappel(modif):
            await db[rp.COL_RAPPELS].update_many({"subscription_id": "s1", "statut": "envoye"}, {"$set": {"envoye_le": vieux}})
            await db.subscriptions.update_one({"id": "s1"}, {"$set": modif})
            ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
            return await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap.get("empreinte", "")})
        r = await _un_rappel({"suivi_paiement.prochaine_echeance": D(0)})
        v("1er rappel", r.status_code == 200 and len(faux.Emails.appels) == 1, r.text)
        r = await _un_rappel({"suivi_paiement.prochaine_echeance": D(1)})
        v("2e rappel, date changée : il compte", r.status_code == 200 and len(faux.Emails.appels) == 2, r.text)
        r = await _un_rappel({"suivi_paiement.note_interne": "note"})
        v("3e rappel, note changée : il compte", r.status_code == 200 and len(faux.Emails.appels) == 3, r.text)
        for nom, modif in (("date changée", {"suivi_paiement.prochaine_echeance": D(2)}), ("note changée", {"suivi_paiement.note_interne": "autre"}),
                           ("total corrigé", {"suivi_paiement.montant_total": 450}), ("nouvelle date, encore", {"suivi_paiement.prochaine_echeance": D(-1)})):
            r = await _un_rappel(modif)
            v(f"4e rappel, {nom} : refusé", r.status_code == 409 and r.json()["detail"]["type"] == "maximum_atteint" and len(faux.Emails.appels) == 3, r.text)
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        rs = await asyncio.gather(*[cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]}) for _ in range(5)])
        v("4e rappel, demandes simultanées : aucun message", all(x.status_code == 409 for x in rs) and len(faux.Emails.appels) == 3, [x.status_code for x in rs])
        A2 = {"Authorization": "Bearer " + jwt.encode({"email": ADMIN, "sub": ADMIN, "iat": 1}, os.environ["JWT_SECRET"], algorithm="HS256")}
        r = await cl.get("/api/rappels-paiement/s1/apercu", headers=A2)
        v("nouvelle session : le compteur reste", r.json()["envoi"]["type"] == "maximum_atteint", r.text)
        await db.subscriptions.update_one({"id": "s1"}, {"$unset": {"suivi_paiement.plusieurs_fois": "", "suivi_paiement.nb_paiements": "", "suivi_paiement.paiement_actuel": ""}})
        r = await cl.get("/api/rappels-paiement/s1/apercu", headers=A)
        v("case décochée : le compteur reste", r.json()["envoi"]["type"] == "maximum_atteint", r.text)
        hist = r.json()["historique"]
        v("historique : Relance 2, Relance 1, Rappel", [h["etape"] for h in hist] == ["Relance 2", "Relance 1", "Rappel"], [h["etape"] for h in hist])
        print("── DÉCISION 2 : un paiement réellement distinct, identifié sans ambiguïté")

        async def _sequence(modif_avant=None):
            await semer(db, flag=True)
            faux.Emails.__init__()
            await db.subscriptions.update_one({"id": "s1"}, {"$set": {"suivi_paiement": suivi(montant_total=600, nb_paiements=3, paiement_actuel=1)}})
            for _ in range(3):
                await _un_rappel({})
        await _sequence()
        v("échéancier en 3 fois : 3 rappels pour le 2e paiement", len(faux.Emails.appels) == 3)
        r = await _un_rappel({"montant_encaisse": 300})
        v("un acompte ne change pas le paiement : refus", r.status_code == 409 and r.json()["detail"]["type"] == "maximum_atteint", r.text)
        await _sequence()
        r = await _un_rappel({"suivi_paiement.paiement_actuel": 2})
        v("rang avancé sans encaissement : identité incertaine, bloqué", r.status_code == 409 and r.json()["detail"]["type"] == "paiement_ambigu" and len(faux.Emails.appels) == 3, r.text)
        r = await cl.get("/api/rappels-paiement/s1/apercu", headers=A)
        v("le motif est affiché", r.json()["envoi"]["peut_envoyer"] is False and "même paiement" in r.json()["envoi"]["message"], r.text)
        await _sequence()
        r = await _un_rappel({"suivi_paiement.paiement_actuel": 2, "suivi_paiement.montant_total": 400, "montant_encaisse": 200.01})
        v("rang avancé, total baissé, 1 centime : bloqué", r.status_code == 409 and r.json()["detail"]["type"] == "paiement_ambigu" and len(faux.Emails.appels) == 3, r.text)
        await _sequence()
        r = await _un_rappel({"suivi_paiement.paiement_actuel": 2, "montant_encaisse": 400})
        v("rang avancé ET encaissement : nouveau paiement, nouveau compteur", r.status_code == 200 and len(faux.Emails.appels) == 4, r.text)
        d = await db[rp.COL_RAPPELS].find_one({"_id": rp.cle_envoi("s1", 4)})
        v("il repart au 1er rappel de ce paiement", d["numero"] == 1 and d["paiement_numero"] == 3, d)
        r = await _un_rappel({})
        v("et son compteur tourne normalement", r.status_code == 200 and (await db[rp.COL_RAPPELS].find_one({"_id": rp.cle_envoi("s1", 5)}))["numero"] == 2, r.text)
        print("── DÉCISION 2 : échéancier en 4 fois, chaque part payée")
        await semer(db, flag=True)
        faux.Emails.__init__()
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"montant_encaisse": 100, "suivi_paiement": suivi(montant_total=400, nb_paiements=4, paiement_actuel=1)}})
        for nom, modif in (("2/4", {}), ("3/4", {"suivi_paiement.paiement_actuel": 2, "montant_encaisse": 200}), ("4/4", {"suivi_paiement.paiement_actuel": 3, "montant_encaisse": 300})):
            r = await _un_rappel(modif)
            v(f"rappel pour {nom} : parti, jamais de faux blocage", r.status_code == 200, r.text)
        print("── DÉCISION 2 : le délai de 7 jours et les abonnements remplacés")
        await semer(db, flag=True)
        faux.Emails.__init__()
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]})
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"suivi_paiement.prochaine_echeance": D(1)}})
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        r = await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]})
        v("date changée : les 7 jours restent", r.status_code == 409 and r.json()["detail"]["type"] == "deja_envoye" and len(faux.Emails.appels) == 1, r.text)
        await semer(db, flag=True)
        faux.Emails.__init__()
        for _ in range(3):
            await _un_rappel({})
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"status": "superseded"}})
        await db.subscriptions.insert_one(abo(id="s1-copie"))
        await db[rp.COL_RAPPELS].update_many({"subscription_id": "s1"}, {"$set": {"envoye_le": vieux}})
        r = await cl.get("/api/rappels-paiement/s1-copie/apercu", headers=A)
        v("abonnement recopié, même dette : le compteur suit la personne", r.json()["envoi"]["type"] == "maximum_atteint", r.text)
        await db.subscriptions.update_one({"id": "s1-copie"}, {"$set": {"suivi_paiement.montant_total": 400.01}})
        r = await cl.get("/api/rappels-paiement/s1-copie/apercu", headers=A)
        v("recopié avec 1 centime d'écart : identité incertaine, bloqué", r.json()["envoi"]["type"] == "paiement_ambigu", r.text)
        await db.subscriptions.update_one({"id": "s1-copie"}, {"$set": {"suivi_paiement.montant_total": 800, "montant_encaisse": 400}})
        r = await cl.get("/api/rappels-paiement/s1-copie/apercu", headers=A)
        v("autres montants, ancienne dette non soldée : bloqué", r.json()["envoi"]["type"] == "paiement_ambigu", r.text)
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"suivi_paiement.montant_total": 200}})
        r = await cl.get("/api/rappels-paiement/s1-copie/apercu", headers=A)
        v("baisser le total de l'ancien ne solde pas la dette : bloqué", r.json()["envoi"]["type"] == "paiement_ambigu", r.text)
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"status": "ACTIVE", "montant_encaisse": 400}})
        r = await cl.get("/api/rappels-paiement/s1-copie/apercu", headers=A)
        v("ancien abonnement soldé mais encore actif : bloqué", r.json()["possible"] is False and r.json()["motif"] == "plusieurs_abonnements", r.text)
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"status": "superseded", "montant_encaisse": 400}})
        r = await cl.get("/api/rappels-paiement/s1-copie/apercu", headers=A)
        v("ancien abonnement clos et soldé : paiement distinct", r.json()["envoi"]["peut_envoyer"] is True and r.json()["envoi"]["etape"] == "Rappel", r.text)
        print("── Revue : l'historique suit le code et la plateforme")
        await semer(db, flag=True)
        faux.Emails.__init__()
        faux.Emails.reponse = TimeoutError()
        ap = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        await cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]})
        faux.Emails.reponse = None
        n = len(faux.Emails.appels)
        await db.discount_codes.insert_one({"id": "c-neuf", "code": "CODE-NEUF", "coach_id": ADMIN, "assignedEmail": ""})
        await db.subscriptions.insert_one(abo(id="s-neuf", code="CODE-NEUF", coach_id=ADMIN))
        ap = (await cl.get("/api/rappels-paiement/s-neuf/apercu", headers=A)).json()
        v("nouveau code du super-admin, ancienne fiche sans propriétaire : toujours bloqué", ap["envoi"]["type"] == "incertain_bloque", ap["envoi"])
        await db.subscriptions.update_one({"id": "s1"}, {"$set": {"status": "superseded"}})
        await db.discount_codes.update_one({"id": "c1"}, {"$set": {"assignedEmail": ""}})
        await db.subscriptions.insert_one(abo(id="s-autre-adresse", email="alias@example.test"))
        ap = (await cl.get("/api/rappels-paiement/s-autre-adresse/apercu", headers=A)).json()
        v("même code, nouvelle adresse : toujours bloqué", ap["envoi"]["type"] == "incertain_bloque", ap["envoi"])
        print("── Revue : deux abonnements de la même personne, en même temps")
        await semer(db, flag=True)
        faux.Emails.__init__()
        faux.Emails.delai = 0.2
        await db.discount_codes.insert_one({"id": "c-bis", "code": "CODE-BIS", "coach_id": "", "assignedEmail": ""})
        await db.subscriptions.insert_one(abo(id="s-bis", code="CODE-BIS"))
        a1 = (await cl.get("/api/rappels-paiement/s1/apercu", headers=A)).json()
        a2 = (await cl.get("/api/rappels-paiement/s-bis/apercu", headers=A)).json()
        rs = await asyncio.gather(cl.post("/api/rappels-paiement/s1/envoyer", headers=A, json={"confirmation": True, "empreinte": a1["empreinte"]}),
                                  cl.post("/api/rappels-paiement/s-bis/envoyer", headers=A, json={"confirmation": True, "empreinte": a2["empreinte"]}))
        faux.Emails.delai = 0
        v("au plus un message pour cette personne", len(faux.Emails.appels) <= 1, [x.status_code for x in rs])
        v("aucune ligne ne reste « en cours »", await db[rp.COL_RAPPELS].count_documents({"statut": "en_cours"}) == 0)
        print("── Contre-revue : un envoi tout juste terminé fait renoncer")
        await semer(db, flag=True)
        faux.Emails.__init__()
        _ctx_v = await rp._contexte("s1")
        _pa = rp.paiement_attendu("s1", _ctx_v["sub"])
        _ici = datetime.now(timezone.utc).isoformat()
        await db[rp.COL_RAPPELS].insert_one({"_id": rp.cle_envoi("s-bis-x"), "subscription_id": "s-bis-x", "coach_id": "", "destinataire": "cliente@example.test", "palier": rp.PALIER_MANUEL, "rang": 1, "numero": 1, "statut": "envoye", "envoye_le": _ici, "encaisse_au_rappel": 200, "total_au_rappel": 400, "cree_le": _ici, "maj_le": _ici})
        _mien = {"_id": rp.cle_envoi("s1"), "subscription_id": "s1", "coach_id": "", "destinataire": "cliente@example.test", "palier": rp.PALIER_MANUEL, "rang": 1, "statut": "en_cours", "tentatives": 1, "maj_le": _ici, "cree_le": _ici}
        await db[rp.COL_RAPPELS].insert_one(_mien)
        try:
            await rp._seul_en_cours("s1", _mien, _ctx_v, datetime.now(timezone.utc), {"type": "en_cours", "message": "x"}, 7, _pa)
            _renonce = False
        except Exception as _x:
            _renonce = getattr(_x, "status_code", 0) == 409
        d = await db[rp.COL_RAPPELS].find_one({"_id": rp.cle_envoi("s1")})
        v("renoncement, aucun appel, l'essai reste un échec", _renonce and d["statut"] == "echec" and d["erreur"] == "envoi_concurrent" and len(faux.Emails.appels) == 0, d)
        print("── DÉCISION 2 : droits des partenaires")
        await semer(db, flag=True)
        faux.Emails.__init__()
        for _ in range(3):
            await db[rp.COL_RAPPELS].update_many({"subscription_id": "s-lea", "statut": "envoye"}, {"$set": {"envoye_le": vieux}})
            ap = (await cl.get("/api/rappels-paiement/s-lea/apercu", headers=P)).json()
            await cl.post("/api/rappels-paiement/s-lea/envoyer", headers=P, json={"confirmation": True, "empreinte": ap["empreinte"]})
        await db[rp.COL_RAPPELS].update_many({"subscription_id": "s-lea", "statut": "envoye"}, {"$set": {"envoye_le": vieux}})
        r = await cl.get("/api/rappels-paiement/s-lea/apercu", headers=P)
        v("partenaire : 3 rappels, puis maximum", r.json()["envoi"]["type"] == "maximum_atteint" and len(faux.Emails.appels) == 3, r.text)
        v("un autre coach ne voit ni le client ni le compteur", (await cl.get("/api/rappels-paiement/s-lea/apercu", headers=O)).status_code == 404)
        v("son propre client n'est pas touché", (await cl.get("/api/rappels-paiement/s-tom/apercu", headers=O)).json()["envoi"]["etape"] == "Rappel")
        v("son historique reste vide", (await cl.get("/api/rappels-paiement/historique", headers=O)).json()["historique"] == [])


        print("── V649 : les routes, avec le mode réel")
        await semer(db, flag=True)
        faux.Emails.__init__()
        await db.subscriptions.update_one({"id": "s-offre"}, {"$set": {"origine_paiement": "especes"}})
        ap = (await cl.get("/api/rappels-paiement/s-offre/apercu", headers=A)).json()
        v("offre saison_2x en espèces, sans Stripe : aperçu possible, mode réel", ap["possible"] is True and ap["mode_paiement"] == "Espèces", ap)
        r = await cl.post("/api/rappels-paiement/s-offre/envoyer", headers=A, json={"confirmation": True, "empreinte": ap["empreinte"]})
        v("offre saison_2x en espèces : le rappel suit les règles normales", r.status_code == 200 and len(faux.Emails.appels) == 1, r.text)
        L = {x["code"]: x for x in (await cl.get("/api/rappels-paiement/liste", headers=A)).json()["lignes"]}
        v("liste : TWINT affiché", L["CODE-1"]["mode_paiement"] == "TWINT", L["CODE-1"])
        v("liste : Stripe réel, motif explicite, aucun bouton", L["CODE-STRIPE"]["mode_paiement"] == "Prélèvement automatique Stripe" and L["CODE-STRIPE"]["possible"] is False and "Prélevé automatiquement par Stripe" in L["CODE-STRIPE"]["message"], L["CODE-STRIPE"])
        await db.subscriptions.update_one({"id": "s-case"}, {"$set": {"stripe_subscription_id": "sub_y", "origine_paiement": "twint"}})
        L = {x["code"]: x for x in (await cl.get("/api/rappels-paiement/liste", headers=A)).json()["lignes"]}
        v("liste : données contradictoires, « Paiement à vérifier », jamais Stripe", L["CODE-CASE"]["mode_paiement"] == "Paiement à vérifier" and L["CODE-CASE"]["motif"] == "paiement_a_verifier" and "Stripe" not in L["CODE-CASE"]["message"], L["CODE-CASE"])
        ap = (await cl.get("/api/rappels-paiement/s-case/apercu", headers=A)).json()
        r = await cl.post("/api/rappels-paiement/s-case/envoyer", headers=A, json={"confirmation": True, "empreinte": "x", "montant_confirme": 200})
        v("à vérifier : envoi refusé", r.status_code == 409 and r.json()["detail"]["type"] == "paiement_a_verifier" and len(faux.Emails.appels) == 1, r.text)

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

        await tests_v650(db, cl, faux, A, P)
        await tests_v652(db, cl, faux, A, P)

    await client.drop_database(BASE)
    client.close()


asyncio.run(principal())
print(f"\n{'ÉCHECS : ' + str(len(echecs)) + ' ' + str(echecs) if echecs else 'TOUT EST VERT'}")
sys.exit(1 if echecs else 0)
