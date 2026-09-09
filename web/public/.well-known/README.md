# `/.well-known` on app.badgeday.com

Digital Asset Links for the Play TWA (`com.badgeday.app`) are served from
**this host** — `https://app.badgeday.com/.well-known/assetlinks.json` — not
from the marketing site.

`assetlinks.json` is the filled statement list: package `com.badgeday.app` and
the Play **app signing** SHA-256 (classical) from Play Console → Setup →
App integrity. Vite copies this directory into `web/dist` on `npm run build`;
`app/spa.py` then serves any real file under the build, so the production
path is that JSON at `/.well-known/assetlinks.json` after the next Azure
image deploy (`./deploy/azure-deploy.sh`).

Do not replace the fingerprint with a placeholder. A wrong hash fails
verification the same as none, and looks configured.

See `mobile/android/PLAY_CONSOLE.md`.
