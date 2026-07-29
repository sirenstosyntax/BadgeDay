-- 0007 — the revoke in 0006 was a no-op, and this is the fix.
--
-- 0006 wrote:
--
--     revoke update (resolved_at, resolution) on public.question_reports from authenticated;
--
-- and it did nothing. Supabase grants ALL at the *table* level to `anon` and
-- `authenticated` by default, and in Postgres a column-level revoke cannot cut a hole in a
-- table-level grant — the table grant still covers every column. So a candidate could mark
-- his own complaint resolved, which is precisely what 0006's comment said he must not be
-- able to do. The comment was right and the SQL was decorative.
--
-- 0005 already had the correct pattern for exactly this situation, on `profiles`: revoke
-- update at the table level, then grant it back on the named columns a candidate is
-- allowed to write. It was not followed here.
--
-- Worth stating plainly, because it is the general lesson: this class of bug is invisible
-- in review. The migration reads as though it does the right thing, applies without error,
-- and leaves the privilege in place. Only asking the database what it actually granted
-- finds it — which is the same reason `scripts/verify_schema.py` exists, and why its check
-- reads the row back rather than trusting the status code of the update.

revoke update on public.question_reports from anon, authenticated;

-- What a candidate may still change about his own report: which category, and what he
-- wrote. He can decide the answer is wrong rather than missing, or add the detail he did
-- not have time for mid-session. Both are him telling us more, and both are covered by the
-- existing row policy so he can only reach his own rows.
grant update (reason, detail) on public.question_reports to authenticated;

-- Triage stays ours. resolved_at and resolution are service-role writes, so the open queue
-- means what it says: a report is open until somebody who is not the complainant has
-- looked at it.
