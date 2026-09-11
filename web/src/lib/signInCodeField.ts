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
