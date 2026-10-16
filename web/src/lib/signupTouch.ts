import { validSignupSrc } from './startRoute'

/** First-touch attribution. Survives the magic-link return in this browser. */
export const SIGNUP_TOUCH_KEY = 'badgeday.signup-touch'

const OWN_HOSTS = new Set(['badgeday.com', 'app.badgeday.com'])

export type SignupTouch = {
  referrer_domain: string | null
  utm_source: string | null
  utm_medium: string | null
  utm_campaign: string | null
}

type KeyStore = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

function hasAny(touch: SignupTouch): boolean {
  return (
    touch.referrer_domain !== null ||
    touch.utm_source !== null ||
    touch.utm_medium !== null ||
    touch.utm_campaign !== null
  )
}

function isIpAddress(host: string): boolean {
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(host)) {
    return host.split('.').every((part) => Number(part) <= 255)
  }
  return host.includes(':')
}

/** Hostname only. Path, query, our own hosts, empty referrers, and IPs are dropped. */
export function referrerDomain(referrer: string): string | null {
  const text = referrer.trim()
  if (!text) return null
  let url: URL
  try {
    url = new URL(text)
  } catch {
    return null
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return null
  const host = url.hostname.toLowerCase().replace(/\.$/, '')
  if (!host || OWN_HOSTS.has(host) || isIpAddress(host)) return null
  return validSignupSrc(host)
}

function utmFrom(search: string, name: string): string | null {
  return validSignupSrc(new URLSearchParams(search).get(name))
}

export function touchFromLanding(referrer: string, search: string): SignupTouch | null {
  const touch: SignupTouch = {
    referrer_domain: referrerDomain(referrer),
    utm_source: utmFrom(search, 'utm_source'),
    utm_medium: utmFrom(search, 'utm_medium'),
    utm_campaign: utmFrom(search, 'utm_campaign'),
  }
  return hasAny(touch) ? touch : null
}

function parseStored(raw: string): SignupTouch | null {
  try {
    const body = JSON.parse(raw) as Partial<SignupTouch>
    if (typeof body !== 'object' || body === null) return null
    const touch: SignupTouch = {
      referrer_domain:
        typeof body.referrer_domain === 'string'
          ? referrerDomain(`https://${body.referrer_domain}`)
          : null,
      utm_source: typeof body.utm_source === 'string' ? validSignupSrc(body.utm_source) : null,
      utm_medium: typeof body.utm_medium === 'string' ? validSignupSrc(body.utm_medium) : null,
      utm_campaign: typeof body.utm_campaign === 'string' ? validSignupSrc(body.utm_campaign) : null,
    }
    return hasAny(touch) ? touch : null
  } catch {
    return null
  }
}

/** The stored touch, re-checked. Null when nothing valid is stored. */
export function readSignupTouch(store: KeyStore): SignupTouch | null {
  const raw = store.getItem(SIGNUP_TOUCH_KEY)
  if (raw == null) return null
  return parseStored(raw)
}

/**
 * Remember the first landing that has a referrer domain or a utm tag.
 * A later landing does not replace it. An empty landing writes nothing,
 * so a real source on the next page can still be first.
 */
export function captureSignupTouch(
  input: { referrer: string; search: string },
  store: KeyStore,
): SignupTouch | null {
  if (store.getItem(SIGNUP_TOUCH_KEY) != null) return readSignupTouch(store)
  const touch = touchFromLanding(input.referrer, input.search)
  if (!touch) return null
  store.setItem(SIGNUP_TOUCH_KEY, JSON.stringify(touch))
  return touch
}

export function clearSignupTouch(store: KeyStore): void {
  store.removeItem(SIGNUP_TOUCH_KEY)
}

/** Body for POST /me/signup-src. Only the tag and the four columns. */
export function signupAttributionBody(
  src: string | null,
  touch: SignupTouch | null,
): Record<string, string> {
  const body: Record<string, string> = {}
  if (src) body.src = src
  if (touch?.referrer_domain) body.referrer_domain = touch.referrer_domain
  if (touch?.utm_source) body.utm_source = touch.utm_source
  if (touch?.utm_medium) body.utm_medium = touch.utm_medium
  if (touch?.utm_campaign) body.utm_campaign = touch.utm_campaign
  return body
}
