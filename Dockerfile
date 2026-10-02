# Tahap 1: build frontend
FROM node:20-alpine AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ .
RUN npm run build

# Tahap 2: aplikasi Python
FROM python:3.12-slim
WORKDIR /app
# libgomp1 dibutuhkan XGBoost (OpenMP)
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=web /web/dist ./static
RUN useradd --create-home --uid 1000 appuser \
 && mkdir -p /data/uploads /data/models && chown -R appuser /data
USER appuser
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2 --proxy-headers --forwarded-allow-ips='*'"]
