#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0-B2 — LES 6 ROUTES REPORTÉES. AUCUN RÉSEAU, AUCUNE BASE RÉELLE, AUCUN RAPPEL RÉEL.

Application RÉELLE (`S.fastapi_app`, intergiciels compris) via httpx ASGITransport, base EN MÉMOIRE.

  A. visiteur supprime SON message ; B. message d'autrui / id deviné / groupe usurpé → refus ;
  C. création de conversation par le coach ; D. ajout de participant légitime ;
  E. conversation étrangère → refus ; F. notifications propres ; G. notifications d'autrui → intactes ;
  H. déclencheur interne des rappels intact (moteur SIMULÉ) ; I. appel externe → 401 ; J. Twilio → 410.
"""
try:
    import builtins as _b, os as _o, sys as _s
    _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
    import api.resend_central as _rc
    _b._rc = _rc
except Exception:  # noqa: BLE001
    pass
import asyncio
import base64
import io
import json
import os
import pathlib
import socket
import sys
import tempfile
import time

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
_TENT = []
_GA = socket.getaddrinfo


def _dns(h, p, *a, **k):
    if str(h) in ("localhost", "127.0.0.1", "::1", None, "testserver"):
        return _GA(h, p, *a, **k)
    _TENT.append(h)
    raise OSError("reseau interdit")


socket.getaddrinfo = _dns
SECRET = "secret-de-test-p0b-sans-aucun-rapport-avec-la-production-0123456789"
os.environ["JWT_SECRET"] = SECRET
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("RESEND_API_KEY", None)
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p0b2-inexistant:27017")

import httpx  # noqa: E402
import jwt as _jwt  # noqa: E402
import api.server as S  # noqa: E402

SA = "contact.artboost@gmail.com"
COACH_B = "coach.b.fictif@exemple.test"
COACH_C = "coach.c.fictif@exemple.test"
_BANC = os.path.join(RACINE, "tests", "test_p3s3b_preparation_campagne.py")
_src = io.open(_BANC, encoding="utf-8").read()
_esp = {"S": S, "asyncio": asyncio, "COACH_A": SA, "COACH_B": COACH_B, "INSTANT": "2026-10-19T08:00:00+00:00",
        "json": json, "os": os, "sys": sys, "_jwt": _jwt, "SECRET": SECRET, "HTTPException": S.HTTPException}
exec(compile(_src[_src.index("def lancer(coroutine):"):_src.index('# ============================================================================\nprint("\\n1.')],
             _BANC, "exec"), _esp)  # noqa: S102
BaseBouchon, _Col = _esp["BaseBouchon"], _esp["CollectionBouchon"]


class Col(_Col):
    async def update_one(self, filtre, maj, *a, **k):
        if "$push" in maj:
            for d in self.documents:
                if self._ok(d, filtre):
                    for c, v in maj["$push"].items():
                        d.setdefault(c, []).append(v)
                    d.update(maj.get("$set") or {})
                    return type("R", (), {"matched_count": 1, "modified_count": 1, "upserted_id": None})()
            return type("R", (), {"matched_count": 0, "modified_count": 0, "upserted_id": None})()
        return await super().update_one(filtre, maj, *a, **k)

    async def update_many(self, filtre, maj, *a, **k):
        n = 0
        for d in self.documents:
            if self._ok(d, filtre):
                d.update(maj.get("$set") or {}); n += 1
        return type("R", (), {"matched_count": n, "modified_count": n})()

    async def delete_one(self, filtre, *a, **k):
        for i, d in enumerate(self.documents):
            if self._ok(d, filtre):
                self.documents.pop(i)
                return type("R", (), {"deleted_count": 1})()
        return type("R", (), {"deleted_count": 0})()


R = []


def verifier(nom, ok, detail=""):
    R.append(bool(ok))
    print("  %-6s %s%s" % ("OK" if ok else "ECHEC", nom, "" if ok else "  -> %s" % detail))


def jeton(email):
    return _jwt.encode({"email": email, "sub": email, "role": "super_admin" if email == SA else "coach",
                        "exp": int(time.time()) + 3600}, SECRET, algorithm="HS256")


J_SA = {"Authorization": "Bearer " + jeton(SA)}
J_B = {"Authorization": "Bearer " + jeton(COACH_B)}
J_C = {"Authorization": "Bearer " + jeton(COACH_C)}
H_SA = {"X-User-Email": SA}
DOSSIER = pathlib.Path(tempfile.mkdtemp(prefix="p0b2_"))
S.EMOJIS_DIR = DOSSIER



def jeton_abonne(email):
    return _jwt.encode({"type": "subscriber", "email": email, "code": "AFR-T",
                        "exp": int(time.time()) + 3600}, SECRET, algorithm="HS256")


ALICE, BOB = "p-alice", "p-bob"
T_ALICE = {"X-Subscriber-Token": jeton_abonne("alice@exemple.test")}
T_BOB = {"X-Subscriber-Token": jeton_abonne("bob@exemple.test")}


def base():
    b = BaseBouchon([])
    msgs = [
        {"id": "m-a1", "session_id": "s1", "sender_id": ALICE, "sender_type": "user"},
        {"id": "m-c1", "session_id": "s1", "sender_id": COACH_B, "sender_type": "coach"},
        {"id": "m-b2", "session_id": "s2", "sender_id": BOB, "sender_type": "user"},
        {"id": "m-ga", "session_id": "g1", "sender_id": ALICE, "sender_type": "user"},
        {"id": "m-gb", "session_id": "g1", "sender_id": BOB, "sender_type": "user"},
    ]
    for nom, docs in {
        "coaches": [{"email": COACH_B, "is_active": True}, {"email": COACH_C, "is_active": True}],
        "coach_auth": [{"id": "coach_auth", "email": SA}],
        "chat_sessions": [{"id": "s1", "coach_id": COACH_B, "participant_ids": [ALICE], "mode": "ai"},
                          {"id": "s2", "coach_id": COACH_C, "participant_ids": [BOB], "mode": "ai"},
                          {"id": "g1", "coach_id": COACH_B, "participant_ids": [ALICE, BOB], "mode": "group"}],
        "chat_participants": [{"id": ALICE, "email": "alice@exemple.test"}, {"id": BOB, "email": "bob@exemple.test"}],
        "chat_messages": msgs, "campaigns": [{"id": "c1", "results": [{"sid": "SMfaux", "status": "sent"}]}],
        "feature_flags": [{"id": "feature_flags"}],
    }.items():
        b[nom] = Col(nom, docs)
    S.db = b
    S._p0a_cache["t"] = -1e9
    return b


def faire_q(m, chemin, h=None, params=None, corps=None, data=None):
    async def _go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=S.fastapi_app), base_url="http://testserver") as c:
            return await c.request(m, chemin, headers=h or {}, params=params, json=corps, data=data)
    return asyncio.get_event_loop().run_until_complete(_go())


def refus(r):
    return r.status_code in (401, 403)


def msg(b, i):
    return next(d for d in b["chat_messages"].documents if d["id"] == i)


def suppr(i, h=None, pid=None):
    return faire_q("PUT", "/api/chat/messages/%s/delete" % i, h, {"participant_id": pid} if pid is not None else None)


print("\nA. visiteur supprime SON message")
b = base()
r = suppr("m-a1", pid=ALICE)
verifier("A1 auteur (participant_id) → 200", r.status_code == 200, r.text)
verifier("A2 message marqué supprimé", msg(b, "m-a1").get("is_deleted") is True)
b = base()
r = suppr("m-ga", T_ALICE)
verifier("A3 groupe : auteur avec jeton abonné → 200", r.status_code == 200 and msg(b, "m-ga").get("is_deleted"), r.text)
b = base()
r = suppr("m-c1", J_B)
verifier("A4 coach propriétaire (JWT) → 200", r.status_code == 200 and msg(b, "m-c1").get("is_deleted"), r.text)
b = base()
r = suppr("m-b2", J_SA)
verifier("A5 super-admin (JWT) → 200", r.status_code == 200 and msg(b, "m-b2").get("is_deleted"), r.text)

print("\nB. message d'autrui / id deviné → refus")
b = base()
for nom, args in [("B1 anonyme sans preuve", ("m-a1",)),
                  ("B2 autre visiteur (son propre participant_id)", ("m-a1", None, BOB)),
                  ("B3 autre visiteur usurpant l'id visible", ("m-a1", None, ALICE + "x")),
                  ("B4 visiteur sur le message du COACH", ("m-c1", None, ALICE)),
                  ("B5 groupe : id d'Alice (visible de tous) sans jeton", ("m-ga", None, ALICE)),
                  ("B6 groupe : jeton de Bob sur le message d'Alice", ("m-ga", T_BOB, ALICE)),
                  ("B7 autre coach (JWT)", ("m-a1", J_C)),
                  ("B8 e-mail super-admin DÉCLARÉ", ("m-a1", H_SA)),
                  ("B9 e-mail du coach DÉCLARÉ", ("m-a1", {"X-User-Email": COACH_B})),
                  ("B10 id deviné inexistant", ("m-zzz", None, ALICE)),
                  ("B11 participant_id d'une autre conversation", ("m-b2", None, ALICE))]:
    r = suppr(*args)
    verifier(nom + " → 404", r.status_code == 404, "%s %s" % (r.status_code, r.text))
verifier("B12 AUCUN message supprimé", not any(d.get("is_deleted") for d in b["chat_messages"].documents))

print("\nC. création de conversation")
b = base()
r = faire_q("POST", "/api/chat/sessions", J_B, corps={"mode": "community", "is_ai_active": False, "title": "Groupe"})
verifier("C1 coach (JWT) → 200", r.status_code == 200, r.text)
verifier("C2 propriétaire = coach du jeton", r.status_code == 200 and r.json().get("coach_id") == COACH_B
         and any(d.get("coach_id") == COACH_B and d.get("title") == "Groupe" for d in b["chat_sessions"].documents))
n0 = len(b["chat_sessions"].documents)
for nom, h in [("C3 anonyme", None), ("C4 e-mail super-admin déclaré", H_SA), ("C5 e-mail coach déclaré", {"X-User-Email": COACH_B}),
               ("C6 jeton abonné", T_ALICE)]:
    r = faire_q("POST", "/api/chat/sessions", h, corps={"mode": "ai"})
    verifier(nom + " → refus", refus(r), "%s %s" % (r.status_code, r.text))
verifier("C7 aucune conversation créée par les refus", len(b["chat_sessions"].documents) == n0)

print("\nD/E. ajout de participant")
b = base()
r = faire_q("POST", "/api/chat/sessions/s1/add-participant", J_B, {"participant_id": BOB})
verifier("D1 coach propriétaire → 200", r.status_code == 200 and BOB in r.json().get("participant_ids", []), r.text)
b = base()
r = faire_q("POST", "/api/chat/sessions/s2/add-participant", J_SA, {"participant_id": ALICE})
verifier("D2 super-admin → 200", r.status_code == 200, r.text)
b = base()
for nom, h, code in [("E1 anonyme", None, (401, 403)), ("E2 autre coach", J_C, (404,)), ("E3 e-mail super-admin déclaré", H_SA, (401, 403)),
                     ("E4 jeton abonné", T_BOB, (401, 403))]:
    r = faire_q("POST", "/api/chat/sessions/s1/add-participant", h, {"participant_id": BOB})
    verifier(nom + " → refus", r.status_code in code, "%s %s" % (r.status_code, r.text))
verifier("E5 conversation étrangère inchangée", next(d for d in b["chat_sessions"].documents if d["id"] == "s1")["participant_ids"] == [ALICE])

print("\nF/G. notifications")
b = base()
r = faire_q("PUT", "/api/notifications/mark-read", J_B, corps={"message_ids": ["m-a1", "m-b2"]})
verifier("F1 coach B → 200, 1 marqué", r.status_code == 200 and r.json().get("marked_count") == 1, r.text)
verifier("F2 son message marqué", msg(b, "m-a1").get("notified") is True)
verifier("G1 message de C intact", not msg(b, "m-b2").get("notified"))
b = base()
r = faire_q("PUT", "/api/notifications/mark-read", J_B, corps={"all_for_target": "coach"})
verifier("F3 « tout » = seulement SES conversations", r.status_code == 200 and msg(b, "m-a1").get("notified")
         and msg(b, "m-ga").get("notified") and not msg(b, "m-b2").get("notified"), r.text)
b = base()
r = faire_q("PUT", "/api/notifications/mark-read", J_B, corps={"all_for_target": "coach", "session_id": "s2"})
verifier("G2 session d'un autre coach → 0", r.status_code == 200 and r.json().get("marked_count") == 0 and not msg(b, "m-b2").get("notified"), r.text)
r = faire_q("PUT", "/api/notifications/mark-read", J_C, corps={"message_ids": ["m-a1", "m-ga"]})
verifier("G3 coach C sur les messages de B → 0", r.status_code == 200 and r.json().get("marked_count") == 0, r.text)
for nom, h in [("G4 anonyme", None), ("G5 e-mail super-admin déclaré", H_SA), ("G6 jeton abonné", T_ALICE)]:
    r = faire_q("PUT", "/api/notifications/mark-read", h, corps={"all_for_target": "coach"})
    verifier(nom + " → refus", refus(r), "%s %s" % (r.status_code, r.text))
verifier("G7 aucune notification touchée par les refus", not any(d.get("notified") for d in b["chat_messages"].documents))
r = faire_q("PUT", "/api/notifications/mark-read", J_B, corps={"message_ids": ["x"] * 501})
verifier("G8 liste démesurée → 400", r.status_code == 400, r.text)
b = base()
r = faire_q("PUT", "/api/notifications/mark-read", J_SA, corps={"all_for_target": "coach"})
verifier("F4 super-admin → toutes", r.status_code == 200 and r.json().get("marked_count") == 4, r.text)

print("\nH/I. déclencheur des rappels (moteur SIMULÉ : aucun rappel réel)")
import inspect  # noqa: E402
APPELS = []
_VRAI = S.cron_reservation_reminders


async def _moteur_simule():
    APPELS.append(1)
    return {"sent": 0, "simule": True}


S.cron_reservation_reminders = _moteur_simule
os.environ["CRON_SECRET"] = "cron-secret-de-test-p0b2"
b = base()
r = faire_q("GET", "/api/cron/reservation-reminders", {"Authorization": "Bearer cron-secret-de-test-p0b2"})
verifier("H1 tâche machine (Bearer CRON_SECRET) → 200", r.status_code == 200 and r.json().get("simule") and len(APPELS) == 1, r.text)
r = faire_q("GET", "/api/cron/reservation-reminders", J_SA)
verifier("H2 super-admin signé (déclenchement manuel) → 200", r.status_code == 200 and len(APPELS) == 2, r.text)
src_boucle = inspect.getsource(S._rv3b_boucle_rappels)
verifier("H3 boucle RV3-B : appel DIRECT du moteur, sans HTTP", "await cron_reservation_reminders()" in src_boucle
         and "http" not in src_boucle.split('"""')[-1].lower())
verifier("H4 moteur appelable sans requête (signature vide)", len(inspect.signature(_VRAI).parameters) == 0)
n = len(APPELS)
for nom, h in [("I1 anonyme", None), ("I2 mauvais secret", {"Authorization": "Bearer nimportequoi"}),
               ("I3 e-mail super-admin déclaré", H_SA), ("I4 coach ordinaire signé", J_B),
               ("I5 secret sans Bearer", {"Authorization": "cron-secret-de-test-p0b2"})]:
    r = faire_q("GET", "/api/cron/reservation-reminders", h)
    verifier(nom + " → 401", r.status_code == 401, "%s %s" % (r.status_code, r.text))
os.environ["CRON_SECRET"] = ""
r = faire_q("GET", "/api/cron/reservation-reminders", {"Authorization": "Bearer "})
verifier("I6 secret NON posé + « Bearer » vide → 401", r.status_code == 401, r.text)
verifier("I7 le moteur n'a JAMAIS tourné sur un refus", len(APPELS) == n)
S.cron_reservation_reminders = _VRAI
os.environ.pop("CRON_SECRET", None)

print("\nJ. webhook Twilio")
b = base()
r = faire_q("POST", "/api/webhooks/twilio/status", data={"MessageSid": "SMfaux", "MessageStatus": "failed"})
verifier("J1 appel falsifié → 410", r.status_code == 410, r.text)
verifier("J2 statut de campagne inchangé", b["campaigns"].documents[0]["results"][0]["status"] == "sent")
r = faire_q("POST", "/api/webhooks/twilio/status", {"X-Twilio-Signature": "faux"}, data={"MessageSid": "SMfaux", "MessageStatus": "delivered"})
verifier("J3 avec une signature quelconque → 410", r.status_code == 410)

print("\nK. aucune sortie réseau")
verifier("K1 aucune tentative réseau", not _TENT, _TENT)

print("\n%d/%d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
