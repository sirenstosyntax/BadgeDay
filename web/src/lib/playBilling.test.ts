import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { configuredSkus } from './playBilling'

describe('configuredSkus', () => {
  const products = {
    monthly: 'promote.monthly',
    intensive_90day: 'promote.90',
    recruit_monthly: 'recruit.monthly',
    recruit_intensive_90day: 'recruit.90',
    recruit_6month: 'recruit.6mo',
    recruit_annual: 'recruit.yr',
  }

  it('lists only Promote SKUs by default', () => {
    assert.deepEqual(configuredSkus(products), ['promote.monthly', 'promote.90'])
  })

  it('lists the four Recruit SKUs when the paywall is Recruit', () => {
    assert.deepEqual(configuredSkus(products, 'recruit'), [
      'recruit.monthly',
      'recruit.90',
      'recruit.6mo',
      'recruit.yr',
    ])
  })

  it('drops blank Recruit placeholders', () => {
    assert.deepEqual(
      configuredSkus({ recruit_monthly: 'recruit.monthly', recruit_annual: '' }, 'recruit'),
      ['recruit.monthly'],
    )
  })
})
