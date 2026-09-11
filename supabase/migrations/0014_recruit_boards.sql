-- ---------------------------------------------------------------------------
-- 0014 — five-question Recruit boards (BD-R-003 / START ORDER 2026-09-11)
-- ---------------------------------------------------------------------------
-- A session is a board of five. Notes stay on held_candidate_lines until the
-- board completes and C1 is written. Authenticated clients never select
-- upcoming slot text or C1 internals. Free/daily units are boards, not
-- single attempts. Paid / Stripe / Play stay HELD — this file does not
-- enable checkout.

create table public.recruit_boards (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  started_at timestamptz not null,
  completed_at timestamptz,
  abandoned_at timestamptz,
  status text not null
    check (status in ('in_progress', 'scoring', 'completed', 'abandoned')),
  slots jsonb not null
    check (jsonb_typeof(slots) = 'array' and jsonb_array_length(slots) = 5),
  current_index integer not null default 0
    check (current_index >= 0 and current_index <= 4),
  current_question_text text not null,
  current_scenario_id text not null,
  current_criterion_id text not null,
  current_family text not null,
  issued_families text[] not null,
  issued_scenario_ids text[] not null,
  current_attempt_id uuid,
  notes_released boolean not null default false,
  c1_outcome text
    check (c1_outcome is null or c1_outcome in ('scored', 'not_assessable', 'not_answered')),
  c1_internal_score integer
    check (c1_internal_score is null or (c1_internal_score between 0 and 5)),
  c1_route text,
  c1_determination text,
  c1_deciding_clause_id text,
  c1_points jsonb,
  c1_candidate_lines jsonb not null default '[]'::jsonb
    check (jsonb_typeof(c1_candidate_lines) = 'array'),
  constraint recruit_boards_completed_shape check (
    (status = 'completed' and completed_at is not null and notes_released
     and jsonb_array_length(c1_candidate_lines) >= 1)
    or (status <> 'completed')
  ),
  constraint recruit_boards_abandoned_shape check (
    (status = 'abandoned' and abandoned_at is not null and not notes_released)
    or (status <> 'abandoned')
  )
);

create index recruit_boards_user_started_idx
  on public.recruit_boards (user_id, started_at desc);

create unique index recruit_boards_one_open_idx
  on public.recruit_boards (user_id)
  where status in ('in_progress', 'scoring');

alter table public.recruit_attempts
  add column board_id uuid references public.recruit_boards(id) on delete cascade;

alter table public.recruit_attempts
  add column slot_index integer check (slot_index is null or (slot_index between 0 and 4));

alter table public.recruit_attempts
  add column held_candidate_lines jsonb not null default '[]'::jsonb
  check (jsonb_typeof(held_candidate_lines) = 'array');

-- ---------------------------------------------------------------------------
-- jobs: whole-board C1 after the fifth attempt
-- ---------------------------------------------------------------------------

alter table public.jobs drop constraint jobs_kind_check;

alter table public.jobs
  add constraint jobs_kind_check
  check (kind in ('ingest', 'generate', 'recruit_critique', 'recruit_c1'));

alter table public.jobs
  add column board_id uuid references public.recruit_boards(id) on delete cascade;

create index jobs_board_idx on public.jobs (board_id);

alter table public.jobs drop constraint jobs_subject_matches_kind;

alter table public.jobs
  add constraint jobs_subject_matches_kind check (
    (
      kind in ('ingest', 'generate')
      and document_id is not null
      and attempt_id is null
      and board_id is null
    )
    or (
      kind = 'recruit_critique'
      and attempt_id is not null
      and document_id is null
    )
    or (
      kind = 'recruit_c1'
      and board_id is not null
      and document_id is null
      and attempt_id is null
    )
  );

drop view public.dead_jobs;

create view public.dead_jobs
  with (security_invoker = true)
  as
select
  j.id,
  j.kind,
  j.document_id,
  j.attempt_id,
  j.board_id,
  coalesce(d.user_id, a.user_id, b.user_id) as user_id,
  d.filename,
  j.attempts,
  j.max_attempts,
  j.last_error,
  j.updated_at as died_at
from public.jobs j
left join public.documents d on d.id = j.document_id
left join public.recruit_attempts a on a.id = j.attempt_id
left join public.recruit_boards b on b.id = j.board_id
where j.status = 'failed';

-- ---------------------------------------------------------------------------
-- RLS. Upcoming slot text and C1 internals stay ungranted.
-- ---------------------------------------------------------------------------

alter table public.recruit_boards enable row level security;

create policy recruit_boards_read_own on public.recruit_boards
  for select using (auth.uid() = user_id);
create policy recruit_boards_delete_own on public.recruit_boards
  for delete using (auth.uid() = user_id);

revoke insert, update on public.recruit_boards from anon, authenticated;
revoke select on public.recruit_boards from anon, authenticated;
grant select (
  id, user_id, started_at, completed_at, abandoned_at, status,
  current_index, current_question_text, current_scenario_id,
  current_criterion_id, current_family, issued_families, issued_scenario_ids,
  current_attempt_id,
  notes_released, c1_candidate_lines
) on public.recruit_boards to authenticated;
grant delete on public.recruit_boards to authenticated;

grant select (
  id, user_id, scenario_id, question_text, started_at, completed_at,
  transcript, status, audio_retained, version, error, candidate_lines,
  audio_storage_path, criterion_id, board_id, slot_index
) on public.recruit_attempts to authenticated;

-- ---------------------------------------------------------------------------
-- Start a board. Authenticated only. Slots are stored; only Q1 is granted.
-- ---------------------------------------------------------------------------

create function public.start_recruit_board(
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

  if p_user_id is distinct from auth.uid() then
    raise exception 'not allowed' using errcode = '42501';
  end if;

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

revoke all on function public.start_recruit_board(
  uuid, uuid, timestamptz, jsonb
) from public, anon;

grant execute on function public.start_recruit_board(
  uuid, uuid, timestamptz, jsonb
) to authenticated;

-- ---------------------------------------------------------------------------
-- Attach a queued attempt to the current slot and advance the visible question.
-- ---------------------------------------------------------------------------

create function public.attach_recruit_board_attempt(
  p_board_id uuid,
  p_attempt_id uuid,
  p_slot_index integer
) returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  board public.recruit_boards%rowtype;
  next_slot jsonb;
begin
  if p_board_id is null or p_attempt_id is null or p_slot_index is null then
    raise exception 'missing required argument' using errcode = '22023';
  end if;

  select * into board
    from public.recruit_boards
   where id = p_board_id
   for update;

  if not found or board.user_id is distinct from auth.uid() then
    raise exception 'not allowed' using errcode = '42501';
  end if;

  if board.status is distinct from 'in_progress' or board.current_index is distinct from p_slot_index then
    raise exception 'board is not waiting for this slot' using errcode = '22023';
  end if;

  update public.recruit_attempts
     set board_id = p_board_id,
         slot_index = p_slot_index
   where id = p_attempt_id
     and user_id = board.user_id;

  if not found then
    raise exception 'attempt % is not attachable' , p_attempt_id using errcode = '22023';
  end if;

  board.slots := jsonb_set(
    board.slots,
    array[p_slot_index::text],
    (board.slots -> p_slot_index) || jsonb_build_object('attempt_id', p_attempt_id::text)
  );

  if p_slot_index >= 4 then
    update public.recruit_boards
       set slots = board.slots,
           current_attempt_id = p_attempt_id,
           status = 'scoring'
     where id = p_board_id;
  else
    next_slot := board.slots -> (p_slot_index + 1);
    update public.recruit_boards
       set slots = board.slots,
           current_index = p_slot_index + 1,
           current_attempt_id = p_attempt_id,
           current_question_text = next_slot->>'question_text',
           current_scenario_id = next_slot->>'scenario_id',
           current_criterion_id = next_slot->>'criterion_id',
           current_family = next_slot->>'family'
     where id = p_board_id;
  end if;

  return p_board_id;
end;
$$;

revoke all on function public.attach_recruit_board_attempt(
  uuid, uuid, integer
) from public, anon;

grant execute on function public.attach_recruit_board_attempt(
  uuid, uuid, integer
) to authenticated;

-- ---------------------------------------------------------------------------
-- Abandon. Issued prompts stay on the slots row (seen). No C1. No notes.
-- ---------------------------------------------------------------------------

create function public.abandon_recruit_board(p_board_id uuid) returns uuid
language plpgsql
security definer
set search_path = public
as $$
begin
  if p_board_id is null then
    raise exception 'missing required argument' using errcode = '22023';
  end if;

  update public.recruit_boards
     set status = 'abandoned',
         abandoned_at = now(),
         notes_released = false,
         c1_candidate_lines = '[]'::jsonb,
         c1_outcome = null,
         c1_internal_score = null,
         c1_route = null,
         c1_determination = null,
         c1_deciding_clause_id = null,
         c1_points = null
   where id = p_board_id
     and user_id = auth.uid()
     and status in ('in_progress', 'scoring');

  if not found then
    raise exception 'board % cannot be abandoned', p_board_id using errcode = '22023';
  end if;

  return p_board_id;
end;
$$;

revoke all on function public.abandon_recruit_board(uuid) from public, anon;
grant execute on function public.abandon_recruit_board(uuid) to authenticated;

-- ---------------------------------------------------------------------------
-- Submit: accept board_id + slot. Still one transaction with the job.
-- ---------------------------------------------------------------------------

drop function public.submit_queued_recruit_attempt(
  uuid, uuid, text, text, timestamptz, text, text
);

create function public.submit_queued_recruit_attempt(
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

  if p_user_id is distinct from auth.uid() then
    raise exception 'not allowed' using errcode = '42501';
  end if;

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
) to authenticated;

-- ---------------------------------------------------------------------------
-- Complete a queued attempt. Board rows hold lines until release.
-- ---------------------------------------------------------------------------

drop function public.complete_queued_recruit_attempt(
  uuid, text, text, jsonb, jsonb, integer, text, text, text, text, text
);

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
  v_board_id uuid;
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

  select board_id into v_board_id
    from public.recruit_attempts
   where id = p_attempt_id;

  update public.recruit_attempts
     set status = 'completed',
         completed_at = now(),
         transcript = coalesce(p_transcript, ''),
         candidate_lines = case when v_board_id is null then p_candidate_lines else '[]'::jsonb end,
         held_candidate_lines = p_candidate_lines,
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

-- ---------------------------------------------------------------------------
-- Release per-answer notes + C1. Service-role only. No fake C1 on abandon.
-- ---------------------------------------------------------------------------

create function public.complete_recruit_board(
  p_board_id uuid,
  p_c1_outcome text,
  p_c1_points jsonb,
  p_c1_candidate_lines jsonb,
  p_c1_internal_score integer default null,
  p_c1_route text default 'n/a',
  p_c1_determination text default '',
  p_c1_deciding_clause_id text default null
) returns uuid
language plpgsql
security definer
set search_path = public
as $$
begin
  if p_board_id is null or p_c1_outcome is null then
    raise exception 'missing required argument' using errcode = '22023';
  end if;

  if p_c1_outcome not in ('scored', 'not_assessable', 'not_answered') then
    raise exception 'invalid outcome' using errcode = '22023';
  end if;

  if jsonb_typeof(p_c1_candidate_lines) is distinct from 'array'
     or jsonb_array_length(p_c1_candidate_lines) < 1 then
    raise exception 'C1 candidate lines are required' using errcode = '22023';
  end if;

  update public.recruit_attempts
     set candidate_lines = held_candidate_lines
   where board_id = p_board_id
     and status in ('completed', 'critique_failed');

  update public.recruit_boards
     set status = 'completed',
         completed_at = now(),
         notes_released = true,
         c1_outcome = p_c1_outcome,
         c1_internal_score = p_c1_internal_score,
         c1_route = p_c1_route,
         c1_determination = coalesce(p_c1_determination, ''),
         c1_deciding_clause_id = p_c1_deciding_clause_id,
         c1_points = coalesce(p_c1_points, '[]'::jsonb),
         c1_candidate_lines = p_c1_candidate_lines
   where id = p_board_id
     and status in ('in_progress', 'scoring');

  if not found then
    raise exception 'board % is not awaiting C1', p_board_id using errcode = '22023';
  end if;

  return p_board_id;
end;
$$;

revoke all on function public.complete_recruit_board(
  uuid, text, jsonb, jsonb, integer, text, text, text
) from public, anon, authenticated;

grant execute on function public.complete_recruit_board(
  uuid, text, jsonb, jsonb, integer, text, text, text
) to service_role;
