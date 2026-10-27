"""Double authentification TOTP (C-03, SEC-04, ADR-003).

- Enrôlement en deux temps : secret en attente (chiffré, 15 min), puis confirmation par un premier code.
- Connexion : mot de passe → défi (jeton `mfa`, 5 min) → code TOTP ou code de récupération → session
  marquée `otp` (amr). Essais limités par compte (limiteur partagé `tokens`), échecs audités.
- Anti-rejeu : un pas TOTP accepté ne l'est plus jamais ; un code de récupération est à usage unique.
- Secrets chiffrés (AES-GCM, contexte lié au compte), codes de récupération hachés ; aucun secret ni code
  dans l'audit ni les journaux.
"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.audit.contracts import record
from app.authz.dependencies import Authorized, load_grants
from app.core import totp
from app.core.clock import Clock
from app.core.config import Settings
from app.core.errors import AppError
from app.core.http import check_version
from app.core.secretbox import open_sealed, seal
from app.core.security import (
    constant_time_equals,
    credential_fingerprint,
    decode_mfa_challenge,
    verify_password,
)
from app.core.tenancy import set_tenant_context
from app.identity.auth_service import (
    AuthLimiters,
    IssuedSession,
    _client_key,
    _open_session,
    _rate_limited,
)
from app.identity.contracts import revoke_sessions
from app.identity.models import AuthSession, UserAccount
from app.identity.service import _user_or_404
from app.organization.models import Tenant

SETUP_TTL = timedelta(minutes=15)


def _context(user: UserAccount, purpose: str) -> str:
    return f"{purpose}:{user.tenant_id}:{user.user_account_id}"


def required_for(roles: set[str], settings: Settings) -> bool:
    return bool(roles & set(settings.mfa_required_roles))


def _roles(auth: Authorized) -> set[str]:
    return {g.role_code for g in load_grants(auth.db, auth.user_id, auth.clock)}


def _me(auth: Authorized) -> UserAccount:
    return auth.db.execute(
        select(UserAccount).where(UserAccount.user_account_id == auth.user_id).with_for_update(key_share=True)
    ).scalar_one()


def _active_secret(user: UserAccount, settings: Settings) -> bytes:
    secret = (
        open_sealed(user.mfa_secret_encrypted, context=_context(user, "mfa"), settings=settings)
        if user.mfa_secret_encrypted
        else None
    )
    if secret is None:
        raise AppError("INTERNAL_ERROR")  # secret illisible : clé changée ou valeur altérée
    return secret


def _new_recovery(user: UserAccount) -> list[str]:
    codes = totp.new_recovery_codes()
    user.mfa_recovery_hashes = [totp.hash_recovery_code(c) for c in codes]
    return codes


def _check_totp(
    user: UserAccount, code: str, *, now: datetime, settings: Settings, key: str, limiters: AuthLimiters
) -> None:
    """Code TOTP de l'utilisateur connecté (opérations sensibles) : limité et anti-rejeu."""
    if limiters.tokens.is_blocked(key, now):
        raise _rate_limited(settings)
    step = totp.verify(_active_secret(user, settings), code, now, last_step=user.mfa_last_step)
    if step is None:
        limiters.tokens.record_failure(key, now)
        raise AppError("MFA_CODE_INVALID")
    user.mfa_last_step = step
    limiters.tokens.reset(key)


def status(auth: Authorized, settings: Settings) -> dict[str, object]:
    user = auth.db.execute(
        select(UserAccount).where(UserAccount.user_account_id == auth.user_id)
    ).scalar_one()
    return {
        "enabled": user.mfa_enabled,
        "required": required_for(_roles(auth), settings) and settings.mfa_enforcement == "enroll",
        "enabled_at": user.mfa_enabled_at,
        "recovery_codes_remaining": len(user.mfa_recovery_hashes),
    }


def start_setup(auth: Authorized, settings: Settings) -> dict[str, str]:
    db = auth.db
    user = _me(auth)
    if user.mfa_enabled:
        raise AppError("MFA_ALREADY_ENABLED")
    secret = totp.new_secret()
    user.mfa_pending_secret_encrypted = seal(secret, context=_context(user, "mfa-pending"), settings=settings)
    user.mfa_pending_created_at = auth.clock.now()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="user.mfa_setup_start",
        entity_type="user_account",
        entity_id=user.user_account_id,
        actor_user_id=auth.user_id,
    )
    db.commit()
    return {
        "secret": totp.to_base32(secret),
        "otpauth_uri": totp.provisioning_uri(secret, account=user.email, issuer=settings.mfa_issuer),
    }


def confirm_setup(auth: Authorized, code: str, settings: Settings, limiters: AuthLimiters) -> list[str]:
    """Active le second facteur ; renvoie UNE fois les codes de récupération en clair."""
    db = auth.db
    now = auth.clock.now()
    key = f"mfa-setup:{auth.user_id}"
    if limiters.tokens.is_blocked(key, now):
        raise _rate_limited(settings)
    user = _me(auth)
    if user.mfa_enabled:
        raise AppError("MFA_ALREADY_ENABLED")
    pending = (
        open_sealed(
            user.mfa_pending_secret_encrypted, context=_context(user, "mfa-pending"), settings=settings
        )
        if user.mfa_pending_secret_encrypted and user.mfa_pending_created_at
        else None
    )
    if (
        pending is None
        or user.mfa_pending_created_at is None
        or now - user.mfa_pending_created_at > SETUP_TTL
    ):
        raise AppError("MFA_SETUP_EXPIRED")
    step = totp.verify(pending, code, now, last_step=None)
    if step is None:
        limiters.tokens.record_failure(key, now)
        raise AppError("MFA_CODE_INVALID")
    limiters.tokens.reset(key)
    user.mfa_secret_encrypted = seal(pending, context=_context(user, "mfa"), settings=settings)
    user.mfa_pending_secret_encrypted = None
    user.mfa_pending_created_at = None
    user.mfa_enabled = True
    user.mfa_enabled_at = now
    user.mfa_last_step = step
    codes = _new_recovery(user)
    # La session courante vient de prouver le second facteur ; les autres (mot de passe seul) sont fermées.
    db.execute(
        update(AuthSession)
        .where(AuthSession.auth_session_id == auth.principal.session_id)
        .values(amr=["pwd", "otp"])
    )
    revoke_sessions(
        db,
        now=now,
        reason="MFA_ENABLED",
        user_id=user.user_account_id,
        except_session=auth.principal.session_id,
    )
    record(
        db,
        tenant_id=auth.tenant_id,
        action="user.mfa_enable",
        entity_type="user_account",
        entity_id=user.user_account_id,
        actor_user_id=auth.user_id,
        changed_fields=("mfa_enabled",),
    )
    db.commit()
    return codes


def regenerate_recovery(auth: Authorized, code: str, settings: Settings, limiters: AuthLimiters) -> list[str]:
    db = auth.db
    user = _me(auth)
    if not user.mfa_enabled:
        raise AppError("MFA_NOT_ENABLED")
    _check_totp(
        user,
        code,
        now=auth.clock.now(),
        settings=settings,
        key=f"mfa-manage:{auth.user_id}",
        limiters=limiters,
    )
    codes = _new_recovery(user)
    record(
        db,
        tenant_id=auth.tenant_id,
        action="user.mfa_recovery_regenerate",
        entity_type="user_account",
        entity_id=user.user_account_id,
        actor_user_id=auth.user_id,
    )
    db.commit()
    return codes


def disable(auth: Authorized, password: str, code: str, settings: Settings, limiters: AuthLimiters) -> None:
    """Retrait volontaire : interdit aux rôles soumis à l'obligation ; mot de passe ET code exigés."""
    db = auth.db
    if required_for(_roles(auth), settings):
        raise AppError("MFA_REQUIRED_FOR_ROLE")
    user = _me(auth)
    if not user.mfa_enabled:
        raise AppError("MFA_NOT_ENABLED")
    key = f"mfa-manage:{auth.user_id}"
    now = auth.clock.now()
    if limiters.tokens.is_blocked(key, now):  # avant tout calcul : pas de force brute du mot de passe
        raise _rate_limited(settings)
    password_ok = verify_password(user.password_hash, password)
    step = totp.verify(_active_secret(user, settings), code, now, last_step=user.mfa_last_step)
    if not password_ok or step is None:
        # Erreur unique : ne révèle pas lequel des deux facteurs est faux.
        limiters.tokens.record_failure(key, now)
        raise AppError("INVALID_CREDENTIALS")
    limiters.tokens.reset(key)
    _clear(user)
    record(
        db,
        tenant_id=auth.tenant_id,
        action="user.mfa_disable",
        entity_type="user_account",
        entity_id=user.user_account_id,
        actor_user_id=auth.user_id,
        changed_fields=("mfa_enabled",),
    )
    db.commit()


def _clear(user: UserAccount) -> None:
    user.mfa_enabled = False
    user.mfa_enabled_at = None
    user.mfa_secret_encrypted = None
    user.mfa_pending_secret_encrypted = None
    user.mfa_pending_created_at = None
    user.mfa_last_step = None
    user.mfa_recovery_hashes = []


def admin_reset(auth: Authorized, user_id: uuid.UUID, expected_version: int) -> UserAccount:
    """Perte du téléphone : l'administrateur retire le second facteur ; toutes les sessions sont fermées
    et l'utilisateur devra se réenrôler (si son rôle l'exige) à la prochaine connexion."""
    db = auth.db
    if user_id == auth.user_id:
        raise AppError("SELF_ROLE_CHANGE_FORBIDDEN")
    user = _user_or_404(db, user_id, for_update=True)
    check_version(expected_version, user.row_version)
    if not user.mfa_enabled and user.mfa_pending_secret_encrypted is None:
        raise AppError("MFA_NOT_ENABLED")
    _clear(user)
    user.updated_by = auth.user_id
    revoke_sessions(db, now=auth.clock.now(), reason="MFA_RESET", user_id=user.user_account_id)
    db.flush()
    record(
        db,
        tenant_id=auth.tenant_id,
        action="user.mfa_reset",
        entity_type="user_account",
        entity_id=user.user_account_id,
        actor_user_id=auth.user_id,
        changed_fields=("mfa_enabled",),
    )
    db.commit()
    return user


def verify_challenge(
    db: Session, *, mfa_token: str, code: str, clock: Clock, settings: Settings, limiters: AuthLimiters
) -> IssuedSession:
    """Seconde étape de connexion : code TOTP (ou de récupération) → session `pwd`+`otp`."""
    now = clock.now()
    challenge = decode_mfa_challenge(mfa_token, now, settings)
    if challenge is None:
        raise AppError("MFA_CODE_INVALID")
    key = f"mfa-login:{challenge.user_id}"
    source = f"ip:{_client_key()}"
    if limiters.tokens.is_blocked(key, now) or limiters.source.is_blocked(source, now):
        raise _rate_limited(settings)
    set_tenant_context(db, challenge.tenant_id)
    user = db.execute(
        select(UserAccount)
        .where(UserAccount.user_account_id == challenge.user_id)
        .with_for_update(key_share=True)
    ).scalar_one_or_none()
    tenant = db.get(Tenant, challenge.tenant_id)
    if (
        user is None
        or tenant is None
        or user.status != "ACTIVE"
        or tenant.status != "ACTIVE"
        or not user.mfa_enabled
        # Mot de passe changé (ou réinitialisé) depuis l'émission du défi : celui-ci ne vaut plus.
        or not constant_time_equals(
            challenge.credential_fingerprint, credential_fingerprint(user.password_hash)
        )
    ):
        raise AppError("MFA_CODE_INVALID")

    method: str | None = None
    if totp.looks_like_recovery_code(code):
        presented = totp.hash_recovery_code(code)
        remaining = [h for h in user.mfa_recovery_hashes if not constant_time_equals(h, presented)]
        if len(remaining) < len(user.mfa_recovery_hashes):
            user.mfa_recovery_hashes = remaining  # usage unique
            method = "RECOVERY_CODE"
    else:
        step = totp.verify(_active_secret(user, settings), code, now, last_step=user.mfa_last_step)
        if step is not None:
            user.mfa_last_step = step
            method = "TOTP"

    if method is None:
        limiters.tokens.record_failure(key, now)
        limiters.source.record_failure(source, now)
        record(
            db,
            tenant_id=tenant.tenant_id,
            action="auth.mfa_verify",
            entity_type="user_account",
            entity_id=user.user_account_id,
            actor_user_id=user.user_account_id,
            outcome="FAILURE",
            reason="MFA_CODE_INVALID",
        )
        db.commit()
        raise AppError("MFA_CODE_INVALID")

    limiters.tokens.reset(key)
    user.last_login_at = now
    issued = _open_session(db, user, tenant, clock, settings, amr=("pwd", "otp"))
    record(
        db,
        tenant_id=tenant.tenant_id,
        action="auth.mfa_verify",
        entity_type="user_account",
        entity_id=user.user_account_id,
        actor_user_id=user.user_account_id,
        reason=method,
    )
    db.commit()
    return issued
