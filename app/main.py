"""FastAPI application entry point."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.account import router as account_router
from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.practice import router as practice_router
from app.config import get_settings

settings = get_settings()
logging.basicConfig(level=settings.log_level)

app = FastAPI(
    title="BadgeDay",
    description="Cited practice questions from your department's promotional reading list.",
    version="0.1.0",
)

# The browser app runs on a different origin from the API, so it needs CORS. Origins are
# listed explicitly rather than wildcarded: allow_credentials with "*" is rejected by the
# browser anyway, and an explicit list means a new deployment target is a deliberate act.
# Authorization is the header that matters — every request the app makes carries the
# candidate's token, and without it exposed here the browser strips it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(health_router)
app.include_router(documents_router)
app.include_router(practice_router)
app.include_router(account_router)
