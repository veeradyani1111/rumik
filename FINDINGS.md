# Findings

## Dependency compatibility

- `pipecat-rumik==0.1.4` advertises compatibility with `pipecat-ai>=1,<2`, but importing it with `pipecat-ai==1.8.1` fails because `_NotGiven` was removed from `pipecat.services.settings`. The latest pair is therefore not usable as published on 2026-08-30. The project pins `pipecat-ai==1.3.0`, where the Rumik service and all planned LiveKit/OpenAI imports load successfully.
