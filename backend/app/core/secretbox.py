"""Chiffrement authentifié (AES-256-GCM) des secrets stockés en base, notamment les secrets TOTP.

Le texte chiffré est lié à son propriétaire par des données associées (tenant, compte, usage) : une
valeur recopiée sur un autre compte ne se déchiffre pas. Format : version (1 octet) | nonce (12) | chiffré.
"""

import base64
import hashlib
import hmac
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings

_VERSION = b"\x01"


def _key(settings: Settings) -> bytes:
    if settings.mfa_encryption_key is not None:
        raw = settings.mfa_encryption_key.get_secret_value().strip()
        key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        if len(key) != 32:
            raise RuntimeError("MF_MFA_ENCRYPTION_KEY doit contenir 32 octets encodés en base64url")
        return key
    if settings.env in ("staging", "production"):
        raise RuntimeError("MF_MFA_ENCRYPTION_KEY manquant")
    # Développement et tests uniquement : clé dérivée, jamais utilisée sur un serveur (validation Settings).
    return hmac.new(
        settings.jwt_secret.get_secret_value().encode(), b"minefleet-mfa-dev", hashlib.sha256
    ).digest()


def derive(label: str, settings: Settings) -> bytes:
    """Sous-clé dédiée à un usage (ex. poivre des codes de récupération), jamais la clé elle-même."""
    return hmac.new(_key(settings), f"minefleet:{label}".encode(), hashlib.sha256).digest()


def seal(plaintext: bytes, *, context: str, settings: Settings) -> bytes:
    nonce = os.urandom(12)
    return _VERSION + nonce + AESGCM(_key(settings)).encrypt(nonce, plaintext, context.encode())


def open_sealed(sealed: bytes, *, context: str, settings: Settings) -> bytes | None:
    """None si la valeur est altérée, d'une autre version ou d'un autre contexte."""
    if len(sealed) < 1 + 12 + 16 or sealed[:1] != _VERSION:
        return None
    try:
        return AESGCM(_key(settings)).decrypt(sealed[1:13], sealed[13:], context.encode())
    except InvalidTag:
        return None
