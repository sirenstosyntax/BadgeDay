-- ---------------------------------------------------------------------------
-- 0016 — the migration ledger is not a public table
-- ---------------------------------------------------------------------------
-- scripts/apply_migrations.py creates public.schema_migrations outside the
-- migration files. Supabase's default privileges hand a new public table to
-- anon and authenticated, and PostgREST exposes it. This table never had RLS.
--
-- Verified against the live BadgeDay project with the publishable key that
-- ships in the web and Play clients (no user session): SELECT returned every
-- ledger row, INSERT reached the primary key, and UPDATE and DELETE were
-- permitted. The rows are filenames, checksums, and applied_at — operational
-- metadata, not a catalog and not candidate data. Writing them is still
-- enough to skip or replay a migration on the next runner pass.
--
-- No policy. Enabling RLS with zero policies denies anon and authenticated,
-- the same stance as public.jobs. The runner connects as the table owner
-- over the direct database URL and bypasses RLS. The service role bypasses
-- RLS too; nothing in the API reads this table through PostgREST.
--
-- The revokes are the second lock. A policy added later does not reopen the
-- table to the publishable key unless someone also restores the privilege.
--
-- 0011_recruit_critique_jobs.sql is not this gap. The live ledger checksum
-- matches the file in the repo. That file has no CREATE TABLE and no
-- ENABLE or DISABLE ROW LEVEL SECURITY. It alters recruit_attempts and jobs,
-- replaces the security_invoker view dead_jobs, and adds policies on
-- storage.objects for the private recruit-audio bucket. Those two tables
-- already have RLS from 0009 and 0001. Project tqunuflbtoiqyflnecmu.

create table if not exists public.schema_migrations (
  filename text primary key,
  checksum text not null,
  applied_at timestamptz not null default now()
);

alter table public.schema_migrations enable row level security;

revoke all on table public.schema_migrations from public;
revoke all on table public.schema_migrations from anon;
revoke all on table public.schema_migrations from authenticated;
