-- BadgeDay Command — initial schema.
--
-- Design notes that are not obvious from the DDL:
--
-- PRIVACY IS ENFORCED BY THE DATABASE, NOT BY APPLICATION CODE.
-- Every table holding user content has row-level security enabled, and every policy
-- resolves back to auth.uid(). A bug in a query cannot leak another candidate's
-- documents, because the database will not return them. This is the whole reason
-- Supabase was chosen over rolling auth ourselves.
--
-- HARD DELETE IS A CASCADE, NOT A JOB.
-- The brief requires deleting a document and deleting an account to remove user content.
-- Every foreign key from auth.users downward is ON DELETE CASCADE, so removing a user
-- removes their documents, chunks, questions, sessions, and responses in one statement.
-- Storage objects are the one exception and must be deleted by the application; there is
-- no foreign key from storage.objects into these tables.
--
-- NO ORGANIZATION, TEAM, OR DEPARTMENT TABLES. EVER.
-- Company policy: exam prep is sold to individuals; exam creation is sold to no one.
-- There is deliberately no tenant column, no membership table, and no way to share a
-- document. Adding one is a product decision, not a schema convenience.
--
-- STATUS COLUMNS USE TEXT + CHECK, NOT ENUM TYPES.
-- Postgres enums cannot have values removed and are awkward to reorder. A check
-- constraint is altered with a single statement.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- updated_at maintenance
-- ---------------------------------------------------------------------------

create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- profiles — one row per authenticated user
-- ---------------------------------------------------------------------------
-- Billing state lives here rather than on auth.users, which Supabase owns.
-- access_expires_at covers the 90-day intensive: a one-time purchase grants access
-- until a date, whereas a subscription grants it while status is active. Both are
-- expressed here so entitlement is a single check.

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  stripe_customer_id text unique,
  subscription_status text not null default 'none'
    check (subscription_status in ('none', 'active', 'past_due', 'canceled')),
  access_expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create trigger profiles_touch_updated_at
  before update on public.profiles
  for each row execute function public.touch_updated_at();

-- Create the profile automatically on signup so no code path can forget to.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email)
  values (new.id, new.email)
  on conflict (id) do nothing;
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- documents — one uploaded file
-- ---------------------------------------------------------------------------
-- status drives the ingestion pipeline. The terminal states are 'ready' and 'failed';
-- everything else means a job is outstanding.

create table public.documents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  filename text not null,
  storage_path text not null,
  byte_size bigint,
  page_count integer check (page_count is null or page_count > 0),
  status text not null default 'pending'
    check (status in ('pending', 'analyzing', 'chunking', 'generating', 'ready', 'failed')),
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index documents_user_id_idx on public.documents (user_id, created_at desc);

create trigger documents_touch_updated_at
  before update on public.documents
  for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------------------
-- chunks — citable units of source text
-- ---------------------------------------------------------------------------
-- id is supplied by the application, not generated here: chunk IDs are uuid5 over
-- (document_id, ordinal) so that re-ingesting a document yields the same IDs and does
-- not orphan the citations already pointing at them.
--
-- section_path is an array because a citation is a path through an outline, not a single
-- number. A decimal guideline yields {'304.2.1'}; a lettered one yields
-- {'PROCEDURE','C','4','d'}. An empty array means the chunk has no outline position.
--
-- is_generatable records whether the chunk carries anything worth asking about. A
-- container heading ("304.3 Responsibilities", whose substance is entirely in its
-- children) and a document title block are both perfectly citable and completely
-- worthless as questions. Storing the decision here keeps coverage arithmetic honest:
-- a section that can never be exercised must not sit in the denominator, or coverage
-- can never reach 100% and the tracker reads as broken to a candidate who has in fact
-- covered everything.

create table public.chunks (
  id uuid primary key,
  document_id uuid not null references public.documents(id) on delete cascade,
  ordinal integer not null check (ordinal >= 0),
  kind text not null check (kind in ('outline', 'semantic')),
  section_path text[] not null default '{}',
  section_title text,
  page_start integer not null check (page_start >= 1),
  page_end integer not null check (page_end >= page_start),
  body text not null,
  is_generatable boolean not null default true,
  created_at timestamptz not null default now(),
  unique (document_id, ordinal)
);

create index chunks_document_id_idx on public.chunks (document_id, ordinal);
create index chunks_generatable_idx on public.chunks (document_id) where is_generatable;

-- ---------------------------------------------------------------------------
-- questions
-- ---------------------------------------------------------------------------
-- The citation is the chunk_id foreign key. It is deliberately not denormalized into
-- section/page columns here: duplicating them would let a question's displayed citation
-- drift from the chunk it actually points at, and an unfalsifiable citation is the one
-- guarantee this product cannot afford to weaken.
--
-- The check constraints mirror the application's verification gate. A multiple-choice
-- row without options, or a true/false row carrying a model answer, cannot be written at
-- all. The gate and these constraints are two independent statements of the same rule;
-- either alone would eventually drift.
--
-- source_quote is absent by design. The model supplies one to prove grounding, it is
-- checked, and it is discarded — storing verbatim source text is what the copyright
-- constraint forbids. There is no column for it here and there must not be one.

create table public.questions (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
  chunk_id uuid not null references public.chunks(id) on delete cascade,
  type text not null check (type in ('multiple_choice', 'true_false', 'short_answer')),
  stem text not null,
  explanation text not null,
  options text[],
  correct_index integer,
  correct_answer boolean,
  model_answer text,
  created_at timestamptz not null default now(),

  constraint questions_multiple_choice_shape check (
    type <> 'multiple_choice' or (
      options is not null
      and array_length(options, 1) between 3 and 5
      and correct_index is not null
      and correct_index >= 0
      and correct_index < array_length(options, 1)
      and correct_answer is null
      and model_answer is null
    )
  ),
  constraint questions_true_false_shape check (
    type <> 'true_false' or (
      correct_answer is not null
      and options is null
      and correct_index is null
      and model_answer is null
    )
  ),
  constraint questions_short_answer_shape check (
    type <> 'short_answer' or (
      model_answer is not null
      and options is null
      and correct_index is null
      and correct_answer is null
    )
  )
);

create index questions_document_id_idx on public.questions (document_id);
create index questions_chunk_id_idx on public.questions (chunk_id);

-- ---------------------------------------------------------------------------
-- practice sessions and responses
-- ---------------------------------------------------------------------------
-- document_id is nullable: a null means a full-list mix drawn across every document the
-- candidate has uploaded, which is the mode the brief calls for alongside per-document
-- practice.

create table public.practice_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  document_id uuid references public.documents(id) on delete cascade,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create index practice_sessions_user_idx
  on public.practice_sessions (user_id, created_at desc);

create table public.responses (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.practice_sessions(id) on delete cascade,
  question_id uuid not null references public.questions(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  selected_index integer,
  answered_boolean boolean,
  answered_text text,
  is_correct boolean,
  answered_at timestamptz not null default now(),
  unique (session_id, question_id)
);

-- Coverage is computed from which chunks a candidate has been questioned on, so this
-- index carries the join that answers it.
create index responses_user_question_idx on public.responses (user_id, question_id);

-- Saving is independent of answering: a candidate flags a question to revisit whether
-- or not they got it right, and it must survive the session ending.
create table public.saved_questions (
  user_id uuid not null references auth.users(id) on delete cascade,
  question_id uuid not null references public.questions(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (user_id, question_id)
);

-- ---------------------------------------------------------------------------
-- jobs — the ingestion and generation queue
-- ---------------------------------------------------------------------------
-- Ingestion and generation are minutes-to-hours of work, so they run as jobs rather than
-- inside a request. A Postgres table with FOR UPDATE SKIP LOCKED handles this without a
-- broker to operate, and keeps job state in the same database as everything else.
--
-- Workers claim with:
--   select * from public.jobs
--    where status = 'queued' and run_after <= now()
--    order by created_at
--    for update skip locked
--    limit 1;
--
-- No user ever reads this table. RLS is enabled with no policies at all, which denies
-- every client role; only the service role, which bypasses RLS, can touch it.

create table public.jobs (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('ingest', 'generate')),
  document_id uuid not null references public.documents(id) on delete cascade,
  status text not null default 'queued'
    check (status in ('queued', 'running', 'succeeded', 'failed')),
  attempts integer not null default 0,
  max_attempts integer not null default 3,
  last_error text,
  run_after timestamptz not null default now(),
  locked_at timestamptz,
  locked_by text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index jobs_claim_idx
  on public.jobs (status, run_after, created_at)
  where status = 'queued';

create index jobs_document_idx on public.jobs (document_id);

create trigger jobs_touch_updated_at
  before update on public.jobs
  for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------------------
-- coverage
-- ---------------------------------------------------------------------------
-- "% of each document's sections exercised". The denominator counts only chunks worth
-- questioning, so a document made entirely of container headings does not report 0%
-- forever.
--
-- security_invoker makes the view run under the querying user's permissions, so the RLS
-- policies below apply to it. Without that flag a view silently becomes a hole through
-- which any user reads every row.

create view public.document_coverage
with (security_invoker = true)
as
select
  d.id as document_id,
  d.user_id,
  count(distinct c.id) filter (where c.is_generatable) as sections_total,
  count(distinct r.chunk_id) as sections_exercised
from public.documents d
left join public.chunks c
  on c.document_id = d.id
left join (
  select distinct q.chunk_id, resp.user_id
  from public.responses resp
  join public.questions q on q.id = resp.question_id
) r
  on r.chunk_id = c.id and r.user_id = d.user_id
group by d.id, d.user_id;

-- ---------------------------------------------------------------------------
-- Row-level security
-- ---------------------------------------------------------------------------
-- Enabling RLS without a policy denies all access to client roles. The service role
-- bypasses RLS entirely and is what the background workers use; it must never be shipped
-- to a browser.

alter table public.profiles          enable row level security;
alter table public.documents         enable row level security;
alter table public.chunks            enable row level security;
alter table public.questions         enable row level security;
alter table public.practice_sessions enable row level security;
alter table public.responses         enable row level security;
alter table public.saved_questions   enable row level security;
alter table public.jobs              enable row level security;

create policy profiles_select_own on public.profiles
  for select using (auth.uid() = id);
create policy profiles_update_own on public.profiles
  for update using (auth.uid() = id) with check (auth.uid() = id);

create policy documents_all_own on public.documents
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Chunks and questions have no user_id of their own. Reaching the owner requires a join
-- through documents, which is why these policies are subqueries rather than comparisons.
create policy chunks_select_own on public.chunks
  for select using (
    exists (
      select 1 from public.documents d
      where d.id = chunks.document_id and d.user_id = auth.uid()
    )
  );

create policy questions_select_own on public.questions
  for select using (
    exists (
      select 1 from public.documents d
      where d.id = questions.document_id and d.user_id = auth.uid()
    )
  );

create policy practice_sessions_all_own on public.practice_sessions
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy responses_all_own on public.responses
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy saved_questions_all_own on public.saved_questions
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- No policy on public.jobs. Client roles get nothing; workers use the service role.

-- Chunks and questions are written only by the ingestion worker under the service role,
-- so there are deliberately no insert, update, or delete policies for client roles. A
-- candidate can read their generated questions and can delete the document that owns
-- them, which cascades — but cannot author or edit a question.

-- ---------------------------------------------------------------------------
-- Storage
-- ---------------------------------------------------------------------------
-- A private bucket. Objects are keyed by "<user_id>/<document_id>/<filename>", and the
-- policies compare the first path segment to auth.uid(), so one candidate cannot read
-- another's upload even with a guessed object name.

insert into storage.buckets (id, name, public)
values ('documents', 'documents', false)
on conflict (id) do nothing;

create policy documents_storage_select_own on storage.objects
  for select using (
    bucket_id = 'documents' and (storage.foldername(name))[1] = auth.uid()::text
  );

create policy documents_storage_insert_own on storage.objects
  for insert with check (
    bucket_id = 'documents' and (storage.foldername(name))[1] = auth.uid()::text
  );

create policy documents_storage_delete_own on storage.objects
  for delete using (
    bucket_id = 'documents' and (storage.foldername(name))[1] = auth.uid()::text
  );
