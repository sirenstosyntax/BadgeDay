"""The Recruit paywall names four offers and does not print Grant's amounts."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAYWALL = ROOT / "web/src/ui/Paywall.tsx"
TYPES = ROOT / "web/src/lib/types.ts"
ACCOUNT = ROOT / "app/api/account.py"
RECRUIT_UI = ROOT / "web/src/ui/Recruit.tsx"


def test_paywall_lists_the_four_recruit_offers() -> None:
    source = PAYWALL.read_text()
    assert "recruit_monthly" in source
    assert "recruit_intensive_90day" in source
    assert "recruit_6month" in source
    assert "recruit_annual" in source
    assert "90-day pass" in source
    assert "6-month pass" in source
    assert "Keep practicing the oral board" in source


def test_paywall_does_not_hardcode_held_amounts() -> None:
    blob = PAYWALL.read_text() + TYPES.read_text()
    for needle in ("24.99", "24,99", "$59", "$119", "$179", "59.99", "119.99", "179.99"):
        assert needle not in blob


def test_a_402_on_the_oral_board_opens_the_recruit_paywall() -> None:
    source = RECRUIT_UI.read_text()
    assert "caught.status === 402" in source
    assert "onNeedsAccess" in source
    assert "See plans" in source


def test_account_exposes_recruit_play_product_ids() -> None:
    source = ACCOUNT.read_text()
    assert "play_product_id_recruit_monthly" in source
    assert "play_product_id_recruit_intensive_90day" in source
    assert "play_product_id_recruit_6month" in source
    assert "play_product_id_recruit_annual" in source
