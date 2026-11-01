"""No declared hash or pending record can authorize document-backed review."""

import pytest

from app.legal.document_eligibility import (
    DocumentEvidence,
    DocumentStatus,
    document_eligible_for_submission,
)

SHA = "a" * 64


def evidence(**changes: object) -> DocumentEvidence:
    fields = {
        "tenant_id": "tenant-a",
        "contract_id": "contract-a",
        "sha256": SHA,
        "status": DocumentStatus.VERIFIED,
        "stored_object_verified": True,
        "malware_scan_passed": True,
    }
    fields.update(changes)
    return DocumentEvidence(**fields)  # type: ignore[arg-type]


def eligible(item: DocumentEvidence | None, sha: str | None = SHA) -> bool:
    return document_eligible_for_submission(
        tenant_id="tenant-a",
        contract_id="contract-a",
        declared_sha256=sha,
        evidence=item,
    )


def test_only_verified_stored_scanned_document_is_eligible() -> None:
    assert eligible(evidence())
    assert not eligible(None)
    assert not eligible(evidence(), sha=None)


@pytest.mark.parametrize(
    "changes",
    [
        {"tenant_id": "tenant-b"},
        {"contract_id": "contract-b"},
        {"sha256": "b" * 64},
        {"status": DocumentStatus.PENDING},
        {"status": DocumentStatus.REJECTED},
        {"stored_object_verified": False},
        {"malware_scan_passed": False},
    ],
)
def test_evidence_fail_closed(changes: dict[str, object]) -> None:
    assert not eligible(evidence(**changes))
