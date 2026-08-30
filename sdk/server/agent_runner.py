from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Awaitable, Callable, Mapping
from typing import Any


ProcessFactory = Callable[..., Awaitable[Any]]


class AgentRunner:
    def __init__(self, *, process_factory: ProcessFactory = asyncio.create_subprocess_exec) -> None:
        self._process_factory = process_factory
        self._processes: dict[str, Any] = {}

    def active_count(self) -> int:
        return sum(process.returncode is None for process in self._processes.values())

    async def spawn(
        self,
        room: str,
        agent_config: Mapping[str, Any],
        secret_env: Mapping[str, str],
    ) -> Any:
        if room in self._processes and self._processes[room].returncode is None:
            raise RuntimeError(f"Agent already running for room {room}")
        child_env = os.environ.copy()
        child_env.update(secret_env)
        child_env["RUMIK_AGENT_CONFIG"] = json.dumps(dict(agent_config), separators=(",", ":"))
        process = await self._process_factory(
            sys.executable,
            "-m",
            "sdk.server.agent_worker",
            "--room",
            room,
            env=child_env,
        )
        self._processes[room] = process
        return process

    async def reap_once(self) -> dict[str, int]:
        exited: dict[str, int] = {}
        for room, process in list(self._processes.items()):
            if process.returncode is not None:
                exited[room] = int(process.returncode)
                self._processes.pop(room, None)
        return exited

    async def shutdown_all(self) -> None:
        processes = list(self._processes.values())
        for process in processes:
            if process.returncode is None:
                process.terminate()
        if processes:
            await asyncio.gather(*(process.wait() for process in processes), return_exceptions=True)
        self._processes.clear()
