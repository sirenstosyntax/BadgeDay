/**
 * Mirrors the API's response models.
 *
 * `QuizQuestion` has no answer fields, and that is not an omission for brevity — the
 * server cannot send them. Migration 0004 revoked those columns from the candidate's
 * role, so the only route by which an answer reaches this app is `Verdict`, returned
 * after an answer has been committed. If a field like `correct_index` ever seems to be
 * missing here, the fix is not to add it.
 */

export type DocumentStatus =
  | 'pending'
  | 'analyzing'
  | 'chunking'
  | 'generating'
  | 'ready'
  | 'failed'

export type DocumentRecord = {
  id: string
  user_id: string
  filename: string
  storage_path: string
  byte_size: number | null
  page_count: number | null
  status: DocumentStatus
  error: string | null
  created_at: string
  updated_at: string
}

export type QuestionType = 'multiple_choice' | 'true_false' | 'short_answer'

export type QuizQuestion = {
  id: string
  document_id: string
  chunk_id: string
  type: QuestionType
  stem: string
  options: string[] | null
}

export type NextQuestion = {
  question: QuizQuestion | null
  remaining: number
}

/** What comes back once an answer is committed — including, only now, the answer. */
export type Verdict = {
  is_correct: boolean | null
  explanation: string
  correct_index: number | null
  correct_answer: boolean | null
  model_answer: string | null
  citation: string
}

export type PracticeSession = {
  id: string
  user_id: string
  document_id: string | null
  created_at: string
  completed_at: string | null
}

export type Coverage = {
  document_id: string
  sections_total: number
  sections_exercised: number
  percent: number
}

export type ReviewRow = {
  question_id: string
  session_id: string
  document_id: string
  type: QuestionType
  stem: string
  options: string[] | null
  correct_index: number | null
  correct_answer: boolean | null
  model_answer: string | null
  explanation: string
  is_correct: boolean | null
  selected_index: number | null
  answered_boolean: boolean | null
  answered_text: string | null
  answered_at: string
  section_path: string[]
  section_title: string | null
  page_start: number
  page_end: number
}
