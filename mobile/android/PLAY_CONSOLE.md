# Grant: Play Console steps for this TWA

The CI job **TWA / Play TWA AAB (billing on)** builds an AAB with package
`com.badgeday.app`, start URL `https://app.badgeday.com/`, and the Play Billing
permission. It does **not** create an in-app product or print a price. Stripe
live is approved for Recruit and Promote on the web; Play uses Play Billing.
Do not invent product ids.

Developer account (organisation, already exists): Sirens to Syntax LLC,
`7304930268481203834`, owner `grant@sirenstosyntax.com`.

## 1. Create the Play app if it is missing

1. Play Console → **Create app**.
2. Name: BadgeDay. Default language: English (United States).
3. App or game: **App**. Free or paid: **Free** (subscriptions are in-app
   products, not a paid APK).
4. Package name is **not** chosen on this screen. It is locked by the first
   uploaded AAB to `com.badgeday.app`. Do not create a different application id.
5. Accept the declarations that apply. Privacy policy URL:
   `https://app.badgeday.com/privacy`.

If an app entry already exists, its application id wins. If that id is not
`com.badgeday.app`, stop and tell the repo — Play will not let it change.

## 2. Play App Signing

New apps get Play App Signing by default. Leave it on.

The fingerprint that Digital Asset Links needs is the **app signing** key Play
shows under **Setup → App integrity**, not the upload key on a laptop. Using the
upload-key fingerprint is the usual reason a TWA ships with the address bar
still visible.

## 3. Upload keystore (required before Play will accept the AAB)

CI produces an **unsigned** AAB unless these four GitHub Actions secrets exist
on `sirenstosyntax/BadgeDay`. Do not put the passwords in the repo, a PR, or
chat.

| Secret | What it is |
| --- | --- |
| `TWA_KEYSTORE_BASE64` | Upload keystore file, base64 (`base64 -w0 android.keystore`) |
| `TWA_KEYSTORE_PASSWORD` | Keystore password |
| `TWA_KEY_ALIAS` | Key alias (Bubblewrap default is `android`) |
| `TWA_KEY_PASSWORD` | Key password |

Create the upload keystore once, in a password manager, not in git:

```bash
keytool -genkeypair -v -keystore android.keystore -alias android \
  -keyalg RSA -keysize 2048 -validity 10000
base64 -w0 android.keystore
```

Then either:

- add the four secrets and re-run the TWA workflow, and download
  `badgeday-twa.aab`, or
- sign the unsigned artifact locally (`jarsigner` / `jarsigner -sigalg SHA256withRSA`)
  and keep the keystore out of the tree.

`BUILD_NOTES.txt` in the workflow artifact says `signed=1` or
`playUpload=blocked-until-signed`.

## 4. Internal testing upload

1. Play Console → the BadgeDay app → **Testing → Internal testing**.
2. Create a release. Upload the **signed** AAB.
3. Add yourself as a tester. Install from the internal-testing link on a device
   with Play Store.

Closed-testing 12-testers-for-14-days does **not** apply (organisation account).
Internal testing is still the right first upload: a TWA can fail Digital Asset
Links or Play Billing on a real device in ways this build cannot see.

## 5. Digital Asset Links

The statement list is filled: package `com.badgeday.app` and the Play **app
signing** SHA-256 (classical) from Setup → App integrity. It lives at
`mobile/android/assetlinks.template.json` and is copied to
`web/public/.well-known/assetlinks.json`.

That public file is what Vite puts in `web/dist`. After the next Azure image
deploy (`./deploy/azure-deploy.sh`), `app/spa.py` serves it at
`https://app.badgeday.com/.well-known/assetlinks.json`.

Do **not** put a placeholder fingerprint there — a wrong hash fails
verification the same as none, and looks configured.

The TWA host is `app.badgeday.com`. The marketing site on `badgeday.com` is the
wrong origin for this file.

Verify after deploy (expect HTTP 200 and `Content-Type: application/json`).
Use GET — `curl -I` sends HEAD, and the SPA catch-all is GET-only (405):

```bash
curl -sSI -X GET https://app.badgeday.com/.well-known/assetlinks.json
curl -sS https://app.badgeday.com/.well-known/assetlinks.json
```

Play's statement list for the same host:

```text
https://digitalassetlinks.googleapis.com/v1/statements:list?source.web.site=https://app.badgeday.com&relation=delegate_permission/common.handle_all_urls
```

## 6. Play SKUs (match locked amounts)

Promote and Recruit paid offers are named and locked (`badgeday_pricing.md`).
Live Stripe price IDs are ops-filled. Play SKUs should match those amounts.
Do not invent product ids in the repo, in env, or in the UI.

| Module | Offer | Locked amount |
| --- | --- | --- |
| Promote | Monthly | $29/mo |
| Promote | 90-day intensive | $129 |
| Recruit | Monthly | $24.99/mo |
| Recruit | 90-day pass | $59 |
| Recruit | 6-month | $119 |
| Recruit | Annual | $179/yr |

To wire Play Billing:

1. Play Console → Monetise → create the subscription / one-time products at
   those amounts. Product ids must match Console exactly.
2. Set `PLAY_PACKAGE_NAME=com.badgeday.app` and `PLAY_PRODUCT_ID_*` on the
   Azure app (names only in `.env.example`).
3. Wire Play Developer API + RTDN as in `mobile_release_plan.md` before taking
   a real purchase. Until those credentials exist, `/billing/store/play/*`
   correctly answers 503.
4. The TWA paywall shows a Play buy path only after `/me` returns those ids
   **and** Digital Goods `getDetails` recognises them. No id, no buy button.

## 7. Play reviewer sign-in (Production)

Google rejects magic-link / emailed OTP as MFA. Production has an env-gated
password path for allowlisted reviewer emails only. Normal candidates stay on
OTP. This is not a public password product.

Set both on the Azure web app (`.env` → `./deploy/azure-deploy.sh`). Leave
them blank and the path stays off (`GET /auth/play-reviewer` →
`{"configured":false}`; `POST` is 404).

```text
PLAY_REVIEWER_EMAILS=REVIEWER_EMAIL
PLAY_REVIEWER_PASSWORD=REVIEWER_PASSWORD
```

Do not commit the live values. After deploy, paste the Sign-in details from
the PR that added this path into Play Console → App content → App access.

The first successful password sign-in creates the auth user if it does not
already exist (Supabase admin generate_link). Grant entitlements separately
if the reviewer must see paid surfaces; reaching the signed-in home screen
does not require a plan.

## 8. Still needed for Play production

Web Stripe go-live is done for both Recruit and Promote (START ORDER
2026-09-11; see `badgeday_pricing.md` and `CLAUDE.md`). That is not a hold
on Play.

Play Production 1.1.0 was rejected for MFA/OTP. Resubmit stays blocked on
reviewer Sign-in details until that path is configured and pasted into Play
Console (see §7). That is a reviewer-access hold, not a Stripe-test hold.

Store listing screenshots, feature graphic, and the Data safety form are
still needed before production, as appropriate — not before internal testing.
