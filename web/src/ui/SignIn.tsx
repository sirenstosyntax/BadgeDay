import { useState } from 'react'
import { sendMagicLink } from '../lib/auth'
import { consumeAuthRedirectError } from '../lib/authRedirectError'
import { LegalLinks } from './LegalLinks'

export function SignIn() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState<string | null>(consumeAuthRedirectError)
  const [sending, setSending] = useState(false)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setSending(true)
    setError(null)
    try {
      await sendMagicLink(email)
      setSent(true)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not send the link.')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-stone-50 px-4 dark:bg-stone-950">
      <div className="w-full max-w-sm">
        <h1 className="text-2xl font-semibold tracking-tight text-stone-900 dark:text-stone-50">
          BadgeDay
        </h1>
        <p className="mt-1 text-sm text-stone-600 dark:text-stone-400">
          Practice the oral board out loud, or study questions from your reading list.
        </p>

        <div className="mt-8 space-y-4">
          {error && (
            <p
              role="alert"
              className="rounded-lg bg-red-50 p-4 text-sm text-red-900 dark:bg-red-950 dark:text-red-200"
            >
              {error}
            </p>
          )}

          {sent ? (
            <p className="rounded-lg bg-emerald-50 p-4 text-sm text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100">
              Check <span className="font-medium">{email}</span> for a sign-in link. You can
              close this tab — the link opens a new one.
            </p>
          ) : (
            <form onSubmit={submit} className="space-y-3">
              <label htmlFor="email" className="block text-sm font-medium text-stone-700 dark:text-stone-300">
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@department.gov"
                className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-stone-900 outline-none focus:border-stone-900 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100 dark:focus:border-stone-400"
              />
              <button
                type="submit"
                disabled={sending}
                className="w-full rounded-lg bg-stone-900 px-3 py-2 font-medium text-white disabled:opacity-50 dark:bg-stone-100 dark:text-stone-900"
              >
                {sending ? 'Sending…' : 'Email me a sign-in link'}
              </button>
              <p className="text-xs text-stone-500 dark:text-stone-500">
                No password to forget. The link signs you in.
              </p>
            </form>
          )}
        </div>

        <LegalLinks className="mt-10" />
      </div>
    </div>
  )
}
