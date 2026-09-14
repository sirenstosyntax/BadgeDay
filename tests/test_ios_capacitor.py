"""BD-iOS-4.2: Capacitor native capabilities are landed in-repo, not a second app."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IOS_PKG = ROOT / "mobile/ios/package.json"
IOS_LOCK = ROOT / "mobile/ios/package-lock.json"
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
    lock = json.loads(IOS_LOCK.read_text())
    packages = lock.get("packages", {})
    for plugin in (
        "@capacitor/camera",
        "@capacitor/filesystem",
        "@capacitor/local-notifications",
        "@capawesome/capacitor-file-picker",
        "@capgo/native-purchases",
    ):
        assert plugin in pkg["dependencies"]
        assert f"node_modules/{plugin}" in packages


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
    documents = DOCUMENTS.read_text()
    assert "NSCameraUsageDescription" in text
    assert "NSPhotoLibraryUsageDescription" in text
    assert "NSMicrophoneUsageDescription" in text
    assert "reading list" in text.lower()
    assert "oral-board" in text.lower() or "oral board" in text.lower()
    assert "does not read your photo library" in text.lower()
    assert "camera only" in text.lower()
    assert "Scan page" in documents
    assert "source: 'CAMERA'" in (ROOT / "web/src/lib/nativeUpload.ts").read_text()
    assert "source: 'PHOTOS'" not in (ROOT / "web/src/lib/nativeUpload.ts").read_text()
    assert "reads a photo you choose" not in text.lower()


def test_offline_sync_and_recache_avoid_orphans() -> None:
    app = APP.read_text()
    practice = (ROOT / "web/src/lib/offlinePractice.ts").read_text()
    assert "pendingSyncFailure" in app
    assert "already_answered" in practice
    assert "resolveOfflinePack" in app
    assert "reusableOfflineSessionId" in practice


def test_bd_ios_42_spec_declares_landed_storekit_plugin() -> None:
    spec = (ROOT / "specs/badgeday/BD-iOS-4.2-capacitor-native-capabilities.md").read_text()
    assert "@capgo/native-purchases" in spec
    assert "StoreKit bridge **is declared** as `@capgo/native-purchases` (PR 79)" in spec
    assert "Still wire purchases → `POST /billing/store/appstore/purchase`" in spec
    assert "StoreKit bridge dependency is **not** yet declared" not in spec
    assert "add whatever Gyro chooses" not in spec
    assert "StoreKit Capacitor plugin (or equivalent)" not in spec
    assert "IAP product create remains **HELD**" in spec
    assert "Do not invent `APPSTORE_PRODUCT_ID_*`" in spec


def test_docs_mark_capabilities_landed_and_testflight_ci_ready() -> None:
    readme = README.read_text()
    plan = PLAN.read_text()
    ci_doc = ROOT / "mobile/ios/TESTFLIGHT_CI.md"
    assert ci_doc.is_file()
    assert "None of these are implemented yet" not in readme
    assert "Landed" in readme
    assert "TestFlight" in readme
    assert "TESTFLIGHT_CI.md" in readme
    assert "does not claim a successful TestFlight upload" in readme
    assert "BD-iOS-4.2" in plan
    assert "Code-landed" in plan
    assert "macos-latest" in plan
    assert "TESTFLIGHT_CI.md" in plan
    assert "package-lock.json" in readme
    assert "npm ci" in readme
