"""
Optional Slack ping when a new call lands. Safe no-op if not configured.
"""
import json

from config import settings


def notify_slack(call_id: str, doc: dict) -> None:
    webhook_url = settings.slack_webhook_url
    if not webhook_url:
        return
    try:
        import urllib.request

        direction = (doc.get("call_direction") or "inbound").capitalize()
        text = (
            f"New {direction} call logged (id: {call_id})\n"
            f"From: {doc.get('caller_number', 'unknown')}\n"
            f"Business: {doc.get('business_name') or '-'}\n"
            f"Review here: {settings.public_base_url}/"
        )
        data = json.dumps({"text": text}).encode("utf-8")
        req = urllib.request.Request(
            webhook_url, data=data, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass
