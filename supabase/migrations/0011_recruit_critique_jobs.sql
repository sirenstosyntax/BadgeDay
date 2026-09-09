-- ---------------------------------------------------------------------------
-- 0011 — Recruit critiques run on the existing jobs queue
-- ---------------------------------------------------------------------------
-- Ship gate #3. POST /recruit/attempts must not hold Deepgram + Anthropic inside
-- the HTTP request: Azure ingress dies well before the 600s critique timeout, and
-- a min-replicas-1 Container App that is blocked on one critique stalls Promote
-- too. The queue already exists; this migration lets it carry a Recruit attempt
-- the same way it carries a document.
--
-- Entitlements(user, module) is ship gate #4. This file only adds the stub
-- `has_recruit_access`, which returns false — Promote's `has_access` is a
-- different product and must not grant Recruit. Free first session(s) and the
-- daily cap live in application config, not here.

-- Queued / running rows so the client can poll before a critique exists.
-- completed_shape is unchanged: completed still requires completed_at, and the
-- deferred trigger from 0009 still requires a matching recruit_critiques row.

alter table public.recruit_attempts
  drop constraint recruit_attempts_status_check;

alter table public.recruit_attempts
  add constraint recruit_attempts_status_check
  check (status in ('queued', 'running', 'completed', 'abandoned', 'critique_failed'));

alter table public.recruit_attempts
  add column audio_storage_path text;

alter table public.recruit_attempts
  add column error text;

-- Rendered candidate-facing lines, written only after verify. Stored so GET
-- can return them without selecting internal critique columns (score, route,
-- clause ids) that 0009 deliberately withheld.
alter table public.recruit_attempts
  add column candidate_lines jsonb not null default '[]'::jsonb
  check (jsonb_typeof(candidate_lines) = 'array');

create index recruit_attempts_user_started_idx
  on public.recruit_attempts (user_id, started_at desc);

-- ---------------------------------------------------------------------------
-- jobs: a third kind, pointing at an attempt instead of a document
-- ---------------------------------------------------------------------------

alter table public.jobs drop constraint jobs_kind_check;

alter table public.jobs
  add constraint jobs_kind_check
  check (kind in ('ingest', 'generate', 'recruit_critique'));

alter table public.jobs alter column document_id drop not null;

alter table public.jobs
  add column attempt_id uuid references public.recruit_attempts(id) on delete cascade;

alter table public.jobs
  add constraint jobs_subject_matches_kind check (
    (
      kind in ('ingest', 'generate')
      and document_id is not null
      and attempt_id is null
    )
    or (
      kind = 'recruit_critique'
      and attempt_id is not null
      and document_id is null
    )
  );

create index jobs_attempt_idx on public.jobs (attempt_id);

-- dead_jobs joined documents inner, so a failed Recruit job would vanish from
-- the standing list. Left-join both subjects; user_id comes from whichever
-- side the kind points at.

drop view public.dead_jobs;

create view public.dead_jobs
  with (security_invoker = true)
  as
select
  j.id,
  j.kind,
  j.document_id,
  j.attempt_id,
  coalesce(d.user_id, a.user_id) as user_id,
  d.filename,
  j.attempts,
  j.max_attempts,
  j.last_error,
  j.updated_at as died_at
from public.jobs j
left join public.documents d on d.id = j.document_id
left join public.recruit_attempts a on a.id = j.attempt_id
where j.status = 'failed';

comment on view public.dead_jobs is
  'Jobs that exhausted their retries. A row here is a candidate whose document '
  'or Recruit attempt never finished and who has not been told. Poll it; alert '
  'on a non-zero count.';

-- ---------------------------------------------------------------------------
-- Temporary audio: transcribed and discarded. No select for the candidate —
-- voice is not theirs to download unless they later opt in to retention.
-- ---------------------------------------------------------------------------

insert into storage.buckets (id, name, public)
values ('recruit-audio', 'recruit-audio', false)
on conflict (id) do nothing;

create policy recruit_audio_insert_own on storage.objects
  for insert with check (
    bucket_id = 'recruit-audio'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

create policy recruit_audio_delete_own on storage.objects
  for delete using (
    bucket_id = 'recruit-audio'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

-- ---------------------------------------------------------------------------
-- Paid-path stub. #4 replaces the body with entitlements(user, 'recruit').
-- ---------------------------------------------------------------------------

create function public.has_recruit_access(candidate uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  -- Always false until the entitlements table lands. Do not call has_access:
  -- that is Promote, a separate plan.
  select false;
$$;

revoke all on function public.has_recruit_access(uuid) from public;
grant execute on function public.has_recruit_access(uuid) to authenticated;

-- ---------------------------------------------------------------------------
-- Submit: one transaction inserts the queued attempt and the job.
-- Authenticated only; auth.uid() is the owner. No table INSERT grant — a
-- candidate reaching PostgREST directly cannot create a row without a job,
-- and cannot create a completed row that would skip the critique.
-- ---------------------------------------------------------------------------

create function public.submit_queued_recruit_attempt(
  p_id uuid,
  p_user_id uuid,
  p_scenario_id text,
  p_question_text text,
  p_started_at timestamptz,
  p_audio_storage_path text
) returns uuid
language plpgsql
security definer
set search_path = public
as $$
begin
  if p_id is null or p_user_id is null or p_scenario_id is null
     or p_question_text is null or p_started_at is null
     or p_audio_storage_path is null then
    raise exception 'missing required argument' using errcode = '22023';
  end if;

  if p_user_id is distinct from auth.uid() then
    raise exception 'not allowed' using errcode = '42501';
  end if;

  insert into public.recruit_attempts (
    id, user_id, scenario_id, question_text, started_at,
    transcript, status, audio_retained, audio_storage_path
  ) values (
    p_id, p_user_id, p_scenario_id, p_question_text, p_started_at,
    '', 'queued', false, p_audio_storage_path
  );

  insert into public.jobs (kind, attempt_id)
  values ('recruit_critique', p_id);

  return p_id;
end;
$$;

revoke all on function public.submit_queued_recruit_attempt(
  uuid, uuid, text, text, timestamptz, text
) from public, anon;

grant execute on function public.submit_queued_recruit_attempt(
  uuid, uuid, text, text, timestamptz, text
) to authenticated;

-- ---------------------------------------------------------------------------
-- Complete a queued/running attempt after verify. Service-role only.
-- 0009's deferred completed-requires-critique rule still applies.
-- ---------------------------------------------------------------------------

create function public.complete_queued_recruit_attempt(
  p_attempt_id uuid,
  p_transcript text,
  p_outcome text,
  p_points jsonb,
  p_candidate_lines jsonb,
  p_internal_score integer default null,
  p_route text default 'n/a',
  p_determination text default '',
  p_deciding_clause_id text default null,
  p_criterion_id text default null,
  p_criterion_name text default null
) returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  has_quote boolean;
begin
  if p_attempt_id is null or p_outcome is null then
    raise exception 'missing required argument' using errcode = '22023';
  end if;

  if p_outcome not in ('scored', 'not_assessable', 'not_answered') then
    raise exception 'invalid outcome' using errcode = '22023';
  end if;

  if jsonb_typeof(p_points) is distinct from 'array' or jsonb_array_length(p_points) < 1 then
    raise exception 'verified critique has no points' using errcode = '22023';
  end if;

  if jsonb_typeof(p_candidate_lines) is distinct from 'array' then
    raise exception 'candidate_lines must be an array' using errcode = '22023';
  end if;

  select exists (
    select 1
      from jsonb_array_elements(p_points) as point
     where coalesce(point->>'answer_quote', '') <> ''
  ) into has_quote;

  if p_outcome = 'not_assessable' and not has_quote then
    raise exception 'not_assessable requires a quote that establishes absence'
      using errcode = '22023';
  end if;

  update public.recruit_attempts
     set status = 'completed',
         completed_at = now(),
         transcript = coalesce(p_transcript, ''),
         candidate_lines = p_candidate_lines,
         error = null,
         audio_storage_path = null
   where id = p_attempt_id
     and status in ('queued', 'running');

  if not found then
    raise exception 'attempt % is not awaiting a critique', p_attempt_id
      using errcode = '22023';
  end if;

  insert into public.recruit_critiques (
    attempt_id, outcome, points, internal_score, route, determination,
    deciding_clause_id, criterion_id, criterion_name
  ) values (
    p_attempt_id, p_outcome, p_points, p_internal_score, p_route,
    coalesce(p_determination, ''), p_deciding_clause_id,
    p_criterion_id, p_criterion_name
  );

  return p_attempt_id;
end;
$$;

revoke all on function public.complete_queued_recruit_attempt(
  uuid, text, text, jsonb, jsonb, integer, text, text, text, text, text
) from public, anon, authenticated;

grant execute on function public.complete_queued_recruit_attempt(
  uuid, text, text, jsonb, jsonb, integer, text, text, text, text, text
) to service_role;

-- Polling reads status, rendered lines, and a failure message. Internal
-- critique columns stay withheld. audio_storage_path is readable so account
-- deletion can remove leftover objects (storage has no cascade). The bucket
-- itself has no select policy, so the path is not a download.

grant select (
  id, user_id, scenario_id, question_text, started_at, completed_at,
  transcript, status, audio_retained, version, error, candidate_lines,
  audio_storage_path
) on public.recruit_attempts to authenticated;
