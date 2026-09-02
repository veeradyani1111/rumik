from __future__ import annotations

import re


TONE_TAGS = ("neutral", "happy", "excited", "sad", "angry", "whisper")
SYSTEM_PROMPT_FRAGMENT = """
Voice output contract:
- Start every paragraph with exactly one supported tone tag: [neutral], [happy],
  [excited], [sad], [angry], or [whisper].
- Keep each paragraph to one to three short sentences.
- Wrap digit strings, including document numbers and dates, in double quotes so
  the voice reads them digit by digit.
- Return plain spoken text only: no markdown, tables, or code fences.
""".strip()

_LEADING_TONE = re.compile(r"^\[(?:" + "|".join(TONE_TAGS) + r")\]\s*", re.IGNORECASE)
_UNQUOTED_DIGITS = re.compile(r'(?<!["\d])\d+(?![\d"])')


def sanitize(text: str, *, force_tone: str | None = None) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"```(?:\w+)?", "", cleaned)
    cleaned = cleaned.replace("`", "").replace("**", "").replace("__", "")
    cleaned = re.sub(r"(?m)^\s*(?:#{1,6}\s+|[-*+]\s+)", "", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned).strip()
    cleaned = _UNQUOTED_DIGITS.sub(lambda match: f'"{match.group(0)}"', cleaned)
    if force_tone:
        if force_tone not in TONE_TAGS:
            raise ValueError(f"unsupported forced tone: {force_tone}")
        cleaned = _LEADING_TONE.sub("", cleaned).lstrip()
        cleaned = f"[{force_tone}] {cleaned}"
    elif not _LEADING_TONE.match(cleaned):
        cleaned = f"[neutral] {cleaned}"
    return cleaned
