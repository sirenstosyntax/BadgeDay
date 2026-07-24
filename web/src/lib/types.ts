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

/**
 * Entitlement as the app sees it. `entitled` is the only field a gate should read — it is
 * the same OR the server computes (an active subscription, or an unexpired pass), so the
 * browser never re-derives "are they allowed" from status and expiry and never disagrees
 * with the server about it. `subscription_status` and `access_expires_at` are for telling
 * the candidate *what* they have, not for deciding whether they may act.
 */
export type Account = {
  id: string
  email: string | null
  entitled: boolean
  subscription_status: 'none' | 'active' | 'past_due' | 'canceled'
  access_expires_at: string | null
}

/** The two things a candidate can buy. Named, not priced — the price lives in Stripe. */
export type Plan = 'monthly' | 'intensive_90day'

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

/**
 * One answered question. Carries the answer, unlike `QuizQuestion` — safe because the
 * view behind it joins through responses, so nothing unanswered can appear here.
 *
 * `citation` arrives already rendered. The browser does not assemble it from section_path
 * and page numbers, deliberately: the same string is shown on answering and again on
 * review, and a second implementation is a second chance to point at the wrong section.
 */
export type ReviewItem = {
  question_id: string
  type: QuestionType
  stem: string
  options: string[] | null
  is_correct: boolean | null
  selected_index: number | null
  answered_boolean: boolean | null
  answered_text: string | null
  correct_index: number | null
  correct_answer: boolean | null
  model_answer: string | null
  explanation: string
  citation: string
  answered_at: string
}
