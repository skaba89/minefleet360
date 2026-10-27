"""Mots de passe à usage unique temporels (TOTP, RFC 6238 / RFC 4226) et codes de récupération.

Paramètres compatibles avec les applications d'authentification courantes : HMAC-SHA1, 6 chiffres,
pas de 30 s. Tolérance d'un pas de part et d'autre (dérive d'horloge du téléphone, CLAUDE.md) ; un pas
déjà accepté est refusé ensuite (anti-rejeu).
"""

import base64
import hashlib
import hmac
import secrets
import struct
from datetime import datetime
from urllib.parse import quote

STEP_SECONDS = 30
DIGITS = 6
WINDOW = 1
RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sans 0/O ni 1/I : dictée et saisie sur terrain


def new_secret() -> bytes:
    return secrets.token_bytes(20)  # 160 bits (RFC 4226 §4)


def to_base32(secret: bytes) -> str:
    return base64.b32encode(secret).decode().rstrip("=")


def step_at(instant: datetime) -> int:
    return int(instant.timestamp()) // STEP_SECONDS


def code_at(secret: bytes, step: int) -> str:
    digest = hmac.new(secret, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def verify(secret: bytes, code: str, now: datetime, *, last_step: int | None) -> int | None:
    """Renvoie le pas accepté, ou None. Chaque pas candidat est comparé en temps constant."""
    code = code.strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return None
    current = step_at(now)
    accepted: int | None = None
    for step in range(current - WINDOW, current + WINDOW + 1):
        if hmac.compare_digest(code_at(secret, step), code) and (last_step is None or step > last_step):
            accepted = step
    return accepted


def provisioning_uri(secret: bytes, *, account: str, issuer: str) -> str:
    label = quote(f"{issuer}:{account}")
    return (
        f"otpauth://totp/{label}?secret={to_base32(secret)}&issuer={quote(issuer)}"
        f"&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}"
    )


# --- Codes de récupération ------------------------------------------------------------------------------


def new_recovery_codes(count: int = 10) -> list[str]:
    def one() -> str:
        raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(10))  # ≈ 50 bits
        return f"{raw[:5]}-{raw[5:]}"

    return [one() for _ in range(count)]


def normalize_recovery_code(code: str) -> str:
    return code.strip().upper().replace("-", "").replace(" ", "")


def hash_recovery_code(code: str) -> bytes:
    """Empreinte stockée (codes à forte entropie, usage unique) : jamais le code en clair."""
    return hashlib.sha256(normalize_recovery_code(code).encode()).digest()


def looks_like_recovery_code(code: str) -> bool:
    normalized = normalize_recovery_code(code)
    return len(normalized) == 10 and all(c in RECOVERY_ALPHABET for c in normalized)
