import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { detectIosCapacitorShell } from './platform'
import { selectPaywallTill } from './paywallTill'

describe('detectIosCapacitorShell', () => {
  it('is false in an ordinary browser (no Capacitor)', () => {
    assert.equal(detectIosCapacitorShell({}), false)
  })

  it('is false when Capacitor is present but not native (web plugin stubs)', () => {
    assert.equal(
      detectIosCapacitorShell({
        Capacitor: { isNativePlatform: () => false, getPlatform: () => 'web' },
      }),
      false,
    )
  })

  it('is false on a native Android Capacitor host (not this shell)', () => {
    assert.equal(
      detectIosCapacitorShell({
        Capacitor: { isNativePlatform: () => true, getPlatform: () => 'android' },
      }),
      false,
    )
  })

  it('is true only inside the BadgeDay iOS Capacitor shell', () => {
    assert.equal(
      detectIosCapacitorShell({
        Capacitor: { isNativePlatform: () => true, getPlatform: () => 'ios' },
      }),
      true,
    )
  })
})

describe('selectPaywallTill', () => {
  it('uses the App Store till inside the iOS shell when StoreKit recognises ids', () => {
    assert.equal(
      selectPaywallTill({
        iosShell: true,
        playAvailable: true,
        storeSkus: ['ops.filled.monthly'],
        storeRecognised: 1,
        playSkus: ['play.monthly'],
        playRecognised: 1,
      }),
      'appstore',
    )
  })

  it('does not fall back to Stripe or Play when App Store ids are blank', () => {
    assert.equal(
      selectPaywallTill({
        iosShell: true,
        playAvailable: false,
        storeSkus: [],
        storeRecognised: 0,
        playSkus: [],
        playRecognised: 0,
      }),
      'appstore-unlisted',
    )
  })

  it('treats unrecognised StoreKit ids as the unlisted till', () => {
    assert.equal(
      selectPaywallTill({
        iosShell: true,
        playAvailable: false,
        storeSkus: ['ops.filled.monthly'],
        storeRecognised: 0,
        playSkus: [],
        playRecognised: 0,
      }),
      'appstore-unlisted',
    )
  })

  it('keeps Stripe in a browser tab', () => {
    assert.equal(
      selectPaywallTill({
        iosShell: false,
        playAvailable: false,
        storeSkus: ['ops.filled.monthly'],
        storeRecognised: 1,
        playSkus: [],
        playRecognised: 0,
      }),
      'stripe',
    )
  })

  it('keeps Play in the TWA when Digital Goods recognises the SKU', () => {
    assert.equal(
      selectPaywallTill({
        iosShell: false,
        playAvailable: true,
        storeSkus: [],
        storeRecognised: 0,
        playSkus: ['play.monthly'],
        playRecognised: 1,
      }),
      'play',
    )
  })
})
