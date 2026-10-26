-- ---------------------------------------------------------------------------
-- 0019 — one free Promote document, so a candidate sees the product before paying
-- ---------------------------------------------------------------------------
-- Until now Promote asked for a subscription before a candidate could upload anything
-- (0005). Recruit gives a full oral board away with no card; Promote gave away nothing,
-- so a promotional candidate was asked to pay before seeing a single question built from
-- their own reading list. That is the product's whole pitch, and it was behind the wall.
--
-- The free taste is ONE document per account, ever. The worker caps what that document
-- costs (the first N pages are read, and at most M questions are written — see
-- app/worker/pipeline.py and the PROMOTE_FREE_TASTE_* settings), so the spend per
-- stranger is bounded by configuration rather than by the size of whatever they upload.
--
-- `badgeday_pricing.md` records why there was no Promote free tier: a stranger's upload
-- costs Document Intelligence money. The page cap is the answer to that, not a reversal
-- of it.

-- ---------------------------------------------------------------------------
-- The claim
-- ---------------------------------------------------------------------------
-- One row per candidate who has used their free document. The row outlives the document:
-- deleting the free document does not hand out a second one, otherwise upload, delete,
-- upload would be an unlimited free tier with extra steps. document_id goes null on
-- delete and the claim stays.
--
-- The foreign key is deferred because the claim is written by the BEFORE INSERT trigger
-- below, a moment before the document row it points at exists. Checked at commit, by
-- which time the document is there — or the whole insert has rolled back and the claim
-- with it.
--
-- Known limit, accepted: deleting the whole account cascades this row away, so a
-- candidate who deletes their account and signs up again gets another free document.
-- Keeping a tombstone keyed on their email would contradict the hard-delete promise in
-- the privacy constraint, and the page and question caps keep that path cheap.

create table public.promote_free_taste (
  user_id uuid primary key references auth.users(id) on delete cascade,
  document_id uuid references public.documents(id) on delete set null
    deferrable initially deferred,
  claimed_at timestamptz not null default now()
);

alter table public.promote_free_taste enable row level security;

-- The candidate may see their own claim, so the app can say which document is the free
-- one. Nobody writes it but the trigger: a candidate who could delete their own row could
-- reset their own free tier.
revoke all on table public.promote_free_taste from public, anon, authenticated;
grant select on table public.promote_free_taste to authenticated;

create policy promote_free_taste_select_own on public.promote_free_taste
  for select using (auth.uid() = user_id);

-- The candidate's free document, or null. security definer so the policies below can
-- ask it the same way has_access is asked. VOLATILE rather than STABLE on purpose: the
-- documents insert policy calls this in the same statement whose BEFORE trigger has just
-- written the claim, and a STABLE function reads the statement's starting snapshot,
-- which does not contain that row.
create function public.free_taste_document(candidate uuid)
returns uuid
language sql
volatile
security definer
set search_path = public
as $$
  select f.document_id from public.promote_free_taste f where f.user_id = candidate;
$$;

revoke all on function public.free_taste_document(uuid) from public;
grant execute on function public.free_taste_document(uuid) to authenticated;

-- ---------------------------------------------------------------------------
-- Claiming it
-- ---------------------------------------------------------------------------
-- A candidate with access uploads as before and claims nothing. A candidate without
-- access claims the free taste with this document — or, if they have already claimed it,
-- is refused with the same 42501 the API already turns into a 402, so the app shows the
-- paywall exactly as it did before this migration.
--
-- `on conflict do nothing` plus the FOUND check is what makes two concurrent uploads
-- safe: the primary key lets exactly one of them claim, and the other is refused rather
-- than both slipping through a check-then-insert gap.

create function public.claim_promote_free_taste()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if public.has_access(new.user_id) then
    return new;
  end if;

  insert into public.promote_free_taste (user_id, document_id)
  values (new.user_id, new.id)
  on conflict (user_id) do nothing;

  if not found then
    raise exception 'subscription required' using errcode = '42501';
  end if;

  return new;
end;
$$;

revoke all on function public.claim_promote_free_taste() from public;

create trigger documents_claim_free_taste
  before insert on public.documents
  for each row execute function public.claim_promote_free_taste();

-- ---------------------------------------------------------------------------
-- The policies, widened by exactly the free document
-- ---------------------------------------------------------------------------
-- Same shape as 0005, with one more way through: this row IS the candidate's free
-- document. The trigger above is what decides whether it gets to be.

drop policy documents_create_own on public.documents;

create policy documents_create_own on public.documents
  for insert with check (
    auth.uid() = user_id
    and (
      public.has_access(auth.uid())
      or id = public.free_taste_document(auth.uid())
    )
  );

-- Practice on the free document only. A mix session (null document_id) still needs a
-- plan: someone who tried the free document, then subscribed, then lapsed, must not get
-- their whole reading list back through a mix session.
drop policy practice_sessions_create_own on public.practice_sessions;

create policy practice_sessions_create_own on public.practice_sessions
  for insert with check (
    auth.uid() = user_id
    and (
      public.has_access(auth.uid())
      or (
        document_id is not null
        and document_id = public.free_taste_document(auth.uid())
      )
    )
  );

-- ---------------------------------------------------------------------------
-- Answering, re-stated with the free-document path
-- ---------------------------------------------------------------------------
-- submit_response is security definer, so the policies above do not reach inside it
-- (the reason 0005 re-stated it). Replaced in full, because a function is replaced
-- whole. The only change from 0005 is the access check: without a plan, the session
-- must be on the free document AND the question must come from it.

create or replace function public.submit_response(
  p_session_id uuid,
  p_question_id uuid,
  p_selected_index integer default null,
  p_answered_boolean boolean default null,
  p_answered_text text default null
)
returns table (
  is_correct boolean,
  explanation text,
  correct_index integer,
  correct_answer boolean,
  model_answer text,
  section_path text[],
  section_title text,
  page_start integer,
  page_end integer
)
language plpgsql
security definer
set search_path = public
as $$
declare
  uid uuid := auth.uid();
  q public.questions;
  c public.chunks;
  verdict boolean;
  entitled boolean;
  free_document uuid;
begin
  if uid is null then
    raise exception 'not authenticated' using errcode = '28000';
  end if;

  entitled := public.has_access(uid);
  if not entitled then
    free_document := public.free_taste_document(uid);
    perform 1 from public.practice_sessions s
     where s.id = p_session_id
       and s.user_id = uid
       and free_document is not null
       and s.document_id = free_document;
    if not found then
      raise exception 'subscription required' using errcode = '42501';
    end if;
  end if;

  perform 1 from public.practice_sessions s
   where s.id = p_session_id and s.user_id = uid;
  if not found then
    raise exception 'no such session' using errcode = 'P0002';
  end if;

  select * into q from public.questions where id = p_question_id;
  if not found then
    raise exception 'no such question' using errcode = 'P0002';
  end if;

  perform 1 from public.documents d where d.id = q.document_id and d.user_id = uid;
  if not found then
    raise exception 'no such question' using errcode = 'P0002';
  end if;

  if not entitled and q.document_id is distinct from free_document then
    raise exception 'subscription required' using errcode = '42501';
  end if;

  verdict := case q.type
    when 'multiple_choice' then p_selected_index is not null and p_selected_index = q.correct_index
    when 'true_false' then p_answered_boolean is not null and p_answered_boolean = q.correct_answer
    else null
  end;

  insert into public.responses (
    session_id, question_id, user_id, selected_index, answered_boolean, answered_text, is_correct
  ) values (
    p_session_id, p_question_id, uid, p_selected_index, p_answered_boolean, p_answered_text, verdict
  );

  select * into c from public.chunks where id = q.chunk_id;

  return query select
    verdict, q.explanation, q.correct_index, q.correct_answer, q.model_answer,
    c.section_path, c.section_title, c.page_start, c.page_end;
end;
$$;
