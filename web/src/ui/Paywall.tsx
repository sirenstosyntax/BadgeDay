import { useState } from 'react'
import { ApiError, api } from '../lib/api'
import type { Plan } from '../lib/types'

/**
 * Shown when a candidate tries to do the one thing that costs money — add a document or
 * start a session — without an active plan. Reading and deleting are never gated, so this
 * is an overlay over their documents, not a wall that replaces them.
 *
 * No prices are printed here. The amount lives in Stripe (the brief keeps pricing out of
 * the code), and the candidate sees it on the checkout page a click away. Describing the
 * two plans without a dollar figure is deliberate, not a stub — a number typed here would
 * be a second source of truth that drifts the first time the price changes.
 */
const PLANS: { plan: Plan; name: string; blurb: string }[] = [
  {
    plan: 'monthly',
    name: 'Monthly',
    blurb: 'Keep drilling for as long as you are testing. Cancel anytime from billing.',
  },
  {
    plan: 'intensive_90day',
    name: '90-day intensive',
    blurb: 'One payment, ninety days of access — the run-up to a badge day on the calendar.',
  },
]

export function Paywall({ onClose }: { onClose: () => void }) {
  const [pending, setPending] = useState<Plan | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function choose(plan: Plan) {
    setPending(plan)
    setError(null)
    try {
      const { url } = await api.billing.checkout(plan)
      // A full navigation, not a new tab: the candidate is leaving to pay and comes back to
      // this same app afterwards, where useAccount re-reads their now-active entitlement.
      window.location.href = url
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'Could not reach checkout. Try again in a moment.',
      )
      setPending(null)
    }
  }

  return (
    <div
      className="fixed inset-0 z-20 flex items-center justify-center bg-stone-900/40 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl dark:bg-stone-900"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="text-lg font-semibold">Drill until badge day</h2>
        <p className="mt-1 text-sm text-stone-600 dark:text-stone-400">
          Uploading a document and starting a session need an active plan. Anything you have
          already uploaded stays yours to read and to delete.
        </p>

        <div className="mt-5 space-y-3">
          {PLANS.map(({ plan, name, blurb }) => (
            <button
              key={plan}
              onClick={() => void choose(plan)}
              disabled={pending !== null}
              className="w-full rounded-lg border border-stone-300 p-4 text-left transition hover:border-stone-900 disabled:opacity-60 dark:border-stone-700 dark:hover:border-stone-100"
            >
              <div className="flex items-center justify-between">
                <span className="font-medium">{name}</span>
                <span className="text-xs text-stone-500 dark:text-stone-400">
                  {pending === plan ? 'Redirecting…' : 'Choose →'}
                </span>
              </div>
              <p className="mt-1 text-sm text-stone-600 dark:text-stone-400">{blurb}</p>
            </button>
          ))}
        </div>

        {error && (
          <p className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-900 dark:bg-red-950 dark:text-red-200">
            {error}
          </p>
        )}

        <button
          onClick={onClose}
          className="mt-4 w-full text-sm text-stone-500 hover:underline dark:text-stone-400"
        >
          Not now
        </button>
      </div>
    </div>
  )
}
