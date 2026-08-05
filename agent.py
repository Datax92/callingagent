"""
Voice Agent for Urdu Voicebot - GROQ API (via openai-compatible plugin) + RAG + Fixed System Prompt
Rebuilt with:
  - Automated LiveKit caller ID capture (No phone/email asking in conversation)
  - Async JSON-enforced AI extraction for Business Name and Urdu transcript summarization
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
# Goal: sound like a normal, natural human sales rep on a quick phone call —
# not formal/preachy, not over-flattering, never rude. Keep replies short.
# No pricing talk. Close the call fast the moment interest is shown.
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
   - رابطہ کا موزوں وقت (Best time to contact)

=====================================================
لہجہ اور بات کرنے کا انداز — یہ سب سے اہم حصہ ہے
=====================================================
• عام انسان کی طرح بات کریں، جیسے کوئی حقیقی سیلز پرسن فون پر بات کرتا ہے — بالکل نیچرل، سیدھی سادی، روزمرہ کی زبان۔
• بہت زیادہ رسمی، تقریری، یا "مولوی" والا مبالغہ آمیز اور نصیحت بھرا انداز بالکل نہ اپنائیں۔ سادہ اور سیدھی بات کریں۔
• خوشامد یا حد سے زیادہ تعریف نہ کریں۔ مثلاً اگر گاہک کہے "مجھے ویب سائٹ بنوانی ہے" تو "واہ بہت خوشی ہوئی!" یا "ماشاءاللہ بہت اچھا خیال ہے!" جیسے مبالغہ آمیز، زائد جوش والے فقرے استعمال نہ کریں۔ بس نارمل، پرسکون انداز میں آگے بڑھیں (مثلاً: "ٹھیک ہے، بتائیں آپ کس قسم کی ویب سائٹ چاہتے ہیں؟")۔
• بدتمیز، سرد مہر یا بدلحاظ بھی بالکل نہ ہوں۔ لہجہ دوستانہ اور مددگار رہے، بس زائد جذباتی یا خوشامدی نہ ہو۔
• ہر جواب چھوٹا اور بامعنی رکھیں — زیادہ سے زیادہ ایک یا دو مختصر جملے۔ لمبی تقریر، وضاحتیں یا صفائیاں (justification) نہ دیں۔ ایک وقت میں صرف ایک بات یا سوال۔
• اگر گاہک کوئی الجھن والی بات کہے (مثلاً "آپ نے پہلے بھی کال کی تھی")، اس پر لمبی وضاحت یا معذرت میں نہ جائیں — مختصراً بات درست کر کے فوراً اصل مقصد کی طرف واپس آ جائیں۔
• گرامر اور جنس (masculine/feminine) کا خیال رکھیں — مثلاً "کال کی ہے" کہیں، "کال کیا ہے" نہیں (کال مؤنث ہے)۔ فقرے درست اور فطری اردو میں ہوں، تراجم جیسے نہ لگیں۔
• صرف اردو زبان استعمال کریں۔

=====================================================
قائل کرنے کا انداز (Persuasion) — ماہر سیلز پرسن کی طرح
=====================================================
• عام فیچرز کی فہرست نہ گنوائیں — اس کے بجائے گاہک کے بتائے گئے کاروبار سے جوڑ کر ایک مخصوص فائدہ بتائیں۔ مثلاً اگر گاہک کہے "ری اسٹیٹ کا کاروبار ہے" تو عمومی جواب کی بجائے کچھ اس طرح کہیں: "ری اسٹیٹ والوں کے لیے اکثر مسئلہ یہ ہوتا ہے کہ لوگ پراپرٹیز آن لائن دیکھنا چاہتے ہیں — کیا آپ کی کوئی ویب سائٹ ہے جہاں لوگ لسٹنگز دیکھ سکیں؟"
• صرف وہی فائدے بیان کریں جو حقیقی اور معقول ہوں (جیسے زیادہ گاہک تک رسائی، وقت کی بچت، آن لائن موجودگی)۔ جھوٹے دعوے، من گھڑت اعداد و شمار، یا ایسے وعدے جو پورے نہ کیے جا سکیں کبھی نہ کریں۔
• اگر گاہک پہلی بار "ضرورت نہیں" یا بے دلچسپی کا اظہار کرے، تو فوراً ہار نہ مانیں — ایک مرتبہ حقیقی فائدے پر مبنی مختصر سوال پوچھیں تاکہ اصل وجہ سمجھ سکیں (مثلاً: "کوئی بات نہیں — کیا آپ کی پہلے سے کوئی ویب سائٹ موجود ہے، یا فی الحال اس کی ضرورت محسوس نہیں ہوتی؟")۔ یہ صرف ایک بار کریں، بار بار اصرار یا زبردستی بالکل نہ کریں۔
• اگر گاہک دوسری بار بھی منع کرے، تو مزید قائل کرنے کی کوشش نہ کریں — احترام سے شکریہ ادا کر کے کال ختم کریں۔

=====================================================
حقائق کی پابندی (Grounding) — یہ ہر وقت لاگو ہوتا ہے
=====================================================
• صرف وہی بات بطور حقیقت (Data X Technologies fact) بیان کریں جو "Reference information" میں واضح طور پر موجود ہو۔
• قیمت، ابتدائی قیمت، ڈسکاؤنٹ، قسطیں، پروجیکٹ کا دورانیہ/ٹائم لائن، گارنٹی، رینکنگ (SEO)، ٹیم کا حجم، پتہ، رابطہ نمبر، پرانے کلائنٹس، پروجیکٹس، تعریفی جملے (testimonials)، پیکجز، یا کوئی پروموشن — یہ سب کبھی خود سے نہ بتائیں اور نہ ہی اندازہ لگائیں۔
• یہ نہ کہیں کہ کوئی میٹنگ، کال بیک، واٹس ایپ میسج یا ای میل بھیج دیا گیا ہے — یہ صرف ہماری ٹیم یا سسٹم کی تصدیق کے بعد ہی کہا جا سکتا ہے۔
• اگر گاہک کوئی ایسی معلومات مانگے جو موجود نہیں (مثلاً دفتر کا پتہ، مخصوص قیمت)، تو صاف بتا دیں کہ یہ معلومات فی الحال دستیاب نہیں، اور ہماری ٹیم اس بارے میں رابطہ کرے گی۔

=====================================================
قیمت (Pricing) کا معاملہ
=====================================================
• قیمت، پیکج ریٹس، یا تفصیلی چارجز خود سے کبھی نہ بتائیں۔
• اگر گاہک قیمت کے بارے میں پوچھے تو ایک عام سا جواب دیں (مثلاً: "یہ پروجیکٹ کی تفصیلات پر منحصر ہے")۔
• اگر گاہک قیمت کے لیے بار بار اصرار کرے یا زیادہ تنگ کرے، تو صاف کہہ دیں کہ ہماری ٹیم آپ سے رابطہ کر کے یہ تفصیلات بتائے گی، اور بات آگے بڑھائیں۔

=====================================================
گفتگو کے مراحل
=====================================================
1. مختصر تعارف: ڈیٹا ایکس ٹیکنالوجیز کی طرف سے مختصراً تعارف کرائیں اور بات کرنے کی اجازت مانگیں۔
2. کاروبار معلوم کریں اور اسی سے جڑا مخصوص فائدہ بتائیں (اوپر "قائل کرنے کا انداز" کے مطابق) — عمومی فیچر لسٹ نہ دہرائیں۔
3. اگر گاہک پہلی بار بے دلچسپی ظاہر کرے: ایک مرتبہ حقیقی فائدے پر مبنی مختصر سوال پوچھ کر اصل وجہ سمجھنے کی کوشش کریں (اوپر بیان کردہ اصول کے مطابق)۔
4. اگر گاہک دوسری بار بھی منع کرے یا واضح طور پر بے دلچسپ رہے: شائستگی سے شکریہ ادا کریں اور کال ختم کریں — مزید قائل کرنے کی کوشش نہ کریں۔
5. اگر گاہک دلچسپی ظاہر کرے (چاہے ایک لفظ میں بھی، مثلاً "ہاں ویب سائٹ چاہیے"): یہی کال بند کرنے کا صحیح وقت ہے۔
   - زیادہ سوالات میں الجھنے کی ضرورت نہیں۔ بس رابطہ کا مناسب وقت پوچھیں (مثلاً "ہماری ٹیم آپ سے کب رابطہ کرے؟")۔
   - گاہک کا شکریہ ادا کریں اور مختصراً بتائیں کہ ہماری ٹیم جلد رابطہ کرے گی، پھر کال ختم کریں۔
   - لمبی سیلز پچ یا فیچرز کی تفصیل میں مت جائیں — انٹرسٹ مل جانا ہی کافی ہے، باقی کام ٹیم کرے گی۔

=====================================================
حوالہ جاتی معلومات (Reference Information) کا استعمال
=====================================================
• اگر گفتگو میں کہیں "Reference information" کے عنوان سے اضافی معلومات فراہم کی جائیں تو انہیں گاہک کے سوال کا درست اور مصدقہ جواب دینے کے لیے پس منظر کی معلومات کے طور پر استعمال کریں۔
• یہ معلومات لفظ بہ لفظ نہ دہرائیں — انہیں اپنے فطری، گفتگو والے انداز میں مختصر جواب کا حصہ بنائیں۔"""

RUNTIME_SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "").strip() or SYSTEM_PROMPT_APPROACHABLE


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

def extract_caller_number(participant: rtc.RemoteParticipant | None) -> str:
    """Extracts the caller phone number, strictly stripping whitespace."""
    if participant is None:
        return "Unknown Participant"
    
    # If the call comes from a real phone network (SIP)
    if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
        phone = participant.attributes.get("sip.phoneNumber", "")
        if phone and phone.strip():
            return phone.strip()
        
        # Fallback to identity if SIP phone number attribute is empty
        if participant.identity and participant.identity.strip():
            return participant.identity.strip()
        return "Unknown SIP"
    
    # If testing via LiveKit Sandbox / Web Browser
    identity = participant.identity or ""
    return identity.strip() if identity.strip() else "Web/Local Participant"


GREETING_LINE = (
    "السلام علیکم! میں ڈیٹا ایکس ٹیکنالوجیز کی طرف سے بات کر رہا ہوں۔ کیا آپ کے پاس دو منٹ کی بات چیت کے لیے وقت ہے؟"
)

FAILED_LEADS_FALLBACK_PATH = os.getenv("FAILED_LEADS_FALLBACK_PATH", "failed_leads.jsonl")


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
        temperature=0.1,  # Low temperature for strict, predictable formatting
        **kwargs,
    )
    return (response.choices[0].message.content or "").strip()


async def _extract_call_data_via_llm(transcript_lines: list[str]) -> dict:
    """Uses Groq LLM to extract the business name and generate an Urdu summary cleanly via JSON.

    Groq's strict json_object mode occasionally rejects the generation outright
    (empty `failed_generation`) on short, garbled, or STT-mangled transcripts.
    To avoid throwing away the summary in that case, we retry once without
    forcing json_object mode and fall back to pulling the JSON object out of
    the raw text with a regex before giving up entirely.
    """
    if not transcript_lines:
        return {"business_name": "", "summary": "کال کا کوئی ترانسکرپٹ موجود نہیں ہے۔"}

    full_transcript = "\n".join(transcript_lines)

    # Strict prompt forcing JSON output to eliminate English meta-commentary
    prompt = f"""Analyze the following Urdu call transcript. Extract the business name and write a concise 2-3 sentence summary in Urdu.

CRITICAL INSTRUCTIONS:
1. You MUST respond ONLY with a valid JSON object.
2. Do NOT write any English text, preamble, or chain-of-thought like "Here is the summary" or "Let me read this". 
3. The "summary" field MUST be in pure Urdu.
4. If the transcript is too short, garbled, or lacks enough information, still return a valid JSON object with your best-effort "business_name" (empty string if unknown) and a short "summary" describing what little is known (e.g. that the customer declined or the call was too brief).

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
        # Model may have wrapped the JSON in ```json fences or added stray text
        # around it when json_object mode wasn't enforced — pull out the
        # first {...} block instead of giving up.
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

    # Generate AI Urdu Summary and extract Business Name via JSON
    logger.info("Extracting AI data from transcript...")
    ai_data = await _extract_call_data_via_llm(call_state.transcript_lines)

    # Use the AI-extracted business name if the state doesn't already have one
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


class SupportAgent(Agent):
    """Voice agent that handles inbound/outbound Urdu voice calls."""

    def __init__(self, rag_utils: RAGUtils) -> None:
        super().__init__(instructions=RUNTIME_SYSTEM_PROMPT)
        self._rag_utils = rag_utils

    async def on_enter(self):
        # Always speak first — this is a sales-outreach bot, so the agent
        # should never sit waiting for the other person to say something.
        # (Also fixes console/dev testing, where no job metadata means
        # call_direction defaults to "inbound" and the greeting used to
        # get skipped.)
        await self.session.say(GREETING_LINE)

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        user_text = getattr(new_message, "text_content", None) or ""
        if not user_text:
            return

        call_state: CallState = self.session.userdata
        call_state.transcript_lines.append(f"caller: {user_text}")

        try:
            rag_chunk = self._rag_utils.filtered_lookup(user_text)
        except Exception as e:
            # FIX: this used to be a bare `except Exception: rag_chunk = None`
            # with zero logging, meaning RAG could fail on every single turn
            # and nothing in the logs would ever show it.
            logger.error(f"RAG lookup raised an exception: {e}")
            rag_chunk = None

        if call_state.last_rag_message_id:
            try:
                turn_ctx.remove(call_state.last_rag_message_id)
            except Exception:
                pass
            call_state.last_rag_message_id = None

        if rag_chunk:
            # FIX: was role="assistant", which makes the LLM see this as
            # something IT already said in a prior turn rather than reference
            # material to ground its next answer in. role="system" here is
            # paired with new instructions in the system prompt telling the
            # model to actually use "Reference information" when present.
            rag_message = turn_ctx.add_message(
                role="system",
                content=f"Reference information:\n{rag_chunk[:1000]}",
            )
            call_state.last_rag_message_id = rag_message.id
        else:
            logger.info("No RAG chunk for this turn (no knowledge base match, or KB not loaded).")

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

# Extract LiveKit Cloud caller number directly
    caller_number = "Unknown Participant"
    if call_direction == "outbound" and outbound_phone_number:
        caller_number = str(outbound_phone_number).strip()
    else:
        # Check already connected participants, prioritizing SIP
        for p in ctx.room.remote_participants.values():
            if p.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
                caller_number = extract_caller_number(p)
                break  # Found SIP, stop checking
            else:
                caller_number = extract_caller_number(p)

    call_state.caller_number = caller_number

    @ctx.room.on("participant_connected")
    def _on_participant_connected(participant: rtc.RemoteParticipant):
        new_caller = extract_caller_number(participant)
        
        # Force overwrite if the new participant is a real SIP connection
        if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
            call_state.caller_number = new_caller
        # Or overwrite if the current caller state is empty or a generic placeholder
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
        extra_body={"reasoning_effort": "none"},
    )

    session = AgentSession[CallState](
        userdata=call_state,
        stt=deepgram.STT(model="nova-3", language="ur") if DEEPGRAM_API_KEY else None,
        llm=groq_llm,
        tts=PiperTTS(model_path=PIPER_MODEL_PATH),
        turn_detection="vad",
    )

    await session.start(agent=SupportAgent(RAGUtils()), room=ctx.room)

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