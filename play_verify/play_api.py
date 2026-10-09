"""Play Developer API calls for one package, with an injected transport.

The transport returns ``(status, body_text)``. It must not log the URL: the
purchase token is a path segment on Google's API. Errors raised here are short
codes. They never include the token or the URL.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

ANDROID_PUBLISHER_SCOPE = "https://www.googleapis.com/auth/androidpublisher"
PLAY_API_ROOT = "https://androidpublisher.googleapis.com/androidpublisher/v3"

RequestFn = Callable[[str, str, dict | None], tuple[int, str]]


class PlayCallError(Exception):
    """Play did not return a usable result. ``code`` is safe to send onward."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class AlreadyAcknowledged(PlayCallError):
    def __init__(self) -> None:
        super().__init__("already_acknowledged")


def _quote(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def interpret(status: int, text: str) -> dict:
    """Map a Play HTTP response to a dict, or a token-free error.

    Acknowledgement is idempotent: Google's 400 "already acknowledged" is
    success. The response body is not returned on that path, and it is not
    included in any error — Google sometimes echoes the request.
    """
    lowered = text.lower()
    if status == 400 and "already" in lowered and "acknowledg" in lowered:
        raise AlreadyAcknowledged()
    if status in (200, 204):
        if not text.strip():
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            raise PlayCallError("play_unreadable") from None
        if not isinstance(parsed, dict):
            raise PlayCallError("play_unreadable")
        return parsed
    if status in (400, 404):
        raise PlayCallError("play_rejected")
    raise PlayCallError("play_unavailable")


class AndroidPublisher:
    """subscriptionsv2.get, products.get, and both acknowledge methods.

    There is no consume method. Consuming a subscription or a non-consumable
    would revoke what the buyer paid for.
    """

    def __init__(self, package_name: str, request: RequestFn) -> None:
        package = package_name.strip()
        if not package or "/" in package or ".." in package:
            raise ValueError("Play package name is missing")
        self._package = package
        self._request = request

    def _url(self, *parts: str, suffix: str = "") -> str:
        path = "/".join(_quote(part) for part in parts)
        return f"{PLAY_API_ROOT}/applications/{_quote(self._package)}/{path}{suffix}"

    def get_subscription(self, token: str) -> dict:
        status, text = self._request(
            "GET",
            self._url("purchases", "subscriptionsv2", "tokens", token),
            None,
        )
        return interpret(status, text)

    def get_product(self, product_id: str, token: str) -> dict:
        status, text = self._request(
            "GET",
            self._url("purchases", "products", product_id, "tokens", token),
            None,
        )
        return interpret(status, text)

    def acknowledge_subscription(self, product_id: str, token: str) -> None:
        status, text = self._request(
            "POST",
            self._url(
                "purchases",
                "subscriptions",
                product_id,
                "tokens",
                token,
                suffix=":acknowledge",
            ),
            {},
        )
        interpret(status, text)

    def acknowledge_product(self, product_id: str, token: str) -> None:
        status, text = self._request(
            "POST",
            self._url(
                "purchases",
                "products",
                product_id,
                "tokens",
                token,
                suffix=":acknowledge",
            ),
            {},
        )
        interpret(status, text)


class MetadataAuthorizedRequest:
    """Authorize with the Cloud Run runtime service account. No JSON key.

    ``google.auth.default`` on Cloud Run reads the metadata server. A laptop
    without Application Default Credentials fails closed with ``play_auth``.
    """

    def __init__(self) -> None:
        self._credentials = None
        self._auth_request = None

    def _access_token(self) -> str:
        try:
            if self._credentials is None:
                import google.auth
                from google.auth.transport.urllib import Request

                self._credentials, _ = google.auth.default(scopes=[ANDROID_PUBLISHER_SCOPE])
                self._auth_request = Request()
            if not self._credentials.valid:
                self._credentials.refresh(self._auth_request)
            token = self._credentials.token
            if not token:
                raise PlayCallError("play_auth")
            return token
        except PlayCallError:
            raise
        except Exception:
            raise PlayCallError("play_auth") from None

    def __call__(self, method: str, url: str, body: dict | None) -> tuple[int, str]:
        access = self._access_token()
        data = None if body is None else json.dumps(body).encode()
        headers = {"Authorization": f"Bearer {access}", "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read().decode(errors="replace")
            except Exception:
                raw = ""
            return exc.code, raw
        except urllib.error.URLError:
            return 503, ""
