import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from app.core.http import StrictModel

VehicleStatus = Literal["AVAILABLE", "IN_MAINTENANCE", "IMMOBILIZED", "OUT_OF_SERVICE", "RETIRED"]
OperationalStatus = Literal["AVAILABLE", "IN_MAINTENANCE", "IMMOBILIZED", "OUT_OF_SERVICE"]
Ownership = Literal["OWNED", "LEASED", "SUBCONTRACTED"]
FuelType = Literal["DIESEL", "PETROL", "ELECTRIC", "OTHER"]
# Codes de motif (pas de texte libre : pas de donnée personnelle dans un motif).
ReasonCode = Literal[
    "BREAKDOWN",
    "ACCIDENT",
    "DOCUMENT_EXPIRED",
    "AWAITING_PARTS",
    "SAFETY_BAN",
    "PREVENTIVE_MAINTENANCE",
    "RECEPTION_IN_PROGRESS",
    "END_OF_LIFE",
    "TOTAL_LOSS",
    "SOLD",
    "OTHER",
]


class VehicleCategoryOut(BaseModel):
    vehicle_category_id: uuid.UUID
    code: str
    label_fr: str
    family: str
    requires_driver: bool
    requires_internal_authorization: bool
    has_odometer: bool
    has_hour_meter: bool
    is_active: bool
    required_license_categories: list[str]


class VehicleCreate(StrictModel):
    site_id: uuid.UUID
    vehicle_category_id: uuid.UUID
    fleet_number: str = Field(pattern=r"^\S{1,30}$")
    registration_number: str | None = Field(default=None, min_length=2, max_length=20)
    serial_number: str | None = Field(default=None, min_length=1, max_length=60)
    make: str | None = Field(default=None, max_length=60)
    model: str | None = Field(default=None, max_length=60)
    model_year: int | None = Field(default=None, ge=1950, le=2100)
    ownership_type: Ownership = "OWNED"
    fuel_type: FuelType | None = None
    rated_payload_kg: int | None = Field(default=None, gt=0, le=1_000_000)
    commissioned_on: date | None = None
    notes: str | None = Field(default=None, max_length=1000)


class VehicleUpdate(StrictModel):
    site_id: uuid.UUID | None = None
    vehicle_category_id: uuid.UUID | None = None
    registration_number: str | None = Field(default=None, min_length=2, max_length=20)
    serial_number: str | None = Field(default=None, min_length=1, max_length=60)
    make: str | None = Field(default=None, max_length=60)
    model: str | None = Field(default=None, max_length=60)
    model_year: int | None = Field(default=None, ge=1950, le=2100)
    ownership_type: Ownership | None = None
    fuel_type: FuelType | None = None
    rated_payload_kg: int | None = Field(default=None, gt=0, le=1_000_000)
    commissioned_on: date | None = None
    notes: str | None = Field(default=None, max_length=1000)


class VehicleStatusChange(StrictModel):
    status: OperationalStatus
    reason_code: ReasonCode | None = None


class VehicleRetire(StrictModel):
    reason_code: ReasonCode


class VehicleOut(BaseModel):
    vehicle_id: uuid.UUID
    site_id: uuid.UUID
    vehicle_category_id: uuid.UUID
    fleet_number: str
    registration_number: str | None
    serial_number: str | None
    make: str | None
    model: str | None
    model_year: int | None
    ownership_type: str
    fuel_type: str | None
    rated_payload_kg: int | None
    status: str
    status_reason_code: str | None
    status_changed_at: datetime
    commissioned_on: date | None
    decommissioned_on: date | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    row_version: int


class StatusHistoryOut(BaseModel):
    from_status: str | None
    to_status: str
    reason_code: str | None
    changed_at: datetime
    changed_by: uuid.UUID | None = None  # TENANT_ADMIN et AUDITOR seulement (SEC1B-08)


# --- Compteurs et documents (lot 2c, PLAN_LOT2 §8) ------------------------------------------------------

MeterKind = Literal["ODOMETER_KM", "HOUR_METER"]
# Remise à zéro motivée : seule exception à la progression du compteur (RM-102), action distincte.
ResetReason = Literal["METER_REPLACED", "ROLLOVER", "ENTRY_ERROR"]
DocumentType = Literal[
    "INSURANCE",
    "TECHNICAL_INSPECTION",
    "INTERNAL_INSPECTION",
    "LIFTING_INSPECTION",
    "ROAD_PERMIT",
    "REGISTRATION",
    "SITE_ACCESS_PERMIT",
    "OTHER",
]
# Seule la carte grise est sans échéance (revue L2C-R-03) ; tout autre document a une date de fin.
UNDATED_TYPES: frozenset[str] = frozenset({"REGISTRATION"})
WithdrawReason = Literal["REPLACED", "LOST", "REVOKED_BY_AUTHORITY", "ENTRY_ERROR", "OTHER"]
# Référence administrative : chiffres, lettres et séparateurs, sans donnée personnelle.
REFERENCE = r"^[A-Za-z0-9 /._-]{1,60}$"


class MeterReadingCreate(StrictModel):
    meter_kind: MeterKind
    # Kilomètres ou heures, au dixième.
    value: Decimal = Field(ge=0, lt=100_000_000, max_digits=12, decimal_places=1)
    # Heure du relevé (fuseau obligatoire) ; par défaut l'heure du serveur (RM-101).
    read_at: AwareDatetime | None = None


class MeterReset(MeterReadingCreate):
    reset_reason: ResetReason


class MeterReadingOut(BaseModel):
    vehicle_meter_reading_id: uuid.UUID
    vehicle_id: uuid.UUID
    meter_kind: str
    value: float
    read_at: datetime
    source: str
    reset_reason: str | None
    # Masqué hors administration et audit (revue L2C-R-08).
    recorded_by: uuid.UUID | None = None
    recorded_at: datetime


class DocumentCreate(StrictModel):
    doc_type: DocumentType
    # Numéro du document (police, procès-verbal…) : pas de donnée personnelle.
    reference: str = Field(pattern=REFERENCE)
    # Organisme émetteur (assureur, centre de contrôle, autorité) : jamais le nom d'une personne.
    issuer: str | None = Field(default=None, min_length=2, max_length=120)
    valid_from: date | None = None
    # Obligatoire sauf pour la carte grise.
    valid_until: date | None = None


class DocumentWithdraw(StrictModel):
    reason_code: WithdrawReason


class DocumentOut(BaseModel):
    vehicle_document_id: uuid.UUID
    vehicle_id: uuid.UUID
    vehicle_fleet_number: str
    site_id: uuid.UUID
    doc_type: str
    reference: str
    issuer: str | None
    valid_from: date | None
    valid_until: date | None
    status: str
    status_reason: str | None
    # Type exigé par la catégorie du véhicule (D-42) : un exemplaire valide conditionne l'affectation.
    required: bool
    # Validité dérivée des dates au fuseau du site (D-03) : VALID, EXPIRING, EXPIRED, WITHDRAWN…
    validity: str
    created_at: datetime
    row_version: int


class VehicleDocumentsOut(BaseModel):
    documents: list[DocumentOut]
    required_types: list[str]
    # Types exigés sans exemplaire valide : affectation refusée ou signalée selon la politique (D-42).
    missing_types: list[str]


class CategoryDocumentsIn(StrictModel):
    doc_types: list[DocumentType] = Field(max_length=8)


class CategoryDocumentsOut(BaseModel):
    vehicle_category_id: uuid.UUID
    doc_types: list[str]
