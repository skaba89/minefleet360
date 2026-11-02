"""Récapitulatif HSE quotidien par e-mail (docs/LIVRAISON_NOTIFICATIONS.md).

Décision (arbitrage délégué, MATRICE_RBAC §6 point 3) : pas d'alerte en temps réel ni de SMS ; un seul
message par jour et par personne, envoyé seulement s'il y a quelque chose à faire :
- au responsable d'une action corrective OUVERTE en retard ou à échéance sous 2 jours (date du site) ;
- aux comptes HSE actifs : incidents CRITIQUES ou ÉLEVÉS non clôturés de leur périmètre.
Contenu minimal : références, échéances et lien vers l'application. Jamais de titre ni de description libre
(qui peuvent contenir des données personnelles ou médicales). Chaque envoi est audité (acteur SYSTEM).

La fonction travaille dans le contexte du tenant déjà posé par l'appelant (commande d'exploitation).
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.audit.contracts import record
from app.core.config import Settings
from app.core.email import EmailMessage, EmailSender
from app.hse.models import HseCorrectiveAction, HseIncident, HseInspection
from app.hse.service import inspection_reference, reference
from app.identity.models import UserAccount, UserRoleAssignment
from app.organization.contracts import local_date

DUE_SOON = timedelta(days=2)
MAX_LINES = 20


@dataclass
class _Digest:
    actions: list[tuple[str, date, bool]] = field(
        default_factory=list
    )  # (référence parent, échéance, en retard)
    incidents: list[tuple[str, str]] = field(default_factory=list)  # (référence, gravité)


def _lines(digest: _Digest) -> list[str]:
    lines: list[str] = []
    if digest.actions:
        lines.append("Actions correctives dont vous êtes responsable :")
        for parent, due, late in sorted(digest.actions, key=lambda a: a[1])[:MAX_LINES]:
            state = "EN RETARD" if late else "à échéance proche"
            lines.append(f"  - {parent} : échéance {due:%d/%m/%Y} ({state})")
    if digest.incidents:
        lines.append("Incidents graves non clôturés de votre périmètre :")
        severity = {"CRITICAL": "critique", "HIGH": "élevée"}
        for ref, level in digest.incidents[:MAX_LINES]:
            lines.append(f"  - {ref} (gravité {severity.get(level, level)})")
    return lines


def collect(db: Session, now: datetime) -> dict[uuid.UUID, _Digest]:
    """Éléments à signaler par compte, pour le tenant du contexte courant."""
    digests: dict[uuid.UUID, _Digest] = defaultdict(_Digest)
    today_by_site: dict[uuid.UUID, date] = {}

    def today(site_id: uuid.UUID) -> date:
        if site_id not in today_by_site:
            today_by_site[site_id] = local_date(db, site_id, now)
        return today_by_site[site_id]

    actions = (
        db.execute(
            select(HseCorrectiveAction).where(
                HseCorrectiveAction.status == "OPEN",
                HseCorrectiveAction.due_date <= (now + DUE_SOON + timedelta(days=1)).date(),
            )
        )
        .scalars()
        .all()
    )
    incident_numbers = dict(
        db.execute(
            select(HseIncident.hse_incident_id, HseIncident.number).where(
                HseIncident.hse_incident_id.in_({a.hse_incident_id for a in actions if a.hse_incident_id})
            )
        ).all()
    )
    inspection_numbers = dict(
        db.execute(
            select(HseInspection.hse_inspection_id, HseInspection.number).where(
                HseInspection.hse_inspection_id.in_(
                    {a.hse_inspection_id for a in actions if a.hse_inspection_id}
                )
            )
        ).all()
    )
    for a in actions:
        local_today = today(a.site_id)
        if a.due_date > local_today + DUE_SOON:
            continue
        parent = (
            reference(incident_numbers[a.hse_incident_id])
            if a.hse_incident_id
            else inspection_reference(inspection_numbers[a.hse_inspection_id])  # type: ignore[index]
        )
        digests[a.owner_user_id].actions.append((parent, a.due_date, a.due_date < local_today))

    serious = db.execute(
        select(HseIncident.number, HseIncident.severity, HseIncident.site_id).where(
            HseIncident.status.in_(("REPORTED", "INVESTIGATING")),
            HseIncident.severity.in_(("CRITICAL", "HIGH")),
        )
    ).all()
    if serious:
        assignments = db.execute(
            select(
                UserRoleAssignment.user_account_id, UserRoleAssignment.scope_type, UserRoleAssignment.site_id
            )
            .join(UserAccount, UserAccount.user_account_id == UserRoleAssignment.user_account_id)
            .where(
                UserRoleAssignment.role_code == "HSE",
                UserRoleAssignment.revoked_at.is_(None),
                UserRoleAssignment.valid_from <= now,
                or_(UserRoleAssignment.valid_to.is_(None), UserRoleAssignment.valid_to > now),
                UserAccount.status == "ACTIVE",
            )
        ).all()
        scope: dict[uuid.UUID, set[uuid.UUID] | None] = {}
        for user_id, scope_type, site_id in assignments:
            if scope_type == "TENANT":
                scope[user_id] = None
            elif site_id is not None:
                sites = scope.setdefault(user_id, set())
                if sites is not None:  # une attribution société couvre déjà tous les sites
                    sites.add(site_id)
        for user_id, sites in scope.items():
            for number, severity, site_id in sorted(
                serious, key=lambda r: (r.severity != "CRITICAL", r.number)
            ):
                if sites is None or site_id in sites:
                    digests[user_id].incidents.append((reference(number), severity))
    return digests


def send_digests(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    now: datetime,
    settings: Settings,
    sender: EmailSender,
    dry_run: bool,
) -> int:
    """Envoie les récapitulatifs du tenant courant ; renvoie le nombre de messages (prévus en simulation)."""
    digests = {user: d for user, d in collect(db, now).items() if d.actions or d.incidents}
    if not digests:
        return 0
    accounts = {
        u.user_account_id: u
        for u in db.execute(
            select(UserAccount).where(
                UserAccount.user_account_id.in_(digests), UserAccount.status == "ACTIVE"
            )
        ).scalars()
    }
    sent = 0
    for user_id, digest in digests.items():
        account = accounts.get(user_id)
        if account is None:
            continue
        count = len(digest.actions) + len(digest.incidents)
        if not dry_run:
            body = "\n".join(
                [
                    f"Bonjour {account.display_name},",
                    "",
                    *_lines(digest),
                    "",
                    f"Ouvrir MINEFLEET 360 : {settings.public_web_url}/hse",
                    "",
                    "Message automatique quotidien : il n'est envoyé que lorsqu'un élément vous concerne.",
                ]
            )
            sender.send(
                EmailMessage(
                    to=account.email,
                    subject=f"MINEFLEET 360 — HSE : {count} élément(s) à traiter",
                    body=body,
                    kind="HSE_DIGEST",
                )
            )
            record(
                db,
                tenant_id=tenant_id,
                action="hse.digest.sent",
                entity_type="user_account",
                entity_id=user_id,
                actor_kind="SYSTEM",
                after={"actions": len(digest.actions), "incidents": len(digest.incidents)},
            )
        sent += 1
    return sent
