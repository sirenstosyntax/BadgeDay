import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { AnswerBody } from '../lib/api'
import type { QuizQuestion, Verdict } from '../lib/types'

/**
 * One question at a time, then the verdict.
 *
 * The verdict is a separate piece of state from the question and only exists after the
 * answer has been committed, which mirrors what the server will do regardless: nothing in
 * `QuizQuestion` can tell you the answer, because the columns holding it were revoked from
 * this candidate's role. The UI is not choosing to withhold anything — there is nothing
 * here to withhold.
 */
export function Quiz({ sessionId, onDone }: { sessionId: string; onDone: () => void }) {
  const [question, setQuestion] = useState<QuizQuestion | null>(null)
  const [remaining, setRemaining] = useState(0)
  const [verdict, setVerdict] = useState<Verdict | null>(null)
  const [choice, setChoice] = useState<number | null>(null)
  const [text, setText] = useState('')
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [finished, setFinished] = useState(false)

  const load = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const next = await api.practice.next(sessionId)
      setQuestion(next.question)
      setRemaining(next.remaining)
      setFinished(next.question === null)
      setVerdict(null)
      setChoice(null)
      setText('')
      setSaved(false)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load the next question.')
    } finally {
      setBusy(false)
    }
  }, [sessionId])

  useEffect(() => {
    void load()
  }, [load])

  async function answer(body: Omit<AnswerBody, 'question_id'>) {
    if (!question || busy) return
    setBusy(true)
    setError(null)
    try {
      setVerdict(await api.practice.answer(sessionId, { question_id: question.id, ...body }))
      // Decrement here rather than waiting for the next load. The count is read once per
      // question, so without this the candidate reads the verdict for the first of three
      // under a heading that still says three left.
      setRemaining((count) => Math.max(0, count - 1))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'That answer did not save.')
    } finally {
      setBusy(false)
    }
  }

  async function toggleSave() {
    if (!question) return
    try {
      if (saved) await api.saved.remove(question.id)
      else await api.saved.add(question.id)
      setSaved(!saved)
    } catch {
      /* Saving is a convenience; a failure here must not derail the drill. */
    }
  }

  if (finished) {
    return (
      <div className="space-y-4 text-center">
        <h2 className="text-lg font-semibold">Session complete</h2>
        <p className="text-sm text-stone-600 dark:text-stone-400">
          Every question in this set has been answered.
        </p>
        <button
          onClick={() => {
            void api.practice.complete(sessionId).catch(() => {})
            onDone()
          }}
          className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white dark:bg-stone-100 dark:text-stone-900"
        >
          Back to documents
        </button>
      </div>
    )
  }

  if (!question) {
    return <p className="text-sm text-stone-500">Loading…</p>
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between text-sm text-stone-500 dark:text-stone-400">
        <button onClick={onDone} className="hover:underline">
          ← Leave session
        </button>
        <span>{remaining} left</span>
      </div>

      <h2 className="text-lg font-medium">{question.stem}</h2>

      {question.type === 'multiple_choice' && question.options && (
        <div className="space-y-2">
          {question.options.map((option, index) => {
            const isAnswer = verdict !== null && verdict.correct_index === index
            const isMine = choice === index
            return (
              <button
                key={index}
                disabled={verdict !== null || busy}
                onClick={() => {
                  setChoice(index)
                  void answer({ selected_index: index })
                }}
                className={`w-full rounded-lg border px-3 py-2 text-left text-sm ${
                  isAnswer
                    ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-950'
                    : isMine && verdict
                      ? 'border-red-500 bg-red-50 dark:bg-red-950'
                      : 'border-stone-300 dark:border-stone-700'
                }`}
              >
                {option}
              </button>
            )
          })}
        </div>
      )}

      {question.type === 'true_false' && (
        <div className="flex gap-2">
          {[true, false].map((value) => (
            <button
              key={String(value)}
              disabled={verdict !== null || busy}
              onClick={() => void answer({ answered_boolean: value })}
              className={`flex-1 rounded-lg border px-3 py-2 text-sm ${
                verdict !== null && verdict.correct_answer === value
                  ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-950'
                  : 'border-stone-300 dark:border-stone-700'
              }`}
            >
              {value ? 'True' : 'False'}
            </button>
          ))}
        </div>
      )}

      {question.type === 'short_answer' && (
        <div className="space-y-2">
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            disabled={verdict !== null}
            rows={4}
            placeholder="Answer in your own words."
            className="w-full rounded-lg border border-stone-300 bg-white p-3 text-sm dark:border-stone-700 dark:bg-stone-900"
          />
          {verdict === null && (
            <button
              disabled={!text.trim() || busy}
              onClick={() => void answer({ answered_text: text })}
              className="rounded-lg bg-stone-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50 dark:bg-stone-100 dark:text-stone-900"
            >
              Submit
            </button>
          )}
        </div>
      )}

      {verdict && (
        <div className="space-y-3 rounded-lg border border-stone-200 p-4 dark:border-stone-800">
          <p className="font-medium">
            {verdict.is_correct === null
              ? 'Compare with the model answer'
              : verdict.is_correct
                ? 'Correct'
                : 'Not quite'}
          </p>

          {verdict.model_answer && (
            <p className="text-sm text-stone-700 dark:text-stone-300">
              <span className="font-medium">Model answer: </span>
              {verdict.model_answer}
            </p>
          )}

          <p className="text-sm text-stone-700 dark:text-stone-300">{verdict.explanation}</p>

          {/* The citation is the product. It is never a quotation of the source — it is a
              location the candidate can open their own document to and read. */}
          <p className="text-xs text-stone-500 dark:text-stone-400">
            Source: {verdict.citation}
          </p>

          <div className="flex items-center justify-between pt-2">
            <button onClick={() => void toggleSave()} className="text-sm hover:underline">
              {saved ? '★ Saved' : '☆ Save for later'}
            </button>
            <button
              onClick={() => void load()}
              className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white dark:bg-stone-100 dark:text-stone-900"
            >
              Next question
            </button>
          </div>
        </div>
      )}

      {error && <p className="text-sm text-red-700 dark:text-red-400">{error}</p>}
    </div>
  )
}
