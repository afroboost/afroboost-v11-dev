FROM node:18-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
COPY frontend/craco.config.js ./
RUN npm install --legacy-peer-deps
COPY frontend/ ./

# V229 — Configuration Cloudinary (upload direct depuis le navigateur).
# Create React App inline les `process.env.REACT_APP_*` AU MOMENT DU BUILD : une
# variable posee uniquement comme variable d'execution Coolify n'atteindrait
# jamais le bundle, et le bouton d'upload disparaitrait silencieusement en
# production. Elles doivent donc etre presentes ici, pendant `craco build`.
#
# `frontend/.env` ne peut PAS servir de repli : il est exclu deux fois, par
# .gitignore (motif `*.env`) et par .dockerignore.
#
# Ces deux valeurs ne sont pas des secrets : un `upload preset` unsigned existe
# precisement pour etre expose au navigateur, et le `cloud name` est visible
# dans chaque URL d'image livree. Les inscrire en defaut rend le build
# deterministe ; une Build Variable Coolify du meme nom les remplace.
ARG REACT_APP_CLOUDINARY_CLOUD_NAME=dtm0r7hwq
ARG REACT_APP_CLOUDINARY_UPLOAD_PRESET=afroboost
ENV REACT_APP_CLOUDINARY_CLOUD_NAME=$REACT_APP_CLOUDINARY_CLOUD_NAME
ENV REACT_APP_CLOUDINARY_UPLOAD_PRESET=$REACT_APP_CLOUDINARY_UPLOAD_PRESET

# V283 — CACHE-BUST du build frontend. Symptome observe : la production servait
# un frontend PERIME (Service Worker afroboost-v277) alors que le backend, lui,
# etait a jour — les deux sont pourtant dans la MEME image. Cause : Coolify
# reutilisait l'etape `frontend-build` en cache et ne relancait pas `craco build`.
# Changer la valeur de cet ARG modifie l'instruction Docker qui suit : le cache
# de `craco build` est invalide et le frontend est TOUJOURS reconstruit a neuf.
# -> BUMPER cette valeur a chaque fois qu'un changement frontend doit partir.
ARG FRONTEND_CACHEBUST=v318-20260728

# V308b : la limite mémoire Node de 512 Mo était trop juste pour des fichiers de
# 10 000+ lignes (ChatWidget.js, App.js, CoachDashboard.js) -> build tué par OOM
# (exit 255, ~10 s après « Creating an optimized production build… »). Portée à
# 2048 Mo (VPS Hetzner).
#
# V424 — NE PAS MONTER CETTE VALEUR. L'ancien conseil (« monter à 3072 ») est
# FAUX pour la panne réellement observée. Trace du build tué le 10 août 2026 :
#     [frontend-build 7/7] RUN … npx craco build
#     failed to read oom_kill event … memory.events: no such file or directory
# Le cgroup avait déjà disparu : c'est le NOYAU qui a tué le processus sur sa
# mémoire RÉSIDENTE. Node, lui, aurait dit « JavaScript heap out of memory ».
# Un tas plus grand laisse Node repousser ses ramasse-miettes, donc AUGMENTE la
# mémoire résidente — on aggraverait la panne en croyant la corriger.
# Les deux leviers qui marchent RÉDUISENT le pic — mesurés sur un build complet :
#   parallel=1,     heap 2048  ->  1476 Mo   (configuration d'origine)
#   parallel=false, heap 2048  ->  1367 Mo
#   parallel=false, heap 1536  ->  1019 Mo   <- RETENU (-31 %)
#   parallel=false, heap 1024  ->   955 Mo   (marge trop juste si le code grossit)
# Un tas PLUS PETIT force Node à ramasser plus tôt : la mémoire résidente baisse,
# alors même que le plafond du tas descend. C'est l'inverse de l'intuition, et
# c'est ce que la mesure montre. Voir aussi `parallel = false` (craco.config.js).
RUN rm -rf node_modules/.cache && NODE_OPTIONS="--max-old-space-size=1536" GENERATE_SOURCEMAP=false CI=false npx craco build

FROM python:3.11-slim AS production
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc libffi-dev libjpeg-dev zlib1g-dev && rm -rf /var/lib/apt/lists/*
COPY api/requirements.txt /app/api/requirements.txt
RUN pip install --no-cache-dir -r /app/api/requirements.txt
COPY api/ /app/api/
COPY --from=frontend-build /app/frontend/build /app/static
EXPOSE 8080
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# V320 — meme sonde que docker-compose.yml, portee par l'IMAGE : ainsi le conteneur
# est « healthy/unhealthy » quel que soit le mode de lancement choisi par Coolify
# (Dockerfile seul OU docker-compose). C'est cette sonde qui permet la bascule sans
# coupure : le nouveau conteneur doit repondre AVANT que l'ancien soit retire.
# Cible /healthz : sonde PURE, sans acces MongoDB (voir api/server.py) — sinon un
# ralentissement d'Atlas ferait redemarrer en boucle une application qui marche.
HEALTHCHECK --interval=10s --timeout=4s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=3).status==200 else 1)"
CMD ["uvicorn", "api.server:fastapi_app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--timeout-keep-alive", "65"]
