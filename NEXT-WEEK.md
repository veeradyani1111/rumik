# What I Would Change With Another Week

1. Replace heuristic liveness with a dedicated presentation-attack/liveness provider and verify PAN data against an authoritative service.
2. Add magic-link authentication, email verification, named/scoped keys, safe rotation, per-account quotas, and rate limiting.
3. Move subprocess dispatch to LiveKit agent dispatch or a durable job system with distributed concurrency accounting.
4. Store usage events and upstream latency/cost metrics; add tracing across broker, room, worker, model, and tool calls.
5. Add an explicit SDK `requestLook()` control so deterministic workflows do not depend exclusively on the LLM choosing the built-in tool.
6. Replace the shallow parameter shorthand with a first-class JSON Schema option for deeply nested tools such as KYC results.
7. Add Playwright browser tests and credential-backed LiveKit audio/vision smoke tests in a protected CI environment.
8. Add transient-error retry policies around OpenAI and Rumik with circuit breaking, richer user-facing recovery events, and health probes that actively reach dependencies.

