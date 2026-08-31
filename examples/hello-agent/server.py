from __future__ import annotations

import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles


ROOT = Path(__file__).resolve().parent
SDK_ROOT = ROOT.parents[1] / "sdk" / "browser"

# Load the combined repository-root .env so this example runs without the
# launching shell needing to export the platform credentials by hand.
load_dotenv(ROOT.parents[1] / ".env")

PLATFORM_URL = os.getenv("PLATFORM_URL", "http://127.0.0.1:8000").rstrip("/")
PLATFORM_KEY = os.getenv("DEMO_PLATFORM_KEY", "")

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

