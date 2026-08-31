from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles


ROOT = Path(__file__).resolve().parent
SDK_ROOT = ROOT.parent / "sdk" / "browser"
ClientFactory = Callable[..., httpx.AsyncClient]

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
        try:
            async with client_factory(timeout=30) as client:
                response = await client.post(
                    f"{resolved_url}{path}",
                    content=await request.body(),
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
    app.mount("/", StaticFiles(directory=ROOT, html=True), name="kyc")
    return app


app = create_app()
