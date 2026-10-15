-- ---------------------------------------------------------------------------
-- 0017 — Recruit activation: signup source, test date, follow-up email
-- ---------------------------------------------------------------------------
-- One-tap /start and the two follow-up emails (results, then one reminder).
-- All of this state lives on profiles, which already references auth.users
-- ON DELETE CASCADE (0001). Deleting the account deletes the test date and
-- the reminder with the row. There is no second table to orphan.
--
-- Candidates still cannot UPDATE profiles (0005). The API writes these
-- columns with the service role. signup_src is set once, at sign-up, and
-- only when the link carried a tag. A blank tag writes nothing.

alter table public.profiles
  add column signup_src text,
  add column recruit_test_on date,
  add column recruit_reminder_due_at timestamptz,
  add column recruit_reminder_sent_for date,
  add column recruit_reminder_claimed_at timestamptz,
  add column recruit_results_ready_at timestamptz,
  add column recruit_results_sent_at timestamptz,
  add column recruit_results_claimed_at timestamptz,
  add column recruit_unsubscribed_at timestamptz,
  add column recruit_email_token text;

alter table public.profiles
  add constraint profiles_signup_src_shape check (
    signup_src is null
    or (
      char_length(signup_src) between 1 and 64
      and signup_src ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
    )
  );

create unique index profiles_recruit_email_token_idx
  on public.profiles (recruit_email_token)
  where recruit_email_token is not null;

-- Worker scans. Partial so the index stays small: most accounts never have
-- a pending results email or a pending reminder.
create index profiles_recruit_results_due_idx
  on public.profiles (recruit_results_ready_at)
  where recruit_results_sent_at is null
    and recruit_unsubscribed_at is null;

create index profiles_recruit_reminder_due_idx
  on public.profiles (recruit_reminder_due_at)
  where recruit_reminder_due_at is not null
    and recruit_unsubscribed_at is null;
