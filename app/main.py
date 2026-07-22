"""FastAPI application entry point."""

import logging

from fastapi import FastAPI

from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.config import get_settings

settings = get_settings()
logging.basicConfig(level=settings.log_level)

app = FastAPI(
    title="BadgeDay",
    description="Cited practice questions from your department's promotional reading list.",
    version="0.1.0",
)

app.include_router(health_router)
app.include_router(documents_router)
