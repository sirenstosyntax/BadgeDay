# BadgeDay Play verification, without a JSON key

Project `sirens-to-syntax-play` blocks service-account key creation. BadgeDay
cannot put `PLAY_SERVICE_ACCOUNT_JSON` on Azure, so the live purchase endpoint
answers 503, grants nothing, and does not acknowledge. Google refunds an
unacknowledged purchase after three days.

This directory is a separate Cloud Run service, `badgeday-play-verify`. It
calls the Play Developer API as its runtime service account (the metadata
server). BadgeDay on Azure calls that service with a shared secret. The
secret is a random string, not a Google key.

Do not reuse `drillground-play-ack`. That service is live for package
`com.sirenstosyntax.drillground` and the one product `drillground.packs.v1`.
It does not understand subscriptions, and its Play Console grant is that app
only.

This file does not deploy anything. Merging the pull request does not turn
purchases on.

## What Grant does

Two clicks in Play Console. No pricing decision, no JSON key, no Azure screen.

Run the command in the next section first, so the service account exists.
Then:

1. Play Console → **Users and permissions**. Invite
   `badgeday-play@sirens-to-syntax-play.iam.gserviceaccount.com`.
   App access: **only** `com.badgeday.app` (not DrillGround).
   Permissions, and nothing else:
   - **View financial data, orders, and cancellation survey responses**
   - **Manage orders and subscriptions**
2. Play Console → **Monetise** → real-time developer notifications. Choose
   topic `projects/sirens-to-syntax-play/topics/badgeday-rtdn`.
   That topic is what tells BadgeDay about renewals, cancellations, and
   refunds. The first purchase can unlock without it. A refund will not
   revoke access until this is selected.

Paste each product id from the existing Play products into the Azure settings
listed below, character for character. Do not invent an id. A wrong id lets
Google charge and then BadgeDay refuses to record or acknowledge, which
refunds the buyer after three days and does not unlock the account.

## The command

Someone already logged into `gcloud` on project `sirens-to-syntax-play` runs
this from the repo root. It does not change Azure, Stripe, or Play prices.

```bash
gcloud config set project sirens-to-syntax-play
CONFIRM_PLAY_VERIFY_DEPLOY=1 ./deploy/play-verify/deploy.sh
```

The command creates the service account **without a key**, stores a random
shared secret in Secret Manager, deploys Cloud Run, and creates the Pub/Sub
topic and push subscription. It prints the Cloud Run URL. It does not print
the secret. If this machine created the secret, the value is in
`deploy/play-verify/shared-secret.txt` (gitignored, mode 600). Re-running
does not rotate that secret.

Cloud Run is reachable without a Google login because Azure has no Google
identity. The application rejects every request that lacks the shared secret,
before it reads the body. Do not remove that check.

## Azure setting names

Set these on the next BadgeDay deploy (`./deploy/azure-deploy.sh` reads them
from `.env`). Do not set them by hand in a way the next deploy will wipe, and
do not put the secret in git.

| Name | Value |
| --- | --- |
| `PLAY_PACKAGE_NAME` | `com.badgeday.app` |
| `PLAY_VERIFY_BASE_URL` | the Cloud Run URL the script prints, origin only |
| `PLAY_VERIFY_SHARED_SECRET` | the contents of `shared-secret.txt` |
| `PLAY_PUBSUB_AUDIENCE` | `https://app.badgeday.com/billing/store/play/notifications` |
| `PLAY_PUBSUB_SERVICE_ACCOUNT` | `badgeday-play@sirens-to-syntax-play.iam.gserviceaccount.com` |
| `PLAY_PRODUCT_ID_MONTHLY` | paste from Play Console |
| `PLAY_PRODUCT_ID_INTENSIVE_90DAY` | paste from Play Console |
| `PLAY_PRODUCT_ID_RECRUIT_MONTHLY` | paste from Play Console |
| `PLAY_PRODUCT_ID_RECRUIT_INTENSIVE_90DAY` | paste from Play Console |
| `PLAY_PRODUCT_ID_RECRUIT_6MONTH` | paste from Play Console |
| `PLAY_PRODUCT_ID_RECRUIT_ANNUAL` | paste from Play Console |

Leave `PLAY_SERVICE_ACCOUNT_JSON` empty.

`PLAY_PUBSUB_*` are names. They are how BadgeDay checks that a notification
came from our push subscription. They are not keys.

After that deploy, `GET /ready` on the app reports `play_purchase: true`.
`play_rtdn` stays false until the two Pub/Sub names are set. Neither field
contains a secret.

## What still fails closed

- No verifier URL or secret: purchase endpoint **503**, nothing granted, nothing acknowledged.
- Verifier unreachable or the shared secret does not match: **503**, nothing granted.
- Google does not recognise the token: **402**, nothing granted.
- Product id is not one of the `PLAY_PRODUCT_ID_*` values: nothing is written and Play is not acknowledged, so Google can refund it. This is deliberate. Acknowledging an unknown product would block that refund.
- The service never calls `consume`.
