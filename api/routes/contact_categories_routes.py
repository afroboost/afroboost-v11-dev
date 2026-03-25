# contact_categories_routes.py - Routes catégories de contacts V154
# Gestion des catégories pour organiser les contacts (Étudiants, Associations, Entreprises, etc.)
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
import uuid
import logging

logger = logging.getLogger(__name__)

SUPER_ADMIN_EMAIL = "contact.artboost@gmail.com"

def is_super_admin(email: str) -> bool:
    return email and email.lower().strip() == SUPER_ADMIN_EMAIL.lower()

# Router
category_router = APIRouter(tags=["contact-categories"])

db = None

def init_category_db(database):
    global db
    db = database

# Catégories par défaut (insérées automatiquement si absentes)
DEFAULT_CATEGORIES = [
    {"name": "Étudiants", "color": "#3B82F6", "icon": "🎓", "order": 1},
    {"name": "Associations", "color": "#8B5CF6", "icon": "🤝", "order": 2},
    {"name": "Entreprises", "color": "#10B981", "icon": "🏢", "order": 3},
    {"name": "Autres", "color": "#6B7280", "icon": "📋", "order": 4},
]


@category_router.get("/contact-categories")
async def get_contact_categories(request: Request):
    """Liste toutes les catégories de contacts pour ce coach"""
    caller_email = request.headers.get("X-User-Email", "").lower().strip()
    if not caller_email:
        raise HTTPException(status_code=401, detail="Non authentifié")

    try:
        coach_id = caller_email if not is_super_admin(caller_email) else SUPER_ADMIN_EMAIL

        # Vérifier si le coach a déjà des catégories, sinon créer les défauts
        existing = await db.contact_categories.find(
            {"coach_id": coach_id}, {"_id": 0}
        ).to_list(100)

        if not existing:
            # Première visite : créer les catégories par défaut
            for cat in DEFAULT_CATEGORIES:
                new_cat = {
                    "id": str(uuid.uuid4()),
                    "coach_id": coach_id,
                    "name": cat["name"],
                    "color": cat["color"],
                    "icon": cat["icon"],
                    "is_default": True,
                    "order": cat["order"],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                await db.contact_categories.insert_one(new_cat)
            existing = await db.contact_categories.find(
                {"coach_id": coach_id}, {"_id": 0}
            ).to_list(100)

        # Trier par order
        existing.sort(key=lambda x: x.get("order", 99))
        return {"success": True, "categories": existing}

    except Exception as e:
        logger.error(f"[CATEGORIES] Erreur get: {e}")
        return {"success": False, "categories": [], "error": str(e)}


@category_router.post("/contact-categories")
async def create_contact_category(request: Request):
    """Créer une nouvelle catégorie personnalisée"""
    caller_email = request.headers.get("X-User-Email", "").lower().strip()
    if not caller_email:
        raise HTTPException(status_code=401, detail="Non authentifié")

    body = await request.json()
    name = (body.get("name") or "").strip()
    color = body.get("color", "#6B7280")
    icon = body.get("icon", "📋")

    if not name:
        raise HTTPException(status_code=400, detail="Nom requis")

    coach_id = caller_email if not is_super_admin(caller_email) else SUPER_ADMIN_EMAIL

    # Vérifier doublon
    existing = await db.contact_categories.find_one(
        {"coach_id": coach_id, "name": {"$regex": f"^{name}$", "$options": "i"}},
        {"_id": 0}
    )
    if existing:
        raise HTTPException(status_code=409, detail="Catégorie existe déjà")

    # Trouver le prochain order
    max_order = await db.contact_categories.find(
        {"coach_id": coach_id}, {"order": 1, "_id": 0}
    ).sort("order", -1).to_list(1)
    next_order = (max_order[0]["order"] + 1) if max_order else 1

    new_cat = {
        "id": str(uuid.uuid4()),
        "coach_id": coach_id,
        "name": name,
        "color": color,
        "icon": icon,
        "is_default": False,
        "order": next_order,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.contact_categories.insert_one(new_cat)
    del new_cat["_id"]

    logger.info(f"[CATEGORIES] Nouvelle catégorie créée: {name} pour {coach_id}")
    return {"success": True, "category": new_cat}


@category_router.put("/contact-categories/{category_id}")
async def update_contact_category(category_id: str, request: Request):
    """Modifier une catégorie"""
    caller_email = request.headers.get("X-User-Email", "").lower().strip()
    if not caller_email:
        raise HTTPException(status_code=401, detail="Non authentifié")

    body = await request.json()
    update_fields = {}
    if "name" in body and body["name"]:
        update_fields["name"] = body["name"].strip()
    if "color" in body:
        update_fields["color"] = body["color"]
    if "icon" in body:
        update_fields["icon"] = body["icon"]
    if "order" in body:
        update_fields["order"] = body["order"]

    if not update_fields:
        return {"success": True, "message": "Rien à modifier"}

    result = await db.contact_categories.update_one(
        {"id": category_id},
        {"$set": update_fields}
    )
    updated = await db.contact_categories.find_one({"id": category_id}, {"_id": 0})
    return {"success": True, "category": updated}


@category_router.delete("/contact-categories/{category_id}")
async def delete_contact_category(category_id: str, request: Request):
    """Supprimer une catégorie (retire aussi la catégorie des contacts)"""
    caller_email = request.headers.get("X-User-Email", "").lower().strip()
    if not caller_email:
        raise HTTPException(status_code=401, detail="Non authentifié")

    cat = await db.contact_categories.find_one({"id": category_id}, {"_id": 0})
    if not cat:
        raise HTTPException(status_code=404, detail="Catégorie non trouvée")

    # Retirer cette catégorie de tous les contacts qui l'ont
    await db.chat_participants.update_many(
        {"categories": category_id},
        {"$pull": {"categories": category_id}}
    )

    await db.contact_categories.delete_one({"id": category_id})
    logger.info(f"[CATEGORIES] Catégorie supprimée: {cat.get('name')} ({category_id})")
    return {"success": True, "deleted": True}


@category_router.post("/contacts/set-categories")
async def set_contact_categories(request: Request):
    """Attribuer des catégories à une liste de contacts"""
    caller_email = request.headers.get("X-User-Email", "").lower().strip()
    if not caller_email:
        raise HTTPException(status_code=401, detail="Non authentifié")

    body = await request.json()
    contact_ids = body.get("contact_ids", [])
    category_ids = body.get("category_ids", [])
    mode = body.get("mode", "add")  # "add" = ajouter, "set" = remplacer, "remove" = retirer

    if not contact_ids:
        return {"updated": 0}

    updated = 0
    for cid in contact_ids:
        # V154b: Vérifier si le contact existe dans chat_participants
        existing = await db.chat_participants.find_one({"id": cid}, {"_id": 0, "id": 1})
        if not existing:
            # Contact vient peut-être de la collection users — le copier dans chat_participants
            user = await db.users.find_one({"id": cid}, {"_id": 0})
            if user:
                from datetime import datetime, timezone
                new_participant = {
                    "id": cid,
                    "name": user.get("name") or user.get("email", ""),
                    "email": (user.get("email") or "").lower().strip(),
                    "whatsapp": None,
                    "phone": None,
                    "source": "app",
                    "coach_id": caller_email,
                    "tags": [],
                    "categories": [],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "last_seen_at": datetime.now(timezone.utc).isoformat()
                }
                await db.chat_participants.insert_one(new_participant)
                logger.info(f"[CATEGORIES] Contact app_user copié dans chat_participants: {cid}")
            else:
                continue  # Contact introuvable, skip

        if mode == "set":
            result = await db.chat_participants.update_one(
                {"id": cid},
                {"$set": {"categories": category_ids}}
            )
        elif mode == "remove":
            result = await db.chat_participants.update_one(
                {"id": cid},
                {"$pullAll": {"categories": category_ids}}
            )
        else:  # add
            result = await db.chat_participants.update_one(
                {"id": cid},
                {"$addToSet": {"categories": {"$each": category_ids}}}
            )
        if result.modified_count:
            updated += 1

    logger.info(f"[CATEGORIES] {updated} contacts mis à jour (mode={mode})")
    return {"success": True, "updated": updated, "mode": mode}


@category_router.post("/contacts/filter-by-categories")
async def filter_contacts_by_categories(request: Request):
    """Filtrer les contacts par catégories (pour campagnes et codes promo)"""
    caller_email = request.headers.get("X-User-Email", "").lower().strip()
    if not caller_email:
        raise HTTPException(status_code=401, detail="Non authentifié")

    body = await request.json()
    category_ids = body.get("category_ids", [])
    filter_mode = body.get("filter_mode", "any")  # "any" = OR, "all" = AND

    if not category_ids:
        return {"success": True, "contacts": [], "total": 0}

    coach_id = caller_email if not is_super_admin(caller_email) else SUPER_ADMIN_EMAIL

    if filter_mode == "all":
        # Contacts qui ont TOUTES les catégories sélectionnées
        query = {"coach_id": coach_id, "categories": {"$all": category_ids}}
    else:
        # Contacts qui ont AU MOINS UNE des catégories
        query = {"coach_id": coach_id, "categories": {"$in": category_ids}}

    contacts = await db.chat_participants.find(query, {"_id": 0}).to_list(5000)
    return {"success": True, "contacts": contacts, "total": len(contacts)}


@category_router.get("/contact-categories/stats")
async def get_category_stats(request: Request):
    """Obtenir le nombre de contacts par catégorie"""
    caller_email = request.headers.get("X-User-Email", "").lower().strip()
    if not caller_email:
        raise HTTPException(status_code=401, detail="Non authentifié")

    coach_id = caller_email if not is_super_admin(caller_email) else SUPER_ADMIN_EMAIL

    categories = await db.contact_categories.find(
        {"coach_id": coach_id}, {"_id": 0}
    ).to_list(100)

    stats = []
    for cat in categories:
        count = await db.chat_participants.count_documents(
            {"coach_id": coach_id, "categories": cat["id"]}
        )
        stats.append({
            "id": cat["id"],
            "name": cat["name"],
            "color": cat["color"],
            "icon": cat["icon"],
            "count": count
        })

    # Contacts sans catégorie
    uncategorized = await db.chat_participants.count_documents(
        {"coach_id": coach_id, "$or": [{"categories": {"$exists": False}}, {"categories": {"$size": 0}}, {"categories": None}]}
    )
    stats.append({
        "id": "__uncategorized__",
        "name": "Sans catégorie",
        "color": "#9CA3AF",
        "icon": "❓",
        "count": uncategorized
    })

    return {"success": True, "stats": stats}
