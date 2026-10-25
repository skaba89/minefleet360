"""Contexte tenant PostgreSQL (D-08). SEUL module autorisé à poser app.tenant_id (test d'architecture).

Le contexte est transactionnel (set_config(..., true) ≡ SET LOCAL) : il disparaît au COMMIT/ROLLBACK,
et une transaction sans contexte ne voit aucune ligne (politiques RLS + app.current_tenant_id()).
"""

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

PLATFORM_TENANT_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")


def set_tenant_context(session: Session, tenant_id: uuid.UUID) -> None:
    session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": str(tenant_id)},
    )


def set_login_tenant_code(session: Session, code: str) -> None:
    """Autorise la lecture de la seule ligne tenant portant ce code exact (pré-authentification, DB-05)."""
    session.execute(
        text("SELECT set_config('app.login_tenant_code', :code, true)"),
        {"code": code},
    )


def current_tenant_id(session: Session) -> uuid.UUID | None:
    value = session.execute(text("SELECT app.current_tenant_id()")).scalar_one_or_none()
    return value if isinstance(value, uuid.UUID) or value is None else uuid.UUID(str(value))
