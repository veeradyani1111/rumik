"""Decide when the spoken verdict has FULLY played so the call may end.

The verdict is the model's response right after the final tool result. It is now
spoken sentence by sentence (TTS streaming), so a single "TTS stopped" or "bot
stopped speaking" no longer means the verdict is over - it may just be the gap
before the next sentence. Seen live: the call ended after "…you're verified." and
cut off "Thank you for your time, goodbye!".

The rule here: the call may end only when
  1. the verdict response has both started AND finished generating,
  2. at least one sentence was synthesized and none is still being synthesized,
  3. the bot is not speaking,
  4. and nothing new started speaking for a quiet tail (``TAIL_SEC``) after that -
     ``gen`` changes whenever speech (re)starts, so a pending end is abandoned.

Pure state machine, no I/O: the pipeline feeds it frames and owns the timer.
"""

from __future__ import annotations


class VerdictEnd:
    # Covers the ~0.35s between one sentence's audio draining and the next sentence's
    # synthesis starting, plus the browser's own playout buffer.
    TAIL_SEC = 1.5

    def __init__(self) -> None:
        self.response_started = False
        self.response_ended = False
        self.tts_open = 0  # sentences being synthesized right now
        self.tts_seen = 0  # sentences synthesized since the verdict response began
        self.bot_speaking = False
        self.gen = 0  # bumps whenever speech (re)starts; invalidates a pending end

    # --- events ------------------------------------------------------------
    def on_response_start(self) -> bool:
        """Returns True the first time (the verdict response has begun)."""
        if self.response_started:
            return False
        self.response_started = True
        return True

    def on_response_end(self) -> bool:
        self.response_ended = True
        return self.ready()

    def on_tts_started(self) -> bool:
        """Returns True when the verdict audio is queued behind speech already
        playing - the on-screen result should be revealed now rather than never."""
        self.tts_open += 1
        self.tts_seen += 1
        self.gen += 1
        return self.bot_speaking

    def on_tts_stopped(self) -> None:
        self.tts_open = max(0, self.tts_open - 1)

    def on_bot_started(self) -> None:
        self.bot_speaking = True
        self.gen += 1

    def on_bot_stopped(self) -> bool:
        self.bot_speaking = False
        return self.ready()

    # --- decisions ---------------------------------------------------------
    def ready(self) -> bool:
        """Everything generated and nothing playing: a quiet tail may now begin."""
        return (
            self.response_started
            and self.response_ended
            and self.tts_seen > 0
            and self.tts_open == 0
            and not self.bot_speaking
        )

    def still_quiet(self, gen: int) -> bool:
        """After the tail: end only if no speech (re)started meanwhile."""
        return gen == self.gen and self.ready()
