"""GeminiLiveSTTService: streaming speech-to-text over Gemini's Live API.

These tests drive the service with a fake Live session (no network) and check the
three things that make it fast and safe:
  - audio is only streamed inside an activity our own VAD opened, with a short
    pre-roll so the first word is not clipped;
  - the transcript is emitted exactly once, when Gemini says the generation is
    complete, never on a partial;
  - silence (a turn with no transcription text) emits nothing.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from pipecat.frames.frames import TranscriptionFrame
from sdk.server.gemini_live_stt import GeminiLiveSTTService


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def send_realtime_input(self, **kwargs) -> None:
        self.calls.append(kwargs)


def make_service(monkeypatch) -> tuple[GeminiLiveSTTService, list, FakeSession]:
    service = GeminiLiveSTTService(api_key="fake-key", preroll_ms=100)
    pushed: list = []

    async def fake_push(frame, direction=None):
        pushed.append(frame)

    monkeypatch.setattr(service, "push_frame", fake_push)
    session = FakeSession()
    service._attach_session(session)
    service._sample_rate = 16000
    return service, pushed, session


def msg(text: str | None = None, complete: bool = False):
    transcription = SimpleNamespace(text=text) if text is not None else None
    return SimpleNamespace(
        server_content=SimpleNamespace(
            input_transcription=transcription,
            generation_complete=complete,
            turn_complete=False,
            model_turn=None,
        )
    )


def test_requires_an_api_key() -> None:
    with pytest.raises(ValueError):
        GeminiLiveSTTService(api_key="")


def test_audio_is_gated_by_our_vad_with_a_preroll(monkeypatch) -> None:
    service, _pushed, session = make_service(monkeypatch)

    async def scenario():
        # Before speech: audio is buffered, not sent. 100ms pre-roll @16k/16-bit = 3200 bytes.
        for chunk in (b"a" * 3200, b"b" * 3200, b"c" * 1600):
            async for _ in service.run_stt(chunk):
                pass
        assert session.calls == []
        await service._begin_activity()
        # activity_start, then only the most recent 100ms of pre-roll, in order.
        assert "activity_start" in session.calls[0]
        preroll = b"".join(c["audio"].data for c in session.calls[1:])
        assert preroll == (b"b" * 3200 + b"c" * 1600)[-3200:]
        assert session.calls[1]["audio"].mime_type == "audio/pcm;rate=16000"
        # During speech: streamed live.
        async for _ in service.run_stt(b"d" * 320):
            pass
        assert session.calls[-1]["audio"].data == b"d" * 320
        await service._end_activity()
        assert "activity_end" in session.calls[-1]
        # After speech: back to buffering.
        n = len(session.calls)
        async for _ in service.run_stt(b"e" * 320):
            pass
        assert len(session.calls) == n

    asyncio.run(scenario())


def test_transcript_is_emitted_once_on_generation_complete(monkeypatch) -> None:
    service, pushed, _session = make_service(monkeypatch)

    async def scenario():
        await service._on_message(msg("Yes, I am ready"))
        assert pushed == []  # partial: nothing yet
        await service._on_message(msg(" to start.", complete=True))
        assert len(pushed) == 1
        assert isinstance(pushed[0], TranscriptionFrame)
        assert pushed[0].text == "Yes, I am ready to start."
        # A silent turn (no text) emits nothing.
        await service._on_message(msg(None, complete=True))
        assert len(pushed) == 1

    asyncio.run(scenario())
