#!/usr/bin/env python3
"""Re-export a distribution P12 so macOS `security import` can read it.

OpenSSL 3's default `pkcs12 -export` uses AES-256-CBC + PBKDF2. Apple
`security` (SecKeychainItemImport) often rejects that bag with
"MAC verification failed during PKCS12 import (wrong password?)" even
when the password is correct. Re-export with
`-keypbe PBE-SHA1-3DES -certpbe PBE-SHA1-3DES -macalg SHA1` before
Fastlane imports into the setup_ci keychain.

Does not invent secrets. Reads IOS_DISTRIBUTION_CERTIFICATE_PASSWORD from
the environment. Never prints the password.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

OPENSSL_CANDIDATES = (
    "/opt/homebrew/opt/openssl@3/bin/openssl",
    "/usr/local/opt/openssl@3/bin/openssl",
)

Proc = subprocess.CompletedProcess[str]


def openssl_binaries() -> list[str]:
    found: list[str] = []
    for candidate in OPENSSL_CANDIDATES:
        if os.path.isfile(candidate):
            found.append(candidate)
    which = shutil.which("openssl")
    if which and which not in found:
        found.append(which)
    return found


def _run(openssl: str, args: Sequence[str], env: dict[str, str]) -> Proc:
    return subprocess.run(
        [openssl, *args],
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )


# OpenSSL 3's default provider cannot unwrap SHA1-3DES / RC2 bags;
# those need ``-legacy``. A modern AES-256-CBC+PBKDF2 bag fails *with*
# ``-legacy``. LibreSSL / OpenSSL 1.1 reject the flag entirely. Try
# without, then with, before fail-closed.
DECRYPT_PKCS12_EXTRA_FLAGS: tuple[tuple[str, ...], ...] = (
    (),
    ("-legacy",),
)


def decrypt_p12(openssl: str, src: Path, pem: Path, env: dict[str, str]) -> Proc:
    last: Proc | None = None
    for extra in DECRYPT_PKCS12_EXTRA_FLAGS:
        if pem.exists():
            pem.unlink()
        result = _run(
            openssl,
            [
                "pkcs12",
                "-in",
                str(src),
                "-passin",
                "env:IOS_DISTRIBUTION_CERTIFICATE_PASSWORD",
                "-nodes",
                "-out",
                str(pem),
                *extra,
            ],
            env,
        )
        if result.returncode == 0:
            return result
        last = result
    assert last is not None
    return last


APPLE_P12_PBE = (
    "-keypbe",
    "PBE-SHA1-3DES",
    "-certpbe",
    "PBE-SHA1-3DES",
    "-macalg",
    "SHA1",
)


def export_p12(openssl: str, pem: Path, dest: Path, env: dict[str, str]) -> Proc:
    # SHA1-3DES only. An OpenSSL 3 default bag (AES-256-CBC+PBKDF2) is what
    # Apple `security` rejects as MAC verification failed. Fail closed —
    # do not fall back to that encoding.
    return _run(
        openssl,
        [
            "pkcs12",
            "-export",
            "-in",
            str(pem),
            "-out",
            str(dest),
            "-passout",
            "env:IOS_DISTRIBUTION_CERTIFICATE_PASSWORD",
            *APPLE_P12_PBE,
        ],
        env,
    )


def rewrite(src: Path, dest: Path, password: str) -> str:
    if not src.is_file():
        raise SystemExit(f"error: P12 not found at {src}")
    if not password:
        raise SystemExit(
            "error: IOS_DISTRIBUTION_CERTIFICATE_PASSWORD is empty. "
            "Cannot import or rewrite the distribution P12."
        )

    env = os.environ.copy()
    env["IOS_DISTRIBUTION_CERTIFICATE_PASSWORD"] = password

    binaries = openssl_binaries()
    if not binaries:
        if src.resolve() != dest.resolve():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        return "no openssl; left P12 as uploaded"

    last_err = ""
    for openssl in binaries:
        with tempfile.TemporaryDirectory(prefix="badgeday-p12-") as tmp:
            pem = Path(tmp) / "bag.pem"
            dumped = decrypt_p12(openssl, src, pem, env)
            if dumped.returncode != 0:
                last_err = (dumped.stderr or dumped.stdout or "openssl pkcs12 failed")
                last_err = last_err.strip()
                continue
            out = Path(tmp) / "macos.p12"
            exported = export_p12(openssl, pem, out, env)
            too_small = not out.is_file() or out.stat().st_size < 32
            if exported.returncode != 0 or too_small:
                last_err = exported.stderr or exported.stdout
                last_err = (last_err or "openssl pkcs12 -export failed").strip()
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(out, dest)
            os.chmod(dest, 0o600)
            return f"wrote macOS-compatible P12 via {openssl}"

    raise SystemExit(
        "error: cannot decrypt or SHA1-3DES-export "
        "IOS_DISTRIBUTION_CERTIFICATE_P12_BASE64 "
        f"with IOS_DISTRIBUTION_CERTIFICATE_PASSWORD ({last_err or 'openssl pkcs12 failed'}). "
        "Wrong password, OpenSSL 3 could not unwrap the bag even with "
        "-legacy, or SHA1-3DES export failed (no OpenSSL-3-default fallback — "
        "that bag is what Apple `security` rejects as MAC verification failed). "
        "Recreate the P12 with -keypbe PBE-SHA1-3DES -certpbe PBE-SHA1-3DES "
        "-macalg SHA1 — see mobile/ios/TESTFLIGHT_CI.md."
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: rewrite_p12_for_macos.py SRC DEST", file=sys.stderr)
        return 2
    src, dest = Path(args[0]), Path(args[1])
    password = os.environ.get("IOS_DISTRIBUTION_CERTIFICATE_PASSWORD", "")
    print(rewrite(src, dest, password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
