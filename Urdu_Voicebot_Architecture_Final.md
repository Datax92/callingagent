# Urdu Voicebot — Final Architecture (GROQ API + RAG + System Prompt)

**System:** Inbound/outbound Urdu voice agent (cold-calling / customer support)
**LLM:** GROQ Cloud API (hosted Qwen model, no self-hosted GPU, no fine-tuning)
**Status:** Final production architecture
**Last updated:** July 24, 2026

---

## 1. Purpose & Scope

Single technical reference for the voicebot's production deployment. The agent handles both
inbound and outbound Urdu voice calls using one consistent pipeline: Speech-to-Text → LLM (GROQ
API, grounded with RAG and a fixed system prompt) → Text-to-Speech, wrapped around a lead-gen
dashboard.

**Design targets:**
- End-to-end turn latency (caller stops speaking → bot starts speaking): **p95 ≤ 650ms**
- Language: Urdu only, streaming STT and local TTS
- Call volume basis: ~5,000 active call minutes/month
- Same system prompt used for both inbound and outbound calls (hard constraint)
- No paid vector database, no idle infrastructure, no cold starts

---

## 2. High-Level Architecture

```text
                                +--------------------------+
                                |     PSTN / Phone Net     |
                                |   (Pakistani Mobiles)    |
                                +-------------+------------+
                                              |
                                +-------------v------------+
                                |        PTCL SIP           |
                                |  (Business SIP Trunk)     |
                                +-------------+------------+
                                              | SIP over TLS/SRTP
                                +-------------v------------+
        +---------------------+|      LiveKit Cloud        |+---------------------+
        |                      ||  (SIP Trunk + WebRTC SFU) ||                      |
        |                      |+-------------+------------+|                      |
        | WebRTC Audio                        | WebRTC Audio                       | Egress WAV/MP3
        |                                     |                                    |
+-------v--------+           +----------------v-----------------+          +-------v--------+
|   Deepgram      |           |     CONSOLIDATED APP SERVER      |          | Cloudflare R2   |
|   Nova-3 Urdu   |==========>|      (Railway, compute-tier)     |          | (Call Recording |
|   (Streaming    |  WebSocket|  - Voice Agent Loop (LiveKit SDK)|          |   Archive)      |
|    STT)         |           |  - FastAPI Dashboard             |          +-------+---------+
+-----------------+           |  - Piper TTS (local, CPU-bound)  |                  ^
                               |  - RAG: filtered JSON lookup,    |                  | URL reference
                               |    <500 tok injected per turn    |                  |
                               |  - Fixed system prompt (shared   |                  |
                               |    inbound/outbound)             |                  |
                               +----------------+------------------+<-----------------+
                                                |         |
                        Prompt + filtered RAG   |         | Call metadata / leads
                        chunk (HTTPS, streamed) |         v
                                                |   +-------------------+
                                                |   |  MongoDB Atlas    |
                                                |   |  (Shared/M0-M10)  |
                                                |   +-------------------+
                                                v
                          +---------------------------------------------+
                          |              GROQ CLOUD API                 |
                          |   Managed, pay-per-token, always warm        |
                          |   Model: Qwen3 (Groq-hosted — confirm exact  |
                          |   SKU against Groq's live catalog before     |
                          |   build)                                     |
                          |   Streaming chat completions, no ops         |
                          +---------------------------------------------+
```

---

## 3. Call Sequence (Inbound Example)

1. Caller dials the PTCL number → **PTCL SIP trunk** delivers the call over SIP/TLS.
2. LiveKit's **SIP inbound trunk** receives the INVITE and, per the dispatch rule, creates a new
   room and auto-dispatches the calling agent into it.
3. The **Voice Agent Loop** (LiveKit Agents SDK) joins the room, subscribes to the caller's audio
   track, and streams it to **Deepgram Nova-3 (Urdu)** over WebSocket for real-time transcription.
4. As Deepgram returns transcribed text, it's appended to the conversation history.
5. The agent builds the prompt: **fixed system prompt** (identical for inbound/outbound) +
   **filtered RAG chunk** (relevant policy/business-detail snippet, <500 tokens — not the full
   knowledge base) + bounded conversation history (last ~6 messages) + latest user turn.
6. The prompt is sent to the **GROQ Cloud API** as a streaming chat-completion request; tokens
   stream back as they're generated.
7. Generated text is sentence-chunked and sent to **Piper TTS**, which synthesizes and streams
   audio incrementally.
8. Synthesized audio is published back into the LiveKit room; the caller hears the reply.
9. On call end, lead/summary data is extracted and POSTed to the FastAPI dashboard's webhook,
   which writes to **MongoDB Atlas**.
10. Full call audio is archived to **Cloudflare R2**; the dashboard stores/serves the R2 URL, not
    the audio itself.

**Outbound calls** follow the same STT/LLM/TTS path, starting from a built-in greeting instead of
a caller utterance, and originate via the PTCL/LiveKit outbound SIP path into a fresh room.

---

## 4. Component Reference

### 4.1 Telephony — PTCL SIP Trunk

| Property | Detail |
|---|---|
| Role | Inbound/outbound PSTN ingress for Pakistani (+92) numbers |
| Protocol | SIP over TLS, media over SRTP |
| Pricing | Quote-based, ~$35/month estimate pending formal PTCL quote |
| Alternative comparison | DIDWW, DIDLogic, or Nayatel |

### 4.2 Voice Orchestration — LiveKit Cloud

| Property | Detail |
|---|---|
| Role | WebRTC SFU + SIP bridging + agent dispatch + room lifecycle |
| Plan | Ship ($50/month) — 5,000 agent-session minutes + 150,000 WebRTC minutes included |
| Open risk | Telephony/PSTN-leg minutes may meter separately from included agent-session minutes — confirm against live usage dashboard |

### 4.3 Speech-to-Text — Deepgram Nova-3

| Property | Detail |
|---|---|
| Role | Real-time streaming Urdu transcription |
| Pricing | $0.0077/min → **$38.50/month** at 5,000 min/month |
| Model variant | Monolingual (Urdu) |

### 4.4 App Server — Railway (Consolidated)

Single Railway service running:

**a) Voice Agent Loop** (LiveKit Agents SDK) — orchestrates STT → LLM → TTS per turn, calls the
GROQ API client for generation.

**b) FastAPI Dashboard** — receives call-summary webhooks, serves the lead/call dashboard UI
(numbers, duration, call summary, contact details, follow-up status), talks to MongoDB Atlas.

**c) Piper TTS** — local, CPU-based synthesis (`ur_PK-fasih-medium` voice), emits audio
incrementally rather than buffering the full utterance. CPU-bound and shared with the
dashboard/agent process — 2–3 concurrent calls can saturate CPU; requires a compute-optimized tier
(4+ vCPUs) and active monitoring.

**d) RAG (in-process, no vector DB)** — knowledge base is a single JSON file (<20KB). Correct
implementation is a **filtered lookup**, retrieving only the relevant chunk (<500 tokens) per
turn — full-file injection would add ~4,000–5,000 tokens to every turn and should not be used.

| Property | Detail |
|---|---|
| Plan | Railway Pro, ~$30–40/month |

### 4.5 LLM Inference — GROQ Cloud API

| Property | Detail |
|---|---|
| Role | Turn-by-turn response generation, grounded by RAG + fixed system prompt |
| Model | Qwen3-family model on Groq (confirm exact hosted SKU against Groq's live catalog before build) |
| Pricing (verify before build) | ~$0.29/M input tokens, ~$0.59/M output tokens |
| Mode | Streaming chat completions over HTTPS |
| System prompt | One fixed prompt shared by inbound and outbound flows (hard constraint) — describes the business, services, and tone; instructs the agent to inform and respectfully persuade the caller, and to hand off follow-up to the human team |
| History | Bounded to last ~6 messages + compact state summary — not sent in full |
| Output length | Target ~120 tokens per turn, stop on first complete sentence pair |
| Rate limits | Production traffic requires a paid/on-demand Groq tier — confirm RPM/TPM ceilings against expected peak concurrent calls |
| Data handling | Transcripts and RAG chunks are sent to Groq's API — review data-retention/training-use terms before routing real customer calls |

### 4.6 Database — MongoDB Atlas

| Property | Detail |
|---|---|
| Role | Call metadata, extracted leads, dashboard data |
| Tier | Free (M0) or low-tier shared cluster (M10) |
| Cost | $0–$9/month |
| Stored per call | Phone number, timestamp, duration, call summary, contact details for follow-up, pickup status, whether a human follow-up is required |

### 4.7 Call Recording Archive — Cloudflare R2

| Property | Detail |
|---|---|
| Role | Full-call audio storage (WAV/MP3), referenced by URL from the dashboard |
| Cost | $0.50–$1/month at ~30GB/month |
| Access pattern | Recording/transcript is only surfaced on the dashboard when a specific call is clicked open — not shown in the default call list view |

### 4.8 Dashboard

Displays, at a glance: total calls made, leads generated, calls picked up, and calls flagged for
human follow-up. Clicking into a specific call reveals full detail: number, duration, summary,
extracted contact info, and (if enabled) the recording/transcript.

---

## 5. System Prompt & RAG Design Notes

- **One system prompt, two call directions.** The same prompt governs both inbound and outbound
  calls; only the opening turn differs (outbound starts with a built-in greeting, inbound starts
  by listening).
- **RAG is a filtered lookup, not a vector search.** The knowledge base is small (<20KB JSON), so
  a keyword/rule-based filter pulling the relevant chunk (<500 tokens) is sufficient — no
  embeddings or vector database needed.
- **The prompt carries all the customization work.** Since the API model isn't fine-tuned, tone,
  business-specific phrasing, and objection-handling style must be written directly into the
  system prompt and reinforced with the RAG chunks, rather than learned in model weights.
- **Keep turns short.** Target ~120 output tokens per reply, stopping at the first complete
  sentence pair — this keeps both latency and per-token cost predictable.

---

## 6. Monthly Cost Summary

*(5,000 active call minutes/month basis)*

| Component | Monthly Cost (USD) |
|---|---|
| Core app server (Railway) | $30 – $40 |
| Database (MongoDB Atlas) | $0 – $9 |
| LLM inference (GROQ API) | $3 – $25 |
| Voice orchestration (LiveKit Ship) | $50 |
| Speech-to-text (Deepgram Nova-3) | $38.50 |
| Text-to-speech (Piper, local) | $0 |
| Call recording storage (Cloudflare R2) | $0.50 – $1 |
| Telephony (PTCL SIP, estimate) | $35 |
| **Total** | **$157 – $198.50** |
| + LiveKit telephony contingency | +$0 – $50 |
| **Total with contingency** | **$157 – $248.50** |

**LLM cost assumptions:** ~10,000 turns/month (5,000 min at ~2 turns/min), ~900 input tokens/turn
(system prompt + RAG chunk + bounded history + user utterance), ~120 output tokens/turn, at
~$0.29/M input and ~$0.59/M output. The upper end of the range ($25) adds margin for longer calls,
retries, and pricing-tier confirmation.

---

## 7. Pre-Production Checklist

- [ ] Confirm the exact Groq-hosted model SKU and re-price §6 if it differs from the assumed rate
- [ ] Move to a production/paid Groq tier sized for expected peak concurrent calls; confirm
      RPM/TPM ceilings
- [ ] Implement the RAG filtered-lookup (not full-file injection) and verify token size per turn
- [ ] Bound conversation history to last ~6 messages + compact state summary
- [ ] Set output target to ~120 tokens, stop on first complete sentence pair
- [ ] Prewarm Piper per worker rather than per call
- [ ] Load-test Piper concurrency ceiling on the target Railway compute tier
- [ ] Review Groq's data-retention/training-use terms before routing real customer transcripts
- [ ] Confirm PTCL SIP trunk pricing/paperwork lead time
- [ ] Confirm LiveKit telephony-leg metering against the live usage dashboard
- [ ] Verify the dashboard only surfaces recording/transcript on a per-call click-through, not in
      the default list view

---

## 8. Open Items Pending Vendor/Ops Confirmation

| Item | Why it's open | Action needed |
|---|---|---|
| Exact Groq model SKU | Groq's public catalog naming may not match the originally planned model size | Check Groq's live model list at build time |
| PTCL SIP trunk pricing | Not publicly published, quote-based | Request formal PTCL business quote |
| LiveKit telephony billing | Unclear if PSTN legs meter separately from agent-session minutes | Verify against live usage dashboard; $50/month contingency budgeted until confirmed |
| Piper concurrency ceiling | Exact simultaneous-call limit before CPU saturation is unmeasured | Load-test before go-live |
| Groq production rate limits | Free tier is prototyping-only | Confirm paid-tier RPM/TPM limits against peak concurrency |
