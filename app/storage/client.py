"""Supabase clients. The difference between the two of them is the privacy guarantee.

`user_client` carries the candidate's own access token, so every query it makes runs
under row-level security: the database returns their rows and nobody else's, whatever
the calling code asks for. This is the client that serves API requests.

`service_client` bypasses RLS completely. It exists for the ingestion worker, which
writes chunks and questions — tables that deliberately have no client insert policy,
because a candidate must not be able to author the questions they are then graded on.

Reaching for `service_client` inside a request handler would quietly move the privacy
boundary out of the database and into whatever `.eq("user_id", ...)` filters the handler
remembered to write. That is the precise failure `scripts/verify_schema.py` exists to
catch, and it would still report 27 passing checks while the application leaked, because
it tests the database rather than the code above it. Don't do it.
"""

from supabase import Client, ClientOptions, create_client

from app.config import Settings


def user_client(settings: Settings, access_token: str) -> Client:
    """A client scoped to one candidate, for use inside a request.

    Built on the publishable key with the candidate's token attached, which is what makes
    PostgREST resolve `auth.uid()` to them and apply their policies. Supabase verifies
    the token itself on every call, so this is a real boundary and not a courtesy — a
    forged token does not become trusted by being passed through here.
    """
    return create_client(
        settings.supabase_url,
        settings.supabase_anon_key,
        ClientOptions(headers={"Authorization": f"Bearer {access_token}"}),
    )


_service: Client | None = None


def service_client(settings: Settings) -> Client:
    """The worker's client, with RLS bypassed. Never use this to serve a request.

    Cached, because it holds no per-request state — unlike `user_client`, whose whole
    purpose is to hold exactly that.
    """
    global _service
    if _service is None:
        _service = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _service


def reset_service_client() -> None:
    """Drop the cached service client. For tests that swap settings between cases."""
    global _service
    _service = None
