from __future__ import annotations

import os

import aiohttp
import pytest
from pipecat.frames.frames import ErrorFrame, TTSAudioRawFrame
from pipecat_rumik import RumikHttpTTSService

from sdk.server.config import Settings


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_live_rumik_returns_nontrivial_pcm() -> None:
    if os.getenv("RUN_LIVE_TESTS") != "1":
        pytest.skip("set RUN_LIVE_TESTS=1 to spend live credentials")

    settings = Settings()
    if not settings.rumik_api_key or not settings.rumik_gateway_url:
        pytest.skip("RUMIK_API_KEY and RUMIK_GATEWAY_URL are required")

    async with aiohttp.ClientSession() as session:
        service = RumikHttpTTSService(
            api_key=settings.rumik_api_key,
            gateway_url=settings.rumik_gateway_url,
            aiohttp_session=session,
            settings=RumikHttpTTSService.Settings(
                model=settings.rumik_tts_model,
                voice=settings.rumik_tts_speaker,
            ),
        )
        frames = [
            frame
            async for frame in service.run_tts(
                "[neutral] This is the Rumik integration smoke test.",
                "live-smoke",
            )
        ]

    errors = [frame.error for frame in frames if isinstance(frame, ErrorFrame)]
    assert errors == []
    pcm = b"".join(frame.audio for frame in frames if isinstance(frame, TTSAudioRawFrame))
    assert len(pcm) > 4_800
