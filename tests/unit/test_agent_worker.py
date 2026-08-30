import json

import pytest

from sdk.server.agent_worker import load_worker_config, run_worker


def worker_env() -> dict[str, str]:
    return {
        "RUMIK_AGENT_CONFIG": json.dumps(
            {
                "room": "sess_1",
                "agent_token": "token",
                "livekit_url": "wss://example.livekit.cloud",
                "prompt": "hello",
            }
        ),
        "OPENAI_API_KEY": "openai-key",
        "RUMIK_API_KEY": "rumik-key",
        "RUMIK_GATEWAY_URL": "https://rumik.example",
    }


def test_load_worker_config_combines_json_and_secret_env() -> None:
    config, settings = load_worker_config("sess_1", worker_env())

    assert config.room == "sess_1"
    assert config.agent_token == "token"
    assert settings.openai_api_key == "openai-key"
    assert settings.rumik_api_key == "rumik-key"


def test_load_worker_config_rejects_room_mismatch() -> None:
    with pytest.raises(ValueError, match="does not match"):
        load_worker_config("sess_other", worker_env())


@pytest.mark.asyncio
async def test_run_worker_builds_and_runs_pipeline() -> None:
    events: list[str] = []

    class Runtime:
        async def run(self) -> None:
            events.append("ran")

    def builder(config, settings):
        assert config.room == "sess_1"
        assert settings.rumik_gateway_url == "https://rumik.example"
        return Runtime()

    await run_worker("sess_1", worker_env(), pipeline_builder=builder)

    assert events == ["ran"]
