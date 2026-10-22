"""Fail if recruit-audio holds a recording older than a day.

    python scripts/recruit_audio_retention_check.py

Exit 0 when the bucket has no such file. Exit 1 when it does, or when the
listing itself fails. Exit 2 when the service-role credentials are missing.
The monthly GitHub Action runs this and treats any non-zero exit as a failure.
"""

import sys

from app.config import get_settings
from app.storage.client import service_client
from app.storage.recruit_audio_retention import enforce_recruit_audio_retention


def main() -> int:
    settings = get_settings()
    if not (settings.supabase_url and settings.supabase_service_role_key):
        print(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.",
            file=sys.stderr,
        )
        return 2
    try:
        stale = enforce_recruit_audio_retention(service_client(settings))
    except Exception as exc:
        print(f"recruit-audio retention check failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    if stale:
        print(
            f"recruit-audio has {len(stale)} file(s) older than one day.",
            file=sys.stderr,
        )
        for name in stale[:50]:
            print(f"  {name}", file=sys.stderr)
        if len(stale) > 50:
            print(f"  ... {len(stale) - 50} more", file=sys.stderr)
        return 1
    print("recruit-audio has no files older than one day.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
