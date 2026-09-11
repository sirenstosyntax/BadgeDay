/** Supabase email OTPs are 6 or 8 digits depending on the project; ignore spaces. */
export function normalizeEmailOtp(raw: string): string {
  return raw.replace(/\D/g, '').slice(0, 8)
}

export function isCompleteEmailOtp(token: string): boolean {
  return /^\d{6}$|^\d{8}$/.test(token)
}

/**
 * Current supabase-js documents `email` for codes from `signInWithOtp`.
 * `magiclink` and `signup` are deprecated aliases for the same verify path.
 */
export const EMAIL_OTP_VERIFY_TYPE = 'email' as const

export function emailOtpVerifyParams(email: string, token: string) {
  return {
    email,
    token: normalizeEmailOtp(token),
    type: EMAIL_OTP_VERIFY_TYPE,
  }
}
