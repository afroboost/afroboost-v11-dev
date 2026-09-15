# -*- coding: utf-8 -*-
"""RÉACTIVATION 3B — les règles PURES du pré-lancement (aucun envoi ici).

Ce module ne connaît ni Resend, ni Meta, ni le push : il DÉCIDE, il n'envoie
pas. Il est consommé par le moteur de campagne (`launch_campaign`), par la
prévisualisation (`/campaigns/{id}/preview`) et par les segments V363
(`contact_segments_routes`). Une seule définition de chaque règle :

  - SEGMENTS de réactivation (lus sur l'historique client d'une personne) ;
  - CLIENT ACTIF (jamais réactivé commercialement) ;
  - DONNÉE DE TEST (jamais ciblée, jamais supprimée) ;
  - CLÉ D'IDEMPOTENCE (une personne + une campagne + un canal = un envoi) ;
  - LIEN de réactivation avec sa nomenclature UTM (tracking 2B inchangé).

« Présence inconnue » n'est JAMAIS un no-show : `absence_marked_at` est trop
peu renseigné (audit du 15/09/2026 : 0 absence déclarée). Le segment
`essai_non_converti` compte les essais PRÉSENTS ; les essais réservés sans
scan restent à part (`essai_presence_inconnue`), jamais fusionnés.
"""
import re
from datetime import datetime, timezone, timedelta

SEGMENTS_REACTIVATION = (
    "essai_non_converti",      # essai accordé, PRÉSENCE confirmée, aucun achat ensuite
    "essai_presence_inconnue", # essai réservé, ni scan ni absence déclarée (C2, à part)
    "essai_non_reserve",       # essai accordé, jamais réservé
    "ancien_participant",      # ≥ 1 réservation de cours (hors essai), sans droit actif
    "ancien_abonne",           # ≥ 1 abonnement / pack payé (Pulse, Abonnement, Bassboost…), inactif
    "recent_non_abonne",       # dernière activité ≤ 60 j, avec historique, sans droit actif
)
LIBELLES = {
    "essai_non_converti": "Essais présents non convertis",
    "essai_presence_inconnue": "Essais réservés, présence inconnue",
    "essai_non_reserve": "Essais jamais réservés",
    "ancien_participant": "Anciens participants",
    "ancien_abonne": "Anciens abonnés / packs",
    "recent_non_abonne": "Récents non abonnés",
}
RECENT_JOURS = 60

# Données de test : jamais ciblées (jamais supprimées non plus).
RX_TEST_EMAIL = re.compile(r"(example\.com|@test\b|test@|\.test$|playboot\.com|mailinator|yopmail|tempmail|guerrilla|@afroboost\.test|sonde)", re.I)
RX_TEST_NOM = re.compile(r"\b(test|sonde|xtrem)\b", re.I)
RX_ESSAI = re.compile(r"essai|gratuit", re.I)
RX_ABO = re.compile(r"abonn|pulse|bassboost|membres|saison|mensuel|fondateur|flex|tudiant", re.I)
RX_EVENEMENT = re.compile(r"festival|lakeside|sunset|silent disco|lausanne|dîner|diner|silent avec bassi|billet", re.I)

UTM_SOURCE_EMAIL = "email"
UTM_MEDIUM = "reactivation"
UTM_CAMPAGNE_DEFAUT = "hiver2026"
BASE_DEFAUT = "https://afroboost.com"


def _texte(v):
    return str(v or "").strip()


def _dt(v):
    if not v:
        return None
    try:
        s = _texte(v).replace("Z", "+00:00")
        d = datetime.fromisoformat(s if "T" in s else s + "T00:00:00")
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def est_donnee_test(email, nom="") -> bool:
    e = _texte(email).lower()
    return bool(e and RX_TEST_EMAIL.search(e)) or bool(RX_TEST_NOM.search(_texte(nom)))


def est_essai(sub) -> bool:
    s = sub or {}
    return bool(RX_ESSAI.search(_texte(s.get("offer_name")))) or _texte(s.get("origine_paiement")).lower() == "offert"


def est_droit_actif(sub, maintenant=None) -> bool:
    """Un droit ACTIF = souscription `active`, non essai, non expirée, avec des
    séances restantes (ou un cycle récurrent : mensuel / saison 2×)."""
    s = sub or {}
    maintenant = maintenant or datetime.now(timezone.utc)
    if _texte(s.get("status")).lower() != "active" or est_essai(s):
        return False
    exp = _dt(s.get("expires_at"))
    if exp is not None and exp < maintenant:
        return False
    if s.get("billing_mode") in ("mensuel_auto", "saison_2x"):
        return True
    restantes = s.get("remaining_sessions")
    try:
        return restantes is None or float(restantes) > 0
    except (TypeError, ValueError):
        return True


def est_client_actif(subs, maintenant=None) -> bool:
    return any(est_droit_actif(s, maintenant) for s in (subs or []))


def classer_personne(dossier, maintenant=None) -> set:
    """Les segments de réactivation d'UNE personne, depuis son dossier :
    {resas: [...], subs: [...], pays: [...], dernier_contact: datetime|None}.
    Une personne active ou de test n'a AUCUN segment (exclue en amont)."""
    maintenant = maintenant or datetime.now(timezone.utc)
    d = dossier or {}
    subs = [s for s in (d.get("subs") or []) if isinstance(s, dict) and _texte(s.get("status")).lower() != "superseded"]
    resas = [r for r in (d.get("resas") or []) if isinstance(r, dict) and not r.get("isProduct")]
    pays = [p for p in (d.get("pays") or []) if isinstance(p, dict) and _texte(p.get("payment_status")) == "paid"
            and float(p.get("amount_total") or p.get("amount") or 0) > 0]
    if est_client_actif(subs, maintenant):
        return set()
    essais = [s for s in subs if est_essai(s)]
    payes = [s for s in subs if not est_essai(s)]
    cles_essai = {_texte(s.get("code")).upper() for s in essais} | {_texte(s.get("id")) for s in essais}
    cles_essai.discard("")
    resas_essai = [r for r in resas if _texte(r.get("discountCode")).upper() in cles_essai or _texte(r.get("subscriptionId")) in cles_essai]
    resas_cours = [r for r in resas if r not in resas_essai and not RX_EVENEMENT.search(_texte(r.get("courseName")))]
    segments = set()
    if essais:
        d0 = min((x for x in (_dt(s.get("created_at")) for s in essais) if x), default=None)
        achat_apres = any(s.get("converted_at") for s in essais) or any(
            (x or maintenant) > (d0 or maintenant) for x in ([_dt(s.get("created_at")) for s in payes] + [_dt(p.get("created_at")) for p in pays]))
        present = any(r.get("validated") is True for r in resas_essai)
        absent = any(r.get("absence_marked_at") for r in resas_essai)
        if present and not achat_apres:
            segments.add("essai_non_converti")
        elif resas_essai and not present and not absent and not achat_apres:
            segments.add("essai_presence_inconnue")
        elif not resas_essai and not achat_apres:
            segments.add("essai_non_reserve")
    if resas_cours:
        segments.add("ancien_participant")
    if any(RX_ABO.search(_texte(s.get("offer_name"))) for s in payes):
        segments.add("ancien_abonne")
    dates = [x for x in ([_dt(r.get("datetime")) or _dt(r.get("createdAt")) for r in resas] + [_dt(s.get("created_at")) for s in subs]
                         + [_dt(p.get("created_at")) for p in pays] + [d.get("dernier_contact")]) if x]
    derniere = max(dates) if dates else None
    if derniere and (resas or subs or pays) and (maintenant - derniere) <= timedelta(days=RECENT_JOURS):
        segments.add("recent_non_abonne")
    return segments


def derniere_activite(dossier):
    d = dossier or {}
    dates = [x for x in ([_dt(r.get("datetime")) or _dt(r.get("createdAt")) for r in (d.get("resas") or [])]
                         + [_dt(s.get("created_at")) for s in (d.get("subs") or [])]
                         + [_dt(p.get("created_at")) for p in (d.get("pays") or [])] + [d.get("dernier_contact")]) if x]
    return max(dates) if dates else None


def cle_idempotence(campaign_id, canal, valeur_normalisee) -> str:
    """UNE personne + UNE campagne + UN canal = UN envoi. La clé vit dans
    `campaigns.results[].cle` ; un retry technique la retrouve et n'envoie pas."""
    return "%s|%s|%s" % (_texte(campaign_id), _texte(canal).lower(), _texte(valeur_normalisee).lower())


def deja_envoye(results, cle) -> bool:
    for r in results or []:
        if isinstance(r, dict) and r.get("cle") == cle and r.get("status") == "sent":
            return True
    return False


def masquer_email(email) -> str:
    e = _texte(email).lower()
    if "@" not in e:
        return ""
    nom, dom = e.split("@", 1)
    return (nom[:2] + "…" if len(nom) > 2 else nom[:1] + "…") + "@" + dom


def lien_reactivation(segment, campagne=UTM_CAMPAGNE_DEFAUT, base=BASE_DEFAUT, chemin="/", source=UTM_SOURCE_EMAIL) -> str:
    """Le lien d'une campagne de réactivation : nomenclature UTM fixe, `utm_content`
    = le segment. Le tracking 2B (first/last, héritage) fait le reste : la
    first-touch historique n'est jamais écrasée, la campagne se lit en `last`."""
    seg = re.sub(r"[^a-z0-9_-]", "", _texte(segment).lower())[:64]
    camp = re.sub(r"[^a-z0-9_-]", "", _texte(campagne).lower())[:64] or UTM_CAMPAGNE_DEFAUT
    src = re.sub(r"[^a-z0-9_-]", "", _texte(source).lower())[:32] or UTM_SOURCE_EMAIL
    parties = ["utm_source=%s" % src, "utm_medium=%s" % UTM_MEDIUM, "utm_campaign=%s" % camp]
    if seg:
        parties.append("utm_content=%s" % seg)
    return base.rstrip("/") + (chemin or "/") + "?" + "&".join(parties)
