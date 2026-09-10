import type { Account } from './types'

export const MILESTONE_FACT = (answeredCount: number) =>
  `You've answered every question we have — ${answeredCount} of them, none twice.`

export const MILESTONE_MEANING =
  "The tool has said what it can. Surprise is used up; rehearsed repeats train the wrong skill, so we won't offer them."

export const MILESTONE_STANDING_TITLE = 'Across your recent answers'

export const MILESTONE_STANDING_STUB =
  'Looking back across your recent answers — what held and what still drops under pressure will show here once we have enough history to summarize. This is not a locked door.'

export const MILESTONE_HANDOFF =
  "Next reps belong in front of people — a mentor mock board, a station visit, or a ride-along. We name the routes; we don't book the provider."

export const MILESTONE_MONEY_LEAD =
  'Nothing new until we add questions or older ones come back into rotation.'

export const MILESTONE_MONEY_STRIPE =
  "Pause from your account page; we'll email when there's more."

export const MILESTONE_PORTAL_FAILED =
  'The billing portal could not be opened. Nothing was paused. You can manage your plan from Account.'

export const BANK_EXHAUSTED_EVENT = 'recruit_bank_exhausted_viewed'

export type MilestoneBilling = 'stripe' | 'store' | 'none'

export function milestoneBilling(account: Account | null): MilestoneBilling {
  if (!account) return 'none'
  if (account.managed_by === 'play' || account.managed_by === 'appstore') return 'store'
  if (account.subscription_status !== 'none') return 'stripe'
  return 'none'
}
