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


def test_context_does_not_request_a_second_greeting_when_one_is_fixed() -> None:
    config = AgentConfig(
        room="sess_1",
        agent_token="token",
        livekit_url="wss://example.livekit.cloud",
        prompt="Continue the workflow.",
        greeting="Welcome to verification.",
        force_tone="neutral",
    )

    prompt = build_context(config).messages[0]["content"]

    assert "proactively greet" not in prompt
    assert "fixed greeting is handled separately" in prompt
    assert config.force_tone == "neutral"


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
        llm_provider="openai",  # explicit: an earlier test module loads .env into os.environ
        openai_api_key="openai-key",
        rumik_api_key="rumik-key",
        rumik_gateway_url="https://rumik.example",
    )

    runtime = build_pipeline(config, settings)

    assert runtime.context.messages[0]["role"] == "system"
    assert runtime.sampler.policy.max_frames_per_min == 40
    assert runtime.llm.has_function("look") is True


def test_pipeline_builds_gemini_services_when_provider_is_gemini() -> None:
    from pipecat.services.google.llm import GoogleLLMService

    from sdk.server.gemini_stt import GeminiSTTService

    config = AgentConfig(
        room="sess_g",
        agent_token="livekit-token",
        livekit_url="wss://example.livekit.cloud",
        prompt="Be helpful.",
        vision=True,
    )
    settings = Settings(
        _env_file=None,
        llm_provider="gemini",
        gemini_api_key="gemini-key",
        rumik_api_key="rumik-key",
        rumik_gateway_url="https://rumik.example",
    )

    runtime = build_pipeline(config, settings)

    assert isinstance(runtime.llm, GoogleLLMService)
    assert runtime.llm.has_function("look") is True
    assert GeminiSTTService  # importable with the google extra installed
    # The provider gate: Gemini needs the Gemini key, not the OpenAI one. (Every field is
    # explicit because an earlier test module loads the real .env into os.environ.)
    assert Settings(_env_file=None, llm_provider="gemini", gemini_api_key="k", rumik_api_key="r",
                    rumik_gateway_url="u", livekit_url="w", livekit_api_key="a", livekit_api_secret="s",
                    database_url="d").external_services_configured is True
    assert Settings(_env_file=None, llm_provider="gemini", gemini_api_key="", openai_api_key="only-openai", rumik_api_key="r",
                    rumik_gateway_url="u", livekit_url="w", livekit_api_key="a", livekit_api_secret="s",
                    database_url="d").external_services_configured is False


def test_pipeline_builds_cerebras_llm_with_gemini_stt() -> None:
    from pipecat.services.cerebras.llm import CerebrasLLMService

    config = AgentConfig(room="sess_c", agent_token="t", livekit_url="wss://example.livekit.cloud", vision=True)
    settings = Settings(
        _env_file=None,
        llm_provider="cerebras",
        stt_provider="",  # resolves to gemini: Cerebras has no STT
        cerebras_api_key="cerebras-key",
        gemini_api_key="gemini-key",
        openai_api_key="",
        rumik_api_key="rumik-key",
        rumik_gateway_url="https://rumik.example",
    )
    assert settings.resolved_stt_provider == "gemini"
    runtime = build_pipeline(config, settings)
    assert isinstance(runtime.llm, CerebrasLLMService)
    assert runtime.llm.has_function("look") is True
    # The gate needs the Cerebras key for the model AND the Gemini key for STT.
    assert Settings(_env_file=None, llm_provider="cerebras", cerebras_api_key="", gemini_api_key="g", rumik_api_key="r",
                    rumik_gateway_url="https://x", livekit_url="wss://x", livekit_api_key="k", livekit_api_secret="s",
                    database_url="postgres://x").external_services_configured is False


def _settings(**overrides) -> Settings:
    base = dict(
        _env_file=None,
        llm_provider="cerebras",
        cerebras_api_key="cerebras-key",
        gemini_api_key="gemini-key",
        openai_api_key="",
        rumik_api_key="rumik-key",
        rumik_gateway_url="https://rumik.example",
    )
    base.update(overrides)
    return Settings(**base)


def test_pipeline_builds_streaming_stt_providers() -> None:
    from pipecat.services.deepgram.stt import DeepgramSTTService
    from pipecat.services.sarvam.stt import SarvamSTTService

    config = AgentConfig(room="sess_s", agent_token="t", livekit_url="wss://example.livekit.cloud", vision=True)
    dg = _settings(stt_provider="deepgram", deepgram_api_key="dg-key")
    assert dg.resolved_stt_provider == "deepgram"
    assert dg.stt_api_key == "dg-key"
    assert dg.stt_model_name() == "nova-3-general"
    runtime = build_pipeline(config, dg)
    assert isinstance(runtime.stt, DeepgramSTTService)

    sv = _settings(stt_provider="sarvam", sarvam_api_key="sv-key")
    assert sv.stt_model_name() == "saaras:v3"
    runtime = build_pipeline(config, sv)
    assert isinstance(runtime.stt, SarvamSTTService)


def test_gate_requires_the_key_of_the_chosen_stt_provider() -> None:
    common = dict(livekit_url="wss://x", livekit_api_key="k", livekit_api_secret="s", database_url="postgres://x")
    # Deepgram chosen but no Deepgram key -> not configured, even though Gemini has a key.
    assert _settings(stt_provider="deepgram", deepgram_api_key="", **common).external_services_configured is False
    assert _settings(stt_provider="deepgram", deepgram_api_key="dg", **common).external_services_configured is True
    assert _settings(stt_provider="sarvam", sarvam_api_key="sv", **common).external_services_configured is True


def test_tts_streams_sentences_by_default_and_can_buffer_the_whole_reply() -> None:
    from pipecat_rumik.services.rumik.tts import _FullResponseTextAggregator

    config = AgentConfig(room="sess_t", agent_token="t", livekit_url="wss://example.livekit.cloud", vision=True)
    streaming = build_pipeline(config, _settings())
    assert not isinstance(streaming.tts._text_aggregator, _FullResponseTextAggregator)
    buffered = build_pipeline(config, _settings(rumik_tts_stream_sentences=False))
    assert isinstance(buffered.tts._text_aggregator, _FullResponseTextAggregator)


def test_pipeline_builds_gemini_live_stt_by_default_and_segmented_on_request() -> None:
    from sdk.server.gemini_live_stt import GeminiLiveSTTService
    from sdk.server.gemini_stt import GeminiSTTService

    config = AgentConfig(room="sess_g", agent_token="t", livekit_url="wss://example.livekit.cloud", vision=True)
    live = _settings()  # cerebras LLM -> gemini STT, mode defaults to live
    assert live.stt_model_name() == "gemini-3.5-transcribe-live"
    assert isinstance(build_pipeline(config, live).stt, GeminiLiveSTTService)
    segmented = _settings(gemini_stt_mode="segmented")
    assert segmented.stt_model_name() == "gemini-3.5-flash-lite"
    assert isinstance(build_pipeline(config, segmented).stt, GeminiSTTService)
