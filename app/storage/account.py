"""Deleting a candidate, and everything that is theirs.

The same seam delete_document lives on: Postgres cascades, object storage does not. Every
table in the schema references auth.users (directly, or through documents and sessions that
do) with `on delete cascade`, so removing the one auth row removes every row the candidate
owns — profiles, documents, chunks, questions, sessions, responses, saved questions, jobs.
Object storage has no such reach: the uploaded files must be removed by hand, and their keys
live in the document rows the auth delete is about to destroy.

So the order is forced. Read the file keys, remove the files, then delete the user. Delete
the user first and the keys are gone with the rows — the files become storage nobody can
find, list or delete, which is the deletion promise broken silently. Removing files first
and failing before the user delete leaves a still-listable account: visible, retryable, and
the better failure.
"""

from supabase import Client

from app.storage.documents import BUCKET


def purge_account(db: Client, service: Client, user_id: str) -> None:
    """Hard-delete the candidate: their files, then their auth user (which cascades the rows).

    `db` is the candidate's own client — removing their files runs under their storage
    policy, which scopes to their prefix. `service` is the service-role client, needed only
    for the admin delete of the auth user, which no candidate token can perform.
    """
    paths = [
        row["storage_path"]
        for row in db.table("documents").select("storage_path").execute().data
    ]
    if paths:
        db.storage.from_(BUCKET).remove(paths)

    service.auth.admin.delete_user(user_id)
