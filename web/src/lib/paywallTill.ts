/**
 * Which till the paywall uses. iOS Capacitor is App Store only (3.1.1) —
 * never Stripe redirect, never Play Digital Goods. Browser stays Stripe;
 * Play TWA stays Play.
 */

export type PaywallTill =
  | 'checking'
  | 'stripe'
  | 'play'
  | 'play-unlisted'
  | 'appstore'
  | 'appstore-unlisted'

export function selectPaywallTill(input: {
  iosShell: boolean
  playAvailable: boolean
  storeSkus: string[]
  storeRecognised: number
  playSkus: string[]
  playRecognised: number
}): Exclude<PaywallTill, 'checking'> {
  if (input.iosShell) {
    if (input.storeSkus.length === 0 || input.storeRecognised === 0) {
      return 'appstore-unlisted'
    }
    return 'appstore'
  }
  if (!input.playAvailable) return 'stripe'
  if (input.playSkus.length === 0 || input.playRecognised === 0) return 'play-unlisted'
  return 'play'
}
