"""Play Console reviewer sign-in — env-gated, not a public password product.

Google rejects magic-link / emailed OTP as MFA: a reviewer cannot wait on a
real-time email. This path accepts a reusable email+password only when both
``PLAY_REVIEWER_EMAILS`` (allowlist) and ``PLAY_REVIEWER_PASSWORD`` are set.
Everyone else keeps the existing OTP flow. Wrong email and wrong password
fail the same way so the allowlist is not a boolean oracle.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.config import Settings

GENERIC_DENIED = "That email and password did not match."
UNAVAILABLE = "Sign-in is unavailable right now."
NOT_CONFIGURED = "Not found."
TOO_MANY_ATTEMPTS = "Too many sign-in attempts. Try again later."

# Shared allowlist password on a public origin. Five misses lock the IP and
# the attempted email for fifteen minutes so a known reviewer mailbox is not
# an unbounded online oracle. Process-local is enough: there is no Redis, and
# the allowlist is tiny. Each replica enforces its own window.
REVIEWER_MAX_FAILURES = 5
REVIEWER_LOCKOUT_SECONDS = 15 * 60


class ReviewerSessionError(RuntimeError):
    """Supabase did not hand back a usable session. Callers map this to 503."""


@dataclass
class _AttemptBucket:
    count: int = 0
    locked_until: float = 0.0


class ReviewerAttemptGuard:
    """Per-IP and per-email failure lock for ``POST /auth/play-reviewer``."""

    def __init__(
        self,
        *,
        max_failures: int = REVIEWER_MAX_FAILURES,
        lockout_seconds: float = REVIEWER_LOCKOUT_SECONDS,
        now: Callable[[], float] | None = None,
    ) -> None:
        if max_failures < 1:
            raise ValueError("reviewer max failures must be at least 1")
        if lockout_seconds <= 0:
            raise ValueError("reviewer lockout seconds must be positive")
        self.max_failures = max_failures
        self.lockout_seconds = lockout_seconds
        self._now = now or time.monotonic
        self._lock = threading.Lock()
        self._buckets: dict[str, _AttemptBucket] = {}

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()

    def retry_after(self, *keys: str) -> int | None:
        """Seconds left on the longest live lock, or None if none are locked."""
        now = self._now()
        remaining = 0.0
        with self._lock:
            for key in keys:
                bucket = self._buckets.get(key)
                if bucket is None:
                    continue
                left = bucket.locked_until - now
                if left > remaining:
                    remaining = left
        if remaining <= 0:
            return None
        return max(1, int(remaining))

    def record_failure(self, *keys: str) -> bool:
        """Count a miss on each key. True when any key is now locked."""
        now = self._now()
        locked = False
        with self._lock:
            for key in keys:
                bucket = self._buckets.setdefault(key, _AttemptBucket())
                if bucket.locked_until and bucket.locked_until <= now:
                    bucket.count = 0
                    bucket.locked_until = 0.0
                bucket.count += 1
                if bucket.count >= self.max_failures:
                    bucket.locked_until = now + self.lockout_seconds
                    locked = True
                elif bucket.locked_until > now:
                    locked = True
        return locked

    def record_success(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._buckets.pop(key, None)


_ATTEMPTS = ReviewerAttemptGuard()


def reviewer_attempt_guard() -> ReviewerAttemptGuard:
    return _ATTEMPTS


def reviewer_client_ip(*, forwarded_for: str | None, client_host: str | None) -> str:
    """Leftmost ``X-Forwarded-For`` hop, then the socket peer.

    Azure Container Apps sits in front; the leftmost hop is the browser. A
    spoofed header still hits the per-email lock once the allowlisted mailbox
    is the target.
    """
    if forwarded_for:
        first = forwarded_for.split(",")[0].strip()
        if first:
            return first
    if client_host:
        return client_host
    return "unknown"


def reviewer_attempt_keys(email: str, ip: str) -> tuple[str, str]:
    digest = hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()
    return (f"ip:{ip}", f"email:{digest}")


@dataclass(frozen=True)
class ReviewerSessionTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"


def normalize_email(email: str) -> str:
    return email.strip().lower()


def reviewer_email_allowlist(raw: str) -> frozenset[str]:
    return frozenset(normalize_email(part) for part in raw.split(",") if part.strip())


def reviewer_path_configured(emails: str, password: str) -> bool:
    return bool(reviewer_email_allowlist(emails) and password)


def is_allowlisted_reviewer(email: str, allowlist: frozenset[str]) -> bool:
    return normalize_email(email) in allowlist


def reviewer_password_matches(provided: str, expected: str) -> bool:
    """Compare after hashing so length differences do not skip the digest."""
    if not provided or not expected:
        return False
    left = hashlib.sha256(provided.encode("utf-8")).digest()
    right = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(left, right)


def reviewer_credentials_accepted(
    email: str,
    password: str,
    *,
    emails: str,
    expected_password: str,
) -> bool:
    allowlisted = is_allowlisted_reviewer(email, reviewer_email_allowlist(emails))
    password_ok = reviewer_password_matches(password, expected_password)
    return allowlisted and password_ok


def hashed_token_from_link(response: object) -> str:
    properties = getattr(response, "properties", None)
    if properties is None and isinstance(response, dict):
        properties = response.get("properties")
    token = getattr(properties, "hashed_token", None)
    if token is None and isinstance(properties, dict):
        token = properties.get("hashed_token")
    if not token or not isinstance(token, str):
        raise ReviewerSessionError("no hashed token")
    return token


def tokens_from_verified(response: object) -> ReviewerSessionTokens:
    session = getattr(response, "session", None)
    if session is None and isinstance(response, dict):
        session = response.get("session")
    if session is None:
        raise ReviewerSessionError("no session")
    access = getattr(session, "access_token", None)
    refresh = getattr(session, "refresh_token", None)
    if isinstance(session, dict):
        access = session.get("access_token", access)
        refresh = session.get("refresh_token", refresh)
    if not access or not refresh:
        raise ReviewerSessionError("incomplete session")
    expires = getattr(session, "expires_in", None)
    token_type = getattr(session, "token_type", None)
    if isinstance(session, dict):
        expires = session.get("expires_in", expires)
        token_type = session.get("token_type", token_type)
    return ReviewerSessionTokens(
        access_token=access,
        refresh_token=refresh,
        expires_in=int(expires or 0),
        token_type=str(token_type or "bearer"),
    )


def mint_reviewer_session(email: str, *, admin: object, anon: object) -> ReviewerSessionTokens:
    """Turn an allowlisted email into a Supabase session without sending mail.

    Admin ``generate_link`` creates the user if needed and does not send the
    email. Anon ``verify_otp`` on the hashed token is the same exchange a
    magic-link click would have done, minus the inbox.
    """
    link = admin.auth.admin.generate_link({"type": "magiclink", "email": email})
    hashed = hashed_token_from_link(link)
    verified = anon.auth.verify_otp({"token_hash": hashed, "type": "email"})
    return tokens_from_verified(verified)


def reviewer_path_ready(settings: Settings) -> bool:
    return reviewer_path_configured(settings.play_reviewer_emails, settings.play_reviewer_password)
