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
from dataclasses import dataclass

from app.config import Settings

GENERIC_DENIED = "That email and password did not match."
UNAVAILABLE = "Sign-in is unavailable right now."
NOT_CONFIGURED = "Not found."


class ReviewerSessionError(RuntimeError):
    """Supabase did not hand back a usable session. Callers map this to 503."""


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
