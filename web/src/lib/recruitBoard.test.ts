import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { describe, it } from 'node:test'
import { fileURLToPath } from 'node:url'
import {
  BOARD_FRAMING,
  SOFT_TIMER_SECONDS,
  boardProgressLabel,
  formatSoftTimer,
} from './recruitBoard'

const root = dirname(fileURLToPath(import.meta.url))

describe('soft timer', () => {
  it('is two minutes and formats without going negative', () => {
    assert.equal(SOFT_TIMER_SECONDS, 120)
    assert.equal(formatSoftTimer(120), '2:00')
    assert.equal(formatSoftTimer(0), '0:00')
    assert.equal(formatSoftTimer(-3), '0:00')
  })

  it('the mic screen never auto-submits when the timer hits zero', () => {
    const source = readFileSync(join(root, '../ui/Recruit.tsx'), 'utf8')
    assert.match(source, /SOFT_TIMER_SECONDS/)
    assert.doesNotMatch(source, /auto-submit|autosubmit|submit\(\).*timer|timer.*submit\(\)/i)
    assert.match(source, /soft timer/i)
  })
})

describe('board progress', () => {
  it('names the current slot only', () => {
    assert.equal(boardProgressLabel(1), 'Question 1 of 5')
    assert.equal(boardProgressLabel(5), 'Question 5 of 5')
  })

  it('holds the Red-signed framing string', () => {
    assert.equal(
      BOARD_FRAMING,
      'Board complete. Notes held until the end on purpose — same as a real board.',
    )
  })
})
