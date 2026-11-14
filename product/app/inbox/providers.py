"""Mailbox providers behind one interface (phase 5B design section 1).

- `mailpit`: the local test inbox (its HTTP API); a Mailpit tag stands in for a label, so
  the demo and the browser tests need no Google account.
- `gmail`: Gmail API with a refresh token; scope `gmail.readonly` only. Never sends,
  moves, labels or deletes anything.
- `fake`: in memory, for unit tests.

Every provider only lists messages under one label and downloads a message's attachments;
no provider reads or returns the body text.
"""

from __future__ import annotations

import base64
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from typing import Any, Protocol

import httpx

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 (a URL, not a secret)


class ProviderError(Exception):
    """A provider call failed; retry later."""


class ProviderAuthError(ProviderError):
    """The access was revoked or expired; the recruiter has to reconnect."""


@dataclass(frozen=True)
class Attachment:
    name: str
    media_type: str
    data: bytes


@dataclass(frozen=True)
class RawEmail:
    id: str
    subject: str
    sender_name: str
    sender_address: str
    to: list[str]
    received_at: datetime | None
    attachments: list[Attachment]
    skipped: list[str] = field(default_factory=list)  # attachments not downloaded, with why


class MailboxProvider(Protocol):
    name: str

    async def labels(self) -> list[str]: ...

    async def list_new(
        self, label: str, checkpoint: str | None, limit: int
    ) -> tuple[list[str], str | None]: ...

    async def fetch(self, message_id: str, max_bytes: int) -> RawEmail: ...


def _wanted(name: str, media_type: str) -> bool:
    """Only files that could be a CV are downloaded (PDF and Word .docx)."""
    n = name.lower()
    return n.endswith((".pdf", ".docx")) or media_type in (
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


# ---- Mailpit (local test inbox) -----------------------------------------------------------


class MailpitMailbox:
    name = "mailpit"

    def __init__(self, api_url: str, timeout: float = 10.0) -> None:
        self.api = api_url.rstrip("/")
        self.timeout = timeout

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                r = await c.get(f"{self.api}{path}", params=params)
        except httpx.HTTPError as exc:
            raise ProviderError(f"mailpit unreachable: {type(exc).__name__}") from exc
        if r.status_code >= 400:
            raise ProviderError(f"mailpit returned {r.status_code}")
        return r

    async def labels(self) -> list[str]:
        r = await self._get("/api/v1/tags")
        return sorted(str(t) for t in (r.json() or []))

    async def list_new(
        self, label: str, checkpoint: str | None, limit: int
    ) -> tuple[list[str], str | None]:
        r = await self._get("/api/v1/search", {"query": f'tag:"{label}"', "limit": limit})
        msgs = r.json().get("messages") or []
        # oldest first, so a partial run processes in arrival order
        ids = [str(m["ID"]) for m in sorted(msgs, key=lambda m: str(m.get("Created", "")))]
        return ids, checkpoint  # the unique message key makes re-listing harmless

    async def fetch(self, message_id: str, max_bytes: int) -> RawEmail:
        m = (await self._get(f"/api/v1/message/{message_id}")).json()
        frm = m.get("From") or {}
        to = [str(a.get("Address", "")) for a in (m.get("To") or [])]
        to += [str(a.get("Address", "")) for a in (m.get("Cc") or [])]
        atts: list[Attachment] = []
        skipped: list[str] = []
        for a in m.get("Attachments") or []:
            name, media = str(a.get("FileName", "")), str(a.get("ContentType", ""))
            if not _wanted(name, media):
                skipped.append(f"{name or 'file'}: not a PDF or Word file")
                continue
            if int(a.get("Size", 0)) > max_bytes:
                skipped.append(f"{name}: larger than the limit")
                continue
            part = await self._get(f"/api/v1/message/{message_id}/part/{a['PartID']}")
            atts.append(Attachment(name, media, part.content))
        received = None
        if m.get("Date"):
            try:
                received = datetime.fromisoformat(str(m["Date"]).replace("Z", "+00:00"))
            except ValueError:
                received = None
        return RawEmail(
            id=message_id,
            subject=str(m.get("Subject", "")),
            sender_name=str(frm.get("Name", "")),
            sender_address=str(frm.get("Address", "")),
            to=[a for a in to if a],
            received_at=received,
            attachments=atts,
            skipped=skipped,
        )


# ---- Gmail -----------------------------------------------------------------------------------


class GmailMailbox:
    name = "gmail"

    def __init__(
        self,
        refresh_token: str,
        client_id: str,
        client_secret: str,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.refresh_token = refresh_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout
        self.transport = transport
        self._access: str | None = None
        self._label_ids: dict[str, str] = {}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout, transport=self.transport)

    async def _token(self) -> str:
        if self._access:
            return self._access
        try:
            async with self._client() as c:
                r = await c.post(
                    GOOGLE_TOKEN_URL,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": self.refresh_token,
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    },
                )
        except httpx.HTTPError as exc:
            raise ProviderError(f"google unreachable: {type(exc).__name__}") from exc
        if r.status_code in (400, 401):
            raise ProviderAuthError("google refused the stored access; reconnect the inbox")
        if r.status_code >= 400:
            raise ProviderError(f"google token endpoint returned {r.status_code}")
        body = r.json()
        if GMAIL_SCOPE not in str(body.get("scope", GMAIL_SCOPE)).split():
            raise ProviderAuthError("the access no longer includes read only Gmail")
        self._access = str(body["access_token"])
        return self._access

    async def _get(self, path: str, params: Any = None) -> dict[str, Any]:
        token = await self._token()
        try:
            async with self._client() as c:
                r = await c.get(
                    f"{GMAIL_API}{path}",
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                )
        except httpx.HTTPError as exc:
            raise ProviderError(f"gmail unreachable: {type(exc).__name__}") from exc
        if r.status_code in (401, 403):
            raise ProviderAuthError(f"gmail refused access ({r.status_code})")
        if r.status_code >= 400:
            raise ProviderError(f"gmail returned {r.status_code}")
        data: dict[str, Any] = r.json()
        return data

    async def _labels(self) -> dict[str, str]:
        if not self._label_ids:
            data = await self._get("/labels")
            self._label_ids = {str(x["name"]): str(x["id"]) for x in data.get("labels", [])}
        return self._label_ids

    async def labels(self) -> list[str]:
        return sorted((await self._labels()).keys())

    async def list_new(
        self, label: str, checkpoint: str | None, limit: int
    ) -> tuple[list[str], str | None]:
        ids = await self._labels()
        if label not in ids:
            raise ProviderError(f"the label {label!r} no longer exists")
        params: dict[str, Any] = {"labelIds": ids[label], "maxResults": limit}
        if checkpoint:
            params["q"] = f"after:{checkpoint}"  # epoch seconds of the newest seen
        data = await self._get("/messages", params)
        msgs = [str(m["id"]) for m in data.get("messages", [])]
        # The new checkpoint is set after fetching (from internalDate); keep the old one
        # here so a failure part way never skips a message.
        return list(reversed(msgs)), checkpoint

    async def fetch(self, message_id: str, max_bytes: int) -> RawEmail:
        m = await self._get(f"/messages/{message_id}", {"format": "full"})
        payload = m.get("payload", {})
        headers = {str(h["name"]).lower(): str(h["value"]) for h in payload.get("headers", [])}
        name, addr = parseaddr(headers.get("from", ""))
        to = [
            a for _, a in getaddresses([headers.get(k, "") for k in ("to", "cc", "delivered-to")])
        ]
        atts: list[Attachment] = []
        skipped: list[str] = []
        for part in _parts(payload):
            fname = str(part.get("filename") or "")
            if not fname:
                continue
            media = str(part.get("mimeType", ""))
            body = part.get("body", {})
            if not _wanted(fname, media):
                skipped.append(f"{fname}: not a PDF or Word file")
                continue
            if int(body.get("size", 0)) > max_bytes:
                skipped.append(f"{fname}: larger than the limit")
                continue
            if "attachmentId" in body:
                data = await self._get(f"/messages/{message_id}/attachments/{body['attachmentId']}")
                raw = str(data.get("data", ""))
            else:
                raw = str(body.get("data", ""))
            atts.append(
                Attachment(fname, media, base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
            )
        received = None
        if m.get("internalDate"):
            received = datetime.fromtimestamp(int(m["internalDate"]) / 1000, tz=UTC)
        elif headers.get("date"):
            try:
                received = parsedate_to_datetime(headers["date"])
            except (TypeError, ValueError):
                received = None
        return RawEmail(
            id=message_id,
            subject=headers.get("subject", ""),
            sender_name=name,
            sender_address=addr,
            to=[a for a in to if a],
            received_at=received,
            attachments=atts,
            skipped=skipped,
        )


def _parts(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    yield payload
    for p in payload.get("parts", []) or []:
        yield from _parts(p)


# ---- fake (tests) ------------------------------------------------------------------------------


class FakeMailbox:
    name = "fake"

    def __init__(self) -> None:
        self.messages: dict[str, tuple[str, RawEmail]] = {}  # id -> (label, email)
        self.fail_auth = False
        self.fail_next = 0
        self.fetches = 0

    def add(self, label: str, email: RawEmail) -> None:
        self.messages[email.id] = (label, email)

    async def labels(self) -> list[str]:
        return sorted({lbl for lbl, _ in self.messages.values()} | {"Applications"})

    async def list_new(
        self, label: str, checkpoint: str | None, limit: int
    ) -> tuple[list[str], str | None]:
        if self.fail_auth:
            raise ProviderAuthError("revoked")
        if self.fail_next:
            self.fail_next -= 1
            raise ProviderError("temporary failure")
        return [i for i, (lbl, _) in self.messages.items() if lbl == label][:limit], checkpoint

    async def fetch(self, message_id: str, max_bytes: int) -> RawEmail:
        self.fetches += 1
        return self.messages[message_id][1]
