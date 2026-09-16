#!/usr/bin/env python3
"""E1 (16/09/2026) — MONITORING DU PREMIER ABONNÉ FONDATEURS RÉEL. LECTURE SEULE, n'écrit JAMAIS.

Usage :
  python3 tests/monitoring_premier_fondateur.py                 # dernier abonnement Fondateurs en prod
  python3 tests/monitoring_premier_fondateur.py client@mail.ch  # un e-mail précis
  DB_NAME=afroboost_pw_test python3 tests/monitoring_premier_fondateur.py   # base de test
Contrôles : checkout.session.completed reçu, abonnement local créé UNE fois, stripe_subscription_id,
montant 59, offre Fondateurs, remaining 8, total cohérent, stripe_invoices, attribution first/last,
compteur de places N -> N+1, e-mail transactionnel (trace Resend si RESEND_API_KEY), accès espace
(code d'accès + canonique discount_codes), doublon_de absent, erreurs (indicateurs)."""
import os, sys, json, urllib.request
from datetime import datetime, timezone
from pymongo import MongoClient

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env = {}
for l in open(os.path.join(RACINE, ".env.local")):
    l = l.strip()
    if "=" in l and not l.startswith("#"):
        k, v = l.split("=", 1); env[k] = v.strip().strip('"').strip("'")
NOM_BASE = os.environ.get("DB_NAME") or env.get("DB_NAME", "promo-credits-lab")
db = MongoClient(env["MONGO_URL"], serverSelectionTimeoutMS=30000)[NOM_BASE]
FID = "cc73f6ee-163a-433d-b5f0-c00c6392b437"
STOCK = 50
PRIX = 59.0
PACK = 8

def masque(e):
    e = e or ""
    return (e[:2] + "…@" + e.split("@")[-1]) if "@" in e else (e[:4] + "…")

def ligne(ok, libelle, detail=""):
    print(("  OK   " if ok is True else "  !!   " if ok is False else "  ..   ") + libelle + (("  -> " + str(detail)[:140]) if detail else ""))
    return ok

def main():
    email = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    print(f"# Monitoring premier Fondateur — base `{NOM_BASE}` — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} — LECTURE SEULE")
    q = {"offer_id": FID}
    if email:
        q["email"] = email
    abos = list(db.subscriptions.find(q, {"_id": 0}).sort("created_at", -1))
    vendues = db.subscriptions.count_documents({"offer_id": FID, "status": {"$ne": "superseded"}})
    print(f"PLACES VENDUES (règle du code : subscriptions offer_id=Fondateurs, status != superseded) = {vendues} / {STOCK}  -> restantes {max(0, STOCK - vendues)}")
    if not abos:
        print("Aucun abonnement Fondateurs" + (f" pour {masque(email)}" if email else "") + " — rien à contrôler. (0 client réel pour l'instant.)")
        pend = db.payment_transactions.count_documents({"metadata.offer_id": FID, "payment_status": "pending"})
        print(f"  checkouts Fondateurs abandonnés (pending) : {pend} — ne comptent pas comme vendus.")
        return 0
    a = abos[0]
    em = a.get("email") or a.get("user_email") or ""
    print(f"Abonnement contrôlé : {masque(em)} — créé {str(a.get('created_at'))[:19]} — id {str(a.get('id'))[:8]}…")
    doublons = [x for x in abos if (x.get("email") or x.get("user_email")) == em]
    ligne(len(doublons) == 1, "abonnement local créé UNE seule fois pour cette adresse", f"{len(doublons)} document(s)")
    tx = list(db.payment_transactions.find({"metadata.offer_id": FID, "customer_email": em}, {"_id": 0}).sort("created_at", -1))
    payes = [t for t in tx if t.get("payment_status") in ("paid", "completed", "succeeded") or t.get("webhook_received_at")]
    ligne(bool(payes), "checkout.session.completed reçu (payment_transactions payé / webhook_received_at)", f"{len(payes)} payé(s) sur {len(tx)} transaction(s)")
    ligne(bool(a.get("stripe_subscription_id")), "stripe_subscription_id présent", str(a.get("stripe_subscription_id"))[:12] + "…")
    montant = a.get("renewal_price") or a.get("montant_encaisse") or (payes[0].get("amount") if payes else None)
    ligne(montant is not None and abs(float(montant) - PRIX) < 0.01, "montant = 59 CHF", montant)
    ligne(a.get("offer_id") == FID and "ondateur" in str(a.get("offer_name") or a.get("name") or ""), "offre = Fondateurs", a.get("offer_name") or a.get("name"))
    ligne(a.get("remaining_sessions") == PACK, "remaining_sessions = 8", a.get("remaining_sessions"))
    ligne(a.get("total_sessions") == PACK * max(1, len(a.get("stripe_invoices") or []) or 1) or a.get("total_sessions") == PACK, "total_sessions cohérent (8 par facture payée)", f"total {a.get('total_sessions')} / factures {len(a.get('stripe_invoices') or [])}")
    ligne(isinstance(a.get("stripe_invoices"), list), "stripe_invoices enregistrée (liste ; vide tant que la 2e facture n'est pas arrivée)", a.get("stripe_invoices"))
    att = a.get("attribution") or {}
    ligne(bool(att.get("first")) and bool(att.get("last")), "attribution first/last conservée", f"first={((att.get('first') or {}).get('source'))} last={((att.get('last') or {}).get('source'))}" if att else "absente (visite directe sans UTM = normal)")
    ligne(vendues >= 1, "compteur Fondateurs : N -> N+1 (au moins 1 vendue)", vendues)
    ligne(a.get("billing_mode") == "mensuel_auto", "billing_mode = mensuel_auto", a.get("billing_mode"))
    ligne(a.get("status") == "active" and not a.get("cancel_at_period_end"), "état = actif, aucune résiliation programmée", f"{a.get('status')} / cancel_at_period_end={a.get('cancel_at_period_end')}")
    ligne(a.get("expires_at") and str(a.get("expires_at")) > datetime.now(timezone.utc).isoformat(), "expires_at dans le futur (fin de période payée)", str(a.get("expires_at"))[:19])
    code = a.get("code") or a.get("access_code")
    dc = db.discount_codes.find_one({"code": code}, {"_id": 0}) if code else None
    ligne(bool(code) and bool(dc), "accès espace : code d'accès émis + canonique discount_codes", f"code …{str(code)[-4:]} maxUses={dc.get('maxUses') if dc else None} used={dc.get('used') if dc else None}")
    ligne(not a.get("doublon_de") and not any(t.get("doublon_de") for t in tx), "aucun doublon_de", "")
    if env.get("RESEND_API_KEY") and NOM_BASE != "afroboost_pw_test":
        try:
            req = urllib.request.Request("https://api.resend.com/emails?limit=50", headers={"Authorization": "Bearer " + env["RESEND_API_KEY"]})
            data = json.load(urllib.request.urlopen(req, timeout=20)).get("data", [])
            mails = [m for m in data if em in [x.lower() for x in (m.get("to") or [])]]
            ligne(bool(mails), "e-mail transactionnel envoyé (Resend, lecture seule)", "; ".join(f"{m.get('created_at','')[:16]} {m.get('subject','')[:40]} [{m.get('last_event')}]" for m in mails[:3]) or "aucun trouvé dans les 50 derniers")
        except Exception as e:  # noqa: BLE001
            ligne(None, "e-mail transactionnel : Resend illisible", type(e).__name__)
    else:
        ligne(None, "e-mail transactionnel : non vérifié (pas de RESEND_API_KEY ou base de test)")
    print("Erreurs serveur : à lire dans Coolify -> Logs (filtrer [HIVER], [STRIPE], [WEBHOOK]) — non accessible depuis ce script.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
