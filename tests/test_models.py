"""Tests for Pydantic models (models.py)."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from pydantic import ValidationError

from models import CallSummary, OutboundCallRequest, BulkOutboundCallRequest, StatusUpdate


# ---------------------------------------------------------------------------
# CallSummary
# ---------------------------------------------------------------------------

class TestCallSummary:
    def test_minimal_valid(self):
        """Only required field (caller_number) works with defaults."""
        model = CallSummary(caller_number="+923001234567")
        assert model.caller_number == "+923001234567"
        assert model.call_direction == "inbound"
        assert model.room_name is None
        assert model.business_name is None
        assert model.notes is None
        assert model.transcript_summary is None
        assert model.recording_url is None
        assert model.call_duration is None

    def test_full_payload(self):
        """All fields populated."""
        model = CallSummary(
            caller_number="+923001234567",
            call_direction="outbound",
            room_name="room-xyz",
            business_name="Test Corp",
            notes="Interested in services",
            transcript_summary="یہ ایک ٹیسٹ ہے۔",
            recording_url="https://example.com/rec.wav",
            call_duration=95.3,
        )
        assert model.caller_number == "+923001234567"
        assert model.call_direction == "outbound"
        assert model.business_name == "Test Corp"
        assert model.call_duration == 95.3

    def test_invalid_direction_fails(self):
        """call_direction should accept any string (no enum validation),
        but we test it accepts what we use."""
        model = CallSummary(caller_number="+92", call_direction="inbound")
        assert model.call_direction == "inbound"
        model2 = CallSummary(caller_number="+92", call_direction="outbound")
        assert model2.call_direction == "outbound"

    def test_empty_caller_number(self):
        """Empty caller_number is allowed by schema (no min_length)."""
        model = CallSummary(caller_number="")
        assert model.caller_number == ""


# ---------------------------------------------------------------------------
# OutboundCallRequest
# ---------------------------------------------------------------------------

class TestOutboundCallRequest:
    def test_valid(self):
        """Minimal valid request."""
        model = OutboundCallRequest(phone_number="03001234567")
        assert model.phone_number == "03001234567"

    def test_missing_phone_number_fails(self):
        """Missing phone_number raises ValidationError."""
        with pytest.raises(ValidationError):
            OutboundCallRequest()


# ---------------------------------------------------------------------------
# BulkOutboundCallRequest
# ---------------------------------------------------------------------------

class TestBulkOutboundCallRequest:
    def test_valid_numbers(self):
        """A list of phone numbers."""
        model = BulkOutboundCallRequest(
            phone_numbers=["03001234567", "+923001234568"]
        )
        assert len(model.phone_numbers) == 2

    def test_empty_list_fails(self):
        """Empty list should fail min_length validation."""
        with pytest.raises(ValidationError):
            BulkOutboundCallRequest(phone_numbers=[])

    def test_single_number(self):
        """A single number in the list should work."""
        model = BulkOutboundCallRequest(phone_numbers=["03001234567"])
        assert len(model.phone_numbers) == 1


# ---------------------------------------------------------------------------
# StatusUpdate
# ---------------------------------------------------------------------------

class TestStatusUpdate:
    def test_valid_status(self):
        """The status field accepts any string."""
        model = StatusUpdate(status="new")
        assert model.status == "new"
        model2 = StatusUpdate(status="reviewed")
        assert model2.status == "reviewed"

    def test_arbitrary_status_string(self):
        """Schema only requires a string — no enum validation (enforced in router)."""
        model = StatusUpdate(status="anything-else")
        assert model.status == "anything-else"
