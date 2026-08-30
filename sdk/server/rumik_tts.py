from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pipecat_rumik import RumikTTSService

from .config import Settings


def create_rumik_tts(
    settings: Settings, *, voice: Mapping[str, Any] | None = None
) -> RumikTTSService:
    if not settings.rumik_api_key or not settings.rumik_gateway_url:
        raise ValueError("RUMIK_API_KEY and RUMIK_GATEWAY_URL are required")
    override = voice or {}
    service_settings = RumikTTSService.Settings(
        model=str(override.get("model") or settings.rumik_tts_model),
        voice=str(override.get("speaker") or override.get("voice") or settings.rumik_tts_speaker),
        description=override.get("description"),
    )
    return RumikTTSService(
        api_key=settings.rumik_api_key,
        gateway_url=settings.rumik_gateway_url,
        settings=service_settings,
    )
