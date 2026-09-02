from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pipecat_rumik import RumikTTSService

from .config import Settings
from .tone_tags import sanitize


def create_rumik_tts(
    settings: Settings,
    *,
    voice: Mapping[str, Any] | None = None,
    force_tone: str | None = None,
) -> RumikTTSService:
    if not settings.rumik_api_key or not settings.rumik_gateway_url:
        raise ValueError("RUMIK_API_KEY and RUMIK_GATEWAY_URL are required")
    override = voice or {}
    service_settings = RumikTTSService.Settings(
        model=str(override.get("model") or settings.rumik_tts_model),
        voice=str(override.get("speaker") or override.get("voice") or settings.rumik_tts_speaker),
        description=override.get("description"),
    )

    async def sanitize_for_tts(text: str, _aggregation_type: object) -> str:
        return sanitize(text, force_tone=force_tone)

    return RumikTTSService(
        api_key=settings.rumik_api_key,
        gateway_url=settings.rumik_gateway_url,
        settings=service_settings,
        text_transforms=[("*", sanitize_for_tts)],
        # pipecat-rumik defaults to buffering the WHOLE model reply before the
        # first TTS request (to hide Rumik's ~0.3s per-request start-up). That
        # cost 1-3s of dead air on every multi-sentence line. Sentence streaming
        # speaks the first sentence while the rest is still being generated; the
        # ~0.3s between sentences reads as a natural pause.
        full_response_aggregation=not settings.rumik_tts_stream_sentences,
    )
