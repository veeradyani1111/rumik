from pipecat_rumik import RumikTTSService

from sdk.server.config import Settings
from sdk.server.rumik_tts import create_rumik_tts


def test_factory_maps_platform_and_session_voice_settings() -> None:
    settings = Settings(
        _env_file=None,
        rumik_api_key="rumik-key",
        rumik_gateway_url="https://rumik.example",
        rumik_tts_model="muga",
        rumik_tts_speaker="speaker_1",
    )

    service = create_rumik_tts(
        settings,
        voice={"model": "mulberry", "speaker": "speaker_2", "description": "warm and concise"},
    )

    assert isinstance(service, RumikTTSService)
    assert service._settings.model == "mulberry"
    assert service._settings.voice == "speaker_2"
    assert service._settings.description == "warm and concise"
