# Dockerfile for the FastAPI Dashboard
# Architecture: single consolidated app server per Urdu_Voicebot_Architecture_Final.md
# See README.md for the module layout (config.py, db.py, routers/, etc.)
FROM python:3.12-slim

# curl is needed for this image's own HEALTHCHECK / docker-compose healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (dashboard-only, resolver-verified requirements file)
COPY requirements-dashboard.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements-dashboard.txt

# Application code — modular dashboard package
COPY app.py config.py db.py models.py notifications.py phone.py rendering.py ./
COPY routers/ ./routers/
COPY templates/ ./templates/
COPY static/ ./static/

EXPOSE 8000

# Runtime defaults (overridden by docker-compose / Railway environment variables)
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    MONGODB_URI="" \
    MONGODB_DATABASE=voice_agent_db \
    PUBLIC_BASE_URL=http://localhost:8000 \
    SLACK_WEBHOOK_URL="" \
    # Needed for the "Make Calls" screen to dispatch the voice agent
    LIVEKIT_URL="" \
    LIVEKIT_API_KEY="" \
    LIVEKIT_API_SECRET="" \
    SIP_OUTBOUND_TRUNK_ID="" \
    VOICE_AGENT_NAME=urdu-voicebot \
    MAX_BULK_CALL_NUMBERS=25 \
    # Cloudflare R2 (dashboard generates recording URLs on per-call click-through)
    CLOUDFLARE_R2_ACCOUNT_ID="" \
    CLOUDFLARE_R2_ACCESS_KEY_ID="" \
    CLOUDFLARE_R2_SECRET_ACCESS_KEY="" \
    CLOUDFLARE_R2_BUCKET_NAME="" \
    CLOUDFLARE_R2_PUBLIC_URL=""

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

CMD exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}
