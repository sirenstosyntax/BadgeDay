"""The request-scoped identity seam.

These tests never reach Supabase. What they pin down is the behaviour around the call —
that an unauthenticated request is refused before any database work is attempted, and
that a candidate's token actually lands on the clients that talk to PostgREST and
Storage. The second one is the whole privacy design: if the token is dropped somewhere
between `user_client` and the wire, every query silently runs as the anonymous role and
the RLS policies verified in scripts/verify_schema.py stop applying to anything.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import CurrentUser, CurrentUserDep, verify_access_token
from app.config import Settings
from app.storage.client import user_client

SETTINGS = Settings(
    supabase_url="https://example.supabase.co",
    supabase_anon_key="sb_publishable_test",
    supabase_service_role_key="sb_secret_test",
)


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/whoami")
    def whoami(user: CurrentUserDep) -> dict[str, str]:
        return {"id": user.id}

    return app


client = TestClient(_app())


# --- Refusing the request ----------------------------------------------------


def test_no_credentials_is_refused() -> None:
    response = client.get("/whoami")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_a_non_bearer_scheme_is_refused() -> None:
    response = client.get("/whoami", headers={"Authorization": "Basic Zm9vOmJhcg=="})
    assert response.status_code == 401


def test_a_rejected_token_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Supabase declining the token must surface as 401, not as a 500."""
    from supabase import AuthApiError

    class Auth:
        def get_user(self, token: str):
            raise AuthApiError("bad jwt", 401, "401")

    monkeypatch.setattr(
        "app.api.deps.create_client", lambda *a, **k: type("C", (), {"auth": Auth()})()
    )

    with pytest.raises(Exception) as exc:
        verify_access_token(SETTINGS, "expired-token")
    assert exc.value.status_code == 401


def test_an_unknown_token_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 200 carrying no user is still not an authenticated request."""

    class Auth:
        def get_user(self, token: str):
            return None

    monkeypatch.setattr(
        "app.api.deps.create_client", lambda *a, **k: type("C", (), {"auth": Auth()})()
    )

    with pytest.raises(Exception) as exc:
        verify_access_token(SETTINGS, "unknown-token")
    assert exc.value.status_code == 401


# --- Carrying the token through ----------------------------------------------


def test_a_verified_token_reaches_the_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.api.deps.verify_access_token",
        lambda settings, token: CurrentUser(id="user-1", email="a@example.com", access_token=token),
    )
    response = client.get("/whoami", headers={"Authorization": "Bearer good-token"})
    assert response.status_code == 200
    assert response.json() == {"id": "user-1"}


def test_the_candidates_token_is_attached_to_every_supabase_surface() -> None:
    """Both PostgREST and Storage must carry it.

    Storage matters as much as the tables: objects are keyed `<user_id>/...` and the
    bucket policies compare that first path segment to auth.uid(). A client that
    authenticated for queries but not for file access would fail closed on reads — and
    quietly write uploads that no policy had vetted.
    """
    supabase = user_client(SETTINGS, "candidate-token")
    assert supabase.postgrest.session.headers["Authorization"] == "Bearer candidate-token"
    assert supabase.storage.session.headers["Authorization"] == "Bearer candidate-token"


def test_two_candidates_get_separately_scoped_clients() -> None:
    """No shared mutable client — one candidate's token must not leak into another's."""
    alice = user_client(SETTINGS, "alice-token")
    bob = user_client(SETTINGS, "bob-token")
    assert alice.postgrest.session.headers["Authorization"] == "Bearer alice-token"
    assert bob.postgrest.session.headers["Authorization"] == "Bearer bob-token"
