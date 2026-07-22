FROM node:18-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
COPY frontend/craco.config.js ./
RUN npm install --legacy-peer-deps
COPY frontend/ ./
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
