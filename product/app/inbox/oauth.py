"""Connecting Gmail (phase 5B design section 5): OAuth authorization code flow with PKCE.

- The `state` value is one time, bound to the recruiter who started, and expires in 10
  minutes; a missing, reused, expired or foreign state is refused.
- Scope `gmail.readonly` only; a grant with any other scope list is refused and revoked.
- The refresh token is encrypted before it is stored; nothing logs or traces it.
- Disconnect revokes the token at Google and deletes it.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.config import Settings
from app.db.models import Mailbox, MailboxEvent, OAuthState
from app.db.session import SessionMaker
from app.inbox.crypto import encrypt_token
from app.inbox.providers import GMAIL_API, GMAIL_SCOPE, GOOGLE_TOKEN_URL

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
STATE_TTL = timedelta(minutes=10)


class ConnectRefused(Exception):
    """The connect flow cannot finish (400 with a reason the recruiter can act on)."""


def gmail_configured(settings: Settings) -> bool:
    return bool(
        settings.google_client_id and settings.google_client_secret and settings.inbox_token_key
    )


async def start_gmail(sessions: SessionMaker, settings: Settings, actor_id: str) -> str:
    if not gmail_configured(settings):
        raise ConnectRefused("Gmail is not set up yet: add the Google OAuth client to .env")
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    async with sessions() as s, s.begin():
        s.add(OAuthState(state=state, provider="gmail", code_verifier=verifier, actor_id=actor_id))
    return (
        AUTH_URL
        + "?"
        + urlencode(
            {
                "client_id": settings.google_client_id,
                "redirect_uri": settings.google_redirect_uri,
                "response_type": "code",
                "scope": GMAIL_SCOPE,
                "access_type": "offline",
                "prompt": "consent",
                "include_granted_scopes": "false",
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
    )


async def finish_gmail(
    sessions: SessionMaker,
    settings: Settings,
    *,
    actor_id: str,
    code: str,
    state: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Mailbox:
    now = datetime.now(UTC)
    async with sessions() as s, s.begin():
        row = await s.get(OAuthState, state, with_for_update=True)
        if row is None or row.provider != "gmail":
            raise ConnectRefused("this sign in link is not one we started; start again")
        if row.used_at is not None:
            raise ConnectRefused("this sign in link was already used; start again")
        if row.actor_id != actor_id:
            raise ConnectRefused("this sign in was started by someone else; start again")
        if now - row.created_at > STATE_TTL:
            raise ConnectRefused("the sign in took too long; start again")
        row.used_at = now
        verifier = row.code_verifier
    assert settings.google_client_secret is not None
    async with httpx.AsyncClient(timeout=15, transport=transport) as c:
        r = await c.post(
            GOOGLE_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret.get_secret_value(),
                "redirect_uri": settings.google_redirect_uri,
                "code_verifier": verifier,
            },
        )
        if r.status_code >= 400:
            raise ConnectRefused("Google did not accept the sign in; start again")
        body = r.json()
        refresh = body.get("refresh_token")
        granted = set(str(body.get("scope", "")).split())
        if granted != {GMAIL_SCOPE}:
            await _revoke(c, str(refresh or body.get("access_token", "")))
            raise ConnectRefused(
                "only read only Gmail access may be granted; nothing was connected"
            )
        if not refresh:
            raise ConnectRefused(
                "Google sent no lasting access; remove the app in your Google "
                "account and start again"
            )
        p = await c.get(
            f"{GMAIL_API}/profile", headers={"Authorization": f"Bearer {body['access_token']}"}
        )
        if p.status_code >= 400:
            await _revoke(c, str(refresh))
            raise ConnectRefused("could not read the mailbox address; nothing was connected")
        address = str(p.json().get("emailAddress", ""))
    async with sessions() as s, s.begin():
        mb = Mailbox(
            provider="gmail",
            address=address,
            label=None,
            status="needs_label",
            token_ciphertext=encrypt_token(settings, str(refresh)),
            scopes=[GMAIL_SCOPE],
            connected_by=actor_id,
        )
        s.add(mb)
        await s.flush()
        s.add(
            MailboxEvent(
                mailbox_id=mb.id, kind="connect", actor_id=actor_id, detail="gmail, read only"
            )
        )
    return mb


async def _revoke(c: httpx.AsyncClient, token: str) -> bool:
    if not token:
        return False
    try:
        r = await c.post(REVOKE_URL, data={"token": token})
        return r.status_code < 400
    except httpx.HTTPError:
        return False


async def revoke(token: str, transport: httpx.AsyncBaseTransport | None = None) -> bool:
    async with httpx.AsyncClient(timeout=10, transport=transport) as c:
        for _ in range(2):
            if await _revoke(c, token):
                return True
    return False
