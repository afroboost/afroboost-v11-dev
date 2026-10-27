# -*- coding: utf-8 -*-
# P4-RELAIS : PASSERELLE SERVEUR-A-SERVEUR, LECTURE SEULE, VERS AFROBOOSTEUR.COM
"""P4-RELAIS — permet à un membre autorisé d'afroboosteur.com de CONSULTER les
prospects, campagnes et conversations d'afroboost.com, sans jamais y écrire.

─────────────────────────────── CE QUE CE MODULE EST ───────────────────────────────

Un GUICHET, pas un second accès admin. Trois routes, toutes GET, qui relisent les
MÊMES collections que le tableau de bord du coach (`partner_prospects`,
`prospect_campaigns`, `prospect_inbound_messages`) à travers une projection
RÉDUITE — jamais les champs internes (dedupe_key, website_domain, created_by…).

Phases 4/5 : trois routes `GET`, consultation seule, aucune écriture.

PHASE 6A — UNE SEULE ACTION DÉLÉGUÉE AJOUTÉE, ET RIEN D'AUTRE. « Répondre à un
partenaire » est la SEULE action que ce fichier autorise désormais, via trois
routes NARROWEMENT dédiées — jamais un relais générique vers les routes
privées d'afroboost.com :

  * `GET  .../conversations/{id}/brouillon`        — lecture, aucune écriture.
  * `POST .../conversations/{id}/brouillon`        — enregistre le TEXTE d'une
    réponse (et lui seul — jamais un média), avec contrôle de concurrence par
    empreinte : un brouillon modifié entre-temps refuse l'écriture plutôt que
    de l'écraser en silence. C'EST LA SEULE ÉCRITURE MONGO DE CE FICHIER.
  * `POST .../conversations/{id}/apercu-reponse`   — VALIDE un envoi possible,
    sans jamais le réserver ni l'exécuter.

Chacune réutilise les MÊMES fonctions déjà prouvées par le tableau de bord du
coach (`p3ai_dossier`, `v625_empreinte`, `p3ai4_refuse_par_stop`,
`p3n_contexte_obsolete`, `p3ai_sujets_sensibles`...), jamais une réécriture
parallèle qui pourrait diverger.

⚠️ L'ENVOI RÉEL N'EST PAS CÂBLÉ ICI. `apercu-reponse` valide tout ce qu'un
envoi validerait (brouillon présent, empreinte à jour, destinataire joignable,
registre STOP, contexte non périmé) mais NE RÉSERVE NI N'ENVOIE RIEN — aucune
ligne n'est écrite dans `prospect_reply_sends`. La réservation et l'appel au
fournisseur, qui existent déjà et fonctionnent pour le coach, ne sont
délibérément PAS repris ici tant qu'un GO explicite et séparé n'autorise pas
l'envoi réel depuis ce relais.

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


def _empreinte_corps(corps_brut: bytes) -> str:
    """SHA-256 hexadecimal du CORPS BRUT exact — `b""` pour un GET (constante
    bien connue, `e3b0c4...`), les octets exacts envoyes pour un POST. Jamais
    une reserialisation JSON : reserialiser risquerait un ordre de cles
    different de celui reellement signe cote appelant — l'empreinte porte sur
    ce qui a VOYAGE, pas sur une reconstruction."""
    import hashlib
    return hashlib.sha256(corps_brut or b"").hexdigest()


def _chaine_canonique(methode: str, chemin: str, requete_brute: str, horodatage: str,
                       empreinte_corps: str = "") -> str:
    """REVUE DE SECURITE — P6A : la chaine ne liait que methode+chemin+requete+
    horodatage. Les routes de lecture (phases 4/5) n'ont jamais de corps, donc
    rien n'etait en jeu ; la phase 6A a introduit DEUX routes `POST` avec un
    corps JSON SIGNIFICATIF (le texte d'un brouillon, une empreinte) — et ce
    corps, lui, n'etait couvert par AUCUNE preuve : une signature valide pour
    UN corps restait valide, telle quelle, pour N'IMPORTE QUEL AUTRE corps sur
    le MEME chemin/horodatage. Une fuite de signature (journal intermediaire,
    outil de diagnostic) aurait permis de substituer le TEXTE enregistre,
    dans la fenetre de 5 minutes.
    `empreinte_corps` (vide par defaut) ferme ce defaut en liant le corps a la
    preuve — `_empreinte_corps()`, jamais une reserialisation. Les trois
    routes GET existantes n'envoient jamais de corps : leur preuve ne change
    pas de NATURE, seulement d'une ligne CONSTANTE (l'empreinte d'un corps
    vide) — mais CHANGE DE VALEUR, ce qui rompt la compatibilite avec les
    signatures emises avant ce correctif. Voir le journal de deploiement :
    les deux cotes doivent etre deployes ENSEMBLE, jamais l'un sans l'autre.
    """
    return "\n".join([methode.upper(), chemin, requete_brute or "", horodatage, empreinte_corps])


def _chaine_canonique_heritee(methode: str, chemin: str, requete_brute: str,
                               horodatage: str) -> str:
    """L'ANCIENNE chaine, en QUATRE lignes, telle qu'afroboosteur.com la signe
    ENCORE EN PRODUCTION a l'heure ou ce correctif part.

    ⚠️ CECI EST UN PONT, PAS L'ETAT FINAL — a retirer, voir `_garde`.

    Pourquoi elle existe : le passage a cinq lignes change la VALEUR de toutes
    les signatures, y compris celles des trois routes de lecture deja en
    production. Sans ce pont, deployer un seul des deux depots renvoie 403 sur
    TOUT jusqu'a ce que l'autre suive — et comme les deux ne peuvent jamais
    basculer a la milliseconde, l'interruption est garantie dans les deux
    ordres possibles.

    Pourquoi elle n'affaiblit RIEN : `_garde` ne l'essaie QUE si le corps de la
    requete est VIDE. Un corps vide n'a rien a prouver — son empreinte est une
    constante connue de tous. Les deux routes `POST` de la phase 6A, les seules
    a porter un corps SIGNIFICATIF et les seules pour lesquelles ce correctif a
    ete ecrit, n'atteignent JAMAIS ce repli : elles exigent la chaine a cinq
    lignes, sans exception et des le premier jour.

    Ne comporte volontairement PAS de cinquieme ligne vide : l'ancienne chaine
    n'avait pas de saut de ligne final, et `_chaine_canonique(...)` appelee a
    quatre arguments en produirait un.
    """
    return "\n".join([methode.upper(), chemin, requete_brute or "", horodatage])


def _signature_valide(secret: str, chaine_canonique: str, entetes) -> bool:
    """HMAC-SHA256 en TEMPS CONSTANT sur une chaîne LIÉE À LA REQUÊTE (méthode,
    chemin, requête, horodatage, empreinte du corps) — jamais une valeur
    réutilisable telle quelle, et jamais substituable sur son corps."""
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
    """Vérifie secret + horodatage + signature liée à la requête (ET à son
    corps — P6A), ET la présence du périmètre coach. Lève HTTPException
    (503 si inerte, 401/403 selon le défaut) ou rend l'identité (informative)
    du membre appelant.

    `await request.body()` AVANT toute autre lecture du corps : Starlette met
    en cache les octets lus, donc `await request.json()`, plus bas dans
    chaque route, relit le MEME corps sans jamais retoucher le flux reseau —
    aucun risque d'epuiser le flux avant que la route n'y accede a son tour.
    """
    secret = _secret()
    coach_id = _coach_id_configure()
    if not secret or not coach_id:
        raise HTTPException(status_code=503, detail="Relais afroboosteur non configuré")

    horodatage = (request.headers.get("X-Afroboosteur-Timestamp", "") or "").strip()
    if not horodatage or not _horodatage_dans_la_fenetre(horodatage):
        logger.warning(f"{PREFIXE} horodatage absent ou hors fenetre")
        raise HTTPException(status_code=401, detail="Horodatage absent ou expiré")

    corps_brut = await request.body()
    requete_brute = str(request.url.query or "")
    chaine = _chaine_canonique(
        request.method, request.url.path, requete_brute, horodatage,
        _empreinte_corps(corps_brut)
    )
    if not _signature_valide(secret, chaine, request.headers):
        # ─────────────────────────────────────────────────────────────────────
        # PONT DE TRANSITION P6A — A RETIRER, PROCEDURE CI-DESSOUS
        #
        # Accepte l'ANCIENNE chaine (quatre lignes, sans empreinte de corps)
        # UNIQUEMENT pour une requete SANS CORPS, le temps qu'afroboosteur.com
        # recoive le meme correctif. Voir `_chaine_canonique_heritee` pour le
        # raisonnement complet : un corps vide n'a rien a prouver, et les deux
        # routes `POST` de la phase 6A ne passent JAMAIS par ici.
        #
        # MEME MOTIF QUE LE PONT V265 (`[V265] repli X-User-Email`, CLAUDE.md) :
        # tant que `[TRANSITION P6A]` apparait dans les journaux, afroboosteur.com
        # signe encore a l'ancien format — NE PAS retirer ce repli. Quand ces
        # avertissements ont cesse, une version dediee supprime ce bloc et
        # `_chaine_canonique_heritee`, et le relais redevient strict.
        # ─────────────────────────────────────────────────────────────────────
        pont_possible = not corps_brut and _signature_valide(
            secret,
            _chaine_canonique_heritee(request.method, request.url.path, requete_brute, horodatage),
            request.headers,
        )
        if not pont_possible:
            logger.warning(f"{PREFIXE} signature invalide")
            raise HTTPException(status_code=403, detail="Signature invalide")
        logger.warning(
            "%s [TRANSITION P6A] signature a l'ANCIEN format (4 lignes, sans corps) acceptee "
            "sur %s — afroboosteur.com n'a pas encore le correctif ; ne pas retirer le pont",
            PREFIXE, request.url.path)

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


# -----------------------------------------------------------------------------
# 4. PHASE 6A — REPONDRE A UN PARTENAIRE : lecture du brouillon, puis apercu
#    valide de l'envoi. AUCUNE reservation, AUCUN envoi reel depuis ce fichier
#    — voir l'avertissement en tete de module.
# -----------------------------------------------------------------------------

async def _message_de_la_portee(inbound_id: str) -> dict:
    """Le message, dans la portee du coach configure. 404 sinon — jamais un
    indice sur l'existence d'un message hors portee."""
    identifiant = (inbound_id or "").strip()
    if not identifiant or len(identifiant) > 64:
        raise HTTPException(status_code=404, detail="Reponse introuvable")
    message = await db[P3U2_COLLECTION].find_one(
        {"id": identifiant, **_portee()}, {"_id": 0})
    if not message:
        raise HTTPException(status_code=404, detail="Reponse introuvable")
    return message


@router.get("/api/afroboosteur-relais/conversations/{inbound_id}/brouillon")
async def relais_lire_brouillon(inbound_id: str, request: Request):
    """Le brouillon de reponse a ce message, ou null. LECTURE SEULE.

    Reutilise EXACTEMENT ce que `p3ai_lire_brouillon` calcule pour le coach
    (etat lu/traite, contexte perime, statut commercial) — la meme verite,
    jamais une resumee a part pour ce relais.
    """
    await _garde(request)
    # Import differe : evite la circularite avec api.server, qui importe ce
    # module. Motif deja etabli ailleurs dans ce depot (ex. bot_whatsapp_routes.py).
    from api.server import (
        P3AI_BROUILLONS, P3AI_CHAMP_LU, P3AI_CHAMP_TRAITE,
        p3n_contexte_obsolete, p3n_derniere_declaration,
        p3n_notes_du_dossier, p3n_statut_commercial,
        v625_empreinte, v625_medias,
    )

    message = await _message_de_la_portee(inbound_id)
    brouillon = await db[P3AI_BROUILLONS].find_one(
        {"inbound_id": message["id"]}, {"_id": 0})
    notes = await p3n_notes_du_dossier(message.get("action_id") or "")
    # L'EMPREINTE EST CALCULEE ICI, PAS CHEZ L'APPELANT. afroboosteur.com n'a
    # pas besoin de connaitre l'algorithme de `v625_empreinte` : il recoit la
    # valeur deja calculee et la renvoie telle quelle a `.../apercu-reponse`.
    # Un seul endroit sait COMMENT elle se calcule — jamais une seconde
    # implementation, dans un troisieme langage, qui pourrait diverger.
    empreinte = None
    if brouillon:
        texte_brouillon = str(brouillon.get("reponse_proposee") or "").strip()
        if texte_brouillon:
            empreinte = v625_empreinte(texte_brouillon, v625_medias(brouillon))
    return {
        "brouillon": brouillon,
        "draft_hash": empreinte,
        "lu": bool(message.get(P3AI_CHAMP_LU)),
        "traite": bool(message.get(P3AI_CHAMP_TRAITE)),
        "contexte_obsolete": p3n_contexte_obsolete(brouillon, notes),
        "statut_commercial": p3n_statut_commercial(
            message, p3n_derniere_declaration(notes),
            (brouillon or {}).get("intention")),
    }


@router.post("/api/afroboosteur-relais/conversations/{inbound_id}/brouillon")
async def relais_enregistrer_brouillon(inbound_id: str, request: Request):
    """Enregistre le TEXTE d'une reponse — jamais le media, jamais l'envoi.

    ─────────────────────────────────────────────────────────────────────────────
    LA SEULE ECRITURE MONGO DE CE FICHIER, ET DELIBEREMENT ETROITE

    Reprend `p3ai_modifier_brouillon` (meme troncature P3AI_REPONSE_MAX, memes
    `motifs_validation`/`validation_requise` recalcules, meme `upsert=True` qui
    permet d'ECRIRE le tout premier brouillon d'une reponse — pas seulement
    corriger un brouillon ne de l'IA) — a UNE difference pres, delibere pour ce
    canal : AUCUN champ media n'est jamais touche. `corps.get("medias")` et
    `corps.get("media")` ne sont meme pas lus : un brouillon deja joint d'un
    fichier le reste strictement tel quel apres un passage par ce relais.

    ⚠️ JAMAIS D'ECRASEMENT SILENCIEUX. Le brouillon EXISTANT (s'il y en a un)
    est fourni avec une empreinte (`draft_hash`, GET .../brouillon) : enregistrer
    exige de renvoyer CETTE empreinte. Si le brouillon a change entre-temps
    (corrige par le coach, par l'IA, ou par un autre membre autorise), l'empreinte
    ne correspond plus et l'ecriture est refusee avec un message explicite —
    jamais une ecriture qui gagnerait en silence. Pour un TOUT PREMIER brouillon
    (aucun n'existe encore), `draft_hash` doit etre vide : une empreinte non vide
    face a une absence de brouillon est, elle aussi, refusee.

    `to_email` n'est toujours PAS ecrit ici, pour la meme raison que la route du
    coach : le destinataire reel se resout a l'envoi, jamais depuis un corps de
    requete.
    """
    await _garde(request)
    # Import differe : evite la circularite avec api.server, qui importe ce
    # module. Motif deja etabli ailleurs dans ce depot (ex. bot_whatsapp_routes.py).
    from api.server import (
        P3AI_BROUILLONS, P3AI_REPONSE_MAX,
        p3ai_sujets_sensibles, v625_empreinte, v625_medias,
    )

    message = await _message_de_la_portee(inbound_id)

    try:
        corps = await request.json()
    except Exception:
        corps = {}
    if not isinstance(corps, dict) or "texte" not in corps:
        raise HTTPException(status_code=400, detail="Champ `texte` requis")
    texte = str(corps.get("texte") or "").strip()
    if not texte:
        raise HTTPException(status_code=400, detail="Un brouillon vide ne se garde pas")
    empreinte_recue = str(corps.get("draft_hash") or "").strip()

    brouillon_actuel = await db[P3AI_BROUILLONS].find_one(
        {"inbound_id": message["id"]}, {"_id": 0})

    if brouillon_actuel:
        texte_actuel = str(brouillon_actuel.get("reponse_proposee") or "").strip()
        empreinte_actuelle = (
            v625_empreinte(texte_actuel, v625_medias(brouillon_actuel)) if texte_actuel else ""
        )
        if empreinte_recue != empreinte_actuelle:
            raise HTTPException(
                status_code=409,
                detail="Ce brouillon a été modifié depuis votre dernière lecture. "
                       "Rechargez-le avant d'enregistrer — rien n'a été écrasé.")
    elif empreinte_recue:
        # L'appelant croit qu'un brouillon existe deja (il porte une empreinte),
        # mais il n'y en a aucun — meme refus, meme raison : sa vue est perimee.
        raise HTTPException(
            status_code=409,
            detail="Ce brouillon a été modifié depuis votre dernière lecture. "
                   "Rechargez-le avant d'enregistrer — rien n'a été écrasé.")

    maintenant = datetime.now(timezone.utc).isoformat()
    membre = (request.headers.get("X-Afroboosteur-Membre", "") or "").strip()[:200]
    texte_tronque = texte[:P3AI_REPONSE_MAX]
    await db[P3AI_BROUILLONS].update_one(
        {"inbound_id": message["id"]},
        {"$set": {"reponse_proposee": texte_tronque,
                  "motifs_validation": p3ai_sujets_sensibles(texte_tronque),
                  "validation_requise": bool(p3ai_sujets_sensibles(texte_tronque)),
                  "edite_le": maintenant,
                  # INFORMATIF, comme X-Afroboosteur-Membre partout ailleurs dans ce
                  # fichier — jamais une identite verifiee par afroboost.com.
                  "edite_par": "afroboosteur:%s" % (membre or _coach_id_configure()),
                  "updated_at": maintenant},
         "$setOnInsert": {"inbound_id": message["id"], "origine": "coach",
                          "created_at": maintenant}},
        upsert=True)

    brouillon_enregistre = await db[P3AI_BROUILLONS].find_one(
        {"inbound_id": message["id"]}, {"_id": 0})
    logger.info("%s brouillon enregistre pour %s via le relais (membre=%s)",
               PREFIXE, inbound_id[:24], membre or "(non precise)")
    return {
        "brouillon": brouillon_enregistre,
        "draft_hash": v625_empreinte(texte_tronque, v625_medias(brouillon_enregistre)),
    }


@router.post("/api/afroboosteur-relais/conversations/{inbound_id}/apercu-reponse")
async def relais_apercu_reponse(inbound_id: str, request: Request):
    """Valide qu'une reponse POURRAIT partir — sans rien reserver ni envoyer.

    Corps attendu : `{"draft_hash": "..."}` — la meme empreinte que l'ecran du
    coach calcule et exige avant un envoi reel, pour que l'apercu porte sur LE
    MEME texte que celui affiche, jamais une version perimee.

    Rend `{"pret": bool, "raison": str|None, "destinataire": str|None,
    "texte": str|None, "deja_envoye": bool}`. `pret: false` n'est jamais une
    erreur HTTP : c'est une reponse normale ("pas encore prete"), pour que
    l'ecran l'affiche sans avoir a distinguer un refus metier d'une panne.
    """
    await _garde(request)
    from api.server import (
        P3AI4_COLLECTION, P3AI_BROUILLONS, P3S3_ACTIONS,
        p3ai4_cle_envoi, p3ai4_destinataire, p3ai4_refuse_par_stop,
        p3n_contexte_obsolete, p3n_notes_du_dossier,
        v621_a_completer, v625_empreinte, v625_medias, v627_blocage,
    )

    message = await _message_de_la_portee(inbound_id)

    try:
        corps = await request.json()
    except Exception:
        corps = {}
    if not isinstance(corps, dict):
        raise HTTPException(status_code=400, detail="Corps JSON attendu")
    empreinte_recue = str(corps.get("draft_hash") or "").strip()
    if not empreinte_recue:
        raise HTTPException(status_code=400, detail="Empreinte du brouillon requise")

    action = {}
    if message.get("action_id"):
        action = await db[P3S3_ACTIONS].find_one(
            {"id": message["action_id"]}, {"_id": 0}) or {}
    fiches = []
    uuids = [u for u in (action.get("prospect_uuids") or []) if u][:20]
    if uuids:
        fiches = await db[P3S1_COLLECTION].find(
            {"id": {"$in": uuids}}, {"_id": 0}).to_list(20)

    brouillon = await db[P3AI_BROUILLONS].find_one(
        {"inbound_id": message["id"]}, {"_id": 0})

    def refus(raison: str) -> dict:
        return {"pret": False, "raison": raison, "destinataire": None,
                "texte": None, "deja_envoye": False}

    if not brouillon:
        return refus("Aucun brouillon a envoyer")
    texte = str(brouillon.get("reponse_proposee") or "").strip()
    if not texte:
        return refus("Le brouillon est vide")
    if v621_a_completer(texte):
        return refus("Completez le champ « [A COMPLETER : …] » avant l'envoi")

    medias_joints = v625_medias(brouillon)
    empreinte_calculee = v625_empreinte(texte, medias_joints)
    if empreinte_recue != empreinte_calculee:
        return refus("Le brouillon a ete modifie. Rechargez la derniere version")

    cle = p3ai4_cle_envoi(message["id"], empreinte_calculee)
    deja = await db[P3AI4_COLLECTION].find_one({"id": cle}, {"_id": 0})
    if deja:
        return {"pret": False, "raison": "Deja envoye", "destinataire": None,
                "texte": None, "deja_envoye": True}

    notes = await p3n_notes_du_dossier(message.get("action_id") or "")
    if p3n_contexte_obsolete(brouillon, notes):
        return refus("Le contexte a change depuis la redaction. Regenerez ou confirmez le brouillon")

    destinataire = p3ai4_destinataire(message, action)
    if not destinataire:
        return refus("Aucune adresse exploitable pour ce dossier")
    if await p3ai4_refuse_par_stop(destinataire):
        return refus("Ce destinataire ne peut pas etre contacte")
    blocage = v627_blocage(fiches)
    if blocage:
        from api.server import v627_message
        return refus(v627_message(blocage))

    return {"pret": True, "raison": None, "destinataire": destinataire,
            "texte": texte, "deja_envoye": False}
