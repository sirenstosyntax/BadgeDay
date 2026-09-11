import type { Session } from '@supabase/supabase-js'
import { useEffect, useState } from 'react'
import { normalizeEmailOtp } from './emailOtp'
import { supabase } from './supabase'

const SIGNIN_EMAIL_KEY = 'badgeday.signin-email'

export function rememberSignInEmail(email: string) {
  window.localStorage.setItem(SIGNIN_EMAIL_KEY, email)
}

export function readRememberedSignInEmail(): string {
  if (typeof window === 'undefined') return ''
  return window.localStorage.getItem(SIGNIN_EMAIL_KEY) ?? ''
}

export function forgetSignInEmail() {
  window.localStorage.removeItem(SIGNIN_EMAIL_KEY)
}

/**
 * The signed-in session, or null.
 *
 * `loading` exists to distinguish "not signed in" from "we have not looked yet". Without
 * it the app renders the sign-in screen for a moment on every reload before the stored
 * session is restored, which reads to a returning candidate as being logged out.
 */
export function useSession() {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setLoading(false)
    })

    const { data } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next)
      setLoading(false)
    })
    return () => data.subscription.unsubscribe()
  }, [])

  return { session, loading }
}

export async function sendMagicLink(email: string) {
  const { error } = await supabase.auth.signInWithOtp({
    email,
    options: { emailRedirectTo: window.location.origin },
  })
  if (error) throw error
  rememberSignInEmail(email)
}

/**
 * Complete passwordless sign-in with the OTP from the same email as the magic
 * link. `type: 'email'` is what current supabase-js documents for signInWithOtp;
 * `magiclink` / `signup` are deprecated aliases for the same verify path.
 */
export async function verifyEmailOtp(email: string, token: string) {
  const { error } = await supabase.auth.verifyOtp({
    email,
    token: normalizeEmailOtp(token),
    type: 'email',
  })
  if (error) throw error
  forgetSignInEmail()
}

export async function signOut() {
  forgetSignInEmail()
  await supabase.auth.signOut()
}
