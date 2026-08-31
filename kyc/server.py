from __future__ import annotations

import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles


ROOT = Path(__file__).resolve().parent
SDK_ROOT = ROOT.parent / "sdk" / "browser"

# The combined deployment ships one .env at the repository root. Load it so the
# proxy is self-contained instead of depending on the launching shell's exports.
load_dotenv(ROOT.parent / ".env")

PLATFORM_URL = os.getenv("PLATFORM_URL", "http://127.0.0.1:8000").rstrip("/")
PLATFORM_KEY = os.getenv("DEMO_PLATFORM_KEY", "")

app = FastAPI(title="Rumik KYC Demo")


async def _forward(path: str, request: Request) -> JSONResponse:
    if not PLATFORM_KEY:
        return JSONResponse(
            status_code=503,
            content={"code": "DEMO_KEY_MISSING", "message": "Set DEMO_PLATFORM_KEY on the demo server."},
        )
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{PLATFORM_URL}{path}",
            content=await request.body(),
            headers={"Authorization": f"Bearer {PLATFORM_KEY}", "Content-Type": "application/json"},
        )
    return JSONResponse(status_code=response.status_code, content=response.json())


@app.post("/session")
async def session(request: Request):
    return await _forward("/session", request)


@app.post("/kyc-result")
async def kyc_result(request: Request):
    return await _forward("/kyc-result", request)


app.mount("/sdk", StaticFiles(directory=SDK_ROOT), name="sdk")
app.mount("/", StaticFiles(directory=ROOT, html=True), name="kyc")

