import datetime as dt
import uuid
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from app.core.http import StrictModel

AssignmentStatus = Literal["PLANNED", "ACTIVE", "SUSPENDED", "COMPLETED", "CANCELLED"]
Compliance = Literal["COMPLIANT", "NON_COMPLIANT"]
# Codes de motif (pas de texte libre : pas de donnée personnelle dans un motif).
SuspendReason = Literal["BREAKDOWN", "DRIVER_ABSENT", "SAFETY", "WEATHER", "OPERATIONS", "OTHER"]
# SAFETY_STOP : clôture automatique sur statut de sécurité (politique « close », D-41), jamais saisi.
EndReason = Literal["END_OF_SHIFT", "BREAKDOWN", "REASSIGNMENT", "NON_COMPLIANCE", "OTHER"]
CancelReason = Literal["PLAN_CHANGED", "DRIVER_UNAVAILABLE", "VEHICLE_UNAVAILABLE", "ENTRY_ERROR", "OTHER"]


class AssignmentCreate(StrictModel):
    vehicle_id: uuid.UUID
    driver_id: uuid.UUID
    # Instants avec fuseau obligatoires (A14) : stockés en UTC, affichés au fuseau du site.
    valid_from: AwareDatetime
    valid_to: AwareDatetime | None = None
    shift_code: str | None = Field(default=None, pattern=r"^[A-Z0-9_-]{1,20}$")


class AssignmentSuspend(StrictModel):
    reason_code: SuspendReason


class AssignmentComplete(StrictModel):
    ended_at: AwareDatetime | None = None  # par défaut : maintenant (horloge serveur)
    reason_code: EndReason = "END_OF_SHIFT"


class AssignmentCancel(StrictModel):
    reason_code: CancelReason


class Issue(BaseModel):
    """Motif d'inéligibilité, de non-conformité ou avertissement ; `date` = échéance concernée."""

    code: str
    date: dt.date | None = None


class ComplianceOut(BaseModel):
    status: Compliance
    reasons: list[Issue]
    warnings: list[Issue]


class AssignmentOut(BaseModel):
    vehicle_assignment_id: uuid.UUID
    site_id: uuid.UUID
    vehicle_id: uuid.UUID
    vehicle_fleet_number: str
    driver_id: uuid.UUID
    driver_display_name: str
    driver_employee_number: str
    valid_from: datetime
    valid_to: datetime | None
    shift_code: str | None
    status: AssignmentStatus
    status_reason: str | None
    activated_at: datetime | None  # instant réel de la prise de poste (null si jamais commencée)
    # Indicateurs dérivés à la lecture (D-27), jamais stockés.
    activation_overdue: bool
    end_overdue: bool
    # Calculée pour les affectations ACTIVE seulement (US-1.25 A6) ; absente sinon.
    compliance: ComplianceOut | None = None
    # Avertissements de la création (permis bientôt expiré, prochaine échéance d'un intervalle ouvert).
    warnings: list[Issue] | None = None
    created_at: datetime
    updated_at: datetime
    row_version: int
