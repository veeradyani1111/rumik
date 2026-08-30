# Credential Boundary Design

> **Status: superseded.** The user chose a single root `.env` because the whole repository will be deployed together. The retained boundary is behavioral: `kyc/server.py` reads only `PLATFORM_URL` and `DEMO_PLATFORM_KEY`; provider and database variables are consumed only by the platform code.

## Goal

Make the local demo match the platform's intended one-key developer experience. The KYC application must receive only its platform URL and platform API key. OpenAI, Rumik, LiveKit, and database credentials must remain exclusive to the platform process.

## Configuration boundary

- Root `.env` remains the platform operator configuration. It contains OpenAI, Rumik, LiveKit, Neon, model, sampling, and broker settings. `RUMIK_GATEWAY_URL` uses the documented base URL `https://silk-api.rumik.ai` without `/v1`.
- `kyc/.env` becomes the developer-demo configuration. It contains only `PLATFORM_URL` and `PLATFORM_API_KEY`.
- The browser receives neither file and no long-lived credential. The KYC proxy attaches `PLATFORM_API_KEY` when calling the platform. The platform returns only a short-lived, room-scoped LiveKit participant token to the browser.
- `DEMO_PLATFORM_KEY` may remain in the platform configuration solely to seed a matching local key hash. For the demo, its value must match `kyc/.env`'s `PLATFORM_API_KEY`.

## Runtime changes

- Rename the KYC proxy's environment input from `DEMO_PLATFORM_KEY` to `PLATFORM_API_KEY` and update its missing-key error.
- Add `kyc/.env.example` containing only the two developer-side variables.
- Create ignored `kyc/.env` with blank `PLATFORM_API_KEY` and the local platform URL.
- Start the platform with the root `.env`; start KYC with `--env-file kyc/.env`. Restart the currently running KYC supervisor so it no longer inherits the combined root file.
- Update README and Makefile instructions to show the split explicitly.

## Error handling

- If `PLATFORM_API_KEY` is absent, KYC proxy routes return HTTP 503 with `PLATFORM_KEY_MISSING` and a message naming `kyc/.env`.
- If the platform is unavailable or rejects the key, the proxy preserves the platform response status and body as it does today.

## Testing

- Add an isolated KYC proxy test proving a missing `PLATFORM_API_KEY` returns the stable 503 error.
- Add a forwarding test proving the proxy sends `Authorization: Bearer <platform key>` to the configured platform URL.
- Run the full Python and browser suites, syntax/compile checks, and manually verify the KYC page starts from `kyc/.env` without exposing or printing secrets.

## Out of scope

- Moving KYC into a separate repository or deployment.
- Giving each developer upstream provider credentials.
- Sending the platform key to browser JavaScript.
