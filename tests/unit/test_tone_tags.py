from sdk.server.tone_tags import SYSTEM_PROMPT_FRAGMENT, sanitize


def test_sanitize_adds_default_tone_and_removes_markdown() -> None:
    assert sanitize("**Your result** is ready.") == "[neutral] Your result is ready."


def test_sanitize_preserves_supported_leading_tone() -> None:
    assert sanitize("[happy] Great news!") == "[happy] Great news!"


def test_sanitize_quotes_unquoted_digit_sequences_for_speech() -> None:
    text = sanitize("[neutral] PAN digits are 1234 and DOB is 30/08/2000.")

    assert '"1234"' in text
    assert '"30"/"08"/"2000"' in text


def test_sanitize_does_not_double_quote_existing_digits() -> None:
    assert sanitize('[neutral] Say "1234".') == '[neutral] Say "1234".'


def test_system_prompt_explains_tone_and_plain_text_contract() -> None:
    assert "[neutral]" in SYSTEM_PROMPT_FRAGMENT
    assert "no markdown" in SYSTEM_PROMPT_FRAGMENT.lower()
