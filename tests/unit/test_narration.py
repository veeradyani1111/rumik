from sdk.server.narration import NarrationAcks, normalize_line


def test_normalize_strips_emotion_tag_and_whitespace() -> None:
    assert normalize_line("[happy]  Now tilt it   slowly. ") == "now tilt it slowly."
    assert normalize_line("Now tilt it slowly.") == "now tilt it slowly."


def test_page_line_is_acked_only_after_its_audio_drains() -> None:
    acks = NarrationAcks()
    acks.request("n1", "Now tilt it slowly side to side.")
    # The model's own sentence plays first - it must not be mistaken for the page line.
    assert acks.on_tts_text("[happy] Lovely, the hologram checked out.") is None
    assert acks.on_bot_stopped() == []
    # Then the page line is synthesized (Rumik adds its own tag) and finishes playing.
    assert acks.on_tts_text("[neutral] Now tilt it slowly side to side.") == "n1"
    assert acks.on_bot_stopped() == ["n1"]
    assert acks.on_bot_stopped() == []
    assert acks.outstanding == 0


def test_identical_lines_are_acked_in_request_order() -> None:
    acks = NarrationAcks()
    acks.request("a", "Got it - one moment.")
    acks.request("b", "Got it - one moment.")
    assert acks.on_tts_text("Got it - one moment.") == "a"
    assert acks.on_bot_stopped() == ["a"]
    assert acks.on_tts_text("Got it - one moment.") == "b"
    assert acks.on_bot_stopped() == ["b"]


def test_requests_without_id_or_text_are_ignored() -> None:
    acks = NarrationAcks()
    acks.request("", "hello")
    acks.request("x", "")
    assert acks.outstanding == 0
