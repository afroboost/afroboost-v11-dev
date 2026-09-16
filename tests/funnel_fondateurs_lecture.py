#!/usr/bin/env python3
"""FUNNEL FONDATEURS — LECTURE SEULE (aucune ecriture, aucun envoi).

Imprime les 8 etapes du tunnel telles que l'existant les MESURE deja, plus les
statuts des campagnes « Fondateurs V1 » / « Offre Fondateurs » (WhatsApp : Meta
`whatsapp_statuts` par wamid ; e-mail : `campaigns.results[]` + rebonds P3B1).
Etapes NON mesurees par l'existant (3 arrivee page, 4 ouverture fiche,
5 clic Acheter) : dites telles quelles, rien n'est ajoute — c'est PostHog
(index.html) qui voit les pages, pas la base.

Usage : python3 tests/funnel_fondateurs_lecture.py [--depuis 2026-09-16]
"""
import os, re, sys, argparse
from datetime import datetime, timezone
from pymongo import MongoClient

OFFRE_FONDATEURS = "cc73f6ee-163a-433d-b5f0-c00c6392b437"
PREFIXES_CAMPAGNES = ("Fondateurs V1", "Offre Fondateurs", "V2 ")
UTM = "fondateurs2026"


def _env():
    env = {}
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for l in open(os.path.join(racine, ".env.local")):
        l = l.strip()
        if "=" in l and not l.startswith("#"):
            k, v = l.split("=", 1); env[k] = v.strip().strip('"').strip("'")
    return env


def _mentionne_fondateurs(doc):
    s = str(doc)
    return OFFRE_FONDATEURS in s or UTM in s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--depuis", default="2026-09-16")
    a = ap.parse_args()
    depuis = a.depuis
    db = MongoClient(_env()["MONGO_URL"], serverSelectionTimeoutMS=40000)["promo-credits-lab"]

    print("FUNNEL FONDATEURS — lecture seule — depuis", depuis, "—", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    # 1. message delivre
    camps = [c for c in db.campaigns.find({}, {"_id": 0, "id": 1, "name": 1, "status": 1, "results": 1, "created_at": 1, "createdAt": 1})
             if str(c.get("name") or "").startswith(PREFIXES_CAMPAGNES)]
    print(f"\n[1] MESSAGES — {len(camps)} campagne(s) Fondateurs")
    wamids = {}
    for c in camps:
        res = c.get("results") or []
        par = {}
        for r in res:
            par[(r.get("channel"), r.get("status"))] = par.get((r.get("channel"), r.get("status")), 0) + 1
            if r.get("channel") == "whatsapp" and (r.get("sid") or r.get("wamid")):
                wamids[r.get("sid") or r.get("wamid")] = c.get("name")
        print(f"   - {c.get('name')[:50]:50} statut={c.get('status')} | resultats={dict(sorted((f'{k[0]}:{k[1]}', v) for k, v in par.items()))}")
    if wamids:
        stat = {}
        for s in db.whatsapp_statuts.find({"wamid": {"$in": list(wamids)}}, {"_id": 0, "wamid": 1, "statut": 1, "erreurs": 1}):
            stat.setdefault(s["wamid"], set()).add(s.get("statut"))
        cpt = {"sent": 0, "delivered": 0, "read": 0, "failed": 0, "sans_statut_meta": 0}
        for w in wamids:
            st = stat.get(w, set())
            if not st: cpt["sans_statut_meta"] += 1
            for k in ("sent", "delivered", "read", "failed"):
                if k in st: cpt[k] += 1
        print(f"   WhatsApp (Meta, par message) : {cpt}  — « sent » n'est PAS « delivered »")
        for w in wamids:
            for s in db.whatsapp_statuts.find({"wamid": w, "statut": "failed"}, {"_id": 0, "erreurs": 1}):
                print("     failed :", [(e.get("code"), (e.get("title") or "")[:40]) for e in (s.get("erreurs") or [])])
    else:
        print("   WhatsApp : aucun wamid enregistre (rien d'envoye ou champ absent)")
    rebonds = db.subscribers.count_documents({"channel": "email", "status": {"$in": ["bounced", "opted_out"]}, "updated_at": {"$gte": depuis}})
    print(f"   E-mail : rebonds/refus enregistres depuis {depuis} (subscribers) : {rebonds}  — livraison detaillee = tableau Resend")
    # 2. clic (attribution) -> mesure seulement quand l'attribution atteint le serveur (checkout ou reservation)
    pt = list(db.payment_transactions.find({"created_at": {"$gte": depuis}}, {"_id": 0, "payment_status": 1, "metadata": 1, "attribution": 1, "amount_total": 1, "customer_email": 1}))
    pt_f = [p for p in pt if (p.get("metadata") or {}).get("offer_id") == OFFRE_FONDATEURS]
    attrib = [p for p in pt_f if _mentionne_fondateurs(p.get("attribution") or (p.get("metadata") or {}))]
    print(f"\n[2] CLIC (attribution utm/ref) : NON MESURE en base tant qu'aucun checkout/reservation n'est cree ; attribution 'fondateurs2026' vue sur {len(attrib)} checkout(s) Fondateurs")
    print("[3] ARRIVEE PAGE FONDATEURS : NON MESURE par la base — PostHog (index.html) pageviews $pageview avec ?offre=…")
    print("[4] OUVERTURE FICHE : NON MESURE par la base (etat React local)")
    print("[5] CLIC ACHETER : NON MESURE par la base — visible seulement s'il aboutit a un checkout (etape 6)")
    # 6. checkout cree
    pend = [p for p in pt_f if p.get("payment_status") == "pending"]
    print(f"\n[6] CHECKOUT STRIPE CREE (payment_transactions, offre Fondateurs, depuis {depuis}) : {len(pt_f)} dont pending={len(pend)}, paid={sum(1 for p in pt_f if p.get('payment_status')=='paid')}")
    # 7. paiement -> subscriptions
    subs = list(db.subscriptions.find({"offer_id": OFFRE_FONDATEURS, "status": {"$ne": "superseded"}}, {"_id": 0, "status": 1, "stripe_subscription_id": 1, "created_at": 1, "remaining_sessions": 1, "doublon_de": 1, "cancel_at_period_end": 1}))
    print(f"[7] PAIEMENT — abonnements Fondateurs (hors superseded) : {len(subs)} | avec stripe_subscription_id={sum(1 for s in subs if s.get('stripe_subscription_id'))} | doublon_de={sum(1 for s in subs if s.get('doublon_de'))} | resiliation programmee={sum(1 for s in subs if s.get('cancel_at_period_end'))}")
    print(f"    STOCK : {len(subs)} vendue(s) / {50 - len(subs)} restante(s) sur 50")
    # 8. reservation essai gratuit
    essais = 0
    for r in db.reservations.find({"createdAt": {"$gte": depuis}}, {"_id": 0, "discountCode": 1, "attribution": 1, "subscriptionId": 1}):
        code = db.discount_codes.find_one({"code": str(r.get("discountCode") or "").upper()}, {"_id": 0, "paid": 1, "price": 1, "origine_paiement": 1, "isTrial": 1, "amount": 1}) if r.get("discountCode") else None
        gratuit = bool(code) and (str(code.get("origine_paiement") or "").lower() == "offert" or code.get("isTrial") is True or float(code.get("price") or code.get("amount") or 0) == 0)
        if gratuit:
            essais += 1
    subs_essai = db.subscriptions.count_documents({"created_at": {"$gte": depuis}, "origine_paiement": "offert"})
    print(f"[8] RESERVATION ESSAI GRATUIT depuis {depuis} : reservations liees a un code gratuit={essais} | essais octroyes (subscriptions origine offert)={subs_essai}")
    print("\n0 ecriture. Fin.")


if __name__ == "__main__":
    main()
