import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { SIGN_IN_EMAIL_HINT, emailAtSubmit, signInEmailToSend } from './signInEmail.ts'

const root = dirname(fileURLToPath(import.meta.url))

test('the live field wins over empty React state', () => {
  assert.equal(emailAtSubmit('qa@example.com', ''), 'qa@example.com')
  assert.equal(emailAtSubmit('  qa@example.com  ', ''), 'qa@example.com')
})

test('a blank mounted field is not replaced by stale state', () => {
  assert.equal(emailAtSubmit('', 'qa@example.com'), '')
  assert.equal(emailAtSubmit('   ', 'qa@example.com'), '')
})

test('an unmounted field falls back to the address already submitted', () => {
  assert.equal(emailAtSubmit(null, ' qa@example.com '), 'qa@example.com')
  assert.equal(emailAtSubmit(null, ''), '')
})

test('an empty email is refused and is not a sendable address', () => {
  assert.throws(() => signInEmailToSend(''), /Enter your email address/)
  assert.throws(() => signInEmailToSend('   '), /Enter your email address/)
  assert.throws(() => signInEmailToSend('not-an-address'), /Enter your email address/)
  assert.equal(signInEmailToSend(' qa@example.com '), 'qa@example.com')
})

test('sign-in reads the named email input and keeps the link-or-code hint', () => {
  const signIn = readFileSync(join(root, '../ui/SignIn.tsx'), 'utf8')
  const auth = readFileSync(join(root, './auth.ts'), 'utf8')
  assert.match(signIn, /name="email"/)
  assert.match(signIn, /emailAtSubmit/)
  assert.match(signIn, /min-h-24/)
  assert.match(signIn, /Have a password\? Sign in/)
  assert.match(signIn, /START_CAMPAIGN_HEADING/)
  assert.equal(
    SIGN_IN_EMAIL_HINT,
    'Click the link in the email, or type the 6-digit code if your email shows one.',
  )
  assert.match(signIn, /SIGN_IN_EMAIL_HINT/)
  assert.doesNotMatch(signIn, /sendMagicLink\(email\)/)
  assert.match(auth, /signInEmailToSend\(email\)/)
  assert.doesNotMatch(auth, /signInWithOtp\(\{\s*email,/)
})
