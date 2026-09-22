"""The migration ledger is service-side state, not a PostgREST catalog.

public.schema_migrations is created by scripts/apply_migrations.py, so it never
passed through the ENABLE ROW LEVEL SECURITY lines in the numbered migrations.
Supabase grants new public tables to anon and authenticated. The publishable
key in the web and Play clients could read and write every row.
"""

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
