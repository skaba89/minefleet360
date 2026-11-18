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


def _decode(raw: str, name: str) -> bytes:
    raw = raw.strip()
    key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    if len(key) != 32:
        raise RuntimeError(f"{name} doit contenir 32 octets encodés en base64url")
    return key


def _previous_key(settings: Settings) -> bytes | None:
    """Ancienne clé pendant une rotation : jamais utilisée pour chiffrer, seulement pour relire."""
    if settings.mfa_encryption_key_previous is None:
        return None
    if settings.mfa_encryption_key is None:
        raise RuntimeError("MF_MFA_ENCRYPTION_KEY_PREVIOUS sans MF_MFA_ENCRYPTION_KEY")
    previous = _decode(
        settings.mfa_encryption_key_previous.get_secret_value(), "MF_MFA_ENCRYPTION_KEY_PREVIOUS"
    )
    if hmac.compare_digest(previous, _key(settings)):
        raise RuntimeError("MF_MFA_ENCRYPTION_KEY_PREVIOUS identique à la clé courante")
    return previous


def _key(settings: Settings) -> bytes:
    if settings.mfa_encryption_key is not None:
        return _decode(settings.mfa_encryption_key.get_secret_value(), "MF_MFA_ENCRYPTION_KEY")
    if settings.env in ("staging", "production"):
        raise RuntimeError("MF_MFA_ENCRYPTION_KEY manquant")
    # Développement et tests uniquement : clé dérivée, jamais utilisée sur un serveur (validation Settings).
    return hmac.new(
        settings.jwt_secret.get_secret_value().encode(), b"minefleet-mfa-dev", hashlib.sha256
    ).digest()


def _derive_with(key: bytes, label: str) -> bytes:
    return hmac.new(key, f"minefleet:{label}".encode(), hashlib.sha256).digest()


def derive(label: str, settings: Settings) -> bytes:
    """Sous-clé dédiée à un usage (ex. poivre des codes de récupération), jamais la clé elle-même."""
    return _derive_with(_key(settings), label)


def derive_all(label: str, settings: Settings) -> list[bytes]:
    """Sous-clés acceptées en vérification : courante d'abord, puis celle de l'ancienne clé (rotation)."""
    previous = _previous_key(settings)
    keys = [derive(label, settings)]
    if previous is not None:
        keys.append(_derive_with(previous, label))
    return keys


def seal(plaintext: bytes, *, context: str, settings: Settings) -> bytes:
    nonce = os.urandom(12)
    return _VERSION + nonce + AESGCM(_key(settings)).encrypt(nonce, plaintext, context.encode())


def _open_with(key: bytes, sealed: bytes, context: str) -> bytes | None:
    if len(sealed) < 1 + 12 + 16 or sealed[:1] != _VERSION:
        return None
    try:
        return AESGCM(key).decrypt(sealed[1:13], sealed[13:], context.encode())
    except InvalidTag:
        return None


def open_sealed(sealed: bytes, *, context: str, settings: Settings) -> bytes | None:
    """None si la valeur est altérée, d'une autre version ou d'un autre contexte.

    Pendant une rotation, une valeur encore chiffrée par l'ancienne clé reste lisible.
    """
    plaintext = _open_with(_key(settings), sealed, context)
    if plaintext is None:
        previous = _previous_key(settings)
        if previous is not None:
            plaintext = _open_with(previous, sealed, context)
    return plaintext


def reseal(sealed: bytes, *, context: str, settings: Settings) -> tuple[bytes | None, str]:
    """Rotation : (nouvelle valeur, état). États : « current » (déjà sous la clé courante, inchangée),
    « resealed » (relue par l'ancienne clé, rechiffrée), « unreadable » (aucune clé ne l'ouvre)."""
    if _open_with(_key(settings), sealed, context) is not None:
        return sealed, "current"
    previous = _previous_key(settings)
    plaintext = _open_with(previous, sealed, context) if previous is not None else None
    if plaintext is None:
        return None, "unreadable"
    return seal(plaintext, context=context, settings=settings), "resealed"
