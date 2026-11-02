"""Identifiants DEMO : générés à l'exécution, jamais stockés en clair, jamais affichés dans le terminal.

Ils sont écrits UNE fois dans un fichier créé en mode 600 (création exclusive : un fichier existant n'est
jamais écrasé), à transmettre aux testeurs par un canal sûr puis à supprimer. `reset-credentials` en régénère
pour une société DEMO (exclusivement) : anciennes sessions fermées, action auditée.
"""

import os
import secrets
from collections.abc import Iterable
from pathlib import Path

from sqlalchemy import select

from app.audit.contracts import record
from app.core.clock import SystemClock
from app.core.config import Settings, get_settings
from app.core.db import new_session
from app.core.security import hash_password
from app.core.tenancy import set_login_tenant_code, set_tenant_context
from app.demo.catalog import TENANTS
from app.demo.generator import Credential
from app.demo.guards import DemoRefused, ensure_demo_database
from app.identity.contracts import revoke_sessions
from app.identity.models import UserAccount, UserRoleAssignment
from app.organization.models import Tenant

HEADER = (
    "# Identifiants DEMO MineFleet 360 — fichier confidentiel (600) : "
    "transmettre par canal sûr puis supprimer.\n"
)


def write_credentials(path: str, credentials: Iterable[Credential]) -> int:
    rows = list(credentials)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(HEADER)
        handle.write("societe\trole\tsite\te-mail\tmot_de_passe\n")
        for c in rows:
            handle.write(f"{c.tenant}\t{c.role}\t{c.site or '-'}\t{c.email}\t{c.password}\n")
    os.chmod(path, 0o600)
    return len(rows)


def ensure_new_file(path: str) -> None:
    if Path(path).exists():
        raise DemoRefused(f"{path} existe déjà : choisir un nouveau fichier (aucun écrasement)")


def reset_credentials(tenant_code: str, settings: Settings | None = None) -> list[Credential]:
    settings = settings or get_settings()
    ensure_demo_database(settings)
    if tenant_code not in {t.code for t in TENANTS}:
        raise DemoRefused(f"{tenant_code} n'est pas une société du catalogue DEMO")
    db = new_session()
    try:
        set_login_tenant_code(db, tenant_code)
        tenant = db.execute(select(Tenant).where(Tenant.code == tenant_code)).scalar_one_or_none()
        if tenant is None or not tenant.is_demo:
            raise DemoRefused(f"{tenant_code} absente ou non marquée DEMO")
        tenant_id = tenant.tenant_id
        db.rollback()
        set_tenant_context(db, tenant_id)
        now = SystemClock().now()
        users = (
            db.execute(
                select(UserAccount)
                .where(UserAccount.status == "ACTIVE")
                .order_by(UserAccount.email)
                .with_for_update()
            )
            .scalars()
            .all()
        )
        grants = (
            db.execute(select(UserRoleAssignment).where(UserRoleAssignment.revoked_at.is_(None)))
            .scalars()
            .all()
        )
        sites = {g.user_account_id: g for g in grants}
        out: list[Credential] = []
        for user in users:
            password = "Demo-" + secrets.token_urlsafe(14)
            user.password_hash = hash_password(password)
            user.must_change_password = False
            user.failed_login_count = 0
            user.locked_until = None
            revoke_sessions(db, now=now, reason="PASSWORD_RESET", user_id=user.user_account_id)
            record(
                db,
                tenant_id=tenant_id,
                action="user.password_reset",
                entity_type="user_account",
                entity_id=user.user_account_id,
                actor_kind="SYSTEM",
                reason="OPS_CLI:demo-reset-credentials",
                changed_fields=("password_hash",),
            )
            grant = sites.get(user.user_account_id)
            out.append(Credential(tenant_code, grant.role_code if grant else "-", None, user.email, password))
        db.commit()
        return out
    finally:
        db.close()
