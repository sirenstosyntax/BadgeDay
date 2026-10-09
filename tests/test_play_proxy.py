"""The Azure side of the keyless verifier. No network, no JSON key."""

import io
import json
import urllib.error

import pytest

from app.billing.play_proxy import KeylessProxyPlayClient, _RefuseRedirect
from app.billing.store_gateway import StoreNotConfigured, StoreVerificationError

_TOKEN = "purchase-token-must-not-leak"
_SECRET = "shared-secret-must-not-leak"


class _Response:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


def _client(opener) -> KeylessProxyPlayClient:
    return KeylessProxyPlayClient(
        "https://verify.example.test",
        _SECRET,
        opener=opener,
    )


def test_lookup_sends_the_bearer_and_not_a_package_name() -> None:
    seen = []

    def opener(request, timeout):
        seen.append((request, timeout))
        return _Response(200, b'{"subscriptionState":"SUBSCRIPTION_STATE_ACTIVE"}')

    body = _client(opener).get_subscription(_TOKEN)

    assert body["subscriptionState"] == "SUBSCRIPTION_STATE_ACTIVE"
    request, timeout = seen[0]
    assert timeout == 15
    assert request.full_url == "https://verify.example.test/v1/play"
    assert request.get_header("Authorization") == f"Bearer {_SECRET}"
    payload = json.loads(request.data.decode())
    assert payload == {"op": "subscription.get", "purchaseToken": _TOKEN}
    assert "packageName" not in payload
    assert _SECRET not in request.data.decode()


def test_a_play_rejection_does_not_echo_the_token() -> None:
    def opener(request, timeout):
        raise urllib.error.HTTPError(
            url="https://verify.example.test/v1/play",
            code=400,
            msg="bad",
            hdrs=None,
            fp=io.BytesIO(b'{"detail":"play_rejected"}'),
        )

    with pytest.raises(StoreVerificationError) as caught:
        _client(opener).get_product(_TOKEN, "sku.example")

    assert _TOKEN not in str(caught.value)
    assert "400" in str(caught.value)


def test_verifier_outage_is_not_a_rejected_purchase() -> None:
    def opener(request, timeout):
        raise urllib.error.URLError("down")

    with pytest.raises(StoreNotConfigured):
        _client(opener).get_subscription(_TOKEN)


def test_http_verifier_urls_are_refused() -> None:
    for url in (
        "http://verify.example.test",
        "https://localhost/play",
        "https://user:secret@verify.example.test",
        "https://verify.example.test/play?token=1",
    ):
        with pytest.raises(ValueError):
            KeylessProxyPlayClient(url, _SECRET)


def test_redirects_are_refused() -> None:
    with pytest.raises(urllib.error.URLError):
        _RefuseRedirect().redirect_request(None, None, 302, "found", None, "https://evil/")
