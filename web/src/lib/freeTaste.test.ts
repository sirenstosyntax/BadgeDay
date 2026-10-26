import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { freeTasteNotice, practiceScope, promoteFreeTaste } from './freeTaste'
import type { Account } from './types'

function account(partial: Partial<Account> = {}): Account {
  return {
    id: 'user-1',
    email: 'c@example.com',
    entitled: false,
    subscription_status: 'none',
    access_expires_at: null,
    promote_free_taste_open: true,
    promote_free_taste_document_id: null,
    promote_free_taste_pages: 30,
    promote_free_taste_questions: 10,
    ...partial,
  }
}

describe('Promote free taste', () => {
  it('lets a candidate without a plan upload one document', () => {
    const taste = promoteFreeTaste(account(), false)
    assert.equal(taste.canUpload, true)
    assert.equal(taste.documentId, null)
  })

  it('offers nothing free to a candidate who already has a plan', () => {
    const taste = promoteFreeTaste(account({ entitled: true }), true)
    assert.equal(taste.canUpload, false)
  })

  it('stops offering an upload once the free document is used', () => {
    const taste = promoteFreeTaste(
      account({ promote_free_taste_open: false, promote_free_taste_document_id: 'doc-free' }),
      false,
    )
    assert.equal(taste.canUpload, false)
    assert.equal(taste.documentId, 'doc-free')
  })

  it('treats an unknown account as no free taste, the safe direction', () => {
    assert.equal(promoteFreeTaste(null, false).canUpload, false)
  })

  it('states the caps the server reported', () => {
    const notice = freeTasteNotice(
      promoteFreeTaste(account({ promote_free_taste_pages: 12, promote_free_taste_questions: 4 }), false),
    )
    assert.match(notice, /up to 4 cited questions/)
    assert.match(notice, /first 12 pages/)
  })
})

describe('practice scope', () => {
  const used = promoteFreeTaste(
    account({ promote_free_taste_open: false, promote_free_taste_document_id: 'doc-free' }),
    false,
  )

  it('keeps the candidate choice when they have a plan', () => {
    const paid = promoteFreeTaste(account({ entitled: true }), true)
    assert.equal(practiceScope(true, paid, null), null)
    assert.equal(practiceScope(true, paid, 'doc-1'), 'doc-1')
  })

  it('opens the free document without a plan', () => {
    assert.equal(practiceScope(false, used, 'doc-free'), 'doc-free')
  })

  it('turns the whole list into the free document, since a mix needs a plan', () => {
    assert.equal(practiceScope(false, used, null), 'doc-free')
  })

  it('sends any other document to the paywall', () => {
    assert.equal(practiceScope(false, used, 'doc-paid-earlier'), undefined)
    assert.equal(practiceScope(false, promoteFreeTaste(account(), false), null), undefined)
  })
})
