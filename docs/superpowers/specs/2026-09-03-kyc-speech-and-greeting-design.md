# KYC Speech and Greeting Design

## Goal

Make the KYC call calm and deterministic: no expressive laughter, no duplicate greeting, no joining indicator during the greeting, and one concise liveness instruction that starts capture without another user command.

## Design

The KYC browser config requests a forced neutral tone. The broker carries that option into the worker config, and the TTS text filter replaces any model-selected tone tag with `[neutral]` before synthesis. Other SDK consumers keep the existing expressive-tone behavior.

When a fixed greeting is configured, the worker system prompt says that the greeting is handled separately and forbids another greeting. Without a fixed greeting, the existing proactive greeting instruction remains.

The KYC page treats subscription to the agent audio track as the end of joining, so the greeting cannot play under a stale joining state. The later speaking event remains supported.

After identity matching, the model calls `captureLiveness` silently. The page is the only speaker for this transition and says exactly: "The liveness check will appear now. Move your head left, then right." It then records automatically without separate "Go" or completion narration.

## Verification

Regression tests cover forced-tone sanitization and propagation, conditional greeting composition, the KYC UI event mapping, exact liveness wording, and the silent capture instruction. The full Python and browser suites must pass before both remote `main` branches are updated. Railway must deploy the shared commit successfully and its public health endpoints must remain healthy.
