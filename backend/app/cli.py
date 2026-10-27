"""Commandes d'exploitation (rôle applicatif mf_app, jamais le propriétaire du schéma).

minefleet create-platform-admin --email <e-mail> --name "<nom>"
    US-1.32 : premier PLATFORM_ADMIN ; mot de passe lu dans MF_BOOTSTRAP_PASSWORD (jamais en argument).
minefleet seed-fictif
    US-1.30 : jeu de données FICTIF de recette (refusé en production et en cas de réexécution).
minefleet reset-platform-mfa --email <e-mail>
    C-03 : retire le second facteur d'un PLATFORM_ADMIN qui a perdu téléphone ET codes de récupération
    (aucun compte au-dessus de lui ne peut le faire par l'API). Sessions fermées, action auditée.
"""

import argparse
import getpass
import os
import sys

from sqlalchemy import select

from app.audit.contracts import record
from app.core.clock import SystemClock
from app.core.config import get_settings
from app.core.db import new_session
from app.core.errors import AppError
from app.core.security import check_password_policy, hash_password
from app.core.tenancy import PLATFORM_TENANT_ID, set_tenant_context
from app.identity.models import UserAccount, UserRoleAssignment


def create_platform_admin(email: str, display_name: str, password: str) -> int:
    settings = get_settings()
    try:
        check_password_policy(password, settings, email=email)
    except AppError as exc:
        print(f"Mot de passe refusé : {exc.details}", file=sys.stderr)
        return 2
    now = SystemClock().now()
    db = new_session()
    try:
        set_tenant_context(db, PLATFORM_TENANT_ID)
        existing = db.execute(
            select(UserRoleAssignment.user_role_assignment_id).where(
                UserRoleAssignment.role_code == "PLATFORM_ADMIN", UserRoleAssignment.revoked_at.is_(None)
            )
        ).first()
        if existing is not None:
            print("Refusé : un PLATFORM_ADMIN existe déjà (US-1.32 A2).", file=sys.stderr)
            return 3
        user = UserAccount(
            tenant_id=PLATFORM_TENANT_ID,
            email=email.strip().lower(),
            display_name=display_name,
            password_hash=hash_password(password),
            status="ACTIVE",
            must_change_password=False,
        )
        db.add(user)
        db.flush()
        db.add(
            UserRoleAssignment(
                tenant_id=PLATFORM_TENANT_ID,
                tenant_kind="PLATFORM",
                user_account_id=user.user_account_id,
                role_code="PLATFORM_ADMIN",
                scope_type="PLATFORM",
                valid_from=now,
                granted_by=user.user_account_id,
            )
        )
        record(
            db,
            tenant_id=PLATFORM_TENANT_ID,
            action="platform_admin.bootstrap",
            entity_type="user_account",
            entity_id=user.user_account_id,
            actor_kind="SYSTEM",
            after={"display_name": display_name},
        )
        db.commit()
        print(f"PLATFORM_ADMIN créé : {user.user_account_id}")
        return 0
    finally:
        db.close()


def _operator() -> str:
    """Utilisateur système qui lance la commande (traçabilité de l'exploitation, revue MFA-R-09)."""
    try:
        return getpass.getuser()
    except (KeyError, OSError):
        return "inconnu"


def reset_platform_mfa(email: str) -> int:
    from app.identity.contracts import revoke_sessions

    db = new_session()
    try:
        set_tenant_context(db, PLATFORM_TENANT_ID)
        user = db.execute(
            select(UserAccount).where(UserAccount.email == email.strip().lower()).with_for_update()
        ).scalar_one_or_none()
        if user is None or not user.mfa_enabled:
            print("Refusé : compte plateforme inconnu ou sans double authentification.", file=sys.stderr)
            return 3
        user.mfa_enabled = False
        user.mfa_enabled_at = None
        user.mfa_secret_encrypted = None
        user.mfa_pending_secret_encrypted = None
        user.mfa_pending_created_at = None
        user.mfa_last_step = None
        user.mfa_recovery_hashes = []
        revoke_sessions(db, now=SystemClock().now(), reason="MFA_RESET", user_id=user.user_account_id)
        record(
            db,
            tenant_id=PLATFORM_TENANT_ID,
            action="user.mfa_reset",
            entity_type="user_account",
            entity_id=user.user_account_id,
            actor_kind="SYSTEM",
            reason=f"OPS_CLI:{_operator()}"[:200],
            changed_fields=("mfa_enabled",),
        )
        db.commit()
        print("Double authentification retirée : réenrôlement exigé à la prochaine connexion.")
        return 0
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="minefleet")
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("create-platform-admin")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True)
    sub.add_parser("seed-fictif")
    reset = sub.add_parser("reset-platform-mfa")
    reset.add_argument("--email", required=True)
    args = parser.parse_args(argv)
    if args.command == "create-platform-admin":
        password = os.environ.get("MF_BOOTSTRAP_PASSWORD")
        if not password:
            print("MF_BOOTSTRAP_PASSWORD est requis (variable d'environnement).", file=sys.stderr)
            return 2
        return create_platform_admin(args.email, args.name, password)
    if args.command == "seed-fictif":
        return seed_fictitious()
    if args.command == "reset-platform-mfa":
        return reset_platform_mfa(args.email)
    return 1


def seed_fictitious() -> int:
    from app.seed import SeedRefused, seed

    try:
        report = seed()
    except SeedRefused as exc:
        print(f"Refusé : {exc}", file=sys.stderr)
        return 3
    print("Données FICTIVES chargées :", ", ".join(f"{k}={v}" for k, v in sorted(report.counts.items())))
    print("Comptes fictifs (mots de passe affichés UNE seule fois, non stockés en clair) :")
    for workspace, email, role, password in report.accounts:
        print(f"  {workspace:18} {role:15} {email:45} {password}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
