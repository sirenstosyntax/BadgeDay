import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'
import {
  SIGNUP_TOUCH_KEY,
  captureSignupTouch,
  referrerDomain,
  signupAttributionBody,
  touchFromLanding,
} from './signupTouch.ts'

const root = dirname(fileURLToPath(import.meta.url))

function memoryStore(initial: Record<string, string> = {}) {
  const data = { ...initial }
  return {
    getItem: (key: string) => (key in data ? data[key] : null),
    setItem: (key: string, value: string) => {
      data[key] = value
    },
    removeItem: (key: string) => {
      delete data[key]
    },
    data,
  }
}

test('referrer keeps the hostname and drops the path, query, and userinfo', () => {
  assert.equal(
    referrerDomain('https://news.ycombinator.com/item?id=1'),
    'news.ycombinator.com',
  )
  assert.equal(
    referrerDomain('https://user:pass@jobs.example.com:8443/a/b?q=1#x'),
    'jobs.example.com',
  )
  assert.equal(referrerDomain('https://www.google.com/search?q=firefighter'), 'www.google.com')
  assert.equal(referrerDomain(''), null)
  assert.equal(referrerDomain('   '), null)
  assert.equal(referrerDomain('not a url'), null)
})

test('our own hosts and IP referrers are ignored', () => {
  assert.equal(referrerDomain('https://app.badgeday.com/start?src=zazu'), null)
  assert.equal(referrerDomain('https://badgeday.com/'), null)
  assert.equal(referrerDomain('https://www.badgeday.com/waitlist'), null)
  assert.equal(referrerDomain('https://App.BadgeDay.com/foo'), null)
  assert.equal(referrerDomain('https://api.badgeday.com/'), null)
  assert.equal(referrerDomain('https://badgeday.app/'), null)
  assert.equal(referrerDomain('https://www.badgeday.app/'), null)
  assert.equal(referrerDomain('https://sirenstosyntax.com/privacy'), null)
  assert.equal(referrerDomain('https://www.sirenstosyntax.com/'), null)
  assert.equal(referrerDomain('http://8.8.8.8/lookup'), null)
  assert.equal(referrerDomain('http://[2001:db8::1]/'), null)
  assert.equal(referrerDomain('https://www.google.com/search?q=firefighter'), 'www.google.com')
})

test('utm tags are captured and a value that fails the src rule is dropped', () => {
  const touch = touchFromLanding(
    'https://news.ycombinator.com/item?id=1',
    '?utm_source=hn&utm_medium=social&utm_campaign=oct&utm_term=secret',
  )
  assert.deepEqual(touch, {
    referrer_domain: 'news.ycombinator.com',
    utm_source: 'hn',
    utm_medium: 'social',
    utm_campaign: 'oct',
  })

  const partial = touchFromLanding(
    '',
    `?utm_source=has%20space&utm_medium=email&utm_campaign=${'x'.repeat(65)}&utm_source=a@b.com`,
  )
  assert.deepEqual(partial, {
    referrer_domain: null,
    utm_source: null,
    utm_medium: 'email',
    utm_campaign: null,
  })
  assert.equal(touchFromLanding('', ''), null)
  assert.equal(touchFromLanding('https://badgeday.com/pricing', '?utm_source=has space'), null)
})

test('the first landing wins, including across the magic-link return', () => {
  const store = memoryStore()
  assert.equal(captureSignupTouch({ referrer: '', search: '' }, store), null)
  assert.equal(store.getItem(SIGNUP_TOUCH_KEY), null)

  const first = captureSignupTouch(
    {
      referrer: 'https://news.ycombinator.com/item?id=1',
      search: '?utm_source=hn&utm_medium=social&utm_campaign=oct',
    },
    store,
  )
  assert.equal(first?.referrer_domain, 'news.ycombinator.com')
  assert.equal(store.data[SIGNUP_TOUCH_KEY]?.includes('/item'), false)
  assert.equal(store.data[SIGNUP_TOUCH_KEY]?.includes('id='), false)

  const returned = captureSignupTouch(
    { referrer: 'https://app.badgeday.com/', search: '?utm_source=bing' },
    store,
  )
  assert.equal(returned?.referrer_domain, 'news.ycombinator.com')
  assert.equal(returned?.utm_source, 'hn')
  assert.equal(returned?.utm_medium, 'social')
  assert.equal(returned?.utm_campaign, 'oct')
})

test('an explicit src stays its own field and the post body has no URL or address', () => {
  const touch = touchFromLanding('https://google.com/search?q=1', '?utm_source=newsletter')
  const body = signupAttributionBody('test1', touch)
  assert.equal(body.src, 'test1')
  assert.equal(body.referrer_domain, 'google.com')
  assert.equal(body.utm_source, 'newsletter')
  assert.deepEqual(Object.keys(body).sort(), ['referrer_domain', 'src', 'utm_source'])
  const encoded = JSON.stringify(body)
  assert.equal(encoded.includes('http'), false)
  assert.equal(encoded.includes('search'), false)
  assert.equal(encoded.includes('Mozilla'), false)

  const bare = signupAttributionBody(null, touch)
  assert.equal('src' in bare, false)
  assert.equal(bare.referrer_domain, 'google.com')
})

test('first touch is captured on any page, not only /start', () => {
  const app = readFileSync(join(root, '../App.tsx'), 'utf8')
  const captureAt = app.indexOf('captureSignupTouch(')
  const startGuard = app.indexOf("if (activationEntry(path, null) === 'start')")
  assert.ok(captureAt > 0)
  assert.ok(startGuard > captureAt)
  assert.match(app, /signupAttributionBody\(src, touch\)/)
})
