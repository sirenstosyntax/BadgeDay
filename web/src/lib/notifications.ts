/**
 * Local notifications for the iOS shell. No remote push. Copy is a Red-route
 * placeholder until candidate-facing marketing tone is signed.
 *
 * Practice-streak last-practice date is device-local (see offlinePractice).
 */
import { callPlugin } from './capacitorBridge'
import { EXAM_DATE_KEY, NOTIFY_PROMPTED_KEY } from './deviceLocal'
import { deviceLocalDate, readLastPractice } from './offlinePractice'
import { currentHost, type CapacitorHost } from './platform'

export const STREAK_NOTIFICATION_ID = 4201
export const EXAM_WEEK_NOTIFICATION_ID = 4202
export const EXAM_DAY_NOTIFICATION_ID = 4203

/** Placeholder until Red signs reminder copy. BD-iOS-4.2 open question 1. */
export const STREAK_TITLE = 'BadgeDay'
export const STREAK_BODY = 'Time to practice on BadgeDay.'
export const EXAM_WEEK_TITLE = 'BadgeDay'
export const EXAM_WEEK_BODY = 'Your exam date is in seven days.'
export const EXAM_DAY_TITLE = 'BadgeDay'
export const EXAM_DAY_BODY = 'Exam day is today.'

const DEFAULT_STREAK_HOUR = 18
const EXAM_HOUR = 8

export type LocalNotification = {
  id: number
  title: string
  body: string
  schedule: { at: Date }
}

export function parseExamDate(raw: string | null): string | null {
  if (!raw) return null
  return /^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw : null
}

export function readExamDate(store: Pick<Storage, 'getItem'>): string | null {
  return parseExamDate(store.getItem(EXAM_DATE_KEY))
}

export function writeExamDate(store: Pick<Storage, 'setItem' | 'removeItem'>, date: string | null): void {
  if (!date) {
    store.removeItem(EXAM_DATE_KEY)
    return
  }
  store.setItem(EXAM_DATE_KEY, date)
}

export function atLocalHour(ymd: string, hour: number, now: Date = new Date()): Date {
  const [year, month, day] = ymd.split('-').map(Number)
  const when = new Date(now)
  when.setFullYear(year, month - 1, day)
  when.setHours(hour, 0, 0, 0)
  return when
}

function addDays(ymd: string, days: number): string {
  const [year, month, day] = ymd.split('-').map(Number)
  const date = new Date(year, month - 1, day + days)
  return deviceLocalDate(date)
}

export function streakFireAt(
  lastPractice: string | null,
  now: Date = new Date(),
  hour = DEFAULT_STREAK_HOUR,
): Date | null {
  if (!lastPractice) return null
  const today = deviceLocalDate(now)
  if (lastPractice >= today) return null
  const todayAt = atLocalHour(today, hour, now)
  if (todayAt.getTime() > now.getTime()) return todayAt
  return atLocalHour(addDays(today, 1), hour, now)
}

export function examNotifications(
  examDate: string | null,
  now: Date = new Date(),
): LocalNotification[] {
  if (!examDate) return []
  const today = deviceLocalDate(now)
  if (examDate < today) return []
  const out: LocalNotification[] = []
  const dayOf = atLocalHour(examDate, EXAM_HOUR, now)
  if (dayOf.getTime() > now.getTime()) {
    out.push({
      id: EXAM_DAY_NOTIFICATION_ID,
      title: EXAM_DAY_TITLE,
      body: EXAM_DAY_BODY,
      schedule: { at: dayOf },
    })
  }
  const weekBefore = addDays(examDate, -7)
  if (weekBefore > today || (weekBefore === today && atLocalHour(weekBefore, EXAM_HOUR, now) > now)) {
    const when = atLocalHour(weekBefore, EXAM_HOUR, now)
    if (when.getTime() > now.getTime()) {
      out.push({
        id: EXAM_WEEK_NOTIFICATION_ID,
        title: EXAM_WEEK_TITLE,
        body: EXAM_WEEK_BODY,
        schedule: { at: when },
      })
    }
  }
  return out
}

export function plannedNotifications(
  store: Pick<Storage, 'getItem'>,
  now: Date = new Date(),
): LocalNotification[] {
  const planned: LocalNotification[] = []
  const streakAt = streakFireAt(readLastPractice(store), now)
  if (streakAt) {
    planned.push({
      id: STREAK_NOTIFICATION_ID,
      title: STREAK_TITLE,
      body: STREAK_BODY,
      schedule: { at: streakAt },
    })
  }
  planned.push(...examNotifications(readExamDate(store), now))
  return planned
}

export async function requestNotificationPermission(
  host: CapacitorHost = currentHost(),
): Promise<'granted' | 'denied' | 'unavailable'> {
  try {
    const result = await callPlugin<{ display?: string }>(
      'LocalNotifications',
      'requestPermissions',
      undefined,
      host,
    )
    return result.display === 'granted' ? 'granted' : 'denied'
  } catch {
    return 'unavailable'
  }
}

export async function cancelNotificationIds(
  ids: number[],
  host: CapacitorHost = currentHost(),
): Promise<void> {
  try {
    await callPlugin(
      'LocalNotifications',
      'cancel',
      { notifications: ids.map((id) => ({ id })) },
      host,
    )
  } catch {
    /* Plugin missing or already cancelled — practice still works. */
  }
}

export async function scheduleLocalNotifications(
  notifications: LocalNotification[],
  host: CapacitorHost = currentHost(),
): Promise<void> {
  if (notifications.length === 0) return
  await callPlugin(
    'LocalNotifications',
    'schedule',
    {
      notifications: notifications.map((item) => ({
        id: item.id,
        title: item.title,
        body: item.body,
        schedule: { at: item.schedule.at, allowWhileIdle: true },
      })),
    },
    host,
  )
}

export async function refreshLocalNotifications(
  store: Pick<Storage, 'getItem'>,
  host: CapacitorHost = currentHost(),
  now: Date = new Date(),
): Promise<void> {
  await cancelNotificationIds(
    [STREAK_NOTIFICATION_ID, EXAM_WEEK_NOTIFICATION_ID, EXAM_DAY_NOTIFICATION_ID],
    host,
  )
  const planned = plannedNotifications(store, now)
  if (planned.length === 0) return
  try {
    await scheduleLocalNotifications(planned, host)
  } catch {
    /* Denial or missing plugin is non-blocking. */
  }
}

export function markNotifyPrompted(store: Pick<Storage, 'setItem'>): void {
  store.setItem(NOTIFY_PROMPTED_KEY, '1')
}

export function wasNotifyPrompted(store: Pick<Storage, 'getItem'>): boolean {
  return store.getItem(NOTIFY_PROMPTED_KEY) === '1'
}
