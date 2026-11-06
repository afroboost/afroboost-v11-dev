# -*- coding: utf-8 -*-
"""V650 — préparation du TEST RÉEL contrôlé des rappels. À lancer seulement après un GO de Bassi.

Crée un abonnement FICTIF dont l'adresse est une plus-adresse du super-admin : avec le mode test,
le serveur refuse tout autre destinataire. Aucun vrai client, aucun paiement réel.

  MONGO_URL=... DB_NAME=... python3 tests/rappel_test_reel.py poser
  MONGO_URL=... DB_NAME=... python3 tests/rappel_test_reel.py test on|off    -> RAPPEL_PAIEMENT_TEST_CONTROLE
  MONGO_URL=... DB_NAME=... python3 tests/rappel_test_reel.py auto on|off    -> RAPPEL_PAIEMENT_AUTO_ACTIF
  MONGO_URL=... DB_NAME=... python3 tests/rappel_test_reel.py bilan          -> les envois de ce test
  MONGO_URL=... DB_NAME=... python3 tests/rappel_test_reel.py nettoyer       -> retire tout, drapeaux compris
"""
import os
import sys
from datetime import datetime, timezone

from pymongo import MongoClient

SUPER_ADMIN = "contact.artboost@gmail.com"
ORIGINE = "test_reel_v650"
_local, _dom = SUPER_ADMIN.split("@")
ADRESSES = {"V650-TEST-MANUEL": "%s+rappel-manuel@%s" % (_local, _dom), "V650-TEST-AUTO": "%s+rappel-auto@%s" % (_local, _dom)}
db = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=8000)[os.environ["DB_NAME"]]
_ids = ["v650-" + c.lower() for c in ADRESSES]
action = sys.argv[1] if len(sys.argv) > 1 else ""
if action == "poser":
    _jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for _code, _mail in ADRESSES.items():
        db.discount_codes.update_one({"code": _code}, {"$set": {"id": "c-" + _code.lower(), "code": _code, "type": "CHF", "value": 0, "maxUses": 1, "used": 0, "active": True,
                                                                  "assignedEmail": _mail, "coach_id": "", "courses": [], "_origine": ORIGINE}}, upsert=True)
        db.subscriptions.update_one({"code": _code}, {"$set": {
            "id": "v650-" + _code.lower(), "code": _code, "status": "active", "email": _mail, "name": "Test Rappel", "montant_encaisse": 1, "devise": "CHF",
            "origine_paiement": "twint", "total_sessions": 1, "used_sessions": 0, "remaining_sessions": 1, "_origine": ORIGINE,
            "suivi_paiement": {"montant_total": 2, "plusieurs_fois": True, "nb_paiements": 2, "paiement_actuel": 1, "prochaine_echeance": _jour}}}, upsert=True)
elif action in ("test", "auto"):
    _nom = "RAPPEL_PAIEMENT_TEST_CONTROLE" if action == "test" else "RAPPEL_PAIEMENT_AUTO_ACTIF"
    db.feature_flags.update_one({"id": "feature_flags"}, {"$set": {_nom: sys.argv[2] == "on"}})
elif action == "bilan":
    for _d in db.rappels_paiement.find({"subscription_id": {"$in": _ids}}):
        print(_d.get("code"), _d.get("mode_envoi"), _d.get("rang"), _d.get("statut"), _d.get("destinataire"), _d.get("resend_id"))
elif action == "nettoyer":
    db.rappels_paiement.delete_many({"subscription_id": {"$in": _ids}})
    db.subscriptions.delete_many({"_origine": ORIGINE})
    db.discount_codes.delete_many({"_origine": ORIGINE})
    db.feature_flags.update_one({"id": "feature_flags"}, {"$set": {"RAPPEL_PAIEMENT_TEST_CONTROLE": False, "RAPPEL_PAIEMENT_AUTO_ACTIF": False}})
else:
    sys.exit(__doc__)
