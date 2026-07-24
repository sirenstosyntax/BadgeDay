import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL
const publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY

if (!url || !publishableKey) {
  throw new Error(
    'VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY must be set. Copy web/.env.example ' +
      'to web/.env.local and fill them in from the Supabase dashboard.',
  )
}

/**
 * Auth only. Every piece of data in this app comes from the BadgeDay API, never straight
 * from PostgREST — because the API is where the question-serving path is arranged not to
 * be able to see an answer. A component that reached for `supabase.from('questions')`
 * would be asking the database for columns migration 0004 revoked, and would get an error
 * rather than a leak, but the reason it fails is worth knowing before writing it.
 *
 * The publishable key is public by design: it identifies the project, it does not grant
 * anything. What grants access is the candidate's own token, and RLS decides the rest.
 */
export const supabase = createClient(url, publishableKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    // The magic link lands back here with the session in the URL fragment; this is what
    // picks it up and exchanges it. Without it, clicking the emailed link appears to do
    // nothing at all.
    detectSessionInUrl: true,
  },
})
