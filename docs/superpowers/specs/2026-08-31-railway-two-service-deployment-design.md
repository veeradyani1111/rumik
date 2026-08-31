# Railway Two-Service Deployment Design

## Goal

Publish the same reviewed source commit to `veeradyani1111/rumik` and
`veeradyani222/rumik`, then deploy the SDK platform and KYC demo as two
independent services in one Railway project. The KYC service must call the SDK
through the SDK's public HTTPS URL.

## Source and Git layout

- The current repository remains a monorepo containing both deployable apps.
- All tracked working-tree changes are reviewed, tested, and committed before
  either remote is updated. The root `.env` stays ignored and is never staged.
- The same commit is pushed to the `main` branch of both GitHub repositories.
- The authenticated GitHub account currently has admin access to
  `veeradyani222/rumik` but only read access to `veeradyani1111/rumik`. The
  second push is not considered complete until credentials with write access
  are available or collaborator access is granted.

## Railway architecture

One Railway project contains two services:

- `rumik-sdk` runs `sdk.server.app:app`, owns account and session APIs, starts
  voice-agent workers, serves SDK assets and documentation, and stores KYC
  results.
- `rumik-kyc` runs `kyc.server:app`, serves the KYC UI and browser SDK assets,
  and proxies `/session` and `/kyc-result` to `rumik-sdk`.

Both services bind to `0.0.0.0` on Railway's injected `PORT`. Both receive a
Railway-provided public HTTPS domain. `rumik-kyc` uses a Railway reference
variable equivalent to
`PLATFORM_URL=https://${{rumik-sdk.RAILWAY_PUBLIC_DOMAIN}}`; it does not use
Railway private networking.

## Secret boundary

`rumik-sdk` receives the platform-only settings from the local `.env`:

- OpenAI and Rumik credentials and model configuration.
- LiveKit URL, API key, API secret, and room defaults.
- Neon `DATABASE_URL`.
- `DEMO_PLATFORM_KEY`, vision sampling policy, token lifetime, and concurrency
  limits.

`rumik-kyc` receives only:

- `PLATFORM_URL`, defined from the SDK's Railway public domain.
- `DEMO_PLATFORM_KEY`, matching the value used by `rumik-sdk` to seed the demo
  account.

Secret values are transferred directly from `.env` to Railway without being
printed, written to deployment files, added to shell history, or committed.

## Deployment configuration

- Add explicit production start commands for the SDK and KYC services.
- Add a lightweight KYC health endpoint so Railway and the deployment verifier
  can distinguish a running proxy from a static-page-only response.
- Configure `/health` as the health-check path for each service.
- Connect both services to `veeradyani1111/rumik` on `main`, the repository
  available to the Railway workspace's GitHub integration. Railway builds the
  exact commit that was first pushed to both GitHub repositories.
- Use Railway CLI to create and configure the project and services, connect the
  GitHub sources, and inspect deployment state.
- Record the repeatable service commands and variable ownership in repository
  documentation without recording secret values.

## Request flow

1. A browser opens the public `rumik-kyc` URL.
2. Browser requests for `/session` and `/kyc-result` go to the KYC service on
   the same origin.
3. The KYC server adds `Authorization: Bearer <DEMO_PLATFORM_KEY>` and forwards
   the request to the public `rumik-sdk` URL.
4. The SDK validates the platform key, talks to LiveKit and model providers,
   and returns only the session response or KYC storage result.
5. No long-lived platform or provider credential is sent to browser code.

## Error handling

- KYC returns a stable HTTP 503 response when `DEMO_PLATFORM_KEY` is absent.
- KYC returns a stable HTTP 502 response when the SDK is unreachable, times
  out, or returns a response that cannot be decoded as JSON. Provider errors
  must not produce an unhandled KYC server exception.
- Valid SDK JSON responses preserve their upstream status code and JSON body.
- Railway deployments are not considered successful until both health
  endpoints report HTTP 200 and the public KYC page loads.

## Verification

- Add focused KYC proxy tests for health, missing configuration, successful
  forwarding, and unreachable or malformed upstream responses.
- Run the complete offline Python and browser test suites before committing.
- Inspect the staged file list and confirm `.env` is absent before each push.
- Verify both remote `main` branches resolve to the same commit SHA.
- Verify Railway variables by name and service scope without retrieving or
  displaying secret values.
- Verify both public `/health` endpoints and the public KYC root URL after the
  deployments reach a successful state.

## Rollback

Each Railway service remains independently deployable. If one deployment
fails, its logs and deployment state are inspected while the other service is
left intact. A rollback redeploys the last known-good Git commit to only the
affected service; secret values are not changed unless configuration itself is
the diagnosed cause.

## Out of scope

- Railway private networking.
- Splitting the monorepo into separate source repositories or divergent
  branches.
- Custom domains, horizontal scaling, or production-grade distributed worker
  orchestration.
