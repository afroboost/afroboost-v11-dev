# -*- coding: utf-8 -*-
"""ANALYTICS PHASE 4 — LA CLÔTURE MENSUELLE : figer un bilan Association.

PREMIÈRE ÉCRITURE D'ANALYTICS, et la seule : UNE collection dédiée,
`analytics_monthly_reports`, qui ne contient que des bilans AGRÉGÉS (la
projection Association de la phase 3, telle quelle). Aucune collection
métier n'est jamais touchée (`reservations`, `subscriptions`,
`discount_codes`, `payment_transactions`, `memberships`, `seance_mouvements`,
`courses`, `offers`) — le banc fait échouer toute tentative.

FLUX : moteur phases 1/2 → projection Association (phase 3) → `verifier_anonymat`
→ snapshot. Ce module ne recalcule RIEN : il prend le bilan déjà validé, le
range avec ses métadonnées, le signe d'une empreinte SHA-256 déterministe.

RÈGLES DE CLÔTURE : le MODE MOIS uniquement (`periode=mois`, `mois=YYYY-MM`),
un mois civil complet TERMINÉ (fin ≤ maintenant), sans filtre cours ; jamais
une période personnalisée (même si `du`/`au` couvrent exactement un mois),
jamais le mois en cours. Le POST ne lit jamais `du`/`au` : il reconstruit
lui-même le mois officiel depuis `mois=YYYY-MM`. Une clôture existante n'est JAMAIS
écrasée : clé unique `annee-mois:perimetre`, `insert_one` seul, 409 sinon.
Une version corrigée (v2) sera un lot à part — ici, on empêche l'écrasement.

EMPREINTE : SHA-256 du JSON canonique du bilan (clés triées, sans espace,
UTF-8), hors champs volatils (`genere_le`). Deux clôtures du même contenu
donnent la même empreinte ; la date de téléchargement n'y entre pas.
"""
import hashlib
import json
import uuid
from datetime import datetime

from api.routes.analytics_shared import mois_suivant

CLOTURE_COLLECTION = "analytics_monthly_reports"
CLOTURE_SCHEMA_VERSION = 1
CLOTURE_ANALYTICS_VERSION = "phase4-1"
CLOTURE_STATUT_OFFICIEL = "officiel"
CLOTURE_PERIMETRE_TOUS = "tous"
CHAMPS_VOLATILS = ("genere_le",)
CLOTURE_INDEX = [("cle", "unique"), ("id", "unique")]

RAISON_MOIS_INCOMPLET = "Seul un mois civil complet peut être clôturé (du 1er au dernier jour)."
RAISON_MOIS_EN_COURS = "Le mois n'est pas terminé : la clôture n'est possible qu'après sa fin."
RAISON_FILTRE_COURS = "Un bilan officiel couvre tout le périmètre : retirez le filtre cours."
RAISON_PERIODE_PERSO = "Une période personnalisée ne peut pas être clôturée. Sélectionnez un mois complet."
RAISON_DEJA_CLOTURE = "Ce mois est déjà clôturé pour ce périmètre ; une clôture n'est jamais écrasée."


def cle_cloture(annee, mois, coach_id="") -> str:
    """La clé canonique d'un bilan officiel : « 2026-08:tous » ou « 2026-08:coach:<id> »."""
    _c = str(coach_id or "").strip().lower()
    return "%04d-%02d:%s" % (int(annee), int(mois), ("coach:" + _c) if _c else CLOTURE_PERIMETRE_TOUS)


def est_cloturable(debut, fin, maintenant, course_id="", periode="mois") -> tuple:
    """(True, "") si — et seulement si — la vue est le MODE MOIS (`periode=mois`),
    sur un mois civil complet, terminé, sans filtre cours.

    Une période personnalisée n'est JAMAIS clôturable, même quand `du`/`au`
    tombent exactement sur le premier et le dernier jour d'un mois : elle
    reste une vue dynamique. Seul un mois explicitement désigné (`mois=YYYY-MM`)
    devient un bilan officiel."""
    if str(periode or "").strip().lower() != "mois":
        return False, RAISON_PERIODE_PERSO
    if debut is None or fin is None:
        return False, RAISON_MOIS_INCOMPLET
    if not (debut.day == 1 and debut.hour == 0 and debut.minute == 0 and fin == mois_suivant(debut)):
        return False, RAISON_MOIS_INCOMPLET
    if fin > maintenant:
        return False, RAISON_MOIS_EN_COURS
    if str(course_id or "").strip():
        return False, RAISON_FILTRE_COURS
    return True, ""


def bilan_figeable(assoc) -> dict:
    """Le bilan tel qu'il sera figé : la projection, sans ses champs volatils."""
    return {k: v for k, v in (assoc or {}).items() if k not in CHAMPS_VOLATILS}


def hash_bilan(bilan) -> str:
    """SHA-256 du JSON canonique — indépendant de l'ordre des clés et des champs volatils."""
    _canon = json.dumps(bilan_figeable(bilan), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(_canon.encode("utf-8")).hexdigest()


def construire_snapshot(assoc, debut, fin, coach_id, created_by, maintenant=None) -> dict:
    """Le document à insérer. Pur : aucune base, aucun recalcul."""
    maintenant = maintenant or datetime.now()
    bilan = bilan_figeable(assoc)
    return {
        "id": str(uuid.uuid4()),
        "cle": cle_cloture(debut.year, debut.month, coach_id),
        "annee": debut.year,
        "mois": debut.month,
        "periode": {"debut": debut.strftime("%Y-%m-%d"), "fin_exclue": fin.strftime("%Y-%m-%d"),
                    "libelle": (assoc or {}).get("periode", {}).get("libelle", "")},
        "perimetre": {"libelle": (assoc or {}).get("perimetre", {}).get("libelle", ""),
                      "coach_id": str(coach_id or "").strip().lower() or None},
        "statut": CLOTURE_STATUT_OFFICIEL,
        "version": 1,
        "schema_version": CLOTURE_SCHEMA_VERSION,
        "analytics_version": CLOTURE_ANALYTICS_VERSION,
        "created_at": maintenant.strftime("%Y-%m-%dT%H:%M:%S"),
        "created_by": str(created_by or "").strip().lower(),
        "bilan_genere_le": (assoc or {}).get("genere_le", ""),
        "hash": hash_bilan(bilan),
        "bilan": bilan,
    }


def meta_snapshot(doc) -> dict:
    """Ce que l'écran et les archives voient d'une clôture — sans le bilan complet."""
    _d = doc or {}
    return {
        "id": _d.get("id"), "cle": _d.get("cle"), "annee": _d.get("annee"), "mois": _d.get("mois"),
        "periode": _d.get("periode"), "perimetre": _d.get("perimetre"), "statut": _d.get("statut"),
        "version": _d.get("version"), "schema_version": _d.get("schema_version"),
        "analytics_version": _d.get("analytics_version"), "created_at": _d.get("created_at"),
        "created_by": _d.get("created_by"), "hash": _d.get("hash"),
    }


def assoc_depuis_snapshot(doc) -> dict:
    """Le bilan figé remis dans la forme de la projection (pour les exports) — avec
    sa mention de clôture. La date de génération d'origine est conservée."""
    _d = doc or {}
    assoc = dict(_d.get("bilan") or {})
    assoc["genere_le"] = _d.get("bilan_genere_le") or _d.get("created_at") or ""
    assoc["cloture"] = {
        "officiel": True, "date": _d.get("created_at"), "version": _d.get("version"),
        "hash": _d.get("hash"), "statut": _d.get("statut"),
        "libelle": "BILAN OFFICIEL — clôturé le %s (v%s) — empreinte %s" % (
            str(_d.get("created_at") or "")[:16].replace("T", " "), _d.get("version"), str(_d.get("hash") or "")[:12]),
    }
    return assoc


def verifier_integrite(doc) -> bool:
    """L'empreinte stockée correspond-elle encore au bilan stocké ?"""
    return bool(doc) and hash_bilan((doc or {}).get("bilan") or {}) == (doc or {}).get("hash")
