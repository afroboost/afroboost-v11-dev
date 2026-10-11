#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V608 — point d'envoi Resend unique, accepté ≠ remis, webhook étendu, quota atomique.

AUCUN VRAI E-MAIL : faux fournisseur Resend ; MongoDB LOCAL et TEMPORAIRE (supprimé à la fin) ;
webhooks signés localement avec un secret de test.

    python3 -W "error:Flags not at the start:DeprecationWarning" tests/test_v608_resend_central.py
"""
import asyncio, base64, hashlib, hmac, json, os, re, shutil, socket, subprocess, sys, tempfile, time, uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
CLE = b"cle-de-test-webhook-v608"
os.environ["RESEND_WEBHOOK_SECRET"] = "whsec_" + base64.b64encode(CLE).decode()
os.environ["JWT_SECRET"] = "secret-de-test-v608"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v608:27017")
os.environ["RESEND_DAILY_LIMIT"] = "100"
os.environ["RESEND_DAILY_SAFETY_LIMIT"] = "95"
import api.server as S  # noqa: E402
import api.resend_central as RC  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402

R = []
def verifier(nom, cond, detail=""):
    R.append(bool(cond)); print("  %-6s %s" % ("OK  " if cond else "ECHEC", nom))
    if detail and not cond: print("           ->", detail)

# ---------------------------------------------------------------- MongoDB local
mongod = shutil.which("mongod")
if not mongod:
    print("mongod absent"); sys.exit(1)
dossier = tempfile.mkdtemp(prefix="v608-mongo-")
with socket.socket() as so:
    so.bind(("127.0.0.1", 0)); PORT = so.getsockname()[1]
proc = subprocess.Popen([mongod, "--dbpath", dossier, "--port", str(PORT), "--bind_ip", "127.0.0.1", "--quiet"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
for _ in range(80):
    try:
        socket.create_connection(("127.0.0.1", PORT), timeout=0.5).close(); break
    except OSError:
        time.sleep(0.25)
URL = "mongodb://127.0.0.1:%d" % PORT
SYNC = MongoClient(URL)["v608"]
APPELS = []
def faux_resend(params, options=None):
    APPELS.append((params, options))
    return {"id": "re_" + uuid.uuid4().hex[:12]}
RC.configurer(base=SYNC, transport=faux_resend)

def raz_quota(n=0, critique_plancher=None):
    now = datetime.now(timezone.utc)
    SYNC[RC.COL_QUOTA].delete_many({"_id": RC.DOC_QUOTA})   # le RÉGLAGE (autre document) est conservé
    SYNC[RC.COL_QUOTA].insert_one({"_id": RC.DOC_QUOTA, "tentatives": [(now - timedelta(minutes=5)).isoformat()] * n,
                                   "plancher": 0, "plancher_expire_at": ""})

class Req:
    def __init__(self, corps: bytes, entetes: dict):
        self._c, self.headers = corps, entetes
    async def body(self):
        return self._c

def signe(evt: dict, eid=None, mauvaise=False):
    corps = json.dumps(evt).encode()
    eid = eid or "msg_" + uuid.uuid4().hex[:10]
    ts = str(int(time.time()))
    sig = base64.b64encode(hmac.new(CLE, ("%s.%s.%s" % (eid, ts, corps.decode())).encode(), hashlib.sha256).digest()).decode()
    if mauvaise:
        sig = base64.b64encode(b"x" * 32).decode()
    return Req(corps, {"svix-id": eid, "svix-timestamp": ts, "svix-signature": "v1," + sig})

async def scenario():
    S.db = AsyncIOMotorClient(URL)["v608"]
    db = S.db
    hook = S.p3u3_webhook_resend

    print("\n0. Point d'envoi : même interface, journal, accepté")
    raz_quota(0)
    r = RC.emails("test:envoi", critique=False).send({"from": "a@x", "to": ["t@test.invalid"], "subject": "s", "text": "t"},
                                                     {"idempotency_key": "k1"})
    j = SYNC[RC.COL_JOURNAL].find_one({"resend_id": r["id"]})
    verifier("retour identique au SDK (id) + options transmises telles quelles", r["id"].startswith("re_") and APPELS[-1][1] == {"idempotency_key": "k1"})
    verifier("journal : accepted, source, destinataire, aucune clé ni contenu", j and j["provider_status"] == "accepted" and j["source"] == "test:envoi"
             and j["destinataire"] == "t@test.invalid" and "text" not in j and "api_key" not in json.dumps(j, default=str))

    # données métier minimales (TEST, base locale)
    await db[S.P3S3_ACTIONS].insert_one({"id": "act-A", "coach_id": "coach@test", "target": "rel@test.invalid",
        "sent_at": "2026-10-11T08:00:00+00:00", "provider_message_id": "re_j0", "provider_status": "accepted", "suivi_livraison": True,
        "j3_sent_at": "2026-10-14T08:00:00+00:00", "j3_provider_message_id": "re_j3", "j3_provider_status": "accepted",
        "prospect_ids": ["T-1"], "recipient_key": "T-1"})
    async def trace(rid, **k):
        await db[S.P3AI4_COLLECTION].insert_one(dict({"id": "tr-" + rid, "inbound_id": "in-" + rid, "action_id": "act-" + rid,
            "coach_id": "coach@test", "to_email": rid + "@test.invalid", "organisation": "TEST", "intention": "positif",
            "send_status": "envoye", "provider_message_id": rid, "provider_status": "accepted", "suivi_livraison": True,
            "sent_at": "2026-10-11T10:00:00+00:00"}, **k))

    print("\nA. accepted puis delivered → Remis")
    await trace("re_A")
    rep = await hook(signe({"type": "email.delivered", "data": {"email_id": "re_A"}}))
    t = await db[S.P3AI4_COLLECTION].find_one({"id": "tr-re_A"})
    notes = await db[S.P3N_COLLECTION].count_documents({"inbound_id": "in-re_A", "origine": "remise"})
    verifier("provider_status delivered → état « remis »", t["provider_status"] == "delivered" and S.v608_etat_envoi(t) == "remis", rep)
    verifier("une note de remise (l'état commercial avance à la remise)", notes == 1)

    print("\nB. accepted puis failed → Échec, conversation reste « à répondre »")
    await trace("re_B")
    await hook(signe({"type": "email.failed", "data": {"email_id": "re_B", "failed": {"reason": "Mailbox unavailable"}}}))
    t = await db[S.P3AI4_COLLECTION].find_one({"id": "tr-re_B"})
    verifier("état « echec », raison brute gardée, réessai permis", S.v608_etat_envoi(t) == "echec" and t["provider_raison"] == "Mailbox unavailable" and S.v608_reessai_permis(t))
    verifier("aucune note de remise (pas de faux « répondu »)", await db[S.P3N_COLLECTION].count_documents({"inbound_id": "in-re_B"}) == 0)
    verifier("aucune nouvelle tentative automatique (aucun appel fournisseur)", len(APPELS) == 1)

    print("\nC. failed quota → « Non envoyé — quota », adresse NON bloquée")
    await trace("re_C")
    await hook(signe({"type": "email.failed", "data": {"email_id": "re_C", "failed": {"reason": "Reached the daily sending quota: You reached your daily sending quota."}}}))
    t = await db[S.P3AI4_COLLECTION].find_one({"id": "tr-re_C"})
    refus = await S.c3_refus_exprimes("email", ["re_c@test.invalid"])
    verifier("état « quota » (problème de COMPTE), réessai permis", S.v608_etat_envoi(t) == "quota" and S.v608_reessai_permis(t))
    verifier("adresse PAS inscrite au registre STOP", not refus)

    print("\nD. rebond permanent (relance J+3) → adresse bloquée, relances annulées")
    await hook(signe({"type": "email.bounced", "data": {"email_id": "re_j3", "bounce": {"type": "Permanent", "subType": "General", "message": "no such user"}}}))
    a = await db[S.P3S3_ACTIONS].find_one({"id": "act-A"})
    verifier("j3_provider_status bounced + J+7/J+14 annulées", a["j3_provider_status"] == "bounced" and a.get("j7_annule_le") and a.get("j14_annule_le"), a)
    verifier("adresse inscrite au registre STOP", bool(await S.c3_refus_exprimes("email", ["rel@test.invalid"])))

    print("\nE. rebond temporaire (réponse) → signalé, adresse conservée")
    await trace("re_E")
    await hook(signe({"type": "email.bounced", "data": {"email_id": "re_E", "bounce": {"type": "Transient", "subType": "MailboxFull"}}}))
    t = await db[S.P3AI4_COLLECTION].find_one({"id": "tr-re_E"})
    verifier("état « rebond », adresse non bloquée", S.v608_etat_envoi(t) == "rebond" and not await S.c3_refus_exprimes("email", ["re_e@test.invalid"]))

    print("\nF. plainte → plus d'envoi automatique vers l'adresse")
    await trace("re_F")
    await hook(signe({"type": "email.complained", "data": {"email_id": "re_F"}}))
    t = await db[S.P3AI4_COLLECTION].find_one({"id": "tr-re_F"})
    verifier("état « plainte » + registre STOP", S.v608_etat_envoi(t) == "plainte" and bool(await S.c3_refus_exprimes("email", ["re_f@test.invalid"])))

    print("\nG. même webhook deux fois → un seul effet")
    await trace("re_G")
    req1 = signe({"type": "email.delivered", "data": {"email_id": "re_G"}}, eid="msg_meme")
    req2 = signe({"type": "email.delivered", "data": {"email_id": "re_G"}}, eid="msg_meme")
    await hook(req1); r2 = await hook(req2)
    verifier("seconde réception reconnue comme doublon", (r2.get("suivi") or {}).get("doublon") or r2.get("doublon"), r2)
    verifier("une seule note de remise", await db[S.P3N_COLLECTION].count_documents({"inbound_id": "in-re_G", "origine": "remise"}) == 1)
    await hook(signe({"type": "email.sent", "data": {"email_id": "re_A"}}))
    verifier("jamais de recul : « sent » après « delivered » ne rétrograde pas", (await db[S.P3AI4_COLLECTION].find_one({"id": "tr-re_A"}))["provider_status"] == "delivered")

    print("\nH. signature invalide → 401, aucune écriture")
    avant = await db[S.V608_EVENEMENTS].count_documents({})
    try:
        await hook(signe({"type": "email.delivered", "data": {"email_id": "re_B"}}, mauvaise=True)); code = 200
    except HTTPException as e:
        code = e.status_code
    verifier("HTTP 401", code == 401, code)
    verifier("aucune écriture", await db[S.V608_EVENEMENTS].count_documents({}) == avant
             and (await db[S.P3AI4_COLLECTION].find_one({"id": "tr-re_B"}))["provider_status"] == "failed")

    print("\nI. 94 consommés, 2 envois simultanés non critiques → un seul passe")
    raz_quota(94); n0 = len(APPELS)
    def un():
        try:
            RC.emails("test:concurrence").send({"to": ["c@test.invalid"], "subject": "s", "text": "t"}); return True
        except RC.QuotaResendAtteint:
            return False
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda _: un(), range(2)))
    verifier("une seule autorisée, l'autre bloquée AVANT Resend", sum(res) == 1 and len(APPELS) - n0 == 1, res)
    raz_quota(85)
    with ThreadPoolExecutor(16) as ex:
        res = list(ex.map(lambda _: un(), range(40)))
    verifier("40 simultanées pour 10 places → exactement 10", sum(res) == 10, sum(res))

    print("\nJ/K/L. seuil 95, réserve critique, plafond 100")
    raz_quota(95); n0 = len(APPELS)
    try:
        RC.emails("prospection:j0_relances").send({"to": ["p@test.invalid"]}); passe = True
    except RC.QuotaResendAtteint as q:
        passe = False; msg = q.message
    verifier("J. non critique bloqué à 95, Resend non appelé, message clair", not passe and len(APPELS) == n0 and "quota Resend atteint" in msg)
    verifier("J. journal : bloque_quota", SYNC[RC.COL_JOURNAL].find_one({"source": "prospection:j0_relances", "provider_status": "bloque_quota"}) is not None)
    RC.emails("server:b3s1_demander_otp", critique=True).send({"to": ["otp@test.invalid"]})
    verifier("K. critique autorisé dans la réserve 95-100", len(APPELS) == n0 + 1)
    raz_quota(100)
    try:
        RC.emails("server:b3s1_demander_otp", critique=True).send({"to": ["otp@test.invalid"]}); passe = True
    except RC.QuotaResendAtteint:
        passe = False
    verifier("L. à 100, même un critique est bloqué AVANT Resend", not passe and len(APPELS) == n0 + 1)

    print("\nRéconciliation avec le compte Resend (envois extérieurs)")
    raz_quota(80); now = datetime.now(timezone.utc)
    page = {"data": [{"id": "e%d" % i, "created_at": (now - timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S.000000+00")} for i in range(90)]
            + [{"id": "vieux", "created_at": (now - timedelta(hours=30)).strftime("%Y-%m-%d %H:%M:%S.000000+00")}], "has_more": False}
    RC.reconcilier_avec_resend(lister=lambda apres: page)
    e = RC.etat()
    verifier("plancher = 90 (le compte, pas seulement Afroboost) ; effectif 90 (jamais baissé)", e["plancher_resend"] == 90 and e["compte_effectif"] == 90, e)
    ok = 0
    for _ in range(10):
        try:
            RC.emails("test:rec").send({"to": ["r@test.invalid"]}); ok += 1
        except RC.QuotaResendAtteint:
            pass
    verifier("le plancher AVANCE avec nos envois : 5 places non critiques (90→95), pas 15", ok == 5, ok)

    print("\nRéessai d'une réponse en échec : nouvelle clé d'idempotence, une seule reprise")
    t = {"send_status": "echec", "provider_status": "failed"}
    verifier("échec réessayable ; « indéterminé » jamais (un e-mail a pu partir)",
             S.v608_reessai_permis(t) and not S.v608_reessai_permis({"send_status": "indetermine"})
             and not S.v608_reessai_permis({"send_status": "envoye", "provider_status": "accepted"}))

    print("\nRÉGLAGE « Limiter les envois Resend » (persistant, super-admin)")
    SYNC[RC.COL_QUOTA].delete_many({"_id": RC.DOC_REGLAGES})
    verifier("valeurs initiales : ON, 100 / 95", RC.reglages()["actif"] is True and RC.limites()["limite"] == 100 and RC.limites()["seuil"] == 95)
    RC.enregistrer_reglages(True, 100, 95, "admin@test")
    raz_quota(95); n0 = len(APPELS)
    try:
        RC.emails("test:reglage").send({"to": ["x@test.invalid"]}); passe = True
    except RC.QuotaResendAtteint:
        passe = False
    verifier("A. ON 100/95 → non critique bloqué à 95", not passe and len(APPELS) == n0)
    RC.enregistrer_reglages(False, 100, 95, "admin@test")
    raz_quota(150); n0 = len(APPELS)
    RC.emails("test:reglage").send({"to": ["x@test.invalid"]})
    RC.emails("test:reglage").send({"to": ["x@test.invalid"]})
    verifier("B. OFF → le garde-fou local ne bloque pas (même à 150), le comptage continue",
             len(APPELS) == n0 + 2 and RC.etat()["compte_effectif"] == 152 and RC.etat()["reglages"]["actif"] is False)
    RC.enregistrer_reglages(True, 500, 475, "admin@test")
    raz_quota(474)
    RC.emails("test:reglage").send({"to": ["x@test.invalid"]})
    try:
        RC.emails("test:reglage").send({"to": ["x@test.invalid"]}); passe = True
    except RC.QuotaResendAtteint as q:
        passe = False; msg = q.message
    RC.emails("test:otp", critique=True).send({"to": ["o@test.invalid"]})
    verifier("C. ON 500/475 → non critique bloqué à 475, critique passe dans la réserve", not passe and "475" in msg)
    RC.enregistrer_reglages(False, 500, 475, "admin@test")
    RC.configurer(base=MongoClient(URL)["v608"], transport=faux_resend)   # « redémarrage » : nouvelle connexion
    verifier("D. ON → OFF persistant après redémarrage simulé", RC.reglages()["actif"] is False and RC.reglages()["source"] == "base")
    r = RC.enregistrer_reglages(True, RC.reglages()["limite"], RC.reglages()["seuil"], "admin@test")
    verifier("E. OFF → ON : valeurs précédentes récupérées (500 / 475)", r["actif"] and r["limite"] == 500 and r["seuil"] == 475)
    for mauvais in ((True, 100, 101), (True, 0, 0), ("oui", 100, 95), (True, "abc", 95)):
        try:
            RC.enregistrer_reglages(*mauvais); ok_ = False
        except ValueError:
            ok_ = True
        verifier("valeur incohérente refusée %s" % (mauvais,), ok_)
    RC.enregistrer_reglages(False, 100, 95, "admin@test")
    await trace("re_OFF_F"); await trace("re_OFF_G")
    await hook(signe({"type": "email.failed", "data": {"email_id": "re_OFF_F", "failed": {"reason": "Reached the daily sending quota"}}}))
    await hook(signe({"type": "email.delivered", "data": {"email_id": "re_OFF_G"}}))
    tf = await db[S.P3AI4_COLLECTION].find_one({"id": "tr-re_OFF_F"})
    tg = await db[S.P3AI4_COLLECTION].find_one({"id": "tr-re_OFF_G"})
    verifier("F. OFF + email.failed (quota Resend) → échec enregistré, « quota », adresse non bloquée",
             tf["provider_status"] == "failed" and S.v608_etat_envoi(tf) == "quota" and not await S.c3_refus_exprimes("email", ["re_off_f@test.invalid"]))
    verifier("G. OFF + delivered → « Remis » enregistré", tg["provider_status"] == "delivered" and S.v608_etat_envoi(tg) == "remis")
    RC.enregistrer_reglages(True, 100, 95, "admin@test")
    for route, corps in ((S.v608_reglages_resend, b'{"actif": false, "limite": 100, "seuil": 95}'), (S.v608_etat_resend, b"")):
        try:
            await route(Req(corps, {})); code = 200
        except HTTPException as e:
            code = e.status_code
        verifier("%s sans super-admin signé → 403" % route.__name__, code == 403, code)
    verifier("le refus n'a rien modifié", RC.reglages()["actif"] is True)

    print("\nM. 49 points d'appel → tous par le point unique")
    sortie = subprocess.run(["grep", "-rnE", "--include=*.py", r"\b(resend|_r|resend_lib|_resend_lib)\.Emails\.send\b", os.path.join(RACINE, "api")],
                            capture_output=True, text=True).stdout.strip().split("\n")
    hors = [l for l in sortie if l and "resend_central.py" not in l and "`resend.Emails.send`" not in l]
    via = subprocess.run(["grep", "-rnoE", "--include=*.py", "--exclude=resend_central.py", r"_rc\.emails\(", os.path.join(RACINE, "api")], capture_output=True, text=True).stdout.strip().split("\n")
    verifier("0 appel direct au SDK hors point unique", not hors, hors)
    verifier("49 appels passent par _rc.emails(...)", len([v for v in via if v]) == 49, len(via))

asyncio.run(scenario())
proc.terminate(); proc.wait(timeout=10); shutil.rmtree(dossier, ignore_errors=True)
ok = sum(R); print("\n%d/%d vérifications réussies (base locale supprimée, aucun e-mail réel)" % (ok, len(R)))
sys.exit(0 if ok == len(R) else 1)
