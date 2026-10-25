"""Flux d'authentification (ADR-003, D-06, MODELE_PHYSIQUE §6.2).

- Réponse 401 INVALID_CREDENTIALS identique : code d'espace inconnu, e-mail inconnu, mot de passe faux,
  compte non actif, tenant suspendu ; hachage factice pour garder un coût comparable.
- Tenant résolu avant authentification par code EXACT (app.login_tenant_code), sans BYPASSRLS.
- Refresh opaque rotatif à usage unique ; réutilisation hors fenêtre de grâce → session révoquée + audit.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.audit.contracts import record
from app.core.clock import Clock
from app.core.config import Settings
from app.core.email import EmailMessage
from app.core.errors import AppError
from app.core.logging import security_logger
from app.core.ratelimit import FailureLimiter
from app.core.request_context import get_request_meta
from app.core.security import (
    AccessClaims,
    CompositeToken,
    burn_password_check,
    check_password_policy,
    constant_time_equals,
    hash_password,
    issue_access_token,
    new_secret,
    parse_composite_token,
    password_needs_rehash,
    sha256,
    verify_password,
)
from app.core.tenancy import set_login_tenant_code, set_tenant_context
from app.identity.contracts import issue_account_token, reset_message, revoke_sessions
from app.identity.models import AccountToken, AuthSession, UserAccount
from app.organization.models import Tenant


@dataclass(frozen=True)
class IssuedSession:
    access_token: str
    refresh_cookie: str
    expires_in: int
    session_expires_at: datetime
    user_id: uuid.UUID
    display_name: str
    workspace_code: str


class AuthLimiters:
    def __init__(self, settings: Settings) -> None:
        self.login = FailureLimiter(settings.login_max_failures, settings.login_lockout_duration)
        self.source = FailureLimiter(settings.login_ip_max_failures, settings.login_lockout_duration)
        self.tokens = FailureLimiter(settings.login_max_failures, settings.login_lockout_duration)


def _client_key() -> str:
    meta = get_request_meta()
    return meta.ip_address if meta and meta.ip_address else "unknown"


def _rate_limited(settings: Settings) -> AppError:
    return AppError(
        "RATE_LIMITED", headers={"Retry-After": str(int(settings.login_lockout_duration.total_seconds()))}
    )


def _resolve_tenant(db: Session, code: str, kind: str) -> Tenant | None:
    set_login_tenant_code(db, code)
    tenant = db.execute(select(Tenant).where(Tenant.code == code, Tenant.kind == kind)).scalar_one_or_none()
    if tenant is not None:
        set_tenant_context(db, tenant.tenant_id)
    return tenant


def _open_session(
    db: Session, user: UserAccount, tenant: Tenant, clock: Clock, settings: Settings
) -> IssuedSession:
    now = clock.now()
    meta = get_request_meta()
    secret = new_secret()
    session = AuthSession(
        auth_session_id=uuid.uuid4(),
        tenant_id=tenant.tenant_id,
        user_account_id=user.user_account_id,
        refresh_hash_current=sha256(secret),
        amr=["pwd"],
        ip_address=meta.ip_address if meta else None,
        user_agent=(meta.user_agent or "")[:300] if meta and meta.user_agent else None,
        created_at=now,
        last_seen_at=now,
        expires_at=now + settings.session_max_age,
    )
    db.add(session)
    db.flush()
    return _issue(session, user, tenant, secret, clock, settings)


def _issue(
    session: AuthSession, user: UserAccount, tenant: Tenant, secret: str, clock: Clock, settings: Settings
) -> IssuedSession:
    access = issue_access_token(
        AccessClaims(user.user_account_id, tenant.tenant_id, session.auth_session_id), clock.now(), settings
    )
    return IssuedSession(
        access_token=access,
        refresh_cookie=CompositeToken(tenant.tenant_id, session.auth_session_id, secret).encode(),
        expires_in=int(settings.access_token_ttl.total_seconds()),
        session_expires_at=session.expires_at,
        user_id=user.user_account_id,
        display_name=user.display_name,
        workspace_code=tenant.code,
    )


def login(
    db: Session,
    *,
    code: str,
    email: str,
    password: str,
    kind: str,
    clock: Clock,
    settings: Settings,
    limiters: AuthLimiters,
) -> IssuedSession:
    now = clock.now()
    code, email_key = code.strip().lower(), email.strip().lower()
    key = f"{kind}:{code}:{email_key}"
    if limiters.login.is_blocked(key, now) or limiters.source.is_blocked(f"ip:{_client_key()}", now):
        raise _rate_limited(settings)

    if kind == "CUSTOMER" and code == settings.platform_tenant_code:
        tenant = None  # la plateforme a son propre point d'entrée
    else:
        tenant = _resolve_tenant(db, code, kind)
    user = None
    if tenant is not None:
        user = db.execute(select(UserAccount).where(UserAccount.email == email_key)).scalar_one_or_none()
    password_ok = verify_password(user.password_hash if user else None, password) if user else False
    if user is None:
        burn_password_check(password)

    if (
        tenant is None
        or user is None
        or not password_ok
        or user.status != "ACTIVE"
        or tenant.status != "ACTIVE"
    ):
        limiters.login.record_failure(key, now)
        limiters.source.record_failure(f"ip:{_client_key()}", now)
        if tenant is None:
            security_logger.info("login_unknown_workspace")
        else:
            if user is not None:
                user.failed_login_count += 1
            record(
                db,
                tenant_id=tenant.tenant_id,
                action="auth.login",
                entity_type="user_account",
                entity_id=user.user_account_id if user else None,
                actor_user_id=user.user_account_id if user else None,
                actor_kind="USER" if user else "ANONYMOUS",
                outcome="FAILURE",
                reason="INVALID_CREDENTIALS",
            )
            db.commit()
        raise AppError("INVALID_CREDENTIALS")

    assert user is not None and tenant is not None
    limiters.login.reset(key)
    if user.password_hash and password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.failed_login_count = 0
    user.last_login_at = now
    issued = _open_session(db, user, tenant, clock, settings)
    record(
        db,
        tenant_id=tenant.tenant_id,
        action="auth.login",
        entity_type="user_account",
        entity_id=user.user_account_id,
        actor_user_id=user.user_account_id,
    )
    db.commit()
    return issued


def _load_session(db: Session, raw_cookie: str | None) -> tuple[AuthSession, CompositeToken] | None:
    token = parse_composite_token(raw_cookie)
    if token is None:
        return None
    set_tenant_context(db, token.tenant_id)
    session = db.execute(
        select(AuthSession)
        .where(AuthSession.auth_session_id == token.record_id)
        .with_for_update(key_share=True)
    ).scalar_one_or_none()
    return (session, token) if session is not None else None


def refresh(db: Session, *, raw_cookie: str | None, clock: Clock, settings: Settings) -> IssuedSession:
    now = clock.now()
    loaded = _load_session(db, raw_cookie)
    if loaded is None:
        raise AppError("AUTH_REQUIRED")
    session, token = loaded
    user = db.get(UserAccount, session.user_account_id)
    tenant = db.get(Tenant, session.tenant_id)
    if (
        session.revoked_at is not None
        or session.expires_at <= now
        or user is None
        or tenant is None
        or user.status != "ACTIVE"
        or tenant.status != "ACTIVE"
    ):
        raise AppError("AUTH_REQUIRED")
    presented = token.secret_hash
    if constant_time_equals(presented, session.refresh_hash_current):
        secret = new_secret()
        session.refresh_hash_previous = session.refresh_hash_current
        session.refresh_hash_current = sha256(secret)
        session.rotated_at = now
        session.last_seen_at = now
        db.flush()
        issued = _issue(session, user, tenant, secret, clock, settings)
        db.commit()
        return issued
    if session.refresh_hash_previous is not None and constant_time_equals(
        presented, session.refresh_hash_previous
    ):
        in_grace = (
            session.rotated_at is not None and now - session.rotated_at <= settings.refresh_grace_period
        )
        if not in_grace:
            # Rejeu d'un refresh déjà consommé : vol présumé → révocation de la session (ADR-003).
            session.revoked_at = now
            session.revoked_reason = "REFRESH_REUSE"
            record(
                db,
                tenant_id=tenant.tenant_id,
                action="auth.refresh_reuse",
                entity_type="auth_session",
                entity_id=session.auth_session_id,
                actor_user_id=user.user_account_id,
                outcome="FAILURE",
                reason="REFRESH_REUSE",
            )
            db.commit()
            security_logger.warning("refresh_token_reuse", extra={"tenant_id": str(tenant.tenant_id)})
    raise AppError("AUTH_REQUIRED")


def logout(db: Session, *, raw_cookie: str | None, clock: Clock) -> None:
    """US-1.09 : toujours 204 ; révoque la session si le cookie est reconnu."""
    loaded = _load_session(db, raw_cookie)
    if loaded is None:
        return
    session, token = loaded
    known = constant_time_equals(token.secret_hash, session.refresh_hash_current) or (
        session.refresh_hash_previous is not None
        and constant_time_equals(token.secret_hash, session.refresh_hash_previous)
    )
    if not known or session.revoked_at is not None:
        return
    session.revoked_at = clock.now()
    session.revoked_reason = "LOGOUT"
    record(
        db,
        tenant_id=session.tenant_id,
        action="auth.logout",
        entity_type="auth_session",
        entity_id=session.auth_session_id,
        actor_user_id=session.user_account_id,
    )
    db.commit()


def _consume_token(
    db: Session,
    *,
    raw_token: str,
    purpose: str,
    expected_status: str,
    clock: Clock,
    settings: Settings,
    limiters: AuthLimiters,
) -> tuple[AccountToken, UserAccount]:
    now = clock.now()
    ip_key = f"ip:{_client_key()}"
    if limiters.tokens.is_blocked(ip_key, now):
        raise _rate_limited(settings)
    token = parse_composite_token(raw_token)
    row = user = tenant = None
    if token is not None:
        set_tenant_context(db, token.tenant_id)
        row = db.execute(
            select(AccountToken)
            .where(AccountToken.account_token_id == token.record_id, AccountToken.purpose == purpose)
            .with_for_update(key_share=True)
        ).scalar_one_or_none()
        if row is not None:
            user = db.get(UserAccount, row.user_account_id)
            tenant = db.get(Tenant, row.tenant_id)
    if (
        token is None
        or row is None
        or user is None
        or tenant is None
        or not constant_time_equals(token.secret_hash, row.token_hash)
        or row.consumed_at is not None
        or row.revoked_at is not None
        or row.expires_at <= now
        or tenant.status != "ACTIVE"
        or user.status != expected_status
    ):
        limiters.tokens.record_failure(ip_key, now)
        raise AppError("TOKEN_INVALID")
    return row, user


def accept_invitation(
    db: Session, *, raw_token: str, password: str, clock: Clock, settings: Settings, limiters: AuthLimiters
) -> None:
    row, user = _consume_token(
        db,
        raw_token=raw_token,
        purpose="INVITATION",
        expected_status="INVITED",
        clock=clock,
        settings=settings,
        limiters=limiters,
    )
    check_password_policy(password, settings, email=user.email)
    now = clock.now()
    user.password_hash = hash_password(password)
    user.status = "ACTIVE"
    user.must_change_password = False
    user.updated_by = user.user_account_id
    row.consumed_at = now
    db.flush()
    record(
        db,
        tenant_id=user.tenant_id,
        action="user.activate",
        entity_type="user_account",
        entity_id=user.user_account_id,
        actor_user_id=user.user_account_id,
        before={"status": "INVITED"},
        after={"status": "ACTIVE"},
        changed_fields=("password", "status"),
    )
    db.commit()


def request_password_reset(
    db: Session, *, code: str, email: str, clock: Clock, settings: Settings, limiters: AuthLimiters
) -> EmailMessage | None:
    """US-1.10 A1 : réponse identique (202) que le compte existe ou non."""
    now = clock.now()
    ip_key = f"reset-ip:{_client_key()}"
    pair_key = f"reset:{code.strip().lower()}:{email.strip().lower()}"
    if limiters.tokens.is_blocked(ip_key, now) or limiters.tokens.is_blocked(pair_key, now):
        raise _rate_limited(settings)
    limiters.tokens.record_failure(ip_key, now)  # compte chaque demande : limite le volume par source
    limiters.tokens.record_failure(pair_key, now)
    code = code.strip().lower()
    if code == settings.platform_tenant_code:
        return None
    tenant = _resolve_tenant(db, code, "CUSTOMER")
    if tenant is None or tenant.status != "ACTIVE":
        return None
    user = db.execute(
        select(UserAccount).where(UserAccount.email == email.strip().lower())
    ).scalar_one_or_none()
    if user is None or user.status != "ACTIVE":
        return None
    token = issue_account_token(
        db,
        tenant_id=tenant.tenant_id,
        user_id=user.user_account_id,
        purpose="PASSWORD_RESET",
        now=now,
        settings=settings,
        created_by=None,
    )
    record(
        db,
        tenant_id=tenant.tenant_id,
        action="user.password_reset_request",
        entity_type="user_account",
        entity_id=user.user_account_id,
        actor_kind="ANONYMOUS",
    )
    db.commit()
    return reset_message(user.email, token, settings)


def confirm_password_reset(
    db: Session, *, raw_token: str, password: str, clock: Clock, settings: Settings, limiters: AuthLimiters
) -> None:
    row, user = _consume_token(
        db,
        raw_token=raw_token,
        purpose="PASSWORD_RESET",
        expected_status="ACTIVE",
        clock=clock,
        settings=settings,
        limiters=limiters,
    )
    check_password_policy(password, settings, email=user.email)
    now = clock.now()
    user.password_hash = hash_password(password)
    user.updated_by = user.user_account_id
    row.consumed_at = now
    db.flush()
    revoked = revoke_sessions(db, now=now, reason="PASSWORD_RESET", user_id=user.user_account_id)
    record(
        db,
        tenant_id=user.tenant_id,
        action="user.password_reset",
        entity_type="user_account",
        entity_id=user.user_account_id,
        actor_user_id=user.user_account_id,
        changed_fields=("password",),
        after={"sessions_revoked": revoked},
    )
    db.commit()


def change_own_password(
    db: Session,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    current: str,
    new: str,
    clock: Clock,
    settings: Settings,
    limiters: AuthLimiters,
) -> None:
    """Un jeton d'accès volé ne doit pas permettre de deviner le mot de passe actuel : limitation par
    compte ; au seuil, la session courante est révoquée (présomption de vol) et l'échec audité."""
    now = clock.now()
    key = f"pwchange:{user_id}"
    if limiters.tokens.is_blocked(key, now):
        raise _rate_limited(settings)
    user = db.execute(
        select(UserAccount).where(UserAccount.user_account_id == user_id).with_for_update(key_share=True)
    ).scalar_one()
    if not verify_password(user.password_hash, current):
        limiters.tokens.record_failure(key, now)
        blocked = limiters.tokens.is_blocked(key, now)
        if blocked:
            db.execute(
                update(AuthSession)
                .where(AuthSession.auth_session_id == session_id, AuthSession.revoked_at.is_(None))
                .values(revoked_at=now, revoked_reason="PASSWORD_GUESSING")
            )
        record(
            db,
            tenant_id=user.tenant_id,
            action="user.change_own_password",
            entity_type="user_account",
            entity_id=user_id,
            actor_user_id=user_id,
            outcome="FAILURE",
            reason="RATE_LIMITED" if blocked else "INVALID_CURRENT_PASSWORD",
        )
        db.commit()
        if blocked:
            raise _rate_limited(settings)
        raise AppError("VALIDATION_ERROR", details=[{"field": "current_password", "type": "invalid"}])
    check_password_policy(new, settings, email=user.email)
    limiters.tokens.reset(key)
    user.password_hash = hash_password(new)
    user.updated_by = user_id
    db.flush()
    revoke_sessions(db, now=now, reason="PASSWORD_CHANGED", user_id=user_id, except_session=session_id)
    record(
        db,
        tenant_id=user.tenant_id,
        action="user.change_own_password",
        entity_type="user_account",
        entity_id=user_id,
        actor_user_id=user_id,
        changed_fields=("password",),
    )
    db.commit()
