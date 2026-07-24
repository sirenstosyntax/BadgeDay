"""apply_change — the only writer of entitlement columns on profiles.

A wrong column or a wrong filter here is exactly the silent failure that matters: writing
access to the wrong row, or matching by the wrong key so a real payment updates nobody. A
fake client records the query each change builds, so those are assertions rather than
things noticed in production.
"""

from datetime import UTC, datetime
from types import SimpleNamespace

from app.billing.plan import GrantPass, LinkCustomer, SetSubscription
from app.storage.billing import apply_change

CUSTOMER = "cus_test123"
USER = "44444444-4444-4444-4444-444444444444"


class _Query:
    def __init__(self, table: str, sink: list, rows: list) -> None:
        self.record = {"table": table, "eq": []}
        self._sink = sink
        self._rows = rows

    def update(self, values: dict) -> "_Query":
        self.record["update"] = values
        return self

    def eq(self, column: str, value: object) -> "_Query":
        self.record["eq"].append((column, value))
        return self

    def execute(self) -> SimpleNamespace:
        self._sink.append(self.record)
        return SimpleNamespace(data=self._rows)


class _Db:
    def __init__(self, rows: list | None = None) -> None:
        self.writes: list[dict] = []
        self._rows = [{"id": USER}] if rows is None else rows

    def table(self, name: str) -> _Query:
        return _Query(name, self.writes, self._rows)


def test_linking_writes_the_customer_id_keyed_by_user() -> None:
    db = _Db()
    apply_change(db, LinkCustomer(user_id=USER, customer_id=CUSTOMER))
    (write,) = db.writes
    assert write["table"] == "profiles"
    assert write["update"] == {"stripe_customer_id": CUSTOMER}
    assert write["eq"] == [("id", USER)]


def test_subscription_status_is_keyed_by_customer_not_user() -> None:
    """Subscription events know only the customer id — matching by user id would write no row."""
    db = _Db()
    apply_change(db, SetSubscription(customer_id=CUSTOMER, status="active"))
    (write,) = db.writes
    assert write["update"] == {"subscription_status": "active"}
    assert write["eq"] == [("stripe_customer_id", CUSTOMER)]


def test_granting_a_pass_writes_the_expiry_keyed_by_customer() -> None:
    db = _Db()
    expires = datetime(2026, 4, 1, tzinfo=UTC)
    apply_change(db, GrantPass(customer_id=CUSTOMER, expires_at=expires))
    (write,) = db.writes
    assert write["update"] == {"access_expires_at": expires.isoformat()}
    assert write["eq"] == [("stripe_customer_id", CUSTOMER)]


def test_a_change_matching_no_row_does_not_raise() -> None:
    """An event for a customer we don't know must be logged, not thrown — the webhook has
    to answer 200 or Stripe retries it forever."""
    db = _Db(rows=[])
    apply_change(db, SetSubscription(customer_id="cus_unknown", status="active"))
    assert db.writes  # the update was attempted; it simply matched nothing
