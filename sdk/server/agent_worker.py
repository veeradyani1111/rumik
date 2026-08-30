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
        rumik_api_key=environ.get("RUMIK_API_KEY", ""),
        rumik_gateway_url=environ.get("RUMIK_GATEWAY_URL", ""),
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
