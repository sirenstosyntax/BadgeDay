"""Health and readiness endpoints.

`/health` is a liveness check — it answers "is the process up" and never touches a
dependency. `/ready` reports which external services are configured, without calling
them, so a deploy can tell at a glance what is still unwired.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings

router = APIRouter(tags=["health"])

SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(settings: SettingsDep) -> dict[str, object]:
    """Report configuration state of each external dependency.

    This deliberately does not make network calls — it answers "is this wired up",
    not "is this reachable".
    """
    return {
        "status": "ok",
        "environment": settings.environment,
        "configured": {
            "anthropic": bool(settings.anthropic_api_key),
            "azure_document_intelligence": settings.azure_docintel_configured,
            "supabase": bool(settings.supabase_url and settings.supabase_service_role_key),
            "stripe": bool(settings.stripe_secret_key),
        },
    }
