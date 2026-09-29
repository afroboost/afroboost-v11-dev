#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MT-3 — MATRICE DE SÉCURITÉ MULTI-TENANT (banc HTTP RÉEL, isolé, jetable).

CE QUE FAIT CE BANC
    1. Démarre un MongoDB LOCAL (127.0.0.1:27111) et l'API FastAPI LOCALE
       (127.0.0.1:8111) du dépôt ciblé — ou réutilise ceux fournis par
       variables d'environnement (MT_MONGO_URL + MT_API_URL + MT_DB_NAME).
    2. Crée 4 identités : SUPER-ADMIN (compte LOCAL portant l'adresse de la
       liste super-admin codée côté serveur — base jetable), COACH A, COACH B
       (@banc.test) et ANONYME. Jetons obtenus par POST /api/auth/login.
       Mots de passe aléatoires, gardés en mémoire, JAMAIS imprimés.
    3. Sème des données SÉPARÉES A / B (+ fiches « héritées » sans
       propriétaire, marque MTBANC-G) directement en base LOCALE (pymongo) :
       ainsi le jeu de données est identique avant et après correctif, et ne
       dépend pas du code testé. Les campagnes, elles, sont créées par la
       route normale POST /api/campaigns (déjà protégée par JWT).
    4. Exécute la matrice route × scénario et imprime le tableau, puis la
       ligne `N / M vérifications MT au vert`. Code de sortie 1 si rouge.
    5. ARRÊTE l'API et MongoDB et SUPPRIME la base, les journaux et le dossier
       temporaire (règle du propriétaire : nettoyage après chaque test), même
       en cas d'erreur ou d'interruption (Ctrl-C).

SCÉNARIOS
    A lit A = 200 | A lit B = 403/404 (listes : aucune donnée de B ni héritée)
    B lit A = 403/404 | A modifie A = OK | A modifie B = 403/404 + base intacte
    anonyme = 401/403 | X-User-Email A sans JWT = 401/403
    JWT B + X-User-Email A -> réponse de B, jamais de A
    SUPER-ADMIN -> accès global.

DESTINATAIRES DE CAMPAGNE
    Vérifiés par la route d'APERÇU `GET /api/campaigns/{id}/preview` (même
    résolution que le lancement, `ecrire=False`) : AUCUN lancement, AUCUN
    envoi — aucune clé d'envoi n'existe d'ailleurs dans l'environnement de
    l'API (lancée sous `env -i`).

USAGE
    python3 tests/test_mt_matrice_http.py [--repo CHEMIN]
    Variables facultatives : MT_SCRATCH (dossier temporaire), MT_MONGO_URL,
    MT_API_URL, MT_DB_NAME (réutiliser des serveurs déjà lancés — 127.0.0.1
    OBLIGATOIRE, le banc refuse tout autre hôte).

GARDE-FOUS
    - refuse de démarrer si MONGO_URL / l'API ne sont pas sur 127.0.0.1 ;
    - aucun appel à la production, aucune lecture de fichier .env ;
    - aucune donnée réelle : tout est marqué MTBANC et vit dans une base
      jetable supprimée à la fin.
"""
import argparse
import hashlib
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, quote

try:
    import requests
    from pymongo import MongoClient
except ImportError as _e:  # pragma: no cover
    print(f"Dépendance manquante : {_e} (pip install requests pymongo)")
    sys.exit(2)

SCRATCH_DEFAUT = ("/private/tmp/claude-501/-Users-afroboost-afroboost-v11-dev/"
                  "256653a6-1acc-4dfa-be6a-b798c1d20a8b/scratchpad/mt-matrice")
PORT_MONGO = 27111
PORT_API = 8111
TIMEOUT = 40

EMAIL_SA = "contact.artboost@gmail.com"   # liste super-admin codée côté serveur
EMAIL_A = "coach-a@banc.test"
EMAIL_B = "coach-b@banc.test"
EMAIL_COACH = {"a": EMAIL_A, "b": EMAIL_B}

# Marques de fuite (recherchées en minuscules dans les réponses).
MA, MB, MG = "mtbanc-a", "mtbanc-b", "mtbanc-g"

REFUS_AUTH = (401, 403)
REFUS_OBJET = (403, 404)

RESULTATS = []   # (route, scénario, code HTTP, ok, note)


# ═══════════════════════════ outillage ════════════════════════════════════════
def verifier(route, scenario, code, ok, note="", attendu=""):
    if not ok and not note and attendu:
        note = f"attendu {attendu}"
    RESULTATS.append((route, scenario, code, bool(ok), note))


def _hote_local(url):
    try:
        return urlparse(url).hostname == "127.0.0.1"
    except Exception:
        return False


def _port_occupe(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


class Rep:
    __slots__ = ("s", "t", "j")

    def __init__(self, s, t, j):
        self.s, self.t, self.j = s, t, j


class Banc:
    def __init__(self, repo, scratch):
        self.repo = repo
        self.scratch = scratch
        self.mongo_url = os.environ.get("MT_MONGO_URL", "").strip()
        self.api_url = os.environ.get("MT_API_URL", "").strip().rstrip("/")
        self.db_name = os.environ.get("MT_DB_NAME", "mt_banc").strip() or "mt_banc"
        self.externe = bool(self.mongo_url or self.api_url)
        self.proc_api = None
        self.pidfile = os.path.join(scratch, "mongod.pid")
        self.mongo_lance = False
        self.client = None
        self.db = None
        self._nettoye = False

    # ─── démarrage ────────────────────────────────────────────────────────────
    def demarrer(self):
        if self.externe:
            if not (self.mongo_url and self.api_url):
                raise SystemExit("MT_MONGO_URL ET MT_API_URL doivent être fournis ensemble.")
        else:
            self.mongo_url = f"mongodb://127.0.0.1:{PORT_MONGO}"
            self.api_url = f"http://127.0.0.1:{PORT_API}"
        # GARDE-FOU : jamais autre chose que 127.0.0.1.
        if not self.mongo_url.startswith("mongodb://") or not _hote_local(self.mongo_url):
            raise SystemExit(f"REFUS : MONGO_URL doit être mongodb://127.0.0.1:… (reçu : {self.mongo_url!r})")
        if not _hote_local(self.api_url):
            raise SystemExit(f"REFUS : l'API doit écouter sur 127.0.0.1 (reçu : {self.api_url!r})")
        if not self.db_name.startswith("mt_"):
            raise SystemExit("REFUS : MT_DB_NAME doit commencer par « mt_ » (base jetable).")

        if not self.externe:
            for p in (PORT_MONGO, PORT_API):
                if _port_occupe(p):
                    raise SystemExit(f"REFUS : le port {p} est déjà occupé (banc précédent non arrêté ?).")
            if os.path.exists(self.scratch):
                shutil.rmtree(self.scratch)
            os.makedirs(os.path.join(self.scratch, "db"))
            subprocess.run(
                ["mongod", "--dbpath", os.path.join(self.scratch, "db"), "--port", str(PORT_MONGO),
                 "--bind_ip", "127.0.0.1", "--fork", "--logpath", os.path.join(self.scratch, "mongod.log"),
                 "--pidfilepath", self.pidfile],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.mongo_lance = True

        self.client = MongoClient(self.mongo_url, serverSelectionTimeoutMS=15000)
        self.client.admin.command("ping")
        self.db = self.client[self.db_name]
        if self.db.list_collection_names():
            # Une base jetable « mt_ » déjà remplie = reste d'un banc interrompu.
            self.client.drop_database(self.db_name)

        if not self.externe:
            env = {
                "HOME": os.environ.get("HOME", "/tmp"),
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "MONGO_URL": self.mongo_url,
                "DB_NAME": self.db_name,
                "JWT_SECRET": secrets.token_hex(32),       # aléatoire, jamais imprimé
                "FRONTEND_URL": f"http://localhost:{PORT_API}",
            }
            self._log_api = open(os.path.join(self.scratch, "api.log"), "wb")
            self.proc_api = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "api.index:app", "--host", "127.0.0.1",
                 "--port", str(PORT_API)],
                cwd=self.repo, env=env, stdout=self._log_api, stderr=subprocess.STDOUT,
                start_new_session=True)
        t0 = time.time()
        while time.time() - t0 < 120:
            if self.proc_api is not None and self.proc_api.poll() is not None:
                break
            try:
                if requests.get(self.api_url + "/healthz", timeout=2).status_code == 200:
                    return
            except Exception:
                pass
            time.sleep(0.5)
        self._afficher_log_api()
        raise SystemExit("L'API locale n'a pas répondu sur /healthz.")

    def _afficher_log_api(self):
        chemin = os.path.join(self.scratch, "api.log")
        if os.path.exists(chemin):
            with open(chemin, "rb") as f:
                print("--- fin du journal API ---")
                print(f.read()[-3000:].decode("utf-8", "replace"))

    # ─── arrêt + suppression ─────────────────────────────────────────────────
    def nettoyer(self):
        if self._nettoye:
            return
        self._nettoye = True
        bilan = []
        if self.proc_api is not None:
            try:
                os.killpg(self.proc_api.pid, signal.SIGTERM)
                self.proc_api.wait(timeout=15)
            except Exception:
                try:
                    os.killpg(self.proc_api.pid, signal.SIGKILL)
                except Exception:
                    pass
            bilan.append("API arrêtée")
        try:
            if self.client is not None and self.db_name.startswith("mt_"):
                self.client.drop_database(self.db_name)
                bilan.append(f"base {self.db_name} supprimée")
        except Exception:
            pass
        try:
            if self.client is not None:
                self.client.close()
        except Exception:
            pass
        if self.mongo_lance:
            try:
                with open(self.pidfile) as f:
                    pid = int(f.read().strip())
                os.kill(pid, signal.SIGTERM)
                for _ in range(40):
                    try:
                        os.kill(pid, 0)
                        time.sleep(0.25)
                    except OSError:
                        break
                else:
                    os.kill(pid, signal.SIGKILL)
                bilan.append("MongoDB arrêté")
            except Exception as e:
                bilan.append(f"arrêt MongoDB incertain ({type(e).__name__})")
        if not self.externe and os.path.exists(self.scratch):
            try:
                if getattr(self, "_log_api", None):
                    self._log_api.close()
            except Exception:
                pass
            shutil.rmtree(self.scratch, ignore_errors=True)
            bilan.append("dossier temporaire (base, journaux) supprimé")
        restes = os.path.exists(self.scratch) if not self.externe else False
        ports = [p for p in (PORT_MONGO, PORT_API) if not self.externe and _port_occupe(p)]
        print("\nNETTOYAGE : " + " ; ".join(bilan)
              + (" — ⚠️ dossier encore présent" if restes else "")
              + (f" — ⚠️ ports encore occupés {ports}" if ports else " — vérifié : ports libres, rien ne reste"))

    # ─── HTTP ────────────────────────────────────────────────────────────────
    def appel(self, methode, chemin, entetes=None, corps=None):
        try:
            r = requests.request(methode, self.api_url + chemin, headers=entetes or {},
                                 json=corps, timeout=TIMEOUT)
            try:
                j = r.json()
            except Exception:
                j = None
            return Rep(r.status_code, (r.text or "").lower(), j)
        except Exception as e:
            return Rep(0, f"exception {type(e).__name__}", None)


# ═══════════════════════════ données du banc ═══════════════════════════════════
def _maintenant(decalage_jours=0):
    return (datetime.now(timezone.utc) + timedelta(days=decalage_jours)).isoformat()


def _hash_mdp(mdp):
    sel = secrets.token_hex(16)
    return f"{sel}:" + hashlib.pbkdf2_hmac("sha256", mdp.encode(), sel.encode(), 100000).hex()


def creer_comptes(db):
    mdp = {}
    for cle, email, nom in (("SA", EMAIL_SA, "Banc Super-Admin"), ("A", EMAIL_A, "Banc Coach A"),
                            ("B", EMAIL_B, "Banc Coach B")):
        mdp[cle] = secrets.token_urlsafe(24)
        db.users_auth.insert_one({"user_id": "mt-auth-" + cle.lower(), "email": email, "name": nom,
                                  "password_hash": _hash_mdp(mdp[cle]), "created_at": _maintenant()})
        if cle != "SA":
            db.coaches.insert_one({"id": "mt-coach-" + cle.lower(), "email": email, "name": nom,
                                   "credits": 500, "is_active": True, "created_at": _maintenant()})
    # État de PRODUCTION reproduit : X-User-Email ne suffit plus pour l'identité coach (V319).
    db.feature_flags.insert_one({"id": "feature_flags", "REQUIRE_COACH_JWT": True})
    return mdp


def _tel(x, n):
    return f"+41790{'1' if x == 'a' else '2'}0{n:02d}"


def semer_coach(db, x):
    """Portefeuille du coach x ('a' | 'b'). Marque MTBANC-X dans les noms et e-mails."""
    X = x.upper()
    m = f"MTBANC-{X}"
    e = lambda s: f"mtbanc-{x}-{s}@banc.test"
    coach = EMAIL_COACH[x]
    cps = [
        {"id": f"mt-cp-{x}1", "name": f"{m}-Contact1", "email": e("contact1"), "whatsapp": _tel(x, 1),
         "categories": [f"mt-cat-{x}"], "tags": []},
        {"id": f"mt-cp-{x}2", "name": f"{m}-Contact2", "email": e("contact2"), "whatsapp": _tel(x, 2),
         "categories": [], "tags": []},
    ]
    for c in cps:
        c.update({"coach_id": coach, "source": "banc", "created_at": _maintenant(-10),
                  "last_seen_at": _maintenant(-1)})
        db.chat_participants.insert_one(c)
    semer_doublons(db, x)
    db.users.insert_many([
        {"id": f"mt-user-{x}1", "name": f"{m}-User1", "email": e("user1"), "whatsapp": _tel(x, 11),
         "coach_id": coach, "createdAt": _maintenant(-20)},
        # Fiche SANS coach_id rattachée au coach par une RELATION (abonnement + code).
        {"id": f"mt-user-{x}2", "name": f"{m}-Abonne", "email": e("abonne"), "whatsapp": _tel(x, 12),
         "createdAt": _maintenant(-20)},
    ])
    db.reservations.insert_one({"id": f"mt-resa-{x}", "userEmail": e("user1"), "userName": f"{m}-User1",
                                "userWhatsapp": _tel(x, 11), "coach_id": coach, "courseId": f"mt-cours-{x}",
                                "courseName": f"{m}-Cours", "datetime": _maintenant(-5),
                                "createdAt": _maintenant(-6)})
    code = f"AFR-MT{X}001"
    db.subscriptions.insert_one({"id": f"mt-sub-{x}", "code": code, "email": e("abonne"), "name": f"{m}-Abonne",
                                 "whatsapp": _tel(x, 12), "status": "active", "coach_id": coach,
                                 "offer_name": "Banc 10 séances", "total_sessions": 10, "used_sessions": 5,
                                 "remaining_sessions": 5, "expires_at": _maintenant(60),
                                 "created_at": _maintenant(-30)})
    db.discount_codes.insert_one({"id": f"mt-dc-{x}", "code": code, "assignedEmail": e("abonne"),
                                  "name": f"{m}-Abonne", "active": True, "coach_id": coach,
                                  "maxUses": 10, "used": 5, "type": "100%", "value": 100})
    db.contact_categories.insert_one({"id": f"mt-cat-{x}", "coach_id": coach, "name": f"{m}-Categorie",
                                      "color": "#6B7280", "icon": "mt", "is_default": False, "order": 1,
                                      "created_at": _maintenant(-10)})
    db.leads.insert_one({"id": f"mt-lead-{x}", "firstName": f"{m}-Lead", "email": e("lead"),
                         "whatsapp": _tel(x, 21), "coach_id": coach, "source": "banc",
                         "createdAt": _maintenant(-3)})
    db.coaching_notes.insert_one({"id": f"mt-note-{x}", "target_type": "subscriber", "target_id": code,
                                  "text": f"{m}-Note", "author_id": coach, "author_role": "coach",
                                  "created_at": _maintenant(-2), "updated_at": _maintenant(-2)})
    db.chat_sessions.insert_one({"id": f"grp_mt{x}", "coach_id": coach, "title": f"{m}-Groupe",
                                 "name": f"{m}-Groupe", "mode": "community", "is_group": True,
                                 "participant_ids": [f"mt-cp-{x}1"], "is_deleted": False,
                                 "created_at": _maintenant(-10)})


def semer_doublons(db, x):
    """Deux fiches du coach x portant le même e-mail (cible de /contacts/deduplicate)."""
    X = x.upper()
    db.chat_participants.delete_many({"email": f"mtbanc-{x}-doublon@banc.test"})
    for i, jours in ((1, -9), (2, -8)):
        db.chat_participants.insert_one({
            "id": f"mt-cp-{x}-dup{i}", "name": f"MTBANC-{X}-Doublon{i}", "email": f"mtbanc-{x}-doublon@banc.test",
            "whatsapp": "", "coach_id": EMAIL_COACH[x], "source": "banc", "tags": [], "categories": [],
            "created_at": _maintenant(jours)})


def semer_herites(db):
    """Fiches HÉRITÉES sans propriétaire : visibles du seul super-admin (fail-closed)."""
    db.users.insert_one({"id": "mt-user-g1", "name": "MTBANC-G-Herite", "email": "mtbanc-g-herite@banc.test",
                         "whatsapp": "+41790300001", "createdAt": _maintenant(-40)})
    db.chat_participants.insert_one({"id": "mt-cp-g1", "name": "MTBANC-G-Herite2",
                                     "email": "mtbanc-g-herite2@banc.test", "whatsapp": "+41790300002",
                                     "source": "banc", "tags": [], "categories": [],
                                     "created_at": _maintenant(-40)})


# ═══════════════════════════ la matrice ═══════════════════════════════════════
class Matrice:
    def __init__(self, banc, jetons):
        self.b = banc
        self.db = banc.db
        self.hA = {"Authorization": "Bearer " + jetons["A"]}
        self.hB = {"Authorization": "Bearer " + jetons["B"]}
        self.hSA = {"Authorization": "Bearer " + jetons["SA"]}
        self.ANON = {}
        self.SPOOF_A = {"X-User-Email": EMAIL_A}
        self.MIXTE = {"Authorization": "Bearer " + jetons["B"], "X-User-Email": EMAIL_A}
        self.camp = {}   # campagne principale de chaque coach
        self._n = 0

    def c(self, m, p, h=None, corps=None):
        return self.b.appel(m, p, h, corps)

    def uid(self):
        self._n += 1
        return f"{self._n:03d}"

    @staticmethod
    def fuites(t, marques):
        return [m for m in marques if m in t]

    # ─── patrons génériques ──────────────────────────────────────────────────
    def lecture_liste(self, route, methode, chemin, corps=None, sa=True):
        r = self.c(methode, chemin, self.hA, corps)
        verifier(route, "A lit A", r.s, r.s == 200 and MA in r.t, "" if MA in r.t else "données de A absentes")
        f = self.fuites(r.t, (MB, MG))
        verifier(route, "A lit B (+hérités)", r.s, r.s != 500 and not f, f"fuite {f}" if f else "")
        r = self.c(methode, chemin, self.hB, corps)
        f = self.fuites(r.t, (MA, MG))
        verifier(route, "B lit A (+hérités)", r.s, r.s != 500 and not f, f"fuite {f}" if f else "")
        r = self.c(methode, chemin, self.ANON, corps)
        f = self.fuites(r.t, (MA, MB, MG))
        verifier(route, "anonyme", r.s, r.s in REFUS_AUTH and not f, f"fuite {f}" if f else "", "401/403")
        r = self.c(methode, chemin, self.SPOOF_A, corps)
        f = self.fuites(r.t, (MA,))
        verifier(route, "X-User-Email A sans JWT", r.s, r.s in REFUS_AUTH and not f, f"fuite {f}" if f else "",
                 "401/403")
        r = self.c(methode, chemin, self.MIXTE, corps)
        f = self.fuites(r.t, (MA,))
        verifier(route, "JWT B + X-User-Email A", r.s, r.s == 200 and not f and MB in r.t,
                 f"données de A présentes {f}" if f else ("" if MB in r.t else "réponse sans les données de B"),
                 "200 (vue de B)")
        if sa:
            r = self.c(methode, chemin, self.hSA, corps)
            verifier(route, "SUPER-ADMIN global", r.s, r.s == 200 and MA in r.t and MB in r.t,
                     "" if (MA in r.t and MB in r.t) else "vue non globale")

    def lecture_id(self, route, gabarit, id_a, id_b, sa=True):
        pa, pb = gabarit.format(quote(id_a, safe="")), gabarit.format(quote(id_b, safe=""))
        r = self.c("GET", pa, self.hA)
        verifier(route, "A lit A", r.s, r.s == 200 and MA in r.t, "", "200 + données de A")
        r = self.c("GET", pb, self.hA)
        verifier(route, "A lit B", r.s, r.s in REFUS_OBJET and MB not in r.t,
                 "fuite données B" if MB in r.t else "", "403/404")
        r = self.c("GET", pa, self.hB)
        verifier(route, "B lit A", r.s, r.s in REFUS_OBJET and MA not in r.t,
                 "fuite données A" if MA in r.t else "", "403/404")
        r = self.c("GET", pa, self.ANON)
        verifier(route, "anonyme", r.s, r.s in REFUS_AUTH and MA not in r.t,
                 "fuite données A" if MA in r.t else "", "401/403")
        r = self.c("GET", pa, self.SPOOF_A)
        verifier(route, "X-User-Email A sans JWT", r.s, r.s in REFUS_AUTH and MA not in r.t,
                 "fuite données A" if MA in r.t else "", "401/403")
        r = self.c("GET", pa, self.MIXTE)
        verifier(route, "JWT B + X-User-Email A", r.s, r.s in REFUS_OBJET and MA not in r.t,
                 "réponse de A" if MA in r.t else "", "403/404")
        if sa:
            r = self.c("GET", pb, self.hSA)
            verifier(route, "SUPER-ADMIN global", r.s, r.s == 200 and MB in r.t, "", "200 + données de B")

    SCEN_MUTATION = (
        ("A modifie A", "hA", "a", "ok"),
        ("A modifie B", "hA", "b", "objet"),
        ("anonyme", "ANON", "a", "auth"),
        ("X-User-Email A sans JWT", "SPOOF_A", "a", "auth"),
        ("JWT B + X-User-Email A", "MIXTE", "a", "mixte"),
        ("SUPER-ADMIN global", "hSA", "b", "ok"),
    )

    def mutation(self, route, methode, gabarit, fabrique, etat, corps_fn, scenarios=None):
        """fabrique(x) -> id d'une ressource FRAÎCHE du coach x ; etat(id) -> instantané base ;
        corps_fn(id) -> corps JSON. « modifie » = l'instantané a changé."""
        for nom, cle_h, x, attendu in (scenarios or self.SCEN_MUTATION):
            rid = fabrique(x)
            avant = etat(rid)
            r = self.c(methode, gabarit.format(quote(rid, safe="")), getattr(self, cle_h), corps_fn(rid))
            change = etat(rid) != avant
            if attendu == "ok":
                ok, note = r.s == 200 and change, "" if change else "aucun effet en base"
            elif attendu == "objet":
                ok, note = r.s in REFUS_OBJET and not change, "MODIFIÉ en base" if change else ""
            elif attendu == "auth":
                ok, note = r.s in REFUS_AUTH and not change, "MODIFIÉ en base" if change else ""
            else:  # mixte : la ressource de A ne doit jamais être touchée au nom de A
                ok, note = r.s in (401, 403, 404) and not change, "MODIFIÉ en base" if change else ""
            verifier(route, nom, r.s, ok, note,
                     {"ok": "200 + effet", "objet": "403/404", "auth": "401/403", "mixte": "401/403/404"}[attendu])

    # ─── helpers base ────────────────────────────────────────────────────────
    def doc(self, coll, filtre, champ=None):
        d = self.db[coll].find_one(filtre, {"_id": 0})
        if champ is None:
            return d
        return None if d is None else json.dumps(d.get(champ), sort_keys=True, default=str)

    def credits(self, x):
        return (self.db.coaches.find_one({"email": EMAIL_COACH[x]}) or {}).get("credits")

    # ═══════════════════════════ CAMPAGNES ═══════════════════════════════════
    def creer_campagne(self, x, h, nom, **extra):
        corps = {"name": nom, "message": f"Message {nom}", "targetType": "all", "channels": {"email": True}}
        corps.update(extra)
        r = self.c("POST", "/api/campaigns", h, corps)
        return r, ((r.j or {}).get("id") if isinstance(r.j, dict) else None)

    def semer_campagnes(self):
        for x, h in (("a", self.hA), ("b", self.hB)):
            r, cid = self.creer_campagne(x, h, f"MTBANC-{x.upper()}-Campagne")
            if not cid:   # repli : insertion directe (le banc ne doit pas dépendre de cette route)
                cid = f"mt-camp-{x}"
                self.db.campaigns.insert_one({"id": cid, "name": f"MTBANC-{x.upper()}-Campagne",
                                              "message": "m", "status": "draft", "targetType": "all",
                                              "channels": {"email": True}, "coach_id": EMAIL_COACH[x],
                                              "createdAt": _maintenant()})
            self.db.campaigns.update_one({"id": cid}, {"$set": {"results": [
                {"contactId": f"mt-cp-{x}1", "contactName": f"MTBANC-{x.upper()}-Contact1",
                 "channel": "email", "status": "pending"}]}})
            self.camp[x] = cid

    def campagnes(self):
        self.lecture_liste("GET /api/campaigns", "GET", "/api/campaigns")
        self.lecture_liste("GET /api/campaigns-list", "GET", "/api/campaigns-list")
        self.lecture_id("GET /api/campaigns/{id}", "/api/campaigns/{}", self.camp["a"], self.camp["b"])
        self.lecture_id("GET /api/campaign-debug/{id}", "/api/campaign-debug/{}", self.camp["a"], self.camp["b"])
        self.lecture_id("GET /api/campaigns/{id}/preview", "/api/campaigns/{}/preview",
                        self.camp["a"], self.camp["b"])

        # PUT : le message change (jamais le nom : il porte la marque).
        def fab_put(x):
            self.db.campaigns.update_one({"id": self.camp[x]}, {"$set": {"message": "origine"}})
            return self.camp[x]
        self.mutation("PUT /api/campaigns/{id}", "PUT", "/api/campaigns/{}", fab_put,
                      lambda i: self.doc("campaigns", {"id": i}, "message"),
                      lambda i: {"message": "modifie-" + self.uid()})

        # mark-sent : le résultat repasse « pending » avant chaque scénario.
        def fab_ms(x):
            self.db.campaigns.update_one({"id": self.camp[x]}, {"$set": {
                "status": "draft", "results": [{"contactId": f"mt-cp-{x}1", "channel": "email",
                                                "contactName": f"MTBANC-{x.upper()}-Contact1",
                                                "status": "pending"}]}})
            return self.camp[x]
        self.mutation("POST /api/campaigns/{id}/mark-sent", "POST", "/api/campaigns/{}/mark-sent", fab_ms,
                      lambda i: self.doc("campaigns", {"id": i}, "results"),
                      lambda i: {"contactId": (self.doc("campaigns", {"id": i}) or {}).get("results", [{}])[0].get("contactId"),
                                 "channel": "email"})

        # DELETE : une campagne jetable fraîche par scénario.
        def fab_del(x):
            cid = f"mt-camp-{x}-jetable-{self.uid()}"
            self.db.campaigns.insert_one({"id": cid, "name": f"MTBANC-{x.upper()}-Jetable", "message": "m",
                                          "status": "draft", "targetType": "all", "channels": {"email": True},
                                          "coach_id": EMAIL_COACH[x], "createdAt": _maintenant()})
            return cid
        self.mutation("DELETE /api/campaigns/{id}", "DELETE", "/api/campaigns/{}", fab_del,
                      lambda i: self.db.campaigns.count_documents({"id": i}), lambda i: None)

        self.send_email()

    def send_email(self):
        route = "POST /api/campaigns/send-email"
        corps = {"to_email": "destinataire@banc.test", "to_name": "Banc", "subject": "banc", "message": "banc"}
        r = self.c("POST", "/api/campaigns/send-email", self.ANON, corps)
        verifier(route, "anonyme", r.s, r.s in REFUS_AUTH)
        a0 = self.credits("a")
        r = self.c("POST", "/api/campaigns/send-email", self.SPOOF_A, corps)
        verifier(route, "X-User-Email A sans JWT", r.s, r.s in REFUS_AUTH and self.credits("a") == a0,
                 "" if self.credits("a") == a0 else "A DÉBITÉ")
        r = self.c("POST", "/api/campaigns/send-email", self.hA, corps)
        verifier(route, "A autorisé (JWT, sans clé Resend)", r.s, r.s == 200)
        b0 = self.credits("b")
        r = self.c("POST", "/api/campaigns/send-email", dict(self.hA, **{"X-User-Email": EMAIL_B}), corps)
        verifier(route, "JWT A + X-User-Email B : aucun débit de B", r.s,
                 r.s != 500 and self.credits("b") == b0,
                 f"crédits B {b0} -> {self.credits('b')}" if self.credits("b") != b0 else "")
        a0 = self.credits("a")
        r = self.c("POST", "/api/campaigns/send-email", self.MIXTE, corps)
        verifier(route, "JWT B + X-User-Email A : aucun débit de A", r.s,
                 r.s != 500 and self.credits("a") == a0,
                 f"crédits A {a0} -> {self.credits('a')}" if self.credits("a") != a0 else "")
        r = self.c("POST", "/api/campaigns/send-email", self.hSA, corps)
        verifier(route, "SUPER-ADMIN autorisé", r.s, r.s == 200)

    # ═══════════════════════════ DESTINATAIRES ══════════════════════════════
    def _noms_apercu(self, cid, h):
        r = self.c("GET", f"/api/campaigns/{quote(cid, safe='')}/preview", h)
        noms = []
        if isinstance(r.j, dict):
            for bloc in (r.j, r.j.get("whatsapp") or {}):
                for ligne in (bloc.get("liste") or []):
                    noms.append(str(ligne.get("nom") or "").lower())
        return r, noms

    def destinataires(self):
        route = "DESTINATAIRES (aperçu /preview)"
        tous_segments = ["whatsapp", "email", "abonne_actif", "essai_gratuit", "abonnement_expire", "visiteur",
                         "demarchable_whatsapp", "comptes_app", "a_completer", "interne_test",
                         "essai_non_converti", "essai_presence_inconnue", "essai_non_reserve",
                         "ancien_participant", "ancien_abonne", "recent_non_abonne"]
        cas = [
            ("A « tous » -> uniquement A", {"targetType": "all"}, True),
            ("A targetIds avec contacts de B", {"targetType": "selected",
                                               "targetIds": ["mt-cp-a1", "mt-cp-b1", "mt-user-b1", "mt-user-g1"]}, True),
            ("A segments (tous les segments)", {"targetType": "all", "targetCategories": tous_segments}, False),
            ("A catégorie de B", {"targetType": "selected", "targetCategories": ["mt-cat-b"]}, False),
            ("A sélection manuelle de B", {"targetType": "selected", "selectedContacts": ["mt-cp-b2", "mt-user-b1"]}, False),
            ("A groupe de B", {"targetType": "selected", "targetIds": ["grp_mtb"]}, False),
        ]
        for nom, extra, exiger_a in cas:
            r0, cid = self.creer_campagne("a", self.hA, f"MTBANC-A-Dest-{self.uid()}", **extra)
            if r0.s in (400, 403, 422) and not cid:
                verifier(route, nom, r0.s, True, "refusé à la création")
                continue
            if not cid:
                verifier(route, nom, r0.s, False, "création impossible")
                continue
            r, noms = self._noms_apercu(cid, self.hA)
            etrangers = [n for n in noms if MB in n or MG in n]
            a_present = any(MA in n for n in noms)
            ok = r.s == 200 and not etrangers and (a_present or not exiger_a)
            note = (f"{len(etrangers)} destinataire(s) de B/hérités : {etrangers[:3]}" if etrangers
                    else ("" if (a_present or not exiger_a) else "aucun contact de A"))
            verifier(route, nom, r.s, ok, note)
        # Contrôle positif : le groupe de A est bien déplié pour A.
        _, cid = self.creer_campagne("a", self.hA, f"MTBANC-A-Dest-{self.uid()}", targetType="selected",
                                     targetIds=["grp_mta"])
        r, noms = self._noms_apercu(cid, self.hA) if cid else (Rep(0, "", None), [])
        verifier(route, "A groupe de A (contrôle positif)", r.s,
                 r.s == 200 and any(MA in n for n in noms) and not any(MB in n for n in noms))
        # Super-admin « tous » -> global.
        _, cid = self.creer_campagne("sa", self.hSA, f"MTBANC-SA-Dest-{self.uid()}", targetType="all")
        r, noms = self._noms_apercu(cid, self.hSA) if cid else (Rep(0, "", None), [])
        verifier(route, "SUPER-ADMIN « tous » -> global", r.s,
                 r.s == 200 and any(MA in n for n in noms) and any(MB in n for n in noms))

    # ═══════════════════════════ PURGE (fin des campagnes) ══════════════════
    def purge(self):
        route = "DELETE /api/campaigns/purge/all"

        def brouillon(x):
            cid = f"mt-camp-{x}-purge-{self.uid()}"
            self.db.campaigns.insert_one({"id": cid, "name": f"MTBANC-{x.upper()}-Purge", "status": "draft",
                                          "coach_id": EMAIL_COACH[x], "message": "m", "createdAt": _maintenant()})
            return cid
        n = lambda x: self.db.campaigns.count_documents({"coach_id": EMAIL_COACH[x], "status": "draft"})
        brouillon("a"); brouillon("b")
        a0, b0 = n("a"), n("b")
        r = self.c("DELETE", "/api/campaigns/purge/all", self.ANON)
        verifier(route, "anonyme", r.s, r.s in REFUS_AUTH and n("a") == a0 and n("b") == b0)
        r = self.c("DELETE", "/api/campaigns/purge/all", self.SPOOF_A)
        verifier(route, "X-User-Email A sans JWT", r.s, r.s in REFUS_AUTH and n("a") == a0,
                 "" if n("a") == a0 else "brouillons de A SUPPRIMÉS")
        b0 = n("b")
        r = self.c("DELETE", "/api/campaigns/purge/all", self.hA)
        verifier(route, "A modifie A (ses brouillons)", r.s, r.s == 200 and n("a") == 0)
        verifier(route, "A supprime B (brouillons de B intacts)", r.s, n("b") == b0,
                 "" if n("b") == b0 else f"B {b0} -> {n('b')}")
        brouillon("a")
        a0 = n("a")
        r = self.c("DELETE", "/api/campaigns/purge/all", self.MIXTE)
        verifier(route, "JWT B + X-User-Email A : A intact", r.s, r.s != 500 and n("a") == a0,
                 "" if n("a") == a0 else "brouillons de A SUPPRIMÉS")
        brouillon("a"); brouillon("b")
        r = self.c("DELETE", "/api/campaigns/purge/all", self.hSA)
        verifier(route, "SUPER-ADMIN global", r.s, r.s == 200 and n("a") == 0 and n("b") == 0)

    # ═══════════════════════════ CONTACTS — lectures ════════════════════════
    def contacts_lectures(self):
        self.lecture_liste("GET /api/chat/participants", "GET", "/api/chat/participants")
        self.lecture_id("GET /api/chat/participants/{id}", "/api/chat/participants/{}", "mt-cp-a1", "mt-cp-b1")
        self.lecture_liste("GET /api/contacts/all", "GET", "/api/contacts/all")
        self.check_duplicates()
        self.lecture_liste("GET /api/contact-categories", "GET", "/api/contact-categories", sa=False)
        self.lecture_liste("GET /api/contact-categories/stats", "GET", "/api/contact-categories/stats", sa=False)
        self.filter_by_categories()
        self.segments()
        self.lecture_id("GET /api/users/{id}", "/api/users/{}", "mt-user-a1", "mt-user-b1")
        r = self.c("GET", "/api/users/mt-user-a2", self.hA)
        verifier("GET /api/users/{id}", "A lit A (fiche liée par relation)", r.s, r.s == 200 and MA in r.t)
        r = self.c("GET", "/api/users/mt-user-g1", self.hA)
        verifier("GET /api/users/{id}", "A lit hérité (sans propriétaire)", r.s,
                 r.s in REFUS_OBJET and MG not in r.t)
        self.profil_lecture()
        self.lecture_liste("GET /api/leads", "GET", "/api/leads")
        self.lecture_id("GET /api/subscriber/by-email/{email}/space-link", "/api/subscriber/by-email/{}/space-link",
                        "mtbanc-a-abonne@banc.test", "mtbanc-b-abonne@banc.test")
        self.lecture_id("GET /api/notes/subscriber/{code}", "/api/notes/subscriber/{}", "AFR-MTA001", "AFR-MTB001")
        self.lecture_liste("GET /api/progress/coach/subscribers", "GET", "/api/progress/coach/subscribers")

    def check_duplicates(self):
        route = "POST /api/contacts/check-duplicates"
        corps = {"emails": ["mtbanc-a-contact1@banc.test", "mtbanc-b-contact1@banc.test"], "phones": []}
        self.lecture_liste(route, "POST", "/api/contacts/check-duplicates", corps)

    def filter_by_categories(self):
        route = "POST /api/contacts/filter-by-categories"
        p = "/api/contacts/filter-by-categories"
        ca, cb = {"category_ids": ["mt-cat-a"]}, {"category_ids": ["mt-cat-b"]}
        r = self.c("POST", p, self.hA, ca)
        verifier(route, "A lit A", r.s, r.s == 200 and MA in r.t)
        r = self.c("POST", p, self.hA, cb)
        verifier(route, "A lit B (catégorie de B)", r.s, r.s != 500 and MB not in r.t)
        r = self.c("POST", p, self.hB, ca)
        verifier(route, "B lit A (catégorie de A)", r.s, r.s != 500 and MA not in r.t)
        r = self.c("POST", p, self.ANON, ca)
        verifier(route, "anonyme", r.s, r.s in REFUS_AUTH and MA not in r.t)
        r = self.c("POST", p, self.SPOOF_A, ca)
        verifier(route, "X-User-Email A sans JWT", r.s, r.s in REFUS_AUTH and MA not in r.t)
        r = self.c("POST", p, self.MIXTE, ca)
        verifier(route, "JWT B + X-User-Email A", r.s, r.s != 500 and MA not in r.t)

    def segments(self):
        route = "GET /api/contacts/segments"
        ra = self.c("GET", "/api/contacts/segments", self.hA)
        rs = self.c("GET", "/api/contacts/segments", self.hSA)
        pa = (ra.j or {}).get("personnes") if isinstance(ra.j, dict) else None
        ps = (rs.j or {}).get("personnes") if isinstance(rs.j, dict) else None
        verifier(route, "A lit A", ra.s, ra.s == 200 and isinstance(pa, int) and pa > 0)
        verifier(route, "A lit B (comptes ≠ vue globale)", ra.s,
                 isinstance(pa, int) and isinstance(ps, int) and pa < ps, f"A={pa} global={ps}")
        for nom, h in (("anonyme", self.ANON), ("X-User-Email A sans JWT", self.SPOOF_A)):
            r = self.c("GET", "/api/contacts/segments", h)
            verifier(route, nom, r.s, r.s in REFUS_AUTH)
        verifier(route, "SUPER-ADMIN global", rs.s, rs.s == 200 and isinstance(ps, int) and ps > 0)

        route = "GET /api/contacts/segment/{cle}"
        cles = ["whatsapp", "email", "abonne_actif", "essai_gratuit", "abonnement_expire", "visiteur",
                "demarchable_whatsapp", "comptes_app", "a_completer", "interne_test", "essai_non_converti",
                "essai_presence_inconnue", "essai_non_reserve", "ancien_participant", "ancien_abonne",
                "recent_non_abonne"]

        def union(h):
            ids, codes = set(), set()
            for k in cles:
                r = self.c("GET", f"/api/contacts/segment/{k}", h)
                codes.add(r.s)
                if isinstance(r.j, dict):
                    ids.update(str(c.get("id") or "") for c in (r.j.get("contacts") or []))
            return ids, codes
        ia, ca = union(self.hA)
        verifier(route, "A lit A", sorted(ca), ca == {200} and any(i.startswith("mt-") and "-a" in i for i in ia))
        etr = sorted(i for i in ia if i.startswith(("mt-cp-b", "mt-user-b", "mt-lead-b", "mt-cp-g", "mt-user-g")))
        verifier(route, "A lit B (+hérités)", sorted(ca), 500 not in ca and not etr, f"ids étrangers {etr[:4]}" if etr else "")
        ib, cb = union(self.hB)
        etr = sorted(i for i in ib if i.startswith(("mt-cp-a", "mt-user-a", "mt-lead-a")))
        verifier(route, "B lit A", sorted(cb), 500 not in cb and not etr, f"ids de A {etr[:4]}" if etr else "")
        for nom, h in (("anonyme", self.ANON), ("X-User-Email A sans JWT", self.SPOOF_A)):
            r = self.c("GET", "/api/contacts/segment/email", h)
            verifier(route, nom, r.s, r.s in REFUS_AUTH and "mt-" not in r.t)
        isa, csa = union(self.hSA)
        verifier(route, "SUPER-ADMIN global", sorted(csa),
                 any(i.startswith("mt-cp-a") or i.startswith("mt-user-a") for i in isa)
                 and any(i.startswith("mt-cp-b") or i.startswith("mt-user-b") for i in isa))

    def profil_lecture(self):
        route = "GET /api/users/{id}/profile"
        pa, pb = "/api/users/mt-user-a1/profile", "/api/users/mt-user-b1/profile"
        ea, eb = "mtbanc-a-user1@banc.test", "mtbanc-b-user1@banc.test"
        r = self.c("GET", pa, self.hA)
        verifier(route, "A lit A", r.s, r.s == 200 and MA in r.t)
        r = self.c("GET", pb, self.hA)
        verifier(route, "A lit B (aucune coordonnée de B)", r.s, r.s != 500 and eb not in r.t,
                 "e-mail de B exposé" if eb in r.t else "")
        r = self.c("GET", pa, self.hB)
        verifier(route, "B lit A (aucune coordonnée de A)", r.s, r.s != 500 and ea not in r.t,
                 "e-mail de A exposé" if ea in r.t else "")
        r = self.c("GET", pa, self.ANON)
        verifier(route, "anonyme (aucune coordonnée)", r.s, r.s != 500 and ea not in r.t,
                 "e-mail exposé à un anonyme" if ea in r.t else "")
        r = self.c("GET", pa, self.SPOOF_A)
        verifier(route, "X-User-Email A sans JWT (aucune coordonnée)", r.s, r.s != 500 and ea not in r.t,
                 "e-mail exposé" if ea in r.t else "")
        r = self.c("GET", pa, self.MIXTE)
        verifier(route, "JWT B + X-User-Email A (aucune coordonnée de A)", r.s, r.s != 500 and ea not in r.t,
                 "e-mail de A exposé" if ea in r.t else "")
        r = self.c("GET", pb, self.hSA)
        verifier(route, "SUPER-ADMIN global", r.s, r.s == 200 and MB in r.t)

    # ═══════════════════════════ CONTACTS — écritures ═══════════════════════
    def contacts_ecritures(self):
        self.participants_creation()

        def fab_cp2(x):
            self.db.chat_participants.update_one({"id": f"mt-cp-{x}2"},
                                                 {"$unset": {"mt_marque": "", "contact_type": ""},
                                                  "$set": {"tags": [], "categories": []}})
            return f"mt-cp-{x}2"
        self.mutation("PUT /api/chat/participants/{id}", "PUT", "/api/chat/participants/{}", fab_cp2,
                      lambda i: self.doc("chat_participants", {"id": i}, "mt_marque"),
                      lambda i: {"mt_marque": "modifie-" + self.uid()})

        def fab_cp_jet(x):
            i = f"mt-cp-{x}-jetable-{self.uid()}"
            self.db.chat_participants.insert_one({"id": i, "name": f"MTBANC-{x.upper()}-Jetable",
                                                  "email": f"mtbanc-{x}-jetable-{i[-3:]}@banc.test",
                                                  "coach_id": EMAIL_COACH[x], "source": "banc",
                                                  "created_at": _maintenant()})
            return i
        self.mutation("DELETE /api/chat/participants/{id}", "DELETE", "/api/chat/participants/{}", fab_cp_jet,
                      lambda i: self.db.chat_participants.count_documents({"id": i}), lambda i: None)

        self.mutation("PUT /api/contacts/{id}/type", "PUT", "/api/contacts/{}/type", fab_cp2,
                      lambda i: self.doc("chat_participants", {"id": i}, "contact_type"),
                      lambda i: {"contact_type": "prospect"})

        self.mutation("POST /api/contacts/add-tags", "POST", "/api/contacts/add-tags", fab_cp2,
                      lambda i: self.doc("chat_participants", {"id": i}, "tags"),
                      lambda i: {"contact_ids": [i], "tags": ["mt-tag-" + self.uid()]})

        self.mutation("POST /api/contacts/set-categories", "POST", "/api/contacts/set-categories", fab_cp2,
                      lambda i: self.doc("chat_participants", {"id": i}, "categories"),
                      # catégorie DU PROPRIÉTAIRE de la fiche (mt-cp-x2 -> mt-cat-x) : seul l'appelant change.
                      lambda i: {"contact_ids": [i], "category_ids": ["mt-cat-" + i.split("-")[2][0]], "mode": "add"})
        # Copie d'une fiche `users` de B dans le CRM de A (V154b) ?
        route = "POST /api/contacts/set-categories"
        self.db.chat_participants.delete_many({"id": "mt-user-b1"})
        r = self.c("POST", "/api/contacts/set-categories", self.hA,
                   {"contact_ids": ["mt-user-b1"], "category_ids": ["mt-cat-a"], "mode": "add"})
        copie = self.db.chat_participants.find_one({"id": "mt-user-b1"}, {"_id": 0, "coach_id": 1})
        verifier(route, "A importe une fiche users de B", r.s, r.s != 500 and not copie,
                 f"fiche de B COPIÉE chez {copie.get('coach_id')}" if copie else "")
        self.db.chat_participants.delete_many({"id": "mt-user-b1"})

        def fab_cat(x):
            self.db.contact_categories.update_one({"id": f"mt-cat-{x}"}, {"$set": {"icon": "mt"}})
            return f"mt-cat-{x}"
        self.mutation("PUT /api/contact-categories/{id}", "PUT", "/api/contact-categories/{}", fab_cat,
                      lambda i: self.doc("contact_categories", {"id": i}, "icon"),
                      lambda i: {"icon": "mt-" + self.uid()})

        def fab_cat_jet(x):
            i = f"mt-cat-{x}-jetable-{self.uid()}"
            self.db.contact_categories.insert_one({"id": i, "coach_id": EMAIL_COACH[x],
                                                   "name": f"MTBANC-{x.upper()}-CatJetable-{i[-3:]}",
                                                   "color": "#6B7280", "icon": "mt", "order": 9})
            self.db.chat_participants.update_one({"id": f"mt-cp-{x}1"}, {"$addToSet": {"categories": i}})
            return i
        self.mutation("DELETE /api/contact-categories/{id}", "DELETE", "/api/contact-categories/{}", fab_cat_jet,
                      lambda i: (self.db.contact_categories.count_documents({"id": i}),
                                 self.db.chat_participants.count_documents({"categories": i})),
                      lambda i: None)

        def fab_user(x):
            self.db.users.update_one({"id": f"mt-user-{x}1"}, {"$set": {"whatsapp": _tel(x, 11)}})
            return f"mt-user-{x}1"

        def corps_user(i):
            d = self.doc("users", {"id": i}) or {}
            return {"name": d.get("name", ""), "email": d.get("email", ""), "whatsapp": "+4179099" + self.uid()}
        self.mutation("PUT /api/users/{id}", "PUT", "/api/users/{}", fab_user,
                      lambda i: self.doc("users", {"id": i}, "whatsapp"), corps_user)

        def fab_user_jet(x):
            i = f"mt-user-{x}-jetable-{self.uid()}"
            self.db.users.insert_one({"id": i, "name": f"MTBANC-{x.upper()}-UserJetable",
                                      "email": f"mtbanc-{x}-userjet-{i[-3:]}@banc.test",
                                      "coach_id": EMAIL_COACH[x], "createdAt": _maintenant()})
            return i
        self.mutation("DELETE /api/users/{id}", "DELETE", "/api/users/{}", fab_user_jet,
                      lambda i: self.db.users.count_documents({"id": i}), lambda i: None)

        def fab_profil(x):
            self.db.users.update_one({"id": f"mt-user-{x}1"}, {"$unset": {"bio": ""}})
            return f"mt-user-{x}1"
        self.mutation("PATCH /api/users/{id}/profile", "PATCH", "/api/users/{}/profile", fab_profil,
                      lambda i: self.doc("users", {"id": i}, "bio"),
                      lambda i: {"bio": "mt-bio-" + self.uid()},
                      scenarios=[s for s in self.SCEN_MUTATION if s[0] != "A modifie A"])

        def fab_lead_jet(x):
            i = f"mt-lead-{x}-jetable-{self.uid()}"
            self.db.leads.insert_one({"id": i, "firstName": f"MTBANC-{x.upper()}-LeadJetable",
                                      "email": f"mtbanc-{x}-leadjet-{i[-3:]}@banc.test",
                                      "whatsapp": "+4179077" + i[-3:], "coach_id": EMAIL_COACH[x],
                                      "createdAt": _maintenant()})
            return i
        self.mutation("DELETE /api/leads/{id}", "DELETE", "/api/leads/{}", fab_lead_jet,
                      lambda i: self.db.leads.count_documents({"id": i}), lambda i: None)

        def fab_note(x):
            code = f"AFR-MT{x.upper()}001"
            self.db.coaching_notes.update_one({"target_type": "subscriber", "target_id": code},
                                              {"$set": {"text": f"MTBANC-{x.upper()}-Note"}})
            return code
        self.mutation("POST /api/notes", "POST", "/api/notes", fab_note,
                      lambda i: self.doc("coaching_notes", {"target_type": "subscriber", "target_id": i}, "text"),
                      lambda i: {"target_type": "subscriber", "target_id": i, "text": "mt-modif-" + self.uid()})

        self.bulk_import()
        self.deduplicate()

    def participants_creation(self):
        route = "POST /api/chat/participants"
        p = "/api/chat/participants"

        def creer(h, etiquette):
            email = f"mtbanc-n-{etiquette}-{self.uid()}@banc.test"
            r = self.c("POST", p, h, {"name": f"MTBANC-N-{etiquette}", "email": email, "whatsapp": ""})
            d = self.db.chat_participants.find_one({"email": email}, {"_id": 0, "coach_id": 1})
            self.db.chat_participants.delete_many({"email": email})   # jamais de reste dans les listes
            return r, d
        r, d = creer(self.hA, "a")
        verifier(route, "A crée (propriétaire = A)", r.s,
                 r.s == 200 and d is not None and d.get("coach_id") == EMAIL_A,
                 f"coach_id={None if d is None else d.get('coach_id')}")
        r, d = creer(self.ANON, "anon")
        verifier(route, "anonyme", r.s, r.s in REFUS_AUTH and d is None, "fiche CRÉÉE" if d else "")
        r, d = creer(self.SPOOF_A, "spoof")
        verifier(route, "X-User-Email A sans JWT", r.s, r.s in REFUS_AUTH and d is None,
                 f"fiche CRÉÉE chez {d.get('coach_id')}" if d else "")
        r, d = creer(self.MIXTE, "mixte")
        verifier(route, "JWT B + X-User-Email A (propriétaire = B)", r.s,
                 d is None or d.get("coach_id") == EMAIL_B,
                 f"coach_id={None if d is None else d.get('coach_id')}")
        r, d = creer(self.hSA, "sa")
        verifier(route, "SUPER-ADMIN crée", r.s, r.s == 200 and d is not None)
        # A soumet l'e-mail d'un contact de B : jamais la fiche de B en retour, jamais B modifié.
        avant = self.doc("chat_participants", {"id": "mt-cp-b1"})
        r = self.c("POST", p, self.hA, {"name": "MTBANC-N-collision", "email": "mtbanc-b-contact1@banc.test"})
        apres = self.doc("chat_participants", {"id": "mt-cp-b1"})
        cree = self.db.chat_participants.find_one({"email": "mtbanc-b-contact1@banc.test",
                                                   "id": {"$ne": "mt-cp-b1"}}, {"_id": 0, "id": 1})
        if cree:
            self.db.chat_participants.delete_many({"id": cree["id"]})
        fuite = "mt-cp-b1" in r.t or MB in r.t
        verifier(route, "A POST e-mail d'un contact de B", r.s,
                 r.s != 500 and not fuite and _sans_horodatage(avant) == _sans_horodatage(apres),
                 ("fiche de B renvoyée " if fuite else "")
                 + ("fiche de B MODIFIÉE" if _sans_horodatage(avant) != _sans_horodatage(apres) else ""))
        if apres != avant and avant:
            self.db.chat_participants.replace_one({"id": "mt-cp-b1"}, avant)

    def bulk_import(self):
        route = "POST /api/contacts/bulk-import"
        p = "/api/contacts/bulk-import"

        def imp(h, etiquette, email=None):
            email = email or f"mtbanc-n-imp-{etiquette}-{self.uid()}@banc.test"
            r = self.c("POST", p, h, {"contacts": [{"name": f"MTBANC-N-Import-{etiquette}", "email": email}],
                                      "source": "banc"})
            docs = list(self.db.chat_participants.find({"email": email, "name": {"$regex": "^MTBANC-N-"}},
                                                       {"_id": 0, "coach_id": 1}))
            self.db.chat_participants.delete_many({"email": email, "name": {"$regex": "^MTBANC-N-"}})
            return r, docs
        r, d = imp(self.hA, "a")
        verifier(route, "A importe (propriétaire = A)", r.s,
                 r.s == 200 and len(d) == 1 and d[0].get("coach_id") == EMAIL_A, f"docs={d}")
        r, d = imp(self.ANON, "anon")
        verifier(route, "anonyme", r.s, r.s in REFUS_AUTH and not d)
        r, d = imp(self.SPOOF_A, "spoof")
        verifier(route, "X-User-Email A sans JWT", r.s, r.s in REFUS_AUTH and not d,
                 f"IMPORTÉ chez {d[0].get('coach_id')}" if d else "")
        r, d = imp(self.MIXTE, "mixte")
        verifier(route, "JWT B + X-User-Email A (propriétaire = B)", r.s,
                 all(x.get("coach_id") == EMAIL_B for x in d), f"docs={d}")
        r, d = imp(self.hSA, "sa")
        verifier(route, "SUPER-ADMIN importe", r.s, r.s == 200 and len(d) == 1)
        avant = self.doc("chat_participants", {"id": "mt-cp-b1"})
        r, d = imp(self.hA, "collision", email="mtbanc-b-contact1@banc.test")
        apres = self.doc("chat_participants", {"id": "mt-cp-b1"})
        dup = (r.j or {}).get("duplicates") if isinstance(r.j, dict) else None
        verifier(route, "A importe l'e-mail d'un contact de B", r.s,
                 r.s != 500 and _sans_horodatage(avant) == _sans_horodatage(apres) and not dup,
                 f"duplicates={dup} (existence de B révélée / import bloqué)" if dup else
                 ("fiche de B MODIFIÉE" if _sans_horodatage(avant) != _sans_horodatage(apres) else ""))

    def deduplicate(self):
        route = "POST /api/contacts/deduplicate"
        p = "/api/contacts/deduplicate"
        n = lambda x: self.db.chat_participants.count_documents({"email": f"mtbanc-{x}-doublon@banc.test"})
        for x in ("a", "b"):
            semer_doublons(self.db, x)
        r = self.c("POST", p, self.ANON)
        verifier(route, "anonyme", r.s, r.s in REFUS_AUTH and n("a") == 2 and n("b") == 2)
        r = self.c("POST", p, self.SPOOF_A)
        verifier(route, "X-User-Email A sans JWT", r.s, r.s in REFUS_AUTH and n("a") == 2,
                 "" if n("a") == 2 else "doublons de A FUSIONNÉS")
        semer_doublons(self.db, "a")
        r = self.c("POST", p, self.MIXTE)
        verifier(route, "JWT B + X-User-Email A : A intact", r.s, r.s != 500 and n("a") == 2,
                 "" if n("a") == 2 else "doublons de A FUSIONNÉS")
        for x in ("a", "b"):
            semer_doublons(self.db, x)
        r = self.c("POST", p, self.hA)
        verifier(route, "A modifie A (ses doublons fusionnés)", r.s, r.s == 200 and n("a") == 1, f"A={n('a')}")
        verifier(route, "A supprime B (doublons de B intacts)", r.s, n("b") == 2, f"B={n('b')}")
        semer_doublons(self.db, "a")
        r = self.c("POST", p, self.hSA)
        verifier(route, "SUPER-ADMIN global", r.s, r.s == 200 and n("a") == 1 and n("b") == 1,
                 f"A={n('a')} B={n('b')}")

    # ═══════════════════════════ REGEX WHATSAPP (en dernier : écrit) ════════
    def regex_whatsapp(self):
        route = "POST /api/chat/participants (regex WhatsApp)"
        filtre_etr = {"$or": [{"coach_id": EMAIL_B}, {"coach_id": {"$exists": False}}]}
        etrangers = lambda: [_sans_horodatage(d) for d in
                             self.db.chat_participants.find(filtre_etr, {"_id": 0}).sort("id", 1)]
        for motif in ("+", ".", ".*", "[", "(", "\\", "^", "$"):
            ids_avant = set(d["id"] for d in self.db.chat_participants.find({}, {"_id": 0, "id": 1}))
            sauvegarde = list(self.db.chat_participants.find(filtre_etr))
            avant = etrangers()
            r = self.c("POST", "/api/chat/participants", self.hA,
                       {"name": f"MTBANC-A-Regex-{self.uid()}", "whatsapp": motif, "email": ""})
            apres = etrangers()
            fuite = self.fuites(r.t, (MB, MG))
            ok = r.s != 500 and r.s != 0 and not fuite and avant == apres
            note = " ".join(filter(None, [f"renvoie la fiche d'un autre {fuite}" if fuite else "",
                                          "fiche étrangère MODIFIÉE" if avant != apres else "",
                                          "erreur serveur" if r.s == 500 else ""]))
            verifier(route, f"whatsapp « {motif} »", r.s, ok, note)
            # Remise en état EXACTE : on retire les seules fiches créées par ce test et on
            # restaure les fiches étrangères telles qu'avant (chaque motif part du même état).
            self.db.chat_participants.delete_many({"id": {"$nin": list(ids_avant)}})
            for d in sauvegarde:
                self.db.chat_participants.replace_one({"_id": d["_id"]}, d, upsert=True)


def _sans_horodatage(d):
    if not d:
        return d
    return {k: v for k, v in d.items() if k not in ("last_seen_at", "updated_at")}


# ═══════════════════════════ rapport ══════════════════════════════════════════
def imprimer():
    lr = max(len(r[0]) for r in RESULTATS)
    ls = max(len(r[1]) for r in RESULTATS)
    print(f"\n{'ROUTE'.ljust(lr)} | {'SCÉNARIO'.ljust(ls)} | HTTP | VERDICT")
    print("-" * (lr + ls + 30))
    for route, scen, code, ok, note in RESULTATS:
        c = str(code) if not isinstance(code, list) else ",".join(map(str, code))
        v = "OK" if ok else "ÉCHEC" + (f" ({note})" if note else "")
        print(f"{route.ljust(lr)} | {scen.ljust(ls)} | {c:>4} | {v}")
    vert = sum(1 for r in RESULTATS if r[3])
    rouges = {}
    for route, scen, *_rest in (r for r in RESULTATS if not r[3]):
        rouges.setdefault(route, []).append(scen)
    if rouges:
        print("\nROUTES EN ÉCHEC :")
        for route, sc in rouges.items():
            print(f"  - {route} : {', '.join(sc)}")
    print(f"\n{vert} / {len(RESULTATS)} vérifications MT au vert")
    return vert == len(RESULTATS)


def main():
    ap = argparse.ArgumentParser(description="MT-3 — matrice de sécurité multi-tenant (banc local jetable)")
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help="dépôt dont on lance l'API (défaut : ce dépôt)")
    args = ap.parse_args()
    repo = os.path.abspath(args.repo)
    if not os.path.exists(os.path.join(repo, "api", "index.py")):
        raise SystemExit(f"{repo} n'est pas un dépôt Afroboost (api/index.py absent).")
    scratch = os.environ.get("MT_SCRATCH", SCRATCH_DEFAUT)
    banc = Banc(repo, scratch)

    def _interruption(signum, _frame):
        banc.nettoyer()
        sys.exit(130)
    signal.signal(signal.SIGINT, _interruption)
    signal.signal(signal.SIGTERM, _interruption)

    tout_vert = False
    try:
        try:
            _commit = subprocess.run(["git", "-C", repo, "rev-parse", "--short", "HEAD"],
                                     capture_output=True, text=True).stdout.strip()
        except Exception:
            _commit = "?"
        print(f"=== MT-3 MATRICE MULTI-TENANT — dépôt {repo} (commit {_commit}) ===")
        banc.demarrer()
        print(f"Banc prêt : API {banc.api_url}, base {banc.db_name} (locale, jetable)")
        mdp = creer_comptes(banc.db)
        semer_herites(banc.db)          # en premier : ordre naturel = fiches étrangères d'abord
        semer_coach(banc.db, "b")
        semer_coach(banc.db, "a")
        jetons = {}
        for cle, email in (("SA", EMAIL_SA), ("A", EMAIL_A), ("B", EMAIL_B)):
            r = banc.appel("POST", "/api/auth/login", {}, {"email": email, "password": mdp[cle]})
            jetons[cle] = (r.j or {}).get("token") if isinstance(r.j, dict) else None
            if r.s != 200 or not jetons[cle]:
                raise SystemExit(f"Connexion impossible pour {cle} (HTTP {r.s}) — banc inutilisable.")
        mdp.clear()
        m = Matrice(banc, jetons)
        m.semer_campagnes()
        m.campagnes()
        m.contacts_lectures()
        m.contacts_ecritures()
        m.destinataires()
        m.purge()
        m.regex_whatsapp()
        tout_vert = imprimer()
    finally:
        banc.nettoyer()
    sys.exit(0 if tout_vert else 1)


if __name__ == "__main__":
    main()
