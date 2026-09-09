import { useEffect, useRef, useState } from 'react'
import { api, ApiError, type RecruitResult } from '../lib/api'

const POLL_MS = 2000
const POLL_TIMEOUT_MS = 15 * 60 * 1000

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** POST returns 202; keep asking GET until the worker writes a terminal status. */
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

type Phase = 'loading' | 'ready' | 'blocked' | 'recording' | 'recorded' | 'submitting' | 'done'

function pickMime(): string {
  const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4']
  return types.find((type) => MediaRecorder.isTypeSupported(type)) ?? ''
}

function filenameFor(mime: string): string {
  if (mime.includes('mp4')) return 'answer.m4a'
  return 'answer.webm'
}

/** Empty HTTP/2 statusText and a missing detail must not hide the failed submit. */
export function submitErrorMessage(
  caught: unknown,
  fallback = 'That answer could not be critiqued.',
): string {
  if (caught instanceof Error && caught.message.trim()) return caught.message.trim()
  return fallback
}

/**
 * One C2 spoken question. Record once, submit, read the candidate critique.
 * The server never sends a score on this path; this screen does not invent one.
 */
export function Recruit({ onDone }: { onDone: () => void }) {
  const [phase, setPhase] = useState<Phase>('loading')
  const [question, setQuestion] = useState('')
  const [lines, setLines] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [persistFailed, setPersistFailed] = useState(false)

  const chunks = useRef<Blob[]>([])
  const recorder = useRef<MediaRecorder | null>(null)
  const stream = useRef<MediaStream | null>(null)
  const blob = useRef<Blob | null>(null)
  const left = useRef(false)

  useEffect(() => {
    left.current = false
    void api.recruit
      .question()
      .then((issued) => {
        if (left.current) return
        setQuestion(issued.question_text)
        setPhase('ready')
      })
      .catch((caught: unknown) => {
        if (left.current) return
        setError(submitErrorMessage(caught, 'Could not load the question.'))
        setPhase('blocked')
      })
    return () => {
      left.current = true
      stopTracks()
    }
  }, [])

  function stopTracks() {
    stream.current?.getTracks().forEach((track) => track.stop())
    stream.current = null
  }

  async function startRecording() {
    // First take only. A finished recording stays in `recorded`; this is not a retry.
    if (!question || phase !== 'ready') return
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
      setPhase(question ? 'ready' : 'blocked')
    }
  }

  function stopRecording() {
    if (recorder.current && recorder.current.state !== 'inactive') {
      recorder.current.stop()
    }
  }

  async function submit() {
    if (!blob.current || phase === 'submitting') return
    setPhase('submitting')
    setError(null)
    setPersistFailed(false)
    try {
      const mime = blob.current.type || 'audio/webm'
      const file = new File([blob.current], filenameFor(mime), { type: mime })
      const accepted = await api.recruit.attempt(file)
      if (!accepted.attempt_id) {
        throw new ApiError(502, 'That answer was accepted but no attempt id came back.')
      }
      const result = await pollRecruitAttempt(accepted.attempt_id, () => left.current)
      if (left.current) return
      setLines(result.lines)
      setPersistFailed(result.failed && result.status === 'completed')
      if (result.status === 'critique_failed') {
        setError(result.failure?.trim() || 'That answer could not be critiqued.')
      }
      setPhase('done')
    } catch (caught) {
      setError(submitErrorMessage(caught))
      setPhase('recorded')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between text-sm text-stone-500 dark:text-stone-400">
        <button onClick={onDone} className="hover:underline">
          ← Leave
        </button>
      </div>

      <h2 className="text-lg font-medium">{question || 'Loading…'}</h2>
      {question && (
        <p className="text-sm text-stone-600 dark:text-stone-400">
          Answer out loud. You’ll get notes on what went well and what to improve.
        </p>
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

      {/* One take. No re-record — CLAUDE.md binding constraint. */}
      {phase === 'recorded' && (
        <button
          onClick={() => void submit()}
          className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white dark:bg-stone-100 dark:text-stone-900"
        >
          Submit
        </button>
      )}

      {phase === 'submitting' && (
        <p className="text-sm text-stone-500">Working on your critique…</p>
      )}

      {phase === 'done' && (
        <div className="space-y-3 rounded-lg border border-stone-200 p-4 dark:border-stone-800">
          {lines.map((line, index) =>
            line === '' ? (
              <div key={index} className="h-2" />
            ) : (
              <p key={index} className="text-sm text-stone-800 dark:text-stone-200">
                {line}
              </p>
            ),
          )}
          {persistFailed && (
            <p className="text-sm text-stone-500">
              The critique is above. Saving it to your history did not finish.
            </p>
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
    </div>
  )
}
