import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  cacheForUser,
  cacheMatchesScope,
  deviceLocalDate,
  dropPendingAnswer,
  emptyCacheMessage,
  LOCAL_GRADE_NOTE,
  localReviewItems,
  localVerdict,
  offlineCacheFromPack,
  OFFLINE_SCHEMA_VERSION,
  parseOfflineCache,
  pendingSyncBodies,
  pendingSyncFailure,
  recordLocalAnswer,
  resolveOfflinePack,
  reusableOfflineSessionId,
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

  it('treats HTTP 409 AlreadyAnswered as a successful pending drop', () => {
    assert.equal(pendingSyncFailure(409), 'already_answered')
    assert.equal(pendingSyncFailure(404), 'unknown_question')
    assert.equal(pendingSyncFailure(500), 'keep')
    assert.equal(pendingSyncFailure(0), 'keep')
    const kept = dropPendingAnswer(cache({
      answers_local: [
        {
          question_id: 'q1',
          selected_index: 1,
          answered_boolean: null,
          answered_text: null,
          answered_at: '2026-09-12T12:01:00.000Z',
        },
        {
          question_id: 'q2',
          selected_index: null,
          answered_boolean: true,
          answered_text: null,
          answered_at: '2026-09-12T12:02:00.000Z',
        },
      ],
    }).answers_local, 'q1')
    assert.deepEqual(kept.map((row) => row.question_id), ['q2'])
  })

  it('reuses the cached session when re-saving the same scope', () => {
    const whole = cache()
    const one = cache({ session_scope: 'document', document_id: 'd1', session_id: 'session-doc' })
    assert.equal(reusableOfflineSessionId(whole, null), 'session-1')
    assert.equal(reusableOfflineSessionId(whole, 'd1'), null)
    assert.equal(reusableOfflineSessionId(one, 'd1'), 'session-doc')
    assert.equal(reusableOfflineSessionId(null, null), null)
  })

  it('does not call practice.start when the cached session can still pack', async () => {
    const starts: Array<string | null> = []
    const packs: string[] = []
    const resolved = await resolveOfflinePack({
      existing: cache(),
      documentId: null,
      start: async (id) => {
        starts.push(id)
        return { id: 'session-new' }
      },
      pack: async (sessionId) => {
        packs.push(sessionId)
        return { session_id: sessionId, questions: cache().questions }
      },
      isMissingSession: () => false,
    })
    assert.equal(resolved.reused, true)
    assert.equal(resolved.sessionId, 'session-1')
    assert.deepEqual(starts, [])
    assert.deepEqual(packs, ['session-1'])
  })

  it('starts a new session when the cached one is gone, or the scope changed', async () => {
    const starts: Array<string | null> = []
    const missing = await resolveOfflinePack({
      existing: cache(),
      documentId: null,
      start: async (id) => {
        starts.push(id)
        return { id: 'session-new' }
      },
      pack: async (sessionId) => {
        if (sessionId === 'session-1') throw new Error('gone')
        return { session_id: sessionId, questions: cache().questions }
      },
      isMissingSession: (caught) => caught instanceof Error && caught.message === 'gone',
    })
    assert.equal(missing.reused, false)
    assert.equal(missing.sessionId, 'session-new')

    const switched = await resolveOfflinePack({
      existing: cache(),
      documentId: 'd1',
      start: async (id) => {
        starts.push(id)
        return { id: 'session-doc' }
      },
      pack: async (sessionId) => ({ session_id: sessionId, questions: cache().questions }),
      isMissingSession: () => false,
    })
    assert.equal(switched.reused, false)
    assert.equal(switched.sessionId, 'session-doc')
    assert.deepEqual(starts, [null, 'd1'])
  })

  it('keeps matching local answers when re-caching the same session', () => {
    const previous = recordLocalAnswer(cache(), { question_id: 'q1', selected_index: 1 })
    const rebuilt = offlineCacheFromPack({
      userId: 'user-1',
      sessionId: 'session-1',
      documentId: null,
      questions: previous.questions,
      previous,
      now: new Date('2026-09-13T00:00:00.000Z'),
    })
    assert.equal(rebuilt.answers_local.length, 1)
    assert.equal(rebuilt.answers_local[0]?.question_id, 'q1')
    const replaced = offlineCacheFromPack({
      userId: 'user-1',
      sessionId: 'session-new',
      documentId: null,
      questions: previous.questions,
      previous,
    })
    assert.deepEqual(replaced.answers_local, [])
  })
})
