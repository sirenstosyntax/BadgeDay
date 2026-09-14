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

## What each run does

| Event | Mode | Secrets missing | Secrets present |
| --- | --- | --- | --- |
| Pull request touching iOS CI paths | `compile` | Simulator build. `BUILD_NOTES.txt` says `testflightUpload=blocked-until-secrets`. Job is green. | Same. PRs never upload. |
| `workflow_dispatch` with Upload on | `upload` | **Fails.** Does not fake a green upload. | Signed archive + TestFlight upload. |
| `workflow_dispatch` with Upload off | `archive` | Simulator fallback + blocked notes (green). | Signed IPA artifact, no upload. |

`BUILD_NOTES.txt` always lands in the `badgeday-ios` workflow artifact.

## Secrets to add on `sirenstosyntax/BadgeDay`

Names only. Values stay in GitHub Settings → Secrets and variables → Actions.

### Required for the first TestFlight upload

| Secret | What it is |
| --- | --- |
| `APP_STORE_CONNECT_API_KEY_ID` | Key ID from App Store Connect → Users and Access → Integrations → App Store Connect API (the 10-character id). |
| `APP_STORE_CONNECT_ISSUER_ID` | Issuer ID on that same Integrations page (UUID). |
| `APP_STORE_CONNECT_API_KEY_P8` | Contents of the downloaded `.p8`. Raw PEM (`-----BEGIN PRIVATE KEY-----`) or base64 of that file. Either form works. |

Create the key in the App Store Connect website. Role must be **App Manager**
or **Admin** — Developer cannot create a distribution certificate. This does
not need a Mac.

Do **not** use this key to create IAP products.

### Required for durable re-runs (automatic signing via API key is not enough)

GitHub's `macos-latest` runner is ephemeral. A distribution certificate's
**private key** cannot be downloaded back from Apple. Fastlane can mint a
cert on the first upload, then that private key dies with the runner. The
next run will try to mint another, and Apple caps the team at three
distribution certificates.

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
openssl pkcs12 -export -inkey ios_distribution.key -in ios_distribution.pem \
  -out ios_distribution.p12
base64 -w0 ios_distribution.p12
```

Put the base64 in `IOS_DISTRIBUTION_CERTIFICATE_P12_BASE64` and the export
password in `IOS_DISTRIBUTION_CERTIFICATE_PASSWORD`. Keep the `.key` / `.p12`
in a password manager. Never commit them.

The App ID `com.badgeday.app` must already exist (it does — the app record
is in App Store Connect). Enable **Associated Domains** on that App ID if it
is not already on. The live AASA at
`https://badgeday.com/.well-known/apple-app-site-association` already names
`G86W79K99V.com.badgeday.app`, so this is almost certainly done.

Do not create IAP products while doing any of this.

## Will the first run succeed once the secrets exist?

**Upload can succeed on the first `workflow_dispatch` after the three API key
secrets are set**, provided:

- the API key role is App Manager or Admin
- paid-app / free-app agreements in App Store Connect are accepted
- the App ID has Associated Domains (see above)
- no one has already filled the team's three distribution-certificate slots
  with certs whose private keys you do not have

That first signed run uses Fastlane `get_certificates` + `get_provisioning_profile`
when the P12 secrets are still missing. Treat it as a one-shot bootstrap.
Add the two P12 secrets before the second upload or later runs will mint
extra certificates and then fail.

A pull request **compile** is designed to go green **without** any of these
secrets. That is not an upload.

A `workflow_dispatch` upload **without** the three API key secrets **fails on
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

It does not add IAP product identifiers to the binary.

## Local command (only useful on a Mac)

```bash
mobile/ios/build-ios.sh compile
# or, with the same env names the workflow uses:
mobile/ios/build-ios.sh upload
```

Linux cannot run this script past the macOS check. Use the workflow.
