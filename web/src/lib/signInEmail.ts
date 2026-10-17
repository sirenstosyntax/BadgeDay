import { looksLikeSignInEmail } from './signInCodeField'

/**
 * Honest until the hosted Confirm signup and Magic Link templates include
 * {{ .Token }}. GoTrue's default otp_length is 6; the field still accepts 6–8.
 */
export const SIGN_IN_EMAIL_HINT =
  'Click the link in the email, or type the 6-digit code if your email shows one.'

export const SIGN_IN_EMAIL_REQUIRED = 'Enter your email address.'

/**
 * Address to submit. A mounted input wins, including when it is blank, so a
 * stale React value is not sent after the field was cleared or never notified
 * of an autofill. `null` means the input is not in the document.
 */
export function emailAtSubmit(inputValue: string | null, stateValue: string): string {
  const raw = inputValue === null ? stateValue : inputValue
  return raw.trim()
}

/** Refuse an empty or non-email before signInWithOtp. */
export function signInEmailToSend(email: string): string {
  const trimmed = email.trim()
  if (!looksLikeSignInEmail(trimmed)) {
    throw new Error(SIGN_IN_EMAIL_REQUIRED)
  }
  return trimmed
}
