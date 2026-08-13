"""The review set's own integrity.

The answers are calibration fixtures, and `probes` is the record of what each one is for.
That record is printed by `scripts/recruit_review_compare.py` under *"written to probe"*
beside every divergence, so a stale reference does not fail loudly — it aims a reader at
the wrong clause while looking authoritative.

Which is what happened. The 2026-07-29 rewrite inserted two scoring notes above the old
note 3 and every reference below them went off by one, undetected until 2026-08-10.
"""

import re
from pathlib import Path

from app.critique import rubric as rubric_module
from app.critique.review_set import ANSWERS, QUESTION

# "note.5 — ...", "anchor.4B, second attempt", "anchor.4 boundary — ..."
_CLAUSE_REF = re.compile(r"\b(note|anchor)\.(\d+[AB]?)\b")


def test_every_probe_reference_resolves_against_the_real_rubric():
    """The guard on the failure above. Catches a renumbering; cannot catch a swap.

    A shifted reference usually lands on a clause that still exists — `note.4` was a real
    clause the whole time, just the wrong one — so this test only fires when a reference
    shifts off the end of the catalogue. It is worth having anyway: it makes the class of
    error visible at all, and it fails loudly the moment a note is deleted or a route
    retired. Reading the probe text against the clause it names is still a human job.
    """
    root = Path(__file__).resolve().parents[1]
    ids = rubric_module.load("c3", root=root).clause_ids

    for answer in ANSWERS:
        for kind, number in _CLAUSE_REF.findall(answer.probes):
            clause_id = f"c3.{kind}.{number}"
            assert clause_id in ids, (
                f"answer {answer.ref} probes {clause_id}, which is not a clause in c3"
            )


def test_the_two_notes_that_went_stale_point_where_their_prose_says():
    """Pinned by ref, because the generic test above could not have caught this.

    E is the unfalsifiable-claim fixture and H is the no-team-history one. Both named a
    clause that existed and described a different one. Pinning the pairing is the only thing
    that holds them together, since nothing derives one from the other.
    """
    root = Path(__file__).resolve().parents[1]
    rubric = rubric_module.load("c3", root=root)
    by_ref = {answer.ref: answer for answer in ANSWERS}

    assert "note.5" in by_ref["E"].probes
    assert "teammate" in rubric.clause("c3.note.5").label.lower()

    assert "note.4" in by_ref["H"].probes
    assert "no team history" in rubric.clause("c3.note.4").label.lower()


def test_refs_are_unique_and_the_question_is_the_one_the_answers_answer():
    refs = [answer.ref for answer in ANSWERS]
    assert len(set(refs)) == len(refs)
    assert QUESTION.strip()
    assert all(answer.transcript.strip() and answer.probes.strip() for answer in ANSWERS)
