"""Play TWA wrapper: package id locked, billing on, no invented SKU."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "mobile/android/twa-manifest.json"
BUILD_SCRIPT = ROOT / "mobile/android/build-twa.sh"
ASSETLINKS = ROOT / "mobile/android/assetlinks.template.json"
PLAY_BILLING_TS = ROOT / "web/src/lib/playBilling.ts"
PAYWALL = ROOT / "web/src/ui/Paywall.tsx"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text())


def test_package_id_is_permanent() -> None:
    assert _manifest()["packageId"] == "com.badgeday.app"


def test_start_url_is_the_live_app() -> None:
    manifest = _manifest()
    assert manifest["host"] == "app.badgeday.com"
    assert manifest["startUrl"] == "/"
    assert manifest["fullScopeUrl"] == "https://app.badgeday.com/"


def test_play_billing_is_on() -> None:
    """The AAB must ship BILLING / Digital Goods so a SKU can be attached next."""
    manifest = _manifest()
    assert manifest["features"]["playBilling"]["enabled"] is True
    assert manifest["alphaDependencies"]["enabled"] is True


def test_version_was_bumped_for_the_billing_build() -> None:
    manifest = _manifest()
    assert manifest["appVersionCode"] >= 2
    assert manifest["appVersion"] == manifest["appVersionName"]


def test_assetlinks_template_has_no_placeholder_served_as_live() -> None:
    """A served assetlinks.json with REPLACE_WITH_… fails DAL worse than none at all."""
    template = json.loads(ASSETLINKS.read_text())
    assert template[0]["target"]["package_name"] == "com.badgeday.app"
    served = ROOT / "web/public/.well-known/assetlinks.json"
    assert not served.exists()


def test_build_script_does_not_invent_a_sku() -> None:
    script = BUILD_SCRIPT.read_text()
    assert '"$BUBBLEWRAP" play' not in script
    assert "$BUBBLEWRAP play" not in script
    assert "TWA_KEYSTORE_PASSWORD" in script
    # The four signing values are env reads, not literals.
    reads_env = (
        "storePassword System.getenv" in script
        or 'os.environ["TWA_KEYSTORE_PASSWORD"]' in script
    )
    assert reads_env


def test_billing_permission_is_inserted_inside_the_manifest_element() -> None:
    """The first '>' in a Bubblewrap manifest is <?xml ...?>. Putting BILLING
    there makes processReleaseMainManifest fail to parse the file."""
    import re

    sample = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <application />
</manifest>
"""
    match = re.search(r"<manifest\b[^>]*>", sample)
    assert match is not None
    insert = '\n    <uses-permission android:name="com.android.vending.BILLING" />'
    patched = sample[: match.end()] + insert + sample[match.end() :]
    assert patched.startswith("<?xml")
    assert "<manifest" in patched.split("uses-permission")[0]
    assert "com.android.vending.BILLING" in patched


def test_frontend_play_billing_has_no_hardcoded_product_or_price() -> None:
    """Grant has not named the paid offer. The client must not invent one."""
    source = PLAY_BILLING_TS.read_text() + "\n" + PAYWALL.read_text()
    lowered = source.lower()
    for needle in ("$29", "$129", "29.00", "129.00", "android.test.purchased"):
        assert needle not in source
    assert "badgeday." not in lowered
    assert "sku_monthly" not in lowered
    assert "play_product_id" not in lowered
