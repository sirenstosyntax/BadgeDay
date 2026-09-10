-- ---------------------------------------------------------------------------
-- 0013 — persist criterion_id on recruit_attempts
-- ---------------------------------------------------------------------------
-- Bank items are FAMILY.n (MOT-1.3). The worker must load the rubric by
-- criterion, not by scenario_id. Existing rows are the live C2 prompt; they
-- stay c2. This column is the attempt-side copy — recruit_critiques already
-- stores the scored criterion after verify.

alter table public.recruit_attempts
  add column criterion_id text;

update public.recruit_attempts
   set criterion_id = 'c2'
 where criterion_id is null;

alter table public.recruit_attempts
  alter column criterion_id set default 'c2';

alter table public.recruit_attempts
  alter column criterion_id set not null;

-- ---------------------------------------------------------------------------
-- Submit: accept criterion_id. Default c2 so a caller that has not yet
-- picked it up still writes a loadable rubric id.
-- ---------------------------------------------------------------------------

drop function public.submit_queued_recruit_attempt(
  uuid, uuid, text, text, timestamptz, text
);

create function public.submit_queued_recruit_attempt(
  p_id uuid,
  p_user_id uuid,
  p_scenario_id text,
  p_question_text text,
  p_started_at timestamptz,
  p_audio_storage_path text,
  p_criterion_id text default 'c2'
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
    transcript, status, audio_retained, audio_storage_path, criterion_id
  ) values (
    p_id, p_user_id, p_scenario_id, p_question_text, p_started_at,
    '', 'queued', false, p_audio_storage_path, coalesce(p_criterion_id, 'c2')
  );

  insert into public.jobs (kind, attempt_id)
  values ('recruit_critique', p_id);

  return p_id;
end;
$$;

revoke all on function public.submit_queued_recruit_attempt(
  uuid, uuid, text, text, timestamptz, text, text
) from public, anon;

grant execute on function public.submit_queued_recruit_attempt(
  uuid, uuid, text, text, timestamptz, text, text
) to authenticated;

-- Polling still withholds internal critique columns. criterion_id is the
-- bank's scoring target, not a score, and the worker / account-delete path
-- need to read it with the owner's token.

grant select (
  id, user_id, scenario_id, question_text, started_at, completed_at,
  transcript, status, audio_retained, version, error, candidate_lines,
  audio_storage_path, criterion_id
) on public.recruit_attempts to authenticated;
