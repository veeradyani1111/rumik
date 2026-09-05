from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


ROOT = Path(__file__).resolve().parent
SDK_ROOT = ROOT.parent / "sdk" / "browser"
ClientFactory = Callable[..., httpx.AsyncClient]

# Proxied requests carry a session config or a KYC result — both small JSON.
# Anything bigger is junk and just burns platform bandwidth.
MAX_PROXY_BODY_BYTES = 64_000

load_dotenv(ROOT.parent / ".env")


def create_app(
    *,
    platform_url: str | None = None,
    platform_key: str | None = None,
    client_factory: ClientFactory = httpx.AsyncClient,
) -> FastAPI:
    resolved_url = (
        platform_url
        if platform_url is not None
        else os.getenv("PLATFORM_URL", "http://127.0.0.1:8000")
    ).rstrip("/")
    resolved_key = (
        platform_key
        if platform_key is not None
        else os.getenv("DEMO_PLATFORM_KEY", "")
    )

    app = FastAPI(title="Rumik KYC Demo")

    @app.middleware("http")
    async def no_stale_assets(request: Request, call_next):
        # Without Cache-Control, browsers heuristically cache the app's JS and
        # can run a stale module against a freshly deployed page (seen live:
        # old tools, new HTML). no-cache forces revalidation; ETags keep
        # unchanged files cheap (304).
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-cache")
        return response

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "platform_configured": bool(resolved_url and resolved_key),
        }

    async def forward(path: str, request: Request) -> JSONResponse:
        if not resolved_key:
            return JSONResponse(
                status_code=503,
                content={
                    "code": "DEMO_KEY_MISSING",
                    "message": "Set DEMO_PLATFORM_KEY on the demo server.",
                },
            )
        body = await request.body()
        if len(body) > MAX_PROXY_BODY_BYTES:
            return JSONResponse(
                status_code=413,
                content={"code": "PAYLOAD_TOO_LARGE", "message": "Request body is too large."},
            )
        try:
            async with client_factory(timeout=30) as client:
                response = await client.post(
                    f"{resolved_url}{path}",
                    content=body,
                    headers={
                        "Authorization": f"Bearer {resolved_key}",
                        "Content-Type": "application/json",
                    },
                )
            content = response.json()
        except (httpx.HTTPError, ValueError):
            return JSONResponse(
                status_code=502,
                content={
                    "code": "PLATFORM_UNAVAILABLE",
                    "message": "The Rumik platform is temporarily unavailable.",
                },
            )
        return JSONResponse(status_code=response.status_code, content=content)

    @app.post("/session")
    async def session(request: Request):
        return await forward("/session", request)

    @app.post("/kyc-result")
    async def kyc_result(request: Request):
        return await forward("/kyc-result", request)

    app.mount("/sdk", StaticFiles(directory=SDK_ROOT), name="sdk")

    # Serve ONLY the two browser assets by name. A directory-wide static mount
    # here previously exposed the server's own source files and the kyc/logs
    # directory (stored KYC results) to anyone who guessed the paths.
    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(ROOT / "index.html", media_type="text/html")

    @app.get("/kyc-config.js", include_in_schema=False)
    async def kyc_config():
        return FileResponse(ROOT / "kyc-config.js", media_type="text/javascript")

    @app.get("/card-detector.js", include_in_schema=False)
    async def card_detector():
        return FileResponse(ROOT / "card-detector.js", media_type="text/javascript")

    return app


app = create_app()
