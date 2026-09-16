# E1 (16/09/2026) — FIXTURES de la pile LOCALE, base de test `afroboost_pw_test` UNIQUEMENT.
# Sert aux parcours Playwright (deadline dépassée simulée, 50/50 simulé, abonné actif).
# Refuse de toucher toute autre base. Usage :
#   python3 pw_fixtures.py deadline-passee | deadline-restaurer | stock-plein | stock-restaurer | abonne-actif <email> | nettoyer-abonnes
import os, sys, uuid
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient
RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
env = {}
for l in open(os.path.join(RACINE, ".env.local")):
    l = l.strip()
    if "=" in l and not l.startswith("#"):
        k, v = l.split("=", 1); env[k] = v.strip().strip('"').strip("'")
BASE_TEST = "afroboost_pw_test"
db = MongoClient(env["MONGO_URL"], serverSelectionTimeoutMS=20000)[BASE_TEST]
assert db.name == BASE_TEST
FID = "cc73f6ee-163a-433d-b5f0-c00c6392b437"   # Fondateurs (même id que la prod, copié par semer_base_test)
MARQUE = "pw_fixture_e1"

def abonnement_fictif(email, i=0):
    now = datetime.now(timezone.utc)
    return {"id": str(uuid.uuid4()), "user_email": email, "email": email, "offer_id": FID, "offer_name": "Fondateurs",
            "status": "active", "billing_mode": "mensuel_auto", "stripe_subscription_id": "sub_faux_fixture_%03d" % i,
            "stripe_customer_id": "cus_faux_fixture", "cancel_at_period_end": False, "remaining_sessions": 8,
            "total_sessions": 8, "renewal_sessions": 8, "renewal_price": 59.0, "price": 59.0,
            "created_at": now.isoformat(), "expires_at": (now + timedelta(days=30)).isoformat(), MARQUE: True}

a = sys.argv[1] if len(sys.argv) > 1 else ""
if a == "deadline-passee":
    r = db.offers.update_one({"id": FID}, {"$set": {"countdown_date": "2026-01-01", "countdown_time": "00:00"}})
    print("deadline 2026-01-01 00:00 posée :", r.modified_count)
elif a == "deadline-restaurer":
    r = db.offers.update_one({"id": FID}, {"$set": {"countdown_date": "2026-09-30", "countdown_time": "23:59"}})
    print("deadline 2026-09-30 23:59 restaurée :", r.modified_count)
elif a == "stock-plein":
    db.subscriptions.delete_many({MARQUE: True, "user_email": {"$regex": "^pw-stock-"}})
    docs = [abonnement_fictif("pw-stock-%02d@example.com" % i, i) for i in range(50)]
    db.subscriptions.insert_many(docs)
    print("50 abonnements Fondateurs fictifs insérés ; total offre :", db.subscriptions.count_documents({"offer_id": FID, "status": {"$ne": "superseded"}}))
elif a == "stock-restaurer":
    r = db.subscriptions.delete_many({MARQUE: True, "user_email": {"$regex": "^pw-stock-"}})
    print("abonnements fictifs retirés :", r.deleted_count, "; restants offre :", db.subscriptions.count_documents({"offer_id": FID, "status": {"$ne": "superseded"}}))
elif a == "abonne-actif":
    email = sys.argv[2].strip().lower()
    assert email.endswith("@example.com")
    db.subscriptions.insert_one(abonnement_fictif(email, 999))
    print("abonné actif fictif :", email)
elif a == "nettoyer-abonnes":
    r = db.subscriptions.delete_many({MARQUE: True})
    print("fixtures retirées :", r.deleted_count)
else:
    sys.exit("action inconnue")
