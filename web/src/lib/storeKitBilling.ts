/**
 * StoreKit, as the iOS Capacitor page talks to it.
 *
 * Mirror of playBilling: detect the till, show StoreKit prices (never a
 * hardcoded dollar amount), purchase, restore, report the transaction id to
 * `POST /billing/store/appstore/purchase`. Product ids arrive from `/me`
 * (`appstore_products`) — ops-filled, never invented here.
 *
 * Safari and the Play TWA have no NativePurchases plugin; they stay on Stripe
 * / Play. Cancelled sheets are not an error banner.
 */
import { callPlugin } from './capacitorBridge'
import { configuredSkus, type PlayProductIds, type PlaySkuModule } from './playBilling'
import { currentHost, detectIosCapacitorShell, type CapacitorHost } from './platform'

export type AppStoreProductIds = PlayProductIds
export type AppStoreSkuModule = PlaySkuModule

export const APPLE_SUBSCRIPTIONS_URL = 'https://apps.apple.com/account/subscriptions'

export type StoreKitItemDetails = {
  productId: string
  title: string
  priceString: string
  productType: 'subs' | 'inapp'
}

export type ReportAppStorePurchase = (
  transactionId: string,
) => Promise<{ entitled: boolean }>

const SUBSCRIPTION_FIELDS = new Set(['monthly', 'recruit_monthly', 'recruit_annual'])

export function appStoreConfiguredSkus(
  products: AppStoreProductIds | null | undefined,
  module: AppStoreSkuModule = 'promote',
): string[] {
  return configuredSkus(products, module)
}

export function productTypeForSku(
  sku: string,
  products: AppStoreProductIds | null | undefined,
): 'subs' | 'inapp' {
  const fields: Array<keyof AppStoreProductIds> = [
    'monthly',
    'intensive_90day',
    'recruit_monthly',
    'recruit_intensive_90day',
    'recruit_6month',
    'recruit_annual',
  ]
  for (const field of fields) {
    if (products?.[field] === sku) {
      return SUBSCRIPTION_FIELDS.has(field) ? 'subs' : 'inapp'
    }
  }
  return 'inapp'
}

export function isStoreKitCancel(caught: unknown): boolean {
  const message = caught instanceof Error ? caught.message : String(caught)
  const lower = message.toLowerCase()
  return (
    lower.includes('cancel') ||
    lower.includes('dismiss') ||
    lower.includes('user cancelled') ||
    lower.includes('paymentcancelled')
  )
}

export function createStoreKitBilling(deps: {
  isIosShell: () => boolean
  getProducts: (ids: string[], productType: 'subs' | 'inapp') => Promise<StoreKitItemDetails[]>
  purchase: (
    sku: string,
    productType: 'subs' | 'inapp',
  ) => Promise<{ transactionId: string } | { cancelled: true }>
  listTransactions: () => Promise<Array<{ transactionId: string }>>
  reportPurchase: ReportAppStorePurchase
  manageSubscriptions?: () => Promise<void>
  warn?: (message: string, detail?: unknown) => void
}) {
  const warn = deps.warn ?? (() => undefined)

  function available() {
    return Promise.resolve(deps.isIosShell())
  }

  function detailsFor(skus: string[], products?: AppStoreProductIds | null) {
    if (skus.length === 0) return Promise.resolve([] as StoreKitItemDetails[])
    const subs = skus.filter((sku) => productTypeForSku(sku, products) === 'subs')
    const inapp = skus.filter((sku) => productTypeForSku(sku, products) === 'inapp')
    return Promise.all([
      subs.length ? deps.getProducts(subs, 'subs').catch(() => []) : Promise.resolve([]),
      inapp.length ? deps.getProducts(inapp, 'inapp').catch(() => []) : Promise.resolve([]),
    ]).then(([a, b]) => {
      const found = [...a, ...b]
      return skus
        .map((sku) => found.find((item) => item.productId === sku))
        .filter((item): item is StoreKitItemDetails => Boolean(item))
    })
  }

  function report(transactionId: string) {
    return Promise.resolve()
      .then(() => deps.reportPurchase(transactionId))
      .then((res) => ({ ok: true as const, entitled: res.entitled }))
      .catch((err: unknown) => {
        warn('app store purchase report failed', err)
        return { ok: false as const, entitled: false, error: String(err) }
      })
  }

  function restore() {
    if (!deps.isIosShell()) return Promise.resolve([] as string[])
    return Promise.resolve()
      .then(() => deps.listTransactions())
      .then((rows) => {
        const reported: string[] = []
        return Promise.all(
          rows.map((row) => {
            if (!row?.transactionId) return Promise.resolve()
            return report(row.transactionId).then((res) => {
              if (res.ok) reported.push(row.transactionId)
            })
          }),
        ).then(() => reported)
      })
      .catch((err: unknown) => {
        warn('could not list existing App Store purchases', err)
        return [] as string[]
      })
  }

  async function buy(sku: string, products?: AppStoreProductIds | null) {
    if (!sku) return { ok: false as const, reason: 'no-sku' as const }
    if (!deps.isIosShell()) return { ok: false as const, reason: 'no-store' as const }
    try {
      const result = await deps.purchase(sku, productTypeForSku(sku, products))
      if ('cancelled' in result && result.cancelled) {
        return { ok: false as const, reason: 'cancelled' as const }
      }
      if (!('transactionId' in result) || !result.transactionId) {
        return { ok: false as const, reason: 'no-transaction-id' as const }
      }
      const res = await report(result.transactionId)
      if (!res.ok) {
        return { ok: false as const, reason: 'report-failed' as const, error: res.error }
      }
      return { ok: true as const, entitled: res.entitled, transactionId: result.transactionId }
    } catch (err: unknown) {
      if (isStoreKitCancel(err)) return { ok: false as const, reason: 'cancelled' as const }
      return { ok: false as const, reason: 'payment-failed' as const, error: String(err) }
    }
  }

  function openManage() {
    if (typeof deps.manageSubscriptions === 'function') {
      return deps.manageSubscriptions().catch(() => {
        window.location.href = APPLE_SUBSCRIPTIONS_URL
      })
    }
    window.location.href = APPLE_SUBSCRIPTIONS_URL
    return Promise.resolve()
  }

  return { available, detailsFor, restore, buy, openManage }
}

type NativeProduct = {
  identifier?: string
  productIdentifier?: string
  title?: string
  priceString?: string
  price?: string
}

type NativePurchase = {
  transactionId?: string
}

function asItem(product: NativeProduct, productType: 'subs' | 'inapp'): StoreKitItemDetails | null {
  const productId = product.identifier || product.productIdentifier
  if (!productId) return null
  const priceString = product.priceString || product.price || ''
  return {
    productId,
    title: product.title || productId,
    priceString,
    productType,
  }
}

export function browserStoreKitBilling(
  reportPurchase: ReportAppStorePurchase,
  host: CapacitorHost = currentHost(),
) {
  return createStoreKitBilling({
    isIosShell: () => detectIosCapacitorShell(host),
    getProducts: async (ids, productType) => {
      const result = await callPlugin<{ products?: NativeProduct[] }>(
        'NativePurchases',
        'getProducts',
        { productIdentifiers: ids, productType },
        host,
      )
      return (result.products || [])
        .map((product) => asItem(product, productType))
        .filter((item): item is StoreKitItemDetails => Boolean(item))
    },
    purchase: async (sku, productType) => {
      try {
        const result = await callPlugin<{ transactionId?: string }>(
          'NativePurchases',
          'purchaseProduct',
          { productIdentifier: sku, productType },
          host,
        )
        return { transactionId: result.transactionId || '' }
      } catch (caught) {
        if (isStoreKitCancel(caught)) return { cancelled: true }
        throw caught
      }
    },
    listTransactions: async () => {
      try {
        await callPlugin('NativePurchases', 'restorePurchases', undefined, host)
      } catch {
        /* restorePurchases is best-effort; getPurchases still lists owned txns. */
      }
      const result = await callPlugin<{ purchases?: NativePurchase[] }>(
        'NativePurchases',
        'getPurchases',
        undefined,
        host,
      )
      return (result.purchases || [])
        .map((row) => ({ transactionId: row.transactionId || '' }))
        .filter((row) => row.transactionId)
    },
    reportPurchase,
    manageSubscriptions: () =>
      callPlugin('NativePurchases', 'manageSubscriptions', undefined, host),
    warn: (message, detail) => {
      console.warn(`[badgeday/appstore] ${message}`, detail)
    },
  })
}
