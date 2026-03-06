# Routes modulaires pour Afroboost v13.4
# Structure préparée pour migration progressive depuis server.py

from api.routes.shared import (
    SUPER_ADMIN_EMAIL,
    DEFAULT_COACH_ID,
    ROLE_SUPER_ADMIN,
    ROLE_COACH,
    ROLE_USER,
    is_super_admin,
    get_coach_filter
)

# Routers
from api.routes.admin_routes import admin_router
from api.routes.coach_routes import coach_router
from api.routes.campaign_routes import campaign_router
from api.routes.stripe_routes import router as stripe_router, init_db as init_stripe_db

__all__ = [
    'SUPER_ADMIN_EMAIL', 'DEFAULT_COACH_ID', 
    'ROLE_SUPER_ADMIN', 'ROLE_COACH', 'ROLE_USER',
    'is_super_admin', 'get_coach_filter',
    'admin_router', 'coach_router', 'campaign_router', 'stripe_router', 'init_stripe_db'
]
