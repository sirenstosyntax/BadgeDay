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

    # --- Speech to text ------------------------------------------------------
    # Deepgram, chosen on the evidence in recruit_design_decisions.md §5 — filler_words is
    # an explicit documented switch and word timings come back by default. Blank means no
    # transcription is attempted; the fixture transcriber serves tests either way, so an
    # unset key never fails a test run.
    deepgram_api_key: str = ""
    # nova-2 with filler_words=true and smart_format=false. smart_format tidies speech into
    # readable prose, which is precisely the failure mode — a cleaned-up transcript is a
    # better one by the industry's measure and a useless one by ours.
    deepgram_model: str = "nova-2"

    @property
    def transcription_configured(self) -> bool:
        return bool(self.deepgram_api_key)

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

    # --- Web ------------------------------------------------------------------
    # Origins the browser app is served from. Comma-separated, because this arrives as an
    # environment variable. Empty in production is deliberate: an unset value permits
    # nothing rather than everything, so a deploy that forgets to set it fails visibly
    # instead of accepting requests from anywhere.
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # The one host every link, cookie and Stripe redirect should end up on. The alternates
    # (www, the .app domain) exist so a misremembered address still lands, but they are
    # redirected here rather than becoming second homes. Empty means no redirect at all —
    # correct in development and on the raw Container Apps URL.
    canonical_host: str = ""
    redirect_hosts: str = ""

    @property
    def redirect_host_set(self) -> set[str]:
        return {host.strip().lower() for host in self.redirect_hosts.split(",") if host.strip()}

    # --- Uploads -------------------------------------------------------------
    # Ceiling on a single uploaded document. A reading list is SOG packets and published
    # texts, which sit far below this; the cap exists so that one oversized or malicious
    # upload cannot be read wholesale into the process memory of a request handler.
    max_upload_bytes: int = 25 * 1024 * 1024

    # --- Recruit access (ship gate #4) ---------------------------------------
    # Free first session(s) without a card. Further attempts need a Recruit
    # row on entitlements(user, module). Promote's has_access is a different
    # product and is never consulted.
    recruit_free_sessions: int = 1
    # Cost ceiling while the bank is still one C2 prompt. 10/day is enough for
    # a real practice day and cheap enough that a leaked magic-link cannot run
    # up an unbounded Anthropic bill. UTC day.
    recruit_daily_attempt_limit: int = 10

    # --- Stripe --------------------------------------------------------------
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id_monthly: str = ""
    stripe_price_id_intensive_90day: str = ""
    # Recruit prices — held, blank. Grant's held offer (docs only, no checkout
    # go-live): first session free, no card; $24.99/mo; $59 / 90-day; $119/yr.
    # Do not invent live Stripe product IDs. Stripe stays in test mode until
    # Grant says go live. Mapping from a filled ID to the recruit module is
    # `billing.module.module_for_stripe_price`.
    stripe_price_id_recruit_monthly: str = ""
    stripe_price_id_recruit_intensive_90day: str = ""
    stripe_price_id_recruit_annual: str = ""
    # Length of the one-time intensive pass. The price is set in Stripe; how long the pass
    # it buys grants access is our decision, kept here so "90-day" is not welded into a
    # timedelta at the point a webhook grants it. Recruit's 90-day pass uses the same
    # duration when checkout is later wired; it is not a second constant.
    intensive_pass_days: int = 90

    # Where the browser app lives, used to build the URLs Stripe returns the candidate to
    # after checkout or the billing portal. Not the API's own origin — the human ends up
    # back in the web app, not on a JSON endpoint.
    public_web_url: str = "http://localhost:5173"

    @property
    def stripe_configured(self) -> bool:
        return bool(
            self.stripe_secret_key
            and self.stripe_price_id_monthly
            and self.stripe_price_id_intensive_90day
        )

    # --- App stores ----------------------------------------------------------
    # Both stores require that a subscription sold inside their app is bought through
    # their billing system, so the phone apps have a second till. See
    # mobile_release_plan.md; the entitlement it grants is the same one Stripe grants.
    #
    # Product ids are configuration for the same reason Stripe's price ids are: they are
    # created in a console, they differ between the two stores, and a typo in a hardcoded
    # one is a purchase flow that opens and then fails with an unhelpful store error.
    play_package_name: str = ""
    play_product_id_monthly: str = ""
    play_product_id_intensive_90day: str = ""
    # Recruit Play SKUs — held, blank. Same three offers as the Stripe
    # placeholders. Do not invent live IAP public SKUs.
    play_product_id_recruit_monthly: str = ""
    play_product_id_recruit_intensive_90day: str = ""
    play_product_id_recruit_annual: str = ""
    # The service account that may read purchase state from the Play Developer API, as the
    # JSON key file's contents. A purchase token means nothing without this call — the
    # notification carries no expiry date.
    play_service_account_json: str = ""
    # The Pub/Sub push subscription's expected audience and service account. Both are
    # checked on the OIDC token every notification carries; without them, any POST to the
    # notification URL would be believed.
    play_pubsub_audience: str = ""
    play_pubsub_service_account: str = ""

    appstore_bundle_id: str = ""
    appstore_product_id_monthly: str = ""
    appstore_product_id_intensive_90day: str = ""
    # Recruit App Store SKUs — held, blank. Same three offers. Do not invent
    # live IAP public SKUs.
    appstore_product_id_recruit_monthly: str = ""
    appstore_product_id_recruit_intensive_90day: str = ""
    appstore_product_id_recruit_annual: str = ""
    # App Store Server API credentials, used to check a transaction against Apple rather
    # than trust the receipt the device presented.
    appstore_issuer_id: str = ""
    appstore_key_id: str = ""
    appstore_private_key: str = ""
    # Apple's root certificates, comma-separated base64 DER, from
    # https://www.apple.com/certificateauthority/. There is no default and there must not
    # be one: a notification verifier with an empty trust store rejects every real
    # notification while looking configured, which is a subscription system that quietly
    # stops renewing people.
    appstore_root_certs: str = ""
    # Sandbox until the app is live. Apple's sandbox signs with a different chain, so a
    # mismatch here rejects every notification with a signature error that reads like a
    # credential problem.
    appstore_environment: Literal["sandbox", "production"] = "sandbox"

    @property
    def play_configured(self) -> bool:
        return bool(
            self.play_package_name
            and self.play_service_account_json
            and self.play_pubsub_audience
            and self.play_pubsub_service_account
        )

    @property
    def appstore_configured(self) -> bool:
        return bool(
            self.appstore_bundle_id
            and self.appstore_issuer_id
            and self.appstore_key_id
            and self.appstore_private_key
            # Included deliberately. Without the roots the gateway cannot verify anything,
            # so "configured" would otherwise mean "has credentials and rejects every
            # notification" — and the endpoint would answer 400 rather than 503, reporting
            # a forged notification where the truth is a missing setting.
            and self.appstore_root_certs
        )

    @property
    def subscription_product_ids(self) -> frozenset[str]:
        """Which store products are recurring, as opposed to the one-time pass.

        Apple's transaction payload does not always carry a usable type, so the configured
        list is the reliable answer to "is this a subscription" — see
        `store_payloads.parse_appstore_payload`.
        """
        return frozenset(
            p
            for p in (
                self.play_product_id_monthly,
                self.appstore_product_id_monthly,
                self.play_product_id_recruit_monthly,
                self.play_product_id_recruit_annual,
                self.appstore_product_id_recruit_monthly,
                self.appstore_product_id_recruit_annual,
            )
            if p
        )

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
