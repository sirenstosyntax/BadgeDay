"""Parse rules for deploy/env_secrets.sh. Names only in assertions."""

from pathlib import Path
import subprocess

HELPER = Path(__file__).resolve().parent.parent / "deploy" / "env_secrets.sh"


def _names(env_text: str, *, crlf: bool = False) -> list[str]:
    env_file = Path("/tmp/badgeday-parse-env-test.env")
    data = env_text.encode()
    if crlf:
        data = env_text.replace("\n", "\r\n").encode()
    env_file.write_bytes(data)
    script = f"""
set -euo pipefail
source "{HELPER}"
parse_env_file "{env_file}"
env_secret_names
"""
    result = subprocess.run(
        ["bash", "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def _has_deepgram(env_text: str, environment: str) -> int:
    env_file = Path("/tmp/badgeday-parse-env-prod-test.env")
    env_file.write_text(env_text)
    script = f"""
set -euo pipefail
source "{HELPER}"
parse_env_file "{env_file}"
require_deepgram_if_production "{environment}" "{env_file}"
"""
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True).returncode


def test_plain_deepgram_is_kept() -> None:
    assert "deepgram-api-key" in _names("DEEPGRAM_API_KEY=dg-test-plain\n")


def test_export_quoted_deepgram_is_kept() -> None:
    assert "deepgram-api-key" in _names('export DEEPGRAM_API_KEY="dg-test-quoted"\n')


def test_single_quoted_deepgram_is_kept() -> None:
    assert "deepgram-api-key" in _names("DEEPGRAM_API_KEY='dg-test-single'\n")


def test_crlf_deepgram_is_kept() -> None:
    assert "deepgram-api-key" in _names("DEEPGRAM_API_KEY=dg-test-crlf\n", crlf=True)


def test_leading_space_deepgram_is_kept() -> None:
    assert "deepgram-api-key" in _names("  DEEPGRAM_API_KEY=dg-test-space\n")


def test_empty_quoted_deepgram_is_dropped() -> None:
    assert "deepgram-api-key" not in _names('DEEPGRAM_API_KEY=""\nANTHROPIC_API_KEY=dummy\n')


def test_production_without_deepgram_fails() -> None:
    assert _has_deepgram("ANTHROPIC_API_KEY=dummy\n", "production") != 0


def test_production_with_deepgram_passes() -> None:
    assert _has_deepgram("DEEPGRAM_API_KEY=dg-test-ok\n", "production") == 0


def test_names_output_has_no_values() -> None:
    names = "\n".join(_names('DEEPGRAM_API_KEY="dg-secret-must-not-print"\n'))
    assert "dg-secret-must-not-print" not in names
    assert "deepgram-api-key" in names
