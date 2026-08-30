import json

import pytest

from sdk.server.agent_runner import AgentRunner, reap_and_record, record_exits


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
async def test_spawn_passes_tokens_and_upstream_secrets_only_in_child_env(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://platform-secret")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "livekit-api-secret")
    monkeypatch.setenv("DEMO_PLATFORM_KEY", "rk_live_platform-secret")
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
    assert "DATABASE_URL" not in kwargs["env"]
    assert "LIVEKIT_API_SECRET" not in kwargs["env"]
    assert "DEMO_PLATFORM_KEY" not in kwargs["env"]
    assert runner.active_count() == 1


@pytest.mark.asyncio
async def test_exited_process_is_retained_until_explicitly_forgotten() -> None:
    process = FakeProcess()

    async def create_process(*_args: str, **_kwargs):
        return process

    runner = AgentRunner(process_factory=create_process)
    await runner.spawn("sess_123", {}, {})
    process.returncode = 1

    assert runner.exited() == {"sess_123": 1}
    assert runner.active_count() == 0
    assert runner.exited() == {"sess_123": 1}

    runner.forget({"sess_123": 1})

    assert runner.exited() == {}


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

    exited = await runner.shutdown_all()

    assert all(process.terminated for process in processes)
    assert runner.active_count() == 0
    assert exited == {"sess_one": 0, "sess_two": 0}


@pytest.mark.asyncio
async def test_reaper_records_ended_or_error_session_status() -> None:
    class Runner:
        def __init__(self) -> None:
            self.pending = {"sess_ok": 0, "sess_bad": 7}

        def exited(self):
            return dict(self.pending)

        def forget(self, rooms):
            for room in rooms:
                self.pending.pop(room)

    class Database:
        def __init__(self):
            self.calls = []

        async def finish_session(self, room, **values):
            self.calls.append((room, values["status"]))

    database = Database()

    assert await reap_and_record(Runner(), database) == 2
    assert database.calls == [("sess_ok", "ended"), ("sess_bad", "error")]


@pytest.mark.asyncio
async def test_reaper_retries_an_exit_when_status_persistence_fails() -> None:
    process = FakeProcess()

    async def create_process(*_args: str, **_kwargs):
        return process

    class FlakyDatabase:
        def __init__(self) -> None:
            self.attempts = 0

        async def finish_session(self, _room: str, **_values) -> None:
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("database temporarily unavailable")

    runner = AgentRunner(process_factory=create_process)
    database = FlakyDatabase()
    await runner.spawn("sess_retry", {}, {})
    process.returncode = 7

    with pytest.raises(RuntimeError, match="temporarily unavailable"):
        await reap_and_record(runner, database)

    assert await reap_and_record(runner, database) == 1
    assert await reap_and_record(runner, database) == 0
    assert database.attempts == 2


@pytest.mark.asyncio
async def test_platform_initiated_shutdown_records_workers_as_ended() -> None:
    calls = []

    class Database:
        async def finish_session(self, room: str, **values) -> None:
            calls.append((room, values["status"]))

    await record_exits(Database(), {"sess_terminated": -15}, forced_status="ended")

    assert calls == [("sess_terminated", "ended")]
