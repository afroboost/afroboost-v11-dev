# campaign_routes.py - Routes campagnes v9.1.2
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
import uuid
import logging

logger = logging.getLogger(__name__)

# Constantes
SUPER_ADMIN_EMAIL = "contact.artboost@gmail.com"

def is_super_admin(email: str) -> bool:
    return email and email.lower().strip() == SUPER_ADMIN_EMAIL.lower()

# Router
campaign_router = APIRouter(tags=["campaigns"])

# Variable db sera injectée depuis server.py
db = None

def init_campaign_db(database):
    global db
    db = database

# === MODÈLES ===
class CampaignCreate(BaseModel):
    name: str
    message: str
    mediaUrl: Optional[str] = None
    mediaFormat: Optional[str] = None
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

# === ENDPOINTS CAMPAGNES ===
@campaign_router.get("/campaigns")
async def get_campaigns(request: Request):
    """Récupère les campagnes - Filtré par coach_id"""
    caller_email = request.headers.get("X-User-Email", "").lower().strip()
    if is_super_admin(caller_email):
        campaigns = await db.campaigns.find({}, {"_id": 0}).sort("createdAt", -1).to_list(100)
    else:
        campaigns = await db.campaigns.find({"coach_id": caller_email}, {"_id": 0}).sort("createdAt", -1).to_list(100) if caller_email else []
    return campaigns

@campaign_router.get("/campaigns/logs")
async def get_campaigns_error_logs():
    """Renvoie les 50 dernières erreurs d'envoi de campagnes."""
    try:
        error_logs = []
        campaigns_with_results = await db.campaigns.find({"results": {"$exists": True, "$ne": []}}, {"_id": 0, "id": 1, "name": 1, "results": 1, "updatedAt": 1}).sort("updatedAt", -1).to_list(100)
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
            twilio_errors = await db.campaign_errors.find({}, {"_id": 0}).sort("created_at", -1).to_list(50)
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
async def get_campaign(campaign_id: str):
    """Récupère une campagne par ID"""
    campaign = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign

@campaign_router.put("/campaigns/{campaign_id}")
async def update_campaign(campaign_id: str, request: Request):
    """Met à jour une campagne"""
    data = await request.json()
    data["updatedAt"] = datetime.now(timezone.utc).isoformat()
    await db.campaigns.update_one({"id": campaign_id}, {"$set": data})
    return await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})

@campaign_router.delete("/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: str):
    """Supprime une campagne"""
    result = await db.campaigns.delete_one({"id": campaign_id})
    logger.info(f"[HARD DELETE] Campagne {campaign_id} supprimée")
    return {"success": True, "hardDelete": True, "deleted": {"campaign": result.deleted_count}}

@campaign_router.delete("/campaigns/purge/all")
async def purge_all_campaigns():
    """Purge toutes les campagnes terminées"""
    result = await db.campaigns.delete_many({"status": {"$in": ["completed", "failed", "draft"]}})
    logger.info(f"[PURGE] {result.deleted_count} campagnes supprimées")
    return {"success": True, "purgedCount": result.deleted_count}

@campaign_router.post("/campaigns/{campaign_id}/mark-sent")
async def mark_campaign_sent(campaign_id: str, request: Request):
    """Marque un résultat comme envoyé"""
    data = await request.json()
    contact_id = data.get("contactId")
    channel = data.get("channel")
    await db.campaigns.update_one(
        {"id": campaign_id, "results.contactId": contact_id, "results.channel": channel},
        {"$set": {"results.$.status": "sent", "results.$.sentAt": datetime.now(timezone.utc).isoformat()}}
    )
    campaign = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if campaign:
        all_sent = all(r.get("status") == "sent" for r in campaign.get("results", []))
        if all_sent:
            await db.campaigns.update_one({"id": campaign_id}, {"$set": {"status": "completed"}})
    return await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
