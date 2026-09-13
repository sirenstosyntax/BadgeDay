/**
 * Device connectivity. Recruit, upload, generation, and billing stay online-only.
 * Promote can drill a cached session with this off.
 */

export function isOnline(host: { navigator?: { onLine?: boolean } } = globalThis): boolean {
  return host.navigator?.onLine !== false
}
