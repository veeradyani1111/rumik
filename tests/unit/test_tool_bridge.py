import asyncio

import pytest

from sdk.server.tool_bridge import ClientToolBridge, normalize_parameters


def test_normalize_parameters_translates_the_developer_shorthand() -> None:
    schema = normalize_parameters(
        {
            "decision": "pass | fail | needs_review",
            "reasons": "string[]",
            "extracted": "{ name: string, panNumber: string }",
            "confidence": "number",
        }
    )

    assert schema == {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["pass", "fail", "needs_review"]},
            "reasons": {"type": "array", "items": {"type": "string"}},
            "extracted": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "panNumber": {"type": "string"},
                },
                "required": ["name", "panNumber"],
                "additionalProperties": False,
            },
            "confidence": {"type": "number"},
        },
        "required": ["decision", "reasons", "extracted", "confidence"],
        "additionalProperties": False,
    }


def test_normalize_parameters_preserves_full_json_schema_escape_hatch() -> None:
    full_schema = {
        "type": "object",
        "properties": {
            "checks": {
                "type": "object",
                "properties": {"card_read": {"type": "object"}},
                "required": ["card_read"],
                "additionalProperties": False,
            }
        },
        "required": ["checks"],
        "additionalProperties": False,
    }

    assert normalize_parameters(full_schema) == full_schema


@pytest.mark.asyncio
async def test_call_emits_id_and_matching_result_resolves() -> None:
    sent: list[dict] = []

    async def send(payload: dict) -> None:
        sent.append(payload)

    bridge = ClientToolBridge(send, timeout_seconds=0.5)
    task = asyncio.create_task(bridge.call("submitResult", {"decision": "pass"}))
    await asyncio.sleep(0)

    assert sent[0]["type"] == "tool_call"
    assert sent[0]["name"] == "submitResult"
    await bridge.handle_message(
        {"type": "tool_result", "id": sent[0]["id"], "result": {"stored": True}}
    )

    assert await task == {"stored": True}
    assert bridge.pending_count == 0


@pytest.mark.asyncio
async def test_unknown_result_id_is_ignored() -> None:
    bridge = ClientToolBridge(lambda _payload: None)

    assert await bridge.handle_message({"type": "tool_result", "id": "missing", "result": 1}) is False


@pytest.mark.asyncio
async def test_call_timeout_returns_stable_error_contract() -> None:
    async def send(_payload: dict) -> None:
        return None

    bridge = ClientToolBridge(send, timeout_seconds=0.01)

    assert await bridge.call("slowTool", {}) == {"error": "tool_timeout"}
    assert bridge.pending_count == 0
