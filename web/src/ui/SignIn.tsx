import { useEffect, useState } from 'react'
import {
  forgetSignInEmail,
  readRememberedSignInEmail,
  sendMagicLink,
  verifyEmailOtp,
} from '../lib/auth'
import {
  consumeAuthRedirectError,
  consumeFreshAuthRedirectError,
} from '../lib/authRedirectError'
import { isCompleteEmailOtp, normalizeEmailOtp } from '../lib/emailOtp'
import { looksLikeSignInEmail, showSignInCodeField } from '../lib/signInCodeField'
import { LegalLinks } from './LegalLinks'

export function SignIn() {
  const [email, setEmail] = useState(readRememberedSignInEmail)
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(consumeAuthRedirectError)
  const [fromRedirect, setFromRedirect] = useState(() => Boolean(consumeAuthRedirectError()))
  const [sent, setSent] = useState(
    () => Boolean(readRememberedSignInEmail() && consumeAuthRedirectError()),
  )
  const [sending, setSending] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const showCode = showSignInCodeField({ sent, email, fromRedirect })

  useEffect(() => {
    function syncRedirectError() {
      const message = consumeFreshAuthRedirectError()
      if (!message) return
      setError(message)
      setFromRedirect(true)
    }
    window.addEventListener('hashchange', syncRedirectError)
    return () => window.removeEventListener('hashchange', syncRedirectError)
  }, [])

  async function requestEmail() {
    setSending(true)
    setError(null)
    try {
      await sendMagicLink(email)
      setCode('')
      setSent(true)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not send the email.')
    } finally {
      setSending(false)
    }
  }

  async function submitCode(event: React.FormEvent) {
    event.preventDefault()
    const token = normalizeEmailOtp(code)
    if (!looksLikeSignInEmail(email)) {
      setError('Enter the email the code was sent to.')
      return
    }
    if (!isCompleteEmailOtp(token)) {
      setError('Enter the 6- to 8-digit code from the email.')
      return
    }
    setVerifying(true)
    setError(null)
    try {
      await verifyEmailOtp(email, token)
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'That code did not work. Request a new email and type the latest code.',
      )
    } finally {
      setVerifying(false)
    }
  }

  function useDifferentEmail() {
    forgetSignInEmail()
    setSent(false)
    setCode('')
    setEmail('')
    setError(null)
    setFromRedirect(false)
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

          {sent && (
            <p className="rounded-lg bg-emerald-50 p-4 text-sm text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100">
              Check <span className="font-medium">{email}</span> for a sign-in email. If
              the button in that email does nothing, type the code from the email here.
            </p>
          )}

          {!sent && (
            <form
              onSubmit={(event) => {
                event.preventDefault()
                void requestEmail()
              }}
              className="space-y-3"
            >
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
                No password to forget. If the button in the email does nothing, type
                the code from that email below.
              </p>
            </form>
          )}

          {showCode && (
            <>
              <form onSubmit={submitCode} className="space-y-3">
                <label htmlFor="otp" className="block text-sm font-medium text-stone-700 dark:text-stone-300">
                  Code from the email
                </label>
                <input
                  id="otp"
                  name="one-time-code"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  autoFocus={sent}
                  required
                  value={code}
                  onChange={(event) => setCode(normalizeEmailOtp(event.target.value))}
                  placeholder="6 to 8 digits"
                  className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 tracking-widest text-stone-900 outline-none focus:border-stone-900 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100 dark:focus:border-stone-400"
                />
                <button
                  type="submit"
                  disabled={verifying || !looksLikeSignInEmail(email) || !isCompleteEmailOtp(code)}
                  className="w-full rounded-lg bg-stone-900 px-3 py-2 font-medium text-white disabled:opacity-50 dark:bg-stone-100 dark:text-stone-900"
                >
                  {verifying ? 'Signing in…' : 'Sign in with code'}
                </button>
              </form>
              {sent && (
                <div className="flex flex-col gap-2 text-sm">
                  <button
                    type="button"
                    disabled={sending}
                    onClick={() => void requestEmail()}
                    className="text-stone-600 hover:underline dark:text-stone-400"
                  >
                    {sending ? 'Sending…' : 'Email a new code'}
                  </button>
                  <button
                    type="button"
                    onClick={useDifferentEmail}
                    className="text-stone-600 hover:underline dark:text-stone-400"
                  >
                    Use a different email
                  </button>
                </div>
              )}
            </>
          )}
        </div>

        <LegalLinks className="mt-10" />
      </div>
    </div>
  )
}
