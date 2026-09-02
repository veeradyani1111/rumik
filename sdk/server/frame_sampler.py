from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from io import BytesIO
from time import monotonic
from typing import Callable

from PIL import Image
from pipecat.frames.frames import InputImageRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from .config import SamplePolicy


@dataclass(frozen=True, slots=True)
class RawCapture:
    image: Image.Image
    captured_at: float


@dataclass(frozen=True, slots=True)
class SampledImage:
    jpeg: bytes
    size: tuple[int, int]
    captured_at: float


@dataclass(frozen=True, slots=True)
class LookResult:
    images: list[SampledImage]
    note: str | None = None
    reused_last_frame: bool = False


class FrameSampler(FrameProcessor):
    """Keeps the latest camera frame and encodes only explicit looks."""

    def __init__(self, policy: SamplePolicy, *, clock: Callable[[], float] = monotonic) -> None:
        super().__init__()
        self.policy = policy
        self._now = clock
        self.latest_raw: RawCapture | None = None
        self._last_accept_at: float | None = None
        self._spend_timestamps: deque[float] = deque()
        self._last_encoded: SampledImage | None = None
        self._new_frame_event = asyncio.Event()
        self._burst_active = 0
        self.accepted_count = 0
        self.images_sent = 0

    def accept_image(self, image: Image.Image) -> bool:
        now = self._now()
        # While a motion burst is recording, sample at the faster burst rate so
        # brief gestures (a blink, a hologram flash while tilting) are captured.
        fps = self.policy.burst_fps if self._burst_active else self.policy.max_fps
        minimum_interval = 1.0 / fps
        if self._last_accept_at is not None and now - self._last_accept_at < minimum_interval:
            return False

        capture = RawCapture(image=image.convert("RGB").copy(), captured_at=now)
        self.latest_raw = capture
        self._last_accept_at = now
        self.accepted_count += 1
        self._new_frame_event.set()
        return True

    async def look(self, *, reason: str, motion: bool = False) -> LookResult:
        del reason  # useful to the LLM/tool trace; sampling itself is reason-agnostic
        now = self._now()
        self._prune_spend(now)
        if self.latest_raw is None:
            return LookResult(images=[], note="(no camera frame available)")

        remaining = self.policy.max_frames_per_min - len(self._spend_timestamps)
        if remaining <= 0:
            fallback = self._last_encoded or self._encode(self.latest_raw)
            return LookResult(
                images=[fallback],
                note="Sampling budget exhausted; using last frame.",
                reused_last_frame=True,
            )

        captures = await self._captures_for_look(motion)
        captures = captures[:remaining]
        encoded = [self._encode(capture) for capture in captures]
        for _frame in encoded:
            self._spend_timestamps.append(now)
            self.images_sent += 1
        self._last_encoded = encoded[-1]
        reused = motion and len({frame.captured_at for frame in encoded}) < len(encoded)
        note = None
        if len(captures) < (self.policy.burst_count if motion else 1):
            note = "Sampling budget reached during motion burst."
        return LookResult(images=encoded, note=note, reused_last_frame=reused)

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, InputImageRawFrame):
            mode = frame.format or "RGB"
            self.accept_image(Image.frombytes(mode, frame.size, frame.image))
            return
        await self.push_frame(frame, direction)

    async def _captures_for_look(self, motion: bool) -> list[RawCapture]:
        if not motion:
            return [self.latest_raw] if self.latest_raw else []
        fallback = self.latest_raw
        captures: list[RawCapture] = []
        loop = asyncio.get_running_loop()
        deadline = loop.time() + (self.policy.burst_window_ms / 1000)
        observed_count = self.accepted_count
        self._new_frame_event.clear()
        self._burst_active += 1
        try:
            while len(captures) < self.policy.burst_count:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    await asyncio.wait_for(self._new_frame_event.wait(), timeout=remaining)
                except TimeoutError:
                    break
                self._new_frame_event.clear()
                if self.accepted_count > observed_count and self.latest_raw is not None:
                    captures.append(self.latest_raw)
                    observed_count = self.accepted_count
        finally:
            self._burst_active -= 1
        if not captures and fallback is not None:
            captures.append(fallback)
        while captures and len(captures) < self.policy.burst_count:
            captures.append(captures[-1])
        return captures

    def _prune_spend(self, now: float) -> None:
        cutoff = now - 60.0
        while self._spend_timestamps and self._spend_timestamps[0] <= cutoff:
            self._spend_timestamps.popleft()

    def _encode(self, capture: RawCapture) -> SampledImage:
        output = capture.image.copy()
        output.thumbnail((self.policy.image_max_side, self.policy.image_max_side))
        buffer = BytesIO()
        output.save(buffer, format="JPEG", quality=self.policy.jpeg_quality, optimize=True)
        return SampledImage(
            jpeg=buffer.getvalue(),
            size=output.size,
            captured_at=capture.captured_at,
        )
