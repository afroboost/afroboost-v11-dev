"""
Mise à la CORBEILLE des conversations de test (is_deleted = True, RÉVERSIBLE).

Critères CUMULATIFS — les quatre doivent être vrais, sinon la conversation est
laissée intacte :
  1. pas déjà dans la corbeille ;
  2. l'email du participant (ou celui porté par la session) est en @example.com
     — domaine réservé par la RFC 2606 aux exemples et aux tests ;
  3. ZÉRO message ;
  4. la catégorie calculée est « visitor » — donc ni abonné, ni lien intelligent.

Rien n'est supprimé définitivement. Usage :
    python3 purge_tests.py            -> essai à blanc (n'écrit rien)
    python3 purge_tests.py --appliquer
    python3 purge_tests.py --annuler   -> restaure ce que CE script a mis en corbeille
"""
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pymongo import MongoClient

MARQUE = "purge_tests_v347"   # trace posée pour pouvoir annuler EXACTEMENT ce lot

env = {}
with open("/Users/afroboost/afroboost-v11-dev/.env.local", encoding="utf-8") as f:
    for l in f:
        m = re.match(r"^\s*([A-Z_0-9]+)\s*=\s*(.*)\s*$", l)
        if m:
            env[m.group(1)] = m.group(2).strip().strip('"').strip("'")

cli = MongoClient(env["MONGO_URL"], serverSelectionTimeoutMS=15000)
db = cli[env.get("DB_NAME") or "promo-credits-lab"]

if "--annuler" in sys.argv:
    r = db.chat_sessions.update_many(
        {"deleted_reason": MARQUE},
        {"$set": {"is_deleted": False}, "$unset": {"deleted_at": "", "deleted_reason": ""}},
    )
    print(f"restaurées : {r.modified_count}")
    cli.close()
    sys.exit(0)

appliquer = "--appliquer" in sys.argv

abonnes = {(s.get("email") or "").lower().strip()
           for s in db.subscriptions.find({"status": "active"}, {"_id": 0, "email": 1})}
abonnes |= {(d.get("assignedEmail") or "").lower().strip()
            for d in db.discount_codes.find({"active": True}, {"_id": 0, "assignedEmail": 1})}
abonnes.discard("")

pmap = {p["id"]: p for p in db.chat_participants.find({}, {"_id": 0, "id": 1, "email": 1})}
nb_msg = {r["_id"]: r["n"] for r in db.chat_messages.aggregate([
    {"$match": {"is_deleted": {"$ne": True}}},
    {"$group": {"_id": "$session_id", "n": {"$sum": 1}}},
])}


def email_de(s):
    for pid in (s.get("participant_ids") or []):
        p = pmap.get(pid)
        if p and (p.get("email") or "").strip():
            return p["email"].lower().strip()
    return (s.get("participantEmail") or "").lower().strip()


def categorie(s):
    if s.get("is_smart_link") is True or s.get("lead_type") is not None:
        return "smart_link"
    e = email_de(s)
    return "subscriber" if (e and e in abonnes) else "visitor"


vivantes = list(db.chat_sessions.find({"is_deleted": {"$ne": True}}, {"_id": 0}))


def compte(lot):
    return Counter(categorie(s) for s in lot)


print("=== AVANT ===")
print(f"conversations visibles : {len(vivantes)}")
c = compte(vivantes)
for k in ("subscriber", "visitor", "smart_link"):
    print(f"   {k:12} : {c.get(k, 0)}")

cibles = [
    s for s in vivantes
    if "@example.com" in email_de(s)
    and nb_msg.get(s.get("id"), 0) == 0
    and categorie(s) == "visitor"
]

print(f"\n=== CIBLES (les 4 critères réunis) : {len(cibles)} ===")
# Contrôle de sûreté : aucune cible ne doit être abonné/lien/porteuse de messages.
assert all(categorie(s) == "visitor" for s in cibles), "STOP : une cible n'est pas un visiteur"
assert all(nb_msg.get(s.get("id"), 0) == 0 for s in cibles), "STOP : une cible a des messages"
assert all("@example.com" in email_de(s) for s in cibles), "STOP : une cible n'est pas @example.com"
print("contrôles de sûreté : OK (aucun abonné, aucun lien intelligent, aucun message)")

restant = [s for s in vivantes if s not in cibles]
print("\n=== APRÈS (simulation) ===")
print(f"conversations visibles : {len(restant)}")
c2 = compte(restant)
for k in ("subscriber", "visitor", "smart_link"):
    print(f"   {k:12} : {c2.get(k, 0)}")

if not appliquer:
    print("\n(essai à blanc — RIEN n'a été modifié. Relancer avec --appliquer)")
    cli.close()
    sys.exit(0)

ids = [s["id"] for s in cibles if s.get("id")]
res = db.chat_sessions.update_many(
    {"id": {"$in": ids}},
    {"$set": {"is_deleted": True,
              "deleted_at": datetime.now(timezone.utc).isoformat(),
              "deleted_reason": MARQUE}},
)
print(f"\n=== APPLIQUÉ === mises en corbeille : {res.modified_count}")
print(f"réversible : python3 purge_tests.py --annuler")
cli.close()
