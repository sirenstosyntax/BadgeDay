-- ---------------------------------------------------------------------------
-- 0004 — a candidate can answer a question without being able to look it up
-- ---------------------------------------------------------------------------
-- questions_select_own is correct and stays: a candidate may read the questions generated
-- from their own documents. What it cannot express is *which columns*. Row-level security
-- is row-level, so "read your own questions" has until now included correct_answer,
-- correct_index, model_answer and explanation — readable with the candidate's own token
-- straight off /rest/v1/questions, before answering anything.
--
-- This is not a privacy breach; the data is theirs. It is a product failure. "Drill cited
-- questions until nothing on the list can surprise you" is worth nothing if the answers
-- ship alongside the questions, and a quiz UI built on select=* would put them in the
-- browser where a candidate finds them by accident rather than by cheating.
--
-- Column privileges are the fix, and they force the rest of this migration: once the
-- candidate cannot read the answer, neither can the API, because the API deliberately
-- runs under the candidate's token. So grading moves into the database.

-- Postgres has no way to revoke a subset of a table-level grant, so the table-level
-- SELECT goes and comes back as an explicit column list. Anything added to questions
-- later is unreadable by clients until it is named here, which is the right default for
-- a table whose whole purpose is holding answers.
revoke select on public.questions from anon, authenticated;
grant select (id, document_id, chunk_id, type, stem, options, created_at)
  on public.questions to authenticated;

-- ---------------------------------------------------------------------------
-- Grading, where the answer lives
-- ---------------------------------------------------------------------------
-- security definer, so it can read the columns the caller cannot. That means none of the
-- candidate's policies apply inside this function and the ownership checks below are the
-- only thing standing between one candidate and another's practice session. They are
-- written first and they are not optional.
--
-- Short answer returns null rather than a verdict. There is a model answer to compare
-- against, not a key to match, and auto-grading free text would be a confident lie about
-- whether an officer knows their guideline. The candidate self-assesses against the model
-- answer this returns.

create function public.submit_response(
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

  perform 1 from public.practice_sessions s
   where s.id = p_session_id and s.user_id = uid;
  if not found then
    raise exception 'no such session' using errcode = 'P0002';
  end if;

  select * into q from public.questions where id = p_question_id;
  if not found then
    raise exception 'no such question' using errcode = 'P0002';
  end if;

  -- The question must come from a document this candidate owns. Without this, a valid
  -- session id plus a guessed question id would grade — and return the explanation for —
  -- somebody else's question.
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

revoke all on function public.submit_response(uuid, uuid, integer, boolean, text) from public;
revoke all on function public.submit_response(uuid, uuid, integer, boolean, text) from anon;
grant execute on function public.submit_response(uuid, uuid, integer, boolean, text)
  to authenticated;

-- ---------------------------------------------------------------------------
-- Reviewing what has already been answered
-- ---------------------------------------------------------------------------
-- 0001 warns that a view without security_invoker is a hole through which any user reads
-- every row, and document_coverage sets the flag for exactly that reason. This view
-- deliberately does the opposite, and the distinction matters:
--
--   document_coverage exposes columns the caller may already read, so running it under
--   the caller's own permissions costs nothing and gains the policies.
--
--   This view exists *because* the caller may no longer read those columns. Running it as
--   invoker would return nothing at all. So it runs as owner and carries its own filter —
--   `r.user_id = auth.uid()` is not decoration here, it is the entire access control, and
--   removing it would expose every candidate's answers to every candidate.
--
-- It joins through responses, so a question appears only once the candidate has answered
-- it. Answers stay unreachable until they have been earned.

create view public.answered_questions
with (security_invoker = false)
as
select
  r.session_id,
  r.answered_at,
  r.is_correct,
  r.selected_index,
  r.answered_boolean,
  r.answered_text,
  q.id as question_id,
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

grant select on public.answered_questions to authenticated;
