import { supabase } from './supabase'
import type {
  Account,
  Coverage,
  DocumentRecord,
  NextQuestion,
  Plan,
  PracticeSession,
  QuizQuestion,
  ReviewItem,
  Verdict,
} from './types'

const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  // Declared and assigned rather than a constructor parameter property: this tsconfig
  // sets erasableSyntaxOnly, so TypeScript-only syntax that emits runtime code is out.
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/**
 * The token is read from the session on every request rather than captured once, because
 * supabase-js rotates it in the background. A token held in a module variable works
 * perfectly until the first refresh, then fails as 401s that look like a session expiring
 * far too early.
 */
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (!token) throw new ApiError(401, 'Not signed in.')

  const headers = new Headers(init.headers)
  headers.set('Authorization', `Bearer ${token}`)
  // FormData sets its own multipart boundary; setting Content-Type here would overwrite
  // it with one that has no boundary, and the upload would fail as a malformed body.
  if (init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${BASE}${path}`, { ...init, headers })
  if (response.status === 204) return undefined as T

  const body = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(response.status, body?.detail ?? response.statusText)
  }
  return body as T
}

export const api = {
  account: {
    me: () => request<Account>('/me'),
  },

  billing: {
    // Both return a Stripe URL the browser navigates to. They are POSTs, not links,
    // because each mints a fresh single-use session server-side against the candidate's
    // token — there is no URL to hardcode.
    checkout: (plan: Plan) =>
      request<{ url: string }>('/billing/checkout', {
        method: 'POST',
        body: JSON.stringify({ plan }),
      }),
    portal: () => request<{ url: string }>('/billing/portal', { method: 'POST' }),
  },

  documents: {
    list: () => request<DocumentRecord[]>('/documents'),
    get: (id: string) => request<DocumentRecord>(`/documents/${id}`),
    remove: (id: string) => request<void>(`/documents/${id}`, { method: 'DELETE' }),
    upload: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return request<DocumentRecord>('/documents', { method: 'POST', body: form })
    },
  },

  practice: {
    start: (documentId: string | null) =>
      request<PracticeSession>('/sessions', {
        method: 'POST',
        body: JSON.stringify({ document_id: documentId }),
      }),
    next: (sessionId: string) => request<NextQuestion>(`/sessions/${sessionId}/next`),
    answer: (sessionId: string, answer: AnswerBody) =>
      request<Verdict>(`/sessions/${sessionId}/responses`, {
        method: 'POST',
        body: JSON.stringify(answer),
      }),
    review: (sessionId: string) => request<ReviewItem[]>(`/sessions/${sessionId}/review`),
    complete: (sessionId: string) =>
      request<PracticeSession>(`/sessions/${sessionId}/complete`, { method: 'POST' }),
  },

  coverage: (documentId?: string) =>
    request<Coverage[]>(`/coverage${documentId ? `?document_id=${documentId}` : ''}`),

  saved: {
    list: () => request<QuizQuestion[]>('/saved'),
    add: (questionId: string) => request<void>(`/saved/${questionId}`, { method: 'PUT' }),
    remove: (questionId: string) => request<void>(`/saved/${questionId}`, { method: 'DELETE' }),
  },
}

export type AnswerBody = {
  question_id: string
  selected_index?: number | null
  answered_boolean?: boolean | null
  answered_text?: string | null
}
