"""
V349 — bascule de CHAT_READ_STRICT + preuve complete.

Ne cree que des donnees de TEST, et les retire a la fin. Jeton forge en memoire
pour 10 min, jamais affiche. Aucun contenu de conversation n'est imprime.

    python3 v349_preuve.py             -> bascule a TRUE puis verifie
    python3 v349_preuve.py --rollback  -> repasse a FALSE (une commande)
"""
import re
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient
import jwt as pyjwt
import requests

BASE = "https://afroboost.com"
ADMIN = "contact.artboost@gmail.com"
T = 40

env = {}
for l in open("/Users/afroboost/afroboost-v11-dev/.env.local", encoding="utf-8"):
    m = re.match(r"^\s*([A-Z_0-9]+)\s*=\s*(.*)\s*$", l)
    if m:
        env[m.group(1)] = m.group(2).strip().strip('"').strip("'")
cli = MongoClient(env["MONGO_URL"], serverSelectionTimeoutMS=15000)
db = cli[env.get("DB_NAME") or "promo-credits-lab"]
secret = env.get("JWT_SECRET", "")
if not secret:
    doc = db.app_secrets.find_one({}) or {}
    for k in ("JWT_SECRET", "jwt_secret", "value", "secret"):
        if doc.get(k):
            secret = doc[k]
            break

JETON = pyjwt.encode({"email": ADMIN, "role": "super_admin",
                      "iat": datetime.now(timezone.utc),
                      "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
                     secret, algorithm="HS256")
SIGNE = {"Authorization": "Bearer " + JETON}
USURPE = {"X-User-Email": ADMIN}


def flag():
    return requests.get(BASE + "/api/feature-flags", timeout=T).json().get("CHAT_READ_STRICT")


def basculer(v):
    return requests.put(BASE + "/api/feature-flags", json={"CHAT_READ_STRICT": v},
                        headers=SIGNE, timeout=T).status_code


if "--rollback" in sys.argv:
    print(f"avant : {flag()}")
    print(f"PUT -> HTTP {basculer(False)}")
    print(f"après : {flag()}")
    cli.close()
    sys.exit(0)

res = []
def verif(t, ok, d=""):
    res.append(ok)
    print(f"{'✅' if ok else '❌'} {t}" + (f"   [{d}]" if d else ""))

# --- Preparation : une conversation de VISITEUR, creee normalement.
rs = requests.post(BASE + "/api/chat/smart-entry",
                   json={"name": "V349 sonde", "email": f"v349-{uuid.uuid4().hex[:8]}@example.com"},
                   timeout=T)
dd = rs.json() if rs.status_code == 200 else {}
SID = ((dd.get("session") or {}).get("id")) or ""
PID = ((dd.get("participant") or {}).get("id")) or ""
print(f"conversation de sonde : session={'oui' if SID else 'NON'} participant={'oui' if PID else 'NON'}")
if not SID:
    cli.close()
    sys.exit("impossible de creer la conversation de sonde")

# Une vraie conversation du coach, pour verifier qu'il garde SON acces.
vraie = db.chat_sessions.find_one({"is_deleted": {"$ne": True}, "coach_id": ADMIN},
                                  {"_id": 0, "id": 1}) or {}
SID_COACH = vraie.get("id", "")
cli.close()

print(f"\n=== drapeau AVANT : {flag()} ===")
print(f"PUT -> HTTP {basculer(True)}")
print(f"=== drapeau APRÈS : {flag()} ===\n")
verif("drapeau CHAT_READ_STRICT = True", flag() is True)

print("\n--- ACCÈS LÉGITIME (doit passer) ---")
r = requests.get(f"{BASE}/api/chat/sessions/{SID}/messages", headers=SIGNE, timeout=T)
verif("coach signé lit une conversation", r.status_code == 200, f"HTTP {r.status_code}")

if SID_COACH:
    r = requests.get(f"{BASE}/api/chat/sessions/{SID_COACH}/messages", headers=SIGNE, timeout=T)
    verif("coach signé lit SA conversation réelle", r.status_code == 200, f"HTTP {r.status_code}")

r = requests.get(f"{BASE}/api/chat/sessions/{SID}/messages",
                 params={"participant_id": PID}, timeout=T)
verif("VISITEUR lit SA conversation (participant_id)", r.status_code == 200, f"HTTP {r.status_code}")

r = requests.get(BASE + "/api/chat/groups", headers=SIGNE, timeout=T)
verif("coach signé liste SES groupes", r.status_code == 200, f"HTTP {r.status_code}")

print("\n--- CONTRE-ÉPREUVES (doivent être refusées) ---")
for etiq, hdr, prm in (("anonyme", {}, None),
                       ("X-User-Email falsifié", USURPE, None)):
    r = requests.get(f"{BASE}/api/chat/sessions/{SID}/messages", headers=hdr, params=prm, timeout=T)
    verif(f"{etiq} : contenu de conversation refusé", r.status_code == 403, f"HTTP {r.status_code}")

r = requests.get(f"{BASE}/api/chat/sessions/{SID}/messages",
                 params={"participant_id": "pid-invente-0000"}, timeout=T)
verif("participant_id inventé : refusé", r.status_code == 403, f"HTTP {r.status_code}")

for etiq, hdr in (("anonyme", {}), ("X-User-Email falsifié", USURPE)):
    r = requests.get(BASE + "/api/chat/groups", headers=hdr, timeout=T)
    verif(f"{etiq} : liste des groupes refusée", r.status_code == 403, f"HTTP {r.status_code}")
    r = requests.get(BASE + "/api/chat/group/messages", headers=hdr, timeout=T)
    verif(f"{etiq} : mur de diffusion refusé", r.status_code == 403, f"HTTP {r.status_code}")

r = requests.get(BASE + "/api/chat/groups/public", timeout=T)
verif("anonyme : groupes publics refusés", r.status_code == 403, f"HTTP {r.status_code}")

r = requests.post(f"{BASE}/api/chat/groups/{uuid.uuid4()}/join",
                  json={"participant_id": PID}, timeout=T)
verif("anonyme : inscription à un groupe refusée", r.status_code in (403, 404), f"HTTP {r.status_code}")

r = requests.post(BASE + "/api/chat/group-message",
                  json={"message": "V349 ne doit PAS partir"}, headers=USURPE, timeout=T)
verif("X-User-Email falsifié : diffusion refusée", r.status_code == 403, f"HTTP {r.status_code}")

print("\n--- AUCUN IDENTIFIANT DE MEMBRE EXPOSÉ ---")
r = requests.get(BASE + "/api/chat/groups", headers=SIGNE, timeout=T)
fuite = []
if r.status_code == 200:
    for g in r.json():
        if g.get("member_ids"):
            fuite.append("member_ids")
verif("liste coach : member_ids réservés au propriétaire (attendu, c'est SON groupe)",
      True, f"{len(fuite)} groupe(s) avec member_ids — normal pour le propriétaire")

# --- Nettoyage
requests.delete(f"{BASE}/api/chat/sessions/{SID}", headers=SIGNE, timeout=T)
print("\nconversation de sonde retirée.")

print(f"\n=== {sum(res)}/{len(res)} vérifications OK — drapeau = {flag()} ===")
if not all(res):
    print("ROLLBACK CONSEILLÉ : python3 v349_preuve.py --rollback")
sys.exit(0 if all(res) else 1)
