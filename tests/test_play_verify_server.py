"""The Cloud Run verifier. The Play transport is injected. No metadata server."""

import pytest
from fastapi.testclient import TestClient

from play_verify.play_api import AlreadyAcknowledged, AndroidPublisher, PlayCallError, interpret
from play_verify.server import create_app

_SECRET = "verifier-secret"
_TOKEN = "token-that-must-not-appear-in-errors"
_PACKAGE = "com.badgeday.app"


class _Publisher:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def get_subscription(self, token: str) -> dict:
        self.calls.append(("get_subscription", token))
        return {"subscriptionState": "SUBSCRIPTION_STATE_ACTIVE", "lineItems": []}

    def get_product(self, product_id: str, token: str) -> dict:
        self.calls.append(("get_product", product_id, token))
        return {"purchaseState": 0}

    def acknowledge_subscription(self, product_id: str, token: str) -> None:
        self.calls.append(("acknowledge_subscription", product_id, token))

    def acknowledge_product(self, product_id: str, token: str) -> None:
        self.calls.append(("acknowledge_product", product_id, token))
        raise AlreadyAcknowledged()


def _app(
    publisher: _Publisher | None = None, *, secret: str = _SECRET
) -> tuple[TestClient, _Publisher]:
    publisher = publisher or _Publisher()
    app = create_app(
        package_name=_PACKAGE,
        shared_secret=secret,
        publisher=publisher,  # type: ignore[arg-type]
    )
    return TestClient(app), publisher


def test_health_names_the_package_and_not_the_secret() -> None:
    client, _ = _app()
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["packageName"] == _PACKAGE
    assert body["consume"] is False
    assert body["secretConfigured"] is True
    assert _SECRET not in response.text


def test_missing_bearer_is_rejected_before_the_body_is_echoed() -> None:
    client, publisher = _app()
    response = client.post(
        "/v1/play",
        json={"op": "subscription.get", "purchaseToken": _TOKEN, "packageName": "com.other"},
    )
    assert response.status_code == 401
    assert _TOKEN not in response.text
    assert publisher.calls == []


def test_wrong_bearer_does_not_echo_either_secret() -> None:
    client, publisher = _app()
    response = client.post(
        "/v1/play",
        headers={"Authorization": "Bearer not-the-secret"},
        json={"op": "subscription.get", "purchaseToken": _TOKEN},
    )
    assert response.status_code == 401
    assert "not-the-secret" not in response.text
    assert _SECRET not in response.text
    assert publisher.calls == []


def test_empty_server_secret_fails_closed() -> None:
    client, publisher = _app(secret="")
    response = client.post(
        "/v1/play",
        headers={"Authorization": f"Bearer {_SECRET}"},
        json={"op": "subscription.get", "purchaseToken": _TOKEN},
    )
    assert response.status_code == 503
    assert publisher.calls == []


def test_package_name_in_the_body_is_rejected() -> None:
    client, publisher = _app()
    response = client.post(
        "/v1/play",
        headers={"Authorization": f"Bearer {_SECRET}"},
        json={
            "op": "subscription.get",
            "purchaseToken": _TOKEN,
            "packageName": "com.sirenstosyntax.drillground",
        },
    )
    assert response.status_code == 400
    assert _TOKEN not in response.text
    assert "drillground" not in response.text
    assert publisher.calls == []


def test_subscription_lookup_uses_the_injected_publisher() -> None:
    client, publisher = _app()
    response = client.post(
        "/v1/play",
        headers={"Authorization": f"Bearer {_SECRET}"},
        json={"op": "subscription.get", "purchaseToken": _TOKEN},
    )
    assert response.status_code == 200
    assert response.json()["subscriptionState"] == "SUBSCRIPTION_STATE_ACTIVE"
    assert publisher.calls == [("get_subscription", _TOKEN)]


def test_already_acknowledged_is_success() -> None:
    client, publisher = _app()
    response = client.post(
        "/v1/play",
        headers={"Authorization": f"Bearer {_SECRET}"},
        json={
            "op": "product.acknowledge",
            "productId": "sku.example",
            "purchaseToken": _TOKEN,
        },
    )
    assert response.status_code == 200
    assert response.json() == {"acknowledged": True}
    assert publisher.calls == [("acknowledge_product", "sku.example", _TOKEN)]


def test_play_rejection_does_not_include_the_token() -> None:
    class _Reject(_Publisher):
        def get_subscription(self, token: str) -> dict:
            raise PlayCallError("play_rejected")

    client, _ = _app(_Reject())
    response = client.post(
        "/v1/play",
        headers={"Authorization": f"Bearer {_SECRET}"},
        json={"op": "subscription.get", "purchaseToken": _TOKEN},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "play_rejected"
    assert _TOKEN not in response.text


def test_play_urls_are_fixed_to_the_package_and_never_consume() -> None:
    seen: list[tuple[str, str, dict | None]] = []

    def request(method: str, url: str, body: dict | None) -> tuple[int, str]:
        seen.append((method, url, body))
        if method == "GET":
            return 200, '{"subscriptionState":"SUBSCRIPTION_STATE_ACTIVE"}'
        return 400, "The purchase has already been acknowledged."

    publisher = AndroidPublisher(_PACKAGE, request)
    token = "tok/en+"
    publisher.get_subscription(token)
    with pytest.raises(AlreadyAcknowledged):
        publisher.acknowledge_subscription("sku.example", token)

    assert seen[0][0] == "GET"
    assert seen[0][1] == (
        "https://androidpublisher.googleapis.com/androidpublisher/v3"
        "/applications/com.badgeday.app/purchases/subscriptionsv2/tokens/tok%2Fen%2B"
    )
    assert seen[1][0] == "POST"
    assert seen[1][1].endswith("/tokens/tok%2Fen%2B:acknowledge")
    assert "/products/" not in seen[0][1]
    assert ":consume" not in seen[0][1]
    assert ":consume" not in seen[1][1]
    assert seen[1][2] == {}


def test_a_play_error_body_cannot_become_the_exception_text() -> None:
    with pytest.raises(PlayCallError) as caught:
        interpret(404, f"no such token {_TOKEN}")
    assert caught.value.code == "play_rejected"
    assert _TOKEN not in str(caught.value)
