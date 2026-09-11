/** AC9: verification is for a specific email, not an empty burned-link landing. */
export function looksLikeSignInEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+$/.test(email.trim())
}

/** When to show the emailed-OTP field on SignIn. */
export function showSignInCodeField({
  sent,
  email,
  fromRedirect,
}: {
  sent: boolean
  email: string
  fromRedirect: boolean
}): boolean {
  return sent || email.includes('@') || fromRedirect
}
