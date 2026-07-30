"""
V344/V348 — BASCULE de SUPERADMIN_JWT_STRICT + vérification complète.

Tout ce qui est créé ici est de TEST et supprimé en fin de script. Aucune vraie
publication, aucune vraie conversation, aucun vrai paiement. Le jeton est forgé en
mémoire pour 10 minutes, jamais affiché, jamais écrit.

    python3 bascule_v344.py              -> bascule à TRUE puis vérifie
    python3 bascule_v344.py --rollback   -> repasse à FALSE (une commande)
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
MEDIA = "https://res.cloudinary.com/dtm0r7hwq/image/upload/publications/nonregression_test.jpg"
T = 40

env = {}
with open("/Users/afroboost/afroboost-v11-dev/.env.local", encoding="utf-8") as f:
    for l in f:
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
cli.close()

JETON = pyjwt.encode({"email": ADMIN, "role": "super_admin",
                      "iat": datetime.now(timezone.utc),
                      "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
                     secret, algorithm="HS256")
SIGNE = {"Authorization": "Bearer " + JETON}          # identité PROUVÉE
USURPE = {"X-User-Email": ADMIN}                       # identité PRÉTENDUE


def flag():
    return requests.get(BASE + "/api/feature-flags", timeout=T).json().get("SUPERADMIN_JWT_STRICT")


def basculer(valeur):
    r = requests.put(BASE + "/api/feature-flags",
                     json={"SUPERADMIN_JWT_STRICT": valeur}, headers=SIGNE, timeout=T)
    return r.status_code


if "--rollback" in sys.argv:
    print(f"avant : {flag()}")
    print(f"PUT -> HTTP {basculer(False)}")
    print(f"après : {flag()}")
    sys.exit(0)

resultats = []


def verif(titre, ok, detail=""):
    resultats.append(ok)
    print(f"{'✅' if ok else '❌'} {titre}" + (f"   [{detail}]" if detail else ""))


print(f"=== drapeau AVANT : {flag()} ===")
print(f"PUT /feature-flags (jeton signé) -> HTTP {basculer(True)}")
print(f"=== drapeau APRÈS : {flag()} ===\n")
verif("drapeau SUPERADMIN_JWT_STRICT = True", flag() is True)

a_nettoyer_pub, a_nettoyer_conv = [], []

# ============ (a) PUBLIER EN PERMANENT ============
print("\n--- (a) publication permanente (no_expiry) ---")
r = requests.post(BASE + "/api/publications",
                  json={"media_url": MEDIA, "media_type": "image",
                        "caption": "TEST non-régression (V344 bascule)", "no_expiry": True},
                  headers=SIGNE, timeout=T)
d = r.json() if r.status_code == 200 else {}
pid_signe = d.get("id", "")
if pid_signe:
    a_nettoyer_pub.append(pid_signe)
verif("SIGNÉ : publication permanente accordée", r.status_code == 200 and d.get("no_expiry") is True,
      f"HTTP {r.status_code} no_expiry={d.get('no_expiry')}")

r = requests.post(BASE + "/api/publications",
                  json={"media_url": MEDIA, "media_type": "image",
                        "caption": "TEST non-régression (V344 usurpé)", "no_expiry": True},
                  headers=USURPE, timeout=T)
d2 = r.json() if r.status_code == 200 else {}
if d2.get("id"):
    a_nettoyer_pub.append(d2["id"])
verif("USURPÉ : no_expiry IGNORÉ (48 h)", d2.get("no_expiry") is False,
      f"HTTP {r.status_code} no_expiry={d2.get('no_expiry')}")

# ============ (b) BOOST GRATUIT ============
print("\n--- (b) Boost gratuit vers une autre vitrine ---")
if pid_signe:
    rd = requests.get(f"{BASE}/api/publications/{pid_signe}/boost/destinations", headers=SIGNE, timeout=T)
    dd = rd.json() if rd.status_code == 200 else {}
    dests = [x for x in dd.get("destinations", []) if x.get("kind") == "coach"]
    verif("SIGNÉ : gratuité annoncée", dd.get("gratuit") is True, f"gratuit={dd.get('gratuit')}")

    ru = requests.get(f"{BASE}/api/publications/{pid_signe}/boost/destinations", headers=USURPE, timeout=T)
    du = ru.json() if ru.status_code == 200 else {}
    verif("USURPÉ : gratuité NON annoncée", du.get("gratuit") is not True, f"gratuit={du.get('gratuit')}")

    if dests:
        cible = dests[0]["target"]
        rb = requests.post(f"{BASE}/api/publications/{pid_signe}/boost/checkout",
                           json={"target": cible}, headers=SIGNE, timeout=T)
        db_ = rb.json() if rb.status_code == 200 else {}
        verif("SIGNÉ : Boost gratuit accordé (montant 0, aucun paiement)",
              rb.status_code == 200 and db_.get("gratuit") is True and db_.get("amount_chf") == 0,
              f"HTTP {rb.status_code} gratuit={db_.get('gratuit')} montant={db_.get('amount_chf')}")

        rb2 = requests.post(f"{BASE}/api/publications/{pid_signe}/boost/checkout",
                            json={"target": cible}, headers=USURPE, timeout=T)
        verif("USURPÉ : Boost gratuit REFUSÉ (403)", rb2.status_code == 403, f"HTTP {rb2.status_code}")
    else:
        verif("Boost : aucune vitrine coach disponible", False, "test non concluant")

# ============ (c) SUPPRESSION DE CONVERSATION ============
print("\n--- (c) suppression d'une conversation de test ---")
for etiquette, entetes, attendu in (("SIGNÉ", SIGNE, 200), ("USURPÉ", USURPE, 403), ("ANONYME", {}, 403)):
    rs = requests.post(BASE + "/api/chat/smart-entry",
                       json={"name": "V344 sonde", "email": f"v344-{uuid.uuid4().hex[:8]}@example.com"},
                       timeout=T)
    sid = ((rs.json() or {}).get("session") or {}).get("id") if rs.status_code == 200 else ""
    if not sid:
        verif(f"{etiquette} : conversation de sonde non créée", False)
        continue
    a_nettoyer_conv.append(sid)
    rd = requests.delete(f"{BASE}/api/chat/sessions/{sid}", headers=entetes, timeout=T)
    verif(f"{etiquette} : DELETE -> {attendu}", rd.status_code == attendu, f"HTTP {rd.status_code}")

# ============ (4) COACHS / ABONNÉS NON IMPACTÉS ============
print("\n--- (4) parcours coachs / abonnés / public ---")
verif("mur public des publications lisible",
      requests.get(BASE + "/api/publications", timeout=T).status_code == 200)
verif("prix du Boost lisible publiquement (parcours payant intact)",
      requests.get(BASE + "/api/settings/boost-price", timeout=T).status_code == 200)
verif("conversations lisibles avec identité signée",
      requests.get(BASE + "/api/chat/sessions", headers=SIGNE, timeout=T).status_code == 200)
verif("offres publiques lisibles", requests.get(BASE + "/api/offers", timeout=T).status_code == 200)
verif("cours publics lisibles", requests.get(BASE + "/api/courses", timeout=T).status_code == 200)

# ============ NETTOYAGE ============
print("\n--- nettoyage des données de test ---")
for pid in a_nettoyer_pub:
    requests.delete(f"{BASE}/api/publications/{pid}", headers=SIGNE, timeout=T)
for sid in a_nettoyer_conv:
    requests.delete(f"{BASE}/api/chat/sessions/{sid}", headers=SIGNE, timeout=T)
print(f"{len(a_nettoyer_pub)} publication(s) et {len(a_nettoyer_conv)} conversation(s) de test retirées.")

print(f"\n=== {sum(resultats)}/{len(resultats)} vérifications OK — drapeau = {flag()} ===")
if not all(resultats):
    print("ROLLBACK CONSEILLÉ : python3 bascule_v344.py --rollback")
sys.exit(0 if all(resultats) else 1)
