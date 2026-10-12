"""V223 — Tests unitaires du calcul de prix progressif.

Module pur : aucune connexion MongoDB, aucun serveur requis.
"""
from datetime import datetime, timezone, timedelta

from api.pricing import compute_active_price

# V607 : « 2026-09-01 19:00 » saisi par le coach = 19:00 HEURE SUISSE (17:00 UTC en été).
from zoneinfo import ZoneInfo
REF = datetime(2026, 9, 1, 19, 0, tzinfo=ZoneInfo("Europe/Zurich"))


def _offer(**kw):
    base = {
        "price": 30.0,
        "progressive_pricing": True,
        "countdown_date": "2026-09-01",
        "countdown_time": "19:00",
        "price_early_bird": 15.0,
        "price_standard": 20.0,
        "price_last_minute": 30.0,
        "early_bird_days_before": 7,
        "standard_hours_before": 24,
    }
    base.update(kw)
    return base


def test_offre_non_progressive_retourne_prix_normal():
    res = compute_active_price({"price": 42.0}, now=REF)
    assert res == {"price": 42.0, "tier": "regular",
                   "original_price": 42.0, "currency": "CHF"}


def test_progressif_sans_countdown_date_retombe_sur_regular():
    """Garde-fou anti-perte de revenu : jamais Early Bird par défaut."""
    res = compute_active_price(_offer(countdown_date=None), now=REF)
    assert res["tier"] == "regular"
    assert res["price"] == 30.0


def test_plus_de_7_jours_avant_early_bird():
    res = compute_active_price(_offer(), now=REF - timedelta(days=10))
    assert res["tier"] == "early_bird"
    assert res["price"] == 15.0
    assert res["original_price"] == 30.0


def test_entre_24h_et_7_jours_standard():
    res = compute_active_price(_offer(), now=REF - timedelta(days=3))
    assert res["tier"] == "standard"
    assert res["price"] == 20.0


def test_moins_de_24h_last_minute():
    res = compute_active_price(_offer(), now=REF - timedelta(hours=2))
    assert res["tier"] == "last_minute"
    assert res["price"] == 30.0


def test_date_depassee_reste_last_minute():
    res = compute_active_price(_offer(), now=REF + timedelta(days=5))
    assert res["tier"] == "last_minute"


def test_frontiere_exactement_7_jours_bascule_en_standard():
    """À exactement 7 jours on n'est plus « plus de 7 jours avant »."""
    res = compute_active_price(_offer(), now=REF - timedelta(days=7))
    assert res["tier"] == "standard"


def test_palier_non_defini_retombe_sur_prix_de_base():
    """Une config partielle ne doit jamais produire un prix nul."""
    res = compute_active_price(_offer(price_early_bird=None),
                               now=REF - timedelta(days=10))
    assert res["tier"] == "early_bird"
    assert res["price"] == 30.0


def test_countdown_time_absent_utilise_23h59_comme_la_vitrine():
    """V607 : heure absente = 23:59 SUISSE (ce que l'éditeur affiche et que la vitrine
    lit), plus minuit. Référence = 2026-09-01 23:59 Zurich = 21:59 UTC. À 2026-08-31
    12:00 UTC il reste ~34 h -> standard (l'ancien minuit aurait donné last_minute)."""
    res = compute_active_price(_offer(countdown_time=None),
                               now=datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc))
    assert res["tier"] == "standard"


def test_v607_reference_heure_suisse_et_non_utc():
    """Le bug du fuseau : 19:00 saisi = 19:00 à Zurich (17:00 UTC en été). À 18:30 UTC
    (= 20:30 Zurich, APRÈS l'événement) on est en dernière minute ; et 24 h + 30 min
    avant 19:00 SUISSE, on est encore en standard (l'ancienne lecture UTC décalait de 2 h)."""
    o = _offer(early_bird_days_before=7, standard_hours_before=24)
    # 2026-08-31 16:30 UTC = 18:30 Zurich, soit 24 h 30 avant -> standard
    assert compute_active_price(o, now=datetime(2026, 8, 31, 16, 30, tzinfo=timezone.utc))["tier"] == "standard"
    # 2026-08-31 17:30 UTC = 19:30 Zurich, soit 23 h 30 avant -> dernière minute
    # (l'ancienne lecture UTC voyait encore 25 h 30 -> standard : le bug)
    assert compute_active_price(o, now=datetime(2026, 8, 31, 17, 30, tzinfo=timezone.utc))["tier"] == "last_minute"
    # Hiver (UTC+1) : 2026-12-12 20:00 Zurich = 19:00 UTC ; 7 j + 30 min avant -> prévente
    h = _offer(countdown_date="2026-12-12", countdown_time="20:00")
    assert compute_active_price(h, now=datetime(2026, 12, 5, 18, 30, tzinfo=timezone.utc))["tier"] == "early_bird"
    assert compute_active_price(h, now=datetime(2026, 12, 5, 19, 30, tzinfo=timezone.utc))["tier"] == "standard"


def test_countdown_date_malformee_retombe_sur_regular():
    """Une saisie dashboard invalide ne doit pas faire planter la vitrine."""
    res = compute_active_price(_offer(countdown_date="pas-une-date"), now=REF)
    assert res["tier"] == "regular"
    assert res["price"] == 30.0


def test_prix_absent_vaut_zero_sans_planter():
    res = compute_active_price({}, now=REF)
    assert res["price"] == 0.0
    assert res["tier"] == "regular"


def test_frontiere_exactement_24h_bascule_en_last_minute():
    """Symétrique du seuil 7 jours : à égalité on n'est plus « plus de 24h avant »."""
    res = compute_active_price(_offer(), now=REF - timedelta(hours=24))
    assert res["tier"] == "last_minute"


def test_fenetre_early_bird_a_zero_est_respectee():
    """early_bird_days_before=0 signifie « aucune fenêtre Early Bird », pas 7 jours.

    `now` doit tomber ENTRE le défaut bugué (7 j) et la valeur réelle (0 j),
    sinon le test est tautologique : à 30 jours, 30 > 7 et 30 > 0 donnent tous
    deux early_bird et le test passe même avec le bug. À 3 jours, un défaut à 7
    donnerait standard — l'écart est observable.
    """
    res = compute_active_price(_offer(early_bird_days_before=0),
                               now=REF - timedelta(days=3))
    assert res["tier"] == "early_bird"
    res2 = compute_active_price(_offer(early_bird_days_before=0, price_early_bird=None),
                                now=REF - timedelta(days=3))
    assert res2["price"] == 30.0
