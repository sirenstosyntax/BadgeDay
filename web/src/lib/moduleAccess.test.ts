import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  anyModuleHasManageableBilling,
  headerManageModule,
  headerSubscribeModule,
  moduleEntitled,
  moduleHasManageableBilling,
  moduleIsPassOnly,
  moduleManagedBy,
  modulePlanSummary,
  shouldOfferCheckout,
} from './moduleAccess'
import type { Account } from './types'

function account(partial: Partial<Account> = {}): Account {
  return {
    id: 'user-1',
    email: 'c@example.com',
    entitled: false,
    subscription_status: 'none',
    access_expires_at: null,
    recruit: {
      entitled: false,
      subscription_status: 'none',
      access_expires_at: null,
    },
    ...partial,
  }
}

describe('module entitlement', () => {
  it('reads Recruit from the nest, not Promote entitled', () => {
    const recruitOnly = account({
      recruit: { entitled: true, subscription_status: 'active', access_expires_at: null },
    })
    assert.equal(moduleEntitled(recruitOnly, 'recruit'), true)
    assert.equal(moduleEntitled(recruitOnly, 'promote'), false)
    assert.equal(shouldOfferCheckout(recruitOnly, 'recruit'), false)
    assert.equal(shouldOfferCheckout(recruitOnly, 'promote'), true)
  })

  it('reads Promote from the top-level fields, not Recruit', () => {
    const promoteOnly = account({
      entitled: true,
      subscription_status: 'active',
    })
    assert.equal(moduleEntitled(promoteOnly, 'promote'), true)
    assert.equal(moduleEntitled(promoteOnly, 'recruit'), false)
    assert.equal(shouldOfferCheckout(promoteOnly, 'promote'), false)
    assert.equal(shouldOfferCheckout(promoteOnly, 'recruit'), true)
  })

  it('treats a missing account as not entitled for either module', () => {
    assert.equal(moduleEntitled(null, 'recruit'), false)
    assert.equal(moduleEntitled(null, 'promote'), false)
    assert.equal(shouldOfferCheckout(null, 'recruit'), true)
    assert.equal(anyModuleHasManageableBilling(null), false)
  })
})

describe('manageable billing', () => {
  it('shows Manage for a Recruit subscriber who has no Promote plan', () => {
    const recruitOnly = account({
      recruit: { entitled: true, subscription_status: 'active', access_expires_at: null },
    })
    assert.equal(moduleHasManageableBilling(recruitOnly, 'recruit'), true)
    assert.equal(moduleHasManageableBilling(recruitOnly, 'promote'), false)
    assert.equal(anyModuleHasManageableBilling(recruitOnly), true)
    assert.equal(headerManageModule(recruitOnly, 'other'), 'recruit')
    assert.equal(headerManageModule(recruitOnly, 'recruit'), 'recruit')
    assert.equal(headerSubscribeModule('other'), 'promote')
    assert.equal(shouldOfferCheckout(recruitOnly, headerSubscribeModule('recruit')), false)
    assert.equal(shouldOfferCheckout(recruitOnly, headerSubscribeModule('other')), true)
  })

  it('shows Manage for a Promote subscriber and still offers Recruit checkout', () => {
    const promoteOnly = account({
      entitled: true,
      subscription_status: 'active',
    })
    assert.equal(moduleHasManageableBilling(promoteOnly, 'promote'), true)
    assert.equal(moduleHasManageableBilling(promoteOnly, 'recruit'), false)
    assert.equal(headerManageModule(promoteOnly, 'recruit'), 'promote')
    assert.equal(shouldOfferCheckout(promoteOnly, 'recruit'), true)
  })

  it('sends a Play-managed Recruit subscriber to Play, not the Stripe portal', () => {
    const playRecruit = account({
      recruit: {
        entitled: true,
        subscription_status: 'active',
        access_expires_at: null,
        managed_by: 'play',
      },
    })
    assert.equal(moduleManagedBy(playRecruit, 'recruit'), 'play')
    assert.equal(moduleManagedBy(playRecruit, 'promote'), null)
    assert.equal(headerManageModule(playRecruit, 'other'), 'recruit')
  })

  it('lets past_due open Manage instead of a second checkout', () => {
    const pastDue = account({
      recruit: {
        entitled: false,
        subscription_status: 'past_due',
        access_expires_at: null,
      },
    })
    assert.equal(moduleHasManageableBilling(pastDue, 'recruit'), true)
    assert.equal(shouldOfferCheckout(pastDue, 'recruit'), false)
    assert.equal(modulePlanSummary(pastDue, 'recruit'), 'Subscription payment past due.')
  })

  it('lets a canceled, expired Recruit plan buy again', () => {
    const lapsed = account({
      recruit: {
        entitled: false,
        subscription_status: 'canceled',
        access_expires_at: null,
      },
    })
    assert.equal(moduleHasManageableBilling(lapsed, 'recruit'), false)
    assert.equal(shouldOfferCheckout(lapsed, 'recruit'), true)
    assert.equal(modulePlanSummary(lapsed, 'recruit'), 'Subscription canceled.')
  })

  it('summarizes an active Recruit subscription in plain words', () => {
    const recruitOnly = account({
      recruit: { entitled: true, subscription_status: 'active', access_expires_at: null },
    })
    assert.equal(modulePlanSummary(recruitOnly, 'recruit'), 'Active subscription.')
    assert.equal(modulePlanSummary(recruitOnly, 'promote'), 'No active plan.')
  })

  it('does not send a pass-only candidate to a cancel portal', () => {
    const passOnly = account({
      entitled: true,
      subscription_status: 'none',
      access_expires_at: '2026-12-10T00:00:00.000Z',
    })
    assert.equal(moduleEntitled(passOnly, 'promote'), true)
    assert.equal(moduleIsPassOnly(passOnly, 'promote'), true)
    assert.equal(moduleHasManageableBilling(passOnly, 'promote'), false)
    assert.equal(anyModuleHasManageableBilling(passOnly), false)
    assert.equal(shouldOfferCheckout(passOnly, 'promote'), false)
    assert.match(modulePlanSummary(passOnly, 'promote'), /nothing to cancel/)
    assert.match(modulePlanSummary(passOnly, 'promote'), /One-time pass/)
  })

  it('does not treat a Recruit pass as Manage billing', () => {
    const recruitPass = account({
      recruit: {
        entitled: true,
        subscription_status: 'none',
        access_expires_at: '2026-12-10T00:00:00.000Z',
      },
    })
    assert.equal(moduleIsPassOnly(recruitPass, 'recruit'), true)
    assert.equal(moduleHasManageableBilling(recruitPass, 'recruit'), false)
    assert.equal(shouldOfferCheckout(recruitPass, 'recruit'), false)
    assert.equal(shouldOfferCheckout(recruitPass, 'promote'), true)
  })
})
