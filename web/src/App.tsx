import { signOut, useSession } from './lib/auth'
import { SignIn } from './ui/SignIn'

export default function App() {
  const { session, loading } = useSession()

  // Blank rather than a spinner: restoring a stored session takes a few milliseconds, and
  // a spinner that flashes for one frame reads as jank. What must not happen here is
  // rendering SignIn, which would tell a returning candidate they are logged out.
  if (loading) {
    return <div className="min-h-screen bg-stone-50 dark:bg-stone-950" />
  }

  if (!session) {
    return <SignIn />
  }

  return (
    <div className="min-h-screen bg-stone-50 text-stone-900 dark:bg-stone-950 dark:text-stone-100">
      <header className="border-b border-stone-200 dark:border-stone-800">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
          <span className="font-semibold tracking-tight">BadgeDay</span>
          <div className="flex items-center gap-3 text-sm">
            <span className="text-stone-500 dark:text-stone-400">{session.user.email}</span>
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
        <p className="text-sm text-stone-600 dark:text-stone-400">
          Signed in. Documents and practice come next.
        </p>
      </main>
    </div>
  )
}
