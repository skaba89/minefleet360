"""Validation guards for proposed contract and insurance API inputs."""

import uuid

import pytest
from pydantic import ValidationError

from app.legal.schemas import ContractDraftInput, InsurancePolicyInput

SITE = uuid.UUID("00000000-0000-4000-8000-000000000001")


def contract(**changes: object) -> dict[str, object]:
    return {
        "site_id": SITE,
        "reference": "CT-001",
        "title": "Transport",
        "contract_type": "TRANSPORT",
        "counterparty_name": "Fournisseur A",
        **changes,
    }


def policy(**changes: object) -> dict[str, object]:
    return {
        "site_id": SITE,
        "policy_number": "POL-001",
        "insurer_name": "Assureur A",
        "coverage_type": "FLEET",
        "coverage_start": "2026-01-01",
        "coverage_end": "2026-12-31",
        **changes,
    }


def test_contract_input_accepts_valid_draft() -> None:
    assert ContractDraftInput.model_validate(contract()).reference == "CT-001"


@pytest.mark.parametrize(
    "changes",
    [
        {"title": "   "},
        {"counterparty_name": ""},
        {"reference": "X" * 121},
        {"document_sha256": "not-a-hash"},
        {"contract_type": "UNRECOGNIZED"},
        {"tenant_id": str(SITE)},
        {"created_by": str(SITE)},
    ],
)
def test_contract_input_rejects_invalid_or_server_owned_fields(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ContractDraftInput.model_validate(contract(**changes))


def test_insurance_input_accepts_valid_policy() -> None:
    assert InsurancePolicyInput.model_validate(policy()).currency == "GNF"


@pytest.mark.parametrize(
    "changes",
    [
        {"coverage_end": "2025-12-31"},
        {"currency": "USD"},
        {"premium_amount": "-0.01"},
        {"insurer_name": "   "},
        {"policy_number": ""},
        {"coverage_type": "UNRECOGNIZED"},
        {"tenant_id": str(SITE)},
        {"created_by": str(SITE)},
    ],
)
def test_insurance_input_rejects_invalid_or_server_owned_fields(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        InsurancePolicyInput.model_validate(policy(**changes))
