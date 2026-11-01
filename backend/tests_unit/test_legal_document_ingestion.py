"""Ingestion service rejects failed scans and never writes before scanning."""

import uuid

import pytest

from app.legal.document_ingestion import ingest_contract_pdf
from app.legal.malware_scan import ScanVerdict

PDF = b"%PDF-1.7\n1 0 obj\nendobj\n%%EOF\n"


class Scanner:
    def __init__(self, verdict: ScanVerdict) -> None:
        self.verdict = verdict

    def scan(self, content: bytes) -> ScanVerdict:
        assert content == PDF
        return self.verdict


class Store:
    def __init__(self, *, tamper: bool = False) -> None:
        self.saved: dict[str, bytes] = {}
        self.tamper = tamper

    def put(self, *, key: str, content: bytes) -> None:
        self.saved[key] = content

    def get(self, *, key: str) -> bytes:
        content = self.saved[key]
        return content + b"tamper" if self.tamper else content


def test_ingestion_scans_before_private_write() -> None:
    tenant, contract = uuid.uuid4(), uuid.uuid4()
    store = Store()
    result = ingest_contract_pdf(
        tenant_id=tenant,
        contract_id=contract,
        payload=PDF,
        scanner=Scanner(ScanVerdict.CLEAN),
        store=store,
    )
    assert result.byte_size == len(PDF)
    assert result.object_key.startswith(f"legal/{tenant}/contracts/{contract}/")
    assert store.saved[result.object_key] == PDF


@pytest.mark.parametrize("verdict", [ScanVerdict.INFECTED, ScanVerdict.ERROR])
def test_failed_scan_never_writes(verdict: ScanVerdict) -> None:
    store = Store()
    with pytest.raises(ValueError, match="malware"):
        ingest_contract_pdf(
            tenant_id=uuid.uuid4(),
            contract_id=uuid.uuid4(),
            payload=PDF,
            scanner=Scanner(verdict),
            store=store,
        )
    assert store.saved == {}


def test_unconfigured_scanner_never_writes() -> None:
    store = Store()
    with pytest.raises(ValueError, match="unavailable"):
        ingest_contract_pdf(
            tenant_id=uuid.uuid4(),
            contract_id=uuid.uuid4(),
            payload=PDF,
            scanner=None,
            store=store,
        )
    assert store.saved == {}


def test_corrupted_readback_is_rejected() -> None:
    with pytest.raises(ValueError, match="integrity"):
        ingest_contract_pdf(
            tenant_id=uuid.uuid4(),
            contract_id=uuid.uuid4(),
            payload=PDF,
            scanner=Scanner(ScanVerdict.CLEAN),
            store=Store(tamper=True),
        )
