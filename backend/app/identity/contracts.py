"""Contrat public du module identity (utilisé par organization pour le provisioning d'un tenant)."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.email import EmailMessage
from app.core.security import CompositeToken, new_secret
from app.identity.models import AccountToken, AuthSession, UserAccount, UserRoleAssignment


@dataclass(frozen=True)
class IssuedToken:
    """Jeton à usage unique : la valeur en clair n'existe qu'en mémoire, le temps de l'envoyer."""

    token: CompositeToken
    purpose: str

    def encode(self) -> str:
        return self.token.encode()


def issue_account_token(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    purpose: str,
    now: datetime,
    settings: Settings,
    created_by: uuid.UUID | None,
) -> IssuedToken:
    """Révoque le jeton ouvert de même finalité puis en émet un nouveau (uq_account_token_open)."""
    db.execute(
        update(AccountToken)
        .where(
            AccountToken.user_account_id == user_id,
            AccountToken.purpose == purpose,
            AccountToken.consumed_at.is_(None),
            AccountToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    ttl = settings.invitation_ttl if purpose == "INVITATION" else settings.reset_token_ttl
    token = CompositeToken(tenant_id=tenant_id, record_id=uuid.uuid4(), secret=new_secret())
    db.add(
        AccountToken(
            account_token_id=token.record_id,
            tenant_id=tenant_id,
            user_account_id=user_id,
            purpose=purpose,
            token_hash=token.secret_hash,
            created_at=now,
            expires_at=now + ttl,
            created_by=created_by,
        )
    )
    db.flush()
    return IssuedToken(token=token, purpose=purpose)


def create_invited_user(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    tenant_kind: str,
    email: str,
    display_name: str,
    phone: str | None,
    role_code: str,
    scope_type: str,
    site_id: uuid.UUID | None,
    granted_by: uuid.UUID,
    now: datetime,
    settings: Settings,
) -> tuple[UserAccount, UserRoleAssignment, IssuedToken]:
    """Crée un compte INVITED, son attribution de rôle et un jeton d'invitation (contexte = tenant_id)."""
    user = UserAccount(
        tenant_id=tenant_id,
        email=email,
        display_name=display_name,
        phone=phone,
        status="INVITED",
        created_by=granted_by,
        updated_by=granted_by,
    )
    db.add(user)
    db.flush()
    assignment = UserRoleAssignment(
        tenant_id=tenant_id,
        tenant_kind=tenant_kind,
        user_account_id=user.user_account_id,
        role_code=role_code,
        scope_type=scope_type,
        site_id=site_id,
        valid_from=now,
        granted_by=granted_by,
    )
    db.add(assignment)
    db.flush()
    token = issue_account_token(
        db,
        tenant_id=tenant_id,
        user_id=user.user_account_id,
        purpose="INVITATION",
        now=now,
        settings=settings,
        created_by=granted_by,
    )
    return user, assignment, token


def revoke_open_tokens(db: Session, *, user_id: uuid.UUID, now: datetime) -> int:
    """Invalide les jetons d'invitation et de réinitialisation ouverts (ex. à la désactivation)."""
    result = db.execute(
        update(AccountToken)
        .where(
            AccountToken.user_account_id == user_id,
            AccountToken.consumed_at.is_(None),
            AccountToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    return int(getattr(result, "rowcount", 0) or 0)


def revoke_sessions(
    db: Session,
    *,
    now: datetime,
    reason: str,
    user_id: uuid.UUID | None = None,
    except_session: uuid.UUID | None = None,
) -> int:
    """Révoque les sessions ouvertes du tenant courant (ou d'un utilisateur). Effet : 401 immédiat."""
    stmt = update(AuthSession).where(AuthSession.revoked_at.is_(None))
    if user_id is not None:
        stmt = stmt.where(AuthSession.user_account_id == user_id)
    if except_session is not None:
        stmt = stmt.where(AuthSession.auth_session_id != except_session)
    result = db.execute(stmt.values(revoked_at=now, revoked_reason=reason))
    return int(getattr(result, "rowcount", 0) or 0)


def invitation_message(
    email: str, token: IssuedToken, workspace_code: str, settings: Settings
) -> EmailMessage:
    link = f"{settings.public_web_url}/activation#token={token.encode()}"
    return EmailMessage(
        to=email,
        subject="MINEFLEET 360 — activation de votre compte",
        body=(
            f"Bonjour,\n\nUn compte MINEFLEET 360 a été créé pour vous dans l'espace « {workspace_code} ».\n"
            f"Pour définir votre mot de passe, ouvrez ce lien (usage unique) :\n{link}\n"
        ),
        kind="INVITATION",
    )


def reset_message(email: str, token: IssuedToken, settings: Settings) -> EmailMessage:
    link = f"{settings.public_web_url}/reinitialisation#token={token.encode()}"
    return EmailMessage(
        to=email,
        subject="MINEFLEET 360 — réinitialisation du mot de passe",
        body=(
            "Bonjour,\n\nUne réinitialisation de mot de passe a été demandée pour votre compte.\n"
            f"Ouvrez ce lien (usage unique, durée limitée) :\n{link}\n"
            "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.\n"
        ),
        kind="PASSWORD_RESET",
    )
