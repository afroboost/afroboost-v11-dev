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

RUN rm -rf node_modules/.cache && NODE_OPTIONS="--max-old-space-size=512 --max-semi-space-size=64" GENERATE_SOURCEMAP=false CI=false npx craco build

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
CMD ["uvicorn", "api.server:fastapi_app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--timeout-keep-alive", "65"]
