# -*- coding: utf-8 -*-
# P4-RELAIS : PASSERELLE SERVEUR-A-SERVEUR, LECTURE SEULE, VERS AFROBOOSTEUR.COM
"""P4-RELAIS — permet à un membre autorisé d'afroboosteur.com de CONSULTER les
prospects, campagnes et conversations d'afroboost.com, sans jamais y écrire.

─────────────────────────────── CE QUE CE MODULE EST ───────────────────────────────

Un GUICHET, pas un second accès admin. Trois routes, toutes GET, qui relisent les
MÊMES collections que le tableau de bord du coach (`partner_prospects`,
`prospect_campaigns`, `prospect_inbound_messages`) à travers une projection
RÉDUITE — jamais les champs internes (dedupe_key, website_domain, created_by…).

AUCUNE route d'écriture n'existe ici, PAR CONSTRUCTION : ce fichier ne définit
que des `@router.get`. Créer, approuver, lancer une campagne ou répondre à un
partenaire restent exclusivement des gestes du tableau de bord d'afroboost.com,
jamais de ce relais — c'est la mission qui l'exige explicitement (phases 4/5 :
consultation seule ; les phases ultérieures, non commencées, pourraient un jour
brancher des actions, mais PAS ici).

─────────────────────── L'AUTHENTIFICATION : UN SECRET DÉDIÉ ───────────────────────

Même mécanisme que le webhook Studiio (V331, `_v331_signature_valide`), repris
à l'identique plutôt que réinventé : HMAC-SHA256 du corps brut en voie principale,
`Authorization: Bearer <secret>` en repli, comparaison en TEMPS CONSTANT
(`hmac.compare_digest`). Mais un secret SÉPARÉ, `AFROBOOSTEUR_RELAY_SECRET` —
jamais `AFROBOOST_WEBHOOK_SECRET`, qui sert une direction et un usage différents
(Studiio POUSSE des publications ICI ; afroboosteur.com, lui, TIRE une lecture).
Confondre les deux secrets effacerait la frontière d'audit entre deux intégrations
qui n'ont rien à voir l'une avec l'autre.

INERTE PAR DÉFAUT, comme V331 : sans `AFROBOOSTEUR_RELAY_SECRET` posé, chaque
route répond 503 et ne lit rien. Aucun risque tant que Bassi n'a pas configuré
le secret des DEUX côtés.

L'EN-TÊTE `X-Afroboosteur-Membre` est INFORMATIF SEULEMENT : afroboosteur.com y
place l'identité du membre humain qui consulte, pour que les journaux d'ici
portent un repère lisible — mais elle n'autorise RIEN par elle-même. L'autorité
qui compte a déjà tranché côté afroboosteur.com (les six droits de la phase 3,
revérifiés à chaque requête) AVANT même que cette route ne soit appelée ; ce
service ne fait confiance qu'au secret partagé, jamais à un en-tête qu'un tiers
pourrait forger.

────────────────────────────── LA PORTÉE DES DONNÉES ──────────────────────────────

Aucun filtre `coach_id` : ce relais sert la donnée du SEUL coach réel de cette
installation (aucun coach partenaire actif — db.coaches ne contient que l'admin,
constat déjà établi). Filtrer par coach_id introduirait une notion de tenance qui
n'existe nulle part ailleurs ici, pour rien.

Lecture seule au sens strict : aucun champ renvoyé ne permet de reconstituer un
geste d'écriture (pas de jeton, pas de clé API, pas de secret).
"""
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)
PREFIXE = "[P4-RELAIS]"

router = APIRouter(tags=["afroboosteur-relais"])
db = None

P3S1_COLLECTION = "partner_prospects"
P3S3_CAMPAGNES = "prospect_campaigns"
P3U2_COLLECTION = "prospect_inbound_messages"

LIMITE_MAX = 50


def init_db(database):
    global db
    db = database


def _secret() -> str:
    return (os.environ.get("AFROBOOSTEUR_RELAY_SECRET", "") or "").strip()


def _signature_valide(secret: str, corps_brut: bytes, entetes) -> bool:
    """Identique à `_v331_signature_valide` (webhook Studiio) — voir l'en-tête
    de ce fichier pour pourquoi le secret, lui, ne l'est pas."""
    import hmac
    import hashlib
    attendue = hmac.new(secret.encode(), corps_brut, hashlib.sha256).hexdigest()
    fournie = (entetes.get("X-Afroboosteur-Signature", "") or "").strip()
    if fournie.lower().startswith("sha256="):
        fournie = fournie.split("=", 1)[1].strip()
    if fournie and hmac.compare_digest(fournie.lower(), attendue.lower()):
        return True
    auth = (entetes.get("Authorization", "") or "").strip()
    if auth.lower().startswith("bearer "):
        jeton = auth.split(" ", 1)[1].strip()
        if jeton and hmac.compare_digest(jeton, secret):
            return True
    return False


async def _garde(request: Request) -> str:
    """Vérifie le secret partagé. Lève HTTPException (503 si inerte, 403 si
    signature absente/invalide) ou rend l'identité (informative) du membre
    appelant, pour le seul usage des journaux applicatifs."""
    secret = _secret()
    if not secret:
        raise HTTPException(status_code=503, detail="Relais afroboosteur non configuré")
    corps_brut = await request.body()
    if not _signature_valide(secret, corps_brut, request.headers):
        logger.warning(f"{PREFIXE} signature invalide ou absente")
        raise HTTPException(status_code=403, detail="Signature invalide")
    membre = (request.headers.get("X-Afroboosteur-Membre", "") or "").strip()[:200]
    logger.info(f"{PREFIXE} consultation par membre afroboosteur={membre or '(non precise)'}")
    return membre


def _pagination(request: Request) -> tuple:
    parametres = request.query_params
    try:
        limite = max(1, min(int(parametres.get("limit") or 25), LIMITE_MAX))
    except (TypeError, ValueError):
        limite = 25
    try:
        depart = max(0, int(parametres.get("offset") or 0))
    except (TypeError, ValueError):
        depart = 0
    return limite, depart


# -----------------------------------------------------------------------------
# 1. PROSPECTS — projection reduite, aucun champ interne
# -----------------------------------------------------------------------------

_PROJECTION_PROSPECT = {
    "_id": 0, "id": 1, "organisation_name": 1, "city": 1, "status": 1,
    "category": 1, "priority": 1, "public_email": 1, "public_phone": 1,
    "website": 1, "wave": 1, "created_at": 1, "updated_at": 1,
    "corbeille": 1, "adresse_a_corriger": 1,
}


@router.get("/api/afroboosteur-relais/prospects")
async def relais_lister_prospects(request: Request):
    """Lecture pure des prospects — aucune ecriture possible depuis cette route."""
    await _garde(request)
    limite, depart = _pagination(request)
    filtre = {"corbeille": {"$ne": True}}
    total = await db[P3S1_COLLECTION].count_documents(filtre)
    lignes = await db[P3S1_COLLECTION].find(filtre, _PROJECTION_PROSPECT) \
        .sort([("created_at", -1), ("id", 1)]).skip(depart).limit(limite).to_list(limite)
    return {"total": total, "returned": len(lignes), "limit": limite, "offset": depart,
            "prospects": lignes}


# -----------------------------------------------------------------------------
# 2. CAMPAGNES — etat et compteurs, jamais le contenu brut des envois
# -----------------------------------------------------------------------------

_PROJECTION_CAMPAGNE = {
    "_id": 0, "id": 1, "nom": 1, "etat": 1, "nb_fiches": 1, "nb_destinataires": 1,
    "summary": 1, "created_at": 1, "updated_at": 1, "approved_at": 1,
    "started_at": 1, "finished_at": 1,
}


@router.get("/api/afroboosteur-relais/campaigns")
async def relais_lister_campagnes(request: Request):
    """Lecture pure des campagnes — ni preparer, ni approuver, ni lancer."""
    await _garde(request)
    limite, depart = _pagination(request)
    total = await db[P3S3_CAMPAGNES].count_documents({})
    lignes = await db[P3S3_CAMPAGNES].find({}, _PROJECTION_CAMPAGNE) \
        .sort([("created_at", -1), ("id", 1)]).skip(depart).limit(limite).to_list(limite)
    return {"total": total, "returned": len(lignes), "limit": limite, "offset": depart,
            "campaigns": lignes}


# -----------------------------------------------------------------------------
# 3. CONVERSATIONS (reponses des partenaires) — lecture, jamais de reponse d'ici
# -----------------------------------------------------------------------------

_PROJECTION_CONVERSATION = {
    "_id": 0, "id": 1, "from_email": 1, "subject": 1, "body_text": 1,
    "received_at": 1, "statut": 1, "provider": 1,
}


@router.get("/api/afroboosteur-relais/conversations")
async def relais_lister_conversations(request: Request):
    """Lecture pure des messages recus des partenaires — aucune reponse possible d'ici."""
    await _garde(request)
    limite, depart = _pagination(request)
    total = await db[P3U2_COLLECTION].count_documents({})
    lignes = await db[P3U2_COLLECTION].find({}, _PROJECTION_CONVERSATION) \
        .sort([("received_at", -1), ("id", 1)]).skip(depart).limit(limite).to_list(limite)
    return {"total": total, "returned": len(lignes), "limit": limite, "offset": depart,
            "conversations": lignes}
