import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import {
  forgetSignInEmail,
  readRememberedSignInEmail,
  sendMagicLink,
  signInWithReviewerPassword,
  verifyEmailOtp,
} from '../lib/auth'
import {
  consumeAuthRedirectError,
  consumeFreshAuthRedirectError,
} from '../lib/authRedirectError'
import { isCompleteEmailOtp, normalizeEmailOtp } from '../lib/emailOtp'
import {
  PLAY_REVIEWER_DENIED,
  looksLikeReviewerPassword,
  showPlayReviewerPassword,
} from '../lib/playReviewer'
import {
  SIGN_IN_EMAIL_HINT,
  SIGN_IN_EMAIL_REQUIRED,
  emailAtSubmit,
  signInEmailToSend,
} from '../lib/signInEmail'
import { looksLikeSignInEmail, showSignInCodeField } from '../lib/signInCodeField'
import { START_CAMPAIGN_HEADING, showStartCampaign } from '../lib/startRoute'
import { LegalLinks } from './LegalLinks'

export function SignIn() {
  const emailForm = useRef<HTMLFormElement>(null)
  const [email, setEmail] = useState(readRememberedSignInEmail)
  const [password, setPassword] = useState('')
  const [passwordOpen, setPasswordOpen] = useState(false)
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(consumeAuthRedirectError)
  const [fromRedirect, setFromRedirect] = useState(() => Boolean(consumeAuthRedirectError()))
  const [sent, setSent] = useState(false)
  const [sending, setSending] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [reviewerConfigured, setReviewerConfigured] = useState(false)
  const showPassword = showPlayReviewerPassword(reviewerConfigured)
  const campaign = showStartCampaign(window.location.pathname, window.location.search)
  // On a tagged /start page the password path stays collapsed so the email
  // button does not move when the reviewer flag arrives.
  const passwordVisible = showPassword && (!campaign || passwordOpen)
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

  useEffect(() => {
    let cancelled = false
    void api.auth.playReviewerConfigured().then((configured) => {
      if (!cancelled) setReviewerConfigured(configured)
    })
    return () => {
      cancelled = true
    }
  }, [])

  function submittedEmail(): string {
    const field = emailForm.current?.elements.namedItem('email')
    const live = field instanceof HTMLInputElement ? field.value : null
    return emailAtSubmit(live, email)
  }

  async function requestEmail(address: string) {
    // Keep whatever they submitted. An error must not wipe the field.
    setEmail(address)
    let sendable: string
    try {
      sendable = signInEmailToSend(address)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : SIGN_IN_EMAIL_REQUIRED)
      return
    }
    setSending(true)
    setError(null)
    try {
      await sendMagicLink(sendable)
      setCode('')
      setSent(true)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not send the email.')
    } finally {
      setSending(false)
    }
  }

  async function submitPassword(address: string, secret: string) {
    setEmail(address)
    setPassword(secret)
    if (!looksLikeSignInEmail(address)) {
      setError(SIGN_IN_EMAIL_REQUIRED)
      return
    }
    if (!looksLikeReviewerPassword(secret)) {
      setError('Enter the password for this account.')
      return
    }
    setVerifying(true)
    setError(null)
    try {
      await signInWithReviewerPassword(address, secret)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : PLAY_REVIEWER_DENIED)
    } finally {
      setVerifying(false)
    }
  }

  function onEmailFormSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const address = emailAtSubmit(
      (event.currentTarget.elements.namedItem('email') as HTMLInputElement | null)?.value ?? null,
      email,
    )
    const secretField = event.currentTarget.elements.namedItem('password')
    const secret = secretField instanceof HTMLInputElement ? secretField.value : password
    if (passwordVisible && looksLikeReviewerPassword(secret)) {
      void submitPassword(address, secret)
      return
    }
    if (!sent) void requestEmail(address)
  }

  async function submitCode(event: React.FormEvent) {
    event.preventDefault()
    const address = submittedEmail()
    setEmail(address)
    const token = normalizeEmailOtp(code)
    if (!looksLikeSignInEmail(address)) {
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
      await verifyEmailOtp(address, token)
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
    setPassword('')
    setEmail('')
    setError(null)
    setFromRedirect(false)
  }

  function passwordFields(primary: boolean) {
    return (
      <>
        <label htmlFor="password" className="block text-sm font-medium text-stone-700 dark:text-stone-300">
          Password
        </label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          onInput={(event) => setPassword(event.currentTarget.value)}
          className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-stone-900 outline-none focus:border-stone-900 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100 dark:focus:border-stone-400"
        />
        <button
          type="submit"
          disabled={verifying || !looksLikeReviewerPassword(password)}
          className={
            primary
              ? 'w-full rounded-lg bg-stone-900 px-3 py-2 font-medium text-white disabled:opacity-50 dark:bg-stone-100 dark:text-stone-900'
              : 'w-full rounded-lg border border-stone-300 px-3 py-2 font-medium text-stone-800 disabled:opacity-50 dark:border-stone-700 dark:text-stone-100'
          }
        >
          {verifying ? 'Signing in…' : 'Sign in'}
        </button>
      </>
    )
  }

  return (
    <div className="flex min-h-screen items-start justify-center bg-stone-50 px-4 py-16 dark:bg-stone-950">
      <div className="w-full max-w-sm">
        {campaign ? (
          <>
            <p className="text-sm font-medium tracking-tight text-stone-500 dark:text-stone-400">
              BadgeDay
            </p>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-stone-900 dark:text-stone-50">
              {START_CAMPAIGN_HEADING}
            </h1>
          </>
        ) : (
          <>
            <h1 className="text-2xl font-semibold tracking-tight text-stone-900 dark:text-stone-50">
              BadgeDay
            </h1>
            <p className="mt-1 text-sm text-stone-600 dark:text-stone-400">
              Practice the oral board out loud, or study questions from your department's SOPs.
            </p>
          </>
        )}

        <div className="mt-8 space-y-4">
          {/* Reserved whether or not a message is showing, so the buttons stay put. */}
          <div className="min-h-24" aria-live="polite">
            {error && (
              <p
                role="alert"
                className="rounded-lg bg-red-50 p-4 text-sm text-red-900 dark:bg-red-950 dark:text-red-200"
              >
                {error}
              </p>
            )}

            {sent && !error && (
              <p className="rounded-lg bg-emerald-50 p-4 text-sm text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100">
                Check <span className="font-medium">{email}</span>. {SIGN_IN_EMAIL_HINT}
              </p>
            )}
          </div>

          {(!sent || showPassword) && (
            <form ref={emailForm} onSubmit={onEmailFormSubmit} className="space-y-3">
              <label htmlFor="email" className="block text-sm font-medium text-stone-700 dark:text-stone-300">
                Email
              </label>
              <input
                id="email"
                name="email"
                type="email"
                required
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                onInput={(event) => setEmail(event.currentTarget.value)}
                placeholder="you@department.gov"
                className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-stone-900 outline-none focus:border-stone-900 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100 dark:focus:border-stone-400"
              />
              {passwordVisible && !campaign && passwordFields(true)}
              {!sent && (
                <button
                  type={passwordVisible ? 'button' : 'submit'}
                  disabled={sending}
                  onClick={
                    passwordVisible
                      ? () => {
                          void requestEmail(submittedEmail())
                        }
                      : undefined
                  }
                  className={
                    passwordVisible && !campaign
                      ? 'w-full rounded-lg border border-stone-300 px-3 py-2 font-medium text-stone-800 disabled:opacity-50 dark:border-stone-700 dark:text-stone-100'
                      : 'w-full rounded-lg bg-stone-900 px-3 py-2 font-medium text-white disabled:opacity-50 dark:bg-stone-100 dark:text-stone-900'
                  }
                >
                  {sending ? 'Sending…' : 'Email me a sign-in link'}
                </button>
              )}
              {!sent && (
                <p className="text-xs text-stone-500 dark:text-stone-500">
                  {passwordVisible
                    ? `If you have a password, sign in with it. Otherwise email yourself a sign-in link. ${SIGN_IN_EMAIL_HINT}`
                    : `No password to forget. ${SIGN_IN_EMAIL_HINT}`}
                </p>
              )}
              {campaign && showPassword && !passwordOpen && (
                <button
                  type="button"
                  onClick={() => setPasswordOpen(true)}
                  className="text-sm text-stone-600 hover:underline dark:text-stone-400"
                >
                  Have a password? Sign in
                </button>
              )}
              {passwordVisible && campaign && passwordFields(false)}
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
                    onClick={() => void requestEmail(submittedEmail())}
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
