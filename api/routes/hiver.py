# -*- coding: utf-8 -*-
"""HIVER — modes de paiement, droits par cycle, offre limitée. Règles pures + gestionnaires Stripe.

TROIS MODES DE PAIEMENT (`offers.billing_mode`), un seul par offre :
  * `unique`       — un paiement, un droit. LE SYSTÈME ACTUEL (Pulse X10 été,
                     cours à l'unité, essai, saison 8 mois payée en une fois).
  * `mensuel_auto` — abonnement Stripe RÉCURRENT (Checkout `mode=subscription`,
                     prix mensuel). Chaque facture payée ouvre les droits du
                     mois : `pack_sessions` séances, valables jusqu'au cycle
                     suivant. Carte uniquement (TWINT n'existe pas en récurrent).
  * `saison_2x`    — la saison de 8 mois en DEUX échéances : abonnement Stripe
                     facturé tous les 4 mois, `cancel_at` = début + 8 mois posé
                     après le premier paiement -> exactement deux factures.
                     Chaque facture ouvre 4 mois de droits.

DURÉE DES DROITS (`offers.duree_mois`) : le nombre de mois de validité d'un
achat. Absent = la règle historique (2 mois, `DUREE_VALIDITE_CODE_MOIS`, celle
du Pulse X10 été — INCHANGÉE). Saison 8 mois en une fois : `duree_mois = 8`.
Les abonnements récurrents dérivent leur durée du cycle (1 mois, ou 4 mois).

OFFRE LIMITÉE (Fondateurs) : `stock >= 0` = places (stock − ventes réelles,
`_annoter_places_restantes`) ET `countdown_enabled` + `countdown_date/time` =
date limite RÉELLE, stockée sur l'offre, modifiable depuis le tableau de bord.
L'offre est FERMÉE dès que l'un des deux est atteint : retirée de la vitrine et
de la landing, et REFUSÉE au checkout (409) — la 51e vente est impossible.

IDEMPOTENCE DES FACTURES : une facture Stripe est créditée UNE fois, par une
mise à jour atomique conditionnée à `stripe_invoices ∌ invoice.id` ; un
webhook rejoué ne crédite rien (modified_count = 0), ne crée ni code ni droit.
"""
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

BILLING_UNIQUE = "unique"
BILLING_MENSUEL = "mensuel_auto"
BILLING_SAISON_2X = "saison_2x"
BILLING_MODES = (BILLING_UNIQUE, BILLING_MENSUEL, BILLING_SAISON_2X)
BILLING_DEFAUT = BILLING_UNIQUE

SAISON_MOIS = 8                      # la saison hiver : 8 mois contractuels
SAISON_2X_INTERVALLE_MOIS = 4        # deux échéances : mois 0 et mois 4
SAISON_2X_ECHEANCES = 2
PLACES_RESERVEES_MINUTES = 30        # un checkout ouvert réserve sa place 30 min

RAISON_COMPLETE = "Cette offre est complète : toutes les places ont été prises."
RAISON_EXPIREE = "Cette offre est terminée : la date limite est passée."
LIBELLES_BILLING = {BILLING_UNIQUE: "Paiement unique", BILLING_MENSUEL: "Abonnement mensuel automatique",
                    BILLING_SAISON_2X: "Saison en 2 paiements"}

try:
    from zoneinfo import ZoneInfo
    _ZURICH = ZoneInfo("Europe/Zurich")
except Exception:  # noqa: BLE001
    _ZURICH = None


def billing_mode_valide(valeur) -> str:
    _v = str(valeur or "").strip().lower()
    return _v if _v in BILLING_MODES else BILLING_DEFAUT


def duree_mois_valide(valeur):
    """None (règle historique) ou un entier 1..24."""
    try:
        _n = int(float(valeur))
    except (TypeError, ValueError):
        return None
    return _n if 1 <= _n <= 24 else None


def duree_droits_mois(offre) -> int:
    """Combien de mois couvre UN paiement de cette offre — cycle pour le récurrent, `duree_mois` sinon."""
    _mode = billing_mode_valide((offre or {}).get("billing_mode"))
    if _mode == BILLING_MENSUEL:
        return 1
    if _mode == BILLING_SAISON_2X:
        return SAISON_2X_INTERVALLE_MOIS
    _d = duree_mois_valide((offre or {}).get("duree_mois"))
    if _d:
        return _d
    from api.routes.shared import DUREE_VALIDITE_CODE_MOIS
    return DUREE_VALIDITE_CODE_MOIS


def expiration_droits(depuis, mois):
    """`expires_at` (ISO complet, 23:59:59) et `expiresAt` (AAAA-MM-JJ) à `depuis` + `mois` mois calendaires."""
    from dateutil.relativedelta import relativedelta
    _base = depuis or datetime.now(timezone.utc)
    _fin = (_base + relativedelta(months=+int(mois))).replace(hour=23, minute=59, second=59, microsecond=0)
    return _fin.isoformat(), _fin.strftime("%Y-%m-%d")


def seances_par_paiement(offre) -> int:
    """Les séances ouvertes par UN paiement : pack × mois du cycle pour saison_2x, pack sinon.
    `pack_sessions = 0` est respecté (une adhésion seule n'ouvre aucune séance)."""
    try:
        _pack = int(float((offre or {}).get("pack_sessions")))
    except (TypeError, ValueError):
        _pack = 1
    if _pack < 0:
        _pack = 0
    if billing_mode_valide((offre or {}).get("billing_mode")) == BILLING_SAISON_2X:
        return _pack * SAISON_2X_INTERVALLE_MOIS
    return _pack


def date_limite(offre):
    """La date limite RÉELLE de l'offre (naïve, heure de Zurich), ou None."""
    _o = offre or {}
    if not _o.get("countdown_enabled") or not _o.get("countdown_date"):
        return None
    _t = str(_o.get("countdown_time") or "23:59")[:5]
    try:
        return datetime.strptime("%s %s" % (str(_o.get("countdown_date"))[:10], _t), "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def maintenant_zurich() -> datetime:
    _now = datetime.now(timezone.utc)
    return _now.astimezone(_ZURICH).replace(tzinfo=None) if _ZURICH else _now.replace(tzinfo=None)


def offre_expiree(offre, maintenant=None) -> bool:
    _lim = date_limite(offre)
    return bool(_lim and (maintenant or maintenant_zurich()) > _lim)


def offre_complete(offre) -> bool:
    """`places_restantes` (posé par `_annoter_places_restantes`) à zéro."""
    _p = (offre or {}).get("places_restantes")
    return isinstance(_p, int) and not isinstance(_p, bool) and _p <= 0


def motif_fermeture(offre, maintenant=None) -> str:
    """"" si l'offre est ouverte, sinon la phrase à afficher (complète / expirée)."""
    if offre_complete(offre):
        return RAISON_COMPLETE
    if offre_expiree(offre, maintenant):
        return RAISON_EXPIREE
    return ""


def offres_ouvertes(offres, maintenant=None) -> list:
    return [o for o in (offres or []) if not motif_fermeture(o, maintenant)]


def parametres_checkout(offre, nom_produit, montant_cents, success_url, cancel_url, email, metadata) -> dict:
    """Les paramètres de `stripe.checkout.Session.create` selon le mode de l'offre.

    `unique` : exactement le paramétrage historique (mode=payment, carte + TWINT).
    Récurrent : mode=subscription, carte seule, prix récurrent mensuel (ou tous
    les 4 mois), métadonnées recopiées sur l'abonnement pour que chaque
    facture sache à quelle offre elle appartient."""
    _mode = billing_mode_valide((offre or {}).get("billing_mode"))
    _meta = dict(metadata or {})
    _meta["billing_mode"] = _mode
    if _mode == BILLING_UNIQUE:
        return {
            "payment_method_types": ["card", "twint"],
            "line_items": [{"price_data": {"currency": "chf", "product_data": {"name": nom_produit},
                                           "unit_amount": int(montant_cents)}, "quantity": 1}],
            "mode": "payment", "success_url": success_url, "cancel_url": cancel_url,
            "customer_email": email, "metadata": _meta,
        }
    _recurrent = {"interval": "month", "interval_count": 1 if _mode == BILLING_MENSUEL else SAISON_2X_INTERVALLE_MOIS}
    return {
        "payment_method_types": ["card"],
        "line_items": [{"price_data": {"currency": "chf", "product_data": {"name": nom_produit},
                                       "unit_amount": int(montant_cents), "recurring": _recurrent}, "quantity": 1}],
        "mode": "subscription", "success_url": success_url, "cancel_url": cancel_url,
        "customer_email": email, "metadata": _meta,
        "subscription_data": {"metadata": _meta},
    }


def cancel_at_saison(depuis) -> int:
    """L'instant (epoch) où l'abonnement saison_2x s'arrête : début + 8 mois — deux factures, pas trois."""
    from dateutil.relativedelta import relativedelta
    _base = depuis or datetime.now(timezone.utc)
    if _base.tzinfo is None:
        _base = _base.replace(tzinfo=timezone.utc)
    return int((_base + relativedelta(months=+SAISON_MOIS)).timestamp())


def offre_reservable(offre, places_prises_en_cours=0, maintenant=None) -> tuple:
    """(True, "") si un checkout peut s'ouvrir ; sinon (False, motif).
    `places_prises_en_cours` = checkouts ouverts non encore payés (concurrence
    sur la dernière place) : ils comptent comme pris."""
    _o = dict(offre or {})
    if isinstance(_o.get("places_restantes"), int) and not isinstance(_o.get("places_restantes"), bool):
        _o["places_restantes"] = _o["places_restantes"] - int(places_prises_en_cours or 0)
    _m = motif_fermeture(_o, maintenant)
    return (not _m), _m


# ─────────────────────────── gestionnaires Stripe (base) ───────────────────────────

def fin_periode_facture(invoice, mois_repli):
    """(`expires_at`, `expiresAt`) depuis la période de la facture Stripe ; repli : maintenant + mois."""
    try:
        _lignes = (((invoice or {}).get("lines") or {}).get("data") or [])
        _fin = int(((_lignes[0] if _lignes else {}).get("period") or {}).get("end") or 0)
    except (TypeError, ValueError, AttributeError):
        _fin = 0
    if _fin > 0:
        _dt = datetime.fromtimestamp(_fin, tz=timezone.utc).replace(hour=23, minute=59, second=59, microsecond=0)
        return _dt.isoformat(), _dt.strftime("%Y-%m-%d")
    return expiration_droits(datetime.now(timezone.utc), mois_repli)


def _facture_est_renouvellement(invoice) -> bool:
    """Seules les factures de CYCLE créditent : la première est déjà créditée par
    `checkout.session.completed` (billing_reason subscription_create)."""
    return str((invoice or {}).get("billing_reason") or "") == "subscription_cycle"


async def traiter_facture_payee(db, invoice) -> dict:
    """`invoice.paid` / `invoice.payment_succeeded` : nouveau cycle -> droits du cycle,
    UNE fois par facture (atomique). Rend {credite, motif}."""
    _inv = invoice or {}
    _sid = str(_inv.get("subscription") or "")
    _iid = str(_inv.get("id") or "")
    if not _sid or not _iid:
        return {"credite": False, "motif": "facture_incomplete"}
    if not _facture_est_renouvellement(_inv):
        return {"credite": False, "motif": "premiere_facture_deja_creditee"}
    _doc = await db.subscriptions.find_one({"stripe_subscription_id": _sid}, {"_id": 0})
    if not _doc:
        return {"credite": False, "motif": "abonnement_inconnu"}
    # `renewal_sessions` = les séances d'UN paiement, déjà calculées à l'achat
    # (pack, ou pack × 4 pour saison_2x) : une seule source, pas de second calcul.
    try:
        _seances = max(0, int(float(_doc.get("renewal_sessions") or 0)))
    except (TypeError, ValueError):
        _seances = 0
    _mois = duree_droits_mois({"billing_mode": _doc.get("billing_mode")})
    # La fin des droits = la fin de la période FACTURÉE par Stripe (lines[0].period.end),
    # jamais « maintenant + n mois » : un webhook livré en retard n'ampute rien.
    _exp_iso, _exp_jour = fin_periode_facture(_inv, _mois)
    _maintenant = datetime.now(timezone.utc).isoformat()
    _r = await db.subscriptions.update_one(
        {"stripe_subscription_id": _sid, "stripe_invoices": {"$ne": _iid}},
        {"$inc": {"remaining_sessions": _seances, "total_sessions": _seances},
         "$set": {"status": "active", "expires_at": _exp_iso, "updated_at": _maintenant,
                  "last_renewal_date": _maintenant, "paiement_echoue_le": None},
         "$addToSet": {"stripe_invoices": _iid},
         "$push": {"renewal_warnings_sent": "renewed_" + datetime.now(timezone.utc).strftime("%Y%m%d")}})
    if not getattr(_r, "modified_count", 0):
        return {"credite": False, "motif": "facture_deja_creditee"}
    # Le code d'accès suit : même séances, même échéance. Idempotent par construction
    # (la souscription ne se met à jour qu'une fois par facture, donc on n'arrive ici qu'une fois).
    try:
        await db.discount_codes.update_one(
            {"code": _doc.get("code"), "stripe_invoices": {"$ne": _iid}},
            {"$inc": {"maxUses": _seances}, "$set": {"expiresAt": _exp_jour, "active": True},
             "$addToSet": {"stripe_invoices": _iid}})
    except Exception as _err:  # noqa: BLE001
        logger.error("[HIVER] code non prolongé pour %s : %s", _sid[:16], _err)
    logger.info("[HIVER] cycle crédité : abonnement %s +%d séances jusqu'au %s", _sid[:16], _seances, _exp_jour)
    return {"credite": True, "motif": "", "seances": _seances, "expires_at": _exp_iso}


async def traiter_facture_echouee(db, invoice) -> dict:
    """`invoice.payment_failed` : on le note, on n'enlève RIEN — les droits déjà payés
    courent jusqu'à `expires_at` ; Stripe relance ; à l'échec définitif l'abonnement se
    termine (`customer.subscription.deleted`)."""
    _sid = str((invoice or {}).get("subscription") or "")
    if not _sid:
        return {"note": False}
    _r = await db.subscriptions.update_one(
        {"stripe_subscription_id": _sid},
        {"$set": {"paiement_echoue_le": datetime.now(timezone.utc).isoformat(),
                  "updated_at": datetime.now(timezone.utc).isoformat()},
         "$push": {"renewal_warnings_sent": "payment_failed"}})
    return {"note": bool(getattr(_r, "matched_count", 0))}


async def traiter_abonnement_termine(db, subscription) -> dict:
    """`customer.subscription.deleted` : plus de renouvellement ; l'accès reste
    jusqu'à la fin de la période déjà payée (`expires_at` inchangé)."""
    _sid = str((subscription or {}).get("id") or "")
    if not _sid:
        return {"termine": False}
    _r = await db.subscriptions.update_one(
        {"stripe_subscription_id": _sid},
        {"$set": {"stripe_subscription_status": "canceled", "auto_renew": False,
                  "annule_le": datetime.now(timezone.utc).isoformat(),
                  "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"termine": bool(getattr(_r, "matched_count", 0))}


async def garde_offre_limitee(db, offre_id, maintenant=None) -> tuple:
    """(True, "") si l'offre `offre_id` peut encore être achetée ; sinon (False, motif).
    Places = stock − souscriptions réelles − checkouts ouverts (< 30 min) ; date
    limite = compte à rebours de l'offre. Fail-open sur panne de lecture : une
    caisse ne se bloque pas sur un compteur muet."""
    _oid = str(offre_id or "").strip()
    if not _oid:
        return True, ""
    try:
        _o = await db["offers"].find_one({"id": _oid}, {"_id": 0})
        if not _o or _o.get("isProduct"):
            return True, ""
        _stock = _o.get("stock")
        if isinstance(_stock, (int, float)) and not isinstance(_stock, bool) and _stock >= 0:
            _n = 0
            async for _v in db["subscriptions"].aggregate([
                    {"$match": {"offer_id": _oid, "status": {"$ne": "superseded"}}},
                    {"$count": "n"}]):
                _n = int(_v.get("n") or 0)
            _depuis = (datetime.now(timezone.utc) - timedelta(minutes=PLACES_RESERVEES_MINUTES)).isoformat()
            _en_cours = await db["payment_transactions"].count_documents(
                {"metadata.offer_id": _oid, "payment_status": "pending", "created_at": {"$gte": _depuis}})
            _o["places_restantes"] = max(0, int(_stock) - _n - int(_en_cours or 0))
        return offre_reservable(_o, 0, maintenant)
    except Exception as _err:  # noqa: BLE001
        logger.error("[HIVER] garde offre limitée indisponible (%s) — achat poursuivi", type(_err).__name__)
        return True, ""
