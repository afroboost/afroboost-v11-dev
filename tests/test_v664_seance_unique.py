# -*- coding: utf-8 -*-
"""V664 — UN MÊME COACH NE PROGRAMME PAS DEUX FOIS LA MÊME SÉANCE.

Banc contre un VRAI serveur : uvicorn démarré, vrai JWT coach, vraies requêtes
HTTP. Ce qu'il prouve, et surtout ce qu'il prouve NE PAS casser :

  REFUSÉ   même coach + même jour + même heure + même lieu          -> 409
  REFUSÉ   déplacer un cours (PUT) sur un créneau déjà occupé       -> 409
  AUTORISÉ plusieurs DATES du même cours
  AUTORISÉ plusieurs CONCEPTS, même heure, lieux différents
  AUTORISÉ deux COACHS différents au même créneau
  AUTORISÉ un lieu inconnu (on ne conclut jamais sans lieu)
  AUTORISÉ un cours ponctuel face à un récurrent
  AUTORISÉ reprogrammer sur le créneau d'un cours ARCHIVÉ
  AUTORISÉ modifier un cours sans le déplacer

Le défaut d'origine, mesuré le 11/11/2026 : mercredi 18:45 Valangines existait
deux fois (« Session Cardio » 71 réservations, « Cours à l'unité » 13).
"""
import json, os, subprocess, sys, time, urllib.error, urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
PORT = int(os.environ.get("V664_PORT", "8733"))
BASE = "http://127.0.0.1:%d" % PORT
SECRET = "banc-v664-secret-local"
os.environ["JWT_SECRET"] = SECRET
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ["DB_NAME"] = "test_v664"

COACH = "contact.artboost@gmail.com"
AUTRE_COACH = "coach.deux@exemple.test"
VAL = "Chemin des Valangines 97, 2000 Neuchâtel"
AILLEURS = "ArtDanse, Martigny"

_ok = _ko = 0
_T = [4]


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


from pymongo import MongoClient                                    # noqa: E402
import jwt as _pyjwt                                               # noqa: E402

cli = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=8000)
db = cli[os.environ["DB_NAME"]]
for c in ("courses", "coaches", "offers"):
    db[c].delete_many({})
# L'autre coach doit EXISTER : le super-admin ne peut désigner qu'un coach réel.
db.coaches.insert_one({"email": AUTRE_COACH, "name": "Coach Deux"})

_jet = lambda e: _pyjwt.encode(                                     # noqa: E731
    {"email": e, "role": "admin", "iat": int(time.time()),
     "exp": int(time.time()) + 7 * 86400}, SECRET, algorithm="HS256")
ENT = {"Authorization": "Bearer %s" % _jet(COACH)}


def creer(nom, **kw):
    corps = {"name": nom, "locationName": kw.pop("lieu", VAL), "visible": False}
    corps.update(kw)
    return appel("POST", "/api/courses", corps, ENT)


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
        st, _r = appel("GET", "/healthz")
        if st == 200:
            pret = True
            break
    if not pret:
        print("  SERVEUR INDISPONIBLE :", (proc.stderr.read() or b"")[-700:].decode("utf-8", "replace"))
        sys.exit(1)
    _T[0] = 25
    print("== serveur local prêt ==")
    print()

    print("== LA SÉANCE DE RÉFÉRENCE : mercredi 18:45, Valangines ==")
    st, ref = creer("Afroboost", weekday=3, time="18:45")
    v("créée (200)", st == 200, (st, ref))
    ID_REF = ref.get("id")

    print()
    print("== CE QUI DOIT ÊTRE REFUSÉ ==")
    st, rep = creer("Afroboost", weekday=3, time="18:45")
    v("le même cours, même créneau, même lieu, même coach -> 409", st == 409, (st, rep))
    v("et le refus NOMME la séance existante", "Afroboost" in str(rep.get("detail", "")), rep)
    # Le NOM ne doit rien y faire : c'est la séance physique qui compte.
    st, rep = creer("Un tout autre nom", weekday=3, time="18:45")
    v("un NOM différent sur le même créneau -> 409 aussi", st == 409, (st, rep))
    # L'écriture du lieu ne doit pas servir d'échappatoire.
    st, rep = creer("Afroboost", weekday=3, time="18h45",
                    lieu="chemin des valangines 97 2000 neuchatel")
    v("accents, casse et « 18h45 » ne contournent pas la garde -> 409", st == 409, (st, rep))
    v("rien n'a été inséré en trop",
      db.courses.count_documents({"time": {"$in": ["18:45", "18h45"]}, "weekday": 3}) == 1,
      db.courses.count_documents({}))

    print()
    print("== CE QUI DOIT RESTER AUTORISÉ ==")
    st, r2 = creer("Afroboost", weekday=0, time="18:30")
    v("le même cours un AUTRE JOUR (dimanche)", st == 200, (st, r2))
    st, r3 = creer("Afroboost", date="2026-11-25", time="18:45")
    v("une DATE précise face à un récurrent", st == 200, (st, r3))
    st, r4 = creer("Afroboost", date="2026-12-02", time="18:45")
    v("une SECONDE date du même cours", st == 200, (st, r4))
    st, r5 = creer("Afroboost Live", weekday=3, time="18:45", lieu=AILLEURS)
    v("un AUTRE CONCEPT, même heure, AUTRE LIEU", st == 200, (st, r5))
    st, r6 = appel("POST", "/api/courses", {
        "name": "Afroboost", "weekday": 3, "time": "18:45",
        "locationName": VAL, "visible": False, "coach_id": AUTRE_COACH}, ENT)
    v("un AUTRE COACH au même créneau", st == 200, (st, r6))
    st, r7 = creer("Afroboost sans lieu", weekday=3, time="18:45", lieu="")
    v("un lieu INCONNU n'est jamais refusé (on ne conclut pas)", st == 200, (st, r7))

    print()
    print("== UN CRÉNEAU LIBÉRÉ PAR ARCHIVAGE SE REPROGRAMME ==")
    db.courses.update_one({"id": ID_REF}, {"$set": {"archived": True}})
    st, r8 = creer("Afroboost", weekday=3, time="18:45")
    v("le créneau d'un cours ARCHIVÉ est de nouveau libre", st == 200, (st, r8))
    db.courses.update_one({"id": r8.get("id")}, {"$set": {"archived": True}})
    db.courses.update_one({"id": ID_REF}, {"$set": {"archived": False}})

    print()
    print("== LA MODIFICATION EST GARDÉE AUSSI ==")
    # Déplacer le dimanche sur le mercredi déjà occupé : refusé.
    st, rep = appel("PUT", "/api/courses/%s" % r2.get("id"),
                    {"weekday": 3, "time": "18:45", "locationName": VAL}, ENT)
    v("déplacer un cours sur un créneau occupé -> 409", st == 409, (st, rep))
    # Le cours n'a PAS bougé en base.
    _d = db.courses.find_one({"id": r2.get("id")}, {"_id": 0, "weekday": 1, "time": 1})
    v("et il n'a pas bougé en base", str(_d.get("weekday")) == "0" and _d.get("time") == "18:30", _d)
    # Modifier SANS déplacer : autorisé.
    st, rep = appel("PUT", "/api/courses/%s" % r2.get("id"),
                    {"name": "Afroboost", "description": "Sans casque audio"}, ENT)
    v("renommer sans déplacer reste autorisé", st == 200, (st, rep))
    # Se « déplacer » sur son propre créneau : autorisé (il ne se bloque pas lui-même).
    st, rep = appel("PUT", "/api/courses/%s" % ID_REF,
                    {"weekday": 3, "time": "18:45", "locationName": VAL}, ENT)
    v("un cours ne se bloque pas lui-même", st == 200, (st, rep))

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
