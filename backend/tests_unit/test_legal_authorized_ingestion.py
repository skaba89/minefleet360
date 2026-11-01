"""Tenant/site/draft checks are applied before malware scan and object writes."""

import uuid

import pytest

from app.legal.authorized_ingestion import ingest_authorized_contract_pdf
from app.legal.document_upload_policy import DocumentUploadContext
from app.legal.malware_scan import ScanVerdict

PDF = b"%PDF-1.7\n1 0 obj\nendobj\n%%EOF\n"


class Scanner:
    def __init__(self) -> None:
        self.calls = 0

    def scan(self, content: bytes) -> ScanVerdict:
        self.calls += 1
        return ScanVerdict.CLEAN


class Store:
    def __init__(self) -> None:
        self.items: dict[str, bytes] = {}

    def put(self, *, key: str, content: bytes) -> None:
        self.items[key] = content

    def get(self, *, key: str) -> bytes:
        return self.items[key]


TENANT = uuid.uuid4()
SITE = uuid.uuid4()


def context(**changes: object) -> DocumentUploadContext:
    fields = {
        "authenticated_tenant_id": TENANT,
        "contract_tenant_id": TENANT,
        "contract_site_id": SITE,
        "accessible_site_ids": frozenset({SITE}),
        "tenant_wide": False,
        "contract_status": "DRAFT",
    }
    fields.update(changes)
    return DocumentUploadContext(**fields)  # type: ignore[arg-type]


def test_authorized_ingestion_calls_scanner_and_store() -> None:
    scanner, store = Scanner(), Store()
    result = ingest_authorized_contract_pdf(
        context=context(),
        contract_id=uuid.uuid4(),
        payload=PDF,
        scanner=scanner,
        store=store,
    )
    assert scanner.calls == 1
    assert store.items[result.object_key] == PDF


@pytest.mark.parametrize(
    "changes",
    [
        {"contract_tenant_id": uuid.uuid4()},
        {"accessible_site_ids": frozenset()},
        {"contract_status": "APPROVED"},
    ],
)
def test_unauthorized_ingestion_has_no_side_effects(changes: dict[str, object]) -> None:
    scanner, store = Scanner(), Store()
    with pytest.raises(PermissionError):
        ingest_authorized_contract_pdf(
            context=context(**changes),
            contract_id=uuid.uuid4(),
            payload=PDF,
            scanner=scanner,
            store=store,
        )
    assert scanner.calls == 0
    assert store.items == {}
