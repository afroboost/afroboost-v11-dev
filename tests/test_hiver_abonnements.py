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
# V527 — QUOTA MENSUEL : les 2 séances non utilisées du mois 1 EXPIRENT ; remaining = pack (8), PAS 10.
v("D/F. renouvellement mensuel : remaining REMIS à 8 (2 -> 8, pas 10), total historique 16, expires_at = fin de période Stripe (30/11), statut actif, last_renewal_date posé",
  r1["credite"] and s1["remaining_sessions"] == 8 and s1["total_sessions"] == 16 and s1["expires_at"].startswith("2026-11-30T23:59:59") and s1["status"] == "active" and s1.get("last_renewal_date"), (r1, dict(s1)))
v("D/F. le code d'accès (canonique LOT A) suit : maxUses = used + pack = 6 + 8 = 14 (restant 8, pas 10), used intact, expiresAt 2026-11-30, actif",
  c1["maxUses"] == 14 and c1["used"] == 6 and c1["expiresAt"] == "2026-11-30" and c1["active"] is True, dict(c1))
v("webhook livré en retard (sans période) : repli maintenant + 1 mois", H.fin_periode_facture({}, 1)[1] == H.expiration_droits(datetime.now(timezone.utc), 1)[1])
v("marqueur renewed_AAAAMMJJ posé (renouvellement CONFIRMÉ pour Analytics)", any(str(x).startswith("renewed_") for x in s1["renewal_warnings_sent"]))
r2 = run(H.traiter_facture_payee(db, inv))
v("RETRY du même webhook : 0 crédit (facture déjà créditée), séances et code inchangés",
  not r2["credite"] and r2["motif"] == "facture_deja_creditee" and s1["remaining_sessions"] == 8 and c1["maxUses"] == 14)
r3 = run(H.traiter_facture_payee(db, {"id": "in_first", "subscription": "sub_1", "billing_reason": "subscription_create"}))
v("première facture (subscription_create) : ignorée — déjà créditée par checkout.session.completed", not r3["credite"] and r3["motif"] == "premiere_facture_deja_creditee")
r4 = run(H.traiter_facture_payee(db, {"id": "in_x", "subscription": "sub_inconnu", "billing_reason": "subscription_cycle"}))
v("abonnement inconnu : rien", not r4["credite"] and r4["motif"] == "abonnement_inconnu")
_fin_mai = int(datetime(2027, 5, 31, 12, 0, tzinfo=timezone.utc).timestamp())
r5 = run(H.traiter_facture_payee(db, {"id": "in_s2", "subscription": "sub_2", "billing_reason": "subscription_cycle", "lines": {"data": [{"period": {"end": _fin_mai}}]}}))
s2 = db.subscriptions.docs[1]
v("G. SAISON INCHANGÉE — deuxième échéance saison_2x : +32 séances ADDITIVES (10 -> 42, pack 8 × 4 mois), code maxUses 32 -> 64, droits jusqu'au 31/05",
  r5["credite"] and r5["seances"] == 32 and s2["remaining_sessions"] == 42 and s2["total_sessions"] == 64 and db.discount_codes.docs[1]["maxUses"] == 64 and s2["expires_at"].startswith("2027-05-31"), (r5, dict(s2)))
rf = run(H.traiter_facture_echouee(db, {"id": "in_f", "subscription": "sub_1"}))
v("échec de paiement : noté (paiement_echoue_le, payment_failed), AUCUN retrait de droits", rf["note"] and s1.get("paiement_echoue_le") and s1["remaining_sessions"] == 8 and s1["status"] == "active")
exp_avant = s1["expires_at"]
rd = run(H.traiter_abonnement_termine(db, {"id": "sub_1", "status": "canceled"}))
v("annulation : plus de renouvellement (auto_renew False, statut Stripe canceled), accès jusqu'à expires_at inchangé",
  rd["termine"] and s1["auto_renew"] is False and s1["stripe_subscription_status"] == "canceled" and s1["expires_at"] == exp_avant)
rp = run(H.traiter_facture_payee(db, {"id": "in_3", "subscription": "sub_1", "billing_reason": "subscription_cycle"}))
v("un cycle payé après un échec efface la note d'échec (paiement_echoue_le None)", rp["credite"] and s1["paiement_echoue_le"] is None)

# ═══ 2a. V527 quotas mensuels par offre + résiliation / réactivation / fin réelle ═══
def _base_mensuel(pack, restantes, used, sid="sub_m", code="AFR-M"):
    b = Base()
    b.subscriptions = Coll([{"id": "sm", "code": code, "stripe_subscription_id": sid, "billing_mode": "mensuel_auto",
                             "renewal_sessions": pack, "remaining_sessions": restantes, "total_sessions": pack, "status": "active",
                             "expires_at": "2026-10-31T23:59:59+00:00", "stripe_invoices": ["in_first"], "renewal_warnings_sent": []}])
    b.discount_codes = Coll([{"code": code, "maxUses": pack, "used": used, "active": True, "expiresAt": "2026-10-31", "stripe_invoices": []}])
    return b
def _cycle(b, iid="in_c"):
    return run(H.traiter_facture_payee(b, {"id": iid, "subscription": "sub_m", "billing_reason": "subscription_cycle",
                                           "lines": {"data": [{"period": {"end": _fin_nov}}]}}))
bf = _base_mensuel(4, 2, 2); _cycle(bf)
v("D. Flex 4 : remaining 2 -> 4 (PAS 6) ; canonique maxUses = used + 4 = 6 (restant 4) ; total 8",
  bf.subscriptions.docs[0]["remaining_sessions"] == 4 and bf.discount_codes.docs[0]["maxUses"] == 6 and bf.subscriptions.docs[0]["total_sessions"] == 8, (dict(bf.subscriptions.docs[0]), dict(bf.discount_codes.docs[0])))
bo = _base_mensuel(8, 3, 5); _cycle(bo)
v("E. Fondateurs : remaining 3 -> 8 (PAS 11) ; canonique maxUses = 5 + 8 = 13 (restant 8)",
  bo.subscriptions.docs[0]["remaining_sessions"] == 8 and bo.discount_codes.docs[0]["maxUses"] == 13, (dict(bo.subscriptions.docs[0]), dict(bo.discount_codes.docs[0])))
bl = _base_mensuel(8, 0, 8); _cycle(bl)
v("F. Liberté / Étudiant : mois entièrement consommé (0 restante, used 8) -> 8 (maxUses 16, restant 8)",
  bl.subscriptions.docs[0]["remaining_sessions"] == 8 and bl.discount_codes.docs[0]["maxUses"] == 16)
bz = _base_mensuel(8, 8, 0); _cycle(bz)
v("F2. mois jamais utilisé (8 restantes) -> toujours 8, jamais 16 : aucun cumul", bz.subscriptions.docs[0]["remaining_sessions"] == 8 and bz.discount_codes.docs[0]["maxUses"] == 8)
br = _base_mensuel(4, 1, 3); _cycle(br, "in_1"); _cycle(br, "in_1")
v("D2. idempotence par facture conservée : le même in_1 rejoué ne change rien (4 / maxUses 7)",
  br.subscriptions.docs[0]["remaining_sessions"] == 4 and br.discount_codes.docs[0]["maxUses"] == 7 and br.subscriptions.docs[0]["total_sessions"] == 8)

# A/B/C : résiliation, réactivation, fin réelle — Stripe est un faux injecté (jamais d'appel réseau)
appels = []
def faux_stripe(sid, **champs): appels.append((sid, champs))
ba = _base_mensuel(8, 5, 3); sa = ba.subscriptions.docs[0]
ra = run(H.resilier_abonnement(ba, dict(sa), faux_stripe))
v("A. résiliation : Stripe cancel_at_period_end=True (1 appel), champ local + resiliation_demandee_le, accès jusqu'au 31/10/2026",
  ra["ok"] and appels == [("sub_m", {"cancel_at_period_end": True})] and sa["cancel_at_period_end"] is True and sa.get("resiliation_demandee_le") and ra["acces_jusquau"] == "31/10/2026", (ra, appels))
v("A2. rien n'expire immédiatement : status active, expires_at et séances intacts",
  sa["status"] == "active" and sa["expires_at"] == "2026-10-31T23:59:59+00:00" and sa["remaining_sessions"] == 5)
v("A3. état affiché : « Résiliation programmée — accès jusqu'au 31/10/2026 »",
  H.etat_abonnement(sa) == {"recurrent": True, "etat": "resiliation_programmee", "libelle": "Résiliation programmée — accès jusqu'au 31/10/2026", "acces_jusquau": "31/10/2026"}, H.etat_abonnement(sa))
rb = run(H.reactiver_abonnement(ba, dict(sa), faux_stripe))
v("B. réactivation : cancel_at_period_end=False chez Stripe, état programmé retiré, abonnement actif",
  rb["ok"] and appels[-1] == ("sub_m", {"cancel_at_period_end": False}) and sa["cancel_at_period_end"] is False and sa["resiliation_demandee_le"] is None
  and H.etat_abonnement(sa)["etat"] == "actif" and H.etat_abonnement(sa)["libelle"] == "Actif — prochaine échéance le 31/10/2026", (rb, H.etat_abonnement(sa)))
n_avant = len(appels)
rc = run(H.traiter_abonnement_termine(ba, {"id": "sub_m", "status": "canceled"}))
v("C. fin réelle (customer.subscription.deleted) : logique existante appelée UNE fois, canceled, expires_at inchangé, aucun appel Stripe",
  rc["termine"] and sa["stripe_subscription_status"] == "canceled" and sa["expires_at"] == "2026-10-31T23:59:59+00:00" and len(appels) == n_avant)
v("C2. terminé -> plus résiliable ni réactivable (409 côté route), état « Abonnement terminé »",
  H.abonnement_resiliable(sa)[0] is False and H.etat_abonnement(sa)["etat"] == "termine")
v("C3. un forfait unique / une saison 2× ne se résilie pas ici",
  H.abonnement_resiliable({"stripe_subscription_id": "", "billing_mode": "unique", "status": "active"})[0] is False
  and H.abonnement_resiliable({"stripe_subscription_id": "sub_s", "billing_mode": "saison_2x", "status": "active"})[0] is False)
bu = _base_mensuel(8, 5, 3); su = bu.subscriptions.docs[0]
ru = run(H.traiter_abonnement_mis_a_jour(bu, {"id": "sub_m", "cancel_at_period_end": True}))
v("SYNC. customer.subscription.updated (résiliée depuis Stripe) : cancel_at_period_end reflété, date posée",
  ru["sync"] and su["cancel_at_period_end"] is True and su.get("resiliation_demandee_le"))
ru2 = run(H.traiter_abonnement_mis_a_jour(bu, {"id": "sub_m", "cancel_at_period_end": True}))
v("SYNC2. même événement rejoué : rien réécrit (date d'origine conservée)", not ru2["sync"])
ru3 = run(H.traiter_abonnement_mis_a_jour(bu, {"id": "sub_m", "cancel_at_period_end": False}))
v("SYNC3. annulée depuis Stripe : état retiré", ru3["sync"] and su["cancel_at_period_end"] is False and su["resiliation_demandee_le"] is None)

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

# ═══ 2b. V526 ANTI-DOUBLE ABONNEMENT (garde caisse) ═══
class BaseDbl:
    """subscriptions en mémoire ; find_one honore email/offer_id/status/stripe_subscription_id/
    stripe_subscription_status/expires_at ($nin, $ne, $or/$gt/$in) — juste ce que la garde utilise."""
    def __init__(self, docs): self.docs = docs
    def __getitem__(self, k): return self
    def _ok(self, d, f):
        for k, cond in f.items():
            if k == "$or":
                if not any(self._ok(d, alt) for alt in cond): return False
                continue
            val = d.get(k)
            if isinstance(cond, dict):
                if "$nin" in cond and val in cond["$nin"]: return False
                if "$in" in cond and val not in cond["$in"]: return False
                if "$ne" in cond and val == cond["$ne"]: return False
                if "$gt" in cond and not (val is not None and val > cond["$gt"]): return False
            elif val != cond: return False
        return True
    async def find_one(self, f, p=None):
        for d in self.docs:
            if self._ok(d, f): return dict(d)
        return None
_FUTUR, _PASSE = "2099-01-01T23:59:59+00:00", "2020-01-01T23:59:59+00:00"
_actif = {"id": "s-a", "email": "ana@test.ch", "offer_id": "flex", "status": "active", "stripe_subscription_id": "sub_a", "expires_at": _FUTUR}
_mensuel, _saison2x, _unique = {"id": "flex", "billing_mode": "mensuel_auto"}, {"id": "s2x", "billing_mode": "saison_2x"}, {"id": "u", "billing_mode": "unique"}
v("A. abonné actif + MÊME offre récurrente -> refusé (409), message clair",
  run(H.garde_abonnement_actif(BaseDbl([_actif]), "Ana@Test.ch ", _mensuel)) == (False, H.MSG_DEJA_ABONNE))
v("A2. l'e-mail est normalisé (majuscules/espaces) avant comparaison", run(H.abonnement_actif_meme_offre(BaseDbl([_actif]), "  ANA@test.CH", "flex")) is not None)
v("B. utilisateur non abonné -> checkout normal", run(H.garde_abonnement_actif(BaseDbl([_actif]), "bob@test.ch", _mensuel)) == (True, ""))
v("B2. abonné actif à une AUTRE offre -> l'autre offre reste achetable",
  run(H.garde_abonnement_actif(BaseDbl([_actif]), "ana@test.ch", dict(_saison2x))) == (True, ""))
v("B3. abonnement résilié (stripe_subscription_status canceled) -> re-souscription autorisée",
  run(H.garde_abonnement_actif(BaseDbl([dict(_actif, stripe_subscription_status="canceled")]), "ana@test.ch", _mensuel)) == (True, ""))
v("B4. droits expirés -> re-souscription autorisée", run(H.garde_abonnement_actif(BaseDbl([dict(_actif, expires_at=_PASSE)]), "ana@test.ch", _mensuel)) == (True, ""))
v("B5. abonnement NON récurrent (unique) du même e-mail/offre -> jamais bloqué par cette garde",
  run(H.garde_abonnement_actif(BaseDbl([dict(_actif, offer_id="u", stripe_subscription_id="")]), "ana@test.ch", _unique)) == (True, ""))
v("B6. sans e-mail connu -> fail-open (l'anonyme saisit son adresse chez Stripe)", run(H.garde_abonnement_actif(BaseDbl([_actif]), "", _mensuel)) == (True, ""))
class _Panne:
    def __getitem__(self, k): return self
    async def find_one(self, f, p=None): raise RuntimeError("mongo hs")
v("B7. panne de lecture -> fail-open, la caisse ne se bloque pas", run(H.garde_abonnement_actif(_Panne(), "ana@test.ch", _mensuel)) == (True, ""))

# ═══ 3. intégration server.py / checkout_routes (structure) ═══
S = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
C = open(os.path.join(RACINE, "api", "routes", "checkout_routes.py"), encoding="utf-8").read()
v("checkout principal : garde offre limitée (409) AVANT Stripe, sur l'offre lue en base", "_hiver.offre_reservable(_hiver_offre, _en_cours)" in S and "raise HTTPException(status_code=409, detail=_motif)" in S)
v("checkout principal : Session.create en mode récurrent SEULEMENT si billing_mode != unique ; l'appel historique reste intact",
  "if _hiver_mode != _hiver.BILLING_UNIQUE:" in S and "session = stripe.checkout.Session.create(api_key=active_stripe_key, **_p)" in S and "mode='payment'," in S)
v("checkout principal : métadonnées billing_mode + duree_mois transmises au webhook", 'metadata["billing_mode"] = _hiver_mode' in S and 'metadata["duree_mois"]' in S)
v("checkout vitrine (checkout_routes) : même garde, fail-open", "garde_offre_limitee as _hiver_garde" in C and "status_code=409, detail=_motif" in C)
v("V526 : anti-double branché sur la caisse principale (e-mail connu) ET la vitrine ; doublon MARQUÉ au webhook, jamais ignoré",
  "_hiver.garde_abonnement_actif(db, request.customerEmail, _hiver_offre)" in S and "raise HTTPException(status_code=409, detail=_motif_dbl)" in S
  and "garde_abonnement_actif as _hiver_garde_dbl" in C and 'subscription_data["doublon_de"]' in S and "await db.subscriptions.insert_one(subscription_data)" in S)
# ═══ V527 — structure : routes, webhook updated, filet doublon, anti-double anonyme, textes ═══
A = open(os.path.join(RACINE, "frontend", "src", "App.js"), encoding="utf-8").read()
U = open(os.path.join(RACINE, "frontend", "src", "utils", "offresAimants.js"), encoding="utf-8").read()
E = open(os.path.join(RACINE, "frontend", "src", "components", "SubscriberSpace.js"), encoding="utf-8").read()
v("V527 routes : /resilier et /reactiver derrière la MÊME garde que GET /subscriber/space (jeton B3-S1.3 + tenant), Stripe d'abord puis base",
  '@api_router.post("/subscriber/space/{access_code}/resilier")' in S and '@api_router.post("/subscriber/space/{access_code}/reactiver")' in S
  and "_b3s13_porteur_autorise(request, code_upper, m)" in S.split("_v527_abonnement_du_porteur")[1] and "_b3s13_tenant_accepte(_charge, subscription, discount)" in S
  and "stripe.Subscription.modify(sid, api_key=stripe.api_key, **champs)" in S)
v("V527 webhook : customer.subscription.updated branché (sync cancel_at_period_end) ET relayé par l'URL déclarée ; deleted inchangé",
  "event.type == 'customer.subscription.updated'" in S and "_hiver.traiter_abonnement_mis_a_jour(db, event.data.object)" in S
  and '"customer.subscription.updated"' in C and S.count("_hiver.traiter_abonnement_termine(db, event.data.object)") == 1)
v("V527 filet webhook : doublon -> 0 séance créditée (forfait ET code), cancel_at_period_end sur le doublon, journal explicite, AUCUN remboursement",
  'subscription_data["remaining_sessions"] = 0' in S and '{"$set": {"maxUses": 0, "doublon_de": _dbl.get("id")}}' in S
  and "stripe.Subscription.modify(_sid_dbl, cancel_at_period_end=True, api_key=stripe.api_key)" in S and "Refund" not in S.split("V527: FILET")[1][:3000])
v("I. anti-double anonyme AVANT Stripe : offre récurrente -> e-mail connu ou saisi (jamais la chaîne vide) -> customerEmail -> garde 409 serveur ; offre unique : rien",
  "const v527Email = v527EmailPourAbonnement(offer);" in A and "if (!v527Email.ok) return;" in A and "if (v527Email.email) payload.customerEmail = v527Email.email;" in A
  and "if (!offreEstRecurrente(offer)) return { ok: true, email: null };" in A and "export const estRecurrente = (o) => modeFacturation(o) !== 'unique';" in U
  and "_hiver.garde_abonnement_actif(db, request.customerEmail, _hiver_offre)" in S)
v("H/J/K. la saisie précède setCheckoutBusy et le garde-fou checkoutBusy reste le premier test (double clic = 1 checkout)",
  A.index("if (checkoutBusy) return;\n    const v527Email") < A.index("setCheckoutBusy(true);", A.index("const v527Email")))
v("V527 espace abonné : bloc « Mon abonnement mensuel » (offre, prix/mois, séances, échéance, état) + Résilier / Continuer ; l'ancien interrupteur local n'est plus rendu pour un abonnement Stripe",
  'data-testid="subscriber-space-abonnement-mensuel"' in E and "Résilier mon abonnement" in E and "Continuer mon abonnement" in E
  and "!subscription.etat_abonnement?.recurrent && (subscription.has_payment_method || subscription.auto_renew)" in E
  and '"etat_abonnement": _hiver.etat_abonnement(subscription),' in S)
v("V527 textes : règle « pas reportées au mois suivant » sur le mensuel (fiche, landing, e-mail d'accès, espace) — jamais sur la saison",
  "ne sont pas reportées au mois suivant" in U.split("mensuel_auto') return '1 mois")[1][:200] and "ne sont pas reportées au mois suivant" in S.split("def _m1_engagement")[1][:900]
  and S.count("report&eacute;es au mois suivant") == 2 and "ne sont pas reportées au mois suivant" in E
  and "reportées" not in H.__doc__ and "Saison de %d mois" in S)
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
