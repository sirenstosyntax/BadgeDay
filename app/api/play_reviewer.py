"""HTTP surface for the Play reviewer password path.

GET reports only whether the path is wired — never the allowlist or the
password — so the sign-in screen can show a password field without baking
secrets into the SPA. POST mints a session only for an allowlisted email
that presents the configured password. Repeated misses lock the client IP
and the attempted email so the shared password is not an online oracle.
"""

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from supabase import create_client

from app.api.deps import SettingsDep
from app.auth.play_reviewer import (
    GENERIC_DENIED,
    NOT_CONFIGURED,
    TOO_MANY_ATTEMPTS,
    UNAVAILABLE,
    ReviewerSessionError,
    mint_reviewer_session,
    normalize_email,
    reviewer_attempt_guard,
    reviewer_attempt_keys,
    reviewer_client_ip,
    reviewer_credentials_accepted,
    reviewer_path_ready,
)
from app.storage.client import service_client

router = APIRouter(tags=["auth"])


class PlayReviewerStatus(BaseModel):
    configured: bool


class PlayReviewerSignIn(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)


class PlayReviewerSession(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"


@router.get("/auth/play-reviewer")
def play_reviewer_status(settings: SettingsDep) -> PlayReviewerStatus:
    return PlayReviewerStatus(configured=reviewer_path_ready(settings))


def _locked_out(keys: tuple[str, str]) -> HTTPException:
    retry_after = reviewer_attempt_guard().retry_after(*keys)
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        TOO_MANY_ATTEMPTS,
        headers=headers,
    )


@router.post("/auth/play-reviewer")
def play_reviewer_sign_in(
    body: PlayReviewerSignIn, request: Request, settings: SettingsDep
) -> PlayReviewerSession:
    if not reviewer_path_ready(settings):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_CONFIGURED)

    email = normalize_email(body.email)
    ip = reviewer_client_ip(
        forwarded_for=request.headers.get("x-forwarded-for"),
        client_host=request.client.host if request.client else None,
    )
    keys = reviewer_attempt_keys(email, ip)
    if reviewer_attempt_guard().retry_after(*keys) is not None:
        raise _locked_out(keys)

    if not reviewer_credentials_accepted(
        email,
        body.password,
        emails=settings.play_reviewer_emails,
        expected_password=settings.play_reviewer_password,
    ):
        if reviewer_attempt_guard().record_failure(*keys):
            raise _locked_out(keys)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, GENERIC_DENIED)

    reviewer_attempt_guard().record_success(*keys)

    if not (
        settings.supabase_url
        and settings.supabase_anon_key
        and settings.supabase_service_role_key
    ):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE)

    try:
        tokens = mint_reviewer_session(
            email,
            admin=service_client(settings),
            anon=create_client(settings.supabase_url, settings.supabase_anon_key),
        )
    except ReviewerSessionError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from exc
    except Exception as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, UNAVAILABLE) from exc

    return PlayReviewerSession(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        token_type=tokens.token_type,
    )
