"""Speech-to-text on Gemini, using only a Google AI (Gemini) API key.

Pipecat's built-in ``GoogleSTTService`` is Google Cloud Speech-to-Text, which
needs a GCP project and service-account credentials. This service instead sends
each finished utterance (as WAV, segmented for us by ``SegmentedSTTService`` from
the VAD start/stop frames) to a Gemini model with a strict "transcribe verbatim"
instruction — the same API key that runs the reasoning model.

Trade-off: it is utterance-level, not streaming (~1s after the person stops).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from google import genai
from google.genai import types
from loguru import logger
from pipecat.frames.frames import ErrorFrame, Frame, TranscriptionFrame
from pipecat.services.settings import STTSettings
from pipecat.services.stt_service import SegmentedSTTService
from pipecat.utils.time import time_now_iso8601

TRANSCRIBE_PROMPT = (
    "Transcribe the speech in this audio exactly as spoken, verbatim, in the language "
    "spoken (keep Hindi/Hinglish as is). Output ONLY the transcript text — no quotes, "
    "no labels, no commentary. If the audio is silence, noise, breathing, music or not "
    "intelligible speech, output exactly: [no speech]. Never guess or invent words."
)

# Below this the clip cannot contain a word; skipping it avoids the model inventing
# one from a breath or a click (16 kHz, 16-bit mono => 32,000 bytes per second).
MIN_SEGMENT_BYTES = 44 + int(16000 * 2 * 0.35)

# Answers the model sometimes gives instead of an empty transcript.
_NON_SPEECH = {"", "[no speech]", "(no speech)", "no speech", "[silence]", "(silence)", "silence", "..."}


class GeminiSTTService(SegmentedSTTService):
    def __init__(self, *, api_key: str, model: str = "gemini-3.5-flash-lite", **kwargs) -> None:
        # Pipecat expects every STT settings field initialised (None = unsupported).
        super().__init__(settings=STTSettings(model=model, language=None), **kwargs)
        if not api_key:
            raise ValueError("GEMINI_API_KEY is empty: set it in .env (LLM_PROVIDER=gemini needs it)")
        self._model = model
        self._client = genai.Client(api_key=api_key)

    def can_generate_metrics(self) -> bool:
        return True

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:
        if len(audio) < MIN_SEGMENT_BYTES:
            logger.debug("GeminiSTTService: segment too short ({} bytes), skipping", len(audio))
            yield None
            return
        await self.start_processing_metrics()
        await self.start_ttfb_metrics()
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(text=TRANSCRIBE_PROMPT),
                            types.Part.from_bytes(data=audio, mime_type="audio/wav"),
                        ],
                    )
                ],
                config=types.GenerateContentConfig(temperature=0, max_output_tokens=256),
            )
            await self.stop_ttfb_metrics()
            text = (response.text or "").strip()
            if text.strip("\"'` ").lower() in _NON_SPEECH:
                logger.debug("GeminiSTTService: no speech in segment")
                yield None
                return
            logger.debug("GeminiSTTService transcript: {!r}", text)
            yield TranscriptionFrame(text, "", time_now_iso8601())
        except Exception as exc:  # network / quota / safety — never kill the pipeline
            logger.error("GeminiSTTService error: {}", exc)
            yield ErrorFrame(f"Gemini STT error: {exc}")
        finally:
            await self.stop_processing_metrics()
