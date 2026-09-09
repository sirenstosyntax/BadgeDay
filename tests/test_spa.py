"""Serving the built SPA alongside the API from one origin.

Two things have to stay true: the API always wins over the catch-all (an API path must never
be answered with index.html), and the catch-all cannot be walked out of the build directory.
The rest is the ordinary SPA arrangement — index.html for client routes, real files for real
assets.
"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.spa as spa_module
from app.spa import mount_spa


@pytest.fixture
def client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    dist = (tmp_path / "dist").resolve()
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>BadgeDay</title>")
    (dist / "assets" / "index.js").write_text("console.log('app')")
    (dist / "favicon.svg").write_text("<svg></svg>")
    (dist / "privacy.html").write_text("<!doctype html><title>Privacy Policy</title>")
    monkeypatch.setattr(spa_module, "_DIST", dist)

    app = FastAPI()

    @app.get("/me")
    def me() -> dict:
        return {"api": True}

    assert mount_spa(app) is True
    return TestClient(app)


def test_the_root_serves_the_app(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "BadgeDay" in response.text


def test_a_client_route_falls_back_to_the_app(client: TestClient) -> None:
    """/account is not a server path — it is the SPA reading the URL itself, so index.html."""
    response = client.get("/account")
    assert response.status_code == 200
    assert "BadgeDay" in response.text


def test_an_api_route_is_not_shadowed_by_the_catch_all(client: TestClient) -> None:
    response = client.get("/me")
    assert response.json() == {"api": True}


def test_a_real_asset_is_served_as_itself(client: TestClient) -> None:
    response = client.get("/favicon.svg")
    assert response.status_code == 200
    assert "<svg>" in response.text


def test_assetlinks_is_json_not_the_spa(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Play fetches /.well-known/assetlinks.json and requires application/json."""
    dist = (tmp_path / "dist").resolve()
    well_known = dist / ".well-known"
    well_known.mkdir(parents=True)
    (dist / "assets").mkdir()
    (dist / "index.html").write_text("<!doctype html><title>BadgeDay</title>")
    statement = [{"relation": ["delegate_permission/common.handle_all_urls"]}]
    (well_known / "assetlinks.json").write_text(json.dumps(statement))
    monkeypatch.setattr(spa_module, "_DIST", dist)

    app = FastAPI()
    assert mount_spa(app) is True
    response = TestClient(app).get("/.well-known/assetlinks.json")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == statement
    assert "BadgeDay" not in response.text


def test_a_legal_page_is_served_at_a_clean_url(client: TestClient) -> None:
    """/privacy is privacy.html, not the SPA. It has to render with no account and no JS."""
    response = client.get("/privacy")
    assert response.status_code == 200
    assert "Privacy Policy" in response.text


def test_the_html_fallback_does_not_fire_for_a_path_with_a_suffix(client: TestClient) -> None:
    """A missing asset stays a missing asset — it must not resolve to a same-named page."""
    response = client.get("/privacy.svg")
    assert "Privacy Policy" not in response.text
    assert "BadgeDay" in response.text


def test_a_path_escaping_the_build_is_refused(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The containment guard: a resolved path outside the build must not be served."""
    dist = (tmp_path / "dist").resolve()
    dist.mkdir()
    monkeypatch.setattr(spa_module, "_DIST", dist)
    (tmp_path / "secret.txt").write_text("do not serve me")
    assert spa_module._is_inside(dist / "index.html") is True
    assert spa_module._is_inside((dist / ".." / "secret.txt").resolve()) is False


def test_it_is_a_no_op_when_the_build_is_absent(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(spa_module, "_DIST", (tmp_path / "nonexistent").resolve())
    app = FastAPI()
    assert mount_spa(app) is False
