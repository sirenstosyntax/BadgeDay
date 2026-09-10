"""Config validation.

The `.env` variables sit next to each other and hold similar-looking opaque strings, so
pasting one into the wrong slot is an easy mistake. These tests cover the case that
actually happened during setup: an Anthropic API key pasted into the Azure endpoint.
"""

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_blank_endpoint_is_allowed() -> None:
    """Blank means 'use the fixture analyzer', which is a valid state."""
    assert Settings(azure_docintel_endpoint="").azure_docintel_endpoint == ""


def test_valid_endpoint_is_accepted() -> None:
    endpoint = "https://sts-docintel.cognitiveservices.azure.com/"
    assert Settings(azure_docintel_endpoint=endpoint).azure_docintel_endpoint == endpoint


def test_api_key_pasted_into_endpoint_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must be a URL"):
        Settings(azure_docintel_endpoint="sk-ant-api03-Xy9fake")


def test_rejection_message_names_the_variable_and_where_to_find_it() -> None:
    """The error is read by someone with a dashboard open, not a debugger."""
    with pytest.raises(ValidationError) as exc:
        Settings(azure_docintel_endpoint="not-a-url")
    message = str(exc.value)
    assert "AZURE_DOCINTEL_ENDPOINT" in message
    assert "Keys and Endpoint" in message


def test_recruit_access_defaults() -> None:
    settings = Settings()
    assert settings.recruit_free_sessions == 1
    assert settings.recruit_daily_attempt_limit == 10
    assert settings.stripe_price_id_recruit_monthly == ""
    assert settings.stripe_price_id_recruit_intensive_90day == ""
    assert settings.stripe_price_id_recruit_6month == ""
    assert settings.stripe_price_id_recruit_annual == ""
    assert settings.play_product_id_recruit_monthly == ""
    assert settings.play_product_id_recruit_intensive_90day == ""
    assert settings.play_product_id_recruit_6month == ""
    assert settings.play_product_id_recruit_annual == ""
    assert settings.appstore_product_id_recruit_monthly == ""
    assert settings.appstore_product_id_recruit_intensive_90day == ""
    assert settings.appstore_product_id_recruit_6month == ""
    assert settings.appstore_product_id_recruit_annual == ""


def test_recruit_subscription_product_ids_are_included_when_named() -> None:
    """A filled Recruit monthly/6-month/annual SKU is recurring; the 90-day pass is not."""
    settings = Settings(
        play_product_id_recruit_monthly="badgeday.recruit.monthly",
        play_product_id_recruit_6month="badgeday.recruit.6month",
        play_product_id_recruit_annual="badgeday.recruit.annual",
        play_product_id_recruit_intensive_90day="badgeday.recruit.90day",
        appstore_product_id_recruit_monthly="ios.recruit.monthly",
    )
    ids = settings.subscription_product_ids
    assert "badgeday.recruit.monthly" in ids
    assert "badgeday.recruit.6month" in ids
    assert "badgeday.recruit.annual" in ids
    assert "ios.recruit.monthly" in ids
    assert "badgeday.recruit.90day" not in ids


def test_configured_requires_both_endpoint_and_key() -> None:
    endpoint = "https://sts-docintel.cognitiveservices.azure.com/"
    assert not Settings(
        azure_docintel_endpoint=endpoint, azure_docintel_key=""
    ).azure_docintel_configured
    assert not Settings(
        azure_docintel_endpoint="", azure_docintel_key="k"
    ).azure_docintel_configured
    assert Settings(
        azure_docintel_endpoint=endpoint, azure_docintel_key="k"
    ).azure_docintel_configured
