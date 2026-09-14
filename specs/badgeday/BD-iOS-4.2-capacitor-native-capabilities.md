# BD-iOS-4.2 — Capacitor native capabilities (App Review 4.2)

Status: draft for Zazu / Gyro — START ORDER 2026-09-12. Explicitly-out updated 2026-09-14 for PR 84 Mac CI TestFlight; IAP create HELD.
Product: BadgeDay iOS Capacitor shell (`mobile/ios`, `appId` `com.badgeday.app`, `server.url` `https://app.badgeday.com`)
Audience: pre-hire Recruit candidates and serving Promote candidates using the iOS app
Soft constraint: no real FD names, logos, insignia, apparatus, or facilities; no employer naming (listings, screenshots, copy)

---

## 1. User story

As a BadgeDay candidate on iOS, I need the Capacitor shell to do work that mobile Safari cannot (native document pick/scan, offline Promote practice, local reminder notifications, and App Store purchases) so Apple App Review accepts the app under guideline **4.2 Minimum Functionality** and guideline **3.1.1** In-App Purchase, without a second product codebase.

---

## 2. Scope

### In (priority order — implement in this order; each slice must be independently shippable in-repo)

1. **Native Promote document upload** — Files / iCloud Drive picker and camera-as-scanner on the Promote reading-list upload path; result feeds the existing document upload API as a PDF/DOCX (or JPEG/PNG from camera converted to an uploadable file the existing API accepts).
2. **Offline Promote practice** — while online, cache **one** ready Promote practice session (questions + citation metadata needed to drill and review) so the candidate can answer and review that session with no signal; sync grades / progress when connectivity returns if the online API requires it, or queue locally until online (see data model).
3. **Local notifications** — practice-streak reminder and optional exam-date countdown (candidate-set date; local preference is enough for V1).
4. **StoreKit purchase wiring** — inside the iOS Capacitor shell, buy Recruit and Promote SKUs through App Store billing, then report to existing `POST /billing/store/appstore/purchase`; renewals/cancellations/refunds continue via existing `POST /billing/store/appstore/notifications`. Product ids match configured `APPSTORE_PRODUCT_ID_*` (ops-filled; do not invent). Amounts assume **parity** with live web / Play locked offers unless Grant says otherwise (Promote `$29/mo` + `$129` 90-day; Recruit `$24.99/mo`, `$59` 90-day, `$119` 6-month, `$179/yr`).

### Explicitly out

- **Still out:** App Store Connect listing submit / App Review submission, ASC screenshot/listing asset capture, creating IAP products in App Store Connect (HELD — lawyer; do not invent `APPSTORE_PRODUCT_ID_*`), sandbox StoreKit proving until IAP exists.
- **No longer out (superseded by PR 84):** macOS CI generate-in-CI + archive + TestFlight upload path (`mobile/ios/TESTFLIGHT_CI.md` / the macos-latest workflow). That path is ops+secrets; this native-capabilities spec still owns the web/plugin 4.2 work, not re-implementing the CI workflow.
- A second product codebase, bundled offline copy of the whole SPA as the primary surface, or forking Promote/Recruit business logic into native Swift screens.
- Offline **Recruit** oral boards (ASR + critique require network). Recruit remains online-only in V1.
- Changing Stripe web checkout or Play Digital Goods flows (except shared paywall detection that selects App Store till when running inside Capacitor iOS).
- Inventing a product decision for **account deletion while an App Store subscription is live** (still open in `mobile_release_plan.md` — see Open questions). Do not change `DELETE /me` behavior in this spec.
- US-only external-link purchase UI (Epic / 3.1.1 exception) — not at launch.
- Raising App Store prices above web to absorb Apple’s cut — open commercially; V1 assumes amount parity; ops creates IAP products to match.
- Filling live `APPSTORE_PRODUCT_ID_*` / App Store Connect API credentials in the repo (ops / Grant).
- Universal Links / `apple-app-site-association` hosting changes (marketing site already owns hosting per `mobile/README.md`).
- Play production / TWA work.

---

## 3. Acceptance criteria

### A. Shell / platform detection

1. On iOS Capacitor (`appId` `com.badgeday.app`, remote `server.url` `https://app.badgeday.com`), the web app can detect “running inside BadgeDay iOS native shell” (as opposed to mobile Safari or the Play TWA) and enable the native capability entry points below.
2. On web and Play TWA, those native entry points are not shown as broken buttons; existing Stripe / Play tills continue to work unchanged.
3. No product feature is implemented only in Swift UI screens that duplicate web flows — native code is limited to plugin bridges and Info.plist / permission strings required for those plugins.

### B. Native Promote upload (priority 1)

4. From Promote “Add document” while entitled and inside the iOS shell, the candidate can choose **Files / iCloud** and pick a PDF or DOCX; the file is uploaded through the **existing** document upload API and appears in the reading list with the same status pipeline as a web upload.
5. From the same control (or an adjacent “Scan page” control), the candidate can capture with the **camera**; the resulting image is uploaded as a document the existing ingestion path accepts (or is clearly refused with an existing/API-consistent error if the backend only accepts PDF/DOCX — in that case the UI must convert or state the limit before upload; do not silently drop the capture).
6. Upload still requires Promote entitlement; a 402 still routes to the paywall (App Store till when on iOS shell — see D).
7. Permission denial (Files / Photos / Camera) shows a recoverable message telling the candidate how to enable access in iOS Settings; no crash, no blank screen.
8. Soft constraint: no sample filenames, screenshots, or placeholder assets in-repo that name a real department or show apparatus/insignia.

### C. Offline Promote practice (priority 2)

9. While online, the candidate can **explicitly** cache one Promote practice session for offline use (whole-list or single-document session that is already startable online). The cached payload includes every question the session would present plus the citation / source references needed for review — enough to drill without network.
10. With network offline (or airplane mode), opening the cached session lets the candidate answer questions and see review/citations for that cached set. No network call is required to present the next question or show stored citations.
11. If no session is cached, offline practice shows an empty state that tells the candidate to cache a session while online — not a generic “failed to load” spinner forever.
12. Recruit practice, document upload, generation, and account/billing actions that need the API remain unavailable offline with a clear “needs connection” state (not a crash).
13. When back online, any answers / progress that must reach the server are submitted or the UI states plainly what was only local. Do not invent a second grading model; prefer reusing existing session/response APIs once reachable.
14. Cache is per signed-in user on device; signing out or deleting the account clears the offline cache on that device.

### D. Local notifications (priority 3)

15. On first use of reminders (or first practice after install), the app requests local-notification permission; denial is non-blocking for the rest of the app.
16. **Practice streak:** if the candidate has practiced (Promote quiz and/or Recruit board start — either counts) on a prior calendar day and has not practiced today, a local notification may fire at a quiet default local time (default **18:00** device local) reminding them to practice. Copy is product-safe (no FD names; no scores). Exact string is an open Red route if candidate-facing marketing tone matters; until Red signs, use a neutral placeholder flagged in Open questions.
17. **Exam-date countdown:** the candidate may set an optional **exam date** (date only) in Account (Promote-oriented). When set and permission granted, a local notification fires on a simple schedule (at minimum: morning of exam day, and 7 days before if that date is in the future). Clearing the date cancels those notifications.
18. Notifications do not require a server push provider. No remote push in this spec.
19. Uninstall / disable notifications leaves practice and billing functional.

### E. StoreKit wiring (priority 4)

20. Inside the iOS Capacitor shell, Paywall for Recruit and Promote uses an **App Store till** (not Stripe redirect, not Play Digital Goods). Prices shown are the ones StoreKit returns for the configured product ids — never a hardcoded dollar amount in UI copy (same rule as Play/Stripe today).
21. Completing a purchase calls `POST /billing/store/appstore/purchase` with the transaction id the server already expects; on `entitled: true`, the paywall unlocks the module without waiting for the notification webhook.
22. If App Store billing is not configured server-side (503) or product ids are blank / unrecognized, the paywall shows a non-buyable state equivalent to today’s Play “unlisted” till — no fake price, no Stripe redirect inside the iOS shell for digital subscription (3.1.1).
23. Account “Manage billing” for an App Store–managed module (`managed_by` already reported by `/me`) deep-links or instructs the candidate to manage the subscription in Apple’s subscription settings — not the Stripe portal.
24. Restore purchases: a control exists that re-queries StoreKit / re-reports owned transactions so a reinstall can regain access when Apple still shows the subscription.
25. Product id env keys remain: `APPSTORE_PRODUCT_ID_MONTHLY`, `APPSTORE_PRODUCT_ID_INTENSIVE_90DAY`, `APPSTORE_PRODUCT_ID_RECRUIT_MONTHLY`, `APPSTORE_PRODUCT_ID_RECRUIT_INTENSIVE_90DAY`, `APPSTORE_PRODUCT_ID_RECRUIT_6MONTH`, `APPSTORE_PRODUCT_ID_RECRUIT_ANNUAL`, plus `APPSTORE_BUNDLE_ID=com.badgeday.app`. Spec does **not** invent live id strings; ops fills them to match App Store Connect products at amount parity with web/Play.

### F. Privacy / review hygiene (repo-landable)

26. iOS permission usage descriptions exist for Camera, Photo Library / limited photos (if used), and any Files access wording Apple requires for the chosen picker path — accurate to what the app does (Promote SOG/packet upload; Recruit voice already disclosed elsewhere).
27. No change in this slice invents new collection of PHI, incident data, or department identity.

### G. Docs in-repo

28. `mobile/README.md` iOS section is updated so the capability table reads **implemented** (or “landed in web + plugins”) rather than “none implemented.” Point archive / TestFlight upload at the PR 84 Mac CI path (`mobile/ios/TESTFLIGHT_CI.md` / the macos-latest workflow). Do not claim ASC App Review submit. Capabilities implementation (this spec) and CI archive/upload (PR 84) stay separate.
29. `mobile_release_plan.md` step 4 (iOS capability set) is updated to point at this spec and mark code-landed vs Mac CI archive / TestFlight (PR 84; ops+secrets). Do not treat generate-in-CI / archive / TestFlight upload as still-needs-a-registered-Mac.

---

## 4. Data model

### Offline Promote session cache (device-local)

| Field | Type | Required | Notes |
|---|---|---|---|
| `user_id` | string (uuid) | yes | Must match signed-in user |
| `cached_at` | ISO-8601 datetime | yes | When cached while online |
| `session_scope` | `document` \| `whole_list` | yes | Matches how practice was started |
| `document_id` | string \| null | if scope=document | |
| `questions` | array | yes | Each: question id, prompt text, type, choices if any, citation/location fields the online review UI already shows |
| `answers_local` | array | no | Local answers pending sync: question id, response, answered_at |
| `schema_version` | int | yes | Start at 1 |

Persistence: on-device only (Capacitor Preferences / Filesystem). Not a new Supabase table for V1.

### Exam date preference (V1)

| Field | Type | Required | Notes |
|---|---|---|---|
| `exam_date` | date (YYYY-MM-DD) \| null | no | Candidate-set; **device-local for V1** is acceptable so notifications work without a migration. If Gyro prefers a `profiles` column, that is an allowed implementation detail only if it does not block the slice — behavior is “candidate can set/clear a date and notifications follow.” |

### Practice-streak signal (V1)

Device-local last-practice calendar date (UTC date or device-local date — pick one and document in code comments; default **device-local date**). Updated when a Promote quiz answer is submitted or a Recruit board is started while online. Used only to schedule/cancel streak notifications.

### Store products

No new server tables. Existing `store_purchases` + entitlements + `APPSTORE_PRODUCT_ID_*` mapping in `app/billing/module.py` / `app/config.py` remain authoritative.

---

## 5. Edge cases and failure handling

| Case | Expected |
|---|---|
| Camera permission denied | Message + Settings path; upload via Files still available |
| Cached session from another user after account switch | Ignored / cleared; no questions shown from prior user |
| Cache older than questions regenerated server-side | Online practice remains source of truth; stale cache may show until user re-caches; do not POST answers for unknown question ids without a clear error |
| Offline + Recruit open | “Needs connection” — no recording start |
| StoreKit user cancels sheet | Paywall stays; no error red banner required |
| Purchase verified by Apple but `POST .../purchase` 402/503 | Show server message; do not claim entitled |
| Notification permission denied | Streak/exam features idle; practice works |
| Exam date in the past | No future countdown scheduled; optional one-shot “date passed” is out of scope |
| App Store subscriber opens Stripe portal | Must not; use `managed_by` to route correctly |
| Duplicate report of same transaction | Server already updates same row — client may retry restore safely |

---

## 6. Dependencies and prerequisites

- Existing Capacitor shell: `mobile/ios/capacitor.config.json` (`appId` `com.badgeday.app`, `server.url` `https://app.badgeday.com`).
- Declared plugins already in `mobile/ios/package.json`: `@capacitor/filesystem`, `@capacitor/camera`, `@capacitor/local-notifications` (and core/app/splash). StoreKit bridge dependency is **not** yet declared — add whatever Gyro chooses that can complete IAP and yield a transaction id for `POST /billing/store/appstore/purchase` (behavior-specified only).
- Server: `POST /billing/store/appstore/purchase`, `POST /billing/store/appstore/notifications`, `/me` `managed_by`, module mapping for App Store product ids — already built; configuration may still 503 until ops credentials + product ids exist.
- Promote documents upload + quiz/review APIs — already live on web.
- Ops (not Gyro alone): create App Store Connect IAP products at amount parity (still **HELD** — lawyer; do not invent `APPSTORE_PRODUCT_ID_*`); fill `APPSTORE_*` env on Azure; sandbox Apple ID for proving run (five-step sequence in `mobile_release_plan.md`). Archive / TestFlight upload is the Mac CI path from PR 84 (`mobile/ios/TESTFLIGHT_CI.md` / macos-latest workflow) — ops+secrets, not a registered Mac and not this spec’s 4.2 web/plugin slice. IAP create remains held/ops after that path exists.
- Play Production may still be in review; does not block iOS capability landing in repo.

---

## 7. File touch list (expected)

Gyro may adjust names; this is the blast radius reviewer should expect:

| Area | Likely paths |
|---|---|
| Capacitor package | `mobile/ios/package.json`, lockfile, `capacitor.config.json` (permissions / plugin config only as needed) |
| Native project after sync | `mobile/ios/ios/**` Info.plist usage strings (produced on Mac sync — document required keys in README if the Xcode project is not in git yet) |
| Web: platform detect | small helper under `web/src/lib/` |
| Web: Promote upload | `web/src/ui/Documents.tsx` (+ thin native picker helper) |
| Web: offline cache + quiz | `web/src/ui/Quiz.tsx` / `Review.tsx` and/or `web/src/lib/offlinePractice.ts` |
| Web: notifications + exam date | `web/src/ui/Account.tsx`, small lib for schedule/cancel |
| Web: App Store till | `web/src/ui/Paywall.tsx`, `web/src/lib/` storeKit billing helper parallel to `playBilling` |
| API client | `web/src/lib/api` billing report App Store purchase / restore |
| Docs | `mobile/README.md`, `mobile_release_plan.md` step 4 |

No requirement to change Python store verification in this slice unless a gap blocks AC 21–25.

---

## 8. Cost / risk flags

- **Paid / ops:** App Store Connect IAP creation; Apple fees ~15% SBP; sandbox proving needs a Mac + device.
- **New dependency:** StoreKit Capacitor plugin (or equivalent) — new native dependency.
- **Possible schema:** only if exam date is persisted server-side (optional; device-local preferred for V1).
- **AI / candidate-facing notification copy:** route streak/exam notification strings to Red before shipping wording that reads as coaching.
- **Open product decision (do not invent):** account deletion while App Store subscription is live (`mobile_release_plan.md`).

---

## 9. Open questions

1. **Notification copy** — neutral placeholders until Red signs candidate-facing reminder strings.
2. **Account deletion + live Apple subscription** — still Grant’s product call; this spec does not implement refuse-vs-warn.
3. **IAP price parity vs uplift** — V1 assumes parity with web/Play amounts; Grant may later raise store prices.
4. **Camera upload format** — if backend rejects images, does V1 ship Files-only for upload-to-API and treat camera as “scan to Photos then pick,” or require client-side PDF wrapping? Gyro proposes the smallest path that satisfies AC 5 without a new ingestion MIME type unless already supported.
5. **Exam date server sync** — V1 allows device-local only; confirm if multi-device exam date sync is needed before ASC submit (not required to land repo capabilities).

---

## 10. Test plan (repo-landable; device proving later)

### Automated / web-testable where possible

- Platform detect: native entry points gated off on non-iOS-shell.
- Offline cache read/write unit tests for schema_version 1 payload.
- Paywall till selection: iOS shell → appstore path; browser → stripe; TWA → play (existing).
- Billing client: report App Store purchase posts expected body shape to `/billing/store/appstore/purchase`.

### Manual on device (out of scope to execute on Linux; required before ASC)

Physical-device proving stays out of this Linux workstream. Archive / TestFlight upload is the Mac CI workflow from PR 84 (`mobile/ios/TESTFLIGHT_CI.md`) when secrets exist — not impossible, and not something this spec re-implements.

- Files pick PDF → appears in reading list.
- Camera capture path → upload or clear refusal.
- Airplane mode → cached Promote session drills; Recruit blocked cleanly.
- Notification permission → streak after missed day; exam-date 7-day / day-of.
- Sandbox StoreKit purchase → immediate unlock; restore after reinstall; notification renew/cancel/refund per `mobile_release_plan.md` five-step sequence.

---

## 11. Gyro hand-off

Implement in priority order A/B → C → D → E. Land in-repo so the Mac CI generate/sync/archive path (PR 84) stays mechanical. TestFlight upload is that macos-latest workflow (`mobile/ios/TESTFLIGHT_CI.md`), not something Gyro invents ad hoc. IAP product create stays **HELD** (lawyer). Do not invent `APPSTORE_PRODUCT_ID_*` values. Do not resolve account-deletion-with-live-Apple-sub without Grant. Soft constraint on FD identity unchanged.

When notification strings are ready for candidates, route to Red before release copy ships.
