import type { Account, PaywallModule } from './types'

/**
 * Per-module access for the paywall and Account.
 *
 * `/me` keeps Promote on the top-level fields (`entitled`, `subscription_status`)
 * and Recruit on `recruit.*`. A gate that reads only the top-level fields will
 * offer Recruit checkout to someone who already pays for Recruit, and hide
 * Manage billing from them. These helpers are the one place that distinction
 * is made, so the header, Account, and Paywall cannot disagree.
 */

export function moduleEntitled(
  account: Account | null,
  module: PaywallModule,
): boolean {
  if (!account) return false
  if (module === 'recruit') return Boolean(account.recruit?.entitled)
  return account.entitled
}

export function moduleSubscriptionStatus(
  account: Account | null,
  module: PaywallModule,
): Account['subscription_status'] {
  if (!account) return 'none'
  if (module === 'recruit') return account.recruit?.subscription_status ?? 'none'
  return account.subscription_status
}

export function moduleExpiresAt(
  account: Account | null,
  module: PaywallModule,
): string | null {
  if (!account) return null
  if (module === 'recruit') return account.recruit?.access_expires_at ?? null
  return account.access_expires_at
}

export function moduleManagedBy(
  account: Account | null,
  module: PaywallModule,
): Account['managed_by'] {
  if (!account) return null
  if (module === 'recruit') return account.recruit?.managed_by ?? null
  return account.managed_by ?? null
}

/**
 * Offer Stripe / Play checkout only when this module is not already held
 * and there is no live subscription to update in the portal.
 * A canceled, expired plan may buy again.
 */
export function shouldOfferCheckout(
  account: Account | null,
  module: PaywallModule,
): boolean {
  if (moduleEntitled(account, module)) return false
  const status = moduleSubscriptionStatus(account, module)
  return status !== 'active' && status !== 'past_due'
}

/**
 * Something to cancel or update on this module: a subscription that is
 * still live (including past_due). A one-time pass grants access but has
 * nothing to cancel — sending that candidate to the Stripe portal is how
 * they land on an empty manage page. A canceled row without access is
 * not managed here either; that candidate sees See plans.
 */
export function moduleHasManageableBilling(
  account: Account | null,
  module: PaywallModule,
): boolean {
  if (!account) return false
  const status = moduleSubscriptionStatus(account, module)
  return status === 'active' || status === 'past_due'
}

/** Entitled via a one-time pass — access, but no cancelable subscription. */
export function moduleIsPassOnly(
  account: Account | null,
  module: PaywallModule,
): boolean {
  return (
    moduleEntitled(account, module) &&
    moduleSubscriptionStatus(account, module) === 'none'
  )
}

export function anyModuleHasManageableBilling(account: Account | null): boolean {
  return (
    moduleHasManageableBilling(account, 'promote') ||
    moduleHasManageableBilling(account, 'recruit')
  )
}

/** Which module the header Subscribe button is selling, given where they are. */
export function headerSubscribeModule(view: 'recruit' | 'other'): PaywallModule {
  return view === 'recruit' ? 'recruit' : 'promote'
}

/**
 * Which module's till the header Billing button should open. Prefer the
 * screen they are on when that module has billing; otherwise the other one.
 */
export function headerManageModule(
  account: Account | null,
  view: 'recruit' | 'other',
): PaywallModule {
  const preferred = headerSubscribeModule(view)
  if (moduleHasManageableBilling(account, preferred)) return preferred
  return preferred === 'recruit' ? 'promote' : 'recruit'
}

export function modulePlanSummary(
  account: Account | null,
  module: PaywallModule,
): string {
  if (!account) return 'Loading your account…'
  const status = moduleSubscriptionStatus(account, module)
  if (status === 'active') return 'Active subscription.'
  if (moduleEntitled(account, module)) {
    const when = moduleExpiresAt(account, module)
    const through = when
      ? `Access through ${new Date(when).toLocaleDateString()}.`
      : 'Active access.'
    if (status === 'none') {
      return `${through} One-time pass — nothing to cancel.`
    }
    return through
  }
  if (status === 'past_due') return 'Subscription payment past due.'
  if (status === 'canceled') return 'Subscription canceled.'
  return 'No active plan.'
}
