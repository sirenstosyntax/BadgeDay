import { useEffect, useState } from 'react'
import { ApiError, api } from '../lib/api'
import {
  browserPlayBilling,
  configuredSkus,
  type PlayItemDetails,
  type PlayProductIds,
} from '../lib/playBilling'
import type { PaywallModule, Plan } from '../lib/types'

/**
 * Shown when a candidate tries to do the one thing that costs money — add a document,
 * start a Promote session, or start another Recruit board — without an active plan.
 *
 * No prices are printed here as ours. On the web, the amount lives in Stripe. Inside
 * the TWA, Play is the till and the figure comes from Digital Goods getDetails.
 * A number typed here would be a second source of truth.
 */
const PROMOTE_PLANS: { plan: Plan; name: string; blurb: string }[] = [
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

const RECRUIT_PLANS: { plan: Plan; name: string; blurb: string }[] = [
  {
    plan: 'recruit_monthly',
    name: 'Monthly',
    blurb: 'Keep practicing the oral board. Cancel anytime from billing.',
  },
  {
    plan: 'recruit_intensive_90day',
    name: '90-day pass',
    blurb: 'One payment, ninety days of oral-board practice.',
  },
  {
    plan: 'recruit_6month',
    name: '6-month pass',
    blurb: 'One payment for a hiring-cycle stretch of practice.',
  },
  {
    plan: 'recruit_annual',
    name: 'Annual',
    blurb: 'A year of oral-board practice. Renews until you cancel.',
  },
]

type Till = 'checking' | 'stripe' | 'play' | 'play-unlisted'

export function Paywall({
  onClose,
  playProducts,
  onPlayUnlocked,
  module = 'promote',
}: {
  onClose: () => void
  playProducts?: PlayProductIds | null
  onPlayUnlocked?: () => void
  module?: PaywallModule
}) {
  const [pending, setPending] = useState<Plan | string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [till, setTill] = useState<Till>('checking')
  const [playItems, setPlayItems] = useState<PlayItemDetails[]>([])

  useEffect(() => {
    let cancelled = false
    const purchases = browserPlayBilling(api.billing.reportPlayPurchase)
    void purchases.available().then(async (store) => {
      if (cancelled) return
      if (!store) {
        setTill('stripe')
        return
      }
      const skus = configuredSkus(playProducts, module)
      if (skus.length === 0) {
        setTill('play-unlisted')
        return
      }
      const items = await purchases.detailsFor(skus)
      if (cancelled) return
      // Play has to recognise the id. A configured env var that is not a Console
      // product must not become a buy button — that would be a fake offer.
      if (items.length === 0) {
        setTill('play-unlisted')
        return
      }
      setPlayItems(items)
      setTill('play')
    })
    return () => {
      cancelled = true
    }
  }, [playProducts, module])

  async function chooseStripe(plan: Plan) {
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

  async function choosePlay(item: PlayItemDetails) {
    setPending(item.itemId)
    setError(null)
    try {
      const purchases = browserPlayBilling(api.billing.reportPlayPurchase)
      const result = await purchases.buy(item.itemId)
      if (!result.ok) {
        setError('Google Play did not complete that purchase.')
        setPending(null)
        return
      }
      onPlayUnlocked?.()
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'Could not complete the Play purchase.',
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
        <h2 className="text-lg font-semibold">
          {module === 'recruit' ? 'Keep practicing the oral board' : 'Drill until badge day'}
        </h2>
        {till === 'play-unlisted' ? (
          <p className="mt-1 text-sm text-stone-600 dark:text-stone-400">
            This Play build does not sell a plan yet. The offer has not been named, so
            there is nothing to buy here and no price to show. The website still uses
            Stripe test checkout until then.
          </p>
        ) : module === 'recruit' ? (
          <p className="mt-1 text-sm text-stone-600 dark:text-stone-400">
            Your free board is used. A Recruit plan unlocks more oral-board practice.
            Amounts are the ones Stripe or Play show at checkout — not a figure typed here.
          </p>
        ) : (
          <p className="mt-1 text-sm text-stone-600 dark:text-stone-400">
            Uploading a document and starting a session need an active plan. Anything you have
            already uploaded stays yours to read and to delete.
          </p>
        )}

        {till === 'checking' && (
          <p className="mt-5 text-sm text-stone-500">Checking how you can pay…</p>
        )}

        {till === 'stripe' && (
          <div className="mt-5 space-y-3">
            {(module === 'recruit' ? RECRUIT_PLANS : PROMOTE_PLANS).map(({ plan, name, blurb }) => (
              <button
                key={plan}
                onClick={() => void chooseStripe(plan)}
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
        )}

        {till === 'play' && (
          <div className="mt-5 space-y-3">
            {playItems.map((item) => (
              <button
                key={item.itemId}
                onClick={() => void choosePlay(item)}
                disabled={pending !== null}
                className="w-full rounded-lg border border-stone-300 p-4 text-left transition hover:border-stone-900 disabled:opacity-60 dark:border-stone-700 dark:hover:border-stone-100"
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium">{item.title}</span>
                  <span className="text-xs text-stone-500 dark:text-stone-400">
                    {pending === item.itemId
                      ? 'Purchasing…'
                      : item.price?.label || item.price?.value || 'Choose →'}
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}

        {till === 'stripe' && (
          <p className="mt-4 text-xs leading-relaxed text-stone-500 dark:text-stone-400">
            {module === 'recruit'
              ? 'Monthly and annual renew until you cancel; the 90-day and 6-month passes are single payments and do not renew. '
              : 'Monthly renews until you cancel; the 90-day intensive is a single payment and does not renew. '}
            Payments are non-refundable — cancelling keeps your access to the end of
            the period you have paid for. Choosing a plan takes you to Stripe, and means you
            agree to the{' '}
            <a href="/terms" className="underline">
              Terms of Service
            </a>{' '}
            and{' '}
            <a href="/privacy" className="underline">
              Privacy Policy
            </a>
            .
          </p>
        )}

        {till === 'play' && (
          <p className="mt-4 text-xs leading-relaxed text-stone-500 dark:text-stone-400">
            Purchases on this device go through Google Play. The price Play shows is the
            price you pay. Choosing a plan means you agree to the{' '}
            <a href="/terms" className="underline">
              Terms of Service
            </a>{' '}
            and{' '}
            <a href="/privacy" className="underline">
              Privacy Policy
            </a>
            .
          </p>
        )}

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
