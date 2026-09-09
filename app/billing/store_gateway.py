"""The seam between BadgeDay and the two app stores.

The sibling of `gateway.py`, on the same footing: everything that actually talks to Google
or Apple sits behind this protocol, so the endpoints and the entitlement mapping are
testable against a fake with no store account and no network.

WHAT VERIFICATION MEANS HERE, AND WHY THERE IS NO SHORTCUT
----------------------------------------------------------
A store notification is an unauthenticated HTTP POST to a public URL. The signature is the
entire credential — exactly as with Stripe's webhook, and with a worse blast radius,
because the endpoint's whole job is to grant paid access. An implementation that decodes
the payload without verifying it is not a partial implementation; it is a public endpoint
that grants a subscription to anyone who can spell JSON.

Each store makes you do different work for that:

  * **Google Play.** RTDNs arrive through Cloud Pub/Sub push, carrying an OIDC token in the
    Authorization header that must be verified against Google's keys AND checked for the
    audience and service account we configured. The notification body then carries only a
    purchase token — the paid-through date and the account token require a Play Developer
    API call (`purchases.subscriptionsv2.get`, or `purchases.products.get` for a pass)
    authenticated with a service account holding the "View financial data" grant.
  * **Apple.** The POST body is a JWS whose payload is itself two nested JWS blobs. Each
    must be verified against the x5c certificate chain, up to Apple's root CA, with the
    chain's validity actually checked rather than the leaf simply read. `expiresDate` and
    `appAccountToken` come out of the decoded transaction; there is no second call.

Neither is a few lines, and neither can be exercised from this repository's test suite,
which has no credentials by design. So this file ships the seam, the protocol, and a
gateway that REFUSES — and the endpoints answer 503 rather than trusting anything. The
alternative, a gateway that decodes and hopes, is the failure this comment exists to
prevent.

The remaining work, and what it needs, is written up in mobile_release_plan.md under
"Verification is the launch blocker".
"""

import logging
from typing import Protocol

from app.billing.store import PurchaseFacts


class StoreVerificationError(Exception):
    """The payload did not carry a signature we could verify against the store's keys."""


class StoreNotConfigured(Exception):
    """No credentials for this store, so nothing it sends can be trusted or checked."""


class StoreGateway(Protocol):
    """Three operations, which is all the store billing loop needs."""

    def verify_play_purchase(
        self, *, purchase_token: str, product_id: str, user_id: str
    ) -> PurchaseFacts:
        """Confirm a purchase the Android app says it just made, and return its facts.

        Called from the app's own report of a completed purchase, which is what makes the
        unlock immediate rather than waiting on a notification that may be seconds or
        minutes behind. The token is checked against the Play Developer API — the client
        is telling us what to verify, never what to believe.

        Raises StoreVerificationError if Play does not recognise the token or the purchase
        is not in a granting state.
        """
        ...

    def verify_appstore_purchase(
        self, *, transaction_id: str, user_id: str
    ) -> PurchaseFacts:
        """The same, for a StoreKit purchase reported by the iOS app.

        Checked against the App Store Server API rather than trusting the on-device
        receipt, for the same reason.
        """
        ...

    def read_play_notification(self, *, payload: bytes, authorization: str) -> PurchaseFacts | None:
        """Verify a Pub/Sub push and return the facts, or None if it changes no entitlement.

        Raises StoreVerificationError if the OIDC token does not check out.
        """
        ...

    def read_appstore_notification(self, *, payload: bytes) -> PurchaseFacts | None:
        """Verify an App Store Server Notification V2 and return the facts, or None.

        Raises StoreVerificationError if the JWS chain does not check out.
        """
        ...


class UnconfiguredStoreGateway:
    """The gateway in use until each store's credentials and verification are in place.

    Every method raises. That is the whole design: an endpoint wired to this answers 503,
    which is the correct thing for a payment path that cannot yet tell a real purchase from
    an invented one. It is deliberately not a no-op that returns None — a None would flow
    through the endpoint as "nothing to do" and read, in a log, exactly like a healthy
    notification carrying a price change.
    """

    def verify_play_purchase(
        self, *, purchase_token: str, product_id: str, user_id: str
    ) -> PurchaseFacts:
        raise StoreNotConfigured("Google Play billing is not configured.")

    def verify_appstore_purchase(self, *, transaction_id: str, user_id: str) -> PurchaseFacts:
        raise StoreNotConfigured("App Store billing is not configured.")

    def read_play_notification(self, *, payload: bytes, authorization: str) -> PurchaseFacts | None:
        raise StoreNotConfigured("Google Play billing is not configured.")

    def read_appstore_notification(self, *, payload: bytes) -> PurchaseFacts | None:
        raise StoreNotConfigured("App Store billing is not configured.")


class StoreGateways:
    """One gateway per store, behind the single protocol the endpoints depend on.

    Each store's implementation refuses the other's calls, so this routes rather than
    merges. The point is that a store which is not configured — or whose credentials are
    wrong — refuses on its own, without taking the other one down with it. Launching on
    Play weeks before Apple is the expected order, not an edge case.

    A store whose implementation fails to construct is held as the reason it failed rather
    than as nothing. Anything reaching it raises `StoreNotConfigured` carrying that reason,
    so a bad key surfaces as a 503 naming the problem instead of an AttributeError.
    """

    def __init__(
        self,
        play: object | None = None,
        appstore: object | None = None,
        *,
        play_error: str = "Google Play billing is not configured.",
        appstore_error: str = "App Store billing is not configured.",
    ) -> None:
        self._play = play
        self._appstore = appstore
        self._play_error = play_error
        self._appstore_error = appstore_error

    def _for_play(self) -> object:
        if self._play is None:
            raise StoreNotConfigured(self._play_error)
        return self._play

    def _for_appstore(self) -> object:
        if self._appstore is None:
            raise StoreNotConfigured(self._appstore_error)
        return self._appstore

    def verify_play_purchase(
        self, *, purchase_token: str, product_id: str, user_id: str
    ) -> PurchaseFacts:
        return self._for_play().verify_play_purchase(
            purchase_token=purchase_token, product_id=product_id, user_id=user_id
        )

    def acknowledge_play_purchase(self, facts: PurchaseFacts) -> None:
        return self._for_play().acknowledge_play_purchase(facts)

    def verify_appstore_purchase(self, *, transaction_id: str, user_id: str) -> PurchaseFacts:
        return self._for_appstore().verify_appstore_purchase(
            transaction_id=transaction_id, user_id=user_id
        )

    def read_play_notification(self, *, payload: bytes, authorization: str) -> PurchaseFacts | None:
        return self._for_play().read_play_notification(
            payload=payload, authorization=authorization
        )

    def read_appstore_notification(self, *, payload: bytes) -> PurchaseFacts | None:
        return self._for_appstore().read_appstore_notification(payload=payload)


def build_store_gateway(settings) -> StoreGateways:
    """Assemble whichever stores are configured and constructible.

    Construction is where a bad credential shows up — an unparseable service-account JSON,
    an empty root-certificate list — and it must not take the application down at import
    time. A store that will not construct is recorded as unavailable with its reason, which
    is the same outcome as never having configured it and is visibly different in the logs.
    """
    play = None
    play_error = "Google Play billing is not configured."
    if settings.play_configured:
        try:
            from app.billing.play_gateway import PlayGateway

            play = PlayGateway(settings)
        except Exception as exc:
            play_error = f"Google Play billing failed to start: {exc}"
            logging.getLogger(__name__).error(play_error)

    appstore = None
    appstore_error = "App Store billing is not configured."
    if settings.appstore_configured:
        try:
            from app.billing.appstore_gateway import AppStoreGateway

            appstore = AppStoreGateway(settings)
        except Exception as exc:
            appstore_error = f"App Store billing failed to start: {exc}"
            logging.getLogger(__name__).error(appstore_error)

    return StoreGateways(
        play, appstore, play_error=play_error, appstore_error=appstore_error
    )
