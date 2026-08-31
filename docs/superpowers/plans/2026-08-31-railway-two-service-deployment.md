# Railway Two-Service Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mirror one tested commit to both GitHub repositories and deploy the SDK and KYC as separate, publicly connected services in one Railway project.

**Architecture:** The monorepo stays intact and Railway tracks `veeradyani1111/rumik` on `main` for both services. `rumik-sdk` owns provider and database credentials; `rumik-kyc` receives only the SDK's public URL and the shared demo platform key, and forwards browser requests server-side.

**Tech Stack:** Python 3.13, FastAPI, httpx, pytest, Node test runner, GitHub CLI/Git, Railway CLI 5.45.x, Railway Railpack.

---

## File map

- `kyc/server.py`: construct the KYC app from explicit configuration, expose health, and convert upstream failures into stable JSON responses.
- `tests/unit/test_kyc_server.py`: cover health, secret absence, forwarding, and upstream failure behavior.
- `.python-version`: pin the Python minor version used by Railway Railpack.
- `README.md`: document the two-service Railway layout, start commands, public URL, and variable ownership.
- `PROMPTLOG.md`: append the deployment requests without credentials or injected environment context.
- `docs/superpowers/specs/2026-08-31-railway-two-service-deployment-design.md`: retain the approved design and GitHub source decision.

### Task 1: Verify and preserve the existing working set

**Files:**
- Modify: `PROMPTLOG.md`
- Modify: `examples/hello-agent/server.py`
- Modify: `kyc/index.html`
- Modify: `kyc/kyc-config.js`
- Modify: `kyc/schema.py`
- Modify: `kyc/server.py`
- Modify: `kyc/verify.py`
- Modify: `sdk/browser/livekit-bridge.js`
- Modify: `sdk/browser/rumik-agent.css`
- Modify: `sdk/browser/rumik-agent.js`
- Modify: `sdk/server/agent_worker.py`
- Modify: `sdk/server/broker.py`
- Create: `sdk/server/observability.py`
- Modify: `sdk/server/pipeline.py`
- Modify: `tests/browser/kyc-config.test.js`
- Modify: `tests/integration/test_broker_session.py`
- Modify: `tests/unit/test_kyc_schema_and_decision.py`
- Modify: `web/docs/docs.css`
- Modify: `web/index.html`

- [ ] **Step 1: Check the existing diff for whitespace and secret mistakes**

Run:

```powershell
git diff --check
git check-ignore -v .env
git diff --name-only
```

Expected: `git diff --check` exits 0, `.env` is matched by `.gitignore`, and the changed-file list contains no generated KYC log or secret file.

- [ ] **Step 2: Run the full existing offline suite**

Run:

```powershell
.venv\Scripts\python.exe -m pytest -q
npm test
```

Expected: all Python and browser tests pass. Any failure must be diagnosed before continuing; do not commit a known failure.

- [ ] **Step 3: Commit the verified existing changes**

Run:

```powershell
git add -- PROMPTLOG.md examples/hello-agent/server.py kyc/index.html kyc/kyc-config.js kyc/schema.py kyc/server.py kyc/verify.py sdk/browser/livekit-bridge.js sdk/browser/rumik-agent.css sdk/browser/rumik-agent.js sdk/server/agent_worker.py sdk/server/broker.py sdk/server/observability.py sdk/server/pipeline.py tests/browser/kyc-config.test.js tests/integration/test_broker_session.py tests/unit/test_kyc_schema_and_decision.py web/docs/docs.css web/index.html
git diff --cached --name-only
git commit -m "feat: refine realtime KYC experience"
```

Expected: only the listed product and test files are committed; `.env` remains untracked and ignored.

### Task 2: Make the KYC proxy deployment-safe

**Files:**
- Create: `tests/unit/test_kyc_server.py`
- Modify: `kyc/server.py`

- [ ] **Step 1: Write failing proxy contract tests**

Create `tests/unit/test_kyc_server.py`:

```python
import httpx
import pytest
from httpx import ASGITransport, AsyncClient, MockTransport, Response

from kyc.server import create_app


def _client_for(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_health_reports_configuration_without_exposing_it() -> None:
    app = create_app(platform_url="https://sdk.example", platform_key="rk_live_test")

    async with _client_for(app) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "platform_configured": True}


@pytest.mark.asyncio
async def test_missing_platform_key_returns_stable_503() -> None:
    app = create_app(platform_url="https://sdk.example", platform_key="")

    async with _client_for(app) as client:
        response = await client.post("/session", json={"prompt": "hello"})

    assert response.status_code == 503
    assert response.json()["code"] == "DEMO_KEY_MISSING"


@pytest.mark.asyncio
async def test_proxy_forwards_to_public_platform_url_with_bearer_key() -> None:
    def upstream(request: httpx.Request) -> Response:
        assert str(request.url) == "https://sdk.example/session"
        assert request.headers["authorization"] == "Bearer rk_live_test"
        return Response(201, json={"room": "session-room"})

    def client_factory(**kwargs) -> AsyncClient:
        return AsyncClient(transport=MockTransport(upstream), **kwargs)

    app = create_app(
        platform_url="https://sdk.example/",
        platform_key="rk_live_test",
        client_factory=client_factory,
    )

    async with _client_for(app) as client:
        response = await client.post("/session", json={"prompt": "hello"})

    assert response.status_code == 201
    assert response.json() == {"room": "session-room"}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["connect", "invalid-json"])
async def test_proxy_returns_stable_502_for_unusable_upstream(failure: str) -> None:
    def upstream(request: httpx.Request) -> Response:
        if failure == "connect":
            raise httpx.ConnectError("unreachable", request=request)
        return Response(502, text="not-json")

    def client_factory(**kwargs) -> AsyncClient:
        return AsyncClient(transport=MockTransport(upstream), **kwargs)

    app = create_app(
        platform_url="https://sdk.example",
        platform_key="rk_live_test",
        client_factory=client_factory,
    )

    async with _client_for(app) as client:
        response = await client.post("/session", json={"prompt": "hello"})

    assert response.status_code == 502
    assert response.json() == {
        "code": "PLATFORM_UNAVAILABLE",
        "message": "The Rumik platform is temporarily unavailable.",
    }
```

- [ ] **Step 2: Run the new tests and verify the expected failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_kyc_server.py -q
```

Expected: collection fails because `kyc.server.create_app` does not exist.

- [ ] **Step 3: Implement the app factory, health route, and stable forwarding errors**

Replace `kyc/server.py` with:

```python
from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles


ROOT = Path(__file__).resolve().parent
SDK_ROOT = ROOT.parent / "sdk" / "browser"
ClientFactory = Callable[..., httpx.AsyncClient]

load_dotenv(ROOT.parent / ".env")


def create_app(
    *,
    platform_url: str | None = None,
    platform_key: str | None = None,
    client_factory: ClientFactory = httpx.AsyncClient,
) -> FastAPI:
    resolved_url = (
        platform_url if platform_url is not None else os.getenv("PLATFORM_URL", "http://127.0.0.1:8000")
    ).rstrip("/")
    resolved_key = platform_key if platform_key is not None else os.getenv("DEMO_PLATFORM_KEY", "")

    app = FastAPI(title="Rumik KYC Demo")

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "platform_configured": bool(resolved_url and resolved_key),
        }

    async def forward(path: str, request: Request) -> JSONResponse:
        if not resolved_key:
            return JSONResponse(
                status_code=503,
                content={
                    "code": "DEMO_KEY_MISSING",
                    "message": "Set DEMO_PLATFORM_KEY on the demo server.",
                },
            )
        try:
            async with client_factory(timeout=30) as client:
                response = await client.post(
                    f"{resolved_url}{path}",
                    content=await request.body(),
                    headers={
                        "Authorization": f"Bearer {resolved_key}",
                        "Content-Type": "application/json",
                    },
                )
            content = response.json()
        except (httpx.HTTPError, ValueError):
            return JSONResponse(
                status_code=502,
                content={
                    "code": "PLATFORM_UNAVAILABLE",
                    "message": "The Rumik platform is temporarily unavailable.",
                },
            )
        return JSONResponse(status_code=response.status_code, content=content)

    @app.post("/session")
    async def session(request: Request):
        return await forward("/session", request)

    @app.post("/kyc-result")
    async def kyc_result(request: Request):
        return await forward("/kyc-result", request)

    app.mount("/sdk", StaticFiles(directory=SDK_ROOT), name="sdk")
    app.mount("/", StaticFiles(directory=ROOT, html=True), name="kyc")
    return app


app = create_app()
```

- [ ] **Step 4: Run the focused tests and verify they pass**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_kyc_server.py -q
```

Expected: five test cases pass.

- [ ] **Step 5: Run related KYC and broker tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_kyc_server.py tests/unit/test_kyc_schema_and_decision.py tests/integration/test_broker_session.py -q
npm test
```

Expected: all selected Python cases and browser tests pass.

- [ ] **Step 6: Commit the proxy behavior**

Run:

```powershell
git add -- kyc/server.py tests/unit/test_kyc_server.py
git commit -m "fix: harden KYC deployment proxy"
```

Expected: one focused implementation-and-tests commit.

### Task 3: Pin and document the production runtime

**Files:**
- Create: `.python-version`
- Modify: `README.md`
- Modify: `PROMPTLOG.md`

- [ ] **Step 1: Pin Railpack to Python 3.13**

Create `.python-version` containing exactly:

```text
3.13
```

- [ ] **Step 2: Document the Railway service contract**

Append a `Deploy on Railway` section to `README.md` that states:

```markdown
## Deploy on Railway

Deploy this monorepo as two services in one Railway project. Both services
track `veeradyani1111/rumik` on `main`.

| Service | Start command | Health check | Variables |
| --- | --- | --- | --- |
| `rumik-sdk` | `python -m uvicorn sdk.server.app:app --host 0.0.0.0 --port $PORT` | `/health` | Provider, LiveKit, Neon, model, sampling, broker, and `DEMO_PLATFORM_KEY` settings from `.env` |
| `rumik-kyc` | `python -m uvicorn kyc.server:app --host 0.0.0.0 --port $PORT` | `/health` | Only `PLATFORM_URL` and `DEMO_PLATFORM_KEY` |

Give both services Railway public domains. Set the KYC `PLATFORM_URL` to
`https://${{rumik-sdk.RAILWAY_PUBLIC_DOMAIN}}`; the KYC proxy deliberately
calls the SDK through its public HTTPS URL. Do not upload the root `.env` or
expose either long-lived key to browser JavaScript.
```

- [ ] **Step 3: Append the deployment request to the prompt log**

Append to `PROMPTLOG.md`:

```markdown
## 018 — 2026-08-31

> Push all code to `veeradyani1111/rumik` and `veeradyani222/rumik`. Deploy the
> SDK and KYC separately in one Railway project, with KYC calling the SDK by its
> public API URL. Railway tracks the `veeradyani1111` repository.
```

- [ ] **Step 4: Validate and commit runtime documentation**

Run:

```powershell
git diff --check
git check-ignore -v .env
.venv\Scripts\python.exe -m pytest -q
npm test
git add -- .python-version README.md PROMPTLOG.md
git commit -m "docs: add Railway production deployment"
```

Expected: all tests pass, `.env` remains ignored, and the runtime/documentation commit succeeds.

### Task 4: Publish the identical `main` commit to both GitHub repositories

**Files:**
- No repository file changes.

- [ ] **Step 1: Verify the local release commit and tree**

Run:

```powershell
git status --short --branch
git log -5 --oneline
git ls-files .env
```

Expected: the working tree is clean, `git ls-files .env` prints nothing, and HEAD includes the proxy, runtime, and design commits.

- [ ] **Step 2: Ensure GitHub credentials can write both repositories**

Run:

```powershell
gh auth status
gh repo view veeradyani1111/rumik --json viewerPermission
gh repo view veeradyani222/rumik --json viewerPermission
```

Expected: both permissions are `WRITE`, `MAINTAIN`, or `ADMIN`. If `veeradyani1111/rumik` is still `READ`, authenticate the owner with `gh auth login --hostname github.com --git-protocol https --web` or grant `veeradyani222` collaborator write access, then repeat this check.

- [ ] **Step 3: Configure explicit remotes**

Run:

```powershell
git remote add github-1111 https://github.com/veeradyani1111/rumik.git
git remote add github-222 https://github.com/veeradyani222/rumik.git
git remote -v
```

Expected: each fetch/push URL names the intended repository. If a remote already exists, use `git remote set-url` for that exact remote instead of adding a duplicate.

- [ ] **Step 4: Push the Railway-tracked repository first, then its mirror**

Run:

```powershell
git push github-1111 HEAD:main
git push github-222 HEAD:main
```

Expected: both pushes succeed without force.

- [ ] **Step 5: Verify remote commit equality**

Run:

```powershell
$localSha = git rev-parse HEAD
$firstSha = (git ls-remote github-1111 refs/heads/main).Split()[0]
$secondSha = (git ls-remote github-222 refs/heads/main).Split()[0]
@($localSha, $firstSha, $secondSha) | Select-Object -Unique
```

Expected: exactly one SHA is printed.

### Task 5: Create and configure the Railway project

**Files:**
- No repository file changes; Railway project state is changed.

- [ ] **Step 1: Create and link the project**

Run:

```powershell
npx -y @railway/cli@5.45.10 init --name rumik --workspace f31ac229-9c5c-4e5a-97ee-3f85b1c17097 --json
npx -y @railway/cli@5.45.10 status
```

Expected: a new `rumik` project is linked in the `veeradyani1111's Projects` workspace with a production environment.

- [ ] **Step 2: Create empty services before attaching source**

Run:

```powershell
npx -y @railway/cli@5.45.10 add --service rumik-sdk --json
npx -y @railway/cli@5.45.10 add --service rumik-kyc --json
```

Expected: two distinct service IDs are returned.

- [ ] **Step 3: Configure start commands and health checks**

Run:

```powershell
npx -y @railway/cli@5.45.10 environment edit --service-config rumik-sdk deploy.startCommand 'python -m uvicorn sdk.server.app:app --host 0.0.0.0 --port $PORT' --service-config rumik-sdk deploy.healthcheckPath /health --service-config rumik-sdk deploy.healthcheckTimeout 300 --message 'Configure SDK runtime' --json
npx -y @railway/cli@5.45.10 environment edit --service-config rumik-kyc deploy.startCommand 'python -m uvicorn kyc.server:app --host 0.0.0.0 --port $PORT' --service-config rumik-kyc deploy.healthcheckPath /health --service-config rumik-kyc deploy.healthcheckTimeout 300 --message 'Configure KYC runtime' --json
```

Expected: both service configurations record the explicit Uvicorn command and `/health` check.

- [ ] **Step 4: Transfer SDK variables without exposing values in arguments**

Run an in-memory PowerShell loop that parses `.env` and pipes each selected value to Railway CLI `variable set NAME --stdin --skip-deploys --service rumik-sdk`. The exact allowlist is:

```text
OPENAI_API_KEY
RUMIK_API_KEY
RUMIK_GATEWAY_URL
LIVEKIT_URL
LIVEKIT_API_KEY
LIVEKIT_API_SECRET
LLM_MODEL
STT_MODEL
RUMIK_TTS_MODEL
RUMIK_TTS_SPEAKER
DATABASE_URL
DEMO_PLATFORM_KEY
VISION_MAX_FPS
IMAGE_MAX_SIDE
JPEG_QUALITY
BURST_COUNT
BURST_WINDOW_MS
MAX_FRAMES_PER_MIN
SESSION_TOKEN_TTL_SEC
MAX_CONCURRENT_SESSIONS
```

Expected: every allowlisted key exists and is non-empty before transfer; the loop aborts on any missing value or failed CLI call. Do not use `railway variable list --json` or `--kv` in visible output because those forms include raw values.

- [ ] **Step 5: Configure only the two KYC variables**

Pipe `DEMO_PLATFORM_KEY` from the parsed `.env` to `variable set DEMO_PLATFORM_KEY --stdin --skip-deploys --service rumik-kyc`, then run:

```powershell
npx -y @railway/cli@5.45.10 variable set 'PLATFORM_URL=https://${{rumik-sdk.RAILWAY_PUBLIC_DOMAIN}}' --skip-deploys --service rumik-kyc --json
```

Expected: KYC has no OpenAI, Rumik, LiveKit, or database variables.

- [ ] **Step 6: Connect both service sources to the Railway-tracked repository**

Run:

```powershell
npx -y @railway/cli@5.45.10 service source connect --repo veeradyani1111/rumik --branch main --service rumik-sdk --json
npx -y @railway/cli@5.45.10 service source connect --repo veeradyani1111/rumik --branch main --service rumik-kyc --json
```

Expected: both services report `veeradyani1111/rumik` and `main` as their source.

### Task 6: Deploy and verify both public services

**Files:**
- No repository file changes; Railway deployment and domain state is changed.

- [ ] **Step 1: Wait for both GitHub-source deployments**

Run these commands every 10 seconds, stopping when both report success or either reports failure:

```powershell
npx -y @railway/cli@5.45.10 deployment list --service rumik-sdk --limit 1 --json
npx -y @railway/cli@5.45.10 deployment list --service rumik-kyc --limit 1 --json
```

Expected: both latest deployments reach `SUCCESS`. On failure, inspect only the affected service with `railway logs --build --latest --lines 200` and `railway logs --deployment --latest --lines 200`, fix the diagnosed cause, retest, commit, mirror the new commit, and redeploy.

- [ ] **Step 2: Generate public domains**

Run:

```powershell
npx -y @railway/cli@5.45.10 domain --service rumik-sdk --json
npx -y @railway/cli@5.45.10 domain --service rumik-kyc --json
```

Expected: each command returns a different Railway-provided public hostname.

- [ ] **Step 3: Verify public health and the KYC page**

Resolve the two hostnames using `railway domain list --service rumik-sdk --json` and `railway domain list --service rumik-kyc --json`, assign them to `$sdkDomain` and `$kycDomain`, then run:

```powershell
Invoke-RestMethod -Uri "https://$sdkDomain/health"
Invoke-RestMethod -Uri "https://$kycDomain/health"
$response = Invoke-WebRequest -Uri "https://$kycDomain/"
$response.StatusCode
```

Expected: SDK health returns `status=ok`, LiveKit and Rumik flags are true; KYC health returns `status=ok` and `platform_configured=true`; the KYC root returns HTTP 200.

- [ ] **Step 4: Verify variable names and source configuration without printing values**

Capture Railway variable JSON inside PowerShell, parse it in memory, and print only sorted property names. Confirm the SDK names match the Task 5 allowlist plus Railway-provided variables, and KYC user-defined names are exactly `DEMO_PLATFORM_KEY` and `PLATFORM_URL`. Run `railway service status --json` and confirm both sources point to `veeradyani1111/rumik` on `main`.

- [ ] **Step 5: Report immutable deployment evidence**

Record the shared Git commit SHA, both GitHub repository URLs, Railway project name/ID, service deployment IDs, and both public HTTPS URLs. Do not report or print secret values.
