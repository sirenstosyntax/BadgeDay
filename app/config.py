"""Application configuration.

Every secret and every tunable comes from the environment. Nothing that varies by
deployment — pricing, model IDs, endpoints — is hardcoded at a call site.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Runtime -------------------------------------------------------------
    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"

    # --- Anthropic -----------------------------------------------------------
    anthropic_api_key: str = ""
    generation_model: str = "claude-sonnet-5"
    generation_effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"

    # --- Azure Document Intelligence -----------------------------------------
    # Blank endpoint means the fixture analyzer is used. See app/ingest/analyzer.py.
    azure_docintel_endpoint: str = ""
    azure_docintel_key: str = ""

    # --- Supabase ------------------------------------------------------------
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # --- Stripe --------------------------------------------------------------
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id_monthly: str = ""
    stripe_price_id_intensive_90day: str = ""

    @property
    def azure_docintel_configured(self) -> bool:
        return bool(self.azure_docintel_endpoint and self.azure_docintel_key)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor. Use as a FastAPI dependency."""
    return Settings()
