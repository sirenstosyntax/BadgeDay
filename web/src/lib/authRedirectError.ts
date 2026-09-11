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

/**
 * Read a redirect error once per page load, then strip it from the address bar
 * so a refresh does not keep showing a spent link. Cached because React Strict
 * Mode remounts SignIn and the hash is already gone on the second mount.
 */
export function consumeAuthRedirectError(): string | null {
  if (consumed) return consumed
  if (typeof window === 'undefined') return null

  const message = readAuthRedirectError(window.location.hash, window.location.search)
  if (!message) return null

  const params = new URLSearchParams(window.location.search)
  params.delete('error')
  params.delete('error_code')
  params.delete('error_description')
  const search = params.toString()
  window.history.replaceState(null, '', window.location.pathname + (search ? `?${search}` : ''))
  consumed = message
  return message
}
