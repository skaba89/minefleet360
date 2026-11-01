"""Redacted operational summary for tenant document reconciliation.

Object keys can contain sensitive identifiers and must not enter routine logs.
"""

from dataclasses import dataclass

from app.legal.document_reconciliation import DocumentReconciliation


@dataclass(frozen=True)
class DocumentReconciliationSummary:
    orphan_count: int
    missing_count: int
    consistent: bool


def summarize_document_reconciliation(
    result: DocumentReconciliation,
) -> DocumentReconciliationSummary:
    """Only expose aggregate counts, not private S3 keys or filenames."""
    orphan_count = len(result.orphan_object_keys)
    missing_count = len(result.missing_object_keys)
    return DocumentReconciliationSummary(
        orphan_count=orphan_count,
        missing_count=missing_count,
        consistent=orphan_count == 0 and missing_count == 0,
    )
