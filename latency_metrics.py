import logging

logger = logging.getLogger("voice-agent.latency")

def log_stage(stage_name: str, duration_ms: float, **kwargs):
    """Logs performance and latency metrics for voice agent stages."""
    extra_info = " ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.info(f"[LATENCY] {stage_name}: {duration_ms:.2f}ms {extra_info}".strip())