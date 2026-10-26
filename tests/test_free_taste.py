"""Promote's free document: what it may cost, and the schema that decides who gets one.

The database decides whether an upload is the free one (migration 0019). The worker
decides what that document costs: only its first pages are read, and only a handful of
questions are written. These tests pin the worker's half with fakes, and read the
migration for the shape of the database's half — the behaviour itself was exercised
against Postgres 16 when the migration was written (see the pull request).
"""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.ingest.models import AnalyzedBlock, AnalyzedDocument
from app.worker import pipeline
from app.worker.jobs import Job

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "0019_promote_free_taste.sql"

DOC = "22222222-2222-2222-2222-222222222222"
SETTINGS = Settings(
    supabase_url="https://x.supabase.co",
    supabase_anon_key="k",
    anthropic_api_key="sk-test",
    promote_free_taste_pages=3,
    promote_free_taste_questions=4,
)


def _job(kind: str) -> Job:
    return Job.model_validate(
        {
            "id": "job-1",
            "kind": kind,
            "document_id": DOC,
            "status": "running",
            "attempts": 1,
            "max_attempts": 3,
        }
    )


def _document() -> SimpleNamespace:
    return SimpleNamespace(id=DOC, filename="list.pdf", storage_path=f"u/{DOC}/list.pdf")


class _Storage:
    def from_(self, _bucket: str) -> "_Storage":
        return self

    def download(self, _path: str) -> bytes:
        return b"%PDF-"


class _Db:
    storage = _Storage()


# --- Ingest: the page cap ---------------------------------------------------------------


class _RecordingAnalyzer:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def analyze(self, path: Path, **options: object) -> AnalyzedDocument:
        self.calls.append(options)
        return AnalyzedDocument(
            source_name=path.name,
            page_count=1,
            blocks=[AnalyzedBlock(text="Purpose", page=1, role=None)],
        )


def _ingest(monkeypatch: pytest.MonkeyPatch, *, free: bool) -> _RecordingAnalyzer:
    analyzer = _RecordingAnalyzer()
    monkeypatch.setattr(pipeline, "_document", lambda *_: _document())
    monkeypatch.setattr(pipeline, "set_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(pipeline, "is_free_taste_document", lambda *_: free)
    monkeypatch.setattr(pipeline, "get_analyzer", lambda *_: analyzer)
    monkeypatch.setattr(pipeline, "chunk_document", lambda *_: [])
    monkeypatch.setattr(pipeline, "save_chunks", lambda *_: 0)
    monkeypatch.setattr(pipeline, "record_page_count", lambda *_: None)
    monkeypatch.setattr(pipeline, "enqueue", lambda *_: None)
    pipeline.run_ingest(_Db(), SETTINGS, _job("ingest"))
    return analyzer


def test_the_free_document_is_read_only_to_the_page_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    analyzer = _ingest(monkeypatch, free=True)
    assert analyzer.calls == [{"max_pages": 3}]


def test_a_paid_document_is_read_whole_through_the_unchanged_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analyzer = _ingest(monkeypatch, free=False)
    assert analyzer.calls == [{}]


# --- Generate: the question cap ---------------------------------------------------------


def _generate(
    monkeypatch: pytest.MonkeyPatch, *, free: bool, per_chunk: int, chunks: int
) -> tuple[list[int], int]:
    saved: list[int] = []
    asked: list[int] = []

    def _generate_for_chunk(chunk, _client, _settings):
        asked.append(chunk)
        return SimpleNamespace(questions=[f"q{chunk}-{n}" for n in range(per_chunk)])

    def _save(_db, questions):
        saved.append(len(questions))
        return len(questions)

    monkeypatch.setattr(pipeline, "_document", lambda *_: _document())
    monkeypatch.setattr(pipeline, "set_status", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(pipeline, "is_free_taste_document", lambda *_: free)
    monkeypatch.setattr(
        pipeline, "load_chunks", lambda *_args, **_kwargs: list(range(chunks))
    )
    monkeypatch.setattr(pipeline, "clear_questions", lambda *_: None)
    monkeypatch.setattr(pipeline, "Anthropic", lambda **_: object())
    monkeypatch.setattr(pipeline, "generate_for_chunk", _generate_for_chunk)
    monkeypatch.setattr(pipeline, "save_questions", _save)
    pipeline.run_generate(_Db(), SETTINGS, _job("generate"))
    return saved, len(asked)


def test_the_free_document_stops_at_the_question_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    saved, asked = _generate(monkeypatch, free=True, per_chunk=3, chunks=10)
    # 3 from the first section, then 1 of the next section's 3 — and no third call to the
    # model, because the cap was already reached.
    assert saved == [3, 1]
    assert asked == 2


def test_a_paid_document_gets_every_question(monkeypatch: pytest.MonkeyPatch) -> None:
    saved, asked = _generate(monkeypatch, free=False, per_chunk=3, chunks=10)
    assert sum(saved) == 30
    assert asked == 10


# --- The migration's shape --------------------------------------------------------------


def _statements() -> str:
    lines = []
    for line in MIGRATION.read_text().splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("--"):
            lines.append(stripped)
    return re.sub(r"\s+", " ", " ".join(lines)).lower()


def test_the_claim_table_is_readable_but_never_writable_by_a_candidate() -> None:
    body = _statements()
    assert "alter table public.promote_free_taste enable row level security" in body
    assert "revoke all on table public.promote_free_taste from public, anon, authenticated" in body
    assert "grant select on table public.promote_free_taste to authenticated" in body
    # A candidate who could delete their own claim could reset their own free tier.
    for verb in ("insert", "update", "delete", "all"):
        assert f"grant {verb} on table public.promote_free_taste" not in body
    assert "for select using (auth.uid() = user_id)" in body


def test_one_claim_per_candidate_that_outlives_the_document() -> None:
    body = _statements()
    assert "user_id uuid primary key references auth.users(id) on delete cascade" in body
    assert "on delete set null deferrable initially deferred" in body


def test_the_claim_is_made_at_upload_and_refused_the_way_the_api_already_reads() -> None:
    body = _statements()
    assert "before insert on public.documents" in body
    assert "on conflict (user_id) do nothing" in body
    # 42501 is what as_subscription_required turns into a 402, so the app shows the
    # paywall exactly as it did before.
    assert "raise exception 'subscription required' using errcode = '42501'" in body


def test_a_mix_session_still_needs_a_plan() -> None:
    body = _statements()
    assert "document_id is not null and document_id = public.free_taste_document(auth.uid())" in (
        body
    )


def test_answering_without_a_plan_is_limited_to_the_free_document() -> None:
    body = _statements()
    assert "if not entitled and q.document_id is distinct from free_document then" in body
