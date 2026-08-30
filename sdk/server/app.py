from __future__ import annotations

from contextlib import asynccontextmanager
from contextlib import suppress
import asyncio
import json
import logging
from pathlib import Path
import re

from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from .accounts import AccountService, hash_api_key
from .agent_runner import AgentRunner, reap_and_record, record_exits
from .broker import Broker, SessionRequest, SessionResponse
from .config import Settings
from .db import Database
from .errors import InvalidKeyError, MissingKeyError, PlatformError, SessionNotFoundError
from kyc.schema import KYCResult


logger = logging.getLogger(__name__)


class SignupRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if len(normalized) > 320 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("email must be a valid address")
        return normalized


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
        reaper_task = None
        if owns_dependencies:
            await database.connect()
            if settings.demo_platform_key:
                await database.ensure_demo_key(
                    "demo@local.invalid", hash_api_key(settings.demo_platform_key)
                )
            async def reaper_loop() -> None:
                while True:
                    try:
                        await reap_and_record(broker.runner, database)
                    except Exception:
                        logger.exception("Could not persist exited agent workers; will retry")
                    await asyncio.sleep(1)

            reaper_task = asyncio.create_task(reaper_loop(), name="agent-worker-reaper")
        try:
            yield
        finally:
            if owns_dependencies:
                if reaper_task is not None:
                    reaper_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await reaper_task
                shutdown_exits = await broker.runner.shutdown_all()
                try:
                    await record_exits(database, shutdown_exits, forced_status="ended")
                finally:
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

    @app.post("/kyc-result", status_code=201)
    async def kyc_result(payload: KYCResult, authorization: str | None = Header(default=None)):
        platform_key = _bearer_key(authorization)
        if not platform_key:
            raise MissingKeyError()
        account_id = await accounts.validate(platform_key)
        if account_id is None:
            raise InvalidKeyError()
        data = payload.model_dump(mode="json")
        try:
            await database.save_kyc_result(
                account_id=account_id,
                session_id=payload.session_id,
                decision=payload.decision,
                checks=data["checks"],
                extracted=data["extracted"],
                notes=payload.notes,
            )
        except LookupError as exc:
            raise SessionNotFoundError() from exc
        logs_dir = Path("kyc/logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / f"{payload.session_id}.json").write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )
        return {"stored": True, "session_id": payload.session_id}

    @app.get("/account")
    async def account(authorization: str | None = Header(default=None)):
        platform_key = _bearer_key(authorization)
        if not platform_key:
            raise MissingKeyError()
        account_id = await accounts.validate(platform_key)
        if account_id is None:
            raise InvalidKeyError()
        return await database.account_summary(account_id)

    @app.post("/keys/regenerate", status_code=201)
    async def regenerate_key(authorization: str | None = Header(default=None)):
        platform_key = _bearer_key(authorization)
        if not platform_key:
            raise MissingKeyError()
        account_id = await accounts.validate(platform_key)
        if account_id is None:
            raise InvalidKeyError()
        issued = await accounts.regenerate(account_id)
        return {"account_id": issued.account_id, "api_key": issued.api_key}

    @app.post("/keys/revoke")
    async def revoke_key(authorization: str | None = Header(default=None)):
        platform_key = _bearer_key(authorization)
        if not platform_key:
            raise MissingKeyError()
        account_id = await accounts.validate(platform_key)
        if account_id is None:
            raise InvalidKeyError()
        return {"revoked": await accounts.revoke(account_id, platform_key)}

    repository_root = Path(__file__).resolve().parents[2]
    sdk_assets = repository_root / "sdk" / "browser"
    docs_assets = repository_root / "web" / "docs"
    web_assets = repository_root / "web"
    if sdk_assets.is_dir():
        app.mount("/sdk", StaticFiles(directory=sdk_assets), name="sdk")
    if docs_assets.is_dir():
        app.mount("/docs", StaticFiles(directory=docs_assets, html=True), name="docs")
    if web_assets.is_dir():
        app.mount("/", StaticFiles(directory=web_assets, html=True), name="web")

    return app


app = create_app()
