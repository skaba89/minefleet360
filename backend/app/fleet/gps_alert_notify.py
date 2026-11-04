"""Notifications des alertes GPS : mise en file (dans la transaction de l'alerte) et livraison planifiée.

Règles (docs/GPS_ALERTS.md, décision du 4 novembre 2026) :
- chaque utilisateur choisit e-mail et/ou SMS (`user_alert_notification`) ; rien par défaut ;
- destinataires : comptes actifs dont un rôle en vigueur donne la lecture des alertes (`fleet.gps_alert.read`)
  sur le site de l'alerte ou toute la société ;
- **anti-avalanche** : au plus une notification par destinataire, canal, engin et type d'alerte toutes les
  30 minutes ;
- la livraison (`minefleet deliver-notifications`, chaque minute) n'a jamais lieu pendant l'ingestion GPS ;
  **un seul message par destinataire et canal** regroupe ses notifications en attente ; contenu minimal
  (type, engin, site, heure du site, lien), sans coordonnées ;
- SMS sans fournisseur configuré : notification marquée en échec (`SMS_PROVIDER_NOT_CONFIGURED`).
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.audit.contracts import record
from app.authz.matrix import load_matrix
from app.core.config import Settings
from app.core.email import EmailMessage, EmailSender
from app.core.sms import SmsMessage, SmsSender
from app.fleet.gps_alert_models import GpsAlert, NotificationOutbox, UserAlertNotification
from app.fleet.models import Vehicle
from app.identity.contracts import users_with_roles
from app.identity.models import UserAccount
from app.organization.contracts import site_timezone
from app.organization.models import Site

THROTTLE = timedelta(minutes=30)
MAX_ATTEMPTS = 5
BATCH = 200
GROUP_LINES = 20  # alertes détaillées dans un e-mail groupé ; les suivantes sont comptées
LABEL = {
    "OVERSPEED": "Excès de vitesse",
    "RESTRICTED_ZONE_ENTRY": "Entrée en zone interdite",
    "SITE_BOUNDARY_EXIT": "Sortie de la limite du site",
    "SIGNAL_LOST": "Perte de signal",
}


def _reader_roles() -> list[str]:
    return sorted(load_matrix().permissions["fleet.gps_alert.read"].grants)


def enqueue_alert_notifications(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    gps_alert_id: uuid.UUID,
    site_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    kind: str,
) -> int:
    """Une ligne par destinataire et canal choisis ; renvoie le nombre de notifications mises en file."""
    now = db.scalar(select(func.now()))
    assert now is not None
    readers = {user_id for user_id, _ in users_with_roles(db, _reader_roles(), site_id, now)}
    if not readers:
        return 0
    prefs = db.scalars(
        select(UserAlertNotification).where(
            UserAlertNotification.tenant_id == tenant_id,
            UserAlertNotification.user_account_id.in_(readers),
        )
    ).all()
    queued = 0
    for pref in prefs:
        channels = [c for c, on in (("EMAIL", pref.email_enabled), ("SMS", pref.sms_enabled)) if on]
        for channel in channels:
            recent = db.scalar(
                select(NotificationOutbox.notification_id)
                .join(
                    GpsAlert,
                    (GpsAlert.tenant_id == NotificationOutbox.tenant_id)
                    & (GpsAlert.gps_alert_id == NotificationOutbox.gps_alert_id),
                )
                .where(
                    NotificationOutbox.tenant_id == tenant_id,
                    NotificationOutbox.user_account_id == pref.user_account_id,
                    NotificationOutbox.channel == channel,
                    NotificationOutbox.created_at > now - THROTTLE,
                    GpsAlert.vehicle_id == vehicle_id,
                    GpsAlert.kind == kind,
                )
                .limit(1)
            )
            if recent is not None:
                continue
            inserted = db.execute(
                insert(NotificationOutbox)
                .values(
                    tenant_id=tenant_id,
                    user_account_id=pref.user_account_id,
                    channel=channel,
                    gps_alert_id=gps_alert_id,
                )
                .on_conflict_do_nothing(constraint="uq_no_recipient_alert")
                .returning(NotificationOutbox.notification_id)
            ).scalar_one_or_none()
            queued += inserted is not None
    return queued


@dataclass
class DeliveryReport:
    sent: int = 0  # messages envoyés (un message peut regrouper plusieurs alertes)
    failed: int = 0
    retried: int = 0


def _line(alert: GpsAlert, fleet: str, site: str, when: str) -> str:
    detail = ""
    if alert.kind == "OVERSPEED" and alert.peak_speed_kmh is not None:
        detail = f" ({alert.peak_speed_kmh:.0f} km/h pour {alert.speed_limit_kmh} autorisés)"
    return f"{LABEL[alert.kind]}{detail}, engin {fleet}, site {site}, {when}"


def _message(lines: list[str], kinds: list[str], link: str, channel: str) -> tuple[str, str]:
    """(objet, texte) : une alerte, ou plusieurs regroupées en un seul message (anti-avalanche).

    SMS groupé : résumé par type, court (un message facturé) ; e-mail groupé : alertes détaillées.
    """
    if len(lines) == 1:
        return f"MineFleet 360 — {LABEL[kinds[0]]}", f"MineFleet 360 : {lines[0]}. {link}"
    subject = f"MineFleet 360 — {len(lines)} nouvelles alertes GPS"
    if channel == "SMS":
        counts = [f"{kinds.count(k)} {LABEL[k].lower()}" for k in LABEL if k in kinds]
        return subject, f"MineFleet 360 : {len(lines)} alertes GPS ({', '.join(counts)}). {link}"
    shown = lines[:GROUP_LINES]
    rest = len(lines) - len(shown)
    more = f"\n… et {rest} autre(s)" if rest else ""
    return subject, f"MineFleet 360 : {len(lines)} nouvelles alertes GPS\n" + "\n".join(
        shown
    ) + f"{more}\n{link}"


def deliver_pending(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    settings: Settings,
    email_sender: EmailSender,
    sms_sender: SmsSender | None,
) -> DeliveryReport:
    """Un seul message par destinataire et canal, regroupant toutes ses notifications en attente."""
    report = DeliveryReport()
    rows = db.scalars(
        select(NotificationOutbox)
        .where(NotificationOutbox.tenant_id == tenant_id, NotificationOutbox.status == "PENDING")
        .order_by(NotificationOutbox.created_at)
        .limit(BATCH)
        .with_for_update(skip_locked=True)
    ).all()
    link = settings.public_web_url.rstrip("/") + "/flotte-gps/alertes"
    groups: dict[tuple[uuid.UUID, str], list[NotificationOutbox]] = {}
    for row in rows:
        groups.setdefault((row.user_account_id, row.channel), []).append(row)
    for (user_id, channel), items in groups.items():
        lines: list[str] = []
        kinds: list[str] = []
        sites: set[uuid.UUID] = set()
        for row in items:
            alert = db.get(GpsAlert, row.gps_alert_id)
            assert alert is not None
            sites.add(alert.site_id)
            fleet = db.scalar(
                select(Vehicle.fleet_number).where(
                    Vehicle.tenant_id == tenant_id, Vehicle.vehicle_id == alert.vehicle_id
                )
            )
            site = db.scalar(
                select(Site.name).where(Site.tenant_id == tenant_id, Site.site_id == alert.site_id)
            )
            when = alert.opened_at.astimezone(site_timezone(db, alert.site_id)).strftime("%d/%m/%Y %H:%M")
            lines.append(_line(alert, fleet or "?", site or "?", when))
            kinds.append(alert.kind)
        subject, body = _message(lines, kinds, link, channel)
        error: str | None = None
        try:
            if channel == "EMAIL":
                email = db.scalar(select(UserAccount.email).where(UserAccount.user_account_id == user_id))
                if not email:
                    error = "NO_EMAIL"
                else:
                    email_sender.send(EmailMessage(to=email, subject=subject, body=body, kind="GPS_ALERT"))
            else:
                phone = db.scalar(
                    select(UserAlertNotification.phone_e164).where(
                        UserAlertNotification.tenant_id == tenant_id,
                        UserAlertNotification.user_account_id == user_id,
                    )
                )
                if sms_sender is None:
                    error = "SMS_PROVIDER_NOT_CONFIGURED"
                elif not phone:
                    error = "NO_PHONE"
                else:
                    sms_sender.send(SmsMessage(to=phone, body=body, kind="GPS_ALERT"))
        except OSError:
            error = "TRANSPORT_ERROR"
        sent_at = db.scalar(select(func.now()))  # lu avant toute modification (pas d'écriture partielle)
        for row in items:
            row.attempts += 1
            if error is None:
                row.sent_at = sent_at
                row.status = "SENT"
            elif error == "TRANSPORT_ERROR" and row.attempts < MAX_ATTEMPTS:
                row.last_error_code = error
            else:
                row.status = "FAILED"
                row.last_error_code = error
        if error is None:
            report.sent += 1
        elif error == "TRANSPORT_ERROR" and items[0].attempts < MAX_ATTEMPTS:
            report.retried += 1
        else:
            report.failed += 1
        record(
            db,
            tenant_id=tenant_id,
            actor_kind="SYSTEM",
            site_id=next(iter(sites)) if len(sites) == 1 else None,
            action="fleet.gps.alert.notify",
            entity_type="notification_outbox",
            entity_id=items[0].notification_id,
            outcome="SUCCESS" if error is None else "FAILURE",
            reason=error,
            after={"channel": channel, "alerts": len(items)},
        )
    db.flush()
    return report
