"""HTTP surface for the Play reviewer password path.

GET reports only whether the path is wired — never the allowlist or the
password — so the sign-in screen can show a password field without baking
secrets into the SPA. POST mints a session only for an allowlisted email
that presents the configured password.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from supabase import create_client

from app.api.deps import SettingsDep
from app.auth.play_reviewer import (
    GENERIC_DENIED,
    NOT_CONFIGURED,
    UNAVAILABLE,
    ReviewerSessionError,
    mint_reviewer_session,
    normalize_email,
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


@router.post("/auth/play-reviewer")
def play_reviewer_sign_in(
    body: PlayReviewerSignIn, settings: SettingsDep
) -> PlayReviewerSession:
    if not reviewer_path_ready(settings):
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_CONFIGURED)

    email = normalize_email(body.email)
    if not reviewer_credentials_accepted(
        email,
        body.password,
        emails=settings.play_reviewer_emails,
        expected_password=settings.play_reviewer_password,
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, GENERIC_DENIED)

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
