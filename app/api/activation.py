"""One-tap start bookkeeping and the unsubscribe link.

signup src and the test date are written with the service role because
profiles is not candidate-writable. The unsubscribe route is public: the
mail client has the token and no session.
"""

from datetime import UTC, date, datetime
from html import escape

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from app.api.deps import CurrentUserDep, ServiceDbDep
from app.storage.activation import store_signup_src, store_test_date, unsubscribe_token

router = APIRouter(tags=["activation"])

_UNSUBSCRIBED = "You're unsubscribed. BadgeDay will not email you about the oral board."
_INVALID = "This unsubscribe link is not valid."


class SignupSrcBody(BaseModel):
    src: str | None = None
    referrer_domain: str | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None


class TestDateBody(BaseModel):
    test_on: date | None = None


@router.post("/me/signup-src", status_code=204)
def post_signup_src(body: SignupSrcBody, user: CurrentUserDep, service: ServiceDbDep) -> None:
    """Store the link tag and first-touch columns once. Invalid values write nothing."""
    store_signup_src(
        service,
        user.id,
        body.src,
        referrer_domain=body.referrer_domain,
        utm_source=body.utm_source,
        utm_medium=body.utm_medium,
        utm_campaign=body.utm_campaign,
    )


@router.put("/me/recruit-test-date", status_code=204)
def put_test_date(body: TestDateBody, user: CurrentUserDep, service: ServiceDbDep) -> None:
    """One date. A date inside seven days schedules no reminder."""
    store_test_date(service, user.id, body.test_on, datetime.now(UTC))


def _page(message: str, status: int) -> HTMLResponse:
    safe = escape(message)
    html = (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width, initial-scale=1">'
        f"<title>BadgeDay</title></head><body><p>{safe}</p>"
        "<p>BadgeDay · Sirens to Syntax LLC</p></body></html>"
    )
    return HTMLResponse(html, status_code=status)


@router.api_route("/email/unsubscribe", methods=["GET", "POST"])
def unsubscribe(request: Request, service: ServiceDbDep, token: str = "") -> Response:
    """One click from the letter, or the mail client's List-Unsubscribe POST."""
    ok = unsubscribe_token(service, token, datetime.now(UTC))
    message = _UNSUBSCRIBED if ok else _INVALID
    status = 200 if ok else 404
    if request.method == "POST":
        return PlainTextResponse(message, status_code=status)
    return _page(message, status)
