# BD-A-001 — SignIn: burned magic-link errors and emailed OTP

Status: durable AC for Baymax / Gyro (extracted from BadgeDay PR 59 body + shipped behavior)
Product: BadgeDay (shared SignIn for Recruit and Promote)
Repo: https://github.com/sirenstosyntax/BadgeDay
Author: Geppetto
Date: 2026-09-10
Audience: Baymax (verify), Gyro (maintain), Zazu (ops)

This spec defines behavior only. Library and function names are Gyro's call except where an existing public string must stay character-for-character.

Related PR (implementation source): https://github.com/sirenstosyntax/BadgeDay/pull/59

---

## 1. User story

A candidate whose email client (Yahoo Mail, Safe Links, or similar) prefetches the one-time magic-link URL can still sign in: SignIn shows that the link is spent or invalid, and they can type the 6 to 8 digit (inclusive) code from the same email instead of depending on the button surviving prefetch.

---

## 2. Scope

### In

- Surface Supabase auth redirect errors on SignIn (`#error=…` / `?error=…`, including `otp_expired`).
- Strip those error params from the address bar after they are shown once (refresh must not keep re-showing a spent link).
- Keep magic-link send (`signInWithOtp` / email me a sign-in link) unchanged in product meaning.
- When an email has been sent — and whenever an email address is present — show a code field for 6 to 8 digit (inclusive) OTP.
- Submit verifies with email + token (OTP type for the same passwordless email path). Wrong code shows an error; happy-path magic-link session exchange remains available when the link is still valid.
- Copy that tells the user to type the code if the email button does nothing.

### Out

- Supabase dashboard, email template redesign, or auth-provider migration.
- Password auth, OAuth, phone OTP.
- Changing Recruit / Promote product gates after session exists.
- Play / App Store billing flows.

---

## 3. Acceptance criteria

Each item is independently verifiable.

### Redirect errors

1. When the app loads SignIn with a live `otp_expired` (or equivalent “invalid or has expired”) error in the URL hash **or** query string, SignIn shows this message character-for-character:

   > This sign-in link is invalid or has expired. Type the code from the email if the button did nothing, or request a new email.

2. Other auth redirect errors that include a description show that description (sentence-terminated if needed) plus a retry hint that the user can type the code or request a new email. They do not remount as a blank form with no message.
3. A token-bearing magic-link hash (`access_token` / session exchange) is **not** treated as an error.
4. After a redirect error is shown, the error params are removed from the address bar so a refresh does not keep displaying a spent-link message from a cleared URL. Remount (e.g. Strict Mode) must not lose the already-consumed message for that page load.

### Magic link send

5. Candidate can enter an email and request a sign-in email. On success, SignIn confirms the email was sent and that if the button does nothing they should type the code from the email.
6. Failed send shows a visible error; it does not claim success.

### OTP code path

7. After a successful send, **or** whenever a plausible email is present on the form, a “Code from the email” field is visible.
8. The field accepts 6 to 8 digits inclusive after normalize (spaces/punctuation stripped). Length 7 is valid. Incomplete means fewer than 6 digits after normalize; incomplete codes cannot submit as success.
9. Submitting a complete code attempts verification for that email. Wrong/expired code surfaces an error and leaves the candidate able to retry or request a new email.
10. Successful verification establishes a session (candidate is signed in). Remembered in-progress sign-in email is cleared on success and on sign-out.
11. After send, the candidate can request a new email or choose a different email without being stuck on a dead screen.

### Non-goals / regressions

12. Valid magic-link click that still has an unused token continues to establish a session (existing `detectSessionInUrl` behavior). This slice must not break that path.
13. No password field is introduced.

---

## 4. Data / client shape

| Concern | Behavior |
|---|---|
| Redirect error source | URL hash and/or query: `error`, `error_code`, `error_description` |
| OTP length | Digits only after normalize; complete when length is 6–8 inclusive (7 allowed) |
| Remembered email | Optional client-side remember of the address used for the current sign-in attempt so a burned-link return can still show the code field; cleared on successful verify and on sign-out |

No new server tables required for this slice.

---

## 5. Edge cases

| Case | Behavior |
|---|---|
| Prefetch burns link before human click | AC1 message + code field path |
| Empty location / no error params | No error banner |
| Description without `otp_expired` code | AC2 |
| User refreshes after consume | Error params gone; do not invent a new error |
| 7-digit typed code | Accept (AC8 is inclusive 6–8, not 6-or-8-only) |
| Network failure on verify | Visible error; stay on SignIn |

---

## 6. Dependencies

- Existing Supabase passwordless email / magic-link configuration.
- SPA SignIn route and session detection already used by BadgeDay web.

**Cost:** no new paid API. No schema migration.

**AI / evaluation:** none. Red review not required for this slice.

---

## 7. Open questions

1. Exact non-expired redirect copy beyond AC1 may vary by Supabase description text — AC2 allows description + retry hint rather than hardcoding every provider string.
2. Whether remembered email uses localStorage vs session-only storage is Gyro's call; AC10 only requires clear-on-success and clear-on-sign-out.

---

## Hand-off

- Baymax: use this file as the durable AC list for PR 59 and future SignIn auth regressions (not only the PR body).
- Gyro: keep AC1 string character-for-character when touching burned-link messaging.
