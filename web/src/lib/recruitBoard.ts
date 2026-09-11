/** Soft timer and board-end strings. Display only — never auto-submit. */

export const SOFT_TIMER_SECONDS = 120

export const BOARD_FRAMING =
  'Board complete. Notes held until the end on purpose — same as a real board.'

export const HOLDING_HEADING = 'Working on the notes held until the end…'

export const NOTES_BLOCKED_COPY =
  "These notes can't be finished from that recording. Leave to abandon this board — no notes will be released."

export function formatSoftTimer(remainingSeconds: number): string {
  const clamped = Math.max(0, Math.floor(remainingSeconds))
  const minutes = Math.floor(clamped / 60)
  const seconds = clamped % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

/** Progress dots. Upcoming questions are not named. */
export function boardProgressLabel(index: number, total = 5): string {
  return `Question ${index} of ${total}`
}

/** Holding must not fall back to “Loading…” just because question_text is empty. */
export function boardPromptHeading(phase: string, questionText: string): string {
  if (phase === 'holding') return HOLDING_HEADING
  const text = questionText.trim()
  if (text) return text
  if (phase === 'blocked' || phase === 'summary' || phase === 'milestone') return ''
  return 'Loading…'
}

export function shouldPostAbandon(status: string): boolean {
  return status === 'in_progress' || status === 'scoring'
}

/** Leave during holding: a just-completed board keeps its summary. */
export function leaveAfterAbandon(status: string): 'summary' | 'leave' {
  return status === 'completed' ? 'summary' : 'leave'
}

export function shouldShowNotesBlockedPath(input: {
  notes_blocked?: boolean
  attemptStatus?: string
  attemptFailed?: boolean
}): boolean {
  if (input.notes_blocked) return true
  if (input.attemptStatus === 'critique_failed') return true
  return Boolean(input.attemptFailed)
}
