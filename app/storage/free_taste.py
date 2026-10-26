"""Promote's free document: which one it is, and whether it has been used.

The claim is written by the database, never from here — migration 0019's trigger decides
at upload time whether a candidate without a plan may have this document free. This
module only reads that decision back, for two readers with two different clients:

* the API, on the candidate's own token, where row-level security already limits the
  table to their own row;
* the worker, on the service client, which needs to know whether the document it is
  about to spend money on is a free one, so it can cap pages and questions.
"""

from pydantic import BaseModel
from supabase import Client

TABLE = "promote_free_taste"


class FreeTaste(BaseModel):
    """`open` is true until the candidate has claimed their free document.

    A claim outlives its document — `document_id` is null once that document is deleted —
    so `open` false with no document is a real state, not a missing one.
    """

    open: bool
    document_id: str | None = None


def free_taste_for(db: Client, user_id: str) -> FreeTaste:
    rows = (
        db.table(TABLE).select("document_id").eq("user_id", user_id).limit(1).execute().data
    )
    if not rows:
        return FreeTaste(open=True)
    return FreeTaste(open=False, document_id=rows[0]["document_id"])


def is_free_taste_document(db: Client, document_id: str) -> bool:
    rows = (
        db.table(TABLE).select("user_id").eq("document_id", document_id).limit(1).execute().data
    )
    return bool(rows)
