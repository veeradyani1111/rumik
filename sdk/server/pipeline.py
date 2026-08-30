from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.stt import OpenAISTTService
from pipecat.transports.livekit.transport import LiveKitParams, LiveKitTransport
from pydantic import BaseModel, ConfigDict, Field

from .config import SamplePolicy, Settings
from .frame_sampler import FrameSampler
from .rumik_tts import create_rumik_tts
from .tone_tags import SYSTEM_PROMPT_FRAGMENT
from .tool_bridge import ClientToolBridge, normalize_parameters


class WorkerTool(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str
    parameters: dict[str, str] = Field(default_factory=dict)


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
    system_prompt = f"{config.prompt.strip()}\n\n{SYSTEM_PROMPT_FRAGMENT}"
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
        await PipelineRunner(handle_sigint=False).run(self.worker)


def build_pipeline(config: AgentConfig, settings: Settings) -> PipelineRuntime:
    vad = SileroVADAnalyzer()
    transport = LiveKitTransport(
        config.livekit_url,
        config.agent_token,
        config.room,
        params=LiveKitParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            video_in_enabled=config.vision,
            vad_analyzer=vad,
        ),
    )
    stt = OpenAISTTService(
        api_key=settings.openai_api_key,
        settings=OpenAISTTService.Settings(model=config.stt_model),
    )
    sampler = FrameSampler(config.sample_policy)
    llm = OpenAILLMService(
        api_key=settings.openai_api_key,
        settings=OpenAILLMService.Settings(model=config.llm_model),
    )
    tts = create_rumik_tts(settings, voice=config.voice)
    context = build_context(config)
    aggregators = LLMContextAggregatorPair(context)

    async def send_payload(payload: dict[str, Any]) -> None:
        await transport.send_message(json.dumps(payload, separators=(",", ":")))

    bridge = ClientToolBridge(send_payload)

    @transport.event_handler("on_data_received")
    async def on_data_received(_transport, data: bytes, _participant_id: str):
        await bridge.handle_message(data)

    ephemeral_messages: list[object] = []

    async def look_handler(params) -> None:
        result = await sampler.look(
            reason=str(params.arguments.get("reason", "inspect camera")),
            motion=bool(params.arguments.get("motion", False)),
        )
        for sampled in result.images:
            message = await LLMContext.create_image_message(
                format="image/jpeg",
                size=sampled.size,
                image=sampled.jpeg,
                text="Camera evidence for this tool call.",
            )
            context.add_message(message)
            ephemeral_messages.append(message)
        await params.result_callback(
            {"frames": len(result.images), "note": result.note, "reused": result.reused_last_frame}
        )

    llm.register_function("look", look_handler, timeout_secs=12)

    for tool in config.tools:
        async def client_handler(params, tool_name=tool.name) -> None:
            result = await bridge.call(tool_name, params.arguments)
            await params.result_callback(result)

        llm.register_function(tool.name, client_handler, timeout_secs=15)

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
            stt,
            aggregators.user(),
            sampler,
            llm,
            tts,
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

    @transport.event_handler("on_first_participant_joined")
    async def greet(_transport, _participant_id: str):
        await worker.queue_frame(TTSSpeakFrame("[neutral] Hello! How can I help you today?"))

    @transport.event_handler("on_participant_disconnected")
    async def participant_left(_transport, _participant_id: str):
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
