# Single-container image (UI + API) for Railway, Fly.io, a VPS, or any Docker host.
#   docker build -t ordertrack .
#   docker run -d -p 8000:8000 -v ordertrack-data:/data -e ADMIN_PASSWORD='change-me-now!' \
#              -e CORS_ORIGINS=http://localhost:8000 --name ordertrack ordertrack

# ---- build the user interface
FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ENV VITE_API_URL=""
RUN npm run build

# ---- runtime
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    ENV=production DATA_DIR=/data STATIC_DIR=/app/frontend/dist PORT=8000 MODELS_DIR=/app/backend/model_cache
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/ ./
RUN DATA_DIR=/tmp/build-data python -m app.intelligence.column_model   # bake the model into the image
COPY --from=ui /ui/dist /app/frontend/dist
# uid 1000 matches Hugging Face Spaces (and most hosts), which run containers as user 1000
RUN useradd --create-home --uid 1000 app && mkdir -p /data && chown -R app:app /data /app
USER app
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/api/health',timeout=4)"
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --timeout-keep-alive 75"]
