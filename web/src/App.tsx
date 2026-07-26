import { useEffect, useState } from 'react'
import { ApiError, api } from './lib/api'
import { useAccount } from './lib/account'
import { signOut, useSession } from './lib/auth'
import { Account } from './ui/Account'
import { Documents } from './ui/Documents'
import { LegalLinks } from './ui/LegalLinks'
import { Paywall } from './ui/Paywall'
import { Quiz } from './ui/Quiz'
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
  | { name: 'documents' }
  | { name: 'saved' }
  | { name: 'account' }
  | { name: 'quiz'; sessionId: string }
  | { name: 'review'; sessionId: string }

export default function App() {
  const { session, loading } = useSession()
  const { account, entitled, refreshAccount } = useAccount(!!session)
  const [view, setView] = useState<View>({ name: 'documents' })
  const [starting, setStarting] = useState(false)
  const [showPaywall, setShowPaywall] = useState(false)
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

  async function manageBilling() {
    setNotice(null)
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
            onClick={() => setView({ name: 'documents' })}
            className="font-semibold tracking-tight"
          >
            BadgeDay
          </button>
          <div className="flex items-center gap-3 text-sm">
            {view.name !== 'saved' && (
              <button
                onClick={() => setView({ name: 'saved' })}
                className="text-stone-600 hover:underline dark:text-stone-400"
              >
                Saved
              </button>
            )}
            {entitled ? (
              <button
                onClick={() => void manageBilling()}
                className="text-stone-600 hover:underline dark:text-stone-400"
              >
                Billing
              </button>
            ) : (
              <button
                onClick={() => setShowPaywall(true)}
                className="rounded-md bg-stone-900 px-2 py-1 font-medium text-white dark:bg-stone-100 dark:text-stone-900"
              >
                Subscribe
              </button>
            )}
            <button
              onClick={() => setView({ name: 'account' })}
              className="hidden text-stone-500 hover:underline sm:inline dark:text-stone-400"
            >
              {session.user.email}
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
          <Saved onDone={() => setView({ name: 'documents' })} />
        ) : view.name === 'account' ? (
          <Account
            account={account}
            onManageBilling={() => void manageBilling()}
            onSubscribe={() => setShowPaywall(true)}
            onDeleted={() => void afterDeleted()}
            onDone={() => setView({ name: 'documents' })}
          />
        ) : (
          <Documents
            entitled={entitled}
            onNeedsAccess={needsAccess}
            onPractise={(id) => void practise(id)}
          />
        )}
      </main>

      <footer className="mx-auto max-w-3xl px-4 pb-10">
        <LegalLinks />
      </footer>

      {showPaywall && <Paywall onClose={() => setShowPaywall(false)} />}
    </div>
  )
}
