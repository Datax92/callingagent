"""
Reading calls back out: the grid feed, a single call's full detail (for the
modal), marking reviewed/not-reviewed, and the SSE endpoint that tells the
page to refresh when something changes.
"""
import asyncio
import json
import time

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from models import StatusUpdate
from rendering import render_cards_html

router = APIRouter()

# ---------------------------------------------------------------------------
# Simple pub/sub bus for SSE events
# ---------------------------------------------------------------------------
_sse_clients: set[asyncio.Queue] = set()


async def broadcast_event(event: str, data: dict | None = None) -> None:
    """Push a named SSE event to every connected client."""
    payload = data or {}
    dead: list[asyncio.Queue] = []
    for q in _sse_clients:
        try:
            q.put_nowait((event, payload))
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _sse_clients.discard(q)


@router.get("/events/deals")
async def events_deals(request: Request):
    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue(maxsize=32)
        _sse_clients.add(queue)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event, data = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: {event}\ndata: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'ping'})}\n\n"
        finally:
            _sse_clients.discard(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/deals")
async def api_deals(request: Request, direction: str = "inbound", skip: int = 0, limit: int = 50):
    if direction not in ("inbound", "outbound"):
        direction = "inbound"
    cursor = (
        request.app.state.calls.find({"call_direction": direction})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit + 1)
    )
    docs = await cursor.to_list(length=limit + 1)
    has_more = len(docs) > limit
    empty_msg = (
        "No inbound calls yet." if direction == "inbound"
        else "No outbound calls yet -- use the form above to place one."
    )
    return JSONResponse({
        "html": render_cards_html(docs[:limit], empty_msg),
        "has_more": has_more,
        "skip": skip + limit,
    })


@router.get("/api/call/{call_id}")
async def get_call_detail(call_id: str, request: Request):
    try:
        oid = ObjectId(call_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Call not found")
    doc = await request.app.state.calls.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Call not found")
    doc["_id"] = str(doc["_id"])
    doc["created_at_display"] = time.strftime("%b %d, %Y -- %H:%M", time.localtime(doc.get("created_at", 0)))
    return JSONResponse(doc)


@router.post("/api/call/{call_id}/status")
async def update_call_status(call_id: str, body: StatusUpdate, request: Request):
    if body.status not in ("new", "reviewed"):
        raise HTTPException(status_code=400, detail="status must be 'new' or 'reviewed'")
    try:
        oid = ObjectId(call_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Call not found")
    result = await request.app.state.calls.update_one({"_id": oid}, {"$set": {"status": body.status}})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Call not found")
    return {"status": body.status}
