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

⚠️ L'ENVOI RÉEL EST CÂBLÉ DEPUIS V636 — ET FERMÉ PAR TROIS VERROUS. La réserve
écrite ici depuis la phase 6A (« la réservation et l'appel au fournisseur […]
ne sont délibérément PAS repris ici tant qu'un GO explicite et séparé
n'autorise pas l'envoi réel ») a été levée sur GO du Président. `apercu-reponse`
reste ce qu'elle était — une validation qui ne réserve ni n'envoie rien — et la
section 8 ajoute, À CÔTÉ, une route d'envoi qui réutilise
`p3ai4_envoyer_reponse_pour` (api/server.py), la MÊME fonction que la route du
coach. Trois verrous indépendants, tous fermés par défaut, doivent être ouverts
pour qu'un seul e-mail parte : `AFROBOOSTEUR_RELAIS_ENVOI_ACTIF` (ici),
`P3_REPONSE_ACTIF` et `P3_REPONSE_ENVOI_REEL` (drapeaux en base, côté coach).
Voir l'en-tête de la section 8.

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
V595_MEDIAS = "prospection_medias"  # PHASE 6B

LIMITE_MAX = 50
FENETRE_HORODATAGE_SECONDES = 300  # ±5 minutes


def init_db(database):
    global db
    db = database


def _secret() -> str:
    return (os.environ.get("AFROBOOSTEUR_RELAY_SECRET", "") or "").strip()


def _coach_id_configure() -> str:
    return (os.environ.get("AFROBOOSTEUR_RELAY_COACH_ID", "") or "").strip()


def _interrupteur_actif(nom: str) -> bool:
    """MEME convention que `POSTHOG_SERVER_ENABLED` (api/routes/shared.py) —
    jamais reinventee ici. Absent ou toute autre valeur = FERME."""
    return (os.environ.get(nom, "") or "").strip().lower() in ("1", "true", "yes", "on")


def _fil_actif() -> bool:
    return _interrupteur_actif("AFROBOOSTEUR_RELAIS_FIL_ACTIF")


def _relances_actif() -> bool:
    return _interrupteur_actif("AFROBOOSTEUR_RELAIS_RELANCES_ACTIF")


def _ia_actif() -> bool:
    return _interrupteur_actif("AFROBOOSTEUR_RELAIS_IA_ACTIF")


def _envoi_actif() -> bool:
    return _interrupteur_actif("AFROBOOSTEUR_RELAIS_ENVOI_ACTIF")


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

    ⚠️ INCIDENT DU 27/10/2026, ET CE QUI LE REMPLACE. Une version precedente
    REFUSAIT ICI (503) toute configuration ou `AFROBOOSTEUR_RELAY_COACH_ID`
    designe le super-admin, au motif que `p3s3_portee(appelant)` rend alors un
    filtre VIDE. Le raisonnement sur la PORTEE etait juste ; la CONCLUSION
    etait fausse, et elle a mis tout le relais a terre en production — les
    trois consultations comprises, qui n'appellent meme pas `p3s3_portee`.
    Pourquoi : sur CETTE plateforme, le seul coach reel EST le super-admin
    (`DEFAULT_COACH_ID = SUPER_ADMIN_EMAILS[0]`, V244 — « l'admin, seul coach
    reel »), et c'est lui qui possede legitimement les 449 prospects. La
    configuration etait donc CORRECTE ; refuser de fonctionner etait l'erreur.
    Le cloisonnement est desormais impose LA OU IL MANQUAIT : les deux
    fonctions deleguees recoivent `tenant_strict=True`, qui force la portee a
    `{"coach_id": appelant}` et le controle de propriete meme pour un
    super-admin. Voir leurs docstrings dans api/server.py."""
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
    "media_ids": 1,  # PHASE 6B — purement declaratif, voir p3s3_medias_partages_valides
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


@router.get("/api/afroboosteur-relais/campaigns/{campaign_id}")
async def relais_lire_campagne(campaign_id: str, request: Request):
    """Le detail d'UNE campagne — meme projection que la liste, JAMAIS les
    actions (chaque action porte un message pret et une adresse reelle de
    prospect : une PII que cette route ne doit pas faire voyager vers un
    autre systeme). Pour « combien de destinataires », `summary`/`nb_*`
    suffisent — c'est deja ce que l'ecran du coach affiche en premier."""
    await _garde(request)
    identifiant = (campaign_id or "").strip()[:64]
    campagne = await db[P3S3_CAMPAGNES].find_one(
        dict(_portee(), id=identifiant), _PROJECTION_CAMPAGNE)
    if not campagne:
        raise HTTPException(status_code=404, detail="Campagne introuvable")
    return {"campaign": campagne}


@router.post("/api/afroboosteur-relais/campaigns")
async def relais_preparer_campagne(request: Request):
    """Cree OU previsualise une campagne de prospection — PHASE 6B.

    Relaie VERBATIM vers `p3s3_preparer_campagne_pour`, la MEME fonction que
    la route du coach appelle depuis son extraction (voir server.py) : aucune
    logique parallele, aucun risque de divergence. `dry_run` (true par
    defaut, comme cote coach) decide seul si quelque chose est ecrit —
    « previsualiser » et « creer » ne sont pas deux routes, mais le MEME appel
    avec ce seul booleen different. N'envoie jamais rien : cette fonction n'a
    aucune notion de fournisseur, voir son propre docstring.
    """
    await _garde(request)
    from api.server import p3s3_preparer_campagne_pour

    try:
        corps = await request.json()
    except Exception:
        corps = {}
    if not isinstance(corps, dict):
        raise HTTPException(status_code=400, detail="Corps JSON attendu")
    # tenant_strict : cloisonnement force meme si le coach configure est le
    # super-admin (incident du 27/10, voir le docstring de `_garde`).
    resultat = await p3s3_preparer_campagne_pour(_coach_id_configure(), corps,
                                                 tenant_strict=True)
    campagne = resultat.get("campaign")
    if isinstance(campagne, dict):
        resultat["campaign"] = {cle: campagne.get(cle) for cle in _PROJECTION_CAMPAGNE if cle != "_id"}
    # `actions`/`campagne_ouverte` : memes reserves PII qu'au-dessus — retirees
    # de la reponse du relais, jamais de la fonction reutilisee elle-meme.
    resultat.pop("actions", None)
    ouverte = resultat.get("campagne_ouverte")
    if isinstance(ouverte, dict):
        resultat["campagne_ouverte"] = {cle: ouverte.get(cle) for cle in _PROJECTION_CAMPAGNE if cle != "_id"}
    return resultat


@router.patch("/api/afroboosteur-relais/campaigns/{campaign_id}")
async def relais_modifier_campagne(campaign_id: str, request: Request):
    """Modifie une campagne PREPAREE — nom et/ou medias partages. Relaie vers
    `p3s3_modifier_campagne_pour`, la MEME fonction que la route du coach.
    """
    await _garde(request)
    from api.server import p3s3_modifier_campagne_pour

    try:
        corps = await request.json()
    except Exception:
        corps = {}
    if not isinstance(corps, dict):
        raise HTTPException(status_code=400, detail="Corps JSON attendu")
    identifiant = (campaign_id or "").strip()[:64]
    resultat = await p3s3_modifier_campagne_pour(_coach_id_configure(), identifiant, corps,
                                                 tenant_strict=True)
    campagne = resultat.get("campaign")
    if isinstance(campagne, dict):
        resultat["campaign"] = {cle: campagne.get(cle) for cle in _PROJECTION_CAMPAGNE if cle != "_id"}
    return resultat


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

async def _medias_valides_du_coach(valeurs) -> list:
    """V636 (seuil corrige, relecture du 28/10/2026) — Les medias que CE canal
    accepte de joindre a une reponse.

    ⚠️ LE SEUIL A CHANGE, ET VOICI POURQUOI. La version precedente exigeait
       `validee` — LA MEME frontiere que le PARTAGE DE CAMPAGNE
       (`p3s3_medias_partages_valides`). C'etait la MAUVAISE comparaison.
       Repondre a UN partenaire (6A/V636) est exactement le geste que fait LE
       COACH LUI-MEME depuis son tableau de bord quand il repond a un message
       — et CE geste-la n'a JAMAIS exige `validee` : `v620_resoudre_media`
       accepte tout statut SAUF `archivee`. La campagne, elle, diffuse a
       PLUSIEURS destinataires a la fois — c'est ce volume-la qui justifie une
       barre plus haute, pas la nature de l'action « repondre ».
       Consequence mesuree en production le 28/10/2026 : CHAQUE media nait
       `en_cours` ou `a_verifier` (aucune validation automatique, voir
       `V595_STATUTS_MEDIA`) — exiger `validee` ici revenait, en pratique, a
       fermer ce canal en permanence.

    DEUX refus AVANT toute resolution, chacun pour une raison differente :

      * forme inattendue (pas une liste, un element qui n'est pas un objet, ou
        un objet qui porte autre chose que `media_id`) -> 400. En particulier,
        `fichier_url` est refuse NOMMEMENT : c'est la forme qui designe un
        fichier deja televerse SUR afroboost.com, et un membre afroboosteur
        n'en possede aucun — la lui laisser reviendrait a lui laisser designer
        le fichier d'un autre ;
      * trop de fichiers -> 400, avec la MEME borne que le coach
        (`V625_MEDIAS_MAX`), jamais une seconde valeur qui pourrait diverger.

    Puis `v625_resoudre_medias` — LA MEME FONCTION que la route du coach
    (`p3ai_modifier_brouillon`) appelle pour SON PROPRE brouillon — fait TOUT
    le reste : existence, appartenance au coach configure, statut (tout sauf
    `archivee`, via `v620_resoudre_media`), adresse utilisable, miniature,
    doublons. Plus aucune regle n'est dupliquee ici : la verification
    manuelle du statut (une seconde lecture de `V595_MEDIAS`) a ete retiree,
    parce qu'elle faisait DOUBLE EMPLOI avec ce que cette fonction verifie
    deja — et qu'un seuil different aurait pu y diverger sans qu'un test ne
    le remarque.
    """
    from api.server import V625_MEDIAS_MAX, v625_resoudre_medias

    if valeurs is None:
        valeurs = []
    if not isinstance(valeurs, list):
        raise HTTPException(status_code=400, detail="Liste de médias invalide")
    if len(valeurs) > V625_MEDIAS_MAX:
        raise HTTPException(status_code=400,
                            detail="%d fichiers au maximum par réponse" % V625_MEDIAS_MAX)

    references = []
    for v in valeurs:
        if not isinstance(v, dict):
            raise HTTPException(status_code=400, detail="Média invalide")
        inconnues = set(v.keys()) - {"media_id"}
        if inconnues:
            raise HTTPException(
                status_code=400,
                detail="Seul `media_id` est accepté depuis ce relais — "
                       "un fichier d'afroboost.com ne peut pas y être désigné directement.")
        media_id = str(v.get("media_id") or "").strip()[:64]
        if not media_id:
            raise HTTPException(status_code=400, detail="`media_id` requis")
        references.append({"media_id": media_id})

    return await v625_resoudre_medias(references, _coach_id_configure())


async def _refuser_medias_plus_valides(inbound_id: str) -> None:
    """V636b (seuil corrige, relecture du 28/10/2026) — LA MEME BORNE QUE
    `_medias_valides_du_coach`, RE-VERIFIEE AU MOMENT QUI COMPTE : L'ENVOI.

    LE SEUIL EST DESORMAIS CELUI DE `v620_resoudre_media` — N'IMPORTE QUEL
    STATUT SAUF `archivee`, PAS `validee` seul. Voir le docstring de
    `_medias_valides_du_coach` pour le motif complet du changement (repondre a
    un partenaire est le meme geste que le coach repondant lui-meme, qui n'a
    jamais exige `validee` — exiger `validee` revenait a fermer ce canal en
    permanence, puisqu'aucun media n'est valide automatiquement).

    CE QUI JUSTIFIE QUAND MEME UNE RE-VERIFICATION A L'ENVOI, MEME AVEC CE
    SEUIL PLUS LARGE. Le brouillon est PARTAGE, et l'instantane ne vieillit
    pas : un media peut passer `archivee` APRES avoir ete attache a un
    brouillon (par le coach, depuis son propre tableau de bord, a tout
    moment) — c'est voulu pour LUI (« changer ou supprimer le media plus tard
    ne le touche pas », V620), mais pour un tiers qui envoie en son nom, cela
    reviendrait a expedier un fichier retire entre-temps. On relit donc la
    bibliotheque JUSTE AVANT l'envoi, et on refuse en 409 avec un motif
    lisible si — et seulement si — le media est devenu `archivee` ou a
    disparu. Rien n'est reserve, rien ne part, et le coach garde la
    possibilite d'envoyer lui-meme : son chemin n'est pas touche.

    ⚠️ LIMITE ASSUMEE, A CONNAITRE. Un media que le coach a joint depuis ses
       FICHIERS televerses (`origine: "fichier"`, hors mediatheque) fait aussi
       refuser l'envoi par ce canal : il n'appartient a aucune ligne de
       `prospection_medias`, donc rien ne permet de verifier qu'il est encore
       disponible. C'est le prix de la verification ; le message le dit
       explicitement pour que personne ne cherche une panne.
    """
    from api.server import P3AI_BROUILLONS, V595_MEDIAS, v625_medias

    brouillon = await db[P3AI_BROUILLONS].find_one({"inbound_id": inbound_id}, {"_id": 0})
    if not brouillon:
        return   # l'absence de brouillon est refusee plus loin, par la fonction d'envoi
    for m in v625_medias(brouillon):
        if not isinstance(m, dict):
            raise HTTPException(status_code=409, detail="Média joint illisible — retirez-le avant l'envoi.")
        media_id = str(m.get("media_id") or "").strip()
        if m.get("origine") != "bibliotheque" or not media_id:
            raise HTTPException(
                status_code=409,
                detail="Un fichier joint à ce brouillon ne provient pas de la médiathèque : "
                       "il ne peut pas être envoyé depuis afroboosteur.com. Retirez-le, ou "
                       "demandez au coach d'envoyer cette réponse lui-même.")
        ligne = await db[V595_MEDIAS].find_one(
            dict(_portee(), id=media_id), {"_id": 0, "statut": 1})
        if not ligne or ligne.get("statut") == "archivee":
            raise HTTPException(
                status_code=409,
                detail="Un média joint à ce brouillon n'est plus disponible dans la médiathèque "
                       "(retiré ou archivé). Retirez-le, puis réessayez.")


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
    L'ECRITURE MONGO DU BROUILLON, ET DELIBEREMENT ETROITE

    Reprend `p3ai_modifier_brouillon` (meme troncature P3AI_REPONSE_MAX, memes
    `motifs_validation`/`validation_requise` recalcules, meme `upsert=True` qui
    permet d'ECRIRE le tout premier brouillon d'une reponse — pas seulement
    corriger un brouillon ne de l'IA).

    ⚠️ V636 — LES MEDIAS DEVIENNENT JOIGNABLES DEPUIS CE RELAIS, ET C'EST UN
       CHANGEMENT ASSUME. La version precedente de cette route ne lisait NI
       `medias` NI `media` : un brouillon deja joint d'un fichier restait
       strictement tel quel apres un passage par le relais. Le President a
       demande que ses membres autorises puissent repondre AVEC les medias
       deja presents dans la bibliotheque — ce qui exige d'ecrire ce champ.

       DEUX BORNES, QUI N'EXISTENT PAS POUR LE COACH LUI-MEME (une troisieme,
       `validee` exigee, a existe un temps — voir plus bas pourquoi elle a
       ete retiree) :

       1. PAR IDENTIFIANT DE BIBLIOTHEQUE UNIQUEMENT. `{"media_id": "..."}`
          et rien d'autre : un `fichier_url` (`/api/files/...`) est REFUSE ici,
          parce qu'un membre afroboosteur n'a, par construction, aucun fichier
          televerse a lui sur afroboost.com — accepter cette forme reviendrait
          a lui laisser designer les fichiers d'un AUTRE.
       2. LA RESOLUTION RESTE CELLE DU COACH CONFIGURE. `v625_resoudre_medias`
          est appelee avec `_coach_id_configure()`, jamais avec l'identite du
          membre : la bibliotheque engagee est celle du coach, et un
          identifiant qui ne lui appartient pas est refuse par la fonction
          elle-meme, sans que ce fichier ait a le reverifier.

       ⚠️ LE STATUT ACCEPTE N'EST PLUS BORNE A `validee` (correction du
          28/10/2026, mission du President). `v625_resoudre_medias` /
          `v620_resoudre_media` acceptent ICI exactement ce qu'ils acceptent
          pour LE COACH LUI-MEME repondant a un partenaire : tout statut SAUF
          `archivee` (donc `en_cours` et `a_verifier` aussi). La premiere
          version de ce canal exigeait `validee`, en calquant la frontiere du
          PARTAGE DE CAMPAGNE (`p3s3_medias_partages_valides`) — la mauvaise
          comparaison : une campagne diffuse a PLUSIEURS destinataires a la
          fois, ce qui justifie une barre plus haute ; repondre a UN
          partenaire est exactement le geste que le coach fait lui-meme, qui
          n'a jamais exige `validee`. Mesure en production : chaque media nait
          `en_cours` ou `a_verifier` (aucune validation automatique) — exiger
          `validee` ici revenait, en pratique, a fermer ce canal en
          permanence. Voir `_medias_valides_du_coach` pour le detail.

       Cle ABSENTE = champ inchange (meme semantique que la route du coach) ;
       liste VIDE = retirer les medias. `media` (singulier) est ecrit en meme
       temps, comme le fait la route du coach, pour les lecteurs V620.

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

    # V636 — LES MEDIAS, RESOLUS AVANT TOUTE ECRITURE. Voir les trois bornes du
    # docstring. Tout refus (identifiant inconnu, media non valide, forme
    # inattendue) part en 400 AVANT que quoi que ce soit ne soit ecrit : un
    # brouillon ne doit jamais se retrouver a moitie modifie.
    champ_media = None
    if "medias" in corps:
        champ_media = await _medias_valides_du_coach(corps.get("medias"))

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
    a_ecrire = {"reponse_proposee": texte_tronque,
                "motifs_validation": p3ai_sujets_sensibles(texte_tronque),
                "validation_requise": bool(p3ai_sujets_sensibles(texte_tronque)),
                "edite_le": maintenant,
                # INFORMATIF, comme X-Afroboosteur-Membre partout ailleurs dans ce
                # fichier — jamais une identite verifiee par afroboost.com.
                "edite_par": "afroboosteur:%s" % (membre or _coach_id_configure()),
                "updated_at": maintenant}
    if champ_media is not None:
        # MEMES DEUX CHAMPS QUE LA ROUTE DU COACH : `medias` fait foi,
        # `media` = le premier, pour tout lecteur V620 reste en place.
        a_ecrire["medias"] = champ_media
        a_ecrire["media"] = champ_media[0] if champ_media else None
    await db[P3AI_BROUILLONS].update_one(
        {"inbound_id": message["id"]},
        {"$set": a_ecrire,
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


# -----------------------------------------------------------------------------
# 5. PHASE 6B — MEDIATHEQUE PARTAGEE (V595) : consulter, et ajouter PAR LIEN
#
# PAS DE DUPLICATION DE FICHIERS. Ce relais ne stocke jamais un octet : il
# relit `prospection_medias`/`prospection_niches`, et pour l'ajout, relaie vers
# la MEME validation que l'ecran coach (`v595_ajouter_media_pour`).
#
# ⚠️ L'UPLOAD BINAIRE N'EST PAS REPRIS ICI, PAR CHOIX DELIBERE. `/api/coach/
# upload-asset` et `/api/coach/upload-chunk` exigent une identite COACH
# (JWT ou X-User-Email) pour attribuer et bornewr un fichier — une notion que
# ce relais n'a pas : son secret HMAC agit pour LE coach configure, jamais
# pour un membre afroboosteur precis, et accepter un gros binaire a travers un
# canal protege par un seul secret partage (sans antivirus, sans quota par
# auteur) aurait ete une SURFACE NOUVELLE, pas une reutilisation. Un membre
# qui veut ajouter un fichier neuf doit soit fournir un LIEN PUBLIC (accepte
# ci-dessous), soit demander au coach de l'envoyer directement sur
# afroboost.com. Si le President veut lever cette limite, cela merite un GO
# separe et explicite — ce n'est pas une omission a corriger sans le demander.
#
# AUCUN CHAMP « CONFIDENTIEL » N'EXISTE DANS LE SCHEMA V595 (verifie — zero
# occurrence dans tout server.py). La protection que ce lot apporte n'est donc
# pas de MASQUER des medias (la liste ci-dessous montre tout, comme demande :
# niches ET statuts existants), mais d'empecher qu'un media encore
# `en_cours`/`a_verifier` (jamais relu par le coach) soit SELECTIONNABLE pour
# une campagne — voir `p3s3_medias_partages_valides` : seul `validee` passe.
# -----------------------------------------------------------------------------

_PROJECTION_MEDIA = {
    "_id": 0, "id": 1, "niche": 1, "format": 1, "url": 1, "statut": 1,
    "version": 1, "created_at": 1, "updated_at": 1, "cible": 1, "cible_id": 1,
    "fichier.nom": 1, "fichier.type": 1, "fichier.taille": 1,
    "fichier.duree": 1, "fichier.largeur": 1, "fichier.hauteur": 1,
    # `notes` et `coach_id` : JAMAIS renvoyes — `notes` est une annotation
    # privee du coach, `coach_id` un detail interne sans utilite ici.
}

_STATUTS_MEDIA_FILTRABLES = ("en_cours", "a_verifier", "validee", "archivee")
_FORMATS_MEDIA_FILTRABLES = ("original", "16_9", "9_16", "1_1", "miniature", "document")


@router.get("/api/afroboosteur-relais/medias")
async def relais_lister_medias(request: Request):
    """Lecture pure de la mediatheque — images/videos/miniatures/PDF, niches
    et statuts existants, filtrables. Rien n'est masque par statut : c'est
    l'INSERTION dans une campagne qui est bornee a `validee`, pas la lecture
    (voir l'en-tete de cette section)."""
    await _garde(request)
    limite, depart = _pagination(request)
    filtre = _portee()
    parametres = request.query_params
    niche = (parametres.get("niche") or "").strip()[:64]
    if niche:
        filtre["niche"] = niche
    fmt = (parametres.get("format") or "").strip()
    if fmt:
        if fmt not in _FORMATS_MEDIA_FILTRABLES:
            raise HTTPException(status_code=400,
                                detail="Format inconnu. Valeurs acceptees : %s"
                                       % ", ".join(_FORMATS_MEDIA_FILTRABLES))
        filtre["format"] = fmt
    statut = (parametres.get("statut") or "").strip()
    if statut:
        if statut not in _STATUTS_MEDIA_FILTRABLES:
            raise HTTPException(status_code=400,
                                detail="Statut inconnu. Valeurs acceptees : %s"
                                       % ", ".join(_STATUTS_MEDIA_FILTRABLES))
        filtre["statut"] = statut
    total = await db[V595_MEDIAS].count_documents(filtre)
    lignes = await db[V595_MEDIAS].find(filtre, _PROJECTION_MEDIA) \
        .sort([("created_at", -1), ("id", 1)]).skip(depart).limit(limite).to_list(limite)
    return {"total": total, "returned": len(lignes), "limit": limite, "offset": depart,
            "medias": lignes}


@router.get("/api/afroboosteur-relais/niches")
async def relais_lister_niches(request: Request):
    """Les niches du coach — pour filtrer la mediatheque et choisir une cible
    de campagne. Lecture pure ; reutilise `v598_niches`, qui inscrit les six
    niches d'origine si elles manquent encore (idempotent, jamais destructeur)."""
    await _garde(request)
    from api.server import v598_niches

    niches = await v598_niches(_coach_id_configure())
    projetees = [{"id": n.get("id"), "cle": n.get("cle"), "nom": n.get("nom"),
                 "slug": n.get("slug"), "ordre": n.get("ordre"), "active": bool(n.get("active", True))}
                for n in niches]
    return {"total": len(projetees), "niches": projetees}


@router.post("/api/afroboosteur-relais/medias")
async def relais_ajouter_media(request: Request):
    """Ajoute un media PAR LIEN PUBLIC uniquement — voir l'en-tete de cette
    section pour pourquoi l'upload binaire n'est pas repris ici. Relaie vers
    `v595_ajouter_media_pour`, la MEME validation que l'ecran coach (niche
    active, format autorise, lien public anti-SSRF) : aucune logique
    parallele qui pourrait diverger.

    Entre « en cours », jamais « validee » — comme pour le coach : un ajout
    depuis ce relais ne rend jamais un media immediatement selectionnable
    pour une campagne (`p3s3_medias_partages_valides` exige `validee`). Le
    coach reste seul a faire passer un media au statut valide.
    """
    await _garde(request)
    from api.server import v595_ajouter_media_pour

    try:
        corps = await request.json()
    except Exception:
        corps = {}
    if not isinstance(corps, dict):
        raise HTTPException(status_code=400, detail="Corps JSON attendu")
    url_brute = str(corps.get("url") or "").strip()
    if url_brute.startswith("/api/files/"):
        raise HTTPException(
            status_code=400,
            detail="Un fichier deja envoye sur afroboost.com ne peut pas etre reference depuis ce relais "
                   "— utilisez un lien public, ou demandez au coach de l'ajouter directement.")
    corps_relais = {
        "niche": corps.get("niche"),
        "format": corps.get("format"),
        "url": url_brute,
        "version": corps.get("version"),
        "cible": corps.get("cible"),
        # `notes` : JAMAIS transmis depuis ce relais (annotation privee du coach).
    }
    # REVUE DE SECURITE — P6B : `proteger_valides=True`, voir le docstring de
    # `v595_ajouter_media_pour`. Un media `validee` ne peut JAMAIS etre
    # demotionne par ce relais, quel que soit l'emplacement vise.
    resultat = await v595_ajouter_media_pour(_coach_id_configure(), corps_relais, proteger_valides=True)
    media = resultat.get("media")
    if isinstance(media, dict):
        resultat["media"] = {cle: media.get(cle) for cle in _PROJECTION_MEDIA if cle != "_id" and "." not in cle}
        if media.get("fichier"):
            resultat["media"]["fichier"] = {
                "nom": media["fichier"].get("nom"), "type": media["fichier"].get("type"),
                "taille": media["fichier"].get("taille"), "duree": media["fichier"].get("duree"),
                "largeur": media["fichier"].get("largeur"), "hauteur": media["fichier"].get("hauteur"),
            }
    return resultat


# -----------------------------------------------------------------------------
# 6. PHASE 6C (ETAPE 1A) — LECTURE SEULE : LE FIL D'UNE CONVERSATION, LES
#    ECHEANCES D'UNE CAMPAGNE. DEUX ROUTES NEUVES, ISOLEES, DESACTIVEES PAR
#    DEFAUT — AUCUNE ROUTE EXISTANTE N'EST MODIFIEE PAR CETTE SECTION.
#
# POURQUOI DEUX INTERRUPTEURS SEPARES DE `AFROBOOSTEUR_RELAY_SECRET`. Le
# secret et le coach_id restent la PREMIERE porte (`_garde`, deja verifiee
# avant d'arriver ici) : sans eux, tout le relais est inerte, ces deux routes
# comprises. `AFROBOOSTEUR_RELAIS_FIL_ACTIF` et `AFROBOOSTEUR_RELAIS_
# RELANCES_ACTIF` sont une SECONDE porte, par fonctionnalite : le President
# peut ouvrir l'une sans l'autre, et les fermer toutes deux sans toucher au
# reste du relais deja en service (prospects, campagnes, conversations,
# brouillon, mediatheque). Meme convention que `POSTHOG_SERVER_ENABLED`
# (api/routes/shared.py) — jamais une regle inventee ici.
#
# LECTURE SEULE ABSOLUE, DANS LES DEUX SENS DU MOT :
#   - aucune ecriture Mongo dans cette section (aucun `insert_one`,
#     `update_one`, `delete_one`) ;
#   - aucun appel a `p3r2_reserver`, `p3r2_envoyer_relance`, ni a la boucle de
#     fond `_v604_boucle_relances` : le moteur de relances n'est JAMAIS
#     sollicite. `p3r2_garde_relance(..., simulation=True)` est une fonction
#     PURE (aucun acces base) qui rend un VERDICT, jamais une ACTION.
#
# RATTACHEMENT TECHNIQUE, JAMAIS PAR ADRESSE E-MAIL. Les messages recus d'un
# meme dossier sont retrouves par LE MEME `action_id` que le reste du
# chantier (`pf_cle_conversation`, deja utilise par le tableau de bord du
# coach) — jamais en comparant des adresses. Un message recu SANS action
# associee reste seul : il n'est jamais regroupe avec un autre message, quand
# bien meme les deux partageraient un expediteur.
#
# PERIMETRE ET DONNEES PERSONNELLES. Chaque lecture passe par `_portee()`
# (le coach_id configure, jamais un filtre vide) — y compris pour la
# campagne et les actions d'une relance, verifie par cette section en plus
# de la tenance deja portee par `campaign_id` sur l'action. Aucune des deux
# routes ne renvoie `target` (l'adresse ou le numero reel du destinataire) :
# la route des relances ne sert qu'a decider SI une relance pourrait partir,
# jamais A QUI exactement — comme le reste du relais.
# -----------------------------------------------------------------------------

_PROJECTION_MESSAGE_FIL = {
    "_id": 0, "id": 1, "action_id": 1, "received_at": 1, "subject": 1,
    "body_text": 1, "body_quoted": 1, "from_email": 1, "contenu_recupere": 1,
    "provider_email_id": 1,
}

_PROJECTION_ACTION_TRACE = {
    "_id": 0, "id": 1, "action_id": 1, "inbound_id": 1, "sent_at": 1,
    "updated_at": 1, "created_at": 1, "subject": 1, "send_status": 1,
    "provider_status": 1, "approved_text": 1, "provider_message_id": 1,
    "media": 1, "medias": 1,
}


@router.get("/api/afroboosteur-relais/conversations/{inbound_id}/fil")
async def relais_fil_conversation(inbound_id: str, request: Request):
    """Le fil chronologique COMPLET d'UN dossier : premier contact, messages
    recus, reponses envoyees, relances parties — dans l'ordre, avec leurs
    dates et statuts de remise. LECTURE SEULE : reutilise EXACTEMENT
    `v619_fil`, deja prouve par le tableau de bord du coach (`pf_charger`),
    jamais une seconde implementation.

    Le dossier est celui de CE message (`pf_cle_conversation`) : s'il porte
    une `action_id`, tous les messages recus de LA MEME action forment le
    fil ; sinon, le fil ne contient QUE ce message — jamais un regroupement
    par adresse e-mail.
    """
    await _garde(request)
    if not _fil_actif():
        raise HTTPException(status_code=503, detail="Fil de conversation non activé")

    from api.server import P3AI4_COLLECTION, P3S3_ACTIONS, v619_fil, v619_preuves

    message = await _message_de_la_portee(inbound_id)
    action_id = str(message.get("action_id") or "").strip()

    if action_id:
        # TENANCE VERIFIEE UNE SECONDE FOIS, EXPLICITEMENT, SUR L'ACTION :
        # `message` est deja dans la portee, mais une action orpheline ou mal
        # rattachee ne doit jamais elargir silencieusement le fil a autre
        # chose que ce coach. Absente ou hors portee -> traite comme un
        # dossier SANS action (repli surete, jamais un fil plus large).
        action = await db[P3S3_ACTIONS].find_one(
            {"id": action_id, **_portee()}, {"_id": 0})
        if not action:
            action_id = ""

    if action_id:
        messages_recus = await db[P3U2_COLLECTION].find(
            {"action_id": action_id, **_portee()}, _PROJECTION_MESSAGE_FIL) \
            .sort([("received_at", 1), ("id", 1)]).to_list(500)
        campagne = {}
        preuve = {}
        campaign_id = action.get("campaign_id") if action else None
        if campaign_id:
            campagnes, preuves = await v619_preuves([campaign_id])
            campagne = campagnes.get(campaign_id) or {}
            preuve = preuves.get(campaign_id) or {}
        traces = await db[P3AI4_COLLECTION].find(
            {"action_id": action_id, **_portee()}, _PROJECTION_ACTION_TRACE) \
            .to_list(500)
    else:
        action = {}
        campagne = {}
        preuve = {}
        # Dossier SANS action : son fil ne contient jamais que ce message —
        # jamais un autre message, meme de la meme adresse.
        messages_recus = [{k: message.get(k) for k in _PROJECTION_MESSAGE_FIL if k != "_id"}]
        traces = await db[P3AI4_COLLECTION].find(
            {"inbound_id": message["id"], **_portee()}, _PROJECTION_ACTION_TRACE) \
            .to_list(500)

    fil = v619_fil(messages_recus, action, campagne, preuve, traces)
    return {
        "inbound_id": message["id"],
        "campaign_id": (action or {}).get("campaign_id"),
        "returned": len(fil),
        "fil": fil,
    }


_PROJECTION_ACTION_RELANCE = {
    "_id": 0, "id": 1, "recipient_key": 1, "organisations": 1, "cities": 1,
    "channel": 1, "target": 1, "statut": 1, "execution_type": 1,
    "bounce_type": 1, "suivi_humain": 1, "suivi_livraison": 1,
    "sent_at": 1, "provider_status": 1, "replied_at": 1,
    "interesse_at": 1, "paused_at": 1, "prospect_ids": 1, "prospect_uuids": 1,
    "message_j3": 1, "message_j7": 1, "message_j14": 1,
    "j3_due_at": 1, "j3_sent_at": 1, "j3_annule_le": 1, "j3_annule_motif": 1,
    "j3_provider_status": 1, "j3_claimed_at": 1, "j3_verrou": 1,
    "j7_due_at": 1, "j7_sent_at": 1, "j7_annule_le": 1, "j7_annule_motif": 1,
    "j7_provider_status": 1, "j7_claimed_at": 1, "j7_verrou": 1,
    "j14_due_at": 1, "j14_sent_at": 1, "j14_annule_le": 1, "j14_annule_motif": 1,
    "j14_provider_status": 1, "j14_claimed_at": 1, "j14_verrou": 1,
}

_CHAMPS_ETAPE_EXPOSES = ("due_at", "sent_at", "annule_le", "annule_motif", "provider_status")


@router.get("/api/afroboosteur-relais/campaigns/{campaign_id}/relances")
async def relais_relances_campagne(campaign_id: str, request: Request):
    """Les echeances J+3 / J+7 / J+14 d'UNE campagne — dates prevues,
    envoyees, annulees, statut fournisseur, et le VERDICT (le meme code que
    le moteur rendrait) pour chaque relance pas encore partie.

    LECTURE SEULE ABSOLUE — `p3r2_garde_relance(..., simulation=True)` est une
    fonction PURE (aucun acces base) : elle REND un verdict, elle n'ENVOIE ni
    ne RESERVE jamais rien. Le moteur reel (`p3r2_executer_relances`, la
    boucle de fond, `p3r2_reserver`) n'est appele nulle part dans cette route.

    Jamais `target` (l'adresse ou le numero reel) dans la reponse : cette
    route dit SI une relance pourrait partir, jamais A QUI precisement.
    """
    await _garde(request)
    if not _relances_actif():
        raise HTTPException(status_code=503, detail="Suivi des relances non activé")

    from api.server import (
        P3R2_ETAPES, P3S3_ACTIONS, c3_refus_exprimes, p3r2_champ,
        p3r2_garde_relance, p3r2_relations_humaines,
    )

    identifiant = (campaign_id or "").strip()[:64]
    campagne = await db[P3S3_CAMPAGNES].find_one(
        dict(_portee(), id=identifiant), _PROJECTION_CAMPAGNE)
    if not campagne:
        raise HTTPException(status_code=404, detail="Campagne introuvable")

    limite, depart = _pagination(request)
    filtre_actions = {"campaign_id": identifiant, **_portee()}
    total = await db[P3S3_ACTIONS].count_documents(filtre_actions)
    actions = await db[P3S3_ACTIONS].find(filtre_actions, _PROJECTION_ACTION_RELANCE) \
        .sort([("recipient_key", 1), ("id", 1)]).skip(depart).limit(limite).to_list(limite)

    # LE MEME CALCUL DE REFUS QUE LE MOTEUR (p3r2_executer_relances) — lecture
    # seule sur le registre STOP, jamais une ecriture.
    refus = set()
    par_canal: dict = {}
    for a in actions:
        canal = (a.get("channel") or "").strip().lower()
        if canal:
            par_canal.setdefault(canal, []).append(a.get("target"))
    for canal, valeurs in par_canal.items():
        for v in await c3_refus_exprimes(canal, valeurs):
            refus.add(f"{canal}:{v}")
    humains = await p3r2_relations_humaines(actions)

    maintenant = datetime.now(timezone.utc).isoformat()
    lignes = []
    for action in actions:
        a = dict(action)
        if a.get("id") in humains:
            a["_relation_humaine"] = humains[a["id"]]
        relances = {}
        for etape in P3R2_ETAPES:
            champs = {champ: a.get(p3r2_champ(etape, champ)) for champ in _CHAMPS_ETAPE_EXPOSES}
            verdict = p3r2_garde_relance(
                a, campagne, etape, refus=refus, maintenant=maintenant,
                envoi_autorise=False, simulation=True)
            relances[etape] = {
                **champs,
                "autorise_si_execute": verdict["autorise"],
                "code": verdict["code"],
                "motif": verdict["motif"],
            }
        lignes.append({
            "id": a.get("id"),
            "recipient_key": a.get("recipient_key"),
            "organisations": a.get("organisations") or [],
            "cities": a.get("cities") or [],
            "statut": a.get("statut"),
            "premier_contact_envoye": bool(a.get("sent_at")),
            "a_repondu": bool(a.get("replied_at")),
            "relances": relances,
        })

    return {
        "campaign_id": identifiant, "campaign_etat": campagne.get("etat"),
        "total": total, "returned": len(lignes), "limit": limite, "offset": depart,
        "actions": lignes,
    }


# -----------------------------------------------------------------------------
# 7. PHASE 6D — AIDE IA POUR RÉDIGER UNE RÉPONSE : UNE SEULE ROUTE, UN SEUL
#    CALCUL, AUCUNE ÉCRITURE. INTERRUPTEUR SÉPARÉ, FERMÉ PAR DÉFAUT — MÊME
#    CONVENTION QUE LE FIL ET LES RELANCES (SECTION 6 CI-DESSUS).
#
# POURQUOI UNE ROUTE DE RELAIS DÉDIÉE, PAS UN RELAIS GÉNÉRIQUE VERS
# `/ai/enhance-text`. Cette route-là exige un JWT coach (`_v309_require_coach_
# or_admin`) — une notion que ce relais n'a pas : son secret HMAC agit POUR le
# coach configuré, jamais pour un membre afroboosteur précis (même raison que
# `/api/coach/upload-asset` plus haut, voir section 5). Reconstruire la MÊME
# logique derrière une porte différente serait une divergence ; l'appeler
# directement depuis ce fichier, EN RÉUTILISANT sa fonction de calcul
# (`_v633_ameliorer_texte`, extraite lors de ce lot sans changer son
# comportement), ferme ce trou sans dupliquer les prompts ni le modèle.
#
# AUCUNE ÉCRITURE MONGO DANS CETTE SECTION. Le texte amélioré est rendu à
# l'appelant ; c'est `POST .../brouillon` (section 4) qui l'enregistre, si le
# membre choisit de le garder — deux gestes distincts, comme pour le coach
# (le bouton "Améliorer" du dashboard n'enregistre rien non plus tout seul).
#
# LE MÊME BUDGET QUE LE COACH, PAS UN SUPPLÉMENTAIRE. `_v633_debit_ok` est
# RÉUTILISÉE telle quelle, avec une clé préfixée `relais:` — un membre
# afroboosteur et le coach lui-même ne partagent donc pas le même compteur
# (éviter qu'un pic d'un côté referme l'assistant de l'autre), mais aucun des
# deux ne peut consommer plus que les bornes déjà fixées par V633
# (20/minute, 300/jour). Le secret HMAC agit pour LE coach configuré : sans
# ce préfixe, un seul compteur partagé aurait pu être vidé par l'un des deux
# canaux au détriment de l'autre.
#
# ENTRÉES BORNÉES À L'IDENTIQUE DE V633 (`_V633_TEXTE_MAX`, `_V633_LANG`) —
# jamais une seconde borne qui pourrait diverger de celle déjà prouvée par le
# dashboard coach.
# -----------------------------------------------------------------------------

_V633_CONTEXTES_CONNUS = (
    "offer", "pack", "legal", "seo", "faq_answer", "general", "afroboost", "expert",
)


@router.post("/api/afroboosteur-relais/ia/ameliorer-texte")
async def relais_ameliorer_texte(request: Request):
    """Améliore/corrige/reformule un texte de réponse — AUCUNE écriture, AUCUN
    envoi. Reprend `_v633_ameliorer_texte` (api/server.py), la MÊME fonction
    que `/ai/enhance-text` appelle pour le coach — mêmes prompts, même modèle,
    jamais une seconde implémentation.
    """
    membre = await _garde(request)
    if not _ia_actif():
        raise HTTPException(status_code=503, detail="Assistance IA non activée")

    from api.server import _v633_ameliorer_texte, _v633_debit_ok, _V633_LANG, _V633_TEXTE_MAX

    cle_debit = "relais:%s" % (membre or _coach_id_configure())
    if not _v633_debit_ok(cle_debit):
        raise HTTPException(status_code=429, detail="Trop de demandes à l'assistant IA — réessayez dans un instant")

    try:
        corps = await request.json()
    except Exception:
        corps = {}
    if not isinstance(corps, dict):
        raise HTTPException(status_code=400, detail="Corps JSON attendu")

    texte_brut = corps.get("text", "")
    if not isinstance(texte_brut, str):
        raise HTTPException(status_code=400, detail="Le texte doit être une chaîne")
    texte = texte_brut.strip()
    if not texte:
        raise HTTPException(status_code=400, detail="Le texte est requis")
    if len(texte) > _V633_TEXTE_MAX:
        raise HTTPException(status_code=400, detail="Texte trop long pour l'assistant IA")

    contexte = corps.get("context") or "general"
    if not isinstance(contexte, str) or contexte not in _V633_CONTEXTES_CONNUS:
        contexte = "general"

    langue = corps.get("lang", "fr")
    if not isinstance(langue, str) or not _V633_LANG.match(langue):
        langue = "fr"

    resultat = await _v633_ameliorer_texte(texte, contexte, langue)
    logger.info("%s amelioration IA demandee par membre afroboosteur=%s (contexte=%s)",
               PREFIXE, membre or "(non precise)", contexte)
    return resultat

# -----------------------------------------------------------------------------
# 8. V636 — L'ENVOI REEL D'UNE REPONSE, DEPUIS AFROBOOSTEUR.COM
#
# ⚠️ CECI LEVE LA RESERVE ECRITE EN TETE DE CE MODULE DEPUIS LA PHASE 6A.
#    Elle disait : « La reservation et l'appel au fournisseur, qui existent
#    deja et fonctionnent pour le coach, ne sont deliberement PAS repris ici
#    tant qu'un GO explicite et separe n'autorise pas l'envoi reel depuis ce
#    relais. » Ce GO a ete donne. La reserve est donc levee — mais remplacee
#    par TROIS verrous independants, dont aucun n'est ouvert par ce commit :
#
#      1. `AFROBOOSTEUR_RELAIS_ENVOI_ACTIF` (ici, variable d'environnement) —
#         ferme par defaut, comme FIL_ACTIF et RELANCES_ACTIF. Ferme, cette
#         route repond 503 et ne touche RIEN ;
#      2. `P3_REPONSE_ACTIF` (drapeau EN BASE, defaut False) ;
#      3. `P3_REPONSE_ENVOI_REEL` (drapeau EN BASE, defaut False).
#
#    Les deux derniers sont ceux du coach, lus a CHAQUE envoi dans
#    `p3ai4_envoyer_reponse_pour` : ils ferment l'envoi reel en une seconde
#    depuis le tableau de bord, pour le coach ET pour ce relais, sans
#    redeploiement. Les trois doivent etre ouverts pour qu'un seul e-mail
#    parte. Tant qu'ils ne le sont pas, un appel ici REUSSIT mais le
#    fournisseur est court-circuite (`ENVOI_NON_AUTORISE`) — la trace est
#    posee, l'e-mail ne part pas.
#
# AUCUNE REGLE N'EST REECRITE ICI. Proprietaire, brouillon present, champ
# « [A COMPLETER] », empreinte concordante, idempotence, contexte perime,
# destinataire resolu, registre STOP, corbeille V627 : tout cela vit dans
# `p3ai4_envoyer_reponse_pour` (api/server.py), la MEME fonction que la route
# du coach appelle — extraite pour ce lot, sans qu'une seule de ses lignes ne
# change. Un durcissement futur profitera aux deux appelants le meme jour.
#
# QUI A ENVOYE, ET AU NOM DE QUI. `approved_by` reste le coach configure
# (c'est sa tenance, sa bibliotheque, ses quotas) ; `approved_by_membre` porte
# l'identite du membre afroboosteur transmise dans `X-Afroboosteur-Membre`.
# Cette en-tete reste INFORMATIVE — elle n'autorise rien : l'autorite a deja
# tranche cote afroboosteur.com (le droit « repondre aux partenaires »,
# reverifie a chaque requete) AVANT que cette route ne soit appelee.
# -----------------------------------------------------------------------------


@router.post("/api/afroboosteur-relais/conversations/{inbound_id}/envoyer")
async def relais_envoyer_reponse(inbound_id: str, request: Request):
    """Envoie la reponse preparee — reservation, fournisseur, trace, note.

    Corps attendu : `{"draft_hash": "...", "confirme": true}` — exactement
    celui de la route du coach, a qui le corps est transmis tel quel.

    Rend ce que rend la route du coach : `{"deja_envoye": bool, "envoi": {...},
    "statut_commercial": "..."}`. Un rejeu rend `deja_envoye: true` et un 200,
    jamais une erreur : c'est ce qui rend le double clic inoffensif.
    """
    membre = await _garde(request)
    if not _envoi_actif():
        raise HTTPException(status_code=503, detail="Envoi depuis afroboosteur non activé")

    from api.server import p3ai4_envoyer_reponse_pour

    # LA PORTEE D'ABORD : un dossier hors du coach configure n'existe pas pour
    # ce relais (404), avant meme que la fonction d'envoi ne soit appelee.
    message = await _message_de_la_portee(inbound_id)

    # V636b — LES MEDIAS SONT REVERIFIES ICI, AVANT TOUTE RESERVATION. Exiger
    # `validee` seulement a l'ecriture du brouillon ne disait rien de ce qui
    # part : le coach peut attacher un media `en_cours` depuis son propre
    # tableau de bord, et un media archive apres coup reste dans l'instantane.
    # Voir `_refuser_medias_plus_valides`.
    await _refuser_medias_plus_valides(message["id"])

    try:
        corps = await request.json()
    except Exception:
        corps = {}
    if not isinstance(corps, dict):
        raise HTTPException(status_code=400, detail="Corps JSON attendu")

    resultat = await p3ai4_envoyer_reponse_pour(
        _coach_id_configure(), message["id"], corps, membre_externe=membre or None)

    # `compteurs` et tout autre champ propre au tableau de bord du coach ne
    # traversent pas : ce relais ne rend que ce dont l'ecran afroboosteur a
    # besoin pour dire ce qui s'est passe.
    envoi = resultat.get("envoi") or {}
    return {
        "deja_envoye": bool(resultat.get("deja_envoye")),
        "statut_commercial": resultat.get("statut_commercial"),
        "envoi": {cle: envoi.get(cle) for cle in (
            "id", "send_status", "provider_status", "sent_at", "error_code",
            "subject", "approved_at", "approved_by_membre", "medias", "media",
        )},
    }

