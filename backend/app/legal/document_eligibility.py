"""Document eligibility policy for the future contract submission gate.

A client-supplied hash, and a PENDING registry row, are never proof of verification.
"""

from dataclasses import dataclass
from enum import StrEnum


class DocumentStatus(StrEnum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class DocumentEvidence:
    tenant_id: str
    contract_id: str
    sha256: str
    status: DocumentStatus
    stored_object_verified: bool
    malware_scan_passed: bool


def document_eligible_for_submission(
    *,
    tenant_id: str,
    contract_id: str,
    declared_sha256: str | None,
    evidence: DocumentEvidence | None,
) -> bool:
    """Fail closed unless verified stored bytes match the contract and tenant."""
    return bool(
        evidence is not None
        and declared_sha256 is not None
        and evidence.tenant_id == tenant_id
        and evidence.contract_id == contract_id
        and evidence.sha256 == declared_sha256
        and evidence.status == DocumentStatus.VERIFIED
        and evidence.stored_object_verified
        and evidence.malware_scan_passed
    )
