"""Shared fixtures for all tests."""
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, AsyncGenerator, Generator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

# Ensure the project root is on sys.path so imports work
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Fixtures: MongoDB mock state
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_calls_collection():
    """An in-memory mock that mimics the async Motor collection interface
    enough to let the routers and rendering pass through tests.

    Uses a plain dict keyed by stringified ObjectId so we can test find_one,
    insert_one, update_one, find().sort().skip().limit() etc.
    """
    import time
    from bson import ObjectId

    store: dict[str, dict] = {}
    _id_counter = [0]

    def _next_id() -> ObjectId:
        _id_counter[0] += 1
        return ObjectId(f"000000000000{_id_counter[0]:0>12x}")

    class Cursor:
        """Simulates MotorCursor with sort/skip/limit/to_list."""
        def __init__(self, docs, sort_key=None, sort_dir=-1):
            self._docs = list(docs)
            self._sort_key = sort_key
            self._sort_dir = sort_dir
            self._skip_n = 0
            self._limit_n = 0

        def sort(self, key, direction=-1):
            self._sort_key = key
            self._sort_dir = direction
            return self

        def skip(self, n):
            self._skip_n = n
            return self

        def limit(self, n):
            self._limit_n = n
            return self

        async def to_list(self, length=None):
            docs = self._docs
            if self._sort_key:
                reverse = self._sort_dir == -1
                docs = sorted(docs, key=lambda d: d.get(self._sort_key, 0), reverse=reverse)
            if self._skip_n:
                docs = docs[self._skip_n:]
            if self._limit_n:
                docs = docs[:self._limit_n]
            return docs

    class MockCollection:
        async def find_one(self, filter_: dict) -> dict | None:
            # Support _id lookup
            _id = filter_.get("_id")
            if _id:
                key = str(_id)
                doc = store.get(key)
                if doc:
                    return {**doc, "_id": _id}
            # Support room_name lookup
            room = filter_.get("room_name")
            if room:
                for doc in store.values():
                    if doc.get("room_name") == room:
                        return {**doc, "_id": ObjectId(doc["_id"])}
            return None

        async def insert_one(self, doc: dict) -> Any:
            _id = _next_id()
            key = str(_id)
            doc["_id"] = key
            store[key] = dict(doc)
            result = type("Result", (), {"inserted_id": _id})()
            return result

        async def update_one(self, filter_: dict, update: dict) -> Any:
            _id = filter_.get("_id")
            key = str(_id)
            if key in store:
                set_fields = update.get("$set", {})
                store[key].update(set_fields)
                return type("Result", (), {"matched_count": 1, "modified_count": 1})()
            return type("Result", (), {"matched_count": 0, "modified_count": 0})()

        def find(self, filter_: dict | None = None) -> Cursor:
            filter_ = filter_ or {}
            direction = filter_.get("call_direction")
            if direction:
                docs = [d for d in store.values() if d.get("call_direction") == direction]
            else:
                docs = list(store.values())
            return Cursor(docs)

    return MockCollection()


@pytest.fixture
def mock_app_state(mock_calls_collection):
    """Minimal app.state duck for the routers to consume."""
    from config import settings
    return type("State", (), {
        "calls": mock_calls_collection,
        "settings": settings,
        "mongo_client": None,
    })()


@pytest.fixture
def sample_call_doc() -> dict:
    """A typical inbound call document."""
    return {
        "_id": "000000000000000000000001",
        "call_direction": "inbound",
        "room_name": "room-abc123",
        "caller_number": "+923001234567",
        "business_name": "Test Corp",
        "email": "",
        "phone_number": "",
        "whatsapp_number": "",
        "notes": "Interested in web development",
        "transcript_summary": "یہ ایک ٹیسٹ کال ہے۔ گاہک کو ویب سائٹ میں دلچسپی ہے۔",
        "recording_url": "https://example.com/recording.wav",
        "call_duration": 120.5,
        "status": "new",
        "created_at": 1700000000.0,
    }


@pytest.fixture
def sample_outbound_call_doc() -> dict:
    """A typical outbound call document (dialing)."""
    return {
        "_id": "000000000000000000000002",
        "call_direction": "outbound",
        "room_name": "outbound-def456",
        "caller_number": "+923001234567",
        "business_name": "",
        "email": "",
        "phone_number": "",
        "whatsapp_number": "",
        "notes": "",
        "transcript_summary": "",
        "recording_url": None,
        "call_duration": None,
        "status": "dialing",
        "created_at": 1700000100.0,
    }


# ---------------------------------------------------------------------------
# Fixtures: FastAPI TestClient
# ---------------------------------------------------------------------------

@pytest.fixture
def test_app(mock_calls_collection):
    """Build a minimal FastAPI app with all routers included and the mock
    collection wired into app.state.

    Sets dummy LiveKit env vars so outbound-call tests pass without real
    SIP trunk credentials — the actual dispatch is mocked in those tests.

    Uses monkeypatch via the _livekit_env fixture to set env vars before
    this fixture runs.
    """
    from config import settings

    # Override the existing singleton's LiveKit fields so
    # _require_outbound_config in routers/outbound.py passes.
    settings.livekit_url = "https://test.livekit.cloud"
    settings.livekit_api_key = "test-key"
    settings.livekit_api_secret = "test-secret"
    settings.sip_outbound_trunk_id = "test-trunk"
    settings.voice_agent_name = "test-agent"

    from app import app as real_app
    real_app.state.calls = mock_calls_collection
    real_app.state.settings = settings
    real_app.state.mongo_client = None
    return real_app


@pytest.fixture
async def async_client(test_app) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for testing FastAPI endpoints."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# Fixtures: Temp knowledge base for RAG tests
# ---------------------------------------------------------------------------

@pytest.fixture
def rag_kb_file() -> Generator[str, None, None]:
    """Write a temporary JSONL knowledge base and yield its path."""
    lines = [
        json.dumps({"content": "ہم ویب سائٹ ڈیزائن اور ڈویلپمنٹ کی services فراہم کرتے ہیں۔"}),
        json.dumps({"content": "موبائل ایپ ڈویلپمنٹ کے لیے ہم سے رابطہ کریں۔"}),
        json.dumps({"content": "بزنس آٹومیشن کے solutions بھی دستیاب ہیں۔"}),
        json.dumps({"content": "کسٹم سافٹ ویئر ڈویلپمنٹ کی تفصیلات کے لیے ہماری ٹیم سے بات کریں۔"}),
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
        f.flush()
        path = f.name
    yield path
    os.unlink(path)


# ---------------------------------------------------------------------------
# Fixtures: Environment reset helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_env():
    """Reset environment variables that tests might modify."""
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)
