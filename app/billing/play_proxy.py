"""Client for the keyless Play verifier.

BadgeDay cannot mint a Play Developer API credential on Cloud Run's behalf from
Azure: project ``sirens-to-syntax-play`` blocks service-account key creation.
The verifier (``play_verify``) runs in that project and uses the metadata
server. This module is the only caller. It never grants an entitlement — it
only fetches the purchase Google already has, or asks Google to acknowledge
one we have already recorded.

The shared secret is a bearer this process and the verifier both know. It is
not a Google credential. The purchase token goes in the JSON body, never in
the URL, so a redirect or an error string cannot leak it by echoing the path.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from app.billing.store_gateway import StoreNotConfigured, StoreVerificationError

_TIMEOUT_SECONDS = 15


class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    """A verifier redirect would send the bearer and the purchase token elsewhere."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise urllib.error.URLError("Play verifier refused to follow a redirect")


def _https_verifier_url(base_url: str) -> str:
    """Require https. The bearer and the purchase token travel on this request."""
    parsed = urllib.parse.urlparse(base_url.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host or host == "localhost":
        raise ValueError("Play verifier URL must be https and not localhost")
    if parsed.username or parsed.password:
        raise ValueError("Play verifier URL must not carry credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("Play verifier URL must not include a query or fragment")
    return base_url.strip().rstrip("/") + "/v1/play"


class KeylessProxyPlayClient:
    """POST ``/v1/play`` on the Cloud Run verifier. No package name leaves here.

    The verifier's package is fixed in its own environment. Sending one from
    Azure would let a misrouted request ask about a different app.
    """

    def __init__(
        self,
        base_url: str,
        shared_secret: str,
        *,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        secret = shared_secret.strip()
        if not secret:
            raise ValueError("Play verifier shared secret is empty")
        self._endpoint = _https_verifier_url(base_url)
        self._secret = secret
        self._opener = opener or urllib.request.build_opener(_RefuseRedirect).open

    def get_subscription(self, purchase_token: str) -> dict:
        return self._call({"op": "subscription.get", "purchaseToken": purchase_token})

    def get_product(self, purchase_token: str, product_id: str) -> dict:
        return self._call(
            {
                "op": "product.get",
                "productId": product_id,
                "purchaseToken": purchase_token,
            }
        )

    def acknowledge(self, product_id: str, purchase_token: str, *, subscription: bool) -> None:
        op = "subscription.acknowledge" if subscription else "product.acknowledge"
        self._call(
            {"op": op, "productId": product_id, "purchaseToken": purchase_token}
        )

    def _call(self, payload: dict) -> dict:
        raw, status = self._send(payload)
        if status == 200:
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                raise StoreNotConfigured(
                    "Play verifier returned an unreadable response"
                ) from None
            if not isinstance(parsed, dict):
                raise StoreNotConfigured("Play verifier returned an unreadable response")
            return parsed
        # 401/5xx/unavailable: our verifier, not Google's verdict on the purchase.
        # The purchase endpoint answers 503 and grants nothing.
        if status in (401, 422, 502, 503) or status >= 500:
            raise StoreNotConfigured(f"Play verifier is unavailable ({status})")
        raise StoreVerificationError(f"Play would not confirm the purchase ({status})")

    def _send(self, payload: dict) -> tuple[bytes, int]:
        body = json.dumps(payload).encode()
        request = urllib.request.Request(
            self._endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._secret}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with self._opener(request, timeout=_TIMEOUT_SECONDS) as response:
                return response.read(), getattr(response, "status", 200)
        except urllib.error.HTTPError as exc:
            # Do not include str(exc): HTTPError echoes the request URL.
            try:
                detail = exc.read()
            except Exception:
                detail = b""
            return detail, exc.code
        except urllib.error.URLError:
            raise StoreNotConfigured("Play verifier is unreachable") from None
