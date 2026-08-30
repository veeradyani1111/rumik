from __future__ import annotations

import os
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles


PLATFORM_URL = os.getenv("PLATFORM_URL", "http://127.0.0.1:8000").rstrip("/")
PLATFORM_KEY = os.getenv("DEMO_PLATFORM_KEY", "")
ROOT = Path(__file__).resolve().parent
SDK_ROOT = ROOT.parents[1] / "sdk" / "browser"

app = FastAPI(title="Rumik Hello Agent")


@app.post("/session")
async def session(request: Request):
    if not PLATFORM_KEY:
        return JSONResponse(status_code=503, content={"code": "DEMO_KEY_MISSING", "message": "Set DEMO_PLATFORM_KEY."})
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{PLATFORM_URL}/session",
            content=await request.body(),
            headers={"Authorization": f"Bearer {PLATFORM_KEY}", "Content-Type": "application/json"},
        )
    return JSONResponse(status_code=response.status_code, content=response.json())


app.mount("/sdk", StaticFiles(directory=SDK_ROOT), name="sdk")
app.mount("/", StaticFiles(directory=ROOT, html=True), name="hello")

