# Consolidated Dockerfile — Dashboard + Voice Agent (Combined Service)
# Single container running both FastAPI dashboard and LiveKit voice agent via supervisor
FROM python:3.12-slim

# Use plain mirrors to avoid network issues
RUN sed -i 's/deb.debian.org/mirrors.internode.on.net/g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's/security.debian.org/mirrors.internode.on.net/g' /etc/apt/sources.list.d/debian.sources

WORKDIR /tmp

# Set home to tmp to avoid any home directory issues
ENV HOME=/tmp \
    DEBIAN_FRONTEND=noninteractive \
    TERM=xterm

# Update system packages carefully with explicit error handling
RUN apt-get update && \
    apt-get install -y --no-install-recommends -qq \
    curl \
    ffmpeg \
    libsndfile1 \
    supervisor \
    ca-certificates \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/cache/apt/archives/* /var/log/apt/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip==25.0 && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py config.py db.py models.py notifications.py phone.py rendering.py piper_tts.py rag_utils.py agent.py latency_metrics.py ./
COPY routers/ ./routers/
COPY templates/ ./templates/
COPY static/ ./static/
COPY datax_technologies_approved_rag.jsonl ./datax_technologies_approved_rag.jsonl
COPY supervisors/ provisions/ 2>/dev/null || true

# Create voices directory and ensure it exists
RUN mkdir -p /app/voices && \
    if [ -d "/tmp/voices" ]; then \
        cp -r /tmp/voices/* /app/voices/; \
    fi && \
    touch /app/voices/.gitkeep && \
    chmod 644 /app/voices/.gitkeep

# Supervisor configuration - runs both dashboard and voice agent
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 8000

# Health check - tests the dashboard endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD timeout 5 curl -f http://localhost:${PORT:-8000}/health || exit 1

# Supervisor starts both processes (dashboard on port 8000, voice agent inside)
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]