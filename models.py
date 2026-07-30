"""
Pydantic models: the agent's end-of-call webhook payload, and the request
bodies for the dashboard's own API endpoints.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class CallSummary(BaseModel):
    """Posted by agent.py when a call (inbound or outbound) finishes."""
    caller_number: str
    call_direction: Optional[str] = "inbound"   # "inbound" | "outbound"
    room_name: Optional[str] = None
    business_name: Optional[str] = None
    notes: Optional[str] = None
    transcript_summary: Optional[str] = None     # AI Urdu Summary
    recording_url: Optional[str] = None
    call_duration: Optional[float] = None


class OutboundCallRequest(BaseModel):
    """Single-number dial."""
    phone_number: str


class BulkOutboundCallRequest(BaseModel):
    """Multiple numbers entered on the 'Make Calls' screen."""
    phone_numbers: List[str] = Field(..., min_length=1)


class StatusUpdate(BaseModel):
    status: str