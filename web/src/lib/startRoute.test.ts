import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'
import {
  activationEntry,
  clearSignupSrc,
  pathFor,
  readSignupSrc,
  START_CAMPAIGN_HEADING,
  showStartCampaign,
  startEntry,
  syncSignupSrc,
  validSignupSrc,
} from './startRoute.ts'

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

test('a new visitor on /start is the free board; a used board is Recruit home', () => {
  assert.equal(startEntry(true), 'board')
  assert.equal(startEntry(false), 'home')
  assert.equal(activationEntry('/start', null), 'start')
  assert.equal(activationEntry('/start/', null), 'start')
  assert.equal(activationEntry('/', '/start'), 'start')
  assert.equal(activationEntry('/recruit/test-date', null), 'test-date')
  assert.equal(activationEntry('/', null), null)
  assert.equal(pathFor('start'), '/start')
  assert.equal(pathFor('test-date'), '/recruit/test-date')
})

test('/start?src=test1 is kept and a visit with no tag stores nothing', () => {
  assert.equal(validSignupSrc('test1'), 'test1')
  assert.equal(validSignupSrc('nebraska-nov'), 'nebraska-nov')
  assert.equal(validSignupSrc(null), null)
  assert.equal(validSignupSrc(''), null)
  assert.equal(validSignupSrc('  '), null)
  assert.equal(validSignupSrc('a@b.com'), null)
  assert.equal(validSignupSrc('has space'), null)
  assert.equal(validSignupSrc('x'.repeat(65)), null)
  assert.equal(validSignupSrc('x'.repeat(64)), 'x'.repeat(64))

  const tagged = memoryStore()
  syncSignupSrc('?src=test1', tagged)
  assert.equal(readSignupSrc(tagged), 'test1')
  syncSignupSrc('?src=other', tagged)
  assert.equal(readSignupSrc(tagged), 'test1')

  const bare = memoryStore({ 'badgeday.signup-src': 'stale' })
  syncSignupSrc('', bare)
  assert.equal(readSignupSrc(bare), null)
  clearSignupSrc(bare)
  assert.equal(readSignupSrc(bare), null)
})

test('a signed-out /start with ?src= is the free-board campaign', () => {
  assert.equal(
    START_CAMPAIGN_HEADING,
    'Practice a full oral board out loud. Your first board is free, no card.',
  )
  assert.equal(showStartCampaign('/start', '?src=zazu-test'), true)
  assert.equal(showStartCampaign('/start/', '?src=zazu-test'), true)
  assert.equal(showStartCampaign('/start', ''), false)
  assert.equal(showStartCampaign('/start', '?src='), false)
  assert.equal(showStartCampaign('/start', '?src=a@b.com'), false)
  assert.equal(showStartCampaign('/', '?src=zazu-test'), false)
  assert.equal(showStartCampaign('/recruit', '?src=zazu-test'), false)
})

test('the start page is a phone page: viewport, one date field, question 1, home', () => {
  const html = readFileSync(join(root, '../../index.html'), 'utf8')
  assert.match(html, /width=device-width/)
  const date = readFileSync(join(root, '../ui/TestDate.tsx'), 'utf8')
  assert.match(date, /type="date"/)
  assert.match(date, /w-full/)
  assert.match(date, /text-base/)
  assert.equal((date.match(/<input/g) || []).length, 1)
  const recruit = readFileSync(join(root, '../ui/Recruit.tsx'), 'utf8')
  assert.match(recruit, /data-testid="recruit-home"/)
  assert.match(recruit, /data-testid="oral-board-question"/)
  const app = readFileSync(join(root, '../App.tsx'), 'utf8')
  assert.match(app, /startEntry\(account.free_board_open === true\)/)
  assert.match(app, /flex-wrap/)
})
