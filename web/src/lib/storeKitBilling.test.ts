import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  appStoreConfiguredSkus,
  createStoreKitBilling,
  productTypeForSku,
} from './storeKitBilling'

const products = {
  monthly: 'ops.promote.monthly',
  intensive_90day: 'ops.promote.90',
  recruit_monthly: 'ops.recruit.monthly',
  recruit_intensive_90day: 'ops.recruit.90',
  recruit_6month: 'ops.recruit.6mo',
  recruit_annual: 'ops.recruit.yr',
}

describe('appStoreConfiguredSkus', () => {
  it('lists only configured ids and never invents a live value', () => {
    assert.deepEqual(appStoreConfiguredSkus(products), [
      'ops.promote.monthly',
      'ops.promote.90',
    ])
    assert.deepEqual(appStoreConfiguredSkus({ monthly: '', intensive_90day: null }, 'promote'), [])
  })

  it('maps monthly/annual to subscriptions and passes to in-app', () => {
    assert.equal(productTypeForSku('ops.promote.monthly', products), 'subs')
    assert.equal(productTypeForSku('ops.promote.90', products), 'inapp')
    assert.equal(productTypeForSku('ops.recruit.yr', products), 'subs')
    assert.equal(productTypeForSku('ops.recruit.6mo', products), 'inapp')
  })
})

describe('createStoreKitBilling', () => {
  it('reports a completed purchase as { transaction_id } to the existing endpoint shape', async () => {
    const posted: string[] = []
    const billing = createStoreKitBilling({
      isIosShell: () => true,
      getProducts: async (ids, productType) =>
        ids.map((productId) => ({
          productId,
          title: productId,
          priceString: '$0.00',
          productType,
        })),
      purchase: async () => ({ transactionId: '2000000012345678' }),
      listTransactions: async () => [{ transactionId: '2000000012345678' }],
      reportPurchase: async (transactionId) => {
        posted.push(transactionId)
        return { entitled: true }
      },
    })
    const items = await billing.detailsFor(['ops.promote.monthly'], products)
    assert.equal(items[0]?.priceString, '$0.00')
    const bought = await billing.buy('ops.promote.monthly', products)
    assert.deepEqual(bought, {
      ok: true,
      entitled: true,
      transactionId: '2000000012345678',
    })
    assert.deepEqual(posted, ['2000000012345678'])
    const restored = await billing.restore()
    assert.deepEqual(restored, ['2000000012345678'])
  })

  it('treats a cancelled sheet as a no-op, not an error banner', async () => {
    const billing = createStoreKitBilling({
      isIosShell: () => true,
      getProducts: async () => [],
      purchase: async () => ({ cancelled: true }),
      listTransactions: async () => [],
      reportPurchase: async () => ({ entitled: false }),
    })
    const result = await billing.buy('ops.promote.monthly', products)
    assert.deepEqual(result, { ok: false, reason: 'cancelled' })
  })

  it('does not claim entitled when the report fails', async () => {
    const billing = createStoreKitBilling({
      isIosShell: () => true,
      getProducts: async () => [],
      purchase: async () => ({ transactionId: '2000000012345678' }),
      listTransactions: async () => [],
      reportPurchase: async () => {
        throw new Error('App Store billing is not configured yet.')
      },
    })
    const result = await billing.buy('ops.promote.monthly', products)
    assert.equal(result.ok, false)
    if (result.ok === false) {
      assert.equal(result.reason, 'report-failed')
    }
  })
})
