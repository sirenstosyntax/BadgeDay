"""Print the copy of `.env` that the GitHub deploy workflow should use.

Run by deploy/setup_github_deploy.sh on the laptop that already deploys, and piped
straight into `gh secret set`, so the values are never shown on screen:

    python scripts/github_deploy_env.py .env | gh secret set BADGEDAY_ENV

It changes one thing. Supabase's direct database host (db.<ref>.supabase.co) answers on
IPv6 only unless the project bought the IPv4 add-on, and GitHub's hosted runners have no
IPv6 — so a migration that works from home fails from Actions with "network is
unreachable". When the direct host has no IPv4 address, this finds the project's session
pooler (same database, same password, IPv4, port 5432) and swaps SUPABASE_DB_URL for it
in the copy only. The laptop's own .env is never touched.

Status goes to stderr and never includes a URL; stdout carries only the env text.
"""

import re
import socket
import sys
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

DB_URL_KEY = "SUPABASE_DB_URL"

DIRECT_HOST = re.compile(r"^db\.([a-z0-9]+)\.supabase\.co$")

# Supabase's pooler hosts are aws-0-<region> for older projects and aws-1-<region> for
# newer ones. A wrong region answers "Tenant or user not found" at once, so trying them in
# turn costs seconds, not minutes.
POOLER_PREFIXES = ("aws-0", "aws-1")
POOLER_REGIONS = (
    "us-east-1",
    "us-east-2",
    "us-west-1",
    "us-west-2",
    "ca-central-1",
    "sa-east-1",
    "eu-west-1",
    "eu-west-2",
    "eu-west-3",
    "eu-central-1",
    "eu-central-2",
    "eu-north-1",
    "ap-south-1",
    "ap-southeast-1",
    "ap-southeast-2",
    "ap-northeast-1",
    "ap-northeast-2",
)


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1].strip()
    return value


def read_env_value(env_text: str, key: str) -> str | None:
    """The value of `key` in a .env, read the way deploy/env_secrets.sh reads it."""
    for line in env_text.splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key:
            return _unquote(value) or None
    return None


def replace_env_value(env_text: str, key: str, value: str) -> str:
    """`env_text` with every `key=` line set to `value`, everything else byte for byte."""
    out = []
    for line in env_text.splitlines(keepends=True):
        bare = line.strip()
        if bare.startswith("export "):
            bare = bare[len("export ") :].strip()
        if "=" in bare and bare.split("=", 1)[0].strip() == key:
            ending = "\n" if line.endswith("\n") else ""
            out.append(f"{key}={value}{ending}")
        else:
            out.append(line)
    return "".join(out)


def direct_project_ref(db_url: str) -> str | None:
    """The project ref when `db_url` points at the direct host, else None."""
    match = DIRECT_HOST.match(urlsplit(db_url).hostname or "")
    return match.group(1) if match else None


def pooler_url(db_url: str, ref: str, host: str) -> str:
    """`db_url` re-pointed at a session pooler host: user postgres.<ref>, port 5432."""
    parts = urlsplit(db_url)
    user = parts.username or "postgres"
    if not user.endswith(f".{ref}"):
        user = f"{user}.{ref}"
    netloc = user if parts.password is None else f"{user}:{parts.password}"
    netloc = f"{netloc}@{host}:5432"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def pooler_candidates(db_url: str, ref: str) -> Iterator[str]:
    for prefix in POOLER_PREFIXES:
        for region in POOLER_REGIONS:
            yield pooler_url(db_url, ref, f"{prefix}-{region}.pooler.supabase.com")


def has_ipv4(host: str) -> bool:
    try:
        return bool(socket.getaddrinfo(host, 5432, socket.AF_INET))
    except socket.gaierror:
        return False


def _connects(url: str) -> bool:
    import psycopg

    try:
        with psycopg.connect(url, connect_timeout=5) as conn:
            conn.execute("select 1")
        return True
    except psycopg.Error:
        return False


def url_for_github(db_url: str) -> str:
    ref = direct_project_ref(db_url)
    if ref is None:
        print("Database address is not the direct host; using it as is.", file=sys.stderr)
        return db_url
    if has_ipv4(urlsplit(db_url).hostname or ""):
        print("Direct database host has an IPv4 address; using it as is.", file=sys.stderr)
        return db_url
    print("Direct database host is IPv6 only; looking for its session pooler…", file=sys.stderr)
    for candidate in pooler_candidates(db_url, ref):
        if _connects(candidate):
            host = urlsplit(candidate).hostname
            print(f"Found the session pooler at {host}.", file=sys.stderr)
            return candidate
    print(
        "warning: no session pooler answered. Keeping the direct address; the GitHub "
        "database step will fail until SUPABASE_DB_URL in the BADGEDAY_ENV secret is the "
        "Session pooler string from Supabase -> Connect.",
        file=sys.stderr,
    )
    return db_url


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: github_deploy_env.py PATH_TO_ENV", file=sys.stderr)
        return 2
    env_text = Path(argv[1]).read_text(encoding="utf-8")
    db_url = read_env_value(env_text, DB_URL_KEY)
    if db_url is None:
        print(f"{DB_URL_KEY} is not set in {argv[1]}.", file=sys.stderr)
        return 1
    github_url = url_for_github(db_url)
    if github_url != db_url:
        env_text = replace_env_value(env_text, DB_URL_KEY, github_url)
    sys.stdout.write(env_text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
