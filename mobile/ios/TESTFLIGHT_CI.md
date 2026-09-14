# Grant: TestFlight CI for the Capacitor iOS shell

The **TestFlight** GitHub Actions workflow runs on `macos-latest`. It generates
the native Xcode project (`npx cap add ios` / `npx cap sync ios`), patches
bundle id `com.badgeday.app` and team `G86W79K99V`, compiles, and — when
secrets exist — archives an App Store IPA and uploads it to TestFlight.

It does **not** create In-App Purchase products, does not submit the app for
App Review, and does not invent `APPSTORE_PRODUCT_ID_*` values. IAP product
create stays **HELD**.

Apple Team ID `G86W79K99V` is public (it is already in the live AASA on
badgeday.com). The `.p8` key, the .p12 password, and the certificate bytes
are secrets. Do not put them in the repo, a PR, or chat.

## Why the Xcode project is generated in CI, not committed

`mobile/ios/ios/` and `mobile/ios/App/` are gitignored, same idea as the TWA
regenerating `mobile/android/app/` from `twa-manifest.json`.

Committing a generated `ios/` tree is the usual Capacitor default, but it is
the worse fit here:

- There is no Mac in this shop to run `npx cap add ios` and keep the pbxproj
  honest.
- A committed Xcode project without that Mac becomes a stale snapshot of one
  CLI version and is hostile to merge.
- Plugin pods (`@capgo/native-purchases` and the rest) already come from the
  committed `package-lock.json` via `npx cap sync ios`.
- Info.plist usage strings, associated domains, team, and the 1024 icon are
  applied by `mobile/ios/patch_native_ios.py`, which is reviewable text.

The durable source of truth is the Capacitor shell + the patcher + Fastlane,
not a generated `project.pbxproj`.

`npx cap add ios --packagemanager Cocoapods` pins CocoaPods (Capacitor 7
`cap sync` has no `--packagemanager` flag). After `pod install`, Capacitor
lives in the Pods project. Compile and archive must use
`ios/App/App.xcworkspace` (absolute path). They must **not** fall back to
`App.xcodeproj`. Run 34906234215 archived the project
(`Target dependency graph (1 target)`), so `import Capacitor` failed.
The green PR compile path already used the workspace (12 targets).
Signing / P12 import is a separate path — do not treat a Capacitor
module error as a keychain failure.

`npx cap add ios` copies Capacitor's iOS 14.0 template and immediately runs
`pod install`. `@capgo/native-purchases` requires iOS 15.0, so that first
install fails with a CocoaPods **deployment-target / CapgoNativePurchases**
refusal. The Xcode project is already on disk. `build-ios.sh` treats **only**
that refusal as expected (stderr must name CapgoNativePurchases and a higher
deployment target). A different `cap add` failure is fatal even if
`project.pbxproj` exists. The script then patches the target to 15.0 and
`npx cap sync ios` succeeds. That expected refusal is not an IAP product
create.

The BD-iOS-4.2 spec's "Explicitly out" / Mac CI pointers were corrected in
#85. StoreKit §6 now matches the landed `@capgo/native-purchases` declare
(IAP product create stays HELD).

## What each run does

| Event | Mode | Secrets missing | Secrets present |
| --- | --- | --- | --- |
| Pull request touching iOS CI paths | `compile` | Simulator build. `BUILD_NOTES.txt` says `testflightUpload=blocked-until-secrets`. Job is green. | Same. PRs never upload. |
| `workflow_dispatch` with Upload on | `upload` | **Fails** if the API key **or** the P12 secrets are missing. Does not fake a green upload. Does not call `get_certificates`. | Signed archive + TestFlight upload. |
| `workflow_dispatch` with Upload off | `archive` | No API key: simulator fallback + blocked notes (green). API key without P12: **fails closed**. | Signed IPA artifact, no upload. |

`BUILD_NOTES.txt` always lands in the `badgeday-ios` workflow artifact.

## Secrets to add on `sirenstosyntax/BadgeDay`

Names only. Values stay in GitHub Settings → Secrets and variables → Actions.

### Required for the first TestFlight upload

The API key **and** the distribution P12 are required before any signed
`upload` / `archive`. There is no one-shot `get_certificates` bootstrap —
that would mint a cert whose private key dies with the ephemeral runner.

| Secret | What it is |
| --- | --- |
| `APP_STORE_CONNECT_API_KEY_ID` | Key ID from App Store Connect → Users and Access → Integrations → App Store Connect API (the 10-character id). |
| `APP_STORE_CONNECT_ISSUER_ID` | Issuer ID on that same Integrations page (UUID). |
| `APP_STORE_CONNECT_API_KEY_P8` | Contents of the downloaded `.p8`. Raw PEM (`-----BEGIN PRIVATE KEY-----`) or base64 of that file. Either form works. |

Create the key in the App Store Connect website. Role must be **App Manager**
or **Admin** — Developer cannot create a distribution certificate. This does
not need a Mac.

Do **not** use this key to create IAP products.

### Required for every signed run (automatic signing via API key is not enough)

GitHub's `macos-latest` runner is ephemeral. A distribution certificate's
**private key** cannot be downloaded back from Apple. Fastlane `archive` /
`upload` **fail closed** until these two secrets exist. The Fastfile will
**not** call `get_certificates` to mint a cert on the runner — that private
key would die with the job, and Apple caps the team at three distribution
certificates.

| Secret | What it is |
| --- | --- |
| `IOS_DISTRIBUTION_CERTIFICATE_P12_BASE64` | Apple Distribution `.p12`, base64 (`base64 -w0 ios_distribution.p12` on Linux). |
| `IOS_DISTRIBUTION_CERTIFICATE_PASSWORD` | Password that protects that `.p12`. |

### Optional

| Secret | What it is |
| --- | --- |
| `IOS_PROVISIONING_PROFILE_BASE64` | App Store provisioning profile for `com.badgeday.app`, base64. If omitted, Fastlane `sigh` fetches or creates the **profile** (not an IAP product) via the API key. |

## Creating the .p12 with no Mac

On any machine with OpenSSL (Linux is fine):

```bash
openssl genrsa -out ios_distribution.key 2048
openssl req -new -key ios_distribution.key -out ios_distribution.csr \
  -subj "/emailAddress=grant@sirenstosyntax.com/CN=BadgeDay iOS Distribution/C=US"
```

Then in the Apple Developer website (not App Store Connect IAP):

1. Certificates → Apple Distribution → upload the CSR.
2. Download `ios_distribution.cer`.
3. Convert and encode (still no Mac):

```bash
openssl x509 -in ios_distribution.cer -inform DER -out ios_distribution.pem
# OpenSSL 3's default PKCS#12 is often rejected by Apple `security`
# even with the correct password (MAC verification failed).
openssl pkcs12 -export -inkey ios_distribution.key -in ios_distribution.pem \
  -out ios_distribution.p12 \
  -keypbe PBE-SHA1-3DES -certpbe PBE-SHA1-3DES -macalg SHA1
base64 -w0 ios_distribution.p12
```

Put the base64 in `IOS_DISTRIBUTION_CERTIFICATE_P12_BASE64` and the export
password in `IOS_DISTRIBUTION_CERTIFICATE_PASSWORD`. Keep the `.key` / `.p12`
in a password manager. Never commit them.

`build-ios.sh` also re-exports the uploaded P12 with those same PBE flags
on the runner before Fastlane imports it, so an existing OpenSSL 3 secret
can still sign. That rewrite fail-closes if the password cannot decrypt
the bag.

The App ID `com.badgeday.app` must already exist (it does — the app record
is in App Store Connect). Enable **Associated Domains** on that App ID if it
is not already on. The live AASA at
`https://badgeday.com/.well-known/apple-app-site-association` already names
`G86W79K99V.com.badgeday.app`, so this is almost certainly done.

Do not create IAP products while doing any of this.

## Will the first run succeed once the secrets exist?

**Upload can succeed on the first `workflow_dispatch` after the three API key
secrets *and* the two P12 secrets are set**, provided:

- the API key role is App Manager or Admin
- paid-app / free-app agreements in App Store Connect are accepted
- the App ID has Associated Domains (see above)
- the P12 is an Apple Distribution cert for team `G86W79K99V` whose private
  key you still have (create it with OpenSSL on Linux — steps above)

There is **no** `get_certificates` bootstrap. A signed `upload` or `archive`
without the P12 **fails closed**. `get_provisioning_profile` (`sigh`) still
runs when `IOS_PROVISIONING_PROFILE_BASE64` is omitted — that fetches or
creates the **profile**, not a distribution cert and not an IAP product.

## How signing fails closed (run 34903809952)

Two separate problems. Do not collapse them.

**Primary (this run):** `security import` / `SecKeychainItemImport` failed with
`MAC verification failed during PKCS12 import (wrong password?)`. Fastlane
2.240 logs that and **continues**. Ops recreates
`IOS_DISTRIBUTION_CERTIFICATE_P12_*` with
`-keypbe PBE-SHA1-3DES -certpbe PBE-SHA1-3DES -macalg SHA1` (OpenSSL 3's
default bag is often rejected by Apple `security` even with the correct
password). `build-ios.sh` re-exports with those flags on the runner; a
password that cannot decrypt the bag still fail-closes.

**Follow-on:** because the P12 never landed, `get_provisioning_profile` /
sigh reported “There are no local code signing identities found” / “Could
not find a matching code signing identity for type 'AppStore'”. That is
not the root cause.

**Defense in depth (when the P12 is good):** `setup_ci` creates
`fastlane_tmp_keychain` and sets `MATCH_KEYCHAIN_NAME` /
`MATCH_KEYCHAIN_PASSWORD`. `import_certificate`'s own env name is
`KEYCHAIN_NAME`, not `MATCH_*`. The Fastfile resolves the on-disk
`fastlane_tmp_keychain-db`, unlocks it, and imports into **that** keychain
(not login). A successful secret must still hit the same keychain sigh
and xcodebuild search.

The lane runs `security import` itself **before** Fastlane
`import_certificate`. A `SecKeychainItemImport` / MAC verification failure
is the lane error. It does **not** continue to `get_provisioning_profile`
or `build_app`. It does **not** call `get_certificates`.

A pull request **compile** is designed to go green **without** any of these
secrets. That is not an upload.

A `workflow_dispatch` upload **without** the API key or P12 secrets **fails on
purpose** (`testflightUpload=blocked-until-secrets`). The workflow will not
report a successful TestFlight upload it did not do.

Things this CI cannot prove, even after a green upload:

- App Review guideline 4.2 on a device
- a sandbox StoreKit purchase (IAP products are still HELD)
- export-compliance beyond `ITSAppUsesNonExemptEncryption=false`

## What the patcher writes (no secrets)

`mobile/ios/patch_native_ios.py` after `npx cap sync ios`:

- `PRODUCT_BUNDLE_IDENTIFIER = com.badgeday.app`
- `DEVELOPMENT_TEAM = G86W79K99V`
- usage strings from `INFO_PLIST_PERMISSIONS.md`
- associated domains `applinks:badgeday.com` and `webcredentials:badgeday.com`
- Dawn Shield `web/public/icons/icon-1024.png` as the 1024 App Icon
- `ITSAppUsesNonExemptEncryption = false` so TestFlight is not blocked on
  the export-compliance questionnaire
- iOS deployment target **15.0** (Podfile + pbxproj) so CocoaPods accepts
  `@capgo/native-purchases`. This is not an IAP product create.

It does not add IAP product identifiers to the binary.

## CocoaPods cache key

`Podfile.lock` is created only after generate-in-CI (`mobile/ios/ios/` is
gitignored), so it cannot be the cache key. The TestFlight workflow keys
the CocoaPods **spec cache** as
`cocoapods-specs-${{ runner.os }}-ios15.0-${{ hashFiles('mobile/ios/package-lock.json') }}`:
plugin pod versions come from the committed `package-lock.json`, and `ios15.0`
is the patcher's `IOS_DEPLOYMENT_TARGET`. Only `~/Library/Caches/CocoaPods`
is cached — not `mobile/ios/ios/App/Pods`. Restoring a Pods-only `ios/` tree
makes `cap add` refuse (`ios platform already exists`) without a pbxproj.
`build-ios.sh` also removes a stale `ios/` that has no `project.pbxproj`.
Bump the `ios15.0` token if the constant changes. `mobile/ios/Gemfile.lock`
is committed so Fastlane resolves the same on every signed run.

## Local command (only useful on a Mac)

```bash
mobile/ios/build-ios.sh compile
# or, with the same env names the workflow uses:
mobile/ios/build-ios.sh upload
```

Linux cannot run this script past the macOS check. Use the workflow.
