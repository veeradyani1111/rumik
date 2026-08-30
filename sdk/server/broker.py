from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .config import Settings
from .errors import BusyError, InvalidKeyError, MissingKeyError, SpawnFailedError
from .livekit_tokens import mint_token


class VoiceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str | None = None
    speaker: str | None = None
    description: str | None = None


class ToolSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    description: str = Field(min_length=1)
    parameters: dict[str, str] = Field(default_factory=dict)


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(default="You are a helpful, concise assistant.", min_length=1, max_length=20_000)
    vision: bool = False
    voice: VoiceConfig | None = None
    tools: list[ToolSchema] = Field(default_factory=list, max_length=32)
    options: dict[str, Any] = Field(default_factory=dict)


class SessionResponse(BaseModel):
    url: str
    token: str
    room: str


class Broker:
    def __init__(
        self,
        settings: Settings,
        accounts,
        database,
        runner,
        *,
        room_factory: Callable[[], str] | None = None,
    ) -> None:
        self.settings = settings
        self.accounts = accounts
        self.database = database
        self.runner = runner
        self._room_factory = room_factory or (lambda: f"sess_{uuid4().hex[:12]}")

    async def create_session(self, platform_key: str | None, request: SessionRequest) -> SessionResponse:
        if not platform_key:
            raise MissingKeyError()
        account_id = await self.accounts.validate(platform_key)
        if account_id is None:
            raise InvalidKeyError()
        if self.runner.active_count() >= self.settings.max_concurrent_sessions:
            raise BusyError()

        room = self._room_factory()
        token_args = {
            "api_key": self.settings.livekit_api_key,
            "api_secret": self.settings.livekit_api_secret,
            "room": room,
            "can_publish": True,
            "can_subscribe": True,
            "can_publish_data": True,
        }
        user_token = mint_token(
            **token_args,
            identity="user",
            ttl_seconds=self.settings.session_token_ttl_sec,
        )
        agent_token = mint_token(
            **token_args,
            identity="agent",
            ttl_seconds=max(self.settings.session_token_ttl_sec * 2, 600),
        )
        policy = self.settings.sample_policy.merge(request.options)
        agent_config = {
            "room": room,
            "agent_token": agent_token,
            "livekit_url": self.settings.livekit_url,
            "prompt": request.prompt,
            "vision": request.vision,
            "voice": request.voice.model_dump(exclude_none=True) if request.voice else {},
            "tools": [tool.model_dump() for tool in request.tools],
            "sample_policy": asdict(policy),
            "llm_model": self.settings.llm_model,
            "stt_model": self.settings.stt_model,
        }
        secrets = {
            "OPENAI_API_KEY": self.settings.openai_api_key,
            "RUMIK_API_KEY": self.settings.rumik_api_key,
            "RUMIK_GATEWAY_URL": self.settings.rumik_gateway_url,
        }
        try:
            await self.runner.spawn(room, agent_config, secrets)
        except Exception as exc:
            raise SpawnFailedError() from exc
        await self.database.create_session(
            session_id=room,
            account_id=account_id,
            mode="vision" if request.vision else "audio",
        )
        return SessionResponse(url=self.settings.livekit_url, token=user_token, room=room)

