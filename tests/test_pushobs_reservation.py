# -*- coding: utf-8 -*-
"""
RESERVATION -> PUSH COACH : le parcours entier, et ce qu'il laisse comme trace.

POURQUOI CE BANC EXISTE (mesure du 06/09/2026, production).
  Bassi ne recoit plus la notification quand un participant reserve. La base,
  elle, dit le contraire : `confirmation.coach_push = "envoye"` sur les 26
  reservations qui portent ce canal, y compris celle de 09:51:59. Aucun commit
  depuis le 18/08 n'a touche la chaine. Le desaccord ne pouvait pas etre
  tranche, pour une raison simple et honteuse : PERSONNE NE SAVAIT QUEL
  APPAREIL AVAIT ETE SOLLICITE.
    - un document de `push_subscriptions` ne portait que 4 champs
      (`active`, `participant_id`, `subscription`, `updated_at`) : rien qui
      distingue le telephone du navigateur de bureau ;
    - le statut HTTP rendu par FCM n'existait QUE dans les journaux du
      conteneur Coolify, inaccessibles depuis le poste de travail ;
    - sur les 187 abonnements actifs du compte coach, V437 n'en essaie que 3.
  « envoye » voulait donc dire « au moins un endpoint sur 187 a repondu 201 » —
  et pas du tout « le telephone a sonne ».

CE QUE CE BANC VERIFIE
  A-K   le parcours demande : un seul push par reservation, coach sans
        appareil != panne, 404/410 par endpoint, selection V437, gratuit et
        payant, payload accepte par le Service Worker, clic non casse.
  OBS   ce que PUSH-OBS ajoute : la famille d'appareil a l'inscription, le
        verdict de FCM conserve sur l'abonnement, et AUCUNE fuite (ni endpoint,
        ni cle, ni adresse en clair).

HORS LIGNE. Les VRAIES fonctions sont executees. Aucun reseau, aucun push reel,
aucune donnee de production.

    python3 tests/test_pushobs_reservation.py
"""
import asyncio
import io
import json as _json
import os
import re
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def lire(*b):
    return io.open(os.path.join(RACINE, *b), encoding="utf-8").read()

SERVEUR = lire("api", "server.py")
SHARED = lire("api", "routes", "shared.py")
RESA = lire("api", "routes", "reservation_routes.py")
SW = lire("frontend", "public", "sw.js")

resultats = []
def verifier(nom, cond, detail=""):
    resultats.append((nom, bool(cond), str(detail)))

def extraire(src, nom):
    m = re.search(r"^(?:async )?def %s\(.*?(?=^(?:async def |def |@)|\Z)" % nom, src, re.S | re.M)
    return m.group(0) if m else ""

def code_seul(src):
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    return re.sub(r"^\s*(#|//).*$", "", src, flags=re.M)


# ---------------------------------------------------------------------------
# BASE EN MEMOIRE — avec un VRAI tri, sans quoi V437 ne serait pas eprouve
# ---------------------------------------------------------------------------
def _lire_chemin(d, chemin):
    cur = d
    for part in str(chemin).split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None, False
        cur = cur[part]
    return cur, True

def _ecrire_chemin(d, chemin, valeur):
    parts = str(chemin).split(".")
    for p in parts[:-1]:
        d = d.setdefault(p, {})
    d[parts[-1]] = valeur


class Col(object):
    def __init__(self):
        self.docs = []

    def _match(self, d, f):
        if not f:
            return True
        for k, v in f.items():
            if k == "$or":
                if not any(self._match(d, sf) for sf in v):
                    return False
                continue
            cur, ok = _lire_chemin(d, k)
            if isinstance(v, dict):
                if "$exists" in v and bool(ok) != bool(v["$exists"]):
                    return False
                if "$ne" in v and cur == v["$ne"]:
                    return False
                if "$in" in v and cur not in v["$in"]:
                    return False
                if not any(x in v for x in ("$exists", "$ne", "$in")):
                    return False
            else:
                if not ok or cur != v:
                    return False
        return True

    async def find_one(self, f=None, proj=None):
        for d in self.docs:
            if self._match(d, f):
                return dict(d)
        return None

    def find(self, f=None, proj=None):
        docs = [dict(d) for d in self.docs if self._match(d, f)]
        col = self
        class Cur(object):
            def __init__(s):
                s.docs = docs
            def sort(s, champ, sens=1):
                s.docs.sort(key=lambda d: str(d.get(champ) or ""), reverse=(sens == -1))
                return s
            def limit(s, n):
                s.docs = s.docs[:n]
                return s
            async def to_list(s, n=None):
                return s.docs[:n] if n else s.docs
            def __aiter__(s):
                s._i = 0
                return s
            async def __anext__(s):
                if s._i >= len(s.docs):
                    raise StopAsyncIteration
                s._i += 1
                return s.docs[s._i - 1]
        return Cur()

    async def insert_one(self, d):
        self.docs.append(dict(d))

    async def count_documents(self, f=None):
        return sum(1 for d in self.docs if self._match(d, f))

    async def update_one(self, f, maj, upsert=False):
        class R(object):
            def __init__(s, n):
                s.matched_count = n
                s.modified_count = n
        for d in self.docs:
            if self._match(d, f):
                for k, v in (maj.get("$set") or {}).items():
                    _ecrire_chemin(d, k, v)
                return R(1)
        if upsert:
            nouveau = {}
            for k, v in (f or {}).items():
                if not isinstance(v, dict):
                    _ecrire_chemin(nouveau, k, v)
            for k, v in (maj.get("$set") or {}).items():
                _ecrire_chemin(nouveau, k, v)
            for k, v in (maj.get("$setOnInsert") or {}).items():
                _ecrire_chemin(nouveau, k, v)
            self.docs.append(nouveau)
        return R(0)

    async def update_many(self, f, maj):
        return await self.update_one(f, maj)


class Base(object):
    def __init__(self):
        self.push_subscriptions = Col()
        self.reservations = Col()
        self.notifications = Col()
        self.chat_participants = Col()
        self.users = Col()
        self.courses = Col()
    def __getitem__(self, n):
        return getattr(self, n)


class HTTPException(Exception):
    def __init__(self, status_code=None, detail=None, headers=None):
        self.status_code, self.detail, self.headers = status_code, detail, headers or {}


class Req(object):
    """Requete simulee. `headers` EXISTE : PUSH-OBS y lit le User-Agent."""
    def __init__(self, corps, ua=""):
        self._c = corps
        self.headers = {"user-agent": ua}
    async def json(self):
        return self._c


class FauxWebPushException(Exception):
    def __init__(self, code):
        class Rep(object):
            pass
        self.response = Rep()
        self.response.status_code = code


# ---------------------------------------------------------------------------
# CHARGEURS — les VRAIES fonctions du depot, executees telles quelles
# ---------------------------------------------------------------------------
def esp_base(base):
    import datetime, logging
    return {"db": base, "HTTPException": HTTPException, "Request": object,
            "datetime": datetime.datetime, "timezone": datetime.timezone,
            "logger": logging.getLogger("pushobs"), "json": _json, "re": re}


def charger_subscribe(base):
    esp = esp_base(base)
    exec(compile(extraire(SERVEUR, "subscribe_push"), "<s>", "exec"), esp)
    return esp["subscribe_push"]


def charger_moteur_push(base, reponses):
    """`send_push_notification` reel. `reponses` decide ce que « FCM » repond."""
    esp = esp_base(base)
    tentatives = []

    class Rep201(object):
        status_code = 201

    def faux_webpush(subscription_info=None, data=None, vapid_private_key=None,
                     vapid_claims=None, ttl=None):
        ep = (subscription_info or {}).get("endpoint")
        tentatives.append({"endpoint": ep, "ttl": ttl, "payload": data})
        verdict = reponses.get(ep, 201)
        if verdict != 201:
            raise FauxWebPushException(verdict)
        return Rep201()

    esp["webpush"] = faux_webpush
    esp["WebPushException"] = FauxWebPushException
    esp["WEBPUSH_AVAILABLE"] = True
    esp["VAPID_PRIVATE_KEY"] = "cle-de-test"
    esp["VAPID_CLAIMS_EMAIL"] = "test@exemple.invalid"
    exec(compile(extraire(SERVEUR, "send_push_notification"), "<s>", "exec"), esp)
    exec(compile(extraire(SERVEUR, "send_push_by_email"), "<s>", "exec"), esp)
    return esp["send_push_notification"], esp["send_push_by_email"], tentatives


def charger_notifier(base):
    esp = esp_base(base)
    for fn in ("normaliser_email", "_rc_reserver_jeton", "_rc_cloturer_jeton",
               "resoudre_coach_de_reservation", "notifier_reservation_creee"):
        exec(compile(extraire(SHARED, fn), "<sh>", "exec"), esp)
    return esp["notifier_reservation_creee"]


COACH = "coach@test.ch"
PID = "coach_" + COACH

def abo(ep, maj, actif=True, pid=PID, **extra):
    d = {"participant_id": pid, "subscription": {"endpoint": ep, "keys": {"p256dh": "K", "auth": "A"}},
         "active": actif, "updated_at": maj}
    d.update(extra)
    return d

def resa(rid="r1", prix=0.0, email="client@test.ch"):
    return {"id": rid, "userEmail": email, "userName": "Ana Test", "coach_id": COACH,
            "courseName": "Afroboost Silent", "totalPrice": prix,
            "selectedDatesText": "dimanche 6 septembre"}


# ===========================================================================
# A-C, G-I — LE PARCOURS RESERVATION -> PUSH
# ===========================================================================
async def scenario_parcours():
    # --- A. une reservation valide -> UN SEUL appel de push -----------------
    base = Base()
    await base.push_subscriptions.insert_one(abo("https://fcm/PHONE", "2026-09-06T08:00:00"))
    notifier = charger_notifier(base)
    r = resa("A1")
    await base.reservations.insert_one(dict(r))
    appels = []
    async def push(email, titre, msg, data=None):
        appels.append({"email": email, "titre": titre, "data": data})
        return True
    bilan = await notifier(base, r, envoyer_push_coach=push)
    verifier("A1. le push coach est appele exactement une fois", len(appels) == 1, len(appels))
    verifier("A2. il vise le coach RESOLU, jamais une constante",
             appels and appels[0]["email"] == COACH, appels and appels[0]["email"])
    verifier("A3. le bilan declare l'envoi", bilan.get("coach_push") == "envoye", bilan.get("coach_push"))
    verifier("A4. la charge porte le type et l'identifiant de reservation",
             appels and appels[0]["data"].get("type") == "new_reservation"
             and appels[0]["data"].get("reservation_id") == "A1")

    # --- F. rejeu -> AUCUN second push --------------------------------------
    bilan2 = await notifier(base, r, envoyer_push_coach=push)
    verifier("F1. un rejeu ne renvoie AUCUN second push", len(appels) == 1, len(appels))
    verifier("F2. le rejeu se declare `deja_traite`", bilan2.get("coach_push") == "deja_traite",
             bilan2.get("coach_push"))

    # --- C. coach SANS aucun appareil ---------------------------------------
    base = Base()
    notifier = charger_notifier(base)
    r = resa("C1")
    await base.reservations.insert_one(dict(r))
    appels = []
    bilan = await notifier(base, r, envoyer_push_coach=push)
    verifier("C1. sans appareil, aucun push n'est tente", len(appels) == 0, len(appels))
    verifier("C2. `aucun_abonnement` n'est PAS confondu avec `echec`",
             bilan.get("coach_push") == "aucun_abonnement", bilan.get("coach_push"))
    verifier("C3. la reservation reste intacte", await base.reservations.count_documents({"id": "C1"}) == 1)

    # --- B. l'envoyeur qui echoue ne casse rien -----------------------------
    base = Base()
    await base.push_subscriptions.insert_one(abo("https://fcm/PHONE", "2026-09-06T08:00:00"))
    notifier = charger_notifier(base)
    r = resa("B1")
    await base.reservations.insert_one(dict(r))
    async def push_casse(*a, **k):
        raise RuntimeError("FCM injoignable")
    bilan = await notifier(base, r, envoyer_push_coach=push_casse)
    verifier("B1. une panne de push se dit `echec`, pas `envoye`",
             bilan.get("coach_push") == "echec", bilan.get("coach_push"))
    verifier("B2. la panne de push n'empeche pas la notification en-app",
             bilan.get("coach_inapp") == "envoye", bilan.get("coach_inapp"))

    # --- G/H. gratuit et payant empruntent le MEME chemin -------------------
    for etiquette, prix in (("G. reservation gratuite", 0.0), ("H. reservation payante", 45.0)):
        base = Base()
        await base.push_subscriptions.insert_one(abo("https://fcm/PHONE", "2026-09-06T08:00:00"))
        notifier = charger_notifier(base)
        r = resa("P" + str(prix), prix=prix)
        await base.reservations.insert_one(dict(r))
        appels = []
        await notifier(base, r, envoyer_push_coach=push)
        verifier(etiquette + " -> le coach est prevenu", len(appels) == 1, len(appels))

    # --- I. pas de reservation ecrite -> pas de push ------------------------
    base = Base()
    await base.push_subscriptions.insert_one(abo("https://fcm/PHONE", "2026-09-06T08:00:00"))
    notifier = charger_notifier(base)
    appels = []
    bilan = await notifier(base, resa("FANTOME"), envoyer_push_coach=push)
    verifier("I1. sans reservation en base, AUCUN push « nouvelle reservation »",
             len(appels) == 0, len(appels))

    # --- le coach non resolu ne declenche rien ------------------------------
    base = Base()
    notifier = charger_notifier(base)
    r = resa("SANSCOACH"); r["coach_id"] = ""
    await base.reservations.insert_one(dict(r))
    appels = []
    bilan = await notifier(base, r, envoyer_push_coach=push)
    verifier("I2. coach non resolu -> aucune notification, aucune invention",
             len(appels) == 0 and bilan.get("coach_push") is None, bilan.get("coach_push"))


# ===========================================================================
# D-E — SELECTION DES APPAREILS ET MISE AU REBUT
# ===========================================================================
async def scenario_selection():
    # --- E. V437 : les 3 plus RECENTS, endpoints dedupliques ----------------
    base = Base()
    for i, (ep, maj) in enumerate([
            ("https://fcm/vieux1", "2026-08-01T10:00:00"),
            ("https://fcm/recent1", "2026-09-06T11:46:17"),
            ("https://fcm/vieux2", "2026-08-02T10:00:00"),
            ("https://fcm/recent2", "2026-09-06T11:14:54"),
            ("https://fcm/recent3", "2026-09-03T10:11:03"),
            ("https://fcm/vieux3", "2026-08-03T10:00:00")]):
        await base.push_subscriptions.insert_one(abo(ep, maj))
    envoyer, _, tentatives = charger_moteur_push(base, {})
    ok = await envoyer(PID, "Nouvelle reservation", "Ana vient de reserver")
    vises = [t["endpoint"] for t in tentatives]
    verifier("E1. exactement 3 appareils sont sollicites", len(vises) == 3, len(vises))
    verifier("E2. ce sont les 3 plus RECEMMENT enregistres",
             set(vises) == {"https://fcm/recent1", "https://fcm/recent2", "https://fcm/recent3"}, vises)
    verifier("E3. l'envoi est declare reussi", ok is True, ok)
    verifier("E4. TTL explicite (V434), jamais 0",
             all(t["ttl"] == 3600 for t in tentatives), [t["ttl"] for t in tentatives])

    # --- E bis. endpoint en double -> un seul appel -------------------------
    base = Base()
    await base.push_subscriptions.insert_one(abo("https://fcm/MEME", "2026-09-06T11:00:00"))
    await base.push_subscriptions.insert_one(abo("https://fcm/MEME", "2026-09-06T10:00:00"))
    await base.push_subscriptions.insert_one(abo("https://fcm/AUTRE", "2026-09-06T09:00:00"))
    envoyer, _, tentatives = charger_moteur_push(base, {})
    await envoyer(PID, "t", "m")
    verifier("E5. un endpoint duplique n'est sollicite qu'une fois",
             [t["endpoint"] for t in tentatives].count("https://fcm/MEME") == 1,
             [t["endpoint"] for t in tentatives])

    # --- D. 410 -> CET endpoint seulement est desactive ---------------------
    base = Base()
    await base.push_subscriptions.insert_one(abo("https://fcm/MORT", "2026-09-06T11:00:00"))
    await base.push_subscriptions.insert_one(abo("https://fcm/VIVANT", "2026-09-06T10:00:00"))
    envoyer, _, tentatives = charger_moteur_push(base, {"https://fcm/MORT": 410})
    ok = await envoyer(PID, "t", "m")
    mort = await base.push_subscriptions.find_one({"subscription.endpoint": "https://fcm/MORT"})
    vivant = await base.push_subscriptions.find_one({"subscription.endpoint": "https://fcm/VIVANT"})
    verifier("D1. l'endpoint 410 est desactive", mort.get("active") is False, mort.get("active"))
    verifier("D2. l'autre appareil du MEME coach reste actif", vivant.get("active") is True, vivant.get("active"))
    verifier("D3. un appareil mort n'annule pas l'envoi vers les vivants", ok is True, ok)

    # --- 500 : refus temporaire, on ne desactive RIEN -----------------------
    base = Base()
    await base.push_subscriptions.insert_one(abo("https://fcm/TEMP", "2026-09-06T11:00:00"))
    envoyer, _, _ = charger_moteur_push(base, {"https://fcm/TEMP": 500})
    ok = await envoyer(PID, "t", "m")
    temp = await base.push_subscriptions.find_one({"subscription.endpoint": "https://fcm/TEMP"})
    verifier("D4. un 500 ne desactive PAS l'abonnement (stale != invalid)",
             temp.get("active") is True, temp.get("active"))
    verifier("D5. et l'envoi se declare en echec", ok is False, ok)


# ===========================================================================
# OBS — CE QUE PUSH-OBS AJOUTE
# ===========================================================================
async def scenario_observabilite():
    # --- l'inscription conserve la famille d'appareil -----------------------
    for ua, attendu in (
            ("Mozilla/5.0 (Linux; Android 14; SM-S928B) Chrome/127", "android"),
            ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) Safari", "ios"),
            ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/127", "mac"),
            ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/127", "windows"),
            ("", "inconnu")):
        base = Base()
        subscribe = charger_subscribe(base)
        await subscribe(Req({"participant_id": PID, "role": "coach", "email": COACH,
                             "subscription": {"endpoint": "https://fcm/X", "keys": {}}}, ua=ua))
        d = await base.push_subscriptions.find_one({"subscription.endpoint": "https://fcm/X"})
        verifier("OBS1. famille d'appareil = %s" % attendu, d.get("device_hint") == attendu,
                 d.get("device_hint"))

    # --- role et email cessent d'etre jetes ---------------------------------
    base = Base()
    subscribe = charger_subscribe(base)
    await subscribe(Req({"participant_id": PID, "role": "coach", "email": COACH,
                         "subscription": {"endpoint": "https://fcm/Y", "keys": {}}},
                        ua="Mozilla/5.0 (Linux; Android 14) Chrome"))
    d = await base.push_subscriptions.find_one({"subscription.endpoint": "https://fcm/Y"})
    verifier("OBS2. `role` est conserve (il etait jete)", d.get("role") == "coach", d.get("role"))
    verifier("OBS3. `email` est conserve (il etait jete)", d.get("email") == COACH, d.get("email"))
    verifier("OBS4. l'abonnement reste actif apres inscription", d.get("active") is True)

    # --- un corps sans role/email ne fabrique pas de champs vides -----------
    base = Base()
    subscribe = charger_subscribe(base)
    await subscribe(Req({"participant_id": PID,
                         "subscription": {"endpoint": "https://fcm/Z", "keys": {}}}, ua="Android"))
    d = await base.push_subscriptions.find_one({"subscription.endpoint": "https://fcm/Z"})
    verifier("OBS5. sans role fourni, aucun champ `role` invente", "role" not in d, sorted(d.keys()))
    verifier("OBS6. sans email fourni, aucun champ `email` invente", "email" not in d, sorted(d.keys()))

    # --- le verdict de FCM est CONSERVE, succes ET echec --------------------
    base = Base()
    await base.push_subscriptions.insert_one(abo("https://fcm/OK", "2026-09-06T11:00:00"))
    await base.push_subscriptions.insert_one(abo("https://fcm/KO", "2026-09-06T10:00:00"))
    envoyer, _, _ = charger_moteur_push(base, {"https://fcm/KO": 404})
    await envoyer(PID, "t", "m")
    bon = await base.push_subscriptions.find_one({"subscription.endpoint": "https://fcm/OK"})
    mauvais = await base.push_subscriptions.find_one({"subscription.endpoint": "https://fcm/KO"})
    verifier("OBS7. le succes ecrit le statut reel de FCM", bon.get("last_push_status") == "201",
             bon.get("last_push_status"))
    verifier("OBS8. l'echec ecrit AUSSI son statut", mauvais.get("last_push_status") == "404",
             mauvais.get("last_push_status"))
    verifier("OBS9. le RANG dans la selection V437 est conserve",
             bon.get("last_push_rank") == 1 and mauvais.get("last_push_rank") == 2,
             (bon.get("last_push_rank"), mauvais.get("last_push_rank")))
    verifier("OBS10. l'instant du dernier essai est conserve", bool(bon.get("last_push_at")))

    # --- l'observabilite ne fuit RIEN ---------------------------------------
    src = code_seul(extraire(SERVEUR, "send_push_notification"))
    verifier("OBS11. aucun endpoint complet journalise",
             "logger.info" in src and not re.search(r'logger\.\w+\([^)]*_endpoint[^)]*\)', src))
    verifier("OBS12. aucune cle p256dh/auth journalisee ni conservee",
             "p256dh" not in src and "auth\"" not in src)
    obs = extraire(SERVEUR, "send_push_by_email")
    verifier("OBS13. l'adresse n'est plus journalisee en clair, mais par empreinte",
             "sha256" in obs and "push_target_resolved" in obs)
    verifier("OBS14. les noms demandes existent : push_target_resolved / success / failure",
             "push_target_resolved" in SERVEUR and "push_success" in SERVEUR
             and "push_failure" in SERVEUR)
    verifier("OBS15. la trace ne cree AUCUNE collection nouvelle",
             "push_deliveries" not in SERVEUR and "push_logs" not in SERVEUR)
    verifier("OBS16. une trace ratee n'interrompt pas l'envoi",
             "_obs_verdict" in SERVEUR and re.search(r"async def _obs_verdict[\s\S]{0,900}?except Exception", SERVEUR))


# ===========================================================================
# J-K — SERVICE WORKER
# ===========================================================================
def scenario_sw():
    push = re.search(r"addEventListener\('push'[\s\S]*?^\}\);", SW, re.M)
    push = push.group(0) if push else ""
    verifier("J1. le SW lit le titre et le corps de la charge",
             "data.title" in push and "data.body" in push)
    verifier("J2. il affiche reellement la notification", "showNotification" in push)
    # PUSH-UI : `renotify` reste VRAI, mais il est desormais surchargeable.
    # `data.renotify !== false` dit exactement cela : vrai par defaut, faux
    # seulement si le serveur le demande explicitement. L'invariant tient.
    verifier("J3. `renotify` est vrai par defaut — une reservation qui remplace la precedente re-alerte",
             re.search(r"renotify:\s*(true|data\.renotify !== false)", push) is not None)
    verifier("J4. le tag reste surchargeable par le serveur (dette du tag commun non traitee ici)",
             "data.tag ||" in push)
    verifier("J5. une charge illisible ne casse pas le SW", "catch" in push)
    clic = re.search(r"addEventListener\('notificationclick'[\s\S]*?^\}\);", SW, re.M)
    clic = clic.group(0) if clic else ""
    verifier("K1. le clic ouvre l'URL portee par la notification",
             "notification.data" in clic and "url" in clic)
    verifier("K2. le clic ferme la notification", "notification.close()" in clic)
    verifier("K3. le clic ne casse jamais le SW", "catch" in clic)


# ===========================================================================
# HORS PORTEE — ce lot ne doit RIEN toucher d'autre
# ===========================================================================
def scenario_hors_portee():
    verifier("HP1. le deeplink Prospection n'est pas touche",
             "prospectionIntention" not in SERVEUR)
    verifier("HP2. la selection V437 garde sa borne a 3 appareils",
             "V437_MAX_APPAREILS = 3" in SERVEUR)
    verifier("HP3. le tri V433 (plus recents d'abord) est intact",
             'sort("updated_at", -1)' in SERVEUR)
    verifier("HP4. la mise au rebut P1-c est intacte",
             "superseded_at" in SERVEUR and "superseded_by" in SERVEUR)
    verifier("HP5. le canal e-mail coach (N2) est intact", "coach_email" in SHARED)
    verifier("HP6. aucune migration, aucun index ajoute",
             "create_index" not in extraire(SERVEUR, "subscribe_push"))
    verifier("HP7. les quatre canaux de la reservation sont toujours quatre",
             len(re.findall(r'bilan\["(client_email|coach_inapp|coach_push|coach_email)"\]',
                            SHARED)) >= 4)
    # L'ecriture PRECEDE la notification : sans cela, un push pourrait annoncer
    # une reservation qui n'existe pas (et le jeton d'idempotence, pose sur le
    # document, n'aurait rien ou se poser).
    verifier("HP8. la reservation est ECRITE avant que la notification soit planifiee",
             RESA.index("await db.reservations.insert_one(reservation_data)")
             < RESA.index("asyncio.create_task(_rc_notifier("))


async def principal():
    await scenario_parcours()
    await scenario_selection()
    await scenario_observabilite()
    scenario_sw()
    scenario_hors_portee()


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(principal())
    print("=" * 78)
    print("RESERVATION -> PUSH COACH + PUSH-OBS")
    print("=" * 78)
    for nom, ok, detail in resultats:
        print(("  PASS  " if ok else "  FAIL  ") + nom + ("" if ok else "   -> " + detail))
    reussis = sum(1 for _, ok, _ in resultats if ok)
    print("=" * 78)
    print("Push reels : 0 — base en memoire, FCM simule, aucun reseau")
    print("%d/%d verifications" % (reussis, len(resultats)))
    sys.exit(0 if reussis == len(resultats) else 1)
