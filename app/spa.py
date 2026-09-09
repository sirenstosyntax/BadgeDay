"""Serve the built single-page app from the API's own origin.

In production the web build lands in web/dist and there is one service, so the browser app
and the API share an origin — no CORS, one URL, one thing to deploy. In development this
directory does not exist: Vite serves the app on its own port and the API is separate,
which is what the CORS config in main.py is for. So this is all conditional on the build
being present, and is a no-op without it.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_DIST = (Path(__file__).resolve().parent.parent / "web" / "dist").resolve()


def _is_inside(path: Path) -> bool:
    return path == _DIST or _DIST in path.parents


def _file_response(path: Path) -> FileResponse:
    """Serve a build file, with an explicit type for JSON.

    Play's Digital Asset Links crawler requires ``Content-Type: application/json``
    for ``/.well-known/assetlinks.json``. ``python:3.12-slim`` does not guarantee
    a ``.json`` entry in the mimetypes table, and FileResponse would otherwise
    fall back to ``text/plain``.
    """
    if path.suffix == ".json":
        return FileResponse(path, media_type="application/json")
    return FileResponse(path)


def mount_spa(app: FastAPI) -> bool:
    """Mount the SPA if it has been built. Returns whether it was mounted.

    Called after every API router, so the catch-all below only ever handles the paths the
    API did not already claim.
    """
    if not _DIST.is_dir():
        return False

    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str) -> FileResponse:
        # A real file (favicon, icons) if the path names one and stays inside the build;
        # otherwise index.html, because the app routes on the client. A URL like /account is
        # not a server path — it is the SPA booting and reading the location itself.
        #
        # The containment check is the one that matters here: full_path comes straight from
        # the URL, so without it a request for ../../something would resolve outside the
        # build directory and hand back a file that has no business being served.
        target = (_DIST / full_path).resolve()
        if full_path and _is_inside(target):
            if target.is_file():
                return _file_response(target)

            # /privacy and /terms are static pages rather than app views, and they are the
            # one part of this product that has to render for someone with no account and
            # no JavaScript — a Stripe reviewer following a link, a candidate deciding
            # whether to hand us their department's documents. They live in web/public as
            # .html files, so an extensionless path gets one more chance to name one before
            # falling through to the app. Guarded on there being no suffix already, or a
            # request for a missing thing.png would go looking for thing.html.
            if not target.suffix:
                page = target.with_name(f"{target.name}.html")
                if _is_inside(page) and page.is_file():
                    return _file_response(page)

        return _file_response(_DIST / "index.html")

    return True
