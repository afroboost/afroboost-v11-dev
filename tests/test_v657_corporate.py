#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V657 — AFROBOOST CORPORATE : contrats, invitation privée, capacité atomique, factures Entreprise.

BANC DE BOUT EN BOUT sur la VRAIE application (api.server), contre une MongoDB LOCALE
(`mongodb://127.0.0.1:27017`, base `afroboost_v657_banc`, supprimée à la fin), données FACTICES.
Stripe et Resend sont remplacés : aucun paiement, aucun e-mail. Refuse toute autre adresse.

Lancement : sandbox-exec -f tests/parcours/reseau_local.sb python3 -W ignore tests/test_v657_corporate.py
"""
import asyncio
import json
import os
import re
import sys
import uuid
import zlib

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
MONGO_LOCAL = "mongodb://127.0.0.1:27017"
BASE = "afroboost_v657_banc"
os.environ["MONGO_URL"] = MONGO_LOCAL
os.environ["DB_NAME"] = BASE
os.environ["JWT_SECRET"] = "v657-banc-secret-local"
os.environ["STRIPE_SECRET_KEY"] = "sk_test_faux_banc_v657"
os.environ["RESEND_API_KEY"] = "re_faux_banc_v657"
os.environ["FRONTEND_URL"] = "http://127.0.0.1:8001"
os.environ["LOTB3_ANNULATION_CANONIQUE_ENABLED"] = "true"
for _k in ("META_WHATSAPP_TOKEN", "META_WHATSAPP_PHONE_ID", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
           "VAPID_PRIVATE_KEY", "VAPID_PUBLIC_KEY", "OPENAI_API_KEY", "STRIPE_WEBHOOK_SECRET",
           "STRIPE_WEBHOOK_SECRET_CHECKOUT", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET", "PAWAPAY_API_TOKEN"):
    os.environ.pop(_k, None)

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

EMAILS = []


def _faux_send(params):
    EMAILS.append(params.get("to"))
    return {"id": "em_faux"}


resend.Emails.send = _faux_send
import httpx  # noqa: E402
import jwt  # noqa: E402
import api.server as S  # noqa: E402
from api.routes import corporate as C  # noqa: E402
from api.routes import evenement_special as E  # noqa: E402

S.resend.Emails.send = _faux_send
assert S.db.name == BASE and MONGO_LOCAL.startswith("mongodb://127.0.0.1")
db = S.db
RES = []


def verifier(nom, cond, info=""):
    RES.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + nom + ("" if cond else "  -> %r" % (str(info)[:400],)))


ADMIN = "contact.artboost@gmail.com"
PARTENAIRE = "partenaire@test.local"


def h(email, secret=None):
    return {"Authorization": "Bearer " + jwt.encode({"email": email, "sub": email},
                                                    secret or os.environ["JWT_SECRET"], algorithm="HS256")}


HA, HP, HF = h(ADMIN), h(PARTENAIRE), h(ADMIN, "faux-secret")


def texte_pdf(octets: bytes) -> str:
    """Texte brut d'un PDF reportlab (flux éventuellement compressés)."""
    import base64
    _t = octets.decode("latin-1")
    for _m in re.finditer(rb"stream\r?\n(.*?)endstream", octets, re.S):
        _d = _m.group(1).strip()
        for _f in (lambda x: zlib.decompress(base64.a85decode(x[:-2] if x.endswith(b"~>") else x)), zlib.decompress):
            try:
                _t += _f(_d).decode("latin-1")
                break
            except Exception:  # noqa: BLE001
                pass
    return _t


EVT_A, C_A = "evt-corp-dec", "cours-corp-dec"        # capacité 12, 16/12/2026
EVT_D, C_D = "evt-public-cap3", "cours-public-cap3"  # capacité 3, paiements publics
EVT_N, C_N = "evt-nov-proche", "cours-nov-proche"    # demain : délai dépassé
EVT_L, C_L = "evt-libre", "cours-libre"              # sans capacité
UNITE, C_U = "offre-unite", "cours-unite"


def evt(oid, cid, nom, **k):
    d = {"id": oid, "name": nom, "price": 30.0, "offer_type": "event", "evenement_reservation_auto": True,
         "linked_course_ids": [cid], "visible": True, "stock": -1, "category": "service"}
    d.update(k)
    return d


def cours(cid, nom, date, time="19:00"):
    return {"id": cid, "name": nom, "weekday": None, "date": date, "time": time, "locationName": "Neuchâtel",
            "visible": True, "archived": False}


async def semer():
    await S.client.drop_database(BASE)
    await db.offers.insert_many([
        evt(EVT_A, C_A, "AFROBOOST CORPORATE — décembre", capacite_limitee=True, capacite_max=12),
        evt(EVT_D, C_D, "Événement public", capacite_limitee=True, capacite_max=3),
        evt(EVT_N, C_N, "Événement demain", capacite_limitee=True, capacite_max=40),
        evt(EVT_L, C_L, "Événement libre"),
        {"id": UNITE, "name": "Cours à l'unité", "price": 30.0, "linked_course_ids": [C_U], "visible": True,
         "category": "service", "stock": -1},
    ])
    from datetime import datetime, timedelta, timezone
    _demain = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    await db.courses.insert_many([cours(C_A, "Corporate décembre", "2026-12-16"), cours(C_D, "Public", "2026-12-18"),
                                  cours(C_N, "Demain", _demain), cours(C_L, "Libre", "2027-01-20"),
                                  {"id": C_U, "name": "Unité", "weekday": 3, "date": "", "time": "18:45", "visible": True}])
    await C.assurer_index(db)   # comme au démarrage du serveur (index uniques posés AVANT les données)
    await db.coaches.insert_one({"email": PARTENAIRE, "name": "Partenaire", "role": "coach"})
    await S.v598_niches(ADMIN)
    _niches = {("entreprises" if n.get("nom") == "Entreprises" else n["cle"]): n["id"] for n in await db.prospection_niches.find({"coach_id": ADMIN}).to_list(20)}
    await db.partner_prospects.insert_many([
        {"id": "pr-alpha", "organisation_name": "Alpha SA", "city": "Neuchâtel", "city_key": "neuchatel",
         "category": "entreprise", "website": "https://www.alpha.ch", "website_domain": "alpha.ch",
         "dedupe_key": "alpha sa|neuchatel", "coach_id": ADMIN, "niche_id": _niches.get("entreprises"),
         "status": "a_contacter", "created_at": "2026-11-01"},
        {"id": "pr-beta", "organisation_name": "Beta Sàrl", "city": "Neuchâtel", "city_key": "neuchatel",
         "category": "entreprise", "coach_id": ADMIN, "niche_id": _niches.get("entreprises"),
         "dedupe_key": "beta sarl|neuchatel", "status": "a_contacter", "created_at": "2026-11-01"},
        {"id": "pr-resto", "organisation_name": "Resto", "city": "Neuchâtel", "city_key": "neuchatel",
         "category": "restaurant", "coach_id": ADMIN, "niche_id": _niches.get("A"),
         "public_email": "resto@test.local", "dedupe_key": "resto|neuchatel", "status": "a_contacter", "created_at": "2026-11-01"},
    ])
    return _niches


async def compter_ecritures():
    return {c: await db[c].count_documents({}) for c in ("corporate_contracts", "invoices", "reservations",
                                                          "discount_codes", "evenement_retenues")}


async def principal():
    niches = await semer()
    T = httpx.ASGITransport(app=S.fastapi_app)
    async with httpx.AsyncClient(transport=T, base_url="http://banc", timeout=60) as cl:
        # ── 0. Accès refusés (aucune écriture) ─────────────────────────────────
        avant = await compter_ecritures()
        _admin_routes = [("GET", "/api/corporate/grille"), ("GET", "/api/corporate/prix?places=10&mois=6"),
                         ("POST", "/api/corporate/contrats"), ("GET", "/api/corporate/contrats"),
                         ("POST", "/api/corporate/contrats/x/signer"), ("POST", "/api/corporate/contrats/x/editions/2026-12/lier"),
                         ("GET", "/api/corporate/prospects/pr-alpha/suivi-financier"),
                         ("PUT", "/api/invoices/reglages-facturation"), ("GET", "/api/invoices/reglages-facturation")]
        _ok = True
        for _m, _u in _admin_routes:
            for _h in ({}, HP, HF, {"X-User-Email": ADMIN}):
                _r = await cl.request(_m, _u, headers=_h, json={})
                if _r.status_code != 403:
                    _ok = False
                    print("   ", _m, _u, _h.keys(), _r.status_code)
        verifier("0 routes admin Corporate : 403 sans jeton / partenaire / jeton forgé / X-User-Email seul", _ok)
        for _m, _u in (("GET", "/api/invoices"), ("GET", "/api/invoices/AF-CORP-2026-0001/pdf"),
                       ("POST", "/api/invoices/AF-CORP-2026-0001/paiement"), ("POST", "/api/invoices/generate")):
            _r1 = await cl.request(_m, _u, json={})
            _r2 = await cl.request(_m, _u, headers=HF, json={})
            verifier("0b %s %s : 403 sans jeton et avec jeton forgé" % (_m, _u), _r1.status_code == 403 and _r2.status_code == 403,
                     (_r1.status_code, _r2.status_code))
        _r = await cl.get("/api/corporate/invitation/" + "x" * 32)
        verifier("0c invitation inconnue -> 404", _r.status_code == 404, _r.text)
        verifier("0d aucune écriture par les accès refusés", await compter_ecritures() == avant)

        # ── 1. Grille, devis, gel du prix ──────────────────────────────────────
        r = await cl.get("/api/corporate/prix?places=10&mois=6", headers=HA)
        verifier("1 grille 10 places × 6 mois = 600/mois, total 3600", r.json().get("prix_mensuel") == 600 and r.json().get("total") == 3600, r.text)
        verifier("1b grille 5×3=350, 20×12=1000", (await cl.get("/api/corporate/prix?places=5&mois=3", headers=HA)).json()["prix_mensuel"] == 350
                 and (await cl.get("/api/corporate/prix?places=20&mois=12", headers=HA)).json()["total"] == 12000)
        verifier("1c combinaison inconnue -> 400", (await cl.get("/api/corporate/prix?places=7&mois=6", headers=HA)).status_code == 400)
        r = await cl.post("/api/corporate/contrats", headers=HA, json={
            "prospect_id": "pr-alpha", "places": 10, "mois": 3, "mois_debut": "2026-12",
            "facturation": {"nom": "Alpha SA", "adresse": "Rue du Test 1", "ville": "2000 Neuchâtel", "contact": "Mme RH"}})
        K = r.json()
        verifier("1d devis créé : statut devis, 650/mois, total 1950, grille pilote-2026-11",
                 r.status_code == 200 and K["statut"] == "devis" and K["prix_mensuel"] == 650 and K["total"] == 1950
                 and K["grille_version"] == "pilote-2026-11", r.text)
        verifier("1e 3 éditions « à planifier » 2026-12 → 2027-02, aucune date",
                 [e["mois"] for e in K["editions"]] == ["2026-12", "2027-01", "2027-02"]
                 and all(e["statut"] == "a_planifier" and not e["date"] for e in K["editions"]), K["editions"])
        verifier("1f conditions : places perdues, délai 48 h, à planifier",
                 "perdues" in K["conditions"] and "48 h" in K["conditions"] and "à planifier" in K["conditions"], K["conditions"])
        _anc = C.GRILLE[10][3]
        C.GRILLE[10][3] = 999
        r2 = await cl.get("/api/corporate/contrats/" + K["id"], headers=HA)
        r3 = await cl.post("/api/corporate/contrats", headers=HA, json={"prospect_id": "pr-beta", "places": 10, "mois": 3, "mois_debut": "2026-12"})
        C.GRILLE[10][3] = _anc
        verifier("1g la grille change : le contrat existant garde 650 / 1950 (figé)", r2.json()["prix_mensuel"] == 650 and r2.json()["total"] == 1950)
        verifier("1h ... un nouveau devis prend la nouvelle grille", r3.json()["prix_mensuel"] == 999)
        r = await cl.post("/api/corporate/contrats", headers=HA, json={"prospect_id": "inconnu", "places": 10, "mois": 3, "mois_debut": "2026-12"})
        verifier("1i prospect inconnu -> 404", r.status_code == 404)

        # ── 2. Coordonnées vérifiées, devis, numérotation ──────────────────────
        r = await cl.post("/api/invoices/generate", headers=HA, json={"type_document": "devis", "corporate_contract_id": K["id"]})
        verifier("2 devis Entreprise sans coordonnées vérifiées -> 409 (message clair)", r.status_code == 409 and "vérifiées" in r.text, r.text)
        await cl.put("/api/invoices/reglages-facturation", headers=HA, json={"nom": "Association Test", "adresse": "Rue 1",
                                                                             "ville": "2000 Neuchâtel", "iban": "CH00 TEST", "verifie": False})
        r = await cl.post("/api/invoices/generate", headers=HA, json={"type_document": "devis", "corporate_contract_id": K["id"]})
        verifier("2b coordonnées enregistrées mais NON cochées vérifiées -> 409", r.status_code == 409)
        r = await cl.put("/api/invoices/reglages-facturation", headers=HA, json={"nom": "Association Test", "verifie": True})
        verifier("2c « vérifiées » refusé sans adresse/ville/IBAN -> 400", r.status_code == 400)
        r = await cl.put("/api/invoices/reglages-facturation", headers=HA, json={"nom": "Association Test", "adresse": "Rue 1",
                                                                                 "ville": "2000 Neuchâtel", "iban": "CH00 TEST", "verifie": True})
        verifier("2d coordonnées vérifiées (par, le)", r.json().get("verifie") is True and r.json().get("verifie_par") == ADMIN, r.text)
        r = await cl.post("/api/invoices/generate", headers=HA, json={"type_document": "devis", "corporate_contract_id": K["id"]})
        _t = texte_pdf(r.content)
        verifier("2e devis : PDF, numéro DEVIS-2026-0001", r.status_code == 200 and r.content[:4] == b"%PDF"
                 and r.headers.get("x-invoice-number") == "DEVIS-2026-0001", (r.status_code, r.headers.get("x-invoice-number")))
        verifier("2f PDF : titre DEVIS, options, validité, sans TVA ni IDE inventé", "DEVIS" in _t and "Silent Live Fusion" in _t
                 and "Valable" in _t and "TVA" not in _t and "CHE-407" not in _t, _t[-600:])
        rec = await db.invoices.find_one({"invoice_number": "DEVIS-2026-0001"})
        verifier("2g enregistrement : type corporate, devis, statut emise, lié au contrat",
                 rec and rec.get("type") == "corporate" and rec.get("type_document") == "devis" and rec.get("statut") == "emise"
                 and rec.get("corporate_contract_id") == K["id"], rec)
        r = await cl.post("/api/invoices/generate", headers=HA, json={"corporate_contract_id": K["id"], "mois": "2026-12"})
        verifier("2h facture avant signature -> 409", r.status_code == 409, r.text)
        r = await cl.post("/api/invoices/generate", headers=HP, json={"type_document": "devis", "corporate_contract_id": K["id"]})
        verifier("2i partenaire : document Entreprise -> 403", r.status_code == 403, r.text)

        # ── 3. Signature, factures mensuelles ──────────────────────────────────
        r = await cl.post("/api/corporate/contrats/%s/signer" % K["id"], headers=HA)
        K = r.json()
        verifier("3 acceptation -> contrat signé, lien actif, jeton long", K["statut"] == "signe" and K["token_actif"] and len(K["token"]) >= 32, r.text)
        verifier("3b re-signer -> 409", (await cl.post("/api/corporate/contrats/%s/signer" % K["id"], headers=HA)).status_code == 409)
        r = await cl.post("/api/invoices/generate", headers=HA, json={"corporate_contract_id": K["id"], "mois": "2026-12"})
        verifier("3c facture décembre : AF-CORP-2026-0001, PDF", r.status_code == 200 and r.headers.get("x-invoice-number") == "AF-CORP-2026-0001", r.text[:200])
        _t = texte_pdf(r.content)
        verifier("3d PDF facture : IBAN vérifié, échéance, aucune TVA", "CH00 TEST" in _t and "ch" in _t.lower() and "TVA" not in _t)
        r = await cl.post("/api/invoices/generate", headers=HA, json={"corporate_contract_id": K["id"], "mois": "2026-12"})
        verifier("3e 2e facture pour le même mois -> 409", r.status_code == 409, r.text)
        rs = await asyncio.gather(*[cl.post("/api/invoices/generate", headers=HA, json={"corporate_contract_id": K["id"], "mois": "2027-01"}) for _ in range(4)])
        verifier("3f 4 émissions simultanées de janvier -> UNE facture", sum(1 for x in rs if x.status_code == 200) == 1
                 and await db.invoices.count_documents({"corporate_contract_id": K["id"], "mois": "2027-01"}) == 1, [x.status_code for x in rs])
        n_jan = await db.invoices.find_one({"corporate_contract_id": K["id"], "mois": "2027-01"})
        verifier("3g numérotation séquentielle AF-CORP-2026-NNNN", re.match(r"^AF-CORP-2026-\d{4}$", n_jan["invoice_number"]), n_jan["invoice_number"])
        verifier("3h mois hors contrat -> 400", (await cl.post("/api/invoices/generate", headers=HA, json={"corporate_contract_id": K["id"], "mois": "2027-05"})).status_code == 400)
        K = (await cl.get("/api/corporate/contrats/" + K["id"], headers=HA)).json()
        verifier("3i échéancier : 2 émises, février à émettre (préparer ≠ émettre)",
                 [x["statut"] for x in K["finances"]["echeancier"]] == ["emise", "emise", "a_emettre"], K["finances"]["echeancier"])

        # ── 4. Paiements ───────────────────────────────────────────────────────
        r = await cl.post("/api/invoices/AF-CORP-2026-0001/paiement", headers=HA, json={"montant": 300, "reference": "VIR-1"})
        verifier("4 paiement partiel 300 (virement par défaut) : reste émise", r.status_code == 200 and r.json()["statut"] == "emise"
                 and r.json()["montant_paye"] == 300 and r.json()["paiements"][0]["mode"] == "virement", r.text)
        verifier("4b paiement > reste dû -> 400", (await cl.post("/api/invoices/AF-CORP-2026-0001/paiement", headers=HA, json={"montant": 400})).status_code == 400)
        verifier("4c paiement « offert » -> 400", (await cl.post("/api/invoices/AF-CORP-2026-0001/paiement", headers=HA, json={"montant": 0, "mode": "offert"})).status_code == 400)
        r = await cl.post("/api/invoices/AF-CORP-2026-0001/paiement", headers=HA, json={"montant": 350, "mode": "twint"})
        verifier("4d solde 350 -> décembre payée", r.json().get("statut") == "payee", r.text)
        K = (await cl.get("/api/corporate/contrats/" + K["id"], headers=HA)).json()
        verifier("4e une facture payée ne solde PAS les autres mois (janvier émise, février à émettre)",
                 [x["statut"] for x in K["finances"]["echeancier"]] == ["payee", "emise", "a_emettre"], K["finances"]["echeancier"])
        verifier("4f finances calculées : facturé 1300, payé 650, dû 1300", K["finances"]["facture"] == 1300 and K["finances"]["paye"] == 650
                 and K["finances"]["du"] == 1300, K["finances"])
        verifier("4g paiement d'une facture payée -> 409", (await cl.post("/api/invoices/AF-CORP-2026-0001/paiement", headers=HA, json={"montant": 1})).status_code == 409)
        rs = await asyncio.gather(*[cl.post("/api/invoices/%s/paiement" % n_jan["invoice_number"], headers=HA, json={"montant": 650}) for _ in range(5)])
        _j = await db.invoices.find_one({"invoice_number": n_jan["invoice_number"]})
        verifier("4h 5 paiements simultanés du solde -> un seul compté", sum(1 for x in rs if x.status_code == 200) == 1 and _j["montant_paye"] == 650
                 and len(_j["paiements"]) == 1, [x.status_code for x in rs])

        # ── 5. Liste, re-téléchargement, autorisations ─────────────────────────
        r = await cl.get("/api/invoices?type=corporate", headers=HA)
        _rows = r.json()["factures"]
        verifier("5 liste Entreprise : contrat, durée, mensuel, total joints", r.status_code == 200 and _rows and
                 all(x.get("contrat", {}).get("entreprise") == "Alpha SA" and x["contrat"]["duree_mois"] == 3 for x in _rows), _rows[:1])
        verifier("5b partenaire : ne voit aucune facture Entreprise", (await cl.get("/api/invoices?type=corporate", headers=HP)).json()["factures"] == [])
        r = await cl.get("/api/invoices/AF-CORP-2026-0001/pdf", headers=HA)
        verifier("5c re-téléchargement super-admin : PDF", r.status_code == 200 and r.content[:4] == b"%PDF")
        verifier("5d re-téléchargement partenaire -> 404 ; anonyme / forgé -> 403",
                 (await cl.get("/api/invoices/AF-CORP-2026-0001/pdf", headers=HP)).status_code == 404
                 and (await cl.get("/api/invoices/AF-CORP-2026-0001/pdf")).status_code == 403
                 and (await cl.get("/api/invoices/AF-CORP-2026-0001/pdf", headers=HF)).status_code == 403)

        # ── 6. Facture classique (héritée) inchangée ───────────────────────────
        r = await cl.post("/api/invoices/generate", headers=HP, json={"recipient": {"name": "Client"}, "items": [
            {"description": "Cours", "quantity": 2, "unit_price": 30}]})
        _cd = r.headers.get("content-disposition", "")
        _num = re.search(r'facture_(.+)\.pdf', _cd).group(1) if "facture_" in _cd else ""
        _rec = await db.invoices.find_one({"invoice_number": _num}, {"_id": 0})
        verifier("6 facture classique : 200, numéro AF-AAAAMMJJhhmmss, même nom de fichier", r.status_code == 200
                 and re.match(r"^AF-\d{14}$", _num), (r.status_code, _cd))
        verifier("6b enregistrement classique : aucun champ Entreprise / statut ajouté",
                 _rec and not ({"type", "statut", "type_document", "corporate_contract_id", "paiements", "cle_unicite"} & set(_rec))
                 and _rec.get("total") == 60 and _rec.get("cree_par") == PARTENAIRE, _rec)
        _t = texte_pdf(r.content)
        verifier("6c PDF classique : FACTURE, IBAN et IDE par défaut d'avant", "FACTURE" in _t and "CH77 0900 0000 1688 2939 4" in _t
                 and "CHE-407.097.646" in _t)
        r = await cl.post("/api/invoices/%s/paiement" % _num, headers=HP, json={"montant": 60})
        verifier("6d paiement sur facture classique -> 409 (non suivie)", r.status_code == 409, r.text)
        r = await cl.get("/api/invoices/%s/pdf" % _num, headers=HP)
        verifier("6e l'auteur re-télécharge sa facture classique", r.status_code == 200 and r.content[:4] == b"%PDF")

        # ── 7. Rappels (brouillon, aucun envoi) ────────────────────────────────
        n_e = len(EMAILS)
        await db.invoices.update_one({"invoice_number": n_jan["invoice_number"]}, {"$set": {"statut": "emise", "montant_paye": 0, "paiements": [], "echeance": "2026-11-01"}})
        r = await cl.get("/api/invoices/corporate/a-relancer", headers=HA)
        verifier("7 facture échue listée « à relancer »", any(x["invoice_number"] == n_jan["invoice_number"] and x["en_retard"] for x in r.json()["factures"]), r.text)
        r = await cl.post("/api/invoices/%s/rappel" % n_jan["invoice_number"], headers=HA)
        verifier("7b brouillon professionnel : numéro, montant, aucune promesse d'envoi", r.status_code == 200 and n_jan["invoice_number"] in r.json()["texte"]
                 and "650.00 CHF" in r.json()["texte"], r.text)
        r = await cl.get("/api/invoices/corporate/a-relancer", headers=HA)
        verifier("7c dernier rappel affiché (date + auteur)", any((x.get("dernier_rappel") or {}).get("par") == ADMIN for x in r.json()["factures"]))
        await asyncio.sleep(0.2)
        verifier("7d AUCUN e-mail envoyé par le rappel", len(EMAILS) == n_e, EMAILS[n_e:])
        verifier("7e rappel sur facture payée -> 409", (await cl.post("/api/invoices/AF-CORP-2026-0001/rappel", headers=HA)).status_code == 409)

        # ── 8. Suivi financier du prospect ─────────────────────────────────────
        r = await cl.get("/api/corporate/prospects/pr-alpha/suivi-financier", headers=HA)
        _c = r.json()["contrats"][0]
        verifier("8 dossier prospect : statut, places, devis + factures, payé/dû (lecture)", _c["statut"] == "signe" and _c["places"] == 10
                 and _c["devis"][0]["numero"] == "DEVIS-2026-0001" and len(_c["factures"]) == 2 and _c["paye"] == 650, _c)
        verifier("8b rien n'est copié sur la fiche prospect", not ({"contrat", "factures", "finances"} & set(await db.partner_prospects.find_one({"id": "pr-alpha"}, {"_id": 0}))))

        # ── 9. Lier une édition = retenir les places ───────────────────────────
        r = await cl.post("/api/corporate/contrats/%s/editions/2027-01/lier" % K["id"], headers=HA, json={"offer_id": EVT_A})
        verifier("9 événement d'un autre mois -> 409", r.status_code == 409, r.text)
        r = await cl.post("/api/corporate/contrats/%s/editions/2026-12/lier" % K["id"], headers=HA, json={"offer_id": EVT_A})
        K = r.json()
        _ed = K["editions"][0]
        verifier("9b décembre planifiée (date + lieu réels)", r.status_code == 200 and _ed["statut"] == "planifiee"
                 and _ed["date"] == "2026-12-16T19:00:00" and _ed["lieu"] == "Neuchâtel", r.text)
        _code = await db.discount_codes.find_one({"id": _ed["code_id"]}, {"_id": 0})
        verifier("9c code caché : 100 %, maxUses 10, limité à CET événement, expire le jour J, non devinable",
                 _code["type"] == "100%" and _code["maxUses"] == 10 and set(_code["courses"]) == {EVT_A, C_A}
                 and _code["expiresAt"] == "2026-12-16" and len(_code["code"]) >= 20 and _code["corporate_contract_id"] == K["id"], _code)
        _offA = await db.offers.find_one({"id": EVT_A}, {"_id": 0})
        verifier("9d occupation = 10 places retenues sur 12", await E.occupation(db, _offA) == 10)
        r = await cl.post("/api/corporate/contrats/%s/editions/2026-12/lier" % K["id"], headers=HA, json={"offer_id": EVT_A})
        verifier("9e relier la même édition -> 409", r.status_code == 409)
        K2 = (await cl.post("/api/corporate/contrats", headers=HA, json={"prospect_id": "pr-beta", "places": 5, "mois": 3, "mois_debut": "2026-12",
                                                                        "delai_modif_heures": 48})).json()
        r = await cl.post("/api/corporate/contrats/%s/editions/2026-12/lier" % K2["id"], headers=HA, json={"offer_id": EVT_A})
        verifier("9f devis non signé : aucune retenue -> 409", r.status_code == 409)
        await cl.post("/api/corporate/contrats/%s/signer" % K2["id"], headers=HA)
        r = await cl.post("/api/corporate/contrats/%s/editions/2026-12/lier" % K2["id"], headers=HA, json={"offer_id": EVT_A})
        verifier("9g 2e entreprise (5 places) : seulement 2 restantes -> 409, rien de retenu", r.status_code == 409
                 and "2 restantes" in r.text and await E.occupation(db, _offA) == 10, r.text)

        # ── 10. Invitation publique ────────────────────────────────────────────
        tok = K["token"]
        r = await cl.get("/api/corporate/invitation/" + tok)
        j = r.json()
        verifier("10 page publique : entreprise, décembre daté, janvier/février à planifier SANS date",
                 j["entreprise"] == "Alpha SA" and j["editions"][0].get("date") and j["editions"][0]["places_restantes"] == 10
                 and all("date" not in e for e in j["editions"][1:]), j)
        verifier("10b aucune donnée personnelle ni code dans la page publique",
                 "CORP-" not in r.text and "@" not in r.text and "iban" not in r.text.lower(), r.text)

        async def inscrire(email, mois="2026-12", token=tok, **k):
            _b = {"mois": mois, "nom": "Employé Test", "email": email, "whatsapp": "+41 79 000 00 00", "terms_accepted": True}
            _b.update(k)
            return await cl.post("/api/corporate/invitation/%s/inscription" % token, json=_b,
                                 headers={"X-Forwarded-For": "10.9.%d.%d" % (len(email) % 250, abs(hash(email)) % 250)})

        n_stripe = len(APPELS_STRIPE)
        r = await inscrire("Employe1@Alpha.test")
        j = r.json()
        resa = await db.reservations.find_one({"userEmail": "employe1@alpha.test"}, {"_id": 0})
        verifier("11 inscription : 0 CHF, billet (QR d'entrée), aucun Stripe", r.status_code == 200 and j["prix"] == 0
                 and j["reservation"]["reservationCode"] and len(APPELS_STRIPE) == n_stripe, r.text)
        verifier("11b réservation liée entreprise + contrat + édition, source V628", resa and resa["totalPrice"] == 0
                 and resa["corporate_contract_id"] == K["id"] and resa["corporate_mois"] == "2026-12" and resa["source"] == E.SOURCE_CODE
                 and resa["courseId"] == C_A, resa)
        r = await inscrire("employe1@alpha.test")
        verifier("11c même identité (casse différente) -> 409 « déjà inscrite »", r.status_code == 409 and "déjà inscrite" in r.text, r.text)
        r = await inscrire("x@alpha.test", mois="2027-01")
        verifier("11d édition à planifier -> 409", r.status_code == 409 and "planifiée" in r.text, r.text)
        r = await inscrire("bad-email")
        verifier("11e e-mail invalide -> 400", r.status_code == 400)
        rs = await asyncio.gather(*[inscrire("simul%d@perso.test" % i) for i in range(15)])
        _ok = sum(1 for x in rs if x.status_code == 200)
        verifier("11f 15 inscriptions simultanées pour 9 places restantes -> exactement 9", _ok == 9, [x.status_code for x in rs])
        _code = await db.discount_codes.find_one({"id": _ed["code_id"]}, {"_id": 0})
        verifier("11g code : used == maxUses == 10, 10 réservations", _code["used"] == 10
                 and await db.reservations.count_documents({"corporate_contract_id": K["id"]}) == 10, _code)
        r = await inscrire("onzieme@perso.test")
        verifier("11h 11e personne -> 409 « places prises »", r.status_code == 409 and "places" in r.text, r.text)
        verifier("11i occupation toujours 10 (place Corporate jamais comptée deux fois)", await E.occupation(db, _offA) == 10)

        # ── 12. Capacité publique concurrente (2 places publiques restantes) ───
        await db.discount_codes.insert_many([{"id": "pub-%d" % i, "code": "PUBLIC-%02d" % i, "type": "100%", "value": 100, "maxUses": 1,
                                              "used": 0, "active": True, "expiresAt": "2026-12-16", "courses": [EVT_A, C_A],
                                              "coach_id": ADMIN} for i in range(8)])
        rs = await asyncio.gather(*[cl.post("/api/evenements/%s/place-code" % EVT_A, headers={"X-Forwarded-For": "10.5.0.%d" % i},
                                            json={"prenom": "P", "nom": "Q", "email": "pub%d@test.local" % i, "code": "PUBLIC-%02d" % i,
                                                  "terms_accepted": True}) for i in range(8)])
        verifier("12 8 places par code simultanées, 2 restantes -> exactement 2 (jamais de surréservation)",
                 sum(1 for x in rs if x.status_code == 200) == 2 and await E.occupation(db, _offA) == 12, [x.status_code for x in rs])
        verifier("12b codes refusés pour « complet » non débités", sum([(await db.discount_codes.find_one({"id": "pub-%d" % i}))["used"] for i in range(8)]) == 2)
        r = await cl.post("/api/evenements/%s/place-code" % EVT_A, headers={"X-Forwarded-For": "10.5.1.1"},
                          json={"prenom": "P", "nom": "Q", "email": "pirate@test.local", "code": _code["code"], "terms_accepted": True})
        verifier("12c code Entreprise saisi sur la page publique de l'événement -> refus neutre 400", r.status_code == 400, r.text)
        r = await cl.post("/api/create-checkout-session", json={"amount": 30, "productName": "x", "originUrl": "http://127.0.0.1",
                                                                "offerId": EVT_A, "quantity": 1, "customerEmail": "a@test.local"})
        verifier("12d paiement public sur événement complet -> 409", r.status_code == 409, r.text)

        # ── 13. Correction / annulation ────────────────────────────────────────
        rid = resa["id"]
        r = await cl.patch("/api/corporate/contrats/%s/inscriptions/%s" % (K["id"], rid), headers=HA, json={"nom": "Employée Renommée"})
        verifier("13 renommer", r.status_code == 200 and r.json()["userName"] == "Employée Renommée", r.text)
        r = await cl.patch("/api/corporate/contrats/%s/inscriptions/%s" % (K["id"], rid), headers=HA, json={"email": (await db.reservations.find_one({"corporate_contract_id": K["id"], "id": {"$ne": rid}}))["userEmail"]})
        verifier("13b remplacer par une adresse déjà inscrite -> 409", r.status_code == 409, r.text)
        r = await cl.patch("/api/corporate/contrats/%s/inscriptions/%s" % (K["id"], rid), headers=HA, json={"email": "remplacant@alpha.test"})
        verifier("13c remplacer la personne (nouvel e-mail) : même billet, réclamation déplacée", r.status_code == 200
                 and r.json()["userEmail"] == "remplacant@alpha.test"
                 and await db[E.COLL_PLACES].find_one({"_id": "code:%s:remplacant@alpha.test" % EVT_A})
                 and not await db[E.COLL_PLACES].find_one({"_id": "code:%s:employe1@alpha.test" % EVT_A}), r.text)
        r = await cl.delete("/api/corporate/contrats/%s/inscriptions/%s" % (K["id"], rid), headers=HA)
        _code = await db.discount_codes.find_one({"id": _ed["code_id"]}, {"_id": 0})
        verifier("13d annuler : réservation supprimée, code rendu (used 9)", r.status_code == 200 and _code["used"] == 9
                 and not await db.reservations.find_one({"id": rid}), (r.text, _code.get("used")))
        verifier("13e la place revient à l'ENTREPRISE (occupation 12 : jamais rendue au public)", await E.occupation(db, _offA) == 12)
        r = await inscrire("nouvelle@perso.test")
        verifier("13f une nouvelle employée prend la place libérée", r.status_code == 200, r.text)
        r = await cl.get("/api/corporate/contrats/%s/editions/2026-12/inscriptions" % K["id"], headers=HA)
        verifier("13g liste des inscriptions (admin) : 10, places restantes 0", len(r.json()["inscriptions"]) == 10 and r.json()["places_restantes"] == 0, r.text[:300])
        verifier("13h liste des inscriptions : partenaire -> 403",
                 (await cl.get("/api/corporate/contrats/%s/editions/2026-12/inscriptions" % K["id"], headers=HP)).status_code == 403)

        # ── 14. Délai, jeton, statut ───────────────────────────────────────────
        r = await cl.post("/api/corporate/contrats/%s/editions/2026-11/lier" % K2["id"], headers=HA, json={"offer_id": EVT_N})
        verifier("14 (mois hors contrat 2026-11 -> 404)", r.status_code == 404)
        K3 = (await cl.post("/api/corporate/contrats", headers=HA, json={"prospect_id": "pr-beta", "places": 5, "mois": 3,
                                                                        "mois_debut": (await db.courses.find_one({"id": C_N}))["date"][:7]})).json()
        await cl.post("/api/corporate/contrats/%s/signer" % K3["id"], headers=HA)
        r = await cl.post("/api/corporate/contrats/%s/editions/%s/lier" % (K3["id"], K3["mois_debut"]), headers=HA, json={"offer_id": EVT_N})
        K3 = r.json()
        r = await inscrire("tard@perso.test", mois=K3["mois_debut"], token=K3["token"])
        verifier("14b événement demain, délai 48 h -> inscriptions closes (409)", r.status_code == 409 and "clos" in r.text, r.text)
        r = await cl.post("/api/corporate/contrats/%s/lien" % K["id"], headers=HA, json={"action": "revoquer"})
        verifier("14c lien révoqué : page et inscription -> 404", (await cl.get("/api/corporate/invitation/" + tok)).status_code == 404
                 and (await inscrire("apres-revoc@perso.test")).status_code == 404)
        K = (await cl.post("/api/corporate/contrats/%s/lien" % K["id"], headers=HA, json={"action": "regenerer"})).json()
        verifier("14d lien régénéré : l'ancien reste mort, le nouveau répond", K["token"] != tok
                 and (await cl.get("/api/corporate/invitation/" + tok)).status_code == 404
                 and (await cl.get("/api/corporate/invitation/" + K["token"])).status_code == 200)
        r = await cl.get("/api/corporate/invitation/" + (K2.get("token") or ""))
        K4 = (await cl.post("/api/corporate/contrats", headers=HA, json={"prospect_id": "pr-beta", "places": 5, "mois": 3, "mois_debut": "2027-01"})).json()
        verifier("14e un devis n'a pas de lien (aucune place à 0 CHF)", K4["token"] is None and not K4["token_actif"])
        r = await cl.post("/api/corporate/contrats/%s/statut" % K3["id"], headers=HA, json={"statut": "resilie"})
        _ret3 = await db.evenement_retenues.find_one({"_id": "corp:%s:%s" % (K3["id"], K3["mois_debut"])})
        _c3 = await db.discount_codes.find_one({"corporate_contract_id": K3["id"]})
        verifier("14f résiliation : lien coupé, retenue rendue, code désactivé", r.json()["statut"] == "resilie" and not r.json()["token_actif"]
                 and _ret3["statut"] == "liberee" and _c3["active"] is False, (r.text[:200], _ret3, _c3))

        # ── 15. Code Entreprise inutilisable ailleurs ──────────────────────────
        _cc = (await db.discount_codes.find_one({"id": _ed["code_id"]}))["code"]
        await db.discount_codes.update_one({"id": _ed["code_id"]}, {"$set": {"used": 0}})
        n0 = len(APPELS_STRIPE)
        r = await cl.post("/api/create-checkout-session", json={"amount": 30, "productName": "Cours", "originUrl": "http://127.0.0.1",
                                                                "offerId": UNITE, "quantity": 1, "customerEmail": "b@test.local", "promoCode": _cc})
        _li = ((APPELS_STRIPE[-1].get("line_items") or [{}])[0].get("price_data") or {}) if len(APPELS_STRIPE) > n0 else {}
        verifier("15 code Entreprise au paiement d'un autre cours : aucune remise (plein tarif ou refus)",
                 r.status_code != 200 or _li.get("unit_amount") == 3000, (r.status_code, r.text[:200], _li))
        await db.discount_codes.update_one({"id": _ed["code_id"]}, {"$set": {"used": 10}})

        # ── 16. Retenues de paiement : concurrence, expiration, webhook ────────
        _offD = await db.offers.find_one({"id": EVT_D}, {"_id": 0})
        rs = await asyncio.gather(*[cl.post("/api/create-checkout-session", json={
            "amount": 30, "productName": "Public", "originUrl": "http://127.0.0.1", "offerId": EVT_D, "quantity": 1,
            "customerEmail": "acheteur%d@test.local" % i}) for i in range(8)])
        verifier("16 8 paiements simultanés pour 3 places -> 3 sessions Stripe, 5 refus 409",
                 sum(1 for x in rs if x.status_code == 200) == 3 and sum(1 for x in rs if x.status_code == 409) == 5, [x.status_code for x in rs])
        _rets = await db.evenement_retenues.find({"offer_id": EVT_D, "type": "stripe", "statut": "active"}).to_list(10)
        verifier("16b 3 retenues actives, metadata Stripe porte la retenue", len(_rets) == 3
                 and sum(1 for p in APPELS_STRIPE if (p.get("metadata") or {}).get("evenement_retenue")) >= 3)
        _md = next(p["metadata"] for p in reversed(APPELS_STRIPE) if (p.get("metadata") or {}).get("evenement_retenue"))
        r = await cl.post("/api/webhook/stripe", content=json.dumps({"id": "evt_x", "object": "event", "type": "checkout.session.expired",
                                                                     "data": {"object": {"id": "cs_exp", "object": "checkout.session", "metadata": _md}}}))
        verifier("16c checkout.session.expired : la retenue est rendue", r.status_code == 200
                 and (await db.evenement_retenues.find_one({"_id": _md["evenement_retenue"]}))["statut"] == "liberee", r.text)
        r = await cl.post("/api/create-checkout-session", json={"amount": 30, "productName": "Public", "originUrl": "http://127.0.0.1",
                                                                "offerId": EVT_D, "quantity": 1, "customerEmail": "suivant@test.local"})
        verifier("16d la place rendue se revend", r.status_code == 200, r.text[:200])
        _rt = (await db.evenement_retenues.find_one({"offer_id": EVT_D, "type": "stripe", "statut": "active"}))["_id"]
        _r, _c = await E.apres_paiement(db, session_id="cs_paye_1", offre_id=EVT_D, email="payeur@test.local", nom="P",
                                        code="", subscription_id=None, montant=30, retenue_id=_rt)
        verifier("16e webhook payé : retenue CONVERTIE en réservation, occupation inchangée (3)", _c and _r["offerId"] == EVT_D
                 and (await db.evenement_retenues.find_one({"_id": _rt}))["statut"] == "convertie" and await E.occupation(db, _offD) == 3)
        _r2, _c2 = await E.apres_paiement(db, session_id="cs_paye_1", offre_id=EVT_D, email="payeur@test.local", nom="P",
                                          code="", subscription_id=None, montant=30, retenue_id=_rt)
        verifier("16f webhook rejoué : même réservation, aucune 2e place", not _c2 and _r2["id"] == _r["id"]
                 and await db.reservations.count_documents({"offerId": EVT_D}) == 1)
        _r3, _c3 = await E.apres_paiement(db, session_id="cs_sans_retenue", offre_id=EVT_D, email="tardif@test.local", nom="T",
                                          code="", subscription_id=None, montant=30, retenue_id=None)
        verifier("16g billet payé sans retenue sur événement plein : honoré mais MARQUÉ surréservation", _c3 and _r3.get("surreservation") is True)
        _offL = await db.offers.find_one({"id": EVT_L}, {"_id": 0})
        rs = await asyncio.gather(*[cl.post("/api/create-checkout-session", json={"amount": 30, "productName": "Libre", "originUrl": "http://127.0.0.1",
                                                                                 "offerId": EVT_L, "quantity": 1, "customerEmail": "l%d@test.local" % i}) for i in range(5)])
        verifier("16h événement SANS capacité : inchangé (aucune retenue, aucun verrou, tout passe)",
                 all(x.status_code == 200 for x in rs) and await db.evenement_retenues.count_documents({"offer_id": EVT_L}) == 0
                 and await db.evenement_verrous.count_documents({}) == 0 and E.capacite(_offL) is None, [x.status_code for x in rs])

        # ── 17. Prospection ────────────────────────────────────────────────────
        r = await cl.post("/api/partner-prospects", headers=HA, json={"organisation_name": "Gamma AG", "category": "entreprise", "city": "Neuchâtel"})
        verifier("17 catégorie « entreprise » acceptée", r.status_code == 200 and r.json()["category"] == "entreprise", r.text[:200])
        r = await cl.post("/api/partner-prospects", headers=HA, json={"organisation_name": "Alpha Ressources Humaines", "category": "entreprise",
                                                                      "city": "Neuchâtel", "website": "https://rh.alpha.ch/contact"})
        _d = (r.json().get("detail") or {}).get("possible_duplicates") or []
        verifier("17b même domaine enregistrable (rh.alpha.ch / alpha.ch) -> 409 signalé « domaine », rien créé",
                 r.status_code == 409 and any("domaine" in x["matched_on"] and x["id"] == "pr-alpha" for x in _d)
                 and not await db.partner_prospects.find_one({"organisation_name": "Alpha Ressources Humaines"}), r.text[:300])
        r = await cl.post("/api/partner-prospects", headers=HA, json={"organisation_name": "Alpha Lausanne", "category": "entreprise",
                                                                      "city": "Lausanne", "website": "alpha.ch"})
        _d = (r.json().get("detail") or {}).get("possible_duplicates") or []
        verifier("17c autre ville : signalé (domaine + ville_differente), jamais fusionné", r.status_code == 409
                 and any("ville_differente" in x["matched_on"] for x in _d), r.text[:300])
        r = await cl.post("/api/partner-prospects", headers=HA, json={"organisation_name": "Alpha Lausanne", "category": "entreprise",
                                                                      "city": "Lausanne", "website": "alpha.ch", "allow_duplicate": True})
        verifier("17d allow_duplicate : deux fiches distinctes coexistent", r.status_code == 200
                 and await db.partner_prospects.count_documents({"website_domain": {"$in": ["alpha.ch"]}}) == 2, r.text[:200])
        await db.partner_prospects.update_one({"id": "pr-beta"}, {"$set": {"website_domain": "facebook.com"}})
        r = await cl.post("/api/partner-prospects", headers=HA, json={"organisation_name": "Delta", "category": "entreprise",
                                                                      "city": "Bienne", "website": "https://facebook.com/delta"})
        verifier("17e domaine partagé (facebook.com) : pas un signal", r.status_code == 200, r.text[:200])
        _ent = niches.get("entreprises")
        r = await cl.post("/api/prospect-campaigns/prepare", headers=HA, json={"dry_run": True, "niche_id": _ent})
        _ids = {a.get("prospect_ids", [None])[0] if isinstance(a.get("prospect_ids"), list) else None for a in r.json().get("actions", [])}
        _n_niche = await db.partner_prospects.count_documents({"niche_id": _ent})
        verifier("17f préparation filtrée par niche : uniquement la niche (Resto exclu)", r.status_code == 200
                 and r.json()["campaign"]["nb_fiches"] == _n_niche and "pr-resto" not in json.dumps(r.json()), (r.status_code, r.text[:300]))
        r = await cl.post("/api/prospect-campaigns/prepare", headers=HA, json={"dry_run": True})
        verifier("17g sans niche : comportement d'avant (toutes les fiches)", r.status_code == 200
                 and r.json()["campaign"]["nb_fiches"] == await db.partner_prospects.count_documents({}), r.text[:200])
        verifier("17h dry-run : aucune campagne écrite", await db.prospect_campaigns.count_documents({}) == 0)

        # ── V657b : corrections de la revue de sécurité
        for _pref in ("AF-CORP-2026-9999", "devis-2026-9999"):
            r = await cl.post("/api/invoices/generate", headers=HA, json={"invoice_number": _pref, "recipient": {"name": "X"},
                                                                          "items": [{"description": "x", "quantity": 1, "unit_price": 1}]})
            verifier("18a numéro réservé saisi à la main (%s) : 400, rien d'écrit" % _pref,
                     r.status_code == 400 and await db.invoices.count_documents({"invoice_number": _pref}) == 0, r.text[:200])
        verifier("18b retenue de paiement : 35 minutes au plus", E.RETENUE_STRIPE_DUREE_S <= 35 * 60, E.RETENUE_STRIPE_DUREE_S)
        import inspect as _insp
        verifier("18c nom public : caractères HTML retirés avant tout e-mail", "[<>&" in _insp.getsource(C.v657_inscrire))

    await asyncio.sleep(0.3)
    await S.client.drop_database(BASE)
    print("\n%d/%d PASS" % (sum(RES), len(RES)))
    return all(RES)


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(principal()) else 1)
