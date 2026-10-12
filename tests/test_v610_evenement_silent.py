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
_o60 = dict(OFFRE, stock=-1, max_participants=None)
verifier("Z0 aucune capacité : réservable avec 50, 51, 60 billets déjà vendus (stock -1 = illimité)",
         all(hiver.offre_reservable(_o60, n)[0] for n in (0, 49, 50, 51, 60, 500)), [hiver.offre_reservable(_o60, n) for n in (50, 51)])
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

# ── V610d : audio « Deviens Afroboosteur » — après réservation, événement payant seulement ──
from api.routes import referral_campaigns_engine as IC  # noqa: E402
_mp3 = "/api/files/abc123/afroboosteur.mp3"
_e = IC.valider_entree({"type": "event_paid", "status": "draft", "title": "Silent", "audio_partage_url": _mp3}, None)
verifier("AF1 événement payant : audio après réservation accepté (/api/files/...)", _e.get("audio_partage_url") == _mp3, _e)
for _t in ("trial", "pass_duo", "event_free"):
    _x = IC.valider_entree({"type": _t, "status": "draft", "title": "X", "audio_partage_url": _mp3}, None)
    verifier("AF2 %s : champ vidé (comportement inchangé)" % _t, _x.get("audio_partage_url") is None, _x)
try:
    IC.valider_entree({"type": "event_paid", "status": "draft", "title": "S", "audio_partage_url": "javascript:alert(1)"}, None)
    verifier("AF3 adresse dangereuse refusée", False)
except IC.InvitationCampagneInvalide:
    verifier("AF3 adresse dangereuse refusée", True)
_dp = IC.dto_public({"type": "event_paid", "share_token": "t", "audio_partage_url": _mp3, "audio_url": None})
verifier("AF4 dto public : audio après réservation SÉPARÉ de l'audio d'avant achat (audio_url vide)",
         _dp.get("audio_partage_url") == _mp3 and _dp.get("audio_url") is None, _dp)
verifier("AF5 dto public d'un autre type : jamais d'audio après réservation",
         IC.dto_public({"type": "event_free", "share_token": "t", "audio_partage_url": _mp3}).get("audio_partage_url") is None)
_pub = open(os.path.join(RACINE, "frontend", "src", "components", "InvitationPublique.js"), encoding="utf-8").read()
verifier("AF6 page AVANT achat : n'affiche pas l'audio Afroboosteur", "audio_partage_url" not in _pub)

# ── V610e : éditeur — bascules choisies par le coach, règle membres suspendable, description ──
_o2 = dict(OFFRE, palier_fin_prevente="2026-10-22T20:00", palier_fin_standard="2026-10-27T12:00")
verifier("ED1 bascule libre prévente : 22/10 19:59 -> 25, 20:00 -> 30",
         compute_active_price(_o2, now=zurich(2026, 10, 22, 19, 59))["price"] == 25
         and compute_active_price(_o2, now=zurich(2026, 10, 22, 20, 0))["price"] == 30)
verifier("ED2 bascule libre standard : 27/10 11:59 -> 30, 12:00 -> 40",
         compute_active_price(_o2, now=zurich(2026, 10, 27, 11, 59))["price"] == 30
         and compute_active_price(_o2, now=zurich(2026, 10, 27, 12, 0))["price"] == 40)
verifier("ED3 bascule illisible -> règle d'origine (21/10 18:45) intacte",
         compute_active_price(dict(OFFRE, palier_fin_prevente="n/a"), now=zurich(2026, 10, 21, 18, 45))["price"] == 30)
_o3 = dict(OFFRE, countdown_date="2026-10-15", countdown_time="12:00",
           palier_fin_prevente="2026-10-21T18:45", palier_fin_standard="2026-10-27T18:45")
verifier("ED3b bascules APRÈS le début (événement avancé ailleurs) -> ignorées, règle d'origine (J-7 / H-24)",
         compute_active_price(_o3, now=zurich(2026, 10, 14, 13, 0))["price"] == 40
         and compute_active_price(_o3, now=zurich(2026, 10, 8, 11, 59))["price"] == 25)
verifier("ED4 règle membres suspendue -> plus personne n'est offert ; configurée quand même",
         E.offres_gratuite(dict(OFFRE, gratuit_membres_actif=False)) == [] and E.regle_membres_configuree(dict(OFFRE, gratuit_membres_actif=False))
         and E.offres_gratuite(OFFRE) == IDS)
_dd = IC.valider_entree({"type": "event_paid", "status": "draft", "title": "S", "description": "<b>Ligne 1</b>\nLigne 2"}, None)
verifier("ED5 description : HTML retiré, retours à la ligne gardés", _dd["description"] == "Ligne 1\nLigne 2", _dd.get("description"))
try:
    IC.valider_entree({"type": "event_paid", "status": "draft", "title": "S", "description": "x" * 1501}, None)
    verifier("ED6 description > 1500 refusée", False)
except IC.InvitationCampagneInvalide:
    verifier("ED6 description > 1500 refusée", True)
_src_ed = open(os.path.join(RACINE, "api", "routes", "invitation_edition.py"), encoding="utf-8").read()
verifier("ED7 l'éditeur n'écrit jamais transactions / réservations passées ni la capacité",
         "payment_transactions\"].update" not in _src_ed and "reservations\"].update" not in _src_ed
         and "\"stock\"" not in _src_ed and "max_participants" not in _src_ed)
verifier("ED8 l'éditeur ne change jamais le share_token (aucune écriture, aucun jeton généré)",
         "\"share_token\":" not in _src_ed and "token_urlsafe" not in _src_ed and "_set_camp[\"share_token\"]" not in _src_ed)

# ── V610b : confidentialité — le paiement public ne lit JAMAIS le statut membre ──
_srv = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
_i = _srv.index("async def create_checkout_session(")
_corps = _srv[_i:_srv.index("\n@api_router.", _i)]
verifier("SEC-1 checkout public : aucun appel à abonnement_gratuit / evenements_offerts (pas d'oracle e-mail)",
         "abonnement_gratuit" not in _corps and "evenements_offerts" not in _corps and "gratuit_abonnements_offer_ids" not in _corps)
_appels = [m.start() for m in __import__("re").finditer(r"abonnement_gratuit\(", _srv)]
verifier("SEC-2 la gratuité n'est évaluée que derrière la session d'espace (1 seul appel, dans la route offerte)",
         len(_appels) == 1 and "_b3s13_porteur_autorise" in _srv[max(0, _appels[0] - 2500):_appels[0]], len(_appels))
verifier("SEC-3 l'ancien message révélateur a disparu", "MSG_MEMBRE_DOIT_RESERVER" not in _srv
         and "MSG_MEMBRE_DOIT_RESERVER" not in open(os.path.join(RACINE, "api", "routes", "evenement_special.py"), encoding="utf-8").read())

print("\n%d/%d PASS" % (sum(RES), len(RES)))
sys.exit(0 if all(RES) else 1)
