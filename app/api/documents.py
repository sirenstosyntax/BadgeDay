"""The document lifecycle: upload, list, read, delete.

Every handler here takes `DbDep` and never mentions the candidate's id in a query. The
database decides what they can see. `user.id` appears exactly once, in the upload path,
because the storage key has to start with it for the bucket policy to authorise the
write — and even there the policy, not this code, is what enforces it.
"""

from fastapi import APIRouter, HTTPException, UploadFile, status

from app.api.deps import CurrentUserDep, DbDep, SettingsDep
from app.storage.documents import (
    CONTENT_TYPES,
    DocumentRecord,
    create_document,
    delete_document,
    get_document,
    list_documents,
)

router = APIRouter(prefix="/documents", tags=["documents"])

_NOT_FOUND = "No such document."


@router.post("", status_code=status.HTTP_201_CREATED)
def upload_document(
    user: CurrentUserDep,
    db: DbDep,
    settings: SettingsDep,
    file: UploadFile,
) -> DocumentRecord:
    """Accept one document and queue it for ingestion.

    The response is the row, not the questions: ingestion is minutes of work and runs as
    a job. The candidate polls `status` on this record, which moves through analyzing,
    chunking and generating before reaching ready.
    """
    if file.content_type not in CONTENT_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Upload a PDF or a Word document — that is what a reading list comes as.",
        )

    # Read one byte past the ceiling: enough to know the limit was exceeded, without
    # pulling an arbitrarily large upload into memory to find out.
    data = file.file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        megabytes = settings.max_upload_bytes // (1024 * 1024)
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"That document is larger than {megabytes} MB. Split it and upload the parts.",
        )
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That file is empty.")

    return create_document(db, user.id, file.filename or "document", file.content_type, data)


@router.get("")
def list_all(db: DbDep) -> list[DocumentRecord]:
    return list_documents(db)


@router.get("/{document_id}")
def read_one(db: DbDep, document_id: str) -> DocumentRecord:
    record = get_document(db, document_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)
    return record


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_one(db: DbDep, document_id: str) -> None:
    """Delete a document, its file, and everything generated from it.

    404 rather than 403 when the document belongs to somebody else: the candidate's
    policies make the two cases identical here, and telling them apart would confirm that
    a given id exists.
    """
    if not delete_document(db, document_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)
