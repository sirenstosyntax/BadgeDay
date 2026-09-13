/** Play Console reviewer password path. Off until the API reports configured. */

export type PlayReviewerStatus = {
  configured: boolean
}

export type PlayReviewerSession = {
  access_token: string
  refresh_token: string
  expires_in: number
  token_type: string
}

export function playReviewerConfigured(body: unknown): boolean {
  if (typeof body !== 'object' || body === null) return false
  return (body as PlayReviewerStatus).configured === true
}

/** Show the password field only when the env-gated path is wired. */
export function showPlayReviewerPassword(configured: boolean): boolean {
  return configured
}

export function playReviewerSignInBody(email: string, password: string) {
  return { email: email.trim(), password }
}

export function looksLikeReviewerPassword(password: string): boolean {
  return password.length > 0
}

export const PLAY_REVIEWER_DENIED =
  'That email and password did not match. If you do not have a password, email yourself a sign-in link.'
