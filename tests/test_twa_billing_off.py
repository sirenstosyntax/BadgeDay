"""Play Billing stays off on the TWA until a later order names products."""

import json
from pathlib import Path


def test_play_billing_is_off() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "mobile/android/twa-manifest.json").read_text())
    assert manifest["packageId"] == "com.badgeday.app"
    assert manifest["features"]["playBilling"]["enabled"] is False
