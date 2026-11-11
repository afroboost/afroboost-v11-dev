# -*- coding: utf-8 -*-
"""V662 — PARCOURS REELS CONTRE UN SERVEUR QUI TOURNE (pas une simulation).

On demarre uvicorn, on forge de VRAIS jetons avec les fonctions de production,
et on appelle les routes par HTTP. Ce que ce banc prouve, point par point :

  1. un MEMBRE legitime enregistre son telephone        -> lie et VERIFIE
  2. le COACH enregistre son telephone                  -> lie et VERIFIE
  3. un appareil SANS identite sous l'adresse d'un tiers -> aucune liaison
  4. un compte AUTHENTIFIE visant un autre compte        -> 403
  5. une liaison non prouvee deja en base                -> EFFACEE
  6. la rotation d'endpoint d'un appareil verifie        -> reste verifiee
  7. la desinscription ne touche QUE l'appareil designe

Prerequis : mongod local, JWT_SECRET pose par le banc lui-meme.
"""
import io, json, os, subprocess, sys, time, urllib.error, urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
PORT = int(os.environ.get("V662_PORT", "8731"))
BASE = "http://127.0.0.1:%d" % PORT
SECRET = "banc-v662-secret-local"
os.environ["JWT_SECRET"] = SECRET
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ["DB_NAME"] = "test_v662"

MEMBRE = "membre.v662@exemple.test"
TIERS = "victime.v662@exemple.test"
COACH = "contact.artboost@gmail.com"
PID_MEMBRE = "pid-membre-v662"
PID_TIERS = "pid-tiers-v662"

_ok = _ko = 0
_T = [4]      # court pendant l'attente du serveur, normal ensuite


def v(nom, cond, detail=""):
    global _ok, _ko
    if cond:
        _ok += 1
        print("  PASS  %s" % nom)
    else:
        _ko += 1
        print("  RATE  %s  -> %s" % (nom, str(detail)[:150]))


def appel(methode, chemin, corps=None, entetes=None):
    req = urllib.request.Request(BASE + chemin, method=methode)
    for k, val in (entetes or {}).items():
        req.add_header(k, val)
    donnees = None
    if corps is not None:
        donnees = json.dumps(corps).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, donnees, timeout=_T[0]) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}
    except Exception as e:  # noqa: BLE001
        return 0, {"erreur": type(e).__name__}


def abonnement(ep):
    return {"endpoint": ep, "keys": {"p256dh": "x" * 60, "auth": "y" * 20}}


# ---------------------------------------------------------------- preparation
from pymongo import MongoClient                                    # noqa: E402
cli = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=8000)
db = cli[os.environ["DB_NAME"]]
for c in ("push_subscriptions", "subscriber_sessions", "users", "chat_participants"):
    db[c].delete_many({})
db.users.insert_many([
    {"id": PID_MEMBRE, "email": MEMBRE, "name": "Membre V662"},
    {"id": PID_TIERS, "email": TIERS, "name": "Tiers V662"},
])

# --- de VRAIS jetons, forges par les fonctions de PRODUCTION ---
from api.routes.shared import lotb3s1_make_token                   # noqa: E402
JETON_MEMBRE, JTI_MEMBRE = lotb3s1_make_token("AFR-V662AA", MEMBRE, "coach_test", None)
db.subscriber_sessions.insert_one({
    "jti": JTI_MEMBRE, "code": "AFR-V662AA", "email": MEMBRE,
    "coach_id": "coach_test", "slug": None, "revoked": False,
})
import jwt as _pyjwt                                               # noqa: E402
JETON_COACH = _pyjwt.encode({"email": COACH, "role": "admin"}, SECRET, algorithm="HS256")

# ------------------------------------------------------------------- serveur
os.makedirs(os.path.join(RACINE, "frontend", "build"), exist_ok=True)
lien = os.path.join(RACINE, "static")
_lien_cree = False
if not os.path.exists(lien):
    os.symlink(os.path.join(RACINE, "frontend", "build"), lien)
    _lien_cree = True

proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "api.server:app", "--port", str(PORT), "--log-level", "warning"],
    cwd=RACINE, env=dict(os.environ), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
try:
    pret = False
    for _ in range(90):
        time.sleep(1)
        st, _ = appel("GET", "/healthz")
        if st == 200:
            pret = True
            break
    if not pret:
        print("  SERVEUR INDISPONIBLE :", (proc.stderr.read() or b"")[-700:].decode("utf-8", "replace"))
        sys.exit(1)
    _T[0] = 25
    print("== serveur local pret sur %s ==" % BASE)
    print()

    print("== 1. UN MEMBRE LEGITIME ENREGISTRE SON TELEPHONE ==")
    st, rep = appel("POST", "/api/push/subscribe", {
        "participant_id": PID_MEMBRE, "subscription": abonnement("https://fcm.test/membre-1"),
        "email": MEMBRE, "role": "subscriber",
    }, {"X-Subscriber-Token": JETON_MEMBRE})
    v("accepte (200)", st == 200, (st, rep))
    d = db.push_subscriptions.find_one({"subscription.endpoint": "https://fcm.test/membre-1"})
    v("l'appareil est VERIFIE", bool(d) and d.get("push_verifie") is True, d)
    v("l'adresse enregistree est celle du JETON", bool(d) and d.get("email") == MEMBRE, d and d.get("email"))
    v("la preuve utilisee est tracee", bool(d) and d.get("push_preuve") == "espace_b3s1",
      d and d.get("push_preuve"))

    print()
    print("== 2. LE COACH ENREGISTRE SON TELEPHONE ==")
    st, rep = appel("POST", "/api/push/subscribe", {
        "participant_id": "coach_%s" % COACH, "subscription": abonnement("https://fcm.test/coach-1"),
        "email": COACH, "role": "coach",
    }, {"Authorization": "Bearer %s" % JETON_COACH})
    v("accepte (200)", st == 200, (st, rep))
    d = db.push_subscriptions.find_one({"subscription.endpoint": "https://fcm.test/coach-1"})
    v("l'appareil du coach est VERIFIE", bool(d) and d.get("push_verifie") is True, d)
    v("par son JWT", bool(d) and d.get("push_preuve") == "coach_jwt", d and d.get("push_preuve"))

    print()
    print("== 3. UN APPAREIL SANS IDENTITE, SOUS L'ADRESSE D'UN TIERS ==")
    st, rep = appel("POST", "/api/push/subscribe", {
        "participant_id": PID_TIERS, "subscription": abonnement("https://fcm.test/pirate-1"),
        "email": TIERS, "role": "subscriber",
    })
    # On n'ECHOUE pas l'appel (la rotation du Service Worker n'a pas de jeton) :
    # on refuse la LIAISON. L'appareil existe, il n'appartient a personne.
    v("l'appel n'est pas refuse (rotation preservee)", st == 200, (st, rep))
    d = db.push_subscriptions.find_one({"subscription.endpoint": "https://fcm.test/pirate-1"})
    v("AUCUNE adresse enregistree", bool(d) and not d.get("email"), d and d.get("email"))
    v("marque NON verifie", bool(d) and d.get("push_verifie") is False, d)

    print()
    print("== 4. UN COMPTE AUTHENTIFIE VISE UN AUTRE COMPTE ==")
    st, rep = appel("POST", "/api/push/subscribe", {
        "participant_id": PID_TIERS, "subscription": abonnement("https://fcm.test/vol-1"),
        "email": TIERS,
    }, {"X-Subscriber-Token": JETON_MEMBRE})
    v("REFUSE (403)", st == 403, (st, rep))
    v("et rien n'a ete enregistre",
      db.push_subscriptions.count_documents({"subscription.endpoint": "https://fcm.test/vol-1"}) == 0)

    print()
    print("== 5. UNE LIAISON NON PROUVEE DEJA EN BASE EST EFFACEE ==")
    db.push_subscriptions.insert_one({
        "participant_id": PID_TIERS, "subscription": abonnement("https://fcm.test/legacy-1"),
        "active": True, "email": TIERS,          # posee AVANT V662, sans preuve
    })
    st, rep = appel("POST", "/api/push/subscribe", {
        "participant_id": PID_TIERS, "subscription": abonnement("https://fcm.test/legacy-1"),
        "email": TIERS,
    })
    d = db.push_subscriptions.find_one({"subscription.endpoint": "https://fcm.test/legacy-1"})
    v("l'adresse non prouvee a ete RETIREE", bool(d) and not d.get("email"), d and d.get("email"))

    print()
    print("== 6. LA ROTATION D'ENDPOINT NE DEGRADE PAS UN APPAREIL VERIFIE ==")
    # Le Service Worker n'a AUCUN jeton : il presente l'ancien endpoint.
    st, rep = appel("POST", "/api/push/subscribe", {
        "participant_id": PID_MEMBRE, "subscription": abonnement("https://fcm.test/membre-2"),
        "previous_endpoint": "https://fcm.test/membre-1",
    })
    v("accepte sans jeton (200)", st == 200, (st, rep))
    d = db.push_subscriptions.find_one({"subscription.endpoint": "https://fcm.test/membre-2"})
    v("le nouvel endpoint reste VERIFIE", bool(d) and d.get("push_verifie") is True, d)
    v("et garde l'adresse prouvee", bool(d) and d.get("email") == MEMBRE, d and d.get("email"))
    v("la preuve dit que c'est un report", bool(d) and str(d.get("push_preuve", "")).startswith("rotation:"),
      d and d.get("push_preuve"))

    print()
    print("== 7. LA DESINSCRIPTION NE TOUCHE QUE L'APPAREIL DESIGNE ==")
    db.push_subscriptions.update_many({"participant_id": PID_MEMBRE}, {"$set": {"active": True}})
    avant = db.push_subscriptions.count_documents({"participant_id": PID_MEMBRE, "active": True})
    st, rep = appel("DELETE", "/api/push/subscribe/%s?endpoint=%s"
                    % (PID_MEMBRE, "https%3A%2F%2Ffcm.test%2Fmembre-1"))
    apres = db.push_subscriptions.count_documents({"participant_id": PID_MEMBRE, "active": True})
    v("un seul appareil desactive", st == 200 and avant - apres == 1, (st, avant, apres))
    v("la portee est annoncee", rep.get("portee") == "appareil", rep)

    print()
    print("== 9. V662b — CONNAITRE UN ENDPOINT VERIFIE NE DONNE PAS L'IDENTITE ==")
    # L'attaque exacte que V662 avait laissee ouverte : poser SON PROPRE
    # appareil en declarant l'endpoint verifie de la victime comme « ancien ».
    # Le report d'une rotation ne doit JAMAIS traverser les comptes.
    st, rep = appel("POST", "/api/push/subscribe", {
        "participant_id": PID_TIERS,                       # un AUTRE compte
        "subscription": abonnement("https://fcm.test/pirate-rotation"),
        "previous_endpoint": "https://fcm.test/membre-2",   # endpoint VERIFIE du membre
    })
    v("l'appel n'est pas refuse (rotation legitime preservee)", st == 200, (st, rep))
    d = db.push_subscriptions.find_one({"subscription.endpoint": "https://fcm.test/pirate-rotation"})
    v("l'appareil N'EST PAS verifie", bool(d) and d.get("push_verifie") is not True, d)
    v("et n'a herite AUCUNE adresse", bool(d) and not d.get("email"), d and d.get("email"))
    # Et l'abonnement de la victime n'a pas ete abime au passage.
    dv = db.push_subscriptions.find_one({"subscription.endpoint": "https://fcm.test/membre-2"})
    v("l'appareil de la victime reste intact et verifie",
      bool(dv) and dv.get("push_verifie") is True and dv.get("email") == MEMBRE, dv)

    print()
    print("== 10. LA ROTATION DU MEME APPAREIL MARCHE TOUJOURS ==")
    st, rep = appel("POST", "/api/push/subscribe", {
        "participant_id": PID_MEMBRE,                      # LE MEME compte
        "subscription": abonnement("https://fcm.test/membre-3"),
        "previous_endpoint": "https://fcm.test/membre-2",
    })
    d = db.push_subscriptions.find_one({"subscription.endpoint": "https://fcm.test/membre-3"})
    v("le meme participant garde sa verification",
      st == 200 and bool(d) and d.get("push_verifie") is True, (st, d))

    print()
    print("== 8. UN TIERS AUTHENTIFIE NE PEUT PAS FAIRE TAIRE QUELQU'UN ==")
    st, rep = appel("DELETE", "/api/push/subscribe/%s" % PID_TIERS,
                    None, {"X-Subscriber-Token": JETON_MEMBRE})
    v("REFUSE (403)", st == 403, (st, rep))

finally:
    proc.terminate()
    try:
        proc.wait(timeout=12)
    except Exception:
        proc.kill()
    if _lien_cree and os.path.islink(lien):
        os.unlink(lien)
    cli.drop_database(os.environ["DB_NAME"])
    cli.close()

print()
print("  %d/%d" % (_ok, _ok + _ko))
sys.exit(0 if _ko == 0 else 1)
