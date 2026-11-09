#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V657d — retenues de place × VRAI webhook Stripe (route HTTP réelle, événements SIGNÉS).

Base LOCALE jetable `afroboost_v657d_banc` (127.0.0.1 uniquement). Aucun appel réseau : la création
de session et les deux lectures faites par le webhook (`Session.retrieve`, `list_line_items`) sont
remplacées par des faux ; la VÉRIFICATION DE SIGNATURE est celle de la bibliothèque stripe (HMAC
SHA-256 sur `<t>.<corps>`, en-tête `Stripe-Signature`), avec un secret de TEST.

Version stripe : celle épinglée (api/requirements.txt, 14.1.0) si `STRIPE_EPINGLEE` désigne un
dossier local qui la contient (aucun téléchargement) ; sinon la version installée, affichée.

  sandbox-exec -f tests/parcours/reseau_local.sb python3 -W ignore tests/test_v657d_webhook_stripe.py
"""
import asyncio
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EPINGLEE = os.environ.get("STRIPE_EPINGLEE", "")
if _EPINGLEE and os.path.isdir(os.path.join(_EPINGLEE, "stripe")):
    sys.path.insert(0, _EPINGLEE)
sys.path.insert(0, RACINE)
BASE = "afroboost_v657d_banc"
os.environ["MONGO_URL"] = "mongodb://127.0.0.1:27017"
os.environ["DB_NAME"] = BASE
os.environ["JWT_SECRET"] = "v657d-banc-secret-local"
os.environ["STRIPE_SECRET_KEY"] = "sk_test_faux_banc_v657d"
os.environ["RESEND_API_KEY"] = "re_faux_banc_v657d"
SECRET_WEBHOOK = "whsec_test_v657d_local_" + uuid.uuid4().hex   # jamais affiché
os.environ["STRIPE_WEBHOOK_SECRET_CHECKOUT"] = SECRET_WEBHOOK
for _k in ("META_WHATSAPP_TOKEN", "META_WHATSAPP_PHONE_ID", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
           "VAPID_PRIVATE_KEY", "VAPID_PUBLIC_KEY", "OPENAI_API_KEY", "STRIPE_WEBHOOK_SECRET",
           "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET", "PAWAPAY_API_TOKEN"):
    os.environ.pop(_k, None)

import stripe  # noqa: E402

SESSIONS = {}
CREATIONS = []


def _faux_create(api_key=None, **p):
    _sid = "cs_test_" + uuid.uuid4().hex[:20]
    SESSIONS[_sid] = p
    CREATIONS.append(p)
    return stripe.checkout.Session.construct_from({"id": _sid, "object": "checkout.session",
                                                   "url": "http://127.0.0.1/faux?cs=" + _sid}, "sk_test")


def _faux_retrieve(sid, *a, **k):
    return stripe.checkout.Session.construct_from(payload_session(sid), "sk_test")


def _faux_lignes(sid, *a, **k):
    return stripe.ListObject.construct_from({"object": "list", "data": [
        {"object": "item", "description": SESSIONS.get(sid, {}).get("line_items", [{}])[0].get("price_data", {}).get("product_data", {}).get("name", "")}]}, "sk_test")


stripe.checkout.Session.create = _faux_create
stripe.checkout.Session.retrieve = _faux_retrieve
stripe.checkout.Session.list_line_items = _faux_lignes
import resend  # noqa: E402

EMAILS = []
resend.Emails.send = lambda params: EMAILS.append(params.get("to")) or {"id": "em_faux"}
import httpx  # noqa: E402
import api.server as S  # noqa: E402
from api.routes import evenement_special as E  # noqa: E402

S.resend.Emails.send = resend.Emails.send
assert S.db.name == BASE
db = S.db
RES = []


def verifier(nom, cond, info=""):
    RES.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + nom + ("" if cond else "  -> %r" % (str(info)[:300],)))


def payload_session(sid, payee=True):
    """L'objet `checkout.session` tel que Stripe l'envoie (champs lus par le webhook)."""
    p = SESSIONS[sid]
    li = p["line_items"][0]
    montant = int(li["price_data"]["unit_amount"]) * int(li.get("quantity") or 1)
    return {"id": sid, "object": "checkout.session", "mode": "payment", "currency": "chf",
            "amount_total": montant, "amount_subtotal": montant,
            "payment_status": "paid" if payee else "unpaid", "status": "complete" if payee else "expired",
            "customer_email": p.get("customer_email"), "customer": None, "payment_intent": "pi_" + sid[-12:],
            "customer_details": {"email": p.get("customer_email"), "name": "Client Test", "phone": "+41790000000"},
            "metadata": p.get("metadata") or {}, "expires_at": p.get("expires_at")}


def signer(corps: str):
    t = int(time.time())
    sig = hmac.new(SECRET_WEBHOOK.encode(), ("%d.%s" % (t, corps)).encode(), hashlib.sha256).hexdigest()
    return {"Stripe-Signature": "t=%d,v1=%s" % (t, sig), "Content-Type": "application/json"}


async def webhook(cl, sid, type_="checkout.session.completed"):
    corps = json.dumps({"id": "evt_" + uuid.uuid4().hex[:16], "object": "event", "api_version": "2024-06-20",
                        "type": type_, "created": int(time.time()), "livemode": False,
                        "data": {"object": payload_session(sid, payee=type_ != "checkout.session.expired")}})
    return await cl.post("/api/webhook/stripe", content=corps, headers=signer(corps))


def evt(oid, cid, cap):
    return ({"id": oid, "name": "Événement " + oid, "price": 30.0, "offer_type": "event", "evenement_reservation_auto": True,
             "linked_course_ids": [cid], "visible": True, "stock": -1, "category": "service",
             "capacite_limitee": cap is not None, "capacite_max": cap, "coach_id": "contact.artboost@gmail.com"},
            {"id": cid, "name": "Cours " + oid, "weekday": None, "date": "2026-12-18", "time": "19:00", "visible": True,
             "archived": False, "coach_id": "contact.artboost@gmail.com"})


async def acheter(cl, oid, email):
    n = len(CREATIONS)
    r = await cl.post("/api/create-checkout-session", json={"amount": 30, "productName": "Billet " + oid,
                                                            "originUrl": "http://127.0.0.1", "offerId": oid, "quantity": 1,
                                                            "customerEmail": email})
    sid = r.json().get("sessionId") if r.status_code == 200 else None
    return r, sid


async def retenue_de(sid):
    return await db[E.COLL_RETENUES].find_one({"_id": (SESSIONS[sid].get("metadata") or {}).get("evenement_retenue")})


async def expirer_retenue(sid):
    await db[E.COLL_RETENUES].update_one({"_id": (SESSIONS[sid].get("metadata") or {}).get("evenement_retenue")},
                                         {"$set": {"expire_le": datetime.now(timezone.utc) - timedelta(minutes=1)}})


async def principal():
    print("stripe-python utilisé : %s (épinglé : 14.1.0)" % stripe.VERSION)
    await S.client.drop_database(BASE)
    for oid, cid, cap in (("evt1", "c1", 2), ("evt2", "c2", 1), ("evt3", "c3", 1), ("evt4", "c4", 1), ("evt5", "c5", 1),
                          ("libre", "cl", None)):
        o, c = evt(oid, cid, cap)
        await db.offers.insert_one(o)
        await db.courses.insert_one(c)
    T = httpx.ASGITransport(app=S.fastapi_app)
    async with httpx.AsyncClient(transport=T, base_url="http://banc", timeout=60) as cl:
        # 0. Signature réellement vérifiée par la route
        r, sid0 = await acheter(cl, "evt1", "faux@test.local")
        corps = json.dumps({"id": "evt_x", "object": "event", "type": "checkout.session.completed",
                            "data": {"object": payload_session(sid0)}})
        r = await cl.post("/api/webhook/stripe", content=corps, headers={"Stripe-Signature": "t=1,v1=00", "Content-Type": "application/json"})
        verifier("S0 webhook mal signé -> 400, rien créé", r.status_code == 400
                 and await db.reservations.count_documents({}) == 0, (r.status_code, r.text[:120]))
        await db[E.COLL_RETENUES].delete_many({})

        # 1. Paiement confirmé pendant la retenue
        r, sid = await acheter(cl, "evt1", "a1@test.local")
        p = SESSIONS[sid]
        _exp = int(p.get("expires_at") or 0) - int(time.time())
        ret = await retenue_de(sid)
        _vie = (ret["expire_le"].replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).total_seconds()
        verifier("S1a session Stripe : expires_at ≈ +31 min (≥ 30 min, minimum Stripe)", 30 * 60 < _exp <= 31 * 60 + 5, _exp)
        verifier("S1b retenue ≈ 35 min : elle survit toujours à la session", _vie > _exp and 34 * 60 < _vie <= 35 * 60 + 5, (_vie, _exp))
        r = await webhook(cl, sid)
        resa = await db.reservations.find_one({"stripe_session_id": sid}, {"_id": 0})
        verifier("S1c webhook signé (route réelle) -> réservation confirmée, billet émis", r.status_code == 200 and resa
                 and resa.get("reservationCode") and resa.get("offerId") == "evt1", (r.status_code, r.text[:200]))
        verifier("S1d retenue convertie (une fois)", (await retenue_de(sid))["statut"] == "convertie")
        verifier("S1e paiement tracé (code + transaction)", await db.discount_codes.count_documents({"session_id": sid}) == 1)

        # 6. Même webhook livré deux fois -> une réservation
        r = await webhook(cl, sid)
        verifier("S6 même webhook rejoué -> toujours UNE réservation, un code", r.status_code == 200
                 and await db.reservations.count_documents({"stripe_session_id": sid}) == 1
                 and await db.discount_codes.count_documents({"session_id": sid}) == 1, r.text[:200])

        # 2. Paiement abandonné : la session expire -> retenue rendue
        r, sid = await acheter(cl, "evt1", "abandon@test.local")
        verifier("S2a retenue active pendant le paiement", (await retenue_de(sid))["statut"] == "active")
        r = await webhook(cl, sid, "checkout.session.expired")
        verifier("S2b checkout.session.expired (signé) -> retenue libérée, aucune réservation",
                 r.status_code == 200 and (await retenue_de(sid))["statut"] == "liberee"
                 and not await db.reservations.find_one({"stripe_session_id": sid}), r.text[:200])

        # 3. Paiement tardif (retenue expirée), place libre -> confirmé une fois
        r, sid = await acheter(cl, "evt2", "tardif@test.local")
        await expirer_retenue(sid)
        r = await webhook(cl, sid)
        r2 = await webhook(cl, sid)
        verifier("S3 paiement tardif, place libre -> confirmé UNE fois (rejeu compris)",
                 await db.reservations.count_documents({"stripe_session_id": sid}) == 1 and r2.status_code == 200, r.text[:200])

        # 7. Événement déjà complet au moment du paiement -> refus avant Stripe
        n = len(CREATIONS)
        r, _ = await acheter(cl, "evt2", "trop-tard@test.local")
        verifier("S7 événement complet au checkout -> 409, aucune session Stripe", r.status_code == 409 and len(CREATIONS) == n, r.text[:120])

        # 4. Paiement tardif, événement plein -> PAS confirmé, paiement tracé, signalé
        r, sid_a = await acheter(cl, "evt3", "lent@test.local")
        await expirer_retenue(sid_a)
        r, sid_b = await acheter(cl, "evt3", "rapide@test.local")
        await webhook(cl, sid_b)
        r = await webhook(cl, sid_a)
        place = await db[E.COLL_PLACES].find_one({"_id": "stripe:%s" % sid_a})
        verifier("S4a rapide (retenue vivante) confirmé", await db.reservations.count_documents({"stripe_session_id": sid_b}) == 1)
        verifier("S4b lent (retenue expirée, plein) : AUCUNE réservation, aucun billet", r.status_code == 200
                 and await db.reservations.count_documents({"stripe_session_id": sid_a}) == 0, r.text[:200])
        verifier("S4c paiement tracé (code, transaction) et réclamation « en_attente_place »",
                 await db.discount_codes.count_documents({"session_id": sid_a}) == 1 and place
                 and place.get("statut") == E.STATUT_EN_ATTENTE and place.get("surreservation_bloquee") is True, place)
        verifier("S4d signalé à l'admin (notification du tableau de bord, type affiché)",
                 await db.notifications.count_documents({"type": E.TYPE_NOTIF_BLOQUEE}) == 1
                 and E.TYPE_NOTIF_BLOQUEE in S.C17J_TYPES)
        verifier("S4e jauge respectée : 1 place, 1 réservation", await E.places_prises(db, await db.offers.find_one({"id": "evt3"})) == 1)
        await webhook(cl, sid_a)
        verifier("S4f rejeu du paiement bloqué : rien de plus (ni place, ni notification)",
                 await db.reservations.count_documents({"stripe_session_id": sid_a}) == 0
                 and await db.notifications.count_documents({"type": E.TYPE_NOTIF_BLOQUEE}) == 1)

        # 5. Deux achats simultanés pour la dernière place
        rs = await asyncio.gather(*[acheter(cl, "evt4", "simul%d@test.local" % i) for i in range(2)])
        verifier("S5a deux paiements ouverts en même temps, 1 place -> une session, un 409",
                 sorted(x[0].status_code for x in rs) == [200, 409], [x[0].status_code for x in rs])
        r, sx = await acheter(cl, "evt5", "x@test.local")
        await expirer_retenue(sx)
        r, sy = await acheter(cl, "evt5", "y@test.local")
        await expirer_retenue(sy)
        await asyncio.gather(webhook(cl, sx), webhook(cl, sy))
        n_resa = await db.reservations.count_documents({"offerId": "evt5"})
        n_att = await db[E.COLL_PLACES].count_documents({"offer_id": "evt5", "statut": E.STATUT_EN_ATTENTE})
        verifier("S5b deux paiements tardifs simultanés pour la dernière place -> 1 confirmé, 1 en attente",
                 n_resa == 1 and n_att == 1, (n_resa, n_att))

        # Événement sans capacité : appel Stripe inchangé
        r, sid = await acheter(cl, "libre", "libre@test.local")
        verifier("S8 événement sans capacité : ni expires_at, ni retenue", r.status_code == 200
                 and "expires_at" not in SESSIONS[sid] and await db[E.COLL_RETENUES].count_documents({"offer_id": "libre"}) == 0)
    await S.client.drop_database(BASE)
    print("\n%d/%d PASS" % (sum(RES), len(RES)))
    return all(RES)


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(principal()) else 1)
