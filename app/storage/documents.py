"""A document is a row and a file, and nothing keeps the two in step but this module.

Postgres cascades the row to its chunks, questions and jobs. It has no reach at all into
object storage, so the uploaded file is the one piece of a candidate's document that
survives every database guarantee already verified. Both operations that touch both
things — create and delete — are ordered here deliberately, and the ordering is the
interesting part of the file.

Nothing here filters by `user_id`. The client passed in carries the candidate's token and
the database applies their policies, so `select("*")` already means "theirs". Adding a
filter would not make it safer; it would suggest the safety came from the filter.
"""

import logging
import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel
from supabase import Client

logger = logging.getLogger(__name__)

BUCKET = "documents"

DocumentStatus = Literal["pending", "analyzing", "chunking", "generating", "ready", "failed"]

# What a candidate is allowed to upload, mapped to the extension we store it under.
CONTENT_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


class DocumentRecord(BaseModel):
    """One row of `documents`, as returned to the candidate."""

    id: str
    user_id: str
    filename: str
    storage_path: str
    byte_size: int | None = None
    page_count: int | None = None
    status: DocumentStatus
    error: str | None = None
    created_at: datetime
    updated_at: datetime


def safe_filename(name: str) -> str:
    """Reduce an uploaded name to something safe to use as part of an object key.

    The name lands in the storage path, so it is worth being blunt about what it may
    contain. Note that a `../` in here would *not* escape the candidate's prefix — the
    bucket policy compares the first segment of the literal key to auth.uid(), and a
    traversal sequence is not resolved away before that check. The reason to strip it is
    that unpredictable keys are keys we cannot reliably delete later, and deletion is a
    promise this product makes.
    """
    base = name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    cleaned = _UNSAFE.sub("_", base).lstrip(".")
    return cleaned[:120] or "document"


def create_document(
    db: Client, user_id: str, filename: str, content_type: str, data: bytes
) -> DocumentRecord:
    """Store the file, then record it. In that order, and it matters.

    Inserting the row fires the trigger from migration 0002, which enqueues the ingestion
    job. A worker may therefore claim this document the instant the row lands. If the row
    went in first, that worker could reach a document whose file had not finished
    uploading — or, if the upload then failed, one whose file never arrives at all, which
    surfaces to the candidate as an ingestion failure rather than as the upload failure it
    actually was.

    Uploading first inverts the failure: a stored object with no row is unreachable and
    invisible, and is cleaned up below.
    """
    document_id = str(uuid.uuid4())
    stored_name = safe_filename(filename)
    path = f"{user_id}/{document_id}/{stored_name}"

    db.storage.from_(BUCKET).upload(path, data, {"content-type": content_type, "upsert": "false"})

    try:
        rows = (
            db.table("documents")
            .insert(
                {
                    "id": document_id,
                    "user_id": user_id,
                    "filename": stored_name,
                    "storage_path": path,
                    "byte_size": len(data),
                }
            )
            .execute()
            .data
        )
    except Exception:
        # The row is the only thing that makes this object reachable. Without it the file
        # is storage nobody can find, list or delete — so it goes now, while we still
        # know its key.
        _remove_quietly(db, path)
        raise

    return DocumentRecord.model_validate(rows[0])


def list_documents(db: Client) -> list[DocumentRecord]:
    rows = db.table("documents").select("*").order("created_at", desc=True).execute().data
    return [DocumentRecord.model_validate(row) for row in rows]


def get_document(db: Client, document_id: str) -> DocumentRecord | None:
    """Fetch one document, or None if the candidate has no such document.

    "No such document" and "somebody else's document" are the same answer here, and
    deliberately indistinguishable: RLS returns nothing in both cases, and the caller
    turns both into a 404. Distinguishing them would confirm to a candidate that a given
    document id exists, which is a small leak but a real one.
    """
    rows = db.table("documents").select("*").eq("id", document_id).limit(1).execute().data
    return DocumentRecord.model_validate(rows[0]) if rows else None


def delete_document(db: Client, document_id: str) -> bool:
    """Remove the file, then the row. In that order, and it also matters.

    The row cascades to chunks, questions and jobs, so deleting it is nearly the whole
    job — but it takes the storage_path with it, and Postgres will not touch the object.
    Delete the row first and the object removal fails, and the candidate's file remains
    with nothing left pointing at it: undeletable, unlistable, and still stored. That
    breaks the deletion promise silently, which is the worst way to break it.

    Failing in the other direction leaves a listed document whose file is gone. The
    candidate sees a broken document and can tell us. Visible beats silent.
    """
    record = get_document(db, document_id)
    if record is None:
        return False

    db.storage.from_(BUCKET).remove([record.storage_path])
    db.table("documents").delete().eq("id", document_id).execute()
    return True


def _remove_quietly(db: Client, path: str) -> None:
    """Best-effort cleanup on a path we are already failing out of."""
    try:
        db.storage.from_(BUCKET).remove([path])
    except Exception:
        logger.exception("orphaned upload at %s — object stored with no row", path)
