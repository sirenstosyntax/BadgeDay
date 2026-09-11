import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  clearAuthRedirectError,
  consumeAuthRedirectError,
  readAuthRedirectError,
  resetAuthRedirectErrorForTests,
  takeFreshAuthRedirectError,
} from './authRedirectError.ts'

const LIVE_HASH =
  '#error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid+or+has+expired'

test('live otp_expired hash becomes a visible SignIn message', () => {
  const message = readAuthRedirectError(LIVE_HASH)
  assert.equal(
    message,
    'This sign-in link is invalid or has expired. Type the code from the email if the button did nothing, or request a new email.',
  )
})

test('the same keys on the query string are also read', () => {
  const message = readAuthRedirectError(
    '',
    '?error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid+or+has+expired',
  )
  assert.equal(
    message,
    'This sign-in link is invalid or has expired. Type the code from the email if the button did nothing, or request a new email.',
  )
})

test('a token-bearing magic-link hash is not treated as an error', () => {
  assert.equal(
    readAuthRedirectError('#access_token=tok&refresh_token=ref&expires_in=3600&token_type=bearer'),
    null,
  )
})

test('an empty location is not an error', () => {
  assert.equal(readAuthRedirectError(''), null)
  assert.equal(readAuthRedirectError('#', ''), null)
})

test('other auth redirect errors keep the description and ask for a new link', () => {
  assert.equal(
    readAuthRedirectError('#error=access_denied&error_description=Email+link+was+already+used'),
    'Email link was already used. Type the code from the email if the button did nothing, or request a new email.',
  )
})

test('hashchange does not revive a stale consumed error when the URL is clean', () => {
  resetAuthRedirectErrorForTests()
  const expired = takeFreshAuthRedirectError(LIVE_HASH)
  assert.equal(
    expired,
    'This sign-in link is invalid or has expired. Type the code from the email if the button did nothing, or request a new email.',
  )
  assert.equal(takeFreshAuthRedirectError(''), null)
  assert.equal(takeFreshAuthRedirectError('#', ''), null)
  // Mount / Strict Mode may still reuse consumed when there is no window.
  assert.equal(consumeAuthRedirectError(), expired)
})

test('after clear, consume on a clean URL returns null', () => {
  resetAuthRedirectErrorForTests()
  takeFreshAuthRedirectError(LIVE_HASH)
  assert.ok(consumeAuthRedirectError())
  clearAuthRedirectError()
  assert.equal(consumeAuthRedirectError(), null)
})
