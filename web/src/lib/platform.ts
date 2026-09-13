/**
 * Where this page is running. Native entry points (Files/iCloud, camera, offline
 * cache, local notifications, StoreKit) exist only inside the BadgeDay iOS
 * Capacitor shell. Mobile Safari and the Play TWA must keep today's Stripe /
 * Play tills and must not show broken native buttons.
 *
 * Capacitor injects `window.Capacitor` into the WKWebView. The web bundle does
 * not import `@capacitor/core` — a remote `server.url` app talks to the bridge
 * that the shell already injected.
 */

export type CapacitorBridge = {
  isNativePlatform?: () => boolean
  getPlatform?: () => string
  Plugins?: Record<string, Record<string, (...args: never[]) => Promise<unknown>>>
}

export type CapacitorHost = {
  Capacitor?: CapacitorBridge
}

export function currentHost(): CapacitorHost {
  return window as CapacitorHost
}

export function detectIosCapacitorShell(host: CapacitorHost = currentHost()): boolean {
  const cap = host.Capacitor
  if (!cap || typeof cap.isNativePlatform !== 'function') return false
  if (!cap.isNativePlatform()) return false
  return cap.getPlatform?.() === 'ios'
}

export function isIosCapacitorShell(): boolean {
  return detectIosCapacitorShell()
}
