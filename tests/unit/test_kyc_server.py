import httpx
import pytest
from httpx import ASGITransport, AsyncClient, MockTransport, Response

from kyc.server import create_app


def _client_for(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_health_reports_configuration_without_exposing_it() -> None:
    app = create_app(platform_url="https://sdk.example", platform_key="rk_live_test")

    async with _client_for(app) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "platform_configured": True}


@pytest.mark.asyncio
async def test_missing_platform_key_returns_stable_503() -> None:
    app = create_app(platform_url="https://sdk.example", platform_key="")

    async with _client_for(app) as client:
        response = await client.post("/session", json={"prompt": "hello"})

    assert response.status_code == 503
    assert response.json()["code"] == "DEMO_KEY_MISSING"


@pytest.mark.asyncio
async def test_proxy_forwards_to_public_platform_url_with_bearer_key() -> None:
    def upstream(request: httpx.Request) -> Response:
        assert str(request.url) == "https://sdk.example/session"
        assert request.headers["authorization"] == "Bearer rk_live_test"
        return Response(201, json={"room": "session-room"})

    def client_factory(**kwargs) -> AsyncClient:
        return AsyncClient(transport=MockTransport(upstream), **kwargs)

    app = create_app(
        platform_url="https://sdk.example/",
        platform_key="rk_live_test",
        client_factory=client_factory,
    )

    async with _client_for(app) as client:
        response = await client.post("/session", json={"prompt": "hello"})

    assert response.status_code == 201
    assert response.json() == {"room": "session-room"}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["connect", "invalid-json"])
async def test_proxy_returns_stable_502_for_unusable_upstream(failure: str) -> None:
    def upstream(request: httpx.Request) -> Response:
        if failure == "connect":
            raise httpx.ConnectError("unreachable", request=request)
        return Response(502, text="not-json")

    def client_factory(**kwargs) -> AsyncClient:
        return AsyncClient(transport=MockTransport(upstream), **kwargs)

    app = create_app(
        platform_url="https://sdk.example",
        platform_key="rk_live_test",
        client_factory=client_factory,
    )

    async with _client_for(app) as client:
        response = await client.post("/session", json={"prompt": "hello"})

    assert response.status_code == 502
    assert response.json() == {
        "code": "PLATFORM_UNAVAILABLE",
        "message": "The Rumik platform is temporarily unavailable.",
    }
