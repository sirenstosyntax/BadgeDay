"""Google Play, for real.

Two things happen here, and the file exists because neither is optional:

  1. **The push is authenticated.** A Real-time Developer Notification arrives as a Cloud
     Pub/Sub push — an ordinary POST to a public URL — carrying an OIDC token in the
     Authorization header. Verifying that token against Google's keys, and then checking it
     was issued for OUR audience and signed by OUR service account, is the entire
     credential. Without all three checks the endpoint grants subscriptions to strangers.
  2. **The purchase is looked up.** The notification carries a purchase token and a
     notification type, and nothing else — no expiry date, no account. Those live behind a
     Play Developer API call, which is also the only thing that can confirm a purchase the
     Android app *claims* to have made.

WHY THE NOTIFICATION'S STATE WINS OVER THE LOOKUP'S. A revoked purchase — refunded or
charged back — shows up in `subscriptionsv2.get` as SUBSCRIPTION_STATE_EXPIRED, which is
indistinguishable from a subscription that simply ran its course. The notification knows
the difference (type 12 versus type 13) and the lookup does not. Since a revocation must
end access immediately while an expiry lets the paid-through date stand, the notification's
verdict is kept and the lookup is used only for the facts it alone has.

Nothing here is exercised by the test suite. It cannot be: every path needs a service
account, a Pub/Sub subscription and a real purchase. The mapping it feeds, which is where
the decisions actually live, is tested exhaustively in test_store_plan.py.
"""

import base64
import binascii
import json
import logging
import re
from datetime import UTC, datetime

from app.billing.store import PurchaseFacts, StoreState
from app.billing.store_gateway import StoreVerificationError
from app.billing.store_payloads import parse_play_notification
from app.config import Settings

logger = logging.getLogger(__name__)

_SCOPE = "https://www.googleapis.com/auth/androidpublisher"

# subscriptionsv2's own state vocabulary. Used for the app's purchase report, where there is
# no notification to be more specific than this.
#
# CANCELED is the one to read twice: it means auto-renew is off, NOT that the subscription
# has ended. Google keeps serving it until the expiry, and so do we.
_SUBSCRIPTION_STATE: dict[str, StoreState | None] = {
    "SUBSCRIPTION_STATE_ACTIVE": "purchased",
    "SUBSCRIPTION_STATE_CANCELED": "auto_renew_off",
    "SUBSCRIPTION_STATE_IN_GRACE_PERIOD": "grace_period",
    "SUBSCRIPTION_STATE_ON_HOLD": "on_hold",
    "SUBSCRIPTION_STATE_PAUSED": "expired",
    "SUBSCRIPTION_STATE_EXPIRED": "expired",
    # Nothing has been paid yet — a pending purchase awaiting cash or a parent's approval.
    # Deliberately None rather than a state: there is no entitlement to record, and writing
    # one would grant access to a purchase that may never complete.
    "SUBSCRIPTION_STATE_PENDING": None,
    "SUBSCRIPTION_STATE_UNSPECIFIED": None,
}


class PlayGateway:
    """StoreGateway, backed by Google Play. Constructed only when `play_configured`."""

    def __init__(self, settings: Settings) -> None:
        self._package = settings.play_package_name
        self._audience = settings.play_pubsub_audience
        self._service_account = settings.play_pubsub_service_account
        self._subscription_products = settings.subscription_product_ids
        self._key_info = json.loads(settings.play_service_account_json)
        self._client = None

    # --- Play Developer API ---------------------------------------------------

    def _androidpublisher(self):
        """Built lazily and cached: constructing it does network I/O for the discovery doc."""
        if self._client is None:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            credentials = service_account.Credentials.from_service_account_info(
                self._key_info, scopes=[_SCOPE]
            )
            self._client = build(
                "androidpublisher", "v3", credentials=credentials, cache_discovery=False
            )
        return self._client

    def _look_up_subscription(self, purchase_token: str) -> dict:
        try:
            return (
                self._androidpublisher()
                .purchases()
                .subscriptionsv2()
                .get(packageName=self._package, token=purchase_token)
                .execute()
            )
        except Exception as exc:
            # Deliberately broad. googleapiclient raises HttpError for a token Google does
            # not recognise and a spread of transport errors otherwise, and the caller's
            # response is the same either way: grant nothing.
            raise StoreVerificationError(f"Play would not confirm the purchase: {exc}") from exc

    def _look_up_product(self, purchase_token: str, product_id: str) -> dict:
        try:
            return (
                self._androidpublisher()
                .purchases()
                .products()
                .get(packageName=self._package, productId=product_id, token=purchase_token)
                .execute()
            )
        except Exception as exc:
            raise StoreVerificationError(f"Play would not confirm the purchase: {exc}") from exc

    # --- The app's own report --------------------------------------------------

    def verify_play_purchase(
        self, *, purchase_token: str, product_id: str, user_id: str
    ) -> PurchaseFacts:
        if product_id in self._subscription_products:
            return self._subscription_facts(purchase_token, product_id, user_id=user_id)
        return self._product_facts(purchase_token, product_id, user_id=user_id)

    def _subscription_facts(
        self,
        purchase_token: str,
        product_id: str,
        *,
        user_id: str | None,
        state: StoreState | None = None,
    ) -> PurchaseFacts:
        purchase = self._look_up_subscription(purchase_token)

        resolved = state or _SUBSCRIPTION_STATE.get(purchase.get("subscriptionState", ""))
        if resolved is None:
            raise StoreVerificationError(
                f"purchase is not in a state that grants anything: "
                f"{purchase.get('subscriptionState')}"
            )

        facts = PurchaseFacts(
            platform="play",
            product_id=product_id,
            purchase_identifier=purchase_token,
            kind="subscription",
            state=resolved,
            expires_at=_latest_expiry(purchase),
            user_id=user_id or _account_id(purchase),
        )
        # Play refunds an unacknowledged purchase after three days. Digital
        # Goods v2.1 has no acknowledge() for a subscription, so this is the
        # production path — same reason DrillGround posts to its ack endpoint.
        self._acknowledge(product_id, purchase_token, subscription=True)
        return facts

    def _product_facts(
        self,
        purchase_token: str,
        product_id: str,
        *,
        user_id: str | None,
        state: StoreState | None = None,
    ) -> PurchaseFacts:
        purchase = self._look_up_product(purchase_token, product_id)

        if state is None:
            # 0 purchased, 1 canceled, 2 pending. A pending purchase has paid nothing yet.
            purchase_state = purchase.get("purchaseState")
            if purchase_state == 0:
                state = "purchased"
            elif purchase_state == 1:
                state = "revoked"
            else:
                raise StoreVerificationError("purchase is still pending")

        facts = PurchaseFacts(
            platform="play",
            product_id=product_id,
            purchase_identifier=purchase_token,
            kind="pass",
            state=state,
            # A one-time pass has no expiry of Google's; how long it grants access is our
            # decision, applied where the pass is recorded rather than invented here.
            expires_at=None,
            user_id=user_id or purchase.get("obfuscatedExternalAccountId") or None,
        )
        self._acknowledge(product_id, purchase_token, subscription=False)
        return facts

    def verify_appstore_purchase(self, *, transaction_id: str, user_id: str) -> PurchaseFacts:
        raise StoreVerificationError("This gateway is Google Play only.")

    # --- Notifications ---------------------------------------------------------

    def read_play_notification(self, *, payload: bytes, authorization: str) -> PurchaseFacts | None:
        self._verify_push_token(authorization)

        notification = parse_play_notification(_decode_pubsub_envelope(payload))
        if notification is None:
            return None

        # The notification's verdict, not the lookup's — see the module docstring. The
        # lookup is still made, for the expiry and the account token it alone carries.
        if notification.kind == "subscription":
            return self._subscription_facts(
                notification.purchase_token,
                notification.product_id,
                user_id=None,
                state=notification.state,
            )
        return self._product_facts(
            notification.purchase_token,
            notification.product_id,
            user_id=None,
            state=notification.state,
        )

    def read_appstore_notification(self, *, payload: bytes) -> PurchaseFacts | None:
        raise StoreVerificationError("This gateway is Google Play only.")

    def _verify_push_token(self, authorization: str) -> None:
        """Three checks, and all three matter.

        Verifying the signature alone proves only that *Google* issued the token — which is
        true of any token from any Google account, including one an attacker made for their
        own project. The audience proves it was minted for this endpoint, and the service
        account proves it was our Pub/Sub subscription that sent it.
        """
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise StoreVerificationError("no bearer token on the push")

        try:
            from google.auth.transport import requests as google_requests
            from google.oauth2 import id_token

            claims = id_token.verify_oauth2_token(
                token, google_requests.Request(), self._audience
            )
        except Exception as exc:
            raise StoreVerificationError(f"push token did not verify: {exc}") from exc

        if not claims.get("email_verified"):
            raise StoreVerificationError("push token carries an unverified email claim")
        if claims.get("email") != self._service_account:
            raise StoreVerificationError("push token was signed by an unexpected account")

    def _acknowledge(self, product_id: str, purchase_token: str, *, subscription: bool) -> None:
        """Tell Play we have the purchase. Failure here must not un-grant.

        The candidate has paid. An acknowledgement problem is ours to chase —
        Play may reverse the charge after three days — and must never look to
        them like the purchase failed. Already-acknowledged is success.
        """
        try:
            publisher = self._androidpublisher()
            if subscription:
                (
                    publisher.purchases()
                    .subscriptions()
                    .acknowledge(
                        packageName=self._package,
                        subscriptionId=product_id,
                        token=purchase_token,
                        body={},
                    )
                    .execute()
                )
            else:
                (
                    publisher.purchases()
                    .products()
                    .acknowledge(
                        packageName=self._package,
                        productId=product_id,
                        token=purchase_token,
                        body={},
                    )
                    .execute()
                )
        except Exception as exc:
            if acknowledge_already_done(exc):
                logger.info("Play purchase already acknowledged: %s", product_id)
                return
            logger.error("Play acknowledge failed for %s: %s", product_id, exc)


def acknowledge_already_done(exc: BaseException) -> bool:
    """Google answers 400 when the token was acknowledged on an earlier pass."""
    text = str(exc).lower()
    return "already" in text and "acknowledg" in text


def _decode_pubsub_envelope(payload: bytes) -> dict:
    """Unwrap the Pub/Sub push envelope to the RTDN inside it.

    The envelope is `{"message": {"data": "<base64 of the RTDN>"}}`. Malformed input is a
    verification failure rather than a crash: this endpoint is public, so anything at all
    can arrive at it.
    """
    try:
        envelope = json.loads(payload)
        encoded = envelope["message"]["data"]
        return json.loads(base64.b64decode(encoded))
    except (ValueError, KeyError, TypeError, binascii.Error) as exc:
        raise StoreVerificationError(f"not a Pub/Sub push envelope: {exc}") from exc


def _latest_expiry(purchase: dict) -> datetime | None:
    """The furthest expiry across the subscription's line items.

    A subscription can carry more than one line item — an upgrade mid-period leaves both
    briefly — and access should run to the last of them. Taking the first would cut a
    candidate off at a date they have already paid past.
    """
    expiries = []
    for item in purchase.get("lineItems") or []:
        parsed = _parse_rfc3339(item.get("expiryTime"))
        if parsed:
            expiries.append(parsed)
    return max(expiries) if expiries else None


# Google emits RFC3339 with NANOSECOND precision — "2026-09-30T12:00:00.123456789Z".
# datetime.fromisoformat accepts at most six fractional digits, so the tail is trimmed
# before parsing. Getting this wrong is a silently missing expiry, which reads downstream as
# "this purchase has no paid-through date" and cuts off a candidate who has one.
_RFC3339 = re.compile(
    r"^(?P<stamp>\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<fraction>\d+))?"
    r"(?P<offset>[Zz]|[+-]\d{2}:?\d{2})?$"
)


def _parse_rfc3339(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None

    match = _RFC3339.match(value.strip())
    if not match:
        logger.warning("could not parse an expiry time from Play: %r", value)
        return None

    text = match.group("stamp")
    fraction = match.group("fraction")
    if fraction:
        text += f".{fraction[:6]}"
    offset = match.group("offset") or ""
    text += "+00:00" if offset in ("Z", "z") else offset

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        logger.warning("could not parse an expiry time from Play: %r", value)
        return None
    # A timestamp with no offset is treated as UTC, which is what Google sends. Leaving it
    # naive would make every later comparison against an aware `now` raise.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _account_id(purchase: dict) -> str | None:
    """The candidate id the app attached at purchase time, if it did."""
    identifiers = purchase.get("externalAccountIdentifiers") or {}
    return identifiers.get("obfuscatedExternalAccountId") or None
