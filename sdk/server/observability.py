from __future__ import annotations

from loguru import logger
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


# Raw media and metrics frames arrive many times per second. Logging each one
# would bury the signal, so the tap names them once at DEBUG-free INFO only when
# they are not in this set.
_HIGH_FREQUENCY_FRAMES = frozenset(
    {
        "AudioRawFrame",
        "InputAudioRawFrame",
        "UserAudioRawFrame",
        "OutputAudioRawFrame",
        "TTSAudioRawFrame",
        "UserSpeakingFrame",
        "InputImageRawFrame",
        "OutputImageRawFrame",
        "UserImageRawFrame",
        "SpriteFrame",
        "MetricsFrame",
        "HeartbeatFrame",
    }
)

# Frames whose payload carries a short, human-meaningful string worth logging.
_TEXT_ATTRS = ("text", "transcript", "message", "reason", "error")


def _summarize(frame: object) -> str:
    parts: list[str] = []
    for attr in _TEXT_ATTRS:
        value = getattr(frame, attr, None)
        if isinstance(value, str) and value.strip():
            snippet = value.strip().replace("\n", " ")
            if len(snippet) > 160:
                snippet = snippet[:157] + "..."
            parts.append(f"{attr}={snippet!r}")
    user_id = getattr(frame, "user_id", None)
    if user_id:
        parts.append(f"user_id={user_id}")
    return " ".join(parts)


class FrameTap(FrameProcessor):
    """Logs every frame crossing one point in the pipeline.

    A tap is inserted after each service so a failed turn shows exactly how far
    it travelled: did the user's speech reach the transport, did VAD mark a
    turn, did STT transcribe it, did the LLM answer, did TTS speak?
    """

    def __init__(self, label: str) -> None:
        super().__init__(name=f"FrameTap[{label}]")
        self._label = label

    async def process_frame(self, frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        name = type(frame).__name__
        if name not in _HIGH_FREQUENCY_FRAMES:
            summary = _summarize(frame)
            logger.info(
                "tap[{}] {} dir={}{}",
                self._label,
                name,
                direction.name,
                f" | {summary}" if summary else "",
            )
        await self.push_frame(frame, direction)
