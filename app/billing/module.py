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

from app.billing.plan import Plan
from app.config import Settings

Module = Literal["promote", "recruit"]

# Live subscription, or a pass that still grants access. Same gate Stripe
# checkout uses (PR 76) — store purchase must refuse a second charge too.
HELD_SUBSCRIPTION_STATUSES = frozenset({"active", "past_due"})
ALREADY_HELD_MESSAGE = (
    "You already have a plan for this. Manage billing from your account."
)


def is_module_held(*, entitled: bool, subscription_status: str) -> bool:
    """True when this module must not start another charge.

    `entitled` covers an unexpired one-time pass (status stays `none`).
    `active` / `past_due` are a live subscription — including past_due
    with access withheld, which still belongs in the portal, not checkout.
    """
    return entitled or subscription_status in HELD_SUBSCRIPTION_STATUSES


_PLAN_PRICE_ATTR: dict[Plan, str] = {
    "monthly": "stripe_price_id_monthly",
    "intensive_90day": "stripe_price_id_intensive_90day",
    "recruit_monthly": "stripe_price_id_recruit_monthly",
    "recruit_intensive_90day": "stripe_price_id_recruit_intensive_90day",
    "recruit_6month": "stripe_price_id_recruit_6month",
    "recruit_annual": "stripe_price_id_recruit_annual",
}


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


def module_for_plan(plan: Plan) -> Module:
    return "recruit" if plan.startswith("recruit_") else "promote"


def price_id_for_plan(settings: Settings, plan: Plan) -> str:
    """The configured Stripe price for a named plan. Blank means not for sale yet."""
    return getattr(settings, _PLAN_PRICE_ATTR[plan])


def plan_for_stripe_price(settings: Settings, price_id: str) -> Plan | None:
    """Which named plan a Stripe price ID is. None if blank or unknown."""
    if not price_id:
        return None
    for plan, attr in _PLAN_PRICE_ATTR.items():
        if getattr(settings, attr) == price_id:
            return plan
    return None


def pass_days_for_plan(settings: Settings, plan: Plan) -> int | None:
    """How long a one-time pass grants access. None for a subscription."""
    if plan in ("intensive_90day", "recruit_intensive_90day"):
        return settings.intensive_pass_days
    if plan == "recruit_6month":
        return settings.recruit_6month_pass_days
    return None


def pass_days_for_store_product(settings: Settings, product_id: str) -> int | None:
    """How long a one-time store pass grants access. None for a subscription or unknown."""
    if not product_id:
        return None
    ninety = _filled(
        settings.play_product_id_intensive_90day,
        settings.play_product_id_recruit_intensive_90day,
        settings.appstore_product_id_intensive_90day,
        settings.appstore_product_id_recruit_intensive_90day,
    )
    six = _filled(
        settings.play_product_id_recruit_6month,
        settings.appstore_product_id_recruit_6month,
    )
    if product_id in ninety:
        return settings.intensive_pass_days
    if product_id in six:
        return settings.recruit_6month_pass_days
    return None
