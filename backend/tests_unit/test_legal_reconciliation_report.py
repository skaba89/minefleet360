"""Reconciliation reports must not leak private object identifiers."""

from dataclasses import asdict

from app.legal.document_reconciliation import DocumentReconciliation
from app.legal.reconciliation_report import summarize_document_reconciliation


def test_report_exposes_counts_only() -> None:
    private_key = "legal/tenant/contracts/secret-contract.pdf"
    result = DocumentReconciliation(
        orphan_object_keys=(private_key,),
        missing_object_keys=("legal/tenant/contracts/missing.pdf",),
    )
    report = summarize_document_reconciliation(result)
    assert report.orphan_count == 1
    assert report.missing_count == 1
    assert not report.consistent
    assert private_key not in str(asdict(report))
    assert set(asdict(report)) == {"orphan_count", "missing_count", "consistent"}


def test_empty_report_is_consistent() -> None:
    report = summarize_document_reconciliation(
        DocumentReconciliation(orphan_object_keys=(), missing_object_keys=())
    )
    assert report.consistent
    assert report.orphan_count == 0
    assert report.missing_count == 0
