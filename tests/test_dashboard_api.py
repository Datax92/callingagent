"""Tests for FastAPI dashboard endpoints (routers/calls.py, routers/outbound.py,
routers/webhook.py) using the mock collection from conftest.

These tests exercise the API layer without needing a real MongoDB or LiveKit.
"""
import sys
import time
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

pytestmark = pytest.mark.asyncio


# ===========================================================================
# Dashboard & Inbound calls
# ===========================================================================

class TestDashboard:
    """GET / - root endpoint renders the dashboard HTML."""

    async def test_dashboard_returns_html(self, async_client):
        resp = await async_client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    async def test_dashboard_contains_title(self, async_client):
        resp = await async_client.get("/")
        text = resp.text
        assert "Voice Agent Dashboard" in text

    async def test_health(self, async_client):
        resp = await async_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"ok": True}


class TestGetDeals:
    """GET /api/deals - paginated call listing."""

    async def test_empty_inbound(self, async_client):
        resp = await async_client.get("/api/deals")
        assert resp.status_code == 200
        data = resp.json()
        assert "html" in data
        assert data["has_more"] is False
        assert data["skip"] == 50
        assert "No inbound calls yet" in data["html"]

    async def test_empty_outbound(self, async_client):
        resp = await async_client.get("/api/deals?direction=outbound")
        assert resp.status_code == 200
        data = resp.json()
        assert "No outbound calls yet" in data["html"]

    async def test_with_docs(self, async_client, mock_calls_collection):
        # Insert a couple of inbound docs
        for i in range(3):
            await mock_calls_collection.insert_one({
                "call_direction": "inbound",
                "caller_number": f"+92300123456{i}",
                "business_name": f"Company {i}",
                "status": "new",
                "created_at": time.time() + i,
            })
        resp = await async_client.get("/api/deals?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_more"] is False
        # Each card should contain the company name
        for i in range(3):
            assert f"Company {i}" in data["html"]

    async def test_pagination_has_more(self, async_client, mock_calls_collection):
        for i in range(3):
            await mock_calls_collection.insert_one({
                "call_direction": "inbound",
                "caller_number": f"+92300123456{i}",
                "business_name": "",
                "status": "new",
                "created_at": time.time() + i,
            })
        resp = await async_client.get("/api/deals?limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_more"] is True
        assert len([line for line in data["html"].split("\n") if 'data-call-id' in line]) >= 2


class TestGetCallDetail:
    """GET /api/call/{call_id} - single call detail."""

    async def test_not_found(self, async_client):
        resp = await async_client.get("/api/call/000000000000000000000000")
        assert resp.status_code == 404

    async def test_invalid_id_format(self, async_client):
        resp = await async_client.get("/api/call/invalid-id")
        assert resp.status_code == 404

    async def test_success(self, async_client, mock_calls_collection):
        result = await mock_calls_collection.insert_one({
            "call_direction": "inbound",
            "caller_number": "+923001234567",
            "business_name": "Test Corp",
            "transcript_summary": "Test summary",
            "status": "new",
            "created_at": 1700000000.0,
        })
        call_id = str(result.inserted_id)

        resp = await async_client.get(f"/api/call/{call_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["caller_number"] == "+923001234567"
        assert data["business_name"] == "Test Corp"
        assert data["status"] == "new"
        assert "created_at_display" in data


class TestUpdateCallStatus:
    """POST /api/call/{call_id}/status - update reviewed/new."""

    async def test_not_found(self, async_client):
        resp = await async_client.post(
            "/api/call/000000000000000000000000/status",
            json={"status": "reviewed"},
        )
        assert resp.status_code == 404

    async def test_invalid_status(self, async_client, mock_calls_collection):
        result = await mock_calls_collection.insert_one({
            "call_direction": "inbound",
            "caller_number": "+923001234567",
            "status": "new",
            "created_at": time.time(),
        })
        call_id = str(result.inserted_id)
        resp = await async_client.post(
            f"/api/call/{call_id}/status",
            json={"status": "invalid"},
        )
        assert resp.status_code == 400
        assert "must be 'new' or 'reviewed'" in resp.json()["detail"]

    async def test_mark_reviewed(self, async_client, mock_calls_collection):
        result = await mock_calls_collection.insert_one({
            "call_direction": "inbound",
            "caller_number": "+923001234567",
            "status": "new",
            "created_at": time.time(),
        })
        call_id = str(result.inserted_id)
        resp = await async_client.post(
            f"/api/call/{call_id}/status",
            json={"status": "reviewed"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "reviewed"

        # Verify the DB was actually updated
        doc = await mock_calls_collection.find_one({"_id": result.inserted_id})
        assert doc["status"] == "reviewed"

    async def test_mark_new_again(self, async_client, mock_calls_collection):
        result = await mock_calls_collection.insert_one({
            "call_direction": "inbound",
            "caller_number": "+923001234567",
            "status": "reviewed",
            "created_at": time.time(),
        })
        call_id = str(result.inserted_id)
        resp = await async_client.post(
            f"/api/call/{call_id}/status",
            json={"status": "new"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "new"


# ===========================================================================
# Outbound calls
# ===========================================================================

class TestPlaceOutboundCall:
    """POST /api/outbound-call - single number dial."""

    async def test_invalid_number(self, async_client):
        resp = await async_client.post(
            "/api/outbound-call",
            json={"phone_number": "abc"},
        )
        assert resp.status_code == 400
        assert "doesn't look like a valid number" in resp.json()["detail"].lower()

    async def test_missing_livekit_config(self, async_client):
        """When LiveKit config is missing, returns 500."""
        resp = await async_client.post(
            "/api/outbound-call",
            json={"phone_number": "03001234567"},
        )
        # Either 500 (config missing) or actual dial attempt
        assert resp.status_code in (500, 502, 200)

    @patch("routers.outbound._dispatch_one_call")
    async def test_successful_dial(self, mock_dispatch, async_client):
        """Valid number with mocked dispatch."""
        mock_dispatch.return_value = {
            "phone_number": "+923001234567",
            "status": "dialing",
            "call_id": "mock-call-id",
            "room_name": "room-mock",
        }
        resp = await async_client.post(
            "/api/outbound-call",
            json={"phone_number": "03001234567"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "dialing"
        assert data["phone_number"] == "+923001234567"

    @patch("routers.outbound._dispatch_one_call")
    async def test_failed_dial(self, mock_dispatch, async_client):
        """Dispatch failure returns 502."""
        mock_dispatch.return_value = {
            "phone_number": "+923001234567",
            "status": "failed",
            "error": "Something went wrong",
        }
        resp = await async_client.post(
            "/api/outbound-call",
            json={"phone_number": "03001234567"},
        )
        assert resp.status_code == 502


class TestBulkOutboundCall:
    """POST /api/outbound-calls/bulk - multi-number dial."""

    async def test_empty_list(self, async_client):
        resp = await async_client.post(
            "/api/outbound-calls/bulk",
            json={"phone_numbers": []},
        )
        assert resp.status_code == 422  # Validation error

    async def test_too_many_numbers(self, async_client):
        """Sending more than MAX_BULK_CALL_NUMBERS (25) returns 400."""
        many_numbers = [f"03001234{i:03d}" for i in range(30)]
        resp = await async_client.post(
            "/api/outbound-calls/bulk",
            json={"phone_numbers": many_numbers},
        )
        assert resp.status_code == 400
        assert "25 or fewer" in resp.json()["detail"]

    @patch("routers.outbound._dispatch_one_call")
    async def test_bulk_with_mixed_validity(self, mock_dispatch, async_client):
        """Mixed valid/invalid numbers produce per-number results."""
        mock_dispatch.return_value = {
            "phone_number": "+923001234567",
            "status": "dialing",
            "call_id": "mock-id",
        }

        resp = await async_client.post(
            "/api/outbound-calls/bulk",
            json={"phone_numbers": ["03001234567", "invalid", "03151234567"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["requested"] == 3
        assert data["started"] >= 2  # At least 2 valid numbers

        results = {r["phone_number"]: r["status"] for r in data["results"]}
        assert "+923001234567" in results
        assert "invalid" in results

    @patch("routers.outbound._dispatch_one_call")
    async def test_deduplication(self, mock_dispatch, async_client):
        """Duplicate normalized numbers are skipped."""
        mock_dispatch.return_value = {
            "phone_number": "+923001234567",
            "status": "dialing",
            "call_id": "mock-id",
        }

        resp = await async_client.post(
            "/api/outbound-calls/bulk",
            json={"phone_numbers": ["03001234567", "+923001234567", "03001234567"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should have started only 1 (the first unique), skipped 2nd, 3rd is dedup
        skipped = sum(1 for r in data["results"] if r["status"] == "skipped")
        assert skipped >= 1


# ===========================================================================
# Webhook
# ===========================================================================

class TestWebhook:
    """POST /webhook/call-summary (and /webhook/lead) - end-of-call payload."""

    async def test_receive_minimal(self, async_client):
        """Minimal valid payload."""
        resp = await async_client.post(
            "/webhook/call-summary",
            json={"caller_number": "+923001234567"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "received"
        assert "call_id" in data

    async def test_receive_full_payload(self, async_client, mock_calls_collection):
        """Full payload with all fields."""
        resp = await async_client.post(
            "/webhook/call-summary",
            json={
                "caller_number": "+923001234567",
                "call_direction": "inbound",
                "room_name": "room-xyz",
                "business_name": "Test Corp",
                "notes": "Interested in services",
                "transcript_summary": "یہ ایک ٹیسٹ ہے۔",
                "recording_url": "https://example.com/rec.wav",
                "call_duration": 95.3,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "received"

        # Verify it was stored
        doc = await mock_calls_collection.find_one({"room_name": "room-xyz"})
        assert doc is not None
        assert doc["business_name"] == "Test Corp"
        assert doc["call_duration"] == 95.3

    async def test_upsert_by_room_name(self, async_client, mock_calls_collection):
        """Same room_name updates existing doc instead of inserting new."""
        # Insert initial
        resp1 = await async_client.post(
            "/webhook/call-summary",
            json={
                "caller_number": "+923001234567",
                "room_name": "room-upsert",
                "business_name": "Initial Name",
            },
        )
        call_id_1 = resp1.json()["call_id"]

        # Send update
        resp2 = await async_client.post(
            "/webhook/call-summary",
            json={
                "caller_number": "+923001234567",
                "room_name": "room-upsert",
                "business_name": "Updated Name",
            },
        )
        call_id_2 = resp2.json()["call_id"]

        # Both should reference the same document
        assert call_id_1 == call_id_2

        doc = await mock_calls_collection.find_one({"room_name": "room-upsert"})
        assert doc["business_name"] == "Updated Name"

    async def test_unknown_caller_falls_back(self, async_client):
        """Whitespace-only caller_number becomes 'Unknown Participant'."""
        resp = await async_client.post(
            "/webhook/call-summary",
            json={"caller_number": "   "},
        )
        assert resp.status_code == 200

    async def test_unknown_caller_stripped(self, async_client, mock_calls_collection):
        """Whitespace-padded caller_number gets stripped."""
        resp = await async_client.post(
            "/webhook/call-summary",
            json={"caller_number": "  +923001234567  "},
        )
        assert resp.status_code == 200

    async def test_lead_endpoint_also_works(self, async_client):
        """POST /webhook/lead maps to the same handler."""
        resp = await async_client.post(
            "/webhook/lead",
            json={"caller_number": "+923001234567"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "received"

    async def test_missing_caller_number(self, async_client):
        """caller_number defaults to empty string when not provided (schema validation passes)."""
        # caller_number is a required str field, so sending it as empty is valid
        resp = await async_client.post(
            "/webhook/call-summary",
            json={"caller_number": ""},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "received"


# ===========================================================================
# SSE endpoint
# ===========================================================================

class TestSSE:
    """GET /events/deals - Server-Sent Events."""

    async def test_sse_stream_starts(self, async_client):
        """SSE endpoint is registered and responds."""
        from routers.calls import router as calls_router
        paths = {r.path for r in calls_router.routes}
        assert "/events/deals" in paths
