"""Services identité : utilisateurs, attributions de rôle, protections anti-escalade (MATRICE_RBAC §4.2)."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.contracts import record
from app.authz.dependencies import Authorized, security_denial
from app.authz.matrix import load_matrix
from app.authz.principal import PermissionScope, masked_fields
from app.core.config import Settings
from app.core.email import EmailMessage
from app.core.errors import AppError
from app.core.http import PageParams, check_version
from app.core.logging import security_logger
from app.identity.contracts import (
    create_invited_user,
    invitation_message,
    issue_account_token,
    reset_message,
    revoke_open_tokens,
    revoke_sessions,
)
from app.identity.models import Role, RoleAllowedScope, UserAccount, UserRoleAssignment
from app.identity.schemas import RoleAssignmentCreate, RoleOut, UserInvite, UserOut, UserUpdate
from app.organization.models import Site, Tenant

HIGH_CRITICALITY_ROLES = frozenset({"TENANT_ADMIN", "HR"})


def user_out(user: UserAccount, scope: PermissionScope) -> UserOut:
    hidden = masked_fields("user_account", scope)
    data: dict[str, Any] = {
        "user_account_id": user.user_account_id,
        "display_name": user.display_name,
        "status": user.status,
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
        "row_version": user.row_version,
    }
    if "email" not in hidden:
        data["email"] = user.email
    if "phone" not in hidden and user.phone is not None:
        data["phone"] = user.phone
    return UserOut(**data)  # champs masqués non définis → exclus de la réponse (exclude_unset)


def _user_or_404(db: Session, user_id: uuid.UUID, *, for_update: bool = False) -> UserAccount:
    stmt = select(UserAccount).where(UserAccount.user_account_id == user_id)
    if for_update:
        stmt = stmt.with_for_update(key_share=True)
    user = db.execute(stmt).scalar_one_or_none()
    if user is None:
        security_logger.info(
            "item_not_found", extra={"entity_type": "user_account", "entity_id": str(user_id)}
        )
        raise AppError("NOT_FOUND")
    return user


def _tenant(db: Session, tenant_id: uuid.UUID, *, lock: bool = False) -> Tenant:
    stmt = select(Tenant).where(Tenant.tenant_id == tenant_id)
    if lock:
        stmt = stmt.with_for_update(
            key_share=True
        )  # point de sérialisation des changements d'administrateurs
    return db.execute(stmt).scalar_one()


def _active_admin_count(
    auth: Authorized,
    *,
    excluding_user: uuid.UUID | None = None,
    excluding_assignment: uuid.UUID | None = None,
) -> int:
    now = auth.clock.now()
    stmt = (
        select(func.count(func.distinct(UserRoleAssignment.user_account_id)))
        .join(UserAccount, UserAccount.user_account_id == UserRoleAssignment.user_account_id)
        .where(
            UserRoleAssignment.role_code == "TENANT_ADMIN",
            UserRoleAssignment.revoked_at.is_(None),
            UserRoleAssignment.valid_from <= now,
            (UserRoleAssignment.valid_to.is_(None)) | (UserRoleAssignment.valid_to > now),
            UserAccount.status == "ACTIVE",
        )
    )
    if excluding_user is not None:
        stmt = stmt.where(UserRoleAssignment.user_account_id != excluding_user)
    if excluding_assignment is not None:
        stmt = stmt.where(UserRoleAssignment.user_role_assignment_id != excluding_assignment)
    return int(auth.db.execute(stmt).scalar_one())


def _ensure_not_last_admin(
    auth: Authorized,
    *,
    excluding_user: uuid.UUID | None = None,
    excluding_assignment: uuid.UUID | None = None,
) -> None:
    """US-1.31 A2-A4 : verrou sur la ligne tenant puis recomptage (retraits simultanés : un seul passe)."""
    _tenant(auth.db, auth.tenant_id, lock=True)
    before = _active_admin_count(auth)
    after = _active_admin_count(
        auth, excluding_user=excluding_user, excluding_assignment=excluding_assignment
    )
    if before > 0 and after == 0:
        raise AppError("LAST_TENANT_ADMIN")


def _check_role_and_scope(
    auth: Authorized, role_code: str, scope_type: str, site_id: uuid.UUID | None
) -> None:
    matrix = load_matrix()
    role = matrix.roles.get(role_code)
    if role is None or not role.assignable_by_tenant or role.tenant_kind != auth.principal.tenant_kind:
        security_denial(
            auth,
            action="role_assignment.create",
            entity_type="user_role_assignment",
            reason="ROLE_NOT_ASSIGNABLE",
        )
        raise AppError("ROLE_NOT_ASSIGNABLE")
    if scope_type not in role.allowed_scopes:
        raise AppError("SCOPE_NOT_ALLOWED_FOR_ROLE")
    if (scope_type == "SITE") != (site_id is not None):
        raise AppError("VALIDATION_ERROR", details=[{"field": "site_id", "type": "scope_mismatch"}])
    if site_id is not None and auth.db.get(Site, site_id) is None:
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "site_id"}])


# --- Utilisateurs -------------------------------------------------------------------------------------


def list_users(auth: Authorized, page: PageParams, status: str | None) -> tuple[list[UserAccount], int]:
    stmt = select(UserAccount)
    if status is not None:
        stmt = stmt.where(UserAccount.status == status)
    total = auth.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = auth.db.execute(
        stmt.order_by(UserAccount.display_name, UserAccount.user_account_id)
        .offset(page.offset)
        .limit(page.page_size)
    )
    return list(rows.scalars()), total


def get_user(auth: Authorized, user_id: uuid.UUID) -> UserAccount:
    return _user_or_404(auth.db, user_id)


def invite_user(auth: Authorized, body: UserInvite, settings: Settings) -> tuple[UserAccount, EmailMessage]:
    """US-1.04 : compte INVITED + attribution + jeton ; une seule opération métier auditée."""
    db = auth.db
    _check_role_and_scope(auth, body.role_code, body.scope_type, body.site_id)
    user, assignment, token = create_invited_user(
        db,
        tenant_id=auth.tenant_id,
        tenant_kind=auth.principal.tenant_kind,
        email=str(body.email),
        display_name=body.display_name,
        phone=body.phone,
        role_code=body.role_code,
        scope_type=body.scope_type,
        site_id=body.site_id,
        granted_by=auth.user_id,
        now=auth.clock.now(),
        settings=settings,
    )
    record(
        db,
        tenant_id=auth.tenant_id,
        action="user.invite",
        entity_type="user_account",
        entity_id=user.user_account_id,
        site_id=body.site_id,
        actor_user_id=auth.user_id,
        after={
            "display_name": user.display_name,
            "role_code": assignment.role_code,
            "scope_type": assignment.scope_type,
            "site_id": assignment.site_id,
            **({"criticality": "HIGH"} if body.role_code in HIGH_CRITICALITY_ROLES else {}),
        },
        changed_fields=("display_name", "email", *(("phone",) if body.phone else ())),
    )
    workspace = _tenant(db, auth.tenant_id).code
    db.commit()
    return user, invitation_message(str(body.email), token, workspace, settings)


def resend_invitation(auth: Authorized, user_id: uuid.UUID, settings: Settings) -> EmailMessage:
    db = auth.db
    user = _user_or_404(db, user_id, for_update=True)
    if user.status != "INVITED":
        raise AppError("STATE_TRANSITION_INVALID")
    token = issue_account_token(
        db,
        tenant_id=auth.tenant_id,
        user_id=user.user_account_id,
        purpose="INVITATION",
        now=auth.clock.now(),
        settings=settings,
        created_by=auth.user_id,
    )
    record(
        db,
        tenant_id=auth.tenant_id,
        action="user.resend_invitation",
        entity_type="user_account",
        entity_id=user.user_account_id,
        actor_user_id=auth.user_id,
    )
    workspace = _tenant(db, auth.tenant_id).code
    db.commit()
    return invitation_message(user.email, token, workspace, settings)


def update_user(auth: Authorized, user_id: uuid.UUID, body: UserUpdate, expected_version: int) -> UserAccount:
    db = auth.db
    user = _user_or_404(db, user_id, for_update=True)
    check_version(expected_version, user.row_version)
    fields = tuple(sorted(body.model_fields_set))
    if "display_name" in fields and body.display_name is None:
        raise AppError("VALIDATION_ERROR", details=[{"field": "display_name", "type": "missing"}])
    before = {"display_name": user.display_name} if "display_name" in fields else {}
    for name in fields:
        setattr(user, name, getattr(body, name))
    user.updated_by = auth.user_id
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="user.update",
        entity_type="user_account",
        entity_id=user.user_account_id,
        actor_user_id=auth.user_id,
        before=before,
        after={"display_name": user.display_name} if "display_name" in fields else {},
        changed_fields=fields,
    )
    db.commit()
    return user


def change_user_status(
    auth: Authorized, user_id: uuid.UUID, expected_version: int, deactivate: bool
) -> UserAccount:
    """US-1.07 : désactivation (sessions et jetons révoqués) ou réactivation."""
    db, now = auth.db, auth.clock.now()
    user = _user_or_404(db, user_id, for_update=True)
    check_version(expected_version, user.row_version)
    if deactivate and user.user_account_id == auth.user_id:
        security_denial(
            auth, action="user.deactivate", entity_type="user_account", reason="SELF_DEACTIVATION"
        )
        raise AppError("SELF_ROLE_CHANGE_FORBIDDEN")
    source = user.status
    if deactivate:
        if source == "DISABLED":
            raise AppError("STATE_TRANSITION_INVALID")
        if source == "ACTIVE":
            _ensure_not_last_admin(auth, excluding_user=user.user_account_id)
        target = "DISABLED"
    else:
        if source != "DISABLED":
            raise AppError("STATE_TRANSITION_INVALID")
        target = "ACTIVE" if user.password_hash else "INVITED"
    user.status = target
    user.updated_by = auth.user_id
    db.flush()
    if deactivate:
        revoke_sessions(db, now=now, reason="USER_DISABLED", user_id=user.user_account_id)
        revoke_open_tokens(db, user_id=user.user_account_id, now=now)
    record(
        db,
        tenant_id=auth.tenant_id,
        action="user.deactivate" if deactivate else "user.reactivate",
        entity_type="user_account",
        entity_id=user.user_account_id,
        actor_user_id=auth.user_id,
        before={"status": source},
        after={"status": target},
        changed_fields=("status",),
    )
    db.commit()
    return user


def admin_reset_credentials(auth: Authorized, user_id: uuid.UUID, settings: Settings) -> EmailMessage:
    db = auth.db
    user = _user_or_404(db, user_id, for_update=True)
    if user.status != "ACTIVE":
        raise AppError("STATE_TRANSITION_INVALID")
    token = issue_account_token(
        db,
        tenant_id=auth.tenant_id,
        user_id=user.user_account_id,
        purpose="PASSWORD_RESET",
        now=auth.clock.now(),
        settings=settings,
        created_by=auth.user_id,
    )
    record(
        db,
        tenant_id=auth.tenant_id,
        action="user.reset_credentials",
        entity_type="user_account",
        entity_id=user.user_account_id,
        actor_user_id=auth.user_id,
    )
    db.commit()
    return reset_message(user.email, token, settings)


# --- Rôles --------------------------------------------------------------------------------------------


def list_roles(auth: Authorized) -> list[RoleOut]:
    matrix = load_matrix()
    scopes: dict[str, list[str]] = {}
    for row in auth.db.execute(select(RoleAllowedScope).order_by(RoleAllowedScope.scope_type)).scalars():
        scopes.setdefault(row.role_code, []).append(row.scope_type)
    roles = auth.db.execute(select(Role).order_by(Role.role_code)).scalars()
    platform = auth.principal.tenant_kind == "PLATFORM"
    return [
        RoleOut(
            role_code=r.role_code,
            label_fr=r.label_fr,
            allowed_scopes=scopes.get(r.role_code, []),
            is_optional=r.is_optional,
        )
        for r in roles
        if platform or (r.role_code in matrix.roles and matrix.roles[r.role_code].assignable_by_tenant)
    ]


def list_assignments(
    auth: Authorized, page: PageParams, user_id: uuid.UUID | None, include_revoked: bool
) -> tuple[list[UserRoleAssignment], int]:
    stmt = select(UserRoleAssignment)
    if user_id is not None:
        stmt = stmt.where(UserRoleAssignment.user_account_id == user_id)
    if not include_revoked:
        stmt = stmt.where(UserRoleAssignment.revoked_at.is_(None))
    total = auth.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = auth.db.execute(
        stmt.order_by(UserRoleAssignment.created_at, UserRoleAssignment.user_role_assignment_id)
        .offset(page.offset)
        .limit(page.page_size)
    )
    return list(rows.scalars()), total


def create_assignment(auth: Authorized, body: RoleAssignmentCreate) -> UserRoleAssignment:
    """US-1.06 / US-1.31 : auto-modification (422) évaluée en premier, puis rôle, portée, références."""
    db, now = auth.db, auth.clock.now()
    if body.user_account_id == auth.user_id:
        security_denial(
            auth,
            action="role_assignment.create",
            entity_type="user_role_assignment",
            reason="SELF_ROLE_CHANGE_FORBIDDEN",
        )
        raise AppError("SELF_ROLE_CHANGE_FORBIDDEN")
    _check_role_and_scope(auth, body.role_code, body.scope_type, body.site_id)
    if db.get(UserAccount, body.user_account_id) is None:
        raise AppError("REFERENCE_NOT_FOUND", details=[{"field": "user_account_id"}])
    assignment = UserRoleAssignment(
        tenant_id=auth.tenant_id,
        tenant_kind=auth.principal.tenant_kind,
        user_account_id=body.user_account_id,
        role_code=body.role_code,
        scope_type=body.scope_type,
        site_id=body.site_id,
        valid_from=now,
        granted_by=auth.user_id,
    )
    db.add(assignment)
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="role_assignment.create",
        entity_type="user_role_assignment",
        entity_id=assignment.user_role_assignment_id,
        site_id=body.site_id,
        actor_user_id=auth.user_id,
        after={
            "user_account_id": body.user_account_id,
            "role_code": body.role_code,
            "scope_type": body.scope_type,
            "site_id": body.site_id,
            **({"criticality": "HIGH"} if body.role_code in HIGH_CRITICALITY_ROLES else {}),
        },
    )
    db.commit()
    return assignment


def revoke_assignment(
    auth: Authorized, assignment_id: uuid.UUID, expected_version: int
) -> UserRoleAssignment:
    db, now = auth.db, auth.clock.now()
    assignment = db.execute(
        select(UserRoleAssignment)
        .where(UserRoleAssignment.user_role_assignment_id == assignment_id)
        .with_for_update(key_share=True)
    ).scalar_one_or_none()
    if assignment is None:
        raise AppError("NOT_FOUND")
    check_version(expected_version, assignment.row_version)
    if assignment.user_account_id == auth.user_id:
        security_denial(
            auth,
            action="role_assignment.revoke",
            entity_type="user_role_assignment",
            reason="SELF_ROLE_CHANGE_FORBIDDEN",
        )
        raise AppError("SELF_ROLE_CHANGE_FORBIDDEN")
    if assignment.revoked_at is not None:
        raise AppError("STATE_TRANSITION_INVALID")
    if assignment.role_code == "TENANT_ADMIN":
        _ensure_not_last_admin(auth, excluding_assignment=assignment.user_role_assignment_id)
    assignment.revoked_at = now
    assignment.revoked_by = auth.user_id
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="role_assignment.revoke",
        entity_type="user_role_assignment",
        entity_id=assignment.user_role_assignment_id,
        site_id=assignment.site_id,
        actor_user_id=auth.user_id,
        before={"role_code": assignment.role_code, "revoked": False},
        after={"revoked": True},
        changed_fields=("revoked_at",),
    )
    db.commit()
    return assignment
