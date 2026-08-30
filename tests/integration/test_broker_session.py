import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from sdk.server.app import create_app
from sdk.server.broker import Broker
from sdk.server.config import Settings


class FakeAccounts:
    async def validate(self, key: str):
        return "account-1" if key == "rk_live_valid" else None

    async def signup(self, email: str):
        return type("Issued", (), {"account_id": "account-1", "api_key": "rk_live_once"})()


class FakeDatabase:
    def __init__(self) -> None:
        self.sessions: list[dict] = []

    async def create_session(self, **values) -> None:
        self.sessions.append(values)


class FakeRunner:
    def __init__(self, active: int = 0) -> None:
        self.active = active
        self.spawned: list[tuple[str, dict, dict]] = []

    def active_count(self) -> int:
        return self.active

    async def spawn(self, room: str, agent_config: dict, secret_env: dict) -> None:
        self.spawned.append((room, agent_config, secret_env))
        self.active += 1


def make_client(*, active: int = 0):
    settings = Settings(
        _env_file=None,
        livekit_url="wss://test.livekit.cloud",
        livekit_api_key="livekit-key",
        livekit_api_secret="a-livekit-secret-that-is-more-than-32-bytes",
        openai_api_key="openai-secret",
        rumik_api_key="rumik-secret",
        rumik_gateway_url="https://rumik.example",
        max_concurrent_sessions=2,
    )
    runner = FakeRunner(active)
    database = FakeDatabase()
    broker = Broker(settings, FakeAccounts(), database, runner, room_factory=lambda: "sess_fixed")
    app = create_app(settings=settings, accounts=FakeAccounts(), database=database, broker=broker)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test"), runner, database


@pytest.mark.asyncio
async def test_session_rejects_missing_and_invalid_platform_keys() -> None:
    client, _runner, _database = make_client()
    async with client:
        missing = await client.post("/session", json={"prompt": "hello"})
        invalid = await client.post(
            "/session",
            headers={"Authorization": "Bearer rk_live_wrong"},
            json={"prompt": "hello"},
        )

    assert missing.status_code == 401
    assert missing.json()["code"] == "MISSING_KEY"
    assert invalid.status_code == 401
    assert invalid.json()["code"] == "INVALID_KEY"


@pytest.mark.asyncio
async def test_session_returns_busy_at_concurrency_cap() -> None:
    client, _runner, _database = make_client(active=2)
    async with client:
        response = await client.post(
            "/session",
            headers={"Authorization": "Bearer rk_live_valid"},
            json={"prompt": "hello"},
        )

    assert response.status_code == 429
    assert response.json()["code"] == "BUSY"


@pytest.mark.asyncio
async def test_session_mints_scoped_token_and_spawns_isolated_worker() -> None:
    client, runner, database = make_client()
    async with client:
        response = await client.post(
            "/session",
            headers={"Authorization": "Bearer rk_live_valid"},
            json={
                "prompt": "You are concise.",
                "vision": True,
                "tools": [
                    {
                        "name": "submitResult",
                        "description": "Store the result",
                        "parameters": {"decision": "pass | fail | needs_review"},
                    }
                ],
                "options": {"max_fps": 99},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    claims = jwt.decode(
        payload["token"],
        "a-livekit-secret-that-is-more-than-32-bytes",
        algorithms=["HS256"],
        options={"verify_aud": False},
    )
    assert payload["room"] == "sess_fixed"
    assert claims["sub"] == "user"
    assert claims["video"]["room"] == "sess_fixed"
    assert runner.spawned[0][1]["sample_policy"]["max_fps"] == 5
    assert runner.spawned[0][1]["tools"][0]["name"] == "submitResult"
    assert runner.spawned[0][2]["OPENAI_API_KEY"] == "openai-secret"
    assert database.sessions[0]["account_id"] == "account-1"


@pytest.mark.asyncio
async def test_signup_returns_plaintext_key_once() -> None:
    client, _runner, _database = make_client()
    async with client:
        response = await client.post("/signup", json={"email": "dev@example.com"})

    assert response.status_code == 201
    assert response.json() == {"account_id": "account-1", "api_key": "rk_live_once"}
