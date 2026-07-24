"""Alternate domains 301 to the canonical host; everything else passes through.

The passing-through is the part that matters as much as the redirect: the canonical host
itself, and unrelated hosts like the raw Container Apps URL and the platform's health probe,
must not be redirected, or the app would bounce its own traffic.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.redirect import add_canonical_redirect

CONFIG = Settings(
    canonical_host="badgeday.com",
    redirect_hosts="www.badgeday.com, badgeday.app, www.badgeday.app",
)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()

    @app.get("/{path:path}")
    def anything(path: str) -> dict:
        return {"served": path}

    assert add_canonical_redirect(app, CONFIG) is True
    return TestClient(app, follow_redirects=False)


def test_the_app_domain_redirects_to_the_apex(client: TestClient) -> None:
    r = client.get("/practice?doc=304", headers={"host": "badgeday.app"})
    assert r.status_code == 301
    assert r.headers["location"] == "https://badgeday.com/practice?doc=304"


def test_www_redirects_to_the_apex(client: TestClient) -> None:
    r = client.get("/", headers={"host": "www.badgeday.com"})
    assert r.status_code == 301
    assert r.headers["location"] == "https://badgeday.com/"


def test_the_canonical_host_is_served_not_redirected(client: TestClient) -> None:
    r = client.get("/me", headers={"host": "badgeday.com"})
    assert r.status_code == 200
    assert r.json() == {"served": "me"}


def test_an_unrelated_host_passes_through(client: TestClient) -> None:
    """The raw Container Apps URL and the health probe are not alternates — never bounce them."""
    probe = "badgeday-web.redgrass.centralus.azurecontainerapps.io"
    r = client.get("/health", headers={"host": probe})
    assert r.status_code == 200


def test_it_is_a_no_op_when_unconfigured() -> None:
    app = FastAPI()
    assert add_canonical_redirect(app, Settings()) is False
