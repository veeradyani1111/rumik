from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Literal

from loguru import logger
from PIL import Image as PILImage
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    ErrorFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMMessagesAppendFrame,
    LLMRunFrame,
    TTSSpeakFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
    TTSTextFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.cerebras.llm import CerebrasLLMService, CerebrasLLMSettings
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.stt import OpenAIRealtimeSTTService
from pipecat.transports.livekit.transport import LiveKitParams, LiveKitTransport
from pipecat.turns.user_stop import SpeechTimeoutUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.workers.runner import WorkerRunner
from pydantic import BaseModel, ConfigDict, Field

from .config import SamplePolicy, Settings
from .frame_sampler import FrameSampler
from .gemini_live_stt import GeminiLiveSTTService
from .gemini_stt import GeminiSTTService
from .narration import NarrationAcks
from .observability import FrameTap
from .rumik_tts import create_rumik_tts
from .tone_tags import SYSTEM_PROMPT_FRAGMENT
from .tool_bridge import ClientToolBridge, normalize_parameters
from .verdict_end import VerdictEnd


class WorkerTool(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    # How long the worker waits for the browser handler. Interactive tools (like a
    # card capture that waits for the person to click) legitimately take a while.
    timeout_secs: float = Field(default=15.0, ge=1.0, le=120.0)
    # False = the call survives a barge-in and runs "async": the model may keep
    # talking while it runs and receives the result later as a message. Right for
    # a long, person-facing tool (the card box); wrong for instant tools.
    cancel_on_interruption: bool = True


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
    # Fixed opening line spoken the moment the person joins. When set, it goes
    # straight to TTS rather than through the LLM, so the greeting is guaranteed
    # to be heard and can never be skipped in favour of an early tool call.
    greeting: str = Field(default="", max_length=600)
    force_tone: Literal["", "neutral"] = ""
    # Free-form tag from the page (e.g. its capture-code version) so a live run's
    # logs prove which client code was actually running - a stale tab looks
    # exactly like a regression otherwise.
    client_version: str = Field(default="", max_length=80)


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
    greeting_instruction = (
        "The fixed greeting is handled separately. Do not greet the user again; continue from it."
        if config.greeting
        else "When the session starts, proactively greet the user and begin the requested workflow."
    )
    system_prompt = f"{config.prompt.strip()}\n\n{greeting_instruction}\n\n{SYSTEM_PROMPT_FRAGMENT}"
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
    llm: OpenAILLMService | GoogleLLMService | CerebrasLLMService
    context: LLMContext
    bridge: ClientToolBridge
    stt: Any = None
    tts: Any = None

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
    logger.info("CLIENT_VERSION {}", config.client_version or "(not reported)")
    llm_name = {
        "gemini": settings.gemini_llm_model,
        "cerebras": settings.cerebras_llm_model,
    }.get(settings.llm_provider, config.llm_model)
    stt_provider = settings.resolved_stt_provider
    stt_name = settings.stt_model_name(config.stt_model)
    logger.info(
        "MODEL_PROVIDER llm={}:{} stt={}:{}", settings.llm_provider, llm_name, stt_provider, stt_name
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
    if stt_provider == "gemini" and settings.gemini_stt_mode == "live":
        # Streaming over the Live API: audio goes up while the person talks and
        # our VAD closes the turn, so the transcript lands ~0.3s after they stop
        # (see gemini_live_stt.py). Also used with Cerebras, which has no STT.
        stt = GeminiLiveSTTService(api_key=settings.gemini_api_key, model=settings.gemini_live_stt_model)
    elif stt_provider == "gemini":
        # Old one-shot path (GEMINI_STT_MODE=segmented): one ~3s generateContent
        # call with the whole utterance after the person stops talking.
        stt = GeminiSTTService(api_key=settings.gemini_api_key, model=settings.gemini_stt_model)
    elif stt_provider == "deepgram":
        # Streaming websocket STT: words arrive while the person is still talking,
        # so the transcript is complete within ~100-300ms of them stopping.
        from pipecat.services.deepgram.stt import DeepgramSTTService, DeepgramSTTSettings

        stt = DeepgramSTTService(
            api_key=settings.deepgram_api_key,
            settings=DeepgramSTTSettings(model=settings.deepgram_stt_model, language="en"),
        )
    elif stt_provider == "sarvam":
        # Streaming realtime STT (saaras:v3), strong on Indian English and Indian
        # languages; the same engine the TCY tutor runs on.
        from pipecat.services.sarvam.stt import SarvamSTTService, SarvamSTTSettings

        stt = SarvamSTTService(
            api_key=settings.sarvam_api_key,
            settings=SarvamSTTSettings(model=settings.sarvam_stt_model),
        )
    else:
        stt = OpenAIRealtimeSTTService(
            api_key=settings.openai_api_key,
            settings=OpenAIRealtimeSTTService.Settings(
                model=config.stt_model,
                noise_reduction="near_field",
            ),
        )
    sampler = FrameSampler(config.sample_policy)
    if settings.llm_provider == "cerebras":
        # OpenAI-compatible; gemma-4-31b accepts base64 image data URIs (the format
        # our card/tilt photos already use) and supports parallel + strict tools.
        llm = CerebrasLLMService(
            api_key=settings.cerebras_api_key,
            settings=CerebrasLLMSettings(model=settings.cerebras_llm_model),
        )
    elif settings.llm_provider == "gemini":
        # Gemini 2.5 'thinks' by default, adding seconds to every turn; this flow
        # needs fast, literal tool calls. `thinking_budget` is a 2.5-series knob
        # (3.x uses thinking_level and may reject it), so only set it there.
        gemini_settings = (
            GoogleLLMService.Settings(
                model=settings.gemini_llm_model,
                thinking=GoogleLLMService.ThinkingConfig(thinking_budget=0),
            )
            if "2.5" in settings.gemini_llm_model
            else GoogleLLMService.Settings(model=settings.gemini_llm_model)
        )
        llm = GoogleLLMService(api_key=settings.gemini_api_key, settings=gemini_settings)
    else:
        llm = OpenAILLMService(
            api_key=settings.openai_api_key,
            settings=OpenAILLMService.Settings(model=config.llm_model),
        )
    tts = create_rumik_tts(settings, voice=config.voice, force_tone=config.force_tone or None)
    context = build_context(config)
    # Pipecat 1.3.0 defaults the user-turn-stop decision to an ML model
    # (LocalSmartTurnAnalyzerV3). For a KYC flow we want a deterministic,
    # explainable turn end: once VAD detects the user paused and at least one
    # transcript has arrived, a short window closes the turn and the LLM replies.
    aggregators = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            # Barge-in stays ON (default start strategies): a person should be able
            # to interrupt, get an answer, and have the agent steer back to the
            # current step — like a human would. What a barge-in must NOT do is
            # cancel a tool call that is already running (see register_function
            # calls below) or leave a step un-issued (the page's flow watchdog
            # re-issues it).
            user_turn_strategies=UserTurnStrategies(
                stop=[SpeechTimeoutUserTurnStopStrategy(user_speech_timeout=0.25)],
            ),
        ),
    )

    async def send_payload(payload: dict[str, Any]) -> None:
        await transport.send_message(json.dumps(payload, separators=(",", ":")))

    bridge = ClientToolBridge(send_payload)

    # Bounded-call ending, anchored to the VERDICT RESPONSE itself.
    #
    # The final tool result (matchDetails / submitResult, flagged call_ending) is
    # delivered to the model; the model's NEXT response is the spoken verdict.
    # Everything keys off that response:
    #   - reveal the on-screen result when ITS audio starts ("verdict_spoken"),
    #   - hang up only when ITS audio has fully drained.
    # Why not "the next time the bot speaks"? Because the model often says "let me
    # check…" in the SAME turn it calls matchDetails, and that line can start
    # playing AFTER the result arrives — so it was mistaken for the verdict: FAIL
    # appeared on screen at "let me check" and the call ended before the verdict
    # was ever spoken. Fallbacks cover a model that never responds.
    call_end = {"requested": False, "revealed": False, "ended": False}
    bot_speaking = {"on": False}
    narration = NarrationAcks()
    # When has the verdict FULLY played? With sentence-streamed TTS, "TTS stopped" +
    # "bot stopped" happens after EVERY sentence, so the call used to end after the
    # first one and cut off "thank you, goodbye". VerdictEnd waits for the whole
    # response to be generated and spoken, then for a quiet tail with no new speech
    # (which also covers the browser's own playout buffer).
    verdict = VerdictEnd()
    VERDICT_TAIL_SEC = VerdictEnd.TAIL_SEC

    async def request_call_end(source: str) -> None:
        if call_end["requested"]:
            return
        call_end["requested"] = True
        logger.info("call end requested ({}); will hang up after the verdict is spoken", source)
        asyncio.create_task(end_call_fallbacks())

    async def reveal_verdict() -> None:
        if call_end["revealed"]:
            return
        call_end["revealed"] = True
        await send_payload({"type": "verdict_spoken"})

    async def end_call(reason: str) -> None:
        if call_end["ended"]:
            return
        call_end["ended"] = True
        logger.info("ending call: {}", reason)
        try:
            await reveal_verdict()
            await send_payload({"type": "call_ended", "reason": reason})
        finally:
            await worker.stop_when_done()

    async def end_call_after_quiet(gen: int) -> None:
        await asyncio.sleep(VERDICT_TAIL_SEC)
        if not verdict.still_quiet(gen):
            logger.debug("verdict: more speech followed; not ending yet")
            return
        await end_call("verdict finished playing")

    async def end_call_fallbacks() -> None:
        await asyncio.sleep(12)
        if not call_end["ended"] and not verdict.response_started:
            await end_call("no verdict response within 12s")
            return
        await asyncio.sleep(18)
        if not call_end["ended"]:
            await end_call("fallback timeout after 30s")

    # Provider failures (quota, billing, auth, outages) used to look exactly like a
    # broken flow: the person spoke, nothing came back. Say so out loud and tell
    # the page, once per short window, so "it never responded" has a visible cause.
    provider_error = {"last_spoken_at": 0.0, "retries": 0}
    MAX_TRANSIENT_RETRIES = 3

    async def retry_turn_after(delay: float) -> None:
        # A transient provider failure (503 / overloaded) dropped the model's turn.
        # The person's words are still in context, so re-running the LLM retries
        # the same turn - unless the call is ending or a tool call is mid-flight.
        await asyncio.sleep(delay)
        if call_end["ended"]:
            return
        in_progress = aggregators.assistant().has_function_calls_in_progress
        if callable(in_progress):
            in_progress = in_progress()
        if in_progress:
            logger.info("PROVIDER_RETRY skipped: function call in progress")
            return
        logger.info("PROVIDER_RETRY re-running the turn ({}/{})", provider_error["retries"], MAX_TRANSIENT_RETRIES)
        await worker.queue_frame(LLMRunFrame())

    async def watch_errors(frame, _direction) -> None:
        if not isinstance(frame, ErrorFrame):
            return
        text = str(frame.error or "")
        lowered = text.lower()
        from_stt = text.startswith("Gemini STT error") or any(
            marker in lowered for marker in ("stt", "deepgram", "sarvam", "transcri")
        )
        kind = (
            "billing" if ("402" in text or "payment" in lowered) else
            "quota" if ("429" in text or "quota" in lowered or "rate limit" in lowered) else
            "auth" if ("401" in text or "403" in text or "api key" in lowered or "unauthorized" in lowered) else
            "transient" if ("503" in text or "unavailable" in lowered or "overloaded" in lowered or "high demand" in lowered) else
            "provider"
        )
        logger.error("PROVIDER_ERROR kind={} from_stt={} detail={}", kind, from_stt, text[:300])
        if kind == "transient" and not from_stt and provider_error["retries"] < MAX_TRANSIENT_RETRIES:
            provider_error["retries"] += 1
            asyncio.create_task(retry_turn_after(2.5))
        try:
            await send_payload({"type": "provider_error", "kind": kind, "message": text[:400]})
        except Exception:  # best effort
            pass
        now = asyncio.get_event_loop().time()
        if now - provider_error["last_spoken_at"] < 30 or call_end["ended"]:
            return
        provider_error["last_spoken_at"] = now
        line = {
            "billing": "Sorry - I can't reach my model provider right now; it says payment or billing is required on that account. Please sort that out and try again.",
            "quota": "Sorry - my model provider has hit its usage limit for now. Please try again a little later.",
            "auth": "Sorry - my model provider rejected the access key. Please check the key and try again.",
            "transient": "One moment - my provider is a little busy. Let me try that again.",
        }.get(kind, "Sorry - I'm having trouble reaching my model provider right now. Please try again in a moment.")
        await worker.queue_frame(TTSSpeakFrame(line, append_to_context=False))

    async def watch_bot_speech(frame, _direction) -> None:
        maybe_end = False
        if isinstance(frame, BotStartedSpeakingFrame):
            bot_speaking["on"] = True
            verdict.on_bot_started()
        elif isinstance(frame, BotStoppedSpeakingFrame):
            bot_speaking["on"] = False
            maybe_end = verdict.on_bot_stopped()
            # Page-requested lines are acknowledged only once their audio has drained,
            # so the page can sequence "instruct, THEN check" against what was heard.
            for spoken_id in narration.on_bot_stopped():
                logger.info("page narration heard: id={}", spoken_id)
                await send_payload({"type": "spoken", "id": spoken_id})
        elif isinstance(frame, TTSTextFrame):
            narration.on_tts_text(getattr(frame, "text", ""))
        if not call_end["requested"] or call_end["ended"]:
            return
        if isinstance(frame, LLMFullResponseStartFrame):
            if verdict.on_response_start():
                logger.info("verdict response started")
            return
        if not verdict.response_started:
            return  # anything before the verdict response is the previous line
        if isinstance(frame, TTSStartedFrame):
            # If the bot is already mid-sentence (e.g. "let me check…"), the verdict
            # audio is queued right behind it; reveal now rather than never.
            if verdict.on_tts_started():
                await reveal_verdict()
        elif isinstance(frame, TTSStoppedFrame):
            verdict.on_tts_stopped()
        elif isinstance(frame, LLMFullResponseEndFrame):
            maybe_end = verdict.on_response_end()
        elif isinstance(frame, BotStartedSpeakingFrame):
            await reveal_verdict()  # verdict audio actually began
        if maybe_end:
            # Looks finished - but the next sentence may start within the tail, in
            # which case still_quiet() fails and this attempt is abandoned.
            asyncio.create_task(end_call_after_quiet(verdict.gen))

    @transport.event_handler("on_data_received")
    async def on_data_received(_transport, data: bytes, participant_id: str):
        logger.info("data channel message from {} ({} bytes)", participant_id, len(data))
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            payload = None
        if isinstance(payload, dict) and payload.get("type") == "speak":
            # The developer's page may ask the agent to speak a fixed line at an
            # exact moment (the card box appearing, the snap firing). Those moments
            # sit inside a blocking tool call, where the LLM is silent by
            # construction, so the narration has to come from here. It is spoken
            # verbatim via TTS and recorded in context so the model knows it was said.
            text = str(payload.get("text") or "").strip()[:300]
            speak_id = str(payload.get("id") or "").strip()[:64]
            if text:
                logger.info("page-requested narration: id={} {!r}", speak_id or "-", text)
                if speak_id:
                    narration.request(speak_id, text)
                context.add_message({
                    "role": "system",
                    "content": f"[Already spoken to the person by your voice - do not repeat it: \"{text}\"]",
                })
                await worker.queue_frame(TTSSpeakFrame(text, append_to_context=False))
            return
        if isinstance(payload, dict) and payload.get("type") == "end_call":
            await request_call_end("page")
            return
        if isinstance(payload, dict) and payload.get("type") == "nudge":
            # The page owns the flow and knows when a step has stalled (e.g. the
            # model was interrupted before it issued a tool call and never
            # re-issued it). A nudge is a system note appended to the context
            # that immediately re-runs the model, so the flow self-heals instead
            # of waiting for the person to say something. Never nudge while a
            # tool call is still in flight — the model would get a context with
            # an unresolved call — or once the call is ending.
            text = str(payload.get("text") or "").strip()[:400]
            if not text or call_end["requested"]:
                return
            # In Pipecat 1.3.0 this is a property (bool), not a method; calling it
            # raised "'bool' object is not callable" and silently killed every nudge.
            in_progress = getattr(aggregators.assistant(), "has_function_calls_in_progress", False)
            if callable(in_progress):
                in_progress = in_progress()
            if in_progress:
                logger.info("page nudge skipped (function call in progress): {!r}", text)
                return
            logger.info("page nudge: {!r}", text)
            await worker.queue_frame(
                LLMMessagesAppendFrame(messages=[{"role": "system", "content": text}], run_llm=True)
            )
            return
        await bridge.handle_message(data)

    # `look` frames answer an immediate question and are dropped when the turn
    # ends. CAPTURE photos must survive until the matching report tool has read
    # them: removing them at turn-stop lost the card photo whenever the model
    # spent a turn saying "analyzing..." first - it then called reportCardRead with
    # NO image and invented a name (seen live on Gemini: two different names for
    # one photo). Keyed by the capture tool; consumed by its report tool.
    # `look` frames answer an immediate question and are dropped when the turn
    # ends. CAPTURE photos must survive until the matching report tool has read
    # them: removing them at turn-stop lost the card photo whenever the model
    # spent a turn saying "analyzing..." first - it then called reportCardRead with
    # NO image and invented a name (seen live on Gemini: two different names for
    # one photo). Keyed by the capture tool; consumed by its report tool.
    # `look` frames answer an immediate question and are dropped when the turn
    # ends. CAPTURE photos must survive until the matching report tool has read
    # them: removing them at turn-stop lost the card photo whenever the model
    # spent a turn saying "analyzing..." first - it then called reportCardRead with
    # NO image and invented a name (seen live on Gemini: two different names for
    # one photo). Keyed by the capture tool; consumed by its report tool.
    ephemeral_messages: list[object] = []
    capture_images: dict[str, list[object]] = {}
    CONSUMES = {"reportCardRead": "captureCard", "reportHologram": "captureHologram"}

    def drop_capture_images(capture_tool: str) -> None:
        stale = capture_images.pop(capture_tool, [])
        if stale:
            context.set_messages([m for m in context.get_messages() if m not in stale])
            logger.info("dropped {} attached photo(s) from {}", len(stale), capture_tool)
    capture_images: dict[str, list[object]] = {}
    CONSUMES = {"reportCardRead": "captureCard", "reportHologram": "captureHologram"}

    def drop_capture_images(capture_tool: str) -> None:
        stale = capture_images.pop(capture_tool, [])
        if stale:
            context.set_messages([m for m in context.get_messages() if m not in stale])
            logger.info("dropped {} attached photo(s) from {}", len(stale), capture_tool)
    capture_images: dict[str, list[object]] = {}
    CONSUMES = {"reportCardRead": "captureCard", "reportHologram": "captureHologram"}

    def drop_capture_images(capture_tool: str) -> None:
        stale = capture_images.pop(capture_tool, [])
        if stale:
            context.set_messages([m for m in context.get_messages() if m not in stale])
            logger.info("dropped {} attached photo(s) from {}", len(stale), capture_tool)

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
            # A report tool consumes the photos of its capture; a new capture
            # replaces any photos left over from a previous attempt.
            if tool_name in CONSUMES:
                drop_capture_images(CONSUMES[tool_name])
            if tool_name in capture_images:
                drop_capture_images(tool_name)
            # A report tool consumes the photos of its capture; a new capture
            # replaces any photos left over from a previous attempt.
            if tool_name in CONSUMES:
                drop_capture_images(CONSUMES[tool_name])
            if tool_name in capture_images:
                drop_capture_images(tool_name)
            # A report tool consumes the photos of its capture; a new capture
            # replaces any photos left over from a previous attempt.
            if tool_name in CONSUMES:
                drop_capture_images(CONSUMES[tool_name])
            if tool_name in capture_images:
                drop_capture_images(tool_name)
            result = await bridge.call(tool_name, params.arguments, timeout_seconds=tool_timeout)
            logger.info("client tool {!r} returned", tool_name)
            # A handler may upload one or more high-resolution stills (the card
            # photo, or a burst of frames while the card is tilted) over the data
            # channel and reference them by id. Attach each to the context as an
            # ephemeral image so the LLM reads THESE photos, not the compressed
            # live video frames.
            still_ids: list[str] = []
            if isinstance(result, dict):
                if isinstance(result.get("still_id"), str):
                    still_ids.append(result["still_id"])
                if isinstance(result.get("still_ids"), list):
                    still_ids.extend(s for s in result["still_ids"] if isinstance(s, str))
            note = (
                result.get("image_note")
                if isinstance(result, dict) and isinstance(result.get("image_note"), str)
                else (
                    "This is the high-resolution photo just captured through the "
                    "on-screen card frame. Read printed text from THIS image only. If "
                    "a field is blurry, glared, cut off, or unreadable, say so and ask "
                    "for a new capture — never guess or invent a value."
                )
            )
            attached: list[list[int]] = []
            for still_id in still_ids:
                still = bridge.pop_still(still_id)
                if still is None:
                    continue
                with PILImage.open(BytesIO(still)) as decoded:
                    size = decoded.size
                message = await LLMContext.create_image_message(
                    format="image/jpeg", size=size, image=still, text=note
                )
                context.add_message(message)
                capture_images.setdefault(tool_name, []).append(message)
                attached.append(list(size))
            if attached:
                result = {
                    **result,
                    "photo_attached": True,
                    "photos_attached": len(attached),
                    "photo_size": attached[0],
                }
                # One greppable line per capture so a live run can be audited
                # after the fact even when the frame taps have flooded the log.
                logger.info(
                    "CARD_READ_EVIDENCE tool={} attached={} sizes={} — model received the photo",
                    tool_name, len(attached), attached,
                )
            elif still_ids:
                # The browser said it uploaded a still but nothing was reassembled
                # by the time the result arrived: the model is about to answer
                # with NO image. This is the silent failure behind "John Doe".
                logger.warning(
                    "CARD_READ_EVIDENCE tool={} still_ids={} attached=0 — chunks never "
                    "arrived; model received NO image and must not read anything",
                    tool_name, still_ids,
                )
                if isinstance(result, dict):
                    result = {**result, "photo_attached": False}
            elif isinstance(result, dict) and tool_name == "captureCard":
                logger.info(
                    "CARD_READ_EVIDENCE tool=captureCard captured={} reason={}",
                    result.get("captured"), result.get("reason"),
                )
            if isinstance(result, dict):
                # One compact, greppable line per client-tool result: what happened,
                # how long the box was open, and why it closed.
                logger.info(
                    "CLIENT_TOOL_RESULT tool={} captured={} reason={} elapsed_ms={} frames={} attached={} error={} stats={}",
                    tool_name,
                    result.get("captured"),
                    result.get("reason"),
                    result.get("elapsed_ms"),
                    result.get("frames"),
                    result.get("photos_attached"),
                    result.get("error"),
                    result.get("stats"),
                )
            # A final result: the model's next response is the spoken verdict, so
            # arm the call-ending logic BEFORE the result reaches the model.
            if isinstance(result, dict) and result.get("call_ending") is True:
                await request_call_end(f"tool {tool_name}")
            await params.result_callback(result)

        llm.register_function(
            tool.name,
            client_handler,
            timeout_secs=tool.timeout_secs + 10,
            cancel_on_interruption=tool.cancel_on_interruption,
        )

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
            FrameTap("to-llm", on_frame=watch_errors),  # what reaches the LLM + provider-error surfacing
            llm,
            FrameTap("from-llm"),  # did the LLM answer or call a function?
            tts,
            FrameTap("tts", on_frame=watch_bot_speech),  # did TTS produce speech? + call-end watcher
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

    greeted = False

    @transport.event_handler("on_first_participant_joined")
    async def greet(_transport, participant_id: str):
        # The browser subscribes to the agent's audio track a moment AFTER it
        # joins the room. Greeting the instant we see the participant plays the
        # opening line before that subscription exists, so the user hears
        # nothing (or a clipped word) and it looks like the agent never spoke.
        # Wait briefly so the downstream audio path is live, then greet once.
        nonlocal greeted
        if greeted:
            return
        greeted = True
        logger.info("participant {} joined; waiting for audio subscription before greeting", participant_id)
        await asyncio.sleep(1.5)
        if config.greeting:
            # Speak the fixed opening line directly through TTS. Routing the
            # greeting through the LLM let it decide to call a tool (open the
            # card box) on its very first turn instead of speaking — the person
            # then heard nothing. Record it in context so the model knows what
            # was already said and can pick up the conversation from there.
            logger.info("speaking fixed greeting for {}", participant_id)
            # Recorded as a system NOTE, not a model turn: Gemini merges consecutive
            # model messages and re-speaks them, which echoed the whole greeting.
            context.add_message({
                "role": "system",
                "content": f"[Already spoken to the person by your voice - do not repeat it: \"{config.greeting}\"]",
            })
            # append_to_context=False: the aggregator would otherwise ALSO record this
            # as an assistant turn (on top of the note above) - Gemini merged and
            # re-spoke those. The note is the only trace the model sees.
            # The page is told when the greeting has actually been HEARD (a
            # "spoken" ack with id "greeting"), so its consent reminder counts
            # from the end of the greeting - not from session creation, which on
            # a cold start was long before the agent had even joined and made the
            # agent ask "let me know when you're ready" right after greeting.
            narration.request("greeting", config.greeting)
            await worker.queue_frame(TTSSpeakFrame(config.greeting, append_to_context=False))
        else:
            logger.info("queueing LLM greeting for {}", participant_id)
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
        stt=stt,
        tts=tts,
        llm=llm,
        context=context,
        bridge=bridge,
    )
