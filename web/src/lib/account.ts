import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import type { Account } from './types'

/**
 * The candidate's entitlement, polled from `/me` — the same question every gate in the
 * backend asks, answered in one place here so the UI cannot hold a second opinion about
 * who may act.
 *
 * `refresh` is exposed because entitlement changes outside the app's control: it is set by
 * Stripe's webhook after checkout, so on returning from a successful payment the app must
 * re-ask rather than trust the stale answer it loaded with. A 402 from a gated action is
 * the other moment to refresh — access lapsed while the app was open.
 */
export function useAccount(enabled: boolean) {
  const [account, setAccount] = useState<Account | null>(null)

  const refresh = useCallback(async () => {
    if (!enabled) return
    try {
      setAccount(await api.account.me())
    } catch {
      // A failed entitlement read is left as null rather than assumed either way. The gates
      // treat "unknown" as "not entitled", which is the safe direction: it shows the
      // paywall rather than waving through work the candidate may not have paid for.
      setAccount(null)
    }
  }, [enabled])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return { account, entitled: account?.entitled ?? false, refreshAccount: refresh }
}
