import assert from 'node:assert/strict'
import { test } from 'node:test'
import { looksLikeSignInEmail, showSignInCodeField } from './signInCodeField.ts'

test('a burned-link redirect shows the code field with no remembered email', () => {
  assert.equal(showSignInCodeField({ sent: false, email: '', fromRedirect: true }), true)
  assert.equal(showSignInCodeField({ sent: false, email: 'not-an-address', fromRedirect: true }), true)
})

test('a burned-link return with a remembered email is not a successful send', () => {
  assert.equal(
    showSignInCodeField({ sent: false, email: 'qa@example.com', fromRedirect: true }),
    true,
  )
})

test('verify is refused until the email looks like an email', () => {
  assert.equal(looksLikeSignInEmail(''), false)
  assert.equal(looksLikeSignInEmail('   '), false)
  assert.equal(looksLikeSignInEmail('not-an-address'), false)
  assert.equal(looksLikeSignInEmail('@'), false)
  assert.equal(looksLikeSignInEmail('qa@example.com'), true)
})

test('clean SignIn hides the code field until an email is typed or a link is sent', () => {
  assert.equal(showSignInCodeField({ sent: false, email: '', fromRedirect: false }), false)
  assert.equal(showSignInCodeField({ sent: false, email: 'qa', fromRedirect: false }), false)
  assert.equal(showSignInCodeField({ sent: false, email: 'qa@example.com', fromRedirect: false }), true)
  assert.equal(showSignInCodeField({ sent: true, email: 'qa@example.com', fromRedirect: false }), true)
})
