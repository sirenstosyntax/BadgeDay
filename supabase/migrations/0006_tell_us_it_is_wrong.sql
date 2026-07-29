-- Two ways of finding out the product is broken.
--
-- Verification proves a question is grounded in the section it cites. It cannot prove the
-- question is *right* — a perfectly cited question can still be a bad one, and nothing in
-- the pipeline notices. The candidate reading it is the only party who can, and until now
-- he had nowhere to say so. That is the first table here.
--
-- The second is smaller but the failure is worse: a job that exhausts its retries stops
-- silently. A candidate uploaded a document, paid for the privilege, and nothing happened.
-- The row sits at 'failed' and no process ever looks at it again. `dead_jobs` is the view
-- that makes that queryable rather than archaeological.

-- ---------------------------------------------------------------------------
-- question reports
-- ---------------------------------------------------------------------------
-- `reason` is a small closed set rather than free text alone, because the categories are
-- the useful part: "this isn't in my document" is a citation failure and needs the chunker
-- or the generator looked at, while "the answer is wrong" is a generation failure. Free
-- text is kept alongside, since the category a candidate picks is a guess about our
-- internals and his sentence is what actually says what he saw.
create table public.question_reports (
  id uuid primary key default gen_random_uuid(),
  question_id uuid not null references public.questions(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  reason text not null check (reason in (
    'not_in_document',   -- the cited section does not say this
    'answer_wrong',      -- it is in the document but the marked answer is not right
    'unclear',           -- ambiguous, two defensible answers, badly worded
    'other'
  )),
  detail text check (detail is null or length(detail) <= 2000),
  created_at timestamptz not null default now(),

  -- Triage state. Deliberately not a workflow: a report is open until somebody has looked
  -- at it, and then it is not. Anything richer would be a support tool nobody has asked
  -- for, and this needs to exist before launch rather than be designed before launch.
  resolved_at timestamptz,
  resolution text check (resolution is null or length(resolution) <= 2000),

  -- One report per candidate per question. He can change his mind about the reason; he
  -- cannot file the same complaint twice, which would make the counts useless for
  -- deciding which questions are actually bad.
  unique (question_id, user_id)
);

create index question_reports_question_id_idx on public.question_reports (question_id);
create index question_reports_open_idx on public.question_reports (created_at)
  where resolved_at is null;

alter table public.question_reports enable row level security;

-- A candidate may report a question, and may see and amend his own reports. He may not
-- see anyone else's — a report can quote the question and describe what he expected, which
-- is his own work and nobody else's business.
create policy question_reports_insert_own on public.question_reports
  for insert to authenticated
  with check (user_id = (select auth.uid()));

create policy question_reports_select_own on public.question_reports
  for select to authenticated
  using (user_id = (select auth.uid()));

create policy question_reports_update_own on public.question_reports
  for update to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

-- Triage is ours, not his. Resolving a report is a service-role write, so a candidate
-- cannot mark his own complaint handled — the same reasoning as migration 0005, where
-- billing state is not self-service.
revoke update (resolved_at, resolution) on public.question_reports from authenticated;

-- A candidate may withdraw a report he filed. Deleting the question deletes it too, by
-- cascade, which is correct: a report about a question that no longer exists is noise.
create policy question_reports_delete_own on public.question_reports
  for delete to authenticated
  using (user_id = (select auth.uid()));

-- ---------------------------------------------------------------------------
-- dead jobs
-- ---------------------------------------------------------------------------
-- A job is dead when it has spent every attempt it is going to get. The worker logs this
-- at ERROR when it happens, which is the alerting hook — a log-based alert rule is the
-- mechanism available in Container Apps without standing up anything new. This view is the
-- other half: the answer to "is anything broken right now", cheap enough to poll.
--
-- Security invoker so the view answers with the caller's own permissions rather than the
-- definer's. It is queried with the service role; a candidate reaching it through the API
-- would otherwise see other people's failures.
create view public.dead_jobs
  with (security_invoker = true)
  as
select
  j.id,
  j.kind,
  j.document_id,
  d.user_id,
  d.filename,
  j.attempts,
  j.max_attempts,
  j.last_error,
  j.updated_at as died_at
from public.jobs j
join public.documents d on d.id = j.document_id
where j.status = 'failed';

comment on view public.dead_jobs is
  'Jobs that exhausted their retries. A row here is a candidate whose document never '
  'finished processing and who has not been told. Poll it; alert on a non-zero count.';
