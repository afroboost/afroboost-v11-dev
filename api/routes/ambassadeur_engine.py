# -*- coding: utf-8 -*-
"""V610o — PROGRAMME AMBASSADEUR AFROBOOST : LES RÈGLES PURES (aucun accès base).

PAS UN SECOND SYSTÈME DE PARRAINAGE : un Boost se lit sur la chaîne EXISTANTE des
événements (`invitation_relais`, V607 : parent direct / racine / génération). Il naît
quand le relais d'un FILLEUL est créé — c'est-à-dire quand sa place est CONFIRMÉE
(paiement `paid` vérifié par le webhook, place offerte réservée, inscription confirmée)
— et revient au parrain DIRECT seulement (jamais à toute la chaîne ascendante).

LES RÈGLES QUI NE BOUGENT PAS :
  1. 1 filleul distinct + 1 place confirmée = 1 Boost au parrain direct. Jamais un
     clic, une page vue, un WhatsApp ouvert, un lien créé, un paiement échoué.
  2. Clé unique `boost:<relais du filleul>` : double webhook, double clic, refresh,
     autre appareil -> toujours le MÊME Boost. Une personne = un relais par
     invitation (V607) -> un filleul ne rapporte qu'une fois par événement.
  3. Auto-parrainage (même e-mail que le parent) -> aucun Boost (relais non attribué).
  4. Annulation / remboursement -> Boost RÉVOQUÉ (statut + historique), jamais effacé.
  5. Les Boosts se CUMULENT : franchir 3 ne remet rien à zéro ; un palier franchi est
     historisé ; une récompense déjà remise n'est jamais retirée — signalée au coach.
  6. Aucune remise financière, aucun avantage filleul actif (préparé, désactivé).
  7. « 50 PLACES » est un MESSAGE : aucune capacité technique n'en découle.
"""
import re

EVENEMENT_ACCORDE = "BOOST_GRANTED"
EVENEMENT_REVOQUE = "BOOST_REVOKED"
STATUT_ACCORDE = "granted"
STATUT_REVOQUE = "revoked"

RAISONS_REVOCATION = ("remboursement_stripe", "reservation_annulee", "action_coach")

# Paliers initiaux (modifiables par le coach ; ces valeurs restent les valeurs de départ).
PALIERS_DEFAUT = (
    {"cle": "pass_ami", "seuil": 3, "libelle": "Pass Ami"},
    {"cle": "recompense", "seuil": 5, "libelle": "Récompense Afroboost"},
    {"cle": "vip", "seuil": 10, "libelle": "Ambassadeur VIP"},
)
CLES_PALIERS = tuple(p["cle"] for p in PALIERS_DEFAUT)
MESSAGE_PLACES_DEFAUT = "50 PLACES"
TYPES_AVANTAGE_FILLEUL = ("pourcentage", "montant_fixe", "tarif_special")

# États d'une récompense débloquée (par palier).
#   Pass Ami : disponible -> utilise ; Récompense : a_remettre -> remise ; VIP : actif.
ETATS_INITIAUX = {"pass_ami": "disponible", "recompense": "a_remettre", "vip": "actif"}
TRANSITIONS = {
    "pass_ami": {"utilise": "utilise", "disponible": "disponible"},
    "recompense": {"remise": "remise", "a_remettre": "a_remettre"},
    "vip": {},
}
ETATS_DONNES = {"utilise", "remise"}           # récompense déjà profitée : jamais retirée

LIBELLE_MAX = 40
SEUIL_MAX = 500
MESSAGE_PLACES_MAX = 30
RE_ID = re.compile(r"^[A-Za-z0-9_-]{4,80}$")


class ConfigInvalide(ValueError):
    """Une configuration refusée AVANT toute écriture."""


def cle_boost(relais_filleul_id) -> str:
    return "boost:%s" % str(relais_filleul_id or "")


def peut_accorder(relais_filleul) -> bool:
    """Un relais de filleul ouvre-t-il un Boost ? Seulement s'il est ATTRIBUÉ à un
    parent qui est lui-même un participant (relais), sans auto-invitation. L'invitation
    du coach (racine) n'est pas un ambassadeur : ses filleuls directs ne font gagner
    personne (génération 1)."""
    _r = relais_filleul if isinstance(relais_filleul, dict) else {}
    return bool(_r.get("id") and _r.get("parent_relais_id") and not _r.get("auto_invitation"))


def _paliers_normalises(paliers):
    """Trois paliers, clés fixes, seuils strictement croissants, libellés propres."""
    _par_cle = {p.get("cle"): p for p in (paliers or []) if isinstance(p, dict)}
    _sortie = []
    for _defaut in PALIERS_DEFAUT:
        _p = _par_cle.get(_defaut["cle"]) or {}
        try:
            _s = int(_p.get("seuil", _defaut["seuil"]))
        except (TypeError, ValueError):
            raise ConfigInvalide("seuil invalide pour %s" % _defaut["cle"])
        if _s < 1 or _s > SEUIL_MAX:
            raise ConfigInvalide("seuil hors limites pour %s (1 à %d)" % (_defaut["cle"], SEUIL_MAX))
        _l = re.sub(r"\s+", " ", str(_p.get("libelle") or _defaut["libelle"])).strip()[:LIBELLE_MAX] or _defaut["libelle"]
        _sortie.append({"cle": _defaut["cle"], "seuil": _s, "libelle": _l})
    if not (_sortie[0]["seuil"] < _sortie[1]["seuil"] < _sortie[2]["seuil"]):
        raise ConfigInvalide("les seuils doivent être croissants (ex. 3, 5, 10)")
    return _sortie


def config_defaut() -> dict:
    return {"paliers": [dict(p) for p in PALIERS_DEFAUT], "message_places": MESSAGE_PLACES_DEFAUT,
            "pass_ami": {"activites": [], "expire_le": None},
            "avantage_filleul": {"actif": False, "type": None, "valeur": None}}


def config_valide(doc) -> dict:
    """La configuration du coach normalisée ; absente / illisible -> valeurs initiales.
    L'avantage filleul reste DÉSACTIVÉ dans cette version (préparé, jamais appliqué)."""
    _d = doc if isinstance(doc, dict) else {}
    _c = config_defaut()
    try:
        _c["paliers"] = _paliers_normalises(_d.get("paliers") or PALIERS_DEFAUT)
    except ConfigInvalide:
        _c["paliers"] = [dict(p) for p in PALIERS_DEFAUT]
    _m = re.sub(r"\s+", " ", str(_d.get("message_places") if _d.get("message_places") is not None else MESSAGE_PLACES_DEFAUT)).strip()
    _c["message_places"] = _m[:MESSAGE_PLACES_MAX]
    _pa = _d.get("pass_ami") if isinstance(_d.get("pass_ami"), dict) else {}
    _c["pass_ami"] = {"activites": [str(a) for a in (_pa.get("activites") or []) if RE_ID.match(str(a))][:50],
                      "expire_le": str(_pa.get("expire_le"))[:10] if re.match(r"^\d{4}-\d{2}-\d{2}$", str(_pa.get("expire_le") or "")) else None}
    _af = _d.get("avantage_filleul") if isinstance(_d.get("avantage_filleul"), dict) else {}
    _type = _af.get("type") if _af.get("type") in TYPES_AVANTAGE_FILLEUL else None
    try:
        _val = float(_af.get("valeur")) if _af.get("valeur") not in (None, "") else None
    except (TypeError, ValueError):
        _val = None
    _c["avantage_filleul"] = {"actif": False, "type": _type, "valeur": _val}
    return _c


def config_depuis_saisie(corps, existante=None) -> dict:
    """La saisie du coach -> configuration (lève ConfigInvalide)."""
    _b = corps if isinstance(corps, dict) else {}
    _base = config_valide(existante)
    _brut = dict(_base)
    if "paliers" in _b:
        _brut["paliers"] = _paliers_normalises(_b.get("paliers"))
    for _k in ("message_places", "pass_ami", "avantage_filleul"):
        if _k in _b:
            _brut[_k] = _b[_k]
    _sortie = config_valide(_brut)
    _sortie["paliers"] = _brut["paliers"] if "paliers" in _b else _base["paliers"]
    return _sortie


def progression(boosts, paliers=None) -> dict:
    """Le compteur CUMULÉ et le prochain palier : {boosts, debloques, prochain, vip}."""
    _n = max(0, int(boosts or 0))
    _p = list(paliers or PALIERS_DEFAUT)
    _debloques = [x["cle"] for x in _p if _n >= int(x["seuil"])]
    _suivant = next((x for x in _p if _n < int(x["seuil"])), None)
    return {
        "boosts": _n,
        "debloques": _debloques,
        "prochain": ({"cle": _suivant["cle"], "seuil": int(_suivant["seuil"]), "libelle": _suivant["libelle"],
                      "restant": int(_suivant["seuil"]) - _n} if _suivant else None),
        "vip": "vip" in _debloques,
    }


def paliers_franchis(avant, apres, paliers=None) -> list:
    """Les paliers franchis en passant de `avant` à `apres` Boosts (montée seulement)."""
    _p = list(paliers or PALIERS_DEFAUT)
    return [x for x in _p if int(avant or 0) < int(x["seuil"]) <= int(apres or 0)]


def paliers_perdus(avant, apres, paliers=None) -> list:
    """Les paliers repassés SOUS le seuil (descente après une révocation)."""
    _p = list(paliers or PALIERS_DEFAUT)
    return [x for x in _p if int(apres or 0) < int(x["seuil"]) <= int(avant or 0)]


def transition_recompense(cle_palier, etat_actuel, demande):
    """Le nouvel état d'une récompense, ou None si la demande ne vaut rien ici."""
    _t = TRANSITIONS.get(cle_palier) or {}
    _n = _t.get(demande)
    return _n if _n and _n != etat_actuel else None


def libelle_etat(cle_palier, etat) -> str:
    return {"disponible": "Disponible", "utilise": "Utilisé", "a_remettre": "À remettre",
            "remise": "Remise", "actif": "Actif"}.get(etat, etat or "")


def ville(lieu) -> str:
    """« Chemin des Valangines 97, 2000 Neuchâtel » -> « Neuchâtel » ; sinon le lieu."""
    _l = str(lieu or "").strip()
    _m = re.search(r"\b\d{4}\s+([^,\d][^,]*)$", _l)
    return _m.group(1).strip() if _m else _l
