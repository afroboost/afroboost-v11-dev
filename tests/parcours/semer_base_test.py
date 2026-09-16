# Copie LECTURE SEULE de la prod -> base de test `afroboost_pw_test` (collections de configuration, sans PII ni secrets).
# E1 (16/09/2026) : autonome — lit MONGO_URL dans .env.local (avant : `from dbro import …`, helper jamais versionné).
import os
from pymongo import MongoClient
_RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_env = {}
for _l in open(os.path.join(_RACINE, ".env.local")):
    _l = _l.strip()
    if "=" in _l and not _l.startswith("#"):
        _k, _v = _l.split("=", 1); _env[_k] = _v.strip().strip('"').strip("'")
client = MongoClient(_env["MONGO_URL"], serverSelectionTimeoutMS=20000)
prod = client[_env.get("DB_NAME", "promo-credits-lab")]
test = client["afroboost_pw_test"]
BLANCHE = ["offers", "courses", "concept", "platform_settings", "feature_flags", "ai_config", "bot_quick_replies", "categories",
           "contact_categories", "contact_segments_config", "faqs", "social_proofs", "terms_versions", "media_links",
           "publications", "audio_tracks", "uploaded_files", "coaches", "coach_profiles", "calendar_events"]
for n in BLANCHE:
    docs = list(prod[n].find({}))
    test[n].drop()
    if docs:
        test[n].insert_many(docs)
    print(n, len(docs))
# Le coach de test se connecte par JWT local ; aucune donnée personnelle copiée (users, réservations, abonnements, contacts, messages : vides).
print("collections test :", sorted(test.list_collection_names()))
