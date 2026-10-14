# ==========================================
# Stage 1: Build React Frontend
# ==========================================
FROM node:22-alpine AS frontend-builder
WORKDIR /web
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web/index.html apps/web/tsconfig.json apps/web/vite.config.ts ./
COPY apps/web/public ./public
COPY apps/web/src ./src
RUN npm run build

# ==========================================
# Stage 2: Python All-in-One Service (API + Web)
# ==========================================
FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    fonts-nanum \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/api/fixit_api ./fixit_api
COPY --from=frontend-builder /web/dist ./dist

EXPOSE 8310

CMD ["uvicorn", "fixit_api.main:app", "--host", "0.0.0.0", "--port", "8310"]
