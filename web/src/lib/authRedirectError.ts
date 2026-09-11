/**
 * Supabase sends failed magic-link / confirm-email clicks back to the app as
 * `#error=…&error_code=otp_expired&error_description=…` (sometimes the same
 * keys on the query string). `detectSessionInUrl` exchanges tokens on success
 * and clears the hash; on failure it returns the error internally, leaves the
 * fragment in the address bar, and never notifies the app. Without reading
 * those params, SignIn remounts as a blank form and the click looks like a no-op.
 */

const EXPIRED_MESSAGE =
  'This sign-in link is invalid or has expired. Type the code from the email if the button did nothing, or request a new email.'

const GENERIC_MESSAGE =
  'Sign-in failed. Type the code from the email if the button did nothing, or request a new email.'

const RETRY_HINT =
  'Type the code from the email if the button did nothing, or request a new email.'

let consumed: string | null = null

function paramsFrom(hash: string, search: string): URLSearchParams {
  const fromHash = new URLSearchParams(hash.startsWith('#') ? hash.slice(1) : hash)
  const fromSearch = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  fromHash.forEach((value, key) => {
    if (!fromSearch.has(key)) fromSearch.set(key, value)
  })
  return fromSearch
}

export function readAuthRedirectError(hash: string, search = ''): string | null {
  const params = paramsFrom(hash, search)
  const error = params.get('error')
  const code = params.get('error_code')
  const description = params.get('error_description')?.trim() || null

  if (!error && !code && !description) return null

  if (code === 'otp_expired' || (description !== null && /invalid or has expired/i.test(description))) {
    return EXPIRED_MESSAGE
  }

  if (description) {
    const sentence = /[.!?]$/.test(description) ? description : `${description}.`
    return `${sentence} ${RETRY_HINT}`
  }

  return GENERIC_MESSAGE
}

function clearAuthRedirectParams() {
  const params = new URLSearchParams(window.location.search)
  params.delete('error')
  params.delete('error_code')
  params.delete('error_description')
  const search = params.toString()
  window.history.replaceState(null, '', window.location.pathname + (search ? `?${search}` : ''))
}

/**
 * Read a redirect error from the current URL, then strip it from the address
 * bar so a refresh does not keep showing a spent link. Remembered after the
 * hash is cleared because React Strict Mode remounts SignIn.
 */
export function consumeAuthRedirectError(): string | null {
  if (typeof window === 'undefined') return consumed

  const message = readAuthRedirectError(window.location.hash, window.location.search)
  if (!message) return consumed

  clearAuthRedirectParams()
  consumed = message
  return message
}

/**
 * Hashchange path: only the current URL. Never returns a previously consumed
 * message after the hash has been cleared.
 */
export function takeFreshAuthRedirectError(hash: string, search = ''): string | null {
  const message = readAuthRedirectError(hash, search)
  if (message) consumed = message
  return message
}

export function consumeFreshAuthRedirectError(): string | null {
  if (typeof window === 'undefined') return null
  const message = takeFreshAuthRedirectError(window.location.hash, window.location.search)
  if (message) clearAuthRedirectParams()
  return message
}

/** Drop a remembered redirect error so a later SignIn mount (sign-out) stays clean. */
export function clearAuthRedirectError() {
  consumed = null
}

export function resetAuthRedirectErrorForTests() {
  clearAuthRedirectError()
}
