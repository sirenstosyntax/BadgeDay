"""Play TWA wrapper: package id locked, billing on, no invented SKU."""

import importlib.util
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


def _twa_gradle():
    path = ROOT / "mobile/android/twa_gradle.py"
    spec = importlib.util.spec_from_file_location("twa_gradle", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    helper = (ROOT / "mobile/android/twa_gradle.py").read_text()
    # The four signing values are env reads, not literals.
    reads_env = (
        "storePassword System.getenv" in helper
        or 'os.environ["TWA_KEYSTORE_PASSWORD"]' in helper
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


_MINIMAL_ANDROID = """
android {
    compileSdk 36
    defaultConfig {
        applicationId "com.badgeday.app"
    }
    buildTypes {
        release {
            minifyEnabled false
        }
    }
}
"""


def test_signing_config_attaches_under_build_types_release_not_signing_configs() -> None:
    """A first-match replace of `release {` hits signingConfigs.release and never signs."""
    gradle = _twa_gradle()
    out = gradle.apply_release_signing(_MINIMAL_ANDROID, "/tmp/upload.keystore")
    assert gradle.signing_config_is_under_build_types_release(out)
    assert not gradle.signing_config_is_inside_signing_configs_release(out)
    assert out.count("signingConfig signingConfigs.release") == 1
    assert "storeFile file(" in out and "/tmp/upload.keystore" in out
    # Second pass must not duplicate the attach or move it.
    again = gradle.apply_release_signing(out, "/tmp/upload.keystore")
    assert gradle.signing_config_is_under_build_types_release(again)
    assert not gradle.signing_config_is_inside_signing_configs_release(again)
    assert again.count("signingConfig signingConfigs.release") == 1


def test_billing_pin_rejects_an_unpinned_or_old_helper() -> None:
    """Fail closed: any androidbrowserhelper:billing is not enough."""
    gradle = _twa_gradle()
    helper = gradle.PINNED_BILLING_HELPER
    base = 'applicationId "com.badgeday.app"\n'
    assert gradle.billing_pin_errors(base + helper) == []
    assert (
        gradle.billing_pin_errors(base + "com.android.billingclient:billing:8.3.0") == []
    )
    assert (
        gradle.billing_pin_errors(base + "com.android.billingclient:billing:8.4.1") == []
    )
    assert gradle.billing_pin_errors(base + "com.android.billingclient:billing:8.2.0")
    assert gradle.billing_pin_errors(
        base + "com.google.androidbrowserhelper:billing:1.1.0"
    )
    assert gradle.billing_pin_errors(base + "androidbrowserhelper:billing")
    assert gradle.billing_pin_errors(base)


def test_frontend_play_billing_has_no_hardcoded_product_or_price() -> None:
    """Grant has not named the paid offer. The client must not invent one."""
    source = PLAY_BILLING_TS.read_text() + "\n" + PAYWALL.read_text()
    lowered = source.lower()
    for needle in ("$29", "$129", "29.00", "129.00", "android.test.purchased"):
        assert needle not in source
    assert "badgeday." not in lowered
    assert "sku_monthly" not in lowered
    assert "play_product_id" not in lowered
