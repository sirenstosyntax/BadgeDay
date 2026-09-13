import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  PLAY_REVIEWER_DENIED,
  looksLikeReviewerPassword,
  playReviewerConfigured,
  playReviewerSignInBody,
  showPlayReviewerPassword,
} from './playReviewer.ts'

test('the password field stays hidden until the API says the path is on', () => {
  assert.equal(showPlayReviewerPassword(false), false)
  assert.equal(showPlayReviewerPassword(true), true)
})

test('configured is true only for the exact API flag', () => {
  assert.equal(playReviewerConfigured({ configured: true }), true)
  assert.equal(playReviewerConfigured({ configured: false }), false)
  assert.equal(playReviewerConfigured({}), false)
  assert.equal(playReviewerConfigured(null), false)
  assert.equal(playReviewerConfigured({ configured: 'true' }), false)
  assert.equal(playReviewerConfigured({ emails: 'reviewer@example.com' }), false)
})

test('the sign-in body trims email and never invents a password', () => {
  assert.deepEqual(playReviewerSignInBody('  reviewer@example.com  ', 'secret'), {
    email: 'reviewer@example.com',
    password: 'secret',
  })
  assert.equal(looksLikeReviewerPassword(''), false)
  assert.equal(looksLikeReviewerPassword('secret'), true)
})

test('denied copy does not mention an allowlist or OTP', () => {
  assert.match(PLAY_REVIEWER_DENIED, /email and password did not match/i)
  assert.doesNotMatch(PLAY_REVIEWER_DENIED, /allowlist|otp|magic.?link|reviewer email/i)
})
