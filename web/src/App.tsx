import { useEffect, useState } from 'react'
import { ApiError, api } from './lib/api'
import { useAccount } from './lib/account'
import { signOut, useSession } from './lib/auth'
import { isOnline } from './lib/connectivity'
import { clearDeviceLocalUserData } from './lib/deviceLocal'
import {
  anyModuleHasManageableBilling,
  headerManageModule,
  headerSubscribeModule,
  moduleHasManageableBilling,
  moduleManagedBy,
  shouldOfferCheckout,
} from './lib/moduleAccess'
import {
  markNotifyPrompted,
  readExamDate,
  refreshLocalNotifications,
  requestNotificationPermission,
  wasNotifyPrompted,
  writeExamDate,
} from './lib/notifications'
import {
  cacheMatchesScope,
  emptyCacheMessage,
  OFFLINE_SCHEMA_VERSION,
  pendingSyncBodies,
  readOfflineCache,
  recordLastPractice,
  writeOfflineCache,
} from './lib/offlinePractice'
import { detectIosCapacitorShell } from './lib/platform'
import { browserPlayBilling } from './lib/playBilling'
import { PLAY_SUBSCRIPTIONS_URL } from './lib/recruitMilestone'
import { APPLE_SUBSCRIPTIONS_URL, browserStoreKitBilling } from './lib/storeKitBilling'
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
  | { name: 'quiz'; sessionId: string; offline?: boolean }
  | { name: 'review'; sessionId: string; offline?: boolean }
  | { name: 'recruit' }
  | { name: 'offline-empty' }

export default function App() {
  const { session, loading } = useSession()
  const { account, entitled, refreshAccount } = useAccount(!!session)
  const [view, setView] = useState<View>({ name: 'choose' })
  const [starting, setStarting] = useState(false)
  const [showPaywall, setShowPaywall] = useState(false)
  const [paywallModule, setPaywallModule] = useState<PaywallModule>('promote')
  const [notice, setNotice] = useState<string | null>(null)
  const [online, setOnline] = useState(() => isOnline())
  const [iosShell] = useState(() => detectIosCapacitorShell())
  const [offlineReady, setOfflineReady] = useState(false)
  const [cachingOffline, setCachingOffline] = useState(false)
  const [examDate, setExamDate] = useState<string | null>(() => readExamDate(localStorage))
  const userId = account?.id ?? session?.user?.id ?? null

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

  useEffect(() => {
    const on = () => setOnline(true)
    const off = () => setOnline(false)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
    }
  }, [])

  useEffect(() => {
    setOfflineReady(Boolean(userId && readOfflineCache(localStorage, userId)))
  }, [userId, view])

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

  useEffect(() => {
    if (!session || !iosShell) return
    let cancelled = false
    const purchases = browserStoreKitBilling(api.billing.reportAppStorePurchase)
    void purchases.restore().then((ids) => {
      if (!cancelled && ids.length > 0) void refreshAccount()
    })
    return () => {
      cancelled = true
    }
  }, [session, refreshAccount, iosShell])

  useEffect(() => {
    if (!session || !iosShell || !userId || !online) return
    const cache = readOfflineCache(localStorage, userId)
    if (!cache || cache.answers_local.length === 0) return
    let cancelled = false
    void (async () => {
      const pending = pendingSyncBodies(cache)
      const kept = [...cache.answers_local]
      for (const body of pending) {
        try {
          await api.practice.answer(cache.session_id, body)
          const index = kept.findIndex((row) => row.question_id === body.question_id)
          if (index >= 0) kept.splice(index, 1)
        } catch (caught) {
          if (caught instanceof ApiError && caught.status === 404) {
            if (!cancelled) {
              setNotice(
                'A saved answer could not be submitted — that question is no longer on the server. Re-cache a session while online.',
              )
            }
            const index = kept.findIndex((row) => row.question_id === body.question_id)
            if (index >= 0) kept.splice(index, 1)
            continue
          }
          if (!cancelled) {
            setNotice(
              caught instanceof Error
                ? caught.message
                : 'Answers on this device could not be submitted yet.',
            )
          }
          break
        }
      }
      if (cancelled) return
      writeOfflineCache(localStorage, { ...cache, answers_local: kept })
    })()
    return () => {
      cancelled = true
    }
  }, [session, iosShell, userId, online])

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

  async function afterPracticed() {
    recordLastPractice(localStorage)
    if (!iosShell) return
    if (!wasNotifyPrompted(localStorage)) {
      markNotifyPrompted(localStorage)
      await requestNotificationPermission()
    }
    await refreshLocalNotifications(localStorage)
  }

  function openCachedSession() {
    const cache = userId ? readOfflineCache(localStorage, userId) : null
    if (!cache) {
      setView({ name: 'offline-empty' })
      return
    }
    setView({ name: 'quiz', sessionId: cache.session_id, offline: !online })
  }

  async function cacheOffline(documentId: string | null) {
    if (!entitled) {
      needsAccess()
      return
    }
    if (!online) {
      setNotice('Saving a session for offline needs a connection.')
      return
    }
    setCachingOffline(true)
    setNotice(null)
    try {
      const started = await api.practice.start(documentId)
      const pack = await api.practice.pack(started.id)
      if (!userId) throw new Error('Not signed in.')
      if (pack.questions.length === 0) {
        throw new Error('That session has no questions to cache yet.')
      }
      writeOfflineCache(localStorage, {
        schema_version: OFFLINE_SCHEMA_VERSION,
        user_id: userId,
        cached_at: new Date().toISOString(),
        session_id: pack.session_id,
        session_scope: documentId ? 'document' : 'whole_list',
        document_id: documentId,
        questions: pack.questions,
        answers_local: [],
      })
      setOfflineReady(true)
      setNotice('That session is saved on this device for offline practice.')
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 402) {
        needsAccess()
      } else {
        setNotice(caught instanceof Error ? caught.message : 'Could not save that session.')
      }
    } finally {
      setCachingOffline(false)
    }
  }

  async function practise(documentId: string | null) {
    if (!entitled) {
      needsAccess()
      return
    }
    if (!online) {
      const cache = userId ? readOfflineCache(localStorage, userId) : null
      if (cache && cacheMatchesScope(cache, documentId)) {
        setView({ name: 'quiz', sessionId: cache.session_id, offline: true })
        return
      }
      setView({ name: 'offline-empty' })
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
      if (iosShell) {
        void browserStoreKitBilling(api.billing.reportAppStorePurchase).openManage()
        return
      }
      window.location.href = APPLE_SUBSCRIPTIONS_URL
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
  async function leaveAccount() {
    clearDeviceLocalUserData()
    setOfflineReady(false)
    setExamDate(null)
    await signOut()
  }

  async function afterDeleted() {
    await leaveAccount()
  }

  async function changeExamDate(next: string | null) {
    writeExamDate(localStorage, next)
    setExamDate(next)
    if (!iosShell) return
    if (!wasNotifyPrompted(localStorage)) {
      markNotifyPrompted(localStorage)
      await requestNotificationPermission()
    }
    await refreshLocalNotifications(localStorage)
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
              onClick={() => void leaveAccount()}
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
        ) : view.name === 'offline-empty' ? (
          <div className="space-y-4">
            <p className="text-sm text-stone-600 dark:text-stone-400">{emptyCacheMessage()}</p>
            <button
              type="button"
              onClick={() => setView({ name: 'documents' })}
              className="text-sm text-stone-500 hover:underline dark:text-stone-400"
            >
              ← Back to documents
            </button>
          </div>
        ) : view.name === 'quiz' ? (
          <Quiz
            sessionId={view.sessionId}
            offline={Boolean(view.offline)}
            userId={userId ?? undefined}
            onPracticed={() => void afterPracticed()}
            onDone={() => setView({ name: 'documents' })}
            onReview={() =>
              setView({ name: 'review', sessionId: view.sessionId, offline: view.offline })
            }
          />
        ) : view.name === 'review' ? (
          <Review
            sessionId={view.sessionId}
            offline={Boolean(view.offline)}
            userId={userId ?? undefined}
            onDone={() => setView({ name: 'documents' })}
          />
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
            iosShell={iosShell}
            examDate={examDate}
            onExamDateChange={(next) => void changeExamDate(next)}
          />
        ) : view.name === 'recruit' ? (
          <Recruit
            onDone={() => setView({ name: 'choose' })}
            account={account}
            onOpenAccount={() => setView({ name: 'account' })}
            onNeedsAccess={needsRecruitAccess}
            onBoardStarted={() => void afterPracticed()}
          />
        ) : view.name === 'documents' ? (
          <Documents
            entitled={entitled}
            onNeedsAccess={needsAccess}
            onPractise={(id) => void practise(id)}
            iosShell={iosShell}
            online={online}
            hasOfflineCache={offlineReady}
            cachingOffline={cachingOffline}
            onCacheOffline={(id) => cacheOffline(id)}
            onOpenOffline={openCachedSession}
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
          appstoreProducts={account?.appstore_products}
          module={paywallModule}
          alreadyEntitled={!shouldOfferCheckout(account, paywallModule)}
          canManageBilling={moduleHasManageableBilling(account, paywallModule)}
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
