/**
 * Device-local keys that must not survive a sign-out or account delete, and
 * must not leak from one candidate to the next on a shared phone.
 */
import { LAST_PRACTICE_KEY, OFFLINE_CACHE_KEY } from './offlinePractice'

export const EXAM_DATE_KEY = 'badgeday.examDate.v1'
export const NOTIFY_PROMPTED_KEY = 'badgeday.notifyPrompted.v1'

const USER_SCOPED = [OFFLINE_CACHE_KEY, LAST_PRACTICE_KEY, EXAM_DATE_KEY, NOTIFY_PROMPTED_KEY]

export function clearDeviceLocalUserData(store: Pick<Storage, 'removeItem'> = localStorage): void {
  for (const key of USER_SCOPED) store.removeItem(key)
}
