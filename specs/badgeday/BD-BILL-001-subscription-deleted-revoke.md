# BD-BILL-001 — Stripe `customer.subscription.deleted` revoke scope

Status: durable AC for Baymax / Gyro (Geppetto product lock after PR 68 fail-closed webhook)
Product: BadgeDay (Promote profiles + Recruit entitlements)
Repo: https://github.com/sirenstosyntax/BadgeDay
Author: Geppetto
Date: 2026-09-11
Audience: Baymax (verify), Gyro (maintain), Zazu (ops)

Related: [PR 68](https://github.com/sirenstosyntax/BadgeDay/pull/68) merged as `ddf8dd2` (fail-closed grants). This spec is the revoke-side follow-up.

This spec defines behavior only. Library and function names are Gyro's call.

---

## 1. Ruling

On `customer.subscription.deleted` with no mappable `price_id`: **clear Promote** when the Stripe customer maps to a known user. **Do not clear Recruit** without a Recruit price signal.

Grant paths stay fail-closed without `price_id`. A missing or unknown price must not fall open to Promote `plan_changes` on checkout or subscription create/update.

---

## 2. Module scope on delete

1. `price_id` maps promote → clear Promote only.
2. `price_id` maps recruit → clear Recruit only.
3. no mappable `price_id` → resolve customer→user; clear Promote (legacy profiles subscription canceled / Promote path); do not clear Recruit; log customer / subscription / user for ops.

Retrieving subscription items by id to recover `price_id` before (3) is optional and not required.

---

## 3. Acceptance criteria

Each item is independently verifiable.

1. `customer.subscription.deleted` + known customer + Promote entitled + no `price_id` → Promote access is false after the webhook; the webhook acks success.
2. The same event must **not** clear Recruit when Recruit is entitled and there is no Recruit `price_id`.
3. `customer.subscription.deleted` + mapped Recruit `price_id` → Recruit is cleared; Promote is untouched unless that price also implicates Promote.
4. Grant paths (`checkout.session.completed`, `customer.subscription.created` / `updated`) with a blank or unknown `price_id` remain ack-and-ignore (no Promote `plan_changes`, no Recruit entitlement write).

---

## 4. Out of scope

- Filling live Stripe / Play price IDs or enabling `sk_live`.
- Changing checkout, portal, or store acknowledge grant rules beyond the fail-closed lock already shipped in PR 68.
- Voice, department accounts, or any Recruit scoring change.
