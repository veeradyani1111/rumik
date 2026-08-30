# rumik2222 — Implementation Plan

**A talking, seeing agent you drop onto a web page with one key, a prompt, and your own tools.**

Assignment: build the **integration layer / SDK** (Task 1, the product) and prove it by building a **video-KYC flow on top of it** (Task 2, the proof). Both live in this one repo.

This document is the single source of truth. It is written to be handed to a coding agent and executed end-to-end. It specifies *what every file does, its interface, its core logic, and its edge cases* — not the code itself. Where an external library's exact symbols may drift between versions (Pipecat moves fast), the plan gives the precise **logic** and flags a **VERIFY-AT-BUILD** point honestly rather than inventing a signature.

---

## 0. TL;DR

- **The product = a configurable "seeing + talking agent" SDK.** A developer imports it, gives it **one key**, a **prompt**, and a set of **tools**. The SDK handles everything else: microphone, speech-to-text, an LLM loop *with vision*, tool-calling, Rumik voice, and audio playback. KYC is just *one* prompt + tools combo. Customer support, a tutor, an interviewer — same SDK, different config.
- **One key hides three services.** Behind the scenes the layer wires together **OpenAI** (LLM + vision + STT), **Rumik** (TTS voice), and **LiveKit** (WebRTC transport). The developer never sees any of them. This is the assignment's core ask: *"you are handed three keys, but a developer using your layer should need one."*
- **The developer's one key is a platform key our site issues.** They **enter their email, get an account and an API key**, and use it. Accounts, keys, sessions, and KYC results live in **Neon Postgres**, and the platform ships **proper developer docs**. The platform's server holds the real OpenAI/Rumik/LiveKit credentials. The **browser only ever holds a short-lived LiveKit token** — never a real secret. This is the assignment's *"a key is a secret, a browser is not"* requirement.
- **Multi-tenant by design, single credential-set.** The platform holds **one** set of upstream keys (OpenAI + Rumik + LiveKit) shared across *all* developers; each developer holds **one** platform key; each session is isolated by a fresh LiveKit room + scoped token + its own worker + DB rows. Serving many devs and products needs no per-dev upstream keys (§4A).
- **The judgement piece = the vision frame sampler.** The agent looks **only when it needs to** (prompt-driven), grabbing a single frame per look and a short **burst** for motion checks (hologram tilt, blink), under a hard frames-per-minute cap. 0 frames when idle. This is where the sampling budget is spent.
- **Stack (decided):** LiveKit (transport) + Pipecat (pipeline) + OpenAI (brain/eyes/ears) + Rumik `muga` (voice), glued behind a small browser SDK and a small platform server.

---

## 1. What we're building, and the "one key" model

### 1.1 Two tasks, one repo

- **Task 1 — the SDK / layer (the product).** A reusable, use-case-agnostic drop-in. Judged on developer experience.
- **Task 2 — video-KYC (the proof).** Built *entirely on top of* Task 1's SDK, reaching for nothing the SDK doesn't expose. If the SDK is awkward to build KYC on, that is a finding — it goes in `FINDINGS.md`.

### 1.2 What a developer writes

**Generic agent (the smallest honest snippet):**
```html
<div id="agent"></div>
<script type="module">
  import { RumikAgent } from 'https://<layer-host>/rumik-agent.js';
  const agent = RumikAgent.create({
    session: '/session',          // dev's own tiny endpoint that holds their ONE key
    vision: true,                 // the agent can see the camera
    prompt: 'You are a warm, concise assistant. Greet the user and help them.',
  });
  agent.mount('#agent');
</script>
```

**KYC agent — same SDK, just a richer prompt + one tool:**
```js
const agent = RumikAgent.create({
  session: '/session',
  vision: true,
  prompt: `
    You are a KYC verification agent. Greet the user and explain the steps.
    1. Ask them to hold up their PAN card. Look at it; read the name and number.
    2. Ask them to tilt the card side to side. Look again — a real hologram
       shifts as it tilts; a flat printed photo does not.
    3. Ask them to turn their head or blink to prove they are a live person. Look.
    4. Ask them to say their full name. Check it matches the card.
    Then call submitResult with your decision and the reasons.`,
  tools: {
    submitResult: {
      description: 'Record the final KYC decision',
      parameters: {
        decision: 'pass | fail | needs_review',
        reasons: 'string[]',
        extracted: '{ name: string, panNumber: string }',
      },
      handler: async (result) => renderResultPanel(result),  // runs in the dev's page
    },
  },
});
agent.mount('#kyc');
```

The developer wrote **a prompt and one tool**. Not one line about cameras, frames, STT, Rumik, LiveKit, or tool-call plumbing. The word "Look" in the prompt is enough because the SDK gives the agent a built-in ability to look at the camera on demand.

### 1.3 Who holds which secret

| Secret | Whose | Where it lives | Reaches the browser? |
|---|---|---|---|
| **Platform key** (`rk_live_...`) | the **developer's** | their server env → sent to our broker server-side via `/session` | **No** — server-side only |
| **OpenAI key** (LLM + vision + STT) | the **layer's** (platform infra) | broker/worker server env | No |
| **Rumik key** (TTS) | the **layer's** | broker/worker server env | No |
| **LiveKit API key/secret** | the **layer's** | broker/worker server env | No |
| **LiveKit room token** (short-lived JWT) | minted per session | returned to the browser | **Yes** — this is the *only* credential the browser holds |

The developer's `/session` endpoint is a ~5-line proxy that attaches their platform key and forwards to our broker. In the demo the reviewer runs, they play both roles: they put the real OpenAI/Rumik/LiveKit keys in the platform `.env`, mint a developer key on the local dashboard (or use the seeded demo key), and build KYC with it.

---

## 2. Inspiration — OSS repos we borrow patterns from

We borrow **patterns**, not dependencies. The SDK stays small and self-owned so every line is explainable (the assignment warns you will be asked to explain any line).

| Repo | What we take |
|---|---|
| [openai/openai-agents-js](https://github.com/openai/openai-agents-js) | The **developer-facing shape**: `create({ prompt, tools })` + a session; tools run client-side and can call back to a server; browser holds only an ephemeral token. Our front door mirrors this. |
| [livekit-examples/vision-demo](https://github.com/livekit-examples/vision-demo) | The **vision sampling policy**: ~1 fps while the user speaks, ~0.3 fps otherwise, frame resized + JPEG-encoded. Our sampler's baseline uses this budget. |
| [pipecat-ai/pipecat](https://github.com/pipecat-ai/pipecat) | The **pipeline** (STT → LLM → TTS over a LiveKit transport) and the **on-request frame** pattern (`UserImageRequestFrame` → next frame captured), which maps cleanly onto KYC steps. Rumik officially supports Pipecat. |
| [openai/openai-realtime-agents](https://github.com/openai/openai-realtime-agents) | **Agentic / multi-step patterns** for the KYC step machine. |

**Finding from the research pass (worth stating):** most voice-agent products (Vapi, Retell) are **audio-only** — they cannot see. Only LiveKit, Pipecat, and Gemini Live do camera vision well. So a "talking **and seeing**" SDK with vision built in is the genuinely differentiated part, and exactly where the assignment wants judgement spent.

---

## 3. Architecture

### 3.1 The three halves

```
   DEVELOPER'S PAGE                 LiveKit (WebRTC room)              THE LAYER (our server)
 ┌────────────────────┐                                            ┌───────────────────────────┐
 │  RumikAgent (JS)   │─ POST /session (platform key, server-side)►│  BROKER (FastAPI)         │
 │  cam + mic capture │◄────────── { url, token, room } ───────────│  • validate platform key  │
 │  audio playback    │                                            │  • mint LiveKit token     │
 │  tool handlers     │        ┌────────────────────────┐         │  • spawn agent worker     │
 └─────────┬──────────┘        │  room: audio + video   │         └───────────┬───────────────┘
           │ join(token)       │  + data channel (tools)│◄── join(agent) ─────┘ spawns
           └──────────────────►│                        │         ┌───────────────────────────┐
                               └────────────────────────┘         │  AGENT WORKER (Pipecat)   │
                                                                   │  STT → LLM(+vision) → TTS │
                                                                   │  + FRAME SAMPLER + tools  │
                                                                   └───────────────────────────┘
```

- **Browser (Task 1 SDK, client half):** captures mic + camera, publishes them to the LiveKit room, plays the agent's audio, and runs the developer's tool handlers. Holds only the room token.
- **Broker (Task 1 SDK, server half):** validates the platform key, mints the room token, spawns one Pipecat agent worker per session, holds all real secrets.
- **Agent worker (Task 1 SDK, the brain):** a Pipecat pipeline running server-side in the room — STT → LLM(+vision) → Rumik TTS — plus the frame sampler and the tool bridge.

### 3.2 One conversational turn

1. User speaks → mic audio → LiveKit → worker.
2. **VAD** (Silero) marks speech start/stop; **STT** (OpenAI) transcribes; turn ends.
3. **LLM** (OpenAI, vision-capable) receives the user text. If the prompt/step calls for looking, the LLM calls the built-in **`look`** tool → the **frame sampler** injects the latest camera frame(s) into the LLM context for this turn only.
4. LLM returns a reply, **tone-tagged** for Rumik `muga` (e.g. `[neutral] ...`).
5. **Rumik TTS** streams the text to voice → PCM frames → LiveKit → browser plays. Agent is "speaking."
6. User interrupts → Pipecat cancels current TTS (barge-in). Loop.

### 3.3 A tool call (client tool)

When the LLM calls a developer-defined tool (e.g. `submitResult`), the worker's tool bridge sends `{type:'tool_call', id, name, args}` over the LiveKit **data channel** → the browser runs the developer's `handler(args)` → returns `{type:'tool_result', id, result}` → the worker feeds the result back to the LLM. Built-in tools (`look`) run server-side in the worker and never leave it.

---

## 4A. Credential & tenancy model (one platform serving many devs and products)

The SDK is multi-tenant: one platform operator (you), many developers, each building many products, each running many concurrent sessions/pipelines. The credential model is deliberately flat — **you do not multiply upstream keys per developer.**

### Who holds what
| Party | Credentials | Count | Notes |
|---|---|---|---|
| **Platform operator (you)** | `OPENAI_API_KEY`, `RUMIK_API_KEY` + `RUMIK_GATEWAY_URL`, `LIVEKIT_API_KEY` + `LIVEKIT_API_SECRET`, `DATABASE_URL` (Neon) | **one set total** | shared across *all* developers; set once in the platform env / deployment secrets |
| **Developer** | their platform key `rk_live_...` (you issued it) | **one per dev** | the only thing they ever configure |
| **Session / product / pipeline** | a fresh LiveKit **room** + a short-lived scoped **token** | minted per session, stored 0 | this is the unit of isolation |

### How isolation works without more keys
Every session = **one LiveKit room + one worker process + one Pipecat pipeline**, all drawing on the platform's single upstream key-set. Tenants never collide because:
1. **Room-scoping** — each session gets a unique room; the browser's token is scoped to that room only.
2. **Process isolation** — each session runs its own worker subprocess.
3. **DB tenancy** — `accounts` → `api_keys` → `sessions` / `kyc_results`; every session and result is tagged to the owning account, so usage and data are separated logically.

So "many pipelines for many devs and products" is a **database + room-scoping** problem, not a credential-multiplication problem. Concurrency is bounded by `MAX_CONCURRENT_SESSIONS` (kept under Rumik's cap), not by how many developers exist.

### Why both LiveKit and Pipecat
- **LiveKit** = the real-time **transport** (WebRTC): mic + camera up, voice down, low-latency, reconnection/NAT handled. Hosted on LiveKit Cloud — nothing to run.
- **Pipecat** = the **pipeline** inside each worker: STT → LLM(+vision) → Rumik TTS, VAD, barge-in, frames. Runs *over* the LiveKit transport.
They are complementary layers, not alternatives.

### Deployment credentials
Deploying adds **no new kinds** of credentials — the same env-set becomes the host's **deployment secrets**. LiveKit Cloud and Neon are already hosted; only the **broker + workers** need a home. Because workers are long-running spawned processes, deploy to a **persistent server** (Render / Fly / Railway / a VM), **not** pure serverless (functions time out before a voice session ends). The platform also needs a **public HTTPS URL** so browsers and developer `/session` proxies can reach it.

### Optional (next-week): bring-your-own-key
A real customer could attach *their own* OpenAI/Rumik key to their account (encrypted at rest); the platform would use it for their sessions so billing lands on them. Not required for the assignment — documented as a future path only.

---

## 4. Tech stack & dependencies

- **Transport:** **LiveKit Cloud** (a `wss://*.livekit.cloud` project already exists — no self-hosted server, no Docker required for the demo).
- **Pipeline engine:** **Pipecat** (`pipecat-ai`) — the STT/LLM/TTS graph over LiveKit transport.
- **Brain + eyes + ears:** **OpenAI** — `gpt-4o` (LLM + vision) and a transcription model (STT) via Pipecat's OpenAI services.
- **Voice:** **Rumik** Silk `muga` via the **`pipecat_rumik`** `RumikTTSService` (already exists; used in the prior prototype).
- **Server:** **FastAPI + Uvicorn** (broker, signup + key issuance, developer docs, KYC result store).
- **Browser SDK:** vanilla ES module + `livekit-client` (framework-free on purpose).
- **Accounts / keys / sessions / results store:** **Neon Postgres** (via `asyncpg`) — a real hosted Postgres. Accounts, issued API keys, sessions, and KYC results persist here; `schema.sql` applied idempotently on startup so a fresh Neon DB self-initializes.
- **Tests:** `pytest`, `pytest-asyncio`, `httpx`, `PyJWT`.

### 4.1 `requirements.txt` (pin exact versions at build; verify import paths)
```
fastapi
uvicorn[standard]
pipecat-ai            # verify the extras needed: [livekit,openai,silero]
pipecat-rumik         # Rumik TTS service for Pipecat (verify package/module name at build)
livekit-api           # server-side LiveKit token minting (AccessToken / VideoGrants)
openai
httpx
pydantic>=2
pillow                # frame downscale + JPEG encode
numpy
python-dotenv
asyncpg               # Neon Postgres (accounts, keys, sessions, kyc_results)
pytest
pytest-asyncio
pyjwt
```

> **VERIFY-AT-BUILD (honest):** Pipecat symbol names for the LiveKit transport, `OpenAISTTService`, `OpenAILLMService`, the TTS/function-calling APIs, and the **video-input frame classes** (`UserImageRequestFrame` / `UserImageRawFrame` / `InputImageRawFrame`) must be confirmed against the *installed* Pipecat version by reading its source or examples. The prior prototype (now deleted) confirmed these import paths work on one recent version: `pipecat.services.openai.stt.OpenAISTTService`, `pipecat.services.openai.llm.OpenAILLMService`, `pipecat.transports.livekit.transport.LiveKitTransport/LiveKitParams`, `pipecat.audio.vad.silero.SileroVADAnalyzer`, and `from pipecat_rumik import RumikTTSService`. Pin one version and do not float it. The *logic* in this plan is version-stable; only symbol names may drift.

---

## 5. Repository layout

```
rumik2222/
  IMPLEMENTATION_PLAN.md        # this file
  README.md                     # run it, use the SDK, what's next
  PROMPTLOG.md                  # every prompt given to the coding agent, in order (deliverable)
  FINDINGS.md                   # where the SDK was awkward to build KYC on (deliverable)
  NEXT-WEEK.md                  # what I'd change with another week (deliverable)
  .env.example                  # all env vars, no secrets
  .gitignore                    # .env, __pycache__, *.db, *.wav, node stuff
  requirements.txt
  Makefile                      # run / test / demo shortcuts

  sdk/                          # ── Task 1: the reusable SDK / layer (the product) ──
    browser/
      rumik-agent.js            # the drop-in browser SDK (ESM): create / mount / stop
      livekit-bridge.js         # wraps livekit-client: join, publish tracks, data channel
      rumik-agent.css           # minimal styles (design not judged; keep tiny)
    server/
      __init__.py
      config.py                 # env loading, typed Settings, SamplePolicy defaults
      app.py                    # FastAPI: /signup, /session, /health, /kyc-result, serves web/
      broker.py                 # session orchestration (validate key → token → spawn worker)
      db.py                     # asyncpg pool + schema.sql applied idempotently on startup
      schema.sql                # accounts / api_keys / sessions / kyc_results (Postgres)
      accounts.py               # signup (email→account→key), key mint + validate (sha256)
      livekit_tokens.py         # mint user + agent LiveKit JWTs
      agent_runner.py           # spawn / track / reap agent worker subprocesses per room
      agent_worker.py           # Pipecat pipeline entrypoint (runnable standalone)
      pipeline.py               # builds the Pipecat pipeline (services + processors)
      frame_sampler.py          # THE vision sampling policy (the judgement piece)
      tool_bridge.py            # server<->browser client-tool round-trip over data channel
      rumik_tts.py              # thin config/wrapper around pipecat_rumik RumikTTSService
      tone_tags.py              # muga tone-tag system-prompt fragment + sanitizer
      errors.py                 # typed errors + failure-handling helpers

  web/                          # ── the platform's own site (signup + dashboard + docs) ──
    index.html                  # landing + "get your key" (email → account → API key)
    dashboard.html              # account view: masked key(s), usage, regenerate / revoke
    docs/                       # proper developer documentation
      index.html                # quickstart + the smallest snippet
      configuration.html        # prompt / vision / voice / tools / sampler-option reference
      tools.html                # client tools vs built-in `look`; how tool-calling round-trips
      kyc-example.html          # the KYC flow as a copyable recipe
      errors.html               # failure behavior, error codes, the sampling budget
      docs.css                  # shared minimal docs styling

  examples/
    hello-agent/                # smallest honest snippet: talks + sees (Task 1 proof)
      index.html
      server.py                 # ~5-line dev '/session' proxy → broker (models key hiding)

  kyc/                          # ── Task 2: built ON the SDK, no reaching past it ──
    index.html                  # mounts RumikAgent with the KYC prompt + submitResult tool
    kyc-config.js               # the KYC prompt + tool definitions (the whole "KYC app")
    verify.py                   # pure helpers: PAN regex, name match, decision policy
    schema.py                   # pydantic models for the structured KYC result
    server.py                   # dev '/session' proxy for the KYC page
    logs/                       # written KYC results (.json), gitignored except .gitkeep

  tests/
    unit/
      test_frame_sampler.py
      test_tool_bridge.py
      test_tone_tags.py
      test_accounts.py
      test_pan_and_name.py
      test_kyc_schema_and_decision.py
      test_livekit_tokens.py
    integration/
      test_rumik_tts_live.py    # hits live Rumik TTS, asserts real audio bytes
      test_broker_session.py    # /session mints a decodable, correctly-scoped token
      test_agent_smoke.py       # headless: fake user joins, gets audio back
      test_vision_smoke.py      # publish a static image track, agent describes it
      fixtures/
        sample_pan.jpg          # a synthetic sample PAN card for the read path
        tilt_frames/            # frames simulating a card tilt (offline hologram test)
```

---

## 6. Environment & configuration

### 6.1 `.env.example`
```
# ── Layer secrets (the platform holds these; never sent to the browser) ──
OPENAI_API_KEY=sk-...                       # gpt-4o (LLM+vision) + transcription (STT)
RUMIK_API_KEY=rk_...                         # Rumik Silk TTS
RUMIK_GATEWAY_URL=https://...                # Rumik gateway base URL (from Rumik dashboard)

# ── LiveKit Cloud ──
LIVEKIT_URL=wss://<project>.livekit.cloud    # what the BROWSER connects to
LIVEKIT_API_KEY=API...
LIVEKIT_API_SECRET=...

# ── Models ──
LLM_MODEL=gpt-4o                             # vision-capable
STT_MODEL=gpt-4o-transcribe                  # or gpt-4o-mini-transcribe
RUMIK_TTS_MODEL=muga
RUMIK_TTS_SPEAKER=speaker_1

# ── Platform (Neon Postgres) ──
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DB?sslmode=require   # Neon connection string
DEMO_PLATFORM_KEY=rk_live_demo               # seeded dev key so the demo works instantly

# ── Vision sampling policy (defaults; overridable per session) ──
VISION_MAX_FPS=2                             # hard cap on frames/sec sent to the LLM
IMAGE_MAX_SIDE=1024                          # longest edge before JPEG encode
JPEG_QUALITY=70
BURST_COUNT=5                                # frames in a motion burst (tilt/blink)
BURST_WINDOW_MS=1500
MAX_FRAMES_PER_MIN=40                        # spend cap; sampler refuses beyond this

# ── Broker ──
SESSION_TOKEN_TTL_SEC=300
MAX_CONCURRENT_SESSIONS=4                     # keep under Rumik's concurrency cap
```

### 6.2 `config.py`
- Loads `.env`; exposes a typed `Settings` (pydantic `BaseSettings` or frozen dataclass) for every var above.
- Exposes a `SamplePolicy` dataclass (the sampler defaults) with a `merge(overrides)` that lets `/session` callers override knobs per session, **validated + clamped** (`max_fps ≤ 5`, `image_max_side ≤ 1280`, `burst_count ≤ 12`, `max_frames_per_min ≤ 120`).

---

## 7. The platform server (`sdk/server/app.py` + `broker.py` + `accounts.py` + `db.py`)

A FastAPI app. It serves the JSON API, the platform site (`web/`), and the developer docs (`web/docs/`). Endpoints:

### 7.1 `GET /health`
`{ "status": "ok", "livekit": <bool>, "rumik": <bool>, "sessions": <active_count> }`. Pings Rumik + LiveKit reachability (cached ~30 s) so a reviewer sees deps green.

### 7.2 Signup & keys — email → account → API key
- **`POST /signup { email }`** → if the email is new, create an `accounts` row. Always issue a fresh `rk_live_<32 random>` key, store only its **sha256 hash** in `api_keys`, and return the **plaintext key once** for the developer to copy. A returning email gets a new key (existing keys stay valid until revoked).
- **`web/index.html`** — the "get your key" page: an email box → on submit calls `/signup` → shows the issued key **once** + the copy-paste snippet to start. **`web/dashboard.html`** — a returning developer views masked key(s) + usage and can regenerate/revoke (`POST /keys/regenerate`, `POST /keys/revoke`, auth by current key).
- The seeded **`DEMO_PLATFORM_KEY`** is also accepted directly, so the reviewer's demo works with zero signup.
- **Honest scope (documented):** email-only, no password / no email verification yet — dev-grade onboarding. Next-week hardening: magic-link verification, multiple named keys, per-key scopes, rotation.

### 7.3 `POST /session` (the heart of the layer)
**Auth:** `Authorization: Bearer <platform_key>` (the developer's key, attached by their server-side proxy).
**Body (optional):**
```json
{ "prompt": "…", "vision": true, "voice": {…}, "tools": [ {name, description, parameters} ], "options": {…sampler overrides…} }
```
> Note: only tool **schemas** (name/description/parameters) travel to the server. Tool **handlers** stay in the browser. Built-in tools (`look`) are added server-side.

**Steps:**
1. Extract platform key → sha256 → look up in `api_keys` (not revoked). Missing → `401 MISSING_KEY`; unknown/revoked → `401 INVALID_KEY`.
2. **Concurrency guard:** active sessions ≥ `MAX_CONCURRENT_SESSIONS` → `429 BUSY`.
3. `room = "sess_" + uuid4().hex[:12]`.
4. **Mint two LiveKit tokens** (via `livekit_tokens.py`):
   - `user_token`: identity `user`, `roomJoin`, `room`, `canPublish` (audio+video), `canSubscribe`, `canPublishData` (for tool replies), TTL = `SESSION_TOKEN_TTL_SEC`.
   - `agent_token`: identity `agent`, same room, publish audio + data, subscribe, longer TTL.
5. **Spawn the worker** (via `agent_runner.py`): launch `agent_worker.py` with the room, `agent_token`, `LIVEKIT_URL`, the merged prompt/persona, tool schemas, voice, sample policy, and the layer's OpenAI + Rumik keys (via child **env**, not argv). Register it in the active-session table. Insert a `sessions` row (`status=active`).
6. Return `200 { url: LIVEKIT_URL, token: user_token, room }`.

**Error contract (`{code, message}`):** `MISSING_KEY(401)`, `INVALID_KEY(401)`, `BUSY(429)`, `SPAWN_FAILED(503)`.
**CORS:** allow localhost demo origins so the example pages can call `/session` directly in the demo. (In production the developer's own backend calls it; documented in README.)

### 7.4 KYC result + account endpoints
- `POST /kyc-result` (called by the worker's `submitResult` path, server-side) → insert a `kyc_results` row + write `kyc/logs/<session>.json` (a copy for the recording).
- `GET /account` (auth) → email, masked key(s), session + KYC counts → backs `web/dashboard.html`.

### 7.5 `db.py` + `accounts.py` — Neon Postgres store
- **`db.py`:** an `asyncpg` connection pool created on broker startup from `DATABASE_URL` (Neon, `sslmode=require`). Thin typed query helpers, **no ORM** (keeps it legible). `schema.sql` applied idempotently on startup (`CREATE TABLE IF NOT EXISTS`), so a fresh Neon database self-initializes on first boot.
- **`accounts.py`:** signup, key mint (sha256 hash stored, plaintext returned once), key validate/resolve-account, regenerate, revoke.
- **Schema (`schema.sql`):**
  - `accounts(id uuid pk, email text unique, created_at timestamptz default now())`
  - `api_keys(id uuid pk, account_id uuid fk→accounts, key_hash text unique, label text, created_at timestamptz default now(), revoked_at timestamptz null)`
  - `sessions(id text pk /* = room */, account_id uuid fk, mode text, status text /* active|ended|error */, started_at timestamptz default now(), ended_at timestamptz null, turns int default 0, images_sent int default 0)`
  - `kyc_results(id uuid pk, account_id uuid fk, session_id text fk→sessions, decision text, checks jsonb, extracted jsonb, notes text, created_at timestamptz default now())`
- Usage is **derived** by aggregating `sessions` + `kyc_results` per account (no separate billing table — that's next-week).

### 7.6 Developer docs (`web/docs/`) — the platform's proper documentation
Static pages served by the platform. The assignment's #1 criterion is *developer experience*, so real docs matter as much as the code:
- **Quickstart** — get a key, the smallest snippet, run it.
- **Configuration reference** — `prompt`, `vision`, `voice`, `tools`, sampler `options`: every knob, type, and default.
- **Tools guide** — client tools (browser handler) vs the built-in `look`; how a tool call round-trips; worked examples.
- **KYC example** — the full flow as a copyable recipe.
- **Errors & limits** — error codes, failure behavior, the sampling budget.
These pages double as the backbone of the top-level `README.md`.

---

## 8. LiveKit token minting (`sdk/server/livekit_tokens.py`)

- Thin wrapper over `livekit-api`'s `AccessToken` + `VideoGrants`.
- `mint(identity, room, ttl, can_publish, can_subscribe, can_publish_data) -> JWT`.
- Grants: `room_join=True`, `room`, `can_publish`, `can_subscribe`, `can_publish_data=True` (needed for the tool data channel).
- Signed with `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET`.
- **Testable in isolation:** decode with `PyJWT` + the secret; assert identity, room grant, publish/subscribe/data flags, `exp ≈ now+ttl`.

---

## 9. The agent worker (`sdk/server/agent_worker.py` + `pipeline.py`)

Runnable **standalone** (`python -m sdk.server.agent_worker --room X --token Y ...`) so it can be tested directly against a room without the broker — a deliberate testability win.

### 9.1 `agent_worker.py` (entrypoint)
- Parses args/env: room, agent token, LiveKit URL, prompt, tool schemas (JSON), voice, sample policy, OpenAI key, Rumik key + gateway.
- Builds the pipeline (`pipeline.py`), runs it via Pipecat's runner/worker.
- On room-empty or idle-timeout (~90 s no audio), shuts down cleanly and exits (so `agent_runner` reaps it and the broker frees a slot). On the first participant joining, speaks the greeting.
- Top-level try/except → logs, non-zero exit on fatal error.

### 9.2 `pipeline.py` (the graph)
Constructs, in order (mirrors the prior prototype, **plus** video + tools):
1. **LiveKit input transport** — `audio_in_enabled=True`, **`video_in_enabled=True`**, `vad_analyzer=SileroVADAnalyzer()`. Joins `room` with `agent_token`.
2. **STT** — `OpenAISTTService(model=STT_MODEL)`.
3. **User context aggregator** — accumulates the user turn.
4. **FrameSampler** (§11) — sees inbound video frames; injects images into the LLM context on demand; serves the `look` tool and bursts.
5. **LLM** — `OpenAILLMService(model=LLM_MODEL)` with **registered tools**: the built-in `look`, plus the developer's client tools (bridged via §12). System prompt = developer prompt + `tone_tags` fragment (+ nothing KYC-specific here — KYC lives entirely in the developer's prompt/tools, proving the layer).
6. **Rumik TTS** (§13).
7. **LiveKit output transport** — plays agent audio; also carries data messages (tool calls/replies).
8. **Assistant context aggregator** — records agent turns.

`transport.input() → stt → user_ctx → sampler → llm → tts → transport.output() → assistant_ctx`.
(Exact aggregator wiring per the installed Pipecat's `LLMContext` / aggregator pair — **VERIFY-AT-BUILD**.)

**Barge-in:** Pipecat interruption support (VAD-driven) cancels in-flight Rumik TTS when the user speaks.

### 9.3 `agent_runner.py` (subprocess lifecycle)
- `spawn(room, agent_token, config) -> handle` via `asyncio.create_subprocess_exec`.
- Tracks `{room: process}`; `active_count()`; a `reap()` loop removing exited processes; `shutdown_all()` on broker exit. On exit, updates the `sessions` row (`status`, `ended_at`, `turns`, `images_sent`).
- Secrets passed via child **env**, never argv.
> **Alternative (documented, not default):** LiveKit's own agent-dispatch mechanism could run the worker instead of subprocess spawning. Subprocess is chosen for simplicity and standalone testability.

---

## 10. (reserved)

---

## 11. Vision — the frame sampler (`sdk/server/frame_sampler.py`) — the judgement piece

**Goal:** never fire-hose the LLM. **0 frames idle, look only when asked, a short burst for motion, under a hard cap.**

### 11.1 Structure
A Pipecat `FrameProcessor` subclass + a `SamplePolicy`.

**State:** `latest_raw (frame, ts)` (most recent decoded inbound video frame), `last_accept_ts` (for `max_fps` throttle), `frames_this_minute` (for the spend cap), `policy`.

**Inbound video handling:**
- Throttle: if `now - last_accept_ts < 1/max_fps`, **drop** without storing (cheap).
- Else store as `latest_raw`, update `last_accept_ts`. Never forward raw video downstream.

**The `look` built-in tool** (registered on the LLM):
- `look(reason: str, motion: bool = false)`.
- `motion=false` → take `latest_raw`, downscale (Pillow, longest side = `image_max_side`), JPEG-encode (`jpeg_quality`), inject as one image content part into the LLM context **for this turn only** (not persisted into long history — bounds context growth).
- `motion=true` → collect a **burst** of `burst_count` frames over `burst_window_ms` (await fresh inbound frames, or reuse `latest_raw` if the stream is slow), inject all as multiple image parts in one call — so the LLM can judge *movement* (hologram shift, blink, head turn).
- Every accepted frame increments `frames_this_minute`. Beyond `max_frames_per_min` → `look` returns a "budget exhausted, using last frame" note instead of new captures. (The spend cap, exposed as one knob.)
- If no frame is available (camera off/refused) → inject a sentinel "(no camera frame available)" so the LLM reacts gracefully.

### 11.2 Cost intuition (documented in README)
- Idle: **0** image tokens.
- 10-turn chat where it looks each turn: ~10 images.
- Full KYC run: ~1 read look + 1 hologram burst + 1 liveness burst ≈ 1 + 5 + 5 ≈ 11 images + a few singles. Bounded and predictable — the opposite of "every frame to the LLM."

### 11.3 Exposed vs hidden
- **Exposed knobs** (via `/session options`): `max_fps`, `image_max_side`, `jpeg_quality`, `burst_count`, `burst_window_ms`, `max_frames_per_min`.
- **Hidden (just works):** decode, throttle, downscale, encode, context injection, budget accounting, "no frame" handling.

---

## 12. Tools — the client-tool bridge (`sdk/server/tool_bridge.py`)

The mechanism that lets a developer's browser function be called by a server-side LLM.

**Registration:** each developer tool schema (`name`, `description`, `parameters`) is registered on the Pipecat LLM as a function. Its server-side handler is a **bridge stub**: when the LLM calls it, the stub:
1. Generates a `call_id`, sends `{type:'tool_call', id, name, args}` over the LiveKit **data channel** to the `user` identity.
2. Awaits a matching `{type:'tool_result', id, result}` (timeout ~15 s).
3. Returns `result` to the LLM via Pipecat's function-result callback so the model continues. On timeout → returns `{error:'tool_timeout'}` and the agent apologizes.

**Parameter shape:** the developer writes `parameters` as a simple object of `name: 'type-or-description'`. `tool_bridge` normalizes this into a JSON-Schema `parameters` object for the LLM (OpenAI function-calling shape). Keep the developer's authoring shape dead simple; do the schema translation for them.

**Built-in vs client tools:** `look` (and any future built-ins) run **server-side** in the worker and never touch the data channel. Client tools always round-trip to the browser. Documented clearly so developers know where their code runs.

**Browser side (in `rumik-agent.js`):** listens for `tool_call` data messages, looks up the handler by `name`, `await`s it, and replies with `tool_result`. Errors in the handler are caught and returned as `{error}`.

---

## 13. Rumik TTS (`sdk/server/rumik_tts.py`) + tone tags

### 13.1 Service
- Reuse the existing **`pipecat_rumik.RumikTTSService`** (confirmed to import). Configure:
  ```
  RumikTTSService(
    api_key=RUMIK_API_KEY,
    gateway_url=RUMIK_GATEWAY_URL,
    settings=RumikTTSService.Settings(model="muga", voice=RUMIK_TTS_SPEAKER, description=<persona voice>),
  )
  ```
  **VERIFY-AT-BUILD:** exact `Settings` fields and constructor signature against the installed `pipecat_rumik` version.
- `rumik_tts.py` is a thin factory that reads config and returns the configured service, plus any wrapping we need for error surfacing.

### 13.2 Tone tags (`tone_tags.py`)
- **System-prompt fragment** instructing the LLM to emit `muga`-tagged text: start each paragraph with one of `[neutral] [happy] [excited] [sad] [angry] [whisper]`; keep paragraphs 1–3 sentences; **wrap digit strings (PAN number, DOB) in double quotes** so muga reads them digit-by-digit; output only tagged text, no markdown.
- `sanitize(text) -> text`: guarantees a leading tone tag (default `[neutral]`) if the model forgets and strips stray markdown, so TTS never receives a broken line.

### 13.3 Errors
- Rumik `429` (concurrency/rate) → brief backoff + one retry. `402` (credits) → spoken apology + end. Generation error → one retry then apologize. WS drop mid-utterance → reconnect + resend (handled inside `pipecat_rumik` where possible; wrap + surface otherwise).

---

## 14. The browser SDK (`sdk/browser/rumik-agent.js`)

Deliberately small and framework-free. Imports `livekit-client` (pinned).

### 14.1 Public API
```js
RumikAgent.create({
  session,                 // URL of the dev's /session proxy (POST)
  prompt,                  // the agent's instructions
  vision = false,          // publish camera + allow the agent to look
  voice,                   // optional { model, speaker, description }
  tools,                   // { name: { description, parameters, handler } }
  options,                 // optional sampler overrides
  onState,                 // (state) => {}  connecting|live|reconnecting|ended|error
  onEvent,                 // (evt) => {}     transcript, agent_speaking, tool_call, ...
  onError,                 // (err) => {}
}) -> { mount(target), stop() }
```

### 14.2 Behavior
1. `POST session` with `{ prompt, vision, voice, tools:<schemas only>, options }` → `{ url, token, room }`.
2. Create a LiveKit `Room`; `connect(url, token)`.
3. `getUserMedia`: mic always; camera if `vision`. Publish tracks.
   - **Camera refused / none** → connect audio-only, fire `onState('live')` + `onEvent({type:'camera_unavailable'})`; the agent handles blindness (sentinel frame, §11).
   - **Mic refused** → `onError('mic_required')`, stop (a voice agent needs a mic).
4. Attach the **agent's** audio track to an `<audio autoplay>`; attach the **local** camera to a muted `<video>` preview in `target`.
5. **Tool bridge:** on `tool_call` data messages, run the matching `handler`, reply with `tool_result` (§12).
6. **Reconnect:** rely on LiveKit auto-reconnect; map `Reconnecting/Reconnected/Disconnected` to `onState`.
7. `stop()` → unpublish, disconnect, release media, fire `onState('ended')`.

### 14.3 Kept hidden
Room lifecycle, track publication, resampling, reconnect, the entire tool round-trip. The developer sees `create/mount/stop` + callbacks.

---

## 15. Task 2 — video-KYC, built entirely on the SDK

Nothing here reaches past the SDK. KYC = a prompt + tools + a little pure verification logic the developer owns.

### 15.1 `kyc/schema.py` — the structured result
Pydantic. Final result:
```json
{
  "decision": "pass | fail | needs_review",
  "checks": {
    "card_read":     { "status": "pass|fail|unclear", "confidence": 0.0, "reasons": [] },
    "hologram":      { "status": "pass|fail|unclear", "confidence": 0.0, "reasons": [] },
    "face_liveness": { "status": "pass|fail|unclear", "confidence": 0.0, "reasons": [] },
    "name_match":    { "status": "pass|fail|unclear", "confidence": 0.0, "reasons": [] }
  },
  "extracted": { "name": "", "pan": "", "dob": "" },
  "session_id": "sess_...",
  "timestamp": "ISO-8601",
  "notes": "honest caveats, e.g. liveness heuristic"
}
```

### 15.2 `kyc/verify.py` — pure, unit-tested helpers (the developer's own logic)
- **PAN validate:** regex `^[A-Z]{5}[0-9]{4}[A-Z]$`; 4th char = holder type (`P`=individual). Normalize DOB.
- **Name match:** normalize (uppercase, strip honorifics/punctuation, collapse spaces) + token-set/Levenshtein ratio; `match(card_name, spoken_name, threshold=0.82) -> {match, score}`.
- **Decision policy:** `decide(checks)` — `pass` only if `card_read=pass` AND `name_match=pass` AND both liveness checks `pass`; `fail` if `card_read=fail` OR `name_match=fail`; else `needs_review`. Explicit truth table, unit-tested.

### 15.3 `kyc/kyc-config.js` — the whole "KYC app" (prompt + tools)
- **The prompt** encodes the step machine in plain English (greet → show card → tilt → liveness → say name → result), instructing the agent to **`look`** at each visual step and to **`submitResult`** at the end. The vision judgements (does a card show? does the hologram shift across the tilt burst? did the instructed motion occur?) are done by the vision LLM from the frames `look` injects.
- **Tools:**
  - `submitResult(result)` → browser handler: POST to the dev's endpoint (which the demo forwards to `/kyc-result`), then render the results panel. This is the structured output the assignment asks for.
  - (Optional) `validatePan(pan)` → a client tool that runs the regex in-page and returns validity, demonstrating a developer client-tool with real logic.
- **Honest liveness note (goes in the prompt's notes + README):** hologram = LLM judging specular shift across a tilt burst; face = LLM judging a challenge motion. Both are heuristic and defeatable by a good video/print. Documented as weak; real fix in §19.

### 15.4 `kyc/index.html` + `kyc/server.py`
- `server.py`: a ~5-line proxy exposing `POST /session` (forwards to the broker with the demo platform key) and `POST /kyc-result` (forwards to the broker). Models the real key-hiding pattern.
- `index.html`: mounts `RumikAgent` with the KYC config; shows the live camera preview and, on `submitResult`, a simple panel (decision + per-check reasons + extracted fields). Styling minimal.

### 15.5 `FINDINGS.md` (assignment asks for it)
A running honesty log: every place the SDK felt awkward to build KYC on — e.g. "needed a `look(motion=true)` burst the generic demo didn't exercise; wanted a way to force a look rather than relying on the LLM to call it; per-turn look vs burst are two code paths." Honesty over polish.

---

## 16. Failure-handling matrix (the assignment calls these out)

| Failure | Detection | Behavior |
|---|---|---|
| **Camera refused / none** | no video track / sampler has no frame | agent continues audio-only, says it can't see; KYC → `needs_review` with reason |
| **Mic refused** | `getUserMedia` mic error | SDK `onError('mic_required')`, stop |
| **Network drop** | LiveKit `Reconnecting` | SDK shows `reconnecting`; ICE restart auto-recovers; pipeline resumes |
| **LLM/vision slow** | per-call timeout (~12 s) | agent speaks a filler ("one moment…"), retry once; else apologize + `needs_review` |
| **STT empty/garbled** | empty transcript | agent re-asks once |
| **Tool handler timeout** | no `tool_result` in ~15 s | bridge returns `{error:'tool_timeout'}`, agent apologizes |
| **Rumik 429 / 402 / gen error** | HTTP/WS status | backoff+retry / spoken apology+end / retry+apologize |
| **No usable card after retries** | 3 unusable read looks | `card_read=fail` → overall `fail` |
| **Agent subprocess dies** | broker reaper sees non-zero exit | mark session dead; browser gets `Disconnected` → `ended` |
| **Sampling budget hit** | `frames_this_minute > cap` | `look` reuses last frame + notes budget; no runaway cost |

---

## 17. Testing plan

Write a test for each unit as it is built; run whole-system checks at natural checkpoints (not a slow micro-loop).

### 17.1 Unit (fast, no network) — `pytest`
- `test_frame_sampler.py` — synthetic frames + fake clock: `max_fps` throttling drops frames; `latest` is newest; `look` single vs burst returns the right count within the window; budget cap kicks in; "no frame" sentinel; downscale respects `image_max_side`.
- `test_tool_bridge.py` — a fake data channel: `tool_call` emitted with a `call_id`; matching `tool_result` resolves; timeout path returns `{error}`; developer param shape → JSON-Schema translation.
- `test_tone_tags.py` — `sanitize` adds a default tag, strips markdown, quotes digit strings.
- `test_accounts.py` — signup creates an account + issues a key; mint returns plaintext once and stores only the sha256 hash; validate accepts good, rejects unknown/revoked. (Runs against a test Postgres or a transaction-rolled-back Neon connection.)
- `test_pan_and_name.py` — PAN regex accept/reject; holder-type; name normalization + match scores vs threshold.
- `test_kyc_schema_and_decision.py` — schema validation; `decide()` truth table for every check combination.
- `test_livekit_tokens.py` — decode minted JWT; assert identity, room grant, publish/subscribe/data flags, TTL.

### 17.2 Component integration (some network) — `pytest -m integration`
- `test_rumik_tts_live.py` — hit **live** Rumik TTS with the real key; assert non-trivial PCM/WAV bytes. Real evidence the voice works.
- `test_broker_session.py` — spin the broker (httpx `AsyncClient`), inject a fake `agent_runner`; assert `/session` returns a correctly-scoped, decodable token; `401` on missing/invalid key; `429` at the cap.

### 17.3 Whole-system checkpoints
- **A — talking spine:** `test_agent_smoke.py` — a headless LiveKit client joins as `user`, plays a short PCM utterance, asserts the agent publishes audio back within N s. (Where headless audio-in is impractical, fall back to a documented manual check.)
- **B — eyes:** `test_vision_smoke.py` — publish a **static image** as the video track, ask "what do you see?", assert the reply references the image.
- **C — KYC path:** run the KYC agent against `fixtures/sample_pan.jpg` + `fixtures/tilt_frames/` fed as the video source; assert a well-formed `KYCResult` is produced and logged (validates read + decision **without** a live human). Then a **manual human run** → this is also the screen recording.

### 17.4 Make targets
`make test` (unit), `make itest` (unit + live Rumik + broker), `make check` (whole-system), `make demo` (bring up broker + open pages).

---

## 18. Build sequence (milestones)

One product, built spine-first, tested as we go.

- **M0 — de-risk the voice (½ day).** Stand up `pipecat_rumik` in isolation + `test_rumik_tts_live.py`. Confirm the exact `Settings`/gateway signature. (Reuses the prior prototype's known-good imports.)
- **M1 — talking spine (Day 1).** `config` → `db` + `accounts` (Neon signup + keys, +test) → `web/index.html` "get your key" → `livekit_tokens` (+test) → `broker /session` (+test) → `pipeline` (STT→LLM→Rumik TTS, audio only) → `agent_runner` → `rumik-agent.js` + `examples/hello-agent`. Point at LiveKit Cloud. **Checkpoint A.**
- **M2 — eyes + tools (Day 2).** `frame_sampler` (+test) + `look` tool + video-in on the transport + SDK camera publish → tune sampling. Then `tool_bridge` (+test) + the browser tool round-trip. **Checkpoint B.**
- **M3 — KYC + docs + ship (Day 3).** `kyc/schema` + `kyc/verify` (+tests) → `kyc-config.js` (prompt + `submitResult`) → `kyc/index.html` + `server.py` → **Checkpoint C** (fixtures) → **manual human run + screen recording**. Write `web/docs/`, then README, FINDINGS, NEXT-WEEK; finalize PROMPTLOG. Optionally deploy to a persistent host.

Throughout: append every prompt to `PROMPTLOG.md` in order; keep `FINDINGS.md` updated whenever the SDK is awkward to build on.

---

## 19. Honesty ledger (goes into the README — the assignment rewards this)
- **Liveness is weak.** Hologram = an LLM judging specular shift across a tilt burst; face = an LLM judging a challenge motion. Both defeatable (a good video replay, a high-res tilting print). **Real fix (next week):** dedicated liveness (active flash/color-reflection challenge with pixel analysis, device-sensor depth, or a purpose-built liveness model), plus PAN verification against an authoritative source, not just format.
- **OCR via gpt-4o vision** is "good enough for a demo"; a real deployment might use a dedicated OCR for the read step — a one-line model swap (`LLM_MODEL`).
- **Platform onboarding is dev-grade:** Neon Postgres-backed accounts/keys, but email-only (no password / no email verification yet), seeded demo key, permissive CORS. Demonstrates the model; not production multi-tenant auth.
- **Single-node worker spawning** (subprocess per session); LiveKit's own agent dispatch is the scaled alternative for deployment.

---

## 20. Deliverables mapping (from the assignment)
| Required | Produced by |
|---|---|
| a repo | `rumik2222/` |
| README: run it / use the SDK / what's next | `README.md` (+ `NEXT-WEEK.md`) |
| 3–5 min screen recording of KYC working | manual run in M3 (Checkpoint C → live human) |
| note on what you'd change given another week | `NEXT-WEEK.md` (+ §19) |
| **prompt log** — every prompt, in order, one file | `PROMPTLOG.md` (maintained from the start) |
| "if the layer is awkward, write it down" | `FINDINGS.md` |
| developer docs (supports the #1 DX bar) | `web/docs/` (also backs the README) |

---

## 21. Assumptions & VERIFY-AT-BUILD (flagged honestly)
1. **Pipecat symbol names** (LiveKit transport, STT/LLM services, TTS + function-calling APIs, video-input frame classes) are confirmed against the pinned installed version at build start. The prior prototype confirmed the core import paths on one recent version; re-verify.
2. **`pipecat_rumik` signature** (`Settings` fields, `gateway_url`) confirmed against the installed package.
3. **OpenAI covers LLM + vision + STT**; **Rumik** covers TTS; **LiveKit Cloud** covers transport (creds already exist).
4. **India PAN** card (name / PAN / DOB / hologram), per the assignment's "pan card."
5. **Headless audio/vision e2e** may be partially manual where WebRTC makes full automation impractical — documented, with manual steps written down.
6. Concurrency kept under Rumik's cap via `MAX_CONCURRENT_SESSIONS`.
7. The demo pages call `/session` from a tiny dev-server proxy to model the real key-hiding pattern (in production the developer's own backend does this).
8. **Multi-tenancy is DB + room-scoping, not per-dev keys** (§4A): one upstream key-set serves all developers; isolation is per-room tokens + per-session workers + account-tagged rows.
9. **Deployment** targets a persistent host (Render/Fly/Railway/VM) for the long-running workers; LiveKit Cloud + Neon are already hosted; the same `.env` becomes deployment secrets.
