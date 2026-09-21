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
    # V534b : catalogue autorisé = les offres à 0 CHF réelles (copie lecture seule) ; recommandée = l'essai sur le mercredi
    # Une seule offre offerte est visible en prod : deux offres de TEST (0 CHF, même coach) complètent le catalogue.
    now = datetime.now(timezone.utc).isoformat()
    for oid, nom, pack, mois, desc in (("pw-duo-decouverte", "Pass découverte", 2, 1, "Deux séances pour découvrir Afroboost, à utiliser dans le mois."),
                                       ("pw-duo-etudiant", "Offre étudiant", 1, None, "Sur présentation d'une carte étudiant valide le jour du cours.")):
        doc = {"id": oid, "name": nom, "price": 0, "visible": True, "archived": False, "coach_id": "contact.artboost@gmail.com",
               "pack_sessions": pack, "description": desc, "category": "service", "isProduct": False, "created_at": now, MARQUE: True}
        if mois: doc["duree_mois"] = mois
        db.offers.update_one({"id": oid}, {"$set": doc}, upsert=True)
    OFFRES = ["c1e5f73c-0f16-402e-a746-2041e23f72e8", "pw-duo-decouverte", "pw-duo-etudiant"]
    for pref, reco in (("01f3b303", None), ("62fcac27", OFFRES[0])):
        c = db.courses.find_one({"id": {"$regex": "^" + pref}}, {"_id": 0, "id": 1, "name": 1, "time": 1, "weekday": 1, "locationName": 1})
        db.courses.update_one({"id": c["id"]}, {"$set": {"duo_enabled": True, "duo_offer_ids": OFFRES, "duo_default_offer_id": reco}})
        print("duo_enabled ->", c, "offres:", len(OFFRES), "reco:", bool(reco))
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
    n = {c: db[c].delete_many({MARQUE: True}).deleted_count for c in ("subscriptions", "discount_codes", "offers")}
    print("fixtures retirées :", n)
else:
    sys.exit("action inconnue")
