"""BD-iOS-4.2: Capacitor native capabilities are landed in-repo, not a second app."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IOS_PKG = ROOT / "mobile/ios/package.json"
IOS_CONFIG = ROOT / "mobile/ios/capacitor.config.json"
README = ROOT / "mobile/README.md"
PLAN = ROOT / "mobile_release_plan.md"
PAYWALL = ROOT / "web/src/ui/Paywall.tsx"
APP = ROOT / "web/src/App.tsx"
DOCUMENTS = ROOT / "web/src/ui/Documents.tsx"
RECRUIT = ROOT / "web/src/ui/Recruit.tsx"
STOREKIT = ROOT / "web/src/lib/storeKitBilling.ts"
API = ROOT / "web/src/lib/api.ts"
PERMISSIONS = ROOT / "mobile/ios/INFO_PLIST_PERMISSIONS.md"


def test_capacitor_shell_is_still_the_remote_web_app() -> None:
    config = json.loads(IOS_CONFIG.read_text())
    assert config["appId"] == "com.badgeday.app"
    assert config["server"]["url"] == "https://app.badgeday.com"
    pkg = json.loads(IOS_PKG.read_text())
    for plugin in (
        "@capacitor/camera",
        "@capacitor/filesystem",
        "@capacitor/local-notifications",
        "@capawesome/capacitor-file-picker",
        "@capgo/native-purchases",
    ):
        assert plugin in pkg["dependencies"]


def test_native_entry_points_are_gated_on_the_ios_shell() -> None:
    documents = DOCUMENTS.read_text()
    paywall = PAYWALL.read_text()
    app = APP.read_text()
    assert "detectIosCapacitorShell" in app
    assert "iosShell" in documents
    assert "Files / iCloud" in documents
    assert "Scan page" in documents
    assert "detectIosCapacitorShell" in paywall
    assert "chooseStripe" in paywall
    assert "selectPaywallTill" in paywall


def test_storekit_reports_the_existing_appstore_purchase_body() -> None:
    api = API.read_text()
    store = STOREKIT.read_text()
    assert "/billing/store/appstore/purchase" in api
    assert "transaction_id" in api
    assert "reportAppStorePurchase" in api
    assert "transactionId" in store
    assert "APPSTORE_PRODUCT_ID" not in store
    assert "badgeday.promote" not in store
    assert "badgeday.recruit" not in store


def test_paywall_does_not_hardcode_store_prices() -> None:
    blob = PAYWALL.read_text() + STOREKIT.read_text()
    for needle in ("$29", "$129", "$24.99", "$59", "$119", "$179"):
        assert needle not in blob


def test_recruit_blocks_offline_without_a_spinner_forever() -> None:
    source = RECRUIT.read_text()
    assert "needs a connection" in source.lower() or "Needs a connection" in source
    assert "Oral board needs a connection" in source


def test_privacy_strings_are_documented_for_mac_sync() -> None:
    text = PERMISSIONS.read_text()
    assert "NSCameraUsageDescription" in text
    assert "NSPhotoLibraryUsageDescription" in text
    assert "NSMicrophoneUsageDescription" in text
    assert "reading list" in text.lower()
    assert "oral-board" in text.lower() or "oral board" in text.lower()


def test_docs_mark_capabilities_landed_without_claiming_testflight() -> None:
    readme = README.read_text()
    plan = PLAN.read_text()
    assert "None of these are implemented yet" not in readme
    assert "Landed" in readme
    assert "TestFlight" in readme
    assert "does not claim TestFlight" in readme or "not claim TestFlight" in readme
    assert "BD-iOS-4.2" in plan
    assert "Code-landed" in plan
    assert "Still needs a Mac" in plan
