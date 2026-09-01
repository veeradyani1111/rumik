from __future__ import annotations

import asyncio
import base64
from copy import deepcopy
import inspect
import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from uuid import uuid4


SendPayload = Callable[[dict[str, Any]], Awaitable[None] | None]

# Bounds for client-uploaded stills so a hostile page cannot balloon worker memory.
MAX_STILL_CHUNKS = 256
MAX_STILL_CHUNK_CHARS = 20_000
MAX_STILLS_KEPT = 4


def _value_schema(specification: Any) -> dict[str, Any]:
    if isinstance(specification, Mapping):
        if "type" in specification:
            return deepcopy(dict(specification))
        return normalize_parameters(specification)
    spec = specification.strip()
    primitives = {
        "string": {"type": "string"},
        "number": {"type": "number"},
        "integer": {"type": "integer"},
        "boolean": {"type": "boolean"},
        "object": {"type": "object"},
    }
    if spec in primitives:
        return primitives[spec]
    if spec.endswith("[]"):
        return {"type": "array", "items": _value_schema(spec[:-2])}
    if spec.startswith("{") and spec.endswith("}"):
        entries: dict[str, str] = {}
        for part in spec[1:-1].split(","):
            name, separator, value = part.partition(":")
            if separator:
                entries[name.strip()] = value.strip()
        return normalize_parameters(entries)
    if "|" in spec:
        choices = [choice.strip() for choice in spec.split("|") if choice.strip()]
        return {"type": "string", "enum": choices}
    return {"type": "string", "description": spec}


def normalize_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    if parameters.get("type") == "object" and isinstance(parameters.get("properties"), Mapping):
        schema = deepcopy(dict(parameters))
        schema.setdefault("required", list(schema["properties"]))
        schema.setdefault("additionalProperties", False)
        return schema
    names = list(parameters)
    return {
        "type": "object",
        "properties": {name: _value_schema(spec) for name, spec in parameters.items()},
        "required": names,
        "additionalProperties": False,
    }


def tool_definition(name: str, description: str, parameters: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": normalize_parameters(parameters),
        },
    }


class ClientToolBridge:
    def __init__(self, send_payload: SendPayload, *, timeout_seconds: float = 15.0) -> None:
        self._send_payload = send_payload
        self._timeout_seconds = timeout_seconds
        self._pending: dict[str, asyncio.Future[Any]] = {}
        self._still_chunks: dict[str, dict[int, str]] = {}
        self._stills: dict[str, bytes] = {}

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    async def call(
        self, name: str, args: Mapping[str, Any], *, timeout_seconds: float | None = None
    ) -> Any:
        call_id = uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self._pending[call_id] = future
        try:
            maybe_awaitable = self._send_payload(
                {"type": "tool_call", "id": call_id, "name": name, "args": dict(args)}
            )
            if inspect.isawaitable(maybe_awaitable):
                await maybe_awaitable
            return await asyncio.wait_for(
                future, timeout=timeout_seconds or self._timeout_seconds
            )
        except TimeoutError:
            return {"error": "tool_timeout"}
        finally:
            self._pending.pop(call_id, None)

    def pop_still(self, still_id: object) -> bytes | None:
        """Take ownership of a fully reassembled client still, if present."""
        if not isinstance(still_id, str):
            return None
        return self._stills.pop(still_id, None)

    def _handle_still_chunk(self, payload: Mapping[str, Any]) -> bool:
        still_id = str(payload.get("id", ""))
        try:
            seq = int(payload.get("seq", -1))
            total = int(payload.get("total", 0))
        except (TypeError, ValueError):
            return False
        data = payload.get("data")
        if (
            not still_id
            or not isinstance(data, str)
            or not 0 < total <= MAX_STILL_CHUNKS
            or not 0 <= seq < total
            or len(data) > MAX_STILL_CHUNK_CHARS
        ):
            return False
        chunks = self._still_chunks.setdefault(still_id, {})
        chunks[seq] = data
        if len(chunks) < total:
            return True
        self._still_chunks.pop(still_id, None)
        try:
            image = base64.b64decode("".join(chunks[i] for i in range(total)), validate=True)
        except (KeyError, ValueError):
            return False
        self._stills[still_id] = image
        while len(self._stills) > MAX_STILLS_KEPT:
            self._stills.pop(next(iter(self._stills)))
        return True

    async def handle_message(self, message: bytes | str | Mapping[str, Any]) -> bool:
        if isinstance(message, bytes):
            payload = json.loads(message.decode("utf-8"))
        elif isinstance(message, str):
            payload = json.loads(message)
        else:
            payload = dict(message)
        if payload.get("type") == "still":
            return self._handle_still_chunk(payload)
        if payload.get("type") != "tool_result":
            return False
        future = self._pending.get(str(payload.get("id", "")))
        if future is None or future.done():
            return False
        future.set_result(payload.get("result"))
        return True
