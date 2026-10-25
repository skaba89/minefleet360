"""Primitives cryptographiques : mots de passe (argon2id), jetons opaques, JWT d'accès (ADR-003)."""

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings
from app.core.errors import AppError

# Paramètres par défaut de argon2-cffi (argon2id) ; calibrage sur l'environnement cible : ADR-003 §3.1.
_hasher = PasswordHasher()
# Hachage factice : coût comparable quand le compte est inconnu (pas d'oracle temporel d'existence).
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def burn_password_check(password: str) -> None:
    verify_password(None, password)


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def check_password_policy(password: str, settings: Settings, *, email: str | None = None) -> None:
    rules: list[str] = []
    if len(password) < settings.password_min_length:
        rules.append(f"Au moins {settings.password_min_length} caractères.")
    if len(password) > settings.password_max_length:
        rules.append(f"Au plus {settings.password_max_length} caractères.")
    if email and password.strip().lower() == email.strip().lower():
        rules.append("Le mot de passe ne doit pas être l'adresse e-mail.")
    if password.strip() != password or not password.strip():
        rules.append("Pas d'espace au début ni à la fin.")
    if rules:
        raise AppError("PASSWORD_POLICY_VIOLATION", details={"rules": rules})


# --- Jetons opaques composés « <tenant_id>.<id>.<secret> » (MODELE_PHYSIQUE §6.2) -----------------


@dataclass(frozen=True)
class CompositeToken:
    tenant_id: uuid.UUID
    record_id: uuid.UUID
    secret: str

    def encode(self) -> str:
        return f"{self.tenant_id}.{self.record_id}.{self.secret}"

    @property
    def secret_hash(self) -> bytes:
        return sha256(self.secret)


def new_secret() -> str:
    return secrets.token_urlsafe(32)  # 256 bits


def sha256(value: str) -> bytes:
    return hashlib.sha256(value.encode()).digest()


def constant_time_equals(a: bytes, b: bytes) -> bool:
    return hmac.compare_digest(a, b)


def parse_composite_token(raw: str | None) -> CompositeToken | None:
    if not raw or len(raw) > 200:
        return None
    parts = raw.split(".")
    if len(parts) != 3 or not parts[2]:
        return None
    try:
        return CompositeToken(uuid.UUID(parts[0]), uuid.UUID(parts[1]), parts[2])
    except ValueError:
        return None


# --- JWT d'accès court ------------------------------------------------------------------------------


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    session_id: uuid.UUID


def issue_access_token(claims: AccessClaims, now: datetime, settings: Settings) -> str:
    payload = {
        "sub": str(claims.user_id),
        "tid": str(claims.tenant_id),
        "sid": str(claims.session_id),
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + settings.access_token_ttl).timestamp()),
        "typ": "access",
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, now: datetime, settings: Settings) -> AccessClaims | None:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "tid", "sid", "exp", "iat"], "verify_exp": False},
        )
    except jwt.PyJWTError:
        return None
    # Expiration vérifiée avec l'horloge injectable (testable), pas l'horloge système de PyJWT.
    if payload.get("typ") != "access" or int(payload["exp"]) <= int(now.timestamp()):
        return None
    try:
        return AccessClaims(uuid.UUID(payload["sub"]), uuid.UUID(payload["tid"]), uuid.UUID(payload["sid"]))
    except (ValueError, TypeError):
        return None
