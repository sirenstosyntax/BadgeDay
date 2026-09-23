"""The migration ledger is service-side state, not a PostgREST catalog.

public.schema_migrations is created by scripts/apply_migrations.py, so it never
passed through the ENABLE ROW LEVEL SECURITY lines in the numbered migrations.
Supabase grants new public tables to anon and authenticated. The publishable
key in the web and Play clients could read and write every row.

0011_recruit_critique_jobs.sql does not create a table. The audit below fails
if a later edit adds one without ENABLE ROW LEVEL SECURITY.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT / "supabase" / "migrations" / "0016_migration_ledger_is_not_public.sql"
)
RUNNER = ROOT / "scripts" / "apply_migrations.py"


def _statements(sql: str) -> str:
    lines = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        lines.append(stripped)
    return "\n".join(lines).lower()


def test_migration_0016_enables_rls_and_revokes_client_roles() -> None:
    sql = MIGRATION.read_text()
    body = _statements(sql)
    assert "alter table public.schema_migrations enable row level security" in body
    assert "revoke all on table public.schema_migrations from public" in body
    assert "revoke all on table public.schema_migrations from anon" in body
    assert "revoke all on table public.schema_migrations from authenticated" in body
    # Default deny. A policy would be a grant of access, which this table must not have.
    assert "create policy" not in body
    assert "grant " not in body
    # Leave the owner bypass in place so the migration runner can keep writing.
    assert "force row level security" not in body
    # Billing and store product creation stay out of this fix.
    assert "store_purchases" not in body
    assert "entitlements" not in body
    assert "price_id" not in body


def test_runner_locks_the_ledger_before_migrations_run() -> None:
    """A fresh database creates the table before 0016 runs. The runner must not
    leave that window open, and must heal a ledger created by an older script."""
    body = _statements(RUNNER.read_text())
    assert "alter table public.schema_migrations enable row level security" in body
    assert "revoke all on table public.schema_migrations from public" in body
    assert "revoke all on table public.schema_migrations from anon" in body
    assert "revoke all on table public.schema_migrations from authenticated" in body


def test_every_created_public_table_enables_rls() -> None:
    """Every CREATE TABLE in supabase/migrations has ENABLE ROW LEVEL SECURITY
    somewhere in that set. schema_migrations is created in 0016, which also
    enables it. 0011 is not in the created set."""
    created: dict[str, str] = {}
    enabled: set[str] = set()
    for path in sorted((ROOT / "supabase" / "migrations").glob("*.sql")):
        body = _statements(path.read_text())
        for name in re.findall(
            r"create table(?: if not exists)? public\.([a-z_][a-z0-9_]*)", body
        ):
            created.setdefault(name, path.name)
        enabled.update(
            re.findall(
                r"alter table public\.([a-z_][a-z0-9_]*)\s+enable row level security",
                body,
            )
        )
    missing = {name: src for name, src in created.items() if name not in enabled}
    assert missing == {}
    assert created["schema_migrations"] == "0016_migration_ledger_is_not_public.sql"
    assert "0011_recruit_critique_jobs.sql" not in created.values()


def test_0011_alters_tables_that_already_have_rls() -> None:
    """Live 0011 matches this file (checksum). It must not introduce a public
    table, and it must not turn RLS off on the tables it changes."""
    path = ROOT / "supabase" / "migrations" / "0011_recruit_critique_jobs.sql"
    body = _statements(path.read_text())
    assert "create table" not in body
    assert "disable row level security" not in body
    assert "enable row level security" not in body
    altered = set(re.findall(r"alter table public\.([a-z_][a-z0-9_]*)\b", body))
    assert altered == {"recruit_attempts", "jobs"}

    locked_before: set[str] = set()
    for earlier in sorted((ROOT / "supabase" / "migrations").glob("*.sql")):
        if earlier.name >= path.name:
            break
        locked_before.update(
            re.findall(
                r"alter table public\.([a-z_][a-z0-9_]*)\s+enable row level security",
                _statements(earlier.read_text()),
            )
        )
    assert altered <= locked_before
    assert "with (security_invoker = true)" in body


def test_product_code_does_not_read_the_ledger() -> None:
    """Play and web talk to product tables and auth, not the migration ledger."""
    roots = [ROOT / "app", ROOT / "web" / "src"]
    hits: list[str] = []
    for root in roots:
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx", ".js", ".jsx"}:
                continue
            if "schema_migrations" in path.read_text(errors="ignore"):
                hits.append(str(path.relative_to(ROOT)))
    assert hits == []
