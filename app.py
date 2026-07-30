"""
Voice Agent Dashboard -- entrypoint.

This file only wires things together. Logic lives in:
  config.py          settings (.env.local)
  phone.py           phone number validation/formatting
  models.py          request/webhook payload shapes
  db.py              Mongo connection lifecycle
  notifications.py   Slack ping
  rendering.py        HTML for the call cards
  routers/webhook.py  agent.py -> dashboard call summaries
  routers/outbound.py placing outbound calls (single + bulk)
  routers/calls.py    reading calls back out for the UI
"""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from db import lifespan
from rendering import render_cards_html
from routers import calls, outbound, webhook

app = FastAPI(title="Voice Agent Dashboard", lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

static_dir = Path(__file__).parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

app.include_router(webhook.router)
app.include_router(outbound.router)
app.include_router(calls.router)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    cursor = app.state.calls.find({"call_direction": "inbound"}).sort("created_at", -1).limit(50)
    docs = await cursor.to_list(length=50)
    cards_html = render_cards_html(docs, "No inbound calls yet.")

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "cards_html": cards_html,
            "has_more": len(docs) == 50,
        }
    )


@app.get("/health")
async def health():
    return {"ok": True}
