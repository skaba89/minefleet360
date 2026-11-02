import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from app.core.http import StrictModel

Category = Literal[
    "INJURY",
    "NEAR_MISS",
    "VEHICLE_COLLISION",
    "PROPERTY_DAMAGE",
    "ENVIRONMENT",
    "SPILL",
    "FIRE",
    "UNSAFE_CONDITION",
    "OTHER",
]
Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
IncidentStatus = Literal["REPORTED", "INVESTIGATING", "CLOSED", "CANCELLED"]
IncidentAction = Literal["START_INVESTIGATION", "NOTE", "CLOSE", "CANCEL"]
# Motifs codés (pas de texte libre : pas de donnée personnelle dans un motif).
CancelReason = Literal["DUPLICATE", "NOT_AN_INCIDENT", "ENTRY_ERROR", "OTHER"]
ActionStatus = Literal["OPEN", "DONE", "VERIFIED", "CANCELLED"]
ActionDecision = Literal["VERIFY", "REOPEN", "CANCEL"]
ActionReason = Literal["INEFFECTIVE", "INCOMPLETE", "NO_LONGER_RELEVANT", "DUPLICATE", "OTHER"]


class IncidentCreate(StrictModel):
    site_id: uuid.UUID
    category: Category
    severity: Severity
    title: str = Field(min_length=3, max_length=200)
    # Faits observés : pas de nom de victime ni de donnée médicale (consigne affichée à la saisie).
    description: str = Field(min_length=10, max_length=4000)
    occurred_at: AwareDatetime
    location_note: str | None = Field(default=None, max_length=200)
    vehicle_id: uuid.UUID | None = None
    injured_count: int = Field(default=0, ge=0, le=500)
    lost_time: bool = False
    immediate_actions: str | None = Field(default=None, max_length=2000)


class IncidentTransition(StrictModel):
    action: IncidentAction
    reason_code: CancelReason | None = None
    root_cause: str | None = Field(default=None, max_length=4000)
    investigation_summary: str | None = Field(default=None, max_length=4000)
    # Requalification pendant l'enquête (la gravité réelle est souvent connue après coup).
    severity: Severity | None = None
    category: Category | None = None


class ActionCreate(StrictModel):
    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    owner_user_id: uuid.UUID
    due_date: date


class ActionComplete(StrictModel):
    completion_note: str = Field(min_length=10, max_length=2000)


class ActionDecisionIn(StrictModel):
    action: ActionDecision
    reason_code: ActionReason | None = None


class EventOut(BaseModel):
    event_type: str
    from_status: str | None
    to_status: str
    reason: str | None
    actor_user_id: uuid.UUID
    actor_name: str | None
    occurred_at: datetime


class EvidenceOut(BaseModel):
    hse_evidence_id: uuid.UUID
    content_type: str
    size_bytes: int
    sha256: str
    uploaded_by: uuid.UUID
    uploaded_at: datetime


class ActionOut(BaseModel):
    hse_corrective_action_id: uuid.UUID
    # Exactement un parent : l'incident ou l'inspection d'origine (référence HSE-… ou INS-…).
    hse_incident_id: uuid.UUID | None
    hse_inspection_id: uuid.UUID | None
    parent_reference: str
    site_id: uuid.UUID
    title: str
    description: str | None
    owner_user_id: uuid.UUID
    owner_name: str | None
    due_date: date
    overdue: bool
    status: ActionStatus
    status_reason: str | None
    completion_note: str | None
    completed_at: datetime | None
    completed_by: uuid.UUID | None
    verified_at: datetime | None
    verified_by: uuid.UUID | None
    row_version: int


class IncidentOut(BaseModel):
    hse_incident_id: uuid.UUID
    number: int
    reference: str
    site_id: uuid.UUID
    category: Category
    severity: Severity
    title: str
    description: str
    occurred_at: datetime
    location_note: str | None
    vehicle_id: uuid.UUID | None
    vehicle_fleet_number: str | None
    injured_count: int
    lost_time: bool
    immediate_actions: str | None
    status: IncidentStatus
    status_reason: str | None
    root_cause: str | None
    investigation_summary: str | None
    reported_at: datetime
    reported_by: uuid.UUID
    reported_by_name: str | None
    closed_at: datetime | None
    closed_by: uuid.UUID | None
    open_actions: int
    overdue_actions: int
    row_version: int
    events: list[EventOut] | None = None
    actions: list[ActionOut] | None = None
    evidence: list[EvidenceOut] | None = None


class ActionOwnerOut(BaseModel):
    user_account_id: uuid.UUID
    display_name: str


class HseSummaryOut(BaseModel):
    """Indicateurs HSE de la portée lue (période glissante bornée par `since`)."""

    since: date
    incidents: int
    by_severity: dict[str, int]
    by_category: dict[str, int]
    injured: int
    lost_time_incidents: int
    open_incidents: int
    open_actions: int
    overdue_actions: int
    inspections: int
    failed_inspections: int
