"""Local Piper TTS adapter with incremental audio emission and timings."""
import asyncio
import time
import logging

from livekit.agents import tts
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS, APIConnectOptions
from piper import PiperVoice


logger = logging.getLogger("voice-agent.tts")


class PiperTTS(tts.TTS):
    def __init__(self, model_path: str, config_path: str | None = None) -> None:
        started = time.perf_counter()
        self._voice = PiperVoice.load(model_path, config_path=config_path)
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(f"Piper TTS model loaded in {elapsed_ms:.2f}ms: {model_path}")

        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=self._voice.config.sample_rate,
            num_channels=1
        )

    def synthesize(self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS) -> tts.ChunkedStream:
        return PiperChunkedStream(tts=self, input_text=text, conn_options=conn_options)


class PiperChunkedStream(tts.ChunkedStream):
    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        voice: PiperVoice = self._tts._voice  # type: ignore[attr-defined]
        text = self.input_text
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[bytes | BaseException | None] = asyncio.Queue()

        def generate() -> None:
            try:
                for chunk in voice.synthesize(text):
                    loop.call_soon_threadsafe(queue.put_nowait, chunk.audio_int16_bytes)
            except BaseException as exc:
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        started = time.perf_counter()
        output_emitter.initialize(
            request_id=str(id(self)),
            sample_rate=voice.config.sample_rate,
            num_channels=1,
            mime_type="audio/pcm"
        )
        producer = asyncio.create_task(asyncio.to_thread(generate))
        chunks = 0

        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, BaseException):
                raise tts.APIConnectionError() from item

            if chunks == 0:
                elapsed_ms = (time.perf_counter() - started) * 1000
                logger.debug(f"TTS first audio ready in {elapsed_ms:.2f}ms for {len(text)} chars")

            # Pass raw PCM16 bytes directly to output_emitter
            # Do NOT wrap in rtc.AudioFrame when mime_type="audio/pcm" is set
            output_emitter.push(item)
            chunks += 1

        await producer
        output_emitter.flush()
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.debug(f"TTS synthesis complete in {elapsed_ms:.2f}ms: {len(text)} chars, {chunks} chunks")