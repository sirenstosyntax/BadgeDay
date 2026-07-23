"""Who is making this request, and the database handle that answers as them.

Every endpoint serving candidate data takes `DbDep`. That client carries the candidate's
own token, so the rows it returns are the rows their policies allow — the handler does
not filter by `user_id` and must not start, because a filter that is merely remembered
is a filter that can be forgotten.

`current_user` resolves the token by asking Supabase rather than by verifying the JWT
signature locally. It costs a round trip per request, and buys the one thing local
verification cannot give: a token belonging to a deleted or signed-out user stops working
immediately, instead of staying valid until it expires. Given that account deletion is a
V1 promise, honouring it within the hour rather than within the token lifetime is worth
the round trip. If it later becomes a bottleneck, the swap is behind
`verify_access_token` alone.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from supabase import AuthError, Client, create_client

from app.billing.gateway import PaymentGateway, StripeGateway
from app.config import Settings, get_settings
from app.storage.client import service_client, user_client

SettingsDep = Annotated[Settings, Depends(get_settings)]

_bearer = HTTPBearer(
    auto_error=False,
    description="Supabase access token, as issued to the signed-in candidate.",
)

_UNAUTHENTICATED = {"WWW-Authenticate": "Bearer"}


class CurrentUser(BaseModel):
    """The candidate this request belongs to.

    `access_token` is carried so the request can build a database client that answers as
    them. It is never logged and never stored.
    """

    id: str
    email: str | None = None
    access_token: str


def verify_access_token(settings: Settings, token: str) -> CurrentUser:
    """Resolve an access token to its owner, or refuse the request.

    The anon key is deliberate: this asks "who does this token belong to", a question the
    publishable key is allowed to ask. Using the service role here would let a malformed
    token be resolved with elevated credentials, which is a strange risk to take for a
    lookup that works fine without them.
    """
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    try:
        response = client.auth.get_user(token)
    except AuthError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or expired access token.",
            headers=_UNAUTHENTICATED,
        ) from exc

    if response is None or response.user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or expired access token.",
            headers=_UNAUTHENTICATED,
        )

    return CurrentUser(id=response.user.id, email=response.user.email, access_token=token)


def current_user(
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Sign in to continue.",
            headers=_UNAUTHENTICATED,
        )
    return verify_access_token(settings, credentials.credentials)


CurrentUserDep = Annotated[CurrentUser, Depends(current_user)]


def user_db(user: CurrentUserDep, settings: SettingsDep) -> Client:
    """A database client that answers as the candidate, subject to their policies."""
    return user_client(settings, user.access_token)


DbDep = Annotated[Client, Depends(user_db)]


def service_db(settings: SettingsDep) -> Client:
    """A service-role client, RLS bypassed. For trusted, non-candidate writes only.

    Two endpoints need it: the Stripe webhook, whose caller is Stripe rather than a
    candidate, and account deletion, which removes an auth user (an admin operation no
    candidate token can perform). Never reach for it to serve a candidate's own data — that
    is what `user_db` is for, and storage/client.py explains why the distinction matters.
    """
    return service_client(settings)


def get_gateway(settings: SettingsDep) -> PaymentGateway:
    return StripeGateway(settings)


ServiceDbDep = Annotated[Client, Depends(service_db)]
GatewayDep = Annotated[PaymentGateway, Depends(get_gateway)]
