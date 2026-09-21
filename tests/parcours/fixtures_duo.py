# Base de TEST `afroboost_pw_test` UNIQUEMENT (jamais la prod). Usage : python3 fixtures_duo.py activer | parrain <email> [seances] | nettoyer
import os, sys, uuid
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient
RACINE = os.environ.get("RACINE", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
env = {}
for l in open(os.path.join(RACINE, ".env.local")):
    l = l.strip()
    if "=" in l and not l.startswith("#"):
        k, v = l.split("=", 1); env[k] = v.strip().strip('"').strip("'")
db = MongoClient(env["MONGO_URL"], serverSelectionTimeoutMS=20000)["afroboost_pw_test"]
assert db.name == "afroboost_pw_test"
MARQUE = "pw_fixture_duo"
a = sys.argv[1] if len(sys.argv) > 1 else ""
if a == "activer":
    db.feature_flags.update_one({"id": "feature_flags"}, {"$set": {"parrainage_duo_enabled": True}}, upsert=True)
    for pref in ("01f3b303", "62fcac27"):
        c = db.courses.find_one({"id": {"$regex": "^" + pref}}, {"_id": 0, "id": 1, "name": 1, "time": 1, "weekday": 1, "locationName": 1})
        db.courses.update_one({"id": c["id"]}, {"$set": {"duo_enabled": True}})
        print("duo_enabled ->", c)
    print("offres 0 CHF :", [(o.get("id", "")[:8], o.get("name")) for o in db.offers.find({"price": 0}, {"id": 1, "name": 1})])
    print("terms_versions :", db.terms_versions.count_documents({}))
elif a == "parrain":
    email = sys.argv[2].strip().lower(); assert email.endswith("@example.com")
    seances = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    now = datetime.now(timezone.utc)
    code = "AFR-PD" + uuid.uuid4().hex[:4].upper()
    db.subscriptions.insert_one({"id": str(uuid.uuid4()), "user_email": email, "email": email, "name": "Bassi Parrain", "code": code,
        "offer_name": "Fondateurs", "status": "active", "remaining_sessions": seances, "total_sessions": 8, "used_sessions": 8 - seances,
        "price": 59.0, "created_at": now.isoformat(), "expires_at": (now + timedelta(days=30)).isoformat(), MARQUE: True})
    db.discount_codes.insert_one({"id": str(uuid.uuid4()), "code": code, "name": "Abonné fixture duo", "assignedEmail": email,
        "active": True, "maxUses": 8, "usedCount": 8 - seances, "type": "access", "created_at": now.isoformat(), MARQUE: True})
    print(code)
elif a == "nettoyer":
    n = {c: db[c].delete_many({MARQUE: True}).deleted_count for c in ("subscriptions", "discount_codes")}
    print("fixtures retirées :", n)
else:
    sys.exit("action inconnue")
