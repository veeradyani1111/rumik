# KYC Speech and Greeting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove unsolicited expressive delivery and duplicate/verbose startup and liveness speech from the KYC call.

**Architecture:** Carry a KYC-only forced-tone option through the existing session configuration and enforce it at the final TTS sanitizer. Make fixed greetings alter shared prompt composition, and keep KYC UI/liveness behavior deterministic in browser code.

**Tech Stack:** Python 3.13, JavaScript ES modules, pytest, Node test runner, Railway

---

### Task 1: Add red regression coverage

**Files:**
- Modify: `tests/unit/test_tone_tags.py`
- Modify: `tests/unit/test_pipeline.py`
- Modify: `tests/integration/test_broker_session.py`
- Modify: `tests/browser/kyc-config.test.js`
- Create: `tests/browser/kyc-ui.test.js`

- [ ] **Step 1: Test forced neutral delivery**

Add assertions that `sanitize("[happy] Great", force_tone="neutral")` returns `[neutral] Great`, and that a KYC session option reaches `AgentConfig.force_tone` through the broker.

- [ ] **Step 2: Test fixed-greeting prompt composition**

Build contexts with and without `AgentConfig.greeting`. Assert only the no-greeting context requests a proactive greeting and the fixed-greeting context explicitly forbids repeating it.

- [ ] **Step 3: Test exact liveness and UI behavior**

Assert that a successful identity match directs an immediate silent `captureLiveness` call, `LIVENESS_INSTRUCTION` is exactly `The liveness check will appear now. Move your head left, then right.`, the capture implementation has no separate `Go.` narration, and the KYC page handles `agent_audio` by hiding the joining indicator and setting live status.

- [ ] **Step 4: Run focused tests and verify they fail**

Run: `python -m pytest tests/unit/test_tone_tags.py tests/unit/test_pipeline.py tests/integration/test_broker_session.py -q`

Run: `node --test tests/browser/kyc-config.test.js tests/browser/kyc-ui.test.js`

Expected: failures identify the absent forced-tone option, unconditional greeting instruction, old liveness narration, and missing `agent_audio` UI transition.

### Task 2: Implement the behavior

**Files:**
- Modify: `sdk/server/tone_tags.py`
- Modify: `sdk/server/rumik_tts.py`
- Modify: `sdk/server/pipeline.py`
- Modify: `sdk/server/broker.py`
- Modify: `kyc/kyc-config.js`
- Modify: `kyc/index.html`

- [ ] **Step 1: Enforce a configured tone**

Extend `sanitize` with an optional `force_tone`, pass it through the Rumik TTS filter, add `AgentConfig.force_tone`, propagate `options.force_tone` in the broker, and set KYC to `neutral`.

- [ ] **Step 2: Make greeting composition conditional**

Use the proactive greeting system instruction only when `AgentConfig.greeting` is empty. Otherwise state that the fixed greeting is handled separately and must not be repeated.

- [ ] **Step 3: Make liveness one automatic instruction**

Export the exact `LIVENESS_INSTRUCTION`, have `captureLivenessBurst` speak it once, remove `Go.` and completion narration, and direct the model to call the capture tool immediately without speaking after a match.

- [ ] **Step 4: End joining on agent audio**

Handle `agent_audio` in the KYC page by setting `voiceArrived`, hiding the joining indicator, and setting the live status.

- [ ] **Step 5: Run focused tests and verify they pass**

Run the two focused commands from Task 1. Expected: all selected tests pass.

### Task 3: Verify and deploy

**Files:**
- Modify: `PROMPTLOG.md`

- [ ] **Step 1: Record the request without environment or secret data**

Append a concise summary of the requested speech, liveness, greeting, deployment, and repository behavior to `PROMPTLOG.md`.

- [ ] **Step 2: Run complete verification**

Run: `python -m pytest`

Run: `npm test`

Expected: all offline tests pass, with only credential-dependent live tests skipped.

- [ ] **Step 3: Commit and push**

Commit the tested implementation, fast-forward `main` on `github-1111` and `github-222`, and restore the original active GitHub account.

- [ ] **Step 4: Verify Railway**

Wait until `rumik-sdk` and `rumik-kyc` report `SUCCESS` on the new commit, then verify both `/health` endpoints and the public KYC page.
