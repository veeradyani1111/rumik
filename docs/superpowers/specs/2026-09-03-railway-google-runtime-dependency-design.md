# Railway Google Runtime Dependency Design

## Goal

Ensure Railway workers can import the Gemini-backed LLM and STT modules and join their LiveKit room.

## Design

Add Pipecat's `google` optional dependency alongside the existing provider extras in `requirements.txt`. Keep provider selection and worker startup behavior unchanged. Add a focused deployment-dependency test that parses the pinned Pipecat requirement and requires the `google` extra, preventing local environments with manually installed packages from hiding the omission again.

## Verification

Run the focused regression test, the complete Python and browser suites, deploy the same commit through both remote `main` branches, and run the production join probe. Success means an agent participant appears within 10 seconds and Railway logs no `google.genai` import failure.
