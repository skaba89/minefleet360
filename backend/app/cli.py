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
minefleet sweep-gps-signal
minefleet deliver-notifications
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
import uuid
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

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


def _for_each_tenant(
    label: str, work: Callable[[Session, uuid.UUID], int], *, keep: bool = True
) -> tuple[int, int]:
    """Tâche planifiée : `work` pour chaque société active, sous son contexte RLS, une transaction chacune.

    Une société en échec est annulée sans bloquer les suivantes. Renvoie (total, sociétés en échec).
    `keep=False` (simulation) : chaque transaction est annulée.
    """
    from app.organization.models import Tenant

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
            try:
                set_tenant_context(db, tenant_id)
                total += work(db, tenant_id)
                if keep:
                    db.commit()
                else:
                    db.rollback()
            except SQLAlchemyError:
                db.rollback()
                failures += 1
                print(f"Échec ({label}) pour une société ({tenant_id}).", file=sys.stderr)
    finally:
        db.close()
    return total, failures


def evaluate_preventive(dry_run: bool) -> int:
    """Tâche quotidienne : échéances préventives de chaque société active (acteur SYSTEM, idempotent)."""
    from app.maintenance.preventive_daily import evaluate_tenant_dues

    now = SystemClock().now()
    due = 0

    def work(db: Session, tenant_id: uuid.UUID) -> int:
        nonlocal due
        summary = evaluate_tenant_dues(db, tenant_id, now, dry_run=dry_run)
        due += summary.due_now
        return summary.created

    created, failures = _for_each_tenant("évaluation préventive", work, keep=not dry_run)
    mode = " (simulation : rien n'est enregistré)" if dry_run else ""
    print(f"Échéances préventives dues : {due} ; créées : {created} ; sociétés en échec : {failures}{mode}")
    return 1 if failures else 0


def sweep_gps_signal() -> int:
    """Tâche toutes les 5 min : alertes de perte de signal GPS (acteur SYSTEM, une ouverte par engin)."""
    from app.fleet.gps_signal_sweep import sweep_tenant_signal_loss

    now = SystemClock().now()
    opened, failures = _for_each_tenant(
        "perte de signal GPS", lambda db, tenant_id: sweep_tenant_signal_loss(db, tenant_id, now)
    )
    print(f"Alertes de perte de signal ouvertes : {opened} ; sociétés en échec : {failures}")
    return 1 if failures else 0


def deliver_notifications() -> int:
    """Tâche chaque minute : notifications d'alertes GPS en attente (e-mail, SMS ; acteur SYSTEM)."""
    from app.core.email import build_email_sender
    from app.core.sms import build_sms_sender
    from app.fleet.gps_alert_notify import deliver_pending

    settings = get_settings()
    email_sender, sms_sender = build_email_sender(settings), build_sms_sender(settings)
    failed = 0

    def work(db: Session, tenant_id: uuid.UUID) -> int:
        nonlocal failed
        report = deliver_pending(
            db, tenant_id, settings=settings, email_sender=email_sender, sms_sender=sms_sender
        )
        failed += report.failed
        return report.sent

    sent, failures = _for_each_tenant("notifications d'alertes GPS", work)
    print(f"Notifications envoyées : {sent} ; en échec définitif : {failed} ; sociétés en échec : {failures}")
    return 1 if failures else 0


def reseal_mfa_secrets(apply: bool) -> int:
    """Rotation de MF_MFA_ENCRYPTION_KEY : rechiffre sous la clé courante les secrets TOTP encore sous
    l'ancienne (MF_MFA_ENCRYPTION_KEY_PREVIOUS). Toutes les sociétés, plateforme comprise. Simulation sans
    --apply. Aucun secret affiché ; une trace d'audit SYSTEM par société modifiée."""
    from app.core.secretbox import reseal
    from app.organization.models import Tenant

    settings = get_settings()
    if settings.mfa_encryption_key is None or settings.mfa_encryption_key_previous is None:
        print(
            "Refusé : MF_MFA_ENCRYPTION_KEY et MF_MFA_ENCRYPTION_KEY_PREVIOUS sont requis.", file=sys.stderr
        )
        return 2
    counts = {"current": 0, "resealed": 0, "unreadable": 0}
    recovery_users = 0
    db = new_session()
    try:
        set_tenant_context(db, PLATFORM_TENANT_ID)
        tenants = list(db.execute(select(Tenant.tenant_id)).scalars())
        db.commit()
        for tenant_id in tenants:
            set_tenant_context(db, tenant_id)
            changed = 0
            users = db.execute(
                select(UserAccount)
                .where(
                    UserAccount.tenant_id == tenant_id,
                    (UserAccount.mfa_secret_encrypted.is_not(None))
                    | (UserAccount.mfa_pending_secret_encrypted.is_not(None)),
                )
                .with_for_update()
            ).scalars()
            for user in users:
                for attribute, purpose in (
                    ("mfa_secret_encrypted", "mfa"),
                    ("mfa_pending_secret_encrypted", "mfa-pending"),
                ):
                    sealed = getattr(user, attribute)
                    if sealed is None:
                        continue
                    context = f"{purpose}:{user.tenant_id}:{user.user_account_id}"
                    value, state = reseal(sealed, context=context, settings=settings)
                    counts[state] += 1
                    if state == "resealed":
                        setattr(user, attribute, value)
                        changed += 1
                if user.mfa_enabled and user.mfa_recovery_hashes:
                    recovery_users += 1
            if changed and apply:
                record(
                    db,
                    tenant_id=tenant_id,
                    action="security.mfa_key_rotated",
                    entity_type="tenant",
                    entity_id=tenant_id,
                    actor_kind="SYSTEM",
                    reason=f"OPS_CLI:{_operator()}"[:200],
                    after={"resealed": changed},
                )
            if apply:
                db.commit()
            else:
                db.rollback()
    finally:
        db.close()
    mode = "" if apply else " (simulation : rien n'est enregistré, ajouter --apply)"
    print(
        f"Secrets TOTP : déjà sous la clé courante {counts['current']} ; rechiffrés {counts['resealed']} ; "
        f"illisibles {counts['unreadable']}{mode}"
    )
    print(
        f"Comptes avec codes de récupération : {recovery_users}. Ces codes ne sont pas rechiffrables : "
        "garder MF_MFA_ENCRYPTION_KEY_PREVIOUS jusqu'à leur renouvellement, "
        "ou accepter qu'ils ne valent plus."
    )
    return 3 if counts["unreadable"] else 0


def change_iot_entitlement(tenant_id: uuid.UUID, enabled: bool, reason: str, apply: bool) -> int:
    """Owner-only operation; entitlement and audit are committed together."""
    from sqlalchemy import create_engine, text

    reason = reason.strip()
    if not reason or len(reason) > 200:
        print("Refusé : motif obligatoire (200 caractères maximum).", file=sys.stderr)
        return 2
    engine = create_engine(get_settings().database_url(owner=True), pool_size=1, max_overflow=0)
    try:
        with Session(engine) as db:
            set_tenant_context(db, tenant_id)
            params = {"t": tenant_id, "enabled": enabled}
            if db.scalar(text("SELECT tenant_id FROM tenant WHERE tenant_id = :t"), params) is None:
                print("Refusé : société cliente inconnue.", file=sys.stderr)
                return 3
            db.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended('iot.entitlement:' || :key, 0))"),
                {"key": str(tenant_id)},
            )
            before = db.scalar(
                text("SELECT provisioning_enabled FROM iot_entitlement WHERE tenant_id = :t"), params
            ) is True
            if before == enabled:
                print("Aucun changement nécessaire.")
                return 0
            if not apply:
                print(f"Simulation : {tenant_id}, {before} -> {enabled}.")
                return 0
            db.execute(
                text(
                    "INSERT INTO iot_entitlement (tenant_id, provisioning_enabled) VALUES (:t, :enabled) "
                    "ON CONFLICT (tenant_id) DO UPDATE SET "
                    "provisioning_enabled = EXCLUDED.provisioning_enabled, "
                    "updated_at = now()"
                ),
                params,
            )
            db.execute(
                text(
                    "INSERT INTO audit_event (tenant_id, actor_kind, action, "
                    "entity_type, entity_id, outcome, "
                    "reason, changed_fields, before_data, after_data) "
                    "VALUES (:t, 'SYSTEM', 'iot.entitlement.change', 'iot_entitlement', :t, 'SUCCESS', "
                    ":reason, ARRAY['provisioning_enabled'], "
                    "jsonb_build_object('provisioning_enabled', CAST(:before AS boolean)), "
                    "jsonb_build_object('provisioning_enabled', CAST(:enabled AS boolean)))"
                ),
                {**params, "before": before, "reason": f"OPS_CLI:{_operator()}: {reason}"[:300]},
            )
            db.commit()
            print(f"Activation IoT : {tenant_id}, {before} -> {enabled}.")
            return 0
    finally:
        engine.dispose()


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
    sub.add_parser("sweep-gps-signal")
    sub.add_parser("deliver-notifications")
    reset = sub.add_parser("reset-platform-mfa")
    reset.add_argument("--email", required=True)
    reseal_cmd = sub.add_parser("reseal-mfa-secrets")
    reseal_cmd.add_argument("--apply", action="store_true")
    entitlement = sub.add_parser("iot-entitlement")
    entitlement.add_argument("--tenant-id", type=uuid.UUID, required=True)
    mode = entitlement.add_mutually_exclusive_group(required=True)
    mode.add_argument("--enable", action="store_true")
    mode.add_argument("--disable", action="store_true")
    entitlement.add_argument("--reason", required=True)
    entitlement.add_argument("--apply", action="store_true")
    from app.demo import cli as demo_cli

    demo_cli.register(sub)
    args = parser.parse_args(argv)
    if args.command == "iot-entitlement":
        return change_iot_entitlement(args.tenant_id, args.enable, args.reason, args.apply)
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
    if args.command == "sweep-gps-signal":
        return sweep_gps_signal()
    if args.command == "deliver-notifications":
        return deliver_notifications()
    if args.command == "reset-platform-mfa":
        return reset_platform_mfa(args.email)
    if args.command == "reseal-mfa-secrets":
        return reseal_mfa_secrets(args.apply)
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
