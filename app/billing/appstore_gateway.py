"""Apple, for real.

Apple's payload carries the facts inline, so unlike Play there is no second call to make on
the notification path — but they arrive inside nested JWS blobs, and the verification is the
whole job. `app-store-server-library` is Apple's own implementation of it, used here rather
than hand-rolled for a reason worth stating: the check that actually matters is that the
`x5c` chain validates up to an Apple root, and a hand-written version that decodes the leaf
and reads the claims looks identical in every test you would think to write while being
worth nothing. It is a signature check that verifies no signature.

THE ROOT CERTIFICATES ARE NOT OPTIONAL. `SignedDataVerifier` takes them as an argument and
there is no default. Supplied through `APPSTORE_ROOT_CERTS` as base64 DER, downloaded from
https://www.apple.com/certificateauthority/ — the Apple Root CA G3 is the one that matters
for App Store Server Notifications. With none configured this gateway refuses to construct,
which is the correct failure: a verifier with an empty trust store rejects everything, and
an endpoint that answers 400 to every real notification while looking configured is a
subscription system that quietly stops renewing people.

Nothing here is exercised by the test suite, which has no App Store Connect credentials by
design. The mapping it feeds is tested exhaustively in test_store_payloads.py against
payloads transcribed from Apple's documentation.
"""

import base64
import binascii
import json
import logging

from app.billing.store import PurchaseFacts
from app.billing.store_gateway import StoreVerificationError
from app.billing.store_payloads import millis_to_datetime, parse_appstore_payload
from app.config import Settings

logger = logging.getLogger(__name__)


class AppStoreGateway:
    """StoreGateway, backed by Apple. Constructed only when `appstore_configured`."""

    def __init__(self, settings: Settings) -> None:
        from appstoreserverlibrary.api_client import AppStoreServerAPIClient
        from appstoreserverlibrary.models.Environment import Environment
        from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier

        roots = _root_certificates(settings.appstore_root_certs)
        if not roots:
            raise StoreVerificationError(
                "APPSTORE_ROOT_CERTS is empty. Apple's root certificates are required to "
                "verify a notification; without them every notification is rejected. "
                "Download them from https://www.apple.com/certificateauthority/."
            )

        environment = (
            Environment.PRODUCTION
            if settings.appstore_environment == "production"
            else Environment.SANDBOX
        )
        self._bundle_id = settings.appstore_bundle_id
        self._subscription_products = settings.subscription_product_ids

        self._verifier = SignedDataVerifier(
            roots,
            # Checks the certificate chain against Apple's OCSP responder rather than
            # trusting a chain that merely parses. On by design: a revoked intermediate is
            # exactly the case offline verification cannot see.
            True,
            environment,
            settings.appstore_bundle_id,
        )
        self._api = AppStoreServerAPIClient(
            settings.appstore_private_key.encode(),
            settings.appstore_key_id,
            settings.appstore_issuer_id,
            settings.appstore_bundle_id,
            environment,
        )

    # --- The app's own report --------------------------------------------------

    def verify_appstore_purchase(self, *, transaction_id: str, user_id: str) -> PurchaseFacts:
        """Ask Apple about a transaction the iOS app says it just completed.

        The device's own receipt is not consulted. It is under the control of whoever holds
        the phone, and a jailbroken device can produce a convincing one; the App Store
        Server API is the only account of a purchase that is worth anything.
        """
        try:
            response = self._api.get_transaction_info(transaction_id)
            transaction = self._verifier.verify_and_decode_signed_transaction(
                response.signedTransactionInfo
            )
        except Exception as exc:
            raise StoreVerificationError(f"Apple would not confirm the transaction: {exc}") from exc

        if not transaction.productId or not transaction.originalTransactionId:
            raise StoreVerificationError("Apple returned a transaction with no product or id")

        # A refunded transaction still resolves; it simply carries a revocation date. Reading
        # that as a purchase would re-grant access to somebody who has had their money back.
        state = "revoked" if transaction.revocationDate else "purchased"

        kind = (
            "subscription"
            if transaction.productId in self._subscription_products
            else "pass"
        )

        return PurchaseFacts(
            platform="appstore",
            product_id=transaction.productId,
            purchase_identifier=transaction.originalTransactionId,
            kind=kind,
            state=state,
            expires_at=millis_to_datetime(transaction.expiresDate),
            # The signed-in candidate, not the token on the transaction. This path is
            # authenticated, so we know who is asking, and taking their id here is what
            # binds a purchase whose appAccountToken the app failed to set.
            user_id=user_id,
        )

    def verify_play_purchase(
        self, *, purchase_token: str, product_id: str, user_id: str
    ) -> PurchaseFacts:
        raise StoreVerificationError("This gateway is the App Store only.")

    # --- Notifications ---------------------------------------------------------

    def read_appstore_notification(self, *, payload: bytes) -> PurchaseFacts | None:
        signed = _signed_payload(payload)

        try:
            notification = self._verifier.verify_and_decode_notification(signed)
        except Exception as exc:
            raise StoreVerificationError(f"notification did not verify: {exc}") from exc

        data = notification.data
        if data is None or not data.signedTransactionInfo:
            # Several notification types carry no transaction — a consumption request, or a
            # summary of a renewal extension across many subscribers. Nothing to record.
            return None

        try:
            transaction = self._verifier.verify_and_decode_signed_transaction(
                data.signedTransactionInfo
            )
        except Exception as exc:
            raise StoreVerificationError(f"transaction did not verify: {exc}") from exc

        return parse_appstore_payload(
            {
                # rawNotificationType/rawSubtype are the strings Apple sent. The parsed enums
                # are None for any type this library version predates, and a notification we
                # cannot name must not silently become one we ignore.
                "notificationType": notification.rawNotificationType or "",
                "subtype": notification.rawSubtype,
            },
            {
                "originalTransactionId": transaction.originalTransactionId,
                "productId": transaction.productId,
                "type": transaction.rawType,
                "expiresDate": transaction.expiresDate,
                "appAccountToken": transaction.appAccountToken,
            },
            subscription_products=self._subscription_products,
        )

    def read_play_notification(self, *, payload: bytes, authorization: str) -> PurchaseFacts | None:
        raise StoreVerificationError("This gateway is the App Store only.")


def _signed_payload(payload: bytes) -> str:
    """Pull `signedPayload` out of the POST body.

    The endpoint is public, so a body that is not JSON, or JSON without the field, is an
    ordinary thing to receive and a verification failure rather than a crash.
    """
    try:
        body = json.loads(payload)
        signed = body["signedPayload"]
    except (ValueError, KeyError, TypeError) as exc:
        raise StoreVerificationError(f"not an App Store notification: {exc}") from exc

    if not isinstance(signed, str) or not signed:
        raise StoreVerificationError("notification carried an empty signedPayload")
    return signed


def _root_certificates(configured: str) -> list[bytes]:
    """Comma-separated base64 DER certificates, as bytes.

    A value that does not decode is dropped with a warning rather than raising, so one
    fat-fingered certificate does not take the other roots down with it — but if that
    leaves the list empty the constructor refuses, so it cannot degrade into trusting
    nothing while appearing to work.
    """
    roots: list[bytes] = []
    for chunk in configured.split(","):
        text = chunk.strip()
        if not text:
            continue
        try:
            roots.append(base64.b64decode(text, validate=True))
        except (binascii.Error, ValueError):
            logger.warning("APPSTORE_ROOT_CERTS contains a value that is not base64; skipped")
    return roots
