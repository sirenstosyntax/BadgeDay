"""The job queue, as the worker sees it.

Claiming is a single `for update skip locked` statement inside claim_job (migration
0003), because select-then-update from here would let two workers read the same queued
row before either wrote to it and both would run the ingestion.

Everything else — succeeding, failing, deciding whether to retry — is ordinary SQL and
lives here, where the retry policy is readable.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel
from supabase import Client

logger = logging.getLogger(__name__)

JobKind = Literal["ingest", "generate"]
JobStatus = Literal["queued", "running", "succeeded", "failed"]

# Backoff between attempts, indexed by the attempt that just failed. Ingestion failures
# are rarely transient — a corrupt PDF stays corrupt — so this is short and shallow
# rather than an hours-long exponential climb. Its real purpose is to survive a
# Document Intelligence or Anthropic blip without hammering either.
RETRY_DELAYS = [timedelta(seconds=30), timedelta(minutes=2), timedelta(minutes=10)]

# Anything still 'running' after this has lost its worker: a deploy, an OOM, a crash. No
# process will ever report on it, so it is not really running and must be requeued.
STALE_AFTER = timedelta(minutes=30)


class Job(BaseModel):
    id: str
    kind: JobKind
    document_id: str
    status: JobStatus
    attempts: int
    max_attempts: int
    last_error: str | None = None


def claim(db: Client, worker: str) -> Job | None:
    """Take the oldest ready job, or None when the queue is empty."""
    rows = db.rpc("claim_job", {"worker": worker}).execute().data
    return Job.model_validate(rows[0]) if rows else None


def succeed(db: Client, job: Job) -> None:
    db.table("jobs").update({"status": "succeeded", "last_error": None}).eq("id", job.id).execute()


def fail(db: Client, job: Job, error: str) -> bool:
    """Record a failure. Returns True if the job will be retried.

    `attempts` was already incremented by the claim, so it reads as the number of tries
    spent — including this one.
    """
    detail = error[:2000]
    if job.attempts >= job.max_attempts:
        db.table("jobs").update({"status": "failed", "last_error": detail}).eq(
            "id", job.id
        ).execute()
        return False

    delay = RETRY_DELAYS[min(job.attempts - 1, len(RETRY_DELAYS) - 1)]
    db.table("jobs").update(
        {
            "status": "queued",
            "last_error": detail,
            "run_after": (datetime.now(UTC) + delay).isoformat(),
            "locked_at": None,
            "locked_by": None,
        }
    ).eq("id", job.id).execute()
    return True


def enqueue(db: Client, kind: JobKind, document_id: str) -> None:
    """Queue follow-on work. Ingestion enqueues generation once chunks exist.

    Upload-time enqueueing is not done here — that is a trigger, so that a document
    cannot be created without being queued. See migration 0002.
    """
    db.table("jobs").insert({"kind": kind, "document_id": document_id}).execute()


def requeue_stale(db: Client) -> int:
    """Return jobs abandoned by a dead worker to the queue.

    Without this a worker killed mid-job leaves its row 'running' forever: no process is
    working on it, and no process will ever claim it, so the candidate's document sits at
    'analyzing' permanently. The claim already counted the attempt, so a job that kills
    its worker every time still exhausts max_attempts rather than cycling for ever.
    """
    cutoff = (datetime.now(UTC) - STALE_AFTER).isoformat()
    rows = (
        db.table("jobs")
        .update({"status": "queued", "locked_at": None, "locked_by": None})
        .eq("status", "running")
        .lt("locked_at", cutoff)
        .execute()
        .data
    )
    if rows:
        logger.warning("requeued %d stale job(s) abandoned by a dead worker", len(rows))
    return len(rows)
