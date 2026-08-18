-- ---------------------------------------------------------------------------
-- 0009 — Recruit attempt history (own rows, not Promote)
-- ---------------------------------------------------------------------------
-- BD-R-001. New store. Does not reuse practice_sessions, responses, documents,
-- chunks, or questions. Reading and deleting own rows do not require entitlement.
-- Inserts are service-role only; the writer is a later change.

create table public.recruit_attempts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  scenario_id text not null,
  question_text text not null,
  started_at timestamptz not null,
  completed_at timestamptz,
  transcript text not null default '',
  status text not null
    check (status in ('completed', 'abandoned', 'critique_failed')),
  audio_retained boolean not null default false,
  version integer not null default 1 check (version >= 1),
  constraint recruit_attempts_completed_shape check (
    (status = 'completed' and completed_at is not null)
    or (status <> 'completed' and completed_at is null)
  )
);

create index recruit_attempts_user_completed_idx
  on public.recruit_attempts (user_id, completed_at desc)
  where status = 'completed';

create table public.recruit_critiques (
  attempt_id uuid primary key
    references public.recruit_attempts(id) on delete cascade,
  version integer not null default 1 check (version >= 1),
  outcome text not null
    check (outcome in ('scored', 'not_assessable', 'not_answered')),
  points jsonb not null default '[]'::jsonb
    check (jsonb_typeof(points) = 'array'),
  internal_score integer
    check (internal_score is null or (internal_score between 0 and 5)),
  route text check (route is null or route in ('4A', '4B', 'n/a')),
  determination text not null default '',
  deciding_clause_id text,
  criterion_id text,
  criterion_name text
);

alter table public.recruit_attempts enable row level security;
alter table public.recruit_critiques enable row level security;

create policy recruit_attempts_read_own on public.recruit_attempts
  for select using (auth.uid() = user_id);
create policy recruit_attempts_delete_own on public.recruit_attempts
  for delete using (auth.uid() = user_id);

create policy recruit_critiques_read_own on public.recruit_critiques
  for select using (
    exists (
      select 1 from public.recruit_attempts a
      where a.id = recruit_critiques.attempt_id
        and a.user_id = auth.uid()
    )
  );

revoke insert, update on public.recruit_attempts from anon, authenticated;
revoke insert, update, delete on public.recruit_critiques from anon, authenticated;

revoke select on public.recruit_attempts from anon, authenticated;
grant select (
  id, user_id, scenario_id, question_text, started_at, completed_at,
  transcript, status, audio_retained, version
) on public.recruit_attempts to authenticated;
grant delete on public.recruit_attempts to authenticated;

revoke select on public.recruit_critiques from anon, authenticated;
grant select (attempt_id, version, points)
  on public.recruit_critiques to authenticated;
