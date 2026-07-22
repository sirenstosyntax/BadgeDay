import { useState } from 'react'
import { api } from './lib/api'
import { signOut, useSession } from './lib/auth'
import { Documents } from './ui/Documents'
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
  | { name: 'quiz'; sessionId: string }
  | { name: 'review'; sessionId: string }

export default function App() {
  const { session, loading } = useSession()
  const [view, setView] = useState<View>({ name: 'documents' })
  const [starting, setStarting] = useState(false)

  // Blank rather than a spinner: restoring a stored session takes a few milliseconds, and
  // a spinner that flashes for one frame reads as jank. What must not happen here is
  // rendering SignIn, which would tell a returning candidate they are logged out.
  if (loading) {
    return <div className="min-h-screen bg-stone-50 dark:bg-stone-950" />
  }

  if (!session) {
    return <SignIn />
  }

  async function practise(documentId: string | null) {
    setStarting(true)
    try {
      const started = await api.practice.start(documentId)
      setView({ name: 'quiz', sessionId: started.id })
    } finally {
      setStarting(false)
    }
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
            <span className="hidden text-stone-500 sm:inline dark:text-stone-400">
              {session.user.email}
            </span>
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
        ) : (
          <Documents onPractise={(id) => void practise(id)} />
        )}
      </main>
    </div>
  )
}
