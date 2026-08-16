-- ---------------------------------------------------------------------------
-- 0008 — the same entitlement, bought at a different till
-- ---------------------------------------------------------------------------
-- BadgeDay is going into the App Store and Google Play (decision of 2026-08-16, recorded
-- in CLAUDE.md and mobile_release_plan.md). Both stores require that a digital
-- subscription sold inside their app is bought through their billing system, so a
-- candidate can now arrive entitled by one of three tills:
--
--   * Stripe, on the web                    -> profiles.subscription_status / access_expires_at
--   * Google Play Billing, in the Android app
--   * StoreKit, in the iOS app
--
-- The temptation is to write the store's result straight onto profiles and be done. That
-- is wrong for a reason worth stating, because it is not obvious until it bites: profiles
-- has exactly ONE stripe_customer_id and ONE subscription_status, and a candidate who
-- subscribes on their phone has no Stripe customer at all. Writing a Play subscription
-- into subscription_status would mean a later Stripe webhook, keyed on a customer id that
-- matches nobody, silently overwrites it — or worse, that the two tills take turns
-- clobbering each other for a candidate who has paid at both.
--
-- So store purchases get their own table, and entitlement becomes a question with one
-- answer over both sources. profiles.subscription_status stays what it has always been:
-- what STRIPE says. Nothing in this migration changes how a Stripe purchase behaves.
--
-- WHY A TABLE AND NOT COLUMNS. Three reasons, in order of how much they matter:
--
--   1. A candidate can legitimately hold more than one. Someone who subscribes monthly on
--      iOS and later buys the 90-day intensive on the web has two live purchases, and
--      collapsing them into one row loses the ability to answer "what am I actually paying
--      for" — which is the first question a support email asks.
--   2. Cancellation is not ours to perform. A Play or StoreKit subscription is managed in
--      the store, not in our billing portal, and the UI has to know which one to send the
--      candidate to. That is provenance, and provenance belongs in a row.
--   3. Store notifications are keyed on identifiers we do not choose — Play's purchase
--      token, Apple's originalTransactionId — and those need somewhere to live with a
--      unique constraint on them, so a replayed notification updates rather than doubles.

create table public.store_purchases (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,

  platform text not null check (platform in ('play', 'appstore')),

  -- The store's product identifier, e.g. 'badgeday.promote.monthly'. Kept verbatim rather
  -- than mapped to our plan names, because when a notification arrives naming a product we
  -- do not recognise, the raw string is the only thing that tells a human what happened.
  product_id text not null,

  -- Play: the purchase token. Apple: originalTransactionId, which is stable across the
  -- whole renewal chain and is the only Apple identifier that stays put.
  purchase_identifier text not null,

  -- A recurring subscription, or a one-time purchase that expires on a date. Same two
  -- shapes Stripe sells, deliberately — the store is a different till, not a different
  -- product line.
  kind text not null check (kind in ('subscription', 'pass')),

  -- Same vocabulary as profiles.subscription_status, and for the same reason: a candidate
  -- whose card failed is in the same situation whichever till they used, and two words for
  -- it would mean two code paths. 'past_due' covers Play's ON_HOLD/GRACE_PERIOD and
  -- Apple's billing-retry, none of which grant access — see the note in 0005 about that
  -- being the reversible direction.
  status text not null default 'none'
    check (status in ('none', 'active', 'past_due', 'canceled')),

  -- When access runs out. Set for a pass, and also for a subscription: both stores tell us
  -- the paid-through date on every renewal, and honouring it means a renewal notification
  -- that is late or lost does not cut off a candidate who has in fact paid.
  expires_at timestamptz,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  -- One row per purchase, so a replayed or out-of-order notification updates the row it
  -- already wrote. Both stores retry notifications, and both can deliver them out of
  -- order; without this, a retry would create a second row and a cancellation would land
  -- on only one of them.
  unique (platform, purchase_identifier)
);

create index store_purchases_user on public.store_purchases (user_id);

create trigger store_purchases_touch_updated_at
  before update on public.store_purchases
  for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------------------
-- Who may read and write this
-- ---------------------------------------------------------------------------
-- Read: the owner. The account screen has to be able to say "your subscription is through
-- the App Store — cancel it there", and it cannot say that without seeing the row.
--
-- Write: nobody with a candidate's token. This is 0005's lesson applied before it can be
-- learned twice. That migration exists because profiles was candidate-writable and a
-- candidate could PATCH themselves to 'active' until 2099. This table holds exactly the
-- same kind of value, so it gets the same treatment from the start: no insert, update or
-- delete privilege for anon or authenticated, and no policy pretending otherwise. The
-- writer is a store notification we have cryptographically verified, speaking through a
-- service-role client.

alter table public.store_purchases enable row level security;

create policy store_purchases_select_own on public.store_purchases
  for select using (auth.uid() = user_id);

revoke insert, update, delete on public.store_purchases from anon, authenticated;

-- ---------------------------------------------------------------------------
-- Entitlement, still one question with one answer
-- ---------------------------------------------------------------------------
-- 0005 put the entitlement rule in this function precisely so the API, the row-level
-- security policies, and submit_response could not drift apart about who has paid. A
-- third till does not change that; it widens the one rule.
--
-- Replaced in full rather than patched, because a function is replaced whole. The Stripe
-- half is character-for-character what 0005 wrote. The new half is the last clause.
--
-- security definer, so it reads store_purchases past the select policy above — the same
-- footing on which it already reads profiles.

create or replace function public.has_access(candidate uuid)
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
  )
  or exists (
    select 1
      from public.store_purchases sp
     where sp.user_id = candidate
       and (
         sp.status = 'active'
         or (sp.expires_at is not null and sp.expires_at > now())
       )
  );
$$;

revoke all on function public.has_access(uuid) from public;
grant execute on function public.has_access(uuid) to authenticated;
