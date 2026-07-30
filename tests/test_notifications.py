"""Tests for Slack notifications (notifications.py)."""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from notifications import notify_slack


# ---------------------------------------------------------------------------
# notify_slack
# ---------------------------------------------------------------------------

class TestNotifySlack:
    def test_noop_when_webhook_not_set(self):
        """When SLACK_WEBHOOK_URL is not configured, notify_slack is a no-op."""
        # Ensure the setting returns None
        with patch("notifications.settings") as mock_settings:
            mock_settings.slack_webhook_url = None
            # Should not raise
            notify_slack("call_123", {"caller_number": "+923001234567"})

    def test_noop_when_webhook_empty(self):
        """When SLACK_WEBHOOK_URL is empty string, it's a no-op."""
        with patch("notifications.settings") as mock_settings:
            mock_settings.slack_webhook_url = ""
            notify_slack("call_123", {"caller_number": "+923001234567"})

    @patch("urllib.request.urlopen")
    @patch("notifications.settings")
    def test_sends_payload(self, mock_settings, mock_urlopen):
        """When configured, notify_slack sends a POST with the right payload."""
        mock_settings.slack_webhook_url = "https://hooks.slack.com/services/xxx"
        mock_settings.public_base_url = "http://localhost:8000"
        mock_response = MagicMock()
        mock_urlopen.__enter__.return_value = mock_response

        doc = {
            "caller_number": "+923001234567",
            "business_name": "Test Corp",
            "call_direction": "inbound",
        }
        notify_slack("call_123", doc)

        # Should have called urlopen once
        assert mock_urlopen.call_count >= 1
        # Verify the payload contains expected text
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        body = json.loads(request.data.decode("utf-8"))
        assert "New Inbound call" in body["text"]
        assert "+923001234567" in body["text"]
        assert "Test Corp" in body["text"]

    @patch("urllib.request.urlopen")
    @patch("notifications.settings")
    def test_outbound_call_notification(self, mock_settings, mock_urlopen):
        """Outbound call direction is reflected in the Slack message."""
        mock_settings.slack_webhook_url = "https://hooks.slack.com/services/xxx"
        mock_settings.public_base_url = "http://localhost:8000"
        mock_response = MagicMock()
        mock_urlopen.__enter__.return_value = mock_response

        doc = {
            "caller_number": "+923001234567",
            "business_name": "",
            "call_direction": "outbound",
        }
        notify_slack("call_456", doc)

        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        body = json.loads(request.data.decode("utf-8"))
        assert "New Outbound call" in body["text"]

    @patch("urllib.request.urlopen")
    @patch("notifications.settings")
    def test_swallows_exception(self, mock_settings, mock_urlopen):
        """Exception during HTTP call is swallowed (no crash)."""
        mock_settings.slack_webhook_url = "https://hooks.slack.com/services/xxx"
        mock_urlopen.side_effect = Exception("Network error")
        # Should not raise
        notify_slack("call_123", {"caller_number": "+923001234567"})
