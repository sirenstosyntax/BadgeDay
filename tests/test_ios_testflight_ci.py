"""TestFlight CI: generate-in-CI, locked bundle id, IAP create held, no secrets."""

from __future__ import annotations

import importlib.util
import json
import plistlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IOS_DIR = ROOT / "mobile/ios"
WORKFLOW = ROOT / ".github/workflows/testflight.yml"
BUILD_SCRIPT = IOS_DIR / "build-ios.sh"
FASTFILE = IOS_DIR / "fastlane/Fastfile"
APPFILE = IOS_DIR / "fastlane/Appfile"
CI_DOC = IOS_DIR / "TESTFLIGHT_CI.md"
PERMISSIONS = IOS_DIR / "INFO_PLIST_PERMISSIONS.md"
GITIGNORE = ROOT / ".gitignore"
PATCHER_PATH = IOS_DIR / "patch_native_ios.py"

BUNDLE_ID = "com.badgeday.app"
TEAM_ID = "G86W79K99V"

REQUIRED_SECRETS = (
    "APP_STORE_CONNECT_API_KEY_ID",
    "APP_STORE_CONNECT_ISSUER_ID",
    "APP_STORE_CONNECT_API_KEY_P8",
    "IOS_DISTRIBUTION_CERTIFICATE_P12_BASE64",
    "IOS_DISTRIBUTION_CERTIFICATE_PASSWORD",
    "IOS_PROVISIONING_PROFILE_BASE64",
)

FORBIDDEN_IAP_CALLS = (
    "upload_to_app_store",
    "create_app_online",
    "Spaceship::ConnectAPI::InAppPurchase",
    "produce(",
    "deliver(",
)


def _patcher():
    spec = importlib.util.spec_from_file_location("patch_native_ios", PATCHER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_workflow_is_macos_and_does_not_submit_on_pr() -> None:
    text = WORKFLOW.read_text()
    assert "macos-latest" in text
    assert "permissions:" in text
    assert "contents: read" in text
    assert "workflow_dispatch" in text
    assert "mobile/ios/build-ios.sh compile" in text
    assert "mobile/ios/build-ios.sh upload" in text
    assert "pull_request_target" not in text
    for name in REQUIRED_SECRETS:
        assert f"secrets.{name}" in text


def _without_comments(text: str) -> str:
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def test_secrets_are_names_only() -> None:
    # Docs may show the PEM header as a format hint. Executable files must not.
    executable = "\n".join(
        path.read_text() for path in (WORKFLOW, BUILD_SCRIPT, FASTFILE, APPFILE)
    )
    assert "-----BEGIN" not in executable
    assert "MIGT" not in executable
    blob = executable + "\n" + CI_DOC.read_text()
    lowered = blob.lower()
    assert "sk_live" not in lowered
    # Team id is public (it is in the live AASA). Key material is not.
    assert TEAM_ID in blob


def test_bundle_id_and_team_are_locked() -> None:
    config = json.loads((IOS_DIR / "capacitor.config.json").read_text())
    assert config["appId"] == BUNDLE_ID
    patcher = _patcher()
    assert patcher.BUNDLE_ID == BUNDLE_ID
    assert patcher.TEAM_ID == TEAM_ID
    fastfile = FASTFILE.read_text()
    appfile = APPFILE.read_text()
    assert f'BUNDLE_ID = "{BUNDLE_ID}"' in fastfile
    assert f'TEAM_ID = "{TEAM_ID}"' in fastfile
    assert f'app_identifier("{BUNDLE_ID}")' in appfile
    assert f'team_id("{TEAM_ID}")' in appfile
    assert "app_store_connect_api_key" in fastfile
    assert "upload_to_testflight" in fastfile
    assert "skip_submission: true" in fastfile


def test_fastlane_does_not_create_iap_products() -> None:
    fastfile = FASTFILE.read_text()
    script = BUILD_SCRIPT.read_text()
    workflow = WORKFLOW.read_text()
    blob = fastfile + script + workflow + CI_DOC.read_text()
    code = _without_comments(fastfile)
    for needle in FORBIDDEN_IAP_CALLS:
        assert needle not in code
    assert "iapProductCreate=held" in script
    assert "IAP product create stays HELD" in blob or "IAP product create stays held" in blob
    assert "APPSTORE_PRODUCT_ID" not in fastfile
    assert "badgeday.promote" not in blob.lower()
    assert "badgeday.recruit" not in blob.lower()


def test_build_script_fails_upload_without_secrets() -> None:
    script = BUILD_SCRIPT.read_text()
    assert "blocked-until-secrets" in script
    assert "Not faking a green upload" in script
    assert "npx cap add ios" in script
    assert "--packagemanager Cocoapods" in script
    assert "npx cap sync ios" in script
    assert "cap add ios" in script
    assert "TWA_KEYSTORE" not in script


def test_native_project_stays_gitignored() -> None:
    text = GITIGNORE.read_text()
    assert "mobile/ios/ios/" in text
    assert "mobile/ios/App/" in text
    assert not (IOS_DIR / "ios" / "App" / "App.xcodeproj").exists()


def test_docs_name_every_secret_and_refuse_a_fake_green_upload() -> None:
    doc = CI_DOC.read_text()
    for name in REQUIRED_SECRETS:
        assert name in doc
    assert "first run" in doc.lower()
    assert "blocked-until-secrets" in doc or "blocked until" in doc.lower()
    assert "do not create iap" in doc.lower() or "iap product create stays held" in doc.lower()
    assert BUNDLE_ID in doc
    assert TEAM_ID in doc


def test_usage_strings_match_permissions_doc() -> None:
    patcher = _patcher()
    permissions = PERMISSIONS.read_text()
    for key, value in patcher.USAGE_STRINGS.items():
        assert key in permissions
        assert value in permissions


def test_patcher_writes_bundle_team_usage_and_associated_domains(tmp_path: Path) -> None:
    patcher = _patcher()
    info = {
        "CFBundleDisplayName": "My App",
        "CFBundleShortVersionString": "$(MARKETING_VERSION)",
        "CFBundleVersion": "$(CURRENT_PROJECT_VERSION)",
    }
    pbx = """// !$*UTF8*$!
{
	objects = {
		T1 /* Debug */ = {
			isa = XCBuildConfiguration;
			buildSettings = {
				ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon;
				CODE_SIGN_STYLE = Automatic;
				CURRENT_PROJECT_VERSION = 1;
				INFOPLIST_FILE = App/Info.plist;
				MARKETING_VERSION = 1.0;
				PRODUCT_BUNDLE_IDENTIFIER = com.getcapacitor.App;
			};
			name = Debug;
		};
		P1 /* Project Debug */ = {
			isa = XCBuildConfiguration;
			buildSettings = {
				SDKROOT = iphoneos;
			};
			name = Debug;
		};
	};
}
"""
    repo = tmp_path / "repo"
    shell = repo / "mobile" / "ios"
    native = shell / "ios" / "App"
    native.mkdir(parents=True)
    (native / "App.xcodeproj").mkdir()
    (native / "App").mkdir()
    with (native / "App" / "Info.plist").open("wb") as fh:
        plistlib.dump(info, fh)
    (native / "App.xcodeproj" / "project.pbxproj").write_text(pbx, encoding="utf-8")
    (shell / "package.json").write_text(
        json.dumps({"name": "badgeday-ios", "version": "1.0.0"}),
        encoding="utf-8",
    )
    icon_dir = repo / "web" / "public" / "icons"
    icon_dir.mkdir(parents=True)
    (icon_dir / "icon-1024.png").write_bytes(b"\x89PNG" + b"\x00" * 64)

    report = patcher.apply(shell, marketing_version="1.0.0", build_number="42")
    assert report["bundleId"] == BUNDLE_ID
    assert report["teamId"] == TEAM_ID
    assert report["buildNumber"] == "42"
    assert report["iapProductCreate"] == "held"

    patched_pbx = (native / "App.xcodeproj" / "project.pbxproj").read_text()
    assert f"PRODUCT_BUNDLE_IDENTIFIER = {BUNDLE_ID};" in patched_pbx
    assert f"DEVELOPMENT_TEAM = {TEAM_ID};" in patched_pbx
    assert "CURRENT_PROJECT_VERSION = 42;" in patched_pbx
    assert "MARKETING_VERSION = 1.0.0;" in patched_pbx
    assert "com.getcapacitor.App" not in patched_pbx
    # Project-level config must not gain a bundle id.
    assert patched_pbx.count("PRODUCT_BUNDLE_IDENTIFIER") == 1

    entitlements = plistlib.loads((native / "App" / "App.entitlements").read_bytes())
    assert entitlements["com.apple.developer.associated-domains"] == [
        "applinks:badgeday.com",
        "webcredentials:badgeday.com",
    ]
    assert all("in-app-purchase" not in key.lower() for key in entitlements)

    plist = plistlib.loads((native / "App" / "Info.plist").read_bytes())
    camera = patcher.USAGE_STRINGS["NSCameraUsageDescription"]
    mic = patcher.USAGE_STRINGS["NSMicrophoneUsageDescription"]
    assert plist["NSCameraUsageDescription"] == camera
    assert plist["NSMicrophoneUsageDescription"] == mic
    assert plist["ITSAppUsesNonExemptEncryption"] is False
    iconset = native / "App" / "Assets.xcassets" / "AppIcon.appiconset"
    assert (iconset / "AppIcon-512@2x.png").is_file()


def test_patcher_rejects_non_numeric_build_numbers() -> None:
    patcher = _patcher()
    try:
        patcher.resolve_build_number("1.0.0+ci")
    except ValueError:
        return
    raise AssertionError("expected non-numeric build numbers to fail")
