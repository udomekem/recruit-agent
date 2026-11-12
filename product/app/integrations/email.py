"""Email providers behind one interface (phase 5 design section 7).

- `log`: records messages in memory, sends nothing (tests, and the safe default).
- `mailpit`: a local test inbox (Docker Compose). Local only, so it is allowed while
  EMAIL_SENDING_ENABLED is false.
- `resend`: real sending. Used only when EMAIL_SENDING_ENABLED is true AND a key is set;
  otherwise `make_sender` falls back to `log`. Resend dedupes on the Idempotency-Key
  header, so a repeat after a crash returns the first result instead of a second email.

`already_delivered` lets the delivery job check, after a crash between the provider
accepting a message and the outbox row being marked sent, whether to send again.
"""

from __future__ import annotations

import asyncio
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage as MimeMessage
from email.utils import formatdate
from typing import Any, Protocol

import httpx

from app.config import Settings


class EmailError(Exception):
    """Delivery failed; the job may retry."""


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    sender: str
    reply_to: str
    subject: str
    text: str
    message_id: str  # "<key@domain>", the same on every attempt


class EmailSender(Protocol):
    name: str

    async def send(self, msg: OutgoingEmail) -> str: ...

    async def already_delivered(self, message_id: str) -> bool: ...


@dataclass
class LogSender:
    """Sends nothing. Keeps what it would have sent (tests read `sent`)."""

    name: str = "log"
    sent: list[OutgoingEmail] = field(default_factory=list)
    fail_times: int = 0  # tests: fail this many sends first

    async def send(self, msg: OutgoingEmail) -> str:
        if self.fail_times > 0:
            self.fail_times -= 1
            raise EmailError("log sender configured to fail")
        self.sent.append(msg)
        return f"log-{len(self.sent)}"

    async def already_delivered(self, message_id: str) -> bool:
        return any(m.message_id == message_id for m in self.sent)


def _mime(msg: OutgoingEmail) -> MimeMessage:
    m = MimeMessage()
    m["From"] = msg.sender
    m["To"] = msg.to
    m["Reply-To"] = msg.reply_to
    m["Subject"] = msg.subject
    m["Message-ID"] = msg.message_id
    m["Date"] = formatdate(localtime=False)
    m.set_content(msg.text)
    return m


@dataclass
class MailpitSender:
    smtp_host: str
    smtp_port: int
    api_url: str
    timeout: float = 10.0
    name: str = "mailpit"

    def _send_sync(self, msg: OutgoingEmail) -> None:
        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=self.timeout) as smtp:
            smtp.send_message(_mime(msg))

    async def send(self, msg: OutgoingEmail) -> str:
        try:
            await asyncio.to_thread(self._send_sync, msg)
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailError(f"mailpit: {type(exc).__name__}: {exc}") from exc
        return msg.message_id

    async def already_delivered(self, message_id: str) -> bool:
        bare = message_id.strip("<>")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                r = await c.get(
                    f"{self.api_url.rstrip('/')}/api/v1/search",
                    params={"query": f"message-id:{bare}", "limit": "50"},
                )
                r.raise_for_status()
                data: dict[str, Any] = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise EmailError(f"mailpit search: {type(exc).__name__}") from exc
        # The search is loose (it matches word parts of the id), so compare exactly.
        # Found in the phase 5 build: a different id also "matched".
        return any(
            str(m.get("MessageID", "")).strip("<>") == bare for m in data.get("messages") or []
        )


@dataclass
class ResendSender:
    api_key: str
    url: str = "https://api.resend.com/emails"
    timeout: float = 10.0
    transport: Any = None
    name: str = "resend"

    async def send(self, msg: OutgoingEmail) -> str:
        payload = {
            "from": msg.sender,
            "to": [msg.to],
            "reply_to": msg.reply_to,
            "subject": msg.subject,
            "text": msg.text,
            "headers": {"Message-ID": msg.message_id},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Idempotency-Key": msg.message_id.strip("<>"),
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as c:
                r = await c.post(self.url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise EmailError(f"resend: {type(exc).__name__}") from exc
        if r.status_code >= 400:
            raise EmailError(f"resend: HTTP {r.status_code}")
        return str(r.json().get("id", ""))

    async def already_delivered(self, message_id: str) -> bool:
        # Resend dedupes on the idempotency key: sending again is the safe check.
        return False


def make_sender(settings: Settings) -> EmailSender:
    if settings.email_provider == "mailpit":
        return MailpitSender(
            settings.mailpit_smtp_host,
            settings.mailpit_smtp_port,
            settings.mailpit_api_url,
            settings.email_timeout_seconds,
        )
    if (
        settings.email_provider == "resend"
        and settings.email_sending_enabled
        and settings.resend_api_key is not None
    ):
        return ResendSender(
            settings.resend_api_key.get_secret_value(),
            settings.resend_url,
            settings.email_timeout_seconds,
        )
    return LogSender()
