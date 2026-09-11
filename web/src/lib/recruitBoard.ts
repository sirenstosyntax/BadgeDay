/** Soft timer and board-end strings. Display only — never auto-submit. */

export const SOFT_TIMER_SECONDS = 120

export const BOARD_FRAMING =
  'Board complete. Notes held until the end on purpose — same as a real board.'

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
