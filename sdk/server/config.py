from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from pydantic_settings import BaseSettings, SettingsConfigDict


def _clamp(value: Any, minimum: float, maximum: float, cast):
    return cast(max(minimum, min(maximum, cast(value))))


@dataclass(frozen=True, slots=True)
class SamplePolicy:
    max_fps: float = 2.0
    image_max_side: int = 1024
    jpeg_quality: int = 70
    burst_count: int = 5
    burst_window_ms: int = 1500
    max_frames_per_min: int = 40

    def merge(self, overrides: Mapping[str, Any] | None = None) -> "SamplePolicy":
        values = overrides or {}
        return replace(
            self,
            max_fps=_clamp(values.get("max_fps", self.max_fps), 0.1, 5.0, float),
            image_max_side=_clamp(
                values.get("image_max_side", self.image_max_side), 128, 1280, int
            ),
            jpeg_quality=_clamp(
                values.get("jpeg_quality", self.jpeg_quality), 20, 95, int
            ),
            burst_count=_clamp(
                values.get("burst_count", self.burst_count), 1, 12, int
            ),
            burst_window_ms=_clamp(
                values.get("burst_window_ms", self.burst_window_ms), 250, 5000, int
            ),
            max_frames_per_min=_clamp(
                values.get("max_frames_per_min", self.max_frames_per_min), 1, 120, int
            ),
        )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    rumik_api_key: str = ""
    rumik_gateway_url: str = ""
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    database_url: str = ""
    demo_platform_key: str = ""

    llm_model: str = "gpt-4o"
    stt_model: str = "gpt-4o-transcribe"
    rumik_tts_model: str = "muga"
    rumik_tts_speaker: str = "speaker_1"

    vision_max_fps: float = 2.0
    image_max_side: int = 1024
    jpeg_quality: int = 70
    burst_count: int = 5
    burst_window_ms: int = 1500
    max_frames_per_min: int = 40

    session_token_ttl_sec: int = 300
    max_concurrent_sessions: int = 4

    @property
    def sample_policy(self) -> SamplePolicy:
        return SamplePolicy(
            max_fps=self.vision_max_fps,
            image_max_side=self.image_max_side,
            jpeg_quality=self.jpeg_quality,
            burst_count=self.burst_count,
            burst_window_ms=self.burst_window_ms,
            max_frames_per_min=self.max_frames_per_min,
        ).merge()

    @property
    def external_services_configured(self) -> bool:
        required = (
            self.openai_api_key,
            self.rumik_api_key,
            self.rumik_gateway_url,
            self.livekit_url,
            self.livekit_api_key,
            self.livekit_api_secret,
            self.database_url,
        )
        return all(value.strip() for value in required)
