from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from collections.abc import Mapping

from .config import Settings
from .pipeline import AgentConfig, build_pipeline


LOGGER = logging.getLogger(__name__)


def load_worker_config(room: str, environ: Mapping[str, str]) -> tuple[AgentConfig, Settings]:
    raw_config = environ.get("RUMIK_AGENT_CONFIG")
    if not raw_config:
        raise ValueError("RUMIK_AGENT_CONFIG is required")
    config = AgentConfig.model_validate(json.loads(raw_config))
    if config.room != room:
        raise ValueError(f"Worker room {room!r} does not match config room {config.room!r}")
    settings = Settings(
        _env_file=None,
        openai_api_key=environ.get("OPENAI_API_KEY", ""),
        llm_provider=environ.get("LLM_PROVIDER", "openai"),
        stt_provider=environ.get("STT_PROVIDER", ""),
        cerebras_api_key=environ.get("CEREBRAS_API_KEY", ""),
        cerebras_llm_model=environ.get("CEREBRAS_LLM_MODEL", "gemma-4-31b"),
        gemini_api_key=environ.get("GEMINI_API_KEY", ""),
        gemini_llm_model=environ.get("GEMINI_LLM_MODEL", "gemini-3.5-flash-lite"),
        gemini_stt_model=environ.get("GEMINI_STT_MODEL", "gemini-3.5-flash-lite"),
        gemini_stt_mode=environ.get("GEMINI_STT_MODE", "live"),
        gemini_live_stt_model=environ.get("GEMINI_LIVE_STT_MODEL", "gemini-3.5-transcribe-live"),
        deepgram_api_key=environ.get("DEEPGRAM_API_KEY", ""),
        deepgram_stt_model=environ.get("DEEPGRAM_STT_MODEL", "nova-3-general"),
        sarvam_api_key=environ.get("SARVAM_API_KEY", ""),
        sarvam_stt_model=environ.get("SARVAM_STT_MODEL", "saaras:v3"),
        rumik_tts_stream_sentences=environ.get("RUMIK_TTS_STREAM_SENTENCES", "1").strip().lower() not in ("0", "false", "no", ""),
        rumik_api_key=environ.get("RUMIK_API_KEY", ""),
        rumik_gateway_url=environ.get("RUMIK_GATEWAY_URL", ""),
        rumik_tts_model=environ.get("RUMIK_TTS_MODEL", "muga"),
        rumik_tts_speaker=environ.get("RUMIK_TTS_SPEAKER", "speaker_1"),
        llm_model=config.llm_model,
        stt_model=config.stt_model,
    )
    return config, settings


async def run_worker(room: str, environ: Mapping[str, str], *, pipeline_builder=build_pipeline) -> None:
    config, settings = load_worker_config(room, environ)
    runtime = pipeline_builder(config, settings)
    await runtime.run()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one isolated Rumik agent session")
    parser.add_argument("--room", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(run_worker(args.room, os.environ))
    except Exception:
        LOGGER.exception("Agent worker failed for room %s", args.room)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
