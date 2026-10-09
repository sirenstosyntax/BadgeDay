"""HTTP front for the keyless Play verifier.

Cloud Run may be deployed ``--allow-unauthenticated`` because Azure has no
Google identity to present. The bearer shared secret is the credential.
Requests without it are rejected before the body is parsed, so a purchase
token in a forged body is never echoed in a validation error.

The package name is the process environment. The request cannot choose one.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re

from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel, ValidationError, field_validator

from play_verify.play_api import (
    AlreadyAcknowledged,
    AndroidPublisher,
    MetadataAuthorizedRequest,
    PlayCallError,
)

_PRODUCT_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_MAX_BODY = 16_384
_OPS_NEEDING_PRODUCT = frozenset(
    {"product.get", "subscription.acknowledge", "product.acknowledge"}
)


class PlayOp(BaseModel):
    model_config = {"extra": "forbid"}

    op: str
    purchaseToken: str
    productId: str | None = None

    @field_validator("op")
    @classmethod
    def _known_op(cls, value: str) -> str:
        allowed = {
            "subscription.get",
            "product.get",
            "subscription.acknowledge",
            "product.acknowledge",
        }
        if value not in allowed:
            raise ValueError("unknown op")
        return value

    @field_validator("purchaseToken")
    @classmethod
    def _token(cls, value: str) -> str:
        if not value or len(value) > 4096 or any(ord(ch) < 32 for ch in value):
            raise ValueError("invalid token")
        return value

    @field_validator("productId")
    @classmethod
    def _product(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _PRODUCT_ID.fullmatch(value):
            raise ValueError("invalid product")
        return value


def bearer_matches(presented: str, secret: str) -> bool:
    """Compare digests so the check does not leak the secret's length."""
    if not presented or not secret:
        return False
    return hmac.compare_digest(
        hashlib.sha256(presented.encode()).digest(),
        hashlib.sha256(secret.encode()).digest(),
    )


def require_bearer(authorization: str, secret: str) -> None:
    if not secret:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "play verifier is not configured"
        )
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not bearer_matches(token.strip(), secret):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unauthorized")


def create_app(
    *,
    package_name: str,
    shared_secret: str,
    publisher: AndroidPublisher,
) -> FastAPI:
    app = FastAPI(title="badgeday-play-verify", docs_url=None, redoc_url=None, openapi_url=None)
    secret = shared_secret.strip()

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "ok": True,
            "service": "badgeday-play-verify",
            "packageName": package_name,
            "consume": False,
            "secretConfigured": bool(secret),
        }

    @app.post("/v1/play")
    async def play_op(request: Request) -> dict:
        require_bearer(request.headers.get("authorization", ""), secret)
        raw = await request.body()
        if len(raw) > _MAX_BODY:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid play request")
        try:
            data = json.loads(raw)
            op = PlayOp.model_validate(data)
        except (json.JSONDecodeError, ValidationError, TypeError):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid play request") from None
        if op.op in _OPS_NEEDING_PRODUCT and not op.productId:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid play request")

        try:
            if op.op == "subscription.get":
                return publisher.get_subscription(op.purchaseToken)
            if op.op == "product.get":
                return publisher.get_product(op.productId or "", op.purchaseToken)
            if op.op == "subscription.acknowledge":
                publisher.acknowledge_subscription(op.productId or "", op.purchaseToken)
                return {"acknowledged": True}
            publisher.acknowledge_product(op.productId or "", op.purchaseToken)
            return {"acknowledged": True}
        except AlreadyAcknowledged:
            return {"acknowledged": True}
        except PlayCallError as exc:
            if exc.code == "play_rejected":
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "play_rejected") from None
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "play_unavailable"
            ) from None

    return app


def build_production_app() -> FastAPI:
    package = os.environ.get("PLAY_PACKAGE_NAME", "").strip() or "com.badgeday.app"
    secret = os.environ.get("PLAY_VERIFY_SHARED_SECRET", "")
    publisher = AndroidPublisher(package, MetadataAuthorizedRequest())
    return create_app(package_name=package, shared_secret=secret, publisher=publisher)


app = build_production_app()
