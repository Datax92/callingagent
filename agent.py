"""
Voice Agent for Urdu Voicebot - GROQ API (via openai-compatible plugin) + RAG + Fixed System Prompt
Rebuilt with:
  - Automated LiveKit caller ID capture
  - Async JSON-enforced AI extraction for Business Name and Urdu transcript summarization
  - Text-Triggered Automatic Session Termination (No Function Calling SDK Issues)
"""
import os
import re
import time
from typing import Optional

import asyncio
import logging
import json
import urllib.request
from dotenv import load_dotenv

from openai import AsyncOpenAI
from livekit import rtc
from livekit import api as lk_api
from livekit.agents import (
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    AutoSubscribe,
    Agent,
    AgentSession,
    ChatContext,
    ChatMessage,
)
from livekit.plugins import deepgram, openai
from piper_tts import PiperTTS
from rag_utils import RAGUtils

# 1. Environment and Logging Setup
load_dotenv(".env.local")
logging.basicConfig(level=logging.WARNING)

logger = logging.getLogger("voice-agent")
logger.setLevel(logging.INFO)

for noisy_logger in ["livekit", "livekit.agents", "piper.voice", "asyncio", "urllib3"]:
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)

# 2. Configuration
DASHBOARD_WEBHOOK_URL = os.getenv("DASHBOARD_WEBHOOK_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.getenv("GROQ_MODEL")

PIPER_MODEL_PATH = os.getenv("PIPER_MODEL_PATH")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")
SIP_OUTBOUND_TRUNK_ID = os.getenv("SIP_OUTBOUND_TRUNK_ID")


# --------------------------------------------------------------------------
# UPDATED SYSTEM PROMPT — Outbound lead-generation calls
# --------------------------------------------------------------------------
SYSTEM_PROMPT_APPROACHABLE = """آپ ڈیٹا ایکس ٹیکنالوجیز کی طرف سے آؤٹ باؤنڈ کال کر رہے ہیں۔ آپ کا کردار ایک ایسے سیلز نمائندے کا ہے جسے سیلز اینڈ مارکیٹنگ میں 5 سال سے زیادہ کا تجربہ ہے — یعنی آپ کو معلوم ہے کہ کسی کو مصنوعی طور پر متاثر کیے بغیر، حقیقی دلچسپی کیسے پیدا کی جاتی ہے، اور اعتراض کو کیسے سنبھالا جاتا ہے۔ مقصد صرف معلومات دینا نہیں بلکہ گاہک کو یہ سمجھانا ہے کہ ہماری سروس (ویب سائٹ، موبائل ایپ، کسٹم سافٹ ویئر، بزنس آٹومیشن) ان کے کاروبار کے لیے حقیقی فائدہ رکھتی ہے، اور دلچسپی رکھنے والے گاہک (lead) کو پہچاننا ہے۔

=====================================================
سخت ترین اصول: فون نمبر اور ای میل نہ پوچھیں
=====================================================
1. گاہک کا فون نمبر ہمارے سسٹم (LiveKit Cloud) نے پہلے ہی خودکار طریقے سے ریکارڈ کر لیا ہے۔ گاہک سے فون نمبر، واٹس ایپ نمبر، یا ای میل بالکل نہ پوچھیں۔
2. آپ کا کام صرف اور صرف مندرجہ ذیل معلومات حاصل کرنا ہے (اگر آسانی سے مل جائیں، زبردستی نہیں):
   - کاروبار کا نام (Business Name)
   - کاروبار کی نوعیت یا شعبہ (Business Type / Industry)
   - گاہک کی بنیادی ضرورت یا دلچسپی (کس چیز میں انٹرسٹڈ ہیں — ویب سائٹ، ایپ، آٹومیشن وغیرہ)
   - رابطہ کا موزوں وقت (یہ سوال **صرف اور صرف** اس وقت پوچھیں جب گاہک کسی سروس میں واضح دلچسپی ظاہر کرے۔ انکار کی صورت میں یہ ہرگز نہ پوچھیں)

   =====================================================
لہجہ اور بات کرنے کا انداز — یہ سب سے اہم حصہ ہے
=====================================================
• عام انسان کی طرح بات کریں، جیسے کوئی حقیقی سیلز پرسن فون پر بات کرتا ہے — بالکل نیچرل، سیدھی سادی، روزمرہ کی زبان۔
• بہت زیادہ رسمی، تقریری، یا نصیحت بھرا انداز بالکل نہ اپنائیں۔ سادہ اور سیدھی بات کریں۔
• خوشامد یا حد سے زیادہ تعریف نہ کریں۔ مثلاً اگر گاہک کہے "مجھے ویب سائٹ بنوانی ہے" تو "واہ بہت خوشی ہوئی!" جیسے زائد جوش والے فقرے استعمال نہ کریں۔ بس نارمل، پرسکون انداز میں آگے بڑھیں۔
• بدتمیز، سرد مہر یا بدلحاظ بھی بالکل نہ ہوں۔ لہجہ دوستانہ اور مددگار رہے۔
• ہر جواب چھوٹا اور بامعنی رکھیں — زیادہ سے زیادہ ایک یا دو مختصر جملے۔ لمبی تقریر یا وضاحتیں نہ دیں۔ ایک وقت میں صرف ایک بات یا سوال۔
• اگر گاہک گفتگو کے دوران اپنی ہی پچھلی بات کی تردید کرے (مثلاً پہلے کہے ویب سائٹ نہیں ہے اور پھر کہے کہ ہے)، تو لمبی صفائی دیے بغیر ایک مختصر فطری جملے سے بات تسلیم کریں (مثلاً: 'اوچھا صحیح، یعنی ویب سائٹ موجود ہے!') اور پھر اگلا سوال پوچھیں۔
• گرامر اور جنس (masculine/feminine) کا خیال رکھیں — مثلاً "کال کی ہے" کہیں، "کال کیا ہے" نہیں۔
• صرف اردو زبان استعمال کریں۔

=====================================================
سوالات کی رفتار — یہ ایک دوستانہ گفتگو ہے، تفتیش نہیں
=====================================================
• ایک وقت میں صرف ایک سوال پوچھیں، اور گاہک کے مکمل جواب کا انتظار کریں۔
• اگلا سوال پوچھنے سے پہلے، گاہک نے جو بات بتائی اس پر ایک مختصر اور خاص (specific) ردعمل دیں — صرف "ٹھیک ہے" یا "اچھا" دہرانے کی بجائے ان کی بتائی گئی بات کا حوالہ دیں۔
• گاہک کے موجودہ ڈیجیٹل سسٹم پر تفتیشی سوالات ہرگز نہ کریں — ہم آڈٹ نہیں کر رہے، صرف کاروبار کی نوعیت جان کر ایک متعلقہ فائدہ بتانا ہے۔

=====================================================
قائل کرنے کا انداز (Persuasion) — ماہر سیلز پرسن کی طرح
=====================================================
• عام فیچرز کی فہرست نہ گنوائیں — اس کے بجائے گاہک کے بتائے گئے کاروبار سے جوڑ کر ایک مخصوص فائدہ بتائیں۔
• صرف وہی فائدے بیان کریں جو حقیقی اور معقول ہوں (جیسے زیادہ گاہک تک رسائی، وقت کی بچت، آن لائن موجودگی)۔
• اگر گاہک پہلی بار "ضرورت نہیں" یا بے دلچسپی کا اظہار کرے، تو فوراً ہار نہ مانیں — ایک مرتبہ حقیقی فائدے پر مبنی مختصر سوال پوچھیں تاکہ اصل وجہ سمجھ سکیں۔ یہ صرف ایک بار کریں، بار بار اصرار یا زبردستی بالکل نہ کریں۔

=====================================================
حقائق کی پابندی (Grounding) — یہ ہر وقت لاگو ہوتا ہے
=====================================================
• صرف وہی بات بطور حقیقت (Data X Technologies fact) بیان کریں جو "Reference information" میں واضح طور پر موجود ہو۔
• قیمت، ابتدائی قیمت، ڈسکاؤنٹ، قسطیں، پروجیکٹ کا دورانیہ، گارنٹی، یا پرانے کلائنٹس — یہ سب کبھی خود سے نہ بتائیں۔

=====================================================
گفتگو کے مراحل اور کال ختم کرنے کی ہدایت (CRITICAL TRIGGER)
=====================================================
1. مختصر تعارف اور سروسز: ڈیٹا ایکس ٹیکنالوجیز کی طرف سے تعارف کرائیں اور فوراً کسٹم سافٹ ویئر، ویب سائٹ، ایپس، اور آٹومیشن کی سروسز بتاتے ہوئے کاروبار معلوم کریں۔
2. کاروبار معلوم کریں اور اسی سے جڑا مخصوص فائدہ بتائیں — عمومی فیچر لسٹ نہ دہرائیں۔
3. اگر گاہک دلچسپی ظاہر نہ کرے یا کہے کہ اسے ضرورت نہیں ہے: ہرگز رابطہ کرنے یا کال بیک کا وقت نہ پوچھیں! بس ایک مرتبہ مختصر سوال پوچھ کر اصل وجہ جاننے کی کوشش کریں (مثلاً "کیا فی الحال ضرورت نہیں ہے؟")۔
4. اگر گاہک دوسری بار بھی منع کرے یا ناراضگی ظاہر کرے: فوراً معذرت اور شائستگی سے شکریہ ادا کریں، اور اپنے آخری جملے میں "خدا حافظ" کہہ کر گفتگو ختم کر دیں۔ (یہ لفظ کال کاٹنے کا سگنل ہے)۔
5. اگر گاہک دلچسپی ظاہر کرے: صرف اسی صورت میں رابطہ کرنے کا مناسب وقت پوچھیں اور پھر شکریہ ادا کر کے "خدا حافظ" کہیں۔

=====================================================
حوالہ جاتی معلومات (Reference Information) کا استعمال
=====================================================
• اگر گفتگو میں کہیں "Reference information" کے عنوان سے اضافی معلومات فراہم کی جائیں تو انہیں گاہک کے سوال کا درست جواب دینے کے لیے استعمال کریں۔
• یہ معلومات لفظ بہ لفظ نہ دہرائیں — انہیں اپنے فطری، گفتگو والے انداز میں مختصر جواب کا حصہ بنائیں۔"""

RUNTIME_SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "").strip() or SYSTEM_PROMPT_APPROACHABLE

GREETING_LINE = (
    "السلام علیکم! میں ڈیٹا ایکس ٹیکنالوجیز کی طرف سے بات کر رہا ہوں۔ ہم کسٹم سافٹ ویئر، ویب سائٹ، موبائل ایپس اور بزنس آٹومیشن کی سروسز فراہم کرتے ہیں۔ کیا میں جان سکتا ہوں کہ آپ کا کاروبار کس نوعیت کا ہے؟"
)

FAILED_LEADS_FALLBACK_PATH = os.getenv("FAILED_LEADS_FALLBACK_PATH", "failed_leads.jsonl")


class CallState:
    """Mutable per-call state shared with the session via userdata."""
    def __init__(self) -> None:
        self.caller_number: str = "unknown"
        self.call_direction: str = "inbound"
        self.room_name: str = ""
        self.business_name: Optional[str] = None
        self.business_details: Optional[str] = None
        self.notes: str = ""
        self.last_rag_message_id: Optional[str] = None
        self.transcript_lines: list[str] = []
        self.lead_pushed: bool = False
        self.call_start_time: float = time.time()
        self.call_end_time: Optional[float] = None
        self.recording_url: Optional[str] = None
        self.call_duration: Optional[float] = None
        
        # Keep track of the active chat context to monitor bot responses
        self.chat_ctx: Optional[ChatContext] = None


def extract_caller_number(participant: rtc.RemoteParticipant | None) -> str:
    """Extracts the caller phone number, strictly stripping whitespace."""
    if participant is None:
        return "Unknown Participant"
    
    if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
        phone = participant.attributes.get("sip.phoneNumber", "")
        if phone and phone.strip():
            return phone.strip()
        if participant.identity and participant.identity.strip():
            return participant.identity.strip()
        return "Unknown SIP"
    
    identity = participant.identity or ""
    return identity.strip() if identity.strip() else "Web/Local Participant"


def _post_json(url: str, payload: dict) -> None:
    """Blocking HTTP POST, run off the event loop."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()


async def _call_groq_json(client: AsyncOpenAI, prompt: str, force_json_mode: bool) -> str:
    """Single Groq call, optionally forcing json_object response mode."""
    kwargs = {}
    if force_json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = await client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": "You are a strict data extraction AI. You output ONLY raw, valid JSON. You do not speak conversationally."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1,
        **kwargs,
    )
    return (response.choices[0].message.content or "").strip()


async def _extract_call_data_via_llm(transcript_lines: list[str]) -> dict:
    """Uses Groq LLM to extract the business name and generate an Urdu summary cleanly via JSON."""
    if not transcript_lines:
        return {"business_name": "", "summary": "کال کا کوئی ترانسکرپٹ موجود نہیں ہے۔"}

    full_transcript = "\n".join(transcript_lines)

    prompt = f"""Analyze the following Urdu call transcript. Extract the business name and write a concise 2-3 sentence summary in Urdu.

CRITICAL INSTRUCTIONS:
1. You MUST respond ONLY with a valid JSON object.
2. Do NOT write any English text, preamble, or chain-of-thought like "Here is the summary" or "Let me read this". 
3. The "summary" field MUST be in pure Urdu.
4. If the transcript is too short, garbled, or lacks enough information, still return a valid JSON object with your best-effort "business_name" (empty string if unknown) and a short "summary" describing what little is known.

Transcript:
{full_transcript}"""

    client = AsyncOpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)

    raw_response = ""
    for force_json_mode in (True, False):
        try:
            raw_response = await _call_groq_json(client, prompt, force_json_mode)
            if raw_response:
                break
        except Exception as e:
            logger.error(f"Groq call failed (force_json_mode={force_json_mode}): {e}")

    if not raw_response:
        logger.error("Groq returned no usable output after retry; falling back to raw transcript.")
        return {"business_name": "", "summary": "\n".join(transcript_lines[-4:])}

    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_response, re.DOTALL)
        if not match:
            logger.error(f"Could not locate JSON in Groq response: {raw_response[:200]!r}")
            return {"business_name": "", "summary": "\n".join(transcript_lines[-4:])}
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse extracted JSON block: {e}")
            return {"business_name": "", "summary": "\n".join(transcript_lines[-4:])}

    return {
        "business_name": data.get("business_name", ""),
        "summary": data.get("summary", "")
    }


async def _push_lead_to_dashboard(call_state: CallState) -> None:
    """Send lead data and AI transcript summary to dashboard webhook when call ends."""
    if call_state.lead_pushed:
        return

    had_conversation = bool(call_state.transcript_lines)
    if not had_conversation and call_state.call_direction != "outbound":
        logger.info("Call ended with no conversation — skipping dashboard push.")
        return

    call_state.call_end_time = time.time()
    call_state.call_duration = call_state.call_end_time - call_state.call_start_time

    logger.info("Extracting AI data from transcript...")
    ai_data = await _extract_call_data_via_llm(call_state.transcript_lines)

    final_business_name = call_state.business_name or ai_data.get("business_name", "")

    payload = {
        "caller_number": call_state.caller_number,
        "call_direction": call_state.call_direction,
        "room_name": call_state.room_name,
        "business_name": final_business_name,
        "notes": call_state.notes or "",
        "transcript_summary": ai_data.get("summary", ""),
        "recording_url": call_state.recording_url,
        "call_duration": call_state.call_duration,
    }

    for attempt in range(3):
        try:
            await asyncio.to_thread(_post_json, DASHBOARD_WEBHOOK_URL, payload)
            call_state.lead_pushed = True
            logger.info(f"Lead pushed to dashboard with AI Urdu summary (caller: {call_state.caller_number})")
            return
        except Exception as exc:
            if attempt < 2:
                await asyncio.sleep(1.5 * (attempt + 1))

    logger.error("Failed to push lead to dashboard webhook after retries.")


# --------------------------------------------------------------------------
# VOICE AGENT CLASS
# --------------------------------------------------------------------------
class SupportAgent(Agent):
    """Voice agent that handles inbound/outbound Urdu voice calls."""

    def __init__(self, rag_utils: RAGUtils, room_obj: rtc.Room) -> None:
        super().__init__(instructions=RUNTIME_SYSTEM_PROMPT)
        self._rag_utils = rag_utils

    async def on_enter(self):
        await self.session.say(GREETING_LINE)

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        user_text = getattr(new_message, "text_content", None) or ""
        if not user_text:
            return

        call_state: CallState = self.session.userdata
        # Capture the chat context so our background monitor can read LLM responses
        call_state.chat_ctx = turn_ctx
        
        call_state.transcript_lines.append(f"caller: {user_text}")

        try:
            rag_chunk = self._rag_utils.filtered_lookup(user_text)
        except Exception as e:
            logger.error(f"RAG lookup raised an exception: {e}")
            rag_chunk = None

        if call_state.last_rag_message_id:
            try:
                turn_ctx.remove(call_state.last_rag_message_id)
            except Exception:
                pass
            call_state.last_rag_message_id = None

        if rag_chunk:
            rag_message = turn_ctx.add_message(
                role="system",
                content=f"Reference information:\n{rag_chunk[:1000]}",
            )
            call_state.last_rag_message_id = rag_message.id
        else:
            logger.info("No RAG chunk for this turn.")

        turn_ctx.truncate(max_items=24)


def prewarm(proc: JobProcess):
    pass


async def entrypoint(ctx: JobContext):
    logger.info(f"📞 Connected to room: {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    call_state = CallState()

    job_metadata: dict = {}
    try:
        if ctx.job.metadata:
            job_metadata = json.loads(ctx.job.metadata)
    except Exception:
        pass

    call_direction = job_metadata.get("direction", "inbound")
    outbound_phone_number = job_metadata.get("phone_number")
    call_state.call_direction = call_direction
    call_state.room_name = ctx.room.name

    caller_number = "Unknown Participant"
    if call_direction == "outbound" and outbound_phone_number:
        caller_number = str(outbound_phone_number).strip()
    else:
        for p in ctx.room.remote_participants.values():
            if p.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
                caller_number = extract_caller_number(p)
                break
            else:
                caller_number = extract_caller_number(p)

    call_state.caller_number = caller_number

    @ctx.room.on("participant_connected")
    def _on_participant_connected(participant: rtc.RemoteParticipant):
        new_caller = extract_caller_number(participant)
        if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
            call_state.caller_number = new_caller
        elif call_state.caller_number in ["Unknown Participant", "Web/Local Participant", "Unknown SIP", "unknown", ""]:
            call_state.caller_number = new_caller

    @ctx.room.on("participant_disconnected")
    def _on_participant_disconnected(participant: rtc.RemoteParticipant):
        asyncio.create_task(_push_lead_to_dashboard(call_state))

    if call_direction == "outbound" and outbound_phone_number:
        if not all([LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, SIP_OUTBOUND_TRUNK_ID]):
            call_state.notes = "Outbound failed: missing credentials."
            await _push_lead_to_dashboard(call_state)
            return

        try:
            async with lk_api.LiveKitAPI(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET) as lkapi:
                await lkapi.sip.create_sip_participant(
                    lk_api.CreateSIPParticipantRequest(
                        sip_trunk_id=SIP_OUTBOUND_TRUNK_ID,
                        sip_call_to=outbound_phone_number,
                        room_name=ctx.room.name,
                        participant_identity=f"sip-{outbound_phone_number}",
                        participant_name=outbound_phone_number,
                        wait_until_answered=True,
                    )
                )
        except Exception as exc:
            call_state.notes = f"Outbound call failed: {exc}"
            await _push_lead_to_dashboard(call_state)
            return

    groq_llm = openai.LLM(
        api_key=GROQ_API_KEY,
        base_url=GROQ_BASE_URL,
        model=GROQ_MODEL,
        temperature=0.7,
        max_completion_tokens=300,
        extra_body={"reasoning_effort": "low"},
    )

    session = AgentSession[CallState](
        userdata=call_state,
        stt=deepgram.STT(model="nova-3", language="ur") if DEEPGRAM_API_KEY else None,
        llm=groq_llm,
        tts=PiperTTS(model_path=PIPER_MODEL_PATH),
        turn_detection="vad",
    )

    await session.start(agent=SupportAgent(RAGUtils(), room_obj=ctx.room), room=ctx.room)
# --------------------------------------------------------------------------
    # BACKGROUND MONITOR: Waits for LLM to say "خدا حافظ" and safely disconnects
    # --------------------------------------------------------------------------
    async def call_monitor():
        while ctx.room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
            await asyncio.sleep(1.5)
            if call_state.chat_ctx:
                # Safe Accessor: SDK کے ورژن کے مطابق messages کو ہینڈل کرے گا
                ctx_messages = call_state.chat_ctx.messages
                messages_list = ctx_messages() if callable(ctx_messages) else ctx_messages
                
                if messages_list:
                    last_msg = messages_list[-1]
                    
                    # Safe attribute getting to prevent any missing attribute errors
                    role_str = str(getattr(last_msg, "role", "")).lower()
                    text_content = str(getattr(last_msg, "content", ""))
                    
                    # Trigger disconnect if the agent says the termination keyword
                    if "assistant" in role_str and "خدا حافظ" in text_content:
                        logger.info("🔚 Termination phrase ('خدا حافظ') detected in AI response. Hanging up in 3.5s...")
                        await asyncio.sleep(3.5)  # Allow Piper TTS to finish speaking
                        if ctx.room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
                            try:
                                await ctx.room.disconnect()
                            except Exception as e:
                                logger.error(f"Failed to cleanly disconnect: {e}")
                        break

    # Start the monitor loop asynchronously alongside the main session
    asyncio.create_task(call_monitor())

    while ctx.room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
        await asyncio.sleep(1)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name="urdu-voicebot",
        )
    )