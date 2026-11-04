"""Commandes d'exploitation (rôle applicatif mf_app, jamais le propriétaire du schéma).

minefleet create-platform-admin --email <e-mail> --name "<nom>"
    US-1.32 : premier PLATFORM_ADMIN ; mot de passe lu dans MF_BOOTSTRAP_PASSWORD (jamais en argument).
minefleet seed-fictif
    US-1.30 : jeu de données FICTIF de recette (refusé en production et en cas de réexécution).
minefleet purge-gps [--days N] [--apply]
    Rétention GPS : compte (par défaut) ou supprime (--apply) les positions plus anciennes que N jours
    (MF_GPS_RETENTION_DAYS, 180 par défaut, 7 minimum). Seule commande exécutée avec le propriétaire du schéma
    (MF_OWNER_PASSWORD), comme les migrations : la fonction de purge n'est pas accessible au rôle applicatif.
minefleet send-hse-digest [--dry-run]
minefleet evaluate-preventive [--dry-run]
    Récapitulatif HSE quotidien par e-mail (actions en retard ou proches, incidents graves ouverts), par
    société, audité ; --dry-run compte les messages sans rien envoyer. À planifier une fois par jour.
minefleet demo seed --profile small|standard|large [--seed 42] [--anchor AAAA-MM-JJ] --credentials-out <f>
minefleet demo verify [--anchor AAAA-MM-JJ]
minefleet demo reset-credentials --tenant <code DEMO> --credentials-out <fichier>
minefleet demo live-feed [--api-url http://127.0.0.1:8000] [--interval 15] [--duration 60]
    Environnement de DÉMONSTRATION (docs/DEMO_DATA_ARCHITECTURE.md) : refusé en production et sur toute base
    contenant un tenant client non DEMO ; identifiants écrits dans un nouveau fichier 600, jamais affichés.
minefleet reset-platform-mfa --email <e-mail>
    C-03 : retire le second facteur d'un PLATFORM_ADMIN qui a perdu téléphone ET codes de récupération
    (aucun compte au-dessus de lui ne peut le faire par l'API). Sessions fermées, action auditée.
"""

import argparse
import getpass
import os
import sys

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

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


def purge_gps(days: int | None, apply: bool) -> int:
    from datetime import timedelta

    from sqlalchemy import create_engine, text

    settings = get_settings()
    retention = days if days is not None else settings.gps_retention_days
    if retention < 7:
        print("Refusé : 7 jours d'historique minimum.", file=sys.stderr)
        return 2
    cutoff = SystemClock().now() - timedelta(days=retention)
    engine = create_engine(settings.database_url(owner=True), pool_size=1, max_overflow=0)
    try:
        with engine.begin() as conn:
            count = conn.execute(
                text("SELECT app.purge_gps_positions(:cutoff, :dry)"), {"cutoff": cutoff, "dry": not apply}
            ).scalar_one()
    finally:
        engine.dispose()
    verb = "supprimées" if apply else "à supprimer (simulation, ajouter --apply)"
    print(f"Positions GPS antérieures au {cutoff:%Y-%m-%d %H:%M} UTC {verb} : {count}")
    return 0


def send_hse_digest(dry_run: bool) -> int:
    from app.core.email import build_email_sender
    from app.hse.digest import send_digests
    from app.organization.models import Tenant

    settings = get_settings()
    sender = build_email_sender(settings)
    now = SystemClock().now()
    db = new_session()
    total = failures = 0
    try:
        set_tenant_context(db, PLATFORM_TENANT_ID)
        tenants = list(
            db.execute(
                select(Tenant.tenant_id).where(Tenant.kind == "CUSTOMER", Tenant.status == "ACTIVE")
            ).scalars()
        )
        db.commit()
        for tenant_id in tenants:
            # Une société en échec n'empêche pas les suivantes ; son audit est annulé avec la transaction.
            try:
                set_tenant_context(db, tenant_id)
                total += send_digests(
                    db, tenant_id=tenant_id, now=now, settings=settings, sender=sender, dry_run=dry_run
                )
                db.commit()
            except (SQLAlchemyError, OSError):  # base indisponible ou échec SMTP (smtplib lève des OSError)
                db.rollback()
                failures += 1
                print(f"Échec du récapitulatif pour une société ({tenant_id}).", file=sys.stderr)
    finally:
        db.close()
    verb = "à envoyer (simulation)" if dry_run else "envoyés"
    print(f"Récapitulatifs HSE {verb} : {total} ; sociétés en échec : {failures}")
    return 1 if failures else 0


def evaluate_preventive(dry_run: bool) -> int:
    """Tâche quotidienne : échéances préventives de chaque société active (acteur SYSTEM, idempotent)."""
    from app.maintenance.preventive_daily import evaluate_tenant_dues
    from app.organization.models import Tenant

    now = SystemClock().now()
    db = new_session()
    created = due = failures = 0
    try:
        set_tenant_context(db, PLATFORM_TENANT_ID)
        tenants = list(
            db.execute(
                select(Tenant.tenant_id).where(Tenant.kind == "CUSTOMER", Tenant.status == "ACTIVE")
            ).scalars()
        )
        db.commit()
        for tenant_id in tenants:
            # Une société en échec n'empêche pas les suivantes ; sa transaction est annulée.
            try:
                set_tenant_context(db, tenant_id)
                summary = evaluate_tenant_dues(db, tenant_id, now, dry_run=dry_run)
                if dry_run:
                    db.rollback()
                else:
                    db.commit()
                created += summary.created
                due += summary.due_now
            except SQLAlchemyError:
                db.rollback()
                failures += 1
                print(f"Échec de l'évaluation préventive pour une société ({tenant_id}).", file=sys.stderr)
    finally:
        db.close()
    mode = " (simulation : rien n'est enregistré)" if dry_run else ""
    print(f"Échéances préventives dues : {due} ; créées : {created} ; sociétés en échec : {failures}{mode}")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="minefleet")
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("create-platform-admin")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True)
    sub.add_parser("seed-fictif")
    purge = sub.add_parser("purge-gps")
    purge.add_argument("--days", type=int, default=None)
    purge.add_argument("--apply", action="store_true")
    digest = sub.add_parser("send-hse-digest")
    digest.add_argument("--dry-run", action="store_true")
    preventive = sub.add_parser("evaluate-preventive")
    preventive.add_argument("--dry-run", action="store_true")
    reset = sub.add_parser("reset-platform-mfa")
    reset.add_argument("--email", required=True)
    from app.demo import cli as demo_cli

    demo_cli.register(sub)
    args = parser.parse_args(argv)
    if args.command == "demo":
        return demo_cli.run(args)
    if args.command == "create-platform-admin":
        password = os.environ.get("MF_BOOTSTRAP_PASSWORD")
        if not password:
            print("MF_BOOTSTRAP_PASSWORD est requis (variable d'environnement).", file=sys.stderr)
            return 2
        return create_platform_admin(args.email, args.name, password)
    if args.command == "seed-fictif":
        return seed_fictitious()
    if args.command == "purge-gps":
        return purge_gps(args.days, args.apply)
    if args.command == "send-hse-digest":
        return send_hse_digest(args.dry_run)
    if args.command == "evaluate-preventive":
        return evaluate_preventive(args.dry_run)
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
