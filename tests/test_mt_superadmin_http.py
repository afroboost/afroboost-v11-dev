# -*- coding: utf-8 -*-
"""MT-4 — NON-RÉGRESSION SUPER-ADMIN du lot sécurité multi-coach (29/09/2026).

POURQUOI CE BANC
    Le durcissement multi-coach (Campagnes, Contacts) ne doit RIEN retirer au
    propriétaire de la plateforme, et ne doit transférer AUCUNE capacité globale
    à un coach partenaire. Précédent à ne pas reproduire : V310c (un durcissement
    a renvoyé 403 au tableau de bord du propriétaire -> dashboard VIDE).

CE QU'IL FAIT — banc HTTP 100 % LOCAL
    * un `mongod` jetable (127.0.0.1:27112, dbpath temporaire) ;
    * la VRAIE application (`uvicorn api.index:app`, 127.0.0.1:8112) lancée avec
      un environnement vide (`env -i`) : aucune clé d'envoi (Resend, WhatsApp,
      Twilio, VAPID…) -> AUCUN envoi possible ; `/launch` n'est JAMAIS appelé ;
    * comptes : le super-admin UNIQUE (contact.artboost@gmail.com), l'ANCIEN
      second super-admin (afroboost.bassi@gmail.com — SA-1 : désormais compte
      ordinaire, vérifié NON super-admin) + coachs A et B (@banc.test) dans `users_auth`
      (mot de passe aléatoire, jamais imprimé, PBKDF2 `sel:hex` 100 000 it.) ;
      jetons obtenus par le VRAI `POST /api/auth/login` ;
    * données « plateforme » (sans coach_id, coach_id "bassi_default",
      coach_id = e-mail admin) + données A + données B.

TROIS MODES D'APPEL POUR LE SUPER-ADMIN
    NAVIGATEUR  Bearer + X-User-Email : ce que pose l'intercepteur axios du
                dashboard aujourd'hui. C'est LA RÉFÉRENCE : tout ce qui y est vert
                avant le lot doit y rester vert après (score principal).
    JWT SEUL    Bearer uniquement : la cible d'un durcissement « JWT strict ».
                Informatif : montre quelles routes dépendent encore de l'en-tête.
    EN-TÊTE     X-User-Email seul (repli ChatWidget / afroboost_admin_persist,
                chemin V310c). Informatif : ce qui disparaîtrait si on coupe le
                repli.

CONTRÔLE CROISÉ COACH A — « aucune capacité globale transférée »
    Mêmes routes avec le jeton de A : A ne doit voir QUE A. Plus l'usurpation :
    jeton de A + `X-User-Email: <admin>` ne doit rien ouvrir de plus.

SA-1 — L'ANCIEN SECOND SUPER-ADMIN (afroboost.bassi@gmail.com)
    Connecté par le VRAI `/api/auth/login` : son jeton porte `role: coach`,
    `whoami` le dit non super-admin, il ne voit AUCUNE donnée d'autrui et les
    routes réservées (activation de coach, fils WhatsApp) lui répondent 403 —
    en JWT seul, en mode navigateur, et en usurpation (son jeton + en-tête
    `X-User-Email` du propriétaire).

Lancement :  python3 tests/test_mt_superadmin_http.py
             (ou pytest : ignoré proprement si `mongod` est absent)
Tout ce qui est créé (base, journaux) vit sous SCRATCH et est SUPPRIMÉ à la fin.
"""
import os
import secrets
import shutil
import signal
import subprocess
import sys
import time
import uuid
import hashlib
from datetime import datetime, timezone, timedelta

import requests

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCRATCH = os.environ.get(
    "MT4_SCRATCH",
    "/private/tmp/claude-501/-Users-afroboost-afroboost-v11-dev/"
    "256653a6-1acc-4dfa-be6a-b798c1d20a8b/scratchpad/mt-superadmin",
)
PORT_MONGO = 27112
PORT_API = 8112
MONGO_URL = "mongodb://127.0.0.1:%d" % PORT_MONGO
DB_NAME = "mt_sa"
API = "http://127.0.0.1:%d" % PORT_API

ADMIN1 = "contact.artboost@gmail.com"
ADMIN2 = "afroboost.bassi@gmail.com"   # SA-1 : ANCIEN second super-admin -> compte ordinaire
COACH_A = "coach.a@banc.test"
COACH_B = "coach.b@banc.test"

# Garde-fou : ce banc n'écrit QUE dans une base locale.
assert MONGO_URL.startswith("mongodb://127.0.0.1:"), "MONGO_URL doit viser 127.0.0.1"


# ═══ JEU DE DONNÉES ═══════════════════════════════════════════════════════════
def _iso(jours=0):
    return (datetime.now(timezone.utc) - timedelta(days=jours)).isoformat()


# Propriétaires : "none" = champ absent, sinon valeur de coach_id.
PROPRIOS = [
    ("PLATSANS", None),            # plateforme, sans coach_id
    ("PLATDEF", "bassi_default"),  # plateforme, sentinelle historique
    ("PLATADM", ADMIN1),           # plateforme, e-mail admin
    ("COA", COACH_A),
    ("COB", COACH_B),
]
PLATEFORME = ("PLATSANS", "PLATDEF", "PLATADM")


def _avec_coach(doc, coach):
    if coach is not None:
        doc["coach_id"] = coach
    return doc


def construire_donnees():
    d = {k: [] for k in ("users", "chat_participants", "leads", "campaigns",
                         "reservations", "chat_sessions")}
    for tag, coach in PROPRIOS:
        low = tag.lower()
        d["users"].append(_avec_coach({
            "id": "u-" + low, "name": "Usager " + tag, "email": "usager.%s@clients-banc.ch" % low,
            "whatsapp": "+4178000%04d" % (len(d["users"]) + 1), "createdAt": _iso(10),
        }, coach))
        d["chat_participants"].append(_avec_coach({
            "id": "p-" + low, "name": "Participant " + tag,
            "email": "participant.%s@clients-banc.ch" % low,
            "whatsapp": "+4179000%04d" % (len(d["chat_participants"]) + 1),
            "source": "chat", "created_at": _iso(5),
        }, coach))
        d["leads"].append(_avec_coach({
            "id": "l-" + low, "name": "Prospect " + tag,
            "email": "prospect.%s@clients-banc.ch" % low, "createdAt": _iso(3),
        }, coach))
        d["campaigns"].append(_avec_coach({
            "id": "c-" + low, "name": "Campagne " + tag, "message": "Bonjour",
            "status": "draft", "targetType": "all", "channels": {"email": True},
            "targetIds": [], "selectedContacts": [], "results": [],
            "createdAt": _iso(2), "updatedAt": _iso(2),
        }, coach))
        d["reservations"].append(_avec_coach({
            "id": "r-" + low, "reservationCode": "RB-" + tag, "userName": "Client " + tag,
            "userEmail": "client.%s@clients-banc.ch" % low, "courseName": "Cours banc",
            "offerName": "Offre banc", "totalPrice": 0, "quantity": 1,
            "datetime": _iso(-3), "createdAt": _iso(1), "validated": False,
        }, coach))
        d["chat_sessions"].append(_avec_coach({
            "id": "s-" + low, "title": "Groupe " + tag, "mode": "group",
            "participant_ids": ["p-" + low], "is_deleted": False,
            "created_at": _iso(4), "updated_at": _iso(4),
        }, coach))
    return d


def _hash(mdp):
    sel = secrets.token_hex(16)
    return "%s:%s" % (sel, hashlib.pbkdf2_hmac("sha256", mdp.encode(), sel.encode(), 100000).hex())


# ═══ INFRASTRUCTURE ═══════════════════════════════════════════════════════════
class Banc:
    def __init__(self):
        self.api = None
        self.mdp = {}
        self.jetons = {}

    def demarrer(self):
        if os.path.exists(SCRATCH):
            shutil.rmtree(SCRATCH)
        os.makedirs(os.path.join(SCRATCH, "db"))
        subprocess.run(
            ["mongod", "--dbpath", os.path.join(SCRATCH, "db"), "--port", str(PORT_MONGO),
             "--bind_ip", "127.0.0.1", "--fork", "--logpath", os.path.join(SCRATCH, "mongod.log"),
             "--pidfilepath", os.path.join(SCRATCH, "mongod.pid")],
            check=True, stdout=subprocess.DEVNULL)
        self.semer()
        env = {"HOME": os.environ.get("HOME", ""), "PATH": os.environ.get("PATH", ""),
               "MONGO_URL": MONGO_URL, "DB_NAME": DB_NAME,
               "JWT_SECRET": secrets.token_urlsafe(48),
               "FRONTEND_URL": "http://localhost:%d" % PORT_API}
        assert env["MONGO_URL"].startswith("mongodb://127.0.0.1:")
        self._log = open(os.path.join(SCRATCH, "api.log"), "wb")
        self.api = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "api.index:app", "--host", "127.0.0.1",
             "--port", str(PORT_API)],
            cwd=RACINE, env=env, stdout=self._log, stderr=subprocess.STDOUT)
        for _ in range(240):
            try:
                if requests.get(API + "/healthz", timeout=1).status_code == 200:
                    break
            except requests.RequestException:
                pass
            if self.api.poll() is not None:
                raise RuntimeError("uvicorn s'est arrêté au démarrage (voir api.log)")
            time.sleep(0.5)
        else:
            raise RuntimeError("API locale injoignable (/healthz)")
        for e in (ADMIN1, ADMIN2, COACH_A, COACH_B):
            r = requests.post(API + "/api/auth/login", json={"email": e, "password": self.mdp[e]}, timeout=30)
            jeton = (r.json() or {}).get("token") if r.status_code == 200 else ""
            if not jeton:
                raise RuntimeError("connexion impossible pour %s (HTTP %s)" % (e, r.status_code))
            self.jetons[e] = jeton

    def semer(self):
        from pymongo import MongoClient
        cli = MongoClient(MONGO_URL, serverSelectionTimeoutMS=10000)
        db = cli[DB_NAME]
        for e in (ADMIN1, ADMIN2, COACH_A, COACH_B):
            self.mdp[e] = secrets.token_urlsafe(24)
            db.users_auth.insert_one({
                "user_id": "u_" + uuid.uuid4().hex[:12], "email": e, "name": e.split("@")[0],
                "password_hash": _hash(self.mdp[e]), "auth_method": "email_password",
                "is_coach": True, "pending_validation": False, "created_at": _iso(30)})
        # Le super-admin (et l'ancien second, SA-1) ne sont PAS dans `coaches`.
        for e in (COACH_A, COACH_B):
            db.coaches.insert_one({"id": str(uuid.uuid4()), "email": e, "name": e.split("@")[0],
                                   "credits": 500, "is_active": True, "created_at": _iso(30)})
        for coll, docs in construire_donnees().items():
            db[coll].insert_many(docs)
        cli.close()

    def arreter(self):
        if self.api is not None and self.api.poll() is None:
            self.api.send_signal(signal.SIGTERM)
            try:
                self.api.wait(15)
            except subprocess.TimeoutExpired:
                self.api.kill()
        try:
            self._log.close()
        except Exception:
            pass
        # `mongod --shutdown` n'existe que sous Linux : on arrête par le PID (SIGTERM,
        # arrêt propre) et on ATTEND la fin du processus avant de supprimer le dossier.
        try:
            with open(os.path.join(SCRATCH, "mongod.pid")) as f:
                pid = int(f.read().strip())
            os.kill(pid, signal.SIGTERM)
            for _ in range(60):
                try:
                    os.kill(pid, 0)
                except OSError:
                    break
                time.sleep(0.5)
            else:
                os.kill(pid, signal.SIGKILL)
        except (OSError, ValueError):
            pass
        shutil.rmtree(SCRATCH, ignore_errors=True)


# ═══ APPELS ═══════════════════════════════════════════════════════════════════
def entetes(banc, qui, mode):
    h = {}
    if mode in ("navigateur", "jwt"):
        h["Authorization"] = "Bearer " + banc.jetons[qui]
    if mode in ("navigateur", "entete"):
        h["X-User-Email"] = qui
    return h


def appel(banc, methode, chemin, qui, mode, **kw):
    kw.setdefault("timeout", 60)
    try:
        r = requests.request(methode, API + chemin, headers=entetes(banc, qui, mode), **kw)
    except requests.RequestException as ex:
        return None, "erreur réseau %s" % type(ex).__name__
    try:
        corps = r.json()
    except ValueError:
        corps = None
    return r.status_code, corps


def _liste(corps, cle=None):
    if cle and isinstance(corps, dict):
        corps = corps.get(cle)
    return corps if isinstance(corps, list) else []


def _noms(corps, cle=None, champ="name"):
    return {str(x.get(champ) or "") for x in _liste(corps, cle) if isinstance(x, dict)}


def _attendus(prefixe, tags):
    return {"%s %s" % (prefixe, t) for t in tags}


TOUS = [t for t, _ in PROPRIOS]


# ═══ VÉRIFICATIONS ════════════════════════════════════════════════════════════
class Tableau:
    def __init__(self, titre):
        self.titre = titre
        self.lignes = []

    def v(self, capacite, attendu, obtenu, ok):
        self.lignes.append((capacite, attendu, str(obtenu), bool(ok)))

    @property
    def verts(self):
        return sum(1 for l in self.lignes if l[3])

    def imprimer(self):
        print("\n### %s" % self.titre)
        print("| Capacité | Attendu | Obtenu | Verdict |")
        print("|---|---|---|---|")
        for c, a, o, ok in self.lignes:
            o = o if len(o) <= 140 else o[:137] + "..."
            print("| %s | %s | %s | %s |" % (c, a, o.replace("|", "/"), "OK" if ok else "ÉCHEC"))
        print("-> %d / %d" % (self.verts, len(self.lignes)))


def _voit(t, capacite, st, obtenus, attendus):
    manque = sorted(attendus - obtenus)
    t.v(capacite, "200 + %d éléments (plateforme + A + B)" % len(attendus),
        "HTTP %s, %d/%d vus%s" % (st, len(attendus & obtenus), len(attendus),
                                  (" — manque " + ", ".join(manque)) if manque else ""),
        st == 200 and not manque)


def verifier_super_admin(banc, admin, mode):
    t = Tableau("Super-admin %s — mode %s" % (admin, mode.upper()))

    # Identité (le jeton ne dépend pas du mode : whoami ne lit QUE le Bearer).
    if mode != "entete":
        st, c = appel(banc, "GET", "/api/auth/whoami", admin, mode)
        t.v("whoami", "valid + is_super_admin true", "HTTP %s %s" % (st, {k: (c or {}).get(k) for k in ("valid", "is_super_admin")}),
            st == 200 and (c or {}).get("valid") is True and (c or {}).get("is_super_admin") is True)

    # Contacts
    st, c = appel(banc, "GET", "/api/contacts/all", admin, mode)
    vus = _noms(c, "contacts")
    _voit(t, "contacts/all — participants", st, vus, _attendus("Participant", TOUS))
    _voit(t, "contacts/all — users", st, vus, _attendus("Usager", TOUS))
    _voit(t, "contacts/all — groupes", st, vus, _attendus("Groupe", TOUS))
    fiches = [x for x in _liste(c, "contacts") if isinstance(x, dict) and x.get("type") != "group"
              and str(x.get("name") or "").startswith(("Participant ", "Usager "))]
    # `/contacts/all` ne projette pas le téléphone des `users` (P1-A.1) : l'export
    # exige donc l'e-mail partout, et le téléphone sur les fiches CRM (participants).
    complets = [x for x in fiches if x.get("email") and (
        str(x.get("name")).startswith("Usager ") or x.get("whatsapp") or x.get("phone"))]
    t.v("export (contacts/all : e-mail partout, téléphone CRM)", "10 fiches exportables",
        "%d/%d exportables" % (len(complets), len(fiches)), st == 200 and len(complets) == 10)

    st, c = appel(banc, "GET", "/api/chat/participants", admin, mode)
    _voit(t, "chat/participants", st, _noms(c), _attendus("Participant", TOUS))
    st, c = appel(banc, "GET", "/api/users", admin, mode)
    _voit(t, "users", st, _noms(c), _attendus("Usager", TOUS))
    st, c = appel(banc, "GET", "/api/leads", admin, mode)
    _voit(t, "leads", st, _noms(c), _attendus("Prospect", TOUS))

    st, c = appel(banc, "GET", "/api/contact-categories", admin, mode)
    cats = _liste(c, "categories")
    t.v("contact-categories", "200 + success + catégories", "HTTP %s, success=%s, %d cat." % (st, (c or {}).get("success") if isinstance(c, dict) else None, len(cats)),
        st == 200 and isinstance(c, dict) and c.get("success") is True and len(cats) > 0)

    st, c = appel(banc, "GET", "/api/contacts/segments", admin, mode)
    pers = (c or {}).get("personnes") if isinstance(c, dict) else None
    t.v("contacts/segments (comptes globaux)", "200 + personnes ≥ 15", "HTTP %s, personnes=%s" % (st, pers),
        st == 200 and isinstance(pers, int) and pers >= 15)
    st, c = appel(banc, "GET", "/api/contacts/segment/email", admin, mode)
    ids = {x.get("id") for x in _liste(c, "contacts") if isinstance(x, dict)}
    att = {"p-" + t_.lower() for t_ in TOUS}
    t.v("contacts/segment/email", "200 + participants plateforme + A + B", "HTTP %s, %d/%d" % (st, len(att & ids), len(att)),
        st == 200 and att <= ids)

    # Campagnes
    st, c = appel(banc, "GET", "/api/campaigns", admin, mode)
    _voit(t, "campaigns (liste)", st, _noms(c), _attendus("Campagne", TOUS))
    st, c = appel(banc, "GET", "/api/campaigns-list", admin, mode)
    _voit(t, "campaigns-list", st, _noms(c), _attendus("Campagne", TOUS))
    for cid in ("c-coa", "c-cob", "c-platsans"):
        st, c = appel(banc, "GET", "/api/campaigns/" + cid, admin, mode)
        t.v("campaigns/{id} " + cid, "200 + la campagne", "HTTP %s id=%s" % (st, (c or {}).get("id") if isinstance(c, dict) else None),
            st == 200 and isinstance(c, dict) and c.get("id") == cid)
    st, c = appel(banc, "GET", "/api/campaign-debug/c-cob", admin, mode)
    t.v("campaign-debug/{id} (campagne de B)", "200 + la campagne", "HTTP %s id=%s" % (st, (c or {}).get("id") if isinstance(c, dict) else None),
        st == 200 and isinstance(c, dict) and c.get("id") == "c-cob")

    # Réservations / conversations (clients)
    st, c = appel(banc, "GET", "/api/reservations?all_data=true", admin, mode)
    _voit(t, "reservations (all_data)", st, _noms(c, "data", "userName"), _attendus("Client", TOUS))
    st, c = appel(banc, "GET", "/api/chat/sessions", admin, mode)
    _voit(t, "chat/sessions (conversations)", st, _noms(c, None, "title"), _attendus("Groupe", TOUS))

    # Envoi : brouillon « tous » + aperçu (AUCUN envoi, jamais /launch).
    nom = "MT4 brouillon %s %s" % (admin.split("@")[0], mode)
    st, c = appel(banc, "POST", "/api/campaigns", admin, mode,
                  json={"name": nom, "message": "Aperçu seulement", "targetType": "all",
                        "channels": {"email": True}, "targetIds": [], "selectedContacts": []})
    cid = (c or {}).get("id") if isinstance(c, dict) else None
    t.v("création brouillon « tous »", "200 + draft", "HTTP %s statut=%s" % (st, (c or {}).get("status") if isinstance(c, dict) else None),
        st == 200 and cid and c.get("status") == "draft")
    if cid:
        st, c = appel(banc, "GET", "/api/campaigns/%s/preview" % cid, admin, mode)
        _voit(t, "aperçu « tous » — portée GLOBALE (users, y c. sans coach_id)", st,
              _noms(c, "liste", "nom"), _attendus("Usager", TOUS))
    st, c = appel(banc, "PUT", "/api/campaigns/c-cob", admin, mode, json={"name": "Campagne COB"})
    t.v("modifier la campagne de B (PUT)", "200", "HTTP %s" % st, st == 200)
    if cid:
        st, c = appel(banc, "DELETE", "/api/campaigns/" + cid, admin, mode)
        t.v("supprimer son brouillon (DELETE)", "200", "HTTP %s" % st, st == 200)
    if mode != "entete":
        # SA-1 : preuve V310c — la route réservée V411 reste ouverte au propriétaire.
        st, c = appel(banc, "GET", "/api/private/conversations/admin_afroboost", admin, mode)
        t.v("fils réservés admin_afroboost (V411)", "200", "HTTP %s" % st, st == 200)
    return t


def verifier_coach_a(banc, mode, usurpe=False, qui=COACH_A, tag="COA"):
    """Contrôle croisé : A ne doit voir QUE A. `usurpe` = jeton de A + X-User-Email admin.

    SA-1 : réutilisé tel quel pour l'ANCIEN second super-admin (`qui=ADMIN2`,
    `tag=None`) — il ne possède rien, il ne doit donc RIEN voir d'autrui.
    """
    _nom = "Coach A" if qui == COACH_A else "SA-1 ancien second super-admin %s" % qui
    titre = "%s — %s" % (_nom, "jeton + X-User-Email ADMIN (usurpation)" if usurpe else "mode " + mode.upper())
    t = Tableau(titre)

    def app(methode, chemin, **kw):
        if not usurpe:
            return appel(banc, methode, chemin, qui, mode, **kw)
        h = {"Authorization": "Bearer " + banc.jetons[qui], "X-User-Email": ADMIN1}
        try:
            r = requests.request(methode, API + chemin, headers=h, timeout=60, **kw)
            try:
                return r.status_code, r.json()
            except ValueError:
                return r.status_code, None
        except requests.RequestException as ex:
            return None, str(ex)

    def seulement_a(capacite, st, vus, prefixe):
        # « Groupe VIP » est un groupe STANDARD synthétique de /contacts/all, pas une donnée.
        autres = sorted(n for n in vus if n.startswith(prefixe + " ")
                        and not (tag and n.endswith(" " + tag)) and n != "Groupe VIP")
        a_vu = bool(tag) and ("%s %s" % (prefixe, tag)) in vus
        t.v(capacite, "rien d'autre que A (403 accepté)",
            "HTTP %s, A vu=%s, autres=%s" % (st, a_vu, autres or "aucun"),
            st in (401, 403) or (st == 200 and not autres))

    if not usurpe:
        st, c = app("GET", "/api/auth/whoami")
        t.v("whoami", "is_super_admin false", "HTTP %s %s" % (st, (c or {}).get("is_super_admin") if isinstance(c, dict) else None),
            st == 200 and isinstance(c, dict) and c.get("is_super_admin") is False)
        if qui == ADMIN2:
            t.v("SA-1 : rôle du JWT émis par /auth/login", "coach",
                "role=%s" % (c or {}).get("role") if isinstance(c, dict) else None,
                isinstance(c, dict) and c.get("role") == "coach")
    etrangers_ok = (lambda i: i != "p-" + tag.lower()) if tag else (lambda i: True)
    st, c = app("GET", "/api/contacts/all")
    vus = _noms(c, "contacts")
    seulement_a("contacts/all — participants", st, vus, "Participant")
    seulement_a("contacts/all — users", st, vus, "Usager")
    seulement_a("contacts/all — groupes", st, vus, "Groupe")
    st, c = app("GET", "/api/chat/participants")
    seulement_a("chat/participants", st, _noms(c), "Participant")
    st, c = app("GET", "/api/users")
    seulement_a("users", st, _noms(c), "Usager")
    st, c = app("GET", "/api/leads")
    seulement_a("leads", st, _noms(c), "Prospect")
    st, c = app("GET", "/api/contacts/segment/email")
    ids = {x.get("id") for x in _liste(c, "contacts") if isinstance(x, dict)}
    etrangers = sorted(i for i in ids if i and i.startswith("p-") and etrangers_ok(i))
    t.v("contacts/segment/email", "aucun participant hors A", "HTTP %s, étrangers=%s" % (st, etrangers or "aucun"),
        st in (401, 403) or (st == 200 and not etrangers))
    st, c = app("GET", "/api/campaigns")
    seulement_a("campaigns (liste)", st, _noms(c), "Campagne")
    st, c = app("GET", "/api/campaigns-list")
    seulement_a("campaigns-list", st, _noms(c), "Campagne")
    st, c = app("GET", "/api/campaigns/c-cob")
    t.v("campaigns/{id} de B", "pas 200 avec le contenu", "HTTP %s" % st,
        not (st == 200 and isinstance(c, dict) and c.get("id") == "c-cob"))
    st, c = app("GET", "/api/campaign-debug/c-cob")
    t.v("campaign-debug/{id} de B", "pas le contenu", "HTTP %s id=%s" % (st, (c or {}).get("id") if isinstance(c, dict) else None),
        not (isinstance(c, dict) and c.get("id") == "c-cob"))
    st, c = app("GET", "/api/reservations?all_data=true")
    seulement_a("reservations (all_data)", st, _noms(c, "data", "userName"), "Client")
    st, c = app("GET", "/api/chat/sessions")
    seulement_a("chat/sessions", st, _noms(c, None, "title"), "Groupe")
    st, c = app("PUT", "/api/campaigns/c-cob", json={"name": "Piratée"})
    t.v("modifier la campagne de B (PUT)", "403", "HTTP %s" % st, st in (401, 403))
    st, c = app("POST", "/api/campaigns", json={"name": "MT4 brouillon A", "message": "x", "targetType": "all",
                                                "channels": {"email": True}, "targetIds": [], "selectedContacts": []})
    cid = (c or {}).get("id") if isinstance(c, dict) else None
    if st == 200 and cid:
        st2, c2 = app("GET", "/api/campaigns/%s/preview" % cid)
        seulement_a("aperçu « tous » — portée limitée à A", st2, _noms(c2, "liste", "nom"), "Usager")
        app("DELETE", "/api/campaigns/" + cid)
    else:
        t.v("création brouillon « tous »", "200 (ou refus explicite)", "HTTP %s" % st, st in (200, 401, 402, 403))
    if qui == ADMIN2:
        # SA-1 : routes RÉSERVÉES au super-admin -> 403 pour l'ancien second.
        st, c = app("GET", "/api/private/conversations/admin_afroboost")
        t.v("SA-1 : fils réservés admin_afroboost (V411)", "403", "HTTP %s" % st, st == 403)
        st, c = app("POST", "/api/admin/activate-coach", json={"email": COACH_B})
        t.v("SA-1 : activation de coach (V2-0d)", "403", "HTTP %s" % st, st == 403)
    return t


# ═══ RÉFÉRENCE (af-sec 98d77a0b, code NON corrigé, 29/09/2026) ═══════════════
# Échecs super-admin DÉJÀ présents avant le lot (mode navigateur) — ce ne sont pas
# des régressions du lot, mais des défauts préexistants à corriger à part :
# SA-1 (29/09/2026) : ces lignes ne s'appliquent plus — afroboost.bassi@gmail.com
# n'est plus super-admin du tout (décision définitive du propriétaire). Il est
# désormais vérifié comme compte ORDINAIRE (voir `verifier_coach_a(qui=ADMIN2)`).
#   * afroboost.bassi@gmail.com n'est PAS reconnu super-admin par
#     `contact_segments_routes._est_coach_ou_admin` (liste codée à 1 e-mail) ->
#     segments 403 et, via `_autorise`, PUT/DELETE de campagne 403 ;
#   * `campaign_routes.is_super_admin` ne connaît que contact.artboost -> GET
#     /campaigns ne rend à afroboost.bassi que ses propres campagnes (0 ici).
DEFAUTS_REFERENCE = set()   # SA-1 : plus aucun défaut toléré sur le super-admin unique


# ═══ ORCHESTRATION ════════════════════════════════════════════════════════════
def executer():
    banc = Banc()
    tableaux = {}
    try:
        banc.demarrer()
        for admin in (ADMIN1,):
            for mode in ("navigateur", "jwt", "entete"):
                tableaux[(admin, mode)] = verifier_super_admin(banc, admin, mode)
        tableaux[("A", "navigateur")] = verifier_coach_a(banc, "navigateur")
        tableaux[("A", "jwt")] = verifier_coach_a(banc, "jwt")
        tableaux[("A", "usurpation")] = verifier_coach_a(banc, "navigateur", usurpe=True)
        # SA-1 : l'ancien second super-admin est un compte ORDINAIRE.
        for mode in ("navigateur", "jwt"):
            tableaux[(ADMIN2, mode)] = verifier_coach_a(banc, mode, qui=ADMIN2, tag=None)
        tableaux[(ADMIN2, "usurpation")] = verifier_coach_a(banc, "navigateur", usurpe=True,
                                                             qui=ADMIN2, tag=None)
    finally:
        banc.arreter()
    for t in tableaux.values():
        t.imprimer()

    def total(cles):
        ts = [tableaux[k] for k in cles]
        return sum(t.verts for t in ts), sum(len(t.lignes) for t in ts)

    sa_nav = total([(ADMIN1, "navigateur")])
    sa_jwt = total([(ADMIN1, "jwt")])
    sa_hdr = total([(ADMIN1, "entete")])
    coach = total([("A", "navigateur"), ("A", "jwt"), ("A", "usurpation")])
    ancien = total([(ADMIN2, "navigateur"), (ADMIN2, "jwt"), (ADMIN2, "usurpation")])
    print("\nRÉSUMÉ")
    print("  super-admin JWT SEUL (cible durcissement, informatif) : %d / %d" % sa_jwt)
    print("  super-admin X-User-Email SEUL (repli V310c, informatif) : %d / %d" % sa_hdr)
    print("  contrôle croisé coach A (aucune capacité globale)       : %d / %d" % coach)
    print("  SA-1 ancien second super-admin = compte ordinaire       : %d / %d" % ancien)
    regressions = [(adm, l[0]) for adm in (ADMIN1,) for l in tableaux[(adm, "navigateur")].lignes
                   if not l[3] and (adm, l[0]) not in DEFAUTS_REFERENCE]
    # SA-1 : tout échec sur l'ancien second (il verrait/pourrait plus qu'un compte
    # ordinaire) est une régression de sécurité, en mode navigateur comme en JWT.
    regressions += [(ADMIN2, m, l[0]) for m in ("navigateur", "jwt", "usurpation")
                    for l in tableaux[(ADMIN2, m)].lignes if not l[3]]
    corriges = [k for k in DEFAUTS_REFERENCE
                if any(l[0] == k[1] and l[3] for l in tableaux[(k[0], "navigateur")].lignes)]
    print("  défauts préexistants (référence) désormais corrigés     : %d / %d" % (len(corriges), len(DEFAUTS_REFERENCE)))
    print("  RÉGRESSIONS super-admin vs référence                    : %d %s" % (len(regressions), regressions or ""))
    print("%d / %d vérifications super-admin au vert" % sa_nav)
    _reste = subprocess.run(["pgrep", "-f", "port %d|port %d" % (PORT_MONGO, PORT_API)],
                            capture_output=True, text=True).stdout.split()
    print("(banc arrêté : processus restants=%s ; %s supprimé : %s)"
          % (_reste or "aucun", SCRATCH, not os.path.exists(SCRATCH)))
    return {"regressions": regressions, "sa_nav": sa_nav, "sa_jwt": sa_jwt, "sa_hdr": sa_hdr, "coach": coach,
            "ancien_second": ancien, "tableaux": tableaux}


def test_mt_superadmin_http():
    import pytest
    if not shutil.which("mongod"):
        pytest.skip("mongod absent : banc HTTP local impossible")
    r = executer()
    assert not r["regressions"], "régression super-admin : %s" % r["regressions"]


if __name__ == "__main__":
    res = executer()
    sys.exit(1 if res["regressions"] else 0)
