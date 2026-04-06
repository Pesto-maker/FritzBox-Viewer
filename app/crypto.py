"""
Symmetric encryption for secrets stored in the database.

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the `cryptography` package.
The encryption key is derived deterministically from the current OS user
and machine name via PBKDF2-HMAC-SHA256, so no separate key file is
needed — but the encrypted values are only readable on the same
machine by the same user.
"""

import base64
import hashlib
import os
import platform

from cryptography.fernet import Fernet, InvalidToken

_SALT = b"FritzBox-Viewer-v1"          # static app salt

# Keys that must be stored encrypted
SECRET_KEYS = frozenset({"fritz_password", "anthropic_api_key"})


def _derive_key() -> bytes:
    """Derive a Fernet key from machine identity (hostname + OS username)."""
    identity = f"{platform.node()}|{os.getlogin()}".encode()
    dk = hashlib.pbkdf2_hmac("sha256", identity, _SALT, iterations=480_000)
    return base64.urlsafe_b64encode(dk)


_fernet = Fernet(_derive_key())


def encrypt(plaintext: str) -> str:
    """Encrypt a string and return the Fernet token as UTF-8 string."""
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a Fernet token back to the original string.

    Returns the token unchanged if decryption fails (e.g. the value
    is still stored as plaintext from before the migration).
    """
    try:
        return _fernet.decrypt(token.encode()).decode()
    except (InvalidToken, Exception):
        return token
