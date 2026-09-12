import { useState } from 'react'
import { ApiError, api } from '../lib/api'
import {
  moduleHasManageableBilling,
  modulePlanSummary,
} from '../lib/moduleAccess'
import type { Account as AccountState, PaywallModule } from '../lib/types'

const MODULES: { module: PaywallModule; name: string }[] = [
  { module: 'recruit', name: 'Recruit' },
  { module: 'promote', name: 'Promote' },
]

/**
 * The account page: what the candidate has, and the way out. Deletion is irreversible and
 * takes every document and session with it, so it is not a single confused click — the
 * button reveals a confirmation that makes the candidate type the word, the same weight the
 * action carries. Billing is cancelled server-side as part of the delete; nothing here has
 * to be done first.
 *
 * Recruit and Promote are separate modules. Manage billing appears for a module they
 * already hold; See plans appears only for a module they do not.
 */
export function Account({
  account,
  onManageBilling,
  onSubscribe,
  onDeleted,
  onDone,
}: {
  account: AccountState | null
  onManageBilling: (module: PaywallModule) => void
  onSubscribe: (module: PaywallModule) => void
  onDeleted: () => void
  onDone: () => void
}) {
  const [confirming, setConfirming] = useState(false)
  const [typed, setTyped] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function remove() {
    setDeleting(true)
    setError(null)
    try {
      await api.account.remove()
      onDeleted()
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : 'Could not delete the account.',
      )
      setDeleting(false)
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <button
          onClick={onDone}
          className="text-sm text-stone-500 hover:underline dark:text-stone-400"
        >
          ← Back
        </button>
        <h2 className="mt-3 text-lg font-semibold">Account</h2>
        <p className="mt-1 text-sm text-stone-600 dark:text-stone-400">{account?.email}</p>
      </div>

      <div className="space-y-3">
        {MODULES.map(({ module, name }) => {
          const canManage = moduleHasManageableBilling(account, module)
          return (
            <div
              key={module}
              className="rounded-lg border border-stone-200 p-4 dark:border-stone-800"
            >
              <p className="text-sm font-medium">{name}</p>
              <p className="mt-1 text-sm text-stone-600 dark:text-stone-400">
                {modulePlanSummary(account, module)}
              </p>
              <div className="mt-3">
                {canManage ? (
                  <button
                    onClick={() => onManageBilling(module)}
                    className="rounded-md border border-stone-300 px-3 py-1.5 text-sm dark:border-stone-700"
                  >
                    Manage billing
                  </button>
                ) : (
                  <button
                    onClick={() => onSubscribe(module)}
                    className="rounded-md bg-stone-900 px-3 py-1.5 text-sm font-medium text-white dark:bg-stone-100 dark:text-stone-900"
                  >
                    See plans
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>

      <div className="rounded-lg border border-red-200 p-4 dark:border-red-900/60">
        <h3 className="text-sm font-semibold text-red-900 dark:text-red-200">Delete account</h3>
        <p className="mt-1 text-sm text-stone-600 dark:text-stone-400">
          Permanently removes your documents, questions and practice history, and cancels any
          billing. This cannot be undone.
        </p>

        {confirming ? (
          <div className="mt-3 space-y-3">
            <label className="block text-sm text-stone-600 dark:text-stone-400">
              Type <span className="font-mono font-semibold">DELETE</span> to confirm.
              <input
                value={typed}
                onChange={(event) => setTyped(event.target.value)}
                autoFocus
                className="mt-1 block w-40 rounded-md border border-stone-300 bg-transparent px-2 py-1 dark:border-stone-700"
              />
            </label>
            <div className="flex items-center gap-3">
              <button
                onClick={() => void remove()}
                disabled={typed !== 'DELETE' || deleting}
                className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                {deleting ? 'Deleting…' : 'Delete everything'}
              </button>
              <button
                onClick={() => {
                  setConfirming(false)
                  setTyped('')
                }}
                disabled={deleting}
                className="text-sm text-stone-500 hover:underline dark:text-stone-400"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setConfirming(true)}
            className="mt-3 rounded-md border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 dark:border-red-800 dark:text-red-300"
          >
            Delete account
          </button>
        )}

        {error && (
          <p className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-900 dark:bg-red-950 dark:text-red-200">
            {error}
          </p>
        )}
      </div>
    </div>
  )
}
