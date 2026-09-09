"""Price ID → module. A blank placeholder must never grant either product.

Ship gate #4 holds Recruit pricing. The mapping is what a later checkout will
use to decide which entitlements row to write. Getting Promote and Recruit
swapped here is how a Lieutenant subscription would open the oral board.
"""

from app.billing.module import (
    module_for_store_product,
    module_for_stripe_price,
    store_product_ids_for,
    stripe_price_ids_for,
)
from app.config import Settings


def test_blank_ids_map_to_no_module() -> None:
    settings = Settings()
    assert module_for_stripe_price(settings, "") is None
    assert module_for_store_product(settings, "") is None
    assert stripe_price_ids_for(settings, "recruit") == frozenset()
    assert store_product_ids_for(settings, "recruit") == frozenset()


def test_a_recruit_price_id_is_recruit_not_promote() -> None:
    settings = Settings(
        stripe_price_id_monthly="price_promote_mo",
        stripe_price_id_intensive_90day="price_promote_90",
        stripe_price_id_recruit_monthly="price_recruit_mo",
        stripe_price_id_recruit_intensive_90day="price_recruit_90",
        stripe_price_id_recruit_annual="price_recruit_yr",
    )
    assert module_for_stripe_price(settings, "price_recruit_mo") == "recruit"
    assert module_for_stripe_price(settings, "price_recruit_90") == "recruit"
    assert module_for_stripe_price(settings, "price_recruit_yr") == "recruit"
    assert module_for_stripe_price(settings, "price_promote_mo") == "promote"
    assert module_for_stripe_price(settings, "price_promote_90") == "promote"


def test_an_unknown_price_id_grants_neither_module() -> None:
    settings = Settings(stripe_price_id_recruit_monthly="price_recruit_mo")
    assert module_for_stripe_price(settings, "price_someone_invented") is None


def test_a_recruit_store_sku_is_recruit() -> None:
    settings = Settings(
        play_product_id_monthly="badgeday.promote.monthly",
        play_product_id_recruit_monthly="badgeday.recruit.monthly",
        play_product_id_recruit_annual="badgeday.recruit.annual",
        appstore_product_id_recruit_intensive_90day="badgeday.recruit.90day",
    )
    assert module_for_store_product(settings, "badgeday.recruit.monthly") == "recruit"
    assert module_for_store_product(settings, "badgeday.recruit.annual") == "recruit"
    assert module_for_store_product(settings, "badgeday.recruit.90day") == "recruit"
    assert module_for_store_product(settings, "badgeday.promote.monthly") == "promote"


def test_blank_placeholders_are_not_treated_as_a_shared_id() -> None:
    """Every Recruit and Promote ID defaults to ''. That must not mean they match."""
    settings = Settings()
    assert module_for_stripe_price(settings, "") is None
    assert "" not in stripe_price_ids_for(settings, "recruit")
    assert "" not in stripe_price_ids_for(settings, "promote")
