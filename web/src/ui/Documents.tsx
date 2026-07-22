import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, api } from '../lib/api'
import type { Coverage, DocumentRecord, DocumentStatus } from '../lib/types'

/** Statuses that mean a job is still outstanding, so the list must keep refreshing. */
const IN_PROGRESS: DocumentStatus[] = ['pending', 'analyzing', 'chunking', 'generating']

const LABELS: Record<DocumentStatus, string> = {
  pending: 'Queued',
  analyzing: 'Reading the document',
  chunking: 'Finding the sections',
  generating: 'Writing questions',
  ready: 'Ready',
  failed: 'Failed',
}

function StatusPill({ status }: { status: DocumentStatus }) {
  const tone =
    status === 'ready'
      ? 'bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200'
      : status === 'failed'
        ? 'bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200'
        : 'bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200'
  return <span className={`rounded-full px-2 py-0.5 text-xs ${tone}`}>{LABELS[status]}</span>
}

export function Documents({ onPractise }: { onPractise: (documentId: string | null) => void }) {
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [coverage, setCoverage] = useState<Record<string, Coverage>>({})
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  const refresh = useCallback(async () => {
    try {
      const [docs, cov] = await Promise.all([api.documents.list(), api.coverage()])
      setDocuments(docs)
      setCoverage(Object.fromEntries(cov.map((c) => [c.document_id, c])))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not load your documents.')
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  // Ingestion is minutes of work, so the status on screen has to come to the candidate
  // rather than waiting for them to reload. Polling stops as soon as nothing is
  // outstanding — a list of ready documents does not need a request every three seconds.
  useEffect(() => {
    if (!documents.some((d) => IN_PROGRESS.includes(d.status))) return
    const timer = setInterval(() => void refresh(), 3000)
    return () => clearInterval(timer)
  }, [documents, refresh])

  async function upload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    setUploading(true)
    setError(null)
    try {
      await api.documents.upload(file)
      await refresh()
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : 'That upload did not go through.',
      )
    } finally {
      setUploading(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  async function remove(document: DocumentRecord) {
    if (!confirm(`Delete ${document.filename}? Its questions go with it.`)) return
    try {
      await api.documents.remove(document.id)
      await refresh()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not delete that document.')
    }
  }

  const anyReady = documents.some((d) => d.status === 'ready')

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Your reading list</h2>
          <p className="text-sm text-stone-600 dark:text-stone-400">
            Upload the documents your exam announcement lists. Questions come from those
            documents and cite them.
          </p>
        </div>
        <label className="shrink-0 cursor-pointer rounded-lg bg-stone-900 px-3 py-2 text-sm font-medium text-white dark:bg-stone-100 dark:text-stone-900">
          {uploading ? 'Uploading…' : 'Add document'}
          <input
            ref={fileInput}
            type="file"
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            onChange={upload}
            disabled={uploading}
            className="hidden"
          />
        </label>
      </div>

      {error && (
        <p className="rounded-lg bg-red-50 p-3 text-sm text-red-900 dark:bg-red-950 dark:text-red-200">
          {error}
        </p>
      )}

      {documents.length === 0 ? (
        <p className="rounded-lg border border-dashed border-stone-300 p-8 text-center text-sm text-stone-500 dark:border-stone-700">
          Nothing uploaded yet. Start with one SOG from your announcement.
        </p>
      ) : (
        <ul className="divide-y divide-stone-200 rounded-lg border border-stone-200 dark:divide-stone-800 dark:border-stone-800">
          {documents.map((document) => {
            const cover = coverage[document.id]
            return (
              <li key={document.id} className="flex items-center gap-4 p-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-medium">{document.filename}</span>
                    <StatusPill status={document.status} />
                  </div>
                  <div className="mt-1 text-xs text-stone-500 dark:text-stone-400">
                    {document.page_count ? `${document.page_count} pages · ` : ''}
                    {cover && cover.sections_total > 0
                      ? `${cover.percent}% covered (${cover.sections_exercised}/${cover.sections_total} sections)`
                      : 'No coverage yet'}
                  </div>
                  {document.error && (
                    <p className="mt-1 text-xs text-red-700 dark:text-red-400">{document.error}</p>
                  )}
                </div>
                {document.status === 'ready' && (
                  <button
                    onClick={() => onPractise(document.id)}
                    className="rounded-md border border-stone-300 px-2 py-1 text-sm dark:border-stone-700"
                  >
                    Practise
                  </button>
                )}
                <button
                  onClick={() => void remove(document)}
                  className="text-sm text-stone-500 hover:text-red-700 dark:hover:text-red-400"
                >
                  Delete
                </button>
              </li>
            )
          })}
        </ul>
      )}

      {anyReady && (
        <button
          onClick={() => onPractise(null)}
          className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm font-medium dark:border-stone-700"
        >
          Practise the whole list
        </button>
      )}
    </div>
  )
}
