"""Apply SQL migrations to the Supabase Postgres database.

Deliberately minimal — enough to apply an ordered set of files and record what has run,
without pulling in a migration framework before the schema has settled.

    python scripts/apply_migrations.py            # apply anything not yet applied
    python scripts/apply_migrations.py --status   # show what has and has not run

Each file runs inside a transaction, so a migration that fails partway leaves nothing
behind. Applied filenames are recorded in schema_migrations.
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
    parser.add_argument("--status", action="store_true", help="report without applying")
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
