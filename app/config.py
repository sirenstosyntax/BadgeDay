"""Application configuration.

Every secret and every tunable comes from the environment. Nothing that varies by
deployment — pricing, model IDs, endpoints — is hardcoded at a call site.
"""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
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
    # Direct Postgres connection, used only to apply migrations and to verify RLS.
    # Application code goes through the Supabase client, never this.
    supabase_db_url: str = ""

    # --- Uploads -------------------------------------------------------------
    # Ceiling on a single uploaded document. A reading list is SOG packets and published
    # texts, which sit far below this; the cap exists so that one oversized or malicious
    # upload cannot be read wholesale into the process memory of a request handler.
    max_upload_bytes: int = 25 * 1024 * 1024

    # --- Stripe --------------------------------------------------------------
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id_monthly: str = ""
    stripe_price_id_intensive_90day: str = ""

    @field_validator("azure_docintel_endpoint")
    @classmethod
    def _endpoint_must_be_a_url(cls, value: str) -> str:
        """Reject a non-URL endpoint at startup rather than deep in the pipeline.

        Pasting the wrong secret into this field is an easy mistake — the variables sit
        next to each other in .env — and without this check the failure surfaces much
        later as an opaque HTTP error during ingestion.
        """
        if value and not value.startswith("https://"):
            raise ValueError(
                "AZURE_DOCINTEL_ENDPOINT must be a URL beginning with https:// — for "
                "example https://sts-docintel.cognitiveservices.azure.com/. Find it in "
                "the Azure portal under your Document Intelligence resource -> Keys and "
                "Endpoint. (If the value you pasted starts with 'sk-', that is an API "
                "key, not an endpoint.)"
            )
        return value

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
