/** Supabase email OTPs are 6 or 8 digits depending on the project; ignore spaces. */
export function normalizeEmailOtp(raw: string): string {
  return raw.replace(/\D/g, '').slice(0, 8)
}

export function isCompleteEmailOtp(token: string): boolean {
  return /^\d{6,8}$/.test(token)
}
