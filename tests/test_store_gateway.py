"""Assembling the store gateways, and refusing on behalf of a store that is not there.

The real gateways cannot be tested here — they need a service account, an App Store Connect
key and a live purchase, and the suite has no credentials by design. What CAN be tested, and
is worth more than it looks, is everything around them: that an unconfigured store refuses
rather than crashes, that one store's absence does not take the other down, and that the
dependency can actually be constructed.

That last one is not hypothetical. The first version of `get_store_gateway` cached on the
settings object with `@lru_cache`, which raises TypeError on a pydantic model — so every
store endpoint answered 500 instead of 503, and no test that mocked the gateway could
possibly have noticed.
"""

import pytest

from app.api.deps import get_store_gateway
from app.billing.store_gateway import (
    StoreGateways,
    StoreNotConfigured,
    build_store_gateway,
)
from app.config import Settings


def _settings(**overrides: object) -> Settings:
    return Settings(**overrides)


def test_the_dependency_can_actually_be_built() -> None:
    """Constructing it must not raise. See the module docstring for why this exists."""
    gateway = get_store_gateway(_settings())
    assert gateway is not None


def test_the_dependency_is_built_once() -> None:
    assert get_store_gateway(_settings()) is get_store_gateway(_settings())


def test_no_store_configured_refuses_every_path() -> None:
    gateway = build_store_gateway(_settings())

    with pytest.raises(StoreNotConfigured):
        gateway.verify_play_purchase(purchase_token="t", product_id="p", user_id="u")
    with pytest.raises(StoreNotConfigured):
        gateway.verify_appstore_purchase(transaction_id="t", user_id="u")
    with pytest.raises(StoreNotConfigured):
        gateway.read_play_notification(payload=b"{}", authorization="")
    with pytest.raises(StoreNotConfigured):
        gateway.read_appstore_notification(payload=b"{}")


def test_one_store_being_absent_does_not_disable_the_other() -> None:
    """Launching on Play weeks before Apple is the expected order, not an edge case."""

    class _Play:
        def verify_play_purchase(self, **_: object) -> str:
            return "confirmed"

    gateway = StoreGateways(play=_Play(), appstore=None)

    assert gateway.verify_play_purchase(purchase_token="t", product_id="p", user_id="u")
    with pytest.raises(StoreNotConfigured):
        gateway.verify_appstore_purchase(transaction_id="t", user_id="u")


def test_a_store_that_failed_to_start_says_why() -> None:
    """A bad credential must surface as its own reason, not as a generic 'not configured'.

    Otherwise the operator reads "App Store billing is not configured", goes and checks that
    the credentials are set — and they are.
    """
    gateway = StoreGateways(
        appstore_error="App Store billing failed to start: APPSTORE_ROOT_CERTS is empty."
    )
    with pytest.raises(StoreNotConfigured, match="ROOT_CERTS"):
        gateway.read_appstore_notification(payload=b"{}")


def test_apple_is_not_considered_configured_without_its_root_certificates() -> None:
    """Credentials without roots is a verifier that rejects every real notification.

    Treating that as configured would answer 400 — "your notification is forged" — to
    notifications that are perfectly genuine, and point the investigation at Apple.
    """
    with_credentials_only = _settings(
        appstore_bundle_id="com.badgeday.app",
        appstore_issuer_id="issuer",
        appstore_key_id="key",
        appstore_private_key="-----BEGIN PRIVATE KEY-----",
    )
    assert with_credentials_only.appstore_configured is False

    with_roots = _settings(
        appstore_bundle_id="com.badgeday.app",
        appstore_issuer_id="issuer",
        appstore_key_id="key",
        appstore_private_key="-----BEGIN PRIVATE KEY-----",
        appstore_root_certs="Zm9v",
    )
    assert with_roots.appstore_configured is True
