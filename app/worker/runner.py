"""The worker loop.

    badgeday-worker            # run until stopped
    badgeday-worker --once     # drain the queue and exit, for tests and one-off repairs

All failure handling is here rather than in the handlers, so there is exactly one place
that decides what happens when a job dies. The rule: a job that can be retried goes back
to the queue and the document keeps its in-progress status, because it genuinely is still
in progress. Only when the retries are spent does the document go to 'failed' — a
candidate should not watch their upload flip to failed and then back to analyzing while
we quietly try again.
"""

import argparse
import logging
import os
import socket
import sys
import time

from supabase import Client

from app.config import Settings, get_settings
from app.storage.client import service_client
from app.storage.documents import set_status
from app.storage.recruit import delete_audio, get_attempt, mark_failed
from app.worker.jobs import Job, claim, fail, requeue_stale, succeed
from app.worker.pipeline import HANDLERS, AttemptGone, DocumentGone, EmptyRecruitAudio

logger = logging.getLogger(__name__)

IDLE_SLEEP_SECONDS = 5
STALE_SWEEP_EVERY = 60


def run_one(db: Client, settings: Settings, worker: str) -> bool:
    """Claim and run a single job. False when the queue had nothing ready."""
    job = claim(db, worker)
    if job is None:
        return False

    logger.info(
        "claimed %s job %s for document %s attempt %s",
        job.kind,
        job.id,
        job.document_id,
        job.attempt_id,
    )
    try:
        HANDLERS[job.kind](db, settings, job)
    except DocumentGone:
        # The candidate deleted the document while this sat in the queue. Nothing to do
        # and nothing wrong: the cascade has already removed the row this job points at.
        logger.info("document %s no longer exists; job discarded", job.document_id)
        succeed(db, job)
        return True
    except AttemptGone:
        logger.info("attempt %s no longer exists; job discarded", job.attempt_id)
        succeed(db, job)
        return True
    except EmptyRecruitAudio as exc:
        # Nothing to retry: an empty recording stays empty. Mark the attempt so
        # the polling client stops waiting, then succeed the job.
        attempt = get_attempt(db, exc.attempt_id)
        path = attempt.audio_storage_path if attempt else None
        mark_failed(db, exc.attempt_id, exc.detail)
        delete_audio(db, path)
        succeed(db, job)
        return True
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        logger.exception("%s job %s failed", job.kind, job.id)
        if not fail(db, job, detail):
            _give_up(db, job, detail)
        return True

    succeed(db, job)
    return True


def _give_up(db: Client, job: Job, detail: str) -> None:
    """Retries are spent. Tell the candidate, in terms that are theirs to act on."""
    logger.error("%s job %s exhausted %d attempts", job.kind, job.id, job.max_attempts)
    if job.kind == "recruit_critique" and job.attempt_id:
        attempt = get_attempt(db, job.attempt_id)
        path = attempt.audio_storage_path if attempt else None
        mark_failed(
            db,
            job.attempt_id,
            "The critique could not be finished. Try a new question.",
        )
        delete_audio(db, path)
        return
    if job.document_id:
        set_status(
            db,
            job.document_id,
            "failed",
            error=f"We could not process this document ({detail}). Try uploading it again.",
        )


def run_forever(db: Client, settings: Settings, worker: str) -> None:
    last_sweep = 0.0
    while True:
        now = time.monotonic()
        if now - last_sweep > STALE_SWEEP_EVERY:
            requeue_stale(db)
            last_sweep = now

        if not run_one(db, settings, worker):
            time.sleep(IDLE_SLEEP_SECONDS)


def main() -> int:
    parser = argparse.ArgumentParser(prog="badgeday-worker", description="Run ingestion jobs.")
    parser.add_argument("--once", action="store_true", help="drain the queue, then exit")
    parser.add_argument("--name", default=None, help="worker name recorded on claimed jobs")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    settings = get_settings()
    if not (settings.supabase_url and settings.supabase_service_role_key):
        print("Supabase is not configured; set SUPABASE_URL and the keys.", file=sys.stderr)
        return 1

    worker = args.name or f"{socket.gethostname()}:{os.getpid()}"
    db = service_client(settings)

    if args.once:
        requeue_stale(db)
        drained = 0
        while run_one(db, settings, worker):
            drained += 1
        print(f"{drained} job(s) run.")
        return 0

    logger.info("worker %s started", worker)
    try:
        run_forever(db, settings, worker)
    except KeyboardInterrupt:
        logger.info("worker %s stopped", worker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
