-- ---------------------------------------------------------------------------
-- 0019 — lock SECURITY DEFINER execute, and stop the review view bypassing RLS
-- ---------------------------------------------------------------------------
-- Advisors on the live project, read 2026-10-22 and not applied here:
--
--   * public.answered_questions is a SECURITY DEFINER view (security_invoker
--     = false). 0004 did that on purpose: authenticated cannot read the answer
--     columns of questions, so an invoker view over those columns returns
--     nothing and the review screen breaks. The fix is not to grant those
--     columns back — that would put the key beside the question again. The
--     view becomes invoker and reads a definer function that still filters
--     on auth.uid(). A candidate who has not answered the question still
--     cannot see its answer.
--
--   * anon can execute enqueue_ingest_job, handle_new_user, has_access,
--     has_module_access, and has_recruit_access. The first two are triggers.
--     Postgres checks EXECUTE when the trigger is created, not when it fires,
--     so revoking anon and authenticated does not stop an upload from
--     enqueueing or a signup from creating a profile. The has_* functions
--     stay executable by authenticated because the API and the insert
--     policies call them. anon does not.
--
--   * authenticated can also execute attach_recruit_board_attempt. Nothing
--     in the app calls it. submit_queued_recruit_attempt calls it as the
--     function owner. Revoke the client grant.
--
--   * abandon_recruit_board, start_recruit_board, submit_queued_recruit_attempt,
--     and submit_response stay executable by authenticated. The request path
--     calls them with the candidate's own token. Revoking them would break
--     the app. They remain on the authenticated-definer advisor list on
--     purpose.
--
-- Cross-user writes, checked against the live function bodies (same text as
-- 0014): start_recruit_board and submit_queued_recruit_attempt do not allow
-- them. Both raise 42501 when p_user_id is distinct from auth.uid() before
-- any insert. attach_recruit_board_attempt updates a board only when
-- board.user_id = auth.uid(), and a failed attach rolls the submit back.
-- There is no committed cross-user write through those two RPCs.
--
-- The live check also rejects the service role, because auth.uid() is null
-- on that JWT. The worker does not call these two functions (it calls
-- complete_queued_recruit_attempt and persist_recruit_completed_attempt).
-- reject_unless_self_or_service keeps the client check and lets service_role
-- pass a user id, which is how persist_recruit_completed_attempt has to work.
--
-- has_access(candidate), has_module_access, and has_recruit_access are reads.
-- Before this migration any anon or signed-in caller could pass another
-- user's id and learn whether that person is paid. They now raise 42501
-- unless the id is auth.uid() or the caller is service_role. Policies call
-- has_access(auth.uid()), so a candidate's own insert is unchanged. A null
-- candidate still returns false, so an anonymous insert stays a policy
-- denial rather than an error.
--
-- touch_updated_at and claim_job had no fixed search_path. claim_job is not
-- security definer and is already revoked from anon and authenticated.

-- ---------------------------------------------------------------------------
-- Caller must be the named user, or the service role.
-- ---------------------------------------------------------------------------

create function public.reject_unless_self_or_service(p_user_id uuid)
returns void
language plpgsql
stable
security invoker
set search_path = public
as $$
begin
  if coalesce(auth.role(), '') = 'service_role' then
    return;
  end if;
  if p_user_id is null or p_user_id is distinct from auth.uid() then
    raise exception 'not allowed' using errcode = '42501';
  end if;
end;
$$;

revoke all on function public.reject_unless_self_or_service(uuid) from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- Entitlement reads. Same answers as 0015 / 0012. Stricter about who may ask.
-- ---------------------------------------------------------------------------

create or replace function public.has_access(candidate uuid)
returns boolean
language plpgsql
stable
security definer
set search_path = public
as $$
begin
  if candidate is null then
    return false;
  end if;
  perform public.reject_unless_self_or_service(candidate);
  return (
    exists (
      select 1
        from public.profiles p
       where p.id = candidate
         and (
           p.subscription_status = 'active'
           or (p.access_expires_at is not null and p.access_expires_at > now())
         )
    )
    or exists (
      select 1
        from public.store_purchases sp
       where sp.user_id = candidate
         and sp.module = 'promote'
         and (
           sp.status = 'active'
           or (sp.expires_at is not null and sp.expires_at > now())
         )
    )
  );
end;
$$;

revoke all on function public.has_access(uuid) from public, anon;
grant execute on function public.has_access(uuid) to authenticated, service_role;

create or replace function public.has_module_access(candidate uuid, p_module text)
returns boolean
language plpgsql
stable
security definer
set search_path = public
as $$
begin
  if candidate is null then
    return false;
  end if;
  perform public.reject_unless_self_or_service(candidate);
  return exists (
    select 1
      from public.entitlements e
     where e.user_id = candidate
       and e.module = p_module
       and (
         e.subscription_status = 'active'
         or (e.access_expires_at is not null and e.access_expires_at > now())
       )
  );
end;
$$;

revoke all on function public.has_module_access(uuid, text) from public, anon;
grant execute on function public.has_module_access(uuid, text) to authenticated, service_role;

create or replace function public.has_recruit_access(candidate uuid)
returns boolean
language plpgsql
stable
security definer
set search_path = public
as $$
begin
  if candidate is null then
    return false;
  end if;
  perform public.reject_unless_self_or_service(candidate);
  return public.has_module_access(candidate, 'recruit');
end;
$$;

revoke all on function public.has_recruit_access(uuid) from public, anon;
grant execute on function public.has_recruit_access(uuid) to authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Recruit writes that take a user id.
-- ---------------------------------------------------------------------------

create or replace function public.start_recruit_board(
  p_id uuid,
  p_user_id uuid,
  p_started_at timestamptz,
  p_slots jsonb
) returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  first jsonb;
begin
  if p_id is null or p_user_id is null or p_started_at is null
     or jsonb_typeof(p_slots) is distinct from 'array'
     or jsonb_array_length(p_slots) <> 5 then
    raise exception 'missing or invalid board arguments' using errcode = '22023';
  end if;

  perform public.reject_unless_self_or_service(p_user_id);

  if exists (
    select 1 from public.recruit_boards
     where user_id = p_user_id
       and status in ('in_progress', 'scoring')
  ) then
    raise exception 'an oral board is already in progress' using errcode = '23505';
  end if;

  first := p_slots -> 0;

  insert into public.recruit_boards (
    id, user_id, started_at, status, slots, current_index,
    current_question_text, current_scenario_id, current_criterion_id,
    current_family, issued_families, issued_scenario_ids
  ) values (
    p_id, p_user_id, p_started_at, 'in_progress', p_slots, 0,
    first->>'question_text', first->>'scenario_id', first->>'criterion_id',
    first->>'family',
    array(
      select coalesce(item->>'family', '')
        from jsonb_array_elements(p_slots) as item
    ),
    array(
      select coalesce(item->>'scenario_id', '')
        from jsonb_array_elements(p_slots) as item
    )
  );

  return p_id;
end;
$$;

revoke all on function public.start_recruit_board(uuid, uuid, timestamptz, jsonb)
  from public, anon;
grant execute on function public.start_recruit_board(uuid, uuid, timestamptz, jsonb)
  to authenticated, service_role;

create or replace function public.submit_queued_recruit_attempt(
  p_id uuid,
  p_user_id uuid,
  p_scenario_id text,
  p_question_text text,
  p_started_at timestamptz,
  p_audio_storage_path text,
  p_criterion_id text default 'c2',
  p_board_id uuid default null,
  p_slot_index integer default null
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

  perform public.reject_unless_self_or_service(p_user_id);

  insert into public.recruit_attempts (
    id, user_id, scenario_id, question_text, started_at,
    transcript, status, audio_retained, audio_storage_path, criterion_id,
    board_id, slot_index
  ) values (
    p_id, p_user_id, p_scenario_id, p_question_text, p_started_at,
    '', 'queued', false, p_audio_storage_path, coalesce(p_criterion_id, 'c2'),
    p_board_id, p_slot_index
  );

  insert into public.jobs (kind, attempt_id, board_id)
  values ('recruit_critique', p_id, p_board_id);

  if p_board_id is not null then
    perform public.attach_recruit_board_attempt(p_board_id, p_id, coalesce(p_slot_index, 0));
  end if;

  return p_id;
end;
$$;

revoke all on function public.submit_queued_recruit_attempt(
  uuid, uuid, text, text, timestamptz, text, text, uuid, integer
) from public, anon;
grant execute on function public.submit_queued_recruit_attempt(
  uuid, uuid, text, text, timestamptz, text, text, uuid, integer
) to authenticated, service_role;

-- Service-role only, and it takes p_user_id. The worker calls it with the
-- service-role key. The guard is what stops a later grant to authenticated
-- from writing a completed attempt for somebody else. Authenticated still
-- has no EXECUTE.

create or replace function public.persist_recruit_completed_attempt(
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

  perform public.reject_unless_self_or_service(p_user_id);

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

-- ---------------------------------------------------------------------------
-- Triggers and the internal board attach. Not client RPCs.
-- ---------------------------------------------------------------------------

revoke all on function public.enqueue_ingest_job() from public, anon, authenticated;
revoke all on function public.handle_new_user() from public, anon, authenticated;

revoke all on function public.attach_recruit_board_attempt(uuid, uuid, integer)
  from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- Review. Invoker view, definer function, same columns, same auth.uid() filter.
-- ---------------------------------------------------------------------------

create function public.answered_question_rows()
returns table (
  session_id uuid,
  answered_at timestamptz,
  is_correct boolean,
  selected_index integer,
  answered_boolean boolean,
  answered_text text,
  question_id uuid,
  document_id uuid,
  type text,
  stem text,
  options text[],
  correct_index integer,
  correct_answer boolean,
  model_answer text,
  explanation text,
  section_path text[],
  section_title text,
  page_start integer,
  page_end integer
)
language sql
stable
security definer
set search_path = public
as $$
  select
    r.session_id,
    r.answered_at,
    r.is_correct,
    r.selected_index,
    r.answered_boolean,
    r.answered_text,
    q.id,
    q.document_id,
    q.type,
    q.stem,
    q.options,
    q.correct_index,
    q.correct_answer,
    q.model_answer,
    q.explanation,
    c.section_path,
    c.section_title,
    c.page_start,
    c.page_end
  from public.responses r
  join public.questions q on q.id = r.question_id
  join public.chunks c on c.id = q.chunk_id
  where r.user_id = auth.uid();
$$;

revoke all on function public.answered_question_rows() from public, anon;
grant execute on function public.answered_question_rows() to authenticated;

drop view public.answered_questions;
create view public.answered_questions
with (security_invoker = true)
as
select * from public.answered_question_rows();

revoke all on public.answered_questions from public, anon;
grant select on public.answered_questions to authenticated;

-- ---------------------------------------------------------------------------
-- Fixed search_path. claim_job's body already schema-qualifies public.jobs.
-- ---------------------------------------------------------------------------

alter function public.touch_updated_at() set search_path = public;
alter function public.claim_job(text) set search_path = public;
