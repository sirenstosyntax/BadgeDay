-- ---------------------------------------------------------------------------
-- 0019 — failed Recruit audio deletes are a row, not only a log line
-- ---------------------------------------------------------------------------
-- delete_audio used to log and return. The file stayed in the private
-- recruit-audio bucket, and nothing could list the misses. This table is
-- that list: one row per storage path we meant to discard and could not,
-- or that the worker sweep found still present after 24 hours with no
-- queued or running attempt pointing at it.
--
-- Service role writes it (the worker). No policy. Enabling RLS with zero
-- policies denies anon and authenticated, the same stance as
-- public.schema_migrations. A path is `{user_id}/{attempt_id}/{filename}` —
-- operational, and still not a catalog for the publishable key.
--
-- Apply this on the live database before deploying the API that writes it.
-- A delete that fails before the table exists still logs
-- recruit_audio_delete_failed; the insert then logs
-- recruit_audio_orphan_record_failed until this file has been applied.
--
-- Retry: remove the object with the service role (delete_audio does that
-- and deletes the row when the remove succeeds). This migration does not
-- delete anything by itself.

create table public.recruit_audio_orphans (
  storage_path text primary key,
  reason text not null check (reason in ('delete_failed', 'stale_unattached')),
  error text not null check (char_length(error) between 1 and 2000),
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now()
);

comment on table public.recruit_audio_orphans is
  'Recruit audio objects we failed to discard, or found still in the private '
  'bucket after 24h with no queued or running attempt. Poll it; alert on a '
  'non-zero count. Delete the storage object, then the row.';

alter table public.recruit_audio_orphans enable row level security;

revoke all on table public.recruit_audio_orphans from public;
revoke all on table public.recruit_audio_orphans from anon;
revoke all on table public.recruit_audio_orphans from authenticated;
