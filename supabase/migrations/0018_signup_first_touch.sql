-- ---------------------------------------------------------------------------
-- 0018 — First-touch signup attribution beside signup_src
-- ---------------------------------------------------------------------------
-- Additive and nullable. signup_src stays the explicit ?src= tag only.
-- These four columns are the referrer hostname and the three utm tags.
-- No full URL, address, or user agent belongs here.
--
-- Idempotent so a manual paste can be run twice. Apply this on the live
-- database before deploying the API that selects these columns. profiles
-- UPDATE stays revoked (0005); the service role writes them, same as
-- signup_src.

alter table public.profiles
  add column if not exists signup_referrer_domain text,
  add column if not exists signup_utm_source text,
  add column if not exists signup_utm_medium text,
  add column if not exists signup_utm_campaign text;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'profiles_signup_referrer_domain_shape'
      and conrelid = 'public.profiles'::regclass
  ) then
    alter table public.profiles
      add constraint profiles_signup_referrer_domain_shape check (
        signup_referrer_domain is null
        or (
          char_length(signup_referrer_domain) between 1 and 64
          and signup_referrer_domain ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
        )
      );
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'profiles_signup_utm_source_shape'
      and conrelid = 'public.profiles'::regclass
  ) then
    alter table public.profiles
      add constraint profiles_signup_utm_source_shape check (
        signup_utm_source is null
        or (
          char_length(signup_utm_source) between 1 and 64
          and signup_utm_source ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
        )
      );
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'profiles_signup_utm_medium_shape'
      and conrelid = 'public.profiles'::regclass
  ) then
    alter table public.profiles
      add constraint profiles_signup_utm_medium_shape check (
        signup_utm_medium is null
        or (
          char_length(signup_utm_medium) between 1 and 64
          and signup_utm_medium ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
        )
      );
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'profiles_signup_utm_campaign_shape'
      and conrelid = 'public.profiles'::regclass
  ) then
    alter table public.profiles
      add constraint profiles_signup_utm_campaign_shape check (
        signup_utm_campaign is null
        or (
          char_length(signup_utm_campaign) between 1 and 64
          and signup_utm_campaign ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
        )
      );
  end if;
end $$;
