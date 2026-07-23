"""The seam between BadgeDay and Stripe.

Everything that actually talks to Stripe is behind this protocol, for the same reason the
document analyzer is behind one: the endpoints and the webhook translation can then be
tested against a fake with no Stripe account and no network, and Stripe is an
implementation detail rather than a test dependency.

Three operations, which is all the billing loop needs: begin a checkout, open the billing
portal, and turn a raw webhook request back into a trustworthy event. Nothing here decides
what an event *means* — that is `plan.plan_changes`, kept separate so the meaning is
testable without constructing Stripe objects.
"""

from typing import Literal, Protocol

from app.config import Settings


class WebhookVerificationError(Exception):
    """The webhook payload did not carry a valid signature for our signing secret."""


class PaymentGateway(Protocol):
    def ensure_customer(self, *, email: str | None, user_id: str) -> str:
        """Return a Stripe customer id for this candidate, creating one if needed."""
        ...

    def start_checkout(
        self,
        *,
        mode: Literal["subscription", "payment"],
        price_id: str,
        customer_id: str,
        client_reference_id: str,
        success_url: str,
        cancel_url: str,
    ) -> str:
        """Create a checkout session and return the URL to send the candidate to."""
        ...

    def open_portal(self, *, customer_id: str, return_url: str) -> str:
        """Create a billing-portal session and return its URL."""
        ...

    def read_event(self, *, payload: bytes, signature: str) -> dict:
        """Verify a webhook's signature and return the event as a plain dict.

        Raises WebhookVerificationError if the signature does not check out — the one
        thing standing between "Stripe told us" and "someone posted us a payment they
        invented".
        """
        ...


class StripeGateway:
    """PaymentGateway backed by the real Stripe API."""

    def __init__(self, settings: Settings) -> None:
        import stripe

        self._stripe = stripe
        self._client = stripe.StripeClient(settings.stripe_secret_key)
        self._webhook_secret = settings.stripe_webhook_secret

    def ensure_customer(self, *, email: str | None, user_id: str) -> str:
        customer = self._client.customers.create(
            params={"email": email or None, "metadata": {"user_id": user_id}}
        )
        return customer.id

    def start_checkout(
        self,
        *,
        mode: Literal["subscription", "payment"],
        price_id: str,
        customer_id: str,
        client_reference_id: str,
        success_url: str,
        cancel_url: str,
    ) -> str:
        session = self._client.checkout.sessions.create(
            params={
                "mode": mode,
                "customer": customer_id,
                "client_reference_id": client_reference_id,
                "line_items": [{"price": price_id, "quantity": 1}],
                "success_url": success_url,
                "cancel_url": cancel_url,
            }
        )
        if session.url is None:
            raise RuntimeError("Stripe returned a checkout session without a URL.")
        return session.url

    def open_portal(self, *, customer_id: str, return_url: str) -> str:
        session = self._client.billing_portal.sessions.create(
            params={"customer": customer_id, "return_url": return_url}
        )
        return session.url

    def read_event(self, *, payload: bytes, signature: str) -> dict:
        try:
            event = self._stripe.Webhook.construct_event(
                payload, signature, self._webhook_secret
            )
        except (ValueError, self._stripe.SignatureVerificationError) as exc:
            raise WebhookVerificationError(str(exc)) from exc
        return dict(event)
