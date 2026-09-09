/**
 * Digital Goods / Play Billing, as the TWA page talks to it.
 *
 * Mirror of DrillGround's purchase.js shape — detect the store, restore what
 * this Google account already owns, report the token to our backend so Play
 * can acknowledge it — without a product id of our own. Grant has not named
 * the BadgeDay paid offer. A SKU reaches this module only as an argument
 * from `/me` (env-configured), never as a literal here.
 *
 * An ordinary browser tab has no getDigitalGoodsService. The same deployed
 * page is then Stripe-on-the-web, which is the intended split.
 *
 * Never call consume(). Digital Goods v2.1 maps consume() to consumeAsync,
 * which revokes a non-consumable / subscription. Acknowledgement is the
 * server's job (`POST /billing/store/play/purchase`); older clients that
 * still expose service.acknowledge() are used only as a fallback.
 */

export const PLAY_BILLING_METHOD = 'https://play.google.com/billing'

export type PlayProductIds = {
  monthly?: string | null
  intensive_90day?: string | null
}

export type PlayItemDetails = {
  itemId: string
  title: string
  price?: { currency: string; value: string; label?: string }
}

export type DigitalGoodsService = {
  getDetails: (itemIds: string[]) => Promise<PlayItemDetails[]>
  listPurchases: () => Promise<Array<{ itemId: string; purchaseToken: string }>>
  acknowledge?: (token: string, purchaseType?: string) => Promise<void>
}

export type ReportPurchase = (
  purchaseToken: string,
  productId: string,
) => Promise<{ entitled: boolean }>

export function configuredSkus(products: PlayProductIds | null | undefined): string[] {
  return [products?.monthly, products?.intensive_90day].filter(
    (sku): sku is string => typeof sku === 'string' && sku.length > 0,
  )
}

export function createPlayBilling(deps: {
  getService: () => Promise<DigitalGoodsService | null>
  reportPurchase: ReportPurchase
  startPayment?: (
    sku: string,
  ) => Promise<{ purchaseToken: string; complete?: (status: string) => Promise<void> }>
  warn?: (message: string, detail?: unknown) => void
}) {
  const warn = deps.warn ?? (() => undefined)

  function service() {
    return Promise.resolve()
      .then(() => deps.getService())
      .catch(() => null)
  }

  function available() {
    return service().then((s) => !!s)
  }

  function detailsFor(skus: string[]) {
    if (skus.length === 0) return Promise.resolve([] as PlayItemDetails[])
    return service().then((s) => {
      if (!s || typeof s.getDetails !== 'function') return []
      return Promise.resolve()
        .then(() => s.getDetails(skus))
        .catch(() => [] as PlayItemDetails[])
    })
  }

  function acknowledgeFallback(s: DigitalGoodsService | null, token: string) {
    if (!s || typeof s.acknowledge !== 'function') {
      return Promise.resolve({ acknowledged: false as const, reason: 'no-acknowledge-api' })
    }
    return Promise.resolve()
      .then(() => s.acknowledge?.(token, 'onetime'))
      .then(() => ({ acknowledged: true as const, via: 'acknowledge' }))
      .catch((err: unknown) => ({
        acknowledged: false as const,
        reason: 'acknowledge-failed',
        error: String(err),
      }))
  }

  function report(s: DigitalGoodsService | null, token: string, productId: string) {
    return Promise.resolve()
      .then(() => deps.reportPurchase(token, productId))
      .then((res) => ({ ok: true as const, entitled: res.entitled }))
      .catch((err: unknown) => {
        warn('play purchase report failed', err)
        return acknowledgeFallback(s, token).then((ack) => ({
          ok: false as const,
          entitled: false,
          ack,
          error: String(err),
        }))
      })
  }

  function restore() {
    return service().then((s) => {
      if (!s || typeof s.listPurchases !== 'function') return [] as string[]
      return Promise.resolve()
        .then(() => s.listPurchases())
        .then((purchases) => {
          const reported: string[] = []
          const work = (purchases || []).map((p) => {
            if (!p?.purchaseToken || !p.itemId) return Promise.resolve()
            return report(s, p.purchaseToken, p.itemId).then((res) => {
              if (res.ok) reported.push(p.itemId)
            })
          })
          return Promise.all(work).then(() => reported)
        })
        .catch((err: unknown) => {
          warn('could not list existing Play purchases', err)
          return [] as string[]
        })
    })
  }

  function buy(sku: string) {
    if (!sku) return Promise.resolve({ ok: false as const, reason: 'no-sku' })
    if (typeof deps.startPayment !== 'function') {
      return Promise.resolve({ ok: false as const, reason: 'no-payment-support' })
    }
    return service().then((s) => {
      if (!s) return { ok: false as const, reason: 'no-store' }
      return Promise.resolve()
        .then(() => deps.startPayment?.(sku))
        .then((result) => {
          const token = result?.purchaseToken
          if (!token) return { ok: false as const, reason: 'no-purchase-token' }
          return report(s, token, sku).then((res) => {
            return Promise.resolve()
              .then(() => result.complete?.('success'))
              .catch(() => undefined)
              .then(() =>
                res.ok
                  ? { ok: true as const, sku, entitled: res.entitled }
                  : { ok: false as const, reason: 'report-failed' },
              )
          })
        })
        .catch((err: unknown) => ({
          ok: false as const,
          reason: 'payment-failed',
          error: String(err),
        }))
    })
  }

  return { available, detailsFor, restore, buy }
}

type DigitalGoodsWindow = Window & {
  getDigitalGoodsService?: (method: string) => Promise<DigitalGoodsService>
}

export function browserPlayBilling(reportPurchase: ReportPurchase) {
  const host = window as DigitalGoodsWindow
  return createPlayBilling({
    getService: () => {
      if (typeof host.getDigitalGoodsService !== 'function') return Promise.resolve(null)
      return host.getDigitalGoodsService(PLAY_BILLING_METHOD).catch(() => null)
    },
    reportPurchase,
    startPayment: (sku) => {
      if (typeof window.PaymentRequest !== 'function') {
        return Promise.reject(new Error('PaymentRequest unavailable'))
      }
      // The amount is a PaymentRequest-required placeholder. Play charges the
      // Console price, not this figure — it is never shown.
      const request = new window.PaymentRequest(
        [{ supportedMethods: PLAY_BILLING_METHOD, data: { sku } }],
        { total: { label: 'Total', amount: { currency: 'USD', value: '0' } } },
      )
      return request.show().then((response) => {
        const details = response.details as { purchaseToken?: string } | null
        return {
          purchaseToken: details?.purchaseToken ?? '',
          complete: (status: string) =>
            response.complete(status as PaymentComplete),
        }
      })
    },
    warn: (message, detail) => {
      console.warn(`[badgeday/play] ${message}`, detail)
    },
  })
}
