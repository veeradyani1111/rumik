from __future__ import annotations

import asyncio
from copy import deepcopy
import inspect
import json
from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from uuid import uuid4


SendPayload = Callable[[dict[str, Any]], Awaitable[None] | None]


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

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    async def call(self, name: str, args: Mapping[str, Any]) -> Any:
        call_id = uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self._pending[call_id] = future
        try:
            maybe_awaitable = self._send_payload(
                {"type": "tool_call", "id": call_id, "name": name, "args": dict(args)}
            )
            if inspect.isawaitable(maybe_awaitable):
                await maybe_awaitable
            return await asyncio.wait_for(future, timeout=self._timeout_seconds)
        except TimeoutError:
            return {"error": "tool_timeout"}
        finally:
            self._pending.pop(call_id, None)

    async def handle_message(self, message: bytes | str | Mapping[str, Any]) -> bool:
        if isinstance(message, bytes):
            payload = json.loads(message.decode("utf-8"))
        elif isinstance(message, str):
            payload = json.loads(message)
        else:
            payload = dict(message)
        if payload.get("type") != "tool_result":
            return False
        future = self._pending.get(str(payload.get("id", "")))
        if future is None or future.done():
            return False
        future.set_result(payload.get("result"))
        return True
