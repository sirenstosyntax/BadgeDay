"""Delivery metrics: the arithmetic, and the two places it must refuse to guess.

`recruit_design_decisions.md` §5 makes these numbers the trustworthy half of the audio
feature precisely because they are deterministic — so they need to be right in the boring
sense, and the tests here assert against figures worked out by hand rather than against
whatever the code produced first.

Two behaviours matter more than the arithmetic and are tested hardest.

The opening beat is never counted as a pause in the answer. §6: a beat before answering is
composure and a gap mid-answer is losing the thread, and a display that lumps them teaches
a candidate to start talking immediately, which is the wrong lesson.

An unpunctuated transcript reports its pauses as unclassified rather than assigning them.
Telling a composed candidate he is falling apart, on the strength of a distinction the
provider did not give us, is the exact failure this module exists inside a product to
avoid.
"""

import dataclasses

import pytest

from app.audio.metrics import DEFAULT, Thresholds, classify_pauses, compute
from app.audio.models import Transcript, Word
from app.audio.transcriber import synthetic

TEN_WORDS = "so we had a call and I got there first"  # exactly ten, and the tests count on it


# --- pace --------------------------------------------------------------------


def test_pace_is_measured_over_speech_not_over_the_recording() -> None:
    """A long silence before speaking is its own finding, not evidence of slow speech.

    Folding it into pace would report a composed candidate who took his moment as someone
    who talks slowly — two different things needing two different conversations.
    """
    quick = synthetic(TEN_WORDS, wpm=150, opening=6.0)
    pace = compute(quick).by_name("pace_wpm")
    assert pace is not None
    assert pace.value == pytest.approx(150, abs=1)


@pytest.mark.parametrize(
    ("wpm", "within"),
    [(100, False), (135, True), (150, True), (168, True), (200, False)],
)
def test_pace_reports_a_band_with_two_ends(wpm: float, within: bool) -> None:
    """Bands, not minima. Lower-is-better on pace would train stilted delivery."""
    pace = compute(synthetic(TEN_WORDS, wpm=wpm)).by_name("pace_wpm")
    assert pace.within_band is within
    assert pace.band is not None


def test_too_fast_and_too_slow_are_told_apart() -> None:
    fast = compute(synthetic(TEN_WORDS, wpm=210)).by_name("pace_wpm")
    slow = compute(synthetic(TEN_WORDS, wpm=90)).by_name("pace_wpm")
    assert "Faster" in fast.note
    assert "Slower" in slow.note


# --- the opening beat is not a pause in the answer ---------------------------


def test_the_opening_beat_is_reported_separately_from_pauses() -> None:
    transcript = synthetic(TEN_WORDS, opening=2.5)
    result = compute(transcript)
    assert result.by_name("time_to_first_word").value == pytest.approx(2.5)
    assert result.by_name("pauses_in_answer").value == 0


def test_a_beat_before_answering_is_reported_as_composure() -> None:
    beat = compute(synthetic(TEN_WORDS, opening=2.0)).by_name("time_to_first_word")
    assert beat.within_band is True
    assert "composure" in beat.note


def test_a_very_long_opening_is_not_called_composure() -> None:
    stuck = compute(synthetic(TEN_WORDS, opening=9.0)).by_name("time_to_first_word")
    assert stuck.within_band is False
    assert "composure" not in stuck.note


def test_an_opening_pause_never_appears_among_the_answer_pauses() -> None:
    pauses = classify_pauses(synthetic(TEN_WORDS, opening=4.0))
    assert [p.kind for p in pauses] == ["opening"]
    assert pauses[0].after_index == -1


# --- pauses inside the answer ------------------------------------------------


def test_gaps_below_the_threshold_are_the_ordinary_rhythm_of_speech() -> None:
    assert classify_pauses(synthetic(TEN_WORDS, gaps={3: 0.3})) == []


def test_a_real_gap_is_found_and_located() -> None:
    pauses = classify_pauses(synthetic(TEN_WORDS, gaps={4: 1.5}))
    assert len(pauses) == 1
    assert pauses[0].after_index == 4
    assert pauses[0].seconds == pytest.approx(1.5)


def test_a_long_gap_is_reported_as_a_stall() -> None:
    stall = compute(synthetic(TEN_WORDS, gaps={5: 3.0})).by_name("longest_stall")
    assert stall is not None
    assert stall.value == pytest.approx(3.0)


def test_an_answer_without_stalls_reports_none_rather_than_zero() -> None:
    """Absence of a stall is not a measurement of zero seconds; the line is simply absent."""
    assert compute(synthetic(TEN_WORDS)).by_name("longest_stall") is None


# --- the refusal to guess ----------------------------------------------------


def test_without_punctuation_pauses_are_unclassified_rather_than_assigned() -> None:
    """A gap between sentences and one mid-sentence are opposite signals.

    A provider that returns no punctuation has not given us the distinction, and inventing
    it would tell a composed candidate he is losing the thread.
    """
    pauses = classify_pauses(synthetic(TEN_WORDS, gaps={4: 1.2}, punctuated=False))
    assert [p.kind for p in pauses] == ["unclassified"]


def test_the_unpunctuated_case_says_so_out_loud() -> None:
    result = compute(synthetic(TEN_WORDS, gaps={4: 1.2}, punctuated=False))
    assert result.unclassifiable_pauses is True
    assert any("punctuation" in note for note in result.notes)


def test_with_punctuation_a_gap_after_a_full_stop_is_between_sentences() -> None:
    words = (
        Word("So", 0.0, 0.3),
        Word("we", 0.3, 0.5),
        Word("rolled.", 0.5, 1.0),
        Word("Then", 2.5, 2.8),
        Word("dispatch", 2.8, 3.3),
        Word("called.", 3.3, 3.8),
    )
    transcript = Transcript(words=words, audio_seconds=3.8, punctuated=True)
    assert [p.kind for p in classify_pauses(transcript)] == ["between_sentences"]


def test_with_punctuation_a_gap_mid_sentence_is_the_thread_being_lost() -> None:
    words = (
        Word("So", 0.0, 0.3),
        Word("we", 0.3, 0.5),
        Word("rolled", 0.5, 1.0),
        Word("and", 3.0, 3.2),
        Word("then", 3.2, 3.5),
    )
    transcript = Transcript(words=words, audio_seconds=3.5, punctuated=True)
    assert [p.kind for p in classify_pauses(transcript)] == ["mid_sentence"]


# --- filler ------------------------------------------------------------------


def test_filler_is_counted_as_a_rate_not_a_total() -> None:
    """A rate is comparable across answers of different lengths; a count is not."""
    spoken = "um so we had a call uh and I got there first um yes"
    metric = compute(synthetic(spoken)).by_name("filler_per_100")
    assert metric.value == pytest.approx(3 / 14 * 100, abs=0.1)


def test_filler_reports_a_range_and_never_a_verdict() -> None:
    """§6: driving filler to zero produces dead delivery, so nothing here says 'good'."""
    metric = compute(synthetic("um so uh we um had uh a um call uh")).by_name("filler_per_100")
    assert metric.band is not None
    assert "distract" in metric.note
    assert "good" not in (metric.note or "").lower()


def test_an_answer_with_no_filler_is_not_praised_for_it() -> None:
    metric = compute(synthetic(TEN_WORDS)).by_name("filler_per_100")
    assert metric.value == 0
    assert "Below the range" in metric.note


def test_ordinary_words_are_not_counted_as_filler() -> None:
    """"Like" and "actually" do real work in speech.

    Counting them would inflate the rate with false positives, and a candidate who cannot
    recognise the number as his own concludes the tool is wrong about him — and then stops
    believing the rest of it.
    """
    spoken = "a call like that one actually arrived first so we basically rolled"
    assert compute(synthetic(spoken)).by_name("filler_per_100").value == 0


def test_hedge_phrases_are_counted_apart_from_vocal_filler() -> None:
    """Different habit, different coaching. An um is a reflex; 'you know' asks the panel
    to finish the sentence for him."""
    spoken = "so you know we rolled and I mean it was fine you know"
    result = compute(synthetic(spoken))
    assert result.by_name("hedge_phrases").value == 3
    assert result.by_name("filler_per_100").value == 0


# --- edges -------------------------------------------------------------------


def test_an_empty_transcript_measures_nothing_rather_than_zero() -> None:
    """Silence is not a pace of zero. It is the absence of a measurement, and reporting
    numbers for it would put a fabricated row in front of a candidate."""
    result = compute(Transcript(words=(), audio_seconds=12.0))
    assert result.metrics == ()
    assert any("nothing to measure" in note for note in result.notes)


def test_a_single_word_answer_does_not_divide_by_zero() -> None:
    words = (Word("Yes.", 1.0, 1.4),)
    result = compute(Transcript(words=words, audio_seconds=1.4, punctuated=True))
    assert result.by_name("pace_wpm") is not None


def test_the_longest_unbroken_stretch_is_measured_between_pauses() -> None:
    transcript = synthetic(TEN_WORDS, wpm=60, gaps={2: 2.0})
    # Ten words at 60 wpm is 1s each; the gap after word 2 splits it 3 words / 7 words.
    assert compute(transcript).by_name("longest_unbroken").value == pytest.approx(7.0, abs=0.1)


def test_thresholds_are_one_frozen_object_so_settling_them_is_one_edit() -> None:
    """The metrics spec is an open item needing a fire captain. Nothing downstream should
    be able to hold a different opinion about where a stall begins."""
    assert isinstance(DEFAULT, Thresholds)
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFAULT.stall_seconds = 5.0  # type: ignore[misc]
