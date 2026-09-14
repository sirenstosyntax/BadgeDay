"""Patch the generated Capacitor iOS project after `npx cap add/sync ios`.

The Xcode tree is gitignored and recreated on the macOS runner. This file is
the committed source of truth for bundle id, team, usage strings, associated
domains, and the store icon. It does not create App Store Connect IAP products
and does not write signing secrets.
"""

from __future__ import annotations

import argparse
import json
import plistlib
import re
import shutil
import sys
from pathlib import Path

BUNDLE_ID = "com.badgeday.app"
TEAM_ID = "G86W79K99V"
DISPLAY_NAME = "BadgeDay"
ENTITLEMENTS_BUILD_PATH = "App/App.entitlements"
ASSOCIATED_DOMAINS = (
    "applinks:badgeday.com",
    "webcredentials:badgeday.com",
)
# Exact strings from INFO_PLIST_PERMISSIONS.md. Do not invent department names.
USAGE_STRINGS = {
    "NSCameraUsageDescription": (
        "BadgeDay uses the camera so you can photograph a page from your "
        "promotional reading list and upload it for cited practice questions."
    ),
    "NSPhotoLibraryUsageDescription": (
        "BadgeDay does not read your photo library. Scan page uses the camera "
        "only. This string exists only if the camera plugin requires the key."
    ),
    "NSPhotoLibraryAddUsageDescription": (
        "BadgeDay does not save photos to your library. This string exists "
        "only if a plugin requires the key."
    ),
    "NSMicrophoneUsageDescription": (
        "BadgeDay records your spoken oral-board answer so it can be "
        "transcribed and critiqued. Recordings are discarded unless you keep "
        "them for self-review."
    ),
}

_TARGET_SETTING_MARKERS = ("PRODUCT_BUNDLE_IDENTIFIER", "INFOPLIST_FILE")


def repo_root_from_shell(shell_dir: Path) -> Path:
    return shell_dir.resolve().parents[1]


def find_xcode_app_dir(shell_dir: Path) -> Path:
    """`npx cap add ios` writes mobile/ios/ios/App. Older layouts used App/."""
    candidates = (
        shell_dir / "ios" / "App",
        shell_dir / "App",
    )
    for path in candidates:
        if (path / "App.xcodeproj" / "project.pbxproj").is_file():
            return path
    raise FileNotFoundError(
        "generated Xcode project not found under "
        f"{shell_dir}/ios/App or {shell_dir}/App — run npx cap add ios first"
    )


def info_plist_path(app_dir: Path) -> Path:
    path = app_dir / "App" / "Info.plist"
    if not path.is_file():
        raise FileNotFoundError(f"Info.plist missing at {path}")
    return path


def entitlements_path(app_dir: Path) -> Path:
    return app_dir / "App" / "App.entitlements"


def pbxproj_path(app_dir: Path) -> Path:
    return app_dir / "App.xcodeproj" / "project.pbxproj"


def default_marketing_version(shell_dir: Path) -> str:
    package = json.loads((shell_dir / "package.json").read_text(encoding="utf-8"))
    version = str(package.get("version") or "1.0.0").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError(f"package.json version {version!r} is not x.y.z")
    return version


def resolve_build_number(explicit: str | None) -> str:
    if explicit:
        value = explicit.strip()
        if not value.isdigit():
            raise ValueError("build number must be digits only (CFBundleVersion)")
        return value
    return "1"


def _load_plist(path: Path) -> dict:
    with path.open("rb") as fh:
        data = plistlib.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a dict plist")
    return data


def _dump_plist(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        plistlib.dump(data, fh, fmt=plistlib.FMT_XML, sort_keys=False)


def patch_info_plist(path: Path) -> None:
    data = _load_plist(path)
    data["CFBundleDisplayName"] = DISPLAY_NAME
    # Keep Capacitor's $(MARKETING_VERSION) / $(CURRENT_PROJECT_VERSION)
    # so Fastlane increment_build_number and the pbxproj stay the source
    # of truth. Do not bake a literal build number in here.
    data["CFBundleShortVersionString"] = "$(MARKETING_VERSION)"
    data["CFBundleVersion"] = "$(CURRENT_PROJECT_VERSION)"
    data["ITSAppUsesNonExemptEncryption"] = False
    data.update(USAGE_STRINGS)
    _dump_plist(path, data)


def write_entitlements(path: Path) -> None:
    # Associated domains match the live AASA on badgeday.com. In-App Purchase
    # is a Developer Portal App ID capability, not an entitlements key — and
    # creating IAP *products* in App Store Connect stays HELD.
    payload = {
        "com.apple.developer.associated-domains": list(ASSOCIATED_DOMAINS),
    }
    _dump_plist(path, payload)


def _replace_or_insert_setting(block: str, key: str, value: str) -> str:
    pattern = rf"{re.escape(key)} = [^;]*;"
    replacement = f"{key} = {value};"
    if re.search(pattern, block):
        return re.sub(pattern, replacement, block)
    return re.sub(
        r"(buildSettings = \{)",
        rf"\1\n\t\t\t\t{replacement}",
        block,
        count=1,
    )


def patch_pbxproj(text: str, marketing_version: str, build_number: str) -> str:
    """Set bundle id / team / entitlements on the App target configs only."""

    def repl(match: re.Match[str]) -> str:
        block = match.group(0)
        if not any(marker in block for marker in _TARGET_SETTING_MARKERS):
            return block
        block = _replace_or_insert_setting(block, "PRODUCT_BUNDLE_IDENTIFIER", BUNDLE_ID)
        block = _replace_or_insert_setting(block, "DEVELOPMENT_TEAM", TEAM_ID)
        block = _replace_or_insert_setting(
            block, "CODE_SIGN_ENTITLEMENTS", ENTITLEMENTS_BUILD_PATH
        )
        block = _replace_or_insert_setting(
            block, "CURRENT_PROJECT_VERSION", build_number
        )
        block = _replace_or_insert_setting(block, "MARKETING_VERSION", marketing_version)
        return block

    patched = re.sub(r"buildSettings = \{[^{}]*\}", repl, text, flags=re.DOTALL)
    if patched.count(f"PRODUCT_BUNDLE_IDENTIFIER = {BUNDLE_ID};") < 1:
        raise ValueError("pbxproj patch did not set PRODUCT_BUNDLE_IDENTIFIER")
    if patched.count(f"DEVELOPMENT_TEAM = {TEAM_ID};") < 1:
        raise ValueError("pbxproj patch did not set DEVELOPMENT_TEAM")
    return patched


def copy_store_icon(app_dir: Path, icon_1024: Path) -> Path:
    if not icon_1024.is_file():
        raise FileNotFoundError(f"store icon missing: {icon_1024}")
    iconset = app_dir / "App" / "Assets.xcassets" / "AppIcon.appiconset"
    iconset.mkdir(parents=True, exist_ok=True)
    dest = iconset / "AppIcon-512@2x.png"
    shutil.copyfile(icon_1024, dest)
    contents = {
        "images": [
            {
                "filename": dest.name,
                "idiom": "universal",
                "platform": "ios",
                "size": "1024x1024",
            }
        ],
        "info": {"author": "xcode", "version": 1},
    }
    (iconset / "Contents.json").write_text(
        json.dumps(contents, indent=2) + "\n", encoding="utf-8"
    )
    return dest


def assert_patched(
    app_dir: Path, marketing_version: str, build_number: str
) -> None:
    plist = _load_plist(info_plist_path(app_dir))
    errors: list[str] = []
    if plist.get("CFBundleDisplayName") != DISPLAY_NAME:
        errors.append(f"CFBundleDisplayName is {plist.get('CFBundleDisplayName')!r}")
    for key, expected in USAGE_STRINGS.items():
        if plist.get(key) != expected:
            errors.append(f"{key} does not match INFO_PLIST_PERMISSIONS.md")
    if plist.get("ITSAppUsesNonExemptEncryption") is not False:
        errors.append("ITSAppUsesNonExemptEncryption must be false")
    if str(plist.get("CFBundleVersion")) != "$(CURRENT_PROJECT_VERSION)":
        errors.append(f"CFBundleVersion is {plist.get('CFBundleVersion')!r}")
    if str(plist.get("CFBundleShortVersionString")) != "$(MARKETING_VERSION)":
        errors.append(
            f"CFBundleShortVersionString is {plist.get('CFBundleShortVersionString')!r}"
        )

    entitlements = _load_plist(entitlements_path(app_dir))
    domains = entitlements.get("com.apple.developer.associated-domains")
    if list(domains or []) != list(ASSOCIATED_DOMAINS):
        errors.append(f"associated domains are {domains!r}")
    iap_keys = [key for key in entitlements if "in-app-purchase" in key.lower()]
    if iap_keys:
        errors.append(f"entitlements must not declare IAP product keys: {iap_keys}")

    pbx = pbxproj_path(app_dir).read_text(encoding="utf-8")
    if f"PRODUCT_BUNDLE_IDENTIFIER = {BUNDLE_ID};" not in pbx:
        errors.append("pbxproj missing locked bundle id")
    if f"DEVELOPMENT_TEAM = {TEAM_ID};" not in pbx:
        errors.append("pbxproj missing team id")
    if f"MARKETING_VERSION = {marketing_version};" not in pbx:
        errors.append("pbxproj missing marketing version")
    if f"CURRENT_PROJECT_VERSION = {build_number};" not in pbx:
        errors.append("pbxproj missing build number")
    if "com.getcapacitor.App" in pbx:
        errors.append("pbxproj still has the Capacitor template bundle id")

    icon = app_dir / "App" / "Assets.xcassets" / "AppIcon.appiconset" / "AppIcon-512@2x.png"
    if not icon.is_file() or icon.stat().st_size < 32:
        errors.append("AppIcon-512@2x.png missing or empty")

    if errors:
        raise AssertionError("native iOS patch failed:\n  - " + "\n  - ".join(errors))


def apply(
    shell_dir: Path,
    marketing_version: str | None = None,
    build_number: str | None = None,
) -> dict[str, str]:
    shell_dir = shell_dir.resolve()
    marketing = marketing_version or default_marketing_version(shell_dir)
    build = resolve_build_number(build_number)
    app_dir = find_xcode_app_dir(shell_dir)
    icon_src = repo_root_from_shell(shell_dir) / "web" / "public" / "icons" / "icon-1024.png"

    patch_info_plist(info_plist_path(app_dir))
    write_entitlements(entitlements_path(app_dir))
    pbx = pbxproj_path(app_dir)
    pbx.write_text(
        patch_pbxproj(pbx.read_text(encoding="utf-8"), marketing, build),
        encoding="utf-8",
    )
    copy_store_icon(app_dir, icon_src)
    assert_patched(app_dir, marketing, build)
    return {
        "appDir": str(app_dir),
        "bundleId": BUNDLE_ID,
        "teamId": TEAM_ID,
        "marketingVersion": marketing,
        "buildNumber": build,
        "iapProductCreate": "held",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("apply", "assert"))
    parser.add_argument(
        "shell_dir",
        nargs="?",
        default=str(Path(__file__).resolve().parent),
        help="mobile/ios (the Capacitor shell, not the generated ios/ folder)",
    )
    parser.add_argument("--marketing-version", default="")
    parser.add_argument("--build-number", default="")
    args = parser.parse_args(argv)

    shell_dir = Path(args.shell_dir)
    marketing = args.marketing_version or default_marketing_version(shell_dir)
    build = resolve_build_number(args.build_number or None)

    if args.command == "apply":
        report = apply(shell_dir, marketing, build)
        print(
            "patched native iOS: "
            f"bundleId={report['bundleId']} teamId={report['teamId']} "
            f"version={report['marketingVersion']}({report['buildNumber']}) "
            "iapProductCreate=held"
        )
        return 0

    app_dir = find_xcode_app_dir(shell_dir)
    assert_patched(app_dir, marketing, build)
    print(f"native iOS patch ok: {app_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
