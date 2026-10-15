"""Pluggable follow-up mail.

Supabase Auth already sends the sign-in code. It does not send arbitrary
mail. Resend is the sender when RESEND_API_KEY and EMAIL_FROM are set.
Otherwise LogSender records that nothing went out and the caller leaves the
row unsent, so a later key still delivers the one email.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from app.config import Settings

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"


@dataclass(frozen=True)
class OutboundEmail:
    to: str
    subject: str
    text: str
    headers: dict[str, str]


@dataclass(frozen=True)
class SendResult:
    delivered: bool
    detail: str = ""


class EmailSender(Protocol):
    configured: bool

    def send(self, message: OutboundEmail) -> SendResult: ...


class LogSender:
    """Default. Does not deliver and does not pretend it did."""

    configured = False

    def send(self, message: OutboundEmail) -> SendResult:
        logger.info(
            "recruit follow-up not sent to %s (%s); email sender is not configured",
            message.to,
            message.subject,
        )
        return SendResult(delivered=False, detail="sender not configured")


class ResendSender:
    configured = True

    def __init__(self, api_key: str, from_address: str) -> None:
        self._api_key = api_key
        self._from = from_address

    def send(self, message: OutboundEmail) -> SendResult:
        payload = {
            "from": self._from,
            "to": [message.to],
            "subject": message.subject,
            "text": message.text,
            "headers": message.headers,
        }
        request = urllib.request.Request(
            RESEND_URL,
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                if 200 <= response.status < 300:
                    return SendResult(delivered=True)
                return SendResult(delivered=False, detail=f"HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:500]
            logger.warning("Resend refused a recruit follow-up: HTTP %s", exc.code)
            return SendResult(delivered=False, detail=f"HTTP {exc.code}: {body}")
        except Exception as exc:
            logger.warning("Resend request failed: %s", type(exc).__name__)
            return SendResult(delivered=False, detail=str(exc))


def badge_day_from(raw: str) -> str:
    """The From header names BadgeDay. An address alone gets that display name."""
    text = raw.strip()
    if not text:
        return ""
    if text.lower().startswith("badgeday"):
        return text
    if "<" in text and ">" in text:
        return text
    return f"BadgeDay <{text}>"


def build_sender(settings: Settings) -> EmailSender:
    api_key = settings.resend_api_key.strip()
    from_address = badge_day_from(settings.email_from)
    if api_key and from_address:
        return ResendSender(api_key, from_address)
    return LogSender()
