# -*- coding: utf-8 -*-
"""HIVER — abonnement mensuel automatique, saison 8 mois (1× / 2×), offre limitée, cycles Stripe.

  * modes : unique = système actuel (2 mois, carte + TWINT) ; mensuel_auto = Stripe
    subscription mensuel, carte seule, 1 mois de droits ; saison_2x = tous les 4 mois,
    pack × 4 par échéance, cancel_at début + 8 mois ; saison 1× = duree_mois 8 ;
  * Pulse été : AUCUN changement (2 mois, pack 10, unique) ;
  * offre limitée : places = stock − ventes − checkouts ouverts ; date limite réelle ;
    49e/50e autorisées, 51e refusée ; deadline avant stock ; stock avant deadline ;
  * cycles : facture de renouvellement créditée UNE fois (retry = 0 crédit), première
    facture ignorée, échec noté sans retrait, résiliation = accès jusqu'à expires_at ;
  * intégration server.py (structure) : Session.create en mode subscription seulement
    pour les offres récurrentes, événements invoice.paid / payment_failed /
    subscription.deleted branchés, V195 exclut les abonnements Stripe.

    python3 tests/test_hiver_abonnements.py
"""
import asyncio, copy, os, sys
from datetime import datetime, timedelta, timezone
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from api.routes import hiver as H

R = []
def v(nom, cond, detail=""): R.append((nom, bool(cond), detail))
def run(c): return asyncio.get_event_loop().run_until_complete(c)

# ═══ 1. règles pures ═══
v("modes : valeur inconnue -> unique", H.billing_mode_valide("x") == "unique" and H.billing_mode_valide("MENSUEL_AUTO") == "mensuel_auto")
v("durée : mensuel 1 mois, saison_2x 4 mois, unique+duree_mois 8 -> 8, unique sans durée -> 2 (règle été)",
  [H.duree_droits_mois(o) for o in ({"billing_mode": "mensuel_auto"}, {"billing_mode": "saison_2x"}, {"duree_mois": 8}, {})] == [1, 4, 8, 2])
v("Pulse X10 été INCHANGÉ : unique, 2 mois, 10 séances", H.duree_droits_mois({"pack_sessions": 10, "price": 250}) == 2 and H.seances_par_paiement({"pack_sessions": 10}) == 10)
exp_iso, exp_jour = H.expiration_droits(datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc), 1)
v("expiration : +1 mois calendaire, fin de journée (31 oct -> 30 nov)", exp_jour == "2026-11-30" and exp_iso.startswith("2026-11-30T23:59:59"))
v("expiration : 8 mois (15 oct -> 15 juin)", H.expiration_droits(datetime(2026, 10, 15, tzinfo=timezone.utc), 8)[1] == "2027-06-15")
v("séances par paiement : mensuel = pack ; saison_2x = pack × 4 ; pack 0 = 0 (adhésion seule)",
  H.seances_par_paiement({"billing_mode": "mensuel_auto", "pack_sessions": 8}) == 8 and H.seances_par_paiement({"billing_mode": "saison_2x", "pack_sessions": 8}) == 32
  and H.seances_par_paiement({"pack_sessions": 0}) == 0)
v("cancel_at saison_2x = début + 8 mois (epoch)", H.cancel_at_saison(datetime(2026, 10, 1, tzinfo=timezone.utc)) == int(datetime(2027, 6, 1, tzinfo=timezone.utc).timestamp()))

# checkout : paramètres Stripe
pu = H.parametres_checkout({"billing_mode": "unique"}, "Pulse", 25000, "s", "c", "a@b.ch", {"offer_id": "p"})
v("unique : mode=payment, carte + TWINT, montant 25000, métadonnées + billing_mode", pu["mode"] == "payment" and pu["payment_method_types"] == ["card", "twint"]
  and pu["line_items"][0]["price_data"]["unit_amount"] == 25000 and "recurring" not in pu["line_items"][0]["price_data"] and pu["metadata"]["billing_mode"] == "unique")
pm = H.parametres_checkout({"billing_mode": "mensuel_auto"}, "Mensuel Liberté", 8900, "s", "c", "a@b.ch", {"offer_id": "m"})
v("mensuel_auto : mode=subscription, carte SEULE (pas de TWINT en récurrent), recurring month×1, métadonnées sur l'abonnement",
  pm["mode"] == "subscription" and pm["payment_method_types"] == ["card"] and pm["line_items"][0]["price_data"]["recurring"] == {"interval": "month", "interval_count": 1}
  and pm["subscription_data"]["metadata"]["offer_id"] == "m" and pm["subscription_data"]["metadata"]["billing_mode"] == "mensuel_auto")
ps = H.parametres_checkout({"billing_mode": "saison_2x"}, "Saison 2×", 29900, "s", "c", "a@b.ch", {})
v("saison_2x : recurring month×4, 29900 par échéance", ps["mode"] == "subscription" and ps["line_items"][0]["price_data"]["recurring"] == {"interval": "month", "interval_count": 4})

# offre limitée
T = datetime(2026, 9, 20, 12, 0)
fond = {"stock": 50, "countdown_enabled": True, "countdown_date": "2026-09-30", "countdown_time": "23:59"}
v("date limite réelle lue sur l'offre (Zurich) : 30/09/2026 23:59", H.date_limite(fond) == datetime(2026, 9, 30, 23, 59))
v("avant la date, 49 ventes -> 1 place : réservable", H.offre_reservable(dict(fond, places_restantes=1), 0, T) == (True, ""))
v("50 ventes -> 0 place : refusée (complète)", H.offre_reservable(dict(fond, places_restantes=0), 0, T) == (False, H.RAISON_COMPLETE))
v("1 place mais un checkout ouvert (< 30 min) : refusée — concurrence sur la dernière place", H.offre_reservable(dict(fond, places_restantes=1), 1, T)[0] is False)
v("deadline dépassée avec des places : refusée (expirée) — la deadline arrive avant le stock", H.offre_reservable(dict(fond, places_restantes=30), 0, datetime(2026, 10, 1, 0, 0)) == (False, H.RAISON_EXPIREE))
v("stock épuisé avant la deadline : le motif est « complète »", H.motif_fermeture(dict(fond, places_restantes=0), T) == H.RAISON_COMPLETE)
v("23:59 pile : encore ouverte ; 00:00 le lendemain : fermée", not H.offre_expiree(fond, datetime(2026, 9, 30, 23, 59)) and H.offre_expiree(fond, datetime(2026, 10, 1, 0, 0)))
v("sans compte à rebours ni stock : jamais fermée", H.motif_fermeture({"price": 30}, T) == "")
v("offres_ouvertes : retire complètes et expirées, garde les autres",
  [o["n"] for o in H.offres_ouvertes([{"n": 1, "places_restantes": 0}, {"n": 2}, dict(fond, n=3, places_restantes=5), {"n": 4, "countdown_enabled": True, "countdown_date": "2026-01-01"}], T)] == [2, 3])

# ═══ 2. cycles Stripe (faux Mongo aux sémantiques atomiques) ═══
class _Res:
    def __init__(self, matched, modified): self.matched_count, self.modified_count = matched, modified

def _corr(d, f):
    for k, c in f.items():
        if isinstance(c, dict) and "$ne" in c:
            val = d.get(k)
            if (c["$ne"] in val) if isinstance(val, list) else (val == c["$ne"]): return False
        elif isinstance(c, dict) and "$in" in c:
            if d.get(k) not in c["$in"]: return False
        elif d.get(k) != c: return False
    return True

class Coll:
    def __init__(self, docs): self.docs = docs
    async def find_one(self, f, p=None):
        for d in self.docs:
            if _corr(d, f): return dict(d)
        return None
    async def update_one(self, f, u):
        for d in self.docs:
            if _corr(d, f):
                for k, val in (u.get("$inc") or {}).items(): d[k] = d.get(k, 0) + val
                for k, val in (u.get("$set") or {}).items(): d[k] = val
                for k, val in (u.get("$addToSet") or {}).items():
                    d.setdefault(k, []); d[k].append(val) if val not in d[k] else None
                for k, val in (u.get("$push") or {}).items(): d.setdefault(k, []).append(val)
                return _Res(1, 1)
        return _Res(0, 0)

class Base:
    def __init__(self):
        self.subscriptions = Coll([{"id": "s1", "code": "AFR-AAAAAA", "stripe_subscription_id": "sub_1", "billing_mode": "mensuel_auto",
                                    "renewal_sessions": 8, "remaining_sessions": 2, "total_sessions": 8, "status": "active",
                                    "expires_at": "2026-10-31T23:59:59+00:00", "stripe_invoices": ["in_first"], "renewal_warnings_sent": []},
                                   {"id": "s2", "code": "AFR-BBBBBB", "stripe_subscription_id": "sub_2", "billing_mode": "saison_2x",
                                    "renewal_sessions": 32, "remaining_sessions": 10, "total_sessions": 32, "status": "active",
                                    "expires_at": "2027-01-31T23:59:59+00:00", "stripe_invoices": []}])
        self.discount_codes = Coll([{"code": "AFR-AAAAAA", "maxUses": 8, "used": 6, "active": True, "expiresAt": "2026-10-31", "stripe_invoices": []},
                                    {"code": "AFR-BBBBBB", "maxUses": 32, "used": 22, "active": True, "expiresAt": "2027-01-31"}])

db = Base()
_fin_nov = int(datetime(2026, 11, 30, 12, 0, tzinfo=timezone.utc).timestamp())
inv = {"id": "in_2", "subscription": "sub_1", "billing_reason": "subscription_cycle", "status": "paid", "lines": {"data": [{"period": {"start": 0, "end": _fin_nov}}]}}
r1 = run(H.traiter_facture_payee(db, inv))
s1 = db.subscriptions.docs[0]; c1 = db.discount_codes.docs[0]
v("renouvellement mensuel : +8 séances (2 -> 10), total 16, expires_at = fin de période Stripe (30/11), statut actif, last_renewal_date posé",
  r1["credite"] and s1["remaining_sessions"] == 10 and s1["total_sessions"] == 16 and s1["expires_at"].startswith("2026-11-30T23:59:59") and s1["status"] == "active" and s1.get("last_renewal_date"), (r1, dict(s1)))
v("le code d'accès suit : maxUses 8 -> 16, expiresAt 2026-11-30, actif", c1["maxUses"] == 16 and c1["expiresAt"] == "2026-11-30" and c1["active"] is True, dict(c1))
v("webhook livré en retard (sans période) : repli maintenant + 1 mois", H.fin_periode_facture({}, 1)[1] == H.expiration_droits(datetime.now(timezone.utc), 1)[1])
v("marqueur renewed_AAAAMMJJ posé (renouvellement CONFIRMÉ pour Analytics)", any(str(x).startswith("renewed_") for x in s1["renewal_warnings_sent"]))
r2 = run(H.traiter_facture_payee(db, inv))
v("RETRY du même webhook : 0 crédit (facture déjà créditée), séances et code inchangés",
  not r2["credite"] and r2["motif"] == "facture_deja_creditee" and s1["remaining_sessions"] == 10 and c1["maxUses"] == 16)
r3 = run(H.traiter_facture_payee(db, {"id": "in_first", "subscription": "sub_1", "billing_reason": "subscription_create"}))
v("première facture (subscription_create) : ignorée — déjà créditée par checkout.session.completed", not r3["credite"] and r3["motif"] == "premiere_facture_deja_creditee")
r4 = run(H.traiter_facture_payee(db, {"id": "in_x", "subscription": "sub_inconnu", "billing_reason": "subscription_cycle"}))
v("abonnement inconnu : rien", not r4["credite"] and r4["motif"] == "abonnement_inconnu")
_fin_mai = int(datetime(2027, 5, 31, 12, 0, tzinfo=timezone.utc).timestamp())
r5 = run(H.traiter_facture_payee(db, {"id": "in_s2", "subscription": "sub_2", "billing_reason": "subscription_cycle", "lines": {"data": [{"period": {"end": _fin_mai}}]}}))
s2 = db.subscriptions.docs[1]
v("deuxième échéance saison_2x : +32 séances (pack 8 × 4 mois), droits jusqu'à la fin de la période facturée (31/05)", r5["credite"] and r5["seances"] == 32 and s2["remaining_sessions"] == 42 and s2["expires_at"].startswith("2027-05-31"), (r5, dict(s2)))
rf = run(H.traiter_facture_echouee(db, {"id": "in_f", "subscription": "sub_1"}))
v("échec de paiement : noté (paiement_echoue_le, payment_failed), AUCUN retrait de droits", rf["note"] and s1.get("paiement_echoue_le") and s1["remaining_sessions"] == 10 and s1["status"] == "active")
exp_avant = s1["expires_at"]
rd = run(H.traiter_abonnement_termine(db, {"id": "sub_1", "status": "canceled"}))
v("annulation : plus de renouvellement (auto_renew False, statut Stripe canceled), accès jusqu'à expires_at inchangé",
  rd["termine"] and s1["auto_renew"] is False and s1["stripe_subscription_status"] == "canceled" and s1["expires_at"] == exp_avant)
rp = run(H.traiter_facture_payee(db, {"id": "in_3", "subscription": "sub_1", "billing_reason": "subscription_cycle"}))
v("un cycle payé après un échec efface la note d'échec (paiement_echoue_le None)", rp["credite"] and s1["paiement_echoue_le"] is None)

# garde asynchrone (checkout vitrine) : stock − ventes − checkouts ouverts
class _Agg:
    def __init__(self, n): self.n = n
    def __aiter__(self): self.i = 0; return self
    async def __anext__(self):
        if self.i or self.n is None: raise StopAsyncIteration
        self.i = 1; return {"n": self.n}
class BaseGarde:
    def __init__(self, stock, ventes, ouverts, countdown=None):
        self.o = dict({"id": "f", "stock": stock, "isProduct": False}, **(countdown or {})); self.ventes = ventes; self.ouverts = ouverts
        self.offers = self; self.subscriptions = self; self.payment_transactions = self
    def __getitem__(self, k): return self
    async def find_one(self, f, p=None): return dict(self.o) if f.get("id") == "f" else None
    def aggregate(self, pipeline): return _Agg(self.ventes)
    async def count_documents(self, f): return self.ouverts
v("garde : 49 ventes / 50 -> autorisée", run(H.garde_offre_limitee(BaseGarde(50, 49, 0), "f")) == (True, ""))
v("garde : 50 ventes -> 51e refusée", run(H.garde_offre_limitee(BaseGarde(50, 50, 0), "f")) == (False, H.RAISON_COMPLETE))
v("garde : 49 ventes + 1 checkout ouvert -> refusée (dernière place réservée 30 min)", run(H.garde_offre_limitee(BaseGarde(50, 49, 1), "f"))[0] is False)
v("garde : deadline passée -> refusée même avec des places", run(H.garde_offre_limitee(BaseGarde(50, 0, 0, {"countdown_enabled": True, "countdown_date": "2020-01-01"}), "f")) == (False, H.RAISON_EXPIREE))
v("garde : stock -1 (illimité) -> toujours ouverte", run(H.garde_offre_limitee(BaseGarde(-1, 999, 5), "f")) == (True, ""))
v("garde : sans identifiant -> ouverte", run(H.garde_offre_limitee(BaseGarde(50, 50, 0), "")) == (True, ""))

# ═══ 3. intégration server.py / checkout_routes (structure) ═══
S = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
C = open(os.path.join(RACINE, "api", "routes", "checkout_routes.py"), encoding="utf-8").read()
v("checkout principal : garde offre limitée (409) AVANT Stripe, sur l'offre lue en base", "_hiver.offre_reservable(_hiver_offre, _en_cours)" in S and "raise HTTPException(status_code=409, detail=_motif)" in S)
v("checkout principal : Session.create en mode récurrent SEULEMENT si billing_mode != unique ; l'appel historique reste intact",
  "if _hiver_mode != _hiver.BILLING_UNIQUE:" in S and "session = stripe.checkout.Session.create(api_key=active_stripe_key, **_p)" in S and "mode='payment'," in S)
v("checkout principal : métadonnées billing_mode + duree_mois transmises au webhook", 'metadata["billing_mode"] = _hiver_mode' in S and 'metadata["duree_mois"]' in S)
v("checkout vitrine (checkout_routes) : même garde, fail-open", "garde_offre_limitee as _hiver_garde" in C and "status_code=409, detail=_motif" in C)
v("webhook : pack 0 accepté, saison_2x = pack × 4, expiration par durée (code ET forfait)",
  '_pack == "0" and metadata.get("offer_id")' in S and '"expiresAt": _hiver_exp_jour' in S and '"expires_at": _hiver_exp_iso' in S)
v("webhook : abonnement Stripe -> auto_renew False (jamais V195), stripe_subscription_id, stripe_invoices []",
  '"stripe_subscription_id": ((str(session.get("subscription")' in S and 'if _hiver_mode_wh == _hiver.BILLING_UNIQUE else False' in S and '"stripe_invoices": []' in S)
v("webhook : saison_2x -> cancel_at début + 8 mois posé sur l'abonnement Stripe", "stripe.Subscription.modify(subscription_data[\"stripe_subscription_id\"]" in S and "cancel_at=_hiver.cancel_at_saison" in S)
v("webhook : invoice.paid / payment_succeeded / payment_failed / customer.subscription.deleted branchés",
  "event.type in ('invoice.paid', 'invoice.payment_succeeded')" in S and "event.type == 'invoice.payment_failed'" in S and "event.type == 'customer.subscription.deleted'" in S)
# FONDATEURS / PARCOURS (15/09/2026) : l'URL déclarée chez Stripe est /api/checkout/webhook/stripe
# (checkout_routes) — elle DOIT relayer les événements du cycle d'abonnement vers `stripe_webhook`,
# sinon le mois 2+ n'est jamais crédité (constaté par 2 audits indépendants).
v("relais (checkout_routes) : invoice.paid / payment_succeeded / payment_failed / subscription.deleted transmis au rappel HIVER",
  '"invoice.upcoming", "invoice.paid", "invoice.payment_succeeded"' in C and '"invoice.payment_failed", "customer.subscription.deleted"' in C
  and "request.state.afroboost_event_verifie = event_data" in C)
v("e-mail d'accès : un abonnement mensuel dit « par mois, renouvelées automatiquement » et comment l'arrêter",
  "_mention_abo" in S and "renouvel&eacute;es automatiquement" in S and 'mention: str = ""' in S)
v("V195 : les deux sélections excluent les abonnements Stripe (pas de double débit)", S.count('"stripe_subscription_id": {"$in": [None, ""]}') == 2)
v("modèles : billing_mode / duree_mois sur Offer et OfferCreate ; PUT conserve les valeurs stockées", 'billing_mode: Optional[str] = "unique"' in S and "offer.billing_mode if offer.billing_mode is not None else _offre_avant.get(\"billing_mode\")" in S)
v("public : billing_mode, duree_mois, countdown_* exposés (aucune donnée personnelle)", '"billing_mode", "duree_mois", "countdown_enabled", "countdown_date", "countdown_time", "countdown_text",' in S)
v("GET /offers public et landing : offres expirées retirées (offres_ouvertes)", S.count("_hiver.offres_ouvertes(") == 2)

ok = sum(1 for _, c, _ in R if c)
for nom, cond, detail in R:
    print("  %s  %s%s" % ("OK  " if cond else "ECHEC", nom, ("  <- " + str(detail)) if (detail and not cond) else ""))
print("\n%d/%d" % (ok, len(R)))
sys.exit(0 if ok == len(R) else 1)
