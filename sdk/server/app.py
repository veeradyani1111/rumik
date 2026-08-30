from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .accounts import AccountService
from .agent_runner import AgentRunner
from .broker import Broker, SessionRequest, SessionResponse
from .config import Settings
from .db import Database
from .errors import PlatformError


class SignupRequest(BaseModel):
    email: str


def _bearer_key(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, separator, value = authorization.partition(" ")
    if separator and scheme.lower() == "bearer" and value.strip():
        return value.strip()
    return None


def create_app(*, settings=None, accounts=None, database=None, broker=None) -> FastAPI:
    settings = settings or Settings()
    owns_dependencies = database is None
    database = database or Database(settings.database_url)
    accounts = accounts or AccountService(database)
    runner = AgentRunner()
    broker = broker or Broker(settings, accounts, database, runner)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if owns_dependencies:
            await database.connect()
        try:
            yield
        finally:
            if owns_dependencies:
                await broker.runner.shutdown_all()
                await database.close()

    app = FastAPI(title="Rumik Agent Platform", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8000", "http://localhost:8001", "http://127.0.0.1:8000", "http://127.0.0.1:8001"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.exception_handler(PlatformError)
    async def platform_error_handler(_request: Request, error: PlatformError):
        return JSONResponse(
            status_code=error.status_code,
            content={"code": error.code, "message": error.message},
        )

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "livekit": bool(settings.livekit_url and settings.livekit_api_key),
            "rumik": bool(settings.rumik_api_key and settings.rumik_gateway_url),
            "sessions": broker.runner.active_count(),
        }

    @app.post("/signup", status_code=201)
    async def signup(payload: SignupRequest):
        issued = await accounts.signup(payload.email)
        return {"account_id": issued.account_id, "api_key": issued.api_key}

    @app.post("/session", response_model=SessionResponse)
    async def session(payload: SessionRequest, authorization: str | None = Header(default=None)):
        return await broker.create_session(_bearer_key(authorization), payload)

    return app


app = create_app()
