"""Header, Account, and Paywall gate checkout per module.

A Recruit subscriber must see Manage billing, not Recruit plan buttons.
A Promote subscriber must see the same for Promote. The other module
may still offer checkout — they are separate products.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "web/src/App.tsx"
ACCOUNT = ROOT / "web/src/ui/Account.tsx"
PAYWALL = ROOT / "web/src/ui/Paywall.tsx"
HELPERS = ROOT / "web/src/lib/moduleAccess.ts"


def test_header_and_account_read_per_module_helpers() -> None:
    app = APP.read_text()
    account = ACCOUNT.read_text()
    helpers = HELPERS.read_text()

    assert "shouldOfferCheckout" in helpers
    assert "anyModuleHasManageableBilling" in helpers
    assert "moduleHasManageableBilling" in helpers
    assert "account.recruit?.entitled" in helpers
    assert "anyModuleHasManageableBilling(account)" in app
    assert "shouldOfferCheckout" in app
    assert "headerSubscribeModule" in app
    assert "alreadyEntitled={!shouldOfferCheckout(account, paywallModule)}" in app
    assert "onSubscribe={(module) =>" in app
    assert "onManageBilling={(module) => void manageBilling(module)}" in app
    assert "moduleHasManageableBilling(account, module)" in account
    assert "See plans" in account
    assert "Manage billing" in account
    assert "Recruit" in account
    assert "Promote" in account


def test_paywall_hides_plan_buttons_when_already_entitled() -> None:
    source = PAYWALL.read_text()
    assert "alreadyEntitled" in source
    assert "You already have access" in source
    assert "Manage billing" in source
    assert "!alreadyEntitled && till === 'stripe'" in source
    assert "!alreadyEntitled && till === 'play'" in source
    assert "chooseStripe" in source
