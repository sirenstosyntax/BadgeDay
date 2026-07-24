"""purge_account — the file-and-then-user ordering deletion depends on.

Object storage has no cascade, so the files must be removed while their keys still exist in
the document rows. If the auth-user delete ran first, those rows would be gone and the files
orphaned. The fake records the sequence so that ordering is a test, not a comment.
"""

from app.storage.account import purge_account

USER = "44444444-4444-4444-4444-444444444444"


class _Bucket:
    def __init__(self, log: list) -> None:
        self._log = log

    def remove(self, paths: list[str]) -> None:
        self._log.append(("remove", paths))


class _Storage:
    def __init__(self, log: list) -> None:
        self._log = log

    def from_(self, _bucket: str) -> _Bucket:
        return _Bucket(self._log)


class _Query:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def select(self, _cols: str) -> "_Query":
        return self

    def execute(self) -> object:
        rows = self._rows
        return type("R", (), {"data": rows})()


class _CandidateDb:
    def __init__(self, log: list, rows: list) -> None:
        self.storage = _Storage(log)
        self._rows = rows

    def table(self, _name: str) -> _Query:
        return _Query(self._rows)


class _Admin:
    def __init__(self, log: list) -> None:
        self._log = log

    def delete_user(self, user_id: str) -> None:
        self._log.append(("delete_user", user_id))


class _Auth:
    def __init__(self, log: list) -> None:
        self.admin = _Admin(log)


class _ServiceDb:
    def __init__(self, log: list) -> None:
        self.auth = _Auth(log)


def test_files_are_removed_before_the_user_is_deleted() -> None:
    log: list = []
    rows = [{"storage_path": f"{USER}/d1/a.pdf"}, {"storage_path": f"{USER}/d2/b.pdf"}]
    db = _CandidateDb(log, rows=rows)
    service = _ServiceDb(log)

    purge_account(db, service, USER)

    assert log == [
        ("remove", [f"{USER}/d1/a.pdf", f"{USER}/d2/b.pdf"]),
        ("delete_user", USER),
    ]


def test_a_candidate_with_no_documents_is_still_deleted() -> None:
    log: list = []
    db = _CandidateDb(log, rows=[])
    service = _ServiceDb(log)

    purge_account(db, service, USER)

    # No empty remove() call — nothing to remove — but the user delete still runs.
    assert log == [("delete_user", USER)]
