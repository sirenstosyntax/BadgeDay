import { useState } from 'react'
import { api } from './lib/api'
import { signOut, useSession } from './lib/auth'
import { Documents } from './ui/Documents'
import { Quiz } from './ui/Quiz'
import { SignIn } from './ui/SignIn'

export default function App() {
  const { session, loading } = useSession()
  const [sessionId, setSessionId] = useState<string | null>(null)
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
      setSessionId((await api.practice.start(documentId)).id)
    } finally {
      setStarting(false)
    }
  }

  return (
    <div className="min-h-screen bg-stone-50 text-stone-900 dark:bg-stone-950 dark:text-stone-100">
      <header className="border-b border-stone-200 dark:border-stone-800">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
          <span className="font-semibold tracking-tight">BadgeDay</span>
          <div className="flex items-center gap-3 text-sm">
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
        {sessionId ? (
          <Quiz sessionId={sessionId} onDone={() => setSessionId(null)} />
        ) : starting ? (
          <p className="text-sm text-stone-500">Starting…</p>
        ) : (
          <Documents onPractise={(id) => void practise(id)} />
        )}
      </main>
    </div>
  )
}
