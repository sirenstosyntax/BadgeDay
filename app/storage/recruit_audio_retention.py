"""recruit-audio must not keep a recording past transcription.

The bucket is temporary. A file older than a day means a delete was missed.
The worker runs this monthly, and `scripts/recruit_audio_retention_check.py`
is the scheduled check that exits non-zero.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from supabase import Client

from app.storage.recruit import AUDIO_BUCKET

logger = logging.getLogger(__name__)

MAX_AUDIO_AGE = timedelta(days=1)
# Log name an alert counts. Non-zero is a privacy failure.
RECRUIT_AUDIO_OLDER_THAN_ONE_DAY = "recruit_audio_older_than_one_day"
_MAX_PAGES = 50
_MAX_DEPTH = 6


@dataclass(frozen=True)
class StoredAudio:
    name: str
    created_at: datetime


def stale_audio_names(
    objects: Iterable[StoredAudio],
    *,
    now: datetime,
    max_age: timedelta = MAX_AUDIO_AGE,
) -> list[str]:
    """Names whose created_at is strictly older than `max_age`."""
    moment = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    moment = moment.astimezone(UTC)
    cutoff = moment - max_age
    stale: list[str] = []
    for obj in objects:
        created = obj.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        else:
            created = created.astimezone(UTC)
        if created < cutoff:
            stale.append(obj.name)
    return stale


def _join(prefix: str, name: str) -> str:
    if not prefix:
        return name
    return f"{prefix.rstrip('/')}/{name}"


def list_recruit_audio_objects(db: Client) -> list[StoredAudio]:
    """Every file in the bucket. Folders are walked; they are not files."""
    found: list[StoredAudio] = []
    seen: set[str] = set()

    def walk(prefix: str, depth: int) -> None:
        if depth > _MAX_DEPTH or prefix in seen:
            return
        seen.add(prefix)
        cursor: str | None = None
        folders: list[str] = []
        for _ in range(_MAX_PAGES):
            options: dict[str, Any] = {
                "prefix": prefix,
                "limit": 1000,
                "with_delimiter": True,
            }
            if cursor:
                options["cursor"] = cursor
            page = db.storage.from_(AUDIO_BUCKET).list_v2(options)
            for obj in page.objects:
                key = obj.key or _join(prefix, obj.name)
                found.append(StoredAudio(name=key, created_at=obj.created_at))
            # Folders arrive on every page. Walking only after the cursor
            # runs out drops every user folder except the last page.
            for folder in page.folders:
                folder_prefix = folder.key or _join(prefix, folder.name)
                folders.append(folder_prefix.rstrip("/"))
            next_cursor = page.nextCursor if page.hasNext else None
            if next_cursor and next_cursor != cursor:
                cursor = next_cursor
                continue
            break
        else:
            raise RuntimeError("recruit-audio listing did not finish")
        for folder_prefix in folders:
            walk(folder_prefix, depth + 1)

    walk("", 0)
    return found


def enforce_recruit_audio_retention(db: Client, *, now: datetime | None = None) -> list[str]:
    """Return stale names. Log an ERROR metric when the list is not empty."""
    stale = stale_audio_names(list_recruit_audio_objects(db), now=now or datetime.now(UTC))
    if stale:
        # Count only. Paths are user and attempt ids, and this line is what
        # the public GitHub Action log captures.
        logger.error("%s count=%d", RECRUIT_AUDIO_OLDER_THAN_ONE_DAY, len(stale))
    return stale
