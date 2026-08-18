"""Delivery metrics: arithmetic on timestamps, not audio ML.

`recruit_design_decisions.md` §5 — most of the delivery signal is a sum over word timings,
and that is a feature rather than a limitation. These numbers are deterministic, have zero
run-to-run variance, and are comparable across sessions in a way a model's impression of a
voice never could be. §5 also rules out the alternative permanently: no confidence or
emotion scoring from audio, because it is unreliable and carries documented bias by accent,
gender and first language.

Three rules from §6 shape what is computed and how it is reported.

**Bands, not minima.** Pace, answer length and pause frequency all have an optimal range,
and any display implying lower-is-better trains stilted delivery. Every band here has two
ends. A candidate speaking at 95 wpm and one speaking at 210 both need to know, and they
need to be told opposite things.

**The thinking pause and the stall are different metrics.** A beat before answering is
composure — the candidate who fills it with "that's a great question" is doing worse. A gap
mid-sentence is losing the thread. Same silence, opposite meaning, distinguished only by
position, and lumping them teaches candidates to start talking immediately, which is the
wrong lesson. That distinction is the reason this module classifies pauses at all rather
than counting them.

**Filler is awareness with context, not a target.** Acute self-consciousness typically
raises the count before lowering it, and driving it to zero produces dead delivery. Nothing
here returns a "good/bad" verdict on filler — it returns a rate, a band, and whether it is
high enough to distract.

## The thresholds are provisional

Every number in `Thresholds` is a starting point, not a finding. `recruit_design_decisions.md`
§10 lists the metrics spec — pause classification, band definitions, stall threshold — as an
open item needing a fire captain, and §6 warns that the definitions matter more than they
look. They are gathered in one frozen dataclass so that settling them is one edit in one
place, and so that nothing downstream can quietly hardcode a different opinion.
"""

from dataclasses import dataclass, field

from app.audio.models import CORE_FILLERS, HEDGE_PHRASES, Pause, Transcript, Word


@dataclass(frozen=True)
class Thresholds:
    """Where the lines fall. Provisional — see the module docstring."""

    # A gap a listener notices. Below this is the ordinary rhythm of speech.
    pause_seconds: float = 0.7
    # A gap long enough to read as having lost the thread rather than having paused.
    stall_seconds: float = 2.0
    # An opening beat this long reads as composure; longer starts to read as being stuck.
    opening_beat_max: float = 3.0

    # Bands, both ends. §6: pace sits near 150, answer length roughly one to two minutes.
    pace_wpm: tuple[float, float] = (130.0, 170.0)
    answer_seconds: tuple[float, float] = (60.0, 120.0)

    # Filler per hundred words. The upper end is where it starts to distract rather than
    # where it becomes a fault. **This band is the least evidenced number in the file** —
    # it is a placeholder until it is checked against real answers, and it should not be
    # shown to a candidate as "typical" until it has been.
    filler_per_100: tuple[float, float] = (2.0, 6.0)


DEFAULT = Thresholds()


@dataclass(frozen=True)
class Metric:
    """One measurement, with enough context to be reported without a verdict."""

    name: str
    value: float
    display: str
    band: str | None = None
    within_band: bool | None = None
    note: str | None = None


@dataclass(frozen=True)
class DeliveryMetrics:
    metrics: tuple[Metric, ...]
    pauses: tuple[Pause, ...]
    unclassifiable_pauses: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    def by_name(self, name: str) -> Metric | None:
        for metric in self.metrics:
            if metric.name == name:
                return metric
        return None

    def as_dict(self) -> dict[str, Metric]:
        return {metric.name: metric for metric in self.metrics}


def _band_text(low: float, high: float, unit: str) -> str:
    return f"{low:g}–{high:g} {unit}"


def classify_pauses(transcript: Transcript, thresholds: Thresholds = DEFAULT) -> list[Pause]:
    """Find the gaps and say where each one fell.

    The opening pause is measured from the start of the recording rather than from the
    first word, which is the whole point: a candidate who sat in silence for four seconds
    before speaking did something the transcript alone cannot show.

    Internal gaps are classified by what precedes them. A gap after a full stop is between
    sentences; a gap in the middle of one is the candidate losing his place. Where the
    provider returned no punctuation that distinction cannot be drawn, and the pause is
    marked `unclassified` rather than guessed at — a wrong classification here would tell a
    composed candidate he is falling apart.
    """
    if transcript.is_empty:
        return []

    pauses: list[Pause] = []
    words = transcript.words

    opening = words[0].start
    if opening >= thresholds.pause_seconds:
        pauses.append(Pause(after_index=-1, seconds=opening, kind="opening"))

    for index in range(len(words) - 1):
        gap = words[index + 1].start - words[index].end
        if gap < thresholds.pause_seconds:
            continue
        if not transcript.punctuated:
            kind = "unclassified"
        elif words[index].ends_sentence():
            kind = "between_sentences"
        else:
            kind = "mid_sentence"
        pauses.append(Pause(after_index=index, seconds=gap, kind=kind))

    return pauses


def _count_fillers(words: tuple[Word, ...]) -> tuple[int, int]:
    """Core fillers and multi-word hedges, counted separately.

    Separately because they are different habits with different coaching. "Um" is a vocal
    reflex under load; "you know" is a hedge that invites the panel to fill in the rest of
    the sentence for him.
    """
    normalised = [word.normalised() for word in words]
    core = sum(1 for token in normalised if token in CORE_FILLERS)

    hedges = 0
    for index in range(len(normalised) - 1):
        if (normalised[index], normalised[index + 1]) in HEDGE_PHRASES:
            hedges += 1
    return core, hedges


def compute(transcript: Transcript, thresholds: Thresholds = DEFAULT) -> DeliveryMetrics:
    """Every delivery number, from word timings alone."""
    if transcript.is_empty:
        return DeliveryMetrics(
            metrics=(),
            pauses=(),
            notes=("No words were transcribed — there is nothing to measure.",),
        )

    words = transcript.words
    speaking_span = words[-1].end - words[0].start
    word_count = len(words)
    notes: list[str] = []

    pauses = classify_pauses(transcript, thresholds)
    internal = [p for p in pauses if p.kind != "opening"]
    stalls = [p for p in internal if p.seconds >= thresholds.stall_seconds]

    metrics: list[Metric] = []

    # --- pace ---------------------------------------------------------------
    # Over the speaking span rather than the recording, so a long opening beat does not
    # read as slow speech. They are different findings and get separate lines.
    pace = (word_count / speaking_span * 60) if speaking_span > 0 else 0.0
    low, high = thresholds.pace_wpm
    metrics.append(
        Metric(
            name="pace_wpm",
            value=round(pace, 1),
            display=f"{pace:.0f} words per minute",
            band=_band_text(low, high, "wpm"),
            within_band=low <= pace <= high,
            note=(
                None
                if low <= pace <= high
                else "Slower than most" if pace < low else "Faster than most"
            ),
        )
    )

    # --- length -------------------------------------------------------------
    low, high = thresholds.answer_seconds
    metrics.append(
        Metric(
            name="answer_seconds",
            value=round(transcript.audio_seconds, 1),
            display=f"{transcript.audio_seconds:.0f} seconds",
            band=_band_text(low, high, "seconds"),
            within_band=low <= transcript.audio_seconds <= high,
        )
    )

    # --- the opening beat ---------------------------------------------------
    # Reported as its own thing and never folded into the pause count. §6: a beat before
    # answering is composure, and a display that lumps it with mid-answer gaps teaches a
    # candidate to start talking immediately, which is the wrong lesson.
    opening = words[0].start
    composed = opening <= thresholds.opening_beat_max
    metrics.append(
        Metric(
            name="time_to_first_word",
            value=round(opening, 2),
            display=f"{opening:.1f} seconds before you started",
            band=f"up to {thresholds.opening_beat_max:g} seconds reads as composure",
            within_band=composed,
            note=(
                "A beat before answering is composure, not hesitation."
                if composed
                else "Long enough that it may read as being caught out rather than thinking."
            ),
        )
    )

    # --- pauses within the answer -------------------------------------------
    if not transcript.punctuated:
        notes.append(
            "The provider returned no punctuation, so a pause between sentences cannot be "
            "told from one in the middle of a sentence. Those are opposite signals, so "
            "they are reported together rather than guessed at."
        )

    metrics.append(
        Metric(
            name="pauses_in_answer",
            value=float(len(internal)),
            display=f"{len(internal)} noticeable pause{'s' if len(internal) != 1 else ''}",
            note=(
                None
                if transcript.punctuated
                else "Not split by position — see the note on punctuation."
            ),
        )
    )

    if stalls:
        longest = max(p.seconds for p in stalls)
        metrics.append(
            Metric(
                name="longest_stall",
                value=round(longest, 2),
                display=f"{longest:.1f} seconds",
                note=(
                    f"{len(stalls)} gap{'s' if len(stalls) != 1 else ''} of "
                    f"{thresholds.stall_seconds:g}s or more inside the answer."
                ),
            )
        )

    # --- longest unbroken stretch -------------------------------------------
    # The counterpart to the stall: how long he sustained speech without a gap. A candidate
    # who never pauses is as worth knowing about as one who pauses constantly.
    longest_run, run_start = 0.0, words[0].start
    for index in range(len(words) - 1):
        if words[index + 1].start - words[index].end >= thresholds.pause_seconds:
            longest_run = max(longest_run, words[index].end - run_start)
            run_start = words[index + 1].start
    longest_run = max(longest_run, words[-1].end - run_start)
    metrics.append(
        Metric(
            name="longest_unbroken",
            value=round(longest_run, 2),
            display=f"{longest_run:.0f} seconds without a pause",
        )
    )

    # --- filler -------------------------------------------------------------
    core, hedges = _count_fillers(words)
    rate = core / word_count * 100
    low, high = thresholds.filler_per_100
    metrics.append(
        Metric(
            name="filler_per_100",
            value=round(rate, 1),
            display=f"{rate:.1f} per 100 words ({core} in {word_count})",
            band=_band_text(low, high, "per 100"),
            within_band=low <= rate <= high,
            # No verdict. §6: report the rate, the typical range, and whether it is high
            # enough to distract — driving it to zero produces dead delivery.
            note=(
                "High enough to distract a panel from what you are saying."
                if rate > high
                else "Below the range most speakers sit in."
                if rate < low
                else None
            ),
        )
    )
    if hedges:
        metrics.append(
            Metric(
                name="hedge_phrases",
                value=float(hedges),
                display=f"{hedges} hedge phrase{'s' if hedges != 1 else ''}",
                note='Phrases like "you know" and "I mean", which ask the panel to finish '
                "the thought for you. A different habit from an um, and a different fix.",
            )
        )

    return DeliveryMetrics(
        metrics=tuple(metrics),
        pauses=tuple(pauses),
        unclassifiable_pauses=not transcript.punctuated,
        notes=tuple(notes),
    )
