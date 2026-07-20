"""V223 — Calcul du prix progressif à 3 paliers.

Module volontairement pur : aucun accès base de données, aucun import de
server.py (qui ouvre une connexion MongoDB dès l'import). C'est ce qui rend
cette logique — la seule à porter un risque financier direct — testable
unitairement.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)

CURRENCY = "CHF"


def _reference_datetime(offer: dict) -> Optional[datetime]:
    """Date de référence = countdown_date + countdown_time (v132).

    Renvoie None si la date est absente ou malformée : l'appelant retombe
    alors sur le prix normal.
    """
    raw_date = offer.get("countdown_date")
    if not raw_date:
        return None
    raw_time = offer.get("countdown_time") or "00:00"
    try:
        parsed = datetime.strptime(f"{raw_date} {raw_time}", "%Y-%m-%d %H:%M")
        return parsed.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        logger.warning(f"[V223] countdown_date invalide: {raw_date!r} {raw_time!r}")
        return None


def compute_active_price(offer: dict, now: Optional[datetime] = None) -> dict:
    """Renvoie le prix et le palier actifs d'une offre.

    `now` est injectable pour rendre les tests déterministes.
    """
    base_price = float(offer.get("price") or 0)

    def regular():
        return {"price": base_price, "tier": "regular",
                "original_price": base_price, "currency": CURRENCY}

    if not offer.get("progressive_pricing"):
        return regular()

    reference = _reference_datetime(offer)
    if reference is None:
        # Aucune date de référence : on ne peut pas situer l'acheteur dans le
        # temps. On retombe sur le prix normal — surtout pas sur Early Bird,
        # qui ferait vendre au tarif le plus bas toute offre mal configurée.
        return regular()

    now = now or datetime.now(timezone.utc)
    remaining = reference - now

    # V223: un 0 explicite est une valeur valide (« aucune fenêtre »), il ne
    # doit pas être confondu avec un champ absent.
    _days = offer.get("early_bird_days_before")
    _hours = offer.get("standard_hours_before")
    days_before = int(_days) if _days is not None else 7
    hours_before = int(_hours) if _hours is not None else 24

    if remaining > timedelta(days=days_before):
        tier, tier_price = "early_bird", offer.get("price_early_bird")
    elif remaining > timedelta(hours=hours_before):
        tier, tier_price = "standard", offer.get("price_standard")
    else:
        # Inclut le cas « date dépassée » (remaining négatif).
        tier, tier_price = "last_minute", offer.get("price_last_minute")

    # Un palier non renseigné retombe sur le prix de base : une configuration
    # partielle ne doit jamais produire un prix nul.
    price = float(tier_price) if tier_price is not None else base_price

    return {"price": price, "tier": tier,
            "original_price": base_price, "currency": CURRENCY}
