# -*- coding: utf-8 -*-
"""STATS-1 — les PIÈGES DE CALCUL corrigés avant exposition au Cockpit.

  (a) prix plat sentinelle : une offre à TARIF PROGRESSIF porte `price: 0.0`
      et se vend pourtant 10 à 25 CHF. `essai6_verdict` (preuve P3) la prenait
      pour une gratuité, et le moteur chargeait les offres SANS
      `progressive_pricing` : un billet payé devenait un « essai ».
  (b) abonnements supprimés (`status: "deleted"`, V618i) : comptés comme des
      achats (CA, nouveaux abonnements).
  (c) fuseau : couvert par tests/test_stats_association.py §13.

⚠️ CES CORRECTIONS CHANGENT DES CHIFFRES DE L'ÉCRAN COACH EXISTANT. Le banc le
MONTRE : sur le même jeu piégé, la version de référence (8baf9b13, relue
depuis git) et la version corrigée rendent des valeurs différentes, et la
route machine rend les valeurs corrigées — identiques à l'écran coach corrigé.

AUCUNE BASE RÉELLE, AUCUN RÉSEAU.
    python3 tests/test_stats_pieges.py
"""
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stats_fixtures as F  # noqa: E402

logging.disable(logging.CRITICAL)
RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


F.installer_serveur(F.Base(F.jeu_de_base()), F.ADMIN)
import api.routes.analytics_routes as R  # noqa: E402
import api.routes.analytics_shared as A  # noqa: E402
from api.routes.shared import essai6_verdict, est_un_essai  # noqa: E402
F.poser_admin()
REF = F.charger_reference()
verifier("référence %s relue depuis git" % F.COMMIT_REFERENCE, REF is not None)

# ═══ (a) essai6_verdict et le prix plat ═══
PROG = {"id": "o-prog", "name": "Afroboost Silent — billet", "price": 0.0, "progressive_pricing": True,
        "price_early_bird": 10, "price_standard": 15, "price_last_minute": 25,
        "countdown_date": "2026-09-26", "countdown_time": "18:30"}
verifier("(a) offre progressive à prix plat 0 : PAS un essai (P3 ne prouve rien)",
         not essai6_verdict(None, {"offer_id": "o-prog", "origine_paiement": "twint"}, PROG))
verifier("(a) offre NON progressive à 0 : reste un essai (P3 inchangée)",
         essai6_verdict(None, {"offer_id": "o-essai"}, {"price": 0}))
verifier("(a) offre progressive mais forfait offert (P2) : reste un essai",
         essai6_verdict(None, {"origine_paiement": "offert"}, PROG))
verifier("(a) offre progressive mais code gratuit (P1) : reste un essai",
         essai6_verdict({"payment_method": "free", "total_paid": 0}, {"offer_id": "o-prog"}, PROG))
if REF:
    verifier("(a) DISCRIMINANCE : la règle de référence classait ce billet payé comme essai",
             REF["shared"].essai6_verdict(None, {"offer_id": "o-prog", "origine_paiement": "twint"}, PROG) is True)

_b = F.Base({"subscriptions": [{"code": "AFR-PRG001", "offer_id": "o-prog", "origine_paiement": "twint"}],
             "discount_codes": [], "offers": [PROG]})
verifier("(a) est_un_essai (avec base) lit progressive_pricing : billet payé -> pas un essai",
         F.run(est_un_essai(_b, code="AFR-PRG001")) is False)
_b2 = F.Base({"subscriptions": [{"code": "AFR-ESS009", "offer_id": "o-essai"}], "discount_codes": [],
              "offers": [{"id": "o-essai", "price": 0}]})
verifier("(a) est_un_essai : la vraie offre d'essai à 0 reste un essai", F.run(est_un_essai(_b2, code="AFR-ESS009")) is True)


# ═══ le jeu piégé ═══
def jeu_piege():
    j = F.jeu_de_base()
    j["offers"].append(PROG)
    j["subscriptions"] += [
        # (a) billet payé 15 CHF (TWINT) d'une offre à paliers dont le prix plat vaut 0
        {"id": "s-prog", "code": "AFR-PRG001", "email": "ivan@mail.invalid", "coach_id": F.COACH, "offer_id": "o-prog",
         "offer_name": "Afroboost Silent — billet", "status": "active", "created_at": "2026-09-10T09:00:00+00:00",
         "expires_at": "2026-12-01T00:00:00+00:00", "origine_paiement": "twint", "montant_encaisse": 15,
         "total_sessions": 1, "remaining_sessions": 1},
        # (b) abonnement SUPPRIMÉ par le coach (pierre tombale V618i), 100 CHF déclarés encaissés
        {"id": "s-del", "code": "AFR-DEL001", "email": "jade@mail.invalid", "coach_id": F.COACH, "offer_id": "o-unite",
         "offer_name": "Cours à l'unité", "status": "deleted", "created_at": "2026-09-12T09:00:00+00:00",
         "expires_at": "2026-12-01T00:00:00+00:00", "origine_paiement": "especes", "montant_encaisse": 100,
         "total_sessions": 1, "remaining_sessions": 1, "statut_avant_suppression": "active"},
    ]
    # … dont la fiche de code existe encore : elle ne doit pas le faire renaître.
    j["discount_codes"].append({"code": "AFR-DEL001", "coach_id": F.COACH, "active": True})
    return j


def cockpit(module, **params):
    F.installer_serveur(F.Base(jeu_piege()), F.ADMIN)
    F.horloge_figee(module)
    return json.loads(json.dumps(F.run(module._calculer_cockpit(F.Req(), **params)), default=str))


P = dict(periode="mois", mois="2026-09", vue="association")
NEW = cockpit(R, **P)
verifier("(a) écran coach corrigé : 1 seul essai accordé (le vrai), pas 2", NEW["essais_funnel"]["accordes"] == 1,
         NEW["essais_funnel"]["accordes"])
verifier("(a) le billet progressif payé est un achat ordinaire de 15 CHF au CA",
         NEW["revenus"]["ca_encaisse"] == 295.0 + 15.0, NEW["revenus"]["ca_encaisse"])
verifier("(b) l'abonnement supprimé n'est PAS au CA (pas de +100 CHF)", NEW["revenus"]["ca_encaisse"] == 310.0)
verifier("(b) … ni parmi les nouveaux abonnements (2 + le billet = 3, pas 4)", NEW["abonnements"]["nouveaux"]["total"] == 3,
         NEW["abonnements"]["nouveaux"])
verifier("(b) l'exclusion est COMPTÉE et visible (1 souscription supprimée, 1 droit non ressuscité par sa fiche)",
         NEW["achats"]["ecartes"].get("souscriptions_supprimees") == 1 and NEW["achats"]["ecartes"].get("droits_supprimes") == 1,
         NEW["achats"]["ecartes"])
if REF:
    OLD = cockpit(REF["analytics_routes"], **P)
    verifier("⚠️ CHANGEMENT écran coach — essais accordés : référence 2 -> corrigé 1",
             OLD["essais_funnel"]["accordes"] == 2 and NEW["essais_funnel"]["accordes"] == 1,
             (OLD["essais_funnel"]["accordes"], NEW["essais_funnel"]["accordes"]))
    verifier("⚠️ CHANGEMENT écran coach — CA prouvé : référence 410 (dont 100 d un abonnement supprimé) -> corrigé 310",
             OLD["revenus"]["ca_encaisse"] != NEW["revenus"]["ca_encaisse"], (OLD["revenus"]["ca_encaisse"], NEW["revenus"]["ca_encaisse"]))
    verifier("⚠️ CHANGEMENT écran coach — nouveaux abonnements : référence 4 -> corrigé 3",
             OLD["abonnements"]["nouveaux"]["total"] == 4 and NEW["abonnements"]["nouveaux"]["total"] == 3,
             (OLD["abonnements"]["nouveaux"]["total"], NEW["abonnements"]["nouveaux"]["total"]))
    print("  [info] référence -> corrigé : essais %s -> %s ; CA %s -> %s ; nouveaux abonnements %s -> %s" % (
        OLD["essais_funnel"]["accordes"], NEW["essais_funnel"]["accordes"], OLD["revenus"]["ca_encaisse"],
        NEW["revenus"]["ca_encaisse"], OLD["abonnements"]["nouveaux"]["total"], NEW["abonnements"]["nouveaux"]["total"]))

# ═══ la route machine rend les chiffres corrigés, identiques à l'écran coach corrigé ═══
os.environ[R.STATS_ENV_FINANCES] = "cle-finances-de-test-9876543210-abcdef"
R._STATS_CACHE.clear(); R._STATS_DEBIT.clear()
F.installer_serveur(F.Base(jeu_piege()), "")
F.horloge_figee(R)
_r = F.run(R.stats_association(F.Req({"Authorization": "Bearer cle-finances-de-test-9876543210-abcdef"}), mois="2026-09"))
C = json.loads(_r.body)
verifier("route machine : essais accordés = écran coach corrigé (1)", C["essais"]["accordes"] == NEW["essais_funnel"]["accordes"] == 1)
verifier("route machine : CA prouvé = écran coach corrigé (310)", C["revenus"]["ca_prouve"] == NEW["revenus"]["ca_encaisse"] == 310.0,
         C["revenus"].get("ca_prouve"))
verifier("route machine : nouveaux abonnements = écran coach corrigé (3)", C["abonnements"]["nouveaux"] == 3)
verifier("route machine : aucune trace du code supprimé ni des adresses", "AFR-" not in json.dumps(C) and "@" not in json.dumps(C))

ok = sum(1 for _, c, _ in RESULTATS if c)
for nom, cond, detail in RESULTATS:
    print("  %s  %s%s" % ("OK  " if cond else "ECHEC", nom, ("  <- " + str(detail)[:300]) if (detail and not cond) else ""))
print("\n%d/%d" % (ok, len(RESULTATS)))
sys.exit(0 if ok == len(RESULTATS) else 1)
