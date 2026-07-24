import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { QuizQuestion } from '../lib/types'

const TYPE_LABELS: Record<QuizQuestion['type'], string> = {
  multiple_choice: 'Multiple choice',
  true_false: 'True/false',
  short_answer: 'Short answer',
}

/**
 * Questions flagged to come back to.
 *
 * Deliberately just the questions — no answers, no explanations. Not a UI choice: these
 * come from the same endpoint that serves the quiz, and it cannot return an answer. That
 * turns out to be exactly right for what this list is for. A candidate saves a question
 * because they want another go at it, and a list that showed the answer beside each one
 * would be a list they can only read, never re-attempt.
 */
export function Saved({ onDone }: { onDone: () => void }) {
  const [questions, setQuestions] = useState<QuizQuestion[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setQuestions(await api.saved.list())
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load your saved questions.')
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function remove(questionId: string) {
    setQuestions((current) => current?.filter((q) => q.id !== questionId) ?? null)
    try {
      await api.saved.remove(questionId)
    } catch {
      // Put it back: the row vanished optimistically, and leaving it gone would tell the
      // candidate something was unsaved when it is still saved.
      void refresh()
    }
  }

  if (error) return <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
  if (!questions) return <p className="text-sm text-stone-500">Loading…</p>

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Saved questions</h2>
          <p className="text-sm text-stone-600 dark:text-stone-400">
            Flagged to come back to. They stay here until you unsave them.
          </p>
        </div>
        <button
          onClick={onDone}
          className="shrink-0 rounded-lg border border-stone-300 px-3 py-2 text-sm dark:border-stone-700"
        >
          Done
        </button>
      </div>

      {questions.length === 0 ? (
        <p className="rounded-lg border border-dashed border-stone-300 p-8 text-center text-sm text-stone-500 dark:border-stone-700">
          Nothing saved yet. Star a question during practice to keep it here.
        </p>
      ) : (
        <ul className="divide-y divide-stone-200 rounded-lg border border-stone-200 dark:divide-stone-800 dark:border-stone-800">
          {questions.map((question) => (
            <li key={question.id} className="flex items-start gap-4 p-4">
              <div className="min-w-0 flex-1">
                <p className="text-sm">{question.stem}</p>
                <p className="mt-1 text-xs text-stone-500 dark:text-stone-400">
                  {TYPE_LABELS[question.type]}
                </p>
              </div>
              <button
                onClick={() => void remove(question.id)}
                className="shrink-0 text-sm text-stone-500 hover:text-red-700 dark:hover:text-red-400"
              >
                Unsave
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
