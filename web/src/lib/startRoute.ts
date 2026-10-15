/** /start and the test-date link. Decisions only — the screen reads these. */

export type ActivationKind = 'start' | 'test-date'
export type BoardEntry = 'board' | 'home'

export const SIGNUP_SRC_KEY = 'badgeday.signup-src'
export const PENDING_ENTRY_KEY = 'badgeday.pending-entry'

const SRC_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/

type KeyStore = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

export function normalizePath(pathname: string): string {
  if (!pathname) return '/'
  if (pathname.length > 1 && pathname.endsWith('/')) return pathname.slice(0, -1)
  return pathname
}

export function activationKindFromPath(pathname: string): ActivationKind | null {
  const path = normalizePath(pathname)
  if (path === '/start') return 'start'
  if (path === '/recruit/test-date') return 'test-date'
  return null
}

/** Path wins. A stored path covers the magic-link return to the site origin. */
export function activationEntry(pathname: string, pending: string | null): ActivationKind | null {
  return activationKindFromPath(pathname) ?? activationKindFromPath(pending ?? '')
}

export function pathFor(kind: ActivationKind): string {
  return kind === 'start' ? '/start' : '/recruit/test-date'
}

/** Unused free board opens on question 1. A used one opens Recruit home. */
export function startEntry(freeBoardOpen: boolean): BoardEntry {
  return freeBoardOpen ? 'board' : 'home'
}

export const START_CAMPAIGN_HEADING =
  'Practice a full oral board out loud. Your first board is free, no card.'

/** Signed-out /start with a valid ?src= tag. Other routes stay the plain sign-in. */
export function showStartCampaign(pathname: string, search: string): boolean {
  if (activationKindFromPath(pathname) !== 'start') return false
  return validSignupSrc(new URLSearchParams(search).get('src')) !== null
}

export function validSignupSrc(raw: string | null | undefined): string | null {
  if (raw == null) return null
  const text = raw.trim()
  if (!text || !SRC_RE.test(text)) return null
  return text
}

/**
 * Remember the tag on this /start visit. No tag clears a stale one so a
 * signup without ?src= stores nothing. The first tag on this visit wins.
 */
export function syncSignupSrc(search: string, store: KeyStore): void {
  const src = validSignupSrc(new URLSearchParams(search).get('src'))
  if (!src) {
    store.removeItem(SIGNUP_SRC_KEY)
    return
  }
  if (!store.getItem(SIGNUP_SRC_KEY)) store.setItem(SIGNUP_SRC_KEY, src)
}

export function readSignupSrc(store: KeyStore): string | null {
  return validSignupSrc(store.getItem(SIGNUP_SRC_KEY))
}

export function clearSignupSrc(store: KeyStore): void {
  store.removeItem(SIGNUP_SRC_KEY)
}

export function rememberPendingEntry(pathname: string, store: KeyStore): void {
  const kind = activationKindFromPath(pathname)
  if (!kind) return
  store.setItem(PENDING_ENTRY_KEY, pathFor(kind))
}

export function readPendingEntry(store: KeyStore): string | null {
  return store.getItem(PENDING_ENTRY_KEY)
}

export function clearPendingEntry(store: KeyStore): void {
  store.removeItem(PENDING_ENTRY_KEY)
}
