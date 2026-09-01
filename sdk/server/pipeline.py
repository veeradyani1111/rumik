from __future__ import annotations

import json
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from loguru import logger
from PIL import Image as PILImage
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.stt import OpenAIRealtimeSTTService
from pipecat.transports.livekit.transport import LiveKitParams, LiveKitTransport
from pipecat.turns.user_stop import SpeechTimeoutUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.workers.runner import WorkerRunner
from pydantic import BaseModel, ConfigDict, Field

from .config import SamplePolicy, Settings
from .frame_sampler import FrameSampler
from .observability import FrameTap
from .rumik_tts import create_rumik_tts
from .tone_tags import SYSTEM_PROMPT_FRAGMENT
from .tool_bridge import ClientToolBridge, normalize_parameters


class WorkerTool(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    # How long the worker waits for the browser handler. Interactive tools (like a
    # card capture that waits for the person to click) legitimately take a while.
    timeout_secs: float = Field(default=15.0, ge=1.0, le=120.0)


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    room: str
    agent_token: str
    livekit_url: str
    prompt: str = "You are a helpful, concise assistant."
    vision: bool = False
    voice: dict[str, Any] = Field(default_factory=dict)
    tools: list[WorkerTool] = Field(default_factory=list)
    sample_policy: SamplePolicy = Field(default_factory=SamplePolicy)
    llm_model: str = "gpt-4o"
    stt_model: str = "gpt-4o-transcribe"


def build_context(config: AgentConfig) -> LLMContext:
    look = FunctionSchema(
        name="look",
        description="Look at the user's current camera view. Use motion=true for tilt, blink, or head-movement checks.",
        properties={
            "reason": {"type": "string", "description": "What visual fact you need to inspect"},
            "motion": {"type": "boolean", "description": "Capture a short recent burst for motion"},
        },
        required=["reason"],
    )
    tools = [look]
    for tool in config.tools:
        schema = normalize_parameters(tool.parameters)
        tools.append(
            FunctionSchema(
                name=tool.name,
                description=tool.description,
                properties=schema["properties"],
                required=schema["required"],
            )
        )
    system_prompt = (
        f"{config.prompt.strip()}\n\n"
        "When the session starts, proactively greet the user and begin the requested workflow.\n\n"
        f"{SYSTEM_PROMPT_FRAGMENT}"
    )
    return LLMContext(
        messages=[{"role": "system", "content": system_prompt}],
        tools=ToolsSchema(standard_tools=tools),
    )


@dataclass(slots=True)
class PipelineRuntime:
    pipeline: Pipeline
    worker: PipelineWorker
    transport: LiveKitTransport
    sampler: FrameSampler
    llm: OpenAILLMService
    context: LLMContext
    bridge: ClientToolBridge

    async def run(self) -> None:
        await WorkerRunner(handle_sigint=False).run(self.worker)


def build_pipeline(config: AgentConfig, settings: Settings) -> PipelineRuntime:
    logger.info(
        "building pipeline room={} vision={} llm={} stt={} tts_model={} tts_speaker={} tools={}",
        config.room,
        config.vision,
        config.llm_model,
        config.stt_model,
        settings.rumik_tts_model,
        settings.rumik_tts_speaker,
        [tool.name for tool in config.tools],
    )
    # Tighter end-of-turn: 0.35s of silence closes the turn (default 0.8s) so the
    # agent starts replying sooner. Short KYC answers tolerate this well; if the
    # agent starts talking over people mid-sentence, raise this first.
    vad = SileroVADAnalyzer(params=VADParams(stop_secs=0.35))
    # In Pipecat 1.3.0 the transport no longer runs VAD from a `vad_analyzer`
    # param (that field does not exist and is silently ignored). Voice-activity
    # detection is a standalone processor that must sit in the pipeline; without
    # it no VADUserStarted/StoppedSpeaking frames are emitted, so the user turn
    # never starts, STT never segments, and the agent never replies.
    vad_processor = VADProcessor(vad_analyzer=vad)
    transport = LiveKitTransport(
        config.livekit_url,
        config.agent_token,
        config.room,
        params=LiveKitParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            video_in_enabled=config.vision,
        ),
    )
    # Streaming STT over the OpenAI Realtime websocket. Unlike the segmented HTTP
    # STT (which waited for the full utterance, then made one ~1.6s call), this
    # streams audio continuously and, in local-VAD mode, commits the buffer the
    # moment our VADProcessor reports the user stopped — so the transcript is
    # ready almost immediately at turn end.
    stt = OpenAIRealtimeSTTService(
        api_key=settings.openai_api_key,
        settings=OpenAIRealtimeSTTService.Settings(
            model=config.stt_model,
            noise_reduction="near_field",
        ),
    )
    sampler = FrameSampler(config.sample_policy)
    llm = OpenAILLMService(
        api_key=settings.openai_api_key,
        settings=OpenAILLMService.Settings(model=config.llm_model),
    )
    tts = create_rumik_tts(settings, voice=config.voice)
    context = build_context(config)
    # Pipecat 1.3.0 defaults the user-turn-stop decision to an ML model
    # (LocalSmartTurnAnalyzerV3). For a KYC flow we want a deterministic,
    # explainable turn end: once VAD detects the user paused and at least one
    # transcript has arrived, a short window closes the turn and the LLM replies.
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            user_turn_strategies=UserTurnStrategies(
                stop=[SpeechTimeoutUserTurnStopStrategy(user_speech_timeout=0.25)],
            ),
        ),
    )

    async def send_payload(payload: dict[str, Any]) -> None:
        await transport.send_message(json.dumps(payload, separators=(",", ":")))

    bridge = ClientToolBridge(send_payload)

    @transport.event_handler("on_data_received")
    async def on_data_received(_transport, data: bytes, participant_id: str):
        logger.info("data channel message from {} ({} bytes)", participant_id, len(data))
        await bridge.handle_message(data)

    ephemeral_messages: list[object] = []

    async def look_handler(params) -> None:
        motion = bool(params.arguments.get("motion", False))
        reason = str(params.arguments.get("reason", "inspect camera"))
        logger.info("look() called: motion={} reason={!r}", motion, reason)
        result = await sampler.look(reason=reason, motion=motion)
        logger.info(
            "look() result: frames={} reused={} note={!r}",
            len(result.images),
            result.reused_last_frame,
            result.note,
        )
        for sampled in result.images:
            message = await LLMContext.create_image_message(
                format="image/jpeg",
                size=sampled.size,
                image=sampled.jpeg,
                text=(
                    "This is the actual live camera frame for this look call. "
                    "Report only what you can literally see in THIS image. If a "
                    "document or field is not clearly visible and legible, say so "
                    "and ask the user to reposition it — do not guess or invent."
                ),
            )
            context.add_message(message)
            ephemeral_messages.append(message)
        await params.result_callback(
            {"frames": len(result.images), "note": result.note, "reused": result.reused_last_frame}
        )

    llm.register_function("look", look_handler, timeout_secs=12)

    for tool in config.tools:
        async def client_handler(params, tool_name=tool.name, tool_timeout=tool.timeout_secs) -> None:
            logger.info("client tool {!r} called", tool_name)
            result = await bridge.call(tool_name, params.arguments, timeout_seconds=tool_timeout)
            logger.info("client tool {!r} returned", tool_name)
            # A handler may upload a high-resolution still (e.g. the card photo)
            # over the data channel and reference it by id. Attach it to the
            # context as an ephemeral image so the LLM reads THIS photo, not the
            # compressed live video frames.
            still = bridge.pop_still(result.get("still_id")) if isinstance(result, dict) else None
            if still is not None:
                with PILImage.open(BytesIO(still)) as decoded:
                    size = decoded.size
                message = await LLMContext.create_image_message(
                    format="image/jpeg",
                    size=size,
                    image=still,
                    text=(
                        "This is the high-resolution photo just captured by the "
                        "user through the on-screen card frame. Read printed text "
                        "from THIS image only. If a field is blurry, glared, cut "
                        "off, or unreadable, say so and ask for a new capture — "
                        "never guess or invent a value."
                    ),
                )
                context.add_message(message)
                ephemeral_messages.append(message)
                result = {**result, "photo_attached": True, "photo_size": list(size)}
                logger.info("client tool {!r} attached still ({}x{})", tool_name, *size)
            await params.result_callback(result)

        llm.register_function(tool.name, client_handler, timeout_secs=tool.timeout_secs + 10)

    @aggregators.assistant().event_handler("on_assistant_turn_stopped")
    async def remove_ephemeral_images(_aggregator, _message) -> None:
        if not ephemeral_messages:
            return
        context.set_messages(
            [message for message in context.get_messages() if message not in ephemeral_messages]
        )
        ephemeral_messages.clear()

    pipeline = Pipeline(
        [
            transport.input(),
            vad_processor,  # emits VADUserStarted/StoppedSpeaking so turns can form
            FrameTap("input"),  # did the user's audio/VAD turns reach the pipeline?
            stt,
            FrameTap("stt"),  # did speech become a transcription?
            aggregators.user(),
            sampler,
            FrameTap("to-llm"),  # what reaches the LLM (context/run frames)
            llm,
            FrameTap("from-llm"),  # did the LLM answer or call a function?
            tts,
            FrameTap("tts"),  # did TTS produce speech for the user?
            transport.output(),
            aggregators.assistant(),
        ]
    )
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=16000,
            audio_out_sample_rate=24000,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        idle_timeout_secs=90,
    )

    @transport.event_handler("on_connected")
    async def on_connected(_transport):
        logger.info("agent connected to room {}", config.room)

    @transport.event_handler("on_disconnected")
    async def on_disconnected(_transport):
        logger.info("agent disconnected from room {}", config.room)

    @transport.event_handler("on_participant_connected")
    async def on_participant_connected(_transport, participant_id: str):
        logger.info("participant {} connected", participant_id)

    @transport.event_handler("on_audio_track_subscribed")
    async def on_audio_track_subscribed(_transport, participant_id: str):
        # This is the you->agent path. If it never fires, the agent never hears
        # the user, so no transcription and no reply are possible.
        logger.info("SUBSCRIBED to audio track from {} (agent can now hear user)", participant_id)

    @transport.event_handler("on_video_track_subscribed")
    async def on_video_track_subscribed(_transport, participant_id: str):
        logger.info("SUBSCRIBED to video track from {} (agent can now see user)", participant_id)

    @transport.event_handler("on_first_participant_joined")
    async def greet(_transport, participant_id: str):
        logger.info("participant {} joined; queueing greeting", participant_id)
        await worker.queue_frame(LLMRunFrame())

    @transport.event_handler("on_participant_disconnected")
    async def participant_left(_transport, participant_id: str):
        logger.info("participant {} disconnected; ending session", participant_id)
        await worker.stop_when_done()

    return PipelineRuntime(
        pipeline=pipeline,
        worker=worker,
        transport=transport,
        sampler=sampler,
        llm=llm,
        context=context,
        bridge=bridge,
    )
