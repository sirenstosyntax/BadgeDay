import { useEffect, useRef, useState } from 'react'
import {
  api,
  ApiError,
  type RecruitBoardView,
  type RecruitQuestionExhausted,
  type RecruitResult,
} from '../lib/api'
import {
  BOARD_FRAMING,
  NOTES_BLOCKED_COPY,
  SOFT_TIMER_SECONDS,
  boardProgressLabel,
  boardPromptHeading,
  formatSoftTimer,
  leaveAfterAbandon,
  shouldPostAbandon,
  shouldShowNotesBlockedPath,
} from '../lib/recruitBoard'
import type { Account } from '../lib/types'
import { RecruitMilestone } from './RecruitMilestone'

const POLL_MS = 2000
const POLL_TIMEOUT_MS = 15 * 60 * 1000

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function pollRecruitAttempt(
  attemptId: string,
  isCancelled: () => boolean = () => false,
): Promise<RecruitResult> {
  const started = Date.now()
  while (!isCancelled()) {
    const view = await api.recruit.get(attemptId)
    if (view.status === 'completed' || view.status === 'critique_failed') {
      return view
    }
    if (Date.now() - started > POLL_TIMEOUT_MS) {
      throw new ApiError(
        504,
        'That critique is taking too long. Leave and open Oral board again in a moment.',
      )
    }
    await sleep(POLL_MS)
  }
  throw new ApiError(499, 'Left before the critique finished.')
}

async function pollBoardComplete(
  boardId: string,
  isCancelled: () => boolean = () => false,
): Promise<RecruitBoardView> {
  const started = Date.now()
  while (!isCancelled()) {
    const board = await api.recruit.board(boardId)
    if (
      board.status === 'completed' ||
      board.status === 'abandoned' ||
      board.notes_blocked
    ) {
      return board
    }
    if (Date.now() - started > POLL_TIMEOUT_MS) {
      throw new ApiError(
        504,
        'Those notes are taking too long. Leave and open Oral board again in a moment.',
      )
    }
    await sleep(POLL_MS)
  }
  throw new ApiError(499, 'Left before the notes were ready.')
}

type Phase =
  | 'loading'
  | 'ready'
  | 'milestone'
  | 'blocked'
  | 'recording'
  | 'recorded'
  | 'submitting'
  | 'holding'
  | 'summary'

function pickMime(): string {
  const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']
  return types.find((type) => MediaRecorder.isTypeSupported(type)) ?? ''
}

function filenameFor(mime: string): string {
  if (mime.includes('mp4')) return 'answer.m4a'
  return 'answer.webm'
}

export function submitErrorMessage(
  caught: unknown,
  fallback = 'That answer could not be critiqued.',
): string {
  if (caught instanceof Error && caught.message.trim()) return caught.message.trim()
  return fallback
}

/**
 * Five-question board. Record once per question. Notes stay held until the
 * last answer is in — same as a real board. Soft timer is display only.
 */
export function Recruit({
  onDone,
  account,
  onOpenAccount,
  onNeedsAccess,
}: {
  onDone: () => void
  account: Account | null
  onOpenAccount: () => void
  onNeedsAccess?: () => void
}) {
  const [phase, setPhase] = useState<Phase>('loading')
  const [board, setBoard] = useState<RecruitBoardView | null>(null)
  const [exhausted, setExhausted] = useState<RecruitQuestionExhausted | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [needsPlan, setNeedsPlan] = useState(false)
  const [remaining, setRemaining] = useState(SOFT_TIMER_SECONDS)

  const chunks = useRef<Blob[]>([])
  const recorder = useRef<MediaRecorder | null>(null)
  const stream = useRef<MediaStream | null>(null)
  const blob = useRef<Blob | null>(null)
  const left = useRef(false)
  const abandoned = useRef(false)

  useEffect(() => {
    left.current = false
    void api.recruit
      .startBoard()
      .then((started) => {
        if (left.current) return
        setBoard(started)
        setRemaining(started.soft_timer_seconds || SOFT_TIMER_SECONDS)
        if (started.status === 'completed') {
          setPhase('summary')
          return
        }
        if (shouldShowNotesBlockedPath({ notes_blocked: started.notes_blocked })) {
          setError(NOTES_BLOCKED_COPY)
          setPhase('blocked')
          return
        }
        if (started.status === 'scoring') {
          setPhase('holding')
          return
        }
        setPhase('ready')
      })
      .catch((caught: unknown) => {
        if (left.current) return
        if (caught instanceof ApiError && caught.status === 402) {
          setNeedsPlan(true)
          onNeedsAccess?.()
          setError(submitErrorMessage(caught, 'Your free oral-board session is used.'))
          setPhase('blocked')
          return
        }
        if (caught instanceof ApiError && caught.status === 409) {
          void api.recruit
            .question()
            .then((issued) => {
              if (issued.state === 'exhausted') {
                setExhausted(issued)
                setPhase('milestone')
              } else {
                setError(submitErrorMessage(caught, 'Could not start the board.'))
                setPhase('blocked')
              }
            })
            .catch((inner: unknown) => {
              setError(submitErrorMessage(inner, 'Could not start the board.'))
              setPhase('blocked')
            })
          return
        }
        setError(submitErrorMessage(caught, 'Could not start the board.'))
        setPhase('blocked')
      })
    return () => {
      left.current = true
      stopTracks()
    }
  }, [])

  // Soft timer. Display only — hitting 0:00 does not submit.
  useEffect(() => {
    if (phase !== 'ready' && phase !== 'recording' && phase !== 'recorded') return
    const tick = window.setInterval(() => {
      setRemaining((value) => Math.max(0, value - 1))
    }, 1000)
    return () => window.clearInterval(tick)
  }, [phase, board?.question_index])

  useEffect(() => {
    if (phase !== 'holding' || !board?.board_id) return
    void pollBoardComplete(board.board_id, () => left.current)
      .then((finished) => {
        if (left.current) return
        setBoard(finished)
        if (finished.status === 'completed') {
          setPhase('summary')
          return
        }
        if (shouldShowNotesBlockedPath({ notes_blocked: finished.notes_blocked })) {
          setError(NOTES_BLOCKED_COPY)
          setPhase('blocked')
          return
        }
        setPhase('blocked')
      })
      .catch((caught: unknown) => {
        if (left.current) return
        setError(submitErrorMessage(caught, 'Those notes could not be finished.'))
        setPhase('blocked')
      })
  }, [phase, board?.board_id])

  function stopTracks() {
    stream.current?.getTracks().forEach((track) => track.stop())
    stream.current = null
  }

  async function leave() {
    if (board && !abandoned.current && shouldPostAbandon(board.status)) {
      abandoned.current = true
      try {
        const ended = await api.recruit.abandon(board.board_id)
        if (leaveAfterAbandon(ended.status) === 'summary') {
          setBoard(ended)
          setPhase('summary')
          return
        }
      } catch {
        // Leaving still leaves; the server will treat an unfinished board as abandoned
        // the next time they start, or they can reopen this one.
      }
    }
    onDone()
  }

  async function startRecording() {
    if (!board?.question_text || phase !== 'ready') return
    setError(null)
    blob.current = null
    chunks.current = []
    try {
      const mic = await navigator.mediaDevices.getUserMedia({ audio: true })
      stream.current = mic
      const mime = pickMime()
      const rec = mime ? new MediaRecorder(mic, { mimeType: mime }) : new MediaRecorder(mic)
      recorder.current = rec
      rec.ondataavailable = (event) => {
        if (event.data.size) chunks.current.push(event.data)
      }
      rec.onstop = () => {
        blob.current = new Blob(chunks.current, { type: rec.mimeType || 'audio/webm' })
        stopTracks()
        setPhase('recorded')
      }
      rec.start()
      setPhase('recording')
    } catch {
      setError('The microphone was blocked. Allow it in the browser and try again.')
      setPhase(board?.question_text ? 'ready' : 'blocked')
    }
  }

  function stopRecording() {
    if (recorder.current && recorder.current.state !== 'inactive') {
      recorder.current.stop()
    }
  }

  async function submit() {
    if (!blob.current || !board || phase === 'submitting') return
    setPhase('submitting')
    setError(null)
    try {
      const mime = blob.current.type || 'audio/webm'
      const file = new File([blob.current], filenameFor(mime), { type: mime })
      const accepted = await api.recruit.answer(board.board_id, file)
      if (!accepted.attempt_id) {
        throw new ApiError(502, 'That answer was accepted but no attempt id came back.')
      }
      await pollRecruitAttempt(accepted.attempt_id, () => left.current)
      if (left.current) return
      const next = await api.recruit.board(board.board_id)
      if (left.current) return
      setBoard(next)
      blob.current = null
      if (next.status === 'completed') {
        setPhase('summary')
        return
      }
      if (shouldShowNotesBlockedPath({ notes_blocked: next.notes_blocked })) {
        setError(NOTES_BLOCKED_COPY)
        setPhase('blocked')
        return
      }
      if (next.status === 'scoring' || next.question_index >= 5 && !next.question_text) {
        setPhase('holding')
        return
      }
      setRemaining(next.soft_timer_seconds || SOFT_TIMER_SECONDS)
      setPhase('ready')
    } catch (caught) {
      setError(submitErrorMessage(caught))
      setPhase('recorded')
    }
  }

  const question = board?.question_text || ''
  const index = board?.question_index || 1
  const heading = boardPromptHeading(phase, question)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between text-sm text-stone-500 dark:text-stone-400">
        <button onClick={() => void leave()} className="hover:underline">
          ← Leave
        </button>
        {phase !== 'milestone' && phase !== 'summary' && board && (
          <span>{boardProgressLabel(index, board.board_size)}</span>
        )}
      </div>

      {phase === 'milestone' && exhausted && (
        <RecruitMilestone
          answeredCount={exhausted.answered_count}
          bankSize={exhausted.bank_size}
          account={account}
          onOpenAccount={onOpenAccount}
        />
      )}

      {phase !== 'milestone' && phase !== 'summary' && (
        <>
          <div className="flex justify-center gap-2" aria-hidden="true">
            {[1, 2, 3, 4, 5].map((slot) => (
              <span
                key={slot}
                className={
                  slot < index
                    ? 'h-2 w-2 rounded-full bg-stone-700 dark:bg-stone-300'
                    : slot === index
                      ? 'h-2 w-2 rounded-full bg-stone-900 dark:bg-stone-100'
                      : 'h-2 w-2 rounded-full bg-stone-300 dark:bg-stone-700'
                }
              />
            ))}
          </div>
          {heading && <h2 className="text-lg font-medium">{heading}</h2>}
          {question && phase !== 'holding' && (
            <p className="text-sm text-stone-600 dark:text-stone-400">
              Answer out loud. Notes are held until the end of the board — same as a real
              board.
            </p>
          )}
          {(phase === 'ready' || phase === 'recording' || phase === 'recorded') && (
            <p className="text-sm tabular-nums text-stone-500" data-testid="soft-timer">
              Soft timer {formatSoftTimer(remaining)} — guidance only. It will not submit
              for you.
            </p>
          )}
        </>
      )}

      {phase === 'ready' && question && (
        <button
          onClick={() => void startRecording()}
          className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white dark:bg-stone-100 dark:text-stone-900"
        >
          Record answer
        </button>
      )}

      {phase === 'recording' && (
        <button
          onClick={stopRecording}
          className="rounded-lg bg-red-700 px-4 py-2 text-sm font-medium text-white"
        >
          Stop
        </button>
      )}

      {phase === 'recorded' && (
        <button
          onClick={() => void submit()}
          className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white dark:bg-stone-100 dark:text-stone-900"
        >
          Submit
        </button>
      )}

      {phase === 'submitting' && (
        <p className="text-sm text-stone-500">Saving that answer…</p>
      )}

      {phase === 'holding' && (
        <p className="text-sm text-stone-500">
          Board complete. Working on the notes held until the end…
        </p>
      )}

      {phase === 'summary' && board && (
        <div className="space-y-6">
          <p className="text-sm font-medium text-stone-800 dark:text-stone-200">
            {board.framing || BOARD_FRAMING}
          </p>
          {board.answers.map((answer) => (
            <div
              key={answer.question_index}
              className="space-y-3 rounded-lg border border-stone-200 p-4 dark:border-stone-800"
            >
              <p className="text-xs uppercase tracking-wide text-stone-500">
                Question {answer.question_index}
              </p>
              <p className="text-sm font-medium text-stone-800 dark:text-stone-200">
                {answer.question_text}
              </p>
              {answer.lines.map((line, lineIndex) =>
                line === '' ? (
                  <div key={lineIndex} className="h-2" />
                ) : (
                  <p key={lineIndex} className="text-sm text-stone-800 dark:text-stone-200">
                    {line}
                  </p>
                ),
              )}
            </div>
          ))}
          {board.c1_lines.length > 0 && (
            <div className="space-y-3 rounded-lg border border-stone-200 p-4 dark:border-stone-800">
              {board.c1_lines.map((line, lineIndex) =>
                line === '' ? (
                  <div key={lineIndex} className="h-2" />
                ) : (
                  <p key={lineIndex} className="text-sm text-stone-800 dark:text-stone-200">
                    {line}
                  </p>
                ),
              )}
            </div>
          )}
          <button
            onClick={onDone}
            className="rounded-lg border border-stone-300 px-4 py-2 text-sm dark:border-stone-700"
          >
            Done
          </button>
        </div>
      )}

      {error && <p className="text-sm text-red-700 dark:text-red-400">{error}</p>}
      {needsPlan && onNeedsAccess && (
        <button
          type="button"
          onClick={onNeedsAccess}
          className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white dark:bg-stone-100 dark:text-stone-900"
        >
          See plans
        </button>
      )}
    </div>
  )
}
