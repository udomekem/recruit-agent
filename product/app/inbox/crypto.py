"""Encryption for stored mailbox tokens (phase 5B design section 2). Fernet: AES with an
authentication tag, so a changed ciphertext fails to decrypt instead of giving junk."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings


class TokenKeyMissing(RuntimeError):
    pass


def _fernet(settings: Settings) -> Fernet:
    if settings.inbox_token_key is None:
        raise TokenKeyMissing("INBOX_TOKEN_KEY is not set (run make local-env)")
    return Fernet(settings.inbox_token_key.get_secret_value().encode())


def encrypt_token(settings: Settings, token: str) -> bytes:
    return _fernet(settings).encrypt(token.encode())


def decrypt_token(settings: Settings, ciphertext: bytes) -> str:
    try:
        return _fernet(settings).decrypt(ciphertext).decode()
    except InvalidToken as exc:
        raise TokenKeyMissing("the stored token cannot be read with this key") from exc
