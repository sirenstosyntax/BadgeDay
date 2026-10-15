import { useEffect, useState } from 'react'
import { api } from '../lib/api'

/** The "When is your test?" link. One date field. */
export function TestDate({
  initial,
  onDone,
}: {
  initial: string | null
  onDone: () => void
}) {
  const [value, setValue] = useState(initial ?? '')
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setValue(initial ?? '')
  }, [initial])

  async function save(event: React.FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      await api.account.setTestDate(value || null)
      setSaved(true)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save that date.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={(event) => void save(event)} className="space-y-4">
      <button
        type="button"
        onClick={onDone}
        className="text-sm text-stone-500 hover:underline dark:text-stone-400"
      >
        ← Back
      </button>
      <label htmlFor="test-date" className="block text-lg font-medium">
        When is your test?
      </label>
      <input
        id="test-date"
        name="test_date"
        type="date"
        value={value}
        onChange={(event) => {
          setValue(event.target.value)
          setSaved(false)
        }}
        className="min-h-12 w-full rounded-lg border border-stone-300 bg-white px-3 text-base text-stone-900 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100"
      />
      <button
        type="submit"
        disabled={saving}
        className="min-h-12 w-full rounded-lg bg-stone-900 px-4 text-base font-medium text-white disabled:opacity-50 dark:bg-stone-100 dark:text-stone-900"
      >
        {saving ? 'Saving…' : 'Save'}
      </button>
      {saved && <p className="text-sm text-stone-600 dark:text-stone-400">Saved.</p>}
      {error && <p className="text-sm text-red-700 dark:text-red-400">{error}</p>}
    </form>
  )
}
