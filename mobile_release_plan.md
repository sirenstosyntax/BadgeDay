# BadgeDay — App Store and Google Play release plan

*Decisions of 2026-08-16. Policy facts verified against primary sources on that date and
dated individually below, because both stores changed their payment rules materially in the
fifteen months before it and will again.*

## What was decided, and what it reverses

`CLAUDE.md` listed **"Native mobile apps (responsive web only)"** as explicitly out of
scope. That is reversed. Three decisions, taken together:

| Question | Decision |
|---|---|
| How do we reach the stores? | **Wrap the existing web app.** Trusted Web Activity for Play, Capacitor for iOS. No rewrite, no second codebase for the product itself. |
| How do people pay inside the apps? | **The store's billing inside the apps; Stripe stays on the web.** |
| When do real payments start? | **Unchanged — not until Promote and Recruit are both built.** The launch gate in `CLAUDE.md` stands. |

The third decision is the one that sets the schedule, and it is worth being plain about
what it means: **none of the work in this document puts money in the bank.** Recruit is on
the critical path to revenue and everything here runs alongside it. What this work buys is
that the store side is not *also* three months of lead time once Recruit is done — much of
it (account enrolment, D-U-N-S, closed testing) is waiting rather than building, and
waiting can be done in parallel.

## What each store actually requires

### Google Play

**Play no longer forces you to use Play Billing.** This changed on 2026-06-30 and it is
recent enough to be worth stating carefully, because the widely-known version of this rule
is now wrong.

Under the expanded billing choice programme, a developer in the US, UK or EEA may take
subscription payments through their own system or send the user to a web checkout. Google
separated its two fees to make this possible:

| | Play's service fee | Billing fee | Total |
|---|---|---|---|
| Play Billing | 10% (first $1M/yr) | 5% (US/UK/EEA) | **15%** |
| Own billing / external link | 10% (first $1M/yr) | — | **10%** |

*(Verified 2026-08-16 against the Android Developers Blog announcement and Play Console
Help. The 10% service fee applies to auto-renewing subscriptions regardless of how they
are paid for.)*

**The 5% is not the whole difference.** Choosing own-billing means enrolling in the
programme and, from 2026-10-01, reporting transactions and successful downloads to Google
and remitting the service fee yourself. For a solo operator that is a recurring compliance
obligation against a 5% saving on a $29/month product — roughly $1.45 a subscriber-month.
**Recommendation: use Play Billing.** Google handles tax, refunds, dunning and the
reporting; the 5% buys all of it. Revisit if BadgeDay ever has enough subscribers that 5%
pays for a bookkeeper.

Two hard dates and one exemption:

- **Billing Library v8 or later is required for all new apps from 2026-08-31**, with an
  extension available to 2026-11-01. The TWA wrapper's `android-browser-helper` version
  determines this, so it must be pinned deliberately rather than inherited from whatever
  Bubblewrap generates.
- **Closed testing: 12 testers, opted in continuously for 14 days**, before production
  access — for **personal** developer accounts created after 2023-11-13. Since April 2026
  Google also rejects production requests where testers did not genuinely use the app.
- **Organisation accounts are exempt from that entirely.** They require a D-U-N-S number.
  Sirens to Syntax LLC has a legal entity, so **register the Play account as an
  organisation.** This is the single highest-leverage scheduling decision in this
  document: it removes a hard 14-day gate that cannot be compressed, and it is free.

### Apple

**Guideline 3.1.1 still requires In-App Purchase for digital subscriptions**, at 15% under
the Small Business Programme (which BadgeDay qualifies for, under $1M/yr) rather than 30%.

**On the United States storefront only**, since the May 2025 App Review Guidelines update
made for the Epic injunction, an app may include buttons, external links and other calls to
action pointing at an outside purchase method, and **no entitlement is required**. Outside
the US — UK, Canada, Australia, Japan, the EEA — the same UI is still a 3.1.1 violation.
*(Verified 2026-08-16.)*

We are not taking that route at launch. It means two behaviours by region inside one
binary, on a submission that already carries the 4.2 risk below, to save 15% on a product
that has not yet sold one subscription. It is written down here because it is a real option
worth revisiting once there is revenue to measure it against.

**The material risk is guideline 4.2, minimum functionality.** A WebView wrapper around a
website is the archetypal 4.2 rejection, and BadgeDay's iOS app is exactly that unless it
is deliberately more. What is planned to clear it, in descending order of how much reviewers
appear to weigh it:

- **Document upload from the device** — Files, iCloud Drive, and the camera as a scanner.
  This is the app's central action and it is genuinely better native than in mobile Safari.
- **Offline practice.** Questions and their citations already exist as data; caching a
  session so a candidate can drill on an engine with no signal is a real capability the
  website cannot offer.
- **Local notifications** for a practice streak and an exam-date countdown.
- **Native StoreKit purchase**, which is itself evidence of an app rather than a shortcut.

Apple-specific requirements BadgeDay already meets, worth noting so nobody rebuilds them:
in-app account deletion (5.1.1(v)) exists as `DELETE /me`; privacy policy and terms are
served and linked; sign-in is a magic link rather than a third-party identity provider, so
**Sign in with Apple is not required**.

## What is built

Committed on this branch:

- **Migration 0008** — `store_purchases`, and `has_access` widened to ask both tills. Store
  purchases get their own table rather than columns on `profiles`; the reasoning is in the
  migration's header and it is not a stylistic choice.
- **`app/billing/store.py`** — the pure decision: a verified purchase to the entitlement
  writes it implies.
- **`app/billing/store_payloads.py`** — Google's and Apple's notification vocabularies
  mapped to ours, enumerated in full including the types that mean nothing.
- **`app/api/store.py`** — four endpoints: the app reporting its own purchase (so the
  unlock is immediate), and each store's notification path (renewals, cancellations,
  refunds, expiries).
- **`/me` now reports `managed_by`** so the account screen can send an App Store subscriber
  to the App Store to cancel, rather than to a Stripe portal that will show them nothing.
- 37 tests, covering the mapping exhaustively.

## Verification is the launch blocker

`app/billing/store_gateway.py` ships the seam and a gateway that **refuses every call**.
The endpoints answer 503. That is deliberate and it is the honest state, not an oversight:
a store notification is an unauthenticated POST to a public URL whose entire job is to grant
paid access, and an implementation that decodes the payload without verifying it is not a
partial implementation — it is a subscription for anyone who can spell JSON.

What each store needs before that gateway can be written:

**Google Play**
1. A service account with the *View financial data* grant, linked to the Play Console.
2. A Cloud Pub/Sub topic and push subscription pointed at
   `/billing/store/play/notifications`, and the OIDC token on each push verified against
   Google's keys **and** checked for the configured audience and service account.
3. `purchases.subscriptionsv2.get` / `purchases.products.get` called on the purchase token —
   the notification carries no expiry date, so without this call there is nothing to write
   into `expires_at`.

**Apple**
1. An App Store Connect API key (issuer id, key id, .p8).
2. JWS verification of the notification and of both nested payloads against the `x5c`
   certificate chain, up to Apple's root CA, **with the chain actually validated** rather
   than the leaf simply decoded.
3. App Store Server API lookup for the app's own purchase report.

Neither can be exercised from this repository's test suite, which has no credentials by
design. Both need a real device and a sandbox account to prove out. Budget a working day
per store once the accounts exist, plus a sandbox purchase run.

## Two open decisions that need Grant

**1. Account deletion while a store subscription is live.** `DELETE /me` stops Stripe
billing before it deletes anything, precisely so nobody is left being charged for an account
they can no longer reach. Neither store lets us do the equivalent cleanly: Play's API can
cancel a subscription, **Apple's cannot** — only the subscriber can, from their own device.

So an iOS subscriber who deletes their BadgeDay account keeps being charged by Apple, with
nothing left in our app to explain it. The two ways out conflict with each other:

- *Refuse the deletion* until they cancel in the App Store. Protects them from being
  charged, but sits badly against the privacy constraint's unqualified "hard-deletable".
- *Delete, and warn hard.* Honours the constraint literally; some people will not read the
  warning and will be charged for months.

**Recommendation: delete, and warn hard** — a modal naming the exact Settings path, plus a
confirmation email — with Play subscriptions cancelled server-side first since that one we
*can* do. The privacy promise is unqualified and should stay that way. Not implemented
either way; it is a product decision, not an implementation detail.

**2. Store pricing.** Play Billing costs 15% and Apple 15%, against Stripe's ~2.9% + 30¢.
On a $29/month subscription that is roughly $4.35 versus $1.14. Either absorb it, or price
the in-app products higher than the web — which both stores permit, and which every large
subscription app does. Needs a decision before the products are created in either console,
because the product ids are baked into the builds.

## What Grant has to do, in order

Nothing below is code, and the first three have lead times measured in weeks — they are the
reason to start now rather than when Recruit is finished.

1. **Get a D-U-N-S number for Sirens to Syntax LLC** if there isn't one. Free from Dun &
   Bradstreet, typically days to a few weeks. It gates *both* organisation enrolments.
2. **Enrol in the Apple Developer Program as an organisation** ($99/yr). Verification takes
   days to weeks.
3. **Register the Google Play developer account as an organisation** ($25 once). This is
   what skips the 12-testers/14-days gate.
4. **Decide the two open questions above** — deletion-with-a-live-store-subscription, and
   store pricing.
5. **Create the in-app products** in both consoles once pricing is decided, and put their ids
   in the app's configuration. They must match `PLAY_PRODUCT_ID_*` and `APPSTORE_PRODUCT_ID_*`
   exactly; a typo is a purchase flow that opens and then fails with an unhelpful store
   error.
6. **Store listing assets**: screenshots at both stores' required sizes, a 1024×1024 icon,
   a feature graphic for Play, description and keywords. The brand constants in
   `badgeday_infrastructure_map.md` govern, and the hard rule that Grant's fire department
   is never named or identifiable applies to every screenshot.
7. **The data forms**: Apple's privacy nutrition labels and Play's Data safety form. Both
   must match what the app actually collects — uploaded documents, email, and (once Recruit
   ships) voice recordings, which are a sensitive category and are declared as transcribed,
   measured and discarded.

## Order of work on our side

1. ~~Store entitlement path — schema, mapping, endpoints, tests.~~ **Done.**
2. Wrapper projects — TWA and Capacitor. Buildable but not verifiable in CI; neither Xcode
   nor the Android SDK is present in the container this was written in.
3. The two gateway implementations. **Blocked on steps 1–3 of Grant's list.**
4. The iOS capability set that clears 4.2 — upload from Files and camera, offline practice,
   local notifications.
5. Sandbox purchase runs on a real device, both stores.
6. Closed testing, then submission — **after** Recruit ships, per the launch gate.
