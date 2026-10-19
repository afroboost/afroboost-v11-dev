#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V628 — place d'événement par CODE PROMO (invités Hétaira, 28/10/2026 18:45).

BANC DE BOUT EN BOUT sur la VRAIE application, contre une MongoDB LOCALE uniquement
(`mongodb://127.0.0.1:27017`, base `afroboost_v628_banc`, supprimée à la fin) et des
données FACTICES. Stripe et Resend sont remplacés : aucun paiement, aucun e-mail.
Le banc REFUSE de démarrer si MONGO_URL ne désigne pas la machine locale.

Lancement : python3 tests/test_v628_place_code_evenement.py
"""
import asyncio
import json
import os
import sys
import tempfile
import uuid

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

MONGO_LOCAL = os.environ.get("V628_MONGO_URL", "mongodb://127.0.0.1:27017")
if not MONGO_LOCAL.startswith(("mongodb://127.0.0.1", "mongodb://localhost")):
    sys.exit("REFUS : le banc V628 ne tourne que sur une MongoDB locale.")
BASE = os.environ.get("V628_BASE", "afroboost_v628_banc")
if not BASE.startswith("afroboost_v628_"):
    sys.exit("REFUS : base de banc inattendue.")
os.environ["MONGO_URL"] = MONGO_LOCAL
os.environ["DB_NAME"] = BASE
os.environ["JWT_SECRET"] = "v628-banc-secret-local"
os.environ["STRIPE_SECRET_KEY"] = "sk_test_faux_banc_v628"
os.environ["RESEND_API_KEY"] = "re_faux_banc_v628"
os.environ["FRONTEND_URL"] = "http://127.0.0.1:8001"
for _k in ("META_WHATSAPP_TOKEN", "META_WHATSAPP_PHONE_ID", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
           "VAPID_PRIVATE_KEY", "VAPID_PUBLIC_KEY", "OPENAI_API_KEY", "STRIPE_WEBHOOK_SECRET",
           "STRIPE_WEBHOOK_SECRET_CHECKOUT", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET", "PAWAPAY_API_TOKEN"):
    os.environ.pop(_k, None)

# ── Faux Stripe : on COMPTE les appels (la place par code ne doit en faire aucun) ──
import stripe  # noqa: E402

APPELS_STRIPE = []


class _Obj(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


def _faux_create(api_key=None, **p):
    APPELS_STRIPE.append(p)
    _sid = "cs_test_" + uuid.uuid4().hex[:12]
    return _Obj(id=_sid, url="http://127.0.0.1/faux-stripe?cs=" + _sid, payment_status="unpaid", mode=p.get("mode"))


stripe.checkout.Session.create = _faux_create

import resend  # noqa: E402

EMAILS = os.path.join(tempfile.mkdtemp(prefix="v628_"), "emails.jsonl")


def _faux_send(params):
    with open(EMAILS, "a", encoding="utf-8") as f:
        f.write(json.dumps({"to": params.get("to"), "subject": params.get("subject")}, ensure_ascii=False) + "\n")
    return {"id": "em_faux"}


resend.Emails.send = _faux_send

import httpx  # noqa: E402
import api.server as S  # noqa: E402
from api.routes import evenement_special as E  # noqa: E402

S.resend.Emails.send = _faux_send
for _m in ("checkout_routes", "stripe_routes"):
    try:
        _mod = __import__("api.routes." + _m, fromlist=["x"])
        if hasattr(_mod, "stripe"):
            _mod.stripe.checkout.Session.create = _faux_create
    except Exception:  # noqa: BLE001
        pass

assert S.db.name == BASE, S.db.name
db = S.db
RES = []


def verifier(nom, cond, info=""):
    RES.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + nom + ("" if cond else "  -> %r" % (info,)))


# ── Données FACTICES ────────────────────────────────────────────────────────
COACH = "contact.artboost@gmail.com"
EVT, C_EVT = "evt-silent-test", "cours-evt-28-10"
AUTRE_EVT, C_AUTRE = "evt-autre-test", "cours-autre-evt"
UNITE, C_REG = "offre-unite-test", "cours-mercredi-1845"
CODES = {
    "OK1": "28BOOSTHETAÏRA-01", "OK2": "28BOOSTHETAÏRA-02", "OK3": "28BOOSTHETAÏRA-03",
    "OK5": "28BOOSTHETAÏRA-05", "OK6": "28BOOSTHETAÏRA-06",
    "TOUS": "TEST-TOUS-ARTICLES", "EXP": "TEST-EXPIRE", "USE": "TEST-UTILISE", "P50": "TEST-50POURCENT",
    "OFF": "TEST-INACTIF", "AUTRE": "TEST-AUTRE-EVT", "ASSIGNE": "TEST-ASSIGNE", "NORMAL": "TEST-NORMAL-COURS",
    "DUO1": "TEST-DUO-A", "DUO2": "TEST-DUO-B", "SCAN": "TEST-SCAN-ENTREE",
}


def _code(cle, courses, **k):
    d = {"id": "dc-" + cle.lower(), "code": CODES[cle], "type": "100%", "value": 150, "maxUses": 1, "used": 0,
         "active": True, "expiresAt": "2026-10-28", "courses": courses, "coach_id": COACH, "assignedEmail": None,
         "multi_member": False, "created_at": "2026-10-19T10:00:00+00:00"}
    d.update(k)
    return d


async def semer():
    await S.client.drop_database(BASE)
    await db.offers.insert_many([
        {"id": EVT, "name": "AFROBOOST SILENT — ÉDITION SPÉCIALE", "price": 25.0, "offer_type": "event",
         "evenement_reservation_auto": True, "progressive_pricing": True, "price_early_bird": 25.0,
         "price_standard": 30.0, "price_last_minute": 40.0, "early_bird_days_before": 7, "standard_hours_before": 24,
         "countdown_enabled": True, "countdown_date": "2026-10-28", "countdown_time": "18:45",
         "linked_course_ids": [C_EVT], "visible": True, "stock": -1, "max_participants": None, "category": "service"},
        {"id": AUTRE_EVT, "name": "Autre événement", "price": 20.0, "offer_type": "event",
         "evenement_reservation_auto": True, "linked_course_ids": [C_AUTRE], "visible": True, "stock": -1},
        {"id": UNITE, "name": "Cours à l'unité", "price": 30.0, "linked_course_ids": [C_REG], "visible": True,
         "category": "service", "stock": -1},
    ])
    await db.courses.insert_many([
        {"id": C_EVT, "name": "AFROBOOST SILENT — ÉDITION SPÉCIALE", "weekday": None, "date": "2026-10-28",
         "time": "18:45", "locationName": "Neuchâtel", "visible": True, "archived": False},
        {"id": C_AUTRE, "name": "Autre événement", "weekday": None, "date": "2026-11-11", "time": "19:00",
         "visible": True, "archived": False},
        {"id": C_REG, "name": "Cours à l'unité", "weekday": 3, "date": "", "time": "18:45", "visible": True,
         "archived": False, "dates_annulees": ["2026-10-28"]},
    ])
    _evt = [EVT, C_EVT]
    await db.discount_codes.insert_many([
        _code("OK1", _evt), _code("OK2", _evt), _code("OK3", _evt), _code("OK5", _evt), _code("OK6", _evt),
        _code("TOUS", [EVT, C_EVT, UNITE, C_REG]),
        _code("EXP", _evt, expiresAt="2026-10-01"),
        _code("USE", _evt, used=1),
        _code("P50", _evt, type="%", value=50),
        _code("OFF", _evt, active=False),
        _code("AUTRE", [AUTRE_EVT, C_AUTRE]),
        _code("ASSIGNE", _evt, assignedEmail="titulaire@test.local"),
        _code("NORMAL", [UNITE, C_REG], maxUses=5),
        _code("DUO1", _evt), _code("DUO2", _evt), _code("SCAN", _evt, used=1),
    ])


async def fiche(cle):
    return await db.discount_codes.find_one({"id": "dc-" + cle.lower()}, {"_id": 0})


N_IP = [0]


def corps(code, email, **k):
    d = {"prenom": "Invitée", "nom": "Test", "email": email, "whatsapp": "+41 79 000 00 00", "code": code,
         "terms_accepted": True}
    d.update(k)
    return d


async def poster(cl, code, email, ip=None, offre=EVT, **k):
    N_IP[0] += 1
    _h = {"X-Forwarded-For": ip or "10.0.0.%d" % N_IP[0]}
    return await cl.post("/api/evenements/%s/place-code" % offre, json=corps(code, email, **k), headers=_h)


async def principal():
    await semer()
    transport = httpx.ASGITransport(app=S.fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://banc") as cl:
        # 1. Code valable -> réservation gratuite, sans Stripe
        r = await poster(cl, CODES["OK1"], "invitee1@test.local")
        j = r.json()
        verifier("1 code valable -> 200, place à 0 CHF", r.status_code == 200 and j.get("success") and j.get("prix") == 0
                 and not j.get("deja_reserve"), (r.status_code, j))
        resa = await db.reservations.find_one({"userEmail": "invitee1@test.local"}, {"_id": 0})
        verifier("1b réservation CONFIRMÉE de l'événement du 28/10 18:45",
                 resa and resa.get("courseId") == C_EVT and resa.get("datetime") == "2026-10-28T18:45:00"
                 and resa.get("offerId") == EVT and resa.get("totalPrice") == 0 and resa.get("source") == E.SOURCE_CODE
                 and resa.get("promoCode") == CODES["OK1"] and resa.get("paiement") == "code_promo", resa)
        verifier("1c nom complet (prénom + nom) et WhatsApp conservés",
                 resa and resa.get("userName") == "Invitée Test" and resa.get("userWhatsapp") == "+41 79 000 00 00", resa)
        f = await fiche("OK1")
        verifier("1d code décompté EXACTEMENT une fois (used 0 -> 1)", f.get("used") == 1, f)
        mv = await db.seance_mouvements.find_one({"_id": "debit:%s" % (resa or {}).get("id")})
        verifier("1e le débit porte la clé de LA réservation (annulation = restitution possible)",
                 mv is not None and mv.get("statut") != "en_cours" and mv.get("code") == CODES["OK1"], mv)
        verifier("1f AUCUN appel Stripe / TWINT", len(APPELS_STRIPE) == 0, APPELS_STRIPE)
        place = await db[E.COLL_PLACES].find_one({"_id": "code:%s:invitee1@test.local" % EVT})
        verifier("1g réclamation unique posée (une personne = une place)", place and place.get("statut") == "reservee", place)

        # 2. Saisie sans accents / en minuscules
        r = await poster(cl, "28boosthetaira-02", "invitee2@test.local")
        verifier("2 « 28boosthetaira-02 » (sans Ï, minuscules) est reconnu", r.status_code == 200, r.text)
        verifier("2b c'est bien le code -02 qui est décompté", (await fiche("OK2")).get("used") == 1)

        # 3. Refus
        for nom, cle, attendu in (("3a code inconnu", None, 400), ("3b code expiré", "EXP", 400),
                                  ("3c code déjà utilisé", "USE", 409), ("3d code 50 % (pas 100 %)", "P50", 400),
                                  ("3e code inactif", "OFF", 400)):
            r = await poster(cl, CODES[cle] if cle else "HETAIRA-INVENTE", "refus-%s@test.local" % (cle or "x"))
            verifier("%s -> %d" % (nom, attendu), r.status_code == attendu, (r.status_code, r.text))
        r = await poster(cl, CODES["TOUS"], "tous@test.local")
        verifier("3f code « tous les articles » -> refusé (pas réglé pour CET événement), message neutre",
                 r.status_code == 400 and r.json().get("detail") == E.MSG_CODE_INVALIDE, r.text)
        r = await poster(cl, CODES["AUTRE"], "autre@test.local")
        verifier("3g code d'un AUTRE événement -> refusé", r.status_code == 400, r.text)
        r = await poster(cl, CODES["AUTRE"], "autre@test.local", offre=UNITE)
        verifier("3h la route ne vend pas une offre qui n'est pas un événement (404)", r.status_code == 404, r.text)
        r = await poster(cl, CODES["ASSIGNE"], "intrus@test.local")
        verifier("3i code attribué à une autre adresse -> refus neutre (400, même message qu'un code inconnu)",
                 r.status_code == 400 and r.json().get("detail") == E.MSG_CODE_INVALIDE, r.text)
        await db.concept.insert_one({"id": "concept", "termsText": "Conditions générales de test."})
        r = await poster(cl, CODES["OK3"], "sansconditions@test.local", terms_accepted=False)
        verifier("3j conditions publiées mais non acceptées -> 409", r.status_code == 409, r.text)
        r = await poster(cl, CODES["OK3"], "x@test.local", nom="")
        verifier("3j2 saisie incomplète (sans nom) -> 400", r.status_code == 400, r.text)
        verifier("3k refus sans écriture : codes refusés jamais décomptés",
                 all([(await fiche(c)).get("used") == u for c, u in (("EXP", 0), ("USE", 1), ("P50", 0), ("OFF", 0),
                                                                    ("TOUS", 0), ("AUTRE", 0), ("ASSIGNE", 0))]))

        # 4. Deux utilisations SIMULTANÉES du même code -> une seule acceptée
        rs = await asyncio.gather(*[poster(cl, CODES["OK5"], "simul%d@test.local" % i) for i in range(8)])
        ok = [x for x in rs if x.status_code == 200]
        verifier("4 huit clics simultanés, 8 adresses, 1 code -> UNE seule place", len(ok) == 1,
                 [x.status_code for x in rs])
        verifier("4b quota respecté : used == maxUses == 1", (await fiche("OK5")).get("used") == 1, await fiche("OK5"))
        n = await db.reservations.count_documents({"promoCode": CODES["OK5"]})
        verifier("4c une seule réservation porte ce code", n == 1, n)

        # 5. Double clic de la MÊME personne avec deux codes -> une place, un seul code consommé
        rs = await asyncio.gather(poster(cl, CODES["DUO1"], "double@test.local"),
                                  poster(cl, CODES["DUO2"], "double@test.local"))
        n = await db.reservations.count_documents({"userEmail": "double@test.local"})
        u = (await fiche("DUO1")).get("used") + (await fiche("DUO2")).get("used")
        verifier("5 même personne, 2 codes en même temps -> 1 réservation", n == 1, (n, [x.status_code for x in rs]))
        verifier("5b ... et UN seul code consommé (l'autre rendu)", u == 1, u)

        # 6. Déjà inscrit -> pas de doublon, pas de débit
        r = await poster(cl, CODES["OK3"], "invitee1@test.local")
        verifier("6 déjà inscrit (même adresse) -> place rendue, pas de doublon",
                 r.status_code == 200 and r.json().get("deja_reserve") is True, r.text)
        verifier("6a la réponse « déjà inscrit » ne livre PAS le billet (reservationCode)",
                 "reservationCode" not in json.dumps(r.json()) and "id" not in (r.json().get("reservation") or {}), r.text)
        r = await poster(cl, CODES["OK1"], "invitee1@test.local")
        verifier("6a2 l'invitée retape SON code déjà utilisé -> « déjà inscrite », pas une erreur",
                 r.status_code == 200 and r.json().get("deja_reserve") is True, r.text)
        verifier("6a3 ... et le code n'est pas décompté deux fois", (await fiche("OK1")).get("used") == 1)
        verifier("6b ... et le code OK3 n'est PAS consommé", (await fiche("OK3")).get("used") == 0)
        await db.reservations.insert_one({"id": "resa-payee", "userEmail": "payeur@test.local", "offerId": EVT,
                                          "courseId": C_EVT, "datetime": "2026-10-28T18:45:00",
                                          "source": E.SOURCE_PAYANT, "totalPrice": 25.0})
        r = await poster(cl, CODES["OK3"], "PAYEUR@test.local")
        verifier("6c billet déjà PAYÉ -> aucune seconde place, code intact",
                 r.json().get("deja_reserve") is True and (await fiche("OK3")).get("used") == 0, r.text)

        # 7. Le code d'événement ne sert NULLE PART ailleurs
        r = await cl.post("/api/reservations", json={
            "userName": "Fraude", "userEmail": "fraude@test.local", "userWhatsapp": "", "courseId": C_REG,
            "courseName": "Cours à l'unité", "courseTime": "18:45", "datetime": "2026-11-04T18:45:00",
            "offerName": "Cours à l'unité", "price": 30, "quantity": 1, "totalPrice": 0,
            "promoCode": CODES["OK3"], "discountCode": CODES["OK3"], "terms_accepted": True})
        verifier("7a POST /reservations (autre cours) avec le code d'événement -> 403", r.status_code == 403, r.text)
        _rem, _meta = await S._v429_remise_serveur(CODES["OK3"], {"id": UNITE}, "", "fraude@test.local")
        verifier("7b aucune remise de paiement avec ce code", _rem == (None, 0.0)
                 and _meta.get("quota_guard_result") == "reserve_evenement", (_rem, _meta))
        verifier("7c aucun débit Live (BoostTribe) avec ce code", await S._bt_debit_subscriber(CODES["OK3"]) is None)
        verifier("7d code toujours intact après ces tentatives", (await fiche("OK3")).get("used") == 0)

        # 8. Autres cours inchangés
        r = await cl.post("/api/reservations", json={
            "userName": "Habituée", "userEmail": "habituee@test.local", "userWhatsapp": "", "courseId": C_REG,
            "courseName": "Cours à l'unité", "courseTime": "18:45", "datetime": "2026-11-04T18:45:00",
            "offerName": "Cours à l'unité", "price": 30, "quantity": 1, "totalPrice": 0,
            "promoCode": CODES["NORMAL"], "discountCode": CODES["NORMAL"], "terms_accepted": True})
        verifier("8a un code NORMAL réserve toujours un cours normal (04/11)", r.status_code == 200, r.text)
        verifier("8b ... et son compteur avance comme avant", (await fiche("NORMAL")).get("used") == 1)
        _rem, _ = await S._v429_remise_serveur(CODES["NORMAL"], {"id": UNITE}, UNITE, "habituee@test.local")
        verifier("8c la remise d'un code normal est inchangée (100 %)", _rem == ("100%", 150.0), _rem)
        r = await cl.post("/api/evenements/%s/place-code" % EVT, json=corps(CODES["NORMAL"], "n@test.local"),
                          headers={"X-Forwarded-For": "10.9.9.9"})
        verifier("8d un code de cours normal ne donne PAS de place à l'événement", r.status_code == 400, r.text)
        verifier("8e le cours habituel du 28/10 reste ANNULÉ",
                 E.jour_annule(await db.courses.find_one({"id": C_REG}, {"_id": 0}), "2026-10-28"))

        # 9. Réservation payante normale inchangée : billet 25 CHF par Stripe
        avant = len(APPELS_STRIPE)
        r = await cl.post("/api/create-checkout-session", json={
            "amount": 25, "productName": "AFROBOOST SILENT — ÉDITION SPÉCIALE", "originUrl": "http://127.0.0.1",
            "offerId": EVT, "quantity": 1, "customerEmail": "acheteur@test.local", "allowPromotionCodes": True})
        _p = APPELS_STRIPE[-1] if len(APPELS_STRIPE) > avant else {}
        _li = ((_p.get("line_items") or [{}])[0].get("price_data") or {})
        verifier("9 billet public : session Stripe à 25,00 CHF (palier prévente), inchangée",
                 r.status_code == 200 and _li.get("unit_amount") == 2500, (r.status_code, r.text[:300], _li))

        # 10. Cockpit : la réservation est visible côté coach (liste des réservations)
        jeton = S.generate_jwt_token(COACH, "coach") if hasattr(S, "generate_jwt_token") else None
        if not jeton:
            from api.routes.auth_routes import generate_jwt_token
            jeton = generate_jwt_token(COACH, "coach")
        r = await cl.get("/api/reservations?limit=100", headers={"Authorization": "Bearer " + jeton})
        _l = r.json() if r.status_code == 200 else {}
        _l = _l.get("data") or _l.get("reservations") or _l.get("items") or _l if isinstance(_l, dict) else _l
        _codes = [x.get("promoCode") for x in (_l if isinstance(_l, list) else [])]
        verifier("10 cockpit : les places par code apparaissent dans les réservations du coach",
                 r.status_code == 200 and CODES["OK1"] in _codes, (r.status_code, str(_l)[:300]))
        n = await db[E.COLL_PLACES].count_documents({"offer_id": EVT, "statut": "reservee"})
        verifier("10b places réservées par code = 4 (OK1, OK2, OK5, DUO) — aucune place fantôme",
                 n == 4, n)

        # 10c. Le code d'événement ne se « valide » pas ailleurs (connexion abonné, remise vitrine)
        r = await cl.post("/api/discount-codes/validate", json={"code": CODES["OK3"], "email": ""})
        verifier("10c /discount-codes/validate refuse un code d'événement", r.json().get("valid") is False, r.text)
        r = await cl.post("/api/discount-codes/validate", json={"code": CODES["NORMAL"], "email": ""})
        verifier("10d ... et valide toujours un code normal", r.json().get("valid") is True, r.text[:200])

        # 10e. Scan à l'entrée en tapant le CODE promo : la réservation du jour est retrouvée
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz
        _auj = _dt.now(_tz(_td(hours=2))).strftime("%Y-%m-%d")
        await db.reservations.insert_one({"id": "resa-scan", "reservationCode": "AFSCAN0001", "userName": "Invitée Scan",
                                          "userEmail": "scan@test.local", "promoCode": CODES["SCAN"],
                                          "discountCode": CODES["SCAN"], "courseId": C_EVT, "offerId": EVT,
                                          "datetime": _auj + "T23:30:00", "coach_id": COACH, "validated": False,
                                          "source": E.SOURCE_CODE})
        # Le jour de l'événement, simulé : le cours daté est « aujourd'hui » le temps du scan.
        await db.courses.update_one({"id": C_EVT}, {"$set": {"date": _auj, "time": "23:30"}})
        r = await cl.post("/api/qr/scan-validate", json={"code": CODES["SCAN"]}, headers={"Authorization": "Bearer " + jeton})
        await db.courses.update_one({"id": C_EVT}, {"$set": {"date": "2026-10-28", "time": "18:45"}})
        verifier("10e scan du code promo à l'entrée -> présence validée (pas « code désactivé »)",
                 r.status_code == 200 and "valid" in r.text.lower(), (r.status_code, r.text[:200]))
        verifier("10f ... sans redébiter le code", (await fiche("SCAN")).get("used") == 1)

        # 11. Limite de débit par connexion
        codes_429 = []
        for _i in range(22):
            codes_429.append((await poster(cl, "INCONNU-%d" % _i, "brute@test.local", ip="10.7.7.7")).status_code)
        verifier("11 essais en rafale depuis une même connexion -> 429", 429 in codes_429, codes_429)

        # 12. E-mails : confirmations parties vers le faux Resend uniquement
        await asyncio.sleep(0.5)
        _mails = [json.loads(l) for l in open(EMAILS, encoding="utf-8")] if os.path.exists(EMAILS) else []
        verifier("12 confirmation e-mail créée pour l'invitée (faux Resend, rien n'est envoyé)",
                 any("invitee1@test.local" in json.dumps(m.get("to")) for m in _mails), _mails[:3])

    await S.client.drop_database(BASE)
    print("\n%d/%d PASS" % (sum(RES), len(RES)))
    return all(RES)


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(principal()) else 1)
