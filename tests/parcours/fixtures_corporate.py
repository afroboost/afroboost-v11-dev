# -*- coding: utf-8 -*-
"""V657 — fixtures FICTIVES du parcours Corporate. Base de test locale `afroboost_pw_test` UNIQUEMENT.

  python3 fixtures_corporate.py poser     -> événement daté (capacité 45), prospect entreprise, coordonnées vérifiées
  python3 fixtures_corporate.py etat      -> JSON (contrats, inscriptions, retenues)
  python3 fixtures_corporate.py nettoyer  -> retire tout ce qui précède (et ce que le parcours a créé)
"""
import json
import sys

from pymongo import MongoClient

db = MongoClient("mongodb://127.0.0.1:27017", serverSelectionTimeoutMS=3000)["afroboost_pw_test"]
ORIGINE = "fixtures_v657"
EVT, COURS = "v657-evt-corporate", "v657-cours-corporate"
PROSPECT = "v657-prospect-test"


def poser():
    nettoyer()
    db.courses.insert_one({"id": COURS, "name": "AFROBOOST CORPORATE — Neuchâtel (test)", "weekday": None,
                           "date": "2026-12-16", "time": "19:00", "locationName": "Neuchâtel — salle de test",
                           "visible": True, "archived": False, "coach_id": "contact.artboost@gmail.com", "_origine": ORIGINE})
    db.offers.insert_one({"id": EVT, "name": "AFROBOOST CORPORATE — décembre (test)", "price": 30.0, "offer_type": "event",
                          "evenement_reservation_auto": True, "linked_course_ids": [COURS], "visible": True,
                          "stock": -1, "category": "service", "capacite_limitee": True, "capacite_max": 45,
                          "coach_id": "contact.artboost@gmail.com", "_origine": ORIGINE})
    db.partner_prospects.insert_one({"id": PROSPECT, "organisation_name": "Corporate Test SA", "city": "Neuchâtel",
                                     "city_key": "neuchatel", "category": "entreprise", "status": "a_contacter",
                                     "coach_id": "contact.artboost@gmail.com", "dedupe_key": "corporate test sa|neuchatel",
                                     "created_at": "2026-11-09T00:00:00+00:00", "_origine": ORIGINE})
    db.invoice_settings.update_one({"_id": "facturation_corporate"}, {"$set": {
        "nom": "Association Test (fictive)", "adresse": "Rue Fictive 1", "ville": "2000 Neuchâtel", "iban": "CH00 0000 TEST",
        "verifie": True, "verifie_par": "fixtures", "_origine": ORIGINE}}, upsert=True)
    print("ok")


def etat():
    print(json.dumps({
        "contrats": db.corporate_contracts.count_documents({"entreprise.prospect_id": PROSPECT}),
        "inscriptions": db.reservations.count_documents({"offerId": EVT, "corporate_contract_id": {"$exists": True}}),
        "retenues": db.evenement_retenues.count_documents({"offer_id": EVT, "statut": "active"}),
    }))


def nettoyer():
    ids = [c["id"] for c in db.corporate_contracts.find({"entreprise.prospect_id": PROSPECT}, {"id": 1})]
    db.reservations.delete_many({"offerId": EVT})
    db.evenement_places.delete_many({"offer_id": EVT})
    db.evenement_retenues.delete_many({"offer_id": EVT})
    db.evenement_verrous.delete_many({"_id": "evt:" + EVT})
    db.discount_codes.delete_many({"corporate_contract_id": {"$in": ids}})
    db.invoices.delete_many({"corporate_contract_id": {"$in": ids}})
    db.seance_mouvements.delete_many({"source": {"$regex": "^corporate"}})
    db.corporate_contracts.delete_many({"id": {"$in": ids}})
    db.offers.delete_many({"_origine": ORIGINE})
    db.courses.delete_many({"_origine": ORIGINE})
    db.partner_prospects.delete_many({"_origine": ORIGINE})
    db.invoice_settings.delete_many({"_origine": ORIGINE})
    db.referral_campaigns.delete_many({"offer_id": EVT})
    db.invoice_counters.delete_many({})
    db.payment_transactions.delete_many({"$or": [{"metadata.offer_id": EVT}, {"customer_email": "classique.v657@example.test"}]})


if __name__ == "__main__":
    {"poser": poser, "etat": etat, "nettoyer": nettoyer}[sys.argv[1]]()
