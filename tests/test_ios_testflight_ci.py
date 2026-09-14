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
    assert "failed before writing the Xcode project" in script
    assert "15.0" in script
    assert "cap add ios" in script
    assert "TWA_KEYSTORE" not in script
    assert "signed archive/upload fail closed" in script
    assert "Will not mint a distribution cert" in script


def test_fastfile_fails_closed_without_p12() -> None:
    fastfile = FASTFILE.read_text()
    code = _without_comments(fastfile)
    assert "require_p12!" in fastfile
    assert "fail closed" in fastfile.lower()
    assert "import_certificate" in fastfile
    # Must not mint a cert on an ephemeral runner. The name may appear in
    # the fail-closed error string; a call site must not.
    assert "get_certificates(" not in code
    assert "get_certificates(" not in fastfile


def test_cap_add_failure_is_gated_on_deployment_target_refusal() -> None:
    script = BUILD_SCRIPT.read_text()
    assert "cap_add_failure_is_expected_pod_refusal" in script
    assert "CapgoNativePurchases" in script
    assert "higher minimum deployment target" in script
    assert "Not treating pbxproj presence as success" in script
    assert "grep -qiE 'CapgoNativePurchases'" in script
    assert "higher minimum deployment target|deployment.target" in script


def test_cap_add_gate_accepts_only_capgo_deployment_target_refusal(
    tmp_path: Path,
) -> None:
    import subprocess

    script = BUILD_SCRIPT.read_text()
    start = script.index("cap_add_failure_is_expected_pod_refusal()")
    end = script.index("\nadd_native_project()")
    helper = tmp_path / "gate.sh"
    helper.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        + script[start:end]
        + 'cap_add_failure_is_expected_pod_refusal "$1"\n',
        encoding="utf-8",
    )
    helper.chmod(0o700)

    def classify(text: str) -> bool:
        log = tmp_path / "cap-add.log"
        log.write_text(text, encoding="utf-8")
        result = subprocess.run(
            ["bash", str(helper), str(log)],
            check=False,
        )
        return result.returncode == 0

    expected = (
        "[!] CocoaPods could not find compatible versions for pod "
        '"CapgoNativePurchases":\n'
        "Specs satisfying the dependency were found, but they required "
        "a higher minimum deployment target.\n"
    )
    assert classify(expected)
    assert not classify("error: network timeout while fetching pods\n")
    assert not classify("CapgoNativePurchases built successfully\n")
    assert not classify("required a higher minimum deployment target\n")
    assert not classify("project.pbxproj written\n")


def test_cocoapods_cache_key_includes_deployment_target() -> None:
    text = WORKFLOW.read_text()
    patcher = _patcher()
    token = f"ios{patcher.IOS_DEPLOYMENT_TARGET}"
    assert token == "ios15.0"
    assert token in text
    assert "cocoapods-specs-" in text
    assert "hashFiles('mobile/ios/package-lock.json')" in text
    assert "Podfile.lock is created after generate-in-CI" in text
    assert "path: ~/Library/Caches/CocoaPods" in text
    # Must not key CocoaPods on package-lock alone.
    assert (
        "cocoapods-${{ runner.os }}-${{ hashFiles('mobile/ios/package-lock.json') }}"
        not in text
    )
    doc = CI_DOC.read_text()
    assert token in doc
    assert "IOS_DEPLOYMENT_TARGET" in doc
    assert "ios platform already exists" in doc


def test_build_script_removes_stale_ios_without_pbxproj() -> None:
    script = BUILD_SCRIPT.read_text()
    assert "Removing stale ios/" in script
    assert "rm -rf ios" in script
    assert "no project.pbxproj" in script


def test_fastlane_gemfile_lock_is_committed() -> None:
    gemfile = (IOS_DIR / "Gemfile").read_text()
    lock = IOS_DIR / "Gemfile.lock"
    assert 'gem "fastlane", "~> 2.228"' in gemfile
    assert lock.is_file()
    lock_text = lock.read_text()
    assert "fastlane (2." in lock_text
    assert "fastlane (~> 2.228)" in lock_text
    assert "BUNDLED WITH" in lock_text
    assert "ruby" in lock_text
    assert "arm64-darwin" in lock_text


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
    assert "fail closed" in doc.lower()
    assert "There is **no** `get_certificates` bootstrap" in doc
    assert "@capgo/native-purchases" in doc


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
				IPHONEOS_DEPLOYMENT_TARGET = 14.0;
				MARKETING_VERSION = 1.0;
				PRODUCT_BUNDLE_IDENTIFIER = com.getcapacitor.App;
			};
			name = Debug;
		};
		P1 /* Project Debug */ = {
			isa = XCBuildConfiguration;
			buildSettings = {
				IPHONEOS_DEPLOYMENT_TARGET = 14.0;
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
    (native / "Podfile").write_text("platform :ios, '14.0'\nuse_frameworks!\n", encoding="utf-8")
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
    assert "IPHONEOS_DEPLOYMENT_TARGET = 15.0;" in patched_pbx
    assert "IPHONEOS_DEPLOYMENT_TARGET = 14.0;" not in patched_pbx
    assert "platform :ios, '15.0'" in (native / "Podfile").read_text()
    assert "platform :ios, '14.0'" not in (native / "Podfile").read_text()
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


def test_patch_podfile_raises_capacitor_template() -> None:
    patcher = _patcher()
    out = patcher.patch_podfile("platform :ios, '14.0'\nuse_frameworks!\n")
    assert "platform :ios, '15.0'" in out
    assert "14.0" not in out


def test_patcher_rejects_non_numeric_build_numbers() -> None:
    patcher = _patcher()
    try:
        patcher.resolve_build_number("1.0.0+ci")
    except ValueError:
        return
    raise AssertionError("expected non-numeric build numbers to fail")
