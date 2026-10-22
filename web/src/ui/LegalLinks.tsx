/**
 * Links to the privacy policy and the terms, plus the in-app open-source screen.
 *
 * Privacy and terms are plain anchors, not app views: both pages are static HTML in
 * web/public, served straight from the build so they render for someone with no account
 * and no JavaScript. Clicking one leaves the app, which is correct — a candidate reading
 * the privacy policy is deciding whether to hand us their department's documents, and that
 * should not require being signed in first.
 *
 * Open-source acknowledgements stays in the app. It is a screen of package names and
 * license links, opened from this footer on the sign-in page and after sign-in.
 */
export function LegalLinks({
  className = '',
  onOpenSource,
}: {
  className?: string
  onOpenSource: () => void
}) {
  return (
    <div className={className}>
      <p className="text-xs text-stone-500 dark:text-stone-500">
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
      <p className="mt-2 text-xs text-stone-500 dark:text-stone-500">
        <button
          type="button"
          onClick={onOpenSource}
          className="inline cursor-pointer appearance-none border-0 bg-transparent p-0 text-inherit hover:underline"
        >
          Open-source acknowledgements
        </button>
      </p>
    </div>
  )
}
