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
that the store side is not *also* a long lead time once Recruit is done.

That lead time turned out to be shorter than feared. Both developer accounts already
existed when this was written, and the Play one is an organisation — which exempts it from
the only gate on the store side that could not be compressed by working harder. What
remains is credentials, icons, and the iOS capability set, and none of those has a clock
on it.

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
- **Organisation accounts are exempt from that entirely** — and BadgeDay's is one, so this
  does not apply. See "Settled: the Play account is an organisation" below.

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

## Verification — written, unproven

Both gateways are now implemented: `app/billing/play_gateway.py` and
`app/billing/appstore_gateway.py`. **Neither has ever run against a real store**, and no
test in this repository can change that — every path needs credentials the suite
deliberately does not have. Treat them as code that compiles and is reasoned about, not as
code that is known to work.

Verification is done by each vendor's own library rather than by hand: `google-auth` for the
OIDC token on a Pub/Sub push, `app-store-server-library` for Apple's JWS certificate chain.
That choice is deliberate. The check that actually matters — that the `x5c` chain validates
up to a genuine root — is one a hand-written version can skip while passing every test you
would think to write. It looks like a signature check and verifies no signature.

An unconfigured or failed-to-start store refuses on its own behalf and the endpoints answer
503, so launching on Play weeks before Apple works without touching code.

### What is still needed to switch each one on

**Google Play**
1. A service account with the *View financial data* grant, linked to the Play Console.
   `PLAY_SERVICE_ACCOUNT_JSON` is the whole key file.
2. A Cloud Pub/Sub topic, and a **push** subscription pointed at
   `/billing/store/play/notifications`. Set `PLAY_PUBSUB_AUDIENCE` to that URL and
   `PLAY_PUBSUB_SERVICE_ACCOUNT` to the account the subscription pushes as — both are
   checked on every notification, and without them a signature check proves only that
   *some* Google account signed the token.
3. The RTDN topic named in Play Console under *Monetisation setup*.

**Apple**
1. An App Store Connect API key — issuer id, key id, and the `.p8` contents.
2. `APPSTORE_ROOT_CERTS`: Apple's root certificates as comma-separated base64 DER, from
   <https://www.apple.com/certificateauthority/>. There is no default, and Apple's
   `appstore_configured` check refuses without them — a verifier with an empty trust store
   rejects every genuine notification while looking configured, which presents as Apple
   sending forgeries rather than as a missing setting.
3. `APPSTORE_ENVIRONMENT=sandbox` until the app is live. The sandbox signs with a different
   chain, so getting this wrong rejects everything with what reads like a credential error.

### The proving run

Both need a real device and a sandbox account. The sequence worth running, per store, in
this order:

1. A sandbox purchase → the app's own report unlocks immediately.
2. A sandbox renewal → `expires_at` moves forward.
3. Cancel auto-renew → status goes `canceled` **and access continues** to the paid-through
   date. This is the one most likely to be wrong and the one a candidate would notice.
4. A sandbox refund → access ends immediately, expiry cleared.
5. A replayed notification → updates the same row rather than creating a second.

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

Nothing below is code.

**Both developer accounts already exist** (confirmed 2026-08-16), which removes what would
otherwise have been the longest lead time on this list.

1. **Generate the credentials** for each store, per "What is still needed to switch each one
   on" above. This is the only thing standing between the code and a working purchase.
2. **Decide the two open questions above** — deletion-with-a-live-store-subscription, and
   store pricing.
3. **Create the in-app products** in both consoles once pricing is decided, and put their ids
   in the app's configuration. They must match `PLAY_PRODUCT_ID_*` and `APPSTORE_PRODUCT_ID_*`
   exactly; a typo is a purchase flow that opens and then fails with an unhelpful store
   error.
4. **Confirm the application id** before the first upload. `com.badgeday.app` is what the
   wrapper configs use, and neither store lets it change afterwards. If an app entry has
   already been created in either console, its id wins and the configs should be changed to
   match.
5. **The icons.** See `web/public/icons/README.md`. Nothing builds without them.
6. **Store listing assets**: screenshots at both stores' required sizes, a feature graphic
   for Play, description and keywords. The brand constants in
   `badgeday_infrastructure_map.md` govern, and the hard rule that Grant's fire department
   is never named or identifiable applies to every screenshot.
7. **The data forms**: Apple's privacy nutrition labels and Play's Data safety form. Both
   must match what the app actually collects — uploaded documents, email, and (once Recruit
   ships) voice recordings, which are a sensitive category and are declared as transcribed,
   measured and discarded.

### Settled: the Play account is an organisation

Confirmed 2026-08-16. Sirens to Syntax LLC, developer account 7304930268481203834, owner
grant@sirenstosyntax.com.

**So the 12-testers-for-14-days requirement does not apply.** It binds personal accounts
created after 2023-11-13; organisation accounts are exempt. That was the only deadline on
the store side that could not be compressed by working harder, and it is gone — recorded
here so nobody re-investigates it, and so nobody plans a fortnight of tester recruitment
that was never owed.

Closed testing is still worth running by choice, on a much shorter loop, because a TWA can
fail on a real device in ways no build catches — Digital Asset Links not verifying leaves
the address bar visible, and a purchase can fail against live Play Billing while working in
every test written here.

## Order of work on our side

1. ~~Store entitlement path — schema, mapping, endpoints, tests.~~ **Done.**
2. ~~Wrapper configs — TWA and Capacitor.~~ **Written, never compiled**; neither Xcode nor
   the Android SDK is present in the container this was written in, and the icons are
   missing.
3. ~~The two gateway implementations.~~ **Written, never run against a store.** Now blocked
   only on the credentials in Grant's step 2.
4. The iOS capability set that clears 4.2 — upload from Files and camera, offline practice,
   local notifications. **This is the largest remaining piece of code**, and it is the one
   that decides whether the iOS submission is accepted at all.
5. Sandbox purchase runs on a real device, both stores — the five-step sequence above.
6. Closed testing, then submission — **after** Recruit ships, per the launch gate.
