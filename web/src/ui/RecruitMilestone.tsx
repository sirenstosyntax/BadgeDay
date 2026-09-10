import { useEffect, useState } from 'react'
import { track } from '../lib/analytics'
import { ApiError, api } from '../lib/api'
import {
  BANK_EXHAUSTED_EVENT,
  MILESTONE_FACT,
  MILESTONE_HANDOFF,
  MILESTONE_MEANING,
  MILESTONE_MONEY_LEAD,
  MILESTONE_MONEY_STRIPE,
  MILESTONE_PORTAL_FAILED,
  MILESTONE_STANDING_STUB,
  MILESTONE_STANDING_TITLE,
  milestoneBilling,
} from '../lib/recruitMilestone'
import type { Account } from '../lib/types'

/**
 * Oral-board milestone when nothing novel remains. Calm copy, no mic, no score.
 * The readiness plan CTA and a typed custom prompt are omitted — those routes
 * are not built.
 */
export function RecruitMilestone({
  answeredCount,
  bankSize,
  account,
  onManageBilling,
  onOpenAccount,
}: {
  answeredCount: number
  bankSize: number
  account: Account | null
  onManageBilling: () => void
  onOpenAccount: () => void
}) {
  const billing = milestoneBilling(account)
  const [portalFailed, setPortalFailed] = useState(false)

  useEffect(() => {
    track(BANK_EXHAUSTED_EVENT, {
      answered_count: answeredCount,
      bank_size: bankSize,
    })
  }, [answeredCount, bankSize])

  async function openStripePortal() {
    setPortalFailed(false)
    try {
      const { url } = await api.billing.portal()
      window.location.href = url
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        setPortalFailed(true)
        return
      }
      setPortalFailed(true)
    }
  }

  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <p className="text-lg font-medium text-stone-900 dark:text-stone-100">
          {MILESTONE_FACT(answeredCount)}
        </p>
        <p className="text-sm text-stone-600 dark:text-stone-400">{MILESTONE_MEANING}</p>
      </section>

      <section className="space-y-2">
        <h3 className="text-sm font-medium text-stone-800 dark:text-stone-200">
          {MILESTONE_STANDING_TITLE}
        </h3>
        <p className="text-sm text-stone-600 dark:text-stone-400">{MILESTONE_STANDING_STUB}</p>
      </section>

      <section>
        <p className="text-sm text-stone-600 dark:text-stone-400">{MILESTONE_HANDOFF}</p>
      </section>

      {billing !== 'none' && (
        <section className="space-y-3">
          <p className="text-sm text-stone-600 dark:text-stone-400">
            {billing === 'stripe'
              ? `${MILESTONE_MONEY_LEAD} ${MILESTONE_MONEY_STRIPE}`
              : MILESTONE_MONEY_LEAD}
          </p>
          {billing === 'stripe' ? (
            <button
              type="button"
              onClick={() => void openStripePortal()}
              className="rounded-lg border border-stone-300 px-4 py-2 text-sm dark:border-stone-700"
            >
              Manage billing
            </button>
          ) : (
            <button
              type="button"
              onClick={onManageBilling}
              className="rounded-lg border border-stone-300 px-4 py-2 text-sm dark:border-stone-700"
            >
              Manage billing
            </button>
          )}
          {portalFailed && (
            <div className="space-y-2">
              <p className="text-sm text-stone-600 dark:text-stone-400">{MILESTONE_PORTAL_FAILED}</p>
              <button
                type="button"
                onClick={onOpenAccount}
                className="text-sm text-stone-700 underline dark:text-stone-300"
              >
                Account
              </button>
            </div>
          )}
        </section>
      )}
    </div>
  )
}
