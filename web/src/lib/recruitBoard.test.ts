import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { describe, it } from 'node:test'
import { fileURLToPath } from 'node:url'
import {
  BOARD_FRAMING,
  HOLDING_HEADING,
  NOTES_BLOCKED_COPY,
  SOFT_TIMER_SECONDS,
  boardProgressLabel,
  boardPromptHeading,
  formatSoftTimer,
  leaveAfterAbandon,
  shouldPostAbandon,
  shouldShowNotesBlockedPath,
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

describe('holding chrome', () => {
  it('does not show Loading… when question_text was cleared', () => {
    assert.equal(boardPromptHeading('holding', ''), HOLDING_HEADING)
    assert.notEqual(boardPromptHeading('holding', ''), 'Loading…')
    assert.equal(boardPromptHeading('holding', 'Why this work?'), HOLDING_HEADING)
    assert.equal(boardPromptHeading('ready', 'Why this work?'), 'Why this work?')
    assert.equal(boardPromptHeading('ready', ''), 'Loading…')
    assert.equal(boardPromptHeading('blocked', ''), '')
  })

  it('the mic screen uses the heading helper instead of a bare Loading fallback', () => {
    const source = readFileSync(join(root, '../ui/Recruit.tsx'), 'utf8')
    assert.match(source, /boardPromptHeading/)
    assert.doesNotMatch(source, /question \|\| 'Loading…'/)
  })
})

describe('leave during holding', () => {
  it('keeps a just-completed board instead of treating Leave as abandon', () => {
    assert.equal(shouldPostAbandon('scoring'), true)
    assert.equal(shouldPostAbandon('in_progress'), true)
    assert.equal(shouldPostAbandon('completed'), false)
    assert.equal(leaveAfterAbandon('completed'), 'summary')
    assert.equal(leaveAfterAbandon('abandoned'), 'leave')
  })

  it('the Leave control reads the abandon response', () => {
    const source = readFileSync(join(root, '../ui/Recruit.tsx'), 'utf8')
    assert.match(source, /leaveAfterAbandon/)
    assert.match(source, /shouldPostAbandon/)
    assert.match(source, /setPhase\('summary'\)/)
  })
})

describe('notes blocked path', () => {
  it('opens on a terminal slot that cannot finish notes', () => {
    assert.equal(shouldShowNotesBlockedPath({ notes_blocked: true }), true)
    assert.equal(shouldShowNotesBlockedPath({ attemptStatus: 'critique_failed' }), true)
    assert.equal(shouldShowNotesBlockedPath({ attemptFailed: true }), true)
    assert.equal(shouldShowNotesBlockedPath({ attemptStatus: 'completed' }), false)
    assert.match(NOTES_BLOCKED_COPY, /can't be finished/)
    assert.match(NOTES_BLOCKED_COPY, /Leave to abandon/)
  })

  it('the mic screen stops polling when notes cannot finish', () => {
    const source = readFileSync(join(root, '../ui/Recruit.tsx'), 'utf8')
    assert.match(source, /shouldShowNotesBlockedPath/)
    assert.match(source, /NOTES_BLOCKED_COPY/)
    assert.match(source, /notes_blocked/)
  })
})
