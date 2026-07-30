"""
End-of-call webhook, posted by agent.py once a call finishes.
"""
import time
from fastapi import APIRouter, Request
from models import CallSummary
from notifications import notify_slack
from routers.calls import broadcast_event

router = APIRouter()

@router.post("/webhook/call-summary")
@router.post("/webhook/lead")
async def receive_call_summary(summary: CallSummary, request: Request):
    # Strip whitespace to catch invisible caller IDs
    caller_num = summary.caller_number or ""
    clean_caller = caller_num.strip() if caller_num.strip() else "Unknown Participant"

    doc_fields = {
        "call_direction": summary.call_direction or "inbound",
        "room_name": summary.room_name,
        "caller_number": clean_caller,
        "business_name": summary.business_name or "",
        "notes": summary.notes or "",
        "transcript_summary": summary.transcript_summary or "",
        "recording_url": summary.recording_url,
        "call_duration": summary.call_duration,
        "status": "new",
    }
    
    existing = None
    if summary.room_name:
        existing = await request.app.state.calls.find_one({"room_name": summary.room_name})

    if existing:
        await request.app.state.calls.update_one({"_id": existing["_id"]}, {"$set": doc_fields})
        call_id = str(existing["_id"])
        doc_fields["_id"] = call_id
    else:
        doc_fields["created_at"] = time.time()
        result = await request.app.state.calls.insert_one(doc_fields)
        call_id = str(result.inserted_id)

    notify_slack(call_id, doc_fields)
    await broadcast_event("new_deal", {"call_id": call_id, "direction": doc_fields["call_direction"]})
    return {"status": "received", "call_id": call_id}