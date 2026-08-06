"""Tests for HTML card rendering (rendering.py)."""
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from rendering import PAKISTAN_TZ, render_card, render_cards_html, _format_duration


# ---------------------------------------------------------------------------
# _format_duration
# ---------------------------------------------------------------------------

class TestFormatDuration:
    def test_none(self):
        """None duration → em dash."""
        assert _format_duration(None) == "—"

    def test_zero(self):
        """Zero duration → em dash."""
        assert _format_duration(0) == "—"

    def test_seconds_only(self):
        """Less than a minute → 0:ss."""
        assert _format_duration(45) == "0:45"
        assert _format_duration(5) == "0:05"

    def test_minutes_and_seconds(self):
        """Minutes and seconds → m:ss."""
        assert _format_duration(125) == "2:05"
        assert _format_duration(3661) == "61:01"

    def test_rounds_float(self):
        """Float seconds are rounded."""
        assert _format_duration(90.7) == "1:31"


# ---------------------------------------------------------------------------
# render_card
# ---------------------------------------------------------------------------

class TestRenderCard:
    def _make_doc(self, overrides: dict | None = None) -> dict:
        doc = {
            "_id": "000000000000000000000001",
            "call_direction": "inbound",
            "room_name": "room-abc",
            "caller_number": "+923001234567",
            "business_name": "Test Corp",
            "email": "",
            "phone_number": "",
            "whatsapp_number": "",
            "notes": "Interested in services",
            "transcript_summary": "یہ ایک ٹیسٹ کا خلاصہ ہے۔",
            "recording_url": None,
            "call_duration": None,
            "status": "new",
            "created_at": time.time(),
        }
        if overrides:
            doc.update(overrides)
        return doc

    def test_renders_row_article(self):
        """Renders as an <article class='row'> with data attributes."""
        html = render_card(self._make_doc())
        assert '<article class="row"' in html
        assert 'data-call-id="000000000000000000000001"' in html
        assert 'data-status="new"' in html
        assert 'data-search="+923001234567"' in html
        assert 'tabindex="0"' in html

    def test_shows_caller_number(self):
        """Caller number appears in the card."""
        html = render_card(self._make_doc())
        assert "+923001234567" in html

    def test_unknown_caller_number(self):
        """Blank/whitespace caller → 'Unknown Number'."""
        html = render_card(self._make_doc({"caller_number": ""}))
        assert "Unknown Number" in html
        html = render_card(self._make_doc({"caller_number": "   "}))
        assert "Unknown Number" in html

    def test_local_participant_filtered(self):
        """'<local-participant>' placeholder → 'Unknown Number'."""
        html = render_card(self._make_doc({"caller_number": "<local-participant>"}))
        assert "Unknown Number" in html

    def test_direction_badge(self):
        """Direction badge shows 'Inbound' or 'Outbound'."""
        inbound_html = render_card(self._make_doc({"call_direction": "inbound"}))
        assert "Inbound" in inbound_html
        outbound_html = render_card(self._make_doc({"call_direction": "outbound"}))
        assert "Outbound" in outbound_html
        assert 'title="Inbound"' in inbound_html
        assert 'title="Outbound"' in outbound_html

    def test_status_pill(self):
        """Status pill CSS classes and labels."""
        for status, expected_label in [
            ("new", "New"),
            ("reviewed", "Reviewed"),
            ("dialing", "Dialing..."),
            ("failed", "Call Failed"),
        ]:
            html = render_card(self._make_doc({"status": status}))
            assert expected_label in html

    def test_unknown_status_falls_back_to_new(self):
        """Unrecognised status falls back to 'New'."""
        html = render_card(self._make_doc({"status": "something-else"}))
        assert "New" in html

    def test_business_name_included(self):
        """Business name appears when present."""
        html = render_card(self._make_doc({"business_name": "Acme Ltd"}))
        assert "Acme Ltd" in html

    def test_no_business_name(self):
        """No business-name span when empty."""
        html = render_card(self._make_doc({"business_name": ""}))
        assert 'class="business-name"' not in html

    def test_timestamp_formatted(self):
        """Timestamp is rendered as 'Mon DD, HH:MM' format in Pakistan time."""
        doc = self._make_doc({"created_at": 1700000000.0})
        html = render_card(doc)
        expected = datetime.fromtimestamp(1700000000.0, tz=PAKISTAN_TZ).strftime("%b %d, %H:%M")
        assert expected in html

    def test_duration_shown(self):
        """Duration is rendered."""
        html = render_card(self._make_doc({"call_duration": 125}))
        assert "2:05" in html

    def test_duration_missing_shows_dash(self):
        """Missing duration shows em dash."""
        html = render_card(self._make_doc({"call_duration": None}))
        assert "—" in html

    def test_pulse_on_new_or_dialing(self):
        """Pulse span shown for new/dialing status."""
        for status in ("new", "dialing"):
            html = render_card(self._make_doc({"status": status}))
            assert '<span class="pulse"' in html

    def test_no_pulse_on_reviewed_or_failed(self):
        """No pulse for reviewed or failed."""
        for status in ("reviewed", "failed"):
            html = render_card(self._make_doc({"status": status}))
            assert '<span class="pulse"' not in html

    def test_data_search_attribute(self):
        """data-search contains lowercase caller number for filtering."""
        html = render_card(self._make_doc({"caller_number": "+92300TEXT"}))
        assert 'data-search="+92300text"' in html


# ---------------------------------------------------------------------------
# render_cards_html
# ---------------------------------------------------------------------------

class TestRenderCardsHtml:
    def test_empty_list_renders_empty_message(self):
        """Empty doc list renders the empty-state placeholder."""
        html = render_cards_html([], "Nothing here yet.")
        assert "Nothing here yet." in html
        assert 'class="empty"' in html

    def test_single_row(self):
        """Single doc renders one row."""
        doc = {
            "_id": "000000000000000000000001",
            "call_direction": "inbound",
            "room_name": "room-abc",
            "caller_number": "+923001234567",
            "business_name": "",
            "email": "",
            "phone_number": "",
            "whatsapp_number": "",
            "notes": "",
            "transcript_summary": "",
            "recording_url": None,
            "call_duration": None,
            "status": "new",
            "created_at": time.time(),
        }
        html = render_cards_html([doc])
        assert 'data-call-id="000000000000000000000001"' in html

    def test_multiple_rows(self):
        """Multiple docs all get rendered."""
        docs = [
            {"_id": f"00000000000000000000000{i}", "call_direction": "inbound",
             "caller_number": f"+92300123456{i}", "business_name": "", "email": "",
             "phone_number": "", "whatsapp_number": "", "notes": "",
             "transcript_summary": "", "recording_url": None, "call_duration": None,
             "status": "new", "created_at": time.time() + i}
            for i in range(1, 4)
        ]
        html = render_cards_html(docs)
        for i in range(1, 4):
            assert f"+92300123456{i}" in html
