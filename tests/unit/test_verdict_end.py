from sdk.server.verdict_end import VerdictEnd


def test_first_sentence_gap_does_not_end_the_call() -> None:
    """Sentence-streamed verdict: "…you're verified." <gap> "Thank you, goodbye!"."""
    v = VerdictEnd()
    assert v.on_response_start() is True
    assert v.on_response_start() is False
    v.on_response_end()  # the model finished writing both sentences quickly
    # Sentence 1 synthesized and played.
    assert v.on_tts_started() is False
    v.on_bot_started()
    v.on_tts_stopped()
    assert v.on_bot_stopped() is True  # looks quiet: a tail timer would start here
    gen = v.gen
    # …but sentence 2 starts within the tail: the pending end must be abandoned.
    v.on_tts_started()
    assert v.still_quiet(gen) is False
    v.on_bot_started()
    v.on_tts_stopped()
    assert v.on_bot_stopped() is True
    assert v.still_quiet(v.gen) is True  # nothing followed: now the call may end


def test_not_ready_before_the_response_has_fully_generated_or_while_tts_runs() -> None:
    v = VerdictEnd()
    v.on_response_start()
    v.on_tts_started()
    v.on_bot_started()
    v.on_tts_stopped()
    assert v.on_bot_stopped() is False  # response still generating (long verdict)
    assert v.on_response_end() is True  # generation done and nothing playing -> ready
    v.on_tts_started()  # another sentence begins synthesizing
    assert v.ready() is False
    v.on_tts_stopped()
    assert v.ready() is True


def test_nothing_spoken_is_never_ready_and_reveal_when_queued_behind_speech() -> None:
    v = VerdictEnd()
    v.on_response_start()
    assert v.on_response_end() is False  # no sentence was ever synthesized
    # "let me check…" is still playing when the verdict's TTS begins: reveal now.
    v.on_bot_started()
    assert v.on_tts_started() is True
