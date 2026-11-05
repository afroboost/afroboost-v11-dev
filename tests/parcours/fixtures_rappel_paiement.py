# -*- coding: utf-8 -*-
"""V648 — fixtures FICTIVES du banc « rappel de paiement ». Base de test locale UNIQUEMENT.

  python3 fixtures_rappel_paiement.py poser     -> codes et abonnements @example.test
  python3 fixtures_rappel_paiement.py envoi on|off -> drapeau d'envoi, base de test seulement
  python3 fixtures_rappel_paiement.py vieillir <abonnement> -> 8 jours passent sur ses envois
  python3 fixtures_rappel_paiement.py partenaire <jeton> -> un partenaire connecté, un client
  python3 fixtures_rappel_paiement.py incertain <abonnement> -> un envoi sans réponse depuis 2 jours
  python3 fixtures_rappel_paiement.py compter   -> rappels écrits (JSON)
  python3 fixtures_rappel_paiement.py nettoyer  -> retire tout ce qui précède
"""
import json
import sys
from datetime import datetime, timedelta, timezone

from pymongo import MongoClient

BASE = "afroboost_pw_test"
db = MongoClient("mongodb://127.0.0.1:27017", serverSelectionTimeoutMS=3000)[BASE]
ORIGINE = "fixtures_v648"
PARTENAIRE = "partenaire.v648@example.test"
J = datetime.now(timezone.utc).date()
D = lambda n: (J + timedelta(days=n)).strftime("%Y-%m-%d")  # noqa: E731


def _abo(code, nom, email, **k):
    d = {"id": "v648-" + code.lower(), "code": code, "status": "active", "email": email, "name": nom, "montant_encaisse": 200,
         "devise": "CHF", "origine_paiement": "twint", "total_sessions": 64, "used_sessions": 2, "remaining_sessions": 62,
         "_origine": ORIGINE,
         "suivi_paiement": {"montant_total": 400, "plusieurs_fois": True, "nb_paiements": 2, "paiement_actuel": 1,
                            "prochaine_echeance": D(0)}}
    d.update(k)
    return d


def _code(code, email=""):
    return {"id": "v648-c-" + code.lower(), "code": code, "type": "CHF", "value": 0, "maxUses": 64, "used": 2, "active": True,
            "assignedEmail": email, "coach_id": "", "courses": [], "_origine": ORIGINE}


def nettoyer():
    db.subscriptions.delete_many({"_origine": ORIGINE})
    db.discount_codes.delete_many({"_origine": ORIGINE})
    db.coaches.delete_many({"_origine": ORIGINE})
    db.users_auth.delete_many({"_origine": ORIGINE})
    db.coach_sessions.delete_many({"_origine": ORIGINE})
    db.rappels_paiement.delete_many({})
    db.rappels_paiement_reglages.delete_many({})
    db.resend_envois.delete_many({"type_email": "rappel_paiement"})
    db.feature_flags.update_one({"id": "feature_flags"}, {"$unset": {"RAPPEL_PAIEMENT_ENVOI_REEL": ""}})


def poser():
    nettoyer()
    db.resend_quota.delete_many({})     # le quota simulé de la base de test : le banc se rejoue plusieurs fois par jour
    db.discount_codes.insert_many([_code("V648-NORMAL", "marie.fictive@example.test"), _code("V648-RETARD"), _code("V648-CASE"),
                                   _code("V648-STRIPE"), _code("V648-SANSMAIL")])
    db.subscriptions.insert_many([
        _abo("V648-NORMAL", "Marie Fictive", "marie.fictive@example.test"),
        _abo("V648-RETARD", "Paul Fictif", "paul.fictif@example.test",
             suivi_paiement={"montant_total": 400, "plusieurs_fois": True, "nb_paiements": 2, "paiement_actuel": 1, "prochaine_echeance": D(-2)}),
        _abo("V648-CASE", "Lea Fictive", "lea.fictive@example.test",
             suivi_paiement={"montant_total": 400, "prochaine_echeance": D(3)}),
        _abo("V648-STRIPE", "Sam Fictif", "sam.fictif@example.test", billing_mode="saison_2x", stripe_subscription_id="sub_faux_v648",
             montant_encaisse=199.99),
        _abo("V648-SANSMAIL", "Noa Fictive", ""),
    ])


action = sys.argv[1] if len(sys.argv) > 1 else ""
if action == "poser":
    poser()
elif action == "nettoyer":
    nettoyer()
elif action == "envoi":
    db.feature_flags.update_one({"id": "feature_flags"}, {"$set": {"RAPPEL_PAIEMENT_ENVOI_REEL": sys.argv[2] == "on"}}, upsert=True)
elif action == "partenaire":    # un partenaire fictif, un client fictif
    db.coaches.update_one({"email": PARTENAIRE}, {"$set": {"email": PARTENAIRE, "name": "Banc", "is_active": True, "_origine": ORIGINE}}, upsert=True)
    # Comme un vrai partenaire connecté : un compte et une session (sinon /auth/me le déconnecte).
    db.users_auth.insert_one({"user_id": "v648-partenaire", "email": PARTENAIRE, "name": "Banc", "is_coach": True, "_origine": ORIGINE})
    db.coach_sessions.insert_one({"session_token": sys.argv[2], "user_id": "v648-partenaire", "_origine": ORIGINE,
                                  "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()})
    db.discount_codes.insert_one(dict(_code("V648-PART", ""), coach_id=PARTENAIRE))
    db.subscriptions.insert_one(_abo("V648-PART", "Ana Fictive", "ana.fictive@example.test", coach_id=PARTENAIRE))
elif action == "incertain":     # un envoi resté sans réponse depuis 2 jours
    _h = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    db.rappels_paiement.insert_one({"_id": sys.argv[2] + "|" + D(-2) + "|manuel|1", "subscription_id": sys.argv[2], "palier": "manuel", "echeance": D(-2), "rang": 1,
                                    "statut": "incertain", "destinataire": "paul.fictif@example.test", "montant": 200, "devise": "CHF", "envoye_par": "banc",
                                    "premier_essai_le": _h, "maj_le": _h, "cree_le": _h, "tentatives": 1, "idempotency_key": "banc"})
elif action == "vieillir":      # 8 jours passent sur le dernier envoi de cet abonnement
    _h = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    db.rappels_paiement.update_many({"subscription_id": sys.argv[2], "statut": "envoye"}, {"$set": {"envoye_le": _h, "cree_le": _h}})
elif action == "compter":
    print(json.dumps({"rappels": db.rappels_paiement.count_documents({}),
                      "statuts": [d.get("statut") for d in db.rappels_paiement.find({})],
                      "journal": db.resend_envois.count_documents({"type_email": "rappel_paiement"})}))
else:
    sys.exit(__doc__)
