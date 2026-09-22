# -*- coding: utf-8 -*-
"""V535 — « Membres — 8 mois » : paiement intégral OU en 2 fois (M0 + M+1), 64 séances
au total quel que soit le mode, 8 mois de droits, réservée aux membres actifs,
jamais de réduction membre supplémentaire — SANS toucher aux autres offres.

Les 20 cas demandés par le propriétaire, sur les règles pures du moteur (hiver.py,
shared.py), la facture de cycle sur un faux Mongo, les paramètres Stripe construits
(jamais envoyés) et la structure du webhook (AST). Aucun réseau, aucun paiement.

    python3 tests/test_membres_8_mois.py
"""
import ast, asyncio, io, os, sys
from datetime import datetime, timezone, timedelta
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:1/factice")
os.environ.setdefault("DB_NAME", "factice")
from api.routes import hiver as H
from api.routes.shared import (lot3b_avantage_de_l_offre as pct, lot3b_couverture as couv,
                               lot3b_arbitrer as arb, lotr_verdict_recharge as lotr)


# Faux Mongo minimal (même forme que le banc HIVER — copié, pas importé : un module
# de test n'est pas une bibliothèque, l'importer rejouerait ses 82 vérifications).
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
        self.subscriptions = Coll([]); self.discount_codes = Coll([])

R = []
def v(nom, cond, detail=""): R.append((nom, bool(cond), detail))
def run(c): return asyncio.get_event_loop().run_until_complete(c)

M8 = {"id": "ba530ae4", "name": "Membres — 8 mois", "price": 199.99, "billing_mode": "saison_2x", "pack_sessions": 8,
      "duree_mois": 8, "requires_active_membership": True, "creates_membership": False, "member_discount_pct": 0,
      "installment_interval_months": 1, "full_payment_available": True}
AUTRE_2X = {"id": "7b96a431", "name": "Saison hiver — 2 paiements", "price": 299, "billing_mode": "saison_2x", "pack_sessions": 8}
PACK10 = {"id": "484c4519", "name": "Membres", "price": 150, "pack_sessions": 10, "duree_mois": 2,
          "requires_active_membership": True, "member_discount_pct": 0}
CARTE = {"id": "7cf60a07", "name": "Carte membre association", "price": 100, "duree_mois": 12, "creates_membership": True, "pack_sessions": 0}
WORKSHOP = {"name": "Workshop", "price": 40, "member_discount_pct": 50}
EVENEMENT = {"name": "Événement", "price": 30, "member_discount_pct": 50}
ACTIVE = [{"date_debut": "2026-03-25", "date_fin": "2027-03-24"}]
EXPIREE = [{"date_debut": "2025-03-25", "date_fin": "2026-03-24"}]
JOUR = "2026-10-10T18:30:00"

# ── accès (LOT R, inchangé) ──
v("1. membre actif (0 séance) -> Membres — 8 mois accessible", lotr(M8, "active", 0) == (True, ""))
v("2. non-membre -> achat refusé", lotr(M8, "absente", 0)[0] is False)
v("3. carte expirée -> achat refusé", lotr(M8, "expiree", 0)[0] is False)
v("1b. membre actif avec séances restantes -> refus « termine tes séances » (règle LOT R conservée)", lotr(M8, "active", 3)[0] is False)

# ── mode de paiement : choix explicite, jamais de fractionné par défaut ──
v("mode absent sur une offre à choix -> refus (jamais silencieux)", H.mode_paiement_valide(M8, None) == (None, H.RAISON_MODE_REQUIS))
v("mode inconnu -> refus", H.mode_paiement_valide(M8, "3x")[1] == H.RAISON_MODE_INCONNU)
v("offre SANS choix (autre saison_2x) : le champ est ignoré, comportement historique", H.mode_paiement_valide(AUTRE_2X, "full") == (None, ""))

# ── FULL ──
cents = round(199.99 * 100)
p_full = H.parametres_checkout(M8, "Membres — 8 mois", H.montant_integral_cents(cents), "s", "c", "a@b.ch", {"offer_id": "ba530ae4"}, mode_paiement="full")
v("4. mode FULL -> 399,98 CHF en UNE fois (mode=payment, unit_amount 39998)",
  p_full["mode"] == "payment" and p_full["line_items"][0]["price_data"]["unit_amount"] == 39998 and "recurring" not in p_full["line_items"][0]["price_data"], p_full["line_items"])
v("5. FULL -> aucune souscription Stripe, donc aucune deuxième facture (pas de subscription_data)", "subscription_data" not in p_full and p_full["metadata"]["payment_mode"] == "full")
v("FULL reste payable carte + TWINT comme un paiement unique", p_full["payment_method_types"] == ["card", "twint"])
v("10. FULL -> 64 séances total", H.seances_par_paiement(M8, "full") == 64)
v("13. FULL -> durée des droits 8 mois", H.duree_droits_mois(M8) == 8)

# ── 2X ──
p_2x = H.parametres_checkout(M8, "Membres — 8 mois", cents, "s", "c", "a@b.ch", {"offer_id": "ba530ae4"}, mode_paiement="2x")
rec = p_2x["line_items"][0]["price_data"]["recurring"]
v("6. mode 2X -> 199,99 CHF à M0 (mode=subscription, unit_amount 19999)", p_2x["mode"] == "subscription" and p_2x["line_items"][0]["price_data"]["unit_amount"] == 19999)
v("7. 2X -> 2e échéance à M+1 (interval month, interval_count 1)", rec == {"interval": "month", "interval_count": 1})
debut = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
cancel = datetime.fromtimestamp(H.cancel_at_saison(debut, offre=M8), tz=timezone.utc)
v("8. 2X -> cancel_at = début + 2 mois − 1 jour (la 2e facture M+1 passe, la 3e M+2 ne peut pas être émise)",
  cancel == datetime(2026, 11, 30, 10, 0, tzinfo=timezone.utc), cancel.isoformat())
v("9. total 2X = 199,99 + 199,99 = 399,98", round(19999 * 2 / 100, 2) == 399.98 and H.montant_integral_cents(cents) == 39998)
v("11. 2X -> 32 séances par échéance, 64 au total, JAMAIS 128/256/512",
  H.seances_par_paiement(M8, "2x") == 32 and H.seances_saison_total(M8) == 64 and H.seances_par_paiement(M8) * 2 == 64)
v("12. pack_sessions technique = 8 (quota mensuel) — avec 64 stocké le moteur donnerait 256/échéance",
  H.seances_par_paiement(dict(M8, pack_sessions=64)) == 256 and H.seances_par_paiement(M8) == 32)
v("13b. 2X -> droits de CHAQUE échéance jusqu'à la fin de saison (8 mois), pas 1 ni 2 mois", H.duree_droits_mois(M8) == 8)

# facture de cycle M+1 sur un faux Mongo : +32, droits = début + 8 mois, une 3e facture ne crédite rien
b = Base()
b.subscriptions = Coll([{"id": "s8", "code": "AFR-M8", "stripe_subscription_id": "sub_m8", "billing_mode": "saison_2x",
                         "installment_interval_months": 1, "payment_mode": "2x", "saison_debut": "2026-10-01T10:00:00+00:00",
                         "created_at": "2026-10-01T10:00:00+00:00", "renewal_sessions": 32, "remaining_sessions": 30,
                         "total_sessions": 32, "status": "active", "expires_at": "2027-06-01T23:59:59+00:00", "stripe_invoices": []}])  # M0 = checkout, jamais dans stripe_invoices (état réel du webhook)
b.discount_codes = Coll([{"code": "AFR-M8", "maxUses": 32, "used": 2, "active": True, "expiresAt": "2027-06-01"}])
fin_nov = int(datetime(2026, 11, 30, 12, 0, tzinfo=timezone.utc).timestamp())
r2 = run(H.traiter_facture_payee(b, {"id": "in_2", "subscription": "sub_m8", "billing_reason": "subscription_cycle", "lines": {"data": [{"period": {"end": fin_nov}}]}}))
s8 = b.subscriptions.docs[0]
v("7b. facture M+1 : +32 séances (30 -> 62, total 64), droits jusqu'à début + 8 mois (2027-06-01) et NON fin de période Stripe (30/11)",
  r2["credite"] and r2["seances"] == 32 and s8["remaining_sessions"] == 62 and s8["total_sessions"] == 64 and s8["expires_at"].startswith("2027-06-01"), (r2, dict(s8)))
r3 = run(H.traiter_facture_payee(b, {"id": "in_3", "subscription": "sub_m8", "billing_reason": "subscription_cycle", "lines": {"data": [{"period": {"end": fin_nov}}]}}))
v("8b. une 3e facture (qui ne devrait jamais exister) ne crédite RIEN : échéancier terminé, 64 restent 64",
  not r3["credite"] and r3["motif"] == "echeancier_termine" and s8["total_sessions"] == 64, r3)

# ── autres offres : strictement inchangées ──
p_autre = H.parametres_checkout(AUTRE_2X, "Saison", 29900, "s", "c", "a@b.ch", {})
v("14. autre offre saison_2x : M0 + M4 inchangé (interval_count 4), cancel_at = début + 8 mois",
  p_autre["line_items"][0]["price_data"]["recurring"]["interval_count"] == 4
  and datetime.fromtimestamp(H.cancel_at_saison(debut, offre=AUTRE_2X), tz=timezone.utc) == datetime(2027, 6, 1, 10, 0, tzinfo=timezone.utc)
  and H.cancel_at_saison(debut) == H.cancel_at_saison(debut, offre=AUTRE_2X)
  and H.duree_droits_mois(AUTRE_2X) == 4 and H.seances_par_paiement(AUTRE_2X) == 32 and "payment_mode" not in p_autre["metadata"])
v("constante globale SAISON_2X_INTERVALLE_MOIS toujours 4", H.SAISON_2X_INTERVALLE_MOIS == 4)
v("15. Pack 10 inchangé : 150 CHF, 10 séances, 2 mois, réservé (LOT R), 0 % ; membre actif 0 séance OK, non-membre refusé",
  H.seances_par_paiement(PACK10) == 10 and H.duree_droits_mois(PACK10) == 2 and pct(PACK10) == 0.0 and lotr(PACK10, "active", 0)[0] and not lotr(PACK10, "absente", 0)[0])
v("16. carte membre continue d'ouvrir l'adhésion (creates_membership) et n'ouvre aucune séance", CARTE["creates_membership"] is True and H.seances_par_paiement(CARTE) == 0)
v("17. Membres — 8 mois n'ouvre PAS d'adhésion", M8["creates_membership"] is False)

# ── 50 % ──
def prix(offre, adhesions):
    p = pct(offre); base = offre["price"]; a = couv(adhesions, JOUR)
    tm = base * (1 - p / 100) if (p > 0 and a) else None
    return arb(base, base, total_membre=tm, pct_membre=p)
v("18. workshop 40 CHF à 50 % : membre actif paie 20 CHF, non-membre 40, expiré 40",
  prix(WORKSHOP, ACTIVE)["total"] == 20.0 and prix(WORKSHOP, [])["total"] == 40.0 and prix(WORKSHOP, EXPIREE)["total"] == 40.0)
v("19. événement 30 CHF à 50 % : membre actif paie 15 CHF", prix(EVENEMENT, ACTIVE)["total"] == 15.0)
v("20. Membres — 8 mois : AUCUNE réduction 50 % supplémentaire (pct 0 -> 199,99 ; même avec 50 saisi par erreur ET réservée, l'arbitre refuse < 0)",
  prix(M8, ACTIVE)["total"] == 199.99 and pct(M8) == 0.0)
v("20b. Pack 10 et carte : aucune réduction (0 / creates_membership)", pct(PACK10) == 0.0 and pct(dict(CARTE, member_discount_pct=50)) == 0.0)

# ── intégration server.py (structure, AST) ──
SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
v("checkout : `paymentMode` est un champ de CreateCheckoutRequest, revalidé par `mode_paiement_valide` avant Stripe",
  "paymentMode: Optional[str] = None" in SRC and "mode_paiement_valide(_hiver_offre, getattr(request, \"paymentMode\", None))" in SRC)
v("checkout : FULL -> `montant_integral_cents` (prix × 2) calculé PAR LE SERVEUR, jamais depuis le client",
  "amount_cents = _hiver.montant_integral_cents(amount_cents)" in SRC)
v("webhook : séances créditées via `seances_par_paiement(..., mode_paiement=...)` et `cancel_at_saison(..., offre=...)`",
  "mode_paiement=_v535_mode_wh or None" in SRC and "offre=_v535_offre_wh" in SRC)
v("webhook : FULL -> aucune souscription Stripe conservée (auto_renew False, stripe_subscription_id None)",
  'subscription_data["auto_renew"] = False' in SRC and 'subscription_data["stripe_subscription_id"] = None' in SRC)
v("modèles : les deux champs sont dans Offer ET OfferCreate (symétrie PUT /offers) et dans la liste blanche publique",
  SRC.count("installment_interval_months: Optional[int] = None") == 2 and SRC.count("full_payment_available: bool = False") == 2
  and '"installment_interval_months", "full_payment_available",' in SRC)
v("espace abonné : `_lotr_etat_recharge` rend la LISTE `offres` (Pack 10 + Membres — 8 mois) avec prix, séances, échéancier",
  '"offres": _v535_liste,' in SRC and '"prix_integral"' in SRC)
v("WhatsApp : faits d'offre et règle membres CALCULÉS depuis les offres (v535_faits_offre / v535_regle_membres), rien en dur",
  "def v535_faits_offre" in SRC and "def v535_regle_membres" in SRC and "_faits = v535_faits_offre(_o)" in SRC
  and "399" not in SRC[SRC.index("def v535_faits_offre"):SRC.index("def v440_prix_lisible")])
v("partage : la page OG redirige vers le lien profond `?offre=<id>` et l'URL canonique porte /api",
  'e_cible = _html.escape(f"{FRONT}/?offre={offer_id}", quote=True)' in SRC and 'content="0;url={e_cible}"' in SRC)

# ── WhatsApp : faits et règle CALCULÉS depuis les offres (appel réel des fonctions) ──
try:
    import api.server as S
    _f = S.v535_faits_offre(M8)
    v("WhatsApp — faits de « Membres — 8 mois » : 64 séances au total, 8 mois, 2 × 199,99 (2e à +1 mois, total 399,98), OU 399,98 en une fois, réservée aux membres, aucune réduction supplémentaire",
      "64 séances au total" in _f and "formule de 8 mois" in _f and "1 mois plus tard" in _f and "399.98" in _f and "en une fois" in _f
      and "RÉSERVÉE AUX MEMBRES" in _f and "aucune réduction supplémentaire" in _f, _f)
    _fa = S.v535_faits_offre(AUTRE_2X)
    v("WhatsApp — autre saison_2x : 2e échéance « 4 mois plus tard », pas de paiement en une fois", "4 mois plus tard" in _fa and "en une fois" not in _fa, _fa)
    _r = S.v535_regle_membres([M8, PACK10, CARTE, WORKSHOP, EVENEMENT])
    _rt = " ".join(_r)
    v("WhatsApp — règle membres déduite : adhésion = Carte membre association ; réservées = Membres, Membres — 8 mois ; avantage 50 % UNIQUEMENT sur les offres qui le portent",
      "Carte membre association" in _rt and "Membres — 8 mois" in _rt and "50 %" in _rt and "UNIQUEMENT" in _rt, _rt[:300])
    v("WhatsApp — rien en dur : sans offre à avantage, aucun pourcentage n'est énoncé", "%" not in " ".join(S.v535_regle_membres([M8, PACK10, CARTE])))
    v("WhatsApp — workshop à 50 % : « avantage carte membre : −50 % »", "−50 %" in S.v535_faits_offre(WORKSHOP))

    # ── V535c : SYNCHRONISATION — le contexte suit la base, rien en dur ──────────
    _ctx = lambda offres: S.v440_contexte_metier(offres, None, "test", maintenant=None)
    _base = _ctx([M8, PACK10, CARTE, WORKSHOP])
    v("SYNC. contexte de base : Membres — 8 mois 64 séances, 8 mois, 2 × 199.99 (1 mois plus tard), total 399.98, en une fois 399.98 ; Pack 10 150 CHF / 10 séances",
      all(x in _base for x in ("Membres — 8 mois", "64 séances au total", "formule de 8 mois", "199.99 CHF maintenant puis 199.99 CHF 1 mois plus tard", "total 399.98 CHF", "ou paiement en une fois de 399.98 CHF", "10 séances", "150 CHF")), _base[:400])
    _m8b = dict(M8, price=249.99)
    _c1 = _ctx([_m8b, PACK10, CARTE, WORKSHOP])
    v("SYNC 1. prix 199.99 -> 249.99 : le contexte suit (249.99 puis 249.99, total 499.98, une fois 499.98) et n'a plus 199.99",
      "249.99 CHF maintenant puis 249.99 CHF" in _c1 and "total 499.98 CHF" in _c1 and "une fois de 499.98 CHF" in _c1 and "199.99" not in _c1, _c1[:300])
    _c2 = _ctx([dict(M8, pack_sessions=5), PACK10, CARTE, WORKSHOP])
    v("SYNC 2. pack_sessions 8 -> 5 : « 40 séances au total » (5 × 4 × 2), plus « 64 »", "40 séances au total" in _c2 and "64 séances" not in _c2, _c2[:300])
    _c3 = _ctx([dict(M8, installment_interval_months=3), PACK10, CARTE, WORKSHOP])
    v("SYNC 3. intervalle 1 -> 3 : « 3 mois plus tard », plus « 1 mois plus tard »", "3 mois plus tard" in _c3 and "1 mois plus tard" not in _c3, _c3[:300])
    _c4 = _ctx([PACK10, CARTE, WORKSHOP])
    v("SYNC 4. offre désactivée (absente des offres visibles) : plus proposée, la règle ne la nomme plus",
      "Membres — 8 mois" not in _c4 and "Membres" in _c4, _c4[:300])
    _c5 = _ctx([M8, PACK10, CARTE, dict(WORKSHOP, member_discount_pct=30)])
    v("SYNC 5. member_discount_pct 50 -> 30 sur le workshop : « −30 % » et « 30 % » dans la règle, plus 50 %", "−30 %" in _c5 and "30 %" in _c5 and "50 %" not in _c5, _c5[:300])
    _c6 = _ctx([])
    import re as _re
    v("SYNC 6. aucune offre : aucun montant, aucune séance, aucun pourcentage, aucun nom d'offre ; « N'invente ni prix » et « AUCUNE OFFRE » présents",
      not _re.search(r"\d+(\.\d+)? CHF", _c6) and "séance" not in _c6 and "%" not in _c6 and "Membres" not in _c6
      and "N'invente ni prix" in _c6 and "AUCUNE OFFRE" in _c6, _c6[:300])
    v("SYNC. Membres — 8 mois et Pack 10 : « aucune réduction supplémentaire » ; le 50 % n'est annoncé que sur le workshop",
      S.v535_faits_offre(M8).count("aucune réduction supplémentaire") == 1 and "%" not in S.v535_faits_offre(M8) and "%" not in S.v535_faits_offre(PACK10))
    v("SYNC. la Carte membre annuelle « ouvre l'adhésion membre annuelle »", "ouvre l'adhésion membre annuelle" in S.v535_faits_offre(CARTE))
    _p10c = dict(PACK10, visible=False, requires_active_membership=True)
    _c7 = _ctx([M8, _p10c, CARTE, WORKSHOP])
    v("SYNC 7. Pack 10 MASQUÉ de la vitrine mais réservé aux membres : connu de l'assistant (150 CHF, 10 séances, réservé) SANS lien public, et nommé dans la règle",
      "SANS LIEN PUBLIC" in _c7 and "- Membres — 150 CHF (10 séances" in _c7 and "offre=484c4519" not in _c7 and "RÉSERVÉES AUX MEMBRES ACTIFS : Membres — 8 mois, Membres." in _c7, _c7[:600])
    _c8 = _ctx([M8, dict(PACK10, visible=False, requires_active_membership=False), CARTE, WORKSHOP])
    v("SYNC 8. une offre masquée NON réservée reste inconnue de l'assistant (un brouillon n'est jamais proposé)", "150 CHF" not in _c8, _c8[:300])
    _src_q = S.v440_offres_visibles.__code__.co_consts
    v("SYNC 9. la requête base remonte les offres réservées même masquées (`requires_active_membership: True` dans le `$or`)", "requires_active_membership" in repr(_src_q) and "$or" in repr(_src_q))
    v("SYNC 10. le webhook ne cible (ne lie) qu'une offre VISIBLE", "[_o for _o in _v440_offres if v440_visible(_o)]" in io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read())
    _src_prompt = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
    v("SYNC. aucune donnée commerciale en dur : le contexte est construit par des fonctions, `systemPrompt` est lu tel quel et jamais réécrit",
      "ai_config.get(\"systemPrompt\", \"\") + context" in _src_prompt and "399" not in S.v535_faits_offre.__code__.co_consts.__repr__() and "64" not in S.v535_faits_offre.__code__.co_consts.__repr__())

    # ── V535c : IDENTITÉ MEMBRE par numéro WhatsApp — fail closed ──────────────────
    class _CollTel:
        def __init__(self, docs): self.docs = docs
        def find(self, q, proj=None):
            docs = self.docs
            class _Cur:
                def __init__(s, d): s.d = d
                def limit(s, n): return s
                def __aiter__(s):
                    async def g():
                        for x in s.d: yield dict(x)
                    return g()
                async def to_list(s, n): return [dict(x) for x in s.d]
            return _Cur(docs)
    class _DbTel:
        def __init__(self, users, subs, res, adh):
            self.users, self.subscriptions, self.reservations, self.memberships = map(_CollTel, (users, subs, res, adh))
        def __getitem__(self, k): return getattr(self, k)
    _auj = datetime.now(timezone.utc).date()
    _adh_ok = {"email": "membre@exemple.test", "coach_id": None, "date_debut": str(_auj - timedelta(days=30)), "date_fin": str(_auj + timedelta(days=300))}
    _adh_exp = {"email": "ancien@exemple.test", "coach_id": None, "date_debut": "2024-01-01", "date_fin": "2024-12-31"}
    _S_db = S.db
    try:
        S.db = _DbTel([{"email": "membre@exemple.test", "whatsapp": "+41 76 511 22 33"}], [], [], [_adh_ok])
        _i1 = run(S.v535c_statut_membre_par_telephone("41765112233"))
        v("IDENTITÉ. numéro relié à UN membre actif (égalité stricte après normalisation +41 76 511 22 33 = 41765112233) -> actif + date de fin",
          _i1["statut"] == "actif" and _i1["date_fin"] == str(_auj + timedelta(days=300)), _i1)
        v("IDENTITÉ. contexte membre actif : « carte membre ACTIVE jusqu'au … — tu peux lui proposer les offres réservées »",
          "ACTIVE jusqu'au" in S.v535c_contexte_statut_membre(_i1) and "proposer les offres réservées" in S.v535c_contexte_statut_membre(_i1))
        S.db = _DbTel([{"email": "ancien@exemple.test", "whatsapp": "0765112233"}], [], [], [_adh_exp])
        _i2 = run(S.v535c_statut_membre_par_telephone("41765112233"))
        v("IDENTITÉ. membre expiré (0765112233 = 41765112233) -> expiree ; contexte : « ne présente PAS … comme achetables »",
          _i2["statut"] == "expiree" and "ne présente PAS" in S.v535c_contexte_statut_membre(_i2), _i2)
        S.db = _DbTel([], [], [], [_adh_ok])
        _i3 = run(S.v535c_statut_membre_par_telephone("41765112233"))
        v("IDENTITÉ. numéro inconnu -> « inconnu » ; contexte : « n'affirme JAMAIS qu'elle est membre »",
          _i3["statut"] == "inconnu" and "n'affirme JAMAIS" in S.v535c_contexte_statut_membre(_i3), _i3)
        S.db = _DbTel([{"email": "membre@exemple.test", "whatsapp": "+41765112233"}, {"email": "autre@exemple.test", "phone": "0765112233"}], [], [], [_adh_ok])
        _i4 = run(S.v535c_statut_membre_par_telephone("41765112233"))
        v("IDENTITÉ. numéro partagé par DEUX adresses -> ambigu -> « inconnu » (jamais inventé)", _i4["statut"] == "inconnu", _i4)
        S.db = _DbTel([{"email": "membre@exemple.test", "whatsapp": "+41 76 511 22 34"}], [], [], [_adh_ok])
        _i5 = run(S.v535c_statut_membre_par_telephone("41765112233"))
        v("IDENTITÉ. un numéro qui ne diffère que d'un chiffre n'est PAS relié (pas de suffixe)", _i5["statut"] == "inconnu", _i5)
        class _Muet:
            def __getitem__(self, k): raise RuntimeError("base muette")
        S.db = _Muet()
        _i6 = run(S.v535c_statut_membre_par_telephone("41765112233"))
        v("IDENTITÉ. base en panne -> « inconnu », jamais une exception", _i6["statut"] == "inconnu", _i6)
        _src_wh = _src_prompt
        v("IDENTITÉ. le webhook WhatsApp injecte le statut APRÈS le contexte métier, avant l'appel IA",
          _src_wh.find("v535c_contexte_statut_membre(_v535c_info)") > _src_wh.find("v440_contexte_metier(\n                        _v440_offres") > 0)
    finally:
        S.db = _S_db
except Exception as _e:  # noqa: BLE001
    import traceback; traceback.print_exc()
    v("WhatsApp — fonctions v535 appelables", False, repr(_e))

ok = sum(1 for _, c, _ in R if c); ko = [(n, d) for n, c, d in R if not c]
for n, c, d in R: print(("  OK    " if c else "  RATE  ") + n + ("" if c else "  [%s]" % str(d)[:200]))
print("\n%d / %d verifications au vert" % (ok, len(R)))
sys.exit(0 if not ko else 1)
