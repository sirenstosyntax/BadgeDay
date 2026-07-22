"""Apply SQL migrations to the Supabase Postgres database.

Deliberately minimal — enough to apply an ordered set of files and record what has run,
without pulling in a migration framework before the schema has settled.

    python scripts/apply_migrations.py            # apply anything not yet applied
    python scripts/apply_migrations.py --status   # show what has and has not run
    python scripts/apply_migrations.py --mark-applied 0001_initial_schema.sql

Each file runs inside a transaction, so a migration that fails partway leaves nothing
behind. Applied filenames are recorded in schema_migrations.

`--mark-applied` records a migration as run without running it. It exists for schema
applied out of band — pasted into the Supabase SQL editor before this script had
credentials, which is how the first project was stood up. The alternative is worse: the
DDL is not idempotent (`create table public.profiles`, not `create table if not exists`),
so a blind re-run aborts on the first statement and the ledger stays empty forever.
Recording the truth once lets every later migration flow through the script normally.
"""

import argparse
import hashlib
import sys
from pathlib import Path

from app.config import get_settings

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "supabase" / "migrations"

LEDGER = """
create table if not exists public.schema_migrations (
  filename text primary key,
  checksum text not null,
  applied_at timestamptz not null default now()
);
"""


def _connect(db_url: str):
    try:
        import psycopg
    except ImportError:
        sys.exit("psycopg is not installed. Run: pip install 'psycopg[binary]'")
    return psycopg.connect(db_url)


def _checksum(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply Supabase migrations.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--status", action="store_true", help="report without applying")
    mode.add_argument(
        "--mark-applied",
        nargs="+",
        metavar="FILENAME",
        default=[],
        help="record migrations as applied without running them (schema applied by hand)",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.supabase_db_url:
        sys.exit(
            "SUPABASE_DB_URL is not set. Supabase dashboard -> Project Settings -> "
            "Database -> Connection string (URI), with your database password "
            "substituted for [YOUR-PASSWORD]."
        )

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        sys.exit(f"No migrations found in {MIGRATIONS_DIR}")

    with _connect(settings.supabase_db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(LEDGER)
            conn.commit()
            cur.execute("select filename, checksum from public.schema_migrations")
            applied = dict(cur.fetchall())

        if args.mark_applied:
            # Named explicitly rather than "mark everything pending" — a typo should fail
            # loudly, not quietly record a migration that never ran.
            by_name = {path.name: path for path in files}
            unknown = [name for name in args.mark_applied if name not in by_name]
            if unknown:
                sys.exit(
                    f"Not a migration in {MIGRATIONS_DIR}: {', '.join(unknown)}\n"
                    f"Available: {', '.join(by_name)}"
                )

            for name in args.mark_applied:
                if name in applied:
                    print(f"  {'already recorded':<22} {name}")
                    continue
                with conn.cursor() as cur:
                    cur.execute(
                        "insert into public.schema_migrations (filename, checksum) values (%s, %s)",
                        (name, _checksum(by_name[name].read_text())),
                    )
                conn.commit()
                print(f"  {'marked applied':<22} {name}")
            return 0

        for path in files:
            sql = path.read_text()
            digest = _checksum(sql)

            if path.name in applied:
                drifted = applied[path.name] != digest
                mark = "CHANGED SINCE APPLIED" if drifted else "applied"
                print(f"  {mark:<22} {path.name}")
                if drifted and not args.status:
                    print(
                        "    Refusing to re-run an already-applied migration. Add a new "
                        "file instead of editing this one."
                    )
                continue

            if args.status:
                print(f"  {'pending':<22} {path.name}")
                continue

            print(f"  applying               {path.name} ... ", end="", flush=True)
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute(
                    "insert into public.schema_migrations (filename, checksum) values (%s, %s)",
                    (path.name, digest),
                )
            conn.commit()
            print("ok")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
