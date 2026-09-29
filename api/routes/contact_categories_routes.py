# contact_categories_routes.py - Routes catégories de contacts V154
# Gestion des catégories pour organiser les contacts (Étudiants, Associations, Entreprises, etc.)
import re  # V310 : disponible au niveau module pour re.escape (anti-injection regex)
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime, timezone
import uuid
import logging

logger = logging.getLogger(__name__)

SUPER_ADMIN_EMAIL = "contact.artboost@gmail.com"

# MT-2 : la version locale ne connaissait qu'UN super-admin — le second
# (afroboost.bassi@gmail.com) recevait un espace de catégories à lui, distinct
# de celui de la plateforme. Une seule définition dans tout le dépôt : celle de
# `shared.py` (les DEUX admins). `SUPER_ADMIN_EMAIL` reste l'ESPACE DE NOMS des
# catégories de la plateforme (valeur historique en base, inchangée).
from api.routes.shared import is_super_admin  # noqa: E402
from api.routes.shared import v20_exiger_coach_signe as _mt2_exiger  # noqa: E402


async def _mt2_appelant(request: Request, quoi: str) -> str:
    """MT-2 : identité coach/admin par JWT SIGNÉ uniquement (plus
    `X-User-Email`, falsifiable). 403 « reconnectez-vous » sinon."""
    return await _mt2_exiger(request, db, quoi)


def _mt2_espace(appelant: str) -> str:
    """Espace de noms des catégories : la plateforme pour un super-admin, le
    coach lui-même sinon (règle historique, désormais sur identité signée)."""
    return SUPER_ADMIN_EMAIL if is_super_admin(appelant) else appelant

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
    caller_email = await _mt2_appelant(request, "liste des catégories")  # MT-2

    try:
        coach_id = _mt2_espace(caller_email)

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
    caller_email = await _mt2_appelant(request, "création de catégorie")  # MT-2

    body = await request.json()
    name = (body.get("name") or "").strip()
    color = body.get("color", "#6B7280")
    icon = body.get("icon", "📋")

    if not name:
        raise HTTPException(status_code=400, detail="Nom requis")

    coach_id = _mt2_espace(caller_email)

    # Vérifier doublon
    existing = await db.contact_categories.find_one(
        {"coach_id": coach_id, "name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
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
    caller_email = await _mt2_appelant(request, "modification de catégorie")  # MT-2

    # MT-2 : aucune vérification de propriétaire — tout appelant renommait la
    # catégorie de n'importe quel coach. Filtre (id, espace) ; hors espace -> 404.
    _filtre = {"id": category_id, "coach_id": _mt2_espace(caller_email)}
    if not await db.contact_categories.find_one(_filtre, {"_id": 1}):
        raise HTTPException(status_code=404, detail="Catégorie non trouvée")
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    update_fields = {}
    if isinstance(body.get("name"), str) and body["name"].strip():
        update_fields["name"] = body["name"].strip()[:80]
    if isinstance(body.get("color"), str):
        update_fields["color"] = body["color"][:32]
    if isinstance(body.get("icon"), str):
        update_fields["icon"] = body["icon"][:16]
    if isinstance(body.get("order"), (int, float)) and not isinstance(body.get("order"), bool):
        update_fields["order"] = body["order"]

    if not update_fields:
        return {"success": True, "message": "Rien à modifier"}

    await db.contact_categories.update_one(_filtre, {"$set": update_fields})
    updated = await db.contact_categories.find_one(_filtre, {"_id": 0})
    return {"success": True, "category": updated}


@category_router.delete("/contact-categories/{category_id}")
async def delete_contact_category(category_id: str, request: Request):
    """Supprimer une catégorie (retire aussi la catégorie des contacts)"""
    caller_email = await _mt2_appelant(request, "suppression de catégorie")  # MT-2

    # MT-2 : suppression de la catégorie d'un autre coach possible -> 404.
    _filtre = {"id": category_id, "coach_id": _mt2_espace(caller_email)}
    cat = await db.contact_categories.find_one(_filtre, {"_id": 0})
    if not cat:
        raise HTTPException(status_code=404, detail="Catégorie non trouvée")

    # Retirer cette catégorie de tous les contacts qui l'ont (identifiant UUID
    # propre à cette catégorie : le retrait ne peut toucher qu'elle).
    await db.chat_participants.update_many(
        {"categories": category_id},
        {"$pull": {"categories": category_id}}
    )

    await db.contact_categories.delete_one(_filtre)
    logger.info(f"[CATEGORIES] Catégorie supprimée: {cat.get('name')} ({category_id})")
    return {"success": True, "deleted": True}


@category_router.post("/contacts/set-categories")
async def set_contact_categories(request: Request):
    """Attribuer des catégories à une liste de contacts"""
    caller_email = await _mt2_appelant(request, "attribution de catégories")  # MT-2

    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    contact_ids = body.get("contact_ids") or []
    category_ids = body.get("category_ids") or []
    mode = body.get("mode", "add")  # "add" = ajouter, "set" = remplacer, "remove" = retirer
    if not isinstance(contact_ids, list) or not isinstance(category_ids, list):
        raise HTTPException(status_code=400, detail="contact_ids et category_ids doivent être des listes")
    if mode not in ("add", "set", "remove"):
        mode = "add"

    if not contact_ids:
        return {"updated": 0}

    # MT-2 — QUATRE GARDES :
    #  1. seules les catégories de l'ESPACE de l'appelant s'appliquent (un coach
    #     ne pose pas l'identifiant de catégorie d'un autre) ;
    #  2. une fiche `chat_participants` n'est modifiée que dans le portefeuille
    #     de l'appelant (écriture filtrée par propriétaire) ;
    #  3. la copie `users` -> `chat_participants` (V154b) n'a lieu que si le
    #     `user` est VISIBLE par l'appelant (relation serveur prouvée,
    #     `tenant_contacts.contact_appartient`). Avant, n'importe quelle fiche
    #     de la plateforme était copiée dans le CRM de l'appelant ;
    #  4. si l'identifiant existe déjà chez un AUTRE coach, on ne crée pas de
    #     doublon d'`id` (qui rendrait ambiguës toutes les écritures par id) :
    #     le contact est ignoré.
    from api.routes.tenant_contacts import (
        contact_appartient as _mt2_app, filtre_proprietaire as _mt2_filtre,
        portee_ecriture as _mt2_portee,
    )
    _espace = _mt2_espace(caller_email)
    _cats_ok = {c.get("id") async for c in db.contact_categories.find(
        {"coach_id": _espace, "id": {"$in": [c for c in category_ids if isinstance(c, str)]}},
        {"_id": 0, "id": 1})}
    category_ids = [c for c in category_ids if c in _cats_ok]
    _proprio = _mt2_filtre(caller_email)
    _coach_id_copie, _ = _mt2_portee(caller_email)

    updated = 0
    for cid in contact_ids:
        if not isinstance(cid, str) or not cid or "$" in cid:
            continue
        existing = await db.chat_participants.find_one({"id": cid, **_proprio}, {"_id": 0, "id": 1})
        if not existing:
            if await db.chat_participants.find_one({"id": cid}, {"_id": 1}):
                continue  # garde 4 : fiche d'un autre coach
            if not await _mt2_app(db, caller_email, "users", cid):
                continue  # garde 3 : user hors portefeuille (ou inexistant)
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
                    "coach_id": _coach_id_copie,
                    "tags": [],
                    "categories": [],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "last_seen_at": datetime.now(timezone.utc).isoformat()
                }
                await db.chat_participants.insert_one(new_participant)
                logger.info(f"[CATEGORIES] Contact app_user copié dans chat_participants: {cid}")
            else:
                continue  # Contact introuvable, skip

        _cible = {"id": cid, **_proprio}
        if mode == "set":
            result = await db.chat_participants.update_one(
                _cible,
                {"$set": {"categories": category_ids}}
            )
        elif mode == "remove":
            result = await db.chat_participants.update_one(
                _cible,
                {"$pullAll": {"categories": category_ids}}
            )
        else:  # add
            result = await db.chat_participants.update_one(
                _cible,
                {"$addToSet": {"categories": {"$each": category_ids}}}
            )
        if result.modified_count:
            updated += 1

    logger.info(f"[CATEGORIES] {updated} contacts mis à jour (mode={mode})")
    return {"success": True, "updated": updated, "mode": mode}


@category_router.post("/contacts/filter-by-categories")
async def filter_contacts_by_categories(request: Request):
    """Filtrer les contacts par catégories (pour campagnes et codes promo)"""
    caller_email = await _mt2_appelant(request, "filtre par catégories")  # MT-2

    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    category_ids = [c for c in (body.get("category_ids") or []) if isinstance(c, str)] \
        if isinstance(body.get("category_ids"), list) else []
    filter_mode = body.get("filter_mode", "any")  # "any" = OR, "all" = AND

    if not category_ids:
        return {"success": True, "contacts": [], "total": 0}

    coach_id = _mt2_espace(caller_email)

    if filter_mode == "all":
        # Contacts qui ont TOUTES les catégories sélectionnées
        query = {"coach_id": coach_id, "categories": {"$all": category_ids}}
    else:
        # Contacts qui ont AU MOINS UNE des catégories
        query = {"coach_id": coach_id, "categories": {"$in": category_ids}}

    # MT-2 : liste de données personnelles -> paginée (50 max, `limit`/`skip`
    # dans le corps). Aucun appelant frontend (vérifié). `total` = compte réel.
    try:
        _l = max(1, min(int(body.get("limit") or 50), 50))
        _s = max(0, int(body.get("skip") or 0))
    except (TypeError, ValueError):
        _l, _s = 50, 0
    total = await db.chat_participants.count_documents(query)
    contacts = await db.chat_participants.find(query, {"_id": 0}).skip(_s).limit(_l).to_list(_l)
    return {"success": True, "contacts": contacts, "total": total, "limit": _l, "skip": _s}


@category_router.get("/contact-categories/stats")
async def get_category_stats(request: Request):
    """Obtenir le nombre de contacts par catégorie"""
    caller_email = await _mt2_appelant(request, "statistiques des catégories")  # MT-2

    coach_id = _mt2_espace(caller_email)

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
