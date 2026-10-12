#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V610 — Événement AFROBOOST SILENT (28/10/2026) : règles PURES, sans base ni réseau.

  * paliers 25 / 30 / 40 CHF aux bascules EXACTES (21/10 18:45 et 27/10 18:45,
    Europe/Zurich), plus aucune vente au début de l'événement ;
  * gratuité « abonnement 8 mois ACTIF à la date de l'événement » (et rien d'autre) ;
  * jour annulé du cours régulier (générateurs, scan, invitations) ;
  * une place offerte n'est jamais « restituée » à l'annulation ;
  * aucune capacité (pas de plafond 50) dans l'offre préparée.

Lancement : python3 tests/test_v610_evenement_silent.py
(Le parcours complet — webhook, réservation auto, idempotence, boule de neige,
route offerte, appel direct refusé — est couvert par le banc de bout en bout sur
la pile locale : 50/50.)
"""
import os
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from api.pricing import compute_active_price  # noqa: E402
from api.routes import evenement_special as E  # noqa: E402
from api.routes import hiver  # noqa: E402
from api.routes.referral_campaigns_engine import seance_du_cours  # noqa: E402
from api.routes.reservation_routes import _a1_a_lieu_aujourdhui  # noqa: E402
from api.routes.shared import lotb3_montant_debite  # noqa: E402

Z = ZoneInfo("Europe/Zurich")
RES = []


def verifier(nom, cond, info=""):
    RES.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + nom + ("" if cond else "  -> %r" % (info,)))


def zurich(a, mo, j, h, mi):
    return datetime(a, mo, j, h, mi, tzinfo=Z).astimezone(timezone.utc)


# L'offre telle que la prépare scripts/v610_evenement_silent.py
sys.path.insert(0, os.path.join(RACINE, "scripts"))
import v610_evenement_silent as SCRIPT  # noqa: E402

OFFRE = {"offer_type": "event", "price": 25.0, "progressive_pricing": True, "price_early_bird": 25.0,
         "price_standard": 30.0, "price_last_minute": 40.0, "early_bird_days_before": 7, "standard_hours_before": 24,
         "countdown_enabled": True, "countdown_date": SCRIPT.DATE, "countdown_time": SCRIPT.HEURE,
         "evenement_reservation_auto": True, "gratuit_abonnements_offer_ids": list(SCRIPT.OFFRES_8_MOIS)}

# ── Paliers ────────────────────────────────────────────────────────────────
for nom, quand, prix, palier in (
        ("A prévente aujourd'hui (12/10)", zurich(2026, 10, 12, 10, 0), 25, "early_bird"),
        ("A2 prévente 21/10 18:44", zurich(2026, 10, 21, 18, 44), 25, "early_bird"),
        ("B bascule 25 -> 30 : 21/10 18:45 Zurich", zurich(2026, 10, 21, 18, 45), 30, "standard"),
        ("B2 standard 27/10 18:44", zurich(2026, 10, 27, 18, 44), 30, "standard"),
        ("C bascule 30 -> 40 : 27/10 18:45 Zurich", zurich(2026, 10, 27, 18, 45), 40, "last_minute"),
        ("C2 dernière minute 28/10 18:44", zurich(2026, 10, 28, 18, 44), 40, "last_minute")):
    _r = compute_active_price(OFFRE, now=quand)
    verifier("%s -> %s CHF" % (nom, prix), _r["price"] == prix and _r["tier"] == palier, _r)

_lim = hiver.date_limite(OFFRE)
verifier("C3 vente ouverte le 28/10 à 18:44", not hiver.offre_expiree(OFFRE, datetime(2026, 10, 28, 18, 44)))
verifier("C4 plus AUCUNE vente au début de l'événement (28/10 18:45 + 1 min)",
         hiver.offre_expiree(OFFRE, datetime(2026, 10, 28, 18, 46)), _lim)

# ── Pas de capacité ──────────────────────────────────────────────────────
_src = open(os.path.join(RACINE, "scripts", "v610_evenement_silent.py"), encoding="utf-8").read()
verifier("Z1 offre préparée SANS plafond (stock -1, aucun max_participants)",
         '"stock": -1, "max_participants": None' in _src and "50 places" not in _src)
_txt = open(os.path.join(RACINE, "frontend", "src", "utils", "invitationCampagne.js"), encoding="utf-8").read()
verifier("Z2 message WhatsApp : aucune mention « 50 places »", "places maximum" not in _txt and "50 places" not in _txt)

# ── Gratuité membres ──────────────────────────────────────────────────────
DEBUT = E.debut_utc("2026-10-28T18:45:00")
verifier("D0 début de l'événement = 28/10 17:45 UTC (18:45 Zurich, heure d'hiver)",
         DEBUT == datetime(2026, 10, 28, 17, 45, tzinfo=timezone.utc), DEBUT)
IDS = OFFRE["gratuit_abonnements_offer_ids"]
for nom, sub, attendu in (
        ("D 8 mois (Membres) actif jusqu'en 06/2027 -> offert", {"offer_id": IDS[2], "status": "active",
                                                                 "expires_at": "2027-06-05T23:59:59+00:00"}, True),
        ("D2 Saison hiver 8 mois (paiement unique) actif -> offert", {"offer_id": IDS[0], "status": "active",
                                                                      "expires_at": "2027-05-31T23:59:59+00:00"}, True),
        ("D3 Saison hiver 2 paiements actif -> offert", {"offer_id": IDS[1], "status": "active",
                                                         "expires_at": "2026-11-15T00:00:00+00:00"}, True),
        ("E 8 mois EXPIRÉ avant l'événement (20/10) -> tarif normal", {"offer_id": IDS[0], "status": "active",
                                                                       "expires_at": "2026-10-20T23:59:59+00:00"}, False),
        ("E2 8 mois expirant 1 min AVANT le début -> tarif normal", {"offer_id": IDS[0], "status": "active",
                                                                    "expires_at": "2026-10-28T17:44:00+00:00"}, False),
        ("E3 8 mois statut « expired » -> tarif normal", {"offer_id": IDS[0], "status": "expired",
                                                         "expires_at": "2027-05-31T23:59:59+00:00"}, False),
        ("E4 8 mois sans date de fin -> tarif normal (rien ne prouve le droit)", {"offer_id": IDS[0], "status": "active"}, False),
        ("F Mensuel Liberté actif -> tarif normal", {"offer_id": "2fda04a6-1f0e-4306-a778-3748cd3eedfa", "status": "active",
                                                    "expires_at": "2027-06-05T23:59:59+00:00"}, False),
        ("F2 PULSE x10 actif -> tarif normal", {"offer_id": "a687ce86-94d6-4ba9-a847-c8a20e787491", "status": "active",
                                               "expires_at": "2027-06-05T23:59:59+00:00"}, False),
        ("F3 Carte membre association -> tarif normal", {"offer_id": "7cf60a07-e63c-4ec7-87b6-f9ed9b0be6fc", "status": "active",
                                                        "expires_at": "2027-06-05T23:59:59+00:00"}, False),
        ("F4 Cours à l'unité -> tarif normal", {"offer_id": "fea0ab6a-8adc-460d-9d7d-bbff57059ca5", "status": "active",
                                               "expires_at": "2027-06-05T23:59:59+00:00"}, False)):
    verifier(nom, E.abonnement_donne_droit(sub, IDS, DEBUT)[0] is attendu, E.abonnement_donne_droit(sub, IDS, DEBUT))
verifier("D4 offre SANS liste -> personne n'est offert", not E.abonnement_donne_droit(
    {"offer_id": IDS[0], "status": "active", "expires_at": "2027-06-05T23:59:59+00:00"}, [], DEBUT)[0])
verifier("D5 réservation auto : seulement offer_type event + drapeau explicite",
         E.reservation_auto(OFFRE) and not E.reservation_auto(dict(OFFRE, offer_type="single_class"))
         and not E.reservation_auto(dict(OFFRE, evenement_reservation_auto=None)))
verifier("D6 occurrence de l'événement", E.occurrence({"date": "2026-10-28", "time": "18:45"}) == "2026-10-28T18:45:00")
verifier("D7 événement commencé à 18:45 (Zurich), pas à 18:44",
         E.evenement_commence("2026-10-28T18:45:00", zurich(2026, 10, 28, 18, 45))
         and not E.evenement_commence("2026-10-28T18:45:00", zurich(2026, 10, 28, 18, 44)))

# ── Jour annulé ───────────────────────────────────────────────────────────
REG = {"id": "62fcac27", "weekday": 3, "time": "18:45", "dates_annulees": ["2026-10-28"]}
verifier("K1 jour annulé reconnu (date, ISO, datetime)", E.jour_annule(REG, "2026-10-28")
         and E.jour_annule(REG, "2026-10-28T18:45:00") and E.jour_annule(REG, datetime(2026, 10, 28, 18, 45)))
verifier("K2 les autres mercredis restent", not E.jour_annule(REG, "2026-10-21") and not E.jour_annule(REG, "2026-11-04"))
verifier("K3 cours sans champ : rien d'annulé", not E.jour_annule({"weekday": 3}, "2026-10-28"))
verifier("K4 scan / garde LOT 1 : le cours n'a PAS lieu le 28/10, il a lieu le 21/10",
         not _a1_a_lieu_aujourdhui(REG, "2026-10-28", 3) and _a1_a_lieu_aujourdhui(REG, "2026-10-21", 3))
verifier("K5 invitations : le 28/10 18:45 n'est plus une séance du cours ; le 21/10 l'est",
         not seance_du_cours(REG, "2026-10-28T18:45") and seance_du_cours(REG, "2026-10-21T18:45"))
verifier("K6 un cours à DATE FIXE n'est pas touché par dates_annulees", E.jour_annule(
    {"date": "2026-10-28", "dates_annulees": []}, "2026-10-28") is False)

# ── Annulation d'une place offerte ────────────────────────────────────────
verifier("I1 place offerte annulée : 0 séance à restituer", lotb3_montant_debite({"source": "member_free_event", "quantity": 1}) == 0)
verifier("I2 réservation d'espace ordinaire : inchangé (1 par place)",
         lotb3_montant_debite({"source": "subscriber_space", "quantity": 2}) == 2 and lotb3_montant_debite({}) == 1)

print("\n%d/%d PASS" % (sum(RES), len(RES)))
sys.exit(0 if all(RES) else 1)
