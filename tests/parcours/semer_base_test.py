# Copie LECTURE SEULE de la prod -> base de test `afroboost_pw_test` (collections de configuration, sans PII ni secrets).
from dbro import client, db as prod
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
