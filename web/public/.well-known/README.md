# `/.well-known` on app.badgeday.com

Digital Asset Links for the Play TWA (`com.badgeday.app`) must be served from
**this host** — `https://app.badgeday.com/.well-known/assetlinks.json` — not
from the marketing site.

`assetlinks.json` is deliberately absent. Copy
`mobile/android/assetlinks.template.json` and fill in the Play **app signing**
SHA-256 (Play Console → Setup → App integrity) after the first signed upload.
A placeholder fingerprint fails verification and looks configured; none at all
is the honest state until that hash exists.

See `mobile/android/PLAY_CONSOLE.md`.
