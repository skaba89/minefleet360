import uuid
from datetime import datetime

from sqlalchemy import ARRAY, BigInteger, Boolean, DateTime, FetchedValue, Integer, LargeBinary, String, text
from sqlalchemy.dialects.postgresql import CITEXT, INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import AuditedColumns


class Role(Base):
    __tablename__ = "role"

    role_code: Mapped[str] = mapped_column(String, primary_key=True)
    label_fr: Mapped[str] = mapped_column(String, nullable=False)
    description_fr: Mapped[str | None] = mapped_column(String)
    is_optional: Mapped[bool] = mapped_column(Boolean, nullable=False)


class RoleAllowedScope(Base):
    __tablename__ = "role_allowed_scope"

    role_code: Mapped[str] = mapped_column(String, primary_key=True)
    scope_type: Mapped[str] = mapped_column(String, primary_key=True)


class UserAccount(AuditedColumns, Base):
    __tablename__ = "user_account"
    __mapper_args__ = {"eager_defaults": True}

    user_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    phone: Mapped[str | None] = mapped_column(String)
    password_hash: Mapped[str | None] = mapped_column(String)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # Secrets TOTP toujours chiffrés (app.core.secretbox) ; codes de récupération hachés (app.core.totp).
    mfa_secret_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    mfa_pending_secret_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    mfa_pending_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_last_step: Mapped[int | None] = mapped_column(BigInteger)
    mfa_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_recovery_hashes: Mapped[list[bytes]] = mapped_column(
        ARRAY(LargeBinary), nullable=False, server_default=text("'{}'::bytea[]")
    )
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="INVITED")
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    ui_locale: Mapped[str] = mapped_column(String, nullable=False, server_default="fr-GN")
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserRoleAssignment(Base):
    __tablename__ = "user_role_assignment"
    __mapper_args__ = {"eager_defaults": True}

    user_role_assignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tenant_kind: Mapped[str] = mapped_column(String, nullable=False)
    user_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role_code: Mapped[str] = mapped_column(String, nullable=False)
    scope_type: Mapped[str] = mapped_column(String, nullable=False)
    site_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    granted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), server_onupdate=FetchedValue(), nullable=False
    )
    row_version: Mapped[int] = mapped_column(
        Integer, server_default=text("1"), server_onupdate=FetchedValue(), nullable=False
    )


class AccountToken(Base):
    __tablename__ = "account_token"

    account_token_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    purpose: Mapped[str] = mapped_column(String, nullable=False)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class AuthSession(Base):
    __tablename__ = "auth_session"

    auth_session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    refresh_hash_current: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    refresh_hash_previous: Mapped[bytes | None] = mapped_column(LargeBinary)
    consumed_refresh_hashes: Mapped[list[bytes]] = mapped_column(
        ARRAY(LargeBinary), nullable=False, server_default=text("'{}'::bytea[]")
    )
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    amr: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, server_default=text("'{pwd}'"))
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String)
