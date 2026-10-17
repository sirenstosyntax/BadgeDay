"""StripeGateway.read_event against real Stripe verification, no network.

The rest of the billing tests use a fake gateway that hands back a plain dict, so nothing
there exercises the one line that turns a verified Stripe webhook into that dict. That line
had a bug — dict(event) on a StripeObject raises rather than converting — which only a real
event revealed. These tests sign a payload the way Stripe does and run it through the real
StripeGateway, so the conversion is covered and that regression cannot come back unseen.
"""

import hashlib
import hmac
import json
import time

import pytest

from app.billing.gateway import StripeGateway, WebhookVerificationError, checkout_session_params
from app.config import Settings

SECRET = "whsec_test_secret_for_signing"


def _gateway() -> StripeGateway:
    return StripeGateway(Settings(stripe_secret_key="sk_test_x", stripe_webhook_secret=SECRET))


def _signed(payload: bytes, secret: str = SECRET) -> str:
    """A Stripe-Signature header for this payload, computed the way Stripe computes it."""
    timestamp = int(time.time())
    signature = hmac.new(
        secret.encode(), b"%d." % timestamp + payload, hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={signature}"


def test_checkout_params_are_card_only_and_omit_promotion_codes_unless_asked() -> None:
    base = dict(
        mode="payment",
        price_id="price_recruit_90",
        customer_id="cus_1",
        client_reference_id="user-1",
        success_url="https://app.badgeday.test/?checkout=success",
        cancel_url="https://app.badgeday.test/?checkout=cancelled",
    )
    card_only = checkout_session_params(**base)
    assert card_only["payment_method_types"] == ["card"]
    assert "allow_promotion_codes" not in card_only

    with_code = checkout_session_params(**base, allow_promotion_codes=True)
    assert with_code["payment_method_types"] == ["card"]
    assert with_code["allow_promotion_codes"] is True


def test_a_verified_event_comes_back_as_a_plain_nested_dict() -> None:
    body = json.dumps(
        {
            "type": "customer.subscription.updated",
            "data": {"object": {"customer": "cus_1", "status": "active"}},
        }
    ).encode()

    event = _gateway().read_event(payload=body, signature=_signed(body))

    # A plain dict, not a StripeObject — plan_changes reads it with .get(), and the bug this
    # guards against was exactly a value that looked dict-enough to pass tests but wasn't.
    assert type(event) is dict
    assert event["type"] == "customer.subscription.updated"
    assert event["data"]["object"]["customer"] == "cus_1"


def test_a_forged_signature_is_refused() -> None:
    body = b'{"type":"customer.subscription.deleted"}'
    with pytest.raises(WebhookVerificationError):
        _gateway().read_event(payload=body, signature="t=1,v1=deadbeef")


def test_the_wrong_secret_is_refused() -> None:
    """A validly-formed signature from a different secret must not pass — the secret is the
    entire credential the webhook trusts."""
    body = b'{"type":"checkout.session.completed"}'
    forged = _signed(body, secret="whsec_a_different_secret")
    with pytest.raises(WebhookVerificationError):
        _gateway().read_event(payload=body, signature=forged)
