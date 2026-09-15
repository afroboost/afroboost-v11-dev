# -*- coding: utf-8 -*-
"""ANALYTICS PHASE 2 — revenus, abonnements, essais & conversion, sur données SYNTHÉTIQUES.

Ce que ces bancs tiennent :
  * UN ACHAT = UNE FOIS : souscription + fiche code + transaction Stripe d'un
    même achat -> une seule ligne, un seul montant ; jamais de somme naïve ;
  * seul le PROUVÉ entre dans le CA ; `pending`, déclaré non prouvé, inconnu,
    transaction à zéro sans jumeau : jamais ;
  * `payment_methods` (['card','twint']) n'est jamais présenté comme le moyen ;
  * classification Pulse / abonnement / carte membre / essai / autre, variantes ;
  * renouvellements CONFIRMÉS (KPI principal) ≠ PROBABLES ≠ INCONNUS ;
  * essais : la règle `essai6_verdict`, la convention du funnel existant
    (cohorte = octroi, pas de fenêtre), présence inconnue ≠ absence ;
  * filtres période / coach / cours, périmètre global explicite ;
  * route : 401 sans jeton, 403 hors périmètre, 7 requêtes fixes.

AUCUNE BASE RÉELLE, AUCUN RÉSEAU.
    python3 tests/test_analytics_finance.py
"""
import asyncio, os, sys, types
from datetime import datetime

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from api.routes import analytics_shared as A

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def run(c):
    return asyncio.get_event_loop().run_until_complete(c)


COACH = "coach@exemple.invalid"
AUTRE = "autre@exemple.invalid"
ADMIN = "admin@exemple.invalid"
MAINTENANT = datetime(2026, 9, 15, 12, 0, 0)
DEBUT, FIN = datetime(2026, 9, 1), datetime(2026, 10, 1)


def sub(code, email, cree, offer_name="PULSE x10 cours", status="active", expires="2027-03-01T23:59:59+00:00",
        coach=COACH, **kw):
    d = {"id": "sub-" + code.lower(), "code": code, "email": email, "name": email.split("@")[0],
         "offer_name": offer_name, "status": status, "created_at": cree + "T10:00:00+00:00",
         "expires_at": expires, "total_sessions": 10, "used_sessions": 0, "remaining_sessions": 10,
         "coach_id": coach, "auto_renew": False, "renewal_warnings_sent": []}
    d.update(kw)
    return d


def fiche(code, email, **kw):
    d = {"code": code, "assignedEmail": email, "type": "sessions", "value": 10, "maxUses": 10, "used": 0,
         "active": True, "id": "dc-" + code.lower()}
    d.update(kw)
    return d


def pt(id_, session, email, cree, amount, amount_total=None, status="paid", coach=COACH, **kw):
    d = {"id": id_, "session_id": session, "customer_email": email, "created_at": cree + "T10:00:00+00:00",
         "amount": amount, "amount_total": amount_total, "quantity": 1, "currency": "chf",
         "product_name": "Cours", "payment_status": status, "coach_id": coach,
         "payment_methods": ["card", "twint"],   # la LISTE proposée au checkout : jamais un moyen réel
         "metadata": {"customer_email": email, "product_name": "Cours"}}
    d.update(kw)
    return d


SUBS = [
    # S1 — déclaration sur la souscription ET la fiche : une fois.
    sub("PULSE-A", "anna@mail.ch", "2026-09-03", montant_encaisse=250, origine_paiement="twint"),
    # S2 — Stripe : fiche `stripe_amount` + `session_id`, transaction jumelle.
    sub("AFR-STRIPE1", "ben@mail.ch", "2026-09-05", "PULSE x10 cours (Membres)", source="stripe_auto", renewal_price=150),
    # S3 — déclaration TWINT + session Stripe + transaction : une fois (cas Aurélie).
    sub("AFR-DOUBLE", "cat@mail.ch", "2026-09-06", montant_encaisse=150, origine_paiement="twint"),
    # S7/S8/S9 — essais (origine offert, 0), l'un converti par achat, l'autre par `converted_at`.
    sub("AFR-FREE1", "eve@mail.ch", "2026-09-02", "🎁 Cours d'essai GRATUIT ", expires="2026-10-01T23:59:59+00:00",
        montant_encaisse=0, origine_paiement="offert", source="checkout_vitrine", coach=""),
    sub("AFR-FREE2", "fay@mail.ch", "2026-09-04", "🎁 Cours d'essai GRATUIT ", expires="2026-10-01T23:59:59+00:00",
        montant_encaisse=0, origine_paiement="offert", converted_at="2026-09-12T10:00:00+00:00", coach=""),
    sub("AFR-FREE3", "gus@mail.ch", "2026-09-06", "🎁 Cours d'essai GRATUIT ", expires="2026-10-01T23:59:59+00:00",
        montant_encaisse=0, origine_paiement="offert", coach=""),
    sub("PULSE-EVE", "eve@mail.ch", "2026-09-10", montant_encaisse=250, origine_paiement="especes"),
    # S10 — ancien Pulse épuisé puis nouveau Pulse : renouvellement PROBABLE.
    sub("OLD-PULSE", "hal@mail.ch", "2026-03-01", status="completed", expires="2026-09-10T23:59:59+00:00",
        used_sessions=10, remaining_sessions=0, montant_encaisse=250, origine_paiement="twint"),
    sub("NEW-PULSE", "hal@mail.ch", "2026-09-08", montant_encaisse=250, origine_paiement="twint"),
    # S11 — renouvellement CONFIRMÉ (V195), achat hors période.
    sub("RENEW-OK", "ivy@mail.ch", "2026-08-01", montant_encaisse=250, origine_paiement="virement",
        last_renewal_date="2026-09-07T08:00:00+00:00", renewal_price=250),
    # S12 — abonnement sans aucun montant : inconnu ; expire bientôt et dans la période.
    sub("ABO-1", "jon@mail.ch", "2026-09-09", "Abonnement", expires="2026-09-25T23:59:59+00:00"),
    # S13 — tarif à la création, non prouvé : partiel.
    sub("DECL-1", "kim@mail.ch", "2026-09-11", offer_price=250),
    # S14 — remplacée : écartée.
    sub("SUPER-1", "lou@mail.ch", "2026-09-11", status="superseded", montant_encaisse=250, origine_paiement="twint"),
    # S15 — autre coach.
    sub("AUTRE-COACH", "zed@mail.ch", "2026-09-12", montant_encaisse=100, origine_paiement="twint", coach=AUTRE),
    # S17 — fiche avec `session_id` mais sans `stripe_amount`, souscription à `renewal_price` (non prouvé) :
    #       la transaction jumelle (`amount_total`) prouve le montant — une fois.
    sub("AFR-TX", "ted@mail.ch", "2026-09-14", "Cours à l'unité", source="stripe_auto", renewal_price=2),
    # S16 — deux fiches vivantes du même code, même déclaration : une fois, renouvellement INCONNU.
    sub("MULTI-1", "mia@mail.ch", "2026-09-13", montant_encaisse=250, origine_paiement="twint"),
    dict(sub("MULTI-1", "mia@mail.ch", "2026-09-13", montant_encaisse=250, origine_paiement="twint"), id="sub-multi-1b"),
]
FICHES = [
    fiche("PULSE-A", "anna@mail.ch", montant_encaisse=250, origine_paiement="twint", stripe_amount=250),
    fiche("AFR-STRIPE1", "ben@mail.ch", stripe_amount=150, session_id="cs_1"),
    fiche("AFR-DOUBLE", "cat@mail.ch", montant_encaisse=150, origine_paiement="twint", stripe_amount=150, session_id="cs_2"),
    fiche("AFR-FREE1", "eve@mail.ch", payment_method="free", total_paid=0, transaction_id="free_1"),
    fiche("AFR-FREE2", "fay@mail.ch", payment_method="free", total_paid=0, transaction_id="free_2"),
    fiche("AFR-FREE3", "gus@mail.ch", payment_method="free", total_paid=0, transaction_id="free_3"),
    fiche("PULSE-EVE", "eve@mail.ch"),
    fiche("OLD-PULSE", "hal@mail.ch"), fiche("NEW-PULSE", "hal@mail.ch"), fiche("RENEW-OK", "ivy@mail.ch"),
    fiche("ABO-1", "jon@mail.ch"), fiche("DECL-1", "kim@mail.ch"), fiche("MULTI-1", "mia@mail.ch"),
    fiche("AFR-TX", "ted@mail.ch", session_id="cs_tx", maxUses=1),
    # deux fiches pour PULSE-A : la canonique doit gagner (déclaration identique)
    fiche("PULSE-A", "anna@mail.ch", canonical=True, montant_encaisse=250, origine_paiement="twint"),
    # code seul, sans souscription : une déclaration = un achat (cas CLUBPMI)
    fiche("CLUB-X", "club@mail.ch", montant_encaisse=760, origine_paiement="virement", created_at="2026-09-14T10:00:00+00:00", coach_id=COACH),
]
PAIEMENTS = [
    pt("p1", "cs_1", "ben@mail.ch", "2026-09-05", 150.0, 15000),        # jumeau de AFR-STRIPE1
    pt("p2", "cs_2", "cat@mail.ch", "2026-09-06", 150.0, 15000),        # jumeau de AFR-DOUBLE
    pt("p3", "cs_3", "dan@mail.ch", "2026-09-07", 30.0, 3000),          # achat direct prouvé
    pt("p4", "cs_4", "dan@mail.ch", "2026-09-07", 25.0, None),          # achat direct NON prouvé
    pt("p5", "cs_5", "eli@mail.ch", "2026-09-08", 250.0, None, status="pending"),   # en attente
    pt("p6", "free_1", "eve@mail.ch", "2026-09-02", 0, None, payment_method="free"),  # jumeau (transaction_id) de l'essai
    pt("p7", "free_9", "nod@mail.ch", "2026-09-03", 0, None, payment_method="free"),  # zéro sans jumeau : pas un achat
    pt("p8", "cs_8", "old@mail.ch", "2026-08-20", 40.0, 4000),          # hors période
    pt("p9", "cs_9", "x@mail.ch", "2026-09-09", 10.0, 1000, status="failed"),  # jamais
    pt("p10", "cs_tx", "ted@mail.ch", "2026-09-14", 2.0, 200),           # jumeau prouvant AFR-TX
]
OFFRES = {"o-pulse": {"id": "o-pulse", "name": "PULSE x10 cours", "price": 250.0, "pack_sessions": 10},
          "o-essai": {"id": "o-essai", "name": "🎁 Cours d'essai GRATUIT ", "price": 0.0, "pack_sessions": 1}}
CARTES = [
    {"email": "hal@mail.ch", "date_debut": "2026-09-08", "date_fin": "2027-09-07", "source": "achat", "coach_id": COACH},
    {"email": "ivy@mail.ch", "date_debut": "2026-03-25", "date_fin": "2027-03-24", "source": "regularisation_historique_manuelle", "coach_id": COACH},
    {"email": "eve@mail.ch", "date_debut": "2026-09-10", "date_fin": "2027-09-09", "source": "achat", "coach_id": COACH},
    {"email": "vieux@mail.ch", "date_debut": "2025-09-01", "date_fin": "2026-09-05", "source": "achat", "coach_id": COACH},
]


def resa(id_, email, occ, cree, course_id="c-mer", course_name="Silent", **kw):
    d = {"id": id_, "userEmail": email, "userName": email.split("@")[0], "courseId": course_id, "courseName": course_name,
         "datetime": occ, "createdAt": cree, "coach_id": COACH, "validated": False, "isProduct": False, "price": 0}
    d.update(kw)
    return d


RESAS = [
    resa("r1", "eve@mail.ch", "2026-09-09T18:30:00", "2026-09-02T12:00:00+00:00", discountCode="AFR-FREE1", validated=True),
    resa("r2", "gus@mail.ch", "2026-09-09T18:30:00", "2026-09-06T12:00:00+00:00", subscriptionId="sub-afr-free3"),
    resa("r3", "anna@mail.ch", "2026-09-09T18:30:00", "2026-09-03T12:00:00+00:00", discountCode="PULSE-A", tarif_applique=25.0),
    resa("r4", "anna@mail.ch", "2026-09-13T18:30:00", "2026-09-03T12:00:00+00:00", "c-dim", "Sunday", discountCode="PULSE-A", tarif_applique=25.0),
    resa("r5", "ben@mail.ch", "2026-09-13T18:30:00", "2026-09-05T12:00:00+00:00", "c-dim", "Sunday", discountCode="AFR-STRIPE1"),
]
COURS = {"c-mer": {"id": "c-mer", "name": "Silent", "weekday": 3}, "c-dim": {"id": "c-dim", "name": "Sunday", "weekday": 0}}


def _table():
    fiches_par_code = {}
    for f in FICHES:
        fiches_par_code.setdefault(f["code"].upper(), []).append(f)
    codes_par_code = {k: A.choisir_fiche_code(v) for k, v in fiches_par_code.items()}
    subs_par_id = {s["id"]: s for s in SUBS}
    subs_par_code = {}
    for s in SUBS:
        subs_par_code.setdefault(s["code"].upper(), s)
    return A.construire_faits(RESAS, COURS, subs_par_id, subs_par_code, codes_par_code, OFFRES, {})["faits"]


FAITS = _table()
ACHATS = A.construire_achats(SUBS, FICHES, PAIEMENTS, OFFRES, MAINTENANT)
KPI = A.calculer_kpi_finance(ACHATS["achats"], ACHATS["en_attente"], CARTES, FAITS, DEBUT, FIN, "jour", MAINTENANT)
par_cle = {a["cle"]: a for a in ACHATS["achats"]}
R, AB, ES = KPI["revenus"], KPI["abonnements"], KPI["essais_funnel"]

# ═══ 1. un achat = une fois ═══
verifier("les fiches d'un même code (canonique + doublon) donnent UNE ligne", "droit:PULSE-A" in par_cle and sum(1 for a in ACHATS["achats"] if a["code"] == "PULSE-A") == 1)
verifier("PULSE-A : 250 CHF, twint, prouvé — pas 250 + 250 (souscription + fiche)", par_cle["droit:PULSE-A"]["montant"] == 250 and par_cle["droit:PULSE-A"]["moyen"] == "twint" and par_cle["droit:PULSE-A"]["qualite"] == "fiable")
verifier("choisir_fiche_code : la fiche `canonical` gagne", A.choisir_fiche_code(FICHES)["code"] == "PULSE-A" and A.choisir_fiche_code([f for f in FICHES if f["code"] == "PULSE-A"]).get("canonical") is True)
verifier("Stripe : la transaction jumelle (session_id) est retirée, le droit porte l'achat", "paiement:p1" not in par_cle and par_cle["droit:AFR-STRIPE1"]["montant"] == 150 and par_cle["droit:AFR-STRIPE1"]["qualite"] == "fiable")
verifier("Stripe + déclaration TWINT du même achat : UNE ligne à 150, moyen twint, canal stripe", "paiement:p2" not in par_cle and par_cle["droit:AFR-DOUBLE"]["montant"] == 150 and par_cle["droit:AFR-DOUBLE"]["moyen"] == "twint" and par_cle["droit:AFR-DOUBLE"]["canal"] == "stripe")
verifier("transaction à 0 jumelle par transaction_id : retirée", "paiement:p6" not in par_cle and ACHATS["ecartes"]["paiements_jumeaux"] == 4)
verifier("fiche session_id sans stripe_amount + renewal_price : la transaction jumelle PROUVE 2 CHF, une seule ligne",
         "paiement:p10" not in par_cle and par_cle["droit:AFR-TX"]["montant"] == 2 and par_cle["droit:AFR-TX"]["qualite"] == "fiable"
         and par_cle["droit:AFR-TX"]["montant_source"] == "transaction" and par_cle["droit:AFR-TX"]["moyen"] == "stripe_indetermine")
verifier("transaction à 0 sans jumeau : pas un achat", "paiement:p7" not in par_cle and ACHATS["ecartes"]["paiements_zero_sans_jumeau"] == 1)
verifier("souscription `superseded` écartée", "droit:SUPER-1" not in par_cle and ACHATS["ecartes"]["souscriptions_superseded"] == 1)
verifier("transaction `failed` : jamais", "paiement:p9" not in par_cle and ACHATS["ecartes"]["paiements_non_payes"] == 1)
verifier("achat direct prouvé (amount_total) : ligne à 30, fiable", par_cle["paiement:p3"]["montant"] == 30 and par_cle["paiement:p3"]["qualite"] == "fiable")
verifier("achat direct sans amount_total : partiel, jamais dans le CA", par_cle["paiement:p4"]["qualite"] == "partiel")
verifier("code seul avec déclaration (CLUB-X 760 virement) : un achat, fiable", par_cle["droit:CLUB-X"]["montant"] == 760 and par_cle["droit:CLUB-X"]["qualite"] == "fiable" and par_cle["droit:CLUB-X"]["moyen"] == "virement")
verifier("deux fiches vivantes MULTI-1 : une ligne, 250 (pas 500)", par_cle["droit:MULTI-1"]["montant"] == 250 and par_cle["droit:MULTI-1"]["fiches"] == 2)
verifier("droit sans montant : inconnu ; tarif à la création : partiel", par_cle["droit:ABO-1"]["qualite"] == "inconnu" and par_cle["droit:DECL-1"]["qualite"] == "partiel")

# ═══ 2. revenus ═══
# fiables payants dans la période : PULSE-A 250, AFR-STRIPE1 150, AFR-DOUBLE 150, p3 30, PULSE-EVE 250,
# NEW-PULSE 250, AUTRE-COACH 100, MULTI-1 250, CLUB-X 760, AFR-TX 2  -> 2192 ; 10 achats ; 10 acheteurs
verifier("CA encaissé période = somme des PROUVÉS seulement (2192)", R["ca_encaisse"] == 2192, R["ca_encaisse"])
verifier("transactions payées = 10, panier moyen 219.2", R["transactions_payees"] == 10 and R["panier_moyen"] == 219.2, (R["transactions_payees"], R["panier_moyen"]))
verifier("acheteurs uniques 10, revenu par participant 219.2", R["acheteurs_uniques"] == 10 and R["revenu_par_participant"] == 219.2)
verifier("CA Stripe 332 (150 + 150 + 30 + 2) / CA manuel 1860", R["ca_stripe"] == 332 and R["ca_manuel"] == 1860, (R["ca_stripe"], R["ca_manuel"]))
verifier("gratuits/offerts : 3 essais à 0 prouvés", R["gratuits"] == 3, R["gratuits"])
verifier("déclaré non prouvé à part : 2 (25 + 250)", R["declare_non_prouve"] == {"nombre": 2, "montant": 275}, R["declare_non_prouve"])
verifier("montant inconnu : 1 (ABO-1)", R["montant_inconnu"] == 1)
verifier("pending : compté à part (1, 250), jamais dans le CA", R["en_attente"] == {"nombre": 1, "montant_declare": 250})
verifier("hors période (p8, RENEW-OK) : pas dans le CA", "paiement:p8" in par_cle and R["ca_encaisse"] == 2192)
verifier("par moyen : twint 5/1000, especes 1/250, virement 1/760, Stripe non déterminé 3/182, offert 3/0",
         R["par_moyen"]["twint"] == {"nombre": 5, "montant": 1000} and R["par_moyen"]["especes"]["montant"] == 250
         and R["par_moyen"]["virement"]["montant"] == 760 and R["par_moyen"]["stripe_indetermine"] == {"nombre": 3, "montant": 182}
         and R["par_moyen"]["offert"] == {"nombre": 3, "montant": 0}, R["par_moyen"])
verifier("['card','twint'] n'apparaît JAMAIS comme moyen (Stripe reste « non déterminé » malgré payment_methods)",
         "card" not in R["par_moyen"] and all(a["moyen"] in A.MOYENS and a["moyen"] != "stripe_card" for a in ACHATS["achats"])
         and par_cle["paiement:p3"]["moyen"] == "stripe_indetermine")
verifier("qualité moyen : partiel (Stripe non déterminé présent)", R["qualite"]["moyen_paiement"] == "partiel" and R["qualite"]["stripe_moyen_indetermine"] == 3)
verifier("qualité montants : partiel (fiables + partiels + inconnus)", R["qualite"]["montants"] == "partiel" and R["qualite"]["fiables"] == 13)
verifier("remboursements : libellé explicite, jamais déduits", R["remboursements"] == "Remboursements non disponibles historiquement")
verifier("évolution du CA : par jour, sommes prouvées", any(e["periode"] == "2026-09-14" and e["ca"] == 762 and e["achats"] == 2 for e in R["evolution"]) and sum(e["ca"] for e in R["evolution"]) == 2192)
vc = R["valeur_par_cours"]
# Sunday : r4 tarif figé 25 + r5 valeur par séance d'un encaissement PROUVÉ (150 / 10 = 15) ; Silent : r3 seul (25), r1/r2 inconnues.
verifier("valeur par cours (faits, tarif figé ou encaissement prouvé) : Sunday 40 (2/2), Silent 25 (1/3), total 65, jamais dans le CA",
         [(c["name"], c["valeur"], c["valeurs_connues"], c["reservations"]) for c in vc["cours"]] == [("Sunday", 40, 2, 2), ("Silent", 25, 1, 3)]
         and vc["valeur_totale"] == 65 and vc["couverture_pct"] == 60.0 and R["ca_encaisse"] == 2192, vc)
verifier("périmètre des revenus dit « global » ; valeur par cours dit « tous les cours »", "global" in R["perimetre"] and vc["perimetre"].startswith("tous les cours"))
K2 = A.calculer_kpi_finance(ACHATS["achats"], ACHATS["en_attente"], CARTES, [f for f in FAITS if f["course_id"] == "c-dim"], DEBUT, FIN, "jour", MAINTENANT, cours_filtre="c-dim")
verifier("filtre cours : la valeur par cours suit (Sunday seul), le CA reste global et identique", [c["name"] for c in K2["revenus"]["valeur_par_cours"]["cours"]] == ["Sunday"] and K2["revenus"]["ca_encaisse"] == 2192 and K2["revenus"]["valeur_par_cours"]["perimetre"].startswith("filtré par cours"))
K3 = A.calculer_kpi_finance(ACHATS["achats"], ACHATS["en_attente"], CARTES, FAITS, datetime(2026, 8, 1), datetime(2026, 9, 1), "jour", MAINTENANT)
verifier("filtre période (août) : CA = p8 40 + RENEW-OK 250 = 290", K3["revenus"]["ca_encaisse"] == 290, K3["revenus"]["ca_encaisse"])
K4 = A.calculer_kpi_finance([a for a in ACHATS["achats"] if a["coach_id"] == COACH], ACHATS["en_attente"], CARTES, FAITS, DEBUT, FIN, "jour", MAINTENANT)
verifier("filtre coach (en amont) : sans AUTRE-COACH ni les essais sans coach : 2092", K4["revenus"]["ca_encaisse"] == 2092, K4["revenus"]["ca_encaisse"])

# ═══ 3. abonnements ═══
verifier("classification : variantes Pulse (x10, Membres), Abonnement, essai prime, autre",
         A.categorie_droit("PULSE x10 cours") == "pulse_x10" and A.categorie_droit("PULSE x10 cours (Membres)") == "pulse_x10"
         and A.categorie_droit("Membres") == "pulse_x10" and A.categorie_droit("Abonnement") == "abonnement"
         and A.categorie_droit("PULSE x10 cours", essai=True) == "essai" and A.categorie_droit("Cours à l'unité") == "autre"
         and A.categorie_droit("bass", {"pack_sessions": 10}) == "pulse_x10")
verifier("essais classés `essai` par essai6_verdict (P2 offert)", all(par_cle["droit:" + c]["categorie"] == "essai" for c in ("AFR-FREE1", "AFR-FREE2", "AFR-FREE3")))
act = AB["actifs"]
# actifs au 15/09 : PULSE-A, AFR-STRIPE1, AFR-DOUBLE, 3 essais, PULSE-EVE, NEW-PULSE, RENEW-OK, ABO-1, DECL-1, AUTRE-COACH, MULTI-1, AFR-TX, CLUB-X (code seul actif sans expiration) = 15
verifier("actifs aujourd'hui : 15, dont 9 Pulse, 1 abonnement, 3 essais, 2 autres", act["total"] == 15 and act["par_categorie"]["pulse_x10"] == 9 and act["par_categorie"]["abonnement"] == 1 and act["par_categorie"]["essai"] == 3 and act["par_categorie"]["autre"] == 2, act)
verifier("OLD-PULSE (completed) n'est pas actif", not par_cle["droit:OLD-PULSE"]["actif"])
verifier("nouveaux dans la période : 14 droits (tout sauf OLD-PULSE, RENEW-OK et la remplacée)", AB["nouveaux"]["total"] == 14 and AB["nouveaux"]["par_categorie"]["essai"] == 3, AB["nouveaux"])
verifier("Pulse vendus sur la période : 8 ; Pulse actifs : 9 (RENEW-OK acheté en août)", AB["pulse_x10"] == {"actifs": 9, "vendus": 8}, AB["pulse_x10"])
verifier("expirés pendant la période : OLD-PULSE (10/09) seul — ABO-1 (25/09) n'a PAS encore expiré au 15/09", AB["expires"]["total"] == 1 and AB["expires"]["par_categorie"]["pulse_x10"] == 1, AB["expires"])
verifier("expirant sous 30 j : ABO-1 + 3 essais (01/10) = 4", AB["expirant_bientot"] == {"jours": 30, "total": 4}, AB["expirant_bientot"])
cm = AB["cartes_membres"]
verifier("cartes membres : 3 actives, 2 vendues sur la période, 0 régularisée (hors période), 1 expirée, 4 au total",
         cm == {"actives": 3, "vendues": 2, "regularisees": 0, "expirees": 1, "total": 4}, cm)
rn = AB["renouvellements"]
verifier("renouvellement CONFIRMÉ (last_renewal_date en septembre) : 1 — le KPI principal", rn["confirmes"] == 1 and rn["kpi_principal"] == "confirmes")
verifier("renouvellement PROBABLE à part : NEW-PULSE après OLD-PULSE épuisé (et pas PULSE-EVE, l'essai n'est pas un Pulse)", rn["probables"] == 1, rn)
verifier("renouvellement INCONNU : MULTI-1 (deux fiches vivantes, même jour)", rn["inconnus"] == 1, rn)
verifier("qualité renouvellements : partiel", AB["qualite"]["renouvellements"] == "partiel")
verifier("probables : libellé « non comptés dans le KPI principal » + avertissement comptes/codes de test, aucun filtrage par nom",
         rn["libelle_probables"] == "Renouvellements probables — non comptés dans le KPI principal"
         and "codes de test" in rn["avertissement"] and "codes de test" in AB["qualite"]["note"]
         and "droit:MULTI-1" in par_cle and "droit:AUTRE-COACH" in par_cle)
verifier("évolution abonnements : nouveaux par jour", sum(e["nouveaux"] for e in AB["evolution"]) == 14 and sum(e["expires"] for e in AB["evolution"]) == 1)
verifier("périmètre abonnements : global, jamais filtré par cours", "global" in AB["perimetre"] and K2["abonnements"]["actifs"]["total"] == 15)

# ═══ 4. essais & conversion ═══
verifier("convention : ancre = octroi, AUCUNE fenêtre, confirmée = converted_at", ES["convention"]["fenetre"].startswith("aucune") and "converted_at" in ES["convention"]["confirmee"])
verifier("accordés 3, réservés 2 (FREE1 par code, FREE3 par subscriptionId)", ES["accordes"] == 3 and ES["reserves"] == 2, ES)
verifier("présence : 1 confirmée, 0 absente, 1 inconnue — l'inconnue n'est pas une absence, couverture 50 %",
         ES["presence"] == {"confirmee": 1, "absente": 0, "inconnue": 1, "couverture_pct": 50.0}, ES["presence"])
verifier("convertis CONFIRMÉS (converted_at) : 1 (FREE2)", ES["convertis_confirmes"] == 1)
verifier("convertis PROBABLES : 1 (eve -> Pulse ET carte membre), à part", ES["convertis_probables"]["total"] == 1 and ES["convertis_probables"]["pulse_x10"] == 1 and ES["convertis_probables"]["carte_membre"] == 1 and ES["convertis_probables"]["abonnement"] == 0, ES["convertis_probables"])
verifier("délai médian essai -> achat : 8 jours", ES["delai_conversion_probable_median_jours"] == 8)
verifier("taux : réservation 66.7, présence 50, conversion confirmée 33.3, probable 33.3", ES["taux"] == {"reservation": 66.7, "presence": 50.0, "conversion_confirmee": 33.3, "conversion_probable": 33.3}, ES["taux"])
K5 = A.calculer_kpi_finance(ACHATS["achats"], ACHATS["en_attente"], CARTES, FAITS, datetime(2026, 9, 3), datetime(2026, 9, 5), "jour", MAINTENANT)
verifier("cohorte = essais ACCORDÉS dans la période (3–4 sept : FREE2 seul), suivi sans fenêtre", K5["essais_funnel"]["accordes"] == 1 and K5["essais_funnel"]["convertis_confirmes"] == 1)
verifier("qualité essais : conversion partiel (un achat sans marqueur), présence partiel", ES["qualite"]["conversion"] == "partiel" and ES["qualite"]["probables_sans_marqueur"] == 1 and ES["qualite"]["presence"] == "partiel", ES["qualite"])

# ═══ 5. moyen de paiement ═══
verifier("moyen : Stripe sans moyen unitaire -> stripe_indetermine, partiel",
         A.moyen_de_paiement({"montant": 10, "montant_prouve": True, "montant_source": "stripe", "origine_paiement": "stripe"}, {"session_id": "x", "payment_methods": ["card", "twint"]}) == ("stripe_indetermine", "stripe", "partiel"))
verifier("moyen : Stripe avec `payment_method` unitaire = twint -> stripe_twint, fiable",
         A.moyen_de_paiement({"montant": 10, "montant_prouve": True, "montant_source": "stripe", "origine_paiement": "stripe"}, {"payment_method": "twint"}) == ("stripe_twint", "stripe", "fiable"))
verifier("moyen : gratuit prouvé -> offert", A.moyen_de_paiement({"montant": 0, "montant_prouve": True, "gratuit": True, "origine_paiement": "offert"}) == ("offert", "offert", "fiable"))
verifier("moyen : aucun montant -> inconnu", A.moyen_de_paiement({"montant": None}) == ("inconnu", "inconnu", "inconnu"))
verifier("qualité globale des achats : 1 multi-fiches, 0 sans date, 3 sans coach", ACHATS["qualite"]["droits_multi_fiches"] == 1 and ACHATS["qualite"]["sans_date"] == 0 and ACHATS["qualite"]["sans_coach"] == 3, ACHATS["qualite"])

# ═══ 6. la route : auth, isolation, requêtes fixes ═══
class _Cur:
    def __init__(self, docs): self.d = docs
    async def to_list(self, n): return [dict(x) for x in self.d]


def _match(doc, f):
    for k, v in f.items():
        if k == "$or":
            if not any(_match(doc, alt) for alt in v): return False
        elif isinstance(v, dict) and "$ne" in v:
            if doc.get(k) == v["$ne"]: return False
        elif isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]: return False
        elif doc.get(k) != v:
            return False
    return True


class _Coll2:
    def __init__(self, docs, base): self.docs, self.base = docs, base
    def find(self, f, p=None):
        self.base.requetes += 1
        self.base.ecritures += 0
        return _Cur([d for d in self.docs if _match(d, f)])
    def __getattr__(self, name):
        if name in ("update_one", "insert_one", "delete_one", "update_many", "find_one_and_update", "replace_one"):
            raise AssertionError("ÉCRITURE INTERDITE : " + name)
        raise AttributeError(name)


class _Base:
    def __init__(self):
        self.requetes = 0
        self.ecritures = 0
        self.reservations = _Coll2(RESAS, self)
        self.courses = _Coll2(list(COURS.values()), self)
        self.subscriptions = _Coll2(SUBS, self)
        self.discount_codes = _Coll2(FICHES, self)
        self.offers = _Coll2(list(OFFRES.values()), self)
        self.memberships = _Coll2(CARTES, self)
        self.payment_transactions = _Coll2(PAIEMENTS, self)


def _serveur(base, jwt_email):
    m = types.ModuleType("api.server")
    m.db = base
    m._v311_coach_email_from_jwt = lambda request: jwt_email
    async def _est_coach(email): return email in (COACH, AUTRE, ADMIN)
    m._v309_is_coach_or_admin = _est_coach
    sys.modules["api.server"] = m
    rr = types.ModuleType("api.routes.reservation_routes")
    rr.lot1_occurrence_iso = lambda v: (A.parser_local(v).strftime("%Y-%m-%dT%H:%M:%S") if A.parser_local(v) else "")
    sys.modules["api.routes.reservation_routes"] = rr


import api.routes.shared as _shared
_shared.is_super_admin = lambda e: (e or "").lower() == ADMIN

try:
    import fastapi  # noqa: F401
    from api.routes.analytics_routes import analytics_cockpit
    from fastapi import HTTPException

    class _Req:
        headers = {}

    def _appel(jwt, **params):
        base = _Base()
        _serveur(base, jwt)
        try:
            r = run(analytics_cockpit(_Req(), **params))
            return 200, r, base.requetes
        except HTTPException as e:
            return e.status_code, None, base.requetes

    s, _, _ = _appel("", periode="mois")
    verifier("route : sans jeton -> 401", s == 401, s)
    s, _, _ = _appel(COACH, periode="mois", coach_id=AUTRE)
    verifier("route : coach demandant un autre coach -> 403", s == 403, s)
    s, r, n = _appel(ADMIN, periode="perso", du="2026-09-01", au="2026-09-30")
    verifier("route admin : 200, 7 requêtes exactement, sections phase 2 présentes", s == 200 and n == 7 and all(k in r for k in ("revenus", "abonnements", "essais_funnel", "achats")), (s, n))
    verifier("route admin : CA 2192 (tout)", s == 200 and r["revenus"]["ca_encaisse"] == 2192, r and r["revenus"]["ca_encaisse"])
    s, r, n = _appel(COACH, periode="perso", du="2026-09-01", au="2026-09-30")
    verifier("route coach : 200, 7 requêtes, CA du coach seul 2092 (ni l'autre coach ni les essais sans coach)",
             s == 200 and n == 7 and r["revenus"]["ca_encaisse"] == 2092, (s, n, r and r["revenus"]["ca_encaisse"]))
    verifier("route coach : les essais sans coach_id ne sont pas dans sa cohorte", r["essais_funnel"]["accordes"] == 0)
    s, r, _ = _appel(ADMIN, periode="perso", du="2026-09-01", au="2026-09-30", coach_id=AUTRE)
    verifier("route admin sur l'autre coach : CA 100", s == 200 and r["revenus"]["ca_encaisse"] == 100)
    s, r, _ = _appel(ADMIN, periode="perso", du="2026-09-01", au="2026-09-30", course_id="c-dim")
    verifier("route + filtre cours : CA global inchangé (2192), valeur par cours = Sunday seul, périmètre dit « filtré par cours »",
             r["revenus"]["ca_encaisse"] == 2192 and [c["name"] for c in r["revenus"]["valeur_par_cours"]["cours"]] == ["Sunday"]
             and r["revenus"]["valeur_par_cours"]["perimetre"].startswith("filtré par cours"))
    verifier("route : l'essai de la phase 1 et la cohorte de la phase 2 utilisent la même règle (3 essais)", r["essais_funnel"]["accordes"] == 3)
    verifier("route : DB en lecture seule (aucune méthode d'écriture appelée)", True)
except ImportError:
    verifier("fastapi absent : la route n'a pas pu être exercée", False, "installer fastapi")

ok = sum(1 for _, c, _ in RESULTATS if c)
for nom, cond, detail in RESULTATS:
    print("  %s  %s%s" % ("OK  " if cond else "ECHEC", nom, ("  <- " + str(detail)) if (detail and not cond) else ""))
print("\n%d/%d" % (ok, len(RESULTATS)))
sys.exit(0 if ok == len(RESULTATS) else 1)
