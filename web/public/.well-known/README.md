# `/.well-known` on app.badgeday.com

Digital Asset Links for the Play TWA (`com.badgeday.app`) must be served from
**this host** — `https://app.badgeday.com/.well-known/assetlinks.json` — not
from the marketing site.

`mobile/android/assetlinks.template.json` already has the Play app-signing
SHA-256. `assetlinks.json` is still absent here. The remaining step is to copy
that filled template to `web/public/.well-known/assetlinks.json` and deploy so
it is served at `https://app.badgeday.com/.well-known/assetlinks.json`.

See `mobile/android/PLAY_CONSOLE.md`.
