# The phone apps

Two thin wrappers around the same web app that runs at app.badgeday.com. There is no
second product codebase and there must not be one — a fix to the quiz loop should reach
all three surfaces by being deployed, not by being ported.

The Play TWA is compiled by `mobile/android/build-twa.sh` and by the **TWA** GitHub
Actions workflow, which uploads an AAB. Signing uses CI secrets when present; without
them the AAB is unsigned (Play will not accept it until Grant adds an upload keystore).
See `mobile/android/PLAY_CONSOLE.md`. iOS is still uncompiled here.

## Before either wrapper builds

Both are blocked on the same two things:

1. **The icons.** The Dawn Shield PNGs are in `web/public/icons/`. See that folder's
   README. Bubblewrap reads them out of the web manifest to generate every Android density,
   and both store listings require the 1024×1024 master.
2. **The application id.** `com.badgeday.app` is locked. Do not change it. (DrillGround uses
   `com.sirenstosyntax.drillground`; BadgeDay is a separate consumer brand per `CLAUDE.md`,
   and badgeday.com is a domain the company controls, so the reversed-domain form is
   legitimate.)

## Android — Trusted Web Activity

A TWA is Chrome rendering app.badgeday.com full-screen, with no address bar, inside an
Android app. The address bar disappears only when Digital Asset Links verification passes;
if it fails, the app still works but shows a URL bar, which is both ugly and a Play quality
problem.

The committed answer set is `mobile/android/twa-manifest.json`. To compile
without answering `bubblewrap init`:

```bash
mobile/android/build-twa.sh
```

That script installs JDK 17 and the Android command-line SDK if they are missing,
regenerates the gitignored project with `bubblewrap update --skipVersionUpgrade`,
and builds an AAB. It refuses to run if `packageId` is not `com.badgeday.app` or
if `features.playBilling.enabled` is not `true`. It never creates a keystore,
never calls `bubblewrap play`, and never submits to Play. If the four `TWA_*`
signing secrets are set, the AAB is signed with that upload key; otherwise it is
unsigned.

The older interactive path is still valid if you need to regenerate the answer
set from the live web manifest:

```bash
npm install -g @bubblewrap/cli
cd mobile/android
bubblewrap init --manifest https://app.badgeday.com/manifest.webmanifest
# twa-manifest.json in this directory is the answer set for that prompt — copy it over the
# generated one rather than answering by hand, so Play Billing stays on the next
# time somebody regenerates.
bubblewrap build
```

### Digital Asset Links

`bubblewrap build` prints the SHA-256 fingerprint of the signing key it just used. That
fingerprint goes into `assetlinks.template.json`, and the result is copied to
`web/public/.well-known/assetlinks.json` so it is served from app.badgeday.com — the SPA's
catch-all serves any real file under the build directory, so nothing else needs wiring.

The template is not in `web/public` already, and deliberately: a served assetlinks.json
carrying a placeholder fingerprint is worse than none at all. It fails verification just the
same, and it looks configured.

**Use Play App Signing.** If you do, the fingerprint that matters is the one Play shows
under *Setup → App integrity*, not the one from your local keystore — they are different
keys, and using the local one is the single most common reason a TWA ships with an address
bar still visible.

### Play Billing

`twa-manifest.json` keeps Play Billing **on**, and Bubblewrap 1.25 pulls
`com.google.androidbrowserhelper:billing:1.2.0`, which depends on Play Billing
Library 8.3.0 (the new-app floor). The AAB therefore carries `BILLING` and the
Digital Goods / PaymentActivity wiring.

There is still **no Play SKU and no price in the UI**. Grant has not named the
offer. The TWA paywall shows a Play buy button only after `/me` returns configured
`PLAY_PRODUCT_ID_*` values *and* Digital Goods `getDetails` recognises them. A
browser tab keeps Stripe test checkout. Do not invent a product id to make the
button appear.

Acknowledgement is server-side: the page POSTs the purchase token to
`/billing/store/play/purchase`, which verifies against Google and acknowledges.
Digital Goods v2.1 has no `acknowledge()` for a subscription; `consume()` would
revoke it. Same lesson as DrillGround.

Exact Play Console steps: `mobile/android/PLAY_CONSOLE.md`.

## iOS — Capacitor

Capacitor wraps the same site in a `WKWebView` and adds native plugins to it. The wrapper
part is easy; **clearing App Review guideline 4.2 is the actual work**, and it is not a
configuration setting. A WebView around a website is the textbook 4.2 rejection.

```bash
cd mobile/ios
npm install
npx cap add ios
npx cap open ios     # needs Xcode, on a Mac
```

`capacitor.config.json` points `server.url` at app.badgeday.com, so the app loads the
deployed site rather than a bundled copy. That keeps the wrapper thin and means a web
deploy updates the iOS app without a submission — but note that Apple has been known to
question apps that are *purely* remote, which is the same 4.2 conversation. The planned
native capabilities are what answer it:

| Capability | Plugin | Why it counts |
|---|---|---|
| Upload from Files / iCloud | `@capacitor/filesystem` | The app's central action, and genuinely better than mobile Safari's picker. |
| Camera as a document scanner | `@capacitor/camera` | A candidate photographs an SOG packet instead of finding a scanner. |
| Offline practice | app-side caching | Drilling on an engine with no signal. The website cannot do this. |
| Local notifications | `@capacitor/local-notifications` | Practice streak, exam-date countdown. |
| StoreKit purchase | a Play/StoreKit billing plugin | Required by 3.1.1 anyway, and evidence of an app rather than a shortcut. |

None of these are implemented yet. They are step 4 in `mobile_release_plan.md`.

### Universal links

`apple-app-site-association` is served from **badgeday.com** (the marketing site, on
Netlify) per the infrastructure map, not from this repo. The app side supplies the file's
contents; the marketing side hosts it.

## What connects the wrappers to billing

Both apps buy through their own store, not through Stripe — see `mobile_release_plan.md` for
why, and `app/billing/store*` for the server side. The flow is the same on both platforms:

1. The app completes a purchase with the store's SDK, setting the account token to the
   candidate's user id. **This is the only link between a purchase and an account**, and a
   purchase made without it cannot be attributed to anyone afterwards.
2. The app POSTs the purchase to `/billing/store/{play,appstore}/purchase`, which verifies
   it against the store and unlocks immediately rather than waiting on a notification.
3. Renewals, cancellations and refunds arrive later at
   `/billing/store/{play,appstore}/notifications`.

Those endpoints currently answer **503**, on purpose. The verification described at the top
of `app/billing/store_gateway.py` does not exist yet, and a payment endpoint that cannot
tell a real purchase from an invented one should refuse rather than guess.
