"""Confirm to the page when a line it asked the agent to speak has actually been heard.

The page narrates capture steps ("put the card in the box", "now tilt it") by asking
the worker to speak fixed lines. Those lines are queued behind whatever the agent is
already saying, so the moment a line is REQUESTED can be many seconds before the
moment it is HEARD. A capture step that starts its timer on the request runs ahead of
the person (seen live: the liveness recording finished before "look at the camera"
had played). This tracker pairs each requested line with the TTS text frame that
synthesizes it and the bot-stopped-speaking event that follows, so the worker can
send the page a "spoken" acknowledgement at the right instant.

Pure bookkeeping, no I/O - the pipeline feeds it frames and sends the acks.
"""

from __future__ import annotations

import re

_LEADING_TAG = re.compile(r"^\s*\[[^\]]{1,32}\]\s*")
_SPACES = re.compile(r"\s+")


def normalize_line(text: str) -> str:
    """Strip a leading emotion tag ("[happy] ") and collapse whitespace/case."""
    return _SPACES.sub(" ", _LEADING_TAG.sub("", str(text or ""))).strip().casefold()


class NarrationAcks:
    def __init__(self) -> None:
        self._pending: list[tuple[str, str]] = []  # (id, normalized text), in request order
        self._playing: list[str] = []  # ids whose audio is playing (or queued right behind)

    def request(self, speak_id: str, text: str) -> None:
        """A page line was queued for TTS under this id."""
        if speak_id and text:
            self._pending.append((speak_id, normalize_line(text)))

    def on_tts_text(self, text: str) -> str | None:
        """TTS began synthesizing `text`; returns the matched id, if it was a page line."""
        wanted = normalize_line(text)
        for index, (speak_id, line) in enumerate(self._pending):
            if line == wanted:
                del self._pending[index]
                self._playing.append(speak_id)
                return speak_id
        return None

    def on_bot_stopped(self) -> list[str]:
        """The bot's audio drained: every line that was playing has now been heard."""
        ids, self._playing = self._playing, []
        return ids

    @property
    def outstanding(self) -> int:
        return len(self._pending) + len(self._playing)
