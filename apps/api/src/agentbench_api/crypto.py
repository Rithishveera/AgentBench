"""Fernet encryption for registered-agent secrets."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet
from pydantic import SecretStr


def _key(value: str | SecretStr | None) -> bytes:
    if value is None:
        value = os.environ.get("ENCRYPTION_KEY")
        if value is None:
            raise ValueError("ENCRYPTION_KEY must be configured")
    if isinstance(value, SecretStr):
        value = value.get_secret_value()
    return value.encode("ascii")


def encrypt_agent_secret(
    secret: str,
    encryption_key: str | SecretStr | None = None,
) -> str:
    return Fernet(_key(encryption_key)).encrypt(secret.encode("utf-8")).decode("ascii")


def decrypt_agent_secret(
    encrypted_secret: str,
    encryption_key: str | SecretStr | None = None,
) -> str:
    return (
        Fernet(_key(encryption_key))
        .decrypt(encrypted_secret.encode("ascii"))
        .decode("utf-8")
    )
