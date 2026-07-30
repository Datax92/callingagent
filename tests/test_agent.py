"""Tests for agent.py core logic.

Most of agent.py is LiveKit-integrated voice runtime (entrypoint, callbacks,
session management) which requires actual LiveKit infrastructure to run.

This file tests the **pure-logic units** that can be exercised in isolation:
  - CallState initialisation
  - extract_caller_number
  - _extract_call_data_via_llm (mocked)
  - _push_lead_to_dashboard (mocked)
  - Greeting text
"""
import json
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

pytestmark = pytest.mark.asyncio

from agent import (
    CallState,
    extract_caller_number,
    GREETING_LINE,
    FAILED_LEADS_FALLBACK_PATH,
    _push_lead_to_dashboard,
    _extract_call_data_via_llm,
)


# ---------------------------------------------------------------------------
# CallState
# ---------------------------------------------------------------------------

class TestCallState:
    def test_default_values(self):
        """CallState initialises with sensible defaults."""
        state = CallState()
        assert state.caller_number == "unknown"
        assert state.call_direction == "inbound"
        assert state.room_name == ""
        assert state.business_name is None
        assert state.business_details is None
        assert state.notes == ""
        assert state.last_rag_message_id is None
        assert state.transcript_lines == []
        assert state.lead_pushed is False
        assert state.call_start_time > 0
        assert state.call_end_time is None
        assert state.recording_url is None
        assert state.call_duration is None

    def test_tracks_start_time(self):
        """call_start_time is set at construction."""
        before = time.time()
        state = CallState()
        after = time.time()
        assert before <= state.call_start_time <= after

    def test_transcript_lines_appended(self):
        """Transcript lines list grows."""
        state = CallState()
        state.transcript_lines.append("caller: Hello")
        state.transcript_lines.append("agent: Hi")
        assert len(state.transcript_lines) == 2

    def test_lead_pushed_flag(self):
        """lead_pushed prevents duplicate webhook pushes."""
        state = CallState()
        assert state.lead_pushed is False
        state.lead_pushed = True
        assert state.lead_pushed is True


# ---------------------------------------------------------------------------
# extract_caller_number
# ---------------------------------------------------------------------------

class TestExtractCallerNumber:
    def test_none_participant(self):
        """None participant → 'Unknown Participant'."""
        assert extract_caller_number(None) == "Unknown Participant"

    def test_sip_participant_with_phone(self):
        """SIP participant with phone attribute returns the phone."""
        participant = MagicMock()
        participant.kind = MagicMock()
        participant.kind.__int__ = lambda self: 2  # PARTICIPANT_KIND_SIP = 2 (livekit rtc)
        # We need to mock the enum properly
        from livekit import rtc
        participant.kind = rtc.ParticipantKind.PARTICIPANT_KIND_SIP
        participant.attributes = {"sip.phoneNumber": "+923001234567"}
        participant.identity = "sip-+923001234567"
        assert extract_caller_number(participant) == "+923001234567"

    def test_sip_participant_empty_phone_falls_back_to_identity(self):
        """SIP without phone → falls back to identity."""
        from livekit import rtc
        participant = MagicMock()
        participant.kind = rtc.ParticipantKind.PARTICIPANT_KIND_SIP
        participant.attributes = {"sip.phoneNumber": ""}
        participant.identity = "+923001234567"
        assert extract_caller_number(participant) == "+923001234567"

    def test_sip_empty_phone_and_identity(self):
        """SIP with both empty → 'Unknown SIP'."""
        from livekit import rtc
        participant = MagicMock()
        participant.kind = rtc.ParticipantKind.PARTICIPANT_KIND_SIP
        participant.attributes = {"sip.phoneNumber": ""}
        participant.identity = ""
        assert extract_caller_number(participant) == "Unknown SIP"

    def test_web_participant(self):
        """Web/local participant returns identity."""
        from livekit import rtc
        participant = MagicMock()
        participant.kind = rtc.ParticipantKind.PARTICIPANT_KIND_AGENT  # not SIP
        participant.identity = "web-user-123"
        assert extract_caller_number(participant) == "web-user-123"

    def test_web_participant_empty_identity(self):
        """Web participant with empty identity → 'Web/Local Participant'."""
        from livekit import rtc
        participant = MagicMock()
        participant.kind = rtc.ParticipantKind.PARTICIPANT_KIND_AGENT
        participant.identity = ""
        assert extract_caller_number(participant) == "Web/Local Participant"


# ---------------------------------------------------------------------------
# GREETING_LINE
# ---------------------------------------------------------------------------

class TestGreetingLine:
    def test_greeting_is_urdu(self):
        """Greeting line is in Urdu script."""
        assert "السلام" in GREETING_LINE
        assert "علیکم" in GREETING_LINE

    def test_greeting_includes_company_name(self):
        """Greeting mentions DataX Technologies."""
        assert "ڈیٹا ایکس ٹیکنالوجیز" in GREETING_LINE


# ---------------------------------------------------------------------------
# _extract_call_data_via_llm (mocked)
# ---------------------------------------------------------------------------

class TestExtractCallDataViaLLM:
    @patch("agent.AsyncOpenAI")
    async def test_extracts_business_name_and_summary(self, mock_openai):
        """Happy path: returns parsed business_name and summary from LLM."""
        # Setup mock response
        mock_client = AsyncMock()
        mock_openai.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps({
                        "business_name": "Test Corp",
                        "summary": "یہ ایک ٹیسٹ خلاصہ ہے۔"
                    })
                )
            )
        ]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await _extract_call_data_via_llm(["caller: Hello", "agent: Hi"])
        assert result["business_name"] == "Test Corp"
        assert "ٹیسٹ خلاصہ" in result["summary"]

    @patch("agent.AsyncOpenAI")
    async def test_empty_transcript_returns_defaults(self, mock_openai):
        """Empty transcript returns defaults without calling LLM."""
        result = await _extract_call_data_via_llm([])
        assert result["business_name"] == ""
        assert "کوئی ترانسکرپٹ" in result["summary"]
        mock_openai.assert_not_called()

    @patch("agent.AsyncOpenAI")
    async def test_llm_exception_returns_fallback(self, mock_openai):
        """LLM failure falls back to last few transcript lines."""
        mock_client = AsyncMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))

        transcript = ["caller: Line 1", "caller: Line 2", "caller: Line 3", "caller: Line 4"]
        result = await _extract_call_data_via_llm(transcript)
        assert result["business_name"] == ""
        # Fallback summary should be last 4 lines
        assert "Line 4" in result["summary"]


# ---------------------------------------------------------------------------
# _push_lead_to_dashboard (mocked)
# ---------------------------------------------------------------------------

class TestPushLeadToDashboard:
    @patch("agent._post_json")
    async def test_skips_if_already_pushed(self, mock_post_json):
        """Already-pushed lead skips the HTTP call."""
        state = CallState()
        state.lead_pushed = True
        state.caller_number = "+923001234567"
        state.call_direction = "inbound"
        await _push_lead_to_dashboard(state)
        mock_post_json.assert_not_called()

    @patch("agent._post_json")
    async def test_skips_no_conversation_inbound(self, mock_post_json):
        """Inbound call with no transcript lines is skipped."""
        state = CallState()
        state.lead_pushed = False
        state.caller_number = "+923001234567"
        state.call_direction = "inbound"
        state.transcript_lines = []
        await _push_lead_to_dashboard(state)
        mock_post_json.assert_not_called()

    @patch("agent._post_json")
    async def test_pushes_for_outbound_even_no_conversation(self, mock_post_json):
        """Outbound call pushes even without conversation (for logging)."""
        state = CallState()
        state.lead_pushed = False
        state.caller_number = "+923001234567"
        state.call_direction = "outbound"
        state.transcript_lines = []
        state.room_name = "room-test"
        await _push_lead_to_dashboard(state)
        mock_post_json.assert_called_once()

    @patch("agent._post_json")
    @patch("agent._extract_call_data_via_llm")
    async def test_sends_ai_data_in_payload(self, mock_extract, mock_post_json):
        """Payload sent to dashboard includes AI-extracted data."""
        mock_extract.return_value = {
            "business_name": "AI Corp",
            "summary": "AI generated summary",
        }

        state = CallState()
        state.lead_pushed = False
        state.caller_number = "+923001234567"
        state.call_direction = "inbound"
        state.transcript_lines = ["caller: Hi", "agent: Hello"]
        state.room_name = "room-abc"
        state.recording_url = "https://example.com/rec.wav"

        await _push_lead_to_dashboard(state)

        # Verify the payload that was sent
        call_args = mock_post_json.call_args
        assert call_args is not None
        url, payload = call_args[0]
        assert "DASHBOARD_WEBHOOK_URL" in url or "webhook" in url or "localhost" in url
        assert payload["business_name"] == "AI Corp"
        assert payload["transcript_summary"] == "AI generated summary"
        assert payload["caller_number"] == "+923001234567"
        assert payload["recording_url"] == "https://example.com/rec.wav"

    @patch("agent._post_json")
    @patch("agent._extract_call_data_via_llm")
    async def test_uses_state_business_name_over_ai(self, mock_extract, mock_post_json):
        """If call_state already has a business_name, it takes precedence."""
        mock_extract.return_value = {
            "business_name": "AI-Generated Name",
            "summary": "Summary here",
        }

        state = CallState()
        state.lead_pushed = False
        state.caller_number = "+923001234567"
        state.call_direction = "inbound"
        state.transcript_lines = ["caller: Hi"]
        state.business_name = "Manual Name"
        state.room_name = "room-abc"

        await _push_lead_to_dashboard(state)

        call_args = mock_post_json.call_args
        payload = call_args[0][1]
        assert payload["business_name"] == "Manual Name"

    @patch("agent._post_json")
    @patch("agent._extract_call_data_via_llm")
    async def test_records_call_duration(self, mock_extract, mock_post_json):
        """Call duration is calculated from start/end times."""
        mock_extract.return_value = {"business_name": "", "summary": ""}

        state = CallState()
        state.lead_pushed = False
        state.caller_number = "+923001234567"
        state.call_direction = "inbound"
        state.transcript_lines = ["caller: Hi"]
        state.room_name = "room-abc"
        state.call_start_time = time.time() - 100  # 100 seconds ago

        await _push_lead_to_dashboard(state)

        call_args = mock_post_json.call_args
        payload = call_args[0][1]
        assert payload["call_duration"] >= 99.0  # Should be roughly 100s
