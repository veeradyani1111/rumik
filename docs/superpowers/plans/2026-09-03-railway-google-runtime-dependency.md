# Railway Google Runtime Dependency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install the Google runtime required by Railway agent workers so they can join LiveKit rooms.

**Architecture:** Keep the existing worker and provider selection unchanged. Correct the clean-deployment dependency declaration and protect it with a static regression test that does not depend on packages already installed on a developer machine.

**Tech Stack:** Python 3.13, pytest, pip requirements, Railway

---

### Task 1: Protect the deployment dependency

**Files:**
- Create: `tests/unit/test_deployment_dependencies.py`
- Modify: `requirements.txt:3`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path


def test_pipecat_installs_google_runtime_for_gemini_workers() -> None:
    requirements = Path("requirements.txt").read_text(encoding="utf-8").splitlines()
    pipecat = next(line for line in requirements if line.startswith("pipecat-ai["))
    extras = set(pipecat.split("[", 1)[1].split("]", 1)[0].split(","))

    assert "google" in extras
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_deployment_dependencies.py -q`
Expected: FAIL because the Pipecat extras do not include `google`.

- [ ] **Step 3: Add the minimal dependency**

Change the Pipecat requirement to:

```text
pipecat-ai[livekit,openai,silero,deepgram,sarvam,google]==1.3.0
```

- [ ] **Step 4: Run focused and complete verification**

Run: `python -m pytest tests/unit/test_deployment_dependencies.py -q`
Expected: 1 passed.

Run: `python -m pytest`
Expected: all offline Python tests pass, with only the credential-dependent live test skipped.

Run: `npm test`
Expected: all browser tests pass.

- [ ] **Step 5: Commit and publish**

```text
git add requirements.txt tests/unit/test_deployment_dependencies.py docs/superpowers
git commit -m "fix: install Gemini runtime on Railway"
git push github-1111 HEAD:main
git push github-222 HEAD:main
```

- [ ] **Step 6: Verify production**

Wait for both Railway services to deploy the new commit, then run the production LiveKit join probe. Expected: the remote agent participant appears within 10 seconds and recent SDK logs contain no `google.genai` import error.
