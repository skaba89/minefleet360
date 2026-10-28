import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from app.core.http import StrictModel

Priority = Literal["CRITICAL", "HIGH", "NORMAL", "LOW"]
Symptom = Literal[
    "ENGINE",
    "BRAKES",
    "TYRES",
    "HYDRAULICS",
    "ELECTRICAL",
    "TRANSMISSION",
    "STEERING",
    "COOLING",
    "BODY",
    "SAFETY_EQUIPMENT",
    "SERVICE",
    "OTHER",
]
WorkOrderStatus = Literal[
    "REQUESTED",
    "APPROVED",
    "ASSIGNED",
    "IN_PROGRESS",
    "AWAITING_PARTS",
    "QUALITY_CHECK",
    "CLOSED",
    "REJECTED",
    "CANCELLED",
]
# Motifs codés (pas de texte libre : pas de donnée personnelle dans un motif).
WorkOrderReason = Literal[
    "DUPLICATE",
    "NOT_A_FAULT",
    "OUT_OF_SCOPE",
    "PLAN_CHANGED",
    "PARTS_ORDERED",
    "PARTS_OUT_OF_STOCK",
    "SUPPLIER_DELAY",
    "FAULT_PERSISTS",
    "INCOMPLETE_WORK",
    "SAFETY_CONCERN",
    "OTHER",
]
Decision = Literal["APPROVE", "REJECT", "ASSIGN", "CANCEL", "QC_PASS", "QC_FAIL"]
Progress = Literal["START", "AWAIT_PARTS", "RESUME", "SUBMIT", "NOTE"]


class WorkOrderCreate(StrictModel):
    vehicle_id: uuid.UUID
    symptom_code: Symptom
    priority: Priority = "NORMAL"
    # Texte technique : aucune donnée personnelle (consigne affichée à la saisie).
    description: str | None = Field(default=None, max_length=2000)
    # Panne bloquante : véhicule immobilisé et mission en cours suspendue (D-44).
    immobilize: bool = False
    mission_id: uuid.UUID | None = None


class WorkOrderDecision(StrictModel):
    action: Decision
    reason_code: WorkOrderReason | None = None
    assigned_to: uuid.UUID | None = None
    expected_ready_at: AwareDatetime | None = None


class WorkOrderProgress(StrictModel):
    action: Progress
    reason_code: WorkOrderReason | None = None
    diagnosis: str | None = Field(default=None, max_length=4000)
    work_done: str | None = Field(default=None, max_length=4000)
    parts_note: str | None = Field(default=None, max_length=2000)


class LabourCreate(StrictModel):
    minutes: int = Field(ge=1, le=960)
    performed_on: date
    # Par défaut : l'auteur de la saisie.
    mechanic_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=500)


class EventOut(BaseModel):
    event_type: str
    from_status: str | None
    to_status: str
    reason: str | None
    # Identités masquées (None) hors atelier, exploitation qui décide et audit (revue L3A-R-13).
    actor_user_id: uuid.UUID | None
    actor_name: str | None
    subject_user_id: uuid.UUID | None
    subject_name: str | None
    occurred_at: datetime


class LabourOut(BaseModel):
    work_order_labour_id: uuid.UUID
    mechanic_id: uuid.UUID
    mechanic_name: str | None
    minutes: int
    performed_on: date
    note: str | None
    recorded_at: datetime


class WorkOrderOut(BaseModel):
    work_order_id: uuid.UUID
    number: int
    # Numéro lisible : OT-000123.
    reference: str
    site_id: uuid.UUID
    vehicle_id: uuid.UUID
    vehicle_fleet_number: str
    mission_id: uuid.UUID | None
    kind: str
    priority: str
    symptom_code: str
    description: str | None
    immobilize: bool
    status: WorkOrderStatus
    status_reason: str | None
    assigned_to: uuid.UUID | None
    assigned_name: str | None
    expected_ready_at: datetime | None
    diagnosis: str | None
    work_done: str | None
    parts_note: str | None
    reported_at: datetime
    reported_by: uuid.UUID | None
    approved_at: datetime | None
    started_at: datetime | None
    submitted_at: datetime | None
    closed_at: datetime | None
    closed_by: uuid.UUID | None
    labour_minutes: int
    row_version: int
    events: list[EventOut] | None = None
    labour: list[LabourOut] | None = None


class MechanicOut(BaseModel):
    user_account_id: uuid.UUID
    display_name: str
