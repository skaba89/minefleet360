"""Stored contract PDF must be owned, intact and freshly scanned before review."""

import hashlib
import uuid
from unittest.mock import MagicMock

import pytest

from app.legal.document_reverification import reverify_stored_contract_pdf
from app.legal.malware_scan import ScanVerdict

PDF = b"%PDF-1.7\n1 0 obj\nendobj\n%%EOF\n"


def params() -> dict[str, object]:
    tenant, contract = uuid.uuid4(), uuid.uuid4()
    return {
        "tenant_id": tenant,
        "contract_id": contract,
        "object_key": f"legal/{tenant}/contracts/{contract}/document.pdf",
        "expected_sha256": hashlib.sha256(PDF).hexdigest(),
        "expected_size": len(PDF),
    }


def test_reverification_requires_clean_matching_stored_pdf() -> None:
    store, scanner = MagicMock(), MagicMock()
    store.get.return_value = PDF
    scanner.scan.return_value = ScanVerdict.CLEAN
    assert reverify_stored_contract_pdf(**params(), scanner=scanner, store=store)
    scanner.scan.assert_called_once_with(PDF)


@pytest.mark.parametrize("verdict", [ScanVerdict.INFECTED, ScanVerdict.ERROR])
def test_reverification_rejects_nonclean_scan(verdict: ScanVerdict) -> None:
    store, scanner = MagicMock(), MagicMock()
    store.get.return_value = PDF
    scanner.scan.return_value = verdict
    with pytest.raises(ValueError, match="malware"):
        reverify_stored_contract_pdf(**params(), scanner=scanner, store=store)


def test_reverification_rejects_mismatch_before_scanning() -> None:
    store, scanner = MagicMock(), MagicMock()
    store.get.return_value = PDF + b"tampering"
    with pytest.raises(ValueError):
        reverify_stored_contract_pdf(**params(), scanner=scanner, store=store)
    scanner.scan.assert_not_called()


def test_reverification_rejects_foreign_tenant_before_storage_access() -> None:
    options = params()
    options["tenant_id"] = uuid.uuid4()
    store, scanner = MagicMock(), MagicMock()
    with pytest.raises(ValueError, match="ownership"):
        reverify_stored_contract_pdf(**options, scanner=scanner, store=store)
    store.get.assert_not_called()


def test_reverification_rejects_missing_scanner_before_storage_access() -> None:
    store = MagicMock()
    with pytest.raises(ValueError, match="scanner"):
        reverify_stored_contract_pdf(**params(), scanner=None, store=store)
    store.get.assert_not_called()
