# -*- coding: utf-8 -*-
"""PILE LOCALE DE TEST — la VRAIE application Afroboost (code de l'arbre de travail),
sur une base de test SÉPARÉE (`afroboost_pw_test`, jamais la prod), avec Stripe, Resend,
WhatsApp et push REMPLACÉS par des faux : aucun paiement, aucun e-mail, aucun message.

  - Stripe : `checkout.Session.create` renvoie une page locale « Paiement TEST » ;
    le bouton « Payer » fabrique l'événement `checkout.session.completed` et le
    poste au webhook réel de l'application (sans secret = accepté), puis redirige
    vers `success_url` — exactement le trajet de production, sans Stripe.
  - Resend : chaque e-mail est enregistré dans emails.jsonl (jamais envoyé).
  - Frontend : le build CRA (`frontend/build`) servi par l'application elle-même.

Lancement : python3 pw_stack.py  (port 8001)
"""
import os, sys, json, uuid, time, urllib.parse, urllib.request
RACINE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ICI = os.environ.get("PW_SCRATCH", os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.join(ICI, "pw_lib"))   # stripe==14.1.0, la version ÉPINGLÉE en prod (api/requirements.txt)

# ── Environnement hermétique ───────────────────────────────────────────────
env = {}
for l in open(os.path.join(RACINE, ".env.local")):
    l = l.strip()
    if "=" in l and not l.startswith("#"):
        k, v = l.split("=", 1); env[k] = v.strip().strip('"').strip("'")
os.environ["MONGO_URL"] = env["MONGO_URL"]
os.environ["DB_NAME"] = "afroboost_pw_test"
os.environ["STRIPE_SECRET_KEY"] = "sk_test_faux_local_jamais_reel"
os.environ["RESEND_API_KEY"] = "re_faux_local_jamais_reel"
os.environ["JWT_SECRET"] = "pw-local-secret"
os.environ["FRONTEND_URL"] = "http://127.0.0.1:8001"
os.environ["REACT_APP_FRONTEND_URL"] = "http://127.0.0.1:8001"
for k in ("META_WHATSAPP_TOKEN", "META_WHATSAPP_PHONE_ID", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER",
          "VAPID_PRIVATE_KEY", "VAPID_PUBLIC_KEY", "OPENAI_API_KEY", "STRIPE_WEBHOOK_SECRET_CHECKOUT", "STRIPE_WEBHOOK_SECRET",
          "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET", "PAWAPAY_API_TOKEN", "CINETPAY_API_KEY", "META_APP_SECRET"):
    os.environ.pop(k, None)

# ── Faux Stripe (AVANT l'import de l'application) ──────────────────────────
import stripe
SESSIONS = {}


class _Obj(dict):
    def __getattr__(self, k):
        try: return self[k]
        except KeyError: raise AttributeError(k)


def _faux_session_create(api_key=None, **p):
    sid = "cs_test_" + uuid.uuid4().hex[:16]
    SESSIONS[sid] = p
    return _Obj(id=sid, url="http://127.0.0.1:8001/faux-stripe?cs=" + sid, payment_status="unpaid", mode=p.get("mode"))


MODIFS = []   # V528 : journal des `Subscription.modify` (résiliation / réactivation), lu par /faux-stripe/modifs


class _FauxRessource:
    @staticmethod
    def create(*a, **k): return _Obj(id="faux_" + uuid.uuid4().hex[:10], **{kk: vv for kk, vv in k.items() if kk != "api_key"})
    @staticmethod
    def retrieve(id_, *a, **k): return _Obj(id=id_, status="active")
    @staticmethod
    def modify(id_, *a, **k):
        MODIFS.append({"id": id_, **{kk: vv for kk, vv in k.items() if kk != "api_key"}, "t": time.time()})
        return _Obj(id=id_, **{kk: vv for kk, vv in k.items() if kk != "api_key"})
    @staticmethod
    def list(*a, **k): return _Obj(data=[])


stripe.checkout.Session.create = _faux_session_create
def _faux_session_retrieve(id_, *a, **k):
    # V528 : comme le vrai Stripe, la session RÉCUPÉRÉE porte amount_total (absent des
    # params de create). Sans lui, renewal_price tombait à 0 dans le webhook (harnais only).
    _p = SESSIONS.get(id_) or {}
    _li = (_p.get("line_items") or [{}])[0]
    _amount = int(_li.get("price_data", {}).get("unit_amount", 0)) * int(_li.get("quantity", 1) or 1)
    _base = {kk: vv for kk, vv in _p.items() if kk not in ("amount_total", "customer", "payment_intent")}
    return _Obj(id=id_, payment_status="paid", amount_total=_amount, customer="cus_faux_" + id_[-6:],
                payment_intent=None, **_base)


stripe.checkout.Session.retrieve = _faux_session_retrieve
for nom in ("Subscription", "Customer", "PaymentIntent", "Invoice", "Product", "Price", "Refund", "Account", "AccountLink"):
    setattr(stripe, nom, _FauxRessource)

# ── Faux Resend ─────────────────────────────────────────────────────────────
import resend
EMAILS = os.path.join(ICI, "pw_emails.jsonl")


def _faux_send(params):
    with open(EMAILS, "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": time.time(), "to": params.get("to"), "subject": params.get("subject"), "html": params.get("html", "")[:20000]}, ensure_ascii=False) + "\n")
    return {"id": "em_faux_" + uuid.uuid4().hex[:8]}


resend.Emails.send = _faux_send

# ── L'application RÉELLE ────────────────────────────────────────────────────
import api.server as S
S.resend.Emails.send = _faux_send
S.RESEND_AVAILABLE = True
S.RESEND_API_KEY = os.environ["RESEND_API_KEY"]
S._STATIC_DIR = os.path.join(ICI, "pw_build")
for mod in ("stripe_routes", "checkout_routes", "hiver", "boost_routes"):
    try:
        m = __import__("api.routes." + mod, fromlist=["x"])
        if hasattr(m, "stripe"):
            m.stripe.checkout.Session.create = _faux_session_create
    except Exception:
        pass

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse


@S.fastapi_app.get("/faux-stripe")
async def faux_stripe(cs: str = ""):
    p = SESSIONS.get(cs)
    if not p:
        return HTMLResponse("<h1>Session inconnue</h1>", status_code=404)
    li = (p.get("line_items") or [{}])[0].get("price_data", {})
    montant = li.get("unit_amount", 0) / 100
    nom = li.get("product_data", {}).get("name", "")
    rec = li.get("recurring", {})
    return HTMLResponse(f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Stripe — TEST local</title></head>
<body style="font-family:sans-serif;padding:24px;max-width:480px;margin:auto">
<h1 data-testid="faux-stripe">Paiement TEST (aucun débit)</h1>
<p data-testid="faux-produit">{nom}</p>
<p data-testid="faux-montant">{montant:.2f} CHF {('/ ' + rec.get('interval', '')) if rec else '(unique)'} — mode {p.get('mode')}</p>
<p data-testid="faux-methodes">{', '.join(p.get('payment_method_types') or [])}</p>
<p data-testid="faux-email">{p.get('customer_email', '')}</p>
<form method="post" action="/faux-stripe/payer"><input type="hidden" name="cs" value="{cs}">
<label>E-mail (comme sur la page Stripe) <input data-testid="faux-email-input" name="email" value="{p.get('customer_email') or ('pw-' + cs[-8:] + '@example.com')}" style="width:100%;padding:8px"></label>
<label>Nom <input data-testid="faux-nom-input" name="nom" value="Test Fondateur" style="width:100%;padding:8px"></label>
<button data-testid="faux-payer" style="padding:14px 24px;font-size:16px;margin-top:12px">Payer (TEST)</button></form>
<p><a data-testid="faux-annuler" href="{p.get('cancel_url', '/')}">Annuler</a></p>
</body></html>""")


@S.fastapi_app.post("/faux-stripe/payer")
async def faux_stripe_payer(request: Request):
    form = await request.form()
    cs = form.get("cs", "")
    p = SESSIONS.get(cs)
    if not p:
        return HTMLResponse("<h1>Session inconnue</h1>", status_code=404)
    li = (p.get("line_items") or [{}])[0].get("price_data", {})
    total = li.get("unit_amount", 0) * ((p.get("line_items") or [{}])[0].get("quantity", 1) or 1)
    email = (form.get("email") or p.get("customer_email") or SESSIONS[cs].get("_email") or ("pw-" + cs[-8:] + "@example.com")).strip().lower()
    SESSIONS[cs]["_email"] = email
    nom = (form.get("nom") or SESSIONS[cs].get("_nom") or "Test Fondateur").strip()
    SESSIONS[cs]["_nom"] = nom
    objet = {"id": cs, "object": "checkout.session", "mode": p.get("mode"), "payment_status": "paid", "status": "complete",
             "amount_total": total, "currency": li.get("currency", "chf"), "metadata": p.get("metadata") or {},
             "customer_email": email, "customer_details": {"email": email, "name": nom},
             "customer": "cus_faux_" + cs[-6:], "subscription": ("sub_faux_" + cs[-6:]) if p.get("mode") == "subscription" else None,
             "payment_intent": ("pi_faux_" + cs[-6:]) if p.get("mode") == "payment" else None,
             "success_url": p.get("success_url")}
    evt = {"id": "evt_faux_" + uuid.uuid4().hex[:10], "object": "event", "type": "checkout.session.completed", "data": {"object": objet}}
    corps = json.dumps(evt).encode()
    # Le VRAI webhook de l'application (même route qu'en prod ; sans secret local, il accepte le corps).
    import httpx
    try:
        async with httpx.AsyncClient(timeout=90) as cl:   # asynchrone : ne bloque pas la boucle du serveur
            r = await cl.post("http://127.0.0.1:8001/api/webhook/stripe", content=corps, headers={"Content-Type": "application/json"})
            SESSIONS[cs]["_webhook"] = r.status_code
            SESSIONS[cs]["_webhook_corps"] = r.text[:300]
    except Exception as e:
        SESSIONS[cs]["_webhook"] = str(e)
    SESSIONS[cs]["_paid_at"] = time.time()
    url = (p.get("success_url") or "/").replace("{CHECKOUT_SESSION_ID}", cs)
    return RedirectResponse(url, status_code=303)


@S.fastapi_app.post("/faux-stripe/rejouer")
async def faux_stripe_rejouer(request: Request):
    """Rejoue le webhook d'une session déjà payée (test d'idempotence)."""
    form = await request.form()
    cs = form.get("cs", "")
    if cs not in SESSIONS:
        return HTMLResponse("inconnue", status_code=404)
    return await faux_stripe_payer(request)


@S.fastapi_app.get("/faux-stripe/modifs")
async def faux_stripe_modifs():
    """V528 : les appels Stripe `Subscription.modify` reçus (cancel_at_period_end, cancel_at…)."""
    return {"modifs": MODIFS}


@S.fastapi_app.get("/faux-stripe/abonnement")
async def faux_stripe_abonnement(email: str = ""):
    """V528 : lecture BASE DE TEST d'un abonnement par e-mail (code d'accès + drapeaux Stripe) — pile locale seulement."""
    docs = await S.db.subscriptions.find({"email": email.strip().lower()}, {"_id": 0}).sort("created_at", -1).to_list(10)
    return {"n": len(docs), "abonnements": [{k: d.get(k) for k in ("id", "code", "access_code", "status", "offer_id", "offer_name", "stripe_subscription_id",
                                                                     "cancel_at_period_end", "resiliation_demandee_le", "expires_at", "remaining_sessions",
                                                                     "renewal_sessions", "renewal_price", "billing_mode")} for d in docs]}


@S.fastapi_app.get("/faux-stripe/etat")
async def faux_stripe_etat():
    return {k: {"mode": v.get("mode"), "webhook": v.get("_webhook"), "webhook_corps": v.get("_webhook_corps"), "paid": bool(v.get("_paid_at")), "email": v.get("_email") or v.get("customer_email"),
                "metadata": v.get("metadata")} for k, v in SESSIONS.items()}


# Les routes du faux Stripe passent AVANT le catch-all SPA (déclaré à l'import).
_r = S.fastapi_app.router.routes
_faux = [x for x in _r if getattr(x, "path", "").startswith("/faux-stripe")]
for x in _faux:
    _r.remove(x)
for i, x in enumerate(_faux):
    _r.insert(i, x)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(S.fastapi_app, host="127.0.0.1", port=8001, log_level="warning")
