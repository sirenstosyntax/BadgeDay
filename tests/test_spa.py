"""Serving the built SPA alongside the API from one origin.

Two things have to stay true: the API always wins over the catch-all (an API path must never
be answered with index.html), and the catch-all cannot be walked out of the build directory.
The rest is the ordinary SPA arrangement — index.html for client routes, real files for real
assets.
"""

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
