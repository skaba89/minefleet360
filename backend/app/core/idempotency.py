"""Idempotence transactionnelle des commandes rejouées après une coupure réseau (D-14).

Le corps de requête n'est jamais conservé : seule son empreinte SHA-256 est persistée. L'appelant doit
finaliser l'enregistrement et la mutation métier dans la même transaction, puis reconstruire un rejeu en
relisant la ressource référencée.
"""

import hashlib
import hmac
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import Header
from sqlalchemy import DateTime, LargeBinary, SmallInteger, String, select, update
from sqlalchemy.dialects.postgresql import UUID, insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.config import get_settings
from app.core.db import Base
from app.core.errors import AppError

_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_METHODS = frozenset({"POST", "PUT", "PATCH"})


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_record"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String, primary_key=True)
    request_method: Mapped[str] = mapped_column(String, nullable=False)
    request_path: Mapped[str] = mapped_column(String, nullable=False)
    request_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False, default="IN_PROGRESS")
    response_status: Mapped[int | None] = mapped_column(SmallInteger)
    resource_type: Mapped[str | None] = mapped_column(String)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass(frozen=True)
class ReplayReference:
    response_status: int
    resource_type: str
    resource_id: uuid.UUID


@dataclass(frozen=True)
class IdempotencyClaim:
    tenant_id: uuid.UUID
    user_account_id: uuid.UUID
    key: str
    request_hash: bytes
    replay: ReplayReference | None

    @property
    def is_replay(self) -> bool:
        return self.replay is not None


def validate_idempotency_key(value: str) -> str:
    if not _KEY.fullmatch(value):
        raise AppError(
            "VALIDATION_ERROR",
            details=[{"field": "Idempotency-Key", "type": "format"}],
        )
    return value


def optional_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str | None:
    return validate_idempotency_key(idempotency_key) if idempotency_key is not None else None


def request_fingerprint(method: str, path: str, body: bytes) -> bytes:
    normalized_method = method.upper()
    if normalized_method not in _METHODS or not path.startswith("/") or len(path) > 300:
        raise ValueError("méthode ou chemin non pris en charge pour l'idempotence")
    digest = hashlib.sha256()
    digest.update(normalized_method.encode("ascii"))
    digest.update(b"\0")
    digest.update(path.encode("utf-8"))
    digest.update(b"\0")
    digest.update(body)
    return digest.digest()


def claim(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_account_id: uuid.UUID,
    key: str,
    method: str,
    path: str,
    body: bytes,
    now: datetime,
    ttl: timedelta | None = None,
) -> IdempotencyClaim:
    """Réserver une clé ou renvoyer la référence déjà finalisée.

    L'insertion concurrente attend la transaction propriétaire. Si celle-ci échoue et est annulée, un
    autre worker devient propriétaire ; si elle réussit, les autres obtiennent la référence de rejeu.
    """
    safe_key = validate_idempotency_key(key)
    normalized_method = method.upper()
    fingerprint = request_fingerprint(normalized_method, path, body)
    expires_at = now + (ttl or get_settings().idempotency_ttl)
    statement = (
        insert(IdempotencyRecord)
        .values(
            tenant_id=tenant_id,
            user_account_id=user_account_id,
            idempotency_key=safe_key,
            request_method=normalized_method,
            request_path=path,
            request_hash=fingerprint,
            state="IN_PROGRESS",
            created_at=now,
            expires_at=expires_at,
        )
        .on_conflict_do_nothing(constraint="pk_idempotency_record")
        .returning(IdempotencyRecord.idempotency_key)
    )
    if db.execute(statement).scalar_one_or_none() is not None:
        return IdempotencyClaim(tenant_id, user_account_id, safe_key, fingerprint, None)

    existing = db.execute(
        select(IdempotencyRecord).where(
            IdempotencyRecord.tenant_id == tenant_id,
            IdempotencyRecord.user_account_id == user_account_id,
            IdempotencyRecord.idempotency_key == safe_key,
        )
    ).scalar_one()
    same_request = (
        existing.request_method == normalized_method
        and existing.request_path == path
        and hmac.compare_digest(bytes(existing.request_hash), fingerprint)
    )
    if not same_request:
        raise AppError("IDEMPOTENCY_KEY_REUSED")
    if existing.state != "COMPLETED":
        raise AppError("IDEMPOTENCY_IN_PROGRESS", headers={"Retry-After": "2"})
    assert existing.response_status is not None
    assert existing.resource_type is not None
    assert existing.resource_id is not None
    return IdempotencyClaim(
        tenant_id,
        user_account_id,
        safe_key,
        fingerprint,
        ReplayReference(existing.response_status, existing.resource_type, existing.resource_id),
    )


def complete(
    db: Session,
    claim_record: IdempotencyClaim,
    *,
    response_status: int,
    resource_type: str,
    resource_id: uuid.UUID,
    completed_at: datetime,
) -> None:
    """Finaliser la clé dans la transaction qui contient déjà la mutation métier."""
    if claim_record.is_replay or not 200 <= response_status <= 299:
        raise ValueError("seule une nouvelle commande réussie peut être finalisée")
    result = db.execute(
        update(IdempotencyRecord)
        .where(
            IdempotencyRecord.tenant_id == claim_record.tenant_id,
            IdempotencyRecord.user_account_id == claim_record.user_account_id,
            IdempotencyRecord.idempotency_key == claim_record.key,
            IdempotencyRecord.request_hash == claim_record.request_hash,
            IdempotencyRecord.state == "IN_PROGRESS",
        )
        .values(
            state="COMPLETED",
            response_status=response_status,
            resource_type=resource_type,
            resource_id=resource_id,
            completed_at=completed_at,
        )
    )
    if int(getattr(result, "rowcount", 0) or 0) != 1:
        raise AppError("IDEMPOTENCY_IN_PROGRESS", headers={"Retry-After": "2"})
