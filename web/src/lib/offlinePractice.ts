/**
 * One Promote practice session cached on-device for offline drill.
 *
 * Schema version 1. Persistence is device-local (localStorage in the WKWebView),
 * not a new Supabase table. Recruit is not cached — ASR and critique need the
 * network.
 *
 * Last-practice calendar date is device-local (the device's timezone date), not
 * UTC. Used only to schedule streak notifications.
 */
import type { AnswerBody } from './api'
import type { QuestionType, ReviewItem, Verdict } from './types'

export const OFFLINE_SCHEMA_VERSION = 1
export const OFFLINE_CACHE_KEY = 'badgeday.offlinePractice.v1'
export const LAST_PRACTICE_KEY = 'badgeday.lastPracticeDate.v1'

export type OfflineSessionScope = 'document' | 'whole_list'

export type OfflineQuestion = {
  id: string
  document_id: string
  chunk_id: string
  type: QuestionType
  stem: string
  options: string[] | null
  citation: string
}

export type OfflineAnswer = {
  question_id: string
  selected_index?: number | null
  answered_boolean?: boolean | null
  answered_text?: string | null
  answered_at: string
}

export type OfflinePracticeCache = {
  schema_version: number
  user_id: string
  cached_at: string
  session_id: string
  session_scope: OfflineSessionScope
  document_id: string | null
  questions: OfflineQuestion[]
  answers_local: OfflineAnswer[]
}

export const LOCAL_GRADE_NOTE =
  'Saved on this device. The grade and model answer appear when you are back online.'

export function deviceLocalDate(now: Date = new Date()): string {
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function emptyCacheMessage(): string {
  return 'Cache a practice session while you have a connection, then you can drill it offline.'
}

export function parseOfflineCache(raw: string | null): OfflinePracticeCache | null {
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Partial<OfflinePracticeCache>
    if (parsed.schema_version !== OFFLINE_SCHEMA_VERSION) return null
    if (typeof parsed.user_id !== 'string' || !parsed.user_id) return null
    if (typeof parsed.session_id !== 'string' || !parsed.session_id) return null
    if (parsed.session_scope !== 'document' && parsed.session_scope !== 'whole_list') {
      return null
    }
    if (!Array.isArray(parsed.questions) || parsed.questions.length === 0) return null
    return {
      schema_version: OFFLINE_SCHEMA_VERSION,
      user_id: parsed.user_id,
      cached_at: typeof parsed.cached_at === 'string' ? parsed.cached_at : '',
      session_id: parsed.session_id,
      session_scope: parsed.session_scope,
      document_id: parsed.document_id ?? null,
      questions: parsed.questions as OfflineQuestion[],
      answers_local: Array.isArray(parsed.answers_local)
        ? (parsed.answers_local as OfflineAnswer[])
        : [],
    }
  } catch {
    return null
  }
}

export function cacheForUser(
  raw: string | null,
  userId: string | null | undefined,
): OfflinePracticeCache | null {
  const cache = parseOfflineCache(raw)
  if (!cache || !userId || cache.user_id !== userId) return null
  return cache
}

export function writeOfflineCache(
  store: Pick<Storage, 'setItem'>,
  cache: OfflinePracticeCache,
): void {
  store.setItem(OFFLINE_CACHE_KEY, JSON.stringify(cache))
}

export function readOfflineCache(
  store: Pick<Storage, 'getItem'>,
  userId: string | null | undefined,
): OfflinePracticeCache | null {
  return cacheForUser(store.getItem(OFFLINE_CACHE_KEY), userId)
}

export function clearOfflineCache(store: Pick<Storage, 'removeItem'>): void {
  store.removeItem(OFFLINE_CACHE_KEY)
}

export function recordLastPractice(store: Pick<Storage, 'setItem'>, now: Date = new Date()): void {
  store.setItem(LAST_PRACTICE_KEY, deviceLocalDate(now))
}

export function readLastPractice(store: Pick<Storage, 'getItem'>): string | null {
  return store.getItem(LAST_PRACTICE_KEY)
}

export function cacheMatchesScope(
  cache: OfflinePracticeCache,
  documentId: string | null,
): boolean {
  if (documentId === null) return cache.session_scope === 'whole_list'
  return cache.session_scope === 'document' && cache.document_id === documentId
}

export function unansweredQuestions(cache: OfflinePracticeCache): OfflineQuestion[] {
  const answered = new Set(cache.answers_local.map((row) => row.question_id))
  return cache.questions.filter((question) => !answered.has(question.id))
}

export function recordLocalAnswer(
  cache: OfflinePracticeCache,
  body: AnswerBody,
  now: Date = new Date(),
): OfflinePracticeCache {
  const next: OfflineAnswer = {
    question_id: body.question_id,
    selected_index: body.selected_index ?? null,
    answered_boolean: body.answered_boolean ?? null,
    answered_text: body.answered_text ?? null,
    answered_at: now.toISOString(),
  }
  return {
    ...cache,
    answers_local: [
      ...cache.answers_local.filter((row) => row.question_id !== body.question_id),
      next,
    ],
  }
}

export function localVerdict(question: OfflineQuestion): Verdict {
  return {
    is_correct: null,
    explanation: LOCAL_GRADE_NOTE,
    correct_index: null,
    correct_answer: null,
    model_answer: null,
    citation: question.citation,
  }
}

export function localReviewItems(cache: OfflinePracticeCache): ReviewItem[] {
  const byId = new Map(cache.answers_local.map((row) => [row.question_id, row]))
  return cache.questions
    .filter((question) => byId.has(question.id))
    .map((question) => {
      const answer = byId.get(question.id)
      return {
        question_id: question.id,
        type: question.type,
        stem: question.stem,
        options: question.options,
        is_correct: null,
        selected_index: answer?.selected_index ?? null,
        answered_boolean: answer?.answered_boolean ?? null,
        answered_text: answer?.answered_text ?? null,
        correct_index: null,
        correct_answer: null,
        model_answer: null,
        explanation: LOCAL_GRADE_NOTE,
        citation: question.citation,
        answered_at: answer?.answered_at ?? cache.cached_at,
      }
    })
}

export function pendingSyncBodies(cache: OfflinePracticeCache): AnswerBody[] {
  return cache.answers_local.map((row) => ({
    question_id: row.question_id,
    selected_index: row.selected_index,
    answered_boolean: row.answered_boolean,
    answered_text: row.answered_text,
  }))
}
