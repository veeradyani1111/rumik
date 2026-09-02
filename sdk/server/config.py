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
    # While a motion look is recording, frames are accepted at this faster rate so
    # short gestures (a blink, a card tilt) actually land inside the burst.
    burst_fps: float = 8.0
    max_frames_per_min: int = 40

    def merge(self, overrides: Mapping[str, Any] | None = None) -> "SamplePolicy":
        values = overrides or {}
        return replace(
            self,
            max_fps=_clamp(values.get("max_fps", self.max_fps), 0.1, 5.0, float),
            burst_fps=_clamp(values.get("burst_fps", self.burst_fps), 1.0, 15.0, float),
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

    # Which provider runs the reasoning model and speech-to-text: "openai" (gpt-4o +
    # gpt-4o-transcribe) or "gemini" (Gemini via a Google AI API key — no GCP project).
    llm_provider: str = "openai"  # "openai" | "gemini" | "cerebras"
    # Speech-to-text provider. Empty = follow llm_provider, except Cerebras (no STT
    # of its own) which falls back to Gemini. Values: "openai" | "gemini" |
    # "deepgram" | "sarvam". The last two STREAM: the transcript is ready the
    # moment the person stops talking, instead of a ~3s whole-utterance call.
    stt_provider: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    cerebras_api_key: str = ""
    deepgram_api_key: str = ""
    sarvam_api_key: str = ""
    deepgram_stt_model: str = "nova-3-general"
    sarvam_stt_model: str = "saaras:v3"  # Sarvam's realtime model (English + Indian languages)
    # Speak each sentence as soon as the model has produced it, instead of waiting
    # for the whole reply (first audio 1-3s sooner on long lines).
    rumik_tts_stream_sentences: bool = True
    cerebras_llm_model: str = "gemma-4-31b"  # the Cerebras model with image input
    gemini_llm_model: str = "gemini-3.5-flash-lite"  # smallest current model with vision + tools
    gemini_stt_model: str = "gemini-3.5-flash-lite"  # gemini-3.5-transcribe returns EMPTY via generateContent
    # "live" streams audio over Gemini's Live API while the person talks (transcript
    # ~0.3s after they stop); "segmented" is the old one-shot call (~3s).
    gemini_stt_mode: str = "live"
    gemini_live_stt_model: str = "gemini-3.5-transcribe-live"
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
    burst_fps: float = 8.0
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
            burst_fps=self.burst_fps,
            max_frames_per_min=self.max_frames_per_min,
        ).merge()

    @property
    def resolved_stt_provider(self) -> str:
        if self.stt_provider:
            return self.stt_provider
        return "gemini" if self.llm_provider in ("gemini", "cerebras") else "openai"

    @property
    def stt_api_key(self) -> str:
        return {
            "gemini": self.gemini_api_key,
            "deepgram": self.deepgram_api_key,
            "sarvam": self.sarvam_api_key,
        }.get(self.resolved_stt_provider, self.openai_api_key)

    def stt_model_name(self, openai_model: str | None = None) -> str:
        """The model the resolved STT provider will run (for logs and /health)."""
        return {
            "gemini": self.gemini_live_stt_model if self.gemini_stt_mode == "live" else self.gemini_stt_model,
            "deepgram": self.deepgram_stt_model,
            "sarvam": self.sarvam_stt_model,
        }.get(self.resolved_stt_provider, openai_model or self.stt_model)

    @property
    def external_services_configured(self) -> bool:
        model_key = {
            "gemini": self.gemini_api_key,
            "cerebras": self.cerebras_api_key,
        }.get(self.llm_provider, self.openai_api_key)
        stt_key = self.stt_api_key
        required = (
            model_key,
            stt_key,
            self.rumik_api_key,
            self.rumik_gateway_url,
            self.livekit_url,
            self.livekit_api_key,
            self.livekit_api_secret,
            self.database_url,
        )
        return all(value.strip() for value in required)
