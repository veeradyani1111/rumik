from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Awaitable, Callable, Mapping
from typing import Any


ProcessFactory = Callable[..., Awaitable[Any]]
CHILD_ENV_ALLOWLIST = {
    "APPDATA",
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
}


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
        child_env = {
            key: value for key, value in os.environ.items() if key.upper() in CHILD_ENV_ALLOWLIST
        }
        child_env["PYTHONIOENCODING"] = "utf-8"
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

    def exited(self) -> dict[str, int]:
        return {
            room: int(process.returncode)
            for room, process in self._processes.items()
            if process.returncode is not None
        }

    def forget(self, rooms: Mapping[str, int]) -> None:
        for room in rooms:
            self._processes.pop(room, None)

    async def shutdown_all(self) -> dict[str, int]:
        processes = dict(self._processes)
        for process in processes.values():
            if process.returncode is None:
                process.terminate()
        if processes:
            await asyncio.gather(
                *(process.wait() for process in processes.values()), return_exceptions=True
            )
        exited = {
            room: int(process.returncode if process.returncode is not None else -1)
            for room, process in processes.items()
        }
        self._processes.clear()
        return exited


async def reap_and_record(runner: AgentRunner, database) -> int:
    exited = runner.exited()
    await record_exits(database, exited)
    runner.forget(exited)
    return len(exited)


async def record_exits(
    database, exited: Mapping[str, int], *, forced_status: str | None = None
) -> None:
    for room, return_code in exited.items():
        status = forced_status or ("ended" if return_code == 0 else "error")
        await database.finish_session(room, status=status)
