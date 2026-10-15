import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  EMAIL_OTP_VERIFY_TYPE,
  SUPABASE_DEFAULT_OTP_LENGTH,
  emailOtpVerifyParams,
  isCompleteEmailOtp,
  normalizeEmailOtp,
} from './emailOtp.ts'

test('strips spaces and punctuation from a typed OTP', () => {
  assert.equal(normalizeEmailOtp('123 456'), '123456')
  assert.equal(normalizeEmailOtp('12-34-5678'), '12345678')
  assert.equal(normalizeEmailOtp('  847291  '), '847291')
})

test('GoTrue default OTP length is 6, and this client still accepts 6–8', () => {
  assert.equal(SUPABASE_DEFAULT_OTP_LENGTH, 6)
  assert.equal(isCompleteEmailOtp('1'.repeat(SUPABASE_DEFAULT_OTP_LENGTH)), true)
  assert.equal(isCompleteEmailOtp('1'.repeat(8)), true)
})

test('accepts 6- to 8-digit codes and rejects shorter or longer', () => {
  assert.equal(isCompleteEmailOtp('123456'), true)
  assert.equal(isCompleteEmailOtp('1234567'), true)
  assert.equal(isCompleteEmailOtp('12345678'), true)
  assert.equal(isCompleteEmailOtp('12345'), false)
  assert.equal(isCompleteEmailOtp('123456789'), false)
  assert.equal(isCompleteEmailOtp(''), false)
  assert.equal(isCompleteEmailOtp(normalizeEmailOtp('12 34 56')), true)
})

test('verifyOtp params use type email and a normalized token', () => {
  assert.deepEqual(emailOtpVerifyParams('user@example.com', '12 34 56'), {
    email: 'user@example.com',
    token: '123456',
    type: EMAIL_OTP_VERIFY_TYPE,
  })
  assert.equal(EMAIL_OTP_VERIFY_TYPE, 'email')
})
