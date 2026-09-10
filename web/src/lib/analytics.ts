/**
 * Product analytics, when a tracker is present.
 *
 * Nothing in package.json ships an SDK. The milestone screen must still
 * render if `window.analytics` is missing or throws.
 */

type Tracker = {
  track: (event: string, props?: Record<string, unknown>) => void
}

function tracker(): Tracker | null {
  const candidate = (globalThis as { analytics?: Tracker }).analytics
  if (candidate && typeof candidate.track === 'function') return candidate
  return null
}

export function track(event: string, props?: Record<string, unknown>): void {
  try {
    tracker()?.track(event, props)
  } catch {
    // The screen is the product. A tracker failure is not.
  }
}
