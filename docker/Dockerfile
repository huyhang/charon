# Builds the web UI; only its static files reach the final image.
FROM node:24-slim AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY ui ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CHARON_PORT=8080 \
    CHARON_DB_PATH=/data/charon.db \
    CHARON_DOWNLOAD_DIR=/downloads \
    CHARON_UI_DIR=/app/ui

WORKDIR /app
COPY pyproject.toml ./
COPY charon ./charon
COPY --from=ui /ui/dist ./ui
RUN pip install --no-cache-dir . \
    && useradd --uid 1000 --no-create-home charon \
    && mkdir -p /data /downloads \
    && chown charon /data

# Override at runtime with `user: "PUID:PGID"` so files match your Synology user.
USER charon
EXPOSE 8080
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ['CHARON_PORT'] + '/api/v1/health', timeout=3)"]

CMD ["python", "-m", "charon.main"]
