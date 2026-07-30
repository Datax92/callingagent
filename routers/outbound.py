"""
Placing outbound calls. The agent's job here is strictly to place the call
and have the conversation -- it does not negotiate price, so this layer
never accepts or forwards any pricing/offer data, only phone numbers.
"""
import json
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from models import BulkOutboundCallRequest, OutboundCallRequest
from phone import normalize_phone_number

router = APIRouter()


def _require_outbound_config(cfg):
    if not all([cfg.livekit_url, cfg.livekit_api_key, cfg.livekit_api_secret, cfg.sip_outbound_trunk_id]):
        raise HTTPException(
            status_code=500,
            detail="Outbound calling isn't set up yet -- LIVEKIT_URL, LIVEKIT_API_KEY, "
                   "LIVEKIT_API_SECRET and SIP_OUTBOUND_TRUNK_ID all need to be set in .env.local.",
        )


async def _dispatch_one_call(number: str, request: Request) -> dict:
    """
    Places a single outbound call: writes a 'dialing' placeholder row, then
    asks LiveKit to dispatch the voice agent into a fresh room with the
    target number in the job metadata. The agent places the SIP call once
    it has joined the room (see the outbound-call snippet in agent.py's
    entrypoint) -- this is LiveKit's documented pattern, rather than the
    dashboard trying to create the SIP participant into a room the agent
    hasn't joined yet.

    Returns a dict describing the outcome; never raises for per-call
    failures so a bulk dial can keep going through the rest of the list.
    """
    cfg = request.app.state.settings

    try:
        from livekit import api as lk_api
    except ImportError:
        return {"phone_number": number, "status": "failed",
                "error": "The livekit-api package isn't installed. Run: pip install livekit-api"}

    room_name = f"outbound-{uuid4().hex[:10]}"

    doc = {
        "call_direction": "outbound",
        "room_name": room_name,
        "caller_number": number,
        "business_name": "",
        "email": "",
        "phone_number": "",
        "whatsapp_number": "",
        "notes": "",
        "transcript_summary": "",
        "recording_url": None,
        "call_duration": None,
        "status": "dialing",
        "created_at": time.time(),
    }
    result = await request.app.state.calls.insert_one(doc)
    call_id = str(result.inserted_id)

    try:
        async with lk_api.LiveKitAPI(
            cfg.livekit_url, cfg.livekit_api_key, cfg.livekit_api_secret
        ) as lkapi:
            await lkapi.agent_dispatch.create_dispatch(
                lk_api.CreateAgentDispatchRequest(
                    room=room_name,
                    agent_name=cfg.voice_agent_name,
                    metadata=json.dumps({"direction": "outbound", "phone_number": number}),
                )
            )
    except Exception as e:
        await request.app.state.calls.update_one(
            {"_id": result.inserted_id}, {"$set": {"status": "failed", "notes": str(e)}}
        )
        return {"phone_number": number, "status": "failed", "call_id": call_id, "error": str(e)}

    return {"phone_number": number, "status": "dialing", "call_id": call_id, "room_name": room_name}


@router.post("/api/outbound-call")
async def place_outbound_call(body: OutboundCallRequest, request: Request):
    """Single-number dial. Kept for backwards compatibility / direct API use."""
    number = normalize_phone_number(body.phone_number)
    if not number:
        raise HTTPException(
            status_code=400,
            detail="That doesn't look like a valid number. Use a Pakistani mobile "
                   "like 03XXXXXXXXX or an international number like +92XXXXXXXXXX.",
        )
    _require_outbound_config(request.app.state.settings)

    outcome = await _dispatch_one_call(number, request)
    if outcome["status"] == "failed":
        raise HTTPException(status_code=502, detail=f"Couldn't start the call: {outcome.get('error')}")
    return outcome


@router.post("/api/outbound-calls/bulk")
async def place_bulk_outbound_calls(body: BulkOutboundCallRequest, request: Request):
    """
    Called by the 'Make Calls' screen. Accepts a list of numbers (as typed
    or pasted by the user), validates + de-duplicates them, then dials each
    one in turn. Returns a per-number result so the UI can show exactly
    which numbers went through and which didn't -- no partial silent
    failures.
    """
    cfg = request.app.state.settings
    _require_outbound_config(cfg)

    max_numbers = cfg.max_bulk_call_numbers
    raw_numbers = body.phone_numbers[:max_numbers + 1]  # +1 just so we can detect "too many"
    if len(body.phone_numbers) > max_numbers:
        raise HTTPException(
            status_code=400,
            detail=f"That's {len(body.phone_numbers)} numbers -- please send {max_numbers} or fewer at a time.",
        )

    results = []
    seen = set()
    for raw in raw_numbers:
        normalized = normalize_phone_number(raw)
        if not normalized:
            results.append({"phone_number": raw, "status": "invalid",
                             "error": "Doesn't look like a valid number."})
            continue
        if normalized in seen:
            results.append({"phone_number": raw, "status": "skipped",
                             "error": "Duplicate -- already queued above."})
            continue
        seen.add(normalized)
        outcome = await _dispatch_one_call(normalized, request)
        results.append(outcome)

    started = sum(1 for r in results if r["status"] == "dialing")
    return {
        "requested": len(body.phone_numbers),
        "started": started,
        "results": results,
    }
