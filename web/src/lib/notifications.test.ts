import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  EXAM_DAY_BODY,
  EXAM_WEEK_BODY,
  STREAK_BODY,
  examNotifications,
  parseExamDate,
  streakFireAt,
} from './notifications'

describe('practice-streak schedule', () => {
  it('fires at 18:00 local when they practiced a prior day and not today', () => {
    const now = new Date(2026, 8, 13, 10, 0, 0)
    const at = streakFireAt('2026-09-12', now)
    assert.ok(at)
    assert.equal(at.getHours(), 18)
    assert.equal(at.getDate(), 13)
  })

  it('does not schedule when they already practiced today', () => {
    const now = new Date(2026, 8, 13, 10, 0, 0)
    assert.equal(streakFireAt('2026-09-13', now), null)
  })

  it('does not schedule when they have never practiced', () => {
    assert.equal(streakFireAt(null, new Date(2026, 8, 13, 10, 0, 0)), null)
  })
})

describe('exam-date countdown', () => {
  it('schedules morning of exam day and seven days before when that date is future', () => {
    const now = new Date(2026, 8, 1, 9, 0, 0)
    const planned = examNotifications('2026-09-20', now)
    assert.equal(planned.length, 2)
    assert.equal(
      planned.some((item) => item.body === EXAM_WEEK_BODY),
      true,
    )
    assert.equal(
      planned.some((item) => item.body === EXAM_DAY_BODY),
      true,
    )
  })

  it('schedules nothing for a date already past', () => {
    const now = new Date(2026, 8, 21, 9, 0, 0)
    assert.deepEqual(examNotifications('2026-09-20', now), [])
  })

  it('accepts only a YYYY-MM-DD date', () => {
    assert.equal(parseExamDate('2026-09-20'), '2026-09-20')
    assert.equal(parseExamDate('tonight'), null)
  })
})

describe('placeholder copy', () => {
  it('keeps streak and exam strings product-safe (no scores, no department names)', () => {
    for (const line of [STREAK_BODY, EXAM_WEEK_BODY, EXAM_DAY_BODY]) {
      assert.equal(line.includes('score'), false)
      assert.equal(/FD|department|engine/i.test(line), false)
    }
  })
})
