"""Pure Gradle transforms used by mobile/android/build-twa.sh.

Kept out of the shell so the signing attach and the billing pin can be tested
with a snippet, not only after a full Bubblewrap run. No keystore I/O, no
passwords — signing still reads TWA_* from the process environment at build
time.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PINNED_BILLING_HELPER = "com.google.androidbrowserhelper:billing:1.2.0"
MIN_BILLING_CLIENT = (8, 3, 0)
_SIGNING_ATTACH = "signingConfig signingConfigs.release"


def _matching_brace(text: str, open_idx: int) -> int:
    """`open_idx` points at '{'. Return the index of its matching '}'."""
    if open_idx >= len(text) or text[open_idx] != "{":
        raise ValueError("open_idx must point at '{'")
    depth = 0
    for i in range(open_idx, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("unbalanced braces")


def _keyword_block(
    text: str, keyword: str, start: int = 0, end: int | None = None
) -> tuple[int, int, int]:
    """Return (keyword_start, brace_open, brace_close) for `keyword {` in range."""
    stop = len(text) if end is None else end
    match = re.search(rf"\b{re.escape(keyword)}\s*\{{", text[start:stop])
    if not match:
        raise ValueError(f"no {keyword} {{ ... }} block")
    keyword_start = start + match.start()
    brace_open = start + match.end() - 1
    brace_close = _matching_brace(text, brace_open)
    if brace_close > stop:
        raise ValueError(f"{keyword} block overruns the enclosing range")
    return keyword_start, brace_open, brace_close


def _indent_of_line_containing(text: str, idx: int) -> str:
    line_start = text.rfind("\n", 0, idx) + 1
    raw = text[line_start:idx]
    return raw[: len(raw) - len(raw.lstrip(" \t"))]


def _build_types_release_span(text: str) -> tuple[int, int, int]:
    """Brace span of `buildTypes { release { ... } }`, not `signingConfigs.release`."""
    _, types_open, types_close = _keyword_block(text, "buildTypes")
    _, rel_open, rel_close = _keyword_block(text, "release", start=types_open, end=types_close)
    return rel_open, rel_close, types_close


def signing_config_is_under_build_types_release(text: str) -> bool:
    try:
        rel_open, rel_close, _ = _build_types_release_span(text)
    except ValueError:
        return False
    return _SIGNING_ATTACH in text[rel_open : rel_close + 1]


def signing_config_is_inside_signing_configs_release(text: str) -> bool:
    """The bug: a first-match replace put signingConfig inside signingConfigs.release."""
    try:
        _, configs_open, configs_close = _keyword_block(text, "signingConfigs")
        _, rel_open, rel_close = _keyword_block(
            text, "release", start=configs_open, end=configs_close
        )
    except ValueError:
        return False
    return _SIGNING_ATTACH in text[rel_open : rel_close + 1]


def apply_release_signing(text: str, keystore: str) -> str:
    """Insert signingConfigs and attach it under buildTypes.release only.

    A blind replace of the first `release {` matches the new
    `signingConfigs { release {` } and never signs the bundle.
    """
    if signing_config_is_under_build_types_release(text):
        return text

    if "buildTypes" not in text:
        raise ValueError("generated app/build.gradle has no buildTypes block")

    if "signingConfigs" not in text:
        block = (
            "\n    signingConfigs {\n"
            "        release {\n"
            f"            storeFile file({keystore!r})\n"
            '            storePassword System.getenv("TWA_KEYSTORE_PASSWORD")\n'
            '            keyAlias System.getenv("TWA_KEY_ALIAS")\n'
            '            keyPassword System.getenv("TWA_KEY_PASSWORD")\n'
            "        }\n"
            "    }\n"
        )
        types_kw, _, _ = _keyword_block(text, "buildTypes")
        # Insert at the start of the buildTypes line so its indent stays put.
        line_start = text.rfind("\n", 0, types_kw) + 1
        text = text[:line_start] + block.lstrip("\n") + text[line_start:]

    rel_open, rel_close, _ = _build_types_release_span(text)
    if _SIGNING_ATTACH in text[rel_open : rel_close + 1]:
        return text

    indent = _indent_of_line_containing(text, rel_open) + "    "
    insert = f"\n{indent}{_SIGNING_ATTACH}"
    return text[: rel_open + 1] + insert + text[rel_open + 1 :]


def _parse_dotted_version(raw: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in raw.split("."):
        digits = re.match(r"(\d+)", piece)
        if not digits:
            break
        parts.append(int(digits.group(1)))
    if not parts:
        raise ValueError(f"not a version: {raw!r}")
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def billing_client_version(gradle: str) -> tuple[int, ...] | None:
    match = re.search(r"com\.android\.billingclient:billing:([0-9][0-9A-Za-z.+-]*)", gradle)
    if not match:
        return None
    try:
        return _parse_dotted_version(match.group(1))
    except ValueError:
        return None


def billing_pin_errors(gradle: str, helper: str = PINNED_BILLING_HELPER) -> list[str]:
    """Fail closed unless the pinned helper or Billing Library >= 8.3.0 is present.

    An unpinned or older `androidbrowserhelper:billing` line is not enough:
    helper 1.1.0 still pulls Billing Library 7.x, which Play rejects for new apps.
    """
    if helper in gradle:
        return []
    version = billing_client_version(gradle)
    if version is not None and version >= MIN_BILLING_CLIENT:
        return []
    if "androidbrowserhelper:billing" in gradle:
        return [
            "generated app/build.gradle has an unpinned or older Play Billing helper; "
            f"need {helper} or com.android.billingclient:billing:"
            f"{'.'.join(str(p) for p in MIN_BILLING_CLIENT)}+"
        ]
    return ["generated app/build.gradle is missing the Play Billing helper"]


def generated_project_errors(
    gradle: str,
    manifest: str,
    expected_package: str,
    helper: str = PINNED_BILLING_HELPER,
) -> list[str]:
    errors: list[str] = []
    if (
        f'applicationId "{expected_package}"' not in gradle
        and f"applicationId '{expected_package}'" not in gradle
    ):
        errors.append(f"generated app/build.gradle does not set applicationId {expected_package}")
    errors.extend(billing_pin_errors(gradle, helper))
    needles = ("PaymentActivity", "DigitalGoodsRequestHandler", "play.google.com/billing")
    if manifest and not any(n in manifest for n in needles):
        errors.append("generated AndroidManifest.xml has no Play Billing / Digital Goods component")
    return errors


def _cmd_apply_signing(gradle_path: Path, keystore: str) -> None:
    text = gradle_path.read_text(encoding="utf-8")
    if signing_config_is_under_build_types_release(text):
        print("Release signing config already present under buildTypes.release")
        return
    updated = apply_release_signing(text, keystore)
    if signing_config_is_inside_signing_configs_release(updated):
        sys.exit("error: signingConfig landed inside signingConfigs.release")
    if not signing_config_is_under_build_types_release(updated):
        sys.exit("error: signingConfig was not attached under buildTypes.release")
    gradle_path.write_text(updated, encoding="utf-8")
    print("Release signing config applied from CI env (passwords not written to disk)")


def _cmd_assert_generated(
    gradle_path: Path, manifest_path: Path, expected_package: str, helper: str
) -> None:
    gradle = gradle_path.read_text(encoding="utf-8")
    manifest = manifest_path.read_text(encoding="utf-8") if manifest_path.is_file() else ""
    errors = generated_project_errors(gradle, manifest, expected_package, helper)
    if errors:
        print("Generated project guardrail failed:", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        raise SystemExit(1)
    print("Generated project ok: applicationId set, Play Billing pin present")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sign = sub.add_parser("apply-signing")
    sign.add_argument("gradle")
    sign.add_argument("keystore")
    check = sub.add_parser("assert-generated")
    check.add_argument("gradle")
    check.add_argument("manifest")
    check.add_argument("package")
    check.add_argument("helper")
    args = parser.parse_args(argv)
    if args.cmd == "apply-signing":
        _cmd_apply_signing(Path(args.gradle), args.keystore)
        return 0
    _cmd_assert_generated(Path(args.gradle), Path(args.manifest), args.package, args.helper)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
