from sdk.server.config import Settings
from sdk.server.pipeline import AgentConfig, build_context, build_pipeline


def test_agent_config_rejects_extra_worker_payload_fields() -> None:
    config = AgentConfig.model_validate(
        {
            "room": "sess_1",
            "agent_token": "token",
            "livekit_url": "wss://example.livekit.cloud",
            "prompt": "Be helpful.",
            "vision": True,
            "voice": {},
            "tools": [
                {
                    "name": "submitResult",
                    "description": "Store result",
                    "parameters": {"decision": "pass | fail | needs_review"},
                }
            ],
            "sample_policy": {},
            "llm_model": "gpt-4o",
            "stt_model": "gpt-4o-transcribe",
        }
    )

    assert config.room == "sess_1"
    assert config.sample_policy.max_fps == 2


def test_context_combines_developer_prompt_tone_contract_and_tools() -> None:
    config = AgentConfig.model_validate(
        {
            "room": "sess_1",
            "agent_token": "token",
            "livekit_url": "wss://example.livekit.cloud",
            "prompt": "Be helpful.",
            "tools": [
                {
                    "name": "submitResult",
                    "description": "Store result",
                    "parameters": {"decision": "pass | fail | needs_review"},
                }
            ],
        }
    )

    context = build_context(config)

    assert context.messages[0]["role"] == "system"
    assert "Be helpful." in context.messages[0]["content"]
    assert "[neutral]" in context.messages[0]["content"]
    assert "proactively greet" in context.messages[0]["content"]
    schemas = context.tools.standard_tools
    assert [schema.name for schema in schemas] == ["look", "submitResult"]
    assert schemas[1].properties["decision"]["enum"] == ["pass", "fail", "needs_review"]
def test_pipeline_builds_all_services_without_connecting_to_network() -> None:
    config = AgentConfig(
        room="sess_1",
        agent_token="livekit-token",
        livekit_url="wss://example.livekit.cloud",
        prompt="Be helpful.",
        vision=True,
    )
    settings = Settings(
        _env_file=None,
        openai_api_key="openai-key",
        rumik_api_key="rumik-key",
        rumik_gateway_url="https://rumik.example",
    )

    runtime = build_pipeline(config, settings)

    assert runtime.context.messages[0]["role"] == "system"
    assert runtime.sampler.policy.max_frames_per_min == 40
    assert runtime.llm.has_function("look") is True
