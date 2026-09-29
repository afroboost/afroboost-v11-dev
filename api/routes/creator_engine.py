# -*- coding: utf-8 -*-
"""V559 — PROGRAMME CRÉATEUR / AFFILIATION : LES RÈGLES PURES.

Aucun accès base, aucun réseau : tout ce qui décide (qui est créateur, combien
rapporte un achat, quand une commission devient payable, ce que le créateur a
le droit de voir) vit ici et se prouve sans serveur (tests/test_createur.py).

LE MÊME MOTEUR QUE L'INVITATION ET LE PARRAINAGE, PAS UN SECOND :
  * les programmes d'affiliation sont des documents `referral_programs`
    (`type: "affiliation"`) — la collection que V558 lit déjà pour décider si
    la carte « Affiliation » existe (`referral_engine.programme_valide`) ;
  * les filleuls sont lus dans `referral_passes` (la chaîne A→B→C) ;
  * l'origine d'un achat voyage avec l'attribution M2-A existante.

LES QUATRE RÈGLES QUI NE BOUGENT PAS :
  1. COMMISSION DIRECTE UNIQUEMENT : seul l'apporteur direct de l'achat (son
     lien créateur, sinon le parrain DIRECT de l'invitation que l'acheteur a
     rejointe) peut être rémunéré. Jamais son propre parrain : aucune pyramide.
  2. UNE CONVERSION = UN PAIEMENT CONFIRMÉ PAR LE SERVEUR (webhook Stripe
     `paid`). Jamais un clic, une ouverture, une inscription, un partage, un
     essai gratuit (montant 0).
  3. UN PAIEMENT = UNE COMMISSION AU PLUS (clé unique `cle_paiement`).
  4. L'ESSAI GRATUIT RESTE UNE FOIS PAR PERSONNE : ce module n'en octroie
     jamais — il ne fait que compter de l'argent.
"""
import re
from datetime import datetime, timedelta, timezone

STATUTS_CREATEUR = ("pending", "approved", "rejected", "suspended")
DECISIONS = {"approve": "approved", "reject": "rejected", "suspend": "suspended", "reactivate": "approved"}
STATUTS_COMMISSION = ("pending", "confirmed", "paid", "cancelled", "refunded")
STATUTS_RETRAIT = ("pending", "approved", "paid", "rejected")
DECISIONS_RETRAIT = {"approve": "approved", "pay": "paid", "reject": "rejected"}
METHODES_PAIEMENT = ("twint", "iban")
REWARD_TYPES_AFFILIATION = ("fixed_amount", "percentage")

# Une commission reste « en attente » pendant le délai de rétractation / de
# remboursement ; ensuite elle devient « confirmée » et entre dans le solde.
DELAI_CONFIRMATION_JOURS = 14
RETRAIT_MIN_CHF = 10.0
# L'invitation rejointe ne désigne un créateur que pendant ce délai.
FENETRE_INVITATION_JOURS = 180

NOM_MAX = 60
RESEAUX_MAX = 200
MOTIVATION_MAX = 600
LISTE_MAX = 50
MOTIF_JETON = re.compile(r"^[A-Za-z0-9_-]{8,40}$")

LIBELLES_STATUT_COMMISSION = {"pending": "En attente", "confirmed": "Confirmée", "paid": "Payée",
                              "cancelled": "Annulée", "refunded": "Remboursée"}
LIBELLES_STATUT_RETRAIT = {"pending": "Demandé", "approved": "Accepté", "paid": "Payé", "rejected": "Refusé"}


class DemandeInvalide(ValueError):
    """Une demande créateur (ou un programme) refusée AVANT toute écriture."""


def maintenant():
    return datetime.now(timezone.utc)


def iso(dt=None):
    return (dt or maintenant()).isoformat()


def instant(valeur):
    """Un datetime aware depuis une ISO, sinon None."""
    if isinstance(valeur, datetime):
        return valeur if valeur.tzinfo else valeur.replace(tzinfo=timezone.utc)
    try:
        _d = datetime.fromisoformat(str(valeur or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return _d if _d.tzinfo else _d.replace(tzinfo=timezone.utc)


def normaliser_email(email) -> str:
    return str(email or "").strip().lower()


def arrondi(montant) -> float:
    try:
        return round(float(montant) + 1e-9, 2)
    except (TypeError, ValueError):
        return 0.0


def prenom(nom) -> str:
    """Le premier mot d'un nom, jamais une adresse e-mail."""
    _n = str(nom or "").strip()
    if not _n or "@" in _n:
        return ""
    return _n.split()[0][:30]


# ─── Demande « Devenir créateur » ─────────────────────────────────────────────
def _texte(corps, cle, maxi, requis=False, libelle=""):
    _v = str((corps or {}).get(cle) or "").strip()
    if requis and not _v:
        raise DemandeInvalide("%s requis." % (libelle or cle))
    if len(_v) > maxi:
        raise DemandeInvalide("%s : %d caractères au plus." % (libelle or cle, maxi))
    if "<" in _v or ">" in _v:
        raise DemandeInvalide("%s : caractères < et > interdits." % (libelle or cle))
    return _v


def telephone_valide(tel) -> str:
    """« +41 79 123 45 67 » → « +41791234567 » ; "" si illisible (8 à 15 chiffres)."""
    _brut = str(tel or "").strip()
    _chiffres = "".join(c for c in _brut if c.isdigit())
    if _brut.startswith("00"):
        _chiffres = _chiffres[2:]
    elif _brut.startswith("0") and not _brut.startswith("00"):
        _chiffres = "41" + _chiffres[1:]          # numéro suisse local
    if not 8 <= len(_chiffres) <= 15:
        return ""
    return "+" + _chiffres


def iban_valide(iban) -> str:
    """L'IBAN compacté en majuscules si la clé mod-97 est juste, sinon ""."""
    _i = re.sub(r"\s+", "", str(iban or "")).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", _i):
        return ""
    _r = _i[4:] + _i[:4]
    _n = "".join(str(int(c, 36)) for c in _r)
    return _i if int(_n) % 97 == 1 else ""


def valider_demande(corps) -> dict:
    """Les champs de la demande, normalisés. L'e-mail n'est JAMAIS lu ici : il
    vient de l'identité serveur (espace abonné ou jeton coach)."""
    _c = corps if isinstance(corps, dict) else {}
    _methode = str(_c.get("payout_method") or "").strip().lower()
    if _methode not in METHODES_PAIEMENT:
        raise DemandeInvalide("Méthode de paiement : TWINT ou IBAN.")
    _tel = telephone_valide(_c.get("telephone"))
    if not _tel:
        raise DemandeInvalide("Numéro de téléphone invalide (ex. +41 79 123 45 67).")
    _detail = str(_c.get("payout_detail") or "").strip()
    if _methode == "twint":
        _detail = telephone_valide(_detail or _c.get("telephone"))
        if not _detail:
            raise DemandeInvalide("Numéro TWINT invalide.")
    else:
        _detail = iban_valide(_detail)
        if not _detail:
            raise DemandeInvalide("IBAN invalide : vérifie-le.")
    return {
        "prenom": _texte(_c, "prenom", NOM_MAX, True, "Prénom"),
        "nom": _texte(_c, "nom", NOM_MAX, True, "Nom"),
        "telephone": _tel,
        "reseaux": _texte(_c, "reseaux", RESEAUX_MAX, False, "Réseaux sociaux"),
        "motivation": _texte(_c, "motivation", MOTIVATION_MAX, True, "Motivation / activité"),
        "payout_method": _methode,
        "payout_detail": _detail,
        "reglement_accepte": _c.get("reglement_accepte") is True,
    }


def masquer_detail(methode, detail) -> str:
    """Ce que l'écran montre du moyen de paiement : jamais le numéro entier."""
    _d = str(detail or "")
    if not _d:
        return ""
    if methode == "iban":
        return "%s •••• %s" % (_d[:4], _d[-4:])
    return "•••• %s" % _d[-4:]


def decision_autorisee(statut_actuel, decision) -> str:
    """Le nouveau statut, sinon "" (transition interdite)."""
    _cible = DECISIONS.get(str(decision or ""))
    if not _cible:
        return ""
    _permis = {
        "approve": ("pending", "rejected"),
        "reject": ("pending",),
        "suspend": ("approved",),
        "reactivate": ("suspended",),
    }[decision]
    return _cible if statut_actuel in _permis else ""


def jeton_valide(jeton) -> bool:
    return bool(MOTIF_JETON.match(str(jeton or "")))


def lien_createur(frontend_url, jeton) -> str:
    return "%s/?createur=%s" % (str(frontend_url or "https://afroboost.com").rstrip("/"), jeton)


def lien_partage(frontend_url, jeton) -> str:
    """La page d'aperçu (OG + carte) qui renvoie aussitôt vers le lien créateur."""
    return "%s/api/createur/partage/%s" % (str(frontend_url or "https://afroboost.com").rstrip("/"), jeton)


# ─── Programmes d'affiliation (referral_programs, type « affiliation ») ───────
def valider_programme(corps) -> dict:
    """Un programme d'affiliation : UNE offre, UNE règle. Le montant est fixé
    par le super-admin, jamais par le créateur."""
    _c = corps if isinstance(corps, dict) else {}
    _type = str(_c.get("reward_type") or "").strip()
    if _type not in REWARD_TYPES_AFFILIATION:
        raise DemandeInvalide("Type de commission : fixed_amount ou percentage.")
    try:
        _v = float(_c.get("reward_value"))
    except (TypeError, ValueError):
        raise DemandeInvalide("Valeur de commission invalide.")
    if _v <= 0 or (_type == "percentage" and _v > 100) or _v > 10000:
        raise DemandeInvalide("Valeur de commission hors limites.")
    _oid = str(_c.get("offer_id") or "").strip()
    if not _oid or len(_oid) > 64:
        raise DemandeInvalide("Choisis l'offre du programme.")
    _statut = str(_c.get("status") or "active").strip()
    if _statut not in ("active", "inactive"):
        raise DemandeInvalide("Statut : active ou inactive.")
    return {"name": _texte(_c, "name", 80, True, "Nom du programme"), "offer_id": _oid,
            "reward_type": _type, "reward_value": arrondi(_v), "status": _statut}


def commission_pour(programmes, offer_id, montant):
    """`(montant_commission, programme)` pour cet achat, sinon (0.0, None).

    Un programme actif d'affiliation PAR OFFRE ; le premier qui correspond
    l'emporte (ordre de création). Pourcentage arrondi au centime ; un montant
    fixe ne dépasse jamais le prix payé."""
    _m = arrondi(montant)
    if _m <= 0:
        return 0.0, None
    for _p in (programmes or []):
        if not isinstance(_p, dict) or _p.get("type") != "affiliation" or _p.get("status") != "active":
            continue
        if str(_p.get("offer_id") or "") != str(offer_id or ""):
            continue
        _v = arrondi(_p.get("reward_value"))
        if _v <= 0:
            continue
        if _p.get("reward_type") == "percentage":
            _c = arrondi(_m * _v / 100.0)
        elif _p.get("reward_type") == "fixed_amount":
            _c = min(_v, _m)
        else:
            continue
        if _c > 0:
            return _c, _p
    return 0.0, None


def libelle_programme(programme) -> str:
    """« Pulse X10 : 15 CHF » / « Événement : 10 % »."""
    _p = programme or {}
    _nom = str(_p.get("offer_name") or _p.get("name") or "Offre")
    _v = arrondi(_p.get("reward_value"))
    _txt = ("%g %%" % _v) if _p.get("reward_type") == "percentage" else ("%.2f CHF" % _v)
    return "%s : %s" % (_nom, _txt)


# ─── Attribution d'un achat : l'apporteur DIRECT, jamais une pyramide ─────────
def choisir_createur(createur_lien, createur_invitation, email_acheteur):
    """Le créateur à rémunérer, ou None.

    1. le lien créateur explicite (dernier clic) ;
    2. sinon le parrain DIRECT de l'invitation rejointe par l'acheteur.
    Jamais l'acheteur lui-même ; jamais un créateur non approuvé. Le parrain du
    parrain n'est JAMAIS consulté : il n'y a pas de second niveau."""
    _email = normaliser_email(email_acheteur)
    for _c in (createur_lien, createur_invitation):
        if not isinstance(_c, dict) or _c.get("status") != "approved":
            continue
        if normaliser_email(_c.get("email")) == _email:
            continue
        return _c
    return None


def cle_paiement(source, order_id) -> str:
    """LA clé d'unicité : une session Stripe (ou une transaction vitrine) ne
    produit JAMAIS deux commissions, même si le webhook est rejoué."""
    return "%s:%s" % (str(source or "stripe"), str(order_id or ""))


def nouvelle_commission(*, createur, programme, commission, cle, email_acheteur, nom_acheteur, offer_id,
                        offer_name, montant, devise, order_id, payment_id, origine, referral_id=None,
                        campaign_id=None, quand=None) -> dict:
    import uuid
    _q = quand or maintenant()
    return {
        "id": str(uuid.uuid4()),
        "cle_paiement": cle,
        "creator_id": createur.get("id"),
        "creator_email": normaliser_email(createur.get("email")),
        "programme_id": (programme or {}).get("id"),
        "referral_id": referral_id,
        "campaign_id": campaign_id,
        "buyer_id": normaliser_email(email_acheteur),
        "buyer_prenom": prenom(nom_acheteur),
        "offer_id": str(offer_id or ""),
        "offer_name": str(offer_name or "")[:120],
        "order_id": str(order_id or ""),
        "payment_id": str(payment_id or "") or None,
        "gross_amount": arrondi(montant),
        "commission_amount": arrondi(commission),
        "currency": str(devise or "CHF").upper()[:3],
        "status": "pending",
        "origine": origine,
        "created_at": iso(_q),
        "confirmable_at": iso(_q + timedelta(days=DELAI_CONFIRMATION_JOURS)),
        "history": [{"at": iso(_q), "status": "pending", "motif": "conversion"}],
    }


def a_confirmer(commission, now=None) -> bool:
    """Une commission `pending` dont le délai est passé devient `confirmed`."""
    _c = commission or {}
    if _c.get("status") != "pending":
        return False
    _t = instant(_c.get("confirmable_at"))
    return bool(_t and _t <= (now or maintenant()))


def statut_effectif(commission, now=None) -> str:
    return "confirmed" if a_confirmer(commission, now) else str((commission or {}).get("status") or "pending")


def kpis(commissions, nb_filleuls, now=None) -> dict:
    """Les 4 cartes + le solde. Convention : GAINS TOTAUX = confirmées + payées ;
    EN ATTENTE = pas encore confirmées ; SOLDE = confirmées, non encore demandées
    ni payées ; ACHATS = conversions payées non annulées ni remboursées."""
    _tot = _att = _solde = 0.0
    _achats = 0
    for _c in (commissions or []):
        _s = statut_effectif(_c, now)
        _m = arrondi(_c.get("commission_amount"))
        if _s in ("pending", "confirmed", "paid"):
            _achats += 1
        if _s == "pending":
            _att += _m
        elif _s in ("confirmed", "paid"):
            _tot += _m
            if _s == "confirmed" and not _c.get("payout_request_id"):
                _solde += _m
    return {"gains_totaux": arrondi(_tot), "en_attente": arrondi(_att), "solde": arrondi(_solde),
            "achats": _achats, "filleuls": int(nb_filleuls or 0)}


def dto_conversion(commission, now=None) -> dict:
    """Ce que le créateur voit d'une conversion : jamais l'acheteur."""
    _c = commission or {}
    _s = statut_effectif(_c, now)
    return {"id": _c.get("id"), "date": _c.get("created_at"), "offre": _c.get("offer_name") or "Offre",
            "montant": arrondi(_c.get("gross_amount")), "commission": arrondi(_c.get("commission_amount")),
            "devise": _c.get("currency") or "CHF", "statut": _s,
            "statut_libelle": LIBELLES_STATUT_COMMISSION.get(_s, _s)}


STATUTS_FILLEUL = ("Invité", "Inscrit", "Premier essai", "Client", "Achat confirmé")


def dto_filleul(prenom_filleul, date, origine, statut) -> dict:
    """Prénom, date, origine, statut — rien d'autre (ni e-mail, ni téléphone)."""
    return {"prenom": prenom(prenom_filleul) or "Ami", "date": date,
            "origine": origine, "statut": statut if statut in STATUTS_FILLEUL else "Inscrit"}


def dto_retrait(r) -> dict:
    _r = r or {}
    return {"id": _r.get("id"), "montant": arrondi(_r.get("amount")), "statut": _r.get("status"),
            "statut_libelle": LIBELLES_STATUT_RETRAIT.get(_r.get("status"), _r.get("status")),
            "methode": _r.get("payment_method"), "date": _r.get("created_at"),
            "traite_le": _r.get("processed_at")}
