"""Schémas conducteurs/permis/habilitations. Aucune donnée hors liste du lot 1 (D-15) : extra=forbid."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.http import StrictModel
from app.identity.schemas import PHONE_PATTERN

DriverStatus = Literal["ACTIVE", "UNAVAILABLE", "SUSPENDED", "INACTIVE"]
EmploymentType = Literal["EMPLOYEE", "TEMP_AGENCY", "SUBCONTRACTOR"]
UnavailabilityReason = Literal["LEAVE", "TRAINING", "OTHER"]
# Codes uniquement (pas de texte libre : minimisation, pas de motif médical).
SuspensionReason = Literal["HSE_DECISION", "INVESTIGATION", "LICENSE_ISSUE", "OTHER"]
QualificationType = Literal["DRIVING_AUTHORIZATION", "SAFETY_TRAINING", "OTHER"]


class DriverCreate(StrictModel):
    site_id: uuid.UUID
    employee_number: str = Field(pattern=r"^[A-Za-z0-9_-]{1,30}$")
    last_name: str = Field(min_length=1, max_length=80)
    first_name: str = Field(min_length=1, max_length=80)
    phone: str | None = Field(default=None, pattern=PHONE_PATTERN)
    employment_type: EmploymentType = "EMPLOYEE"
    external_company_name: str | None = Field(default=None, max_length=120)
    hire_date: date | None = None


class DriverUpdate(StrictModel):
    site_id: uuid.UUID | None = None
    last_name: str | None = Field(default=None, min_length=1, max_length=80)
    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    phone: str | None = Field(default=None, pattern=PHONE_PATTERN)
    employment_type: EmploymentType | None = None
    external_company_name: str | None = Field(default=None, max_length=120)
    hire_date: date | None = None


class DriverStatusChange(StrictModel):
    status: DriverStatus
    unavailability_reason: UnavailabilityReason | None = None
    unavailable_until: date | None = None
    suspension_reason_code: SuspensionReason | None = None
    exit_date: date | None = None


class DriverOut(BaseModel):
    """Champs masqués (phone, suspension_reason_code, données RH) ABSENTS pour les rôles non autorisés."""

    driver_id: uuid.UUID
    site_id: uuid.UUID
    employee_number: str
    last_name: str
    first_name: str
    status: str
    unavailability_reason: str | None = None
    unavailable_until: date | None = None
    authorized_category_ids: list[uuid.UUID] = []
    phone: str | None = None
    suspension_reason_code: str | None = None
    employment_type: str | None = None
    external_company_name: str | None = None
    hire_date: date | None = None
    exit_date: date | None = None
    warnings: list[str] | None = None
    created_at: datetime
    row_version: int


class LicenseCreate(StrictModel):
    license_number: str = Field(min_length=3, max_length=40)
    category_code: str = Field(pattern=r"^[A-Z0-9]{1,5}$")
    issuing_authority: str | None = Field(default=None, max_length=120)
    issue_date: date
    expiry_date: date
    document_reference: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def _dates(self) -> "LicenseCreate":
        if self.expiry_date <= self.issue_date:
            raise ValueError("expiry_date doit être postérieure à issue_date")
        return self


class LicenseUpdate(StrictModel):
    status: Literal["VALID", "SUSPENDED", "WITHDRAWN"] | None = None
    status_note: str | None = Field(default=None, max_length=300)
    issuing_authority: str | None = Field(default=None, max_length=120)
    document_reference: str | None = Field(default=None, max_length=80)


class LicenseOut(BaseModel):
    driver_license_id: uuid.UUID
    driver_id: uuid.UUID
    category_code: str
    issue_date: date
    expiry_date: date
    status: str
    validity: str
    issuing_authority: str | None = None
    license_number: str | None = None
    document_reference: str | None = None
    status_note: str | None = None
    row_version: int


class QualificationCreate(StrictModel):
    qualification_type: QualificationType
    vehicle_category_id: uuid.UUID | None = None
    site_id: uuid.UUID | None = None
    valid_from: date
    valid_to: date | None = None
    issued_by_name: str | None = Field(default=None, max_length=120)
    reference: str | None = Field(default=None, max_length=80)
    restrictions: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _rules(self) -> "QualificationCreate":
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to doit être postérieure ou égale à valid_from")
        if self.qualification_type == "DRIVING_AUTHORIZATION" and self.vehicle_category_id is None:
            raise ValueError("une habilitation de conduite exige vehicle_category_id")
        return self


class QualificationRevoke(StrictModel):
    status: Literal["SUSPENDED", "REVOKED"]


class QualificationOut(BaseModel):
    driver_qualification_id: uuid.UUID
    driver_id: uuid.UUID
    qualification_type: str
    vehicle_category_id: uuid.UUID | None
    site_id: uuid.UUID | None
    valid_from: date
    valid_to: date | None
    status: str
    validity: str
    issued_by_name: str | None = None  # texte libre : HR/HSE seulement (SEC1B-03)
    reference: str | None = None
    restrictions: str | None = None
    row_version: int


class ExpirationItem(BaseModel):
    kind: Literal["LICENSE", "QUALIFICATION"]
    item_id: uuid.UUID
    driver_id: uuid.UUID
    employee_number: str
    driver_name: str
    site_id: uuid.UUID
    label: str
    expires_on: date
    validity: str
