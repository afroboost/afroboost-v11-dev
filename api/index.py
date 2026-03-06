# Point d'entrée Vercel Serverless Functions
# Toutes les requêtes /api/* sont routées ici via vercel.json
from api.server import fastapi_app

app = fastapi_app
