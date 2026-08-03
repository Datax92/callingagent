# Consolidated Dockerfile — Dashboard + Voice Agent (Combined Service)
# Single container running both FastAPI dashboard and LiveKit voice agent via supervisor
FROM python:3.12-slim

# Update system dependencies (includes curl for health check, ffmpeg/supervisor for audio/agent)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    libsndfile1 \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install all Python dependencies (dashboard + voice agent)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py config.py db.py models.py notifications.py phone.py rendering.py piper_tts.py rag_utils.py agent.py latency_metrics.py ./
COPY routers/ ./routers/
COPY templates/ ./templates/
COPY static/ ./static/
COPY datax_technologies_approved_rag.jsonl ./datax_technologies_approved_rag.jsonl
COPY voices/ /app/voices/

# Supervisor configuration - runs both dashboard and voice agent
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 8000

# Health check - tests the dashboard endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Supervisor starts both processes (dashboard on port 8000, voice agent inside)
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]