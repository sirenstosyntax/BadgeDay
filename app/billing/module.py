"""Which Stripe price or store product buys which module.

Recruit and Promote are separate plans. A completed checkout must grant the
module the price belongs to, never the other one, and never both. That mapping
lives here, next to the configured IDs, and is resolved server-side — never
inferred from checkout metadata alone (recruit_scope.md).

Blank IDs are placeholders. Ship gate #4 does not go live on pricing: Stripe
stays in test mode, Play IAP public SKUs stay unnamed, and a blank ID maps to
no module. Filling an ID later is how Grant says go live; it is not how a
candidate grants themselves access.
"""

from typing import Literal

from app.config import Settings

Module = Literal["promote", "recruit"]


def _filled(*ids: str) -> frozenset[str]:
    return frozenset(value for value in ids if value)


def stripe_price_ids_for(settings: Settings, module: Module) -> frozenset[str]:
    if module == "recruit":
        return _filled(
            settings.stripe_price_id_recruit_monthly,
            settings.stripe_price_id_recruit_intensive_90day,
            settings.stripe_price_id_recruit_6month,
            settings.stripe_price_id_recruit_annual,
        )
    return _filled(
        settings.stripe_price_id_monthly,
        settings.stripe_price_id_intensive_90day,
    )


def store_product_ids_for(settings: Settings, module: Module) -> frozenset[str]:
    if module == "recruit":
        return _filled(
            settings.play_product_id_recruit_monthly,
            settings.play_product_id_recruit_intensive_90day,
            settings.play_product_id_recruit_6month,
            settings.play_product_id_recruit_annual,
            settings.appstore_product_id_recruit_monthly,
            settings.appstore_product_id_recruit_intensive_90day,
            settings.appstore_product_id_recruit_6month,
            settings.appstore_product_id_recruit_annual,
        )
    return _filled(
        settings.play_product_id_monthly,
        settings.play_product_id_intensive_90day,
        settings.appstore_product_id_monthly,
        settings.appstore_product_id_intensive_90day,
    )


def module_for_stripe_price(settings: Settings, price_id: str) -> Module | None:
    """Which module a Stripe price ID buys. None if blank, unknown, or unconfigured."""
    if not price_id:
        return None
    if price_id in stripe_price_ids_for(settings, "recruit"):
        return "recruit"
    if price_id in stripe_price_ids_for(settings, "promote"):
        return "promote"
    return None


def module_for_store_product(settings: Settings, product_id: str) -> Module | None:
    """Which module a Play / App Store product ID buys. None if blank or unknown."""
    if not product_id:
        return None
    if product_id in store_product_ids_for(settings, "recruit"):
        return "recruit"
    if product_id in store_product_ids_for(settings, "promote"):
        return "promote"
    return None
