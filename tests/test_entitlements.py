"""Grant and check per-module entitlements — the ship gate #4 writers.

A wrong table, a wrong module key, or a check that consults Promote's has_access
is exactly the silent failure that matters: Recruit would open for a Lieutenant
candidate, or stay closed for someone who paid for Recruit. A fake client records
the upsert and the RPC so those are assertions rather than things noticed in
production.
"""

from datetime import UTC, datetime
from types import SimpleNamespace

from app.storage.entitlements import (
    ClearModulePass,
    GrantModulePass,
    SetModuleSubscription,
    apply_entitlement,
    has_module_access,
    has_recruit_access,
    module_entitlement,
)

USER = "44444444-4444-4444-4444-444444444444"
OTHER = "55555555-5555-5555-5555-555555555555"


class _Query:
    def __init__(self, table: str, sink: list, rows: list) -> None:
        self.record: dict = {"table": table}
        self._sink = sink
        self._rows = rows

    def upsert(self, values: dict, on_conflict: str | None = None) -> "_Query":
        self.record["upsert"] = values
        self.record["on_conflict"] = on_conflict
        return self

    def update(self, values: dict) -> "_Query":
        self.record["update"] = values
        return self

    def select(self, columns: str) -> "_Query":
        self.record["select"] = columns
        return self

    def eq(self, column: str, value: object) -> "_Query":
        self.record.setdefault("eq", []).append((column, value))
        return self

    def limit(self, n: int) -> "_Query":
        self.record["limit"] = n
        return self

    def execute(self) -> SimpleNamespace:
        self._sink.append(self.record)
        return SimpleNamespace(data=self._rows)


class _Db:
    def __init__(
        self,
        *,
        rows: list | None = None,
        rpc_result: object = False,
    ) -> None:
        self.writes: list[dict] = []
        self.rpc_calls: list[tuple[str, dict]] = []
        self._rows = rows if rows is not None else [{"user_id": USER}]
        self._rpc_result = rpc_result

    def table(self, name: str) -> _Query:
        return _Query(name, self.writes, self._rows)

    def rpc(self, name: str, args: dict) -> "_Db":
        self.rpc_calls.append((name, args))
        return self

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self._rpc_result)


# --- Grant -------------------------------------------------------------------


def test_granting_a_recruit_subscription_upserts_the_recruit_row() -> None:
    db = _Db()
    apply_entitlement(
        db, SetModuleSubscription(user_id=USER, module="recruit", status="active")
    )
    (write,) = db.writes
    assert write["table"] == "entitlements"
    assert write["on_conflict"] == "user_id,module"
    assert write["upsert"] == {
        "user_id": USER,
        "module": "recruit",
        "subscription_status": "active",
    }


def test_granting_a_promote_subscription_does_not_write_recruit() -> None:
    db = _Db()
    apply_entitlement(
        db, SetModuleSubscription(user_id=USER, module="promote", status="active")
    )
    assert db.writes[0]["upsert"]["module"] == "promote"
    assert db.writes[0]["upsert"]["module"] != "recruit"


def test_granting_a_pass_writes_the_expiry_on_that_module() -> None:
    db = _Db()
    expires = datetime(2026, 12, 8, tzinfo=UTC)
    apply_entitlement(
        db, GrantModulePass(user_id=USER, module="recruit", expires_at=expires)
    )
    assert db.writes[0]["upsert"] == {
        "user_id": USER,
        "module": "recruit",
        "access_expires_at": expires.isoformat(),
    }


def test_clearing_a_pass_nulls_expiry_and_does_not_touch_status() -> None:
    db = _Db()
    apply_entitlement(db, ClearModulePass(user_id=USER, module="recruit"))
    (write,) = db.writes
    assert write["update"] == {"access_expires_at": None}
    assert write["eq"] == [("user_id", USER), ("module", "recruit")]
    assert "subscription_status" not in write["update"]


def test_a_grant_matching_no_row_does_not_raise() -> None:
    db = _Db(rows=[])
    apply_entitlement(
        db, SetModuleSubscription(user_id=OTHER, module="recruit", status="active")
    )
    assert db.writes


# --- Check -------------------------------------------------------------------


def test_recruit_check_calls_has_recruit_access_not_has_access() -> None:
    db = _Db(rpc_result=True)
    assert has_recruit_access(db, USER) is True
    assert db.rpc_calls == [("has_recruit_access", {"candidate": USER})]


def test_module_check_is_scoped_to_the_named_module() -> None:
    db = _Db(rpc_result=False)
    assert has_module_access(db, USER, "recruit") is False
    assert db.rpc_calls == [
        ("has_module_access", {"candidate": USER, "p_module": "recruit"})
    ]


def test_a_false_rpc_is_not_entitled() -> None:
    db = _Db(rpc_result=False)
    assert has_recruit_access(db, USER) is False


def test_module_entitlement_uses_the_database_verdict_not_the_row() -> None:
    """past_due on the row is not access — the RPC is the rule, the row is the label."""
    db = _Db(
        rpc_result=False,
        rows=[{"subscription_status": "past_due", "access_expires_at": None}],
    )
    state = module_entitlement(db, USER, "recruit")
    assert state.entitled is False
    assert state.subscription_status == "past_due"
    assert state.module == "recruit"
    assert db.rpc_calls[0][0] == "has_module_access"
    assert db.rpc_calls[0][1]["p_module"] == "recruit"
