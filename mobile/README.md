# The phone apps

Two thin wrappers around the same web app that runs at app.badgeday.com. There is no
second product codebase and there must not be one — a fix to the quiz loop should reach
all three surfaces by being deployed, not by being ported.

**The Android project under `mobile/android/app/` is generated and gitignored.** Run
Bubblewrap from `twa-manifest.json` to produce it. A first compile still needs a JDK and
the Android SDK; this file is not a claim that an AAB was built here.

## Before either wrapper builds

1. **The icons.** The Dawn Shield PNGs live in `web/public/icons/`. Bubblewrap reads them
   out of the live web manifest. The 1024×1024 master is `icon-1024.png`.
2. **Application id.** `com.badgeday.app` is locked. Do not change it.

## Android — Trusted Web Activity

A TWA is Chrome rendering app.badgeday.com full-screen, with no address bar, inside an
Android app. The address bar disappears only when Digital Asset Links verification passes;
if it fails, the app still works but shows a URL bar, which is both ugly and a Play quality
problem.

```bash
npm install -g @bubblewrap/cli
cd mobile/android
bubblewrap init --manifest https://app.badgeday.com/manifest.webmanifest
# twa-manifest.json in this directory is the answer set for that prompt — copy it over the
# generated one rather than answering by hand, so the Play Billing flag stays off the next
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

`twa-manifest.json` keeps Play Billing **off**. Do not enable it. Official Play Billing
Library v7's new-app cutoff is 2026-08-31; turning billing on with no products buys that
deadline for nothing. Purchases stay on Stripe (test) in the browser until a later order
names Play products.

## iOS — Capacitor

Not this order. See `mobile_release_plan.md` section 4.2. Do not add Capacitor, StoreKit,
or an iOS project here.

## What connects the wrappers to billing

Store purchase endpoints currently answer **503**, on purpose. Do not create Play or App
Store products from this wrap.
