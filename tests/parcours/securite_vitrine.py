#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V646 — Qui peut modifier une vitrine, et quel coach une URL désigne-t-elle ?

BANC LOCAL UNIQUEMENT : serveur `pile_locale.py` et MongoDB sur 127.0.0.1 (adresses écrites
ici, jamais lues dans l'environnement). Le script refuse de tourner hors de `reseau_local.sb`.
Comptes fictifs en @example.*, retirés à la fin. Le concept de la base de test est restauré.

    sandbox-exec -f tests/parcours/reseau_local.sb python3 tests/parcours/securite_vitrine.py
"""
import ctypes
import json
import socket
import subprocess
import sys
import time
import uuid

import jwt
import requests
from pymongo import MongoClient

BASE = "http://127.0.0.1:8001"
SECRET = "pw-local-secret"  # secret de pile_locale.py, sans valeur ailleurs
db = MongoClient("mongodb://127.0.0.1:27017")["afroboost_pw_test"]

ADMIN = "contact.artboost@gmail.com"
A = "coach-a.banc@example.com"
B = "coach-b.banc@example.org"
ANCIEN = "2026-01-01T00:00:00+00:00"
resultats = []


def v(nom, ok, detail=""):
    resultats.append(bool(ok))
    print(f"{'OK ' if ok else 'KO '} {nom}{' — ' + str(detail) if detail != '' else ''}")


def exiger_isolation():
    s = socket.socket()
    s.settimeout(4)
    try:
        s.connect(("1.1.1.1", 443))
        sys.exit("ARRÊT : ce script doit tourner dans reseau_local.sb")
    except PermissionError:
        pass
    except OSError:
        sys.exit("ARRÊT : isolation non prouvée")
    pid = int(subprocess.check_output(["lsof", "-nP", "-iTCP:8001", "-sTCP:LISTEN", "-t"]).split()[0])
    if ctypes.CDLL(None).sandbox_check(pid, None, 0) != 1:
        sys.exit("ARRÊT : le serveur 8001 ne tourne pas dans reseau_local.sb")
    print("OK  isolation : script et serveur dans le bac à sable")


def jeton(email, **extra):
    charge = {"email": email, "type": "coach", "iat": int(time.time()), "exp": int(time.time()) + 1800, **extra}
    return jwt.encode(charge, SECRET, algorithm="HS256")


def porteur(j):
    return {"Authorization": f"Bearer {j}"}


# ─────────────────────────────── données fictives ───────────────────────────────
def coach_doc(email, ident, nom, actif=True, cree=ANCIEN):
    return {"email": email, "id": ident, "name": nom, "is_active": actif, "created_at": cree, "role": "coach", "logo_url": "/origine.png", "credits": 1}


def semer():
    db.coaches.insert_many([coach_doc(A, "coach-a-id", "Coach A Banc"), coach_doc(B, "coach-b-id", "Coach B Banc")])
    db.concept.insert_one({"id": f"concept_{A}", "coach_id": A, "home_shop_banner_url": "/api/files/a/origine.png", "home_shop_banner_type": "image"})
    db.offers.insert_many([
        {"id": "offre-a-banc", "name": "Offre A", "price": 10, "coach_id": A, "visible": True, "images": []},
        {"id": "offre-plateforme-banc", "name": "Offre Plateforme", "price": 10, "coach_id": None, "visible": True, "images": []},
    ])
    db.courses.insert_many([
        {"id": "cours-a-banc", "name": "Cours A", "time": "18:00", "locationName": "Lieu", "coach_id": A, "visible": True, "archived": False},
        {"id": "cours-a-archive-banc", "name": "Cours A archivé", "time": "18:00", "locationName": "Lieu", "coach_id": A, "visible": True, "archived": True},
        {"id": "cours-plateforme-banc", "name": "Cours Plateforme", "time": "18:00", "locationName": "Lieu", "coach_id": None, "visible": True, "archived": False},
    ])
    db.payment_links.insert_one({"id": f"payment_links_{A}", "stripe": "https://example.test/origine"})


def nettoyer():
    q = {"$regex": r"@example[0-9]*\.(org|com|net)$"}
    db.coaches.delete_many({"email": q})
    db.users_auth.delete_many({"email": q})
    db.concept.delete_many({"id": {"$regex": r"^concept_.*@example[0-9]*\."}})
    db.offers.delete_many({"$or": [{"id": {"$regex": "banc"}}, {"coach_id": q}, {"name": "PIRATE"}]})
    db.courses.delete_many({"$or": [{"id": {"$regex": "banc"}}, {"coach_id": q}, {"name": "PIRATE"}]})
    db.payment_links.delete_many({"id": {"$regex": r"example[0-9]*\."}})
    db.coach_packs.delete_one({"id": "pack-banc-0"})
    db.reservations.delete_many({"id": {"$regex": "banc"}})
    db.chat_sessions.delete_many({"id": {"$regex": "banc"}})


def etat():
    """Empreinte de ce qu'un attaquant voudrait modifier."""
    lire = lambda col, q: db[col].find_one(q, {"_id": 0})  # noqa: E731
    return json.dumps({
        "concept_plateforme": {k: v2 for k, v2 in (lire("concept", {"id": "concept"}) or {}).items() if "banner" in k or k in ("appName", "logoUrl")},
        "concept_a": lire("concept", {"id": f"concept_{A}"}),
        "coach_a": lire("coaches", {"email": A}),
        "offre_a": lire("offers", {"id": "offre-a-banc"}),
        "offre_p": lire("offers", {"id": "offre-plateforme-banc"}),
        "cours_a": lire("courses", {"id": "cours-a-banc"}),
        "cours_arch": lire("courses", {"id": "cours-a-archive-banc"}),
        "cours_p": lire("courses", {"id": "cours-plateforme-banc"}),
        "paiement_a": lire("payment_links", {"id": f"payment_links_{A}"}),
        "paiement_p": lire("payment_links", {"id": "payment_links"}),
        "nb_offres": db.offers.count_documents({"name": "PIRATE"}),
        "nb_cours": db.courses.count_documents({"name": "PIRATE"}),
    }, sort_keys=True, default=str)


OFFRE = {"name": "PIRATE", "price": 1, "offer_type": "product"}
COURS = {"name": "PIRATE", "time": "18:00", "locationName": "Lieu"}
BANNIERE = {"home_shop_banner_url": "/api/files/pirate/x.png", "home_shop_banner_type": "image"}

# Les routes qui modifient une vitrine, chacune visant les données du coach A.
ROUTES = [
    ("PUT /concept", "put", "/api/concept", BANNIERE),
    ("PUT /payment-links", "put", "/api/payment-links", {"stripe": "https://example.test/pirate"}),
    ("POST /offers", "post", "/api/offers", OFFRE),
    ("PUT /offers/{A}", "put", "/api/offers/offre-a-banc", OFFRE),
    ("DELETE /offers/{A}", "delete", "/api/offers/offre-a-banc", None),
    ("POST /courses", "post", "/api/courses", COURS),
    ("PUT /courses/{A}", "put", "/api/courses/cours-a-banc", {"name": "PIRATE"}),
    ("PUT /courses/{A}/archive", "put", "/api/courses/cours-a-banc/archive", None),
    ("DELETE /courses/{A}", "delete", "/api/courses/cours-a-banc", None),
    ("DELETE /courses/purge/archived", "delete", "/api/courses/purge/archived", None),
    ("POST /coach/update-branding", "post", "/api/coach/update-branding", {"logo_url": "/pirate.png"}),
    ("POST /coach/update-seo", "post", "/api/coach/update-seo", {"meta_title": "PIRATE"}),
    ("PUT /coach/update-profile", "put", "/api/coach/update-profile", {"bio": "PIRATE"}),
]


def appel(meth, url, corps, entetes):
    return getattr(requests, meth)(BASE + url, json=corps, headers=entetes or {}, timeout=20)


def tester_refus():
    print("\n── Refus : usurpation et comptes non autorisés")
    expire = jwt.encode({"email": A, "type": "coach", "iat": 1, "exp": 2}, SECRET, algorithm="HS256")
    falsifie = jwt.encode({"email": A, "type": "coach", "exp": int(time.time()) + 900}, "mauvaise-cle-mauvaise-cle-mauvaise", algorithm="HS256")
    alg_none = jwt.encode({"email": A, "type": "coach", "exp": int(time.time()) + 900}, "", algorithm="none")
    abonne = jwt.encode({"email": A, "type": "subscriber", "exp": int(time.time()) + 900}, SECRET, algorithm="HS256")
    acteurs = [
        ("anonyme", {}),
        ("en-tête seul au nom de A", {"X-User-Email": A}),
        ("en-tête seul au nom du super-admin", {"X-User-Email": ADMIN}),
        ("jeton expiré de A", {**porteur(expire), "X-User-Email": A}),
        ("jeton falsifié de A", {**porteur(falsifie), "X-User-Email": A}),
        ("jeton sans signature (alg none)", {**porteur(alg_none), "X-User-Email": A}),
        ("jeton abonné au nom de A", {**porteur(abonne), "X-User-Email": A}),
    ]
    for acteur, entetes in acteurs:
        echecs = []
        for nom, meth, url, corps in ROUTES:
            avant = etat()
            r = appel(meth, url, corps, entetes)
            if r.status_code not in (401, 403) or etat() != avant:
                echecs.append(f"{nom}={r.status_code}")
                nettoyer_et_resemer()
        v(f"{acteur} : refus sur les {len(ROUTES)} routes, rien d'écrit", not echecs, " ".join(echecs)[:230])

    print("\n── Refus : le coach B ne touche pas aux données du coach A")
    jb = jeton(B)
    for nom, meth, url, corps in ROUTES:
        if "{A}" not in nom:
            continue
        avant = etat()
        r = appel(meth, url, corps, porteur(jb))
        v(f"jeton de B sur {nom}", r.status_code in (401, 403) and etat() == avant, r.status_code)
        if etat() != avant:
            nettoyer_et_resemer()
    for nom, meth, url, corps in [
        ("PUT /offers/{plateforme}", "put", "/api/offers/offre-plateforme-banc", OFFRE),
        ("DELETE /offers/{plateforme}", "delete", "/api/offers/offre-plateforme-banc", None),
        ("PUT /courses/{plateforme}", "put", "/api/courses/cours-plateforme-banc", {"name": "PIRATE"}),
        ("DELETE /courses/{plateforme}", "delete", "/api/courses/cours-plateforme-banc", None),
    ]:
        avant = etat()
        r = appel(meth, url, corps, porteur(jb))
        v(f"jeton de B sur {nom}", r.status_code in (401, 403) and etat() == avant, r.status_code)
        if etat() != avant:
            nettoyer_et_resemer()

    print("\n── Le jeton fait foi, jamais l'en-tête qui l'accompagne")
    avant_a = etat()
    for nom, meth, url, corps in [r for r in ROUTES if "{A}" not in r[0]]:
        appel(meth, url, corps, {**porteur(jb), "X-User-Email": A})
    d = json.loads(etat())
    ja = json.loads(avant_a)
    v("jeton de B + en-tête de A : le concept, le profil et les paiements de A restent intacts",
      d["concept_a"] == ja["concept_a"] and d["coach_a"] == ja["coach_a"] and d["paiement_a"] == ja["paiement_a"])
    v("jeton de B + en-tête de A : la plateforme reste intacte", d["concept_plateforme"] == ja["concept_plateforme"] and d["paiement_p"] == ja["paiement_p"])
    offre_b = db.offers.find_one({"name": "PIRATE"}, {"_id": 0, "coach_id": 1}) or {}
    v("jeton de B + en-tête de A : l'offre créée appartient à B", offre_b.get("coach_id") == B, offre_b)
    nettoyer_et_resemer()

    print("\n── Lecture du profil d'un autre coach")
    for acteur, entetes in (("anonyme", {}), ("en-tête seul au nom de A", {"X-User-Email": A}), ("jeton expiré de A", {**porteur(expire), "X-User-Email": A})):
        r = requests.get(f"{BASE}/api/coach/profile", headers=entetes, timeout=20)
        v(f"profil : {acteur} refusé", r.status_code in (401, 403) and A not in r.text, r.status_code)
    r = requests.get(f"{BASE}/api/coach/profile", headers={**porteur(jb), "X-User-Email": A}, timeout=20)
    v("profil : jeton de B + en-tête de A : c'est B qui répond", r.status_code == 200 and r.json().get("email") == B and A not in r.text, r.json().get("email"))
    r = requests.get(f"{BASE}/api/coach/profile", headers=porteur(jeton(A)), timeout=20)
    v("profil : jeton de A : 200 (règle V310c)", r.status_code == 200 and r.json().get("email") == A, r.status_code)

    print("\n── /coach/register : plus de compte actif anonyme")
    avant_nb = db.coaches.count_documents({})
    r = requests.post(f"{BASE}/api/coach/register", json={"email": "pirate1@example.org", "name": "Coach A Banc", "credits": 9999}, timeout=20)
    v("anonyme : refus, aucun compte créé", r.status_code in (401, 403) and db.coaches.count_documents({}) == avant_nb, r.status_code)
    r = requests.post(f"{BASE}/api/coach/register", json={"email": "pirate1@example.org", "name": "X", "credits": 9999}, headers={"X-User-Email": ADMIN}, timeout=20)
    v("en-tête du super-admin : refus", r.status_code in (401, 403) and not db.coaches.find_one({"email": "pirate1@example.org"}), r.status_code)
    r = requests.post(f"{BASE}/api/coach/register", json={"email": "pirate1@example.org", "name": "X", "credits": 9999}, headers=porteur(jeton(B)), timeout=20)
    v("jeton d'un coach ordinaire : refus", r.status_code in (401, 403) and not db.coaches.find_one({"email": "pirate1@example.org"}), r.status_code)
    r = requests.post(f"{BASE}/api/coach/register", json={"email": "cree-par-admin.banc@example.com", "name": "Cree Par Admin"}, headers=porteur(jeton(ADMIN)), timeout=20)
    v("jeton signé du super-admin : création possible", r.status_code == 200 and db.coaches.find_one({"email": "cree-par-admin.banc@example.com"}), r.status_code)


def jeton_session(email, role="coach"):
    """Le jeton tel que `/auth/login` et `/auth/me` l'émettent : email + role, SANS `type`."""
    return jwt.encode({"email": email, "role": role, "iat": int(time.time()), "exp": int(time.time()) + 1800}, SECRET, algorithm="HS256")


def tester_quatre_failles():
    print("\n── Faille 1 : un jeton qui n'est pas une session coach")
    abonne_espace = jwt.encode({"type": "subscriber_space", "email": A, "coach_id": A, "slug": None, "jti": "x", "iat": int(time.time()), "exp": int(time.time()) + 900}, SECRET, algorithm="HS256")
    abonne_espace_lui = jwt.encode({"type": "subscriber_space", "email": "abonne.banc@example.org", "coach_id": A, "jti": "y", "iat": int(time.time()), "exp": int(time.time()) + 900}, SECRET, algorithm="HS256")
    abonne = jwt.encode({"type": "subscriber", "code": "AFR-BANC", "email": "abonne.banc@example.org", "exp": int(time.time()) + 900}, SECRET, algorithm="HS256")
    invite = jwt.encode({"iss": "afroboost", "aud": "live-guest", "sub": "x", "email": A, "exp": int(time.time()) + 900}, SECRET, algorithm="HS256")
    autre_type = jwt.encode({"type": "admin", "email": ADMIN, "exp": int(time.time()) + 900}, SECRET, algorithm="HS256")
    for acteur, j in (("jeton subscriber_space au nom de A", abonne_espace), ("jeton subscriber_space d'un abonné", abonne_espace_lui),
                      ("jeton subscriber d'un abonné", abonne), ("jeton à audience (invité)", invite), ("type inconnu au nom du super-admin", autre_type),
                      ("jeton d'un inconnu, sans compte coach", jeton_session("inconnu.banc@example.org"))):
        echecs = []
        for nom, meth, url, corps in ROUTES:
            avant = etat()
            r = appel(meth, url, corps, porteur(j))
            if r.status_code not in (401, 403) or etat() != avant:
                echecs.append(f"{nom}={r.status_code}")
                nettoyer_et_resemer()
        v(f"{acteur} : refus sur les {len(ROUTES)} routes, rien d'écrit", not echecs, " ".join(echecs)[:200])

    print("\n── Coach désactivé : son jeton encore valide n'écrit plus")
    db.coaches.update_one({"email": A}, {"$set": {"is_active": False}})
    echecs = []
    for nom, meth, url, corps in ROUTES:
        avant = etat()
        r = appel(meth, url, corps, porteur(jeton_session(A)))
        if r.status_code != 403 or etat() != avant:
            echecs.append(f"{nom}={r.status_code}")
            db.coaches.update_one({"email": A}, {"$set": {"is_active": False}})
    v("coach désactivé : 403 sur toutes les routes, rien d'écrit", not echecs, " ".join(echecs)[:200])
    db.coaches.update_one({"email": A}, {"$set": {"is_active": True}})
    nettoyer_et_resemer()
    r = appel("put", "/api/concept", BANNIERE, porteur(jeton_session(A)))
    v("réactivé : il écrit de nouveau", r.status_code == 200, r.status_code)
    nettoyer_et_resemer()

    print("\n── Vraies sessions : connexion, renouvellement, compte activé")
    em, mdp = "session.banc@example.com", "motdepasse-banc-1"
    r = requests.post(f"{BASE}/api/auth/register", json={"email": em, "name": "Session Banc", "password": mdp}, timeout=20)
    v("inscription : compte en attente", r.status_code == 403, r.status_code)
    r = requests.post(f"{BASE}/api/auth/login", json={"email": em, "password": mdp}, timeout=20)
    v("en attente : connexion refusée, aucun jeton", r.status_code != 200 or not r.json().get("token"), r.status_code)
    r = requests.post(f"{BASE}/api/admin/activate-coach", json={"email": em}, headers=porteur(jeton_session(ADMIN, "super_admin")), timeout=20)
    if r.status_code == 404 or r.status_code == 405:
        db.users_auth.update_one({"email": em}, {"$set": {"pending_validation": False}})
        db.coaches.update_one({"email": em}, {"$set": {"is_active": True}})
    r = requests.post(f"{BASE}/api/auth/login", json={"email": em, "password": mdp}, timeout=20)
    jeton_reel = r.json().get("token") if r.status_code == 200 else ""
    v("connexion réelle : un jeton est émis", bool(jeton_reel), r.status_code)
    charge = jwt.decode(jeton_reel, SECRET, algorithms=["HS256"]) if jeton_reel else {}
    v("ce jeton a bien la forme attendue (rôle, sans type)", charge.get("role") == "coach" and "type" not in charge, sorted(charge))
    r2 = requests.put(f"{BASE}/api/concept", json=BANNIERE, headers=porteur(jeton_reel), timeout=20)
    v("jeton de connexion réel : écrit dans son concept", r2.status_code == 200, r2.status_code)
    r2 = requests.post(f"{BASE}/api/courses", json=COURS, headers=porteur(jeton_reel), timeout=20)
    v("jeton de connexion réel : crée son cours", r2.status_code == 200 and r2.json().get("coach_id") == em, r2.status_code)
    r2 = requests.get(f"{BASE}/api/coach/profile", headers=porteur(jeton_reel), timeout=20)
    v("jeton de connexion réel : lit son profil", r2.status_code == 200 and r2.json().get("email") == em, r2.status_code)
    cookie = r.cookies.get("coach_session_token") or ""
    r3 = requests.get(f"{BASE}/api/auth/me", cookies={"coach_session_token": cookie}, timeout=20)
    jeton_neuf = r3.json().get("token") if r3.status_code == 200 else ""
    v("renouvellement réel par /auth/me : un jeton est émis", bool(jeton_neuf), r3.status_code)
    r4 = requests.put(f"{BASE}/api/concept", json=BANNIERE, headers=porteur(jeton_neuf), timeout=20)
    v("jeton renouvelé : écrit dans son concept", r4.status_code == 200, r4.status_code)
    r5 = requests.get(f"{BASE}/api/auth/whoami", headers=porteur(jeton_neuf), timeout=20)
    v("/auth/whoami reconnaît le jeton renouvelé", r5.status_code == 200 and r5.json().get("valid") is True, r5.status_code)
    r6 = requests.put(f"{BASE}/api/concept", json=BANNIERE, headers=porteur(jeton_session(ADMIN, "super_admin")), timeout=20)
    v("session du super-admin : écrit dans le concept de la plateforme", r6.status_code == 200, r6.status_code)
    nettoyer_et_resemer()

    print("\n── Faille 2 : créer un cours au nom d'un autre")
    ja = porteur(jeton_session(A))
    r = requests.post(f"{BASE}/api/courses", json={**COURS, "coach_id": B}, headers=ja, timeout=20)
    v("A crée un cours « de B » : il reste à A", r.status_code == 200 and r.json().get("coach_id") == A, (r.status_code, r.json().get("coach_id")))
    r = requests.post(f"{BASE}/api/courses", json={**COURS, "coach_id": ADMIN}, headers=ja, timeout=20)
    v("A crée un cours « de la plateforme » : il reste à A", r.status_code == 200 and r.json().get("coach_id") == A, r.json().get("coach_id"))
    jadm = porteur(jeton_session(ADMIN, "super_admin"))
    r = requests.post(f"{BASE}/api/courses", json={**COURS, "coach_id": A}, headers=jadm, timeout=20)
    v("le super-admin peut créer un cours pour un coach existant", r.status_code == 200 and r.json().get("coach_id") == A, r.status_code)
    r = requests.post(f"{BASE}/api/courses", json={**COURS, "coach_id": "fantome.banc@example.org"}, headers=jadm, timeout=20)
    v("le super-admin : coach inexistant refusé", r.status_code == 400, r.status_code)
    r = requests.post(f"{BASE}/api/courses", json=COURS, headers=jadm, timeout=20)
    v("le super-admin, sans propriétaire : le cours est à lui", r.status_code == 200 and r.json().get("coach_id") == ADMIN, r.json().get("coach_id"))
    nettoyer_et_resemer()

    print("\n── Faille 3 : champs protégés d'un cours")
    protege = {"id": "vole-banc", "_id": "vole-banc", "coach_id": B, "owner_id": "vole", "owner_type": "partner", "name": "Renomme"}
    for acteur, entetes in (("le propriétaire", ja), ("le super-admin", jadm)):
        nettoyer_et_resemer()
        r = requests.put(f"{BASE}/api/courses/cours-a-banc", json=protege, headers=entetes, timeout=20)
        d = db.courses.find_one({"id": "cours-a-banc"}, {"_id": 0}) or {}
        v(f"{acteur} : id, coach_id et owner_* restent inchangés", r.status_code == 200 and d.get("coach_id") == A and "owner_id" not in d and "owner_type" not in d and not db.courses.find_one({"id": "vole-banc"}), (r.status_code, d.get("coach_id")))
        v(f"{acteur} : les autres champs sont bien modifiés", d.get("name") == "Renomme", d.get("name"))
    nettoyer_et_resemer()
    complet = db.courses.find_one({"id": "cours-a-banc"}, {"_id": 0})
    complet["name"] = "Comme le tableau de bord"
    r = requests.put(f"{BASE}/api/courses/cours-a-banc", json=complet, headers=ja, timeout=20)
    v("PUT d'un cours complet, comme le tableau de bord : toujours accepté", r.status_code == 200 and db.courses.find_one({"id": "cours-a-banc"})["name"] == "Comme le tableau de bord", r.status_code)
    nettoyer_et_resemer()

    print("\n── Faille 4 : supprimer ou archiver un cours inexistant")
    fantome = "cours-fantome-banc"

    def semer_liees():
        db.reservations.delete_many({"courseId": fantome})
        db.chat_sessions.delete_many({"courseId": fantome})
        db.reservations.insert_one({"id": "resa-fantome-banc", "courseId": fantome})
        db.chat_sessions.insert_one({"id": "chat-fantome-banc", "courseId": fantome})

    for acteur, entetes in (("un coach", ja), ("le super-admin", jadm)):
        semer_liees()
        r = requests.delete(f"{BASE}/api/courses/{fantome}", headers=entetes, timeout=20)
        v(f"{acteur} : suppression d'un cours inexistant = 404, données liées conservées", r.status_code == 404 and db.reservations.count_documents({"courseId": fantome}) == 1 and db.chat_sessions.count_documents({"courseId": fantome}) == 1, r.status_code)
        r = requests.put(f"{BASE}/api/courses/{fantome}/archive", headers=entetes, timeout=20)
        v(f"{acteur} : archivage d'un cours inexistant = 404", r.status_code == 404, r.status_code)
    db.reservations.delete_many({"courseId": fantome})
    db.chat_sessions.delete_many({"courseId": fantome})
    db.reservations.insert_one({"id": "resa-a-banc", "courseId": "cours-a-banc"})
    r = requests.delete(f"{BASE}/api/courses/cours-a-banc", headers=ja, timeout=20)
    v("cours existant : suppression et réservations liées, comme avant", r.status_code == 200 and not db.courses.find_one({"id": "cours-a-banc"}) and not db.reservations.find_one({"id": "resa-a-banc"}), r.status_code)
    nettoyer_et_resemer()


# Routes qui lisaient SEULEMENT l'en-tête : le drapeau REQUIRE_COACH_JWT ne les protège pas.
ROUTES_ENTETE = [
    ("PUT /payment-config", "put", "/api/payment-config", {"stripe_publishable_key": "pk_pirate", "twint_direct_url": "https://pirate.example/t"}),
    ("GET /payment-config", "get", "/api/payment-config", None),
    ("POST /payment-config/test", "post", "/api/payment-config/test/stripe", {}),
    ("GET /coach-profile", "get", "/api/coach-profile", None),
    ("PUT /coach-profile", "put", "/api/coach-profile", {"name": "PIRATE"}),
    ("POST /coach/faq", "post", "/api/coach/faq", {"question": "PIRATE", "answer": "PIRATE"}),
    ("PUT /coach/faq/{A}", "put", "/api/coach/faq/faq-a-banc", {"question": "PIRATE", "answer": "PIRATE"}),
    ("DELETE /coach/faq/{A}", "delete", "/api/coach/faq/faq-a-banc", None),
    ("POST /audio-tracks", "post", "/api/audio-tracks", {"title": "PIRATE", "url": "https://example.test/x.mp3"}),
    ("PUT /audio-tracks/{A}", "put", "/api/audio-tracks/piste-a-banc", {"title": "PIRATE"}),
    ("DELETE /audio-tracks/{A}", "delete", "/api/audio-tracks/piste-a-banc", None),
    ("POST /stripe/connect/create-account", "post", "/api/stripe/connect/create-account", {}),
    ("POST /stripe/connect/account-link", "post", "/api/stripe/connect/account-link", {}),
    ("GET /stripe/connect/status", "get", "/api/stripe/connect/status", None),
    ("PUT /audio-tracks/reorder", "put", "/api/audio-tracks/reorder", {"track_ids": []}),
    ("PUT /bot/quick-replies/{id}", "put", "/api/bot/quick-replies/reponse-banc", {"response": "PIRATE"}),
    ("POST /credits/deduct", "post", "/api/credits/deduct", {"action": "banc"}),
    ("POST /stripe/create-credit-checkout", "post", "/api/stripe/create-credit-checkout", {"pack_id": "banc"}),
    ("GET /social-proofs", "get", "/api/social-proofs", None),
    ("PUT /social-proofs/{A}/review", "put", "/api/social-proofs/preuve-a-banc/review", {"action": "reject"}),
    ("DELETE /social-proofs/{A}", "delete", "/api/social-proofs/preuve-a-banc", None),
]


FUITES = ("pk_origine", "sk_test_origine", "1990-01-01", "demande.privee@example.org")


def semer_partenaire():
    db.partner_payment_config.update_one({"coach_email": A}, {"$set": {"coach_email": A, "stripe_publishable_key": "pk_origine", "twint_direct_url": "https://origine.example/t", "stripe_secret_key": "sk_test_origine_banc"}}, upsert=True)
    db.coach_profiles.update_one({"email": A}, {"$set": {"email": A, "display_name": "Origine", "birthday": "1990-01-01"}}, upsert=True)
    db.bot_quick_replies.update_one({"id": "reponse-banc"}, {"$set": {"id": "reponse-banc", "response": "Origine"}}, upsert=True)
    db.social_proofs.update_one({"id": "preuve-a-banc"}, {"$set": {"id": "preuve-a-banc", "coach_id": A, "status": "pending", "email": "demande.privee@example.org"}}, upsert=True)
    db.faqs.update_one({"id": "faq-a-banc"}, {"$set": {"id": "faq-a-banc", "coach_email": A, "question": "Origine", "answer": "Origine"}}, upsert=True)
    db.audio_tracks.update_one({"id": "piste-a-banc"}, {"$set": {"id": "piste-a-banc", "coach_email": A, "title": "Origine", "url": "https://example.test/a.mp3"}}, upsert=True)


def etat_partenaire():
    return json.dumps({
        "paiement": db.partner_payment_config.find_one({"coach_email": A}, {"_id": 0}),
        "faq": db.faqs.find_one({"id": "faq-a-banc"}, {"_id": 0}),
        "piste": db.audio_tracks.find_one({"id": "piste-a-banc"}, {"_id": 0}),
        "coach": db.coaches.find_one({"email": A}, {"_id": 0}),
        "profil": db.coach_profiles.find_one({"email": A}, {"_id": 0}),
        "reponse": db.bot_quick_replies.find_one({"id": "reponse-banc"}, {"_id": 0}),
        "preuve": db.social_proofs.find_one({"id": "preuve-a-banc"}, {"_id": 0}),
        "pirates_faq": db.faqs.count_documents({"question": "PIRATE", "coach_email": A}),
        "pirates_pistes": db.audio_tracks.count_documents({"title": "PIRATE", "coach_email": A}),
    }, sort_keys=True, default=str)


def tester_routes_entete():
    print("\n── Routes partenaires qui ne lisaient que l'en-tête")
    semer_partenaire()
    espace = jwt.encode({"type": "subscriber_space", "email": A, "exp": int(time.time()) + 900}, SECRET, algorithm="HS256")
    for acteur, entetes, attendu_statut in (("anonyme", {}, (401,)), ("en-tête seul au nom de A", {"X-User-Email": A}, (401,)), ("jeton abonné au nom de A", {**porteur(espace), "X-User-Email": A}, (401,))):
        echecs = []
        for nom, meth, url, corps in ROUTES_ENTETE:
            avant = etat_partenaire()
            r = appel(meth, url, corps, entetes)
            # GET /coach-profile répond 200 sans jeton, mais VIDE : ce qui compte est qu'il ne livre rien.
            refus = attendu_statut + ((200,) if nom == "GET /coach-profile" else ())
            if r.status_code not in refus or etat_partenaire() != avant or any(s in r.text for s in FUITES):
                echecs.append(f"{nom}={r.status_code}")
                semer_partenaire()
        v(f"{acteur} : refus sur les {len(ROUTES_ENTETE)} routes, rien d'écrit", not echecs, " ".join(echecs)[:220])
    print("\n── Le jeton de B avec l'en-tête de A n'agit jamais au nom de A")
    entetes = {**porteur(jeton_session(B)), "X-User-Email": A}
    echecs = []
    for nom, meth, url, corps in ROUTES_ENTETE:
        # Ces réponses sont communes à la plateforme, pas à A : mesurées à part juste après.
        if nom.startswith("PUT /bot/quick-replies"):
            continue
        avant = etat_partenaire()
        r = appel(meth, url, corps, entetes)
        if etat_partenaire() != avant or any(s in r.text for s in FUITES):
            echecs.append(f"{nom}={r.status_code}")
            semer_partenaire()
    v("jeton de B + en-tête de A : les données de A restent intactes et illisibles", not echecs, " ".join(echecs)[:220])
    d = db.partner_payment_config.find_one({"coach_email": B}) or {}
    v("la configuration écrite est bien celle de B", d.get("stripe_publishable_key") == "pk_pirate", d.get("stripe_publishable_key"))
    # Décision produit en attente : l'onglet « Bot visiteurs » est offert à tous les coachs.
    # Ni vert ni rouge : le constat reste affiché à chaque passage, sans être masqué.
    r = appel("put", "/api/bot/quick-replies/reponse-banc", {"response": "PIRATE"}, porteur(jeton_session(B)))
    d = db.bot_quick_replies.find_one({"id": "reponse-banc"}) or {}
    print(f"RISQUE OUVERT  un coach modifie les réponses du bot communes à la plateforme — {r.status_code} {d.get('response')}")
    semer_partenaire()
    print("\n── La route qui promettait les clés en clair")
    r = appel("get", f"/api/payment-config/raw/{A}", None, {})
    v("anonyme : /payment-config/raw refusé, aucune clé", r.status_code == 403 and "sk_test_origine" not in r.text, r.status_code)
    r = appel("get", f"/api/payment-config/raw/{A}", None, porteur(jeton_session(A)))
    v("même le propriétaire : aucune clé en clair", "sk_test_origine" not in r.text, r.status_code)
    r = appel("get", f"/api/payment-config/raw/{A}", None, porteur(jeton_session(ADMIN, "super_admin")))
    v("super-admin : aucune clé en clair non plus", "sk_test_origine" not in r.text, r.status_code)
    print("\n── Accès légitime : le jeton seul suffit désormais (règle V310c)")
    ja = porteur(jeton_session(A))
    for nom, meth, url, corps in ROUTES_ENTETE:
        semer_partenaire()
        r = appel(meth, url, corps, ja)
        v(f"jeton de A : {nom} n'est plus refusé", r.status_code not in (401, 403), r.status_code)
    db.coaches.update_one({"email": A}, {"$set": {"is_active": False}})
    r = appel("put", "/api/payment-config", {"stripe_public_key": "pk_pirate"}, ja)
    v("coach désactivé : 403 sur sa configuration de paiement", r.status_code == 403, r.status_code)
    r = appel("get", "/api/coach-profile", None, ja)
    v("jeton de A : il lit son profil complet (règle V310c)", r.status_code == 200 and r.json().get("display_name"), r.text[:80])
    db.coaches.update_one({"email": A}, {"$set": {"is_active": True}})
    db.partner_payment_config.delete_many({"coach_email": {"$in": [A, B]}})
    db.faqs.delete_many({"$or": [{"id": "faq-a-banc"}, {"question": "PIRATE"}]})
    db.audio_tracks.delete_many({"$or": [{"id": "piste-a-banc"}, {"title": "PIRATE"}]})
    db.bot_quick_replies.delete_many({"id": "reponse-banc"})
    db.social_proofs.delete_many({"id": "preuve-a-banc"})
    db.coach_profiles.delete_many({"email": {"$regex": r"@example[0-9]*\."}})
    nettoyer_et_resemer()


def tester_effacer_date_cours():
    print("\n── Un cours : une date vide efface bien la date (cours récurrent)")
    db.courses.update_one({"id": "cours-date-banc"}, {"$set": {"id": "cours-date-banc", "coach_id": A, "name": "Date Banc", "date": "2026-12-01"}}, upsert=True)
    r = appel("put", "/api/courses/cours-date-banc", {"date": ""}, porteur(jeton_session(A)))
    d = db.courses.find_one({"id": "cours-date-banc"}) or {}
    v("PUT avec date vide : la date est effacée", r.status_code == 200 and d.get("date") == "", (r.status_code, d.get("date")))
    r = appel("put", "/api/courses/cours-date-banc", {"name": "Renomme", "date": None}, porteur(jeton_session(A)))
    d = db.courses.find_one({"id": "cours-date-banc"}) or {}
    v("PUT avec date nulle : rien n'est effacé, le reste est écrit", r.status_code == 200 and d.get("date") == "" and d.get("name") == "Renomme", (r.status_code, d.get("name")))
    db.courses.delete_many({"id": "cours-date-banc"})


def tester_apercu_partage():
    print("\n── Aperçu de partage : les champs d'un partenaire ne deviennent jamais du code")
    charge = '"/></title><script>alert(1)</script><img src=x onerror=alert(2)>'
    r = appel("post", "/api/coach/update-seo", {"meta_title": charge, "meta_description": charge}, porteur(jeton_session(A)))
    v("jeton de A : il enregistre son référencement", r.status_code == 200, r.status_code)
    db.coaches.update_one({"email": A}, {"$set": {"name": "Apercu Banc", "logo_url": charge, "platform_name": charge, "accent_color": charge}})
    r = appel("get", "/api/og/Apercu%20Banc", None, {})
    v("/api/og : la page répond", r.status_code == 200, r.status_code)
    v("/api/og : aucune balise injectée", "<script>alert" not in r.text and "<img src=x" not in r.text, r.text[r.text.find("<title>"):][:90])
    v("/api/og : le texte reste présent, échappé", "&lt;script&gt;" in r.text, "")
    db.coaches.update_one({"email": A}, {"$set": {"is_active": False}})
    r = appel("get", "/api/og/Apercu%20Banc", None, {})
    v("/api/og : un coach désactivé n'a plus d'aperçu à son nom", "Apercu Banc" not in r.text and "&lt;script&gt;" not in r.text, r.text[:70])
    db.coaches.update_one({"email": A}, {"$set": {"is_active": True, "name": "Coach A Banc", "meta_title": "", "meta_description": "", "logo_url": "", "platform_name": "", "accent_color": ""}})


def nettoyer_et_resemer():
    nettoyer()
    semer()


def tester_acces_legitime():
    print("\n── Accès légitime (règle V310c : 200 avec le jeton, sur les mêmes routes)")
    ja = porteur(jeton(A))
    for nom, meth, url, corps in ROUTES:
        nettoyer_et_resemer()
        c = {"name": "Renomme par A", "price": 12, "offer_type": "product"} if nom == "PUT /offers/{A}" else ({"name": "Renomme par A"} if nom == "PUT /courses/{A}" else corps)
        r = appel(meth, url, c, ja)
        v(f"jeton de A : {nom}", r.status_code == 200, r.status_code)
    nettoyer_et_resemer()
    r = requests.put(f"{BASE}/api/concept", json=BANNIERE, headers=porteur(jeton(A)), timeout=20)
    d = db.concept.find_one({"id": f"concept_{A}"}, {"_id": 0}) or {}
    v("jeton de A : écrit dans SON concept", r.status_code == 200 and d.get("home_shop_banner_url") == BANNIERE["home_shop_banner_url"])
    officielle = db.concept.find_one({"id": "concept"}, {"_id": 0, "home_shop_banner_url": 1, "boutique_page_banner_url": 1})
    v("jeton de A : bannières officielles intactes", officielle.get("home_shop_banner_url") != BANNIERE["home_shop_banner_url"])
    r = requests.put(f"{BASE}/api/offers/offre-plateforme-banc", json={"name": "Par admin", "price": 3, "offer_type": "product"}, headers=porteur(jeton(ADMIN)), timeout=20)
    v("jeton du super-admin : peut modifier une offre de la plateforme", r.status_code == 200, r.status_code)
    r = requests.put(f"{BASE}/api/courses/cours-a-banc", json={"name": "Par admin"}, headers=porteur(jeton(ADMIN)), timeout=20)
    v("jeton du super-admin : peut modifier le cours d'un coach", r.status_code == 200, r.status_code)
    avant = db.concept.find_one({"id": "concept"}, {"_id": 0, "boutique_page_banner_thumbnail": 1})
    r = requests.put(f"{BASE}/api/concept", json={"boutique_page_banner_thumbnail": ""}, headers=porteur(jeton(ADMIN)), timeout=20)
    v("jeton du super-admin : écrit dans le concept de la plateforme", r.status_code == 200 and avant is not None, r.status_code)
    nettoyer_et_resemer()
    arch_b = {"id": "cours-b-archive-banc", "name": "Cours B", "time": "18:00", "locationName": "Lieu", "coach_id": B, "archived": True}
    db.courses.insert_one(arch_b)
    r = requests.delete(f"{BASE}/api/courses/purge/archived", headers=porteur(jeton(B)), timeout=20)
    v("purge par B : les archives de A restent, les siennes partent",
      r.status_code == 200 and db.courses.find_one({"id": "cours-a-archive-banc"}) and not db.courses.find_one({"id": "cours-b-archive-banc"}), r.status_code)


# ───────────────────────── quel coach pour quelle URL ? ─────────────────────────
def vitrine(u):
    r = requests.get(f"{BASE}/api/coach/vitrine/{u}", timeout=20)
    return r.status_code, ((r.json().get("coach") or {}).get("id") if r.status_code == 200 else None), r.text


def attendu(nom, u, ident):
    s, i, _ = vitrine(u)
    v(nom, (s == 200 and i == ident) if ident else s == 404, f"{u} -> {s} {i}")


def tester_resolution():
    print("\n── URL normales : toujours le bon coach")
    db.coaches.insert_many([
        coach_doc("jean.dupont@example.com", "c-point", "Jean Point"),
        coach_doc("paul_dupont@example.com", "c-bas", "Paul Bas"),
        coach_doc("eric-dupont@example.com", "c-tiret", "Eric Tiret"),
        coach_doc("marc.banc@example.com", "c-marc", "Marc Lefevre Banc"),
        coach_doc("ab@example.com", "c-court", "Court"),
        coach_doc("twin@example.com", "c-t1", "Jumeau Un"),
        coach_doc("twin@example.org", "c-t2", "Jumeau Deux"),
    ])
    attendu("e-mail complet", "marc.banc@example.com", "c-marc")
    attendu("identifiant", "c-marc", "c-marc")
    attendu("nom exact", "Marc%20Lefevre%20Banc", "c-marc")
    attendu("nom en slug", "marc-lefevre-banc", "c-marc")
    attendu("début d'e-mail unique", "marc.banc", "c-marc")
    print("\n── Séparateurs . _ - : seulement eux, et un seul entre deux mots")
    attendu("jean-dupont trouve jean.dupont@", "jean-dupont", "c-point")
    attendu("paul-dupont trouve paul_dupont@", "paul-dupont", "c-bas")
    attendu("eric-dupont trouve eric-dupont@", "eric-dupont", "c-tiret")
    attendu("jean.dupont littéral", "jean.dupont", "c-point")
    print("\n── URL approximatives : refusées")
    for u in ("j-an-dupont", "jean-dup-nt", "m-rc.banc", "marc-b-nc", "a-", "-b", "--", "-", "a--b", "jean--dupont", "ab-", "ma", "marc", "jean", ".*", "%5E", "(a%2B)%2B%24", "jean%7Cpaul", "jean.dupont@example.net", "marc.banc@example.org"):
        attendu(f"approximative {u}", u, None)
    print("\n── Ambiguïté entre comptes existants : personne plutôt que le mauvais")
    attendu("même début d'e-mail", "twin", None)
    attendu("mais chacun par son e-mail", "twin@example.org", "c-t2")
    attendu("et par son identifiant", "c-t1", "c-t1")
    s, _, texte = vitrine("c-marc")
    v("réponse publique : aucun e-mail", s == 200 and "@example." not in texte)

    print("\n── Un nouveau compte ne récupère ni ne bloque une URL existante")
    db.coach_packs.update_one({"id": "pack-banc-0"}, {"$set": {"id": "pack-banc-0", "name": "Gratuit", "price": 0, "credits": 1, "visible": True}}, upsert=True)
    gratuit = lambda email, nom: requests.post(f"{BASE}/api/cinetpay/register-free", json={"email": email, "name": nom, "pack_id": "pack-banc-0"}, timeout=30)  # noqa: E731
    r = gratuit("pirate-nom@example.org", "Marc Lefevre Banc")
    v("inscription gratuite sous le nom d'un coach : compte créé", r.status_code == 200, r.status_code)
    attendu("le coach existant garde son URL par nom", "marc-lefevre-banc", "c-marc")
    r = gratuit("pirate-prefixe@example.org", "marc.banc")
    attendu("nommé comme son début d'e-mail : URL conservée", "marc.banc", "c-marc")
    r = gratuit("marc.banc@example.net", "Sans Rapport Banc")
    attendu("même début d'e-mail, autre domaine : URL conservée", "marc.banc", "c-marc")
    r = gratuit("c-marc-usurpe@example.org", "c-marc")
    attendu("nommé comme l'identifiant d'un coach : URL conservée", "c-marc", "c-marc")
    r = gratuit("pirate-email@example.org", "marc.banc@example.com")
    attendu("nommé comme l'e-mail d'un coach : URL conservée", "marc.banc@example.com", "c-marc")
    nouveau = db.coaches.find_one({"email": "pirate-nom@example.org"}, {"_id": 0, "id": 1})
    attendu("le nouveau compte reste joignable par son identifiant", nouveau["id"], nouveau["id"])

    print("\n── Compte non validé")
    r = requests.post(f"{BASE}/api/auth/register", json={"email": "attente.banc@example.org", "name": "Coach Libre Banc", "password": "motdepasse-banc-1"}, timeout=20)
    attendu("en attente : sa vitrine n'existe pas", "coach-libre-banc", None)
    db.coaches.insert_one(coach_doc("pending-marc@example.org", "c-pending", "Marc Lefevre Banc", actif=False, cree="2099-01-01T00:00:00+00:00"))
    attendu("en attente, même nom : ne bloque personne", "marc-lefevre-banc", "c-marc")
    r = gratuit("premier-libre@example.org", "Nom Neuf Banc")
    prem = db.coaches.find_one({"email": "premier-libre@example.org"}, {"_id": 0, "id": 1})
    db.coaches.update_one({"email": "marc.banc@example.com"}, {"$set": {"is_active": False}})
    attendu("coach désactivé : son URL par nom n'est pas réattribuée", "marc-lefevre-banc", None)
    db.coaches.update_one({"email": "marc.banc@example.com"}, {"$set": {"is_active": True}})
    attendu("réactivé : il la retrouve", "marc-lefevre-banc", "c-marc")

    print("\n── Deux nouveaux comptes au même nom : premier arrivé, le second par son identifiant")
    second = gratuit("second-libre@example.org", "Nom Neuf Banc")
    attendu("le premier garde l'URL par nom", "nom-neuf-banc", prem["id"])
    jet = jeton("second-libre@example.org")
    pr = requests.get(f"{BASE}/api/coach/profile", headers=porteur(jet), timeout=20).json()
    v("le tableau de bord du second lui donne un lien vers LUI", pr.get("vitrine_segment") == pr.get("id"), pr.get("vitrine_segment"))
    jp = jeton("premier-libre@example.org")
    pr = requests.get(f"{BASE}/api/coach/profile", headers=porteur(jp), timeout=20).json()
    v("celui du premier garde le lien lisible", pr.get("vitrine_segment") == "nom-neuf-banc", pr.get("vitrine_segment"))
    db.coaches.update_many({"email": "twin@example.org"}, {"$set": {"name": "Jumeau Deux"}})
    jm = jeton("twin@example.org")
    pr = requests.get(f"{BASE}/api/coach/profile", headers=porteur(jm), timeout=20).json()
    v("coach existant : son lien mène bien à lui", vitrine(pr.get("vitrine_segment"))[1] == "c-t2", pr.get("vitrine_segment"))

    print("\n── Plus de 20 correspondances")
    db.coaches.insert_one(coach_doc("foule@example.com", "c-foule", "Foule Banc"))
    db.coaches.insert_many([coach_doc(f"masse{i}.banc@example.org", f"c-m{i}", "Foule Banc", actif=True, cree=f"2026-11-04T10:{i % 60:02d}:00+00:00") for i in range(60)])
    attendu("60 nouveaux comptes au même nom : le coach existant garde son URL", "foule-banc", "c-foule")
    db.coaches.insert_many([coach_doc(f"foule.banc@example{i}.org", f"c-p{i}", f"Sans Rapport {i}", actif=True, cree=f"2026-11-04T11:{i % 60:02d}:00+00:00") for i in range(60)])
    attendu("60 nouveaux comptes au même début d'e-mail : URL par nom inchangée", "foule-banc", "c-foule")
    db.coaches.insert_many([coach_doc(f"inactif{i}.banc@example.org", f"c-i{i}", "Autre Foule Banc", actif=False, cree=f"2026-11-04T09:{i % 60:02d}:00+00:00") for i in range(60)])
    db.coaches.insert_one(coach_doc("vrai-autre.banc@example.org", "c-vrai", "Autre Foule Banc", cree="2026-11-04T12:00:00+00:00"))
    attendu("60 comptes en attente plus anciens : ne bloquent pas un coach actif", "autre-foule-banc", "c-vrai")
    db.coaches.insert_many([coach_doc(f"ancien{i}.banc@example.org", f"c-a{i}", "Foule Ancienne Banc") for i in range(25)])
    attendu("25 comptes existants au même nom : ambigu, refus", "foule-ancienne-banc", None)


def main():
    exiger_isolation()
    sauvegarde = db.concept.find_one({"id": "concept"})
    sauvegarde_liens = db.payment_links.find_one({"id": "payment_links"})
    nettoyer()
    semer()
    try:
        tester_refus()
        tester_acces_legitime()
        tester_quatre_failles()
        tester_routes_entete()
        tester_apercu_partage()
        tester_effacer_date_cours()
        nettoyer()
        tester_resolution()
    finally:
        nettoyer()
        if sauvegarde:
            db.concept.replace_one({"id": "concept"}, sauvegarde)
        if sauvegarde_liens:
            db.payment_links.replace_one({"id": "payment_links"}, sauvegarde_liens)
        else:
            db.payment_links.delete_one({"id": "payment_links"})
    ko = resultats.count(False)
    print(f"\n{len(resultats) - ko}/{len(resultats)} OK")
    sys.exit(1 if ko else 0)


if __name__ == "__main__":
    main()
