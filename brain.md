# Project Architecture Overview

This document captures a **high‑level workflow** of the Voice Agent Dashboard and maps every step to the source file that implements it.  It is meant for quick orientation while navigating the codebase.

---

## 1. Entry‑point & Application Bootstrap

| File | Role |
|------|------|
| **app.py** | FastAPI entry point. Sets up the `FastAPI` instance, mounts static assets, includes all routers, and serves the dashboard UI (`/`). Also defines the health endpoint. |
| **config.py** | Holds the `Settings` class (pydantic) that loads environment variables from `.env.local`.  All other modules import `settings` to read configuration (Mongo URI, LiveKit credentials, Slack webhook, etc.). |
| **db.py** | Provides the `lifespan` async context manager that creates a MongoDB client (`motor`), selects the database/collection (`calls`), creates indexes, and stores the client/collection in `app.state` for the rest of the app. |
| **templates/dashboard.html** | Jinja2 template rendered for the root (`/`) route. Renders the inbound list (`{{ cards_html }}`) server-side on load, plus a search bar and column header above it. |
| **static/** | Directory for CSS/JS assets used by the dashboard (mounted at `/static`). |

**Bootstrap flow** (simplified):
```
app.py ──> FastAPI(app)
           ├─ mount /static   (StaticFiles)
           ├─ include_router(webhook)
           ├─ include_router(outbound)
           └─ include_router(calls)
           └─ lifespan= db.lifespan  ──> MongoDB client & collection
```

---
## 2. Data Model & Validation

| File | Role |
|------|------|
| **models.py** | Pydantic schemas used for API payloads:
| – `CallSummary` – payload posted by the agent (`router/webhook.py`).
| – `OutboundCallRequest` – single‑number dial request.
| – `BulkOutboundCallRequest` – bulk dial request.
| – `StatusUpdate` – status‑update payload for a call.
| **phone.py** | Helper utilities for phone‑number normalisation (`normalize_phone_number`) and UI text direction detection (`text_dir_attrs`). |

---
## 3. Rendering Call Rows (List View)

| File | Role |
|------|------|
| **rendering.py** | Turns a Mongo call document into a single HTML *list row* (`render_card` — name kept for backward compatibility, but it now emits a `.row`, not a card) and aggregates them (`render_cards_html`). Each row shows **phone number, date/time, duration, and status** (New / Dialing / Reviewed / Call Failed). A private `_format_duration` helper renders `call_duration` as `m:ss` (or `—` if missing/zero). Caller numbers that are blank or contain the LiveKit test placeholder `<local-participant>` are shown as "Unknown Number". Each row carries a `data-search` attribute (lowercased phone number) used by the front‑end search bar. |
| **templates/dashboard.html** | Consumes the `cards_html` fragment returned by `rendering.render_cards_html` and displays it as a list (`.deal-list`) with a column header row (Phone Number / Date·Time / Duration / Status) and a search input above it. |

---
## 4. Search / Filter (front‑end only)

- Each tab (Dashboard / Make Calls) has its own search input (`#search-inbound`, `#search-outbound`) sitting above its list.
- `dashboard.js` matches the typed text against each row's `data-search` attribute (the phone number, lowercased) and toggles the row's `hidden` attribute — a pure client‑side filter over whatever rows are currently loaded (including ones added via infinite scroll or an SSE‑triggered reload), **not a new API query parameter**.
- If a search yields zero matches among loaded rows, the empty‑state paragraph (`#empty-inbound` / `#empty-outbound`) is shown.
- **Clicking a row still opens the same detail modal as before search/list-view was added.** Search only hides/shows rows in the list — it doesn't change what the modal fetches or displays, and it doesn't affect `GET /api/deals` or `GET /api/call/{id}` in any way.

---
## 5. Routers (FastAPI endpoints)

### 5.1 `routers/calls.py`
- **Purpose** – Serve the UI data for inbound calls and allow status updates.
- **Key endpoints**:
  - `GET /events/deals` – Server‑Sent Events stream that pings the UI every 15 s (keeps the connection alive).
  - `GET /api/deals` – Returns a JSON payload with a page of inbound call documents (used by the front‑end to populate the list). Handles pagination via `skip` & `limit`. Not filtered server‑side by search term.
  - `GET /api/call/{call_id}` – Returns full details for a single call. This is what powers the modal: clicking any row in the list opens the same modal with the complete call detail — caller number, call direction, timestamp, business name, call duration, the full AI Urdu summary, a recording player (if `recording_url` is set), and the Mark as Reviewed / Not Reviewed action. The list-view change only affects the row layout in the grid; it does not change what the modal shows.
  - `POST /api/call/{call_id}/status` – Updates the status (`new`/`reviewed`).

### 5.2 `routers/outbound.py`
- **Purpose** – Allow the dashboard to place outbound calls.
- **Key functions**:
  - `_require_outbound_config` – Validates LiveKit & SIP settings are present.
  - `_dispatch_one_call` – Inserts a *dialing* placeholder document, creates a LiveKit room, and asks LiveKit to dispatch the voice agent.
- **Endpoints**:
  - `POST /api/outbound-call` – Single‑number dial (backwards compatible).
  - `POST /api/outbound-calls/bulk` – Bulk dial; validates, de‑duplicates, and dispatches each number.

### 5.3 `routers/webhook.py`
- **Purpose** – Receive the end‑of‑call webhook emitted by the voice‑agent (`agent.py`).
- **Workflow**:
  1. Parses `CallSummary` payload.
  2. Normalises the caller number & builds a document (`doc_fields`).
  3. If a call with the same `room_name` already exists, it updates that document; otherwise it inserts a new document with `created_at`.
  4. Calls `notifications.notify_slack` (optional).
- **Endpoints**: `POST /webhook/call-summary` and `POST /webhook/lead` (both map to the same handler).

---
## 6. Notifications

| File | Role |
|------|------|
| **notifications.py** | Sends a Slack notification when a new call document is created.  No‑op if `SLACK_WEBHOOK_URL` is not set. |

---
## 7. End‑to‑End Call Lifecycle (Mermaid diagram)
```mermaid
flowchart TD
    A[Dashboard UI (browser)] -->|load page| B[GET / -> app.py -> dashboard.html]
    B -->|fetch rows| C[GET /api/deals -> routers/calls.py]
    C -->|query Mongo| D[db.lifespan -> calls collection]
    D -->|return docs| C -->|render| E[rendering.render_cards_html]
    E -->|HTML list rows| B
    B -->|filter by phone #, client-side| B

    %% Inbound call finishes (agent side)
    subgraph Agent
        X[LiveKit Agent] -->|POST webhook| Y[/webhook/call-summary]
    end
    Y -->|receive payload| Z[routers/webhook.py]
    Z -->|upsert doc| D
    Z -->|optional Slack| F[notifications.notify_slack]
    
    %% Outbound call flow
    B -->|user clicks "Place Call"| G[POST /api/outbound-call]
    G -->|validate & dispatch| H[routers/outbound.py]
    H -->|insert dialing doc| D
    H -->|LiveKit API| I[LiveKit create room & dispatch]
    I -->|agent joins room and dials| X
    
    %% UI updates via SSE
    B -->|open SSE| J[GET /events/deals]
    J -->|periodic ping| B

    %% Row click -> modal
    B -->|click a row| K[GET /api/call/id -> modal detail]
```

---
## 8. File‑by‑File Quick Reference
```
app.py                – FastAPI app, mounts routers, renders dashboard
config.py             – Settings (env vars) used everywhere
db.py                 – MongoDB client & collection lifecycle
models.py             – Request/response schemas for API
phone.py              – Phone normalization + Urdu text helpers
rendering.py          – HTML list-row generation (phone, date/time, duration, status)
notifications.py      – Slack webhook (optional)
routers/calls.py      – Inbound call list, detail, status update, SSE
routers/outbound.py   – Outbound call creation (single & bulk)
routers/webhook.py    – End‑of‑call webhook handling & DB upsert
templates/dashboard.html – UI skeleton: list view + search bar for the dashboard
static/…             – CSS/JS assets (served at /static); dashboard.js also owns the
                        client-side phone-number search/filter over loaded rows
```

---
## 9. How to Extend / Debug
1. **Add a new UI feature** → create a new endpoint in an appropriate router, add a Pydantic model in `models.py` if needed, and render any UI with `rendering.py` helpers.
2. **Change DB schema** → update the document fields in `routers/webhook.py` and `rendering.py` accordingly; remember to add or modify indexes in `db.py`.
3. **LiveKit integration** → adjust `_dispatch_one_call` in `routers/outbound.py` (room naming, metadata) and ensure the LiveKit credentials are present in `.env.local`.
4. **Slack notifications** → modify `notify_slack` in `notifications.py`.
5. **Search/filter** → currently phone-number-only and client-side (`applySearch` in `dashboard.js`, matched against `data-search` on each row). To filter by other fields (status, date range, business name) either add more data to `data-search`, or move filtering server-side via a new `/api/deals` query param.

---
## 10. Environment Variables (`.env.local`)
```
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=voice_agent_db
SLACK_WEBHOOK_URL=...
PUBLIC_BASE_URL=http://localhost:8000
LIVEKIT_URL=...
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
SIP_OUTBOUND_TRUNK_ID=...
VOICE_AGENT_NAME=urdu-voicebot
MAX_BULK_CALL_NUMBERS=25
```
All of these are loaded by `config.Settings` and accessed via `request.app.state.settings`.

---
*End of Architecture Overview*