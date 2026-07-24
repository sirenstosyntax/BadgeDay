"""Send every alternate domain to the one canonical host.

badgeday.com is the address people are given. www.badgeday.com and badgeday.app exist so a
misremembered one still lands — but they must not become second homes: cookies, the Stripe
redirect URLs and shared links all assume a single host. So a request arriving on an
alternate host is 301'd to the canonical one, scheme forced to https, path and query intact.

A no-op unless a canonical host is configured, which it is not in development or on the raw
Container Apps URL. That is also what keeps it clear of the platform's own health probes:
their Host is the app's internal name, never one of the configured alternates, so they pass
straight through.
"""

from fastapi import FastAPI, Request
from starlette.responses import RedirectResponse

from app.config import Settings


def add_canonical_redirect(app: FastAPI, settings: Settings) -> bool:
    """Install the redirect if a canonical host and alternates are configured."""
    if not (settings.canonical_host and settings.redirect_host_set):
        return False

    canonical = settings.canonical_host
    alternates = settings.redirect_host_set

    @app.middleware("http")
    async def _redirect_to_canonical(request: Request, call_next):
        host = (request.headers.get("host") or "").split(":")[0].lower()
        if host in alternates:
            target = request.url.replace(scheme="https", netloc=canonical)
            return RedirectResponse(str(target), status_code=301)
        return await call_next(request)

    return True
