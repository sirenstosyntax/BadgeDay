-- ---------------------------------------------------------------------------
-- 0010 — write a completed Recruit attempt after a verified critique
-- ---------------------------------------------------------------------------
-- BD-R-001. Called only after verify_critique has accepted the critique.
-- Service-role only. One transaction, so 0009's deferred completed-requires-critique
-- rule can pass.

create function public.persist_recruit_completed_attempt(
  p_user_id uuid,
  p_scenario_id text,
  p_question_text text,
  p_started_at timestamptz,
  p_transcript text,
  p_outcome text,
  p_points jsonb,
  p_internal_score integer default null,
  p_route text default 'n/a',
  p_determination text default '',
  p_deciding_clause_id text default null,
  p_criterion_id text default null,
  p_criterion_name text default null,
  p_audio_retained boolean default false
) returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  new_id uuid;
  has_quote boolean;
begin
  if p_user_id is null or p_scenario_id is null or p_question_text is null
     or p_started_at is null or p_outcome is null then
    raise exception 'missing required argument' using errcode = '22023';
  end if;

  if p_outcome not in ('scored', 'not_assessable', 'not_answered') then
    raise exception 'invalid outcome' using errcode = '22023';
  end if;

  if jsonb_typeof(p_points) is distinct from 'array' or jsonb_array_length(p_points) < 1 then
    raise exception 'verified critique has no points' using errcode = '22023';
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

  insert into public.recruit_attempts (
    user_id, scenario_id, question_text, started_at, completed_at,
    transcript, status, audio_retained
  ) values (
    p_user_id, p_scenario_id, p_question_text, p_started_at, now(),
    coalesce(p_transcript, ''), 'completed', coalesce(p_audio_retained, false)
  ) returning id into new_id;

  insert into public.recruit_critiques (
    attempt_id, outcome, points, internal_score, route, determination,
    deciding_clause_id, criterion_id, criterion_name
  ) values (
    new_id, p_outcome, p_points, p_internal_score, p_route,
    coalesce(p_determination, ''), p_deciding_clause_id,
    p_criterion_id, p_criterion_name
  );

  return new_id;
end;
$$;

revoke all on function public.persist_recruit_completed_attempt(
  uuid, text, text, timestamptz, text, text, jsonb,
  integer, text, text, text, text, text, boolean
) from public, anon, authenticated;

grant execute on function public.persist_recruit_completed_attempt(
  uuid, text, text, timestamptz, text, text, jsonb,
  integer, text, text, text, text, text, boolean
) to service_role;
