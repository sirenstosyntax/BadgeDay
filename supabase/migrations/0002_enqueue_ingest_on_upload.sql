-- ---------------------------------------------------------------------------
-- 0002 — an uploaded document is always queued for ingestion
-- ---------------------------------------------------------------------------
-- A candidate's client can insert a document: documents_all_own permits it, scoped to
-- their own user_id. It cannot insert a job. `jobs` has row-level security enabled and
-- no policies whatsoever, which denies every client role — deliberately, since the queue
-- is not a candidate-facing surface and never should be.
--
-- That leaves the question of who enqueues. The obvious answer is the upload endpoint,
-- using the service role for that one insert. The cost is that a service-role client
-- then exists inside a request handler, and once it is in scope it is available for
-- every other line in that handler — at which point the privacy boundary starts drifting
-- out of the database and into whatever each future handler remembers to do. See the
-- warning in app/storage/client.py.
--
-- Doing it here instead keeps the entire request path under the candidate's own
-- credentials, and turns "an uploaded document is queued for ingestion" from something
-- every upload path must remember into something the schema guarantees. A second upload
-- route, a bulk import, a repair script — all get the job for free, and none can forget.

create function public.enqueue_ingest_job()
returns trigger
language plpgsql
security definer
-- security definer runs this as the function's owner, which is how it reaches a table
-- the caller is denied. Pinning search_path is mandatory for such a function: without
-- it, a caller controlling their own search_path chooses which `jobs` table gets the
-- insert.
set search_path = public
as $$
begin
  insert into public.jobs (kind, document_id) values ('ingest', new.id);
  return new;
end;
$$;

create trigger documents_enqueue_ingest
  after insert on public.documents
  for each row execute function public.enqueue_ingest_job();
