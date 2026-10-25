"""Dépendances FastAPI d'authentification et d'autorisation (ordre D-05a : 401 → 403 → 404 …).

Chaque route protégée déclare exactement une dépendance `Require("module.ressource.action")` ;
le test d'inventaire (ST-01) vérifie la concordance route ↔ authz_matrix.yaml.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.contracts import record_detached
from app.authz.matrix import load_matrix
from app.authz.principal import Grant, PermissionScope, Principal, evaluate
from app.core.clock import Clock
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.errors import AppError
from app.core.security import decode_access_token
from app.core.tenancy import set_tenant_context
from app.identity.models import AuthSession, UserAccount, UserRoleAssignment
from app.organization.models import Tenant


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock


DbSession = Annotated[Session, Depends(get_db)]
ClockDep = Annotated[Clock, Depends(get_clock)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def load_grants(db: Session, user_id: uuid.UUID, clock: Clock) -> tuple[Grant, ...]:
    now = clock.now()
    rows = db.execute(
        select(UserRoleAssignment.role_code, UserRoleAssignment.scope_type, UserRoleAssignment.site_id).where(
            UserRoleAssignment.user_account_id == user_id,
            UserRoleAssignment.revoked_at.is_(None),
            UserRoleAssignment.valid_from <= now,
            (UserRoleAssignment.valid_to.is_(None)) | (UserRoleAssignment.valid_to > now),
        )
    ).all()
    return tuple(Grant(r.role_code, r.scope_type, r.site_id) for r in rows)


def authenticate(
    db: DbSession,
    clock: ClockDep,
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    """401 identique quelle que soit la cause (jeton absent, invalide, expiré, session révoquée…)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError("AUTH_REQUIRED")
    claims = decode_access_token(authorization.removeprefix("Bearer ").strip(), clock.now(), settings)
    if claims is None:
        raise AppError("AUTH_REQUIRED")
    set_tenant_context(db, claims.tenant_id)
    now = clock.now()
    row = db.execute(
        select(AuthSession.auth_session_id, Tenant.kind)
        .join(UserAccount, UserAccount.user_account_id == AuthSession.user_account_id)
        .join(Tenant, Tenant.tenant_id == AuthSession.tenant_id)
        .where(
            AuthSession.auth_session_id == claims.session_id,
            AuthSession.user_account_id == claims.user_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
            UserAccount.status == "ACTIVE",
            Tenant.status == "ACTIVE",
        )
    ).first()
    if row is None:
        raise AppError("AUTH_REQUIRED")
    return Principal(
        user_id=claims.user_id,
        tenant_id=claims.tenant_id,
        tenant_kind=row.kind,
        session_id=claims.session_id,
        grants=load_grants(db, claims.user_id, clock),
    )


@dataclass(frozen=True)
class Authorized:
    principal: Principal
    scope: PermissionScope
    db: Session
    clock: Clock

    @property
    def tenant_id(self) -> uuid.UUID:
        return self.principal.tenant_id

    @property
    def user_id(self) -> uuid.UUID:
        return self.principal.user_id


class Require:
    """Dépendance d'autorisation : 403 audité si aucune attribution active ne porte la permission."""

    def __init__(self, permission: str) -> None:
        if permission not in load_matrix().permissions:
            raise ValueError(f"Permission absente de authz_matrix.yaml : {permission}")
        self.permission = permission

    def __call__(
        self,
        principal: Annotated[Principal, Depends(authenticate)],
        db: DbSession,
        clock: ClockDep,
    ) -> Authorized:
        scope = evaluate(principal, self.permission)
        if scope is None:
            record_detached(
                tenant_id=principal.tenant_id,
                action=self.permission,
                entity_type=self.permission.split(".")[1],
                actor_user_id=principal.user_id,
                outcome="DENIED",
                reason="PERMISSION_DENIED",
            )
            raise AppError("PERMISSION_DENIED")
        return Authorized(principal, scope, db, clock)

    def __repr__(self) -> str:
        return f"Require({self.permission!r})"


def security_denial(auth: Authorized, *, action: str, entity_type: str, reason: str) -> None:
    """Refus de sécurité 422 (auto-escalade, rôle non attribuable) : audité hors transaction métier."""
    record_detached(
        tenant_id=auth.tenant_id,
        action=action,
        entity_type=entity_type,
        actor_user_id=auth.user_id,
        outcome="DENIED",
        reason=reason,
    )
