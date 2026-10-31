"""Validated payloads for future tenant-scoped contracts and insurance APIs.

Tenant/site ownership and authenticated creator are NEVER client supplied.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from app.core.http import StrictModel


class ContractDraftInput(StrictModel):
    site_id: uuid.UUID
    reference: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=240)
    contract_type: Literal["SUPPLIER", "TRANSPORT", "SUBCONTRACTOR", "EMPLOYMENT", "LEASE", "OTHER"]
    counterparty_name: str = Field(min_length=1, max_length=240)
    document_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_text(self) -> "ContractDraftInput":
        if not all((self.reference.strip(), self.title.strip(), self.counterparty_name.strip())):
            raise ValueError("contract text fields must not be blank")
        return self


class InsurancePolicyInput(StrictModel):
    site_id: uuid.UUID
    policy_number: str = Field(min_length=1, max_length=120)
    insurer_name: str = Field(min_length=1, max_length=240)
    coverage_type: Literal[
        "FLEET", "VEHICLE", "CARGO", "LIABILITY", "EMPLOYEE", "EQUIPMENT", "OTHER"
    ]
    coverage_start: date
    coverage_end: date
    premium_amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    currency: Literal["GNF"] = "GNF"
    contract_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_policy(self) -> "InsurancePolicyInput":
        if not self.policy_number.strip() or not self.insurer_name.strip():
            raise ValueError("insurance text fields must not be blank")
        if self.coverage_end < self.coverage_start:
            raise ValueError("coverage_end must not precede coverage_start")
        return self
