-- ---------------------------------------------------------------------------
-- 0005 — a candidate cannot grant themselves access
-- ---------------------------------------------------------------------------
-- profiles_update_own let a candidate write their own profile row. That row holds
-- subscription_status and access_expires_at, so before this migration the following was
-- a complete bypass of billing, using nothing but the candidate's own token:
--
--   PATCH /rest/v1/profiles?id=eq.<self>
--   {"subscription_status": "active", "access_expires_at": "2099-01-01"}
--
-- Verified against the live project: it returned 'active' until 2099. Row-level security
-- was doing exactly what it says — the row *is* theirs — and it has nothing to say about
-- which columns of their own row a candidate may write.
--
-- stripe_customer_id was writable too, which is worse than it first looks. It is the key
-- that maps a Stripe customer to a candidate. Pointing it at somebody else's customer id
-- makes another person's subscription, and their billing portal, reachable as yours.
--
-- There is no column on profiles a candidate has any business writing: the email comes
-- from auth, and everything else comes from Stripe. So the privilege goes entirely rather
-- than being trimmed to a safe subset. When there is eventually a candidate-editable
-- field — a display name, a target exam date — grant update on that column by name.

revoke update on public.profiles from anon, authenticated;

-- Dropped rather than left in place. With the privilege revoked the policy grants
-- nothing, and a policy that reads "candidates may update their own profile" while being
-- inert is worse than no policy: the next person to read this schema believes it.
drop policy profiles_update_own on public.profiles;

-- ---------------------------------------------------------------------------
-- Entitlement, as one question with one answer
-- ---------------------------------------------------------------------------
-- Two ways to be entitled, per 0001: a subscription that is active, or a one-time
-- purchase that has not run out. Both are expressed on profiles so this is a single
-- check, and it lives here so that the API, the policies below and any future caller all
-- ask the same question and get the same answer.
--
-- past_due does not grant access. A card that failed is retried by Stripe over several
-- days, and it is a business decision whether those days are free; treating them as
-- unpaid is the reversible direction. Widening this later is one line, and nobody is
-- harmed by having been asked to fix their card. Narrowing it later takes access away
-- from people who currently have it.

create function public.has_access(candidate uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
      from public.profiles p
     where p.id = candidate
       and (
         p.subscription_status = 'active'
         or (p.access_expires_at is not null and p.access_expires_at > now())
       )
  );
$$;

revoke all on function public.has_access(uuid) from public;
grant execute on function public.has_access(uuid) to authenticated;

-- ---------------------------------------------------------------------------
-- What access is required for
-- ---------------------------------------------------------------------------
-- Creating work needs a subscription. Reading and deleting never do.
--
-- That distinction is deliberate and it is not a technicality. A candidate whose card
-- expires still owns their documents. Holding those documents hostage — or making the
-- delete button the one thing that stops working when you stop paying — would be a
-- straightforwardly hostile way to run a subscription, and the privacy constraint says
-- their documents are hard-deletable without qualifying it with "while paying".

drop policy documents_all_own on public.documents;

create policy documents_read_own on public.documents
  for select using (auth.uid() = user_id);

create policy documents_delete_own on public.documents
  for delete using (auth.uid() = user_id);

create policy documents_update_own on public.documents
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- The only gated one. Uploading is what spends money downstream: Document Intelligence
-- on ingest, then the Anthropic API on every generatable section.
create policy documents_create_own on public.documents
  for insert with check (auth.uid() = user_id and public.has_access(auth.uid()));

-- Practice sessions likewise: reading past sessions is free, starting a new one is not.
drop policy practice_sessions_all_own on public.practice_sessions;

create policy practice_sessions_read_own on public.practice_sessions
  for select using (auth.uid() = user_id);

create policy practice_sessions_update_own on public.practice_sessions
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy practice_sessions_delete_own on public.practice_sessions
  for delete using (auth.uid() = user_id);

create policy practice_sessions_create_own on public.practice_sessions
  for insert with check (auth.uid() = user_id and public.has_access(auth.uid()));

-- ---------------------------------------------------------------------------
-- Answering, re-stated with the same check
-- ---------------------------------------------------------------------------
-- submit_response is security definer, so no policy applies inside it and gating the
-- practice_sessions table does not gate this. Without the check below, a lapsed candidate
-- holding a session id from when they were paying could keep answering indefinitely by
-- calling the function directly — the one route into the quiz that the policies above do
-- not cover.
--
-- Replaced in full rather than patched, because a function is replaced whole. The only
-- change from 0004 is the has_access check.

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
begin
  if uid is null then
    raise exception 'not authenticated' using errcode = '28000';
  end if;

  if not public.has_access(uid) then
    raise exception 'subscription required' using errcode = '42501';
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
