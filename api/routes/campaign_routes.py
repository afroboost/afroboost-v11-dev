# campaign_routes.py - Routes campagnes v9.1.2
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
import uuid
import logging

logger = logging.getLogger(__name__)

# Constantes
SUPER_ADMIN_EMAIL = "contact.artboost@gmail.com"  # héritage (lu par d'anciens imports)


def is_super_admin(email: str) -> bool:
    # MT-1 : alignée sur `api.routes.shared.is_super_admin`, qui connaît les DEUX
    # super-admins. L'ancienne version n'en reconnaissait qu'un : le second
    # (afroboost.bassi@gmail.com) était traité ici comme un coach ordinaire.
    from api.routes.shared import is_super_admin as _is_super_admin_partage
    return bool(_is_super_admin_partage(email))

# Router
campaign_router = APIRouter(tags=["campaigns"])

# Variable db sera injectée depuis server.py
db = None

def init_campaign_db(database):
    global db
    db = database


# =====================================================================
# MT-1 — CAMPAGNES MULTI-COACH : IDENTITÉ SIGNÉE + PÉRIMÈTRE PROPRIÉTAIRE
# =====================================================================
# Règle unique, appliquée à chaque route de campagne :
#   1. identité = JWT SIGNÉ uniquement (`coach_jwt_email`) — `X-User-Email` n'est
#      JAMAIS lu pour décider d'un accès ni d'un périmètre ;
#   2. super-admin (les DEUX, `shared.is_super_admin`) -> portée globale ;
#   3. coach -> uniquement ses campagnes (`tenant_contacts.filtre_proprietaire`) ;
#   4. objet d'un autre coach en lecture -> 404 (on ne révèle pas son existence).
#
# DESTINATAIRES : le périmètre d'un envoi est celui du PROPRIÉTAIRE de la
# campagne (`campaign.coach_id`), jamais celui de l'appelant du moment — le
# moteur programmé n'a d'ailleurs pas d'appelant. Propriétaire super-admin ou
# campagne historique sans propriétaire exploitable -> comportement global
# INCHANGÉ (non-régression admin).

# MT-1 : valeurs de `coach_id` qui ne désignent aucun coach réel (historique).
_MT1_SANS_PROPRIETAIRE = {"", "bassi_default", "none", "null"}


async def mt1_appelant_signe(request: Request, quoi: str = "campagnes") -> str:
    """MT-1 : e-mail coach/admin porté par un JWT SIGNÉ, sinon 403. Aucun repli.

    Même règle que `_v309_require_coach_or_admin` (server.py) : jeton coach
    vérifié (les jetons abonné sont rejetés par `coach_jwt_email`), puis rôle
    relu en base (`coaches` / `coach_auth`) — le navigateur ne décide de rien.
    """
    from api.routes.shared import coach_jwt_email
    email = coach_jwt_email(request)
    if not email:
        logger.warning("[MT-1] REFUS %s — aucun jeton coach signé", quoi)
        raise HTTPException(status_code=403, detail="Authentification coach requise — reconnectez-vous")
    if is_super_admin(email):
        return email
    try:
        if await db.coaches.find_one({"email": email}, {"_id": 1}):
            return email
        if await db.coach_auth.find_one({"email": email}, {"_id": 1}):
            return email
    except Exception as _e:
        logger.warning("[MT-1] vérification du rôle impossible (%s)", type(_e).__name__)
    logger.warning("[MT-1] REFUS %s — jeton valide mais ni coach ni admin", quoi)
    raise HTTPException(status_code=403, detail="Authentification coach requise — reconnectez-vous")


def mt1_filtre_campagnes(appelant: str) -> dict:
    """MT-1 : `{}` pour un super-admin, `{"coach_id": e-mail}` pour un coach."""
    from api.routes.tenant_contacts import filtre_proprietaire, PerimetreRefuse
    try:
        return filtre_proprietaire(appelant)
    except PerimetreRefuse:
        raise HTTPException(status_code=403, detail="Authentification coach requise — reconnectez-vous")


async def mt1_campagne_visible(campaign_id: str, appelant: str, projection=None) -> dict:
    """MT-1 : la campagne si elle est dans le périmètre de l'appelant, sinon 404."""
    if not isinstance(campaign_id, str) or not campaign_id or "$" in campaign_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    _q = {"id": campaign_id}
    _q.update(mt1_filtre_campagnes(appelant))
    campagne = await db.campaigns.find_one(_q, projection or {"_id": 0})
    if not campagne:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campagne


def mt1_proprietaire_restreint(campaign: dict) -> str:
    """MT-1 : e-mail du coach propriétaire dont le PORTEFEUILLE borne les envois.

    '' = portée globale (comportement historique inchangé) : propriétaire
    super-admin, ou campagne sans propriétaire exploitable (absent, "",
    "bassi_default"…). Toute autre valeur = un coach -> périmètre restreint.
    """
    _brut = (campaign or {}).get("coach_id")
    _e = _brut.strip().lower() if isinstance(_brut, str) else ""
    if _e in _MT1_SANS_PROPRIETAIRE or is_super_admin(_e):
        return ""
    return _e


async def mt1_portefeuille(database, proprietaire: str) -> dict:
    """MT-1 : ids et e-mails du portefeuille d'un coach, en DEUX requêtes groupées.

    Même définition que `tenant_contacts` (module partagé, non modifié ici) :
    `users` visibles via `filtre_users_du_coach` + `chat_participants` dont
    `coach_id` == propriétaire. Chargé une fois par envoi (jamais un find_one
    par contact : groupes de 800+ membres).
    """
    from api.routes.tenant_contacts import filtre_users_du_coach, normaliser_email
    _ids, _emails = set(), set()
    _uf = await filtre_users_du_coach(database, proprietaire)
    async for _u in database.users.find(_uf, {"_id": 0, "id": 1, "email": 1}):
        if _u.get("id"):
            _ids.add(_u["id"])
        _m = normaliser_email(_u.get("email"))
        if _m:
            _emails.add(_m)
    async for _p in database.chat_participants.find({"coach_id": proprietaire}, {"_id": 0, "id": 1, "email": 1}):
        if _p.get("id"):
            _ids.add(_p["id"])
        _m = normaliser_email(_p.get("email"))
        if _m:
            _emails.add(_m)
    return {"proprietaire": proprietaire, "ids": _ids, "emails": _emails}


async def mt1_filtrer_cibles(database, portefeuille: dict, ids) -> list:
    """MT-1 : ne garde, parmi des cibles brutes (`targetIds`, `selectedContacts`),
    que celles du portefeuille : contact (users / chat_participants) ou
    conversation/groupe (`chat_sessions`) appartenant au propriétaire.

    Un id d'un autre coach est RETIRÉ SILENCIEUSEMENT ; seul le NOMBRE retiré est
    journalisé (aucune donnée personnelle dans les logs). Ordre conservé.
    """
    from api.routes.tenant_contacts import contact_appartient
    _out, _retires = [], 0
    for _i in ids or []:
        if not isinstance(_i, str) or not _i.strip():
            continue
        if _i in portefeuille["ids"]:
            _out.append(_i)
            continue
        try:
            _ok = await contact_appartient(database, portefeuille["proprietaire"], "chat_sessions", _i)
        except Exception:
            _ok = False
        if _ok:
            _out.append(_i)
        else:
            _retires += 1
    if _retires:
        logger.warning("[MT-1] %d cible(s) hors portefeuille du propriétaire retirée(s)", _retires)
    return _out


def mt1_filtrer_contacts(portefeuille: dict, contacts) -> list:
    """MT-1 : filtre final des contacts RÉSOLUS (groupes dépliés, segments,
    replis par conversation) : id OU e-mail dans le portefeuille du propriétaire."""
    from api.routes.tenant_contacts import normaliser_email
    _out, _retires = [], 0
    for _c in contacts or []:
        if (_c.get("id") in portefeuille["ids"]
                or normaliser_email(_c.get("email")) in portefeuille["emails"]):
            _out.append(_c)
        else:
            _retires += 1
    if _retires:
        logger.warning("[MT-1] %d destinataire(s) hors portefeuille du propriétaire écarté(s)", _retires)
    return _out

# === MODÈLES ===
class CampaignCreate(BaseModel):
    name: str
    message: str
    mediaUrl: Optional[str] = None
    mediaFormat: Optional[str] = None
    mediaType: Optional[str] = None  # v11: 'upload', 'youtube', 'drive', 'image', 'link'
    targetType: str = "all"
    selectedContacts: Optional[List[str]] = []
    channels: dict = {}
    targetGroupId: Optional[str] = None
    targetIds: Optional[List[str]] = []
    targetConversationId: Optional[str] = None
    targetConversationName: Optional[str] = None
    scheduledAt: Optional[str] = None
    ctaType: Optional[str] = None
    ctaText: Optional[str] = None
    ctaLink: Optional[str] = None
    # v11: Prompts indépendants par campagne
    systemPrompt: Optional[str] = None
    descriptionPrompt: Optional[str] = None
    # V154: Ciblage par catégories de contacts
    targetCategories: Optional[List[str]] = []
    categoryFilterMode: str = "any"  # "any" = OR, "all" = AND

# === ENDPOINTS CAMPAGNES ===
@campaign_router.get("/campaigns")
async def get_campaigns(request: Request):
    """Récupère les campagnes du coach authentifié (super-admin : toutes).

    MT-1 : avant, le périmètre se lisait dans `X-User-Email` BRUT — l'e-mail
    super-admin en en-tête suffisait, même en anonyme ou devant le JWT valide
    d'un autre coach, à lister TOUTES les campagnes (messages, cibles, résultats
    nominatifs). Désormais : JWT signé exigé, périmètre tiré du jeton seul.
    Appelant : CoachDashboard.js `loadCampaigns` (axios -> Bearer par
    l'intercepteur global d'App.js).
    """
    appelant = await mt1_appelant_signe(request, "liste des campagnes")
    campaigns = await db.campaigns.find(mt1_filtre_campagnes(appelant), {"_id": 0}).sort("createdAt", -1).to_list(100)
    return campaigns

@campaign_router.get("/campaigns/logs")
async def get_campaigns_error_logs(request: Request):
    """Renvoie les 50 dernières erreurs d'envoi de campagnes.

    V2-0 : route FERMÉE. Elle répondait 200 à un anonyme et livrait
    `campaign_name`, `contact_id` et surtout `contact_name` — nominatif, toutes
    campagnes de tous les coachs confondues. Elle n'avait pas de paramètre
    `Request`. Anomalie d'autant plus nette qu'elle est encadrée, dans ce même
    fichier, par des routes qui lisent une identité (l.52 et suivantes).

    Jeton signé exigé, sans repli : `campaigns/logs` n'apparaît ni dans
    `frontend/src` ni dans les bundles déployés. L'état `campaignLogs` du
    dashboard existe mais il est alimenté UNIQUEMENT côté navigateur
    (`CoachDashboard.js:3381`) — le vrai endpoint de journaux du dashboard est
    `/ai-logs`, qui n'est pas celui-ci.

    ⚠️ Le filtre coach est posé sur `campaigns` (`v20_perimetre_contacts`), mais
    PAS sur `campaign_errors` : aucun de ses 94 documents ne porte de `coach_id`,
    donc aucun cadrage n'y est démontrable. Ils restent réservés au super-admin,
    à qui `v20_perimetre_contacts` rend `{}`. Un coach ordinaire n'en verra
    aucun : fail-closed assumé plutôt qu'attribution inventée.
    """
    from api.routes.shared import (v20_exiger_coach_signe, v20_perimetre_contacts,
                                   V20AccesRefuse)
    _appelant = await v20_exiger_coach_signe(request, db, "journaux de campagnes")
    try:
        _perimetre = v20_perimetre_contacts(_appelant)
    except V20AccesRefuse:
        raise HTTPException(status_code=403, detail="Authentification coach requise")
    try:
        error_logs = []
        # V2-0 : le périmètre du coach entre dans la requête. Vide `{}` pour le
        # super-admin, donc comportement RIGOUREUSEMENT identique pour lui.
        _q_campagnes = {"results": {"$exists": True, "$ne": []}}
        _q_campagnes.update(_perimetre)
        campaigns_with_results = await db.campaigns.find(_q_campagnes, {"_id": 0, "id": 1, "name": 1, "results": 1, "updatedAt": 1}).sort("updatedAt", -1).to_list(100)
        for campaign in campaigns_with_results:
            campaign_id = campaign.get("id", "")
            campaign_name = campaign.get("name", "Sans nom")
            for result in campaign.get("results", []):
                if result.get("status") == "failed" or result.get("error"):
                    error_logs.append({
                        "source": "campaign_result", "campaign_id": campaign_id, "campaign_name": campaign_name,
                        "contact_id": result.get("contactId", ""), "contact_name": result.get("contactName", ""),
                        "channel": result.get("channel", "unknown"), "error": result.get("error", "Erreur inconnue"),
                        "sent_at": result.get("sentAt", campaign.get("updatedAt", "")), "status": "failed"
                    })
        try:
            # V2-0 : `campaign_errors` ne porte AUCUN coach_id (94/94 documents).
            # Impossible de le cadrer honnêtement -> réservé au super-admin. Un
            # coach ordinaire n'en reçoit aucun plutôt qu'un lot mal attribué.
            twilio_errors = ([] if _perimetre else
                             await db.campaign_errors.find({}, {"_id": 0}).sort("created_at", -1).to_list(50))
            for terr in twilio_errors:
                error_logs.append({
                    "source": "twilio_diagnostic", "campaign_id": terr.get("campaign_id", ""),
                    "channel": "whatsapp", "error": terr.get("error_message", ""),
                    "sent_at": terr.get("created_at", ""), "status": "failed"
                })
        except Exception:
            pass
        error_logs.sort(key=lambda x: x.get("sent_at", ""), reverse=True)
        return {"success": True, "total_errors": len(error_logs[:50]), "errors": error_logs[:50]}
    except Exception as e:
        logger.error(f"[CAMPAIGNS-LOGS] Erreur: {e}")
        return {"success": False, "total_errors": 0, "errors": [], "error": str(e)}

@campaign_router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str, request: Request):
    """Récupère une campagne par ID.

    MT-1 : route SANS authentification jusqu'ici (campagne complète, résultats
    nominatifs compris, à n'importe qui). JWT signé + propriétaire ; la campagne
    d'un autre coach répond 404, comme une campagne inexistante.
    """
    appelant = await mt1_appelant_signe(request, "lecture d'une campagne")
    return await mt1_campagne_visible(campaign_id, appelant)

# RÉACTIVATION 3B — LES MUTATIONS DE CAMPAGNE SONT AUTHENTIFIÉES.
# Constaté : PUT / DELETE / purge n'exigeaient RIEN (un anonyme pouvait réécrire
# les destinataires d'une campagne ou l'effacer). Même politique que le
# lancement (V451) : JWT coach/admin signé, puis PROPRIÉTÉ lue sur le document
# (`coach_id`) — le super-admin passe partout, un coach ne touche qu'aux siennes.
async def _r3_campagne_du_proprietaire(campaign_id: str, request: Request):
    from api.routes.shared import is_super_admin as _is_super_admin
    # MT-1 : même authentification (JWT signé, rôle relu en base) mais par la garde
    # des campagnes, qui connaît les DEUX super-admins (`_autorise` des segments
    # n'en reconnaissait qu'un en dur).
    appelant = await mt1_appelant_signe(request, "modification d'une campagne")
    campagne = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0, "coach_id": 1, "name": 1})
    if not campagne:
        raise HTTPException(status_code=404, detail="Campaign not found")
    proprietaire = (campagne.get("coach_id") or "").lower().strip()
    if not _is_super_admin(appelant) and proprietaire != appelant:
        logger.warning("[R3] REFUS mutation de « %s » — %s n'en est pas le propriétaire", campagne.get("name"), appelant)
        raise HTTPException(status_code=403, detail="Cette campagne ne vous appartient pas.")
    return appelant


@campaign_router.put("/campaigns/{campaign_id}")
async def update_campaign(campaign_id: str, request: Request):
    """Met à jour une campagne (JWT coach/admin + propriété)."""
    await _r3_campagne_du_proprietaire(campaign_id, request)
    data = await request.json()
    # Le propriétaire et l'identifiant ne se réécrivent pas par le corps.
    for cle in ("coach_id", "id", "_id"):
        data.pop(cle, None)
    data["updatedAt"] = datetime.now(timezone.utc).isoformat()
    await db.campaigns.update_one({"id": campaign_id}, {"$set": data})
    return await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})

@campaign_router.delete("/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: str, request: Request):
    """Supprime une campagne (JWT coach/admin + propriété)."""
    await _r3_campagne_du_proprietaire(campaign_id, request)
    result = await db.campaigns.delete_one({"id": campaign_id})
    logger.info(f"[HARD DELETE] Campagne {campaign_id} supprimée")
    return {"success": True, "hardDelete": True, "deleted": {"campaign": result.deleted_count}}

@campaign_router.delete("/campaigns/purge/all")
async def purge_all_campaigns(request: Request):
    """Purge les campagnes terminées DU COACH authentifié (le super-admin : toutes)."""
    from api.routes.shared import is_super_admin as _is_super_admin
    appelant = await mt1_appelant_signe(request, "purge des campagnes")  # MT-1 : les deux super-admins
    filtre = {"status": {"$in": ["completed", "failed", "draft"]}}
    if not _is_super_admin(appelant):
        filtre["coach_id"] = appelant
    result = await db.campaigns.delete_many(filtre)
    logger.info(f"[PURGE] {result.deleted_count} campagnes supprimées")
    return {"success": True, "purgedCount": result.deleted_count}

@campaign_router.post("/campaigns/{campaign_id}/mark-sent")
async def mark_campaign_sent(campaign_id: str, request: Request):
    """Marque un résultat comme envoyé.

    ⚠️ Copie MASQUÉE : `api_router` (server.py) est inclus avant ce routeur, c'est
    SA route homonyme qui répond. MT-1 : les deux portent la même garde (JWT +
    propriétaire) et la même règle « jamais `completed` sans résultat ».
    """
    await _r3_campagne_du_proprietaire(campaign_id, request)
    data = await request.json()
    contact_id = data.get("contactId")
    channel = data.get("channel")
    # MT-1 : valeurs du corps dans un filtre Mongo -> chaînes uniquement (pas d'opérateur).
    if not isinstance(contact_id, str) or not isinstance(channel, str):
        raise HTTPException(status_code=400, detail="contactId et channel requis")
    await db.campaigns.update_one(
        {"id": campaign_id, "results.contactId": contact_id, "results.channel": channel},
        {"$set": {"results.$.status": "sent", "results.$.sentAt": datetime.now(timezone.utc).isoformat()}}
    )
    campaign = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if campaign:
        # MT-1 : `all([])` est VRAI — une campagne sans résultat (programmée,
        # brouillon) passait en `completed`, ce qui annulait son envoi programmé.
        _resultats = campaign.get("results") or []
        all_sent = bool(_resultats) and all(r.get("status") == "sent" for r in _resultats)
        if all_sent:
            await db.campaigns.update_one({"id": campaign_id}, {"$set": {"status": "completed"}})
    return await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
