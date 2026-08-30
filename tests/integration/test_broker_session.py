import asyncio
import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from sdk.server.app import create_app
from sdk.server.broker import Broker, SessionRequest
from sdk.server.errors import BusyError, SpawnFailedError
from sdk.server.config import Settings


class FakeAccounts:
    async def validate(self, key: str):
        return "account-1" if key == "rk_live_valid" else None

    async def signup(self, email: str):
        return type("Issued", (), {"account_id": "account-1", "api_key": "rk_live_once"})()

    async def regenerate(self, account_id: str):
        return type("Issued", (), {"account_id": account_id, "api_key": "rk_live_fresh"})()

    async def revoke(self, account_id: str, api_key: str):
        return account_id == "account-1" and api_key == "rk_live_valid"


class FakeDatabase:
    def __init__(self) -> None:
        self.sessions: list[dict] = []
        self.finished: list[tuple[str, str]] = []

    async def create_session(self, **values) -> None:
        self.sessions.append(values)

    async def finish_session(self, session_id: str, *, status: str) -> None:
        self.finished.append((session_id, status))

    async def save_kyc_result(self, **values) -> None:
        if values["session_id"] == "sess_other":
            raise LookupError("session not owned by account")
        self.kyc_result = values

    async def account_summary(self, account_id: str):
        return {"email": "dev@example.com", "keys": [], "session_count": 1, "kyc_count": 0}


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


@pytest.mark.asyncio
async def test_signup_rejects_an_invalid_email_before_creating_an_account() -> None:
    client, _runner, _database = make_client()
    async with client:
        response = await client.post("/signup", json={"email": "not-an-email"})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_platform_serves_landing_docs_and_browser_sdk() -> None:
    client, _runner, _database = make_client()
    async with client:
        landing = await client.get("/")
        docs = await client.get("/docs/")
        sdk = await client.get("/sdk/rumik-agent.js")

    assert landing.status_code == 200
    assert docs.status_code == 200
    assert sdk.status_code == 200
    assert "export const RumikAgent" in sdk.text


@pytest.mark.asyncio
async def test_kyc_result_requires_key_and_persists_structured_result() -> None:
    client, _runner, database = make_client()
    result = {
        "decision": "needs_review",
        "checks": {
            name: {"status": "unclear", "confidence": 0.4, "reasons": ["not clear"]}
            for name in ("card_read", "hologram", "face_liveness", "name_match")
        },
        "extracted": {"name": "", "pan": "", "dob": ""},
        "session_id": "sess_fixed",
        "notes": "Heuristic only.",
    }
    async with client:
        missing = await client.post("/kyc-result", json=result)
        stored = await client.post(
            "/kyc-result",
            headers={"Authorization": "Bearer rk_live_valid"},
            json=result,
        )

    assert missing.status_code == 401
    assert stored.status_code == 201
    assert stored.json() == {"stored": True, "session_id": "sess_fixed"}
    assert database.kyc_result["account_id"] == "account-1"
    assert database.kyc_result["decision"] == "needs_review"


@pytest.mark.asyncio
async def test_kyc_result_cannot_be_attached_to_another_accounts_session() -> None:
    client, _runner, _database = make_client()
    result = {
        "decision": "needs_review",
        "checks": {
            name: {"status": "unclear", "confidence": 0.4, "reasons": ["not clear"]}
            for name in ("card_read", "hologram", "face_liveness", "name_match")
        },
        "extracted": {"name": "", "pan": "", "dob": ""},
        "session_id": "sess_other",
        "notes": "Heuristic only.",
    }
    async with client:
        response = await client.post(
            "/kyc-result",
            headers={"Authorization": "Bearer rk_live_valid"},
            json=result,
        )

    assert response.status_code == 404
    assert response.json()["code"] == "SESSION_NOT_FOUND"


@pytest.mark.asyncio
async def test_account_endpoint_is_authenticated_and_tenant_scoped() -> None:
    client, _runner, _database = make_client()
    async with client:
        response = await client.get(
            "/account", headers={"Authorization": "Bearer rk_live_valid"}
        )

    assert response.status_code == 200
    assert response.json()["email"] == "dev@example.com"
    assert response.json()["session_count"] == 1


@pytest.mark.asyncio
async def test_regenerate_and_revoke_key_endpoints_require_current_key() -> None:
    client, _runner, _database = make_client()
    headers = {"Authorization": "Bearer rk_live_valid"}
    async with client:
        regenerated = await client.post("/keys/regenerate", headers=headers)
        revoked = await client.post("/keys/revoke", headers=headers)

    assert regenerated.status_code == 201
    assert regenerated.json()["api_key"] == "rk_live_fresh"
    assert revoked.status_code == 200
    assert revoked.json() == {"revoked": True}


@pytest.mark.asyncio
async def test_concurrent_session_reservations_cannot_exceed_cap() -> None:
    settings = Settings(
        _env_file=None,
        livekit_url="wss://test.livekit.cloud",
        livekit_api_key="livekit-key",
        livekit_api_secret="a-livekit-secret-that-is-more-than-32-bytes",
        max_concurrent_sessions=1,
    )

    class SlowRunner(FakeRunner):
        async def spawn(self, room: str, agent_config: dict, secret_env: dict) -> None:
            await asyncio.sleep(0)
            await super().spawn(room, agent_config, secret_env)

    rooms = iter(("sess_one", "sess_two"))
    runner = SlowRunner()
    broker = Broker(
        settings,
        FakeAccounts(),
        FakeDatabase(),
        runner,
        room_factory=lambda: next(rooms),
    )

    results = await asyncio.gather(
        broker.create_session("rk_live_valid", SessionRequest(prompt="one")),
        broker.create_session("rk_live_valid", SessionRequest(prompt="two")),
        return_exceptions=True,
    )

    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(isinstance(result, BusyError) for result in results) == 1
    assert runner.active_count() == 1


@pytest.mark.asyncio
async def test_database_failure_does_not_orphan_a_spawned_worker() -> None:
    settings = Settings(
        _env_file=None,
        livekit_url="wss://test.livekit.cloud",
        livekit_api_key="livekit-key",
        livekit_api_secret="a-livekit-secret-that-is-more-than-32-bytes",
    )

    class FailingDatabase(FakeDatabase):
        async def create_session(self, **values) -> None:
            raise RuntimeError("database unavailable")

    runner = FakeRunner()
    broker = Broker(
        settings,
        FakeAccounts(),
        FailingDatabase(),
        runner,
        room_factory=lambda: "sess_fixed",
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await broker.create_session("rk_live_valid", SessionRequest(prompt="hello"))

    assert runner.spawned == []


@pytest.mark.asyncio
async def test_worker_spawn_failure_marks_the_reserved_session_as_error() -> None:
    settings = Settings(
        _env_file=None,
        livekit_url="wss://test.livekit.cloud",
        livekit_api_key="livekit-key",
        livekit_api_secret="a-livekit-secret-that-is-more-than-32-bytes",
    )

    class FailingRunner(FakeRunner):
        async def spawn(self, room: str, agent_config: dict, secret_env: dict) -> None:
            raise OSError("process unavailable")

    database = FakeDatabase()
    broker = Broker(
        settings,
        FakeAccounts(),
        database,
        FailingRunner(),
        room_factory=lambda: "sess_fixed",
    )

    with pytest.raises(SpawnFailedError) as error:
        await broker.create_session("rk_live_valid", SessionRequest(prompt="hello"))

    assert error.value.code == "SPAWN_FAILED"
    assert database.finished == [("sess_fixed", "error")]
