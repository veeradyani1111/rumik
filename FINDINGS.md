# Findings

## Dependency compatibility

- `pipecat-rumik==0.1.4` advertises compatibility with `pipecat-ai>=1,<2`, but importing it with `pipecat-ai==1.8.1` fails because `_NotGiven` was removed from `pipecat.services.settings`. The latest pair is therefore not usable as published on 2026-08-30. The project pins `pipecat-ai==1.3.0`, where the Rumik service and all planned LiveKit/OpenAI imports load successfully.

## SDK pressure discovered while building KYC

- KYC needs both a single read and a multi-frame motion view. Keeping those behind one `look({motion})` tool is workable, but an explicit developer-side `requestLook()` would make deterministic state machines easier.
- The friendly `name: "type-or-description"` tool schema is excellent for shallow tools and weak for a deeply nested KYC result. The SDK accepts `object`, while the server-side Pydantic model remains the strict final validator. A full JSON Schema escape hatch belongs in the next version.
- A tool result needs the platform session ID. The generic SDK now emits `session_started` with the room so the KYC configuration can attach it without reaching into LiveKit internals.
- Keeping images “for this turn only” required lifecycle-aware cleanup after the assistant turn. This is intentionally centralized in the pipeline rather than left to every application prompt.

## Known incomplete live evidence

- The repository arrived without `.env`, so no honest credential-backed OpenAI/Rumik/LiveKit/Neon run or screen recording could be performed during this implementation session. Offline construction and contract tests pass; the live checklist is in the README.
