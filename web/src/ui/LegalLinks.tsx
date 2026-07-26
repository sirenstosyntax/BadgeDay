/**
 * Links to the privacy policy and the terms.
 *
 * Plain anchors, not app views: both pages are static HTML in web/public, served straight
 * from the build so they render for someone with no account and no JavaScript. Clicking one
 * leaves the app, which is correct — a candidate reading the privacy policy is deciding
 * whether to hand us their department's documents, and that should not require being signed
 * in first.
 */
export function LegalLinks({ className = '' }: { className?: string }) {
  return (
    <p className={`text-xs text-stone-500 dark:text-stone-500 ${className}`}>
      <a href="/privacy" className="hover:underline">
        Privacy
      </a>
      <span aria-hidden="true"> · </span>
      <a href="/terms" className="hover:underline">
        Terms
      </a>
      <span aria-hidden="true"> · </span>
      <a href="mailto:grant@sirenstosyntax.com" className="hover:underline">
        Contact
      </a>
    </p>
  )
}
