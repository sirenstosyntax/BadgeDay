-- ---------------------------------------------------------------------------
-- 0003 — claiming a job, atomically
-- ---------------------------------------------------------------------------
-- The claim documented in 0001 is `for update skip locked`, and it has to be one
-- statement: select-then-update from the worker would let two workers read the same
-- queued row before either wrote to it, and both would run the ingestion. PostgREST has
-- no way to express row locking, so the claim lives here and the worker calls it.
--
-- `skip locked` is what makes more than one worker useful. Without it, the second worker
-- blocks on the first worker's lock and the queue drains at single-worker speed while
-- looking like it has concurrency.
--
-- Returns a set rather than a single row so that "nothing to do" is an empty result
-- instead of a row of nulls the caller has to recognise.
--
-- attempts increments on claim, not on failure. A worker that dies mid-job — OOM,
-- deploy, power — never reports anything, and if the count only rose on a clean failure
-- that job would be retried forever. Counting the attempt when it starts means a job
-- that reliably kills its worker still exhausts max_attempts and stops.

create function public.claim_job(worker text)
returns setof public.jobs
language plpgsql
as $$
declare
  claimed_id uuid;
begin
  select id into claimed_id
    from public.jobs
   where status = 'queued'
     and run_after <= now()
   order by created_at
   for update skip locked
   limit 1;

  if claimed_id is null then
    return;
  end if;

  return query
  update public.jobs
     set status = 'running',
         attempts = attempts + 1,
         locked_at = now(),
         locked_by = worker
   where id = claimed_id
  returning *;
end;
$$;

-- Postgres grants execute on new functions to PUBLIC, and PostgREST exposes anything a
-- role may execute. Without this, a signed-in candidate could call claim_job over the
-- REST API. RLS on `jobs` would keep the returned row empty — the function is not
-- security definer — but the UPDATE inside it would still be attempted on every call,
-- and a queue that any authenticated user can poke at is not a queue we control.
revoke all on function public.claim_job(text) from public;
revoke all on function public.claim_job(text) from anon;
revoke all on function public.claim_job(text) from authenticated;
