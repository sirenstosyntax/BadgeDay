-- ---------------------------------------------------------------------------
-- 0012 — entitlements(user, module): Recruit and Promote are separate plans
-- ---------------------------------------------------------------------------
-- Ship gate #4. Recruit is a separate plan (recruit_scope.md, 2026-07-26), so
-- one entitlement per account no longer expresses what a candidate has bought.
-- A table keyed on (user, module) beats adding recruit_* columns to profiles:
-- a third module would need another migration, and every gate would need
-- editing, where a row does not.
--
-- Promote's live path is unchanged. has_access still reads profiles and
-- store_purchases. This table is the home for Recruit, and is ready for
-- Promote when checkout is later pointed at it. Do not treat a Promote
-- subscription as Recruit access, or the other way around.
--
-- Pricing is held. Stripe stays in test mode. The env vars named in
-- badgeday_pricing.md / .env.example are blank placeholders — Grant has not
-- said go live, so this migration grants nothing by existing.

-- ---------------------------------------------------------------------------
-- The table
-- ---------------------------------------------------------------------------
-- One row per (user, module). A subscription and a pass on the same module
-- share the row the way they share a profiles row today: status grants while
-- active, access_expires_at grants while in the future, either is enough.
-- past_due does not grant — same reversible stance as 0005.

create table public.entitlements (
  user_id uuid not null references auth.users(id) on delete cascade,
  module text not null check (module in ('promote', 'recruit')),
  subscription_status text not null default 'none'
    check (subscription_status in ('none', 'active', 'past_due', 'canceled')),
  access_expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, module)
);

create index entitlements_module on public.entitlements (module);

create trigger entitlements_touch_updated_at
  before update on public.entitlements
  for each row execute function public.touch_updated_at();

-- ---------------------------------------------------------------------------
-- Who may read and write this
-- ---------------------------------------------------------------------------
-- Read: the owner. The account screen will need to say which module they hold.
--
-- Write: nobody with a candidate's token. 0005 exists because profiles was
-- candidate-writable and a candidate could PATCH themselves to 'active' until
-- 2099. This table holds the same kind of value, so it gets the same treatment
-- from the start: no insert, update or delete privilege for anon or
-- authenticated, and no policy pretending otherwise. The writer is a verified
-- Stripe / store notification, speaking through a service-role client — or a
-- helper in tests. A candidate must not be able to grant themselves either
-- module.

alter table public.entitlements enable row level security;

create policy entitlements_select_own on public.entitlements
  for select using (auth.uid() = user_id);

revoke insert, update, delete on public.entitlements from anon, authenticated;

-- ---------------------------------------------------------------------------
-- Entitlement, one question per module
-- ---------------------------------------------------------------------------
-- Same rule as has_access, scoped to a module. security definer so it reads
-- past the select policy — the same footing on which has_access reads
-- profiles. An unknown module name matches no row and returns false; it does
-- not raise, because a typo in a caller must withhold access, not 500.

create function public.has_module_access(candidate uuid, p_module text)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
      from public.entitlements e
     where e.user_id = candidate
       and e.module = p_module
       and (
         e.subscription_status = 'active'
         or (e.access_expires_at is not null and e.access_expires_at > now())
       )
  );
$$;

revoke all on function public.has_module_access(uuid, text) from public;
grant execute on function public.has_module_access(uuid, text) to authenticated;

-- 0011's stub always returned false. This is the real check. Promote's
-- has_access is still a different product and is still not consulted.

create or replace function public.has_recruit_access(candidate uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select public.has_module_access(candidate, 'recruit');
$$;

revoke all on function public.has_recruit_access(uuid) from public;
grant execute on function public.has_recruit_access(uuid) to authenticated;
