# admin_routes.py - Routes d'administration v9.1.0
# Ce fichier est préparé pour la future extraction des routes admin de server.py
# Pour l'instant, les routes restent dans server.py pour la stabilité

from fastapi import APIRouter, HTTPException, Request
from api.routes.shared import is_super_admin, SUPER_ADMIN_EMAIL

admin_router = APIRouter(prefix="/admin", tags=["admin"])

# TODO: Migrer progressivement les routes /admin/* depuis server.py
# Endpoints prévus:
# - GET /admin/coaches
# - POST /admin/coaches/{id}/toggle
# - DELETE /admin/coaches/{id}
# - GET /admin/coach-packs
# - POST /admin/coach-packs
# - PUT /admin/coach-packs/{id}
# - DELETE /admin/coach-packs/{id}
