# Rumik Agent SDK

A prompt-first browser SDK for agents that talk, listen, see on demand, and call developer-owned browser tools. The KYC demo proves the integration layer without reaching around it.

## What is implemented

- One developer platform key hides OpenAI, Rumik, LiveKit, and Neon credentials.
- The browser receives only a short-lived JWT scoped to one LiveKit room.
- Each session gets one room, worker subprocess, pipeline, and tenant-tagged database row.
- Pipecat connects LiveKit input → OpenAI STT → conversation context → on-demand frame sampler → OpenAI vision LLM → Rumik TTS → LiveKit output.
- `look` sends zero frames while idle, one frame for a read, or a bounded recent burst for motion. A rolling per-minute cap prevents runaway image spend.
- Client tool handlers stay in the page; schemas go to the worker and calls/results cross the LiveKit data channel.
- Video KYC is a prompt plus `submitResult` and `validatePan` tools.

## Prerequisites

- Python 3.11–3.13. Python 3.13 is used here; avoid 3.14 until the audio/ML wheels in this stack officially support it.
- Node.js 20+.
- OpenAI, Rumik Silk, LiveKit Cloud, and Neon Postgres credentials.

The project deliberately pins `pipecat-ai==1.3.0` with `pipecat-rumik==0.1.4`. Rumik currently fails to import with Pipecat 1.8.1 despite its declared `<2` compatibility; see [FINDINGS.md](FINDINGS.md).

## Install

PowerShell:

```powershell
uv venv --python 3.13 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
npm install
Copy-Item .env.example .env
```

Fill `.env`. Never commit it. `DATABASE_URL` should be a Neon Postgres connection string with TLS. `DEMO_PLATFORM_KEY` is the one key used by the local developer proxy; on platform startup its SHA-256 hash is seeded into Neon.

## Run the KYC demo

Terminal 1 — platform and workers:

```powershell
.venv\Scripts\python.exe -m uvicorn sdk.server.app:app --reload --port 8000
```

Terminal 2 — developer-owned KYC proxy:

```powershell
.venv\Scripts\python.exe -m uvicorn kyc.server:app --reload --port 8001
```

Open `http://127.0.0.1:8001`. The proxy attaches `DEMO_PLATFORM_KEY` server-side. That key never reaches the KYC page.

For the smallest generic example, run this instead in terminal 2:

```powershell
Set-Location examples\hello-agent
..\..\.venv\Scripts\python.exe -m uvicorn server:app --reload --port 8001
```

The platform home and documentation are at `http://127.0.0.1:8000` and `/docs/`.

## Use the SDK

Your server exposes a small `/session` proxy that forwards JSON to the platform and adds `Authorization: Bearer rk_live_...`. Your page then uses:

```js
const agent = RumikAgent.create({
  session: "/session",
  vision: true,
  prompt: "You are a warm, concise assistant. Greet the user and help them.",
  tools: {
    saveTicket: {
      description: "Save a support ticket",
      parameters: { subject: "string", priority: "low | high" },
      handler: async (args) => saveTicket(args),
    },
  },
});

await agent.mount("#agent");
```

See `web/docs/` for configuration, tools, KYC, errors, and sampling limits.

## Test

Fast offline suite:

```powershell
.venv\Scripts\python.exe -m pytest -q
npm test
```

The suite covers configuration clamps, key hashing/revocation, SQL adapter contracts, tenant-scoped broker behavior, JWT grants, process secret isolation, image throttling/downscaling/bursts/budgets, client-tool timeouts, tone tags, worker configuration, Pipecat construction, PAN/name/DOB logic, all 81 KYC decision combinations, and browser tool/payload behavior.

The credential-backed Rumik smoke test is explicit opt-in so normal TDD runs stay fast and never spend credits accidentally:

```powershell
$env:RUN_LIVE_TESTS = "1"
.venv\Scripts\python.exe -m pytest -q tests\integration\test_rumik_tts_live.py
```

## Manual live checkpoint

With `.env` configured:

1. Confirm `/health` reports LiveKit and Rumik configured.
2. Start the hello agent, grant microphone/camera, speak, and verify streamed Rumik audio returns.
3. Ask “what do you see?” and verify one on-demand frame informs the answer.
4. Run KYC through card read, tilt, liveness motion, and spoken name.
5. Verify the result appears in the page, Neon, and `kyc/logs/<session>.json`.
6. Record the required 3–5 minute demo.

## Security and honesty

- Platform keys and upstream keys never belong in browser code.
- Email-only signup, permissive local CORS, and the dashboard are development-grade.
- PAN format validation is not authoritative PAN verification.
- Vision-LLM hologram and face-motion checks are heuristic and can be defeated by replay or high-quality presentation attacks.
- Workers are subprocesses on one persistent host. Use managed agent dispatch and distributed concurrency control before scaling horizontally.

See [NEXT-WEEK.md](NEXT-WEEK.md) for the production hardening path.

## Prompt log

[PROMPTLOG.md](PROMPTLOG.md) is append-only and chronological. It records user-authored prompts, excludes secrets and injected environment/system metadata, and should be updated before each implementation turn. If you want a fully automatic log across tools, add an IDE/agent hook that appends the user message before dispatch; keep secret redaction in that hook.
