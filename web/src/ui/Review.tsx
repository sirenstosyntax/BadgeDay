import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { ReviewItem } from '../lib/types'

function Mark({ item }: { item: ReviewItem }) {
  if (item.is_correct === null) {
    return <span className="text-xs text-stone-500 dark:text-stone-400">Self-assessed</span>
  }
  return item.is_correct ? (
    <span className="text-xs text-emerald-700 dark:text-emerald-400">Correct</span>
  ) : (
    <span className="text-xs text-red-700 dark:text-red-400">Missed</span>
  )
}

/** What the candidate actually put down, in the same shape the question was asked. */
function GivenAnswer({ item }: { item: ReviewItem }) {
  if (item.type === 'multiple_choice' && item.options) {
    const chosen = item.selected_index !== null ? item.options[item.selected_index] : '—'
    const right = item.correct_index !== null ? item.options[item.correct_index] : '—'
    return (
      <dl className="space-y-1 text-sm">
        <div>
          <dt className="inline text-stone-500 dark:text-stone-400">You answered: </dt>
          <dd className="inline">{chosen}</dd>
        </div>
        {!item.is_correct && (
          <div>
            <dt className="inline text-stone-500 dark:text-stone-400">Correct answer: </dt>
            <dd className="inline">{right}</dd>
          </div>
        )}
      </dl>
    )
  }

  if (item.type === 'true_false') {
    return (
      <dl className="space-y-1 text-sm">
        <div>
          <dt className="inline text-stone-500 dark:text-stone-400">You answered: </dt>
          <dd className="inline">{item.answered_boolean ? 'True' : 'False'}</dd>
        </div>
        {!item.is_correct && (
          <div>
            <dt className="inline text-stone-500 dark:text-stone-400">Correct answer: </dt>
            <dd className="inline">{item.correct_answer ? 'True' : 'False'}</dd>
          </div>
        )}
      </dl>
    )
  }

  return (
    <dl className="space-y-1 text-sm">
      <div>
        <dt className="text-stone-500 dark:text-stone-400">You wrote:</dt>
        <dd className="whitespace-pre-wrap">{item.answered_text || '—'}</dd>
      </div>
      <div>
        <dt className="text-stone-500 dark:text-stone-400">Model answer:</dt>
        <dd>{item.model_answer}</dd>
      </div>
    </dl>
  )
}

export function Review({ sessionId, onDone }: { sessionId: string; onDone: () => void }) {
  const [items, setItems] = useState<ReviewItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .practice
      .review(sessionId)
      .then(setItems)
      .catch((caught: unknown) =>
        setError(caught instanceof Error ? caught.message : 'Could not load the review.'),
      )
  }, [sessionId])

  if (error) return <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
  if (!items) return <p className="text-sm text-stone-500">Loading…</p>

  const graded = items.filter((item) => item.is_correct !== null)
  const right = graded.filter((item) => item.is_correct).length

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Session review</h2>
          <p className="text-sm text-stone-600 dark:text-stone-400">
            {graded.length > 0
              ? `${right} of ${graded.length} graded questions correct`
              : 'Nothing auto-graded in this set'}
            {items.length > graded.length &&
              ` · ${items.length - graded.length} to self-assess`}
          </p>
        </div>
        <button
          onClick={onDone}
          className="shrink-0 rounded-lg border border-stone-300 px-3 py-2 text-sm dark:border-stone-700"
        >
          Done
        </button>
      </div>

      <ul className="space-y-4">
        {items.map((item) => (
          <li
            key={item.question_id}
            className="space-y-3 rounded-lg border border-stone-200 p-4 dark:border-stone-800"
          >
            <div className="flex items-start justify-between gap-4">
              <p className="font-medium">{item.stem}</p>
              <Mark item={item} />
            </div>

            <GivenAnswer item={item} />

            <p className="text-sm text-stone-700 dark:text-stone-300">{item.explanation}</p>

            {/* A location to open their own document to, never a quotation of it. */}
            <p className="text-xs text-stone-500 dark:text-stone-400">Source: {item.citation}</p>
          </li>
        ))}
      </ul>
    </div>
  )
}
