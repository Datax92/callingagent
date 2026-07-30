# Urdu Voicebot — Voice Agent + Dashboard

Two services, one docker-compose stack:

- **voice-agent** (`Dockerfile.voice`) — the LiveKit voice agent (`agent.py`): handles
  inbound calls and places outbound calls, using Deepgram STT, Groq (LLM), and Piper TTS.
- **fastapi-dashboard** (`Dockerfile`) — the dashboard: view inbound calls, place outbound
  calls (single or bulk), and review call details/recordings.

See `Urdu_Voicebot_Architecture_Final.md` for the full architecture writeup.

## Project layout

```
agent.py                     Voice agent entrypoint (LiveKit worker)
rag_utils.py                 Filtered-lookup RAG helper (used by agent.py)
piper_tts.py                 (not included here — your existing Piper TTS wrapper)
datax_technologies_approved_rag.jsonl   (not included here — your knowledge base)

app.py                       Dashboard entrypoint — wires the pieces below together
config.py                    Dashboard settings (.env.local / environment)
db.py                        MongoDB connection lifecycle
models.py                    Request / webhook payload shapes
notifications.py             Slack ping on new call
phone.py                     Phone number validation/formatting
rendering.py                 Call-card HTML rendering
routers/webhook.py           agent.py -> dashboard call summaries
routers/outbound.py          Placing outbound calls (single + bulk)
routers/calls.py             Reading calls back out (grid, detail, status, SSE)
templates/dashboard.html     Dashboard page markup
static/css/dashboard.css     Dashboard styling
static/js/dashboard.js       Dashboard client behavior

Dockerfile                   Builds fastapi-dashboard
Dockerfile.voice             Builds voice-agent
docker-compose.yml           Runs both together
.env.local.example           Every environment variable either service reads
requirements*.txt            Pinned dependencies (voice / dashboard / combined)
```

`piper_tts.py` and `datax_technologies_approved_rag.jsonl` aren't included in this
delivery — keep your existing copies in the project root; `Dockerfile.voice` already
expects them there.

## How the two services actually connect

This was the main gap fixed in this pass — previously the pieces were built but not
wired together end-to-end:

1. **Dashboard → LiveKit → Agent (outbound).** The dashboard's "Make Calls" screen
   (`routers/outbound.py`) asks LiveKit to dispatch `agent.py` into a fresh room, passing
   `{"direction": "outbound", "phone_number": "+92..."}` as job metadata. `agent.py`'s
   `entrypoint()` now reads that metadata and — this part was previously missing entirely —
   actually places the SIP call to that number itself via `livekit.api`'s SIP service,
   using `SIP_OUTBOUND_TRUNK_ID`. Only once that's answered does it greet the person.
2. **Agent → Dashboard (call summary).** When a call ends, `agent.py` POSTs a summary to
   `DASHBOARD_WEBHOOK_URL`. It now includes `call_direction` and `room_name` in that
   payload — without these, the dashboard couldn't tell inbound from outbound, and
   outbound calls placed from the dashboard would sit at "Dialing..." forever because
   there was nothing to match the summary back to the placeholder row.
3. **Dashboard → MongoDB.** `db.py` now reads the database name from `MONGODB_DATABASE`
   (matching docker-compose) instead of a hardcoded value, so the two can't drift apart.
4. **Inbound greeting bug.** `agent.py` previously spoke the outbound greeting line on
   *every* call, inbound included. It now only does that for outbound calls; inbound
   calls wait for the caller to speak first, as intended.

## Running it

```bash
cp .env.local.example .env.local
# fill in .env.local with real values

docker compose up --build
```

The dashboard will be at `http://localhost:8000` once both containers report healthy
(`docker compose ps`). `fastapi-dashboard` waits on `voice-agent`'s healthcheck before
starting — if `voice-agent` never goes healthy, check `docker compose logs voice-agent`
first (usually a missing/invalid `GROQ_API_KEY`, `DEEPGRAM_API_KEY`, or LiveKit
credential).

### Required before outbound calling works
- `LIVEKIT_URL` / `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` (both services)
- `SIP_OUTBOUND_TRUNK_ID` — a LiveKit Cloud outbound SIP trunk (both services)
- `VOICE_AGENT_NAME` — must match on both services (defaults to `urdu-voicebot` on both)

### Required before inbound calling works
- A LiveKit **inbound** SIP trunk + dispatch rule pointed at `VOICE_AGENT_NAME`
  (configured in LiveKit Cloud, not in this repo)

### Required before calls get logged anywhere
- `MONGODB_URI` (dashboard)
- `DASHBOARD_WEBHOOK_URL` — inside docker-compose this must be
  `http://fastapi-dashboard:8000/webhook/lead` (the service name, not `localhost`)

## Local development (no Docker)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-local.txt   # installs requirements.txt + dev tools

cp .env.local.example .env.local        # fill in real values

# Terminal 1
uvicorn app:app --reload

# Terminal 2
python agent.py dev
```

## What's in this delivery vs. what changed

- **New:** `Dockerfile` for the dashboard (referenced by `docker-compose.yml` but never
  provided), `.env.local.example`, `.dockerignore`.
- **Fixed:** the `voice-agent` healthcheck in `docker-compose.yml` was checking
  `import groq`, a package that's deliberately not installed — this made the container
  permanently "unhealthy" and would have blocked `fastapi-dashboard` from ever starting
  (it waits on `condition: service_healthy`).
- **Fixed:** `agent.py` now actually dials out for outbound calls, tags call summaries
  with direction + room name, and only greets first on outbound calls.
- **Fixed:** `db.py` honors `MONGODB_DATABASE` instead of a hardcoded name.
- **Added:** `livekit-api` to `requirements-dashboard.txt` / `requirements.txt` — used by
  the outbound-calling code but never actually pinned anywhere.
- **Unchanged:** `rag_utils.py`, the architecture doc, and everything about the LLM
  system prompt / RAG behavior.
