"""A failed recruit-audio delete is an ERROR and a row. The sweep finds the rest.

The bucket is private and temporary. delete_audio must not raise — the
critique has often already been stored — but silence is how a recording
outlives the promise to discard it.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.storage.recruit import (
    AUDIO_BUCKET,
    STALE_AUDIO_AFTER,
    delete_audio,
    sweep_stale_recruit_audio,
)

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
OLD = "user-1/attempt-old/answer.webm"
LIVE = "user-1/attempt-live/answer.webm"
YOUNG = "user-1/attempt-young/answer.webm"


def _stamp(hours_old: float) -> str:
    return (NOW - timedelta(hours=hours_old)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _file(name: str, *, hours_old: float, file_id: str = "obj") -> dict:
    return {
        "name": name,
        "id": file_id,
        "created_at": _stamp(hours_old),
        "metadata": {"size": 4},
    }


def _folder(name: str) -> dict:
    return {"name": name, "id": None, "created_at": None, "metadata": None}


class _Bucket:
    def __init__(self, tree: dict[str, list[dict]], remove_error: Exception | None) -> None:
        self.tree = tree
        self.remove_error = remove_error
        self.removed: list[str] = []

    def remove(self, paths: list[str]) -> None:
        if self.remove_error is not None:
            raise self.remove_error
        self.removed.extend(paths)

    def list(self, path: str | None = None, options: dict | None = None) -> list[dict]:
        if self.tree.get("__error__"):
            raise RuntimeError("list failed")
        items = list(self.tree.get(path or "", []))
        opts = options or {}
        offset = int(opts.get("offset", 0))
        limit = int(opts.get("limit", 100))
        return items[offset : offset + limit]


class _Query:
    def __init__(self, db: "MemoryDb", name: str) -> None:
        self.db = db
        self.name = name
        self.op = "select"
        self.payload: dict | None = None
        self.eqs: dict = {}
        self.ins: dict = {}
        self.window: tuple[int, int] | None = None

    def select(self, *_args: object) -> "_Query":
        self.op = "select"
        return self

    def insert(self, row: dict) -> "_Query":
        self.op = "insert"
        self.payload = row
        return self

    def update(self, row: dict) -> "_Query":
        self.op = "update"
        self.payload = row
        return self

    def delete(self) -> "_Query":
        self.op = "delete"
        return self

    def eq(self, col: str, val: object) -> "_Query":
        self.eqs[col] = val
        return self

    def in_(self, col: str, vals: list) -> "_Query":
        self.ins[col] = set(vals)
        return self

    def order(self, *_args: object, **_kwargs: object) -> "_Query":
        return self

    def limit(self, _n: int) -> "_Query":
        return self

    def range(self, start: int, end: int) -> "_Query":
        self.window = (start, end)
        return self

    def execute(self):
        if self.name == self.db.fail_table:
            raise RuntimeError(f"{self.name} unavailable")
        if self.name == "recruit_audio_orphans":
            data = self._orphans()
        elif self.name == "recruit_attempts":
            data = self._attempts()
        else:
            raise AssertionError(self.name)
        return type("R", (), {"data": data})()

    def _orphans(self):
        rows = self.db.orphans
        if self.op == "select":
            path = self.eqs.get("storage_path")
            found = [rows[path]] if path in rows else []
            return found
        if self.op == "insert":
            assert self.payload is not None
            path = self.payload["storage_path"]
            if path in rows:
                raise RuntimeError("duplicate storage_path")
            rows[path] = dict(self.payload)
            return [rows[path]]
        if self.op == "update":
            assert self.payload is not None
            path = self.eqs["storage_path"]
            rows[path].update(self.payload)
            return [rows[path]]
        if self.op == "delete":
            rows.pop(self.eqs.get("storage_path"), None)
            return []
        raise AssertionError(self.op)

    def _attempts(self):
        rows = [
            row
            for row in self.db.attempts
            if not self.ins or row.get("status") in self.ins.get("status", set())
        ]
        if self.window is not None:
            start, end = self.window
            rows = rows[start : end + 1]
        return rows


class MemoryDb:
    def __init__(
        self,
        tree: dict[str, list[dict]] | None = None,
        attempts: list[dict] | None = None,
        remove_error: Exception | None = None,
    ) -> None:
        self.bucket = _Bucket(tree or {}, remove_error)
        self.storage = self
        self.orphans: dict[str, dict] = {}
        self.attempts = attempts or []
        self.fail_table: str | None = None

    def from_(self, name: str) -> _Bucket:
        assert name == AUDIO_BUCKET
        return self.bucket

    def table(self, name: str) -> _Query:
        return _Query(self, name)


def test_delete_failure_logs_and_records(caplog: pytest.LogCaptureFixture) -> None:
    db = MemoryDb(remove_error=RuntimeError("storage\ndown"))
    with caplog.at_level("ERROR"):
        delete_audio(db, OLD)
    assert db.bucket.removed == []
    assert db.orphans[OLD]["reason"] == "delete_failed"
    assert "storage down" in db.orphans[OLD]["error"]
    assert "\n" not in db.orphans[OLD]["error"]
    messages = [record.message for record in caplog.records]
    assert any(
        message.startswith("recruit_audio_delete_failed ") and f"storage_path={OLD}" in message
        for message in messages
    )
    assert all("\n" not in message for message in messages)


def test_a_second_failure_keeps_the_first_seen_time(caplog: pytest.LogCaptureFixture) -> None:
    db = MemoryDb(remove_error=RuntimeError("first"))
    with caplog.at_level("ERROR"):
        delete_audio(db, OLD)
    first_seen = db.orphans[OLD]["first_seen_at"]
    db.bucket.remove_error = RuntimeError("second")
    delete_audio(db, OLD)
    assert db.orphans[OLD]["first_seen_at"] == first_seen
    assert "second" in db.orphans[OLD]["error"]
    assert db.orphans[OLD]["reason"] == "delete_failed"


def test_successful_delete_clears_the_orphan_row() -> None:
    db = MemoryDb(remove_error=RuntimeError("first"))
    delete_audio(db, OLD)
    assert OLD in db.orphans
    db.bucket.remove_error = None
    delete_audio(db, OLD)
    assert db.bucket.removed == [OLD]
    assert db.orphans == {}


def test_delete_without_a_path_does_nothing() -> None:
    db = MemoryDb()
    delete_audio(db, None)
    delete_audio(db, "")
    assert db.bucket.removed == []
    assert db.orphans == {}


def test_record_failure_still_logs_the_delete(caplog: pytest.LogCaptureFixture) -> None:
    db = MemoryDb(remove_error=RuntimeError("storage down"))
    db.fail_table = "recruit_audio_orphans"
    with caplog.at_level("ERROR"):
        delete_audio(db, OLD)
    assert db.orphans == {}
    kinds = [record.message.split()[0] for record in caplog.records]
    assert "recruit_audio_delete_failed" in kinds
    assert "recruit_audio_orphan_record_failed" in kinds


def test_sweep_flags_only_stale_unattached_objects(caplog: pytest.LogCaptureFixture) -> None:
    pads = [
        _file(f"pad-{index:03d}.webm", hours_old=1, file_id=f"pad-{index}") for index in range(100)
    ]
    tree = {
        "": [_folder("user-1")],
        "user-1": [_folder("attempt-old"), _folder("attempt-live"), _folder("attempt-young")],
        "user-1/attempt-old": [
            *pads,
            _file("answer.webm", hours_old=30, file_id="stale"),
            {
                "name": ".emptyFolderPlaceholder",
                "id": "placeholder",
                "created_at": _stamp(100),
                "metadata": {"size": 0},
            },
            {
                "name": "undated.webm",
                "id": "undated",
                "created_at": None,
                "metadata": {"size": 4},
            },
        ],
        "user-1/attempt-live": [_file("answer.webm", hours_old=48, file_id="live")],
        "user-1/attempt-young": [_file("answer.webm", hours_old=2, file_id="young")],
    }
    db = MemoryDb(
        tree,
        attempts=[
            {"status": "running", "audio_storage_path": LIVE},
            {"status": "completed", "audio_storage_path": OLD},
        ],
    )
    with caplog.at_level("ERROR"):
        stale = sweep_stale_recruit_audio(db, now=NOW)
    assert set(stale) == {OLD, "user-1/attempt-old/undated.webm"}
    assert set(db.orphans) == set(stale)
    assert all(row["reason"] == "stale_unattached" for row in db.orphans.values())
    messages = [record.message for record in caplog.records]
    assert any(f"storage_path={OLD}" in message for message in messages)
    assert any("recruit_audio_orphan_count count=2" in message for message in messages)
    assert not any(LIVE in message for message in messages)
    assert not any("attempt-young" in message for message in messages)
    assert not any("emptyFolderPlaceholder" in message for message in messages)


def test_an_object_exactly_at_the_age_threshold_is_kept() -> None:
    path = "user-1/attempt/answer.webm"
    created = (NOW - STALE_AUDIO_AFTER).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    db = MemoryDb(
        {
            "": [_folder("user-1")],
            "user-1": [_folder("attempt")],
            "user-1/attempt": [
                {"name": "answer.webm", "id": "edge", "created_at": created, "metadata": {}}
            ],
        }
    )
    assert sweep_stale_recruit_audio(db, now=NOW) == []
    assert path not in db.orphans


def test_sweep_does_not_invent_orphans_when_listing_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    db = MemoryDb(tree={"__error__": [{"name": "x"}]})
    with caplog.at_level("ERROR"):
        assert sweep_stale_recruit_audio(db, now=NOW) == []
    assert db.orphans == {}
    assert any(record.message == "recruit_audio_sweep_failed" for record in caplog.records)


def test_sweep_does_not_invent_orphans_when_attempts_cannot_be_read(
    caplog: pytest.LogCaptureFixture,
) -> None:
    db = MemoryDb(
        {
            "": [_file("left-behind.webm", hours_old=48, file_id="left")],
        }
    )
    db.fail_table = "recruit_attempts"
    with caplog.at_level("ERROR"):
        assert sweep_stale_recruit_audio(db, now=NOW) == []
    assert db.orphans == {}
    assert any(record.message == "recruit_audio_sweep_failed" for record in caplog.records)


def test_migration_locks_the_orphan_table() -> None:
    body = "\n".join(
        line.strip()
        for line in (ROOT / "supabase/migrations/0019_recruit_audio_orphans.sql")
        .read_text()
        .splitlines()
        if line.strip() and not line.strip().startswith("--")
    ).lower()
    assert "create table public.recruit_audio_orphans" in body
    assert "alter table public.recruit_audio_orphans enable row level security" in body
    assert "revoke all on table public.recruit_audio_orphans from public" in body
    assert "revoke all on table public.recruit_audio_orphans from anon" in body
    assert "revoke all on table public.recruit_audio_orphans from authenticated" in body
    assert "create policy" not in body
    assert "grant " not in body
    assert "security definer" not in body


def test_worker_runs_the_sweep_on_its_schedule_and_on_once() -> None:
    source = (ROOT / "app/worker/runner.py").read_text()
    assert "RECRUIT_AUDIO_SWEEP_EVERY = 60 * 60" in source
    assert source.count("_sweep_recruit_audio(db)") == 2
