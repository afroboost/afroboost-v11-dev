# -*- coding: utf-8 -*-
"""V651 — TEST RÉEL contrôlé des rappels. À lancer seulement après la validation de Bassi.

Une seule adresse reçoit : le serveur compare chaque destinataire à celle rangée par `poser`.
Crée deux abonnements FICTIFS de 2 CHF. Aucun vrai client, aucun paiement réel.

  MONGO_URL=... DB_NAME=... python3 tests/rappel_test_reel.py poser <adresse>  -> refuse l'adresse d'un membre
  MONGO_URL=... DB_NAME=... python3 tests/rappel_test_reel.py test on|off      -> RAPPEL_PAIEMENT_TEST_CONTROLE
  MONGO_URL=... DB_NAME=... python3 tests/rappel_test_reel.py auto on|off      -> RAPPEL_PAIEMENT_AUTO_ACTIF
  MONGO_URL=... DB_NAME=... python3 tests/rappel_test_reel.py bilan            -> les envois de ce test
  MONGO_URL=... DB_NAME=... python3 tests/rappel_test_reel.py nettoyer         -> retire tout, drapeaux éteints
"""
import os
import re
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from pymongo import MongoClient

ORIGINE = "test_reel_v651"
CODES = ("V651-TEST-MANUEL", "V651-TEST-AUTO")
db = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=8000)[os.environ["DB_NAME"]]
_ids = ["v651-" + c.lower() for c in CODES]
action = sys.argv[1] if len(sys.argv) > 1 else ""
if action == "poser":
    _mail = sys.argv[2].strip().lower()
    _re = {"$regex": "^%s$" % re.escape(_mail), "$options": "i"}
    _hors_test = {"_origine": {"$ne": ORIGINE}}
    _membres = sum(db[c].count_documents(dict(q, **_hors_test)) for c, q in (
        ("subscriptions", {"email": _re}), ("discount_codes", {"assignedEmail": _re}), ("reservations", {"userEmail": _re}), ("users", {"email": _re})))
    if _membres:
        sys.exit("ARRET : cette adresse appartient à %d fiche(s) existante(s). Choisir une adresse sans fiche." % _membres)
    _jour = datetime.now(ZoneInfo("Europe/Zurich")).strftime("%Y-%m-%d")
    for _code in CODES:
        db.discount_codes.update_one({"code": _code}, {"$set": {"id": "c-" + _code.lower(), "code": _code, "type": "CHF", "value": 0, "maxUses": 1, "used": 0, "active": True,
                                                                  "assignedEmail": _mail, "coach_id": "", "courses": [], "_origine": ORIGINE}}, upsert=True)
        db.subscriptions.update_one({"code": _code}, {"$set": {
            "id": "v651-" + _code.lower(), "code": _code, "status": "active", "email": _mail, "name": "Test Rappel", "montant_encaisse": 1, "devise": "CHF",
            "origine_paiement": "twint", "total_sessions": 1, "used_sessions": 0, "remaining_sessions": 1, "_origine": ORIGINE,
            "suivi_paiement": {"montant_total": 2, "plusieurs_fois": True, "nb_paiements": 2, "paiement_actuel": 1, "prochaine_echeance": _jour}}}, upsert=True)
    db.rappels_paiement_reglages.update_one({"_id": "_test_adresse"}, {"$set": {"adresse": _mail}}, upsert=True)
    print("posé : 2 fiches fictives, 1 adresse autorisée")
elif action in ("test", "auto"):
    _nom = "RAPPEL_PAIEMENT_TEST_CONTROLE" if action == "test" else "RAPPEL_PAIEMENT_AUTO_ACTIF"
    db.feature_flags.update_one({"id": "feature_flags"}, {"$set": {_nom: sys.argv[2] == "on"}})
elif action == "bilan":
    for _d in db.rappels_paiement.find({"subscription_id": {"$in": _ids}}):
        print(_d.get("code"), _d.get("mode_envoi"), _d.get("rang"), _d.get("statut"), bool(_d.get("resend_id")))
elif action == "nettoyer":
    db.rappels_paiement.delete_many({"subscription_id": {"$in": _ids}})
    db.subscriptions.delete_many({"_origine": ORIGINE})
    db.discount_codes.delete_many({"_origine": ORIGINE})
    db.rappels_paiement_reglages.delete_one({"_id": "_test_adresse"})
    db.feature_flags.update_one({"id": "feature_flags"}, {"$set": {"RAPPEL_PAIEMENT_TEST_CONTROLE": False, "RAPPEL_PAIEMENT_AUTO_ACTIF": False}})
else:
    sys.exit(__doc__)
