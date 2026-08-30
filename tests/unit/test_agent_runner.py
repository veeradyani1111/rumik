import json

import pytest

from sdk.server.agent_runner import AgentRunner


class FakeProcess:
    def __init__(self) -> None:
        self.returncode = None
        self.terminated = False

    async def wait(self) -> int:
        self.returncode = 0
        return 0

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0


@pytest.mark.asyncio
async def test_spawn_passes_tokens_and_upstream_secrets_only_in_child_env() -> None:
    calls: list[tuple[tuple[str, ...], dict]] = []

    async def create_process(*args: str, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess()

    runner = AgentRunner(process_factory=create_process)
    await runner.spawn(
        "sess_123",
        {"agent_token": "livekit-secret-token", "prompt": "hello"},
        {"OPENAI_API_KEY": "openai-secret", "RUMIK_API_KEY": "rumik-secret"},
    )

    args, kwargs = calls[0]
    command_line = " ".join(args)
    assert "livekit-secret-token" not in command_line
    assert "openai-secret" not in command_line
    assert "rumik-secret" not in command_line
    assert json.loads(kwargs["env"]["RUMIK_AGENT_CONFIG"])["agent_token"] == "livekit-secret-token"
    assert kwargs["env"]["OPENAI_API_KEY"] == "openai-secret"
    assert runner.active_count() == 1


@pytest.mark.asyncio
async def test_reap_removes_exited_processes() -> None:
    process = FakeProcess()

    async def create_process(*_args: str, **_kwargs):
        return process

    runner = AgentRunner(process_factory=create_process)
    await runner.spawn("sess_123", {}, {})
    process.returncode = 1

    assert await runner.reap_once() == {"sess_123": 1}
    assert runner.active_count() == 0


@pytest.mark.asyncio
async def test_shutdown_terminates_and_clears_all_processes() -> None:
    processes: list[FakeProcess] = []

    async def create_process(*_args: str, **_kwargs):
        process = FakeProcess()
        processes.append(process)
        return process

    runner = AgentRunner(process_factory=create_process)
    await runner.spawn("sess_one", {}, {})
    await runner.spawn("sess_two", {}, {})

    await runner.shutdown_all()

    assert all(process.terminated for process in processes)
    assert runner.active_count() == 0
