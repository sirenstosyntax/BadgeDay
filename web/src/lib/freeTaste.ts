import type { Account } from './types'

/**
 * Promote's free document, as the app needs it.
 *
 * The server decides which upload is the free one (migration 0019) and refuses anything
 * past it with a 402, so nothing here is a gate. These helpers only stop the app from
 * sending a candidate to the paywall for something the server would have let through —
 * which, before the free taste existed, was every upload and every session.
 */
export type FreeTaste = {
  /** A candidate without a plan may upload one document now. */
  canUpload: boolean
  /** The document they may practise without a plan, once uploaded. */
  documentId: string | null
  pages: number | null
  questions: number | null
}

export function promoteFreeTaste(account: Account | null, entitled: boolean): FreeTaste {
  const pages = account?.promote_free_taste_pages ?? null
  const questions = account?.promote_free_taste_questions ?? null
  if (!account) return { canUpload: false, documentId: null, pages, questions }
  return {
    canUpload: !entitled && account.promote_free_taste_open === true,
    documentId: account.promote_free_taste_document_id ?? null,
    pages,
    questions,
  }
}

/**
 * Which document a practice session should be on, or `undefined` for the paywall.
 *
 * With a plan, the candidate's own choice stands — one document, or `null` for the whole
 * list. Without one, only the free document can be practised, and "the whole list" means
 * that document: a mix session needs a plan on the server.
 */
export function practiceScope(
  entitled: boolean,
  freeTaste: FreeTaste,
  documentId: string | null,
): string | null | undefined {
  if (entitled) return documentId
  if (!freeTaste.documentId) return undefined
  if (documentId === null || documentId === freeTaste.documentId) return freeTaste.documentId
  return undefined
}

/** The banner line for a candidate without a plan. */
export function freeTasteNotice(freeTaste: FreeTaste): string {
  if (freeTaste.canUpload) {
    const pages = freeTaste.pages ? `its first ${freeTaste.pages} pages` : 'it'
    const questions = freeTaste.questions ? `up to ${freeTaste.questions}` : 'a few'
    return (
      `Try it free: upload one policy or SOP and practise ${questions} cited questions ` +
      `from ${pages}. No card needed.`
    )
  }
  if (freeTaste.documentId) {
    return (
      'Your free document is marked Free. A plan adds the rest of your reading list and ' +
      'every question from each document.'
    )
  }
  return (
    'No active plan. You can still read and delete what you have uploaded; adding ' +
    'documents and starting sessions need a subscription.'
  )
}
