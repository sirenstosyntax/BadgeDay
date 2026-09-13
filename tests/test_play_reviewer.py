"""Play reviewer password path: env-gated, allowlisted, no emailed OTP."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_settings
from app.api.play_reviewer import router
from app.auth.play_reviewer import (
    GENERIC_DENIED,
    NOT_CONFIGURED,
    ReviewerSessionError,
    hashed_token_from_link,
    is_allowlisted_reviewer,
    mint_reviewer_session,
    normalize_email,
    reviewer_credentials_accepted,
    reviewer_email_allowlist,
    reviewer_password_matches,
    reviewer_path_configured,
    tokens_from_verified,
)
from app.config import Settings

REVIEWER = "play.reviewer@example.com"
PASSWORD = "not-a-real-reviewer-password"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "play_reviewer_emails": REVIEWER,
        "play_reviewer_password": PASSWORD,
        "supabase_url": "https://example.supabase.co",
        "supabase_anon_key": "sb_publishable_test",
        "supabase_service_role_key": "sb_secret_test",
    }
    values.update(overrides)
    return Settings(**values)


def _client(settings: Settings) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_allowlist_is_comma_separated_and_case_insensitive() -> None:
    allowlist = reviewer_email_allowlist(f" {REVIEWER.upper()} , second@example.com ")
    assert is_allowlisted_reviewer(REVIEWER, allowlist)
    assert is_allowlisted_reviewer("second@example.com", allowlist)
    assert not is_allowlisted_reviewer("other@example.com", allowlist)


def test_blank_fragments_do_not_become_an_empty_allowlist_entry() -> None:
    assert reviewer_email_allowlist(" , , ") == frozenset()
    assert reviewer_path_configured(" , ", PASSWORD) is False


def test_the_path_is_off_until_both_env_values_are_set() -> None:
    assert reviewer_path_configured("", "") is False
    assert reviewer_path_configured(REVIEWER, "") is False
    assert reviewer_path_configured("", PASSWORD) is False
    assert reviewer_path_configured(REVIEWER, PASSWORD) is True


def test_password_compare_rejects_a_near_miss() -> None:
    assert reviewer_password_matches(PASSWORD, PASSWORD) is True
    assert reviewer_password_matches(PASSWORD + "x", PASSWORD) is False
    assert reviewer_password_matches("", PASSWORD) is False
    assert reviewer_password_matches(PASSWORD, "") is False


def test_unknown_email_and_wrong_password_fail_the_same_way() -> None:
    unknown = reviewer_credentials_accepted(
        "other@example.com",
        PASSWORD,
        emails=REVIEWER,
        expected_password=PASSWORD,
    )
    wrong = reviewer_credentials_accepted(
        REVIEWER,
        "nope",
        emails=REVIEWER,
        expected_password=PASSWORD,
    )
    good = reviewer_credentials_accepted(
        REVIEWER.upper(),
        PASSWORD,
        emails=REVIEWER,
        expected_password=PASSWORD,
    )
    assert unknown is False
    assert wrong is False
    assert good is True


def test_get_reports_configured_without_leaking_secrets() -> None:
    body = _client(_settings()).get("/auth/play-reviewer").json()
    assert body == {"configured": True}
    dumped = str(body)
    assert REVIEWER not in dumped
    assert PASSWORD not in dumped
    assert "play_reviewer" not in dumped


def test_get_reports_off_when_env_is_blank() -> None:
    body = _client(_settings(play_reviewer_emails="", play_reviewer_password="")).get(
        "/auth/play-reviewer"
    )
    assert body.status_code == 200
    assert body.json() == {"configured": False}


def test_post_is_a_404_when_the_path_is_off() -> None:
    response = _client(_settings(play_reviewer_emails="", play_reviewer_password="")).post(
        "/auth/play-reviewer",
        json={"email": REVIEWER, "password": PASSWORD},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == NOT_CONFIGURED


def test_post_rejects_unknown_email_and_wrong_password_identically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    minted: list[str] = []
    monkeypatch.setattr(
        "app.api.play_reviewer.mint_reviewer_session",
        lambda email, **_: minted.append(email) or None,
    )
    client = _client(_settings())
    unknown = client.post(
        "/auth/play-reviewer",
        json={"email": "other@example.com", "password": PASSWORD},
    )
    wrong = client.post(
        "/auth/play-reviewer",
        json={"email": REVIEWER, "password": "nope"},
    )
    assert unknown.status_code == 401
    assert wrong.status_code == 401
    assert unknown.json()["detail"] == GENERIC_DENIED
    assert wrong.json()["detail"] == GENERIC_DENIED
    assert minted == []
    assert PASSWORD not in unknown.text
    assert "nope" not in wrong.text


def test_a_matching_reviewer_receives_session_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_mint(email: str, *, admin: object, anon: object):
        assert email == REVIEWER
        assert admin is not None
        assert anon is not None
        return SimpleNamespace(
            access_token="access-token",
            refresh_token="refresh-token",
            expires_in=3600,
            token_type="bearer",
        )

    monkeypatch.setattr("app.api.play_reviewer.mint_reviewer_session", fake_mint)
    monkeypatch.setattr("app.api.play_reviewer.service_client", lambda settings: object())
    monkeypatch.setattr("app.api.play_reviewer.create_client", lambda *a, **k: object())

    response = _client(_settings()).post(
        "/auth/play-reviewer",
        json={"email": f"  {REVIEWER.upper()}  ", "password": PASSWORD},
    )
    assert response.status_code == 200
    assert response.json() == {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "expires_in": 3600,
        "token_type": "bearer",
    }


def test_supabase_failure_is_a_503_not_a_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(email: str, *, admin: object, anon: object):
        raise ReviewerSessionError("no session")

    monkeypatch.setattr("app.api.play_reviewer.mint_reviewer_session", boom)
    monkeypatch.setattr("app.api.play_reviewer.service_client", lambda settings: object())
    monkeypatch.setattr("app.api.play_reviewer.create_client", lambda *a, **k: object())

    response = _client(_settings()).post(
        "/auth/play-reviewer",
        json={"email": REVIEWER, "password": PASSWORD},
    )
    assert response.status_code == 503
    assert "access_token" not in response.json()


def test_missing_supabase_config_is_a_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.api.play_reviewer.mint_reviewer_session",
        lambda *a, **k: pytest.fail("must not mint without supabase"),
    )
    response = _client(
        _settings(supabase_url="", supabase_anon_key="", supabase_service_role_key="")
    ).post(
        "/auth/play-reviewer",
        json={"email": REVIEWER, "password": PASSWORD},
    )
    assert response.status_code == 503


def test_mint_exchanges_a_generated_link_without_sending_mail() -> None:
    calls: list[tuple[str, object]] = []

    class Admin:
        class auth:
            class admin:
                @staticmethod
                def generate_link(params: dict) -> object:
                    calls.append(("generate_link", params))
                    return SimpleNamespace(properties=SimpleNamespace(hashed_token="hash-1"))

    class Anon:
        class auth:
            @staticmethod
            def verify_otp(params: dict) -> object:
                calls.append(("verify_otp", params))
                return SimpleNamespace(
                    session=SimpleNamespace(
                        access_token="access",
                        refresh_token="refresh",
                        expires_in=120,
                        token_type="bearer",
                    )
                )

    tokens = mint_reviewer_session(REVIEWER, admin=Admin, anon=Anon)
    assert tokens.access_token == "access"
    assert tokens.refresh_token == "refresh"
    assert tokens.expires_in == 120
    assert calls[0] == ("generate_link", {"type": "magiclink", "email": REVIEWER})
    assert calls[1] == ("verify_otp", {"token_hash": "hash-1", "type": "email"})


def test_link_and_session_parsers_accept_objects_and_dicts() -> None:
    assert hashed_token_from_link({"properties": {"hashed_token": "abc"}}) == "abc"
    assert (
        hashed_token_from_link(SimpleNamespace(properties=SimpleNamespace(hashed_token="abc")))
        == "abc"
    )
    tokens = tokens_from_verified(
        {"session": {"access_token": "a", "refresh_token": "r", "expires_in": 9}}
    )
    assert tokens.access_token == "a"
    assert tokens.refresh_token == "r"
    assert tokens.expires_in == 9
    with pytest.raises(ReviewerSessionError):
        hashed_token_from_link({})
    with pytest.raises(ReviewerSessionError):
        tokens_from_verified({})


def test_normalize_email_strips_and_lowercases() -> None:
    assert normalize_email("  Play.Reviewer@Example.COM ") == REVIEWER


def test_the_mounted_app_exposes_the_reviewer_status() -> None:
    from app.main import app

    response = TestClient(app).get("/auth/play-reviewer")
    assert response.status_code == 200
    assert response.json() == {"configured": False}
