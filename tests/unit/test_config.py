from sdk.server.config import SamplePolicy, Settings


def test_sample_policy_merge_clamps_untrusted_overrides() -> None:
    policy = SamplePolicy().merge(
        {
            "max_fps": 99,
            "image_max_side": 4096,
            "jpeg_quality": 1,
            "burst_count": 99,
            "burst_window_ms": 50,
            "max_frames_per_min": 999,
        }
    )

    assert policy.max_fps == 5
    assert policy.image_max_side == 1280
    assert policy.jpeg_quality == 20
    assert policy.burst_count == 12
    assert policy.burst_window_ms == 250
    assert policy.max_frames_per_min == 120


def test_settings_do_not_require_secrets_for_unit_tests(monkeypatch) -> None:
    for key in (
        "OPENAI_API_KEY",
        "RUMIK_API_KEY",
        "RUMIK_GATEWAY_URL",
        "LIVEKIT_URL",
        "LIVEKIT_API_KEY",
        "LIVEKIT_API_SECRET",
        "DATABASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)

    assert settings.external_services_configured is False
    assert settings.sample_policy.max_fps == 2



def test_sample_policy_clamps_burst_fps() -> None:
    assert SamplePolicy().merge({"burst_fps": 99}).burst_fps == 15
    assert SamplePolicy().merge({"burst_fps": 0}).burst_fps == 1
    assert SamplePolicy().burst_fps == 8.0
