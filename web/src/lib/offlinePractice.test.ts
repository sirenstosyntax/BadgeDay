import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  cacheForUser,
  cacheMatchesScope,
  deviceLocalDate,
  emptyCacheMessage,
  LOCAL_GRADE_NOTE,
  localReviewItems,
  localVerdict,
  OFFLINE_SCHEMA_VERSION,
  parseOfflineCache,
  pendingSyncBodies,
  recordLocalAnswer,
  unansweredQuestions,
  type OfflinePracticeCache,
} from './offlinePractice'

function cache(partial: Partial<OfflinePracticeCache> = {}): OfflinePracticeCache {
  return {
    schema_version: OFFLINE_SCHEMA_VERSION,
    user_id: 'user-1',
    cached_at: '2026-09-12T12:00:00.000Z',
    session_id: 'session-1',
    session_scope: 'whole_list',
    document_id: null,
    questions: [
      {
        id: 'q1',
        document_id: 'd1',
        chunk_id: 'c1',
        type: 'multiple_choice',
        stem: 'What is first?',
        options: ['A', 'B'],
        citation: '304.2.1 Water Supply, p. 3',
      },
      {
        id: 'q2',
        document_id: 'd1',
        chunk_id: 'c2',
        type: 'true_false',
        stem: 'True?',
        options: null,
        citation: 'p. 4',
      },
    ],
    answers_local: [],
    ...partial,
  }
}

describe('offline practice cache', () => {
  it('accepts a schema_version 1 payload and rejects another user', () => {
    const raw = JSON.stringify(cache())
    assert.equal(parseOfflineCache(raw)?.session_id, 'session-1')
    assert.equal(cacheForUser(raw, 'user-1')?.user_id, 'user-1')
    assert.equal(cacheForUser(raw, 'user-2'), null)
    assert.equal(cacheForUser(raw, null), null)
  })

  it('rejects a missing schema or empty question list', () => {
    assert.equal(parseOfflineCache('{"user_id":"u"}'), null)
    assert.equal(parseOfflineCache(JSON.stringify(cache({ schema_version: 2 }))), null)
    assert.equal(parseOfflineCache(JSON.stringify(cache({ questions: [] }))), null)
  })

  it('matches whole-list vs one document', () => {
    const whole = cache()
    const one = cache({ session_scope: 'document', document_id: 'd1' })
    assert.equal(cacheMatchesScope(whole, null), true)
    assert.equal(cacheMatchesScope(whole, 'd1'), false)
    assert.equal(cacheMatchesScope(one, 'd1'), true)
    assert.equal(cacheMatchesScope(one, 'd2'), false)
  })

  it('records a local answer without inventing a grade', () => {
    const answered = recordLocalAnswer(cache(), { question_id: 'q1', selected_index: 1 })
    assert.equal(unansweredQuestions(answered).map((q) => q.id).join(), 'q2')
    const verdict = localVerdict(answered.questions[0])
    assert.equal(verdict.is_correct, null)
    assert.equal(verdict.citation, '304.2.1 Water Supply, p. 3')
    assert.equal(verdict.explanation, LOCAL_GRADE_NOTE)
    const review = localReviewItems(answered)
    assert.equal(review.length, 1)
    assert.equal(review[0].selected_index, 1)
    assert.equal(review[0].is_correct, null)
    assert.deepEqual(pendingSyncBodies(answered), [
      {
        question_id: 'q1',
        selected_index: 1,
        answered_boolean: null,
        answered_text: null,
      },
    ])
  })

  it('tells the candidate to cache while online when nothing is stored', () => {
    assert.match(emptyCacheMessage(), /cache a practice session/i)
  })

  it('uses the device-local calendar date, not UTC', () => {
    const local = new Date(2026, 8, 12, 23, 30, 0)
    assert.equal(deviceLocalDate(local), '2026-09-12')
  })
})
