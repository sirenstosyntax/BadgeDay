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
REWRITE_P12 = IOS_DIR / "rewrite_p12_for_macos.py"
IMPORT_P12 = IOS_DIR / "import_p12.swift"
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
        path.read_text()
        for path in (WORKFLOW, BUILD_SCRIPT, FASTFILE, APPFILE, REWRITE_P12, IMPORT_P12)
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
    blob = fastfile + script + workflow + CI_DOC.read_text() + IMPORT_P12.read_text()
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


def test_fastfile_workspace_path_resolves_from_fastfile_dir() -> None:
    # Mirror cocoapods_workspace_path: File.expand_path("../#{WORKSPACE}", __dir__)
    # so gym cannot miss the workspace the way a Dir.pwd-relative check did.
    fastfile_dir = IOS_DIR / "fastlane"
    expected = (IOS_DIR / "ios" / "App" / "App.xcworkspace").resolve()
    resolved = (fastfile_dir / ".." / "ios/App/App.xcworkspace").resolve()
    assert resolved == expected
    assert resolved.name == "App.xcworkspace"
    assert "App.xcodeproj" not in str(resolved)


def test_fastfile_archives_cocoapods_workspace_not_xcodeproj() -> None:
    fastfile = FASTFILE.read_text()
    code = _without_comments(fastfile)
    assert 'WORKSPACE = "ios/App/App.xcworkspace"' in fastfile
    assert "require_cocoapods_workspace!" in fastfile
    assert "cocoapods_workspace_path" in fastfile
    assert "File.expand_path" in fastfile
    assert "__dir__" in fastfile
    assert "workspace: require_cocoapods_workspace!" in code
    assert "import Capacitor" in fastfile
    assert "34906234215" in fastfile
    # Relative Dir.pwd check + project fallback archived 1 target (no Pods).
    assert "xcode_input" not in code
    assert "**xcode_input" not in code
    assert '{ project: PROJECT }' not in code
    assert "Do not fall back to the xcodeproj" in fastfile
    # Signing still edits the app project; gym must not archive it.
    assert "increment_build_number(xcodeproj: PROJECT" in code
    assert "path: PROJECT" in code


def test_build_script_requires_cocoapods_workspace() -> None:
    script = BUILD_SCRIPT.read_text()
    assert "require_cocoapods_workspace" in script
    assert "cocoapods_workspace_ready" in script
    assert "npx cap sync ios" in script
    assert "npx cap sync ios --packagemanager" not in script
    assert "cap add ios --packagemanager Cocoapods" in script
    assert "-workspace \"$workspace\"" in script
    assert "run 34906234215" in script
    assert "Podfile missing after cap add/sync" in script
    # Compile and archive must not silently use App.xcodeproj.
    assert 'xcode_src=(-project "$project")' not in script
    assert 'else\n    xcode_src=(-project' not in script


def test_cocoapods_workspace_gate_rejects_xcodeproj_only(tmp_path: Path) -> None:
    import subprocess

    script = BUILD_SCRIPT.read_text()
    start = script.index("cocoapods_workspace_ready()")
    end = script.index("\ncompile_simulator()")
    helper = tmp_path / "workspace-gate.sh"
    helper.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        + script[start:end]
        + 'require_cocoapods_workspace "$1"\n',
        encoding="utf-8",
    )
    helper.chmod(0o700)

    def check(path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(helper), str(path)],
            check=False,
            capture_output=True,
            text=True,
        )

    missing = tmp_path / "App.xcworkspace"
    missing.mkdir()
    (missing / "App.xcodeproj").mkdir()
    rejected = check(missing)
    assert rejected.returncode == 1
    assert "import Capacitor unresolved" in rejected.stderr
    assert "34906234215" in rejected.stderr

    ready = tmp_path / "ready" / "App.xcworkspace"
    ready.mkdir(parents=True)
    (ready / "contents.xcworkspacedata").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n',
        encoding="utf-8",
    )
    accepted = check(ready)
    assert accepted.returncode == 0, accepted.stderr
    assert "Capacitor via Pods" in accepted.stdout


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


def _ruby_method(text: str, name: str) -> str:
    start = text.index(f"def {name}")
    collected: list[str] = []
    for line in text[start:].splitlines():
        if collected and line.startswith("def "):
            break
        collected.append(line)
    return "\n".join(collected)


def test_fastfile_imports_p12_into_setup_ci_keychain() -> None:
    fastfile = FASTFILE.read_text()
    code = _without_comments(fastfile)
    assert "prepare_signing_keychain!" in fastfile
    assert "import_distribution_certificate!" in fastfile
    assert "import_p12_fail_closed!" in fastfile
    assert "assert_codesigning_identity!" in fastfile
    assert "MATCH_KEYCHAIN_NAME" in fastfile
    assert "MATCH_KEYCHAIN_PASSWORD" in fastfile
    assert "unlock_keychain" in code
    assert "keychain_path" in code
    assert "find-identity -v -p codesigning" in fastfile
    assert "Apple Distribution" in fastfile
    assert "SecKeychainItemImport" in fastfile
    assert "MAC verification" in fastfile
    assert "get_provisioning_profile / " in fastfile or "get_provisioning_profile /" in fastfile
    # Fail-closed import, then import_certificate, then identity,
    # then sigh — not a bare ENV lookup that can be empty.
    setup_idx = code.index("setup_ci(")
    probe_idx = code.index("import_p12_fail_closed!(")
    import_idx = code.index("import_certificate(")
    identity_idx = code.index("find-identity")
    sigh_idx = code.index("get_provisioning_profile(")
    assert setup_idx < probe_idx < import_idx < identity_idx < sigh_idx
    assert "keychain_name: ENV[\"MATCH_KEYCHAIN_NAME\"]" not in code
    # Apple security import's only non-GUI passphrase option is -P on argv.
    # The fail-closed probe must not put the wrapping password there.
    probe = _ruby_method(fastfile, "import_p12_fail_closed!")
    probe_code = _without_comments(probe)
    assert "import_p12.swift" in probe
    assert "stdin_data: password" in probe
    assert '"-P"' not in probe_code
    assert "'-P'" not in probe_code
    assert '"security", "import"' not in probe_code
    assert IMPORT_P12.is_file()


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
    assert "App.xcworkspace" in doc
    assert "34906234215" in doc
    assert "import Capacitor" in doc
    assert "MATCH_KEYCHAIN_NAME" in doc
    assert "PBE-SHA1-3DES" in doc
    assert "-macalg SHA1" in doc
    assert "MAC verification" in doc
    assert "setup_ci" in doc
    assert "primary" in doc.lower()
    assert "follow-on" in doc.lower()
    assert "SecKeychainItemImport" in doc
    assert "does **not** continue to `get_provisioning_profile`" in doc
    assert "Apple `security`" in doc or "Apple security" in doc
    assert "-legacy" in doc
    assert "no stdin / fd / env passphrase" in doc.lower() or "stdin / fd / env" in doc
    assert "import_p12.swift" in doc
    assert "OpenSSL-3-default fallback" in doc


def _load_rewrite_module():
    spec = importlib.util.spec_from_file_location("rewrite_p12_for_macos", REWRITE_P12)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_script_rewrites_p12_for_macos() -> None:
    script = BUILD_SCRIPT.read_text()
    assert "rewrite_p12_for_macos.py" in script
    assert "distribution-macos.p12" in script
    assert REWRITE_P12.is_file()
    text = REWRITE_P12.read_text()
    assert "PBE-SHA1-3DES" in text
    assert "SHA1" in text
    assert "IOS_DISTRIBUTION_CERTIFICATE_PASSWORD" in text
    assert "get_certificates" not in text
    assert "-legacy" in text
    assert "compatible=False" not in text
    assert "compatible=True" not in text
    module = _load_rewrite_module()
    assert module.DECRYPT_PKCS12_EXTRA_FLAGS == ((), ("-legacy",))


def test_import_p12_helper_reads_password_from_stdin() -> None:
    text = IMPORT_P12.read_text()
    assert "SecPKCS12Import" in text
    assert "kSecImportExportPassphrase" in text
    assert "FileHandle.standardInput" in text
    assert "CommandLine.arguments" in text
    assert "get_certificates" not in text
    assert "APPSTORE_PRODUCT_ID" not in text
    # Password is stdin, not argv and not the child environment.
    assert "ProcessInfo.processInfo.environment" not in text
    assert "IOS_DISTRIBUTION_CERTIFICATE_PASSWORD" not in text


def _make_self_signed_pair(tmp_path: Path, openssl: str) -> tuple[Path, Path]:
    import subprocess

    key = tmp_path / "key.pem"
    cert = tmp_path / "cert.pem"
    subprocess.run(
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "1",
            "-nodes",
            "-subj",
            "/CN=BadgeDay P12 rewrite test",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return key, cert


def _export_p12_bag(
    openssl: str,
    key: Path,
    cert: Path,
    dest: Path,
    password: str,
    *,
    apple_pbe: bool,
) -> bool:
    import subprocess

    args = [
        openssl,
        "pkcs12",
        "-export",
        "-inkey",
        str(key),
        "-in",
        str(cert),
        "-out",
        str(dest),
        "-passout",
        f"pass:{password}",
    ]
    if apple_pbe:
        args.extend(
            [
                "-keypbe",
                "PBE-SHA1-3DES",
                "-certpbe",
                "PBE-SHA1-3DES",
                "-macalg",
                "SHA1",
            ]
        )
    exported = subprocess.run(args, check=False, capture_output=True, text=True)
    return exported.returncode == 0 and dest.is_file() and dest.stat().st_size >= 32


def test_rewrite_p12_for_macos_round_trips_openssl3_bag(tmp_path: Path) -> None:
    import os
    import shutil
    import subprocess

    openssl = shutil.which("openssl")
    if openssl is None:
        import pytest

        pytest.skip("openssl not available")

    key, cert = _make_self_signed_pair(tmp_path, openssl)
    modern = tmp_path / "modern.p12"
    rewritten = tmp_path / "macos.p12"
    password = "test-p12-password-not-a-secret"
    if not _export_p12_bag(openssl, key, cert, modern, password, apple_pbe=False):
        import pytest

        pytest.skip("openssl pkcs12 -export unavailable")

    module = _load_rewrite_module()
    os.environ["IOS_DISTRIBUTION_CERTIFICATE_PASSWORD"] = password
    try:
        message = module.rewrite(modern, rewritten, password)
    finally:
        os.environ.pop("IOS_DISTRIBUTION_CERTIFICATE_PASSWORD", None)
    assert rewritten.is_file()
    assert rewritten.stat().st_size >= 32
    assert "macOS-compatible" in message
    check = subprocess.run(
        [
            openssl,
            "pkcs12",
            "-in",
            str(rewritten),
            "-passin",
            f"pass:{password}",
            "-nokeys",
            "-noout",
            "-legacy",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, check.stderr

    try:
        module.rewrite(modern, tmp_path / "wrong.p12", "not-the-password")
    except SystemExit as exc:
        assert "cannot decrypt" in str(exc)
    else:
        raise AssertionError("expected wrong password to fail closed")


def test_rewrite_p12_decrypts_sha1_3des_bag_via_legacy(tmp_path: Path) -> None:
    import os
    import shutil

    openssl = shutil.which("openssl")
    if openssl is None:
        import pytest

        pytest.skip("openssl not available")

    key, cert = _make_self_signed_pair(tmp_path, openssl)
    legacy = tmp_path / "sha1-3des.p12"
    rewritten = tmp_path / "macos.p12"
    password = "test-p12-password-not-a-secret"
    if not _export_p12_bag(openssl, key, cert, legacy, password, apple_pbe=True):
        import pytest

        pytest.skip("openssl pkcs12 SHA1-3DES export unavailable")

    module = _load_rewrite_module()
    os.environ["IOS_DISTRIBUTION_CERTIFICATE_PASSWORD"] = password
    try:
        message = module.rewrite(legacy, rewritten, password)
    finally:
        os.environ.pop("IOS_DISTRIBUTION_CERTIFICATE_PASSWORD", None)
    assert rewritten.is_file()
    assert rewritten.stat().st_size >= 32
    assert "macOS-compatible" in message


def test_decrypt_p12_retries_legacy_before_fail_closed(tmp_path: Path) -> None:
    import subprocess

    module = _load_rewrite_module()
    calls: list[list[str]] = []

    def fake_run(openssl: str, args, env):
        recorded = list(args)
        calls.append(recorded)
        if "-legacy" in recorded:
            return subprocess.CompletedProcess([openssl, *recorded], 0, "", "")
        return subprocess.CompletedProcess(
            [openssl, *recorded], 1, "", "legacy provider required"
        )

    module._run = fake_run
    result = module.decrypt_p12("openssl", tmp_path / "in.p12", tmp_path / "out.pem", {})
    assert result.returncode == 0
    assert len(calls) == 2
    assert "-legacy" not in calls[0]
    assert "-legacy" in calls[1]


def test_decrypt_p12_fail_closes_after_both_attempts(tmp_path: Path) -> None:
    import subprocess

    module = _load_rewrite_module()
    calls: list[list[str]] = []

    def fake_run(openssl: str, args, env):
        recorded = list(args)
        calls.append(recorded)
        return subprocess.CompletedProcess([openssl, *recorded], 1, "", "mac verify failure")

    module._run = fake_run
    result = module.decrypt_p12("openssl", tmp_path / "in.p12", tmp_path / "out.pem", {})
    assert result.returncode == 1
    assert [("-legacy" in call) for call in calls] == [False, True]


def test_rewrite_fail_closes_when_sha1_3des_export_fails(tmp_path: Path) -> None:
    import subprocess

    module = _load_rewrite_module()
    src = tmp_path / "src.p12"
    src.write_bytes(b"\x00" * 64)
    exports: list[list[str]] = []

    def fake_run(openssl: str, args, env):
        recorded = list(args)
        if "-export" in recorded:
            exports.append(recorded)
            return subprocess.CompletedProcess(
                [openssl, *recorded], 1, "", "SHA1-3DES export refused"
            )
        pem = Path(recorded[recorded.index("-out") + 1])
        pem.write_text("-----BEGIN PRIVATE KEY-----\n-----END PRIVATE KEY-----\n")
        return subprocess.CompletedProcess([openssl, *recorded], 0, "", "")

    module._run = fake_run
    module.openssl_binaries = lambda: ["/usr/bin/openssl"]
    try:
        module.rewrite(src, tmp_path / "dest.p12", "test-p12-password-not-a-secret")
    except SystemExit as exc:
        assert "cannot decrypt" in str(exc)
        assert "SHA1-3DES" in str(exc)
    else:
        raise AssertionError("expected SHA1-3DES export failure to fail closed")
    assert exports
    for call in exports:
        assert "PBE-SHA1-3DES" in call
        assert "SHA1" in call
    assert not (tmp_path / "dest.p12").exists()


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
