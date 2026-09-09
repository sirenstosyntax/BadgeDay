"""The worker's failure behaviour.

The happy path is the least interesting thing here — it is four function calls in a row,
and the live smoke test covers it end to end. What these tests pin down is what happens
when a job dies, because that is where a queue either recovers or quietly strands a
candidate's document at 'analyzing' forever.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.config import Settings
from app.worker.jobs import RETRY_DELAYS, Job, claim, fail, succeed
from app.worker.pipeline import AttemptGone, DocumentGone, EmptyRecruitAudio
from app.worker.runner import run_one

SETTINGS = Settings(supabase_url="https://x.supabase.co", supabase_anon_key="k")
DOC = "22222222-2222-2222-2222-222222222222"
ATT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def job(**overrides) -> Job:
    return Job.model_validate(
        {
            "id": "job-1",
            "kind": "ingest",
            "document_id": DOC,
            "status": "running",
            "attempts": 1,
            "max_attempts": 3,
            **overrides,
        }
    )


class FakeTable:
    def __init__(self, log: list, name: str, rows: list) -> None:
        self.log, self.name, self.rows = log, name, rows
        self._patch: dict = {}

    def update(self, patch: dict) -> "FakeTable":
        self._patch = patch
        return self

    def insert(self, row: dict) -> "FakeTable":
        self.log.append(("insert", self.name, row))
        return self

    def delete(self) -> "FakeTable":
        self._patch = {"__delete__": True}
        return self

    def select(self, *_: str) -> "FakeTable":
        return self

    def eq(self, *_: object) -> "FakeTable":
        return self

    def lt(self, *_: object) -> "FakeTable":
        return self

    def order(self, *_: object, **__: object) -> "FakeTable":
        return self

    def limit(self, _: int) -> "FakeTable":
        return self

    def execute(self):
        if self._patch:
            self.log.append(("update", self.name, self._patch))
            self._patch = {}
        return type("R", (), {"data": self.rows})()


class FakeDb:
    def __init__(self, claimed: list | None = None) -> None:
        self.log: list = []
        self.claimed = claimed if claimed is not None else []
        self.tables: dict[str, FakeTable] = {}

    def table(self, name: str) -> FakeTable:
        return self.tables.setdefault(name, FakeTable(self.log, name, []))

    def rpc(self, name: str, params: dict) -> "FakeDb":
        assert name == "claim_job"
        self._rpc = self.claimed.pop(0) if self.claimed else []
        return self

    def execute(self):
        return type("R", (), {"data": self._rpc})()

    def updates(self, table: str) -> list[dict]:
        return [entry[2] for entry in self.log if entry[0] == "update" and entry[1] == table]


# --- Claiming ----------------------------------------------------------------


def test_an_empty_queue_claims_nothing() -> None:
    assert claim(FakeDb(claimed=[[]]), "w1") is None


def test_a_claimed_row_becomes_a_job() -> None:
    row = {
        "id": "job-9",
        "kind": "generate",
        "document_id": DOC,
        "status": "running",
        "attempts": 1,
        "max_attempts": 3,
    }
    claimed = claim(FakeDb(claimed=[[row]]), "w1")
    assert claimed is not None
    assert claimed.kind == "generate"


# --- Retry policy ------------------------------------------------------------


def test_a_first_failure_is_requeued_with_a_delay() -> None:
    db = FakeDb()
    assert fail(db, job(attempts=1), "boom") is True

    patch = db.updates("jobs")[0]
    assert patch["status"] == "queued"
    assert patch["locked_by"] is None
    run_after = datetime.fromisoformat(patch["run_after"])
    assert run_after > datetime.now(UTC) + RETRY_DELAYS[0] - timedelta(seconds=5)


def test_the_backoff_lengthens_with_each_attempt() -> None:
    delays = []
    for attempt in (1, 2, 3):
        db = FakeDb()
        fail(db, job(attempts=attempt, max_attempts=9), "boom")
        run_after = datetime.fromisoformat(db.updates("jobs")[0]["run_after"])
        delays.append(run_after - datetime.now(UTC))
    assert delays[0] < delays[1] < delays[2]


def test_the_last_attempt_is_terminal() -> None:
    db = FakeDb()
    assert fail(db, job(attempts=3, max_attempts=3), "boom") is False
    assert db.updates("jobs")[0]["status"] == "failed"


def test_an_enormous_error_is_truncated_before_storage() -> None:
    db = FakeDb()
    fail(db, job(attempts=3, max_attempts=3), "x" * 50_000)
    assert len(db.updates("jobs")[0]["last_error"]) == 2000


def test_success_clears_a_previous_error() -> None:
    """A job that failed once and then succeeded must not keep its old error, or the
    document carries a scary message that no longer describes anything."""
    db = FakeDb()
    succeed(db, job(attempts=2))
    patch = db.updates("jobs")[0]
    assert patch == {"status": "succeeded", "last_error": None}


# --- The runner's decision ---------------------------------------------------


def _run(db: FakeDb, handler, monkeypatch: pytest.MonkeyPatch) -> bool:
    monkeypatch.setattr("app.worker.runner.HANDLERS", {"ingest": handler})
    return run_one(db, SETTINGS, "w1")


def _claimable(**overrides) -> FakeDb:
    return FakeDb(claimed=[[job(**overrides).model_dump()]])


def test_an_idle_queue_reports_nothing_done(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeDb(claimed=[[]])
    assert _run(db, lambda *a: None, monkeypatch) is False


def test_a_retryable_failure_leaves_the_document_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """The document really is still in progress, and a candidate should not watch it flip
    to failed and back to analyzing while we quietly try again."""

    def explode(*_: object) -> None:
        raise RuntimeError("Azure hiccup")

    db = _claimable(attempts=1)
    _run(db, explode, monkeypatch)

    assert db.updates("jobs")[0]["status"] == "queued"
    assert db.updates("documents") == []


def test_the_final_failure_tells_the_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*_: object) -> None:
        raise RuntimeError("still broken")

    db = _claimable(attempts=3, max_attempts=3)
    _run(db, explode, monkeypatch)

    assert db.updates("jobs")[0]["status"] == "failed"
    document_patch = db.updates("documents")[0]
    assert document_patch["status"] == "failed"
    assert "Try uploading it again" in document_patch["error"]


def test_a_deleted_document_is_not_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """The candidate deleted it while the job sat in the queue. The cascade already took
    the row; retrying three times and then reporting an error would be theatre."""

    def gone(*_: object) -> None:
        raise DocumentGone(DOC)

    db = _claimable()
    _run(db, gone, monkeypatch)

    assert db.updates("jobs")[0]["status"] == "succeeded"
    assert db.updates("documents") == []


def test_a_successful_job_is_marked_and_the_document_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The handler owns the document's status; the runner only records the job."""
    db = _claimable()
    assert _run(db, lambda *a: None, monkeypatch) is True
    assert db.updates("jobs")[0]["status"] == "succeeded"
    assert db.updates("documents") == []


def test_a_deleted_attempt_is_not_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def gone(*_: object) -> None:
        raise AttemptGone(ATT)

    db = _claimable(kind="recruit_critique", document_id=None, attempt_id=ATT)
    monkeypatch.setattr("app.worker.runner.HANDLERS", {"recruit_critique": gone})
    assert run_one(db, SETTINGS, "w1") is True
    assert db.updates("jobs")[0]["status"] == "succeeded"
    assert db.updates("documents") == []


def test_empty_recruit_audio_marks_the_attempt_and_succeeds_the_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def empty(*_: object) -> None:
        raise EmptyRecruitAudio(ATT, "There was not enough in that recording to make a transcript.")

    db = _claimable(kind="recruit_critique", document_id=None, attempt_id=ATT)
    monkeypatch.setattr("app.worker.runner.HANDLERS", {"recruit_critique": empty})
    monkeypatch.setattr("app.worker.runner.get_attempt", lambda *_: None)
    monkeypatch.setattr("app.worker.runner.delete_audio", lambda *_: None)
    assert run_one(db, SETTINGS, "w1") is True
    assert db.updates("jobs")[0]["status"] == "succeeded"
    assert db.updates("recruit_attempts")[0]["status"] == "critique_failed"
    assert db.updates("documents") == []


def test_the_final_recruit_failure_marks_the_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(*_: object) -> None:
        raise RuntimeError("still broken")

    db = _claimable(
        kind="recruit_critique",
        document_id=None,
        attempt_id=ATT,
        attempts=3,
        max_attempts=3,
    )
    monkeypatch.setattr("app.worker.runner.HANDLERS", {"recruit_critique": explode})
    monkeypatch.setattr("app.worker.runner.get_attempt", lambda *_: None)
    monkeypatch.setattr("app.worker.runner.delete_audio", lambda *_: None)
    run_one(db, SETTINGS, "w1")

    assert db.updates("jobs")[0]["status"] == "failed"
    assert db.updates("recruit_attempts")[0]["status"] == "critique_failed"
    assert db.updates("documents") == []
