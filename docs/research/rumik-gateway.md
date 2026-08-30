# Rumik gateway URL and credential boundary

Researched: 2026-08-30

## Conclusion

Set:

```dotenv
RUMIK_GATEWAY_URL=https://silk-api.rumik.ai
```

Do **not** include `/v1`. Rumik's official Pipecat integration page gives the
base URL exactly as `https://silk-api.rumik.ai`, and the official quickstart
builds `/v1/tts` on top of that base.

Sources:

- [Rumik's official Pipecat integration](https://docs.rumik.ai/pipecat)
- [Rumik's official quickstart](https://docs.rumik.ai/quickstart)
- [Rumik's official Pipecat + LiveKit cookbook](https://docs.rumik.ai/cookbook/voice-agent-pipecat-livekit)

## Why `/v1` must not be in the variable

`pipecat-rumik` treats `gateway_url` as a base URL. Its implementation removes
a trailing slash and appends `/v1/tts/ws-connect` for WebSocket setup or
`/v1/tts` for HTTP synthesis. Supplying a value ending in `/v1` would therefore
produce an invalid `/v1/v1/...` path.

Sources:

- [Official `pipecat-rumik` source: WebSocket URL construction](https://github.com/ira-rumik/pipecat-rumik/blob/3c12eb324172cf2df27c2d52f10b83510b0bf498/src/pipecat_rumik/services/rumik/tts.py#L322)
- [Official `pipecat-rumik` source: HTTP URL construction](https://github.com/ira-rumik/pipecat-rumik/blob/3c12eb324172cf2df27c2d52f10b83510b0bf498/src/pipecat_rumik/services/rumik/tts.py#L597)
- [Official PyPI release for the installed 0.1.4 package](https://pypi.org/project/pipecat-rumik/0.1.4/)

## Which process needs which credentials

The KYC app developer should need only the platform key. The upstream
credentials belong to the platform backend:

| Component | Credential | Why |
| --- | --- | --- |
| KYC browser | None | It calls the developer-owned `/session` and `/kyc-result` proxy routes. |
| KYC proxy | Platform key only | It authenticates the developer to this platform. |
| Platform broker/workers | OpenAI, Rumik, LiveKit and database credentials | This layer creates rooms and runs the server-side STT -> LLM -> Rumik TTS pipeline. |
| Pipecat | No key | Pipecat is the pipeline framework, not a hosted credentialed provider. |

This separation is the project's own platform architecture, documented in the
[credential and tenancy model](../../IMPLEMENTATION_PLAN.md#4a-credential--tenancy-model-one-platform-serving-many-devs-and-products)
and implemented by the [KYC proxy](../../kyc/server.py). Rumik's official
Pipecat + LiveKit cookbook confirms why the backend pipeline itself needs the
provider credentials: LiveKit supplies transport, STT and LLM are separate
services, and Rumik supplies TTS.

The apparent confusion comes from local development: both the platform backend
and the KYC proxy are in one repository and currently read one root `.env`.
That file is therefore a combined operator-and-demo configuration file; it is
not the set of credentials a real KYC developer should receive. In deployment,
the separation should be:

- platform deployment secrets: all upstream keys and database credentials;
- KYC developer server secret: one platform key plus the platform URL;
- KYC browser: no long-lived secret.

Sources:

- [Rumik's official Pipecat + LiveKit architecture and prerequisites](https://docs.rumik.ai/cookbook/voice-agent-pipecat-livekit)
- [Official `pipecat-rumik` prerequisites](https://pypi.org/project/pipecat-rumik/0.1.4/)
