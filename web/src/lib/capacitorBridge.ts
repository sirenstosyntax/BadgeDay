/**
 * Thin accessors for Capacitor plugins the iOS shell registers. The web app
 * never ships a second product surface — these are bridges only. On Safari or
 * the Play TWA the plugins are absent and callers treat that as "not available".
 */
import { currentHost, type CapacitorHost } from './platform'

export class PluginUnavailableError extends Error {
  constructor(plugin: string) {
    super(`${plugin} is not available in this browser.`)
    this.name = 'PluginUnavailableError'
  }
}

export function pluginMethod(
  name: string,
  method: string,
  host: CapacitorHost = currentHost(),
): ((payload?: unknown) => Promise<unknown>) | null {
  const fn = host.Capacitor?.Plugins?.[name]?.[method]
  if (typeof fn !== 'function') return null
  return (payload?: unknown) => fn(payload as never)
}

export async function callPlugin<T>(
  name: string,
  method: string,
  payload?: unknown,
  host: CapacitorHost = currentHost(),
): Promise<T> {
  const fn = pluginMethod(name, method, host)
  if (!fn) throw new PluginUnavailableError(name)
  return (await fn(payload)) as T
}
