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
# V535 — ÉCHÉANCIER PAR OFFRE (additif). Une offre `saison_2x` peut porter
# `installment_interval_months` (1..12) : ses deux échéances sont alors à
# M0 et M+n au lieu de M0/M+4, et ses droits (séances ET durée) restent ceux de
# la saison entière, quel que soit le rythme de paiement. Elle peut aussi porter
# `full_payment_available: true` : l'acheteur choisit alors EXPLICITEMENT entre
# « 2 fois » et « en une fois » (prix × 2, un seul paiement). ABSENT = le
# comportement historique, à l'identique, pour toutes les autres offres.
CHAMP_INTERVALLE = "installment_interval_months"
CHAMP_PAIEMENT_INTEGRAL = "full_payment_available"
MODE_PAIEMENT_2X = "2x"
MODE_PAIEMENT_INTEGRAL = "full"
MODES_PAIEMENT = (MODE_PAIEMENT_2X, MODE_PAIEMENT_INTEGRAL)
RAISON_MODE_REQUIS = "Choisis ton mode de paiement : en une fois ou en 2 fois."
RAISON_MODE_INCONNU = "Mode de paiement inconnu."
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


def intervalle_echeances(offre) -> int:
    """V535 — mois entre les deux échéances d'une offre `saison_2x` : sa valeur
    propre (`installment_interval_months`, 1..12) sinon la constante historique."""
    try:
        _n = int(float((offre or {}).get(CHAMP_INTERVALLE)))
    except (TypeError, ValueError):
        return SAISON_2X_INTERVALLE_MOIS
    return _n if 1 <= _n <= 12 else SAISON_2X_INTERVALLE_MOIS


def echeancier_personnalise(offre) -> bool:
    """V535 — vrai si l'offre est en `saison_2x` AVEC un intervalle propre."""
    return (billing_mode_valide((offre or {}).get("billing_mode")) == BILLING_SAISON_2X
            and intervalle_echeances(offre) != SAISON_2X_INTERVALLE_MOIS)


def paiement_integral_disponible(offre) -> bool:
    """V535 — l'acheteur peut choisir « en une fois » : offre `saison_2x` déclarée
    `full_payment_available: true` (booléen strict, jamais « truthy »)."""
    return (billing_mode_valide((offre or {}).get("billing_mode")) == BILLING_SAISON_2X
            and (offre or {}).get(CHAMP_PAIEMENT_INTEGRAL) is True)


def mode_paiement_valide(offre, mode) -> tuple:
    """V535 — (mode_normalisé | None, motif_refus). Quand l'offre laisse le choix,
    le mode est OBLIGATOIRE et explicite : jamais de fractionné par défaut. Quand
    elle ne le laisse pas, le champ est ignoré (None) — comportement historique."""
    if not paiement_integral_disponible(offre):
        return None, ""
    _m = str(mode or "").strip().lower()
    if not _m:
        return None, RAISON_MODE_REQUIS
    if _m not in MODES_PAIEMENT:
        return None, RAISON_MODE_INCONNU
    return _m, ""


def montant_integral_cents(montant_echeance_cents) -> int:
    """V535 — le paiement en une fois vaut la somme des échéances : 2 × 199,99 = 399,98."""
    return int(montant_echeance_cents) * SAISON_2X_ECHEANCES


def duree_droits_mois(offre) -> int:
    """Combien de mois couvre UN paiement de cette offre — cycle pour le récurrent, `duree_mois` sinon."""
    _mode = billing_mode_valide((offre or {}).get("billing_mode"))
    if _mode == BILLING_MENSUEL:
        return 1
    if _mode == BILLING_SAISON_2X:
        # V535 : échéancier propre -> chaque paiement ouvre la SAISON entière (8 mois) ;
        # payer en 2 fois sur 1 mois ne fait pas une formule de 2 mois.
        if echeancier_personnalise(offre):
            return SAISON_MOIS
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


def seances_par_paiement(offre, mode_paiement=None) -> int:
    """Les séances ouvertes par UN paiement : pack × mois du cycle pour saison_2x, pack sinon.
    `pack_sessions = 0` est respecté (une adhésion seule n'ouvre aucune séance)."""
    try:
        _pack = int(float((offre or {}).get("pack_sessions")))
    except (TypeError, ValueError):
        _pack = 1
    if _pack < 0:
        _pack = 0
    if billing_mode_valide((offre or {}).get("billing_mode")) == BILLING_SAISON_2X:
        # V535 : `pack` = QUOTA MENSUEL ; une échéance ouvre pack × 4 = la moitié de la
        # saison, quel que soit le rythme (M+4 ou M+1) ; le paiement intégral ouvre les
        # deux moitiés d'un coup (64), jamais davantage.
        _par_echeance = _pack * SAISON_2X_INTERVALLE_MOIS
        if str(mode_paiement or "") == MODE_PAIEMENT_INTEGRAL:
            return _par_echeance * SAISON_2X_ECHEANCES
        return _par_echeance
    return _pack


def seances_saison_total(offre) -> int:
    """V535 — le total de la saison (les deux échéances), pour l'affichage : 64."""
    return seances_par_paiement(offre, MODE_PAIEMENT_INTEGRAL)


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


def parametres_checkout(offre, nom_produit, montant_cents, success_url, cancel_url, email, metadata,
                        mode_paiement=None) -> dict:
    """Les paramètres de `stripe.checkout.Session.create` selon le mode de l'offre.

    `unique` : exactement le paramétrage historique (mode=payment, carte + TWINT).
    Récurrent : mode=subscription, carte seule, prix récurrent mensuel (ou tous
    les 4 mois), métadonnées recopiées sur l'abonnement pour que chaque
    facture sache à quelle offre elle appartient."""
    _mode = billing_mode_valide((offre or {}).get("billing_mode"))
    _meta = dict(metadata or {})
    _meta["billing_mode"] = _mode
    # V535 : mode choisi par l'acheteur (offres à choix seulement) et rythme propre.
    if _mode == BILLING_SAISON_2X and mode_paiement in MODES_PAIEMENT:
        _meta["payment_mode"] = mode_paiement
        _meta[CHAMP_INTERVALLE] = str(intervalle_echeances(offre))
    if _mode == BILLING_UNIQUE or (_mode == BILLING_SAISON_2X and mode_paiement == MODE_PAIEMENT_INTEGRAL):
        return {
            "payment_method_types": ["card", "twint"],
            "line_items": [{"price_data": {"currency": "chf", "product_data": {"name": nom_produit},
                                           "unit_amount": int(montant_cents)}, "quantity": 1}],
            "mode": "payment", "success_url": success_url, "cancel_url": cancel_url,
            "customer_email": email, "metadata": _meta,
        }
    _recurrent = {"interval": "month", "interval_count": 1 if _mode == BILLING_MENSUEL else intervalle_echeances(offre)}
    return {
        "payment_method_types": ["card"],
        "line_items": [{"price_data": {"currency": "chf", "product_data": {"name": nom_produit},
                                       "unit_amount": int(montant_cents), "recurring": _recurrent}, "quantity": 1}],
        "mode": "subscription", "success_url": success_url, "cancel_url": cancel_url,
        "customer_email": email, "metadata": _meta,
        "subscription_data": {"metadata": _meta},
    }


def cancel_at_saison(depuis, offre=None) -> int:
    """L'instant (epoch) où l'abonnement saison_2x s'arrête : début + 8 mois — deux factures, pas trois."""
    from dateutil.relativedelta import relativedelta
    _base = depuis or datetime.now(timezone.utc)
    if _base.tzinfo is None:
        _base = _base.replace(tzinfo=timezone.utc)
    # V535 : échéancier propre (M0 + M+n) -> début + 2n mois MOINS UN JOUR : la 2e
    # facture (M+n) passe, la 3e (M+2n) ne peut jamais être émise. Les offres
    # historiques gardent exactement début + 8 mois.
    if offre is not None and echeancier_personnalise(offre):
        _n = intervalle_echeances(offre)
        return int((_base + relativedelta(months=+(_n * SAISON_2X_ECHEANCES), days=-1)).timestamp())
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
    # V535 — échéancier propre (M0 + M+n) : la période Stripe de la 2e facture ne
    # couvre qu'un mois, mais les droits courent jusqu'à la FIN DE SAISON, comptée
    # depuis le premier paiement ; et seules les DEUX échéances créditent — une
    # facture de plus (qui ne devrait jamais exister : `cancel_at`) n'ouvre rien.
    if _doc.get(CHAMP_INTERVALLE):
        try:
            # `stripe_invoices` ne contient que les factures de RENOUVELLEMENT :
            # la première échéance (M0) est créditée par le checkout et n'y
            # figure jamais. Deux échéances = M0 + UNE facture de cycle.
            if len(list(_doc.get("stripe_invoices") or [])) >= SAISON_2X_ECHEANCES - 1:
                return {"credite": False, "motif": "echeancier_termine"}
            _debut = datetime.fromisoformat(str(_doc.get("saison_debut") or _doc.get("created_at")))
            if _debut.tzinfo is None:
                _debut = _debut.replace(tzinfo=timezone.utc)
            _exp_iso, _exp_jour = expiration_droits(_debut, SAISON_MOIS)
        except (TypeError, ValueError):
            _exp_iso, _exp_jour = expiration_droits(datetime.now(timezone.utc), SAISON_MOIS)
    _maintenant = datetime.now(timezone.utc).isoformat()
    # V527: QUOTA MENSUEL, PAS DE CUMUL. Pour un abonnement `mensuel_auto`, chaque
    # facture de cycle REMET les séances restantes au pack de l'offre (Flex 4 -> 4,
    # Fondateurs / Liberté / Étudiant -> 8) : les séances non utilisées du mois
    # précédent expirent au renouvellement. `total_sessions` reste le cumul
    # historique acheté (il continue de s'additionner). La saison en 2 paiements
    # garde son crédit saisonnier additif (pack × 4 par échéance) — inchangée.
    _remise_a_zero = billing_mode_valide(_doc.get("billing_mode")) == BILLING_MENSUEL
    _maj_sub = {"$inc": ({"total_sessions": _seances} if _remise_a_zero
                         else {"remaining_sessions": _seances, "total_sessions": _seances}),
                "$set": {"status": "active", "expires_at": _exp_iso, "updated_at": _maintenant,
                         "last_renewal_date": _maintenant, "paiement_echoue_le": None},
                "$addToSet": {"stripe_invoices": _iid},
                "$push": {"renewal_warnings_sent": "renewed_" + datetime.now(timezone.utc).strftime("%Y%m%d")}}
    if _remise_a_zero:
        _maj_sub["$set"]["remaining_sessions"] = _seances
    _r = await db.subscriptions.update_one(
        {"stripe_subscription_id": _sid, "stripe_invoices": {"$ne": _iid}}, _maj_sub)
    if not getattr(_r, "modified_count", 0):
        return {"credite": False, "motif": "facture_deja_creditee"}
    # Le code d'accès suit : même séances, même échéance. Idempotent par construction
    # (la souscription ne se met à jour qu'une fois par facture, donc on n'arrive ici qu'une fois).
    # V527: le solde CANONIQUE (LOT A) se lit `maxUses − used` sur `discount_codes` :
    # pour le mensuel, `maxUses` est reposé à `used + pack` (restant = pack), l'historique
    # des mouvements (`used`, `seance_mouvements`) n'est pas touché.
    try:
        if _remise_a_zero:
            _code_doc = await db.discount_codes.find_one({"code": _doc.get("code")}, {"_id": 0, "used": 1}) or {}
            try:
                _used = max(0, int(float(_code_doc.get("used") or 0)))
            except (TypeError, ValueError):
                _used = 0
            _maj_code = {"$set": {"maxUses": _used + _seances, "expiresAt": _exp_jour, "active": True},
                         "$addToSet": {"stripe_invoices": _iid}}
        else:
            _maj_code = {"$inc": {"maxUses": _seances}, "$set": {"expiresAt": _exp_jour, "active": True},
                         "$addToSet": {"stripe_invoices": _iid}}
        await db.discount_codes.update_one({"code": _doc.get("code"), "stripe_invoices": {"$ne": _iid}}, _maj_code)
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


def _jour_ch(iso) -> str:
    """JJ/MM/AAAA depuis un ISO, ou ""."""
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return ""


def abonnement_resiliable(subscription) -> tuple:
    """V527 — (True, "") si CE forfait est un abonnement mensuel Stripe encore actif ; sinon (False, motif).
    Seul `mensuel_auto` est concerné : la saison en 2 paiements a déjà son `cancel_at`."""
    _s = subscription or {}
    if not _s.get("stripe_subscription_id"):
        return False, "Ce forfait n'est pas un abonnement mensuel : rien à résilier."
    if billing_mode_valide(_s.get("billing_mode")) != BILLING_MENSUEL:
        return False, "Seul un abonnement mensuel se résilie ici."
    if str(_s.get("stripe_subscription_status") or "") == "canceled" or _s.get("status") != "active":
        return False, "Cet abonnement est déjà terminé."
    return True, ""


async def resilier_abonnement(db, subscription, modifier_stripe) -> dict:
    """V527 — RÉSILIER : `cancel_at_period_end=True` chez Stripe (aucun renouvellement futur),
    droits et séances CONSERVÉS jusqu'à `expires_at` (fin de la période déjà payée) ; la fin
    réelle arrive ensuite par `customer.subscription.deleted` -> `traiter_abonnement_termine`.
    `modifier_stripe(sid, **champs)` est injecté : le banc ne parle jamais à Stripe."""
    _ok, _motif = abonnement_resiliable(subscription)
    if not _ok:
        return {"ok": False, "motif": _motif}
    _sid = subscription["stripe_subscription_id"]
    modifier_stripe(_sid, cancel_at_period_end=True)
    _now = datetime.now(timezone.utc).isoformat()
    await db.subscriptions.update_one(
        {"stripe_subscription_id": _sid},
        {"$set": {"cancel_at_period_end": True, "resiliation_demandee_le": _now, "updated_at": _now}})
    logger.info("[HIVER] résiliation programmée : %s (accès jusqu'au %s)", _sid[:16], str(subscription.get("expires_at"))[:10])
    return {"ok": True, "motif": "", "cancel_at_period_end": True, "acces_jusquau": _jour_ch(subscription.get("expires_at"))}


async def reactiver_abonnement(db, subscription, modifier_stripe) -> dict:
    """V527 — RÉACTIVER avant la fin de période : `cancel_at_period_end=False`, l'abonnement continue."""
    _ok, _motif = abonnement_resiliable(subscription)
    if not _ok:
        return {"ok": False, "motif": _motif}
    _sid = subscription["stripe_subscription_id"]
    modifier_stripe(_sid, cancel_at_period_end=False)
    _now = datetime.now(timezone.utc).isoformat()
    await db.subscriptions.update_one(
        {"stripe_subscription_id": _sid},
        {"$set": {"cancel_at_period_end": False, "resiliation_demandee_le": None, "updated_at": _now}})
    logger.info("[HIVER] résiliation annulée : %s", _sid[:16])
    return {"ok": True, "motif": "", "cancel_at_period_end": False}


async def traiter_abonnement_mis_a_jour(db, subscription) -> dict:
    """V527 — `customer.subscription.updated` : ne reflète QUE `cancel_at_period_end`
    (une résiliation programmée ou annulée depuis Stripe). La fin réelle reste le seul
    chemin de `traiter_abonnement_termine` — rien n'est dupliqué ici."""
    _sid = str((subscription or {}).get("id") or "")
    if not _sid:
        return {"sync": False}
    _cape = bool((subscription or {}).get("cancel_at_period_end"))
    _now = datetime.now(timezone.utc).isoformat()
    # Ne réécrit que si l'état local diffère : une résiliation déjà enregistrée par la
    # route `/resilier` garde sa date d'origine.
    _r = await db.subscriptions.update_one(
        {"stripe_subscription_id": _sid, "cancel_at_period_end": {"$ne": _cape}},
        {"$set": {"cancel_at_period_end": _cape, "updated_at": _now,
                  "resiliation_demandee_le": (_now if _cape else None)}})
    return {"sync": bool(getattr(_r, "modified_count", 0)), "cancel_at_period_end": _cape}


def etat_abonnement(subscription) -> dict:
    """V527 — ce que l'espace abonné affiche : {recurrent, etat, libelle, acces_jusquau}."""
    _s = subscription or {}
    _rec = bool(_s.get("stripe_subscription_id")) and billing_mode_valide(_s.get("billing_mode")) == BILLING_MENSUEL
    _fin = _jour_ch(_s.get("expires_at"))
    if not _rec:
        return {"recurrent": False, "etat": "", "libelle": "", "acces_jusquau": _fin}
    if str(_s.get("stripe_subscription_status") or "") == "canceled":
        return {"recurrent": True, "etat": "termine", "libelle": "Abonnement terminé — accès jusqu'au %s" % _fin, "acces_jusquau": _fin}
    if _s.get("cancel_at_period_end"):
        return {"recurrent": True, "etat": "resiliation_programmee", "libelle": "Résiliation programmée — accès jusqu'au %s" % _fin, "acces_jusquau": _fin}
    return {"recurrent": True, "etat": "actif", "libelle": "Actif — prochaine échéance le %s" % _fin, "acces_jusquau": _fin}


MSG_DEJA_ABONNE = ("Tu as déjà cet abonnement actif : inutile de le souscrire une seconde fois. "
                   "Retrouve tes séances dans ton espace abonné.")


async def abonnement_actif_meme_offre(db, email, offre_id):
    """V526 : l'abonnement RÉCURRENT encore actif de `email` à `offre_id`, ou None.
    Actif = `status: active`, un `stripe_subscription_id`, non résilié
    (`stripe_subscription_status` ≠ canceled) et des droits non expirés."""
    from api.routes.shared import normaliser_email
    _e = normaliser_email(email)
    _o = str(offre_id or "").strip()
    if not _e or not _o:
        return None
    _now = datetime.now(timezone.utc).isoformat()
    return await db["subscriptions"].find_one(
        {"email": _e, "offer_id": _o, "status": "active",
         "stripe_subscription_id": {"$nin": [None, ""]},
         "stripe_subscription_status": {"$ne": "canceled"},
         "$or": [{"expires_at": {"$in": [None, ""]}}, {"expires_at": {"$gt": _now}}]},
        {"_id": 0, "id": 1, "code": 1, "expires_at": 1})


async def garde_abonnement_actif(db, email, offre) -> tuple:
    """V526 — ANTI-DOUBLE ABONNEMENT. (True, "") si `email` peut ouvrir un checkout
    pour cette offre ; (False, motif) s'il possède DÉJÀ cet abonnement récurrent actif.
    Ne concerne que les offres récurrentes (mensuel_auto / saison_2x) et la MÊME offre :
    une autre offre reste achetable. Sans e-mail connu (visiteur anonyme, l'adresse est
    saisie chez Stripe), la garde ne peut rien décider : fail-open. Fail-open aussi sur
    panne de lecture — une caisse ne se bloque pas sur un compteur muet."""
    _mode = billing_mode_valide((offre or {}).get("billing_mode"))
    if _mode not in (BILLING_MENSUEL, BILLING_SAISON_2X):
        return True, ""
    try:
        _d = await abonnement_actif_meme_offre(db, email, (offre or {}).get("id"))
        return (not _d), (MSG_DEJA_ABONNE if _d else "")
    except Exception as _err:  # noqa: BLE001
        logger.error("[HIVER] garde anti-double indisponible (%s) — achat poursuivi", type(_err).__name__)
        return True, ""


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
