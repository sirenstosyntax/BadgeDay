import { useEffect, useState } from 'react'
import { ApiError, api } from './lib/api'
import { useAccount } from './lib/account'
import { signOut, useSession } from './lib/auth'
import {
  anyModuleHasManageableBilling,
  headerManageModule,
  headerSubscribeModule,
  moduleManagedBy,
  shouldOfferCheckout,
} from './lib/moduleAccess'
import { browserPlayBilling } from './lib/playBilling'
import { PLAY_SUBSCRIPTIONS_URL } from './lib/recruitMilestone'
import type { PaywallModule } from './lib/types'
import { Account } from './ui/Account'
import { Choose } from './ui/Choose'
import { Documents } from './ui/Documents'
import { LegalLinks } from './ui/LegalLinks'
import { Paywall } from './ui/Paywall'
import { Quiz } from './ui/Quiz'
import { Recruit } from './ui/Recruit'
import { Review } from './ui/Review'
import { Saved } from './ui/Saved'
import { SignIn } from './ui/SignIn'

/**
 * Where the candidate is. A tagged union rather than a router: the app has four places
 * and two of them need a session id, which a union carries and a path string would have
 * to be parsed back out of. When there is a reason for real URLs — sharing, deep links,
 * the back button — that is the moment to add a router, not before.
 */
type View =
  | { name: 'choose' }
  | { name: 'documents' }
  | { name: 'saved' }
  | { name: 'account' }
  | { name: 'quiz'; sessionId: string }
  | { name: 'review'; sessionId: string }
  | { name: 'recruit' }

export default function App() {
  const { session, loading } = useSession()
  const { account, entitled, refreshAccount } = useAccount(!!session)
  const [view, setView] = useState<View>({ name: 'choose' })
  const [starting, setStarting] = useState(false)
  const [showPaywall, setShowPaywall] = useState(false)
  const [paywallModule, setPaywallModule] = useState<PaywallModule>('promote')
  const [notice, setNotice] = useState<string | null>(null)

  // Coming back from a successful checkout, entitlement was set by Stripe's webhook, not by
  // this app — so the answer loaded on mount is stale. Re-ask, and keep asking briefly,
  // because the webhook and the redirect race and the webhook sometimes lands second.
  useEffect(() => {
    if (!session) return
    const params = new URLSearchParams(window.location.search)
    if (params.get('checkout') !== 'success') return
    window.history.replaceState(null, '', window.location.pathname)

    let tries = 0
    const timer = setInterval(() => {
      void refreshAccount()
      if (++tries >= 5) clearInterval(timer)
    }, 2000)
    return () => clearInterval(timer)
  }, [session, refreshAccount])

  // Inside the TWA, Play already knows what this Google account bought. Report
  // those tokens so the server can acknowledge them (Play refunds an
  // unacknowledged purchase after three days) and so a reinstall comes back
  // entitled. A browser tab has no Digital Goods service; this is a no-op.
  useEffect(() => {
    if (!session) return
    let cancelled = false
    const purchases = browserPlayBilling(api.billing.reportPlayPurchase)
    void purchases.restore().then((ids) => {
      if (!cancelled && ids.length > 0) void refreshAccount()
    })
    return () => {
      cancelled = true
    }
  }, [session, refreshAccount])

  // Blank rather than a spinner: restoring a stored session takes a few milliseconds, and
  // a spinner that flashes for one frame reads as jank. What must not happen here is
  // rendering SignIn, which would tell a returning candidate they are logged out.
  if (loading) {
    return <div className="min-h-screen bg-stone-50 dark:bg-stone-950" />
  }

  if (!session) {
    return <SignIn />
  }

  function needsAccess() {
    void refreshAccount()
    setPaywallModule('promote')
    setShowPaywall(true)
  }

  function needsRecruitAccess() {
    void refreshAccount()
    setPaywallModule('recruit')
    setShowPaywall(true)
  }

  async function practise(documentId: string | null) {
    if (!entitled) {
      needsAccess()
      return
    }
    setStarting(true)
    try {
      const started = await api.practice.start(documentId)
      setView({ name: 'quiz', sessionId: started.id })
    } catch (caught) {
      // Entitlement can lapse while the app is open; the server is the authority, so a 402
      // here overrides the optimistic `entitled` check above rather than contradicting it.
      if (caught instanceof ApiError && caught.status === 402) {
        needsAccess()
      } else {
        setNotice(caught instanceof Error ? caught.message : 'Could not start a session.')
      }
    } finally {
      setStarting(false)
    }
  }

  async function manageBilling(module?: PaywallModule) {
    setNotice(null)
    const which =
      module ??
      headerManageModule(account, view.name === 'recruit' ? 'recruit' : 'other')
    const till = moduleManagedBy(account, which)
    if (till === 'play') {
      window.location.href = PLAY_SUBSCRIPTIONS_URL
      return
    }
    if (till === 'appstore') {
      setView({ name: 'account' })
      return
    }
    try {
      const { url } = await api.billing.portal()
      window.location.href = url
    } catch (caught) {
      setNotice(
        caught instanceof Error ? caught.message : 'Could not open billing right now.',
      )
    }
  }

  // The account and its token are gone once deletion returns, so signing out is not a
  // courtesy — it clears the now-invalid local session and drops the app back to sign-in.
  async function afterDeleted() {
    await signOut()
  }

  return (
    <div className="min-h-screen bg-stone-50 text-stone-900 dark:bg-stone-950 dark:text-stone-100">
      <header className="border-b border-stone-200 dark:border-stone-800">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
          <button
            onClick={() => setView({ name: 'choose' })}
            className="font-semibold tracking-tight"
          >
            BadgeDay
          </button>
          <div className="flex items-center gap-3 text-sm">
            {view.name !== 'recruit' && (
              <button
                onClick={() => setView({ name: 'recruit' })}
                className="text-stone-600 hover:underline dark:text-stone-400"
              >
                Oral board
              </button>
            )}
            {view.name !== 'saved' && (
              <button
                onClick={() => setView({ name: 'saved' })}
                className="text-stone-600 hover:underline dark:text-stone-400"
              >
                Saved
              </button>
            )}
            {anyModuleHasManageableBilling(account) && (
              <button
                onClick={() => void manageBilling()}
                className="text-stone-600 hover:underline dark:text-stone-400"
              >
                Billing
              </button>
            )}
            {shouldOfferCheckout(
              account,
              headerSubscribeModule(view.name === 'recruit' ? 'recruit' : 'other'),
            ) && (
              <button
                onClick={() => {
                  setPaywallModule(
                    headerSubscribeModule(view.name === 'recruit' ? 'recruit' : 'other'),
                  )
                  setShowPaywall(true)
                }}
                className="rounded-md bg-stone-900 px-2 py-1 font-medium text-white dark:bg-stone-100 dark:text-stone-900"
              >
                Subscribe
              </button>
            )}
            <button
              onClick={() => setView({ name: 'account' })}
              className="text-stone-500 hover:underline dark:text-stone-400"
            >
              <span className="sm:hidden">Account</span>
              <span className="hidden sm:inline">{session.user.email}</span>
            </button>
            <button
              onClick={signOut}
              className="rounded-md border border-stone-300 px-2 py-1 dark:border-stone-700"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-8">
        {notice && (
          <p className="mb-6 rounded-lg bg-red-50 p-3 text-sm text-red-900 dark:bg-red-950 dark:text-red-200">
            {notice}
          </p>
        )}
        {starting ? (
          <p className="text-sm text-stone-500">Starting…</p>
        ) : view.name === 'quiz' ? (
          <Quiz
            sessionId={view.sessionId}
            onDone={() => setView({ name: 'documents' })}
            onReview={() => setView({ name: 'review', sessionId: view.sessionId })}
          />
        ) : view.name === 'review' ? (
          <Review sessionId={view.sessionId} onDone={() => setView({ name: 'documents' })} />
        ) : view.name === 'saved' ? (
          <Saved onDone={() => setView({ name: 'choose' })} />
        ) : view.name === 'account' ? (
          <Account
            account={account}
            onManageBilling={(module) => void manageBilling(module)}
            onSubscribe={(module) => {
              setPaywallModule(module)
              setShowPaywall(true)
            }}
            onDeleted={() => void afterDeleted()}
            onDone={() => setView({ name: 'choose' })}
          />
        ) : view.name === 'recruit' ? (
          <Recruit
            onDone={() => setView({ name: 'choose' })}
            account={account}
            onOpenAccount={() => setView({ name: 'account' })}
            onNeedsAccess={needsRecruitAccess}
          />
        ) : view.name === 'documents' ? (
          <Documents
            entitled={entitled}
            onNeedsAccess={needsAccess}
            onPractise={(id) => void practise(id)}
          />
        ) : (
          <Choose
            onOralBoard={() => setView({ name: 'recruit' })}
            onReadingList={() => setView({ name: 'documents' })}
          />
        )}
      </main>

      <footer className="mx-auto max-w-3xl px-4 pb-10">
        <LegalLinks />
      </footer>

      {showPaywall && (
        <Paywall
          onClose={() => setShowPaywall(false)}
          playProducts={account?.play_products}
          module={paywallModule}
          alreadyEntitled={!shouldOfferCheckout(account, paywallModule)}
          onManageBilling={() => {
            setShowPaywall(false)
            void manageBilling(paywallModule)
          }}
          onPlayUnlocked={() => {
            void refreshAccount()
            setShowPaywall(false)
          }}
        />
      )}
    </div>
  )
}
