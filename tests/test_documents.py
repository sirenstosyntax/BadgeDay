"""Document lifecycle, against a fake Supabase client.

The fake exists to pin down *ordering*. Both halves of a document — the row and the
stored file — are written and deleted through the same recorded log, so a test can assert
that the upload precedes the insert and that the object removal precedes the row delete.
Those two orderings are the entire argument of app/storage/documents.py, and neither is
visible in a test that only checks the end state: every one of these cases ends with the
right rows and the right objects regardless of the order they were touched in. What the
order buys is the behaviour when the second step fails.
"""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import CurrentUser, current_user, user_db
from app.api.documents import router
from app.config import Settings
from app.storage.documents import (
    create_document,
    delete_document,
    get_document,
    list_documents,
    safe_filename,
)

USER_ID = "11111111-1111-1111-1111-111111111111"
PDF = "application/pdf"


class _Result:
    def __init__(self, data: list) -> None:
        self.data = data


class FakeBucket:
    def __init__(self, log: list) -> None:
        self.log = log
        self.fail_upload = False

    def upload(self, path: str, data: bytes, options: dict) -> None:
        if self.fail_upload:
            raise RuntimeError("storage refused the upload")
        self.log.append(("upload", path))

    def remove(self, paths: list[str]) -> list:
        self.log.append(("remove", paths[0]))
        return []


class FakeStorage:
    def __init__(self, log: list) -> None:
        self.bucket = FakeBucket(log)

    def from_(self, name: str) -> FakeBucket:
        assert name == "documents"
        return self.bucket


class FakeTable:
    def __init__(self, rows: list[dict], log: list) -> None:
        self.rows = rows
        self.log = log
        self.fail_insert = False
        self._op: tuple = ()
        self._eq: list[tuple[str, str]] = []
        self._pending: dict = {}

    def insert(self, row: dict) -> "FakeTable":
        self._op = ("insert",)
        self._pending = row
        return self

    def select(self, *_: str) -> "FakeTable":
        self._op = ("select",)
        return self

    def delete(self) -> "FakeTable":
        self._op = ("delete",)
        return self

    def eq(self, column: str, value: str) -> "FakeTable":
        self._eq.append((column, value))
        return self

    def limit(self, _: int) -> "FakeTable":
        return self

    def order(self, _: str, desc: bool = False) -> "FakeTable":
        return self

    def _matching(self) -> list[dict]:
        return [r for r in self.rows if all(r.get(c) == v for c, v in self._eq)]

    def execute(self) -> _Result:
        op, self._op, eq, self._eq = self._op[0], (), self._eq, []
        if op == "insert":
            if self.fail_insert:
                raise RuntimeError("row rejected")
            now = datetime.now(UTC).isoformat()
            row = {"status": "pending", "created_at": now, "updated_at": now, **self._pending}
            self.rows.append(row)
            self.log.append(("insert", row["id"]))
            return _Result([row])
        if op == "delete":
            self._eq = eq
            doomed = self._matching()
            self._eq = []
            for row in doomed:
                self.rows.remove(row)
            self.log.append(("delete", eq[0][1] if eq else None))
            return _Result(doomed)
        self._eq = eq
        found = self._matching()
        self._eq = []
        return _Result(found)


class FakeClient:
    def __init__(self) -> None:
        self.log: list = []
        self.rows: list[dict] = []
        self.storage = FakeStorage(self.log)
        self._table = FakeTable(self.rows, self.log)

    def table(self, name: str) -> FakeTable:
        assert name == "documents"
        return self._table


@pytest.fixture
def db() -> FakeClient:
    return FakeClient()


# --- Filenames ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("SOG 304.pdf", "SOG_304.pdf"),
        ("../../../etc/passwd", "passwd"),
        ("C:\\Users\\me\\list.docx", "list.docx"),
        (".hidden", "hidden"),
        ("", "document"),
        ("   ", "document"),
        ("////", "document"),
        ("Ünïcødé.pdf", "_n_c_d_.pdf"),
    ],
)
def test_filenames_are_reduced_to_safe_keys(given: str, expected: str) -> None:
    assert safe_filename(given) == expected


def test_a_very_long_filename_is_truncated() -> None:
    assert len(safe_filename("a" * 500 + ".pdf")) == 120


# --- Create ------------------------------------------------------------------


def test_the_file_is_stored_before_the_row_exists(db: FakeClient) -> None:
    """The insert fires the trigger that queues ingestion, so the file must already be
    there — a worker can claim the document the moment the row lands."""
    create_document(db, USER_ID, "sog.pdf", PDF, b"%PDF-1.4 ...")
    assert [entry[0] for entry in db.log] == ["upload", "insert"]


def test_the_object_key_starts_with_the_owner(db: FakeClient) -> None:
    """The bucket policy authorises on the first path segment. If this drifts, uploads
    start failing closed — or worse, stop being scoped at all."""
    record = create_document(db, USER_ID, "sog.pdf", PDF, b"data")
    assert record.storage_path.startswith(f"{USER_ID}/")
    assert record.storage_path.endswith("/sog.pdf")


def test_byte_size_is_recorded_from_the_payload(db: FakeClient) -> None:
    record = create_document(db, USER_ID, "sog.pdf", PDF, b"12345")
    assert record.byte_size == 5


def test_a_failed_insert_takes_the_orphaned_file_with_it(db: FakeClient) -> None:
    """Without this the object is stored, unreachable and undeletable: no row means no
    storage_path, and no storage_path means nothing can ever find it again."""
    db._table.fail_insert = True

    with pytest.raises(RuntimeError):
        create_document(db, USER_ID, "sog.pdf", PDF, b"data")

    assert [entry[0] for entry in db.log] == ["upload", "remove"]
    assert db.rows == []


def test_a_failed_upload_writes_no_row(db: FakeClient) -> None:
    db.storage.bucket.fail_upload = True

    with pytest.raises(RuntimeError):
        create_document(db, USER_ID, "sog.pdf", PDF, b"data")

    assert db.rows == []
    assert db.log == []


# --- Read --------------------------------------------------------------------


def test_a_document_that_is_not_yours_reads_as_absent(db: FakeClient) -> None:
    """RLS returns nothing for another candidate's row, so this is the same code path as
    a genuinely missing id — which is the point."""
    assert get_document(db, "99999999-9999-9999-9999-999999999999") is None


def test_listing_returns_what_the_policies_allow(db: FakeClient) -> None:
    create_document(db, USER_ID, "one.pdf", PDF, b"a")
    create_document(db, USER_ID, "two.pdf", PDF, b"b")
    assert len(list_documents(db)) == 2


# --- Delete ------------------------------------------------------------------


def test_the_file_is_removed_before_the_row(db: FakeClient) -> None:
    """Row first would mean a failed object removal leaves the candidate's file stored
    with nothing pointing at it — the deletion promise broken where nobody can see."""
    record = create_document(db, USER_ID, "sog.pdf", PDF, b"data")
    db.log.clear()

    assert delete_document(db, record.id) is True
    assert [entry[0] for entry in db.log] == ["remove", "delete"]


def test_deleting_something_absent_reports_it(db: FakeClient) -> None:
    assert delete_document(db, "99999999-9999-9999-9999-999999999999") is False


# --- Endpoints ---------------------------------------------------------------


def _client(db: FakeClient) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[current_user] = lambda: CurrentUser(
        id=USER_ID, email="c@example.com", access_token="t"
    )
    app.dependency_overrides[user_db] = lambda: db
    from app.config import get_settings

    app.dependency_overrides[get_settings] = lambda: Settings(max_upload_bytes=1024)
    return TestClient(app)


def test_a_spreadsheet_is_refused(db: FakeClient) -> None:
    response = _client(db).post("/documents", files={"file": ("list.csv", b"a,b,c", "text/csv")})
    assert response.status_code == 415
    assert db.log == []


def test_an_oversized_document_is_refused_without_being_stored(db: FakeClient) -> None:
    response = _client(db).post("/documents", files={"file": ("big.pdf", b"x" * 2048, PDF)})
    assert response.status_code == 413
    assert db.log == []


def test_an_empty_file_is_refused(db: FakeClient) -> None:
    response = _client(db).post("/documents", files={"file": ("empty.pdf", b"", PDF)})
    assert response.status_code == 400
    assert db.log == []


def test_a_good_upload_returns_the_pending_record(db: FakeClient) -> None:
    response = _client(db).post("/documents", files={"file": ("sog.pdf", b"%PDF-1.4", PDF)})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["filename"] == "sog.pdf"


def test_reading_an_unknown_document_is_404(db: FakeClient) -> None:
    response = _client(db).get("/documents/99999999-9999-9999-9999-999999999999")
    assert response.status_code == 404


def test_deleting_an_unknown_document_is_404(db: FakeClient) -> None:
    response = _client(db).delete("/documents/99999999-9999-9999-9999-999999999999")
    assert response.status_code == 404
