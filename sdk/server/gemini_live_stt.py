"""Streaming speech-to-text on Gemini's Live API (``gemini-3.5-transcribe-live``).

Why this exists: ``GeminiSTTService`` (gemini_stt.py) waits for the person to
finish, then makes ONE generateContent call with the whole utterance - measured
at ~3.0s from "stopped talking" to transcript. The Live API instead takes the
audio WHILE the person talks, so at the end there is almost nothing left to do.

Measured with a 3.8s clip (probe, 2026-09-02):
  - Gemini's own turn detection:  transcript 1.54s after the clip ended
  - our VAD closing the activity: transcript 0.30s after the clip ended  <- used

So automatic activity detection is DISABLED and our Silero VAD (already in the
pipeline) drives it: VADUserStartedSpeaking -> ``activity_start`` (+ a short
pre-roll so the first word isn't clipped), audio streams live during speech,
VADUserStoppedSpeaking -> ``activity_end``. Gemini answers with
``input_transcription`` pieces and ``generation_complete``; the transcript is
emitted once, on that completion.

The transcribe-live model is transcription-only: it is asked for TEXT output and
returns none of its own, so the only tokens billed are the transcript.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncGenerator
from typing import Any

from google import genai
from google.genai import types
from loguru import logger
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    ErrorFrame,
    Frame,
    StartFrame,
    TranscriptionFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.settings import STTSettings
from pipecat.services.stt_service import STTService
from pipecat.utils.time import time_now_iso8601

DEFAULT_LIVE_STT_MODEL = "gemini-3.5-transcribe-live"
RECONNECT_DELAY_SEC = 1.0


class GeminiLiveSTTService(STTService):
    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_LIVE_STT_MODEL,
        preroll_ms: int = 400,
        **kwargs: Any,
    ) -> None:
        # Measured speech-end -> transcript is ~0.3s; tell Pipecat's turn logic so
        # it does not wait longer than that for us.
        kwargs.setdefault("ttfs_p99_latency", 0.6)
        super().__init__(settings=STTSettings(model=model, language=None), **kwargs)
        if not api_key:
            raise ValueError("GEMINI_API_KEY is empty: set it in .env (Gemini speech-to-text needs it)")
        self._model = model
        self._client = genai.Client(api_key=api_key)
        self._preroll_ms = preroll_ms
        self._preroll: deque[bytes] = deque()
        self._preroll_bytes = 0
        self._session: Any = None
        self._connection_task: asyncio.Task | None = None
        self._in_activity = False
        self._pending_text: list[str] = []

    def can_generate_metrics(self) -> bool:
        return True

    # ------------------------------------------------------------------ lifecycle
    async def start(self, frame: StartFrame) -> None:
        await super().start(frame)
        self._connection_task = self.create_task(self._connection_handler(), f"{self}::live")

    async def stop(self, frame: EndFrame) -> None:
        await super().stop(frame)
        await self._disconnect()

    async def cancel(self, frame: CancelFrame) -> None:
        await super().cancel(frame)
        await self._disconnect()

    async def _disconnect(self) -> None:
        if self._connection_task:
            await self.cancel_task(self._connection_task)
            self._connection_task = None
        self._attach_session(None)

    def _attach_session(self, session: Any) -> None:
        self._session = session
        self._in_activity = False
        self._pending_text.clear()

    async def _connection_handler(self) -> None:
        """One Live session at a time; reconnects after any drop (sessions have a
        maximum duration, and the server may send goAway)."""
        config = types.LiveConnectConfig(
            response_modalities=[types.Modality.TEXT],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(disabled=True),
            ),
        )
        while True:
            try:
                async with self._client.aio.live.connect(model=self._model, config=config) as session:
                    self._attach_session(session)
                    logger.debug("{}: Live session connected ({})", self, self._model)
                    while True:
                        # receive() yields until the server completes a turn, then
                        # returns; the next call waits for the next turn.
                        async for message in session.receive():
                            await self._on_message(message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # network / quota / model errors: surface + retry
                logger.warning("{}: Live session lost, will retry: {}", self, exc)
                await self.push_error_frame(ErrorFrame(f"Gemini Live STT error: {exc}"))
                await asyncio.sleep(RECONNECT_DELAY_SEC)
            finally:
                self._attach_session(None)

    # ------------------------------------------------------------------ audio in
    def _mime(self) -> str:
        return f"audio/pcm;rate={self.sample_rate}"

    def _preroll_limit(self) -> int:
        return int(self.sample_rate * 2 * self._preroll_ms / 1000)  # 16-bit mono

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:
        if self._in_activity and self._session is not None:
            try:
                await self._session.send_realtime_input(audio=types.Blob(data=audio, mime_type=self._mime()))
            except Exception as exc:
                logger.warning("{}: audio send failed: {}", self, exc)
        else:
            # Not inside speech: keep only the most recent pre-roll worth of audio.
            self._preroll.append(audio)
            self._preroll_bytes += len(audio)
            limit = self._preroll_limit()
            while self._preroll and self._preroll_bytes - len(self._preroll[0]) >= limit:
                self._preroll_bytes -= len(self._preroll.popleft())
        yield None

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, VADUserStartedSpeakingFrame):
            await self._begin_activity()
        elif isinstance(frame, VADUserStoppedSpeakingFrame):
            await self._end_activity()

    async def _begin_activity(self) -> None:
        if self._session is None:
            logger.warning("{}: speech started but no Live session yet - this turn will be lost", self)
            return
        if self._in_activity:
            return
        await self.start_processing_metrics()
        try:
            await self._session.send_realtime_input(activity_start=types.ActivityStart())
            # Pre-roll first so the first syllables the VAD needed to trigger are kept.
            limit = self._preroll_limit()
            buffered = b"".join(self._preroll)[-limit:] if limit > 0 else b""
            self._preroll.clear()
            self._preroll_bytes = 0
            if buffered:
                await self._session.send_realtime_input(audio=types.Blob(data=buffered, mime_type=self._mime()))
            self._in_activity = True
        except Exception as exc:
            logger.warning("{}: activity_start failed: {}", self, exc)

    async def _end_activity(self) -> None:
        if not self._in_activity:
            return
        self._in_activity = False
        if self._session is None:
            return
        try:
            await self._session.send_realtime_input(activity_end=types.ActivityEnd())
        except Exception as exc:
            logger.warning("{}: activity_end failed: {}", self, exc)

    # ------------------------------------------------------------------ results
    async def _on_message(self, message: Any) -> None:
        content = getattr(message, "server_content", None)
        if content is None:
            return
        transcription = getattr(content, "input_transcription", None)
        if transcription is not None and transcription.text:
            self._pending_text.append(transcription.text)
        if getattr(content, "generation_complete", False) or getattr(content, "turn_complete", False):
            await self._flush_transcript()

    async def _flush_transcript(self) -> None:
        text = "".join(self._pending_text).strip()
        self._pending_text.clear()
        await self.stop_ttfb_metrics()
        await self.stop_processing_metrics()
        if not text:
            logger.debug("{}: turn completed with no speech", self)
            return
        logger.debug("GeminiLiveSTTService transcript: {!r}", text)
        await self.push_frame(TranscriptionFrame(text, "", time_now_iso8601()))
