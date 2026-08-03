# Consolidated Dockerfile — Dashboard + Voice Agent (Combined Service)
# Single container running both FastAPI dashboard and LiveKit voice agent via supervisor
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies with minimal configuration
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    ffmpeg \
    libsndfile1 \
    supervisor \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/cache/apt/archives/* /var/log/apt/*

# Upgrade pip in a separate layer for better caching
RUN pip install --no-cache-dir --upgrade pip==25.0

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py config.py db.py models.py notifications.py phone.py rendering.py piper_tts.py rag_utils.py agent.py latency_metrics.py ./
COPY routers/ ./routers/
COPY templates/ ./templates/
COPY static/ ./static/
COPY datax_technologies_approved_rag.jsonl ./datax_technologies_approved_rag.jsonl

# Supervisor configuration - runs both dashboard and voice agent
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Create voices directory
RUN mkdir -p /app/voices && \
    touch /app/voices/.gitkeep && \
    chmod 644 /app/voices/.gitkeep

# Set up log directories
RUN mkdir -p /var/log/supervisor && \
    touch /var/log/supervisor/supervisord.log && \
    touch /var/log/supervisor/dashboard.stdout.log && \
    touch /var/log/supervisor/dashboard.stderr.log && \
    touch /var/log/supervisor/voice-agent.stdout.log && \
    touch /var/log/supervisor/voice-agent.stderr.log && \
    chmod 644 /var/log/supervisor/*.log

EXPOSE 8000

# Health check - tests the dashboard endpoint with timeout
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD timeout 5 curl -f http://localhost:8000/health || exit 1

# Supervisor starts both processes (dashboard on port 8000, voice agent inside)
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]