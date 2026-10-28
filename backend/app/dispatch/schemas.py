import uuid
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from app.core.http import StrictModel

LocationKind = Literal["LOADING_POINT", "DUMP_POINT", "STOCKPILE", "CRUSHER", "WEIGHBRIDGE", "PORT", "OTHER"]
RefStatus = Literal["ACTIVE", "INACTIVE"]
MissionStatus = Literal[
    "PLANNED",
    "ASSIGNED",
    "EN_ROUTE_EMPTY",
    "LOADING",
    "EN_ROUTE_LOADED",
    "UNLOADING",
    "SUSPENDED",
    "COMPLETED",
    "CANCELLED",
]
# Événements déclarés par le dispatcher (2a) ; CREATED est écrit par le serveur.
EventType = Literal[
    "DEPARTED",
    "ARRIVED_LOADING",
    "LOADED",
    "ARRIVED_UNLOADING",
    "UNLOADED",
    "COMPLETED",
    "SUSPENDED",
    "RESUMED",
    "REASSIGNED",
    "CANCELLED",
]
# Motifs codés (pas de texte libre : pas de donnée personnelle dans un motif).
MissionReason = Literal[
    "BREAKDOWN",
    "HSE_STOP",
    "WEATHER",
    "ROAD_BLOCKED",
    "DRIVER_UNAVAILABLE",
    "PLAN_CHANGED",
    "ENTRY_ERROR",
    "OTHER",
]


class LocationCreate(StrictModel):
    site_id: uuid.UUID
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    name: str = Field(min_length=2, max_length=120)
    kind: LocationKind


class LocationUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    kind: LocationKind | None = None
    status: RefStatus | None = None


class LocationOut(BaseModel):
    site_location_id: uuid.UUID
    site_id: uuid.UUID
    code: str
    name: str
    kind: str
    status: str
    row_version: int


class MaterialCreate(StrictModel):
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    name: str = Field(min_length=2, max_length=120)
    is_waste: bool = False


class MaterialUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    is_waste: bool | None = None
    status: RefStatus | None = None


class MaterialOut(BaseModel):
    material_id: uuid.UUID
    code: str
    name: str
    is_waste: bool
    status: str
    row_version: int


class MissionCreate(StrictModel):
    vehicle_assignment_id: uuid.UUID
    origin_location_id: uuid.UUID
    destination_location_id: uuid.UUID
    material_id: uuid.UUID
    planned_start: AwareDatetime
    due_at: AwareDatetime | None = None
    planned_rotations: int | None = Field(default=None, ge=1, le=500)
    notes: str | None = Field(default=None, max_length=1000)
    # Renvoi après coupure réseau : même identifiant → même mission, aucun doublon (revue L2A-R-08).
    client_request_id: uuid.UUID | None = None


class MissionEventCreate(StrictModel):
    event_type: EventType
    # Heure déclarée (fuseau obligatoire) ; par défaut l'heure du serveur. Bornée (RM-083).
    occurred_at: AwareDatetime | None = None
    # Identifiant fourni par le client : un renvoi après coupure réseau ne crée pas de doublon (RM-084).
    client_event_id: uuid.UUID | None = None
    reason_code: MissionReason | None = None
    # Réaffectation (US-2.03) : nouvelle affectation du même site.
    vehicle_assignment_id: uuid.UUID | None = None


class EventOut(BaseModel):
    mission_event_id: uuid.UUID
    event_type: str
    # Affectation en vigueur après l'événement : retrace les réaffectations (revue L2A-R-01).
    vehicle_assignment_id: uuid.UUID
    from_status: str | None
    to_status: str
    occurred_at: datetime
    recorded_at: datetime
    source: str
    reason: str | None


class RotationOut(BaseModel):
    rotation_id: uuid.UUID
    sequence: int
    vehicle_id: uuid.UUID
    loading_started_at: datetime
    loaded_at: datetime | None
    unloading_started_at: datetime | None
    unloaded_at: datetime | None
    status: str
    # Durée du cycle complet en secondes (dérivée), jamais un tonnage.
    cycle_seconds: int | None


class MissionOut(BaseModel):
    mission_id: uuid.UUID
    site_id: uuid.UUID
    vehicle_assignment_id: uuid.UUID
    vehicle_id: uuid.UUID
    vehicle_fleet_number: str
    # Données nominatives : None si l'appelant ne lit pas les affectations sur ce site (D-10, L2A-R-02).
    driver_id: uuid.UUID | None
    driver_display_name: str | None
    origin_location_id: uuid.UUID
    origin_name: str
    destination_location_id: uuid.UUID
    destination_name: str
    material_id: uuid.UUID
    material_name: str
    planned_start: datetime
    due_at: datetime | None
    planned_rotations: int | None
    status: MissionStatus
    status_before_suspension: str | None
    status_reason: str | None
    notes: str | None
    rotations_completed: int
    # Indicateur dérivé : échéance dépassée sans mission terminée.
    overdue: bool
    created_at: datetime
    updated_at: datetime
    row_version: int
    events: list[EventOut] | None = None
    rotations: list[RotationOut] | None = None


# --- Pesées (lot 2b, PLAN_LOT2 §7) ---------------------------------------------------------------------

WeighingSource = Literal["WEIGHBRIDGE", "MANUAL_DEGRADED"]
WeighingStatus = Literal["VALID", "PENDING_APPROVAL", "VOIDED"]
# Motifs codés : pas de texte libre (pas de donnée personnelle dans un motif).
DegradedReason = Literal["WEIGHBRIDGE_DOWN", "POWER_OUTAGE", "CALIBRATION", "NETWORK_DOWN", "OTHER"]
VoidReason = Literal[
    "ENTRY_ERROR", "WRONG_ROTATION", "WRONG_VEHICLE", "DUPLICATE", "CALIBRATION_ISSUE", "OTHER"
]


class WeighingFields(StrictModel):
    weighbridge_location_id: uuid.UUID
    ticket_number: str = Field(pattern=r"^[A-Za-z0-9/_-]{1,40}$")
    source: WeighingSource = "WEIGHBRIDGE"
    degraded_reason: DegradedReason | None = None
    weighed_at: AwareDatetime
    # Kilogrammes entiers (RM-071) ; le net est calculé par la base, jamais saisi.
    gross_kg: int = Field(gt=0, le=500_000)
    tare_kg: int = Field(gt=0, le=500_000)


class WeighingCreate(WeighingFields):
    rotation_id: uuid.UUID


class WeighingCorrection(WeighingFields):
    reason_code: VoidReason
    # Facultatif : rattacher la pesée corrigée à une autre rotation (erreur de rotation).
    rotation_id: uuid.UUID | None = None


class WeighingVoid(StrictModel):
    reason_code: VoidReason


class WeighingDecisionOut(BaseModel):
    decision: str
    reason: str | None
    decided_by: uuid.UUID
    decided_at: datetime


class WeighingOut(BaseModel):
    weighing_ticket_id: uuid.UUID
    site_id: uuid.UUID
    mission_id: uuid.UUID
    rotation_id: uuid.UUID
    rotation_sequence: int
    vehicle_id: uuid.UUID
    vehicle_fleet_number: str
    material_name: str
    weighbridge_location_id: uuid.UUID
    weighbridge_name: str
    ticket_number: str
    source: str
    degraded_reason: str | None
    weighed_at: datetime
    gross_kg: int
    tare_kg: int
    net_kg: int
    rated_payload_kg: int | None
    # Net au-delà de la capacité nominale × seuil (RM-076) : alerte HSE.
    overload: bool
    status: WeighingStatus
    replaces_ticket_id: uuid.UUID | None
    replaced_by_ticket_id: uuid.UUID | None
    recorded_by: uuid.UUID
    recorded_at: datetime
    decisions: list[WeighingDecisionOut]


class IndicatorRow(BaseModel):
    """Activité d'un site pour une matière sur la période : mesuré, en attente et estimé SÉPARÉS (RM-072)."""

    site_id: uuid.UUID
    material_id: uuid.UUID
    material_name: str
    missions_completed: int
    rotations_completed: int
    avg_cycle_seconds: int | None
    # Cycles plus courts que le minimum paramétré : à vérifier (revue L2A-R-04).
    short_cycles: int
    measured_net_kg: int
    measured_rotations: int
    pending_net_kg: int
    pending_rotations: int
    # Capacité nominale × rotations sans aucune pesée : ESTIMATION, jamais additionnée au mesuré.
    estimated_kg: int
    estimated_rotations: int
    rotations_without_estimate: int
    overload_tickets: int


class IndicatorsOut(BaseModel):
    period_start: datetime
    period_end: datetime
    rows: list[IndicatorRow]
