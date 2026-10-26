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

──────────────────────── L'AUTHENTIFICATION : SIGNATURE LIÉE À LA REQUÊTE ────────────────────────

Point de départ : le motif du webhook Studiio (V331, `_v331_signature_valide`).
Mais ce motif signe le CORPS BRUT — et une route GET n'a pas de corps : la
signature y serait donc une valeur CONSTANTE (HMAC du secret sur une chaîne
vide), rejouable indéfiniment par quiconque l'intercepte une seule fois. Une
revue de sécurité l'a signalé avant toute mise en service ; ce module s'en
écarte délibérément sur ce point précis.

La signature couvre ici une CHAÎNE CANONIQUE qui lie la preuve à CETTE requête :

    MÉTHODE \n CHEMIN \n CHAÎNE_DE_REQUÊTE_BRUTE \n HORODATAGE

`X-Afroboosteur-Timestamp` (secondes Unix) est OBLIGATOIRE et doit tomber dans
une fenêtre de ±5 minutes — au-delà, la preuve est trop vieille pour qu'on lui
fasse confiance, qu'elle soit valide ou non. `X-Afroboosteur-Signature` =
HMAC-SHA256(chaîne canonique, secret) en hexadécimal, comparée en TEMPS
CONSTANT (`hmac.compare_digest`). Le repli `Authorization: Bearer <secret>`
de V331 — un secret brut, sans aucune liaison à la requête — n'existe PAS ici :
il serait exactement le défaut qu'on vient de corriger.

Un secret SÉPARÉ, `AFROBOOSTEUR_RELAY_SECRET` — jamais `AFROBOOST_WEBHOOK_SECRET`,
qui sert une direction et un usage différents (Studiio POUSSE des publications
ICI ; afroboosteur.com, lui, TIRE une lecture).

INERTE PAR DÉFAUT, comme V331 : sans `AFROBOOSTEUR_RELAY_SECRET` posé, chaque
route répond 503 et ne lit rien.

L'EN-TÊTE `X-Afroboosteur-Membre` est INFORMATIF SEULEMENT : afroboosteur.com y
place l'identité du membre humain qui consulte, pour que les journaux d'ici
portent un repère lisible — mais elle n'autorise RIEN par elle-même. L'autorité
qui compte a déjà tranché côté afroboosteur.com (les six droits de la phase 3,
revérifiés à chaque requête) AVANT même que cette route ne soit appelée.

────────────────────────────── LA PORTÉE DES DONNÉES ──────────────────────────────

`AFROBOOSTEUR_RELAY_COACH_ID` — OBLIGATOIRE, FERMÉ PAR DÉFAUT. Une revue de
sécurité a signalé qu'une première version de ce fichier ne filtrait RIEN par
`coach_id` : elle s'appuyait sur le fait qu'un seul coach existe AUJOURD'HUI
(db.coaches ne contient que l'admin) — un fait d'EXPLOITATION, pas une garantie
du schéma. Le jour où un second coach existerait, ce relais aurait exposé ses
données sans qu'AUCUNE ligne de code n'ait changé ici. La variable est donc
désormais OBLIGATOIRE (503 si absente, comme le secret) et CHAQUE requête
filtre explicitement sur `coach_id` — jamais un filtre vide qui « marche »
seulement parce que rien d'autre n'existe encore.

Lecture seule au sens strict : aucun champ renvoyé ne permet de reconstituer un
geste d'écriture (pas de jeton, pas de clé API, pas de secret).
"""
import logging
import os
import time
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
FENETRE_HORODATAGE_SECONDES = 300  # ±5 minutes


def init_db(database):
    global db
    db = database


def _secret() -> str:
    return (os.environ.get("AFROBOOSTEUR_RELAY_SECRET", "") or "").strip()


def _coach_id_configure() -> str:
    return (os.environ.get("AFROBOOSTEUR_RELAY_COACH_ID", "") or "").strip()


def _chaine_canonique(methode: str, chemin: str, requete_brute: str, horodatage: str) -> str:
    return "\n".join([methode.upper(), chemin, requete_brute or "", horodatage])


def _signature_valide(secret: str, chaine_canonique: str, entetes) -> bool:
    """HMAC-SHA256 en TEMPS CONSTANT sur une chaîne LIÉE À LA REQUÊTE (méthode,
    chemin, requête, horodatage) — jamais une valeur réutilisable telle quelle."""
    import hmac
    import hashlib
    attendue = hmac.new(secret.encode(), chaine_canonique.encode(), hashlib.sha256).hexdigest()
    fournie = (entetes.get("X-Afroboosteur-Signature", "") or "").strip()
    if fournie.lower().startswith("sha256="):
        fournie = fournie.split("=", 1)[1].strip()
    return bool(fournie) and hmac.compare_digest(fournie.lower(), attendue.lower())


def _horodatage_dans_la_fenetre(valeur: str) -> bool:
    try:
        horodatage = int(valeur)
    except (TypeError, ValueError):
        return False
    return abs(time.time() - horodatage) <= FENETRE_HORODATAGE_SECONDES


async def _garde(request: Request) -> str:
    """Vérifie secret + horodatage + signature liée à la requête, ET la
    présence du périmètre coach. Lève HTTPException (503 si inerte, 401/403
    selon le défaut) ou rend l'identité (informative) du membre appelant."""
    secret = _secret()
    coach_id = _coach_id_configure()
    if not secret or not coach_id:
        raise HTTPException(status_code=503, detail="Relais afroboosteur non configuré")

    horodatage = (request.headers.get("X-Afroboosteur-Timestamp", "") or "").strip()
    if not horodatage or not _horodatage_dans_la_fenetre(horodatage):
        logger.warning(f"{PREFIXE} horodatage absent ou hors fenetre")
        raise HTTPException(status_code=401, detail="Horodatage absent ou expiré")

    chaine = _chaine_canonique(
        request.method, request.url.path, str(request.url.query or ""), horodatage
    )
    if not _signature_valide(secret, chaine, request.headers):
        logger.warning(f"{PREFIXE} signature invalide")
        raise HTTPException(status_code=403, detail="Signature invalide")

    membre = (request.headers.get("X-Afroboosteur-Membre", "") or "").strip()[:200]
    logger.info(f"{PREFIXE} consultation par membre afroboosteur={membre or '(non precise)'}")
    return membre


def _portee() -> dict:
    """Le filtre de tenance, OBLIGATOIRE — jamais un filtre vide. `_garde` a
    déjà refusé la requête (503) si `AFROBOOSTEUR_RELAY_COACH_ID` est absent :
    cette fonction ne s'appelle donc jamais sans lui."""
    return {"coach_id": _coach_id_configure()}


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
    filtre = dict(_portee(), corbeille={"$ne": True})
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
    filtre = _portee()
    total = await db[P3S3_CAMPAGNES].count_documents(filtre)
    lignes = await db[P3S3_CAMPAGNES].find(filtre, _PROJECTION_CAMPAGNE) \
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
    filtre = _portee()
    total = await db[P3U2_COLLECTION].count_documents(filtre)
    lignes = await db[P3U2_COLLECTION].find(filtre, _PROJECTION_CONVERSATION) \
        .sort([("received_at", -1), ("id", 1)]).skip(depart).limit(limite).to_list(limite)
    return {"total": total, "returned": len(lignes), "limit": limite, "offset": depart,
            "conversations": lignes}
