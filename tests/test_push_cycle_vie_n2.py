# -*- coding: utf-8 -*-
"""
CYCLE DE VIE DU PUSH (P1) + E-MAIL COACH (N2).

LE FAIT MESURE QUI A TOUT DECIDE. FCM fait tourner l'endpoint d'un navigateur
en permanence — 1 a 10 nouveaux par jour. Chaque rotation creait un document et
laissait le precedent `active: True` a jamais : 196 endpoints pour un ou deux
appareils reels, 185 actifs, 11 retires. Le serveur pariait sur les trois plus
recemment ENREGISTRES, et l'enregistrement n'a lieu qu'au chargement du
dashboard. Le 18/08/2026, l'endpoint vivant a ete inscrit 1 min 49 s APRES le
push : celui-ci est parti vers un endpoint deja peime du MEME navigateur, que
FCM accepte encore silencieusement.

CE QUI EST TESTE ICI
  P1-c  la mise au rebut de l'endpoint REMPLACE, declaree par le navigateur —
        et seulement celui-la : les autres appareils ne bougent pas.
  P2    « aucun_abonnement » cesse d'etre confondu avec « echec ».
  N2    l'e-mail coach, quatrieme canal, idempotent et non bloquant.
  N1    le push participant sur le parcours qui en etait prive.

Les VRAIES fonctions sont executees (`subscribe_push`,
`notifier_reservation_creee`, `_send_coach_reservation_email`).

HORS LIGNE. Aucune connexion, aucune ecriture, aucune donnee de production.

    python3 tests/test_push_cycle_vie_n2.py
"""
import asyncio
import io
import os
import re
import sys
import types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def lire(*b):
    return io.open(os.path.join(RACINE, *b), encoding="utf-8").read()

SERVEUR = lire("api", "server.py")
SHARED = lire("api", "routes", "shared.py")
RESA = lire("api", "routes", "reservation_routes.py")
DASH = lire("frontend", "src", "components", "CoachDashboard.js")
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
# Base simulee — chemins POINTES obligatoires (`subscription.endpoint`)
# ---------------------------------------------------------------------------
def _lire(d, chemin):
    cur = d
    for part in str(chemin).split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None, False
        cur = cur[part]
    return cur, True

def _ecrire(d, chemin, valeur):
    parts = str(chemin).split(".")
    cur = d
    for part in parts[:-1]:
        if not isinstance(cur.get(part), dict):
            cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = valeur


class Col:
    def __init__(self):
        self.docs = []
    def _m(self, d, f):
        for k, v in (f or {}).items():
            if k == "$or":
                if not any(self._m(d, sf) for sf in v):
                    return False
                continue
            val, present = _lire(d, k)
            if isinstance(v, dict) and "$in" in v:
                if val not in v["$in"]: return False
            elif isinstance(v, dict) and "$ne" in v:
                if val == v["$ne"]: return False
            elif isinstance(v, dict) and "$exists" in v:
                if present != v["$exists"]: return False
            elif val != v:
                return False
        return True
    async def find_one(self, f=None, proj=None):
        for d in self.docs:
            if self._m(d, f or {}): return dict(d)
        return None
    def find(self, f=None, proj=None):
        parent = self
        class _C:
            def sort(self, *a, **k): return self
            async def to_list(self, n=None):
                return [dict(d) for d in parent.docs if parent._m(d, f or {})]
        return _C()
    async def insert_one(self, d): self.docs.append(dict(d))
    async def count_documents(self, f=None):
        return len([d for d in self.docs if self._m(d, f or {})])
    async def update_one(self, f, maj, upsert=False):
        class _R:
            def __init__(s, n): s.matched_count = n; s.modified_count = n
        for d in self.docs:
            if self._m(d, f):
                for k, v in (maj.get("$set") or {}).items(): _ecrire(d, k, v)
                for k in (maj.get("$unset") or {}): d.pop(k, None)
                return _R(1)
        if upsert:
            neuf = {}
            for k, v in (maj.get("$setOnInsert") or {}).items(): _ecrire(neuf, k, v)
            for k, v in (maj.get("$set") or {}).items(): _ecrire(neuf, k, v)
            for k, v in (f or {}).items():
                if not isinstance(v, dict): _ecrire(neuf, k, v)
            self.docs.append(neuf); return _R(0)
        return _R(0)


class Base:
    def __init__(self):
        self.push_subscriptions = Col()
        self.notifications = Col()
        self.reservations = Col()
        self.courses = Col()
    def __getitem__(self, n): return getattr(self, n)


class HTTPException(Exception):
    def __init__(self, status_code=None, detail=None, headers=None):
        self.status_code, self.detail, self.headers = status_code, detail, headers or {}


class Req:
    def __init__(self, corps): self._c = corps
    async def json(self): return self._c
    headers = {}


def charger_subscribe(base):
    import datetime, logging
    esp = {"db": base, "HTTPException": HTTPException, "Request": object,
           "datetime": datetime.datetime, "timezone": datetime.timezone,
           "logger": logging.getLogger("t")}
    exec(compile(extraire(SERVEUR, "subscribe_push"), "<s>", "exec"), esp)
    return esp["subscribe_push"]


def charger_moteur(base):
    import datetime, logging
    esp = {"db": base, "datetime": datetime.datetime, "timezone": datetime.timezone,
           "logger": logging.getLogger("t"), "re": re}
    for fn in ("normaliser_email", "_rc_reserver_jeton", "_rc_cloturer_jeton",
               "resoudre_coach_de_reservation", "notifier_reservation_creee"):
        exec(compile(extraire(SHARED, fn), "<sh>", "exec"), esp)
    return esp["notifier_reservation_creee"]


PID = "coach_bassi@test.ch"
def abo(ep, maj, actif=True, pid=PID):
    return {"participant_id": pid, "subscription": {"endpoint": ep},
            "active": actif, "updated_at": maj}


async def scenario_p1c():
    subscribe = None

    # --- 1. endpoint deja connu -> aucun doublon -----------------------------
    base = Base(); subscribe = charger_subscribe(base)
    await base.push_subscriptions.insert_one(abo("https://fcm/A", "2026-08-18T09:00:00"))
    await subscribe(Req({"participant_id": PID, "subscription": {"endpoint": "https://fcm/A"}}))
    verifier("1. endpoint deja connu -> AUCUN doublon",
             len(base.push_subscriptions.docs) == 1, len(base.push_subscriptions.docs))
    verifier("1b. il reste actif", base.push_subscriptions.docs[0]["active"] is True)

    # --- 2. endpoint REMPLACE -> ancien invalide, nouveau actif --------------
    base = Base(); subscribe = charger_subscribe(base)
    await base.push_subscriptions.insert_one(abo("https://fcm/VIEUX", "2026-08-18T09:00:00"))
    await subscribe(Req({"participant_id": PID,
                         "subscription": {"endpoint": "https://fcm/NEUF"},
                         "previous_endpoint": "https://fcm/VIEUX"}))
    _v = await base.push_subscriptions.find_one({"subscription.endpoint": "https://fcm/VIEUX"})
    _n = await base.push_subscriptions.find_one({"subscription.endpoint": "https://fcm/NEUF"})
    verifier("2. l'ancien endpoint est INVALIDE", _v and _v.get("active") is False, _v)
    verifier("2b. le nouveau est actif", _n and _n.get("active") is True, _n)
    verifier("2c. la mise au rebut est tracee",
             _v and _v.get("superseded_by") == "https://fcm/NEUF", _v)

    # --- 3. les AUTRES appareils restent actifs ------------------------------
    base = Base(); subscribe = charger_subscribe(base)
    await base.push_subscriptions.insert_one(abo("https://fcm/MAC-VIEUX", "2026-08-18T09:00:00"))
    await base.push_subscriptions.insert_one(abo("https://fcm/TELEPHONE", "2026-06-01T09:00:00"))
    await subscribe(Req({"participant_id": PID,
                         "subscription": {"endpoint": "https://fcm/MAC-NEUF"},
                         "previous_endpoint": "https://fcm/MAC-VIEUX"}))
    _tel = await base.push_subscriptions.find_one({"subscription.endpoint": "https://fcm/TELEPHONE"})
    verifier("3. LE TELEPHONE RESTE ACTIF (multi-appareils preserve)",
             _tel and _tel.get("active") is True, _tel)
    verifier("3b. seul le Mac remplace est eteint",
             sum(1 for d in base.push_subscriptions.docs if not d.get("active")) == 1,
             [(d["subscription"]["endpoint"], d.get("active")) for d in base.push_subscriptions.docs])

    # --- 3c. l'age SEUL n'eteint jamais rien (stale != invalid) --------------
    verifier("3c. le telephone de juin n'est PAS eteint par son age",
             _tel.get("active") is True and "superseded_at" not in _tel)

    # --- 4. portee : un AUTRE proprietaire ne peut rien eteindre -------------
    base = Base(); subscribe = charger_subscribe(base)
    await base.push_subscriptions.insert_one(abo("https://fcm/VICTIME", "2026-08-18T09:00:00",
                                                pid="coach_autre@test.ch"))
    await subscribe(Req({"participant_id": PID,
                         "subscription": {"endpoint": "https://fcm/MOI"},
                         "previous_endpoint": "https://fcm/VICTIME"}))
    _vic = await base.push_subscriptions.find_one({"subscription.endpoint": "https://fcm/VICTIME"})
    verifier("4. l'endpoint d'un AUTRE coach est intouchable",
             _vic and _vic.get("active") is True, _vic)

    # --- 5. previous == courant -> on ne se coupe pas soi-meme ---------------
    base = Base(); subscribe = charger_subscribe(base)
    await base.push_subscriptions.insert_one(abo("https://fcm/A", "2026-08-18T09:00:00"))
    await subscribe(Req({"participant_id": PID,
                         "subscription": {"endpoint": "https://fcm/A"},
                         "previous_endpoint": "https://fcm/A"}))
    _a = await base.push_subscriptions.find_one({"subscription.endpoint": "https://fcm/A"})
    verifier("5. previous == courant -> l'abonnement reste ACTIF",
             _a and _a.get("active") is True, _a)

    # --- 6. pas d'accumulation sur N connexions successives ------------------
    base = Base(); subscribe = charger_subscribe(base)
    precedent = None
    for i in range(8):
        ep = "https://fcm/ROT%d" % i
        await subscribe(Req({"participant_id": PID, "subscription": {"endpoint": ep},
                             "previous_endpoint": precedent}))
        precedent = ep
    actifs = [d for d in base.push_subscriptions.docs if d.get("active")]
    verifier("6. 8 rotations -> UN SEUL endpoint actif (fin de l'accumulation)",
             len(actifs) == 1 and actifs[0]["subscription"]["endpoint"] == "https://fcm/ROT7",
             [(d["subscription"]["endpoint"], d.get("active")) for d in base.push_subscriptions.docs])
    verifier("6b. les 7 precedents sont conserves en base, simplement inactifs",
             len(base.push_subscriptions.docs) == 8)


RESA_PON = {"id": "r-pon", "userEmail": "a@x.ch", "userName": "Ana Test",
            "courseName": "Workshop", "courseId": "c1",
            "datetime": "2026-08-22T14:00:00", "coach_id": "bassi@test.ch",
            "reservationCode": "AF1", "quantity": 1}
RESA_REC = dict(RESA_PON, id="r-rec", courseName="Session Cardio",
                datetime="2026-08-19T18:30:00", reservationCode="AF2")


async def scenario_n2_p2():
    async def poser(base, r):
        await base.reservations.insert_one(dict(r)); return dict(r)

    for nom, resa in (("ponctuel", RESA_PON), ("recurrent", RESA_REC)):
        base = Base(); moteur = charger_moteur(base)
        await base.push_subscriptions.insert_one(abo("https://fcm/OK", "2026-08-18T16:00:00",
                                                    pid="coach_bassi@test.ch"))
        mails = []
        async def _mc(_r): return True
        async def _pc(*a, **k): return True
        async def _ec(coach, r): mails.append((coach, r.get("reservationCode"))); return True
        b = await moteur(base, await poser(base, resa), envoyer_email_client=_mc,
                         envoyer_push_coach=_pc, envoyer_email_coach=_ec)
        verifier("N2 %s -> e-mail coach envoye" % nom, b["coach_email"] == "envoye", b)
        verifier("N2 %s -> UN seul e-mail" % nom, len(mails) == 1, mails)
        verifier("N2 %s -> adresse = coach RESOLU, pas une constante" % nom,
                 mails and mails[0][0] == "bassi@test.ch", mails)
        verifier("N2 %s -> push coach envoye" % nom, b["coach_push"] == "envoye", b)

    # --- rejeu x3 -> un seul e-mail ----------------------------------------
    base = Base(); moteur = charger_moteur(base)
    await base.push_subscriptions.insert_one(abo("https://fcm/OK", "2026-08-18T16:00:00",
                                                pid="coach_bassi@test.ch"))
    mails = []
    async def _mc(_r): return True
    async def _pc(*a, **k): return True
    async def _ec(coach, r): mails.append(coach); return True
    _r = await poser(base, RESA_REC)
    for _ in range(3):
        b = await moteur(base, _r, envoyer_email_client=_mc, envoyer_push_coach=_pc,
                         envoyer_email_coach=_ec)
    verifier("N2 rejeu x3 -> UN SEUL e-mail coach", len(mails) == 1, mails)
    verifier("N2 rejeu -> « deja_traite »", b["coach_email"] == "deja_traite", b)

    # --- panne e-mail coach -> le reste tient ------------------------------
    base = Base(); moteur = charger_moteur(base)
    await base.push_subscriptions.insert_one(abo("https://fcm/OK", "2026-08-18T16:00:00",
                                                pid="coach_bassi@test.ch"))
    async def _ec_casse(coach, r): raise RuntimeError("Resend indisponible")
    b = await moteur(base, await poser(base, RESA_PON), envoyer_email_client=_mc,
                     envoyer_push_coach=_pc, envoyer_email_coach=_ec_casse)
    verifier("N2 panne e-mail -> « echec », jamais « envoye »", b["coach_email"] == "echec", b)
    verifier("N2 panne e-mail -> la notification coach est quand meme la",
             b["coach_inapp"] == "envoye" and len(base.notifications.docs) == 1, b)
    verifier("N2 panne e-mail -> l'e-mail CLIENT part quand meme",
             b["client_email"] == "envoye", b)

    # --- P2 : aucun abonnement != echec ------------------------------------
    base = Base(); moteur = charger_moteur(base)          # aucune subscription
    b = await moteur(base, await poser(base, RESA_PON), envoyer_email_client=_mc,
                     envoyer_push_coach=_pc, envoyer_email_coach=_ec)
    verifier("P2. coach sans appareil -> « aucun_abonnement », PAS « echec »",
             b["coach_push"] == "aucun_abonnement", b)
    base = Base(); moteur = charger_moteur(base)
    await base.push_subscriptions.insert_one(abo("https://fcm/MORT", "2026-08-18T16:00:00",
                                                actif=False, pid="coach_bassi@test.ch"))
    b = await moteur(base, await poser(base, RESA_PON), envoyer_email_client=_mc,
                     envoyer_push_coach=_pc, envoyer_email_coach=_ec)
    verifier("P2b. tous les appareils inactifs -> « aucun_abonnement »",
             b["coach_push"] == "aucun_abonnement", b)
    base = Base(); moteur = charger_moteur(base)
    await base.push_subscriptions.insert_one(abo("https://fcm/OK", "2026-08-18T16:00:00",
                                                pid="coach_bassi@test.ch"))
    async def _pc_ko(*a, **k): return False
    b = await moteur(base, await poser(base, RESA_PON), envoyer_email_client=_mc,
                     envoyer_push_coach=_pc_ko, envoyer_email_coach=_ec)
    verifier("P2c. appareil present mais envoi rate -> « echec »", b["coach_push"] == "echec", b)

    # --- retro-compatibilite : sans envoyeur coach, comportement d'avant ----
    base = Base(); moteur = charger_moteur(base)
    await base.push_subscriptions.insert_one(abo("https://fcm/OK", "2026-08-18T16:00:00",
                                                pid="coach_bassi@test.ch"))
    b = await moteur(base, await poser(base, RESA_PON), envoyer_email_client=_mc,
                     envoyer_push_coach=_pc)
    verifier("retro. sans envoyeur coach -> coach_email None, les 3 autres inchanges",
             b["coach_email"] is None and b["client_email"] == "envoye"
             and b["coach_inapp"] == "envoye" and b["coach_push"] == "envoye", b)


def perimetre():
    # --- P1-c serveur ---
    _sub = code_seul(extraire(SERVEUR, "subscribe_push"))
    verifier("S1. la mise au rebut exige le MEME participant_id",
             '"participant_id": participant_id' in _sub and "previous_endpoint" in _sub)
    verifier("S2. aucun critere d'age dans la route",
             not re.search(r"90|days|timedelta", _sub), "stale != invalid")
    verifier("S3. un seul endpoint nomme est eteint, jamais une liste",
             '{"$set": {"active": False,' in _sub and "update_many" not in _sub)
    verifier("S4. la trace du remplacement est ecrite",
             "superseded_at" in _sub and "superseded_by" in _sub)
    verifier("S5. 404/410 reste le SECOND chemin d'invalidation, inchange",
             "status_code in [404, 410]" in SERVEUR)
    # ASSERTION CIBLEE : `server.py` porte 12 `delete_many` preexistants, sur
    # d'autres collections. Ce qui compte, c'est qu'AUCUNE operation de masse ne
    # touche les abonnements push — le stock historique n'est pas nettoye.
    verifier("S6. aucun nettoyage en masse des abonnements push",
             "push_subscriptions.delete_many" not in SERVEUR
             and "push_subscriptions.update_many" not in SERVEUR
             and "push_subscriptions.drop" not in SERVEUR)

    # --- P1-a service worker ---
    verifier("W1. le SW ecoute enfin pushsubscriptionchange",
             "addEventListener('pushsubscriptionchange'" in SW)
    verifier("W2. il declare l'ancien endpoint", "previous_endpoint" in SW)
    verifier("W3. il se reabonne avec la MEME cle si besoin",
             "applicationServerKey" in SW and "oldSubscription" in SW)
    verifier("W4. CACHE_NAME bumpe (sinon l'ancien SW survit)",
             "afroboost-v450" in SW)
    verifier("W5. ES5 strict : aucun const/let/arrow dans le bloc ajoute",
             not re.search(r"pushsubscriptionchange[\s\S]{0,2200}?(=>|\bconst\b|\blet\b)", SW))

    # --- P1-b / P1-d dashboard ---
    verifier("D1. le dashboard memorise le dernier endpoint",
             "af_push_last_endpoint" in DASH)
    verifier("D2. il transmet previous_endpoint", "previous_endpoint:" in DASH)
    verifier("D3. il depose le proprietaire pour le SW",
             "afroboost-push-owner" in DASH)
    _auto = DASH[DASH.index("V120: Auto-subscribe"):][:2600]
    verifier("D4. PLUS de requestPermission automatique au chargement",
             "requestPermission" not in _auto, "contrainte J")
    verifier("D5. la demande n'a lieu QUE sur clic explicite",
             "const p1Activer" in DASH and "Notification.requestPermission()" in DASH)
    verifier("D6. CAS 6 : bandeau « bloquees »", 'data-testid="p1-push-bloque"' in DASH)
    verifier("D7. CAS 7 : bouton d'activation", 'data-testid="p1-push-activer"' in DASH)
    verifier("D8. rien ne s'affiche quand tout va bien",
             "p1EtatPush === 'denied'" in DASH and "p1EtatPush === 'default'" in DASH
             and "p1EtatPush === 'ok'" not in DASH.split("data-testid=\"p1-push-bloque\"")[0][-400:])
    verifier("D9. icones SVG, aucun emoji ajoute",
             'SvgIcon name="warning"' in DASH and 'SvgIcon name="bell"' in DASH)

    # --- N1 ---
    _esp = code_seul(extraire(SERVEUR, "reserve_course_from_space"))
    verifier("N1-1. le parcours espace pousse enfin au participant",
             "send_push_by_email(" in _esp)
    verifier("N1-2. il utilise l'envoyeur DOCUMENTE (V433/V434), pas l'autre",
             "_send_push_to_email(" not in _esp)
    verifier("N1-3. detache : la reservation ne depend pas du push",
             "asyncio.create_task(send_push_by_email(" in _esp)
    verifier("N1-4. il cible l'occurrence reservee",
             "occurrence_iso" in _esp)

    # --- N2 ---
    # L'extraction par regex s'arrete au prochain `def`/`@` : ici la fonction
    # est suivie de CONSTANTES de module (SUPER_ADMIN_EMAILS...), qu'elle
    # avalait — et l'assertion N2-2 echouait sur du code qui n'est pas le sien.
    # On borne donc au corps reel.
    _ec = extraire(RESA, "_send_coach_reservation_email").split("# v9.5.8")[0]
    verifier("N2-1. l'envoyeur coach existe, ecrit UNE fois", bool(_ec))
    verifier("N2-2. il n'envoie PAS a SUPER_ADMIN_EMAIL",
             "SUPER_ADMIN_EMAIL" not in _ec, "piege de l'e-mail d'annulation")
    verifier("N2-3. il echappe tout ce qui vient du client", "escape as _esc" in _ec)
    verifier("N2-4. il rend un verdict, jamais un True en dur",
             _ec.count("return False") >= 2 and "return True" in _ec)
    verifier("N2-5. aucun code d'acces ni QR dans l'e-mail",
             "access_code" not in _ec and "qr" not in _ec.lower())
    verifier("N2-6. il annonce la DATE de l'occurrence, pas « chaque mercredi »",
             'reservation.get("datetime")' in _ec)
    verifier("N2-7. les DEUX routes injectent le MEME envoyeur",
             "envoyer_email_coach=_send_coach_reservation_email" in RESA
             and "envoyer_email_coach=_rc_email_coach" in SERVEUR)
    _mot = code_seul(extraire(SHARED, "notifier_reservation_creee"))
    verifier("N2-8. le canal est idempotent comme les trois autres",
             '_rc_reserver_jeton(db, rid, "coach_email"' in _mot)
    verifier("N2-9. quatre canaux, pas cinq",
             sorted(set(re.findall(r'bilan\["(\w+)"\]', _mot)))
             == ["client_email", "coach_email", "coach_inapp", "coach_push"])

    # --- hors perimetre : intact ---
    verifier("HP1. moteur de rappels intact",
             "cron_reservation_reminders" in SERVEUR and "reminders_enabled" in SERVEUR)
    verifier("HP2. recurrence intacte", "_v184_next_occurrences" in SERVEUR)
    verifier("HP3. moteur ESSAI intact",
             "_essai1_garde" in lire("api", "routes", "checkout_routes.py")
             and "_essai4_garde" in lire("api", "routes", "checkout_routes.py"))
    verifier("HP4. le tag commun n'est PAS touche (lot separe)",
             "data.tag || 'afroboost-push'" in SW and '"tag"' not in code_seul(extraire(SERVEUR, "send_push_notification")))
    verifier("HP5. aucune migration, aucun index",
             SERVEUR.count("create_index") == 7)


asyncio.run(scenario_p1c())
asyncio.run(scenario_n2_p2())
perimetre()

print("=" * 78)
echecs = 0
for nom, ok, det in resultats:
    print(("  PASS  " if ok else "  FAIL  ") + nom + ("" if ok else "   -> " + det[:110]))
    if not ok: echecs += 1
print("=" * 78)
print("Abonnements / e-mails / push REELS : 0 — base en memoire, envoyeurs simules")
print("%d/%d verifications" % (len(resultats) - echecs, len(resultats)))
sys.exit(1 if echecs else 0)
