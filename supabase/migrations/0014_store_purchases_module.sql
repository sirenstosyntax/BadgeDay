-- ---------------------------------------------------------------------------
-- 0014 — store_purchases.module so a Recruit Play SKU cannot open Promote
-- ---------------------------------------------------------------------------
-- 0008's has_access treats any live store_purchases row as Promote access.
-- That was correct when only Promote SKUs existed. Recruit checkout now
-- writes Play / App Store purchases onto the same table (for managed_by
-- provenance). Without a module column, a Recruit monthly would satisfy
-- has_access and open the reading-list product the candidate did not buy.
--
-- Existing rows default to promote — they were Promote purchases. Recruit
-- writes set module = 'recruit'. has_recruit_access still reads only
-- entitlements; this column is the Promote-side filter.

alter table public.store_purchases
  add column module text not null default 'promote'
  check (module in ('promote', 'recruit'));

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
       and sp.module = 'promote'
       and (
         sp.status = 'active'
         or (sp.expires_at is not null and sp.expires_at > now())
       )
  );
$$;

revoke all on function public.has_access(uuid) from public;
grant execute on function public.has_access(uuid) to authenticated;
