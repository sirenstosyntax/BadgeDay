const NOTICES = [
  {
    name: 'certifi',
    license: 'MPL-2.0',
    source: 'https://github.com/certifi/python-certifi',
  },
  {
    name: '@capgo/native-purchases',
    license: 'MPL-2.0',
    source: 'https://github.com/Cap-go/capacitor-native-purchases',
  },
] as const

/**
 * In-app list of open-source packages the product ships with. Plain text and
 * links only. The same screen is opened from the footer on the sign-in page
 * and inside the signed-in app.
 */
export function OpenSourceAcknowledgements({ onBack }: { onBack: () => void }) {
  return (
    <div className="space-y-6">
      <button
        type="button"
        onClick={onBack}
        className="text-sm text-stone-500 hover:underline dark:text-stone-400"
      >
        ← Back
      </button>
      <div>
        <h2 className="text-lg font-semibold">Open-source acknowledgements</h2>
        <p className="mt-2 text-sm text-stone-600 dark:text-stone-400">
          BadgeDay includes this open-source software.
        </p>
      </div>
      <ul className="space-y-4">
        {NOTICES.map((notice) => (
          <li key={notice.name}>
            <p className="text-sm font-medium">{notice.name}</p>
            <p className="mt-1 text-sm text-stone-600 dark:text-stone-400">
              License: {notice.license}
            </p>
            <a
              href={notice.source}
              target="_blank"
              rel="noreferrer"
              className="mt-1 inline-block text-sm text-stone-600 underline dark:text-stone-400"
            >
              {notice.source}
            </a>
          </li>
        ))}
      </ul>
    </div>
  )
}
