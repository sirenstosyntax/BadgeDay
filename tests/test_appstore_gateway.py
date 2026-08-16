"""The parts of the App Store gateway that do not need Apple.

The JWS verification itself is the library's job and needs credentials and a real
notification. What is ours, and testable, is the handling either side of it: pulling the
signed payload out of a public endpoint's request body, and assembling the trust store the
verifier is given.

The trust store is the one to get right. An empty list is not a mild misconfiguration — it
is a verifier that rejects every genuine notification, which presents as Apple sending
forged notifications rather than as a missing setting.
"""

import base64

import pytest

from app.billing.appstore_gateway import _root_certificates, _signed_payload
from app.billing.store_gateway import StoreVerificationError

CERT_A = base64.b64encode(b"root-certificate-a").decode()
CERT_B = base64.b64encode(b"root-certificate-b").decode()


# --- The trust store ----------------------------------------------------------


def test_certificates_are_decoded_from_base64() -> None:
    assert _root_certificates(f"{CERT_A},{CERT_B}") == [
        b"root-certificate-a",
        b"root-certificate-b",
    ]


def test_whitespace_and_empty_entries_are_tolerated() -> None:
    """These arrive through an environment variable, often pasted across several lines."""
    assert _root_certificates(f"  {CERT_A} , , {CERT_B}  ") == [
        b"root-certificate-a",
        b"root-certificate-b",
    ]


def test_one_bad_certificate_does_not_take_the_others_with_it() -> None:
    assert _root_certificates(f"{CERT_A},!!!not base64!!!,{CERT_B}") == [
        b"root-certificate-a",
        b"root-certificate-b",
    ]


def test_nothing_configured_is_an_empty_trust_store() -> None:
    """Empty is what the constructor refuses on, so this must not quietly become non-empty."""
    assert _root_certificates("") == []
    assert _root_certificates("  ,  ") == []
    assert _root_certificates("!!!only rubbish!!!") == []


# --- The request body ---------------------------------------------------------


def test_the_signed_payload_is_read_out_of_the_body() -> None:
    assert _signed_payload(b'{"signedPayload": "eyJhbGc"}') == "eyJhbGc"


def test_anything_else_is_a_verification_failure_rather_than_a_crash() -> None:
    """This endpoint is public and unauthenticated; all of these are ordinary arrivals."""
    for payload in (
        b"",
        b"not json",
        b"{}",
        b'{"signedPayload": ""}',
        b'{"signedPayload": null}',
        b'{"signedPayload": 42}',
        b'["not an object"]',
    ):
        with pytest.raises(StoreVerificationError):
            _signed_payload(payload)
